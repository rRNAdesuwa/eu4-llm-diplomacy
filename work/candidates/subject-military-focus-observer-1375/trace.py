"""Disk-only bounded static evidence for a fixed FRA/NAV raw RO producer."""
import argparse, hashlib, json, os, struct, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,make_disassembler,check_memory_budget
from map_diplomacy_fields import bounded_cfg
SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
SOURCES={
 'work/candidates/subject-military-focus-contract-1375/report.json':'7be628d0e30f1c2e0d92b89d40b3757f310659865dd3d49427114e5a64cedffb',
 'work/reports/native-pair-cancel-1375.json':'54dc047d85fe8c06528d5fb3824a1928f56fac2c4bbf24c26e205bcfb08e0df3',
 'work/reports/native-pair-effects-1375.json':'b67e9e3ec3d333ad5603c9bcb7a70d614bab1107f283c6f01d99e7c744730ae0'}

def bounded(path,limit=8*1024*1024):
 with path.open('rb') as f:b=f.read(limit+1)
 if len(b)>limit:raise ValueError('bounded source')
 return b

def generate():
 p=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(p.data).hexdigest()==SHA
 md,cs=make_disassembler(Path(os.environ.get('TEMP',''))/'eu4-native-analysis-deps')
 reports={}
 for name,h in SOURCES.items():
  b=bounded(ROOT/name);assert hashlib.sha256(b).hexdigest()==h;reports[name]=json.loads(b)
 funcs={}
 for name,entries in [(list(SOURCES)[0],('0x3d79f0','0xf4f9e0','0x2b28c0','0x2b2b30','0xb1fca1','0xb2036b','0x975360','0x9753f0')),
                       (list(SOURCES)[1],('0xb231f0','0xb23ab0','0xb23df0','0xb238b0','0xa62b40','0x95110')),
                       (list(SOURCES)[2],('0xa69970','0x28bd00'))]:
  for entry in entries:
   old=reports[name]['functions'][entry]
   funcs[entry]={'kind':'reused','source':name,'json_pointer':'/functions/'+entry,'instructions':old['instructions']}
 old=reports[list(SOURCES)[2]]['functions']['0x4e5630']['instructions']
 funcs['0x4e5ced']={'kind':'reused_exact_slice','source':list(SOURCES)[2],'json_pointer':'/functions/0x4e5630/instructions','range':['0x4e5ced','0x4e5db0'],'instructions':[i for i in old if 0x4e5ced<=int(i['rva'],16)<0x4e5db0]}
 new_total=0
 for entry in (0x1fd1a0,):
  ins,edges=bounded_cfg(p,md,entry,window=8192,max_instructions=2000)
  n=sum(i.size for i in ins);new_total+=n;assert n<=8192 and new_total<=32768
  funcs[hex(entry)]={'kind':'new_bounded_cfg','instructions':[{'rva':hex(i.address),'bytes':i.bytes.hex(),'instruction':(i.mnemonic+' '+i.op_str).strip()} for i in ins],'edges':edges,'decoded_bytes':n}
 anchors={}
 for f in funcs.values():
  for row in f['instructions']:
   b=bytes.fromhex(row['bytes']);assert p.bytes_at(int(row['rva'],16),len(b))==b;anchors[row['rva']]=row
 data=[]
 for rva,size,label in [(0x1ce7488,0x28,'definition vtable through parser+20'),(0x1c81758,0x40,'dependency vtable first8')]:
  data.append({'rva':hex(rva),'bytes':p.bytes_at(rva,size).hex(),'meaning':label})
 # Selected instruction prefixes, all copied from already-verified anchors.
 wanted=(0x3d79f0,0x3d7a09,0x3d7a1e,0x3d7a25,0x3d7a51,0xf4fa4f,0xf4fa6d,0xf4fa81,
         0xb2321c,0xb23413,0xb2341c,0xb23420,0xb23423,0xb23427,0xb23435,0xb23439,
         0xb2344f,0xb23453,0xb23474,0xb23479,0xb237ea,0xb237ee,0xb237f4,0xb237f7,
         0xb23af0,0xb23af8,0xb23e44,0xb23e58,0xb1fca1,0xb2036b,0x2b28e7,0xa69970,0xa6997c,0xa69983,
         0x1fd1ad,0x1fd1b4,0x1fd1b8,0x1fd1c2,0x1fd1c6,0x1fd1eb,0x1fd200,0x1fd209,0x1fd234,
         0x4e5ced,0x4e5cfe,0x4e5d4b,0x4e5d52,0x4e5d55,0x4e5da2,0x4e5da6,0x4e5daa,
         0xb235b5,0xb235e5,0xb23784)
 pins=[anchors[hex(a)] for a in wanted]
 at=p.u32(0x3c);opt=at+24
 return {'schema_version':1,'exe_sha256':SHA,'sources':SOURCES,'functions':funcs,'instruction_pins':pins,'data_pins':data,'sections':p.sections,
  'pe':{'timestamp':p.u32(at+8),'image_size':p.u32(opt+56),'machine':p.u16(at+4)},
  'bounds':{'new_decoded_bytes':new_total,'new_decode_limit':32768,'each_function_window':8192,'unique_instruction_anchors':len(anchors),'peak_bytes':check_memory_budget()},
  'facts':[
   {'id':'registry_vector','evidence':['0xb23413','0xb2341c','0xb23420','0xb23474','0xb237ea','0xb237f4','0xb237f7'],'claim':'Global233ffd8 registry+40/+48/+50 is definition pointer vector. Newly appended definition+30 is vector index; definition+38 is itself. These are RO cross-checks, not a registry constructor.'},
   {'id':'subject_graph','evidence':['0xf4fa4f','0xf4fa81','0x3d7a09','0x3d7a1e','0x3d7a51'],'claim':'Actor subject vector contains full handles. Country1510 opposite-slot48 record points to index owner; dependency entries stride16 at owner128/count134; selected object+40 gives definition.'},
   {'id':'name_hash_query','evidence':['0xb23df0','0x1fd1ad','0x1fd1c2','0x1fd1eb','0x1fd200','0x1fd234','0xb23e58'],'claim':'Registry name lookup computes 32-bit FNV-1 (multiply then XOR), selects bucket(hash&registry30)*16 from registry18. Bucket+8 is last; traversal follows node+8 backward to bucket first. Node+10 String32 compared exactly; returned node+30 is definition. RO reconstructs only the selected bucket, verifies reciprocal links, count/unique names/vector membership, never invokes helper.'},
   {'id':'type_relation','evidence':['0x4e5ced','0x4e5cfe','0x4e5d4b','0x4e5d52','0x4e5d55','0x4e5da2','0x4e5da6','0x4e5daa'],'claim':'Dependency allocation90 has marker165, vtable1c81758, complete role handles+10/+18, date+20, definition+40. Unknown vtable is rejected before derived reads.'},
   {'id':'no_entitlement_inference','evidence':['0x975360','0x9753f0'],'claim':'Positive enum availability uses globals/TLS/lazy paths. Producer never queries them and entitlement is unsupported for all calls. Focus0 static leaf does not prove complete authorization.'}],
  'runtime_verified':False,'native_call_authorized':False,'production_ready':False}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args()
 report=generate();report['bounds'].pop('peak_bytes');b=(json.dumps(report,indent=2,ensure_ascii=False)+'\n').encode()
 if a.check:assert bounded(HERE/'report.json')==b
 else:
  with (HERE/'report.json').open('xb') as f:f.write(b)
 print(json.dumps({'check':a.check,'sha256':hashlib.sha256(b).hexdigest(),'new_decoded_bytes':report['bounds']['new_decoded_bytes'],'peak_bytes':check_memory_budget()}))
if __name__=='__main__':main()
