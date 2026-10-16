"""Independent file/synthetic review. Never opens a process or publishes."""
import argparse
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT/'work/reports/relation-request-observer-review-20261015-r1'
CAND = ROOT/'work/candidates/relation-request-observer-20261015'
PRE = OUT/'reviewed-preimage'
HIST = ROOT/'work/reports/war-peace-api-20261015-r10-checkpoint/historical-relation-installation-preflight.json'

def pin(path):
    raw = path.read_bytes()
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def check():
    manifest = json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    for name, value in manifest['source_pins'].items():
        assert pin(ROOT/name) == value, name
    print(json.dumps(dict(status='pass', pins=len(manifest['source_pins']), process_accessed=False)))

def main():
    required = {
        CAND/'relation_request_observer.py': (28553,'4bdd6e6454a17d9277885f905559036c3929e39173b9543f172cbaeea7debceb'),
        CAND/'test_relation_request_observer.py': (27042,'200886630b51c05d0b20009acac1fbafd5deb51a5153bb7fd6d80e2e4e69eb86'),
        PRE/'relation_request_observer.py': (28372,'b1b7d0be7fafc61fa7c1764e2851b40fd9b2b25614c7ca0e6380fb85c80e93cd'),
        PRE/'test_relation_request_observer.py': (25606,'07c2e2c961200f339012cc47c9c8c42e3564e703aa7f0c471cedc625293d6cf2'),
        HIST: (2738,'2fe1c1a99984746967e2191e33ea0f32c2c4470904d6169e8f0c65d007f23227'),
    }
    for path, (size, sha) in required.items():
        assert pin(path) == dict(bytes=size,sha256=sha), path
    oldtests = load(PRE/'test_relation_request_observer.py','review_old_relation_tests')
    newtests = load(CAND/'test_relation_request_observer.py','review_new_relation_tests')
    rows = []
    for version, tests in [('preimage_b1b7',oldtests),('patched_4bdd',newtests)]:
        for label, field, value in [
            ('valid_loader_differs_owner',None,None),
            ('loader_dword_overflow','thread',2**32+99),
            ('owner_dword_overflow','owner_thread',2**32+12),
            ('loader_zero','thread',0),
            ('loader_bool','thread',True),
        ]:
            case = tests.CandidateTests('test_missing_baseline_does_not_open_process')
            case.setUp()
            try:
                if field == 'owner_thread':
                    for row in case.rows: row[field] = value
                elif field:
                    case.rows[0][field] = value
                case.write_audit()
                error = None
                try:
                    proof, _ = tests.c.installed_session(case.backend, case.identity)
                    accepted = proof['installation_record_verified']
                    assert proof['live_hook_proven'] is False
                except (ValueError,RuntimeError,KeyError,TypeError) as exc:
                    accepted = False
                    error = type(exc).__name__+': '+str(exc)
                wanted = label == 'valid_loader_differs_owner' or (version == 'preimage_b1b7' and 'overflow' in label)
                assert accepted is wanted, (version,label,accepted,error)
                assert not case.captures and not case.closes
                rows.append(dict(version=version,case=label,installation_accepted=accepted,
                                 captures=0,error=error))
            finally:
                case.doCleanups()
    # Selected boundary probes through real frozen file-audit + byte-reader graph.
    combinations = []
    for scenario in ('unchanged_absence','missing_commit','reverse_guarantee'):
        case = newtests.CandidateTests('test_missing_baseline_does_not_open_process')
        case.setUp()
        try:
            case.ready('guarantee' if scenario == 'reverse_guarantee' else 'offer_alliance')
            if scenario == 'unchanged_absence': case.present = False
            if scenario == 'reverse_guarantee': case.reverse = True
            if scenario == 'missing_commit':
                (case.observer.directory(case.command['request_id'])/'relation-request-baseline-commit.json').unlink()
            count = len(case.captures)
            result = case.observe()
            wanted = 'unknown' if scenario == 'missing_commit' else 'not_observed'
            assert result['effect']['status'] == wanted, result
            assert result['transport_state'] == 'dispatched', result
            assert result['automatic_command_retry'] is False
            assert result['AI_acceptance_verified'] is False
            assert len(case.closes) == len(case.captures)
            if scenario == 'missing_commit': assert len(case.captures) == count
            combinations.append(dict(case=scenario,effect_status=result['effect']['status'],
                transport_state=result['transport_state'],new_captures=len(case.captures)-count,
                request_state=result['request_state'],automatic_command_retry=False,
                AI_acceptance_verified=False,held_ports_closed=len(case.closes)))
        finally:
            case.doCleanups()
    historical = json.loads(HIST.read_text(encoding='utf-8'))
    historical_results=[]
    historical_files={}
    for version, tests in [('preimage_b1b7',oldtests),('patched_4bdd',newtests)]:
        from bridge import tag_command_backend as backend_module
        from bridge import diplomacy_effect_observer as frozen_module
        with patch.object(backend_module,'WindowsRuntime',side_effect=AssertionError('No process access')), \
             patch.object(frozen_module,'WindowsRuntime',side_effect=AssertionError('No process access')), \
             patch.object(backend_module.TagCommandBackend,'load',side_effect=AssertionError('No installation')), \
             patch.object(backend_module.TagCommandBackend,'publish',side_effect=AssertionError('No publication')):
            backend = backend_module.TagCommandBackend()
            proof,audit=tests.c.installed_session(backend,historical['identity'])
            assert tests.c.digest(audit.raw)==historical['audit_sha256']
            assert proof['identity']==historical['identity']
            normalize=lambda values:{str(Path(k).resolve()):v for k,v in values.items()}
            assert normalize(proof['files'])==normalize(historical['installation']['files'])
            assert Path(proof['session_directory']).resolve()==Path(historical['installation']['session_directory']).resolve()
            historical_files.update({str(Path(k).resolve().relative_to(ROOT).as_posix()):v for k,v in proof['files'].items()})
            historical_files[(audit.directory/'events.jsonl').relative_to(ROOT).as_posix()]=pin(audit.directory/'events.jsonl')
            historical_results.append(dict(source_version=version,closed_pid=historical['identity']['pid'],
                audit_sha256=tests.c.digest(audit.raw),installation_record_verified=True,
                live_hook_proven=False,process_accessed=False))
    diff=''.join(difflib.unified_diff((PRE/'relation_request_observer.py').read_text().splitlines(True),
        (CAND/'relation_request_observer.py').read_text().splitlines(True),fromfile='b1b7-preimage',tofile='4bdd-patched'))
    assert diff.count('+    require(type(owner) is int')==1
    report=dict(schema='EU4-RELATION-REQUEST-INDEPENDENT-SOURCE-REVIEW/1',
        status='ready_for_candidate_seal_at_reviewed_pins',finding_count=0,
        scope='Offline source/API review, retained installation files and synthetic byte graphs only; no CLI review',
        fixed_original_finding=dict(priority=3,kind='DWORD_thread_id_upper_bound',
            original_sha256=required[PRE/'relation_request_observer.py'][1],
            fixed_sha256=required[CAND/'relation_request_observer.py'][1],
            original_overflow_cases_accepted=2,patched_overflow_cases_accepted=0,
            legacy_loader_thread_may_differ_from_owner=True),
        narrow_source_diff=diff,thread_counterexamples=rows,selected_combination_probes=combinations,
        historical_file_replay=historical_results,
        author_full_test_receipt=dict(path=(CAND/'test-run.json').relative_to(ROOT).as_posix(),
            tests=46,source_version='b1b7 preimage',independently_repeated=False),
        author_delta_receipt=dict(path=(CAND/'installation-delta-run.json').relative_to(ROOT).as_posix(),
            tests=6,source_version='4bdd patched',independently_repeated=False),
        reviewed_boundaries=[
            'Frozen dependency graph and default44-pin native manifest verified before capture and after receipt use',
            'Original installation/bootstrap/complete audit identity; seq0 loader thread may differ; seq>0 owner-bound DWORD threads',
            'Fresh absent exact typed relation baseline plus immutable postwrite commit before original intent; no retrospective nonce relabel',
            'Fresh TAG/full-handle lookup, shared read budget and held read-only port; typed raw index/object replay and directional guarantee',
            'Original audit strict prefix, full binding and normal native receipt retained independently of effect unknown',
            'No request publisher, loader, hook installer or process/native action in this review',
        ],
        limitations=[
            'No current hook authentication or new API effect; closed42600 file replay is historical installation only',
            'No exclusive publisher lock acquisition, atomic snapshot, world epoch proof, external request-ID causality, AI acceptance or persistence',
            'Races after final checks remain possible; claimed scope is selected matched state change and immutable evidence consistency',
            'Parent historical receipt source pin is b1b7 and is interpreted through preserved preimage; it was not rewritten as patched evidence',
            'An earlier auditor-only exploratory script used nonexistent Memory.q and aborted after successful historical replay; no failed probe is counted here',
            'No review of future CLI or manifest seal; author46 tests and6 delta tests reused rather than rerun',
        ],process_accessed=False,native_calls=0,requests_published=0,new_API_effects=0,native_ready=False)
    pins=newtests.c.source_pins()
    pins.update(historical_files)
    for path in [*required,CAND/'README.md',CAND/'test-run.json',CAND/'test-run.log',
        CAND/'installation-delta-run.json',CAND/'installation-delta-run.log',Path(__file__)]:
        pins[path.relative_to(ROOT).as_posix()]=pin(path)
    output=OUT/'independent-source-ready.json'
    with output.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
    pins[output.relative_to(ROOT).as_posix()]=pin(output)
    with (OUT/'manifest.json').open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(dict(schema='EU4-INDEPENDENT-REVIEW-MANIFEST/1',source_pins=pins),stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],thread_cases=len(rows),combination_cases=len(combinations),
        historical_replays=2,report=pin(output),pins=len(pins),process_accessed=False)))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true')
    if parser.parse_args().check: check()
    else: main()
