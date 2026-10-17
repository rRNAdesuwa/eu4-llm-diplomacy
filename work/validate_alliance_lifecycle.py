"""Offline, bounded validation of the passive alliance lifecycle trace.

The validator consumes an installation record, its build manifest, and a JSONL
control probe.  It never attaches to EU4 and never imports the bridge/native
implementation.  A record is accepted only when the log contains a complete
clone -> wrapper -> serialization_begin -> generic command-entry chain, with
the same session, object generation, addresses, canonical action fingerprint,
and full protocol key ``(origin, sequence, flags)``.  Sequence integers by
themselves are deliberately insufficient.

``serialization_begin`` is reported as an observation stage.  It is not a
submission or enqueue receipt.  The report is therefore suitable for auditing
passive evidence, while remaining conservative when the probe dropped or did
not identify a lifecycle event.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Iterator, Mapping


MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_PROBE_BYTES = 128 * 1024 * 1024
MAX_LINE_BYTES = 256 * 1024
MAX_EVENTS = 250_000
MAX_ISSUES = 256
MAX_PENDING = 8_192
MAX_HASH_FILE_BYTES = 16 * 1024 * 1024
HASH_BLOCK_BYTES = 1024 * 1024

LIFECYCLE_EVENT = "native_alliance_lifecycle"
ENTRY_EVENTS = {
    "native_alliance_command_entry_observed",
    "native_alliance_generic_command_entry",
}
DROP_EVENTS = {
    "native_alliance_lifecycle_drop",
    "observation_incomplete",
    "native_alliance_command_entry_drop",
}
FREE_KINDS = {"free", "deallocator", "release", "destructor_free"}
LIFECYCLE_KINDS = {
    "clone", "wrapper", "destructor", "destructor_return",
    "serialization_begin", *FREE_KINDS,
}
KNOWN_CONTROL_EVENTS = {
    "control_frame",
    "diplomacy_observer_health",
    "diplomatic_command_observed",
    "native_alliance_validity_observed",
    "native_alliance_reason_raw",
    "native_alliance_reason_item",
    "native_alliance_inspection",
    "native_alliance_inspection_failed",
    "command_execution_trace_installed",
    "hook_installed",
    "alliance_rule_observer_installed",
    "diplomacy_observer_installed",
    "popup_confirmation_begin",
    "popup_confirmation_callbacks_returned",
    "control_console_result",
    "control_loaded_pause_requested",
}


class InputError(ValueError):
    """A bounded input or schema error."""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _int(value: Any, *, minimum: int | None = None,
         maximum: int | None = None) -> int | None:
    if _is_int(value):
        result = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            result = int(text, 0)
        except ValueError:
            return None
    else:
        return None
    if minimum is not None and result < minimum:
        return None
    if maximum is not None and result > maximum:
        return None
    return result


def _address(value: Any) -> int | None:
    value = _int(value, minimum=0x10000)
    return value


def _field(event: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in event:
            return event[name]
    return None


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _same(value_a: Any, value_b: Any) -> bool:
    """Compare JSON scalar fields without treating missing as equal."""

    return value_a is not None and value_b is not None and value_a == value_b


def _canonical_handle(value: Any) -> Any:
    """Normalize a native handle without discarding slot/generation bits.

    A three-byte country tag is useful for display, but it is not an identity
    key: two native handles can share the tag while differing in slot or
    generation.  Full integer handles therefore remain integers here.
    """

    if isinstance(value, str):
        text = value.strip()
        if text.lower().startswith("0x"):
            parsed = _int(text)
            if parsed is not None:
                value = parsed
            else:
                return text.upper()
        else:
            return text.upper()
    if _is_int(value):
        return int(value)
    return value


def _fingerprint(shape: Mapping[str, Any] | None) -> tuple[Any, Any, Any, Any] | None:
    if not isinstance(shape, Mapping):
        return None
    actor = _field(shape, "actor10", "actor_handle", "actor", "actor_field")
    recipient = _field(shape, "recipient20", "recipient_handle", "recipient", "recipient_field")
    state = _field(shape, "state34", "state_raw", "state")
    variant = _field(shape, "variant38", "variant")
    if variant is None:
        action_id = shape.get("action_id")
        if action_id == "offer_alliance":
            variant = 1
        elif action_id == "dissolve_alliance":
            variant = 0
    if actor is None or recipient is None or state is None or variant is None:
        return None
    actor = _canonical_handle(actor)
    recipient = _canonical_handle(recipient)
    if _is_int(state):
        state = int(state)
    if _is_int(variant):
        variant = int(variant)
    return actor, recipient, state, variant


def _protocol_key(event: Mapping[str, Any], *, lifecycle: bool = False) -> tuple[int, int, int] | None:
    """Return the complete native protocol key, never a sequence-only key."""

    if lifecycle:
        # These names are the observed wrapper offsets.  Falling back to a
        # generic protocol field would erase the distinction this lifecycle
        # probe is meant to audit.
        origin = event.get("origin48")
        sequence = event.get("seq4c")
        flags = event.get("rawflag4a")
    else:
        origin = _field(event, "origin", "origin48", "protocol_origin")
        sequence = _field(event, "protocol_sequence", "seq4c", "sequence32", "sequence")
        flags = _field(event, "protocol_flags", "rawflag4a", "flags")
    origin = _int(origin, minimum=0, maximum=0xFFFF)
    sequence = _int(sequence, minimum=0, maximum=0xFFFFFFFF)
    flags = _int(flags, minimum=0, maximum=0xFF)
    if origin is None or sequence is None or flags is None:
        return None
    return origin, sequence, flags


def _shape_key(shape: Mapping[str, Any] | None) -> tuple[Any, ...] | None:
    if not isinstance(shape, Mapping):
        return None
    keys = (
        "vtable_rva", "discriminator", "actor10", "mirror18", "recipient20",
        "date28", "date2c", "envoy30", "state34", "variant38", "proposal3c",
    )
    values = tuple(shape.get(key) for key in keys)
    if any(value is None for value in values):
        return None
    # Layout values are captured by the native observer.  Address is excluded
    # intentionally: clone source and target must have the same layout, while
    # being distinct object addresses.
    return values


def _shape_address(shape: Mapping[str, Any] | None) -> int | None:
    return _address(shape.get("addr")) if isinstance(shape, Mapping) else None


def _native_forward_contract(event: Mapping[str, Any]) -> bool:
    """Require the passive hook's one-call forwarding contract."""

    value = event.get("native_forward_count_by_hook_contract")
    if value is None:
        # Keep older fixtures readable while preferring the renamed hook
        # contract field.  A missing count is still rejected by the
        # real-record check.
        value = event.get("native_call_count")
    return _is_int(value) and value == 1


def _native_return_contract(event: Mapping[str, Any], kind: str) -> bool:
    value = event.get("native_return_observed")
    if not isinstance(value, bool):
        return False
    # Clone/wrapper/destructor-return callbacks observe a native return value.
    # Serializer and pre-call destructor callbacks intentionally snapshot
    # before the original call.
    return value is (kind in {"clone", "wrapper", "destructor_return"})


def _real_event(event: Mapping[str, Any]) -> bool:
    return event.get("synthetic") is not True and event.get("real_record") is not False


def _event_kind(event: Mapping[str, Any]) -> str | None:
    if event.get("event") == LIFECYCLE_EVENT:
        kind = event.get("kind")
        return kind if isinstance(kind, str) else None
    if event.get("event") in ENTRY_EVENTS:
        return "generic_entry"
    if event.get("event") in DROP_EVENTS:
        return "drop"
    event_kind = event.get("kind")
    if isinstance(event_kind, str) and event_kind in FREE_KINDS:
        return event_kind
    if event.get("event") in {"native_alliance_free", "native_alliance_lifecycle_free"}:
        return "free"
    return None


def _event_session(event: Mapping[str, Any]) -> str | None:
    value = event.get("session_id")
    return value if isinstance(value, str) and value else None


def _event_sequence(event: Mapping[str, Any], kind: str | None) -> int | None:
    if kind in {"clone", "wrapper", "destructor", "destructor_return",
                "serialization_begin"}:
        return _int(event.get("sequence"), minimum=1)
    if kind == "generic_entry":
        return _int(_field(event, "event_sequence", "log_sequence"), minimum=1)
    return None


def _callback_ordinal(event: Mapping[str, Any], kind: str | None) -> int | None:
    """Return the shared native callback ordinal when the event carries it.

    r15 emits lifecycle ``sequence`` and command-entry ``callback_sequence``
    from the same interlocked counter.  Older traces have no entry ordinal;
    those continue to use their physical line order as a compatibility
    fallback and remain subject to the old conservative gate.
    """

    if kind in {"clone", "wrapper", "destructor", "destructor_return",
                "serialization_begin"}:
        return _int(event.get("sequence"), minimum=1)
    if kind == "generic_entry":
        return _int(event.get("callback_sequence"), minimum=1)
    if kind in FREE_KINDS or kind == "free":
        return _int(_field(event, "callback_sequence", "sequence"), minimum=1)
    return None


def _bounded_json(path: Path, limit: int) -> Any:
    try:
        size = path.stat().st_size
    except OSError as error:
        raise InputError(f"cannot stat {path}: {error}") from error
    if size > limit:
        raise InputError(f"input exceeds bounded size ({size}>{limit}): {path}")
    try:
        with path.open("r", encoding="utf-8-sig") as stream:
            return json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InputError(f"invalid JSON {path}: {error}") from error


def _stream_sha256(path: Path) -> tuple[str | None, str | None]:
    """Hash one bounded artifact without loading it into memory."""

    try:
        size = path.stat().st_size
    except OSError as error:
        return None, f"stat:{error}"
    if size > MAX_HASH_FILE_BYTES:
        return None, f"too_large:{size}"
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(HASH_BLOCK_BYTES)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as error:
        return None, f"read:{error}"
    return digest.hexdigest(), None


def _artifact_path(manifest_path: Path, declared: Any) -> Path | None:
    if not isinstance(declared, str) or not declared:
        return None
    declared_path = Path(declared)
    if declared_path.is_absolute() and declared_path.is_file():
        return declared_path
    # Manifests created on another checkout retain an absolute Windows path.
    # For offline replay, use only the basename beside the supplied manifest;
    # do not follow an arbitrary missing path elsewhere on disk.
    return manifest_path.parent / declared_path.name


def _jsonl(path: Path, limit: int) -> Iterator[tuple[int, dict[str, Any] | None, str | None]]:
    try:
        size = path.stat().st_size
    except OSError as error:
        raise InputError(f"cannot stat {path}: {error}") from error
    if size > limit:
        raise InputError(f"probe exceeds bounded size ({size}>{limit}): {path}")
    try:
        with path.open("rb") as stream:
            for line_number, raw in enumerate(stream, 1):
                if len(raw) > MAX_LINE_BYTES:
                    yield line_number, None, "line_too_large"
                    continue
                try:
                    value = json.loads(raw.decode("utf-8-sig" if line_number == 1 else "utf-8"))
                except (UnicodeError, json.JSONDecodeError):
                    yield line_number, None, "invalid_json"
                    continue
                if not isinstance(value, dict):
                    yield line_number, None, "non_object"
                    continue
                yield line_number, value, None
    except OSError as error:
        raise InputError(f"cannot read {path}: {error}") from error


@dataclass
class Generation:
    address: int
    generation: int
    first_line: int
    shape: dict[str, Any] | None = None
    first_ordinal: int | None = None
    destructor_line: int | None = None
    destructor_ordinal: int | None = None
    free_line: int | None = None
    free_ordinal: int | None = None

    @property
    def ref(self) -> tuple[int, int]:
        return self.address, self.generation


@dataclass
class LifecycleObservation:
    line: int
    session_id: str
    kind: str
    event: dict[str, Any]
    callback_ordinal: int | None = None
    source_address: int | None = None
    target_address: int | None = None
    source_ref: tuple[int, int] | None = None
    target_ref: tuple[int, int] | None = None
    wrapper_address: int | None = None
    wrapper_action: int | None = None
    fingerprint: tuple[Any, Any, Any, Any] | None = None
    layout: tuple[Any, ...] | None = None
    protocol_key: tuple[int, int, int] | None = None


@dataclass
class ValidatorState:
    installation_session: str
    issues: list[dict[str, Any]] = field(default_factory=list)
    lifecycle: list[LifecycleObservation] = field(default_factory=list)
    generic: list[LifecycleObservation] = field(default_factory=list)
    generations: dict[int, list[Generation]] = field(default_factory=dict)
    last_event_sequence: dict[str, int] = field(default_factory=dict)
    session_mismatch: int = 0
    missing_session: int = 0
    unknown_events: int = 0
    ignored_events: int = 0
    dropped_events: int = 0
    malformed_lines: int = 0
    event_count: int = 0
    truncated: bool = False
    lifecycle_install_ack: dict[str, Any] | None = None
    serializer_install_ack: dict[str, Any] | None = None
    diplomacy_install_ack: dict[str, Any] | None = None
    free_events: list[tuple[int, int | None, int]] = field(default_factory=list)
    callback_ordinals: list[tuple[int, int, str]] = field(default_factory=list)

    def issue(self, code: str, line: int | None = None, **details: Any) -> None:
        if len(self.issues) >= MAX_ISSUES:
            return
        entry: dict[str, Any] = {"code": code}
        if line is not None:
            entry["line"] = line
        entry.update(details)
        self.issues.append(entry)

    def _history(self, address: int) -> list[Generation]:
        return self.generations.setdefault(address, [])

    @staticmethod
    def _position(line: int, ordinal: int | None) -> int:
        # Callback ordinals are the native ordering domain.  The line number
        # is retained only for legacy traces without the shared ordinal.
        return ordinal if ordinal is not None else line

    @classmethod
    def _generation_position(cls, generation: Generation) -> int:
        return cls._position(generation.first_line, generation.first_ordinal)

    def active_generation(self, address: int, line: int,
                          ordinal: int | None = None) -> Generation | None:
        position = self._position(line, ordinal)
        history = self.generations.get(address, [])
        for generation in reversed(history):
            if self._generation_position(generation) <= position \
                    and generation.destructor_ordinal is None \
                    and generation.destructor_line is None:
                return generation
            if self._generation_position(generation) <= position \
                    and (generation.destructor_ordinal is not None
                         or generation.destructor_line is not None) \
                    and generation.free_ordinal is None \
                    and generation.free_line is None:
                # A destructor has closed this generation.  Do not cross it.
                return None
        return None

    def generation_at(self, address: int, line: int,
                      ordinal: int | None = None) -> Generation | None:
        position = self._position(line, ordinal)
        history = self.generations.get(address, [])
        for generation in reversed(history):
            if self._generation_position(generation) <= position:
                destructor_position = (
                    generation.destructor_ordinal
                    if generation.destructor_ordinal is not None
                    else generation.destructor_line
                )
                if destructor_position is not None and position > destructor_position:
                    return generation
                return generation
        return None

    def establish(self, address: int, line: int, shape: dict[str, Any] | None,
                  *, ordinal: int | None = None,
                  allow_reuse: bool = True) -> Generation:
        history = self._history(address)
        current = history[-1] if history else None
        if current is None:
            current = Generation(address, 1, line, shape,
                                 first_ordinal=ordinal)
            history.append(current)
            return current
        if (current.destructor_ordinal is not None
                or current.destructor_line is not None
                or current.free_ordinal is not None
                or current.free_line is not None):
            if allow_reuse:
                current = Generation(address, current.generation + 1, line, shape,
                                     first_ordinal=ordinal)
                history.append(current)
                self.issue("ADDRESS_REUSE_NEW_GENERATION", line, address=hex(address),
                            generation=current.generation)
                return current
            return current
        if shape is not None and current.shape is None:
            current.shape = shape
        return current

    def close_destructor(self, address: int, line: int,
                         ordinal: int | None = None) -> Generation | None:
        generation = self.generation_at(address, line, ordinal)
        if generation is None:
            self.issue("DESTRUCTOR_ADDRESS_UNKNOWN", line, address=hex(address))
            return None
        if (generation.destructor_ordinal is not None
                or generation.destructor_line is not None):
            self.issue("DUPLICATE_DESTRUCTOR", line, address=hex(address),
                       generation=generation.generation)
        else:
            generation.destructor_line = line
            generation.destructor_ordinal = ordinal
        return generation

    def close_free(self, address: int, line: int,
                   ordinal: int | None = None) -> Generation | None:
        generation = self.generation_at(address, line, ordinal)
        if generation is None:
            self.issue("FREE_ADDRESS_UNKNOWN", line, address=hex(address))
            return None
        if generation.destructor_line is None:
            self.issue("FREE_BEFORE_DESTRUCTOR", line, address=hex(address),
                       generation=generation.generation)
        else:
            destructor_position = (
                generation.destructor_ordinal
                if generation.destructor_ordinal is not None
                else generation.destructor_line
            )
            free_position = self._position(line, ordinal)
            if destructor_position is not None and free_position <= destructor_position:
                self.issue("DESTRUCTOR_ORDER_INVALID", line, address=hex(address),
                           generation=generation.generation)
        if generation.free_line is not None or generation.free_ordinal is not None:
            self.issue("DUPLICATE_FREE", line, address=hex(address),
                       generation=generation.generation)
        else:
            generation.free_line = line
            generation.free_ordinal = ordinal
        return generation


def _shape_dict(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None


_SHAPE_FIELDS = {
    "addr", "readable", "matched", "handles_canonical", "tracked", "vtable_rva",
    "discriminator", "actor10", "mirror18", "recipient20", "date28", "date2c",
    "envoy30", "state34", "variant38", "proposal3c", "actor_handle",
    "recipient_handle", "state_raw", "variant", "actor", "recipient", "state",
    "action_id", "actor_field", "recipient_field",
}
_EVENT_FIELDS = {
    "event", "kind", "session_id", "sequence", "event_sequence", "source_event_id",
    "target_event_id", "source", "target", "out_value", "wrapper", "wrapper_address",
    "wrapper_action", "action", "action_address", "command", "command_address",
    "callback_sequence", "native_result", "native_flags", "result_readable",
    "origin48", "seq4c", "rawflag4a", "origin", "protocol_origin",
    "protocol_sequence", "sequence32", "protocol_flags", "flags", "readable",
    "wrapper_identity", "wrapper_readable", "native_forward_count_by_hook_contract",
    "native_call_count", "native_return_observed", "synthetic", "real_record",
    "actor_handle", "recipient_handle", "actor_field", "recipient_field", "state_raw",
    "variant", "action_id", "state", "business_result", "dropped", "address",
    "object", "source_address", "target_address",
}


def _compact_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Retain only bounded evidence fields; never retain an arbitrary JSON blob."""

    compact: dict[str, Any] = {
        key: value for key, value in event.items() if key in _EVENT_FIELDS
    }
    for key in ("source", "target"):
        value = event.get(key)
        if isinstance(value, Mapping):
            compact[key] = {name: item for name, item in value.items()
                            if name in _SHAPE_FIELDS}
    return compact


def _addresses_for_free(event: Mapping[str, Any]) -> int | None:
    for name in ("address", "object", "source_address", "target_address", "command", "action"):
        address = _address(event.get(name))
        if address is not None:
            return address
    for name in ("source", "target"):
        address = _shape_address(event.get(name))
        if address is not None:
            return address
    return None


def _lifecycle_observation(event: Mapping[str, Any], line: int,
                           session_id: str, kind: str,
                           state: ValidatorState) -> LifecycleObservation:
    source = _shape_dict(event.get("source"))
    target = _shape_dict(event.get("target"))
    source_address = _shape_address(source)
    target_address = _shape_address(target)
    observation = LifecycleObservation(
        line=line,
        session_id=session_id,
        kind=kind,
        event=_compact_event(event),
        callback_ordinal=_callback_ordinal(event, kind),
        source_address=source_address,
        target_address=target_address,
        fingerprint=_fingerprint(source or target),
        layout=_shape_key(source or target),
        protocol_key=_protocol_key(event, lifecycle=True),
    )
    if kind == "wrapper":
        wrapper_address = _address(_field(event, "out_value", "wrapper", "wrapper_address"))
        wrapper_action = _address(_field(event, "wrapper_action", "action", "action_address"))
        observation.wrapper_address = wrapper_address
        observation.wrapper_action = wrapper_action
    elif kind == "serialization_begin":
        wrapper_address = _address(_field(event, "out_value", "wrapper", "wrapper_address"))
        wrapper_action = _address(_field(event, "wrapper_action", "action", "action_address"))
        observation.wrapper_address = wrapper_address
        observation.wrapper_action = wrapper_action
    # Generation association is intentionally deferred until the whole JSONL
    # stream has been parsed.  r15 callbacks are flushed by independent
    # queues, so physical line order is not a valid object-lifetime order.
    return observation


def _generic_observation(event: Mapping[str, Any], line: int,
                         session_id: str) -> LifecycleObservation:
    command = _address(_field(event, "command", "wrapper", "command_address", "wrapper_address", "out_value"))
    action = _address(_field(event, "action", "wrapper_action", "action_address"))
    source = _shape_dict(event.get("source"))
    return LifecycleObservation(
        line=line,
        session_id=session_id,
        kind="generic_entry",
        event=_compact_event(event),
        callback_ordinal=_callback_ordinal(event, "generic_entry"),
        wrapper_address=command,
        wrapper_action=action,
        fingerprint=_fingerprint(source or event),
        layout=_shape_key(source),
        protocol_key=_protocol_key(event),
    )


def _observation_sort_key(observation: LifecycleObservation) -> tuple[int, int, int]:
    if observation.callback_ordinal is not None:
        return 0, observation.callback_ordinal, observation.line
    return 1, observation.line, observation.line


def _observation_before(left: LifecycleObservation,
                        right: LifecycleObservation) -> bool:
    if left.callback_ordinal is not None and right.callback_ordinal is not None:
        return left.callback_ordinal < right.callback_ordinal
    return left.line < right.line


def _observation_after(left: LifecycleObservation,
                       right: LifecycleObservation) -> bool:
    return _observation_before(right, left)


def _before_generation_end(observation: LifecycleObservation,
                           generation: Generation) -> bool:
    if (observation.callback_ordinal is not None
            and generation.destructor_ordinal is not None):
        return observation.callback_ordinal < generation.destructor_ordinal
    if generation.destructor_line is not None:
        return observation.line < generation.destructor_line
    return True


def _associate_generations(state: ValidatorState) -> None:
    """Associate object generations in native callback order.

    The native hooks enqueue lifecycle and command observations separately.
    A frame flush can therefore place a later callback before an earlier one
    in the JSONL file.  Sorting by the shared callback ordinal before assigning
    generations prevents a flush artifact from crossing an address generation.
    """

    for observation in sorted(state.lifecycle, key=_observation_sort_key):
        line = observation.line
        ordinal = observation.callback_ordinal
        if observation.kind == "clone":
            if observation.source_address is None or observation.target_address is None:
                state.issue("CLONE_ADDRESS_MISSING", line)
                continue
            source_generation = state.active_generation(
                observation.source_address, line, ordinal
            )
            if source_generation is None:
                source_generation = state.establish(
                    observation.source_address, line,
                    _shape_dict(observation.event.get("source")),
                    ordinal=ordinal,
                )
            observation.source_ref = source_generation.ref
            target_generation = state.establish(
                observation.target_address, line,
                _shape_dict(observation.event.get("target")),
                ordinal=ordinal,
            )
            observation.target_ref = target_generation.ref
        elif observation.kind in {"wrapper", "serialization_begin"}:
            if observation.wrapper_action is None:
                state.issue(
                    "WRAPPER_ACTION_ADDRESS_MISSING"
                    if observation.kind == "wrapper"
                    else "SERIALIZATION_ACTION_ADDRESS_MISSING",
                    line,
                )
                continue
            target_generation = state.active_generation(
                observation.wrapper_action, line, ordinal
            )
            if target_generation is None:
                state.issue(
                    "WRAPPER_ACTION_GENERATION_UNKNOWN"
                    if observation.kind == "wrapper"
                    else "SERIALIZATION_ACTION_GENERATION_UNKNOWN",
                    line,
                    address=hex(observation.wrapper_action),
                )
            else:
                observation.target_ref = target_generation.ref
        elif observation.kind == "destructor":
            if observation.source_address is None:
                state.issue("DESTRUCTOR_ADDRESS_MISSING", line)
                continue
            source_generation = state.close_destructor(
                observation.source_address, line, ordinal
            )
            if source_generation is not None:
                observation.source_ref = source_generation.ref
        elif observation.kind == "destructor_return":
            if observation.source_address is None:
                state.issue("DESTRUCTOR_RETURN_ADDRESS_MISSING", line)
                continue
            # This event carries only the before-call snapshot and the native
            # return value.  It never closes or frees the generation.
            source_generation = state.generation_at(
                observation.source_address, line, ordinal
            )
            if source_generation is None:
                state.issue("DESTRUCTOR_RETURN_GENERATION_UNKNOWN", line,
                            address=hex(observation.source_address))
            else:
                observation.source_ref = source_generation.ref

    for line, ordinal, address in sorted(
            state.free_events,
            key=lambda item: (0, item[1], item[0]) if item[1] is not None
            else (1, item[0], item[0])):
        state.close_free(address, line, ordinal)


def _callback_order_summary(state: ValidatorState) -> dict[str, Any]:
    observations = state.callback_ordinals
    lifecycle_present = any(kind != "generic_entry" for _, _, kind in observations)
    entry_present = any(kind == "generic_entry" for _, _, kind in observations)
    if not observations:
        return {
            "status": "unknown",
            "shared_domain": False,
            "observed": 0,
            "unique": 0,
            "line_flush_disagrees": False,
            "min": None,
            "max": None,
        }
    ordinals = [ordinal for ordinal, _, _ in observations]
    unique = len(set(ordinals))
    line_flush_disagrees = any(
        current[0] < prior[0]
        for prior, current in zip(observations, observations[1:])
    )
    duplicate = unique != len(ordinals)
    if duplicate:
        state.issue("CALLBACK_ORDINAL_DUPLICATE")
    shared_domain = lifecycle_present and entry_present
    status = "verified" if shared_domain and not duplicate else "unknown"
    if shared_domain and duplicate:
        status = "incomplete"
    return {
        "status": status,
        "shared_domain": shared_domain,
        "observed": len(ordinals),
        "unique": unique,
        "line_flush_disagrees": line_flush_disagrees,
        "min": min(ordinals),
        "max": max(ordinals),
    }


def _validate_identity(installation: Any, manifest: Any, manifest_path: Path,
                       state: ValidatorState) -> dict[str, Any]:
    if not isinstance(installation, dict):
        raise InputError("installation JSON must be an object")
    if not isinstance(manifest, dict):
        raise InputError("build manifest JSON must be an object")
    session_id = installation.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise InputError("installation.session_id is required")
    manifest_session = manifest.get("session_id")
    if isinstance(manifest_session, str) and manifest_session != session_id:
        state.issue("MANIFEST_SESSION_MISMATCH", installation=session_id,
                    manifest=manifest_session)
    installation_sha = installation.get("dll_sha256")
    manifest_sha = manifest.get("dll_sha256")
    if installation_sha and manifest_sha and installation_sha != manifest_sha:
        state.issue("DLL_HASH_MISMATCH")
    version = _int(manifest.get("version"), minimum=0)
    sources = manifest.get("sources")
    source_names = [item.get("name") for item in sources
                    if isinstance(item, dict) and isinstance(item.get("name"), str)] \
        if isinstance(sources, list) else []
    lifecycle_source = any("alliance-lifecycle" in name or "lifecycle" in name
                           for name in source_names)
    if version is None or version < 10:
        state.issue("BUILD_VERSION_BELOW_NATIVE_OBSERVER", version=version)
    if manifest.get("compiled") is not True:
        state.issue("BUILD_NOT_MARKED_COMPILED", compiled=manifest.get("compiled"))
    if not lifecycle_source:
        state.issue("LIFECYCLE_SOURCE_NOT_IN_MANIFEST")

    source_hashes: list[dict[str, Any]] = []
    for item in sources if isinstance(sources, list) else []:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        expected = item.get("sha256")
        artifact = _artifact_path(manifest_path, name)
        actual, error = _stream_sha256(artifact) if artifact is not None else (None, "path_missing")
        verified = isinstance(expected, str) and actual == expected.lower()
        item_report = {
            "name": name,
            "expected": expected,
            "actual": actual,
            "verified": verified,
            "path": str(artifact) if artifact is not None else None,
        }
        if not isinstance(expected, str):
            state.issue("SOURCE_HASH_MISSING", name=name)
        elif error is not None:
            state.issue("SOURCE_HASH_UNVERIFIED", name=name, reason=error)
        elif not verified:
            state.issue("SOURCE_HASH_MISMATCH", name=name,
                        expected=expected, actual=actual)
        source_hashes.append(item_report)

    manifest_dll_path = _artifact_path(manifest_path, manifest.get("dll"))
    manifest_dll_actual, manifest_dll_error = (
        _stream_sha256(manifest_dll_path) if manifest_dll_path is not None
        else (None, "path_missing")
    )
    manifest_dll_verified = bool(
        isinstance(manifest_sha, str)
        and manifest_dll_actual == manifest_sha.lower()
    )
    if manifest_dll_error is not None:
        state.issue("DLL_HASH_UNVERIFIED", reason=manifest_dll_error)
    elif not manifest_dll_verified:
        state.issue("DLL_HASH_MISMATCH", expected=manifest_sha, actual=manifest_dll_actual)

    installation_modules = installation.get("modules_after_install")
    module_hashes: list[dict[str, Any]] = []
    for module in installation_modules if isinstance(installation_modules, list) else []:
        if not isinstance(module, dict):
            continue
        module_path = _artifact_path(manifest_path, module.get("path"))
        actual, error = _stream_sha256(module_path) if module_path is not None else (None, "path_missing")
        expected = module.get("sha256")
        verified = isinstance(expected, str) and actual == expected.lower()
        module_hashes.append({
            "name": module.get("name"),
            "expected": expected,
            "actual": actual,
            "verified": verified,
            "path": str(module_path) if module_path is not None else None,
        })
        if error is not None:
            state.issue("INSTALLATION_MODULE_HASH_UNVERIFIED",
                        name=module.get("name"), reason=error)
        elif not verified:
            state.issue("INSTALLATION_MODULE_HASH_MISMATCH",
                        name=module.get("name"), expected=expected, actual=actual)

    return {
        "session_id": session_id,
        "pid": installation.get("pid"),
        "creation_filetime": installation.get("creation_filetime"),
        "experiment_id": manifest.get("experiment_id", installation.get("experiment_id")),
        "manifest_version": version,
        "lifecycle_source_present": lifecycle_source,
        "manifest_compiled": manifest.get("compiled"),
        "installation_runtime_verified": installation.get("runtime_verified"),
        "manifest_dll_sha256": manifest_sha,
        "installation_dll_sha256": installation_sha,
        "source_hashes": source_hashes,
        "manifest_dll_hash": {
            "expected": manifest_sha,
            "actual": manifest_dll_actual,
            "verified": manifest_dll_verified,
            "path": str(manifest_dll_path) if manifest_dll_path is not None else None,
        },
        "installation_module_hashes": module_hashes,
    }


def _match_fingerprint(expected: tuple[Any, ...] | None,
                       observed: tuple[Any, ...] | None) -> bool:
    # Tag-only legacy fields are display hints, not native identity.  A
    # complete correlation therefore requires both actor and recipient to
    # retain their full integer handles (including slot/generation bits).
    return (
        expected is not None
        and observed is not None
        and _is_int(expected[0]) and _is_int(expected[1])
        and _is_int(observed[0]) and _is_int(observed[1])
        and expected == observed
    )


def _shape_is_canonical(shape: Mapping[str, Any] | None) -> bool:
    return (
        isinstance(shape, Mapping)
        and _bool(shape.get("readable")) is True
        and _bool(shape.get("matched")) is True
        and _bool(shape.get("handles_canonical")) is True
        and _shape_key(shape) is not None
    )


def _match_records(state: ValidatorState) -> list[dict[str, Any]]:
    clones = sorted((item for item in state.lifecycle if item.kind == "clone"),
                    key=_observation_sort_key)
    wrappers = sorted((item for item in state.lifecycle if item.kind == "wrapper"),
                      key=_observation_sort_key)
    serializations = sorted(
        (item for item in state.lifecycle if item.kind == "serialization_begin"),
        key=_observation_sort_key,
    )
    records: list[dict[str, Any]] = []
    for clone in clones:
        reasons: list[str] = []
        target = clone.event.get("target")
        source = clone.event.get("source")
        clone_real = (
            clone.source_ref is not None and clone.target_ref is not None
            and isinstance(source, dict) and isinstance(target, dict)
            and _bool(source.get("readable")) is True
            and _bool(target.get("readable")) is True
            and _bool(source.get("matched")) is True
            and _bool(target.get("matched")) is True
            and _bool(source.get("handles_canonical")) is True
            and _bool(target.get("handles_canonical")) is True
            and clone.layout is not None
            and _shape_key(target) == clone.layout
            and clone.source_address != clone.target_address
            and _native_forward_contract(clone.event)
            and _native_return_contract(clone.event, "clone")
            and _real_event(clone.event)
        )
        if not clone_real:
            reasons.append("clone_canonical_layout_unproven")

        wrapper_candidates = [item for item in wrappers
                              if _observation_after(item, clone)
                              and item.target_ref == clone.target_ref
                              and item.wrapper_action == clone.target_address]
        if len(wrapper_candidates) != 1:
            reasons.append("wrapper_target_action_unmatched" if not wrapper_candidates
                           else "wrapper_target_action_ambiguous")
            wrapper = wrapper_candidates[0] if len(wrapper_candidates) == 1 else None
        else:
            wrapper = wrapper_candidates[0]
            wrapper_target = wrapper.event.get("target")
            if not (wrapper.wrapper_address and wrapper.wrapper_action
                    and _bool(wrapper.event.get("wrapper_identity")) is True
                    and _bool(wrapper.event.get("wrapper_readable")) is True
                    and isinstance(wrapper_target, dict)
                    and _shape_address(wrapper_target) == wrapper.wrapper_action
                    and _shape_key(wrapper_target) == clone.layout
                    and _native_forward_contract(wrapper.event)
                    and _native_return_contract(wrapper.event, "wrapper")
                    and _real_event(wrapper.event)
                    and _match_fingerprint(clone.fingerprint, wrapper.fingerprint)):
                reasons.append("wrapper_identity_or_fingerprint_unproven")
            if wrapper.protocol_key is None:
                reasons.append("wrapper_protocol_key_incomplete")

        serialization = None
        if wrapper is not None:
            candidates = [item for item in serializations
                          if _observation_after(item, wrapper)
                          and item.wrapper_address == wrapper.wrapper_address
                          and item.wrapper_action == wrapper.wrapper_action
                          and item.target_ref == clone.target_ref]
            if len(candidates) != 1:
                reasons.append("serialization_begin_unmatched" if not candidates
                               else "serialization_begin_ambiguous")
                serialization = candidates[0] if len(candidates) == 1 else None
            else:
                serialization = candidates[0]
            if serialization is not None:
                if serialization.protocol_key is None:
                    reasons.append("serialization_protocol_key_incomplete")
                if not _match_fingerprint(clone.fingerprint, serialization.fingerprint):
                    reasons.append("serialization_fingerprint_mismatch")
                if not (_bool(serialization.event.get("wrapper_identity")) is True
                        and _bool(serialization.event.get("wrapper_readable")) is True
                        and _native_forward_contract(serialization.event)
                        and _native_return_contract(serialization.event, "serialization_begin")
                        and _real_event(serialization.event)):
                    reasons.append("serialization_wrapper_identity_unproven")

        target_generation = next((item for item in state.generations.get(clone.target_address or 0, [])
                                  if item.ref == clone.target_ref), None)
        generic = None
        if serialization is not None:
            generic_candidates = [item for item in state.generic
                                  if item.session_id == clone.session_id
                                  and wrapper is not None
                                  and _observation_after(item, wrapper)
                                  and target_generation is not None
                                  and _before_generation_end(item, target_generation)
                                  and item.wrapper_address == serialization.wrapper_address
                                  and item.wrapper_action == serialization.wrapper_action
                                  and item.protocol_key is not None
                                  and item.protocol_key == serialization.protocol_key
                                  and _real_event(item.event)
                                  and _match_fingerprint(serialization.fingerprint, item.fingerprint)]
            if len(generic_candidates) != 1:
                # Do not retry by sequence only.  A same sequence with a
                # different origin or flags is explicitly a protocol mismatch.
                same_sequence = [item for item in state.generic
                                 if item.wrapper_address == serialization.wrapper_address
                                 and item.protocol_key is not None
                                 and serialization.protocol_key is not None
                                 and item.protocol_key[1] == serialization.protocol_key[1]]
                if same_sequence:
                    reasons.append("generic_protocol_key_or_fingerprint_mismatch")
                else:
                    reasons.append("generic_command_entry_unmatched")
                generic = generic_candidates[0] if len(generic_candidates) == 1 else None
            else:
                generic = generic_candidates[0]
                readable = _bool(generic.event.get("readable"))
                if readable is False:
                    reasons.append("generic_command_entry_unreadable")
                generic_source = _shape_dict(generic.event.get("source"))
                if generic_source is not None:
                    if not _shape_is_canonical(generic_source):
                        reasons.append("generic_source_canonical_layout_unproven")
                    if (_shape_address(generic_source) != generic.wrapper_action
                            or generic.layout != clone.layout):
                        reasons.append("generic_source_layout_mismatch")
                if generic.fingerprint is None:
                    reasons.append("generic_fingerprint_incomplete")
                elif not _match_fingerprint(clone.fingerprint, generic.fingerprint):
                    reasons.append("generic_fingerprint_mismatch")
        else:
            reasons.append("generic_command_entry_unmatched")

        generation = target_generation
        if generation is None or (
                generation.destructor_line is None
                and generation.destructor_ordinal is None):
            reasons.append("destructor_missing_or_not_after_clone")
        elif generation.free_line is None and generation.free_ordinal is None:
            reasons.append("free_missing_after_destructor")
        else:
            destructor_position = (
                generation.destructor_ordinal
                if generation.destructor_ordinal is not None
                else generation.destructor_line
            )
            free_position = (
                generation.free_ordinal
                if generation.free_ordinal is not None
                else generation.free_line
            )
            if (destructor_position is not None and free_position is not None
                    and free_position <= destructor_position):
                reasons.append("destructor_before_free_unproven")
        destructor = next((item for item in state.lifecycle
                           if item.kind == "destructor"
                           and item.source_ref == clone.target_ref
                           and (
                               (generation is not None
                                and generation.destructor_ordinal is not None
                                and item.callback_ordinal == generation.destructor_ordinal)
                               or (generation is not None
                                   and generation.destructor_ordinal is None
                                   and item.line == generation.destructor_line)
                           )), None) \
            if generation and (generation.destructor_line is not None
                               or generation.destructor_ordinal is not None) else None
        if destructor is None or not (_native_forward_contract(destructor.event)
                                      and _native_return_contract(destructor.event, "destructor")
                                      and _real_event(destructor.event)):
            reasons.append("destructor_forward_contract_unproven")

        destructor_returns = [item for item in state.lifecycle
                              if item.kind == "destructor_return"
                              and item.source_ref == clone.target_ref
                              and destructor is not None
                              and _observation_after(item, destructor)]
        destructor_return = (destructor_returns[0]
                             if len(destructor_returns) == 1 else None)
        if len(destructor_returns) > 1:
            reasons.append("destructor_return_ambiguous")
        destructor_return_contract = bool(
            destructor_return is not None
            and _native_forward_contract(destructor_return.event)
            and _native_return_contract(destructor_return.event, "destructor_return")
            and _real_event(destructor_return.event)
        )
        if destructor_return is not None and not destructor_return_contract:
            reasons.append("destructor_return_contract_unproven")

        if state.dropped_events or state.unknown_events or state.session_mismatch:
            reasons.append("trace_has_drop_unknown_or_foreign_session")
        if state.truncated:
            reasons.append("trace_truncated")
        allocator_free_verified = bool(
            generation is not None
            and (generation.free_line is not None or generation.free_ordinal is not None)
        )
        callback_stages = {
            "clone": clone,
            "wrapper": wrapper,
            "serialization_begin": serialization,
            "generic_command_entry": generic,
            "destructor": destructor,
            "destructor_return": destructor_return,
        }
        callback_ordinals = {
            name: (item.callback_ordinal if item is not None else None)
            for name, item in callback_stages.items()
        }
        observed_chain = [clone, wrapper, serialization, generic]
        chain_status = (
            "verified" if all(item is not None for item in observed_chain)
            else "incomplete" if any(item is not None for item in observed_chain)
            else "unknown"
        )
        ordered_chain = [item for item in observed_chain if item is not None]
        order_status = (
            "verified"
            if len(ordered_chain) == len(observed_chain)
            and all(item.callback_ordinal is not None for item in ordered_chain)
            and all(left.callback_ordinal < right.callback_ordinal
                    for left, right in zip(ordered_chain, ordered_chain[1:]))
            else "unknown"
        )
        protocol_status = (
            "verified"
            if serialization is not None and generic is not None
            and serialization.protocol_key is not None
            and generic.protocol_key == serialization.protocol_key
            else "incomplete"
            if serialization is not None and generic is not None
            else "unknown"
        )
        clone_ownership_status = "verified" if clone_real else "incomplete"
        destructor_return_status = (
            "verified" if destructor_return_contract
            else "incomplete" if destructor_return is not None
            else "unknown"
        )
        allocator_status = "verified" if allocator_free_verified else "unknown"
        records.append({
            "record_id": f"clone-line-{clone.line}",
            "real_record": clone_real,
            "session_id": clone.session_id,
            "line_order": {
                "clone": clone.line,
                "wrapper": wrapper.line if wrapper else None,
                "serialization_begin": serialization.line if serialization else None,
                "generic_command_entry": generic.line if generic else None,
                "destructor": generation.destructor_line if generation else None,
                "free": generation.free_line if generation else None,
            },
            "callback_order": callback_ordinals,
            "addresses": {
                "source": hex(clone.source_address) if clone.source_address else None,
                "target": hex(clone.target_address) if clone.target_address else None,
                "wrapper": hex(wrapper.wrapper_address) if wrapper and wrapper.wrapper_address else None,
                "wrapper_action": hex(wrapper.wrapper_action) if wrapper and wrapper.wrapper_action else None,
                "command_entry": hex(generic.wrapper_address) if generic and generic.wrapper_address else None,
            },
            "generations": {
                "target": clone.target_ref[1] if clone.target_ref else None,
            },
            "fingerprint": list(clone.fingerprint) if clone.fingerprint else None,
            "protocol_key": list(serialization.protocol_key) if serialization and serialization.protocol_key else None,
            "protocol_assignment": {
                "wrapper_initial_key": (list(wrapper.protocol_key)
                                         if wrapper and wrapper.protocol_key else None),
                "serialization_actual_key": (list(serialization.protocol_key)
                                               if serialization and serialization.protocol_key else None),
                "wrapper_initial_phase": (
                    "construction_initial"
                    if wrapper and wrapper.protocol_key == (0xFFFF, 0, 0)
                    else "observed_or_unknown"
                ),
                "transport_assignment_not_independently_observed": bool(
                    wrapper is not None
                    and serialization is not None
                    and wrapper.protocol_key is not None
                    and serialization.protocol_key is not None
                    and wrapper.protocol_key != serialization.protocol_key
                ),
            },
            "serialization_protocol_fields": ({
                "origin48": serialization.event.get("origin48"),
                "seq4c": serialization.event.get("seq4c"),
                "rawflag4a": serialization.event.get("rawflag4a"),
            } if serialization else None),
            "generic_protocol_fields": ({
                "origin": generic.event.get("origin"),
                "protocol_sequence": generic.event.get("protocol_sequence"),
                "protocol_flags": generic.event.get("protocol_flags"),
            } if generic else None),
            "serialization_stage": "serialization_begin_observed" if serialization else None,
            "enqueue_verified": False,
            "destructor_return": {
                "status": destructor_return_status,
                "observed": destructor_return is not None,
                "callback_ordinal": (destructor_return.callback_ordinal
                                      if destructor_return else None),
                "native_result": (destructor_return.event.get("native_result")
                                   if destructor_return else None),
                "native_flags": (destructor_return.event.get("native_flags")
                                 if destructor_return else None),
                "native_return_observed": (
                    _bool(destructor_return.event.get("native_return_observed"))
                    if destructor_return else None
                ),
                "before_snapshot_only": destructor_return is not None,
                # A destructor return is not an allocator/free observation,
                # even when a separate free record exists in the trace.
                "allocator_free_verified": False,
            },
            "verification_components": {
                "callback_chain": {"status": chain_status},
                "order": {
                    "status": order_status,
                    "uses_callback_ordinal": all(
                        item is not None and item.callback_ordinal is not None
                        for item in observed_chain
                    ),
                },
                "protocol": {
                    "status": protocol_status,
                    "key": list(serialization.protocol_key)
                    if serialization and serialization.protocol_key else None,
                },
                "clone_ownership": {"status": clone_ownership_status},
                "destructor_return": {
                    "status": destructor_return_status,
                    "allocator_free_verified": False,
                },
                "allocator_free": {
                    "status": allocator_status,
                    "direct_observation": allocator_free_verified,
                },
            },
            "destructor_before_free": bool(
                generation is not None
                and (generation.destructor_line is not None
                     or generation.destructor_ordinal is not None)
                and (generation.free_line is not None
                     or generation.free_ordinal is not None)
                and (
                    (generation.free_ordinal is not None
                     and generation.destructor_ordinal is not None
                     and generation.free_ordinal > generation.destructor_ordinal)
                    or (generation.free_ordinal is None
                        and generation.destructor_ordinal is None
                        and generation.free_line > generation.destructor_line)
                )
            ),
            "complete": not reasons,
            "incomplete_reasons": sorted(set(reasons)),
        })
    return records


def validate_files(installation_path: Path | str, manifest_path: Path | str,
                   probe_path: Path | str, *, fixture_only: bool = False) -> dict[str, Any]:
    """Validate three offline files and return a JSON-serializable report."""

    installation_path = Path(installation_path)
    manifest_path = Path(manifest_path)
    probe_path = Path(probe_path)
    installation = _bounded_json(installation_path, MAX_METADATA_BYTES)
    manifest = _bounded_json(manifest_path, MAX_METADATA_BYTES)
    provisional_session = installation.get("session_id") if isinstance(installation, dict) else ""
    if not isinstance(provisional_session, str):
        provisional_session = ""
    state = ValidatorState(provisional_session)
    identity = _validate_identity(installation, manifest, manifest_path, state)
    state.installation_session = identity["session_id"]

    last_line = 0
    for line, event, parse_error in _jsonl(probe_path, MAX_PROBE_BYTES):
        last_line = line
        if state.event_count >= MAX_EVENTS:
            state.truncated = True
            state.issue("EVENT_LIMIT_REACHED", line)
            break
        if parse_error is not None or event is None:
            state.malformed_lines += 1
            state.dropped_events += 1
            state.issue("MALFORMED_PROBE_LINE", line, reason=parse_error)
            continue
        state.event_count += 1
        kind = _event_kind(event)
        if kind == "drop":
            dropped = _int(event.get("dropped"), minimum=1) or 1
            state.dropped_events += dropped
            state.issue("PROBE_DROPPED_EVENTS", line, dropped=dropped,
                        event=event.get("event"))
            continue
        event_name = event.get("event")
        if event_name == "alliance_lifecycle_observer_installed":
            state.ignored_events += 1
            state.lifecycle_install_ack = {
                "all_native_returns_preserved": event.get("all_native_returns_preserved"),
                "authority_enabled": event.get("authority_enabled"),
            }
            if event.get("all_native_returns_preserved") is not True:
                state.issue("LIFECYCLE_INSTALL_ACK_INVALID", line)
            continue
        if event_name == "alliance_serializer_observer_installed":
            state.ignored_events += 1
            state.serializer_install_ack = {
                "submit_receipt": event.get("submit_receipt"),
                "authority_enabled": event.get("authority_enabled"),
            }
            if event.get("submit_receipt") is not False:
                state.issue("SERIALIZER_INSTALL_ACK_INVALID", line)
            continue
        if event_name == "diplomacy_observer_installed":
            state.ignored_events += 1
            state.diplomacy_install_ack = {
                "session_id": event.get("session_id"),
                "version": event.get("version"),
                "all_commands_forwarded": event.get("all_commands_forwarded"),
            }
            if event.get("session_id") not in {None, state.installation_session}:
                state.issue("DIPLOMACY_INSTALL_ACK_SESSION_MISMATCH", line)
            continue
        unknown_lifecycle = (
            event_name == LIFECYCLE_EVENT
            and event.get("kind") not in LIFECYCLE_KINDS
        )
        unknown_entry = (
            isinstance(event_name, str)
            and ("alliance_command_entry" in event_name or event_name.startswith("native_alliance_lifecycle"))
            and kind is None
        )
        if kind is None or unknown_lifecycle or unknown_entry:
            # Ordinary control/health records are outside this validator's
            # scope.  Unknown lifecycle records are different: they may be a
            # dropped or unmodelled phase and therefore keep acceptance
            # incomplete without becoming a correlation key.
            if (unknown_lifecycle or unknown_entry or event.get("unknown") is True
                    or event_name is None):
                state.unknown_events += 1
                state.issue("UNKNOWN_PROBE_EVENT", line, event=event_name)
            else:
                state.ignored_events += 1
            continue
        session_id = _event_session(event)
        if session_id is None:
            state.missing_session += 1
            state.issue("EVENT_SESSION_MISSING", line, kind=kind)
            continue
        if session_id != state.installation_session:
            state.session_mismatch += 1
            state.issue("EVENT_SESSION_MISMATCH", line, kind=kind,
                        event_session=session_id, expected=state.installation_session)
            continue
        event_sequence = _event_sequence(event, kind)
        callback_ordinal = _callback_ordinal(event, kind)
        if callback_ordinal is not None:
            state.callback_ordinals.append((callback_ordinal, line, kind))
        elif event_sequence is None and kind in {
                "clone", "wrapper", "destructor", "destructor_return",
                "serialization_begin", "generic_entry"}:
            state.issue("EVENT_SEQUENCE_MISSING", line, kind=kind)
        elif event_sequence is not None:
            prior = state.last_event_sequence.get(kind)
            if prior is not None and event_sequence <= prior:
                state.issue("EVENT_SEQUENCE_NOT_MONOTONIC", line, kind=kind,
                            previous=prior, current=event_sequence)
            state.last_event_sequence[kind] = event_sequence
            if kind in {"clone", "wrapper", "destructor", "destructor_return",
                        "serialization_begin"}:
                lifecycle_prior = state.last_event_sequence.get("__lifecycle__")
                if lifecycle_prior is not None and event_sequence <= lifecycle_prior:
                    state.issue("LIFECYCLE_SEQUENCE_NOT_MONOTONIC", line,
                                previous=lifecycle_prior, current=event_sequence)
                state.last_event_sequence["__lifecycle__"] = event_sequence

        if kind in {"clone", "wrapper", "serialization_begin", "destructor",
                    "destructor_return"}:
            if len(state.lifecycle) >= MAX_PENDING:
                state.truncated = True
                state.issue("LIFECYCLE_RECORD_LIMIT_REACHED", line)
                continue
            observation = _lifecycle_observation(event, line, session_id, kind, state)
            state.lifecycle.append(observation)
        elif kind == "generic_entry":
            if len(state.generic) >= MAX_PENDING:
                state.truncated = True
                state.issue("GENERIC_RECORD_LIMIT_REACHED", line)
                continue
            observation = _generic_observation(event, line, session_id)
            state.generic.append(observation)
            if observation.protocol_key is None:
                state.issue("GENERIC_PROTOCOL_KEY_INCOMPLETE", line)
            if observation.wrapper_address is None or observation.wrapper_action is None:
                state.issue("GENERIC_ADDRESS_INCOMPLETE", line)
        elif kind in FREE_KINDS or kind == "free":
            address = _addresses_for_free(event)
            if address is None:
                state.issue("FREE_ADDRESS_MISSING", line)
            else:
                state.free_events.append((line, callback_ordinal, address))

    _associate_generations(state)
    callback_order = _callback_order_summary(state)
    records = _match_records(state)
    real_records = [record for record in records if record["real_record"]]
    complete_records = [record for record in real_records if record["complete"]]
    global_reasons: list[str] = []
    if not records:
        global_reasons.append("NO_REAL_LIFECYCLE_RECORDS")
    if not real_records:
        global_reasons.append("NO_REAL_RECORDS")
    if state.dropped_events:
        global_reasons.append("PROBE_DROPPED_EVENTS")
    if state.unknown_events:
        global_reasons.append("UNKNOWN_EVENTS")
    if state.missing_session or state.session_mismatch:
        global_reasons.append("SESSION_ASSOCIATION_INCOMPLETE")
    if state.truncated:
        global_reasons.append("TRACE_TRUNCATED")
    if any(issue.get("code") in {
        "EVENT_SEQUENCE_MISSING", "EVENT_SEQUENCE_NOT_MONOTONIC",
        "LIFECYCLE_SEQUENCE_NOT_MONOTONIC", "CALLBACK_ORDINAL_DUPLICATE",
    } for issue in state.issues):
        global_reasons.append("EVENT_ORDER_OR_SEQUENCE_UNCERTAIN")
    if not identity["lifecycle_source_present"]:
        global_reasons.append("LIFECYCLE_PROVENANCE_UNPROVEN")
    if identity["manifest_version"] is None or identity["manifest_version"] < 10:
        global_reasons.append("BUILD_VERSION_BELOW_NATIVE_OBSERVER")
    if identity["manifest_compiled"] is not True:
        global_reasons.append("BUILD_NOT_COMPILED")
    identity_issue_codes = {issue.get("code") for issue in state.issues}
    if "MANIFEST_SESSION_MISMATCH" in identity_issue_codes:
        global_reasons.append("MANIFEST_SESSION_MISMATCH")
    if "DLL_HASH_MISMATCH" in identity_issue_codes:
        global_reasons.append("DLL_HASH_MISMATCH")
    if identity_issue_codes.intersection({
        "SOURCE_HASH_MISSING", "SOURCE_HASH_UNVERIFIED", "SOURCE_HASH_MISMATCH",
        "DLL_HASH_UNVERIFIED", "INSTALLATION_MODULE_HASH_UNVERIFIED",
        "INSTALLATION_MODULE_HASH_MISMATCH",
    }):
        global_reasons.append("ARTIFACT_HASH_UNVERIFIED")
    if state.lifecycle_install_ack is None:
        global_reasons.append("LIFECYCLE_INSTALL_ACK_MISSING")
    if state.serializer_install_ack is None:
        global_reasons.append("SERIALIZER_INSTALL_ACK_MISSING")
    if state.diplomacy_install_ack is None:
        global_reasons.append("DIPLOMACY_INSTALL_ACK_MISSING")
    if identity_issue_codes.intersection({
        "LIFECYCLE_INSTALL_ACK_INVALID",
        "SERIALIZER_INSTALL_ACK_INVALID",
        "DIPLOMACY_INSTALL_ACK_SESSION_MISMATCH",
    }):
        global_reasons.append("RUNTIME_INSTALL_ACK_INVALID")
    accepted = bool(real_records and complete_records and not global_reasons)
    return {
        "report_version": 1,
        "validator": "validate_alliance_lifecycle",
        "offline_only": True,
        "runtime_this_turn": False,
        "fixture_only": fixture_only,
        "native_methods_invoked": False,
        "game_started": False,
        "inputs": {
            "installation": str(installation_path),
            "build_manifest": str(manifest_path),
            "control_probe": str(probe_path),
            "probe_last_line": last_line,
        },
        "identity": identity,
        "runtime_installation_ack": {
            "lifecycle": state.lifecycle_install_ack,
            "serializer": state.serializer_install_ack,
            "diplomacy": state.diplomacy_install_ack,
        },
        "event_counts": {
            "parsed": state.event_count,
            "lifecycle": len(state.lifecycle),
            "generic_command_entries": len(state.generic),
            "real_generic_command_entries": sum(_real_event(item.event) for item in state.generic),
            "destructor_returns": sum(item.kind == "destructor_return"
                                       for item in state.lifecycle),
            "allocator_free_observed": sum(
                generation.free_line is not None
                for generations in state.generations.values()
                for generation in generations
            ),
            "callback_ordinals": callback_order["observed"],
            "real_records": len(real_records),
            "complete_records": len(complete_records),
            "dropped": state.dropped_events,
            "unknown": state.unknown_events,
            "ignored": state.ignored_events,
            "malformed_lines": state.malformed_lines,
        },
        "protocol_policy": {
            "key_fields": ["origin", "sequence", "flags"],
            "sequence_only_matching": False,
            "serialization_begin_is_submission": False,
        },
        "callback_order": callback_order,
        "acceptance_gate": accepted,
        "status": "accepted" if accepted else "incomplete",
        "evidence_scope": "fixture_only" if fixture_only else "offline_runtime_artifacts",
        "global_incomplete_reasons": sorted(set(global_reasons)),
        "records": records,
        "issues": state.issues,
    }


def write_new_json(path: Path | str, report: Mapping[str, Any]) -> None:
    """Write an evidence report with exclusive-create semantics."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True,
                  allow_nan=False)
        stream.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", required=True, type=Path,
                        help="offline installation.json")
    parser.add_argument("--build-manifest", required=True, type=Path,
                        help="offline build-manifest.json")
    parser.add_argument("--control-probe", required=True, type=Path,
                        help="offline control-probe.jsonl")
    parser.add_argument("--output", type=Path,
                        help="new JSON report; existing paths are rejected")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        report = validate_files(args.installation, args.build_manifest, args.control_probe)
        if args.output is None:
            json.dump(report, sys.stdout, ensure_ascii=False, indent=2,
                      sort_keys=True, allow_nan=False)
            sys.stdout.write("\n")
        else:
            write_new_json(args.output, report)
    except (InputError, OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
