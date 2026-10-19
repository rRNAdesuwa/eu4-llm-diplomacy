"""Correct one metadata claim; preserve all draft preimages and first tests."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'work/candidates/linked-truce-projection-1375-v2'


def pin(path):
    raw = path.read_bytes()
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    assert pin(HERE/'source-manifest.json')['sha256'] == '3b740b8b9dc2ee73cb27913abe74eafb7345cd82700c42230e3cd3e61e5d9d45'
    assert pin(HERE/'linked_truce_projection.py')['sha256'] == 'f75d0a5dd000c6d513d9e14cf784ff95b45a5e4132e153c3758d981f6e8c69a2'
    pre = HERE / 'lineage-preimage-r1'
    pre.mkdir(exist_ok=False)
    names = ('source-manifest.json', 'source-delta.json', 'prepare_source.py')
    before = {name: pin(HERE/name) for name in names}
    for name in names:
        (pre/name).write_bytes((HERE/name).read_bytes())
    delta = json.loads((HERE/'source-delta.json').read_text(encoding='utf-8'))
    assert 'run' in delta['unchanged']
    delta['unchanged'][delta['unchanged'].index('run')] = 'run status branch; catalog tuple alone changed'
    (HERE/'source-delta.json').write_text(json.dumps(delta, indent=2)+'\n', encoding='utf-8')
    for path in (HERE/'prepare_source.py', ROOT/'work/build_linked_truce_v2_20261015.py'):
        text = path.read_text(encoding='utf-8')
        before_text = "'code_guard', 'Libraries', 'observe', 'run', 'RuntimeCapture reuse'"
        after_text = "'code_guard', 'Libraries', 'observe', 'run status branch; catalog tuple alone changed', 'RuntimeCapture reuse'"
        assert text.count(before_text) == 1
        path.write_text(text.replace(before_text, after_text, 1), encoding='utf-8', newline='\n')
    manifest = json.loads((HERE/'source-manifest.json').read_text(encoding='utf-8'))
    rel = HERE.relative_to(ROOT).as_posix()
    for name in ('prepare_source.py', 'source-delta.json'):
        manifest['source_pins'][rel+'/'+name] = pin(HERE/name)
    (HERE/'source-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    assert all(pin(pre/name) == before[name] for name in names)
    assert pin(HERE/'linked_truce_projection.py')['sha256'] == 'f75d0a5dd000c6d513d9e14cf784ff95b45a5e4132e153c3758d981f6e8c69a2'
    receipt = dict(schema='EU4-V2-LINEAGE-METADATA-REPAIR/1', before=before,
        after={name: pin(HERE/name) for name in names},
        reason='run catalog tuple changed; only the status branch is unchanged',
        CLI_changed=False, tests_changed=False, old_or_new_tests_repeated=0,
        process_accesses=0, native_game_calls=0, requests_published=0, native_ready=False)
    (pre/'repair.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status='passed', manifest=pin(HERE/'source-manifest.json'), repair=pin(pre/'repair.json'))))


if __name__ == '__main__':
    main()
