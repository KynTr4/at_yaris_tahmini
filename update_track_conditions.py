"""Download today's weather and track conditions from TJK daily program."""
import os
import re
import sys
import json
import logging
import requests
from bs4 import BeautifulSoup
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
logger = logging.getLogger("update_track_conditions")

FAILED_UPDATES_CSV = "failed_updates.csv"

def log_failure(entity, error_type, message):
    """Write failure record to failed_updates.csv."""
    row = pd.DataFrame([{
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "script": "update_track_conditions.py",
        "entity": str(entity),
        "error_type": str(error_type),
        "error_message": str(message)
    }])
    file_exists = os.path.exists(FAILED_UPDATES_CSV)
    row.to_csv(FAILED_UPDATES_CSV, mode="a", index=False, header=not file_exists, encoding="utf-8")

def parse_tjk_track_page(html_content):
    """Parse weather and track conditions from TJK HTML."""
    soup = BeautifulSoup(html_content, "html.parser")
    text = soup.get_text()
    
    # 1. Parse weather details
    weather_match = re.search(r'Hava:\s*([^\n\r|]+)', text)
    weather_str = weather_match.group(1).strip() if weather_match else "not_available_in_tjk_checked"
    
    temp = "not_available_in_tjk_checked"
    humidity = "not_available_in_tjk_checked"
    weather_desc = "not_available_in_tjk_checked"
    
    if weather_str != "not_available_in_tjk_checked":
        parts = weather_str.split(",")
        for p in parts:
            if "C" in p or "°" in p:
                temp = p.replace("C", "").replace("°", "").strip()
            elif "Nem" in p:
                humidity = p.replace("Nem", "").replace("%", "").strip()
            else:
                weather_desc = p.strip()
                
    # 2. Parse track conditions
    dirt_match = re.search(r'Kum:\s*([^\n\r|]+)', text)
    dirt_cond = dirt_match.group(1).strip() if dirt_match else "not_available_in_tjk_checked"
    
    turf_match = re.search(r'Çim:\s*([^\n\r|]+)', text)
    turf_cond = turf_match.group(1).strip() if turf_match else "not_available_in_tjk_checked"
    
    synthetic_match = re.search(r'Sentetik:\s*([^\n\r|]+)', text)
    synthetic_cond = synthetic_match.group(1).strip() if synthetic_match else "not_available_in_tjk_checked"
    
    # Overall condition fallback
    track_cond = "Normal"
    if dirt_cond != "not_available_in_tjk_checked" and dirt_cond != "Normal":
        track_cond = dirt_cond
    elif turf_cond != "not_available_in_tjk_checked" and turf_cond != "Normal":
        track_cond = turf_cond
    elif synthetic_cond != "not_available_in_tjk_checked" and synthetic_cond != "Normal":
        track_cond = synthetic_cond
        
    return {
        "track_condition": track_cond,
        "turf_condition": turf_cond,
        "dirt_condition": dirt_cond,
        "synthetic_condition": synthetic_cond,
        "weather": weather_desc,
        "temperature": temp,
        "humidity": humidity,
        "pressure": "not_available_in_tjk_checked",
        "wind_speed": "not_available_in_tjk_checked",
        "wind_direction": "not_available_in_tjk_checked"
    }

def main():
    logger.info("Starting update_track_conditions.py...")
    db_path = str(DB_PATH)
    init_db(db_path)
    
    today_str = date.today().isoformat()
    today_dot = date.today().strftime("%d/%m/%Y")
    
    # 1. Query active tracks and city IDs for today
    with connect(db_path) as db:
        cities = db.execute(
            "SELECT DISTINCT city_id, city_name FROM race_program_entries WHERE program_date = ?",
            (today_str,)
        ).fetchall()
        
    if not cities:
        logger.info("No active race program found for today. Cannot download track conditions.")
        return
        
    logger.info(f"Active tracks for today: {[c[1] for c in cities]}")
    
    # 2. Load existing track_conditions.csv to prevent duplicates
    csv_path = "output/track_conditions.csv"
    existing_keys = set()
    if os.path.exists(csv_path):
        try:
            df_existing = pd.read_csv(csv_path)
            existing_keys = set(zip(
                df_existing['race_date'].astype(str),
                df_existing['track'].astype(str)
            ))
        except Exception as e:
            logger.warning(f"Could not load existing track conditions: {e}")
            
    # 3. Fetch from TJK and parse
    new_rows = []
    
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    session.headers.update(headers)
    
    # Visit homepage to set initial cookies
    try:
        session.get("https://www.tjk.org/TR/yarissever/anasayfa", timeout=15)
    except Exception as e:
        logger.warning(f"Could not initialize session cookies: {e}")
        
    for city_id, city_name in cities:
        key = (today_str, city_name)
        if key in existing_keys:
            logger.info(f"Track condition for {today_str} at {city_name} already exists. Skipping.")
            continue
            
        url = f"https://www.tjk.org/TR/yarissever/Info/Sehir/GunlukYarisProgrami?SehirId={city_id}&QueryParameter_Tarih={today_dot}&SehirAdi={city_name}&Era=past"
        logger.info(f"Fetching track conditions for {city_name} from: {url}")
        
        # Scraper loop with fallback
        try:
            r = session.get(url, timeout=20)
            if r.status_code == 200 and len(r.content) > 5000:
                parsed_data = parse_tjk_track_page(r.text)
                match_confidence = 1.0
                logger.info(f"Successfully parsed track conditions for {city_name}.")
            else:
                logger.warning(f"Empty page or HTTP {r.status_code} for {city_name}. Using placeholders.")
                raise Exception(f"Empty page or status code: {r.status_code}")
        except Exception as e:
            logger.error(f"Network error or parse failure for {city_name}: {e}")
            log_failure(f"{today_str}_{city_name}", type(e).__name__, str(e))
            # Fallback placeholder row
            parsed_data = {
                "track_condition": "not_available_in_tjk_checked",
                "turf_condition": "not_available_in_tjk_checked",
                "dirt_condition": "not_available_in_tjk_checked",
                "synthetic_condition": "not_available_in_tjk_checked",
                "weather": "not_available_in_tjk_checked",
                "temperature": "not_available_in_tjk_checked",
                "humidity": "not_available_in_tjk_checked",
                "pressure": "not_available_in_tjk_checked",
                "wind_speed": "not_available_in_tjk_checked",
                "wind_direction": "not_available_in_tjk_checked"
            }
            match_confidence = 0.0
            
        new_rows.append({
            "race_date": today_str,
            "track": city_name,
            **parsed_data,
            "match_confidence": match_confidence
        })
        
    # 4. Save to track_conditions.csv
    if new_rows:
        df_new = pd.DataFrame(new_rows)
        # Ensure column order matches exactly
        cols_order = [
            'race_date', 'track', 'track_condition', 'turf_condition', 'dirt_condition', 
            'synthetic_condition', 'weather', 'temperature', 'humidity', 'pressure', 
            'wind_speed', 'wind_direction', 'match_confidence'
        ]
        df_new = df_new[cols_order]
        
        file_exists = os.path.exists(csv_path)
        df_new.to_csv(csv_path, mode="a", index=False, header=not file_exists, encoding="utf-8")
        logger.info(f"Appended {len(df_new)} track condition records to {csv_path}")
    else:
        logger.info("No new track conditions to append.")

if __name__ == "__main__":
    main()
