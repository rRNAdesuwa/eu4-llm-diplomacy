"""Materialize a fixed offline R5 case from the explicit stopped 9656 seal."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'work/runtime/native1375-v17'
SEAL = BASE / 'stopped-input-inventory-9656.json'
OUTPUT = BASE / 'batch-stopped-case-r5-9656.json'
SEAL_SHA = 'a495f8df7ade7b651a960daf4531e330f2765787e3d9fe792328152688cc50e2'

def read(path, limit=8*1024*1024):
    if not path.is_file() or path.is_symlink() or path.is_junction():
        raise ValueError('Nonregular case input')
    with path.open('rb') as stream:
        raw = stream.read(limit+1)
    if len(raw)>limit:
        raise ValueError('Case artifact bound')
    return raw

def desc(raw):
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def main():
    raw = read(SEAL,512*1024)
    if desc(raw)['sha256'] != SEAL_SHA:
        raise ValueError('Explicit stopped input seal changed')
    seal = json.loads(raw)
    inputs = dict(seal['inputs'])
    for key,expected in inputs.items():
        if '\\' in key or not key.startswith('work/runtime/native1375-v17/'):
            raise ValueError('Noncanonical input path')
        path = (ROOT/key).resolve()
        if not path.is_relative_to(BASE.resolve()) or desc(read(path)) != expected:
            raise ValueError('Stopped input changed or escaped')
    for path in (SEAL, ROOT/seal['stopped_audit'], Path(__file__)):
        inputs[path.relative_to(ROOT).as_posix()] = desc(read(path))
    if len(inputs)>1400 or sum(v['bytes'] for v in inputs.values())>160*1024*1024:
        raise ValueError('Final case inventory budget')
    case = dict(schema_version=1,purpose='v17_batch_stopped_case_r5',finalized=True,
                inputs=inputs,session_files=seal['session_files'],preflight_scope=seal['preflight_scope'])
    for key in ('batch_scope','journal','summary','exit','stopped_audit'):
        case[key]=seal[key]
    encoded = (json.dumps(case,sort_keys=True,indent=2)+'\n').encode()
    if len(encoded)>512*1024:
        raise ValueError('Case size bound')
    with OUTPUT.open('xb') as stream:
        stream.write(encoded)
    if desc(read(SEAL))['sha256']!=SEAL_SHA:
        raise ValueError('Input seal changed during case materialization')
    print(json.dumps(dict(output=OUTPUT.relative_to(ROOT).as_posix(),case_sha256=desc(encoded)['sha256'],
                         case_bytes=len(encoded),inputs=len(inputs),review_run=False,production=False)))

if __name__=='__main__':
    main()
