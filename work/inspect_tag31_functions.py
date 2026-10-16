"""Bounded function inspection for the eight-category native command expansion."""
import sys, tempfile
from pathlib import Path
from discover_diplomacy import PE, make_disassembler, check_memory_budget
from map_diplomacy_fields import bounded_cfg

ROOT = Path(__file__).resolve().parents[1]
pe = PE(ROOT.parent / 'eu4.exe')
md, _ = make_disassembler(Path(tempfile.gettempdir()) / 'eu4-native-analysis-deps')
for text in sys.argv[1:]:
    address = int(text, 16)
    code, edges = bounded_cfg(pe, md, address, window=0x1800, max_instructions=1200)
    print('FUNCTION', hex(address))
    for ins in code:
        print(hex(ins.address), ins.mnemonic, ins.op_str)
    print('EDGES', edges)
    check_memory_budget()
