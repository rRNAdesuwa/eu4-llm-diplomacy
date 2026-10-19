"""Offline review of preserved v10 sequence13; optional isolated file-lock fixture.

No game processes, native callbacks, runtime directory writes, or publications.
The synthetic fixture creates/removes only its own temporary candidate directory.
"""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes as W
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work.native import lab_protocol_v10_1375 as lab

SESSION = ROOT / "work/runtime/native1375-v10/session-46408-01dd568ed7034bcb"
REQUEST_SHA = "3bc64afefcd9576c17d9eb55103bf2a2be6d843465c7b67c86ac847fc00905f0"


def isolated_sharing_fixture():
    if os.name != "nt":
        raise ValueError("Windows file semantics fixture requires Windows")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, ctypes.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.CloseHandle.restype = W.BOOL
    invalid = ctypes.c_void_p(-1).value
    parent = ROOT / "work/candidates/mailbox-consume-review-1375"
    with tempfile.TemporaryDirectory(prefix="sharing-fixture-", dir=parent) as temporary:
        path = Path(temporary) / "synthetic-input.txt"
        path.write_bytes(b"synthetic-only\n")
        # This handle permits all sharing; the native consumer's share0 still
        # denies an existing read-access handle, so compatibility is reciprocal.
        reader = kernel.CreateFileW(str(path), 0x80000000, 7, None, 3, 0x80, None)
        if reader == invalid:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            attempted = kernel.CreateFileW(str(path), 0x80010000, 0, None, 3, 0x00200080, None)
            blocked_error = ctypes.get_last_error() if attempted == invalid else 0
            if attempted != invalid:
                kernel.CloseHandle(attempted)
            if blocked_error != 32:
                raise AssertionError(f"Expected ERROR_SHARING_VIOLATION32, got {blocked_error}")
        finally:
            if not kernel.CloseHandle(reader):
                raise ctypes.WinError(ctypes.get_last_error())
        reopened = kernel.CreateFileW(str(path), 0x80010000, 0, None, 3, 0x00200080, None)
        reopen_error = ctypes.get_last_error() if reopened == invalid else 0
        if reopened == invalid:
            raise ctypes.WinError(reopen_error)
        if not kernel.CloseHandle(reopened):
            raise ctypes.WinError(ctypes.get_last_error())
        return {"scope": "synthetic isolated file only", "request_content_unchanged": path.read_bytes() == b"synthetic-only\n",
                "reader_share_mask": 7, "consumer_share_mask": 0, "blocked_win32_error": blocked_error,
                "same_file_open_after_reader_closed": True, "reproduces_actual_incident": False,
                "game_process_access": False, "runtime_artifacts_written": False}


def review():
    names = ["session.json", "00000000000000000013.request", "00000000000000000013.host-intent",
             "00000000000000000013.publisher-output.txt", "00000000000000000013.supervisor.jsonl", "research-1375.jsonl"]
    raw, inputs = {}, []
    for name in names:
        path = SESSION / name
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Bounded input exceeded")
        value = path.read_bytes()
        raw[name] = value
        info = path.stat()
        inputs.append({"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(value).hexdigest(),
                       "bytes": len(value), "mtime_ns": info.st_mtime_ns,
                       "mtime_utc": datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat()})
    request = raw[names[1]]
    if hashlib.sha256(request).hexdigest() != REQUEST_SHA:
        raise ValueError("Preserved request differs")
    decoded = lab.decode_request(request)
    intent = json.loads(raw[names[2]])
    publisher = json.loads(raw[names[3]])
    events = [json.loads(line) for line in raw["research-1375.jsonl"].splitlines()]
    frames = [e for e in events if e.get("event") == "research_frame"]
    frozen = [e for e in events if e.get("event") == "lab_session_frozen"]
    if not (intent["body_ascii"].encode() == request and intent["request_sha256"] == REQUEST_SHA
            and publisher["publication"]["request_sha256"] == REQUEST_SHA
            and decoded["pid"] == 46408 and decoded["creation"] == "01dd568ed7034bcb"
            and decoded["sequence"] == 13 and frames[-1]["last_sequence"] == 12
            and len(frozen) == 1 and frozen[0]["sequence"] == 12):
        raise ValueError("Incident identity/evidence mismatch")
    claim_present = (SESSION / "00000000000000000013.claim").exists()
    claimed_events = [e for e in events if e.get("event") == "lab_request_claimed" and e.get("sequence") == 13]
    return {"schema_version": 1, "analysis_kind": "offline_incident_review", "inputs": inputs,
            "request": decoded, "python_parser_accepted": True, "intent_and_publication_exact_match": True,
            "claim_present": claim_present, "native_seq13_claimed_events": len(claimed_events),
            "last_frame": frames[-1], "freeze": frozen[0],
            "timing": {"last_frame_uptime_ms": frames[-1]["uptime_ms"], "request_expiry_ms": decoded["expires"],
                       "publisher_requested_ttl_ms": 5000, "inferred_request_construction_uptime_ms": decoded["expires"] - 5000,
                       "native_consume_failure_uptime_recorded": False, "native_error_stage_recorded": False,
                       "exact_native_ttl_predicate_reconstructable": False},
            "conclusion": "Actual failure stage/root cause is unknown. Preserved bytes parse; no claim/effect boundary was logged. Transient exclusive-open sharing failure is feasible, not proven.",
            "game_process_access": False, "request_republished": False, "runtime_artifacts_modified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sharing-fixture", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "work/reports/mailbox-consume-incident-46408-13.json")
    args = parser.parse_args()
    result = review()
    if args.sharing_fixture:
        result["isolated_sharing_fixture"] = isolated_sharing_fixture()
    output = (json.dumps(result, indent=2, ensure_ascii=False) + "\n").encode()
    args.output.write_bytes(output)
    print(json.dumps({"path": str(args.output), "sha256": hashlib.sha256(output).hexdigest(),
                      "python_parser_accepted": True, "claim_present": result["claim_present"],
                      "actual_failure_cause_known": False, "sharing_fixture": result.get("isolated_sharing_fixture")}))


if __name__ == "__main__":
    main()
