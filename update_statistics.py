"""Update horse_statistics table for new or program horses in pedigreeall_progress.db."""
import os
import sys
import json
import logging
import sqlite3
from datetime import date, datetime
import pandas as pd
from pedigreeall_core import connect, init_db, now

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
logger = logging.getLogger("update_statistics")

FAILED_UPDATES_CSV = "failed_updates.csv"

def log_failure(entity, error_type, message):
    """Write failure record to failed_updates.csv."""
    row = pd.DataFrame([{
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "script": "update_statistics.py",
        "entity": str(entity),
        "error_type": str(error_type),
        "error_message": str(message)
    }])
    file_exists = os.path.exists(FAILED_UPDATES_CSV)
    row.to_csv(FAILED_UPDATES_CSV, mode="a", index=False, header=not file_exists, encoding="utf-8")

def stats_groupby(g, col):
    if col not in g.columns:
        return {}
    out = {}
    try:
        # Group and calculate starts, wins, prize_known
        for k, x in g.dropna(subset=[col]).groupby(col):
            # Calculate wins
            wins = 0
            for f_val in x["finish"]:
                try:
                    if int(float(str(f_val).replace(",", ".").strip())) == 1:
                        wins += 1
                except:
                    pass
            prize_known = int(x["prize"].notna().sum())
            out[str(k)] = {
                "starts": len(x),
                "wins": wins,
                "prize_known": prize_known
            }
    except Exception as e:
        logger.warning(f"Error calculating stats groupby for {col}: {e}")
    return out

def process_horse_stats(db_path, horse_key, races_df):
    # Select races for this specific horse
    g = races_df[races_df["horse_key"] == horse_key].copy()
    if g.empty:
        return False
        
    # Map months to seasons
    g["parsed_date"] = pd.to_datetime(g["race_date"], errors="coerce", dayfirst=True)
    m = g["parsed_date"].dt.month
    g["season"] = m.map({
        12: "winter", 1: "winter", 2: "winter",
        3: "spring", 4: "spring", 5: "spring",
        6: "summer", 7: "summer", 8: "summer",
        9: "autumn", 10: "autumn", 11: "autumn"
    })
    
    with connect(db_path) as db:
        # Fetch profile info
        profile = db.execute(
            "SELECT starts, wins, seconds, thirds, fourths, earnings, group_g1, group_g2, group_g3 FROM horse_profiles WHERE horse_key=?",
            (horse_key,)
        ).fetchone()
        
        p = list(profile) if profile else [None]*9
        
        vals = (
            horse_key,
            *p,
            json.dumps(stats_groupby(g, "surface"), ensure_ascii=False),
            json.dumps(stats_groupby(g, "distance"), ensure_ascii=False),
            json.dumps(stats_groupby(g, "season"), ensure_ascii=False),
            json.dumps(stats_groupby(g, "jockey"), ensure_ascii=False),
            json.dumps(stats_groupby(g, "trainer"), ensure_ascii=False),
            now()
        )
        
        db.execute("INSERT OR REPLACE INTO horse_statistics VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", vals)
    return True

def main():
    logger.info("Starting update_statistics.py...")
    db_path = "pedigreeall_progress.db"
    init_db(db_path)
    
    today_str = date.today().isoformat()
    
    # 1. Identify horses that need stats updates:
    #   - Today's program horses
    #   - Horses in horse_races that don't have records in horse_statistics
    with connect(db_path) as db:
        program_horses = [r[0] for r in db.execute(
            "SELECT DISTINCT CASE WHEN horse_id IS NOT NULL THEN 'horse:'||horse_id ELSE 'tjk:'||tjk_id END FROM race_program_entries WHERE program_date=?",
            (today_str,)
        ).fetchall() if r[0] is not None]
        
        missing_horses = [r[0] for r in db.execute(
            "SELECT DISTINCT horse_key FROM horse_races WHERE horse_key NOT IN (SELECT horse_key FROM horse_statistics)"
        ).fetchall() if r[0] is not None]
        
    target_horses = list(set(program_horses + missing_horses))
    logger.info(f"Identified {len(target_horses)} target horses for statistics calculation.")
    
    if not target_horses:
        logger.info("No target horses need statistics updates.")
        return
        
    # 2. Load races for target horses from database to compute stats
    logger.info("Loading race history for target horses...")
    # Load in chunks or query specifically for target horses to save memory
    with sqlite3.connect(db_path) as conn:
        # Construct query with IN clause or load all if target is very large.
        # Since SQL parameter limit is 999 on some platforms, we can process in chunks.
        chunk_size = 500
        races_list = []
        for i in range(0, len(target_horses), chunk_size):
            chunk = target_horses[i:i+chunk_size]
            placeholders = ",".join(["?"] * len(chunk))
            query = f"SELECT horse_key, race_date, surface, distance, jockey, trainer, finish, prize FROM horse_races WHERE horse_key IN ({placeholders})"
            df_chunk = pd.read_sql_query(query, conn, params=chunk)
            races_list.append(df_chunk)
            
        races_df = pd.concat(races_list, ignore_index=True) if races_list else pd.DataFrame()
        
    logger.info(f"Loaded {len(races_df)} historical races. Computing statistics...")
    
    # 3. Calculate and update stats for each target horse
    success_count = 0
    for horse_key in target_horses:
        try:
            if process_horse_stats(db_path, horse_key, races_df):
                success_count += 1
        except Exception as e:
            logger.error(f"Failed to update statistics for {horse_key}: {e}")
            log_failure(horse_key, "StatsCalculationError", str(e))
            
    logger.info(f"Completed update_statistics.py. Successfully updated statistics for {success_count}/{len(target_horses)} horses.")

if __name__ == "__main__":
    main()
