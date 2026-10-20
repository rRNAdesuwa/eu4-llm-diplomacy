"""Complete synthetic replay only; no DLL build/load or actual session reads."""
import copy,json,sys,types,unittest
from _frozen import HERE,OLD,ROOT,PINS,b,read,sha
import real_capture as current

# Test fixtures remain the sealed author's original files. They are only
# synthetic builders; no CLI main/loader/process function is invoked.
sys.path.append(str(OLD))
import test_capture as fixture


def old_reader():
    path=OLD/'real_capture.py';raw=read(path,32768);pin=PINS[path.relative_to(ROOT).as_posix()]
    assert sha(raw)==pin['sha256'] and len(raw)==pin['bytes']
    module=types.ModuleType('_original_capture_reproducer');module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__);return module


def changed(delta):
    raw,outer,identity,claims=fixture.envelope(fixture.synthetic())
    rows=[b.json_value(x)for x in outer.splitlines()];rows[1]['detail'].update(delta)
    return raw,fixture.pack(rows),identity,claims


class InstallReceiptR2(unittest.TestCase):
    def test_original_three_full_pipeline_counterexamples_now_rejected(self):
        old=old_reader()
        rows=json.loads(read(ROOT/'work/review-results/v18-spy-bootstrap-action-catalog-20261008a/counterexamples.json',16384))
        self.assertEqual(len(rows),3)
        for row in rows:
            args=changed(row['delta'])
            with self.subTest(name=row['name']):
                self.assertTrue(old.validate_stream(*args,True)['completed'])
                with self.assertRaises(ValueError):current.validate_stream(*args,True)
    def test_terminated_threads_allow_less_suspended_including_zero(self):
        for collected in (1,2,512):
            for suspended in (0,1,collected):
                with self.subTest(collected=collected,suspended=suspended):
                    result=current.validate_stream(*changed({'collected':collected,'suspended':suspended}),True)
                    self.assertTrue(result['completed']);self.assertFalse(result['production_ready'])
    def test_each_failure_field_independently_rejected(self):
        for name in ('failure_stage','error','failure_thread','rip','resume_failures','resume_error','resume_thread'):
            for value in (1,2**64-1):
                with self.subTest(name=name,value=value),self.assertRaises(ValueError):
                    current.validate_stream(*changed({name:value}),True)
    def test_strict_typed_install_scalars(self):
        fields=('attempt','result','failure_stage','error','failure_thread','collected','suspended','resume_failures','resume_error','resume_thread','rip')
        for name in fields:
            for value in (False,True,0.0,'0',None,-1,2**64):
                with self.subTest(name=name,value=value),self.assertRaises(ValueError):
                    current.validate_stream(*changed({name:value}),True)
    def test_count_bounds_and_success_flags(self):
        for delta in ({'collected':0,'suspended':0},{'collected':513},{'collected':1,'suspended':2},
                      {'prefix_unchanged':True},{'retrying':True},{'send_supported':True}):
            with self.subTest(delta=delta),self.assertRaises(ValueError):current.validate_stream(*changed(delta),True)
    def test_valid_prepatch_retry_then_success_still_supported(self):
        raw,outer,i,claims=fixture.envelope(fixture.synthetic());rows=[b.json_value(x)for x in outer.splitlines()]
        retry=copy.deepcopy(rows[1]);retry['detail'].update(result=21,prefix_unchanged=True,retrying=True,failure_stage=41,error=0,failure_thread=1234,rip=0)
        rows.insert(1,retry);rows[2]['detail']['attempt']=2
        for n,row in enumerate(rows,1):row['ordinal']=n
        result=current.validate_stream(raw,fixture.pack(rows),i,claims,True);self.assertTrue(result['completed'])
        for field,value in (('resume_failures',1),('result',29),('prefix_unchanged',False),('retrying',False)):
            bad=copy.deepcopy(rows);bad[1]['detail'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):current.validate_stream(raw,fixture.pack(bad),i,claims,True)
    def test_original_valid_stream_outputs_unchanged(self):
        args=fixture.envelope(fixture.synthetic());self.assertEqual(current.validate_stream(*args,True),old_reader().validate_stream(*args,True))
        self.assertEqual(current.validate_stream(*args,True)['legality_results']['family_preview'],dict.fromkeys(fixture.wire.p.FAMILIES,False))
    def test_original_metadata_and_helper_origin_preserved(self):
        self.assertEqual(b.HERE,OLD)
        manifest,digest=b.verify_build(OLD/'build-final')
        self.assertEqual(digest,'d1f65cae88cfb7ed2535c590206b9844882f0870f02773da23c747a6346aa5e5')
        self.assertEqual(manifest['dll_sha256'],'6aff9a9fc4d46692c9be0ac39b0c741bf8eeb840abaf8731d0144510a938f00b')
        self.assertFalse((HERE/'build-final').exists())


if __name__=='__main__':unittest.main()
