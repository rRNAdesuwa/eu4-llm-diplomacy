"""Add only journal-pinned publisher captures omitted from the stopped R6 case."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'work/runtime/native1375-v17'
SOURCE = BASE / 'batch-stopped-case-r6-9656.json'
OUTPUT = BASE / 'batch-stopped-case-r6b-9656.json'
ADD = ROOT / 'work/review-results/v17-batch-r6-missing-artifacts-action-catalog-20261008a/additional-inputs.json'
TRIAGE = ADD.with_name('missing-artifacts.json')
FAILURE = BASE / 'batch-stopped-review-r6-9656-failure.json'
PINS = {
    SOURCE: '7f6425b1fd2aee6d8010e9d0ecd00b0f4fbe53ace8c2a440c6ce19a4dd8268cb',
    ADD: '564399950ab78b6d41fcaa1f9e67300d3b60583c2232904878599129cfb95ffa',
    TRIAGE: '0034eb89074b570a52021f96a570815c1a148388bfa92cae4fcaef321f5f21b6',
}


def read(path, limit=8 * 1024 * 1024):
    if not path.is_file() or path.is_symlink() or path.is_junction():
        raise ValueError('Nonregular case input')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Case artifact bound')
    return raw


def desc(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    original = {path: read(path, 512 * 1024) for path in PINS}
    for path, expected in PINS.items():
        if desc(original[path])['sha256'] != expected:
            raise ValueError('Pinned stopped diagnostic changed')
    case = json.loads(original[SOURCE])
    addition = json.loads(original[ADD])
    triage = json.loads(original[TRIAGE])
    if case['purpose'] != 'v17_batch_stopped_case_r6' or case['finalized'] is not True:
        raise ValueError('Unexpected predecessor case')
    if len(addition) != 88 or triage['missing_inputs'] != addition or triage['inputs_unchanged'] is not True:
        raise ValueError('Unexpected diagnostic addition')
    inputs = dict(case['inputs'])
    if set(addition) & set(inputs):
        raise ValueError('Addition is not an exact missing subset')
    journal_path = ROOT / case['journal']
    journal_raw = read(journal_path)
    if desc(journal_raw) != case['inputs'][case['journal']]:
        raise ValueError('Journal changed')
    references = {row['path'].replace('\\', '/'): row['sha256'] for row in
                  (json.loads(line) for line in journal_raw.splitlines())
                  if row['event'] == 'publisher_capture'}
    if set(references) != set(addition) or any(references[key] != value['sha256'] for key, value in addition.items()):
        raise ValueError('Addition not exactly all journal publisher captures')
    inputs.update(addition)
    for key, expected in inputs.items():
        if '\\' in key or ':' in key or not key.startswith('work/'):
            raise ValueError('Noncanonical case input')
        path = ROOT / key
        if not path.resolve().is_relative_to(ROOT.resolve()) or desc(read(path)) != expected:
            raise ValueError('Stopped input changed or escaped')
    if len(inputs) != 944:
        raise ValueError('Exact stopped input union count')
    for path in (SOURCE, ADD, TRIAGE, FAILURE, Path(__file__)):
        inputs[path.relative_to(ROOT).as_posix()] = desc(read(path))
    if len(inputs) > 1400 or sum(row['bytes'] for row in inputs.values()) > 160 * 1024 * 1024:
        raise ValueError('Final case inventory budget')
    case['inputs'] = inputs
    encoded = (json.dumps(case, sort_keys=True, indent=2) + '\n').encode()
    if len(encoded) > 512 * 1024:
        raise ValueError('Case size bound')
    if any(read(path, 512 * 1024) != raw for path, raw in original.items()):
        raise ValueError('Diagnostic changed during materialization')
    with OUTPUT.open('xb') as stream:
        stream.write(encoded)
    print(json.dumps(dict(output=OUTPUT.relative_to(ROOT).as_posix(), case_sha256=desc(encoded)['sha256'],
                          case_bytes=len(encoded), inputs=len(inputs), added_publishers=len(addition),
                          review_run=False, production=False)))


if __name__ == '__main__':
    main()
