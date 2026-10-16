"""One exact held-process, two-pass RPM sample; no game calls or writes.

The output is exclusive. Failure is retained, never automatically retried.
Only the six selected TAGs are authorized ordinary handles; passive selectors
1..7 are checked and retained according to the existing R2 resolver profile.
"""
from __future__ import annotations

import argparse
import ctypes as C
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.tag_command_backend import GAME_SHA, WindowsRuntime
from work.discover_diplomacy import check_memory_budget
from work.probe_pair_effects_1375 import diplomat_snapshot, index_snapshot, pointer
from work.probe_diplomacy_relations_1375 import dependency_name

PID = 61988
CREATION = "01dd5acc83b0078c"
TAGS = ("FRA", "SCO", "ORL", "AUV", "POR", "BRI")
PAIRS = (("trade_favors_for_trust", "FRA", "SCO"),
         ("designate_march", "FRA", "ORL"),
         ("release_soyurghal", "FRA", "AUV"),
         ("dissolve_protectorate", "POR", "BRI"))
OUTPUT = ROOT / "work/runtime/tag31-corrective-prerequisites-61988.json"
COUNTRY_VT = 0x1C574A0
DEPENDENCY_VT = 0x1C81758
MAX_CALLS, MAX_BYTES, MAX_READ = 8192, 1024 * 1024, 65536


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


class Reader:
    def __init__(self, held):
        self.held, self.calls, self.bytes_read, self.largest_read = held, 0, 0, 0

    def read(self, address, size):
        require(type(address) is int and type(size) is int
                and 0x10000 <= address < address + size <= 2**47
                and 0 < size <= MAX_READ, "RPM range/read bound")
        require(self.calls < MAX_CALLS and self.bytes_read + size <= MAX_BYTES,
                "Shared RPM budget exhausted")
        self.calls += 1
        self.bytes_read += size
        self.largest_read = max(self.largest_read, size)
        buffer, got = C.create_string_buffer(size), C.c_size_t()
        require(self.held.kernel.ReadProcessMemory(
            self.held.handle, C.c_void_p(address), buffer, size, C.byref(got))
            and got.value == size, f"Unavailable exact RPM at {address:#x} ({size} bytes)")
        if self.calls % 256 == 0:
            check_memory_budget()
        return buffer.raw

    def qword(self, address):
        return struct.unpack("<Q", self.read(address, 8))[0]

    def integer(self, address):
        return struct.unpack("<i", self.read(address, 4))[0]

    def byte(self, address):
        return self.read(address, 1)[0]


def roots(reader, base):
    db = pointer(reader.qword(base + 0x233D8D0))
    game = pointer(reader.qword(base + 0x233FE78))
    array = pointer(reader.qword(db + 0x118))
    capacity, count = struct.unpack("<ii", reader.read(db + 0x120, 8))
    require(count == 1380 and count <= capacity <= 4096, "Unexpected 1380-slot table bounds")
    date = reader.integer(game + 0x1DD0)
    current, alternate = struct.unpack("<QQ", reader.read(game + 0x1E60, 16))
    require(date > 0 and ((current >> 48) & 255) == 0, "Current ordinary player/date")
    server = pointer(reader.qword(game + 0x1E00))
    pause = pointer(reader.qword(server + 0x418))
    value = dict(database=hex(db), game=hex(game), array=hex(array),
                 capacity=capacity, count=count, date=date, current_player=hex(current),
                 current_selector=(current >> 48) & 255,
                 alternate=hex(alternate), alternate_selector=(alternate >> 56) & 255,
                 reset=reader.byte(game + 0x7485), load_source=reader.qword(game + 0x74C8),
                 ironman=reader.byte(game + 0x24D0),
                 ordinary_cooldown_months=reader.integer(base + 0x233E064),
                 cooldown_exemption_gate_raw=reader.byte(game + 0x23A9),
                 server=hex(server), pause_manager=hex(pause),
                 manual_pause=reader.byte(pause + 0x48),
                 pause_backlink=hex(reader.qword(pause + 0x50)))
    require(value["reset"] == value["load_source"] == value["ironman"] == 0,
            "Reset/load/ironman exclusion")
    require(value["manual_pause"] == 1 and int(value["pause_backlink"], 16) == server,
            "Explicit manual pause/backlink")
    require(value["ordinary_cooldown_months"] == -1, "Expected current Mod cooldown -1")
    return value


def table(reader, base, root):
    array, count = int(root["array"], 16), root["count"]
    data = reader.read(array, count * 8)
    rows, selected, seen_addresses, seen_handles, seen_tags = [], {}, set(), set(), set()
    for slot, (address,) in enumerate(struct.iter_unpack("<Q", data)):
        if address == 0:
            rows.append(dict(slot=slot, address="0x0"))
            continue
        pointer(address)
        require(address not in seen_addresses, "Country pointer alias")
        seen_addresses.add(address)
        header = reader.read(address, 0x28)
        vt, marker = struct.unpack_from("<QI", header)
        require(vt == base + COUNTRY_VT and marker == 357,
                f"Country vtable/marker mismatch at slot {slot}")
        handle = struct.unpack_from("<Q", header, 0x20)[0]
        require(handle not in seen_handles, "Duplicate complete country handle")
        seen_handles.add(handle)
        row = dict(slot=slot, address=hex(address), vtable_rva=hex(vt - base),
                   marker=marker, handle=hex(handle))
        if slot == 0 and handle == 0x2D2D2D:
            row["sentinel"] = True
        else:
            selector = (handle >> 48) & 255
            tag = (handle & 0xFFFFFF).to_bytes(3, "little").decode("ascii")
            require(slot != 0 and (handle >> 32) & 65535 == slot
                    and handle >> 56 != 0 and (handle >> 24) & 255 == 0
                    and 0 <= selector <= 7 and re.fullmatch(r"[A-Z0-9]{3}", tag),
                    f"Country complete-handle profile at slot {slot}")
            require(tag not in seen_tags, "Duplicate country TAG")
            seen_tags.add(tag)
            row.update(tag=tag, selector=selector, identity_valid=True)
            if tag in TAGS:
                require(selector == 0, "Selected country is not ordinary selector0")
                selected[tag] = row
        rows.append(row)
    require(set(selected) == set(TAGS), "Selected TAG missing; no gameplay absence inferred")
    require(selected["FRA"]["handle"] == root["current_player"], "Player is not complete FRA handle")
    require(reader.read(array, count * 8) == data, "Within-pass pointer table changed")
    return rows, selected


def pair_record(reader, country, other):
    records = pointer(reader.qword(int(country["address"], 16) + 0x1510))
    record = records + other["slot"] * 0x48
    data = reader.read(record, 0x48)
    owner, counterpart = struct.unpack_from("<QQ", data, 8)
    require(owner == int(country["handle"], 16)
            and counterpart == int(other["handle"], 16), "Relation-record complete owner/counterpart")
    return dict(address=hex(record), records=hex(records), root=hex(pointer(struct.unpack_from("<Q", data)[0])),
                owner_handle=hex(owner), counterpart_handle=hex(counterpart),
                deadline_raw=struct.unpack_from("<i", data, 0x30)[0],
                trust_raw_byte= data[0x1E], favors_raw_milli=struct.unpack_from("<i", data, 0x20)[0])


def dependency(reader, base, actor, target):
    left = index_snapshot(reader, actor, target, 0x128, 0x134)
    right = index_snapshot(reader, target, actor, 0x128, 0x134)
    l = [v["object"] for v in left["entries"] if v["slot"] == target["slot"]]
    r = [v["object"] for v in right["entries"] if v["slot"] == actor["slot"]]
    require(len(l) <= 1 and len(r) <= 1 and l == r, "Dependency indexes disagree/duplicate")
    relation = None
    if l:
        obj = pointer(int(l[0], 16))
        data = reader.read(obj, 0x90)
        vt = struct.unpack_from("<Q", data)[0]
        first, second = struct.unpack_from("<QQ", data, 0x10)
        require(vt == base + DEPENDENCY_VT and data[0x28] == 0,
                "Dependency vtable or active marker mismatch")
        require({first, second} == {int(actor["handle"], 16), int(target["handle"], 16)},
                "Dependency full-handle pair mismatch")
        definition = pointer(struct.unpack_from("<Q", data, 0x40)[0])
        relation = dict(address=hex(obj), vtable_rva=hex(vt - base),
                        actor_handle=hex(first), target_handle=hex(second),
                        actor_to_target=first == int(actor["handle"], 16),
                        active_raw_28=data[0x28], start_date_raw=struct.unpack_from("<i", data, 0x20)[0],
                        type_definition=hex(definition), type_name=dependency_name(reader, definition))
    return dict(left=left, right=right, object=relation,
                actor_overlord_handle=hex(reader.qword(int(actor["address"], 16) + 0x18F0)),
                target_overlord_handle=hex(reader.qword(int(target["address"], 16) + 0x18F0)),
                observation_kind="bounded mutually indexed dependency; absence is not complete legality")


def cached_opinion(reader, country, other):
    # Pinned offline PE-derived trust leaf: 4fe001/4fe01c/4fe026/4fe029.
    begin, end = struct.unpack("<QQ", reader.read(int(country["address"], 16) + 0x2380, 16))
    pointer(begin)
    pointer(end)
    require(0 <= end - begin <= 32768 and (end - begin) % 2 == 0,
            "Cached opinion signed16 vector bounds")
    offset = other["slot"] * 2
    require(offset + 2 <= end - begin, "Actor slot outside target opinion vector")
    return dict(begin=hex(begin), end=hex(end), actor_slot=other["slot"],
                signed16=struct.unpack("<h", reader.read(begin + offset, 2))[0],
                evidence="tag31-native-rejection-leaf: trust local80 4fe001/4fe01c/4fe026/4fe029")


def sample(reader, base):
    before = roots(reader, base)
    rows, countries = table(reader, base, before)
    pairs = []
    for action, a, b in PAIRS:
        actor, target = countries[a], countries[b]
        outgoing, incoming = pair_record(reader, actor, target), pair_record(reader, target, actor)
        gate = before["cooldown_exemption_gate_raw"]
        pairs.append(dict(action=action, actor_tag=a, target_tag=b,
                          actor_to_target=outgoing, target_to_actor=incoming,
                          now_strictly_greater_than_deadline=before["date"] > outgoing["deadline_raw"],
                          cooldown_blocked_by_35a7f0=before["date"] <= outgoing["deadline_raw"] and gate == 0,
                          cooldown_only_allows=before["date"] > outgoing["deadline_raw"] or gate != 0,
                          cooldown_gate_is_not_complete_legality=True,
                          target_cached_opinion_of_actor=cached_opinion(reader, target, actor),
                          dependency=dependency(reader, base, actor, target)))
    diplomats = {}
    for tag in ("FRA", "POR"):
        snapshot = diplomat_snapshot(reader, countries[tag], base)
        snapshot["state_zero_count"] = sum(v["state"] == 0 for v in snapshot["entries"])
        snapshot["null_mission_count"] = sum(v["mission_pointer"] == "0x0" for v in snapshot["entries"])
        snapshot["state_zero_null_mission_candidate_count"] = sum(
            v["state"] == 0 and v["mission_pointer"] == "0x0" for v in snapshot["entries"])
        snapshot["availability_proven"] = False
        diplomats[tag] = snapshot
    globals_raw = {hex(rva):reader.integer(base + rva) for rva in (0x233F3D0, 0x233DB7C, 0x233DB80)}
    require(roots(reader, base) == before, "Within-pass roots/date/guards changed")
    for country in countries.values():
        header = reader.read(int(country["address"], 16), 0x28)
        require(struct.unpack_from("<Q", header)[0] == base + COUNTRY_VT
                and struct.unpack_from("<I", header, 8)[0] == 357
                and hex(struct.unpack_from("<Q", header, 0x20)[0]) == country["handle"],
                "Selected country identity changed within pass")
    return dict(roots=before, typed_country_rows=rows, countries=countries,
                pairs=pairs, diplomats=diplomats, trust_globals_raw=globals_raw,
                trust_975110_context_gate_evaluated=False,
                factory_actual_cost_not_observed=True, complete_legality_proven=False)


def serialized_evidence():
    result, pins = {}, {}
    paths = ("work/runtime/tag31-effects-reload-20261013-group1-scoped.json",
             "work/runtime/tag31-effects-reload-20261013-group2-scoped.json")
    for name in paths:
        path = ROOT / name
        require(path.stat().st_size <= 4 * 1024 * 1024, "Serialized source bound")
        data = path.read_bytes()
        doc = json.loads(data)
        require(doc["parsed_complete"] is True and doc["read_only"] is True,
                "Serialized source provenance")
        pins[name] = dict(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), source_save=doc["source"])
        for tag in TAGS:
            if tag in doc["countries"]:
                values = [v for v in doc["countries"][tag]["fields"] if v["key"] == "is_at_war"]
                result[tag] = dict(is_at_war_serialized_fields=values,
                                   missing_field_is_not_proven_false=True,
                                   observed_live=False, source=name)
    return result, pins


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument("creation")
    args = parser.parse_args()
    require((args.pid, args.creation) == (PID, CREATION), "Only this exact authorized process")
    require(not OUTPUT.exists(), "Exclusive report already exists; do not repeat sampling")
    report = dict(schema="EU4TAG31-CORRECTIVE-PREREQUISITES/1", pid=PID, creation=CREATION,
                  captured_at_utc=datetime.now(timezone.utc).isoformat(), game_sha256=GAME_SHA,
                  native_calls=0, memory_written=False, requests_published=0,
                  engine_predicates_called=False, status="incomplete", automatic_retry=False,
                  complete_legality_proven=False, two_pass_equal=False, passes=[])
    held = reader = None
    try:
        report["serialized_war_evidence"], report["serialized_source_pins"] = serialized_evidence()
        proof = ROOT / "work/runtime/tag31-native-rejection-leaf-20261013.json"
        proof_raw = proof.read_bytes()
        proof_data = json.loads(proof_raw)
        require(proof_data["file_only"] is True and proof_data["game_sha256"] == GAME_SHA,
                "Native field evidence provenance")
        report["native_field_proof"] = dict(path=str(proof.relative_to(ROOT)),
                                           sha256=hashlib.sha256(proof_raw).hexdigest())
        runtime = WindowsRuntime()
        identity = dict(pid=PID, creation=CREATION, session="1" * 32,
                        dll_sha256="f" * 64, manifest_sha256="e" * 64)
        held = runtime.readonly.Held(identity)
        held.identity_check()
        modules = held.modules()
        canonical = held.injector._canonical
        matches = [b for b, p in modules if canonical(p) == canonical(held.injector.GAME)]
        require(len(matches) == 1, "Exact main module unavailable")
        research = [str(p) for _, p in modules if Path(p).name.lower().startswith(
            ("eu4_bridge_", "eu4_pair_", "eu4_spy_", "eu4_tag_command_", "tag_diplomacy"))]
        require(not research, "Research DLL already loaded during prerequisites sample")
        base = pointer(matches[0])
        report["module_base"], report["research_modules"] = hex(base), research
        disk_pe = runtime.readonly.disk_identity(held.injector.GAME)
        reader = Reader(held)
        require(runtime.readonly.pe_header(reader.read(base, 8192)) == disk_pe,
                "Loaded main PE differs from hash-verified file")
        report["loaded_main_pe"] = disk_pe
        report["passes"].append(sample(reader, base))
        held.identity_check()
        report["passes"].append(sample(reader, base))
        held.identity_check()
        require(report["passes"][0] == report["passes"][1],
                "Two complete passes differ; no automatic resample")
        report["two_pass_equal"], report["status"] = True, "sampled_equal"
    except Exception as exc:
        report["status"] = "failed_no_retry"
        report["failure"] = dict(type=type(exc).__name__, message=str(exc))
    finally:
        if reader:
            report["rpm_budget"] = dict(calls=reader.calls, bytes=reader.bytes_read,
                                         largest_read=reader.largest_read,
                                         max_calls=MAX_CALLS, max_bytes=MAX_BYTES, max_single_read=MAX_READ)
        if held:
            held.close()
    report["peak_committed_bytes"] = check_memory_budget()
    report["limitations"] = [
        "Two equal RPM passes are not an atomic game-thread snapshot or a proof against ABA reuse.",
        "Cooldown allowed is just the signed comparison/gate at 35a7f0; not full88 or action-specific legality.",
        "No native function, predicate, factory, request, loader, UI action or memory write was executed.",
        "Null mission/state-zero are envoy candidates only; target assignment and full native availability are unproven.",
        "Trust global/TLS context gate 975110 and actual factory cost remain unevaluated.",
        "War fields are pinned serialized reload evidence, not current live predicates; absence is not false.",
        "Subject type observations are exact indexed current objects; normal lifecycle or later mutations remain possible.",
        "Identity or two-pass failure is retained and stops work without retrying the sample.",
    ]
    with OUTPUT.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    summary = dict(path=str(OUTPUT), status=report["status"], two_pass_equal=report["two_pass_equal"],
                   rpm_budget=report.get("rpm_budget"), peak_committed_bytes=report["peak_committed_bytes"],
                   failure=report.get("failure"))
    if report["two_pass_equal"]:
        value = report["passes"][0]
        summary.update(date=value["roots"]["date"],
                       pairs=[dict(action=p["action"], actor=p["actor_tag"], target=p["target_tag"],
                                   deadline=p["actor_to_target"]["deadline_raw"],
                                   cooldown_only_allows=p["cooldown_only_allows"],
                                   target_trust=p["target_to_actor"]["trust_raw_byte"],
                                   target_favors_milli=p["target_to_actor"]["favors_raw_milli"],
                                   target_opinion=p["target_cached_opinion_of_actor"]["signed16"],
                                   dependency_type=(p["dependency"]["object"]["type_name"]["name"]
                                                    if p["dependency"]["object"] else None)) for p in value["pairs"]],
                       diplomats={tag:dict(count=s["count"], state_zero_null_mission_candidates=s[
                           "state_zero_null_mission_candidate_count"]) for tag, s in value["diplomats"].items()})
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if report["two_pass_equal"] else 2


if __name__ == "__main__":
    sys.exit(main())
