"""Root production file review and metadata promotion; no runtime capture."""
from pathlib import Path
import ast
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
SUB = 'work/candidates/peace-current-pending-observer-1375-v1/'
REVIEW = 'work/reports/peace-current-pending-observer-source-review-20261016-r1/'
OUT = ROOT / 'work/reports/peace-current-pending-observer-production-review-20261016-r1'
JOURNAL = []
TOTAL = 0


def pin(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def read(path, expected=None, phase='before'):
    global TOTAL
    p = (ROOT / path).resolve()
    assert p.is_relative_to(ROOT) and 0 <= p.stat().st_size <= 4194304
    with p.open('rb') as f:
        raw = f.read(4194305)
    assert len(raw) <= 4194304
    TOTAL += len(raw)
    assert TOTAL + 1048576 < 25165824
    actual = pin(raw)
    assert expected is None or expected == actual, path
    JOURNAL.append(dict(path=path, phase=phase, **actual))
    return raw


def save(path, value):
    raw = (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode()
    with path.open('xb') as f:
        f.write(raw)
    return pin(raw)


def main():
    assert not OUT.exists()
    expected_draft = dict(bytes=6644, sha256='126baac3a7ff0c0cb28244fcebae9a7f13c446b127ce2e2d494fbf5c63766b41')
    raw = read(SUB + 'source-manifest.json', expected_draft)
    assert read(SUB + 'draft-source-manifest.json', expected_draft) == raw
    draft = json.loads(raw)
    assert draft['sealed'] is draft['runtime_capture_authorized'] is False
    pins = draft['source_pins']
    assert len(pins) == 32
    graph = hashlib.sha256(json.dumps(pins, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest()
    assert graph == draft['source_graph_sha256'] == '488dbb0d2766e54cdea216c5ffd348c58ef93508d10dffe3e9341261ccec2ece'
    cache = {p: read(p, expected) for p, expected in pins.items()}
    cli = cache[SUB + 'peace_current_pending.py']
    assert pin(cli) == dict(bytes=23345, sha256='ac8c292d1320f776a6a8817f0158c275e624bcfe05f9a2dc51220e03532ba643')
    tree = ast.parse(cli)
    tests = ast.parse(cache[SUB + 'test_peace_current_pending.py'])
    count = sum(isinstance(n, ast.FunctionDef) and n.name.startswith('test_') for n in ast.walk(tests))
    assert count == 31
    review_pin = dict(bytes=7013, sha256='fc062117b569990120b3a86e8c5ff68954c6811376f0980ec1c4f3d38678b0e4')
    rm_pin = dict(bytes=12445, sha256='cd77dfff597ecdd21ca558516a3168ff8667dc2a0fa67aa9b7ebfd2ccf075966')
    sr = json.loads(read(REVIEW + 'findings.json', review_pin))
    read(REVIEW + 'manifest.json', rm_pin)
    assert sr['sealed'] is sr['passed'] is True and sr['blocking_findings'] == []
    assert sr['subject_cli_pin'] == pin(cli) and sr['subject_source_graph_sha256'] == graph
    assert sr['subject_draft_manifest'] == expected_draft
    assert sr['authority']['approved_for_current_readonly_status'] is False
    delivery_pin = dict(bytes=10004, sha256='32b2fa5493a6cd199c193a846eae2db2400a6b2176075831869badf190b65a78')
    delivery = json.loads(read(SUB + 'delivery-manifest.json', delivery_pin))
    for name, expected in delivery['files'].items():
        if SUB + name not in cache:
            cache[SUB + name] = read(SUB + name, expected)
        else:
            assert pin(cache[SUB + name]) == expected
    assert delivery['source_pins'] == pins and delivery['real_status_runs'] == 0
    receipt = json.loads(cache[SUB + 'offline-r1/receipt.json'])
    assert receipt['status'] == 'offline_passed' and receipt['actual_status_captures'] == 0
    assert receipt['source_pins'] == receipt['source_post_pins']
    assert [r['operation'] for r in receipt['operations']] == ['new_fake_suite', 'check', 'catalog']
    for rec in receipt['operations']:
        job = rec['job']
        assert rec['passed'] is True and rec['source_unchanged'] is True
        assert job['exit_code'] == 0 and job['error'] is None and job['job_active_processes_final'] == 0
        assert job['direct_child_collected'] is True and job['job_total_processes'] == 2
        assert job['peak_job_commit'] < job['memory_limit'] == 805306368
        assert rec['real_status_run'] is False and rec['game_access'] == rec['native_game_calls'] == 0
        for stream in ('stdout', 'stderr'):
            assert pin(cache[SUB + 'offline-r1/' + rec['operation'] + '-' + stream + '.txt']) == rec[stream]
    suite = json.loads(cache[SUB + 'offline-r1/new_fake_suite-stdout.txt'])
    assert suite['run'] == 31 and suite['failures'] == suite['errors'] == 0 and suite['passed'] is True
    # The root review examines source; it does not execute these snippets or the fake suite.
    source = cli.decode('utf-8')
    for text in ["if runtime or m['runtime_capture_authorized']:",
                 "for key in ('independent_source_review','production_review'):",
                 "v.get('subject_cli_pin')==expected[REL+'/peace_current_pending.py']",
                 "v.get('subject_source_graph_sha256')==g",
                 "v.get('approved_for_current_readonly_status') is True",
                 "self.calls<4096 and self.bytes+size<=512*1024",
                 "pe_header(r.read(self.base,8192))",
                 "require(deleted==0,'Tombstone: action must not be dereferenced')",
                 "require(cap.held is not None and cap.held.handle is None",
                 "close_os_return_checked=False"]:
        assert text in source
    queue_node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'queue_sample')
    queue_text = ast.get_source_segment(source, queue_node)
    assert queue_text.index('require(deleted==0') < queue_text.index('pointer(action)') < queue_text.index('vt_raw=r.read(action,8)')
    assert 'body=r.read(action,64)' in queue_text and 'a==o==actor_handle' in queue_text
    assert 'r.read(action,0x208)' not in source
    for p, expected in pins.items():
        read(p, expected, 'after')
    read(REVIEW + 'findings.json', review_pin, 'after')
    read(REVIEW + 'manifest.json', rm_pin, 'after')
    read(SUB + 'source-manifest.json', expected_draft, 'after')
    OUT.mkdir()
    with (OUT / 'subject-draft-manifest.json').open('xb') as f:
        f.write(raw)
    verification = save(OUT / 'verification.json', dict(schema='EU4-PEACE-PENDING-PRODUCTION-FILE-VERIFICATION/1',
        sealed=True, passed=True, canonical_source_count=32, source_graph_sha256=graph,
        test_methods31_first_receipt_only=True, independent_source_review_bound=True,
        before_after_graph_equal=True, code_prefix_guard735_per_pass=True,
        tombstone_before_action=True, target_inbox_only=True, close_before_commit=True,
        shared_budget_includes_entry8192=True, no_real_status=True, no_cli_or_test_execution=True,
        selected_file_reads=TOTAL, prior_manual_allowance=1048576, bounded_upper=TOTAL + 1048576,
        maximum=25165824, read_journal=JOURNAL))
    findings = save(OUT / 'findings.json', dict(schema='EU4-PEACE-PENDING-ROOT-PRODUCTION-REVIEW/1',
        sealed=True, passed=True, blocking_findings=[], subject_cli_pin=pin(cli),
        subject_source_graph_sha256=graph, subject_draft_manifest=expected_draft,
        independent_source_review=dict(path=REVIEW + 'findings.json', **review_pin),
        approved_for_current_readonly_status=True,
        stage='CURRENT_READONLY_STATUS_AUTHORIZED_LIVE_VALIDATION_PENDING',
        verification=verification,
        authorization='Use this exact CLI only for fresh PID/creation and explicitly selected actor->target current paused inbox. No game write or native call.',
        limits=['Approval is for current typed queue presence/absence, not successful dispatch, original request, acceptance, rejection or peace completion.',
                'Real world has not been sampled. No current compatibility/result is inferred from fake or file-only checks.',
                'Firstflag-zero and iteration0/no-tombstone complete-chain/count profile only; foreign8B or selectedpeace64B prefix. No offer/derived action reads.',
                'Two passes and roots/loaded code/identity/source guards are external coherence checks; no atomic snapshot, world lease, epoch or ABA exclusion.',
                '4096 attempted reads/512KiB requested/64KiB single includeentryPE8192; valid large graphs may fail closed unknown.',
                'Normal context exit and cleared handle are required; OS CloseHandle return is not independently checked.',
                'The frozen delegated host library graph and stable15/98pin tool are reused, not rewritten or recursively re-audited by this receipt.',
                'No real status is authorized until the pending loaded-world/manual-pause clarification is resolved by actual new user/environment evidence.'],
        authority=dict(native_ready=False, callable=False, selected_effect_verified=False, original_request_correlated=False,
            AI_acceptance_verified=False, AI_rejection_verified=False, peace_completed=False, persistence_verified=False,
            world_lease=False, atomic_snapshot=False, authorizes_retry=False),
        operations=dict(PE=0, decoder=0, game_process=0, native=0, requests=0, saves=0, tests_rerun=0)))
    promoted = dict(draft)
    promoted.update(sealed=True, runtime_capture_authorized=True,
        stage='source_reviewed_production_current_readonly_live_pending',
        independent_source_review=dict(path=REVIEW + 'findings.json', **review_pin),
        production_review=dict(path=str((OUT / 'findings.json').relative_to(ROOT)).replace('\\', '/'), **findings))
    tmp = ROOT / SUB / 'source-manifest.production.tmp'
    prod_pin = save(tmp, promoted)
    assert read(SUB + 'source-manifest.json', expected_draft, 'promotion_compare') == raw
    tmp.replace(ROOT / SUB / 'source-manifest.json')
    actual = read(SUB + 'source-manifest.json', prod_pin, 'promoted')
    assert json.loads(actual)['source_pins'] == pins
    manifest = save(OUT / 'manifest.json', dict(schema='EU4-PEACE-PENDING-PRODUCTION-DELIVERY/1',
        sealed=True, passed=True, subject_source_graph_sha256=graph,
        production_manifest=dict(path=SUB + 'source-manifest.json', **prod_pin),
        findings=findings, verification=verification,
        draft_snapshot=dict(path=str((OUT / 'subject-draft-manifest.json').relative_to(ROOT)).replace('\\', '/'), **expected_draft),
        source_review_manifest=dict(path=REVIEW + 'manifest.json', **rm_pin),
        author_delivery=dict(path=SUB + 'delivery-manifest.json', **delivery_pin),
        canonical_source_pins=pins,
        no_actual_status=True))
    with (ROOT / SUB / 'REVIEW_STATUS.md').open('x', encoding='utf-8', newline='\n') as f:
        f.write('# Review status (2026-10-16)\n\nSOURCE-READY and production reviewed for current read-only queue status. Live validation remains pending.\n\n'
                '31 new fake methods passed once. Independent source review and root production review both bind exact CLI/source graph.\n\n'
                'Canonical source-manifest.json has only review/authorization metadata promoted. draft-source-manifest.json, historical first-run reports, CLI and tests remain unchanged.\n\n'
                'Production review: `work/reports/peace-current-pending-observer-production-review-20261016-r1/findings.json`.\n\n'
                'A present/absent result describes the selected current inbox only. It proves no original-request success, acceptance or peace completion. No game write/native/Frida/save/reload was performed.\n')
    print(json.dumps(dict(passed=True, production_manifest=prod_pin, findings=findings,
        manifest=manifest, live_capture_runs=0, selected_file_reads=TOTAL), ensure_ascii=True))


if __name__ == '__main__':
    main()
