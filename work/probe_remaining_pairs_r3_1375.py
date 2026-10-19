"""Two-pass bounded RPM of remaining pair prerequisites; no native calls/writes.

This separate reader adds ORL/MAL actor diplomats, complete coalition handles,
and the decoded pair-war index. It does not call a predicate, initialize TLS,
create an action, publish a request, or infer whole-action legality.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.tag_command_backend import GAME_SHA, TagCommandBackend, WindowsRuntime, read, digest
from work import inspect_tag31_corrective_pairs as prior
from work.probe_pair_effects_1375 import pointer, diplomat_snapshot
from work.probe_current_diplomacy_1375 import envoy_exclusion
from work.discover_diplomacy import check_memory_budget

TAGS = ("FRA", "SCO", "ORL", "AUV", "POR", "BRI", "SAV", "JOL", "MAL")
PAIRS = (("leave_coalition", "FRA", "SAV"),
         ("annex_vassal", "FRA", "ORL"),
         ("cancel_annexation", "FRA", "ORL"),
         ("ask_for_march", "ORL", "FRA"),
         ("knowledge_sharing", "FRA", "JOL"),
         ("ask_knowledge_sharing", "MAL", "FRA"))
ACTORS = tuple(dict.fromkeys(actor for _, actor, _ in PAIRS))
RESOURCE_FIELDS = {"treasury_milli": 0xbb0, "manpower_milli": 0xdb8, "sailors_milli": 0xdc0}
SOURCE_FILES = (
    "work/probe_remaining_pairs_r3_1375.py",
    "work/inspect_tag31_corrective_pairs.py", "work/probe_pair_effects_1375.py",
    "work/probe_diplomacy_relations_1375.py", "work/probe_current_diplomacy_1375.py",
    "work/probe_corrective_favors_r3_1375.py", "work/discover_diplomacy.py",
    "bridge/tag_command_backend.py",
    "work/reports/diplomacy-corrective-20261014-r3/coalition-false-static.json",
    "work/reports/diplomacy-corrective-20261014-r3/coalition-false-disassembly.txt",
    "work/reports/rea-diplomacy-20261013/envoy-reservation-readonly-spec.md",
    "work/reports/rea-api-discovery-20261013/conditions/findings.json",
    "work/reports/native-pair29-favor-effects-1375.json",
)


def source_pins():
    return {name: {"bytes": len(raw := read(ROOT/name, 8*1024*1024)), "sha256": digest(raw)}
            for name in SOURCE_FILES}


def complete_coalition_handle(reader, country, countries, rows):
    raw = reader.qword(int(country["address"], 16)+0x18f8)
    slot = (raw >> 32) & 0xffff
    result = {"handle": hex(raw), "slot_raw_unsigned16": slot,
              "slot_native_signed16": struct.unpack("<h", struct.pack("<H", slot))[0],
              "sentinel": raw == 0x2d2d2d, "complete_identity_validated": False}
    if raw not in (0, 0x2d2d2d):
        prior.require(slot < len(rows) and rows[slot].get("identity_valid") is True
                      and int(rows[slot]["handle"], 16) == raw,
                      "Coalition target does not match complete typed country identity")
        result.update(complete_identity_validated=True, tag=rows[slot]["tag"],
                      selector=rows[slot]["selector"])
    result["matches_selected_handles"] = {tag: raw == int(value["handle"], 16) for tag, value in countries.items()}
    return result


def pair_war_index(reader, outgoing, target, table_count):
    """Implement decoded a68a00 membership using RPM, never call a68a00."""
    record, root = int(outgoing["address"], 16), int(outgoing["root"], 16)
    array = reader.qword(root+0x50)
    count = reader.integer(root+0x5c)  # Native movsxd, not unsigned default.
    prior.require(0 <= count <= 4096, "Signed pair-war index count exceeds sampling bound")
    raw = reader.read(pointer(array), count*0x10) if count else b""
    entries = [struct.unpack_from("<i", raw, i*0x10)[0] for i in range(count)]
    prior.require(all(0 <= entry < table_count for entry in entries), "Pair-war index contains out-of-profile country slot")
    counterpart = reader.qword(record+0x10)
    prior.require(counterpart == int(target["handle"], 16) and reader.qword(record) == root
                  and reader.qword(root+0x50) == array and reader.integer(root+0x5c) == count,
                  "Pair-war relation/header changed within pass")
    signed_slot = struct.unpack("<h", struct.pack("<H", (counterpart >> 32) & 0xffff))[0]
    return {"record": hex(record), "root": hex(root), "array": hex(array), "count_signed": count,
        "entry_stride_bytes": 16, "ordered_country_indices": entries,
        "records_sha256": hashlib.sha256(raw).hexdigest(), "counterpart_complete_handle": hex(counterpart),
        "wanted_native_signed16_index": signed_slot, "matching_indices": [i for i, entry in enumerate(entries) if entry == signed_slot],
        "index_member_observed": signed_slot in entries, "engine_helper_called": False,
        "complete_action_legality_proven": False}


def actor_diplomats(reader, country, base):
    value = diplomat_snapshot(reader, country, base)
    actor = int(country["address"], 16)
    prior.require(reader.qword(actor+0x1480) == int(value["holder"], 16)
                  and reader.qword(int(value["holder"], 16)+0x18) == int(value["manager"], 16)
                  and reader.read(int(value["manager"], 16)+0x20, 16) ==
                  struct.pack("<QQ", int(value["begin"], 16), int(value["end"], 16)),
                  "Actor diplomat holder/vector changed within sample")
    prior.require(len({entry["address"] for entry in value["entries"]}) == value["count"],
                  "Actor diplomat vector contains aliased object pointers")
    value["state_zero_count"] = sum(entry["state"] == 0 for entry in value["entries"])
    value["native_id_exclusion"] = envoy_exclusion(reader, country, value)
    value["mission_null_is_not_availability"] = True
    value["full88_legality_proven"] = False
    return value


def sample(reader, base, size_of_image):
    root = prior.roots(reader, base)  # Includes pause/backlink, Mod -1 and reset/load/ironman guards.
    original_tags = prior.TAGS
    try:
        prior.TAGS = TAGS  # This interpreter only; the frozen helper is untouched.
        rows, countries = prior.table(reader, base, root)
    finally:
        prior.TAGS = original_tags
    coalition = {tag: complete_coalition_handle(reader, country, countries, rows)
                 for tag, country in countries.items()}
    pairs = []
    for action, a, b in PAIRS:
        actor, target = countries[a], countries[b]
        outgoing = prior.pair_record(reader, actor, target)
        incoming = prior.pair_record(reader, target, actor)
        gate = root["cooldown_exemption_gate_raw"]
        pairs.append({"action": action, "actor_tag": a, "target_tag": b,
            "actor_to_target": outgoing, "target_to_actor": incoming,
            "now_strictly_greater_than_deadline": root["date"] > outgoing["deadline_raw"],
            "cooldown_only_allows": root["date"] > outgoing["deadline_raw"] or gate != 0,
            "cooldown_gate_is_not_complete_legality": True,
            "target_cached_opinion_of_actor": prior.cached_opinion(reader, target, actor),
            "dependency": prior.dependency(reader, base, actor, target),
            "pair_war_index": pair_war_index(reader, outgoing, target, root["count"]),
            "coalition_actor_handle": coalition[a],
            "coalition_actor_matches_requested_target_complete_handle": coalition[a]["handle"] == target["handle"],
            "complete_legality_proven": False})
    diplomats = {tag: actor_diplomats(reader, countries[tag], base) for tag in ACTORS}
    resources = {}
    for tag in ("FRA", "ORL", "JOL", "MAL"):
        address = int(countries[tag]["address"], 16)
        resources[tag] = {name: reader.integer(address+offset) for name, offset in RESOURCE_FIELDS.items()}
    country_fields = {}
    for tag, country in countries.items():
        address = int(country["address"], 16)
        capital_raw = reader.qword(address+0x14b0)
        country_fields[tag] = {"war_raw_289b": reader.byte(address+0x289b),
            "existence_province_count_raw_1344": reader.integer(address+0x1344),
            "existence_flag_raw_26": reader.byte(address+0x26),
            "capital_path_pointer_raw_14b0": hex(capital_raw),
            "capital_identity_status": "raw native path pointer only; no guessed province ID/vtable layout",
            "annexation_index_status": "not_sampled_no_independently_pinned_layout",
            "complete_legality_proven": False}
    sharing_counts = {}
    for tag in ("FRA", "JOL", "MAL"):
        address = int(countries[tag]["address"], 16)
        sharing_counts[tag] = {"signed_count_17dc": reader.integer(address+0x17dc),
            "signed_count_17c4": reader.integer(address+0x17c4),
            "native_count_locations_from": "conditions/findings knowledge_sharing_eligibility",
            "institution_context_evaluated": False, "range_evaluated": False,
            "institution_difference_evaluated": False, "full88_legality_proven": False}
    # Revalidate complete selected country headers after all graphs are sampled.
    for country in countries.values():
        header = reader.read(int(country["address"], 16), 0x28)
        vt, marker = struct.unpack_from("<QI", header)
        handle = struct.unpack_from("<Q", header, 0x20)[0]
        prior.require(vt == base+prior.COUNTRY_VT and marker == 357
                      and handle == int(country["handle"], 16), "Selected complete country identity changed")
    prior.require(prior.roots(reader, base) == root, "Roots/date/pause changed after selected sampling")
    return {"roots": root, "typed_country_rows": rows, "countries": countries, "pairs": pairs,
        "diplomats": diplomats, "country_coalition_handles": coalition, "country_fields": country_fields,
        "selected_resources": resources, "knowledge_sharing_selected_counts": sharing_counts,
        "institution_context_evaluated": False, "native_full88_called": False,
        "complete_legality_proven": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--creation", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-tag-host", action="store_true")
    args = parser.parse_args()
    prior.require(not args.output.exists(), "Exclusive report exists; no automatic retry")
    initial_pins = source_pins()
    report = {"schema": "EU4TAG-REMAINING-PAIRS-R3-RPM/1", "game_sha256": GAME_SHA,
        "pid": args.pid, "creation": args.creation, "captured_utc": datetime.now(timezone.utc).isoformat(),
        "native_calls": 0, "memory_written": False, "requests_published": 0, "engine_predicates_called": False,
        "status": "incomplete", "two_pass_equal": False, "automatic_retry": False,
        "complete_legality_proven": False, "passes": [], "source_pins": initial_pins}
    held = reader = None
    try:
        backend = TagCommandBackend()  # File identity validation only; os_runtime is never used.
        runtime = WindowsRuntime()
        held = runtime.readonly.Held({"pid": args.pid, "creation": args.creation, "session": "1"*32,
            "manifest_sha256": backend.manifest_sha, "dll_sha256": backend.manifest["dll"]["sha256"]})
        held.identity_check()
        canonical = held.injector._canonical
        modules = held.modules()
        games = [(address, path) for address, path in modules if canonical(path) == canonical(held.injector.GAME)]
        prior.require(len(games) == 1, "Expected single exact game module")
        research = [(address, str(path)) for address, path in modules if Path(path).name.lower().startswith(
            ("eu4_bridge_", "eu4_pair_", "eu4_spy_", "eu4_tag_command_", "tag_diplomacy"))]
        expected = backend.build/backend.manifest["DLL"]
        prior.require(not research or (args.allow_tag_host and len(research) == 1
                      and canonical(research[0][1]) == canonical(expected)), "Unexpected research DLL")
        reader = prior.Reader(held)  # The same calls/bytes budget covers module headers and both passes.
        base = pointer(games[0][0])
        disk = runtime.readonly.disk_identity(held.injector.GAME)
        prior.require(runtime.readonly.pe_header(reader.read(base, 8192)) == disk, "Loaded main PE differs from fixed executable")
        if research:
            dll_header = runtime.readonly.pe_header(reader.read(pointer(research[0][0]), 8192))
            prior.require(dll_header["machine"] == 0x8664
                          and dll_header["timestamp"] == backend.manifest["PE_timestamp"]
                          and dll_header["size_of_image"] == backend.manifest["SizeOfImage"],
                          "Loaded build-7 DLL header differs from fixed manifest")
            report["loaded_tag_host_pe"] = dll_header
        report.update(module_base=hex(base), loaded_main_pe=disk,
            research_modules=[path for _, path in research],
            build_manifest_sha256=backend.manifest_sha, build_dll_sha256=backend.manifest["dll"]["sha256"])
        for _ in range(2):
            report["passes"].append(sample(reader, base, disk["size_of_image"]))
            held.identity_check()
        prior.require(report["passes"][0] == report["passes"][1], "Two complete selected samples differ")
        held.identity_check()
        prior.require([(a, canonical(p)) for a, p in held.modules()] == [(a, canonical(p)) for a, p in modules],
                      "Module set changed during two-pass sample")
        prior.require(source_pins() == initial_pins, "Reader or pinned field evidence changed during sample")
        report.update(status="sampled_equal", two_pass_equal=True)
    except Exception as exc:
        report.update(status="failed_no_retry", failure={"type": type(exc).__name__, "message": str(exc)})
    finally:
        if reader:
            report["rpm_budget"] = {"calls": reader.calls, "bytes": reader.bytes_read,
                "largest_read": reader.largest_read, "max_calls": prior.MAX_CALLS, "max_bytes": prior.MAX_BYTES}
        if held:
            held.close()
    report["peak_committed_bytes"] = check_memory_budget()
    report["limitations"] = ["Two equal passes are not an atomic main-thread snapshot or future-dispatch guarantee.",
        "FRA/ORL/MAL each have their own sampled diplomat vector and N/R; mission-null is not substituted for ID exclusion.",
        "Pair-war lookup is an RPM projection of the decoded index, not an invoked engine predicate.",
        "Capital+14b0 is a raw pinned native-path observation; exact province identity and annexation index are explicitly not guessed.",
        "Institution registry/TLS, accepted institution difference, local progress, range and full legality are not evaluated.",
        "A sampled condition is not permission to repeat a historical successful/dispatched/unknown action."]
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    brief = {k: report[k] for k in ("status", "two_pass_equal", "rpm_budget", "peak_committed_bytes") if k in report}
    if report["two_pass_equal"]:
        value = report["passes"][0]
        brief.update(date=value["roots"]["date"], actors=list(value["diplomats"]),
            envoys={tag: {k: item["native_id_exclusion"][k] for k in ("N", "R", "R_less_than_N")}
                    for tag, item in value["diplomats"].items()},
            pairs=[{"action": p["action"], "actor": p["actor_tag"], "target": p["target_tag"],
                "cooldown_allows": p["cooldown_only_allows"], "pair_war_index_member": p["pair_war_index"]["index_member_observed"],
                "dependency_type": p["dependency"]["object"]["type_name"]["name"] if p["dependency"]["object"] else None}
                for p in value["pairs"]])
    else:
        brief["failure"] = report["failure"]
    print(json.dumps(brief))
    return 0 if report["two_pass_equal"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
