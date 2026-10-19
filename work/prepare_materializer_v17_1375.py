"""CreateNew fixed v17 root materializer from frozen v16; no build/game access."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'work/materialize_build_v16_1375.py'
NEW = ROOT / 'work/materialize_build_v17_1375.py'
OLD_SHA = '08230f8d01100ac51089047413840daa9275ee97498c04a768027f1dd2ad4995'
PINS = {
    'work/candidates/v17-acceptance-pin-review/review.json': 'ad9d5d2c368e8358cf5e3e6b156f5ccb2b399a7c1c33f989a9e79db0e6d7fd7a',
    'work/candidates/v17-acceptance-pin-review/candidate-index.json': '43552adb80412ddbf21e1dfc608c3aca44f5cb178229a40a5fc0714282016a3a',
    'work/candidates/v17-acceptance-pin-review/native-source-review.json': '120bdc29f85634226aefcf07e3cc4914f7201e169a6edcfefaeb296344fabc7b',
    'work/review-results/v17-candidate-root-20261008a/validation.json': 'dbd8515495bd8ab37f41d026a1843fa18c9ff6f564c890c721592675303c1455',
    'work/review-results/v17-python-external-api-20261008a/review.json': '36dacbd380b54f61efa8ca517f6e26438d51b02d303c3ccf95065fc3cf76eb15',
    'work/review-results/v17-python-external-api-20261008a/validation-final.json': '98202d3e7fbb789a90b5072f774a088585c3db3167b4d5717b7bc7f89bdb39da',
    'work/review-results/v17-native-object-compile-native-inventory-20261008a/review-r2.json': 'c041ce073991df9df0012c04dc79653ffa59b0edf0901de5e8bfbb95cd14172d',
    'work/review-results/v17-native-object-compile-native-inventory-20261008a/validation.json': '16c6298bb3a46dcac39697c87182e24c89dd6f492c56903f4d7d4699aa5dedf7',
    'work/review-results/v17-native-object-compile-native-inventory-20261008a/source-and-pin-review.json': '17926e5a591835ac1eecee3b115d56ab696e7bbd877c52e43cdf20c7eb0cd9fe',
}

INDEPENDENT = '''    independent = data['work/review-results/v17-python-external-api-20261008a/review.json']
    python_validation = data['work/review-results/v17-python-external-api-20261008a/validation-final.json']
    validation = data['work/review-results/v17-candidate-root-20261008a/validation.json']
    require(independent['findings'] == [] and independent['status'] == 'no_blocking_findings_in_reviewed_delta'
        and independent['candidate_review']['sha256'] == PINS['work/candidates/v17-acceptance-pin-review/review.json']
        and independent['inputs_unchanged'] is True and independent['all_shell_sessions_collected'] is True
        and independent['validation']['sha256'] == PINS['work/review-results/v17-python-external-api-20261008a/validation-final.json']
        and python_validation['inputs_unchanged'] is True and python_validation['outputs_compared'] == 47
        and len(python_validation['stages']) == 3 and all(s['exit_code'] == 0 for s in python_validation['stages'])
        and python_validation['stages'][2]['test_methods'] == 8, 'Independent Python review differs')
    pin_review = data['work/review-results/v17-native-object-compile-native-inventory-20261008a/source-and-pin-review.json']
    require(pin_review['code_pin_count'] == 8 and pin_review['code_bytes'] == 945
        and pin_review['pe_header_checks_passed'] == 6 and len(pin_review['data_checks']) == 13
        and all(p['source_matches'] is True for p in pin_review['code_pins'])
        and all(p['match'] is True for p in pin_review['data_checks'])
        and pin_review['game_sha256'].upper() == '9AD3EFE1AF169F40EE577F9DAE5DEBBC87AF6FB8B5450FB345EBF110DC4D771A',
        'Independent exact image review differs')
'''

def main():
    with OLD.open('rb') as stream:
        raw = stream.read(32769)
    if len(raw) > 32768 or hashlib.sha256(raw).hexdigest() != OLD_SHA:
        raise ValueError('Frozen materializer changed')
    text = raw.decode().replace('v16', 'v17').replace('V16', 'V17')
    text = text.replace('v17-acceptance-initialization-review', 'v17-acceptance-pin-review')
    text = text.replace('fixed startup source materialization', 'fixed exact-image source materialization')
    tree = ast.parse(text)
    pin = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'PINS' for t in n.targets))
    audit = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'audited_files')
    lines = text.splitlines(True)
    old_audit = ''.join(lines[audit.lineno-1:audit.end_lineno])
    start = old_audit.index('    independent = ')
    end = old_audit.index("    require(validation['all_stages_exit_zero']", start)
    new_audit = old_audit[:start] + INDEPENDENT + old_audit[end:]
    for begin, finish, replacement in sorted(((pin.lineno, pin.end_lineno, 'PINS = ' + repr(PINS) + '\n'),
                                              (audit.lineno, audit.end_lineno, new_audit + '\n')), reverse=True):
        lines[begin-1:finish] = [replacement]
    result = ''.join(lines).encode()
    compile(result, str(NEW), 'exec')
    difference = ''.join(difflib.unified_diff(text.splitlines(True), result.decode().splitlines(True))).encode()
    record = {'purpose': 'root_v17_materializer_source_adaptation', 'predecessor_sha256': OLD_SHA,
              'source_sha256': hashlib.sha256(result).hexdigest(), 'diff_sha256': hashlib.sha256(difference).hexdigest(),
              'changed_ast_nodes': ['PINS', 'audited_files'], 'pure_version_adaptation_of_remainder': True,
              'game_accessed': False, 'materialized': False, 'native_built': False}
    outputs = ((NEW, result), (ROOT / 'work/review-results/root-v17-materializer-source-adaptation-20261008a.diff', difference),
               (ROOT / 'work/review-results/root-v17-materializer-source-adaptation-20261008a.json', (json.dumps(record, indent=2)+'\n').encode()))
    if any(p.exists() for p, _ in outputs):
        raise ValueError('Never overwrite adaptation')
    for path, value in outputs:
        with path.open('xb') as stream:
            stream.write(value)
    print(json.dumps(record))

if __name__ == '__main__':
    main()
