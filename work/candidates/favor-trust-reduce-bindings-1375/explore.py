"""Explicit bounded disk-only CFG or linear slices, including rejected exploration."""
import argparse,hashlib,json,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,make_disassembler,check_memory_budget
from map_diplomacy_fields import bounded_cfg
from trace_change_subject_type import rows
SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--linear',type=lambda x:int(x,0));p.add_argument('entries',nargs='+');a=p.parse_args()
 assert '/' not in a.output and '\\' not in a.output and a.output.startswith('exploration-') and a.output.endswith('.json')
 total=0;previous=set()
 for path in HERE.glob('exploration-*.json'):
  old=json.loads(path.read_bytes());total+=old['new_this_file'];previous|=set(old['functions'])
 pe=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(pe.data).hexdigest()==SHA
 md,_=make_disassembler(Path(tempfile.gettempdir())/'eu4-native-analysis-deps');assert md is not None
 functions={}
 for entry in a.entries:
  rva=int(entry,16);key=hex(rva);assert key not in previous and key not in functions
  if a.linear is not None:
   assert 0<a.linear<=8192;ins=list(md.disasm(pe.bytes_at(rva,a.linear),rva));edges=[];mode='explicit aligned linear slice'
  else:
   ins,edges=bounded_cfg(pe,md,rva,window=8192,max_instructions=2500);mode='bounded CFG no call recursion'
  count=sum(i.size for i in ins);total+=count;assert count<=8192 and total<=131072
  functions[key]={'instructions':rows(pe,ins),'edges':edges,'decoded_bytes':count,'mode':mode,'requested_window':a.linear or 8192}
 result={'game_sha256':SHA,'functions':functions,'new_this_file':sum(f['decoded_bytes'] for f in functions.values()),'cumulative_new_bytes':total,'window_max':8192,'max_new_bytes':131072,'all_exploration_retained':True,'committed_bytes':check_memory_budget(),'process_accessed':False}
 with (HERE/a.output).open('x',encoding='utf8') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps({k:v for k,v in result.items() if k!='functions'}))
if __name__=='__main__':main()
