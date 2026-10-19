"""Bounded, file-only evidence for the strict diplomacy cooldown boundary."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile

from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import bounded_cfg

ROOT = Path(__file__).resolve().parents[1]
SHA = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'


def main():
    pe = PE(ROOT.parent / 'eu4.exe')
    assert hashlib.sha256(pe.data).hexdigest() == SHA
    md, _ = make_disassembler(Path(tempfile.gettempdir()) / 'eu4-native-analysis-deps')
    slices = [(0x4e9d00, 0x4e9ff8, 0x4ea099),
              (0x4e9d00, 0x4ea174, 0x4ea1b8),
              (0x35a830, 0x35a830, 0x35a87d),
              (0x14c8030, 0x14c8030, 0x14c811d),
              (0xac6770, 0xac689c, 0xac68c0)]
    evidence = []
    for entry, begin, end in slices:
        function = pe.function(entry)
        assert function and function[0] == entry
        regions = [function]
        # MSVC divides the signed month adder into contiguous unwind regions.
        while regions[-1][1] < end:
            following = pe.function(regions[-1][1])
            assert following and following[0] == regions[-1][1] and len(regions) < 8
            regions.append(following)
        assert end <= regions[-1][1] and regions[-1][1] - entry < 0x1800
        code, _ = bounded_cfg(pe, md, entry, window=0x1800, max_instructions=1200)
        evidence.append(dict(function_start=hex(entry), function_end=hex(regions[-1][1]),
                             unwind_regions=[[hex(v) for v in r] for r in regions],
                             instructions=[dict(rva=hex(i.address), bytes=i.bytes.hex(),
                                                instruction=f'{i.mnemonic} {i.op_str}'.strip())
                                           for i in code if begin <= i.address < end]))
    # This helper is a leaf, absent from .pdata. Decode the complete bounded
    # 53-byte sequence including both return blocks reached by its branches.
    evidence.append(dict(function_start='0x35a7f0', pdata=False,
                         instructions=[dict(rva=hex(i.address), bytes=i.bytes.hex(),
                                            instruction=f'{i.mnemonic} {i.op_str}'.strip())
                                       for i in md.disasm(pe.bytes_at(0x35a7f0, 0x35), 0x35a7f0)]))
    slots = {}
    for name, vtable in [('marriage', 0x1c80ab0), ('alliance', 0x1c80720),
                         ('scriptable', 0x1ce1e28)]:
        rva = struct.unpack('<Q', pe.bytes_at(vtable + 0x100, 8))[0] - pe.base
        assert rva == 0x8f440 and pe.bytes_at(rva, 3) == bytes.fromhex('b001c3')
        slots[name] = dict(vtable=hex(vtable), slot='0x100', rva=hex(rva), returns=True)
    report = dict(schema='EU4TAG31-COOLDOWN-STATIC/1', file_only=True,
                  game_accessed=False, game_sha256=SHA, slots=slots, evidence=evidence,
                  facts=[
                      'The common full check calls 35a7f0 when option=false and virtual+100 is true.',
                      '35a7f0 returns true when current raw date <= pair deadline and game+23a9 is zero.',
                      'That true result clears the common allowed flag; local+80 is still required.',
                      '35a830 adds the signed configured months (233e064) to the action date and writes relation+30.',
                      '14c8030 returns immediately for zero; signed division and negative-month year wrapping are present.',
                      'Setting months=-1 is a test-mod candidate for future writes, not a runtime result or a way to clear saved deadlines.'
                  ], runtime_candidate_verified=False, all_rejections_explained=False,
                  peak_committed_bytes=check_memory_budget())
    out = ROOT / 'work/runtime/tag31-cooldown-static-20261013.json'
    with out.open('x', encoding='utf-8') as target:
        json.dump(report, target, ensure_ascii=False, indent=2)
        target.write('\n')
    print(json.dumps(dict(output=str(out), game_accessed=False,
                          runtime_candidate_verified=False)))


if __name__ == '__main__':
    main()
