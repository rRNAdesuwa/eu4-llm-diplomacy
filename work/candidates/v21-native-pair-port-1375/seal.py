"""Author seal after the one fixed final bounded build/mock validation."""
import json
from prepare import HERE,read,desc,current,inputs
def write(name,value):
 with (HERE/name).open('xb') as f:f.write((json.dumps(value,indent=2,sort_keys=True)+'\n').encode('ascii'))
if __name__=='__main__':
 v=json.loads(read(HERE/'validation-final/validation.json'));index=json.loads(read(HERE/'source-index.json'))
 assert v['passed'] and v['before']==v['after']==index==current()
 assert v['inputs_before']==v['inputs_after']==inputs()
 assert 'fake_only=true native_platform_linked=false native_calls=0 submitted=0' in v['tests']
 counter=read(HERE/'validation-final/build/r2.stdout').decode('ascii')
 assert 'r2_real_setter_integration_block_reproduced=true' in counter
 limits={k:False for k in ['runtime_verified','native_ready','production_ready','submitted','game_accessed','DLL_built','native_platform_executed',
  'real_Host_implemented','TAG_resolver_integrated','cancellation_readers_integrated','strict_SP_proven','world_epoch_proven','lifetime_lock_proven','ABA_excluded','public_backend_registered','formal_files_modified']}
 limits.update(new_decode_bytes=0,all_shells_collected=True,remaining_sessions=[])
 report={'schema':1,'purpose':'v21_private_six_profile_native_pair_port_draft',
  'status':'sealed_author_obj_and_fake_only_pending_independent_review','passed_with_explicit_integration_blocker':True,
  'input_files':len(inputs()),'source_files':len(index),'profiles':6,'direct_fake_modes':12,'R2_component_integrated_modes':11,
  'blocked_R2_action':'stop_building_spy_network','blocker':'R2 expects envoy=-1 after real void spy setter, but setter writes resolved nonnegative envoy at586424; faithful view is refused. Needs new caller revision; sealed R2 unchanged.',
  'adapter_binding':'nonnegative native setter output +30 must equal private binder exact ID; no overwrite',
  'compiled_objects':['pair_component.obj','native_pair_engine.obj','native_platform.obj'],
  'linked_mock':'component + adapter + fake platform; real platform object not linked',
  'test_output':v['tests'],'R2_counterexample_output':counter,
  'counts_note':'check counts include repeated bounded read and fake memory assertions, not independent scenarios',
  'build':v['build'],'source_index':desc(HERE/'source-index.json'),'inputs':desc(HERE/'input-pins.json'),
  'pin_provenance':desc(HERE/'pin-provenance.json'),'validation':desc(HERE/'validation-final/validation.json'),
  'authority_interface':{'fresh':'bool(void* user,uint64 module,uint32 owner), identity/pause only',
   'final_operation':'bool(void* user,Call), final identity reads then current monotonic clock/original TTL; only normal known dtor may ignore expiry',
   'final_owned_write':'bool(void* user), same final work barrier after region validation and before exact scalar memcpy'},
  'ownership_basis':'private issued registry + trusted pinned factory/wrapper control flow; not independent allocator or Event ownership authentication',
  'limitations':limits,'independent_review_required':True}
 write('report.json',report)
 write('review.json',{'schema':1,'status':report['status'],'passed':True,'R2_stopspy_integration_supported':False,
  'report':desc(HERE/'report.json'),'validation':desc(HERE/'validation-final/validation.json'),'source_index':desc(HERE/'source-index.json'),
  'inputs':desc(HERE/'input-pins.json'),'limitations':limits})
 print(json.dumps({'review':desc(HERE/'review.json'),'report':desc(HERE/'report.json'),'index':desc(HERE/'source-index.json'),'validation':desc(HERE/'validation-final/validation.json')}))
