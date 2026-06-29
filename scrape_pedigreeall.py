"""Enterprise, resumable collector for every discovered Turkish horse."""
from __future__ import annotations
import argparse, asyncio, json, logging
from pedigreeall_core import APIClient, BASE_URL, connect, init_db
from normalize_data import normalize_entity
from tqdm import tqdm

PUBLIC_ONLY_MODE=True

class PedigreeAllScraper:
    def __init__(self,db="pedigreeall_progress.db",base_url=BASE_URL,rps=.75,concurrency=3,timeout=60,retries=5,api_key=None):
        self.db=db; init_db(db); self.client=APIClient(db,base_url,rps,concurrency,timeout,retries,api_key)
    def entities(self,limit=0):
        with connect(self.db) as db:
            linked=[dict(x) for x in db.execute("SELECT horse_id,tjk_id FROM horse_links WHERE verified=1 AND horse_id IS NOT NULL")]
            linked_h={x["horse_id"] for x in linked}; linked_t={x["tjk_id"] for x in linked}; out=[(f"horse:{x['horse_id']}",x["tjk_id"],x["horse_id"]) for x in linked]
            out += [(f"horse:{x['horse_id']}",None,x["horse_id"]) for x in db.execute("SELECT DISTINCT horse_id FROM discovered_horses WHERE horse_id IS NOT NULL") if x["horse_id"] not in linked_h]
            out += [(f"tjk:{x['tjk_id']}",x["tjk_id"],None) for x in db.execute("SELECT DISTINCT tjk_id FROM discovered_horses WHERE tjk_id IS NOT NULL") if x["tjk_id"] not in linked_t]
        return out[:limit] if limit else out
    async def call(self,key,path,entity,params,force=False):
        with connect(self.db) as db: restricted=db.execute("SELECT 1 FROM access_restrictions WHERE endpoint_key=?",(key,)).fetchone()
        if PUBLIC_ONLY_MODE and restricted: return None
        if not force:
            with connect(self.db) as db: cached=db.execute("SELECT response_json FROM raw_api_responses WHERE entity_key=? AND endpoint_key=? AND status_code BETWEEN 200 AND 299 ORDER BY fetched_at DESC LIMIT 1",(entity,key)).fetchone()
            if cached:
                try: return json.loads(cached[0])
                except Exception: pass
        return await self.client.request(key,path,params=params,entity_key=entity)
    async def process_horse(self,entity,tjk_id,horse_id,force=False):
        with connect(self.db) as db:
            done=db.execute("SELECT status FROM progress WHERE work_type='collect' AND entity_key=? AND endpoint_key='all'",(entity,)).fetchone()
        if done and done[0]=="completed" and not force: return "skipped"
        await self.client.checkpoint("collect",entity,"all","running")
        jobs=[]
        if tjk_id:
            jobs += [self.call("GET:Tjk/Get","Tjk/Get",entity,{"p_iTjkId":tjk_id},force),self.call("GET:Tjk/GetHorseFromTjk","Tjk/GetHorseFromTjk",entity,{"p_iTjkId":tjk_id},force)]
        if horse_id:
            specs=[("GET:HorseInfo/GetById","HorseInfo/GetById",{"p_iId":horse_id}),
             ("GET:Pedigree/GetPedigree","Pedigree/GetPedigree",{"p_iGenerationCount":5,"p_iFirstId":horse_id,"p_iSecondId":0}),
             ("GET:Sibling/GetSiblingFromMother","Sibling/GetSiblingFromMother",{"p_iHorseId":horse_id}),
             ("GET:Sibling/GetSiblingFromFather","Sibling/GetSiblingFromFather",{"p_iHorseId":horse_id}),
             ("GET:Sibling/GetSiblingFromBroodmareSire","Sibling/GetSiblingFromBroodmareSire",{"p_iHorseId":horse_id}),
             ("GET:Progeny/GetProgeny","Progeny/GetProgeny",{"p_iHorseId":horse_id}),
             ("GET:ImageInfo/GetById","ImageInfo/GetById",{"p_iHorseId":horse_id}),
             ("GET:FamilySuccess/Get","FamilySuccess/Get",{"p_iHorseId":horse_id})]
            jobs += [self.call(k,p,entity,q,force) for k,p,q in specs]
        results=await asyncio.gather(*jobs,return_exceptions=True); failed=[str(x) for x in results if isinstance(x,Exception)]
        try: normalize_entity(self.db,entity,tjk_id,horse_id)
        except Exception as exc: failed.append(f"normalize: {exc}"); await self.client.error("normalize",entity,"all",exc,1)
        status="completed" if not failed else "partial"; await self.client.checkpoint("collect",entity,"all",status,message=" | ".join(failed)[:4000] or None); return status
    async def process_all_horses(self,limit=0,batch_size=100,force=False):
        entities=self.entities(limit); counts={}
        async with self.client.open():
            for start in tqdm(range(0,len(entities),batch_size),desc="Horse batches"):
                chunk=entities[start:start+batch_size]; results=await asyncio.gather(*(self.process_horse(*x,force) for x in chunk),return_exceptions=True)
                for r in results: counts[str(r) if isinstance(r,Exception) else r]=counts.get(str(r) if isinstance(r,Exception) else r,0)+1
        return counts

async def run(a):
    s=PedigreeAllScraper(a.db,a.base_url,a.rps,a.concurrency,a.timeout,a.retries,a.api_key); print(json.dumps(await s.process_all_horses(a.limit,a.batch_size,a.force),ensure_ascii=False,indent=2))
def main():
    p=argparse.ArgumentParser(); p.add_argument("--db",default="pedigreeall_progress.db"); p.add_argument("--base-url",default=BASE_URL); p.add_argument("--api-key"); p.add_argument("--rps",type=float,default=.75); p.add_argument("--concurrency",type=int,default=3); p.add_argument("--timeout",type=float,default=60); p.add_argument("--retries",type=int,default=5); p.add_argument("--batch-size",type=int,default=100); p.add_argument("--limit",type=int,default=0); p.add_argument("--force",action="store_true"); a=p.parse_args(); logging.basicConfig(filename="pedigreeall.log",level=logging.INFO); asyncio.run(run(a))
if __name__=="__main__": main()
