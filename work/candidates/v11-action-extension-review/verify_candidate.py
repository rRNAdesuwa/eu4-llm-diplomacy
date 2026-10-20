"""Offline reproducibility, matrix, PE pins, strict compile and synthetic tests."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import prepare

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def sha(data):return hashlib.sha256(data).hexdigest()
def require(value,message):
    if not value:raise ValueError(message)
def table(source):
    return source.split('constexpr Action kActions[] = {',1)[1].split('\n};',1)[0]

def main():
    # generate() is read-only. Comparison includes all generated code and diff.
    expected=prepare.generate()
    for name,content in expected.items():require((HERE/name).read_bytes()==content,'Unreproducible: '+name)
    review=json.loads(expected['review.json']);matrix=json.loads(expected['mode-matrix.json'])
    sources={name:(HERE/'generated'/name).read_text(encoding='utf-8') for name in prepare.BASES}
    core=sources['pair-engine-1375.cpp'];life=sources['pair-probe-v6-1375.cpp']
    names_tokens=re.findall(r'\{"([a-z_]+)", (0x[0-9a-f]+),',table(life))
    require(len(names_tokens)==20 and len(set(names_tokens))==20,'Lifecycle family count/uniqueness')
    tokens=[int(token,16) for _,token in names_tokens]
    require([int(x,16) for x in re.findall(r'\{(0x[0-9a-f]+),',table(core))]==tokens,'Core/lifecycle table mismatch')
    mode_body=core.split('constexpr ModeMapping kModes[] = {',1)[1].split('\n};',1)[0]
    modes=[(int(a),b=='true') for a,b in re.findall(r'\{(\d+), (true|false)\}',mode_body)]
    require(len(modes)==36 and len(set(modes))==36,'36 distinct real modes')
    positive_only={0x2942,0x2947,0x2948,0x3bce}
    required={(i,value) for i,token in enumerate(tokens) for value in (True,False) if value or token not in positive_only}
    require(set(modes)==required,'Fake cancel or missing real mode')
    expected_cases={(target,index,value) for target in ('ENG','POR') for index,value in required}
    actual=[(case['target'],case['family_index'],case['value']) for case in matrix['cases']]
    require(len(actual)==72 and set(actual)==expected_cases,'72 unique target/mode cases')
    for name in ('pair-preview-v6-1375.cpp','pair-command-v6-1375.cpp'):
        source=sources[name]
        require(re.findall(r'\{"([a-z_]+)", (0x[0-9a-f]+),',table(source))==names_tokens,'Phase table mismatch '+name)
        require('mode < v11_mode_count(action.token)' in source and 'return count == 72;' in source,'Phase loop contract '+name)
        mode_helper=source.split('unsigned v11_mode_count',1)[1].split('\n}',1)[0]
        require({int(x,16) for x in re.findall(r'token == (0x[0-9a-f]+)',mode_helper)}==positive_only,'Phase fake cancel '+name)
    for name,source in sources.items():
        if name.endswith('.cpp'):
            require(all(field in source for field in ('fixed_subsidy_amount_milli','fixed_subsidy_duration_years','fixed_gift_amount_milli','fixed_transfer_fraction_milli','fixed_insult_index')),'Missing fixed-field audit '+name)
    pe=prepare.PE(ROOT.parent/'eu4.exe')
    for rva,raw in review['prefixes'].items():
        data=bytes.fromhex(raw);require(pe.bytes_at(int(rva,16),len(data))==data,'PE prefix changed '+rva)
    for item in review['method_slots']:
        actual_method=pe.u64(pe.to_offset(int(item['vtable'],16)+int(item['slot'],16)))-pe.base
        require(actual_method==int(item['method'],16),'PE method mismatch')
    # Only our synthetic executable is built/run. No DLL, process probe or injector.
    completed=subprocess.run([os.environ.get('COMSPEC','cmd.exe'),'/d','/c',str(HERE/'test_extension.cmd')],
        cwd=ROOT,check=True,capture_output=True,text=True,timeout=120)
    match=re.search(r'v11 synthetic extension: (\d+) checks, 0 failures; no engine or process calls\.',completed.stdout)
    require(match is not None,'Synthetic suite did not pass')
    sources_to_pin=list(prepare.BASES)
    payload={'schema':1,'purpose':'offline_candidate_review_only','review_sha256':sha(expected['review.json']),
        'families':20,'action_ids':36,'positive_only_families':4,'lifecycle_cases':20,'preview_cases':72,'command_cases':72,
        'synthetic_memory_checks':int(match.group(1)),'synthetic_failures':0,'compiler_flags':'/std:c++17 /O2 /W4 /WX /MT /GS',
        'compiled_translation_units':4,'dll_built':False,'process_access':False,'runtime_verified':False,'execution_verified':False,
        'verified_method_slots':len(review['method_slots']),'verified_prefixes':len(review['prefixes']),
        'generated_source_sha256':{name:sha((HERE/'generated'/name).read_bytes()) for name in sources_to_pin},
        'review_tool_sha256':{name:sha((HERE/name).read_bytes()) for name in ('prepare.py','verify_candidate.py','binding-helpers.inc','fixed-fields.inc','test_extension.cpp','test_extension.cmd')},
        'compiler_and_test_stdout':completed.stdout}
    raw=(json.dumps(payload,indent=2)+'\n').encode();(HERE/'validation.json').write_bytes(raw)
    print(json.dumps({k:payload[k] for k in ('families','action_ids','synthetic_memory_checks','verified_method_slots','verified_prefixes','runtime_verified')}))
    print('validation_sha256='+sha(raw))

if __name__=='__main__':main()
