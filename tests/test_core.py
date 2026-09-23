import copy, json, tempfile, unittest, sqlite3, shutil, threading, urllib.request, urllib.error
from pathlib import Path
from unittest.mock import patch
from backend import core, service

class CoreTests(unittest.TestCase):
    def test_nonfinite_negative_bool(self):
        for x in [float('nan'),float('inf'),-1,True,None,'1']:
            with self.subTest(x=x),self.assertRaises(core.ValidationError):core.number(x,'x')
    def test_zero_valid(self):self.assertEqual(core.number(0,'x'),0)
    def test_paths(self):
        with self.assertRaises(core.ValidationError):core.relative_file(core.ROOT,'../not_permitted')
    def test_profile_region(self):
        with self.assertRaises(core.ValidationError):core.calculate_carbon({'Electricity':1},core.get_profile('CN-JX-2023'),'US-CO')
    def test_missing_carrier_not_zero(self):
        p=copy.deepcopy(core.get_profile('reference_scenario'));p['factors'].pop('Natural Gas')
        r=core.calculate_carbon({'Electricity':100,'Natural Gas':10},p,'US-CO')
        self.assertIsNone(r['operating_carbon_kg']);self.assertEqual(r['missing_carriers'],['Natural Gas'])
    def test_carbon_units(self):
        p=copy.deepcopy(core.get_profile('reference_scenario'));p['factors']['Electricity']['unit']='kgCO2/MWh'
        with self.assertRaises(core.ValidationError):core.calculate_carbon({'Electricity':100},p,'US-CO')
    def test_carbon_calculation(self):
        r=core.calculate_carbon({'Electricity':100,'Natural Gas':10},core.get_profile('reference_scenario'),'US-CO')
        self.assertEqual(r['operating_carbon_kg'],52);self.assertIsNone(r['ccer_issued_t'])
    def test_factor_invalidation(self):
        p=core.invalidation({'model':'a','factor':'x'},{'model':'a','factor':'y'})
        self.assertEqual(p['action'],'recalc_carbon');self.assertNotIn('energy',p['invalid']);self.assertEqual(p['energyplus_calls_executed'],0)
    def test_new_dependency_fails_closed(self):self.assertEqual(core.invalidation({}, {'unknown':'x'})['action'],'rerun_energyplus')
    def test_tampered_result_not_reused(self):self.assertEqual(core.invalidation({'result':'a'},{'result':'b'})['action'],'reject_and_restore_or_reparse')
    def test_display_only(self):self.assertEqual(core.invalidation({'display':1},{'display':2})['invalid'],['report'])
    def test_unchanged(self):self.assertEqual(core.invalidation({'model':'x'},{'model':'x'})['action'],'reuse')
    def test_cost_missing(self):self.assertIsNone(core.cost_scenario({'Electricity':100},{},0,20,.03)['npv_total_cost_yuan'])
    def test_cost_math(self):self.assertEqual(core.cost_scenario({'Electricity':100},{'Electricity':.5},1000,2,0)['npv_total_cost_yuan'],1100)
    def test_cost_years(self):
        with self.assertRaises(core.ValidationError):core.cost_scenario({}, {},0,1.2,0)
    def test_credit_not_issued(self):self.assertIsNone(core.carbon_value_scenario(10,50,100,100,'假设')['issued_credits_t'])
    def test_credit_needs_basis(self):
        with self.assertRaises(core.ValidationError):core.carbon_value_scenario(10,50,100,100,'')
    def test_gap_priority(self):self.assertEqual(core.evidence_gaps([{'name':'墙','status':'missing','decision_sensitive':True}])['gaps'][0]['priority'],'high')
    def test_measured_needs_source(self):
        with self.assertRaises(core.ValidationError):core.evidence_gaps([{'name':'墙','status':'measured'}])
    def test_missing_sql(self):
        with self.assertRaises(core.ValidationError):core.parse_sql(core.ROOT/'absent.sql')
    def test_no_mock_fallback(self):
        with tempfile.TemporaryDirectory() as td,patch.object(core,'engine_path',side_effect=core.ValidationError('missing engine')):
            r=core.run_simulation('reference_5zone','baseline','reference_scenario',Path(td)/'run_missing')
            self.assertEqual(r['status'],'failed');self.assertIsNone(r['metrics']);self.assertEqual(core.read_json(Path(td)/'run_missing/manifest.json')['engine_calls_executed'],0)

class NativeEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        f=core.ROOT/'validation/reference_comparison.json'
        if not f.exists():raise unittest.SkipTest('Run scripts/run_reference.py first')
        cls.summary=core.read_json(f);cls.source=core.ROOT/'runs'/cls.summary['baseline_run_id']
    def test_native_annual(self):
        m=core.parse_sql(self.source/'output/eplusout.sql')
        self.assertEqual(m['annual_days'],365);self.assertGreater(m['annual_energy_kwh'],0);self.assertAlmostEqual(m['area_m2'],927.2)
    def test_current_comparison(self):
        r=core.compare_runs([core.ROOT/'runs'/x['run_id'] for x in self.summary['results']])
        self.assertEqual(len(r['results']),3)
    def test_sql_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/self.source.name;shutil.copytree(self.source,dest)
            with (dest/'output/eplusout.sql').open('ab') as f:f.write(b'tamper')
            with self.assertRaises(core.ValidationError):core.read_validated(dest,False)
    def test_binding(self):
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/'run_different';shutil.copytree(self.source,dest)
            with self.assertRaises(core.ValidationError):core.read_validated(dest,False)
    def test_short_period_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            sql=Path(td)/'x.sql';shutil.copy2(self.source/'output/eplusout.sql',sql)
            with sqlite3.connect(sql) as c:c.execute('DELETE FROM Time WHERE Month=12')
            c.close()
            with self.assertRaises(core.ValidationError):core.parse_sql(sql)
    def test_recarbon_no_engine_call(self):
        with tempfile.TemporaryDirectory() as td,patch.object(core.subprocess,'run',side_effect=AssertionError('must not run engine')):
            dest=Path(td)/'run_recarbon';r=core.recalculate_carbon(self.source,dest,'none')
            self.assertEqual(r['metrics'],self.summary['results'][0]['metrics']);self.assertIsNone(r['carbon']['operating_carbon_kg'])
            self.assertEqual(core.read_json(dest/'manifest.json')['engine_calls_executed'],0);core.read_validated(dest)

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=service.ThreadingHTTPServer(('127.0.0.1',0),service.Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def test_health(self):
        with urllib.request.urlopen(self.url+'/api/health') as r:self.assertEqual(r.status,200)
    def test_origin_reject(self):
        req=urllib.request.Request(self.url+'/api/health',headers={'Origin':'https://evil.example'})
        with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
        self.assertEqual(e.exception.code,400)
    def test_nan_reject(self):
        req=urllib.request.Request(self.url+'/api/cost',data=b'{"x":NaN}',headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
        self.assertEqual(e.exception.code,400)
    def test_unknown(self):
        with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(self.url+'/api/absent')
        self.assertEqual(e.exception.code,404)
if __name__=='__main__':unittest.main(verbosity=2)
