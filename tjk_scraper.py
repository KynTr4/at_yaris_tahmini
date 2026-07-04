"""TJK günlük yarış sonuçlarını anlık çeker, SQLite'a kaydeder, model tahminleriyle karşılaştırır.

Architecture
============
- HTML scraping happens in RAM only — NO file writes.
- Results are persisted to SQLite (tables from migration 018).
- The API reads from SQLite (fast path), only scrapes when data is stale.
- Deduplication and live-result updates via SQLite UPSERT (migration 018).

URL formatı::

    https://www.tjk.org/TR/YarisSever/Info/Page/GunlukYarisSonuclari
    ?QueryParameter_Tarih=DD/MM/YYYY&SehirAdi=İstanbul
"""

from __future__ import annotations

import logging
import re
import sqlite3
import unicodedata
from datetime import date, datetime, timedelta
from typing import Any

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TJK_BASE = "https://www.tjk.org/TR/YarisSever/Info/Page/GunlukYarisSonuclari"

TURKISH_CITIES: list[str] = [
    "İstanbul",
    "İzmir",
    "Ankara",
    "Adana",
    "Antalya",
    "Bursa",
    "Diyarbakır",
    "Elazığ",
    "Kocaeli",
    "Şanlıurfa",
]

# DB track names → canonical TJK city name used in URL parameter
TRACK_TO_CITY: dict[str, str] = {
    "ISTANBUL": "İstanbul",
    "IZMIR": "İzmir",
    "ANKARA": "Ankara",
    "ADANA": "Adana",
    "ANTALYA": "Antalya",
    "BURSA": "Bursa",
    "DIYARBAKIR": "Diyarbakır",
    "ELAZIG": "Elazığ",
    "KOCAELI": "Kocaeli",
    "SANLIURFA": "Şanlıurfa",
    # Alternative / venue-level names
    "VELIEFENDI": "İstanbul",
    "SIRINYER": "İzmir",
    "YESILOBA": "Adana",
    "OSMANGAZI": "Bursa",
    "KARTEPE": "Kocaeli",
    "75. YIL": "Ankara",
}

_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.tjk.org/",
}

# Module-level cache: avoid calling apply_migrations() more than once per db_path
_schema_applied: set[str] = set()


# ---------------------------------------------------------------------------
# Low-level text helpers
# ---------------------------------------------------------------------------


def _fold(value: str) -> str:
    """Accent-strip, uppercase, and strip a string (used for dict key lookups)."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).upper().strip()


def normalize_horse_name(raw: str) -> str:
    """Return a canonical, storage-ready horse name.

    - Strips any trailing parenthetical (start number or otherwise):
      ``YAĞIZATEŞ(8)`` → ``YAĞIZATEŞ``
    - Collapses multiple internal spaces.
    - Returns ``UPPER().strip()``.
    """
    name = re.sub(r"\s*\([^)]*\)\s*$", "", raw.strip())
    name = re.sub(r"\s+", " ", name)
    return name.upper().strip()


def normalize_city(raw: str) -> str:
    """Map any track/city string to its canonical Turkish city name.

    Folds (accent-strips) the first word and looks it up in :data:`TRACK_TO_CITY`.
    Falls back to the original value when no mapping is found.
    """
    folded_first = _fold(raw).split()[0] if raw else ""
    return TRACK_TO_CITY.get(folded_first, raw)


# ---------------------------------------------------------------------------
# Schema bootstrap (migration integration)
# ---------------------------------------------------------------------------


def _ensure_schema(db_path: str) -> None:
    """Apply all pending SQL migrations exactly once per *db_path* per process.

    Uses the module-level :data:`_schema_applied` set to avoid repeated calls.
    Only caches the key when ``apply_migrations`` returns without raising, so
    a transient failure (e.g. wrong MIGRATIONS_DIR) retries on the next call
    rather than silently caching a broken state.
    """
    key = str(db_path)
    if key in _schema_applied:
        return
    from migrate_provenance_schema import (
        apply_migrations,  # local import; no circular deps
    )

    applied = apply_migrations(key)  # let exceptions propagate to the caller
    if applied:
        logger.debug("Applied migrations: %s", applied)
    _schema_applied.add(key)


# ---------------------------------------------------------------------------
# HTML fetching & parsing — everything stays in RAM
# ---------------------------------------------------------------------------


def fetch_tjk_results(target_date: date, city: str) -> dict[str, Any]:
    """Fetch daily race results from TJK for *target_date* / *city*.

    All HTML processing is done in RAM; nothing is written to disk.

    Returns::

        {
          "city":  "İstanbul",
          "date":  "2026-07-03",
          "races": [
            {
              "race_no":   1,
              "race_time": "17.15",
              "horses": [
                {"finish_pos": 1, "horse_name": "YAĞIZATEŞ", "start_no": 8,
                 "finish_time": "1.34.04", "odds": "10.50", "agf": "%8(3)"},
                ...
              ]
            }, ...
          ],
          "error": None          # str on failure
        }
    """
    date_str = target_date.strftime("%d/%m/%Y")
    url = f"{TJK_BASE}?QueryParameter_Tarih={date_str}&SehirAdi={city}"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        resp.encoding = "utf-8"
    except requests.RequestException as exc:
        logger.warning("TJK fetch failed city=%s date=%s: %s", city, date_str, exc)
        return {
            "city": city,
            "date": target_date.isoformat(),
            "races": [],
            "error": str(exc),
        }

    soup = BeautifulSoup(resp.text, "html.parser")
    races = _parse_races(soup, city)
    return {
        "city": city,
        "date": target_date.isoformat(),
        "races": races,
        "error": None,
    }


def _parse_races(soup: BeautifulSoup, city: str) -> list[dict[str, Any]]:
    """Extract all races and their horse results from a parsed TJK result page."""
    races: list[dict[str, Any]] = []

    panes = soup.select("div.races-panes div[id]")
    for pane in panes:
        if pane.get("id") == "all":
            continue

        # Some pages embed a city attribute on the pane; skip mismatches.
        pane_city = str(pane.get("sehir") or "")
        if pane_city and pane_city.upper() != city.upper():
            continue

        header = pane.select_one("div.race-details h3.race-no a")
        if not header:
            continue
        header_text = header.get_text(" ", strip=True)
        race_no_match = re.search(r"(\d+)\.\s*Ko[sş]u", header_text, re.I)
        time_match = re.search(r"(\d{2}\.\d{2})", header_text)
        if not race_no_match:
            continue
        race_no = int(race_no_match.group(1))
        race_time = time_match.group(1) if time_match else ""

        horses = _parse_horses(pane)
        if not horses:
            continue

        races.append({"race_no": race_no, "race_time": race_time, "horses": horses})

    return sorted(races, key=lambda r: r["race_no"])


def _parse_horses(pane: Any) -> list[dict[str, Any]]:
    """Extract the finisher list from a single race pane element."""
    horses: list[dict[str, Any]] = []
    for row in pane.select("table tbody tr"):
        pos_td = row.select_one("td.gunluk-GunlukYarisSonuclari-SONUCNO")
        name_td = row.select_one("td.gunluk-GunlukYarisSonuclari-AtAdi3")
        time_td = row.select_one("td.gunluk-GunlukYarisSonuclari-Derece")
        odds_td = row.select_one("td.gunluk-GunlukYarisSonuclari-Gny")
        agf_td = row.select_one("td.gunluk-GunlukYarisSonuclari-AGFORAN")

        if not name_td:
            continue

        name_link = name_td.select_one("a")
        if name_link:
            # Remove tooltip <sup> fragments before reading text.
            for sup in name_td.select("sup"):
                sup.decompose()
            name_raw = name_link.get_text(" ", strip=True)
        else:
            name_raw = name_td.get_text(" ", strip=True)

        start_no_match = re.search(r"\((\d+)\)\s*$", name_raw.strip())
        start_no = int(start_no_match.group(1)) if start_no_match else None
        horse_name = normalize_horse_name(name_raw)

        pos_text = pos_td.get_text(strip=True) if pos_td else ""
        try:
            finish_pos = int(pos_text)
        except (ValueError, TypeError):
            finish_pos = None  # "Koşmaz" / DNS / DNF

        finish_time = time_td.get_text(strip=True) if time_td else ""
        odds_span = odds_td.select_one("span") if odds_td else None
        odds = odds_span.get_text(strip=True) if odds_span else ""

        agf_text = ""
        if agf_td:
            agf_link = agf_td.select_one("a")
            agf_text = (
                agf_link.get_text(strip=True)
                if agf_link
                else agf_td.get_text(strip=True)
            )

        horses.append(
            {
                "finish_pos": finish_pos,
                "horse_name": horse_name,
                "start_no": start_no,
                "finish_time": finish_time,
                "odds": odds,
                "agf": agf_text,
            }
        )

    return horses


# ---------------------------------------------------------------------------
# SQLite persistence
# ---------------------------------------------------------------------------


def persist_results(db_path: str, city_data: dict[str, Any]) -> int:
    """Persist raw TJK race results into ``tjk_race_results``.

    Uses an UPSERT so partial live results can be completed by later scrapes
    without creating duplicate rows (UNIQUE constraint: race_date, city,
    race_no, horse_name).

    Returns:
        Number of rows written.
    """
    _ensure_schema(db_path)
    city = city_data.get("city", "")
    race_date = city_data.get("date", "")
    races = city_data.get("races", [])

    rows_inserted = 0
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        with conn:  # single transaction; auto-commits, rolls back on exception
            for race in races:
                race_no = race["race_no"]
                race_time = race.get("race_time", "")
                for horse in race.get("horses", []):
                    cur = conn.execute(
                        """INSERT INTO tjk_race_results
                               (race_date, city, race_no, race_time,
                                horse_name, horse_no, actual_rank,
                                finish_time, ganyan, agf)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(race_date, city, race_no, horse_name)
                           DO UPDATE SET
                               race_time=excluded.race_time,
                               horse_no=excluded.horse_no,
                               actual_rank=excluded.actual_rank,
                               finish_time=excluded.finish_time,
                               ganyan=excluded.ganyan,
                               agf=excluded.agf,
                               scraped_at=strftime('%Y-%m-%dT%H:%M:%SZ', 'now')""",
                        (
                            race_date,
                            city,
                            race_no,
                            race_time,
                            horse["horse_name"],
                            horse.get("start_no"),
                            horse.get("finish_pos"),
                            horse.get("finish_time", ""),
                            horse.get("odds", ""),
                            horse.get("agf", ""),
                        ),
                    )
                    rows_inserted += cur.rowcount
    finally:
        conn.close()

    logger.debug(
        "persist_results: city=%s date=%s inserted=%d", city, race_date, rows_inserted
    )
    return rows_inserted


# ---------------------------------------------------------------------------
# Predictions query
# ---------------------------------------------------------------------------

# Primary SQL: prediction_snapshots joined with program_snapshots (shadow mode).
_PRED_SNAPSHOTS_SQL = """\
WITH preds AS (
    SELECT *, ROW_NUMBER() OVER(
        PARTITION BY race_id, horse_id
        ORDER BY prediction_time DESC, prediction_id DESC
    ) AS rn
    FROM prediction_snapshots
), prog AS (
    SELECT race_id, horse_id, horse_name, race_no, track,
           ROW_NUMBER() OVER(
               PARTITION BY race_id, horse_id
               ORDER BY captured_at DESC, snapshot_id DESC
           ) AS rn
    FROM program_snapshots
)
SELECT p.race_id,
       COALESCE(g.race_no, '')          AS race_no,
       COALESCE(g.track, '')            AS track,
       COALESCE(g.horse_name, p.horse_id) AS horse_name,
       p.horse_id,
       p.predicted_rank,
       p.ensemble_probability           AS ensemble_prob,
       p.catboost_probability           AS catboost_prob,
       p.xgboost_probability            AS xgboost_prob,
       p.logistic_probability           AS logistic_prob,
       'prediction_snapshots'           AS pred_source
FROM preds p
LEFT JOIN prog g
       ON g.race_id  = p.race_id
      AND g.horse_id = p.horse_id
      AND g.rn       = 1
WHERE p.rn = 1
  AND date(p.race_start_at, '+3 hours') = ?
ORDER BY g.race_no, p.predicted_rank
"""

# Fallback: same query but substitutes NULL for logistic_probability
# (used when the column does not yet exist in an older schema).
_PRED_SNAPSHOTS_NO_LOGISTIC_SQL = """\
WITH preds AS (
    SELECT *, ROW_NUMBER() OVER(
        PARTITION BY race_id, horse_id
        ORDER BY prediction_time DESC, prediction_id DESC
    ) AS rn
    FROM prediction_snapshots
), prog AS (
    SELECT race_id, horse_id, horse_name, race_no, track,
           ROW_NUMBER() OVER(
               PARTITION BY race_id, horse_id
               ORDER BY captured_at DESC, snapshot_id DESC
           ) AS rn
    FROM program_snapshots
)
SELECT p.race_id,
       COALESCE(g.race_no, '')          AS race_no,
       COALESCE(g.track, '')            AS track,
       COALESCE(g.horse_name, p.horse_id) AS horse_name,
       p.horse_id,
       p.predicted_rank,
       p.ensemble_probability           AS ensemble_prob,
       p.catboost_probability           AS catboost_prob,
       p.xgboost_probability            AS xgboost_prob,
       NULL                             AS logistic_prob,
       'prediction_snapshots'           AS pred_source
FROM preds p
LEFT JOIN prog g
       ON g.race_id  = p.race_id
      AND g.horse_id = p.horse_id
      AND g.rn       = 1
WHERE p.rn = 1
  AND date(p.race_start_at, '+3 hours') = ?
ORDER BY g.race_no, p.predicted_rank
"""


def get_predictions_for_date(db_path: str, target_date: date) -> list[dict[str, Any]]:
    """Return model predictions for *target_date* from SQLite.

    Tries ``prediction_snapshots`` (canonical shadow mode) first, then falls
    back to ``model_prediction_runs`` (predict_today.py output).

    Each dict contains::

        race_id, race_no, track, horse_name, horse_id,
        predicted_rank, ensemble_prob, catboost_prob,
        xgboost_prob, logistic_prob, pred_source
    """
    _ensure_schema(db_path)
    date_iso = target_date.isoformat()
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        conn.row_factory = sqlite3.Row

        # --- 1. prediction_snapshots (preferred) ---
        for sql in (_PRED_SNAPSHOTS_SQL, _PRED_SNAPSHOTS_NO_LOGISTIC_SQL):
            try:
                rows = conn.execute(sql, (date_iso,)).fetchall()
                if rows:
                    return [dict(r) for r in rows]
                # Query succeeded but returned zero rows: no preds for this date.
                # Don't try the no-logistic fallback unnecessarily.
                break
            except sqlite3.OperationalError:
                # Column or table missing; try the no-logistic variant next.
                continue

        # --- 2. model_prediction_runs (fallback) ---
        try:
            rows = conn.execute(
                """SELECT race_id,
                          race_no,
                          track,
                          horse_name,
                          horse_id,
                          predicted_rank,
                          ensemble_prob,
                          catboost_prob,
                          xgboost_prob,
                          NULL                       AS logistic_prob,
                          'model_prediction_runs'    AS pred_source
                   FROM model_prediction_runs
                   WHERE date(race_start_at, '+3 hours') = ?
                   ORDER BY race_no, predicted_rank""",
                (date_iso,),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            pass

    except Exception as exc:
        logger.warning("get_predictions_for_date failed: %s", exc)
    finally:
        if conn:
            conn.close()

    return []


# ---------------------------------------------------------------------------
# Comparison: build, enrich, and persist
# ---------------------------------------------------------------------------


def build_and_persist_comparisons(
    db_path: str,
    city: str,
    races: list[dict[str, Any]],
    target_date: date,
    predictions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Match TJK results against model predictions and persist to SQLite.

    For each race:

    1. Build a ``{horse_name: prediction}`` lookup filtered to this
       city + race_no (matching city via track normalisation).
    2. For each horse: try exact name match first, then rapidfuzz
       (score_cutoff=85).
    3. Identify actual winner (finish_pos == 1).
    4. ``INSERT OR REPLACE`` into ``tjk_prediction_comparisons``.
    5. ``INSERT OR REPLACE`` into ``tjk_race_summary``.

    Returns::

        {
          "races": [
            {"race_no": int, "top1": bool, "top3": bool,
             "matched": int, "total": int},
            ...
          ]
        }
    """
    _ensure_schema(db_path)
    date_iso = target_date.isoformat()
    city_upper = city.upper()
    race_summaries: list[dict[str, Any]] = []

    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        with conn:
            for race in races:
                race_no = race["race_no"]
                race_time = race.get("race_time", "")
                horses = race.get("horses", [])

                # Filter predictions that belong to this city + race number.
                race_preds: list[dict[str, Any]] = []
                for p in predictions:
                    track = p.get("track", "")
                    track_first = _fold(track).split()[0] if track else ""
                    pred_city = TRACK_TO_CITY.get(track_first) or normalize_city(track)
                    p_rno_raw = p.get("race_no")
                    try:
                        p_rno = int(p_rno_raw) if p_rno_raw is not None else 0
                    except (TypeError, ValueError):
                        p_rno = 0
                    if pred_city.upper() == city_upper and p_rno == race_no:
                        race_preds.append(p)

                # Build normalised name → prediction lookup.
                pred_map: dict[str, dict[str, Any]] = {
                    normalize_horse_name(p["horse_name"]): p for p in race_preds
                }

                # Identify actual winner for this race.
                actual_winner: str | None = next(
                    (h["horse_name"] for h in horses if h.get("finish_pos") == 1),
                    None,
                )

                matched = 0
                top1 = False
                top3 = False

                for horse in horses:
                    h_name = horse["horse_name"]
                    actual_rank = horse.get("finish_pos")

                    # Match: exact first, fuzzy second.
                    pred = pred_map.get(h_name)
                    match_score: float | None = 1.0 if pred is not None else None
                    if pred is None:
                        pred, match_score = _fuzzy_lookup_scored(h_name, pred_map)

                    predicted_rank = pred.get("predicted_rank") if pred else None
                    is_top1 = int(actual_rank == 1 and predicted_rank == 1)
                    is_top3 = int(actual_rank == 1 and (predicted_rank or 99) <= 3)

                    if pred:
                        matched += 1
                    if actual_rank == 1:
                        if predicted_rank == 1:
                            top1 = True
                        if (predicted_rank or 99) <= 3:
                            top3 = True

                    conn.execute(
                        """INSERT OR REPLACE INTO tjk_prediction_comparisons
                               (race_date, city, race_no, race_time,
                                horse_name, horse_no,
                                actual_rank, predicted_rank,
                                ensemble_prob, catboost_prob,
                                xgboost_prob, logistic_prob,
                                is_top1, is_top3,
                                actual_winner, match_score, pred_source)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            date_iso,
                            city,
                            race_no,
                            race_time,
                            h_name,
                            horse.get("start_no"),
                            actual_rank,
                            predicted_rank,
                            pred.get("ensemble_prob") if pred else None,
                            pred.get("catboost_prob") if pred else None,
                            pred.get("xgboost_prob") if pred else None,
                            pred.get("logistic_prob") if pred else None,
                            is_top1,
                            is_top3,
                            actual_winner,
                            match_score,
                            pred.get("pred_source") if pred else None,
                        ),
                    )

                # Derive winner's prediction for the summary row.
                winner_pred: dict[str, Any] | None = None
                if actual_winner:
                    winner_pred = pred_map.get(actual_winner)
                    if winner_pred is None:
                        winner_pred, _ = _fuzzy_lookup_scored(actual_winner, pred_map)

                result_count = sum(1 for h in horses if h.get("finish_pos") is not None)

                conn.execute(
                    """INSERT OR REPLACE INTO tjk_race_summary
                           (race_date, city, race_no, race_time,
                            total_horses, result_count, matched_preds,
                            top1_correct, top3_correct,
                            winner_name, winner_prob, winner_pred_rank,
                            last_updated)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                               strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))""",
                    (
                        date_iso,
                        city,
                        race_no,
                        race_time,
                        len(horses),
                        result_count,
                        matched,
                        int(top1),
                        int(top3),
                        actual_winner,
                        float(winner_pred.get("ensemble_prob") or 0)
                        if winner_pred
                        else None,
                        winner_pred.get("predicted_rank") if winner_pred else None,
                    ),
                )

                race_summaries.append(
                    {
                        "race_no": race_no,
                        "top1": top1,
                        "top3": top3,
                        "matched": matched,
                        "total": len(horses),
                    }
                )
    finally:
        conn.close()

    logger.debug(
        "build_and_persist_comparisons: city=%s races=%d", city, len(race_summaries)
    )
    return {"races": race_summaries}


# ---------------------------------------------------------------------------
# Cache read
# ---------------------------------------------------------------------------


def get_comparisons_from_db(
    db_path: str,
    target_date: date,
    max_age_minutes: int = 15,
) -> dict[str, Any] | None:
    """Return cached comparison data from SQLite if it is still fresh.

    A result is considered fresh when *all* ``tjk_race_summary`` rows for
    *target_date* have ``last_updated > now − max_age_minutes``.

    Returns a result dict with ``"from_cache": True``, or ``None`` if the
    data is missing or stale (caller should re-scrape).

    Return format::

        {
          "date":       "2026-07-03",
          "from_cache": True,
          "cities": [
            {
              "city": "İstanbul",
              "races": [
                {
                  "race_no": 1,
                  "race_time": "17.15",
                  "top1_correct": False,
                  "top3_correct": True,
                  "result_available": True,
                  "horses": [<tjk_prediction_comparisons row dicts>]
                }, ...
              ]
            }, ...
          ],
          "summary": {
            "total_races": 9,
            "top1_hits": 2, "top3_hits": 5,
            "top1_rate": 0.222, "top3_rate": 0.556
          }
        }
    """
    _ensure_schema(db_path)
    date_iso = target_date.isoformat()
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        conn.row_factory = sqlite3.Row

        summaries = conn.execute(
            "SELECT * FROM tjk_race_summary WHERE race_date=? ORDER BY city, race_no",
            (date_iso,),
        ).fetchall()

        if not summaries:
            return None

        # Freshness check: every summary row must be recent enough.
        cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)
        for row in summaries:
            ts_str = row["last_updated"] or ""
            try:
                ts = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ")
                if ts < cutoff:
                    return None
            except ValueError:
                return None  # unparseable timestamp → treat as stale

        comparisons = conn.execute(
            """SELECT * FROM tjk_prediction_comparisons
               WHERE race_date=?
               ORDER BY city, race_no, actual_rank""",
            (date_iso,),
        ).fetchall()
    except Exception as exc:
        logger.warning("get_comparisons_from_db failed: %s", exc)
        return None
    finally:
        if conn:
            conn.close()

    # Assemble: city → race_no → race dict
    cities_dict: dict[str, dict[int, dict[str, Any]]] = {}
    for comp in comparisons:
        city_name = comp["city"]
        race_no = comp["race_no"]
        if city_name not in cities_dict:
            cities_dict[city_name] = {}
        if race_no not in cities_dict[city_name]:
            cities_dict[city_name][race_no] = {
                "race_no": race_no,
                "race_time": comp["race_time"],
                "top1_correct": False,
                "top3_correct": False,
                "result_available": False,
                "horses": [],
            }
        cities_dict[city_name][race_no]["horses"].append(dict(comp))

    # Merge per-race summary flags.
    for row in summaries:
        city_name = row["city"]
        race_no = row["race_no"]
        if city_name in cities_dict and race_no in cities_dict[city_name]:
            cities_dict[city_name][race_no]["top1_correct"] = bool(row["top1_correct"])
            cities_dict[city_name][race_no]["top3_correct"] = bool(row["top3_correct"])
            cities_dict[city_name][race_no]["result_available"] = (
                row["result_count"] or 0
            ) > 0

    total_races = top1_hits = top3_hits = 0
    cities_list: list[dict[str, Any]] = []

    for city_name in sorted(cities_dict):
        races_list = sorted(cities_dict[city_name].values(), key=lambda r: r["race_no"])
        for race in races_list:
            if race.get("result_available"):
                total_races += 1
                if race["top1_correct"]:
                    top1_hits += 1
                if race["top3_correct"]:
                    top3_hits += 1
        cities_list.append({"city": city_name, "races": races_list})

    return {
        "date": date_iso,
        "from_cache": True,
        "cities": cities_list,
        "summary": {
            "total_races": total_races,
            "top1_hits": top1_hits,
            "top3_hits": top3_hits,
            "top1_rate": round(top1_hits / total_races, 3) if total_races else 0.0,
            "top3_rate": round(top3_hits / total_races, 3) if total_races else 0.0,
        },
    }


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def compare_predictions_with_tjk(
    db_path: str,
    target_date: date | None = None,
    cities: list[str] | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Fetch TJK results, persist to SQLite, and compare with model predictions.

    Flow:

    1. Unless *force_refresh*, try :func:`get_comparisons_from_db` → return if fresh.
    2. Determine cities from DB program entries; fall back to all
       :data:`TURKISH_CITIES`.
    3. Load predictions for *target_date* from DB via
       :func:`get_predictions_for_date`.
    4. For each city: fetch TJK HTML → :func:`persist_results` →
       :func:`build_and_persist_comparisons`.
    5. Re-read the freshly written data from DB and return it.

    Never raises — errors are logged as warnings and the result will show
    empty cities / zero summary counts.

    Always includes ``"fetched_at"`` in the returned dict.
    """
    if target_date is None:
        target_date = date.today()

    # 1. Fast path from cache.
    if not force_refresh:
        cached = get_comparisons_from_db(db_path, target_date)
        if cached:
            logger.debug("Serving comparison from cache: %s", target_date.isoformat())
            return cached

    # 2. Which cities ran today?
    if not cities:
        cities = _get_today_cities_from_db(db_path, target_date)
    if not cities:
        cities = list(TURKISH_CITIES)

    # 3. Pull model predictions once for the whole date.
    predictions = get_predictions_for_date(db_path, target_date)
    if not predictions:
        logger.info(
            "No predictions found in DB for %s; TJK results will still be scraped.",
            target_date.isoformat(),
        )

    # 4. Per-city: scrape → persist results → build comparisons.
    for city in cities:
        try:
            city_data = fetch_tjk_results(target_date, city)
            if not city_data.get("races"):
                if city_data.get("error"):
                    logger.warning(
                        "TJK fetch error city=%s: %s", city, city_data["error"]
                    )
                # Empty page = no races in this city today; skip silently.
                continue

            persist_results(db_path, city_data)
            build_and_persist_comparisons(
                db_path, city, city_data["races"], target_date, predictions
            )
        except Exception as exc:
            logger.warning(
                "Unexpected error processing city=%s: %s", city, exc, exc_info=True
            )

    # 5. Read final result from DB (generous window since we just wrote it).
    result = get_comparisons_from_db(db_path, target_date, max_age_minutes=60)
    if result is None:
        result = {
            "date": target_date.isoformat(),
            "from_cache": False,
            "cities": [],
            "summary": {
                "total_races": 0,
                "top1_hits": 0,
                "top3_hits": 0,
                "top1_rate": 0.0,
                "top3_rate": 0.0,
            },
        }

    result["fetched_at"] = datetime.utcnow().isoformat() + "Z"
    result["from_cache"] = False
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_today_cities_from_db(db_path: str, target_date: date) -> list[str]:
    """Return canonical city names present in program entries for *target_date*."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT DISTINCT city_name FROM race_program_entries WHERE program_date=?",
            (target_date.isoformat(),),
        ).fetchall()
        conn.close()
    except Exception as exc:
        logger.warning("DB city lookup failed: %s", exc)
        return []

    cities: list[str] = []
    for row in rows:
        city_name = row["city_name"] or ""
        if not city_name:
            continue
        folded_first = _fold(city_name).split()[0]
        canonical = TRACK_TO_CITY.get(folded_first)
        if canonical and canonical not in cities:
            cities.append(canonical)
    return cities


def _fuzzy_lookup_scored(
    name: str,
    pred_map: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, float | None]:
    """Return ``(prediction_dict, normalised_score)`` via rapidfuzz (score_cutoff=85).

    *normalised_score* is in [0, 1].  Returns ``(None, None)`` when rapidfuzz
    is unavailable or no candidate meets the cutoff.
    """
    if not pred_map:
        return None, None
    try:
        from rapidfuzz import fuzz, process

        match = process.extractOne(
            name, list(pred_map.keys()), scorer=fuzz.ratio, score_cutoff=85
        )
        if match:
            # process.extractOne returns (key, score, index)
            return pred_map[match[0]], match[1] / 100.0
    except ImportError:
        pass
    return None, None


def _fuzzy_lookup(
    name: str, pred_map: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    """Convenience wrapper: return only the prediction dict (score discarded)."""
    pred, _ = _fuzzy_lookup_scored(name, pred_map)
    return pred


# ---------------------------------------------------------------------------
# Backward-compatible public aliases (used by other modules)
# ---------------------------------------------------------------------------


def get_today_cities_from_db(db_path: str, target_date: date) -> list[str]:
    """Public alias for :func:`_get_today_cities_from_db`."""
    return _get_today_cities_from_db(db_path, target_date)


def get_predictions_from_db(db_path: str, target_date: date) -> list[dict[str, Any]]:
    """Backward-compatible alias for :func:`get_predictions_for_date`."""
    return get_predictions_for_date(db_path, target_date)
