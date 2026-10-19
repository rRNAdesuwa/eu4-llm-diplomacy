"""Materialize the exact independently reviewed nine-file Contract/2 patch.

No game/process access. Run only after the source-pinned v18 session has ended.
All original inputs and proposed outputs are archived before the first edit.
Unknown/partial application is retained in the journal; never retry this run.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / 'work/candidates/diplomacy-api-contract-v2-review'
INDEX_SHA = '4bcbb75184cc48f32039e01c3795044e88d20cc1ebb9677af0ace3ef41891c80'
REVIEW_SHA = '636db697d80d07d411ca83eabc6be68e9ad33b3b0ed09025f99720a1905d9b84'
INDEPENDENT = ROOT / 'work/review-results/diplomacy-api-v2-external-20261008a/review.json'
INDEPENDENT_SHA = '3af373b7dba7e84dcd824850118c9249dcbf770188c8ac00f25c3ec1b1138cf0'


def require(ok, why):
    if not ok:
        raise ValueError(why)


def no_links(path):
    path = Path(path).absolute()
    for node in (path, *path.parents):
        if node.exists():
            require(not node.is_symlink() and not (getattr(node.stat(), 'st_file_attributes', 0) & 0x400), 'Reparse path')
    return path


def read(path):
    with no_links(path).open('rb') as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    require(len(raw) <= 2 * 1024 * 1024, 'Source byte budget')
    return raw


def descriptor(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def write_new(path, raw):
    no_links(path.parent).mkdir(parents=True, exist_ok=True)
    with no_links(path).open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def verified():
    for path, digest in ((CANDIDATE / 'candidate-index.json', INDEX_SHA),
                         (CANDIDATE / 'review.json', REVIEW_SHA),
                         (INDEPENDENT, INDEPENDENT_SHA)):
        require(descriptor(read(path))['sha256'] == digest, 'Reviewed identity changed: ' + str(path))
    index = json.loads(read(CANDIDATE / 'candidate-index.json'))
    require(len(index['inputs']) == 34 and len(index['outputs']) == 9, 'Exact patch inventory')
    originals, proposed = {}, {}
    for inventory, base, destination in ((index['inputs'], ROOT, originals),
                                         (index['outputs'], CANDIDATE / 'files', proposed)):
        for name, pin in inventory.items():
            path = no_links(base / name).resolve()
            require(path.is_relative_to(base.resolve()), 'Escaped source')
            raw = read(path)
            require(descriptor(raw) == pin, 'Preimage/candidate changed: ' + name)
            destination[name] = raw
    require(sum(map(len, originals.values())) + sum(map(len, proposed.values())) <= 16 * 1024 * 1024, 'Aggregate source budget')
    for name in proposed:
        target = no_links(ROOT / name)
        require(name in originals or not target.exists(), 'Unreviewed existing output: ' + name)
    return index, originals, proposed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    require(args.apply == (args.output is not None), 'Apply requires one new archive directory; check requires none')
    index, originals, proposed = verified()
    if not args.apply:
        print(json.dumps({'checked': True, 'inputs': len(originals), 'outputs': len(proposed), 'formal_modified': False}))
        return 0
    directory = no_links(args.output).resolve()
    require(directory.is_relative_to((ROOT / 'work/runtime').resolve()) and not directory.exists(), 'New archive within work/runtime required')
    directory.mkdir()
    for label, files in (('preimages', originals), ('proposed', proposed)):
        for name, raw in files.items():
            write_new(directory / label / name, raw)
    write_new(directory / 'candidate-index.json', read(CANDIDATE / 'candidate-index.json'))
    write_new(directory / 'candidate-review.json', read(CANDIDATE / 'review.json'))
    write_new(directory / 'independent-review.json', read(INDEPENDENT))
    with (directory / 'application.jsonl').open('xb') as journal:
        def record(value):
            journal.write((json.dumps(value, sort_keys=True) + '\n').encode())
            journal.flush()
            os.fsync(journal.fileno())
        record({'event': 'verified_preimages_archived', 'inputs': index['inputs'], 'outputs': index['outputs'],
                'candidate_review_sha256': REVIEW_SHA, 'independent_review_sha256': INDEPENDENT_SHA,
                'game_accessed': False, 'production_ready': False})
        for number, (name, raw) in enumerate(proposed.items(), 1):
            target = no_links(ROOT / name)
            if name in originals:
                require(read(target) == originals[name], 'Preimage changed before replace: ' + name)
                temporary = directory / f'{number}.pending'
                write_new(temporary, raw)
                os.replace(temporary, target)
            else:
                write_new(target, raw)
            require(descriptor(read(target)) == index['outputs'][name], 'Applied bytes mismatch: ' + name)
            record({'event': 'file_applied', 'number': number, 'path': name, **index['outputs'][name]})
        record({'event': 'complete', 'files': 9, 'production_ready': False})
    print(json.dumps({'applied': True, 'files': 9, 'archive': str(directory), 'production_ready': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
