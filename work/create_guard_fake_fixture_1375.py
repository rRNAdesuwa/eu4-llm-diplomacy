from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'work/candidates/v21-native-pair-port-r2-1375/test_native_pair_engine.cpp').read_text()
begin=source.index('struct Fake final:Platform {');end=source.index('struct Guard: SyntheticGuard',begin)
body=source[begin:end].replace('CHECK(', 'assert(')
out=ROOT/'work/candidates/v21-native-pair-guard-r2-1375/fake_platform.h'
header='#pragma once\n#include "native_guard.h"\n#include <cassert>\n#include <cstring>\n#include <functional>\n#include <map>\n#include <vector>\nnamespace fixture {\nusing namespace v21pair;using namespace v21port;\n'
with out.open('x',newline='\n') as f:f.write(header+body+'}\n')
