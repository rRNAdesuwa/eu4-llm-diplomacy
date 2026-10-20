"""Exact direct-call byte candidates for the selected console UI chain."""
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"work"))
from discover_diplomacy import PE, check_memory_budget


def main():
    pe = PE(ROOT.parent/"eu4.exe")
    sha = hashlib.sha256(pe.data).hexdigest()
    assert sha == "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
    targets = (0x166CB30, 0x166DE20, 0x166D1F0, 0x166D230, 0x166D450, 0x166D4D0, 0x166D5E0, 0x1560B60)
    result = {hex(t): [] for t in targets}
    for section in pe.sections:
        if not section["flags"] & 0x20000000:
            continue
        at, end = section["raw"], section["raw"]+section["size"]-4
        while True:
            at = pe.data.find(b"\xe8", at, end)
            if at < 0:
                break
            rva = pe.to_rva(at)
            target = rva+5+struct.unpack_from("<i", pe.data, at+1)[0]
            if target in targets:
                function = pe.function(rva)
                result[hex(target)].append(dict(rva=hex(rva), raw_bytes=pe.data[at:at+5].hex(),
                    owner=[hex(x) for x in function] if function else None,
                    evidence_kind="direct_call_byte_candidate"))
                assert sum(len(rows) for rows in result.values()) <= 128
            at += 1
    report = dict(schema="EU4-CONSOLE-UI-DIRECT-CALL-SEEDS/1", game_sha256=sha,
        targets=result, newly_decoded_bytes=0, game_process_accessed=False,
        keys_sent=0, native_calls=0, memory_written=False, peak_committed_bytes=check_memory_budget(),
        producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitations=["Exact selected target byte scan, not whole-file disassembly.",
            "Candidates inside decoded ranges are independently instruction-boundary validated; others remain candidates."])
    path = ROOT/"work/reports/console-shortcut-static-20261015-r2/caller-xrefs.json"
    raw = (json.dumps(report, indent=2)+"\n").encode("ascii")
    with path.open("xb") as stream:
        stream.write(raw)
    print(raw.decode("ascii"))


if __name__ == "__main__":
    main()
