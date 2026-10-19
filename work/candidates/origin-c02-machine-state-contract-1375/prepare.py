"""Reconstruct a contract from pinned existing evidence; never opens a process or EXE."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MAX_FILE = 4 * 1024 * 1024
SOURCE_FILES = ('model.py', 'test_model.py', 'prepare.py', 'validate.py', 'README.md', 'references.json', 'pins.json')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    if path.stat().st_size > MAX_FILE:
        raise ValueError('input exceeds bound')
    return json.loads(path.read_text(encoding='utf-8'))


def demand(condition, message):
    if not condition:
        raise ValueError(message)


def build():
    pins = load(HERE / 'pins.json')
    for name, pin in pins['files'].items():
        p = ROOT / name
        demand(p.resolve().is_relative_to(ROOT.resolve()), 'pin outside repository')
        demand(p.stat().st_size == pin['size_bytes'] and digest(p) == pin['sha256'], 'pin changed: ' + name)
    c01 = load(ROOT / 'work/candidates/origin-c01-unwind-relocation-1375/report.json')
    demand(c01['game_sha256'] == '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a', 'EXE identity')
    entry, parent = c01['functions']['0x80b4c0'], c01['functions']['0x803270']
    demand(entry['unwind']['flags'] == parent['unwind']['flags'] == 2, 'UHANDLER')
    demand(entry['unwind']['prolog_bytes'] == 15, 'callee prolog')
    demand(sum(x.get('stack_delta', 0) for x in entry['unwind']['codes']) == -0x28, 'entry stack')
    demand(sum(x.get('stack_delta', 0) for x in parent['unwind']['codes']) == -0x488, 'caller stack')
    demand(c01['continuation_unwind_chain'][0]['state'] == 31, 'continuation state')
    demand(32 not in [x['state'] for x in c01['continuation_unwind_chain']], 'cleanup gap')
    demand(parent['fh4']['unwind_entries'][32]['action_rva'] == '0x1ae6890', 'config cleanup')
    expected_spans = [(5, '48895c2410'), (15, '48895c241048894c2408574883ec20'),
                      (12, '9048c786f819000000000000'), (23, '9048c786f81900000000000048c786001a000000000000')]
    for span, (length, code) in zip(c01['candidate_spans'], expected_spans, strict=True):
        demand(span['span'] == length and ''.join(i['bytes'] for i in span['instructions']) == code, 'candidate bytes')
        demand(span['approved_patch'] is False and span['all_program_incoming_edges_proved'] is False, 'unapproved site')
    boundaries = [
        {'id': 'B0', 'site_rva': '0x80b4c0', 'phase': 'before_original_instruction',
         'entry_rsp_mod16': 8, 'original_stack_return_rva': '0x803d2c',
         'binding': ['RCX=destination', 'RDX=source', 'raw RSP and [RSP] before recorder changes'],
         'helper_frame_bytes': None, 'preservation_sequence': None, 'unwind_metadata': None},
        {'id': 'B1', 'site_rva': '0x803d2c', 'phase': 'before_original_instruction',
         'entry_rsp_mod16': 0, 'required_rsp': 'same config-copy entry RSP + 8',
         'binding': ['RAX=entry destination', 'same thread/span/parent/generation', 'original CALL/return untouched'],
         'helper_frame_bytes': None, 'preservation_sequence': None, 'unwind_metadata': None}
    ]
    blockers = [
        ('C02-GPR', 'No final machine-code adapter or exhaustive live-state proof',
         'Separate same-PC preservation from native effects; audit every instruction and scratch register including initial save/final restore.'),
        ('C02-FLAGS', 'No permitted RFLAGS capture/restore profile',
         'Define user-restorable bits, DF/TF/RF/debug behavior and first flag-changing instruction; reject unsupported state without corrupting it.'),
        ('C02-XSTATE', 'No actual CPU/OS feature identity or enabled-state mapping',
         'Pin supported CPUID/XCR0/OS-enabled profile, component layout/size/alignment/init semantics; preserve all live enabled state or reject before installation.'),
        ('C02-STACK', 'No proven private recorder frame/unwind at each transient RSP',
         'Choose bounded own storage, own 32B call home area, alignment, guard-page/stack-limit policy and untouched caller stack/return.'),
        ('C02-FH4', 'Continuation state31 omits state32 config cleanup',
         'Demonstrate an exception routing scheme preserving exact native cleanup without calling engine destructors or inventing IP state.'),
        ('C02-UNWIND', 'No registered adapter pdata/xdata or isolation exception tests',
         'At every save/call/restore/relocated boundary test virtual unwind and actual isolated exception propagation, including nested cleanup faults.'),
        ('C02-TLS', 'No no-side-effect recorder machine-code proof',
         'Audit imported calls, stack probes, security helpers, LastError/errno/engine TLS and recursion; preinitialize owned storage outside capture.'),
        ('C02-ASYNC', 'No proven termination notification before skipping an active token',
         'Bind exact invocation, atomically revoke before diagnostic log; missing return/foreign thread/reentry remains terminal even if logging fails.'),
        ('C02-INSTALL', 'Unknown incoming edges, mitigation policy and installation concurrency',
         'Separate early-start owner/thread and IP-safe install proof; no return rewriting, policy disabling, reset or unload while references remain.')
    ]
    return {
        'schema': 'origin_c02_machine_state_contract_v1', 'game_sha256': c01['game_sha256'],
        'evidence_pins_sha256': digest(HERE / 'pins.json'),
        'source_sha256': {name: digest(HERE / name) for name in SOURCE_FILES},
        'prior_report_sha256': digest(ROOT / 'work/candidates/origin-c01-unwind-relocation-1375/report.json'),
        'runtime_supported_profiles': [], 'approved_patch_spans': [],
        'scope': {'hook_code_written': False, 'hook_installed': False, 'native_compiled': False,
                  'game_process_accessed': False, 'machine_state_capture_verified': False,
                  'exception_transparency_verified': False, 'strict_single_player_verified': False,
                  'world_epoch_coverage_verified': False, 'engine_lifetime_synchronized': False,
                  'native_execution_authorized': False, 'production_ready': False},
        'boundaries': boundaries,
        'restoration_contract': {
            'comparison_point': 'same original PC before any relocated/native instruction',
            'gpr': 'all classic 16 GPR, including volatile values and original RSP; extra architectural GPR unsupported',
            'rflags': 'preserve actual live supported state; synthetic uint64 equality is not an executable capture recipe',
            'vectors': 'all live enabled components, including volatile upper vector state; ordinary nonvolatile ABI alone insufficient',
            'control_state': 'full MXCSR plus x87 control/status/tag/data and any other enabled supported state',
            'stack': 'do not use original shadow space as scratch; no red-zone reliance; preserve original return identity',
            'thread_state': 'recorder must not leave changed LastError/errno or engine TLS; modeled subset is not complete TLS proof'},
        'original_effects_separate_from_recorder': [
            'entry first two MOV write original RSP+10/RSP+8; PUSH RDI and SUB RSP20 change stack, SUB changes arithmetic flags',
            'continuation NOP then server+19f8 and +1a00 zero stores retain native order; writes may fault',
            'normal callee may change ABI-volatile state; only recorder boundary is bit-equality'],
        'c01_evidence': {'call_binding': c01['call_binding'], 'candidate_spans': c01['candidate_spans'],
                         'callee_unwind': entry['unwind'], 'parent_unwind': parent['unwind'],
                         'continuation_chain': c01['continuation_unwind_chain'],
                         'state32': parent['fh4']['unwind_entries'][32]},
        'exception_policy': {
            'native_exception': 'must propagate original exception and preserve engine FH4 cleanup; required but unimplemented',
            'recorder_fault': 'unsupported; no swallow/continue, no retry, no guessed native cleanup',
            'stack_overflow_or_unwinding_failure': 'unsupported; not guaranteed that even terminal diagnostic store can complete',
            'capture_terminal': 'first detected invalidation before diagnostic publication where execution permits; never cleared',
            'normal_event_on_exception': False, 'automatic_resume_or_dtor': False},
        'blockers': [{'id': i, 'status': 'unsupported', 'missing': m, 'minimal_next_evidence': e} for i, m, e in blockers],
        'offline_model': {'purpose': 'typed bounded counterexamples only', 'max_packet_bytes': 16384,
                          'synthetic_profiles': ['synthetic_legacy_sse', 'synthetic_avx'],
                          'not_modeled': ['actual save instructions', 'raw XSAVE format/padding', 'APX/AVX512/AMX/PKRU/CET',
                                          'all process/thread memory', 'native FH4 execution', 'thread authenticity'],
                          'passes_do_not_enable_runtime_profiles': True},
        'resource_use': {'new_exe_decoded_bytes': 0, 'process_reads': 0, 'max_json_input_bytes': MAX_FILE,
                         'no_shell_left_running_required': True}
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    raw = (json.dumps(build(), ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    target = HERE / 'contract.json'
    if args.check:
        demand(target.read_bytes() == raw, 'contract bytes differ')
    else:
        with target.open('xb') as f:
            f.write(raw)
    print(json.dumps({'check': args.check, 'sha256': hashlib.sha256(raw).hexdigest(),
                      'size_bytes': len(raw), 'runtime_supported_profiles': [], 'new_decode_bytes': 0}))


if __name__ == '__main__':
    main()
