"""Read-only PE/RIP reference inventory, without modifying or attaching to EU4.

Byte-pattern matches are candidates, not disassembly proof or callable APIs.
"""
from pathlib import Path
import bisect
import hashlib
import json
import re
import struct

from local_config import game_exe

GAME = game_exe()
data = GAME.read_bytes()
pe = struct.unpack_from('<I', data, 0x3c)[0]
assert data[pe:pe + 4] == b'PE\0\0'
machine, count = struct.unpack_from('<HH', data, pe + 4)
assert machine == 0x8664, 'Only x64 PE is supported'
optional_size = struct.unpack_from('<H', data, pe + 20)[0]
optional = pe + 24
assert struct.unpack_from('<H', data, optional)[0] == 0x20b
image_base = struct.unpack_from('<Q', data, optional + 24)[0]
sections = []
for index in range(count):
    header = optional + optional_size + index * 40
    name = data[header:header + 8].rstrip(b'\0').decode('ascii')
    virtual_size, rva, raw_size, raw = struct.unpack_from('<IIII', data, header + 8)
    flags = struct.unpack_from('<I', data, header + 36)[0]
    sections.append(dict(name=name, rva=rva, raw=raw, size=raw_size, flags=flags))

def offset_to_rva(offset):
    for section in sections:
        if section['raw'] <= offset < section['raw'] + section['size']:
            return section['rva'] + offset - section['raw']
    return None

functions = []
for section in sections:
    if section['name'] == '.pdata':
        for offset in range(section['raw'], section['raw'] + section['size'] - 11, 12):
            start, end, unwind = struct.unpack_from('<III', data, offset)
            if 0 < start < end:
                functions.append((start, end))
functions.sort()
starts = [item[0] for item in functions]

labels = [b'CPeaceOffer::Execute, %d', b'MUST_WAIT_UNTIL_NEXT_PEACE_OFFER',
          b'OFFER_PEACE_PENDING_ENFORCE', b'Attempted to open peace offer screen when not actually a proposal',
          b'diplomaticactioncommand', b'set_war_peace_command']
targets = {}
for label in labels:
    offset = data.find(label + b'\0')
    if offset >= 0:
        targets[offset_to_rva(offset)] = {'label': label.decode(), 'string_rva': hex(offset_to_rva(offset)), 'references': []}

pattern = re.compile(rb'[\x48-\x4f][\x8d\x8b][\x05\x0d\x15\x1d\x25\x2d\x35\x3d]....', re.DOTALL)
for section in sections:
    if not section['flags'] & 0x20000000:
        continue
    body = data[section['raw']:section['raw'] + section['size']]
    for match in pattern.finditer(body):
        instruction_rva = section['rva'] + match.start()
        target = instruction_rva + 7 + struct.unpack_from('<i', match.group(), 3)[0]
        if target not in targets:
            continue
        index = bisect.bisect_right(starts, instruction_rva) - 1
        function = None
        if index >= 0 and instruction_rva < functions[index][1]:
            function = [hex(value) for value in functions[index]]
        targets[target]['references'].append({'instruction_rva': hex(instruction_rva), 'function_rva_range': function})

report = {'binary_sha256': hashlib.sha256(data).hexdigest(), 'image_base': hex(image_base),
          'warning': 'Static byte-pattern candidates only. No signature, object layout or callable sender established.',
          'targets': list(targets.values())}
output = Path(__file__).resolve().parent / 'runtime/native-peace-candidates.json'
output.write_text(json.dumps(report, indent=2), encoding='utf-8')
for target in report['targets']:
    print(target['label'], 'candidate references:', len(target['references']))
print('Saved', output)
