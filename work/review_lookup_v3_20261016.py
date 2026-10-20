"""Non-author, bounded file/AST audit; never imports or runs a candidate."""
from pathlib import Path
import ast
import ctypes
import hashlib
import json

ROOT = Path(__file__).resolve().parent.parent
SUB = 'work/candidates/war-peace-api-lookup-1375-v3'
OUT = ROOT / 'work/reports/war-peace-api-lookup-v3-independent-review-20261016-r1'
GAME = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
FLAGS = ('callable', 'native_ready', 'sender_authorized', 'gameplay_effect_verified',
         'process_authenticated', 'selected_effect_verified', 'world_lease',
         'atomic_snapshot', 'authorizes_retry')
EXPECTED_SUBJECT = {'bytes': 16861, 'sha256': '12eb3de0825c7621dd62937eecc9b7dfbe5c150ac70d841fa0122836c4af429c'}
READS = []
TOTAL = 0
CACHE = {}


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read(path, expected=None, phase='before'):
    global TOTAL
    p = (ROOT / path).resolve()
    assert p.is_relative_to(ROOT) and 0 <= p.stat().st_size <= 4 * 1024 * 1024
    with p.open('rb') as f:
        raw = f.read(4 * 1024 * 1024 + 1)
    assert len(raw) <= 4 * 1024 * 1024
    TOTAL += len(raw)
    assert TOTAL + 1024 * 1024 <= 32 * 1024 * 1024
    got = pin(raw)
    assert expected is None or got == expected, ('pin_changed', path)
    READS.append(dict(path=path, phase=phase, **got))
    if phase == 'before':
        CACHE[path] = raw
    return raw


def obj(path):
    return json.loads(CACHE[path])


def canon(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()


def pointer(value, path):
    assert path == '' or path.startswith('/')
    for part in path.split('/')[1:]:
        part = part.replace('~1', '/').replace('~0', '~')
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def write(path, value):
    raw = (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + '\n').encode()
    with path.open('xb') as f:
        f.write(raw)
    return pin(raw)


def main():
    assert not OUT.exists(), 'one_review_only'
    owner = json.loads(read(SUB + '/manifest.json', EXPECTED_SUBJECT))
    assert owner['sealed'] is True and owner['pin_count'] == 85 and len(owner['files']) == 85
    assert owner['independent_source_review_passed'] is False
    assert owner['game_sha256'] == GAME
    for path, expected in owner['files'].items():
        read(path, expected)
    fc = json.loads(read(SUB + '/filecheck.json', {'bytes': 18142, 'sha256': '8660441220784558e7ee2c73f920f532722cf8a36d61cfe1f9f80efc334fff16'}))
    assert fc['passed'] is True and fc['pins_checked'] == 85 and fc['manifest'] == EXPECTED_SUBJECT
    assert fc['query_or_test_reexecution'] is False and fc['PE_decoder_game_native_requests'] == 0
    assert fc['known_file_analysis_explicit_bytes_through_check'] <= fc['analysis_budget'] == 33554432
    sm = obj(SUB + '/source-manifest.json')
    assert sm['sealed'] is True and len(sm['files']) == sm['pin_count'] == 65
    assert all(owner['files'].get(k) == v for k, v in sm['files'].items())
    assert owner['source_manifest'] == pin(CACHE[SUB + '/source-manifest.json'])
    data = obj(SUB + '/data-manifest.json')
    index = obj(SUB + '/index.json')
    olddir = 'work/candidates/war-peace-api-lookup-1375-v2'
    old = obj(olddir + '/index.json')
    olddata = obj(olddir + '/data-manifest.json')
    lineage = obj(SUB + '/lineage-proof.json')
    assert data['game_sha256'] == index['game_sha256'] == GAME
    assert data['index'] == pin(CACHE[SUB + '/index.json'])
    assert len(data['sources']) == 44 and len(olddata['sources']) == 26
    assert all(owner['files'][k] == v for k, v in data['sources'].items())
    assert all(data['sources'][k] == v for k, v in olddata['sources'].items())
    assert sum(v['bytes'] for v in data['sources'].values()) == 1943399
    rows = {e['id']: e for e in index['entries']}
    oldrows = {e['id']: e for e in old['entries']}
    assert len(rows) == len(index['entries']) == 54 and len(oldrows) == 50
    assert list(rows) == sorted(rows) and index['family_aliases'] == old['family_aliases']
    assert all(rows[k] == v for k, v in oldrows.items())
    assert all(a['data_equal'] is True and a['canonical_row_sha256'] == hashlib.sha256(canon(oldrows[a['id']])).hexdigest()
               for a in lineage['original50']) and len(lineage['original50']) == 50
    extra = {k: v for k, v in rows.items() if k not in oldrows}
    assert {v['rva'] for v in extra.values()} == {'0x9b46a0', '0x3383b0', '0x771be0', '0x9844d0'}
    assert len({e['rva'] for e in index['entries']}) == 54
    assert lineage['R63_included'] is False
    assert set(data['sources']) - set(olddata['sources']) == set(lineage['new_pins'])
    assert len(lineage['new_pins']) == 18
    assert all(data['sources'][k] == v for k, v in lineage['new_pins'].items())
    used = set()
    aliases = {}
    ref_count = 0
    for e in index['entries']:
        for flag in FLAGS[:5]:
            assert e[flag] is False
        for alias in [e['id']] + e['aliases']:
            key = alias.casefold()
            assert key not in aliases or aliases[key] == e['id']
            aliases[key] = e['id']
        for ref in e['evidence']:
            assert set(ref) == {'path', 'json_pointer', 'bytes', 'sha256'}
            assert {k: ref[k] for k in ('bytes', 'sha256')} == data['sources'][ref['path']]
            pointer(obj(ref['path']), ref['json_pointer'])
            used.add(ref['path'])
            ref_count += 1
    assert used == set(data['sources'])
    for e in extra.values():
        assert all(e[k] is False for k in FLAGS)
        assert e['kind'] == 'function' and e['stage'] == 'static'
        assert e['signature']['complete_prototype'] == 'unknown'
        assert e['independent_review_status'] == 'full_independent_file_audit_passed_for_each_retained_scope'
        assert e['unresolved']
    selected = rows['shared.pending_kind_counter_path']
    assert selected['scope_kind'] == 'conditional_path'
    assert selected['conditional_inputs'] == {'EDX': 5, 'R8D': '0xffffffff'}
    assert selected['owned_code_ranges'] == [['0x771be0', '0x771c06'], ['0x771c06', '0x771cbd'], ['0x771cc7', '0x771cf6']]
    assert sum(int(b, 16) - int(a, 16) for a, b in selected['owned_code_ranges']) == selected['owned_code_unique_bytes'] == 268
    assert selected['unselected_code_gaps'] == [['0x771cbd', '0x771cc7']]
    assert selected['independent_fragment_callable'] is selected['whole_function_closed'] is False
    expected_subjects = {
        'r57': (15393, '844e3cb62f19047878a0849844dcd13c14c0413da9cbb18459af1236b90b2150'),
        'r58': (13949, 'f989fde03fae380c52ff0694bdb009116cec96877ace3c6f5f4e44326bc4edcf'),
        'r59': (14507, '633a4ba43344f5b4041470189e93b2caafd01271b795b6516d1793f0d173beaa'),
        'r60': (13753, 'bb537f3b7e537d59fde9cde59e0a941f3c9bafed7b9ed59c4795cd9f1859fa64'),
        'r61': (15099, '3e92d2244c8c5a532e86c8f8bfd1f2147391beb0302e0c16f5d4e5cd10d9cd6c'),
        'r62': (14300, 'd3516fdbc60b2c66115b9a0aa907daace7e5a8adac0c5dbd4c53f0840eba6db4'),
    }
    for scope, (size, sha) in expected_subjects.items():
        path = next(k for k in data['sources'] if f'-{scope}-independent-review/findings.json' in k)
        f = obj(path)
        assert f['sealed'] is f['passed'] is True and f['blocking_findings'] == []
        assert f['subject_manifest'] == {'bytes': size, 'sha256': sha}
    # Exact source normalization: only data pin, revision/help and constant-false metadata differ.
    before = CACHE[olddir + '/war_peace_lookup.py'].decode('utf-8')
    after = CACHE[SUB + '/war_peace_lookup.py'].decode('utf-8')
    normalized = before.replace(olddata and "DATA_SHA = '6f4cb91a1798df84a3ff10b5f2f7244a536a30d2995124f23fe68bb2451cf874'",
                                "DATA_SHA = '8f849152e150b3f3918b10bb427cfa39457e4774db83c4dac42f82da04c3c212'")
    normalized = normalized.replace("'gameplay_effect_verified', 'process_authenticated')", "'gameplay_effect_verified', 'process_authenticated',\n         'selected_effect_verified', 'world_lease', 'atomic_snapshot', 'authorizes_retry')")
    normalized = normalized.replace('tool_revision=2', 'tool_revision=3').replace('revision 2;', 'revision 3;')
    normalized = normalized.replace('original_engine_source_guard_before_and_after=True)',
        'original_engine_source_guard_before_and_after=True,\n                      selected_effect_verified=False, world_lease=False,\n                      atomic_snapshot=False, authorizes_retry=False)')
    assert ast.dump(ast.parse(normalized), include_attributes=False) == ast.dump(ast.parse(after), include_attributes=False)
    modules = {v: ast.parse(CACHE[v]) for v in [olddir + '/war_peace_lookup.py', SUB + '/war_peace_lookup.py']}
    for name in ('Parser', 'base_bytes', 'engine'):
        nodes = [next(n for n in modules[v].body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name) for v in modules]
        assert ast.dump(nodes[0], include_attributes=False) == ast.dump(nodes[1], include_attributes=False)
    # Parse all delivered Python, without import/exec/compile or transitive dependency expansion.
    parsed_python = []
    for path in owner['files']:
        if path.endswith('.py'):
            ast.parse(CACHE[path])
            parsed_python.append(path)
    rd = 'work/reports/war-peace-api-lookup-v3-delta-20261016-r1'
    receipt = obj(rd + '/receipt.json')
    assert receipt['passed'] is receipt['sealed'] is receipt['first_queries_only'] is True
    assert receipt['command_count'] == len(receipt['records']) == 7 and receipt['error'] is None
    assert receipt['PE_decoder_game_native_requests_install_publish'] == receipt['old_tests_or_old_CLI_main'] == 0
    assert receipt['all_jobs_and_direct_children_collected'] is True
    assert owner['delta_receipt'] == pin(CACHE[rd + '/receipt.json'])
    assert receipt['source_manifest'] == owner['source_manifest']
    perpass = sum(v['bytes'] for v in data['sources'].values()) + data['index']['bytes'] + len(CACHE[SUB + '/data-manifest.json'])
    assert perpass == 2090193
    expected_ops = ['check', 'catalog', 'lookup', 'lookup', 'lookup', 'lookup', 'search']
    expected_ids = [[], list(rows), ['peace.gold_component_helper'], ['shared.scalar_add_clamp'], ['shared.pending_kind_counter_path'], ['peace.generated_record_body'], ['shared.pending_kind_counter_path']]
    for n, rec in enumerate(receipt['records']):
        stdout = CACHE[rd + f'/{n:02}.stdout.json']
        stderr = CACHE[rd + f'/{n:02}.stderr.txt']
        assert pin(stdout) == rec['stdout'] and pin(stderr) == rec['stderr'] and stderr == b''
        answer = json.loads(stdout)
        assert rec['operation'] == answer['operation'] == expected_ops[n]
        assert answer['status'] == rec['status'] == 'ok'
        assert answer['tool_revision'] == 3 and all(answer[k] is False for k in FLAGS)
        assert answer['native_calls'] == answer['requests_published'] == 0
        assert answer['original_engine_source_guard_before_and_after'] is True
        assert answer['provenance']['source_guard_before_and_after'] is True
        assert answer['provenance']['selected_source_count'] == 44
        assert rec['selected_bytes_per_pass'] == answer['provenance']['selected_bytes_per_pass'] == perpass
        assert rec['explicit_query_source_bytes'] == perpass * 2 + 16583 * 3
        ids = [e['id'] for e in answer.get('entries', [])]
        assert ids == rec['ids'] == expected_ids[n]
        if expected_ops[n] == 'lookup':
            assert answer['entries'] == [rows[k] for k in ids]
        if n == 0:
            assert answer['entry_count'] == 54 and answer['stage_counts'] == {'static': 53, 'real_rawbody_postcondition': 1}
        job = rec['job']
        assert job['exit_code'] == 0 and job['error'] is None and job['direct_child_collected'] is True
        assert job['job_active_processes_final'] == 0 and job['job_total_processes'] == 2
        assert job['completed_command_descendants_terminated'] is False
        assert job['peak_job_commit'] < job['memory_limit'] == 805306368
    assert sum(r['explicit_query_source_bytes'] for r in receipt['records']) == receipt['query_source_explicit_bytes'] == 29610945
    assert sum(r['bytes'] for r in receipt['controller_read_journal']) == receipt['controller_explicit_bytes'] == 6284362
    assert receipt['combined_delta_explicit_bytes'] == receipt['query_source_explicit_bytes'] + receipt['controller_explicit_bytes'] == 35895307
    assert receipt['combined_delta_explicit_bytes'] < receipt['delta_budget'] == 67108864
    assert fc['delta_explicit_bytes_separate'] == receipt['combined_delta_explicit_bytes']
    for path, expected in owner['files'].items():
        read(path, expected, 'after')
    read(SUB + '/manifest.json', EXPECTED_SUBJECT, 'after')
    read(SUB + '/filecheck.json', pin(CACHE[SUB + '/filecheck.json']), 'after')
    OUT.mkdir()
    evidence = write(OUT / 'verification.json', dict(schema='EU4-LOOKUP-V3-FILE-AST-VERIFICATION/1', sealed=True,
        source_manifest65_subset=True, final_manifest85_unchanged=True, flat_JSON_sources44=True,
        old50_data_equal=True, four_new_only=True, evidence_refs_resolved=ref_count,
        six_prior_full_reviews_binding_checked=True, authority_escalation=False,
        CLI_AST_exact_allowed_normalization=True, parsed_python_without_execution=parsed_python,
        first_seven_receipts_replayed=True, query_source_bytes=29610945, controller_bytes=6284362,
        author_analysis_bytes=fc['known_file_analysis_explicit_bytes_through_check'],
        read_journal=READS, known_file_reads=TOTAL, prior_manual_inspection_allowance=1048576,
        total_bounded_upper=TOTAL + 1048576, max_total=33554432,
        no_PE_decoder_process_or_CLI_test_execution=True))
    findings = write(OUT / 'findings.json', dict(schema='EU4-LOOKUP-V3-INDEPENDENT-REVIEW/1', sealed=True,
        passed=True, blocking_findings=[], subject_path=SUB + '/manifest.json', subject_manifest=EXPECTED_SUBJECT,
        subject_cli_pin=pin(CACHE[SUB + '/war_peace_lookup.py']), verification_pin=evidence,
        stage='SOURCE-READY_FILE_ONLY_LOOKUP', authority={k: False for k in FLAGS},
        result='54 entries / 44 flat retained JSON sources; original50 unchanged; 4 new fixed-PE partial machine contracts.',
        limits=[
            'Only delivered 85 files plus filecheck were opened. No transitive PE/decoder dependency authentication or new raw-body reanalysis.',
            'Six retained independent reviews remain the authority for new machine contracts; this review validates their exact selected pins and index boundaries.',
            '771be0 is a conditional EDX5/R8Dffffffff path in three ranges, not a complete function or independently callable fragments.',
            'FFFFFFFF writes zero before error call; no normal wrap, uniqueness, retry or bridge request-ID binding.',
            '3383b0 wraps ADD32 before signed clamp; no returned balance, business unit or settlement success.',
            'R63 is outside this frozen index. New helper knowledge does not rewrite older retained rows.',
            'First seven query receipts were checked as files, without rerunning CLI or tests.',
            'Counters are explicit listed-source I/O and author resource witnesses, not all interpreter/OS loader reads.',
            'No current process authentication, game write, original-request effect or war/peace sender authorization.'
        ], operations=dict(PE=0, decoder=0, game=0, native=0, query_or_test_rerun=0)))
    own = read(str(Path(__file__).relative_to(ROOT)).replace('\\', '/'), phase='seal_script')
    manifest = write(OUT / 'manifest.json', dict(schema='EU4-LOOKUP-V3-REVIEW-MANIFEST/1', sealed=True, passed=True,
        subject_manifest=EXPECTED_SUBJECT, files={
            str((OUT / 'findings.json').relative_to(ROOT)).replace('\\', '/'): findings,
            str((OUT / 'verification.json').relative_to(ROOT)).replace('\\', '/'): evidence,
            str(Path(__file__).relative_to(ROOT)).replace('\\', '/'): pin(own),
        }, subject_files=owner['files']))
    status = ROOT / SUB / 'REVIEW_STATUS.md'
    with status.open('x', encoding='utf-8', newline='\n') as f:
        f.write('# Review status (2026-10-16)\n\nSOURCE-READY for file-only research lookup: 54 entries, 44 retained JSON sources.\n\n'
                'Independent source, AST delta, 85 pins and the first seven query receipts passed. The frozen author manifest and STATUS.md remain unchanged.\n\n'
                'Review: `work/reports/war-peace-api-lookup-v3-independent-review-20261016-r1/findings.json`.\n\n'
                'This index does not authorize a native call, game write, retry, or current-effect claim. R63 is outside this frozen revision.\n')
    print(json.dumps(dict(passed=True, files=85, findings=findings, manifest=manifest,
                          explicit_reads=TOTAL, upper=TOTAL + 1048576), ensure_ascii=True))


if __name__ == '__main__':
    main()
