"""Synthetic whole-file replay and tempfile publication; no actual process."""
from pathlib import Path
from contextlib import contextmanager
import copy,json,tempfile,unittest
from unittest.mock import patch
from _base import base,check
import coherent as r
import client_r3 as wrapper

b=base.client.b;wire=base.client.wire;client=wrapper.client
fixture=base._module(base.OLD/'test_capture.py',{'build_manifest':b,'wire':wire,'real_capture':base.reader,'client':client})

class Kernel:
    def __init__(self):self.closed=0
    def WaitForSingleObject(self,*args):return 0x102
    def CloseHandle(self,*args):self.closed+=1;return True

class Files:
    def __init__(self,path):
        self.path=path;self.first=fixture.synthetic()[0]
        raw,outer,self.identity,_=self.capture(1)
        self.session=wire.session_path(path,self.identity);self.session.mkdir()
        self.rawpath=self.session/'raw-events.jsonl';self.outerpath=self.session/'bootstrap-events.jsonl'
        self.rawpath.write_bytes(raw);self.outerpath.write_bytes(outer)
        packet=wire.encode_boot(self.identity)
        (path/f'bootstrap-{self.identity["pid"]}-{self.identity["creation"]}.request').write_bytes(packet)
        self.manifest={'dll_sha256':self.identity['dll_sha256'],'pe':{'bridge_start_rva':0x7000}}
        load=dict(schema='EU4SPYLOAD/1',purpose=b.PURPOSE,identity=self.identity,plan_only=False,disposable_test_premise=True,held_identity_checked_after=True,
            strict_sp_verified=False,world_epoch_verified=False,production_ready=False,automatic_stage=False,send_supported=False,stage_request_written=False,
            bootstrap_sha256=b.sha(packet),bootstrap_bytes=len(packet),installation=dict(pid=self.identity['pid'],dll=str((path/b.DLL).resolve()),bridge_rva='0x7000',
            bridge_thread_exit_status='0x0',dll_unloaded=False,test_save_acknowledged=True,dll_module_base='0x7fff00000000',bridge_remote_address='0x7fff00007000'))
        self.loaderpath=path/f'loader-{self.identity["pid"]}-{self.identity["creation"]}.json'
        self.loaderpath.write_bytes(b.canonical(load));self.kernel=Kernel()
    def capture(self,count):
        rows=[copy.deepcopy(self.first) for _ in range(count)]
        for n,row in enumerate(rows,1):row['ordinal']=row['frame']=n
        return fixture.envelope(rows,False)
    def complete(self,count=2):
        raw,out,_,_=self.capture(count);self.rawpath.write_bytes(raw);self.outerpath.write_bytes(out)
    def pending(self,kind='begin'):
        raw,out,_,_=self.capture(2)
        if kind in ('begin','begin_health'):self.outerpath.write_bytes(b''.join(out.splitlines(keepends=True)[:-1]))
        if kind in ('raw_ahead','begin_health'):self.rawpath.write_bytes(raw)
    def outer_delta(self,index,delta):
        rows=[b.json_value(x) for x in self.outerpath.read_bytes().splitlines()];rows[index].update(delta)
        self.outerpath.write_bytes(fixture.pack(rows))
    @contextmanager
    def fake(self):
        factory=r._reader;original_build=b.verify_build
        def build(path):
            if Path(path).resolve()==self.path.resolve():return self.manifest,self.identity['manifest_sha256']
            return original_build(path)
        def reader(reads):
            value=factory(reads);value.b.verify_build=build;return value
        with patch.object(r,'_reader',side_effect=reader),patch.object(b,'verify_build',side_effect=build),\
             patch.object(client,'process_guard',return_value=(self.kernel,1)),patch.object(client,'now_ms',return_value=10000):yield
    def inspect(self):return r.inspect(self.path,self.identity)

class Coherent(unittest.TestCase):
    def rejected_once(self,c):
        with c.fake(),patch.object(r.time,'sleep') as sleep,self.assertRaises(r.CoherentReadError) as error:c.inspect()
        self.assertEqual(len(error.exception.attempts),1);sleep.assert_not_called()
        self.assertFalse(error.exception.attempts[0]['will_reread']);self.assertFalse(error.exception.retry_allowed)
        json.dumps(error.exception.attempts,allow_nan=False)
        return error.exception
    def test_stable_complete_r2_inspect_one_read(self):
        with tempfile.TemporaryDirectory() as td:
            c=Files(Path(td))
            with c.fake(),patch.object(r.time,'sleep') as sleep:value=c.inspect()
            self.assertEqual(len(value['coherent_read']['attempts']),1);sleep.assert_not_called()
            self.assertTrue(value['source_bound_native_trace_replayed']);self.assertEqual(value['completed_stages'],0)
            self.assertFalse(value['production_ready']);self.assertFalse(value['coherent_read']['prefix_discarded'])
    def test_three_health_race_shapes_resolve_on_second_whole_read(self):
        for kind in ('begin','begin_health','raw_ahead'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as td:
                c=Files(Path(td));c.pending(kind);prior=(c.rawpath.read_bytes(),c.outerpath.read_bytes())
                with c.fake(),patch.object(r.time,'sleep',side_effect=lambda _:c.complete()) as sleep:value=c.inspect()
                self.assertEqual(sleep.call_count,1);attempts=value['coherent_read']['attempts'];self.assertEqual(len(attempts),2)
                self.assertTrue(attempts[0]['will_reread']);self.assertEqual(value['controller_frames'],2)
                for name,old in zip(('raw-events.jsonl','bootstrap-events.jsonl'),prior):self.assertEqual(attempts[0]['logs'][name]['sha256'],b.sha(old))
                self.assertEqual(value['raw_sha256'],b.sha(c.rawpath.read_bytes()))
    def test_exact_three_read_limit_resolve_or_exhaust(self):
        for resolve in (False,True):
            with self.subTest(resolve=resolve),tempfile.TemporaryDirectory() as td:
                c=Files(Path(td));c.pending();calls=0
                def later(_):
                    nonlocal calls
                    calls+=1
                    if resolve and calls==2:c.complete()
                with c.fake(),patch.object(r.time,'sleep',side_effect=later):
                    if resolve:attempts=c.inspect()['coherent_read']['attempts']
                    else:
                        with self.assertRaises(r.CoherentReadError) as exc:c.inspect()
                        attempts=exc.exception.attempts
                self.assertEqual(calls,2);self.assertEqual(len(attempts),3)
                self.assertEqual([x['attempt'] for x in attempts],[1,2,3]);self.assertFalse(attempts[-1]['will_reread'])
    def test_completed_stage_claims_preserved_during_health_only_reread(self):
        source=fixture.synthetic()
        for completed in (1,2,3):
            with self.subTest(completed=completed),tempfile.TemporaryDirectory() as td:
                c=Files(Path(td));end=next(n for n,x in enumerate(source) if x['event']=='health' and x['completed_stages']==completed)
                rows=copy.deepcopy(source[:end+1]);raw,outer,_,claims=fixture.envelope(rows,False)
                extra=copy.deepcopy(rows[-1]);extra['ordinal']+=1;extra['frame']+=1
                fullraw,fullouter,_,_=fixture.envelope(rows+[extra],completed==3)
                outrows=fullouter.splitlines(keepends=True)
                # Remove the optional footer and the new return, preserving
                # all completed request frames and their exact permanent files.
                c.rawpath.write_bytes(raw);c.outerpath.write_bytes(b''.join(outrows[:-(2 if completed==3 else 1)]))
                for sequence,packet in claims.items():
                    for suffix in ('claim','request'):(c.session/f'{sequence}.{suffix}').write_bytes(packet)
                def complete(_):c.rawpath.write_bytes(fullraw);c.outerpath.write_bytes(fullouter)
                with c.fake(),patch.object(r.time,'sleep',side_effect=complete) as sleep:value=c.inspect()
                self.assertEqual(sleep.call_count,1);self.assertEqual(value['completed_stages'],completed)
                self.assertEqual(value['claimed_sequence'],completed);self.assertEqual(value['raw_sha256'],b.sha(fullraw))
                self.assertEqual(value['completed'],completed==3)
    def test_three_old_install_faults_are_never_reread(self):
        for delta in ({'error':5},{'collected':0,'suspended':0},{'failure_thread':1,'rip':0x140000000}):
            with self.subTest(delta=delta),tempfile.TemporaryDirectory() as td:
                c=Files(Path(td));rows=[b.json_value(x) for x in c.outerpath.read_bytes().splitlines()];rows[1]['detail'].update(delta)
                c.outerpath.write_bytes(fixture.pack(rows));self.rejected_once(c)
    def test_unpaired_semantic_fault_cannot_hide_behind_tail_error(self):
        for mutation in ('manual_bool','foreign_player','raw_fault','float_frame'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as td:
                c=Files(Path(td));c.pending('begin_health');rows=[b.json_value(x) for x in c.rawpath.read_bytes().splitlines()]
                if mutation=='manual_bool':rows[-1]['observed']['manual_pause']=True
                elif mutation=='foreign_player':rows[-1]['observed']['player']=0
                elif mutation=='raw_fault':rows[-1]['event']='fault'
                else:rows[-1]['frame']=2.0
                c.rawpath.write_bytes(fixture.pack(rows));error=self.rejected_once(c)
                self.assertEqual(error.attempts[0]['classification'],'terminal_nonretryable')
    def test_bad_json_partial_line_and_complete_contradiction_terminal(self):
        for mutation in ('json','partial','failed_return','duplicate_key'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as td:
                c=Files(Path(td))
                if mutation=='json':c.rawpath.write_bytes(b'not-json\n')
                elif mutation=='partial':c.rawpath.write_bytes(c.rawpath.read_bytes()[:-1])
                elif mutation=='failed_return':c.outer_delta(-1,{'success':False})
                else:c.outerpath.write_bytes(b'{"event":"fault","event":"owner_call_return"}\n')
                self.rejected_once(c)
    def test_request_begin_claim_and_core_tails_never_reread(self):
        for mutation in ('request_begin','claim_file','claim_row','core_row'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as td:
                c=Files(Path(td));c.pending()
                if mutation=='request_begin':c.outer_delta(-1,{'request_sequence':1})
                elif mutation=='claim_file':
                    _,_,_,claims=fixture.envelope(fixture.synthetic())
                    for suffix in ('claim','request'):(c.session/f'1.{suffix}').write_bytes(claims[1])
                else:
                    name='claim' if mutation=='claim_row' else 'core_event';row=next(x for x in fixture.synthetic() if x['event']==name)
                    with c.rawpath.open('ab') as f:f.write(fixture.pack([row]))
                self.rejected_once(c)
    def test_new_request_or_fault_on_later_read_terminal(self):
        for kind in ('claim_file','core_row','outer_fault','request_begin'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as td:
                c=Files(Path(td));c.pending()
                def later(_):
                    if kind=='claim_file':
                        _,_,_,claims=fixture.envelope(fixture.synthetic())
                        for suffix in ('claim','request'):(c.session/f'1.{suffix}').write_bytes(claims[1])
                    elif kind=='core_row':
                        with c.rawpath.open('ab') as f:f.write(b'{"event":"core_event"}\n')
                    elif kind=='outer_fault':
                        with c.outerpath.open('ab') as f:f.write(b'{"event":"fault"}\n')
                    else:
                        c.complete();raw,out,_,_=c.capture(3);last=out.splitlines(keepends=True)[-2]
                        row=b.json_value(last);row['request_sequence']=1
                        with c.outerpath.open('ab') as f:f.write(fixture.pack([row]))
                with c.fake(),patch.object(r.time,'sleep',side_effect=later) as sleep,self.assertRaises(r.CoherentReadError) as exc:c.inspect()
                self.assertEqual(sleep.call_count,1);self.assertEqual(len(exc.exception.attempts),2)
                self.assertFalse(exc.exception.attempts[-1]['will_reread'])
    def test_rewrite_truncation_or_nonlog_change_never_erased(self):
        for name in ('raw_rewrite','raw_truncate','outer_rewrite','loader_change'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as td:
                c=Files(Path(td));c.pending()
                def later(_):
                    if name=='raw_rewrite':c.rawpath.write_bytes(c.rawpath.read_bytes().replace(b'"manual_pause":1',b'"manual_pause":0'))
                    elif name=='raw_truncate':c.rawpath.write_bytes(c.rawpath.read_bytes()[:-1])
                    elif name=='outer_rewrite':c.outerpath.write_bytes(c.outerpath.read_bytes().replace(b'"owner_entry":200',b'"owner_entry":201'))
                    else:c.loaderpath.write_bytes(c.loaderpath.read_bytes()+b' ')
                with c.fake(),patch.object(r.time,'sleep',side_effect=later),self.assertRaises(r.CoherentReadError) as exc:c.inspect()
                self.assertEqual(len(exc.exception.attempts),2)
                self.assertIn('changed between attempts' if name=='loader_change' else 'rewritten/truncated',exc.exception.attempts[-1]['error'])
                if name.startswith('raw'):self.assertEqual(exc.exception.attempts[-1]['logs']['raw-events.jsonl']['sha256'],b.sha(c.rawpath.read_bytes()))
    def test_append_clock_and_typed_fields_still_use_original_r2(self):
        for field,value in (('frame',2.0),('uptime_ms',9999),('claimed_sequence',True)):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as td:
                c=Files(Path(td));c.pending()
                def later(_):
                    c.complete();rows=[b.json_value(x) for x in c.rawpath.read_bytes().splitlines()];rows[-1][field]=value
                    # SHA/range updates make this a semantic counterexample,
                    # not merely a stale outer segment hash.
                    raw,out,_,_=fixture.envelope(rows,False);c.rawpath.write_bytes(raw);c.outerpath.write_bytes(out)
                with c.fake(),patch.object(r.time,'sleep',side_effect=later),self.assertRaises(r.CoherentReadError) as exc:c.inspect()
                self.assertEqual(len(exc.exception.attempts),2);self.assertFalse(exc.exception.attempts[-1]['will_reread'])
    def test_total_byte_and_read_count_bounds(self):
        for field,value in (('MAX_TOTAL_BYTES',20),('MAX_READ_CALLS',2)):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as td:
                c=Files(Path(td));c.pending()
                with patch.object(r,field,value):self.rejected_once(c)
    def test_one_publish_call_internal_read_race_never_republishes(self):
        with tempfile.TemporaryDirectory() as td:
            c=Files(Path(td));write=client.loader.write_new;written=[]
            def create(path,data):
                write(path,data);written.append(Path(path).name)
                if str(path).endswith('publisher-intent.json'):c.pending()
            with c.fake(),patch.object(client.loader,'write_new',side_effect=create),patch.object(r.time,'sleep',side_effect=lambda _:c.complete()):
                result=client.publish(c.path,c.identity,'lifecycle')
            self.assertTrue(result['request_written']);self.assertTrue(result['native_result_unknown'])
            self.assertEqual(written,['1.publisher-intent.json','1.publisher-pending']);self.assertEqual(c.kernel.closed,1)
            packet=(c.session/'1.request').read_bytes();self.assertEqual(wire.p.decode(packet)['sequence'],1)
            with c.fake(),self.assertRaises(ValueError):client.publish(c.path,c.identity,'lifecycle')
            self.assertEqual((c.session/'1.request').read_bytes(),packet)
    def test_exhausted_second_gate_leaves_intent_no_request_no_retry(self):
        with tempfile.TemporaryDirectory() as td:
            c=Files(Path(td));write=client.loader.write_new
            def create(path,data):
                write(path,data)
                if str(path).endswith('publisher-intent.json'):c.pending()
            with c.fake(),patch.object(client.loader,'write_new',side_effect=create),patch.object(r.time,'sleep'),self.assertRaises(r.CoherentReadError) as exc:
                client.publish(c.path,c.identity,'lifecycle')
            self.assertEqual(len(exc.exception.attempts),3);self.assertTrue((c.session/'1.publisher-intent.json').exists())
            self.assertFalse((c.session/'1.request').exists());self.assertFalse((c.session/'1.publisher-pending').exists())
            c.complete()
            with c.fake(),self.assertRaises(FileExistsError):client.publish(c.path,c.identity,'lifecycle')
    def test_stale_complete_health_is_not_refreshed_or_published(self):
        with tempfile.TemporaryDirectory() as td:
            c=Files(Path(td))
            with c.fake(),patch.object(client,'now_ms',return_value=12501),patch.object(r.time,'sleep') as sleep,self.assertRaises(ValueError):
                client.publish(c.path,c.identity,'lifecycle')
            sleep.assert_not_called();self.assertFalse((c.session/'1.publisher-intent.json').exists())
            self.assertFalse((c.session/'1.request').exists());self.assertEqual(c.kernel.closed,1)
    def test_source_origin_and_original_dll_manifest_preserved(self):
        value=check();self.assertEqual(value['original_manifest_sha256'],'d1f65cae88cfb7ed2535c590206b9844882f0870f02773da23c747a6346aa5e5')
        self.assertEqual(value['original_dll_sha256'],'6aff9a9fc4d46692c9be0ac39b0c741bf8eeb840abaf8731d0144510a938f00b')
        self.assertEqual(Path(client.__file__),base.OLD/'client.py');self.assertIs(client.real_capture,r)
        self.assertIs(base.client.real_capture,base.reader)
        reads=r._Reads(Path('unused'));reader=r._reader(reads)
        self.assertEqual(Path(reader.__file__),base.R2/'real_capture.py');self.assertEqual(reader.b.HERE,base.OLD)

if __name__=='__main__':unittest.main(verbosity=2)
