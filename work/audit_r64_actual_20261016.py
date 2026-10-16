"""Independent R64 actual-result retention only; no author/PE/engine execution."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
SUBJECT='work/reports/war-peace-api-20261016-r64-gold-element-selection/'
OUT=ROOT/'work/reports/war-peace-api-20261016-r64-independent-review'
M_PIN=dict(bytes=14450,sha256='ac219aa1b6adc947acf64d61dcd56126b370860b02ab7dcff22a1a8000d1fc81')
LIMIT=24*1024*1024;MAX_FILE=4*1024*1024;MEMORY=768*1024*1024
reads=[dict(path=SUBJECT+'manifest.json',bytes=14450,phase='initial_schema_inspection'),
       dict(path=SUBJECT+'contract.json',bytes=9119,phase='initial_contract_inspection')]
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
    guard();a=(ROOT/path).stat();assert a.st_size<=MAX_FILE
    assert sum(x['bytes'] for x in reads)+a.st_size<=LIMIT
    raw=(ROOT/path).read_bytes();b=(ROOT/path).stat()
    assert len(raw)==a.st_size and(a.st_size,a.st_mtime_ns)==(b.st_size,b.st_mtime_ns)
    value=pin(raw)
    if expected is not None:assert value==expected,(path,value,expected)
    files[path]=dict(**value,raw_hex=raw.hex());reads.append(dict(path=path,**value))
    guard();return raw

def write(name,obj):
    raw=(json.dumps(obj,ensure_ascii=True,indent=2)+'\n').encode()
    assert len(raw)<=MAX_FILE
    with (OUT/name).open('xb') as f:f.write(raw)
    guard();return pin(raw)

def main():
    OUT.mkdir(exist_ok=False)
    write('review-start.json',dict(schema='EU4-R64-ACTUAL-INDEPENDENT-START/1',subject=M_PIN,
        PE_engine_decoder_author_program_tests_game_native=0))
    try:
        m=json.loads(read(SUBJECT+'manifest.json',M_PIN))
        assert isinstance(m['source_pins'],dict) and len(m['source_pins'])==38
        assert isinstance(m['decoder_expected_witness_pins'],dict) and len(m['decoder_expected_witness_pins'])==38
        for path,expected in m['source_pins'].items():read(path,expected)
        for name in ['delivery-manifest.json','filecheck.json','seal-read-accounting.json',
                     'filecheck-actual-execution.json','filecheck-actual.stdout.txt','filecheck-actual.stderr.txt',
                     'seal-execution.json','seal.stdout.txt','seal.stderr.txt']:
            read(SUBJECT+name)
        print(bytes.fromhex(files[SUBJECT+'disassembly.txt']['raw_hex']).decode())
        selected=json.loads(bytes.fromhex(files[SUBJECT+'selected-native.json']['raw_hex']))
        cap=json.loads(bytes.fromhex(files[SUBJECT+'capture.json']['raw_hex']))
        print('KEYS',json.dumps(dict(selected=list(selected),capture=list(cap))))
        print('STORE_INFO',json.dumps({k:v for k,v in selected.items() if k in ['store_counts','manual_explicit_store_sites']}))
        result=write('retained-source.json',dict(schema='EU4-R64-ACTUAL-INDEPENDENT-RETAINED/1',files=files,
            reads=reads,source_physical_bytes=sum(x['bytes'] for x in reads),self_peak=peak,
            PE_engine_decoder_author_program_tests_game_native=0))
        print(json.dumps(dict(retained=result,files=len(files),bytes=sum(x['bytes'] for x in reads),self_peak=peak)))
    except Exception as exc:
        write('retention-failure.json',dict(type=type(exc).__name__,detail=str(exc),reads=reads,self_peak=peak))
        raise

if __name__=='__main__':main()
