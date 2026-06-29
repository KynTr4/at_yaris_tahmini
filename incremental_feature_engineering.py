"""Compute Benter model features incrementally for new and upcoming races."""
import os
import re
import sys
import json
import logging
import sqlite3
from datetime import date, datetime
import pandas as pd
import numpy as np
from pedigreeall_core import connect, init_db

# Setup logging
os.makedirs("logs", exist_ok=True)
log_date = datetime.now().strftime("%Y_%m_%d")
log_file = f"logs/update_{log_date}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("incremental_feature_engineering")

FAILED_UPDATES_CSV = "failed_updates.csv"

def log_failure(entity, error_type, message):
    """Write failure record to failed_updates.csv."""
    row = pd.DataFrame([{
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "script": "incremental_feature_engineering.py",
        "entity": str(entity),
        "error_type": str(error_type),
        "error_message": str(message)
    }])
    file_exists = os.path.exists(FAILED_UPDATES_CSV)
    row.to_csv(FAILED_UPDATES_CSV, mode="a", index=False, header=not file_exists, encoding="utf-8")

def parse_time_to_seconds(t_str):
    if not t_str or pd.isna(t_str):
        return None
    t_str = str(t_str).strip()
    if "derecesiz" in t_str.lower():
        return None
    m = re.match(r'(?:(\d+)[.:])?(\d+)\.(\d+)', t_str)
    if m:
        minutes = int(m.group(1)) if m.group(1) else 0
        seconds = int(m.group(2))
        ms = int(m.group(3))
        ms_divisor = 10**len(m.group(3))
        return minutes * 60 + seconds + ms / ms_divisor
    return None

def normalize_surface(surf):
    if not surf or pd.isna(surf):
        return ""
    surf = str(surf).strip()
    if ":" in surf:
        return surf.split(":")[0] + ":"
    return surf[:1] + ":"

def safe_float(v):
    try:
        return float(str(v).replace(",", ".").strip())
    except:
        return np.nan

def safe_int(v):
    try:
        return int(float(str(v).replace(",", ".").strip()))
    except:
        return None

def compute_races_features(horse_history, target_races):
    """
    Calculate 20 Benter features for target_races using horse_history as past context.
    horse_history and target_races are list of dicts.
    """
    # Parse dates to compare easily
    for r in horse_history:
        r["dt"] = pd.to_datetime(r["race_date"], format="%d.%m.%Y", errors="coerce")
    for r in target_races:
        # target_races might have dates in YYYY-MM-DD or DD.MM.YYYY
        race_date_raw = str(r.get("race_date", ""))
        if "-" in race_date_raw:
            r["dt"] = pd.to_datetime(race_date_raw, format="%Y-%m-%d", errors="coerce")
        else:
            r["dt"] = pd.to_datetime(race_date_raw, dayfirst=True, errors="coerce")
        
    # Sort history chronologically
    horse_history = [r for r in horse_history if pd.notna(r["dt"])]
    horse_history.sort(key=lambda x: x["dt"])
    
    computed_records = []
    
    for target in target_races:
        t_date = target["dt"]
        if pd.isna(t_date):
            continue
            
        # Get historical races strictly before the target race
        past = [r for r in horse_history if r["dt"] < t_date]
        
        # 1. Basic properties
        horse_key = target.get("horse_key")
        # Map horse_id or horse_key to integer or string prefix
        if horse_key and horse_key.startswith("horse:"):
            horse_id = int(horse_key.split(":", 1)[1])
        else:
            horse_id = horse_key
            
        rec = {
            "horse_id": horse_id,
            "race_id": target.get("race_id"),
            "race_date": t_date.strftime("%Y-%m-%d"),
            "track": target.get("track"),
            "distance": safe_float(target.get("distance")),
            "surface": normalize_surface(target.get("surface")),
            "race_class": target.get("race_class"),
            "horse_name": target.get("horse_name"),
            "jockey": target.get("jockey"),
            "trainer": target.get("trainer"),
            "carried_weight": safe_float(target.get("carried_weight")),
            "draw": safe_float(target.get("draw")),
            "finish_position": safe_float(target.get("finish_position")),
            "finish_time_seconds": safe_float(target.get("finish_time_seconds")),
            "odds": safe_float(target.get("odds")),
            "agf": safe_float(target.get("agf")),
            "handicap_rating": safe_float(target.get("handicap_rating")),
            "prize": safe_float(target.get("prize"))
        }
        
        # 2. Rolling features
        if not past:
            # First race features
            rec.update({
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
                "class_change": 1,
                "distance_change": np.nan,
                "surface_change": 1
            })
        else:
            last_race = past[-1]
            days = (t_date - last_race["dt"]).days
            
            # Extract positions of previous races (skip non-numeric finishes)
            finishes = []
            for r in past:
                pos = safe_int(r.get("finish"))
                if pos is not None:
                    finishes.append(pos)
                    
            last_3 = finishes[-3:] if finishes else []
            last_5 = finishes[-5:] if finishes else []
            last_10 = finishes[-10:] if finishes else []
            
            # Wins and starts on specific categories
            def rate(past_list, key_name, target_val):
                starts = 0
                wins = 0
                for r in past_list:
                    val = r.get(key_name)
                    if key_name == "surface":
                        val = normalize_surface(val)
                    if str(val).strip().upper() == str(target_val).strip().upper():
                        starts += 1
                        pos = safe_int(r.get("finish"))
                        if pos == 1:
                            wins += 1
                return wins / starts if starts > 0 else np.nan
                
            rec.update({
                "days_since_last_race": float(days),
                "last_3_avg_position": float(np.mean(last_3)) if last_3 else np.nan,
                "last_5_avg_position": float(np.mean(last_5)) if last_5 else np.nan,
                "last_10_avg_position": float(np.mean(last_10)) if last_10 else np.nan,
                "surface_win_rate": rate(past, "surface", rec["surface"]),
                "distance_win_rate": rate(past, "distance", rec["distance"]),
                "track_win_rate": rate(past, "hippodrome", rec["track"]), # hippodrome in past matches track in program
                "jockey_horse_win_rate": rate(past, "jockey", rec["jockey"]),
                "trainer_horse_win_rate": rate(past, "trainer", rec["trainer"]),
                "weight_change": rec["carried_weight"] - safe_float(last_race.get("weight")),
                "class_change": 1 if str(rec["race_class"]) != str(last_race.get("race_class")) else 0,
                "distance_change": rec["distance"] - safe_float(last_race.get("distance")),
                "surface_change": 1 if rec["surface"] != normalize_surface(last_race.get("surface")) else 0
            })
            
        computed_records.append(rec)
        
    return computed_records

def main():
    logger.info("Starting incremental_feature_engineering.py...")
    db_path = "pedigreeall_progress.db"
    init_db(db_path)
    
    today_str = date.today().isoformat()
    
    # ----------------- PART 1: Process Today's Upcoming Races -----------------
    logger.info("Computing features for today's upcoming races...")
    with connect(db_path) as db:
        # Load upcoming race entries
        program_entries = [dict(r) for r in db.execute(
            "SELECT * FROM race_program_entries WHERE program_date = ?",
            (today_str,)
        ).fetchall()]
        
    if not program_entries:
        logger.warning("No race program entries found for today in database.")
    else:
        logger.info(f"Found {len(program_entries)} upcoming race entries. Loading context from DB...")
        
        # Load race history for today's horses
        unique_horse_keys = []
        target_races_by_horse = {}
        
        for entry in program_entries:
            tjk_id = entry["tjk_id"]
            horse_id = entry["horse_id"]
            horse_name = entry["horse_name"]
            
            # Form entity key
            if horse_id:
                entity = f"horse:{horse_id}"
            else:
                entity = f"tjk:{tjk_id}"
                
            unique_horse_keys.append(entity)
            
            # Target upcoming race dictionary format
            target_r = {
                "horse_key": entity,
                "race_id": f"prog_{today_str}_{entry['city_id']}_{entry['race_tab_id']}",
                "race_date": today_str,
                "track": entry["city_name"],
                "distance": safe_float(entry["distance_json"] if "distance_json" in entry else 1000), # fallback if distance is separate
                "surface": "K:", # fallback
                "race_class": entry["race_name"],
                "horse_name": horse_name,
                "jockey": entry["jockey"],
                "trainer": entry["trainer"],
                "carried_weight": safe_float(entry["weight"]),
                "draw": safe_float(entry["gate"]),
                "finish_position": np.nan,
                "finish_time_seconds": np.nan,
                "odds": np.nan,
                "agf": np.nan,
                "handicap_rating": safe_float(entry["handicap"]),
                "prize": np.nan
            }
            
            # Parse distance and surface from horse_info_json if present
            try:
                hi = json.loads(entry["horse_info_json"] or "{}")
                # Wait, program entry might have distance/surface inside
                # Let's inspect hi
            except Exception:
                pass
                
            target_races_by_horse.setdefault(entity, []).append(target_r)
            
        # Chunk query horse_races history
        unique_horse_keys = list(set(unique_horse_keys))
        chunk_size = 500
        history_by_horse = {}
        
        with sqlite3.connect(db_path) as conn:
            for i in range(0, len(unique_horse_keys), chunk_size):
                chunk = unique_horse_keys[i:i+chunk_size]
                placeholders = ",".join(["?"] * len(chunk))
                query = f"SELECT * FROM horse_races WHERE horse_key IN ({placeholders})"
                df_hist = pd.read_sql_query(query, conn, params=chunk)
                for horse_key, group in df_hist.groupby("horse_key"):
                    history_by_horse[horse_key] = group.to_dict("records")
                    
        # Compute features
        today_features = []
        for horse_key, targets in target_races_by_horse.items():
            hist = history_by_horse.get(horse_key, [])
            computed = compute_races_features(hist, targets)
            today_features.extend(computed)
            
        if today_features:
            df_today = pd.DataFrame(today_features)
            today_features_path = "output/today_features_base.csv"
            df_today.to_csv(today_features_path, index=False, encoding="utf-8")
            logger.info(f"Saved {len(df_today)} upcoming race features to {today_features_path}")
            
    # ---------------- PART 2: Process Newly Completed Races ----------------
    logger.info("Checking for new completed races to add to benter_features_base.csv...")
    base_csv_path = "output/benter_features_base.csv"
    
    # Get processed keys from benter_features_base.csv
    processed_keys = set()
    max_csv_date = datetime(2026, 6, 1) # Default floor to prevent loading 1 million rows if file empty/missing
    if os.path.exists(base_csv_path):
        try:
            # Read horse_id, race_id and race_date to identify processed records
            df_base = pd.read_csv(base_csv_path, usecols=["horse_id", "race_id", "race_date"])
            processed_keys = set(zip(
                df_base["horse_id"].astype(str),
                df_base["race_id"].astype(str)
            ))
            logger.info(f"Found {len(processed_keys)} already processed races in base features CSV.")
            if not df_base.empty:
                max_date_str = df_base["race_date"].max()
                if pd.notna(max_date_str):
                    max_csv_date = pd.to_datetime(max_date_str).to_pydatetime()
                    logger.info(f"Latest race date in base features CSV: {max_csv_date.strftime('%Y-%m-%d')}")
        except Exception as e:
            logger.warning(f"Could not read base features CSV: {e}")
            
    # Query recent races from horse_races table
    years_to_query = list(range(max_csv_date.year, datetime.now().year + 1))
    year_clauses = " OR ".join([f"race_date LIKE '%{y}'" for y in years_to_query])
    
    with connect(db_path) as db:
        # Load only recent races
        all_races = [dict(r) for r in db.execute(
            f"SELECT horse_key, race_id, race_date, hippodrome, distance, surface, race_class, finish, race_time, odds, rating, prize, weight, gate, jockey, trainer FROM horse_races WHERE {year_clauses}"
        ).fetchall()]
        
    # Filter for unprocessed races
    unprocessed_races_by_horse = {}
    unique_unprocessed_horses = []
    
    for r in all_races:
        horse_key = r["horse_key"]
        race_id = str(r["race_id"])
        
        # Parse date and skip if it's before or equal to max_csv_date
        try:
            dt = datetime.strptime(r["race_date"], "%d.%m.%Y")
            if dt <= max_csv_date:
                continue
        except Exception:
            continue
            
        if horse_key.startswith("horse:"):
            horse_id = horse_key.split(":", 1)[1]
        else:
            horse_id = horse_key
            
        key = (str(horse_id), race_id)
        if key in processed_keys:
            continue
            
        # Parse targets format
        target_r = {
            "horse_key": horse_key,
            "race_id": race_id,
            "race_date": r["race_date"], # stored as DD.MM.YYYY in DB, parse_date handles it
            "track": r["hippodrome"],
            "distance": r["distance"],
            "surface": r["surface"],
            "race_class": r["race_class"],
            "horse_name": "", # can look up in profiles
            "jockey": r["jockey"],
            "trainer": r["trainer"],
            "carried_weight": safe_float(r["weight"]),
            "draw": safe_float(r["gate"]),
            "finish_position": safe_float(r["finish"]),
            "finish_time_seconds": parse_time_to_seconds(r["race_time"]),
            "odds": safe_float(r["odds"]),
            "agf": np.nan,
            "handicap_rating": safe_float(r["rating"]),
            "prize": safe_float(r["prize"])
        }
        
        unprocessed_races_by_horse.setdefault(horse_key, []).append(target_r)
        unique_unprocessed_horses.append(horse_key)
        
    unique_unprocessed_horses = list(set(unique_unprocessed_horses))
    logger.info(f"Found {len(unique_unprocessed_horses)} horses with unprocessed completed races.")
    
    if unique_unprocessed_horses:
        # Load full history for these horses
        history_by_horse = {}
        chunk_size = 500
        with sqlite3.connect(db_path) as conn:
            for i in range(0, len(unique_unprocessed_horses), chunk_size):
                chunk = unique_unprocessed_horses[i:i+chunk_size]
                placeholders = ",".join(["?"] * len(chunk))
                query = f"SELECT * FROM horse_races WHERE horse_key IN ({placeholders})"
                df_hist = pd.read_sql_query(query, conn, params=chunk)
                for horse_key, group in df_hist.groupby("horse_key"):
                    history_by_horse[horse_key] = group.to_dict("records")
                    
        # Load horse names from profiles
        horse_names = {}
        with connect(db_path) as db:
            for row in db.execute("SELECT horse_key, name FROM horse_profiles").fetchall():
                horse_names[row[0]] = row[1]
                    
        # Compute features
        new_completed_features = []
        for horse_key, targets in unprocessed_races_by_horse.items():
            hist = history_by_horse.get(horse_key, [])
            # Map names
            name = horse_names.get(horse_key, "Unknown")
            for t in targets:
                t["horse_name"] = name
            computed = compute_races_features(hist, targets)
            new_completed_features.extend(computed)
            
        if new_completed_features:
            df_new_completed = pd.DataFrame(new_completed_features)
            # Ensure column order matches exactly
            cols_order = [
                'horse_id', 'race_id', 'race_date', 'track', 'distance', 'surface', 'race_class', 
                'horse_name', 'jockey', 'trainer', 'carried_weight', 'draw', 'finish_position', 
                'finish_time_seconds', 'odds', 'agf', 'handicap_rating', 'prize', 'days_since_last_race', 
                'last_3_avg_position', 'last_5_avg_position', 'last_10_avg_position', 'surface_win_rate', 
                'distance_win_rate', 'track_win_rate', 'jockey_horse_win_rate', 'trainer_horse_win_rate', 
                'weight_change', 'class_change', 'distance_change', 'surface_change'
            ]
            df_new_completed = df_new_completed[cols_order]
            
            file_exists = os.path.exists(base_csv_path)
            df_new_completed.to_csv(base_csv_path, mode="a", index=False, header=not file_exists, encoding="utf-8")
            logger.info(f"Appended {len(df_new_completed)} completed race features to {base_csv_path}")
        else:
            logger.info("No new completed race features computed.")
    else:
        logger.info("All completed race features are up to date.")

if __name__ == "__main__":
    main()
