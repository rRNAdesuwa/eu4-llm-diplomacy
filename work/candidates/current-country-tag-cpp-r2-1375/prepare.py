import ast
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
FILES=['country_resolver.h','country_resolver.cpp','selected_pins.h','test_country_resolver.cpp','README.md','prepare.py','validate.py','build_test.cmd','input-pins.json']
INPUTS=['work/AGENTS.md',
 'work/candidates/current-country-tag-resolver-1375/layout.py',
 'work/candidates/current-country-tag-resolver-1375/resolver.py',
 'work/candidates/current-country-tag-resolver-1375/review.json',
 'work/candidates/current-country-tag-resolver-1375/source-index.json',
 'work/review-results/current-country-tag-resolver-independent-20261008a/review.json',
 'work/review-results/current-country-tag-resolver-independent-20261008a/report.json',
 'work/review-results/current-country-tag-resolver-independent-20261008a/validation.json',
 'work/candidates/v21-core-pair-nosend-1375/validate.py']
def raw(p):
    assert p.stat().st_size<=4*1024*1024
    return p.read_bytes()
def desc(p):
    data=raw(p);return dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
def pins():
    layout=ast.parse(raw(ROOT/INPUTS[1]).decode('utf-8'))
    value=next(ast.literal_eval(n.value) for n in layout.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CODE_PINS' for t in n.targets))
    rows=[]
    for rva,h in value:
        data=bytes.fromhex(h);assert 1<=len(data)<=8
        rows.append('    CodePin{0x%x, {%s}, %d},'%(rva,','.join('0x%02x'%b for b in data),len(data)))
    text='#pragma once\n#include <array>\n#include <cstdint>\nnamespace country1375 {\nstruct CodePin { std::uint32_t rva; std::array<std::uint8_t,8> bytes; std::uint32_t length; };\ninline constexpr std::array<CodePin,%d> SelectedPins{{\n%s\n}};\n}\n'%(len(value),'\n'.join(rows))
    return text.encode('ascii')
def jsonbytes(obj):return (json.dumps(obj,indent=2,sort_keys=True)+'\n').encode('ascii')
def main():
    check='--check' in sys.argv
    expected=pins()
    if check:assert raw(HERE/'selected_pins.h')==expected
    else:
        with (HERE/'selected_pins.h').open('xb') as f:f.write(expected)
    inputs={name:desc(ROOT/name) for name in INPUTS}
    if check:assert json.loads(raw(HERE/'input-pins.json'))==inputs
    else:
        with (HERE/'input-pins.json').open('xb') as f:f.write(jsonbytes(inputs))
    sources={name:desc(HERE/name) for name in FILES}
    if check:assert json.loads(raw(HERE/'source-index.json'))==sources
    else:
        with (HERE/'source-index.json').open('xb') as f:f.write(jsonbytes(sources))
    print(json.dumps(dict(check=check,inputs=len(inputs),sources=len(sources),new_decode_bytes=0)))
if __name__=='__main__':main()
