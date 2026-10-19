"""Current typed noCB/application registry snapshot, strictly held QUERY/VM_READ."""
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy_effect_observer import RuntimeCapture, BudgetReader, HeldRPMPort, roots, ptr, pins
from bridge.tag_command_backend import TagCommandBackend, digest, require

OUT = ROOT / "work/reports/war-peace-api-20261015-r8-stack-scope/war/live-80340-registry-current.json"
SOURCES = ("work/reports/war-peace-api-20261015-r6-owner-boundary/war/manifest.json",
           "work/reports/war-peace-api-20261015-r6-registry-lifetime/war/manifest.json",
           "work/reports/war-peace-api-20261015-r9-registry-insert/war/manifest.json",
           "work/reports/war-peace-api-20261015-r8-stack-scope/war/manifest.json",
           "work/capture_nocb_registry_live_20261015.py")


def sources():
    result = {}
    for name in SOURCES:
        raw = (ROOT / name).read_bytes()
        result[name] = {"bytes": len(raw), "sha256": digest(raw)}
    return result


def sample(reader, base):
    before = roots(reader, base)
    require(before["manual_pause"] == 1, "Paused checkpoint required")
    app = ptr(reader.q(base + 0x242bf50))
    registry = ptr(reader.q(base + 0x242bed0))
    goal = ptr(reader.q(base + 0x2340030))
    definition = ptr(reader.q(base + 0x2340038))
    require(app != int(before["database"], 16), "Application aliases country database")
    app_raw = reader.read(app, 0x18)
    require(struct.unpack_from("<Q", app_raw, 0)[0] == base + 0x1c48bf8
            and struct.unpack_from("<Q", app_raw, 0x10)[0] == base + 0x1c48c80,
            "Application primary/secondary type mismatch")
    reg_raw = reader.read(registry, 0x28)
    hash_count, bucket_count, bucket_storage, begin, end, capacity = struct.unpack("<IIQQQQ", reg_raw)
    require(1 <= bucket_count <= 4096 and 0 <= hash_count <= 256, "Registry hash bound")
    ptr(bucket_storage)
    if begin == end == capacity == 0:
        array = b""
        values = []
    else:
        for value in (begin, end, capacity):
            ptr(value)
        require(begin <= end <= capacity and (end-begin) % 8 == 0 and (capacity-begin) % 8 == 0
                and (end-begin)//8 <= 256 and (capacity-begin)//8 <= 512, "Registry vector bound")
        array = reader.read(begin, end-begin) if end != begin else b""
        values = [v for v, in struct.iter_unpack("<Q", array)]
        for v in values:
            ptr(v)
    goal_raw = reader.read(goal, 0x18)
    def_raw = reader.read(definition, 0x40)
    require(struct.unpack_from("<Q", goal_raw, 0)[0] == base + 0x1d207f8,
            "Current sentinel type mismatch")
    require(struct.unpack_from("<Q", goal_raw, 0x10)[0] == definition,
            "Current sentinel definition differs from current global slot")
    require(struct.unpack_from("<Q", def_raw, 0)[0] == base + 0x1d20ae0
            and struct.unpack_from("<i", def_raw, 0x38)[0] == 12, "Current nowargoal definition type/enum mismatch")
    after_slots = [reader.q(base+x) for x in (0x242bf50, 0x242bed0, 0x2340030, 0x2340038)]
    require(after_slots == [app, registry, goal, definition], "Current registry roots changed")
    require(roots(reader, base) == before, "Game roots changed during current snapshot")
    return {"roots": before, "application": {"address": hex(app), "raw_hex": app_raw.hex(),
                                             "primary_vtable_rva": "0x1c48bf8", "secondary_vtable_rva": "0x1c48c80"},
            "registry": {"address": hex(registry), "raw_hex": reg_raw.hex(), "hash_count": hash_count,
                         "bucket_count": bucket_count, "bucket_storage": hex(bucket_storage),
                         "vector_begin": hex(begin), "vector_end": hex(end), "vector_capacity": hex(capacity),
                         "vector_count": len(values), "vector_raw_hex": array.hex(),
                         "current_definition_occurrences": values.count(definition)},
            "sentinel": {"address": hex(goal), "raw_hex": goal_raw.hex(), "definition": hex(definition)},
            "definition": {"address": hex(definition), "raw_hex": def_raw.hex(), "enum": 12},
            "current_definition_in_registry_vector": values.count(definition) == 1,
            "current_slot_and_sentinel_definition_match": True}


def main():
    require(not OUT.exists(), "Exclusive live output required")
    original_sources = sources()
    backend = TagCommandBackend()
    identity = {"pid": 80340, "creation": "01dd5c075fcf8c26", "session": secrets.token_hex(16),
                "dll_sha256": backend.manifest["dll"]["sha256"], "manifest_sha256": backend.manifest_sha}
    started = time.perf_counter()
    with RuntimeCapture(identity, backend) as cap:
        require(not any(Path(p).name.lower().startswith(("eu4_bridge_", "eu4_pair_", "eu4_spy_",
                    "eu4_tag_command_", "tag_diplomacy")) for _, p in cap.modules), "Unexpected research module")
        reader = BudgetReader(HeldRPMPort(cap.held))
        first, second = sample(reader, cap.base), sample(reader, cap.base)
        require(first == second, "Two complete current snapshots differ")
        cap.held.identity_check()
        require(cap.held.modules() == cap.modules and pins() == cap.initial_pins,
                "Modules or frozen observer sources changed")
        require(sources() == original_sources, "Research sources changed")
        base = cap.base
    data = {"schema": "EU4-NOCB-REGISTRY-CURRENT-READONLY/1", "captured_utc": datetime.now(timezone.utc).isoformat(),
            "identity": identity, "identity_purpose": "Read-only nonce, not a TAG installation or native request",
            "base": hex(base), "source_pins": original_sources, "observer_source_pins": cap.initial_pins,
            "samples": [first, second], "two_pass_equal": True,
            "duration_ms_including_host_and_source_checks": round((time.perf_counter()-started)*1000,3),
            "rpm_budget": {"calls": reader.calls, "bytes": reader.bytes, "largest_read": reader.largest},
            "current_membership_only": True, "atomic_world_snapshot": False, "native_lifetime_authority": False,
            "native_ready": False, "native_calls": 0, "memory_written": False, "requests_published": 0,
            "saves_written": 0, "reloads": 0, "new_API_effect_tested": False}
    with OUT.open("x",encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)
        f.write("\n")
    print(json.dumps({"output": str(OUT), "sha256":digest(OUT.read_bytes()), "two_pass_equal":True,
                      "current_definition_in_registry_vector":first["current_definition_in_registry_vector"],
                      "vector_count":first["registry"]["vector_count"],"rpm_budget":data["rpm_budget"],
                      "duration_ms":data["duration_ms_including_host_and_source_checks"],"native_ready":False}))


if __name__ == "__main__":
    main()
