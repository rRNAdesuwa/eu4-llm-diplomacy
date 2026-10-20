#!/usr/bin/env python3
"""Prepare an R71 inbound-favor initial scene without changing other save bytes.

The source is expected to be a text EU4 save.  The stream copier changes only
the explicitly recorded initial-scene fields: ``FRA.active_relations.SAV``
favors to ``20.000``, FRA/PAP direct treasury to ``1000.000``/``100.000``, and
the existing direct ``trade_favors_for_gold`` cooldown date in FRA, PAP, or SAV
to the day before the save date.  Missing PAP/SAV cooldown fields are reported
as absent and are never added.  The untouched ``FRA/active_relations/PAP``
guard (``14.655`` by default) is validated.  The source and output SHA-256
digests are computed while making one streaming copy pass.

This prepares initial resources and cooldown state for later native requests;
it does not fabricate a settlement effect, edit war state, or launch the game.
Later native settlement and save proof remain required.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, BinaryIO


EXPECTED_OUTPUT_NAME = "llm_diplomacy_r71_favors_inbound_20261020.eu4"
EXPECTED_PAP_FAVORS = Decimal("14.655")
REPORT_NAME = "report.json"
TARGET_COUNTRIES = frozenset(("FRA", "PAP", "SAV"))
TARGET_RELATION = "SAV"
PAP_GUARD_RELATION = "PAP"
TARGET_NEW_FAVORS = b"20.000"
FRA_NEW_TREASURY = b"1000.000"
PAP_NEW_TREASURY = b"100.000"
COOLDOWN_ACTION = "trade_favors_for_gold"

# The current R70 source date is discovered from the save itself.  The
# previous calendar day is used so the native cooldown is unambiguously past
# at the source date; no hard-coded date is used for the scene.
DATE_RE = re.compile(
    rb"^[ \t]*date[ \t]*=[ \t]*(?P<value>\d+\.\d+\.\d+)[ \t]*(?:#.*)?$"
)
COOLDOWN_RE = re.compile(
    rb"^(?P<prefix>[ \t]*trade_favors_for_gold[ \t]*=[ \t]*)"
    rb"(?P<value>\d+\.\d+\.\d+)"
    rb"(?P<suffix>[ \t]*(?:#.*)?)[ \t]*$"
)
TREASURY_RE = re.compile(
    rb"^(?P<prefix>[ \t]*treasury[ \t]*=[ \t]*)"
    rb"(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+))"
    rb"(?P<suffix>[ \t]*(?:#.*)?)[ \t]*$"
)

FAVORS_RE = re.compile(
    rb"^(?P<prefix>[ \t]*favors[ \t]*=[ \t]*)"
    rb"(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+))"
    rb"(?P<suffix>[ \t]*(?:#.*)?)[ \t]*$"
)


def stripped(line: bytes) -> bytes:
    return line.strip()


def is_open(line: bytes, key: str) -> bool:
    return stripped(line) == key.encode("ascii") + b"={"


def brace_delta(line: bytes) -> int:
    """Count structural braces while ignoring braces inside quoted strings."""

    quoted = False
    escaped = False
    delta = 0
    for byte in line:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 0x5C:  # backslash
                escaped = True
            elif byte == 0x22:  # double quote
                quoted = False
        elif byte == 0x22:
            quoted = True
        elif byte == 0x7B:  # {
            delta += 1
        elif byte == 0x7D:  # }
            delta -= 1
    return delta


def split_line_ending(line: bytes) -> tuple[bytes, bytes]:
    if line.endswith(b"\r\n"):
        return line[:-2], b"\r\n"
    if line.endswith(b"\n") or line.endswith(b"\r"):
        return line[:-1], line[-1:]
    return line, b""


def parse_favors(line: bytes) -> tuple[Decimal, bytes] | None:
    body, _ending = split_line_ending(line)
    match = FAVORS_RE.match(body)
    if match is None:
        return None
    try:
        value = Decimal(match.group("value").decode("ascii"))
    except (UnicodeDecodeError, InvalidOperation) as exc:
        raise ValueError(f"invalid favors value in line: {line!r}") from exc
    if not value.is_finite():
        raise ValueError(f"non-finite favors value in line: {line!r}")
    return value, match.group("value")


def replace_favors(line: bytes, new_value: bytes) -> bytes:
    body, ending = split_line_ending(line)
    match = FAVORS_RE.match(body)
    if match is None:
        raise ValueError(f"cannot replace favors assignment in {line!r}")
    return body[: match.start("value")] + new_value + body[match.end("value") :] + ending


def parse_game_date(value: bytes, context: str) -> date:
    try:
        year, month, day = (int(part) for part in value.decode("ascii").split("."))
        return date(year, month, day)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"invalid {context} date: {value!r}") from exc


def parse_save_date(line: bytes) -> tuple[date, bytes] | None:
    body, _ending = split_line_ending(line)
    match = DATE_RE.match(body)
    if match is None:
        return None
    raw_value = match.group("value")
    return parse_game_date(raw_value, "save"), raw_value


def parse_cooldown(line: bytes) -> tuple[date, bytes] | None:
    body, _ending = split_line_ending(line)
    match = COOLDOWN_RE.match(body)
    if match is None:
        return None
    raw_value = match.group("value")
    return parse_game_date(raw_value, COOLDOWN_ACTION), raw_value


def replace_cooldown(line: bytes, new_value: bytes) -> bytes:
    body, ending = split_line_ending(line)
    match = COOLDOWN_RE.match(body)
    if match is None:
        raise ValueError(f"cannot replace {COOLDOWN_ACTION} assignment in {line!r}")
    return body[: match.start("value")] + new_value + body[match.end("value") :] + ending


def parse_treasury(line: bytes) -> tuple[Decimal, bytes] | None:
    body, _ending = split_line_ending(line)
    match = TREASURY_RE.match(body)
    if match is None:
        return None
    try:
        value = Decimal(match.group("value").decode("ascii"))
    except (UnicodeDecodeError, InvalidOperation) as exc:
        raise ValueError(f"invalid treasury value in line: {line!r}") from exc
    if not value.is_finite():
        raise ValueError(f"non-finite treasury value in line: {line!r}")
    return value, match.group("value")


def replace_treasury(line: bytes, new_value: bytes) -> bytes:
    body, ending = split_line_ending(line)
    match = TREASURY_RE.match(body)
    if match is None:
        raise ValueError(f"cannot replace treasury assignment in {line!r}")
    return body[: match.start("value")] + new_value + body[match.end("value") :] + ending


def display_line(line: bytes) -> str:
    body, _ending = split_line_ending(line)
    return body.decode("utf-8", errors="replace")


@dataclass
class RelationState:
    tag: str
    start_line: int
    depth: int
    favors_lines: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CountryState:
    tag: str
    start_line: int
    depth: int
    active_relations_count: int = 0
    active_relations_depth: int | None = None
    relation: RelationState | None = None
    relation_counts: dict[str, int] = field(
        default_factory=lambda: {TARGET_RELATION: 0, PAP_GUARD_RELATION: 0}
    )
    cooldowns_count: int = 0
    cooldowns_depth: int | None = None
    cooldown_lines: list[dict[str, Any]] = field(default_factory=list)
    treasury_lines: list[dict[str, Any]] = field(default_factory=list)
    end_line: int | None = None


@dataclass
class ScanState:
    line_count: int = 0
    depth: int = 0
    countries_found: bool = False
    countries_complete: bool = False
    countries_depth: int | None = None
    countries_start_line: int | None = None
    countries_end_line: int | None = None
    source_date: date | None = None
    source_date_raw: bytes | None = None
    expired_date: date | None = None
    expired_date_raw: bytes | None = None
    countries: dict[str, CountryState] = field(default_factory=dict)
    current_country: CountryState | None = None
    target_replacements: int = 0
    favors_source: Decimal | None = None
    target_old_line: str | None = None
    target_new_line: str | None = None
    target_line_number: int | None = None
    pap_favors: Decimal | None = None
    pap_line: str | None = None
    pap_line_number: int | None = None
    treasury_replacements: int = 0
    fra_treasury: Decimal | None = None
    fra_treasury_old_line: str | None = None
    fra_treasury_new_line: str | None = None
    fra_treasury_line_number: int | None = None
    pap_treasury: Decimal | None = None
    pap_treasury_old_line: str | None = None
    pap_treasury_new_line: str | None = None
    pap_treasury_line_number: int | None = None
    cooldown_replacements: int = 0


def _finish_relation(state: ScanState, country: CountryState) -> None:
    relation = country.relation
    if relation is None:
        return
    country.relation_counts[relation.tag] += 1
    if len(relation.favors_lines) > 1:
        raise ValueError(
            f"{country.tag}.active_relations.{relation.tag} relation has "
            f"{len(relation.favors_lines)} direct favors lines"
        )
    if not relation.favors_lines:
        country.relation = None
        return
    entry = relation.favors_lines[0]
    if country.tag == "FRA" and relation.tag == TARGET_RELATION:
        if state.favors_source is not None:
            raise ValueError("duplicate FRA.active_relations.SAV.favors assignment")
        state.favors_source = entry["value"]
        state.target_old_line = entry["original_line"]
        state.target_line_number = entry["line_number"]
    elif country.tag == "FRA" and relation.tag == PAP_GUARD_RELATION:
        if state.pap_favors is not None:
            raise ValueError("duplicate FRA.active_relations.PAP.favors assignment")
        state.pap_favors = entry["value"]
        state.pap_line = entry["original_line"]
        state.pap_line_number = entry["line_number"]
    country.relation = None


def _finish_country(state: ScanState, country: CountryState, line_number: int) -> None:
    if country.relation is not None:
        _finish_relation(state, country)
    country.end_line = line_number
    if country.tag in state.countries:
        raise ValueError(f"duplicate top-level {country.tag} block")
    state.countries[country.tag] = country


def _cooldown_report(country: CountryState, state: ScanState) -> dict[str, Any]:
    entries = country.cooldown_lines
    path = f"countries/{country.tag}/cooldowns/{COOLDOWN_ACTION}"
    if not entries:
        return {
            "country": country.tag,
            "action": COOLDOWN_ACTION,
            "save_path": path,
            "present": False,
            "count": 0,
            "line_number": None,
            "original_date": None,
            "new_date": None,
            "original_line": None,
            "new_line": None,
            "changed_line_count": 0,
            "unchanged": True,
            "reason": "action cooldown field absent from the source country block",
        }
    entry = entries[0]
    return {
        "country": country.tag,
        "action": COOLDOWN_ACTION,
        "save_path": path,
        "present": True,
        "count": len(entries),
        "line_number": entry["line_number"],
        "original_date": entry["date"],
        "new_date": entry["new_date"],
        "original_line": entry["original_line"],
        "new_line": entry["new_line"],
        "changed_line_count": 1,
        "unchanged": False,
        "source_date": state.source_date_raw.decode("ascii") if state.source_date_raw else None,
    }


def _validate_scan(state: ScanState) -> None:
    errors: list[str] = []
    if not state.countries_found:
        errors.append("countries block not found at top level")
    if not state.countries_complete:
        errors.append("countries block did not close")
    if state.depth != 0:
        errors.append(f"final brace depth is {state.depth}, expected 0")
    for tag in sorted(TARGET_COUNTRIES):
        if tag not in state.countries:
            errors.append(f"expected exactly one top-level {tag} block, found 0")
    fra = state.countries.get("FRA")
    if fra is None:
        errors.append("FRA country block is unavailable for relation validation")
    if fra is not None and fra.active_relations_count != 1:
        errors.append(
            "expected exactly one direct FRA.active_relations block, "
            f"found {fra.active_relations_count}"
        )
    if fra is not None:
        for tag in (TARGET_RELATION, PAP_GUARD_RELATION):
            if fra.relation_counts[tag] != 1:
                errors.append(
                    f"expected exactly one FRA.active_relations.{tag} block, "
                    f"found {fra.relation_counts[tag]}"
                )
    if state.source_date is None:
        errors.append("top-level save date is missing")
    if state.expired_date is None:
        errors.append("expired cooldown date was not derived")
    if state.favors_source is None:
        errors.append("FRA.active_relations.SAV.favors is missing")
    if state.pap_favors is None:
        errors.append("FRA.active_relations.PAP.favors is missing")
    elif state.pap_favors != EXPECTED_PAP_FAVORS:
        errors.append(
            "PAP guard changed from the expected baseline: "
            f"found {state.pap_favors}, expected {EXPECTED_PAP_FAVORS}"
        )
    if state.target_replacements != 1:
        errors.append(
            "expected exactly one SAV favors replacement, "
            f"performed {state.target_replacements}"
        )
    if state.treasury_replacements != 2:
        errors.append(
            "expected exactly two initial treasury replacements (FRA and PAP), "
            f"performed {state.treasury_replacements}"
        )
    for tag in ("FRA", "PAP"):
        country = state.countries.get(tag)
        if country is None or len(country.treasury_lines) != 1:
            errors.append(
                f"expected exactly one direct countries/{tag}/treasury field, "
                f"found {len(country.treasury_lines) if country is not None else 0}"
            )
    for tag in TARGET_COUNTRIES:
        country = state.countries.get(tag)
        if country is not None and country.cooldown_lines and len(country.cooldown_lines) != 1:
            errors.append(
                f"expected at most one {tag}.cooldowns.{COOLDOWN_ACTION} field, "
                f"found {len(country.cooldown_lines)}"
            )
    if fra is not None and len(fra.cooldown_lines) != 1:
        errors.append(
            f"expected exactly one FRA.cooldowns.{COOLDOWN_ACTION} field, "
            f"found {len(fra.cooldown_lines)}"
        )
    if errors:
        raise ValueError("; ".join(errors))


def _resolve_existing(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"{label} is not a regular file: {resolved}")
    return resolved


def prepare(source: Path, output: Path, report_dir: Path) -> dict[str, Any]:
    source = _resolve_existing(source, "source save")
    output = output.expanduser().resolve(strict=False)
    report_dir = report_dir.expanduser().resolve(strict=False)

    if output.name != EXPECTED_OUTPUT_NAME:
        raise ValueError(
            f"output basename must be {EXPECTED_OUTPUT_NAME!r}, got {output.name!r}"
        )
    if output == source:
        raise ValueError("source and output must be different files")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    if not output.parent.is_dir():
        raise FileNotFoundError(f"output parent does not exist: {output.parent}")

    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / REPORT_NAME
    if report_path.exists():
        raise FileExistsError(f"refusing to overwrite existing report: {report_path}")

    state = ScanState()
    source_hash = hashlib.sha256()
    output_hash = hashlib.sha256()
    source_size = 0
    output_size = 0
    created_output = False

    try:
        # ``xb`` is an exclusive create: even a race that creates the target
        # after the preflight check cannot be overwritten.
        with source.open("rb", buffering=1024 * 1024) as src, output.open(
            "xb", buffering=1024 * 1024
        ) as dst:
            created_output = True
            for line_number, raw_line in enumerate(src, 1):
                state.line_count = line_number
                before = state.depth
                output_line = raw_line

                if before == 0:
                    parsed_date = parse_save_date(raw_line)
                    if parsed_date is not None:
                        if state.source_date is not None:
                            raise ValueError("duplicate top-level save date")
                        state.source_date, state.source_date_raw = parsed_date
                        state.expired_date = state.source_date - timedelta(days=1)
                        state.expired_date_raw = (
                            f"{state.expired_date.year}.{state.expired_date.month}."
                            f"{state.expired_date.day}"
                        ).encode("ascii")

                if (
                    not state.countries_found
                    and before == 0
                    and stripped(raw_line) == b"countries={"
                ):
                    state.countries_found = True
                    state.countries_start_line = line_number
                    state.countries_depth = before + brace_delta(raw_line)

                if (
                    state.current_country is None
                    and state.countries_found
                    and not state.countries_complete
                    and state.countries_depth is not None
                    and before == state.countries_depth
                ):
                    for tag in TARGET_COUNTRIES:
                        if is_open(raw_line, tag):
                            state.current_country = CountryState(
                                tag, line_number, before + brace_delta(raw_line)
                            )
                            break

                country = state.current_country
                if country is not None:
                    if before == country.depth:
                        parsed_treasury = parse_treasury(raw_line)
                        if parsed_treasury is not None:
                            value, _raw_value = parsed_treasury
                            if len(country.treasury_lines) >= 1:
                                raise ValueError(
                                    f"duplicate direct {country.tag}.treasury assignment"
                                )
                            treasury_entry = {
                                "line_number": line_number,
                                "value": value,
                                "original_line": display_line(raw_line),
                            }
                            country.treasury_lines.append(treasury_entry)
                            if country.tag in {"FRA", "PAP"}:
                                new_treasury = (
                                    FRA_NEW_TREASURY
                                    if country.tag == "FRA"
                                    else PAP_NEW_TREASURY
                                )
                                output_line = replace_treasury(raw_line, new_treasury)
                                state.treasury_replacements += 1
                                new_line = display_line(output_line)
                                if country.tag == "FRA":
                                    state.fra_treasury = value
                                    state.fra_treasury_old_line = treasury_entry["original_line"]
                                    state.fra_treasury_new_line = new_line
                                    state.fra_treasury_line_number = line_number
                                else:
                                    state.pap_treasury = value
                                    state.pap_treasury_old_line = treasury_entry["original_line"]
                                    state.pap_treasury_new_line = new_line
                                    state.pap_treasury_line_number = line_number
                        if is_open(raw_line, "active_relations"):
                            country.active_relations_count += 1
                            if country.active_relations_count > 1:
                                raise ValueError(
                                    f"duplicate direct {country.tag}.active_relations block"
                                )
                            country.active_relations_depth = before + brace_delta(raw_line)
                        if is_open(raw_line, "cooldowns"):
                            country.cooldowns_count += 1
                            if country.cooldowns_count > 1:
                                raise ValueError(
                                    f"duplicate direct {country.tag}.cooldowns block"
                                )
                            country.cooldowns_depth = before + brace_delta(raw_line)

                    if country.cooldowns_depth is not None and before == country.cooldowns_depth:
                        parsed_cooldown = parse_cooldown(raw_line)
                        if parsed_cooldown is not None:
                            if state.expired_date_raw is None:
                                raise ValueError(
                                    "cannot rewrite cooldown before top-level save date"
                                )
                            cooldown_date, _raw_value = parsed_cooldown
                            if len(country.cooldown_lines) >= 1:
                                raise ValueError(
                                    f"duplicate {country.tag}.cooldowns.{COOLDOWN_ACTION} assignment"
                                )
                            original_line = display_line(raw_line)
                            output_line = replace_cooldown(raw_line, state.expired_date_raw)
                            country.cooldown_lines.append(
                                {
                                    "line_number": line_number,
                                    "date": f"{cooldown_date.year}.{cooldown_date.month}.{cooldown_date.day}",
                                    "original_line": original_line,
                                    "new_date": state.expired_date_raw.decode("ascii"),
                                    "new_line": display_line(output_line),
                                }
                            )
                            state.cooldown_replacements += 1

                    if country.active_relations_depth is not None:
                        if country.relation is None and before == country.active_relations_depth:
                            for relation_tag in (TARGET_RELATION, PAP_GUARD_RELATION):
                                if is_open(raw_line, relation_tag):
                                    country.relation = RelationState(
                                        relation_tag,
                                        line_number,
                                        before + brace_delta(raw_line),
                                    )
                                    break
                        elif country.relation is not None and before == country.relation.depth:
                            parsed = parse_favors(raw_line)
                            if parsed is not None:
                                value, _raw_value = parsed
                                original_line = display_line(raw_line)
                                entry = {
                                    "line_number": line_number,
                                    "value": value,
                                    "original_line": original_line,
                                }
                                country.relation.favors_lines.append(entry)
                                if (
                                    country.tag == "FRA"
                                    and country.relation.tag == TARGET_RELATION
                                ):
                                    if state.target_replacements != 0:
                                        raise ValueError("duplicate SAV favors replacement")
                                    output_line = replace_favors(raw_line, TARGET_NEW_FAVORS)
                                    state.target_replacements += 1
                                    state.target_new_line = display_line(output_line)

                source_hash.update(raw_line)
                output_hash.update(output_line)
                source_size += len(raw_line)
                output_size += len(output_line)
                dst.write(output_line)

                state.depth += brace_delta(raw_line)

                if country is not None and country.relation is not None and state.depth < country.relation.depth:
                    _finish_relation(state, country)
                if country is not None and country.active_relations_depth is not None and state.depth < country.active_relations_depth:
                    country.active_relations_depth = None
                if country is not None and country.cooldowns_depth is not None and state.depth < country.cooldowns_depth:
                    country.cooldowns_depth = None
                if country is not None and state.depth < country.depth:
                    _finish_country(state, country, line_number)
                    state.current_country = None
                if (
                    state.countries_found
                    and state.countries_depth is not None
                    and state.depth < state.countries_depth
                ):
                    state.countries_complete = True
                    state.countries_end_line = line_number

        # If the input ends inside one of the selected blocks, do not publish
        # a partial scenario.  A well-formed save reaches all close delimiters.
        if state.current_country is not None:
            _finish_country(state, state.current_country, state.line_count)
            state.current_country = None
        _validate_scan(state)
    except Exception:
        if created_output and output.exists():
            output.unlink()
        raise

    fra = state.countries["FRA"]
    pap = state.countries["PAP"]
    sav = state.countries["SAV"]
    cooldown_reports = [
        _cooldown_report(country, state) for country in (fra, pap, sav)
    ]
    report: dict[str, Any] = {
        "schema": "r71_favor_scene_prepare_v2",
        "status": "passed",
        "initial_experiment_scene": {
            "purpose": "initial resources and expired native favor-gold cooldowns for inbound experiments",
            "source_date": state.source_date_raw.decode("ascii"),
            "expired_cooldown_date": state.expired_date_raw.decode("ascii"),
            "native_settlement_effect": "not fabricated by this preparation; later native settle and save proof are required",
            "changed_paths": [
                "countries/FRA/active_relations/SAV/favors",
                "countries/FRA/treasury",
                "countries/PAP/treasury",
                *[row["save_path"] for row in cooldown_reports if row["present"]],
            ],
        },
        "source": {
            "path": str(source),
            "size": source_size,
            "sha256": source_hash.hexdigest(),
        },
        "output": {
            "path": str(output),
            "size": output_size,
            "sha256": output_hash.hexdigest(),
            "parent_exists_before_write": True,
            "created_exclusively": True,
        },
        "report_path": str(report_path),
        "replacement": {
            "country_owner": "FRA",
            "relation_key": TARGET_RELATION,
            "save_path": "countries/FRA/active_relations/SAV",
            "native_inbound_interpretation": "recipient=FRA, actor=SAV",
            "line_number": state.target_line_number,
            "original_favors": str(state.favors_source),
            "new_favors": TARGET_NEW_FAVORS.decode("ascii"),
            "original_line": state.target_old_line,
            "new_line": state.target_new_line,
            "changed_line_count": state.target_replacements,
        },
        "treasury_changes": [
            {
                "country": "FRA",
                "save_path": "countries/FRA/treasury",
                "line_number": state.fra_treasury_line_number,
                "original_value": str(state.fra_treasury),
                "new_value": FRA_NEW_TREASURY.decode("ascii"),
                "original_line": state.fra_treasury_old_line,
                "new_line": state.fra_treasury_new_line,
                "changed_line_count": 1,
            },
            {
                "country": "PAP",
                "save_path": "countries/PAP/treasury",
                "line_number": state.pap_treasury_line_number,
                "original_value": str(state.pap_treasury),
                "new_value": PAP_NEW_TREASURY.decode("ascii"),
                "original_line": state.pap_treasury_old_line,
                "new_line": state.pap_treasury_new_line,
                "changed_line_count": 1,
            },
        ],
        "cooldown_changes": cooldown_reports,
        "pap_guard": {
            "country_owner": "FRA",
            "relation_key": PAP_GUARD_RELATION,
            "save_path": "countries/FRA/active_relations/PAP",
            "line_number": state.pap_line_number,
            "favors": str(state.pap_favors),
            "expected_favors": str(EXPECTED_PAP_FAVORS),
            "unchanged": True,
            "line": state.pap_line,
        },
        "scan": {
            "line_count": state.line_count,
            "countries_start_line": state.countries_start_line,
            "countries_end_line": state.countries_end_line,
            "countries_complete": state.countries_complete,
            "target_country_blocks": {
                tag: {
                    "start_line": country.start_line,
                    "end_line": country.end_line,
                    "treasury_count": len(country.treasury_lines),
                    "active_relations_count": country.active_relations_count,
                    "cooldowns_count": country.cooldowns_count,
                }
                for tag, country in sorted(state.countries.items())
            },
            "fra_active_relations_block_count": fra.active_relations_count,
            "target_relation_block_count": fra.relation_counts[TARGET_RELATION],
            "pap_relation_block_count": fra.relation_counts[PAP_GUARD_RELATION],
            "changed_line_count": state.target_replacements
            + state.treasury_replacements
            + state.cooldown_replacements,
            "streaming_single_pass_hashes": True,
            "other_save_bytes_copied_verbatim": True,
            "treasury_or_balance_fields_touched": True,
            "treasury_changes_are_initial_scene_only": True,
            "war_fields_touched": False,
        },
    }
    report_bytes = (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    created_report = False
    try:
        # Use exclusive creation here too, so a concurrent file cannot be
        # overwritten after the preflight existence check.
        with report_path.open("xb") as report_stream:
            created_report = True
            report_stream.write(report_bytes)
    except Exception:
        if created_report and report_path.exists():
            report_path.unlink()
        if output.exists():
            output.unlink()
        raise
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = prepare(args.source, args.output, args.report_dir)
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": report["output"]["path"],
                "report": report["report_path"],
                "replacement": report["replacement"],
                "treasury_changes": report["treasury_changes"],
                "cooldown_changes": report["cooldown_changes"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
