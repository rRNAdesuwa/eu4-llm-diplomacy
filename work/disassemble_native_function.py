"""Bounded offline disassembly from the PE function table; never attaches to EU4."""
import argparse
import bisect
import contextlib
import io
from pathlib import Path
import runpy
import subprocess

from local_config import get_value

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('rva', type=lambda value: int(value, 0))
parser.add_argument('output', type=Path)
args = parser.parse_args()
with contextlib.redirect_stdout(io.StringIO()):
    pe = runpy.run_path(str(Path(__file__).with_name('map_native_peace_candidates.py')))
index = bisect.bisect_right(pe['starts'], args.rva) - 1
if index < 0:
    raise SystemExit('No matching PE function')
start, end = pe['functions'][index]
if not start <= args.rva < end or end - start > 0x20000:
    raise SystemExit('Address outside a bounded PE function')
result = subprocess.run([get_value('EU4_OBJDUMP'), '-d',
    f'--start-address={hex(pe["image_base"] + start)}',
    f'--stop-address={hex(pe["image_base"] + end)}', str(pe['GAME'])],
    capture_output=True, text=True, check=True)
args.output.write_text(result.stdout, encoding='utf-8')
print(f'{start:#x}–{end:#x}: {args.output}')
