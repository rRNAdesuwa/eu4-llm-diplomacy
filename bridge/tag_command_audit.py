"""Bounded, file-only receipts. This module cannot load or send game commands.

Historical receipts remain readable after working sources change. Runnable
backends still verify every source pin before loading or publishing.
"""
from pathlib import Path
import re

from bridge.tag_command_backend import (ACTIONS, GAME_SHA, PURPOSE, SCHEMA,
    decode, digest, read, require, validate_command, validate_identity, wire)


class AuditSnapshot:
    def __init__(self, directory, identity, *, purpose, actions, limit):
        self.directory = Path(directory)
        self.identity = validate_identity(identity)
        self.purpose, self.actions, self.limit = purpose, tuple(actions), limit
        self.raw = read(self.directory / "events.jsonl", 2 * 1024 * 1024)
        self.complete = self.raw[:self.raw.rfind(b"\n") + 1]
        self.rows = [decode(line) for line in self.complete.splitlines()]
        require(1 <= len(self.rows) <= 4096 and self.rows[0].get("event") == "bootstrap_verified",
                "Missing bootstrap audit")
        owner = self.rows[0]["owner_thread"]
        require(type(owner) is int and owner > 0, "Invalid audit owner")
        for ordinal, row in enumerate(self.rows, 1):
            require(row.get("schema") == SCHEMA and row.get("ordinal") == ordinal
                    and all(row.get(k) == v for k, v in self.identity.items())
                    and row.get("production_ready") is False and row.get("no_send") is False,
                    "Audit identity/order mismatch")
            require(type(row.get("sequence")) is int and 0 <= row["sequence"] <= limit,
                    "Audit sequence bound")
            if row["sequence"]:
                require(row.get("thread") == owner and row.get("owner_thread") == owner,
                        "Non-owner native audit")
        terminals = [i for i, row in enumerate(self.rows) if row["event"] == "terminal"]
        require(not terminals or terminals == [len(self.rows) - 1], "Audit continued after terminal")
        self.summary = {
            "identity": dict(self.identity), "terminal": bool(terminals),
            "hook_installed": any(r["event"] == "hook_installed" for r in self.rows),
            "owner_thread": owner, "audit_sha256": digest(self.complete),
            "gameplay_effects_verified": False,
        }

    def status(self, request_id=None):
        result = dict(self.summary)
        if request_id is None:
            result["results"] = [r for r in self.rows if r["event"] == "request_result"]
            return result
        require(type(request_id) is str and re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", request_id),
                "Invalid request_id")
        intent_path = self.directory / ("key-" + digest(request_id.encode("ascii")) + ".json")
        intent = decode(read(intent_path, 8192))
        command = validate_command(intent["command"], self.actions)
        require(intent["identity"] == self.identity and command["request_id"] == request_id,
                "Request intent mismatch")
        seq = intent["sequence"]
        require(type(seq) is int and 1 <= seq <= self.limit, "Intent sequence bound")
        expected = wire(self.identity, seq, intent["expires"], command, purpose=self.purpose,
                        actions=self.actions, limit=self.limit)
        require(intent.get("wire_sha256") == digest(expected), "Intent wire mismatch")
        selected = [r for r in self.rows if r["sequence"] == seq]
        claimed = [r for r in selected if r["event"] == "request_claimed"]
        outcome = [r for r in selected if r["event"] == "request_result"]
        bound = [r for r in selected if r["event"] == "pair_bound"]
        require(len(claimed) <= 1 and len(outcome) <= 1 and len(bound) <= 1,
                "Duplicate native attempt")
        require(not (outcome or bound) or claimed, "Native result without claim")
        request_path = self.directory / f"{seq}.request"
        if request_path.exists():
            require(read(request_path, 1024) == expected, "Published request changed")
        if claimed:
            row = claimed[0]
            require(all(row[k] == command[k] for k in ("action", "actor", "target"))
                    and row["expires"] == intent["expires"], "Claim changed command")
            require(read(self.directory / f"{seq}.claim", 1024) == expected
                    and read(request_path, 1024) == expected, "Claim/request mismatch")
        if bound:
            row = bound[0]
            for field, tag in (("actor_handle", command["actor"]), ("target_handle", command["target"])):
                require(row[field] & 0xffffff == int.from_bytes(tag.encode("ascii"), "little"),
                        "Resolved TAG mismatch")
            require(row["actor_is_human_player"] == (row["actor_handle"] == row["human_player_handle"]),
                    "Wrong actor identity receipt")
        state = "claimed" if claimed else "published" if request_path.exists() else "publication_unknown"
        if outcome:
            row = outcome[0]
            require(type(row.get("submitted")) is bool and type(row.get("status")) is int
                    and 0 <= row["status"] <= 5, "Invalid native result state")
            if row["submitted"]:
                sends = [r for r in selected if r["event"] == "native_call_return" and r["call"] == 7]
                require(len(sends) == 1 and bound and any(r["event"] == "dispatch_intent" for r in selected)
                        and row["status"] == 4 and row["reason"] == "normal_dispatch_slot_consumed"
                        and row["ownership_closed"] and row["owned_live"] == row["quarantined"] == row["adapter_fault"] == 0
                        and all(sends[0][k] is True for k in ("normal", "boolean", "slot_consumed"))
                        and sends[0]["exception"] == 0, "Unproven native dispatch")
                state = "dispatched"
            else:
                state = "unknown_no_retry" if row["status"] == 5 else "native_rejected"
        elif self.summary["terminal"]:
            state = "unknown_no_retry" if any(r["event"] == "native_call_begin" for r in selected) else "not_dispatched"
        result.update(command=command, sequence=seq, state=state,
                      binding=bound[0] if bound else None, native_result=outcome[0] if outcome else None)
        return result


def recorded_snapshot(manifest_path, identity):
    """Validate recorded manifest/DLL identity without current source pins.

    No runtime adapter is constructed; the result has no load/publish methods.
    This is evidence inspection, never permission to execute an old build.
    """
    identity = validate_identity(identity)
    manifest_path = Path(manifest_path).resolve()
    raw = read(manifest_path, 1024 * 1024)
    require(digest(raw) == identity["manifest_sha256"], "Recorded manifest mismatch")
    manifest = decode(raw)
    purpose = manifest["purpose"]
    require(manifest["schema"] == "EU4TAGBUILD/1" and purpose in (PURPOSE, "tag_command_1375_v31")
            and manifest["game_sha256"] == GAME_SHA and manifest["no_send"] is False,
            "Wrong recorded native host")
    require(Path(manifest["DLL"]).name == manifest["DLL"], "DLL path must be a basename")
    dll = read(manifest_path.parent / manifest["DLL"], 16 * 1024 * 1024)
    require(manifest["dll"] == {"bytes": len(dll), "sha256": digest(dll)}
            and digest(dll) == identity["dll_sha256"], "Recorded DLL mismatch")
    actions = tuple(manifest["actions"]) if purpose != PURPOSE else ACTIONS
    require(1 <= len(actions) <= 128 and len(set(actions)) == len(actions), "Recorded action registry bound")
    for action in actions:
        require(type(action) is str and re.fullmatch(r"[a-z0-9_]{1,96}", action), "Invalid recorded action")
    prefix, limit = ("tagcommand30", 64) if purpose == PURPOSE else ("tagcommand31", 128)
    directory = manifest_path.parent / f"{prefix}-{identity['pid']}-{identity['creation']}-{identity['session']}"
    return AuditSnapshot(directory, identity, purpose=purpose, actions=actions, limit=limit)
