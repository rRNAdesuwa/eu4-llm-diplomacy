"""Check this offline-only candidate or print an unfilled future case contract."""
import argparse
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def descriptor(path):
    with path.open('rb') as stream:raw=stream.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:raise ValueError('Source bound')
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def check():
    pins=json.loads((HERE/'source-pins.json').read_text())
    index=json.loads((HERE/'candidate-index.json').read_text())
    if not 1<=len(pins)<=128 or len(index)!=5:raise ValueError('Unexpected input count')
    for mapping in (pins,index):
        for name,expected in mapping.items():
            path=ROOT/name
            if path.resolve()!=path or not path.is_relative_to(ROOT) or descriptor(path)!=expected:
                raise ValueError('Changed/noncanonical pinned input: '+name)
    return {'source_pins':len(pins),'candidate_sources':len(index),'actual_case_entrypoint':False,
            'native_execution_verified':False,'publication':False}


def template():
    return {'purpose':'v17_batch_stopped_review_future_case_template','implemented_actual_case_reader':False,
            'root_must_supply':{'pid':None,'creation':None,'world_cookie':None,'window_thread':None,'run_id':None,
                'preflight_summary':None,'stopped_session_inputs':None,'held_exit':None,'batch_scope':None,
                'journal':None,'summary':None,'status_and_capture_inventory':None,'initial_census':None,'final_census':None},
            'native_source_replay_required':True,'census_full_pass_replay_required':True,
            'effect_verification':False,'production':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check',action='store_true');group.add_argument('--template',action='store_true')
    args=parser.parse_args();print(json.dumps(check() if args.check else template(),indent=2))
