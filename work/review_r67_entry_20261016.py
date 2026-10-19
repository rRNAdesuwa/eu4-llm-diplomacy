"""R67 raw caller seed only. No delivered program/decoder/PE execution."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import hashlib
import json
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
B='work/reports/war-peace-api-20261016-r67-entry-helper-register-contract/'
U='work/reports/war-peace-api-20261016-r66-generated-record-postprocess/'
R='work/reports/war-peace-api-20261016-r66-independent-review/'
O='work/reports/war-peace-api-20261016-r67-entry-independent-review/'
OUT=ROOT/O
LIMIT=4*1024*1024;MANUAL=512*1024;MEMORY=768*1024*1024
reads=[];peak=0;files={}
PINS={
 B+'entry-seed.json':dict(bytes=9961,sha256='460b09544e559155dc5153b223df04e36dadb3fef4866cea7bdf3fde6579f975'),
 U+'manifest.json':dict(bytes=15233,sha256='ccf2263abe0d7b538f6b28dcd8df86afb7f50e7a05931c6b48d1a7e7dda7e6a2'),
 U+'capture.json':dict(bytes=106529,sha256='afe78019ab8dc507a69611f00ed3807013f2c5f3a4d355fbd718ff33e05fb292'),
 U+'owned-code.json':dict(bytes=881,sha256='7a8d4de931b655d3292cde59d28bc7ca4e8a8bbf95e9abed54f1401abf94f42e'),
 U+'contract.json':dict(bytes=8319,sha256='1440ddf1b3da152a643899a64d1c02226da8becd9080a4204fa1beaf6d10dc2e'),
 R+'findings.json':dict(bytes=5711,sha256='9f4f95352be92800da6c7e1d93a237f7875f45ca7a6ed4d3d0ec2ecc163c0005'),
 R+'manifest.json':dict(bytes=13196,sha256='29faa23e023e72f12d63a3a990b8dedfd6f93dee6e58d369785b8c4dc274726f')}
class PMC(ctypes.Structure):
 _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True)
k.GetCurrentProcess.restype=wintypes.HANDLE;p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]
def guard():
 global peak
 x=PMC();x.cb=ctypes.sizeof(x);assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(x),x.cb)
 peak=max(peak,x.WorkingSetSize,x.PrivateUsage,x.PeakWorkingSetSize,x.PeakPagefileUsage);assert peak<=MEMORY
def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def read(path,expected=None):
 assert 'eu4.exe' not in path.lower() and not path.startswith('work/deps/')
 guard();f=ROOT/path;a=f.stat();assert a.st_size<=4*1024*1024
 assert sum(x['bytes'] for x in reads)+a.st_size<LIMIT
 raw=f.read_bytes();z=f.stat();assert len(raw)==a.st_size and(a.st_size,a.st_mtime_ns)==(z.st_size,z.st_mtime_ns)
 actual=pin(raw)
 if expected is not None:assert actual==expected,(path,actual,expected)
 reads.append(dict(path=path,**actual));guard();return raw
def write(name,value):
 raw=(json.dumps(value,ensure_ascii=True,indent=2)+'\n').encode('ascii');assert len(raw)<4*1024*1024
 with (OUT/name).open('xb') as f:f.write(raw)
 return pin(raw)
def false_authority():return {k:False for k in ('native_ready','callable','reader_adoption_allowed','selected_effect_verified','amount_units_verified','recipient_direction_verified','world_lease','atomic_snapshot','authorizes_retry','runtime_capture_authorized','new_static_actual_authorized')}
def operations():return {k:0 for k in ('PE_stat_open','engine_stat_open','decoder','producer','tests','game_process','Frida','native_game_calls','requests','new_callee_bytes','new_actual_or_authorization_or_claim')}
def main():
 OUT.mkdir(exist_ok=False)
 try:
  for path,expected in PINS.items():files[path]=read(path,expected)
  # Additional three files are pinned as source/budget metadata only. The raw
  # caller review does not audit or run their contents or follow their closure.
  for name,n,prefix in [('source-manifest.json',19910,'4e40c319'),('produce.py',23058,'0864e0e4'),('budget.json',1637,'d25a011f')]:
   path=B+name;raw=read(path);actual=pin(raw);assert actual['bytes']==n and actual['sha256'].startswith(prefix);files[path]=raw;PINS[path]=actual
  seed=json.loads(files[B+'entry-seed.json']);cap=json.loads(files[U+'capture.json']);owned=json.loads(files[U+'owned-code.json']);full=json.loads(files[R+'findings.json'])
  assert full['sealed'] is True and full['passed'] is True and full['blocking_findings']==[]
  assert full['subject_manifest']==PINS[U+'manifest.json'] and full['subject_capture']==PINS[U+'capture.json'] and full['subject_contract']==PINS[U+'contract.json']
  assert seed['entry_rva']=='0x1a337f0' and seed['call_site_rva']=='0x994f15' and seed['raw_call']=='e8d6e80901'
  assert seed['game_sha256']==cap['game_sha256']==owned['game_sha256']=='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
  assert seed['game_bytes']==cap['game_bytes']==38462504
  for field,name in [('upstream_R66_manifest','manifest.json'),('upstream_R66_capture','capture.json'),('upstream_R66_owned','owned-code.json'),('upstream_R66_contract','contract.json')]:assert seed[field]==PINS[U+name]
  rows=seed['minimal_continuous_caller_rows'];assert rows==cap['analysis']['instructions'][:10] and len(rows)==10
  expected=[('48895c2408','mov'),('48896c2410','mov'),('4889742418','mov'),('57','push'),('b840100000','mov'),('e8d6e80901','call'),('482be0','sub'),('0fb61a','movzx'),('488b6908','mov'),('488b31','mov')]
  cur=0x994f00;raw=bytes.fromhex(owned['raw_hex']);replayed=[]
  for row,(hx,mnemonic) in zip(rows,expected):
   b=bytes.fromhex(hx);assert int(row['rva'],16)==cur and row['bytes']==hx and row['mnemonic']==mnemonic
   assert raw[cur-0x994f00:cur-0x994f00+len(b)]==b
   replayed.append(dict(rva=hex(cur),bytes=hx,mnemonic=mnemonic,raw_equal=True));cur+=len(b)
  assert cur==0x994f27 and sum(len(bytes.fromhex(x['bytes'])) for x in rows)==39
  assert seed['minimal_window']==['0x994f00','0x994f27'] and seed['minimal_window_bytes']==39
  assert seed['first_CALL_prefix_bytes']==26 and seed['postCALL_SUB_and_field_read_bytes']==13
  call=bytes.fromhex(seed['raw_call']);displacement=struct.unpack('<i',call[1:])[0]
  assert displacement==seed['signed_rel32']==17426646
  assert 0x994f15+5+displacement==0x1a337f0 and rows[5]['immediates']==[0x1a337f0]
  assert rows[4]['immediates']==[0x1040] and rows[4]['registers_written']==['eax']
  assert all(not(set(row['registers_written'])&{'rcx','ecx','cx','cl','rdx','edx','dx','dl','r8','r8d','r9','r9d'}) for row in rows[:6])
  for row,base,disp,width in [(rows[0],'rsp',8,8),(rows[1],'rsp',16,8),(rows[2],'rsp',24,8),(rows[7],'rdx',0,1),(rows[8],'rcx',8,8),(rows[9],'rcx',0,8)]:
   q=row['memory_operands'];assert len(q)==1 and(q[0]['base'],q[0]['displacement'],q[0]['width_bytes'])==(base,disp,width)
  assert all('rflags' not in row['registers_written'] for row in rows[:6])
  assert rows[6]['registers_written']==['rflags','rsp']
  assert seed['XMM0_at_call']=='unknown_inherited_no_local_XMM_assignment_before_first_CALL' and seed['callee_XMM_consumption_proved'] is False
  for key in false_authority():
   if key in seed:assert seed[key] is False
  before={path:pin(value) for path,value in files.items()}
  for path,expectedpin in before.items():read(path,expectedpin)
  rp=write('raw-seed-replay.json',dict(schema='EU4-R67-INDEPENDENT-RAW-SEED/1',passed=True,
   complete_contiguous_rows=replayed,window=['0x994f00','0x994f27'],bytes=39,pre_and_call_bytes=26,post_call_bytes=13,
   call=dict(site='0x994f15',raw_hex='e8d6e80901',next_rva='0x994f1a',signed_rel32=displacement,target_rva='0x1a337f0'),
   pre_CALL=dict(RAX='0x1040 zeroextended by MOVEAX',RCX='incoming R66 opaqueH pointer unchanged by shownprefix; pointee contents notimmutable',
    RDX='incoming borrowedcurrentTaddress unchanged by shownprefix; not a preservation proof aftercall',R8_R9_XMM='unknown inherited; no local assignment',
    arithmetic_flags_DF='unknown inherited; MOV/PUSH do not establish them',
    RSP='R66entryQ-8 afterPUSHRDI; helperentryRSPQ-16 afterCALLpush; returnslotQ-16 holds modulebase+0x994f1a',
    explicit_stores='Q+8 RBX/Q+10hex RBP/Q+18hex RSI; PUSHRDI implicitstoreQ-8'),
   post_CALL=dict(RAX_RCX_RDX_RSP_contract='unknown until actual specificcallee evidence',
    selected_caller_use='SUBRSP,RAX; thenBYTE[postRDX]->zeroextendedEBX; QWORD[postRCX+8]->RBP; QWORD[postRCX]->RSI',
    flags='SUB writes arithmeticflags with unknowninputs; no DF orotherbitpreservation inferred'),
   new_callee_bytes=0,ordinary_ABI_substitution=False,all_sources_pre_post_equal=True))
  # The extra512KiB is an explicit allowance for initial seed inspection and
  # this script's small own-output pin reads; the counted source read stage<4MiB.
  counted=sum(x['bytes'] for x in reads);assert counted<LIMIT
  fp=write('findings.json',dict(schema='EU4-R67-INDEPENDENT-ENTRY-SEED-REVIEW/1',sealed=True,passed=True,blocking_findings=[],
   scope='raw_call_entry_seed_only',entry_seed_pin=PINS[B+'entry-seed.json'],entry_rva='0x1a337f0',call_site_rva='0x994f15',raw_call='e8d6e80901',
   source_manifest_pin=PINS[B+'source-manifest.json'],producer_pin=PINS[B+'produce.py'],budget_pin=PINS[B+'budget.json'],
   upstream_full_review=dict(path=R+'findings.json',**PINS[R+'findings.json']),raw_replay=rp,
   checks=dict(continuous_rows=10,owned_raw_bytes=39,pre_call_with_CALL_bytes=26,post_call_bytes=13,
    caller_relative_CALL_target_verified=True,original_frame_and_pre_RAX_verified=True,
    incoming_RCXRDX_unchanged_in_selected_prefix=True,postCALL_preservation_unknown=True,
    source_pins_pre_post_equal=True),
   limits=[
    'This verifies a raw direct CALL seed and selected caller prefix only; helper body, entrypdata, return, faults, memorywrites and downstreamcalls are not read.',
    'OpaqueH/currentTinput direction is inherited conditionally from the pinned fullR66 review; pointer registers stable beforeCALL do not prove immutable pointed contents or complete types.',
    'OrdinaryWin64ABI cannot fill postcalleeRAX/RCX/RDX/RSP behavior. PreRAX1040 does not establish returnedRAX1040 or a fixed/balanced1040frame.',
    'R8/R9/XMM/arithmeticflags/DF are unknown inherited. MOV/PUSH do not establish flagvalues; postSUB hasunknowninputs and does not establish DF.',
    'No __chkstk/CRT name, purepredicate, currency, ownership, safelease, nativepermission, actualcapture or result effect is proved.',
    'Source/producer/budget are hashfixed metadata only; this rawseed review does not repeat the separate fullsourcepeer audit or authorize staticactual.'
   ],source_pins=before,resource_evidence=dict(counted_source_bytes=counted,source_read_limit=LIMIT,
    manual_and_small_own_pin_allowance_bytes=MANUAL,total_explicit_upper_before_check=counted+MANUAL,
    own_peak_bytes=peak,software_memory_limit=MEMORY,no_all_OS_or_loader_IO_claim=True),
   authority=false_authority(),operations=operations(),all_shells_collected=True,next_scope_auto_authorized=False))
  report=('R67 raw caller entry-only review passed. Ten continuous retainedrows/39bytes match R66; '
   'CALL994f15 E8d6e80901 has signedrel32 17426646 and target1a337f0. PreRAX1040/framefacts are local; '
   'postcallee RAX/RCX/RDX/RSP and flags remainunknown. No helper bytes or actual execution authorized.\n').encode('ascii')
  with (OUT/'report.md').open('xb') as f:f.write(report)
  own={O+n:pin((OUT/n).read_bytes()) for n in ('raw-seed-replay.json','findings.json','report.md')}
  own['work/review_r67_entry_20261016.py']=pin(Path(__file__).read_bytes())
  mp=write('manifest.json',dict(schema='EU4-R67-INDEPENDENT-ENTRY-SEED-MANIFEST/1',sealed=True,source_pins=before,local_pins=own,
   source_scope='10explicit source files, no recursive source/engine closure',findings=fp,operations=operations(),authority=false_authority()))
  print(json.dumps(dict(passed=True,findings=fp,manifest=mp,raw_replay=rp,counted_source_bytes=counted,peak=peak,all_shells_collected=True)))
 except Exception as exc:
  if not(OUT/'review-failure.json').exists():write('review-failure.json',dict(type=type(exc).__name__,detail=str(exc),reads=reads,peak=peak,author_sources_unchanged=True))
  raise
def check():
 m=json.loads(read(O+'manifest.json'))
 for path,pn in (m['source_pins']|m['local_pins']).items():read(path,pn)
 f=json.loads(read(O+'findings.json',m['local_pins'][O+'findings.json']))
 upper=f['resource_evidence']['total_explicit_upper_before_check']+sum(x['bytes'] for x in reads)
 assert upper<LIMIT+MANUAL
 vp=write('verification.json',dict(schema='EU4-R67-INDEPENDENT-ENTRY-VERIFICATION/1',passed=True,checked_pins=len(m['source_pins']|m['local_pins']),
  all_sources_current_equal=True,byte_verification_only=True,conservative_complete_stage_upper_bytes=upper,
  source_plus_manual_allowance_limit=LIMIT+MANUAL,own_peak_bytes=peak,operations=operations(),authority=false_authority(),all_shells_collected=True))
 print(json.dumps(dict(passed=True,verification=vp,checked_pins=len(m['source_pins']|m['local_pins']),conservative_complete_stage_upper_bytes=upper,peak=peak)))
if __name__=='__main__':check() if sys.argv[1:]==['--check'] else main()
