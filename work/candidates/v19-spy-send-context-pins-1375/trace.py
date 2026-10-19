"""Exact seeks into the disk PE, using previously sealed instruction rows only."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
GAME_SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
PLAN='work/candidates/v19-spy-send-plan-1375/report.json'
ORIGIN='work/reports/native-single-player-origin-1375.json'
WORLD='work/candidates/war-dynasty-province-contracts-1375/report.json'
INPUTS=[
 'work/AGENTS.md',PLAN,ORIGIN,WORLD,
 'work/candidates/v19-spy-send-plan-r2-1375/review.json',
 'work/candidates/v19-spy-send-plan-r2-1375/contract.json',
 'work/review-results/v19-spy-send-plan-r2-native-inventory-20261008a/review.json',
 'work/review-results/v19-spy-send-plan-native-inventory-20261008a/static-check.json',
 'work/review-results/war-dynasty-province-action-catalog-20261008a/review.json',
 'docs/native-epoch-sp-closure-1375.md',
 'work/native/v17/pair-engine-1375.cpp',
]
# Inclusive first/last instruction RVAs. None selects the already bounded body.
SLICES=[
 ('world_context_path',WORLD,'0xbfe50',None,None),
 ('server_context_getter',ORIGIN,'0x811aa0',None,None),
 ('context_submit_owned_slot',PLAN,'0x14ca210',None,None),
 ('different_raw_pointer_abi_do_not_call',PLAN,'0x14ca2d0',None,None),
 ('transport_submit_entry',PLAN,'0x1580370',0x1580370,0x158039b),
 ('transport_original_command_delete',PLAN,'0x1580370',0x1580c4a,0x1580c5c),
 ('transport_receiver_queue_getter',PLAN,'0x8b0e0',None,None),
 ('receiver_context_queue_entry',PLAN,'0x14ca870',0x14ca870,0x14ca8b0),
 ('receiver_gate',PLAN,'0x14ca870',0x14cab2a,0x14cab35),
 ('receiver_callback_binding',PLAN,'0x14ca870',0x14caf25,0x14caf49),
 ('receiver_command_delete',PLAN,'0x14ca870',0x14cb130,0x14cb13b),
 ('callback_instrumentation_entry',PLAN,'0x14d4e70',None,None),
 ('callback_instrumentation_recursive',PLAN,'0x14d4e30',None,None),
 ('callback_function_invoker',PLAN,'0x10a0f20',None,None),
 ('command_callback_entry',PLAN,'0x14cea10',0x14cea10,0x14cea2c),
 ('command_callback_tail',PLAN,'0x14cea10',0x14ceaca,0x14ceae0),
 ('owned_command_destructor',PLAN,'0x4e7470',None,None),
]
SLOTS=[('server_context_getter',0x1cb8460,0x80,0x811aa0),
 ('transport_submit',0x1d96178,0x30,0x1580370),
 ('transport_queue',0x1d96178,0x48,0x8b0e0),
 ('command_destructor',0x1c814b0,0,0x4e7470),
 ('command_gate',0x1c814b0,0x40,0x4e8630),
 ('command_execute',0x1c814b0,0x48,0x4e7c50),
 ('callback_invoke',0x1d8c8b0,0x10,0x14cea10)]


def read(p,limit=8*1024*1024):
    with p.open('rb') as f:b=f.read(limit+1)
    assert len(b)<=limit;return b
def load(p):return json.loads(read(p))
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def rec(p):return dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=digest(p))
def enc(x):return (json.dumps(x,sort_keys=True,indent=2)+'\n').encode()


class PE:
    def __init__(self,path):
        self.f=path.open('rb');self.size=path.stat().st_size
        assert self.at(0,2)==b'MZ'
        nt=struct.unpack('<I',self.at(0x3c,4))[0];assert self.at(nt,4)==b'PE\0\0'
        machine,n,t,_,_,os,_=struct.unpack('<HHIIIHH',self.at(nt+4,20))
        assert machine==0x8664 and 0<n<32 and t==0x66fe6ab9
        assert struct.unpack('<H',self.at(nt+24,2))[0]==0x20b
        self.base=struct.unpack('<Q',self.at(nt+48,8))[0];assert self.base==0x140000000
        assert struct.unpack('<I',self.at(nt+24+56,4))[0]==0x25e0000
        self.sections=[]
        for i in range(n):
            b=self.at(nt+24+os+40*i,40)
            _,rva,size,offset=struct.unpack_from('<IIII',b,8)
            assert offset+size<=self.size;self.sections.append((rva,size,offset))
    def at(self,offset,size):
        assert 0<=size<=8192 and 0<=offset<=self.size-size
        self.f.seek(offset);b=self.f.read(size);assert len(b)==size;return b
    def rva(self,rva,size):
        matches=[(r,s,o) for r,s,o in self.sections if r<=rva and rva+size<=r+s]
        assert len(matches)==1;r,s,o=matches[0];return self.at(o+rva-r,size)


def render():
    assert digest(ROOT.parent/'eu4.exe')==GAME_SHA
    inputs=[rec(ROOT/p) for p in INPUTS]
    assert sum(r['bytes'] for r in inputs)<32*1024*1024
    assert digest(ROOT/PLAN)=='107dd35cf80f1dfb589244dfdae57ffa017769ceba3da908fb5a79e35d9da659'
    assert digest(ROOT/INPUTS[4])=='0f5b2cbccd17ab0e52494c7177317baadefc6f2b2086f001419950e16e87a0cc'
    docs={p:load(ROOT/p) for p in (PLAN,ORIGIN,WORLD)}
    pe=PE(ROOT.parent/'eu4.exe');code=[];slots=[]
    try:
        for name,source,function,first,last in SLICES:
            body=docs[source]['functions'][function]['instructions']
            if first is None:rows=body
            else:
                first_index=next(i for i,r in enumerate(body) if int(r['rva'],16)==first)
                last_index=next(i for i,r in enumerate(body) if int(r['rva'],16)==last)
                rows=body[first_index:last_index+1]
            start=int(rows[0]['rva'],16);next_rva=start;blob=b''
            for row in rows:
                b=bytes.fromhex(row['bytes']);assert int(row['rva'],16)==next_rva
                assert pe.rva(next_rva,len(b))==b;blob+=b;next_rva+=len(b)
            assert 0<len(blob)<=180
            code.append(dict(name=name,rva=hex(start),end=hex(next_rva),bytes=blob.hex(),
                byte_count=len(blob),source=source,source_pointer='/functions/'+function+'/instructions',
                first_rva=rows[0]['rva'],last_rva=rows[-1]['rva'],instructions=rows,
                pin_only_not_hook_patch_or_unwind_contract=True))
        for name,vt,offset,target in SLOTS:
            b=pe.rva(vt+offset,8);assert struct.unpack('<Q',b)[0]==pe.base+target
            slots.append(dict(name=name,vtable_rva=hex(vt),slot=hex(offset),rva=hex(vt+offset),
                              expected_target_rva=hex(target),bytes=b.hex()))
    finally:pe.f.close()
    byname={r['name']:r for r in code}
    assert byname['context_submit_owned_slot']['byte_count']==180
    assert byname['context_submit_owned_slot']['bytes'][0x1d*2:0x24*2]=='48c70200000000'
    assert 0x2a0-0x1a0-0x78==0x50+0x38
    report=dict(schema=1,purpose='v19_context_static_pins_and_private_stamp_only',game_sha256=GAME_SHA,
        image=dict(machine='0x8664',timestamp='0x66fe6ab9',size_of_image='0x25e0000'),
        inputs=inputs,code_pins=code,slot_pins=slots,
        facts=dict(selected_signature='bool __fastcall(void* context, void** owned_command_slot)',
          selected_entry='0x14ca210',different_abi_not_selected='0x14ca2d0(context, command*)',
          slot_read='0x14ca22a',slot_preclear='0x14ca22d',transport_nonnull_test='0x14ca234',
          readiness_byte_tests=['0x14ca244','0x14ca24a'],transport_virtual_call='0x14ca299',
          normal_true_assignment='0x14ca29c',normal_bool_return='0x14ca2b1',
          null_command_is_not_a_valid_send=True,readiness_required_by_restricted_profile=True,
          command_predicate_bypass_not_used=['command virtual+0x80','command virtual+0x58'],
          context_metadata_native_writes=[{'read_offset':'0x8c','read_width':4,'command_write_offset':'0x38','write_width':4},
            {'read_offset':'0x68','read_width':4,'command_write_offset':'0x48','write_width':2,'rule':'native signed compare and WORD selection, not reproduced or host-written'}],
          context_vtable_identity='not_claimed',queue_getter_returns_transport_offset='0xc8',
          later_frame_not_queue_settlement=True,receiver_callback_stack_equation='rbp=rsp+0x100; rbp-0x78 == rsp+0x50+0x38'),
        limits=dict(new_decode_bytes=0,source_instruction_reuse_only=True,max_pin_bytes=max(r['byte_count'] for r in code),
                    selected_instruction_rows=sum(len(r['instructions']) for r in code),selected_bytes=sum(r['byte_count'] for r in code),
                    no_whole_binary_buffer=True,no_process_access=True),
        unsupported=['context lifetime/ABA exclusion','strict SP','world epoch','all unwind paths','native owner thread proof',
                     'queue scheduling/settlement','effect causality','automatic retry','actual sender/resolver'],
        runtime_verified=False,production_ready=False)
    header=['// Generated exact-build byte/data constants only. No native callable, resolver or hook.',
      '// Pins do not prove SP, world epoch, lifetime, unwind safety or permission to send.',
      '#pragma once','#include <cstdint>','namespace eu4_spy19_sender {',
      'struct CodePin { std::uintptr_t rva; const char* hex; };',
      'struct SlotPin { std::uintptr_t rva, target; };',
      'inline constexpr CodePin kCodePins[] = {']
    header += ['    { '+r['rva']+', "'+r['bytes']+'" }, // '+r['name'] for r in code]
    header += ['};','inline constexpr SlotPin kSlotPins[] = {']
    header += ['    { '+r['rva']+', '+r['expected_target_rva']+' }, // '+r['name'] for r in slots]
    header += ['};','inline constexpr std::uintptr_t kContextSubmit = 0x14ca210;',
      'inline constexpr std::uintptr_t kGameGlobal = 0x233fe78;',
      'inline constexpr std::uintptr_t kGameServerOffset = 0x1e00;',
      'inline constexpr std::uintptr_t kServerHolderOffset = 0x330;',
      'inline constexpr std::uintptr_t kHolderContextOffset = 0x370;',
      'inline constexpr std::uintptr_t kContextTransportOffset = 0x58;',
      'inline constexpr std::uintptr_t kReady55Offset = 0x55, kReady80dOffset = 0x80d;',
      'inline constexpr unsigned kReadyWidth = 1;',
      'inline constexpr std::uintptr_t kServerVtable = 0x1cb8460, kTransportVtable = 0x1d96178;',
      '} // namespace eu4_spy19_sender','']
    return enc(report),'\n'.join(header).encode()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');a=parser.parse_args()
    report,header=render()
    for name,b in [('report.json',report),('sender-pins.h',header)]:
        if a.check:assert read(HERE/name)==b,name
        else:
            with (HERE/name).open('xb') as f:f.write(b)
    print(json.dumps(dict(passed=True,check=a.check,new_decode_bytes=0,
                         report=rec(HERE/'report.json'),header=rec(HERE/'sender-pins.h'))))
