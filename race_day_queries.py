"""Read-only race-day program, prediction, result and coverage view."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from results_coverage import build_results_coverage, resolved_tjk_id
from race_scope import track_key


def validate_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("date must be YYYY-MM-DD") from exc
    return value


def race_day_view(connection: sqlite3.Connection, target_date: str, country: str = "ALL") -> dict[str, Any]:
    target_date = validate_date(target_date)
    connection.row_factory = sqlite3.Row
    coverage = build_results_coverage(connection, target_date, country)
    scoped_race_ids = {row["race_id"] for row in coverage["races"]}
    programs = connection.execute(
        """WITH ranked AS (
               SELECT *,ROW_NUMBER() OVER(
                   PARTITION BY race_id,horse_id ORDER BY captured_at DESC,snapshot_id DESC
               ) AS rn FROM program_snapshots
               WHERE date(race_start_at,'+3 hours')=?
           )
           SELECT race_id,horse_id,horse_name FROM ranked WHERE rn=1""",
        (target_date,),
    ).fetchall()
    programs = [row for row in programs if row["race_id"] in scoped_race_ids]
    horse_names = {(row["race_id"], row["horse_id"]): row["horse_name"] or row["horse_id"] for row in programs}
    race_horses: dict[str, set[str]] = {}
    for row in programs:
        race_horses.setdefault(row["race_id"], set()).add(row["horse_id"])

    predictions = connection.execute(
        """WITH ranked AS (
               SELECT p.*,ROW_NUMBER() OVER(
                   PARTITION BY race_id
                   ORDER BY prediction_time DESC,ensemble_probability DESC,horse_id
               ) AS rn
               FROM prediction_snapshots p
               WHERE date(race_start_at,'+3 hours')=?
                 AND julianday(prediction_time)<julianday(race_start_at)
           )
           SELECT prediction_id,race_id,horse_id,prediction_time,
                  ensemble_probability,model_version
           FROM ranked WHERE rn=1""",
        (target_date,),
    ).fetchall()
    prediction_by_race = {row["race_id"]: dict(row) for row in predictions}

    winners = connection.execute(
        """WITH ranked AS (
               SELECT r.*,ROW_NUMBER() OVER(
                   PARTITION BY race_id,horse_id ORDER BY captured_at DESC,result_id DESC
               ) AS rn FROM race_results r
               WHERE date(race_start_at,'+3 hours')=? AND result_status='finished'
           )
           SELECT race_id,horse_id,result_odds FROM ranked
           WHERE rn=1 AND finish_position=1""",
        (target_date,),
    ).fetchall()
    winners_by_race: dict[str, list[dict[str, Any]]] = {}
    for row in winners:
        winners_by_race.setdefault(row["race_id"], []).append(dict(row))

    matched_prediction_ids = {
        row[0] for row in connection.execute(
            """SELECT pr.prediction_id FROM prediction_results pr
               JOIN prediction_snapshots p USING(prediction_id)
               WHERE date(p.race_start_at,'+3 hours')=?""",
            (target_date,),
        )
    }
    lifecycle_by_race = {}
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='race_prediction_lifecycle'"
    ).fetchone():
        lifecycle_by_race = {row["race_id"]: dict(row) for row in connection.execute(
            """SELECT * FROM race_prediction_lifecycle
               WHERE date(race_start_at,'+3 hours')=?""", (target_date,)
        )}

    races = []
    for base in coverage["races"]:
        item = dict(base); race_id = item["race_id"]
        prediction = prediction_by_race.get(race_id)
        race_winners = winners_by_race.get(race_id, [])
        winner_ids = [row["horse_id"] for row in race_winners]
        winner_names = [horse_names.get((race_id, horse_id), horse_id) for horse_id in winner_ids]
        winner_mapped = bool(winner_ids) and all(horse_id in race_horses.get(race_id, set()) for horse_id in winner_ids)
        predicted_horse_id = prediction.get("horse_id") if prediction else None
        correct = bool(prediction and predicted_horse_id in winner_ids) if race_winners else None
        winner_odds = next((row["result_odds"] for row in race_winners if row["horse_id"] == predicted_horse_id), None)
        if correct is True and winner_odds is not None:
            net_return = float(winner_odds) - 1.0
        elif correct is False and race_winners:
            net_return = -1.0
        else:
            net_return = None

        if item["result_fetched"]:
            if not prediction:
                status = "Tahmin yok"
            elif not winner_mapped:
                status = "Eşleşme hatası"
            else:
                status = "Sonuç çekildi"
        elif item["track_policy"] == "unsupported":
            status = "Kaynak desteklenmiyor"
        elif item["missing_reason"] == "TJK_ID_MISSING":
            status = "TJK ID eksik"
        elif not prediction:
            status = "Tahmin yok"
        else:
            status = "Sonuç bekleniyor"

        item.update({
            "date": target_date, "prediction_available": bool(prediction),
            "top1_horse_id": predicted_horse_id,
            "top1_horse": horse_names.get((race_id, predicted_horse_id), predicted_horse_id) if prediction else None,
            "model": "Ensemble" if prediction else None,
            "model_version": prediction.get("model_version") if prediction else None,
            "ensemble_probability": prediction.get("ensemble_probability") if prediction else None,
            "prediction_time": prediction.get("prediction_time") if prediction else None,
            "winner_ids": winner_ids, "actual_winner": ", ".join(winner_names) if winner_names else None,
            "result_status": status, "winner_mapped": winner_mapped,
            "prediction_result_matched": bool(prediction and prediction["prediction_id"] in matched_prediction_ids),
            "evaluatable": bool(prediction and race_winners and winner_mapped and item["track_policy"] != "unsupported"),
            "correct": correct, "decimal_odds": winner_odds, "net_return": net_return,
        })
        lifecycle = lifecycle_by_race.get(race_id, {})
        updated = lifecycle.get("updated_at")
        try:
            next_check = (datetime.fromisoformat(updated.replace("Z", "+00:00")) + timedelta(minutes=5)).isoformat() if updated else None
        except ValueError:
            next_check = None
        item.update({
            "final_agf_at": lifecycle.get("agf_snapshot_done_at"),
            "final_odds_at": lifecycle.get("odds_snapshot_done_at"),
            "final_prediction_at": lifecycle.get("final_prediction_done_at"),
            "freeze_status": lifecycle.get("status") or ("SOURCE_UNSUPPORTED" if item["track_policy"] == "unsupported" else "WAITING"),
            "freeze_warning": lifecycle.get("warning"),
            "prediction_immutable": bool(lifecycle.get("final_prediction_done_at")),
            "next_result_check_at": next_check,
            "final_prediction_due_at": lifecycle.get("final_prediction_due_at"),
            "result_check_status": status,
        })
        races.append(item)

    track_rows = []
    for track in sorted({row["track"] for row in races}):
        selected = [row for row in races if row["track"] == track]
        missing_reasons = sorted({row["missing_reason"] for row in selected if not row["result_fetched"]})
        policy = selected[0]["track_policy"]
        track_rows.append({
            "track": track, "track_policy": policy,
            "program_races": len(selected),
            "prediction_races": sum(row["prediction_available"] for row in selected),
            "result_races": sum(row["result_fetched"] for row in selected),
            "evaluated_races": sum(row["evaluatable"] for row in selected),
            "missing_result_races": sum(not row["result_fetched"] for row in selected),
            "missing_reason": ",".join(missing_reasons) if missing_reasons else "NONE",
            "tjk_id_missing_count": sum(row["tjk_id_missing_horse_count"] for row in selected),
            "unsupported_source_count": sum(
                not row["result_fetched"] and row["track_policy"] == "unsupported" for row in selected
            ),
        })
    status_map = {
        "TJK_ID_MISSING": "TJK ID eksik",
        "SOURCE_UNSUPPORTED": "Desteklenmeyen kaynak",
        "PROVIDER_RESULT_NOT_PUBLISHED": "Sonuç bekleniyor (Yayınlanmadı)",
        "AMBIGUOUS_PROGRAM_MATCH": "Program eşleşme karmaşası",
        "DATA_MISSING": "Veri eksik",
        "API_ERROR": "API hatası",
        "DB_WRITE_ERROR": "Veritabanı yazma hatası",
    }
    warnings = []
    for row in track_rows:
        if row["track_policy"] == "mandatory" and row["missing_result_races"]:
            reasons = []
            for r in row["missing_reason"].split(","):
                if r and r != "RESULT_CAPTURED":
                    reasons.append(status_map.get(r, r))
            reason_str = ", ".join(reasons) if reasons else "Veri eksik"
            warnings.append(
                f"{row['track']} pistinde eksik sonuç var ({row['missing_result_races']} yarış). "
                f"Durum: {reason_str}"
            )
    return {"date": target_date, "tracks": track_rows, "races": races, "warnings": warnings}


def race_day_summary(connection: sqlite3.Connection, target_date: str, country: str = "ALL") -> dict[str, Any]:
    view = race_day_view(connection, target_date, country)
    return {
        "date": target_date, "track_count": len(view["tracks"]),
        "program_races": sum(row["program_races"] for row in view["tracks"]),
        "prediction_races": sum(row["prediction_races"] for row in view["tracks"]),
        "result_races": sum(row["result_races"] for row in view["tracks"]),
        "evaluated_races": sum(row["evaluated_races"] for row in view["tracks"]),
        "missing_result_races": sum(row["missing_result_races"] for row in view["tracks"]),
        "warnings": view["warnings"],
    }


def race_day_performance(connection: sqlite3.Connection, target_date: str, track: str | None = None,
                         country: str = "ALL") -> dict[str, Any]:
    view = race_day_view(connection, target_date, country)
    rows = [row for row in view["races"] if row["evaluatable"] and (not track or track_key(row["track"]) == track_key(track))]
    returns = [float(row["net_return"]) for row in rows if row["net_return"] is not None]
    correct = sum(bool(row["correct"]) for row in rows)
    return {
        "date": target_date, "track": track, "has_data": bool(rows),
        "evaluated_races": len(rows), "correct_races": correct,
        "accuracy_percent": 100.0 * correct / len(rows) if rows else 0.0,
        "roi_percent": 100.0 * sum(returns) / len(returns) if returns else 0.0,
        "net_profit": sum(returns), "races": rows,
    }


def missing_horses(connection: sqlite3.Connection, target_date: str,
                   track: str | None = None) -> list[dict[str, Any]]:
    target_date = validate_date(target_date); connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """WITH ranked AS (
               SELECT *,ROW_NUMBER() OVER(
                   PARTITION BY race_id,horse_id ORDER BY captured_at DESC,snapshot_id DESC
               ) rn FROM program_snapshots WHERE date(race_start_at,'+3 hours')=?
           ) SELECT * FROM ranked WHERE rn=1 ORDER BY race_start_at,race_no,draw,horse_id""",
        (target_date,),
    ).fetchall()
    output = []
    for raw in rows:
        row = dict(raw)
        if track and track_key(row.get("track")) != track_key(track):
            continue
        tjk_id = resolved_tjk_id(connection, str(row["horse_id"]))
        missing = []
        for field in ("horse_name", "draw", "jockey", "trainer", "carried_weight"):
            if row.get(field) in (None, ""):
                missing.append(field)
        if not tjk_id:
            missing.insert(0, "tjk_id")
        if not missing:
            continue
        output.append({
            "date": target_date, "track": row.get("track"), "race_no": row.get("race_no"),
            "race_id": row.get("race_id"), "race_start_at": row.get("race_start_at"),
            "missing_reason": "TJK_ID_MISSING" if not tjk_id else "DATA_MISSING",
            "horse_id": row.get("horse_id"), "horse_name": row.get("horse_name"),
            "draw": row.get("draw"), "jockey": row.get("jockey"), "trainer": row.get("trainer"),
            "tjk_id": tjk_id, "missing_fields": missing,
        })
    return output
