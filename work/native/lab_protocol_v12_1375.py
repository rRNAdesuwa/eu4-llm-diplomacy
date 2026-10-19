"""EU4LAB/2 restricted research tooling. Not the production EU4PAIR/1 backend.

Pure helpers are import-safe. LiveLabProcess opens QUERY_INFORMATION|VM_READ
only; the separately named loader is the sole injection entry point.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re

from bridge.diplomacy_api import canonical, decode_json
from bridge.native_build import LOCAL_SHA256
from bridge.native_pair_backend import _no_links, _private_root, publish_exclusive, read_bounded, uptime_ms

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "work/runtime/native1375-v12"
DLL_NAME = "eu4_pair_lab_v12_1375.dll"
PURPOSE = "restricted_pair_lab_1375_v12"
# Frozen v12 request allowlist; future production/backend additions cannot widen it.
ACTIONS = frozenset(('offer_vassalization', 'cancel_vassalization', 'royal_marriage', 'break_marriage', 'improve_relations', 'stop_improving_relations', 'guarantee', 'revoke_guarantee', 'build_spy_network', 'stop_building_spy_network', 'offer_alliance', 'dissolve_alliance', 'ask_military_access', 'cancel_military_access', 'offer_military_access', 'revoke_military_access', 'ask_fleet_basing_rights', 'cancel_fleet_basing_rights', 'offer_fleet_basing_rights', 'revoke_fleet_basing_rights', 'embargo', 'revoke_embargo', 'give_subsidies', 'cancel_subsidies', 'warn', 'insult', 'form_coalition', 'leave_coalition', 'support_independence', 'cancel_independence_support', 'request_trade_power', 'cancel_trade_power_transfer', 'steer_trade', 'cancel_steer_trade', 'send_gift', 'trade_favors_for_gold'))
FIXED_RESEARCH_PARAMETERS = {'give_subsidies': {'monthly_amount': '1.000', 'duration_years': 10}, 'cancel_subsidies': {'monthly_amount': '1.000', 'duration_years': 10}, 'send_gift': {'amount': '25.000'}, 'insult': {'index': -1}, 'request_trade_power': {'fraction_milli': 500}, 'cancel_trade_power_transfer': {'fraction_milli': 500}}

PROTOCOL = "EU4LAB/2"
MAX_LOG = 8 * 1024 * 1024
MAX_LINE = 16384
MAX_RECORD = 1024
MAX_SEQUENCE = 2**63 - 1
MAX_TTL = 60000
FRAME_MAX_AGE = 2500
FIELDS = ("pid", "creation", "sequence", "expires", "operation", "mode", "action", "actor", "target", "speed")
TAGS = ("FRA", "ENG", "POR", "NAV", "FOI")
FIXTURE_ACTIONS = ("fixture_on", "fixture_off")
FIXTURE_PROFILE_ID = "1375_test_fixture_v3"
FIXTURE_CANDIDATE_ROOT = "work/candidates/fixture-v12-1375"
FIXTURE_SOURCES = tuple("mod/llm_diplomacy_test/" + name for name in (
    "descriptor.mod", "common/defines/zz_llm_diplomacy_test.lua", "events/llmt_fixture.txt",
    "common/event_modifiers/llm_diplomacy_test.txt", "common/opinion_modifiers/llmt_fixture.txt"))
FIXTURE_PROFILE_SHA256 = "f3507bb78f665443c5dad20efee0aef2dd86a8b6741130ee03e883b2ecc1a507"
FIXTURE_EVENT_CONTRACT_READY = True
SOURCES = tuple("work/native/v12/" + name for name in (
    "research-lab-1375.cpp", "research-lab-bootstrap-1375.inc", "research-frame-v6-1375.asm",
    "pair-probe-v6-1375.cpp", "pair-preview-v6-1375.cpp", "pair-command-v6-1375.cpp",
    "pair-engine-1375.h", "pair-engine-1375.cpp", "test-controls-1375.h", "test-controls-1375.cpp",
    "lab-request-1375.h", "build-lab-1375.cmd")) + ("work/native/test-fixture-v12-1375.h", "work/native/test-fixture-v12-1375.cpp")
PHASES = {
    "lifecycle": ("pair-selftest.request", "phase-lifecycle.claim", b"PAIR_SELFTEST_1375\n"),
    "preview": ("pair-preview.request", "phase-preview.claim", b"PAIR_PREVIEW_1375\n"),
    "command": ("pair-command.request", "phase-command.claim", b"PAIR_COMMAND_1375\n"),
}
TEST_SAVES = {
    "llm_diplomacy_1375_baseline.eu4": "276F88AFECDBC1F1A24ED6314845351B1BA5640715B7ED1FD14513B3376664FB",
    "llm_diplomacy_1375_after_improve.eu4": "7BFABE371E68AE502B806F9B80375FC8A4DAC638AD116D2506966FEF69633C5F",
}


class LabError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise LabError(message)


def integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def encode_request(record):
    require(isinstance(record, dict) and set(record) == set(FIELDS), "Request has unknown/missing fields")
    require(integer(record["pid"], 1, 2**32 - 1), "Invalid PID")
    require(isinstance(record["creation"], str) and re.fullmatch(r"[0-9a-f]{16}", record["creation"])
            and int(record["creation"], 16) > 0, "Invalid process creation identity")
    require(integer(record["sequence"], 1, MAX_SEQUENCE) and integer(record["expires"], 1, 2**64 - 1), "Invalid sequence/expiry")
    require(integer(record["speed"], 0, 5), "Invalid speed")
    if record["operation"] == "pair":
        require(isinstance(record["action"], str) and record["action"] in ACTIONS, "Unknown pair action")
        require(record["mode"] in ("legality_only", "submit") and record["speed"] == 0, "Invalid pair mode/speed")
        require(record["actor"] in TAGS and record["target"] in TAGS
                and record["actor"] != record["target"], "Invalid research country pair")
    elif record["operation"] == "speed":
        require(record["mode"] == "submit" and record["action"] == "none"
                and record["actor"] == record["target"] == "FRA", "Invalid speed request fields")
    elif record["operation"] == "fixture":
        require(record["mode"] == "submit" and record["action"] in FIXTURE_ACTIONS
                and record["actor"] == record["target"] == "FRA" and record["speed"] == 0,
                "Fixture requests accept only the fixed FRA fixture_on/fixture_off profile")
    else:
        raise LabError("Unknown research operation")
    raw = (PROTOCOL + "\n" + "".join(f"{key}={record[key]}\n" for key in FIELDS)).encode("ascii")
    require(len(raw) <= MAX_RECORD, "Request exceeds protocol limit")
    return raw


def decode_request(raw):
    require(isinstance(raw, bytes) and len(raw) <= MAX_RECORD and raw.endswith(b"\n"), "Invalid request framing")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise LabError("Request must be ASCII") from error
    require(len(lines) == len(FIELDS) + 1 and lines[0] == PROTOCOL, "Wrong protocol or field count")
    record = {}
    for line, key in zip(lines[1:], FIELDS):
        require(line.startswith(key + "="), "Wrong field order, duplicate or unknown key")
        value = line[len(key) + 1:]
        if key in ("pid", "sequence", "expires", "speed"):
            require(bool(re.fullmatch(r"0|[1-9][0-9]{0,19}", value)), "Noncanonical integer")
            value = int(value)
        record[key] = value
    require(encode_request(record) == raw, "Request is not canonical")
    return record


def file_hash(path):
    _no_links(Path(path))
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest().upper()


def fixture_source_path(root, name):
    """Reviewed candidate source, separate from the installed mod namespace."""
    require(name in FIXTURE_SOURCES, "Unknown fixed fixture source")
    return Path(root) / FIXTURE_CANDIDATE_ROOT / name


def fixture_profile(root=ROOT):
    profile = {"profile_id": FIXTURE_PROFILE_ID, "source_sha256": {name:file_hash(fixture_source_path(root,name)) for name in FIXTURE_SOURCES}}
    require(hashlib.sha256(canonical(profile).encode("ascii")).hexdigest() == FIXTURE_PROFILE_SHA256,
            "Fixture definitions differ from the fixed native profile")
    return profile


def fixture_proof_wire(metadata, sequence):
    require(integer(metadata.get("pid"), 1, 2**32-1) and integer(sequence, 1, MAX_SEQUENCE)
            and isinstance(metadata.get("process_creation_filetime"), str)
            and re.fullmatch(r"[0-9a-f]{16}", metadata["process_creation_filetime"]), "Invalid fixture proof identity")
    return (f"EU4FIXTURE/1\npid={metadata['pid']}\ncreation={metadata['process_creation_filetime']}\nsequence={sequence}\n"
            f"profile={FIXTURE_PROFILE_SHA256}\n").encode("ascii")


def verify_installed_fixture(manifest, pid, creation, *, root=ROOT, user_root=None):
    """Disk/startup evidence only; never claims engine event registration."""
    from work.local_config import user_data
    require(integer(pid,1,2**32-1) and isinstance(creation,str) and re.fullmatch(r"[0-9a-f]{16}",creation), "Invalid fixture process identity")
    process_ns = (int(creation,16)-116444736000000000)*100
    require(process_ns>0, "Invalid fixture creation timestamp")
    profile = fixture_profile(root)
    require(manifest.get("fixture_profile") == profile, "Manifest fixture profile differs from reviewed definitions")
    destination = Path(user_root) if user_root is not None else user_data()
    settings = destination/"dlc_load.json"
    config = decode_json(read_bounded(settings,1024*1024).decode("utf-8-sig"))
    require(isinstance(config.get("enabled_mods"),list) and "mod/llm_diplomacy_test.mod" in config["enabled_mods"], "Fixed test mod is not enabled")
    checked = [settings]
    for name,digest in profile["source_sha256"].items():
        installed = destination/name
        require(file_hash(installed)==digest, f"Installed fixture definition differs: {name}")
        checked.append(installed)
    descriptor = destination/"mod/llm_diplomacy_test.mod"
    source_descriptor = read_bounded(fixture_source_path(root,FIXTURE_SOURCES[0]),16384).decode("utf-8").replace("\r\n","\n")
    expected = source_descriptor+'\npath="mod/llm_diplomacy_test"\n'
    require(read_bounded(descriptor,32768).decode("utf-8").replace("\r\n","\n")==expected, "Enabled descriptor does not select the fixed fixture directory")
    checked.append(descriptor)
    require(all(0<path.stat().st_mtime_ns<process_ns for path in checked), "Fixture files or enabled-mod configuration changed after process creation")
    return {"pid":pid,"creation":creation,"profile_sha256":FIXTURE_PROFILE_SHA256,
            "fixture_definition_files_verified":True,"installed_before_process_creation":True,
            "engine_registration_verified":False,"files_checked":len(checked),
            "enabled_mod_configuration_sha256":file_hash(settings)}


def record_build(root=ROOT, output=OUTPUT):
    root, output = Path(root), Path(output)
    dll = output / DLL_NAME
    require(dll.is_file(), "Successful DLL build is required first")
    require(FIXTURE_SOURCES and FIXTURE_EVENT_CONTRACT_READY, "v12 fixture profile/audit contract has not been finalized")
    speed_flags = re.findall(r"static constexpr bool running_speed_enabled = (true|false);",
                            read_bounded(root / "work/native/v12/research-lab-1375.cpp", 1024 * 1024).decode("utf-8"))
    require(len(speed_flags) == 1, "Native running-speed gate must have one explicit definition")
    manifest = {"schema_version": 1, "purpose": PURPOSE, "game_sha256": LOCAL_SHA256,
                "built_at_utc": datetime.now(timezone.utc).isoformat(), "dll_sha256": file_hash(dll),
                "source_sha256": {name: file_hash(root / name) for name in SOURCES},
                "runtime_verified": False, "production_backend_registered": False,
                "fixture_profile": fixture_profile(root),
                "lease_duration_ms": 5000, "lease_max_raw_date_delta": 48,
                "requires_exact_process_external_watchdog": True, "running_speed_enabled": speed_flags[0] == "true"}
    # The build tool owns this artifact; never called by an operational CLI.
    (output / "build.json").write_text(canonical(manifest) + "\n", encoding="utf-8")
    return manifest


def verify_build(root=ROOT, output=OUTPUT):
    root, output = Path(root), Path(output)
    manifest_path = output / "build.json"
    manifest_raw = read_bounded(manifest_path, 65536)
    manifest = decode_json(manifest_raw.decode("utf-8"))
    require(isinstance(manifest, dict) and set(manifest) == {"schema_version", "purpose", "game_sha256", "built_at_utc",
            "dll_sha256", "source_sha256", "runtime_verified", "production_backend_registered",
            "lease_duration_ms", "lease_max_raw_date_delta", "requires_exact_process_external_watchdog", "running_speed_enabled", "fixture_profile"}, "Unexpected build manifest schema")
    require(FIXTURE_SOURCES and FIXTURE_EVENT_CONTRACT_READY, "v12 fixture profile/audit contract has not been finalized")
    profile = manifest["fixture_profile"]
    require(isinstance(profile, dict) and set(profile) == {"profile_id", "source_sha256"}
            and profile["profile_id"] == FIXTURE_PROFILE_ID and isinstance(profile["source_sha256"], dict)
            and set(profile["source_sha256"]) == set(FIXTURE_SOURCES), "v12 fixed fixture definition set is incomplete")
    require(all(file_hash(fixture_source_path(root,name)) == digest for name,digest in profile["source_sha256"].items()), "Candidate fixture definitions changed after build")
    require(profile == fixture_profile(root), "Manifest fixture profile is not the fixed native profile")
    require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1 and manifest["purpose"] == PURPOSE
            and manifest["game_sha256"] == LOCAL_SHA256 and manifest["runtime_verified"] is False
            and manifest["production_backend_registered"] is False
            and type(manifest["lease_duration_ms"]) is int and manifest["lease_duration_ms"] == 5000
            and type(manifest["lease_max_raw_date_delta"]) is int and manifest["lease_max_raw_date_delta"] == 48
            and manifest["requires_exact_process_external_watchdog"] is True, "Not the audited v12 research build profile")
    require(type(manifest["running_speed_enabled"]) is bool, "Manifest running-speed gate must be boolean")
    require(isinstance(manifest["source_sha256"], dict) and set(manifest["source_sha256"]) == set(SOURCES), "Source manifest is incomplete")
    for name, digest in manifest["source_sha256"].items():
        require(file_hash(root / name) == digest, f"Source changed after build: {name}")
    require(file_hash(output / DLL_NAME) == manifest["dll_sha256"], "DLL changed after build")
    speed_flags = re.findall(r"static constexpr bool running_speed_enabled = (true|false);",
                            read_bounded(root / "work/native/v12/research-lab-1375.cpp", 1024 * 1024).decode("utf-8"))
    require(speed_flags == ["true" if manifest["running_speed_enabled"] else "false"], "Manifest running-speed gate differs from pinned source")
    return manifest, hashlib.sha256(manifest_raw).hexdigest()


def verify_test_save(name, save_root=None):
    from work.local_config import user_data
    require(name in TEST_SAVES, "Only the two audited independent-NAV baseline saves are accepted")
    path = (Path(save_root) if save_root else user_data() / "save games") / name
    require(file_hash(path) == TEST_SAVES[name], "Disposable test save differs from its audited bytes")
    with path.open("rb") as stream:
        head = stream.read(4096)
    require(head.startswith(b"EU4txt\n") and b"\nmulti_player=no\n" in head and b'\nplayer="FRA"\n' in head,
            "Expected serialized single-player FRA test premise")
    return {"path": str(path), "sha256": TEST_SAVES[name], "serialized_single_player": True,
            "loaded_save_identity_verified": False, "strict_live_single_player_verified": False,
            "scope": "isolated disposable test premise; file existence does not identify the live world"}


class LiveLabProcess:
    """A held read-only process handle; does not enumerate unrelated memory."""
    def __init__(self, pid, *, expected_creation=None, output=OUTPUT, require_loaded=True):
        from work.local_config import game_root
        from work.probe_diplomacy_current import ProcessReader, pe_signature, verified_executable
        from work.native import inject_probe
        self.reader = None
        self.output, self.pid = Path(output), pid
        executable = game_root() / "eu4.exe"
        _, signature = verified_executable(executable)
        self.reader = ProcessReader(pid, executable, signature)
        try:
            self.kernel = inject_probe._configure_kernel32()
            self.kernel.GetProcessTimes.argtypes = [W.HANDLE, C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME)]
            self.kernel.GetProcessTimes.restype = W.BOOL
            created, exited, cpu_kernel, cpu_user = W.FILETIME(), W.FILETIME(), W.FILETIME(), W.FILETIME()
            require(self.kernel.GetProcessTimes(self.reader.handle, C.byref(created), C.byref(exited), C.byref(cpu_kernel), C.byref(cpu_user))
                    and not (exited.dwLowDateTime or exited.dwHighDateTime), "Cannot identify the current live process")
            self.creation = f"{(created.dwHighDateTime << 32) | created.dwLowDateTime:016x}"
            require(expected_creation is None or expected_creation == self.creation, "PID creation identity changed")
            self.modules = inject_probe._enum_modules(self.kernel, self.reader.handle)
            matches = inject_probe._find_module(self.modules, self.output / DLL_NAME)
            if require_loaded:
                require(len(matches) == 1, "The exact v12 lab DLL is not uniquely loaded")
                with (self.output / DLL_NAME).open("rb") as stream:
                    local_signature = pe_signature(stream)
                require(pe_signature(self.reader, matches[0].handle) == local_signature, "Loaded DLL PE identity differs from disk")
            else:
                require(not any(Path(module.path).name.lower().startswith(("eu4_pair_", "eu4_bridge_")) for module in self.modules),
                        "A bridge is already loaded; never hot-replace or rearm this process")
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.reader:
            self.reader.close()
            self.reader = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def snapshot(self):
        from work.probe_diplomacy_current import GAME_POINTER_RVA, DATABASE_POINTER_RVA
        import struct
        def u64(address):
            return struct.unpack("<Q", self.reader.read(address, 8))[0]
        game = u64(self.reader.base + GAME_POINTER_RVA)
        database = u64(self.reader.base + DATABASE_POINTER_RVA)
        player = u64(game + 0x1e60)
        date = struct.unpack("<i", self.reader.read(game + 0x1dd0, 4))[0]
        require(game >= 0x10000 and database >= 0x10000 and player == 0x0100007a00415246 and date > 0,
                "Live FRA world identity is unavailable")
        require(u64(self.reader.base + GAME_POINTER_RVA) == game and u64(game + 0x1e60) == player,
                "Live world changed during observation")
        return {"pid": self.pid, "creation": self.creation, "world_cookie": hex(game),
                "player_handle": f"0x{player:016x}", "raw_date": date}


@contextmanager
def watchdog_parent(pid, creation):
    """Bind an explicitly invoked watchdog subprocess relationship, not an ACL.

The reviewed parent wrapper owns termination authority and the bounded timer.
This prevents accidental direct CLI use; it is not same-user authentication.
"""
    require(integer(pid, 1, 2**32 - 1) and pid == os.getppid()
            and isinstance(creation, str) and re.fullmatch(r"[0-9a-f]{16}", creation),
            "Running speed requires the direct verified watchdog parent")
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.GetProcessTimes.argtypes = [W.HANDLE, C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME)]
    kernel.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
    kernel.WaitForSingleObject.restype = W.DWORD
    kernel.CloseHandle.argtypes = [W.HANDLE]
    handle = kernel.OpenProcess(0x1000 | 0x00100000, False, pid)  # QUERY_LIMITED_INFORMATION | SYNCHRONIZE
    require(handle, "Cannot hold the watchdog process identity")
    try:
        created, exited, cpu_kernel, cpu_user = W.FILETIME(), W.FILETIME(), W.FILETIME(), W.FILETIME()
        require(kernel.GetProcessTimes(handle, C.byref(created), C.byref(exited), C.byref(cpu_kernel), C.byref(cpu_user)),
                "Cannot verify watchdog creation time")
        require(f"{(created.dwHighDateTime << 32) | created.dwLowDateTime:016x}" == creation, "Watchdog PID was reused")
        def healthy():
            require(kernel.WaitForSingleObject(handle, 0) == 0x102, "Watchdog exited; no running request may be published")
        healthy()
        yield healthy
    finally:
        kernel.CloseHandle(handle)


def session_path(output, pid, creation):
    require(integer(pid, 1, 2**32 - 1) and isinstance(creation, str) and re.fullmatch(r"[0-9a-f]{16}", creation), "Invalid session identity")
    result = Path(output) / f"session-{pid}-{creation}"
    _private_root(result)
    return result


def read_session_metadata(session, pid, creation):
    value = decode_json(read_bounded(Path(session) / "session.json", 4096).decode("utf-8"))
    require(isinstance(value, dict) and set(value) == {"schema_version", "purpose", "pid", "process_creation_filetime", "window_thread",
            "game_sha256", "world_generation_verified", "runtime_verified"}, "Unexpected native session metadata")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1 and value["purpose"] == PURPOSE
            and type(value["pid"]) is int and value["pid"] == pid and value["process_creation_filetime"] == creation
            and integer(value["window_thread"], 1, 2**32 - 1) and value["game_sha256"] == LOCAL_SHA256
            and value["world_generation_verified"] is False and value["runtime_verified"] is False,
            "Native metadata has a different process/build or overclaims production verification")
    require(decode_json(read_bounded(Path(session) / "install.claim", 4096).decode("utf-8")) == value,
            "Durable installation claim differs from session identity")
    return value


def read_evidence(session, metadata):
    """Stream a fixed-length bounded snapshot, retain only phase proofs and ACKs."""
    from tools.verify_diplomacy_lifecycle_v12 import Session, PREVIEW_EVENTS, COMMAND_EVENTS
    from tools.verify_diplomacy_preview_v12 import PreviewSession
    from tools.verify_diplomacy_command_v12 import CommandSession
    path = Path(session) / "research-1375.jsonl"
    _no_links(path)
    size = path.stat().st_size
    require(0 < size <= MAX_LOG, "Research log is empty or exceeds its bounded snapshot limit")
    validators, proofs, complete = {}, {}, set()
    latest, installed, last_sequence, pending, requests = None, False, 0, None, {}
    previous_frame, previous_uptime, previous_date, world = 0, 0, 0, None
    digest = hashlib.sha256()
    phase_events = PREVIEW_EVENTS | COMMAND_EVENTS | {"pair_selftest_begin", "pair_lifecycle", "pair_lifecycle_complete", "pair_selftest_complete"}
    lease = None
    input_wait = None
    last_input_uptime = 0
    with path.open("rb") as stream:
        remaining, line_number = size, 0
        while remaining:
            raw = stream.readline(min(remaining, MAX_LINE + 1))
            require(raw and raw.endswith(b"\n") and len(raw) <= MAX_LINE, "Truncated or oversized research log line")
            remaining -= len(raw)
            digest.update(raw)
            line_number += 1
            event = decode_json(raw.decode("utf-8"))
            require(isinstance(event, dict) and isinstance(event.get("event"), str), "Malformed research event")
            name = event["event"]
            if name.startswith("lab_") or name == "research_hook_installed":
                require(type(event.get("pid")) is int and event["pid"] == metadata["pid"]
                        and event.get("process_creation_filetime") == metadata["process_creation_filetime"],
                        "Native event lacks its exact process identity")
            if "pid" in event:
                require(type(event["pid"]) is int and event["pid"] == metadata["pid"], "Foreign PID in session log")
            if "process_creation_filetime" in event:
                require(event["process_creation_filetime"] == metadata["process_creation_filetime"], "Foreign creation time in session log")
            if name == "research_hook_installed":
                require(not installed and not validators and event.get("window_thread") == metadata["window_thread"], "Duplicate/foreign hook boundary")
                installed = True
                validators = {"lifecycle": Session(event, line_number, metadata["pid"]),
                              "preview": PreviewSession(event, line_number, metadata["pid"]),
                              "command": CommandSession(event, line_number, metadata["pid"])}
                continue
            if not installed and name == "research_hook_refused":
                require(event.get("result") == 21 and event.get("prefix_unchanged") is True
                        and event.get("resume_failures") == 0 and event.get("retrying") is True
                        and event.get("submitted") is False, "Installation refusal was not a safely retried guard failure")
                continue
            require(installed, "Research events precede a verified installation boundary")
            if name in ("lab_session_frozen", "lab_host_exception"):
                raise LabError("Native lab session is frozen; no retry: " + str(event.get("reason", name)))
            if name == "research_frame":
                require(event.get("thread") == metadata["window_thread"] and event.get("thread_changed") is False
                        and event.get("world_changed") is False and event.get("session_frozen") is False, "Frame thread/world/session fault")
                require(event.get("fixture_profile_sha256") == FIXTURE_PROFILE_SHA256, "Frame has a different fixture profile")
                require(integer(event.get("frames"), previous_frame + 1, 2**31 - 1)
                        and integer(event.get("uptime_ms"), max(1, previous_uptime, last_input_uptime), 2**64 - 1), "Frame sequence/time regressed")
                require(type(event.get("pid")) is int and event["pid"] == metadata["pid"]
                        and event.get("process_creation_filetime") == metadata["process_creation_filetime"], "Frame lacks process identity")
                require(event.get("last_sequence") == last_sequence, "Frame sequence differs from observed claimed requests")
                if event.get("world_ready") is True:
                    identity = (event.get("world_cookie"), event.get("player_handle"))
                    require(world is None or world == identity, "Frame world/player identity changed")
                    require(integer(event.get("raw_date"), max(1, previous_date), 2**31 - 1), "Frame date regressed")
                    world, previous_date = identity, event["raw_date"]
                previous_frame, previous_uptime = event["frames"], event["uptime_ms"]
                latest = event
            if name in ("lab_input_wait", "lab_input_failed"):
                kind = event.get("input_kind")
                require(kind in (*PHASES, "request") and event.get("sequence") == last_sequence
                        and type(event.get("sequence")) is int and event.get("native_invoked") is False
                        and event.get("retry_allowed") is False and pending is None and lease is None,
                        "Input diagnostic has an invalid kind, sequence, or operation boundary")
                input_sequence = event.get("input_sequence")
                require(type(input_sequence) is int and input_sequence == (last_sequence + 1 if kind == "request" else 0),
                        "Input diagnostic refers to the wrong unclaimed input")
                if kind == "request":
                    require("command" in proofs and proofs["command"]["passed"], "Request input preceded complete preflight")
                else:
                    order = tuple(PHASES)
                    require(last_sequence == 0 and kind not in proofs and kind not in complete and all(p in proofs for p in order[:order.index(kind)]),
                            "Input diagnostic refers to an already completed or out-of-order phase")
                require(integer(event.get("uptime_ms"), max(1, previous_uptime, last_input_uptime), 2**64 - 1),
                        "Input diagnostic time regressed")
                last_input_uptime = event["uptime_ms"]
                if name == "lab_input_failed":
                    stages = {"open_wait_budget", "wait_begin_audit", "open", "wait_end_audit", "file_type", "file_info",
                              "file_attributes", "file_links", "file_size", "size_range", "read", "read_length", "marker_token",
                              "parse", "pid", "creation", "sequence", "ttl_expired", "ttl_range", "claim_open", "claim_write",
                              "claim_length", "claim_flush", "claim_close", "disposition", "request_close"}
                    require(event.get("stage") in stages and integer(event.get("win32_error"), 0, 2**32 - 1)
                            and integer(event.get("close_win32_error"), 0, 2**32 - 1) and integer(event.get("expires"), 0, 2**64 - 1)
                            and integer(event.get("bytes"), 0, MAX_RECORD) and integer(event.get("attempts"), 1, 16)
                            and all(type(event.get(k)) is bool for k in ("claim_created", "claim_flushed", "request_deleted"))
                            and (not event["claim_flushed"] or event["claim_created"])
                            and (not event["request_deleted"] or event["claim_flushed"]), "Malformed input failure diagnostic")
                    raise LabError("Native input failed; no retry: " + event["stage"]
                                   + "; win32_error=" + str(event["win32_error"])
                                   + "; claim_created=" + str(event["claim_created"]))
                require(event.get("maximum_wait_ms") == 250 and type(event.get("maximum_wait_ms")) is int
                        and event.get("maximum_attempts") == 16 and type(event.get("maximum_attempts")) is int
                        and event.get("win32_error") == 32 and type(event.get("win32_error")) is int
                        and event.get("claim_created") is False and integer(event.get("attempts"), 1, 16)
                        and integer(event.get("elapsed_ms"), 0, 2**64 - 1), "Malformed bounded sharing wait")
                if event.get("wait_state") == "begin":
                    require(input_wait is None and event.get("outcome") == "sharing_violation"
                            and event["attempts"] == 1 and event["elapsed_ms"] == 0, "Duplicate or malformed wait start")
                    input_wait = event
                elif event.get("wait_state") == "end":
                    require(input_wait is not None and all(event[k] == input_wait[k] for k in ("sequence", "input_sequence", "input_kind"))
                            and event["uptime_ms"] >= input_wait["uptime_ms"]
                            and event["elapsed_ms"] == event["uptime_ms"] - input_wait["uptime_ms"]
                            and event["attempts"] >= input_wait["attempts"], "Unbound sharing wait end")
                    outcome = event.get("outcome")
                    require(outcome in ("opened", "budget_exhausted", "disappeared", "open_error"), "Unknown sharing wait outcome")
                    require(outcome != "opened" or event["elapsed_ms"] < 250 and event["attempts"] >= 2,
                            "Opened input exceeded its sharing wait budget or has no second open attempt")
                    input_wait = None
                    require(outcome == "opened", "Native input wait failed; no retry: " + outcome)
                else:
                    raise LabError("Unknown sharing wait state")
                continue

            if name.startswith("lab_"):
                require(input_wait is None, "Mailbox operation preceded the end of its unclaimed input wait")
                require("command" in proofs and proofs["command"]["passed"], "Mailbox activity preceded complete preflight proof")
                sequence = event.get("sequence")
                if name == "lab_request_claimed":
                    require(pending is None and integer(sequence, last_sequence + 1, last_sequence + 1)
                            and event.get("durable_claim") is True and event.get("retry_allowed") is False, "Duplicate/out-of-order native claim")
                    record = {key: event[key] for key in ("pid", "sequence", "expires", "operation", "mode", "action", "actor", "target", "speed")}
                    record["creation"] = metadata["process_creation_filetime"]
                    wire = encode_request(record)
                    require(read_bounded(Path(session) / f"{sequence:020}.claim", MAX_RECORD) == wire, "Native claim bytes differ from event")
                    if record["operation"] == "fixture":
                        require(read_bounded(Path(session)/f"{sequence:020}.fixture-profile",512)==fixture_proof_wire(metadata,sequence),
                                "Fixture claim lacks its exact permanent profile proof")
                    pending = {"request": record, "records": [], "complete": None}
                    requests[sequence] = pending
                    require(len(requests) <= 4096, "Session request budget exceeded")
                    last_sequence = sequence
                elif name == "lab_native_record":
                    owner = pending
                    if event.get("lease_pause") is True:
                        require(lease is not None and sequence == lease["sequence"] and pending is None, "Unbound lease-pause audit record")
                        owner = lease
                    require(owner is not None and sequence == last_sequence and isinstance(event.get("record"), dict), "Unbound native audit record")
                    require(len(owner["records"]) < 8, "Native record budget exceeded")
                    core = event["record"]
                    require(type(core.get("thread_id")) is int and core["thread_id"] == metadata["window_thread"]
                            and core.get("retry_allowed") is False, "Core record has a foreign thread or permits retry")
                    pair = pending is not None and pending["request"]["operation"] == "pair"
                    fixture = pending is not None and pending["request"]["operation"] == "fixture"
                    if pair:
                        request = pending["request"]
                        require(core.get("event") in ("pair_engine_begin", "pair_engine_dispatch_intent", "pair_engine_complete")
                                and all(core.get(key) == request[key] for key in ("pid", "actor", "target"))
                                and core.get("process_creation_filetime") == metadata["process_creation_filetime"]
                                and core.get("action_id") == request["action"] and core.get("applied_verified") is False
                                and core.get("world") == latest["world_cookie"]
                                and core.get("raw_date") == latest["raw_date"], "Pair core record differs from request/world")
                        subsidy = request["action"] in ("give_subsidies", "cancel_subsidies")
                        require(type(core.get("fixed_subsidy_amount_milli")) is int and core["fixed_subsidy_amount_milli"] == (1000 if subsidy else 0)
                                and type(core.get("fixed_subsidy_duration_years")) is int and core["fixed_subsidy_duration_years"] == (10 if subsidy else 0),
                                "Pair core fixed research parameters differ")
                        expected_extra = {
                            "fixed_gift_amount_milli": 25000 if request["action"] == "send_gift" else 0,
                            "fixed_transfer_fraction_milli": 500 if request["action"] in ("request_trade_power", "cancel_trade_power_transfer") else 0,
                            "fixed_insult_index": -1 if request["action"] == "insult" else 0,
                        }
                        require(all(type(core.get(k)) is int and core[k] == v for k, v in expected_extra.items()),
                                "Pair core fixed gift/trade/insult parameters differ")
                    elif fixture:
                        requested_event = "llmt.1" if pending["request"]["action"] == "fixture_on" else "llmt.2"
                        require(core.get("event") in ("test_fixture_begin","test_fixture_complete")
                                and core.get("fixture_event") == requested_event and core.get("target") == "FRA"
                                and core.get("fixture_profile_sha256") == FIXTURE_PROFILE_SHA256
                                and core.get("fixture_effect_verified") is False and core.get("diplomacy_submitted") is False
                                and core.get("before_date") == latest["raw_date"], "Fixture audit differs from fixed request/profile/world")
                    else:
                        wanted_speed = 0 if owner is lease else pending["request"]["speed"]
                        require(core.get("event") in ("test_speed_begin", "test_speed_complete")
                                and core.get("requested_speed") == wanted_speed and core.get("diplomacy_submitted") is False,
                                "Controls record differs from requested speed")
                    expected_begin = "pair_engine_begin" if pair else ("test_fixture_begin" if fixture else "test_speed_begin")
                    require(owner["records"] or core.get("event") == expected_begin, "Core evidence has no begin boundary")
                    require(not owner["records"] or owner["records"][-1].get("event") not in ("pair_engine_complete", "test_speed_complete", "test_fixture_complete"),
                            "Core evidence continues after completion")
                    owner["records"].append(core)
                elif name == "lab_lease_armed":
                    require(pending is not None and lease is None and sequence == last_sequence
                            and pending["request"]["operation"] == "speed" and pending["request"]["speed"] > 0
                            and event.get("automatic_pause") is True and event.get("maximum_raw_date_delta") == 48
                            and event.get("reliable_generation_verified") is False, "Unexpected running lease")
                    lease = {"sequence": sequence, "records": [], "armed": event, "complete": None}
                elif name == "lab_request_complete":
                    require(pending is not None and sequence == last_sequence and event.get("operation") == pending["request"]["operation"]
                            and event.get("session_frozen") is False and event.get("retry_allowed") is False
                            and event.get("applied_verified") is False, "Unbound or uncertain native completion")
                    pending["complete"] = event
                    require(pending["records"] and pending["records"][-1].get("event") in ("pair_engine_complete", "test_speed_complete", "test_fixture_complete"),
                            "Completion lacks the core's final audit record")
                    if pending["request"]["operation"] == "pair":
                        require(event.get("action") == pending["request"]["action"] and event.get("ownership_uncertain") is False,
                                "Pair completion differs from the original request or has unknown ownership")
                        fields = ("status", "reason", "submit_entered", "submit_returned", "ownership_uncertain")
                    elif pending["request"]["operation"] == "fixture":
                        require(event.get("action") == pending["request"]["action"] and event.get("fixture_effect_verified") is False,
                                "Fixture completion differs from request or overclaims effects")
                        fields = ("reason","native_invoked","callback_returned","callback_success","result_destroyed",
                                  "arguments_unchanged","callback_flag_restored","world_identity_unchanged")
                        core = pending["records"][-1]
                        require(core.get("event") == "test_fixture_complete" and type(core.get("reason")) is int and core["reason"] == 0
                                and all(core.get(key) is True for key in fields[1:])
                                and type(core.get("exception_code")) is int and core["exception_code"] == 0
                                and core.get("after_date") == core.get("before_date"), "Fixture native callback completion is uncertain")
                    else:
                        require(event.get("speed") == pending["request"]["speed"], "Speed completion differs from request")
                        fields = ("reason", "write_entered", "callback_returned", "readback_matches")
                    core = pending["records"][-1]
                    require(all(key in event and key in core and type(event[key]) is type(core[key]) and event[key] == core[key] for key in fields)
                            and core.get("freeze_session") is False, "Host completion conflicts with its core record")
                    pending = None
                elif name == "lab_lease_complete":
                    require(lease is not None and pending is None and sequence == lease["sequence"]
                            and event.get("session_frozen") is False and event.get("readback_matches") is True
                            and event.get("paused_readback") is True and event.get("retry_allowed") is False,
                            "Automatic pause was not verified")
                    require(lease["records"] and lease["records"][-1].get("event") == "test_speed_complete", "Lease has no controls audit completion")
                    core = lease["records"][-1]
                    require(core.get("after_paused") is True and core.get("readback_matches") is True
                            and core.get("freeze_session") is False and core.get("exception_code") == 0
                            and all(key in core and core[key] == event.get(key) for key in ("reason", "write_entered", "callback_returned")),
                            "Automatic pause completion conflicts with its controls record")
                    claim = decode_json(read_bounded(Path(session) / f"{sequence:020}.lease-pause.claim", 4096).decode("utf-8"))
                    require(claim.get("purpose") == "bounded_running_lease_pause" and claim.get("pid") == metadata["pid"]
                            and claim.get("process_creation_filetime") == metadata["process_creation_filetime"]
                            and claim.get("origin_sequence") == sequence and claim.get("speed") == 0
                            and claim.get("deadline_uptime_ms") == lease["armed"].get("deadline_uptime_ms")
                            and claim.get("maximum_raw_date_delta") == 48
                            and claim.get("retry_allowed") is False, "Automatic pause claim identity differs")
                    requests[sequence]["lease_complete"] = event
                    lease = None
                else:
                    raise LabError("Unknown lab event: " + name)
                continue
            require(input_wait is None or name == "research_frame", "Phase invocation preceded the end of its unclaimed input wait")
            require(name == "research_frame" or name in phase_events, "Unknown non-mailbox event in research log: " + name)
            require(not ("command" in proofs and name in phase_events), "Preflight phases cannot be repeated after completion")
            for phase, validator in validators.items():
                if phase not in proofs:
                    validator.accept(event, line_number)
            for phase, completion in (("lifecycle", "pair_selftest_complete"), ("preview", "pair_preview_complete"), ("command", "pair_command_complete")):
                if name == completion:
                    complete.add(phase)
                if phase in complete and phase not in proofs and name == "research_frame":
                    proof = validators[phase].finish()
                    require(proof["passed"], f"{phase} prefix failed its detailed native lifecycle validator: {proof.get('errors')}")
                    require(read_bounded(Path(session) / PHASES[phase][1], MAX_RECORD) == PHASES[phase][2],
                            "Detailed phase proof lacks its exact durable marker claim")
                    proofs[phase] = proof
            require(len(requests) <= 4096, "Session request budget exceeded")
    require(installed and latest is not None, "Session has no installed healthy frame")
    return {"latest_frame": latest, "phases": {name: name in proofs for name in PHASES}, "phase_proofs": proofs,
            "last_sequence": last_sequence, "pending": pending is not None, "lease_pending": lease is not None, "requests": requests,
            "input_wait_pending": input_wait is not None,
            "log_sha256": digest.hexdigest(), "log_bytes": size, "read_kind": "fixed_size_read_only_snapshot"}


def check_ready(evidence, live, now, *, phase=None, operation=None):
    frame = evidence["latest_frame"]
    require(integer(now, 1, 2**64 - 1) and 0 <= now - frame["uptime_ms"] <= FRAME_MAX_AGE, "Native frame heartbeat is stale")
    require(frame.get("world_ready") is True and frame.get("frames", 0) >= 100, "World/frame preflight is not ready")
    require(frame.get("world_cookie") == live["world_cookie"] and frame.get("player_handle") == live["player_handle"]
            and live["raw_date"] >= frame.get("raw_date", 0), "Independent live world differs from frame evidence")
    require(not evidence.get("input_wait_pending"), "A published input is awaiting its bounded pre-handle sharing wait")
    require(not evidence["pending"], "Prior native request is incomplete; never automatically resubmit")
    require(not evidence.get("lease_pending") and frame.get("lease_active") is not True, "Running lease must finish its automatic pause first")
    if operation != "speed":
        require(frame.get("paused") is True and live["raw_date"] == frame["raw_date"], "Pair/preflight operations require a stable paused world")
    if phase:
        order = tuple(PHASES)
        index = order.index(phase)
        require(not evidence["phases"][phase] and all(evidence["phases"][name] for name in order[:index]), "Phase was already completed or prerequisites are missing")
    else:
        require(all(evidence["phases"].values()) and frame.get("mailbox_ready") is True, "Three detailed preflight phases must pass before mailbox use")
        require(all(frame.get(name + "_passed") is True for name in PHASES), "Frame contradicts detailed preflight evidence")


def prepare_request(metadata, evidence, *, sequence, operation, mode, action, actor, target, speed, ttl_ms, now):
    """Validate the same request in plan and publication modes; no file writes."""
    require(integer(sequence, 1, MAX_SEQUENCE) and sequence == evidence["last_sequence"] + 1,
            "Sequence must explicitly match the next native sequence")
    require(integer(ttl_ms, 1, MAX_TTL), "TTL must be 1..60000 ms")
    require(operation != "speed" or speed == 0 or evidence["latest_frame"].get("running_speed_enabled") is True,
            "Running speed is disabled until its bounded automatic-pause lease is reviewed")
    require(operation != "pair" or mode != "submit" or actor == "FRA", "Only current player FRA may submit in this research profile")
    require(operation != "fixture" or FIXTURE_EVENT_CONTRACT_READY, "v12 native fixture audit contract is not finalized")
    record = {"pid": metadata["pid"], "creation": metadata["process_creation_filetime"], "sequence": sequence,
              "expires": now + ttl_ms, "operation": operation, "mode": mode, "action": action,
              "actor": actor, "target": target, "speed": speed}
    return record, encode_request(record)


def publish_research(session, metadata, manifest_sha, evidence, live, *, sequence=None, operation=None,
                     mode="legality_only", action=None, actor="FRA", target="ENG", speed=0, phase=None, ttl_ms=5000,
                     clock=uptime_ms, recheck=None, watchdog_verified=False, fixture_check=None):
    """One explicit publication. Durable host intent precedes the final file."""
    session = Path(session)
    _private_root(session)
    check_ready(evidence, live, clock(), phase=phase, operation=operation)
    require(not list(session.glob("*.request")), "A request/phase marker is already pending")
    require(operation != "fixture" or callable(fixture_check), "Fixture publication requires independent installed-file/startup verification")
    if phase:
        filename, claim, raw = PHASES[phase]
        final, claimed = session / filename, session / claim
        intent_path = session / (claim + ".host-intent")
    else:
        require(operation != "speed" or speed == 0 or watchdog_verified is True,
                "Running speed requires an active exact-process external watchdog")
        record, raw = prepare_request(metadata, evidence, sequence=sequence, operation=operation, mode=mode,
                                      action=action, actor=actor, target=target, speed=speed, ttl_ms=ttl_ms, now=clock())
        final, claimed = session / f"{sequence:020}.request", session / f"{sequence:020}.claim"
        intent_path = session / f"{sequence:020}.host-intent"
    _no_links(final)
    _no_links(claimed)
    require(not final.exists() and not claimed.exists(), "Request/claim already exists; no retry or replacement")
    intent = {"protocol": PROTOCOL, "purpose": PURPOSE, "pid": metadata["pid"], "creation": metadata["process_creation_filetime"],
              "manifest_sha256": manifest_sha, "request_sha256": hashlib.sha256(raw).hexdigest(),
              "body_ascii": raw.decode("ascii"), "automatic_retry": False}
    publish_exclusive(intent_path, (canonical(intent) + "\n").encode())
    # Any failure from here leaves intent in place. Repeating this command can
    # never republish, even if the native consumer removed the original file.
    if recheck is not None:
        current_evidence, current_live = recheck()
        check_ready(current_evidence, current_live, clock(), phase=phase, operation=operation)
        require(current_evidence["last_sequence"] == evidence["last_sequence"]
                and all(current_live[key] == live[key] for key in ("pid", "creation", "world_cookie", "player_handle")),
                "Session/world/sequence changed before publication")
    if not phase:
        require(clock() < record["expires"], "Publication deadline elapsed; retained intent may not be retried")
    if operation == "fixture":
        proof = fixture_check()
        require(proof.get("pid") == metadata["pid"] and proof.get("creation") == metadata["process_creation_filetime"]
                and proof.get("profile_sha256") == FIXTURE_PROFILE_SHA256
                and proof.get("fixture_definition_files_verified") is True and proof.get("installed_before_process_creation") is True
                and proof.get("engine_registration_verified") is False, "Fixture disk/startup evidence is missing or overclaims loaded registration")
        publish_exclusive(session/f"{sequence:020}.fixture-profile",fixture_proof_wire(metadata,sequence))
        require(clock() < record["expires"], "Fixture proof exceeded publication deadline; no retry")
    publish_exclusive(final, raw)
    return {"research_only": True, "protocol": PROTOCOL, "status": "published", "path": str(final),
            "request_sha256": intent["request_sha256"], "pid": metadata["pid"], "creation": metadata["process_creation_filetime"],
            "sequence": sequence, "phase": phase, "native_dispatch_verified": False, "applied_verified": False,
            "automatic_retry": False, "production_backend_registered": False}
