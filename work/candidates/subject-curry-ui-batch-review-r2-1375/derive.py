"""CreateNew narrow R2 derivative; never read actual observations or invoke reviewer."""
from pathlib import Path
import hashlib,json,difflib
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OLD=ROOT/'work/candidates/subject-curry-ui-batch-review-1375'
REJECTION=ROOT/'work/review-results/subject-curry-ui-batch-native-inventory-20261008a/review.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def emit(name,raw):
    with (HERE/name).open('xb')as f:f.write(raw)
def main():
    assert sha(OLD/'review.json')=='43a7bd907663cc66581ffc3f4ae1f54fe8ba4c3f6387b5b1205bb8b945111c9f'
    assert sha(REJECTION)=='b8c0bca86ec5d222d19bc969c24f9f8a1b9c811492724f599615d79ba307d6cf'
    pins=json.loads((OLD/'input-pins.json').read_bytes())
    oldidx=json.loads((OLD/'source-index.json').read_bytes())
    for name,d in oldidx['sources'].items():assert sha(ROOT/name)==d['sha256'];pins[name]=d['sha256']
    for p in (OLD/'review.json',OLD/'source-index.json',OLD/'validation-final/validation.json',REJECTION):pins[p.relative_to(ROOT).as_posix()]=sha(p)
    raw=(json.dumps(pins,sort_keys=True,indent=2)+'\n').encode();emit('input-pins.json',raw)
    old=(OLD/'reviewer.py').read_text(encoding='utf-8');new=old.replace("PINS_SHA='47453c6dc3cb9cd7b975afa0cf610ad82b84f596a1e417419dce9010e43bf3eb'",f"PINS_SHA='{hashlib.sha256(raw).hexdigest()}'")
    needle="    same(focus['snapshot'],toggle['snapshot']['graph'],'same complete subject graph within census')"
    assert new.count(needle)==1
    new=new.replace(needle,"    # Same FRA+1510 field across samplers; target-specific record/root remain distinct.\n    curry_records=integer(curry['passes'][0]['index']['records'],65536,2**47-1)\n    subject_records=integer(focus['snapshot']['left']['records'],65536,2**47-1)\n    require(curry_records==subject_records,'common FRA relationship records')\n"+needle)
    new=new.replace("case['purpose']=='fixed_subject_curry_ui_batch_38232'","case['purpose']=='fixed_subject_curry_ui_batch_r2_38232'")
    emit('reviewer.py',new.encode())
    test=(OLD/'test_reviewer.py').read_text(encoding='utf-8').replace("purpose='fixed_subject_curry_ui_batch_38232'","purpose='fixed_subject_curry_ui_batch_r2_38232'")
    # Old cases are produced by a helper literal, retain exact replacement either syntax.
    test=test.replace("'purpose':'fixed_subject_curry_ui_batch_38232'","'purpose':'fixed_subject_curry_ui_batch_r2_38232'")
    tests='''
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
'''
    test=test.replace("if __name__=='__main__':",tests+"\nif __name__=='__main__':")
    emit('test_reviewer.py',test.encode())
    prep=(OLD/'prepare.py').read_text(encoding='utf-8').replace("'input-pins.json')","'input-pins.json','derive.py','repair.diff')").replace("fixed_subject_curry_manual_ui_batch_candidate","fixed_subject_curry_manual_ui_batch_candidate_r2")
    emit('prepare.py',prep.encode());emit('validate.py',(OLD/'validate.py').read_bytes())
    readme=(OLD/'README.md').read_text(encoding='utf-8').replace('subject-curry-ui-batch-review-1375','subject-curry-ui-batch-review-r2-1375')
    readme+='\n\nR2 最小修复：对每份 census 的共同 FRA+0x1510 关系表，严格整数核对 curry.passes[0].index.records 与 military_focus.snapshot.left.records。两遍 curry 已经逐字段绑定；focus 与 toggle.graph 仍整图精确一致。NAV 和 POR 的 record/root 是不同目标字段，保留不同值。group_atomic=false 并不豁免共同字段一致性。原独审三项 before/after/both 反例必须拒绝。旧候选、validation、拒审报告均作为输入固定；没有 actual reviewer 执行或效果授权。\n'
    emit('README.md',readme.encode())
    emit('repair.diff',''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='R1/reviewer.py',tofile='R2/reviewer.py')).encode())
    print(json.dumps({'files_created':8,'old_unchanged':sha(OLD/'review.json')=='43a7bd907663cc66581ffc3f4ae1f54fe8ba4c3f6387b5b1205bb8b945111c9f','inputs':len(pins),'actual_review_executed':False}))
if __name__=='__main__':main()
