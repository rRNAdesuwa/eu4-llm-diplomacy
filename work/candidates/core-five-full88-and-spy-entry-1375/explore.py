"""Finite disk-only jump-table expansion; every newly decoded byte is retained."""
import hashlib,json,pathlib,struct,sys,tempfile
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import check_memory_budget,make_disassembler
SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
class DiskPE:
 def __init__(self):
  self.path=ROOT.parent/'eu4.exe';self.f=self.path.open('rb');h=hashlib.sha256()
  while b:=self.f.read(1024*1024):h.update(b)
  assert h.hexdigest()==SHA
  self.f.seek(0x3c);pe=struct.unpack('<I',self.f.read(4))[0];self.f.seek(pe);head=self.f.read(24);assert head[:4]==b'PE\0\0';n=struct.unpack_from('<H',head,6)[0];size=struct.unpack_from('<H',head,20)[0]
  assert n<=32 and size<=512
  optional=self.f.read(size);self.base=struct.unpack_from('<Q',optional,24)[0];self.sections=[]
  for _ in range(n):
   q=self.f.read(40);self.sections.append(struct.unpack_from('<IIII',q,8))
 def read(self,rva,size):
  assert 0<size<=8192
  for vs,va,rawsize,off in self.sections:
   if va<=rva and rva+size<=va+rawsize:self.f.seek(off+rva-va);b=self.f.read(size);assert len(b)==size;return b
  raise ValueError(hex(rva))
 def close(self):self.f.close()
def main():
 p=DiskPE()
 try:
  d=json.loads((ROOT/'work/candidates/curry-favors-contract-1375/report.json').read_bytes());known={int(x['rva'],16):x for x in d['functions']['0x12b860']['instructions']}
  table=p.read(0x12cde8,28);targets=list(struct.unpack('<7I',table));md,cs=make_disassembler(pathlib.Path(tempfile.gettempdir())/'eu4-native-analysis-deps');assert md
  out={};total=0
  for token in (0x2940,0x2941):
   entry=targets[token-0x293e];todo=[entry];rows={};joins=[]
   while todo:
    pc=todo.pop()
    while pc not in rows:
     if pc in known:joins.append(hex(pc));break
     assert 0x12bb86<=pc<0x12c09d
     ins=next(md.disasm(p.read(pc,15),pc),None);assert ins
     row={'rva':hex(pc),'bytes':ins.bytes.hex(),'instruction':ins.mnemonic+' '+ins.op_str};rows[pc]=row;total+=ins.size;assert total<=32768
     if ins.group(cs.CS_GRP_RET) or ins.mnemonic=='int3':break
     if ins.group(cs.CS_GRP_JUMP):
      assert ins.operands and ins.operands[0].type==cs.x86.X86_OP_IMM
      target=ins.operands[0].imm;todo.append(target)
      if ins.mnemonic=='jmp':break
     pc+=ins.size
   out[hex(token)]={'entry':hex(entry),'instructions':[rows[k] for k in sorted(rows)],'joins_existing_rows':sorted(set(joins)),'decoded_bytes':sum(len(bytes.fromhex(r['bytes'])) for r in rows.values())}
  record={'game_sha256':SHA,'table':{'rva':'0x12cde8','bytes':table.hex(),'base_token':'0x293e','targets':[hex(x) for x in targets]},'explorations':out,'all_exploration_decoded_bytes':total,'per_range_max_bytes':8192,'total_budget':32768,'peak_process_commit':check_memory_budget(),'new_decode_scope':'Only missing two direct jump-table branches; calls not followed; all branches/joins retained.'}
  with (HERE/'exploration-01.json').open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
  print(json.dumps({'targets':record['table']['targets'],'decoded_bytes':total,'peak_commit':record['peak_process_commit']}))
  for v in out.values():
   for r in v['instructions']:print(r['rva'],r['instruction'])
 finally:p.close()
if __name__=='__main__':main()
