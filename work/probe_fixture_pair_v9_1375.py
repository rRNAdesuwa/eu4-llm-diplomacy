"""Fixed FRA/NAV read-only fixture diagnostics, before or after v9 injection.

The two passes are bounded consistent reads, not an atomic or causal proof.
No function calls into the game, process writes, UI inputs or request publication.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work.native import lab_protocol_v9_1375 as lab
from work.probe_diplomacy_current import pointer

HANDLES = {"FRA": 0x0100007A00415246, "NAV": 0x010000BC0056414E}
EVIDENCE = ROOT / "work/candidates/v9-build-review/baseline-guard-evidence.json"
EVIDENCE_SHA = "e86fc8c7225d89c441d0cafb4657a129f4a752d7ab23556c1502e62341812643"


def sample(process):
    reader = process.reader
    snapshot = process.snapshot()
    database = pointer(reader.qword(reader.base + 0x233D8D0))
    array = pointer(reader.qword(database + 0x118))
    countries = {}
    for tag, handle in HANDLES.items():
        address = pointer(reader.qword(array + ((handle >> 32) & 0xFFFF) * 8))
        lab.require(reader.qword(address + 0x20) == handle, "Fixed country handle differs")
        countries[tag] = {"address": hex(address), "handle": hex(handle),
                          "overlord": hex(reader.qword(address + 0x18F0))}
    relations = {}
    for actor, target in (("FRA", "NAV"), ("NAV", "FRA")):
        owner = int(countries[actor]["address"], 16)
        target_handle = HANDLES[target]
        slot = (target_handle >> 32) & 0xFFFF
        records = pointer(reader.qword(owner + 0x1510))
        record = records + slot * 0x48
        lab.require(reader.qword(record + 0x10) == target_handle, "Relation handle differs")
        root = pointer(reader.qword(record))
        index = reader.qword(root + 0x80)
        count = reader.integer(root + 0x8C)
        lab.require(0 <= count <= 4096, "Unbounded alliance index")
        if index:
            pointer(index)
        lab.require(not count or index, "Missing alliance index")
        entries = []
        for offset in range(count):
            item = index + offset * 16
            indexed_slot = reader.integer(item)
            obj = pointer(reader.qword(item + 8))
            lab.require(0 <= indexed_slot < 4096, "Invalid indexed country slot")
            entries.append({"slot": indexed_slot, "object": hex(obj)})
        flags = reader.read(record + 0x45, 1)[0]
        relations[f"{actor}->{target}"] = {
            "records": hex(records), "record": hex(record), "root": hex(root),
            "truce_flags": flags, "active_truce_bit0": bool(flags & 1),
            "alliance_index": hex(index), "alliance_count": count,
            "entries": entries, "matching_alliance": any(e["slot"] == slot for e in entries),
        }
    lab.require(process.snapshot() == snapshot, "World changed during bounded read")
    return {"live": snapshot, "database": hex(database), "country_array": hex(array),
            "countries": countries, "relations": relations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--creation", required=True)
    parser.add_argument("--before-injection", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    lab.require(hashlib.sha256(EVIDENCE.read_bytes()).hexdigest() == EVIDENCE_SHA,
                "Static layout evidence changed")
    lab.verify_build()
    with lab.LiveLabProcess(args.pid, expected_creation=args.creation,
                            require_loaded=not args.before_injection) as process:
        passes = [sample(process), sample(process)]
        lab.require(passes[0] == passes[1], "Pair changed between read passes")
        nav = passes[0]["countries"]["NAV"]
        relations = passes[0]["relations"]
        result = {"schema": "fixed_fixture_pair_v9_1375_observation_v1", "read_only": True,
                  "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                  "layout_evidence_sha256": EVIDENCE_SHA, "passes": passes,
                  "consistent": True, "nav_independent": int(nav["overlord"], 16) >> 56 == 0,
                  "bilateral_no_alliance": all(not v["matching_alliance"] for v in relations.values()),
                  "bilateral_no_truce": all(not v["active_truce_bit0"] for v in relations.values()),
                  "bytes_read": process.reader.bytes_read, "atomic_snapshot": False,
                  "loaded_save_identity_verified": False, "request_causality_verified": False,
                  "production_execution_verified": False}
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(result, file, indent=2)
        file.write("\n")
    print(json.dumps({k: result[k] for k in ("consistent", "nav_independent", "bilateral_no_alliance",
                                           "bilateral_no_truce", "bytes_read")}))


if __name__ == "__main__":
    main()
