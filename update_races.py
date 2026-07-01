"""Download historical races for today's new horses."""
import os
import sys
import json
import logging
import asyncio
from datetime import date, datetime
import pandas as pd
from pedigreeall_core import APIClient, connect, init_db, now, resolve_tjk_id
from normalize_data import normalize_entity

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
logger = logging.getLogger("update_races")

FAILED_UPDATES_CSV = "failed_updates.csv"
PUBLIC_ONLY_MODE = True

def log_failure(entity, error_type, message):
    """Write failure record to failed_updates.csv."""
    row = pd.DataFrame([{
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "script": "update_races.py",
        "entity": str(entity),
        "error_type": str(error_type),
        "error_message": str(message)
    }])
    file_exists = os.path.exists(FAILED_UPDATES_CSV)
    row.to_csv(FAILED_UPDATES_CSV, mode="a", index=False, header=not file_exists, encoding="utf-8")

async def fetch_endpoint(c, key, path, entity, params):
    with connect(c.db_path) as db:
        restricted = db.execute("SELECT 1 FROM access_restrictions WHERE endpoint_key=?", (key,)).fetchone()
    if PUBLIC_ONLY_MODE and restricted:
        return None
    try:
        return await c.request(key, path, params=params, entity_key=entity)
    except Exception as e:
        logger.warning(f"Failed to fetch {key} for {entity}: {e}")
        log_failure(entity, type(e).__name__, f"Endpoint {key} failed: {e}")
        return None

async def process_race_history(c, entity, tjk_id, horse_id):
    logger.info(f"Downloading historical races for {entity} (TJK ID: {tjk_id})...")
    if not tjk_id:
        logger.warning(f"No tjk_id available for {entity}; cannot fetch GET:Tjk/Get")
        return "skipped"
        
    await fetch_endpoint(c, "GET:Tjk/Get", "Tjk/Get", entity, {"p_iTjkId": tjk_id})
    
    try:
        # Run normalization to update horse_races table
        normalize_entity(c.db_path, entity, tjk_id, horse_id)
        logger.info(f"Successfully normalized races for {entity}")
        return "success"
    except Exception as exc:
        logger.error(f"Failed to normalize races for {entity}: {exc}")
        log_failure(entity, "NormalizationError", str(exc))
        await c.error("normalize", entity, "races", exc, 1)
        return "failed"

async def main():
    logger.info("Starting update_races.py...")
    db_path = "pedigreeall_progress.db"
    init_db(db_path)
    
    today_str = date.today().isoformat()
    
    # 1. Find all unique horses in today's race program
    with connect(db_path) as db:
        horses = [dict(r) for r in db.execute(
            "SELECT DISTINCT tjk_id, horse_id, horse_name FROM race_program_entries WHERE program_date=?",
            (today_str,)
        ).fetchall()]
        
    if not horses:
        logger.info("No horses found in today's race program.")
        return
        
    logger.info(f"Found {len(horses)} unique horses in today's race program. Checking race history counts...")
    
    # 2. Check if the horses already have races in horse_races
    new_horses = []
    with connect(db_path) as db:
        for h in horses:
            horse_id = h["horse_id"]
            name = h["horse_name"]
            
            # Use unified resolver
            res = resolve_tjk_id(db, horse_id if horse_id else f"tjk:{h['tjk_id']}", name, today_str)
            tjk_id = res["tjk_id"]
            
            # Form entity key
            if horse_id:
                entity = f"horse:{horse_id}"
            else:
                entity = f"tjk:{tjk_id}" if tjk_id else f"tjk:{h['tjk_id']}"
                
            # Check race count in DB
            race_count = db.execute("SELECT COUNT(*) FROM horse_races WHERE horse_key=?", (entity,)).fetchone()[0]
            
            if race_count == 0:
                new_horses.append((entity, tjk_id, horse_id, name))
                
    logger.info(f"{len(horses) - len(new_horses)} horses already have race history. {len(new_horses)} new horses need race history download.")
    
    if not new_horses:
        logger.info("All race histories are up to date.")
        return
        
    # 3. Download and normalize race history for new horses
    c = APIClient(db_path, rps=0.75, concurrency=2)
    success_count = 0
    
    async with c.open():
        for entity, tjk_id, horse_id, name in new_horses:
            if not tjk_id:
                logger.warning(f"Skipping {name} ({entity}) - no TJK ID.")
                continue
            logger.info(f"Processing missing race history for {name} ({entity})")
            status = await process_race_history(c, entity, tjk_id, horse_id)
            if status == "success":
                success_count += 1
                
    logger.info(f"Completed update_races.py. Downloaded and normalized race history for {success_count}/{len(new_horses)} horses.")

if __name__ == "__main__":
    asyncio.run(main())
