"""Fresh R2 fixes MSVC trailing-backslash quoting; keeps first tree intact."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'work/candidates/v24-pair-send-core-1375'
HERE=ROOT/'work/candidates/v24-pair-send-core-r2-1375'
def desc(p):
 b=p.read_bytes();assert len(b)<4*1024*1024;return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def put(p,b):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(b.encode('ascii') if isinstance(b,str) else b)
index=json.loads((OLD/'source-index.json').read_bytes());assert all(desc(OLD/k)==v for k,v in index.items())
HERE.mkdir(exist_ok=False);pins=json.loads((OLD/'input-pins.json').read_bytes())
for k,v in index.items():
 pins[(OLD/k).relative_to(ROOT).as_posix()]=v
 if k=='input-pins.json':continue
 put(HERE/k,(OLD/k).read_bytes())
pins[(OLD/'development-attempt1/validation.json').relative_to(ROOT).as_posix()]=desc(OLD/'development-attempt1/validation.json')
pins[Path(__file__).relative_to(ROOT).as_posix()]=desc(Path(__file__))
build=(HERE/'build_test.cmd').read_text()
old='''cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS "%pair24_src%pair_send.cpp" "%pair24_src%test_send.cpp" /Fo"%pair24_out%\\" /Fe"%pair24_out%\\test_send.exe" > "%pair24_out%\\compile.stdout" 2> "%pair24_out%\\compile.stderr"
if errorlevel 1 exit /b 12'''
new='''for %%f in (pair_send test_send) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair24_src%%%f.cpp" /Fo"%pair24_out%\\%%f.obj" > "%pair24_out%\\%%f.stdout" 2> "%pair24_out%\\%%f.stderr"
 if errorlevel 1 exit /b 12
)
link /nologo /OUT:"%pair24_out%\\test_send.exe" "%pair24_out%\\pair_send.obj" "%pair24_out%\\test_send.obj" > "%pair24_out%\\link.stdout" 2> "%pair24_out%\\link.stderr"
if errorlevel 1 exit /b 13'''
assert old in build;(HERE/'build_test.cmd').write_text(build.replace(old,new,1),encoding='ascii')
put(HERE/'input-pins.json',json.dumps(pins,indent=2,sort_keys=True)+'\n')
put(HERE/'source-index.json',json.dumps({p.name:desc(p) for p in HERE.iterdir() if p.is_file()},indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(candidate=HERE.name,inputs=len(pins))))
