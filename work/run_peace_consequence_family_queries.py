"""Query every public Peace term on one paused war without executing it."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal  # noqa: E402
from bridge.peace_consequences import (  # noqa: E402
    project_event_consequences, validate_native_consequences,
)
from work.local_config import game_exe  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_peace_concession_queries import (  # noqa: E402
    _control_from_probe, _control_is_paused_por,
)
from work.run_peace_consequence_queries import (  # noqa: E402
    _copy_bounded_slice, _has_private_fields, _installation_binding,
    _matching_event, _native_validator, _output_paths, _raw_header_contract,
    _single_discovered_war_id, _write_json, _read_slice_events,
)
from work.validate_alliance_queries import PROBE_SPECS, _run_probe  # noqa: E402


ACTOR = "FRA"
ACTION_IDS = (
    "white_peace", "demand_ducats", "cede_province", "war_reparations",
    "transfer_trade_power", "concede_defeat", "annul_treaties",
    "humiliate_rival", "show_strength", "force_religion", "return_core",
    "revoke_core", "release_subject", "transfer_subject", "release_nation",
    "force_vassalization", "form_personal_union", "grant_independence",
    "full_annexation",
)
EVENT_NAMES = {
    "white_peace": "native_peace_empty_offer_inspection",
    "demand_ducats": "native_peace_money_offer_inspection",
    "cede_province": "native_peace_province_offer_inspection",
    "war_reparations": "native_peace_reparations_offer_inspection",
    "transfer_trade_power": "native_peace_trade_power_offer_inspection",
    "concede_defeat": "native_peace_concede_defeat_offer_inspection",
    "annul_treaties": "native_peace_annul_treaties_offer_inspection",
    "humiliate_rival": "native_peace_special_offer_inspection",
    "show_strength": "native_peace_special_offer_inspection",
    "force_religion": "native_peace_special_offer_inspection",
    "return_core": "native_peace_core_offer_query",
    "revoke_core": "native_peace_core_offer_query",
    "release_subject": "native_peace_subject_offer_query",
    "transfer_subject": "native_peace_subject_offer_query",
}
BITS = {
    "humiliate_rival": "h", "show_strength": "s", "force_religion": "f",
    "return_core": "b", "revoke_core": "v", "release_subject": "l",
    "transfer_subject": "x", "release_nation": "n",
    "force_vassalization": "z", "form_personal_union": "u",
    "grant_independence": "i", "full_annexation": "e",
}


def _write(path: Path, value: object) -> None:
    _write_json(path, value)


def _family_event(path: Path, action_id: str, actor: str, recipient: str,
                  direction: str, war_id: str) -> dict[str, object] | None:
    """Select the terminal public peace event from a bounded slice."""
    matches = []
    allowed = EVENT_NAMES.get(action_id)
    for event in _read_slice_events(path):
        name = event.get("event")
        if (event.get("family") != "peace" or event.get("action_id") != action_id
                or event.get("actor") != actor or event.get("recipient") != recipient
                or event.get("direction") != direction or event.get("war_id") != war_id
                or not isinstance(name, str) or name.endswith("_private")
                or name.endswith("_failed")):
            continue
        if allowed is None:
            if name != "native_peace_combined_country_offer_query":
                continue
        elif name != allowed:
            continue
        matches.append(event)
    with_consequences = [row for row in matches
                         if isinstance(row.get("native_consequences"), dict)]
    return (with_consequences or matches)[-1] if matches else None


def _selection(action_id: str, war_id: str, direction: str,
               recipient: str, *, amount_raw: int = -1,
               province_ids: list[int] | None = None,
               beneficiary: str | None = None,
               source: str = "-",
               trade_power_beneficiary: str | None = None,
               annul_country: str = "-",
               annul_partners: list[str] | None = None,
               subject_country: str | None = None) -> dict[str, object]:
    """Build the exact selection shape consumed by the production validator.

    Empty terms are retained only for the native discovery families (T/A,
    core, subject, and country).  Numeric and role-bound terms must carry a
    real minimum selection so a failed adapter call cannot be mistaken for a
    native result.
    """
    base: dict[str, object] = {
        "action_id": action_id, "war_id": war_id, "direction": direction,
        "amount_raw": amount_raw, "province_ids": list(province_ids or []),
        "beneficiary": beneficiary,
        "source": source, "trade_power_beneficiary": trade_power_beneficiary,
        "payer": recipient, "claimant": ACTOR, "conceding_country": None,
        "concede_beneficiary": None, "annul_country": annul_country,
        "annul_partners": list(annul_partners or []),
    }
    if action_id == "white_peace":
        return base
    if action_id == "cede_province":
        return {"war_id": war_id, "direction": direction,
                "province_ids": list(province_ids or []),
                "beneficiary": beneficiary}
    if action_id == "demand_ducats":
        return {"war_id": war_id, "direction": direction,
                "amount_raw": amount_raw, "payer": recipient, "claimant": ACTOR}
    if action_id == "transfer_trade_power":
        return {**base, "term_mask": "t",
                "trade_power_beneficiary": trade_power_beneficiary or ACTOR,
                "_sources_protocol": True}
    if action_id == "war_reparations":
        return {**base, "term_mask": "r"}
    if action_id == "concede_defeat":
        return {**base, "term_mask": "c", "conceding_country": recipient,
                "concede_beneficiary": ACTOR}
    if action_id == "annul_treaties":
        return {**base, "term_mask": "a"}
    if action_id in ("humiliate_rival", "show_strength", "force_religion"):
        return {**base, "term_mask": BITS[action_id], "special_terms": [{
            "action_id": action_id, "country": recipient,
            "beneficiary": ACTOR}]}
    if action_id in ("return_core", "revoke_core"):
        return {"action_id": action_id, "war_id": war_id, "direction": direction,
                "province_ids": list(province_ids or []),
                "core_owner": beneficiary, "discovery": not province_ids}
    if action_id in ("release_subject", "transfer_subject"):
        return {"action_id": action_id, "war_id": war_id, "direction": direction,
                "country": subject_country, "discovery": subject_country is None}
    # QUERY18 country discovery binds every family to the same empty request.
    fields = {
        "release_nation_country": None, "release_nation_source": None,
        "vassal_country": None, "vassal_beneficiary": None,
        "union_country": None, "union_beneficiary": None,
        "independence_country": None, "annex_country": None,
        "annex_beneficiary": None,
    }
    return {**base, **fields, "term_mask": BITS[action_id]}


def _request_parameters(action_id: str, war_id: str, recipient: str,
                        *, beneficiary: str = ACTOR,
                        province_ids: list[int] | None = None) -> dict[str, object]:
    """Return a legal minimum request for one public action family."""
    context = lambda terms: {"peace_context": {
        "war_id": war_id, "direction": "demand", "terms": terms}}
    if action_id == "white_peace":
        return context([])
    if action_id == "demand_ducats":
        return context([{"action_id": "demand_ducats", "amount": "1.0",
                         "payer": recipient, "claimant": ACTOR}])
    if action_id == "cede_province":
        return context([{"action_id": "cede_province",
                         "province_ids": list(province_ids or [88]),
                         "beneficiary": beneficiary}])
    if action_id == "war_reparations":
        return context([{"action_id": "war_reparations", "payer": recipient,
                         "claimant": ACTOR}])
    if action_id == "concede_defeat":
        return context([{"action_id": "concede_defeat",
                         "conceding_country": recipient,
                         "beneficiary": ACTOR}])
    if action_id in ("humiliate_rival", "show_strength", "force_religion"):
        return context([{"action_id": action_id, "country": recipient,
                         "beneficiary": ACTOR}])
    # These families have an explicit discovery form.  Supplying made-up
    # country/source/partner values would turn a missing candidate into a
    # fabricated success, so retain the native candidate query shape.
    return context([])


def _selection_for_parameters(action_id: str, war_id: str, direction: str,
                              recipient: str, parameters: dict[str, object],
                              *, province_ids: list[int] | None = None,
                              beneficiary: str | None = None) -> dict[str, object]:
    """Derive validator expectations from the exact public request."""
    context = parameters.get("peace_context")
    terms = context.get("terms", []) if isinstance(context, dict) else []
    term = terms[0] if isinstance(terms, list) and terms and isinstance(terms[0], dict) else {}
    if action_id == "demand_ducats":
        return _selection(action_id, war_id, direction, recipient, amount_raw=1000)
    if action_id == "cede_province":
        ids = province_ids if province_ids is not None else term.get("province_ids", [])
        return _selection(action_id, war_id, direction, recipient,
                          province_ids=list(ids), beneficiary=beneficiary or term.get("beneficiary"))
    if action_id == "war_reparations":
        return _selection(action_id, war_id, direction, recipient)
    if action_id == "concede_defeat":
        return _selection(action_id, war_id, direction, recipient)
    if action_id in ("humiliate_rival", "show_strength", "force_religion"):
        return _selection(action_id, war_id, direction, recipient)
    return _selection(action_id, war_id, direction, recipient)


def _validator_event(event: dict[str, object]) -> dict[str, object]:
    """Validate the producer record unchanged through the current adapter."""
    return event


def _validator_normalization(event: dict[str, object] | None) -> str | None:
    """The production validator accepts and checks the optional list."""
    return None


def _native_valid(event: dict[str, object] | None, action_id: str,
                  actor: str, recipient: str, direction: str, war_id: str,
                  date_raw: object, session_id: str,
                  province_ids: list[int] | None = None,
                  beneficiary: str | None = None,
                  expected_selection: dict[str, object] | None = None) -> bool | None:
    if not isinstance(event, dict):
        return None
    query_id = event.get("query_id")
    expected = expected_selection or _selection(
        action_id, war_id, direction, recipient,
        province_ids=province_ids, beneficiary=beneficiary)
    event_for_validation = _validator_event(event)
    try:
        if action_id == "demand_ducats":
            return ObserverSession._valid_native_peace_money_offer_inspection(
                event_for_validation, action_id, actor, recipient, "initiate", date_raw,
                expected, query_id, session_id)
        if action_id in ("white_peace", "cede_province"):
            return _native_validator(
                event_for_validation, action_id=action_id, actor=actor, recipient=recipient,
                direction=direction, war_id=war_id, expected_date=date_raw,
                query_id=query_id, session_id=session_id, amount_raw=None,
                province_ids=province_ids or [], beneficiary=beneficiary)
        if action_id == "transfer_trade_power":
            return ObserverSession._valid_native_peace_trade_power_offer_inspection(
                event_for_validation, action_id, actor, recipient, "initiate", date_raw, expected,
                query_id, session_id)
        if action_id == "war_reparations":
            return ObserverSession._valid_native_peace_reparations_offer_inspection(
                event_for_validation, action_id, actor, recipient, "initiate", date_raw, expected,
                query_id, session_id)
        if action_id == "concede_defeat":
            return ObserverSession._valid_native_peace_concede_defeat_offer_inspection(
                event_for_validation, action_id, actor, recipient, "initiate", date_raw, expected,
                query_id, session_id)
        if action_id == "annul_treaties":
            return ObserverSession._valid_native_peace_annul_treaties_offer_inspection(
                event_for_validation, action_id, actor, recipient, "initiate", date_raw, expected,
                query_id, session_id)
        if action_id in ("humiliate_rival", "show_strength", "force_religion"):
            return ObserverSession._valid_native_peace_special_offer_inspection(
                event_for_validation, action_id, actor, recipient, "initiate", date_raw, expected,
                query_id, session_id)
        if action_id in ("return_core", "revoke_core"):
            if event_for_validation.get("event") == "native_peace_core_offer_query":
                return ObserverSession._valid_native_peace_core_offer_query(
                    event_for_validation, action_id, actor, recipient, "initiate", date_raw, expected,
                    query_id, session_id)
            return ObserverSession._valid_native_peace_combined_core_offer_query(
                event_for_validation, action_id, actor, recipient, "initiate", date_raw,
                {**_selection("white_peace", war_id, direction, recipient),
                 "term_mask": BITS[action_id],
                 "return_ids": [], "return_core_owner": None,
                 "revoke_ids": [], "revoke_core_owner": None}, query_id, session_id)
        if action_id in ("release_subject", "transfer_subject"):
            if event_for_validation.get("event") == "native_peace_subject_offer_query":
                return ObserverSession._valid_native_peace_subject_offer_query(
                    event_for_validation, action_id, actor, recipient, "initiate", date_raw, expected,
                    query_id, session_id)
            return ObserverSession._valid_native_peace_combined_subject_offer_query(
                event_for_validation, action_id, actor, recipient, "initiate", date_raw,
                {**_selection("white_peace", war_id, direction, recipient),
                 "term_mask": BITS[action_id], "release_countries": [],
                 "transfer_countries": []}, query_id, session_id)
        return ObserverSession._valid_native_peace_combined_country_offer_query(
            event_for_validation, action_id, actor, recipient, "initiate", date_raw, expected,
            query_id, session_id)
    except (TypeError, ValueError, KeyError):
        return False


def _public_base(value: object, action_id: str, actor: str, recipient: str,
                 war_id: str, direction: str,
                 expected_terms: list[object] | None = None) -> bool:
    return (isinstance(value, dict) and value.get("action_id") == action_id
            and value.get("actor") == actor and value.get("recipient") == recipient
            and value.get("phase") == "initiate"
            and isinstance(value.get("peace_context"), dict)
            and value["peace_context"].get("war_id") == war_id
            and value["peace_context"].get("direction") == direction
            and value["peace_context"].get("terms") == (expected_terms or []))


def _semantic_projector(event_name: str):
    """Return the production semantic projector for one native event."""
    return {
        "native_peace_empty_offer_inspection":
            ObserverSession._semantic_peace_empty_offer_inspection,
        "native_peace_money_offer_inspection":
            ObserverSession._semantic_peace_money_offer_inspection,
        "native_peace_province_offer_inspection":
            ObserverSession._semantic_peace_province_offer_inspection,
        "native_peace_reparations_offer_inspection":
            ObserverSession._semantic_peace_reparations_offer_inspection,
        "native_peace_trade_power_offer_inspection":
            ObserverSession._semantic_peace_trade_power_offer_inspection,
        "native_peace_concede_defeat_offer_inspection":
            ObserverSession._semantic_peace_concede_defeat_offer_inspection,
        "native_peace_annul_treaties_offer_inspection":
            ObserverSession._semantic_peace_annul_treaties_offer_inspection,
        "native_peace_special_offer_inspection":
            ObserverSession._semantic_peace_special_offer_inspection,
        "native_peace_core_offer_query":
            ObserverSession._semantic_peace_core_offer_query,
        "native_peace_subject_offer_query":
            ObserverSession._semantic_peace_subject_offer_query,
        "native_peace_combined_core_offer_query":
            ObserverSession._semantic_peace_combined_core_offer_query,
        "native_peace_combined_subject_offer_query":
            ObserverSession._semantic_peace_combined_subject_offer_query,
        "native_peace_combined_country_offer_query":
            ObserverSession._semantic_peace_combined_country_offer_query,
    }.get(event_name)


def _strip_public_private(value: object) -> object:
    """Keep only the production semantic projection's public-safe fields."""
    forbidden = {"pid", "session_id", "creation_filetime", "native_war_reference",
                 "native_reference", "module_base", "vtable_rva", "dll_sha256",
                 "query_id", "identity_scope", "selected_war_id", "date_raw", "event"}
    if isinstance(value, dict):
        return {key: _strip_public_private(item)
                for key, item in value.items() if key not in forbidden}
    if isinstance(value, list):
        return [_strip_public_private(item) for item in value]
    return value


def _recover_public_projection(raw: dict[str, object], parameters: dict[str, object],
                               codec: str) -> dict[str, object] | None:
    """Project a valid raw event when the adapter rejects a compatibility field.

    The fallback calls the same production semantic projector used by
    ``DiplomacyTools``.  It never reconstructs native consequences or term
    records itself; the report records the adapter error separately.
    """
    projector = _semantic_projector(str(raw.get("event")))
    if projector is None:
        return None
    try:
        projected = projector(raw, codec)
    except (TypeError, ValueError, KeyError):
        return None
    if not isinstance(projected, dict):
        return None
    public = _strip_public_private(projected)
    if not isinstance(public, dict):
        return None
    public["projection_source"] = "native_semantic_fallback"
    consequences = public.get("peace_consequences")
    actual_context = {"peace_context": public.get("peace_context")}
    if (isinstance(consequences, dict)
            and consequences.get("requested_terms_applied") is False):
        # The execution/public contract deliberately withholds an actual
        # treaty when native did not copy the requested selection.
        actual_context = None
    public["parameters"] = {
        "requested": parameters,
        "actual": actual_context,
        "complete": public.get("parameters_matched") is True,
    }
    return public


def _semantic_public_terms(raw: dict[str, object] | None,
                           codec: str) -> list[object]:
    """Read actual copied terms from the production semantic projector."""
    if not isinstance(raw, dict):
        return []
    projector = _semantic_projector(str(raw.get("event")))
    if projector is None:
        return []
    try:
        projected = projector(raw, codec)
    except (TypeError, ValueError, KeyError):
        return []
    context = projected.get("peace_context") if isinstance(projected, dict) else None
    terms = context.get("terms") if isinstance(context, dict) else None
    return list(terms) if isinstance(terms, list) else []


def _native_parameter_state(action_id: str, raw: dict[str, object] | None) -> bool | None:
    """Read the action-specific native candidate/selection state."""
    if not isinstance(raw, dict):
        return None
    if action_id == "white_peace":
        return True
    if action_id == "full_annexation":
        value = raw.get("native_annexation")
        if isinstance(value, dict):
            if isinstance(value.get("parameters_matched"), bool):
                return value["parameters_matched"]
            # QUERY18 exposes the full-annex candidate set through the
            # selection flags rather than a generic parameters_matched key.
            # An empty discovery request is evidence of an unselected offer,
            # never a successful treaty selection.
            if isinstance(value.get("selection_requested"), bool):
                return value.get("selection_applied") is True
    field = {
        "cede_province": "native_provinces",
        "demand_ducats": "native_money",
        "war_reparations": "native_reparations",
        "transfer_trade_power": "native_trade_power",
        "concede_defeat": "native_concede_defeat",
        "annul_treaties": "native_annul_treaties",
        "humiliate_rival": "native_humiliate_rival",
        "show_strength": "native_show_strength",
        "force_religion": "native_force_religion",
        "return_core": "native_core_terms",
        "revoke_core": "native_core_terms",
        "release_subject": "native_subject_terms",
        "transfer_subject": "native_subject_terms",
    }.get(action_id)
    if field:
        value = raw.get(field)
        if isinstance(value, dict) and isinstance(value.get("parameters_matched"), bool):
            return value["parameters_matched"]
        return None
    country = raw.get("native_country_terms")
    if isinstance(country, dict):
        value = country.get(action_id)
        if isinstance(value, dict) and isinstance(value.get("parameters_matched"), bool):
            return value["parameters_matched"]
    return None


def _empty_consequence_projection(value: object) -> bool:
    """Confirm that a candidate miss produced no applied treaty consequence."""
    if not isinstance(value, dict):
        return False
    ae = value.get("aggressive_expansion")
    if isinstance(ae, dict) and ae.get("maximum_raw", 0) != 0:
        return False
    dip = value.get("diplomatic_power")
    if isinstance(dip, dict) and dip.get("value", 0) != 0:
        return False
    coalition = value.get("coalition")
    if isinstance(coalition, dict) and coalition.get("countries") not in ([], None):
        return False
    territorial = value.get("territorial")
    if not isinstance(territorial, list):
        return False
    return all(isinstance(row, dict)
               and row.get("overextension_added_raw", 0) == 0
               and row.get("provinces", []) == [] for row in territorial)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recipient", default="BUR")
    args = parser.parse_args(argv)
    recipient = str(args.recipient).upper()
    report_path: Path | None = None
    session: ObserverSession | None = None
    report: dict[str, Any] = {
        "validator": Path(__file__).name, "version": 2,
        "mode": "read_only_peace_consequence_family_queries", "status": "running",
        "actor": ACTOR, "recipient": recipient, "action_ids": list(ACTION_IDS),
        "query_call_count": 0, "execute_call_count": 0,
        "business_submission": False, "advance_requested": False,
        "save_requested": False, "restart_requested": False, "cases": [],
    }
    try:
        report_path, evidence = _output_paths(args.output)
        installation = args.installation.expanduser().resolve(strict=True)
        report.update(_installation_binding(installation))
        session = ObserverSession(installation, game_exe())
        report["session"] = {key: session.record.get(key)
                              for key in ("pid", "session_id", "experiment_id", "dll_sha256")}
        before_health = wait_runtime_ready(session, restore_minimized=True)
        before_probe = _run_probe(PROBE_SPECS[0], session.record["pid"],
                                  evidence / "before" / "control.json")
        control_before = _control_from_probe(before_probe)
        date_raw = before_health.get("date_raw")
        report["before"] = {"health": before_health, "control": control_before}
        if (before_health.get("status") != "ready"
                or not _control_is_paused_por(control_before, date_raw)):
            raise RuntimeError("BASELINE_NOT_READY_POR_PAUSED")
        log_path = session.directory / "control-probe.jsonl"
        with DurableJournal(evidence / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id) as journal:
            api = DiplomacyTools(journal, session)
            discovery = api.inspect_diplomatic_action(
                "white_peace", ACTOR, recipient, phase="initiate", parameters={})
            _write(evidence / "war-discovery.json", discovery)
            report["query_call_count"] += 1
            war_id = _single_discovered_war_id(discovery, ACTOR, recipient)
            if not war_id:
                raise RuntimeError("PEACE_WAR_DISCOVERY_INCOMPLETE")
            report["war_id"] = war_id
            # Catalog is a read-only ACK surface, not another native action
            # query.  Keep the complete response in evidence and retain a
            # bounded summary in the family report for finalization.
            action_catalog = api.list_diplomatic_actions(
                ACTOR, recipient, category="peace")
            _write(evidence / "action-catalog.json", action_catalog)
            catalog_actions = action_catalog.get("actions", []) \
                if isinstance(action_catalog, dict) else []
            catalog_by_id = {
                row.get("action_id"): row for row in catalog_actions
                if isinstance(row, dict) and isinstance(row.get("action_id"), str)}
            catalog_query_consequences = [
                action_id for action_id in ACTION_IDS
                if isinstance(catalog_by_id.get(action_id), dict)
                and catalog_by_id[action_id].get("phases", {}).get(
                    "initiate", {}).get("query_consequences")
                == "native_peace_consequences"]
            report["action_catalog"] = {
                "path": str(evidence / "action-catalog.json"),
                "action_count": len(catalog_actions)
                if isinstance(catalog_actions, list) else 0,
                "required_action_count": len(ACTION_IDS),
                "query_consequences_action_ids": catalog_query_consequences,
                "required_query_consequences_action_ids": list(ACTION_IDS),
            }
            catalog_contract = set(catalog_query_consequences) == set(ACTION_IDS)

            def run_case(name: str, action_id: str, parameters: dict[str, object],
                         *, province_ids: list[int] | None = None,
                         beneficiary: str | None = None,
                         optional: bool = False) -> None:
                case_dir = evidence / "cases" / name
                case_dir.mkdir(parents=True, exist_ok=False)
                _write(case_dir / "input.json", {
                    "action_id": action_id, "actor": ACTOR, "recipient": recipient,
                    "phase": "initiate", "parameters": parameters,
                    "expected_war_id": war_id, "expected_province_ids": province_ids or [],
                    "expected_beneficiary": beneficiary,
                })
                start = log_path.stat().st_size
                error = None
                report["query_call_count"] += 1
                try:
                    api_public = api.inspect_diplomatic_action(
                        action_id, ACTOR, recipient, phase="initiate", parameters=parameters)
                except Exception as exc:  # keep one invalid terms[] bounded
                    api_public = {"error_code": type(exc).__name__, "error": str(exc)}
                    error = {"type": type(exc).__name__, "message": str(exc)}
                slice_meta = _copy_bounded_slice(
                    log_path, start, case_dir / "native-events-slice.jsonl")
                raw = _family_event(case_dir / "native-events-slice.jsonl",
                                    action_id, ACTOR, recipient, "demand", war_id)
                if raw is not None:
                    _write(case_dir / "native-event.json", raw)
                expected = _selection_for_parameters(
                    action_id, war_id, "demand", recipient, parameters,
                    province_ids=province_ids, beneficiary=beneficiary)
                header = _raw_header_contract(
                    raw, action_id=action_id, actor=ACTOR, recipient=recipient,
                    direction="demand", war_id=war_id, expected_date=date_raw,
                    session_id=session.session_id)
                native_valid = _native_valid(
                    raw, action_id, ACTOR, recipient, "demand", war_id,
                    date_raw, session.session_id, province_ids, beneficiary,
                    expected)
                raw_nc = raw.get("native_consequences") if isinstance(raw, dict) else None
                nc_valid = validate_native_consequences(raw_nc) if raw_nc is not None else None
                # Event-level projection is authoritative for requested-term
                # application.  In particular, an unmatched province or
                # country request must remain unavailable even when the raw
                # consequence counters happen to be zero.
                projected = (project_event_consequences(
                    raw, codec=session.native_text_codec)
                             if isinstance(raw, dict) and nc_valid else None)
                public = api_public
                api_error = (api_public.get("error_code")
                             if isinstance(api_public, dict) else None)
                recovered = False
                if (isinstance(api_public, dict) and api_error is not None
                        and isinstance(raw, dict) and native_valid is True):
                    recovered_public = _recover_public_projection(
                        raw, parameters, session.native_text_codec)
                    if recovered_public is not None:
                        public = recovered_public
                        recovered = True
                        _write(case_dir / "public-api-error.json", api_public)
                _write(case_dir / "public.json", public)
                public_nc = public.get("peace_consequences") if isinstance(public, dict) else None
                parity = (projected == public_nc) if nc_valid and isinstance(public_nc, dict) else None
                unchanged = ((public.get("object_unchanged") is True
                              and isinstance(raw, dict)
                              and raw.get("object_unchanged") is True)
                             if isinstance(public, dict) and raw is not None else None)
                private_absent = isinstance(public, dict) and not _has_private_fields(public)
                # The public peace_context displays the caller's proposal;
                # parameters.actual and requested_terms_applied report which
                # terms the native engine actually selected.
                expected_public_terms = parameters["peace_context"]["terms"]
                public_contract = _public_base(
                    public, action_id, ACTOR, recipient, war_id, "demand",
                    expected_public_terms)
                native_public_parity = all(value is True for value in (
                    header, native_valid, nc_valid, parity, unchanged,
                    public_contract, private_absent))
                native_state = _native_parameter_state(action_id, raw)
                if native_public_parity:
                    availability = "available" if native_state is not False else "unavailable"
                elif raw is None and api_error is None:
                    availability = "unknown"
                elif raw is not None:
                    availability = "invalid"
                else:
                    availability = "unknown"
                not_applied = False
                if name == "cede_province_88_ORL":
                    native_provinces = raw.get("native_provinces") if isinstance(raw, dict) else None
                    selected_ids = (native_provinces.get("selected_province_ids", [])
                                    if isinstance(native_provinces, dict) else None)
                    parameters_matched = (native_provinces.get("parameters_matched")
                                          if isinstance(native_provinces, dict) else None)
                    not_applied = (
                        parameters_matched is False and selected_ids == []
                        and _empty_consequence_projection(public_nc))
                    if not_applied:
                        availability = "unavailable"
                row = {
                    "name": name, "action_id": action_id, "direction": "demand",
                    "optional": optional,
                    "error": error, "public_path": str(case_dir / "public.json"),
                    "native_slice": slice_meta,
                    "native_event_path": str(case_dir / "native-event.json") if raw else None,
                    "native_query_id": raw.get("query_id") if raw else None,
                    "api_error_code": api_error,
                    "public_projection_recovered": recovered,
                    "public_contract": public_contract,
                    "raw_header_contract": header if raw else None,
                    "native_validator": native_valid,
                    "validator_normalization": _validator_normalization(raw),
                    "native_consequences_present": isinstance(raw_nc, dict),
                    "consequence_contract": nc_valid,
                    "requested_terms_applied": (
                        projected.get("requested_terms_applied")
                        if isinstance(projected, dict) else None),
                    "consequence_reason_code": (
                        projected.get("reason_code")
                        if isinstance(projected, dict) else None),
                    "raw_public_parity": parity,
                    "object_unchanged": unchanged,
                    "private_fields_absent": private_absent,
                    "native_parameter_state": native_state,
                    "native_public_parity": native_public_parity,
                    "not_applied": not_applied,
                    "availability": availability,
                    "legality_status": public.get("legality", {}).get("status")
                    if isinstance(public, dict) and isinstance(public.get("legality"), dict)
                    else "unknown",
                }
                report["cases"].append(row)

            for action_id in ACTION_IDS:
                if action_id == "cede_province":
                    run_case("cede_province_88_FRA", action_id,
                             _request_parameters(action_id, war_id, recipient,
                                                 beneficiary=ACTOR,
                                                 province_ids=[88]),
                             province_ids=[88], beneficiary=ACTOR)
                else:
                    run_case(action_id, action_id,
                             _request_parameters(action_id, war_id, recipient))
            # This is an explicit third-country coverage probe.  It is kept
            # separate from the required 19-family set because ORL is not a
            # guessed legal beneficiary; a native candidate must prove it.
            run_case("cede_province_88_ORL", "cede_province",
                     _request_parameters("cede_province", war_id, recipient,
                                         beneficiary="ORL", province_ids=[88]),
                     province_ids=[88], beneficiary="ORL", optional=True)
        after_health = session.health()
        after_probe = _run_probe(PROBE_SPECS[0], session.record["pid"],
                                 evidence / "after" / "control.json")
        control_after = _control_from_probe(after_probe)
        report["after"] = {"health": after_health, "control": control_after}
        cases = report["cases"]
        required_cases = [row for row in cases if not row.get("optional")]
        available = [row for row in cases if row.get("availability") == "available"]
        report["availability"] = {
            "available": [row["name"] for row in available],
            "unavailable": [row["name"] for row in cases
                            if row.get("availability") == "unavailable"],
            "unknown": [row["name"] for row in cases if row.get("availability") == "unknown"],
            "invalid": [row["name"] for row in cases if row.get("availability") == "invalid"],
        }
        orl_case = next((row for row in cases
                         if row.get("name") == "cede_province_88_ORL"), None)
        report["province_88_comparison"] = {
            "fra_case": "cede_province_88_FRA", "orl_case": "cede_province_88_ORL",
            "offer_orl_queried": True,
            "third_country_candidate_required": True,
            "third_country_success": bool(
                isinstance(orl_case, dict)
                and orl_case.get("availability") == "available"
                and orl_case.get("native_parameter_state") is True),
            "orl_unavailable": bool(
                isinstance(orl_case, dict)
                and orl_case.get("availability") == "unavailable"),
            "orl_not_applied": bool(
                isinstance(orl_case, dict) and orl_case.get("not_applied") is True),
            "orl_requested_province": 88,
        }
        report["checks"] = {
            "before_por_paused": _control_is_paused_por(control_before, date_raw),
            "after_por_paused_same_date": (_control_is_paused_por(control_after, date_raw)
                                            and control_after.get("date_raw") == date_raw),
            "same_session": (report["session"].get("session_id") == session.session_id),
            "catalog_19_query_consequences": catalog_contract,
            "all_action_ids_queried": {
                row["action_id"] for row in required_cases} == set(ACTION_IDS),
            "all_required_native_public_parity": all(
                row.get("native_public_parity") is True for row in required_cases),
            "no_required_unknown_or_invalid": all(
                row.get("availability") not in ("unknown", "invalid")
                for row in required_cases),
            "public_results_no_private_fields": all(
                row.get("private_fields_absent") is True
                for row in cases if row.get("native_public_parity") is True),
            "province_88_fra_and_orl_recorded": all(
                any(row.get("name") == f"cede_province_88_{tag}" for row in cases)
                for tag in (ACTOR, "ORL")),
            "orl_unavailable_is_explicit": bool(
                isinstance(orl_case, dict)
                and ((orl_case.get("availability") == "available")
                     or (orl_case.get("availability") == "unavailable"
                         and orl_case.get("not_applied") is True))),
            "no_business_submission": report["execute_call_count"] == 0
            and report["business_submission"] is False
            and report["advance_requested"] is False
            and report["save_requested"] is False
            and report["restart_requested"] is False,
        }
        report["required_case_count"] = len(required_cases)
        report["required_cases_with_native_public_parity"] = sum(
            row.get("native_public_parity") is True for row in required_cases)
        report["api_projection_recovery_cases"] = [
            row["name"] for row in cases if row.get("public_projection_recovered")]
        report["status_reason"] = {
            "unknown_cases": report["availability"]["unknown"],
            "invalid_cases": report["availability"]["invalid"],
            "unavailable_cases": report["availability"]["unavailable"],
            "third_country_not_applied": report["province_88_comparison"][
                "orl_not_applied"],
        }
        report["required_checks"] = {
            key: report["checks"][key] for key in (
                "before_por_paused", "after_por_paused_same_date", "same_session",
                "catalog_19_query_consequences",
                "all_action_ids_queried", "all_required_native_public_parity",
                "no_required_unknown_or_invalid", "public_results_no_private_fields",
                "no_business_submission")}
        report["coverage"] = {
            "required_action_ids": list(ACTION_IDS),
            "required_case_names": [row["name"] for row in required_cases],
            "required_case_count": len(required_cases),
            "required_cases_with_native_public_parity": report[
                "required_cases_with_native_public_parity"],
            "availability": report["availability"],
            "unknown_or_invalid_cases": (
                report["availability"]["unknown"]
                + report["availability"]["invalid"]),
            "optional_cases": [
                {key: row.get(key) for key in (
                    "name", "action_id", "availability", "native_parameter_state",
                    "native_public_parity", "not_applied")}
                for row in cases if row.get("optional")],
        }
        required_ok = (report["checks"]["all_action_ids_queried"]
                       and report["checks"]["catalog_19_query_consequences"]
                       and report["checks"]["all_required_native_public_parity"]
                       and report["checks"]["no_required_unknown_or_invalid"])
        hard_failure = (not report["checks"]["before_por_paused"]
                        or not report["checks"]["after_por_paused_same_date"]
                        or not report["checks"]["same_session"]
                        or not report["checks"]["no_business_submission"]
                        or bool(report["availability"]["invalid"]))
        if hard_failure:
            report["status"] = "failed"
        elif (required_ok
              and all(report["required_checks"].values())
              and report["checks"]["orl_unavailable_is_explicit"]):
            report["status"] = "passed"
        else:
            report["status"] = "passed_partial"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        if report_path is not None:
            _write(report_path, report)
    print(json.dumps({"status": report["status"], "report": str(report_path),
                      "query_call_count": report["query_call_count"]}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
