"""R22 fixed-file replay only. No decoder/producer/process/native invocation."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]
EXE=ROOT.parent/'eu4.exe'
SRC=ROOT/'work/reports/war-peace-api-20261015-r22-string-cleanup/war'
OUT=ROOT/'work/reports/war-peace-api-20261015-r22-independent-review/war'
GAME_SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'


def pin(path):
    sha=hashlib.sha256();count=0
    with path.open('rb') as stream:
        while block:=stream.read(65536):count+=len(block);sha.update(block)
    return dict(bytes=count,sha256=sha.hexdigest())


def load(path):
    assert path.stat().st_size<=1024*1024
    return json.loads(path.read_text(encoding='utf-8'))


def write_new(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(value if isinstance(value,str) else json.dumps(value,indent=2)+'\n')


class FilePE:
    def __init__(self,stream):
        self.stream=stream;self.reads=self.bytes=0
        dos=self.at(0,64);assert dos[:2]==b'MZ'
        start=struct.unpack_from('<I',dos,60)[0];coff=self.at(start,24)
        assert coff[:4]==b'PE\0\0' and struct.unpack_from('<H',coff,4)[0]==0x8664
        sections=struct.unpack_from('<H',coff,6)[0];size=struct.unpack_from('<H',coff,20)[0]
        assert 0<sections<=32 and 112<=size<=512
        opt=self.at(start+24,size);assert struct.unpack_from('<H',opt)[0]==0x20b
        assert struct.unpack_from('<Q',opt,24)[0]==0x140000000
        self.pdata_rva,self.pdata_bytes=struct.unpack_from('<II',opt,136)
        data=self.at(start+24+size,sections*40)
        self.sections=[struct.unpack_from('<IIII',data,i+8)[1:] for i in range(0,len(data),40)]
        self.header_bytes=self.bytes;self.reads=self.bytes=0
    def at(self,offset,size):
        assert 0<size<=4096 and 0<=offset<=38462504-size
        self.stream.seek(offset);value=self.stream.read(size);assert len(value)==size
        self.reads+=1;self.bytes+=size;return value
    def offset(self,rva,size):
        found=[offset+rva-va for va,count,offset in self.sections if va<=rva and rva+size<=va+count]
        assert len(found)==1;return found[0]
    def rva(self,rva,size):return self.at(self.offset(rva,size),size)


def rel32(row):
    raw=bytes.fromhex(row['bytes']);assert len(raw)==5 and raw[0]==0xe8
    target=int(row['rva'],16)+5+struct.unpack('<i',raw[1:])[0]
    assert target==int(row['operands'],16);return target


def check():
    m=load(OUT/'manifest.json');assert m['sealed'] is True
    for name,wanted in m['source_pins'].items():assert pin(ROOT/name)==wanted,name
    for name,wanted in m['artifact_pins'].items():assert pin(Path(name))==wanted,name
    print(json.dumps(dict(status='pass',source_pins=len(m['source_pins']),artifact_pins=len(m['artifact_pins']),
        new_decode_bytes=0,producer_executed=False,process_accessed=False)))


def main():
    assert pin(SRC/'manifest.json')==dict(bytes=2732,sha256='db58b96f997d6fc6acc8bc77e34fef36f00570103522dd001640c86aeb85479f')
    assert pin(SRC/'facts.json')==dict(bytes=6940,sha256='4e1df33cc32061f5623e6089448e2bb5d8892d0f4976f14fa44d9a30ac7ad463')
    m=load(SRC/'manifest.json');assert m['sealed'] is True and len(m['source_pins'])==13
    selected=dict(m['source_pins'])
    for name,wanted in selected.items():assert pin(ROOT/name)==wanted,name
    assert pin(EXE)==dict(bytes=38462504,sha256=GAME_SHA)
    facts=load(SRC/'facts.json');decode=load(SRC/'selected-decode.json')
    assert facts['game_sha256']==decode['game_sha256']==GAME_SHA
    raw=bytes.fromhex(decode['raw_hex'])
    assert len(raw)==94 and hashlib.sha256(raw).hexdigest()==decode['raw_sha256']=='91a12e7a3441b73ba4a7160593bf9ce49bec133871cf3552d3e4d2b70889d354'
    rows={int(row['rva'],16):row for row in decode['instructions']};assert len(rows)==26
    cursor=0x95660;joined=bytearray()
    for row in decode['instructions']:
        assert int(row['rva'],16)==cursor
        b=bytes.fromhex(row['bytes']);cursor+=len(b);joined.extend(b)
    assert cursor==0x956be and joined==raw
    assert next(row['rva'] for row in decode['instructions'] if row['mnemonic']=='ret')=='0x956b7'
    source=load(ROOT/'work/reports/war-peace-api-20261015-r21-sender-ownership/war/evidence.json')
    original={int(row['rva'],16):row for f in source['functions'] if f['entry_rva'] in ('0x4e7470','0x4e9930') for row in f['instructions']}
    for caller in facts['caller_rows']:assert original[int(caller['rva'],16)]==caller
    assert len(facts['caller_rows'])==7
    assert original[0x4e74bc]['bytes']=='488d4b18' and rel32(original[0x4e74c0])==0x95660
    assert original[0x4e9971]['bytes']=='33d2' and original[0x4e9989]['bytes']=='48c740300f000000'
    assert original[0x4e9985]['bytes']=='48895028' and original[0x4e997e]['bytes']=='48895018'
    pdata=decode['pdata'];assert len(pdata['binary_search'])==16 and len(pdata['neighbors'])==2
    with EXE.open('rb') as stream:
        pe=FilePE(stream)
        assert (pe.pdata_rva,pe.pdata_bytes)==(0x2465000,958968)
        assert pe.pdata_bytes//12==pdata['table_count']==79914
        assert pe.offset(0x95660,94)==decode['file_offset']==608864
        assert pe.rva(0x95660,94)==raw
        low,high=0,pdata['table_count']
        all_pdata=pdata['binary_search']+[pdata['selected']]+pdata['neighbors']
        for retained in all_pdata:
            at=pe.pdata_rva+retained['index']*12
            assert at==int(retained['rva'],16)
            value=pe.rva(at,12);assert value.hex()==retained['raw_hex']
            assert struct.unpack('<III',value)==tuple(int(retained[key],16) for key in ('begin_rva','end_exclusive','unwind_rva'))
        for retained in pdata['binary_search']:
            mid=(low+high)//2;assert retained['index']==mid
            if int(retained['begin_rva'],16)<=0x95660:low=mid+1
            else:high=mid
        assert low==high==701 and pdata['selected']['index']==low-1==700
        assert int(pdata['selected']['begin_rva'],16)==0x95660 and int(pdata['selected']['end_exclusive'],16)==0x956be
        assert [r['index'] for r in pdata['neighbors']]==[699,701]
        assert int(pdata['neighbors'][0]['end_exclusive'],16)<=0x95660<0x956be<=int(pdata['neighbors'][1]['begin_rva'],16)
        for caller in facts['caller_rows']:
            assert pe.rva(int(caller['rva'],16),len(bytes.fromhex(caller['bytes'])))==bytes.fromhex(caller['bytes'])
        file_replay=dict(selected_reads=pe.reads,selected_bytes=pe.bytes,header_bytes=pe.header_bytes)
    assert rows[0x95666]['bytes']=='488b5118' and rows[0x9566d]['bytes']=='4883fa10'
    assert rows[0x95671]['mnemonic']=='jb' and rows[0x95671]['bytes']=='722c'
    assert 0x95671+2+struct.unpack('<b',bytes.fromhex('2c'))[0]==0x9569f
    assert rows[0x9569f]['bytes']=='48c7431000000000' and rows[0x956a7]['bytes']=='48c743180f000000'
    assert rows[0x956af]['bytes']=='c60300'
    trace=[];current=0x95660
    while True:
        row=rows[current];trace.append(row)
        if row['mnemonic']=='ret':break
        current=0x9569f if current==0x95671 else current+len(bytes.fromhex(row['bytes']))
    assert trace==facts['empty_inline_trace'] and len(trace)==12
    assert sum(len(bytes.fromhex(row['bytes'])) for row in trace)==facts['empty_inline_trace_bytes']==44
    assert not any(row['mnemonic']=='call' for row in trace)
    assert facts['access_table']==[
        dict(access='read',bytes=8,meaning='unsigned representation/capacity qword',receiver_offset='0x18',rva='0x95666'),
        dict(access='write',bytes=8,receiver_offset='0x10',rva='0x9569f',value=0),
        dict(access='write',bytes=8,receiver_offset='0x18',rva='0x956a7',value=15),
        dict(access='write',bytes=1,receiver_offset='0x0',rva='0x956af',value=0)]
    assert rel32(rows[0x9569a])==0x17394f0 and rel32(rows[0x956b8])==0x1a41c6c
    assert rows[0x95695]['bytes']=='7721' and 0x95695+2+0x21==0x956b8 and rows[0x956bd]['bytes']=='cc'
    # Data-only unsigned branch checks. They do not validate or invoke headers.
    branch_examples=[{'raw_qword':format(value,'016x'),'unsigned_inline_branch':value<16}
                     for value in (0,15,16,1<<63,(1<<64)-1)]
    assert [r['unsigned_inline_branch'] for r in branch_examples]==[True,True,False,False,False]
    assert facts['normal_inline_contract']['clears_remaining_inline_bytes'] is False
    assert pdata['unwind_info_read'] is facts['unwind_info_read'] is False
    assert len(all_pdata)==19 and len({row['index'] for row in all_pdata})==17
    report={'schema':'EU4-R22-INDEPENDENT-STRING-CLEANUP-STATIC-REVIEW/1','status':'pass_conditional_normal_inline_string_cleanup',
        'findings':[],'R22_manifest':pin(SRC/'manifest.json'),'facts':pin(SRC/'facts.json'),'source_pins_verified':13,
        'retained_source_new_decode_bytes':94,'review_new_decode_bytes':0,'retained_instruction_rows':26,
        'fixed_raw_SHA':decode['raw_sha256'],'PE_file_replay':file_replay,
        'pdata':{'directory_rva':'0x2465000','entries':79914,'binary_steps':16,'selected_reread':1,'neighbors':2,
            'producer_data_read_requests_reconstructed':19,'unique_indices':17,'selected_index':700,
            'extent':['0x95660','0x956be'],'first_RET':'0x956b7','unwind_rva_metadata_only':'0x1dc9810','unwind_info_read':False},
        'receiver':{'X':'commandP+0x18','capacity_qword':'X+0x18 == P+0x30','constructor_capacity':15,
            'length_qword':'X+0x10 == P+0x28','first_byte':'X+0 == P+0x18','minimum_selected_span_bytes':32},
        'unsigned_branch_examples':branch_examples,'inline':{'instructions':12,'selected_bytes':44,'calls':0,
            'indirect_buffer_read':False,'receiver_writes':[{'offset':'0x10','bytes':8,'value':0},
            {'offset':'0x18','bytes':8,'value':15},{'offset':'0x0','bytes':1,'value':0}],
            'remaining_inline_bytes_cleared':False,'caller_outer_storage_freed':False},
        'noninline':{'condition':'unsigned capacity>=16','free_call':'0x9569a ->0x17394f0','free_callee_followed':False,
            'invalid_header_tail':'0x956b8 ->0x1a41c6c; thenINT3','tail_callee_followed':False,'HeapFree_success_proven':False},
        'precision_notes':[
            'Source verification lists16 binary and2 neighbor records by category; the producer separately rereads selected700, so pdata total is19requests/17distinctindices. This is not a claim that18 was its total.',
            'The access table is receiver-relative only. PUSH/POP and local stack adjustment still touch stack state; no all-memory-write count is inferred.',
            '956b8 is the selected invalid-header failure tail in ordinary code, not a decoded pdata exception handler. UnwindInfo1dc9810 is metadata only and was not read.'
        ],
        'limits':[
            'No producer, verifier, Capstone, tests, game/process, Frida or native code is executed. Review reads fixed disk bytes and retained instruction/pdata records only; callee bodies are not expanded.',
            'Capacity is unsigned64; signed-negative reinterpretation must not classify highbit/allones values asinline. Damaged-header overflow behavior is not a valid-object or native-call permission.',
            'This conditional normal path assumes a valid live writable string subobject with stable selected representation. Constructor15 does not establish preservation through later aliases/callees.',
            'Only length/capacity/firstbyte reset is established; bytes1..15 are not cleared, no caller storage freed and no world/definition/TLS data is read by this selected path.',
            'Noninline free veneer normal return, HeapFree failure, CRT/errno/TLS/handler and exceptional unwind remain outside. Pdata extent/firstRET does not prove exception safety.',
            'This closes the R21 normal-inline string body gap only. SenderstableH0/false/true meanings, command/action/goal/Sheader ownership, world/context/transport lease, retry and sender gates are unchanged.',
            'No new game call or business effect is tested. The prior R19 body experiment remains a separate one-call rawABI observation and is not repeated or promoted by this review.'
        ],
        'producer_executed':False,'tests_executed':False,'process_accessed':False,'Frida_loaded':False,'new_native_calls':0,
        'native_ready':False,'sender_authorized':False,'lifetime_lease':False,'sentinel_header_lease':False,'new_API_effects':0}
    assert not OUT.exists();OUT.mkdir(parents=True)
    write_new(OUT/'findings.json',report)
    write_new(OUT/'report.md',
        '# R22 字符串 cleanup 独立静态审计\n\n通过。固定94B/26条保留指令、rel32、pdata二分与邻项及7个caller锚点均与PE相符。'
        'unsigned capacity<16 路径12条/44B/0calls，仅写长度0、容量15、首byte0；不读间接buffer、不清其余inlinebytes。\n\n'
        'receiver明确X=P+18，capacity=X+18=P+30（ctor初始化15）。高bit/allones按unsigned不会走inline。pdata读取精确为16search+1selected重读+2neighbors=19requests/17unique。'
        '956b8只是invalid-header失败尾，不能称已核SEH handler；UnwindInfo未读。\n\n'
        '非SSO只绑定旧free入口，不展开失败/异常；sender、alias、Sheader及所有lease/nativeReady门不变。未执行producer、decoder、测试或任何进程/native代码。\n')
    for path in (SRC/'manifest.json',Path(__file__).resolve(),OUT/'findings.json',OUT/'report.md'):
        selected[path.relative_to(ROOT).as_posix()]=pin(path)
    write_new(OUT/'manifest.json',{'schema':'EU4-R22-INDEPENDENT-STATIC-REVIEW-MANIFEST/1','sealed':True,
        'source_pins':dict(sorted(selected.items())),'artifact_pins':{str(EXE):pin(EXE)}})
    print(json.dumps(dict(status=report['status'],report=pin(OUT/'findings.json'),manifest=pin(OUT/'manifest.json'),
        source_pins=len(selected),artifact_pins=1,new_decode_bytes=0)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    check() if args.check else main()
