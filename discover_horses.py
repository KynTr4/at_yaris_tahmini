"""Discover all accessible Turkish horses from documented list/filter endpoints."""
from __future__ import annotations
import argparse, asyncio, hashlib, html, json, logging, re, unicodedata
from collections import deque
from datetime import date, timedelta
from rapidfuzz.fuzz import WRatio
import sqlite3
from pedigreeall_core import APIClient, AccessRestricted, BASE_URL, canonical, connect, init_db, now, unwrap

PUBLIC_ONLY_MODE=True
partial_discovery_mode=True

def norm(v):
    s=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]+"," ",s).strip()

def i(v):
    try: return int(v) if v is not None and str(v)!="" else None
    except (TypeError,ValueError): return None

def f(v):
    try: return float(str(v).replace(".","").replace(",",".")) if v not in (None,"") else None
    except (TypeError,ValueError): return None
def text(v): return html.unescape(str(v)).strip() if v not in (None,"") else None

FIELDS=("source","source_record_id","tjk_id","horse_id","name","father_id","father_name","mother_id","mother_name","birth_date","age_text","sex","sex_id","race","race_id","country_id","country_name","owner","real_owner","breeder","trainer","earnings","starts","wins","seconds","thirds","fourths","discovery_payload_json","is_turkey","discovered_at")

def record(source,r,country_id=None,country_name=None,is_turkey=True):
    tjk=str(r.get("TJK_ID")) if r.get("TJK_ID") not in (None,0,"") else None
    hid=i(r.get("HORSE_ID")) if source!="tjk_list" else None
    rid=str(r.get("TJK_AT_ID") or r.get("HORSE_ID") or tjk or hashlib.sha1(canonical(r).encode()).hexdigest())
    return {"source":source,"source_record_id":rid,"tjk_id":tjk,"horse_id":hid,"name":text(r.get("NAME") or r.get("HORSE_NAME")),
      "father_id":i(r.get("FATHER_ID")),"father_name":text(r.get("FATHER_NAME")),"mother_id":i(r.get("MOTHER_ID")),"mother_name":text(r.get("MOTHER_NAME")),
      "birth_date":r.get("BIRTH_DATE") or r.get("HORSE_BIRTH_DATE"),"age_text":r.get("AGE"),"sex":r.get("GENDER") or r.get("SEX_TR") or r.get("SEX_EN"),"sex_id":i(r.get("SEX_ID")),
      "race":r.get("RACE"),"race_id":i(r.get("RACE_ID")),"country_id":country_id or i(r.get("COUNTRY_ID")),"country_name":country_name or r.get("COUNTRY_TR") or r.get("COUNTRY_EN"),
      "owner":r.get("OWNER"),"real_owner":r.get("REAL_OWNER"),"breeder":r.get("BREEDER"),"trainer":r.get("COACH"),"earnings":f(r.get("EARN")),
      "starts":i(r.get("START") or r.get("START_COUNT")),"wins":i(r.get("FIRST")),"seconds":i(r.get("SECOND")),"thirds":i(r.get("THIRD")),"fourths":i(r.get("FOURTH")),
      "discovery_payload_json":canonical(r),"is_turkey":int(is_turkey),"discovered_at":now()}

def horse_objects(obj):
    out=[]
    if isinstance(obj,dict):
        merged=obj.get("HORSE_INFO") if isinstance(obj.get("HORSE_INFO"),dict) else obj
        if isinstance(merged,dict) and (merged.get("HORSE_ID") or merged.get("TJK_ID")):
            if merged is not obj: merged={**merged,**{k:v for k,v in obj.items() if k!="HORSE_INFO"}}
            out.append(merged)
        for v in obj.values(): out.extend(horse_objects(v))
    elif isinstance(obj,list):
        for v in obj: out.extend(horse_objects(v))
    return out

async def public_request(c,key,path,entity,params):
    with connect(c.db_path) as db: restricted=db.execute("SELECT 1 FROM access_restrictions WHERE endpoint_key=?",(key,)).fetchone()
    if PUBLIC_ONLY_MODE and restricted: return None
    try: return await c.request(key,path,params=params,entity_key=entity)
    except AccessRestricted: return None
    except Exception: return None

async def discover_race_programs(c,args):
    found=0
    for offset in range(args.race_days):
        day=date.today()-timedelta(days=offset); ds=day.isoformat(); marker=f"race_program:{ds}"
        with connect(args.db) as db: done=db.execute("SELECT status FROM progress WHERE work_type='public_discovery' AND entity_key=? AND endpoint_key='race_program'",(marker,)).fetchone()
        if done and done[0]=="completed": continue
        await c.checkpoint("public_discovery",marker,"race_program","running")
        payload=None
        for date_value in (day.strftime("%d.%m.%Y"),ds):
            payload=await public_request(c,"GET:Tjk/GetRaceProgram","Tjk/GetRaceProgram",marker,{"p_sDate":date_value})
            if payload: break
        for city in payload if isinstance(payload,list) else []:
            if not isinstance(city,dict): continue
            for tab in city.get("SUB_TAB",[]) or []:
                if not isinstance(tab,dict): continue
                for entry in tab.get("PROGRAM_LIST",[]) or []:
                    if not isinstance(entry,dict): continue
                    hi=entry.get("HORSE_INFO") or {}; x={**hi,**{k:v for k,v in entry.items() if k!="HORSE_INFO"}}
                    upsert(args.db,record("race_program",x,is_turkey=True)); found+=1
                    with connect(args.db) as db: db.execute("INSERT OR REPLACE INTO race_program_entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(ds,i(city.get("CITY_ID")),city.get("CITY_NAME"),i(tab.get("RACE_TAB_ID")),tab.get("RACE_TAB_NAME") or tab.get("TITLE"),tab.get("RACE_NO"),str(entry.get("TJK_ID")) if entry.get("TJK_ID") else None,i(hi.get("HORSE_ID")),entry.get("HORSE_NAME") or hi.get("HORSE_NAME"),i(entry.get("AGE")),entry.get("WEIGHT"),entry.get("JOCKEY"),entry.get("OWNER"),entry.get("COACH"),entry.get("START"),entry.get("HANDICAP"),entry.get("LAST_6_RACE"),entry.get("KGS"),entry.get("GNY"),entry.get("AGF"),entry.get("DERECE"),canonical(hi)))
        await c.checkpoint("public_discovery",marker,"race_program","completed",message=f"horses={found}")
    return found

async def scan_range(c,args,kind,start,end):
    if end<start or end<=0: return 0
    endpoint="tjk_range" if kind=="tjk" else "horse_range"; key="GET:Tjk/Get" if kind=="tjk" else "GET:HorseInfo/GetById"; path="Tjk/Get" if kind=="tjk" else "HorseInfo/GetById"; param="p_iTjkId" if kind=="tjk" else "p_iId"
    with connect(args.db) as db: old=db.execute("SELECT last_cursor FROM progress WHERE work_type='public_discovery' AND entity_key='ranges' AND endpoint_key=?",(endpoint,)).fetchone()
    cursor=max(start,int(old[0])+1) if old and old[0] else start; found=0
    await c.checkpoint("public_discovery","ranges",endpoint,"running",str(cursor-1))
    for ident in range(cursor,end+1):
        payload=await public_request(c,key,path,f"{kind}:{ident}",{param:ident}); rows=unwrap(payload) if payload else []
        for x in horse_objects(rows):
            if not (x.get("NAME") or x.get("HORSE_NAME")): continue
            source="tjk_id_scan" if kind=="tjk" else "horse_id_scan"; upsert(args.db,record(source,x,is_turkey=kind=="tjk")); found+=1
        if ident%args.checkpoint_every==0: await c.checkpoint("public_discovery","ranges",endpoint,"running",str(ident),f"found={found}")
    await c.checkpoint("public_discovery","ranges",endpoint,"completed",str(end),f"found={found}"); return found

async def graph_crawl(c,args):
    with connect(args.db) as db: seeds=[x[0] for x in db.execute("SELECT DISTINCT horse_id FROM discovered_horses WHERE horse_id IS NOT NULL")]
    q=deque((x,0) for x in seeds); seen=set(); found=0
    specs=[("GET:HorseInfo/GetById","HorseInfo/GetById","p_iId"),("GET:Pedigree/GetPedigree","Pedigree/GetPedigree",None),("GET:Sibling/GetSiblingFromMother","Sibling/GetSiblingFromMother","p_iHorseId"),("GET:Sibling/GetSiblingFromFather","Sibling/GetSiblingFromFather","p_iHorseId"),("GET:Sibling/GetSiblingFromBroodmareSire","Sibling/GetSiblingFromBroodmareSire","p_iHorseId"),("GET:Progeny/GetProgeny","Progeny/GetProgeny","p_iHorseId")]
    while q and len(seen)<args.graph_max_nodes:
        hid,depth=q.popleft()
        if hid in seen or depth>args.graph_depth: continue
        seen.add(hid); entity=f"horse:{hid}"
        with connect(args.db) as db: done=db.execute("SELECT status FROM progress WHERE work_type='graph_crawl' AND entity_key=? AND endpoint_key='all'",(entity,)).fetchone()
        if done and done[0]=="completed": continue
        await c.checkpoint("graph_crawl",entity,"all","running")
        for key,path,param in specs:
            params={"p_iGenerationCount":5,"p_iFirstId":hid,"p_iSecondId":0} if param is None else {param:hid}
            payload=await public_request(c,key,path,entity,params)
            for x in horse_objects(unwrap(payload) if payload else []):
                xid=i(x.get("HORSE_ID"));
                if xid:
                    upsert(args.db,record("graph_crawl",x,is_turkey=False)); found+=1
                    if xid not in seen: q.append((xid,depth+1))
                for parent in (i(x.get("FATHER_ID")),i(x.get("MOTHER_ID"))):
                    if parent and parent not in seen: q.append((parent,depth+1))
        await c.checkpoint("graph_crawl",entity,"all","completed",message=f"depth={depth}")
    return found

def upsert(db_path,row):
    cols=",".join(FIELDS); marks=",".join("?" for _ in FIELDS); updates=",".join(f"{x}=excluded.{x}" for x in FIELDS if x not in ("source","source_record_id"))
    values=[row[x] for x in FIELDS]
    sql=f"INSERT INTO discovered_horses({cols}) VALUES({marks}) ON CONFLICT(source,source_record_id) DO UPDATE SET {updates}"
    update_by_horse_sql=",".join(f"{x}=?" for x in FIELDS if x not in ("source","source_record_id","horse_id"))
    update_by_horse_values=[row[x] for x in FIELDS if x not in ("source","source_record_id","horse_id")]
    if hasattr(db_path, "execute"):
        try:
            db_path.execute(sql, values)
        except sqlite3.IntegrityError:
            if row.get("horse_id") is None:
                raise
            db_path.execute(f"UPDATE discovered_horses SET {update_by_horse_sql} WHERE horse_id=?", update_by_horse_values+[row["horse_id"]])
    else:
        with connect(db_path) as db:
            try:
                db.execute(sql, values)
            except sqlite3.IntegrityError:
                if row.get("horse_id") is None:
                    raise
                db.execute(f"UPDATE discovered_horses SET {update_by_horse_sql} WHERE horse_id=?", update_by_horse_values+[row["horse_id"]])

def link_horses(db_path,threshold=97.0):
    with connect(db_path) as db:
        tjk=[dict(x) for x in db.execute("SELECT * FROM discovered_horses WHERE source='tjk_list'")]; horses=[dict(x) for x in db.execute("SELECT * FROM discovered_horses WHERE source LIKE 'horse_filter%'")]
        exact={}
        for h in horses: exact.setdefault((norm(h["name"]),norm(h["father_name"]),norm(h["mother_name"])),[]).append(h)
        for t in tjk:
            key=(norm(t["name"]),norm(t["father_name"]),norm(t["mother_name"])); choices=exact.get(key,[]); best=None; method="unmatched"; score=0.0
            if len(choices)==1: best=choices[0]; method="exact_name_parents"; score=100.0
            else:
                candidates=[]
                for h in horses:
                    s=.55*WRatio(key[0],norm(h["name"]))+.225*WRatio(key[1],norm(h["father_name"]))+.225*WRatio(key[2],norm(h["mother_name"]))
                    if s>=threshold: candidates.append((s,h))
                candidates.sort(key=lambda x:x[0],reverse=True)
                if candidates and (len(candidates)==1 or candidates[0][0]-candidates[1][0]>=3): score,best=candidates[0]; method="fuzzy_name_parents"
            if best:
                db.execute("INSERT OR REPLACE INTO horse_links VALUES(?,?,?,?,?,?,?)",(t["tjk_id"],best["horse_id"],method,round(score/100,4),canonical({"tjk":key,"horse":[best["name"],best["father_name"],best["mother_name"]]}),int(score>=threshold),now()))

async def run(args):
    init_db(args.db); c=APIClient(args.db,args.base_url,args.rps,args.concurrency,args.timeout,args.retries,args.api_key)
    async with c.open():
        if not args.skip_tjk_list:
            await c.checkpoint("discovery","turkey","tjk_list","running")
            try:
                tjk=unwrap(await asyncio.wait_for(c.request("GET:Tjk/getHorseListFromTjk","Tjk/getHorseListFromTjk",entity_key="turkey"),timeout=args.full_list_timeout)) or []
                for r in tjk:
                    if isinstance(r,dict): upsert(args.db,record("tjk_list",r))
                await c.checkpoint("discovery","turkey","tjk_list","completed",str(len(tjk)))
            except Exception as exc:
                await c.checkpoint("discovery","turkey","tjk_list","failed",message=f"Non-blocking source failure: {exc}")
        countries=unwrap(await c.request("GET:Country/Get","Country/Get",entity_key="reference")) or []
        turkey=[x for x in countries if "TURK" in norm(x.get("COUNTRY_TR")) or "TURK" in norm(x.get("COUNTRY_EN"))]
        if not turkey: raise RuntimeError("Country/Get yanıtında Türkiye bulunamadı; ülke filtresi varsayılamaz")
        country_id=i(turkey[0].get("COUNTRY_ID")); country_name=turkey[0].get("COUNTRY_TR") or turkey[0].get("COUNTRY_EN")
        with connect(args.db) as db:
            old=db.execute("SELECT last_cursor,status FROM progress WHERE work_type='discovery' AND entity_key='turkey' AND endpoint_key='horse_filter'").fetchone()
        page=max(1,int(old[0])+1) if old and old[0] and old[1]!="completed" else 1
        await c.checkpoint("discovery","turkey","horse_filter","running",str(page-1))
        while True:
            body={"COUNTRY_ID":str(country_id),"PAGE_NO":page,"PAGE_COUNT":args.page_size,"ACTIVE":"","APPROVED":""}
            try:
                payload=unwrap(await c.request("POST:Horse/GetFilter","Horse/GetFilter","POST",body=body,entity_key=f"turkey:page:{page}")) or []
            except Exception as exc:
                await c.checkpoint("discovery","turkey","horse_filter","failed",str(page-1),f"Discovery access failed: {exc}")
                break
            if not isinstance(payload,list): raise RuntimeError("Horse/GetFilter m_cData liste değil")
            for r in payload:
                if isinstance(r,dict): upsert(args.db,record("horse_filter_turkey",r,country_id,country_name))
            await c.checkpoint("discovery","turkey","horse_filter","running",str(page),f"page_rows={len(payload)}")
            if len(payload)<args.page_size: break
            page+=1
            if args.max_pages and page>args.max_pages: break
        with connect(args.db) as db:
            state=db.execute("SELECT status FROM progress WHERE work_type='discovery' AND entity_key='turkey' AND endpoint_key='horse_filter'").fetchone()
        if not state or state[0]!="failed": await c.checkpoint("discovery","turkey","horse_filter","completed",str(page))
        public_counts={}
        if not args.no_race_program: public_counts["race_program_records"]=await discover_race_programs(c,args)
        public_counts["tjk_range_records"]=await scan_range(c,args,"tjk",args.tjk_start,args.tjk_end)
        public_counts["horse_range_records"]=await scan_range(c,args,"horse",args.horse_start,args.horse_end)
        if not args.no_graph: public_counts["graph_records"]=await graph_crawl(c,args)
        with connect(args.db) as db: db.execute("INSERT OR REPLACE INTO schema_meta VALUES('partial_discovery_mode','true')")
    link_horses(args.db,args.match_threshold)
    with connect(args.db) as db: print(json.dumps({"mode":"partial_discovery_mode","public_only":PUBLIC_ONLY_MODE,"discovered":db.execute("SELECT COUNT(*) FROM discovered_horses").fetchone()[0],"tjk":db.execute("SELECT COUNT(*) FROM discovered_horses WHERE tjk_id IS NOT NULL").fetchone()[0],"horse_id":db.execute("SELECT COUNT(*) FROM discovered_horses WHERE horse_id IS NOT NULL").fetchone()[0],"linked":db.execute("SELECT COUNT(*) FROM horse_links WHERE verified=1").fetchone()[0],**public_counts},ensure_ascii=False,indent=2))

def main():
    p=argparse.ArgumentParser(); p.add_argument("--db",default="pedigreeall_progress.db"); p.add_argument("--base-url",default=BASE_URL); p.add_argument("--api-key"); p.add_argument("--rps",type=float,default=.75); p.add_argument("--concurrency",type=int,default=2); p.add_argument("--timeout",type=float,default=60); p.add_argument("--retries",type=int,default=5); p.add_argument("--page-size",type=int,default=500); p.add_argument("--max-pages",type=int,default=0); p.add_argument("--match-threshold",type=float,default=97); p.add_argument("--skip-tjk-list",action="store_true"); p.add_argument("--full-list-timeout",type=float,default=45); p.add_argument("--race-days",type=int,default=30); p.add_argument("--no-race-program",action="store_true"); p.add_argument("--tjk-start",type=int,default=1); p.add_argument("--tjk-end",type=int,default=0); p.add_argument("--horse-start",type=int,default=1); p.add_argument("--horse-end",type=int,default=0); p.add_argument("--checkpoint-every",type=int,default=100); p.add_argument("--graph-depth",type=int,default=2); p.add_argument("--graph-max-nodes",type=int,default=10000); p.add_argument("--no-graph",action="store_true"); a=p.parse_args(); logging.basicConfig(filename="pedigreeall.log",level=logging.INFO); asyncio.run(run(a))
if __name__=="__main__": main()
