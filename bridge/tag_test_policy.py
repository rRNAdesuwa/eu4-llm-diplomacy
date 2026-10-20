"""Cross-session development reservations and file-only rejection evidence.

Reservations are immutable. An unfinished reservation blocks its action until
the recorded native files prove normal rejection and closed cleanup. This
module never opens a process, sends a command, repairs files, or clears a stale
lock. Ordinary callers do not use this development policy.
"""
from pathlib import Path
import re

from bridge.tag_command_audit import recorded_snapshot
from bridge.tag_command_backend import (GAME_SHA, ROOT, decode, digest, encode, read,
                                       require, validate_command, validate_identity, write_new)

SCHEMA = "EU4TAG-DEVELOPMENT-ATTEMPT/1"
MAX_RECORDS = 4096
HISTORICAL_DISPATCH_POLICY = "work/reports/diplomacy-corrective-20261013-r2/historical-dispatch-exclusions.json"
HISTORICAL_DISPATCH_POLICY_SHA = "21f71454fbced52e9e5bea41654c40a996fa78e7ce9a0cdf3906624a5a9c743c"


def historical_dispatch_blocks(root=ROOT):
    """Verify the two additional cross-version dispatch exclusions, file-only."""
    root = Path(root).resolve()
    raw = read(root/HISTORICAL_DISPATCH_POLICY, 16384)
    require(digest(raw) == HISTORICAL_DISPATCH_POLICY_SHA,
            "Historical dispatch policy changed")
    policy = decode(raw)
    require(policy["schema"] == "EU4TAG-HISTORICAL-DISPATCH-EXCLUSIONS/1"
            and policy["game_sha256"] == GAME_SHA, "Historical dispatch policy identity")
    sources = {}
    for name, pin in policy["source_pins"].items():
        path = Path(name)
        require(not path.is_absolute() and ".." not in path.parts, "Historical dispatch source path")
        data = read(root/path, 2*1024*1024)
        require(len(data) == pin["bytes"] and digest(data) == pin["sha256"],
                "Historical dispatch evidence changed: " + name)
        sources[name] = data
    for record in policy["evidence"]:
        lines = sources[record["source"]].splitlines()
        claim = decode(lines[record["claim_line"]-1])
        result = decode(lines[record["result_line"]-1])
        require(claim["sequence"] == record["sequence"] == result["sequence"],
                "Historical dispatch sequence mismatch")
        for row in (claim, result):
            require(all(type(row.get(key)) is type(value) and row[key] == value
                        for key, value in record["identity"].items()),
                    "Historical dispatch process identity mismatch")
        if record.get("result_json_pointer") == "/record":
            result = result["record"]
        for row, expected in ((claim, record["claim_expected"]),
                              (result, record["result_expected"])):
            require(all(type(row.get(key)) is type(value) and row[key] == value
                        for key, value in expected.items()), "Historical dispatch receipt mismatch")
    blocked = set(policy["blocked_actions"])
    require(blocked == {record["action"] for record in policy["evidence"]},
            "Historical dispatch action mismatch")
    return blocked


def clean_rejection(result):
    """Only explicit, normal preview/gate rejection with closed ownership."""
    reason_status = {"full88_normal_false":2, "command_gate_normal_false":3}
    return (type(result) is dict
            and type(result.get("status")) is int
            and result.get("status") == reason_status.get(result.get("reason"), -1)
            and all(result.get(key) is True for key in ("known_cleanup_complete", "ownership_closed"))
            and all(result.get(key) is False for key in ("submitted", "submit_attempted",
                                                         "submit_returned", "submit_value", "slot_consumed"))
            and all(type(result.get(key)) is int and result[key] == 0
                    for key in ("owned_live", "quarantined", "adapter_fault",
                                "transfer_outcome", "submit_exception")))


class DevelopmentTestHistory:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()

    def _acquire(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        stat = self.directory.stat()
        require(not self.directory.is_symlink()
                and not getattr(stat, "st_file_attributes", 0)&0x400,
                "Linked development history directory")
        lock = self.directory/"test-policy.lock"
        write_new(lock,b"Development reservation mutex; uncertain writes require manual audit.\n")
        return lock

    def _records(self):
        records = []
        for path in self.directory.iterdir():
            if path.name == "test-policy.lock":
                continue
            require(re.fullmatch(r"attempt-[0-9a-f]{64}\.json", path.name),
                    "Unexpected development history entry")
            require(len(records) < MAX_RECORDS, "Development history record bound")
            record = decode(read(path, 16384))
            require(set(record) == {"schema", "game_sha256", "manifest", "identity", "command",
                                   "sequence", "audit_prefix_bytes", "audit_prefix_sha256"}
                    and record["schema"] == SCHEMA and record["game_sha256"] == GAME_SHA,
                    "Invalid development reservation")
            validate_identity(record["identity"])
            command = record["command"]
            require(type(command) is dict and type(command.get("action")) is str
                    and re.fullmatch(r"[a-z0-9_]{1,96}", command["action"]),
                    "Invalid reserved development action")
            validate_command(command, (command["action"],))
            require(path.name == "attempt-"+digest(command["request_id"].encode("ascii"))+".json"
                    and type(record["manifest"]) is str and Path(record["manifest"]).is_absolute()
                    and type(record["sequence"]) is int and 1 <= record["sequence"] <= 128
                    and type(record["audit_prefix_bytes"]) is int and 0 < record["audit_prefix_bytes"] <= 2*1024*1024
                    and type(record["audit_prefix_sha256"]) is str
                    and re.fullmatch(r"[0-9a-f]{64}", record["audit_prefix_sha256"]),
                    "Development reservation identity mismatch")
            records.append(record)
        return records

    @staticmethod
    def _proven_rejection(record):
        try:
            snapshot = recorded_snapshot(record["manifest"],record["identity"])
            require(snapshot.raw == snapshot.complete, "Partial development audit tail")
            require(not (snapshot.directory/"publisher.lock").exists(), "Uncertain development publisher")
            prefix = record["audit_prefix_bytes"]
            require(len(snapshot.raw) >= prefix and digest(snapshot.raw[:prefix]) == record["audit_prefix_sha256"],
                    "Development audit prefix changed")
            result = snapshot.status(record["command"]["request_id"])
            require(result["command"] == record["command"] and result["sequence"] == record["sequence"]
                    and result["state"] == "native_rejected" and result["binding"] is not None
                    and clean_rejection(result["native_result"]), "Development rejection is not proven clean")
            selected = [row for row in snapshot.rows if row["sequence"] == record["sequence"]]
            require(not any(row["event"] == "dispatch_intent" for row in selected),
                    "Development attempt reached dispatch intent")
            calls = [row for row in selected if row["event"] in ("native_call_begin", "native_call_return")]
            expected = ([0,1,2,5] if result["native_result"]["reason"] == "full88_normal_false"
                        else [0,1,2,3,4,5,6])
            require(type(result["native_result"].get("adapter_call_attempts")) is int
                    and result["native_result"]["adapter_call_attempts"] == len(expected)
                    and len(calls) == 2*len(expected), "Incomplete development native calls")
            for index, call in enumerate(expected):
                begin, returned = calls[2*index:2*index+2]
                require(begin["event"] == "native_call_begin" and begin.get("call") == call
                        and returned["event"] == "native_call_return" and returned.get("call") == call
                        and returned.get("normal") is True
                        and type(returned.get("exception")) is int and returned["exception"] == 0,
                        "Unproven development native cleanup")
            rejecting_call = 2 if result["native_result"]["reason"] == "full88_normal_false" else 4
            require(next(row for row in calls if row["event"] == "native_call_return"
                         and row["call"] == rejecting_call).get("boolean") is False,
                    "Missing normal false rejection")
            return True
        except (OSError,ValueError,KeyError,TypeError,UnicodeError,StopIteration):
            # Missing, changing, incomplete or contradictory evidence cannot
            # authorize another attempt. Do not manufacture a native status.
            return False

    def _check(self, commands, records):
        ids = {command["request_id"] for command in commands}
        actions = {command["action"] for command in commands}
        require(not ids & {record["command"]["request_id"] for record in records},
                "Development request_id already reserved: test forbidden")
        for record in records:
            action = record["command"]["action"]
            if action in actions:
                require(self._proven_rejection(record),
                        "Development action reserved, dispatched or uncertain: test forbidden: "+action)

    def check(self, commands):
        lock = self._acquire()
        try:
            self._check(commands,self._records())
        finally:
            lock.unlink()

    def reserve(self, manifest, identity, commands, first, *, on_progress):
        lock = self._acquire()
        preserve_lock = writing = False
        try:
            records = self._records()
            self._check(commands,records)
            require(len(records)+len(commands) <= MAX_RECORDS, "Development history record bound")
            snapshot = recorded_snapshot(manifest,identity)
            require(snapshot.raw == snapshot.complete and snapshot.summary["hook_installed"]
                    and not snapshot.summary["terminal"], "Development session audit is not ready")
            for index,command in enumerate(commands):
                record = {"schema":SCHEMA, "game_sha256":GAME_SHA,
                          "manifest":str(Path(manifest).resolve()), "identity":dict(identity),
                          "command":dict(command), "sequence":first+index,
                          "audit_prefix_bytes":len(snapshot.raw), "audit_prefix_sha256":digest(snapshot.raw)}
                packet = encode(record)
                writing = True
                on_progress(index,False)
                write_new(self.directory/("attempt-"+digest(command["request_id"].encode("ascii"))+".json"),packet)
                on_progress(index,True)
            writing = False
        except BaseException:
            preserve_lock = writing
            raise
        finally:
            if not preserve_lock:
                lock.unlink()
