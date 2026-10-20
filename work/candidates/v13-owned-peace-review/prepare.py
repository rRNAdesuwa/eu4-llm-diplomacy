"""Generate an isolated v13 source review. Never materialize, build, or open a process."""
from __future__ import annotations
import argparse
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INPUT_SHA = 'ccbf006eae1f4a54bb6ba6dcbd8dfb79845c8d2dc65ca4dd79c3a7a5a75938f0'
OWNED = ROOT / 'work/candidates/owned-peace-lifecycle-review'
NEW = 'work/native/v13/'
OLD = 'work/native/v12/'

def digest(raw): return hashlib.sha256(raw).hexdigest()
def encode(value): return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()
def replace(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError(f'Expected {count} copies, got {text.count(old)}: {old[:100]!r}')
    return text.replace(old, new)

def audit_inputs():
    raw = (HERE / 'input-pins.json').read_bytes()
    if digest(raw) != INPUT_SHA: raise ValueError('Input pin manifest changed')
    pins = json.loads(raw)['inputs']
    for item in pins:
        path = ROOT / item['path']
        if path.stat().st_size != item['bytes'] or digest(path.read_bytes()) != item['sha256']:
            raise ValueError('Frozen/reviewed input changed: ' + item['path'])
    return pins

def host(text):
    text = replace(text, '// Three explicit preflight markers precede a canonical twenty-four-ID/speed mailbox.',
                   '// Four explicit preflight markers precede the unchanged 36-ID research mailbox.')
    text = replace(text, '#include "lab-request-1375.h"', '#include "lab-request-1375.h"\n#include "owned-peace-stage-1375.h"')
    text = replace(text, 'static DWORD window_thread;', 'static DWORD window_thread;\nnamespace owned_phase = eu4_owned_peace_stage_1375;\nstatic owned_phase::State owned_peace{};\nstatic wchar_t owned_peace_request_file[MAX_PATH]{};')
    text = replace(text, 'static InputWait input_waits[4]{};', 'static InputWait input_waits[5]{};')
    text = replace(text, 'static void run_phase(unsigned phase) {',
                   '#include "owned-peace-host-1375.inc"\n\nstatic void run_phase(unsigned phase) {\n'
                   '    if (phase > 2 || (phase > 0 && !owned_phase::permits_later(owned_peace))) {\n'
                   '        freeze("owned_peace_phase_gate_failed"); return;\n    }')
    text = replace(text, '&& tested && selftest_passed && preview_tested && preview_passed && command_tested && command_passed',
                   '&& tested && selftest_passed && owned_phase::permits_later(owned_peace)\n'
                   '        && preview_tested && preview_passed && command_tested && command_passed')
    text = replace(text, 'selftest_passed, controls_guard', 'selftest_passed && owned_phase::permits_later(owned_peace), controls_guard', 2)
    text = replace(text, 'static void process_mailbox() {', 'static void process_mailbox() {\n'
                   '    if (!owned_phase::permits_later(owned_peace) || !selftest_passed || !preview_passed || !command_passed) {\n'
                   '        freeze("mailbox_phase_gate_failed"); return;\n    }')
    old = '''            else if (!tested) run_phase(0);
            else if (selftest_passed && !preview_tested && last_health_frame > last_phase_frame) run_phase(1);
            else if (preview_passed && !command_tested && last_health_frame > last_phase_frame) run_phase(2);
            else if (selftest_passed && preview_passed && command_passed && last_health_frame > last_phase_frame) process_mailbox();'''
    new = '''            else switch (owned_phase::next(tested, selftest_passed, owned_peace,
                preview_tested, preview_passed, command_tested, command_passed, last_health_frame > last_phase_frame)) {
                case owned_phase::Next::lifecycle: run_phase(0); break;
                case owned_phase::Next::owned_peace: run_owned_peace_phase(); break;
                case owned_phase::Next::preview: run_phase(1); break;
                case owned_phase::Next::command: run_phase(2); break;
                case owned_phase::Next::mailbox: process_mailbox(); break;
                case owned_phase::Next::none: break;
            }'''
    text = replace(text, old, new)
    text = replace(text, 'selftest_passed && preview_passed && command_passed',
                   'selftest_passed && owned_phase::permits_later(owned_peace) && preview_passed && command_passed', 3)
    text = replace(text, 'char line[1536]{};', 'char line[2048]{};')
    text = replace(text, r'\"lifecycle_passed\":%s,\"preview_passed\":%s',
                   r'\"lifecycle_passed\":%s,\"owned_peace_tested\":%s,\"owned_peace_passed\":%s,\"preview_passed\":%s')
    text = replace(text, '                preview_passed ? "true" : "false", command_passed ? "true" : "false", static_cast<unsigned long long>(last_sequence),',
                   '                owned_peace.tested ? "true" : "false", owned_phase::permits_later(owned_peace) ? "true" : "false",\n'
                   '                preview_passed ? "true" : "false", command_passed ? "true" : "false", static_cast<unsigned long long>(last_sequence),')
    text = replace(text, '        const DWORD exception = GetExceptionCode();\n        session_frozen = true;',
                   '        const DWORD exception = GetExceptionCode();\n        if (owned_peace.in_call) owned_phase::reject(owned_peace);\n        session_frozen = true;')
    return text

def bootstrap(text):
    text = replace(text, '|| !in_session_path(command_request_file, L"pair-command.request")) return 15;',
                   '|| !in_session_path(command_request_file, L"pair-command.request")\n'
                   '        || !in_session_path(owned_peace_request_file, L"owned-peace-lifecycle.request")) return 15;')
    text = replace(text, r'\"selftest_automatic\":false,\"preview_automatic\":false',
                   r'\"selftest_automatic\":false,\"owned_peace_automatic\":false,\"preview_automatic\":false')
    return text

def build_script(text):
    # This is a prospective source-set change for ROOT review, not a runnable
    # candidate build. Even after materialization, explicit root approval and
    # a reviewed v13 recorder are required. This generator never invokes it.
    text = replace(text, '@echo off\n', '@echo off\n'
                   'if not "%EU4_V13_ROOT_REVIEW_APPROVED%"=="1" (\n'
                   '  echo v13 formal build requires root source-set and host review.\n'
                   '  exit /b 90\n)\n')
    first = 'cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\\..\\runtime\\native1375-v13\\research-lab-1375.obj" research-lab-1375.cpp'
    text = replace(text, first, first + '\nif errorlevel 1 (popd & exit /b 1)\n'
                   'cl /nologo /c /std:c++17 /EHsc /O2 /W4 /WX /MT /GS /Fo"..\\..\\runtime\\native1375-v13\\peace-owned-lifecycle-1375.obj" peace-owned-lifecycle-1375.cpp')
    text = replace(text, ' kernel32.lib user32.lib advapi32.lib',
                   ' "..\\..\\runtime\\native1375-v13\\peace-owned-lifecycle-1375.obj" kernel32.lib user32.lib advapi32.lib')
    return text

def outputs():
    pins = audit_inputs()
    files, lineage, diffs = {}, [], []
    for item in pins:
        if item['role'] != 'frozen_v12_native': continue
        source = item['path']; destination = source.replace('/v12/', '/v13/').replace('-v12-', '-v13-')
        raw = (ROOT / source).read_bytes(); original = raw.decode('utf-8').replace('\r\n', '\n')
        # Keep the proven engine and all three ordinary phase units byte-identical.
        # Their internal v12_* symbols describe the reviewed implementation, not
        # an external protocol. Only destination includes/purpose/build change.
        versioned = source.endswith(('/research-lab-1375.cpp', '/research-lab-bootstrap-1375.inc', '/build-lab-1375.cmd')) or '/test-fixture-v12-' in source
        changed = original.replace('v12', 'v13') if versioned else original
        if source.endswith('/research-lab-1375.cpp'): changed = host(changed)
        if source.endswith('/research-lab-bootstrap-1375.inc'): changed = bootstrap(changed)
        if source.endswith('/build-lab-1375.cmd'): changed = build_script(changed)
        # Preserve each original source's newline convention and final newline.
        result = changed.replace('\n', '\r\n').encode() if b'\r\n' in raw else changed.encode()
        files['generated/' + destination] = result
        lineage.append({'path': destination, 'sha256': digest(result), 'bytes': len(result),
                        'origin': source, 'origin_sha256': item['sha256'], 'role': 'derived_frozen_v12'})
        diffs.extend(difflib.unified_diff(original.splitlines(True), changed.splitlines(True),
                                       fromfile=source, tofile=destination))
    added = ['peace-owned-lifecycle-1375.h', 'peace-owned-lifecycle-1375.cpp', 'default-contract.h', 'pins.h']
    for name in added + ['owned-peace-stage-1375.h', 'owned-peace-host-1375.inc']:
        source = OWNED / name if name in added else HERE / name
        raw = source.read_bytes(); destination = NEW + name
        files['generated/' + destination] = raw
        lineage.append({'path': destination, 'sha256': digest(raw), 'bytes': len(raw),
                        'origin': source.relative_to(ROOT).as_posix(), 'origin_sha256': digest(raw),
                        'role': 'unchanged_reviewed_owned_peace' if name in added else 'new_stage_adapter'})
        diffs.extend(difflib.unified_diff([], raw.decode().splitlines(True), fromfile='/dev/null', tofile=destination))
    if len(lineage) != 20: raise ValueError('Unexpected native source-set size')
    core = files['generated/' + NEW + 'peace-owned-lifecycle-1375.cpp'].decode()
    if '0x14ca210' in core or '0x4e9930' in core: raise ValueError('Peace core unexpectedly references submit/wrapper')
    files['candidate.diff'] = ''.join(diffs).encode()
    files['source-set.json'] = encode({'schema_version': 1, 'purpose': 'restricted_pair_lab_1375_v13',
        'source_count': len(lineage), 'sources': sorted(lineage, key=lambda x:x['path']),
        'formal_build_performed': False, 'materialized': False,
        'python_v13_host_status': 'separate_review_required_not_generated_here'})
    files['host-contract.json'] = encode({
        'schema_version': 1, 'purpose': 'restricted_pair_lab_1375_v13',
        'stages': ['lifecycle_20', 'owned_peace_default_lifecycle_1', 'preview_72', 'command_72'],
        'healthy_frame_required_between_stages_and_before_mailbox': True,
        'mailbox_pair_ids': 36, 'peace_mailbox_action_added': False,
        'marker': {'filename':'owned-peace-lifecycle.request', 'claim':'phase-owned-peace-lifecycle.claim',
            'ascii_template':'OWNED_PEACE_LIFECYCLE/1\npurpose=restricted_pair_lab_1375_v13\npid={decimal_pid}\ncreation={lowercase_16_hex_filetime}\n',
            'exact_roundtrip': True, 'durable_claim_before_native': True, 'once_per_session': True},
        'frame_fields': {'owned_peace_tested':'boolean', 'owned_peace_passed':'boolean'},
        'core_wrapper': {'event':'owned_peace_core_record', 'binding':['pid','process_creation_filetime','thread_id'],
            'nested_field':'core', 'nested_events':['owned_peace_lifecycle_step_begin','owned_peace_lifecycle_step_complete','owned_peace_lifecycle_return'],
            'submitted':False},
        'begin_event':'owned_peace_selftest_begin', 'complete_event':'owned_peace_selftest_complete',
        'complete_kind':'wrapper_result', 'complete_is_not_following_health_frame':True,
        'required_result_fields':['reason','core_passed','core_audit_complete','post_guard_ok','factory_entered','factory_returned',
            'clone_entered','clone_returned','original_destroy_entered','original_destroy_returned','clone_destroy_entered','clone_destroy_returned',
            'original_mismatch_mask','clone_mismatch_mask','distinct_owned_ranges','original_unchanged_after_clone',
            'clone_unchanged_after_original_destroy','exception','freeze_session','retry_allowed','execution_verified','submitted'],
        'phase_runtime_scope':'default_owned_peace_lifecycle_only', 'runtime_verified':False, 'execution_verified':False,
        'war_identity_verified':False, 'parameterized_offer_verified':False, 'world_generation_verified':False,
        'dll_contains_existing_research_sender':True, 'owned_peace_module_has_sender':False,
        'failure_policy':'freeze_session_keep_claim_no_retry_no_speculative_cleanup'})
    review_sources = ['prepare.py','input-pins.json','owned-peace-stage-1375.h','owned-peace-host-1375.inc','test_stage.cpp','verify_candidate.py','README.md']
    review = {'schema_version':1, 'purpose':'isolated_v13_owned_peace_candidate',
        'inputs_sha256':INPUT_SHA, 'input_count':len(pins), 'native_source_count':len(lineage),
        'candidate_files':[{'path':name,'sha256':digest((HERE/name).read_bytes())} for name in review_sources],
        'outputs':[{'path':name,'sha256':digest(raw),'bytes':len(raw)} for name,raw in sorted(files.items())],
        'runtime_verified':False, 'execution_verified':False, 'game_access':False, 'dll_built':False,
        'frozen_sources_modified':False, 'materialized':False,
        'unchanged_peace_core_files':added,
        'review_boundaries':['Root alone may materialize and perform one formal DLL build after review.',
            'No v13 Python host, manifest recorder, installer, verifier, or phase request writer is implemented here.',
            'Existing 36-ID research sender remains gated; this is not a no-send DLL.',
            'Default offer cleanup returns are not heap-release proof or war/negotiation/send validation.',
            'Pointer/date/player checks do not prove a reliable world epoch or all multiplayer origins.']}
    files['review.json'] = encode(review)
    audit_inputs() # Reject input changes during generation.
    return files

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    expected = outputs()
    for name, raw in expected.items():
        path = HERE / name
        if args.check:
            if not path.is_file() or path.read_bytes() != raw: raise ValueError('Stale candidate output: ' + name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    actual = {p.relative_to(HERE).as_posix() for p in (HERE/'generated').rglob('*') if p.is_file()}
    if actual != {p for p in expected if p.startswith('generated/')}: raise ValueError('Unexpected generated files')
    print(json.dumps({'checked':args.check, 'inputs':len(audit_inputs()), 'native_sources':20,
        'outputs':len(expected),'review_sha256':digest(expected['review.json']), 'runtime_verified':False}))
    return 0

if __name__ == '__main__': raise SystemExit(main())
