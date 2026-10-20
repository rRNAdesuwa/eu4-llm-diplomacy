"""Locate the reference frame prologue in this binary; do not install a hook."""
import contextlib
import io
import json
from pathlib import Path
import runpy
import subprocess

from local_config import get_value

root = Path(__file__).resolve().parent
with contextlib.redirect_stdout(io.StringIO()):
    context = runpy.run_path(str(root / 'map_native_peace_candidates.py'))
signature = bytes.fromhex('4c89442418555357488d6c24b04881ec50010000')
data = context['data']
offsets = []
position = 0
while True:
    position = data.find(signature, position)
    if position < 0:
        break
    offsets.append(position)
    position += 1
entries = []
for offset in offsets:
    rva = context['offset_to_rva'](offset)
    address = context['image_base'] + rva
    result = subprocess.run([get_value('EU4_OBJDUMP'), '-d',
        f'--start-address={hex(address)}', f'--stop-address={hex(address + 128)}', str(context['GAME'])],
        capture_output=True, text=True, check=True)
    path = root / f'runtime/frame-candidate-{rva:x}.txt'
    path.write_text(result.stdout, encoding='utf-8')
    entries.append({'rva': hex(rva), 'file_offset': hex(offset), 'disassembly': str(path)})
output = root / 'runtime/frame-candidates.json'
output.write_text(json.dumps({'binary_sha256': context['report']['binary_sha256'], 'signature': signature.hex(),
    'candidates': entries, 'status': 'Exact prologue match only; runtime frequency and thread not verified.'}, indent=2), encoding='utf-8')
print(json.dumps(entries))
