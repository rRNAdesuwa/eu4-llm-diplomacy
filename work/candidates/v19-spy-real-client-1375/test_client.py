from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import client
import provenance
import frozen as f

fixture=f.load('test_fixture',f.PURE/'fixture.py',{'fixed':f.fixed,'reader':f.reader})

def bound_status(stage=1):
    identity=dict(pid=1234,creation='0000000000000001',session='a'*32,dll_sha256=f.DLL_SHA,manifest_sha256=f.MANIFEST_SHA)
    return dict(identity=identity,status='ready',next_sequence=stage,claimed_sequence=stage-1,preflight_ready=True,authenticated_stages=3 if stage==4 else 0,
                controller_frames=6 if stage==4 else 0,last_owner_uptime_ms=10000,source_bound_origin_verified=True,source_manifest_verified=True,build_loader_verified=True,
                outer_sha256='a'*64,raw_sha256='b'*64,startup_only=stage==1)

class HeldFake:
    def __init__(self):self.checks=0;self.identities=0
    def check(self,status,directory):self.checks+=1
    def identity_check(self):self.identities+=1

class IO:
    def __init__(self,status):self.status=status;self.reads=0;self.moves=0;self.writes=0;self.failure=None
    def inspect(self,d,i):
        self.reads+=1
        if self.failure==self.reads:raise ValueError('Second/third complete semantic gate failed')
        return deepcopy(self.status)
    def now(self):return 10001
    def build(self,d):return None
    def write(self,p,raw):self.writes+=1;client.write_new(p,raw)
    def move(self,source,target):self.moves+=1;client.move_new(source,target)

class PublishTests(unittest.TestCase):
    def setup_fs(self,temp,stage=1):
        s=bound_status(stage);i=s['identity'];p=f.wire.session_path(temp,i);p.mkdir();return s,i,p
    def test_once_durable_with_real_temp_noreplace(self):
        with tempfile.TemporaryDirectory() as temp:
            s,i,p=self.setup_fs(temp);io=IO(s);held=HeldFake();result=client._publish(Path(temp),i,'lifecycle',held,io)
            self.assertTrue(result['request_written']);self.assertTrue(result['native_result_unknown']);self.assertIsNone(result['native_result'])
            self.assertEqual([io.reads,io.moves,io.writes,held.checks,held.identities],[3,1,2,3,1])
            self.assertTrue((p/'1.publisher-intent.json').is_file());self.assertEqual((p/'1.request').read_bytes(),f.wire.encode_request(i,'lifecycle',70001))
            with self.assertRaises(ValueError):client._publish(Path(temp),i,'lifecycle',HeldFake(),IO(s))
    def test_permanent_second_and_third_gate_failure(self):
        for fail in (2,3):
            with tempfile.TemporaryDirectory() as temp:
                s,i,p=self.setup_fs(temp);io=IO(s);io.failure=fail
                with self.assertRaises(ValueError):client._publish(Path(temp),i,'lifecycle',HeldFake(),io)
                self.assertEqual(io.moves,0);self.assertTrue((p/'1.publisher-intent.json').exists());self.assertFalse((p/'1.request').exists())
                with self.assertRaises(ValueError):client._publish(Path(temp),i,'lifecycle',HeldFake(),IO(s))
    def test_unknown_after_atomic_publication_is_not_retried(self):
        with tempfile.TemporaryDirectory() as temp:
            s,i,p=self.setup_fs(temp);io=IO(s)
            def unknown(a,b):client.move_new(a,b);raise OSError('Unknown after successful rename')
            io.move=unknown
            with self.assertRaises(OSError):client._publish(Path(temp),i,'lifecycle',HeldFake(),io)
            self.assertTrue((p/'1.request').exists());self.assertTrue((p/'1.publisher-intent.json').exists())
            with self.assertRaises(ValueError):client._publish(Path(temp),i,'lifecycle',HeldFake(),IO(s))
    def test_native_claim_or_external_request_blocks_publish(self):
        for name in ('1.claim','1.request','1.publisher-pending','1.publisher-intent.json'):
            with tempfile.TemporaryDirectory() as temp:
                s,i,p=self.setup_fs(temp);(p/name).write_bytes(b'existing');io=IO(s)
                with self.assertRaises(ValueError):client._publish(Path(temp),i,'lifecycle',HeldFake(),io)
                self.assertEqual([io.moves,io.writes],[0,0]);self.assertEqual((p/name).read_bytes(),b'existing')
    def test_noreplace_target_collision(self):
        with tempfile.TemporaryDirectory() as temp:
            a=Path(temp)/'a';b=Path(temp)/'b';a.write_bytes(b'new');b.write_bytes(b'old')
            with self.assertRaises(OSError):client.move_new(a,b)
            self.assertEqual(b.read_bytes(),b'old');self.assertEqual(a.read_bytes(),b'new')
    def test_explicit_batch4_only_after_same_session_proof(self):
        s=bound_status(4);i=s['identity'];self.assertEqual(client.proposed(s,i,'send_batch',10001),(4,70001))
        for key,value in [('authenticated_stages',2),('next_sequence',3),('preflight_ready',False),('startup_only',True),('claimed_sequence',True)]:
            bad=deepcopy(s);bad[key]=value
            with self.assertRaises(ValueError):client.proposed(bad,i,'send_batch',10001)
    def test_typed_health_future_stale(self):
        for key,value in [('next_sequence',True),('last_owner_uptime_ms',10000.0),('claimed_sequence',False),('build_loader_verified',1),('identity',{})]:
            s=bound_status();i=s['identity'];s[key]=value
            with self.assertRaises(ValueError):client.proposed(s,i,'lifecycle',10001)
        for now in (9999,12501,True,10001.0):
            s=bound_status()
            with self.assertRaises(ValueError):client.proposed(s,s['identity'],'lifecycle',now)
    def test_fsync_failure_keeps_exclusive_intent(self):
        with tempfile.TemporaryDirectory() as temp:
            s,i,p=self.setup_fs(temp);io=IO(s)
            with patch.object(client.os,'fsync',side_effect=OSError('fsync uncertain')):
                with self.assertRaises(OSError):client._publish(Path(temp),i,'lifecycle',HeldFake(),io)
            self.assertTrue((p/'1.publisher-intent.json').exists());self.assertEqual(io.moves,0)
            with self.assertRaises(ValueError):client._publish(Path(temp),i,'lifecycle',HeldFake(),IO(s))
    def test_clock_rollback_after_intent_freezes_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            s,i,p=self.setup_fs(temp);io=IO(s);values=iter([10001,10000]);io.now=lambda:next(values)
            with self.assertRaises(ValueError):client._publish(Path(temp),i,'lifecycle',HeldFake(),io)
            self.assertTrue((p/'1.publisher-intent.json').exists());self.assertEqual(io.moves,0)
    def test_own_intent_mutation_cannot_override_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            s,i,p=self.setup_fs(temp);io=IO(s);old=io.inspect
            def alter(*args):
                result=old(*args)
                if io.reads==2:(p/'1.publisher-intent.json').write_bytes(b'changed')
                return result
            io.inspect=alter
            with self.assertRaises(ValueError):client._publish(Path(temp),i,'lifecycle',HeldFake(),io)
            self.assertEqual(io.moves,0)

def fake_loader(identity,manifest,directory):
    boot=f.wire.encode_boot(identity);base=0x7ff800000000
    call=dict(pid=identity['pid'],process='C:\\fake\\eu4.exe',dll=str((directory/f.b.DLL).resolve()),dll_module_base=hex(base),bridge_rva=hex(manifest['pe']['bridge_start_rva']),bridge_remote_address=hex(base+manifest['pe']['bridge_start_rva']),load_library_owner='C:\\Windows\\System32\\kernelbase.dll',load_library_rva='0x1234',load_library_remote_address='0x7ff900001234',load_thread_exit_status=hex(base&0xffffffff),bridge_thread_exit_status='0x0',test_save_acknowledged=True,dll_unloaded=False,warnings=[])
    return dict(schema='EU4SPYSENDLOAD/1',purpose=f.wire.PURPOSE,identity=identity,process_path=call['process'],plan_only=False,disposable_test_premise=True,strict_sp_verified=False,world_epoch_verified=False,production_ready=False,automatic_stage=False,restricted_research_send=True,stage_request_written=False,bootstrap_sha256=f.b.sha(boot),bootstrap_bytes=len(boot),installation=call,held_identity_checked_after=True),boot

class ProvenanceTests(unittest.TestCase):
    def test_real_frozen_build_disk_only_and_origins(self):
        m,h=f.verify_build(f.BUILD);self.assertEqual(h,f.MANIFEST_SHA);self.assertEqual(m['dll_sha256'],f.DLL_SHA)
        self.assertEqual(Path(f.b.__file__).resolve(),(f.BOOT/'build_manifest.py').resolve())
        self.assertEqual(Path(f.reader.__file__).resolve(),(f.PURE/'reader.py').resolve())
        with self.assertRaises(ValueError):f.verify_build(f.BUILD.parent)
    def test_loader_strict_types_and_export(self):
        m,_=f.verify_build(f.BUILD);i=bound_status()['identity'];record,boot=fake_loader(i,m,f.BUILD)
        self.assertEqual(provenance.loader_record(record,i,m,f.BUILD,boot),0x7ff800000000)
        for path,value in [(('identity','pid'),1234.0),(('bootstrap_bytes',),float(len(boot))),(('held_identity_checked_after',),1),(('installation','pid'),True),(('installation','bridge_rva'),'0x1000'),(('installation','bridge_thread_exit_status'),'0x1'),(('installation','dll_unloaded'),0),(('installation','warnings'),['unknown'])]:
            bad=deepcopy(record);d=bad
            for key in path[:-1]:d=d[key]
            d[path[-1]]=value
            with self.assertRaises(ValueError):provenance.loader_record(bad,i,m,f.BUILD,boot)
    def test_startup_only_and_no_fake_claim(self):
        r,o,i,c=fixture.fixture(1);outer=fixture.encode(o[:3]);s=provenance.startup(b'',outer,i)
        self.assertEqual(s['next_sequence'],1);self.assertIsNone(s['selected_world'])
        with self.assertRaises(ValueError):provenance.startup(fixture.encode(r[:1]),outer,i)
        with self.assertRaises(ValueError):provenance.startup(b'',fixture.encode(o),i)
    def test_startup_installer_failure_alias(self):
        for key,value in [('collected',0),('error',5),('rip',1),('failure_thread',1),('suspended',0.0)]:
            r,o,i,c=fixture.fixture(1);o[1]['detail'][key]=value
            with self.assertRaises(ValueError):provenance.startup(b'',fixture.encode(o[:3]),i)
    def test_complete_file_wrapper_synthetic_and_path_scope(self):
        r,o,i,c=fixture.fixture(6)
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);m={'dll_sha256':i['dll_sha256'],'pe':{'bridge_start_rva':19264}}
            record,boot=fake_loader(i,m,d);(d/f'bootstrap-{i["pid"]}-{i["creation"]}.request').write_bytes(boot)
            (d/f'loader-{i["pid"]}-{i["creation"]}.json').write_bytes(f.b.canonical(record))
            s=f.wire.session_path(d,i);s.mkdir();(s/'raw-events.jsonl').write_bytes(fixture.encode(r));(s/'bootstrap-events.jsonl').write_bytes(fixture.encode(o))
            for name,data in c.items():(s/(name+'.claim')).write_bytes(data);(s/(name+'.request')).write_bytes(data)
            with patch.object(provenance,'verify_build',return_value=(m,i['manifest_sha256'])):
                value=provenance.inspect(d,i);self.assertEqual(value['next_sequence'],4);self.assertTrue(value['build_loader_verified']);self.assertFalse(value['live_identity_verified'])
                (s/'2.request').write_bytes(b'wrong')
                with self.assertRaises(ValueError):provenance.inspect(d,i)

if __name__=='__main__':unittest.main()
