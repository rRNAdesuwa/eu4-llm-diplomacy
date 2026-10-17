#!/usr/bin/env python3
"""Reproduce the bounded C-round Military Access source/hold validation.

The script reads the existing C-round JSON and JSONL evidence only.  It
recomputes the GEN fixture hold checks from raw events and calls the shared
inbound source validator for the natural CAS response.  It never connects to
the game, publishes a query or action, advances time, or writes into an
existing evidence directory.  Every JSONL input is processed line by line and
all input files are limited to 10 MiB.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

WORK = Path(__file__).resolve().parent
ROOT = WORK.parent
if str(WORK) not in sys.path:
    sys.path.insert(0, str(WORK))

from validate_royal_inbound_source import validate as validate_inbound_source  # noqa: E402


MAX_INPUT_BYTES = 10 * 1024 * 1024
CHUNK_BYTES = 64 * 1024
DEFAULT_RUNTIME = ROOT / "work" / "runtime" / "diplomacy-query-20261015-r32-military-access-c-direction-reload"


def read_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"JSON_INPUT_TOO_LARGE:{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_NOT_OBJECT:{path}")
    return value


def digest(path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    if size > MAX_INPUT_BYTES:
        raise ValueError(f"INPUT_TOO_LARGE:{path}")
    sha = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            sha.update(chunk)
    return {
        "path": str(path.resolve()),
        "bytes": total,
        "sha256": sha.hexdigest(),
        "bounded": True,
    }


def stream_jsonl(path: Path, names: set[str]) -> dict[str, Any]:
    selected: dict[str, list[dict[str, Any]]] = {name: [] for name in names}
    counts: dict[str, int] = {}
    malformed: list[int] = []
    lines = 0
    with path.open("r", encoding="utf-8") as stream:
        for line_number, raw_line in enumerate(stream, 1):
            lines += 1
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                malformed.append(line_number)
                continue
            if not isinstance(event, dict):
                malformed.append(line_number)
                continue
            name = event.get("event")
            counts[name] = counts.get(name, 0) + 1
            if name in selected:
                selected[name].append({**event, "_line": line_number})
    return {
        "line_count": lines,
        "malformed_lines": malformed,
        "event_counts": counts,
        "selected": selected,
    }


def all_true(values: list[bool]) -> bool:
    return bool(values) and all(value is True for value in values)


def same_pending(records: list[dict[str, Any]], proposal: int,
                 token: int, actor: str) -> bool:
    return bool(records) and all(
        event.get("proposal_id") == proposal
        and event.get("token3c") == token
        and event.get("decision_country") == "FRA"
        and event.get("actor", actor) == actor
        for event in records
    )


def automatic_state_entries(events: list[dict[str, Any]], actor: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for event in events:
        if event.get("actor_field") != actor and event.get("actor") != actor:
            continue
        source = event.get("source") if isinstance(event.get("source"), dict) else {}
        payload = source.get("payload") if isinstance(source.get("payload"), dict) else source
        if payload.get("state34") in (1, 2):
            result.append(event)
    return result


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    runtime = args.runtime_root.expanduser().resolve(strict=True)
    output = args.output_dir.expanduser().resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {output}")

    gen_prep = runtime / "military-access-inbound-preparation-d4542e0e162b466cac24c353ef011c13"
    gen_late = runtime / "inbound-response-6db77d4280fb4234bcf1b7b53d784f8d"
    observation = runtime / "lifecycle-observation-e8af4ca6ea7b49dfbd749c42f14653b0"
    cas_response = runtime / "inbound-response-462a74fd7d134c578e83b2fd056ecf6a"
    paths = {
        "gen_preparation_report": gen_prep / "report.json",
        "gen_preparation_native": gen_prep / "native-events.jsonl",
        "gen_late_report": gen_late / "report.json",
        "gen_late_native": gen_late / "native-events.jsonl",
        "observation_report": observation / "observation-report.json",
        "observation_events": observation / "observed-events.jsonl",
        "cas_response_report": cas_response / "report.json",
        "cas_response_native": cas_response / "native-events.jsonl",
        "cas_control_probe": runtime / "control-probe.jsonl",
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)

    output.mkdir(parents=True)
    try:
        records = {name: digest(path) for name, path in paths.items()}
        prep_report = read_json(paths["gen_preparation_report"])
        late_report = read_json(paths["gen_late_report"])
        observation_report = read_json(paths["observation_report"])
        cas_report = read_json(paths["cas_response_report"])

        prep_scan = stream_jsonl(paths["gen_preparation_native"], {
            "native_alliance_inbound_test_submitted",
            "native_alliance_inbound_offer",
            "native_alliance_inbound_inspection",
        })
        late_scan = stream_jsonl(paths["gen_late_native"], {
            "native_alliance_inbound_inspection",
            "native_alliance_submission_result",
            "native_diplomacy_relation_response_result",
            "native_alliance_response_result",
        })
        observation_scan = stream_jsonl(paths["observation_events"], {
            "native_alliance_inbound_offer",
            "native_diplomacy_inbound_ai_choice_held",
            "native_alliance_command_entry_observed",
        })
        cas_scan = stream_jsonl(paths["cas_response_native"], {
            "native_alliance_submission_result",
            "native_diplomacy_relation_response_result",
            "native_alliance_response_result",
        })

        prep_tests = prep_scan["selected"]["native_alliance_inbound_test_submitted"]
        gen_offers = prep_scan["selected"]["native_alliance_inbound_offer"]
        obs_offers = observation_scan["selected"]["native_alliance_inbound_offer"]
        holds = observation_scan["selected"]["native_diplomacy_inbound_ai_choice_held"]
        gen_holds = [event for event in holds if event.get("proposal_id") == 2 and event.get("token3c") == 9]
        cas_holds = [event for event in holds if event.get("proposal_id") == 3 and event.get("token3c") == 10]
        cas_offers = [event for event in obs_offers if event.get("actor") == "CAS" and event.get("recipient") == "FRA"]
        command_entries = observation_scan["selected"]["native_alliance_command_entry_observed"]
        gen_auto_entries = automatic_state_entries(command_entries, "GEN")
        late_inspections = late_scan["selected"]["native_alliance_inbound_inspection"]
        late_submissions = late_scan["selected"]["native_alliance_submission_result"]
        late_responses = (
            late_scan["selected"]["native_diplomacy_relation_response_result"]
            + late_scan["selected"]["native_alliance_response_result"]
        )
        cas_submissions = cas_scan["selected"]["native_alliance_submission_result"]
        cas_responses = (
            cas_scan["selected"]["native_diplomacy_relation_response_result"]
            + cas_scan["selected"]["native_alliance_response_result"]
        )

        # Recompute the complete CAS source chain through the shared validator.
        cas_result = validate_inbound_source(
            cas_response,
            paths["cas_control_probe"],
            "accepted",
            "r32c_accept_cas_access_001",
            family="military_access",
            action_id="ask_military_access",
            source_actor="CAS",
            recipient="FRA",
            source_tag="CAS_NATURAL_TO_FRA",
            source_kind="natural_native",
            response_event="native_diplomacy_relation_response_result",
            observation=observation,
        )

        sessions = {
            event.get("session_id")
            for group in (
                prep_tests, gen_offers, gen_holds, cas_offers, cas_holds,
                late_inspections, cas_submissions, cas_responses,
            )
            for event in group
            if isinstance(event.get("session_id"), str)
        }
        checks: dict[str, bool] = {
            "all_inputs_exist_and_bounded": all(item["bounded"] for item in records.values()),
            "all_input_jsonl_well_formed": all(
                not scan["malformed_lines"]
                for scan in (prep_scan, late_scan, observation_scan, cas_scan)
            ),
            "single_session_across_c_evidence": sessions == {"12860-1dd5ca7b28c9d9f"},
            "gen_preparation_passed": prep_report.get("status") == "passed",
            "gen_fixture_submission_identified": (
                len(prep_tests) == 1 and prep_tests[0].get("source") == "GEN"
                and prep_tests[0].get("recipient") == "FRA"
                and prep_tests[0].get("submitted") is True
            ),
            "gen_initial_offer_tuple": (
                len(gen_offers) == 1 and all(
                    gen_offers[0].get(field) == value
                    for field, value in {
                        "actor": "GEN", "mirror": "GEN", "recipient": "FRA",
                        "family": "military_access", "extra60": 0,
                        "proposal_id": 2, "token3c": 9, "state34": 0,
                        "variant38": 1, "date28": 56464752,
                    }.items()
                )
            ),
            "gen_three_distinct_hold_dates": sorted({event.get("date_raw") for event in gen_holds}) == [56464776, 56464800, 56464824],
            "gen_hold_same_pending_identity": same_pending(gen_holds, 2, 9, "GEN"),
            "gen_hold_queue_verified_and_ai_skipped": all_true([
                event.get("native_queue_verified") is True
                and event.get("native_ai_choice_skipped") is True
                for event in gen_holds
            ]),
            "gen_no_automatic_state1_or2": not gen_auto_entries,
            "gen_observation_reached_paused_date": (
                observation_report.get("status") == "observed"
                and observation_report.get("paused_after") is True
                and observation_report.get("date_raw_after") == 56464872
            ),
            "gen_late_check_pending_not_active": (
                bool(late_inspections) and all(
                    event.get("reason") == "PENDING_NOT_ACTIVE"
                    and event.get("native_validity") is False
                    and event.get("response_rules_complete") is False
                    for event in late_inspections
                )
            ),
            "gen_late_request_not_submitted": (
                late_report.get("execution", {}).get("submitted") is False
                and late_report.get("persisted", {}).get("submitted") is False
            ),
            "gen_late_has_no_native_response": not late_submissions and not late_responses,
            "gen_business_outcome_not_claimed": (
                late_report.get("execution", {}).get("game_outcome") == "unknown"
                and not late_responses
            ),
            "cas_natural_offer_tuple": (
                len(cas_offers) == 1 and all(
                    cas_offers[0].get(field) == value
                    for field, value in {
                        "actor": "CAS", "mirror": "CAS", "recipient": "FRA",
                        "family": "military_access", "extra60": 0,
                        "proposal_id": 3, "token3c": 10, "state34": 0,
                        "variant38": 1, "date28": 56464824,
                    }.items()
                )
            ),
            "cas_two_distinct_hold_dates": sorted({event.get("date_raw") for event in cas_holds}) == [56464848, 56464872],
            "cas_hold_same_pending_identity": same_pending(cas_holds, 3, 10, "CAS"),
            "cas_hold_queue_verified_and_ai_skipped": all_true([
                event.get("native_queue_verified") is True
                and event.get("native_ai_choice_skipped") is True
                for event in cas_holds
            ]),
            "cas_response_submitted_once": (
                len(cas_submissions) == 1
                and cas_submissions[0].get("request_id") == "r32c_accept_cas_access_001"
                and cas_submissions[0].get("submitted") is True
            ),
            "cas_native_response_verified": (
                len(cas_responses) == 1 and all(
                    cas_responses[0].get(field) == value
                    for field, value in {
                        "outcome": "accepted", "native_state": 2,
                        "native_variant": 1, "military_access_before": False,
                        "military_access_after": True, "pending_removed": True,
                        "response_verified": True, "request_binding_verified": True,
                    }.items()
                )
            ),
            "cas_source_validator_passed_46": (
                cas_result.get("summary", {}).get("validation_passed") is True
                and cas_result.get("summary", {}).get("total_checks") == 46
                and cas_result.get("summary", {}).get("passed_checks") == 46
            ),
        }
        selected = {
            "gen": {
                "fixture_submission": prep_tests,
                "initial_offer": gen_offers,
                "hold_records": gen_holds,
                "late_inspections": late_inspections,
                "automatic_state1_or2_entries": gen_auto_entries,
            },
            "cas": {
                "natural_offer": cas_offers,
                "hold_records": cas_holds,
                "submission": cas_submissions,
                "response": cas_responses,
            },
        }
        summary = {
            "total_checks": len(checks),
            "passed_checks": sum(value is True for value in checks.values()),
            "failed_checks": sum(value is not True for value in checks.values()),
        }
        report = {
            "validator": "validate_military_access_c_source_hold.py",
            "read_only": True,
            "replay": False,
            "status": "passed" if summary["failed_checks"] == 0 else "failed",
            "runtime_root": str(runtime),
            "session": "12860-1dd5ca7b28c9d9f",
            "conclusion": {
                "gen": "fixture proposal held on three dates; late check was PENDING_NOT_ACTIVE and no response was submitted; outcome remains unclassified",
                "cas": "natural proposal held on two dates; one interface accept request produced verified false_to_true relation transition and pending removal",
            },
            "checks": checks,
            "summary": summary,
            "inputs": records,
            "selected_records": selected,
            "cas_source_validation": {
                "summary": cas_result.get("summary"),
                "source_context": cas_result.get("source_context"),
                "request_binding": cas_result.get("request_binding"),
            },
        }
        write_json(output / "validation.json", report)
        markdown = [
            "# C 轮军事通行权来源与跨日保持综合独立验证",
            "",
            f"验收状态：{'通过' if report['status'] == 'passed' else '失败'}（{summary['passed_checks']}/{summary['total_checks']} 项）。本脚本只读现有 JSON/JSONL 证据，没有连接游戏，也没有重新查询、执行、推进或保存。",
            "",
            "## GEN→FRA：测试提议三天保持后的迟到检查",
            "",
            "GEN 测试提议为 proposal 2/token 9。raw 56464776、56464800、56464824 三次 hold 均保持队列验证和跳过 AI 选择；观察到 raw 56464872 后，迟到检查为 PENDING_NOT_ACTIVE，submitted=false，且没有 native submission/response。消费请求的 invalidated 状态不被解释为提议已过期、接受或拒绝。",
            "",
            "## CAS→FRA：自然提议两天保持后的接受",
            "",
            "CAS 自然提议为 proposal 3/token 10，未使用 TEST_ONLY 来源。raw 56464848 和 56464872 两次 hold 后，唯一请求 r32c_accept_cas_access_001 产生 native state=2、variant=1、false→true、pending_removed=true；共享来源校验器 46/46 通过。",
            "",
            "## 可复现输入",
            "",
            f"- 运行目录：`{runtime}`",
            f"- JSON 报告：`{(output / 'validation.json').resolve()}`",
            "- 输入 JSONL 全部按行流式读取；每个输入文件限制为 10 MiB，并在 JSON 报告中记录字节数、SHA-256、行数和解析错误。",
        ]
        (output / "report.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
        print(json.dumps({
            "status": report["status"],
            "summary": summary,
            "json": str((output / "validation.json").resolve()),
            "markdown": str((output / "report.md").resolve()),
        }, ensure_ascii=False))
        return 0 if report["status"] == "passed" else 2
    except Exception:
        # Preserve a clear failed artifact without overwriting any evidence.
        if not (output / "report.json").exists():
            (output / "error.json").write_text(
                json.dumps({"status": "failed"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
