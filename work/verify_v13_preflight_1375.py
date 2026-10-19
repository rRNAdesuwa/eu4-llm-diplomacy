"""Fixed, offline v13 preflight review: 20 / 1 / 72 / 72, never diplomacy.

prepare inventories an explicitly preserved session prefix and diagnostic files.
review replays that immutable inventory into the frozen four phase validators.
Neither command opens a process, publishes a marker, or calls a native function.
The whole v13 DLL contains a sender; only this reviewed prefix is no-send.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy_api import decode_json
from work.native import lab_protocol_v13_1375 as lab
from tools import verify_diplomacy_lifecycle_v13 as life
from tools import verify_diplomacy_preview_v13 as preview

BUILD = "work/runtime/native1375-v13/build.json"
BUILD_SHA = "2cac305ddabdae1f1ce3a13cd389cbb9b6b25d6bd7f37e830d8a6ed16ad58389"
DLL_SHA = "b8d42242e5600bb1a18ef3115668b3f21c15913397e8e13ca799929c30f2500f"
PINS = {
    "work/candidates/v13-owned-peace-review/review.json": "ceaa1802a0230761ebaf27476c368377d59485cd275f7d8466da5052223a1ef7",
    "work/candidates/v13-host-review/review.json": "131a460f7cb75e110857ab73a8fe3e6b23a7cc604eee583152d17febe1751bfe",
    "work/candidates/v13-host-review/new-files.json": "55b395e5a2a6447d478de78f0a059ea5d41188ce4264ce89364fb3d85d290952",
    "work/runtime/native1375-v13/root-single-build-verification-20261008a.json": "d3fd2de0aa389436d2ccff0cc8e61930e6c070fb14f157f36c15665a774a2cdf",
}
COUNTS = {"lifecycle": 20, "owned_peace": 1, "preview": 72, "command": 72}
FILES = ("session.json", "install.claim", "research-1375.jsonl",
         "phase-lifecycle.claim", "phase-owned-peace-lifecycle.claim", "phase-preview.claim", "phase-command.claim")
INPUTS = {*FILES, "before", "after", "loader"}
MAX_FILE, MAX_TOTAL, MAX_MANIFEST = 8 * 1024 * 1024, 24 * 1024 * 1024, 64 * 1024
HEX = re.compile(r"[0-9a-f]{64}\Z")
require = lab.require


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def integer(value, minimum=0, maximum=2**64 - 1):
    return type(value) is int and minimum <= value <= maximum


def creation(value):
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{16}", value)
            and int(value, 16) > 0, "Creation must be a nonzero canonical 16-hex string")
    return value


def bounded(path, maximum=MAX_FILE):
    with Path(path).open("rb") as stream:
        value = stream.read(maximum + 1)
    require(len(value) <= maximum, "Bounded artifact exceeded: " + str(path))
    return value


def relative(root, name):
    require(type(name) is str and "\\" not in name and ":" not in name, "Noncanonical artifact path")
    parts = PurePosixPath(name)
    require(parts.parts and not parts.is_absolute() and str(parts) == name
            and all(p not in (".", "..") for p in parts.parts), "Unconfined artifact path")
    root = Path(root).resolve()
    path = root.joinpath(*parts.parts)
    require(path.resolve().is_relative_to(root), "Artifact escaped repository")
    cursor = path
    while cursor != root:
        require(not cursor.is_symlink() and not cursor.is_junction(), "Linked artifact forbidden")
        cursor = cursor.parent
    return path


def json_doc(raw):
    value = decode_json(raw.decode("utf-8-sig"))
    require(type(value) is dict, "Expected JSON object")
    return value


def fixed_build(root=ROOT):
    """Rehash reviewed inputs AND the frozen manifest's 20 + 11 + 8 source set."""
    for name, digest in PINS.items():
        require(sha(bounded(relative(root, name))) == digest, "Review/build evidence changed: " + name)
    require(sha(bounded(relative(root, BUILD))) == BUILD_SHA, "Not the single frozen v13 build")
    manifest, digest = lab.verify_build(root=Path(root), output=relative(root, BUILD).parent)
    require(digest == BUILD_SHA and manifest["dll_sha256"].lower() == DLL_SHA
            and type(manifest["schema_version"]) is int and manifest["schema_version"] == 2,
            "Wrong v13 manifest/DLL identity")
    require(tuple(lab.PHASES) == tuple(COUNTS) and len(lab.ACTIONS) == 36
            and (len(manifest["source_sha256"]), len(manifest["host_source_sha256"]),
                 len(manifest["support_source_sha256"])) == (20, 11, 8), "Frozen source/stage set differs")
    return manifest


class Inventory:
    def __init__(self, root, entries):
        require(type(entries) is dict and set(entries) == INPUTS, "Need exactly ten preflight artifacts")
        self.root, self.entries = root, entries
        paths, total = set(), 0
        for row in entries.values():
            require(type(row) is dict and set(row) == {"path", "size_bytes", "sha256"}, "Invalid input descriptor")
            relative(root, row["path"])
            require(row["path"] not in paths, "Duplicate artifact path")
            paths.add(row["path"])
            require(integer(row["size_bytes"], 1, MAX_FILE) and type(row["sha256"]) is str
                    and HEX.fullmatch(row["sha256"]), "Invalid input size/hash")
            total += row["size_bytes"]
        require(total <= MAX_TOTAL, "Aggregate evidence budget exceeded")

    def raw(self, key):
        row = self.entries[key]
        data = bounded(relative(self.root, row["path"]), row["size_bytes"])
        require(len(data) == row["size_bytes"] and sha(data) == row["sha256"], "Input changed: " + key)
        return data


def identity(row, pid, created):
    require(type(row) is dict and integer(row.get("pid"), 1, 2**32 - 1) and row["pid"] == pid
            and creation(row.get("creation")) == created, "Foreign/incomplete full process identity")
    life.pointer_value(row.get("world_cookie"), "world")
    require(row.get("player_handle") == "0x0100007a00415246"
            and integer(row.get("raw_date"), 1, 2**31 - 1), "Foreign player/date identity")
    return {k: row[k] for k in ("pid", "creation", "world_cookie", "player_handle", "raw_date")}


def diagnostic(report, pid, created):
    """Require the complete held-handle read-only envelope, not PID alone."""
    projection = life.snapshot_projection(report, pid, lab.LOCAL_SHA256.lower())
    source = report["source"]
    require(type(source.get("process_creation_filetime")) is int
            and source["process_creation_filetime"] == int(created, 16)
            and type(source.get("process_exit_filetime")) is int and source["process_exit_filetime"] == 0,
            "Diagnostic process creation/exit differs")
    require(source.get("access") == ["PROCESS_QUERY_INFORMATION", "PROCESS_VM_READ"]
            and source.get("atomic_snapshot") is False
            and source.get("held_identity_verified_before_and_after") is True,
            "Missing exact held-handle read-only diagnostic envelope")
    endpoints = report.get("identity_before_and_after")
    require(type(endpoints) is list and len(endpoints) == 2, "Missing double observed process identity")
    first, last = (identity(row, pid, created) for row in endpoints)
    require(first == last and first["raw_date"] == projection["current_raw_date"]
            and int(first["player_handle"], 16) == projection["player"]["handle"], "Diagnostic identity moved during capture")
    state = report["state"]
    require(state.get("game_pointer") == first["world_cookie"], "Diagnostic root/held identity mismatch")
    started = life.time_value(report.get("capture_started_at_utc"), "capture_started_at_utc")
    require(started <= projection["captured_at"], "Capture timestamp regressed")
    require(state["snapshot_consistency"].get("atomic") is False, "Diagnostic overclaims atomic sampling")
    budget = report.get("read_budget", {})
    from work import probe_diplomacy_current as probe
    expected = {"per_read_max_bytes": probe.MAX_READ, "total_max_bytes": probe.MAX_TOTAL_READ,
                "country_slot_max": probe.MAX_SLOTS, "diplomat_entry_max": probe.MAX_DIPLOMATS}
    require(all(type(budget.get(k)) is int and budget[k] == v for k, v in expected.items())
            and integer(budget.get("bytes_requested"), 1, probe.MAX_TOTAL_READ)
            and integer(state.get("memory_bytes_requested"), 1, budget["bytes_requested"]), "Diagnostic read budget missing/inconsistent")
    require(report.get("offset_profile") == {"database_pointer_rva": hex(probe.DATABASE_POINTER_RVA),
            "game_pointer_rva": hex(probe.GAME_POINTER_RVA)}, "Diagnostic offset profile differs")
    return first, projection, (started, projection["captured_at"])


def loader_record(document, pid, created, held, root=ROOT):
    if "report" in document:
        require(type(document.get("exit_code")) is int and document["exit_code"] == 0
                and document.get("stderr") == "" and document.get("automatic_retry") is False,
                "Loader capture failed or allowed retry")
        document = document["report"]
    require(type(document) is dict and integer(document.get("pid"), 1) and document["pid"] == pid
            and creation(document.get("creation")) == created and document.get("purpose") == lab.PURPOSE,
            "Loader is not from the exact v13 process")
    require(document.get("dll_sha256", "").lower() == DLL_SHA and document.get("manifest_sha256") == BUILD_SHA
            and document.get("plan_only") is False, "Loader is a plan or a different build")
    require(all(document.get(k) is False for k in ("selftest_automatic", "owned_peace_automatic", "preview_automatic",
            "command_automatic", "submit_automatic", "production_backend_registered")), "Loader automatic-stage contract differs")
    require(identity(document.get("live_observation"), pid, created) == held, "Loader observation/diagnostic identity differs")
    install = document.get("installation", {})
    require(integer(install.get("pid"), 1) and install["pid"] == pid
            and install.get("bridge_thread_exit_status") == "0x0" and install.get("dll_unloaded") is False
            and install.get("test_save_acknowledged") is True and install.get("warnings") == [], "Loader did not record a clean successful installation")
    require(type(install.get("dll")) is str and Path(install["dll"]).resolve() == (relative(root, BUILD).parent/lab.DLL_NAME).resolve(),
            "Loader DLL path differs")
    base = life.pointer_value(install.get("dll_module_base"), "loaded DLL")
    remote = life.pointer_value(install.get("bridge_remote_address"), "BridgeStart")
    require(type(install.get("bridge_rva")) is str and re.fullmatch(r"0x[0-9a-f]+", install["bridge_rva"])
            and 0 < int(install["bridge_rva"], 16) < 16 * 1024 * 1024
            and base + int(install["bridge_rva"], 16) == remote, "Loader export address is inconsistent")
    fixture = document.get("fixture_disk_evidence", {})
    require(integer(fixture.get("pid"), 1) and fixture["pid"] == pid and creation(fixture.get("creation")) == created
            and fixture.get("profile_sha256") == lab.FIXTURE_PROFILE_SHA256
            and fixture.get("fixture_definition_files_verified") is True and fixture.get("installed_before_process_creation") is True
            and fixture.get("engine_registration_verified") is False, "Loader fixture premise is missing or different")
    return {"installation_success_recorded": True, "dll_module_base": install["dll_module_base"],
            "loaded_dll_memory_hash_independently_verified": False}


def validate_preflight(evidence, held):
    require(set(evidence.get("phases", {})) == set(COUNTS) and all(v is True for v in evidence["phases"].values())
            and set(evidence["phase_proofs"]) == set(COUNTS), "Four complete native stage proofs required")
    require(not evidence["requests"] and type(evidence["last_sequence"]) is int and evidence["last_sequence"] == 0
            and all(evidence[k] is False for k in ("pending", "lease_pending", "input_wait_pending")), "Prefix contains operations or unresolved activity")
    require(set(evidence["phase_attempted"]) == set(COUNTS) and all(v is True for v in evidence["phase_attempted"].values()), "Missing once-only native stage attempts")
    proofs = evidence["phase_proofs"]
    require(len(proofs["lifecycle"]["lifecycle"]) == 20
            and proofs["owned_peace"]["core_record_count"] == 9
            and proofs["preview"]["case_count"] == 72 and proofs["command"]["case_count"] == 72, "Not the exact 20/1/72/72 matrix")
    frame = evidence["latest_frame"]
    require(identity({"pid": frame.get("pid"), "creation": frame.get("process_creation_filetime"),
            **{k: frame.get(k) for k in ("world_cookie", "player_handle", "raw_date")}}, held["pid"], held["creation"]) == held,
            "Final healthy frame/held diagnostic identity differs")
    require(frame.get("paused") is True and frame.get("world_ready") is True
            and frame.get("send_enabled") is False and frame.get("session_frozen") is False,
            "Final preflight frame is not healthy, paused, and no-send")


def review(case, *, root=ROOT):
    require(type(case) is dict and set(case) == {"schema_version", "purpose", "pid", "creation", "build_manifest_sha256", "reviewer_sha256", "inputs"}, "Unexpected preflight case schema")
    require(type(case["schema_version"]) is int and case["schema_version"] == 1
            and case["purpose"] == "fixed_v13_preflight_case" and case["build_manifest_sha256"] == BUILD_SHA
            and case["reviewer_sha256"] == sha(bounded(Path(__file__))), "Case is not bound to this fixed reviewer/build")
    pid, created = case["pid"], creation(case["creation"])
    require(integer(pid, 1, 2**32 - 1), "Invalid case PID")
    build = fixed_build(root)
    inventory = Inventory(root, case["inputs"])
    raw = {key: inventory.raw(key) for key in INPUTS}
    before, after = (json_doc(raw[key]) for key in ("before", "after"))
    held, projection, times = diagnostic(before, pid, created)
    held_after, _, times_after = diagnostic(after, pid, created)
    require(held == held_after and times[1] < times_after[0], "Before/after full identity differs or captures overlap")
    loader = loader_record(json_doc(raw["loader"]), pid, created, held, root)
    # Validators read only this already-hashed byte snapshot. Never reread a
    # concurrently growing original session while combining phase proofs.
    with tempfile.TemporaryDirectory(prefix="eu4-v13-preflight-") as directory:
        frozen = Path(directory)
        for name in FILES:
            (frozen/name).write_bytes(raw[name])
        for key in ("before", "after"):
            (frozen/(key+".json")).write_bytes(raw[key])
        metadata = lab.read_session_metadata(frozen, pid, created)
        evidence = lab.read_evidence(frozen, metadata)
        validate_preflight(evidence, held)
        phases = {}
        for phase in COUNTS:
            result = life.verify_phase(phase, frozen/"research-1375.jsonl", pid,
                frozen/"before.json", frozen/"after.json", relative(root, BUILD))
            require(result["status"] == "passed" and result["runtime_verified"] is True
                    and result["execution_verified"] is False, f"{phase} review failed: {result['errors']}")
            phases[phase] = result
    # Fail if any original artifact changed while the fixed review was running.
    for key in INPUTS:
        inventory.raw(key)
    fixed_build(root)
    return {"schema_version": 1, "purpose": "reviewed_v13_preflight_only", "status": "passed",
        "pid": pid, "creation": created, "world_cookie": held["world_cookie"], "raw_date": held["raw_date"],
        "window_thread": metadata["window_thread"], "phase_case_counts": COUNTS,
        "phase_prefix_sha256": evidence["log_sha256"], "phase_prefix_bytes": evidence["log_bytes"],
        "build_manifest_sha256": BUILD_SHA, "dll_sha256": DLL_SHA,
        "source_sha256": build["source_sha256"], "host_source_sha256": build["host_source_sha256"],
        "support_source_sha256": build["support_source_sha256"], "review_pins": PINS,
        "case_sha256": sha(json.dumps(case, sort_keys=True, separators=(",", ":")).encode()),
        "input_artifacts": case["inputs"], "loader": loader, "phases": phases,
        "native_request_count": 0, "diplomatic_submit_count": 0, "fixture_submit_count": 0,
        "selected_snapshot_fields_equal": True, "full_held_process_identity_equal": True,
        "runtime_verification_scopes": [p["verification_scope"] for p in phases.values()],
        "game_process_accessed_by_reviewer": False, "execution_verified": False,
        "war_identity_verified": False, "parameterized_offer_verified": False, "white_peace_verified": False,
        "heap_release_independently_observed": False, "whole_world_unchanged": False,
        "world_generation_verified": False, "loaded_save_exact_path_verified": False,
        "strict_live_single_player_verified": False, "production_backend_registered": False,
        "limitations": ["Default owned peace has no war identity or negotiated terms; this is not a peace send.",
            "Read-only snapshots compare selected fields and are non-atomic; no exact per-event timestamp bracket is inferred.",
            "Native returned/destructor flags are recorded lifecycle evidence, not independent heap instrumentation.",
            "The loader records installation, not an independent post-load DLL memory hash or world epoch.",
            "The frozen DLL contains a sender; the preserved prefix alone is verified as no-send."]}


def prepare(*, pid, created, session, before, after, loader, root=ROOT):
    root = Path(root).resolve()
    paths = {name: Path(session)/name for name in FILES} | {"before": Path(before), "after": Path(after), "loader": Path(loader)}
    entries = {}
    for key, path in paths.items():
        path = path if path.is_absolute() else root/path
        name = path.absolute().relative_to(root).as_posix()
        raw = bounded(relative(root, name))
        entries[key] = {"path": name, "size_bytes": len(raw), "sha256": sha(raw)}
    case = {"schema_version": 1, "purpose": "fixed_v13_preflight_case", "pid": pid, "creation": created,
            "build_manifest_sha256": BUILD_SHA, "reviewer_sha256": sha(bounded(Path(__file__))), "inputs": entries}
    review(case, root=root)  # Do not publish an apparently usable case on failure.
    return case


def write_new(path, value):
    path = Path(path)
    lab._no_links(path)
    raw = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)+"\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return sha(raw)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("prepare")
    create.add_argument("--pid", type=int, required=True)
    create.add_argument("--creation", required=True)
    for name in ("session", "before", "after", "loader"):
        create.add_argument("--"+name, type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("review")
    verify.add_argument("--case", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        require(not args.output.exists(), "CreateNew output already exists")
        if args.command == "prepare":
            result = prepare(pid=args.pid, created=args.creation, session=args.session, before=args.before,
                             after=args.after, loader=args.loader)
        else:
            result = review(json_doc(bounded(args.case, MAX_MANIFEST)))
        digest = write_new(args.output, result)
        print(json.dumps({"status": "passed", "command": args.command, "output": str(args.output), "sha256": digest,
                          "execution_verified": False, "game_process_accessed": False}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError, OverflowError) as error:
        print(json.dumps({"status": "failed", "execution_verified": False, "error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
