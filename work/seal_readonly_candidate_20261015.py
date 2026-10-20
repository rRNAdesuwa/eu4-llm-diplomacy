"""Four-field metadata seal of an exact independently reviewed readonly draft."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT=Path(__file__).resolve().parents[1]


def path(name):
    p=PurePosixPath(name)
    assert not p.is_absolute() and '..' not in p.parts and ':' not in name and '\\' not in name
    resolved=(ROOT/name).resolve();assert resolved.is_relative_to(ROOT)
    return resolved


def read(p):
    with p.open('rb') as stream:b=stream.read(4*1024*1024+1)
    assert 0<len(b)<=4*1024*1024
    return b


def pin(p):
    b=read(p);return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())


def main():
    parser=argparse.ArgumentParser()
    for arg in ('candidate','draft-sha','review','review-sha','out'):parser.add_argument('--'+arg,required=True)
    a=parser.parse_args();candidate=path(a.candidate);manifest=candidate/'source-manifest.json'
    review=path(a.review);out=path(a.out)
    assert pin(manifest)['sha256']==a.draft_sha and pin(review)['sha256']==a.review_sha
    snapshot=review.parent/'subject-draft-manifest.json'
    assert read(snapshot)==read(manifest), 'Independent draft snapshot must match exactly'
    old=json.loads(read(manifest));old_pins=old['source_pins']
    assert old['sealed'] is False and old['runtime_capture_authorized'] is False and old['native_ready'] is False
    assert 1<=len(old_pins)<=64
    assert all(pin(path(n))==wanted for n,wanted in old_pins.items())
    out.mkdir(exist_ok=False);(out/'subject-draft-manifest.json').write_bytes(read(manifest))
    new=dict(old);new.update(sealed=True,runtime_capture_authorized=True,stage='independently_reviewed_readonly_runtime_candidate',
        independent_source_review=dict(path=a.review,**pin(review)))
    allowed={'sealed','runtime_capture_authorized','stage','independent_source_review'}
    changed={k for k in set(old)|set(new) if old.get(k)!=new.get(k)}
    assert changed==allowed and new['source_pins']==old_pins and new['native_ready'] is False
    manifest.write_text(json.dumps(new,indent=2)+'\n',encoding='utf-8')
    assert all(pin(path(n))==wanted for n,wanted in old_pins.items())
    assert pin(review)['sha256']==a.review_sha
    receipt=dict(schema='EU4-READONLY-CANDIDATE-ROOT-SEAL/1',draft=pin(out/'subject-draft-manifest.json'),
        production=pin(manifest),review=pin(review),changed_metadata_keys=sorted(changed),source_pin_count=len(old_pins),
        source_pins_unchanged=True,tests_repeated=0,game_process_accesses=0,native_game_calls=0,
        requests_published=0,native_ready=False)
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='sealed',production=pin(manifest),receipt=pin(out/'receipt.json'))))


if __name__=='__main__':main()
