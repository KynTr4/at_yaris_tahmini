"""Automatically catalog every endpoint exposed by the official Help index."""
from __future__ import annotations
import argparse, asyncio, html, json, logging, re
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urljoin, urlparse
from pedigreeall_core import APIClient, BASE_URL, connect, init_db, now

SAFE_POST={"Horse/GetFilter","HorseInfo/GetFilter","HorseRace/GetFilter"}
UNSAFE_WORDS=re.compile(r"(^|/)(Add|Insert|Update|Delete|Approve|Reject|Activate|Deactivate|Login|Logout|Pay|Order|Upload|Make|Create|Generate|Set|Save|Send|Remove|Import)",re.I)
def classify(method,path):
    if UNSAFE_WORDS.search(path): return "state_change_or_auth",0
    if method=="GET": return ("long_running_read" if path=="Tjk/getHorseListFromTjk" else "read"),1
    if method=="POST" and path in SAFE_POST: return "read_filter",1
    return "state_change_or_auth",0

class HelpParser(HTMLParser):
    def __init__(self): super().__init__(); self.current=None; self.links=[]
    def handle_starttag(self,tag,attrs):
        href=dict(attrs).get("href")
        if tag=="a" and href and href.startswith("/Help/Api/"): self.current=[href,[]]
    def handle_data(self,data):
        if self.current: self.current[1].append(data)
    def handle_endtag(self,tag):
        if tag=="a" and self.current:
            self.links.append((self.current[0],html.unescape(" ".join(self.current[1])).strip())); self.current=None

class DetailParser(HTMLParser):
    def __init__(self): super().__init__(); self.in_pre=False; self.in_h1=False; self.buf=[]; self.pres=[]; self.title=""
    def handle_starttag(self,tag,attrs):
        if tag=="pre": self.in_pre=True; self.buf=[]
        if tag=="h1": self.in_h1=True; self.buf=[]
    def handle_data(self,data):
        if self.in_pre or self.in_h1: self.buf.append(data)
    def handle_endtag(self,tag):
        if tag=="pre" and self.in_pre: self.pres.append(html.unescape("".join(self.buf)).strip()); self.in_pre=False
        if tag=="h1" and self.in_h1: self.title=html.unescape("".join(self.buf)).strip(); self.in_h1=False

def split_signature(text):
    method,route=(text.split(None,1)+[""])[:2]; parsed=urlparse(route); params=[k for k,_ in parse_qsl(parsed.query,keep_blank_values=True)]
    return method.upper(),parsed.path,params

def json_samples(pres):
    out=[]
    for p in pres:
        try: out.append(json.loads(p))
        except Exception: pass
    return out

async def discover(args):
    init_db(args.db); client=APIClient(args.db,args.base_url,args.rps,args.concurrency,args.timeout,args.retries,args.api_key)
    async with client.open():
        await client.rate.wait(); index=await client.session.get(urljoin(args.base_url,"Help")); index.raise_for_status(); parser=HelpParser(); parser.feed(await index.text())
        with connect(args.db) as db:
            for href,text in parser.links:
                method,path,query_params=split_signature(text); safety,enabled=classify(method,path); key=f"{method}:{path}"
                db.execute("""INSERT INTO endpoint_catalog(endpoint_key,method,path,parameters_json,description,help_url,safety_class,verified_at,enabled)
                VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(endpoint_key) DO UPDATE SET method=excluded.method,path=excluded.path,parameters_json=excluded.parameters_json,description=excluded.description,help_url=excluded.help_url,safety_class=excluded.safety_class,enabled=excluded.enabled""",
                (key,method,path,json.dumps(query_params),text,urljoin(args.base_url,href),safety,now(),enabled))
        if args.index_only:
            with connect(args.db) as db: print(json.dumps({"catalogued_from_index":db.execute("SELECT COUNT(*) FROM endpoint_catalog").fetchone()[0]},indent=2))
            return
        for href,text in parser.links:
            try:
                method,path,query_params=split_signature(text); await client.rate.wait(); response=await client.session.get(urljoin(args.base_url,href)); response.raise_for_status()
                detail=DetailParser(); detail.feed(await response.text()); samples=json_samples(detail.pres)
                request_sample=samples[0] if method=="POST" and len(samples)>1 else None; response_sample=samples[-1] if samples else None
                params=query_params+(list(request_sample) if isinstance(request_sample,dict) else [])
                safety,enabled=classify(method,path); key=f"{method}:{path}"
                with connect(args.db) as db: db.execute("""INSERT INTO endpoint_catalog(endpoint_key,method,path,parameters_json,request_schema_json,response_schema_json,description,help_url,safety_class,verified_at,enabled)
                VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(endpoint_key) DO UPDATE SET parameters_json=excluded.parameters_json,request_schema_json=excluded.request_schema_json,response_schema_json=excluded.response_schema_json,description=excluded.description,help_url=excluded.help_url,safety_class=excluded.safety_class,verified_at=excluded.verified_at,enabled=excluded.enabled""",(key,method,path,json.dumps(params),json.dumps(request_sample,ensure_ascii=False),json.dumps(response_sample,ensure_ascii=False),detail.title,urljoin(args.base_url,href),safety,now(),enabled))
            except Exception as exc:
                await client.error("endpoint_discovery",None,href,exc,1)
    with connect(args.db) as db: print(json.dumps({"catalogued":db.execute("SELECT COUNT(*) FROM endpoint_catalog").fetchone()[0],"enabled":db.execute("SELECT COUNT(*) FROM endpoint_catalog WHERE enabled=1").fetchone()[0]},indent=2))

def main():
    p=argparse.ArgumentParser(); p.add_argument("--db",default="pedigreeall_progress.db"); p.add_argument("--base-url",default=BASE_URL); p.add_argument("--rps",type=float,default=1); p.add_argument("--concurrency",type=int,default=3); p.add_argument("--timeout",type=float,default=45); p.add_argument("--retries",type=int,default=5); p.add_argument("--api-key"); p.add_argument("--index-only",action="store_true"); a=p.parse_args(); logging.basicConfig(level=logging.INFO); asyncio.run(discover(a))
if __name__=="__main__": main()
