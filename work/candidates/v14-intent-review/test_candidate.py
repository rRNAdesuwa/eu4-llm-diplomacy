"""Actual Windows temp-file stage publications; no game/process/native calls."""
from __future__ import annotations
from copy import deepcopy
import contextlib
import hashlib
import importlib.util
import io
import json
import os
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


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module)
    if '.' in name:
        package,leaf=name.rsplit('.',1);setattr(sys.modules[package],leaf,module)
    return module


# Use preserved synthetic log data from the reviewed v13 candidate. This loads
# no real logs and invokes no entrypoint. v14 modules themselves are actual new
# generated sources, not copies of the implementation under test.
fixtures=load('v13_synthetic_fixture_data',ROOT/'work/candidates/v13-host-review/test_candidate.py')
GEN=HERE/'generated'
for name in ('lifecycle','preview','command','owned_peace'):
    load('tools.verify_diplomacy_'+name+'_v14',GEN/f'tools/verify_diplomacy_{name}_v14.py')
lab=load('work.native.lab_protocol_v14_1375',GEN/'work/native/lab_protocol_v14_1375.py')
prior=fixtures.lab


@unittest.skipUnless(os.name=='nt','Requires real Win32 NTFS temp-file contract')
class PublicationTests(unittest.TestCase):
    def fixture(self,phase,protocol=lab):
        base=fixtures.CandidateTests();base.setUp();self.addCleanup(base.doCleanups)
        f=base.f
        # Report the actual filesystem, not merely the host operating system.
        fs=lab.C.create_unicode_buffer(32)
        kernel=lab.C.WinDLL('kernel32',use_last_error=True)
        kernel.GetVolumeInformationW.argtypes=[lab.W.LPCWSTR,lab.W.LPWSTR,lab.W.DWORD,
            lab.C.c_void_p,lab.C.c_void_p,lab.C.c_void_p,lab.W.LPWSTR,lab.W.DWORD]
        kernel.GetVolumeInformationW.restype=lab.W.BOOL
        self.assertTrue(kernel.GetVolumeInformationW(f.session.anchor,None,0,None,None,None,fs,len(fs)))
        self.assertEqual(fs.value,'NTFS')
        f.metadata['purpose']=protocol.PURPOSE
        names={'lifecycle':'pair_selftest_begin','owned_peace':'owned_peace_selftest_begin',
            'preview':'pair_preview_begin','command':'pair_command_begin'}
        i=next(i for i,e in enumerate(f.events) if e['event']==names[phase])
        f.events=f.events[:i]
        for name in ('session.json','install.claim'):(f.session/name).write_text(json.dumps(f.metadata))
        order=tuple(protocol.PHASES)
        for p,(_,claim,_) in protocol.PHASES.items():
            path=f.session/claim
            if order.index(p)>=order.index(phase):path.unlink(missing_ok=True)
            else:path.write_bytes(protocol.phase_wire(p,f.metadata))
        f.write()
        self.enterContext(patch.object(protocol,'LiveLabProcess',side_effect=AssertionError('No game access')))
        self.enterContext(patch.object(protocol,'_private_root',lambda _:None))
        return f

    def read(self,f,protocol=lab):return protocol.read_evidence(f.session,f.metadata)
    def publish(self,f,phase,*,recheck=None,evidence=None,protocol=lab):
        evidence=evidence or self.read(f,protocol)
        clock=lambda:evidence['latest_frame']['uptime_ms']+1
        return protocol.publish_research(f.session,f.metadata,'a'*64,evidence,f.live,phase=phase,
            clock=clock,recheck=recheck or (lambda:(self.read(f,protocol),dict(f.live))))

    def test_reproduces_frozen_v13_failure_with_real_recheck(self):
        f=self.fixture('lifecycle',prior)
        with self.assertRaisesRegex(ValueError,'already claimed, intended or started'):
            self.publish(f,'lifecycle',protocol=prior)
        marker,claim,_=prior.PHASES['lifecycle']
        self.assertTrue((f.session/(claim+'.host-intent')).is_file())
        self.assertFalse((f.session/marker).exists());self.assertFalse((f.session/claim).exists())

    def test_all_four_phases_real_filesystem_recheck(self):
        for phase in lab.PHASES:
            with self.subTest(phase=phase):
                f=self.fixture(phase);seen=[]
                def recheck():
                    evidence=self.read(f)
                    self.assertTrue(evidence['phase_attempted'][phase])
                    self.assertEqual(evidence['phase_attempt_sources'][phase],dict(native_started=False,native_claim=False,host_intent=True))
                    seen.append(evidence)
                    return evidence,dict(f.live)
                result=self.publish(f,phase,recheck=recheck)
                marker,claim,_=lab.PHASES[phase]
                self.assertEqual(result['status'],'published');self.assertEqual(len(seen),1)
                self.assertEqual((f.session/marker).read_bytes(),lab.phase_wire(phase,f.metadata))
                self.assertTrue((f.session/(claim+'.host-intent')).is_file());self.assertFalse((f.session/claim).exists())
                # The original evidence object is not modified by the local projection.
                self.assertTrue(seen[0]['phase_attempted'][phase])
                with self.assertRaises(ValueError):self.publish(f,phase)

    def test_preexisting_identical_or_foreign_intent_never_owned(self):
        for raw in (b'foreign',None):
            f=self.fixture('lifecycle');evidence=self.read(f)
            marker,claim,_=lab.PHASES['lifecycle'];path=f.session/(claim+'.host-intent')
            if raw is None:
                body=lab.phase_wire('lifecycle',f.metadata)
                raw=(lab.canonical(dict(protocol=lab.PROTOCOL,purpose=lab.PURPOSE,pid=f.pid,creation=f.creation,
                    manifest_sha256='a'*64,request_sha256=hashlib.sha256(body).hexdigest(),body_ascii=body.decode(),automatic_retry=False))+'\n').encode()
            path.write_bytes(raw)
            with self.assertRaises((ValueError,OSError)):self.publish(f,'lifecycle',evidence=evidence)
            self.assertEqual(path.read_bytes(),raw);self.assertFalse((f.session/marker).exists())

    def test_windows_held_file_denies_write_truncate_delete_and_replace(self):
        for operation in ('write','truncate','delete','replace'):
            with self.subTest(operation=operation):
                f=self.fixture('lifecycle');marker,claim,_=lab.PHASES['lifecycle'];path=f.session/(claim+'.host-intent')
                def recheck():
                    contents=path.read_bytes()  # FILE_SHARE_READ succeeds.
                    with self.assertRaises(OSError):
                        if operation=='write':path.write_bytes(b'corrupt')
                        elif operation=='truncate':
                            with path.open('r+b') as stream:stream.truncate(0)
                        elif operation=='delete':path.unlink()
                        else:
                            replacement=f.session/'replacement.tmp';replacement.write_bytes(contents);os.replace(replacement,path)
                    self.assertEqual(path.read_bytes(),contents)
                    raise ValueError('stop after denied interference')
                with self.assertRaisesRegex(ValueError,'stop after'):self.publish(f,'lifecycle',recheck=recheck)
                self.assertFalse((f.session/marker).exists());self.assertTrue(path.is_file())
                with self.assertRaises(ValueError):self.publish(f,'lifecycle')

    def test_request_or_native_claim_appearing_during_recheck_rejected(self):
        for what in ('claim','marker','other_request'):
            with self.subTest(what=what):
                f=self.fixture('lifecycle');marker,claim,_=lab.PHASES['lifecycle']
                chosen={'claim':claim,'marker':marker,'other_request':'00000000000000000001.request'}[what]
                def recheck():
                    (f.session/chosen).write_bytes(lab.phase_wire('lifecycle',f.metadata))
                    return self.read(f),dict(f.live)
                with self.assertRaises(ValueError):self.publish(f,'lifecycle',recheck=recheck)
                self.assertTrue((f.session/(claim+'.host-intent')).exists())
                if what!='marker':self.assertFalse((f.session/marker).exists())

    def test_started_native_stage_cannot_be_hidden_by_current_intent(self):
        f=self.fixture('lifecycle');marker,claim,_=lab.PHASES['lifecycle']
        def recheck():
            (f.session/claim).write_bytes(lab.phase_wire('lifecycle',f.metadata))
            f.events.append(dict(event='pair_selftest_begin',send_enabled=False));f.write()
            return self.read(f),dict(f.live)
        with self.assertRaises(ValueError):self.publish(f,'lifecycle',recheck=recheck)
        self.assertFalse((f.session/marker).exists())
        self.assertTrue((f.session/(claim+'.host-intent')).is_file())

    def test_stale_heartbeat_changed_identity_and_throw_leave_permanent_intent(self):
        for bad in ('world','creation','pid','player','time','exception'):
            with self.subTest(bad=bad):
                f=self.fixture('lifecycle');marker,claim,_=lab.PHASES['lifecycle']
                def recheck():
                    e=self.read(f);live=dict(f.live)
                    if bad=='world':live['world_cookie']='0x30000000'
                    elif bad=='creation':live['creation']='01da123456789abd'
                    elif bad=='pid':live['pid']+=1
                    elif bad=='player':live['player_handle']='0x010000bb00474e45'
                    elif bad=='time':e['latest_frame']['uptime_ms']+=lab.FRAME_MAX_AGE+1
                    else:raise ValueError('fresh read failed')
                    return e,live
                with self.assertRaises(ValueError):self.publish(f,'lifecycle',recheck=recheck)
                self.assertFalse((f.session/marker).exists());self.assertTrue((f.session/(claim+'.host-intent')).exists())
                with self.assertRaises(ValueError):self.publish(f,'lifecycle')

    def test_phase_requires_real_recheck_callback_before_creating_intent(self):
        f=self.fixture('lifecycle');e=self.read(f)
        with self.assertRaisesRegex(ValueError,'requires fresh filesystem evidence'):
            lab.publish_research(f.session,f.metadata,'a'*64,e,f.live,phase='lifecycle',clock=lambda:e['latest_frame']['uptime_ms'])
        self.assertFalse((f.session/'phase-lifecycle.claim.host-intent').exists())

    def test_public_readiness_stays_fail_closed(self):
        f=self.fixture('lifecycle');e=self.read(f)
        e['phase_attempted']['lifecycle']=True
        with self.assertRaises(ValueError):lab.check_ready(e,f.live,e['latest_frame']['uptime_ms'],phase='lifecycle')

    def test_missing_or_nonboolean_attempt_diagnostics_rejected(self):
        for changed in (None,{},dict(native_started=0,native_claim=False,host_intent=True),
                        dict(native_started=False,native_claim=False,host_intent=1)):
            f=self.fixture('lifecycle');marker,claim,_=lab.PHASES['lifecycle']
            def recheck():
                e=self.read(f)
                if changed is None:e.pop('phase_attempt_sources')
                elif not changed:e['phase_attempt_sources']={}
                else:e['phase_attempt_sources']['lifecycle']=changed
                return e,dict(f.live)
            with self.assertRaises(ValueError):self.publish(f,'lifecycle',recheck=recheck)
            self.assertFalse((f.session/marker).exists());self.assertTrue((f.session/(claim+'.host-intent')).exists())

    def test_nonphase_publication_keeps_existing_semantics(self):
        base=fixtures.CandidateTests();base.setUp();self.addCleanup(base.doCleanups);f=base.f
        f.metadata['purpose']=lab.PURPOSE
        for name in ('session.json','install.claim'):(f.session/name).write_text(json.dumps(f.metadata))
        (f.session/lab.PHASES['owned_peace'][1]).write_bytes(lab.phase_wire('owned_peace',f.metadata));f.write()
        self.enterContext(patch.object(lab,'_private_root',lambda _:None))
        e=self.read(f)
        result=lab.publish_research(f.session,f.metadata,'a'*64,e,f.live,sequence=1,operation='pair',
            mode='legality_only',action='improve_relations',target='ENG',clock=lambda:e['latest_frame']['uptime_ms']+1,
            recheck=lambda:(self.read(f),dict(f.live)))
        self.assertEqual(result['status'],'published');self.assertTrue((f.session/'00000000000000000001.host-intent').exists())

    def test_default_owned_peace_wrong_pid_claim_remains_rejected(self):
        f=self.fixture('preview')
        path=f.session/lab.PHASES['owned_peace'][1]
        path.write_bytes(lab.phase_wire('owned_peace',f.metadata|{'pid':f.pid+1}))
        with self.assertRaises(ValueError):self.read(f)


def main():
    stream=io.StringIO();suite=unittest.defaultTestLoader.loadTestsFromTestCase(PublicationTests)
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    print(json.dumps({'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'skipped':len(result.skipped),'passed':result.wasSuccessful() and not result.skipped,
        'actual_windows_filesystem':os.name=='nt','required_filesystem':'NTFS','game_accessed':False,'details':stream.getvalue()}))
    return 0 if result.wasSuccessful() and not result.skipped else 1
if __name__=='__main__':raise SystemExit(main())
