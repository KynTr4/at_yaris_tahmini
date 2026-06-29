"""Build analytical datasets and data-quality reports from normalized tables."""
from __future__ import annotations
import argparse, json, sqlite3
from pathlib import Path
import pandas as pd
import pyarrow as pa, pyarrow.parquet as pq
from pedigreeall_core import connect, init_db, now

TABLES=("discovered_horses","horse_profiles","horse_pedigrees","horse_races","race_program_entries","horse_statistics","horse_siblings","horse_progeny","horse_media","endpoint_probe_results","access_restrictions","errors")
def export_table(db_path,table,out,chunksize):
    csv=out/f"{table}.csv"; parquet=out/f"{table}.parquet"; writer=None; rows=0
    for old in (csv,parquet):
        if old.exists(): old.unlink()
    with sqlite3.connect(db_path) as db:
        decl={r[1]:(r[2] or "TEXT").upper() for r in db.execute(f"PRAGMA table_info({table})")}
        schema=pa.schema([(c,pa.int64() if "INT" in typ else pa.float64() if any(x in typ for x in ("REAL","FLOAT","DOUBLE")) else pa.string()) for c,typ in decl.items()])
        for part_no,df in enumerate(pd.read_sql_query(f"SELECT * FROM {table}",db,chunksize=chunksize)):
            df.to_csv(csv,mode="w" if part_no==0 else "a",header=part_no==0,index=False,encoding="utf-8-sig"); rows+=len(df)
            t=pa.Table.from_pandas(df,schema=schema,preserve_index=False,safe=False)
            if writer is None: writer=pq.ParquetWriter(parquet,t.schema,compression="zstd")
            writer.write_table(t)
    if writer: writer.close()
    elif not csv.exists(): pd.DataFrame().to_csv(csv,index=False)
    return rows
def stats(g,col):
    if col not in g: return {}
    out={}
    for k,x in g.dropna(subset=[col]).groupby(col): out[str(k)]={"starts":len(x),"wins":int((pd.to_numeric(x["finish"],errors="coerce")==1).sum()),"prize_known":int(x["prize"].notna().sum())}
    return out
def update_statistics(db_path):
    with sqlite3.connect(db_path) as db: races=pd.read_sql_query("SELECT * FROM horse_races",db)
    if races.empty: return 0
    races["parsed_date"]=pd.to_datetime(races["race_date"],errors="coerce",dayfirst=True); m=races["parsed_date"].dt.month
    races["season"]=m.map({12:"winter",1:"winter",2:"winter",3:"spring",4:"spring",5:"spring",6:"summer",7:"summer",8:"summer",9:"autumn",10:"autumn",11:"autumn"})
    with connect(db_path) as db:
        for key,g in races.groupby("horse_key"):
            profile=db.execute("SELECT starts,wins,seconds,thirds,fourths,earnings,group_g1,group_g2,group_g3 FROM horse_profiles WHERE horse_key=?",(key,)).fetchone(); p=list(profile) if profile else [None]*9
            vals=(key,*p,json.dumps(stats(g,"surface"),ensure_ascii=False),json.dumps(stats(g,"distance"),ensure_ascii=False),json.dumps(stats(g,"season"),ensure_ascii=False),json.dumps(stats(g,"jockey"),ensure_ascii=False),json.dumps(stats(g,"trainer"),ensure_ascii=False),now())
            db.execute("INSERT OR REPLACE INTO horse_statistics VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",vals)
    return races["horse_key"].nunique()
def quality(db_path,out):
    with sqlite3.connect(db_path) as db:
        profile=pd.read_sql_query("SELECT * FROM horse_profiles",db); progress=pd.read_sql_query("SELECT status,COUNT(*) count FROM progress GROUP BY status",db); errors=pd.read_sql_query("SELECT endpoint_key,COUNT(*) count FROM errors GROUP BY endpoint_key ORDER BY count DESC",db)
        counts={t:db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES[:-1]}
        discovered=db.execute("SELECT COUNT(DISTINCT COALESCE('h:'||horse_id,'t:'||tjk_id,source||':'||source_record_id)) FROM discovered_horses").fetchone()[0]
        entities=db.execute("SELECT COUNT(*) FROM horse_profiles").fetchone()[0]
        probes=dict(db.execute("SELECT status_class,COUNT(*) FROM endpoint_probe_results GROUP BY status_class").fetchall()); catalog_total=db.execute("SELECT COUNT(*) FROM endpoint_catalog").fetchone()[0]; safe_total=db.execute("SELECT COUNT(*) FROM endpoint_catalog WHERE enabled=1").fetchone()[0]
    supported=[c for c in profile.columns if c not in ("unsupported_fields_json","extra_fields_json","updated_at")]
    missing=[]
    for c in supported:
        mask=profile[c].isna()|profile[c].astype(str).str.strip().isin(("","not_available")); missing.append({"field":c,"missing":int(mask.sum()),"missing_pct":round(mask.mean()*100,2) if len(mask) else 0})
    pd.DataFrame(missing).sort_values("missing_pct",ascending=False).to_csv(out/"missing_fields.csv",index=False,encoding="utf-8-sig"); errors.to_csv(out/"endpoint_errors.csv",index=False,encoding="utf-8-sig")
    safe_probed=sum(probes.values()); public=probes.get("public_available",0)
    coverage={"catalogued_endpoints":catalog_total,"safe_endpoints_probed_pct":round(100*safe_probed/safe_total,2) if safe_total else 0,"endpoint_public_pct_of_probed":round(100*public/safe_probed,2) if safe_probed else 0,"discovered_entities_with_profile_pct":round(100*entities/discovered,2) if discovered else 0}
    with sqlite3.connect(db_path) as db:
        for table,label in (("horse_races","races"),("horse_pedigrees","pedigree"),("horse_siblings","siblings"),("horse_progeny","progeny"),("horse_media","media")):
            have=db.execute(f"SELECT COUNT(DISTINCT horse_key) FROM {table}").fetchone()[0]; coverage[f"profiles_with_{label}_pct"]=round(100*have/max(1,entities),2)
    report={"mode":"public_only_partial_discovery","table_counts":counts,"endpoint_access_counts":probes,"coverage":coverage,"progress":dict(zip(progress.get("status",[]),progress.get("count",[]))),"profile_quality_pct":round(100-pd.DataFrame(missing)["missing_pct"].mean(),2) if len(profile) and missing else 0,"unsupported_fields":["health_records","veterinary_records","vaccinations","nutrition","sleep","mental_analysis","stress_score","market_value","private_breeding_records"]}
    (out/"data_quality_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8"); return report
def main():
    p=argparse.ArgumentParser(); p.add_argument("--db",default="pedigreeall_progress.db"); p.add_argument("--output",default="lake/analytics"); p.add_argument("--chunksize",type=int,default=100_000); a=p.parse_args(); init_db(a.db); out=Path(a.output); out.mkdir(parents=True,exist_ok=True); update_statistics(a.db); exports={t:export_table(a.db,t,out,a.chunksize) for t in TABLES}; print(json.dumps({"exports":exports,"quality":quality(a.db,out)},ensure_ascii=False,indent=2))
if __name__=="__main__": main()
