"""Safely classify documented endpoints under anonymous/public access."""
from __future__ import annotations
import argparse, asyncio, json, time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin
import aiohttp, pandas as pd
from pedigreeall_core import APIClient, BASE_URL, canonical, connect, init_db, now

PUBLIC_ONLY_MODE=True
UNLOCKED_FIELDS={
 "GET:HorseInfo/GetById":["HORSE_ID","HORSE_NAME","FATHER_ID/NAME","MOTHER_ID/NAME","BM_SIRE_NAME","COLOR_TEXT","SEX_OBJECT","EARN","START_COUNT","FIRST-FOURTH","OWNER","BREEDER","COACH","IMAGE_LIST"],
 "GET:HorseInfo/GetFoals":["foal HORSE_INFO profiles","foal earnings","foal career statistics"],"GET:HorseInfo/GetLatest":["latest HORSE_INFO records","HORSE_ID","parents","profile summary"],
 "GET:Horse/GetCount":["total internal horse record count"],
 "GET:Pedigree/GetPedigree":["PEDIGREE_CELL_LIST","5-generation HORSE_ID/NAME","FATHER_ID","MOTHER_ID","FAMILY_OBJECT","INFO_LIST"],
 "GET:Sibling/GetSiblingFromMother":["maternal_siblings","sibling_profile_and_statistics"],"GET:Sibling/GetSiblingFromFather":["paternal_siblings","sibling_profile_and_statistics"],
 "GET:Sibling/GetSiblingFromBroodmareSire":["broodmare_sire_siblings","sibling_profile_and_statistics"],"GET:Progeny/GetProgeny":["progeny_profiles","progeny_earnings","progeny_statistics"],
 "GET:ImageInfo/GetById":["INFO","IMAGE","IMAGE_LIST"],"POST:Horse/GetFilter":["country-filtered HORSE_ID list","profile summary","pagination"],"POST:HorseInfo/GetFilter":["HORSE_INFO list","country filter","pagination"]}
def sample_value(name):
    x=name.lower()
    if "date" in x: return date.today().strftime("%d.%m.%Y")
    if "language" in x: return 1
    if "pagecount" in x or "page_count" in x: return 1
    if "pageno" in x or "page_no" in x: return 1
    if "count" in x: return 1
    if "path" in x or "link" in x: return "/"
    if "list" in x: return "1"
    return 1
def fixture(params,request_sample,method):
    params=params or []; query={p:sample_value(p) for p in params} if method=="GET" else {}
    body=None
    if method=="POST":
        body={}
        for k,v in (request_sample or {}).items(): body[k]=1 if isinstance(v,(int,float)) else False if isinstance(v,bool) else ""
        body.update({"PAGE_NO":1,"PAGE_COUNT":1})
    return query,body
async def run(args):
    init_db(args.db); c=APIClient(args.db,args.base_url,args.rps,args.concurrency,args.timeout,1,None)
    with connect(args.db) as db: rows=[dict(x) for x in db.execute("SELECT * FROM endpoint_catalog WHERE enabled=1 AND safety_class IN ('read','read_filter','long_running_read') ORDER BY endpoint_key")]
    if args.endpoint: rows=[x for x in rows if x["endpoint_key"]==args.endpoint]
    if args.limit: rows=rows[:args.limit]
    async with c.open():
        for row in rows:
            key,method,path=row["endpoint_key"],row["method"],row["path"]
            try: params=json.loads(row.get("parameters_json") or "[]")
            except: params=[]
            try: request_sample=json.loads(row.get("request_schema_json") or "null")
            except: request_sample=None
            query,body=fixture(params,request_sample,method); timeout=args.long_timeout if row["safety_class"]=="long_running_read" else args.probe_timeout; started=time.monotonic(); status=None; message=None
            try:
                async with c.sem:
                    await c.rate.wait()
                    async with c.session.request(method,urljoin(args.base_url,path),params=query,json=body,timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                        status=resp.status; text=await resp.text(); latency=int((time.monotonic()-started)*1000)
                        if status in (200,201,202,204):
                            status_class="public_available"
                            try: payload=json.loads(text); await c.save_raw("probe:"+key,None,key,method,str(resp.url),query,body,status,payload)
                            except Exception: message="Public response was not JSON"
                        elif status in (401,403): status_class="requires_api_key"; await c.restriction(key,status,text[:1000])
                        elif status==404: status_class="not_found"
                        elif status>=500: status_class="server_error"
                        else: status_class="other_http_status"
                        message=message or text[:1000]
            except asyncio.TimeoutError: status_class="timeout"; latency=int((time.monotonic()-started)*1000); message=f"Probe exceeded {timeout}s"
            except Exception as exc: status_class="connection_or_protocol_error"; latency=int((time.monotonic()-started)*1000); message=str(exc)[:1000]
            with connect(args.db) as db:
                db.execute("INSERT OR REPLACE INTO endpoint_probe_results VALUES(?,?,?,?,?,?,?,?)",(key,status_class,status,latency,canonical(query),canonical(body),message,now()))
                db.execute("UPDATE endpoint_catalog SET access_status=?,last_probe_status=?,last_probed_at=? WHERE endpoint_key=?",(status_class,status,now(),key))
    report(args.db,Path(args.report_dir))
def report(db_path,out):
    out.mkdir(parents=True,exist_ok=True)
    with connect(db_path) as db: df=pd.read_sql_query("SELECT p.*,c.path,c.method,c.parameters_json,c.response_schema_json FROM endpoint_probe_results p JOIN endpoint_catalog c USING(endpoint_key) ORDER BY status_class,endpoint_key",db)
    df["api_key_unlocked_fields_json"]=df["endpoint_key"].map(lambda x:json.dumps(UNLOCKED_FIELDS.get(x,[]),ensure_ascii=False))
    df.to_csv(out/"endpoint_access_matrix.csv",index=False,encoding="utf-8-sig")
    for status,name in (("public_available","public_endpoints"),("requires_api_key","requires_api_key_endpoints"),("timeout","timeout_endpoints"),("not_found","not_found_endpoints"),("server_error","server_error_endpoints")):
        part=df[df.status_class==status]; part.to_csv(out/f"{name}.csv",index=False,encoding="utf-8-sig"); (out/f"{name}.json").write_text(part.to_json(orient="records",force_ascii=False,indent=2),encoding="utf-8")
    unsafe=[]
    with connect(db_path) as db: unsafe=pd.read_sql_query("SELECT endpoint_key,method,path,safety_class FROM endpoint_catalog WHERE safety_class='state_change_or_auth'",db)
    unsafe.to_csv(out/"not_probed_unsafe_endpoints.csv",index=False,encoding="utf-8-sig")
    with connect(db_path) as db: unprobed=pd.read_sql_query("SELECT endpoint_key,method,path,parameters_json,safety_class FROM endpoint_catalog WHERE enabled=1 AND endpoint_key NOT IN (SELECT endpoint_key FROM endpoint_probe_results)",db)
    unprobed.to_csv(out/"unprobed_safe_endpoints.csv",index=False,encoding="utf-8-sig")
def main():
    p=argparse.ArgumentParser(); p.add_argument("--db",default="pedigreeall_progress.db"); p.add_argument("--base-url",default=BASE_URL); p.add_argument("--rps",type=float,default=.5); p.add_argument("--concurrency",type=int,default=2); p.add_argument("--timeout",type=float,default=20); p.add_argument("--probe-timeout",type=float,default=12); p.add_argument("--long-timeout",type=float,default=45); p.add_argument("--limit",type=int,default=0); p.add_argument("--endpoint"); p.add_argument("--report-dir",default="reports/public_mode"); asyncio.run(run(p.parse_args()))
if __name__=="__main__": main()
