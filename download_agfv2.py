"""
TJK AGFv2 Downloader & Parser
Downloads AGF (Altılı Ganyan Favorileri) data using TJK AGFv2 URL structure:
https://www.tjk.org/AGFv2/{sehir_id}/{ddmmyyyy}/TR/{agf_table_no}/{page_no}
Saves raw HTML, outputs parsed CSV, download logs, and error logs.
Supports stateful resume and rate limits.
"""

import os
import re
import time
import argparse
import hashlib
import requests
import pandas as pd
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from migrate_provenance_schema import apply_migrations
from app_config import DB_PATH, OUTPUT_DIR, PROJECT_ROOT

# Global rate limiting tracker
last_request_time = 0.0

def filter_race_rows(rows, race_nos):
    if not race_nos:
        return rows
    allowed = {int(value) for value in race_nos}
    return [row for row in rows if row.get("race_no") is not None and int(row["race_no"]) in allowed]

def wait_for_rate_limit(rps):
    """Wait to ensure requests-per-second rate limit is respected."""
    global last_request_time
    if rps <= 0:
        return
    delay = 1.0 / rps
    now = time.time()
    elapsed = now - last_request_time
    if elapsed < delay:
        time.sleep(delay - elapsed)
    last_request_time = time.time()

def parse_horse_cell(cell_text):
    """
    Extract horse number and AGF percentage from string (e.g. "7 (%45,74)").
    Returns (horse_no, agf_percent)
    """
    cell_text = cell_text.strip()
    if not cell_text:
        return None, None
    
    # Matches pattern like "7 (%45,74)", "12 (%4,55)", "1 (%0,05)", "12 (%0)"
    m = re.match(r'^(\d+)\s*\(\s*%?\s*([\d,.]+)\s*\)$', cell_text)
    if m:
        try:
            horse_no = int(m.group(1))
            percent_str = m.group(2).replace(',', '.')
            agf_percent = float(percent_str)
            return horse_no, agf_percent
        except ValueError:
            pass
    return None, None

def parse_agfv2_html(html_content, race_date, sehir_id, agf_table_no, page_no, source_url, source_file, http_status, downloaded_at):
    """
    Parse AGFv2 HTML page, resolving rowspans statefully.
    Returns a list of parsed row dictionaries.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    tables = soup.find_all('table')
    
    parsed_rows = []
    
    for table in tables:
        table_id = table.get('id', '')
        if not table_id or not table_id.startswith('GridView'):
            continue
            
        m = re.match(r'^GridView(\d+)$', table_id)
        if not m:
            continue
        leg_no = int(m.group(1))
        
        # Determine race_no based on leg_no
        if agf_table_no == 1:
            race_no = leg_no
        elif agf_table_no == 2:
            race_no = leg_no + 3
        else:
            race_no = None
            
        rows = table.find_all('tr')
        if not rows:
            continue
            
        # Separate headers and data rows
        data_rows = []
        for r in rows:
            tds = r.find_all(['td', 'th'])
            row_texts = [td.get_text(strip=True) for td in tds]
            # Skip header rows containing "AT NO"
            if any('AT NO' in txt for txt in row_texts) or all(txt == '' for txt in row_texts if txt):
                continue
            if not r.find_all('td'):
                continue
            data_rows.append(r)
            
        # Stateful rowspan tracker: [Rank, Horse Info, Group Sum %]
        active_rowspans = [None, None, None]
        
        for row in data_rows:
            tds = row.find_all('td')
            row_cells = [None, None, None]
            
            # Step 1: Carry forward rowspans from previous rows
            for col_idx in range(3):
                if active_rowspans[col_idx] is not None:
                    val, remaining = active_rowspans[col_idx]
                    row_cells[col_idx] = val
                    remaining -= 1
                    if remaining > 0:
                        active_rowspans[col_idx] = (val, remaining)
                    else:
                        active_rowspans[col_idx] = None
            
            # Step 2: Fill cells from current row tds
            for td in tds:
                col_idx = 0
                while col_idx < 3 and row_cells[col_idx] is not None:
                    col_idx += 1
                
                if col_idx >= 3:
                    break
                    
                rowspan = int(td.get('rowspan', 1))
                val = td.get_text(strip=True)
                row_cells[col_idx] = val
                
                if rowspan > 1:
                    active_rowspans[col_idx] = (val, rowspan - 1)
            
            rank_str = row_cells[0]
            horse_cell_text = row_cells[1]
            
            if not horse_cell_text:
                continue
                
            horse_no, agf_percent = parse_horse_cell(horse_cell_text)
            
            # Resolve rank
            if rank_str and rank_str.strip().isdigit():
                agf_rank = int(rank_str.strip())
            else:
                agf_rank = None
                
            parsed_rows.append({
                'race_date': race_date,
                'sehir_id': sehir_id,
                'agf_table_no': agf_table_no,
                'page_no': page_no,
                'race_no': race_no,
                'horse_no': horse_no,
                'horse_name': None,
                'agf_percent': agf_percent,
                'agf_rank': agf_rank,
                'raw_text': horse_cell_text,
                'source_url': source_url,
                'source_file': source_file,
                'http_status': http_status,
                'downloaded_at': downloaded_at
            })
            
    return parsed_rows

def download_url_with_retry(url, rps, max_retries=3):
    """Download a URL with retry logic and exponential backoff."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    retries = 0
    backoff = 2.0
    
    while retries <= max_retries:
        wait_for_rate_limit(rps)
        try:
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code == 429:
                print(f"Received HTTP 429 for {url}. Waiting {backoff}s and retrying...")
                time.sleep(backoff)
                retries += 1
                backoff *= 2
                continue
            return r, None
        except requests.exceptions.RequestException as e:
            print(f"Network error downloading {url}: {e}. Retrying {retries}/{max_retries}...")
            retries += 1
            if retries <= max_retries:
                time.sleep(backoff)
                backoff *= 2
            else:
                return None, e
                
    return None, Exception("Max retries exceeded")

def check_response_status(response):
    """Classify the downloaded response status."""
    if response is None:
        return "network_error", "No response received"
        
    status_code = response.status_code
    
    if status_code == 404:
        return "not_found", "HTTP 404 Not Found"
        
    if not response.content or len(response.content.strip()) == 0:
        return "not_found", "Empty response body"
        
    content_str = response.text
    
    # Check Cloudflare
    if "cf-challenge" in content_str or "cloudflare" in response.headers.get("Server", "").lower() or "Cloudflare" in content_str:
        return "cloudflare_blocked", "Blocked by Cloudflare protection"
        
    # Check generic HTML error pages
    if status_code >= 400:
        soup = BeautifulSoup(response.content, 'html.parser')
        title = soup.title.string.strip() if soup.title else f"HTTP {status_code}"
        return f"http_error_{status_code}", f"HTML error page: {title}"
        
    return "success", ""

def append_to_csv(filepath, df_new):
    """Append a DataFrame to a CSV file, creating it with headers if new."""
    if df_new.empty:
        return
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    file_exists = os.path.exists(filepath)
    df_new.to_csv(filepath, mode='a', index=False, header=not file_exists, encoding='utf-8')

def log_error(race_date, sehir_id, agf_table_no, page_no, url, error_type, error_message):
    """Append an execution error to errors.csv."""
    err_row = pd.DataFrame([{
        'race_date': race_date,
        'sehir_id': sehir_id,
        'agf_table_no': agf_table_no,
        'page_no': page_no,
        'url': url,
        'error_type': error_type,
        'error_message': error_message
    }])
    append_to_csv("data/agfv2_raw/errors.csv", err_row)

def log_download(race_date, sehir_id, agf_table_no, page_no, url, status, byte_size, saved_file, message):
    """Append a download event to download_log.csv."""
    log_row = pd.DataFrame([{
        'race_date': race_date,
        'sehir_id': sehir_id,
        'agf_table_no': agf_table_no,
        'page_no': page_no,
        'url': url,
        'status': status,
        'bytes': byte_size,
        'saved_file': saved_file,
        'message': message
    }])
    append_to_csv("data/agfv2_raw/download_log.csv", log_row)

def append_to_agf_csv(parsed_rows):
    """Map parsed rows to horse names and track names, and append to output/agf_data.csv."""
    if not parsed_rows:
        return
        
    db_path = str(DB_PATH)
    city_map = {1: 'Adana', 2: 'İzmir', 3: 'İstanbul', 4: 'Bursa', 5: 'Ankara', 7: 'Elazığ', 8: 'Diyarbakır', 9: 'Kocaeli', 57: 'Şanlıurfa'}
    
    agf_rows = []
    import sqlite3
    
    try:
        apply_migrations(db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
    except Exception as e:
        print(f"Could not connect to database for AGF mapping: {e}")
        conn = None
        
    for r in parsed_rows:
        race_date = r['race_date']
        sehir_id = int(r['sehir_id'])
        race_no = r['race_no']
        horse_no = r['horse_no']
        agf_percent = r['agf_percent']
        agf_rank = r['agf_rank']
        
        if race_no is None or horse_no is None:
            continue
            
        track = city_map.get(sehir_id, f"Sehir_{sehir_id}")
        horse_name = "not_found"
        match_confidence = 0.0
        
        if conn:
            try:
                # Find matching entry in today's race program by program_number (gate)
                cursor.execute(
                    """SELECT horse_name,city_name,race_tab_id,tjk_id,horse_id
                       FROM race_program_entries
                       WHERE program_date=? AND city_id=?
                         AND CAST(race_no AS INTEGER)=? AND CAST(gate AS INTEGER)=?""",
                    (race_date, sehir_id, int(race_no), int(horse_no))
                )
                res = cursor.fetchone()
                if res:
                    horse_name = res[0]
                    track = res[1]
                    match_confidence = 1.0
                    entity = (
                        f"horse:{int(res[4])}" if res[4]
                        else f"tjk:{res[3]}" if res[3] not in (None, "", "0", 0)
                        else "name:" + hashlib.sha256(str(horse_name).upper().encode()).hexdigest()[:20]
                    )
                    captured = datetime.fromisoformat(str(r.get('downloaded_at')).replace('Z', '+00:00'))
                    if captured.tzinfo is None:
                        captured = captured.replace(tzinfo=ZoneInfo('Europe/Istanbul'))
                    captured_at = captured.astimezone(ZoneInfo('UTC')).isoformat()
                    source_request_id = hashlib.sha256(
                        f"{r.get('source_url')}|{captured_at}|{r.get('source_file')}".encode()
                    ).hexdigest()
                    stable_race_id = f"prog_{race_date}_{sehir_id}_{res[2]}"
                    cursor.execute(
                        """SELECT race_start_at FROM program_snapshots
                           WHERE race_id=? AND horse_id=?
                           ORDER BY captured_at DESC,snapshot_id DESC LIMIT 1""",
                        (stable_race_id, entity),
                    )
                    start_row = cursor.fetchone()
                    if not start_row or datetime.fromisoformat(captured_at) >= datetime.fromisoformat(start_row[0].replace('Z', '+00:00')):
                        continue
                    cursor.execute(
                        """INSERT OR IGNORE INTO agf_snapshots(
                               race_id,horse_id,captured_at,agf_percent,agf_rank,
                               source_request_id,source_endpoint)
                           VALUES(?,?,?,?,?,?,?)""",
                        (stable_race_id, entity, captured_at, agf_percent, agf_rank,
                         source_request_id, 'TJK_AGFv2'),
                    )
            except Exception as e:
                pass
                
        agf_rows.append({
            'race_date': race_date,
            'track': track,
            'horse_name': horse_name,
            'agf_percent': agf_percent if agf_percent is not None else 'not_found',
            'agf_rank': agf_rank if agf_rank is not None else 'not_found',
            'match_confidence': match_confidence
        })
        
    if conn:
        conn.commit()
        conn.close()
        
    if not agf_rows:
        return
        
    df_new = pd.DataFrame(agf_rows)
    agf_csv_path = str(OUTPUT_DIR / "agf_data.csv")
    
    # Idempotent append: check duplicates
    if os.path.exists(agf_csv_path):
        try:
            df_existing = pd.read_csv(agf_csv_path)
            # Remove any rows in df_new that are already present in df_existing
            existing_keys = set(zip(
                df_existing['race_date'].astype(str),
                df_existing['track'].astype(str),
                df_existing['horse_name'].astype(str)
            ))
            df_new['key'] = list(zip(
                df_new['race_date'].astype(str),
                df_new['track'].astype(str),
                df_new['horse_name'].astype(str)
            ))
            df_new = df_new[~df_new['key'].isin(existing_keys)].drop(columns=['key'])
        except Exception as e:
            print(f"Warning: could not filter existing agf_data.csv: {e}")
            
    if not df_new.empty:
        append_to_csv(agf_csv_path, df_new)
        print(f"Appended {len(df_new)} AGF records to {agf_csv_path}")

def main():
    parser = argparse.ArgumentParser(description="TJK AGFv2 Downloader and Parser")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--sehir-ids", type=int, nargs="+", help="City IDs")
    parser.add_argument("--today", action="store_true", help="Download AGF for today's date and cities")
    parser.add_argument("--tables", type=int, nargs="+", choices=[1, 2], default=[1, 2], help="AGF table numbers")
    parser.add_argument("--rps", type=float, default=1.0, help="Requests per second limit")
    parser.add_argument("--force-refresh", action="store_true", help="Fetch a new immutable capture instead of using resume/cache")
    parser.add_argument("--race-nos", type=int, nargs="+", help="Only persist these race numbers")
    args = parser.parse_args()
    
    # Parse dates and determine cities
    sehir_ids = args.sehir_ids
    if args.today:
        start_date_str = datetime.now().strftime("%Y-%m-%d")
        end_date_str = start_date_str
        
        # Query cities from race program entries for today
        db_path = str(DB_PATH)
        if os.path.exists(db_path):
            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT city_id FROM race_program_entries WHERE program_date = ?", (start_date_str,))
                sehir_ids = [r[0] for r in cursor.fetchall() if r[0] is not None]
                conn.close()
                print(f"Queried city IDs for today from race program: {sehir_ids}")
            except Exception as e:
                print(f"Error querying cities from race program: {e}")
                
        if not sehir_ids:
            # Fallback to standard city IDs
            sehir_ids = [1, 2, 3, 4, 5, 7, 8, 9, 57]
            print(f"Using fallback city IDs: {sehir_ids}")
    else:
        if not args.start_date or not args.end_date:
            parser.error("--start-date and --end-date are required unless --today is set")
        start_date_str = args.start_date
        end_date_str = args.end_date
        if not sehir_ids:
            parser.error("--sehir-ids is required unless --today is set")
            
    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    except ValueError as e:
        print(f"Error parsing dates: {e}. Dates must be in YYYY-MM-DD format.")
        return

    # Generate dates list
    date_range = []
    curr = start_date
    while curr <= end_date:
        date_range.append(curr)
        curr += timedelta(days=1)

    # Set up folders
    raw_dir = PROJECT_ROOT / "data" / "agfv2_raw"
    html_dir = raw_dir / "html"
    html_dir.mkdir(parents=True, exist_ok=True)
    
    parsed_csv_path = raw_dir / "agfv2_parsed.csv"
    
    # Load parsed keys for resume mechanism
    parsed_keys = set()
    if parsed_csv_path.exists() and not args.force_refresh:
        try:
            df_existing = pd.read_csv(parsed_csv_path)
            if not df_existing.empty and 'race_date' in df_existing.columns:
                parsed_keys = set(zip(
                    df_existing['race_date'].astype(str),
                    df_existing['sehir_id'].astype(str),
                    df_existing['agf_table_no'].astype(str),
                    df_existing['page_no'].astype(str)
                ))
        except Exception as e:
            print(f"Warning: could not read existing parsed CSV: {e}")

    # Generate task list
    tasks = []
    for r_date in date_range:
        race_date_str = r_date.strftime("%Y-%m-%d")
        ddmmyyyy = r_date.strftime("%d%m%Y")
        yyyymmdd = r_date.strftime("%Y%m%d")
        
        for sehir_id in sehir_ids:
            for agf_table_no in args.tables:
                page_no = 1  # default page
                tasks.append({
                    'race_date_str': race_date_str,
                    'ddmmyyyy': ddmmyyyy,
                    'yyyymmdd': yyyymmdd,
                    'sehir_id': sehir_id,
                    'agf_table_no': agf_table_no,
                    'page_no': page_no
                })
                
    # Run stats
    urls_attempted = 0
    successful_responses = 0
    html_files_saved = 0
    parsed_lines_total = 0
    table1_rows_count = 0
    table2_rows_count = 0
    all_new_parsed_rows = []
    
    print(f"Starting downloader pipeline. Total tasks: {len(tasks)}")
    
    for t in tasks:
        race_date_str = t['race_date_str']
        sehir_id = t['sehir_id']
        agf_table_no = t['agf_table_no']
        page_no = t['page_no']
        
        # Check if already processed and parsed
        key = (str(race_date_str), str(sehir_id), str(agf_table_no), str(page_no))
        if key in parsed_keys and not args.force_refresh:
            continue
            
        url = f"https://www.tjk.org/AGFv2/{sehir_id}/{t['ddmmyyyy']}/TR/{agf_table_no}/{page_no}"
        html_path = html_dir / f"{t['yyyymmdd']}_{sehir_id}_agf{agf_table_no}_page{page_no}.html"
        
        # Check cache (local files)
        if html_path.exists() and not args.force_refresh:
            if html_path.stat().st_size == 0:
                continue
                
            with open(html_path, "r", encoding="utf-8", errors="replace") as f:
                html_content = f.read()
                
            if "404 Not Found" in html_content or not html_content.strip():
                continue
                
            try:
                downloaded_at = datetime.fromtimestamp(html_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                parsed_rows = parse_agfv2_html(
                    html_content, 
                    race_date_str, 
                    sehir_id, 
                    agf_table_no, 
                    page_no, 
                    url, 
                    str(html_path), 
                    200, 
                    downloaded_at
                )
                parsed_rows = filter_race_rows(parsed_rows, args.race_nos)
                if parsed_rows:
                    df_parsed = pd.DataFrame(parsed_rows)
                    append_to_csv(str(parsed_csv_path), df_parsed)
                    parsed_keys.add(key)
                    all_new_parsed_rows.extend(parsed_rows)
                    
                    urls_attempted += 1
                    successful_responses += 1
                    html_files_saved += 1
                    for r in parsed_rows:
                        parsed_lines_total += 1
                        if r['agf_table_no'] == 1:
                            table1_rows_count += 1
                        elif r['agf_table_no'] == 2:
                            table2_rows_count += 1
            except Exception as e:
                log_error(race_date_str, sehir_id, agf_table_no, page_no, url, "cache_parse_error", str(e))
                
            continue
            
        # Download from web
        urls_attempted += 1
        response, network_err = download_url_with_retry(url, args.rps)
        downloaded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if network_err:
            log_error(race_date_str, sehir_id, agf_table_no, page_no, url, "network_failure", str(network_err))
            continue
            
        status_type, status_msg = check_response_status(response)
        
        if status_type == "success":
            html_content = response.text
            soup = BeautifulSoup(response.content, 'html.parser')
            has_tables = any(t.get('id', '').startswith('GridView') for t in soup.find_all('table'))
            
            if not has_tables:
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write("")
                log_download(race_date_str, sehir_id, agf_table_no, page_no, url, "not_found", 0, str(html_path), "No GridView tables found in HTML")
                continue
                
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
                
            html_files_saved += 1
            successful_responses += 1
            log_download(race_date_str, sehir_id, agf_table_no, page_no, url, "success", len(response.content), str(html_path), "Download successful")
            
            try:
                parsed_rows = parse_agfv2_html(
                    html_content, 
                    race_date_str, 
                    sehir_id, 
                    agf_table_no, 
                    page_no, 
                    url, 
                    str(html_path), 
                    response.status_code, 
                    downloaded_at
                )
                parsed_rows = filter_race_rows(parsed_rows, args.race_nos)
                if parsed_rows:
                    df_parsed = pd.DataFrame(parsed_rows)
                    append_to_csv(str(parsed_csv_path), df_parsed)
                    parsed_keys.add(key)
                    all_new_parsed_rows.extend(parsed_rows)
                    
                    for r in parsed_rows:
                        parsed_lines_total += 1
                        if r['agf_table_no'] == 1:
                            table1_rows_count += 1
                        elif r['agf_table_no'] == 2:
                            table2_rows_count += 1
            except Exception as e:
                log_error(race_date_str, sehir_id, agf_table_no, page_no, url, "parse_error", str(e))
                
        elif status_type == "not_found":
            with open(html_path, "w", encoding="utf-8") as f:
                f.write("")
            log_download(race_date_str, sehir_id, agf_table_no, page_no, url, "not_found", 0, str(html_path), status_msg)
            
        elif status_type == "cloudflare_blocked":
            log_error(race_date_str, sehir_id, agf_table_no, page_no, url, "cloudflare_blocked", status_msg)
            
        else:
            log_error(race_date_str, sehir_id, agf_table_no, page_no, url, "http_error", status_msg)

    # Print run summary
    print("\n" + "="*40)
    print("RUN STATISTICS:")
    print(f"Urls tried: {urls_attempted}")
    print(f"Successful responses: {successful_responses}")
    print(f"HTML files saved: {html_files_saved}")
    print(f"AGF lines parsed: {parsed_lines_total}")
    print(f"  - Table 1 rows: {table1_rows_count}")
    print(f"  - Table 2 rows: {table2_rows_count}")
    print("="*40)
    
    # Map and append new rows to output/agf_data.csv
    if all_new_parsed_rows:
        append_to_agf_csv(all_new_parsed_rows)
        
    # Print preview of first 20 parsed rows
    if parsed_csv_path.exists():
        try:
            df_final = pd.read_csv(parsed_csv_path)
            print("\nPreview of first 20 parsed lines:")
            print(df_final.head(20).to_string(index=False))
        except Exception as e:
            print(f"Could not load final CSV preview: {e}")

if __name__ == "__main__":
    main()
