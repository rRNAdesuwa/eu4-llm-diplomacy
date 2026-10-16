"""Compare raw native peace snapshots; differing fields are not automatically named."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('before', type=Path)
parser.add_argument('after', type=Path)
args = parser.parse_args()
def window(path):
    matches = json.loads(path.read_text(encoding='utf-8'))['peace_ui_probe']['matches']
    if len(matches) != 1:
        raise ValueError('Expected exactly one validated peace window')
    return matches[0]
a, b = window(args.before), window(args.after)
if a['recipient_handle'] != b['recipient_handle']:
    raise ValueError('Recipient changed between observations')
for key in ('proposal_48_hex', 'proposal_208_hex'):
    x, y = bytes.fromhex(a[key]), bytes.fromhex(b[key])
    print(key)
    for i in range(0, len(x), 4):
        if x[i:i+4] != y[i:i+4]:
            print(f'+{i:#05x}: {x[i:i+4].hex()} -> {y[i:i+4].hex()} '
                  f'(u32 {int.from_bytes(x[i:i+4], "little")} -> {int.from_bytes(y[i:i+4], "little")})')
