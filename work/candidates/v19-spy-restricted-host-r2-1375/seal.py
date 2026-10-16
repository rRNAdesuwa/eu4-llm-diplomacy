from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OLD=ROOT/'work/candidates/v19-spy-restricted-host-1375'
def raw(p):
    with p.open('rb') as f:b=f.read(8388609)
    assert len(b)<=8388608
    return b
def desc(p):
    b=raw(p);return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def load(p):return json.loads(raw(p))
old=load(OLD/'source-index.json');new=load(HERE/'source-index.json')
validation=load(HERE/'validation-final/validation.json')
assert validation['passed'] and validation['inputs_unchanged'] and validation['mock_result']['checks']==966
assert all(desc(ROOT/name)==pin for name,pin in validation['before'].items())
unchanged=[];changed=[]
for name,pin in old['sources'].items():
    assert desc(OLD/name)==pin
    (unchanged if desc(HERE/name)==pin else changed).append(name)
assert set(changed)=={'README.md','host.cpp','input-pins.json','prepare.py','test_host.cmd'}
for folder in ('core/','preflight/','v18-preimage/'):
    assert all(name in unchanged for name in old['sources'] if name.startswith(folder))
assert 'host.h' in unchanged and 'test_host.cpp' in unchanged and 'interface.json' in unchanged
review={'schema_version':1,'purpose':'isolated_v19_restricted_host_r2_terminal_boundary_repairs',
 'state':'sealed_pending_independent_review','predecessor':{'path':OLD.relative_to(ROOT).as_posix(),
   'review':desc(OLD/'review.json'),'source_index':desc(OLD/'source-index.json')},
 'finding_review':{'path':'work/review-results/v19-host-native-inventory-20261008a/review.json',
   **desc(ROOT/'work/review-results/v19-host-native-inventory-20261008a/review.json')},
 'repairs':[
   {'id':'F1','contract':'All begin_frame false or terminal returns lock the Host, including sequence 4; restoring the callback cannot permit reclaim or native work.',
    'implementation':'One private begin_frame_cb wrapper is used for preflight, sequence 4 and later automatic callbacks.'},
   {'id':'F2','contract':'All clock observations share one monotonic high water across preflight and sequence 4; the true lower value is returned and terminal failure prevents subsequent work.',
    'implementation':'clock_cb tracks the real value; barrier uses the callback and checks health before proceeding. No time clamping.'}],
 'source_changes':changed,'unchanged_predecessor_sources':unchanged,
 'inputs':{'count':61,'pin_index':desc(HERE/'input-pins.json'),'local_source_count':39,'source_index':desc(HERE/'source-index.json')},
 'key_files':{name:desc(HERE/name) for name in ['host.cpp','host.h','host-r2.diff','test_host_r2.cpp','test_host.cpp','test_host.cmd','interface.json','derive.py','README.md','seal.py']},
 'validation':{'record':desc(HERE/'validation-final/validation.json'),'exit_code':0,'mock_checks':966,'mock_failures':0,
   'new_checks_added_to_exact_old_suite':111,'owner_frame_failure_positions':17,'inputs_before_after':101,
   'all_inputs_unchanged':True,'all_shell_sessions_collected':True,
   'object_builds':6,'mock_executables':1,'compiler_flags':['/std:c++17','/O2','/W4','/WX','/MT','/GS'],
   'native_environment_initializer_called':False,'capture':validation['capture']},
 'limits':{'actual_process_access':False,'actual_native_calls':False,'dll_built':False,'hook_installed':False,
   'requests_published':False,'runtime_verified':False,'strict_sp_verified':False,'epoch_verified':False,
   'effect_verified':False,'production_ready':False,'frozen_sources_modified':False,
   'ownership_protocol_changed':False,'public_interface_changed':False},
 'validation_artifacts':validation['artifacts']}
with (HERE/'review.json').open('x',encoding='utf-8') as f:json.dump(review,f,sort_keys=True,indent=2);f.write('\n')
print(json.dumps({n:desc(HERE/n) for n in ['review.json','source-index.json','host.cpp','host-r2.diff','test_host_r2.cpp','validation-final/validation.json']}))
