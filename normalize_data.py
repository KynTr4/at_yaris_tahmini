"""Normalize stored raw responses into the relational warehouse."""
from __future__ import annotations
import argparse, html, json, re
from datetime import date
from pedigreeall_core import canonical, connect, init_db, now, unwrap

def first(v):
    v=unwrap(v)
    if isinstance(v,list) and v and isinstance(v[0],dict): return v[0]
    return v if isinstance(v,dict) else {}
def n(v):
    try:
        value=int(v) if v not in (None,"") else None
        return value if value is not None and value>=0 else None
    except: return None
def num(v):
    try:
        value=float(re.sub(r"[^0-9,.-]","",str(v)).replace(".","").replace(",",".")) if v not in (None,"") else None
        return value if value is not None and value>=0 else None
    except: return None
def txt(v): return html.unescape(str(v)).strip() if v not in (None,"") else None
def load_raw(db,entity):
    out={}
    for r in db.execute("SELECT endpoint_key,response_json FROM raw_api_responses WHERE entity_key=? ORDER BY fetched_at",(entity,)):
        try: out[r["endpoint_key"]]=json.loads(r["response_json"])
        except: pass
    return out
def recursive_horses(obj):
    found=[]
    if isinstance(obj,dict):
        if "HORSE_NAME" in obj or ("HORSE_ID" in obj and "NAME" in obj): found.append(obj)
        for v in obj.values(): found.extend(recursive_horses(v))
    elif isinstance(obj,list):
        for v in obj: found.extend(recursive_horses(v))
    return found

def normalize_entity(db_path,entity_key,tjk_id=None,horse_id=None):
    init_db(db_path)
    with connect(db_path) as db:
        raw=load_raw(db,entity_key); tjk=first(raw.get("GET:Tjk/Get")); tp=first(raw.get("GET:Tjk/GetHorseFromTjk")); hp=first(raw.get("GET:HorseInfo/GetById"))
        disc=db.execute("SELECT * FROM discovered_horses WHERE (horse_id=? AND ? IS NOT NULL) OR (tjk_id=? AND ? IS NOT NULL) ORDER BY horse_id DESC LIMIT 1",(horse_id,horse_id,tjk_id,tjk_id)).fetchone(); d=dict(disc) if disc else {}
        candidate_name=d.get("name") or hp.get("HORSE_NAME") or tjk.get("NAME") or tp.get("HORSE_NAME")
        if not candidate_name:
            for table in ("horse_profiles","horse_races","horse_pedigrees","horse_siblings","horse_progeny","horse_media"): db.execute(f"DELETE FROM {table} WHERE horse_key=?",(entity_key,))
            return
        birth=d.get("birth_date") or hp.get("HORSE_BIRTH_DATE_TEXT") or tjk.get("BIRTH_DATE") or tp.get("BIRTH_DATE_TEXT"); years=re.findall(r"(?:18|19|20)\d{2}",str(birth or "")); year=n(years[-1]) if years else None
        sex=hp.get("SEX_OBJECT") or {}; unsupported={x:"not_supported_by_api" for x in ("health_records","veterinary_records","vaccinations","nutrition","sleep","mental_analysis","stress_score","market_value","private_breeding_records")}
        p={"horse_key":entity_key,"tjk_id":str(tjk_id) if tjk_id else None,"horse_id":horse_id,"name":txt(candidate_name),
          "birth_date":birth,"birth_year":year,"age":date.today().year-year if year else n(d.get("age_text")),"sex":sex.get("SEX_TR") or sex.get("SEX_EN") or d.get("sex"),"color":hp.get("COLOR_TEXT"),
          "country":txt(d.get("country_name") or hp.get("ICON")),"father_id":n(d.get("father_id") or hp.get("FATHER_ID")),"father_name":txt(d.get("father_name") or hp.get("FATHER_NAME") or tjk.get("FATHER_NAME")),
          "mother_id":n(d.get("mother_id") or hp.get("MOTHER_ID")),"mother_name":txt(d.get("mother_name") or hp.get("MOTHER_NAME") or tjk.get("MOTHER_NAME")),"broodmare_sire":txt(hp.get("BM_SIRE_NAME") or tjk.get("BM_SIRE_NAME")),
          "owner":txt(hp.get("OWNER") or d.get("owner")),"breeder":txt(hp.get("BREEDER") or d.get("breeder")),"trainer":txt(hp.get("COACH") or d.get("trainer")),"is_dead":n(hp.get("IS_DEAD")),
          "earnings":num(hp.get("EARN") or tp.get("EARN") or d.get("earnings")),"currency_id":n(hp.get("EARN_CURRENCY_ID")),"starts":n(hp.get("START_COUNT") or tp.get("TOTAL") or d.get("starts")),
          "wins":n(hp.get("FIRST") or tp.get("FIRST") or d.get("wins")),"seconds":n(hp.get("SECOND") or tp.get("SECOND") or d.get("seconds")),"thirds":n(hp.get("THIRD") or tp.get("THIRD") or d.get("thirds")),"fourths":n(hp.get("FOURTH") or tp.get("FOURTH") or d.get("fourths")),
          "handicap":num(tp.get("HANDIKAP") or tjk.get("HANDIKAP")),"group_g1":n(tp.get("G1")),"group_g2":n(tp.get("G2")),"group_g3":n(tp.get("G3")),"unsupported_fields_json":canonical(unsupported),"extra_fields_json":canonical({"horse_info":hp,"tjk_profile":tp,"discovery":json.loads(d.get("discovery_payload_json") or "{}")}),"updated_at":now()}
        cols=list(p); db.execute(f"INSERT OR REPLACE INTO horse_profiles({','.join(cols)}) VALUES({','.join('?' for _ in cols)})",[p[x] for x in cols])
        races=tjk.get("HORSE_TABLE") or []
        for idx,r in enumerate(races):
            if not isinstance(r,dict): continue
            rid=str(r.get("ID") or f"{r.get('TARIH')}:{r.get('SEHIR')}:{r.get('MESAFE')}:{idx}")
            vals=(entity_key,rid,r.get("TARIH"),r.get("SEHIR"),n(r.get("MESAFE")),r.get("PIST"),r.get("K_CINS") or r.get("GRUP"),r.get("S"),r.get("DERECE"),None,r.get("GNY"),r.get("JOKEY"),r.get("ANTRENOR"),r.get("IKRAMIYE"),r.get("KG"),r.get("TAKI"),r.get("ST"),r.get("HP"),r.get("VIDEO"),r.get("FOTO"),canonical(r))
            db.execute("INSERT OR REPLACE INTO horse_races VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",vals)
        ped=unwrap(raw.get("GET:Pedigree/GetPedigree") or {}); cells=ped.get("PEDIGREE_CELL_LIST",[]) if isinstance(ped,dict) else []
        for generation,row in enumerate(cells):
            if not isinstance(row,list): continue
            for pos,a in enumerate(row):
                if not isinstance(a,dict): continue
                fam=a.get("FAMILY_OBJECT") or {}; db.execute("INSERT OR REPLACE INTO horse_pedigrees VALUES(?,?,?,?,?,?,?,?,?,?)",(entity_key,generation,pos,n(a.get("HORSE_ID")),a.get("HORSE_NAME"),n(a.get("FATHER_ID")),n(a.get("MOTHER_ID")),n(a.get("IS_SIRE")),fam.get("FAMILY_TEXT"),canonical(a)))
        for endpoint,rel in (("GET:Sibling/GetSiblingFromMother","maternal"),("GET:Sibling/GetSiblingFromFather","paternal"),("GET:Sibling/GetSiblingFromBroodmareSire","broodmare_sire")):
            seen=set()
            for s in recursive_horses(unwrap(raw.get(endpoint) or {})):
                sid=n(s.get("HORSE_ID")); name=s.get("HORSE_NAME") or s.get("NAME"); key=(sid,name)
                if key in seen or (sid==horse_id): continue
                seen.add(key); db.execute("INSERT OR REPLACE INTO horse_siblings VALUES(?,?,?,?,?)",(entity_key,rel,sid,name,canonical(s)))
        seen=set()
        for x in recursive_horses(unwrap(raw.get("GET:Progeny/GetProgeny") or {})):
            xid=n(x.get("HORSE_ID")); name=x.get("HORSE_NAME") or x.get("NAME"); key=(xid,name)
            if key in seen or xid==horse_id: continue
            seen.add(key); db.execute("INSERT OR REPLACE INTO horse_progeny VALUES(?,?,?,?,?,?,?,?)",(entity_key,xid,name,num(x.get("EARN")),n(x.get("START_COUNT")),n(x.get("FIRST")),canonical({k:x.get(k) for k in ("SECOND","THIRD","FOURTH","POINT","EFFECT_POINT")}),canonical(x)))
        media=unwrap(raw.get("GET:ImageInfo/GetById") or {})
        for item in media if isinstance(media,list) else [media]:
            if not isinstance(item,dict): continue
            for typ,url in [("primary",item.get("IMAGE"))]+[("gallery",u) for u in item.get("IMAGE_LIST",[])]:
                if url: db.execute("INSERT OR REPLACE INTO horse_media VALUES(?,?,?,?,?)",(entity_key,typ,str(url),item.get("INFO"),"GET:ImageInfo/GetById"))
        for typ,url in (("profile",hp.get("IMAGE")),("father",hp.get("FATHER_IMAGE")),("mother",hp.get("MOTHER_IMAGE")),("broodmare_sire",hp.get("BM_SIRE_IMAGE"))):
            if url: db.execute("INSERT OR REPLACE INTO horse_media VALUES(?,?,?,?,?)",(entity_key,typ,str(url),None,"GET:HorseInfo/GetById"))

def main():
    p=argparse.ArgumentParser(); p.add_argument("--db",default="pedigreeall_progress.db"); a=p.parse_args(); init_db(a.db)
    with connect(a.db) as db: entities=[dict(x) for x in db.execute("SELECT DISTINCT entity_key FROM raw_api_responses WHERE entity_key LIKE 'horse:%' OR entity_key LIKE 'tjk:%'")]
    for e in entities:
        key=e["entity_key"]; hid=n(key.split(":",1)[1]) if key.startswith("horse:") else None; tid=key.split(":",1)[1] if key.startswith("tjk:") else None; normalize_entity(a.db,key,tid,hid)
    print(f"Normalized {len(entities)} entities")
if __name__=="__main__": main()
