"""Build certified pre-race features from immutable snapshots only.

This module has a leakage-safe fallback to the legacy horse_races table.
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
import re
from pathlib import Path

import numpy as np
import pandas as pd

from app_config import DB_PATH, OUTPUT_DIR, PROJECT_ROOT
from feature_contract import MODEL_FEATURES, POST_RACE_COLUMNS, validate_model_feature_contract
from migrate_provenance_schema import apply_migrations

ROOT = PROJECT_ROOT
DB = DB_PATH
CSV = OUTPUT_DIR / "asof_features.csv"
PARQUET = OUTPUT_DIR / "asof_features.parquet"


def latest_program_asof(connection: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """WITH eligible AS (
               SELECT *, ROW_NUMBER() OVER (
                   PARTITION BY race_id,horse_id
                   ORDER BY captured_at DESC,snapshot_id DESC
               ) AS rn
               FROM program_snapshots
               WHERE julianday(captured_at) < julianday(race_start_at)
           )
           SELECT * FROM eligible WHERE rn=1""",
        connection,
    )


def latest_results(connection: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """WITH ranked AS (
               SELECT *, ROW_NUMBER() OVER (
                   PARTITION BY race_id,horse_id
                   ORDER BY captured_at DESC,result_id DESC
               ) AS rn
               FROM race_results
               WHERE result_status='finished'
           )
           SELECT * FROM ranked WHERE rn=1""",
        connection,
    )


def latest_market_asof(
    targets: pd.DataFrame, values: pd.DataFrame, value_columns: list[str]
) -> pd.DataFrame:
    if targets.empty or values.empty:
        return pd.DataFrame(columns=["race_id", "horse_id", *value_columns])
    joined = targets[["race_id", "horse_id", "race_start_at"]].merge(
        values, on=["race_id", "horse_id"], how="left", suffixes=("", "_market")
    )
    joined["_start"] = pd.to_datetime(joined["race_start_at"], utc=True, errors="coerce")
    joined["_captured"] = pd.to_datetime(joined["captured_at"], utc=True, errors="coerce")
    joined = joined[joined["_captured"] < joined["_start"]]
    if joined.empty:
        return pd.DataFrame(columns=["race_id", "horse_id", *value_columns])
    joined = joined.sort_values("_captured").drop_duplicates(["race_id", "horse_id"], keep="last")
    return joined[["race_id", "horse_id", *value_columns]]


def normalize_track(val):
    if pd.isna(val): return ""
    val = str(val).lower()
    val = re.sub(r'\s*\([^)]*\)', '', val)
    val = val.replace("i", "i").replace("ı", "i").replace("ş", "s").replace("ç", "c").replace("ğ", "g").replace("ö", "o").replace("ü", "u")
    return " ".join(val.split())


def normalize_surface(val):
    if pd.isna(val): return ""
    val = str(val).lower()
    if "kum" in val or "dirt" in val or "k:" in val:
        return "k:"
    elif "çim" in val or "turf" in val or "ç:" in val or "c:" in val:
        return "ç:"
    elif "sentetik" in val or "synthetic" in val or "s:" in val or "tapeta" in val:
        return "s:"
    return val


def normalize_distance(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return np.nan


def normalize_person(val):
    if pd.isna(val): return ""
    val = str(val).lower()
    val = val.replace("i", "i").replace("ı", "i").replace("ş", "s").replace("ç", "c").replace("ğ", "g").replace("ö", "o").replace("ü", "u")
    return "".join(val.split())


def load_horse_races_history(connection: sqlite3.Connection, unique_horse_ids: list[str]) -> pd.DataFrame:
    if not unique_horse_ids:
        return pd.DataFrame(columns=[
            "horse_id", "_start", "carried_weight", "race_class", "distance",
            "surface", "finish_position", "track", "jockey", "trainer", "race_no", "race_id"
        ])
    placeholders = ",".join("?" for _ in unique_horse_ids)
    query = f"SELECT * FROM horse_races WHERE horse_key IN ({placeholders})"
    try:
        df = pd.read_sql_query(query, connection, params=unique_horse_ids)
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        return pd.DataFrame(columns=[
            "horse_id", "_start", "carried_weight", "race_class", "distance",
            "surface", "finish_position", "track", "jockey", "trainer", "race_no", "race_id"
        ])
    
    if df.empty:
        return pd.DataFrame(columns=[
            "horse_id", "_start", "carried_weight", "race_class", "distance",
            "surface", "finish_position", "track", "jockey", "trainer", "race_no", "race_id"
        ])
        
    mapped = pd.DataFrame()
    mapped["horse_id"] = df["horse_key"]
    mapped["_start"] = pd.to_datetime(df["race_date"], format="%d.%m.%Y", errors="coerce", utc=True)
    mapped["carried_weight"] = pd.to_numeric(df["weight"].str.replace(",", ".", regex=False), errors="coerce")
    mapped["race_class"] = df["race_class"]
    mapped["distance"] = pd.to_numeric(df["distance"], errors="coerce")
    mapped["surface"] = df["surface"]
    mapped["finish_position"] = pd.to_numeric(df["finish"], errors="coerce")
    mapped["track"] = df["hippodrome"]
    mapped["jockey"] = df["jockey"]
    mapped["trainer"] = df["trainer"]
    mapped["race_no"] = 1
    mapped["race_id"] = df["race_id"]
    return mapped.dropna(subset=["horse_id", "_start"])


def history_features(target: pd.Series, history: pd.DataFrame) -> dict[str, object]:
    target_start = pd.to_datetime(target["race_start_at"], utc=True)
    past = history[
        history["horse_id"].eq(target["horse_id"])
        & history["_start"].lt(target_start)
    ].sort_values(["_start", "race_no", "race_id"], kind="stable")
    
    if past.empty:
        return {
            "days_since_last_race": np.nan,
            "last_3_avg_position": np.nan,
            "last_5_avg_position": np.nan,
            "last_10_avg_position": np.nan,
            "surface_win_rate": np.nan,
            "distance_win_rate": np.nan,
            "track_win_rate": np.nan,
            "jockey_horse_win_rate": np.nan,
            "trainer_horse_win_rate": np.nan,
            "weight_change": np.nan,
            "class_change": np.nan,
            "distance_change": np.nan,
            "surface_change": np.nan,
        }
        
    last = past.iloc[-1]
    result = {
        "days_since_last_race": (target_start - last["_start"]).total_seconds() / 86400.0,
        "weight_change": target["carried_weight"] - last["carried_weight"] if pd.notna(target["carried_weight"]) and pd.notna(last["carried_weight"]) else np.nan,
        "class_change": int(normalize_track(target["race_class"]) != normalize_track(last["race_class"])) if pd.notna(target["race_class"]) and pd.notna(last["race_class"]) else np.nan,
        "distance_change": target["distance"] - last["distance"] if pd.notna(target["distance"]) and pd.notna(last["distance"]) else np.nan,
        "surface_change": int(normalize_surface(target["surface"]) != normalize_surface(last["surface"])) if pd.notna(target["surface"]) and pd.notna(last["surface"]) else np.nan,
    }
    finishes = pd.to_numeric(past["finish_position"], errors="coerce")
    for window in (3, 5, 10):
        result[f"last_{window}_avg_position"] = finishes.tail(window).mean()
        
    for category, output, norm_fn in [
        ("surface", "surface_win_rate", normalize_surface),
        ("distance", "distance_win_rate", normalize_distance),
        ("track", "track_win_rate", normalize_track),
        ("jockey", "jockey_horse_win_rate", normalize_person),
        ("trainer", "trainer_horse_win_rate", normalize_person),
    ]:
        target_val = norm_fn(target[category])
        if pd.isna(target_val) or target_val == "":
            result[output] = np.nan
            continue
        past_vals = past[category].map(norm_fn)
        selected = past[past_vals == target_val]
        finish = pd.to_numeric(selected["finish_position"], errors="coerce")
        result[output] = finish.eq(1).sum() / len(selected) if len(selected) else np.nan
        
    return result


def build_frame(db_path: str | Path = DB) -> pd.DataFrame:
    validate_model_feature_contract(MODEL_FEATURES)
    apply_migrations(db_path)
    connection = sqlite3.connect(str(db_path), timeout=60)
    try:
        program = latest_program_asof(connection)
        results = latest_results(connection)
        agf = pd.read_sql_query("SELECT * FROM agf_snapshots", connection)
        odds = pd.read_sql_query("SELECT * FROM odds_snapshots", connection)
        
        # Load fallback history from horse_races
        unique_horses = list(program["horse_id"].dropna().unique())
        mapped_hr = load_horse_races_history(connection, unique_horses)
    finally:
        connection.close()
        
    metadata = [
        "race_id", "horse_id", "horse_name", "race_start_at", "race_no",
        "captured_at", "source_endpoint", "source_request_id", "snapshot_id",
    ]
    output_columns = metadata + MODEL_FEATURES + [
        "agf_percent", "agf_rank", "agf_captured_at", "odds", "odds_captured_at"
    ]
    if program.empty:
        return pd.DataFrame(columns=output_columns)

    program["_start"] = pd.to_datetime(program["race_start_at"], utc=True, errors="raise")
    program["_captured"] = pd.to_datetime(program["captured_at"], utc=True, errors="raise")
    if not (program["_captured"] < program["_start"]).all():
        raise AssertionError("Program as-of join admitted captured_at >= race_start_at")
    program["pre_race_handicap_rating"] = pd.to_numeric(
        program["handicap_rating"], errors="coerce"
    )

    if results.empty:
        history_standard = pd.DataFrame(columns=list(program.columns) + ["finish_position"])
    else:
        history_standard = program.merge(
            results[["race_id", "horse_id", "finish_position"]],
            on=["race_id", "horse_id"], how="inner",
        )
        history_standard["_start"] = pd.to_datetime(history_standard["race_start_at"], utc=True, errors="raise")

    metadata_cols = [
        "horse_id", "_start", "carried_weight", "race_class", "distance",
        "surface", "finish_position", "track", "jockey", "trainer", "race_no", "race_id"
    ]
    history_standard_sub = history_standard[metadata_cols] if not history_standard.empty else pd.DataFrame(columns=metadata_cols)
    combined_history = pd.concat([history_standard_sub, mapped_hr], ignore_index=True)
    combined_history = combined_history.drop_duplicates(subset=["horse_id", "race_id"], keep="first")

    derived = pd.DataFrame([history_features(row, combined_history) for _, row in program.iterrows()])
    frame = pd.concat([program.reset_index(drop=True), derived], axis=1)
    agf_latest = latest_market_asof(
        program, agf, ["agf_percent", "agf_rank", "captured_at"]
    ).rename(columns={"captured_at": "agf_captured_at"})
    odds_latest = latest_market_asof(
        program, odds, ["odds", "captured_at"]
    ).rename(columns={"captured_at": "odds_captured_at"})
    frame = frame.merge(agf_latest, on=["race_id", "horse_id"], how="left")
    frame = frame.merge(odds_latest, on=["race_id", "horse_id"], how="left")

    forbidden = sorted(set(MODEL_FEATURES) & POST_RACE_COLUMNS)
    if forbidden:
        raise AssertionError(f"Post-race columns entered model features: {forbidden}")
    return frame[output_columns].sort_values(
        ["race_start_at", "race_no", "race_id", "horse_id"], kind="stable"
    ).reset_index(drop=True)


def write_frame(frame: pd.DataFrame) -> None:
    CSV.parent.mkdir(exist_ok=True)
    frame.to_csv(CSV, index=False, encoding="utf-8")
    frame.to_parquet(PARQUET, index=False)
    csv = pd.read_csv(CSV, low_memory=False)
    parquet = pd.read_parquet(PARQUET)
    if csv.shape != parquet.shape or list(csv.columns) != list(parquet.columns):
        raise AssertionError("As-of CSV/Parquet synchronization failed")


def main() -> int:
    frame = build_frame()
    write_frame(frame)
    subprocess.run([sys.executable, str(ROOT / "run_leakage_ci.py")], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "validate_feature_provenance.py")], cwd=ROOT, check=True)
    print({"rows": len(frame), "races": frame["race_id"].nunique() if len(frame) else 0})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
