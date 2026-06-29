"""Identify and download missing horse profiles for today's race program."""
import os
import sys
import json
import logging
import asyncio
from datetime import date, datetime
import pandas as pd
from pedigreeall_core import APIClient, connect, init_db, now
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
logger = logging.getLogger("update_profiles")

FAILED_UPDATES_CSV = "failed_updates.csv"
PUBLIC_ONLY_MODE = True

def log_failure(entity, error_type, message):
    """Write failure record to failed_updates.csv."""
    row = pd.DataFrame([{
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "script": "update_profiles.py",
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

async def process_profile(c, entity, tjk_id, horse_id):
    logger.info(f"Downloading profile details for {entity}...")
    jobs = []
    if horse_id:
        jobs.append(fetch_endpoint(c, "GET:HorseInfo/GetById", "HorseInfo/GetById", entity, {"p_iId": horse_id}))
    if tjk_id:
        jobs.append(fetch_endpoint(c, "GET:Tjk/GetHorseFromTjk", "Tjk/GetHorseFromTjk", entity, {"p_iTjkId": tjk_id}))
        
    if jobs:
        await asyncio.gather(*jobs, return_exceptions=True)
        
    try:
        # Run normalization to update horse_profiles table
        normalize_entity(c.db_path, entity, tjk_id, horse_id)
        logger.info(f"Successfully normalized profile for {entity}")
        return "success"
    except Exception as exc:
        logger.error(f"Failed to normalize {entity}: {exc}")
        log_failure(entity, "NormalizationError", str(exc))
        await c.error("normalize", entity, "profiles", exc, 1)
        return "failed"

async def main():
    logger.info("Starting update_profiles.py...")
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
        logger.info("No horses found in today's race program. Maybe update_race_programs.py has not run or there are no races today.")
        return
        
    logger.info(f"Found {len(horses)} unique horses in today's race program. Checking if profiles exist...")
    
    # 2. Filter out horses that already exist in horse_profiles
    missing_horses = []
    with connect(db_path) as db:
        for h in horses:
            tjk_id = h["tjk_id"]
            horse_id = h["horse_id"]
            name = h["horse_name"]
            
            # Form entity key
            if horse_id:
                entity = f"horse:{horse_id}"
            else:
                entity = f"tjk:{tjk_id}"
                
            # Check if profile already exists in DB
            exists = False
            if horse_id:
                res = db.execute("SELECT 1 FROM horse_profiles WHERE horse_id=?", (horse_id,)).fetchone()
                if res: exists = True
            if not exists and tjk_id:
                res = db.execute("SELECT 1 FROM horse_profiles WHERE tjk_id=?", (tjk_id,)).fetchone()
                if res: exists = True
                
            if not exists:
                missing_horses.append((entity, tjk_id, horse_id, name))
                
    logger.info(f"{len(horses) - len(missing_horses)} profiles already exist. {len(missing_horses)} profiles are missing and will be downloaded.")
    
    if not missing_horses:
        logger.info("All profiles are up to date.")
        return
        
    # 3. Download and normalize missing profiles
    c = APIClient(db_path, rps=0.75, concurrency=2)
    success_count = 0
    
    async with c.open():
        for entity, tjk_id, horse_id, name in missing_horses:
            logger.info(f"Processing missing profile for {name} ({entity})")
            status = await process_profile(c, entity, tjk_id, horse_id)
            if status == "success":
                success_count += 1
                
    logger.info(f"Completed update_profiles.py. Downloaded and normalized {success_count}/{len(missing_horses)} profiles.")

if __name__ == "__main__":
    asyncio.run(main())
