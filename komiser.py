import os
import time
import requests
from datetime import date, datetime
from bs4 import BeautifulSoup

# Configuration: Adjust the date range and output folder as needed
START_DATE = date(2026, 1, 1)
END_DATE = date(2026, 6, 22)
OUT_DIR = "komiser_raporlari"

def normalize_turkish(text):
    """
    Normalizes Turkish characters to English ASCII counterparts
    and sanitizes the text for safe file names.
    """
    mapping = {
        'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u',
        'Ç': 'C', 'Ğ': 'G', 'İ': 'I', 'Ö': 'O', 'Ş': 'S', 'Ü': 'U'
    }
    for tr_char, en_char in mapping.items():
        text = text.replace(tr_char, en_char)
    # Remove any invalid filename characters on Windows
    for c in r'<>:"/\|?*':
        text = text.replace(c, "")
    return text.strip().replace(' ', '_')

def download_pdf(url, filepath):
    """
    Downloads a PDF file from a URL and saves it to the given filepath.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 200 and r.headers.get("content-type", "").lower().startswith("application/pdf"):
            with open(filepath, "wb") as f:
                f.write(r.content)
            return True
        else:
            print(f"\n[ERROR] Failed to download {url}. Status: {r.status_code}")
    except Exception as e:
        print(f"\n[ERROR] Exception while downloading {url}: {e}")
    return False

def main():
    global START_DATE, END_DATE, OUT_DIR
    import argparse
    parser = argparse.ArgumentParser(description="TJK Stewards Reports Downloader")
    parser.add_argument("--today", action="store_true", help="Download today's reports only")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
    args = parser.parse_args()
    
    if args.today:
        START_DATE = date.today()
        END_DATE = date.today()
    elif args.start_date and args.end_date:
        try:
            START_DATE = datetime.strptime(args.start_date, "%Y-%m-%d").date()
            END_DATE = datetime.strptime(args.end_date, "%Y-%m-%d").date()
        except ValueError as e:
            print(f"Error parsing dates: {e}")
            return

    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"Starting TJK Stewards Reports Downloader...")
    print(f"Target Range: {START_DATE} to {END_DATE}")
    print(f"Output Directory: {OUT_DIR}\n")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    url = "https://www.tjk.org/TR/YarisSever/Query/DataRows/KomiserRaporlari"
    
    page = 0
    finished = False
    download_count = 0
    skip_count = 0
    
    while not finished:
        print(f"Scanning Page {page}...")
        params = {
            "PageNumber": str(page),
            "Sort": "Tarih DESC",
            "QueryParameter_SehirId": "-1",
            "QueryParameter_Tarih": "",
            "Era": "past"
        }
        
        try:
            r = requests.get(url, params=params, headers=headers, timeout=20)
            if r.status_code != 200:
                print(f"[ERROR] Failed to fetch page {page}. Status: {r.status_code}")
                break
            
            # Parse rows from AJAX response
            soup = BeautifulSoup(r.text, 'html.parser')
            tr_elements = soup.find_all('tr')
            
            if not tr_elements:
                print(f"No records found on page {page}. Pagination complete.")
                break
            
            rows_parsed = 0
            for tr in tr_elements:
                tds = tr.find_all('td')
                if len(tds) >= 3:
                    rows_parsed += 1
                    link_el = tds[0].find('a')
                    if not link_el or 'href' not in link_el.attrs:
                        continue
                        
                    pdf_url = link_el['href']
                    city_raw = tds[1].text.strip()
                    date_str = tds[2].text.strip()
                    
                    # Parse report date
                    try:
                        report_date = datetime.strptime(date_str, "%d.%m.%Y").date()
                    except ValueError:
                        continue
                    
                    # Since data is sorted descending, if we go past START_DATE, we can stop entirely
                    if report_date < START_DATE:
                        finished = True
                        print(f"Found report date {report_date} (< START_DATE {START_DATE}). Stopping search.")
                        break
                    
                    # Skip if newer than END_DATE
                    if report_date > END_DATE:
                        continue
                    
                    # Prepare normalized filename
                    city_clean = normalize_turkish(city_raw)
                    yyyymmdd = report_date.strftime("%Y%m%d")
                    filename = f"{yyyymmdd}_{city_clean}.pdf"
                    filepath = os.path.join(OUT_DIR, filename)
                    
                    # Avoid redownloading
                    if os.path.exists(filepath):
                        skip_count += 1
                        continue
                    
                    print(f" -> Downloading {filename} (Date: {date_str}, City: {city_raw})")
                    if download_pdf(pdf_url, filepath):
                        download_count += 1
                        time.sleep(0.5)  # Politeness interval
            
            if rows_parsed == 0:
                print(f"No valid rows found on page {page}.")
                break
                
            page += 1
            
        except Exception as e:
            print(f"[ERROR] Exception on page {page}: {e}")
            break
            
    print(f"\nProcess Complete!")
    print(f"Downloaded: {download_count} new reports.")
    print(f"Skipped: {skip_count} existing reports.")

if __name__ == "__main__":
    main()