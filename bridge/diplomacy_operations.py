"""Source contracts and four-phase discovery for the existing diplomacy owner.

These functions use cached API metadata and pure codecs. They perform no game
reads, native calls, publication, or session construction.
"""
from __future__ import annotations

from .diplomacy_effect_profiles import profile_catalog


def _parameters(action, route, caps):
    if route == "typed_peace":
        return ["actor", "target", "direction", "terms"]
    if route == "typed_subject":
        import subject_codec as codec
        extra = []
        if action in codec.TOGGLES:
            extra = ["enabled"]
        elif action == "subject.set_military_focus":
            extra = ["focus"]
        elif action == codec.TRIBUTE_ACTION:
            extra = ["tribute"]
        elif action in codec.RELEASE_ACTIONS:
            extra = ["play_as_released"]
        elif action == codec.CUSTOMIZE_ACTION:
            extra = ["name", "adjective"]
        elif action in codec.TYPE_ACTIONS:
            extra = ["subject_type"]
        elif action in codec.PROVINCE_ACTIONS:
            extra = ["province_id"]
        elif action == codec.COLONIAL_WAR_ACTION:
            extra = ["enemy"]
        elif action == codec.ISOLATION_ACTION:
            extra = ["direction"]
        return ["actor", "target", *extra]
    typed = caps.get(route)
    if isinstance(typed, dict):
        return typed.get("parameter_fields_by_action", {}).get(
            action, typed.get("parameter_fields", typed.get("parameters", [])))
    return ["actor", "target", *caps.get("parameterized_actions", {}).get(action, [])]


def _conditions(action, route):
    conditions = ["current native diplomatic legality and action costs"]
    if action in ("offer_loan", "give_subsidies", "send_gift", "take_on_debt"):
        conditions += ["current treasury, income, debt and requested amount/duration"]
    if action in ("sell_province", "threaten_war", "return_core_favor"):
        conditions += ["current province ownership, core/claim and recipient eligibility"]
    if action in ("sell_ships", "offer_condottieri"):
        conditions += ["current actor-owned unit identity, location and transferable composition"]
    if action in ("request_maps", "steal_maps"):
        conditions += ["current map region, exploration difference and action resource costs"]
    if action in ("knowledge_sharing", "ask_knowledge_sharing", "subject.knowledge_sharing"):
        conditions += ["institution knowledge difference, current sharing relation and income cost"]
    if action in ("build_spy_network", "counterespionage", "fabricate_claim", "fabricate_state_claim",
                  "support_rebels", "sabotage_recruitment", "sabotage_reputation", "sow_discontent",
                  "corrupt_officials", "agitate_for_liberty", "infiltrate_administration", "steal_maps"):
        conditions += ["actual spy network, diplomat, technology and target eligibility"]
    if action in ("trade_favors_for_sailors", "break_alliance_favor", "return_core_favor", "trade_favors_for_war_prep"):
        conditions += ["current favor balance, bilateral relation and third-country/province conditions"]
    if route == "typed_war_context":
        conditions += ["unique existing war selected by attacker/defender leaders and optional started_date",
                       "current alliance, war side and participation rules"]
    if route == "typed_subject" and action != "create_vassal":
        conditions += ["actual overlord/subject relation and current subject-type ability"]
    if "colon" in action:
        conditions += ["actual colonial country/region and colonial subject type"]
    if "tribut" in action:
        conditions += ["current tributary relationship, eligibility and tribute state"]
    if action in ("call_crusade", "excommunicate", "lift_excommunication"):
        conditions += ["actor is current Curia controller; target meets Catholic action conditions"]
    if any(word in action for word in ("imperial", "reichskrieg", "hre", "free_city", "freecity", "unlawful", "religious_unity")):
        conditions += ["current HRE membership, emperor powers, reforms and religious rules"]
    if action in ("influence_nation", "intervene_in_war", "break_alliance", "take_on_debt"):
        conditions += ["current great-power eligibility where required by the native action"]
    if action in ("annex_vassal", "integrate", "integrate_union", "integrate_personal_union"):
        conditions += ["current dependency duration, relations and integration eligibility; observe progress over time"]
    return conditions


def catalog(api, *, action=None, category=None):
    caps = api.capabilities()
    profiles = {row["action"]: row for row in profile_catalog()}
    rows = []
    for source in api.list_actions(category=category, include_excluded=False):
        name = source["action"]
        if action is not None and name != action:
            continue
        route = source.get("route", "ordinary_tag")
        candidates = []
        if route == "typed_war_context":
            candidates.append("wars")
        if route == "typed_sell_ships":
            candidates.append("fleets")
        if route == "typed_condottieri":
            candidates.append("units")
        if route == "typed_rebels":
            candidates.append("rebel_factions")
        fields = _parameters(name, route, caps)
        if "province_id" in fields:
            candidates.append("provinces")
        if name in ("call_crusade", "excommunicate", "lift_excommunication"):
            candidates.append("curia_controller")
        profile = profiles.get(name)
        row = dict(source, route=route, parameter_fields=fields,
                   parameter_details=caps.get(route, {}),
                   conditions=_conditions(name, route), candidates=candidates,
                   native_preview=name == "offer_peace" or route == "ordinary_tag",
                   effect_profile=profile)
        row["interfaces"] = {"query": "/v1/diplomacy/query",
                             "execute": "/v1/production/requests",
                             "response": "/v1/requests/{request_id}/response",
                             "effects": "/v1/requests/{request_id}/effects"}
        if profile is None and name == "event.choose_governor_option":
            row["effect_profile_note"] = "Event option execution; selected-effect evidence is handled by the subject.replace_governor pending-election profile."
        rows.append(row)
    if action is not None and not rows:
        raise ValueError("Unknown action: " + action)
    return {"schema": "EU4DIPLOMACYOPERATIONS/1", "actions": rows,
            "action_count": len(rows), "query_scope": "source_contract",
            "request_fields": ["request_id", "action", "parameters"]}


def query(api, request):
    normalized = api.validate(request)
    contract = catalog(api, action=normalized["action"])["actions"][0]
    return {"schema": "EU4DIPLOMACYQUERY/1", "request": normalized,
            "parameters_valid": True, "contract": contract,
            "availability": "evaluate_current_native_conditions", "requests_published": 0}


def response(native):
    """Keep generated decisions, pending delivery and application in one DTO."""
    from eu4harness.v32_diplomacy_outcome_20261024 import generated_decisions
    summary = native.get("observation_summary", {})
    return {"schema": "EU4DIPLOMACYRESPONSE/1",
            "request_id": native.get("request_id"), "request": native.get("request"),
            "status": native.get("status"), "identity": native.get("identity"),
            "sequence": native.get("sequence"),
            "generated_decisions": generated_decisions(summary),
            "acceptance": summary.get("acceptance"),
            "effect_completion": summary.get("effect_completion"),
            "stages": [{key: factory.get(key) for key in (
                "slot_index", "generated_reply", "origin_parent_slot", "pending",
                "reply", "generated_send", "effect", "payload")}
                for factory in summary.get("factories", [])],
            "evidence": native.get("observation_evidence"),
            "error": native.get("error"), "automatic_retry": False}
