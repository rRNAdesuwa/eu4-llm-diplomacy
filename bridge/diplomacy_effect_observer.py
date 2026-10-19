"""Request-correlated, bounded EU4 1.37.5 state observation. No game calls.

The only process operation is QUERY/VM_READ through the existing held-process
reader. Consistent external samples are observations, never a world lease.
"""
from __future__ import annotations

from datetime import datetime, timezone
import ctypes as C
import hashlib
import json
from pathlib import Path
import re
import struct
import time

from bridge.tag_command_backend import (DEFAULT_MANIFEST, GAME_SHA, ROOT,
    TagCommandBackend, WindowsRuntime, decode, digest, read, require,
    validate_command, validate_identity)
from bridge.tag_command_audit import recorded_snapshot

SCHEMA = "EU4DIPLOMACY-SNAPSHOT/1"
SENTINEL = 0x2D2D2D
COUNTRY_VT = 0x1C574A0
DEPENDENCY_VT = 0x1C81758
DEFAULT_STORE = ROOT / "work/runtime/effect-observations-v1"
SOURCE_MANIFEST = ROOT / "bridge/diplomacy_observer_manifest_1375.json"
LIMITS = dict(calls=4096, bytes=512*1024, single_read=65536, index_entries=256)
EVIDENCE_FILES = (
    "work/inspect_tag31_corrective_pairs.py",
    "work/probe_corrective_favors_r3_1375.py",
    "work/probe_annex_context_r3_1375.py",
    "work/probe_knowledge_context_r3_1375.py",
    "work/reports/war-peace-api-20261015-r4/peace/lifecycle/observer-contract.json",
    "work/reports/war-peace-api-20261015-r4/war/host-contract.json",
    "work/reports/diplomacy-effect-profiles-20261015/annex-task-layout/static.json",
)


def pins():
    raw = read(SOURCE_MANIFEST, 65536)
    manifest = decode(raw)
    require(manifest["schema"] == "EU4DIPLOMACY-OBSERVER-MANIFEST/1"
            and manifest["game_sha256"] == GAME_SHA
            and manifest["native_manifest_sha256"] == digest(read(DEFAULT_MANIFEST, 1024*1024)),
            "Observer/executable/native manifest identity changed")
    result = {}
    for name, expected in manifest["source_pins"].items():
        require(not Path(name).is_absolute() and ".." not in Path(name).parts, "Invalid observer source path")
        data = read(ROOT/name, 2*1024*1024)
        actual = {"bytes": len(data), "sha256": digest(data)}
        require(actual == expected, "Observer source/evidence changed: "+name)
        result[name] = actual
    require(set(EVIDENCE_FILES) <= set(result), "Observer evidence set missing")
    result[SOURCE_MANIFEST.relative_to(ROOT).as_posix()] = {"bytes": len(raw), "sha256": digest(raw)}
    return result


def ptr(value):
    require(type(value) is int and 0x10000 <= value < 2**47, "Noncanonical pointer")
    return value


def full_handle(value, count=1380, *, tag=None):
    require(type(value) is int and 0 < value < 2**64, "Invalid handle encoding")
    slot = (value >> 32) & 0xffff
    raw_tag = (value & 0xffffff).to_bytes(3, "little")
    require(value >> 56 != 0 and (value >> 48) & 255 == 0
            and (value >> 24) & 255 == 0 and 0 < slot < min(count, 32768)
            and re.fullmatch(rb"[A-Z0-9]{3}", raw_tag), "Not a valid ordinary country handle")
    actual = raw_tag.decode("ascii")
    require(tag is None or actual == tag, "Handle TAG differs from request")
    return slot, actual


class BudgetReader:
    def __init__(self, reader):
        self.reader = reader
        self.calls = self.bytes = self.largest = 0

    def read(self, address, size):
        ptr(address)
        require(type(size) is int and 0 < size <= LIMITS["single_read"]
                and address+size <= 2**47, "Read bound")
        require(self.calls < LIMITS["calls"] and self.bytes+size <= LIMITS["bytes"], "Shared read budget")
        self.calls += 1
        self.bytes += size
        self.largest = max(self.largest, size)
        value = self.reader.read(address, size)
        require(type(value) is bytes and len(value) == size, "Short memory read")
        return value

    def q(self, address):
        return struct.unpack("<Q", self.read(address, 8))[0]

    def i(self, address):
        return struct.unpack("<i", self.read(address, 4))[0]

    def b(self, address):
        return self.read(address, 1)[0]


class HeldRPMPort:
    """Dedicated VM_READ port; never changes the frozen PE-header reader."""
    def __init__(self, held):
        self.held = held

    def read(self, address, size):
        # BudgetReader validates the complete address and shared byte/call
        # bounds before this port. This port has no write or execute operation.
        buffer, got = C.create_string_buffer(size), C.c_size_t()
        require(self.held.kernel.ReadProcessMemory(self.held.handle, C.c_void_p(address),
                buffer, size, C.byref(got)) and got.value == size, "Exact VM_READ unavailable")
        return buffer.raw


def roots(r, base):
    game, db = ptr(r.q(base+0x233FE78)), ptr(r.q(base+0x233D8D0))
    require(r.q(game) == base+0x1CB00C8, "Game type changed")
    array = ptr(r.q(db+0x118))
    capacity, count = struct.unpack("<ii", r.read(db+0x120, 8))
    require(count == 1380 and count <= capacity <= 4096, "Country table profile changed")
    server = ptr(r.q(game+0x1E00))
    require(r.q(server) == base+0x1CB8460, "Single player server type changed")
    pause = ptr(r.q(server+0x418))
    require(r.q(pause+0x50) == server, "Pause owner changed")
    value = dict(game=hex(game), database=hex(db), array=hex(array), count=count,
        capacity=capacity, date=r.i(game+0x1DD0), server=hex(server), pause=hex(pause),
        manual_pause=r.b(pause+0x48), reset=r.b(game+0x7485),
        load_source=r.q(game+0x74C8), recalculating=r.b(game+0x2521),
        ironman=r.b(game+0x24D0), current_player=r.q(game+0x1E60),
        alternate_player=r.q(game+0x1E68), selector=r.b(game+0x1E66))
    full_handle(value["current_player"], count)
    require(value["date"] > 0 and value["manual_pause"] in (0, 1)
            and value["reset"] == value["load_source"] == value["recalculating"] == value["ironman"] == 0,
            "Loading/reset/cache recalculation/unsupported world state")
    require(value["selector"] == 0 and value["alternate_player"] == SENTINEL,
            "Alternate player/selector is unsupported")
    return value


def country(r, base, root, handle, tag=None):
    slot, actual = full_handle(handle, root["count"], tag=tag)
    address = ptr(r.q(int(root["array"], 16)+8*slot))
    header = r.read(address, 0x28)
    require(struct.unpack_from("<Q", header)[0] == base+COUNTRY_VT
            and struct.unpack_from("<I", header, 8)[0] == 357
            and struct.unpack_from("<Q", header, 0x20)[0] == handle, "Complete country identity changed")
    return dict(address=hex(address), handle=hex(handle), tag=actual, slot=slot)


def typed_country_or_sentinel(r, base, root, handle):
    if handle == SENTINEL:
        return hex(handle)
    country(r, base, root, handle)
    return hex(handle)


def relation(r, owner, other, base=None):
    address = int(owner["address"], 16)
    embedded = address+0x14F8
    header = r.read(embedded, 0x30)
    if base is None:
        base = r.q(address)-COUNTRY_VT
    require(struct.unpack_from("<QI", header) == (base+0x1C4F5F8, 357), "Relation root type/marker mismatch")
    records, end, capacity = struct.unpack_from("<QQQ", header, 0x18)
    require(struct.unpack_from("<Q", header, 0x10)[0] == address, "Relation root owner mismatch")
    ptr(records)
    require(records <= end <= capacity < 2**47 and (end-records) % 0x48 == 0
            and (capacity-records) % 0x48 == 0 and capacity-records <= 4096*0x48
            and other["slot"] < (end-records)//0x48, "Relation record vector bounds")
    record = records+other["slot"]*0x48
    data = r.read(record, 0x48)
    require(struct.unpack_from("<QQQ", data) == (embedded, int(owner["handle"], 16),
            int(other["handle"], 16)), "Relation root/complete pair mismatch")
    require(r.read(embedded, 0x30) == header, "Relation root changed within sample")
    return dict(root=embedded, record=record, data=data,
        trust=data[0x1e], favors=struct.unpack_from("<i", data, 0x20)[0],
        deadline=struct.unpack_from("<i", data, 0x30)[0])


def index(r, root, offset, other_slot, count):
    header = r.read(root+offset, 16)
    array, capacity, used = struct.unpack("<Qii", header)
    require(0 <= used <= LIMITS["index_entries"] and used <= capacity <= 4096, "Signed index count/capacity bound")
    require((capacity == 0 and array == 0) or
            (capacity > 0 and 0x10000 <= array < array+capacity*16 <= 2**47), "Index allocation metadata mismatch")
    raw = r.read(ptr(array), used*16) if used else b""
    entries = []
    for slot, obj in struct.iter_unpack("<i4xQ", raw):
        require(0 < slot < min(count, 32768), "Index country slot invalid")
        ptr(obj)
        entries.append((slot, obj))
    require(len({s for s, _ in entries}) == len(entries), "Duplicate indexed country")
    require(r.read(root+offset, 16) == header, "Index header changed within sample")
    selected = [obj for slot, obj in entries if slot == other_slot]
    return dict(count=used, member=bool(selected), object=selected[0] if selected else None,
                records_sha256=digest(raw))


def dependency_key(r, definition):
    header = r.read(ptr(definition)+0x10, 32)
    length, capacity = struct.unpack_from("<QQ", header, 16)
    require(0 < length <= min(capacity, 96) and capacity <= 4096, "Dependency key string bound")
    raw = header[:16] if capacity < 16 else r.read(ptr(struct.unpack_from("<Q", header)[0]), length+1)
    require(raw[length:length+1] == b"\0", "Dependency key terminator")
    value = raw[:length].decode("ascii")
    require(re.fullmatch(r"[a-z0-9_]{1,96}", value), "Dependency key grammar")
    return value


def sample_pair(r, base, identity, command, handles):
    root = roots(r, base)
    actor = country(r, base, root, handles[0], command["actor"])
    target = country(r, base, root, handles[1], command["target"])
    outgoing, incoming = relation(r, actor, target, base), relation(r, target, actor, base)
    left = index(r, outgoing["root"], 0x128, target["slot"], root["count"])
    right = index(r, incoming["root"], 0x128, actor["slot"], root["count"])
    require(left["object"] == right["object"], "Bilateral dependency mismatch")
    key = None
    if left["object"]:
        obj = left["object"]
        body = r.read(obj, 0x48)
        require(struct.unpack_from("<Q", body)[0] == base+DEPENDENCY_VT and body[0x28] == 0,
                "Dependency type/inactive state changed")
        first, second = struct.unpack_from("<QQ", body, 0x10)
        require({first, second} == set(handles), "Dependency complete endpoints mismatch")
        key = dependency_key(r, struct.unpack_from("<Q", body, 0x40)[0])
    annex = index(r, outgoing["root"], 0x200, target["slot"], root["count"])
    annex_reverse = index(r, incoming["root"], 0x200, actor["slot"], root["count"])
    require(annex["object"] == annex_reverse["object"], "Bilateral annexation indexes disagree")
    annex_task = None
    if annex["object"] is not None:
        body = r.read(annex["object"], 0x48)
        first, second = struct.unpack_from("<QQ", body, 0x10)
        require(struct.unpack_from("<QI", body) == (base+0x1CDE020, 357)
                and {first, second} == set(handles) and body[0x28] == 0,
                "Indexed annex task type/endpoints/removal state mismatch")
        started = struct.unpack_from("<i", body, 0x20)[0]
        require(0 < started <= root["date"], "Annex task start date invalid")
        annex_task = dict(address=hex(annex["object"]), vtable_rva="0x1cde020", marker=357,
            actor_handle=hex(first), target_handle=hex(second), started_raw_date=started,
            removed_byte_28=body[0x28], raw_word_28=struct.unpack_from("<H", body, 0x28)[0],
            complete_endpoint_pair_validated=True, state="in_progress", completion_proven=False)
    resources = {"treasury_milli": 0xBB0, "manpower_milli": 0xDB8, "sailors_milli": 0xDC0}
    for item in (actor, target):
        address = int(item["address"], 16)
        item["resources"] = {name: r.i(address+offset) for name, offset in resources.items()}
        item["sharing_counts"] = {"signed_count_17dc": r.i(address+0x17dc), "signed_count_17c4": r.i(address+0x17c4)}
    a, t = int(actor["address"], 16), int(target["address"], 16)
    pair = dict(actor_tag=command["actor"], target_tag=command["target"],
        actor_handle=actor["handle"], target_handle=target["handle"],
        coalition_actor_handle=typed_country_or_sentinel(r, base, root, r.q(a+0x18F8)),
        actor_overlord_handle=typed_country_or_sentinel(r, base, root, r.q(a+0x18F0)),
        target_overlord_handle=typed_country_or_sentinel(r, base, root, r.q(t+0x18F0)),
        dependency_type=key, dependency_present=left["member"],
        annex_index_count=annex["count"], annex_target_member=annex["member"],
        annex_object_pointer=hex(annex["object"]) if annex["object"] else None)
    war_prep = {"actor_handle": hex(r.q(t+0x272C)), "deadline": r.i(t+0x2728)}
    # Re-resolve identities and every root after the projection. No raw pointer
    # is retained into a later capture or treated as an engine object lease.
    require(country(r, base, root, handles[0]) == {k: actor[k] for k in ("address", "handle", "tag", "slot")}
            and country(r, base, root, handles[1]) == {k: target[k] for k in ("address", "handle", "tag", "slot")},
            "Selected country identity changed after projection")
    require(roots(r, base) == root, "World/date/guards changed within sample")
    return dict(schema=SCHEMA, identity={"pid": identity["pid"], "creation": identity["creation"]},
        now_raw=root["date"], roots=root, pair=pair, actor=actor, target=target,
        incoming={"trust": incoming["trust"], "favors": incoming["favors"]},
        target_war_prep=war_prep,
        knowledge={"actor_counts": actor["sharing_counts"], "target_counts": target["sharing_counts"],
                   "pair_object_identity_proven": False},
        annex_task=annex_task, annex_task_object_type_proven=annex_task is not None)


class RuntimeCapture:
    """One exact held process; only external memory reads, never injection."""
    def __init__(self, identity, backend=None):
        self.identity = validate_identity(identity)
        self.backend = backend or TagCommandBackend()
        self.held = None

    def __enter__(self):
        self.backend.verify()
        self.runtime = WindowsRuntime()
        self.held = self.runtime.readonly.Held(self.identity)
        try:
            self.held.identity_check()
            self.modules = self.held.modules()
            canonical = self.held.injector._canonical
            games = [b for b, p in self.modules if canonical(p) == canonical(self.held.injector.GAME)]
            require(len(games) == 1, "Expected exact main module")
            self.base = ptr(games[0])
            disk = self.runtime.readonly.disk_identity(self.held.injector.GAME)
            require(self.runtime.readonly.pe_header(self.held.memory(self.base, 8192)) == disk, "Loaded main PE mismatch")
            self.initial_pins = pins()
            return self
        except BaseException:
            self.held.close()
            self.held = None
            raise

    def __exit__(self, *unused):
        if self.held:
            self.held.close()

    def capture(self, command, binding=None):
        command = validate_command(command, self.backend.actions)
        started = time.perf_counter()
        r = BudgetReader(HeldRPMPort(self.held))
        root = roots(r, self.base)
        if binding:
            handles = (binding["actor_handle"], binding["target_handle"])
        else:
            raw = r.read(int(root["array"], 16), root["count"]*8)
            selected = {}
            for address, in struct.iter_unpack("<Q", raw):
                if not address:
                    continue
                value = r.q(ptr(address)+0x20)
                name = (value & 0xffffff).to_bytes(3, "little")
                for tag in (command["actor"], command["target"]):
                    if name == tag.encode("ascii"):
                        require(tag not in selected, "Duplicate selected TAG")
                        full_handle(value, root["count"], tag=tag)
                        selected[tag] = value
            require(set(selected) == {command["actor"], command["target"]}, "Selected TAG unavailable")
            handles = (selected[command["actor"]], selected[command["target"]])
        first = sample_pair(r, self.base, self.identity, command, handles)
        second = sample_pair(r, self.base, self.identity, command, handles)
        require(first == second, "Two selected state passes differ; observation unknown")
        self.held.identity_check()
        require(self.held.modules() == self.modules, "Module set changed")
        require(pins() == self.initial_pins, "Observer evidence/source changed during capture")
        return dict(schema="EU4DIPLOMACY-CAPTURE/1", identity=self.identity, command=command,
            game_sha256=GAME_SHA, captured_utc=datetime.now(timezone.utc).isoformat(),
            two_pass_equal=True, snapshot=first, source_pins=self.initial_pins,
            duration_ms=round((time.perf_counter()-started)*1000, 3),
            rpm_budget=dict(calls=r.calls, bytes=r.bytes, largest_read=r.largest, limits=LIMITS),
            native_calls=0, memory_written=False, requests_published=0,
            atomic_main_thread_snapshot=False, world_epoch_proven=False,
            limitations=["Two consistent external reads can miss transient changes or ABA reuse.",
                "No engine predicate, lazy initializer, action or destructor is called.",
                "Task presence proves an observed index; completion requires its own postcondition.",
                "Read failures or changing state never mean action rejection."])


def import_probe(report, command, identity):
    """Normalize a retained, two-pass legacy probe without accessing the game."""
    require(report.get("two_pass_equal") is True and len(report.get("passes", [])) == 2
            and report["passes"][0] == report["passes"][1], "Unproven legacy sample")
    require((report["pid"], report["creation"]) == (identity["pid"], identity["creation"]), "Legacy process differs")
    v = report["passes"][0]
    p = next((p for p in v["pairs"] if (p["action"], p["actor_tag"], p["target_tag"]) ==
              (command["action"], command["actor"], command["target"])), None)
    require(p is not None, "Legacy exact command pair missing")
    actor, target = v["countries"][command["actor"]], v["countries"][command["target"]]
    dep = p["dependency"]
    obj = dep["object"]
    pair = dict(actor_tag=command["actor"], target_tag=command["target"], actor_handle=actor["handle"],
        target_handle=target["handle"], coalition_actor_handle=v["country_coalition_handles"][command["actor"]]["handle"],
        actor_overlord_handle=dep["actor_overlord_handle"], target_overlord_handle=dep["target_overlord_handle"],
        dependency_type=obj["type_name"]["name"] if obj else None, dependency_present=obj is not None)
    if command["actor"] == "FRA" and command["target"] == "ORL" and "annex_context_supplement" in v:
        a = v["annex_context_supplement"]["annexation_index_FRA_to_ORL"]
        pair.update(annex_index_count=a["count_signed"], annex_target_member=a["index_member_observed"],
                    annex_object_pointer=a["matching_entries"][0]["object_pointer_raw"] if a["matching_entries"] else None)
    return dict(schema=SCHEMA, identity={"pid": identity["pid"], "creation": identity["creation"]},
        pair=pair, roots=v["roots"], now_raw=v["roots"]["date"],
        actor={**actor, "resources": v.get("selected_resources", {}).get(command["actor"], {})},
        target={**target, "resources": v.get("selected_resources", {}).get(command["target"], {})},
        incoming={"trust": p["target_to_actor"]["trust_raw_byte"], "favors": p["target_to_actor"]["favors_raw_milli"]})


class EffectObserver:
    def __init__(self, identity, *, backend=None, store=DEFAULT_STORE, capture_factory=RuntimeCapture):
        self.identity = validate_identity(identity)
        self.backend = backend or TagCommandBackend()
        self.store = Path(store) / f"{identity['pid']}-{identity['creation']}-{identity['session']}"
        self.capture_factory = capture_factory

    def directory(self, request_id):
        require(type(request_id) is str and re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", request_id), "Invalid request ID")
        return self.store / digest(request_id.encode("ascii"))

    def prepare(self, command, *, legacy_probe=None):
        command = validate_command(command, self.backend.actions)
        directory = self.directory(command["request_id"])
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "baseline.json"
        require(not path.exists(), "Baseline already exists; do not replace it")
        if legacy_probe is None:
            session = self.backend.session(self.identity)
            intent = self.backend.key_path(session, command["request_id"])
            lock = session/"publisher.lock"
            require(not intent.exists() and not lock.exists(),
                    "Request already reserved; only an explicit retained baseline import is allowed")
            with self.capture_factory(self.identity, self.backend) as reader:
                capture = reader.capture(command)
            require(not intent.exists() and not lock.exists(),
                    "Publisher reserved or started during capture; baseline timing is unknown")
            baseline = capture["snapshot"]
            provenance = dict(kind="live_before_publication", capture=capture)
        else:
            raw = read(Path(legacy_probe), 8*1024*1024)
            baseline = import_probe(decode(raw), command, self.identity)
            provenance = dict(kind="explicit_retained_probe_import", path=str(Path(legacy_probe).resolve()),
                bytes=len(raw), sha256=digest(raw), exclusion_of_external_causes_proven=False)
        value = dict(schema="EU4DIPLOMACY-BASELINE/1", identity=self.identity, command=command,
                     snapshot=baseline, provenance=provenance)
        with path.open("x", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=True, indent=2)
        return dict(request_id=command["request_id"], baseline=str(path), sha256=digest(path.read_bytes()), native_calls=0)

    def observe(self, request_id, *, record=True):
        from bridge.diplomacy_effect_profiles import evaluate_profile, profile_catalog
        status = recorded_snapshot(self.backend.manifest_path, self.identity).status(request_id)
        command = status["command"]
        result = dict(schema="EU4DIPLOMACY-OBSERVATION/1", request_id=request_id, identity=self.identity,
            command=command, transport_state=status["state"], audit_sha256=status["audit_sha256"],
            captured_utc=datetime.now(timezone.utc).isoformat(), native_calls=0, memory_written=False,
            requests_published=0, saves_written=0, automatic_command_retry=False,
            persistence_verified=False, AI_acceptance_verified=False, completion_state="evidence_insufficient")
        if command["action"] not in {row["action"] for row in profile_catalog()}:
            result.update(effect={"status": "unsupported", "selected_effect_verified": False})
        elif not status["binding"] or status["state"] != "dispatched":
            result.update(effect={"status": "unknown", "selected_effect_verified": False,
                "reason": "No proven dispatched command; observation is not a retry decision"})
        else:
            try:
                path = self.directory(request_id) / "baseline.json"
                raw = read(path, 2*1024*1024) if path.exists() else None
                before = decode(raw) if raw else None
                if before:
                    require(before["identity"] == self.identity and before["command"] == command, "Baseline identity/request mismatch")
                with self.capture_factory(self.identity, self.backend) as reader:
                    capture = reader.capture(command, status["binding"])
                result["capture"] = capture
                result["baseline_sha256"] = digest(raw) if raw else None
                effect = evaluate_profile(command["action"], before["snapshot"] if before else None,
                                          capture["snapshot"], status)
                result["effect"] = effect
                if effect.get("selected_effect_verified"):
                    result["completion_state"] = "in_progress" if command["action"] == "annex_vassal" else "selected_effect_observed"
            except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
                result["effect"] = dict(status="unknown", selected_effect_verified=False,
                    reason="Live state unavailable or unstable", failure={"type": type(exc).__name__, "message": str(exc)})
        if record:
            directory = self.directory(request_id)
            directory.mkdir(parents=True, exist_ok=True)
            name = f"observation-{time.time_ns()}.json"
            with (directory/name).open("x", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=True, indent=2)
            result["record"] = str(directory/name)
        return result
