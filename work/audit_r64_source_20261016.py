"""R64 source-peer file retention only. No target/engine or author module access."""
from pathlib import Path
import ast
import ctypes
from ctypes import wintypes
import hashlib
import json
import difflib

ROOT=Path(__file__).resolve().parents[1]
SUBJECT='work/reports/war-peace-api-20261016-r64-gold-element-selection/'
OLD='work/reports/war-peace-api-20261016-r63-gold-scalar-source/'
OUT=ROOT/'work/reports/war-peace-api-20261016-r64-source-independent-review'
EXPECTED=dict(bytes=19275,sha256='043e7f261df881931801a67308e012723f0f62c87313f54d3be8b62687bd52f0')
MAX_FILE=4*1024*1024;MAX_TOTAL=24*1024*1024;MEMORY=768*1024*1024
reads=[dict(path=SUBJECT+'source-manifest.json',bytes=19275,phase='initial_statstable_schema_inspection')]
files={};peak=0
class PMC(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[
        (x,ctypes.c_size_t) for x in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage',
        'QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage',
        'PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True)
k.GetCurrentProcess.restype=wintypes.HANDLE
p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]

def guard():
    global peak
    x=PMC();x.cb=ctypes.sizeof(x)
    assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(x),x.cb)
    peak=max(peak,x.WorkingSetSize,x.PrivateUsage,x.PeakWorkingSetSize,x.PeakPagefileUsage)
    assert peak<=MEMORY

def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def read(path,expected=None):
    assert not path.startswith('work/deps/') and 'eu4.exe' not in path.lower()
    guard();f=ROOT/path;a=f.stat();assert a.st_size<=MAX_FILE
    assert sum(x['bytes'] for x in reads)+a.st_size<=MAX_TOTAL
    raw=f.read_bytes();b=f.stat()
    assert len(raw)==a.st_size and (a.st_size,a.st_mtime_ns)==(b.st_size,b.st_mtime_ns)
    pn=pin(raw)
    if expected is not None:assert pn==expected,(path,pn,expected)
    files[path]=dict(**pn,raw_hex=raw.hex());reads.append(dict(path=path,**pn))
    guard();return raw

def write(name,obj):
    raw=(json.dumps(obj,ensure_ascii=True,indent=2)+'\n').encode()
    with (OUT/name).open('xb') as f:f.write(raw)
    guard();return pin(raw)

def main():
    OUT.mkdir(exist_ok=False)
    write('review-start.json',dict(schema='EU4-R64-SOURCE-REVIEW-START/1',subject=EXPECTED,
        target_PE_stat_open=0,engine_stat_open_import=0,producer_imports_runs=0,
        tests_game_native_actual_auth_claim=0))
    try:
        manifest=json.loads(read(SUBJECT+'source-manifest.json',EXPECTED))
        assert isinstance(manifest['actual_source_pins'],dict) and len(manifest['actual_source_pins'])==14
        assert isinstance(manifest['decoder_expected_witness_pins'],dict) and len(manifest['decoder_expected_witness_pins'])==38
        for path,pn in manifest['actual_source_pins'].items():read(path,pn)
        extra=['preparation-accounting-delta.json','preparation-delivery.json','preparation-manifest.json',
            'preparation-source-pins.json','preparation.json','prepared-filecheck.json','seal_prepared.py',
            'filecheck-execution.json','filecheck.stderr.txt','filecheck.stdout.json',
            'preparation-execution.json','preparation.stderr.txt','preparation.stdout.json']
        for name in extra:read(SUBJECT+name)
        old=bytes.fromhex(files[OLD+'produce.py']['raw_hex']).decode()
        new=bytes.fromhex(files[SUBJECT+'produce.py']['raw_hex']).decode()
        oldast=ast.parse(old);newast=ast.parse(new)
        oldnodes={x.name:ast.dump(x,include_attributes=False) for x in oldast.body if isinstance(x,(ast.FunctionDef,ast.ClassDef))}
        newnodes={x.name:ast.dump(x,include_attributes=False) for x in newast.body if isinstance(x,(ast.FunctionDef,ast.ClassDef))}
        print('AST_NAMES',list(newnodes));print('AST_CHANGED',[n for n in oldnodes if oldnodes[n]!=newnodes[n]])
        print('SOURCE_DIFF',''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='sealedR63',tofile='preparedR64')))
        print('PROTOCOL',bytes.fromhex(files[SUBJECT+'PROTOCOL.md']['raw_hex']).decode())
        print('SEED',bytes.fromhex(files[SUBJECT+'entry-seed.json']['raw_hex']).decode())
        for node in newast.body:
            if isinstance(node,ast.FunctionDef) and node.name in ('authorization_preflight','main'):
                print('PRODUCER_FUNCTION',ast.get_source_segment(new,node))
        write('retained-source.json',dict(schema='EU4-R64-SOURCE-REVIEW-RETAINED/1',files=files,
            reads=reads,source_physical_bytes=sum(x['bytes'] for x in reads),self_peak_bytes=peak,
            engine_witness_opened=False,PE_stat_open=0,producer_runs=0))
        print('RETAINED',len(files),sum(x['bytes'] for x in reads),peak)
    except Exception as exc:
        write('retention-failure.json',dict(type=type(exc).__name__,detail=str(exc),reads=reads,self_peak=peak))
        raise

if __name__=='__main__':main()
