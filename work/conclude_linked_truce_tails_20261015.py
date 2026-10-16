"""R26 retained-tail conclusions/corrigendum only; no decoder or new code read."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT/'work/reports/war-peace-api-20261015-r26-linked-truce-tails/war'
MANIFEST_SHA = 'e73c64d929f38504ee1f3ac570e7a4e1997838e8fcf1858fabfd9cb825f5627a'


def pin(path):
    digest = hashlib.sha256(); size = 0
    with path.open('rb') as stream:
        while raw := stream.read(65536): size += len(raw); digest.update(raw)
    return {'bytes':size,'sha256':digest.hexdigest()}


def load(path):
    assert path.stat().st_size <= 1024*1024
    return json.loads(path.read_bytes().decode('utf-8'))


def write_new(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(value if isinstance(value,str) else json.dumps(value,indent=2)+'\n')


def fixed_manifest():
    assert pin(HERE/'manifest.json')['sha256'] == MANIFEST_SHA
    m = load(HERE/'manifest.json'); assert m['sealed'] is True
    for name,wanted in m['source_pins'].items(): assert pin(ROOT/name) == wanted,name
    for name,wanted in m['artifact_pins'].items(): assert pin(Path(name)) == wanted,name
    return m


def check():
    base = fixed_manifest(); m = load(HERE/'conclusions-manifest.json'); assert m['sealed'] is True
    for name,wanted in m['source_pins'].items(): assert pin(ROOT/name) == wanted,name
    assert m['base_manifest_sha256'] == MANIFEST_SHA
    print(json.dumps({'status':'pass','base_local_pins':len(base['source_pins']),
        'base_artifact_pins':len(base['artifact_pins']),'conclusion_local_pins':len(m['source_pins']),
        'new_code_reads':0,'decoder_executed':False,'target_process_accessed':False}))


def main():
    m = fixed_manifest(); d = load(HERE/'selected-decode.json'); c = load(HERE/'contract.json')
    assert pin(HERE/'selected-decode.json') == {'bytes':29646,'sha256':'e59486834e38e541a243353b73673fb0e1170724282f258c86cb106ad2b5fb52'}
    false, byte = d['new_tails']
    assert false['raw_hex'] == '4883c4205bc3'
    assert byte['raw_hex'] == '90488bc8e897cfcaffcc'
    assert [(row['rva'],row['bytes'],row['mnemonic'],row['operands']) for row in false['instructions']] == [
        ('0x2f160d','4883c420','add','rsp, 0x20'),('0x2f1611','5b','pop','rbx'),('0x2f1612','c3','ret','')]
    assert [(row['rva'],row['bytes'],row['mnemonic'],row['operands']) for row in byte['instructions']] == [
        ('0x7ae2e0','90','nop',''),('0x7ae2e1','488bc8','mov','rcx, rax'),
        ('0x7ae2e4','e897cfcaff','call','0x45b280'),('0x7ae2e9','cc','int3','')]
    call = bytes.fromhex('e897cfcaff')
    assert 0x7ae2e4+5+struct.unpack('<i',call[1:])[0] == 0x45b280
    assert c['status'] == 'unknown_tail_semantics'
    assert c['byte_7a']['returns_to_selected_byte_load'] is False
    assert 'before its jump' in c['byte_7a']['post_45b260_validation']
    assert d['retained_decoded_bytes'] == 253 and d['new_decoder_input_bytes'] == 16
    assert d['complete_joined_instruction_bytes'] == 269
    assert sum(row['bytes'] for row in d['PE_read_accounting']['new_code_reads']) == 13
    first = load(HERE/'attempt-01/failure.json'); first_source = (HERE/'attempt-01/producer.py').read_text(encoding='utf-8')
    first_tree = ast.parse(first_source)
    calls = [node for node in ast.walk(first_tree) if isinstance(node,ast.Call)
        and isinstance(node.func,ast.Attribute) and node.func.attr == 'code'
        and isinstance(node.func.value,ast.Name) and node.func.value.id == 'pe']
    assert [[arg.value for arg in node.args] for node in calls] == [[0x2f1610,3],[0x7ae2e0,10]]
    assert "assert not any(row['mnemonic'] == 'call'" in first_source.splitlines()[239]
    assert first['failure_stage'] == 'after both exact code reads and both tail decodes, before any output write'
    assert first['raw_tails_retained'] is False and first['decoder_input_bytes'] == 16
    transcript = load(HERE/'attempt-01/tool-result.json')
    assert transcript['exit_code'] == 1 and 'line 240, in main' in transcript['output']
    second = load(HERE/'attempt-02/tool-result.json')['result']
    assert second['exit_code'] == 0 and '"new_decoder_input_bytes": 16' in second['output']
    result = {'schema':'EU4-R26-LINKED-TRUCE-TAILS-CONCLUSIONS-CORRIGENDUM/1',
        'status':'selected_tail_bytes_verified_false_RET_closed_and_call_INT3_tail_identified',
        'base_manifest':pin(HERE/'manifest.json'),'base_sources_unchanged':True,
        'conclusion_prepublication_correction':'Initial file-only conclusions run used defaultGBK when reading its UTF8 producerpreimage and stopped before writes. Corrected to explicitUTF8; no codewindow read/decoder/source-evidence change.',
        'false_2f':{'prior_AL_zero':'0x2f160b XOR AL,AL','tail_raw':'4883c4205bc3',
            'tail':'ADD RSP,0x20; POP RBX; RET','false_normal_RET':'0x2f1612',
            'other_retained_normal_RET':'0x2f160a','selected_normal_AL':'0or1; no fullRAX normalization claim',
            'ordinary_false_epilogue_closed':True,'callee_contracts_or_exception_paths_closed':False},
        'tail_7ae':{'raw':'90488bc8e897cfcaffcc',
            'instructions':'NOP; MOV RCX,RAX; CALL0x45b280; INT3',
            'preceding_call':'0x7ae2db ->0x45b260','additional_callsite':'0x7ae2e4',
            'additional_unfollowed_callee':'0x45b280','callee_argument_assignment':'RCX receives preceding45b260 RAX; other call state not upgraded',
            'if_45b260_returns_normally':'executesNOP, thenMOV RCX,RAX andCALL45b280',
            'if_45b280_returns_normally':'next instructionINT3 at0x7ae2e9',
            'normal_RET_in_new_tail':False,'jump_back_to_7ae2be_in_new_tail':False,
            'prior_other_branch_byte_RET':'0x7ae2be MOVZX EAX,byte[RAX] ->normalRET7ae2c6',
            'all_7ae_normal_paths_closed':False,'callee_nonreturn_proven':False,
            'SEH_or_exception_class_or_business_operation_proven':False},
        'corrigenda':[{'source':'sealed contract.json byte_7a.post_45b260_validation',
            'obsolete_phrase':'before its jump','cause':'old template residual; actual selected tail has nojump',
            'replacement':'MOV RCX,RAX; CALL45b280; if normalreturn executesINT3; no normalRET or jumpback in this tail.',
            'original_artifact_modified':False},
            {'source':'sealed contract.json status=unknown_tail_semantics',
             'clarification':'Retained tail instructions and absence of jump/normalRET are now explicit facts; unknown remains callee/exception semantics. This does not promote all paths to normal completion.'}],
        'accounting':{'attempt01_code_reads':2,'attempt01_physical_code_bytes':13,'attempt01_decoder_input':16,
            'attempt01_raw_retained':False,'attempt01_count_grade':'source AST plus complete retained tool-error transcript witness',
            'attempt02_code_reads':2,'attempt02_physical_code_bytes':13,'attempt02_decoder_input':16,
            'cumulative_physical_code_reads':4,'cumulative_physical_code_bytes':26,'cumulative_decoder_input':32,
            'unique_new_code_coverage':13,'unique_new_instruction_input':16,'reused_partial_raw_now_decoded':3,
            'retained_old_decode':253,'joined_instruction_bytes':269,
            'no_whole_function_redecode':True,'new_code_read_by_this_conclusions_script':0},
        'resources':{'attempt02_own_peak_committed_bytes':23953408,'memory_guard_bytes':805306368,
            'hard_stop_bytes':1073741824,'hard_job_object_installed':False,'attempt01_peak_not_retained':True},
        'unchanged_unknowns':['all five7ae callees including new45b280 effects/lifetime/failure',
            'R9/R10 preservation across2f externalcall','literal232e9c8/1c38150 contents','businessclasses/ownership',
            'transitivepurepredicate','truceobject/expiry/dateunits/removed','peacecompletion/requestcausality','worldlease/atomicity'],
        'authority':c['authority'],'new_decode_bytes_this_conclusion':0,'target_process_accesses':0,
        'Frida_operations':0,'game_native_calls':0,'requests_published':0,'tests_run':0,
        'independent_review_completed':False}
    write_new(HERE/'conclusions.json',result)
    write_new(HERE/'conclusions.md',
        '# R26 尾部结论与独立补正\n\n'
        '2f160d..13为4883c4205bc3：ADD RSP20、POP RBX、RET2f1612。此前2f160b清AL的false普通返回闭合。\n\n'
        '7ae2e0..ea为90488bc8e897cfcaffcc：NOP、MOV RCX,RAX、CALL45b280、INT3。没有跳回7ae2be，'
        '若45b280正常返回则执行INT3；未展开它，不声称nonreturncallee、SEH或任何异常class。其他已保留分支仍有byte-return7ae2c6，不能称所有普通路径closed。\n\n'
        '原sealed合同“before its jump”为模板残留，以本文件明确替代；原manifest e73c64d9…与全部原文件保持。\n\n'
        '首轮错误断言无tailCALL后失败、raw未留，前像与完整tool-error转录保留，计数仅producer/trace见证。root授权同窗口修复一次：'
        '累计物理code读26B/4seek，decoder输入32B；唯一新覆盖13B、唯一新指令16B（含旧partial3），拼接旧253B共269B。'
        '本补正仅文件重放，0新code读取/解码/游戏/Frida/native/test；所有authority仍false。\n')
    write_new(HERE/'verification.json',{'schema':'EU4-R26-FILE-VERIFICATION/1','status':'pass',
        'base_manifest':pin(HERE/'manifest.json'),'base_local_pins':len(m['source_pins']),
        'base_artifact_pins':len(m['artifact_pins']),'tail_raw_and_rel32_replayed':True,
        'first_failure_counts_checked_from_source_and_tool_transcript':True,
        'conclusions':pin(HERE/'conclusions.json'),'new_decode_bytes':0,'new_code_reads':0,
        'tests_run':0,'target_process_accesses':0,'game_native_calls':0})
    paths = [HERE/name for name in ('manifest.json','selected-decode.json','contract.json','preparation.json',
        'report.md','attempt-01/producer.py','attempt-01/failure.json','attempt-01/tool-result.json',
        'attempt-02/tool-result.json','conclusions.json','conclusions.md','verification.json')]+[Path(__file__).resolve()]
    write_new(HERE/'conclusions-manifest.json',{'schema':'EU4-R26-CONCLUSIONS-MANIFEST/1','sealed':True,
        'base_manifest_sha256':MANIFEST_SHA,'source_pins':{p.relative_to(ROOT).as_posix():pin(p) for p in paths},
        'native_ready':False,'base_artifacts_unchanged':True})
    print(json.dumps({'status':result['status'],'conclusions':pin(HERE/'conclusions.json'),
        'conclusions_manifest':pin(HERE/'conclusions-manifest.json'),'verification':pin(HERE/'verification.json')}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true')
    check() if parser.parse_args().check else main()
