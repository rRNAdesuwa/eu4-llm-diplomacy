import hashlib,json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCES=['native_guard.h','native_guard.cpp','environment_binding.h','environment_binding.cpp','test_native_guard.cpp','build_test.cmd','README.md','prepare.py','validate.py','input-pins.json','port/native_platform.h','port/native_pair_engine.h','header-composition.json']
INPUTS=['work/AGENTS.md',
 'work/candidates/v21-core-pair-nosend-1375/validate.py',
 'work/candidates/v21-core-pair-nosend-r2-1375/pair_component.h',
 'work/candidates/v21-core-pair-nosend-r2-1375/pair_component.cpp',
 'work/candidates/v21-core-pair-nosend-r2-1375/review.json',
 'work/review-results/v21-pair-r2-action-catalog-20261008a/review.json',
 'work/candidates/v21-native-pair-port-1375/native_platform.h',
 'work/candidates/v21-native-pair-port-1375/native_pair_engine.h',
 'work/candidates/v21-native-pair-port-1375/component/pair_component.h',
 'work/candidates/v21-native-pair-port-1375/review.json',
 'work/candidates/current-country-tag-cpp-1375/country_resolver.h',
 'work/candidates/current-country-tag-cpp-1375/country_resolver.cpp',
 'work/candidates/current-country-tag-cpp-1375/selected_pins.h',
 'work/candidates/current-country-tag-cpp-1375/test_country_resolver.cpp',
 'work/candidates/current-country-tag-cpp-1375/review.json',
 'work/review-results/current-country-tag-cpp-favor-20261008a/review.json',
 'work/candidates/v21-five-cancel-reader-1375/cancel_reader.h',
 'work/candidates/v21-five-cancel-reader-1375/cancel_reader.cpp',
 'work/candidates/v21-five-cancel-reader-1375/review.json',
 'work/candidates/v21-five-cancel-reader-1375/source-index.json',
 'work/candidates/v19-spy-restricted-host-r2-1375/preflight/native_env.h',
 'work/candidates/v19-spy-restricted-host-r2-1375/preflight/native_env.cpp',
 'work/candidates/v19-spy-restricted-host-r2-1375/preflight/host.h',
 'work/candidates/v19-spy-restricted-host-r2-1375/preflight/codec.h',
 'work/candidates/v19-spy-restricted-host-r2-1375/core/v18-preimage/spy_core.h',
 'work/candidates/v19-spy-restricted-host-r2-1375/review.json',
 'work/review-results/v19-host-r2-native-inventory-20261008a/review.json']
def raw(p):
    assert p.stat().st_size<=4*1024*1024
    return p.read_bytes()
def desc(p):
    data=raw(p);return dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
def write(p,obj):
    with p.open('xb') as f:f.write((json.dumps(obj,sort_keys=True,indent=2)+'\n').encode('ascii'))
def main():
    check='--check' in sys.argv
    inputs={p:desc(ROOT/p) for p in INPUTS}
    if check:assert json.loads(raw(HERE/'input-pins.json'))==inputs
    else:write(HERE/'input-pins.json',inputs)
    sources={p:desc(HERE/p) for p in SOURCES}
    if check:assert json.loads(raw(HERE/'source-index.json'))==sources
    else:write(HERE/'source-index.json',sources)
    print(json.dumps(dict(check=check,inputs=len(inputs),sources=len(sources),new_decode_bytes=0)))
if __name__=='__main__':main()
