import json
from prepare import HERE,read,desc,current,inputs
def write(name,value):
 with (HERE/name).open('xb') as f:f.write((json.dumps(value,indent=2,sort_keys=True)+'\n').encode('ascii'))
if __name__=='__main__':
 v=json.loads(read(HERE/'validation-final/validation.json'));index=json.loads(read(HERE/'source-index.json'))
 assert v['passed'] and v['before']==v['after']==index==current()
 assert v['inputs_before']==v['inputs_after']==inputs()
 old=read(HERE/'validation-final/build/test.stdout').decode('ascii');counter=read(HERE/'validation-final/build/counter.stdout').decode('ascii');new=read(HERE/'validation-final/build/r3.stdout').decode('ascii')
 assert 'groups=24 native_calls=0' in old and 'r2_counterchecks=38' in counter and 'r3_groups=37' in new and 'twelve_component_modes=true native_calls=0 fake_only=true' in new
 limits={k:False for k in ['runtime_verified','native_ready','production_ready','submitted','DLL_built','game_accessed','native_platform_executed','OS_memory_accessed',
  'formal_files_modified','old_sealed_files_modified','strict_SP_proven','world_epoch_proven','lifetime_lock_proven','ABA_excluded','effect_causality_proven','backend_registered']}
 limits.update(all_shells_collected=True,remaining_sessions=[],new_decode_bytes=0)
 report={'schema':1,'status':'sealed_author_r3_spy_fix_pending_independent_review','purpose':'faithful_void_spy_setter_and_typed_private_binder',
  'passed':True,'profiles':6,'component_fake_modes':12,'author_regression_groups':24,'retained_R2_checks':38,'new_groups':37,
  'header_ABI_unchanged':True,'registry_FullCallerEvidence_unchanged':True,'adapter_copies_byte_identical':True,
  'native_setter_effect':'586330(false) sets signed action+30 envoy; match exact private typed graph ID immediately after normal return',
  'legacy_named_bind_envoy_owned':'read-only same-ID confirmation; never clear or overwrite native result',
  'typed_additions':['country manager-vector end/capacity','manager vt/marker/token/kind/unaligned full owner/vector-capacity',
    'entry vt/marker/kind before status/mission','unique entry pointers','mission marker182 before task','typed transcript across both passes and immediate rebind'],
  'not_promoted':['five normal full88 caller evidence; old descriptive stack offset -81 is known incorrect (-89)',
    'adapter overall review or its unrelated marriage heap-alias finding','runtime authority, loaded registry, actual effect, strictSP, epoch or ABA'],
  'input_files':len(inputs()),'source_files':len(index),'build':v['build'],'test_outputs':{'regression':old,'R2':counter,'R3':new},
  'source_index':desc(HERE/'source-index.json'),'inputs':desc(HERE/'input-pins.json'),'delta':desc(HERE/'r3-delta.diff'),
  'validation':desc(HERE/'validation-final/validation.json'),'limits':limits,'independent_review_required':True}
 write('report.json',report)
 write('review.json',{'schema':1,'passed':True,'status':report['status'],'report':desc(HERE/'report.json'),
  'index':desc(HERE/'source-index.json'),'validation':desc(HERE/'validation-final/validation.json'),'limits':limits})
 print(json.dumps({k:desc(HERE/p) for k,p in [('review','review.json'),('index','source-index.json'),('validation','validation-final/validation.json'),('report','report.json')]}))
