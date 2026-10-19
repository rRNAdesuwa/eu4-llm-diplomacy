"""Tests import generated v13 files; all sessions and manifests are synthetic."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
import tools
import work.native
import bridge

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module)
    package,leaf=name.rsplit('.',1);setattr(sys.modules[package],leaf,module);return module

GEN=HERE/'generated'
life=load('tools.verify_diplomacy_lifecycle_v13',GEN/'tools/verify_diplomacy_lifecycle_v13.py')
preview=load('tools.verify_diplomacy_preview_v13',GEN/'tools/verify_diplomacy_preview_v13.py')
command=load('tools.verify_diplomacy_command_v13',GEN/'tools/verify_diplomacy_command_v13.py')
owned=load('tools.verify_diplomacy_owned_peace_v13',GEN/'tools/verify_diplomacy_owned_peace_v13.py')
lab=load('work.native.lab_protocol_v13_1375',GEN/'work/native/lab_protocol_v13_1375.py')
http=load('bridge.diplomacy_lab_http_v13',GEN/'bridge/diplomacy_lab_http_v13.py')
from bridge.tests import test_diplomacy_lab_v10 as f10
from bridge.tests import test_diplomacy_lab_v12 as f12
from bridge.tests.test_diplomacy_lab_http import SyntheticRuntime,fake_history
from work.native import lab_protocol_v12_1375 as prior

def owned_rows(fixture):
    bind=dict(pid=fixture.pid,process_creation_filetime=fixture.creation,thread_id=fixture.thread,submitted=False)
    result=[dict(bind,event='owned_peace_selftest_begin',durable_claim=True,base_lifecycle_count=20,send_enabled=False)]
    # Generate the log from the documented native progression, independently of
    # the verifier's expected_core_flags helper.
    flags={k:0 for k in owned.RESULT_FLAGS}
    changes=[('factory_entered','factory_returned'),
        ('clone_entered','clone_returned','distinct_owned_ranges','original_unchanged_after_clone'),
        ('original_destroy_entered','original_destroy_returned','clone_unchanged_after_original_destroy'),
        ('clone_destroy_entered','clone_destroy_returned')]
    def core(event,step):
        return dict(event=event,step=step,action='requestpeace',token=0x293c,thread_id=fixture.thread,
            reason=0,original_mismatch_mask=0,clone_mismatch_mask=0,exception=0,freeze_session=0,
            retry_allowed=False,execution_verified=False,submitted=False,**flags)
    for i,fields in enumerate(changes,1):
        result.append(dict(bind,event='owned_peace_core_record',core=core('owned_peace_lifecycle_step_begin',i)))
        for k in fields:flags[k]=1
        result.append(dict(bind,event='owned_peace_core_record',core=core('owned_peace_lifecycle_step_complete',i)))
    result.append(dict(bind,event='owned_peace_core_record',core=core('owned_peace_lifecycle_return',0)))
    result.append(dict(bind,event='owned_peace_selftest_complete',record_kind='wrapper_result',passed=True,
        core_passed=True,core_audit_complete=True,post_guard_ok=True,reason=0,original_mismatch_mask=0,
        clone_mismatch_mask=0,exception=0,freeze_session=False,retry_allowed=False,execution_verified=False,
        **{k:True for k in owned.RESULT_FLAGS}))
    return result

class CandidateTests(unittest.TestCase):
    def setUp(self):
        template=f10.LabV10Tests();template.setUp();self.addCleanup(template.doCleanups)
        self.f=template.session_fixture();f12.extend_v12_fixture(self.f)
        self.f.metadata['purpose']=lab.PURPOSE
        self.f.events[0]['owned_peace_automatic']=False
        pos=next(i for i,e in enumerate(self.f.events) if e['event']=='pair_preview_begin')
        health=deepcopy(self.f.events[pos-1]);assert health['event']=='research_frame'
        self.f.events[pos:pos]=owned_rows(self.f)+[health]
        begun=complete=False;frames=0
        for event in self.f.events:
            if event['event']=='owned_peace_selftest_begin':begun=True
            if event['event']=='owned_peace_selftest_complete':complete=True
            if event['event']=='research_frame':
                frames+=100;event.update(frames=frames,uptime_ms=1000+frames,owned_peace_tested=begun,owned_peace_passed=complete)
        for name in ('session.json','install.claim'):(self.f.session/name).write_text(json.dumps(self.f.metadata))
        (self.f.session/lab.PHASES['owned_peace'][1]).write_bytes(lab.phase_wire('owned_peace',self.f.metadata))
        self.enterContext(patch.object(lab,'LiveLabProcess',side_effect=AssertionError('Forbidden live process')))
        self.enterContext(patch.object(lab,'_private_root',lambda _:None))
        self.original=deepcopy(self.f.events)

    def read(self,events=None):
        self.f.events=deepcopy(events if events is not None else self.original);self.f.write()
        return lab.read_evidence(self.f.session,self.f.metadata)

    def test_exact_scope_and_claim_marker(self):
        self.assertEqual(lab.ACTIONS,prior.ACTIONS);self.assertEqual(len(lab.ACTIONS),36)
        self.assertEqual(lab.FIXED_RESEARCH_PARAMETERS,prior.FIXED_RESEARCH_PARAMETERS)
        self.assertEqual((len(lab.SOURCES),len(lab.HOST_SOURCES),len(lab.SUPPORT_SOURCES)),(20,11,8))
        self.assertEqual(tuple(lab.PHASES),('lifecycle','owned_peace','preview','command'))
        raw=lab.phase_wire('owned_peace',self.f.metadata)
        self.assertEqual(raw,f'OWNED_PEACE_LIFECYCLE/1\npurpose={lab.PURPOSE}\npid={self.f.pid}\ncreation={self.f.creation}\n'.encode())
        for change in ({'pid':True},{'pid':0},{'process_creation_filetime':'0'*16},{'process_creation_filetime':'01DA123456789ABC'}):
            with self.subTest(change=change),self.assertRaises(ValueError):lab.phase_wire('owned_peace',self.f.metadata|change)
        for action in lab.ACTIONS:self.assertEqual(lab.encode_request(self.f.record|{'action':action}),prior.encode_request(self.f.record|{'action':action}))

    def test_full_four_stage_stream(self):
        evidence=self.read();self.assertTrue(all(evidence['phases'].values()))
        self.assertEqual(evidence['phase_proofs']['owned_peace']['core_record_count'],9)
        self.assertFalse(evidence['phase_proofs']['owned_peace']['execution_verified'])
        self.assertEqual(evidence['phase_proofs']['command']['case_count'],72)
        lab.check_ready(evidence,self.f.live,evidence['latest_frame']['uptime_ms'],operation='pair')
        self.assertEqual(owned.verify.__module__,'tools.verify_diplomacy_owned_peace_v13')
        proof,_=preview.read_session(self.f.session/'research-1375.jsonl',self.f.pid)
        self.assertEqual(proof['case_count'],72)

    def test_missing_or_foreign_claim_rejected(self):
        claim=self.f.session/lab.PHASES['owned_peace'][1]
        for raw in (b'',b'OWNED_PEACE_LIFECYCLE/1\n',lab.phase_wire('owned_peace',self.f.metadata|{'pid':self.f.pid+1}),
                    lab.phase_wire('owned_peace',self.f.metadata).replace(b'\n',b'\r\n')):
            claim.write_bytes(raw)
            with self.subTest(raw=raw),self.assertRaises(ValueError):self.read()
        claim.unlink()
        with self.assertRaises(OSError):self.read()

    def test_each_wrapper_proof_and_scalar_type_required(self):
        index=next(i for i,e in enumerate(self.original) if e['event']=='owned_peace_selftest_complete')
        for field in (*owned.RESULT_FLAGS,'passed','core_passed','core_audit_complete','post_guard_ok'):
            for bad in (False,1,None):
                rows=deepcopy(self.original);rows[index][field]=bad
                with self.subTest(field=field,bad=bad),self.assertRaises(ValueError):self.read(rows)
        for field in owned.ZERO_FIELDS:
            for bad in (1,False,None):
                rows=deepcopy(self.original);rows[index][field]=bad
                with self.subTest(field=field,bad=bad),self.assertRaises(ValueError):self.read(rows)

    def test_core_steps_diagnostics_order_and_no_alias_shortcut(self):
        indices=[i for i,e in enumerate(self.original) if e['event']=='owned_peace_core_record']
        for index in indices:
            rows=deepcopy(self.original);rows[index]['core']['factory_returned']=True
            with self.subTest(index=index),self.assertRaises(ValueError):self.read(rows)
        for field,bad in [('token',0x293d),('step',True),('reason',1),('freeze_session',1),('exception',0xc0000005),
            ('distinct_owned_ranges',0),('clone_unchanged_after_original_destroy',0),('execution_verified',True)]:
            rows=deepcopy(self.original);rows[indices[-1]]['core'][field]=bad
            with self.subTest(field=field),self.assertRaises(ValueError):self.read(rows)
        for mutation in ('missing','duplicate','swapped','unknown'):
            rows=deepcopy(self.original)
            if mutation=='missing':rows.pop(indices[4])
            elif mutation=='duplicate':rows.insert(indices[4],deepcopy(rows[indices[4]]))
            elif mutation=='swapped':rows[indices[0]],rows[indices[1]]=rows[indices[1]],rows[indices[0]]
            else:rows[indices[0]]['core']['pointer']='0x1000'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):self.read(rows)

    def test_pid_creation_thread_binding_and_frame_diagnostics(self):
        indices=[i for i,e in enumerate(self.original) if e['event'] in owned.OWNED_EVENTS]
        for index in indices:
            for field,bad in [('pid',self.f.pid+1),('process_creation_filetime','0000000000000001'),('thread_id',self.f.thread+1)]:
                rows=deepcopy(self.original);rows[index][field]=bad
                with self.subTest(index=index,field=field),self.assertRaises(ValueError):self.read(rows)
        for field,bad in [('owned_peace_tested',None),('owned_peace_passed',1),('owned_peace_passed',False)]:
            rows=deepcopy(self.original);rows[-1][field]=bad
            with self.subTest(field=field,bad=bad),self.assertRaises(ValueError):self.read(rows)

    def test_owned_independent_metadata_and_events_reject_numeric_creation(self):
        # 2**56 is exactly representable as float; neither it nor True may be a
        # native hexadecimal-string FILETIME, including both sides forged alike.
        invalid=(float(2**56),2**56,True,False,None,'0'*16,'01DA123456789ABC','1','01da123456789abc\n')
        for value in invalid:
            with self.subTest(metadata=value),self.assertRaises(ValueError):
                owned.OwnedPeaceSession(self.f.metadata|{'process_creation_filetime':value})
            event=owned_rows(self.f)[0]|{'process_creation_filetime':value}
            validator=owned.OwnedPeaceSession(self.f.metadata)
            with self.subTest(event=value),self.assertRaises(ValueError):validator.binding(event)
        validator=owned.OwnedPeaceSession(self.f.metadata)
        validator.binding(owned_rows(self.f)[0])

    def test_wrapper_cannot_replace_following_health_or_skip_stage(self):
        done=next(i for i,e in enumerate(self.original) if e['event']=='owned_peace_selftest_complete')
        rows=deepcopy(self.original);rows.pop(done+1)
        with self.assertRaises(ValueError):self.read(rows)
        rows=[e for e in self.original if e['event'] not in owned.OWNED_EVENTS]
        for e in rows:
            if e['event']=='research_frame':e.update(owned_peace_tested=False,owned_peace_passed=False)
        with self.assertRaises(ValueError):self.read(rows)
        rows=deepcopy(self.original);rows[done+1]['raw_date']+=24
        with self.assertRaises(ValueError):self.read(rows)

    def test_partial_or_ghost_claim_never_retries(self):
        start=next(i for i,e in enumerate(self.original) if e['event']=='owned_peace_selftest_begin')
        for endpoint in (start,start+1,start+5,start+11):
            evidence=self.read(self.original[:endpoint])
            self.assertFalse(evidence['phases']['owned_peace'])
            self.assertTrue(evidence['phase_attempted']['owned_peace'])
            with self.assertRaises(ValueError):lab.check_ready(evidence,self.f.live,evidence['latest_frame']['uptime_ms'],phase='owned_peace')
            with self.assertRaises(ValueError):lab.check_ready(evidence,self.f.live,evidence['latest_frame']['uptime_ms'],operation='pair')

    def test_explicit_marker_publication_once_with_bound_bytes(self):
        start=next(i for i,e in enumerate(self.original) if e['event']=='owned_peace_selftest_begin')
        claim=self.f.session/lab.PHASES['owned_peace'][1];claim.unlink()
        evidence=self.read(self.original[:start]);now=evidence['latest_frame']['uptime_ms']
        published=lab.publish_research(self.f.session,self.f.metadata,'a'*64,evidence,self.f.live,
            phase='owned_peace',clock=lambda:now)
        marker=self.f.session/lab.PHASES['owned_peace'][0]
        self.assertEqual(marker.read_bytes(),lab.phase_wire('owned_peace',self.f.metadata))
        self.assertFalse(published['native_dispatch_verified']);marker.unlink()
        with self.assertRaises((ValueError,OSError)):lab.publish_research(self.f.session,self.f.metadata,'a'*64,evidence,self.f.live,
            phase='owned_peace',clock=lambda:now)

    def test_fixed_five_scalars_and_positive_only_stay_checked(self):
        for family,key,bad in [('warsubsidy','fixed_subsidy_amount_milli',0),('warsubsidy','fixed_subsidy_duration_years',120),
            ('giftaction','fixed_gift_amount_milli',1),('transfer_trade_power','fixed_transfer_fraction_milli',50),('insultaction','fixed_insult_index',0)]:
            rows=deepcopy(self.original);next(e for e in rows if e['event']=='pair_preview_case' and e['action']==family)[key]=bad
            with self.subTest(field=key),self.assertRaises(ValueError):self.read(rows)
        for action in ('revoke_warning','cancel_insult','cancel_gift','requestpeace'):
            with self.assertRaises(ValueError):lab.encode_request(self.f.record|{'action':action})

    def test_unknown_owned_or_failed_wait_cannot_be_ignored(self):
        rows=deepcopy(self.original);rows.insert(2,dict(event='owned_peace_made_up',pid=self.f.pid))
        with self.assertRaises(ValueError):self.read(rows)

    def test_owned_sharing_wait_and_failure_diagnostics(self):
        start=next(i for i,e in enumerate(self.original) if e['event']=='owned_peace_selftest_begin')
        now=self.original[start-1]['uptime_ms']
        begin=dict(event='lab_input_wait',wait_state='begin',pid=self.f.pid,process_creation_filetime=self.f.creation,
            sequence=0,input_sequence=0,input_kind='owned_peace',outcome='sharing_violation',win32_error=32,
            uptime_ms=now,attempts=1,elapsed_ms=0,maximum_wait_ms=250,maximum_attempts=16,
            claim_created=False,native_invoked=False,retry_allowed=False)
        end=begin|dict(wait_state='end',outcome='opened',attempts=2,uptime_ms=now+1,elapsed_ms=1)
        evidence=self.read(self.original[:start]+[begin,end]+self.original[start:])
        self.assertTrue(evidence['phases']['owned_peace'])
        with self.assertRaises(ValueError):self.read(self.original[:start]+[begin]+self.original[start:])
        failed={k:v for k,v in begin.items() if k not in ('wait_state','outcome','elapsed_ms','maximum_wait_ms','maximum_attempts')}
        failed.update(event='lab_input_failed',stage='claim_flush',close_win32_error=0,expires=0,bytes=100,
            claim_created=True,claim_flushed=False,request_deleted=False)
        with self.assertRaises(ValueError):self.read(self.original[:start]+[failed])

    def test_actual_generated_loader_requires_creation_and_build_check_precedes_process(self):
        loader=load('work.native.inject_lab_v13_1375',GEN/'work/native/inject_lab_v13_1375.py')
        with patch('sys.stderr',new=io.StringIO()),self.assertRaises(SystemExit):
            loader.main(['--pid','1234','--ack-test-save','--test-save',next(iter(lab.TEST_SAVES)),'--plan-only'])
        with patch.object(lab,'verify_build',side_effect=ValueError('synthetic missing pinned build')),patch('sys.stderr',new=io.StringIO()):
            self.assertEqual(loader.main(['--pid','1234','--creation',self.f.creation,'--ack-test-save','--test-save',next(iter(lab.TEST_SAVES)),'--plan-only']),2)
        rows=deepcopy(self.original);rows[-1]['send_enabled']=True
        with self.assertRaises(ValueError):self.read(rows)

    def test_http_isolation_and_no_phase_bypass(self):
        class Runtime(SyntheticRuntime):protocol=lab
        runtime=Runtime(self.f.session);service=http.ResearchService(runtime,capability_reader=fake_history)
        value=service.capabilities()
        self.assertEqual(http.PREFIX,'/research/v13');self.assertEqual(len(value['http_pair_contract']['actions']),36)
        self.assertEqual(value['required_native_stages']['counts'],[20,1,72,72]);self.assertFalse(value['v13_candidate']['runtime_verified'])
        body={'protocol':lab.PROTOCOL,'pid':runtime.pid,'creation':runtime.creation,'sequence':1,
            'mode':'submit','action':'send_gift','actor':'FRA','target':'NAV','ttl_ms':5000}
        self.assertEqual(service.dispatch('POST','/research/v12/pair',body)[0],404)
        self.assertEqual(service.dispatch('POST',http.PREFIX+'/stage',{})[0],404)
        self.assertEqual(service.dispatch('POST',http.PREFIX+'/pair',body|{'amount':25})[0],422)
        self.assertEqual(service.dispatch('POST',http.PREFIX+'/pair',body)[0],409) # mock has only old three phases
        self.assertEqual(runtime.calls,0)

    def test_http_valid_four_phase_publication_and_duplicate_never_rewrites(self):
        class Runtime(SyntheticRuntime):
            protocol=lab
            def publish(self,snapshot,request):
                self.calls+=1
                return lab.publish_research(snapshot['session'],snapshot['metadata'],snapshot['manifest_sha256'],
                    snapshot['evidence'],snapshot['live'],sequence=request['sequence'],operation='pair',
                    mode=request['mode'],action=request['action'],actor=request['actor'],target=request['target'],
                    ttl_ms=request['ttl_ms'],clock=lambda:snapshot['now'])
        with tempfile.TemporaryDirectory() as directory:
            runtime=Runtime(directory)
            evidence=runtime.snapshot['evidence'];evidence['phases']['owned_peace']=True
            evidence['latest_frame'].update(owned_peace_tested=True,owned_peace_passed=True)
            service=http.ResearchService(runtime,capability_reader=fake_history)
            body={'protocol':lab.PROTOCOL,'pid':runtime.pid,'creation':runtime.creation,'sequence':1,
                'mode':'legality_only','action':'send_gift','actor':'FRA','target':'NAV','ttl_ms':5000}
            status,value=service.dispatch('POST',http.PREFIX+'/pair',body)
            self.assertEqual(status,202,value);self.assertFalse(value['native_dispatch_verified'])
            marker=Path(directory)/'00000000000000000001.request';before=marker.read_bytes()
            service.dispatch('POST',http.PREFIX+'/pair',body)
            self.assertEqual(runtime.calls,1);self.assertEqual(marker.read_bytes(),before)

class ManifestTests(unittest.TestCase):
    def test_exact_twenty_native_eleven_host_and_support_sources_are_mandatory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);output=root/'runtime';output.mkdir();(output/lab.DLL_NAME).write_bytes(b'not-an-executable-synthetic-dll')
            native_root=ROOT/'work/candidates/v13-owned-peace-review/generated'
            for name in lab.SOURCES:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((native_root/name).read_bytes())
            for name in lab.HOST_SOURCES:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((GEN/name).read_bytes())
            for name in lab.SUPPORT_SOURCES:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((ROOT/name).read_bytes())
            for name in lab.FIXTURE_SOURCES:
                path=lab.fixture_source_path(root,name);path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(lab.fixture_source_path(GEN,name).read_bytes())
            with patch.object(lab,'_private_root',lambda _:None):
                manifest=lab.record_build(root,output)
                self.assertEqual(manifest['schema_version'],2);self.assertEqual(lab.verify_build(root,output)[0],manifest)
                with self.assertRaises(ValueError):lab.record_build(root,output)
                path=root/lab.HOST_SOURCES[0];old=path.read_bytes();path.write_bytes(old+b'\n#changed')
                with self.assertRaises(ValueError):lab.verify_build(root,output)
                path.write_bytes(old)
                wire=(output/'build.json').read_bytes()
                for change in ({'schema_version':1},{'native_candidate_review_sha256':'0'*64},
                    {'owned_peace_stage_contract':lab.OWNED_PEACE_STAGE_CONTRACT|{'counts':[20,0,72,72]}},
                    {'host_source_sha256':{}},{'support_source_sha256':{}},{'source_sha256':{}},
                    {'runtime_verified':True}):
                    (output/'build.json').write_text(json.dumps(manifest|change))
                    with self.subTest(change=change),self.assertRaises(ValueError):lab.verify_build(root,output)
                (output/'build.json').write_bytes(wire)

if __name__=='__main__':
    output=io.StringIO();result=unittest.TextTestRunner(stream=output,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    print(json.dumps({'tests_run':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),
        'errors':len(result.errors),'details':output.getvalue(),'live_process_calls':0,'server_started':False}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
