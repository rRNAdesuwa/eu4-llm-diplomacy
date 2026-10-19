"""Prepare the fixed DLL war script/header/config; never executes the game."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.compiler import compile_request
from local_config import user_data

script = compile_request({'id': 'war_auto_01', 'action': 'declare_war', 'target': 'ENG'})
script += '\n' + compile_request({'id': 'war_observe', 'action': 'snapshot'})
assert script.isascii() and ')EU4AUTO"' not in script
native = ROOT / 'work/native'
(native / 'automated-war-script.h').write_text(
    '// Generated fixed template; no caller-provided code.\n'
    'static const char automatic_war_script[]=R"EU4AUTO(' + script + ')EU4AUTO";\n',
    encoding='ascii', newline='\n')
destination = user_data() / 'llm_auto.txt'
destination.write_text(script, encoding='ascii', newline='\n')
(native / 'automatic-war-script.path').write_bytes((str(destination) + '\0').encode('utf-16le'))
print(destination)
