"""Experimental, real EU4 1.37.5 TAG command transport.

Commands are consumed by the injected main-thread host. Queue dispatch is not
AI acceptance or a verified game effect. No process is opened at import time.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import struct
import types

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "bridge/native/tag_diplomacy_1375_v31/build-7/build/build.json"
GAME_SHA = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
PURPOSE = "tag_command_1375_v30"
SCHEMA = "EU4TAGCOMMAND/1"
ACTIONS = (
    "offer_vassalization", "cancel_vassalization", "royal_marriage", "break_marriage",
    "improve_relations", "stop_improving_relations", "guarantee", "revoke_guarantee",
    "build_spy_network", "stop_building_spy_network", "curry_favors", "stop_currying_favors",
    "offer_fleet_basing_rights", "insult", "form_coalition", "support_independence",
    "trade_favors_for_gold", "trade_favors_for_men", "trade_favors_for_sailors",
    "trade_favors_for_trust", "trade_favors_for_war_prep",
)
FAMILIES = (0,0,1,1,2,2,3,3,4,4,5,5,6,7,8,9,10,11,12,13,14)
LAUNCHER = ROOT / "work/candidates/v19-spy-real-client-r2-1375/launcher.py"
LAUNCHER_SHA = "a7944c63e044e195a242b417afbea27c001ef2cae1f9d1a721bf3b83352845fe"


def require(ok, message):
    if not ok:
        raise ValueError(message)


class PublicationUnknownError(RuntimeError):
    """Publication stopped after reservation; stages are not native outcomes."""
    def __init__(self, error, identity, progress):
        super().__init__(str(error))
        self.result = {"error":"publication_unknown", "state":"publication_unknown",
                       "message":str(error), "identity":dict(identity),
                       "results":[dict(row) for row in progress],
                       "automatic_retry":False, "gameplay_effects_verified":False}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2)+"\n").encode("ascii")


def decode(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique,
                      parse_constant=lambda _: require(False, "Nonfinite JSON"))


def read(path, maximum):
    path = Path(path)
    before = path.stat()
    require(not path.is_symlink() and not getattr(before, "st_file_attributes", 0)&0x400,
            "Linked runtime file")
    require(before.st_nlink == 1 and 0 < before.st_size <= maximum, "File size/link bound")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        data = stream.read(maximum+1)
        after = os.fstat(stream.fileno())
    require((opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino)
            and (opened.st_size, opened.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
            and len(data) == before.st_size, "File changed during read")
    return data


def write_new(path, data):
    with Path(path).open("xb") as stream:
        require(stream.write(data) == len(data), "Short write")
        stream.flush()
        os.fsync(stream.fileno())


def validate_command(command, actions=ACTIONS):
    require(type(command) is dict and set(command) == {"request_id", "action", "actor", "target"},
            "Command requires exactly request_id, action, actor, target")
    require(type(command["request_id"]) is str and re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", command["request_id"]),
            "Invalid request_id")
    require(type(command["action"]) is str and command["action"] in actions,
            "Action has no native binding in this host")
    for key in ("actor", "target"):
        require(type(command[key]) is str and re.fullmatch("[A-Z0-9]{3}", command[key]), "Invalid "+key+" TAG")
    require(command["actor"] != command["target"], "Actor and target must differ")
    return dict(command)


def validate_identity(identity):
    require(type(identity) is dict and set(identity) == {"pid", "creation", "session", "dll_sha256", "manifest_sha256"},
            "Exact session identity required")
    require(type(identity["pid"]) is int and 0 < identity["pid"] <= 0xffffffff, "Invalid PID")
    for key, length in (("creation",16), ("session",32), ("dll_sha256",64), ("manifest_sha256",64)):
        require(type(identity[key]) is str and re.fullmatch(f"[0-9a-f]{{{length}}}", identity[key])
                and int(identity[key],16), "Invalid "+key)
    return dict(identity)


def wire(identity, sequence, expires, command, *, purpose=PURPOSE, actions=ACTIONS, limit=64):
    validate_identity(identity)
    command = validate_command(command, actions)
    require(type(sequence) is int and 1 <= sequence <= limit, "Sequence bound")
    require(type(expires) is int and 0 < expires <= 0xffffffffffffffff, "Expiry bound")
    return (f"{SCHEMA}\npurpose={purpose}\ngame_sha256={GAME_SHA}\npid={identity['pid']}\n"
            f"creation={identity['creation']}\nsession={identity['session']}\ndll_sha256={identity['dll_sha256']}\n"
            f"manifest_sha256={identity['manifest_sha256']}\nsequence={sequence}\nexpires={expires}\n"
            f"action={command['action']}\nactor={command['actor']}\ntarget={command['target']}\nsend=1\n").encode("ascii")


def boot(identity, *, purpose=PURPOSE):
    validate_identity(identity)
    return (f"EU4TAGBOOT/1\npurpose={purpose}\ngame_sha256={GAME_SHA}\npid={identity['pid']}\n"
            f"creation={identity['creation']}\nsession={identity['session']}\ndll_sha256={identity['dll_sha256']}\n"
            f"manifest_sha256={identity['manifest_sha256']}\ndisposable=1\nsend=1\n").encode("ascii")


def verified_graph():
    data = read(LAUNCHER, 64*1024)
    require(digest(data) == LAUNCHER_SHA, "Frozen loader changed")
    module = types.ModuleType("_tag_command_frozen_loader")
    module.__file__ = str(LAUNCHER)
    exec(compile(data, str(LAUNCHER), "exec"), module.__dict__)
    return module.verified_graph()


class WindowsRuntime:
    """Held PID/creation and exact loaded DLL checks; loader remains explicit."""
    def __init__(self):
        self.graph = verified_graph()
        self.readonly = self.graph.local("readonly.py")

    def now(self):
        return self.readonly.now_ms()

    def check(self, identity, build, manifest, owner=None):
        held = self.readonly.Held(identity)
        try:
            held.identity_check()
            canonical = held.injector._canonical
            modules = held.modules()
            game = [base for base,path in modules if canonical(path) == canonical(held.injector.GAME)]
            dll = [base for base,path in modules if canonical(path) == canonical(build/manifest["DLL"])]
            research = [path for _,path in modules if Path(path).name.lower().startswith(
                ("eu4_bridge_", "eu4_pair_", "eu4_spy_", "eu4_tag_command_"))]
            require(len(game) == len(dll) == len(research) == 1, "Expected single game and command DLL")
            pe = self.readonly.pe_header(held.memory(dll[0],8192))
            require(pe["timestamp"] == manifest["PE_timestamp"] and pe["size_of_image"] == manifest["SizeOfImage"],
                    "Loaded DLL header mismatch")
            # A freshly loaded game can display the pause banner while its
            # explicit manual-pause bit is still zero. The native guard needs
            # that bit; reject before reserving/publishing any command.
            def pointer(address):
                return struct.unpack("<Q",held.memory(address,8))[0]
            game_object = pointer(game[0]+0x233fe78)
            server = pointer(game_object+0x1e00)
            pause_manager = pointer(server+0x418)
            require(held.memory(pause_manager+0x48,1) == b"\x01",
                    "Explicit manual pause required; automatic pause after loading is insufficient")
            self.readonly.disk_identity(held.injector.GAME)
            if owner is not None:
                require(held.window_thread() == owner, "Owner thread changed")
            held.identity_check()
        finally:
            held.close()

    def load(self, identity, build, manifest):
        held = self.readonly.Held(identity)
        try:
            require(not any(Path(path).name.lower().startswith(("eu4_bridge_", "eu4_pair_", "eu4_spy_", "eu4_tag_command_"))
                            for _,path in held.modules()), "Research DLL already loaded; restart required")
            injector = self.graph.load(ROOT/"work/native/inject_probe.py")
            held.identity_check()
            result = injector._run(argparse.Namespace(pid=identity["pid"], dll=str(build/manifest["DLL"]),
                                  timeout_ms=10000, ack_test_save=True), expected_game_hash=GAME_SHA)
            held.identity_check()
            return result
        finally:
            held.close()


class TagCommandBackend:
    def __init__(self, manifest=DEFAULT_MANIFEST, *, runtime=None, test_history_dir=None):
        self.manifest_path = Path(manifest).resolve()
        self.build = self.manifest_path.parent
        self.runtime = runtime  # Construct the OS adapter only for an explicit operation.
        self.test_history_dir = (ROOT/"work/runtime/tag-command-development-history-1375"
                                 if test_history_dir is None else Path(test_history_dir).resolve())
        self.manifest_sha = digest(read(self.manifest_path,1024*1024))
        initial = decode(read(self.manifest_path,1024*1024))
        self.purpose = initial.get("purpose")
        self.actions, self.prefix, self.excluded = ACTIONS, "tagcommand30", []
        self.bindings, self.categories = [], []
        self.limit = 64
        if self.purpose == "tag_command_1375_v31":
            self.config_path = ROOT/"bridge/tag_actions_1375_v31.json"
            config = decode(read(self.config_path,1024*1024))
            require(config["schema"] == "EU4TAGACTIONS/1" and config["purpose"] == self.purpose,
                    "Invalid V31 action configuration")
            self.actions = tuple(config["actions"])
            self.prefix, self.excluded = config["session_prefix"], config["excluded"]
            self.bindings, self.categories = config["bindings"], config["categories"]
            require([b["action"] for b in self.bindings] == list(self.actions)
                    and len(set(self.actions)) == len(self.actions)
                    and all(b["category"] in self.categories for b in self.bindings),
                    "Action metadata and native registry differ")
            self.limit = config["request_limit"]
            require(self.limit == 128, "Unsupported V31 command limit")
        self.manifest = self.verify()

    def verify(self):
        raw = read(self.manifest_path,1024*1024)
        require(digest(raw) == self.manifest_sha, "Build manifest changed")
        m = decode(raw)
        require(m["schema"] == "EU4TAGBUILD/1" and m["purpose"] == self.purpose
                and self.purpose in (PURPOSE,"tag_command_1375_v31")
                and m["game_sha256"] == GAME_SHA and m["no_send"] is False, "Wrong native host")
        if self.purpose != PURPOSE:
            require(m.get("actions") == list(self.actions)
                    and self.config_path.relative_to(ROOT).as_posix() in m["source_pins"],
                    "Native registry and API actions differ")
        require(Path(m["DLL"]).name == m["DLL"], "DLL path must be a basename")
        dll = read(self.build/m["DLL"],16*1024*1024)
        require({"bytes":len(dll),"sha256":digest(dll)} == m["dll"], "DLL changed")
        require(type(m["source_pins"]) is dict and 1 <= len(m["source_pins"]) <= 128, "Source count")
        for name, expected in m["source_pins"].items():
            require(not Path(name).is_absolute() and ".." not in Path(name).parts, "Invalid source pin")
            data = read(ROOT/name,4*1024*1024)
            require({"bytes":len(data),"sha256":digest(data)} == expected, "Build source changed: "+name)
        return m

    def os_runtime(self):
        if self.runtime is None:
            self.runtime = WindowsRuntime()
        return self.runtime

    def capabilities(self):
        return {"protocol":SCHEMA, "purpose":self.purpose, "experimental":True, "actions":list(self.actions),
                "excluded":self.excluded,
                "bindings":self.bindings, "categories":self.categories,
                "request_limit":self.limit,
                "command_fields":["request_id", "action", "actor", "target"],
                "parameters_supported":False,
                "action_lookup":{"endpoint":"/native/v1/actions/{action}",
                                 "search_endpoint":"/native/v1/actions",
                                 "cli":"lookup --action <action>; search --query <text>",
                                 "available":self.purpose == "tag_command_1375_v31",
                                 "includes_excluded_research_labels":True,
                                 "evaluated_in_game":False},
                "condition_reference":{"endpoint":"/native/v1/conditions/{action}",
                                       "cli":"conditions --action <action>",
                                       "available":self.purpose == "tag_command_1375_v31",
                                       "evaluated_in_game":False,
                                       "complete_legality_documented":False},
                "batch_expiry":{"maximum_ttl_ms":self.maximum_ttl_ms,
                                "minimum_default_ttl_ms":60000,
                                "per_command_default_ms":10000 if self.maximum_ttl_ms > 60000 else 0,
                                "default_margin_ms":30000 if self.maximum_ttl_ms > 60000 else 0,
                                "shared_absolute_deadline":True},
                "actor":"caller-supplied TAG", "target":"caller-supplied TAG", "requires_pause":True,
                "requires_explicit_manual_pause":True,
                "idempotency_scope":"exact process creation and loaded session",
                "automatic_retry":False,
                "actor_must_be_human_player":False,
                "arbitrary_actor_runtime_verified":False, "production_ready":False,
                "dispatch_does_not_prove_ai_acceptance":True, "manifest_sha256":self.manifest_sha}

    @property
    def maximum_ttl_ms(self):
        return 1800000 if self.purpose == "tag_command_1375_v31" else 60000

    def session(self, identity):
        identity = validate_identity(identity)
        require(identity["manifest_sha256"] == self.manifest_sha and identity["dll_sha256"] == self.manifest["dll"]["sha256"],
                "Session/build mismatch")
        return self.build/f"{self.prefix}-{identity['pid']}-{identity['creation']}-{identity['session']}"

    def load(self, pid, creation):
        identity = validate_identity({"pid":pid, "creation":creation, "session":secrets.token_hex(16),
                                     "dll_sha256":self.manifest["dll"]["sha256"], "manifest_sha256":self.manifest_sha})
        self.verify()
        intent = self.build/f"loader-intent-{pid}-{creation}.json"
        packet = self.build/f"bootstrap-{pid}-{creation}.request"
        require(not packet.exists(), "Bootstrap already exists; never load again")
        write_new(intent,encode({"identity":identity,"outcome":"unknown_until_loader_returns"}))
        write_new(packet,boot(identity,purpose=self.purpose))
        result = self.os_runtime().load(identity,self.build,self.manifest)
        report = {"identity":identity,"installation":result,"experimental":True}
        write_new(self.build/f"session-{pid}-{creation}.json",encode(report))
        return report

    @staticmethod
    def key_path(directory, request_id):
        return directory/("key-"+digest(request_id.encode("ascii"))+".json")

    def status(self, identity, request_id=None):
        from bridge.tag_command_audit import AuditSnapshot
        return AuditSnapshot(self.session(identity), identity, purpose=self.purpose,
                             actions=self.actions, limit=self.limit).status(request_id)

    def publish(self, identity, commands, *, ttl_ms=None, test_only=False):
        require(type(commands) is list and 1 <= len(commands) <= self.limit, "Batch size bound")
        commands = [validate_command(c,self.actions) for c in commands]
        require(len({c["request_id"] for c in commands}) == len(commands), "Duplicate request_id in batch")
        maximum_ttl = self.maximum_ttl_ms
        if ttl_ms is None:
            # V31 rechecks 51 native families and resolves the caller's TAGs.
            # A full 128-command batch cannot finish in the old 60s window.
            ttl_ms = max(60000, len(commands)*10000+30000) if maximum_ttl > 60000 else 60000
        require(type(ttl_ms) is int and 1 <= ttl_ms <= maximum_ttl, "TTL bound")
        if test_only:
            from bridge.tag_test_policy import DevelopmentTestHistory, clean_rejection, historical_dispatch_blocks
            require(not {c["action"] for c in commands}&historical_dispatch_blocks(),
                    "Historically dispatched action: test forbidden")
            policy = decode(read(ROOT/"work/reports/diplomacy-no-repeat-test-policy-1375.json",1024*1024))
            require(not {c["action"] for c in commands}&set(policy["blocked_actions"]), "Previously successful action: test forbidden")
            closed = decode(read(ROOT/"bridge/tag_test_history_1375.json",128*1024))
            require(closed["schema"] == "EU4TAG-TEST-HISTORY/1"
                    and closed["game_sha256"] == GAME_SHA and closed["final_integration_closed"]
                    and closed["effect_success_claimed"] is False, "Invalid closed test history")
            source = Path(closed["source"])
            require(not source.is_absolute() and ".." not in source.parts, "Invalid test evidence path")
            evidence_raw = read(ROOT/source, 2*1024*1024)
            require(digest(evidence_raw) == closed["source_sha256"], "Closed test evidence changed")
            evidence = decode(evidence_raw)
            require(evidence["completed_without_unattempted_requests"] is True
                    and closed["requests"] == [{"command":r["command"], "state":r["state"]}
                                               for r in evidence["results"]], "Test history differs from evidence")
            original_ids = {r["command"]["request_id"] for r in evidence["results"]}
            require(not {c["request_id"] for c in commands}&original_ids,
                    "Original final-integration request: test forbidden")
            blocked = set()
            for row in evidence["results"]:
                result = row["native_result"] or {}
                # The sparse lease rejection receipt has no allocation/cleanup
                # proof. Keep it blocked until independently audited evidence
                # is admitted, rather than defaulting absent fields to zero.
                if row["state"] != "native_rejected" or not clean_rejection(result):
                    blocked.add(row["command"]["action"])
            require(not {c["action"] for c in commands}&blocked,
                    "Dispatched or uncertain final action: test forbidden")
            require(len({c["action"] for c in commands}) == len(commands), "One test per action per batch")
            test_history = DevelopmentTestHistory(self.test_history_dir)
            test_history.check(commands)
        self.verify()
        directory = self.session(identity)
        lock = directory/"publisher.lock"
        write_new(lock,b"Permanent on uncertain publisher termination; inspect before recovery.\n")
        reservation_started = preserve_lock = False
        progress = []
        try:
            existing = [self.key_path(directory,c["request_id"]).exists() for c in commands]
            if any(existing):
                require(all(existing), "Mixed old/new batch; never resume partial publication automatically")
                for command in commands:
                    old = decode(read(self.key_path(directory,command["request_id"]),8192))
                    require(old["command"] == command, "Idempotency conflict")
                return {"reused":True,"results":[self.status(identity,c["request_id"]) for c in commands]}
            status = self.status(identity)
            require(status["hook_installed"] and not status["terminal"], "Host not ready")
            intents = list(directory.glob("key-*.json"))
            require(len(intents) <= self.limit and len(intents)+len(commands) <= self.limit, "Session command limit reached")
            first = len(intents)+1
            require(len(status["results"]) == len(intents), "Prior commands not finished; inspect first")
            runtime = self.os_runtime()
            runtime.check(identity,self.build,self.manifest,status["owner_thread"])
            expires = runtime.now()+ttl_ms
            packets = []
            progress = [{"request_id":command["request_id"], "sequence":first+index,
                         "publication_stage":"not_started"}
                        for index,command in enumerate(commands)]
            if test_only:
                def test_reservation_progress(index, complete):
                    nonlocal reservation_started
                    reservation_started = True
                    progress[index]["publication_stage"] = ("development_reserved" if complete
                                                             else "development_reservation_started")
                # Recheck under the central mutex and retain immutable records
                # before any game request can be reserved or published.
                test_history.reserve(self.manifest_path,identity,commands,first,
                                     on_progress=test_reservation_progress)
            for seq,command in enumerate(commands,first):
                require(not any((directory/f"{seq}.{suffix}").exists() for suffix in ("request","claim","pending")), "Sequence already reserved")
                packet = wire(identity,seq,expires,command,purpose=self.purpose,actions=self.actions,limit=self.limit)
                intent = encode({"identity":identity,"sequence":seq,
                                 "expires":expires,"command":command,"wire_sha256":digest(packet)})
                stage = progress[seq-first]
                # Even a failed write can leave a partial intent. Retain the
                # lock from here onward and never infer a native outcome.
                reservation_started = True
                stage["publication_stage"] = "intent_write_started"
                write_new(self.key_path(directory,command["request_id"]),intent)
                stage["publication_stage"] = "intent_retained"
                stage["publication_stage"] = "pending_write_started"
                write_new(directory/f"{seq}.pending",packet)
                stage["publication_stage"] = "pending_retained"
                packets.append((seq,packet))
            self.verify()
            for seq,packet in packets:
                runtime.check(identity,self.build,self.manifest,status["owner_thread"])
                require(runtime.now() < expires, "Expired before publication; preserve intents")
                require(read(directory/f"{seq}.pending",1024) == packet, "Changed pending command")
                source,target = directory/f"{seq}.pending",directory/f"{seq}.request"
                require(not target.exists(), "Existing request; never overwrite")
                progress[seq-first]["publication_stage"] = "publication_attempted"
                if os.name == "nt":
                    kernel = ctypes.WinDLL("kernel32",use_last_error=True)
                    kernel.MoveFileExW.argtypes = [ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint32]
                    kernel.MoveFileExW.restype = ctypes.c_int
                    if not kernel.MoveFileExW(str(source),str(target),8):
                        raise ctypes.WinError(ctypes.get_last_error())
                else:  # Offline transport tests; real EU4 host is Windows only.
                    os.link(source,target)
                    source.unlink()
                progress[seq-first]["publication_stage"] = "published"
            return {"identity":dict(identity),"published":[dict(c,sequence=seq) for (seq,_),c in zip(packets,commands)],
                    "expires":expires,"reused":False,"gameplay_effects_verified":False}
        except BaseException as error:
            if reservation_started:
                preserve_lock = True
                if isinstance(error, Exception):
                    raise PublicationUnknownError(error,identity,progress) from error
            raise
        finally:
            if not preserve_lock:
                try:
                    lock.unlink()
                except Exception as error:
                    if reservation_started:
                        raise PublicationUnknownError(error,identity,progress) from error
                    raise
