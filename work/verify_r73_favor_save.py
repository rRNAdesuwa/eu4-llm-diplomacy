"""Compare Trust/Men native settlements with one independent streaming save scan."""
from __future__ import annotations
import argparse
from collections import OrderedDict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy import ObserverSession
from bridge.favor_resources import validate_query, validate_result
from work.verify_r71_favor_save import _iter_json_file, brace_delta

ACTION_KIND = {"trade_favors_for_trust": "trust", "trade_favors_for_men": "men"}
EVENTS = {"native_diplomacy_favor_trade_execution_result",
          "native_diplomacy_favor_trade_response_result"}
TAG_OPEN = re.compile(rb"^([A-Z0-9]{3})\s*=\s*\{$")
FIELD = re.compile(rb"^(manpower|favors|trust_value)\s*=\s*([-+]?\d+(?:\.\d*)?)$")
TRUST_SAVE_CONTRACT = ROOT / "work/runtime/r74-gift-influence-contract-20261020-001/trust-save-contract.md"


def collect(paths: list[Path]) -> tuple[OrderedDict, list, list]:
    expected = OrderedDict()
    selected = []
    errors = []
    for path in paths:
        for ordinal, event in _iter_json_file(path):
            if not isinstance(event, dict) or event.get("event") not in EVENTS:
                continue
            action = event.get("action_id")
            if action not in ACTION_KIND:
                continue
            proof = event.get("favor_trade")
            kind = ACTION_KIND[action]
            if (isinstance(proof, dict) and proof.get("kind") == kind
                    and (proof.get("complete") is not True or proof.get("verified") is not True
                         or event.get("execution_verified") is not True
                         or event.get("request_binding_verified") is not True)):
                continue
            if (event.get("family") != "favor_trade" or not isinstance(proof, dict)
                    or proof.get("kind") != kind or event.get("execution_verified") is not True
                    or event.get("request_binding_verified") is not True
                    or proof.get("complete") is not True or proof.get("verified") is not True
                    or not validate_result(proof, event.get("native_state"))):
                errors.append(f"Unverified {action} settlement: {path}:{ordinal}")
                continue
            actor, recipient = event.get("actor"), event.get("recipient")
            if any(not isinstance(tag, str) or not re.fullmatch(r"[A-Z0-9]{3}", tag)
                   for tag in (actor, recipient)) or actor == recipient:
                errors.append(f"Invalid endpoints: {path}:{ordinal}")
                continue
            provenance = {"file": str(path.resolve()), "item": ordinal,
                          "request_id": event.get("request_id"), "action_id": action,
                          "actor": actor, "recipient": recipient,
                          "native_state": event["native_state"], "date_raw": event.get("date_raw"),
                          "session_id": event.get("session_id")}
            selected.append(provenance)
            after = proof["after"]
            expected[(recipient, actor, "favors")] = {
                "raw": after["favors_raw"], "scale": 1000, "event": provenance}
            if kind == "trust":
                expected[(recipient, actor, "trust")] = {
                    "raw": after["recipient_trust_raw"], "scale": 1, "event": provenance}
            else:
                for tag, key in ((actor, "actor_manpower_raw"), (recipient, "recipient_manpower_raw")):
                    expected[(tag, None, "manpower")] = {
                        "raw": after[key], "scale": 1000, "event": provenance}
    if not selected:
        errors.append("No complete Trust/Men settlement events")
    return expected, selected, errors


def apply_final_queries(paths: list[Path], expected: dict, settlements: list,
                        errors: list) -> list:
    """Account for natural monthly changes between earlier settlements.

    The settlement formulas remain checked by collect(). Final queries must
    come from the last settlement day, and cannot contradict a settlement
    field already observed on that same day.
    """
    final_date = max((event["date_raw"] for event in settlements), default=None)
    sessions = {event["session_id"] for event in settlements}
    observed = []
    for path in paths:
        for ordinal, event in _iter_json_file(path):
            if not isinstance(event, dict) or event.get("event") != "native_alliance_inspection":
                continue
            action = event.get("action_id")
            if action not in ACTION_KIND:
                continue
            actor, recipient = event.get("actor"), event.get("recipient")
            query = event.get("native_favor_trade")
            if (len(sessions) != 1 or event.get("session_id") not in sessions
                    or event.get("date_raw") != final_date
                    or not ObserverSession._valid_native_inspection(
                        event, action, actor, recipient, "initiate", final_date,
                        event.get("query_id"), event.get("session_id"))
                    or not validate_query(query) or not query["complete"]
                    or query["kind"] != ACTION_KIND[action]):
                errors.append(f"Invalid final resource query: {path}:{ordinal}")
                continue
            provenance = {"file": str(path.resolve()), "item": ordinal,
                          "source": "final_native_query", "date_raw": final_date,
                          "action_id": action, "actor": actor, "recipient": recipient,
                          "query_id": event["query_id"], "session_id": event["session_id"]}
            observed.append(provenance)
            values = {(recipient, actor, "favors"): (query["favors_available_raw"], 1000)}
            if query["kind"] == "trust":
                values[(recipient, actor, "trust")] = (query["recipient_trust_raw"], 1)
            else:
                values[(actor, None, "manpower")] = (query["actor_manpower_raw"], 1000)
                values[(recipient, None, "manpower")] = (query["recipient_manpower_raw"], 1000)
            for key, (raw, scale) in values.items():
                old = expected.get(key)
                if old is None:
                    errors.append(f"Final query introduces an untested resource: {key}")
                    continue
                if old["event"]["date_raw"] == final_date and old["raw"] != raw:
                    errors.append(f"Same-day resource changed after settlement: {key}")
                expected[key] = {"raw": raw, "scale": scale, "event": provenance,
                                 "last_settlement": old.get("last_settlement", old)}
    return observed


def scan(path: Path, expected: dict, save_sha256: str | None) -> dict:
    targets = {key[0] for key in expected}
    wanted_relations = {(key[0], key[1]) for key in expected if key[1] is not None}
    depth = 0
    countries_depth = country_depth = active_depth = relation_depth = None
    country = relation = None
    country_seen = set()
    relation_seen = set()
    fields = {}
    errors = []
    digest = hashlib.sha256() if save_sha256 is None else None
    countries_found = countries_complete = False
    line_count = 0
    with path.open("rb") as stream:
        for line_count, line in enumerate(stream, 1):
            if line_count == 1 and not line.startswith(b"EU4txt"):
                raise ValueError("Expected an uncompressed EU4 text save")
            if digest is not None:
                digest.update(line)
            stripped = line.strip()
            tag = TAG_OPEN.fullmatch(stripped)
            if countries_depth is None and depth == 0 and stripped == b"countries={":
                if countries_found:
                    errors.append("Duplicate countries block")
                countries_found = True
                countries_depth = depth + 1
            elif countries_depth is not None:
                if depth == countries_depth and tag:
                    value = tag.group(1).decode("ascii")
                    if value in targets:
                        country = value
                        country_depth = depth + 1
                        if value in country_seen:
                            errors.append(f"Duplicate country {value}")
                        country_seen.add(value)
                elif country is not None:
                    if depth == country_depth and stripped == b"active_relations={":
                        active_depth = depth + 1
                    elif active_depth is not None and depth == active_depth and tag:
                        value = tag.group(1).decode("ascii")
                        if (country, value) in wanted_relations:
                            relation = value
                            relation_depth = depth + 1
                            identity = (country, value)
                            if identity in relation_seen:
                                errors.append(f"Duplicate relation {country}/{value}")
                            relation_seen.add(identity)
                    else:
                        field = FIELD.fullmatch(stripped)
                        if field:
                            name = field.group(1).decode("ascii")
                            if name == "trust_value":
                                name = "trust"
                            key = (country, None, name) if depth == country_depth else (
                                (country, relation, name)
                                if relation is not None and depth == relation_depth else None)
                            if key in expected:
                                if key in fields:
                                    errors.append(f"Duplicate field {key}")
                                value = Decimal(field.group(2).decode("ascii"))
                                raw = value * expected[key]["scale"]
                                if raw != raw.to_integral_value():
                                    errors.append(f"Nonintegral resource {key} at line {line_count}")
                                fields[key] = {"line": line_count, "value": str(value), "raw": int(raw),
                                               "source": stripped.decode("ascii")}
            next_depth = depth + brace_delta(line)
            if relation_depth is not None and next_depth < relation_depth:
                relation = relation_depth = None
            if active_depth is not None and next_depth < active_depth:
                active_depth = None
            if country_depth is not None and next_depth < country_depth:
                country = country_depth = None
            if countries_depth is not None and next_depth < countries_depth:
                countries_complete = True
                countries_depth = None
            depth = next_depth
    if not countries_complete or depth != 0:
        errors.append("Country scan or save braces are incomplete")
    # The native relation writer a66770 omits +1e exactly when it equals
    # 0x32: cmp bl,0x32 at a668b0; je a668fa skips trust_value key 0x32d5.
    if countries_complete and depth == 0 and TRUST_SAVE_CONTRACT.is_file():
        for key in expected:
            country, relation, field = key
            if field == "trust" and key not in fields and (country, relation) in relation_seen:
                fields[key] = {"line": None, "value": "50", "raw": 50,
                               "source": "native_serializer_default_omitted",
                               "contract": str(TRUST_SAVE_CONTRACT.relative_to(ROOT))}
    return {"fields": fields, "errors": errors, "countries_found": countries_found,
            "countries_complete": countries_complete, "country_tags_found": sorted(country_seen),
            "line_count": line_count, "sha256": save_sha256 or digest.hexdigest(),
            "sha256_source": "caller_reference" if save_sha256 else "single_scan",
            "hash_passes": 0 if save_sha256 else 1}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", type=Path, required=True)
    parser.add_argument("--events", type=Path, nargs="+", required=True)
    parser.add_argument("--final-queries", type=Path, nargs="+", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--save-sha256")
    args = parser.parse_args()
    if args.save_sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", args.save_sha256):
        raise ValueError("Save hash must be a SHA256 reference")
    expected, events, errors = collect(args.events)
    final_queries = apply_final_queries(args.final_queries, expected, events, errors)
    state = scan(args.save, expected, args.save_sha256)
    errors.extend(state["errors"])
    rows = []
    for key, value in expected.items():
        actual = state["fields"].get(key)
        country, relation, field = key
        save_path = f"countries/{country}/" + (
            f"active_relations/{relation}/" if relation else "") + (
                "trust_value" if field == "trust" else field)
        rows.append({"save_path": save_path, "expected": value, "actual": actual,
                     "match": actual is not None and actual["raw"] == value["raw"]})
        if not rows[-1]["match"]:
            errors.append(f"Resource mismatch or absent field: {save_path}")
    report = {"schema": "r73_favor_save_v1", "status": "passed" if not errors else "failed",
              "errors": errors, "events": events, "final_queries": final_queries, "fields": rows,
              "save": {"path": str(args.save.resolve()), "size": args.save.stat().st_size,
                       **{key: value for key, value in state.items() if key not in ("fields", "errors")}}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"status": report["status"], "fields": len(rows), "errors": errors}, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
