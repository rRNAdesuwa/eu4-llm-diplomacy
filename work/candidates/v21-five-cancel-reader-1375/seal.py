"""CREATE_NEW author seal from an already completed isolated validation."""
import json
import prepare as p


def main():
    before = p.inputs()
    index = json.loads(p.read(p.HERE / 'source-index.json'))
    assert index == p.own()
    evidence = p.evidence()
    assert p.read(p.HERE / 'evidence.json') == p.encoded(evidence)
    path = p.HERE / 'validation-final/validation.json'
    validation = json.loads(p.read(path))
    assert validation['passed'] is True and validation['inputs_unchanged'] is True
    assert validation['build']['exit_code'] == 0 and validation['build']['job_active_processes_final'] == 0
    assert validation['build']['all_children_collected'] is True
    assert 'groups=29 native_calls=0 submitted=0 OS_reader=false ABA_excluded=false' in validation['test_stdout']
    assert 'budget_groups=6 exact_limits=true rejected_before_source_read=true shared_budget=true native_calls=0' in validation['budget_stdout']
    for name, expected in validation['inputs_before'].items():
        assert p.desc(p.ROOT / name) == expected, name
    for name, expected in validation['artifacts'].items():
        assert p.desc(path.parent / name) == expected, name
    limits = {'runtime_verified': False, 'native_ready': False, 'production_ready': False,
              'native_called': False, 'native_adapter_implemented': False, 'sender_implemented': False,
              'public_backend_registered': False, 'OS_game_attestation_verified': False,
              'game_process_accessed': False, 'executable_read_this_task': False, 'DLL_built': False,
              'strict_SP_verified': False, 'world_epoch_verified': False, 'snapshot_ABA_excluded': False,
              'lifetime_lock_verified': False, 'effect_verified': False, 'cancel_recall_verified': False,
              'new_decode_bytes': 0, 'old_or_formal_files_modified': False,
              'all_shells_collected': True, 'remaining_sessions': []}
    report = {'schema_version': 1, 'purpose': 'five_negative_private_typed_graph_reader_1375',
              'status': 'sealed_common_author_pending_independent_review',
              'authors': ['root (initial reader draft)', 'native_inventory (bounded closure, tests, seal)'],
              'passed_author_validation': True, 'independent_review_required': True,
              'profiles': evidence['profiles'], 'spy_network': 'explicitly_unsupported_separate_binder_required',
              'proof_scope': 'concrete C++ private reader plus sealed R2 fake engine; not OS/raw runtime proof or engine ABI authorization',
              'test_groups': 29, 'budget_groups': 6, 'build': validation['build'],
              'inputs': before, 'input_pins_sha256': p.desc(p.HERE / 'input-pins.json')['sha256'],
              'source_index_sha256': p.desc(p.HERE / 'source-index.json')['sha256'],
              'evidence_sha256': p.desc(p.HERE / 'evidence.json')['sha256'],
              'validation_sha256': p.desc(path)['sha256'], 'limits': limits,
              'reader_source_sha256': p.desc(p.HERE / 'cancel_reader.cpp')['sha256'],
              'negative_cases': ['wrong header before derived read', 'reverse directional relation / symmetric marriage',
                 'duplicate index slot/object or asymmetric relation pointer', 'subtype/overlord/String32 mismatch',
                 'manager/entry/mission marker and kind mismatch', 'full generation/backreference/ID/token mismatch',
                 'bad state and malformed nonselected mission', 'changed holder end/capacity/roots/two-pass transcript',
                 'read failure/exception preserving but invalidating prior output', 'unsupported Spy and over-limit capacities',
                 'exact shared call/byte/single-read/address budget refusal before source callback'],
              'known_limits': ['same-value ABA counterexample deliberately passes; no generation/lifetime lock claimed',
                 'PairStamp and injected read source are private assumptions, not authenticated OS credentials',
                 'module bytes/EXE identity are not checked by this reader; external future adapter must pin loaded type/code identity',
                 'only current selected actor/target objects resolved; other mission target identity is shape-only',
                 'normal/native legality, resource, truce, cooldown, acceptance and actual cancellation are unobserved',
                 '256-entry cap and ordinary-handle filters may reject other otherwise valid worlds; refusal is unsupported, not absence'],
              'development': ['Root original sources preserved under preimages/',
                 'validation-development-1 retained /WX narrow-int test failure, no native reader compiler error',
                 'validation-development-2 passed 28 groups before added ordinary handle/budget coverage',
                 'final contains 29 graph/integration groups plus 6 actual internal budget groups; no repeats after final pass'],
              'exploration': {'new_decode_attempts': [], 'new_decode_bytes': 0,
                 'reused_instruction_records': evidence['reused_instruction_records'],
                 'reused_instruction_bytes_including_overlap': evidence['reused_instruction_bytes_including_overlap'],
                 'file_search_misses': ['prior rg nonexistent work/probe_diplomacy_effects_1375.py (exit2), corrected to probe_pair_effects_1375.py',
                                       'finite rg with no matching symbol (exit1); no scan left running']}}
    report_hash = p.seal(p.HERE / 'report.json', report)
    review_hash = p.seal(p.HERE / 'review.json', {'schema_version': 1, 'passed_author_validation': True,
        'independent_review_required': True, 'report_sha256': report_hash,
        'source_index_sha256': report['source_index_sha256'], 'validation_sha256': report['validation_sha256'],
        'evidence_sha256': report['evidence_sha256'], 'reader_source_sha256': report['reader_source_sha256'],
        'common_authors': report['authors'], 'limits': limits})
    assert before == p.inputs() and index == p.own()
    print(json.dumps({'review_sha256': review_hash, 'report_sha256': report_hash,
                      'source_index_sha256': report['source_index_sha256'],
                      'validation_sha256': report['validation_sha256'], 'passed_author_validation': True}))


if __name__ == '__main__':
    main()
