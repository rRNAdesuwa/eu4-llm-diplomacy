"""Bounded disk-only C01 dossier. Does not emit patches or load any DLL."""
import argparse
import hashlib
import json
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE, make_disassembler, check_memory_budget

SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
HEADER=Path('C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/MSVC/14.44.35207/include/ehdata4_export.h')
LENGTH=(1,2,1,3,1,2,1,4,1,2,1,3,1,2,1,5)
REG=('rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi','r8','r9','r10','r11','r12','r13','r14','r15')

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def decode_unsigned(data):
    if not data:raise ValueError('truncated compressed integer')
    n=LENGTH[data[0]&15]
    if len(data)<n:raise ValueError('truncated compressed integer')
    return int.from_bytes(data[:n],'little')>>(n if n<5 else 8),n

class Reader:
    def __init__(self,pe):self.pe=pe;self.reads=[]
    def raw(self,r,n):
        if n<1 or n>8192:raise ValueError('read bound')
        b=self.pe.bytes_at(r,n)
        if len(b)!=n:raise ValueError('unmapped metadata')
        self.reads.append((r,n));return b
    def u32(self,r):return int.from_bytes(self.raw(r,4),'little')
    def uint(self,r):
        n=LENGTH[self.raw(r,1)[0]&15]
        v,n=decode_unsigned(self.raw(r,n));return v,r+n

def unwind(rd,fn):
    begin,end,r=fn;h=rd.raw(r,4);v,prolog,count,frame=h
    assert v&7==1 and count<=64
    flags=v>>3;body=rd.raw(r+4,((count+1)&~1)*2);i=0;codes=[]
    while i<count:
        off,op=body[2*i:2*i+2];info=op>>4;op&=15;slots=1
        row={'code_offset':off,'operation':op,'op_info':info}
        if op==0:row.update(name='PUSH_NONVOL',register=REG[info],stack_delta=-8)
        elif op==1:
            assert info in (0,1);slots=2 if info==0 else 3
            size=int.from_bytes(body[2*i+2:2*(i+slots)],'little')*(8 if info==0 else 1)
            row.update(name='ALLOC_LARGE',size=size,stack_delta=-size)
        elif op==2:row.update(name='ALLOC_SMALL',size=info*8+8,stack_delta=-(info*8+8))
        elif op==3:row.update(name='SET_FPREG',register=REG[frame&15],frame_offset=(frame>>4)*16)
        elif op in (4,5,8,9):
            slots=2 if op in (4,8) else 3
            value=int.from_bytes(body[2*i+2:2*(i+slots)],'little')*(8 if op==4 else 16 if op==8 else 1)
            row.update(name={4:'SAVE_NONVOL',5:'SAVE_NONVOL_FAR',8:'SAVE_XMM128',9:'SAVE_XMM128_FAR'}[op],register=('xmm'+str(info)) if op>=8 else REG[info],stack_offset=value)
        else:raise ValueError('unsupported unwind opcode')
        assert i+slots<=count;row['slots']=slots;codes.append(row);i+=slots
    tail=r+4+((count+1)&~1)*2
    assert flags==2 # These exact two records are termination-handler records, no chain.
    handler=rd.u32(tail);meta=rd.u32(tail+4)
    assert handler==0x1a34e3c
    return {'pdata':list(map(hex,fn)),'unwind_rva':hex(r),'version':v&7,'flags':flags,
            'prolog_bytes':prolog,'count_of_codes':count,'frame_register':frame&15,
            'codes':codes,'encoded_bytes':rd.raw(r,tail+8-r).hex(),
            'handler_rva':hex(handler),'language_data_rva':hex(meta),'chained':False}

def fh4(rd,fn,meta):
    h=rd.raw(meta,1)[0];assert h==0x28 # EHs + unwind-map only; not separated/catch/try.
    uw=rd.u32(meta+1);ip=rd.u32(meta+5)
    count,cur=rd.uint(uw);assert 0<count<=256;start=cur;entries=[]
    for state in range(count):
        at=cur;word,cur=rd.uint(cur);kind=word&3;back=word>>2
        row={'state':state,'entry_rva':hex(at),'type':kind,'previous_entry_rva':hex(at-back),'next_offset':back}
        if kind:row['action_rva']=hex(rd.u32(cur));cur+=4
        if kind in (1,2):row['object_frame_offset'],cur=rd.uint(cur)
        entries.append(row)
    by_rva={int(e['entry_rva'],16):e['state'] for e in entries}
    for e in entries:
        prev=int(e['previous_entry_rva'],16)
        e['previous_state']=-1 if prev<start else by_rva[prev]
        assert -1<=e['previous_state']<e['state']
    uw_end=cur;count,cur=rd.uint(ip);assert 0<count<=512;relative=0;ips=[]
    for _ in range(count):
        delta,cur=rd.uint(cur);state,cur=rd.uint(cur);relative+=delta
        assert fn[0]<=fn[0]+relative<fn[1] and -1<=state-1<len(entries)
        ips.append({'ip_rva':hex(fn[0]+relative),'state':state-1})
    return {'metadata_rva':hex(meta),'header':h,'unwind_map_rva':hex(uw),'ip_map_rva':hex(ip),
            'metadata_bytes':rd.raw(meta,9).hex(),'unwind_map_bytes':rd.raw(uw,uw_end-uw).hex(),
            'ip_map_bytes':rd.raw(ip,cur-ip).hex(),'unwind_entries':entries,'ip_states':ips,
            'format_basis':'Pinned Microsoft ehdata4_export.h plus matching in-image 1a34360 flag/field decoder; not a generic SCOPE_TABLE interpretation.'}

def generate():
    sources=[ROOT/'work/reports/native-single-player-origin-1375.json',ROOT/'work/candidates/origin-native-integration-plan-1375/plan.json',
             ROOT/'work/candidates/origin-native-integration-plan-1375/review.json',ROOT/'work/discover_diplomacy.py',HEADER]
    pins={str(p):digest(p) for p in sources};assert digest(ROOT.parent/'eu4.exe')==SHA
    pe=PE(ROOT.parent/'eu4.exe');md,_=make_disassembler(Path(tempfile.gettempdir())/'eu4-native-analysis-deps')
    old=json.loads(sources[0].read_text());old_rows={int(i['rva'],16):i for f in old['functions'].values() for i in f['instructions']}
    rd=Reader(pe);functions={};decoded={}
    for entry in (0x80b4c0,0x803270):
        fn=pe.function(entry);u=unwind(rd,fn);f=fh4(rd,fn,int(u['language_data_rva'],16))
        functions[hex(entry)]={'unwind':u,'fh4':f}
    # Exact finite neighborhoods and helper decoder, not a full constructor scan.
    ranges=((0x80b4c0,0x84),(0x803270,0x52),(0x803d19,0x48),(0x1a34e3c,0xbf),(0x1a34360,0x122),
            (0x1ae6870,19),(0x1ae6890,19),(0x956c0,5))
    for start,size in ranges:
        items=list(md.disasm(pe.bytes_at(start,size),start));assert sum(i.size for i in items)==size
        for ins in items:
            row={'rva':hex(ins.address),'bytes':ins.bytes.hex(),'instruction':ins.mnemonic+' '+ins.op_str,
                 'previous_report_instruction':ins.address in old_rows}
            if ins.address in old_rows:assert row['bytes']==old_rows[ins.address]['bytes']
            row['rip_relative']='rip' in ins.op_str
            row['control_transfer']=ins.mnemonic.startswith('j') or ins.mnemonic in ('call','ret')
            row['registers_read']=[ins.reg_name(x) for x in ins.regs_access()[0]]
            row['registers_written']=[ins.reg_name(x) for x in ins.regs_access()[1]]
            decoded[ins.address]=row
    assert sum(len(bytes.fromhex(i['bytes'])) for i in decoded.values())<=8192
    fn=functions['0x803270']['fh4'];ips=fn['ip_states'];state=next(x['state'] for x in reversed(ips) if int(x['ip_rva'],16)<=0x803d2c)
    assert state==31
    chain=[]
    while state>=0:chain.append(fn['unwind_entries'][state]);state=chain[-1]['previous_state']
    candidates=[]
    for name,start,span in [('entry_rel32_minimum',0x80b4c0,5),('entry_absolute14_whole_instructions',0x80b4c0,15),
                            ('continuation_rel32_minimum',0x803d2c,12),('continuation_absolute14_whole_instructions',0x803d2c,23)]:
        rows=[decoded[r] for r in sorted(decoded) if start<=r<start+span]
        assert sum(len(bytes.fromhex(r['bytes'])) for r in rows)==span
        incoming=[]
        for key,f in old['functions'].items():
            for e in f['edges']:
                if 'target_rva' not in e:continue # Unknown/indirect prior edges stay outside a completeness claim.
                dest=int(e['target_rva'],16)
                if start<=dest<start+span:incoming.append({'function':key,**e})
        candidates.append({'name':name,'start':hex(start),'span':span,'instructions':rows,
                           'known_direct_cfg_incoming':incoming,'relocation_operands_rip_or_control':any(r['rip_relative'] or r['control_transfer'] for r in rows),
                           'approved_patch':False,'all_program_incoming_edges_proved':False})
    length_table=pe.bytes_at(0x1c20f68,16);shift_table=pe.bytes_at(0x1c20f78,16)
    assert list(struct.unpack('16b',length_table))==[-n for n in LENGTH]
    assert list(shift_table)==[32-7*n if n<5 else 0 for n in LENGTH]
    report={'schema':'origin_c01_unwind_relocation_1375_v1','game_sha256':SHA,'pins':pins,
            'functions':functions,'decoded_instructions':list(decoded.values()),'candidate_spans':candidates,
            'fh4_integer_tables':{'length_rva':'0x1c20f68','length_hex':length_table.hex(),'shift_rva':'0x1c20f78','shift_hex':shift_table.hex()},
            'continuation_unwind_chain':chain,
            'call_binding':{'call_rva':'0x803d27','call_hex':'e894770000','return_rva':'0x803d2c',
                            'destination':'RCX = RSI + 0x1708','source':'RDX = [RBP + 0x3b0]',
                            'source_derivation':'Caller RBP=entry_RSP-0x388, so source slot is entry_RSP+0x28 (fifth argument).',
                            'callee_return':'RAX=destination; normal continuation RSP=callee original entry RSP+8.'},
            'limits':{'decoded_bytes':sum(len(bytes.fromhex(i['bytes'])) for i in decoded.values()),
                      'new_not_in_prior_report_bytes':sum(len(bytes.fromhex(i['bytes'])) for i in decoded.values() if not i['previous_report_instruction']),
                      'max_decode_bytes':8192,'metadata_read_bytes_including_duplicates':sum(n for r,n in rd.reads),'memory_guard_mib':768},
            'scope':{'strict_single_player_verified':False,'engine_lifetime_synchronized':False,'hooks_implemented':False,
                     'patch_length_approved':False,'game_access':False,'build':False},
            'unsupported':['No native adapter unwind info, RtlVirtualUnwind synthetic proof, exception token invalidation or installation exists.',
             'Existing constructor CFG ends before pdata end; known direct branch absence is not global incoming-edge completeness.',
             'Continuation recorder creates a new potentially faulting site; original FH4 IP state31 does not include newly constructed configuration cleanup state32.',
             'Recorder exceptions cannot be swallowed or mapped to an arbitrary original PC; correct EH propagation and source cleanup semantics remain to be proved.',
             'Unknown indirect entries, caller threads, reentrant destruction, XSTATE, mitigations and early-install quiescence remain unsupported.']}
    assert pins=={str(p):digest(p) for p in sources};check_memory_budget();return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
    r=generate();raw=(json.dumps(r,indent=2,ensure_ascii=False)+'\n').encode();p=HERE/'report.json'
    if args.check:assert p.read_bytes()==raw
    else:p.open('xb').write(raw)
    print(json.dumps({'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'limits':r['limits'],'check':args.check}))

if __name__=='__main__':main()
