"""One-time file-only seal of the already built private bootstrap candidate."""
from pathlib import Path
import json
import build_manifest as b
import prepare

HERE=Path(__file__).resolve().parent

def descriptor(path):
    raw=b.bounded(path,2*1024*1024)
    return {'bytes':len(raw),'sha256':b.sha(raw)}

def write_new(path,value):
    raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode('ascii')
    with path.open('xb') as stream:stream.write(raw)

def main():
    b.require(not (HERE/'candidate-index.json').exists() and not (HERE/'review.json').exists(),'Seal already exists')
    manifest,manifest_sha=b.verify_build(HERE/'build-attempt2')
    validation=b.json_value(b.bounded(HERE/'build-attempt2-validation.json',16384))
    b.require(validation['build_exit_code']==validation['wire_exit_code']==0 and validation['sources_unchanged'] is True,'Validation failed')
    b.require(validation['dll_loaded'] is False and validation['bridge_start_called'] is False and validation['game_accessed'] is False,'Offline build boundary')
    names=(*b.LOCAL_SOURCES,'README.md','prepare.py','freeze_lineage.py','validate_build.py','seal_candidate.py')
    index={'sources':{name:descriptor(HERE/name) for name in sorted(names)},
           'predecessors':b.json_value(b.bounded(HERE/'predecessor-pins-r2.json',131072)),
           'build':{'directory':'build-attempt2','manifest_sha256':manifest_sha,'dll_sha256':manifest['dll_sha256']}}
    write_new(HERE/'candidate-index.json',index)
    checked=prepare.check()
    artifacts=('build-attempt2-validation.json','build-attempt2-source-check.json','build-attempt2/test.stdout',
               'build-attempt2/claims.stdout','build-attempt2/wire.stderr','development-build-attempt1/failure.json',
               'development-pre-r2-host/source-index.json')
    report={'schema':1,'status':'sealed_candidate_requires_independent_review','scope':'private restricted bootstrap offline build only',
            'candidate_index':descriptor(HERE/'candidate-index.json'),'manifest':descriptor(HERE/'build-attempt2/build.json'),
            'dll':descriptor(HERE/'build-attempt2'/b.DLL),'pe':manifest['pe'],'prepare':checked,
            'validation_artifacts':{name:descriptor(HERE/name) for name in artifacts},
            'tests':{'codec_scheduler_assertions':465,'raw_claim_assertions':35,'python_wire_methods':6,'build_exit_code':0,'wire_exit_code':0},
            'manifest_sources_unchanged':165,'host_r2_independent_review_sha256':validation['host_independent_review_sha256'],
            'all_spawned_sessions_collected':True,'dll_loaded':False,'bridge_start_called':False,'game_accessed':False,
            'runtime_verified':False,'effect_verified':False,'production_ready':False,'strict_single_player_verified':False,
            'world_epoch_verified':False,'publisher_implemented':False,'public_backend_registered':False,
            'limitations':['Offline tests do not prove native runtime or effects.','Original hook is not a full processor XSTATE proof.',
                           'Root equality/server classifier are not strict single-player or world epoch proofs.',
                           'Loaded objects remain until process exit; no retry, hot replacement, or unload.',
                           'Build/loader provenance wrapper and independent bootstrap review remain required.',
                           'First build driver failed before output directory creation; child stdout/stderr were not retained.']}
    write_new(HERE/'review.json',report)
    print(json.dumps({'candidate_index':descriptor(HERE/'candidate-index.json'),'review':descriptor(HERE/'review.json'),'prepare':checked},sort_keys=True))

if __name__=='__main__':main()
