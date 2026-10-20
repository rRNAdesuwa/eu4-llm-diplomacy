"""Independent flat metadata/reference review. Never runs delivered programs."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import hashlib
import json
import sys
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
BASE = 'work/reports/war-peace-result-reader-gaps-20261016-v2/'
OUTREL = 'work/reports/war-peace-result-reader-gaps-v2-independent-20261016-r1/'
OUT = ROOT / OUTREL
LIMIT = 16 * 1024 * 1024
MEMORY = 768 * 1024 * 1024
CACHE_PIN = dict(bytes=1689456, sha256='9201d17deac96c942ba149e6a74b9156266f0fd96e26a1c45e2602e2bae75ea4')
SUBJECT_PIN = dict(bytes=8135, sha256='5473038352018d1de3ff358bc0605043ee64cb4d054d991044f9b5f4ab64b77e')
peak = 0
reads = []

class PMC(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
        (x, ctypes.c_size_t) for x in ('PeakWorkingSetSize', 'WorkingSetSize',
        'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
        'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]

k = ctypes.WinDLL('kernel32', use_last_error=True)
p = ctypes.WinDLL('psapi', use_last_error=True)
k.GetCurrentProcess.restype = wintypes.HANDLE
p.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]

def guard():
    global peak
    x = PMC(); x.cb = ctypes.sizeof(x)
    assert p.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(x), x.cb)
    peak = max(peak, x.WorkingSetSize, x.PrivateUsage, x.PeakWorkingSetSize, x.PeakPagefileUsage)
    assert peak <= MEMORY

def pin(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

def pairs(items):
    out = {}
    for key, value in items:
        assert key not in out, ('duplicate JSON key', key)
        out[key] = value
    return out

def decode(raw):
    return json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))

def read(path, expected=None):
    assert not path.startswith('work/deps/') and 'eu4.exe' not in path.lower()
    guard(); f = ROOT / path; a = f.stat()
    assert a.st_size <= 4 * 1024 * 1024
    raw = f.read_bytes(); b = f.stat()
    assert len(raw) == a.st_size and (a.st_size, a.st_mtime_ns) == (b.st_size, b.st_mtime_ns)
    pn = pin(raw)
    if expected is not None:
        assert pn == expected, (path, pn, expected)
    reads.append(dict(path=path, **pn)); guard()
    return raw

def write(name, value):
    raw = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode('ascii')
    assert len(raw) <= 4 * 1024 * 1024
    with (OUT / name).open('xb') as f:
        f.write(raw)
    return pin(raw)

def pointer(value, text):
    if text == '': return value
    assert text.startswith('/')
    for part in text[1:].split('/'):
        part = part.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            assert part.isdigit() and (part == '0' or not part.startswith('0'))
            value = value[int(part)]
        else:
            assert isinstance(value, dict) and part in value
            value = value[part]
    return value

def references(value, location=''):
    found = []
    if isinstance(value, dict):
        if {'path', 'bytes', 'sha256', 'json_pointer'} <= set(value):
            found.append((location, value))
        for key, child in value.items():
            found.extend(references(child, location + '/' + key))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            found.extend(references(child, location + '/' + str(i)))
    return found

def all_false(value):
    assert isinstance(value, dict) and value and all(v is False for v in value.values())

def checked_review(value):
    assert value['sealed'] is True and value['passed'] is True
    assert value['blocking_findings'] == []

def main():
    cache = decode(read(OUTREL + 'retained-metadata.json', CACHE_PIN))
    files = cache['files']
    objects = {}
    for path, entry in files.items():
        raw = bytes.fromhex(entry['raw_hex'])
        assert pin(raw) == {k: entry[k] for k in ('bytes', 'sha256')}
        if path.endswith('.json'): objects[path] = decode(raw)
    subject = objects[BASE + 'manifest.json']
    assert {k: files[BASE + 'manifest.json'][k] for k in ('bytes', 'sha256')} == SUBJECT_PIN
    sources = subject['captured_source_pins']; local = subject['local_pins']
    assert len(sources) == 22 and len(local) == 15
    combined = objects[BASE + 'combined-source-pins.json']
    assert combined == sources
    assert objects[BASE + 'source-pins.json'] | objects[BASE + 'extension-source.json']['source_pins'] == sources
    captured = objects[BASE + 'selected-sources.json'] | objects[BASE + 'extension-source.json']['documents']
    assert set(captured) == set(sources)
    assert all(captured[path] == objects[path] for path in sources)
    for path, pn in {**sources, **local}.items():
        assert {k: files[path][k] for k in ('bytes', 'sha256')} == pn
    ledger = objects[BASE + 'gap-ledger-v2.json']
    assert ledger['schema'] == 'EU4-WAR-PEACE-RESULT-READER-GAPS/2'
    refs = references(ledger)
    assert len(refs) == 43, len(refs)
    resolved = []
    for loc, ref in refs:
        assert ref['path'] in sources
        assert {k: ref[k] for k in ('bytes', 'sha256')} == sources[ref['path']]
        selected = pointer(objects[ref['path']], ref['json_pointer'])
        canonical = json.dumps(selected, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('ascii')
        resolved.append(dict(ledger_pointer=loc, **ref, selected_value_type=type(selected).__name__,
            selected_value_canonical_sha256=hashlib.sha256(canonical).hexdigest()))
    old = objects[ledger['baseline']['path']]
    previous = old['result_questions']; questions = ledger['questions']
    assert len(previous) == len(questions) == 15
    lineage = []
    for a, b in zip(previous, questions):
        assert (a['id'], a['question']) == (b['id'], b['question'])
        assert b['inherited_scope'] == a['current_sufficient_for']
        assert b['previous_unresolved_preserved'] == a['unknown_or_not_proved']
        assert b['request_effect_authenticated'] is False and b['selected_term_effect_verified'] is False
        assert b['live_state_newly_validated'] is False
        lineage.append(dict(id=b['id'], question_preserved=True, inherited_scope_equal=True,
            previous_unknowns_equal=True, status=b['status']))
    expected_counts = {'current_scope_available_inherited': 4,
        'current_reader_source_production_ready_live_pending': 1,
        'inference_boundary_settled_result_open': 1,
        'partial_reviewed_static_no_settlement_oracle': 1, 'original_request_result_open': 8}
    assert dict(Counter(q['status'] for q in questions)) == expected_counts
    summary = ledger['summary']
    assert summary['status_counts'] == expected_counts
    assert summary['original_questions'] == 15 and summary['new_fully_verified_original_request_effects'] == 0
    assert summary['newly_accepted_static_fact_groups'] == 3
    assert summary['current_pending_reader_live_validated'] is False
    assert summary['current_pending_reader_source_production_and_check_ready'] is True
    assert sorted(ledger['unchanged_counts'].values()) == [15, 42, 44, 48]
    assert ledger['historical_native_calls']['new_native_game_calls'] == 0
    assert ledger['historical_native_calls']['top_level_game_native_total'] == 1
    all_false(ledger['authority']); all_false(subject['authority'])
    assert all(v == 0 for v in ledger['operations'].values())
    assert all(x['execution_authorized_by_this_ledger'] is False for x in ledger['next_priorities'])
    by_id = {q['id']: q for q in questions}
    assert by_id['P4_acceptance_response']['status'] == 'current_reader_source_production_ready_live_pending'
    assert by_id['P5_terminal_mark_vs_finish']['status'] == 'inference_boundary_settled_result_open'
    assert by_id['P7_gold_terms']['status'] == 'partial_reviewed_static_no_settlement_oracle'
    increments = {x['id']: x for x in ledger['accepted_increments']}
    assert len(increments) == 5
    counter = increments['F1_native_counter_conditional_path']
    assert 'oldV!=ffffffff' in counter['observation'] and 'ffffffff' in counter['observation']
    assert 'INT3' in counter['observation'] and 'mod32' in counter['observation']
    assert any('epoch' in x and 'wrap' in x for x in counter['not_proved'])
    assert any('bridge request_id' in x for x in counter['not_proved'])
    review_paths = [p for p in sources if p.endswith('/findings.json')]
    for path in review_paths: checked_review(objects[path])
    prod_path = 'work/reports/peace-current-pending-observer-production-review-20261016-r1/findings.json'
    prod = objects[prod_path]
    assert prod['approved_for_current_readonly_status'] is True
    assert 'LIVE_VALIDATION_PENDING' in prod['stage']
    all_false(prod['authority'])
    check_path = 'work/reports/peace-current-pending-observer-production-check-20261016-r1/receipt.json'
    check = objects[check_path]
    assert check.get('passed', check.get('success', True)) is True
    doc = objects['docs/runtime-capability-map-1375-v3.json']
    assert doc['accepted_entry_count'] == 5 and doc['pending_active_world_reader_count'] == 2
    assert len(doc['tools']) == 7 and doc['authoritative_for_permissions'] is False
    assert doc['historical_effect_signals'] == 48 and doc['historical_persistence_aggregate'] == 44
    assert doc['remaining_repair_candidates'] == 42 and doc['current_process_authenticated'] is False
    published = ledger['published_tool_directory']
    assert published['accepted_entries'] == 5 and published['pending_active_world_readers'] == 2
    assert published['permission_authority'] is False
    index = objects['work/candidates/war-peace-api-lookup-1375-v3/index.json']
    assert len(index['entries']) == 54 and index['not_a_callable_API'] is True
    def rva(entry):
        n = entry['rva']; return int(n, 16) if isinstance(n, str) else n
    numbers = {rva(e) for e in index['entries']}
    assert {0x9b46a0, 0x3383b0, 0x771be0, 0x9844d0} <= numbers
    assert 0x97b2c0 not in numbers and 0x97b8a0 not in numbers
    for entry in index['entries']:
        for field in ('native_ready', 'callable', 'sender_authorized', 'process_authenticated'):
            assert entry[field] is False
    counter_entry = next(e for e in index['entries'] if rva(e) == 0x771be0)
    assert 'conditional_path' in json.dumps(counter_entry)
    lookup_review = objects['work/reports/war-peace-api-lookup-v3-independent-review-20261016-r1/findings.json']
    assert '54 entries / 44 flat retained JSON sources; original50 unchanged' in lookup_review['result']
    assert objects[BASE + 'delta.json']['lookup_index_R63_inclusion'] is False
    pending = ledger['pending_reviews']
    assert len(pending) == 1 and pending[0]['id'] == 'R64'
    assert pending[0]['acceptance'] == 'author_result_pending_full_independent_review_at_this_snapshot'
    assert pending[0]['used_to_close_any_gap'] is False
    late_path = 'work/reports/war-peace-api-20261016-r64-independent-review/findings.json'
    late = objects[late_path]; checked_review(late)
    assert late['subject_manifest'] == sources['work/reports/war-peace-api-20261016-r64-gold-element-selection/manifest.json']
    assert late['subject_contract'] == sources['work/reports/war-peace-api-20261016-r64-gold-element-selection/contract.json']
    all_false(late['authority'])
    # Re-hash only this retained flat set, never recurse source manifests.
    for path, entry in files.items():
        read(path, {k: entry[k] for k in ('bytes', 'sha256')})
    post_bytes = sum(x['bytes'] for x in reads[1:])
    # Four metadata-inspection cache reads preceded this producer. 64KiB covers
    # the small script inspection/note; this is conservative listed I/O, not OS I/O.
    prior_inspection_upper = 4 * CACHE_PIN['bytes'] + 65536
    explicit_upper = cache['source_physical_bytes'] + prior_inspection_upper + sum(x['bytes'] for x in reads)
    assert explicit_upper < LIMIT
    rp = write('refs-verification.json', dict(schema='EU4-GAP-V2-INDEPENDENT-REFS/1', passed=True,
        source_count=22, local_count=15, reference_occurrences=len(refs),
        unique_reference_targets=len({(r['path'], r['json_pointer']) for _, r in refs}),
        all_refs_exact_pins_and_pointers=True, selected_source_values_equal=True,
        old_question_lineage=lineage, status_counts=expected_counts, resolved=resolved,
        flat_source_postguard=reads[1:], source_postguard_equal=True,
        no_recursive_sources_or_machine_raw_reanalysis=True))
    notes = [
        'R64 pending is correct for the immutable v2 snapshot. The later independent full review is separately pinned here; it does not rewrite that snapshot or settle P7.',
        'Current queue presence/absence and raw state do not prove original-request acceptance, rejection, term completion, persistence or request-ID correlation.',
        'The ledger future-priority wording about separate authorization means a new bounded root run scope. The user already authorized read-only testing; fresh loaded-world/manual-pause evidence remains the concrete runtime prerequisite.',
        'Native-call history1 and effects48/persistence44/repair42/profiles15 are inherited exact metadata, not newly recounted or runtime-authenticated by this audit.',
        'The v3 index excludes R63; its original50 equality and 44-source boundary are inherited from its pinned full independent review, not re-executed or recursively re-audited here.',
        'Counter selected path remains conditional: oldFFFFFFFF writes zero before an unknown error call/INT3; no ordinary wrap, unique ID, bridge binding, retry or epoch authority.',
        'All references are exact-pin JSON pointers into the22 flat delivered sources. Producer budget/PE/decoder evidence remains author or prior-review witness, not new machine-byte authentication.',
        'Initial wrong guessed filename caused only a failed stat (0failed-read bytes). A later metadata inspection failed GBK console encoding after reading the retained cache. Neither changed delivered files or ran delivered code.'
    ]
    operations = {k: 0 for k in ('PE', 'engine', 'decoder', 'game_process', 'native_game_calls',
        'CLI', 'tests', 'author_programs', 'requests', 'saves', 'new_scope_actual')}
    authority = {k: False for k in ledger['authority']}
    findings = dict(schema='EU4-GAP-V2-INDEPENDENT-FINDINGS/1', sealed=True, passed=True,
        subject_manifest=SUBJECT_PIN, subject_ledger=sources.get(BASE + 'gap-ledger-v2.json', local[BASE + 'gap-ledger-v2.json']),
        blocking_findings=[], author_frozen_source_needs_change=False,
        stage='FLAT_METADATA_REFERENCE_AND_CLASSIFICATION_REVIEW_ONLY', refs_verification=rp,
        checks=dict(flat_sources=22, local_pins=15, references=43, original_questions_preserved=15,
            status_counts=expected_counts, new_original_request_effects=0,
            inherited_effects_persistence_repair_profiles=ledger['unchanged_counts'],
            historical_top_level_native_calls=1, new_native_calls=0,
            current_pending_live_pending=True, R63_excluded_from_frozen_v3=True,
            future_priorities_authorize_execution=False),
        late_R64_annotation=dict(path=late_path, **cache['late_annotation_pins'][late_path],
            full_independent_review_passed_after_subject_snapshot=True,
            subject_manifest_matches=True, old_snapshot_modified=False,
            selected_gold_settlement_verified=False),
        precision_notes=notes, operations=operations, authority=authority,
        independent_resources=dict(retention_explicit_bytes=cache['source_physical_bytes'],
            prior_inspection_upper_bytes=prior_inspection_upper,
            final_cache_and_flat_postguard_bytes=sum(x['bytes'] for x in reads),
            flat_postguard_bytes=post_bytes, listed_analysis_upper_bytes=explicit_upper,
            source_limit_bytes=LIMIT, own_peak_bytes=peak, software_memory_limit_bytes=MEMORY,
            source_budget_not_all_OS_or_loader_IO=True, recursive_closure=False),
        self_diagnostics=dict(initial_wrong_filename_stat_retained=True,
            metadata_console_encoding_failure='UnicodeEncodeError: GBK could not print U+2194; no delivered-file change',
            review_producer_failures=0), all_shells_collected=True, next_scope_auto_authorized=False)
    fp = write('findings.json', findings)
    report = ('Independent file-only review passed. All43 exact-pin JSON references resolve into22 flat sources; '
        'the15 historical questions, inherited sufficient scopes and unknowns are unchanged. '
        'Classification is4 current,1 settled inference boundary with result open,1 current pending-reader '
        'source/production/check ready but live pending,1 partial static gold line,8 original results open. '
        'New effects and native calls are0. R64 laterfullreview is a separate annotation. '
        'No PE/engine/decoder/program/CLI/test/game/native execution occurred.\n\n'
        + '\n'.join('- ' + x for x in notes) + '\n').encode('ascii')
    with (OUT / 'report.md').open('xb') as f: f.write(report)
    own = {OUTREL + name: pin((OUT / name).read_bytes()) for name in
        ('retained-metadata.json', 'initial-inspection-note.json', 'refs-verification.json', 'findings.json', 'report.md')}
    own['work/audit_gap_v2_20261016.py'] = pin((ROOT / 'work/audit_gap_v2_20261016.py').read_bytes())
    own['work/review_gap_v2_20261016.py'] = pin(Path(__file__).read_bytes())
    flatpins = {path: {k: entry[k] for k in ('bytes', 'sha256')} for path, entry in files.items()}
    mp = write('manifest.json', dict(schema='EU4-GAP-V2-INDEPENDENT-MANIFEST/1', sealed=True,
        source_pins=flatpins, local_pins=own, source_count=len(flatpins),
        source_scope='15local+22explicit sources+subject manifest+2late R64 annotations; no recursion',
        subject_manifest=SUBJECT_PIN, findings=fp, operations=operations, authority=authority))
    print(json.dumps(dict(passed=True, findings=fp, refs_verification=rp, manifest=mp,
        listed_analysis_upper_bytes=explicit_upper, peak=peak, all_shells_collected=True)))

def check():
    m = decode(read(OUTREL + 'manifest.json'))
    for path, pn in (m['source_pins'] | m['local_pins']).items(): read(path, pn)
    amount = sum(x['bytes'] for x in reads)
    f = decode((OUT / 'findings.json').read_bytes())
    upper = f['independent_resources']['listed_analysis_upper_bytes'] + amount
    assert upper < LIMIT
    result = dict(schema='EU4-GAP-V2-INDEPENDENT-VERIFICATION/1', passed=True,
        checked_pins=len(m['source_pins'] | m['local_pins']), manifest=pin((OUT / 'manifest.json').read_bytes()),
        byte_verification_only=True, current_flat_sources_equal=True,
        check_listed_bytes=amount, conservative_full_review_upper_bytes=upper,
        limit_bytes=LIMIT, own_peak_bytes=peak, all_shells_collected=True,
        operations=m['operations'], authority=m['authority'])
    vp = write('verification.json', result)
    print(json.dumps(dict(passed=True, verification=vp, bytes=amount, conservative_full_review_upper_bytes=upper, peak=peak)))

if __name__ == '__main__':
    try:
        check() if sys.argv[1:] == ['--check'] else main()
    except Exception as exc:
        name = 'review-failure.json' if sys.argv[1:] != ['--check'] else 'verification-failure.json'
        if not (OUT / name).exists():
            write(name, dict(type=type(exc).__name__, detail=str(exc), reads=reads, peak=peak,
                author_sources_unchanged=True, no_PE_or_program_replay=True))
        raise
