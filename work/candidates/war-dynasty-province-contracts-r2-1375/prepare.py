"""CreateNew minimal offline R2 overlay; original static evidence stays in place."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT/'work/candidates/war-dynasty-province-contracts-1375'
REVIEW = ROOT/'work/review-results/war-dynasty-province-action-catalog-20261008a'
OLD_SHA = 'c283abb1341301392fc613d369e03cf4fff7a91eb776ca55cc10062cd9fb56fc'
REVIEW_SHA = '406f925939ab1ef6df26575176b16460edeac7e866ed1e04221a5b4aed96430a'
FILES = ('contract.py','test_contract.py','test_rewrap.py','prepare.py','validate.py',
         'README.md','repair.diff','source-pins.json')


def raw(p):
    with p.open('rb') as f: b=f.read(8*1024*1024+1)
    assert len(b)<=8*1024*1024
    return b


def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def rec(p): return dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=digest(p))
def load(p):return json.loads(raw(p))
def enc(x):return (json.dumps(x,sort_keys=True,indent=2)+'\n').encode()


def tracked_originals():
    assert digest(OLD/'review.json')==OLD_SHA
    assert digest(REVIEW/'review.json')==REVIEW_SHA
    old=load(OLD/'source-index.json')
    for path, r in old['sources'].items():
        assert digest(ROOT/path)==r['sha256'] and (ROOT/path).stat().st_size==r['bytes'],path
    for path, sha in old['inputs'].items():assert digest(ROOT/path)==sha,path
    # All old candidate files, including both retained validations, remain immutable.
    paths=set(p for p in OLD.rglob('*') if p.is_file())
    paths|={ROOT/p for p in old['inputs']}
    paths|={REVIEW/p for p in ('review.json','counterexamples.json','counterexamples.py',
                             'validation.json','pe-verification.json','test_independent.py')}
    return sorted(paths)


def expected_contract():
    b=raw(OLD/'contract.py')
    patches=[(b' terminal_unknown:bool=False',b' terminal_unknown:bool=False\n ever_wrapped:bool=False'),
      (b"not self.original_destroyed and not self.command_present,'single wrapper'",
       b"not self.ever_wrapped and not self.original_destroyed and not self.command_present,'single wrapper'"),
      (b'self.command_present=True\n def destroy_original',
       b'self.command_present=True;self.ever_wrapped=True\n def destroy_original')]
    # Preserve the frozen source's LF bytes; no global newline or version replacement.
    assert b'\r' not in b and b'\n' in b
    for before,after in patches:
        assert b.count(before)==1, before
        b=b.replace(before,after)
    return b


def create_check(path,b,check):
    if check:assert raw(path)==b,path
    else:
        with path.open('xb') as f:f.write(b)


def main(check):
    pins=[rec(p) for p in tracked_originals()]
    old=raw(OLD/'contract.py');new=expected_contract()
    delta=''.join(difflib.unified_diff(old.decode().splitlines(True),new.decode().splitlines(True),
              fromfile='sealed-v1/contract.py',tofile='r2/contract.py')).encode()
    create_check(HERE/'contract.py',new,check)
    create_check(HERE/'test_contract.py',raw(OLD/'test_contract.py'),check)
    create_check(HERE/'repair.diff',delta,check)
    create_check(HERE/'source-pins.json',enc(pins),check)
    index=dict(schema=1,purpose='war4_one_shot_owned_model_repair_only',
        lineage=[rec(OLD/'review.json'),rec(REVIEW/'review.json')],
        static_report=rec(OLD/'report.json'),inputs=pins,outputs=[rec(HERE/n) for n in FILES],
        static_artifacts_copied_or_rewritten=False,new_decoded_bytes=0,native_implementation=False,
        game_access=False,runtime_verified=False,production_ready=False)
    create_check(HERE/'source-index.json',enc(index),check)
    print(json.dumps(dict(passed=True,check=check,original_inputs=len(pins),
      output_sources=len(FILES),index=rec(HERE/'source-index.json'))))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true')
    main(parser.parse_args().check)
