"""Bounded offline audit of the fixed 39 previously unmapped diplomacy IDs.

No process access, native execution, injection or current-catalog hash cycle.
Mode evidence identifies code branches, never proves cancellation actually works.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys

from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg, token_descriptors

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_diplomacy_catalog import LOC

INPUTS = {
    "baseline": ("work/reports/diplomacy-unmapped-baseline-1375.json", "ce846a61dd9801ca8da797accbee102832a48406b3981078c002d1fa8c63f988"),
    "native": ("work/reports/native-diplomacy-1.37.5.json", "c64df6e043c9e7a498a25082e0e768902764e4a271ab3579f0eaddb2f1391633"),
    "fields": ("work/reports/native-action-fields-1375.json", "cfabb4622b7c82f9e2476a82352f91fa5d0f8ba0f8150e75aac47fb4aeaddc96"),
    "cancel": ("work/reports/native-pair-cancel-1375.json", "54dc047d85fe8c06528d5fb3824a1928f56fac2c4bbf24c26e205bcfb08e0df3"),
}


def mode(action, family, compare, literal, label, *, value=False, slot="0x70", kind="native_pair_boolean_mode", predicate=None):
    return {"action_id": action, "family": family, "method_slot": slot, "compare_rva": compare,
            "literal_rva": literal, "label": label, "value": value, "classification": kind,
            "state_predicate": predicate}


MODES = [
    mode("dissolve_alliance", "allianceaction", 0x512D83, 0x512EBA, "BREAKALLIANCENEWDESC"),
    mode("cancel_military_access", "milaccess", 0x525CC4, 0x525D51, "CANCELMILACCNEWDESC"),
    mode("revoke_military_access", "offermilaccess", 0x536BC4, 0x536C1B, "REVOKEMILACCNEWDESC"),
    mode("cancel_fleet_basing_rights", "fleet_access", 0x5302C0, 0x530476, "CANCELNAVALACCNEWDESC"),
    mode("revoke_fleet_basing_rights", "offer_fleet_access", 0x53469B, 0x5348B3, "REVOKENAVALACCNEWDESC"),
    mode("ask_support_independence", "support_independence_action", 0x50EF93, 0x50EFA1, "ASKSUPPORTINDEPENDENCENEWDESC", value=True,
         kind="native_pair_state_selected_mode", predicate="actor has a valid overlord, dependency helper 0x3d79f0 returns a definition, and definition+0x11a BYTE is nonzero"),
    mode("cancel_requested_independence_support", "support_independence_action", 0x50EF93, 0x50EFAA, "BREAKASKSUPPORTINDEPENDENCEDESC",
         kind="native_pair_state_selected_mode", predicate="same dependent-actor predicate as ask_support_independence"),
    mode("cancel_offered_independence_support", "support_independence_action", 0x50EF93, 0x50EFB1, "BREAKOFFERSUPPORTINDEPENDENCEDESC",
         kind="native_pair_state_selected_mode", predicate="dependent-actor predicate is false; actor is the provider of support"),
    mode("cancel_annexation", "annexationaction", 0x51A073, 0x51AE3E, "CANCEL_ANNEXNEWDESC"),
    mode("cancel_integration", "integrationaction", 0x51CCC0, 0x51D515, "CANCEL_INTEGRATENEWDESC"),
    mode("revoke_march", "designate_march", 0x514925, 0x515294, "CANCELMARCHNEWDESC"),
    mode("revoke_embargo", "embargoaction", 0x518344, 0x51839B, "REVOKEEMBARGONEWDESC"),
    mode("lift_excommunication", "excommunicate_action", 0x56ECBB, 0x56EEC5, "EXCOMMUNICATEREVOKEDESC"),
    mode("cancel_subsidies", "warsubsidy", 0x549286, 0x5492AA, "CANCELWARSUBDESC"),
    mode("cancel_trade_power_transfer", "transfer_trade_power", 0x57AB94, 0x57ABCE, "CANCEL_TRANSFER_TRADE_POWER_SELECT_DESC"),
    mode("cancel_steer_trade", "steer_trade", 0x57CA74, 0x57CC83, "CANCEL_STEER_TRADE_SELECT_DESC",
         kind="native_pair_state_selected_mode", predicate="false branch inspects the current actor-to-target trade-steering relation; another subbranch uses OUR_CANCEL_STEER_TRADE_SELECT_DESC"),
    mode("cancel_tributary", "tributary_state_action", 0x5A35AD, 0x5A38AE, "TRIBUTARYBREAKDESC",
         kind="native_pair_state_selected_mode", predicate="false branch compares recipient.overlord slot to original (+0x18) slot; the opposite direction uses TRIBUTARYSUBJECTBREAKDESC"),
    mode("stop_counterespionage", "counterespionage", 0x586EF1, 0x5870C7, "CANCEL_COUNTERESPIONAGE_LONG_DESC"),
    mode("stop_currying_favors", "curry_favors", 0x5AE261, 0x5AE281, "CANCEL_CURRY_FAVORS_DESC"),
    mode("stop_supporting_heir", "support_heir", 0x5969A1, 0x5969C1, "CANCEL_SUPPORT_HEIR_DESC"),
    mode("stop_supporting_rebels", "support_rebels", 0x583EAE, 0x584294, "CANCEL_SUPPORTREBELS_WARNING",
         predicate="false description resolves a currently supported rebel faction; matching faction/task identity is not validated here"),
    mode("cancel_infiltration", "infiltrate_administration", 0x57D79A, 0x57D9F4, "CONFIRM_CANCEL_INFILTRATE"),
    mode("kick_from_federation", "invite_to_federation", 0x58F0AE, 0x58F143, "KICKFROMFEDERATIONDESC"),
    mode("leave_federation", "request_to_join_federation", 0x58C96E, 0x58C9B4, "LEAVEFEDERATIONDESC"),
    mode("leave_coalition", "form_coalition", 0x58A72A, 0x58A806, "LEAVE_COALITION_REQ_DESC"),
    mode("join_coalition", "form_coalition", 0x58A72A, 0x58A786, "JOIN_COALITION_AGAINST", value=True,
         kind="native_pair_state_selected_alias", predicate="recipient country+0x1920 DWORD > 0; otherwise the same true-mode action displays FORM_COALITION_AGAINST"),
    mode("kick_from_trade_league", "invite_to_trade_league", 0x593550, 0x5936CE, "KICKFROMTRADELEAGUEDESC",
         kind="native_pair_state_selected_mode", predicate="same league pointer at both country+0x1948, first member in league+0x20..+0x28 has actor slot"),
    mode("leave_trade_league", "invite_to_trade_league", 0x593550, 0x593718, "LEAVETRADELEAGUEDESC",
         kind="native_pair_state_selected_mode", predicate="same league pointer, first member is not actor; initiating actor leaves, not the leader expelling recipient"),
    mode("revoke_condottieri", "condottieri_action", 0x59EC36, 0x59EDAC, "REVOKECONDOTTIERI_REQDES",
         kind="native_pair_state_selected_mode", predicate="existing first-direction relation at owner+0x2a8/count+0x2b4 resolves a rented-out army"),
    mode("cancel_condottieri", "condottieri_action", 0x59EC36, 0x59EE09, "CANCELCONDOTTIERI_REQDES",
         kind="native_pair_state_selected_mode", predicate="opposite relation resolves a rented-in army; no matching contract returns empty description"),
    mode("scornful_insult", "insultaction", 0x538B11, 0x538B03, "SCORNFULINSULTDESC", value=None,
         kind="native_pair_derived_field_variant", predicate="signed DWORD index at action+0x40 >= 0; ordinary insult uses a negative index"),
    mode("cancel_fabricate_claim", "fabricate_claim", 0x57691B, 0x576973, "CANCEL_FABRICATECLAIM", slot="0xe8", kind="native_ui_cancel_mode_effect_unverified"),
    mode("cancel_agitate_for_liberty", "agitate_for_liberty", 0x5889BB, 0x588A22, "CANCEL_AGITATEFORLIBERTY", slot="0xe8", kind="native_ui_cancel_mode_effect_unverified"),
    mode("cancel_sow_discontent", "sow_discontent", 0x58543B, 0x585493, "CANCEL_SOWDISCONTENT", slot="0xe8", kind="native_ui_cancel_mode_effect_unverified"),
    mode("cancel_justify_trade_conflict", "justify_trade_conflict", 0x57900B, 0x57907C, "CANCEL_JUSTIFY_TRADE_CONFLICT", slot="0xe8", kind="native_ui_cancel_mode_effect_unverified"),
]

COMMANDS = {
    "add_rival": (0x2FAE, 0x1C55138, 0x60, 0xEDA830),
    "remove_rival": (0x2FAF, 0x1C54A68, 0x60, 0xF163F0),
    "replace_rival_command": (0x3005, 0x1C54B10, 0x68, 0xEDA830),
    "createvassal": (0x2991, 0x1C55F40, 0x60, 0xEDD2C0),
}
EXTRA_ENTRIES = (0x51FB60, 0x51F020, 0xA6ADE0, 0x277310)
MAX_FILE = 4 * 1024 * 1024


def raw_file(path):
    if path.stat().st_size > MAX_FILE:
        raise ValueError("Input exceeds 4 MiB bound")
    return path.read_bytes()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def generate(game, unpacked, deps):
    check_memory_budget()
    pe = PE(game / "eu4.exe")
    if sha(pe.data) != SHA:
        raise ValueError("Unsupported executable SHA-256")
    loaded, inputs = {}, []
    for key, (relative, digest) in INPUTS.items():
        raw = raw_file(ROOT / relative)
        if sha(raw) != digest:
            raise ValueError(f"Changed reviewed input: {key}")
        loaded[key] = json.loads(raw)
        inputs.append({"path": relative, "sha256": digest, "bytes": len(raw), "origin": "repository"})
    baseline = loaded["baseline"]
    if len(baseline["rows"]) != 39 or baseline["game_sha256"].lower() != SHA:
        raise ValueError("Wrong fixed baseline")
    baseline_by_id = {a["action_id"]: a for a in baseline["rows"]}
    if set(baseline_by_id) != {m["action_id"] for m in MODES} | {"select_rival", "remove_rival", "create_vassal", "break_vassalization"}:
        raise ValueError("Incomplete classification of the frozen 39 IDs")
    native = {a["name"]: a for a in loaded["native"]["native_actions"]["actions"]}
    md, cs = make_disassembler(deps)
    if md is None:
        raise ValueError("Capstone unavailable")
    tokens = token_descriptors(pe)
    entries = set(EXTRA_ENTRIES)
    for item in MODES:
        family = native[item["family"]]
        table = int(family["vtable_rva"], 16)
        getter = int(family["accessor_rva"], 16)
        if pe.u64(pe.to_offset(table) + 0x98) - pe.base != getter or pe.bytes_at(getter, 6) != b"\xb8" + family["token_id"].to_bytes(4, "little") + b"\xc3":
            raise ValueError("Ordinary native token/vtable pin mismatch")
        entry = int(family["slots"][item["method_slot"]], 16)
        if pe.u64(pe.to_offset(table) + int(item["method_slot"], 16)) - pe.base != entry:
            raise ValueError("Mode method slot mismatch")
        entries.add(entry)
        # Retain the four ambiguous cancellation effect/legality methods, rather
        # than incorrectly elevating a real UI label to effect semantics.
        if item["classification"] == "native_ui_cancel_mode_effect_unverified":
            entries.update(int(family["slots"][s], 16) for s in ("0x48", "0x80", "0x88"))
    commands = {}
    for name, (token, table, size, ui) in COMMANDS.items():
        slots = {hex(o): pe.u64(pe.to_offset(table) + o) - pe.base for o in range(0, 0x70, 8)}
        if not all(pe.executable(rva) for rva in slots.values()):
            raise ValueError("Invalid independent command vtable")
        if pe.bytes_at(slots["0x50"], 6) != b"\xb8" + token.to_bytes(4, "little") + b"\xc3" or [t["name"] for t in tokens[token]] != [name]:
            raise ValueError("Independent command token getter mismatch")
        entries.update(slots[s] for s in ("0x10", "0x20", "0x40", "0x48", "0x50", "0x60"))
        entries.add(ui)
        commands[name] = {"name": name, "token_id": token, "token_descriptor": tokens[token][0], "vtable_rva": hex(table),
            "size_bytes": size, "ui_handler_rva": hex(ui), "slots": {s: hex(v) for s, v in slots.items()},
            "runtime_verified": False, "execution_verified": False, "ownership_verified": False}
    functions, instruction_objects, lookup, code_bytes = {}, {}, {}, 0
    for entry in sorted(entries):
        code, edges = bounded_cfg(pe, md, entry, window=0x4000, max_instructions=4000)
        code_bytes += sum(i.size for i in code)
        if code_bytes > 160 * 1024:
            raise ValueError("Total decode budget exceeded")
        rows = []
        for i in code:
            row = {"rva": hex(i.address), "bytes": i.bytes.hex(), "instruction": f"{i.mnemonic} {i.op_str}".strip()}
            rows.append(row)
            lookup[i.address] = row
            instruction_objects[i.address] = i
        functions[hex(entry)] = {"entry_rva": hex(entry), "instructions": rows, "edges": edges}
        check_memory_budget()

    def anchors(*rvas):
        if any(rva not in lookup for rva in rvas):
            raise ValueError("Missing reviewed instruction anchor: " + ",".join(hex(r) for r in rvas if r not in lookup))
        return [lookup[r] for r in rvas]

    def literal(rva, expected):
        ins = instruction_objects[rva]
        refs = [ins.address + ins.size + op.mem.disp for op in ins.operands if op.type == cs.CS_OP_MEM and op.mem.base == cs.x86_const.X86_REG_RIP]
        if len(refs) != 1 or pe.bytes_at(refs[0], len(expected) + 1) != expected.encode("ascii") + b"\0":
            raise ValueError(f"Literal reference mismatch at {rva:#x}: {expected}")
        return {**lookup[rva], "literal_rva": hex(refs[0]), "literal": expected}

    manifest_raw = raw_file(unpacked / "manifest.json")
    manifest = json.loads(manifest_raw)
    unpacked_base = {f["origin"]: f for f in manifest["files"] if f["path"].startswith("base/")}
    labels = {a["localization_key"] for a in baseline["rows"]} | {m["label"] + ("TITLE" if m["method_slot"] == "0xe8" else "") for m in MODES}
    labels |= {"OUR_CANCEL_STEER_TRADE_SELECT_DESC", "TRIBUTARYSUBJECTBREAKDESC", "FORM_COALITION_AGAINST", "CANCELVASSALTITLE"}
    localization, sources = {}, {}

    def source(path):
        rel = path.relative_to(game).as_posix()
        raw = raw_file(path)
        item = unpacked_base.get(rel)
        if item is None or item["sha256"] != sha(raw) or raw_file(unpacked / item["path"]) != raw:
            raise ValueError("Installed source does not match unpacked manifest")
        sources[rel] = {"path": rel, "sha256": sha(raw), "bytes": len(raw), "unpacked_path": item["path"]}
        return raw.decode("utf-8-sig")

    for path in sorted((game / "localisation").glob("*_l_english.yml")):
        raw = raw_file(path)
        matches = []
        for n, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
            match = LOC.match(line)
            if match and match[1] in labels:
                matches.append((match[1], {"path": path.relative_to(game).as_posix(), "line": n, "text": match[2]}))
        if matches:
            source(path)
            localization.update(matches)
    if set(localization) != labels:
        raise ValueError("Missing expected localization keys: " + str(labels - set(localization)))
    gui = source(game / "interface/countrydiplomacyview.gui")
    gui_controls = {}
    for control in ("button_createvassals", "play_as_released_vassal", "select_rivals_window"):
        found = next((n for n, line in enumerate(gui.splitlines(), 1) if f'"{control}"' in line), None)
        if found is None:
            raise ValueError("Missing expected GUI control")
        gui_controls[control] = {"path": "interface/countrydiplomacyview.gui", "line": found}

    field_actions = {a["name"]: a for a in loaded["fields"]["actions"]}
    audited = []
    for spec in MODES:
        family = native[spec["family"]]
        compare = instruction_objects[spec["compare_rva"]]
        if compare.mnemonic != "cmp" or ("+ 0x40]" if spec["value"] is None else "+ 0x38]") not in compare.op_str:
            raise ValueError("Mode discriminator is not the reviewed object field")
        following = instruction_objects.get(compare.address + compare.size)
        if following is None:
            raise ValueError("Missing instruction after mode discriminator")
        condition = {"value": spec["value"]} if spec["value"] is not None else {"signed_index_at_0x40": {"minimum": 0}}
        if spec["state_predicate"]:
            condition["state_predicate"] = spec["state_predicate"]
        label_key = spec["label"] + ("TITLE" if spec["method_slot"] == "0xe8" else "")
        action = {"action_id": spec["action_id"], "classification": spec["classification"],
            "native_family": spec["family"], "native_token_id": family["token_id"], "vtable_rva": family["vtable_rva"],
            "factory_rva": loaded["native"]["native_actions"]["factory_rva"], "factory_branch": family.get("factory_branch"),
            "accessor_rva": family["accessor_rva"], "token_slot_offset": "0x98",
            "size_bytes_candidate": family["layout"]["allocation_size_candidate"], "mode": condition,
            "method_slot": spec["method_slot"], "method_rva": family["slots"][spec["method_slot"]],
            "mode_instructions": anchors(compare.address, following.address), "literal_binding": literal(spec["literal_rva"], spec["label"]),
            "localization": {"key": label_key, **localization[label_key]},
            "baseline_localization": {"key": baseline_by_id[spec["action_id"]]["localization_key"], **localization[baseline_by_id[spec["action_id"]]["localization_key"]]},
            "derived_fields": field_actions[spec["family"]].get("derived_fields", []),
            "runtime_verified": False, "execution_verified": False, "public_parameter_binding_verified": False,
            "effect_semantics_verified": False, "ownership_verified": False,
            "unresolved": ["Native lifetime, wrapper/command ownership, player authority and transport are not tested for this operation.",
                "Current relation/task/definition identity, envoy selection, direction preconditions and original-vs-actor roles require runtime binding.",
                "A real name/mode branch does not establish UI reachability, successful application, acceptance or persistence."]}
        if spec["classification"] == "native_ui_cancel_mode_effect_unverified":
            action["unresolved"].append("The false name branch exists, but the reviewed effect body is not proof of a cancellation/rollback path. Do not reuse the positive effect or assume a running diplomat exists in this game version.")
            action["parameter_status_required"] = "partial"
            action["effect_review_entries"] = {s: family["slots"][s] for s in ("0x48", "0x80", "0x88")}
        if spec["action_id"] == "join_coalition":
            action["state_selected_alias_of"] = "form_coalition"
        if spec["action_id"] == "scornful_insult":
            action["unresolved"].append("The selected insult index must resolve to a valid insult definition. Public selector and valid range are not recovered; do not accept a raw offset or assume index=0.")
            action["parameter_status_required"] = "partial"
        audited.append(action)

    def fact(detail, *rvas):
        return {"detail": detail, "evidence_instructions": anchors(*rvas), "runtime_verified": False}

    facts = {
        "support_independence_roles": fact("Actor is resolved from action+0x10. Overlord marker and dependency helper 0x3d79f0/definition+0x11a choose asking for support versus offering it; action+0x38 independently chooses establishing/canceling. No extra public boolean or blind actor/target swap is proven.",
            0x50EF4A, 0x50EF64, 0x50EF6B, 0x50EF70, 0x50EF84, 0x50EF93, 0x50EFB8, 0x50EFBA),
        "league_roles": fact("False invite_to_trade_league requires matching league pointers. The first member handle distinguishes actor-as-leader (kick recipient) from actor-as-member (leave); same value=false is insufficient to bind these public IDs without current league roles.",
            0x593550, 0x59362B, 0x59364B, 0x59365E, 0x59366B, 0x59366F, 0x59368F, 0x593693, 0x5936CE, 0x593718),
        "coalition_state_alias": fact("True form_coalition reads target+0x1920. Positive count selects JOIN_COALITION_AGAINST, otherwise FORM_COALITION_AGAINST. This is a state-selected alias, not a second class. False selects LEAVE_COALITION_REQ_DESC.",
            0x58A72A, 0x58A74E, 0x58A776, 0x58A77D, 0x58A786, 0x58A796, 0x58A806),
        "condottieri_contract_direction": fact("The false description searches the existing directional condottieri relation lists at owner+0x2a8/count DWORD+0x2b4. Matching first direction yields REVOKECONDOTTIERI_REQDES (renting out); opposite direction yields CANCELCONDOTTIERI_REQDES (renting in). It resolves the existing army with 0xa64bf0; no contract produces an empty description. This does not establish the full cancellation execute path or ownership.",
            0x59EC36, 0x59EC92, 0x59ECA5, 0x59ECC3, 0x59ECD2, 0x59ECF0, 0x59ECFD, 0x59ED09, 0x59ED23, 0x59ED34, 0x59ED68, 0x59EDAC, 0x59EE09),
        "tributary_direction": fact("False tributary state compares recipient.overlord slot with original action+0x18 slot. One branch labels cancelling an overlord's tributary; the other labels the tributary breaking. Original cannot be silently replaced by actor on reply/reused objects.",
            0x5A35AD, 0x5A37E5, 0x5A3803, 0x5A380A, 0x5A3816, 0x5A3819, 0x5A38AE, 0x5A3A3A),
        "vassal_false_label_is_not_direction_permission": fact("Vassal name virtual +0xe8 has value=false CANCELVASSAL versus BREAKVASSAL, selected by relation helper 0xa6ade0. But false legality explicitly rejects actor.overlord == recipient with IS_SUBJECT. Therefore the subject-initiated public break_vassalization cannot reuse the proven overlord-only cancel_vassalization. A label branch is not a legal action.",
            0x51FB84, 0x51FBE7, 0x51FC03, 0x51FC13, 0x51FC3A, 0x51F435, 0x51F467),
        "rival_add_replace_ui": fact("UI 0xeda830 chooses an independent 0x68 replace_rival_command when UI+0x1c7 is set, otherwise independent 0x60 add_rival. Add stores actor at +0x50 and selected rival +0x58. Replace stores the selected new rival from UI+0x1b8 at +0x58 and the replaced rival from UI+0x1c0 at +0x60; serializer tokens country/rival/replace_rival_countrytag confirm the three handles. No ordinary diplomacy action or value mode is involved.",
            0xEDA836, 0xEDA866, 0xEDA86C, 0xEDA87D, 0xEDA884, 0xEDA8D6, 0xEDA8E0, 0xEDA8E7, 0xEDA8EB, 0xEDA8F1, 0xEDA95B, 0xEDA965, 0xEDA969,
            0x2AC80B, 0x2AC818, 0x2AC82A, 0x2AC837, 0x2AC849, 0x2AC856),
        "rival_remove_ui": fact("UI allocates 0x60 remove_rival, token0x2faf; actor from the UI controller/player context is command+0x50 and selected country is +0x58. Its parser/serializer are shared with add_rival, but its token, vtable, gate and execute differ. The weak command gate is not full gameplay/caller authority validation.",
            0xF16409, 0xF16432, 0xF16450, 0xF16459, 0xF16492, 0xF164A1, 0xF164AB, 0xF164AF, 0xF16506),
        "create_vassal_ui": fact("UI reads play_as_released_vassal, then always allocates and submits a 0x60 createvassal command. UI+0x1d0 released country goes to command+0x50; UI+0x1c8 former owner goes to +0x58. Gate requires the released-country object to have zero owned provinces (+0x1344); this is release of an existing landless country identity, not an offer to a living foreign ruler and not the script effect create_vassal.",
            0xEDD338, 0xEDD373, 0xEDD3CA, 0xEDD3DC, 0xEDD3E3, 0xEDD417, 0xEDD426, 0xEDD430, 0xEDD434, 0xEDD48E, 0x2A1E2C, 0x2A1E4A, 0x2A1E51),
        "create_and_play_are_two_commands": fact("After the first command, play checkbox==1 and context flag permit separately constructing set_controller through 0x277310 and submitting it. This is not a bool in createvassal, has no proven atomicity, and changes player identity. Both permissions and partial completion must be handled before executable API support.",
            0xEDD491, 0xEDD4CF, 0xEDD507, 0xEDD511, 0xEDD571, 0x277368, 0x277381),
    }
    facts["create_vassal_ui"]["checkbox_literal"] = literal(0xEDD338, "play_as_released_vassal")
    audited += [
        {"action_id": "select_rival", "classification": "independent_native_command", "primary_command": "add_rival", "alternative_commands": ["replace_rival_command"], "parameter_status_required": "partial", "fact_keys": ["rival_add_replace_ui"], "unresolved": ["Public replacement selector, current eligible rival/slot identity, costs and caller authority remain unbound."]},
        {"action_id": "remove_rival", "classification": "independent_native_command", "primary_command": "remove_rival", "alternative_commands": [], "parameter_status_required": "partial", "fact_keys": ["rival_remove_ui"], "unresolved": ["Full current handle, allowed removal, costs, controller authority and ownership are unverified."]},
        {"action_id": "create_vassal", "classification": "independent_native_command", "primary_command": "createvassal", "alternative_commands": ["set_controller"], "parameter_status_required": "partial", "fact_keys": ["create_vassal_ui", "create_and_play_are_two_commands"], "unresolved": ["Landless country identity and releasable provinces must be resolved from current state; ordinary live-country-only resolution is insufficient.", "Play-as is a separately submitted command; atomicity, partial completion and new player binding are not implemented."]},
        {"action_id": "break_vassalization", "classification": "native_ui_label_direction_rejected", "mapping_allowed": False, "observed_family": "vassalaction", "observed_value": False,
         "fact_keys": ["vassal_false_label_is_not_direction_permission"], "unresolved": ["Native false label exists but verified legality rejects the requested subject-to-overlord direction. Do not merge with cancel_vassalization or substitute an independence-war/script effect."]},
    ]
    for row in audited:
        row.update(runtime_verified=False, execution_verified=False, ownership_verified=False, public_parameter_binding_verified=False)
    counts = Counter(r["classification"] for r in audited)
    return {"schema_version": 1, "analysis_kind": "bounded_static_remaining_diplomacy_modes_and_commands", "game_sha256": SHA,
        "runtime_verified": False, "execution_verified": False, "public_backend_registered": False,
        "inputs": inputs, "source_inputs": sorted(sources.values(), key=lambda s: s["path"]),
        "source_audit": {"manifest_sha256": sha(manifest_raw), "selected_installed_sources_match_unpacked": True, "active_load_order_resolved": False},
        "baseline_count": 39, "classifications": dict(sorted(counts.items())), "actions": sorted(audited, key=lambda a: a["action_id"]),
        "commands": commands, "facts": facts, "gui_controls": gui_controls, "functions": functions,
        "limits": {"input_file_bytes": MAX_FILE, "function_window_bytes": 0x4000, "max_instructions_per_function": 4000,
            "total_decode_limit_bytes": 160 * 1024, "decoded_bytes": code_bytes, "memory_guard_bytes": 768 * 1024 * 1024},
        "boundaries": ["The frozen baseline is historical inventory, never a live catalog dependency; no circular report/catalog hash.",
            "No new executable API support. Static native UI mode, legality, dispatch, actual effect and persistence are separate evidence levels.",
            "The four old spy cancellation name modes have no verified cancellation effect; description/name branches do not authorize using positive effects as cancellation.",
            "The subject-initiated break_vassalization remains unmapped because the observed native false mode rejects that direction.",
            "Independent commands do not use the ordinary diplomacy factory; internal UI roles and pointers are not accepted as public raw parameters."]}


def render_docs(report):
    rows = report["actions"]
    return "\n".join(["# 剩余 39 个外交 ID 的静态分类", "",
        "本报告来自固定的 274/232 目录基线，只读精确 SHA EXE、既有原生报告及解包一致的安装资料；不访问游戏进程。复现：`python work/trace_diplomacy_modes.py --check`。", "",
        f"游戏 SHA-256：`{SHA}`。固定清单 SHA-256：`{INPUTS['baseline'][1]}`。固定清单不会随目录增加映射而改写，避免摘要循环。", "",
        "35 个 ID 找到普通外交类的具体模式分支，3 个是独立 command，1 个有同名原生 UI 分支却被合法性明确拒绝该方向。全部 execution_verified/runtime_verified/ownership_verified=false；所有权、原生实际效果、响应和存档重载都需分别证明。", "",
        "## 模式不是新的工厂类", "",
        "联盟解除使用 allianceaction false，和大国的 break_alliance 第三国要求不同。请求军通/自己取消使用 milaccess，主动给予/撤回使用 offermilaccess；舰队停泊对应两套同方向类。证据是各类自身的 action+0x38 分支和文案，不是共享 value setter。", "",
        "支持独立的请求/提供由发起国是否符合原生依赖条件选择，value 再选择开始/撤销。联盟、朝贡、佣兵与贸易关系也有依当前状态区分方向的分支，不能只填 false 就把所有公开操作互换。蔑视侮辱由 signed index+0x40>=0 选择，不是 value=false；选项定义解析仍未完成。加入包围网是 form_coalition 的 true 模式在目标已有包围网时的名称分支，保留独立 ID 兼容。", "",
        "## 不能当作已完成取消的四个分支", "",
        "伪造宣称、煽动独立、散布不满、制造贸易争端确有 value=false→CANCEL_* 的原生名称虚方法。已保留其效果和合法性函数作审查材料，但这不能证明当前版本存在相应运行任务，也没有证明 false 会撤销既有效果。它们归类 native_ui_cancel_mode_effect_unverified，参数保持 partial，禁止把正向即时效果当作取消执行。", "",
        "break_vassalization 更直接存在冲突：vassalaction 的 false 名称有 BREAKVASSAL，但合法性拒绝 actor.overlord==recipient。该 ID 继续未映射，不能借用宗主解除的 cancel_vassalization，也不能悄悄替换成宣战或 free_vassal 脚本效果。", "",
        "## 独立命令", "",
        "select_rival 的空槽选择为 add_rival 0x60；替换已有槽位为 replace_rival_command 0x68，具有第三个国家字段。remove_rival 是另一 0x60 类，共享 parser 不代表共享 token/效果。三者都使用独立 command 布局，不能投进普通外交工厂。", "",
        "create_vassal 对应 createvassal 0x60 命令，释放目标是当前没有省份的国家对象，和外交附庸提议、同名脚本效果均不同。play_as_released 复选框会在释放提交之后另行构造 set_controller；没有原子性，也没有玩家身份变更后的安全续接。", "",
        "| ID | 分类 | 原生家族/命令 |", "| --- | --- | --- |",
        *[f"| `{a['action_id']}` | `{a['classification']}` | `{a.get('native_family', a.get('primary_command', a.get('observed_family', 'unknown')))}` |" for a in rows], "",
        "精确 token、虚表、源文件哈希、模式指令、字符串引用、状态谓词和待验证项均保存在机器报告。RVA 只作为离线证据；接口不接受 raw pointer/RVA/脚本。", ""])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path)
    parser.add_argument("--unpacked", type=Path, default=ROOT / "work/runtime/unpacked-1.37.5")
    parser.add_argument("--deps", type=Path, default=Path(os.environ.get("TEMP", ".")) / "eu4-native-analysis-deps")
    parser.add_argument("--output", type=Path, default=ROOT / "work/reports/native-diplomacy-modes-1375.json")
    parser.add_argument("--docs", type=Path, default=ROOT / "docs/native-diplomacy-modes-1375.md")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.game_root is None:
        from local_config import get_value
        args.game_root = Path(get_value("EU4_GAME_ROOT"))
    report = generate(args.game_root, args.unpacked, args.deps)
    products = {args.output: json.dumps(report, ensure_ascii=False, indent=2) + "\n", args.docs: render_docs(report)}
    stale = []
    for path, text in products.items():
        raw = text.encode("utf-8")
        if args.check:
            if not path.is_file() or path.read_bytes() != raw:
                stale.append(path.name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    print(json.dumps({"mode": "check" if args.check else "write", "sha256": sha(products[args.output].encode("utf-8")),
        "bytes": len(products[args.output].encode("utf-8")), "classifications": report["classifications"], "decoded_bytes": report["limits"]["decoded_bytes"], "stale": stale}))
    return int(bool(stale))


if __name__ == "__main__":
    raise SystemExit(main())
