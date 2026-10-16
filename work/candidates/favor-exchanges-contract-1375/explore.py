"""Explicit disk-only CFG exploration, never recursive through calls."""
import argparse,hashlib,json,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,make_disassembler,check_memory_budget
from map_diplomacy_fields import bounded_cfg
from trace_change_subject_type import rows
SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('entries',nargs='+');a=p.parse_args()
 assert '/' not in a.output and '\\' not in a.output and a.output.startswith('exploration-') and a.output.endswith('.json')
 previous={};total=0
 for path in HERE.glob('exploration-*.json'):
  old=json.loads(path.read_bytes())
  total+=old.get('extra_failed_attempt_bytes',0)
  for k,f in old['functions'].items():assert k not in previous;previous[k]=f;total+=f['decoded_bytes']
 pe=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(pe.data).hexdigest()==SHA
 md,_=make_disassembler(Path(tempfile.gettempdir())/'eu4-native-analysis-deps');functions={}
 for entry in a.entries:
  rva=int(entry,16);key=hex(rva);assert key not in previous and key not in functions
  ins,edges=bounded_cfg(pe,md,rva,window=8192,max_instructions=2500)
  count=sum(i.size for i in ins);total+=count
  assert count<=8192 and total<=49152
  functions[key]={'instructions':rows(pe,ins),'edges':edges,'decoded_bytes':count}
 result={'game_sha256':SHA,'functions':functions,'new_this_file':sum(f['decoded_bytes'] for f in functions.values()),'cumulative_new_bytes':total,'window':8192,'max_new_bytes':49152,'all_exploration_retained':True,'committed_bytes':check_memory_budget(),'process_accessed':False}
 with (HERE/a.output).open('x',encoding='utf8') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps({k:v for k,v in result.items() if k!='functions'}))
if __name__=='__main__':main()
