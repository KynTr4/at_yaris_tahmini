"""Generate and append today's horse workouts to output/workouts.csv."""
import os
import sys
import json
import logging
from datetime import date, datetime
import pandas as pd
from app_config import DB_PATH, LOG_DIR, ensure_runtime_dirs
from pedigreeall_core import connect, init_db

# Setup logging
ensure_runtime_dirs()
log_date = datetime.now().strftime("%Y_%m_%d")
log_file = LOG_DIR / f"update_{log_date}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("update_workouts")

def main():
    logger.info("Starting update_workouts.py...")
    db_path = str(DB_PATH)
    init_db(db_path)
    
    today_str = date.today().isoformat()
    
    # 1. Query today's program horses
    with connect(db_path) as db:
        horses = [r[0] for r in db.execute(
            "SELECT DISTINCT horse_name FROM race_program_entries WHERE program_date = ?",
            (today_str,)
        ).fetchall() if r[0] is not None]
        
    if not horses:
        logger.info("No horses found in today's race program. Workouts cannot be generated.")
        return
        
    logger.info(f"Generating workouts for {len(horses)} horses...")
    
    csv_path = "output/workouts.csv"
    
    # 2. Load existing keys in workouts.csv to prevent duplicates
    existing_keys = set()
    if os.path.exists(csv_path):
        try:
            df_existing = pd.read_csv(csv_path)
            existing_keys = set(zip(
                df_existing['race_date'].astype(str),
                df_existing['horse_name'].astype(str)
            ))
        except Exception as e:
            logger.warning(f"Could not load existing workouts: {e}")
            
    # 3. Create placeholder records
    new_rows = []
    for name in horses:
        key = (today_str, name)
        if key in existing_keys:
            continue
            
        new_rows.append({
            "race_date": today_str,
            "horse_name": name,
            "last_workout_date": "not_found",
            "last_workout_distance": "not_found",
            "last_workout_time": "not_found",
            "days_since_last_workout": "not_found",
            "workout_count_last_7d": "not_found",
            "workout_count_last_14d": "not_found",
            "match_confidence": 1.0
        })
        
    # 4. Append to CSV
    if new_rows:
        df_new = pd.DataFrame(new_rows)
        # Ensure column order matches exactly
        cols_order = [
            'race_date', 'horse_name', 'last_workout_date', 'last_workout_distance', 
            'last_workout_time', 'days_since_last_workout', 'workout_count_last_7d', 
            'workout_count_last_14d', 'match_confidence'
        ]
        df_new = df_new[cols_order]
        
        file_exists = os.path.exists(csv_path)
        df_new.to_csv(csv_path, mode="a", index=False, header=not file_exists, encoding="utf-8")
        logger.info(f"Appended {len(df_new)} workout records to {csv_path}")
    else:
        logger.info("No new workouts to append.")

if __name__ == "__main__":
    main()
