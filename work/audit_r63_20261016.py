"""Independent bounded file-only R63 retention, no original module import."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
SUBJECT='work/reports/war-peace-api-20261016-r63-gold-scalar-source/'
OUT=ROOT/'work/reports/war-peace-api-20261016-r63-independent-review'
SHA='965c8f654428410f47ff327a7de28252c9650d8ae02f2f8876560881a6ffdca5'
MAX_FILE=4*1024*1024
MAX_TOTAL=24*1024*1024
MEMORY=768*1024*1024
class PMC(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[
        (x,ctypes.c_size_t) for x in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage',
        'QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage',
        'PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True)
k.GetCurrentProcess.restype=wintypes.HANDLE
p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]
peak=0
reads=[dict(path=SUBJECT+'manifest.json',bytes=14796,phase='initial_statstable_human_inspection'),
       dict(path=SUBJECT+'contract.json',bytes=7894,phase='initial_statstable_human_inspection')]
files={}

def guard():
    global peak
    x=PMC();x.cb=ctypes.sizeof(x)
    assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(x),x.cb)
    peak=max(peak,x.WorkingSetSize,x.PrivateUsage,x.PeakWorkingSetSize,x.PeakPagefileUsage)
    assert peak<=MEMORY

def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def read(path,expected=None):
    guard();a=(ROOT/path).stat();assert a.st_size<=MAX_FILE
    assert sum(x['bytes'] for x in reads)+a.st_size<=MAX_TOTAL
    raw=(ROOT/path).read_bytes();b=(ROOT/path).stat()
    assert len(raw)==a.st_size and (a.st_size,a.st_mtime_ns)==(b.st_size,b.st_mtime_ns)
    actual=pin(raw)
    if expected is not None:assert actual==expected,(path,actual,expected)
    files[path]=dict(**actual,raw_hex=raw.hex());reads.append(dict(path=path,**actual))
    guard();return raw

def main():
    OUT.mkdir(exist_ok=False)
    (OUT/'claim.json').write_bytes((json.dumps(dict(schema='EU4-R63-INDEPENDENT-CLAIM/1',
        subject_manifest_SHA=SHA,PE_decoder_engine_author_program_oldtests_game_native=0),indent=2)+'\n').encode())
    try:
        m=json.loads(read(SUBJECT+'manifest.json',dict(bytes=14796,sha256=SHA)))
        assert isinstance(m['source_pins'],dict) and len(m['source_pins'])==40
        assert isinstance(m['decoder_expected_witness_pins'],dict) and len(m['decoder_expected_witness_pins'])==38
        for path,expected in m['source_pins'].items():read(path,expected)
        for name in ('actual-delivery.json','actual-filecheck.json','retained-seal-accounting.json'):
            if (ROOT/SUBJECT/name).exists():read(SUBJECT+name)
        owned=json.loads(bytes.fromhex(files[SUBJECT+'owned-code.json']['raw_hex']))
        cap=json.loads(bytes.fromhex(files[SUBJECT+'capture.json']['raw_hex']))
        selected=json.loads(bytes.fromhex(files[SUBJECT+'selected-native.json']['raw_hex']))
        print(bytes.fromhex(files[SUBJECT+'disassembly.txt']['raw_hex']).decode())
        print('KEYS',json.dumps(dict(owned=list(owned),capture=list(cap),selected=list(selected))))
        print('SELECTEDKEYS',json.dumps({key:(len(value) if isinstance(value,(list,dict)) else value) for key,value in selected.items() if key not in ('instructions','raw_hex')}))
        raw=(json.dumps(dict(schema='EU4-R63-INDEPENDENT-RETAINED/1',files=files,
            source_reads=reads,source_physical_bytes=sum(x['bytes'] for x in reads),self_peak_bytes=peak,
            engine_witness_opened=False,PE_reads=0,decoder_imports=0),indent=2)+'\n').encode()
        assert len(raw)<=MAX_FILE
        (OUT/'retained-sources.json').write_bytes(raw)
        guard()
        print('RETAINED',len(files),sum(x['bytes'] for x in reads),len(raw),peak)
    except Exception as exc:
        (OUT/'retention-failure.json').write_bytes((json.dumps(dict(type=type(exc).__name__,detail=str(exc),
            source_reads=reads,self_peak_bytes=peak),indent=2)+'\n').encode())
        raise

if __name__=='__main__':main()
