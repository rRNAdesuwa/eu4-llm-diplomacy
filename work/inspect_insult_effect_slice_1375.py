"""Read bounded, pinned existing insult evidence; no game or native calls."""
import hashlib
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'work/reports/native-pair-extension-v11-1375.json'
EXPECTED = 'ac4559379e218aaf1fa8ffc1dd7dc6b8332ed5b7bf681c4b66bfc59349944344'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=lambda value:int(value,16))
    parser.add_argument('--end', type=lambda value:int(value,16))
    args = parser.parse_args()
    if (args.start is None) != (args.end is None):
        raise ValueError('Supply both bounded slice endpoints')
    if args.start is not None and not (0x5378f0 <= args.start < args.end <= 0x538700 and args.end-args.start <= 0x600):
        raise ValueError('Requested slice exceeds selected function/window')
    if not 0 < PATH.stat().st_size <= 5 * 1024 * 1024:
        raise ValueError('Parent report exceeds budget')
    raw = PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED:
        raise ValueError('Parent report changed')
    parent = json.loads(raw)
    function = parent['functions']['0x5378f0']
    instructions = function['instructions']
    if len(instructions) > 4000:
        raise ValueError('Instruction count exceeds bound')
    selected = [row for row in instructions if row['instruction'].startswith('call ')]
    output = selected if args.start is None else [row for row in instructions if args.start <= int(row['rva'],16) < args.end]
    for row in output:
        print(json.dumps(row,ensure_ascii=False))
    print(json.dumps({'parent_sha256':EXPECTED,'instruction_count':len(instructions),
                      'call_count':len(selected),'game_accessed':False}))

if __name__ == '__main__':
    main()
