"""Seal only this additive relation host, CLI, tests and independent audit."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FILES=('bridge/relation_state_service.py','tools/observe_relation_runtime.py',
    'bridge/tests/test_relation_state_service.py','tools/build_relation_state_service_manifest.py',
    'bridge/relation_effect_reader_manifest_1375.json','bridge/diplomacy_observer_service.py',
    'work/reports/relation-state-service-20261015/audit_live_file.py',
    'work/reports/relation-state-service-20261015/live-file-audit.json',
    'work/reports/relation-state-service-20261015/report.md')


def main():
    pins={}
    for name in FILES:
        raw=(ROOT/name).read_bytes();pins[name]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    value=dict(schema='EU4-RELATION-STATE-HOST-MANIFEST/1',
        game_sha256='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a',
        read_only=True,native_calls=0,source_pins=pins)
    dest=ROOT/'bridge/relation_state_service_manifest_1375.json'
    with dest.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
    print(json.dumps(dict(path=str(dest),bytes=dest.stat().st_size,sha256=hashlib.sha256(dest.read_bytes()).hexdigest())))


if __name__=='__main__':main()
