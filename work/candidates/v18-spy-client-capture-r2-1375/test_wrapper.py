"""Temporary files, real R2 replay, fake query guard/clock; never a real process."""
from pathlib import Path
from contextlib import ExitStack,contextmanager,redirect_stdout
import copy,io,json,sys,tempfile,types,unittest
from unittest.mock import patch
import _binding as binding
import client_r2 as wrapper

client=binding.client;b=client.b;wire=client.wire;reader=client.real_capture
fixture=binding._module(binding.OLD/'test_capture.py',{'build_manifest':b,'wire':wire,'real_capture':reader,'client':client})
BAD_INSTALL=({'error':5},{'collected':0,'suspended':0},{'failure_thread':123456,'rip':0x140000000})

class Kernel:
 def __init__(self):self.closed=0;self.wait=0x102
 def WaitForSingleObject(self,*args):return self.wait
 def CloseHandle(self,*args):self.closed+=1;return True

class Case:
 def __init__(self,path,stage=0):
  self.path=path;rows=fixture.synthetic();end=next(n for n,x in enumerate(rows) if x['event']=='health' and x['completed_stages']==stage)
  self.raw,self.outer,self.identity,self.claims=fixture.envelope(rows[:end+1],False)
  self.session=wire.session_path(path,self.identity);self.session.mkdir()
  self.packet=wire.encode_boot(self.identity)
  (path/f'bootstrap-{self.identity["pid"]}-{self.identity["creation"]}.request').write_bytes(self.packet)
  (self.session/'raw-events.jsonl').write_bytes(self.raw);(self.session/'bootstrap-events.jsonl').write_bytes(self.outer)
  for n,raw in self.claims.items():
   for suffix in ('request','claim'):(self.session/f'{n}.{suffix}').write_bytes(raw)
  self.manifest={'dll_sha256':self.identity['dll_sha256'],'pe':{'bridge_start_rva':0x7000}}
  load=dict(schema='EU4SPYLOAD/1',purpose=b.PURPOSE,identity=self.identity,plan_only=False,disposable_test_premise=True,held_identity_checked_after=True,
   strict_sp_verified=False,world_epoch_verified=False,production_ready=False,automatic_stage=False,send_supported=False,stage_request_written=False,
   bootstrap_sha256=b.sha(self.packet),bootstrap_bytes=len(self.packet),installation=dict(pid=self.identity['pid'],dll=str((path/b.DLL).resolve()),bridge_rva='0x7000',
   bridge_thread_exit_status='0x0',dll_unloaded=False,test_save_acknowledged=True,dll_module_base='0x7fff00000000',bridge_remote_address='0x7fff00007000'))
  (path/f'loader-{self.identity["pid"]}-{self.identity["creation"]}.json').write_bytes(b.canonical(load))
  self.kernel=Kernel()
 def mutate(self,delta):
  rows=[b.json_value(x) for x in self.outer.splitlines()];rows[1]['detail'].update(delta)
  (self.session/'bootstrap-events.jsonl').write_bytes(fixture.pack(rows))
 def argv(self,command='status',stage=None):
  args=['--build',str(self.path),'--pid',str(self.identity['pid']),'--creation',self.identity['creation'],'--session',self.identity['session'],command]
  return args+([stage] if stage is not None else [])
 @contextmanager
 def fake(self,now=10000):
  original=b.verify_build
  def build(path):
   if Path(path).resolve()==self.path.resolve():return self.manifest,self.identity['manifest_sha256']
   return original(path)
  with patch.object(b,'verify_build',side_effect=build),patch.object(client,'process_guard',return_value=(self.kernel,1)),patch.object(client,'now_ms',return_value=now):yield

class Wrapper(unittest.TestCase):
 def test_exact_origins_and_native_metadata(self):
  result=binding.check()
  self.assertEqual(result['reader_revision'],'v18-spy-bootstrap-capture-r2-1375')
  self.assertEqual(result['original_manifest_sha256'],'d1f65cae88cfb7ed2535c590206b9844882f0870f02773da23c747a6346aa5e5')
  self.assertEqual(result['original_dll_sha256'],'6aff9a9fc4d46692c9be0ac39b0c741bf8eeb840abaf8731d0144510a938f00b')
  self.assertEqual(Path(client.__file__),binding.OLD/'client.py')
  self.assertEqual(Path(reader.__file__),binding.R2/'real_capture.py')
  self.assertIs(reader.b,client.b);self.assertIs(reader.wire,client.wire)
 def test_private_imports_ignore_cached_untrusted_helpers(self):
  names=('build_manifest','wire','real_capture','loader','_frozen')
  old={k:sys.modules.get(k) for k in names};before=list(sys.path)
  fake={name:types.ModuleType(name) for name in names}
  with patch.dict(sys.modules,fake):
   fresh=types.ModuleType('_independent_binding');fresh.__file__=str(binding.HERE/'_binding.py')
   exec(compile(binding.read(binding.HERE/'_binding.py'),fresh.__file__,'exec'),fresh.__dict__)
   self.assertIs(fresh.client.real_capture,fresh.reader);self.assertNotIn(fresh.reader,fake.values())
   self.assertEqual(sys.path,before)
   self.assertTrue(all(sys.modules[k] is fake[k] for k in names))
  self.assertTrue(all(sys.modules.get(k) is v for k,v in old.items()))
 def test_old_reader_cannot_impersonate_r2_role_or_source_pin(self):
  old_path=binding.OLD/'real_capture.py';original_read=binding.read
  old=types.SimpleNamespace(__file__=str(old_path))
  with patch.object(client,'real_capture',old),self.assertRaisesRegex(ValueError,'dependency roles'):binding.check()
  def swapped(path,limit=binding.MAX_FILE):
   if Path(path)==binding.R2/'real_capture.py':return original_read(old_path,limit)
   return original_read(path,limit)
  with patch.object(binding,'read',side_effect=swapped),self.assertRaisesRegex(ValueError,'Frozen dependency changed'):
   binding._source(binding.R2/'real_capture.py')
  self.assertIs(client.real_capture,reader)
 def test_all_three_gates_reject_each_old_counterexample(self):
  for gate in ('status','before_intent','after_intent'):
   for delta in BAD_INSTALL:
    with self.subTest(gate=gate,delta=delta),tempfile.TemporaryDirectory() as td:
     c=Case(Path(td));write=client.loader.write_new
     def create(path,data):
      write(path,data)
      if str(path).endswith('.publisher-intent.json'):c.mutate(delta)
     if gate!='after_intent':c.mutate(delta)
     with c.fake(),patch.object(client.loader,'write_new',side_effect=create),redirect_stdout(io.StringIO()):
      with self.assertRaisesRegex(ValueError,'Successful installation'):
       wrapper.main(c.argv() if gate=='status' else c.argv('stage','lifecycle'))
     self.assertEqual((c.session/'1.publisher-intent.json').exists(),gate=='after_intent')
     self.assertFalse((c.session/'1.request').exists());self.assertFalse((c.session/'1.publisher-pending').exists())
     self.assertEqual(c.kernel.closed,0 if gate=='status' else 1)
 def test_valid_status_and_three_explicit_stages(self):
  for n,stage in enumerate(wire.p.STAGES):
   with self.subTest(stage=stage),tempfile.TemporaryDirectory() as td:
    c=Case(Path(td),n);c.mutate({'collected':2,'suspended':0})
    with c.fake(),redirect_stdout(io.StringIO()) as output:
     self.assertEqual(wrapper.main(c.argv()),0)
     result=json.loads(output.getvalue());self.assertEqual(result['completed_stages'],n)
    with c.fake(),redirect_stdout(io.StringIO()) as output:
     self.assertEqual(wrapper.main(c.argv('stage',stage)),0)
     result=json.loads(output.getvalue());self.assertIs(result['native_result_unknown'],True)
    request=wire.p.decode((c.session/f'{n+1}.request').read_bytes())
    self.assertEqual(request['stage'],stage);self.assertEqual(request['expires'],70000)
    self.assertEqual(request['sequence'],n+1);self.assertIs(request['value'],True)
    self.assertEqual((request['actor'],request['target'],request['state'],request['envoy']),('FRA','ENG',0,-1))
 def test_freshness_recheck_and_strict_next(self):
  for now,stage in ((9999,'lifecycle'),(12501,'lifecycle'),(True,'lifecycle'),(10000,'owned_command')):
   with self.subTest(now=now,stage=stage),tempfile.TemporaryDirectory() as td:
    c=Case(Path(td))
    with c.fake(now),self.assertRaises(ValueError):client.publish(c.path,c.identity,stage)
    self.assertFalse((c.session/'1.publisher-intent.json').exists())
  with tempfile.TemporaryDirectory() as td:
   c=Case(Path(td))
   with c.fake(),patch.object(client,'now_ms',side_effect=[10000,12501]),self.assertRaises(ValueError):client.publish(c.path,c.identity,'lifecycle')
   self.assertTrue((c.session/'1.publisher-intent.json').exists());self.assertFalse((c.session/'1.request').exists())
 def test_single_publish_and_all_preexisting_files(self):
  for suffix in ('request','claim','publisher-intent.json','publisher-pending'):
   with self.subTest(suffix=suffix),tempfile.TemporaryDirectory() as td:
    c=Case(Path(td));path=c.session/f'1.{suffix}';path.write_bytes(b'permanent')
    with c.fake(),self.assertRaises((ValueError,OSError)):client.publish(c.path,c.identity,'lifecycle')
    self.assertEqual(path.read_bytes(),b'permanent')
    if suffix!='request':self.assertFalse((c.session/'1.request').exists())
  with tempfile.TemporaryDirectory() as td:
   c=Case(Path(td))
   with c.fake():client.publish(c.path,c.identity,'lifecycle')
   first=(c.session/'1.request').read_bytes()
   with c.fake(),self.assertRaises(ValueError):client.publish(c.path,c.identity,'lifecycle')
   self.assertEqual((c.session/'1.request').read_bytes(),first)
 def test_flush_rename_and_unknown_failure_never_retry(self):
  for at in ('intent_fsync','pending_fsync','rename_before','rename_after'):
   with self.subTest(at=at),tempfile.TemporaryDirectory() as td:
    c=Case(Path(td));fsync=client.loader.os.fsync;rename=client.os.rename;count=0
    def flush(fd):
     nonlocal count
     count+=1
     if count==(1 if at=='intent_fsync' else 2) and at.endswith('fsync'):raise OSError('synthetic flush failure')
     return fsync(fd)
    def move(a,z):
     if at=='rename_before':raise OSError('synthetic rename failure')
     rename(a,z)
     if at=='rename_after':raise OSError('synthetic unknown after rename')
    with c.fake(),patch.object(client.loader.os,'fsync',side_effect=flush),patch.object(client.os,'rename',side_effect=move),self.assertRaises(OSError):client.publish(c.path,c.identity,'lifecycle')
    self.assertTrue((c.session/'1.publisher-intent.json').exists())
    self.assertEqual((c.session/'1.request').exists(),at=='rename_after')
    with c.fake(),self.assertRaises((ValueError,OSError)):client.publish(c.path,c.identity,'lifecycle')
    self.assertEqual(c.kernel.closed,2)
 def test_racing_request_not_replaced(self):
  with tempfile.TemporaryDirectory() as td:
   c=Case(Path(td));rename=client.os.rename
   def race(a,z):
    Path(z).write_bytes(b'foreign existing request');return rename(a,z)
   with c.fake(),patch.object(client.os,'rename',side_effect=race),self.assertRaises(OSError):client.publish(c.path,c.identity,'lifecycle')
   self.assertEqual((c.session/'1.request').read_bytes(),b'foreign existing request')
   self.assertTrue((c.session/'1.publisher-pending').exists())
 def test_exit_and_ttl_failures_preserve_intent(self):
  for case in ('exit','expiry_before_pending','expiry_before_rename'):
   with self.subTest(case=case),tempfile.TemporaryDirectory() as td:
    c=Case(Path(td));clock=[10000,10000,70000] if case=='expiry_before_pending' else [10000,10000,10000,70000]
    if case=='exit':c.kernel.wait=0
    with c.fake(),patch.object(client,'now_ms',side_effect=clock),self.assertRaises(ValueError):client.publish(c.path,c.identity,'lifecycle')
    self.assertTrue((c.session/'1.publisher-intent.json').exists());self.assertFalse((c.session/'1.request').exists())
 def test_foreign_and_malformed_cli_rejected_without_process(self):
  with tempfile.TemporaryDirectory() as td:
   c=Case(Path(td));base=c.argv()
   for args in (base+['--reader','other.py'],c.argv('submit'),c.argv('stage','execute')):
    with self.subTest(args=args),c.fake(),patch.object(client,'process_guard',side_effect=AssertionError('must not query')),redirect_stdout(io.StringIO()),self.assertRaises(SystemExit):wrapper.main(args)
   foreign=dict(c.identity);foreign['pid']+=1
   with c.fake(),self.assertRaises((ValueError,OSError)):reader.inspect(c.path,foreign)
 def test_build_mismatch_before_process_or_intent(self):
  with tempfile.TemporaryDirectory() as td:
   c=Case(Path(td));original=b.verify_build
   def verify(path):
    if Path(path).resolve()==c.path.resolve():raise ValueError('synthetic build mismatch')
    return original(path)
   with patch.object(b,'verify_build',side_effect=verify),patch.object(client,'process_guard',side_effect=AssertionError('must not query')),self.assertRaisesRegex(ValueError,'build mismatch'):
    wrapper.main(c.argv('stage','lifecycle'))
   self.assertFalse((c.session/'1.publisher-intent.json').exists())

if __name__=='__main__':unittest.main(verbosity=2)
