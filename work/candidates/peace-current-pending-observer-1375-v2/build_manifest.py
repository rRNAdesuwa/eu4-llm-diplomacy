"""First v2 source freeze only. No Libraries, tests, target or PE access."""
from pathlib import Path
import ast, ctypes, hashlib, json, types
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
TOTAL=0
EVENTS=[]
CAP=32*1024*1024
class Memory(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in ('peakws','ws','peakpaged','paged','peaknonpaged','nonpaged','pagefile','peakpagefile','private')]
def memory():
 k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True)
 k.GetCurrentProcess.restype=ctypes.c_void_p
 p.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong];p.GetProcessMemoryInfo.restype=ctypes.c_int
 v=Memory();v.cb=ctypes.sizeof(v);assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(v),v.cb)
 assert v.private<768*1024*1024 and v.private<1024*1024*1024
 return v.private
def read(path):
 global TOTAL
 memory();size=path.stat().st_size;assert 0<size<=4194304 and TOTAL+size<=CAP
 b=path.read_bytes();TOTAL+=len(b);assert len(b)==size
 EVENTS.append(dict(path=path.relative_to(ROOT).as_posix(),bytes=len(b)));return b
def bpin(b):return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def pin(path):return bpin(read(path))
def save(name,value):
 with (HERE/name).open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,ensure_ascii=True,sort_keys=True,indent=2);f.write('\n')
def main():
 assert not (HERE/'source-manifest.json').exists()
 save('build-claim.json',dict(operation='freeze_new_v2_source_only',automatic_retry=False,tests_run=0,game_access=0))
 raw=read(HERE/'peace_current_pending.py');ast.parse(raw)
 module=types.ModuleType('_peace_v2_freeze');module.__file__=str(HERE/'peace_current_pending.py');exec(compile(raw,module.__file__,'exec'),module.__dict__)
 budget=json.loads(read(HERE/'budget.json'));auth=budget['delegated_budget_authorization']
 auth_raw=read(ROOT/auth['path']);assert bpin(auth_raw)=={k:auth[k] for k in ('bytes','sha256')}
 owner_raw=read(ROOT/(module.DESIGN+'manifest.json'));assert bpin(owner_raw)['sha256']==module.FIXED[module.DESIGN+'manifest.json']
 owner=json.loads(owner_raw);pins={**owner['local_pins'],**owner['captured_source_pins']}
 for name,sha in module.FIXED.items():
  value=pin(ROOT/name);assert value['sha256']==sha;pins[name]=value
 for name in module.REQUIRED:pins[name]=pin(ROOT/name)
 pins[auth['path']]={k:auth[k] for k in ('bytes','sha256')}
 assert len(pins)<=96 and sum(p['bytes'] for p in pins.values())<=16*1024*1024
 for name,expected in pins.items():assert pin(ROOT/name)==expected
 m=dict(schema='EU4-PEACE-CURRENT-PENDING-MANIFEST/2',sealed=False,runtime_capture_authorized=False,
  stage='draft_source_frozen_before_first_six_new_fakes',game_sha256=module.GAME_SHA,source_pins=pins,
  source_graph_sha256=module.graph_digest(pins),independent_source_review=None,production_review=None,
  native_ready=False,selected_effect_verified=False)
 save('source-manifest.json',m)
 save('source-manifest.draft.json',m)
 # Use the new verifier once, metering its explicit reads without changing its source.
 original=module.read
 def tracked(path,maximum=4194304):
  b=read(Path(path));assert len(b)<=maximum;return b
 module.read=tracked
 checked=module.verify_sources();module.read=original
 assert checked['runtime_capture_authorized'] is False
 save('preparation.json',dict(schema='EU4-PEACE-V2-PREPARATION/1',source_manifest=pin(HERE/'source-manifest.json'),
  source_count=len(pins),source_graph_bytes=sum(v['bytes'] for v in pins.values()),source_graph_sha256=m['source_graph_sha256'],
  owner_graph_complete=True,new_test_methods=6,tests_run=0,check_catalog_run=0,old_test_methods_run=0,
  source_review='pending',production_review='pending',game_access=0,native_game_calls=0,
  budget=budget,explicit_read_bytes_before_preparation_write=TOTAL,explicit_read_events=EVENTS,software_private_bytes=memory(),
  accounting_scope='Explicit bounded build reads; source verifier reads included; no delegated Libraries execution'))
 print(json.dumps(dict(status='v2_draft_frozen',source_manifest=pin(HERE/'source-manifest.json'),source_count=len(pins),source_graph_bytes=sum(v['bytes'] for v in pins.values()),build_explicit_read_bytes=TOTAL,software_private_bytes=memory()),ensure_ascii=True))
if __name__=='__main__':main()
