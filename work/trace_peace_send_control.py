"""Offline exact GUI control-name references; not a sender implementation."""
import contextlib
import io
import json
from pathlib import Path
import re
import runpy
import struct
import bisect

root = Path(__file__).resolve().parent
with contextlib.redirect_stdout(io.StringIO()):
    context = runpy.run_path(str(root / 'map_native_peace_candidates.py'))
data = context['data']
targets = {}
for word in (b'send', b'reset_button', b'suggest_peace_button', b'surrender_button'):
    for match in re.finditer(rb'\x00' + re.escape(word) + rb'\x00', data):
        rva = context['offset_to_rva'](match.start() + 1)
        if rva is not None:
            targets[rva] = word.decode()
refs = []
for section in context['sections']:
    if not section['flags'] & 0x20000000:
        continue
    body = data[section['raw']:section['raw'] + section['size']]
    for match in re.finditer(rb'[\x48-\x4f][\x8d\x8b][\x05\x0d\x15\x1d\x25\x2d\x35\x3d]....', body, re.S):
        rva = section['rva'] + match.start()
        target = rva + 7 + struct.unpack_from('<i', match.group(), 3)[0]
        if target in targets:
            index = bisect.bisect_right(context['starts'], rva) - 1
            function = context['functions'][index] if index >= 0 and rva < context['functions'][index][1] else None
            refs.append({'control': targets[target], 'instruction_rva': hex(rva),
                         'function_rva_range': [hex(x) for x in function] if function else None})
output = root / 'runtime/peace-control-references.json'
output.write_text(json.dumps(refs, indent=2), encoding='utf-8')
for ref in refs:
    if ref['control'] != 'send' or 0x12f0000 <= int(ref['instruction_rva'], 16) < 0x1320000:
        print(ref)
print('All control candidates saved:', len(refs))
