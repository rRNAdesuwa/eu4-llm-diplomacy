"""Pure synthetic sparse-memory producer outputs; no actual inputs/process calls."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import reviewer as r

FULL, SPY, DENSE, PRODUCER_PINS = r.dependencies()

def load_fixture():
    path=r.ROOT/'work/candidates/spy-dense-full-observer-r2-1375/test_observer.py'
    spec=importlib.util.spec_from_file_location('_spy5_synthetic_full_fixture',path)
    old=sys.modules.get('observer');sys.modules['observer']=FULL
    try:
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    finally:
        if old is None:sys.modules.pop('observer',None)
        else:sys.modules['observer']=old
    m.MOCK.Fixture.GAME=r.WORLD
    return m

FIXTURE=load_fixture()

def records():
    f=FIXTURE.fixture();memory=f.m
    costs=[25000,50000,80000,70000,90000]  # Synthetic, sum315000; not claimed live per-family constants.
    definitions={};expiry={}
    for i,name in enumerate(r.ORDER):
        config=SPY.contract()['families'][name];definition=f.DEF+i*0x1000
        definitions[name]=definition
        memory.q(f.REG+config['registry_slot'],definition);memory.b(f.REG+config['registry_slot']+8,1)
        memory.q(definition,f.BASE+0x1c48378)
        f.name(definition+0x158,config['definition_key'],f.NAME+i*0x1000)
        memory.b(f.CAP+config['capability_offset'],1)
        memory.i(f.BASE+config['base_cost_rva'],costs[i])
        duration=60 if config['duration_to_days']==30 else 1825
        memory.i(f.BASE+config['duration_rva'],duration)
        expiry[name]=r.DATE+duration*config['duration_to_days']*24
    def census(phase):
        reports={}
        for name in r.ORDER:
            x=FULL.capture(memory,f.BASE,family=name)
            x['source_kind']='held_process_readonly'
            x['process']={'identity':{'pid':r.PID,'creation_filetime':r.CREATION,'exit_filetime':0,'module_base':f.BASE},
                          'path':str((r.ROOT.parent/'eu4.exe').resolve()),'disk_exe_sha256':SPY.EXE_SHA,
                          'loaded_full_image_hash_verified':False,'rights':['PROCESS_QUERY_INFORMATION','PROCESS_VM_READ']}
            reports[name]=x
        result = dict(kind='fixed_spy_mod_setup_ro_census',phase=phase,pid=r.PID,creation=r.CREATION,
                    expected_raw_date=r.DATE,source_pins=PRODUCER_PINS,spy_reports=reports,
                    subject_report={'synthetic_ancillary':True},diagnostic_report={'synthetic_ancillary':True},
                    game_native_calls=False,game_memory_written=False,individual_effect_verified=False,
                    production_ready=False,group_atomic=False,actual_cost_verified=False,status='captured',world=r.WORLD,
                    initial_reference_sha256='0'*64)
        if phase == 'after_ui_spy_batch':
            pins=r.verify_sources()
            result.update(initial_reference_sha256=r.INITIAL_SHA,ui_journal_sha256='1'*64,
                          setup_helper_sha256=pins['work/sample_spy_test_setup_ro_38232_1375.py'],
                          capture_helper_sha256=pins['work/sample_spy5_ui_batch_final_ro_38232_1375.py'],
                          capture_scope='read_only_final_after_manual_ui_batch',native_request_receipt=False)
        return result
    before=census('after_fixture')
    for i,name in enumerate(r.ORDER):
        node=f.NODE+i*0x100;obj=f.OBJ+i*0x100
        memory.put(node,struct.pack('<QQQB',obj,0 if i==0 else node-0x100,0 if i==4 else node+0x100,0))
        memory.q(obj,f.BASE+0x1ce8040);memory.i(obj+8,0x165);memory.q(obj+0x30,definitions[name])
        memory.q(obj+0x38,0);memory.i(obj+0x44,expiry[name])
    memory.q(f.TARGET+0x1f0,f.NODE);memory.q(f.TARGET+0x1f8,f.NODE+4*0x100);memory.i(f.TARGET+0x200,5)
    memory.put(f.record+0x18,struct.pack('<h',2125))
    after=census('after_ui_spy_batch')
    rows=[]
    for i in range(11):
        row=dict(event='start' if i==0 else ('intent' if i%2 else 'ui_confirmed'),
                 family=None if i==0 else r.ORDER[(i-1)//2],note='synthetic fixture',
                 recorded_utc=f'2026-10-08T00:00:{i:02d}+00:00',pid=r.PID,creation=r.CREATION,
                 world=hex(r.WORLD),initial_sha256=r.INITIAL_SHA,actor='FRA',target='ENG',
                 source='manual_game_ui_observation',native_request_receipt=False,
                 individual_effect_verified=False,production_ready=False)
        if i==0:row['plan']=list(r.ORDER)
        rows.append(row)
    return before,after,rows

class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.original=records()
    def inputs(self):return copy.deepcopy(self.original)
    def reject(self,inputs):
        with self.assertRaises((ValueError,KeyError,TypeError)):r.review_records(*inputs)
    def test_full_synthetic_batch_selected_and_balance_only(self):
        result=r.review_records(*self.inputs())
        self.assertEqual(result['batch_balance']['candidate_total_milli'],78750)
        self.assertEqual(len(result['families']),5)
        self.assertTrue(all(result[k] is False for k in r.FALSE_OUTPUT))
        self.assertTrue(all(x['observed_selected_presence'] is True and x['individual_effect_verified'] is False
                            for x in result['families'].values()))
    def test_journal_missing_duplicate_unknown_and_order(self):
        for mutate in [lambda x:x.pop(),lambda x:x.append(copy.deepcopy(x[-1])),
                       lambda x:x[4].update(event='unknown'),lambda x:x[2].update(family=r.ORDER[1]),
                       lambda x:x[3].update(event='ui_confirmed'),lambda x:x[0].update(plan=list(reversed(r.ORDER)))]:
            a=self.inputs();mutate(a[2]);self.reject(a)
    def test_journal_identity_source_and_false_claims(self):
        for key,value in [('pid',float(r.PID)),('pid',True),('creation','0000000000000001'),('world',r.WORLD),
                          ('target','POR'),('actor','ENG'),('initial_sha256','0'*64),('source','native'),
                          ('native_request_receipt',0),('individual_effect_verified',True),('note','x'*1025)]:
            a=self.inputs();a[2][6][key]=value;self.reject(a)
    def test_journal_timestamp_and_duplicate_json(self):
        for stamp in ['2026-10-08','2026-10-08T00:00:01Z','2026-10-07T00:00:00+00:00',True]:
            a=self.inputs();a[2][-1]['recorded_utc']=stamp;self.reject(a)
        for raw in [b'{"x":1,"x":1}',b'{"x":NaN}',b'{"x":Infinity}']:
            with self.assertRaises(ValueError):r.decode(raw)
    def test_outer_identity_types_and_incomplete_phase(self):
        for side in (0,1):
            for key,value in [('pid',float(r.PID)),('world',float(r.WORLD)),('expected_raw_date',float(r.DATE)),
                              ('status','unsupported_or_read_failed'),('group_atomic',0),('production_ready',1)]:
                a=self.inputs();a[side][key]=value;self.reject(a)
        a=self.inputs();a[1]['phase']='after_fixture';self.reject(a)
    def test_missing_or_extra_family(self):
        a=self.inputs();del a[1]['spy_reports'][r.ORDER[-1]];self.reject(a)
        a=self.inputs();a[0]['spy_reports']['wrong']={};self.reject(a)
    def test_held_identity_path_and_hash_each_family(self):
        for name in r.ORDER:
            for key,value in [('pid',True),('module_base',float(FIXTURE.MOCK.Fixture.BASE)),
                              ('creation_filetime',int(r.CREATION,16)),('exit_filetime',False)]:
                a=self.inputs();a[1]['spy_reports'][name]['process']['identity'][key]=value;self.reject(a)
        for key,value in [('path','eu4.exe'),('disk_exe_sha256','0'*64),('loaded_full_image_hash_verified',True),
                          ('rights',['PROCESS_ALL_ACCESS'])]:
            a=self.inputs();a[1]['spy_reports'][r.ORDER[0]]['process'][key]=value;self.reject(a)
    def test_full_and_nested_flags_strict(self):
        for field in ['full_envelope_equal','native_calls','actual_cost_verified','object_lifetime_verified']:
            a=self.inputs();x=a[1]['spy_reports'][r.ORDER[0]];x[field]=int(x[field]);self.reject(a)
        for side in ['before','after']:
            a=self.inputs();a[1]['spy_reports'][r.ORDER[0]][side]['two_pass_equal']=1;self.reject(a)
    def test_each_snapshot_typed_identity_and_selected(self):
        for phase in (0,1):
            for side in ['before','after']:
                for key in ['date','player','game','count']:
                    a=self.inputs();z=a[phase]['spy_reports'][r.ORDER[0]][side]['snapshot']['identity']
                    z[key]=float(z[key]);self.reject(a)
                a=self.inputs();a[phase]['spy_reports'][r.ORDER[0]][side]['selected']['unknown_objects_or_selected_semantics']=0;self.reject(a)
    def test_consistent_unknown_object_rejected(self):
        a=self.inputs()
        for report in a[1]['spy_reports'].values():
            for side in ('before','after'):
                cap=report[side];node=cap['snapshot']['modifiers']['nodes'][0]
                node.update(vtable=FIXTURE.MOCK.Fixture.BASE+0x1c48000,type_marker=None,fields=None)
                cap['selected']=SPY.selected(cap['snapshot'])
        self.reject(a)
    def test_expiry_associated_removed_and_typed_fields(self):
        for field,value in [('expiry',r.DATE-1),('expiry',r.DATE+1),('associated',0x78000000),('expiry',float(r.DATE))]:
            a=self.inputs()
            for report in a[1]['spy_reports'].values():
                for side in ('before','after'):
                    cap=report[side];cap['snapshot']['modifiers']['nodes'][0]['fields'][field]=value
                    cap['selected']=SPY.selected(cap['snapshot'])
            self.reject(a)
        a=self.inputs();a[1]['spy_reports'][r.ORDER[0]]['before']['snapshot']['modifiers']['nodes'][0]['flag']=True;self.reject(a)
    def test_absence_and_exactly_one_selected_new(self):
        a=self.inputs()
        for report in a[1]['spy_reports'].values():
            for side in ('before','after'):
                cap=report[side];cap['snapshot']['modifiers']=copy.deepcopy(a[0]['spy_reports'][r.ORDER[0]][side]['snapshot']['modifiers'])
                cap['selected']=SPY.selected(cap['snapshot'])
        self.reject(a)
    def test_network_consistency_and_balance(self):
        for value in [2124,10000,2125.0,True]:
            a=self.inputs()
            for report in a[1]['spy_reports'].values():
                for side in ('before','after'):report[side]['snapshot']['cost']['network_centipoints']=value
            self.reject(a)
    def test_dense_snapshot_scalar_aliases_both_passes(self):
        for side in ['before','after']:
            for key in ['base_milli','cache_state','transform_root','transform']:
                a=self.inputs();dense=a[0]['spy_reports'][r.ORDER[0]]['dense'][side]
                dense[key]=float(dense[key]);self.reject(a)
            for key in ['address','vtable','type_marker','dense','vector_vtable','data','capacity','count']:
                a=self.inputs();dense=a[0]['spy_reports'][r.ORDER[0]]['dense'][side]['aggregate']
                dense[key]=float(dense[key]);self.reject(a)
    def test_dense_unknown_bounds_and_identity(self):
        for key,value in [('cache_state',1),('status','unknown'),('transform',0x72000000)]:
            a=self.inputs();a[0]['spy_reports'][r.ORDER[0]]['dense']['before'][key]=value;self.reject(a)
        for key,value in [('capacity',500),('count',0),('vtable',0),('data',0)]:
            a=self.inputs();a[0]['spy_reports'][r.ORDER[0]]['dense']['before']['aggregate'][key]=value;self.reject(a)
        a=self.inputs();a[0]['spy_reports'][r.ORDER[0]]['dense']['before']['aggregate']['selected_record']['id']=2;self.reject(a)
    def test_cross_envelope_and_cross_family_dense(self):
        a=self.inputs();a[0]['spy_reports'][r.ORDER[0]]['dense']['before']['aggregate']['data']+=8;self.reject(a)
        a=self.inputs();a[0]['spy_reports'][r.ORDER[0]]['cost_binding']['observed_common_fields']=[];self.reject(a)
        a=self.inputs();a[0]['spy_reports'][r.ORDER[0]]['dense']['final_milli_candidate']+=1;self.reject(a)
    def test_trace_schema_counts_and_budget(self):
        for key,value in [('calls',0),('bytes',False),('max_bytes',2**32)]:
            a=self.inputs();a[0]['spy_reports'][r.ORDER[0]]['before']['read_budget'][key]=value;self.reject(a)
        a=self.inputs();a[0]['spy_reports'][r.ORDER[0]]['dense']['reads'][0]['sha256']='bad';self.reject(a)
        a=self.inputs();a[0]['spy_reports'][r.ORDER[0]]['read_budget']['bytes']=1;self.reject(a)
    def test_no_osi_entry_called(self):
        with patch.object(FULL,'sample_process',side_effect=AssertionError('process entry')), \
             patch.object(SPY,'sample_process',side_effect=AssertionError('process entry')):
            r.review_records(*self.inputs())
    def test_existing_output_and_bad_case_hash_preserve_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);out=d/'out.json';out.write_bytes(b'keep')
            with self.assertRaisesRegex(ValueError,'CREATE_NEW'):r.review_case(d/'none', '0'*64,out)
            self.assertEqual(out.read_bytes(),b'keep')
            case=d/'case.json';case.write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'case hash'):r.review_case(case,'0'*64,d/'new.json')
            self.assertFalse((d/'new.json').exists())
    def test_final_producer_and_initial_references(self):
        for key,value in [('initial_reference_sha256','0'*64),('capture_helper_sha256','0'*64),
                          ('setup_helper_sha256','0'*64),('capture_scope','native_sender'),
                          ('native_request_receipt',0),('ui_journal_sha256',False)]:
            a=self.inputs();a[1][key]=value;self.reject(a)
        a=self.inputs();del a[1]['capture_scope'];self.reject(a)
    def test_source_pin_substitution_and_budget_upper_bound(self):
        a=self.inputs();a[0]['source_pins']={};self.reject(a)
        a=self.inputs();a[1]['spy_reports'][r.ORDER[0]]['source_pins']={};self.reject(a)
        with tempfile.TemporaryDirectory()as tmp:
            p=Path(tmp)/'bounded';p.write_bytes(b'012345')
            with self.assertRaisesRegex(ValueError,'budget'):r.bounded(p,5)
    def test_old_object_reused_cannot_prove_new_selected(self):
        a=self.inputs();node=copy.deepcopy(a[1]['spy_reports'][r.ORDER[0]]['before']['snapshot']['modifiers']['nodes'][0])
        node['next']=0;node['fields']['definition']=0x7f000000
        state=dict(head=node['address'],tail=node['address'],count=1,nodes=[node])
        for report in a[0]['spy_reports'].values():
            for side in ('before','after'):
                report[side]['snapshot']['modifiers']=copy.deepcopy(state)
                report[side]['selected']=SPY.selected(report[side]['snapshot'])
        self.reject(a)
    def test_synthetic_file_entry_and_exact_journal_hash(self):
        # Full file entry in an isolated temporary fake repository. Only fixed
        # initial SHA/root/source-check are test substitutions; pure review
        # functions and input hashing/path/schema/output code execute unchanged.
        pins=r.verify_sources()
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);(root/'work/runtime').mkdir(parents=True)
            before,after,rows=self.inputs()
            for census in (before,after):
                for record in census['spy_reports'].values():
                    record['process']['path']=str((root.parent/'eu4.exe').resolve())
            enc=lambda x:(json.dumps(x,sort_keys=True)+'\n').encode()
            before_raw=enc(before);initial_sha=hashlib.sha256(before_raw).hexdigest()
            for row in rows:row['initial_sha256']=initial_sha
            journal_raw=b''.join(enc(row)for row in rows);journal_sha=hashlib.sha256(journal_raw).hexdigest()
            after.update(initial_reference_sha256=initial_sha,ui_journal_sha256=journal_sha)
            blobs={'before':before_raw,'after':enc(after),'journal':journal_raw}
            paths={'before':r.INITIAL_PATH,'after':r.FINAL_PATH,'journal':r.JOURNAL_PATH}
            def write_case():
                inputs={}
                for name,raw in blobs.items():
                    (root/paths[name]).write_bytes(raw)
                    inputs[name]=dict(path=paths[name],sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
                case=dict(schema=1,purpose='fixed_spy5_ui_batch_38232_r2',
                          identity=dict(pid=r.PID,creation=r.CREATION,world=r.WORLD,raw_date=r.DATE,actor='FRA',target='ENG'),
                          inputs=inputs)
                p=root/'case.json';p.write_bytes(enc(case));return p,r.sha(p)
            case,case_sha=write_case()
            with patch.object(r,'ROOT',root),patch.object(r,'INITIAL_SHA',initial_sha), \
                 patch.object(r,'verify_sources',return_value=pins):
                output=root/'summary.json';result=r.review_case(case,case_sha,output)
                self.assertEqual(result['status'],'reviewed_manual_ui_batch_selected_observation')
                self.assertTrue(output.exists());self.assertFalse(result['execution_verified'])
                after['ui_journal_sha256']='0'*64;blobs['after']=enc(after);case,case_sha=write_case()
                with self.assertRaisesRegex(ValueError,'journal hash'):r.review_case(case,case_sha,root/'bad.json')
                self.assertFalse((root/'bad.json').exists())

if __name__=='__main__':unittest.main()
