"""Send one native, rule-checked inbound Peace fixture for an operator.

This single-use experiment creates an incoming proposal.  FRA's decision is
left pending for the public response tools; this is not an AI-facing tool.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import ObserverSession
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready


def _native_trade_power_contract(
        dispatched: list[dict[str, object]],
        pending: list[dict[str, object]], *, direction: str = "demand",
        source: str | None = None) -> bool:
    """Validate the serialized native peace payload for the T fixture.

    ``peace.selected_term_count`` is a native payload count.  It includes the
    native zero-gold/base selection alongside the requested transfer term, so
    it must not be compared with the one public T clause. Candidate counts
    vary with the war and its parties; this checks the selected base/T shape.
    """
    if len(dispatched) != 1 or len(pending) != 1:
        return False
    dispatch = dispatched[0]
    peace = pending[0].get("peace")
    if not isinstance(peace, dict):
        return False
    participant_counts = peace.get("participant_counts")
    return (
        dispatch.get("trade_power_requested") is True
        and dispatch.get("reparations_requested") is False
        and (direction == "demand" or dispatch.get("direction") == direction)
        and (source is None or dispatch.get("trade_power_source") == source)
        and peace.get("complete") is True
        and type(peace.get("term_count")) is int
        and peace.get("term_count") >= 2
        and type(peace.get("selected_term_count")) is int
        and peace.get("selected_term_count") == 2
        and isinstance(participant_counts, list)
        and len(participant_counts) == 4
        and all(type(value) is int for value in participant_counts)
        and peace.get("flag40") == 1
        and peace.get("direction41") == (1 if direction == "demand" else 0)
        and peace.get("preview208") == 0
    )


def _native_concede_defeat_contract(
        dispatched: list[dict[str, object]],
        pending: list[dict[str, object]], *, direction: str = "demand") -> bool:
    """Validate the native payload shape for the C fixture.

    The pending offer includes the native zero-gold/base candidate, so the
    selected count is two even though the public context contains one C term.
    """
    if len(dispatched) != 1 or len(pending) != 1 or direction != "demand":
        return False
    dispatch = dispatched[0]
    peace = pending[0].get("peace")
    if not isinstance(peace, dict):
        return False
    participant_counts = peace.get("participant_counts")
    return (
        dispatch.get("concede_defeat_requested") is True
        and dispatch.get("reparations_requested") is False
        and dispatch.get("trade_power_requested") is False
        and dispatch.get("direction") == "demand"
        and peace.get("complete") is True
        and type(peace.get("term_count")) is int
        and peace.get("term_count") >= 2
        and type(peace.get("selected_term_count")) is int
        and peace.get("selected_term_count") == 2
        and isinstance(participant_counts, list)
        and len(participant_counts) == 4
        and all(type(value) is int for value in participant_counts)
        and peace.get("flag40") == 1
        and peace.get("direction41") == 1
        and peace.get("preview208") == 0
    )


def _normalize_annul(country: str | None, partners: list[str] | None) -> tuple[str, list[str]]:
    if not isinstance(country, str) or not re.fullmatch(r"[A-Z0-9]{3}", country):
        raise ValueError("ANNUL_COUNTRY_REQUIRED")
    if not isinstance(partners, list) or not 1 <= len(partners) <= 16:
        raise ValueError("ANNUL_PARTNERS_REQUIRED")
    values = [str(item).upper() for item in partners]
    if (any(not re.fullmatch(r"[A-Z0-9]{3}", item) for item in values)
            or len(set(values)) != len(values)
            or values != sorted(values)
            or country in values):
        raise ValueError("ANNUL_PARTNERS_INVALID")
    return country, values


def _native_annul_treaties_contract(
        dispatched: list[dict[str, object]],
        pending: list[dict[str, object]], *,
        country: str, partners: list[str], direction: str = "demand") -> bool:
    """Validate the native shape without assuming candidate-list size."""
    if len(dispatched) != 1 or len(pending) != 1 or direction != "demand":
        return False
    dispatch = dispatched[0]
    peace = pending[0].get("peace")
    if not isinstance(peace, dict):
        return False
    selected = peace.get("selected_annul_treaties")
    selected_ok = selected is None or (
        isinstance(selected, dict)
        and selected.get("country") == country
        and selected.get("treaty_partners") == partners)
    return (
        dispatch.get("annul_treaties_requested") is True
        and dispatch.get("annul_country", country) == country
        and dispatch.get("annul_partners", partners) == partners
        and dispatch.get("reparations_requested") is False
        and dispatch.get("trade_power_requested") is False
        and dispatch.get("concede_defeat_requested") is False
        and dispatch.get("direction") == "demand"
        and peace.get("complete") is True
        and type(peace.get("term_count")) is int
        and peace.get("term_count") >= 2
        and peace.get("selected_term_count") == 1 + len(partners)
        and peace.get("flag40") == 1
        and peace.get("direction41") == 1
        and peace.get("preview208") == 0
        and selected_ok)


def _native_special_contract(
        dispatched: list[dict[str, object]],
        pending: list[dict[str, object]], *, term: str,
        direction: str = "demand", proposer: str = "ENG",
        recipient: str = "FRA") -> bool:
    """Validate one native H/S/F pending fixture without guessing legality."""
    if len(dispatched) != 1 or len(pending) != 1:
        return False
    if direction not in {"demand", "offer"}:
        return False
    # The native offer fixture is intentionally limited to Show Strength for
    # the historical ENG path and Force Religion for the explicit LEI path.
    # Both paths retain the native actor/recipient identity in the pending
    # event; the response side must not infer ENG from the direction bit.
    if direction == "offer" and not (
            term == "show_strength" and proposer == "ENG"
            or term == "force_religion" and proposer == "LEI"):
        return False
    dispatch = dispatched[0]
    peace = pending[0].get("peace")
    if not isinstance(peace, dict):
        return False
    requested_key = {
        "humiliate_rival": "humiliate_rival_requested",
        "show_strength": "show_strength_requested",
        "force_religion": "force_religion_requested",
    }.get(term)
    if requested_key is None:
        return False
    result = (
        dispatch.get(requested_key) is True
        and all(dispatch.get(key, False) is False for key in (
            "reparations_requested", "trade_power_requested",
            "concede_defeat_requested", "annul_treaties_requested"))
        and dispatch.get("direction") == direction
        and peace.get("complete") is True
        and type(peace.get("term_count")) is int
        and peace.get("term_count") >= 2
        and peace.get("selected_term_count") == 2
        and peace.get("flag40") == 1
        and peace.get("direction41") == (1 if direction == "demand" else 0)
        and peace.get("preview208") == 0)
    if not result or direction != "offer":
        return result
    # The pending event must retain the complete native actor/recipient
    # identity.  A direction bit alone is insufficient to prove the offer is
    # ENG -> FRA with FRA as the decision country.
    return (
        pending[0].get("actor") == proposer
        and pending[0].get("mirror") == proposer
        and pending[0].get("recipient") == recipient
        and pending[0].get("decision_country") == recipient
        and pending[0].get("decision_country_verified") is True
    )


def _fixture_wire(term: str, direction: str, source: str | None,
                  annul_country: str | None = None,
                  annul_partners: list[str] | None = None,
                  proposer: str = "ENG", recipient: str = "FRA") -> str:
    if proposer not in {"ENG", "LEI", "BUR"} or recipient != "FRA":
        raise ValueError("UNSUPPORTED_INBOUND_PROPOSER_OR_RECIPIENT")
    if proposer == "BUR":
        if (term != "white_peace" or direction != "demand" or source is not None
                or annul_country is not None or annul_partners is not None):
            raise ValueError("BUR_FIXTURE_WHITE_PEACE_ONLY")
        return "TEST_ONLY BUR_PEACE_FRA_WHITE_PENDING\n"
    if term == "annul_treaties":
        if direction != "demand" or source is not None:
            raise ValueError("ANNUL_TREATIES_DEMAND_ONLY")
        country, partners = _normalize_annul(annul_country, annul_partners)
        if proposer != "ENG":
            raise ValueError("ANNUL_TREATIES_PROPOSER_UNSUPPORTED")
        return ("TEST_ONLY ENG_PEACE_FRA_ANNUL_TREATIES_PENDING\t"
                f"{country}\t{','.join(partners)}\n")
    if term in {"humiliate_rival", "show_strength", "force_religion"}:
        if source is not None:
            raise ValueError("SPECIAL_SOURCE_UNSUPPORTED")
        if direction == "offer":
            if proposer == "ENG" and term == "show_strength":
                return "TEST_ONLY ENG_PEACE_FRA_SHOW_STRENGTH_OFFER_PENDING\n"
            if proposer == "LEI" and term == "force_religion":
                return "TEST_ONLY LEI_PEACE_FRA_FORCE_RELIGION_OFFER_PENDING\n"
            if proposer == "ENG" and term == "force_religion":
                raise ValueError("SPECIAL_OFFER_UNSUPPORTED")
            if term not in {"show_strength", "force_religion"}:
                raise ValueError("SPECIAL_OFFER_UNSUPPORTED")
            raise ValueError("SPECIAL_OFFER_PROPOSER_UNSUPPORTED")
        if direction != "demand":
            raise ValueError("SPECIAL_DIRECTION_UNSUPPORTED")
        kind = {
            "humiliate_rival": "HUMILIATE_RIVAL",
            "show_strength": "SHOW_STRENGTH",
            "force_religion": "FORCE_RELIGION",
        }[term]
        if proposer != "ENG":
            raise ValueError("SPECIAL_DEMAND_PROPOSER_UNSUPPORTED")
        return f"TEST_ONLY ENG_PEACE_FRA_{kind}_PENDING\n"
    if direction == "offer":
        if (term != "transfer_trade_power" or not isinstance(source, str)
                or not re.fullmatch(r"[A-Z0-9]{3}", source) or source == "FRA"):
            raise ValueError("TRADE_POWER_OFFER_SOURCE_REQUIRED")
        if proposer != "ENG":
            raise ValueError("TRADE_POWER_PROPOSER_UNSUPPORTED")
        return f"TEST_ONLY ENG_PEACE_FRA_TRADE_POWER_OFFER_PENDING {source}\n"
    if direction != "demand" or source is not None:
        raise ValueError("EXPLICIT_SOURCE_REQUIRES_TRADE_POWER_OFFER_FIXTURE")
    kind = {"white_peace": "WHITE", "war_reparations": "REPARATIONS",
            "transfer_trade_power": "TRADE_POWER",
            "concede_defeat": "CONCEDE_DEFEAT"}[term]
    if proposer != "ENG":
        raise ValueError("DEMAND_PROPOSER_UNSUPPORTED")
    return f"TEST_ONLY ENG_PEACE_FRA_{kind}_PENDING\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--term", choices=("white_peace", "war_reparations",
                                            "transfer_trade_power",
                                            "concede_defeat", "annul_treaties",
                                            "humiliate_rival", "show_strength",
                                            "force_religion"),
                        default="war_reparations")
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument("--direction", choices=("demand", "offer"), default="demand")
    parser.add_argument("--proposer", choices=("ENG", "LEI", "BUR"), default="ENG",
                        help="native inbound proposer; ENG is retained for legacy fixtures")
    parser.add_argument("--trade-power-source")
    parser.add_argument("--annul-country")
    parser.add_argument("--annul-partners", nargs="+")
    args = parser.parse_args()
    wire = _fixture_wire(
        args.term, args.direction, args.trade_power_source,
        args.annul_country, args.annul_partners, args.proposer, "FRA")
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("OUTPUT_ALREADY_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    session = ObserverSession(args.installation, game_exe())
    report = {
        "validator": Path(__file__).name, "private": True,
        "session_id": session.session_id, "term": args.term,
        "request_id": args.request_id, "status": "unknown", "publish_count": 0,
        "source": "explicit_operator_native_fixture",
        "proposer": args.proposer,
        "recipient": "FRA",
        "direction": args.direction, "trade_power_source": args.trade_power_source,
        "annul_country": args.annul_country,
        "annul_partners": args.annul_partners,
        "fra_decision_submitted": False,
    }
    log = session.directory / "control-probe.jsonl"
    start = log.stat().st_size
    raw = b""
    try:
        health = wait_runtime_ready(session, timeout=25, restore_minimized=True)
        report["health"] = health
        if health.get("status") != "ready" or health.get("date_raw") != args.expected_date_raw:
            raise RuntimeError("EXPECTED_READY_DATE_REQUIRED")
        report["publication"] = session._publish_atomic_request(
            wire, args.request_id, "diplomacy-authority-test.req")
        report["publish_count"] = 1 if report["publication"] == "published" else 0
        if report["publish_count"] != 1:
            raise RuntimeError("FIXTURE_NOT_PUBLISHED")
        events = []
        pending = []
        dispatched = []
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            available = log.stat().st_size - start
            if available > 4 * 1024 * 1024:
                raise RuntimeError("FIXTURE_LOG_SLICE_LIMIT")
            with log.open("rb") as stream:
                stream.seek(start)
                raw = stream.read(available)
            events = []
            for line in raw.splitlines():
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                if event.get("session_id") in (None, session.session_id):
                    events.append(event)
            dispatched = [e for e in events if e.get("event") ==
                          "native_peace_inbound_fixture_dispatched"]
            pending = [e for e in events if e.get("event") == "native_alliance_inbound_offer"
                       and e.get("actor") == args.proposer
                       and e.get("recipient") == "FRA"
                       and e.get("family") == "peace"]
            if pending or dispatched and dispatched[-1].get("dispatcher_accepted") is False:
                break
            if any(e.get("request_id") == "peace_inbound_fixture"
                   and e.get("reason") for e in events):
                break
            time.sleep(0.1)
        report["dispatch"] = dispatched
        report["pending"] = pending
        checks = {
            "published_once": report["publish_count"] == 1,
            "single_dispatch": len(dispatched) == 1,
            "dispatcher_accepted": len(dispatched) == 1
                and dispatched[0].get("dispatcher_accepted") is True,
            "native_gates_available": len(dispatched) == 1
                and dispatched[0].get("native_gates_available") is True,
            "no_fra_initiation_authority": len(dispatched) == 1
                and dispatched[0].get("authority_seed_created") is False,
            "single_native_pending": len(pending) == 1,
            "full_native_payload": len(pending) == 1
                and pending[0].get("peace", {}).get("complete") is True,
            "native_pending_source": len(pending) == 1
                and pending[0].get("source_verified") is True
                and pending[0].get("pending_source") == "native_executor_pending_block",
        }
        if args.term == "war_reparations":
            checks["reparations_selected"] = (
                len(dispatched) == 1 and dispatched[0].get("reparations_requested") is True
                and len(pending) == 1
                and pending[0].get("peace", {}).get("selected_term_count") == 2)
        elif args.term == "transfer_trade_power":
            checks["trade_power_selected"] = _native_trade_power_contract(
                dispatched, pending, direction=args.direction, source=args.trade_power_source)
        elif args.term == "concede_defeat":
            checks["concede_defeat_selected"] = _native_concede_defeat_contract(
                dispatched, pending, direction=args.direction)
        elif args.term == "annul_treaties":
            country, partners = _normalize_annul(
                args.annul_country, args.annul_partners)
            checks["annul_treaties_selected"] = _native_annul_treaties_contract(
                dispatched, pending, country=country, partners=partners,
                direction=args.direction)
        elif args.term in {"humiliate_rival", "show_strength", "force_religion"}:
            checks["special_selected"] = _native_special_contract(
                dispatched, pending, term=args.term, direction=args.direction,
                proposer=args.proposer, recipient="FRA")
        report["checks"] = checks
        report["status"] = "passed" if all(checks.values()) else "failed"
    except Exception as error:
        report["error"] = {"type": type(error).__name__, "text": str(error)}
        report["status"] = "failed"
    finally:
        slice_path = output.with_name(output.stem + "-native-events.jsonl")
        slice_path.write_bytes(raw)
        report["native_events"] = {
            "path": str(slice_path), "start_offset": start, "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(), "complete": raw.endswith(b"\n"),
        }
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(output)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
