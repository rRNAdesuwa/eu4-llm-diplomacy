"""Exact .rdata console seeds and byte-pattern xrefs; no disassembly scan."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"work"))
from discover_diplomacy import PE, rip_references, check_memory_budget


def main():
    pe = PE(ROOT.parent/"eu4.exe")
    sha = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
    assert hashlib.sha256(pe.data).hexdigest() == sha
    section = next(s for s in pe.sections if s["name"] == ".rdata")
    start, end = section["raw"], section["raw"]+section["size"]
    seeds = {}
    for seed in ("console_wnd", "console_edit", "toggle_console", "console", "console_list"):
        offsets, at = [], start
        pattern = seed.encode("ascii")+b"\0"
        while True:
            at = pe.data.find(pattern, at, end)
            if at < 0:
                break
            if at == start or pe.data[at-1] == 0:
                offsets.append(pe.to_rva(at))
                assert len(offsets) <= 32
            at += 1
        seeds[seed] = offsets
    targets = {x for group in seeds.values() for x in group}
    refs = rip_references(pe, targets)
    assert sum(len(x) for x in refs.values()) <= 128
    for seed, targets in seeds.items():
        seeds[seed] = [dict(rva=hex(target), byte_pattern_references=refs.get(target, [])) for target in targets]
    interval = pe.function(0x1721320)
    directory = ROOT/"work/reports/console-shortcut-static-20261015-r2"
    directory.mkdir(parents=True, exist_ok=True)
    report = dict(schema="EU4-CONSOLE-EXACT-SEED-XREFS/1", game_sha256=sha,
        seeds=seeds, searched_section={k: section[k] for k in ("name", "rva", "size")},
        dispatcher_pdata=[hex(x) for x in interval], dispatcher_pdata_bytes=interval[1]-interval[0],
        newly_decoded_bytes=0, game_process_accessed=False, native_calls=0, keys_sent=0,
        memory_written=False, peak_committed_bytes=check_memory_budget(),
        producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitations=["Xrefs are exact-seed byte-pattern candidates until instruction boundaries are independently decoded.",
            "Only .rdata exact NUL-terminated seed matches and executable RIP-pattern references; no whole-file disassembly."])
    path = directory/"seed-xrefs.json"
    raw = (json.dumps(report, indent=2)+"\n").encode("ascii")
    with path.open("xb") as stream:
        stream.write(raw)
    print(raw.decode("ascii"))


if __name__ == "__main__":
    main()
