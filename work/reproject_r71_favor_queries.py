"""Reproject the saved R71 favor-for-gold queries without game/API access.

The source batch contains the native observation event for each target.  This
script binds those events to the original source files, decodes them through
the existing semantic projection, and then runs the complete public
``DiplomacyTools.inspect_diplomatic_action`` facade against a replay session.
The replay session has no native transport, health probe, or query side
effects.  It is deliberately limited to the query capability advertised by
the saved source catalog.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.favor_trade import (
    ACTION_ID,
    QUERY_CAPABILITY,
    project_query,
    validate_query,
)
from bridge.native_text import EU4_ESCAPE_CODEC


ACTOR = "FRA"
PHASE = "initiate"
COOLDOWN_TEXT = "1458年7月31日"
PAP_CASH_TEXT = "教宗国没有"

# Keep this list aligned with the public query contract.  The extra fields are
# included here because this artifact also serves as a regression guard for
# accidental raw-event leakage from a future facade change.
FORBIDDEN_PUBLIC_KEYS = frozenset({
    "pid", "session_id", "creation_filetime", "native_war_reference",
    "native_reference", "module_base", "vtable_rva", "dll_sha256",
    "query_id", "frame_thread", "native_diagnostic_hex",
    "native_proposal_id", "actor_treasury_raw", "recipient_treasury_raw",
})
REQUIRED_PUBLIC_KEYS = frozenset({
    "action_id", "actor", "recipient", "phase", "session", "legality",
    "authorization", "favor_trade", "costs", "native_diagnostic",
})


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _has_private_fields(value: object) -> bool:
    if isinstance(value, dict):
        return bool(FORBIDDEN_PUBLIC_KEYS.intersection(value)) or any(
            _has_private_fields(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_private_fields(item) for item in value)
    return False


def _catalog_query_capability(catalog: dict[str, Any]) -> str:
    """Read the favor query cap from the saved catalog, never from runtime."""

    actions = catalog.get("actions")
    if not isinstance(actions, list):
        raise ValueError("source catalog has no actions list")
    for action in actions:
        if not isinstance(action, dict) or action.get("action_id") != ACTION_ID:
            continue
        phases = action.get("phases")
        initiate = phases.get(PHASE) if isinstance(phases, dict) else None
        query = initiate.get("query") if isinstance(initiate, dict) else None
        if query != QUERY_CAPABILITY:
            raise ValueError(
                f"source catalog query capability changed: {query!r}")
        return query
    raise ValueError(f"source catalog has no {ACTION_ID!r} action")


class ReplaySession:
    """Minimal local session used by the full public facade."""

    def __init__(
        self,
        raw: dict[str, Any],
        health: dict[str, Any],
        capabilities: frozenset[str],
        session_id: str,
        actor: str,
        recipient: str,
    ) -> None:
        self._raw = copy.deepcopy(raw)
        self._health = copy.deepcopy(health)
        self._capabilities = frozenset(capabilities)
        self.session_id = session_id
        self.native_text_codec = EU4_ESCAPE_CODEC
        self.record = {"controlled_countries": [actor]}
        self._actor = actor
        self._recipient = recipient
        self.inspect_calls = 0
        self.health_reads = 0
        self.capability_reads = 0
        # These counters deliberately stay at zero: the replay never contacts
        # a native adapter or a game/API query endpoint.
        self.native_query_calls = 0
        self.submit_calls = 0

    def health(self) -> dict[str, Any]:
        self.health_reads += 1
        return copy.deepcopy(self._health)

    def installation_capabilities(self) -> frozenset[str]:
        self.capability_reads += 1
        return self._capabilities

    def inspect_alliance(
        self,
        action_id: str,
        actor: str,
        recipient: str,
        phase: str,
        _query_capabilities: object = None,
        **_kwargs: object,
    ) -> dict[str, Any]:
        """Return the saved event's semantic projection, with no native call."""

        if (action_id, actor, recipient, phase) != (
            ACTION_ID, self._actor, self._recipient, PHASE
        ):
            raise ValueError("replay inspection identity mismatch")
        self.inspect_calls += 1
        return ObserverSession._semantic_inspection(
            copy.deepcopy(self._raw), {}, codec=EU4_ESCAPE_CODEC)

    def submit_trade_favors_for_gold(self, *_args: object, **_kwargs: object) -> dict[str, Any]:
        """Guard against a future test accidentally reaching native submit."""

        self.submit_calls += 1
        raise AssertionError("offline favor replay attempted native submission")


def reproject_case(
    raw: dict[str, Any],
    actor: str,
    recipient: str,
    health: dict[str, Any],
    capabilities: frozenset[str],
    session_id: str,
) -> dict[str, Any]:
    """Run the complete public inspection against one saved raw event."""

    session = ReplaySession(
        raw, health, capabilities, session_id, actor, recipient)
    semantic = ObserverSession._semantic_inspection(
        copy.deepcopy(raw), {}, codec=EU4_ESCAPE_CODEC)
    public = DiplomacyTools(None, session).inspect_diplomatic_action(
        ACTION_ID, actor, recipient, PHASE)
    return {"semantic": semantic, "public": public, "session": session}


def _case_checks(
    raw: dict[str, Any],
    public: dict[str, Any],
    semantic: dict[str, Any],
    health: dict[str, Any],
    replay: ReplaySession,
    actor: str,
    recipient: str,
) -> dict[str, bool]:
    legality = public.get("legality")
    reasons = legality.get("reasons", []) if isinstance(legality, dict) else []
    first_reason = reasons[0] if reasons and isinstance(reasons[0], dict) else {}
    diagnostic = public.get("native_diagnostic")
    diagnostic_text = diagnostic.get("text") if isinstance(diagnostic, dict) else None
    semantic_text = semantic.get("native_diagnostic_text")
    query = raw.get("native_favor_trade")
    expected_trade = project_query(query, actor, recipient)
    public_session = public.get("session")
    return {
        "raw_identity_valid": ObserverSession._valid_native_inspection(
            raw, ACTION_ID, actor, recipient, PHASE, raw.get("date_raw"),
            raw.get("query_id"), raw.get("session_id")),
        "raw_resource_valid": validate_query(query),
        "full_tools_projection": REQUIRED_PUBLIC_KEYS.issubset(public),
        "action_identity_bound": all(public.get(key) == value for key, value in (
            ("action_id", ACTION_ID), ("actor", actor),
            ("recipient", recipient), ("phase", PHASE))),
        "legality_unavailable": isinstance(legality, dict)
        and legality.get("status") == "unavailable",
        "legality_complete": isinstance(legality, dict)
        and legality.get("complete") is True,
        "native_reason_first": first_reason.get("code") == "NATIVE_VALIDITY_FALSE",
        "native_reason_text_complete": (
            first_reason.get("text") == diagnostic_text
            and diagnostic_text == semantic_text
            and isinstance(diagnostic_text, str)
            and bool(diagnostic_text.strip())),
        "cooldown_date_present": COOLDOWN_TEXT in (diagnostic_text or ""),
        "pap_cash_reason_present": (
            recipient != "PAP"
            or (PAP_CASH_TEXT in (diagnostic_text or "")
                and "12" in (diagnostic_text or ""))),
        "public_favor_trade_present": public.get("favor_trade") == expected_trade,
        "semantic_trade_matches_public": public.get("favor_trade") == semantic.get(
            "favor_trade"),
        "health_date_bound": isinstance(public_session, dict)
        and public_session.get("date_raw") == health.get("date_raw"),
        "public_private_fields_absent": not _has_private_fields(public),
        "no_external_native_query": replay.native_query_calls == 0,
        "no_native_submit": replay.submit_calls == 0,
    }


def _fixture_case(
    name: str,
    recipient: str,
    raw: dict[str, Any],
    public: dict[str, Any],
    source_raw_sha256: str,
) -> dict[str, Any]:
    diagnostic = public.get("native_diagnostic", {})
    trade = raw.get("native_favor_trade", {})
    return {
        "name": name,
        "action_id": ACTION_ID,
        "actor": ACTOR,
        "recipient": recipient,
        "phase": PHASE,
        "date_raw": raw.get("date_raw"),
        "query_id": raw.get("query_id"),
        "source_raw_sha256": source_raw_sha256,
        "raw": copy.deepcopy(raw),
        "expected": {
            "legality_status": "unavailable",
            "legality_complete": True,
            "cooldown_text": COOLDOWN_TEXT,
            "pap_cash_text": PAP_CASH_TEXT if recipient == "PAP" else None,
            "native_diagnostic_text": diagnostic.get("text"),
            "amount_raw": trade.get("amount_raw"),
            "favor_cost_raw": trade.get("favor_cost_raw"),
            "favors_available_raw": trade.get("favors_available_raw"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="original R71 report.json")
    parser.add_argument("--output", type=Path, required=True,
                        help="new report.json under a new output directory")
    parser.add_argument(
        "--fixture", type=Path,
        default=ROOT / "bridge/tests/fixtures/r71_favor_queries_real.json",
        help="self-contained fixture path (default: bridge/tests/fixtures/...)",
    )
    args = parser.parse_args()
    source_report_path = args.source.resolve()
    output_report_path = args.output.resolve()
    output_root = output_report_path.parent
    fixture_path = args.fixture.resolve()
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite output directory: {output_root}")
    if not source_report_path.is_file():
        raise FileNotFoundError(source_report_path)

    source_report = _read_json(source_report_path)
    if not isinstance(source_report, dict):
        raise ValueError("source report is not an object")
    source_catalog_path = source_report_path.parent / "catalog.json"
    source_catalog = _read_json(source_catalog_path)
    query_capability = _catalog_query_capability(source_catalog)
    capabilities = frozenset({query_capability})
    source_cases = source_report.get("cases")
    health = source_report.get("health")
    session_id = source_report.get("session_id")
    if not isinstance(source_cases, list) or len(source_cases) != 8:
        raise ValueError("expected exactly eight source cases")
    if not isinstance(health, dict) or not isinstance(session_id, str):
        raise ValueError("source report lacks reusable health/session")

    output_root.mkdir(parents=True, exist_ok=False)
    fixture_cases: list[dict[str, Any]] = []
    report_cases: list[dict[str, Any]] = []
    for source_case in source_cases:
        if not isinstance(source_case, dict):
            raise ValueError("source case is not an object")
        name = source_case.get("name")
        action_id = source_case.get("action_id")
        recipient = source_case.get("recipient")
        if (not isinstance(name, str) or action_id != ACTION_ID
                or not isinstance(recipient, str)):
            raise ValueError(f"invalid source case identity: {source_case!r}")
        raw_path = source_report_path.parent / "cases" / name / "native-event.json"
        if not raw_path.is_file():
            raise FileNotFoundError(raw_path)
        raw_bytes = raw_path.read_bytes()
        raw = json.loads(raw_bytes.decode("utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"raw event is not an object: {raw_path}")
        if (raw.get("action_id") != ACTION_ID or raw.get("actor") != ACTOR
                or raw.get("recipient") != recipient or raw.get("phase") != PHASE
                or raw.get("session_id") != session_id):
            raise ValueError(f"raw event identity mismatch: {raw_path}")

        projected = reproject_case(
            raw, ACTOR, recipient, health, capabilities, session_id)
        semantic = projected["semantic"]
        public = projected["public"]
        replay = projected["session"]
        checks = _case_checks(
            raw, public, semantic, health, replay, ACTOR, recipient)
        case_root = output_root / "cases" / name
        case_root.mkdir(parents=True, exist_ok=False)
        native_event_path = case_root / "native-event.json"
        native_event_path.write_bytes(raw_bytes)
        semantic_path = case_root / "semantic.json"
        public_path = case_root / "public.json"
        _write_json(semantic_path, semantic)
        _write_json(public_path, public)
        source_raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        report_cases.append({
            "name": name,
            "action_id": ACTION_ID,
            "actor": ACTOR,
            "recipient": recipient,
            "phase": PHASE,
            "source_raw_path": str(raw_path),
            "source_raw_sha256": source_raw_sha256,
            "raw_source_bound": True,
            "native_event_path": str(native_event_path),
            "semantic_path": str(semantic_path),
            "public_path": str(public_path),
            "projection_method": "DiplomacyTools.inspect_diplomatic_action",
            "projection_calls": replay.inspect_calls,
            "native_query_calls": replay.native_query_calls,
            "api_call_count": 0,
            "game_query_count": 0,
            "legality": public.get("legality"),
            "native_diagnostic": public.get("native_diagnostic"),
            "favor_trade": public.get("favor_trade"),
            "public_checks": checks,
            "public_private_fields_absent": checks["public_private_fields_absent"],
        })
        fixture_cases.append(_fixture_case(
            name, recipient, raw, public, source_raw_sha256))

    report_checks = {
        "case_count_eight": len(report_cases) == 8,
        "all_raw_identity_valid": all(
            c["public_checks"]["raw_identity_valid"] for c in report_cases),
        "all_raw_resource_valid": all(
            c["public_checks"]["raw_resource_valid"] for c in report_cases),
        "all_full_tools_projections": all(
            c["public_checks"]["full_tools_projection"] for c in report_cases),
        "all_unavailable": all(
            c["public_checks"]["legality_unavailable"] for c in report_cases),
        "all_legality_complete": all(
            c["public_checks"]["legality_complete"] for c in report_cases),
        "all_native_reasons_first": all(
            c["public_checks"]["native_reason_first"] for c in report_cases),
        "all_native_reason_text_complete": all(
            c["public_checks"]["native_reason_text_complete"] for c in report_cases),
        "all_cooldown_dates_present": all(
            c["public_checks"]["cooldown_date_present"] for c in report_cases),
        "pap_cash_reason_present": all(
            c["public_checks"]["pap_cash_reason_present"] for c in report_cases),
        "all_public_trade_present": all(
            c["public_checks"]["public_favor_trade_present"] for c in report_cases),
        "all_semantic_trade_matches": all(
            c["public_checks"]["semantic_trade_matches_public"] for c in report_cases),
        "public_private_fields_absent": all(
            c["public_checks"]["public_private_fields_absent"] for c in report_cases),
        "all_health_dates_bound": all(
            c["public_checks"]["health_date_bound"] for c in report_cases),
        "zero_api_calls": True,
        "zero_game_queries": True,
        "zero_native_queries": all(
            c["public_checks"]["no_external_native_query"] for c in report_cases),
        "zero_native_submissions": all(
            c["public_checks"]["no_native_submit"] for c in report_cases),
        "source_raw_bound": all(c["raw_source_bound"] for c in report_cases),
    }
    report: dict[str, Any] = {
        "status": "passed" if all(report_checks.values()) else "failed",
        "mode": "offline_reproject_r71_favor_queries",
        "game_contact": False,
        "source_report": str(source_report_path),
        "source_report_sha256": _sha256(source_report_path),
        "source_catalog": str(source_catalog_path),
        "source_catalog_sha256": _sha256(source_catalog_path),
        "source_session_id": session_id,
        "health": copy.deepcopy(health),
        "health_source_reused": True,
        "capabilities": sorted(capabilities),
        "capabilities_source": "source catalog actions[trade_favors_for_gold].phases.initiate.query",
        "api_call_count": 0,
        "game_query_count": 0,
        "native_query_call_count": 0,
        "execute_call_count": 0,
        "fixture_path": str(fixture_path),
        "public_checks": report_checks,
        "cases": report_cases,
        "availability": {
            "all_cases_unavailable": report_checks["all_unavailable"],
            "available_case_names": [
                c["name"] for c in report_cases
                if c["legality"].get("status") == "available"
            ],
            "unavailable_case_names": [
                c["name"] for c in report_cases
                if c["legality"].get("status") == "unavailable"
            ],
        },
    }
    _write_json(output_report_path, report)

    fixture = {
        "format": "r71_favor_queries_real_fixture_v1",
        "source_batch": source_report_path.parent.name,
        "source_report_sha256": _sha256(source_report_path),
        "source_catalog_sha256": _sha256(source_catalog_path),
        "session_id": session_id,
        "health": copy.deepcopy(health),
        "capabilities": sorted(capabilities),
        "cases": fixture_cases,
    }
    if fixture_path.exists():
        if _read_json(fixture_path) != fixture:
            raise FileExistsError(
                f"refusing to overwrite a different fixture: {fixture_path}")
    else:
        _write_json(fixture_path, fixture)

    print(json.dumps({
        "status": report["status"],
        "report": str(output_report_path),
        "fixture": str(fixture_path),
        "api_call_count": report["api_call_count"],
        "game_query_count": report["game_query_count"],
        "cases": len(report_cases),
        "all_unavailable": report_checks["all_unavailable"],
        "pap_cash_reason_present": report_checks["pap_cash_reason_present"],
    }, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
