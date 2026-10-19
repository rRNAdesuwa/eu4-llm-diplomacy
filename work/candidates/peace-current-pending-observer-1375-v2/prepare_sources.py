"""One source-only v2 construction from exact v1 bytes; never run old tests."""
from pathlib import Path
import ast, hashlib, json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OLD=ROOT/'work/candidates/peace-current-pending-observer-1375-v1'
AUTH='work/reports/peace-current-pending-v2-source-authorization-20261016-r1/authorization.json'
EXPECTED={
 AUTH:(3296,'423d8b9e04d29e0fe3de58228e79903dac49e4a07881e38e3b92a81df38a1dec'),
 'work/candidates/peace-current-pending-observer-1375-v1/peace_current_pending.py':(23345,'ac8c292d1320f776a6a8817f0158c275e624bcfe05f9a2dc51220e03532ba643'),
 'work/candidates/peace-current-pending-observer-1375-v1/test_peace_current_pending.py':(13657,'96f41c4e8752f639c67db42144437734d9dee1ff38a09ae770f6cfc271b65ca5')}
def write(name,b):
 if isinstance(b,str):b=b.encode('utf-8')
 with (HERE/name).open('xb') as f:f.write(b)
def save(name,v):write(name,json.dumps(v,ensure_ascii=True,sort_keys=True,indent=2)+'\n')
def main():
 source={}
 for n,(size,sha) in EXPECTED.items():
  b=(ROOT/n).read_bytes();assert len(b)==size and hashlib.sha256(b).hexdigest()==sha;source[n]=b
 auth=json.loads(source[AUTH]);assert auth['chosen_option']=='B-layout-profile-plus-raw-diagnostic'
 old=source[next(n for n in source if n.endswith('/peace_current_pending.py'))].decode().replace('\r\n','\n')
 cli=old.replace('Current selected peace inbox only. Read-only candidate; never request/effect proof.',
  'Current selected peace inbox v2. Unclassified scalar is raw/coherence-only; never request/effect proof.')
 cli=cli.replace('EU4-PEACE-CURRENT-PENDING-MANIFEST/1','EU4-PEACE-CURRENT-PENDING-MANIFEST/2').replace("schema='EU4-PEACE-CURRENT-PENDING/1'","schema='EU4-PEACE-CURRENT-PENDING/2'")
 cli=cli.replace("'build_manifest.py','run_offline.py')","'build_manifest.py','run_offline.py','prepare_sources.py','offline_child.py','source-delta.json','budget.json')")
 marker="     require(r.i(cap.base+0x233e064)==-1,'Unsupported current Mod')"
 assert cli.count(marker)==1
 cli=cli.replace(marker,"     scalar_raw=r.read(cap.base+0x233e064,4)\n     scalar=dict(rva='0x233e064',raw_hex=scalar_raw.hex(),i32=struct.unpack('<i',scalar_raw)[0],\n      u32=struct.unpack('<I',scalar_raw)[0],semantics='unknown')")
 marker="     out['samples'].append(sample_selected(r,observer,libraries,cap.base,root,table,handles,chosen['actor'],chosen['target']))"
 assert cli.count(marker)==1
 cli=cli.replace(marker,"     sample=sample_selected(r,observer,libraries,cap.base,root,table,handles,chosen['actor'],chosen['target'])\n     sample['unclassified_scalar']=scalar;out['samples'].append(sample)")
 # Metadata-only provenance roots; no new execution path.
 additions={AUTH:EXPECTED[AUTH][1],
  'work/candidates/peace-current-pending-observer-1375-v1/peace_current_pending.py':EXPECTED[next(n for n in source if n.endswith('/peace_current_pending.py'))][1],
  'work/candidates/peace-current-pending-observer-1375-v1/test_peace_current_pending.py':EXPECTED[next(n for n in source if n.endswith('/test_peace_current_pending.py'))][1],
  'work/reports/peace-current-pending-guard-proposal-20261016-r1/proposal.json':'ba2b0931280bb38087c686b8bf6e47688c49d68178c8a8183815cd604e4030e7'}
 needle="JOB:'5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011'}"
 assert needle in cli
 cli=cli.replace(needle,needle[:-1]+',\n'+',\n'.join(' '+repr(n)+':'+repr(v) for n,v in additions.items())+'}')
 trees=[ast.parse(x) for x in (old,cli)]
 defs=[{n.name:ast.dump(n,include_attributes=False) for n in t.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))} for t in trees]
 changed=[n for n in defs[0] if defs[0][n]!=defs[1][n]]
 assert changed==['verify_sources','base_result','observe'],changed
 protected=['queue_sample','sample_selected','capture_class','host_sample','code_guard','SharedReader','Libraries','result_code','run','selection','pointer']
 assert all(defs[0][n]==defs[1][n] for n in protected)
 write('peace_current_pending.py',cli)
 rawtest=source[next(n for n in source if n.endswith('/test_peace_current_pending.py'))].decode().replace('\r\n','\n')
 prefix=rawtest.split('class PeaceTests(unittest.TestCase):',1)[0]
 assert 'class PeaceTests' not in prefix
 newtests='''class ScalarV2Tests(unittest.TestCase):
 def retain(self,name,out,f):
  self.assertTrue(f.closed)
  self.assertTrue(all(out[k] is False for k in m.FALSE_FLAGS))
  self.assertFalse(out['close_os_return_checked'])
  self.assertEqual(out['rpm_budget']['bytes_requested'],sum(x['requested_bytes'] for x in out['raw_ordered_read_journal']))
  p=HERE/'offline-r1'/('fake-'+name+'.json')
  with p.open('x',encoding='utf-8',newline='\\n') as stream:json.dump(out,stream,ensure_ascii=True,sort_keys=True,indent=2);stream.write('\\n')
 def scalar_rows(self,out):
  return [x for x in out['raw_ordered_read_journal'] if x['address']==hex(BASE+0x233e064)]
 def success(self,name,value,present):
  f=FakeLibraries([dict(id=0,state=0xffffffff)] if present else [])
  f.mem.put(BASE+0x233e064,struct.pack('<i',value));out=m.observe(CHOSEN,f)
  self.assertEqual(m.result_code(out),0);self.assertIs(out['selected_queue_presence'],present)
  self.assertTrue(out['commit_after_context_exit']);self.assertTrue(out['selected_two_pass_equal'])
  self.assertEqual(len(self.scalar_rows(out)),2)
  for sample in out['samples']:
   self.assertEqual(sample['unclassified_scalar'],dict(rva='0x233e064',raw_hex=struct.pack('<i',value).hex(),i32=value,u32=value&0xffffffff,semantics='unknown'))
  if present:
   row=out['samples'][0]['queue']['selected'][0];self.assertEqual(row['native_id_raw_u32'],0);self.assertEqual(row['state_raw_u32'],0xffffffff)
  self.retain(name,out,f)
 def test_01_minus_one_absent(self):self.success('minus-one-absent',-1,False)
 def test_02_one_absent(self):self.success('one-absent',1,False)
 def test_03_one_present(self):self.success('one-present',1,True)
 def test_04_scalar_changes(self):
  f=FakeLibraries();f.mem.put(BASE+0x233e064,struct.pack('<i',1));calls=[]
  def hook(a,n):
   if (a,n)==(BASE+0x233e064,4):
    calls.append(1)
    if len(calls)==2:f.mem.put(a,struct.pack('<i',2))
  f.mem.hook=hook;out=m.observe(CHOSEN,f)
  self.assertEqual(m.result_code(out),2);self.assertIsNone(out['selected_queue_presence']);self.assertFalse(out['commit_after_context_exit'])
  self.assertEqual([s['unclassified_scalar']['i32'] for s in out['samples']],[1,2])
  self.assertTrue(any(e['message']=='Two complete passes differ' for e in out['errors']))
  self.retain('scalar-change',out,f)
 def test_05_short_scalar(self):
  f=FakeLibraries();f.mem.put(BASE+0x233e064,struct.pack('<i',1));f.mem.short=(BASE+0x233e064,4);out=m.observe(CHOSEN,f)
  self.assertEqual(m.result_code(out),2);self.assertIsNone(out['selected_queue_presence']);self.assertFalse(out['commit_after_context_exit'])
  rows=self.scalar_rows(out);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['requested_bytes'],4);self.assertEqual(rows[0]['returned_bytes'],3);self.assertEqual(rows[0]['status'],'failed')
  self.assertNotIn((TARGET+0x18d8,21),f.mem.reads);self.retain('short-scalar',out,f)
 def test_06_structural_refusal(self):
  f=FakeLibraries([dict(id=0)]);f.mem.put(BASE+0x233e064,struct.pack('<i',1));f.mem.put(NODE+24,b'\\x01');f.mem.put(NODE,struct.pack('<Q',1))
  out=m.observe(CHOSEN,f)
  self.assertEqual(m.result_code(out),2);self.assertIsNone(out['selected_queue_presence']);self.assertFalse(out['commit_after_context_exit'])
  self.assertTrue(any('Tombstone' in e['message'] for e in out['errors']));self.assertFalse(any(a==1 for a,n in f.mem.reads))
  self.assertEqual(self.scalar_rows(out)[0]['raw_hex'],'01000000');self.retain('structural-refusal',out,f)

if __name__=='__main__':unittest.main(verbosity=2)
'''
 test=prefix+newtests;assert len([n for n in ast.walk(ast.parse(test)) if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')])==6
 write('test_peace_current_pending.py',test)
 save('source-delta.json',dict(schema='EU4-PEACE-PENDING-V2-SOURCE-DELTA/1',old_cli=EXPECTED['work/candidates/peace-current-pending-observer-1375-v1/peace_current_pending.py'],
  changed_definitions=changed,metadata_changes=['module docstring','manifest/result schema version2','FIXED provenance roots','OWN_NAMES graph closure'],
  verify_sources_change='Only manifest schema literal /1 -> /2; all guard logic unchanged',base_result_change='Only output schema /1 -> /2',
  observe_change='Replace unproven scalar==-1 rejection with same shared 4B read, raw/i32/u32 diagnostic attached to each full sample; exact sample equality unchanged',
  unchanged_definitions=[n for n in defs[0] if n not in changed],protected_AST_equal=protected,
  copied_fixture_helpers=['handle','Memory','FakeLibraries'],old_test_methods_copied=0,new_test_methods=6,
  scalar_semantics='unknown',all_mod_compatibility_claimed=False,production_authorized=False))
 save('source-construction.json',dict(authorization=EXPECTED[AUTH],source_pins={n:dict(bytes=s,sha256=h) for n,(s,h) in EXPECTED.items()},
  explicit_source_read_bytes=sum(len(v) for v in source.values()),new_tests_run=0,old_tests_run=0,game_access=0))
 print(json.dumps(dict(status='source_created',changed_definitions=changed,unchanged_definitions=len(defs[0])-len(changed),new_test_methods=6)))
if __name__=='__main__':main()
