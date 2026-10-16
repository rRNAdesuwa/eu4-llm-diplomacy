"""Disk-only bounded effect trace for five newly selected favor actions."""
import hashlib,json,struct,tempfile
from pathlib import Path
from discover_diplomacy import PE,make_disassembler,check_memory_budget
from map_diplomacy_fields import SHA,bounded_cfg
from trace_change_subject_type import rows
ROOT=Path(__file__).resolve().parents[1]
pe=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(pe.data).hexdigest()==SHA
md,_=make_disassembler(Path(tempfile.gettempdir())/'eu4-native-analysis-deps')
vts={'gold':0x1c80980,'men':0x1c80ff0,'sailors':0x1c81250,'trust':0x1c80c60,'war_prep':0x1c80ec0}
report={'game_sha256':SHA,'disk_only':True,'functions':{},'vtable_effects':{}}
for name,vt in vts.items():
 entry=struct.unpack('<Q',pe.bytes_at(vt+0x48,8))[0]-pe.base
 code,edges=bounded_cfg(pe,md,entry,window=0x1800,max_instructions=2000)
 report['vtable_effects'][name]=hex(entry)
 report['functions'][hex(entry)]={'instructions':rows(pe,code),'edges':edges}
 check_memory_budget()
out=ROOT/'work/reports/native-pair29-favor-effects-1375.json'
with out.open('x',encoding='utf8') as f:json.dump(report,f,indent=2);f.write('\n')
for name,entry in report['vtable_effects'].items():
 print(name,entry)
 for r in report['functions'][entry]['instructions']:
  if r['instruction'].startswith('call') or any(s in r['instruction'] for s in ('0x1510','0xe00','0x40]','0x44]')):print(r['rva'],r['instruction'])
