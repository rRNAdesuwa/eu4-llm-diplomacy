"""Independent bounded knowledge-sharing RPM supplement; no native calls.

Uses the delivered remaining-pair reader's held-process/module/pause/Mod -1
guards, source checks, exclusive output and shared8192-call/1MiB two-pass
budget. It never calls a registry, TLS, modifier, range or action helper.
Unknown native context and unobserved bounds are retained explicitly.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work import probe_remaining_pairs_r3_1375 as guarded
from tools.build_diplomacy_unlock_mod import spans

ORIGINAL_SAMPLE = guarded.sample
ORIGINAL_SOURCE_PINS = guarded.source_pins
ADDED_SOURCES = (
    "work/probe_knowledge_context_r3_1375.py",
    "work/reports/diplomacy-corrective-20261014-r3/knowledge-layout-static.json",
    "work/reports/diplomacy-corrective-20261014-r3/knowledge-layout-disassembly.txt",
    "work/reports/diplomacy-corrective-20261014-r3/trace-knowledge-layout.py",
    "tools/build_diplomacy_unlock_mod.py", "tools/build_diplomacy_catalog.py",
)
AREA_SOURCE = ROOT.parent / "map/area.txt"
PAIRS = (("knowledge_sharing", "FRA", "JOL", "FRA", "JOL"),
         ("ask_knowledge_sharing", "MAL", "FRA", "FRA", "MAL"))
REGISTRY_RVA, REGISTRY_GUARD_RVA = 0x2328B10, 0x245B6B8
MAX_INSTITUTIONS, MAX_INSTITUTION_ID, MAX_AREA_PROVINCES = 32, 31, 96


def source_pins():
    pins = ORIGINAL_SOURCE_PINS()
    pins.update({name: {"bytes": len(raw := guarded.read(ROOT/name, 8*1024*1024)),
                        "sha256": guarded.digest(raw)} for name in ADDED_SOURCES})
    raw = guarded.read(AREA_SOURCE, 1024*1024)
    pins[AREA_SOURCE.resolve().as_posix()] = {"bytes": len(raw), "sha256": guarded.digest(raw)}
    guarded.prior.require(pins["work/probe_remaining_pairs_r3_1375.py"]["sha256"] ==
                          "444d028e17efdafa3d504abc02339eade28666e47aba37a5e09e1edecd389b61",
                          "Delivered guarded reader changed")
    return pins


def country_handle(raw, rows):
    slot = (raw >> 32) & 0xffff
    guarded.prior.require(slot < len(rows), "Knowledge province owner slot outside typed country table")
    if raw == 0x2d2d2d:
        guarded.prior.require(rows[slot].get("sentinel") is True and int(rows[slot]["handle"], 16) == raw,
                              "Knowledge province sentinel identity differs")
        return {"handle": hex(raw), "slot": slot, "sentinel": True}
    guarded.prior.require(rows[slot].get("identity_valid") is True
                          and int(rows[slot]["handle"], 16) == raw,
                          "Knowledge province full owner handle differs from typed identity")
    return {"handle": hex(raw), "slot": slot, "tag": rows[slot]["tag"],
            "selector": rows[slot]["selector"], "complete_identity_validated": True}


def registry_snapshot(reader, base):
    registry = base+REGISTRY_RVA
    guard = reader.integer(base+REGISTRY_GUARD_RVA)
    header = reader.read(registry, 0x20)
    begin, end = struct.unpack_from("<QQ", header, 0x10)
    result = {"address": hex(registry), "guard_raw": guard, "begin": hex(begin), "end": hex(end),
              "getter_called": False, "owner_thread_guard_evaluated": False,
              "header_sha256": hashlib.sha256(header).hexdigest(), "entries": []}
    if guard == -1:
        result["status"] = "uninitialized_guard_observed_not_called"
        return result
    if begin == end == 0:
        result.update(status="existing_empty_vector_observed", count=0)
        return result
    guarded.pointer(begin)
    guarded.pointer(end)
    guarded.prior.require(end >= begin and (end-begin) % 8 == 0 and (end-begin)//8 <= MAX_INSTITUTIONS,
                          "Existing institution registry vector exceeds 32-entry profile")
    count = (end-begin)//8
    raw = reader.read(begin, count*8) if count else b""
    entries = []
    for ordinal, (address,) in enumerate(struct.iter_unpack("<Q", raw)):
        guarded.pointer(address)
        object_header = reader.read(address, 0x14)
        index = struct.unpack_from("<i", object_header, 0x10)[0]
        guarded.prior.require(0 <= index <= MAX_INSTITUTION_ID,
                              "Native institution ID outside explicitly bounded0..31 profile")
        entries.append({"ordinal": ordinal, "address": hex(address), "id_raw_10": index,
                        "header_sha256": hashlib.sha256(object_header).hexdigest(),
                        "exact_type_vtable_and_name_not_guessed": True})
        guarded.prior.require(reader.integer(address+0x10) == index, "Institution candidate ID changed")
    guarded.prior.require(len({entry["address"] for entry in entries}) == count
                          and len({entry["id_raw_10"] for entry in entries}) == count,
                          "Existing registry contains duplicate pointer or ID")
    guarded.prior.require(reader.read(registry, 0x20) == header
                          and reader.integer(base+REGISTRY_GUARD_RVA) == guard,
                          "Institution registry header/guard changed within pass")
    result.update(status="existing_vector_sampled", count=count, entries=entries,
                  vector_sha256=hashlib.sha256(raw).hexdigest())
    return result


def indexed_values(reader, owner_address, field, ids):
    array = reader.qword(owner_address+field)
    result = {"field_offset": hex(field), "array": hex(array), "values_by_native_id": {},
              "native_vector_length_not_sampled": True}
    if not ids:
        result["status"] = "no_registry_candidate_ids_available"
        return result
    guarded.pointer(array)
    result["values_by_native_id"] = {str(index): reader.integer(array+index*4) for index in ids}
    guarded.prior.require(reader.qword(owner_address+field) == array, "Indexed institution field pointer changed")
    result["status"] = "selected_native_indices_sampled"
    return result


def distance_snapshot(reader, provider, recipient):
    address = int(provider["address"], 16)
    first = reader.read(address+0x2398, 16)
    second = reader.read(address+0x23b0, 16)
    a, b = struct.unpack("<QQ", first)
    c, d = struct.unpack("<QQ", second)
    for start, end in ((a, b), (c, d)):
        if start == end == 0:
            continue
        guarded.pointer(start)
        guarded.pointer(end)
        guarded.prior.require(0 <= end-start <= 32768 and (end-start) % 2 == 0,
                              "Provider distance cache header outside bounded WORD-vector profile")
    result = {"provider_tag": provider["tag"], "recipient_tag": recipient["tag"],
              "presence_begin_2398": hex(a), "presence_end_23a0": hex(b), "presence_bytes": b-a,
              "distance_begin_23b0": hex(c), "distance_end_23b8": hex(d), "distance_bytes": d-c,
              "recipient_slot": recipient["slot"], "raw_distance_word": None, "distance_milli": None,
              "native_cache_build_invalidation_unresolved": True}
    if b-a < 2 or d-c < 2:
        result.update(status="native_zero_branch_selected_by_observed_short_vector", distance_milli=0)
    elif recipient["slot"]*2+2 > d-c:
        result["status"] = "native_target_index_outside_observed_distance_vector_unknown"
    else:
        word = struct.unpack("<H", reader.read(c+recipient["slot"]*2, 2))[0]
        result.update(status="selected_word_sampled", raw_distance_word=word, distance_milli=word*1000)
    guarded.prior.require(reader.read(address+0x2398, 16) == first
                          and reader.read(address+0x23b0, 16) == second,
                          "Provider cache vector header changed within pass")
    return result


def signed32(value):
    return (value+2**31) % 2**32-2**31


def trunc_div(value, divisor):
    return (1 if value >= 0 else -1)*(abs(value)//divisor)


def range_arithmetic(base_range, modifier):
    factor = signed32(modifier+1000)
    scaled = trunc_div(base_range*factor, 1000)
    low = signed32(scaled)
    rounded = signed32(low+(500 if low > 0 else -500))
    remainder = rounded-trunc_div(rounded, 1000)*1000
    return signed32(rounded-remainder)


def provider_range_snapshot(reader, base, provider, image_size):
    address = int(provider["address"], 16)
    tech = guarded.pointer(reader.qword(address+0x2440))
    tech_range = reader.integer(tech+0x50)
    state = reader.integer(address+0x28c8)
    settings = guarded.pointer(reader.qword(base+0x2358080))
    override = reader.qword(settings+0x2da0)
    result = {"provider_tag": provider["tag"], "technology_pointer_2440": hex(tech),
              "base_range_raw_tech_50": tech_range, "modifier_context_state_raw_28c8": state,
              "modifier_id": 0x79, "dynamic_root_2358080": hex(settings),
              "dynamic_override_pointer_2da0": hex(override), "modifier_raw": None,
              "range_milli_projected": None, "engine_helper_called": False,
              "native_thread_cache_lookup_or_initialization_called": False}
    if override:
        guarded.pointer(override)
        vt = guarded.pointer(reader.qword(override))
        slot8 = reader.qword(vt+8)
        result.update(dynamic_override_vtable=hex(vt), dynamic_override_slot8=hex(slot8),
                      dynamic_override_slot8_rva=hex(slot8-base) if base <= slot8 < base+image_size else None,
                      dynamic_override_evaluated=False)
    if state == 1:
        result["status"] = "modifier_getter_requires_owner_thread_cache_context_unknown"
    else:
        # 93d750 returns country+28c8 when its state!=1 irrespective of the
        # thread-cache match. We do not invoke df320, which has a writing path.
        context = address+0x28d0
        dense = reader.byte(context+0x10)
        table = reader.qword(context+0x58)
        result.update(modifier_context_projection="state!=1 return country+28c8, then caller+8",
                      modifier_context=hex(context), modifier_dense_raw_10=dense, modifier_table=hex(table))
        if dense:
            modifier = reader.integer(guarded.pointer(table)+0x3cc)
            result["modifier_lookup_branch"] = "dense table+0x3cc"
        else:
            count = reader.integer(context+0x64)
            guarded.prior.require(-4096 <= count <= 4096, "Signed modifier sparse count exceeds bound")
            raw = reader.read(guarded.pointer(table), count*8) if count > 0 else b""
            matches = [{"ordinal": i, "value": struct.unpack_from("<i", raw, i*8+4)[0]}
                       for i in range(max(0, count)) if struct.unpack_from("<i", raw, i*8)[0] == 0x79]
            modifier = matches[0]["value"] if matches else 0
            result.update(modifier_lookup_branch="sparse first token0x79 else native zero branch",
                          modifier_count_signed=count, matching_modifier_entries=matches,
                          modifier_records_sha256=hashlib.sha256(raw).hexdigest())
            guarded.prior.require(reader.integer(context+0x64) == count, "Sparse modifier count changed")
        guarded.prior.require(reader.byte(context+0x10) == dense and reader.qword(context+0x58) == table,
                              "Modifier selected context header changed")
        result["modifier_raw"] = modifier
        if override:
            result["status"] = "modifier_observed_but_dynamic_override_unknown"
        else:
            result.update(status="native_arithmetic_projected_without_helper",
                          range_milli_projected=range_arithmetic(tech_range, modifier))
    guarded.prior.require(reader.qword(address+0x2440) == tech and reader.integer(tech+0x50) == tech_range
                          and reader.integer(address+0x28c8) == state
                          and reader.qword(base+0x2358080) == settings and reader.qword(settings+0x2da0) == override,
                          "Provider native range context changed within pass")
    return result


def area_catalog():
    text = guarded.read(AREA_SOURCE, 1024*1024).decode("utf-8-sig")
    values = {}
    for node in spans(text):
        ids = [int(child.key) for child in node.children if child.value is None and not child.children
               and child.key.lstrip("-").isdigit()]
        if ids:
            values[node.key] = ids
    guarded.prior.require(values, "Installed area map structural parse produced no province lists")
    return values


def recipient_area_snapshot(reader, game, recipient, rows, ids, base, image_size, catalog):
    country = int(recipient["address"], 16)
    capital = guarded.pointer(reader.qword(country+0x14b0))
    province_array = guarded.pointer(reader.qword(game+0x1ca8))
    delta = capital-province_array
    guarded.prior.require(delta >= 0 and delta % 0x2e10 == 0 and delta//0x2e10 < 65536,
                          "Recipient capital is not within decoded indexed province array")
    capital_id = reader.integer(capital+0x20)
    guarded.prior.require(capital_id == delta//0x2e10, "Recipient capital native/indexed ID mismatch")
    definition = guarded.pointer(reader.qword(capital+0x28))
    area = reader.qword(definition+0x40)
    result = {"recipient_tag": recipient["tag"], "capital": hex(capital), "capital_native_id": capital_id,
              "capital_definition_28": hex(definition), "area_pointer_40": hex(area),
              "business_type_exact_vtable_identity_proven": False, "provinces": [],
              "capital_area_semantics_static_status": "inference; optional exact installed-map vector correlation reported separately"}
    if not area:
        result["status"] = "native_selected_area_pointer_null_observed"
        result["province_ids"] = []
    else:
        guarded.pointer(area)
        header = reader.read(area+0x88, 16)
        begin, end = struct.unpack("<QQ", header)
        if begin == end == 0:
            raw = b""
        else:
            guarded.pointer(begin)
            guarded.pointer(end)
            guarded.prior.require(0 <= end-begin <= MAX_AREA_PROVINCES*4 and (end-begin) % 4 == 0,
                                  "Native selected capital-area ID vector exceeds96-province bound")
            raw = reader.read(begin, end-begin) if begin != end else b""
        province_ids = [value[0] for value in struct.iter_unpack("<i", raw)]
        guarded.prior.require(all(0 <= value < 65536 for value in province_ids)
                              and len(province_ids) == len(set(province_ids)), "Invalid/duplicate native area province IDs")
        provinces = []
        for index in province_ids:
            address = province_array+index*0x2e10
            identity = reader.read(address, 0x28)
            vt, native_id = struct.unpack_from("<Q", identity)[0], struct.unpack_from("<i", identity, 0x20)[0]
            guarded.prior.require(base <= vt < base+image_size and native_id == index,
                                  "Native area province indexed ID/vtable module bounds mismatch")
            owner_raw = reader.qword(address+0x468)
            owner = country_handle(owner_raw, rows)
            progress = indexed_values(reader, address, 0xd0, ids) if owner_raw == int(recipient["handle"], 16) else None
            provinces.append({"native_id": index, "address": hex(address), "vtable_rva_observed": hex(vt-base),
                              "exact_vtable_identity_pinned": False, "owner": owner,
                              "owner_complete_handle_matches_recipient": owner_raw == int(recipient["handle"], 16),
                              "institution_progress": progress})
            guarded.prior.require(reader.read(address, 0x28) == identity
                                  and reader.qword(address+0x468) == owner_raw,
                                  "Native area province identity/owner changed")
        matches = [name for name, map_ids in catalog.items() if len(map_ids) == len(province_ids)
                   and set(map_ids) == set(province_ids) and capital_id in map_ids]
        result.update(status="native_selected_area_vector_sampled", vector_begin=hex(begin), vector_end=hex(end),
                      vector_sha256=hashlib.sha256(raw).hexdigest(), province_ids=province_ids, provinces=provinces,
                      installed_area_exact_set_matches=matches, installed_area_match_unique=len(matches) == 1,
                      installed_map_source=AREA_SOURCE.resolve().as_posix())
        guarded.prior.require(reader.read(area+0x88, 16) == header, "Native capital area vector header changed")
    guarded.prior.require(reader.qword(country+0x14b0) == capital
                          and reader.qword(capital+0x28) == definition and reader.qword(definition+0x40) == area
                          and reader.qword(game+0x1ca8) == province_array, "Recipient capital-area path changed")
    return result


def sample(reader, base, image_size):
    value = ORIGINAL_SAMPLE(reader, base, image_size)
    roots, rows, countries = value["roots"], value["typed_country_rows"], value["countries"]
    registry = registry_snapshot(reader, base)
    ids = [entry["id_raw_10"] for entry in registry["entries"]]
    accepted = {tag: indexed_values(reader, int(countries[tag]["address"], 16), 0xc68, ids)
                for tag in ("FRA", "JOL", "MAL")}
    context_bits = {"233ff38_raw": reader.byte(base+0x233ff38), "233fed6_raw": reader.byte(base+0x233fed6)}
    context_bits.update(direct_global_branch_allows=context_bits["233ff38_raw"] != 0 and context_bits["233fed6_raw"] == 0,
                        owner_thread_TLS_not_sampled=True, initializer_called=False)
    catalog = area_catalog()
    provider_range = provider_range_snapshot(reader, base, countries["FRA"], image_size)
    pairs = []
    for action, actor_tag, target_tag, provider_tag, recipient_tag in PAIRS:
        provider, recipient = countries[provider_tag], countries[recipient_tag]
        original = next(p for p in value["pairs"] if p["action"] == action)
        provider_record = guarded.prior.pair_record(reader, provider, recipient)
        war = guarded.pair_war_index(reader, provider_record, recipient, roots["count"])
        distance = distance_snapshot(reader, provider, recipient)
        area = recipient_area_snapshot(reader, int(roots["game"], 16), recipient, rows, ids, base, image_size, catalog)
        candidates = []
        for entry in registry["entries"]:
            key = str(entry["id_raw_10"])
            p_accepted = accepted[provider_tag]["values_by_native_id"][key]
            r_accepted = accepted[recipient_tag]["values_by_native_id"][key]
            qualified = [province["native_id"] for province in area["provinces"]
                         if province["owner_complete_handle_matches_recipient"]
                         and province["institution_progress"]["values_by_native_id"][key] < 100000]
            candidates.append({"registry_ordinal": entry["ordinal"], "native_id": entry["id_raw_10"],
                               "provider_accepted_raw": p_accepted, "recipient_accepted_raw": r_accepted,
                               "provider_nonzero_recipient_zero": p_accepted != 0 and r_accepted == 0,
                               "qualifying_owned_area_province_ids": qualified,
                               "selected_candidate_fields_match": p_accepted != 0 and r_accepted == 0 and bool(qualified)})
        matches = [candidate for candidate in candidates if candidate["selected_candidate_fields_match"]]
        native_range, native_distance = provider_range["range_milli_projected"], distance["distance_milli"]
        counts = {tag: value["knowledge_sharing_selected_counts"][tag] for tag in (provider_tag, recipient_tag)}
        pairs.append({"action": action, "original_actor": actor_tag, "original_target": target_tag,
            "provider": provider_tag, "recipient": recipient_tag,
            "common_original_actor_envoys": actor_tag, "common_cooldown_pair": [actor_tag, target_tag],
            "common_cooldown_selected_projection": original["cooldown_only_allows"],
            "provider_to_recipient_record": provider_record, "provider_pair_war_index": war,
            "provider_distance": distance, "provider_native_range": provider_range,
            "provider_distance_le_range_selected_projection": native_distance <= native_range
                if native_range is not None and native_distance is not None else None,
            "participant_share_counts": counts,
            "share_counts_only_allows": all(item["signed_count_17dc"] <= 0 and item["signed_count_17c4"] <= 0
                                             for item in counts.values()),
            "recipient_native_area": area, "institution_candidate_selected_fields": candidates,
            "first_matching_candidate_by_observed_registry_order": matches[0] if matches else None,
            "candidate_evaluation_available": registry["status"] != "uninitialized_guard_observed_not_called",
            "legacy_scope": {"token": "0x3776", "ROOT": provider_tag, "FROM": recipient_tag},
            "native_predicates_called": False, "complete_legality_proven": False})
    guarded.prior.require(guarded.prior.roots(reader, base) == roots
                          and reader.byte(base+0x233ff38) == context_bits["233ff38_raw"]
                          and reader.byte(base+0x233fed6) == context_bits["233fed6_raw"],
                          "Knowledge roots/context bits changed within pass")
    value["knowledge_context_supplement"] = {"schema": "EU4TAG-KNOWLEDGE-CONTEXT-RPM-SUPPLEMENT/1",
        "registry": registry, "country_accepted_selected_indices": accepted, "context_gate_raw": context_bits,
        "pairs": pairs, "native_calls": 0, "complete_legality_proven": False,
        "limits": {"registry_entries": MAX_INSTITUTIONS, "native_id_max": MAX_INSTITUTION_ID,
                   "area_province_count": MAX_AREA_PROVINCES, "shared_calls": 8192, "shared_bytes": 1048576},
        "limitations": ["Registry and country/province arrays are observed existing data; no lazy initializer or engine helper is called.",
                        "Only native-selected institution indices are read; array length/capacity fields are not guessed.",
                        "Modifier state==1 needs the real engine-thread cache context; dynamic override also remains unresolved if nonnull.",
                        "Area business name is an inference unless the observed complete ID set matches one installed map area; exact class vtable is not pinned.",
                        "Selected field projection is not a complete native legality/AI acceptance/effect proof or authorization to resend an action."]}
    return value


def main():
    old_sample, old_pins = guarded.sample, guarded.source_pins
    try:
        guarded.sample, guarded.source_pins = sample, source_pins
        return guarded.main()
    finally:
        guarded.sample, guarded.source_pins = old_sample, old_pins


if __name__ == "__main__":
    raise SystemExit(main())
