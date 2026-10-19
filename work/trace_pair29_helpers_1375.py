"""Bounded disk-only resource and war preparation helpers."""
import hashlib,json,tempfile
from pathlib import Path
from discover_diplomacy import PE,make_disassembler,check_memory_budget
from map_diplomacy_fields import SHA,bounded_cfg
from trace_change_subject_type import rows
ROOT=Path(__file__).resolve().parents[1]
pe=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(pe.data).hexdigest()==SHA
md,_=make_disassembler(Path(tempfile.gettempdir())/'eu4-native-analysis-deps')
report={'game_sha256':SHA,'disk_only':True,'functions':{}}
for entry in (0x34cf10,0x34de70,0x3e1ad0,0x4f6660,0x4f8a30):
 code,edges=bounded_cfg(pe,md,entry,window=0x1200,max_instructions=1500)
 report['functions'][hex(entry)]={'instructions':rows(pe,code),'edges':edges}
 check_memory_budget()
out=ROOT/'work/reports/native-pair29-favor-helpers-1375.json'
with out.open('x',encoding='utf8') as f:json.dump(report,f,indent=2);f.write('\n')
for entry,f in report['functions'].items():
 print(entry)
 for r in f['instructions']:
  if any(s in r['instruction'] for s in ('dword ptr','byte ptr','call','ret')):print(r['rva'],r['instruction'])
