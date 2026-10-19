"""Create a new immutable named test-save copy and parse it completely."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from work.inspect_diplomacy_save import inspect_save, MAX_STREAM, CHUNK


def identity(path):
    s = path.stat()
    return s.st_size, s.st_mtime_ns, s.st_ino


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--destination', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--target', action='append', required=True)
    a = p.parse_args()
    source = a.source.resolve(strict=True)
    destination = a.destination.resolve()
    output = a.output.resolve()
    if not source.is_file() or source == destination or source == output or destination == output:
        raise ValueError('Paths must be distinct and source must be a regular file')
    if destination.parent != source.parent or destination.suffix != '.eu4':
        raise ValueError('Destination must be a new .eu4 in the same save directory')
    if destination.exists() or output.exists():
        raise FileExistsError('Evidence destination/output already exists; never overwrite')
    before = identity(source)
    if before[0] > MAX_STREAM:
        raise ValueError('Save exceeds byte bound')
    digest = hashlib.sha256()
    count = 0
    with destination.open('xb') as dst, source.open('rb') as src:
        while raw := src.read(CHUNK):
            count += len(raw)
            if count > MAX_STREAM:
                raise ValueError('Save exceeded bound while copying')
            dst.write(raw)
            digest.update(raw)
    if before != identity(source) or count != before[0]:
        raise ValueError('Source changed during copy; incomplete copy retained, do not use')
    report = inspect_save(destination, 'FRA', tuple(a.target))
    expected = digest.hexdigest().upper()
    if report['source']['sha256'] != expected or report['source']['size_bytes'] != count:
        raise ValueError('Copy hash/size mismatch')
    if before != identity(source):
        raise ValueError('Source changed during parsing; do not use copy')
    report['copy_evidence'] = {'source': str(source), 'destination_create_new': True,
        'source_identity_before_after_equal': True, 'size_bytes': count, 'sha256': expected,
        'source_stat': list(before)}
    with output.open('x', encoding='utf-8', newline='\n') as dst:
        json.dump(report, dst, ensure_ascii=True, indent=2)
        dst.write('\n')
    records = report['global_diplomacy']['records']
    selected = [r for r in records if 'trade' in str(r['key'])]
    print(json.dumps({'output': str(output), 'copy': str(destination), 'sha256': expected,
        'size_bytes': count, 'parsed_complete': report['parsed_complete'],
        'metadata': report['metadata'], 'trade_records': selected}, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
