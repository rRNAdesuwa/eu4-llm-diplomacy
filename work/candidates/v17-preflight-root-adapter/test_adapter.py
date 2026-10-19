"""Cold-process, unmocked disk-build import regression; no actual case or log."""
import importlib.util,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import adapter as a
class ImportTests(unittest.TestCase):
 def run_child(self,code):
  result=subprocess.run([sys.executable,'-B','-c',code],cwd=a.ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
  self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'));return json.loads(result.stdout)
 def test_legacy_cold_phase_fails_on_mirror_default_root(self):
  result=self.run_child("import importlib.util,json,tempfile;from pathlib import Path;p=Path('work/candidates/v17-acceptance-experiment-review/reviewer.py').resolve();s=importlib.util.spec_from_file_location('old_review',p);r=importlib.util.module_from_spec(s);s.loader.exec_module(r);from tools import verify_diplomacy_lifecycle_v17 as life;d=Path(tempfile.gettempdir())/'eu4-nonexistent-preflight-test';v=life.verify_phase('lifecycle',d/'research-1375.jsonl',63500,d/'before-never-created.json',d/'after-never-created.json',r.ROOT/'work/runtime/native1375-v17/build.json');print(json.dumps({'root':str(r.lab.ROOT),'errors':v['errors'],'status':v['status']}))")
  self.assertEqual(result['status'],'failed');self.assertIn('v17-acceptance-pin-review',result['root']);self.assertTrue(any('offered-fleet-ai-response' in x for x in result['errors']))
 def test_formal_cold_phase_passes_real_build_then_rejects_missing_diagnostic(self):
  result=self.run_child("import sys,json,tempfile;from pathlib import Path;sys.path.insert(0,str(Path('work/candidates/v17-preflight-root-adapter').resolve()));import adapter;a,r,modules=adapter.configured();life=modules['tools.verify_diplomacy_lifecycle_v17'];d=Path(tempfile.gettempdir())/'eu4-nonexistent-preflight-test';v=life.verify_phase('lifecycle',d/'research-1375.jsonl',63500,d/'before-never-created.json',d/'after-never-created.json',adapter.BUILD);print(json.dumps({'root':str(r.lab.ROOT),'errors':v['errors'],'status':v['status'],'origin':str(life.__file__)}))")
  self.assertEqual(result['status'],'failed');self.assertEqual(Path(result['root']),a.ROOT);self.assertTrue(any('before-never-created.json' in x for x in result['errors']));self.assertFalse(any('offered-fleet-ai-response' in x for x in result['errors']))
 def test_preexisting_mirror_module_is_rejected_not_replaced(self):
  result=self.run_child("import sys,importlib.util,json;from pathlib import Path;p=Path('work/candidates/v17-acceptance-experiment-review/reviewer.py').resolve();s=importlib.util.spec_from_file_location('old_review',p);r=importlib.util.module_from_spec(s);s.loader.exec_module(r);sys.path.insert(0,str(Path('work/candidates/v17-preflight-root-adapter').resolve()));import adapter\ntry:adapter.configured();result={'accepted':True}\nexcept ValueError as e:result={'accepted':False,'error':str(e)}\nprint(json.dumps(result))")
  self.assertFalse(result['accepted']);self.assertIn('Nonformal cached module',result['error'])
 def test_preload_files_identical_to_reviewed_mirror(self):
  for name in a.MODULES:
   relative=name.replace('.','/')+'.py';self.assertEqual((a.ROOT/relative).read_bytes(),(a.MIRROR/relative).read_bytes())
 def test_existing_output_rejected_before_case_read(self):
  builder,_=a.source_context()
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'output.json').write_text('retained',encoding='utf-8')
   with patch.object(a,'ROOT',root),patch.object(a,'configured',return_value=(builder,None,{})):
    with self.assertRaisesRegex(ValueError,'Output already exists'):a.preflight('missing-case.json','missing-scope.json','output.json')
   self.assertEqual((root/'output.json').read_text(),'retained')
 def test_path_alias_rejected_before_case_read(self):
  builder,_=a.source_context()
  with tempfile.TemporaryDirectory() as d:
   with patch.object(a,'ROOT',Path(d)),patch.object(a,'configured',return_value=(builder,None,{})):
    with self.assertRaisesRegex(ValueError,'must be distinct'):a.preflight('case.json','case.json','new.json')
if __name__=='__main__':unittest.main()
