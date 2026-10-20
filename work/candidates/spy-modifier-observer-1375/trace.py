"""Exact-build bounded disk trace. No process access and no recursive decoding."""
import argparse,hashlib,json,struct,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,make_disassembler,check_memory_budget
from map_diplomacy_fields import bounded_cfg
from trace_change_subject_type import rows
EXE_SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
OLD='work/candidates/spy-action-contracts-1375/report.json'
OLD_SHA='274221df57719404edfcacd7451ebc28c678369dab9d4377e6201be5db734774'
ENTRIES=(0x8f58f0,0xb354c0,0x3b9fa0,0x3ba040,0x8ed850,0x93d750,0x2154c8,0x8f42b0,0x8eef60,0x8f440,0x8f450)
FAMILIES={
 'corrupt_officials':(0x160,0x86,0x233fa8c,0x233fae0,1,'corrupt_officials',0x1cc7ac8),
 'sabotage_reputation':(0x150,0x80,0x233fa88,0x233fae4,1,'reputation_sabotaged',0x1cc7a80),
 'sow_discontent':(0x140,0x83,0x233fa7c,0x233faf8,1,'discontent_sowed',0x1cc7a98),
 'slander_merchants':(0x170,0x81,0x233fa90,0x233faf0,30,'merchants_slandered',0x1cc7d60),
 'sabotage_recruitment':(0x180,0x82,0x233fa94,0x233faf4,30,'recruitment_sabotaged',0x1cc7ab0),
}
def bounded(path,limit=10*1024*1024):
 with Path(path).open('rb') as f:raw=f.read(limit+1)
 if len(raw)>limit:raise ValueError('input bound')
 return raw
def render():
 oldraw=bounded(ROOT/OLD);assert hashlib.sha256(oldraw).hexdigest()==OLD_SHA
 old=json.loads(oldraw);pe=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(pe.data).hexdigest()==EXE_SHA
 md,version=make_disassembler(Path(tempfile.gettempdir())/'eu4-native-analysis-deps')
 functions={};total=0
 for entry in ENTRIES:
  ins,edges=bounded_cfg(pe,md,entry,window=0x2000,max_instructions=2200)
  n=sum(i.size for i in ins);total+=n;assert total<=16384
  functions[hex(entry)]={'instructions':rows(pe,ins),'edges':edges,'decoded_bytes':n}
 imported={}
 for entry in ('0x4ea610','0xb357b0','0x3283c0','0x328c70','0x582730','0x4ea820'):
  data=old['functions'][entry]['instructions']
  for row in data:assert pe.bytes_at(int(row['rva'],16),len(bytes.fromhex(row['bytes'])))==bytes.fromhex(row['bytes'])
  imported[entry]={'source':OLD,'json_pointer':'/functions/'+entry+'/instructions','instructions':data}
 strings=[]
 for value in FAMILIES.values():
  raw=value[5].encode()+b'\0';assert pe.bytes_at(value[6],len(raw))==raw
  strings.append({'rva':hex(value[6]),'bytes':raw.hex(),'text':value[5]})
 # +90 of the shared empty sentinel is false. Do not mistake it for a loaded definition.
 assert pe.u64(pe.to_offset(0x1c48378+0x90))==pe.base+0x8f450
 anchors=[0x8f42ec,0x8f42ef,0x8ef020,0x8ef027,0x8ef02c,0x8ef032,0x8ef08e,
          0x3b9fa0,0x93d750,0x93d78c,0x8f440,0x8f442,0x8f450,0x8f452]
 lookup={row['rva']:row for f in functions.values() for row in f['instructions']}
 instruction_pins=[lookup[hex(x)] for x in anchors]
 for e,rs in {'0x3283c0':(0x3283fe,0x328413,0x328416,0x32841a,0x328422,0x328430),
              '0xb357b0':(0xb357c5,0xb357cc,0xb357ff,0xb3581a,0xb3581e),
              '0x4ea610':(0x4ea655,0x4ea65c,0x4ea661,0x4ea665,0x4ea683,0x4ea687,0x4ea6a4,0x4ea6ab,0x4ea6ca,0x4ea7d8)}.items():
  by={x['rva']:x for x in imported[e]['instructions']}
  instruction_pins.extend(by[hex(x)] for x in rs)
 at=pe.u32(0x3c);opt=at+24
 return {'schema_version':1,'exe_sha256':EXE_SHA,'prior_report_sha256':OLD_SHA,
  'pe':{'timestamp':pe.u32(at+8),'image_size':pe.u32(opt+56),'machine':pe.u16(at+4)},
  'sections':pe.sections,'functions':functions,'imported':imported,'strings':strings,
  'families':{k:dict(zip(('registry_slot','capability_offset','base_cost_rva','duration_rva','duration_to_days','definition_key','key_rva'),v)) for k,v in FAMILIES.items()},
  'instruction_pins':instruction_pins,'bounds':{'new_decoded_bytes':total,'max_new_decoded_bytes':16384,'max_function_window':8192,'max_function_instructions':2200},
  'facts':[
   {'id':'cached_registry','source':'8ed850 names ->8f42b0 ->8eef60','claim':'Slots initially share2458c68 with initialized flag0; named lookup writes pointer and flag1 even if lookup falls back to empty sentinel. Require flag1 AND pointer!=sentinel AND bounded exact name; pointer alone is insufficient.'},
   {'id':'definition_name','source':'8ef020..8ef03a','claim':'Definition+158 is String32, QWORD length+10/capacity+18, SSO capacity<16; lookup compares exact bytes. The RO reader never calls lookup or virtual90. Sentinel vt1c48378/+90 returns false; recognized loaded registry objects require a readonly-module vtable with exact constant-true90=8f440, without claiming a concrete dynamic subtype.'},
   {'id':'cost_subset','source':'4ea610 and93d750','claim':'country+28c0 getter can enter thread/lazy diagnostics. For DWORD country+28c8 !=1 its normal return is country+28c8; caller uses aggregate+8. Sparse flag0 data+58/count+64 scans id261. Global2358080+e4a0 nonnull executes unreviewed virtual8. Observer only computes a static arithmetic candidate for nonlazy sparse aggregate and null transform; all other cases remain unknown.'},
   {'id':'cost_direction','source':'3b9fa0/3ba040','claim':'Target with overlord+18f0 top byte0 uses literal target handle. Subject redirect conditions are not fully modeled; this candidate refuses subject targets rather than borrowing a network row.'},
   {'id':'observer_not_legality','source':OLD,'claim':'Capability byte is one full-preview condition, not the complete gate. Country modifier does not store initiating actor; selected same-day differences are correlation, not request causality. Positive only; false is not cancellation.'}],
  'process_accessed':False,'runtime_verified':False,'native_call_authorized':False,'production_ready':False}
def main():
 a=argparse.ArgumentParser();a.add_argument('--check',action='store_true');args=a.parse_args()
 result=render();raw=(json.dumps(result,indent=2,ensure_ascii=False)+'\n').encode()
 if args.check:assert bounded(HERE/'report.json')==raw
 else:
  with (HERE/'report.json').open('xb') as f:f.write(raw)
 print(json.dumps({'check':args.check,'sha256':hashlib.sha256(raw).hexdigest(),'decoded_bytes':result['bounds']['new_decoded_bytes'],'peak_bytes':check_memory_budget()}))
if __name__=='__main__':main()
