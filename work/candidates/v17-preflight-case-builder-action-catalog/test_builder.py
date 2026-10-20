"""Synthetic complete phase files; no actual63500 prefix/RO inputs are consumed."""
from copy import deepcopy
from pathlib import Path
import hashlib,json,sys,unittest
from unittest.mock import patch
import build_case as b
sys.path.insert(0,str(b.ROOT/'work/candidates/v17-acceptance-experiment-review'))
import synthetic as syn
class BuilderTests(unittest.TestCase):
 def setUp(self):
  self.f=syn.Fixture();self.f.setUp();self.addCleanup(self.f.doCleanups);self.root=self.f.root
  self.c=b.template();self.c['prefix_directory']=b.RUNTIME+'directional-preflight-prefix-'+str(self.f.scope['pid'])
  self.c['output_directory']=b.RUNTIME+'synthetic-constructed'
  prefix=self.root/self.c['prefix_directory'];prefix.mkdir(parents=True)
  for name in b.FILES:self.add(name,self.c['prefix_directory']+'/'+name,(self.f.prefix_dir/name).read_bytes())
  for name in ('before','after','loader','status'):
   self.add(name,b.RUNTIME+name+'.json',(self.root/('prefix-'+name+'.json')).read_bytes())
  build=self.f.pre.fixed_build();self.add('build',b.RUNTIME+'build.json',b.wire(build))
  self.c['scope']=dict(self.f.scope,manifest_sha256=self.c['inputs']['build']['sha256'],
   preflight_case=self.c['output_directory']+'/preflight-case.json',preflight_summary=self.c['output_directory']+'/preflight-summary.json')
  self.enterContext(patch.object(syn.lab,'verify_build',return_value=(build,self.c['scope']['manifest_sha256'])))
  for key in ('loader','status'):
   d=b.decode((self.root/self.c['inputs'][key]['path']).read_bytes());d['manifest_sha256']=self.c['scope']['manifest_sha256'];self.add(key,self.c['inputs'][key]['path'],b.wire(d))
  snap={'pid':self.f.scope['pid'],'creation':self.f.scope['creation'],'prefix_bytes':len(self.f.prefix),'prefix_sha256':b.sha(self.f.prefix),
   'source_process_exit_observed':False,'whole_active_log_unchanged_verified':False,
   'snapshot_file_sha256':{k:self.c['inputs'][k]['sha256'] for k in b.FILES},'status_sha256':self.c['inputs']['status']['sha256']}
  self.add('snapshot',b.RUNTIME+'snapshot.json',b.wire(snap))
  # Only expected fixed identity/build values use explicit synthetic bindings.
  # All file/schema/held/process/phase/status validators remain the real code.
  self.enterContext(patch.object(b,'EXPECTED',{k:self.c['scope'][k] for k in b.EXPECTED}))
 def add(self,key,name,raw):
  p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
  self.c['inputs'][key]={'path':name,'size_bytes':len(raw),'sha256':b.sha(raw)}
 def mutate(self,key,fn):
  name=self.c['inputs'][key]['path'];d=b.decode((self.root/name).read_bytes());fn(d);self.add(key,name,b.wire(d))
 def test_valid_complete_sources_publish_only_three_construction_files(self):
  packet=b.construct(self.c,self.root);self.assertFalse(packet['construction']['formal_review_performed']);self.assertFalse(packet['construction']['runtime_promoted'])
  out=b.publish(self.c,self.root);self.assertEqual({p.name for p in out.iterdir()},{'scope.json','preflight-case.json','construction.json'})
  with self.assertRaises(FileExistsError):b.publish(self.c,self.root)
 def test_missing_after_no_case_directory(self):
  (self.root/self.c['inputs']['after']['path']).unlink()
  with self.assertRaises(FileNotFoundError):b.publish(self.c,self.root)
  self.assertFalse((self.root/self.c['output_directory']).exists())
 def test_same_file_or_bytecopy_is_not_two_captures(self):
  c=deepcopy(self.c);self.c['inputs']['after']=deepcopy(self.c['inputs']['before'])
  with self.assertRaises(ValueError):b.construct(self.c,self.root)
  self.c=c;self.add('after',self.c['inputs']['after']['path'],(self.root/self.c['inputs']['before']['path']).read_bytes())
  with self.assertRaises(ValueError):b.construct(self.c,self.root)
 def test_status_not_ro_diagnostic(self):
  self.add('after',self.c['inputs']['after']['path'],(self.root/self.c['inputs']['status']['path']).read_bytes())
  with self.assertRaises((ValueError,KeyError)):b.construct(self.c,self.root)
 def test_budget_only_difference_allowed(self):
  self.mutate('after',lambda d:(d['read_budget'].__setitem__('bytes_requested',d['read_budget']['bytes_requested']+16),d['state'].__setitem__('memory_bytes_requested',d['state']['memory_bytes_requested']+16)))
  b.construct(self.c,self.root)
 def test_diplomat_change_rejected(self):
  old=(self.root/self.c['inputs']['after']['path']).read_bytes()
  self.mutate('after',lambda d:d['state']['actor_diplomats'].__setitem__('entry_count',103))
  with self.assertRaisesRegex(ValueError,'Diplomat data unavailable or malformed'):b.construct(self.c,self.root)
  self.add('after',self.c['inputs']['after']['path'],old)
  def change(d):
   vector=d['state']['actor_diplomats'];entry=vector['entries'][0]
   entry['state_raw_18']=1 if entry['state_raw_18']==0 else 0
   entry['state_zero_available_candidate']=entry['state_raw_18']==0
   vector['state_zero_count']=sum(x['state_raw_18']==0 for x in vector['entries'])
  self.mutate('after',change)
  with self.assertRaisesRegex(ValueError,'Selected diagnostic state changed'):b.construct(self.c,self.root)
 def test_creation_bool_float_rejected(self):
  old=(self.root/self.c['inputs']['after']['path']).read_bytes()
  for value in (True,float(int(self.c['scope']['creation'],16))):
   self.add('after',self.c['inputs']['after']['path'],old);self.mutate('after',lambda d:d['source'].__setitem__('process_creation_filetime',value))
   with self.subTest(value=value),self.assertRaisesRegex(ValueError,'Diagnostic process creation/exit differs'):b.construct(self.c,self.root)
 def test_overlapping_captures_rejected(self):
  before=b.decode((self.root/self.c['inputs']['before']['path']).read_bytes())
  self.mutate('after',lambda d:d.__setitem__('capture_started_at_utc',before['captured_at_utc']))
  with self.assertRaisesRegex(ValueError,'Before/after captures overlap'):b.construct(self.c,self.root)
 def test_wrong_export_even_self_consistent_rejected(self):
  def change(d):
   v=d['installation'];v['bridge_rva']='0x1000';v['bridge_remote_address']=hex(int(v['dll_module_base'],16)+0x1000)
  self.mutate('loader',change)
  with self.assertRaisesRegex(ValueError,'Loader export differs'):b.construct(self.c,self.root)
 def test_fixed_scope_exact_types_and_no_pid22784(self):
  for k,v in [('pid',22784),('pid',True),('window_thread',float(self.c['scope']['window_thread'])),('prefix_bytes',float(self.c['scope']['prefix_bytes']))]:
   c=deepcopy(self.c);c['scope'][k]=v
   with self.subTest(key=k,value=v),self.assertRaises(ValueError):b.construct(c,self.root)
 def test_snapshot_float_and_filehash_rejected(self):
  old=(self.root/self.c['inputs']['snapshot']['path']).read_bytes()
  for fn in (lambda d:d.__setitem__('prefix_bytes',float(d['prefix_bytes'])),lambda d:d['snapshot_file_sha256'].__setitem__('install.claim','0'*64)):
   self.add('snapshot',self.c['inputs']['snapshot']['path'],old);self.mutate('snapshot',fn)
   with self.assertRaises(ValueError):b.construct(self.c,self.root)
 def test_bad_phase_claim_rejected(self):
  self.add('phase-command.claim',self.c['inputs']['phase-command.claim']['path'],b'bad claim\n')
  with self.assertRaises(ValueError):b.construct(self.c,self.root)
 def test_growing_session_and_extra_prefix_refused(self):
  c=deepcopy(self.c);c['prefix_directory']=b.RUNTIME+'session-1-0000000000000001'
  with self.assertRaises(ValueError):b.construct(c,self.root)
  (self.root/self.c['prefix_directory']/'unexpected.claim').write_bytes(b'x')
  with self.assertRaises(ValueError):b.construct(self.c,self.root)
 def test_duplicate_json_and_bounded_read(self):
  with self.assertRaises(ValueError):b.decode(b'{"pid":1,"pid":2}')
  p=self.root/'oversized';p.write_bytes(b'x'*33)
  with self.assertRaises(ValueError):b.bounded(p,32)
 def test_tampered_bytes_after_descriptor_rejected(self):
  p=self.root/self.c['inputs']['loader']['path'];p.write_bytes(p.read_bytes()+b' ')
  with self.assertRaises(ValueError):b.construct(self.c,self.root)
 def test_disk_build_failure_blocks_publication(self):
  with patch.object(syn.lab,'verify_build',side_effect=ValueError('Synthetic disk mismatch')):
   with self.assertRaisesRegex(ValueError,'Synthetic disk mismatch'):b.publish(self.c,self.root)
  self.assertFalse((self.root/self.c['output_directory']).exists())
 def test_phase_reader_uses_hashed_private_copy(self):
  original=syn.lab.read_evidence;seen=[]
  def read(directory,metadata):
   self.assertNotEqual(Path(directory).resolve(),(self.root/self.c['prefix_directory']).resolve())
   for name in b.FILES:self.assertEqual((Path(directory)/name).read_bytes(),(self.root/self.c['inputs'][name]['path']).read_bytes())
   seen.append(directory);return original(directory,metadata)
  with patch.object(syn.lab,'read_evidence',side_effect=read):b.construct(self.c,self.root)
  self.assertEqual(len(seen),1)
 def test_input_mutation_during_replay_blocks_publication(self):
  original=syn.lab.read_evidence
  def read(directory,metadata):
   value=original(directory,metadata)
   path=self.root/self.c['inputs']['loader']['path'];raw=path.read_bytes();path.write_bytes(b' '+raw[1:])
   return value
  with patch.object(syn.lab,'read_evidence',side_effect=read):
   with self.assertRaisesRegex(ValueError,'Input changed during construction'):b.publish(self.c,self.root)
  self.assertFalse((self.root/self.c['output_directory']).exists())
 def test_template_is_not_usable_without_inputs(self):
  with self.assertRaises(ValueError):b.construct(b.template(),self.root)
if __name__=='__main__':unittest.main()
