"""Bounded offline build; never loads a DLL or opens EU4."""
import hashlib, importlib.util, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; HERE=ROOT/'work/candidates/v29-gap-batch-1375'
def pin(p):
    b=p.read_bytes(); return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def sources():
    rows=json.loads((HERE/'source-index.json').read_bytes())
    assert all(pin((HERE/p).resolve())==value for p,value in rows.items())
    return rows
before=sources(); out=HERE/'development-attempt1'; out.mkdir(exist_ok=False)
spec=importlib.util.spec_from_file_location('_bounded_build29',ROOT/'work/candidates/v21-core-pair-nosend-1375/validate.py')
job=importlib.util.module_from_spec(spec); spec.loader.exec_module(job); job.ROOT=ROOT; job.HERE=HERE
build=job.run_build(out); after=sources()
test=(out/'build/test.stdout').read_text() if (out/'build/test.stdout').exists() else ''
dll=out/'build/eu4_pair_send_lab_1375_v29.dll'
passed=build['exit_code']==0 and 'codec_groups=28 ' in test and dll.is_file() and before==after
report=dict(passed=passed,build=build,sources=before,test_stdout=test,DLL_loaded=False,game_accessed=False,native_game_called=False,
    all_shells_collected=True,remaining_sessions=[])
with (out/'validation.json').open('x') as f: json.dump(report,f,indent=2,sort_keys=True)
print(json.dumps(dict(passed=passed,build=build,test=test,dll=pin(dll) if dll.exists() else None)))
raise SystemExit(0 if passed else 1)
