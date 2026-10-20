"""Disk-only byte/pin generation for the raw RO producer; no disassembly."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE='work/candidates/peace-constructor-preconditions-ro-1375'
INPUTS={
 BASE+'/prepare.py':'90961b4cf899c8bf160d51baec324896e9c202d9470defb61b434095a24035b4',
 BASE+'/static-contract.json':'1a34f841be89574e5b9cba1aaf7edae3ea87bcf499cc954e4796e4ef70121c37',
 BASE+'/observer.py':'0cba6bc03304bb99db729c299631d34329b28ed38b76ca0443fbf09b3c17cc40',
 BASE+'/test_observer.py':'a81b544cf758896b6c268697c2c2b169ed7b1d8bbb844adea26505a98314df48',
 BASE+'/README.md':'8c809a2fedd503140f62b91dce56443cb07f8c240804df7b6a1fc71f0e471c39',
 'work/probe_diplomacy_current.py':'a5a0b775a701466cf5f4c85db671e37f81c165daf5fddd2080b71ed6f147bb38',
 'work/probe_pair_effects_1375.py':'e5ae9d341c57e7cc79169b708c1d37ccf79ac3d09e88c953e1d4bcbb3ab1cf67',
 'bridge/native_build.py':'2f8f7f1781f10084ed85cae59f876080a9cd0efcf9810e1fc394561682048925',
 'work/local_config.py':'55a3bce5a2bf98f83c58e27884699c780456ea40b84d11bcac5fe78082262001',
 'work/reports/native-world-epoch-1375.json':'d4ee6ad5c8a3577dff2209ec5884978862552c700338e07ef669bd866a30de05',
}


def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(262144),b''):h.update(block)
 return h.hexdigest()


def render():
 for path,digest in INPUTS.items():
  if sha(ROOT/path)!=digest:raise ValueError('Pinned input differs: '+path)
 spec=importlib.util.spec_from_file_location('fixed_prior_peace_ro_prepare',ROOT/BASE/'prepare.py')
 prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
 contract=prior.render()
 if (json.dumps(contract,indent=2,sort_keys=True)+'\n').encode()!=(ROOT/BASE/'static-contract.json').read_bytes():raise ValueError('Prior report changed')
 pe=prior.PE(ROOT.parent/'eu4.exe')
 try:
  nt=struct.unpack_from('<I',pe.read(0,64),60)[0];coff=pe.read(nt,24)
  count=struct.unpack_from('<H',coff,6)[0];size=struct.unpack_from('<H',coff,20)[0]
  raw=pe.read(nt+24+size,count*40);sections=[]
  for i in range(count):
   off=i*40;vsize,rva,rawsize,rawptr=struct.unpack_from('<IIII',raw,off+8)
   sections.append({'name':raw[off:off+8].rstrip(b'\0').decode(),'rva':rva,'size':max(vsize,rawsize),
                    'flags':struct.unpack_from('<I',raw,off+36)[0]})
  anchors={row['rva']:row for group in contract['anchors'].values() for row in group}
  epoch=json.loads((ROOT/'work/reports/native-world-epoch-1375.json').read_bytes())
  rows=epoch['functions']['0x286250']['instructions']
  extra=[]
  for i,row in enumerate(rows):
   if int(row['rva'],16) in (0x286439,0x286440,0x286447,0x28644d,0x28645e):
    item=dict(row,source='work/reports/native-world-epoch-1375.json',json_pointer=f'/functions/0x286250/instructions/{i}')
    assert pe.at(int(row['rva'],16),len(bytes.fromhex(row['bytes']))).hex()==row['bytes']
    anchors[row['rva']]=item;extra.append(item)
  return {'schema_version':1,'purpose':'peace_raw_ro_producer_fixed_inputs','exe_sha256':prior.EXE_SHA,
   'inputs':INPUTS,'prior_static_contract_sha256':INPUTS[BASE+'/static-contract.json'],'pe':contract['pe'],'sections':sections,
   'instruction_pins':[{'rva':row['rva'],'bytes':row['bytes']} for _,row in sorted(anchors.items(),key=lambda x:int(x[0],16))],
   'take_colony_vtable':contract['take_colony_vtable'],'extra_anchors':extra,
   'count_layout_scope':'CountryDatabase +110 is the pointer-vector wrapper: +118 array and +124 signed count, cleared together by286250. Per-slot full identity must additionally match country+20.',
   'tls_capture_supported':False,'thread_query_api_added':False,'new_decoded_bytes':0,
   'parameter_constructor_authorized':False,'runtime_verified':False}
 finally:pe.stream.close()


def main():
 parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
 raw=(json.dumps(render(),indent=2,sort_keys=True)+'\n').encode();path=HERE/'pins.json'
 if args.check:
  if path.read_bytes()!=raw:raise ValueError('pins.json differs')
 else:
  with path.open('xb') as f:f.write(raw)
 print(json.dumps({'check':args.check,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'new_decoded_bytes':0,'game_accessed':False}))


if __name__=='__main__':main()
