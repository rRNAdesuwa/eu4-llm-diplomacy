"""Stream-check the rejected mixed offer against its final save fields."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work import verify_r67_ally_save as scan


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execution", type=Path, required=True)
    p.add_argument("--save-report", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    assert not args.output.exists(), "OUTPUT_EXISTS"
    execution = json.loads(args.execution.read_text(encoding="utf-8-sig"))
    saved = json.loads(args.save_report.read_text(encoding="utf-8-sig"))
    result = execution["steps"]["outbound"]["result"]
    native = result["result"]
    country = native["effects"]["country_terms"]["release_nation"]
    path = Path(saved["save"]["path"])
    source = scan.bounded.detect_container(path)
    scanner = scan.ProvinceScanner(row["province_id"] for row in country["province_rows"])
    with scan.bounded.open_gamestate(path, source) as stream:
        for line in stream:
            scanner.consume_line(line)
    provinces = scanner.finish()
    war = scan._war_summary(scan.scan_active_wars(path, source, "FRA", "BUR"))
    checks = {
        "native_ai_rejected": result["status"] == "rejected" and native["native_state"] == 1,
        "request_and_response_bound": native["request_binding_verified"] is True and native["response_verified"] is True,
        "correct_mixed_terms": native["term_mask"] == "mn" and native["amount_raw"] == 1000
            and native["release_nation_country"] == "PIC" and native["release_nation_source"] == "BUR",
        "native_territory_unchanged": country["unchanged"] is True,
        "no_ducats_settled": native["effects"]["money"]["paid_raw"] == 0,
        "province_scan_complete": not provinces["unknown"] and provinces["final_brace_depth"] == 0,
        "war_scan_complete": war["scan_complete"] is True,
        "war_still_active": war["matching_count"] == 1 and war["pair_currently_active"] is True,
        "original_attacker_FRA": war["original_attacker"] == "FRA",
        "original_defender_BUR": war["original_defender"] == "BUR",
        "original_goal_88": str(war["war_goal"]["province"]) == "88",
        "saved_paused_scene": saved["status"] == "success"
            and saved["save"]["inspection"]["date"] == "1455.11.13"
            and saved["save"]["inspection"]["player"] == "POR",
    }
    for row in country["province_rows"]:
        state = provinces["targets"][str(row["province_id"])]
        for field in ("owner", "controller"):
            checks[f"province_{row['province_id']}_{field}"] = (
                state["complete"] is True and state[field] == row[field + "_after"])
    report = {"status": "passed" if all(checks.values()) else "failed",
              "checks": checks, "request_id": result["request_id"],
              "execution": str(args.execution.resolve()), "save_report": str(args.save_report.resolve()),
              "save": saved["save"], "provinces": provinces, "war": war,
              "source_hash_recomputed": False, "dedicated_reload": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": checks}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
