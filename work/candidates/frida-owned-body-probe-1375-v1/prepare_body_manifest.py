"""File-only draft for independent review; cannot seal or launch the probe."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT/'work/reports/war-peace-api-20261015-r19-body-host-offline/body-host-manifest-draft.json'


def pin(path):
    raw = path.read_bytes()
    if not 0 < len(raw) <= 16*1024*1024:
        raise ValueError('Selected source size bound')
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def main():
    sources = {}
    for path in sorted([*HERE.glob('*.py'),*HERE.glob('*.js'),HERE/'PROTOCOL.md',HERE/'source-manifest.json']):
        sources[path.relative_to(ROOT).as_posix()] = pin(path)
    selected = [
        'work/candidates/frida-entry-observer-1375-v1/capture_once.py',
        'work/candidates/frida-entry-observer-1375-v1/host-manifest.json',
        'work/reports/frida-entry-host-review-20261015-r1/independent-source-ready.json',
        'work/reports/war-peace-api-20261015-r17-owned-goal-independent-review/war/profiles.json',
        'work/reports/war-peace-api-20261015-r18-body-probe-contract/war/manifest.json',
        'work/reports/war-peace-api-20261015-r18-body-probe-contract/war/body-probe-contract.json',
        'work/reports/war-peace-api-20261015-r18-body-probe-contract/war/required-loaded-bytes.json',
        'work/candidates/rea-frida-owned-ffi-smoke-20261015/source-manifest.json',
        'work/reports/rea-frida-owned-ffi-source-review-20261015/independent-source-ready.json',
        'work/reports/rea-frida-owned-ffi-live-review-20261015/independent-file-audit.json',
        'work/reports/rea-frida-owned-ffi-live-review-20261015/manifest.json',
        'work/reports/rea-frida-owned-ffi-smoke-20261015/f724e4537abba85248a900c51ca487c3/launcher-receipt.json',
        'work/reports/frida-owned-body-component-review-20261015-r1/component-source-ready.json',
        'work/reports/frida-owned-body-component-review-20261015-r1/manifest.json',
        'work/reports/war-peace-api-20261015-r19-body-host-review/war/independent-source-ready.json',
        'work/candidates/frida-owned-body-probe-1375-v1/offline-r1/receipt.json',
        'work/candidates/frida-owned-body-probe-1375-v1/offline-r1/vm-corpus.json',
        'work/reports/war-peace-api-20261015-r19-body-host-offline/initial-tests.json',
        'work/reports/war-peace-api-20261015-r19-body-host-offline/host-tests.stderr.txt',
    ]
    for rel in selected:
        sources[rel] = pin(ROOT/rel)
    require_review = 'work/reports/frida-owned-body-final-review-20261015-r1/independent-source-ready.json'
    result = dict(schema='EU4-OWNED-BODY-HOST-MANIFEST/1',sealed=False,pid=80340,
        creation='01dd5c075fcf8c26',base='0x7ff7034b0000',source_pins=sources,
        independent_review=require_review,independent_review_pin=None,
        native_ready=False,sender_authorized=False,lifetime_lease=False,
        source_only_draft=True,automatic_retry=False)
    with OUT.open('x',encoding='ascii',newline='\n') as stream:
        json.dump(result,stream,indent=2,sort_keys=True)
        stream.write('\n')
    print(json.dumps(dict(output=str(OUT),pin=pin(OUT),source_pins=len(sources),sealed=False,
        process_opened=False)))


if __name__ == '__main__':
    main()
