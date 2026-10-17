"""运行一次受限的 Rival 原生执行验收。

脚本要求游戏已经运行、加载观察 DLL，并处于暂停的 POR 上下文。脚本只对
``set_rival`` 或 ``remove_rival`` 执行一次提交：先做一次运行就绪/日期检查，
再读取执行前状态；只有原生 schema3 同时证明完整规则和当前动作可用时才会
调用执行接口。脚本最多轮询 20 秒，未知结果保留原状，不会重发请求、推进
日期、保存游戏或安装 DLL。

输出目录包含 ``report.json``、独立 SQLite journal 和有界的私有
``native-events-slice.jsonl``。原生 header、地址和线程字段只保留在私有日志
切片中，报告使用 bridge 的稳定语义结果。

示例::

    python work/run_rival_execution.py \
        --installation work/runtime/r34-rival-build/installation.json \
        --action-id set_rival --recipient BUR \
        --request-id r35_set_bur_001 --expected-date-raw 56500920
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal  # noqa: E402
from work.local_config import game_exe  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_alliance_execution import (  # noqa: E402
    _POLL_SECONDS,
    _copy_log_slice,
    _stable_result,
    _write_json,
)
from work.run_improve_relations_execution import _new_artifact  # noqa: E402
from work.run_royal_marriage_execution import (  # noqa: E402
    ExperimentStop,
    _installation_binding,
)


_ACTOR = "FRA"
_FAMILY = "rival"
_ACTIONS = ("set_rival", "remove_rival")
_PHASE = "initiate"
_TERMINAL_STATUSES = frozenset(("executed", "invalidated", "unknown"))
_TAG_RE = re.compile(r"[A-Z]{3}\Z")
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_NATIVE_QUERY_CAPABILITY = "native_rival_query"
_NATIVE_SUBMISSION_CAPABILITY = "native_rival_submission"


def _bool(value: object) -> bool:
    return type(value) is bool


def _int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _expected_transition(action_id: str) -> tuple[bool, bool]:
    if action_id == "set_rival":
        return False, True
    return True, False


def _inspect_checks(
    inspection: object,
    action_id: str,
    recipient: str,
    expected_date_raw: int,
    expected_active: bool,
    *,
    require_action_available: bool = True,
) -> dict[str, object]:
    """Validate the public schema3 pre/post inspection without native internals."""

    if not isinstance(inspection, dict):
        return {"inspection_object": False, "all": False}
    session = inspection.get("session")
    support = inspection.get("interface_support")
    legality = inspection.get("legality")
    authorization = inspection.get("authorization")
    relationship = inspection.get("relationship_state")
    components = inspection.get("native_rule_components")
    native = inspection
    active = native.get("rival_active")
    relationship_active = (
        relationship.get("rival_active") if isinstance(relationship, dict) else None
    )
    checks: dict[str, object] = {
        "inspection_object": True,
        "binding": all(inspection.get(field) == expected for field, expected in (
            ("action_id", action_id),
            ("family", _FAMILY),
            ("actor", _ACTOR),
            ("recipient", recipient),
            ("phase", _PHASE),
        )) and inspection.get("event") in (None, "native_rival_inspection"),
        "session_ready": (
            isinstance(session, dict)
            and session.get("status") == "ready"
            and session.get("complete") is True
        ),
        "date_matches": (
            inspection.get("date_raw", expected_date_raw) == expected_date_raw
            and isinstance(session, dict)
            and session.get("date_raw") == expected_date_raw
        ),
        "schema3": inspection.get("rules_schema") == 3,
        "full_rules_complete": inspection.get("full_rules_complete") is True,
        "native_action_available": (
            not require_action_available
            or inspection.get("native_action_available") is True
        ),
        "native_components_complete": (
            not require_action_available
            or (isinstance(components, dict) and components.get("complete") is True)
        ),
        "legality_available": (
            not require_action_available
            or (
                isinstance(legality, dict)
                and legality.get("status") == "available"
                and legality.get("complete") is True
            )
        ),
        "authorization_available": (
            not require_action_available
            or (
                isinstance(authorization, dict)
                and authorization.get("status") == "available"
                and authorization.get("complete") is True
            )
        ),
        "rival_state_complete": (
            isinstance(relationship, dict)
            and relationship.get("complete") is True
            and _bool(active)
            and relationship_active is active
        ),
        "expected_active": active is expected_active,
        "acceptance_not_applicable": (
            isinstance(inspection.get("acceptance"), dict)
            and inspection["acceptance"].get("applicability") == "not_applicable"
        ),
        "execute_adapter": (
            not require_action_available
            or (
                isinstance(support, dict)
                and support.get("execute") == _NATIVE_SUBMISSION_CAPABILITY
            )
        ),
        "action_available_required": (
            not require_action_available
            or inspection.get("native_action_available") is True
        ),
    }
    checks["all"] = all(value is True for value in checks.values())
    return checks


def _execution_checks(
    result: object,
    before: object,
    after: object,
    request_id: str,
    action_id: str,
    recipient: str,
    expected_date_raw: int,
) -> dict[str, object]:
    """Check the public consequence and its relation to before/after queries."""

    empty = {
        "terminal_executed": False,
        "binding": False,
        "proof": False,
        "transition": False,
        "count": False,
        "diplomatic_power": False,
        "before_query": False,
        "after_query": False,
        "all": False,
    }
    if not isinstance(result, dict):
        return empty
    public = result.get("result")
    if not isinstance(public, dict):
        return empty
    expected_before, expected_after = _expected_transition(action_id)
    binding = all(public.get(field) == expected for field, expected in (
        ("event", "native_rival_execution_result"),
        ("request_id", request_id),
        ("action_id", action_id),
        ("family", _FAMILY),
        ("actor", _ACTOR),
        ("recipient", recipient),
        ("phase", _PHASE),
        ("date_raw", expected_date_raw),
        ("status", "executed"),
    ))
    proof = all(public.get(field) is True for field in (
        "executed", "request_binding_verified", "native_rule_verified",
        "relationship_verified",
    ))
    transition = (
        public.get("before_active") is expected_before
        and public.get("after_active") is expected_after
    )
    before_count = public.get("rival_count_before")
    after_count = public.get("rival_count_after")
    count = (
        _int(before_count) and _int(after_count)
        and (after_count == before_count + 1
             if action_id == "set_rival"
             else after_count == before_count - 1)
    )
    before_dip = public.get("dip_before")
    after_dip = public.get("dip_after")
    cost = public.get("cost_raw")
    diplomatic_power = (
        _int(before_dip) and _int(after_dip) and _int(cost) and cost >= 0
        and (after_dip == before_dip if action_id == "set_rival"
             else before_dip - after_dip == cost)
    )

    def query_state(query: object, expected: bool) -> bool:
        if not isinstance(query, dict):
            return False
        relationship = query.get("relationship_state")
        active = query.get("rival_active")
        relationship_active = (
            relationship.get("rival_active")
            if isinstance(relationship, dict) else None
        )
        return (
            active is expected
            and relationship_active is expected
            and isinstance(relationship, dict)
            and relationship.get("complete") is True
        )

    before_query = query_state(before, expected_before)
    after_query = query_state(after, expected_after)
    checks = {
        "terminal_executed": (
            result.get("status") == "executed"
            and result.get("game_outcome") == "executed"
        ),
        "binding": binding,
        "proof": proof,
        "transition": transition,
        "count": count,
        "diplomatic_power": diplomatic_power,
        "before_query": before_query,
        "after_query": after_query,
    }
    checks["all"] = all(value is True for value in checks.values())
    checks["public_result"] = public
    return checks


def _poll_result(
    api: DiplomacyTools, request_id: str, timeout: float = 20.0
) -> dict[str, object]:
    """Read the journal repeatedly without ever calling execute again."""

    deadline = time.monotonic() + timeout
    calls = 0
    history: list[str] = []
    final: dict[str, object] | None = None
    while True:
        final_value = api.get_diplomatic_result(request_id)
        calls += 1
        final = final_value if isinstance(final_value, dict) else None
        status = final.get("status") if isinstance(final, dict) else None
        if isinstance(status, str) and (not history or history[-1] != status):
            history.append(status)
        if status in _TERMINAL_STATUSES:
            return {
                "calls": calls,
                "status_history": history,
                "terminal": True,
                "timed_out": False,
                "final": final,
            }
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {
                "calls": calls,
                "status_history": history,
                "terminal": False,
                "timed_out": True,
                "final": final,
            }
        time.sleep(min(0.25, remaining))


def _make_artifact(installation: Path, requested: Path | None) -> Path:
    if requested is not None:
        artifact = requested.expanduser().resolve()
        artifact.mkdir(parents=True, exist_ok=False)
        return artifact
    return _new_artifact(installation.parent, "rival-execution")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--action-id", choices=_ACTIONS, required=True)
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument(
        "--output", type=Path,
        help="可选的全新输出目录；省略时在 installation 同目录创建唯一目录",
    )
    args = parser.parse_args(argv)

    installation = args.installation.expanduser().resolve(strict=True)
    artifact = _make_artifact(installation, args.output)
    log_path = installation.parent / "control-probe.jsonl"
    journal_path = artifact / "diplomacy.sqlite3"
    report: dict[str, object] = {
        "status": "running",
        "mode": "rival_execution_once",
        "artifact": str(artifact),
        "installation": str(installation),
        "action_id": args.action_id,
        "family": _FAMILY,
        "actor": _ACTOR,
        "recipient": args.recipient,
        "phase": _PHASE,
        "parameters": {},
        "request_id": args.request_id,
        "expected_date_raw": args.expected_date_raw,
        "execute_call_count": 0,
        "resubmission_count": 0,
        "advance_requested": False,
        "save_requested": False,
        "installation_requested": False,
        "checks": {},
    }
    log_start: int | None = None
    try:
        if (
            not _TAG_RE.fullmatch(args.recipient)
            or args.recipient == _ACTOR
            or not _REQUEST_ID_RE.fullmatch(args.request_id)
            or not _int(args.expected_date_raw)
            or args.expected_date_raw < 0
        ):
            raise ExperimentStop("ARGUMENTS_INVALID", "recipient/request/date binding is invalid")
        report.update(_installation_binding(installation))
        session = ObserverSession(installation, game_exe())
        report["session"] = {
            "experiment_id": session.experiment_id,
            "session_id": session.session_id,
            "pid": session.record.get("pid"),
            "dll_sha256": session.record.get("dll_sha256"),
        }
        log_start = log_path.stat().st_size
        report["log_start_offset"] = log_start
        health = wait_runtime_ready(session, restore_minimized=False)
        capabilities = sorted(session.installation_capabilities())
        report["preflight"] = {"health": health, "capabilities": capabilities}
        preflight_checks = {
            "health_ready": health.get("status") == "ready" and health.get("complete") is True,
            "health_date_matches_expected": health.get("date_raw") == args.expected_date_raw,
            "native_rival_query_ack": _NATIVE_QUERY_CAPABILITY in capabilities,
            "native_rival_submission_ack": _NATIVE_SUBMISSION_CAPABILITY in capabilities,
        }
        report["preflight"]["checks"] = preflight_checks
        if not all(preflight_checks.values()):
            raise ExperimentStop("PREFLIGHT_NOT_READY", json.dumps(preflight_checks, ensure_ascii=False))

        with DurableJournal(
            journal_path, session.experiment_id, session.session_id,
            global_request_ids=True,
        ) as journal:
            api = DiplomacyTools(journal, session)
            before = api.inspect_diplomatic_action(
                args.action_id, _ACTOR, args.recipient,
                phase=_PHASE, parameters={},
            )
            expected_before, expected_after = _expected_transition(args.action_id)
            before_checks = _inspect_checks(
                before, args.action_id, args.recipient,
                args.expected_date_raw, expected_before,
            )
            report["before"] = {"inspection": before, "checks": before_checks}
            if before_checks.get("all") is not True:
                raise ExperimentStop("BEFORE_RIVAL_NOT_EXECUTABLE", json.dumps(before_checks, ensure_ascii=False))

            report["execute_call_count"] = 1
            execution = api.execute_diplomatic_action(
                args.request_id, args.action_id, _ACTOR, args.recipient,
                phase=_PHASE, parameters={},
            )
            report["execution_submission"] = execution
            poll = _poll_result(api, args.request_id, timeout=20.0)
            report["poll"] = poll
            final = poll.get("final")

            after = api.inspect_diplomatic_action(
                args.action_id, _ACTOR, args.recipient,
                phase=_PHASE, parameters={},
            )
            after_checks = _inspect_checks(
                after, args.action_id, args.recipient,
                args.expected_date_raw, expected_after,
                require_action_available=False,
            )
            report["after"] = {"inspection": after, "checks": after_checks}
            result_checks = _execution_checks(
                final, before, after, args.request_id, args.action_id,
                args.recipient, args.expected_date_raw,
            )
            report["result_checks"] = result_checks
            stable = _stable_result(final)

        with DurableJournal(
            journal_path, session.experiment_id, session.session_id,
            global_request_ids=True,
        ) as reopened:
            reopened_result = DiplomacyTools(reopened, session).get_diplomatic_result(
                args.request_id
            )
        report["reopened_result"] = reopened_result
        reopened_stable = _stable_result(reopened_result)
        report["persistence"] = {
            "same_public_result": stable == reopened_stable,
            "original": stable,
            "reopened": reopened_stable,
        }

        final_status = final.get("status") if isinstance(final, dict) else None
        report["checks"] = {
            "execute_called_once": report["execute_call_count"] == 1,
            "no_resubmission": report["resubmission_count"] == 0,
            "before_available_and_complete": before_checks.get("all") is True,
            "after_inspection_bound": all(
                after_checks.get(key) is True for key in (
                    "inspection_object", "binding", "session_ready", "date_matches",
                    "schema3", "full_rules_complete", "rival_state_complete",
                    "expected_active",
                )
            ),
            "after_relation_expected": after_checks.get("expected_active") is True,
            "journal_reopen_same_result": report["persistence"]["same_public_result"] is True,
            "terminal_status_observed": final_status in _TERMINAL_STATUSES,
            "executed_consequence_valid": result_checks.get("all") is True,
            "no_advance_save_install": (
                report["advance_requested"] is False
                and report["save_requested"] is False
                and report["installation_requested"] is False
            ),
        }
        if final_status == "executed" and result_checks.get("all") is True:
            report["status"] = (
                "passed" if all(value is True for value in report["checks"].values())
                else "failed"
            )
        elif final_status in ("invalidated", "unknown") or report.get("poll", {}).get("timed_out"):
            report["status"] = final_status if final_status in ("invalidated", "unknown") else "unknown"
        else:
            report["status"] = "failed"
    except ExperimentStop as error:
        report["status"] = "failed"
        report["error"] = {"code": error.code, "message": error.message}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {
            "code": "UNEXPECTED_OPERATOR_ERROR",
            "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        if log_start is not None:
            report["private_native_slice"] = _copy_log_slice(
                log_path, log_start, artifact / "native-events-slice.jsonl"
            )
        _write_json(artifact / "report.json", report)

    print(json.dumps({
        "status": report["status"],
        "artifact": str(artifact),
        "request_id": args.request_id,
        "execute_call_count": report["execute_call_count"],
    }, ensure_ascii=False), flush=True)
    if report["status"] == "passed":
        return 0
    if report["status"] in ("invalidated", "unknown"):
        return 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
