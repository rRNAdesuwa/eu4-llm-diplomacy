"""CreateNew adaptation of the frozen root v15 materializer; does not build."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'work/materialize_build_v15_1375.py'
OLD_SHA = 'dfc5456a93eb4bdc18d7ddbf678fdf0648280bce18288eeea2af37530d771548'
NEW = ROOT / 'work/materialize_build_v16_1375.py'
PINS = {
    'work/candidates/v16-acceptance-initialization-review/review.json': 'bfc1654624ad7ed054bf640f9445f566c73ce9e53f32041d8fbc687c4c680929',
    'work/candidates/v16-acceptance-initialization-review/candidate-index.json': '710cd5ba13e501ab23cd8587a24cfae868813e6aefd0ad82b430c91941339c60',
    'work/review-results/v16-candidate-root-20261008a/validation.json': '29b2d5353dc1f46ec5b75dea25eb76750285102b15b44a26dd87ef32763e73ad',
    'work/review-results/v16-acceptance-initialization-action-catalog-20261008a/review.json': '34b01891d7759b8648045f3eb6c5fb340ac9e424f6278d7c5a8049ef0ac7c545',
    'work/review-results/v16-native-object-compile-native-inventory-20261008a/review-r2.json': 'b57e14850c402e263981875e397b00717b20aee7b9d8c51bb9e09a579a20b5ad',
    'work/review-results/v16-native-object-compile-native-inventory-20261008a/validation.json': 'b137fb63846a101456ec1e8e0dbe0b9aefe21fbb9f9d4c2e577f214825d4b5f0',
    'work/candidates/v16-acceptance-initialization-review/native-source-review.json': '1ac15f2466a2feffcc48d7c14fe247176bfce22d685d6cc28690c281fedd92c5',
}

AUDIT = '''def audited_files():
    data = {}
    for name, digest in PINS.items():
        raw = bounded(ROOT / name)
        require(sha(raw) == digest, 'Fixed review input changed: ' + name)
        data[name] = json.loads(raw)
    independent = data['work/review-results/v16-acceptance-initialization-action-catalog-20261008a/review.json']
    validation = data['work/review-results/v16-candidate-root-20261008a/validation.json']
    require(independent['findings'] == [] and independent['status'] == 'passed_with_no_blocking_findings_in_reviewed_scope'
        and independent['candidate_review']['sha256'] == PINS['work/candidates/v16-acceptance-initialization-review/review.json']
        and independent['source_scope']['before_after_equal'] is True
        and independent['independent_validation']['python_tests'] == 56
        and independent['independent_validation']['python_test_exit_code'] == 0, 'Independent review differs')
    require(validation['all_stages_exit_zero'] is True and validation['inputs_unchanged'] is True
        and all(r['exit_code'] == 0 for r in validation['runs']), 'Root validation differs')
    check = subprocess.run([sys.executable, '-B', str(CANDIDATE / 'prepare.py'), '--check'],
        cwd=ROOT, capture_output=True, timeout=30)
    require(check.returncode == 0, 'Fixed candidate check failed: ' + check.stderr.decode(errors='replace')[:2000])
    index = data['work/candidates/v16-acceptance-initialization-review/candidate-index.json']
    native = data['work/candidates/v16-acceptance-initialization-review/native-source-review.json']['native_source_sha256']
    require(index['counts'] == {'native': 22, 'host': 12, 'support': 8, 'fixture': 5, 'total': 47}
        and len(index['files']) == 47 and len(native) == 22 and SUPPORT <= index['files'].keys(), 'Inventory differs')
    compiled = data['work/review-results/v16-native-object-compile-native-inventory-20261008a/validation.json']
    native_review = data['work/review-results/v16-native-object-compile-native-inventory-20261008a/review-r2.json']
    require(compiled['all_compile_steps_passed'] is True and compiled['sources_unchanged'] is True
        and compiled['all_candidate_inputs_unchanged'] is True and compiled['sources_before'] == compiled['sources_after']
        and compiled['object_cpp_count'] == 9 and compiled['assembly_count'] == 1
        and len(compiled['commands']) == 12 and all(c['exit_code'] == 0 for c in compiled['commands']), 'Compile evidence differs')
    require(native_review['mock_observation']['checks_summary'] == 'checks=69 failures=0'
        and native_review['mock_observation']['event']['acceptance_action'] == 'none'
        and native_review['mock_observation']['event']['acceptance_target'] == 'none'
        and native_review['candidate_review']['sha256'] == PINS['work/candidates/v16-acceptance-initialization-review/review.json'], 'Mock evidence differs')
    for name, digest in native.items():
        key = ('work/candidates/v16-acceptance-initialization-review/files/' + name).replace('/', chr(92))
        require(compiled['sources_before'][key]['sha256'] == digest.lower()
            and native_review['native_sources_after'][name]['sha256'] == digest.lower(), 'Compiled source differs: ' + name)
    files = []
    for name, item in index['files'].items():
        dest = ROOT / name
        require(not Path(name).is_absolute() and '..' not in Path(name).parts
            and dest.resolve().is_relative_to(ROOT.resolve()), 'Target escapes repository')
        raw = bounded(CANDIDATE / 'files' / name)
        require(len(raw) == item['bytes'] and sha(raw) == item['sha256'], 'Source changed: ' + name)
        if name in SUPPORT:
            require(sha(bounded(dest)) == item['sha256'], 'Frozen shared support changed: ' + name)
        else:
            require('v16' in name, 'Nonversioned mutation rejected: ' + name)
            files.append((dest, raw, item['sha256']))
    require(len(files) == 39 and len({str(p) for p, _, _ in files}) == 39, 'New destination count differs')
    return files
'''


def main():
    with OLD.open('rb') as f:
        raw = f.read(32769)
    if len(raw) > 32768 or hashlib.sha256(raw).hexdigest() != OLD_SHA:
        raise ValueError('Frozen root materializer changed')
    text = raw.decode().replace('v15', 'v16').replace('V15', 'V16')
    text = text.replace('v16-acceptance-control-implementation-r3', 'v16-acceptance-initialization-review')
    text = text.replace('fixed r3 source materialization', 'fixed startup source materialization')
    tree = ast.parse(text)
    replacements = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(n, ast.Name) and n.id == 'PINS' for n in node.targets):
            replacements.append((node.lineno, node.end_lineno, 'PINS = ' + repr(PINS) + '\n'))
        if isinstance(node, ast.FunctionDef) and node.name == 'audited_files':
            replacements.append((node.lineno, node.end_lineno, AUDIT))
    if len(replacements) != 2:
        raise ValueError('Unexpected inherited source structure')
    lines = text.splitlines(True)
    for start, end, replacement in sorted(replacements, reverse=True):
        lines[start-1:end] = [replacement]
    result = ''.join(lines).encode()
    compile(result, str(NEW), 'exec')
    delta = ''.join(difflib.unified_diff(text.splitlines(True), result.decode().splitlines(True))).encode()
    report = ROOT / 'work/review-results/root-v16-materializer-source-adaptation-20261008a.json'
    difference = ROOT / 'work/review-results/root-v16-materializer-source-adaptation-20261008a.diff'
    if any(p.exists() for p in (NEW, report, difference)):
        raise ValueError('Never overwrite root adaptation')
    for path, data in ((NEW, result), (difference, delta)):
        with path.open('xb') as f:
            f.write(data)
    record = {'purpose': 'root_materializer_v16_source_adaptation', 'predecessor_sha256': OLD_SHA,
              'source_sha256': hashlib.sha256(result).hexdigest(), 'diff_sha256': hashlib.sha256(delta).hexdigest(),
              'changed_ast_nodes': ['PINS', 'audited_files'], 'pure_version_adaptation_of_remainder': True,
              'game_accessed': False, 'materialized': False, 'native_built': False}
    with report.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(record, f, indent=2);f.write('\n')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
