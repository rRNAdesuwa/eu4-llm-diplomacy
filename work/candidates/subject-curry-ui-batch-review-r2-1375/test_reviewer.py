"""Sparse synthetic producer records only; no game/actual census read."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import reviewer as r

MODS,PRODUCER_PINS=r.dependencies()

def fixture_module(name,observer):
    path=r.ROOT/f'work/candidates/{name}-observer-1375/test_observer.py'
    spec=importlib.util.spec_from_file_location('_batch_fixture_'+name,path)
    module=importlib.util.module_from_spec(spec);old=sys.modules.get('observer');sys.modules['observer']=observer
    try:spec.loader.exec_module(module)
    finally:
        if old is None:sys.modules.pop('observer',None)
        else:sys.modules['observer']=old
    return module

TF=fixture_module('subject-toggle',MODS['toggles'])
CF=fixture_module('curry-favors',MODS['curry'])

class SubjectFixture(TF.Fixture):GAME=r.WORLD
class CurryFixture(CF.Fixture):GAME=r.WORLD;POR=0x71280000

def records():
    subject=SubjectFixture();curry=CurryFixture(False)
    subject.m.i(subject.FRA+0x2258,0)
    pins=r.verify_sources()
    held=dict(pid=r.PID,creation_filetime=r.CREATION,exit_filetime=0,module_base=subject.BASE)
    process=dict(identity=held,path=str((r.ROOT.parent/'eu4.exe').resolve()),disk_exe_sha256=MODS['focus'].EXE_SHA,
                 loaded_full_image_hash_verified=False,rights=['PROCESS_QUERY_INFORMATION','PROCESS_VM_READ'])
    def census(phase):
        c=MODS['curry'].capture(curry.m,curry.BASE)
        f=MODS['focus'].capture(subject.m,subject.BASE)
        t=MODS['toggles'].capture(subject.m,subject.BASE)
        for x in (c,f,t):x['source_kind']='held_process_readonly'
        c['process']=copy.deepcopy(process);f['process']=copy.deepcopy(process)
        t['process']=dict(pid=r.PID,creation=r.CREATION,before=copy.deepcopy(held),after=copy.deepcopy(held),
            executable=process['path'],disk_exe_sha256=process['disk_exe_sha256'],loaded_full_image_hash_verified=False,rights=process['rights'])
        return dict(kind='fixed_subject_and_curry_ui_selected_census',phase=phase,pid=r.PID,creation=r.CREATION,
            world=r.WORLD,raw_date=r.DATE,source_pins=PRODUCER_PINS,capture_helper_sha256=pins[r.WRAPPER],
            reports=dict(curry=c,military_focus=f,subject_toggles=t),group_atomic=False,game_native_calls=False,
            game_memory_written=False,individual_effect_verified=False,production_ready=False,native_request_receipt=False,
            initial_reference_sha256=None if phase=='before_ui'else r.INITIAL_SHA,status='captured')
    before=census('before_ui')
    subject.m.i(subject.NAV+0x2864,5);subject.m.i(subject.NAV+0x78,0x52);subject.m.i(subject.FRA+0x2258,1)
    curry.m.i(curry.ROOT+0x164,1);curry.entry(curry.ENTRY,0,curry.MISSION,2)
    after=census('after_ui');rows=[]
    for i in range(13):
        row=dict(event='start'if i==0 else('intent'if i%2 else'ui_confirmed'),action=None if i==0 else r.PLAN[(i-1)//2][0],
            note='synthetic only',recorded_utc=f'2026-10-08T00:00:{i:02d}+00:00',pid=r.PID,creation=r.CREATION,
            world=hex(r.WORLD),initial_sha256=r.INITIAL_SHA,actor='FRA',source='manual_game_ui_observation',
            native_request_receipt=False,individual_effect_verified=False,production_ready=False)
        if i==0:row['plan']=[list(x)for x in r.PLAN]
        else:row.update(target=r.PLAN[(i-1)//2][1],requested_value=r.PLAN[(i-1)//2][2])
        rows.append(row)
    return before,after,rows

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.original=records()
    def inputs(self):return copy.deepcopy(self.original)
    def reject(self,x):
        with self.assertRaises((ValueError,KeyError,TypeError)):r.review_records(*x)
    def test_complete_synthetic_batch_flags_focus_curry_and_rival_count(self):
        result=r.review_records(*self.inputs())
        self.assertEqual(result['military_focus']['after'],5);self.assertEqual(result['rival_count']['after'],1)
        self.assertEqual(result['curry_graph']['matching_missions'],1)
        self.assertTrue(all(result[k]is False for k in r.FALSE_OUTPUT))
    def test_source_pins_missing_reports_and_phase(self):
        for key,val in [('source_pins',{}),('capture_helper_sha256','0'*64),('status','unknown'),('phase','before_ui')]:
            x=self.inputs();x[1][key]=val;self.reject(x)
        x=self.inputs();del x[0]['reports']['military_focus'];self.reject(x)
    def test_outer_identity_aliases_every_phase(self):
        for side in (0,1):
            for key in ('pid','world','raw_date'):
                for bad in (True,float(self.original[side][key])):
                    x=self.inputs();x[side][key]=bad;self.reject(x)
            for key,bad in [('creation',int(r.CREATION,16)),('group_atomic',0),('native_request_receipt',0),('production_ready',True)]:
                x=self.inputs();x[side][key]=bad;self.reject(x)
    def test_exact_journal_order_confirmations_and_targets(self):
        for at in range(1,13):
            for key,val in [('event','unknown'),('target','ENG'),('action','wrong'),('native_request_receipt',0)]:
                x=self.inputs();x[2][at][key]=val;self.reject(x)
        for mutation in (lambda rows:rows.pop(),lambda rows:rows.append(rows[-1]),lambda rows:rows.reverse()):
            x=self.inputs();mutation(x[2]);self.reject(x)
    def test_typed_journal_value_and_timestamp(self):
        for at in range(1,13):
            original=self.original[2][at]['requested_value']
            for val in (float(original),int(original)):
                if type(original)is type(val):continue
                x=self.inputs();x[2][at]['requested_value']=val;self.reject(x)
        for key,val in [('recorded_utc','2026-10-08'),('recorded_utc','2026-10-07T00:00:00+00:00'),('initial_sha256','0'*64),('note','x'*1025),('source','native')]:
            x=self.inputs();x[2][-1][key]=val;self.reject(x)
    def test_every_held_scope_must_match(self):
        for side in (0,1):
            for name in ('curry','military_focus','subject_toggles'):
                p=self.original[side]['reports'][name]['process'];ident='before'if name=='subject_toggles'else'identity'
                for key,val in [('pid',True),('creation_filetime',int(r.CREATION,16)),('module_base',float(p[ident]['module_base'])),('exit_filetime',False)]:
                    x=self.inputs();x[side]['reports'][name]['process'][ident][key]=val;self.reject(x)
                x=self.inputs();x[side]['reports'][name]['source_kind']='injected_reader_not_process_attested';self.reject(x)
    def test_both_curry_and_toggle_passes_not_summary_only(self):
        for name in ('curry','subject_toggles'):
            for at in (0,1):
                x=self.inputs();s=x[1]['reports'][name]['passes'][at]
                z=s['identity']if name=='curry'else s['graph']['identity'];z['date']=float(z['date']);self.reject(x)
        x=self.inputs();x[1]['reports']['curry']['state']['active_graph_observed']=1;self.reject(x)
        x=self.inputs();x[1]['reports']['subject_toggles']['snapshot']['states']['scutage']['current']=1;self.reject(x)
    def test_focus_snapshot_flag_and_common_graph_binding(self):
        for key,val in [('two_pass_equal',1),('entitlement','verified'),('effect_verified',True)]:
            x=self.inputs();x[0]['reports']['military_focus'][key]=val;self.reject(x)
        x=self.inputs();x[1]['reports']['military_focus']['snapshot']['focus']=4;self.reject(x)
        x=self.inputs();x[1]['reports']['military_focus']['snapshot']['identity']['countries']['FRA']['address']+=8;self.reject(x)
    def test_trace_budget_calls_bytes_types_each_observer(self):
        for name in ('curry','military_focus','subject_toggles'):
            for key,val in [('calls',1),('calls',8193),('bytes',1),('bytes',True),('max_calls',16384)]:
                x=self.inputs();x[1]['reports'][name]['read_budget'][key]=val;self.reject(x)
            x=self.inputs();x[0]['reports'][name]['trace'][0]['size']=False;self.reject(x)
    def test_real_rival_change_required_not_blanket_stability(self):
        for val in (0,2,True,1.0):
            x=self.inputs();report=x[1]['reports']['subject_toggles']
            for snapshot in [*report['passes'],report['snapshot']]:
                snapshot['raw_fields']['actor_rival_count']=val
                snapshot['states']=MODS['toggles'].selected_states(snapshot['graph'],snapshot['raw_fields'],snapshot['permission_map'],MODS['toggles'].contract())
            self.reject(x)
    def test_unrelated_subject_bits_and_gate_changes_rejected(self):
        x=self.inputs();report=x[1]['reports']['subject_toggles']
        for snapshot in [*report['passes'],report['snapshot']]:snapshot['raw_fields']['subject_flags']|=0x100
        self.reject(x)
        x=self.inputs();report=x[1]['reports']['subject_toggles']
        for snapshot in [*report['passes'],report['snapshot']]:snapshot['raw_fields']['actor_presence']+=1
        self.reject(x)
    def test_curry_inactive_unknown_relation_and_mission_not_accepted(self):
        for kind in ('absent','wrongtoken','unknown','wrongdate'):
            x=self.inputs();report=x[1]['reports']['curry']
            if kind=='absent':x[1]['reports']['curry']=copy.deepcopy(x[0]['reports']['curry'])
            else:
                for s in report['passes']:
                    if kind=='wrongtoken':s['envoys']['fields']['entries'][0]['fields']['mission_object']['fields']['token']=0x2ddb
                    elif kind=='unknown':
                        s['relation']['vtable']+=8
                        s['relation'].update(marker=None,removed=None,fields=None)
                    else:s['relation']['fields']['started']=r.DATE-1
                report['state']=MODS['curry'].selected(report['passes'][0])
            self.reject(x)
    def test_no_process_entry_called(self):
        with (patch.object(MODS['curry'],'sample_process',side_effect=AssertionError('process')),
              patch.object(MODS['focus'],'sample_process',side_effect=AssertionError('process')),
              patch.object(MODS['toggles'],'sample_process',side_effect=AssertionError('process'))):
            r.review_records(*self.inputs())
    def test_common_world_country_and_date_consistent_aliases(self):
        for field,bad in [('database',0x7f000000),('count',301),('date',r.DATE+1)]:
            x=self.inputs();report=x[1]['reports']['curry']
            for s in report['passes']:s['identity'][field]=bad
            report['state']=MODS['curry'].selected(report['passes'][0]);self.reject(x)
        x=self.inputs();x[1]['reports']['curry']['process']['identity']['creation_filetime']='01dd56e0cbe2c7f8';self.reject(x)
    def test_not_claiming_effect_from_manual_evidence(self):
        x=self.inputs();result=r.review_records(*x)
        self.assertEqual(result['rival_count']['target_evidence'],'manual_UI_journal_only')
        self.assertFalse(result['rival_target_ro_verified'])
        for row in result['subject_flags'].values():
            self.assertFalse(row['individual_effect_verified']);self.assertFalse(row['side_effects_verified'])
        x[2][2]['requested_value']=False;self.reject(x)
    def test_after_initial_hash_and_unavailable_snapshot_refused(self):
        for key,bad in [('initial_reference_sha256','0'*64),('status','unsupported_or_read_failed')]:
            x=self.inputs();x[1][key]=bad;self.reject(x)
        x=self.inputs();x[0]['initial_reference_sha256']=r.INITIAL_SHA;self.reject(x)
    def test_complete_file_entry_in_temporary_synthetic_repository(self):
        # Only file namespace/source-root attestation is replaced for this fake
        # repository. Full typed validators, input hashing, journal and output
        # CREATE_NEW logic run unchanged; no actual census is opened.
        pins=r.verify_sources()
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);(root/'work/runtime').mkdir(parents=True)
            before,after,rows=self.inputs()
            for census in (before,after):
                for name,report in census['reports'].items():
                    report['process']['executable'if name=='subject_toggles'else'path']=str((root.parent/'eu4.exe').resolve())
            enc=lambda value:(json.dumps(value,sort_keys=True)+'\n').encode()
            before_raw=enc(before);before_sha=hashlib.sha256(before_raw).hexdigest();after['initial_reference_sha256']=before_sha
            for row in rows:row['initial_sha256']=before_sha
            blobs={'before':before_raw,'after':enc(after),'journal':b''.join(enc(row)for row in rows)}
            inputs={}
            for key,raw in blobs.items():
                (root/r.PATHS[key]).write_bytes(raw);inputs[key]=dict(path=r.PATHS[key],bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
            case=dict(schema=1,purpose='fixed_subject_curry_ui_batch_r2_38232',inputs=inputs,
                      identity=dict(pid=r.PID,creation=r.CREATION,world=r.WORLD,raw_date=r.DATE,actor='FRA',subject='NAV',curry_target='POR'))
            cp=root/'case.json';cp.write_bytes(enc(case));case_sha=hashlib.sha256(enc(case)).hexdigest()
            with (patch.object(r,'ROOT',root),patch.object(r,'INITIAL_SHA',before_sha),patch.object(r,'verify_sources',return_value=pins),
                  patch.object(MODS['curry'],'ROOT',root),patch.object(MODS['toggles'],'ROOT',root)):
                output=root/'summary.json';result=r.review_case(cp,case_sha,output)
                self.assertFalse(result['execution_verified']);self.assertTrue(output.exists())
                (root/r.PATHS['journal']).write_bytes(blobs['journal']+b'{}\n')
                with self.assertRaisesRegex(ValueError,'input hash'):r.review_case(cp,case_sha,root/'bad.json')
                self.assertFalse((root/'bad.json').exists())
    def test_create_new_bad_case_hash_and_json_ambiguity(self):
        with tempfile.TemporaryDirectory()as d:
            p=Path(d);output=p/'summary.json';output.write_bytes(b'keep')
            with self.assertRaisesRegex(ValueError,'CREATE_NEW'):r.review_case(p/'missing','0'*64,output)
            self.assertEqual(output.read_bytes(),b'keep')
            case=p/'case.json';case.write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'case hash'):r.review_case(case,'0'*64,p/'new.json')
            self.assertFalse((p/'new.json').exists())
            source=p/'large';source.write_bytes(b'123456')
            with self.assertRaises(ValueError):r.bounded(source,5)
        for raw in (b'{"a":1,"a":1}',b'{"a":NaN}',b'{"a":Infinity}'):
            with self.assertRaises(ValueError):r.decode(raw)


class SharedRecordsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.original=records()
    def rejected(self,x):
        with self.assertRaises((ValueError,KeyError,TypeError)):r.review_records(*x)
    def test_three_original_complete_pipeline_counterexamples(self):
        for phases in ((0,),(1,),(0,1)):
            x=copy.deepcopy(self.original)
            for side in phases:
                for snap in x[side]['reports']['curry']['passes']:
                    snap['index']['records']+=0x1000000;snap['index']['record']+=0x1000000
            self.rejected(x)
    def test_shared_pointer_typed_on_every_side(self):
        for side in (0,1):
            for family in ('curry','military_focus','subject_toggles'):
                for bad in (True,False,0,float(0x72000000),'1929379840',None):
                    x=copy.deepcopy(self.original);v=x[side]['reports'][family]
                    if family=='curry':
                        for snap in v['passes']:snap['index']['records']=bad
                    elif family=='military_focus':v['snapshot']['left']['records']=bad
                    else:
                        v['snapshot']['graph']['left']['records']=bad
                        for snap in v['passes']:snap['graph']['left']['records']=bad
                    self.rejected(x)
    def test_equal_shared_records_distinct_target_roots_allowed(self):
        x=copy.deepcopy(self.original)
        for side in (0,1):
            p=x[side]['reports'];c=p['curry']['passes'][0]['index'];f=p['military_focus']['snapshot']['left']
            self.assertEqual(c['records'],f['records']);self.assertNotEqual(c['root'],f['root'])
        result=r.review_records(*x);self.assertIs(result['group_atomic'],False)
        self.assertIs(result['individual_effect_verified'],False)
    def test_equal_shared_pointer_integer_boundary_is_not_relaxed(self):
        for bad in (65535,2**47):
            x=copy.deepcopy(self.original)
            for side in (0,1):
                p=x[side]['reports']
                for snap in p['curry']['passes']:snap['index']['records']=bad
                p['military_focus']['snapshot']['left']['records']=bad
                p['subject_toggles']['snapshot']['graph']['left']['records']=bad
                for snap in p['subject_toggles']['passes']:snap['graph']['left']['records']=bad
            self.rejected(x)

if __name__=='__main__':unittest.main()
