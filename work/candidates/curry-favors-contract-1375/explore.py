"""Bounded disk-only exploration; every decoded function retained and budgeted."""
import argparse,hashlib,json,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,make_disassembler,check_memory_budget
from map_diplomacy_fields import bounded_cfg
from trace_change_subject_type import rows
SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
def main():
 p=argparse.ArgumentParser();p.add_argument('entries',nargs='+');a=p.parse_args()
 existing={}
 for f in sorted(HERE.glob('decode-*.json')):
  d=json.loads(f.read_text());existing.update(d['functions'])
 pe=PE(ROOT.parent/'eu4.exe')
 if hashlib.sha256(pe.data).hexdigest()!=SHA:raise ValueError('EXE SHA')
 md,version=make_disassembler(Path(tempfile.gettempdir())/'eu4-native-analysis-deps')
 total=sum(x['decoded_bytes'] for x in existing.values());out={}
 for value in a.entries:
  entry=int(value,16);key=hex(entry)
  if key in existing or key in out:raise ValueError('already decoded '+key)
  ins,edges=bounded_cfg(pe,md,entry,window=8192,max_instructions=2500)
  n=sum(i.size for i in ins);total+=n
  if total>65536:raise ValueError('64KiB cumulative budget exceeded')
  out[key]={'instructions':rows(pe,ins),'edges':edges,'decoded_bytes':n,'pdata':pe.function(entry)}
 target=HERE/('decode-%02d.json'%(len(list(HERE.glob('decode-*.json')))+1))
 raw=json.dumps({'game_sha256':SHA,'functions':out,'cumulative_new_decoded_bytes':total,'window':8192,'decoder_version':version.__version__},indent=2)
 with target.open('x') as f:f.write(raw)
 print(json.dumps({'path':target.name,'new':{k:v['decoded_bytes'] for k,v in out.items()},'total':total,'memory':check_memory_budget()}))
if __name__=='__main__':main()
