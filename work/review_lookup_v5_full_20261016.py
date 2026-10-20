"""Non-author flat-file/AST review. Never import or execute subject programs."""
import ast
import ctypes
import hashlib
import json
import re
import traceback
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/war-peace-api-lookup-v5-independent-review-20261016-r1'
BASE = 'work/candidates/war-peace-api-lookup-1375-v5/'
OLD = 'work/candidates/war-peace-api-lookup-1375-v4/'
GAME = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
FLAGS = ('callable', 'native_ready', 'sender_authorized', 'gameplay_effect_verified',
         'process_authenticated', 'selected_effect_verified', 'world_lease', 'atomic_snapshot', 'authorizes_retry')
LIMIT = 32 * 1024 * 1024
RETAINED = 8 * 1024 * 1024
MANUAL = 2 * 1024 * 1024
reads = []
raws = {}
peak = 0


class PMC(ctypes.Structure):
    _fields_ = [('cb', ctypes.c_ulong), ('faults', ctypes.c_ulong)] + [(n, ctypes.c_size_t) for n in
        ('pw', 'w', 'pp', 'p', 'pn', 'n', 'pf', 'ppf', 'private')]


k = ctypes.WinDLL('kernel32', use_last_error=True)
k.GetCurrentProcess.restype = ctypes.c_void_p
ps = ctypes.WinDLL('psapi', use_last_error=True)


def memory():
    global peak
    x = PMC(); x.cb = ctypes.sizeof(x)
    assert ps.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()), ctypes.byref(x), x.cb)
    peak = max(peak, x.pw, x.ppf, x.private)
    assert peak < 1024 * 1024 * 1024 and peak <= 768 * 1024 * 1024


def pin(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def read(path, expected=None, phase='owned'):
    memory()
    path = path.resolve()
    assert path.is_relative_to(ROOT) and path.suffix.lower() not in ('.exe', '.dll', '.pyd')
    a = path.stat(); assert a.st_size <= 4 * 1024 * 1024
    assert sum(x['bytes'] for x in reads) + a.st_size + MANUAL + 3512355 < LIMIT
    raw = path.read_bytes(); b = path.stat()
    assert (len(raw), a.st_size, a.st_mtime_ns) == (b.st_size, b.st_size, b.st_mtime_ns)
    value = pin(raw)
    reads.append(dict(path=path.relative_to(ROOT).as_posix(), phase=phase, **value))
    if expected is not None:
        assert value == expected, str(path)
    return raw


def document(rel):
    return json.loads(raws[rel])


def pointer(obj, text):
    assert isinstance(text, str) and (text == '' or text.startswith('/'))
    for segment in text.split('/')[1:] if text else []:
        assert not re.search(r'~(?![01])', segment)
        segment = segment.replace('~1', '/').replace('~0', '~')
        if isinstance(obj, list):
            assert re.fullmatch(r'0|[1-9][0-9]*', segment)
            obj = obj[int(segment)]
        else:
            assert isinstance(obj, dict) and segment in obj
            obj = obj[segment]
    return obj


def write(name, value):
    data = (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode()
    assert len(data) <= 4 * 1024 * 1024
    with (OUT / name).open('xb') as f:
        f.write(data)
    return pin(data)


def job_check(record, expected_exit):
    j = record['job']
    assert j['exit_code'] == expected_exit and j['error'] is None
    assert j['direct_child_collected'] and j['job_active_processes_final'] == 0 and j['job_total_processes'] == 2
    assert j['memory_limit'] == 768 * 1024 * 1024 and j['peak_job_commit'] <= j['memory_limit']
    assert j['completed_command_descendants_terminated'] is False and j['existing_target_game_assigned_to_job'] is False


def check_journal(items):
    for item in items:
        rel = item['path']
        assert rel in raws and pin(raws[rel]) == {x: item[x] for x in ('bytes', 'sha256')}, rel
    return sum(x['bytes'] for x in items)


def main():
    intake_pin = dict(bytes=37504, sha256='786546ce426441948bfe6d646467ed67d68180a4386bbb583e053fc4b6deb4a9')
    intake = json.loads(read(OUT / 'intake.json', intake_pin))
    assert intake['intake_passed'] and intake['complete_review_passed'] is False
    assert len(intake['cached']) == 144 and intake['selected_read_bytes'] == 3512355
    for rel, item in intake['cached'].items():
        name = PurePosixPath(rel)
        assert not name.is_absolute() and '..' not in name.parts and ':' not in rel and '\\' not in rel
        raws[rel] = read(OUT / item['owned'], item['pin'])
    source, author, pub = [document(BASE + n) for n in ('source-manifest.json', 'author-manifest.json', 'publication-manifest.json')]
    assert source['sealed'] and author['sealed'] and pub['sealed']
    assert author['subject_source_manifest'] == pin(raws[BASE + 'source-manifest.json'])
    assert pub['author_manifest'] == pin(raws[BASE + 'author-manifest.json'])
    assert len(author['local_and_selected_source_pins']) == author['pin_count'] == 136
    for group in (source['files'], author['local_and_selected_source_pins'], pub['additional_and_delivery_pins']):
        for rel, expected in group.items():
            assert rel in raws and pin(raws[rel]) == expected

    original = raws['work/candidates/war-peace-api-lookup-1375-v1/war_peace_lookup.py']
    engine = raws[BASE + 'query_engine.py']
    assert original == raws[BASE + 'lineage/frozen_query_engine.py']
    needle = b'1 <= len(sources) <= 64'
    assert original.count(needle) == 1
    assert original.replace(needle, b'1 <= len(sources) <= 96') == engine
    delta = [i for i, pair in enumerate(zip(original, engine)) if pair[0] != pair[1]]
    assert delta == [9450, 9451]
    old_tree, new_tree = ast.parse(original), ast.parse(engine)
    changes = [n for n in ast.walk(new_tree) if isinstance(n, ast.Constant) and n.value == 96]
    assert len(changes) == 1
    changes[0].value = 64
    assert ast.dump(old_tree) == ast.dump(new_tree)
    imports = {n.module.split('.')[0] for n in ast.walk(ast.parse(engine)) if isinstance(n, ast.ImportFrom)}
    imports |= {a.name.split('.')[0] for n in ast.walk(ast.parse(engine)) if isinstance(n, ast.Import) for a in n.names}
    assert imports <= {'__future__', 'argparse', 'copy', 'hashlib', 'json', 'pathlib', 're', 'sys'}
    old_wrap, wrap = raws[OLD + 'war_peace_lookup.py'], raws[BASE + 'war_peace_lookup.py']
    replacement = old_wrap.replace(b'work/candidates/war-peace-api-lookup-1375-v1/war_peace_lookup.py',
                                   b'work/candidates/war-peace-api-lookup-1375-v5/query_engine.py')
    replacement = replacement.replace(pin(original)['sha256'].encode(), pin(engine)['sha256'].encode())
    replacement = replacement.replace(pin(raws[OLD + 'data-manifest.json'])['sha256'].encode(), pin(raws[BASE + 'data-manifest.json'])['sha256'].encode())
    replacement = replacement.replace(b'tool_revision=4', b'tool_revision=5').replace(b'revision 4; file queries only.', b'revision 5; file queries only.')
    assert replacement == wrap
    old_nodes = {n.name: ast.dump(n) for n in ast.parse(old_wrap).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    new_nodes = {n.name: ast.dump(n) for n in ast.parse(wrap).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    assert all(old_nodes[n] == new_nodes[n] for n in ('Parser', 'base_bytes', 'engine'))
    # Static source inspection only: pin before parse/compile, fixed graph, bounded ordinary files.
    text = engine.decode(); wt = wrap.decode()
    assert text.index("require(_hash(raw) == self.expected_manifest") < text.index('manifest = _json(raw)')
    assert "stream.read(MAX_FILE + 1)" in text and "MAX_TOTAL = 32 * 1024 * 1024" in text
    assert text.index('content = _bounded_read(_source_path') < text.index("require(total <= MAX_TOTAL")
    assert wt.index('raw = base_bytes()') < wt.index('exec(compile(raw')
    assert 'module.SourceGraph(ROOT, HERE, DATA_SHA)' in wt and 'result, code = module.query' in wt

    data, old_data = document(BASE + 'data-manifest.json'), document(OLD + 'data-manifest.json')
    index, old_index = document(BASE + 'index.json'), document(OLD + 'index.json')
    assert data['schema'] == 'EU4-WAR-PEACE-LOOKUP-DATA-MANIFEST/1' and data['scope'] == 'offline_selected_evidence_only'
    assert data['game_sha256'] == index['game_sha256'] == GAME and data['version'] == index['version'] == '1.37.5'
    assert data['index'] == pin(raws[BASE + 'index.json'])
    assert len(data['sources']) == 74 and len(old_data['sources']) == 59
    assert all(data['sources'].get(r) == p for r, p in old_data['sources'].items())
    added = sorted(set(data['sources']) - set(old_data['sources']))
    lineage = document(BASE + 'lineage-proof.json')
    assert len(added) == 15 and added == lineage['new_JSON_paths']
    for rel, value in data['sources'].items():
        assert rel.startswith('work/reports/') and rel.endswith('.json') and pin(raws[rel]) == value
    rows = index['entries']; old_rows = {e['id']: e for e in old_index['entries']}
    assert len(rows) == 59 and len(old_rows) == 58
    assert all(next(e for e in rows if e['id'] == k) == v for k, v in old_rows.items())
    fresh = [e for e in rows if e['id'] not in old_rows]
    assert len(fresh) == 1 and fresh[0]['id'] == 'peace.generator_divisor_source' and fresh[0]['rva'] == '0x993570'
    assert [r['id'] for r in rows] == sorted(set(r['id'] for r in rows))
    used = set(); refs = []
    for row in rows:
        assert all(row[f] is False for f in FLAGS[:5])
        assert row['signature']['complete_prototype'] == 'unknown'
        if row['stage'] == 'real_rawbody_postcondition':
            assert row['id'] == 'declare_war.body_destructor' and row['rva'] == '0x500560'
        for ref in row['evidence']:
            assert set(ref) == {'path', 'json_pointer', 'bytes', 'sha256'}
            rel = ref['path']; assert {k: ref[k] for k in ('bytes', 'sha256')} == data['sources'][rel]
            value = pointer(document(rel), ref['json_pointer'])
            refs.append(dict(entry=row['id'], path=rel, pointer=ref['json_pointer'], resolved_type=type(value).__name__))
            used.add(rel)
    assert len(refs) == 264 and used == set(data['sources'])
    new = fresh[0]
    assert new['scope_kind'] == 'known_entry_selected_prefix_with_later_conditional_fragments'
    assert new['whole_function_closed'] is new['independent_fragments_callable'] is False
    assert all(new[f] is False for f in FLAGS)
    assert [(r['window'], r['bytes']) for r in new['owned_ranges']] == [
        (['0x993570', '0x9935a7'], 55), (['0x9935a7', '0x993643'], 156), (['0x993643', '0x993658'], 21)]
    assert [c['entry'] for c in new['later_conditional_context']] == ['0x9935a7', '0x993643']
    assert all(c['independent_function'] is False for c in new['later_conditional_context'])
    assert len(new['evidence']) == 30 and {r['path'] for r in new['evidence']} == set(added)
    for r, contract, manifest in (
        ('r69', 'war-peace-api-20261016-r69-generator-divisor-source/contract.json', 'war-peace-api-20261016-r69-generator-divisor-source/manifest.json'),
        ('r71', 'war-peace-api-20261016-r71-divisor-fallthrough-fragment/actual-contract.json', 'war-peace-api-20261016-r71-divisor-fallthrough-fragment/actual-manifest.json'),
        ('r73', 'war-peace-api-20261016-r73-divisor-nonpositive-fragment/actual-contract.json', 'war-peace-api-20261016-r73-divisor-nonpositive-fragment/actual-manifest.json')):
        f = document('work/reports/war-peace-api-20261016-' + r + '-actual-independent-review/findings.json')
        assert f['sealed'] and f['passed'] and f['blocking_findings'] == []
        assert f['subject_contract'] == pin(raws['work/reports/' + contract])
        assert f['subject_manifest'] == pin(raws['work/reports/' + manifest])
    selected_bytes = len(raws[BASE + 'data-manifest.json']) + len(raws[BASE + 'index.json']) + sum(p['bytes'] for p in data['sources'].values())
    assert selected_bytes == 2521937
    query_dir = 'work/reports/war-peace-api-lookup-v5-first-queries-20261016-r1/'
    queries = document(query_dir + 'receipt.json')
    assert queries['sealed'] and queries['passed'] and queries['error'] is None and len(queries['records']) == 4
    assert queries['first_only_no_retries'] and queries['old_suites_or_old_CLI'] == 0
    assert queries['source_manifest'] == pin(raws[BASE + 'source-manifest.json'])
    assert check_journal(queries['controller_read_journal']) == queries['controller_explicit_bytes'] == 6071308
    catalog_keys = ('id', 'actions', 'title', 'rva', 'kind', 'stage', 'stage_scope', 'summary', 'evidence') + FLAGS[:5]
    expected_catalog = [{key: row[key] for key in catalog_keys} for row in rows]
    outputs = []
    for n, rec in enumerate(queries['records']):
        job_check(rec, 0)
        for stream, ext in (('stdout', 'json'), ('stderr', 'txt')):
            assert rec[stream] == pin(raws[query_dir + f'{n:02d}.{stream}.{ext}'])
        assert rec['stderr']['bytes'] == 0
        q = document(query_dir + f'{n:02d}.stdout.json'); outputs.append(q)
        assert q['status'] == 'ok' and q['tool_revision'] == 5 and q['reused_engine_sha256'] == pin(engine)['sha256']
        assert q['native_calls'] == q['requests_published'] == 0 and all(q[f] is False for f in FLAGS)
        assert q['provenance'] == dict(index_sha256=data['index']['sha256'], manifest_sha256=pin(raws[BASE + 'data-manifest.json'])['sha256'],
            selected_bytes_per_pass=selected_bytes, selected_source_count=74, source_guard_before_and_after=True)
        assert rec['explicit_query_source_bytes'] == 2 * selected_bytes + 3 * len(engine)
    assert [x['operation'] for x in outputs] == ['check', 'catalog', 'lookup', 'search']
    assert outputs[0]['entry_count'] == 59 and outputs[1]['entries'] == expected_catalog and outputs[1]['count'] == 59
    assert outputs[2]['entries'] == [new] and outputs[2]['count'] == 1
    assert outputs[3]['entries'] == [{key: new[key] for key in catalog_keys}] and outputs[3]['count'] == outputs[3]['total_matches'] == 1
    assert sum(r['explicit_query_source_bytes'] for r in queries['records']) == queries['query_source_explicit_bytes'] == 20374492
    assert queries['combined_physical_explicit_bytes'] == 6071308 + 20374492 == 26445800 < 64 * 1024 * 1024

    failed_dir = 'work/reports/war-peace-api-lookup-v5-guard-fixtures-20261016-r1/'
    failed = document(failed_dir + 'receipt.json')
    assert failed['sealed'] and failed['passed'] is False and len(failed['records']) == 1
    job_check(failed['records'][0], 1)
    assert failed['records'][0]['stdout'] == pin(raws[failed_dir + '00.stdout.json']) and not raws[failed_dir + '00.stdout.json']
    assert failed['records'][0]['stderr'] == pin(raws[failed_dir + '00.stderr.txt'])
    stderr = raws[failed_dir + '00.stderr.txt'].decode()
    assert 'line 45, in main' in stderr and 'AssertionError' in stderr
    assert check_journal(failed['controller_read_journal']) == failed['controller_explicit_bytes'] == 2973221
    fixtures = raws[BASE + 'guard_fixtures.py'].decode()
    assert fixtures.splitlines()[44].strip().startswith("assert len(calls)==3 and calls[-1]['path']==badpath")
    assert "reject(root,data,'manifest_sources',calls)" in fixtures and "reject(root,data,'file_limit_exceeded',calls)" in fixtures
    assert 'str(path.relative_to(root))' in fixtures
    delta_dir = 'work/reports/war-peace-api-lookup-v5-aggregate-delta-20261016-r1/'
    aggregate_receipt = document(delta_dir + 'receipt.json'); aggregate = document(delta_dir + '00.stdout.json')
    assert aggregate_receipt['sealed'] and aggregate_receipt['passed'] and len(aggregate_receipt['records']) == 1
    job_check(aggregate_receipt['records'][0], 0)
    assert aggregate_receipt['records'][0]['stdout'] == pin(raws[delta_dir + '00.stdout.json'])
    assert aggregate_receipt['records'][0]['stderr'] == pin(raws[delta_dir + '00.stderr.txt']) and not raws[delta_dir + '00.stderr.txt']
    assert aggregate['passed'] and aggregate['first_aggregate_only'] and aggregate['not_32MiB_OS_read_proof']
    assert aggregate['clean_three_fixture_batch_passed'] is aggregate_receipt['clean_three_fixture_batch_passed'] is False
    assert aggregate['earlier_cases_or_old_suite_rerun'] is False and aggregate['owned_buffer_objects'] == 1
    assert aggregate['physical_OS_body_read_bytes'] == 0 and aggregate['physical_explicit_read_bytes'] == 16583
    virtual_manifest = json.loads(bytes.fromhex(aggregate['input_manifest_raw_hex']))
    assert len(virtual_manifest['sources']) == 17 and len(aggregate['journal']) == 18
    assert all(j['OS_body_read'] is False for j in aggregate['journal'])
    assert aggregate['synthetic_returned_or_charged_bytes'] == sum(j['synthetic_returned_or_charged_bytes'] for j in aggregate['journal']) == 33556847 < 40 * 1024 * 1024
    assert aggregate['refusal'] == 'source_graph_limit_exceeded'
    assert check_journal(aggregate_receipt['controller_read_journal']) == aggregate_receipt['controller_explicit_bytes'] == 6278349
    fixture_upper = 2973221 + 5 * 1024 * 1024 + 6278349 + 16583
    assert aggregate_receipt['cumulative_fixture_physical_upper'] == fixture_upper == 14511033 < 16 * 1024 * 1024
    verification = document(BASE + 'verification.json')
    assert verification['passed'] and verification['author_selfcheck_not_independent'] and verification['source_prepost_equal']
    assert check_journal(verification['read_events']) == verification['metrics']['sealer_explicit_bytes'] == 6536365
    assert verification['metrics']['combined_build_seal_upper'] == 21702246
    assert pub['combined_build_seal_metadata_upper'] == 21702246 + pub['postseal_metadata_read_bytes'] + pub['postseal_allowance'] == 22394731 < LIMIT
    assert pub['source_or_query_logic_changed'] is False
    for rel, p in verification['query_fixture_output_pins'].items():
        assert pin(raws[rel]) == p
    for rel, p in verification['receipt_pins'].items():
        assert pin(raws[rel]) == p
    # Final whole-original graph check. This does not authenticate recursively named dependencies.
    for rel, item in intake['cached'].items():
        read(ROOT / rel, item['pin'], phase='original_final_after')
    read(OUT / 'intake.json', intake_pin, phase='intake_final_after')
    self_pin = pin(read(Path(__file__), phase='reviewer_source'))
    memory()
    resources = dict(intake_source_bytes=3512355, own_explicit_bytes=sum(r['bytes'] for r in reads), manual_inspection_allowance=MANUAL,
        combined_source_upper=3512355 + sum(r['bytes'] for r in reads) + MANUAL, source_limit=LIMIT,
        retained_existing_intake=3512355 + 37504, additional_retained_reserve=1024 * 1024,
        retained_upper=3512355 + 37504 + 1024 * 1024, retained_limit=RETAINED, peak_bytes=peak,
        software_memory_limit=768 * 1024 * 1024, stop_at_or_above_1GiB=True, hard_job_limit_claimed=False,
        complete_OS_loader_IO_claimed=False, shell_children_spawned=0)
    assert resources['combined_source_upper'] < LIMIT and resources['retained_upper'] < RETAINED
    finding = dict(schema='ROOT-LOOKUP-V5-COMPLETE-NONAUTHOR-REVIEW/1', sealed=True, passed=True, blocking_findings=[],
        reviewer_role='root non-author; no v5 build, subject program, query, fixture or native execution',
        subject_source_manifest=pin(raws[BASE + 'source-manifest.json']), subject_author_manifest=pin(raws[BASE + 'author-manifest.json']),
        subject_publication_manifest=pin(raws[BASE + 'publication-manifest.json']), subject_data_manifest=pin(raws[BASE + 'data-manifest.json']),
        subject_index=pin(raws[BASE + 'index.json']), subject_query_engine=pin(engine), subject_wrapper=pin(wrap),
        checks=dict(flat_files=144, original_graph_final_after_equal=True, engine_only_two_bytes_changed=delta,
            engine_AST_only_64_to_96=True, wrapper_only_expected_constants_revision_help_delta=True,
            old58_entries_equal=True, old59_source_pins_equal=True, direct_JSON_sources=74, added_JSON_sources=15,
            JSON_pointer_refs=264, all_sources_used=True, new_entry_count=1, new_fragment_entrypoints=0,
            retained_first_queries=4, query_Jobs_collected=True, fixture_failed_batch_preserved=True,
            prior_expected_refusals_limited_source_plus_traceback_witnesses=2, clean_three_fixture_batch_passed=False,
            first_clean_aggregate_only=1, old_CLI_tests_or_query_reruns=0),
        machine_contract=dict(entry='0x993570', scope=new['scope_kind'], owned_bytes=[55, 156, 21],
            later_context_entries=['0x9935a7', '0x993643'], whole_function_closed=False,
            current_R14_pointer_return_conditional=True, final_D_or_header_or_units_or_ownership_unknown=True,
            historic_NULL_993658_unread_in_this_index=True, later_R75_R77_not_silently_imported=True),
        source_review=dict(full_engine_and_wrapper_read=True, expected_manifest_hash_before_JSON=True,
            fixed_wrapper_engine_bytes_hashed_before_compile=True, same_bytes_compiled=True,
            fixed_graph_only=True, before_after_disk_pins=True, reader_graph_atomic_or_ABA_proof=False),
        precision_notes=[
            'The new query engine has SHA ea030c...; original d4237d... remains frozen. The legacy result field original_engine_source_guard_before_and_after describes guard mechanics, not byte identity.',
            'MAX_TOTAL32MiB is an acceptance bound checked after reading the next bounded file. A refused verification may have read one additional bounded file; no hard32MiB OS IO ceiling is claimed.',
            'The97-source and4MiB+1 fixture witnesses are limited to frozen source order and an actual traceback reachingline45. Their raw per-case journal was not emitted; the batch still failed.',
            'The clean aggregate is a separate first execution with one reused2MiB buffer and virtual returned-byte charging, not32MiB of OS disk reads.',
            'Full owner reviews are directly pinned witnesses. Their recursively named dependencies are not reread or fully re-audited here.',
            'Manual review included a nonexistent tools/intake path and an exploratory empty-JSON parse failure. Both tool failures are retained in conversation, changed no subjects, and are covered by the2MiB inspection allowance.'
        ], author_resources=dict(query_physical=26445800, fixture_physical_upper=fixture_upper,
            fixture_synthetic_separate=33556847, build_seal_metadata_upper=22394731),
        independent_resources=resources, reviewer_source=self_pin, authority={f: False for f in FLAGS},
        operations=dict(PE=0, Capstone=0, engine_body_from_binary=0, game_queries=0, native_calls=0, author_program_executions=0,
            queries=0, tests=0, retries=0, source_closure_recursive_authentication=False), next_scope_auto_authorized=False)
    pointer_pin = write('pointer-replay.json', dict(sealed=True, passed=True, refs=refs))
    fp = write('findings.json', finding)
    mp = write('manifest.json', dict(schema='ROOT-LOOKUP-V5-REVIEW-MANIFEST/1', sealed=True,
        findings=fp, source_pins={r: v['pin'] for r, v in intake['cached'].items()}, intake=intake_pin,
        local_pins={'pointer-replay.json': pointer_pin, 'reviewer_source': self_pin}, read_journal=reads,
        source_scope='144 selected flat files only; no recursive expansion', authority={f: False for f in FLAGS}))
    print(json.dumps(dict(passed=True, findings=fp, manifest=mp, resources=resources), ensure_ascii=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        value = dict(sealed=True, passed=False, error=dict(type=type(exc).__name__, message=str(exc)),
            traceback=traceback.format_exc(), read_journal=reads, subject_operations=0)
        write('reviewer-failure-r1.json', value)
        raise
