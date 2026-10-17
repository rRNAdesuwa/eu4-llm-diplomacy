"""Disassemble one explicit, hash-bound range of at most 0x8000 bytes offline."""
import argparse
import hashlib
from pathlib import Path
import subprocess

from local_config import game_exe, get_value


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("start", type=lambda value: int(value, 0))
parser.add_argument("end", type=lambda value: int(value, 0))
parser.add_argument("output", type=Path)
args = parser.parse_args()
if not 0x1000 <= args.start < args.end <= 0x1b66000 or args.end - args.start > 0x8000:
    raise SystemExit("Expected a bounded .text RVA range")
game = game_exe()
digest = hashlib.sha256()
with game.open("rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
if digest.hexdigest() != "b23fa0e1f698d31b01cdd1c3817a675805d8c6286cb66f9c231e6e2a42544d77":
    raise SystemExit("Unsupported PE hash")
if args.output.exists():
    raise SystemExit("Evidence exists; choose a new output")
result = subprocess.run([
    get_value("EU4_OBJDUMP"), "-d", "-M", "intel",
    f"--start-address={hex(0x140000000 + args.start)}",
    f"--stop-address={hex(0x140000000 + args.end)}", str(game),
], capture_output=True, text=True, check=True, timeout=30)
with args.output.open("x", encoding="utf-8") as output:
    output.write(result.stdout)
print(f"{args.start:#x}–{args.end:#x}: {args.output}")
