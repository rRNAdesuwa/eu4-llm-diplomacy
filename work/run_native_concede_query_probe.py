"""Operator-only read-only QUERY11 evidence, independent of public reducers."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = json.loads(args.installation.read_text(encoding="utf-8"))
    directory = args.installation.resolve().parent
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    control = output / "control-before.json"
    subprocess.run([sys.executable, "-B", "work/probe_control_state.py", "--pid",
                    str(record["pid"]), "--output", str(control)], check=True, timeout=30,
                   stdout=subprocess.DEVNULL)
    snapshot = json.loads(control.read_text(encoding="utf-8"))
    if snapshot.get("paused_flag") != 1 or snapshot.get("player_slot") != 189:
        raise RuntimeError("PAUSED_POR_REQUIRED")
    date = snapshot["date_raw"]
    log = directory / "control-probe.jsonl"
    initial = log.stat().st_size

    def query(action: str, suffix: str, protocol: str) -> dict:
        query_id = "r52_native_" + uuid.uuid4().hex
        expiry = time.time_ns() // 100 + 116444736000000000 + 300000000
        wire = (f"{protocol} {record['creation_filetime']:x} {query_id} {action} FRA ENG "
                f"{date} {expiry}{suffix}\n")
        temporary = directory / (query_id + ".tmp")
        target = directory / "diplomacy-query.request"
        start = log.stat().st_size
        with temporary.open("x", encoding="ascii", newline="\n") as stream:
            stream.write(wire)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.rename(target)
        (output / (query_id + "-wire.txt")).write_text(wire, encoding="ascii")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            available = log.stat().st_size - start
            if not 0 <= available <= 4 * 1024 * 1024:
                raise RuntimeError("NATIVE_LOG_SLICE_LIMIT")
            with log.open("rb") as stream:
                stream.seek(start)
                raw = stream.read(available)
            for line in raw.splitlines():
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                if (event.get("query_id") == query_id
                        and event.get("session_id") == record["session_id"]
                        and (event.get("event") == "native_peace_context_inspection"
                             or event.get("event", "").endswith("offer_inspection")
                             or event.get("event", "").endswith("failed"))):
                    return event
            time.sleep(0.1)
        raise RuntimeError("NATIVE_QUERY_OBSERVATION_TIMEOUT:" + query_id)

    report = {"private": True, "public_api": False, "business_submission": False,
              "date_raw": date, "session_id": record["session_id"], "cases": []}
    try:
        discovered = query("white_peace", "", "EU4DIP_QUERY1")
        report["discovery"] = discovered
        wars = discovered["wars"]
        if len(wars) != 1:
            raise RuntimeError("UNIQUE_WAR_REQUIRED")
        war_id = wars[0]["war_id"]
        definitions = [
            ("demand-c", "concede_defeat", "demand -1 - - c -"),
            ("offer-c", "concede_defeat", "offer -1 - - c -"),
            ("money-c", "demand_ducats", "demand 1000 - - mc -"),
            ("reparations-c", "war_reparations", "demand -1 - - rc -"),
            ("trade-c", "transfer_trade_power", "demand -1 - - tc UTR"),
            ("province-c", "cede_province", "demand -1 177 FRA pc -"),
        ]
        for name, action, selection in definitions:
            event = query(action, " " + war_id + " " + selection, "EU4DIP_QUERY11")
            report["cases"].append({"name": name, "event": event})
        report["status"] = "observed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "text": str(error)}
    available = log.stat().st_size - initial
    if 0 <= available <= 4 * 1024 * 1024:
        with log.open("rb") as stream:
            stream.seek(initial)
            (output / "native-events-slice.jsonl").write_bytes(stream.read(available))
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(output / "report.json")}, ensure_ascii=False))
    return 0 if report["status"] == "observed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
