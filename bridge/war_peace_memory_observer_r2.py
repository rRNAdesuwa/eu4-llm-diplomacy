"""R7-r2 current war-pair projection using the native war-index predicate.

No process opener, native call, sender or saved-war pointer input. This module
observes current graph membership; it cannot establish an atomic world lease,
war retirement, peace terms, or exclusive causality for an API request.
"""
from __future__ import annotations

import struct

from bridge.diplomacy_effect_observer import (BudgetReader, country, full_handle,
    relation, roots)
from bridge.tag_command_backend import require

SCHEMA = "EU4-WAR-PAIR-GRAPH/2"
WAR_VT = 0x1D1F768
WAR_ARRAY_VT = 0x1C38348
WAR_INDEX_VT = 0x1C3A538
LIMITS = {"global_wars": 64, "global_capacity": 512, "pair_index": 64,
          "side_members": 64, "war_outer_bytes": 0x218}


def pointer(value, size=1):
    require(type(value) is int and value >= 0x10000 and value % 8 == 0
            and type(size) is int and size > 0 and value+size <= 2**47,
            "Unaligned/noncanonical native range")
    return value


def _storage(data, capacity, used, stride, maximum, *, max_capacity=None):
    require(type(capacity) is int and type(used) is int
            and 0 <= used <= min(capacity, maximum)
            and 0 <= capacity <= (maximum if max_capacity is None else max_capacity),
            "Signed native count/capacity bound")
    require((capacity == 0 and data == 0) or capacity > 0, "Empty allocation metadata mismatch")
    if capacity:
        pointer(data, capacity*stride)


def _view(item):
    require(type(item) is dict, "R1 country view required")
    return {k: item[k] for k in ("address", "handle", "tag", "slot")}


def _index(r, owner, other, rel, base, root):
    embedded = int(owner["address"], 16)+0x14F8
    require(embedded == rel["root"], "Embedded relation identity differs")
    at = embedded+0x48
    header = r.read(at, 24)
    vt, data, capacity, used = struct.unpack("<QQii", header)
    require(vt == base+WAR_INDEX_VT, "War index type differs")
    _storage(data, capacity, used, 16, LIMITS["pair_index"])
    raw = r.read(data, used*16) if used else b""
    entries = []
    for slot, war in struct.iter_unpack("<i4xQ", raw):
        require(0 < slot < min(root["count"], 32768), "War index signed country slot invalid")
        pointer(war, LIMITS["war_outer_bytes"])
        entries.append((slot, war))
    require(len({slot for slot, _ in entries}) == len(entries), "Duplicate war-index country key")
    require(r.read(at, 24) == header, "War index header changed")
    selected = [war for slot, war in entries if slot == other["slot"]]
    # These are aliases, not two independent indexes or four independent votes.
    require(embedded+0x50 == int(owner["address"], 16)+0x1548, "Alias arithmetic differs")
    return dict(header_address=at, header=header, data=data, raw=raw, entries=entries,
                selected=selected[0] if selected else None,
                record46=rel["data"][0x46],
                projection=dict(owner_handle=owner["handle"], root=hex(embedded),
                    object=hex(at), data_field=hex(embedded+0x50),
                    country_data_alias=hex(int(owner["address"], 16)+0x1548),
                    independent_physical_indexes=1, capacity=capacity, count=used,
                    entries=[{"other_slot": s, "current_war_address": hex(w)} for s, w in entries],
                    target_match=bool(selected), relation_byte46_raw=rel["data"][0x46],
                    relation_byte46_mask4=bool(rel["data"][0x46] & 4),
                    relation_byte46_is_war_membership=False,
                    native_war_membership_predicate_rva="0xa68a00"))


def _war_shape(body):
    return (struct.unpack_from("<QI", body), struct.unpack_from("<i", body, 0x24)[0],
            struct.unpack_from("<QQQ", body, 0x48), struct.unpack_from("<QQQ", body, 0x78),
            struct.unpack_from("<QQQ", body, 0x150), struct.unpack_from("<I", body, 0x210)[0])


def sample_war_pair(r, base, expected_root, actor, target):
    """One strict current projection; invalid/unsupported layouts raise.

    actor/target are R1 country views, never historical war capabilities. The
    caller owns loaded-image/process authentication. All reads share r's budget.
    """
    require(isinstance(r, BudgetReader), "Use the existing R1 shared BudgetReader")
    pointer(base)
    root = roots(r, base)
    require(root == expected_root, "R1 world/date/health roots changed")
    actor_expected, target_expected = _view(actor), _view(target)
    a = country(r, base, root, int(actor_expected["handle"], 16), actor_expected["tag"])
    t = country(r, base, root, int(target_expected["handle"], 16), target_expected["tag"])
    require(a == actor_expected and t == target_expected
            and a["address"] != t["address"] and a["slot"] != t["slot"], "Current selected country identity differs")
    ah, th = int(a["handle"], 16), int(t["handle"], 16)
    forward, reverse = relation(r, a, t, base), relation(r, t, a, base)
    left, right = _index(r, a, t, forward, base, root), _index(r, t, a, reverse, base, root)
    require(left["selected"] == right["selected"], "Bilateral war-index pointers differ")

    game = int(root["game"], 16)
    global_at = game+0x1E28
    global_header = r.read(global_at, 24)
    vt, data, capacity, used = struct.unpack("<QQii", global_header)
    require(vt == base+WAR_ARRAY_VT, "Current global war-array type differs")
    _storage(data, capacity, used, 8, LIMITS["global_wars"], max_capacity=LIMITS["global_capacity"])
    require(r.b(game+0x1E54) == 0, "Global war-list iteration is unsupported")
    global_raw = r.read(data, used*8) if used else b""
    current_wars = [value for value, in struct.iter_unpack("<Q", global_raw)]
    for value in current_wars:
        pointer(value, LIMITS["war_outer_bytes"])
    require(len(set(current_wars)) == len(current_wars), "Duplicate global war pointer")
    current_set = set(current_wars)
    # Never follow a relation entry which is no longer globally reachable.
    for item in (left, right):
        require(all(w in current_set for _, w in item["entries"]), "Indexed war is absent from current global array")

    table_at = int(root["array"], 16)
    table_raw = r.read(table_at, root["count"]*8)
    lookup = struct.unpack("<"+"Q"*root["count"], table_raw)
    countries = {}
    def member(handle):
        slot, tag = full_handle(handle, root["count"])
        if handle not in countries:
            address = pointer(lookup[slot], 0x28)
            header = r.read(address, 0x28)
            require(struct.unpack_from("<QI", header) == (base+0x1C574A0, 357)
                    and struct.unpack_from("<Q", header, 0x20)[0] == handle,
                    "War member full country identity differs")
            countries[handle] = dict(slot=slot, tag=tag, handle=hex(handle), address=hex(address))
        return countries[handle]

    def side(body, offset):
        begin, end, cap = struct.unpack_from("<QQQ", body, offset)
        pointer(begin); pointer(end); pointer(cap)
        require(begin < end <= cap and (end-begin) % 8 == (cap-begin) % 8 == 0
                and (cap-begin)//8 <= LIMITS["side_members"], "War side-vector extent is unsupported")
        raw = r.read(begin, end-begin)
        handles = [value for value, in struct.iter_unpack("<Q", raw)]
        rows = [member(value) for value in handles]
        require(len({row["slot"] for row in rows}) == len(rows), "Duplicate country slot within war side")
        return handles, rows, (begin, end, cap)

    wars = {}
    opposing = []
    for current in current_wars:
        body = r.read(current, LIMITS["war_outer_bytes"])
        shape = _war_shape(body)
        require(shape[0] == (base+WAR_VT, 357), "Current war type/marker differs")
        started = shape[1]
        require(0 < started <= root["date"], "War date is invalid/future")
        attackers, attacking, av = side(body, 0x48)
        defenders, defending, dv = side(body, 0x78)
        require(not ({x["slot"] for x in attacking} & {x["slot"] for x in defending}),
                "Country slot occurs on both war sides")
        primary_attacker, primary_defender, goal = shape[4]
        member(primary_attacker); member(primary_defender); pointer(goal)
        require(primary_attacker in attackers and primary_defender in defenders,
                "Primary war leaders are not in their complete sides")
        require(_war_shape(r.read(current, LIMITS["war_outer_bytes"])) == shape, "War fields changed during side reads")
        aa, ad, ta, td = ah in attackers, ah in defenders, th in attackers, th in defenders
        opposite = (aa and td) or (ad and ta)
        if opposite:
            opposing.append(current)
        wars[current] = dict(current_war_address=hex(current), vtable_rva=hex(WAR_VT), marker=357,
            started_raw_date=started, primary_attacker_handle=hex(primary_attacker),
            primary_defender_handle=hex(primary_defender), goal_pointer_raw=hex(goal),
            goal_definition_layout_validated=False, attackers=attacking, defenders=defending,
            attacker_vector=[hex(x) for x in av], defender_vector=[hex(x) for x in dv],
            raw_outcome=shape[5], outcome_is_retirement=False, actor_side="attacker" if aa else "defender" if ad else None,
            target_side="attacker" if ta else "defender" if td else None, selected_pair_opponents=opposite)

    require(len(opposing) <= 1, "Multiple current opposing wars are ambiguous for the pair index")
    selected = opposing[0] if opposing else None
    require(left["selected"] == selected and right["selected"] == selected,
            "Bilateral index/global complete-side membership differs")
    # Native a68a00(record) returns counterpart-key presence in root+50/count5c.
    # Byte46/mask4 is conditionally marked by28ad30 even when war=NULL removes
    # the key, and is not read by that predicate. Retain its stability evidence
    # below, without turning this non-membership marker into a state boolean.
    require(bool(left["selected"]) == bool(selected) == bool(right["selected"]),
            "Native war-index predicate/global complete-side graph differs")
    # Other keys may legitimately share one war pointer. Validate those keys as
    # opposing slots, without counting their aliases as extra selected evidence.
    for item, owner in ((left, ah), (right, th)):
        for slot, address in item["entries"]:
            war = wars[address]
            al = {int(x["handle"], 16): x["slot"] for x in war["attackers"]}
            de = {int(x["handle"], 16): x["slot"] for x in war["defenders"]}
            require((owner in al and slot in de.values()) or (owner in de and slot in al.values()),
                    "Indexed country is not an opponent in its global war")
        require(r.read(item["header_address"], 24) == item["header"], "War-index header changed after global projection")
        if item["raw"]:
            require(r.read(item["data"], len(item["raw"])) == item["raw"], "War-index entries changed after global projection")
    require(r.read(global_at, 24) == global_header and (not global_raw or r.read(data, len(global_raw)) == global_raw)
            and r.b(game+0x1E54) == 0, "Global war container changed during projection")
    require(r.read(table_at, len(table_raw)) == table_raw, "Country lookup table changed during projection")
    for owner, other, earlier in ((a, t, forward), (t, a, reverse)):
        final = relation(r, owner, other, base)
        require(final["root"] == earlier["root"] and final["record"] == earlier["record"]
                and final["data"][0x46] == earlier["data"][0x46],
                "Pair record identity/diagnostic byte46 changed")
    require(country(r, base, root, ah) == a and country(r, base, root, th) == t
            and roots(r, base) == root, "Selected identity/world/date/health changed after war projection")
    return dict(schema=SCHEMA, roots=root, actor=a, target=t,
        pair_state="opponents" if selected else "not_currently_opponents",
        global_war_count=used, global_war_capacity=capacity, physical_pair_indexes=2,
        relation_indexes=[left["projection"], right["projection"]], wars=list(wars.values()),
        selected_war=next((w for w in wars.values() if w["selected_pair_opponents"]), None),
        complete_current_global_scan=True, historical_war_pointer_input_supported=False,
        global_array_vtable_rva=hex(WAR_ARRAY_VT), war_retired_proven=False,
        peace_terms_verified=False, peace_completion_verified=False,
        request_causality_verified=False, queue_removal_is_completion=False)


def capture_war_pair(r, base, root, actor, target):
    """Two consistent external projections, or unknown. Never a retry signal."""
    start_calls, start_bytes = getattr(r, "calls", 0), getattr(r, "bytes", 0)
    result = dict(schema="EU4-WAR-PAIR-CAPTURE/2", status="unknown", native_calls=0,
        memory_written=False, requests_published=0, automatic_command_retry=False,
        atomic_main_thread_snapshot=False, world_epoch_proven=False, world_lifetime_lease_proven=False,
        process_identity_authenticated_by_this_module=False, runtime_effect_verified=False,
        limits=dict(LIMITS), limitations=[
            "Current graph membership only; request audit, before-baseline and terms require separate evidence.",
            "Index/global removal does not prove war destruction, retirement, peace terms or queue acceptance.",
            "Two matching external reads can miss transient changes or ABA reuse.",
            "Unsupported or malformed current global wars make pair absence unknown; they are never skipped."])
    try:
        first = sample_war_pair(r, base, root, actor, target)
        second = sample_war_pair(r, base, root, actor, target)
        require(first == second, "Two complete selected war-graph passes differ")
        result.update(status="observed", two_pass_equal=True, projection=first, passes=[first, second])
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, struct.error) as exc:
        result.update(two_pass_equal=False, projection=None,
                      failure={"type": type(exc).__name__, "message": str(exc)})
    result["rpm_budget_used"] = dict(calls=getattr(r, "calls", 0)-start_calls,
                                    bytes=getattr(r, "bytes", 0)-start_bytes)
    return result
