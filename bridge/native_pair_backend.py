"""Explicitly configured EU4PAIR/1 file transport; never loads or calls a DLL.

Construction/capability/status/reconcile do not publish files. No backend is
registered automatically. Current research DLLs lack this production handshake.
The live identity and effect verifiers are trusted, read-only integration seams;
no JSON file can substitute for a live identity verifier.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
import time
from typing import Callable
from urllib.parse import quote
import uuid

from .diplomacy_api import REQUEST_ID, canonical, decode_json
from .native_build import LOCAL_SHA256

PROTOCOL = "EU4PAIR/1"
MAX_RECORD = 4096
MAX_EVENT = 16384
MAX_JOURNAL = 2 * 1024 * 1024
MAX_MANIFEST = 65536
MAX_EVENTS = 4096
FRESH_MS = 2000
DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "work/runtime/pair-adapter"
ACTIONS = frozenset(("offer_vassalization", "cancel_vassalization", "royal_marriage", "break_marriage",
                     "improve_relations", "stop_improving_relations", "guarantee", "revoke_guarantee",
                     "build_spy_network", "stop_building_spy_network"))
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
TAG = re.compile(r"[A-Z0-9]{3}\Z")
BASE = ("store_id", "native_session_id", "host_nonce", "pid", "process_creation_filetime",
        "world_generation", "game_sha256", "dll_sha256")
MANIFEST_BINDING = ("experiment_sha256", "whitelist_sha256")
HEALTH = ("window_thread", "frame_sequence", "uptime_ms", "world_ready", "thread_changed", "send_enabled",
          "lifecycle_passed", "command_no_send_passed", "world_generation_verified", "single_player_verified", "paused")
WIRE_FIELDS = {
    "submit": BASE + ("sequence", "request_id", "request_sha256", "action", "actor", "target", "deadline_uptime_ms") + MANIFEST_BINDING,
    "handshake_request": BASE + MANIFEST_BINDING + ("challenge_uptime_ms",),
    "handshake_response": BASE + MANIFEST_BINDING + HEALTH,
    "heartbeat": BASE + MANIFEST_BINDING + HEALTH,
}
INTEGER_FIELDS = {"pid", "world_generation", "sequence", "deadline_uptime_ms", "window_thread",
                  "frame_sequence", "uptime_ms", "challenge_uptime_ms"}
BOOL_FIELDS = set(HEALTH) - INTEGER_FIELDS
EVENT_KEYS = set(BASE + MANIFEST_BINDING + ("sequence", "request_id", "request_sha256", "action", "actor", "target")) | {
    "protocol", "event_sequence", "uptime_ms", "utc", "event", "data", "previous_event_sha256", "event_sha256"}
EVENT_DATA = {
    "received": set(), "claimed": set(),
    "legality_result": {"allowed"},
    "dispatch_intent": {"ownership_known"},
    "dispatch_returned": {"returned", "container_consumed", "exception", "ownership_known"},
    "rejected_before_dispatch": {"reason_code", "dispatch_excluded", "ownership_known"},
    "ai_rejected": {"reason_code", "rejection_verified", "ownership_known"},
    "session_fault": {"reason_code", "dispatch_may_have_occurred", "ownership_known"},
    "effect_observed": {"effect_report_sha256"},
}


class MailboxError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate_request(request):
    if not isinstance(request, dict) or set(request) != {"request_id", "action", "parameters"}:
        raise MailboxError("invalid_request", "Only request_id, action and parameters are accepted")
    if not isinstance(request["request_id"], str) or not REQUEST_ID.fullmatch(request["request_id"]):
        raise MailboxError("invalid_request", "Invalid request_id")
    if not isinstance(request["action"], str) or request["action"] not in ACTIONS or not isinstance(request["parameters"], dict) or set(request["parameters"]) != {"actor", "target"}:
        raise MailboxError("invalid_request", "Unknown action or extra/missing pair parameters")
    actor, target = (request["parameters"][key] for key in ("actor", "target"))
    if any(not isinstance(value, str) or not TAG.fullmatch(value) for value in (actor, target)) or actor == target:
        raise MailboxError("invalid_request", "Distinct three-character TAGs are required")


def _field(key, value):
    if key in INTEGER_FIELDS:
        maximum = 0xffffffff if key in ("pid", "window_thread") else 0x7fffffffffffffff
        if type(value) is not int or not 1 <= value <= maximum:
            raise MailboxError("invalid_record", f"Invalid integer {key}")
        return str(value)
    if key in BOOL_FIELDS:
        if type(value) is not bool:
            raise MailboxError("invalid_record", f"Invalid boolean {key}")
        return "true" if value else "false"
    if not isinstance(value, str) or not value.isascii() or any(char in value for char in "\r\n\x00="):
        raise MailboxError("invalid_record", f"Invalid ASCII field {key}")
    if key.endswith("sha256"):
        valid = bool(HEX64.fullmatch(value))
    elif key in ("native_session_id", "host_nonce"):
        valid = bool(HEX32.fullmatch(value))
    elif key == "store_id":
        try:
            valid = str(uuid.UUID(value)) == value
        except ValueError:
            valid = False
    elif key == "process_creation_filetime":
        valid = bool(re.fullmatch(r"[0-9a-f]{16}", value)) and int(value, 16) > 0
    elif key in ("actor", "target"):
        valid = bool(TAG.fullmatch(value))
    elif key == "request_id":
        valid = bool(REQUEST_ID.fullmatch(value))
    elif key == "action":
        valid = value in ACTIONS
    else:
        valid = False
    if not valid:
        raise MailboxError("invalid_record", f"Invalid field {key}")
    return value


def encode_record(operation: str, values: dict) -> bytes:
    if operation not in WIRE_FIELDS or set(values) != set(WIRE_FIELDS[operation]):
        raise MailboxError("invalid_record", "Wrong operation or field set")
    body = (PROTOCOL + "\noperation=" + operation + "\n" + "".join(
        f"{key}={_field(key, values[key])}\n" for key in WIRE_FIELDS[operation])).encode("ascii")
    raw = body + f"record_sha256={sha(body)}\n".encode("ascii")
    if len(raw) > MAX_RECORD:
        raise MailboxError("record_too_large", "Record exceeds 4096 bytes")
    return raw


def decode_record(raw: bytes, operation: str) -> dict:
    if len(raw) > MAX_RECORD or not raw.endswith(b"\n") or b"\r" in raw or b"\x00" in raw:
        raise MailboxError("invalid_record", "Oversized or invalid record framing")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise MailboxError("invalid_record", "Record must be ASCII") from error
    fields = WIRE_FIELDS.get(operation, ())
    if len(lines) != len(fields) + 3 or lines[:2] != [PROTOCOL, "operation=" + operation]:
        raise MailboxError("invalid_record", "Wrong record header or number of fields")
    result = {}
    for line, key in zip(lines[2:-1], fields):
        if not line.startswith(key + "="):
            raise MailboxError("invalid_record", "Unknown, duplicate or reordered field")
        value = line[len(key) + 1:]
        if key in INTEGER_FIELDS:
            if not re.fullmatch(r"[1-9][0-9]{0,18}", value):
                raise MailboxError("invalid_record", "Noncanonical integer")
            value = int(value)
        elif key in BOOL_FIELDS:
            if value not in ("true", "false"):
                raise MailboxError("invalid_record", "Invalid boolean")
            value = value == "true"
        result[key] = value
    # This also validates every field, exact spelling, checksum and final LF.
    if encode_record(operation, result) != raw:
        raise MailboxError("invalid_record", "Checksum or canonical encoding mismatch")
    if operation == "submit":
        request = {"request_id": result["request_id"], "action": result["action"],
                   "parameters": {"actor": result["actor"], "target": result["target"]}}
        validate_request(request)
        if sha(canonical(request).encode()) != result["request_sha256"]:
            raise MailboxError("invalid_record", "Request digest mismatch")
    return result


def _windows_private_acl(path: Path, *, establish=False):
    """Require only the current user and SYSTEM allow ACEs; no shell commands."""
    from ctypes import wintypes as W
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    ptr = ctypes.c_void_p
    adv.OpenProcessToken.argtypes = [W.HANDLE, W.DWORD, ctypes.POINTER(W.HANDLE)]
    adv.GetTokenInformation.argtypes = [W.HANDLE, ctypes.c_int, ptr, W.DWORD, ctypes.POINTER(W.DWORD)]
    adv.ConvertSidToStringSidW.argtypes = [ptr, ctypes.POINTER(W.LPWSTR)]
    adv.GetNamedSecurityInfoW.argtypes = [W.LPWSTR, ctypes.c_int, W.DWORD, ctypes.POINTER(ptr), ctypes.POINTER(ptr), ctypes.POINTER(ptr), ctypes.POINTER(ptr), ctypes.POINTER(ptr)]
    adv.GetNamedSecurityInfoW.restype = W.DWORD
    adv.GetAclInformation.argtypes = [ptr, ptr, W.DWORD, ctypes.c_int]
    adv.GetAce.argtypes = [ptr, W.DWORD, ctypes.POINTER(ptr)]
    kernel.GetCurrentProcess.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.LocalFree.argtypes = [ptr]
    kernel.LocalFree.restype = ptr
    token, needed = W.HANDLE(), W.DWORD()
    if not adv.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise MailboxError("mailbox_not_private", "Cannot inspect current user token")
    def sid_text(sid):
        text = W.LPWSTR()
        if not adv.ConvertSidToStringSidW(sid, ctypes.byref(text)):
            raise MailboxError("mailbox_not_private", "Cannot inspect SID")
        try:
            return text.value
        finally:
            kernel.LocalFree(ctypes.cast(text, ptr))
    try:
        adv.GetTokenInformation(token, 1, None, 0, ctypes.byref(needed))
        data = ctypes.create_string_buffer(needed.value)
        if not adv.GetTokenInformation(token, 1, data, needed, ctypes.byref(needed)):
            raise MailboxError("mailbox_not_private", "Cannot read current user SID")
        user = sid_text(ptr.from_buffer(data).value)
    finally:
        kernel.CloseHandle(token)
    if establish:
        descriptor, acl = ptr(), ptr()
        present, defaulted = W.BOOL(), W.BOOL()
        adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [W.LPCWSTR, W.DWORD, ctypes.POINTER(ptr), ctypes.POINTER(W.DWORD)]
        adv.GetSecurityDescriptorDacl.argtypes = [ptr, ctypes.POINTER(W.BOOL), ctypes.POINTER(ptr), ctypes.POINTER(W.BOOL)]
        adv.SetNamedSecurityInfoW.argtypes = [W.LPWSTR, ctypes.c_int, W.DWORD, ptr, ptr, ptr, ptr]
        adv.SetNamedSecurityInfoW.restype = W.DWORD
        sddl = f"D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;{user})"
        if not adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None):
            raise MailboxError("mailbox_not_private", "Cannot construct private ACL")
        try:
            if not adv.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present), ctypes.byref(acl), ctypes.byref(defaulted)) or not present:
                raise MailboxError("mailbox_not_private", "Cannot read private ACL")
            if adv.SetNamedSecurityInfoW(str(path), 1, 4 | 0x80000000, None, None, acl, None):
                raise MailboxError("mailbox_not_private", "Cannot apply private ACL")
        finally:
            kernel.LocalFree(descriptor)
    owner, acl, descriptor = ptr(), ptr(), ptr()
    result = adv.GetNamedSecurityInfoW(str(path), 1, 1 | 4, ctypes.byref(owner), None, ctypes.byref(acl), None, ctypes.byref(descriptor))
    if result:
        raise MailboxError("mailbox_not_private", "Cannot read mailbox ACL")
    try:
        if not acl or sid_text(owner) != user:
            raise MailboxError("mailbox_not_private", "Mailbox must be owned by the current user with a non-null DACL")
        information = (W.DWORD * 3)()
        if not adv.GetAclInformation(acl, information, ctypes.sizeof(information), 2) or information[0] > 128:
            raise MailboxError("mailbox_not_private", "Cannot bound mailbox ACL")
        for index in range(information[0]):
            ace = ptr()
            if not adv.GetAce(acl, index, ctypes.byref(ace)):
                raise MailboxError("mailbox_not_private", "Cannot read ACE")
            kind = ctypes.c_ubyte.from_address(ace.value).value
            if kind == 1:  # Deny ACE cannot broaden access.
                continue
            if kind != 0 or sid_text(ace.value + 8) not in (user, "S-1-5-18"):
                raise MailboxError("mailbox_not_private", "Mailbox grants another principal access")
    finally:
        kernel.LocalFree(descriptor)


def _no_links(path: Path):
    for item in (path, *path.parents):
        if not item.exists() and not item.is_symlink():
            continue
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise MailboxError("unsafe_mailbox_path", "Symlinks/junctions/reparse points are forbidden")
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise MailboxError("unsafe_mailbox_path", "Hard-linked mailbox files are forbidden")


def _private_root(root: Path):
    if not root.is_absolute() or str(root).startswith(("\\\\", "//")):
        raise MailboxError("unsafe_mailbox_path", "Mailbox must be a local absolute directory")
    _no_links(root)
    if not root.is_dir():
        raise MailboxError("requires_new_native_handshake", "Mailbox directory is not provisioned")
    if os.name == "nt":
        from ctypes import wintypes as W
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        volume, filesystem = ctypes.create_unicode_buffer(32768), ctypes.create_unicode_buffer(32)
        kernel.GetVolumePathNameW.argtypes = [W.LPCWSTR, W.LPWSTR, W.DWORD]
        kernel.GetVolumeInformationW.argtypes = [W.LPCWSTR, W.LPWSTR, W.DWORD, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, W.LPWSTR, W.DWORD]
        kernel.GetDriveTypeW.argtypes = [W.LPCWSTR]
        if (not kernel.GetVolumePathNameW(str(root), volume, len(volume))
                or kernel.GetDriveTypeW(volume.value) != 3
                or not kernel.GetVolumeInformationW(volume.value, None, 0, None, None, None, filesystem, len(filesystem))
                or filesystem.value.upper() != "NTFS"):
            raise MailboxError("unsafe_mailbox_path", "Production mailbox requires a fixed local NTFS volume")
        _windows_private_acl(root)
    elif root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
        raise MailboxError("mailbox_not_private", "Mailbox requires owner-only permissions")


def _safe(root: Path, *parts: str) -> Path:
    if any(not isinstance(part, str) or part in ("", ".", "..") or "/" in part or "\\" in part or ":" in part for part in parts):
        raise MailboxError("unsafe_mailbox_path", "Mailbox path must use fixed local components")
    path = root.joinpath(*parts)
    _no_links(path)
    return path


def read_bounded(path: Path, maximum: int) -> bytes:
    _no_links(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
        raise MailboxError("artifact_too_large", "Artifact is not a bounded regular file")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise MailboxError("artifact_changed", "Artifact changed while opening")
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise MailboxError("artifact_too_large", "Artifact grew past its bound")
    return raw


def publish_exclusive(path: Path, raw: bytes):
    """Same-directory durable temp, then no-replace publication; never retries."""
    _no_links(path.parent)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(temporary, flags, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        if stream.write(raw) != len(raw):
            raise OSError("Short mailbox write")
        stream.flush()
        os.fsync(stream.fileno())
    # On Windows MoveFileEx without REPLACE_EXISTING fails if destination exists.
    # POSIX link is atomic/no-replace; unlink only our completed temp afterwards.
    if os.name == "nt":
        from ctypes import wintypes as W
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.MoveFileExW.argtypes = [W.LPCWSTR, W.LPCWSTR, W.DWORD]
        kernel.MoveFileExW.restype = W.BOOL
        if not kernel.MoveFileExW(str(temporary), str(path), 8):  # WRITE_THROUGH
            raise OSError(ctypes.get_last_error(), "Exclusive mailbox publication failed")
    else:
        os.link(temporary, path)
        temporary.unlink()
        descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def initialize_mailbox(root: Path) -> str:
    """Explicit one-time provisioning only; constructor never calls this."""
    root = Path(root).absolute()
    _no_links(root)
    if root.exists():
        raise MailboxError("mailbox_exists", "Never replace or silently recreate a mailbox ledger")
    root.mkdir(mode=0o700)
    if os.name == "nt":
        _windows_private_acl(root, establish=True)
    _private_root(root)
    store_id = str(uuid.uuid4())
    publish_exclusive(root / "store.json", (canonical({"schema_version": 1, "store_id": store_id}) + "\n").encode())
    (root / "sessions").mkdir(mode=0o700)
    database = sqlite3.connect(root / "ledger.sqlite3")
    try:
        # DELETE avoids read-only status creating/updating WAL shared-memory
        # artifacts. EXTRA also synchronizes the rollback-journal directory.
        database.execute("PRAGMA journal_mode=DELETE")
        database.execute("PRAGMA synchronous=EXTRA")
        database.executescript("CREATE TABLE metadata(store_id TEXT NOT NULL); CREATE TABLE requests(request_id TEXT PRIMARY KEY,digest TEXT NOT NULL,session_id TEXT NOT NULL,sequence INTEGER NOT NULL,wire BLOB NOT NULL,binding TEXT NOT NULL,receipt TEXT,phase TEXT NOT NULL,verifier_id TEXT NOT NULL,closed INTEGER NOT NULL DEFAULT 0,UNIQUE(session_id,sequence));")
        database.execute("INSERT INTO metadata VALUES(?)", (store_id,))
        database.commit()
    finally:
        database.close()
    if os.name != "nt":
        os.chmod(root / "ledger.sqlite3", 0o600)
    return store_id


def uptime_ms() -> int:
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32")
        kernel.GetTickCount64.restype = ctypes.c_ulonglong
        return int(kernel.GetTickCount64())
    return int(time.monotonic() * 1000)


class NativePairBackend:
    name = "native_pair_1375_v1"

    def __init__(self, mailbox_root: Path = DEFAULT_ROOT, *, store_id: str | None = None,
                 session_id: str | None = None, host_nonce: str | None = None,
                 experiment_sha256: str | None = None, whitelist_sha256: str | None = None,
                 live_identity_probe: Callable[[], dict] | None = None,
                 effect_verifier: Callable[[dict, dict, bytes], dict] | None = None,
                 clock: Callable[[], int] = uptime_ms):
        self.root = Path(mailbox_root).absolute()
        self.store_id, self.session_id, self.host_nonce = store_id, session_id, host_nonce
        self.experiment_sha256 = experiment_sha256.lower() if experiment_sha256 else None
        self.whitelist_sha256 = whitelist_sha256.lower() if whitelist_sha256 else None
        self.live_identity_probe, self.effect_verifier, self.clock = live_identity_probe, effect_verifier, clock
        self.lock = threading.RLock()

    @contextmanager
    def _db(self, write=False):
        _private_root(self.root)
        path = _safe(self.root, "ledger.sqlite3")
        if not path.is_file():
            raise MailboxError("ledger_missing", "Persistent ledger is missing; do not recreate it")
        uri = "file:" + quote(path.as_posix(), safe="/:") + ("?mode=rw" if write else "?mode=ro")
        db = sqlite3.connect(uri, uri=True, timeout=2)
        db.row_factory = sqlite3.Row
        try:
            identity = db.execute("SELECT store_id FROM metadata").fetchall()
            if len(identity) != 1 or identity[0][0] != self.store_id:
                raise MailboxError("store_mismatch", "Ledger identity differs from configured store")
            if write:
                db.execute("PRAGMA synchronous=EXTRA")
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.commit()
        except Exception:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    def _session_path(self, name, session_id=None):
        selected = session_id or self.session_id
        if not isinstance(selected, str) or not HEX32.fullmatch(selected):
            raise MailboxError("requires_new_native_handshake", "A new native EU4PAIR/1 session is required")
        return _safe(self.root, "sessions", selected, name)

    def _manifest(self, name, expected):
        if not expected or not HEX64.fullmatch(expected):
            raise MailboxError("empty_execution_whitelist", "Explicit pinned experiment and whitelist are required")
        raw = read_bounded(_safe(self.root, name), MAX_MANIFEST)
        if sha(raw) != expected:
            raise MailboxError("manifest_mismatch", f"Pinned {name} SHA mismatch")
        value = decode_json(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise MailboxError("invalid_manifest", "Manifest must be an object")
        return value

    def _configuration(self, action, parameters):
        experiment = self._manifest("experiment.json", self.experiment_sha256)
        whitelist = self._manifest("whitelist.json", self.whitelist_sha256)
        if set(experiment) != {"schema_version", "protocol", "purpose", "game_sha256", "dll_sha256", "world_generation_method", "world_generation_verified", "actions"}:
            raise MailboxError("invalid_manifest", "Unexpected experiment schema")
        if (type(experiment["schema_version"]) is not int or experiment["schema_version"] != 1 or experiment["protocol"] != PROTOCOL
                or experiment["purpose"] != "native_pair_mailbox_verified"
                or experiment["game_sha256"] != LOCAL_SHA256
                or experiment["world_generation_method"] != "native_load_counter_v1"
                or experiment["world_generation_verified"] is not True):
            raise MailboxError("requires_new_native_handshake", "Research experiments do not establish a production world-generation handshake")
        if not isinstance(experiment["dll_sha256"], str) or not re.fullmatch(r"[0-9A-F]{64}", experiment["dll_sha256"]):
            raise MailboxError("invalid_manifest", "Invalid DLL identity")
        if set(whitelist) != {"schema_version", "protocol", "game_sha256", "dll_sha256", "experiment_sha256", "entries"} or type(whitelist["schema_version"]) is not int or any(
                whitelist.get(key) != experiment[key] for key in ("schema_version", "protocol", "game_sha256", "dll_sha256")) or whitelist["experiment_sha256"] != self.experiment_sha256:
            raise MailboxError("manifest_mismatch", "Whitelist and experiment differ")
        verified = {}
        if not isinstance(experiment["actions"], list) or len(experiment["actions"]) > 64:
            raise MailboxError("invalid_manifest", "Invalid experiment action budget")
        for entry in experiment["actions"]:
            keys = {"action", "actor", "target", "verifier_id", "evidence_sha256", "dispatch_verified", "effects_verified", "reload_verified"}
            if not isinstance(entry, dict) or set(entry) != keys or any(entry[key] is not True for key in ("dispatch_verified", "effects_verified", "reload_verified")):
                raise MailboxError("invalid_manifest", "Action lacks dispatch/effect/reload verification")
            validate_request({"request_id": "manifest", "action": entry["action"], "parameters": {"actor": entry["actor"], "target": entry["target"]}})
            key = (entry["action"], entry["actor"], entry["target"])
            if key in verified or not isinstance(entry["verifier_id"], str) or not REQUEST_ID.fullmatch(entry["verifier_id"]) or not isinstance(entry["evidence_sha256"], str) or not HEX64.fullmatch(entry["evidence_sha256"]):
                raise MailboxError("invalid_manifest", "Duplicate or invalid action verification")
            verified[key] = entry
        entries = whitelist["entries"]
        if not isinstance(entries, list) or len(entries) > 64:
            raise MailboxError("invalid_manifest", "Invalid whitelist budget")
        selected, seen = [], set()
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"action", "actor", "target", "verifier_id", "evidence_sha256"}:
                raise MailboxError("invalid_manifest", "Unexpected whitelist fields")
            validate_request({"request_id": "manifest", "action": entry["action"], "parameters": {"actor": entry["actor"], "target": entry["target"]}})
            key = (entry["action"], entry["actor"], entry["target"])
            if key in seen or key not in verified or any(entry[field] != verified[key][field] for field in entry):
                raise MailboxError("manifest_mismatch", "Whitelist lacks exact experiment evidence")
            seen.add(key)
            if entry["action"] == action and (parameters is None or (entry["actor"], entry["target"]) == (parameters["actor"], parameters["target"])):
                selected.append(entry)
        if not selected:
            raise MailboxError("action_not_whitelisted", "This exact action/direction/country pair is not verified")
        return experiment, selected

    def _preflight(self, action, build, parameters, *, check_pending=True):
        if parameters is not None:
            validate_request({"request_id": "capability", "action": action, "parameters": parameters})
        if not self.session_id or not self.host_nonce:
            raise MailboxError("requires_new_native_handshake", "Current research DLLs have no EU4PAIR/1 mailbox handshake")
        _private_root(self.root)
        store = decode_json(read_bounded(_safe(self.root, "store.json"), MAX_RECORD).decode("utf-8"))
        if store != {"schema_version": 1, "store_id": self.store_id}:
            raise MailboxError("store_mismatch", "Configured store identity is missing or changed")
        experiment, entries = self._configuration(action, parameters)
        digest = (build.get("sha256") or build.get("executable_sha256") or "").upper()
        if digest != LOCAL_SHA256:
            raise MailboxError("unsupported_build", "Only the exact audited executable is supported")
        challenge = decode_record(read_bounded(self._session_path("handshake.request"), MAX_RECORD), "handshake_request")
        response = decode_record(read_bounded(self._session_path("handshake.response"), MAX_RECORD), "handshake_response")
        heartbeat = decode_record(read_bounded(self._session_path("heartbeat.record"), MAX_RECORD), "heartbeat")
        expected = {"store_id": self.store_id, "native_session_id": self.session_id, "host_nonce": self.host_nonce,
                    "game_sha256": LOCAL_SHA256.lower(), "dll_sha256": experiment["dll_sha256"].lower(),
                    "experiment_sha256": self.experiment_sha256, "whitelist_sha256": self.whitelist_sha256}
        for key in BASE + MANIFEST_BINDING:
            if challenge[key] != response[key] or heartbeat[key] != response[key] or key in expected and response[key] != expected[key]:
                raise MailboxError("handshake_mismatch", "Process/session/build handshake differs")
        for record in (response, heartbeat):
            if record["paused"] is not True:
                raise MailboxError("world_not_paused", "Production publication requires an explicitly paused native world")
            if any(record[key] is not (key != "thread_changed") for key in BOOL_FIELDS):
                raise MailboxError("requires_new_native_handshake", "Native world/thread/lifecycle/send gates are not verified")
        now = self.clock()
        if (not 0 <= now - heartbeat["uptime_ms"] <= FRESH_MS or response["uptime_ms"] < challenge["challenge_uptime_ms"]
                or heartbeat["uptime_ms"] < response["uptime_ms"] or heartbeat["frame_sequence"] < response["frame_sequence"]
                or heartbeat["window_thread"] != response["window_thread"]):
            raise MailboxError("stale_handshake", "Heartbeat is stale or regressed")
        if self.live_identity_probe is None:
            raise MailboxError("requires_live_identity_verifier", "DLL self-reported identity is not a live process proof")
        live = self.live_identity_probe()
        keys = ("pid", "process_creation_filetime", "world_generation", "window_thread")
        if (not isinstance(live, dict) or any(live.get(key) != heartbeat[key] for key in keys)
                or any(live.get(key) is not True for key in ("process_identity_verified", "loaded_dll_identity_verified", "world_generation_verified", "single_player_verified", "paused"))
                or live.get("game_sha256") != LOCAL_SHA256 or live.get("dll_sha256") != experiment["dll_sha256"]
                or type(live.get("observed_uptime_ms")) is not int or not 0 <= now - live["observed_uptime_ms"] <= FRESH_MS):
            raise MailboxError("live_identity_mismatch", "Independent live process/DLL/world identity is unverified or stale")
        if self.effect_verifier is None:
            raise MailboxError("requires_effect_verifier", "No independent effect verifier is installed")
        if check_pending:
            with self._db() as db:
                pending = db.execute("SELECT * FROM requests WHERE closed=0 LIMIT 2").fetchall()
            if len(pending) > 1 or any(self._observe(row)["status"] not in ("applied", "rejected", "failed") for row in pending):
                raise MailboxError("mailbox_pending", "A prior mailbox request is incomplete or unknown; never resubmit")
        # A terminal request does not clear a native session fault. Also reject
        # unsolicited ACKs that cannot be tied to this permanent intent ledger.
        with self._db() as db:
            latest = db.execute("SELECT * FROM requests WHERE session_id=? ORDER BY sequence DESC LIMIT 1", (self.session_id,)).fetchone()
        journal = self._session_path("native-events.jsonl")
        if journal.exists():
            if latest:
                self._read_events(journal, decode_record(latest["wire"], "submit"), require_healthy=True)
            elif read_bounded(journal, MAX_JOURNAL):
                raise MailboxError("event_chain_invalid", "Native events exist without durable host intents")
        return heartbeat, entries

    @staticmethod
    def _identity(wire):
        return {"store_id": wire["store_id"], "session_id": wire["native_session_id"], "pid": wire["pid"],
                "process_creation_filetime": wire["process_creation_filetime"], "world_generation": wire["world_generation"],
                **{key: wire[key].upper() for key in ("game_sha256", "dll_sha256", "experiment_sha256", "whitelist_sha256")}}

    def capability(self, action, build, parameters):
        try:
            with self.lock:
                wire, entries = self._preflight(action["action_id"], build, parameters)
                return {"ready": True, "dispatch_identity": self._identity(wire), "constraints": entries,
                        "reason": "Exact reviewed tuple and new native handshake verified"}
        except Exception as error:
            return {"ready": False, "reason_code": getattr(error, "code", "requires_new_native_handshake"), "reason": str(error)}

    def submit(self, request, build):
        validate_request(request)
        digest = sha(canonical(request).encode())
        with self.lock:
            # Durable duplicate decisions precede readiness; never publish again.
            with self._db() as db:
                old = db.execute("SELECT * FROM requests WHERE request_id=?", (request["request_id"],)).fetchone()
            if old:
                if old["digest"] != digest:
                    raise MailboxError("request_id_conflict", "Persistent request ID identifies another payload")
                if old["phase"] == "published" and old["receipt"]:
                    return decode_json(old["receipt"])
                raise MailboxError("dispatch_unknown", "Previous publication is unresolved; use read-only reconciliation")
            heartbeat, entries = self._preflight(request["action"], build, request["parameters"])
            with self._db(write=True) as db:
                # BEGIN IMMEDIATE serializes all publishers across processes.
                if db.execute("SELECT 1 FROM requests WHERE request_id=?", (request["request_id"],)).fetchone():
                    raise MailboxError("duplicate_publication_race", "Request was reserved concurrently; do not retry publication")
                pending = db.execute("SELECT * FROM requests WHERE closed=0 LIMIT 2").fetchall()
                if len(pending) > 1:
                    raise MailboxError("mailbox_pending", "Multiple unresolved publications")
                for row in pending:
                    observation = self._observe(row)
                    if observation["status"] not in ("applied", "rejected", "failed"):
                        raise MailboxError("mailbox_pending", "Previous request is unresolved")
                    db.execute("UPDATE requests SET closed=1 WHERE request_id=?", (row["request_id"],))
                sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM requests WHERE session_id=?", (self.session_id,)).fetchone()[0]
                values = {key: heartbeat[key] for key in BASE + MANIFEST_BINDING}
                values.update(sequence=sequence, request_id=request["request_id"], request_sha256=digest,
                              action=request["action"], **request["parameters"], deadline_uptime_ms=self.clock() + 5000)
                raw = encode_record("submit", values)
                binding = dict(self._identity(values), request_id=request["request_id"], request_sha256=digest,
                               backend=self.name, external_id=f"{self.store_id}/{self.session_id}/{sequence}", sequence=sequence)
                db.execute("INSERT INTO requests(request_id,digest,session_id,sequence,wire,binding,phase,verifier_id) VALUES(?,?,?,?,?,?,?,?)",
                           (request["request_id"], digest, self.session_id, sequence, raw, canonical(binding), "reserved", entries[0]["verifier_id"]))
            # Reservation is durable BEFORE a potentially consumable file exists.
            current, _ = self._preflight(request["action"], build, request["parameters"], check_pending=False)
            if self._identity(current) != self._identity(values):
                raise MailboxError("dispatch_unknown", "Identity changed after reservation; no automatic republish")
            if self.clock() >= values["deadline_uptime_ms"]:
                raise MailboxError("dispatch_unknown", "Publication deadline elapsed after reservation; never extend it")
            inbox = _safe(self.root, "sessions", self.session_id, "inbox", f"{sequence}.request")
            claimed = _safe(self.root, "sessions", self.session_id, "claimed", f"{sequence}.request")
            if claimed.exists():
                raise MailboxError("dispatch_unknown", "A prior claim exists for this publication")
            publish_exclusive(inbox, raw)
            receipt = self._receipt(binding, raw)
            with self._db(write=True) as db:
                db.execute("UPDATE requests SET phase='published',receipt=? WHERE request_id=? AND phase='reserved'",
                           (canonical(receipt), request["request_id"]))
            return receipt

    @staticmethod
    def _receipt(binding, raw):
        return {"status": "queued", "external_id": binding["external_id"], "binding": binding,
                "dispatch_outcome_known": True, "ownership_known": True,
                "evidence": [{"kind": "mailbox_publication", "reference": "mailbox:" + binding["external_id"], "sha256": sha(raw)}]}

    def _load_request(self, request):
        validate_request(request)
        digest = sha(canonical(request).encode())
        with self._db() as db:
            row = db.execute("SELECT * FROM requests WHERE request_id=?", (request["request_id"],)).fetchone()
        if row is None or row["digest"] != digest:
            raise MailboxError("request_not_found", "No matching durable request; reconciliation never creates one")
        return row

    def status(self, request, receipt):
        row = self._load_request(request)
        binding = decode_json(row["binding"])
        if not isinstance(receipt, dict) or receipt.get("binding") != binding or receipt.get("external_id") != binding["external_id"]:
            raise MailboxError("receipt_mismatch", "Receipt does not identify the durable publication")
        return self._observe(row)

    def reconcile(self, request, prior_record):
        row = self._load_request(request)
        binding = decode_json(row["binding"])
        expected = prior_record.get("result", {}).get("dispatch_context", {}).get("identity")
        if expected != {key: binding[key] for key in self._identity(decode_record(row["wire"], "submit"))}:
            raise MailboxError("receipt_mismatch", "Recovery differs from API's pre-dispatch identity")
        result = self._observe(row)
        if result["status"] in ("queued", "dispatched", "applied"):
            result["receipt"] = decode_json(row["receipt"]) if row["receipt"] else self._receipt(binding, row["wire"])
        return result

    def _observe(self, row):
        """Only reads bounded fixed paths. No ledger writes, retry or publication."""
        raw = bytes(row["wire"])
        wire = decode_record(raw, "submit")
        binding = decode_json(row["binding"])
        evidence = [{"kind": "durable_mailbox_intent", "reference": "ledger:" + binding["external_id"], "sha256": sha(raw)}]
        def result(state, *, unknown=False, ownership=False):
            value = {"status": state, "binding": binding, "evidence": list(evidence),
                     "dispatch_outcome_known": not unknown, "ownership_known": not ownership,
                     "game_effects_verified": state == "applied"}
            if unknown:
                value.update(reason_code="native_dispatch_unknown", automatic_retry=False,
                             uncertainty="ownership_unknown" if ownership else "dispatch_outcome_unknown")
            return value
        try:
            session = wire["native_session_id"]
            matches = []
            for directory in ("inbox", "claimed"):
                path = _safe(self.root, "sessions", session, directory, f"{wire['sequence']}.request")
                if path.exists():
                    if read_bounded(path, MAX_RECORD) != raw:
                        raise MailboxError("request_corrupted", "Published/claimed request differs from durable intent")
                    matches.append(directory)
            if len(matches) > 1:
                raise MailboxError("duplicate_claim", "Both inbox and claim exist")
            journal_path = self._session_path("native-events.jsonl", session)
            events = self._read_events(journal_path, wire) if journal_path.exists() else []
            if events:
                evidence.append({"kind": "native_event_chain", "reference": "native-events:" + binding["external_id"], "sha256": events[-1]["event_sha256"]})
            state = "queued"
            for event in events:
                name, data = event["event"], event["data"]
                if name == "dispatch_intent":
                    state = "dispatch_unknown"
                elif name == "dispatch_returned":
                    if data["returned"] is not True or data["container_consumed"] is not True or data["exception"] != 0 or data["ownership_known"] is not True:
                        return result("dispatch_unknown", unknown=True, ownership=True)
                    state = "dispatched"
                elif name == "rejected_before_dispatch":
                    if data["dispatch_excluded"] is not True or data["ownership_known"] is not True:
                        return result("dispatch_unknown", unknown=True, ownership=True)
                    state = "rejected"
                elif name == "ai_rejected":
                    if data["rejection_verified"] is not True or data["ownership_known"] is not True:
                        return result("dispatch_unknown", unknown=True, ownership=True)
                    state = "rejected"
                elif name == "session_fault":
                    if state in ("dispatch_unknown", "dispatched") or data["dispatch_may_have_occurred"] is not False or data["ownership_known"] is not True:
                        return result("dispatch_unknown", unknown=True, ownership=data["ownership_known"] is not True)
                    state = "failed"
                elif name == "effect_observed":
                    if self.effect_verifier is None:
                        continue
                    effect_path = _safe(self.root, "sessions", session, "effects", f"{wire['sequence']}.json")
                    proof_raw = read_bounded(effect_path, MAX_MANIFEST)
                    if sha(proof_raw) != data["effect_report_sha256"]:
                        raise MailboxError("effect_mismatch", "Independent effect artifact hash differs")
                    request = {"request_id": wire["request_id"], "action": wire["action"], "parameters": {"actor": wire["actor"], "target": wire["target"]}}
                    proof = self.effect_verifier(request, dict(binding), proof_raw)
                    if (not isinstance(proof, dict) or proof.get("binding") != binding or proof.get("game_effects_verified") is not True
                            or proof.get("verifier_id") != row["verifier_id"]):
                        raise MailboxError("effect_unverified", "Independent verifier did not establish the requested effect")
                    evidence.append({"kind": "independently_verified_effect", "reference": "effects:" + binding["external_id"], "sha256": sha(proof_raw)})
                    state = "applied"
            if state == "dispatch_unknown":
                return result(state, unknown=True, ownership=True)
            if state == "queued" and (matches != ["inbox"] or self.clock() > wire["deadline_uptime_ms"]):
                return result("dispatch_unknown", unknown=True)
            return result(state)
        except Exception as error:
            observation = result("dispatch_unknown", unknown=True)
            observation["observation_error"] = str(error)
            return observation

    def _read_events(self, path, wire, *, require_healthy=False):
        raw = read_bounded(path, MAX_JOURNAL)
        if raw and not raw.endswith(b"\n"):
            raise MailboxError("event_chain_invalid", "Truncated native event journal")
        events, previous, previous_time = [], "0" * 64, 0
        bound = {key: wire[key] for key in BASE + MANIFEST_BINDING}
        by_request, by_sequence, by_id, legality = {}, {}, {}, {}
        with self._db() as db:
            rows = db.execute("SELECT wire FROM requests WHERE session_id=? LIMIT ?", (wire["native_session_id"], MAX_EVENTS + 1)).fetchall()
        if len(rows) > MAX_EVENTS:
            raise MailboxError("event_chain_invalid", "Session intent count exceeds the bounded journal")
        intents = {}
        identity_fields = ("sequence", "request_id", "request_sha256", "action", "actor", "target")
        for row in rows:
            intent = decode_record(row["wire"], "submit")
            intents[intent["sequence"]] = {key: intent[key] for key in identity_fields}
        lines = raw.splitlines()
        if len(lines) > MAX_EVENTS:
            raise MailboxError("event_chain_invalid", "Native event count exceeds bound")
        for index, line in enumerate(lines, 1):
            if not line or len(line) > MAX_EVENT:
                raise MailboxError("event_chain_invalid", "Native event exceeds bound")
            event = decode_json(line.decode("utf-8"))
            if not isinstance(event, dict) or set(event) != EVENT_KEYS or event["protocol"] != PROTOCOL:
                raise MailboxError("event_chain_invalid", "Unexpected event schema")
            for key in BASE + MANIFEST_BINDING + ("sequence", "request_id", "request_sha256", "action", "actor", "target", "uptime_ms"):
                _field(key, event[key])
            digest = event["event_sha256"]
            without_digest = {key: value for key, value in event.items() if key != "event_sha256"}
            if (digest != sha(canonical(without_digest).encode()) or event["previous_event_sha256"] != previous
                    or type(event["event_sequence"]) is not int or event["event_sequence"] != index
                    or type(event["uptime_ms"]) is not int or event["uptime_ms"] < previous_time
                    or any(event[key] != value for key, value in bound.items())):
                raise MailboxError("event_chain_invalid", "Event hash/order/process/session identity differs")
            if not isinstance(event["utc"], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", event["utc"]):
                raise MailboxError("event_chain_invalid", "Event needs an explicit UTC timestamp")
            name, data = event["event"], event["data"]
            if not isinstance(name, str) or name not in EVENT_DATA or not isinstance(data, dict) or set(data) != EVENT_DATA[name]:
                raise MailboxError("event_chain_invalid", "Unknown event/data fields (paths are never accepted)")
            for key, value in data.items():
                if key in ("allowed", "ownership_known", "returned", "container_consumed", "dispatch_excluded", "rejection_verified", "dispatch_may_have_occurred") and type(value) is not bool:
                    raise MailboxError("event_chain_invalid", "Boolean event fields must be bool")
                if key == "exception" and (type(value) is not int or not 0 <= value <= 0xffffffff):
                    raise MailboxError("event_chain_invalid", "Invalid exception code")
                if key == "reason_code" and (not isinstance(value, str) or not REQUEST_ID.fullmatch(value)):
                    raise MailboxError("event_chain_invalid", "Invalid reason code")
                if key == "effect_report_sha256" and (not isinstance(value, str) or not HEX64.fullmatch(value)):
                    raise MailboxError("event_chain_invalid", "Invalid effect digest")
            request = {"request_id": event["request_id"], "action": event["action"], "parameters": {"actor": event["actor"], "target": event["target"]}}
            validate_request(request)
            if (type(event["sequence"]) is not int or not 1 <= event["sequence"] <= 0x7fffffffffffffff
                    or sha(canonical(request).encode()) != event["request_sha256"]):
                raise MailboxError("event_chain_invalid", "Event request digest/sequence differs")
            key = (event["sequence"], event["request_id"], event["request_sha256"])
            if intents.get(key[0]) != {field: event[field] for field in identity_fields}:
                raise MailboxError("event_chain_invalid", "Event has no matching durable host intent")
            if by_sequence.setdefault(key[0], key) != key or by_id.setdefault(key[1], key) != key:
                raise MailboxError("event_chain_invalid", "Request ID or sequence was reused")
            prior = by_request.get(key)
            allowed = {None: {"received", "rejected_before_dispatch"}, "received": {"claimed", "rejected_before_dispatch", "session_fault"},
                       "claimed": {"legality_result", "rejected_before_dispatch", "session_fault"},
                       "legality_result": {"dispatch_intent", "rejected_before_dispatch", "session_fault"},
                       "dispatch_intent": {"dispatch_returned", "session_fault"},
                       "dispatch_returned": {"effect_observed", "ai_rejected", "session_fault"}}
            if name not in allowed.get(prior, set()):
                raise MailboxError("event_chain_invalid", "Native event order violates the dispatch boundary")
            if name == "legality_result":
                legality[key] = data["allowed"]
            if name == "dispatch_intent" and (legality.get(key) is not True or data["ownership_known"] is not True):
                raise MailboxError("event_chain_invalid", "Dispatch requires legality and known pre-call ownership")
            if require_healthy and name == "session_fault":
                raise MailboxError("native_session_fault", "A native session fault requires a new verified session")
            by_request[key] = name
            if event["request_id"] == wire["request_id"] or event["sequence"] == wire["sequence"]:
                if any(event[field] != wire[field] for field in ("sequence", "request_id", "request_sha256", "action", "actor", "target")):
                    raise MailboxError("event_chain_invalid", "Selected request was rebound")
                events.append(event)
            previous, previous_time = digest, event["uptime_ms"]
        return events
