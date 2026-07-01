"""Shared infrastructure for the Pedigreeall data-lake pipeline."""
from __future__ import annotations
import asyncio, hashlib, json, logging, random, sqlite3, time, uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import aiohttp
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter
from app_config import DB_PATH

BASE_URL="https://api.pedigreeall.com/"
SCHEMA_VERSION=3
PUBLIC_ONLY_MODE=True

def now(): return datetime.now(timezone.utc).isoformat()
def canonical(value: Any): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))

class ClosingConnection(sqlite3.Connection):
    def __exit__(self,*args):
        try: return super().__exit__(*args)
        finally: self.close()

def connect(path: str|Path):
    db=sqlite3.connect(path,timeout=60,factory=ClosingConnection)
    db.row_factory=sqlite3.Row; db.execute("PRAGMA journal_mode=WAL"); db.execute("PRAGMA synchronous=NORMAL"); db.execute("PRAGMA foreign_keys=ON")
    return db

DDL="""
CREATE TABLE IF NOT EXISTS schema_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS endpoint_catalog(
 endpoint_key TEXT PRIMARY KEY,method TEXT NOT NULL,path TEXT NOT NULL,parameters_json TEXT,
 request_schema_json TEXT,response_schema_json TEXT,description TEXT,help_url TEXT,
 safety_class TEXT NOT NULL DEFAULT 'unknown',verified_at TEXT,enabled INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS discovered_horses(
 id INTEGER PRIMARY KEY AUTOINCREMENT,source TEXT NOT NULL,source_record_id TEXT,tjk_id TEXT,horse_id INTEGER,
 name TEXT,father_id INTEGER,father_name TEXT,mother_id INTEGER,mother_name TEXT,birth_date TEXT,age_text TEXT,
 sex TEXT,sex_id INTEGER,race TEXT,race_id INTEGER,country_id INTEGER,country_name TEXT,owner TEXT,real_owner TEXT,
 breeder TEXT,trainer TEXT,earnings REAL,starts INTEGER,wins INTEGER,seconds INTEGER,thirds INTEGER,fourths INTEGER,
 discovery_payload_json TEXT NOT NULL,is_turkey INTEGER NOT NULL DEFAULT 0,discovered_at TEXT NOT NULL,
 UNIQUE(source,source_record_id));
CREATE INDEX IF NOT EXISTS idx_discovered_tjk ON discovered_horses(tjk_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_discovered_horse ON discovered_horses(horse_id) WHERE horse_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS horse_links(
 tjk_id TEXT PRIMARY KEY,horse_id INTEGER,match_method TEXT NOT NULL,confidence REAL NOT NULL,
 evidence_json TEXT,verified INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS horse_profiles(
 horse_key TEXT PRIMARY KEY,tjk_id TEXT,horse_id INTEGER,name TEXT,birth_date TEXT,birth_year INTEGER,age INTEGER,
 sex TEXT,color TEXT,country TEXT,father_id INTEGER,father_name TEXT,mother_id INTEGER,mother_name TEXT,
 broodmare_sire TEXT,owner TEXT,breeder TEXT,trainer TEXT,is_dead INTEGER,earnings REAL,currency_id INTEGER,
 starts INTEGER,wins INTEGER,seconds INTEGER,thirds INTEGER,fourths INTEGER,handicap REAL,group_g1 INTEGER,
 group_g2 INTEGER,group_g3 INTEGER,unsupported_fields_json TEXT,extra_fields_json TEXT,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS horse_pedigrees(
 horse_key TEXT NOT NULL,generation INTEGER NOT NULL,position INTEGER NOT NULL,ancestor_horse_id INTEGER,
 ancestor_name TEXT,father_id INTEGER,mother_id INTEGER,is_sire INTEGER,family_text TEXT,info_json TEXT,
 PRIMARY KEY(horse_key,generation,position));
CREATE TABLE IF NOT EXISTS horse_races(
 horse_key TEXT NOT NULL,race_id TEXT NOT NULL,race_date TEXT,hippodrome TEXT,distance INTEGER,surface TEXT,
 race_class TEXT,finish TEXT,race_time TEXT,agf TEXT,odds TEXT,jockey TEXT,trainer TEXT,prize TEXT,weight TEXT,
 equipment TEXT,gate TEXT,rating TEXT,video TEXT,photo TEXT,raw_fields_json TEXT,
 PRIMARY KEY(horse_key,race_id));
CREATE TABLE IF NOT EXISTS race_program_entries(
 program_date TEXT NOT NULL,city_id INTEGER,city_name TEXT,race_tab_id INTEGER,race_name TEXT,race_no TEXT,
 tjk_id TEXT,horse_id INTEGER,horse_name TEXT,age INTEGER,weight TEXT,jockey TEXT,owner TEXT,trainer TEXT,
 gate TEXT,handicap TEXT,last_6_race TEXT,kgs TEXT,odds TEXT,agf TEXT,race_time TEXT,horse_info_json TEXT,
 PRIMARY KEY(program_date,city_id,race_tab_id,tjk_id));
CREATE TABLE IF NOT EXISTS horse_statistics(
 horse_key TEXT PRIMARY KEY,starts INTEGER,wins INTEGER,seconds INTEGER,thirds INTEGER,fourths INTEGER,
 earnings REAL,g1 INTEGER,g2 INTEGER,g3 INTEGER,surface_stats_json TEXT,distance_stats_json TEXT,
 seasonal_stats_json TEXT,jockey_stats_json TEXT,trainer_stats_json TEXT,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS horse_siblings(
 horse_key TEXT NOT NULL,relation_type TEXT NOT NULL,sibling_horse_id INTEGER,sibling_name TEXT,
 profile_json TEXT,PRIMARY KEY(horse_key,relation_type,sibling_horse_id,sibling_name));
CREATE TABLE IF NOT EXISTS horse_progeny(
 horse_key TEXT NOT NULL,progeny_horse_id INTEGER,progeny_name TEXT,earnings REAL,starts INTEGER,wins INTEGER,
 statistics_json TEXT,profile_json TEXT,PRIMARY KEY(horse_key,progeny_horse_id,progeny_name));
CREATE TABLE IF NOT EXISTS horse_media(
 horse_key TEXT NOT NULL,media_type TEXT NOT NULL,url TEXT NOT NULL,description TEXT,source_endpoint TEXT,
 PRIMARY KEY(horse_key,media_type,url));
CREATE TABLE IF NOT EXISTS raw_api_responses(
 id INTEGER PRIMARY KEY AUTOINCREMENT,request_key TEXT UNIQUE NOT NULL,entity_key TEXT,endpoint_key TEXT NOT NULL,
 method TEXT NOT NULL,request_url TEXT NOT NULL,request_params_json TEXT,request_body_json TEXT,status_code INTEGER,
 response_json TEXT,response_sha256 TEXT,fetched_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS progress(
 work_type TEXT NOT NULL,entity_key TEXT NOT NULL,endpoint_key TEXT NOT NULL,status TEXT NOT NULL,
 attempts INTEGER NOT NULL DEFAULT 0,last_cursor TEXT,message TEXT,started_at TEXT,completed_at TEXT,updated_at TEXT NOT NULL,
 PRIMARY KEY(work_type,entity_key,endpoint_key));
CREATE TABLE IF NOT EXISTS errors(
 id INTEGER PRIMARY KEY AUTOINCREMENT,work_type TEXT,entity_key TEXT,endpoint_key TEXT,error_type TEXT,
 status_code INTEGER,message TEXT,attempt INTEGER,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS endpoint_probe_results(
 endpoint_key TEXT PRIMARY KEY,status_class TEXT NOT NULL,http_status INTEGER,latency_ms INTEGER,
 sample_params_json TEXT,sample_body_json TEXT,message TEXT,probed_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS access_restrictions(
 endpoint_key TEXT PRIMARY KEY,http_status INTEGER NOT NULL,reason TEXT,first_seen_at TEXT NOT NULL,last_seen_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_discovered_country ON discovered_horses(is_turkey,country_id);
CREATE INDEX IF NOT EXISTS idx_races_horse_date ON horse_races(horse_key,race_date);
CREATE INDEX IF NOT EXISTS idx_raw_entity ON raw_api_responses(entity_key,endpoint_key);
"""

def init_db(path: str|Path):
    with connect(path) as db:
        # Preserve v1 catalog before upgrading its wider schema.
        cols={r[1] for r in db.execute("PRAGMA table_info(endpoint_catalog)")}
        if cols and "request_schema_json" not in cols:
            db.execute("ALTER TABLE endpoint_catalog RENAME TO endpoint_catalog_v1")
        cols={r[1] for r in db.execute("PRAGMA table_info(progress)")}
        if cols and "work_type" not in cols:
            db.execute("ALTER TABLE progress RENAME TO progress_v1")
        cols={r[1] for r in db.execute("PRAGMA table_info(errors)")}
        if cols and "work_type" not in cols:
            db.execute("ALTER TABLE errors RENAME TO errors_v1")
        cols={r[1] for r in db.execute("PRAGMA table_info(raw_api_responses)")}
        if cols and "request_key" not in cols:
            db.execute("ALTER TABLE raw_api_responses RENAME TO raw_api_responses_v1")
        db.executescript(DDL)
        existing={r[1] for r in db.execute("PRAGMA table_info(endpoint_catalog)")}
        for name,decl in (("access_status","TEXT"),("last_probe_status","INTEGER"),("last_probed_at","TEXT")):
            if name not in existing: db.execute(f"ALTER TABLE endpoint_catalog ADD COLUMN {name} {decl}")
        db.execute("DROP INDEX IF EXISTS uq_discovered_tjk")
        db.execute("INSERT OR REPLACE INTO schema_meta VALUES('schema_version',?)",(str(SCHEMA_VERSION),))
        seeds=[
          ("GET:Tjk/getHorseListFromTjk","GET","Tjk/getHorseListFromTjk",[],"read",1),("GET:Horse/GetCount","GET","Horse/GetCount",[],"read",1),
          ("POST:Horse/GetFilter","POST","Horse/GetFilter",["COUNTRY_ID","PAGE_NO","PAGE_COUNT"],"read_filter",1),("POST:HorseInfo/GetFilter","POST","HorseInfo/GetFilter",["COUNTRY_ID","PAGE_NO","PAGE_COUNT"],"read_filter",1),
          ("GET:Country/Get","GET","Country/Get",[],"read",1),("GET:Tjk/Get","GET","Tjk/Get",["p_iTjkId"],"read",1),("GET:Tjk/GetHorseFromTjk","GET","Tjk/GetHorseFromTjk",["p_iTjkId"],"read",1),
          ("GET:HorseInfo/GetById","GET","HorseInfo/GetById",["p_iId"],"read",1),("GET:Pedigree/GetPedigree","GET","Pedigree/GetPedigree",["p_iGenerationCount","p_iFirstId","p_iSecondId"],"read",1),
          ("GET:Sibling/GetSiblingFromMother","GET","Sibling/GetSiblingFromMother",["p_iHorseId"],"read",1),("GET:Sibling/GetSiblingFromFather","GET","Sibling/GetSiblingFromFather",["p_iHorseId"],"read",1),
          ("GET:Sibling/GetSiblingFromBroodmareSire","GET","Sibling/GetSiblingFromBroodmareSire",["p_iHorseId"],"read",1),("GET:Progeny/GetProgeny","GET","Progeny/GetProgeny",["p_iHorseId"],"read",1),
          ("GET:ImageInfo/GetById","GET","ImageInfo/GetById",["p_iHorseId"],"read",1),("GET:FamilySuccess/Get","GET","FamilySuccess/Get",["p_iHorseId"],"read",1)]
        seeds.extend([
          ("GET:Tjk/GetRaceProgram","GET","Tjk/GetRaceProgram",["p_sDate"],"read",1),("GET:Tjk/GetRestRace","GET","Tjk/GetRestRace",["p_iTjkId","p_iRaceId"],"read",1),
          ("GET:HorseInfo/GetLatest","GET","HorseInfo/GetLatest",["p_iRaceId"],"read",1),("GET:HorseInfo/GetFoals","GET","HorseInfo/GetFoals",["p_iHorseId","p_iTypeId"],"read",1)])
        for key,method,route,params,safety,enabled in seeds:
            db.execute("""INSERT INTO endpoint_catalog(endpoint_key,method,path,parameters_json,help_url,safety_class,verified_at,enabled) VALUES(?,?,?,?,?,?,?,?)
             ON CONFLICT(endpoint_key) DO UPDATE SET method=excluded.method,path=excluded.path,parameters_json=excluded.parameters_json,safety_class=excluded.safety_class,enabled=excluded.enabled""",
             (key,method,route,canonical(params),urljoin(BASE_URL,"Help"),safety,"2026-06-20",enabled))
    # Versioned provenance migrations are also applied for fresh/test databases.
    from migrate_provenance_schema import apply_migrations
    apply_migrations(path)

class RetriableHTTP(Exception):
    def __init__(self,status: int|None,message: str,retry_after: float|None=None): super().__init__(message); self.status=status; self.retry_after=retry_after
class AccessRestricted(Exception):
    def __init__(self,status:int,message:str): super().__init__(message); self.status=status

class RateLimiter:
    def __init__(self,rps: float):
        if rps<=0: raise ValueError("rps must be > 0")
        self.interval=1/rps; self.lock=asyncio.Lock(); self.last=0.0
    async def wait(self):
        async with self.lock:
            delay=max(0,self.interval-(time.monotonic()-self.last))
            if delay: await asyncio.sleep(delay)
            self.last=time.monotonic()

class APIClient:
    def __init__(self,db_path=DB_PATH,base_url=BASE_URL,rps=1.0,concurrency=3,timeout=45,retries=5,api_key=None):
        self.db_path=Path(db_path); init_db(self.db_path); self.base_url=base_url.rstrip("/")+"/"; self.rate=RateLimiter(rps)
        self.sem=asyncio.Semaphore(concurrency); self.timeout=aiohttp.ClientTimeout(total=timeout,connect=min(15,timeout)); self.retries=retries
        self.headers={"Accept":"application/json","User-Agent":"PedigreeallTurkeyDataLake/2.0"}; self.session=None; self.db_lock=asyncio.Lock(); self.log=logging.getLogger(__name__)
        self.last_source_request_id=None
        api_key=None if PUBLIC_ONLY_MODE else (api_key or os.getenv("PEDIGREEALL_API_KEY"))
        if api_key: self.headers["Authorization"]=f"Bearer {api_key}"
    @asynccontextmanager
    async def open(self):
        async with aiohttp.ClientSession(timeout=self.timeout,headers=self.headers,connector=aiohttp.TCPConnector(limit=20,ttl_dns_cache=300)) as s:
            self.session=s
            try: yield self
            finally: self.session=None
    async def request(self,key,path,method="GET",params=None,body=None,entity_key=None,store_raw=True):
        if self.session is None: raise RuntimeError("Use 'async with client.open()'")
        url=urljoin(self.base_url,path); signature=hashlib.sha256(canonical([method,url,params,body]).encode()).hexdigest()
        async for attempt in AsyncRetrying(stop=stop_after_attempt(self.retries),wait=wait_exponential_jitter(initial=1,max=60),retry=retry_if_exception_type((RetriableHTTP,aiohttp.ClientError,asyncio.TimeoutError)),reraise=True):
            with attempt:
                try:
                    async with self.sem:
                        await self.rate.wait()
                        async with self.session.request(method,url,params=params,json=body) as resp:
                            text=await resp.text(); status=resp.status
                            if status in (401,403):
                                await self.restriction(key,status,text[:1000]); raise AccessRestricted(status,text[:1000])
                            if status==429 or status>=500:
                                ra=resp.headers.get("Retry-After"); raise RetriableHTTP(status,text[:1000],float(ra) if ra and ra.isdigit() else None)
                            if status==404: return None
                            if status>=400: raise aiohttp.ClientResponseError(resp.request_info,resp.history,status=status,message=text[:1000])
                            try: payload=json.loads(text)
                            except json.JSONDecodeError as e: raise RetriableHTTP(status,f"Non-JSON response: {text[:300]}") from e
                            if store_raw:
                                self.last_source_request_id=await self.save_raw(signature,entity_key,key,method,str(resp.url),params,body,status,payload)
                            return payload
                except Exception as exc:
                    if not isinstance(exc,AccessRestricted): await self.error("request",entity_key,key,exc,attempt.retry_state.attempt_number)
                    raise
    async def restriction(self,key,status,reason):
        stamp=now()
        async with self.db_lock:
            with connect(self.db_path) as db:
                db.execute("INSERT INTO access_restrictions VALUES(?,?,?,?,?) ON CONFLICT(endpoint_key) DO UPDATE SET http_status=excluded.http_status,reason=excluded.reason,last_seen_at=excluded.last_seen_at",(key,status,reason,stamp,stamp))
                db.execute("UPDATE endpoint_catalog SET access_status='requires_api_key',last_probe_status=?,last_probed_at=? WHERE endpoint_key=?",(status,stamp,key))
    async def save_raw(self,request_key,entity,key,method,url,params,body,status,payload):
        raw=canonical(payload); stamp=now()
        # A request signature identifies the logical request.  The stored key
        # identifies one immutable network capture, so repeated downloads append.
        capture_key=hashlib.sha256(canonical([request_key,stamp,uuid.uuid4().hex]).encode()).hexdigest()
        async with self.db_lock:
            with connect(self.db_path) as db:
                db.execute("""INSERT INTO raw_api_responses(request_key,entity_key,endpoint_key,method,request_url,request_params_json,request_body_json,status_code,response_json,response_sha256,fetched_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (capture_key,entity,key,method,url,canonical(params),canonical(body),status,raw,hashlib.sha256(raw.encode()).hexdigest(),stamp))
        return capture_key
    async def error(self,work,entity,key,exc,attempt):
        async with self.db_lock:
            with connect(self.db_path) as db: db.execute("INSERT INTO errors(work_type,entity_key,endpoint_key,error_type,status_code,message,attempt,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (work,entity,key,type(exc).__name__,getattr(exc,"status",None),str(exc)[:4000],attempt,now()))
    async def checkpoint(self,work,entity,key,status,cursor=None,message=None):
        stamp=now()
        async with self.db_lock:
            with connect(self.db_path) as db: db.execute("""INSERT INTO progress VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(work_type,entity_key,endpoint_key) DO UPDATE SET status=excluded.status,attempts=CASE WHEN excluded.status='running' THEN progress.attempts+1 ELSE progress.attempts END,last_cursor=excluded.last_cursor,message=excluded.message,completed_at=excluded.completed_at,updated_at=excluded.updated_at""",
            (work,entity,key,status,1,cursor,message,stamp,stamp if status in ('completed','failed','not_found') else None,stamp))

def unwrap(payload):
    return payload.get("m_cData",payload) if isinstance(payload,dict) else payload


class TjkResolverCache:
    def __init__(self, conn):
        self.conn = conn
        self.tables = {}
        self.program_entries = {}  # (horse_id, date) -> tjk_id
        self.program_entries_hist = {}  # horse_id -> (tjk_id, program_date)
        self.links = {}  # horse_id -> tjk_id
        self.profiles_by_id = {}  # horse_id -> tjk_id
        self.profiles_by_name = {}  # folded_name -> (tjk_id, name)
        self.mapping = {}  # horse_id -> tjk_id
        self.loaded = False

    def load_all(self):
        if self.loaded:
            return
        
        # Check tables once
        for t in ("race_program_entries", "horse_links", "horse_profiles", "horse_mapping"):
            self.tables[t] = self.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)
            ).fetchone() is not None

        # Preload program entries
        if self.tables.get("race_program_entries"):
            for r in self.conn.execute("SELECT horse_id, tjk_id, program_date FROM race_program_entries WHERE horse_id IS NOT NULL AND tjk_id IS NOT NULL AND tjk_id != '' AND tjk_id != '0'"):
                h_id = r[0]
                t_id = str(r[1])
                dt = r[2]
                self.program_entries[(h_id, dt)] = t_id
                existing = self.program_entries_hist.get(h_id)
                if not existing or dt > existing[1]:
                    self.program_entries_hist[h_id] = (t_id, dt)

        # Preload horse_links
        if self.tables.get("horse_links"):
            for r in self.conn.execute("SELECT horse_id, tjk_id FROM horse_links WHERE verified = 1 AND horse_id IS NOT NULL AND tjk_id IS NOT NULL AND tjk_id != '' AND tjk_id != '0'"):
                self.links[r[0]] = str(r[1])

        # Preload horse_profiles
        if self.tables.get("horse_profiles"):
            from race_scope import fold
            for r in self.conn.execute("SELECT horse_id, tjk_id, name FROM horse_profiles WHERE tjk_id IS NOT NULL AND tjk_id != '' AND tjk_id != '0'"):
                h_id = r[0]
                t_id = str(r[1])
                name = r[2]
                if h_id is not None:
                    self.profiles_by_id[h_id] = t_id
                if name:
                    self.profiles_by_name[fold(name)] = (t_id, name)

        # Preload horse_mapping
        if self.tables.get("horse_mapping"):
            for r in self.conn.execute("SELECT horse_id, tjk_id FROM horse_mapping WHERE verified = 1 AND horse_id IS NOT NULL AND tjk_id IS NOT NULL AND tjk_id != '' AND tjk_id != '0'"):
                self.mapping[r[0]] = str(r[1])

        self.loaded = True


_resolver_caches = {}


def resolve_tjk_id(conn: sqlite3.Connection, horse_id: Any, horse_name: str | None = None, date: str | None = None) -> dict[str, Any]:
    from race_scope import fold

    global _resolver_caches
    if len(_resolver_caches) > 100:
        _resolver_caches.clear()

    conn_id = id(conn)
    if conn_id not in _resolver_caches:
        _resolver_caches[conn_id] = TjkResolverCache(conn)
    cache = _resolver_caches[conn_id]
    cache.load_all()

    # Normalize inputs
    tjk_id_val = None
    h_id = None

    if isinstance(horse_id, str):
        if horse_id.startswith("tjk:"):
            val = horse_id.split(":", 1)[1].strip()
            if val and val != "0" and val.lower() != "none":
                tjk_id_val = val
        elif horse_id.startswith("horse:"):
            val = horse_id.split(":", 1)[1].strip()
            if val and val != "0" and val.lower() != "none":
                try:
                    h_id = int(val)
                except ValueError:
                    h_id = val
        else:
            val = horse_id.strip()
            if val and val != "0" and val.lower() != "none":
                try:
                    h_id = int(val)
                except ValueError:
                    h_id = val
    elif isinstance(horse_id, int):
        h_id = horse_id

    if tjk_id_val:
        return {
            "tjk_id": tjk_id_val,
            "source_table": "input_tjk_id",
            "confidence": 1.0,
            "reason": "Input was already a valid TJK ID key"
        }

    if h_id is None and not horse_name:
        return {
            "tjk_id": None,
            "source_table": None,
            "confidence": 0.0,
            "reason": "No valid horse_id or horse_name provided"
        }

    # 1. race_program_entries.tjk_id match by horse_id
    if h_id is not None and cache.tables.get("race_program_entries"):
        if date and (h_id, date) in cache.program_entries:
            return {
                "tjk_id": cache.program_entries[(h_id, date)],
                "source_table": "race_program_entries",
                "confidence": 1.0,
                "reason": f"Matched by horse_id and date={date}"
            }
        
        if h_id in cache.program_entries_hist:
            t_id, hist_date = cache.program_entries_hist[h_id]
            return {
                "tjk_id": t_id,
                "source_table": "race_program_entries",
                "confidence": 1.0,
                "reason": f"Matched by horse_id (historical date {hist_date})"
            }

    # 2. horse_links (verified=1)
    if h_id is not None and cache.tables.get("horse_links"):
        if h_id in cache.links:
            return {
                "tjk_id": cache.links[h_id],
                "source_table": "horse_links",
                "confidence": 1.0,
                "reason": "Matched by verified horse_links"
            }

    # 3. horse_profiles
    if cache.tables.get("horse_profiles"):
        if h_id is not None and h_id in cache.profiles_by_id:
            return {
                "tjk_id": cache.profiles_by_id[h_id],
                "source_table": "horse_profiles",
                "confidence": 1.0,
                "reason": "Matched by horse_id in horse_profiles"
            }

        if horse_name:
            folded_name = fold(horse_name)
            if folded_name in cache.profiles_by_name:
                t_id, db_name = cache.profiles_by_name[folded_name]
                return {
                    "tjk_id": t_id,
                    "source_table": "horse_profiles",
                    "confidence": 0.8,
                    "reason": f"Matched by normalized name fallback (name={db_name})"
                }

    # 4. horse_mapping (verified=1)
    if h_id is not None and cache.tables.get("horse_mapping"):
        if h_id in cache.mapping:
            return {
                "tjk_id": cache.mapping[h_id],
                "source_table": "horse_mapping",
                "confidence": 1.0,
                "reason": "Matched by verified legacy horse_mapping"
            }

    return {
        "tjk_id": None,
        "source_table": None,
        "confidence": 0.0,
        "reason": "No TJK ID found across all sources"
    }



