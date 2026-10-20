"""R26: exactly13 new code bytes,16 decoder bytes with retained partial3.

No author producer/test execution, target process, callee, literal or unwind read.
Only this analysis process's memory counters are queried for the resource guard.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
R25 = ROOT/'work/reports/war-peace-api-20261015-r25-linked-truce-callees/war'
OUT = ROOT/'work/reports/war-peace-api-20261015-r26-linked-truce-tails/war'
DEP = ROOT/'work/deps/capstone-5.0.7'
EXE = ROOT.parent/'eu4.exe'
GAME_SHA = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
MANIFEST_SHA = '31235a31aee32a2cf98015df9960d46d94f60b05b9a08053887fe237b37bf1c8'
DECODE_SHA = '7254f306665963fd6ec2c9b0ea50ecb7bc293aab2c5c52adb961f46015375323'
MEMORY_GUARD = 768*1024*1024
HARD_STOP = 1024*1024*1024


class MemoryGuard:
    class Counters(C.Structure):
        _fields_ = [('cb',W.DWORD),('PageFaultCount',W.DWORD)]+[(name,C.c_size_t) for name in (
            'PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
            'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
    def __init__(self):
        assert sys.platform == 'win32'
        self.kernel = C.WinDLL('kernel32',use_last_error=True)
        self.psapi = C.WinDLL('psapi',use_last_error=True)
        self.kernel.GetCurrentProcess.restype = W.HANDLE
        self.psapi.GetProcessMemoryInfo.argtypes = [W.HANDLE,C.POINTER(self.Counters),W.DWORD]
        self.psapi.GetProcessMemoryInfo.restype = W.BOOL
        self.peak = self.calls = 0
        self()
    def __call__(self):
        item = self.Counters(); item.cb = C.sizeof(item)
        assert self.psapi.GetProcessMemoryInfo(self.kernel.GetCurrentProcess(),C.byref(item),item.cb)
        self.peak = max(self.peak,item.PeakPagefileUsage); self.calls += 1
        if item.PagefileUsage > MEMORY_GUARD or self.peak > HARD_STOP:
            raise MemoryError('Own analysis exceeds768MiB current/1GiB historical committed-memory guard')
        return self.peak


GUARD = None


def pin(path):
    h = hashlib.sha256(); size = 0
    with path.open('rb') as stream:
        while block := stream.read(65536):
            size += len(block); h.update(block)
            if GUARD: GUARD()
    return {'bytes':size,'sha256':h.hexdigest()}


def load(path):
    assert path.stat().st_size <= 1024*1024
    def unique(pairs):
        value = {}
        for k,v in pairs:
            assert k not in value; value[k] = v
        return value
    return json.loads(path.read_bytes().decode('utf-8'),object_pairs_hook=unique)


def write_new(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(value if isinstance(value,str) else json.dumps(value,indent=2)+'\n')


class FilePE:
    def __init__(self,stream):
        self.stream = stream; self.header_reads = self.header_bytes = 0; self.code_reads = []
        dos = self.header(0,64); assert dos[:2] == b'MZ'
        start = struct.unpack_from('<I',dos,60)[0]
        coff = self.header(start,24)
        assert coff[:4] == b'PE\0\0' and struct.unpack_from('<H',coff,4)[0] == 0x8664
        count,size = struct.unpack_from('<H',coff,6)[0],struct.unpack_from('<H',coff,20)[0]
        assert 0 < count <= 32 and 144 <= size <= 512
        opt = self.header(start+24,size)
        assert struct.unpack_from('<H',opt)[0] == 0x20b and struct.unpack_from('<Q',opt,24)[0] == 0x140000000
        section = self.header(start+24+size,count*40)
        self.sections = [struct.unpack_from('<IIII',section,i+8)[1:] for i in range(0,len(section),40)]
    def header(self,at,size):
        assert 0 < size <= 2048 and 0 <= at <= 38462504-size
        self.stream.seek(at); value = self.stream.read(size); assert len(value) == size
        self.header_reads += 1; self.header_bytes += size; GUARD()
        return value
    def offset(self,rva,size):
        matches = [offset+rva-va for va,span,offset in self.sections if va <= rva and rva+size <= va+span]
        assert len(matches) == 1
        return matches[0]
    def code(self,rva,size):
        assert (rva,size) in ((0x2f1610,3),(0x7ae2e0,10))
        assert rva not in [int(item['rva'],16) for item in self.code_reads]
        offset = self.offset(rva,size); self.stream.seek(offset); value = self.stream.read(size)
        assert len(value) == size
        self.code_reads.append({'rva':hex(rva),'end_exclusive':hex(rva+size),'file_offset':offset,
            'bytes':size,'raw_hex':value.hex(),'raw_sha256':hashlib.sha256(value).hexdigest()})
        GUARD(); return value


class VerifiedSourceLoader(importlib.machinery.SourceFileLoader):
    def __init__(self,fullname,path,wanted,loaded):
        super().__init__(fullname,str(path)); self.wanted = wanted; self.loaded = loaded
    def get_code(self,fullname):
        value = self.get_data(self.path)
        assert len(value) == self.wanted['bytes'] and hashlib.sha256(value).hexdigest() == self.wanted['sha256']
        self.loaded[fullname] = {'path':str(Path(self.path).relative_to(ROOT)),**self.wanted}
        GUARD()
        return compile(value,self.path,'exec')  # Never load or create a capstone pyc.


class VerifiedCapstoneFinder(importlib.abc.MetaPathFinder):
    def __init__(self,pins): self.pins = pins; self.loaded = {}
    def find_spec(self,fullname,path=None,target=None):
        if fullname != 'capstone' and not fullname.startswith('capstone.'): return None
        name = 'capstone/__init__.py' if fullname == 'capstone' else fullname.replace('.','/')+'.py'
        assert name in self.pins,'Unpinned Capstone Python module'
        actual = DEP/name
        return importlib.util.spec_from_file_location(fullname,actual,
            loader=VerifiedSourceLoader(fullname,actual,self.pins[name],self.loaded),
            submodule_search_locations=[str(DEP/'capstone')] if fullname == 'capstone' else None)


def check():
    m = load(OUT/'manifest.json'); assert m['sealed'] is True
    for name,wanted in m['source_pins'].items(): assert pin(ROOT/name) == wanted,name
    for name,wanted in m['artifact_pins'].items(): assert pin(Path(name)) == wanted,name
    print(json.dumps({'status':'pass','local_pins':len(m['source_pins']),'artifact_pins':len(m['artifact_pins']),
        'new_code_read_bytes':0,'new_decode_bytes':0,'process_accessed':False,'producer_or_tests_rerun':False}))


def main():
    global GUARD
    started = time.perf_counter(); GUARD = MemoryGuard()
    assert pin(OUT/'attempt-01/producer.py') == {'bytes':20620,'sha256':'9613bae680b3d31619bc17ee7c09d4ca0d395feee4d1ba44692eeb74ca39c66e'}
    assert pin(OUT/'attempt-01/failure.json')['sha256'] == 'ef717f1d4af0fb4023a7d8a96bb0d6b8fab9b2be77faabca6e09ce1bc86328de'
    first_failure = load(OUT/'attempt-01/failure.json')
    assert pin(R25/'manifest.json')['sha256'] == MANIFEST_SHA
    assert pin(R25/'selected-decode.json') == {'bytes':20724,'sha256':DECODE_SHA}
    manifest = load(R25/'manifest.json'); assert manifest['sealed'] is True and manifest['native_ready'] is False
    selected = dict(manifest['sources'])
    selected.update({(R25/name).relative_to(ROOT).as_posix():wanted for name,wanted in manifest['files'].items()})
    for name,wanted in selected.items(): assert pin(ROOT/name) == wanted,name
    d = load(R25/'selected-decode.json'); meta = load(R25/'metadata-plan.json')
    assert d['game_sha256'] == meta['game_sha256'] == GAME_SHA
    assert d['metadata_plan_pin'] == pin(R25/'metadata-plan.json')
    regions = {int(region['target_rva'],16):region for region in d['regions']}
    targets = {int(item['target_rva'],16):item for item in meta['targets']}
    prior = {}; complete = {}; retained_rows = []
    for start,end,old_count in ((0x2f1590,0x2f1613,125),(0x7ae260,0x7ae2ea,128)):
        region = regions[start]; raw = bytes.fromhex(region['raw_hex'])
        assert len(raw) == region['read_bytes'] == 128
        assert hashlib.sha256(raw).hexdigest() == region['raw_sha256']
        rows = region['instructions']; joined = b''.join(bytes.fromhex(row['bytes']) for row in rows)
        assert len(joined) == region['new_decoded_bytes'] == old_count and joined == raw[:old_count]
        cursor = start
        for row in rows:
            assert int(row['rva'],16) == cursor; cursor += len(bytes.fromhex(row['bytes']))
        assert raw[old_count:].hex() == region['undecoded_tail_hex']
        assert cursor == start+old_count
        chosen = targets[start]['selected_lower']; pdata = bytes.fromhex(chosen['raw_hex'])
        assert struct.unpack('<III',pdata) == (start,end,int(chosen['unwind_rva'],16))
        assert int(chosen['begin_rva'],16) == start and int(chosen['end_exclusive'],16) == end
        prior[start] = raw; complete[start] = [dict(row) for row in rows]
        retained_rows.extend(rows)
    assert prior[0x2f1590][125:] == bytes.fromhex('4883c4') and prior[0x7ae260][128:] == b''
    assert len(retained_rows) == 71
    assert pin(EXE) == {'bytes':38462504,'sha256':GAME_SHA}
    with EXE.open('rb') as stream:
        pe = FilePE(stream)
        for start in (0x2f1590,0x7ae260):
            assert pe.offset(start,128) == regions[start]['file_offset'] == targets[start]['window_file_offset']
        new2f = pe.code(0x2f1610,3); new7a = pe.code(0x7ae2e0,10)
        pe_counts = {'header_reads':pe.header_reads,'header_bytes':pe.header_bytes,
            'new_code_reads':pe.code_reads,'new_code_bytes':sum(item['bytes'] for item in pe.code_reads)}
    assert pe_counts['new_code_bytes'] == 13
    dependency_receipt = load(ROOT/'work/deps/capstone-5.0.7.receipt.json')
    dependency_pins = {name:value for name,value in dependency_receipt['files'].items()
                       if name.endswith(('.py','.dll'))}
    assert len(dependency_pins) == 38
    for name,wanted in dependency_pins.items():
        path = DEP/name; assert pin(path) == wanted,name
        selected[path.relative_to(ROOT).as_posix()] = wanted
    assert not any(name == 'capstone' or name.startswith('capstone.') for name in sys.modules)
    finder = VerifiedCapstoneFinder(dependency_pins)
    previous = os.environ.get('LIBCAPSTONE_PATH')
    os.environ['LIBCAPSTONE_PATH'] = str(DEP/'capstone/lib')
    sys.meta_path.insert(0,finder)
    try:
        import capstone
        assert capstone.__version__ == '5.0.7'
        assert Path(capstone._cs._name).resolve() == (DEP/'capstone/lib/capstone.dll').resolve()
        md = capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
        tails = []
        for start,raw,new_bytes,retained_partial in ((0x2f160d,prior[0x2f1590][125:]+new2f,3,3),
                                                    (0x7ae2e0,new7a,10,0)):
            GUARD(); rows = [{'rva':hex(ins.address),'bytes':bytes(ins.bytes).hex(),
                'mnemonic':ins.mnemonic,'operands':ins.op_str} for ins in md.disasm(raw,start)]
            assert b''.join(bytes.fromhex(row['bytes']) for row in rows) == raw
            assert len(raw) == new_bytes+retained_partial
            tails.append({'start_rva':hex(start),'end_exclusive':hex(start+len(raw)),
                'raw_hex':raw.hex(),'raw_sha256':hashlib.sha256(raw).hexdigest(),
                'new_code_bytes':new_bytes,'reused_undecoded_partial_bytes':retained_partial,
                'decoder_input_bytes':len(raw),'instructions':rows})
    finally:
        sys.meta_path.remove(finder)
        if previous is None: os.environ.pop('LIBCAPSTONE_PATH',None)
        else: os.environ['LIBCAPSTONE_PATH'] = previous
    for name,wanted in dependency_pins.items(): assert pin(DEP/name) == wanted,name
    # Exact local continuation checks only. No outgoing callee is decoded or invoked.
    false_rows = tails[0]['instructions']; byte_rows = tails[1]['instructions']
    false_closed = [(r['mnemonic'],r['operands']) for r in false_rows] == [('add','rsp, 0x20'),('pop','rbx'),('ret','')]
    continuation = None
    if len(byte_rows) == 2 and byte_rows[1]['mnemonic'] == 'jmp':
        b = bytes.fromhex(byte_rows[1]['bytes']); site = int(byte_rows[1]['rva'],16)
        if len(b) == 5 and b[0] == 0xe9:
            continuation = site+5+struct.unpack('<i',b[1:])[0]
    local_pointer_load = len(byte_rows) == 2 and byte_rows[0]['mnemonic'] == 'mov' and byte_rows[0]['operands'] == 'rax, qword ptr [rsp + 0x40]'
    byte_path_closed = continuation == 0x7ae2be
    additional_calls = []
    for tail in tails:
        for row in tail['instructions']:
            if row['mnemonic'] == 'call':
                b = bytes.fromhex(row['bytes']); site = int(row['rva'],16)
                assert len(b) == 5 and b[0] == 0xe8
                called = site+5+struct.unpack('<i',b[1:])[0]
                assert row['operands'] == hex(called)
                additional_calls.append({'site':hex(site),'target':hex(called),'callee_followed':False})
    complete[0x2f1590].extend(false_rows); complete[0x7ae260].extend(byte_rows)
    for start,end in ((0x2f1590,0x2f1613),(0x7ae260,0x7ae2ea)):
        cursor = start
        for row in complete[start]:
            assert int(row['rva'],16) == cursor; cursor += len(bytes.fromhex(row['bytes']))
        assert cursor == end
    instructions = {int(row['rva'],16):row for rows in complete.values() for row in rows}
    assert instructions[0x2f160b]['bytes'] == '32c0' and instructions[0x2f1603]['bytes'] == 'b001'
    assert instructions[0x7ae2be]['bytes'] == '0fb600' and instructions[0x7ae2db]['bytes'] == 'e880cfcaff'
    GUARD()
    decode = {'schema':'EU4-LINKED-TRUCE-TAILS-SELECTED-DECODE/1','game_sha256':GAME_SHA,
        'evidence_type':'ordinary_offline_Capstone_not_REA','source_R25_manifest':pin(R25/'manifest.json'),
        'source_R25_decode':pin(R25/'selected-decode.json'),'capstone_version':capstone.__version__,
        'verified_decoder_sources':finder.loaded,'verified_capstone_dependency_pins':dependency_pins,
        'bytecode_cache_read_or_written':False,'engine_DLL':str(DEP/'capstone/lib/capstone.dll'),
        'new_tails':tails,'retained_decoded_bytes':253,'retained_undecoded_partial_bytes':3,
        'new_code_bytes_read':13,'new_decoder_input_bytes':16,'complete_joined_instruction_bytes':269,
        'complete_functions':[{'entry_rva':hex(start),'end_exclusive':hex(start+sum(len(bytes.fromhex(r['bytes'])) for r in rows)),
            'instructions':rows,'normal_RET_sites':[r['rva'] for r in rows if r['mnemonic'] == 'ret']}
            for start,rows in complete.items()],
        'PE_read_accounting':pe_counts,'pdata_boundaries_reused_without_read':[
            targets[start]['selected_lower'] for start in (0x2f1590,0x7ae260)],
        'additional_unfollowed_tail_calls':additional_calls,
        'attempt_accounting':{'attempt01_new_code_read_requests':first_failure['new_code_read_requests'],
            'attempt01_new_code_read_bytes':first_failure['new_code_read_bytes'],
            'attempt01_decoder_input_bytes':first_failure['decoder_input_bytes'],
            'attempt01_raw_retained':False,'attempt01_counts_grade':'pinned producer plus retained failure trace witness, not firstraw replay',
            'attempt02_new_code_read_requests':2,'attempt02_code_read_bytes':13,'attempt02_decoder_input_bytes':16,
            'cumulative_code_read_requests':4,'cumulative_physical_code_read_bytes':26,
            'cumulative_decoder_input_bytes':32,'unique_new_code_coverage_bytes':13,
            'unique_newly_decoded_instruction_bytes':16,'reason_for_second_read':'first attempt incorrectly asserted no tailCALL before saving raw; root authorized samewindow repair only'},
        'whole_function_redecoded':False,'callee_or_literal_or_unwind_read':False,
        'memory_guard_bytes':MEMORY_GUARD,'hard_stop_bytes':HARD_STOP,
        'own_peak_committed_bytes':GUARD.peak,'hard_job_object_installed':False,
        'process_accessed':False,'game_native_calls':0,'Frida_operations':0,'tests_run':0,'native_ready':False}
    contract = {'schema':'EU4-LINKED-TRUCE-TAILS-STATIC-CONTRACT/1','game_sha256':GAME_SHA,
        'status':'selected_normal_tails_closed' if false_closed and byte_path_closed else 'unknown_tail_semantics',
        'scope':'R25 normal tail closure only; no transitive predicate or business type proof',
        'false_2f':{'entry_rva':'0x2f1590','pdata_extent':['0x2f1590','0x2f1613'],
            'false_AL_zero_site':'0x2f160b','tail_extent':['0x2f160d','0x2f1613'],
            'false_normal_RET_closed':false_closed,
            'false_normal_RET_site':false_rows[-1]['rva'] if false_closed else None,
            'true_normal_RET_site':'0x2f160a','return_scope':'AL0 or1 only on selected normal paths; upperRAX is not a normalized full-widthBoolean',
            'stack_balance':'PUSH RBX/SUB RSP20; both selected normal exits ADD RSP20/POP RBX/RET',
            'unfollowed_calls':['0x3d79f0','0xb1e020'],
            'unchanged_unknowns':['callee effects/return contracts and R9/R10 preservation',
                'business types of U/+11a/+1c8/+18f0','alias/lifetime/exception/unwind']},
        'byte_7a':{'entry_rva':'0x7ae260','pdata_extent':['0x7ae260','0x7ae2ea'],
            'preceding_call':'0x7ae2db ->0x45b260','tail_extent':['0x7ae2e0','0x7ae2ea'],
            'loads_RAX_from_local_RSP40':local_pointer_load,'tail_jump_target':hex(continuation) if continuation is not None else None,
            'returns_to_selected_byte_load':byte_path_closed,'byte_load_site':'0x7ae2be',
            'normal_RET_site':'0x7ae2c6','return_scope':'EAX is zero-extended selected byte, not normalized to0/1; R23 only tests ALzero/nonzero',
            'tail_instructions':byte_rows,'additional_unfollowed_calls':additional_calls,
            'post_45b260_validation':'The selected tail contains no conditionalnonnull/type guard before its jump; all additional CALL bodies and their returnpointer contracts remain unknown.',
            'local_buffer_scope':'24localbytes at currentRSP40..57 were zeroed before45b260. Tail register definitions are preserved explicitly; no guessed localrecord business type.',
            'unfollowed_calls':['0x7b3950','0x1a3514c','0x45b6e0','0x45b260']+[item['target'] for item in additional_calls],
            'unchanged_unknowns':['localrecord business type and pointer lifetime','callee effects/allocation/caching/failure',
                'contents of232e9c8/1c38150','entryRSP+8 byte origin','exception/unwind']},
        'accounting':{'new_code_read':13,'new_decoder_input':16,'old_partial_now_decoded':3,
            'retained_old_decoded':253,'completed_joined_bytes':269,'old_functions_redecoded':False,
            'cumulative_physical_code_read_bytes':26,'cumulative_code_read_requests':4,
            'cumulative_decoder_input_bytes':32,'first_attempt_raw_available':False},
        'authority':{'callable':False,'native_ready':False,'side_effect_free_transitive':False,
            'world_lifetime_lease':False,'truce_expiry_known':False,'peace_completion_verified':False,
            'reader_implemented':False,'runtime_calls_performed':False},
        'execution':{'target_process_accesses':0,'Frida_operations':0,'game_native_calls':0,
            'requests_published':0,'tests_run':0,'old_sealed_sources_changed':False}}
    preparation = {'schema':'EU4-LINKED-TRUCE-TAILS-PREPARATION/1','captured_utc':datetime.now(timezone.utc).isoformat(),
        'source_manifest_before_tail_reads':pin(R25/'manifest.json'),'source_decode_before_tail_reads':pin(R25/'selected-decode.json'),
        'source_raw_prefixes_checked':True,'fixed_EXE':pin(EXE),'new_code_read_bytes':13,
        'decoder_input_bytes':16,'complete_joined_bytes':269,'tail_semantics_closed':false_closed and byte_path_closed,
        'no_external_body_or_literal_or_unwind_followed':True,'own_peak_committed_bytes':GUARD.peak,
        'memory_guard_checks':GUARD.calls,'memory_guard_bytes':MEMORY_GUARD,'hard_stop_bytes':HARD_STOP,
        'hard_job_object_installed':False,'target_process_accesses':0,'game_native_calls':0,
        'Frida_operations':0,'tests_run':0,'elapsed_ms':round((time.perf_counter()-started)*1000,3)}
    preparation['attempt_accounting'] = decode['attempt_accounting']
    assert OUT.exists() and {p.name for p in OUT.iterdir()} == {'attempt-01'}
    write_new(OUT/'selected-decode.json',decode); write_new(OUT/'contract.json',contract)
    write_new(OUT/'preparation.json',preparation)
    write_new(OUT/'report.md',
        '# R26 linked truce helper 尾部补闭\n\n'
        '只新读13B：2f1610..13的3B与7ae2e0..ea的10B。旧partial3B与新3B拼成6B，另10B单独解码；'
        '新decoder输入16B，与R25旧253B指令表拼接269B，不整函数重解码。两个窗口均止于已保留pdata边界。'
        '首轮错误断言tail不含CALL，解码后封存前失败且未留raw；完整前像/失败记录保留。经root授权仅同窗口重放一次，'
        '累计物理code读取26B/4seek、decoder输入32B，唯一新增code覆盖仍13B/新指令16B。首次计数是固定producer与失败trace见证，不冒称首次raw可回放。\n\n'
        f'2f false普通返回闭合={false_closed}；AL在2f160b清零，tail恢复RSP/RBX后RET。'
        f'7ae的45b260后回到byte-load路径={byte_path_closed}，tail逐条指令与新发现CALL目标以selecteddecode为准，'
        f'追加未跟随CALL={additional_calls}。没有额外nonnull/type检查；所有callee返回合同仍未知。'
        '选定正常路径EAX为zero-extended byte，不证明严格Boolean。\n\n'
        '不读literal/unwind或任何callee，不执行旧producer/测试/游戏/Frida。callee effects、业务类型、ownership/异常、expiry/peace仍未知；'
        '所有authority保持false。仅自有分析进程内存计数用于768MiB guard，超过1GiB停止；非硬Job限额。\n')
    for path in (R25/'manifest.json',R25/'verification.json',Path(__file__).resolve(),
        OUT/'attempt-01/producer.py',OUT/'attempt-01/failure.json',OUT/'attempt-01/tool-result.json',
        OUT/'selected-decode.json',OUT/'contract.json',OUT/'preparation.json',OUT/'report.md'):
        selected[path.relative_to(ROOT).as_posix()] = pin(path)
    write_new(OUT/'manifest.json',{'schema':'EU4-LINKED-TRUCE-TAILS-STATIC-MANIFEST/1','sealed':True,
        'source_pins':dict(sorted(selected.items())),'artifact_pins':{str(EXE):pin(EXE)},
        'new_code_bytes_read':13,'new_decoder_input_bytes':16,'native_ready':False,
        'cumulative_physical_code_read_bytes':26,'cumulative_decoder_input_bytes':32,
        'verification_receipt_separately_pinned':True})
    print(json.dumps({'status':contract['status'],'selected_decode':pin(OUT/'selected-decode.json'),
        'contract':pin(OUT/'contract.json'),'manifest':pin(OUT/'manifest.json'),'local_pins':len(selected),
        'new_code_read_bytes':13,'new_decoder_input_bytes':16,'own_peak_committed_bytes':GUARD.peak}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--check',action='store_true')
    check() if parser.parse_args().check else main()
