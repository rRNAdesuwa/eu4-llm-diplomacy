"""Generate the disposable diplomacy unlock mod from exact 1.37.5 scripts.

This changes script/define gates, never native senders or action effects. Native
object/role/war/province validity and hidden engine checks still apply.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_diplomacy_catalog import TOKEN, parse_script

NAME = "llm_diplomacy_unlock"
DEFAULT_BASE = ROOT / "work/runtime/unpacked-1.37.5/base"
EXE_SHA = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
SUBJECT_NORMALIZER_SHA = "f5b15d6f30de12da1df2b09d304308327e4932dda57d3cddd69d3d51e39f165c"

# Every key is checked against its actual namespace in the installed defines.
# Small positive costs keep the native spend path meaningful.
DEFINES = {
    "NDiplomacy": {
        # The engine requires now > deadline, so 0 still rejects same-date
        # proposals. Its signed month adder supports -1; future deadlines are
        # placed in the past. This does not clear deadlines in loaded saves.
        "DIPLOMAT_COOLDOWN_TIME": -1, "DIPLOMAT_SPEED": 100000,
        "DAYS_TO_DECLARE_WAR": 0, "OFFENSIVE_WAR_COOLDOWN": 0,
        "VASSALIZE_BASE_DEVELOPMENT_CAP": 1000000,
        "MARCH_BASE_DEVELOPMENT_CAP": 1000000,
        "MIN_RELATIONS_TO_ALLY": -200,
        "MIN_RELATIONS_TO_SUPPORT_INDEPENDENCE": -200,
        "INTEGRATE_UNION_MIN_YEARS": 0, "INTEGRATE_VASSAL_MIN_YEARS": 0,
        "SPY_DISCOVERY_COOLDOWN_MONTHS": 0, "BASE_SPY_DISCOVERY_CHANCE": 0,
        "COUNTERESPIONAGE_DISCOVER_CHANCE": 0,
        "BUILD_SPY_NETWORK_SPEED": 100, "SPY_NETWORK_DISTANCE_EFFECT": 0,
        "SPY_NETWORK_DECAY": 0,
        "FABRICATE_CLAIM_COST": 1, "FABRICATE_CLAIM_COST_MODIFIER_PER_CLAIM": 0,
        "JUSTIFY_TRADE_CONFLICT_COST": 1, "INFILTRATE_ADMINISTRATION_COST": 1,
        "SABOTAGE_REPUTATION_COST": 1, "STEAL_MAPS_COST": 1,
        "SUPPORT_REBELS_COST": 1, "SOW_DISCONTENT_COST": 1,
        "AGITATE_FOR_LIBERTY_COST": 1, "SABOTAGE_RECRUITMENT_COST": 1,
        "SLANDER_MERCHANTS_COST": 1, "CORRUPT_OFFICIALS_COST": 1,
        "INCREASE_TRUST_COST": 1, "PREPARE_FOR_WAR_COST": 1,
        "CALL_TO_ARMS_COST": 1, "CONDOTTIERI_MIN_DURATION": 0,
        "MIN_MONTHLY_COST_FOR_INFLUENCE_NATION": 0,
        "MIN_PAPAL_INFLUENCE_TO_PREVENT_EXCOMMUNICATION": 1000000,
        "DIPLOANNEX_LIBERTY_THRESHOLD": 101,
        "TRUCE_YEARS": 0, "SCALED_TRUCE_YEARS": 0,
        "REQUEST_HEIR_TRUCE": 0, "THREATEN_WAR_TRUCE_YEARS": 0,
        "FORCE_BREAK_ALLIANCE_TRUCE_YEARS": 0, "ANNUL_TREATIES_YEARS": 0,
        "JUSTIFY_TRADE_CONFLICT_LIMIT": 0,
        "JUSTIFY_TRADE_CONFLICT_ACTOR_LIMIT": 0,
        "SCORNFUL_INSULT_PRESTIGE_COST": 0,
        "AE_COALITION_THRESHOLD": 201,
    },
    "NCountry": {
        "FEDERATION_ACTION_COOLDOWN": 0, "BREAK_ALLIANCE_ACTION_COOLDOWN": 0,
        "TRADE_FAVORS_ACTION_COOLDOWN": 0, "REDUCE_RELATION_ACTION_COOLDOWN": 0,
        "REQUEST_EXTRA_LEVIES_COOLDOWN_MONTHS": 0,
        "SEIZE_COURT_RESOURCES_COOLDOWN_MONTHS": 0,
        "FORCE_CONVERT_COOLDOWN_DURATION": 0,
        "CHANGE_COLONIAL_TYPE_COOLDOWN_DURATION": 0,
        "BREAK_ALLIANCE_NON_GREAT_POWER_FAVOR_COST": 1,
        "BREAK_ALLIANCE_REQUIRED_OPINION": -200,
        "BREAK_ALLIANCE_OPINION_TO_NOT_WANT_TO": 201,
        "RETURN_CORE_FAVOR_COST_PER_DEV": 1, "RETURN_CORE_REQUIRED_OPINION": -200,
        "REDUCE_OPINION_FAVOR_COST": 1, "REDUCE_OPINION_REQUIRED_OPINION": -200,
        "REDUCE_OPINION_OPINION_TO_NOT_WANT_TO": 201,
        "TRADE_FAVORS_FOR_GOLD_FAVOR_COST": 1,
        "TRADE_FAVORS_FOR_GOLD_REQUIRED_OPINION": -200,
        "TRADE_FAVORS_FOR_MEN_FAVOR_COST": 1,
        "TRADE_FAVORS_FOR_MEN_REQUIRED_OPINION": -200,
        "TRADE_FAVORS_FOR_SAILORS_FAVOR_COST": 1,
        "TRADE_FAVORS_FOR_SAILORS_REQUIRED_OPINION": -200,
        "TRADE_FAVORS_FOR_HEIR_FAVOR_COST": 1,
        "TRADE_FAVORS_FOR_HEIR_REQUIRED_OPINION": -200,
        "TRADE_FAVORS_FOR_TRUST_REQUIRED_OPINION": -200,
        "TRADE_FAVORS_FOR_WAR_PREP_REQUIRED_OPINION": -200,
        "BREAK_MARRIAGE_STABILITY_PENALTY": 0,
        "BREAK_MARRIAGE_PRESTIGE_PENALTY": 0,
    },
}

BASE_MODIFIERS = {
    "diplomats": "102", "diplomatic_upkeep": "1004",
    "diplomatic_reputation": "1000", "accept_vassalization_reasons": "10000",
    "transfer_trade_power_reasons": "10000", "envoy_travel_time": "-0.99",
    "spy_offence": "100",
    "diplomatic_annexation_cost": "-0.90", "reduced_liberty_desire": "10000",
    "country_diplomatic_power": "100", "improve_relation_modifier": "100",
}


@dataclass
class Span:
    key: str
    start: int
    end: int
    value: str | None = None
    children: list["Span"] = field(default_factory=list)
    close: int | None = None


def spans(text: str) -> list[Span]:
    parse_script(text)  # Independent structural scanner, including quote validation.
    tokens = [(m.group(), m.start(), m.end()) for m in TOKEN.finditer(text)
              if not m.group().isspace() and not m.group().startswith("#")]
    pos = 0

    def block(nested=False):
        nonlocal pos
        nodes = []
        while pos < len(tokens):
            key, start, end = tokens[pos]
            pos += 1
            if key == "}":
                if not nested:
                    raise ValueError("unexpected closing brace")
                return nodes, start, end
            node = Span(key.strip('"'), start, end)
            if pos < len(tokens) and tokens[pos][0] == "=":
                pos += 1
                value, vs, ve = tokens[pos]
                pos += 1
                if value == "{":
                    node.children, node.close, node.end = block(True)
                else:
                    node.value, node.end = value.strip('"'), ve
            nodes.append(node)
        if nested:
            raise ValueError("unclosed block")
        return nodes, None, len(text)

    return block()[0]


def patch(text: str, edits: list[tuple[int, int, str]]) -> str:
    ordered = sorted(edits, key=lambda e: (e[0], e[1]))
    for left, right in zip(ordered, ordered[1:]):
        if left[1] > right[0]:
            raise ValueError("overlapping edits")
    for start, end, replacement in reversed(ordered):
        text = text[:start] + replacement + text[end:]
    parse_script(text)
    return text


def replace_fields(node: Span, replacements: dict[str, str], edits, *, add_missing=False):
    found = set()
    for child in node.children:
        if child.key in replacements:
            found.add(child.key)
            edits.append((child.start, child.end, f"{child.key} = {replacements[child.key]}"))
    missing = replacements.keys() - found
    if add_missing and missing:
        if node.close is None:
            raise ValueError("cannot add fields to scalar")
        additions = "\n" + "\n".join(f"\t{k} = {replacements[k]}" for k in sorted(missing)) + "\n"
        edits.append((node.close, node.close, additions))


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(base: Path, destination: Path, *, replace=False) -> dict:
    sources, outputs, counts = {}, {}, {}
    effects = []

    def read(rel):
        data = (base / rel).read_bytes()
        sources[rel] = {"sha256": digest(data), "bytes": len(data)}
        return data.decode("utf-8-sig")

    def write(rel, text, *, bom=False):
        parse_script(text) if rel.endswith((".txt", ".mod")) else None
        data = text.encode("utf-8-sig" if bom else "utf-8")
        outputs[rel] = data

    def unchanged_effects(rel, before, after, keys):
        def collect(text):
            return [(n.key, c.key, text[c.start:c.end]) for n in spans(text)
                    for c in n.children if c.key in keys]
        old, new = collect(before), collect(after)
        if old != new:
            raise ValueError(f"action effects changed: {rel}")
        effects.append({"path": rel, "preserved_effect_blocks": len(old)})

    rel = "common/diplomatic_actions/00_diplomatic_actions.txt"
    original = read(rel)
    edits, count = [], 0
    for node in spans(original):
        for condition in node.children:
            if condition.key == "condition":
                replace_fields(condition, {"potential": "{ always = yes }", "allow": "{ always = yes }"}, edits, add_missing=True)
                count += 1
    changed = patch(original, edits)
    unchanged_effects(rel, original, changed, {"effect", "pre_effect"})
    write(rel, changed)
    counts["native_additional_condition_blocks"] = count

    rel = "common/new_diplomatic_actions/00_diplomatic_actions.txt"
    original = read(rel)
    edits, count, acceptance = [], 0, 0
    for node in spans(original):
        if node.key == "static_actions":
            continue
        fields = {c.key: c for c in node.children}
        required = fields["require_acceptance"].value == "yes"
        replacements = {"is_visible": "{ always = yes }", "is_allowed": "{ always = yes }",
                        "ai_will_do": "{ always = no }"}
        if required:
            replacements["ai_acceptance"] = "{ add_entry = { name = llm_unlock_acceptance export_to_variable = { variable_name = ai_value value = 100000 } } }"
            acceptance += 1
        replace_fields(node, replacements, edits, add_missing=True)
        count += 1
    changed = patch(original, edits)
    unchanged_effects(rel, original, changed, {"on_accept", "on_decline", "require_acceptance"})
    # static_actions is the native registration table, never replaced with substitutes.
    if original[spans(original)[0].start:spans(original)[0].end] != changed[spans(changed)[0].start:spans(changed)[0].end]:
        raise ValueError("native registration table changed")
    write(rel, changed)
    counts.update(scripted_diplomatic_actions=count, scripted_acceptance_boosts=acceptance)

    rel = "common/subject_types/00_subject_types.txt"
    original = read(rel)
    nodes = spans(original)
    default = next(n for n in nodes if n.key == "default")
    keys = [c.key for c in default.children]
    interactions = keys[keys.index("embargo_rivals"):keys.index("expel_ronin") + 1]
    changes = {k: "yes" for k in interactions}
    # These four fields are relationship-class lists, not country triggers.
    # The engine rejects `always` here. Use only the native list vocabulary.
    subject_names = [n.key for n in nodes if n.children and n.key != "default"]
    relation_classes = "{ independent_nations = yes other_overlord = all " + " ".join(
        f"same_overlord = {name}" for name in subject_names) + " }"
    changes.update({k: relation_classes for k in ("can_fight", "can_rival", "can_ally", "can_marry")})
    changes["is_potential_overlord"] = "{ always = yes }"
    changes.update(can_be_annexed="yes", can_be_integrated="yes", can_gain_favors="yes")
    edits = []
    for node in nodes:
        if node.children:  # Leave required forward declarations intact.
            replace_fields(node, changes, edits, add_missing=True)
    write(rel, patch(original, edits))
    counts.update(subject_interaction_switches=len(interactions), subject_type_definitions=sum(bool(n.children) for n in nodes))

    # on_dependency_gained otherwise converts these special types back to
    # vassal when a disposable test actor lacks the associated government
    # ability. Disable only that fallback guard; keep native action effects
    # and every other helper intact.
    rel = "common/scripted_effects/01_scripted_effects_for_diplomacy.txt"
    original = read(rel)
    if sources[rel]["sha256"] != SUBJECT_NORMALIZER_SHA:
        raise ValueError("special-subject normalizer source changed")
    helper = [n for n in spans(original) if n.key == "convert_special_subject_to_vassal"]
    if len(helper) != 1 or len(helper[0].children) != 1 or helper[0].children[0].key != "if":
        raise ValueError("special-subject fallback shape changed")
    branch = helper[0].children[0]
    limits = [n for n in branch.children if n.key == "limit"]
    if len(limits) != 1:
        raise ValueError("special-subject fallback requires one outer limit")
    guard = limits[0]
    write(rel, patch(original, [(guard.start, guard.end, "limit = { always = no }")]))
    counts["special_subject_normalization_guards_disabled"] = 1

    rel = "common/static_modifiers/00_static_modifiers.txt"
    original = read(rel)
    node = next(n for n in spans(original) if n.key == "base_values")
    edits = []
    replace_fields(node, BASE_MODIFIERS, edits, add_missing=True)
    write(rel, patch(original, edits))

    rel = "common/technologies/dip.txt"
    original = read(rel)
    nodes = spans(original)
    unlocks = {c.key: "yes" for n in nodes if n.key == "technology" for c in n.children
               if c.value == "yes" and (c.key.startswith("may_") or c.key == "allow_client_states")}
    edits = []
    replace_fields(next(n for n in nodes if n.key == "technology"), unlocks, edits, add_missing=True)
    write(rel, patch(original, edits))
    counts["technology_unlocks_at_level_zero"] = sorted(unlocks)

    rel = "common/scripted_functions/00_scripted_functions.txt"
    original = read(rel)
    edits, count = [], 0
    for node in spans(original):
        if node.key in {"will_demand_annexation", "can_join_hre", "can_leave_hre", "can_join_hre_league", "can_leave_hre_league"}:
            for condition in node.children:
                if condition.key == "condition":
                    replace_fields(condition, {"potential": "{ always = yes }", "allow": "{ always = yes }"}, edits, add_missing=True)
                    count += 1
    write(rel, patch(original, edits))
    counts["additional_diplomacy_function_conditions"] = count

    rel = "common/government_mechanics/17_shogunate.txt"
    original = read(rel)
    edits, count = [], 0
    for node in spans(original):
        replace_fields(node, {"available": "{ always = yes }"}, edits)
        for group in node.children:
            if group.key == "interactions":
                for interaction in group.children:
                    replace_fields(interaction, {"trigger": "{ always = yes }", "cooldown_years": "0"}, edits)
                    count += 1
    changed = patch(original, edits)
    def gov_effects(text):
        return [text[c.start:c.end] for n in spans(text) for g in n.children if g.key == "interactions"
                for a in g.children for c in a.children if c.key == "effect"]
    if gov_effects(original) != gov_effects(changed):
        raise ValueError("government interaction effects changed")
    write(rel, changed)
    counts["shogunate_interactions"] = count

    counts["scripted_peace_terms"] = 0
    for source in sorted((base / "common/peace_treaties").glob("*.txt")):
        rel = source.relative_to(base).as_posix()
        original = read(rel)
        edits = []
        for node in spans(original):
            if node.key == "make_dummy":  # Disabled engine documentation example, not a real action.
                continue
            replace_fields(node, {"is_visible": "{ always = yes }", "is_allowed": "{ always = yes }",
                                  "requires_is_allowed": "no", "requires_demand_independence": "no",
                                  "power_cost_base": "0", "warscore_cost": "{ no_provinces = 1 }",
                                  "warscore_cap": "1"}, edits, add_missing=True)
            counts["scripted_peace_terms"] += 1
        changed = patch(original, edits)
        unchanged_effects(rel, original, changed, {"effect", "is_make_subject", "applies_to_war_target"})
        write(rel, changed)

    define_source = read("common/defines.lua")
    section, available = None, {}
    for line in define_source.splitlines():
        match = re.fullmatch(r"(N\w+)\s*=\s*\{", line.strip())
        if match:
            section = match[1]
        assignment = re.match(r"\s*([A-Z][A-Z0-9_]*)\s*=\s*([^,]+),", line)
        if section and assignment:
            available[(section, assignment[1])] = assignment[2].strip()
    overrides = []
    for section, values in DEFINES.items():
        for key, value in values.items():
            if (section, key) not in available:
                raise ValueError(f"unknown 1.37.5 define {section}.{key}")
            overrides.append({"namespace": section, "key": key, "original": available[section, key], "test": value})
    write("common/defines/zzzz_llm_diplomacy_unlock.lua", "-- Disposable 1.37.5 test campaigns only.\n" + "\n".join(
        f"NDefines.{v['namespace']}.{v['key']} = {v['test']}" for v in overrides) + "\n")
    counts["define_overrides"] = len(overrides)

    # Preparation is explicitly separate from native diplomatic requests. No
    # vanilla action has been replaced by a direct scripted effect.
    write("common/scripted_effects/llm_diplomacy_unlock.txt", """llm_unlock_refill_country = {
    remove_country_modifier = llm_unlock_envoy_pool
    add_country_modifier = { name = llm_unlock_envoy_pool duration = -1 }
    add_treasury = 100000
    add_adm_power = 1000
    add_dip_power = 1000
    add_mil_power = 1000
    add_prestige = 200
    add_stability = 6
    add_manpower = 1000
    add_sailors = 100000
}
llm_unlock_prepare_pair = {
    llm_unlock_refill_country = yes
    add_favors = { who = FROM amount = 100 }
    add_trust = { who = FROM value = 100 mutual = yes }
    add_spy_network_in = { who = FROM value = 100 }
    FROM = { llm_unlock_refill_country = yes }
}
llm_unlock_clear_pair_opinion = {
    remove_opinion = { who = FROM modifier = llm_unlock_friendly }
    remove_opinion = { who = FROM modifier = llm_unlock_hostile }
    FROM = {
        remove_opinion = { who = ROOT modifier = llm_unlock_friendly }
        remove_opinion = { who = ROOT modifier = llm_unlock_hostile }
    }
}
""")
    write("common/event_modifiers/llm_diplomacy_unlock.txt", """# Explicit modifier refreshes envoy counts in already-existing saves.
llm_unlock_envoy_pool = { diplomats = 100 global_tax_modifier = 100 }
llm_unlock_rebellious = { liberty_desire = 100000 }
""")
    write("common/opinion_modifiers/llm_diplomacy_unlock.txt", """# Applied only to a deliberately selected fixture pair, never globally.
llm_unlock_friendly = { opinion = 10000 max = 10000 }
llm_unlock_hostile = { opinion = -10000 min = -10000 }
""")
    write("common/new_diplomatic_actions/zzzz_llm_unlock_fixtures.txt", """# Fixture operations, excluded from diplomacy success counts.
llm_unlock_prepare_target = {
    category = relation
    require_acceptance = no
    is_visible = { ai = no }
    is_allowed = { always = yes }
    on_accept = {
        llm_unlock_prepare_pair = yes
        llm_unlock_clear_pair_opinion = yes
    }
    ai_will_do = { always = no }
}
llm_unlock_prepare_allied_target = {
    category = relation
    require_acceptance = no
    is_visible = { ai = no }
    is_allowed = { always = yes }
    on_accept = {
        llm_unlock_prepare_pair = yes
        llm_unlock_clear_pair_opinion = yes
        create_alliance = FROM
    }
    ai_will_do = { always = no }
}
llm_unlock_prepare_friendly_target = {
    category = relation
    require_acceptance = no
    is_visible = { ai = no }
    is_allowed = { always = yes }
    on_accept = {
        llm_unlock_prepare_pair = yes
        llm_unlock_clear_pair_opinion = yes
        add_opinion = { who = FROM modifier = llm_unlock_friendly }
        FROM = { add_opinion = { who = ROOT modifier = llm_unlock_friendly } }
    }
    ai_will_do = { always = no }
}
llm_unlock_prepare_hostile_target = {
    category = relation
    require_acceptance = no
    is_visible = { ai = no }
    is_allowed = { always = yes }
    on_accept = {
        llm_unlock_prepare_pair = yes
        llm_unlock_clear_pair_opinion = yes
        add_opinion = { who = FROM modifier = llm_unlock_hostile }
        FROM = { add_opinion = { who = ROOT modifier = llm_unlock_hostile } }
    }
    ai_will_do = { always = no }
}
llm_unlock_prepare_rebellious_target = {
    category = relation
    require_acceptance = no
    is_visible = { ai = no }
    is_allowed = { always = yes }
    on_accept = {
        llm_unlock_prepare_pair = yes
        llm_unlock_clear_pair_opinion = yes
        add_opinion = { who = FROM modifier = llm_unlock_friendly }
        FROM = {
            add_opinion = { who = ROOT modifier = llm_unlock_friendly }
            remove_country_modifier = llm_unlock_rebellious
            add_country_modifier = { name = llm_unlock_rebellious duration = -1 }
        }
    }
    ai_will_do = { always = no }
}
llm_unlock_prepare_favor_target = {
    category = relation
    require_acceptance = no
    is_visible = { ai = no }
    is_allowed = { always = yes }
    on_accept = {
        llm_unlock_prepare_pair = yes
        llm_unlock_clear_pair_opinion = yes
        create_alliance = FROM
        add_opinion = { who = FROM modifier = llm_unlock_friendly }
        FROM = { add_opinion = { who = ROOT modifier = llm_unlock_friendly } }
        add_trust = { who = FROM value = -50 mutual = yes }
    }
    ai_will_do = { always = no }
}
""")
    write("decisions/llm_diplomacy_unlock.txt", """country_decisions = {
    llm_unlock_refill = {
        potential = { ai = no }
        allow = { always = yes }
        effect = { llm_unlock_refill_country = yes }
        ai_will_do = { factor = 0 }
    }
}
""")
    write("localisation/llm_diplomacy_unlock_l_english.yml", """l_english:
 llm_unlock_acceptance:0 "Test mod acceptance"
 llm_unlock_refill_title:0 "TEST PREP: Refill diplomacy resources"
 llm_unlock_refill_desc:0 "Refill treasury, monarch power, prestige, stability, manpower and sailors. Not native dispatch evidence."
 llm_unlock_prepare_target_title:0 "TEST PREP: Refill both countries"
 llm_unlock_prepare_target_desc:0 "Refill both countries, favors, trust and spy network. Excluded from action success counts."
 llm_unlock_prepare_target_tooltip:0 "Prepare resources, favors, trust and spy network."
 llm_unlock_prepare_target_dialog:0 "Prepare the selected country pair."
 llm_unlock_prepare_allied_target_title:0 "TEST PREP: Ally and refill both countries"
 llm_unlock_prepare_allied_target_desc:0 "Direct fixture alliance and resources. Does not test the native alliance sender."
 llm_unlock_prepare_allied_target_tooltip:0 "Prepare an allied pair and resources."
 llm_unlock_prepare_allied_target_dialog:0 "Prepare an existing-alliance fixture."
 llm_unlock_prepare_friendly_target_title:0 "TEST PREP: Friendly pair"
 llm_unlock_prepare_friendly_target_desc:0 "Refill resources and maximize opinion in both directions. Fixture only."
 llm_unlock_prepare_friendly_target_tooltip:0 "Prepare resources and friendly opinion."
 llm_unlock_prepare_friendly_target_dialog:0 "Prepare a friendly pair."
 llm_unlock_prepare_hostile_target_title:0 "TEST PREP: Hostile pair"
 llm_unlock_prepare_hostile_target_desc:0 "Refill resources and minimize opinion in both directions. No war or relation cancellation."
 llm_unlock_prepare_hostile_target_tooltip:0 "Prepare resources and hostile opinion."
 llm_unlock_prepare_hostile_target_dialog:0 "Prepare a hostile pair."
 llm_unlock_friendly:0 "Diplomacy test friendly fixture"
 llm_unlock_hostile:0 "Diplomacy test hostile fixture"
 llm_unlock_prepare_rebellious_target_title:0 "TEST PREP: Rebellious target"
 llm_unlock_prepare_rebellious_target_desc:0 "Refill and raise target liberty desire. Existing subject relation is required separately. Excluded from action success counts."
 llm_unlock_prepare_rebellious_target_tooltip:0 "Prepare a friendly rebellious subject."
 llm_unlock_prepare_rebellious_target_dialog:0 "Prepare a friendly rebellious subject."
 llm_unlock_envoy_pool:0 "Diplomacy test envoy pool"
 llm_unlock_rebellious:0 "Diplomacy test rebellious subject"
 llm_unlock_prepare_favor_target_title:0 "TEST PREP: Favor pair"
 llm_unlock_prepare_favor_target_desc:0 "Direct fixture alliance, friendly opinion, resources, 100 favors and 50 trust. Tax boost requires a monthly tick. Excluded from action success counts."
 llm_unlock_prepare_favor_target_tooltip:0 "Prepare an allied favor pair with 50 trust."
 llm_unlock_prepare_favor_target_dialog:0 "Prepare an allied favor pair with 50 trust."
""", bom=True)
    write("descriptor.mod", 'name="LLM Diplomacy Unlock Test (1.37.5)"\nversion="1.0.0"\nsupported_version="1.37.*"\ntags={ "Utilities" }\n')

    # Verify exact source identity against the already pinned catalog where present.
    catalog = json.loads((ROOT / "bridge/diplomacy_catalog.json").read_text(encoding="utf-8-sig"))
    for source in catalog["sources"]:
        if source["path"] in sources and source["sha256"].lower() != sources[source["path"]]["sha256"]:
            raise ValueError(f"not the catalog's exact 1.37.5 source: {source['path']}")
    manifest = {
        "schema_version": 1, "kind": "disposable_diplomacy_script_unlock_mod",
        "game_version": "1.37.5", "exe_sha256": EXE_SHA,
        "runtime_verified": False, "all_native_conditions_bypassed": False,
        "native_senders_modified": False, "ordinary_action_effects_preserved": True,
        "special_subject_fallback_disabled": True,
        "counts": counts, "sources": sources, "define_overrides": overrides,
        "preserved_effects": effects,
        "files": {k: {"sha256": digest(v), "bytes": len(v)} for k, v in sorted(outputs.items())},
        "fixture_actions_excluded_from_success": ["llm_unlock_prepare_target", "llm_unlock_prepare_allied_target",
                                                  "llm_unlock_prepare_friendly_target", "llm_unlock_prepare_hostile_target", "llm_unlock_prepare_rebellious_target", "llm_unlock_prepare_favor_target"],
        "limitations": [
            "Native hidden legality, DLC entitlements, actors' roles and structural object checks still apply.",
            "Cancellation requires an existing relation or task; war actions require an actual suitable war.",
            "Province, fleet, rebel, heir and third-party arguments must identify actual suitable objects.",
            "HRE, Curia, great power and shogunate role context is not manufactured by this mod.",
            "Faction, government-power and mission-specific effect costs inside on_accept remain unchanged.",
            "Fixture preparation is not native diplomatic dispatch evidence.",
            "DIPLOMAT_COOLDOWN_TIME=-1 is a statically supported same-date test candidate, not runtime-verified; existing saved deadlines persist.",
            "At least 100 additional base diplomats, not numerical infinity; historical pool modifiers may stack.",
            "Opinion is not forced globally: friendly, hostile and neutral fixtures are separate to avoid disabling negative-opinion or improvement actions.",
        ],
        "references": ["https://www.eu4cn.com/wiki/Scripted_function", "https://www.eu4cn.com/wiki/Defines"],
    }
    manifest_path = destination / "unlock-manifest.json"
    manifest_data = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    different = manifest_path.exists() and manifest_path.read_bytes() != manifest_data
    for rel, data in outputs.items():
        target = destination / rel
        if target.exists() and target.read_bytes() != data:
            different = True
    if different:
        if not replace:
            raise FileExistsError("generated mod differs; --replace creates a backup before rebuilding")
        backup = ROOT / "work/backup" / ("diplomacy-unlock-build-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        shutil.copytree(destination, backup)
    for rel, data in outputs.items():
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    manifest_path.write_bytes(manifest_data)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--output", type=Path, default=ROOT / "mod" / NAME)
    parser.add_argument("--replace", action="store_true", help="back up differing generated bytes before rebuilding")
    args = parser.parse_args()
    manifest = build(args.base, args.output, replace=args.replace)
    print(json.dumps({"path": str(args.output), "counts": manifest["counts"],
                      "runtime_verified": False, "all_native_conditions_bypassed": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
