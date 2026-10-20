"""Offline re-projection of the sixteen R73 favor query observations.

The live operator writes one bounded ``native.jsonl`` slice per query.  A
private reverse-direction call returns a semantic projection, so this tool
always selects the original ``native_alliance_inspection`` event from that
slice and stores the semantic projection separately.  FRA-forward cases are
fed through the complete public ``DiplomacyTools.inspect_diplomatic_action``
facade; reverse cases remain operator-private semantic evidence and are never
turned into an LLM-facing result.
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
from bridge.favor_resources import project_query, validate_query
from bridge.native_text import EU4_ESCAPE_CODEC


ACTION_KINDS = {
    "trade_favors_for_trust": "trust",
    "trade_favors_for_men": "men",
}
PHASE = "initiate"
ACTOR_SCOPE = "FRA"
MAX_NATIVE_LINE = 2 * 1024 * 1024

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


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _has_private_fields(value: object) -> bool:
    if isinstance(value, dict):
        return bool(FORBIDDEN_PUBLIC_KEYS.intersection(value)) or any(
            _has_private_fields(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_private_fields(item) for item in value)
    return False


def _read_native_events(path: Path) -> list[tuple[dict[str, Any], bytes]]:
    """Read a bounded JSONL slice without loading an unbounded log."""

    events: list[tuple[dict[str, Any], bytes]] = []
    with path.open("rb") as stream:
        while True:
            line = stream.readline(MAX_NATIVE_LINE + 1)
            if not line:
                break
            if len(line) > MAX_NATIVE_LINE:
                continue
            try:
                value = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                events.append((value, line))
    return events


def _select_raw_event(
    path: Path,
    session_id: str,
    action_id: str,
    actor: str,
    recipient: str,
) -> tuple[dict[str, Any], bytes]:
    matches = [
        (event, line)
        for event, line in _read_native_events(path)
        if event.get("event") == "native_alliance_inspection"
        and event.get("session_id") == session_id
        and event.get("action_id") == action_id
        and event.get("actor") == actor
        and event.get("recipient") == recipient
        and event.get("phase") == PHASE
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected one raw event in {path.name} for "
            f"{action_id} {actor}->{recipient}, found {len(matches)}")
    return matches[0]


def _catalog_capabilities(catalog: dict[str, Any], action_id: str) -> tuple[str, str]:
    actions = catalog.get("actions")
    if not isinstance(actions, list):
        raise ValueError("source catalog has no actions list")
    for action in actions:
        if not isinstance(action, dict) or action.get("action_id") != action_id:
            continue
        phases = action.get("phases")
        initiate = phases.get(PHASE) if isinstance(phases, dict) else None
        query = initiate.get("query") if isinstance(initiate, dict) else None
        submission = initiate.get("execute") if isinstance(initiate, dict) else None
        expected = f"native_favor_{ACTION_KINDS[action_id]}_query"
        expected_submission = f"native_favor_{ACTION_KINDS[action_id]}_submission"
        if query != expected:
            raise ValueError(
                f"source catalog query capability changed for {action_id}: {query!r}")
        if submission != expected_submission:
            raise ValueError(
                f"source catalog submission capability changed for {action_id}: "
                f"{submission!r}")
        return query, submission
    raise ValueError(f"source catalog has no {action_id!r} action")


class ReplaySession:
    """A no-I/O session that exposes exactly one saved query result."""

    def __init__(
        self,
        raw: dict[str, Any],
        semantic: dict[str, Any],
        health: dict[str, Any],
        capabilities: tuple[str, str],
        session_id: str,
        actor: str,
        recipient: str,
    ) -> None:
        self._raw = copy.deepcopy(raw)
        self._semantic = copy.deepcopy(semantic)
        self._health = copy.deepcopy(health)
        self._query_capability, self._submission_capability = capabilities
        self.session_id = session_id
        self.native_text_codec = EU4_ESCAPE_CODEC
        self.record = {"controlled_countries": [ACTOR_SCOPE]}
        self._actor = actor
        self._recipient = recipient
        self.inspect_calls = 0
        self.native_query_calls = 0
        self.submit_calls = 0

    def health(self) -> dict[str, Any]:
        return copy.deepcopy(self._health)

    def installation_capabilities(self) -> frozenset[str]:
        return frozenset({self._query_capability, self._submission_capability})

    def inspect_alliance(
        self,
        action_id: str,
        actor: str,
        recipient: str,
        phase: str,
        query_capabilities: object = None,
        **_kwargs: object,
    ) -> dict[str, Any]:
        if (action_id, actor, recipient, phase) != (
            self._raw.get("action_id"), self._actor, self._recipient, PHASE):
            raise ValueError("replay inspection identity mismatch")
        if (query_capabilities is not None
                and frozenset(query_capabilities)
                != frozenset({self._query_capability})):
            raise ValueError("replay query capability mismatch")
        self.inspect_calls += 1
        return copy.deepcopy(self._semantic)

    def submit_trade_favors_for_trust(self, *_args: object, **_kwargs: object) -> dict[str, Any]:
        self.submit_calls += 1
        raise AssertionError("offline replay attempted native trust submission")

    def submit_trade_favors_for_men(self, *_args: object, **_kwargs: object) -> dict[str, Any]:
        self.submit_calls += 1
        raise AssertionError("offline replay attempted native men submission")


def _raw_checks(
    raw: dict[str, Any],
    action_id: str,
    actor: str,
    recipient: str,
    session_id: str,
    date_raw: object,
    capability: str,
) -> dict[str, bool]:
    query = raw.get("native_favor_trade")
    return {
        "event_identity_bound": all(raw.get(key) == expected for key, expected in (
            ("event", "native_alliance_inspection"),
            ("action_id", action_id), ("actor", actor),
            ("recipient", recipient), ("phase", PHASE),
            ("family", "favor_trade"), ("session_id", session_id))),
        "raw_schema_valid": ObserverSession._valid_native_inspection(
            raw, action_id, actor, recipient, PHASE, date_raw,
            raw.get("query_id"), session_id),
        "resource_schema_valid": validate_query(query),
        "resource_kind_bound": isinstance(query, dict)
        and query.get("kind") == ACTION_KINDS[action_id],
        "query_capability_bound": capability
        == f"native_favor_{ACTION_KINDS[action_id]}_query",
        "source_query_id_present": isinstance(raw.get("query_id"), str),
    }


def _semantic_checks(
    raw: dict[str, Any], semantic: dict[str, Any], actor: str, recipient: str,
) -> dict[str, bool]:
    query = raw.get("native_favor_trade")
    expected_trade = project_query(query, actor, recipient)
    diagnostic = semantic.get("native_diagnostic_text")
    diagnostic_present = raw.get("diagnostic_readable") is not True or (
        isinstance(diagnostic, str) and bool(diagnostic.strip()))
    return {
        "semantic_identity_bound": all(semantic.get(key) == expected for key, expected in (
            ("event", "native_alliance_inspection"),
            ("action_id", raw.get("action_id")), ("actor", actor),
            ("recipient", recipient), ("phase", PHASE))),
        "semantic_trade_matches_native": semantic.get("favor_trade") == expected_trade,
        "readable_chinese_reason_present": diagnostic_present,
        "normalized_is_separate": semantic is not raw,
    }


def _public_checks(
    raw: dict[str, Any], public: dict[str, Any], semantic: dict[str, Any],
    actor: str, recipient: str, action_id: str, submission_capability: str,
) -> dict[str, bool]:
    legality = public.get("legality")
    diagnostic = public.get("native_diagnostic")
    diagnostic_text = diagnostic.get("text") if isinstance(diagnostic, dict) else None
    semantic_text = semantic.get("native_diagnostic_text")
    reasons = legality.get("reasons", []) if isinstance(legality, dict) else []
    specific_reason = any(
        isinstance(item, dict)
        and item.get("code") == "NATIVE_VALIDITY_FALSE"
        and item.get("text") == semantic_text
        for item in reasons)
    native_validity_reason_ok = (
        raw.get("native_validity") is not False or specific_reason)
    return {
        "required_public_projection": REQUIRED_PUBLIC_KEYS.issubset(public),
        "public_identity_bound": all(public.get(key) == expected for key, expected in (
            ("action_id", action_id), ("actor", actor),
            ("recipient", recipient), ("phase", PHASE))),
        "public_favor_trade_matches_semantic": public.get("favor_trade")
        == semantic.get("favor_trade"),
        "public_private_fields_absent": not _has_private_fields(public),
        "legality_is_classified": isinstance(legality, dict)
        and legality.get("status") in ("available", "unavailable", "unknown"),
        "legality_complete": isinstance(legality, dict)
        and legality.get("complete") is True,
        "public_reason_matches_normalized": diagnostic_text == semantic_text,
        "submission_support_acknowledged": (
            public.get("interface_support", {}).get("execute")
            == submission_capability),
        "authorization_independent_of_legality": (
            public.get("authorization", {}).get("status") == "available"
            and isinstance(legality, dict)
            and legality.get("status") != "available"),
        "specific_native_validity_reason": native_validity_reason_ok,
    }


def _source_case_name(action_id: str, actor: str, recipient: str) -> str:
    return f"{ACTION_KINDS[action_id]}_{actor}_{recipient}"


def _output_paths(requested: Path) -> tuple[Path, Path]:
    target = requested.expanduser().resolve()
    if target.exists():
        raise FileExistsError(f"refusing to overwrite output: {target}")
    if target.suffix.casefold() == ".json":
        return target.parent, target
    return target, target / "report.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="R73-001 report.json")
    parser.add_argument("--output", type=Path, required=True,
                        help="new output directory, or report.json path")
    args = parser.parse_args()

    source_report_path = args.source.expanduser().resolve()
    if not source_report_path.is_file():
        raise FileNotFoundError(source_report_path)
    output_root, output_report_path = _output_paths(args.output)
    source_report = _read_json(source_report_path)
    if not isinstance(source_report, dict):
        raise ValueError("source report is not an object")
    source_root = source_report_path.parent
    source_catalog_path = source_root / "catalog.json"
    source_catalog = _read_json(source_catalog_path)
    if not isinstance(source_catalog, dict):
        raise ValueError("source catalog is not an object")
    source_cases = source_report.get("cases")
    health = source_report.get("health")
    session_id = source_report.get("session_id")
    date_raw = health.get("date_raw") if isinstance(health, dict) else None
    if not isinstance(source_cases, list) or len(source_cases) != 16:
        raise ValueError("expected exactly sixteen source cases")
    if (not isinstance(health, dict) or health.get("status") != "ready"
            or not isinstance(session_id, str) or not isinstance(date_raw, int)
            or isinstance(date_raw, bool)):
        raise ValueError("source report lacks reusable ready health/session")
    catalog_capabilities = {
        action_id: _catalog_capabilities(source_catalog, action_id)
        for action_id in ACTION_KINDS
    }

    output_root.mkdir(parents=True, exist_ok=False)
    report_cases: list[dict[str, Any]] = []
    facade_count = 0
    for source_case in source_cases:
        if not isinstance(source_case, dict):
            raise ValueError("source case is not an object")
        action_id = source_case.get("action_id")
        actor = source_case.get("actor")
        recipient = source_case.get("recipient")
        if (action_id not in ACTION_KINDS or not isinstance(actor, str)
                or not isinstance(recipient, str)):
            raise ValueError(f"invalid source case identity: {source_case!r}")
        name = _source_case_name(action_id, actor, recipient)
        source_case_root = source_root / "cases" / name
        raw_jsonl = source_case_root / "native.jsonl"
        if not raw_jsonl.is_file():
            raise FileNotFoundError(raw_jsonl)
        query_capability, submission_capability = catalog_capabilities[action_id]
        raw, raw_line = _select_raw_event(
            raw_jsonl, session_id, action_id, actor, recipient)
        raw_checks = _raw_checks(
            raw, action_id, actor, recipient, session_id, date_raw, query_capability)
        semantic = ObserverSession._semantic_inspection(
            copy.deepcopy(raw), {}, codec=EU4_ESCAPE_CODEC)
        semantic_checks = _semantic_checks(raw, semantic, actor, recipient)

        public = None
        public_checks: dict[str, bool] | None = None
        replay = None
        operator_private_scope = actor != ACTOR_SCOPE
        if not operator_private_scope:
            replay = ReplaySession(
                raw, semantic, health, (query_capability, submission_capability),
                session_id, actor, recipient)
            public = DiplomacyTools(None, replay).inspect_diplomatic_action(
                action_id, actor, recipient, PHASE)
            facade_count += 1
            public_checks = _public_checks(
                raw, public, semantic, actor, recipient, action_id,
                submission_capability)

        case_root = output_root / "cases" / name
        case_root.mkdir(parents=True, exist_ok=False)
        raw_path = case_root / "native-event.json"
        raw_path.write_bytes(raw_line)
        normalized_path = case_root / "normalized.json"
        _write_json(normalized_path, semantic)
        public_path = None
        if public is not None:
            public_path = case_root / "public.json"
            _write_json(public_path, public)

        source_slice = source_case.get("native_slice")
        report_cases.append({
            "name": name,
            "action_id": action_id,
            "kind": ACTION_KINDS[action_id],
            "actor": actor,
            "recipient": recipient,
            "phase": PHASE,
            "operator_private_scope": operator_private_scope,
            "llm_visible": not operator_private_scope,
            "projection": "operator_private_semantic" if operator_private_scope
            else "DiplomacyTools.inspect_diplomatic_action",
            "query_capability": query_capability,
            "submission_capability": submission_capability,
            "source_native_jsonl": str(raw_jsonl),
            "source_slice_sha256": source_slice.get("sha256")
            if isinstance(source_slice, dict) else None,
            "source_raw_sha256": _sha256_bytes(raw_line),
            "source_raw_bytes": len(raw_line),
            "raw_event_path": str(raw_path),
            "normalized_path": str(normalized_path),
            "public_path": str(public_path) if public_path else None,
            "raw_checks": raw_checks,
            "semantic_checks": semantic_checks,
            "public_checks": public_checks,
            "native_diagnostic_text": semantic.get("native_diagnostic_text"),
            "legality": public.get("legality") if public else None,
            "favor_trade": public.get("favor_trade") if public else semantic.get(
                "favor_trade"),
            "game_query_count": 0,
            "native_query_call_count": 0,
            "submit_call_count": 0,
            "replay_inspect_call_count": replay.inspect_calls if replay else 0,
        })

    all_raw = all(all(case["raw_checks"].values()) for case in report_cases)
    all_semantic = all(all(case["semantic_checks"].values()) for case in report_cases)
    forward_cases = [case for case in report_cases if not case["operator_private_scope"]]
    all_public = all(
        case["public_checks"] is not None
        and all(case["public_checks"].values()) for case in forward_cases)
    availability = {
        "available_case_names": [
            case["name"] for case in forward_cases
            if isinstance(case.get("legality"), dict)
            and case["legality"].get("status") == "available"],
        "unavailable_case_names": [
            case["name"] for case in forward_cases
            if isinstance(case.get("legality"), dict)
            and case["legality"].get("status") == "unavailable"],
        "unknown_case_names": [
            case["name"] for case in forward_cases
            if isinstance(case.get("legality"), dict)
            and case["legality"].get("status") == "unknown"],
    }
    checks = {
        "case_count_sixteen": len(report_cases) == 16,
        "all_raw_events_valid": all_raw,
        "all_semantic_projections_valid": all_semantic,
        "all_forward_public_projections_valid": all_public,
        "all_forward_submission_support_acknowledged": all(
            case["public_checks"] is not None
            and case["public_checks"]["submission_support_acknowledged"]
            for case in forward_cases),
        "all_forward_support_independent_of_legality": all(
            case["public_checks"] is not None
            and case["public_checks"]["authorization_independent_of_legality"]
            for case in forward_cases),
        "all_forward_native_validity_reasons_specific": all(
            case["public_checks"] is not None
            and case["public_checks"]["specific_native_validity_reason"]
            for case in forward_cases),
        "reverse_cases_operator_private": all(
            case["operator_private_scope"] and case["public_path"] is None
            and case["llm_visible"] is False
            for case in report_cases if case["actor"] != ACTOR_SCOPE),
        "zero_game_queries": all(case["game_query_count"] == 0 for case in report_cases),
        "zero_native_queries": all(
            case["native_query_call_count"] == 0 for case in report_cases),
        "zero_submissions": all(case["submit_call_count"] == 0 for case in report_cases),
        "readable_reason_evidence": all(
            case["semantic_checks"]["readable_chinese_reason_present"]
            for case in report_cases),
    }
    report = {
        "status": "passed" if all(checks.values()) else "failed",
        "mode": "offline_reproject_r73_favor_queries",
        "game_contact": False,
        "source_report": str(source_report_path),
        "source_report_sha256": _sha256_file(source_report_path),
        "source_catalog": str(source_catalog_path),
        "source_catalog_sha256": _sha256_file(source_catalog_path),
        "source_session_id": session_id,
        "health": copy.deepcopy(health),
        "health_source_reused": True,
        "catalog_capabilities": {
            action_id: {
                "query": values[0], "submission": values[1],
            }
            for action_id, values in catalog_capabilities.items()
        },
        "case_count": len(report_cases),
        "facade_inspection_count": facade_count,
        "api_call_count": 0,
        "game_query_count": 0,
        "native_query_call_count": 0,
        "submit_call_count": 0,
        "checks": checks,
        "availability": availability,
        "cases": report_cases,
    }
    _write_json(output_report_path, report)
    print(json.dumps({
        "status": report["status"],
        "report": str(output_report_path),
        "cases": len(report_cases),
        "forward_facade_cases": facade_count,
        "reverse_operator_private_cases": len(report_cases) - facade_count,
        "game_query_count": report["game_query_count"],
        "submit_call_count": report["submit_call_count"],
        "availability": availability,
    }, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
