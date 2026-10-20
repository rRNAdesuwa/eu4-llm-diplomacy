"""Complete the integration manifest's existing four-review metadata gate."""
import hashlib
import json
from pathlib import Path
import types

ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'work/candidates/integration-task-observer-1375-v1'


def pin(path):
    b=path.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())


def main():
    manifest=HERE/'source-manifest.json'
    assert pin(manifest)['sha256']=='4e41f40b7a3b738357c02f984eb86b5bd89a4ec39dcdeb1e0f69d3b6af585097'
    code=HERE/'integration_task_observer.py'
    assert pin(code)['sha256']=='ec576a21a4018fa1b91d0864990b281a7a075ed3761404d9bdd7559de8b25cb9'
    out=ROOT/'work/reports/integration-task-observer-root-seal-20261015-r2'
    out.mkdir(exist_ok=False);(out/'previous-production-manifest.json').write_bytes(manifest.read_bytes())
    old_receipt=ROOT/'work/reports/integration-task-observer-root-seal-20261015-r1/receipt.json'
    assert pin(old_receipt)['sha256']=='46132a2a1317b3543e6950b3e61cb542b78772c66623532a66300b643f821212'
    (out/'previous-root-seal-receipt.json').write_bytes(old_receipt.read_bytes())
    old=json.loads(manifest.read_text(encoding='utf-8'));new=json.loads(manifest.read_text(encoding='utf-8'))
    assert set(old['independent_reviews'])=={'R44','R45','R46'}
    review=old['independent_source_review']
    assert review['path']=='work/reports/integration-task-observer-source-review-20261015-r1/independent-source-ready.json'
    assert review['sha256']=='14662f7d78556103252f3f52f30a398d570ce246e56bb17948127249ebc10cc4'
    assert pin(ROOT/review['path'])=={k:review[k] for k in ('bytes','sha256')}
    new['independent_reviews']['candidate']=review
    assert new['source_pins']==old['source_pins'] and new['native_ready'] is False
    assert {k for k in old if old[k]!=new[k]}=={'independent_reviews'}
    manifest.write_text(json.dumps(new,indent=2)+'\n',encoding='utf-8')
    module=types.ModuleType('_integration_manifest_file_only');module.__file__=str(code)
    exec(compile(code.read_bytes(),str(code),'exec'),module.__dict__)
    checked=module.verify_sources(runtime=True)
    assert checked['sealed'] is True and checked['runtime_capture_authorized'] is True
    assert checked['source_pins']==old['source_pins']
    receipt=dict(schema='EU4-INTEGRATION-REVIEW-LINK-REPAIR/1',previous_production=pin(out/'previous-production-manifest.json'),
        previous_seal=pin(out/'previous-root-seal-receipt.json'),production=pin(manifest),review=review,
        changed_metadata_paths=['independent_reviews.candidate'],source_pins_unchanged=True,
        final_top_level_changes_from_original_draft=['sealed','runtime_capture_authorized','stage','independent_source_review','independent_reviews'],
        file_only_runtime_source_gate_passed=True,Libraries_constructed=False,observer_constructed=False,game_process_accesses=0,
        tests_repeated=0,CLI_queries_repeated=0,native_game_calls=0,requests_published=0,native_ready=False)
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='metadata_gate_passed',production=pin(manifest),receipt=pin(out/'receipt.json'))))


if __name__=='__main__':main()
