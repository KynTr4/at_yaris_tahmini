import os
import re
import csv
import pandas as pd
from datetime import datetime, timedelta
import pdfplumber
from tqdm import tqdm
from rapidfuzz import fuzz

# Constants
PDF_DIR = "komiser_raporlari"
OUTPUT_DIR = "output"
REPORTS_DIR = "reports"

# Create directories
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

# Helper to normalize Turkish characters and sanitize name strings
def clean_horse_name(name):
    if not name:
        return ""
    mapping = {
        'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u',
        'Ç': 'C', 'Ğ': 'G', 'İ': 'I', 'Ö': 'O', 'Ş': 'S', 'Ü': 'U'
    }
    for tr_char, en_char in mapping.items():
        name = name.replace(tr_char, en_char)
    # Keep only letters and spaces
    name = "".join(c if c.isalpha() or c == " " else "" for c in name)
    return " ".join(name.upper().split()).strip()

def normalize_text(text):
    if not text:
        return ""
    return " ".join(text.split()).strip()

# Track names mappings (ASCII in filename -> Turkish in DB)
TRACK_MAPPING = {
    'sanliurfa': 'Şanlıurfa',
    'istanbul': 'İstanbul',
    'izmir': 'İzmir',
    'elaziğ': 'Elazığ',
    'elazig': 'Elazığ',
    'diyarbakir': 'Diyarbakır',
    'kocaeli': 'Kocaeli',
    'adana': 'Adana',
    'ankara': 'Ankara',
    'antalya': 'Antalya',
    'bursa': 'Bursa'
}

def get_db_track(city_name):
    city_lower = clean_horse_name(city_name).lower()
    return TRACK_MAPPING.get(city_lower, city_name)

def parse_race_numbers_from_merged(table):
    """
    Scans the table for merged text blocks that contain lines starting with 'race_no horse_no'
    returns a dict mapping: (horse_no, horse_name_prefix) -> race_no
    """
    mapping = {}
    for row in table:
        for cell in row:
            if cell and '\n' in cell:
                for line in cell.split('\n'):
                    line = line.strip()
                    m = re.match(r'^(\d+)\s+(\d+)\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)', line)
                    if m:
                        race_no, horse_no, prefix = m.groups()
                        mapping[(horse_no, prefix.upper())] = int(race_no)
    return mapping

def main():
    import argparse
    parser = argparse.ArgumentParser(description="TJK Komiser Reports Parser")
    parser.add_argument("--today", action="store_true", help="Process today's reports only")
    args = parser.parse_args()
    
    events_path = os.path.join(OUTPUT_DIR, "komiser_events.csv")
    processed_pdfs = set()
    if os.path.exists(events_path):
        try:
            df_existing = pd.read_csv(events_path, usecols=["source_pdf"])
            processed_pdfs = set(df_existing["source_pdf"].dropna().unique())
        except Exception as e:
            print(f"Warning: Could not read existing events CSV to skip duplicates: {e}")
            
    # List PDFs
    all_pdf_files = [f for f in os.listdir(PDF_DIR) if f.endswith(".pdf")]
    
    # Filter PDFs
    pdf_files = []
    today_prefix = datetime.now().strftime("%Y%m%d")
    for f in all_pdf_files:
        if f in processed_pdfs:
            continue
        if args.today and not f.startswith(today_prefix):
            continue
        pdf_files.append(f)
        
    print(f"Found {len(all_pdf_files)} total PDF files. Processing {len(pdf_files)} new PDFs.")
    
    if not pdf_files:
        print("No new PDFs to process. Exiting.")
        return

    # 1. Load DB reference names for validation and exact matching
    db_features_path = os.path.join(OUTPUT_DIR, "benter_features_enriched.csv")
    db_races_path = os.path.join(OUTPUT_DIR, "expanded_horse_races.csv")
    
    print("Loading race database reference names...")
    try:
        df_db = pd.read_csv(db_features_path, usecols=["horse_name", "jockey", "trainer"])
        known_horses = set(df_db["horse_name"].dropna().unique())
        known_jockeys = set(df_db["jockey"].dropna().unique())
        known_trainers = set(df_db["trainer"].dropna().unique())
    except Exception as e:
        print(f"Warning: Could not load full race database reference. Using empty sets. Error: {e}")
        known_horses, known_jockeys, known_trainers = set(), set(), set()
        
    print(f"Loaded {len(known_horses)} horses, {len(known_jockeys)} jockeys, {len(known_trainers)} trainers from reference.")
    
    # Pre-compute cleaned forms of reference names for speed
    known_horses_clean = {clean_horse_name(h): h for h in known_horses}
    known_jockeys_clean = {clean_horse_name(j): j for j in known_jockeys}
    known_trainers_clean = {clean_horse_name(t): t for t in known_trainers}
    
    raw_text_records = []
    events_records = []
    
    # QC stats counters
    qc_total_pdfs = len(pdf_files)
    qc_read_pdfs = 0
    qc_ocr_needed = 0
    
    # Parsing loop
    for pdf_filename in tqdm(sorted(pdf_files), desc="Parsing PDFs"):
        pdf_path = os.path.join(PDF_DIR, pdf_filename)
        
        # Extract date and city from filename (e.g. 20260524_Adana.pdf)
        m = re.match(r'^(\d{8})_([A-Za-zÇĞİÖŞÜçğıöşü]+)\.pdf$', pdf_filename)
        if not m:
            continue
        date_raw, city_raw = m.groups()
        report_date_str = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:]}" # YYYY-MM-DD
        city = get_db_track(city_raw)
        
        full_text = ""
        tables_data = []
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                qc_read_pdfs += 1
                for page_idx, page in enumerate(pdf.pages):
                    page_text = page.extract_text() or ""
                    full_text += page_text + "\n"
                    
                    # Extract tables
                    page_tables = page.extract_tables()
                    if page_tables:
                        tables_data.extend(page_tables)
            
            # Check if OCR is needed
            if len(full_text.strip()) < 100:
                qc_ocr_needed += 1
                
        except Exception as e:
            print(f"Error reading PDF {pdf_filename}: {e}")
            continue
            
        # Store raw text
        raw_text_records.append({
            'report_date': report_date_str,
            'city': city,
            'pdf_file': pdf_filename,
            'raw_text': full_text
        })
        
        # Track current race no as we scan paragraphs
        current_race_no = None
        
        # Parse tables (Tabular structure)
        for table in tables_data:
            # 1. Determine table type
            table_text = " ".join([str(c) for r in table for c in r if c]).upper()
            table_type = "UNKNOWN"
            if "JOKEY" in table_text or "KOŞMAYAN" in table_text:
                table_type = "JOCKEY_CHANGE"
            elif "ANTRENÖR" in table_text:
                table_type = "TRAINER_CHANGE"
            elif "ÇIKAN ATLAR" in table_text or "IKAN ATLAR" in table_text or "ÇIKIŞ NEDENİ" in table_text:
                if "JOKEY" in table_text:
                    table_type = "JOCKEY_CHANGE"
                else:
                    table_type = "WITHDRAWN"
            elif "SEYİS" in table_text:
                table_type = "SEYIS_CHANGE"
                
            if table_type == "UNKNOWN" or table_type == "SEYIS_CHANGE":
                continue
                
            # 2. Parse race number mapping from merged cells
            race_mapping = parse_race_numbers_from_merged(table)
            
            # 3. Find column index defaults
            header_row = None
            first_data_row_idx = 0
            
            # Look for row containing headers
            for idx, r in enumerate(table):
                r_str = [str(c).upper() if c else "" for c in r]
                joined = "".join(r_str)
                if any(h in joined for h in ["AT NO", "KOSU NO", "KOŞMAYAN", "DEĞİŞEN"]):
                    header_row = r_str
                    first_data_row_idx = idx + 1
                    break
                    
            # Parse data rows
            for r_idx in range(first_data_row_idx, len(table)):
                row = table[r_idx]
                if not any(row):
                    continue
                # Skip title rows that got merged
                if len([c for c in row if c]) <= 1 and any(h in str(row) for h in ["ATLAR", "DEĞİŞİKLİĞİ", "ANTRENÖR"]):
                    continue
                    
                row_clean = [normalize_text(c) for c in row]
                non_empty = [c for c in row_clean if c]
                if len(non_empty) < 2:
                    continue
                    
                # Setup event base
                event = {
                    'report_date': report_date_str,
                    'city': city,
                    'race_no': '',
                    'horse_name': '',
                    'jockey_change_flag': False,
                    'trainer_change_flag': False,
                    'scratch_flag': False,
                    'injury_flag': False,
                    'lameness_flag': False,
                    'veterinary_flag': False,
                    'steward_incident_flag': False,
                    'equipment_change_flag': False,
                    'incident_type': '',
                    'incident_text': '',
                    'match_confidence': 0.0,
                    'source_pdf': pdf_filename
                }
                
                # Parse depending on table type
                if table_type == "WITHDRAWN":
                    event['scratch_flag'] = True
                    event['incident_type'] = 'scratch'
                    
                    at_no = ""
                    at_adi = ""
                    cikis_nedeni = ""
                    race_no = None
                    
                    # Extract fields
                    for c in row_clean:
                        if c.isdigit() and len(c) <= 2:
                            if not at_no:
                                at_no = c
                            else:
                                if not race_no:
                                    race_no = int(at_no)
                                    at_no = c
                        elif c and not c.isdigit():
                            if not at_adi:
                                at_adi = c
                            else:
                                if not cikis_nedeni:
                                    cikis_nedeni = c
                                else:
                                    cikis_nedeni += " " + c
                                    
                    # Resolve race number from merged headers if index 0 has it
                    if not race_no and header_row and header_row[0] and '\n' in header_row[0]:
                        m_nums = re.findall(r'\d+', header_row[0])
                        if m_nums:
                            race_no = int(m_nums[-1])
                            
                    if not race_no and at_adi:
                        prefix = at_adi.split()[0].upper()
                        race_no = race_mapping.get((at_no, prefix))
                        
                    event['race_no'] = str(race_no) if race_no else ""
                    event['horse_name'] = at_adi
                    event['incident_text'] = f"Çıkış Nedeni: {cikis_nedeni}"
                    
                elif table_type == "JOCKEY_CHANGE":
                    event['jockey_change_flag'] = True
                    event['incident_type'] = 'jockey_change'
                    
                    numerics = [c for c in row_clean if c.isdigit()]
                    texts = [c for c in row_clean if c and not c.isdigit()]
                    
                    race_no = None
                    at_no = ""
                    if len(numerics) >= 2:
                        race_no = int(numerics[0])
                        at_no = numerics[1]
                    elif len(numerics) == 1:
                        at_no = numerics[0]
                        
                    at_adi = texts[0] if len(texts) > 0 else ""
                    kosmayan = texts[1] if len(texts) > 1 else ""
                    cikis_nedeni = texts[2] if len(texts) > 2 else ""
                    degisen = texts[3] if len(texts) > 3 else ""
                    
                    if not race_no and at_adi:
                        prefix = at_adi.split()[0].upper()
                        race_no = race_mapping.get((at_no, prefix))
                        
                    event['race_no'] = str(race_no) if race_no else ""
                    event['horse_name'] = at_adi
                    event['incident_text'] = f"Jokey Değişikliği: Koşmayan Jokey: {kosmayan}, Neden: {cikis_nedeni}, Değişen Jokey: {degisen}"
                    
                elif table_type == "TRAINER_CHANGE":
                    event['trainer_change_flag'] = True
                    event['incident_type'] = 'trainer_change'
                    
                    numerics = [c for c in row_clean if c.isdigit()]
                    texts = [c for c in row_clean if c and not c.isdigit()]
                    
                    race_no = None
                    at_no = ""
                    if len(numerics) >= 2:
                        race_no = int(numerics[0])
                        at_no = numerics[1]
                    elif len(numerics) == 1:
                        at_no = numerics[0]
                        
                    at_adi = texts[0] if len(texts) > 0 else ""
                    old_trainer = texts[1] if len(texts) > 1 else ""
                    cikis_nedeni = texts[2] if len(texts) > 2 else ""
                    new_trainer = texts[3] if len(texts) > 3 else ""
                    
                    if not race_no and at_adi:
                        prefix = at_adi.split()[0].upper()
                        race_no = race_mapping.get((at_no, prefix))
                        
                    event['race_no'] = str(race_no) if race_no else ""
                    event['horse_name'] = at_adi
                    event['incident_text'] = f"Antrenör Değişikliği: Eski: {old_trainer}, Neden: {cikis_nedeni}, Yeni: {new_trainer}"
                    
                # Match horse name
                clean_pdf_name = clean_horse_name(event['horse_name'])
                if clean_pdf_name in known_horses_clean:
                    event['horse_name'] = known_horses_clean[clean_pdf_name]
                    event['match_confidence'] = 1.0
                else:
                    # Fuzzy match
                    best_match = None
                    best_score = 0
                    for db_clean, db_orig in known_horses_clean.items():
                        score = fuzz.ratio(clean_pdf_name, db_clean)
                        if score > best_score:
                            best_score = score
                            best_match = db_orig
                    if best_score >= 95.0:
                        event['horse_name'] = best_match
                        event['match_confidence'] = best_score / 100.0
                    else:
                        event['match_confidence'] = best_score / 100.0 if clean_pdf_name else 0.0
                        
                events_records.append(event)
                
        # Parse paragraphs (Text structure)
        # Split text into paragraphs
        paragraphs = []
        current_p = []
        for line in full_text.split('\n'):
            line_str = line.strip()
            if not line_str:
                if current_p:
                    paragraphs.append(" ".join(current_p))
                    current_p = []
            else:
                if (line.startswith("    ") or line.startswith("\t") or "KOŞU NO:" in line_str or "KOSU NO:" in line_str or "Ek Rapor" in line_str) and current_p:
                    paragraphs.append(" ".join(current_p))
                    current_p = []
                current_p.append(line_str)
        if current_p:
            paragraphs.append(" ".join(current_p))
            
        for paragraph in paragraphs:
            # Check for race number header
            m_race_hdr = re.search(r'(?:KOŞU|KOSU)\s+NO\s*:\s*(\d+)', paragraph, re.IGNORECASE)
            if m_race_hdr:
                current_race_no = int(m_race_hdr.group(1))
                continue
                
            if "isimli at" in paragraph or "numara" in paragraph:
                # 1. Parse horse and race info
                race_no = None
                horse_no = None
                horse_name = ""
                
                # Regex pattern 1
                m = re.search(r'(?:(\d+)\.\s*[Kk]oşuda\s+)?(\d+)\s*numara[a-z\s]*kayıtlı\s+(?:olarak\s+koşan\s+)?([A-ZÇĞİÖŞÜa-zçğıöşü\s\-]+?)\s+isimli\s+at', paragraph)
                if m:
                    r_no, h_no, name = m.groups()
                    if r_no:
                        race_no = int(r_no)
                    horse_no = h_no
                    horse_name = clean_horse_name(name)
                    
                # Regex pattern 2 (fallback)
                if not horse_name:
                    m = re.search(r'[Kk]oşuda\s*(\d+)?\s*numara[da]?\s*kayıtlı\s+(?:olarak\s+koşan\s+)?([A-ZÇĞİÖŞÜa-zçğıöşü\s\-]+?)\s+isimli\s+at', paragraph)
                    if m:
                        h_no, name = m.groups()
                        horse_no = h_no
                        horse_name = clean_horse_name(name)
                        
                if not race_no:
                    race_no = current_race_no
                    
                # Match name with DB
                matched_name = None
                confidence = 0.0
                if horse_name:
                    if horse_name in known_horses_clean:
                        matched_name = known_horses_clean[horse_name]
                        confidence = 1.0
                    else:
                        # Substring match
                        for kh_clean in known_horses_clean.keys():
                            if kh_clean in horse_name or horse_name in kh_clean:
                                matched_name = known_horses_clean[kh_clean]
                                confidence = 0.95
                                break
                        if not matched_name:
                            # Fuzzy match
                            best_match = None
                            best_score = 0
                            for db_clean, db_orig in known_horses_clean.items():
                                score = fuzz.ratio(horse_name, db_clean)
                                if score > best_score:
                                    best_score = score
                                    best_match = db_orig
                            if best_score >= 95.0:
                                matched_name = best_match
                                confidence = best_score / 100.0
                            else:
                                confidence = best_score / 100.0
                                
                if not matched_name:
                    # Semantic database search fallback: find any known horse name inside the paragraph text
                    sorted_known_horses = sorted(known_horses_clean.keys(), key=len, reverse=True)
                    paragraph_clean = clean_horse_name(paragraph)
                    for kh_clean in sorted_known_horses:
                        if len(kh_clean) >= 4 and kh_clean in paragraph_clean:
                            matched_name = known_horses_clean[kh_clean]
                            confidence = 0.95
                            # Find if a horse number appears before this name in the paragraph
                            # E.g. "5 numaralı HİMA" or "5.koşuda HİMA"
                            idx = paragraph_clean.find(kh_clean)
                            window = paragraph_clean[max(0, idx-50):idx]
                            m_num = re.findall(r'\b\d+\b', window)
                            if m_num:
                                horse_no = m_num[-1]
                            break
                            
                final_horse_name = matched_name if matched_name else (horse_name if horse_name else "Bilinmeyen At")
                
                # 2. Extract Event Flags
                jockey_change = any(k in paragraph.upper() for k in ["JOKEY DEĞİŞİKLİĞİ", "APRANTİ DEĞİŞİKLİĞİ"])
                trainer_change = "ANTRENÖR DEĞİŞİKLİĞİ" in paragraph.upper()
                scratch = any(k in paragraph.upper() for k in ["KOŞMAYACAK", "ÇIKARILDI", "YARIŞTAN ÇIKARILDI"])
                
                injury = any(k in paragraph.upper() for k in ["SAKATLIK", "YARA", "SAKATLANARAK"])
                lameness = "TOPALLIK" in paragraph.upper()
                veterinary = any(k in paragraph.upper() for k in ["VETERİNER", "SAĞLIK KONTROLÜ", "HEKİM"])
                
                steward = any(k in paragraph.upper() for k in ["USULSÜZ", "KULVAR DEĞİŞTİRDİ", "FAUL", "ENGELLEME", "DİSİPLİN", "CEZA", "İHTAR", "UYARILDI", "UYARILMIŞTIR"])
                equipment = any(k in paragraph.upper() for k in ["KG", "DB", "KBB", "SK", "KULAKLIK", "DİLBAĞI", "KAPALI GÖZLÜK"])
                
                # Determine event type
                event_type = "steward_incident"
                if scratch: event_type = "scratch"
                elif veterinary or injury or lameness: event_type = "medical"
                elif jockey_change: event_type = "jockey_change"
                elif trainer_change: event_type = "trainer_change"
                elif equipment: event_type = "equipment_change"
                
                medical_reason = ""
                if injury or lameness or veterinary:
                    # Extract a small context of the medical reason
                    for term in ["SAKATLANARAK", "TOPALLIK", "KANAMA", "SAĞLIK KONTROLÜ", "ÖKSÜRÜK", "ATEŞ"]:
                        if term in paragraph.upper():
                            medical_reason = term
                            break
                    if not medical_reason:
                        medical_reason = "VETERİNER KONTROLÜ"
                        
                equipment_type = ""
                if equipment:
                    for term in ["KG", "DB", "KBB", "SK", "KULAKLIK", "DİLBAĞI", "KAPALI GÖZLÜK"]:
                        if term in paragraph.upper():
                            equipment_type = term
                            break
                            
                # Save Paragraph Event
                events_records.append({
                    'report_date': report_date_str,
                    'city': city,
                    'race_no': str(race_no) if race_no else "",
                    'horse_name': final_horse_name,
                    'jockey_change_flag': jockey_change,
                    'trainer_change_flag': trainer_change,
                    'scratch_flag': scratch,
                    'injury_flag': injury,
                    'lameness_flag': lameness,
                    'veterinary_flag': veterinary,
                    'steward_incident_flag': steward,
                    'equipment_change_flag': equipment,
                    'incident_type': event_type,
                    'incident_text': f"Tıbbi Neden: {medical_reason}, Ekipman: {equipment_type}, Rapor: {paragraph}" if (medical_reason or equipment_type) else paragraph,
                    'match_confidence': confidence,
                    'source_pdf': pdf_filename
                })
                
    # 3. Create DataFrame for raw texts and events and combine with existing files
    df_raw_new = pd.DataFrame(raw_text_records)
    raw_path = os.path.join(OUTPUT_DIR, "komiser_raw_text.csv")
    if os.path.exists(raw_path):
        try:
            df_raw_old = pd.read_csv(raw_path)
            df_raw_combined = pd.concat([df_raw_old, df_raw_new], ignore_index=True).drop_duplicates(subset=["pdf_file"])
        except Exception:
            df_raw_combined = df_raw_new
    else:
        df_raw_combined = df_raw_new
    df_raw_combined.to_csv(raw_path, index=False, encoding='utf-8')
    print(f"Saved raw text records. Total: {len(df_raw_combined)} to output/komiser_raw_text.csv")
    
    df_events_new = pd.DataFrame(events_records)
    if os.path.exists(events_path):
        try:
            df_events_old = pd.read_csv(events_path)
            df_events_combined = pd.concat([df_events_old, df_events_new], ignore_index=True)
            # drop duplicates safely
            df_events_combined = df_events_combined.drop_duplicates(subset=["source_pdf", "horse_name", "incident_text"])
        except Exception:
            df_events_combined = df_events_new
    else:
        df_events_combined = df_events_new
    df_events_combined.to_csv(events_path, index=False, encoding='utf-8')
    print(f"Saved structured event records. Total: {len(df_events_combined)} to output/komiser_events.csv")
    
    # Set to combined variables for the matching step below
    df_raw = df_raw_combined
    df_events = df_events_combined
    
    # 4. Matching and Feature Enrichment with Benter Features
    print("Loading enriched features dataset...")
    try:
        df_feat = pd.read_csv(db_features_path)
    except Exception as e:
        print(f"Critical Error: Could not load features dataset {db_features_path}: {e}")
        return
        
    print(f"Original features dataset rows: {len(df_feat)}")
    
    # Load race mapping for K_NO_K_ADI (race_no)
    print("Loading race numbers map from expanded_horse_races...")
    try:
        df_races = pd.read_csv(db_races_path, usecols=["ID", "K_NO_K_ADI"]).rename(columns={"ID": "race_id", "K_NO_K_ADI": "race_no"})
        df_races = df_races.drop_duplicates(subset=["race_id"])
        # Merge race_no into features df
        df_feat = df_feat.merge(df_races, on="race_id", how="left")
    except Exception as e:
        print(f"Warning: Could not merge race numbers: {e}. Matching will fall back to name and date.")
        df_feat['race_no'] = pd.NA
        
    # Pre-clean horse names in DB
    df_feat['horse_name_clean'] = df_feat['horse_name'].apply(clean_horse_name)
    df_events['horse_name_clean'] = df_events['horse_name'].apply(clean_horse_name)
    
    # Track matching statistics
    unmatched_events = []
    matched_indices = set()
    
    # Initialize features to 0
    new_cols = [
        'had_jockey_change', 'had_trainer_change', 'had_equipment_change',
        'had_veterinary_issue', 'had_lameness_issue', 'had_steward_incident', 'had_recent_scratch',
        'incident_count_last_30d', 'veterinary_count_last_180d', 'steward_incident_count_last_180d'
    ]
    for col in new_cols:
        df_feat[col] = 0
        
    # Parse dates
    df_feat['race_date_parsed'] = pd.to_datetime(df_feat['race_date']).dt.date
    df_events['report_date_parsed'] = pd.to_datetime(df_events['report_date']).dt.date
    
    # Normalize tracks for mapping
    df_feat['track_normalized'] = df_feat['track'].apply(lambda x: clean_horse_name(x).lower())
    df_events['track_normalized'] = df_events['city'].apply(lambda x: clean_horse_name(x).lower())
    
    # Build dictionary of events for fast lookup
    # Group events by horse_name_clean
    events_by_horse = {}
    for idx, row in df_events.iterrows():
        h = row['horse_name_clean']
        if h not in events_by_horse:
            events_by_horse[h] = []
        events_by_horse[h].append(row)
        
    print("Performing matching and feature calculation...")
    
    # Optimize calculation: only loop over horses that have events in the archive
    matched_count = 0
    
    # For every event, attempt to find its corresponding race row in df_feat
    for idx, event in tqdm(df_events.iterrows(), total=len(df_events), desc="Matching events"):
        h_clean = event['horse_name_clean']
        e_date = event['report_date_parsed']
        e_track = event['track_normalized']
        e_race_no = str(event['race_no']).strip()
        
        # Filter features df subset for matching candidates
        # Priority 1: date, city, race_no, horse
        candidates = df_feat[
            (df_feat['horse_name_clean'] == h_clean) & 
            (df_feat['race_date_parsed'] == e_date) & 
            (df_feat['track_normalized'] == e_track)
        ]
        
        match_idx = None
        if len(candidates) > 0:
            # If we have race_no, match exactly
            if e_race_no and e_race_no != 'None' and e_race_no != '':
                exact_race = candidates[candidates['race_no'].astype(str).str.contains(e_race_no)]
                if len(exact_race) > 0:
                    match_idx = exact_race.index[0]
            if match_idx is None:
                # Fall back to alternative: date, city, horse
                match_idx = candidates.index[0]
                
        if match_idx is not None:
            matched_indices.add(idx)
            matched_count += 1
            # Apply binary flags for the current race row
            if event['jockey_change_flag']:
                df_feat.loc[match_idx, 'had_jockey_change'] = 1
            if event['trainer_change_flag']:
                df_feat.loc[match_idx, 'had_trainer_change'] = 1
            if event['equipment_change_flag']:
                df_feat.loc[match_idx, 'had_equipment_change'] = 1
            if event['veterinary_flag'] or event['injury_flag']:
                df_feat.loc[match_idx, 'had_veterinary_issue'] = 1
            if event['lameness_flag']:
                df_feat.loc[match_idx, 'had_lameness_issue'] = 1
            if event['steward_incident_flag']:
                df_feat.loc[match_idx, 'had_steward_incident'] = 1
            if event['scratch_flag']:
                df_feat.loc[match_idx, 'had_recent_scratch'] = 1
        else:
            # Event could not be matched
            unmatched_events.append({
                'event_date': event['report_date'],
                'city': event['city'],
                'race_no': event['race_no'],
                'horse_name': event['horse_name'],
                'incident_type': event['incident_type'],
                'incident_text': event['incident_text'],
                'match_confidence': event['match_confidence'],
                'source_pdf': event['source_pdf']
            })
            
    # Calculate rolling counts for all rows in df_feat where horse matches a horse in events
    print("Calculating rolling counts for matched horses...")
    # Loop over horses in events_by_horse
    for h_clean, horse_events in tqdm(events_by_horse.items(), desc="Calculating rolling statistics"):
        # Find all race rows for this horse in the main features database
        horse_races = df_feat[df_feat['horse_name_clean'] == h_clean]
        if len(horse_races) == 0:
            continue
            
        for race_idx, race_row in horse_races.iterrows():
            r_date = race_row['race_date_parsed']
            
            # Windows
            date_30d_ago = r_date - timedelta(days=30)
            date_180d_ago = r_date - timedelta(days=180)
            
            # Count historical events for this horse
            incidents_30d = 0
            vets_180d = 0
            stewards_180d = 0
            scratches_30d = 0
            
            for event in horse_events:
                ev_date = event['report_date_parsed']
                # Must be strictly in the past relative to the current race
                if ev_date < r_date:
                    if ev_date >= date_30d_ago:
                        if event['steward_incident_flag']:
                            incidents_30d += 1
                        if event['scratch_flag']:
                            scratches_30d += 1
                    if ev_date >= date_180d_ago:
                        if event['veterinary_flag'] or event['injury_flag'] or event['lameness_flag']:
                            vets_180d += 1
                        if event['steward_incident_flag']:
                            stewards_180d += 1
                            
            df_feat.loc[race_idx, 'incident_count_last_30d'] = incidents_30d
            df_feat.loc[race_idx, 'veterinary_count_last_180d'] = vets_180d
            df_feat.loc[race_idx, 'steward_incident_count_last_180d'] = stewards_180d
            if scratches_30d > 0:
                df_feat.loc[race_idx, 'had_recent_scratch'] = 1

    # Cleanup temp columns
    df_feat = df_feat.drop(columns=['horse_name_clean', 'race_date_parsed', 'track_normalized'])
    
    # Save enriched Benter features
    output_benter_path = os.path.join(OUTPUT_DIR, "benter_features_with_komiser.csv")
    df_feat.to_csv(output_benter_path, index=False, encoding='utf-8')
    print(f"Saved enriched dataset: {len(df_feat)} rows to {output_benter_path}")
    
    # 5. Generate Match Report
    df_unmatched = pd.DataFrame(unmatched_events)
    unmatched_path = os.path.join(REPORTS_DIR, "komiser_match_report.csv")
    df_unmatched.to_csv(unmatched_path, index=False, encoding='utf-8')
    print(f"Saved unmatched match report: {len(df_unmatched)} rows to {unmatched_path}")
    
    # 6. Generate Feature Coverage Report
    feature_counts = []
    for col in new_cols:
        non_zero_cnt = (df_feat[col] > 0).sum()
        feature_counts.append({
            'feature_name': col,
            'non_zero_count': non_zero_cnt,
            'total_rows': len(df_feat),
            'coverage_percent': (non_zero_cnt / len(df_feat)) * 100.0
        })
    df_coverage = pd.DataFrame(feature_counts)
    coverage_path = os.path.join(REPORTS_DIR, "komiser_feature_coverage.csv")
    df_coverage.to_csv(coverage_path, index=False, encoding='utf-8')
    print(f"Saved feature coverage report to {coverage_path}")
    
    # 7. Generate Quality Control Markdown Report
    # Extract total counts of structured events
    total_events = len(df_events)
    total_health = df_events['veterinary_flag'].sum() + df_events['injury_flag'].sum() + df_events['lameness_flag'].sum()
    total_jockey = df_events['jockey_change_flag'].sum()
    total_trainer = df_events['trainer_change_flag'].sum()
    total_steward = df_events['steward_incident_flag'].sum()
    total_scratch = df_events['scratch_flag'].sum()
    match_rate = (matched_count / total_events) * 100.0 if total_events > 0 else 0.0
    
    report_content = f"""# Quality Control Report - TJK Stewards Reports Extraction

## PDF Processing Status
- **Total PDFs Found**: {qc_total_pdfs}
- **Successfully Read PDFs**: {qc_read_pdfs}
- **OCR Required PDFs**: {qc_ocr_needed} (PDFs containing <100 characters of extracted text)

## Structured Event Counts
- **Total Events Extracted**: {total_events}
- **Total Jockey Changes**: {total_jockey}
- **Total Trainer Changes**: {total_trainer}
- **Total Scratched Horses**: {total_scratch}
- **Total Health/Veterinary Incidents**: {total_health}
- **Total Steward/Kurul Incidents**: {total_steward}

## Match Statistics (with Benter Dataset)
- **Total Events Matched**: {matched_count}
- **Match Rate**: {match_rate:.2f}%
- **Total Unmatched Events**: {len(df_unmatched)} (saved to `reports/komiser_match_report.csv`)

*Note: Since the Benter race database only has 3 rows in 2026, most 2026 events in the PDF archive cannot be matched with performance records. They are correctly classified and logged in the unmatched events list.*
"""
    report_path = os.path.join(REPORTS_DIR, "komiser_extraction_report.md")
    with open(report_path, 'w', encoding='utf-8') as rf:
        rf.write(report_content)
    print(f"Saved Quality Control Report to {report_path}")
    
    print("\nExtraction and enrichment pipeline completed successfully!")

if __name__ == "__main__":
    main()
