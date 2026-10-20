"""Create/check staging manifest, explicit patch and immutable source index."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
STAGE = HERE / 'files'
INPUT_SHA = '35b5e7152bbf21c63f0c0ae9954ca1d4382322f440ada4d7a3a010e479fb3b8b'
APPLICATION_FILES = (
    'bridge/diplomacy_api.py', 'bridge/diplomacy_service.py',
    'bridge/diplomacy_contract_v3.py', 'bridge/diplomacy_contract_v3_pins.json',
    'tools/diplomacy.py', 'tools/serve_diplomacy.py',
    'bridge/tests/test_diplomacy_contract_v3.py', 'docs/diplomacy-api.md',
)


def read(path, limit=2 * 1024 * 1024):
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('bounded input exceeded')
    return raw


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def descriptor(path):
    return {'bytes': path.stat().st_size, 'sha256': digest(path)}


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode('ascii')


def verify_inputs():
    raw = read(HERE / 'input-pins.json', 64 * 1024)
    if hashlib.sha256(raw).hexdigest() != INPUT_SHA:
        raise ValueError('fixed original input inventory changed')
    pins = json.loads(raw)
    if not 1 <= len(pins) <= 64:
        raise ValueError('input count')
    total = 0
    for name, pin in pins.items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError('source path escaped original repository')
        source = read(path)
        total += len(source)
        if pin != {'bytes': len(source), 'sha256': hashlib.sha256(source).hexdigest()}:
            raise ValueError('original source changed: ' + name)
        if total > 16 * 1024 * 1024:
            raise ValueError('aggregate source budget')
    return pins


def proposed_artifacts():
    pins = verify_inputs()
    stage_names = {str(path.relative_to(STAGE)).replace('\\', '/')
                   for path in STAGE.rglob('*') if path.is_file()}
    if stage_names != set(pins) | set(APPLICATION_FILES):
        raise ValueError('unexpected staging file, cache or database')
    for name in set(pins) - set(APPLICATION_FILES):
        if descriptor(STAGE / name) != pins[name]:
            raise ValueError('unchanged dependency copy differs: ' + name)
    manifest = {
        'schema': 1, 'status': 'staging_only_not_applied',
        'original_files_modified': False, 'protocol': 'EU4DIPLOMACY-CONTRACT/3',
        'application_files': {name: {'before': pins.get(name), 'after': descriptor(STAGE / name)}
                              for name in APPLICATION_FILES},
        'unchanged_supporting_dependency_copies': len(stage_names - set(APPLICATION_FILES)),
        'all_execution_unsupported': True, 'backend_registered': False,
        'production_supported': False, 'independent_review_required': True,
        'application_note': 'Only the listed eight application files are proposed for later explicit application. Other files under files/ are unchanged pinned dependencies for isolated validation.',
    }
    patch_lines = []
    for name in APPLICATION_FILES:
        before = read(ROOT / name).decode('utf8').splitlines(keepends=True) if name in pins else []
        after = read(STAGE / name).decode('utf8').splitlines(keepends=True)
        # Normalize line endings only in the review patch, not in any source.
        before = [line.rstrip('\r\n') + '\n' for line in before]
        after = [line.rstrip('\r\n') + '\n' for line in after]
        patch_lines.extend(difflib.unified_diff(before, after,
            fromfile='a/' + name if name in pins else '/dev/null', tofile='b/' + name))
    examples = json.loads(read(STAGE / 'work/candidates/ten-families-typed-contract-r2-1375/request-examples.json'))
    formal_examples = {'protocol': 'EU4DIPLOMACY-CONTRACT/3',
                      'scope': 'syntax only; unsupported; no runtime authority', 'requests': []}
    for request in examples['requests']:
        formal_examples['requests'].append({'protocol': 'EU4DIPLOMACY-CONTRACT/3',
            'request_id': request['request_id'], 'action': request['action_id'], 'parameters': request['parameters']})
    return {'application-manifest.json': canonical(manifest),
            'patch.diff': ''.join(patch_lines).encode('utf8'),
            'formal-request-examples.json': canonical(formal_examples)}


def source_index():
    names = ['input-pins.json', 'prepare.py', 'validate.py', 'README.md',
             'application-manifest.json', 'patch.diff', 'formal-request-examples.json']
    names += [str(path.relative_to(HERE)).replace('\\', '/')
              for path in STAGE.rglob('*') if path.is_file()]
    return {'schema': 1, 'input_pins_sha256': INPUT_SHA,
            'sources': {name: descriptor(HERE / name) for name in sorted(names)},
            'application_files': list(APPLICATION_FILES),
            'original_repository_modified': False, 'runtime_verified': False,
            'production_supported': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for name, raw in proposed_artifacts().items():
        path = HERE / name
        if args.check:
            if read(path) != raw:
                raise ValueError('prepared artifact differs: ' + name)
        else:
            with path.open('xb') as stream:
                stream.write(raw)
    raw = canonical(source_index())
    path = HERE / 'source-index.json'
    if args.check:
        if read(path) != raw:
            raise ValueError('staging source index changed')
    else:
        with path.open('xb') as stream:
            stream.write(raw)
    print(json.dumps({'check': args.check, 'source_index_sha256': hashlib.sha256(raw).hexdigest(),
                      'application_files': len(APPLICATION_FILES), 'stage_sources': len(source_index()['sources']),
                      'original_repository_modified': False, 'execution_supported': False}))


if __name__ == '__main__':
    main()
