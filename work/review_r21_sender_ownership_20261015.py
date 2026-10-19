"""Independent R21 retained-byte/CFG review, without producer or disassembler."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]
EXE=ROOT.parent/'eu4.exe'
SRC=ROOT/'work/reports/war-peace-api-20261015-r21-sender-ownership/war'
OUT=ROOT/'work/reports/war-peace-api-20261015-r21-independent-review/war'
GAME_SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'


def pin(path):
    sha=hashlib.sha256();size=0
    with path.open('rb') as stream:
        while raw:=stream.read(65536):size+=len(raw);sha.update(raw)
    return {'bytes':size,'sha256':sha.hexdigest()}


def load(path):
    assert path.stat().st_size<=10*1024*1024
    def unique(rows):
        result={}
        for key,value in rows:
            assert key not in result;result[key]=value
        return result
    return json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=unique)


def write_new(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(value if isinstance(value,str) else json.dumps(value,indent=2)+'\n')


class FilePE:
    def __init__(self,stream):
        self.stream=stream;self.calls=self.bytes=0
        dos=self.read(0,64);assert dos[:2]==b'MZ'
        pe=struct.unpack_from('<I',dos,60)[0];coff=self.read(pe,24)
        assert coff[:4]==b'PE\0\0' and struct.unpack_from('<H',coff,4)[0]==0x8664
        count=struct.unpack_from('<H',coff,6)[0];optional=struct.unpack_from('<H',coff,20)[0]
        assert 0<count<=32 and 112<=optional<=512
        opt=self.read(pe+24,optional);assert struct.unpack_from('<H',opt)[0]==0x20b
        self.base=struct.unpack_from('<Q',opt,24)[0];assert self.base==0x140000000
        raw=self.read(pe+24+optional,40*count);self.sections=[]
        for i in range(count):
            _,va,size,offset=struct.unpack_from('<IIII',raw,40*i+8)
            self.sections.append((va,size,offset))
        self.header_bytes=self.bytes;self.calls=self.bytes=0
    def read(self,offset,size):
        assert type(offset) is int and type(size) is int and 0<size<=4096 and 0<=offset<=38462504-size
        self.stream.seek(offset);raw=self.stream.read(size);assert len(raw)==size
        self.calls+=1;self.bytes+=size;return raw
    def rva(self,address,size):
        offsets=[offset+address-va for va,count,offset in self.sections if va<=address and address+size<=va+count]
        assert len(offsets)==1;return self.read(offsets[0],size)


def relative_target(row):
    """Replay displacement of an already retained branch/call, not new decode."""
    raw=bytes.fromhex(row['bytes']);at=int(row['rva'],16)
    if raw[:1] in (b'\xe8',b'\xe9') and len(raw)==5:delta=struct.unpack('<i',raw[1:])[0]
    elif raw[:1]==b'\xeb' and len(raw)==2:delta=struct.unpack('<b',raw[1:])[0]
    elif len(raw)==2 and 0x70<=raw[0]<=0x7f:delta=struct.unpack('<b',raw[1:])[0]
    elif len(raw)==6 and raw[0]==0x0f and 0x80<=raw[1]<=0x8f:delta=struct.unpack('<i',raw[2:])[0]
    else:raise AssertionError('Not selected direct relative encoding: '+row['rva'])
    target=at+len(raw)+delta;assert target==int(row['operands'],16)
    return target


def graph_for(function):
    rows={int(row['rva'],16):row for row in function['instructions']};graph={}
    for at,row in rows.items():
        mnemonic=row['mnemonic'];fall=at+len(bytes.fromhex(row['bytes']))
        if mnemonic in ('ret','int3','ud2'):edges=[]
        elif mnemonic=='jmp':edges=[relative_target(row)]
        elif mnemonic.startswith('j'):edges=[relative_target(row),fall]
        else:edges=[fall]
        assert all(target in rows for target in edges),(hex(at),edges)
        graph[at]=edges
    return rows,graph


def reachable(graph,start,blocked=(),override=None):
    todo=[start];seen=set()
    while todo:
        current=todo.pop()
        if current in seen or current in blocked:continue
        seen.add(current);todo.extend((override or {}).get(current,graph[current]))
    return seen


def walk_sender(rows,graph,condition,zero_holder=True):
    decisions={0x14ca239:condition['T'],0x14ca242:not condition['P'],0x14ca2a4:zero_holder}
    for address,key in ((0x14ca248,'byte55'),(0x14ca251,'byte80d')):
        if key in condition:decisions[address]=condition[key]!=0
    for address,key in ((0x14ca261,'virtual80'),(0x14ca26e,'virtual58')):
        if key in condition:decisions[address]=condition[key]
    current=0x14ca210;trace=[];calls=[];result=False if not condition['P'] else None
    while True:
        assert current not in trace and len(trace)<80
        trace.append(current);row=rows[current]
        if row['mnemonic']=='call':calls.append(current)
        if current in (0x14ca23b,0x14ca270):result=False
        if current==0x14ca29c:result=True
        if row['mnemonic']=='ret':break
        edges=graph[current]
        if len(edges)==2:
            assert current in decisions and type(decisions[current]) is bool
            current=edges[0] if decisions[current] else edges[1]
        else:assert len(edges)==1;current=edges[0]
    assert type(result) is bool
    return {'trace_rvas':[hex(at) for at in trace],'call_sites':[hex(at) for at in calls],'sender_bool':result}


def check():
    m=load(OUT/'manifest.json');assert m['sealed'] is True
    for name,wanted in m['source_pins'].items():assert pin(ROOT/name)==wanted,name
    for name,wanted in m['artifact_pins'].items():assert pin(Path(name))==wanted,name
    print(json.dumps({'status':'pass','source_pins':len(m['source_pins']),'artifact_pins':len(m['artifact_pins']),
        'new_decode_bytes':0,'producer_executed':False,'process_accessed':False}))


def main():
    manifest_path=SRC/'manifest.json'
    assert pin(manifest_path)=={'bytes':4596,'sha256':'6b1a5efa43cbdb769e388b8fbe71951a4d3f79d32dbb2d7e3135b1785be5adbd'}
    assert pin(SRC/'ownership-paths.json')=={'bytes':28323,'sha256':'29c538c3e4cf85210c81bdaa23c32c4895cbe379a289f1e50cdfd52e4302bfb9'}
    m=load(manifest_path);assert m['sealed'] is True and len(m['source_pins'])==23
    selected=dict(m['source_pins'])
    for name,wanted in selected.items():assert '..' not in Path(name).parts and pin(ROOT/name)==wanted,name
    assert pin(EXE)=={'bytes':38462504,'sha256':GAME_SHA}
    e=load(SRC/'evidence.json');o=load(SRC/'ownership-paths.json');functions={f['entry_rva']:f for f in e['functions']}
    assert len(functions)==21 and e['game_sha256']==GAME_SHA and e['new_decoded_bytes']==e['new_callee_reads']==0
    assert len(e['source_pins'])==18 and e['source_postcheck'] is True
    for name,wanted in e['source_pins'].items():assert selected[name]==wanted
    # Verify copies against exact original function carriers, one file at a time.
    for origin in sorted({f['source'] for f in functions.values()}):
        original=load(ROOT/origin);assert original['game_sha256']==GAME_SHA
        for f in [f for f in functions.values() if f['source']==origin]:
            rows=[old for old in original['functions'] if old['entry_rva']==f['entry_rva']]
            assert len(rows)==1 and rows[0]['instructions']==f['instructions'] and rows[0]['decoded_bytes']==f['decoded_bytes']
    unique={}
    for f in functions.values():
        for row in f['instructions']:
            at=int(row['rva'],16);raw=bytes.fromhex(row['bytes']);assert 0<len(raw)<=15
            assert at not in unique or unique[at]==raw;unique[at]=raw
            if row['mnemonic'].startswith('j') and row['operands'].startswith('0x'):relative_target(row)
            if row['mnemonic']=='call' and row['operands'].startswith('0x'):relative_target(row)
    assert len(unique)==1963 and sum(map(len,unique.values()))==8285
    assert len(e['vtable_slots'])==19
    with EXE.open('rb') as stream:
        pe=FilePE(stream)
        for at,raw in unique.items():assert pe.rva(at,len(raw))==raw,hex(at)
        for slot in e['vtable_slots']:
            at=int(slot['vtable_rva'],16)+int(slot['slot'],16)
            assert at==int(slot['slot_rva'],16)
            raw=pe.rva(at,8);assert raw.hex()==slot['bytes']
            assert struct.unpack('<Q',raw)[0]==pe.base+int(slot['target_rva'],16)
        pe_replay={'instruction_rows':len(unique),'instruction_bytes':8285,'vtable_qwords':19,
                   'reads':pe.calls,'bytes':pe.bytes,'header_bytes':pe.header_bytes}
    assert pe_replay['reads']==1982 and pe_replay['bytes']==8437
    slots={(int(row['vtable_rva'],16),int(row['slot'],16)):int(row['target_rva'],16) for row in e['vtable_slots']}
    assert slots[0x1c814b0,0x80]==slots[0x1c814b0,0x58]==0x8f450
    assert unique[0x8f450]==b'\x32\xc0' and unique[0x8f452]==b'\xc3'
    for at,raw in ((0x14ca224,'488bf2'),(0x14ca22a,'488b1a'),(0x14ca22d,'48c70200000000'),
        (0x14ca29e,'488b0e'),(0x14ca2a9,'ba01000000'),(0x14ca2ae,'41ff10'),(0x14ca29c,'b301')):
        assert unique[at].hex()==raw
    sender_rows,sender_graph=graph_for(functions['0x14ca210'])
    assert [hex(at) for at,row in sender_rows.items() if row['mnemonic']=='ret']==['0x14ca2c3']
    cases=[]
    for case in o['paths']:
        trace=walk_sender(sender_rows,sender_graph,case['conditions'])
        assert all(trace[key]==case[key] for key in ('trace_rvas','call_sites','sender_bool'))
        assert case['stable_holder_zero_required'] is True and case['caller_holder_after_take']==0
        assert case['holder_tail_deleting_call'] is case['automatic_retry_permitted'] is False
        assert ('0x14ca299' in trace['call_sites']) is case['queue_or_transport_called']
        assert '0x14ca2ae' not in trace['call_sites']
        cases.append({'id':case['id'],'return_bool':trace['sender_bool'],'calls':trace['call_sites'],'stable_zero_holder':True})
    assert len(cases)==8
    alias=walk_sender(sender_rows,sender_graph,o['paths'][3]['conditions'],zero_holder=False)
    assert alias==o['common_cleanup']['diagnostic_generic_false_replacement_trace']
    assert '0x14ca2ae' in alias['call_sites'] and alias['sender_bool'] is False
    tr,graph=graph_for(functions['0x1580370'])
    rets=[at for at,row in tr.items() if row['mnemonic']=='ret'];assert rets==[0x1580cad]
    assert unique[0x1580370].hex()=='4885d2' and tr[0x1580373]['mnemonic']=='je'
    normal_override={0x1580373:[0x1580379]}
    assert 0x1580cad in reachable(graph,0x1580370,override=normal_override)
    assert 0x1580cad not in reachable(graph,0x1580370,blocked={0x1580c5a},override=normal_override)
    assert 0x1580cad in reachable(graph,0x1580370,blocked={0x1580c5a}) # NULL input direct RET counterexample.
    assert tr[0x1580c5a]['mnemonic']=='call' and unique[0x1580c5a].hex()=='ff10'
    assert unique[0x1580379].hex()=='4889542410' and unique[0x1580c4a].hex()=='488b8c24f80b0000'
    assert unique[0x1580c52].hex()=='488b01' and unique[0x1580c55].hex()=='ba01000000'
    assert sum(1 for row in tr.values() if row['mnemonic']=='push')==7
    assert 0xbb0+7*8+0x10==0xbf8
    assert [row for row in tr.values() if '0xbf8' in row['operands']]==[tr[0x1580c4a]]
    # Inventory is deliberately principal four functions only, not all21 bodies.
    principal={'0x14ca210','0x1580370','0x4e7470','0x4e9930'}
    calls={(f['entry_rva'],row['rva']):row for f in functions.values() if f['entry_rva'] in principal for row in f['instructions'] if row['mnemonic']=='call'}
    assert len(calls)==len(o['callee_inventory'])==49
    assert set(calls)=={(row['function_rva'],row['call_rva']) for row in o['callee_inventory']}
    for item in o['callee_inventory']:
        row=calls[item['function_rva'],item['call_rva']]
        if item['binding']=='direct_rel32':assert relative_target(row)==int(item['target_rva'],16)
        elif item['binding']=='conditional_on_selected_receiver_vtable':assert slots[int(item['vtable_rva'],16),int(item['slot'],16)]==int(item['target_rva'],16)
        else:assert item['binding']=='receiver_not_closed_here' and item['target_rva'] is None
    # Explicit clarification of sealed report shorthand: virtual slot, not A+a8.
    assert unique[0x4e7489].hex()=='488b4950' and unique[0x4e7492].hex()=='488b01'
    assert unique[0x4e7495].hex()=='ff90a8000000' and slots[0x1c80d90,0xa8]==0x8f450
    clarification={'sealed_source':'work/reports/war-peace-api-20261015-r21-sender-ownership/war/report.md section3',
        'shorthand':'普通declarewar的action+a8为8f450(false)',
        'correct_receiver':'load action=A1 from[P0+50]; V=read64(A1); call read64(V+0xa8)',
        'selected_binding':'action.vtable1c80d90.slot+a8 ->8f450',
        'evidence':[{'rva':hex(at),'bytes':unique[at].hex()} for at in (0x4e7489,0x4e7492,0x4e7495)],
        'action_object_A_plus_a8_read_proved':False,'machine_table_correct':True,'blocking':False}
    for field in ('native_ready','sender_authorized','lifetime_lease','sentinel_header_lease','automatic_retry','game_accessed'):
        assert o[field] is False,field
    assert o['native_calls']==o['new_decoded_bytes']==0
    report={'schema':'EU4-R21-INDEPENDENT-SENDER-OWNERSHIP-STATIC-REVIEW/1','status':'pass_normal_selected_ownership_with_documentation_clarification',
        'findings':[],'documentation_clarifications':[clarification],'R21_manifest':pin(manifest_path),'ownership_paths':pin(SRC/'ownership-paths.json'),
        'source_pins_verified':23,'original_function_carriers_matched':21,'PE_byte_replay':pe_replay,
        'normal_sender_cases_replayed':cases,'stable_zero_tail_replacement_counterexample_replayed':True,
        'transport_nonnull_callsite_dominates_unique_normal_RET':True,'transport_null_direct_RET_requires_nonnull_qualifier':True,
        'saved_P0_slot':'entryRSP+10 == frameRSP+bf8; no other explicitbf8 reference in retained transport',
        'principal_callee_inventory_checked':{'functions':4,'call_sites':49,'recursive_closure_claimed':False},
        'selected_conclusions':[
            'P0=RBX and H=RSI are different identities: sender takes[H] intoRBX then clears[H] before any T/command gate. Tail reloadsRCX=[H] and may delete that current value only; it is not a savedP0 fallback.',
            'StableH0 no-call earlyfalse and selected vt1c814b0 pure8f450 gatefalse paths have no transport/tail-deleting call in this function. This is not a full-program leak proof or permission to retry/compensating-destruct.',
            'With nonnullP0 and selected T.vt1d96178, all retained intraprocedural paths to normalRET1580cad cross deletingcall1580c5a. This proves the callsite under normal-callee-return assumptions, not object liveness, HeapFree success or exceptional cleanup.',
            'After T.vt.slot30 returns normally sender unconditionally writesBL=1. It does not inspect AI/action/queue success and may deleteP0 even with zero recipients. QueuedQi/Ni are separate stages; no empty-queue/effect completion follows.'
        ],
        'limits':[
            'Files/fixed diskPE/retained instruction displacement replay only. No original producer, old tests, process, Frida, native function or new decoder/callee read is executed.',
            'The graph treats calls as normally returning and terminals/int3 as non-normal ends. Callee nonreturn/exception/fatal/SEH behavior, command/context/transport mutation and all externalaliases/rebinding remain unknown.',
            'StableH0 is an explicit assumption. If H_after is rewritten nonzero, tail cleanup deletes the reloaded replacement identity and does not clearH again. Generic virtual80/58 may have ownership side effects; typed8f450 alone is the purefalse leaf.',
            'Savedstack-slot and callsite dominance are structural identities, not owning references or leases. Unknown serializer/dynamic factory/parser/string95660/free failure/CRT handler/TLS paths are not recursively closed.',
            'The49-call inventory covers four principal functions; retained21 bodies are not a complete callee/alias graph. Distinct factory paths forQi/Ni do not establish arbitrary-all-objects-distinct predicates or complete failure disposal.',
            'Ordinarywrapper gate-true cases are explicitly unreachable forvt1c814b0; genericcommand hypotheses cannot inherit typed gate purity. Nullcommand cases are not constructed-request effect tests.',
            'Earlier one-body rawABI experiment does not validate wrapper/sender execution, legalCpp construction/full lifecycle/noCB, sentinel/world lifetime, thread/TLS or gameplay effects. No native/sender ready, retry or new test authority is granted.'
        ],
        'new_decode_bytes':0,'producer_executed':False,'tests_executed':False,'process_accessed':False,'Frida_loaded':False,'native_calls':0,
        'native_ready':False,'sender_authorized':False,'lifetime_lease':False,'sentinel_header_lease':False,'new_API_effects':0}
    assert not OUT.exists();OUT.mkdir(parents=True)
    write_new(OUT/'findings.json',report)
    write_new(OUT/'report.md',
        '# R21 sender ownership 独立静态复核\n\n通过。23 个来源 pin、21 个原始函数载体、8285B 保留指令和19虚槽均与固定 PE 匹配；8正常 case trace、H重绑反例及非空transport删除调用支配关系重放一致。\n\n'
        '关键限制：尾部重读 H，不恢复保存的 P0；stable H=0 下指定早期false未在该函数释放/转交原command。typed transport正常RET前经过原P0 deleting call，sender true只表示transport槽30正常返回。'
        '外部alias、gate副作用、callee异常、HeapFree成功、队列副本处置与效果仍未知，不开放重试。\n\n'
        '封存报告第3节 action+a8 为缩略措辞：实际 4e7492先加载action.vtable，4e7495调用[vtable+a8]；vt1c80d90.slot+a8→8f450。机器表正确，不能解释为读取98B action本体+a8。原报告不改写。\n\n'
        '未执行producer/测试/游戏/Frida/native，新增decode0。nativeReady、sender、lease及APIeffect均保持false/0。\n')
    for p in (manifest_path,Path(__file__).resolve(),OUT/'findings.json',OUT/'report.md'):
        selected[p.relative_to(ROOT).as_posix()]=pin(p)
    write_new(OUT/'manifest.json',{'schema':'EU4-R21-INDEPENDENT-OWNERSHIP-REVIEW-MANIFEST/1','sealed':True,
        'source_pins':dict(sorted(selected.items())),'artifact_pins':{str(EXE):pin(EXE)}})
    print(json.dumps({'status':report['status'],'report':pin(OUT/'findings.json'),'manifest':pin(OUT/'manifest.json'),
        'source_pins':len(selected),'artifact_pins':1,'new_decode_bytes':0}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    check() if args.check else main()
