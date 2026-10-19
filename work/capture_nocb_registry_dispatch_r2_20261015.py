"""Fresh current registry/hash and SDL dispatch reads; no hooks, injection or calls."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import secrets
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OLD_RECEIPT = ROOT / "work/reports/war-peace-api-20261015-r8-stack-scope/war/live-80340-registry-current.json"
OLD_PRODUCER = ROOT / "work/capture_nocb_registry_live_20261015.py"
OUT = ROOT / "work/reports/war-peace-api-20261015-r8-stack-scope/war/live-80340-registry-and-dispatch-r2.json"

# Validate the reused producer before loading it. This receipt's literal digest
# binds the old code; the nonce in that receipt is not reused as a session.
old_raw = OLD_RECEIPT.read_bytes()
assert hashlib.sha256(old_raw).hexdigest() == "b9608f0c6343834e6ffa3fec8a7a355f51a91b45080e8d8e04add31c0490e9a5"
expected = json.loads(old_raw)["source_pins"][OLD_PRODUCER.relative_to(ROOT).as_posix()]
producer_raw = OLD_PRODUCER.read_bytes()
assert {"bytes": len(producer_raw), "sha256": hashlib.sha256(producer_raw).hexdigest()} == expected
spec = importlib.util.spec_from_file_location("fixed_nocb_current_reader", OLD_PRODUCER)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)

SOURCES = (OLD_RECEIPT, OLD_PRODUCER,
           ROOT / "work/reports/war-peace-api-20261015-r6-main-holder/war/manifest.json",
           ROOT / "work/reports/war-peace-api-20261015-r9-registry-insert/war/manifest.json",
           Path(__file__).resolve())
CELLS = (("creator", 0x1fb0058, 0x1738d30), ("wait", 0x1fb0db8, 0x1739460),
         ("guard_dispatch", 0x1b67860, 0x1a79a30))


def sources():
    result = {}
    for p in SOURCES:
        raw = p.read_bytes()
        result[p.relative_to(ROOT).as_posix()] = {"bytes": len(raw), "sha256": old.digest(raw)}
    return result


def sample(reader, base):
    value = old.sample(reader, base)  # Resolves all roots afresh; no old pointers.
    raw = bytes.fromhex(value["definition"]["raw_hex"])
    length, capacity = struct.unpack_from("<QQ", raw, 0x28)
    old.require(length == 9 and capacity == 15 and raw[0x18:0x18+length] == b"nowargoal",
                "Selected definition name/SSO layout changed")
    hash_value = 0
    for char in raw[0x18:0x18+length]:
        signed = char if char < 128 else char - 256
        hash_value = ((hash_value + signed) * 61) & 0xffffffff
    reg = value["registry"]
    bucket = hash_value % reg["bucket_count"]
    head_address = int(reg["bucket_storage"],16) + bucket * 8
    head_raw = reader.read(head_address, 8)
    node = struct.unpack("<Q", head_raw)[0]
    seen, nodes = set(), []
    while node:
        old.ptr(node)
        old.require(node % 8 == 0 and node not in seen and len(nodes) < min(256, reg["hash_count"]+1),
                    "Selected hash chain bound/cycle/alignment")
        seen.add(node)
        node_raw = reader.read(node, 0x10)
        definition, next_node = struct.unpack("<QQ", node_raw)
        old.ptr(definition)
        nodes.append({"address":hex(node),"raw_hex":node_raw.hex(),"definition":hex(definition),
                      "next":hex(next_node)})
        node = next_node
    selected = int(value["definition"]["address"],16)
    value["selected_hash"] = {"name":"nowargoal","hash_u32":hash_value,"bucket_index":bucket,
                              "head_address":hex(head_address),"head_raw_hex":head_raw.hex(),"nodes":nodes,
                              "current_definition_occurrences":sum(int(n["definition"],16)==selected for n in nodes)}
    dispatch = []
    for name, slot, target in CELLS:
        cell_raw = reader.read(base+slot,8)
        address = struct.unpack("<Q",cell_raw)[0]
        dispatch.append({"name":name,"slot_rva":hex(slot),"raw_hex":cell_raw.hex(),"address":hex(address),
                         "expected_target_rva":hex(target),"current_expected_binding":address==base+target})
    value["dispatch_bindings"] = dispatch
    old.require(reader.read(int(value["definition"]["address"],16),0x40).hex()==value["definition"]["raw_hex"],
                "Selected definition changed during hash snapshot")
    old.require([reader.q(base+x) for x in (0x242bf50,0x242bed0,0x2340030,0x2340038)] ==
                [int(value[k]["address"],16) for k in ("application","registry","sentinel","definition")],
                "Selected current roots changed during hash/dispatch read")
    old.require(old.roots(reader,base)==value["roots"], "Game roots changed during extended snapshot")
    return value


def main():
    old.require(not OUT.exists(), "Exclusive output required")
    initial = sources()
    backend = old.TagCommandBackend()
    identity = {"pid":80340,"creation":"01dd5c075fcf8c26","session":secrets.token_hex(16),
                "dll_sha256":backend.manifest["dll"]["sha256"],"manifest_sha256":backend.manifest_sha}
    started = time.perf_counter()
    with old.RuntimeCapture(identity,backend) as cap:
        old.require(not any(Path(p).name.lower().startswith(("eu4_bridge_","eu4_pair_","eu4_spy_",
                        "eu4_tag_command_","tag_diplomacy")) for _,p in cap.modules), "Unexpected research module")
        reader = old.BudgetReader(old.HeldRPMPort(cap.held))
        first,second = sample(reader,cap.base),sample(reader,cap.base)
        old.require(first==second, "Complete extended snapshots differ")
        cap.held.identity_check()
        old.require(cap.held.modules()==cap.modules and old.pins()==cap.initial_pins and sources()==initial,
                    "Modules or frozen sources changed")
        base=cap.base
    data={"schema":"EU4-NOCB-REGISTRY-AND-DISPATCH-READONLY/2","captured_utc":datetime.now(timezone.utc).isoformat(),
          "identity":identity,"identity_purpose":"Fresh read-only nonce, not a TAG installation or native request",
          "base":hex(base),"source_pins":initial,"observer_source_pins":cap.initial_pins,"samples":[first,second],
          "two_pass_equal":True,"duration_ms_including_host_and_source_checks":round((time.perf_counter()-started)*1000,3),
          "rpm_budget":{"calls":reader.calls,"bytes":reader.bytes,"largest_read":reader.largest},
          "current_hash_membership_only":True,"current_dispatch_binding_only":True,"atomic_world_snapshot":False,
          "native_lifetime_authority":False,"native_ready":False,"native_calls":0,"requests_published":0,
          "memory_written":False,"injection_performed":False,"hooks_installed":0,"saves_written":0,"reloads":0,
          "new_API_effect_tested":False}
    with OUT.open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({"output":str(OUT),"sha256":old.digest(OUT.read_bytes()),"two_pass_equal":True,
                      "hash_current_definition_occurrences":first["selected_hash"]["current_definition_occurrences"],
                      "dispatch_bindings":[{"name":x["name"],"current_expected_binding":x["current_expected_binding"]} for x in first["dispatch_bindings"]],
                      "rpm_budget":data["rpm_budget"],"duration_ms":data["duration_ms_including_host_and_source_checks"],
                      "native_ready":False}))


if __name__ == "__main__":
    main()
