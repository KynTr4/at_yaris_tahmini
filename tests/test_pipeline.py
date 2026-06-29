import asyncio, hashlib, tempfile, unittest
from pathlib import Path
from discover_endpoints import split_signature
from discover_horses import link_horses, record, upsert
from normalize_data import normalize_entity
from pedigreeall_core import APIClient, canonical, connect, init_db, now

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.db=Path(self.tmp.name)/"test.db"; init_db(self.db)
    def tearDown(self): self.tmp.cleanup()
    def test_required_schema(self):
        required={"endpoint_catalog","discovered_horses","horse_profiles","horse_pedigrees","horse_races","race_program_entries","horse_statistics","horse_siblings","horse_progeny","horse_media","raw_api_responses","progress","errors","endpoint_probe_results","access_restrictions"}
        with connect(self.db) as db: actual={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue(required<=actual)
    def test_endpoint_signature(self):
        method,path,params=split_signature("GET Tjk/Get?p_iTjkId={p_iTjkId}")
        self.assertEqual((method,path),("GET","Tjk/Get")); self.assertEqual(params,["p_iTjkId"])
    def test_tjk_at_id_is_not_horse_id(self):
        r=record("tjk_list",{"TJK_AT_ID":99,"TJK_ID":7,"NAME":"ATA"})
        self.assertEqual(r["source_record_id"],"99"); self.assertEqual(r["tjk_id"],"7"); self.assertIsNone(r["horse_id"])
    def test_access_restriction_is_not_error(self):
        asyncio.run(APIClient(self.db).restriction("GET:HorseInfo/GetById",401,"denied"))
        with connect(self.db) as db:
            self.assertEqual(db.execute("SELECT http_status FROM access_restrictions WHERE endpoint_key='GET:HorseInfo/GetById'").fetchone()[0],401)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM errors").fetchone()[0],0)
    def test_exact_link(self):
        upsert(self.db,record("tjk_list",{"TJK_AT_ID":1,"TJK_ID":7,"NAME":"SAHIN","FATHER_NAME":"BABA","MOTHER_NAME":"ANNE"}))
        upsert(self.db,record("horse_filter_turkey",{"HORSE_ID":55,"HORSE_NAME":"SAHIN","FATHER_NAME":"BABA","MOTHER_NAME":"ANNE"},1,"Turkey"))
        link_horses(self.db)
        with connect(self.db) as db: row=db.execute("SELECT horse_id,verified FROM horse_links WHERE tjk_id='7'").fetchone()
        self.assertEqual(tuple(row),(55,1))
    def test_raw_normalization(self):
        entity="horse:55"; upsert(self.db,record("horse_filter_turkey",{"HORSE_ID":55,"HORSE_NAME":"ATA"},1,"Turkey"))
        payload=[{"TJK_ID":7,"NAME":"ATA","HORSE_TABLE":[{"ID":101,"TARIH":"01.01.2024","MESAFE":1200,"JOKEY":"J","GNY":"2.5"}]}]; raw=canonical(payload)
        with connect(self.db) as db: db.execute("INSERT INTO raw_api_responses(request_key,entity_key,endpoint_key,method,request_url,status_code,response_json,response_sha256,fetched_at) VALUES(?,?,?,?,?,?,?,?,?)",("k",entity,"GET:Tjk/Get","GET","x",200,raw,hashlib.sha256(raw.encode()).hexdigest(),now()))
        normalize_entity(self.db,entity,"7",55)
        with connect(self.db) as db:
            p=db.execute("SELECT name FROM horse_profiles WHERE horse_key=?",(entity,)).fetchone(); race=db.execute("SELECT distance,agf,jockey FROM horse_races WHERE horse_key=?",(entity,)).fetchone()
        self.assertEqual(p[0],"ATA"); self.assertEqual(race[0],1200); self.assertIsNone(race[1]); self.assertEqual(race[2],"J")

if __name__=="__main__": unittest.main()
