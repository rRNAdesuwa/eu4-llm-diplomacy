"""Generate isolated, unbuilt v12 contract-review sources from frozen v11."""
from __future__ import annotations
import argparse
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = ROOT / 'work/runtime/native1375-v11/build.json'
MANIFEST_SHA = '747f3f326dbe3da5002bf4edacf00c8bf3a450fd4a3347abd77590127b1856cc'
QUEUE_REPORT = 'work/reports/native-coalition-queue-1375.json'
QUEUE_SHA = 'b36c788c3eeb589abaa208df83cb3f97bf3697023188149588b41bb60dde5b65'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Missing/ambiguous source anchor: ' + old[:100])
    return text.replace(old, new)


def generate(check=False, materialize=False):
    raw = MANIFEST.read_bytes()
    assert sha(raw) == MANIFEST_SHA
    manifest = json.loads(raw)
    assert sha((MANIFEST.parent / 'eu4_pair_lab_v11_1375.dll').read_bytes()).upper() == manifest['dll_sha256']
    assert all(sha((ROOT / name).read_bytes()).upper() == value for name, value in manifest['source_sha256'].items())
    assert sha((ROOT / QUEUE_REPORT).read_bytes()) == QUEUE_SHA
    fragment = (HERE / 'contract-diagnostic.inc').read_text(encoding='utf-8')
    outputs, diffs, native = {}, [], {}
    changed = []
    for source_name in manifest['source_sha256']:
        filename = Path(source_name).name
        destination = source_name.replace('v11', 'v12')
        original = (ROOT / source_name).read_bytes().decode('utf-8')
        text = original
        if filename == 'pair-engine-1375.cpp':
            begin, end = text.index('bool factory_fields('), text.index('\nvoid initialize(')
            chunk = text[begin:end]
            chunk = once(chunk, 'read_at<std::uint32_t>(object + 0x34) == 0',
                         'read_at<std::uint32_t>(object + 0x34) == (action.token == 0x2de0 ? 2U : 0U)')
            text = text[:begin] + chunk + text[end:]
            text = once(text, 'write_owned(object, 0x34, static_cast<std::uint32_t>(0));',
                        'write_owned(object, 0x34, static_cast<std::uint32_t>(action.token == 0x2de0 ? 2U : 0U));')
            text = once(text, 'read_at<std::uint32_t>(object + 0x34) == 0',
                        'read_at<std::uint32_t>(object + 0x34) == (action.token == 0x2de0 ? 2U : 0U)')
        elif filename in ('pair-preview-v6-1375.cpp', 'pair-command-v6-1375.cpp'):
            text = once(text, 'write_owned(object, 0x34, static_cast<std::uint32_t>(0));',
                        'write_owned(object, 0x34, static_cast<std::uint32_t>(action.token == 0x2de0 ? 2U : 0U));')
            if filename == 'pair-command-v6-1375.cpp':
                text = once(text, 'read_at<std::uint32_t>(object + 0x34) == 0',
                            'read_at<std::uint32_t>(object + 0x34) == (action.token == 0x2de0 ? 2U : 0U)')
            else:
                text = once(text, '        && read_at<std::int32_t>(object + 0x30) == -1\n',
                            '        && read_at<std::int32_t>(object + 0x30) == -1\n'
                            '        && read_at<std::uint32_t>(object + 0x34) == (action.token == 0x2de0 ? 2U : 0U)\n')
        elif filename == 'pair-probe-v6-1375.cpp':
            unused_begin = text.index('bool v11_fixed_fields(')
            unused_end = text.index('void v11_initialize_fixed(', unused_begin)
            text = text[:unused_begin] + text[unused_end:]
            begin, end = text.index('bool default_fields_match('), text.index('\nbool one_lifecycle(')
            text = text[:begin] + fragment + text[end:]
            text = once(text, '    DWORD exception = 0;\n    __try {',
                        '    DWORD exception = 0;\n    ContractDiagnostic factory_diagnostic{}, clone_diagnostic{}, retained_diagnostic{};\n    __try {')
            text = once(text, 'default_fields_match(reinterpret_cast<std::uintptr_t>(original), action, base);',
                        'default_fields_match(reinterpret_cast<std::uintptr_t>(original), action, base, factory_diagnostic);')
            text = once(text, 'default_fields_match(reinterpret_cast<std::uintptr_t>(copy), action, base, true)',
                        'default_fields_match(reinterpret_cast<std::uintptr_t>(copy), action, base, clone_diagnostic, true)')
            text = once(text, 'default_fields_match(reinterpret_cast<std::uintptr_t>(original), action, base, true)',
                        'default_fields_match(reinterpret_cast<std::uintptr_t>(original), action, base, retained_diagnostic, true)')
            text = once(text, '    char line[1024]{};\n    std::snprintf(line, sizeof(line),',
                        '    char factory_state[16]{}, factory_mask[16]{}, clone_state[16]{}, clone_mask[16]{}, retained_state[16]{}, retained_mask[16]{};\n'
                        '    format_diagnostic(factory_diagnostic, factory_state, factory_mask);\n'
                        '    format_diagnostic(clone_diagnostic, clone_state, clone_mask);\n'
                        '    format_diagnostic(retained_diagnostic, retained_state, retained_mask);\n'
                        '    char line[4096]{};\n    const int count = std::snprintf(line, sizeof(line),')
            text = once(text, r'\"fixed_insult_index\":%d}",',
                        r'\"fixed_insult_index\":%d,' + '"\n'
                        r'                  "\"factory_contract_checked\":%s,\"factory_state\":%s,\"factory_contract_failure_mask\":%s,' + '"\n'
                        r'                  "\"clone_contract_checked\":%s,\"clone_state\":%s,\"clone_contract_failure_mask\":%s,' + '"\n'
                        r'                  "\"retained_original_contract_checked\":%s,\"retained_original_state\":%s,\"retained_original_contract_failure_mask\":%s}",')
            text = once(text, 'action.token == 0x2947 ? -1 : 0);',
                        'action.token == 0x2947 ? -1 : 0,\n'
                        '                  factory_diagnostic.completed ? "true" : "false", factory_state, factory_mask,\n'
                        '                  clone_diagnostic.completed ? "true" : "false", clone_state, clone_mask,\n'
                        '                  retained_diagnostic.completed ? "true" : "false", retained_state, retained_mask);\n'
                        '    if (count <= 0 || static_cast<std::size_t>(count) >= sizeof(line)) return false;')
        text = text.replace('v11', 'v12')
        baseline = original.replace('v11', 'v12')
        raw = text.encode('utf-8')
        outputs['generated/' + Path(destination).name] = raw
        native[destination] = raw
        if text != baseline:
            changed.append(destination)
        diffs.extend(difflib.unified_diff(baseline.splitlines(True), text.splitlines(True),
                     fromfile=destination + '.version-only-baseline', tofile=destination))
    outputs['contract.diff'] = ''.join(diffs).encode()
    report = {'purpose': 'v12_factory_contract_review_only', 'frozen_v11_manifest_sha256': MANIFEST_SHA,
              'normal_coalition_queue_report': QUEUE_REPORT, 'normal_coalition_queue_sha256': QUEUE_SHA,
              'generated_sha256': {name: sha(raw) for name, raw in outputs.items()},
              'native_source_sha256': {name: sha(raw) for name, raw in native.items()},
              'meaningful_changed_sources': changed,
              'native_source_count': len(native),
              'factory_contract_state': {'form_coalition': 2, 'other_19_families': 0},
              'initialized_request_state_changed': True,
              'initialized_coalition_state_status': 'Exact token2de0 initializes state2, as normal AI construction12c54f and wrapper/owned-command queue129b60; all other19 families remain0.',
              'diagnostic_prefixes': ['factory', 'clone', 'retained_original'],
              'failure_mask_bits': {str(i): name for i, name in enumerate((
                  'null_or_sentinel_pointer', 'vtable', 'marker08', 'actor10', 'original_actor18', 'target20',
                  'date28', 'date2c', 'envoy30', 'state34', 'value38_flag39', 'field3c', 'insult_index40',
                  'gift_amount40', 'transfer_amount40', 'transfer_flag44', 'subsidy_amount40', 'subsidy_years44',
                  'marriage_string_first40', 'marriage_length50', 'marriage_capacity58', 'marriage_flag60'))},
              'diagnostic_completed': 'checked true means all applicable reads completed or pointer/identity failed early; mask zero is required for success',
              'unobserved_diagnostic': 'mask null until completed; state null until read; absent clone has checked false and both null',
              'native_built': False, 'process_access': False, 'runtime_verified': False}
    outputs['review.json'] = (json.dumps(report, indent=2) + '\n').encode()
    if materialize:
        assert not check
        output = ROOT / 'work/runtime/native1375-v12'
        assert not (output / 'eu4_pair_lab_v12_1375.dll').exists()
        assert not (output / 'build.json').exists()
        assert not output.exists() or not any(output.glob('session-*'))
        # Validate the entire target set before the first write. Never replace a
        # pre-existing native file with different bytes, even before a build.
        for name, raw in native.items():
            path = ROOT / name
            assert not path.exists() or path.read_bytes() == raw, 'Existing v12 native source differs: ' + name
    for name, raw in outputs.items():
        path = HERE / name
        if check:
            assert path.read_bytes() == raw, name
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    if materialize:
        for name, raw in native.items():
            path = ROOT / name
            if path.exists():
                assert path.read_bytes() == raw
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(raw)
    return {'native_sources': len(native), 'changed_native_sources': len(changed),
            'review_sha256': sha(outputs['review.json']), 'materialized': materialize, 'built': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--materialize', action='store_true', help='Copy reviewed candidate into new native/v12; never builds or accesses a process')
    args = parser.parse_args()
    print(json.dumps(generate(args.check, args.materialize)))
