"""Offline direct-call cross references, confirmed with objdump disassembly.

No live process access. This cannot recover indirect calls or function ABI.
"""
from pathlib import Path
import bisect
import contextlib
import io
import json
import re
import runpy
import struct
import subprocess

from local_config import get_value

ROOT = Path(__file__).resolve().parent
with contextlib.redirect_stdout(io.StringIO()):
    context = runpy.run_path(str(ROOT / 'map_native_peace_candidates.py'))
data, sections, functions, starts = (context[key] for key in ('data', 'sections', 'functions', 'starts'))
image_base = context['image_base']
targets = {}
for target in context['report']['targets']:
    for reference in target['references']:
        if reference['function_rva_range']:
            start = int(reference['function_rva_range'][0], 16)
            targets[start] = {'label': target['label'], 'function_rva': hex(start), 'direct_call_candidates': []}
for section in sections:
    if not section['flags'] & 0x20000000:
        continue
    body = data[section['raw']:section['raw'] + section['size']]
    for match in re.finditer(rb'\xe8....', body, re.DOTALL):
        address = section['rva'] + match.start()
        destination = address + 5 + struct.unpack_from('<i', match.group(), 1)[0]
        if destination not in targets:
            continue
        index = bisect.bisect_right(starts, address) - 1
        caller = functions[index] if index >= 0 and address < functions[index][1] else None
        confirmed = False
        if caller:
            # Decode from the recorded function start so a byte inside another
            # instruction cannot be mistaken for a CALL opcode.
            result = subprocess.run([
                get_value('EU4_OBJDUMP'), '-d',
                f'--start-address={hex(image_base + caller[0])}',
                f'--stop-address={hex(image_base + address + 5)}', str(context['GAME']),
            ], capture_output=True, text=True, check=True)
            target_line = re.search(rf'^\s*{image_base + address:x}:.*$', result.stdout, re.M)
            confirmed = bool(target_line and re.search(r'\bcallq?\s+(?:0x)?' + f'{image_base + destination:x}', target_line.group()))
        targets[destination]['direct_call_candidates'].append({
            'call_rva': hex(address), 'caller_rva_range': [hex(v) for v in caller] if caller else None,
            'disassembly_confirmed': confirmed,
        })
output = ROOT / 'runtime/native-peace-callers.json'
output.write_text(json.dumps({'binary_sha256': context['report']['binary_sha256'],
    'targets': list(targets.values()), 'limitations': 'Direct CALL only. Candidate function meaning and signature remain unverified.'}, indent=2), encoding='utf-8')
for target in targets.values():
    refs = target['direct_call_candidates']
    print(target['label'], 'confirmed direct callers:', sum(item['disassembly_confirmed'] for item in refs))
    for item in refs[:8]:
        print(item)
