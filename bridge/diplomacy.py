"""Four semantic diplomacy tools with explicit, evidence-limited support.

The observer supplies real session health, not game legality. Unimplemented
native actions never enqueue a legacy request or execute a console script.
"""
from __future__ import annotations

import hashlib
import json
import ctypes
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

from .diplomacy_catalog import ACTIONS, INBOUND_ACTIONS, PEACE_ACTION_IDS
from .diplomacy_journal import (AmbiguousRequestError, ContextMismatchError, DurableJournal,
                                EvidenceConflictError, InvalidTransitionError,
                                RequestConflictError, UnknownRequestError)
from .diplomacy_session import probe_identity
from .native_text import (DEFAULT_NATIVE_TEXT_CODEC, InvalidNativeText,
                          decode_native_text_hex, validate_native_text_codec)
from .peace_execution import normalize_peace_execution_parameters


def reason(code: str, text: str, source: str, complete: bool = False) -> dict:
    return {"code": code, "text": text, "source": source, "complete": complete}


_INSTALL_ACK_HEADER_BYTES = 64 * 1024
_MAX_REASON_ITEMS = 32
_NATIVE_OFFER_SUBMISSION_CAPABILITY = "native_offer_submission"
_NATIVE_DISSOLVE_SUBMISSION_CAPABILITY = "native_dissolve_submission"
_NATIVE_ROYAL_MARRIAGE_SUBMISSION_CAPABILITY = "native_royal_marriage_submission"
_NATIVE_IMPROVE_RELATIONS_SUBMISSION_CAPABILITY = "native_improve_relations_submission"
_NATIVE_SPY_NETWORK_SUBMISSION_CAPABILITY = "native_spy_network_submission"
_NATIVE_GUARANTEE_SUBMISSION_CAPABILITY = "native_guarantee_submission"
_NATIVE_SUPPORT_INDEPENDENCE_SUBMISSION_CAPABILITY = "native_support_independence_submission"
_NATIVE_MILITARY_ACCESS_SUBMISSION_CAPABILITY = "native_military_access_submission"
_NATIVE_INSULT_SUBMISSION_CAPABILITY = "native_insult_submission"
_NATIVE_INBOUND_ALLIANCE_CAPABILITY = "native_inbound_alliance"
_NATIVE_INBOUND_RESPONSE_CAPABILITY = "native_inbound_alliance_response"
_NATIVE_INBOUND_ROYAL_RESPONSE_CAPABILITY = "native_inbound_royal_marriage_response"
_NATIVE_INBOUND_SUPPORT_RESPONSE_CAPABILITY = "native_inbound_support_independence_response"
_NATIVE_INBOUND_MILITARY_ACCESS_RESPONSE_CAPABILITY = "native_inbound_military_access_response"
_NATIVE_INBOUND_VASSAL_RESPONSE_CAPABILITY = "native_inbound_vassalization_response"
_NATIVE_INBOUND_PEACE_RESPONSE_CAPABILITY = "native_inbound_peace_response"
_NATIVE_REASON_METADATA_CAPABILITY = "native_alliance_reason_metadata"
_NATIVE_ROYAL_MARRIAGE_QUERY_CAPABILITY = "native_royal_marriage_query"
_NATIVE_IMPROVE_RELATIONS_QUERY_CAPABILITY = "native_improve_relations_query"
_NATIVE_SPY_NETWORK_QUERY_CAPABILITY = "native_spy_network_query"
_NATIVE_GUARANTEE_QUERY_CAPABILITY = "native_guarantee_query"
_NATIVE_SUPPORT_INDEPENDENCE_QUERY_CAPABILITY = "native_support_independence_query"
_NATIVE_MILITARY_ACCESS_QUERY_CAPABILITY = "native_military_access_query"
_NATIVE_INSULT_QUERY_CAPABILITY = "native_insult_query"
_NATIVE_RIVAL_QUERY_CAPABILITY = "native_rival_query"
_NATIVE_RIVAL_SUBMISSION_CAPABILITY = "native_rival_submission"
_NATIVE_VASSALIZATION_QUERY_CAPABILITY = "native_vassalization_query"
_NATIVE_VASSALIZATION_SUBMISSION_CAPABILITY = "native_vassalization_submission"
_NATIVE_DECLARE_WAR_QUERY_CAPABILITY = "native_declare_war_query"
_NATIVE_DECLARE_WAR_SUBMISSION_CAPABILITY = "native_declare_war_submission"
_NATIVE_PEACE_SUBMISSION_CAPABILITY = "native_peace_submission"
_NATIVE_PEACE_CONTEXT_QUERY_CAPABILITY = "native_peace_context_query"
_NATIVE_PEACE_EMPTY_OFFER_QUERY_CAPABILITY = "native_peace_empty_offer_query"
_NATIVE_PEACE_OFFER_EVALUATION_QUERY_CAPABILITY = "native_peace_offer_evaluation_query"
_NATIVE_PEACE_MONEY_OFFER_QUERY_CAPABILITY = "native_peace_money_offer_query"
_NATIVE_PEACE_PROVINCE_OFFER_QUERY_CAPABILITY = "native_peace_province_offer_query"
_NATIVE_PEACE_COMBINED_QUERY_CAPABILITY = "native_peace_combined_query"
_NATIVE_PEACE_REPARATIONS_QUERY_CAPABILITY = "native_peace_reparations_query"
_NATIVE_PEACE_REPARATIONS_EXECUTION_CAPABILITY = "native_peace_reparations_execution"
_NATIVE_PEACE_WRAPPER_RULE_QUERY_CAPABILITY = "native_peace_wrapper_rule_query"
_EXECUTE_REQUEST_NAME = "diplomacy-execute.req"
_PEACE_EXECUTE_REQUEST_NAME = "diplomacy-peace-execute.req"
_RIVAL_EXECUTE_REQUEST_NAME = "rival-execute.req"
_INBOUND_QUERY_REQUEST_NAME = "diplomacy-inbound-query.req"
_INBOUND_RESPONSE_REQUEST_NAME = "diplomacy-respond.req"
_EXECUTE_WAIT_SECONDS = 10.0
_FILETIME_EPOCH = 116444736000000000
_RESPONSE_LOG_CHUNK_BYTES = 64 * 1024
_RESPONSE_LOG_SCAN_BYTES = 8 * 1024 * 1024
_RESPONSE_LOG_LINE_BYTES = 256 * 1024
_HEALTH_LOG_MAX_TAIL_BYTES = 1024 * 1024
_NATIVE_QUERY_CAPS = frozenset({
    "native_alliance_inspection", "native_alliance_query", "alliance_inspection",
    "alliance_query", "native_queries", "native_queries_enabled",
})

# This is the complete set of implemented initiation actions whose native
# query may expose a counterparty acceptance score/predicate.  Keep the
# explicit action-to-family/capability table closed: catalog entries that
# merely declare ``response=True`` do not gain scoring or native execution by
# accident.
_NEGOTIATED_NATIVE_ACTIONS = {
    "offer_alliance": ("alliance", _NATIVE_OFFER_SUBMISSION_CAPABILITY),
    "offer_royal_marriage": (
        "royal_marriage", _NATIVE_ROYAL_MARRIAGE_SUBMISSION_CAPABILITY),
    "support_independence": (
        "support_independence", _NATIVE_SUPPORT_INDEPENDENCE_SUBMISSION_CAPABILITY),
    "ask_military_access": (
        "military_access", _NATIVE_MILITARY_ACCESS_SUBMISSION_CAPABILITY),
    "offer_vassalization": (
        "vassalization", _NATIVE_VASSALIZATION_SUBMISSION_CAPABILITY),
}
_NEGOTIATED_INITIATION_ACTIONS = frozenset(_NEGOTIATED_NATIVE_ACTIONS)
_INSULT_ACTIONS = frozenset(("send_insult", "scornful_insult"))
_RIVAL_ACTIONS = frozenset(("set_rival", "remove_rival"))
_VASSALIZATION_ACTIONS = frozenset(("offer_vassalization", "cancel_vassalization"))
_PEACE_EXECUTION_ACTIONS = frozenset(
    ("white_peace", "demand_ducats", "cede_province", "war_reparations"))
_PEACE_WAR_ID_PATTERN = r"war_[0-9a-f]{16}_[0-9a-f]{8}"
_MAX_PEACE_EVALUATION_FACTORS = 64


def _native_tick_count_ms() -> int:
    """Return the Windows monotonic tick used by the Rival wire deadline.

    The fallback keeps offline contract tests portable; a live Windows
    installation always uses ``GetTickCount64`` with its 64-bit return type.
    """

    try:
        kernel32 = getattr(ctypes, "windll", None)
        if kernel32 is not None:
            get_tick = kernel32.kernel32.GetTickCount64
            get_tick.restype = ctypes.c_ulonglong
            get_tick.argtypes = []
            return int(get_tick())
    except (AttributeError, OSError, TypeError):
        pass
    return time.monotonic_ns() // 1_000_000


def _inbound_family(action_id: str) -> str | None:
    if action_id == "peace_offer":
        return "peace"
    spec = _NEGOTIATED_NATIVE_ACTIONS.get(action_id)
    return spec[0] if spec is not None else None


def _inbound_response_capability(action_id: str) -> str | None:
    if action_id == "offer_alliance":
        return _NATIVE_INBOUND_RESPONSE_CAPABILITY
    if action_id == "offer_royal_marriage":
        return _NATIVE_INBOUND_ROYAL_RESPONSE_CAPABILITY
    if action_id == "support_independence":
        return _NATIVE_INBOUND_SUPPORT_RESPONSE_CAPABILITY
    if action_id == "ask_military_access":
        return _NATIVE_INBOUND_MILITARY_ACCESS_RESPONSE_CAPABILITY
    if action_id == "offer_vassalization":
        return _NATIVE_INBOUND_VASSAL_RESPONSE_CAPABILITY
    if action_id == "peace_offer":
        return _NATIVE_INBOUND_PEACE_RESPONSE_CAPABILITY
    return None


class ObserverSession:
    """Trusted operator binding; no process or filesystem identifiers go out."""

    def __init__(self, installation: Path, game_exe: Path):
        self.directory = installation.resolve().parent
        self.record = json.loads(installation.read_text(encoding="utf-8"))
        self.game_exe = game_exe
        self.experiment_id = self.record["experiment_id"]
        self.session_id = self.record["session_id"]
        self.native_text_codec = validate_native_text_codec(
            self.record.get("native_text_codec", DEFAULT_NATIVE_TEXT_CODEC))
        self._response_log_offsets: dict[str, int] = {}
        # Inbound observations use one bounded stream cursor, while the
        # native proposal id is kept as a per-proposal de-duplication key.
        # The mapping deliberately remains private: it contains the native
        # session and payload needed by a future response wire.
        self._inbound_log_offset = 0
        self._inbound_seen_native_proposals: set[int] = set()
        self._inbound_private_proposals: dict[str, dict] = {}

    def _installation_ack(self) -> dict | None:
        """Return only this installation's bounded, operator-owned ack."""
        log = self.directory / "control-probe.jsonl"
        try:
            with log.open("rb") as stream:
                header = stream.read(_INSTALL_ACK_HEADER_BYTES)
        except OSError:
            return None
        # Search only the bounded header. Startup health lines may precede the
        # installation acknowledgement, so line position is not an identity
        # signal.
        for raw_line in header.splitlines():
            try:
                event = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                continue
            if (isinstance(event, dict)
                    and event.get("event") == "diplomacy_observer_installed"
                    and event.get("session_id") == self.session_id):
                return event
        return None

    def installation_capabilities(self) -> frozenset[str]:
        """Read capabilities from the exact installation ack without querying the game."""
        ack = self._installation_ack()
        if ack is None:
            return frozenset()
        capabilities: set[str] = set()
        advertised = ack.get("caps", ack.get("capabilities"))
        if isinstance(advertised, dict):
            capabilities.update(key for key, value in advertised.items()
                                if isinstance(key, str) and len(key) <= 80 and value is True)
        elif isinstance(advertised, (list, tuple, set)):
            capabilities.update(value for value in advertised
                                if isinstance(value, str) and len(value) <= 80)
        # The inbound observer and response adapters require their explicit
        # top-level ACKs; a copied caps list cannot grant either authority.
        capabilities.discard(_NATIVE_INBOUND_ALLIANCE_CAPABILITY)
        capabilities.discard(_NATIVE_INBOUND_RESPONSE_CAPABILITY)
        capabilities.discard(_NATIVE_INBOUND_ROYAL_RESPONSE_CAPABILITY)
        capabilities.discard(_NATIVE_INBOUND_SUPPORT_RESPONSE_CAPABILITY)
        capabilities.discard(_NATIVE_INBOUND_MILITARY_ACCESS_RESPONSE_CAPABILITY)
        capabilities.discard(_NATIVE_INBOUND_PEACE_RESPONSE_CAPABILITY)
        capabilities.discard(_NATIVE_REASON_METADATA_CAPABILITY)
        capabilities.discard(_NATIVE_DISSOLVE_SUBMISSION_CAPABILITY)
        capabilities.discard(_NATIVE_ROYAL_MARRIAGE_SUBMISSION_CAPABILITY)
        capabilities.discard(_NATIVE_IMPROVE_RELATIONS_SUBMISSION_CAPABILITY)
        capabilities.discard(_NATIVE_SPY_NETWORK_SUBMISSION_CAPABILITY)
        capabilities.discard(_NATIVE_GUARANTEE_SUBMISSION_CAPABILITY)
        capabilities.discard(_NATIVE_SUPPORT_INDEPENDENCE_SUBMISSION_CAPABILITY)
        capabilities.discard(_NATIVE_MILITARY_ACCESS_SUBMISSION_CAPABILITY)
        capabilities.discard(_NATIVE_INSULT_SUBMISSION_CAPABILITY)
        capabilities.discard(_NATIVE_RIVAL_SUBMISSION_CAPABILITY)
        capabilities.discard(_NATIVE_DECLARE_WAR_QUERY_CAPABILITY)
        capabilities.discard(_NATIVE_PEACE_SUBMISSION_CAPABILITY)
        # Royal-marriage inspection is granted only by its dedicated
        # top-level literal ACK below.  A copied caps/capabilities entry is
        # not an installation proof for the new native adapter.
        capabilities.discard(_NATIVE_ROYAL_MARRIAGE_QUERY_CAPABILITY)
        # ImproveRelations inspection is granted only by its dedicated
        # top-level literal ACK; a copied caps entry cannot grant it.
        capabilities.discard(_NATIVE_IMPROVE_RELATIONS_QUERY_CAPABILITY)
        # Spy Network inspection is granted only by its dedicated top-level
        # literal ACK; a copied caps entry cannot grant this family.
        capabilities.discard(_NATIVE_SPY_NETWORK_QUERY_CAPABILITY)
        # Guarantee inspection is granted only by its dedicated top-level
        # literal ACK; a copied caps entry cannot grant this family.
        capabilities.discard(_NATIVE_GUARANTEE_QUERY_CAPABILITY)
        # Support Independence inspection is granted only by its dedicated
        # top-level literal ACK; a copied caps entry cannot grant it.
        capabilities.discard(_NATIVE_SUPPORT_INDEPENDENCE_QUERY_CAPABILITY)
        capabilities.discard(_NATIVE_MILITARY_ACCESS_QUERY_CAPABILITY)
        capabilities.discard(_NATIVE_INSULT_QUERY_CAPABILITY)
        # Rival inspection is granted only by its dedicated top-level literal
        # ACK; a copied caps entry cannot grant the countrycommands adapter.
        capabilities.discard(_NATIVE_RIVAL_QUERY_CAPABILITY)
        # Vassalization inspection and submission are each granted only by
        # their dedicated top-level literal ACKs.
        capabilities.discard(_NATIVE_VASSALIZATION_QUERY_CAPABILITY)
        capabilities.discard(_NATIVE_VASSALIZATION_SUBMISSION_CAPABILITY)
        capabilities.discard(_NATIVE_DECLARE_WAR_SUBMISSION_CAPABILITY)
        # Peace-context discovery is granted only by its exact top-level
        # literal ACK; a copied caps entry cannot authorize QUERY1.
        capabilities.discard(_NATIVE_PEACE_CONTEXT_QUERY_CAPABILITY)
        # The empty-offer constructor/query is a separate read-only ACK.  A
        # context-enumeration ACK must never imply that QUERY4 is available.
        capabilities.discard(_NATIVE_PEACE_EMPTY_OFFER_QUERY_CAPABILITY)
        # The optional score/factor readout is independently acknowledged;
        # a copied caps entry must not activate the evaluator.
        capabilities.discard(_NATIVE_PEACE_OFFER_EVALUATION_QUERY_CAPABILITY)
        # QUERY5 money-offer inspection is also granted only by its exact
        # top-level ACK; a copied caps entry must not activate it.
        capabilities.discard(_NATIVE_PEACE_MONEY_OFFER_QUERY_CAPABILITY)
        # QUERY6 province-offer inspection is separately acknowledged; the
        # other peace query ACKs must never imply it.
        capabilities.discard(_NATIVE_PEACE_PROVINCE_OFFER_QUERY_CAPABILITY)
        # Mixed money+province inspection is a separate aggregate ACK.  A
        # single-term query ACK must never authorize a combined native query.
        capabilities.discard(_NATIVE_PEACE_COMBINED_QUERY_CAPABILITY)
        # The wrapper-rule proof is a separate read-only ACK.  Older query
        # capability lists must not activate the new four-proof validator.
        capabilities.discard(_NATIVE_PEACE_WRAPPER_RULE_QUERY_CAPABILITY)
        capabilities.discard(_NATIVE_INBOUND_VASSAL_RESPONSE_CAPABILITY)
        # v10's exact ack uses this boolean instead of a caps array.
        if ack.get("native_queries_enabled") is True:
            capabilities.add("native_alliance_inspection")
        # Native execution builds advertise this capability as a top-level
        # boolean. Only the literal JSON true authorizes submission.
        if ack.get(_NATIVE_OFFER_SUBMISSION_CAPABILITY) is True:
            capabilities.add(_NATIVE_OFFER_SUBMISSION_CAPABILITY)
        if ack.get(_NATIVE_DISSOLVE_SUBMISSION_CAPABILITY) is True:
            capabilities.add(_NATIVE_DISSOLVE_SUBMISSION_CAPABILITY)
        if ack.get(_NATIVE_ROYAL_MARRIAGE_SUBMISSION_CAPABILITY) is True:
            capabilities.add(_NATIVE_ROYAL_MARRIAGE_SUBMISSION_CAPABILITY)
        if ack.get(_NATIVE_IMPROVE_RELATIONS_SUBMISSION_CAPABILITY) is True:
            capabilities.add(_NATIVE_IMPROVE_RELATIONS_SUBMISSION_CAPABILITY)
        if ack.get(_NATIVE_SPY_NETWORK_SUBMISSION_CAPABILITY) is True:
            capabilities.add(_NATIVE_SPY_NETWORK_SUBMISSION_CAPABILITY)
        if ack.get(_NATIVE_GUARANTEE_SUBMISSION_CAPABILITY) is True:
            capabilities.add(_NATIVE_GUARANTEE_SUBMISSION_CAPABILITY)
        if ack.get(_NATIVE_SUPPORT_INDEPENDENCE_SUBMISSION_CAPABILITY) is True:
            capabilities.add(_NATIVE_SUPPORT_INDEPENDENCE_SUBMISSION_CAPABILITY)
        if ack.get(_NATIVE_MILITARY_ACCESS_SUBMISSION_CAPABILITY) is True:
            capabilities.add(_NATIVE_MILITARY_ACCESS_SUBMISSION_CAPABILITY)
        if ack.get(_NATIVE_INSULT_SUBMISSION_CAPABILITY) is True:
            capabilities.add(_NATIVE_INSULT_SUBMISSION_CAPABILITY)
        if ack.get(_NATIVE_RIVAL_SUBMISSION_CAPABILITY) is True:
            capabilities.add(_NATIVE_RIVAL_SUBMISSION_CAPABILITY)
        if ack.get(_NATIVE_VASSALIZATION_SUBMISSION_CAPABILITY) is True:
            capabilities.add(_NATIVE_VASSALIZATION_SUBMISSION_CAPABILITY)
        if ack.get(_NATIVE_DECLARE_WAR_SUBMISSION_CAPABILITY) is True:
            capabilities.add(_NATIVE_DECLARE_WAR_SUBMISSION_CAPABILITY)
        if ack.get(_NATIVE_PEACE_SUBMISSION_CAPABILITY) is True:
            capabilities.add(_NATIVE_PEACE_SUBMISSION_CAPABILITY)
        # r21's inbound build is observation/defer only.  This flag grants
        # bounded observation, never acceptance or rejection authority.
        if ack.get(_NATIVE_INBOUND_ALLIANCE_CAPABILITY) is True:
            capabilities.add(_NATIVE_INBOUND_ALLIANCE_CAPABILITY)
        if ack.get(_NATIVE_INBOUND_RESPONSE_CAPABILITY) is True:
            capabilities.add(_NATIVE_INBOUND_RESPONSE_CAPABILITY)
        if ack.get(_NATIVE_INBOUND_ROYAL_RESPONSE_CAPABILITY) is True:
            capabilities.add(_NATIVE_INBOUND_ROYAL_RESPONSE_CAPABILITY)
        if ack.get(_NATIVE_INBOUND_SUPPORT_RESPONSE_CAPABILITY) is True:
            capabilities.add(_NATIVE_INBOUND_SUPPORT_RESPONSE_CAPABILITY)
        if ack.get(_NATIVE_INBOUND_MILITARY_ACCESS_RESPONSE_CAPABILITY) is True:
            capabilities.add(_NATIVE_INBOUND_MILITARY_ACCESS_RESPONSE_CAPABILITY)
        if ack.get(_NATIVE_INBOUND_VASSAL_RESPONSE_CAPABILITY) is True:
            capabilities.add(_NATIVE_INBOUND_VASSAL_RESPONSE_CAPABILITY)
        if ack.get(_NATIVE_INBOUND_PEACE_RESPONSE_CAPABILITY) is True:
            capabilities.add(_NATIVE_INBOUND_PEACE_RESPONSE_CAPABILITY)
        if ack.get(_NATIVE_REASON_METADATA_CAPABILITY) is True:
            capabilities.add(_NATIVE_REASON_METADATA_CAPABILITY)
        if ack.get(_NATIVE_ROYAL_MARRIAGE_QUERY_CAPABILITY) is True:
            capabilities.add(_NATIVE_ROYAL_MARRIAGE_QUERY_CAPABILITY)
        if ack.get(_NATIVE_IMPROVE_RELATIONS_QUERY_CAPABILITY) is True:
            capabilities.add(_NATIVE_IMPROVE_RELATIONS_QUERY_CAPABILITY)
        if ack.get(_NATIVE_SPY_NETWORK_QUERY_CAPABILITY) is True:
            capabilities.add(_NATIVE_SPY_NETWORK_QUERY_CAPABILITY)
        if ack.get(_NATIVE_GUARANTEE_QUERY_CAPABILITY) is True:
            capabilities.add(_NATIVE_GUARANTEE_QUERY_CAPABILITY)
        if ack.get(_NATIVE_SUPPORT_INDEPENDENCE_QUERY_CAPABILITY) is True:
            capabilities.add(_NATIVE_SUPPORT_INDEPENDENCE_QUERY_CAPABILITY)
        if ack.get(_NATIVE_MILITARY_ACCESS_QUERY_CAPABILITY) is True:
            capabilities.add(_NATIVE_MILITARY_ACCESS_QUERY_CAPABILITY)
        if ack.get(_NATIVE_INSULT_QUERY_CAPABILITY) is True:
            capabilities.add(_NATIVE_INSULT_QUERY_CAPABILITY)
        if ack.get(_NATIVE_RIVAL_QUERY_CAPABILITY) is True:
            capabilities.add(_NATIVE_RIVAL_QUERY_CAPABILITY)
        if ack.get(_NATIVE_VASSALIZATION_QUERY_CAPABILITY) is True:
            capabilities.add(_NATIVE_VASSALIZATION_QUERY_CAPABILITY)
        if ack.get(_NATIVE_DECLARE_WAR_QUERY_CAPABILITY) is True:
            capabilities.add(_NATIVE_DECLARE_WAR_QUERY_CAPABILITY)
        if ack.get(_NATIVE_PEACE_CONTEXT_QUERY_CAPABILITY) is True:
            capabilities.add(_NATIVE_PEACE_CONTEXT_QUERY_CAPABILITY)
        if ack.get(_NATIVE_PEACE_EMPTY_OFFER_QUERY_CAPABILITY) is True:
            capabilities.add(_NATIVE_PEACE_EMPTY_OFFER_QUERY_CAPABILITY)
        if ack.get(_NATIVE_PEACE_OFFER_EVALUATION_QUERY_CAPABILITY) is True:
            capabilities.add(_NATIVE_PEACE_OFFER_EVALUATION_QUERY_CAPABILITY)
        if ack.get(_NATIVE_PEACE_MONEY_OFFER_QUERY_CAPABILITY) is True:
            capabilities.add(_NATIVE_PEACE_MONEY_OFFER_QUERY_CAPABILITY)
        if ack.get(_NATIVE_PEACE_PROVINCE_OFFER_QUERY_CAPABILITY) is True:
            capabilities.add(_NATIVE_PEACE_PROVINCE_OFFER_QUERY_CAPABILITY)
        if ack.get(_NATIVE_PEACE_COMBINED_QUERY_CAPABILITY) is True:
            capabilities.add(_NATIVE_PEACE_COMBINED_QUERY_CAPABILITY)
        if ack.get(_NATIVE_PEACE_WRAPPER_RULE_QUERY_CAPABILITY) is True:
            capabilities.add(_NATIVE_PEACE_WRAPPER_RULE_QUERY_CAPABILITY)
        return frozenset(capabilities)

    @staticmethod
    def _valid_native_inbound_offer_event(event: object, session_id: str) -> bool:
        """Validate the narrow r21 pending-offer observation contract.

        The native event contains diagnostic addresses, tokens and dates for
        operator evidence.  Those fields are intentionally only checked for
        identity here and are never copied to the public proposal object.
        """

        if not isinstance(event, dict) or event.get("session_id") != session_id:
            return False
        action_id = event.get("action_id", "offer_alliance")
        family = _inbound_family(action_id)
        if (event.get("event") not in {
                    "native_alliance_inbound_offer",
                    "native_alliance_inbound_pending",
                }
                or family is None or event.get("phase") != "initiate"):
            return False
        if family == "royal_marriage":
            if (event.get("family") != "royal_marriage"
                    or isinstance(event.get("extra60"), bool)
                    or not isinstance(event.get("extra60"), int)
                    or event.get("extra60") != 0):
                return False
        elif family == "support_independence":
            # Support Independence has its own pending family discriminator.
            # Its response-rule inspection carries the relation-state fields;
            # the pending offer only needs the family/action binding here.
            if event.get("family") != "support_independence":
                return False
        elif family == "military_access":
            # Military Access has its own pending family discriminator.  The
            # public proposal exposes only the action family and opaque id;
            # native addresses and prediction fields stay private.
            if event.get("family") != "military_access":
                return False
        elif family == "vassalization":
            # Vassalization is a separate relation family.  Its pending
            # proposal must carry the family discriminator; an optional
            # selector value is checked when the native formatter emits it.
            if (event.get("family") != "vassalization"
                    or ("extra60" in event and (
                        isinstance(event.get("extra60"), bool)
                        or not isinstance(event.get("extra60"), int)
                        or event.get("extra60") != 0))):
                return False
        elif family == "peace":
            # Peace is an aggregate inbound proposal.  The pending event may
            # carry only the bounded native payload summary; the complete
            # war/term context is obtained by the fresh response inspection.
            # Never accept a cross-family event or treat the summary as a
            # white-peace term selection.
            if event.get("family") != "peace":
                return False
            summary = event.get("peace")
            if summary is not None:
                if (not isinstance(summary, dict)
                        or type(summary.get("complete")) is not bool
                        or not isinstance(summary.get("term_count"), int)
                        or isinstance(summary.get("term_count"), bool)
                        or summary.get("term_count") < 0
                        or summary.get("term_count") > 512
                        or not isinstance(summary.get("selected_term_count"), int)
                        or isinstance(summary.get("selected_term_count"), bool)
                        or summary.get("selected_term_count") < 0
                        or summary.get("selected_term_count") > summary.get("term_count")):
                    return False
        elif event.get("family") not in (None, "alliance"):
            return False
        elif ("extra60" in event
              and (isinstance(event.get("extra60"), bool)
                   or not isinstance(event.get("extra60"), int)
                   or event.get("extra60") != 0)):
            return False
        if (event.get("business_result") is not None
                and event.get("business_result") != "pending_observed"):
            return False
        proposal_id = event.get("proposal_id")
        if (isinstance(proposal_id, bool) or not isinstance(proposal_id, int)
                or proposal_id <= 0 or proposal_id > 0xFFFFFFFFFFFFFFFF):
            return False
        actor = event.get("actor")
        if (not isinstance(actor, str) or not re.fullmatch(r"[A-Z0-9]{3}", actor)
                or actor == "FRA" or event.get("mirror") != actor):
            return False
        if event.get("recipient") != "FRA" or event.get("decision_country") != "FRA":
            return False
        state34 = event.get("state34")
        variant38 = event.get("variant38")
        if (isinstance(state34, bool) or not isinstance(state34, int) or state34 != 0
                or isinstance(variant38, bool) or not isinstance(variant38, int)
                or variant38 != 1):
            return False
        for field in ("queue_readable", "list_integrity", "new_entry",
                      "payload_readable", "decision_country_verified",
                      "source_verified", "call_redirected"):
            if event.get(field) is not True:
                return False
        return True

    @staticmethod
    def _valid_native_inbound_pending_restored_event(event: object,
                                                      session_id: str) -> bool:
        """Validate a pending offer restored from the native save queue.

        A restored queue item has the same diplomatic payload identity as an
        inbound offer, but it is not a newly created offer.  Keep this
        contract separate from ``_valid_native_inbound_offer_event`` so a
        restored item cannot silently satisfy the old ``new_entry`` or
        ``call_redirected`` proof.
        """

        if not isinstance(event, dict) or event.get("session_id") != session_id:
            return False
        if event.get("event") != "native_diplomacy_inbound_pending_restored":
            return False
        action_id = event.get("action_id")
        if not isinstance(action_id, str):
            return False
        family = _inbound_family(action_id)
        if family is None or event.get("family") != family:
            return False
        if family == "peace" and event.get("peace") is not None:
            summary = event.get("peace")
            if (not isinstance(summary, dict)
                    or type(summary.get("complete")) is not bool
                    or type(summary.get("term_count")) is not int
                    or summary.get("term_count") < 0
                    or summary.get("term_count") > 512
                    or type(summary.get("selected_term_count")) is not int
                    or summary.get("selected_term_count") < 0
                    or summary.get("selected_term_count") > summary.get("term_count")):
                return False
        if event.get("phase") != "initiate":
            return False
        extra60 = event.get("extra60")
        if isinstance(extra60, bool) or not isinstance(extra60, int) or extra60 != 0:
            return False
        pending_source = event.get("pending_source")
        if pending_source != "native_saved_pending_queue":
            return False
        business_result = event.get("business_result")
        if (business_result is not None
                and business_result not in ("pending_restored", "pending_observed")):
            return False
        proposal_id = event.get("proposal_id")
        if (isinstance(proposal_id, bool) or not isinstance(proposal_id, int)
                or proposal_id <= 0 or proposal_id > 0xFFFFFFFFFFFFFFFF):
            return False
        actor = event.get("actor")
        if (not isinstance(actor, str) or not re.fullmatch(r"[A-Z0-9]{3}", actor)
                or actor == "FRA" or event.get("mirror") != actor):
            return False
        if event.get("recipient") != "FRA" or event.get("decision_country") != "FRA":
            return False
        state34 = event.get("state34")
        variant38 = event.get("variant38")
        if (isinstance(state34, bool) or not isinstance(state34, int) or state34 != 0
                or isinstance(variant38, bool) or not isinstance(variant38, int)
                or variant38 != 1):
            return False
        for field in ("queue_readable", "list_integrity", "payload_readable",
                      "decision_country_verified", "source_verified",
                      "saved_queue_restored", "native_queue_membership_verified"):
            if event.get(field) is not True:
                return False
        if event.get("new_entry") is not False or event.get("call_redirected") is not False:
            return False
        return True

    @staticmethod
    def _public_native_inbound_offer(public_id: str, event: dict) -> dict:
        """Reduce a verified native event to the AI-facing safe contract."""

        action_id = event.get("action_id", "offer_alliance")
        family = _inbound_family(action_id)
        public = {
            "proposal_id": public_id,
            "action_id": action_id,
            "family": family,
            "actor": event["actor"],
            "recipient": "FRA",
            "decision_country": "FRA",
            "phase": "initiate",
            "observer_status": "observed_pending",
            "currently_pending": None,
            "legality": {"status": "unknown", "complete": False},
            "legality_status": "unknown",
            "execute": {"accept": "unimplemented", "reject": "unimplemented"},
        }
        if event.get("event") == "native_diplomacy_inbound_pending_restored":
            public["source"] = "saved_native_pending"
        return public

    def read_native_alliance_inbound_offers(self) -> list[dict]:
        """Read at most one bounded log window of verified inbound offers.

        The cursor advances only over complete lines and is reset if the
        control log is replaced.  A native proposal id can therefore produce
        one public opaque id per observer session without rescanning the full
        log or retaining native diagnostics in the public response.
        """

        if _NATIVE_INBOUND_ALLIANCE_CAPABILITY not in self.installation_capabilities():
            return []
        log = self.directory / "control-probe.jsonl"
        try:
            size = log.stat().st_size
            offset = self._inbound_log_offset
            if size < offset:
                offset = 0
                self._inbound_log_offset = 0
                self._inbound_seen_native_proposals.clear()
                self._inbound_private_proposals.clear()
            with log.open("rb") as stream:
                stream.seek(offset)
                pending = b""
                consumed = offset
                scanned = 0
                while scanned < _RESPONSE_LOG_SCAN_BYTES:
                    chunk = stream.read(min(_RESPONSE_LOG_CHUNK_BYTES,
                                            _RESPONSE_LOG_SCAN_BYTES - scanned))
                    if not chunk:
                        break
                    scanned += len(chunk)
                    pending += chunk
                    while True:
                        newline = pending.find(b"\n")
                        if newline < 0:
                            break
                        line = pending[:newline]
                        pending = pending[newline + 1:]
                        consumed += newline + 1
                        if len(line) > _RESPONSE_LOG_LINE_BYTES:
                            continue
                        try:
                            event = json.loads(line.decode("utf-8"))
                        except (UnicodeDecodeError, ValueError):
                            continue
                        restored = self._valid_native_inbound_pending_restored_event(
                            event, self.session_id)
                        if (not restored
                                and not self._valid_native_inbound_offer_event(
                                    event, self.session_id)):
                            continue
                        native_proposal_id = event["proposal_id"]
                        if native_proposal_id in self._inbound_seen_native_proposals:
                            continue
                        try:
                            payload = json.dumps(event, ensure_ascii=False, sort_keys=True,
                                                 separators=(",", ":"), allow_nan=False)
                        except (TypeError, ValueError):
                            continue
                        self._inbound_seen_native_proposals.add(native_proposal_id)
                        opaque = hashlib.sha256(
                            (self.session_id + "\0" + str(native_proposal_id)
                             + "\0" + payload).encode("utf-8")).hexdigest()[:32]
                        public_id = opaque
                        public = self._public_native_inbound_offer(public_id, event)
                        self._inbound_private_proposals[public_id] = {
                            "session_id": self.session_id,
                            "native_proposal_id": native_proposal_id,
                            "payload": dict(event),
                            "public": public,
                        }
                    if len(pending) > _RESPONSE_LOG_LINE_BYTES:
                        consumed += len(pending)
                        pending = b""
                self._inbound_log_offset = consumed
        except OSError:
            return [dict(item["public"])
                    for item in self._inbound_private_proposals.values()]
        return [dict(item["public"])
                for item in self._inbound_private_proposals.values()]

    # Short aliases keep the observer-facing method discoverable to offline
    # bridge callers without creating a second reader or cursor.
    read_native_inbound_offers = read_native_alliance_inbound_offers
    read_native_alliance_inbound = read_native_alliance_inbound_offers

    def find_native_alliance_inbound_offer(self, public_id: object) -> dict | None:
        """Return one safe observed proposal by its opaque public id."""

        if not isinstance(public_id, str):
            return None
        self.read_native_alliance_inbound_offers()
        item = self._inbound_private_proposals.get(public_id)
        if item is None:
            return None
        return dict(item["public"])

    def _native_alliance_inbound_context(self, public_id: object) -> dict | None:
        """Return private wire context for an already observed opaque id.

        This method is intentionally private and is consumed only by the
        bridge's response adapter.  The raw native proposal id never enters
        an AI-facing inspection or result.
        """

        if not isinstance(public_id, str):
            return None
        self.read_native_alliance_inbound_offers()
        item = self._inbound_private_proposals.get(public_id)
        if item is None or item.get("session_id") != self.session_id:
            return None
        payload = item.get("payload")
        if not isinstance(payload, dict):
            return None
        actor = payload.get("actor")
        native_proposal_id = payload.get("proposal_id")
        action_id = payload.get("action_id", "offer_alliance")
        family = _inbound_family(action_id)
        if (not isinstance(actor, str) or not re.fullmatch(r"[A-Z0-9]{3}", actor)
                or actor == "FRA" or isinstance(native_proposal_id, bool)
                or not isinstance(native_proposal_id, int)
                or native_proposal_id <= 0 or native_proposal_id > 0xFFFFFFFFFFFFFFFF
                or family is None
                or payload.get("family", family) != family):
            return None
        return {
            "actor": actor,
            "recipient": "FRA",
            "native_proposal_id": native_proposal_id,
            "session_id": self.session_id,
            "action_id": action_id,
            "family": family,
        }

    @staticmethod
    def _safe_submission_sequence(value: object) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value if 0 <= value <= 0xFFFFFFFF else None

    @staticmethod
    def _safe_submission_flags(value: object) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value if 0 <= value <= 0xFF else None

    @staticmethod
    def _safe_submission_date(value: object) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value if -0x80000000 <= value <= 0x7FFFFFFF else None

    @staticmethod
    def _safe_submission_origin(value: object) -> int | None:
        """Accept only the native uint16 origin enum."""

        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value if 0 <= value <= 0xFFFF else None
        return None

    @staticmethod
    def _transport_receipt_present(event: dict) -> bool:
        """Recognize a positive transport-ring receipt without retaining it."""

        value = event.get("transport_ring")
        if value is True:
            return True
        if not isinstance(value, dict):
            if isinstance(value, str) and value.strip():
                return True
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                return True
            value = event.get("transport_ring_receipt")
            if value is True:
                return True
            if isinstance(value, dict):
                value = value.get("receipt", value.get("verified"))
            return bool(value) if isinstance(value, (str, int)) and not isinstance(value, bool) else False
        for key in ("receipt", "transport_ring_receipt"):
            candidate = value.get(key)
            if candidate is True:
                return True
            if key.endswith("receipt") and isinstance(candidate, str) and candidate.strip():
                return True
            if key.endswith("receipt") and isinstance(candidate, dict) and candidate:
                return True
        return False

    @classmethod
    def _valid_native_submission_result(cls, event: object, request_id: str,
                                        session_id: str, actor: str,
                                        recipient: str, phase: str,
                                        expected_date: object,
                                        action_id: str = "offer_alliance") -> bool:
        """Validate one native result before it can become submission evidence."""

        if not isinstance(event, dict):
            return False
        if event.get("action_id", "offer_alliance") != action_id:
            return False
        for field, expected in (("event", "native_alliance_submission_result"),
                                ("request_id", request_id),
                                ("session_id", session_id),
                                ("actor", actor),
                                ("recipient", recipient),
                                ("phase", phase)):
            if event.get(field) != expected:
                return False
        wanted_date = cls._safe_submission_date(expected_date)
        if wanted_date is None:
            return False
        submitted = event.get("submitted")
        queue_verified = event.get("native_queue_verified")
        if not isinstance(submitted, bool):
            return False
        if not submitted:
            actual_date_raw = event.get("date_raw")
            if (actual_date_raw is not None
                    and (cls._safe_submission_date(actual_date_raw) is None
                         or cls._safe_submission_date(actual_date_raw) != wanted_date)):
                return False
            if queue_verified is not None and not isinstance(queue_verified, bool):
                return False
            return True
        actual_date = cls._safe_submission_date(event.get("date_raw"))
        if actual_date is None or actual_date != wanted_date:
            return False
        if queue_verified is not True or not cls._transport_receipt_present(event):
            return False
        return (cls._safe_submission_sequence(event.get("native_sequence")) is not None
                and cls._safe_submission_origin(event.get("native_origin")) is not None
                and cls._safe_submission_flags(event.get("native_flags")) is not None)

    @classmethod
    def _valid_native_vassalization_submission_result(
            cls, event: object, request_id: str, session_id: str,
            actor: str, recipient: str, phase: str,
            expected_date: object, action_id: str) -> bool:
        """Validate the family-bound transport receipt for Vassalization."""

        if (action_id not in _VASSALIZATION_ACTIONS
                or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z]{3}", recipient) is None
                or recipient == "FRA"
                or not isinstance(event, dict)
                or event.get("family") != "vassalization"):
            return False
        return cls._valid_native_submission_result(
            event, request_id, session_id, actor, recipient, phase,
            expected_date, action_id)

    @classmethod
    def _valid_native_rival_submission_result(cls, event: object, request_id: str,
                                              session_id: str, actor: str,
                                              recipient: str, phase: str,
                                              expected_date: object,
                                              action_id: str) -> bool:
        """Validate the independent Rival transport receipt.

        Rival countrycommands do not use the Alliance receipt fields.  The
        native adapter supplies ``native_sequence``/``native_flags`` as private header
        evidence; only their bounded types are checked here and they are
        removed before the receipt is persisted in the public journal.
        """

        if (not isinstance(event, dict) or action_id not in _RIVAL_ACTIONS
                or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z]{3}", recipient) is None
                or recipient == "FRA"):
            return False
        for field, expected in (
                ("event", "native_rival_submission_result"),
                ("request_id", request_id), ("session_id", session_id),
                ("action_id", action_id), ("family", "rival"),
                ("actor", actor), ("recipient", recipient), ("phase", phase)):
            if event.get(field) != expected:
                return False
        wanted_date = cls._safe_submission_date(expected_date)
        actual_date = cls._safe_submission_date(event.get("date_raw"))
        if wanted_date is None or actual_date is None or actual_date != wanted_date:
            return False
        submitted = event.get("submitted")
        if not isinstance(submitted, bool):
            return False
        for field in ("request_binding_verified", "protocol_verified"):
            if field in event and not isinstance(event.get(field), bool):
                return False
        for field, validator in (
                ("native_origin", cls._safe_submission_origin),
                ("native_flags", cls._safe_submission_flags),
                ("native_sequence", cls._safe_submission_sequence)):
            if field in event and validator(event.get(field)) is None:
                return False
        if submitted:
            if (event.get("request_binding_verified") is not True
                    or event.get("protocol_verified") is not True):
                return False
            if any(field not in event for field in (
                    "native_origin", "native_flags", "native_sequence")):
                return False
            if any(validator(event.get(field)) is None for field, validator in (
                    ("native_origin", cls._safe_submission_origin),
                    ("native_flags", cls._safe_submission_flags),
                    ("native_sequence", cls._safe_submission_sequence))):
                return False
        else:
            reason_code = event.get("reason_code")
            if reason_code is not None and (
                    not isinstance(reason_code, str)
                    or re.fullmatch(r"[A-Z0-9_]{1,96}", reason_code) is None):
                return False
        return True

    @classmethod
    def _public_native_rival_submission_receipt(cls, event: object,
                                                request_id: str, actor: str,
                                                recipient: str, phase: str,
                                                date_raw: object,
                                                action_id: str) -> dict | None:
        """Reduce a Rival receipt without copying native headers."""

        if (not isinstance(event, dict)
                or not cls._valid_native_rival_submission_result(
                    event, request_id, event.get("session_id", ""), actor,
                    recipient, phase, date_raw, action_id)):
            return None
        result = {
            "event": "native_rival_submission_result",
            "request_id": request_id,
            "action_id": action_id,
            "family": "rival",
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": cls._safe_submission_date(date_raw),
            "submitted": event["submitted"],
            "request_binding_verified": event.get("request_binding_verified") is True,
            "protocol_verified": event.get("protocol_verified") is True,
        }
        if event.get("reason_code") is not None:
            result["reason_code"] = event["reason_code"]
        return result

    @classmethod
    def _valid_native_declare_war_submission_result(
            cls, event: object, request_id: str, session_id: str,
            actor: str, recipient: str, phase: str, expected_date: object,
            parameters: object) -> bool:
        """Validate the independent Declare War transport receipt.

        Declare War uses EXEC3 and therefore cannot reuse the Alliance receipt
        contract.  The selected CB, war-goal province and beneficiary remain
        part of the binding all the way through the receipt.
        """

        if (not isinstance(event, dict) or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z]{3}", recipient) is None
                or recipient == "FRA" or event.get("event") !=
                "native_declare_war_submission_result"
                or (event.get("family") is not None
                    and event.get("family") != "declare_war")):
            return False
        for field, expected in (
                ("request_id", request_id), ("session_id", session_id),
                ("action_id", "declare_war"), ("actor", actor),
                ("recipient", recipient), ("phase", phase)):
            if event.get(field) != expected:
                return False
        wanted_date = cls._safe_submission_date(expected_date)
        if (wanted_date is None
                or cls._safe_submission_date(event.get("date_raw")) != wanted_date):
            return False
        try:
            selected = cls._normalize_declare_war_selection(parameters)
        except (TypeError, ValueError):
            selected = None
        if selected is None:
            return False
        if (event.get("casus_belli") != selected["casus_belli"]
                or event.get("war_goal_province") != selected["province_id"]
                or event.get("war_goal_beneficiary") != selected["beneficiary"]):
            return False
        if not isinstance(event.get("submitted"), bool):
            return False
        for field in ("transport_verified", "request_binding_verified"):
            if not isinstance(event.get(field), bool):
                return False
        if event.get("submitted") is True and (
                event.get("transport_verified") is not True
                or event.get("request_binding_verified") is not True):
            return False
        reason_code = event.get("reason_code")
        return (reason_code is None or (
            isinstance(reason_code, str)
            and re.fullmatch(r"[A-Z0-9_]{1,96}", reason_code) is not None))

    @classmethod
    def _public_native_declare_war_submission_receipt(
            cls, event: object, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: object, parameters: object) -> dict | None:
        """Reduce one verified Declare War receipt to safe journal fields."""

        if (not isinstance(event, dict)
                or event.get("submitted") is not True
                or not cls._valid_native_declare_war_submission_result(
                    event, request_id, event.get("session_id", ""), actor,
                    recipient, phase, date_raw, parameters)):
            return None
        selected = cls._normalize_declare_war_selection(parameters)
        return {
            "event": "native_declare_war_submission_result",
            "request_id": request_id,
            "action_id": "declare_war",
            "family": "declare_war",
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": cls._safe_submission_date(date_raw),
            "casus_belli": selected["casus_belli"],
            "war_goal_province": selected["province_id"],
            "war_goal_beneficiary": selected["beneficiary"],
            "submitted": True,
            "transport_verified": True,
            "request_binding_verified": True,
        }

    @staticmethod
    def _peace_execution_fields(parameters: object) -> tuple | None:
        """Return normalized fields used by the independent Peace wire.

        The final three fields are the direction-bound reparations parties and
        the canonical term mask.  Keeping the mask here makes every receipt,
        result and journal re-open path compare the same complete selection,
        rather than inferring a reparations term from the primary action ID.
        """

        if not isinstance(parameters, dict):
            return None
        context = parameters.get("peace_context")
        if not isinstance(context, dict):
            return None
        war_id = context.get("war_id")
        direction = context.get("direction", "demand")
        terms = context.get("terms")
        if (not isinstance(war_id, str)
                or re.fullmatch(_PEACE_WAR_ID_PATTERN, war_id) is None
                or direction not in ("demand", "offer")
                or not isinstance(terms, list)):
            return None
        amount_raw = -1
        province_ids: list[int] = []
        beneficiary: str | None = None
        reparations_payer: str | None = None
        reparations_claimant: str | None = None
        term_actions: set[str] = set()
        for term in terms:
            if not isinstance(term, dict):
                return None
            if term.get("action_id") == "demand_ducats":
                term_actions.add("m")
                amount = term.get("amount")
                if (not isinstance(amount, str)
                        or re.fullmatch(r"[0-9]+\.[0-9]", amount) is None):
                    return None
                whole, tenths = amount.split(".")
                amount_raw = (int(whole) * 10 + int(tenths)) * 100
                if amount_raw <= 0 or amount_raw > 0x7FFFFFFF or amount_raw % 100:
                    return None
            elif term.get("action_id") == "cede_province":
                term_actions.add("p")
                ids = term.get("province_ids")
                beneficiary = term.get("beneficiary")
                if (not isinstance(ids, list)
                        or any(isinstance(value, bool) or not isinstance(value, int)
                               or value <= 0 or value > 0x7FFFFFFF for value in ids)
                        or len(ids) > 16 or len(set(ids)) != len(ids)
                        or not isinstance(beneficiary, str)
                        or re.fullmatch(r"[A-Z0-9]{3}", beneficiary) is None):
                    return None
                province_ids = list(ids)
            elif term.get("action_id") == "war_reparations":
                term_actions.add("r")
                if (not isinstance(term.get("payer"), str)
                        or not isinstance(term.get("claimant"), str)
                        or re.fullmatch(r"[A-Z0-9]{3}", term["payer"]) is None
                        or re.fullmatch(r"[A-Z0-9]{3}", term["claimant"]) is None):
                    return None
                reparations_payer = term["payer"]
                reparations_claimant = term["claimant"]
            else:
                return None
        if not province_ids:
            beneficiary = None
        term_mask = "".join(letter for letter in "mpr" if letter in term_actions)
        return (war_id, direction, amount_raw, province_ids, beneficiary,
                reparations_payer, reparations_claimant, term_mask)

    @classmethod
    def _valid_native_peace_submission_result(
            cls, event: object, request_id: str, session_id: str,
            actor: str, recipient: str, phase: str, expected_date: object,
            action_id: str, parameters: object) -> bool:
        """Validate the independent Peace transport receipt and its payload."""

        if (not isinstance(event, dict) or action_id not in _PEACE_EXECUTION_ACTIONS
                or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z0-9]{3}", recipient) is None
                or recipient == "FRA"
                or event.get("event") != "native_peace_submission_result"
                or event.get("family") != "peace"):
            return False
        expected = cls._peace_execution_fields(parameters)
        if expected is None:
            return False
        for field, value in (
                ("request_id", request_id), ("session_id", session_id),
                ("action_id", action_id), ("actor", actor),
                ("recipient", recipient), ("phase", phase)):
            if event.get(field) != value:
                return False
        wanted_date = cls._safe_submission_date(expected_date)
        actual_date = cls._safe_submission_date(event.get("date_raw"))
        if wanted_date is None or actual_date != wanted_date:
            return False
        (war_id, direction, amount_raw, province_ids, beneficiary,
         reparations_payer, reparations_claimant, term_mask) = expected
        if (event.get("war_id") != war_id
                or event.get("direction") != direction
                or event.get("amount_raw") != amount_raw
                or event.get("province_ids") != province_ids
                or event.get("beneficiary") not in (beneficiary, "-" if beneficiary is None else beneficiary)):
            return False
        if term_mask and event.get("term_mask") != term_mask:
            return False
        if not term_mask and "term_mask" in event:
            return False
        submitted = event.get("submitted")
        if not isinstance(submitted, bool):
            return False
        for field in ("transport_verified", "request_binding_verified"):
            if not isinstance(event.get(field), bool):
                return False
        if submitted and (event.get("transport_verified") is not True
                           or event.get("request_binding_verified") is not True):
            return False
        reason_code = event.get("reason", event.get("reason_code"))
        return reason_code is None or (
            isinstance(reason_code, str)
            and re.fullmatch(r"[A-Z0-9_]{1,96}", reason_code) is not None)

    @classmethod
    def _public_native_peace_submission_receipt(
            cls, event: object, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: object, action_id: str,
            parameters: object) -> dict | None:
        if (not isinstance(event, dict) or event.get("submitted") is not True
                or not cls._valid_native_peace_submission_result(
                    event, request_id, event.get("session_id", ""), actor,
                    recipient, phase, date_raw, action_id, parameters)):
            return None
        fields = cls._peace_execution_fields(parameters)
        if fields is None:
            return None
        (war_id, direction, amount_raw, province_ids, beneficiary,
         reparations_payer, reparations_claimant, term_mask) = fields
        return {
            "event": "native_peace_submission_result",
            "request_id": request_id,
            "action_id": action_id,
            "family": "peace",
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": cls._safe_submission_date(date_raw),
            "war_id": war_id,
            "direction": direction,
            "amount_raw": amount_raw,
            "province_ids": list(province_ids),
            "beneficiary": beneficiary,
            **({"term_mask": term_mask,
                "reparations_payer": reparations_payer,
                "reparations_claimant": reparations_claimant}
               if term_mask else {}),
            "submitted": True,
            "transport_verified": True,
            "request_binding_verified": True,
        }

    @classmethod
    def _valid_native_peace_execution_result(
            cls, event: object, request_id: str, session_id: str,
            actor: str, recipient: str, phase: str, expected_date: object,
            action_id: str, parameters: object) -> bool:
        """Validate one native Peace consequence without asserting term effects."""

        if (not isinstance(event, dict) or action_id not in _PEACE_EXECUTION_ACTIONS
                or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z0-9]{3}", recipient) is None
                or recipient == "FRA"
                or event.get("event") != "native_peace_execution_result"
                or event.get("family") != "peace"):
            return False
        expected = cls._peace_execution_fields(parameters)
        if expected is None:
            return False
        for field, value in (
                ("request_id", request_id), ("session_id", session_id),
                ("action_id", action_id), ("actor", actor),
                ("recipient", recipient), ("phase", phase)):
            if event.get(field) != value:
                return False
        wanted_date = cls._safe_submission_date(expected_date)
        if (wanted_date is None
                or cls._safe_submission_date(event.get("date_raw")) != wanted_date):
            return False
        (war_id, direction, amount_raw, province_ids, beneficiary,
         reparations_payer, reparations_claimant, term_mask) = expected
        if (event.get("war_id") != war_id
                or event.get("direction") != direction
                or event.get("amount_raw") != amount_raw
                or event.get("province_ids") != province_ids
                or event.get("beneficiary") not in (beneficiary, "-" if beneficiary is None else beneficiary)):
            return False
        if term_mask and event.get("term_mask") != term_mask:
            return False
        if not term_mask and "term_mask" in event:
            return False
        outcome = event.get("outcome")
        if outcome not in ("executed", "accepted", "rejected", "unknown", "invalidated"):
            return False
        state = event.get("native_state")
        if isinstance(state, bool) or not isinstance(state, int) or not -0x80000000 <= state <= 0x7FFFFFFF:
            return False
        # The native producer uses state 0 for an immediate Peace execution,
        # state 1 for an NPC refusal, and state 2 for an NPC acceptance.  The
        # transition checks below are necessary but do not bind those three
        # meanings by themselves; enforce the producer's explicit mapping so
        # a contradictory result cannot be persisted as success.
        if ((outcome == "executed" and state != 0)
                or (outcome == "accepted" and state != 2)
                or (outcome == "rejected" and state != 1)):
            return False
        for field in ("response_verified", "request_binding_verified",
                      "execution_verified", "terms_verified", "war_before",
                      "war_after"):
            if not isinstance(event.get(field), bool):
                return False
        if outcome in ("executed", "accepted") and (
                event.get("response_verified") is not True
                or event.get("request_binding_verified") is not True
                or event.get("execution_verified") is not True
                or event.get("war_before") is not True
                or event.get("war_after") is not False):
            return False
        if outcome == "rejected" and (
                event.get("response_verified") is not True
                or event.get("request_binding_verified") is not True
                or event.get("execution_verified") is not False
                or event.get("war_before") is not True
                or event.get("war_after") is not True):
            return False
        effects_present = "effects" in event
        if effects_present and not cls._valid_native_peace_effects(
                event.get("effects"), direction, amount_raw, province_ids,
                beneficiary, actor, recipient, expected_date,
                event.get("terms_verified") is True):
            return False
        if effects_present and outcome in ("rejected", "unknown", "invalidated"):
            effects = event["effects"]
            money = effects.get("money") if isinstance(effects, dict) else None
            provinces = effects.get("provinces", []) if isinstance(effects, dict) else []
            if ((isinstance(money, dict) and money.get("verified") is True)
                    or any(isinstance(row, dict) and row.get("verified") is True
                           for row in provinces)):
                return False
        # A non-white proposal may claim terms_verified only after every
        # selected money/province consequence has a verified effect.  Older
        # events without effects remain compatible while terms_verified is
        # false; they are not promoted to a settled-term result.
        if (event.get("terms_verified") is True
                and action_id != "white_peace"
                and not effects_present):
            return False
        return True

    @classmethod
    def _valid_native_peace_effects(
            cls, effects: object, direction: str, amount_raw: int,
            province_ids: list[int], beneficiary: str | None,
            actor: str, recipient: str, expected_date: object,
            terms_verified: bool) -> bool:
        """Validate bounded, public-safe post-peace consequence evidence."""

        if not isinstance(effects, dict) or set(effects) != {
                "complete", "date_unchanged", "currency_scale", "money",
                "provinces"}:
            return False
        if (not isinstance(effects.get("complete"), bool)
                or not isinstance(effects.get("date_unchanged"), bool)
                or isinstance(effects.get("currency_scale"), bool)
                or effects.get("currency_scale") != 1000
                or not isinstance(effects.get("provinces"), list)
                or len(effects["provinces"]) > 16):
            return False
        verified_province_effect = any(
            isinstance(row, dict) and row.get("verified") is True
            for row in effects["provinces"])
        money = effects.get("money")
        verified_money_effect = (
            isinstance(money, dict) and money.get("verified") is True)
        if ((verified_money_effect or verified_province_effect)
                and (not effects["complete"]
                     or not effects["date_unchanged"])):
            return False
        if terms_verified and (not effects["complete"]
                               or not effects["date_unchanged"]):
            return False
        expected_payer = actor if direction == "offer" else recipient
        if money is None:
            if terms_verified and amount_raw != -1:
                return False
        else:
            if not isinstance(money, dict) or set(money) != {
                    "amount_raw", "payer", "paid_raw", "credits", "verified"}:
                return False
            effect_amount = cls._safe_int(
                money.get("amount_raw"), 1, 2147483647)
            paid_raw = money.get("paid_raw")
            if (amount_raw <= 0 or effect_amount != amount_raw
                    or money.get("payer") != expected_payer
                    or isinstance(paid_raw, bool)
                    or not isinstance(paid_raw, int)
                    or not isinstance(money.get("verified"), bool)
                    or not isinstance(money.get("credits"), list)
                    or len(money["credits"]) > 256):
                return False
            seen_credit_countries: set[str] = set()
            credit_total = 0
            all_credits_verified = True
            for credit in money["credits"]:
                if (not isinstance(credit, dict)
                        or set(credit) != {"country", "amount_raw"}
                        or not isinstance(credit.get("country"), str)
                        or re.fullmatch(r"[A-Z0-9]{3}", credit["country"]) is None
                        or credit["country"] in seen_credit_countries):
                    return False
                credit_amount = cls._safe_int(
                    credit.get("amount_raw"), 1, 2147483647)
                if credit_amount is None:
                    return False
                if credit["country"] == money["payer"]:
                    return False
                seen_credit_countries.add(credit["country"])
                credit_total += credit_amount
            if money["verified"]:
                if paid_raw != amount_raw or credit_total != amount_raw:
                    return False
            else:
                all_credits_verified = False
            if terms_verified and (
                    not money["verified"] or not all_credits_verified
                    or paid_raw != amount_raw or credit_total != amount_raw):
                return False

        seen_provinces: set[int] = set()
        for province in effects["provinces"]:
            if (not isinstance(province, dict)
                    or set(province) != {
                        "province_id", "beneficiary", "owner_before",
                        "owner_after", "controller_before", "controller_after",
                        "verified"}):
                return False
            province_id = cls._safe_int(
                province.get("province_id"), 1, 2147483647)
            if (province_id is None or province_id in seen_provinces
                    or not isinstance(province.get("beneficiary"), str)
                    or re.fullmatch(r"[A-Z0-9]{3}", province["beneficiary"]) is None
                    or any(not isinstance(province.get(field), str)
                           or re.fullmatch(r"[A-Z0-9]{3}", province[field]) is None
                           for field in ("owner_before", "owner_after",
                                         "controller_before", "controller_after"))
                    or not isinstance(province.get("verified"), bool)):
                return False
            if province_id not in province_ids:
                return False
            if province["verified"] and (
                    province["beneficiary"] != beneficiary
                    or province["owner_before"] == province["beneficiary"]
                    or province["owner_after"] != province["beneficiary"]):
                return False
            seen_provinces.add(province_id)
        if terms_verified:
            if set(seen_provinces) != set(province_ids):
                return False
            if any(not row.get("verified") for row in effects["provinces"]):
                return False
        return True

    @staticmethod
    def _public_native_peace_effects(effects: dict) -> dict:
        """Return only the stable consequence fields exposed to the caller."""

        money = effects.get("money")
        public_money = None
        if isinstance(money, dict):
            public_money = {
                "amount_raw": money["amount_raw"],
                "payer": money["payer"],
                "paid_raw": money["paid_raw"],
                "credits": [
                    {"country": row["country"], "amount_raw": row["amount_raw"]}
                    for row in money["credits"]],
                "verified": money["verified"],
            }
        return {
            "complete": effects["complete"],
            "date_unchanged": effects["date_unchanged"],
            "currency_scale": effects["currency_scale"],
            "money": public_money,
            "provinces": [
                {key: row[key] for key in (
                    "province_id", "beneficiary", "owner_before", "owner_after",
                    "controller_before", "controller_after", "verified")}
                for row in effects["provinces"]],
        }

    @classmethod
    def _public_native_peace_execution_result(
            cls, event: object, request_id: str, session_id: str,
            actor: str, recipient: str, phase: str, date_raw: object,
            action_id: str, parameters: object) -> dict | None:
        if not cls._valid_native_peace_execution_result(
                event, request_id, session_id, actor, recipient, phase,
                date_raw, action_id, parameters):
            return None
        fields = cls._peace_execution_fields(parameters)
        if fields is None:
            return None
        (war_id, direction, amount_raw, province_ids, beneficiary,
         reparations_payer, reparations_claimant, term_mask) = fields
        result = {
            "event": "native_peace_execution_result",
            "request_id": request_id,
            "action_id": action_id,
            "family": "peace",
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": cls._safe_submission_date(date_raw),
            "war_id": war_id,
            "direction": direction,
            "amount_raw": amount_raw,
            "province_ids": list(province_ids),
            "beneficiary": beneficiary,
            **({"term_mask": term_mask,
                "reparations_payer": reparations_payer,
                "reparations_claimant": reparations_claimant}
               if term_mask else {}),
            "native_state": event["native_state"],
            "outcome": event["outcome"],
            "response_verified": event["response_verified"],
            "request_binding_verified": event["request_binding_verified"],
            "execution_verified": event["execution_verified"],
            "terms_verified": event["terms_verified"],
            "war_before": event["war_before"],
            "war_after": event["war_after"],
            "native_outcome": event["outcome"],
        }
        if "effects" in event:
            result["effects"] = cls._public_native_peace_effects(event["effects"])
        return result

    @classmethod
    def _public_native_submission_receipt(cls, event: dict, request_id: str,
                                          actor: str, recipient: str,
                                          phase: str, date_raw: int,
                                          action_id: str = "offer_alliance") -> dict:
        """Reduce a native event to safe fields for the public journal result."""

        return {
            "event": "native_alliance_submission_result",
            "request_id": request_id,
            "action_id": action_id,
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": date_raw,
            "submitted": True,
            "native_queue_verified": True,
            "transport_ring": True,
            "transport_ring_receipt": True,
            "native_sequence": cls._safe_submission_sequence(event.get("native_sequence")),
            "native_origin": cls._safe_submission_origin(event.get("native_origin")),
            "native_flags": cls._safe_submission_flags(event.get("native_flags")),
        }

    @classmethod
    def _public_native_vassalization_submission_receipt(
            cls, event: object, request_id: str, actor: str,
            recipient: str, phase: str, date_raw: object,
            action_id: str) -> dict | None:
        """Reduce one verified Vassalization receipt to safe journal fields."""

        if (not isinstance(event, dict)
                or not cls._valid_native_vassalization_submission_result(
                    event, request_id, event.get("session_id", ""), actor,
                    recipient, phase, date_raw, action_id)
                or event.get("submitted") is not True):
            return None
        result = cls._public_native_submission_receipt(
            event, request_id, actor, recipient, phase,
            cls._safe_submission_date(date_raw), action_id)
        result["family"] = "vassalization"
        return result

    @classmethod
    def _public_native_response_result(cls, event: object, request_id: str,
                                       session_id: str, actor: str,
                                       recipient: str, phase: str,
                                       date_raw: object,
                                       action_id: str = "offer_alliance") -> dict | None:
        """Validate and reduce one bound native response to public fields."""

        if not isinstance(event, dict):
            return None
        if action_id not in ("offer_alliance", "offer_royal_marriage"):
            return None
        for field, expected in (
                ("event", "native_alliance_response_result"),
                ("request_id", request_id),
                ("session_id", session_id),
                ("action_id", action_id),
                ("actor", actor),
                ("recipient", recipient),
                ("phase", phase)):
            if event.get(field) != expected:
                return None
        wanted_date = cls._safe_submission_date(date_raw)
        actual_date = cls._safe_submission_date(event.get("date_raw"))
        if wanted_date is None or actual_date is None or actual_date != wanted_date:
            return None
        if (event.get("response_verified") is not True
                or event.get("request_binding_verified") is not True):
            return None
        native_state = event.get("native_state")
        royal = action_id == "offer_royal_marriage"
        if royal:
            if event.get("family") != "royal_marriage":
                return None
            # The observed outbound Royal response wire (r26) carries the
            # post-response relation and the verified binding fields, but its
            # response record omits ``royal_marriage_before``.  An offer is
            # only executable after the native initiation-validity gate has
            # established that no Royal Marriage exists, so the missing
            # before value is the action's false precondition rather than an
            # unknown result.  Keep an explicitly supplied value strict.
            before = event.get("royal_marriage_before", False)
            after = event.get("royal_marriage_after")
            if (isinstance(native_state, bool) or not isinstance(native_state, int)
                    or not isinstance(before, bool) or not isinstance(after, bool)):
                return None
        else:
            before = None
            after = event.get("alliance_after")
            if (isinstance(native_state, bool) or not isinstance(native_state, int)
                    or not isinstance(after, bool)):
                return None
        for field, validator in (
                ("native_sequence", cls._safe_submission_sequence),
                ("native_origin", cls._safe_submission_origin),
                ("native_flags", cls._safe_submission_flags)):
            if field in event and validator(event.get(field)) is None:
                return None
        if native_state == 2 and after is True:
            outcome = "accepted"
        elif native_state == 1 and after is False:
            outcome = "rejected"
        else:
            outcome = "unknown"
        result = {
            "event": "native_alliance_response_result",
            "request_id": request_id,
            "action_id": action_id,
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": wanted_date,
            "response_verified": True,
            "request_binding_verified": True,
            "native_state": native_state,
            "native_outcome": outcome,
        }
        if royal:
            result.update({"family": "royal_marriage",
                           "royal_marriage_before": before,
                           "royal_marriage_after": after})
        else:
            result["alliance_after"] = after
        return result

    @staticmethod
    def _safe_native_proposal_id(value: object) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value if 0 < value <= 0xFFFFFFFFFFFFFFFF else None

    @staticmethod
    def _safe_public_peace_value(value: object, depth: int = 0) -> bool:
        """Accept only bounded semantic JSON values for an inbound treaty.

        Native pointers, handles, tokens and process diagnostics never belong
        in the public term context.  The native reader supplies semantic
        strings/integers/bools; this recursive check keeps an unexpected raw
        field from crossing the public boundary while allowing the 19 term
        schemas to evolve independently.
        """
        if depth > 8:
            return False
        if value is None or isinstance(value, (str, bool)):
            return not isinstance(value, str) or len(value) <= 4096
        if isinstance(value, int) and not isinstance(value, bool):
            return -(1 << 63) <= value <= (1 << 63) - 1
        if isinstance(value, float):
            return value == value and value not in (float("inf"), float("-inf"))
        if isinstance(value, list):
            return len(value) <= 512 and all(
                ObserverSession._safe_public_peace_value(item, depth + 1)
                for item in value)
        if isinstance(value, dict):
            if len(value) > 64:
                return False
            private_markers = ("native", "pointer", "address", "handle", "rva",
                               "thread", "pid", "token", "session_id")
            for key, item in value.items():
                if (not isinstance(key, str) or len(key) > 80
                        or any(marker in key.lower() for marker in private_markers)
                        or not ObserverSession._safe_public_peace_value(item, depth + 1)):
                    return False
            return True
        return False

    @classmethod
    def _valid_public_peace_context(cls, value: object) -> bool:
        if not isinstance(value, dict):
            return False
        allowed = {
            "war_id", "direction", "terms", "complete", "costs",
            "original_actor", "original_recipient", "white_peace",
            "selected_terms_complete", "reason",
        }
        if any(key not in allowed for key in value):
            return False
        war_id = value.get("war_id")
        direction = value.get("direction")
        terms = value.get("terms")
        if (not isinstance(war_id, str)
                or re.fullmatch(_PEACE_WAR_ID_PATTERN, war_id) is None
                or direction not in ("demand", "offer")
                or not isinstance(terms, list) or len(terms) > 512
                or type(value.get("complete")) is not bool):
            return False
        if not all(isinstance(term, dict)
                   and isinstance(term.get("action_id"), str)
                   and term.get("action_id") in PEACE_ACTION_IDS
                   and cls._safe_public_peace_value(term)
                   for term in terms):
            return False
        for key in ("original_actor", "original_recipient"):
            if key in value and (
                    not isinstance(value[key], str)
                    or re.fullmatch(r"[A-Z0-9]{3}", value[key]) is None):
                return False
        if "white_peace" in value and not isinstance(value["white_peace"], bool):
            return False
        if ("selected_terms_complete" in value
                and not isinstance(value["selected_terms_complete"], bool)):
            return False
        if "reason" in value and (
                not isinstance(value["reason"], str)
                or (value["reason"] != "none"
                    and re.fullmatch(r"[A-Z0-9_]{1,96}", value["reason"]) is None)):
            return False
        if "costs" in value and not cls._safe_public_peace_value(value["costs"]):
            return False
        return True

    @classmethod
    def _copy_public_peace_context(cls, value: object) -> dict | None:
        if not cls._valid_public_peace_context(value):
            return None
        try:
            copied = json.loads(json.dumps(value, ensure_ascii=False,
                                           allow_nan=False))
        except (TypeError, ValueError):
            return None
        return copied if isinstance(copied, dict) else None

    @classmethod
    def _valid_native_inbound_inspection(cls, event: object, query_id: str,
                                         session_id: str, actor: str, phase: str,
                                         native_proposal_id: object,
                                         date_raw: object,
                                         action_id: str = "offer_alliance") -> bool:
        """Validate a fresh r22 inbound response-rule inspection."""

        if not isinstance(event, dict):
            return False
        family = _inbound_family(action_id)
        if family is None:
            return False
        for field, expected in (
                ("event", "native_alliance_inbound_inspection"),
                ("query_id", query_id),
                ("session_id", session_id),
                ("action_id", action_id),
                ("actor", actor),
                ("recipient", "FRA"),
                ("phase", phase)):
            if event.get(field) != expected:
                return False
        if (not isinstance(actor, str) or not re.fullmatch(r"[A-Z0-9]{3}", actor)
                or actor == "FRA"):
            return False
        wanted_id = cls._safe_native_proposal_id(native_proposal_id)
        if wanted_id is None or cls._safe_native_proposal_id(event.get("native_proposal_id")) != wanted_id:
            return False
        wanted_date = cls._safe_submission_date(date_raw)
        if wanted_date is None or cls._safe_submission_date(event.get("date_raw")) != wanted_date:
            return False
        if event.get("decision_country") != "FRA":
            return False
        before_field = (
            "royal_marriage_before" if action_id == "offer_royal_marriage"
            else "support_independence_before" if action_id == "support_independence"
            else "military_access_before" if action_id == "ask_military_access"
            else "vassalization_before" if action_id == "offer_vassalization"
            else "alliance_before")
        for field in ("pending_active", "decision_country_verified", "native_validity",
                      "response_rules_complete"):
            if not isinstance(event.get(field), bool):
                return False
        if action_id == "peace_offer":
            if event.get("family") != "peace":
                return False
            for field in ("war_before", "war_active", "war_readable",
                          "native_current_war_readable", "peace_payload_complete",
                          "selected_terms_complete"):
                if not isinstance(event.get(field), bool):
                    return False
            for field in ("term_count", "selected_term_count"):
                value = event.get(field)
                if (isinstance(value, bool) or not isinstance(value, int)
                        or value < 0 or value > 512):
                    return False
            if event.get("selected_term_count") > event.get("term_count"):
                return False
            current_war = event.get("native_current_war")
            if not isinstance(current_war, bool):
                return False
            context = event.get("peace_context")
            if not cls._valid_public_peace_context(context):
                return False
            # The native field is the current-war *state*, not an identity
            # string.  The opaque war identity is carried by the validated
            # public context and must be bound to the observed proposer pair.
            if (context.get("original_actor") != actor
                    or context.get("original_recipient") != "FRA"):
                return False
        elif action_id != "ask_military_access" and not isinstance(event.get(before_field), bool):
            return False
        if action_id == "offer_royal_marriage":
            if (event.get("family") != family
                    or isinstance(event.get("extra60"), bool)
                    or not isinstance(event.get("extra60"), int)
                    or event.get("extra60") != 0):
                return False
        elif action_id == "support_independence":
            if (event.get("family") != family
                    or not isinstance(event.get("native_current_support_independence"), bool)
                    or event.get("native_current_support_independence_readable") is not True
                    or event.get("native_current_support_independence")
                    != event.get("support_independence_before")):
                return False
        elif action_id == "ask_military_access":
            if (event.get("family") != family
                    or not isinstance(event.get("military_access_active"), bool)
                    or not isinstance(event.get("military_access_state_verified"), bool)):
                return False
            # The native adapter emits a complete, typed inactive schema when
            # the queried proposal has already left the pending queue.  Its
            # legality and decision proof fields are deliberately false and
            # the stable reason is PENDING_NOT_ACTIVE.  Accept this schema so
            # the caller can report an unavailable/inactivated proposal with
            # the native reason instead of treating the event as malformed.
            inactive_pending_schema = (
                event.get("reason") == "PENDING_NOT_ACTIVE"
                and event.get("pending_active") is False
                and event.get("decision_country_verified") is False
                and event.get("native_validity") is False
                and event.get("response_rules_complete") is False
                and event.get("military_access_state_verified") is False
            )
            if event.get("pending_active") is False and not inactive_pending_schema:
                return False
            if not inactive_pending_schema and event.get("military_access_state_verified") is not True:
                return False
        elif action_id == "offer_vassalization":
            if (event.get("family") != family
                    or not isinstance(event.get("native_current_vassalization"), bool)
                    or event.get("native_current_vassalization_readable") is not True
                    or event.get("native_current_vassalization")
                    != event.get("vassalization_before")):
                return False
        elif action_id == "peace_offer":
            # The aggregate Peace inspection uses its own war/payload fields;
            # an alliance_before or relation-state field must not satisfy it.
            if event.get("family") != "peace":
                return False
        elif event.get("family") not in (None, family):
            return False
        failure_reason = event.get("reason", "none")
        if (not isinstance(failure_reason, str)
                or (failure_reason != "none"
                    and not re.fullmatch(r"[A-Z0-9_]{1,96}", failure_reason))):
            return False
        return True

    @classmethod
    def _public_native_inbound_inspection(cls, event: dict,
                                          date_raw: int,
                                          action_id: str = "offer_alliance") -> dict:
        """Reduce a native inbound inspection without raw proposal identity."""

        family = _inbound_family(action_id)
        before_field = (
            "royal_marriage_before" if action_id == "offer_royal_marriage"
            else "support_independence_before" if action_id == "support_independence"
            else "military_access_before" if action_id == "ask_military_access"
            else "vassalization_before" if action_id == "offer_vassalization"
            else "alliance_before")
        if action_id == "peace_offer":
            before_value = event["war_before"]
        else:
            before_value = (
                event["military_access_active"]
                if action_id == "ask_military_access" else event[before_field]
            )
        public_before_field = "war_before" if action_id == "peace_offer" else before_field
        result = {
            "event": "native_alliance_inbound_inspection",
            "action_id": action_id,
            "actor": event["actor"],
            "recipient": "FRA",
            "phase": event["phase"],
            "date_raw": date_raw,
            "pending_active": event["pending_active"],
            "decision_country": "FRA",
            "decision_country_verified": event["decision_country_verified"],
            "native_validity": event["native_validity"],
            "response_rules_complete": event["response_rules_complete"],
            "reason": event.get("reason", "none"),
            public_before_field: before_value,
        }
        if family in ("royal_marriage", "support_independence", "military_access", "vassalization"):
            result["family"] = family
        if family == "peace":
            result.update({
                "family": "peace",
                "war_before": event["war_before"],
                "native_current_war": event.get("native_current_war"),
                "native_current_war_readable": event["native_current_war_readable"],
                "war_active": event["war_active"],
                "war_readable": event["war_readable"],
                "peace_payload_complete": event["peace_payload_complete"],
                "selected_terms_complete": event["selected_terms_complete"],
                "term_count": event["term_count"],
                "selected_term_count": event["selected_term_count"],
                "peace_context": cls._copy_public_peace_context(
                    event["peace_context"]),
            })
            if "costs" in event and cls._safe_public_peace_value(event["costs"]):
                result["costs"] = json.loads(json.dumps(
                    event["costs"], ensure_ascii=False, allow_nan=False))
        if family == "support_independence":
            result["native_current_support_independence"] = event[
                "native_current_support_independence"]
            result["native_current_support_independence_readable"] = event[
                "native_current_support_independence_readable"]
        if family == "military_access":
            result["military_access_active"] = event["military_access_active"]
            result["military_access_state_verified"] = event[
                "military_access_state_verified"]
        if family == "vassalization":
            result["native_current_vassalization"] = event[
                "native_current_vassalization"]
            result["native_current_vassalization_readable"] = event[
                "native_current_vassalization_readable"]
        return result

    def inspect_native_inbound_response(self, query_id: str, actor: str,
                                        phase: str, date_raw: object,
                                        native_proposal_id: object,
                                        timeout: float = _EXECUTE_WAIT_SECONDS,
                                        action_id: str = "offer_alliance") -> dict:
        """Freshly query native response rules for one private proposal id."""

        capability = _inbound_response_capability(action_id)
        if capability is None:
            return {"error_code": "NATIVE_INBOUND_QUERY_INVALID"}
        if capability not in self.installation_capabilities():
            return {"error_code": (
                "NATIVE_INBOUND_ROYAL_MARRIAGE_RESPONSE_CAPABILITY_MISSING"
                if action_id == "offer_royal_marriage"
                else "NATIVE_INBOUND_SUPPORT_INDEPENDENCE_RESPONSE_CAPABILITY_MISSING"
                if action_id == "support_independence"
                else "NATIVE_INBOUND_MILITARY_ACCESS_RESPONSE_CAPABILITY_MISSING"
                if action_id == "ask_military_access"
                else "NATIVE_INBOUND_VASSALIZATION_RESPONSE_CAPABILITY_MISSING"
                if action_id == "offer_vassalization"
                else "NATIVE_INBOUND_PEACE_RESPONSE_CAPABILITY_MISSING"
                if action_id == "peace_offer"
                else "NATIVE_INBOUND_RESPONSE_CAPABILITY_MISSING")}
        if (not isinstance(query_id, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", query_id)
                or not isinstance(actor, str)
                or not re.fullmatch(r"[A-Z0-9]{3}", actor)
                or actor == "FRA" or phase not in ("accept", "reject")
                or "|" in self.session_id or "\n" in self.session_id
                or "\r" in self.session_id):
            return {"error_code": "NATIVE_INBOUND_QUERY_INVALID"}
        wanted_date = self._safe_submission_date(date_raw)
        wanted_id = self._safe_native_proposal_id(native_proposal_id)
        if wanted_date is None or wanted_id is None:
            return {"error_code": "NATIVE_INBOUND_QUERY_INVALID"}
        health = self.health()
        fresh_date = self._safe_submission_date(health.get("date_raw")) if isinstance(health, dict) else None
        if health.get("status") != "ready" or fresh_date is None:
            return {"error_code": "QUERY_SESSION_UNREADY"}
        if fresh_date != wanted_date:
            return {"error_code": "QUERY_DATE_CHANGED"}
        log = self.directory / "control-probe.jsonl"
        try:
            offset = log.stat().st_size
        except OSError:
            return {"error_code": "QUERY_LOG_UNAVAILABLE"}
        expiry = int(time.time_ns() // 100 + _FILETIME_EPOCH + 10 * 10_000_000)
        wire = "|".join(("v1", query_id, self.session_id, str(expiry), str(wanted_date),
                          action_id, actor, "FRA", phase, str(wanted_id))) + "\n"
        published = self._publish_atomic_request(wire, query_id, _INBOUND_QUERY_REQUEST_NAME)
        if published == "busy":
            return {"error_code": "QUERY_CHANNEL_BUSY"}
        if published != "published":
            return {"error_code": "QUERY_CHANNEL_WRITE_FAILED"}
        deadline = time.monotonic() + max(0.0, min(float(timeout), _EXECUTE_WAIT_SECONDS))
        while time.monotonic() < deadline:
            try:
                if log.stat().st_size < offset:
                    return {"error_code": "QUERY_LOG_TRUNCATED"}
                with log.open("rb") as stream:
                    stream.seek(offset)
                    chunk = stream.read(_RESPONSE_LOG_CHUNK_BYTES)
            except OSError:
                return {"error_code": "QUERY_LOG_UNAVAILABLE"}
            complete_end = chunk.rfind(b"\n")
            if complete_end >= 0:
                offset += complete_end + 1
                for line in chunk[:complete_end + 1].splitlines():
                    if len(line) > _RESPONSE_LOG_LINE_BYTES:
                        continue
                    try:
                        event = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, ValueError):
                        continue
                    if (not isinstance(event, dict)
                            or event.get("query_id") != query_id
                            or event.get("session_id") != self.session_id):
                        continue
                    if event.get("event") != "native_alliance_inbound_inspection":
                        continue
                    if not self._valid_native_inbound_inspection(
                            event, query_id, self.session_id, actor, phase, wanted_id, wanted_date,
                            action_id):
                        return {"error_code": "QUERY_NATIVE_INBOUND_RESULT_INVALID"}
                    return self._public_native_inbound_inspection(event, wanted_date, action_id)
            time.sleep(0.02)
        return {"error_code": "QUERY_OBSERVATION_TIMEOUT"}

    # Names used by offline adapters and tests; all share the same wire path.
    inspect_native_inbound_offer = inspect_native_inbound_response
    query_native_inbound_response = inspect_native_inbound_response

    def read_native_alliance_response(self, request_id: str, actor: str,
                                      recipient: str, phase: str,
                                      date_raw: object,
                                      action_id: str = "offer_alliance",
                                      insult_id: int | None = None) -> dict | None:
        """Read one bound native response from the installation log incrementally."""

        log = self.directory / "control-probe.jsonl"
        try:
            size = log.stat().st_size
            offset = self._response_log_offsets.get(request_id, 0)
            if size < offset:
                offset = 0
            with log.open("rb") as stream:
                stream.seek(offset)
                pending = b""
                consumed = offset
                scanned = 0
                while scanned < _RESPONSE_LOG_SCAN_BYTES:
                    chunk = stream.read(min(_RESPONSE_LOG_CHUNK_BYTES,
                                            _RESPONSE_LOG_SCAN_BYTES - scanned))
                    if not chunk:
                        break
                    scanned += len(chunk)
                    pending += chunk
                    while True:
                        newline = pending.find(b"\n")
                        if newline < 0:
                            break
                        line = pending[:newline]
                        pending = pending[newline + 1:]
                        consumed += newline + 1
                        if len(line) > _RESPONSE_LOG_LINE_BYTES:
                            continue
                        try:
                            event = json.loads(line.decode("utf-8"))
                        except (UnicodeDecodeError, ValueError):
                            continue
                        expected_event = (
                            "native_diplomacy_relation_execution_result"
                            if action_id in ("proclaim_guarantee", "revoke_guarantee",
                                             "revoke_support_independence",
                                             "cancel_military_access")
                            else "native_diplomacy_relation_response_result"
                            if action_id in ("support_independence", "ask_military_access")
                            else "native_diplomacy_task_execution_result"
                            if action_id in ("improve_relations", "stop_improving_relations",
                                             "build_spy_network", "stop_building_spy_network")
                            else "native_alliance_execution_result"
                            if action_id in ("dissolve_alliance", "break_royal_ties")
                            else "native_diplomacy_insult_execution_result"
                            if action_id in _INSULT_ACTIONS
                            else "native_diplomacy_relation_response_result"
                            if action_id == "offer_vassalization"
                            else "native_diplomacy_relation_execution_result"
                            if action_id == "cancel_vassalization"
                            else "native_alliance_response_result")
                        if (not isinstance(event, dict)
                                or event.get("event") != expected_event):
                            continue
                        if (event.get("request_id") != request_id
                                or event.get("session_id") != self.session_id):
                            continue
                        if action_id == "dissolve_alliance":
                            result = self._public_native_dissolve_result(
                                event, request_id, self.session_id, actor, recipient, phase, date_raw)
                        elif action_id == "break_royal_ties":
                            result = self._public_native_royal_break_result(
                                event, request_id, self.session_id, actor, recipient, phase, date_raw)
                        elif action_id in ("improve_relations", "stop_improving_relations"):
                            result = self._public_native_improve_relations_execution_result(
                                event, request_id, self.session_id, actor, recipient, phase,
                                date_raw, action_id)
                        elif action_id in ("build_spy_network", "stop_building_spy_network"):
                            result = self._public_native_spy_network_execution_result(
                                event, request_id, self.session_id, actor, recipient, phase,
                                date_raw, action_id)
                        elif action_id in ("proclaim_guarantee", "revoke_guarantee"):
                            result = self._public_native_guarantee_execution_result(
                                event, request_id, self.session_id, actor, recipient, phase,
                                date_raw, action_id)
                        elif action_id == "support_independence":
                            result = self._public_native_support_independence_response_result(
                                event, request_id, self.session_id, actor, recipient, phase,
                                date_raw)
                        elif action_id == "revoke_support_independence":
                            result = self._public_native_support_independence_execution_result(
                                event, request_id, self.session_id, actor, recipient, phase,
                                date_raw)
                        elif action_id == "ask_military_access":
                            result = self._public_native_military_access_response_result(
                                event, request_id, self.session_id, actor, recipient, phase,
                                date_raw)
                        elif action_id == "cancel_military_access":
                            result = self._public_native_military_access_execution_result(
                                event, request_id, self.session_id, actor, recipient, phase,
                                date_raw)
                        elif action_id in _INSULT_ACTIONS:
                            result = self._public_native_insult_execution_result(
                                event, request_id, self.session_id, actor, recipient, phase,
                                date_raw, action_id, insult_id)
                        elif action_id == "offer_vassalization":
                            result = self._public_native_vassalization_response_result(
                                event, request_id, self.session_id, actor, recipient, phase,
                                date_raw)
                        elif action_id == "cancel_vassalization":
                            result = self._public_native_vassalization_execution_result(
                                event, request_id, self.session_id, actor, recipient, phase,
                                date_raw)
                        else:
                            result = self._public_native_response_result(
                                event, request_id, self.session_id, actor, recipient, phase, date_raw,
                                action_id)
                        self._response_log_offsets[request_id] = consumed
                        if result is None:
                            return {"status": "invalid", "reason_code": "NATIVE_RESPONSE_RESULT_INVALID"}
                        return {"status": result["native_outcome"], "result": result}
                    if len(pending) > _RESPONSE_LOG_LINE_BYTES:
                        consumed += len(pending)
                        pending = b""
                self._response_log_offsets[request_id] = consumed
        except OSError:
            return None
        return None

    def read_native_insult_execution(self, request_id: str, actor: str,
                                     recipient: str, phase: str, date_raw: object,
                                     action_id: str = "send_insult",
                                     insult_id: int = -1) -> dict | None:
        """Read one bound, family-specific insult execution result."""

        if action_id not in _INSULT_ACTIONS:
            return {"status": "invalid", "reason_code": "NATIVE_RESPONSE_ACTION_INVALID"}
        return self.read_native_alliance_response(
            request_id, actor, recipient, phase, date_raw, action_id, insult_id)

    def read_native_dissolve_result(self, request_id: str, actor: str,
                                   recipient: str, phase: str, date_raw: object) -> dict | None:
        return self.read_native_alliance_response(
            request_id, actor, recipient, phase, date_raw, "dissolve_alliance")

    def read_native_royal_marriage_response(self, request_id: str, actor: str,
                                             recipient: str, phase: str,
                                             date_raw: object) -> dict | None:
        """Read one bound native Royal Marriage offer response."""

        return self.read_native_alliance_response(
            request_id, actor, recipient, phase, date_raw, "offer_royal_marriage")

    def read_native_royal_break_result(self, request_id: str, actor: str,
                                       recipient: str, phase: str,
                                       date_raw: object) -> dict | None:
        """Read one bound native Royal Marriage break consequence."""

        return self.read_native_alliance_response(
            request_id, actor, recipient, phase, date_raw, "break_royal_ties")

    def read_native_improve_relations_execution(
            self, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: object,
            action_id: str = "improve_relations") -> dict | None:
        """Read one bound native ImproveRelations task consequence."""

        if action_id not in ("improve_relations", "stop_improving_relations"):
            return {"status": "invalid", "reason_code": "NATIVE_RESPONSE_ACTION_INVALID"}
        return self.read_native_alliance_response(
            request_id, actor, recipient, phase, date_raw, action_id)

    def read_native_spy_network_execution(
            self, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: object,
            action_id: str = "build_spy_network") -> dict | None:
        """Read one bound native Spy Network task consequence."""

        if action_id not in ("build_spy_network", "stop_building_spy_network"):
            return {"status": "invalid", "reason_code": "NATIVE_RESPONSE_ACTION_INVALID"}
        return self.read_native_alliance_response(
            request_id, actor, recipient, phase, date_raw, action_id)

    def read_native_guarantee_execution(
            self, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: object,
            action_id: str = "proclaim_guarantee") -> dict | None:
        """Read one bound native Guarantee relation consequence."""

        if action_id not in ("proclaim_guarantee", "revoke_guarantee"):
            return {"status": "invalid", "reason_code": "NATIVE_RESPONSE_ACTION_INVALID"}
        return self.read_native_alliance_response(
            request_id, actor, recipient, phase, date_raw, action_id)

    def read_native_support_independence_response(
            self, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: object,
            action_id: str = "support_independence") -> dict | None:
        """Read one bound Support Independence response result."""

        if action_id != "support_independence":
            return {"status": "invalid", "reason_code": "NATIVE_RESPONSE_ACTION_INVALID"}
        return self.read_native_alliance_response(
            request_id, actor, recipient, phase, date_raw, "support_independence")

    def read_native_support_independence_execution(
            self, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: object,
            action_id: str = "revoke_support_independence") -> dict | None:
        """Read one bound Support Independence revoke consequence."""

        if action_id != "revoke_support_independence":
            return {"status": "invalid", "reason_code": "NATIVE_RESPONSE_ACTION_INVALID"}
        return self.read_native_alliance_response(
            request_id, actor, recipient, phase, date_raw,
            "revoke_support_independence")

    def read_native_military_access_response(
            self, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: object,
            action_id: str = "ask_military_access") -> dict | None:
        """Read one bound Military Access request response."""

        if action_id != "ask_military_access":
            return {"status": "invalid", "reason_code": "NATIVE_RESPONSE_ACTION_INVALID"}
        return self.read_native_alliance_response(
            request_id, actor, recipient, phase, date_raw, "ask_military_access")

    def read_native_military_access_execution(
            self, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: object,
            action_id: str = "cancel_military_access") -> dict | None:
        """Read one bound Military Access cancellation consequence."""

        if action_id != "cancel_military_access":
            return {"status": "invalid", "reason_code": "NATIVE_RESPONSE_ACTION_INVALID"}
        return self.read_native_alliance_response(
            request_id, actor, recipient, phase, date_raw, "cancel_military_access")

    def read_native_vassalization_response(
            self, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: object,
            action_id: str = "offer_vassalization") -> dict | None:
        """Read one bound outbound Vassalization offer response."""

        if action_id != "offer_vassalization":
            return {"status": "invalid", "reason_code": "NATIVE_RESPONSE_ACTION_INVALID"}
        return self.read_native_alliance_response(
            request_id, actor, recipient, phase, date_raw, action_id)

    def read_native_vassalization_execution(
            self, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: object,
            action_id: str = "cancel_vassalization") -> dict | None:
        """Read one bound outbound Vassalization cancellation consequence."""

        if action_id != "cancel_vassalization":
            return {"status": "invalid", "reason_code": "NATIVE_RESPONSE_ACTION_INVALID"}
        return self.read_native_alliance_response(
            request_id, actor, recipient, phase, date_raw, action_id)

    def read_native_rival_execution(self, request_id: str, actor: str,
                                    recipient: str, phase: str, date_raw: object,
                                    action_id: str = "set_rival") -> dict | None:
        """Read one strictly bound Rival countrycommand consequence."""

        if action_id not in _RIVAL_ACTIONS:
            return {"status": "invalid", "reason_code": "NATIVE_RIVAL_ACTION_INVALID"}
        log = self.directory / "control-probe.jsonl"
        try:
            size = log.stat().st_size
            offset = self._response_log_offsets.get(request_id, 0)
            if size < offset:
                offset = 0
            with log.open("rb") as stream:
                stream.seek(offset)
                pending = b""
                consumed = offset
                scanned = 0
                while scanned < _RESPONSE_LOG_SCAN_BYTES:
                    chunk = stream.read(min(_RESPONSE_LOG_CHUNK_BYTES,
                                            _RESPONSE_LOG_SCAN_BYTES - scanned))
                    if not chunk:
                        break
                    scanned += len(chunk)
                    pending += chunk
                    while True:
                        newline = pending.find(b"\n")
                        if newline < 0:
                            break
                        line = pending[:newline]
                        pending = pending[newline + 1:]
                        consumed += newline + 1
                        if len(line) > _RESPONSE_LOG_LINE_BYTES:
                            continue
                        try:
                            event = json.loads(line.decode("utf-8"))
                        except (UnicodeDecodeError, ValueError):
                            continue
                        if (not isinstance(event, dict)
                                or event.get("event") != "native_rival_execution_result"
                                or event.get("request_id") != request_id
                                or event.get("session_id") != self.session_id):
                            continue
                        result = self._public_native_rival_execution_result(
                            event, request_id, self.session_id, actor, recipient,
                            phase, date_raw, action_id)
                        self._response_log_offsets[request_id] = consumed
                        if result is None:
                            return {"status": "invalid",
                                    "reason_code": "NATIVE_RIVAL_EXECUTION_RESULT_INVALID"}
                        return {"status": result["status"], "result": result}
                    if len(pending) > _RESPONSE_LOG_LINE_BYTES:
                        consumed += len(pending)
                        pending = b""
                self._response_log_offsets[request_id] = consumed
        except OSError:
            return None
        return None

    def read_native_declare_war_execution(
            self, request_id: str, actor: str, recipient: str, phase: str,
            date_raw: object, parameters: object) -> dict | None:
        """Read one strictly bound Declare War consequence event."""

        try:
            selected = self._normalize_declare_war_selection(parameters)
        except (TypeError, ValueError):
            selected = None
        if (selected is None or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z]{3}", recipient) is None
                or recipient == "FRA"):
            return {"status": "invalid", "reason_code": "NATIVE_DECLARE_WAR_PARAMETERS_INVALID"}
        log = self.directory / "control-probe.jsonl"
        try:
            size = log.stat().st_size
            offset = self._response_log_offsets.get(request_id, 0)
            if size < offset:
                offset = 0
            with log.open("rb") as stream:
                stream.seek(offset)
                pending = b""
                consumed = offset
                scanned = 0
                while scanned < _RESPONSE_LOG_SCAN_BYTES:
                    chunk = stream.read(min(_RESPONSE_LOG_CHUNK_BYTES,
                                            _RESPONSE_LOG_SCAN_BYTES - scanned))
                    if not chunk:
                        break
                    scanned += len(chunk)
                    pending += chunk
                    while True:
                        newline = pending.find(b"\n")
                        if newline < 0:
                            break
                        line = pending[:newline]
                        pending = pending[newline + 1:]
                        consumed += newline + 1
                        if len(line) > _RESPONSE_LOG_LINE_BYTES:
                            continue
                        try:
                            event = json.loads(line.decode("utf-8"))
                        except (UnicodeDecodeError, ValueError):
                            continue
                        if (not isinstance(event, dict)
                                or event.get("event") !=
                                "native_declare_war_execution_result"
                                or event.get("request_id") != request_id
                                or event.get("session_id") != self.session_id):
                            continue
                        result = self._public_native_declare_war_execution_result(
                            event, request_id, self.session_id, actor, recipient,
                            phase, date_raw, selected)
                        self._response_log_offsets[request_id] = consumed
                        if result is None:
                            return {"status": "invalid",
                                    "reason_code":
                                    "NATIVE_DECLARE_WAR_EXECUTION_RESULT_INVALID"}
                        return {"status": result["native_outcome"], "result": result}
                    if len(pending) > _RESPONSE_LOG_LINE_BYTES:
                        consumed += len(pending)
                        pending = b""
                self._response_log_offsets[request_id] = consumed
        except OSError:
            return None
        return None

    def read_native_peace_execution(
            self, request_id: str, actor: str, recipient: str, phase: str,
            date_raw: object, action_id: str, parameters: object) -> dict | None:
        """Read one strictly bound Peace consequence event from the log."""

        try:
            normalized = normalize_peace_execution_parameters(
                action_id, actor, recipient, phase, parameters)
        except (TypeError, ValueError):
            return {"status": "invalid", "reason_code": "NATIVE_PEACE_PARAMETERS_INVALID"}
        if ObserverSession._safe_submission_date(date_raw) is None:
            return {"status": "invalid", "reason_code": "NATIVE_PEACE_DATE_INVALID"}
        log = self.directory / "control-probe.jsonl"
        try:
            size = log.stat().st_size
            offset = self._response_log_offsets.get(request_id, 0)
            if size < offset:
                offset = 0
            with log.open("rb") as stream:
                stream.seek(offset)
                pending = b""
                consumed = offset
                scanned = 0
                while scanned < _RESPONSE_LOG_SCAN_BYTES:
                    chunk = stream.read(min(
                        _RESPONSE_LOG_CHUNK_BYTES,
                        _RESPONSE_LOG_SCAN_BYTES - scanned))
                    if not chunk:
                        break
                    scanned += len(chunk)
                    pending += chunk
                    while True:
                        newline = pending.find(b"\n")
                        if newline < 0:
                            break
                        line = pending[:newline]
                        pending = pending[newline + 1:]
                        consumed += newline + 1
                        if len(line) > _RESPONSE_LOG_LINE_BYTES:
                            continue
                        try:
                            event = json.loads(line.decode("utf-8"))
                        except (UnicodeDecodeError, ValueError):
                            continue
                        if (not isinstance(event, dict)
                                or event.get("event") != "native_peace_execution_result"
                                or event.get("request_id") != request_id
                                or event.get("session_id") != self.session_id):
                            continue
                        result = self._public_native_peace_execution_result(
                            event, request_id, self.session_id, actor, recipient,
                            phase, date_raw, action_id, normalized)
                        self._response_log_offsets[request_id] = consumed
                        if result is None:
                            return {"status": "invalid",
                                    "reason_code": "NATIVE_PEACE_EXECUTION_RESULT_INVALID"}
                        return {"status": result["native_outcome"], "result": result}
                    if len(pending) > _RESPONSE_LOG_LINE_BYTES:
                        consumed += len(pending)
                        pending = b""
                self._response_log_offsets[request_id] = consumed
        except OSError:
            return None
        return None

    @classmethod
    def _public_native_rival_execution_result(
            cls, event: object, request_id: str, session_id: str,
            actor: str, recipient: str, phase: str, date_raw: object,
            action_id: str) -> dict | None:
        """Validate and reduce the independent Rival business event."""

        if (not isinstance(event, dict) or action_id not in _RIVAL_ACTIONS
                or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z]{3}", recipient) is None
                or recipient == "FRA"):
            return None
        for field, expected in (
                ("event", "native_rival_execution_result"),
                ("request_id", request_id), ("session_id", session_id),
                ("action_id", action_id), ("family", "rival"),
                ("actor", actor), ("recipient", recipient), ("phase", phase)):
            if event.get(field) != expected:
                return None
        wanted_date = cls._safe_submission_date(date_raw)
        actual_date = cls._safe_submission_date(event.get("date_raw"))
        if wanted_date is None or actual_date is None or actual_date != wanted_date:
            return None
        status = event.get("status")
        if status not in ("executed", "invalidated", "unknown"):
            return None
        if not isinstance(event.get("executed"), bool):
            return None
        for field in ("request_binding_verified", "native_rule_verified",
                      "relationship_verified"):
            if not isinstance(event.get(field), bool):
                return None
        for field in ("before_active", "after_active"):
            if not isinstance(event.get(field), bool):
                return None
        for field in ("dip_before", "dip_after", "cost_raw",
                      "rival_count_before", "rival_count_after"):
            value = event.get(field)
            if isinstance(value, bool) or not isinstance(value, int):
                return None
        if (event["cost_raw"] < 0 or event["rival_count_before"] < 0
                or event["rival_count_after"] < 0):
            return None
        reason_code = event.get("reason_code")
        if (not isinstance(reason_code, str)
                or re.fullmatch(r"[A-Z0-9_]{1,96}", reason_code) is None):
            return None
        if status == "executed":
            if (event["executed"] is not True
                    or event["request_binding_verified"] is not True
                    or event["native_rule_verified"] is not True
                    or event["relationship_verified"] is not True):
                return None
            if action_id == "set_rival":
                valid_transition = (
                    event["before_active"] is False
                    and event["after_active"] is True
                    and event["rival_count_after"] == event["rival_count_before"] + 1
                    and event["dip_after"] == event["dip_before"]
                    and event["cost_raw"] == 0)
            else:
                valid_transition = (
                    event["before_active"] is True
                    and event["after_active"] is False
                    and event["rival_count_after"] == event["rival_count_before"] - 1
                    and event["dip_before"] - event["dip_after"] == event["cost_raw"])
            if not valid_transition:
                return None
        elif event["executed"] is True:
            return None
        return {
            "event": "native_rival_execution_result",
            "request_id": request_id,
            "action_id": action_id,
            "family": "rival",
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": wanted_date,
            "status": status,
            "executed": event["executed"],
            "request_binding_verified": event["request_binding_verified"],
            "native_rule_verified": event["native_rule_verified"],
            "relationship_verified": event["relationship_verified"],
            "before_active": event["before_active"],
            "after_active": event["after_active"],
            "dip_before": event["dip_before"],
            "dip_after": event["dip_after"],
            "cost_raw": event["cost_raw"],
            "rival_count_before": event["rival_count_before"],
            "rival_count_after": event["rival_count_after"],
            "reason_code": reason_code,
            "native_outcome": status,
        }

    @classmethod
    def _public_native_declare_war_execution_result(
            cls, event: object, request_id: str, session_id: str,
            actor: str, recipient: str, phase: str, date_raw: object,
            parameters: object) -> dict | None:
        """Validate and reduce one Declare War consequence event.

        ``executed`` is granted only by the native transition and both
        binding proofs.  A native ``unknown`` event remains unknown even when
        some diagnostic fields happen to look like a successful transition.
        """

        if (not isinstance(event, dict) or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z]{3}", recipient) is None
                or recipient == "FRA"
                or (event.get("family") is not None
                    and event.get("family") != "declare_war")):
            return None
        for field, expected in (
                ("event", "native_declare_war_execution_result"),
                ("request_id", request_id), ("session_id", session_id),
                ("action_id", "declare_war"),
                ("actor", actor), ("recipient", recipient),
                ("phase", phase)):
            if event.get(field) != expected:
                return None
        wanted_date = cls._safe_submission_date(date_raw)
        if (wanted_date is None
                or cls._safe_submission_date(event.get("date_raw")) != wanted_date):
            return None
        try:
            selected = cls._normalize_declare_war_selection(parameters)
        except (TypeError, ValueError):
            selected = None
        if selected is None or (
                event.get("casus_belli") != selected["casus_belli"]
                or event.get("war_goal_province") != selected["province_id"]
                or event.get("war_goal_beneficiary") != selected["beneficiary"]):
            return None
        outcome = event.get("outcome")
        if outcome not in ("executed", "unknown"):
            return None
        for field in ("execution_verified", "request_binding_verified",
                      "war_before", "war_after"):
            if not isinstance(event.get(field), bool):
                return None
        # The country association table exposes only an opaque native war
        # reference.  The native result therefore makes the integer war ID
        # and the stability observations independently optional.  A verified
        # value must be an int32; an unverified value must be serialized as
        # JSON null.  Never turn an unverified native sentinel into a public
        # ID or cost observation.
        war_identity_verified = event.get("war_identity_verified")
        stability_verified = event.get("stability_verified")
        if (not isinstance(war_identity_verified, bool)
                or not isinstance(stability_verified, bool)):
            return None

        def optional_int32(field: str, verified: bool) -> int | None:
            value = event.get(field)
            if value is None:
                return None
            if (isinstance(value, bool) or not isinstance(value, int)
                    or value < -2147483648 or value > 2147483647
                    or not verified):
                return None
            return value

        war_id = optional_int32("war_id", war_identity_verified)
        stability_before = optional_int32(
            "stability_before_raw", stability_verified)
        stability_after = optional_int32(
            "stability_after_raw", stability_verified)
        if (war_identity_verified and war_id is None
                or stability_verified
                and (stability_before is None or stability_after is None)):
            return None
        if (not war_identity_verified and event.get("war_id") is not None
                or not stability_verified
                and (event.get("stability_before_raw") is not None
                     or event.get("stability_after_raw") is not None)):
            return None
        if outcome == "executed":
            if (event.get("execution_verified") is not True
                    or event.get("request_binding_verified") is not True
                    or event.get("war_before") is not False
                    or event.get("war_after") is not True):
                return None
        return {
            "event": "native_declare_war_execution_result",
            "request_id": request_id,
            "action_id": "declare_war",
            "family": "declare_war",
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": wanted_date,
            "casus_belli": selected["casus_belli"],
            "war_goal_province": selected["province_id"],
            "war_goal_beneficiary": selected["beneficiary"],
            "outcome": outcome,
            "execution_verified": event["execution_verified"],
            "request_binding_verified": event["request_binding_verified"],
            "war_before": event["war_before"],
            "war_after": event["war_after"],
            "war_id": war_id if war_identity_verified else None,
            "war_identity_verified": war_identity_verified,
            "stability_before_raw": stability_before if stability_verified else None,
            "stability_after_raw": stability_after if stability_verified else None,
            "stability_verified": stability_verified,
            "native_outcome": outcome,
        }

    @classmethod
    def _public_native_dissolve_result(cls, event: object, request_id: str,
                                      session_id: str, actor: str, recipient: str,
                                      phase: str, date_raw: object) -> dict | None:
        if not isinstance(event, dict) or actor != "FRA" or phase != "initiate":
            return None
        for key, value in (("event", "native_alliance_execution_result"),
                           ("request_id", request_id), ("session_id", session_id),
                           ("action_id", "dissolve_alliance"), ("actor", actor),
                           ("recipient", recipient), ("phase", phase)):
            if event.get(key) != value:
                return None
        date = cls._safe_submission_date(date_raw)
        if date is None or cls._safe_submission_date(event.get("date_raw")) != date:
            return None
        if (event.get("execution_verified") is not True
                or event.get("request_binding_verified") is not True
                or type(event.get("native_state")) is not int or event["native_state"] != 0
                or type(event.get("native_variant")) is not int or event["native_variant"] != 0
                or not isinstance(event.get("alliance_before"), bool)
                or not isinstance(event.get("alliance_after"), bool)):
            return None
        executed = event["alliance_before"] is True and event["alliance_after"] is False
        return {"event": "native_alliance_execution_result", "request_id": request_id,
                "action_id": "dissolve_alliance", "actor": actor, "recipient": recipient,
                "phase": phase, "date_raw": date, "native_state": 0, "native_variant": 0,
                "execution_verified": True, "request_binding_verified": True,
                "alliance_before": event["alliance_before"], "alliance_after": event["alliance_after"],
                "native_outcome": "executed" if executed else "unknown"}

    @classmethod
    def _public_native_royal_break_result(cls, event: object, request_id: str,
                                          session_id: str, actor: str, recipient: str,
                                          phase: str, date_raw: object) -> dict | None:
        """Validate one native Royal Marriage break consequence."""

        if not isinstance(event, dict) or actor != "FRA" or phase != "initiate":
            return None
        for key, value in (("event", "native_alliance_execution_result"),
                           ("request_id", request_id), ("session_id", session_id),
                           ("action_id", "break_royal_ties"), ("actor", actor),
                           ("recipient", recipient), ("phase", phase)):
            if event.get(key) != value:
                return None
        if event.get("family") not in (None, "royal_marriage"):
            return None
        date = cls._safe_submission_date(date_raw)
        if date is None or cls._safe_submission_date(event.get("date_raw")) != date:
            return None
        if (event.get("execution_verified") is not True
                or event.get("request_binding_verified") is not True
                or type(event.get("native_state")) is not int or event["native_state"] != 0
                or type(event.get("native_variant")) is not int or event["native_variant"] != 0
                or not isinstance(event.get("royal_marriage_before"), bool)
                or not isinstance(event.get("royal_marriage_after"), bool)):
            return None
        for field, validator in (
                ("native_sequence", cls._safe_submission_sequence),
                ("native_origin", cls._safe_submission_origin),
                ("native_flags", cls._safe_submission_flags)):
            if field in event and validator(event.get(field)) is None:
                return None
        before = event["royal_marriage_before"]
        after = event["royal_marriage_after"]
        executed = before is True and after is False
        return {
            "event": "native_alliance_execution_result",
            "request_id": request_id,
            "action_id": "break_royal_ties",
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": date,
            "family": "royal_marriage",
            "native_state": 0,
            "native_variant": 0,
            "execution_verified": True,
            "request_binding_verified": True,
            "royal_marriage_before": before,
            "royal_marriage_after": after,
            "native_outcome": "executed" if executed else "unknown",
        }

    @classmethod
    def _public_native_vassalization_response_result(
            cls, event: object, request_id: str, session_id: str,
            actor: str, recipient: str, phase: str,
            date_raw: object) -> dict | None:
        """Validate one outbound Vassalization offer response."""

        if (not isinstance(event, dict) or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z]{3}", recipient) is None
                or recipient == "FRA"):
            return None
        for key, value in (
                ("event", "native_diplomacy_relation_response_result"),
                ("request_id", request_id), ("session_id", session_id),
                ("action_id", "offer_vassalization"), ("actor", actor),
                ("recipient", recipient), ("phase", phase),
                ("family", "vassalization")):
            if event.get(key) != value:
                return None
        date = cls._safe_submission_date(date_raw)
        if date is None or cls._safe_submission_date(event.get("date_raw")) != date:
            return None
        native_variant = event.get("native_variant")
        native_state = event.get("native_state")
        before = event.get("vassalization_before")
        after = event.get("vassalization_after")
        if (type(native_variant) is not int or native_variant != 1
                or type(native_state) is not int or native_state not in (1, 2)
                or event.get("response_verified") is not True
                or event.get("request_binding_verified") is not True
                or not isinstance(before, bool) or not isinstance(after, bool)
                or ("pending_removed" in event
                    and not isinstance(event.get("pending_removed"), bool))):
            return None
        expected_after = native_state == 2
        if before is not False or after is not expected_after:
            return None
        expected_outcome = "accepted" if native_state == 2 else "rejected"
        if event.get("outcome") not in (expected_outcome, "unknown"):
            return None
        result = {
            "event": "native_diplomacy_relation_response_result",
            "request_id": request_id, "action_id": "offer_vassalization",
            "actor": actor, "recipient": recipient, "phase": phase,
            "date_raw": date, "family": "vassalization",
            "native_variant": native_variant, "native_state": native_state,
            "outcome": event["outcome"],
            "vassalization_before": before,
            "vassalization_after": after,
            "response_verified": True, "request_binding_verified": True,
            "native_outcome": (expected_outcome
                                if event.get("outcome") == expected_outcome
                                else "unknown"),
        }
        if "pending_removed" in event:
            result["pending_removed"] = event["pending_removed"]
        return result

    @classmethod
    def _public_native_vassalization_execution_result(
            cls, event: object, request_id: str, session_id: str,
            actor: str, recipient: str, phase: str,
            date_raw: object) -> dict | None:
        """Validate one outbound Vassalization cancellation consequence."""

        if (not isinstance(event, dict) or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z]{3}", recipient) is None
                or recipient == "FRA"):
            return None
        for key, value in (
                ("event", "native_diplomacy_relation_execution_result"),
                ("request_id", request_id), ("session_id", session_id),
                ("action_id", "cancel_vassalization"), ("actor", actor),
                ("recipient", recipient), ("phase", phase),
                ("family", "vassalization")):
            if event.get(key) != value:
                return None
        date = cls._safe_submission_date(date_raw)
        if date is None or cls._safe_submission_date(event.get("date_raw")) != date:
            return None
        before = event.get("vassalization_before")
        after = event.get("vassalization_after")
        prestige_before = cls._safe_int(
            event.get("prestige_before_raw"), -2147483648, 2147483647)
        prestige_after = cls._safe_int(
            event.get("prestige_after_raw"), -2147483648, 2147483647)
        prestige_scale = cls._safe_int(event.get("prestige_scale"), 1, 1000000)
        if (event.get("outcome") not in ("executed", "unknown")
                or type(event.get("native_variant")) is not int
                or event.get("native_variant") != 0
                or type(event.get("native_state")) is not int
                or event.get("native_state") != 0
                or event.get("execution_verified") is not True
                or event.get("request_binding_verified") is not True
                or not isinstance(before, bool) or not isinstance(after, bool)
                or prestige_before is None or prestige_after is None
                or prestige_scale is None):
            return None
        executed = before is True and after is False and event.get("outcome") == "executed"
        result = {
            "event": "native_diplomacy_relation_execution_result",
            "request_id": request_id, "action_id": "cancel_vassalization",
            "actor": actor, "recipient": recipient, "phase": phase,
            "date_raw": date, "family": "vassalization",
            "native_variant": 0, "native_state": 0,
            "outcome": event["outcome"],
            "vassalization_before": before,
            "vassalization_after": after,
            "prestige_before_raw": prestige_before,
            "prestige_after_raw": prestige_after,
            "prestige_scale": prestige_scale,
            "execution_verified": True, "request_binding_verified": True,
            "native_outcome": "executed" if executed else "unknown",
        }
        raw_cost = max(0, prestige_before - prestige_after)
        exact = raw_cost % prestige_scale == 0
        result["costs"] = {
            "status": "available" if exact else "partial",
            "items": [{
                "resource": "prestige", "amount_raw": raw_cost,
                "amount": raw_cost // prestige_scale if exact else None,
                "unit": "prestige", "unit_verified": exact,
                "scale": prestige_scale, "scale_verified": True,
                "source": "native_execution_consequence", "complete": exact,
            }],
            "complete": False,
            "coverage": {"status": "partial", "known_items": 1,
                          "additional_costs": "unknown", "complete": False,
                          "source": "native_execution_consequence"},
        }
        result["prestige_delta_raw"] = prestige_after - prestige_before
        return result

    @classmethod
    def _public_native_task_execution_result(
            cls, event: object, request_id: str, session_id: str,
            actor: str, recipient: str, phase: str, date_raw: object,
            action_id: str) -> dict | None:
        """Validate one bound single-party diplomatic task consequence.

        The action id selects the family and expected variant.  The family is
        checked explicitly so an ImproveRelations receipt cannot satisfy a
        Spy Network request (or the reverse), even when all transport fields
        happen to match.
        """

        family_by_action = {
            "improve_relations": "improve_relations",
            "stop_improving_relations": "improve_relations",
            "build_spy_network": "spy_network",
            "stop_building_spy_network": "spy_network",
        }
        if (not isinstance(event, dict)
                or action_id not in family_by_action
                or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z]{3}", recipient) is None
                or recipient == "FRA"):
            return None
        family = family_by_action[action_id]
        for key, value in (
                ("event", "native_diplomacy_task_execution_result"),
                ("request_id", request_id), ("session_id", session_id),
                ("action_id", action_id), ("actor", actor),
                ("recipient", recipient), ("phase", phase),
                ("family", family)):
            if event.get(key) != value:
                return None
        date = cls._safe_submission_date(date_raw)
        if date is None or cls._safe_submission_date(event.get("date_raw")) != date:
            return None
        expected_variant = (1 if action_id in ("improve_relations", "build_spy_network") else 0)
        if (event.get("outcome") not in ("executed", "unknown")
                or type(event.get("native_state")) is not int
                or event.get("native_state") != 0
                or type(event.get("native_variant")) is not int
                or event.get("native_variant") != expected_variant
                or event.get("execution_verified") is not True
                or event.get("request_binding_verified") is not True
                or not isinstance(event.get("task_before"), bool)
                or not isinstance(event.get("task_after"), bool)):
            return None
        starts_task = action_id in ("improve_relations", "build_spy_network")
        expected_transition = (
            event["task_before"] is False and event["task_after"] is True
            if starts_task
            else event["task_before"] is True and event["task_after"] is False)
        native_outcome = (
            "executed"
            if event["outcome"] == "executed" and expected_transition
            else "unknown")
        return {
            "event": "native_diplomacy_task_execution_result",
            "request_id": request_id,
            "action_id": action_id,
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": date,
            "family": family,
            "outcome": event["outcome"],
            "native_state": 0,
            "native_variant": event["native_variant"],
            "task_before": event["task_before"],
            "task_after": event["task_after"],
            "execution_verified": True,
            "request_binding_verified": True,
            "native_outcome": native_outcome,
        }

    @classmethod
    def _public_native_improve_relations_execution_result(
            cls, event: object, request_id: str, session_id: str,
            actor: str, recipient: str, phase: str, date_raw: object,
            action_id: str) -> dict | None:
        """Compatibility wrapper for the ImproveRelations contract."""

        if action_id not in ("improve_relations", "stop_improving_relations"):
            return None
        return cls._public_native_task_execution_result(
            event, request_id, session_id, actor, recipient, phase, date_raw, action_id)

    @classmethod
    def _public_native_spy_network_execution_result(
            cls, event: object, request_id: str, session_id: str,
            actor: str, recipient: str, phase: str, date_raw: object,
            action_id: str) -> dict | None:
        """Compatibility wrapper for the Spy Network task contract."""

        if action_id not in ("build_spy_network", "stop_building_spy_network"):
            return None
        return cls._public_native_task_execution_result(
            event, request_id, session_id, actor, recipient, phase, date_raw, action_id)

    @classmethod
    def _public_native_insult_execution_result(
            cls, event: object, request_id: str, session_id: str,
            actor: str, recipient: str, phase: str, date_raw: object,
            action_id: str, expected_insult_id: int | None = None) -> dict | None:
        """Validate one one-sided insult execution consequence."""

        if (not isinstance(event, dict) or action_id not in _INSULT_ACTIONS
                or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z]{3}", recipient) is None
                or recipient == "FRA"):
            return None
        for key, value in (
                ("event", "native_diplomacy_insult_execution_result"),
                ("request_id", request_id), ("session_id", session_id),
                ("action_id", action_id), ("actor", actor),
                ("recipient", recipient), ("phase", phase),
                ("family", "insult")):
            if event.get(key) != value:
                return None
        date = cls._safe_submission_date(date_raw)
        if date is None or cls._safe_submission_date(event.get("date_raw")) != date:
            return None
        insult_id = cls._safe_int(event.get("insult_id"), -2147483648, 2147483647)
        if insult_id is None:
            return None
        if expected_insult_id is not None and insult_id != expected_insult_id:
            return None
        if action_id == "send_insult" and cls._safe_int(insult_id, -1, -1) is None:
            return None
        if action_id == "scornful_insult" and insult_id < 0:
            return None
        if (event.get("outcome") not in ("executed", "unknown")
                or type(event.get("native_state")) is not int
                or event.get("native_state") != 0
                or type(event.get("native_variant")) is not int
                or event.get("native_variant") != 1
                or event.get("execution_verified") is not True
                or event.get("request_binding_verified") is not True
                or not isinstance(event.get("insult_before"), bool)
                or not isinstance(event.get("insult_after"), bool)):
            return None
        for field in ("opinion_modifier_before_raw", "opinion_modifier_after_raw",
                      "prestige_before_raw", "prestige_after_raw"):
            value = event.get(field)
            if cls._safe_int(value, -2147483648, 2147483647) is None:
                return None
        before = event["insult_before"]
        after = event["insult_after"]
        executed = before is False and after is True and event.get("outcome") == "executed"
        return {
            "event": "native_diplomacy_insult_execution_result",
            "request_id": request_id,
            "action_id": action_id,
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": date,
            "family": "insult",
            "insult_id": insult_id,
            "outcome": event["outcome"],
            "native_state": 0,
            "native_variant": 1,
            "insult_before": before,
            "insult_after": after,
            "opinion_modifier_before_raw": event.get("opinion_modifier_before_raw"),
            "opinion_modifier_after_raw": event.get("opinion_modifier_after_raw"),
            "prestige_before_raw": event.get("prestige_before_raw"),
            "prestige_after_raw": event.get("prestige_after_raw"),
            "execution_verified": True,
            "request_binding_verified": True,
            "native_outcome": "executed" if executed else "unknown",
        }

    @classmethod
    def _public_native_guarantee_execution_result(
            cls, event: object, request_id: str, session_id: str,
            actor: str, recipient: str, phase: str, date_raw: object,
            action_id: str) -> dict | None:
        """Validate one bound native Guarantee relation consequence."""

        if (not isinstance(event, dict)
                or action_id not in ("proclaim_guarantee", "revoke_guarantee")
                or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z]{3}", recipient) is None
                or recipient == "FRA"):
            return None
        for key, value in (
                ("event", "native_diplomacy_relation_execution_result"),
                ("request_id", request_id), ("session_id", session_id),
                ("action_id", action_id), ("actor", actor),
                ("recipient", recipient), ("phase", phase),
                ("family", "guarantee")):
            if event.get(key) != value:
                return None
        date = cls._safe_submission_date(date_raw)
        if date is None or cls._safe_submission_date(event.get("date_raw")) != date:
            return None
        expected_variant = 1 if action_id == "proclaim_guarantee" else 0
        if (event.get("outcome") not in ("executed", "unknown")
                or type(event.get("native_state")) is not int
                or event.get("native_state") != 0
                or type(event.get("native_variant")) is not int
                or event.get("native_variant") != expected_variant
                or event.get("execution_verified") is not True
                or event.get("request_binding_verified") is not True
                or not isinstance(event.get("guarantee_before"), bool)
                or not isinstance(event.get("guarantee_after"), bool)):
            return None
        expected_transition = (
            event["guarantee_before"] is False and event["guarantee_after"] is True
            if action_id == "proclaim_guarantee"
            else event["guarantee_before"] is True and event["guarantee_after"] is False)
        native_outcome = (
            "executed"
            if event["outcome"] == "executed" and expected_transition
            else "unknown")
        return {
            "event": "native_diplomacy_relation_execution_result",
            "request_id": request_id,
            "action_id": action_id,
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": date,
            "family": "guarantee",
            "outcome": event["outcome"],
            "native_state": 0,
            "native_variant": expected_variant,
            "execution_verified": True,
            "request_binding_verified": True,
            "guarantee_before": event["guarantee_before"],
            "guarantee_after": event["guarantee_after"],
            "native_outcome": native_outcome,
        }

    @classmethod
    def _public_native_support_independence_response_result(
            cls, event: object, request_id: str, session_id: str,
            actor: str, recipient: str, phase: str,
            date_raw: object) -> dict | None:
        """Validate one bound Support Independence offer response."""

        if (not isinstance(event, dict) or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z]{3}", recipient) is None
                or recipient == "FRA"):
            return None
        for key, value in (
                ("event", "native_diplomacy_relation_response_result"),
                ("request_id", request_id), ("session_id", session_id),
                ("action_id", "support_independence"), ("actor", actor),
                ("recipient", recipient), ("phase", phase),
                ("family", "support_independence")):
            if event.get(key) != value:
                return None
        date = cls._safe_submission_date(date_raw)
        if date is None or cls._safe_submission_date(event.get("date_raw")) != date:
            return None
        native_variant = event.get("native_variant")
        native_state = event.get("native_state")
        if (type(native_variant) is not int or native_variant != 1
                or type(native_state) is not int or native_state not in (1, 2)
                or event.get("response_verified") is not True
                or event.get("request_binding_verified") is not True
                or not isinstance(event.get("support_independence_before"), bool)
                or not isinstance(event.get("support_independence_after"), bool)
                or ("pending_removed" in event
                    and not isinstance(event.get("pending_removed"), bool))):
            return None
        before = event["support_independence_before"]
        after = event["support_independence_after"]
        expected_after = native_state == 2
        if before is not False or after is not expected_after:
            return None
        expected_outcome = "accepted" if native_state == 2 else "rejected"
        if event.get("outcome") not in (expected_outcome, "unknown"):
            return None
        native_outcome = expected_outcome if event.get("outcome") == expected_outcome else "unknown"
        result = {
            "event": "native_diplomacy_relation_response_result",
            "request_id": request_id,
            "action_id": "support_independence",
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": date,
            "family": "support_independence",
            "native_variant": native_variant,
            "native_state": native_state,
            "outcome": event["outcome"],
            "support_independence_before": before,
            "support_independence_after": after,
            "response_verified": True,
            "request_binding_verified": True,
            "native_outcome": native_outcome,
        }
        if "pending_removed" in event:
            result["pending_removed"] = event["pending_removed"]
        return result

    @classmethod
    def _public_native_support_independence_execution_result(
            cls, event: object, request_id: str, session_id: str,
            actor: str, recipient: str, phase: str,
            date_raw: object) -> dict | None:
        """Validate one bound Support Independence revoke consequence."""

        if (not isinstance(event, dict) or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z]{3}", recipient) is None
                or recipient == "FRA"):
            return None
        for key, value in (
                ("event", "native_diplomacy_relation_execution_result"),
                ("request_id", request_id), ("session_id", session_id),
                ("action_id", "revoke_support_independence"), ("actor", actor),
                ("recipient", recipient), ("phase", phase),
                ("family", "support_independence")):
            if event.get(key) != value:
                return None
        date = cls._safe_submission_date(date_raw)
        if date is None or cls._safe_submission_date(event.get("date_raw")) != date:
            return None
        native_variant = event.get("native_variant")
        if (type(native_variant) is not int or native_variant != 0
                or type(event.get("native_state")) is not int
                or event.get("native_state") != 0
                or event.get("execution_verified") is not True
                or event.get("request_binding_verified") is not True
                or not isinstance(event.get("support_independence_before"), bool)
                or not isinstance(event.get("support_independence_after"), bool)):
            return None
        before = event["support_independence_before"]
        after = event["support_independence_after"]
        if event.get("outcome") not in ("executed", "unknown"):
            return None
        executed = before is True and after is False and event.get("outcome") == "executed"
        return {
            "event": "native_diplomacy_relation_execution_result",
            "request_id": request_id,
            "action_id": "revoke_support_independence",
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": date,
            "family": "support_independence",
            "native_variant": native_variant,
            "native_state": 0,
            "outcome": event["outcome"],
            "support_independence_before": before,
            "support_independence_after": after,
            "execution_verified": True,
            "request_binding_verified": True,
            "native_outcome": "executed" if executed else "unknown",
        }

    @classmethod
    def _public_native_military_access_response_result(
            cls, event: object, request_id: str, session_id: str,
            actor: str, recipient: str, phase: str,
            date_raw: object) -> dict | None:
        """Validate one bound outbound Military Access response."""

        if (not isinstance(event, dict) or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z]{3}", recipient) is None
                or recipient == "FRA"):
            return None
        for key, value in (
                ("event", "native_diplomacy_relation_response_result"),
                ("request_id", request_id), ("session_id", session_id),
                ("action_id", "ask_military_access"), ("actor", actor),
                ("recipient", recipient), ("phase", phase),
                ("family", "military_access")):
            if event.get(key) != value:
                return None
        date = cls._safe_submission_date(date_raw)
        if date is None or cls._safe_submission_date(event.get("date_raw")) != date:
            return None
        native_variant = event.get("native_variant")
        native_state = event.get("native_state")
        if (type(native_variant) is not int or native_variant != 1
                or type(native_state) is not int or native_state not in (1, 2)
                or event.get("response_verified") is not True
                or event.get("request_binding_verified") is not True
                or not isinstance(event.get("military_access_before"), bool)
                or not isinstance(event.get("military_access_after"), bool)
                or ("pending_removed" in event
                    and not isinstance(event.get("pending_removed"), bool))):
            return None
        before = event["military_access_before"]
        after = event["military_access_after"]
        expected_after = native_state == 2
        if before is not False or after is not expected_after:
            return None
        expected_outcome = "accepted" if native_state == 2 else "rejected"
        if event.get("outcome") not in (expected_outcome, "unknown"):
            return None
        result = {
            "event": "native_diplomacy_relation_response_result",
            "request_id": request_id,
            "action_id": "ask_military_access",
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": date,
            "family": "military_access",
            "native_variant": native_variant,
            "native_state": native_state,
            "outcome": event["outcome"],
            "military_access_before": before,
            "military_access_after": after,
            "response_verified": True,
            "request_binding_verified": True,
            "native_outcome": (expected_outcome
                                if event.get("outcome") == expected_outcome
                                else "unknown"),
        }
        if "pending_removed" in event:
            result["pending_removed"] = event["pending_removed"]
        return result

    @classmethod
    def _public_native_military_access_execution_result(
            cls, event: object, request_id: str, session_id: str,
            actor: str, recipient: str, phase: str,
            date_raw: object) -> dict | None:
        """Validate one bound Military Access cancellation consequence."""

        if (not isinstance(event, dict) or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z]{3}", recipient) is None
                or recipient == "FRA"):
            return None
        for key, value in (
                ("event", "native_diplomacy_relation_execution_result"),
                ("request_id", request_id), ("session_id", session_id),
                ("action_id", "cancel_military_access"), ("actor", actor),
                ("recipient", recipient), ("phase", phase),
                ("family", "military_access")):
            if event.get(key) != value:
                return None
        date = cls._safe_submission_date(date_raw)
        if date is None or cls._safe_submission_date(event.get("date_raw")) != date:
            return None
        native_variant = event.get("native_variant")
        if (type(native_variant) is not int or native_variant != 0
                or isinstance(event.get("native_state"), bool)
                or event.get("native_state") != 0
                or event.get("execution_verified") is not True
                or event.get("request_binding_verified") is not True
                or not isinstance(event.get("military_access_before"), bool)
                or not isinstance(event.get("military_access_after"), bool)):
            return None
        before = event["military_access_before"]
        after = event["military_access_after"]
        if event.get("outcome") not in ("executed", "unknown"):
            return None
        executed = before is True and after is False and event.get("outcome") == "executed"
        return {
            "event": "native_diplomacy_relation_execution_result",
            "request_id": request_id,
            "action_id": "cancel_military_access",
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": date,
            "family": "military_access",
            "native_variant": native_variant,
            "native_state": 0,
            "outcome": event["outcome"],
            "military_access_before": before,
            "military_access_after": after,
            "execution_verified": True,
            "request_binding_verified": True,
            "native_outcome": "executed" if executed else "unknown",
        }

    def _publish_atomic_request(self, wire: str, request_id: str,
                                request_name: str) -> str:
        """Atomically publish one ASCII request on an exclusive channel."""

        request = self.directory / request_name
        pending = self.directory / f"{request_id}.{uuid.uuid4().hex}.pending"
        pending_owned = False
        try:
            with pending.open("x", encoding="ascii", newline="\n") as stream:
                pending_owned = True
                stream.write(wire)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(pending, request)
            return "published"
        except FileExistsError:
            return "busy"
        except (OSError, UnicodeEncodeError):
            return "failed"
        finally:
            if pending_owned and pending.exists():
                try:
                    pending.unlink()
                except OSError:
                    pass

    def _publish_execute_request(self, wire: str, request_id: str) -> str:
        """Atomically publish one request on the exclusive execute channel."""

        return self._publish_atomic_request(wire, request_id, _EXECUTE_REQUEST_NAME)

    def submit_offer_alliance(self, request_id: str, actor: str, recipient: str,
                              phase: str, date_raw: int,
                              timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        return self._submit_alliance_action("offer_alliance", request_id, actor,
                                            recipient, phase, date_raw, timeout)

    def submit_dissolve_alliance(self, request_id: str, actor: str, recipient: str,
                                 phase: str, date_raw: int,
                                 timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        return self._submit_alliance_action("dissolve_alliance", request_id, actor,
                                            recipient, phase, date_raw, timeout)

    def submit_offer_royal_marriage(self, request_id: str, actor: str,
                                    recipient: str, phase: str, date_raw: int,
                                    timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        """Publish one native Royal Marriage offer and await its receipt."""

        return self._submit_alliance_action("offer_royal_marriage", request_id, actor,
                                            recipient, phase, date_raw, timeout)

    def submit_break_royal_ties(self, request_id: str, actor: str,
                                 recipient: str, phase: str, date_raw: int,
                                 timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        """Publish one native Royal Marriage break and await its receipt."""

        return self._submit_alliance_action("break_royal_ties", request_id, actor,
                                            recipient, phase, date_raw, timeout)

    def submit_improve_relations(self, request_id: str, actor: str,
                                 recipient: str, phase: str, date_raw: int,
                                 timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        """Publish one native ImproveRelations task start and await its receipt."""

        return self._submit_alliance_action("improve_relations", request_id, actor,
                                            recipient, phase, date_raw, timeout)

    def submit_stop_improving_relations(self, request_id: str, actor: str,
                                        recipient: str, phase: str, date_raw: int,
                                        timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        """Publish one native ImproveRelations task stop and await its receipt."""

        return self._submit_alliance_action("stop_improving_relations", request_id, actor,
                                            recipient, phase, date_raw, timeout)

    def submit_build_spy_network(self, request_id: str, actor: str,
                                 recipient: str, phase: str, date_raw: int,
                                 timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        """Publish one native Spy Network task start and await its receipt."""

        return self._submit_alliance_action("build_spy_network", request_id, actor,
                                            recipient, phase, date_raw, timeout)

    def submit_stop_building_spy_network(self, request_id: str, actor: str,
                                         recipient: str, phase: str, date_raw: int,
                                         timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        """Publish one native Spy Network task stop and await its receipt."""

        return self._submit_alliance_action("stop_building_spy_network", request_id, actor,
                                            recipient, phase, date_raw, timeout)

    def submit_proclaim_guarantee(self, request_id: str, actor: str,
                                  recipient: str, phase: str, date_raw: int,
                                  timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        """Publish one native Guarantee start and await its transport receipt."""

        return self._submit_alliance_action("proclaim_guarantee", request_id, actor,
                                            recipient, phase, date_raw, timeout)

    def submit_revoke_guarantee(self, request_id: str, actor: str,
                                recipient: str, phase: str, date_raw: int,
                                timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        """Publish one native Guarantee revoke and await its transport receipt."""

        return self._submit_alliance_action("revoke_guarantee", request_id, actor,
                                            recipient, phase, date_raw, timeout)

    def submit_support_independence(self, request_id: str, actor: str,
                                    recipient: str, phase: str, date_raw: int,
                                    timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        """Publish one native Support Independence proposal."""

        return self._submit_alliance_action("support_independence", request_id, actor,
                                            recipient, phase, date_raw, timeout)

    def submit_revoke_support_independence(self, request_id: str, actor: str,
                                           recipient: str, phase: str, date_raw: int,
                                           timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        """Publish one native Support Independence revoke."""

        return self._submit_alliance_action("revoke_support_independence", request_id, actor,
                                            recipient, phase, date_raw, timeout)

    def submit_ask_military_access(self, request_id: str, actor: str,
                                   recipient: str, phase: str, date_raw: int,
                                   timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        """Publish one native Military Access request."""

        return self._submit_alliance_action("ask_military_access", request_id, actor,
                                            recipient, phase, date_raw, timeout)

    def submit_cancel_military_access(self, request_id: str, actor: str,
                                      recipient: str, phase: str, date_raw: int,
                                      timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        """Publish one native Military Access cancellation."""

        return self._submit_alliance_action("cancel_military_access", request_id, actor,
                                            recipient, phase, date_raw, timeout)

    def submit_offer_vassalization(self, request_id: str, actor: str,
                                   recipient: str, phase: str, date_raw: int,
                                   timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        """Publish one native Vassalization offer when its ACK is present."""

        return self._submit_alliance_action("offer_vassalization", request_id, actor,
                                            recipient, phase, date_raw, timeout)

    def submit_cancel_vassalization(self, request_id: str, actor: str,
                                    recipient: str, phase: str, date_raw: int,
                                    timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        """Publish one native Vassalization cancellation when authorized."""

        return self._submit_alliance_action("cancel_vassalization", request_id, actor,
                                            recipient, phase, date_raw, timeout)

    def submit_send_insult(self, request_id: str, actor: str,
                           recipient: str, phase: str, date_raw: int,
                           timeout: float = _EXECUTE_WAIT_SECONDS,
                           insult_id: int = -1) -> dict:
        """Publish an ordinary insult (the native selector is ``-1``)."""

        return self._submit_alliance_action(
            "send_insult", request_id, actor, recipient, phase, date_raw,
            timeout, insult_id=insult_id)

    def submit_scornful_insult(self, request_id: str, actor: str,
                               recipient: str, phase: str, date_raw: int,
                               insult_id: int,
                               timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        """Publish a selected scornful insult candidate."""

        return self._submit_alliance_action(
            "scornful_insult", request_id, actor, recipient, phase, date_raw,
            timeout, insult_id=insult_id)

    def submit_set_rival(self, request_id: str, actor: str, recipient: str,
                         phase: str, date_raw: int,
                         timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        """Publish one native ``set_rival`` countrycommand request."""

        return self._submit_native_rival(
            "set_rival", request_id, actor, recipient, phase, date_raw, timeout)

    def submit_remove_rival(self, request_id: str, actor: str, recipient: str,
                            phase: str, date_raw: int,
                            timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        """Publish one native ``remove_rival`` countrycommand request."""

        return self._submit_native_rival(
            "remove_rival", request_id, actor, recipient, phase, date_raw, timeout)

    def submit_declare_war(self, request_id: str, actor: str, recipient: str,
                           phase: str, date_raw: int, parameters: object,
                           timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        """Publish one parameter-bound EXEC3 Declare War request."""

        return self._submit_native_declare_war(
            request_id, actor, recipient, phase, date_raw, parameters, timeout)

    def submit_peace(self, request_id: str, actor: str, recipient: str,
                     phase: str, date_raw: int, action_id: str,
                     parameters: object,
                     timeout: float = _EXECUTE_WAIT_SECONDS) -> dict:
        """Publish one independently framed Peace execution request.

        The native submission ACK is a separate capability.  This method only
        reports a verified transport hand-off; the journal consumes the later
        ``native_peace_execution_result`` before exposing a business outcome.
        """
        if (actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z0-9]{3}", recipient) is None
                or recipient == "FRA"):
            return {"status": "unavailable",
                    "reason_code": "NATIVE_PEACE_SUBMISSION_SCOPE_UNSUPPORTED"}
        try:
            normalized = normalize_peace_execution_parameters(
                action_id, actor, recipient, phase, parameters)
        except (TypeError, ValueError):
            return {"status": "failed", "reason_code": "NATIVE_PEACE_PARAMETERS_INVALID"}
        fields = self._peace_execution_fields(normalized)
        wanted_date = self._safe_submission_date(date_raw)
        creation_epoch = self.record.get("creation_filetime")
        if (fields is None or wanted_date is None
                or isinstance(creation_epoch, bool)
                or not isinstance(creation_epoch, int) or creation_epoch < 0
                or not isinstance(request_id, str)
                or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id) is None):
            return {"status": "failed", "reason_code": "NATIVE_PEACE_WIRE_INVALID"}
        (war_id, direction, amount_raw, province_ids, beneficiary,
         reparations_payer, reparations_claimant, term_mask) = fields
        capabilities = self.installation_capabilities()
        if term_mask:
            if _NATIVE_PEACE_REPARATIONS_QUERY_CAPABILITY not in capabilities:
                return {"status": "unavailable",
                        "reason_code": "NATIVE_PEACE_REPARATIONS_QUERY_CAPABILITY_MISSING"}
            if _NATIVE_PEACE_REPARATIONS_EXECUTION_CAPABILITY not in capabilities:
                return {"status": "unavailable",
                        "reason_code": "NATIVE_PEACE_REPARATIONS_EXECUTION_CAPABILITY_MISSING"}
            wire_prefix = "EU4PEACE_EXEC2"
        else:
            if _NATIVE_PEACE_SUBMISSION_CAPABILITY not in capabilities:
                return {"status": "unavailable",
                        "reason_code": "NATIVE_PEACE_SUBMISSION_CAPABILITY_MISSING"}
            wire_prefix = "EU4PEACE_EXEC1"
        expiry_epoch_ms = int(time.time_ns() // 1_000_000) + int(
            max(0.0, min(float(timeout), _EXECUTE_WAIT_SECONDS)) * 1000)
        province_field = ",".join(str(value) for value in province_ids) or "-"
        beneficiary_field = beneficiary or "-"
        wire = " ".join((
            wire_prefix, str(creation_epoch), request_id, action_id,
            actor, recipient, str(wanted_date), str(expiry_epoch_ms), war_id,
            direction, str(amount_raw), province_field, beneficiary_field,
            *( (term_mask,) if term_mask else ()))) + "\n"
        try:
            if len(wire.encode("ascii")) > 512:
                return {"status": "failed", "reason_code": "NATIVE_PEACE_WIRE_TOO_LARGE"}
        except UnicodeEncodeError:
            return {"status": "failed", "reason_code": "NATIVE_PEACE_WIRE_INVALID"}
        log = self.directory / "control-probe.jsonl"
        try:
            offset = log.stat().st_size
        except OSError:
            return {"status": "failed",
                    "reason_code": "NATIVE_PEACE_SUBMISSION_LOG_UNAVAILABLE"}
        published = self._publish_atomic_request(
            wire, request_id, _PEACE_EXECUTE_REQUEST_NAME)
        if published == "busy":
            return {"status": "busy", "reason_code": "EXECUTE_CHANNEL_BUSY"}
        if published != "published":
            return {"status": "failed", "reason_code": "NATIVE_PEACE_WRITE_FAILED"}
        deadline = time.monotonic() + max(0.0, min(float(timeout), _EXECUTE_WAIT_SECONDS))
        while time.monotonic() < deadline:
            try:
                if log.stat().st_size < offset:
                    return {"status": "failed",
                            "reason_code": "NATIVE_PEACE_LOG_TRUNCATED"}
                with log.open("rb") as stream:
                    stream.seek(offset)
                    chunk = stream.read(_RESPONSE_LOG_CHUNK_BYTES)
            except OSError:
                return {"status": "failed",
                        "reason_code": "NATIVE_PEACE_LOG_UNAVAILABLE"}
            complete_end = chunk.rfind(b"\n")
            if complete_end >= 0:
                offset += complete_end + 1
                for line in chunk[:complete_end + 1].splitlines():
                    if len(line) > _RESPONSE_LOG_LINE_BYTES:
                        continue
                    try:
                        event = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, ValueError):
                        continue
                    if (not isinstance(event, dict)
                            or event.get("request_id") != request_id
                            or event.get("session_id") != self.session_id
                            or event.get("event") != "native_peace_submission_result"):
                        continue
                    if not self._valid_native_peace_submission_result(
                            event, request_id, self.session_id, actor, recipient,
                            phase, wanted_date, action_id, normalized):
                        return {"status": "failed",
                                "reason_code": "NATIVE_PEACE_SUBMISSION_RESULT_INVALID"}
                    if event.get("submitted") is not True:
                        return {"status": "failed", "reason_code": event.get(
                            "reason", event.get(
                                "reason_code", "NATIVE_PEACE_NOT_SUBMITTED"))}
                    receipt = self._public_native_peace_submission_receipt(
                        event, request_id, actor, recipient, phase, wanted_date,
                        action_id, normalized)
                    if receipt is None:
                        return {"status": "failed",
                                "reason_code": "NATIVE_PEACE_RECEIPT_INVALID"}
                    return {"status": "submitted", "receipt": receipt}
            time.sleep(0.02)
        return {"status": "timeout", "reason_code": "NATIVE_PEACE_SUBMISSION_TIMEOUT"}

    def _submit_native_declare_war(self, request_id: str, actor: str,
                                   recipient: str, phase: str, date_raw: int,
                                   parameters: object, timeout: float) -> dict:
        if _NATIVE_DECLARE_WAR_SUBMISSION_CAPABILITY not in self.installation_capabilities():
            return {"status": "unavailable",
                    "reason_code": "NATIVE_DECLARE_WAR_SUBMISSION_CAPABILITY_MISSING"}
        if (actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z]{3}", recipient) is None
                or recipient == "FRA"):
            return {"status": "unavailable",
                    "reason_code": "NATIVE_DECLARE_WAR_SUBMISSION_SCOPE_UNSUPPORTED"}
        try:
            selected = self._normalize_declare_war_selection(parameters)
        except (TypeError, ValueError):
            selected = None
        if selected is None:
            return {"status": "failed", "reason_code": "NATIVE_DECLARE_WAR_PARAMETERS_INVALID"}
        if (not isinstance(request_id, str)
                or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id) is None
                or any(value in str(self.session_id) for value in ("|", "\n", "\r"))):
            return {"status": "failed", "reason_code": "NATIVE_DECLARE_WAR_WIRE_INVALID"}
        wanted_date = self._safe_submission_date(date_raw)
        creation_filetime = self.record.get("creation_filetime")
        if (wanted_date is None or isinstance(creation_filetime, bool)
                or not isinstance(creation_filetime, int) or creation_filetime < 0):
            return {"status": "failed", "reason_code": "NATIVE_DECLARE_WAR_WIRE_INVALID"}
        log = self.directory / "control-probe.jsonl"
        try:
            offset = log.stat().st_size
        except OSError:
            return {"status": "failed",
                    "reason_code": "NATIVE_DECLARE_WAR_SUBMISSION_LOG_UNAVAILABLE"}
        expiry = int(time.time_ns() // 100 + _FILETIME_EPOCH + 10 * 10_000_000)
        wire = "|".join((
            "EU4DIP_EXEC3", request_id, self.session_id, str(expiry),
            str(wanted_date), "declare_war", "FRA", recipient, phase,
            selected["casus_belli"], str(selected["province_id"]),
            selected["beneficiary"])) + "\n"
        if len(wire.encode("ascii")) > 512:
            return {"status": "failed", "reason_code": "NATIVE_DECLARE_WAR_WIRE_TOO_LARGE"}
        published = self._publish_atomic_request(wire, request_id, _EXECUTE_REQUEST_NAME)
        if published == "busy":
            return {"status": "busy", "reason_code": "EXECUTE_CHANNEL_BUSY"}
        if published != "published":
            return {"status": "failed", "reason_code": "NATIVE_DECLARE_WAR_WRITE_FAILED"}
        deadline = time.monotonic() + max(0.0, min(float(timeout), _EXECUTE_WAIT_SECONDS))
        while time.monotonic() < deadline:
            try:
                if log.stat().st_size < offset:
                    return {"status": "failed",
                            "reason_code": "NATIVE_DECLARE_WAR_LOG_TRUNCATED"}
                with log.open("rb") as stream:
                    stream.seek(offset)
                    chunk = stream.read(_RESPONSE_LOG_CHUNK_BYTES)
            except OSError:
                return {"status": "failed",
                        "reason_code": "NATIVE_DECLARE_WAR_LOG_UNAVAILABLE"}
            complete_end = chunk.rfind(b"\n")
            if complete_end >= 0:
                offset += complete_end + 1
                for line in chunk[:complete_end + 1].splitlines():
                    if len(line) > _RESPONSE_LOG_LINE_BYTES:
                        continue
                    try:
                        event = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, ValueError):
                        continue
                    if (not isinstance(event, dict)
                            or event.get("request_id") != request_id
                            or event.get("session_id") != self.session_id
                            or event.get("event") !=
                            "native_declare_war_submission_result"):
                        continue
                    if not self._valid_native_declare_war_submission_result(
                            event, request_id, self.session_id, actor, recipient,
                            phase, wanted_date, selected):
                        return {"status": "failed",
                                "reason_code":
                                "NATIVE_DECLARE_WAR_SUBMISSION_RESULT_INVALID"}
                    if event.get("submitted") is not True:
                        return {"status": "failed",
                                "reason_code": event.get(
                                    "reason_code", "NATIVE_DECLARE_WAR_NOT_SUBMITTED")}
                    receipt = self._public_native_declare_war_submission_receipt(
                        event, request_id, actor, recipient, phase, wanted_date, selected)
                    if receipt is None:
                        return {"status": "failed",
                                "reason_code": "NATIVE_DECLARE_WAR_RECEIPT_INVALID"}
                    return {"status": "submitted", "receipt": receipt}
            time.sleep(0.02)
        return {"status": "timeout", "reason_code": "NATIVE_DECLARE_WAR_SUBMISSION_TIMEOUT"}

    def _submit_native_rival(self, action_id: str, request_id: str, actor: str,
                             recipient: str, phase: str, date_raw: int,
                             timeout: float) -> dict:
        """Write the independent Rival wire once and await its receipt."""

        if action_id not in _RIVAL_ACTIONS:
            return {"status": "unavailable", "reason_code": "NATIVE_RIVAL_ACTION_UNSUPPORTED"}
        if _NATIVE_RIVAL_SUBMISSION_CAPABILITY not in self.installation_capabilities():
            return {"status": "unavailable",
                    "reason_code": "NATIVE_RIVAL_SUBMISSION_CAPABILITY_MISSING"}
        if (actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z]{3}", recipient) is None
                or recipient == "FRA"):
            return {"status": "unavailable", "reason_code": "NATIVE_RIVAL_SUBMISSION_SCOPE_UNSUPPORTED"}
        if (not isinstance(request_id, str)
                or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id) is None
                or "|" in self.session_id or "\n" in self.session_id
                or "\r" in self.session_id):
            return {"status": "failed", "reason_code": "NATIVE_RIVAL_WIRE_INVALID"}
        wanted_date = self._safe_submission_date(date_raw)
        creation_filetime = self.record.get("creation_filetime")
        if (wanted_date is None or isinstance(creation_filetime, bool)
                or not isinstance(creation_filetime, int) or creation_filetime < 0):
            return {"status": "failed", "reason_code": "NATIVE_RIVAL_WIRE_INVALID"}
        log = self.directory / "control-probe.jsonl"
        try:
            offset = log.stat().st_size
        except OSError:
            return {"status": "failed", "reason_code": "NATIVE_RIVAL_SUBMISSION_LOG_UNAVAILABLE"}
        expiry_tick = _native_tick_count_ms() + 30_000
        wire = (f"RIVAL_EXEC1 {request_id} {creation_filetime:x} {expiry_tick} "
                f"{wanted_date} {action_id} FRA {recipient}\n")
        published = self._publish_atomic_request(
            wire, request_id, _RIVAL_EXECUTE_REQUEST_NAME)
        if published == "busy":
            return {"status": "busy", "reason_code": "EXECUTE_CHANNEL_BUSY"}
        if published != "published":
            return {"status": "failed", "reason_code": "NATIVE_RIVAL_WRITE_FAILED"}
        deadline = time.monotonic() + max(0.0, min(float(timeout), _EXECUTE_WAIT_SECONDS))
        while time.monotonic() < deadline:
            try:
                if log.stat().st_size < offset:
                    return {"status": "failed", "reason_code": "NATIVE_RIVAL_LOG_TRUNCATED"}
                with log.open("rb") as stream:
                    stream.seek(offset)
                    chunk = stream.read(_RESPONSE_LOG_CHUNK_BYTES)
            except OSError:
                return {"status": "failed", "reason_code": "NATIVE_RIVAL_LOG_UNAVAILABLE"}
            complete_end = chunk.rfind(b"\n")
            if complete_end >= 0:
                offset += complete_end + 1
                for line in chunk[:complete_end + 1].splitlines():
                    if len(line) > _RESPONSE_LOG_LINE_BYTES:
                        continue
                    try:
                        event = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, ValueError):
                        continue
                    if (not isinstance(event, dict)
                            or event.get("request_id") != request_id
                            or event.get("session_id") != self.session_id
                            or event.get("event") != "native_rival_submission_result"):
                        continue
                    if not self._valid_native_rival_submission_result(
                            event, request_id, self.session_id, actor, recipient,
                            phase, wanted_date, action_id):
                        return {"status": "failed", "reason_code": "NATIVE_RIVAL_SUBMISSION_RESULT_INVALID"}
                    if event.get("submitted") is not True:
                        return {"status": "failed",
                                "reason_code": event.get("reason_code", "NATIVE_RIVAL_NOT_SUBMITTED")}
                    receipt = self._public_native_rival_submission_receipt(
                        event, request_id, actor, recipient, phase, wanted_date, action_id)
                    if receipt is None:
                        return {"status": "failed", "reason_code": "NATIVE_RIVAL_RECEIPT_INVALID"}
                    return {"status": "submitted", "receipt": receipt}
            time.sleep(0.02)
        return {"status": "timeout", "reason_code": "NATIVE_RIVAL_SUBMISSION_TIMEOUT"}

    def _submit_alliance_action(self, action_id: str, request_id: str, actor: str,
                                recipient: str, phase: str, date_raw: int,
                                timeout: float, insult_id: int | None = None) -> dict:
        """Publish one native offer and wait for its matching native result.

        A timeout or malformed matching event is terminal for this call. The
        caller must persist that state and must never republish the same id.
        """

        capability = {
            "offer_alliance": _NATIVE_OFFER_SUBMISSION_CAPABILITY,
            "dissolve_alliance": _NATIVE_DISSOLVE_SUBMISSION_CAPABILITY,
            "offer_royal_marriage": _NATIVE_ROYAL_MARRIAGE_SUBMISSION_CAPABILITY,
            "break_royal_ties": _NATIVE_ROYAL_MARRIAGE_SUBMISSION_CAPABILITY,
            "improve_relations": _NATIVE_IMPROVE_RELATIONS_SUBMISSION_CAPABILITY,
            "stop_improving_relations": _NATIVE_IMPROVE_RELATIONS_SUBMISSION_CAPABILITY,
            "build_spy_network": _NATIVE_SPY_NETWORK_SUBMISSION_CAPABILITY,
            "stop_building_spy_network": _NATIVE_SPY_NETWORK_SUBMISSION_CAPABILITY,
            "proclaim_guarantee": _NATIVE_GUARANTEE_SUBMISSION_CAPABILITY,
            "revoke_guarantee": _NATIVE_GUARANTEE_SUBMISSION_CAPABILITY,
            "support_independence": _NATIVE_SUPPORT_INDEPENDENCE_SUBMISSION_CAPABILITY,
            "revoke_support_independence": _NATIVE_SUPPORT_INDEPENDENCE_SUBMISSION_CAPABILITY,
            "ask_military_access": _NATIVE_MILITARY_ACCESS_SUBMISSION_CAPABILITY,
            "cancel_military_access": _NATIVE_MILITARY_ACCESS_SUBMISSION_CAPABILITY,
            "send_insult": _NATIVE_INSULT_SUBMISSION_CAPABILITY,
            "scornful_insult": _NATIVE_INSULT_SUBMISSION_CAPABILITY,
            "offer_vassalization": _NATIVE_VASSALIZATION_SUBMISSION_CAPABILITY,
            "cancel_vassalization": _NATIVE_VASSALIZATION_SUBMISSION_CAPABILITY,
        }.get(action_id)
        if capability is None:
            return {"status": "unavailable", "reason_code": "NATIVE_SUBMISSION_ACTION_UNSUPPORTED"}
        if capability not in self.installation_capabilities():
            return {"status": "unavailable",
                    "reason_code": ("NATIVE_ROYAL_MARRIAGE_SUBMISSION_CAPABILITY_MISSING"
                                     if action_id in ("offer_royal_marriage", "break_royal_ties")
                    else "NATIVE_IMPROVE_RELATIONS_SUBMISSION_CAPABILITY_MISSING"
                                     if action_id in ("improve_relations", "stop_improving_relations")
                    else "NATIVE_GUARANTEE_SUBMISSION_CAPABILITY_MISSING"
                                     if action_id in ("proclaim_guarantee", "revoke_guarantee")
                                     else "NATIVE_SUPPORT_INDEPENDENCE_SUBMISSION_CAPABILITY_MISSING"
                                     if action_id in ("support_independence", "revoke_support_independence")
                                     else "NATIVE_MILITARY_ACCESS_SUBMISSION_CAPABILITY_MISSING"
                                      if action_id in ("ask_military_access", "cancel_military_access")
                                     else "NATIVE_INSULT_SUBMISSION_CAPABILITY_MISSING"
                                     if action_id in _INSULT_ACTIONS
                                     else "NATIVE_SPY_NETWORK_SUBMISSION_CAPABILITY_MISSING"
                                     if action_id in ("build_spy_network", "stop_building_spy_network")
                                     else "NATIVE_VASSALIZATION_SUBMISSION_CAPABILITY_MISSING"
                                     if action_id in _VASSALIZATION_ACTIONS
                                     else "NATIVE_OFFER_SUBMISSION_CAPABILITY_MISSING")}
        if (actor != "FRA" or phase != "initiate"
                or (action_id in ("improve_relations", "stop_improving_relations",
                                  "build_spy_network", "stop_building_spy_network",
                                  "proclaim_guarantee", "revoke_guarantee",
                                   "support_independence", "revoke_support_independence",
                                   "ask_military_access", "cancel_military_access",
                                   "send_insult", "scornful_insult",
                                   "offer_vassalization", "cancel_vassalization")
                    and recipient == "FRA")):
            return {"status": "unavailable",
                    "reason_code": ("NATIVE_ROYAL_MARRIAGE_SUBMISSION_SCOPE_UNSUPPORTED"
                                     if action_id in ("offer_royal_marriage", "break_royal_ties")
                                     else "NATIVE_IMPROVE_RELATIONS_SUBMISSION_SCOPE_UNSUPPORTED"
                                     if action_id in ("improve_relations", "stop_improving_relations")
                                     else "NATIVE_SPY_NETWORK_SUBMISSION_SCOPE_UNSUPPORTED"
                                     if action_id in ("build_spy_network", "stop_building_spy_network")
                                     else "NATIVE_GUARANTEE_SUBMISSION_SCOPE_UNSUPPORTED"
                                     if action_id in ("proclaim_guarantee", "revoke_guarantee")
                                     else "NATIVE_SUPPORT_INDEPENDENCE_SUBMISSION_SCOPE_UNSUPPORTED"
                                     if action_id in ("support_independence", "revoke_support_independence")
                                      else "NATIVE_MILITARY_ACCESS_SUBMISSION_SCOPE_UNSUPPORTED"
                                      if action_id in ("ask_military_access", "cancel_military_access")
                                     else "NATIVE_INSULT_SUBMISSION_SCOPE_UNSUPPORTED"
                                     if action_id in _INSULT_ACTIONS
                                     else "NATIVE_VASSALIZATION_SUBMISSION_SCOPE_UNSUPPORTED"
                                     if action_id in _VASSALIZATION_ACTIONS
                                     else "NATIVE_OFFER_SUBMISSION_SCOPE_UNSUPPORTED")}
        if action_id == "send_insult" and insult_id != -1:
            return {"status": "failed", "reason_code": "INSULT_PARAMETER_INVALID"}
        if action_id == "scornful_insult" and self._safe_int(
                insult_id, 0, 2147483647) is None:
            return {"status": "failed", "reason_code": "INSULT_PARAMETER_INVALID"}
        if (not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id)
                or not isinstance(recipient, str) or not re.fullmatch(r"[A-Z]{3}", recipient)
                or "|" in self.session_id or "\n" in self.session_id or "\r" in self.session_id):
            return {"status": "failed", "reason_code": "NATIVE_SUBMISSION_WIRE_INVALID"}
        if self._safe_submission_date(date_raw) is None:
            return {"status": "failed", "reason_code": "NATIVE_SUBMISSION_DATE_INVALID"}
        log = self.directory / "control-probe.jsonl"
        try:
            offset = log.stat().st_size
        except OSError:
            return {"status": "failed", "reason_code": "NATIVE_SUBMISSION_LOG_UNAVAILABLE"}
        expiry = int(time.time_ns() // 100 + _FILETIME_EPOCH + 10 * 10_000_000)
        wire_fields = ("v2" if action_id in _INSULT_ACTIONS else "v1",
                       request_id, self.session_id, str(expiry), str(date_raw),
                       action_id, actor, recipient, phase)
        if action_id in _INSULT_ACTIONS:
            wire_fields = (*wire_fields, str(insult_id))
        wire = "|".join(wire_fields) + "\n"
        published = self._publish_execute_request(wire, request_id)
        if published == "busy":
            return {"status": "busy", "reason_code": "EXECUTE_CHANNEL_BUSY"}
        if published != "published":
            return {"status": "failed", "reason_code": "EXECUTE_CHANNEL_WRITE_FAILED"}
        deadline = time.monotonic() + max(0.0, min(float(timeout), _EXECUTE_WAIT_SECONDS))
        while time.monotonic() < deadline:
            try:
                with log.open("rb") as stream:
                    if log.stat().st_size < offset:
                        return {"status": "failed", "reason_code": "EXECUTE_LOG_TRUNCATED"}
                    stream.seek(offset)
                    chunk = stream.read(65536)
            except OSError:
                return {"status": "failed", "reason_code": "EXECUTE_LOG_UNAVAILABLE"}
            complete_end = chunk.rfind(b"\n")
            if complete_end >= 0:
                offset += complete_end + 1
                for line in chunk[:complete_end + 1].splitlines():
                    try:
                        event = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, ValueError):
                        continue
                    if not isinstance(event, dict):
                        continue
                    if event.get("request_id") != request_id or event.get("session_id") != self.session_id:
                        continue
                    if event.get("event") != "native_alliance_submission_result":
                        continue
                    valid_submission = (
                        self._valid_native_vassalization_submission_result(
                            event, request_id, self.session_id, actor, recipient,
                            phase, date_raw, action_id)
                        if action_id in _VASSALIZATION_ACTIONS else
                        self._valid_native_submission_result(
                            event, request_id, self.session_id, actor, recipient,
                            phase, date_raw, action_id))
                    if not valid_submission:
                        return {"status": "failed", "reason_code": "NATIVE_SUBMISSION_RESULT_INVALID"}
                    if event.get("submitted") is not True:
                        return {"status": "failed", "reason_code": "NATIVE_SUBMISSION_NOT_SUBMITTED"}
                    receipt = (
                        self._public_native_vassalization_submission_receipt(
                            event, request_id, actor, recipient, phase, date_raw, action_id)
                        if action_id in _VASSALIZATION_ACTIONS else
                        self._public_native_submission_receipt(
                            event, request_id, actor, recipient, phase, date_raw, action_id))
                    if receipt is None:
                        return {"status": "failed", "reason_code": "NATIVE_SUBMISSION_RECEIPT_INVALID"}
                    return {"status": "submitted", "receipt": receipt}
            time.sleep(0.02)
        return {"status": "timeout", "reason_code": "NATIVE_SUBMISSION_TIMEOUT"}

    @classmethod
    def _valid_native_inbound_submission_result(cls, event: object, request_id: str,
                                                 session_id: str, actor: str,
                                                 recipient: str, phase: str,
                                                 date_raw: object,
                                                 native_proposal_id: object,
                                                 action_id: str = "offer_alliance") -> bool:
        # Peace inbound responses use a dedicated receipt event and preserve
        # the original proposer as the native actor.  The public response API
        # keeps the observed proposer->FRA direction, so it cannot use the
        # generic relation submission validator below.
        if action_id == "peace_offer":
            if (not isinstance(event, dict)
                    or event.get("event") != "native_peace_inbound_submission_result"
                    or event.get("request_id") != request_id
                    or event.get("session_id") != session_id
                    or event.get("action_id") != action_id
                    or event.get("family") != "peace"
                    or event.get("recipient") != "FRA"
                    or event.get("phase") != phase
                    or phase not in ("accept", "reject")
                    or not isinstance(actor, str)
                    or not re.fullmatch(r"[A-Z0-9]{3}", actor)
                    or actor == "FRA"
                    or event.get("actor") != actor
                    or event.get("decision_country") != "FRA"
                    or event.get("submitted") is not True
                    or event.get("transport_verified") is not True
                    or event.get("request_binding_verified") is not True):
                return False
            wanted_date = cls._safe_submission_date(date_raw)
            if (wanted_date is None
                    or cls._safe_submission_date(event.get("date_raw")) != wanted_date):
                return False
            wanted_id = cls._safe_native_proposal_id(native_proposal_id)
            if wanted_id is None:
                return False
            if ("native_proposal_id" in event
                    and cls._safe_native_proposal_id(event.get("native_proposal_id"))
                    != wanted_id):
                return False
            for field, validator in (
                    ("native_sequence", cls._safe_submission_sequence),
                    ("native_origin", cls._safe_submission_origin),
                    ("native_flags", cls._safe_submission_flags)):
                if field in event and validator(event.get(field)) is None:
                    return False
            context = event.get("peace_context")
            if context is not None and not cls._valid_public_peace_context(context):
                return False
            return True
        if not cls._valid_native_submission_result(
                event, request_id, session_id, actor, recipient, phase, date_raw, action_id):
            return False
        family = _inbound_family(action_id)
        if not isinstance(event, dict) or family is None or event.get("action_id") != action_id:
            return False
        if recipient != "FRA" or phase not in ("accept", "reject"):
            return False
        if (not isinstance(actor, str) or not re.fullmatch(r"[A-Z0-9]{3}", actor)
                or actor == "FRA"):
            return False
        wanted_id = cls._safe_native_proposal_id(native_proposal_id)
        if wanted_id is None:
            return False
        if action_id == "offer_royal_marriage":
            # The native submission event predates the family discriminator.
            # The action id is already the binding for this transport record;
            # accept an omitted family field for observed r27 receipts while
            # rejecting an explicitly crossed family.
            if (event.get("family") not in (None, "royal_marriage")
                    or ("extra60" in event and (
                        isinstance(event.get("extra60"), bool)
                        or not isinstance(event.get("extra60"), int)
                        or event.get("extra60") != 0))):
                return False
        elif action_id == "support_independence":
            # The generic transport receipt predates family-specific fields,
            # so an omitted family is accepted.  An explicit cross-family
            # value is never accepted for a Support response.
            if event.get("family") not in (None, "support_independence"):
                return False
        elif action_id == "ask_military_access":
            # The generic submission event predates family-specific fields;
            # accept omission for observed transport receipts but reject a
            # receipt explicitly crossed into another relation family.
            if event.get("family") not in (None, "military_access"):
                return False
        elif action_id == "offer_vassalization":
            if event.get("family") != "vassalization":
                return False
        # The existing submission event contract binds request/session and
        # does not require a proposal id.  If r22 emits the optional field,
        # verify it; never infer it from actor/date alone.
        if "native_proposal_id" in event:
            return cls._safe_native_proposal_id(event.get("native_proposal_id")) == wanted_id
        return True

    @classmethod
    def _public_native_inbound_submission_receipt(cls, event: dict, request_id: str,
                                                  actor: str, phase: str,
                                                  date_raw: int,
                                                  action_id: str = "offer_alliance") -> dict:
        """Copy an inbound transport receipt without the raw proposal id."""

        if action_id == "peace_offer":
            result = {
                "event": "native_peace_inbound_submission_result",
                "request_id": request_id,
                "action_id": action_id,
                "family": "peace",
                "actor": actor,
                "recipient": "FRA",
                "decision_country": "FRA",
                "phase": phase,
                "date_raw": date_raw,
                "submitted": True,
                "transport_verified": True,
                "request_binding_verified": True,
            }
            for key, validator in (
                    ("native_sequence", cls._safe_submission_sequence),
                    ("native_origin", cls._safe_submission_origin),
                    ("native_flags", cls._safe_submission_flags)):
                if key in event:
                    value = validator(event.get(key))
                    if value is not None:
                        result[key] = value
            return result

        result = {
            "event": "native_alliance_submission_result",
            "request_id": request_id,
            "action_id": action_id,
            "actor": actor,
            "recipient": "FRA",
            "phase": phase,
            "date_raw": date_raw,
            "submitted": True,
            "native_queue_verified": True,
            "transport_ring": True,
            "transport_ring_receipt": True,
            "native_sequence": cls._safe_submission_sequence(event.get("native_sequence")),
            "native_origin": cls._safe_submission_origin(event.get("native_origin")),
            "native_flags": cls._safe_submission_flags(event.get("native_flags")),
        }
        if action_id == "offer_vassalization":
            result["family"] = "vassalization"
        return result

    @classmethod
    def _public_native_inbound_response_result(cls, event: object, request_id: str,
                                               session_id: str, actor: str,
                                               phase: str, date_raw: object,
                                               native_proposal_id: object,
                                               action_id: str = "offer_alliance") -> dict | None:
        if not isinstance(event, dict):
            return None
        family = _inbound_family(action_id)
        if family is None:
            return None
        if action_id == "peace_offer":
            for field, expected in (
                    ("event", "native_peace_inbound_response_result"),
                    ("request_id", request_id),
                    ("session_id", session_id),
                    ("action_id", action_id),
                    ("actor", actor),
                    ("recipient", "FRA"),
                    ("phase", phase),
                    ("family", "peace")):
                if event.get(field) != expected:
                    return None
            if (not isinstance(actor, str)
                    or not re.fullmatch(r"[A-Z0-9]{3}", actor)
                    or actor == "FRA"
                    or phase not in ("accept", "reject")):
                return None
            wanted_id = cls._safe_native_proposal_id(native_proposal_id)
            if wanted_id is None:
                return None
            if ("native_proposal_id" in event
                    and cls._safe_native_proposal_id(event.get("native_proposal_id"))
                    != wanted_id):
                return None
            wanted_date = cls._safe_submission_date(date_raw)
            if (wanted_date is None
                    or cls._safe_submission_date(event.get("date_raw")) != wanted_date):
                return None
            for field in ("response_verified", "request_binding_verified",
                          "pending_removed", "war_state_verified",
                          "terms_verified", "war_before", "war_after"):
                if not isinstance(event.get(field), bool):
                    return None
            native_state = event.get("native_state")
            if (isinstance(native_state, bool)
                    or not isinstance(native_state, int)
                    or native_state not in (1, 2)):
                return None
            context = event.get("peace_context")
            if not cls._valid_public_peace_context(context):
                return None
            outcome = event.get("outcome")
            if outcome not in ("accepted", "rejected", "unknown"):
                return None
            if (native_state == 2 and event["war_before"] is True
                    and event["war_after"] is False
                    and event["pending_removed"] is True):
                derived = "accepted"
            elif (native_state == 1 and event["war_before"] is True
                  and event["war_after"] is True
                  and event["pending_removed"] is True):
                derived = "rejected"
            else:
                derived = "unknown"
            if outcome != derived:
                return None
            result = {
                "event": "native_peace_inbound_response_result",
                "request_id": request_id,
                "action_id": action_id,
                "family": "peace",
                "actor": actor,
                "recipient": "FRA",
                "decision_country": "FRA",
                "phase": phase,
                "date_raw": wanted_date,
                "native_state": native_state,
                "native_outcome": outcome,
                "response_verified": True,
                "request_binding_verified": True,
                "pending_removed": event["pending_removed"],
                "war_before": event["war_before"],
                "war_after": event["war_after"],
                "war_state_verified": True,
                "terms_verified": event["terms_verified"],
                "peace_context": cls._copy_public_peace_context(context),
            }
            return result
        support = action_id == "support_independence"
        military = action_id == "ask_military_access"
        vassal = action_id == "offer_vassalization"
        expected_event = ("native_diplomacy_relation_response_result"
                          if support or military or vassal else "native_alliance_response_result")
        for field, expected in (
                ("event", expected_event),
                ("request_id", request_id),
                ("session_id", session_id),
                ("action_id", action_id),
                ("actor", actor),
                ("recipient", "FRA"),
                ("phase", phase)):
            if event.get(field) != expected:
                return None
        if (not isinstance(actor, str) or not re.fullmatch(r"[A-Z0-9]{3}", actor)
                or actor == "FRA" or phase not in ("accept", "reject")):
            return None
        wanted_id = cls._safe_native_proposal_id(native_proposal_id)
        if wanted_id is None:
            return None
        if ("native_proposal_id" in event
                and cls._safe_native_proposal_id(event.get("native_proposal_id")) != wanted_id):
            return None
        wanted_date = cls._safe_submission_date(date_raw)
        if wanted_date is None or cls._safe_submission_date(event.get("date_raw")) != wanted_date:
            return None
        if (event.get("response_verified") is not True
                or event.get("request_binding_verified") is not True
                or not isinstance(event.get("pending_removed"), bool)):
            return None
        native_state = event.get("native_state")
        royal = action_id == "offer_royal_marriage"
        if support:
            if event.get("family") != "support_independence":
                return None
            relation_before = event.get("support_independence_before")
            relation_after = event.get("support_independence_after")
            if (type(event.get("native_variant")) is not int
                    or event.get("native_variant") != 1
                    or not isinstance(relation_before, bool)
                    or not isinstance(relation_after, bool)):
                return None
        elif military:
            if event.get("family") != "military_access":
                return None
            relation_before = event.get("military_access_before")
            relation_after = event.get("military_access_after")
            if (type(event.get("native_variant")) is not int
                    or event.get("native_variant") != 1
                    or not isinstance(relation_before, bool)
                    or not isinstance(relation_after, bool)):
                return None
        elif vassal:
            if event.get("family") != "vassalization":
                return None
            relation_before = event.get("vassalization_before")
            relation_after = event.get("vassalization_after")
            if (type(event.get("native_variant")) is not int
                    or event.get("native_variant") != 1
                    or not isinstance(relation_before, bool)
                    or not isinstance(relation_after, bool)):
                return None
        else:
            relation_before = None
            relation_after = event.get("royal_marriage_after" if royal else "alliance_after")
            if (isinstance(native_state, bool) or not isinstance(native_state, int)
                    or not isinstance(relation_after, bool)):
                return None
            if royal and event.get("family") != "royal_marriage":
                return None
            if not royal and event.get("family") not in (None, "alliance"):
                return None
        if ((support or military or vassal)
                and (type(native_state) is not int or native_state not in (1, 2))):
            return None
        if (support or military or vassal) and event.get("pending_removed") is not True:
            return None
        for field, validator in (
                ("native_sequence", cls._safe_submission_sequence),
                ("native_origin", cls._safe_submission_origin),
                ("native_flags", cls._safe_submission_flags)):
            if field in event and validator(event.get(field)) is None:
                return None
        pending_removed = event["pending_removed"]
        if ((support or military or vassal) and native_state == 2 and relation_before is False
                and relation_after is True and pending_removed is True):
            outcome = "accepted"
        elif ((support or military or vassal) and native_state == 1 and relation_before is False
              and relation_after is False and pending_removed is True):
            outcome = "rejected"
        elif not support and native_state == 2 and relation_after is True and pending_removed is True:
            outcome = "accepted"
        elif not support and native_state == 1 and relation_after is False and pending_removed is True:
            outcome = "rejected"
        else:
            outcome = "unknown"
        result = {
            "event": expected_event,
            "request_id": request_id,
            "action_id": action_id,
            "actor": actor,
            "recipient": "FRA",
            "phase": phase,
            "date_raw": wanted_date,
            "response_verified": True,
            "request_binding_verified": True,
            "native_state": native_state,
            "pending_removed": pending_removed,
            "native_outcome": outcome,
        }
        if support:
            result.update({"family": "support_independence", "native_variant": 1,
                           "support_independence_before": relation_before,
                           "support_independence_after": relation_after})
        elif military:
            result.update({"family": "military_access", "native_variant": 1,
                           "military_access_before": relation_before,
                           "military_access_after": relation_after})
        elif vassal:
            result.update({"family": "vassalization", "native_variant": 1,
                           "vassalization_before": relation_before,
                           "vassalization_after": relation_after})
        elif royal:
            result.update({"family": "royal_marriage", "royal_marriage_after": relation_after})
        else:
            result["alliance_after"] = relation_after
        return result

    def submit_native_inbound_response(self, request_id: str, actor: str,
                                       recipient: str, phase: str, date_raw: int,
                                       native_proposal_id: object,
                                       timeout: float = _EXECUTE_WAIT_SECONDS,
                                       action_id: str = "offer_alliance") -> dict:
        """Publish one capability-authorized inbound accept/reject response."""

        capability = _inbound_response_capability(action_id)
        if capability is None:
            return {"status": "failed", "reason_code": "NATIVE_INBOUND_WIRE_INVALID"}
        if capability not in self.installation_capabilities():
            return {"status": "unavailable", "reason_code": (
                "NATIVE_INBOUND_ROYAL_MARRIAGE_RESPONSE_CAPABILITY_MISSING"
                if action_id == "offer_royal_marriage"
                else "NATIVE_INBOUND_SUPPORT_INDEPENDENCE_RESPONSE_CAPABILITY_MISSING"
                if action_id == "support_independence"
                else "NATIVE_INBOUND_MILITARY_ACCESS_RESPONSE_CAPABILITY_MISSING"
                if action_id == "ask_military_access"
                else "NATIVE_INBOUND_VASSALIZATION_RESPONSE_CAPABILITY_MISSING"
                if action_id == "offer_vassalization"
                else "NATIVE_INBOUND_PEACE_RESPONSE_CAPABILITY_MISSING"
                if action_id == "peace_offer"
                else "NATIVE_INBOUND_RESPONSE_CAPABILITY_MISSING")}
        if (not isinstance(request_id, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id)
                or not isinstance(actor, str) or not re.fullmatch(r"[A-Z0-9]{3}", actor)
                or actor == "FRA" or recipient != "FRA"
                or phase not in ("accept", "reject")
                or "|" in self.session_id or "\n" in self.session_id
                or "\r" in self.session_id):
            return {"status": "failed", "reason_code": "NATIVE_INBOUND_WIRE_INVALID"}
        wanted_date = self._safe_submission_date(date_raw)
        wanted_id = self._safe_native_proposal_id(native_proposal_id)
        if wanted_date is None or wanted_id is None:
            return {"status": "failed", "reason_code": "NATIVE_INBOUND_WIRE_INVALID"}
        log = self.directory / "control-probe.jsonl"
        try:
            offset = log.stat().st_size
        except OSError:
            return {"status": "failed", "reason_code": "NATIVE_SUBMISSION_LOG_UNAVAILABLE"}
        expiry = int(time.time_ns() // 100 + _FILETIME_EPOCH + 10 * 10_000_000)
        wire = "|".join(("v1", request_id, self.session_id, str(expiry), str(wanted_date),
                          action_id, actor, "FRA", phase, str(wanted_id))) + "\n"
        published = self._publish_atomic_request(wire, request_id, _INBOUND_RESPONSE_REQUEST_NAME)
        if published == "busy":
            return {"status": "busy", "reason_code": "INBOUND_RESPONSE_CHANNEL_BUSY"}
        if published != "published":
            return {"status": "failed", "reason_code": "INBOUND_RESPONSE_CHANNEL_WRITE_FAILED"}
        deadline = time.monotonic() + max(0.0, min(float(timeout), _EXECUTE_WAIT_SECONDS))
        while time.monotonic() < deadline:
            try:
                with log.open("rb") as stream:
                    if log.stat().st_size < offset:
                        return {"status": "failed", "reason_code": "EXECUTE_LOG_TRUNCATED"}
                    stream.seek(offset)
                    chunk = stream.read(_RESPONSE_LOG_CHUNK_BYTES)
            except OSError:
                return {"status": "failed", "reason_code": "NATIVE_SUBMISSION_LOG_UNAVAILABLE"}
            complete_end = chunk.rfind(b"\n")
            if complete_end >= 0:
                offset += complete_end + 1
                for line in chunk[:complete_end + 1].splitlines():
                    if len(line) > _RESPONSE_LOG_LINE_BYTES:
                        continue
                    try:
                        event = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, ValueError):
                        continue
                    expected_submission_event = (
                        "native_peace_inbound_submission_result"
                        if action_id == "peace_offer"
                        else "native_alliance_submission_result")
                    if (not isinstance(event, dict)
                            or event.get("request_id") != request_id
                            or event.get("session_id") != self.session_id
                            or event.get("event") != expected_submission_event):
                        continue
                    if not self._valid_native_inbound_submission_result(
                            event, request_id, self.session_id, actor, "FRA", phase,
                            wanted_date, wanted_id, action_id):
                        return {"status": "failed", "reason_code": "NATIVE_SUBMISSION_RESULT_INVALID"}
                    if event.get("submitted") is not True:
                        return {"status": "failed", "reason_code": "NATIVE_SUBMISSION_NOT_SUBMITTED"}
                    receipt = self._public_native_inbound_submission_receipt(
                        event, request_id, actor, phase, wanted_date, action_id)
                    return {"status": "submitted", "receipt": receipt}
            time.sleep(0.02)
        return {"status": "timeout", "reason_code": "NATIVE_SUBMISSION_TIMEOUT"}

    def read_native_alliance_inbound_response(self, request_id: str, actor: str,
                                              recipient: str, phase: str,
                                              date_raw: object,
                                              native_proposal_id: object,
                                              action_id: str = "offer_alliance") -> dict | None:
        """Read one bound r22 inbound response result incrementally."""

        if recipient != "FRA" or _inbound_family(action_id) is None:
            return None

        log = self.directory / "control-probe.jsonl"
        try:
            size = log.stat().st_size
            offset = self._response_log_offsets.get(request_id, 0)
            if size < offset:
                offset = 0
            with log.open("rb") as stream:
                stream.seek(offset)
                pending = b""
                consumed = offset
                scanned = 0
                while scanned < _RESPONSE_LOG_SCAN_BYTES:
                    chunk = stream.read(min(_RESPONSE_LOG_CHUNK_BYTES,
                                            _RESPONSE_LOG_SCAN_BYTES - scanned))
                    if not chunk:
                        break
                    scanned += len(chunk)
                    pending += chunk
                    while True:
                        newline = pending.find(b"\n")
                        if newline < 0:
                            break
                        line = pending[:newline]
                        pending = pending[newline + 1:]
                        consumed += newline + 1
                        if len(line) > _RESPONSE_LOG_LINE_BYTES:
                            continue
                        try:
                            event = json.loads(line.decode("utf-8"))
                        except (UnicodeDecodeError, ValueError):
                            continue
                        expected_event = (
                            "native_diplomacy_relation_response_result"
                            if action_id in ("support_independence", "ask_military_access",
                                             "offer_vassalization")
                            else "native_peace_inbound_response_result"
                            if action_id == "peace_offer"
                            else "native_alliance_response_result")
                        if (not isinstance(event, dict)
                                or event.get("event") != expected_event
                                or event.get("request_id") != request_id
                                or event.get("session_id") != self.session_id):
                            continue
                        result = self._public_native_inbound_response_result(
                            event, request_id, self.session_id, actor, phase,
                            date_raw, native_proposal_id, action_id)
                        self._response_log_offsets[request_id] = consumed
                        if result is None:
                            return {"status": "invalid", "reason_code": "NATIVE_RESPONSE_RESULT_INVALID"}
                        return {"status": result["native_outcome"], "result": result}
                    if len(pending) > _RESPONSE_LOG_LINE_BYTES:
                        consumed += len(pending)
                        pending = b""
                self._response_log_offsets[request_id] = consumed
        except OSError:
            return None
        return None

    def read_native_royal_marriage_inbound_response(
            self, request_id: str, actor: str, recipient: str, phase: str,
            date_raw: object, native_proposal_id: object) -> dict | None:
        """Read one bound native Royal Marriage response result."""

        return self.read_native_alliance_inbound_response(
            request_id, actor, recipient, phase, date_raw, native_proposal_id,
            "offer_royal_marriage")

    def read_native_support_independence_inbound_response(
            self, request_id: str, actor: str, recipient: str, phase: str,
            date_raw: object, native_proposal_id: object) -> dict | None:
        """Read one bound native Support Independence response result."""

        return self.read_native_alliance_inbound_response(
            request_id, actor, recipient, phase, date_raw, native_proposal_id,
            "support_independence")

    def read_native_military_access_inbound_response(
            self, request_id: str, actor: str, recipient: str, phase: str,
            date_raw: object, native_proposal_id: object) -> dict | None:
        """Read one bound native Military Access response result."""

        return self.read_native_alliance_inbound_response(
            request_id, actor, recipient, phase, date_raw, native_proposal_id,
            "ask_military_access")

    def read_native_vassalization_inbound_response(
            self, request_id: str, actor: str, recipient: str, phase: str,
            date_raw: object, native_proposal_id: object) -> dict | None:
        """Read one bound native Vassalization inbound response result."""

        return self.read_native_alliance_inbound_response(
            request_id, actor, recipient, phase, date_raw, native_proposal_id,
            "offer_vassalization")

    def read_native_peace_inbound_response(
            self, request_id: str, actor: str, recipient: str, phase: str,
            date_raw: object, native_proposal_id: object) -> dict | None:
        """Read one bound aggregate Peace inbound response result."""

        return self.read_native_alliance_inbound_response(
            request_id, actor, recipient, phase, date_raw, native_proposal_id,
            "peace_offer")

    # Explicit aliases make the adapter easy to patch in offline bridge tests.
    submit_native_offer = submit_offer_alliance
    submit_alliance = submit_offer_alliance

    @staticmethod
    def _safe_int(value: object, minimum: int | None = None,
                  maximum: int | None = None) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        if minimum is not None and value < minimum:
            return None
        if maximum is not None and value > maximum:
            return None
        return value

    @staticmethod
    def _safe_bool(value: object) -> bool | None:
        return value if isinstance(value, bool) else None

    @classmethod
    def _normalize_declare_war_parameters(cls, parameters: object) -> dict | None:
        """Validate and normalize the bounded Declare War QUERY3 selection.

        An empty object deliberately selects the older QUERY1 default-payload
        observation.  A non-empty object must identify the CB and war-goal
        context completely; ally selection is reserved for a later adapter
        and therefore only an empty list is accepted here.
        """

        if parameters == {}:
            return None
        if not isinstance(parameters, dict):
            raise ValueError("DECLARE_WAR_PARAMETERS_MUST_BE_OBJECT")
        if set(parameters) != {"casus_belli", "war_goal", "call_allies"}:
            raise ValueError("DECLARE_WAR_PARAMETERS_REQUIRED")
        casus_belli = parameters.get("casus_belli")
        if (not isinstance(casus_belli, str)
                or re.fullmatch(r"[A-Za-z0-9_]{1,128}", casus_belli) is None):
            raise ValueError("DECLARE_WAR_CASUS_BELLI_INVALID")
        war_goal = parameters.get("war_goal")
        if not isinstance(war_goal, dict) or set(war_goal) != {
                "province_id", "beneficiary"}:
            raise ValueError("DECLARE_WAR_WAR_GOAL_INVALID")
        province_id = war_goal.get("province_id")
        if (isinstance(province_id, bool) or not isinstance(province_id, int)
                or not (-1 == province_id or 1 <= province_id <= 2147483647)):
            raise ValueError("DECLARE_WAR_PROVINCE_ID_INVALID")
        beneficiary = war_goal.get("beneficiary")
        if (not isinstance(beneficiary, str)
                or (beneficiary != "---"
                    and re.fullmatch(r"[A-Z]{3}", beneficiary) is None)):
            raise ValueError("DECLARE_WAR_BENEFICIARY_INVALID")
        call_allies = parameters.get("call_allies")
        if not isinstance(call_allies, list):
            raise ValueError("DECLARE_WAR_CALL_ALLIES_INVALID")
        if call_allies:
            raise ValueError("DECLARE_WAR_CALL_ALLIES_UNSUPPORTED")
        if casus_belli == "no_casus_belli" and (
                province_id != -1 or beneficiary != "FRA"):
            raise ValueError("DECLARE_WAR_NO_CB_CONTEXT_INVALID")
        return {
            "casus_belli": casus_belli,
            "province_id": province_id,
            "beneficiary": beneficiary,
            "call_allies": [],
        }

    @classmethod
    def _normalize_declare_war_selection(cls, parameters: object) -> dict | None:
        """Accept the public QUERY3 shape or the internal normalized shape."""

        if (isinstance(parameters, dict)
                and set(parameters) == {
                    "casus_belli", "province_id", "beneficiary", "call_allies"}):
            parameters = {
                "casus_belli": parameters["casus_belli"],
                "war_goal": {
                    "province_id": parameters["province_id"],
                    "beneficiary": parameters["beneficiary"],
                },
                "call_allies": parameters["call_allies"],
            }
        return cls._normalize_declare_war_parameters(parameters)

    @staticmethod
    def _safe_native_text(event: dict, codec: str = DEFAULT_NATIVE_TEXT_CODEC,
                          field: str = "text_hex") -> str | None:
        """Decode configured bounded native text without exposing its bytes."""
        selected = validate_native_text_codec(codec)
        if not isinstance(event, dict):
            return None
        if event.get("text_readable") is not True:
            return None
        encoded = event.get(field)
        if not isinstance(encoded, str):
            return None
        try:
            text = decode_native_text_hex(encoded, selected)
        except InvalidNativeText:
            return None
        return text if text.strip() else None

    @classmethod
    def _semantic_reason_item(cls, event: dict,
                              codec: str = DEFAULT_NATIVE_TEXT_CODEC,
                              metadata_acknowledged: bool = False) -> dict:
        selected = validate_native_text_codec(codec)
        value = cls._safe_int(event.get("native_value"), -2147483648, 2147483647)
        name = cls._safe_native_text(event, selected)
        value_verified = (metadata_acknowledged and value is not None
                          and event.get("row_binding_verified") is True
                          and event.get("constructor_value_verified") is True
                          and event.get("value_representation") == "signed_int32"
                          and event.get("value_normalized") is False)
        identifier = event.get("native_identifier")
        identifier_verified = (value_verified
                               and event.get("native_identifier_verified") is True
                               and event.get("identifier_verified") is True
                               and event.get("identity_source") == "native_localization_key"
                               and isinstance(identifier, str)
                               and re.fullmatch(r"DIPLO_[A-Z0-9_]{1,41}", identifier) is not None)
        return {
            "name": name,
            "text_decoded": name is not None,
            "native_value": value,
            "source": "native_rule",
            "complete": False,
            "text_encoding_verified": False,
            "text_complete": False,
            "native_identifier": identifier if identifier_verified else None,
            "identifier_verified": identifier_verified,
            "identity_source": "native_localization_key" if identifier_verified else None,
            "native_value_verified": value_verified,
            "value_representation": "signed_int32" if value_verified else "unknown",
            "value_normalized": False,
            "unit": "unknown",
            "unit_verified": False,
            "truncated": event.get("text_truncated") is True,
        }

    @classmethod
    def _semantic_inspection(cls, event: dict, reason_events: dict[int, dict],
                             codec: str = DEFAULT_NATIVE_TEXT_CODEC,
                             metadata_acknowledged: bool = False,
                             candidate_events: list[dict] | None = None) -> dict:
        selected = validate_native_text_codec(codec)
        reason_count = cls._safe_int(event.get("reason_count"), 0, 4096)
        items = [cls._semantic_reason_item(reason_events[index], selected, metadata_acknowledged)
                 for index in sorted(reason_events)[:_MAX_REASON_ITEMS]]
        display_predicate = cls._safe_bool(event.get("display_predicate"))
        if "common_action_gate" in event:
            common_action_gate = cls._safe_bool(event.get("common_action_gate"))
        else:
            # Legacy r7 emitted only display_predicate.  It is the sole
            # permitted fallback for the missing common gate field.
            common_action_gate = display_predicate
        diagnostic = cls._safe_native_text({
            "text_readable": event.get("diagnostic_readable") is True,
            "text_hex": event.get("native_diagnostic_hex", ""),
        }, selected)
        diagnostic_readable = cls._safe_bool(event.get("diagnostic_readable"))
        if diagnostic_readable is None and diagnostic is not None:
            diagnostic_readable = True
        result = {
            "event": "native_alliance_inspection",
            "action_id": event.get("action_id"),
            "actor": event.get("actor"),
            "recipient": event.get("recipient"),
            "phase": event.get("phase"),
            "date_raw": cls._safe_int(event.get("date_raw")),
            "ui_selection_checked": cls._safe_bool(event.get("ui_selection_checked")),
            "native_visibility": cls._safe_bool(event.get("native_visibility")),
            "ui_enabled_gate_checked": cls._safe_bool(event.get("ui_enabled_gate_checked")),
            "common_action_gate": common_action_gate,
            "display_predicate": display_predicate,
            "initiation_gate": cls._safe_bool(event.get("initiation_gate")),
            "tooltip_gate": cls._safe_bool(event.get("tooltip_gate")),
            "validity_called": cls._safe_bool(event.get("validity_called")),
            "native_validity": cls._safe_bool(event.get("native_validity")),
            "diagnostic_readable": diagnostic_readable,
            "diagnostic_truncated": cls._safe_bool(event.get("diagnostic_truncated")),
            "native_diagnostic_text": diagnostic,
            "native_diagnostic_text_decoded": diagnostic is not None,
            "diplomat_context_readable": cls._safe_bool(event.get("diplomat_context_readable")),
            "diplomat_required": cls._safe_bool(event.get("diplomat_required")),
            "available_diplomat_count": cls._safe_int(event.get("available_diplomat_count"), 0, 256),
            "acceptance_predicate_available": cls._safe_bool(event.get("acceptance_predicate_available")),
            "native_would_accept": cls._safe_bool(event.get("native_would_accept")),
            "score_applicable": cls._safe_bool(event.get("score_applicable")),
            "score_available": cls._safe_bool(event.get("score_available")),
            "native_total_raw": cls._safe_int(event.get("native_total_raw"), -2147483648, 2147483647),
            "acceptance_threshold_raw": cls._safe_int(event.get("acceptance_threshold_raw"), -2147483648, 2147483647),
            "reason_container_readable": cls._safe_bool(event.get("reason_container_readable")),
            "reason_count": reason_count,
            "reason_items": items,
            "reason_items_truncated": bool(reason_count is not None and reason_count > _MAX_REASON_ITEMS)
                or len(reason_events) > _MAX_REASON_ITEMS,
            "reason_items_decoded": any(item["text_decoded"] for item in items),
            "full_rules_complete": cls._safe_bool(event.get("full_rules_complete")),
            "submitted": cls._safe_bool(event.get("submitted")),
        }
        # Guarantee uses the established inspection event while adding a
        # family-specific relation-state proof.  Keep these fields absent for
        # older Alliance/Royal/Improve/Spy events so their public contracts
        # remain unchanged.
        if "family" in event:
            result["family"] = event.get("family")
        if "guarantee_active" in event:
            result["guarantee_active"] = cls._safe_bool(event.get("guarantee_active"))
        if "guarantee_state_verified" in event:
            result["guarantee_state_verified"] = cls._safe_bool(
                event.get("guarantee_state_verified"))
        if event.get("family") == "guarantee":
            active = cls._safe_bool(event.get("guarantee_active"))
            state_verified = event.get("guarantee_state_verified") is True
            result["relationship_state"] = {
                "guarantee_active": active if active is not None else None,
                "complete": active is not None and state_verified,
            }
        if "support_independence_active" in event:
            result["support_independence_active"] = cls._safe_bool(
                event.get("support_independence_active"))
        if "support_independence_state_verified" in event:
            result["support_independence_state_verified"] = cls._safe_bool(
                event.get("support_independence_state_verified"))
        if event.get("family") == "support_independence":
            active = cls._safe_bool(event.get("support_independence_active"))
            state_verified = event.get("support_independence_state_verified") is True
            result["relationship_state"] = {
                "support_independence_active": active if active is not None else None,
                "complete": active is not None and state_verified,
            }
        if "military_access_active" in event:
            result["military_access_active"] = cls._safe_bool(
                event.get("military_access_active"))
        if "military_access_state_verified" in event:
            result["military_access_state_verified"] = cls._safe_bool(
                event.get("military_access_state_verified"))
        if event.get("family") == "military_access":
            active = cls._safe_bool(event.get("military_access_active"))
            state_verified = event.get("military_access_state_verified") is True
            result["relationship_state"] = {
                "military_access_active": active if active is not None else None,
                "complete": active is not None and state_verified,
            }
        if event.get("family") == "vassalization":
            subject_type = event.get("subject_type")
            if (not isinstance(subject_type, str) or not subject_type
                    or len(subject_type) > 64):
                subject_type = None
            active = cls._safe_bool(event.get("vassal_active"))
            state_verified = event.get("vassal_state_verified") is True
            result.update({
                "vassal_active": active,
                "vassal_state_verified": cls._safe_bool(
                    event.get("vassal_state_verified")),
                "actor_is_overlord": cls._safe_bool(
                    event.get("actor_is_overlord")),
                "actor_is_subject": cls._safe_bool(
                    event.get("actor_is_subject")),
                "subject_type": subject_type,
                "relationship_state": {
                    "vassal_active": active if active is not None else None,
                    "complete": active is not None and state_verified,
                },
            })
            # Vassal cancellation exposes a verified prestige delta in the
            # R35B query contract.  Keep raw native values public alongside
            # the typed proof; the cost projection is added below only when
            # the cancellation predicate supplies a complete delta.
            result.update({
                "prestige_raw": cls._safe_int(
                    event.get("prestige_raw"), -2147483648, 2147483647),
                "cancel_prestige_delta_raw": cls._safe_int(
                    event.get("cancel_prestige_delta_raw"),
                    -2147483648, 2147483647),
                "cancel_prestige_effect_allowed": cls._safe_bool(
                    event.get("cancel_prestige_effect_allowed")),
                "prestige_scale": cls._safe_int(
                    event.get("prestige_scale"), 1, 1000000),
                "cancel_prestige_cost_verified": event.get(
                    "cancel_prestige_cost_verified") is True,
            })
        if event.get("family") == "insult":
            # Insults are one-sided actions.  Their query never supplies a
            # counterparty acceptance predicate; an empty scornful request
            # only discovers candidate IDs and remains parameter-unselected.
            result.update({
                "insult_id": cls._safe_int(event.get("insult_id"), -2147483648, 2147483647),
                "insult_parameter_selected": cls._safe_bool(
                    event.get("insult_parameter_selected")),
                "insult_state_verified": cls._safe_bool(event.get("insult_state_verified")),
                "insult_active": cls._safe_bool(event.get("insult_active")),
                "opinion_modifier_raw": cls._safe_int(
                    event.get("opinion_modifier_raw"), -2147483648, 2147483647),
                "actor_prestige_raw": cls._safe_int(
                    event.get("actor_prestige_raw"), -2147483648, 2147483647),
                "prestige_cost_raw": cls._safe_int(
                    event.get("prestige_cost_raw"), -2147483648, 2147483647),
                "candidates_available": cls._safe_bool(event.get("candidates_available")),
                "candidate_count": cls._safe_int(event.get("candidate_count"), 0, 256),
                "candidates_complete": cls._safe_bool(event.get("candidates_complete")),
                "parameters": {
                    "candidates": {
                        "insult_id": [candidate["insult_id"]
                                      for candidate in (candidate_events or [])],
                        "items": candidate_events or [],
                        "complete": event.get("candidates_complete") is True,
                    },
                },
            })
        return result

    @classmethod
    def _semantic_declare_war_inspection(
            cls, event: dict,
            codec: str = DEFAULT_NATIVE_TEXT_CODEC) -> dict:
        """Project the read-only default Declare War inspection.

        The generic UI/rule fields remain useful evidence.  The separate
        parameter and candidate flags prevent those observations from being
        mistaken for a complete CB/war-goal declaration.
        """

        result = cls._semantic_inspection(event, {}, codec, False)
        result.update({
            "event": "native_declare_war_inspection",
            "family": "declare_war",
            "initiation_gate_checked": event.get("initiation_gate_checked") is True,
            "parameter_context_complete": event.get("parameter_context_complete") is True,
            "native_default_payload": event.get("native_default_payload") is True,
            "candidate_context_complete": event.get("candidate_context_complete") is True,
            "candidates": [],
            "full_rules_complete": event.get("full_rules_complete") is True,
            "submitted": event.get("submitted") is True,
        })
        if "selection_requested" in event:
            result.update({
                "selection_requested": event.get("selection_requested") is True,
                "selection_matched": event.get("selection_matched") is True,
                "selection_match_count": cls._safe_int(
                    event.get("selection_match_count"), 0, 4096),
                "requested_casus_belli": event.get("requested_casus_belli"),
                "requested_province_id": cls._safe_int(
                    event.get("requested_province_id"), -2147483648, 2147483647),
                "requested_beneficiary": event.get("requested_beneficiary"),
            })
        enumeration_fields = (
            "candidate_enumeration_called", "candidate_enumeration_complete",
            "candidate_native_count", "candidate_capture_truncated",
            "candidate_cleanup_verified")
        if any(field in event for field in enumeration_fields):
            projected_candidates = []
            for candidate in event.get("candidates", []):
                metadata_readable = candidate.get("metadata_readable") is True
                text_readable = (metadata_readable
                                 and candidate.get("metadata_text_readable") is True)
                metadata_text = cls._safe_native_text({
                    "text_hex": candidate.get("native_metadata_hex"),
                    "text_readable": text_readable,
                }, codec)
                projected_candidates.append({
                    # These are query-local observation coordinates.  The
                    # bridge intentionally does not expose the native
                    # discriminator, bytes, pointer or a stable CB identity.
                    "candidate_index": candidate.get("candidate_index"),
                    "metadata_group_raw": candidate.get("metadata_group_raw"),
                    "metadata_readable": metadata_readable,
                    "metadata_text_readable": candidate.get(
                        "metadata_text_readable") is True,
                    "metadata_text_truncated": candidate.get(
                        "metadata_text_truncated") is True,
                    "metadata_text": metadata_text,
                    "metadata_text_decoded": metadata_text is not None,
                    "identifier_verified": False,
                })
                if any(field in candidate for field in (
                        "casus_belli_key", "casus_belli_key_verified",
                        "target_province_id", "province_identifier_verified",
                        "beneficiary_tag", "beneficiary_identifier_verified")):
                    projected_candidates[-1].update({
                        "casus_belli_key": candidate.get("casus_belli_key"),
                        "casus_belli_key_verified": candidate.get(
                            "casus_belli_key_verified") is True,
                        "target_province_id": cls._safe_int(
                            candidate.get("target_province_id"),
                            -2147483648, 2147483647),
                        "province_identifier_verified": candidate.get(
                            "province_identifier_verified") is True,
                        "beneficiary_tag": candidate.get("beneficiary_tag"),
                        "beneficiary_identifier_verified": candidate.get(
                            "beneficiary_identifier_verified") is True,
                    })
            native_count = cls._safe_int(event.get("candidate_native_count"), 0, 4096)
            captured_truncated = event.get("candidate_capture_truncated") is True
            result["candidate_enumeration_called"] = (
                event.get("candidate_enumeration_called") is True)
            result["candidate_enumeration_complete"] = (
                event.get("candidate_enumeration_complete") is True)
            result["candidate_native_count"] = native_count
            result["candidate_capture_truncated"] = captured_truncated
            result["candidate_cleanup_verified"] = (
                event.get("candidate_cleanup_verified") is True)
            result["candidate_enumeration"] = {
                "called": result["candidate_enumeration_called"],
                "complete": result["candidate_enumeration_complete"],
                "native_count": native_count,
                "captured_count": len(projected_candidates),
                "capture_truncated": captured_truncated,
                "cleanup_verified": result["candidate_cleanup_verified"],
                "query_complete": (
                    result["candidate_enumeration_called"]
                    and result["candidate_enumeration_complete"]
                    and result["candidate_cleanup_verified"]
                    and not captured_truncated
                    and native_count == len(projected_candidates)),
            }
            result["candidates"] = projected_candidates
        if "native_costs" in event:
            result["costs"] = cls._public_declare_war_costs(event, codec)
        result["native_rule_components"] = {
            "ui_selection_checked": event.get("ui_selection_checked") is True,
            "native_visibility": cls._safe_bool(event.get("native_visibility")),
            "ui_enabled_gate_checked": event.get("ui_enabled_gate_checked") is True,
            "common_action_gate": cls._safe_bool(event.get("common_action_gate")),
            "validity_called": event.get("validity_called") is True,
            "native_validity": cls._safe_bool(event.get("native_validity")),
            "initiation_gate_checked": event.get("initiation_gate_checked") is True,
            "initiation_gate": cls._safe_bool(event.get("initiation_gate")),
            "parameter_context_complete": event.get("parameter_context_complete") is True,
            "native_default_payload": event.get("native_default_payload") is True,
            "candidate_context_complete": event.get("candidate_context_complete") is True,
            "candidate_enumeration_called": event.get(
                "candidate_enumeration_called"),
            "candidate_enumeration_complete": event.get(
                "candidate_enumeration_complete"),
            "candidate_native_count": event.get("candidate_native_count"),
            "candidate_capture_truncated": event.get(
                "candidate_capture_truncated"),
            "candidate_cleanup_verified": event.get(
                "candidate_cleanup_verified"),
            "full_rules_complete": event.get("full_rules_complete") is True,
            "complete": False,
        }
        return result

    @classmethod
    def _semantic_peace_context_inspection(
            cls, event: dict,
            codec: str = DEFAULT_NATIVE_TEXT_CODEC) -> dict:
        """Project the bounded, read-only peace-war context discovery.

        The native event may carry private lookup data beside each public
        registry id.  Only the session-scoped opaque id and the fields in the
        peace context contract leave this method; native references, object
        addresses and war terms never become LLM-visible values.
        """

        # Validate the configured codec even though this event carries no
        # text fields; this keeps the semantic helper's contract consistent
        # with the other native inspection projections.
        validate_native_text_codec(codec)
        war_contexts = []
        for raw in event.get("wars", [])[:32]:
            if not isinstance(raw, dict):
                continue
            war_contexts.append({
                "war_id": raw.get("war_id"),
                "identity_scope": raw.get("identity_scope"),
                "actor": raw.get("actor"),
                "recipient": raw.get("recipient"),
                "pair_at_war": raw.get("pair_at_war") is True,
                "actor_war_role": None,
                "recipient_war_role": None,
                "roles_verified": raw.get("roles_verified") is True,
                "actor_is_war_leader": None,
                "recipient_is_war_leader": None,
                "leaders_verified": raw.get("leaders_verified") is True,
                "context_complete": raw.get("context_complete") is True,
            })
        return {
            "event": "native_peace_context_inspection",
            "family": "peace",
            "query_id": event.get("query_id"),
            "session_id": event.get("session_id"),
            "action_id": event.get("action_id"),
            "actor": event.get("actor"),
            "recipient": event.get("recipient"),
            "phase": event.get("phase"),
            "date_raw": cls._safe_int(event.get("date_raw")),
            "context_discovery": event.get("discovery") is True,
            "query_complete": event.get("query_complete") is True,
            "war_context_enumeration_complete": (
                event.get("enumeration_complete") is True),
            "native_offer_inspected": event.get("native_offer_inspected") is True,
            "full_rules_complete": event.get("full_rules_complete") is True,
            "submitted": event.get("submitted") is True,
            "war_contexts": war_contexts,
        }

    @classmethod
    def _semantic_peace_offer_evaluation(
            cls, evaluation: dict,
            codec: str = DEFAULT_NATIVE_TEXT_CODEC) -> dict:
        """Project QUERY4's optional, read-only score/factor extension.

        The native preview score and proposal aggregate score are separate
        signed integers.  A false availability flag keeps each raw
        placeholder visible for audit while preventing it from being used as
        a semantic value.  A factor value is marked numerically verified
        when its row binding and integer value were verified by the producer.
        Identifier recognition is independent: dynamic factors may have a
        null native identifier while their row value and flag remain bound to
        the inspected offer.
        """

        selected = validate_native_text_codec(codec)
        score_raw = cls._safe_int(
            evaluation.get("score_raw"), -2147483648, 2147483647)
        score_available = evaluation.get("score_available") is True
        aggregate_score_raw = cls._safe_int(
            evaluation.get("aggregate_score_raw"), -2147483648, 2147483647)
        aggregate_score_available = (
            evaluation.get("aggregate_score_available") is True)
        items = []
        for raw in evaluation.get("items", []):
            identifier = raw.get("native_identifier")
            identifier_verified = (
                raw.get("identifier_verified") is True
                and isinstance(identifier, str) and bool(identifier))
            value = cls._safe_int(
                raw.get("native_value"), -2147483648, 2147483647)
            row_binding_verified = raw.get("row_binding_verified") is True
            text = cls._safe_native_text({
                "text_hex": raw.get("text_hex"),
                "text_readable": raw.get("text_readable") is True,
            }, selected)
            items.append({
                "native_identifier": identifier if identifier_verified else None,
                "identifier_verified": identifier_verified,
                "native_value": value,
                "native_value_verified": (
                    value is not None and row_binding_verified),
                "native_flag": raw.get("native_flag") is True,
                "native_flag_verified": (
                    row_binding_verified),
                "text": text,
                "text_decoded": text is not None,
                "text_truncated": raw.get("text_truncated") is True,
                "row_binding_verified": row_binding_verified,
                "source": "native_rule",
                "complete": (
                    identifier_verified
                    and row_binding_verified
                    and text is not None
                    and raw.get("text_truncated") is False),
            })
        return {
            "called": evaluation.get("called") is True,
            "score_available": score_available,
            "score_raw": score_raw,
            "native_total": score_raw if score_available else None,
            "aggregate_score_available": aggregate_score_available,
            "aggregate_score_raw": aggregate_score_raw,
            "score_representation": evaluation.get("score_representation"),
            "factor_native_count": cls._safe_int(
                evaluation.get("factor_native_count"), 0, 4096),
            "factor_capture_truncated": evaluation.get(
                "factor_capture_truncated") is True,
            "factors_available": evaluation.get("factors_available") is True,
            "factors_complete": evaluation.get("factors_complete") is True,
            "items": items,
            "complete": False,
        }

    @staticmethod
    def _valid_native_peace_war_context(
            value: object, actor: str, recipient: str,
            direction: str = "demand") -> bool:
        """Validate observed native sides without assigning attack/defence roles."""

        if not isinstance(value, dict):
            return False
        required = (
            "war_context_resolved", "participant_lists_complete",
            "actor_side_verified", "recipient_side_verified",
            "actor_recipient_opposite", "offer_identity_verified",
            "offer_vectors_readable",
        )
        if any(value.get(key) is not True for key in required):
            return False
        for key in ("primary_offer_mapping_verified",
                    "derived_offer_mapping_verified",
                    "offer_vector_mapping_verified"):
            if not isinstance(value.get(key), bool):
                return False
        if value["offer_vector_mapping_verified"] != (
                value["primary_offer_mapping_verified"]
                and value["derived_offer_mapping_verified"]):
            return False
        if any(value.get(key) is not False for key in (
                "roles_verified", "leaders_verified", "context_complete")):
            return False
        if direction not in ("demand", "offer"):
            return False
        sides = {}
        for side in ("side_a", "side_b"):
            members = value.get(f"{side}_members")
            count = value.get(f"{side}_count")
            if (not isinstance(members, list) or not 1 <= len(members) <= 256
                    or isinstance(count, bool) or not isinstance(count, int)
                    or count != len(members)
                    or any(not isinstance(tag, str)
                           or re.fullmatch(r"[A-Z0-9]{3}", tag) is None
                           for tag in members)
                    or len(set(members)) != len(members)):
                return False
            sides[side] = set(members)
        if sides["side_a"] & sides["side_b"]:
            return False
        actor_side = value.get("actor_side")
        recipient_side = value.get("recipient_side")
        selected_side = actor_side if direction == "demand" else recipient_side
        return (actor_side in sides and recipient_side in sides
                and actor_side != recipient_side
                and value.get("selected_side") == selected_side
                and actor in sides[actor_side]
                and recipient in sides[recipient_side])

    @staticmethod
    def _semantic_peace_war_context(value: dict) -> dict:
        """Project the stable member tags; private native references stay local."""

        fields = (
            "war_context_resolved", "side_a_count", "side_b_count",
            "participant_lists_complete", "selected_side", "actor_side",
            "recipient_side", "actor_side_verified", "recipient_side_verified",
            "actor_recipient_opposite", "offer_identity_verified",
            "offer_vectors_readable", "primary_offer_mapping_verified",
            "derived_offer_mapping_verified", "offer_vector_mapping_verified",
            "roles_verified", "leaders_verified", "context_complete",
        )
        result = {key: value[key] for key in fields}
        for side in ("side_a", "side_b"):
            result[f"{side}_members"] = list(value[f"{side}_members"])
        return result

    @staticmethod
    def _valid_native_peace_payload(value: object) -> bool:
        if (not isinstance(value, dict)
                or value.get("schema") != "native_peace_serialized_fields_v1"
                or value.get("authority_bound") is not False):
            return False
        for key in ("capture_available", "serialized_fields_complete",
                    "source_owner_verified", "action_owner_verified",
                    "selected_index_complete"):
            if not isinstance(value.get(key), bool):
                return False
        for key in ("term_count", "selected_term_count", "unsupported_term_count"):
            count = value.get(key)
            if (isinstance(count, bool) or not isinstance(count, int)
                    or not 0 <= count <= 512):
                return False
        if max(value["selected_term_count"], value["unsupported_term_count"]) > value["term_count"]:
            return False
        complete = value["serialized_fields_complete"]
        if complete and (not value["capture_available"]
                         or not value["source_owner_verified"]
                         or not value["action_owner_verified"]
                         or not value["selected_index_complete"]
                         or value["unsupported_term_count"] != 0):
            return False
        for key in ("source_copy_equal", "serialized_fields_unchanged"):
            if complete:
                if not isinstance(value.get(key), bool):
                    return False
            elif value.get(key) is not None:
                return False
        return True

    @staticmethod
    def _semantic_peace_payload(value: dict) -> dict:
        return {key: value[key] for key in (
            "schema", "capture_available", "serialized_fields_complete",
            "source_copy_equal", "serialized_fields_unchanged",
            "source_owner_verified", "action_owner_verified", "term_count",
            "selected_term_count", "unsupported_term_count",
            "selected_index_complete", "authority_bound",
        )}

    @classmethod
    def _semantic_peace_empty_offer_inspection(
            cls, event: dict,
            codec: str = DEFAULT_NATIVE_TEXT_CODEC) -> dict:
        """Project QUERY4's empty-white-peace constructor inspection.

        QUERY4 proves construction and three native gates for one discovered
        war.  It does not prove participant roles, complete peace terms, UI
        display rules, fees or acceptance, so those claims stay outside this
        native projection and are handled as unknown by the public inspect
        layer.
        """

        selected = validate_native_text_codec(codec)

        def diagnostic(prefix: str) -> dict:
            # QUERY4's validity diagnostic uses the native producer's short
            # field names (diagnostic_readable/diagnostic_truncated).  The
            # common and send diagnostics retain their qualified names.
            readable_field = (
                "diagnostic_readable" if prefix == "native"
                else f"{prefix}_diagnostic_readable")
            truncated_field = (
                "diagnostic_truncated" if prefix == "native"
                else f"{prefix}_diagnostic_truncated")
            readable = event.get(readable_field) is True
            text = cls._safe_native_text({
                "text_hex": event.get(f"{prefix}_diagnostic_hex"),
                "text_readable": readable,
            }, selected)
            return {
                "text": text,
                "text_decoded": text is not None,
                "source": "native_rule",
                "complete": False,
                "truncated": event.get(truncated_field) is True,
            }

        validity_diagnostic = diagnostic("native")
        common_diagnostic = diagnostic("common")
        initiation_diagnostic = diagnostic("send")
        result = {
            "event": "native_peace_empty_offer_inspection",
            "family": "peace",
            "query_id": event.get("query_id"),
            "session_id": event.get("session_id"),
            "action_id": event.get("action_id"),
            "actor": event.get("actor"),
            "recipient": event.get("recipient"),
            "phase": event.get("phase"),
            "date_raw": cls._safe_int(event.get("date_raw")),
            "selected_war_id": event.get("war_id"),
            "identity_scope": event.get("identity_scope"),
            "peace_context": {
                "war_id": event.get("war_id"),
                # QUERY4 had no direction field; all legacy empty queries are
                # demand.  QUERY7 carries the explicit offer direction.
                "direction": event.get("direction", "demand"),
                "terms": [],
                "complete": False,
            },
            "query_complete": event.get("query_complete") is True,
            "native_offer_inspected": event.get("native_offer_inspected") is True,
            "pair_at_war": event.get("pair_at_war") is True,
            "unique_shared_war": event.get("unique_shared_war") is True,
            "offer_constructed": event.get("offer_constructed") is True,
            "action_constructed": event.get("action_constructed") is True,
            "participant_copy_verified": event.get(
                "participant_copy_verified") is True,
            "offer_identity_verified": event.get(
                "offer_identity_verified") is True,
            "object_unchanged": event.get("object_unchanged") is True,
            "cleanup_verified": event.get("cleanup_verified") is True,
            "validity_called": event.get("validity_called") is True,
            "native_validity": cls._safe_bool(event.get("native_validity")),
            "common_gate_checked": event.get("common_gate_checked") is True,
            "common_action_gate": cls._safe_bool(event.get("common_action_gate")),
            "initiation_gate_checked": event.get(
                "initiation_gate_checked") is True,
            "initiation_gate": cls._safe_bool(event.get("initiation_gate")),
            "native_diagnostic_text": validity_diagnostic["text"],
            "native_diagnostic_text_decoded": validity_diagnostic["text_decoded"],
            "native_diagnostic_truncated": validity_diagnostic["truncated"],
            "diagnostics": {
                "validity": validity_diagnostic,
                "common_action_gate": common_diagnostic,
                "initiation_gate": initiation_diagnostic,
            },
            "full_rules_complete": event.get("full_rules_complete") is True,
            "reasons_complete": event.get("reasons_complete") is True,
            "submitted": event.get("submitted") is True,
        }
        wrapper_fields = (
            "native_wrapper_gate_checked", "native_wrapper_gate",
            "wrapper_identity_verified", "wrapper_payload_unchanged")
        if any(field in event for field in wrapper_fields):
            result.update({field: cls._safe_bool(event.get(field))
                           for field in wrapper_fields})
        if isinstance(event.get("native_evaluation"), dict):
            result["native_evaluation"] = cls._semantic_peace_offer_evaluation(
                event["native_evaluation"], selected)
        if isinstance(event.get("native_war_context"), dict):
            result["native_war_context"] = cls._semantic_peace_war_context(
                event["native_war_context"])
        if isinstance(event.get("native_payload"), dict):
            result["native_payload"] = cls._semantic_peace_payload(event["native_payload"])
        return result

    @classmethod
    def _semantic_peace_money_offer_inspection(
            cls, event: dict,
            codec: str = DEFAULT_NATIVE_TEXT_CODEC) -> dict:
        """Project a read-only money-term constructor in either direction."""

        result = cls._semantic_peace_empty_offer_inspection(event, codec)
        result["event"] = "native_peace_money_offer_inspection"
        result["action_id"] = "demand_ducats"
        money = event.get("native_money", {})
        result["native_money"] = {
            "query_complete": money.get("query_complete") is True,
            "requested_amount_raw": cls._safe_int(
                money.get("requested_amount_raw"), -2147483648, 2147483647),
            "currency_scale": cls._safe_int(
                money.get("currency_scale"), 0, 2147483647),
            "currency_precision_raw": cls._safe_int(
                money.get("currency_precision_raw"), 0, 2147483647),
            "currency_scale_verified": money.get("currency_scale_verified") is True,
            "ceiling_input_raw": cls._safe_int(
                money.get("ceiling_input_raw"), -2147483648, 2147483647),
            "currency_ceiling_raw": cls._safe_int(
                money.get("currency_ceiling_raw"), 0, 2147483647),
            "amount_within_limit": money.get("amount_within_limit") is True,
            "setter_called": money.get("setter_called") is True,
            "source_amount_raw": cls._safe_int(
                money.get("source_amount_raw"), 0, 2147483647),
            "action_amount_raw": cls._safe_int(
                money.get("action_amount_raw"), 0, 2147483647),
            "source_readback_matches": money.get("source_readback_matches") is True,
            "action_copy_verified": money.get("action_copy_verified") is True,
            "parameters_matched": money.get("parameters_matched") is True,
            "direction": money.get("direction"),
            "direction_verified": money.get("direction_verified") is True,
            "payer": money.get("payer"),
            "claimant": money.get("claimant"),
        }
        amount_raw = result["native_money"]["requested_amount_raw"]
        direction = money.get("direction", event.get("direction", "demand"))
        if (result["native_money"]["parameters_matched"]
                and isinstance(amount_raw, int)
                and not isinstance(amount_raw, bool)
                and amount_raw > 0
                and amount_raw % 100 == 0):
            result["peace_context"]["direction"] = direction
            result["peace_context"]["terms"] = [{
                "action_id": "demand_ducats",
                "amount": f"{amount_raw // 1000}.{(amount_raw % 1000) // 100}",
                "amount_raw": amount_raw,
                "payer": money.get("payer"),
                "claimant": money.get("claimant"),
            }]
        return result

    @classmethod
    def _semantic_peace_province_offer_inspection(
            cls, event: dict,
            codec: str = DEFAULT_NATIVE_TEXT_CODEC) -> dict:
        """Project a province-term inspection in either direction.

        The native event deliberately separates candidate enumeration from a
        selected province toggle.  Public rows contain only the bounded
        province identifier, beneficiary, selection state and decoded name;
        native object references and caller metadata never cross this method.
        """
        native = event.get("native_provinces", {})
        common = dict(event)
        common["event"] = "native_peace_empty_offer_inspection"
        common["action_id"] = "white_peace"
        common["direction"] = event.get(
            "direction", native.get("direction", "demand"))
        result = cls._semantic_peace_empty_offer_inspection(common, codec)
        result["event"] = "native_peace_province_offer_inspection"
        result["action_id"] = "cede_province"
        public = {
            "query_complete": native.get("query_complete") is True,
            "candidate_enumeration_complete": (
                native.get("candidate_enumeration_complete") is True),
            "candidate_count": cls._safe_int(
                native.get("candidate_count"), 0, 512),
            "candidates": [],
            "selection_requested": native.get("selection_requested") is True,
            "requested_province_ids": list(native.get(
                "requested_province_ids", [])),
            "requested_beneficiary": native.get("requested_beneficiary"),
            "requested_candidates_found": (
                native.get("requested_candidates_found") is True),
            "toggle_called": native.get("toggle_called") is True,
            "toggle_call_count": cls._safe_int(
                native.get("toggle_call_count"), 0, 512),
            "parameters_matched": native.get("parameters_matched") is True,
            "selected_province_ids": list(native.get(
                "selected_province_ids", [])),
            "selected_beneficiary": native.get("selected_beneficiary"),
            "selection_copy_verified": (
                native.get("selection_copy_verified") is True),
            "selected_term_records_complete": (
                native.get("selected_term_records_complete") is True),
            "direction": native.get("direction"),
            "direction_verified": native.get("direction_verified") is True,
            "reason_code": native.get("reason_code"),
            "selection_delta_raw": cls._safe_int(
                native.get("selection_delta_raw"), -2147483648, 2147483647),
        }
        selected_codec = validate_native_text_codec(codec)
        for row in native.get("candidates", []):
            decoded = cls._safe_native_text({
                "text_hex": row.get("name_hex"),
                "text_readable": row.get("name_readable") is True,
            }, selected_codec)
            public["candidates"].append({
                "province_id": row.get("province_id"),
                "beneficiary": row.get("beneficiary"),
                "selected": row.get("selected") is True,
                "name": decoded,
                "name_readable": decoded is not None,
                "name_truncated": row.get("name_truncated") is True,
                "native_selectability_checked": (
                    row.get("native_selectability_checked") is True),
                "native_selectable": row.get("native_selectable")
                if isinstance(row.get("native_selectable"), bool) else None,
            })
        result["native_provinces"] = public
        # QUERY6's actual terms reflect the native selection, rather than the
        # requested list.  This keeps an unmatched request from masquerading
        # as a successful toggle.
        if (public["selected_province_ids"]
                and isinstance(public["selected_beneficiary"], str)):
            result["peace_context"]["direction"] = public["direction"]
            result["peace_context"]["terms"] = [{
                "action_id": "cede_province",
                "province_ids": list(public["selected_province_ids"]),
                "beneficiary": public["selected_beneficiary"],
            }]
        return result

    @classmethod
    def _semantic_peace_combined_offer_inspection(
            cls, event: dict,
            codec: str = DEFAULT_NATIVE_TEXT_CODEC) -> dict:
        """Project one aggregate money-plus-province QUERY7 observation.

        Both nested term projections are derived from the same native event.
        The public context contains only terms that native copied and matched;
        a failed money or province sub-selection therefore cannot be promoted
        to the caller's requested payload.
        """

        result = cls._semantic_peace_empty_offer_inspection(event, codec)
        result["event"] = "native_peace_combined_offer_inspection"
        result["action_id"] = event.get("action_id")
        money_view = cls._semantic_peace_money_offer_inspection(event, codec)
        province_view = cls._semantic_peace_province_offer_inspection(event, codec)
        result["native_money"] = money_view.get("native_money")
        result["native_provinces"] = province_view.get("native_provinces")

        money = result["native_money"] or {}
        provinces = result["native_provinces"] or {}
        direction = event.get("direction", "demand")
        terms = []
        amount_raw = money.get("requested_amount_raw")
        if (money.get("parameters_matched") is True
                and isinstance(amount_raw, int)
                and not isinstance(amount_raw, bool)
                and amount_raw > 0 and amount_raw % 100 == 0):
            terms.append({
                "action_id": "demand_ducats",
                "amount": f"{amount_raw // 1000}.{(amount_raw % 1000) // 100}",
                "amount_raw": amount_raw,
                "payer": money.get("payer"),
                "claimant": money.get("claimant"),
            })
        selected_ids = provinces.get("selected_province_ids", [])
        selected_beneficiary = provinces.get("selected_beneficiary")
        if (provinces.get("parameters_matched") is True
                and isinstance(selected_ids, list) and selected_ids
                and isinstance(selected_beneficiary, str)):
            terms.append({
                "action_id": "cede_province",
                "province_ids": list(selected_ids),
                "beneficiary": selected_beneficiary,
            })
        result["peace_context"]["direction"] = direction
        result["peace_context"]["terms"] = terms
        payload = result.get("native_payload")
        payload_complete = (isinstance(payload, dict)
                            and payload.get("serialized_fields_complete") is True
                            and payload.get("source_copy_equal") is True
                            and payload.get("serialized_fields_unchanged") is True)
        result["parameters_matched"] = (
            money.get("parameters_matched") is True
            and provinces.get("parameters_matched") is True)
        result["parameters_complete"] = (
            result["parameters_matched"] and payload_complete)
        return result

    @classmethod
    def _semantic_rival_inspection(cls, event: dict,
                                   codec: str = DEFAULT_NATIVE_TEXT_CODEC) -> dict:
        """Project the countrycommands Rival query without inventing UI rules.

        Rival is a one-sided country relation.  The native query proves the
        command predicate and the current membership.  Schema 2 additionally
        reports the individual candidate and war-gate fields, while complete
        cost/preflight coverage remains separate from those facts.
        """

        result = cls._semantic_inspection(event, {}, codec, False)
        rules_schema = cls._safe_int(event.get("rules_schema"), 1, 3)
        if rules_schema is None:
            # The pre-R34B event did not carry a schema marker.  The validator
            # accepts that shape as schema 1; keep the public value explicit.
            rules_schema = 1
        result.update({
            "event": "native_rival_inspection",
            "family": "rival",
            "rules_schema": rules_schema,
            "native_command_validity_called": event.get(
                "native_command_validity_called") is True,
            "native_command_validity": cls._safe_bool(
                event.get("native_command_validity")),
            "rival_state_verified": event.get("rival_state_verified") is True,
            "rival_active": cls._safe_bool(event.get("rival_active")),
            "rival_since_date_raw": cls._safe_int(
                event.get("rival_since_date_raw"), -2147483648, 2147483647),
            "rival_count": cls._safe_int(event.get("rival_count"), 0, 1000000),
            "max_rivals": cls._safe_int(event.get("max_rivals"), 0, 1000000),
            "diplomatic_power_raw": cls._safe_int(
                event.get("diplomatic_power_raw"), -2147483648, 2147483647),
            "at_war": cls._safe_bool(event.get("at_war")),
            # Preserve the native boolean value.  This is a capability/status
            # field, not a proof flag: ``false`` must remain false in the
            # public result rather than becoming ``true`` because the field
            # was present.
            "candidate_eligibility_available": cls._safe_bool(
                event.get("candidate_eligibility_available")),
            "candidate_eligible": cls._safe_bool(event.get("candidate_eligible")),
            "target_exists": cls._safe_bool(event.get("target_exists")),
            "ui_war_allowed": cls._safe_bool(event.get("ui_war_allowed")),
            "cost_query_called": cls._safe_bool(event.get("cost_query_called")),
            "diplomatic_power_cost_raw": cls._safe_int(
                event.get("diplomatic_power_cost_raw"), 0, 2147483647),
            "full_rules_complete": cls._safe_bool(event.get("full_rules_complete")),
            "native_action_available": cls._safe_bool(
                event.get("native_action_available")),
            "submitted": cls._safe_bool(event.get("submitted")),
        })
        # The generic semantic projection has no common UI gate for this
        # event.  Keep the exact command result in a dedicated component.
        result["validity_called"] = result["native_command_validity_called"]
        result["native_validity"] = result["native_command_validity"]
        result["native_rule_components"] = {
            "rules_schema": result["rules_schema"],
            "specific_validity_query_called": result["native_command_validity_called"],
            "executor_validity": result["native_command_validity"],
            "rival_state_verified": result["rival_state_verified"],
            "candidate_eligibility_available": result["candidate_eligibility_available"],
            "candidate_eligible": result["candidate_eligible"],
            "target_exists": result["target_exists"],
            "ui_war_allowed": result["ui_war_allowed"],
            "full_rules_complete": result["full_rules_complete"],
            "native_action_available": result["native_action_available"],
            "complete": (rules_schema == 3
                         and result["full_rules_complete"] is True
                         and result["native_action_available"] is True),
        }
        if rules_schema == 3:
            result["native_rule_components"].update({
                "full_rules_complete": result["full_rules_complete"],
                "native_action_available": result["native_action_available"],
            })
        active = result["rival_active"]
        result["relationship_state"] = {
            "rival_active": active if isinstance(active, bool) else None,
            "rival_since_date_raw": result["rival_since_date_raw"],
            "complete": isinstance(active, bool) and result["rival_state_verified"],
        }
        if (isinstance(result["rival_count"], int)
                and isinstance(result["max_rivals"], int)):
            result["resources"] = {
                "rivals": {
                    "current_count": result["rival_count"],
                    "max_count": result["max_rivals"],
                    "source": "native_rule",
                    "complete": True,
                },
                "diplomatic_power": {
                    "native_value_raw": result["diplomatic_power_raw"],
                    "source": "native_rule",
                    "complete": False,
                },
            }
        cost = result["diplomatic_power_cost_raw"]
        if (result["cost_query_called"] is True
                and event.get("action_id") == "remove_rival" and cost is not None):
            result["costs"] = {
                # R34F binds the native final-power integer to the actual
                # execution delta (581 -> 480 for cost_raw=101).  The known
                # item therefore has scale 1 and a verified diplomatic-power
                # unit; coverage remains partial because no claim is made
                # about additional costs.
                "status": "available",
                "items": [{
                    "resource": "diplomatic_power",
                    "amount_raw": cost,
                    "amount": cost,
                    "unit": "diplomatic_power",
                    "unit_verified": True,
                    "scale": 1,
                    "scale_verified": True,
                    "affordable": cost <= result["diplomatic_power_raw"],
                    "source": "native_rule_and_execution_consequence",
                    "complete": True,
                }],
                "complete": False,
                "coverage": {"status": "partial", "known_items": 1,
                             "additional_costs": "unknown", "complete": False,
                             "source": "native_rule_and_execution_consequence"},
            }
        return result

    @classmethod
    def _public_insult_costs(cls, action_id: str, event: dict) -> dict:
        """Project the verified Insult prestige cost into the common costs shape.

        R33 established the display scale from the native raw value and the
        saved prestige delta: 1000 raw units equal one displayed prestige.
        ``complete`` remains false because this evidence covers the known
        prestige item only; it does not assert that no other future cost exists.
        """

        if action_id not in _INSULT_ACTIONS or not isinstance(event, dict):
            return {"status": "unknown", "items": [], "complete": False}
        raw = cls._safe_int(event.get("prestige_cost_raw"), 0, 2147483647)
        if raw is None:
            return {
                "status": "unknown",
                "items": [],
                "complete": False,
                "coverage": {
                    "status": "unknown",
                    "known_items": 0,
                    "additional_costs": "unknown",
                    "complete": False,
                },
            }
        scale = 1000
        amount = raw // scale if raw % scale == 0 else None
        scale_verified = amount is not None
        item = {
            "resource": "prestige",
            "amount": amount,
            "amount_raw": raw,
            "unit": "prestige",
            "unit_verified": scale_verified,
            "scale": scale,
            "scale_verified": scale_verified,
            "source": "native_rule_and_save_effect",
            "complete": scale_verified,
        }
        return {
            "status": "available" if scale_verified else "partial",
            "items": [item],
            "complete": False,
            "coverage": {
                "status": "partial",
                "known_items": 1,
                "additional_costs": "unknown",
                "complete": False,
                "source": "native_rule_and_save_effect",
            },
        }

    @classmethod
    def _public_vassalization_costs(cls, action_id: str, event: dict) -> dict:
        """Project the verified prestige cost of Vassalization cancellation.

        The native field is a signed prestige delta.  A negative delta is a
        cost, so the public amount uses its absolute value.  Offer queries do
        not imply a zero cost and therefore retain an unknown cost result.
        """

        if action_id != "cancel_vassalization" or not isinstance(event, dict):
            return {"status": "unknown", "items": [], "complete": False}
        delta = cls._safe_int(event.get("cancel_prestige_delta_raw"),
                              -2147483648, 2147483647)
        scale = cls._safe_int(event.get("prestige_scale"), 1, 1000000)
        effect_allowed = cls._safe_bool(event.get("cancel_prestige_effect_allowed"))
        verified = (event.get("cancel_prestige_cost_verified") is True
                    and delta is not None and scale is not None
                    and effect_allowed is not None)
        if not verified:
            return {
                "status": "unknown", "items": [], "complete": False,
                "coverage": {"status": "unknown", "known_items": 0,
                              "additional_costs": "unknown", "complete": False},
            }
        raw_cost = max(0, -delta) if effect_allowed else 0
        exact = raw_cost % scale == 0
        item = {
            "resource": "prestige",
            "amount_raw": raw_cost,
            "amount": raw_cost // scale if exact else None,
            "unit": "prestige",
            "unit_verified": exact,
            "scale": scale,
            "scale_verified": True,
            "source": "native_rule",
            "complete": exact,
        }
        return {
            "status": "available" if exact else "partial",
            "items": [item],
            "complete": False,
            "coverage": {"status": "partial", "known_items": 1,
                          "additional_costs": "unknown", "complete": False,
                          "source": "native_rule"},
        }

    @classmethod
    def _public_declare_war_costs(
            cls, event: dict,
            codec: str = DEFAULT_NATIVE_TEXT_CODEC) -> dict:
        """Project the bounded default-payload Declare War cost observation.

        The native helper reports display calculations before a CB, war goal,
        or ally context is selected.  Only the stability-loss scale is
        identified by the current evidence; the other integers remain named
        raw components and are never presented as diplomatic power or a
        complete fee.
        """

        native_costs = event.get("native_costs") if isinstance(event, dict) else None
        if not isinstance(native_costs, dict):
            return {"status": "unknown", "items": [], "complete": False}
        stability_available = native_costs.get("stability_available") is True
        stability_raw = cls._safe_int(
            native_costs.get("stability_hit_raw"), -2147483648, 2147483647)
        stability_scale = cls._safe_int(native_costs.get("stability_scale"), 1, 1000000)
        warex_available = native_costs.get("warex_available") is True
        warex_raw = cls._safe_int(
            native_costs.get("warex_display_raw"), -2147483648, 2147483647)
        primary_available = native_costs.get("primary_available") is True
        primary_raw = cls._safe_int(
            native_costs.get("primary_raw"), -2147483648, 2147483647)
        secondary_available = native_costs.get("secondary_available") is True
        secondary_raw = cls._safe_int(
            native_costs.get("secondary_raw"), -2147483648, 2147483647)
        text_readable = native_costs.get("text_readable") is True
        native_text = cls._safe_native_text({
            "text_hex": native_costs.get("native_text_hex"),
            "text_readable": text_readable,
        }, codec)
        items = []
        if stability_available and stability_raw is not None and stability_scale == 1000:
            items.append({
                "resource": "stability_loss",
                "native_raw": stability_raw,
                "amount_raw": stability_raw,
                "amount": stability_raw / stability_scale,
                "unit": "stability_loss",
                "unit_verified": True,
                "scale": stability_scale,
                "scale_verified": True,
                "source": "native_rule",
                "complete": True,
            })
        return {
            "status": "partial",
            "items": items,
            "complete": False,
            "context": "default_parameters_unselected",
            "native_text": native_text,
            "native_text_decoded": native_text is not None,
            "native_text_truncated": native_costs.get("text_truncated") is True,
            "coverage": {
                "status": "partial",
                "known_items": len(items),
                "additional_costs": "unknown",
                "complete": False,
                "source": "native_rule",
            },
            "raw_components": {
                "stability_available": stability_available,
                "stability_hit_raw": stability_raw,
                "stability_scale": stability_scale,
                "warex_available": warex_available,
                "warex_display_raw": warex_raw,
                "primary_available": primary_available,
                "primary_raw": primary_raw,
                "secondary_available": secondary_available,
                "secondary_raw": secondary_raw,
                "native_text": native_text,
                "text_readable": text_readable,
                "text_decoded": native_text is not None,
                "text_truncated": native_costs.get("text_truncated") is True,
            },
        }

    @classmethod
    def _public_native_insult_candidate(cls, event: object,
                                        codec: str = DEFAULT_NATIVE_TEXT_CODEC) -> dict | None:
        """Reduce one bounded candidate event without exposing native storage."""

        if not isinstance(event, dict):
            return None
        if event.get("native_candidate_valid") is not None \
                and event.get("native_candidate_valid") is not True:
            return None
        insult_id = cls._safe_int(event.get("insult_id"), 0, 2147483647)
        if insult_id is None:
            return None
        encoded = event.get("text_hex", "")
        if (not isinstance(encoded, str) or len(encoded) > 1024
                or (len(encoded) % 2) != 0
                or re.fullmatch(r"[0-9a-fA-F]*", encoded) is None):
            return None
        text = cls._safe_native_text(event, codec)
        readable = event.get("text_readable")
        if readable is not None and not isinstance(readable, bool):
            return None
        truncated = event.get("text_truncated")
        if truncated is not None and not isinstance(truncated, bool):
            return None
        key = event.get("key")
        if key is not None and (not isinstance(key, str) or len(key) > 128):
            return None
        return {
            "insult_id": insult_id,
            "text_hex": encoded,
            "text_readable": readable is True,
            "text": text,
            "text_decoded": text is not None,
            "text_truncated": truncated is True,
            "key": key,
        }

    @classmethod
    def _valid_native_inspection(cls, event: object, action_id: str, actor: str,
                                 recipient: str, phase: str, expected_date: object,
                                 expected_query_id: str | None = None,
                                 expected_session_id: str | None = None) -> bool:
        if action_id in PEACE_ACTION_IDS:
            return cls._valid_native_peace_context_inspection(
                event, action_id, actor, recipient, phase, expected_date,
                expected_query_id, expected_session_id)
        if (action_id == "declare_war" and isinstance(event, dict)
                and event.get("event") == "native_declare_war_inspection"):
            # Keep the long-standing generic validator useful to offline
            # callers while the live query path uses the stricter identity-
            # bound Declare War validator below.
            return cls._valid_native_declare_war_inspection(
                event, action_id, actor, recipient, phase, expected_date)
        if not isinstance(event, dict):
            return False
        if any(event.get(field) != expected for field, expected in (
                ("event", "native_alliance_inspection"), ("action_id", action_id),
                ("actor", actor), ("recipient", recipient), ("phase", phase))):
            return False
        actual_date = cls._safe_int(event.get("date_raw"))
        wanted_date = cls._safe_int(expected_date)
        if actual_date is None or wanted_date is None or actual_date != wanted_date:
            return False
        if action_id in ("proclaim_guarantee", "revoke_guarantee"):
            if (event.get("family") != "guarantee"
                    or not isinstance(event.get("guarantee_active"), bool)
                    or event.get("guarantee_state_verified") is not True):
                return False
        if action_id in ("support_independence", "revoke_support_independence"):
            if (event.get("family") != "support_independence"
                    or not isinstance(event.get("support_independence_active"), bool)
                    or event.get("support_independence_state_verified") is not True):
                return False
        if action_id in ("ask_military_access", "cancel_military_access"):
            if (event.get("family") != "military_access"
                    or not isinstance(event.get("military_access_active"), bool)
                    or event.get("military_access_state_verified") is not True):
                return False
        if action_id in _VASSALIZATION_ACTIONS:
            if (event.get("family") != "vassalization"
                    or not isinstance(event.get("vassal_active"), bool)
                    or event.get("vassal_state_verified") is not True):
                return False
            for field in ("actor_is_overlord", "actor_is_subject"):
                if field in event and not isinstance(event.get(field), bool):
                    return False
            subject_type = event.get("subject_type")
            if (subject_type is not None
                    and (not isinstance(subject_type, str)
                         or not subject_type or len(subject_type) > 64)):
                return False
        score_available = event.get("score_available")
        if score_available is not None and not isinstance(score_available, bool):
            return False
        for field in ("acceptance_predicate_available", "native_would_accept",
                      "score_applicable", "diplomat_context_readable", "diplomat_required"):
            if event.get(field) is not None and not isinstance(event[field], bool):
                return False
        if action_id in ("improve_relations", "stop_improving_relations",
                         "build_spy_network", "stop_building_spy_network",
                         "proclaim_guarantee", "revoke_guarantee",
                         "cancel_vassalization"):
            # ImproveRelations, Spy Network, and Guarantee are single-party
            # actions. Their native query records must not expose an
            # acceptance score or counterparty predicate, even if an unrelated
            # event is nearby.
            for field in ("score_applicable", "score_available",
                          "acceptance_predicate_available"):
                if event.get(field) is not False:
                    return False
        if score_available is True:
            if (cls._safe_int(event.get("native_total_raw"), -2147483648, 2147483647) is None
                    or cls._safe_int(event.get("acceptance_threshold_raw"), -2147483648, 2147483647) is None):
                return False
        if event.get("acceptance_predicate_available") is True:
            if (action_id not in _NEGOTIATED_INITIATION_ACTIONS
                    or score_available is not True
                    or not isinstance(event.get("native_would_accept"), bool)):
                return False
        if event.get("diplomat_context_readable") is True:
            if (cls._safe_int(event.get("available_diplomat_count"), 0, 256) is None
                    or not isinstance(event.get("diplomat_required"), bool)):
                return False
        return True

    @classmethod
    def _valid_native_peace_context_inspection(
            cls, event: object, action_id: str, actor: str, recipient: str,
            phase: str, expected_date: object,
            expected_query_id: str | None = None,
            expected_session_id: str | None = None) -> bool:
        """Validate the QUERY1 peace context discovery event.

        This contract proves only that the native observer enumerated wars for
        the requested pair.  It deliberately does not accept roles, leaders,
        peace terms or offer-rule results as inferred values.
        """

        if (not isinstance(event, dict)
                or action_id not in PEACE_ACTION_IDS
                or event.get("event") != "native_peace_context_inspection"
                or event.get("family") != "peace"
                or event.get("action_id") != action_id
                or event.get("actor") != actor
                or event.get("recipient") != recipient
                or event.get("phase") != phase):
            return False
        actual_date = cls._safe_int(event.get("date_raw"))
        wanted_date = cls._safe_int(expected_date)
        if actual_date is None or wanted_date is None or actual_date != wanted_date:
            return False
        for field, expected in (("query_id", expected_query_id),
                                ("session_id", expected_session_id)):
            value = event.get(field)
            if (not isinstance(value, str) or not value or len(value) > 128
                    or (expected is not None and value != expected)):
                return False
        if (event.get("discovery") is not True
                or event.get("query_complete") is not True
                or not isinstance(event.get("enumeration_complete"), bool)
                or event.get("native_offer_inspected") is not False
                or event.get("full_rules_complete") is not False
                or event.get("submitted") is not False):
            return False
        wars = event.get("wars")
        if not isinstance(wars, list) or len(wars) > 32:
            return False
        war_id_pattern = r"war_[0-9a-f]{16}_[0-9a-f]{8}"
        for row in wars:
            if not isinstance(row, dict):
                return False
            war_id = row.get("war_id")
            if (not isinstance(war_id, str)
                    or re.fullmatch(war_id_pattern, war_id) is None
                    or row.get("identity_scope") != "observer_session"
                    or row.get("actor") != actor
                    or row.get("recipient") != recipient
                    or row.get("pair_at_war") is not True
                    or row.get("actor_war_role") is not None
                    or row.get("recipient_war_role") is not None
                    or row.get("roles_verified") is not False
                    or row.get("actor_is_war_leader") is not None
                    or row.get("recipient_is_war_leader") is not None
                    or row.get("leaders_verified") is not False
                    or row.get("context_complete") is not False):
                return False
        return True

    @classmethod
    def _valid_native_peace_offer_evaluation(cls, evaluation: object) -> bool:
        """Validate QUERY4's optional native score/factor object.

        The object is optional for backwards compatibility with the R38B
        producer.  Its raw score and factor values remain bounded native
        observations; this validator does not infer a unit or a response.
        """

        if not isinstance(evaluation, dict):
            return False
        for field in ("called", "score_available",
                      "aggregate_score_available",
                      "factor_capture_truncated", "factors_available",
                      "factors_complete", "complete"):
            if not isinstance(evaluation.get(field), bool):
                return False
        if evaluation.get("complete") is not False:
            return False
        if evaluation.get("score_representation") != "signed_int32":
            return False
        if cls._safe_int(evaluation.get("score_raw"),
                         -2147483648, 2147483647) is None:
            return False
        if cls._safe_int(evaluation.get("aggregate_score_raw"),
                         -2147483648, 2147483647) is None:
            return False
        factor_count = cls._safe_int(evaluation.get("factor_native_count"), 0, 4096)
        if factor_count is None:
            return False
        items = evaluation.get("items")
        if (not isinstance(items, list)
                or len(items) > _MAX_PEACE_EVALUATION_FACTORS
                or len(items) > factor_count):
            return False
        if evaluation.get("called") is False and (
                evaluation.get("score_available") is True
                or evaluation.get("aggregate_score_available") is True
                or evaluation.get("factors_available") is True
                or factor_count != 0 or items):
            return False
        if evaluation.get("factors_complete") is True:
            if (evaluation.get("called") is not True
                    or evaluation.get("factors_available") is not True
                    or evaluation.get("factor_capture_truncated") is not False
                    or len(items) != factor_count):
                return False
        for item in items:
            if not isinstance(item, dict):
                return False
            identifier = item.get("native_identifier")
            if identifier is not None and (
                    not isinstance(identifier, str) or len(identifier) > 128):
                return False
            identifier_verified = item.get("identifier_verified")
            if not isinstance(identifier_verified, bool):
                return False
            if identifier_verified and (not isinstance(identifier, str)
                                        or not identifier):
                return False
            if (cls._safe_int(item.get("native_value"),
                              -2147483648, 2147483647) is None
                    or not isinstance(item.get("native_flag"), bool)
                    or not isinstance(item.get("text_hex"), str)
                    or len(item["text_hex"]) > 1024
                    or len(item["text_hex"]) % 2
                    or re.fullmatch(r"[0-9a-fA-F]*", item["text_hex"])
                    is None
                    or not isinstance(item.get("text_readable"), bool)
                    or not isinstance(item.get("text_truncated"), bool)
                    or not isinstance(item.get("row_binding_verified"), bool)):
                return False
            if evaluation.get("factors_complete") is True and (
                    item.get("identifier_verified") is not True
                    or item.get("row_binding_verified") is not True
                    or item.get("text_readable") is not True
                    or item.get("text_truncated") is not False):
                return False
        return True

    @classmethod
    def _peace_wrapper_rule_state(cls, event: object) -> str:
        """Classify the optional four-proof wrapper-rule contract.

        Older B-build events do not contain these fields and remain a valid
        partial observation.  A producer that emits only part of the proof,
        or claims ``full_rules_complete`` without reporting all four proof
        fields, is malformed rather than implicitly complete.  The completion
        flag describes the completeness of the proof *observation*; it does
        not describe the result of the wrapper gate.  Consequently a complete
        observation may legitimately contain ``native_wrapper_gate=False``
        while the identity and payload checks are true.
        """

        if not isinstance(event, dict):
            return "invalid"
        fields = (
            "native_wrapper_gate_checked", "native_wrapper_gate",
            "wrapper_identity_verified", "wrapper_payload_unchanged")
        present = [field in event for field in fields]
        if not any(present):
            return ("missing" if event.get("full_rules_complete") is False
                    else "invalid")
        if not all(present) or any(not isinstance(event.get(field), bool)
                                   for field in fields):
            return "invalid"
        if event.get("full_rules_complete") is not True:
            return "invalid"
        verified = all(event.get(field) is True for field in fields)
        return "verified" if verified else "failed"

    @classmethod
    def _valid_native_peace_money_offer_inspection(
            cls, event: object, action_id: str, actor: str, recipient: str,
            phase: str, expected_date: object, expected_selection: dict,
            expected_query_id: str | None = None,
            expected_session_id: str | None = None,
            *, require_wrapper_rule: bool = False) -> bool:
        """Validate a family-bound money inspection in either direction."""

        expected_direction = (expected_selection.get("direction", "demand")
                              if isinstance(expected_selection, dict) else None)
        expected_payer = actor if expected_direction == "offer" else recipient
        expected_claimant = recipient if expected_direction == "offer" else actor
        if (not isinstance(expected_selection, dict)
                or expected_direction not in ("demand", "offer")
                or expected_selection.get("payer") != expected_payer
                or expected_selection.get("claimant") != expected_claimant
                or cls._safe_int(expected_selection.get("amount_raw"),
                                 1, 2147483647) is None):
            return False
        if (not isinstance(event, dict)
                or event.get("event") != "native_peace_money_offer_inspection"
                or action_id != "demand_ducats"
                or event.get("action_id") != action_id
                or event.get("family") != "peace"
                or event.get("actor") != actor
                or event.get("recipient") != recipient):
            return False
        common = dict(event)
        common["event"] = "native_peace_empty_offer_inspection"
        common["action_id"] = "white_peace"
        common["direction"] = event.get(
            "direction", event.get("native_money", {}).get(
                "direction", expected_direction))
        if not cls._valid_native_peace_empty_offer_inspection(
                common, "white_peace", actor, recipient, phase, expected_date,
                expected_selection.get("war_id"), expected_query_id,
                expected_session_id, require_wrapper_rule=require_wrapper_rule,
                expected_direction=expected_direction):
            return False
        money = event.get("native_money")
        if not isinstance(money, dict):
            return False
        required_bool = (
            "query_complete", "currency_scale_verified", "amount_within_limit",
            "setter_called", "source_readback_matches", "action_copy_verified",
            "parameters_matched", "direction_verified")
        if any(not isinstance(money.get(field), bool) for field in required_bool):
            return False
        if (money.get("query_complete") is not True
                or money.get("currency_scale") != 1000
                or money.get("currency_precision_raw") != 100
                or money.get("currency_scale_verified") is not True
                or money.get("ceiling_input_raw") != 100000
                or money.get("direction") != expected_direction
                or money.get("direction_verified") is not True
                or money.get("payer") != expected_payer
                or money.get("claimant") != expected_claimant):
            return False
        expected_amount = expected_selection["amount_raw"]
        if (not isinstance(expected_amount, int)
                or isinstance(expected_amount, bool)
                or expected_amount <= 0
                or expected_amount % 100 != 0
                or money.get("requested_amount_raw") != expected_amount
                or money.get("action_copy_verified") is not True):
            return False
        ceiling = cls._safe_int(
            money.get("currency_ceiling_raw"), 0, 2147483647)
        source_amount = cls._safe_int(
            money.get("source_amount_raw"), 0, 2147483647)
        action_amount = cls._safe_int(
            money.get("action_amount_raw"), 0, 2147483647)
        if ceiling is None or source_amount is None or action_amount is None:
            return False
        if money["amount_within_limit"]:
            if (expected_amount > ceiling
                    or not money["setter_called"]
                    or source_amount != expected_amount
                    or action_amount != source_amount
                    or not money["source_readback_matches"]
                    or not money["parameters_matched"]
                    or not money["action_copy_verified"]):
                return False
        else:
            if (expected_amount <= ceiling
                    or money["setter_called"]
                    or source_amount != 0
                    or action_amount != 0
                    or money["source_readback_matches"]
                    or money["parameters_matched"]):
                return False
        evaluation = event.get("native_evaluation")
        if (not isinstance(evaluation, dict)
                or not cls._valid_native_peace_offer_evaluation(evaluation)):
            return False
        if (money["parameters_matched"] is not True
                or event.get("native_validity") is False):
            if (evaluation.get("called") is not False
                    or evaluation.get("score_available") is not False
                    or evaluation.get("aggregate_score_available") is not False
                    or evaluation.get("factor_native_count") != 0
                    or evaluation.get("items") != []):
                return False
        elif evaluation.get("called") is not True:
            return False
        return True

    @classmethod
    def _valid_native_peace_empty_offer_inspection(
            cls, event: object, action_id: str, actor: str, recipient: str,
            phase: str, expected_date: object, expected_war_id: str,
            expected_query_id: str | None = None,
            expected_session_id: str | None = None,
            *, require_wrapper_rule: bool = False,
            expected_direction: str = "demand") -> bool:
        """Validate the read-only empty-offer inspection contract."""

        if (not isinstance(event, dict)
                or action_id != "white_peace"
                or event.get("event") != "native_peace_empty_offer_inspection"
                or event.get("family") != "peace"
                or event.get("action_id") != action_id
                or event.get("actor") != actor
                or event.get("recipient") != recipient
                or event.get("phase") != phase
                or event.get("war_id") != expected_war_id
                or event.get("identity_scope") != "observer_session"):
            return False
        if expected_direction not in ("demand", "offer"):
            return False
        # QUERY4 predates explicit direction and therefore has no direction
        # field.  Treat a missing field as the legacy demand direction, while
        # QUERY7 offer events must carry the explicit offer value.
        if event.get("direction", "demand") != expected_direction:
            return False
        if (not isinstance(expected_war_id, str)
                or re.fullmatch(_PEACE_WAR_ID_PATTERN, expected_war_id) is None):
            return False
        actual_date = cls._safe_int(event.get("date_raw"))
        wanted_date = cls._safe_int(expected_date)
        if actual_date is None or wanted_date is None or actual_date != wanted_date:
            return False
        for field, expected in (("query_id", expected_query_id),
                                ("session_id", expected_session_id)):
            value = event.get(field)
            if (not isinstance(value, str) or not value or len(value) > 128
                    or (expected is not None and value != expected)):
                return False
        wrapper_state = cls._peace_wrapper_rule_state(event)
        if (wrapper_state == "invalid"
                or (require_wrapper_rule and wrapper_state == "missing")):
            return False
        if (event.get("query_complete") is not True
                or event.get("native_offer_inspected") is not True
                or event.get("pair_at_war") is not True
                or event.get("unique_shared_war") is not True
                or event.get("offer_constructed") is not True
                or event.get("action_constructed") is not True
                or event.get("participant_copy_verified") is not True
                or event.get("offer_identity_verified") is not True
                or event.get("object_unchanged") is not True
                or event.get("cleanup_verified") is not True
                or event.get("validity_called") is not True
                or event.get("common_gate_checked") is not True
                or event.get("initiation_gate_checked") is not True
                or event.get("reasons_complete") is not False
                or event.get("submitted") is not False):
            return False
        for field in ("native_validity", "common_action_gate", "initiation_gate"):
            if not isinstance(event.get(field), bool):
                return False
        for prefix in ("native", "common", "send"):
            encoded = event.get(f"{prefix}_diagnostic_hex")
            if (not isinstance(encoded, str) or len(encoded) > 4096
                    or len(encoded) % 2
                    or re.fullmatch(r"[0-9a-fA-F]*", encoded) is None):
                return False
            readable_field = (
                "diagnostic_readable" if prefix == "native"
                else f"{prefix}_diagnostic_readable")
            truncated_field = (
                "diagnostic_truncated" if prefix == "native"
                else f"{prefix}_diagnostic_truncated")
            for field in (readable_field, truncated_field):
                if not isinstance(event.get(field), bool):
                    return False
        if "native_evaluation" in event:
            evaluation = event.get("native_evaluation")
            if (not cls._valid_native_peace_offer_evaluation(evaluation)
                    or (event.get("native_validity") is False
                        and evaluation.get("called") is not False)):
                return False
        if ("native_war_context" in event
                and not cls._valid_native_peace_war_context(
                    event["native_war_context"], actor, recipient,
                    event.get("direction", "demand"))):
            return False
        if ("native_payload" in event
                and not cls._valid_native_peace_payload(event["native_payload"])):
            return False
        return True

    @classmethod
    def _valid_native_peace_province_offer_inspection(
            cls, event: object, action_id: str, actor: str, recipient: str,
            phase: str, expected_date: object, expected_selection: dict,
            expected_query_id: str | None = None,
            expected_session_id: str | None = None,
            *, require_wrapper_rule: bool = False) -> bool:
        """Validate the family-bound QUERY6 province-term inspection."""
        expected_direction = (expected_selection.get("direction", "demand")
                              if isinstance(expected_selection, dict) else None)
        if (not isinstance(expected_selection, dict)
                or not isinstance(expected_selection.get("war_id"), str)
                or re.fullmatch(_PEACE_WAR_ID_PATTERN,
                                expected_selection["war_id"]) is None
                or expected_direction not in ("demand", "offer")
                or not isinstance(expected_selection.get("province_ids"), list)
                or not 0 <= len(expected_selection["province_ids"]) <= 16
                or (expected_selection.get("beneficiary") is not None
                    and (not isinstance(expected_selection.get("beneficiary"), str)
                         or re.fullmatch(r"[A-Z0-9]{3}",
                                         expected_selection["beneficiary"]) is None))):
            return False
        expected_ids = expected_selection["province_ids"]
        if (any(cls._safe_int(value, 1, 2147483647) is None
                for value in expected_ids)
                or len(set(expected_ids)) != len(expected_ids)):
            return False
        if (not isinstance(event, dict)
                or event.get("event") != "native_peace_province_offer_inspection"
                or action_id != "cede_province"
                or event.get("action_id") != action_id
                or event.get("family") != "peace"
                or event.get("actor") != actor
                or event.get("recipient") != recipient
                or event.get("phase") != phase
                or event.get("war_id") != expected_selection["war_id"]
                or event.get("identity_scope") != "observer_session"):
            return False
        actual_date = cls._safe_int(event.get("date_raw"))
        wanted_date = cls._safe_int(expected_date)
        if actual_date is None or wanted_date is None or actual_date != wanted_date:
            return False
        for field, expected in (("query_id", expected_query_id),
                                ("session_id", expected_session_id)):
            value = event.get(field)
            if (not isinstance(value, str) or not value or len(value) > 128
                    or (expected is not None and value != expected)):
                return False
        common = dict(event)
        common["event"] = "native_peace_empty_offer_inspection"
        common["action_id"] = "white_peace"
        common["direction"] = event.get(
            "direction", event.get("native_provinces", {}).get(
                "direction", expected_direction))
        if not cls._valid_native_peace_empty_offer_inspection(
                common, "white_peace", actor, recipient, phase, expected_date,
                expected_selection["war_id"], expected_query_id,
                expected_session_id, require_wrapper_rule=require_wrapper_rule,
                expected_direction=expected_direction):
            return False
        native = event.get("native_provinces")
        if not isinstance(native, dict):
            return False
        bool_fields = (
            "query_complete", "candidate_enumeration_complete",
            "selection_requested", "requested_candidates_found",
            "toggle_called", "parameters_matched", "selection_copy_verified",
            "selected_term_records_complete", "direction_verified")
        if any(not isinstance(native.get(field), bool) for field in bool_fields):
            return False
        if (native.get("query_complete") is not True
                or native.get("candidate_enumeration_complete") is not True
                or native.get("direction") != expected_direction
                or native.get("direction_verified") is not True):
            return False
        candidate_count = cls._safe_int(native.get("candidate_count"), 0, 512)
        candidates = native.get("candidates")
        if (candidate_count is None or not isinstance(candidates, list)
                or len(candidates) > 512 or candidate_count != len(candidates)):
            return False
        seen_candidates: set[int] = set()
        for row in candidates:
            if not isinstance(row, dict):
                return False
            province_id = cls._safe_int(row.get("province_id"), 1, 2147483647)
            beneficiary = row.get("beneficiary")
            if (province_id is None or province_id in seen_candidates
                    or not isinstance(beneficiary, str)
                    or re.fullmatch(r"[A-Z0-9]{3}", beneficiary) is None
                    or not isinstance(row.get("selected"), bool)
                    or not isinstance(row.get("name_hex"), str)
                    or len(row["name_hex"]) > 1024
                    or len(row["name_hex"]) % 2
                    or re.fullmatch(r"[0-9a-fA-F]*", row["name_hex"]) is None
                    or not isinstance(row.get("name_readable"), bool)
                    or not isinstance(row.get("name_truncated"), bool)
                    or not isinstance(row.get("native_selectability_checked"), bool)
                    or (row.get("native_selectable") is not None
                        and not isinstance(row.get("native_selectable"), bool))):
                return False
            seen_candidates.add(province_id)
        requested_ids = native.get("requested_province_ids")
        if (not isinstance(requested_ids, list)
                or len(requested_ids) > 16
                or any(cls._safe_int(value, 1, 2147483647) is None
                       for value in requested_ids)
                or requested_ids != expected_selection["province_ids"]
                or native.get("requested_beneficiary") != expected_selection.get(
                    "beneficiary")):
            return False
        if len(set(requested_ids)) != len(requested_ids):
            return False
        selected_ids = native.get("selected_province_ids")
        if (not isinstance(selected_ids, list) or len(selected_ids) > 512
                or any(cls._safe_int(value, 1, 2147483647) is None
                       for value in selected_ids)):
            return False
        if len(set(selected_ids)) != len(selected_ids):
            return False
        selected_beneficiary = native.get("selected_beneficiary")
        if (selected_beneficiary is not None
                and (not isinstance(selected_beneficiary, str)
                     or re.fullmatch(r"[A-Z0-9]{3}", selected_beneficiary) is None)):
            return False
        if (cls._safe_int(native.get("toggle_call_count"), 0, 512) is None
                or native.get("toggle_called")
                != (native["toggle_call_count"] > 0)):
            return False
        reason_code = native.get("reason_code")
        if reason_code is not None and reason_code not in {
                "NATIVE_PEACE_PROVINCE_CANDIDATE_ABSENT",
                "NATIVE_PEACE_PROVINCE_SELECTION_UNAVAILABLE",
                "NATIVE_PEACE_PROVINCE_SELECTION_MISMATCH"}:
            return False
        requested_ids = expected_selection["province_ids"]
        if not requested_ids:
            if (native.get("selection_requested") is not False
                    or native.get("requested_candidates_found") is not False
                    or native.get("parameters_matched") is not False
                    or native.get("toggle_called") is not False
                    or native.get("toggle_call_count") != 0
                    or selected_ids
                    or selected_beneficiary is not None
                    or native.get("selection_copy_verified") is not True):
                return False
        else:
            if native.get("selection_requested") is not True:
                return False
            if native.get("parameters_matched") is True:
                if (set(selected_ids) != set(requested_ids)
                        or selected_beneficiary != expected_selection.get("beneficiary")
                        or native.get("selection_copy_verified") is not True):
                    return False
        delta = native.get("selection_delta_raw")
        if delta is not None and cls._safe_int(delta, -2147483648, 2147483647) is None:
            return False
        evaluation = event.get("native_evaluation")
        if evaluation is not None and not cls._valid_native_peace_offer_evaluation(
                evaluation):
            return False
        if (not requested_ids or native.get("parameters_matched") is not True) \
                and isinstance(evaluation, dict):
            if (evaluation.get("called") is not False
                    or evaluation.get("score_available") is not False
                    or evaluation.get("aggregate_score_available") is not False
                    or evaluation.get("factor_native_count") != 0
                    or evaluation.get("items") != []):
                return False
        return True

    @classmethod
    def _valid_native_peace_combined_offer_inspection(
            cls, event: object, action_id: str, actor: str, recipient: str,
            phase: str, expected_date: object, expected_selection: dict,
            expected_query_id: str | None = None,
            expected_session_id: str | None = None,
            *, require_wrapper_rule: bool = False) -> bool:
        """Validate one native offer carrying money and provinces together.

        The two nested term records are checked against the same event and the
        same war/date identity.  This deliberately does not combine results
        from the older money and province queries: both records and the
        serialized payload must come from the one aggregate QUERY7 event.
        """

        if (not isinstance(expected_selection, dict)
                or action_id not in ("demand_ducats", "cede_province")
                or expected_selection.get("action_id") != action_id
                or not isinstance(expected_selection.get("war_id"), str)
                or re.fullmatch(_PEACE_WAR_ID_PATTERN,
                                expected_selection["war_id"]) is None
                or expected_selection.get("direction") not in ("demand", "offer")
                or cls._safe_int(expected_selection.get("amount_raw"),
                                 1, 2147483647) is None
                or not isinstance(expected_selection.get("province_ids"), list)
                or not 1 <= len(expected_selection["province_ids"]) <= 16
                or any(cls._safe_int(value, 1, 2147483647) is None
                       for value in expected_selection["province_ids"])
                or len(set(expected_selection["province_ids"]))
                != len(expected_selection["province_ids"])
                or not isinstance(expected_selection.get("beneficiary"), str)
                or re.fullmatch(r"[A-Z0-9]{3}",
                                expected_selection["beneficiary"]) is None):
            return False
        direction = expected_selection["direction"]
        expected_payer = actor if direction == "offer" else recipient
        expected_claimant = recipient if direction == "offer" else actor
        if (expected_selection.get("payer") != expected_payer
                or expected_selection.get("claimant") != expected_claimant):
            return False
        if (not isinstance(event, dict)
                or event.get("event") != "native_peace_combined_offer_inspection"
                or event.get("family") != "peace"
                or event.get("action_id") != action_id
                or event.get("actor") != actor
                or event.get("recipient") != recipient
                or event.get("phase") != phase
                or event.get("war_id") != expected_selection["war_id"]
                or event.get("identity_scope") != "observer_session"
                or event.get("direction") != direction
                or not isinstance(event.get("full_rules_complete"), bool)
                or event.get("reasons_complete") is not False
                or event.get("submitted") is not False):
            return False

        # Reuse the already strict common proof and each term validator against
        # this one event.  The synthetic event names are local validation views
        # and never escape to the public projection.
        common = dict(event)
        common["event"] = "native_peace_empty_offer_inspection"
        common["action_id"] = "white_peace"
        if not cls._valid_native_peace_empty_offer_inspection(
                common, "white_peace", actor, recipient, phase, expected_date,
                expected_selection["war_id"], expected_query_id,
                expected_session_id, require_wrapper_rule=require_wrapper_rule,
                expected_direction=direction):
            return False

        money_event = dict(event)
        money_event["event"] = "native_peace_money_offer_inspection"
        money_event["action_id"] = "demand_ducats"
        money_selection = {
            "war_id": expected_selection["war_id"],
            "direction": direction,
            "amount_raw": expected_selection["amount_raw"],
            "payer": expected_payer,
            "claimant": expected_claimant,
        }
        # Evaluation is independently acknowledged.  A combined event without
        # that ACK is still a valid constructor/term observation; use a local
        # empty evaluation only to exercise the established money shape.
        if "native_evaluation" not in money_event:
            money_event["native_evaluation"] = {
                "called": False, "score_available": False,
                "aggregate_score_available": False,
                "factor_capture_truncated": False, "factors_available": False,
                "factors_complete": False, "complete": False,
                "score_representation": "signed_int32", "score_raw": 0,
                "aggregate_score_raw": 0, "factor_native_count": 0, "items": [],
            }
        if not cls._valid_native_peace_money_offer_inspection(
                money_event, "demand_ducats", actor, recipient, phase,
                expected_date, money_selection, expected_query_id,
                expected_session_id, require_wrapper_rule=require_wrapper_rule):
            return False

        province_event = dict(event)
        province_event["event"] = "native_peace_province_offer_inspection"
        province_event["action_id"] = "cede_province"
        province_selection = {
            "war_id": expected_selection["war_id"],
            "direction": direction,
            "province_ids": list(expected_selection["province_ids"]),
            "beneficiary": expected_selection["beneficiary"],
        }
        if not cls._valid_native_peace_province_offer_inspection(
                province_event, "cede_province", actor, recipient, phase,
                expected_date, province_selection, expected_query_id,
                expected_session_id, require_wrapper_rule=require_wrapper_rule):
            return False

        payload = event.get("native_payload")
        if (not cls._valid_native_peace_payload(payload)
                or payload.get("serialized_fields_complete") is not True
                or payload.get("source_copy_equal") is not True
                or payload.get("serialized_fields_unchanged") is not True
                or payload.get("selected_term_count", 0) < 2):
            return False
        return True

    @classmethod
    def _valid_native_declare_war_inspection(
            cls, event: object, action_id: str, actor: str, recipient: str,
            phase: str, expected_date: object,
            expected_query_id: str | None = None,
            expected_session_id: str | None = None,
            expected_selection: dict | None = None) -> bool:
        """Validate the default or selected Declare War query contract.

        QUERY1 reports only the default action object.  QUERY3 adds a
        family-bound CB/province/beneficiary selection and must echo every
        requested parameter before its rule booleans can be consumed.
        """

        if (not isinstance(event, dict)
                or event.get("event") != "native_declare_war_inspection"
                or action_id != "declare_war"
                or event.get("action_id") != action_id
                or event.get("family") != "declare_war"
                or event.get("actor") != actor
                or event.get("recipient") != recipient
                or event.get("phase") != phase):
            return False
        actual_date = cls._safe_int(event.get("date_raw"))
        wanted_date = cls._safe_int(expected_date)
        if actual_date is None or wanted_date is None or actual_date != wanted_date:
            return False
        for field, expected in (("query_id", expected_query_id),
                                ("session_id", expected_session_id)):
            value = event.get(field)
            if (not isinstance(value, str) or not value or len(value) > 128
                    or (expected is not None and value != expected)):
                return False
        bool_fields = (
            "ui_selection_checked", "native_visibility",
            "ui_enabled_gate_checked", "common_action_gate",
            "validity_called", "native_validity",
            "initiation_gate_checked", "initiation_gate",
            "diagnostic_readable", "diagnostic_truncated", "submitted",
            "score_applicable", "parameter_context_complete",
            "native_default_payload", "candidate_context_complete",
            "full_rules_complete",
        )
        if any(not isinstance(event.get(field), bool) for field in bool_fields):
            return False
        selection_requested = expected_selection is not None
        if selection_requested:
            if (event.get("selection_requested") is not True
                    or not isinstance(event.get("selection_matched"), bool)
                    or cls._safe_int(event.get("selection_match_count"), 0, 4096) is None):
                return False
            if (event.get("requested_casus_belli") != expected_selection["casus_belli"]
                    or event.get("requested_province_id") != expected_selection["province_id"]
                    or event.get("requested_beneficiary") != expected_selection["beneficiary"]):
                return False
            if (not isinstance(event.get("requested_casus_belli"), str)
                    or re.fullmatch(r"[A-Za-z0-9_]{1,128}",
                                    event["requested_casus_belli"]) is None
                    or cls._safe_int(event.get("requested_province_id"),
                                     -2147483648, 2147483647) is None
                    or (event.get("requested_province_id") != -1
                        and event.get("requested_province_id") <= 0)
                    or (not isinstance(event.get("requested_beneficiary"), str)
                        or (event["requested_beneficiary"] != "---"
                            and re.fullmatch(r"[A-Z]{3}",
                                             event["requested_beneficiary"]) is None))):
                return False
            matched = event["selection_matched"]
            match_count = event["selection_match_count"]
            if matched:
                if (match_count < 1
                        or event.get("parameter_context_complete") is not True
                        or event.get("candidate_context_complete") is not True
                        or event.get("full_rules_complete") is not True
                        or event.get("native_default_payload") is not (
                            expected_selection["casus_belli"] == "no_casus_belli")):
                    return False
            elif (match_count != 0
                  or event.get("parameter_context_complete") is not False
                  or event.get("candidate_context_complete") is not False
                  or event.get("full_rules_complete") is not False):
                return False
        else:
            # A QUERY1 result must not be reused as proof for an explicit
            # QUERY3 selection.  Older producers omit selection fields;
            # schema-compatible default events may explicitly mark false.
            if "selection_requested" in event and event.get("selection_requested") is not False:
                return False
            if (event.get("submitted") is not False
                    or event.get("score_applicable") is not False
                    or event.get("parameter_context_complete") is not False
                    or event.get("native_default_payload") is not True
                    or event.get("candidate_context_complete") is not False
                    or event.get("full_rules_complete") is not False):
                return False
        encoded = event.get("native_diagnostic_hex")
        if (not isinstance(encoded, str) or len(encoded) > 4096
                or len(encoded) % 2
                or re.fullmatch(r"[0-9a-fA-F]*", encoded) is None):
            return False
        if "native_costs" in event:
            native_costs = event.get("native_costs")
            if not isinstance(native_costs, dict):
                return False
            if (native_costs.get("called") is not True
                    or native_costs.get("action_unchanged") is not True
                    or native_costs.get("complete") is not False):
                return False
            for field in (
                    "stability_available", "warex_available",
                    "primary_available", "secondary_available",
                    "text_readable", "text_truncated"):
                if not isinstance(native_costs.get(field), bool):
                    return False
            for field in (
                    "stability_hit_raw", "warex_display_raw", "primary_raw",
                    "secondary_raw"):
                if (isinstance(native_costs.get(field), bool)
                        or cls._safe_int(native_costs.get(field),
                                        -2147483648, 2147483647) is None):
                    return False
            if (isinstance(native_costs.get("stability_scale"), bool)
                    or cls._safe_int(native_costs.get("stability_scale"),
                                    1, 1000000) != 1000):
                return False
            cost_text = native_costs.get("native_text_hex")
            if (not isinstance(cost_text, str) or len(cost_text) > 1024
                    or len(cost_text) % 2
                    or re.fullmatch(r"[0-9a-fA-F]*", cost_text) is None):
                return False
        candidates = event.get("candidates")
        enumeration_fields = (
            "candidate_enumeration_called", "candidate_enumeration_complete",
            "candidate_native_count", "candidate_capture_truncated",
            "candidate_cleanup_verified")
        has_enumeration = any(field in event for field in enumeration_fields)
        if not isinstance(candidates, list) or len(candidates) > 64:
            return False
        if not has_enumeration:
            return not candidates
        if (not isinstance(event.get("candidate_enumeration_called"), bool)
                or not isinstance(event.get("candidate_enumeration_complete"), bool)
                or not isinstance(event.get("candidate_capture_truncated"), bool)
                or not isinstance(event.get("candidate_cleanup_verified"), bool)
                or isinstance(event.get("candidate_native_count"), bool)
                or not isinstance(event.get("candidate_native_count"), int)
                or not 0 <= event["candidate_native_count"] <= 4096):
            return False
        seen_indexes: set[int] = set()
        candidate_matches_selection = False
        for candidate in candidates:
            if not isinstance(candidate, dict):
                return False
            index = candidate.get("candidate_index")
            if (isinstance(index, bool) or not isinstance(index, int)
                    or index < 0 or index in seen_indexes):
                return False
            seen_indexes.add(index)
            discriminator = candidate.get("native_discriminator")
            if (isinstance(discriminator, bool) or not isinstance(discriminator, int)
                    or discriminator != 0x165):
                return False
            group = candidate.get("metadata_group_raw")
            if isinstance(group, bool) or not isinstance(group, int):
                return False
            metadata_hex = candidate.get("native_metadata_hex")
            if (not isinstance(metadata_hex, str) or len(metadata_hex) > 1024
                    or len(metadata_hex) % 2
                    or re.fullmatch(r"[0-9a-fA-F]*", metadata_hex) is None):
                return False
            for field in ("metadata_readable", "metadata_text_readable",
                          "metadata_text_truncated"):
                if not isinstance(candidate.get(field), bool):
                    return False
            if candidate.get("identifier_verified") is not False:
                return False
            if selection_requested:
                # QUERY3 keeps the complete enumeration in the event even
                # when one requested tuple is selected (or no tuple matches).
                # The selected clone is bound by the request echo,
                # selection_match_count and parameter-context flags; each
                # enumerated candidate only needs its own identifier proof.
                # Requiring every enumeration row to equal the requested
                # tuple incorrectly rejected the real R36E events, which
                # contain twelve rows alongside the single matched clone.
                candidate_cb = candidate.get("casus_belli_key")
                target_province = candidate.get("target_province_id")
                candidate_beneficiary = candidate.get("beneficiary_tag")
                if (not isinstance(candidate_cb, str)
                        or re.fullmatch(r"[A-Za-z0-9_]{1,128}", candidate_cb) is None
                        or candidate.get("casus_belli_key_verified") is not True
                        or isinstance(target_province, bool)
                        or not isinstance(target_province, int)
                        or not (-1 == target_province
                                 or 1 <= target_province <= 2147483647)
                        or candidate.get("province_identifier_verified") is not True
                        or not isinstance(candidate_beneficiary, str)
                        or (candidate_beneficiary != "---"
                            and re.fullmatch(r"[A-Z]{3}", candidate_beneficiary) is None)
                        or candidate.get("beneficiary_identifier_verified") is not True):
                    return False
                # The native enumeration uses ``---`` for the actor's own
                # beneficiary (for example requested beneficiary FRA in an
                # FRA query).  Keep one candidate-row binding in addition to
                # the request echo and native selected-clone proof; the
                # remaining rows are the other legal candidates.
                expected_candidate_beneficiaries = (
                    {"---", expected_selection["beneficiary"]}
                    if expected_selection["beneficiary"] == actor
                    else {expected_selection["beneficiary"]})
                if (candidate_cb == expected_selection["casus_belli"]
                        and target_province == expected_selection["province_id"]
                        and candidate_beneficiary in expected_candidate_beneficiaries):
                    candidate_matches_selection = True
        if selection_requested and matched and not candidates:
            return False
        if (selection_requested
                and expected_selection["casus_belli"] != "no_casus_belli"
                and matched and not candidate_matches_selection):
            return False
        if selection_requested and not matched and candidate_matches_selection:
            return False
        return True

    @classmethod
    def _valid_native_rival_inspection(cls, event: object, action_id: str,
                                       actor: str, recipient: str, phase: str,
                                       expected_date: object,
                                       expected_query_id: str | None = None,
                                       expected_session_id: str | None = None) -> bool:
        """Validate the narrow R34 countrycommands Rival query event."""

        if (not isinstance(event, dict)
                or action_id not in ("set_rival", "remove_rival")
                or event.get("event") != "native_rival_inspection"
                or event.get("action_id") != action_id
                or event.get("family") != "rival"
                or event.get("actor") != actor
                or event.get("recipient") != recipient
                or event.get("phase") != phase):
            return False
        actual_date = cls._safe_int(event.get("date_raw"))
        wanted_date = cls._safe_int(expected_date)
        if actual_date is None or wanted_date is None or actual_date != wanted_date:
            return False
        query_id = event.get("query_id")
        session_id = event.get("session_id")
        if (not isinstance(query_id, str) or not query_id
                or len(query_id) > 128
                or not isinstance(session_id, str) or not session_id
                or len(session_id) > 128
                or (expected_query_id is not None and query_id != expected_query_id)
                or (expected_session_id is not None and session_id != expected_session_id)):
            return False
        if (event.get("native_command_validity_called") is not True
                or not isinstance(event.get("native_command_validity"), bool)
                or event.get("rival_state_verified") is not True
                or not isinstance(event.get("rival_active"), bool)):
            return False
        since = event.get("rival_since_date_raw")
        if since is not None and cls._safe_int(since, -2147483648, 2147483647) is None:
            return False
        for field in ("rival_count", "max_rivals"):
            if cls._safe_int(event.get(field), 0, 1000000) is None:
                return False
        if cls._safe_int(event.get("diplomatic_power_raw"), -2147483648, 2147483647) is None:
            return False
        if not isinstance(event.get("at_war"), bool):
            return False
        encoded = event.get("native_diagnostic_hex")
        if (not isinstance(encoded, str) or len(encoded) > 4096
                or len(encoded) % 2
                or re.fullmatch(r"[0-9a-fA-F]*", encoded) is None):
            return False
        if (not isinstance(event.get("diagnostic_readable"), bool)
                or not isinstance(event.get("diagnostic_truncated"), bool)):
            return False
        rules_schema = event.get("rules_schema", 1)
        if (not isinstance(rules_schema, int) or isinstance(rules_schema, bool)
                or rules_schema not in (1, 2, 3)):
            return False
        candidate_available = event.get("candidate_eligibility_available")
        if (not isinstance(candidate_available, bool)
                or (rules_schema == 1 and candidate_available is not False)):
            return False
        if rules_schema in (2, 3):
            for field in ("candidate_eligible", "target_exists", "ui_war_allowed"):
                if not isinstance(event.get(field), bool):
                    return False
        else:
            # Schema 1 may omit the fields introduced by R34B.  If a producer
            # includes one accidentally, it still must be typed as a boolean;
            # absence remains the compatible representation.
            for field in ("candidate_eligible", "target_exists", "ui_war_allowed"):
                if field in event and not isinstance(event.get(field), bool):
                    return False
        if rules_schema == 3:
            if (not isinstance(event.get("full_rules_complete"), bool)
                    or not isinstance(event.get("native_action_available"), bool)
                    or event.get("submitted") is not False):
                return False
        elif (event.get("full_rules_complete") is not False
              or event.get("submitted") is not False):
            return False
        # R34C adds a native final-cost read without changing the schema2
        # candidate contract. Older events omit both cost fields.
        if "cost_query_called" in event or "diplomatic_power_cost_raw" in event:
            cost_called = event.get("cost_query_called")
            cost = cls._safe_int(event.get("diplomatic_power_cost_raw"), -1, 2147483647)
            if (not isinstance(cost_called, bool) or cost is None
                    or (cost_called and (action_id != "remove_rival" or cost < 0))
                    or (not cost_called and cost != -1)):
                return False
        if "frame_thread" in event and cls._safe_int(
                event.get("frame_thread"), 0, 2**63 - 1) is None:
            return False
        # Rival has no counterparty acceptance score.  If a producer emits
        # the generic flags, every one must explicitly be false.
        for field in ("score_applicable", "score_available",
                      "acceptance_predicate_available"):
            if field in event and event.get(field) is not False:
                return False
        return True

    @classmethod
    def _valid_native_insult_inspection(cls, event: object, action_id: str,
                                        actor: str, recipient: str, phase: str,
                                        expected_date: object,
                                        expected_insult_id: int) -> bool:
        """Validate the family-specific query2 result for an insult action."""

        if (not isinstance(event, dict)
                or action_id not in _INSULT_ACTIONS
                or event.get("event") != "native_alliance_inspection"
                or event.get("action_id") != action_id
                or event.get("family") != "insult"
                or event.get("actor") != actor
                or event.get("recipient") != recipient
                or event.get("phase") != phase):
            return False
        actual_date = cls._safe_int(event.get("date_raw"))
        wanted_date = cls._safe_int(expected_date)
        if actual_date is None or wanted_date is None or actual_date != wanted_date:
            return False
        if cls._safe_int(event.get("insult_id"), -2147483648, 2147483647) != expected_insult_id:
            return False
        if (not isinstance(event.get("insult_parameter_selected"), bool)
                or event.get("insult_parameter_selected") is not (expected_insult_id != -2)
                or event.get("insult_state_verified") is not True
                or not isinstance(event.get("insult_active"), bool)):
            return False
        for field in ("opinion_modifier_raw", "actor_prestige_raw"):
            if cls._safe_int(event.get(field), -2147483648, 2147483647) is None:
                return False
        cost = event.get("prestige_cost_raw")
        if cost is not None and cls._safe_int(cost, -2147483648, 2147483647) is None:
            return False
        for field in ("candidates_available", "candidates_complete"):
            if not isinstance(event.get(field), bool):
                return False
        if cls._safe_int(event.get("candidate_count"), 0, 256) is None:
            return False
        # An insult is single-sided; a copied negotiated-score record cannot
        # authorize it or supply a response prediction.
        for field in ("score_applicable", "score_available",
                      "acceptance_predicate_available"):
            if event.get(field) is not False:
                return False
        if event.get("native_would_accept") not in (False, None):
            return False
        return True

    def alliance_objects(self, actor: str, recipient: str) -> dict:
        # Read only the controlled country's objects for semantic output. A
        # queue node alone does not prove delivery, expiry or response ownership.
        controlled = self.record.get("controlled_countries", ["FRA"])
        if actor not in controlled and recipient not in controlled:
            return {"status": "unknown", "items": [], "complete": False,
                    "reason_code": "OUTSIDE_CONTROLLED_COUNTRY_INFORMATION_SCOPE"}
        try:
            from work.local_config import get_value
            root = Path(__file__).resolve().parents[1]
            output = self.directory / f"alliance-inspection-{time.time_ns()}.json"
            subprocess.run([get_value("EU4_PYTHON"), "-B", str(root / "work/probe_alliance_state.py"),
                "--pid", str(self.record["pid"]), "--output", str(output)], check=True, timeout=30,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            snapshot = json.loads(output.read_text(encoding="utf-8"))
            after = probe_identity(self.record["pid"], self.game_exe)
            if snapshot["pid"] != self.record["pid"] or after["session_id"] != self.session_id:
                raise RuntimeError("SNAPSHOT_SESSION_MISMATCH")
            items = []
            for country in snapshot["countries"]:
                if country["country"] not in controlled:
                    continue
                for obj in country["actions"]:
                    if obj.get("identification") != "static_vtable_layout_matched_live":
                        continue
                    if obj["actor_field"] != actor or obj["recipient_field"] != recipient:
                        continue
                    opaque = hashlib.sha256(f"{self.session_id}:{obj['object']}:{obj['date_field_28']}".encode()).hexdigest()[:24]
                    items.append({"object_id": "observed_" + opaque, "action_id": obj["action_id"],
                        "actor": actor, "recipient": recipient, "lifecycle_stage": "unknown",
                        "decision_country": None, "source": "native_queue_read", "complete": False})
            return {"status": "observed", "items": items, "date_raw": snapshot["date_raw"],
                    "complete": False, "reason_code": "QUEUE_LIFECYCLE_NOT_RECOVERED"}
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError):
            return {"status": "unknown", "items": [], "complete": False, "reason_code": "NATIVE_QUEUE_READ_FAILED"}

    def inspect_alliance(self, action_id: str, actor: str, recipient: str, phase: str,
                         required_capabilities: frozenset[str] | None = None,
                         allow_recipient_scope: bool = False,
                         inspection_event: str = "native_alliance_inspection",
                         declare_war_selection: dict | None = None,
                         peace_war_id: str | None = None,
                         peace_direction: str = "demand",
                         peace_money_offer: dict | None = None,
                         peace_province_offer: dict | None = None,
                         peace_combined_offer: dict | None = None) -> dict | None:
        if phase != "initiate":
            return None
        controlled = self.record.get("controlled_countries", ["FRA"])
        if actor not in controlled and not (allow_recipient_scope and recipient in controlled):
            return {"error_code": "QUERY_INFORMATION_SCOPE_UNAVAILABLE"}
        # Capabilities are acknowledged by this exact installation, rather
        # than inferred from the shared DLL filename or a version number.
        log = self.directory / "control-probe.jsonl"
        required = _NATIVE_QUERY_CAPS if required_capabilities is None else required_capabilities
        if not (self.installation_capabilities() & required):
            return None
        peace_evaluation_enabled = (
            _NATIVE_PEACE_OFFER_EVALUATION_QUERY_CAPABILITY in required)
        peace_wrapper_rule_enabled = (
            _NATIVE_PEACE_WRAPPER_RULE_QUERY_CAPABILITY in required)
        health = self.health()
        if health["status"] != "ready":
            return {"error_code": "QUERY_SESSION_UNREADY"}
        query_id = "inspect_" + uuid.uuid4().hex
        expiry = time.time_ns() // 100 + 116444736000000000 + 30 * 10000000
        if peace_combined_offer is not None:
            province_ids = peace_combined_offer.get("province_ids", [])
            csv_ids = ",".join(str(value) for value in province_ids) or "-"
            beneficiary = peace_combined_offer.get("beneficiary") or "-"
            direction = peace_combined_offer.get("direction", "demand")
            amount_raw = peace_combined_offer.get("amount_raw")
            primary_action = peace_combined_offer.get("action_id", action_id)
            wire = (f"EU4DIP_QUERY7 {self.record['creation_filetime']:x} {query_id} "
                    f"{primary_action} {actor} {recipient} {health['date_raw']} {expiry} "
                    f"{peace_combined_offer['war_id']} {direction} {amount_raw} "
                    f"{csv_ids} {beneficiary}\n")
        elif peace_province_offer is not None:
            province_ids = peace_province_offer.get("province_ids", [])
            csv_ids = ",".join(str(value) for value in province_ids) or "-"
            beneficiary = peace_province_offer.get("beneficiary") or "-"
            if peace_province_offer.get("direction", "demand") == "offer":
                wire = (f"EU4DIP_QUERY7 {self.record['creation_filetime']:x} {query_id} "
                        f"cede_province {actor} {recipient} {health['date_raw']} {expiry} "
                        f"{peace_province_offer['war_id']} offer -1 {csv_ids} {beneficiary}\n")
            else:
                wire = (f"EU4DIP_QUERY6 {self.record['creation_filetime']:x} {query_id} "
                        f"cede_province {actor} {recipient} {health['date_raw']} {expiry} "
                        f"{peace_province_offer['war_id']} {csv_ids} {beneficiary}\n")
        elif peace_money_offer is not None:
            if peace_money_offer.get("direction", "demand") == "offer":
                wire = (f"EU4DIP_QUERY7 {self.record['creation_filetime']:x} {query_id} "
                        f"demand_ducats {actor} {recipient} {health['date_raw']} {expiry} "
                        f"{peace_money_offer['war_id']} offer "
                        f"{peace_money_offer['amount_raw']} - -\n")
            else:
                wire = (f"EU4DIP_QUERY5 {self.record['creation_filetime']:x} {query_id} "
                        f"demand_ducats {actor} {recipient} {health['date_raw']} {expiry} "
                        f"{peace_money_offer['war_id']} {peace_money_offer['amount_raw']}\n")
        elif peace_war_id is not None:
            if peace_direction == "offer":
                wire = (f"EU4DIP_QUERY7 {self.record['creation_filetime']:x} {query_id} "
                        f"{action_id} {actor} {recipient} {health['date_raw']} {expiry} "
                        f"{peace_war_id} offer -1 - -\n")
            else:
                wire = (f"EU4DIP_QUERY4 {self.record['creation_filetime']:x} {query_id} "
                        f"{action_id} {actor} {recipient} {health['date_raw']} {expiry} "
                        f"{peace_war_id}\n")
        elif declare_war_selection is None:
            wire = (f"EU4DIP_QUERY1 {self.record['creation_filetime']:x} {query_id} {action_id} "
                    f"{actor} {recipient} {health['date_raw']} {expiry}\n")
        else:
            wire = (f"EU4DIP_QUERY3 {self.record['creation_filetime']:x} {query_id} {action_id} "
                    f"{actor} {recipient} {health['date_raw']} {expiry} "
                    f"{declare_war_selection['casus_belli']} "
                    f"{declare_war_selection['province_id']} "
                    f"{declare_war_selection['beneficiary']}\n")
        offset = log.stat().st_size
        request = self.directory / "diplomacy-query.request"
        pending = self.directory / f"{query_id}.pending"
        pending_owned = False
        try:
            with pending.open("x", encoding="ascii", newline="\n") as stream:
                pending_owned = True
                stream.write(wire)
                stream.flush()
                os.fsync(stream.fileno())
            # A same-directory hard link publishes the completed wire atomically
            # and fails if another request owns the fixed channel. Opening the
            # channel first exposes an empty/partial request to the frame reader.
            os.link(pending, request)
        except FileExistsError:
            return {"error_code": "QUERY_CHANNEL_BUSY"}
        except OSError:
            return {"error_code": "QUERY_CHANNEL_WRITE_FAILED"}
        finally:
            if pending_owned and pending.exists():
                pending.unlink()
        reason_events: dict[int, dict] = {}
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with log.open("rb") as stream:
                if log.stat().st_size < offset:
                    return {"error_code": "QUERY_LOG_TRUNCATED"}
                stream.seek(offset)
                chunk = stream.read(65536)
            complete_end = chunk.rfind(b"\n")
            if complete_end >= 0:
                offset += complete_end + 1
                for line in chunk[:complete_end+1].splitlines():
                    try:
                        event = json.loads(line)
                    except (TypeError, ValueError, UnicodeDecodeError):
                        continue
                    if not isinstance(event, dict):
                        continue
                    if event.get("query_id") != query_id or event.get("session_id") != self.session_id:
                        continue
                    if event.get("event") in {
                            "native_alliance_inspection_failed",
                            "native_rival_inspection_failed",
                            "native_declare_war_inspection_failed",
                            "native_peace_context_inspection_failed",
                            "native_peace_empty_offer_inspection_failed",
                            "native_peace_money_offer_inspection_failed",
                             "native_peace_province_offer_inspection_failed",
                             "native_peace_combined_offer_inspection_failed"}:
                        return {"error_code": event["reason_code"]}
                    if event.get("event") == "native_alliance_reason_item":
                        index = self._safe_int(event.get("index"), 0, _MAX_REASON_ITEMS - 1)
                        if index is not None and index not in reason_events:
                            reason_events[index] = event
                        continue
                    if event.get("event") == inspection_event:
                        event_for_validation = event
                        if (inspection_event in {
                                "native_peace_empty_offer_inspection",
                                "native_peace_province_offer_inspection",
                                "native_peace_combined_offer_inspection"}
                                and not peace_evaluation_enabled
                                and "native_evaluation" in event):
                            # A producer-side optional field cannot activate
                            # the public evaluator without its exact ACK.  The
                            # established QUERY4 contract remains readable.
                            event_for_validation = dict(event)
                            event_for_validation.pop("native_evaluation", None)
                        valid = (
                            self._valid_native_rival_inspection(
                                event_for_validation, action_id, actor, recipient, phase,
                                health.get("date_raw"), query_id, self.session_id)
                            if inspection_event == "native_rival_inspection" else
                            self._valid_native_declare_war_inspection(
                                event_for_validation, action_id, actor, recipient, phase,
                                health.get("date_raw"), query_id, self.session_id,
                                declare_war_selection)
                            if inspection_event == "native_declare_war_inspection" else
                            self._valid_native_peace_empty_offer_inspection(
                                event_for_validation, action_id, actor, recipient, phase,
                                health.get("date_raw"), peace_war_id,
                                query_id, self.session_id,
                                require_wrapper_rule=peace_wrapper_rule_enabled,
                                expected_direction=peace_direction)
                            if inspection_event == "native_peace_empty_offer_inspection" else
                            self._valid_native_peace_money_offer_inspection(
                                event_for_validation, action_id, actor, recipient, phase,
                                health.get("date_raw"), peace_money_offer,
                                query_id, self.session_id,
                                require_wrapper_rule=peace_wrapper_rule_enabled)
                            if inspection_event == "native_peace_money_offer_inspection" else
                            self._valid_native_peace_province_offer_inspection(
                                event_for_validation, action_id, actor, recipient, phase,
                                health.get("date_raw"), peace_province_offer,
                                query_id, self.session_id,
                                require_wrapper_rule=peace_wrapper_rule_enabled)
                            if inspection_event == "native_peace_province_offer_inspection" else
                             self._valid_native_peace_combined_offer_inspection(
                                 event_for_validation, action_id, actor, recipient, phase,
                                 health.get("date_raw"), peace_combined_offer,
                                 query_id, self.session_id,
                                 require_wrapper_rule=peace_wrapper_rule_enabled)
                             if inspection_event == "native_peace_combined_offer_inspection" else
                            self._valid_native_peace_context_inspection(
                                event_for_validation, action_id, actor, recipient, phase,
                                health.get("date_raw"), query_id, self.session_id)
                            if inspection_event == "native_peace_context_inspection" else
                            self._valid_native_inspection(
                                event_for_validation, action_id, actor, recipient, phase,
                                health.get("date_raw")))
                        if not valid:
                            return {"error_code": "QUERY_NATIVE_RESULT_INVALID"}
                        actual = probe_identity(self.record["pid"], self.game_exe)
                        if not isinstance(actual, dict) or actual.get("session_id") != self.session_id:
                            return {"error_code": "QUERY_SESSION_CHANGED"}
                        if inspection_event == "native_rival_inspection":
                            return self._semantic_rival_inspection(
                                event, self.native_text_codec)
                        if inspection_event == "native_declare_war_inspection":
                            return self._semantic_declare_war_inspection(
                                event, self.native_text_codec)
                        if inspection_event == "native_peace_context_inspection":
                            return self._semantic_peace_context_inspection(event)
                        if inspection_event == "native_peace_empty_offer_inspection":
                            return self._semantic_peace_empty_offer_inspection(
                                event_for_validation, self.native_text_codec)
                        if inspection_event == "native_peace_money_offer_inspection":
                            return self._semantic_peace_money_offer_inspection(
                                event_for_validation, self.native_text_codec)
                        if inspection_event == "native_peace_province_offer_inspection":
                            return self._semantic_peace_province_offer_inspection(
                                event_for_validation, self.native_text_codec)
                        if inspection_event == "native_peace_combined_offer_inspection":
                            return self._semantic_peace_combined_offer_inspection(
                                event_for_validation, self.native_text_codec)
                        return self._semantic_inspection(
                            event, reason_events, self.native_text_codec,
                            _NATIVE_REASON_METADATA_CAPABILITY in self.installation_capabilities())
            time.sleep(0.02)
        # Timeout is an unobserved query, not a rule prohibition or rejection.
        return {"error_code": "QUERY_OBSERVATION_TIMEOUT"}

    def inspect_royal_marriage(self, action_id: str, actor: str,
                               recipient: str, phase: str) -> dict | None:
        """Run the same bounded query wire with the dedicated Royal ACK gate."""

        return self.inspect_alliance(
            action_id, actor, recipient, phase,
            frozenset({_NATIVE_ROYAL_MARRIAGE_QUERY_CAPABILITY}))

    def inspect_improve_relations(self, action_id: str, actor: str,
                                  recipient: str, phase: str) -> dict | None:
        """Read a bounded native ImproveRelations UI inspection.

        The native producer uses the existing ``native_alliance_inspection``
        event and query wire.  The dedicated ACK is required so an Alliance
        or Royal installation cannot be treated as an ImproveRelations build.
        """

        if action_id not in ("improve_relations", "stop_improving_relations") \
                or phase != "initiate":
            return None
        return self.inspect_alliance(
            action_id, actor, recipient, phase,
            frozenset({_NATIVE_IMPROVE_RELATIONS_QUERY_CAPABILITY}))

    def inspect_spy_network(self, action_id: str, actor: str,
                            recipient: str, phase: str) -> dict | None:
        """Read a bounded native Spy Network UI inspection.

        Spy Network uses the existing inspection wire and event shape, while
        the dedicated ACK keeps its query authority separate from Improve,
        Alliance and Royal Marriage families.
        """

        if action_id not in ("build_spy_network", "stop_building_spy_network") \
                or phase != "initiate":
            return None
        return self.inspect_alliance(
            action_id, actor, recipient, phase,
            frozenset({_NATIVE_SPY_NETWORK_QUERY_CAPABILITY}))

    def inspect_guarantee(self, action_id: str, actor: str,
                          recipient: str, phase: str) -> dict | None:
        """Read a bounded native Guarantee relation inspection.

        Guarantee keeps the existing ``native_alliance_inspection`` wire and
        event name, but requires its own ACK and validates the
        ``family=guarantee`` relation-state fields.
        """

        if action_id not in ("proclaim_guarantee", "revoke_guarantee") \
                or phase != "initiate":
            return None
        return self.inspect_alliance(
            action_id, actor, recipient, phase,
            frozenset({_NATIVE_GUARANTEE_QUERY_CAPABILITY}))

    def inspect_support_independence(self, action_id: str, actor: str,
                                     recipient: str, phase: str) -> dict | None:
        """Read one native Support Independence relation inspection.

        Support Independence shares the bounded inspection wire with Alliance,
        but its relation state and query ACK remain family-specific.  This
        method observes both the offer and revoke variants; it does not expose
        an inbound accept/reject response adapter.
        """

        if action_id not in ("support_independence", "revoke_support_independence") \
                or phase != "initiate":
            return None
        return self.inspect_alliance(
            action_id, actor, recipient, phase,
            frozenset({_NATIVE_SUPPORT_INDEPENDENCE_QUERY_CAPABILITY}))

    def inspect_military_access(self, action_id: str, actor: str,
                                recipient: str, phase: str) -> dict | None:
        """Read one native Military Access relation inspection.

        Military Access shares the bounded inspection wire and event with the
        other relation families, while its dedicated query ACK and relation
        fields remain family-specific.
        """

        if action_id not in ("ask_military_access", "cancel_military_access") \
                or phase != "initiate":
            return None
        return self.inspect_alliance(
            action_id, actor, recipient, phase,
            frozenset({_NATIVE_MILITARY_ACCESS_QUERY_CAPABILITY}),
            allow_recipient_scope=True)

    def inspect_rival(self, action_id: str, actor: str,
                      recipient: str, phase: str) -> dict | None:
        """Read the dedicated R34 Rival countrycommands inspection.

        This method is query-only.  A separate exact submission ACK and wire
        adapter govern execution; querying Rival never grants that authority.
        """

        if (action_id not in ("set_rival", "remove_rival")
                or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z0-9]{3}", recipient) is None
                or recipient == actor):
            return {"error_code": "QUERY_INFORMATION_SCOPE_UNAVAILABLE"}
        return self.inspect_alliance(
            action_id, actor, recipient, phase,
            frozenset({_NATIVE_RIVAL_QUERY_CAPABILITY}),
            inspection_event="native_rival_inspection")

    def inspect_vassalization(self, action_id: str, actor: str,
                               recipient: str, phase: str) -> dict | None:
        """Read the dedicated R35 Vassalization inspection contract.

        Query support is gated by the exact vassalization ACK.  Submission is
        intentionally absent from this method and remains unimplemented until
        a separate ``native_vassalization_submission`` ACK is issued.
        """

        if (action_id not in _VASSALIZATION_ACTIONS
                or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z0-9]{3}", recipient) is None
                or recipient == actor):
            return {"error_code": "QUERY_INFORMATION_SCOPE_UNAVAILABLE"}
        return self.inspect_alliance(
            action_id, actor, recipient, phase,
            frozenset({_NATIVE_VASSALIZATION_QUERY_CAPABILITY}))

    def inspect_declare_war(self, action_id: str, actor: str,
                            recipient: str, phase: str,
                            parameters: dict | None = None) -> dict | None:
        """Read the default QUERY1 object or a bounded QUERY3 selection."""

        if (action_id != "declare_war" or actor != "FRA"
                or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z0-9]{3}", recipient) is None
                or recipient == actor):
            return {"error_code": "QUERY_INFORMATION_SCOPE_UNAVAILABLE"}
        try:
            selection = self._normalize_declare_war_parameters(
                {} if parameters is None else parameters)
        except ValueError as exc:
            return {"error_code": str(exc)}
        return self.inspect_alliance(
            action_id, actor, recipient, phase,
            frozenset({_NATIVE_DECLARE_WAR_QUERY_CAPABILITY}),
            inspection_event="native_declare_war_inspection",
            declare_war_selection=selection)

    def inspect_peace_contexts(self, action_id: str, actor: str,
                               recipient: str, phase: str) -> dict | None:
        """Discover the current opaque war contexts for one peace action.

        QUERY1 only enumerates wars.  It does not inspect peace terms and it
        never grants an offer or response execution adapter.
        """

        if (action_id not in PEACE_ACTION_IDS
                or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z0-9]{3}", recipient) is None
                or recipient == actor):
            return {"error_code": "QUERY_INFORMATION_SCOPE_UNAVAILABLE"}
        return self.inspect_alliance(
            action_id, actor, recipient, phase,
            frozenset({_NATIVE_PEACE_CONTEXT_QUERY_CAPABILITY}),
            inspection_event="native_peace_context_inspection")

    def inspect_peace_empty_offer(self, action_id: str, actor: str,
                                  recipient: str, phase: str,
                                  war_id: str, direction: str = "demand") -> dict | None:
        """Inspect a constructed empty white-peace term in one direction."""

        if (action_id != "white_peace" or actor != "FRA"
                or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z0-9]{3}", recipient) is None
                or recipient == actor):
            return {"error_code": "QUERY_INFORMATION_SCOPE_UNAVAILABLE"}
        if (not isinstance(war_id, str)
                or re.fullmatch(_PEACE_WAR_ID_PATTERN, war_id) is None):
            return {"error_code": "QUERY_PEACE_WAR_ID_INVALID"}
        if direction not in ("demand", "offer"):
            return {"error_code": "QUERY_PEACE_DIRECTION_INVALID"}
        required = {_NATIVE_PEACE_EMPTY_OFFER_QUERY_CAPABILITY}
        if (_NATIVE_PEACE_OFFER_EVALUATION_QUERY_CAPABILITY
                in self.installation_capabilities()):
            required.add(_NATIVE_PEACE_OFFER_EVALUATION_QUERY_CAPABILITY)
        if (_NATIVE_PEACE_WRAPPER_RULE_QUERY_CAPABILITY
                in self.installation_capabilities()):
            required.add(_NATIVE_PEACE_WRAPPER_RULE_QUERY_CAPABILITY)
        return self.inspect_alliance(
            action_id, actor, recipient, phase,
            frozenset(required),
            inspection_event="native_peace_empty_offer_inspection",
            peace_war_id=war_id, peace_direction=direction)

    def inspect_peace_money_offer(self, action_id: str, actor: str,
                                  recipient: str, phase: str,
                                  selection: dict) -> dict | None:
        """Inspect one money term through QUERY5 or explicit-direction QUERY7."""

        if (action_id != "demand_ducats" or actor != "FRA"
                or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z0-9]{3}", recipient) is None
                or recipient == actor
                or not isinstance(selection, dict)
                or selection.get("direction") not in ("demand", "offer")
                or selection.get("payer") != (
                    actor if selection.get("direction") == "offer" else recipient)
                or selection.get("claimant") != (
                    recipient if selection.get("direction") == "offer" else actor)
                or not isinstance(selection.get("war_id"), str)
                or re.fullmatch(_PEACE_WAR_ID_PATTERN,
                                selection["war_id"]) is None
                or self._safe_int(selection.get("amount_raw"),
                                  1, 2147483647) is None):
            return {"error_code": "QUERY_INFORMATION_SCOPE_UNAVAILABLE"}
        required = {_NATIVE_PEACE_MONEY_OFFER_QUERY_CAPABILITY}
        if (_NATIVE_PEACE_WRAPPER_RULE_QUERY_CAPABILITY
                in self.installation_capabilities()):
            required.add(_NATIVE_PEACE_WRAPPER_RULE_QUERY_CAPABILITY)
        return self.inspect_alliance(
            action_id, actor, recipient, phase,
            frozenset(required),
            inspection_event="native_peace_money_offer_inspection",
            peace_money_offer=selection)

    def inspect_peace_province_offer(self, action_id: str, actor: str,
                                     recipient: str, phase: str,
                                     selection: dict) -> dict | None:
        """Inspect QUERY6/QUERY7 province candidates or a selected term."""
        if (action_id != "cede_province" or actor != "FRA"
                or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z0-9]{3}", recipient) is None
                or recipient == actor
                or not isinstance(selection, dict)
                or not isinstance(selection.get("war_id"), str)
                or re.fullmatch(_PEACE_WAR_ID_PATTERN,
                                selection["war_id"]) is None
                or selection.get("direction") not in ("demand", "offer")
                or not isinstance(selection.get("province_ids"), list)
                or len(selection["province_ids"]) > 16
                or any(self._safe_int(value, 1, 2147483647) is None
                       for value in selection["province_ids"])
                or (selection.get("beneficiary") is not None
                    and (not isinstance(selection.get("beneficiary"), str)
                         or re.fullmatch(r"[A-Z0-9]{3}",
                                         selection["beneficiary"]) is None))):
            return {"error_code": "QUERY_PEACE_PROVINCE_PARAMETERS_INVALID"}
        if len(set(selection["province_ids"])) != len(selection["province_ids"]):
            return {"error_code": "QUERY_PEACE_PROVINCE_PARAMETERS_INVALID"}
        required = {_NATIVE_PEACE_PROVINCE_OFFER_QUERY_CAPABILITY}
        if (_NATIVE_PEACE_OFFER_EVALUATION_QUERY_CAPABILITY
                in self.installation_capabilities()):
            required.add(_NATIVE_PEACE_OFFER_EVALUATION_QUERY_CAPABILITY)
        if (_NATIVE_PEACE_WRAPPER_RULE_QUERY_CAPABILITY
                in self.installation_capabilities()):
            required.add(_NATIVE_PEACE_WRAPPER_RULE_QUERY_CAPABILITY)
        return self.inspect_alliance(
            action_id, actor, recipient, phase,
            frozenset(required),
            inspection_event="native_peace_province_offer_inspection",
            peace_province_offer=selection)

    def inspect_peace_combined_offer(self, action_id: str, actor: str,
                                     recipient: str, phase: str,
                                     selection: dict) -> dict | None:
        """Inspect one mixed money+province offer through aggregate QUERY7."""
        if (action_id not in ("demand_ducats", "cede_province")
                or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z0-9]{3}", recipient) is None
                or recipient == actor
                or not isinstance(selection, dict)
                or selection.get("direction") not in ("demand", "offer")
                or not isinstance(selection.get("war_id"), str)
                or re.fullmatch(_PEACE_WAR_ID_PATTERN,
                                selection["war_id"]) is None
                or self._safe_int(selection.get("amount_raw"),
                                  1, 2147483647) is None
                or not isinstance(selection.get("province_ids"), list)
                or not 1 <= len(selection["province_ids"]) <= 16
                or any(self._safe_int(value, 1, 2147483647) is None
                       for value in selection["province_ids"])
                or len(set(selection["province_ids"]))
                != len(selection["province_ids"])
                or not isinstance(selection.get("beneficiary"), str)
                or re.fullmatch(r"[A-Z0-9]{3}",
                                selection["beneficiary"]) is None):
            return {"error_code": "QUERY_PEACE_COMBINED_PARAMETERS_INVALID"}
        direction = selection["direction"]
        expected_payer = actor if direction == "offer" else recipient
        expected_claimant = recipient if direction == "offer" else actor
        if (selection.get("payer") != expected_payer
                or selection.get("claimant") != expected_claimant
                or selection.get("action_id") != action_id):
            return {"error_code": "QUERY_PEACE_COMBINED_PARAMETERS_INVALID"}
        required = {_NATIVE_PEACE_COMBINED_QUERY_CAPABILITY}
        if (_NATIVE_PEACE_OFFER_EVALUATION_QUERY_CAPABILITY
                in self.installation_capabilities()):
            required.add(_NATIVE_PEACE_OFFER_EVALUATION_QUERY_CAPABILITY)
        if (_NATIVE_PEACE_WRAPPER_RULE_QUERY_CAPABILITY
                in self.installation_capabilities()):
            required.add(_NATIVE_PEACE_WRAPPER_RULE_QUERY_CAPABILITY)
        return self.inspect_alliance(
            action_id, actor, recipient, phase,
            frozenset(required),
            inspection_event="native_peace_combined_offer_inspection",
            peace_combined_offer=selection)

    def inspect_peace_execution(self, action_id: str, actor: str,
                                recipient: str, phase: str,
                                parameters: object) -> dict | None:
        """Freshly inspect the selected complete Peace execution context."""

        try:
            normalized = normalize_peace_execution_parameters(
                action_id, actor, recipient, phase, parameters)
        except (TypeError, ValueError):
            return {"error_code": "NATIVE_PEACE_EXECUTION_PARAMETERS_INVALID"}
        terms = normalized["peace_context"]["terms"]
        if len(terms) > 1:
            if _NATIVE_PEACE_COMBINED_QUERY_CAPABILITY not in self.installation_capabilities():
                return {"error_code": "NATIVE_PEACE_EXECUTION_MIXED_INSPECTION_UNAVAILABLE"}
            money_term = next((term for term in terms
                               if term["action_id"] == "demand_ducats"), None)
            province_term = next((term for term in terms
                                  if term["action_id"] == "cede_province"), None)
            if money_term is None or province_term is None:
                return {"error_code": "NATIVE_PEACE_EXECUTION_PARAMETERS_INVALID"}
            amount = money_term["amount"]
            whole, tenths = amount.split(".")
            direction = normalized["peace_context"]["direction"]
            selection = {
                "action_id": action_id,
                "war_id": normalized["peace_context"]["war_id"],
                "direction": direction,
                "amount_raw": (int(whole) * 10 + int(tenths)) * 100,
                "payer": money_term["payer"],
                "claimant": money_term["claimant"],
                "province_ids": list(province_term["province_ids"]),
                "beneficiary": province_term["beneficiary"],
            }
            return self.inspect_peace_combined_offer(
                action_id, actor, recipient, phase, selection)
        war_id = normalized["peace_context"]["war_id"]
        if action_id == "white_peace":
            return self.inspect_peace_empty_offer(
                action_id, actor, recipient, phase, war_id,
                normalized["peace_context"]["direction"])
        term = terms[0]
        if term["action_id"] == "demand_ducats":
            amount = term["amount"]
            whole, tenths = amount.split(".")
            selection = {
                "war_id": war_id,
                "direction": normalized["peace_context"]["direction"],
                "amount_raw": (int(whole) * 10 + int(tenths)) * 100,
                "payer": term["payer"],
                "claimant": term["claimant"],
            }
            return self.inspect_peace_money_offer(
                action_id, actor, recipient, phase, selection)
        selection = {
            "war_id": war_id,
            "direction": normalized["peace_context"]["direction"],
            "province_ids": list(term["province_ids"]),
            "beneficiary": term["beneficiary"],
        }
        return self.inspect_peace_province_offer(
            action_id, actor, recipient, phase, selection)

    def inspect_insult(self, action_id: str, actor: str, recipient: str,
                       phase: str, insult_id: int | None = None) -> dict | None:
        """Query one insult or discover scornful-insult candidates.

        Query2 is deliberately separate from the legacy Query1 wire.  ``-1``
        represents ordinary insult, ``-2`` asks the native adapter to enumerate
        scornful candidates, and a non-negative value selects one candidate.
        """

        if action_id not in _INSULT_ACTIONS or phase != "initiate":
            return None
        controlled = self.record.get("controlled_countries", ["FRA"])
        if (actor != "FRA" or actor not in controlled
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z]{3}", recipient) is None
                or recipient == "FRA"):
            return {"error_code": "QUERY_INFORMATION_SCOPE_UNAVAILABLE"}
        if action_id == "send_insult":
            if self._safe_int(insult_id, -1, -1) is None:
                return {"error_code": "INSULT_PARAMETER_INVALID"}
            query_insult_id = -1
        elif insult_id is None:
            query_insult_id = -2
        elif self._safe_int(insult_id, 0, 2147483647) is None:
            return {"error_code": "INSULT_PARAMETER_INVALID"}
        else:
            query_insult_id = insult_id
        if _NATIVE_INSULT_QUERY_CAPABILITY not in self.installation_capabilities():
            return None
        health = self.health()
        if health["status"] != "ready":
            return {"error_code": "QUERY_SESSION_UNREADY"}
        log = self.directory / "control-probe.jsonl"
        query_id = "inspect_" + uuid.uuid4().hex
        expiry = time.time_ns() // 100 + _FILETIME_EPOCH + 30 * 10_000_000
        wire = (f"EU4DIP_QUERY2 {self.record['creation_filetime']:x} {query_id} {action_id} "
                f"{actor} {recipient} {health['date_raw']} {expiry} {query_insult_id}\n")
        try:
            offset = log.stat().st_size
        except OSError:
            return {"error_code": "QUERY_LOG_UNAVAILABLE"}
        request = self.directory / "diplomacy-query.request"
        pending = self.directory / f"{query_id}.pending"
        pending_owned = False
        try:
            with pending.open("x", encoding="ascii", newline="\n") as stream:
                pending_owned = True
                stream.write(wire)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(pending, request)
        except FileExistsError:
            return {"error_code": "QUERY_CHANNEL_BUSY"}
        except (OSError, UnicodeEncodeError):
            return {"error_code": "QUERY_CHANNEL_WRITE_FAILED"}
        finally:
            if pending_owned and pending.exists():
                pending.unlink()
        reason_events: dict[int, dict] = {}
        candidates: dict[int, dict] = {}
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                with log.open("rb") as stream:
                    if log.stat().st_size < offset:
                        return {"error_code": "QUERY_LOG_TRUNCATED"}
                    stream.seek(offset)
                    chunk = stream.read(65536)
            except OSError:
                return {"error_code": "QUERY_LOG_UNAVAILABLE"}
            complete_end = chunk.rfind(b"\n")
            if complete_end >= 0:
                offset += complete_end + 1
                for line in chunk[:complete_end + 1].splitlines():
                    try:
                        event = json.loads(line)
                    except (TypeError, ValueError, UnicodeDecodeError):
                        continue
                    if (not isinstance(event, dict)
                            or event.get("query_id") != query_id
                            or event.get("session_id") != self.session_id):
                        continue
                    if event.get("event") == "native_alliance_inspection_failed":
                        return {"error_code": event.get("reason_code", "QUERY_NATIVE_RESULT_INVALID")}
                    if event.get("event") == "native_alliance_reason_item":
                        index = self._safe_int(event.get("index"), 0, _MAX_REASON_ITEMS - 1)
                        if index is not None and index not in reason_events:
                            reason_events[index] = event
                        continue
                    if event.get("event") == "native_insult_candidate":
                        candidate = self._public_native_insult_candidate(event, self.native_text_codec)
                        if candidate is not None:
                            candidates[candidate["insult_id"]] = candidate
                        continue
                    if event.get("event") != "native_alliance_inspection":
                        continue
                    if not self._valid_native_insult_inspection(
                            event, action_id, actor, recipient, phase, health.get("date_raw"),
                            query_insult_id):
                        return {"error_code": "QUERY_NATIVE_RESULT_INVALID"}
                    actual = probe_identity(self.record["pid"], self.game_exe)
                    if not isinstance(actual, dict) or actual.get("session_id") != self.session_id:
                        return {"error_code": "QUERY_SESSION_CHANGED"}
                    result = self._semantic_inspection(
                        event, reason_events, self.native_text_codec,
                        _NATIVE_REASON_METADATA_CAPABILITY in self.installation_capabilities(),
                        [candidates[key] for key in sorted(candidates)])
                    result["parameters"] = {
                        "requested": ({"insult_id": insult_id}
                                       if insult_id is not None else {}),
                        "actual": {"insult_id": query_insult_id},
                        "candidates": result.get("parameters", {}).get("candidates"),
                        "complete": query_insult_id != -2 or event.get("candidates_complete") is True,
                    }
                    return result
            time.sleep(0.02)
        return {"error_code": "QUERY_OBSERVATION_TIMEOUT"}

    def health(self) -> dict:
        try:
            if self.record.get("installation_returncode") != 0:
                raise RuntimeError("INSTALLATION_NOT_CONFIRMED")
            current = probe_identity(self.record["pid"], self.game_exe)
            if current["session_id"] != self.session_id:
                raise RuntimeError("PROCESS_SESSION_CHANGED")
            modules = current["modules"]
            if len(modules) != 1 or modules[0]["sha256"] != self.record["dll_sha256"]:
                raise RuntimeError("LOADED_MODULE_IDENTITY_MISMATCH")
            log = self.directory / "control-probe.jsonl"
            if time.time() - log.stat().st_mtime > 5:
                raise RuntimeError("FRAME_HEARTBEAT_STALE")
            # Bounded tail; incomplete final lines are ignored, never repaired.
            # Keep the 64 KiB fast path, then widen only when it contains no
            # heartbeat for this session and the log is larger than that path.
            log_size = log.stat().st_size

            def stable_health_from_tail(tail_limit: int) -> dict | None:
                with log.open("rb") as stream:
                    tail_size = min(log_size, tail_limit)
                    stream.seek(max(0, log_size - tail_size))
                    lines = stream.read(tail_size).splitlines()
                events: list[object] = []
                for line in lines:
                    try:
                        event = json.loads(line)
                    except (ValueError, UnicodeDecodeError):
                        continue
                    events.append(event)
                # Keep the readiness predicate identical to the bounded wait
                # helper.  The local import avoids a module-level cycle while
                # retaining one pure implementation for both paths.
                from work.observer_runtime_ready import _stable_matching_heartbeat
                return _stable_matching_heartbeat(events, self.session_id)

            latest = stable_health_from_tail(_RESPONSE_LOG_CHUNK_BYTES)
            if latest is None and log_size > _RESPONSE_LOG_CHUNK_BYTES:
                latest = stable_health_from_tail(_HEALTH_LOG_MAX_TAIL_BYTES)
            if latest is None:
                raise RuntimeError("FRAME_THREAD_OR_WORLD_UNREADY")
            stamp = hashlib.sha256(f"{self.session_id}:{latest['frames']}:{latest['date_raw']}".encode()).hexdigest()
            return {"status": "ready", "state_id": stamp, "date_raw": latest["date_raw"],
                    "reasons": [], "complete": True}
        except (OSError, ValueError, KeyError, RuntimeError):
            # Native diagnostics stay in the operator evidence directory.
            return {"status": "unready", "state_id": None, "date_raw": None,
                    "reasons": [reason("SESSION_UNREADY", "当前实验会话或帧线程尚未通过身份与健康检查。", "runtime_error")],
                    "complete": False}


class DiplomacyTools:
    def __init__(self, journal: DurableJournal, session: ObserverSession | None = None):
        self.journal = journal
        self.session = session

    def _health(self) -> dict:
        if self.session is None:
            return {"status": "unready", "state_id": None, "date_raw": None,
                    "reasons": [reason("NO_SESSION", "尚未绑定经过校验的游戏会话。", "runtime_error")], "complete": False}
        return self.session.health()

    def _installation_capabilities(self) -> frozenset[str]:
        """Read the exact installation ack independently of rule inspection."""

        if self.session is None:
            return frozenset()
        reader = getattr(self.session, "installation_capabilities", None)
        if not callable(reader):
            return frozenset()
        try:
            advertised = reader()
        except (OSError, TypeError, ValueError, RuntimeError):
            return frozenset()
        if isinstance(advertised, dict):
            return frozenset(key for key, value in advertised.items()
                             if isinstance(key, str) and value is True
                             and key not in (_NATIVE_ROYAL_MARRIAGE_QUERY_CAPABILITY,
                                             _NATIVE_IMPROVE_RELATIONS_QUERY_CAPABILITY,
                                             _NATIVE_ROYAL_MARRIAGE_SUBMISSION_CAPABILITY,
                                             _NATIVE_IMPROVE_RELATIONS_SUBMISSION_CAPABILITY,
                                             _NATIVE_SPY_NETWORK_QUERY_CAPABILITY,
                                             _NATIVE_SPY_NETWORK_SUBMISSION_CAPABILITY,
                                             _NATIVE_GUARANTEE_QUERY_CAPABILITY,
                                             _NATIVE_GUARANTEE_SUBMISSION_CAPABILITY,
                                             _NATIVE_SUPPORT_INDEPENDENCE_QUERY_CAPABILITY,
                                             _NATIVE_SUPPORT_INDEPENDENCE_SUBMISSION_CAPABILITY,
                                              _NATIVE_MILITARY_ACCESS_QUERY_CAPABILITY,
                                              _NATIVE_MILITARY_ACCESS_SUBMISSION_CAPABILITY,
                                             _NATIVE_INSULT_QUERY_CAPABILITY,
                                             _NATIVE_INSULT_SUBMISSION_CAPABILITY,
                                             _NATIVE_RIVAL_QUERY_CAPABILITY,
                                             _NATIVE_RIVAL_SUBMISSION_CAPABILITY,
                                             _NATIVE_DECLARE_WAR_QUERY_CAPABILITY,
                                              _NATIVE_PEACE_SUBMISSION_CAPABILITY,
                                             _NATIVE_PEACE_CONTEXT_QUERY_CAPABILITY,
                                             _NATIVE_PEACE_EMPTY_OFFER_QUERY_CAPABILITY,
                                             _NATIVE_PEACE_MONEY_OFFER_QUERY_CAPABILITY,
                                             _NATIVE_PEACE_PROVINCE_OFFER_QUERY_CAPABILITY,
                                              _NATIVE_PEACE_COMBINED_QUERY_CAPABILITY,
                                              _NATIVE_PEACE_OFFER_EVALUATION_QUERY_CAPABILITY,
                                             _NATIVE_INBOUND_PEACE_RESPONSE_CAPABILITY,
                                             _NATIVE_INBOUND_SUPPORT_RESPONSE_CAPABILITY,
                                              _NATIVE_INBOUND_MILITARY_ACCESS_RESPONSE_CAPABILITY,
                                             _NATIVE_INBOUND_ROYAL_RESPONSE_CAPABILITY))
        if isinstance(advertised, (set, frozenset)):
            # ObserverSession returns a normalized frozenset after validating
            # the installation ACK.  Preserve that normalized result.
            return frozenset(value for value in advertised if isinstance(value, str))
        if isinstance(advertised, (list, tuple)):
            # A raw caps list is not allowed to grant the dedicated Royal
            # query; only the exact top-level ACK may do so.
            return frozenset(value for value in advertised
                             if isinstance(value, str)
                             and value not in (_NATIVE_ROYAL_MARRIAGE_QUERY_CAPABILITY,
                                               _NATIVE_IMPROVE_RELATIONS_QUERY_CAPABILITY,
                                               _NATIVE_ROYAL_MARRIAGE_SUBMISSION_CAPABILITY,
                                               _NATIVE_IMPROVE_RELATIONS_SUBMISSION_CAPABILITY,
                                               _NATIVE_SPY_NETWORK_QUERY_CAPABILITY,
                                               _NATIVE_SPY_NETWORK_SUBMISSION_CAPABILITY,
                                               _NATIVE_GUARANTEE_QUERY_CAPABILITY,
                                               _NATIVE_GUARANTEE_SUBMISSION_CAPABILITY,
                                               _NATIVE_SUPPORT_INDEPENDENCE_QUERY_CAPABILITY,
                                               _NATIVE_SUPPORT_INDEPENDENCE_SUBMISSION_CAPABILITY,
                                                _NATIVE_MILITARY_ACCESS_QUERY_CAPABILITY,
                                                _NATIVE_MILITARY_ACCESS_SUBMISSION_CAPABILITY,
                                               _NATIVE_INSULT_QUERY_CAPABILITY,
                                               _NATIVE_INSULT_SUBMISSION_CAPABILITY,
                                               _NATIVE_RIVAL_QUERY_CAPABILITY,
                                               _NATIVE_RIVAL_SUBMISSION_CAPABILITY,
                                               _NATIVE_DECLARE_WAR_QUERY_CAPABILITY,
                                                _NATIVE_PEACE_SUBMISSION_CAPABILITY,
                                               _NATIVE_PEACE_CONTEXT_QUERY_CAPABILITY,
                                               _NATIVE_PEACE_EMPTY_OFFER_QUERY_CAPABILITY,
                                               _NATIVE_PEACE_MONEY_OFFER_QUERY_CAPABILITY,
                                               _NATIVE_PEACE_PROVINCE_OFFER_QUERY_CAPABILITY,
                                                _NATIVE_PEACE_COMBINED_QUERY_CAPABILITY,
                                                _NATIVE_PEACE_OFFER_EVALUATION_QUERY_CAPABILITY,
                                               _NATIVE_INBOUND_PEACE_RESPONSE_CAPABILITY,
                                               _NATIVE_INBOUND_SUPPORT_RESPONSE_CAPABILITY,
                                                _NATIVE_INBOUND_MILITARY_ACCESS_RESPONSE_CAPABILITY,
                                               _NATIVE_INBOUND_ROYAL_RESPONSE_CAPABILITY))
        return frozenset()

    @staticmethod
    def _safe_inbound_proposal(item: object) -> dict | None:
        """Copy only the stable public fields of an observed proposal."""

        if not isinstance(item, dict):
            return None
        public_id = item.get("proposal_id")
        actor = item.get("actor")
        action_id = item.get("action_id", "offer_alliance")
        family = _inbound_family(action_id)
        if (not isinstance(public_id, str) or not re.fullmatch(r"[0-9a-f]{32}", public_id)
                or not isinstance(actor, str) or not re.fullmatch(r"[A-Z0-9]{3}", actor)
                or actor == "FRA" or family is None
                or item.get("family", family) != family
                or item.get("recipient") != "FRA"
                or item.get("decision_country") != "FRA"
                or item.get("observer_status") != "observed_pending"):
            return None
        # Do not trust arbitrary extra fields returned by a session adapter.
        # The restored-queue marker is a fixed semantic label produced by the
        # ObserverSession; all native ids, addresses and tokens stay private.
        safe = {
            "proposal_id": public_id,
            "action_id": action_id,
            "family": family,
            "actor": actor,
            "recipient": "FRA",
            "decision_country": "FRA",
            "phase": "initiate",
            "observer_status": "observed_pending",
            "currently_pending": None,
            "legality": {"status": "unknown", "complete": False},
            "legality_status": "unknown",
            "execute": {"accept": "unimplemented", "reject": "unimplemented"},
        }
        if item.get("source") == "saved_native_pending":
            safe["source"] = "saved_native_pending"
        return safe

    def _read_inbound_proposals(self, health: dict,
                                recipient: str | None = None) -> list[dict]:
        """Read query-only inbound proposals when the exact ACK permits it."""

        if (self.session is None or health.get("status") != "ready"
                or _NATIVE_INBOUND_ALLIANCE_CAPABILITY not in self._installation_capabilities()):
            return []
        # The inbound event is always addressed to the controlled decision
        # country FRA.  A different recipient filter has no matching rows.
        if recipient is not None and recipient != "FRA":
            return []
        reader = getattr(self.session, "read_native_alliance_inbound_offers", None)
        if not callable(reader):
            reader = getattr(self.session, "read_native_inbound_offers", None)
        if not callable(reader):
            return []
        try:
            raw_items = reader()
        except (OSError, TypeError, ValueError, RuntimeError):
            return []
        if not isinstance(raw_items, (list, tuple)):
            return []
        safe_items = []
        seen: set[str] = set()
        for item in raw_items:
            safe = self._safe_inbound_proposal(item)
            if safe is None or safe["proposal_id"] in seen:
                continue
            seen.add(safe["proposal_id"])
            capability = _inbound_response_capability(safe["action_id"])
            if capability in self._installation_capabilities():
                safe["execute"] = {"accept": "native_inbound_response",
                                   "reject": "native_inbound_response"}
            safe_items.append(safe)
        return safe_items

    def _find_inbound_proposal(self, health: dict, public_id: object) -> dict | None:
        if not isinstance(public_id, str):
            return None
        return next((item for item in self._read_inbound_proposals(health)
                     if item["proposal_id"] == public_id), None)

    def _private_inbound_context(self, health: dict, public_id: object,
                                 action_id: str | None = None) -> dict | None:
        """Resolve an opaque proposal only for the private native adapter."""

        if (self.session is None or health.get("status") != "ready"
                or _NATIVE_INBOUND_ALLIANCE_CAPABILITY not in self._installation_capabilities()
                or not isinstance(public_id, str)):
            return None
        resolver = getattr(self.session, "_native_alliance_inbound_context", None)
        if not callable(resolver):
            return None
        try:
            context = resolver(public_id)
        except (OSError, TypeError, ValueError, RuntimeError):
            return None
        if not isinstance(context, dict):
            return None
        context_action = context.get("action_id", "offer_alliance")
        context_family = _inbound_family(context_action)
        if (context.get("recipient") != "FRA"
                or not isinstance(context.get("actor"), str)
                or not re.fullmatch(r"[A-Z0-9]{3}", context["actor"])
                or context["actor"] == "FRA"
                or ObserverSession._safe_native_proposal_id(
                    context.get("native_proposal_id")) is None
                or context.get("session_id") != getattr(self.session, "session_id", None)
                or context_family is None
                or context.get("family", context_family) != context_family
                or (action_id is not None and context_action != action_id)):
            return None
        return {
            "actor": context["actor"],
            "recipient": "FRA",
            "native_proposal_id": context["native_proposal_id"],
            "session_id": context["session_id"],
            "action_id": context_action,
            "family": context_family,
        }

    @staticmethod
    def _native_offer_scope(action_id: str, actor: str, phase: str) -> bool:
        return action_id == "offer_alliance" and actor == "FRA" and phase == "initiate"

    @staticmethod
    def _native_royal_scope(action_id: str, actor: str, phase: str) -> bool:
        return (action_id in ("offer_royal_marriage", "break_royal_ties")
                and actor == "FRA" and phase == "initiate")

    @staticmethod
    def _native_improve_scope(action_id: str, actor: str, phase: str) -> bool:
        return (action_id in ("improve_relations", "stop_improving_relations")
                and actor == "FRA" and phase == "initiate")

    @staticmethod
    def _native_spy_network_scope(action_id: str, actor: str, phase: str) -> bool:
        return (action_id in ("build_spy_network", "stop_building_spy_network")
                and actor == "FRA" and phase == "initiate")

    @staticmethod
    def _native_guarantee_scope(action_id: str, actor: str, phase: str) -> bool:
        return (action_id in ("proclaim_guarantee", "revoke_guarantee")
                and actor == "FRA" and phase == "initiate")

    @staticmethod
    def _native_support_independence_scope(action_id: str, actor: str, phase: str) -> bool:
        return (action_id in ("support_independence", "revoke_support_independence")
                and actor == "FRA" and phase == "initiate")

    @staticmethod
    def _native_military_access_scope(action_id: str, actor: str, phase: str) -> bool:
        return (action_id in ("ask_military_access", "cancel_military_access")
                and actor == "FRA" and phase == "initiate")

    @staticmethod
    def _native_insult_scope(action_id: str, actor: str, phase: str) -> bool:
        return action_id in _INSULT_ACTIONS and actor == "FRA" and phase == "initiate"

    @staticmethod
    def _native_rival_scope(action_id: str, actor: str, phase: str) -> bool:
        return action_id in _RIVAL_ACTIONS and actor == "FRA" and phase == "initiate"

    @staticmethod
    def _native_vassalization_scope(action_id: str, actor: str, phase: str) -> bool:
        return (action_id in _VASSALIZATION_ACTIONS
                and actor == "FRA" and phase == "initiate")

    @staticmethod
    def _native_declare_war_scope(action_id: str, actor: str, phase: str) -> bool:
        return action_id == "declare_war" and actor == "FRA" and phase == "initiate"

    @staticmethod
    def _public_submission_receipt(receipt: object, request_id: str,
                                    actor: str, recipient: str, phase: str,
                                    date_raw: object,
                                    action_id: str = "offer_alliance") -> dict | None:
        """Validate and copy only the safe receipt fields into the journal."""

        wanted_date = ObserverSession._safe_submission_date(date_raw)
        if (not isinstance(receipt, dict) or wanted_date is None
                or not isinstance(recipient, str) or not re.fullmatch(r"[A-Z]{3}", recipient)):
            return None
        actual_date = ObserverSession._safe_submission_date(receipt.get("date_raw"))
        if (receipt.get("event") != "native_alliance_submission_result"
                or receipt.get("request_id") != request_id
                or receipt.get("action_id") != action_id
                or receipt.get("actor") != actor
                or receipt.get("recipient") != recipient
                or receipt.get("phase") != phase
                or actual_date is None
                or actual_date != wanted_date
                or receipt.get("submitted") is not True
                or receipt.get("native_queue_verified") is not True
                or not ObserverSession._transport_receipt_present(receipt)):
            return None
        sequence = ObserverSession._safe_submission_sequence(receipt.get("native_sequence"))
        origin = ObserverSession._safe_submission_origin(receipt.get("native_origin"))
        flags = ObserverSession._safe_submission_flags(receipt.get("native_flags"))
        if sequence is None or origin is None or flags is None:
            return None
        return {
            "event": "native_alliance_submission_result",
            "request_id": request_id,
            "action_id": action_id,
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": wanted_date,
            "submitted": True,
            "native_queue_verified": True,
            "transport_ring": True,
            "transport_ring_receipt": True,
            "native_sequence": sequence,
            "native_origin": origin,
            "native_flags": flags,
        }

    @staticmethod
    def _public_vassalization_submission_receipt(
            receipt: object, request_id: str, actor: str,
            recipient: str, phase: str, date_raw: object,
            action_id: str) -> dict | None:
        """Validate the family discriminator on a Vassalization receipt."""

        if not isinstance(receipt, dict) or receipt.get("family") != "vassalization":
            return None
        safe = DiplomacyTools._public_submission_receipt(
            receipt, request_id, actor, recipient, phase, date_raw, action_id)
        if safe is not None:
            safe["family"] = "vassalization"
        return safe

    @staticmethod
    def _public_vassalization_inbound_submission_receipt(
            receipt: object, request_id: str, actor: str,
            recipient: str, phase: str, date_raw: object,
            action_id: str) -> dict | None:
        """Validate and retain the Vassalization family on inbound receipts."""

        if not isinstance(receipt, dict) or receipt.get("family") != "vassalization":
            return None
        safe = DiplomacyTools._public_submission_receipt(
            receipt, request_id, actor, recipient, phase, date_raw, action_id)
        if safe is not None:
            safe["family"] = "vassalization"
        return safe

    @staticmethod
    def _public_rival_submission_receipt(receipt: object, request_id: str,
                                         actor: str, recipient: str, phase: str,
                                         date_raw: object, action_id: str) -> dict | None:
        """Validate the already-reduced Rival receipt stored by the journal."""

        wanted_date = ObserverSession._safe_submission_date(date_raw)
        actual_date = (ObserverSession._safe_submission_date(receipt.get("date_raw"))
                        if isinstance(receipt, dict) else None)
        if (not isinstance(receipt, dict) or action_id not in _RIVAL_ACTIONS
                or wanted_date is None or actual_date != wanted_date
                or receipt.get("event") != "native_rival_submission_result"
                or receipt.get("request_id") != request_id
                or receipt.get("action_id") != action_id
                or receipt.get("family") != "rival"
                or receipt.get("actor") != actor
                or receipt.get("recipient") != recipient
                or receipt.get("phase") != phase
                or receipt.get("submitted") is not True
                or receipt.get("request_binding_verified") is not True
                or receipt.get("protocol_verified") is not True):
            return None
        return {
            "event": "native_rival_submission_result",
            "request_id": request_id,
            "action_id": action_id,
            "family": "rival",
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": wanted_date,
            "submitted": True,
            "request_binding_verified": True,
            "protocol_verified": True,
        }

    @staticmethod
    def _public_declare_war_submission_receipt(
            receipt: object, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: object, parameters: object) -> dict | None:
        """Validate the already-reduced Declare War receipt in the journal."""

        wanted_date = ObserverSession._safe_submission_date(date_raw)
        try:
            selected = ObserverSession._normalize_declare_war_selection(parameters)
        except (TypeError, ValueError):
            selected = None
        if (selected is None or not isinstance(receipt, dict)
                or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z]{3}", recipient) is None
                or recipient == "FRA"
                or wanted_date is None
                or ObserverSession._safe_submission_date(receipt.get("date_raw")) != wanted_date):
            return None
        if (any(receipt.get(field) != expected for field, expected in (
                ("event", "native_declare_war_submission_result"),
                ("request_id", request_id), ("action_id", "declare_war"),
                ("family", "declare_war"), ("actor", actor),
                ("recipient", recipient), ("phase", phase),
                ("casus_belli", selected["casus_belli"]),
                ("war_goal_province", selected["province_id"]),
                 ("war_goal_beneficiary", selected["beneficiary"]))) or
                receipt.get("submitted") is not True
                or receipt.get("transport_verified") is not True
                or receipt.get("request_binding_verified") is not True):
            return None
        return {
            "event": "native_declare_war_submission_result",
            "request_id": request_id,
            "action_id": "declare_war",
            "family": "declare_war",
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": wanted_date,
            "casus_belli": selected["casus_belli"],
            "war_goal_province": selected["province_id"],
            "war_goal_beneficiary": selected["beneficiary"],
            "submitted": True,
            "transport_verified": True,
            "request_binding_verified": True,
        }

    @staticmethod
    def _public_peace_submission_receipt(
            receipt: object, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: object, action_id: str,
            parameters: object) -> dict | None:
        """Revalidate the reduced Peace receipt before journal persistence."""

        wanted_date = ObserverSession._safe_submission_date(date_raw)
        fields = ObserverSession._peace_execution_fields(parameters)
        if (fields is None or not isinstance(receipt, dict)
                or action_id not in _PEACE_EXECUTION_ACTIONS
                or actor != "FRA" or phase != "initiate"
                or not isinstance(recipient, str)
                or re.fullmatch(r"[A-Z0-9]{3}", recipient) is None
                or recipient == "FRA" or wanted_date is None
                or ObserverSession._safe_submission_date(receipt.get("date_raw")) != wanted_date):
            return None
        (war_id, direction, amount_raw, province_ids, beneficiary,
         reparations_payer, reparations_claimant, term_mask) = fields
        if (receipt.get("event") != "native_peace_submission_result"
                or receipt.get("request_id") != request_id
                or receipt.get("action_id") != action_id
                or receipt.get("family") != "peace"
                or receipt.get("actor") != actor
                or receipt.get("recipient") != recipient
                or receipt.get("phase") != phase
                or receipt.get("war_id") != war_id
                or receipt.get("direction") != direction
                or receipt.get("amount_raw") != amount_raw
                or receipt.get("province_ids") != province_ids
                or receipt.get("beneficiary") != beneficiary
                or (term_mask and receipt.get("term_mask") != term_mask)
                or (not term_mask and receipt.get("term_mask") not in (None, ""))
                or receipt.get("submitted") is not True
                or receipt.get("transport_verified") is not True
                or receipt.get("request_binding_verified") is not True):
            return None
        return {
            "event": "native_peace_submission_result",
            "request_id": request_id, "action_id": action_id, "family": "peace",
            "actor": actor, "recipient": recipient, "phase": phase,
            "date_raw": wanted_date, "war_id": war_id,
            "direction": direction, "amount_raw": amount_raw,
            "province_ids": list(province_ids), "beneficiary": beneficiary,
            **({"term_mask": term_mask,
                "reparations_payer": reparations_payer,
                "reparations_claimant": reparations_claimant}
               if term_mask else {}),
            "submitted": True, "transport_verified": True,
            "request_binding_verified": True,
        }

    @staticmethod
    def _native_submission_context(record: object) -> tuple | None:
        """Return only a fully bound, previously recorded native submission."""

        payload = getattr(record, "payload", None)
        receipt = getattr(record, "native_receipt", None)
        request_id = getattr(record, "request_id", None)
        session_id = getattr(record, "session_id", None)
        if (not isinstance(payload, dict)
                or payload.get("action_id") not in ("offer_alliance", "dissolve_alliance",
                                                     "offer_royal_marriage", "break_royal_ties",
                                                     "improve_relations", "stop_improving_relations",
                                                     "build_spy_network", "stop_building_spy_network",
                                                     "proclaim_guarantee", "revoke_guarantee",
                                                      "support_independence", "revoke_support_independence",
                                                      "ask_military_access", "cancel_military_access",
                                                      "send_insult", "scornful_insult",
                                                      "set_rival", "remove_rival",
                                                       "offer_vassalization", "cancel_vassalization",
                                                        "declare_war",
                                                        "white_peace", "demand_ducats",
                                                        "cede_province", "war_reparations")
                or payload.get("actor") != "FRA" or payload.get("phase") != "initiate"
                or not isinstance(request_id, str) or not isinstance(session_id, str)
                or not isinstance(receipt, dict)):
            return None
        parameters = payload.get("parameters")
        action_id = payload.get("action_id")
        if action_id in _VASSALIZATION_ACTIONS:
            if parameters != {}:
                return None
            actor = payload.get("actor")
            recipient = payload.get("recipient")
            phase = payload.get("phase")
            date_raw = ObserverSession._safe_submission_date(receipt.get("date_raw"))
            safe_receipt = DiplomacyTools._public_vassalization_submission_receipt(
                receipt, request_id, actor, recipient, phase, date_raw, action_id)
            if safe_receipt is None:
                return None
            return actor, recipient, phase, date_raw
        if action_id in _RIVAL_ACTIONS:
            if parameters != {}:
                return None
            actor = payload.get("actor")
            recipient = payload.get("recipient")
            phase = payload.get("phase")
            date_raw = ObserverSession._safe_submission_date(receipt.get("date_raw"))
            safe_receipt = DiplomacyTools._public_rival_submission_receipt(
                receipt, request_id, actor, recipient, phase, date_raw, action_id)
            if safe_receipt is None:
                return None
            return actor, recipient, phase, date_raw
        if action_id == "declare_war":
            try:
                selected = ObserverSession._normalize_declare_war_selection(parameters)
            except (TypeError, ValueError):
                selected = None
            if selected is None:
                return None
            actor = payload.get("actor")
            recipient = payload.get("recipient")
            phase = payload.get("phase")
            date_raw = ObserverSession._safe_submission_date(receipt.get("date_raw"))
            safe_receipt = DiplomacyTools._public_declare_war_submission_receipt(
                receipt, request_id, actor, recipient, phase, date_raw, selected)
            if safe_receipt is None:
                return None
            return actor, recipient, phase, date_raw, selected
        if action_id in _PEACE_EXECUTION_ACTIONS:
            try:
                normalized = normalize_peace_execution_parameters(
                    action_id, payload.get("actor"), payload.get("recipient"),
                    payload.get("phase"), parameters)
            except (TypeError, ValueError):
                return None
            fields = ObserverSession._peace_execution_fields(normalized)
            actor = payload.get("actor")
            recipient = payload.get("recipient")
            phase = payload.get("phase")
            date_raw = ObserverSession._safe_submission_date(receipt.get("date_raw"))
            if (fields is None or not isinstance(actor, str)
                    or not isinstance(recipient, str) or not isinstance(phase, str)
                    or date_raw is None):
                return None
            (war_id, direction, amount_raw, province_ids, beneficiary,
             reparations_payer, reparations_claimant, term_mask) = fields
            if (receipt.get("event") != "native_peace_submission_result"
                    or receipt.get("family") != "peace"
                    or receipt.get("request_id") != request_id
                    or receipt.get("action_id") != action_id
                    or receipt.get("actor") != actor
                    or receipt.get("recipient") != recipient
                    or receipt.get("phase") != phase
                    or receipt.get("submitted") is not True
                    or receipt.get("transport_verified") is not True
                    or receipt.get("request_binding_verified") is not True
                    or receipt.get("war_id") != war_id
                    or receipt.get("direction") != direction
                    or receipt.get("amount_raw") != amount_raw
                    or receipt.get("province_ids") != province_ids
                    or receipt.get("beneficiary") != beneficiary):
                return None
            if ((term_mask and receipt.get("term_mask") != term_mask)
                    or (not term_mask and receipt.get("term_mask") not in (None, ""))):
                return None
            return actor, recipient, phase, date_raw, normalized
        if action_id == "send_insult":
            if parameters != {}:
                return None
            insult_id = -1
        elif action_id == "scornful_insult":
            if (not isinstance(parameters, dict) or set(parameters) != {"insult_id"}
                    or ObserverSession._safe_int(parameters.get("insult_id"), 0, 2147483647) is None):
                return None
            insult_id = parameters["insult_id"]
        elif parameters != {}:
            return None
        else:
            insult_id = None
        actor = payload.get("actor")
        recipient = payload.get("recipient")
        phase = payload.get("phase")
        date_raw = ObserverSession._safe_submission_date(receipt.get("date_raw"))
        if (not isinstance(recipient, str) or not re.fullmatch(r"[A-Z]{3}", recipient)
                or not isinstance(actor, str) or not isinstance(phase, str)
                or date_raw is None
                or receipt.get("event") != "native_alliance_submission_result"
                or receipt.get("request_id") != request_id
                or receipt.get("action_id") != payload["action_id"]
                or receipt.get("actor") != actor
                or receipt.get("recipient") != recipient
                or receipt.get("phase") != phase
                or receipt.get("submitted") is not True
                or receipt.get("native_queue_verified") is not True
                or not ObserverSession._transport_receipt_present(receipt)
                or ObserverSession._safe_submission_sequence(receipt.get("native_sequence")) is None
                or ObserverSession._safe_submission_origin(receipt.get("native_origin")) is None
                or ObserverSession._safe_submission_flags(receipt.get("native_flags")) is None):
            return None
        if action_id in _INSULT_ACTIONS:
            return actor, recipient, phase, date_raw, insult_id
        return actor, recipient, phase, date_raw

    def _native_inbound_submission_context(self, record: object) -> tuple[str, str, str, int, int] | None:
        """Return a bound inbound response context using the private mapping."""

        if self.session is None:
            return None
        payload = getattr(record, "payload", None)
        receipt = getattr(record, "native_receipt", None)
        request_id = getattr(record, "request_id", None)
        session_id = getattr(record, "session_id", None)
        action_id = payload.get("action_id") if isinstance(payload, dict) else None
        family = _inbound_family(action_id) if isinstance(action_id, str) else None
        if (not isinstance(payload, dict) or family is None
                or payload.get("recipient") != "FRA"
                or not isinstance(payload.get("actor"), str)
                or payload["actor"] == "FRA"
                or payload.get("phase") not in ("accept", "reject")
                or not isinstance(request_id, str) or not isinstance(session_id, str)
                or session_id != getattr(self.session, "session_id", None)
                or not isinstance(receipt, dict)):
            return None
        actor = payload["actor"]
        phase = payload["phase"]
        if (not isinstance(actor, str) or not re.fullmatch(r"[A-Z0-9]{3}", actor)
                or actor == "FRA"):
            return None
        parameters = payload.get("parameters")
        public_id = parameters.get("proposal_id") if isinstance(parameters, dict) else None
        if (not isinstance(parameters, dict) or set(parameters) != {"proposal_id"}
                or not isinstance(public_id, str)
                or not re.fullmatch(r"[0-9a-f]{32}", public_id)):
            return None
        resolver = getattr(self.session, "_native_alliance_inbound_context", None)
        if not callable(resolver):
            return None
        try:
            private = resolver(public_id)
        except (OSError, TypeError, ValueError, RuntimeError):
            return None
        if (not isinstance(private, dict) or private.get("actor") != actor
                or private.get("recipient") != "FRA"
                or private.get("session_id") != session_id
                or private.get("action_id", "offer_alliance") != action_id
                or private.get("family", family) != family):
            return None
        native_proposal_id = ObserverSession._safe_native_proposal_id(
            private.get("native_proposal_id"))
        date_raw = ObserverSession._safe_submission_date(receipt.get("date_raw"))
        if native_proposal_id is None or date_raw is None:
            return None
        peace = action_id == "peace_offer"
        expected_receipt_event = (
            "native_peace_inbound_submission_result"
            if peace else "native_alliance_submission_result")
        receipt_ok = (
            receipt.get("event") != expected_receipt_event
                or receipt.get("request_id") != request_id
                or receipt.get("action_id") != action_id
                or receipt.get("actor") != actor
                or receipt.get("recipient") != "FRA"
                or receipt.get("phase") != phase
                or receipt.get("submitted") is not True
                or (receipt.get("transport_verified") is not True
                    if peace else receipt.get("native_queue_verified") is not True)
                or (receipt.get("request_binding_verified") is not True
                    if peace else not ObserverSession._transport_receipt_present(receipt))
                or (not peace and (
                    ObserverSession._safe_submission_sequence(receipt.get("native_sequence")) is None
                    or ObserverSession._safe_submission_origin(receipt.get("native_origin")) is None
                    or ObserverSession._safe_submission_flags(receipt.get("native_flags")) is None)))
        if receipt_ok:
            return None
        if action_id == "offer_vassalization" and receipt.get("family") != "vassalization":
            return None
        if peace and receipt.get("family") != "peace":
            return None
        return actor, "FRA", phase, date_raw, native_proposal_id

    @staticmethod
    def _native_response_event_id(result: dict) -> str:
        serialized = json.dumps(result, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":"), allow_nan=False)
        return "native-response:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _persist_native_response(self, record: object) -> None:
        """Consume one verified response and apply only a legal journal transition."""

        if (getattr(record, "status", None) not in {"submitted", "unknown", "executing", "waiting_response"}
                or getattr(record, "submitted_at", None) is None
                or self.session is None):
            return
        if getattr(record, "session_id", None) != getattr(self.session, "session_id", None):
            return
        context = self._native_submission_context(record)
        inbound_context = context is None
        if context is not None:
            action_id = getattr(record, "payload", {}).get("action_id")
            if action_id == "dissolve_alliance":
                reader_name = "read_native_dissolve_result"
            elif action_id == "break_royal_ties":
                reader_name = "read_native_royal_break_result"
            elif action_id == "offer_royal_marriage":
                reader_name = "read_native_royal_marriage_response"
            elif action_id in ("improve_relations", "stop_improving_relations"):
                reader_name = "read_native_improve_relations_execution"
            elif action_id in ("build_spy_network", "stop_building_spy_network"):
                reader_name = "read_native_spy_network_execution"
            elif action_id in ("proclaim_guarantee", "revoke_guarantee"):
                reader_name = "read_native_guarantee_execution"
            elif action_id == "support_independence":
                reader_name = "read_native_support_independence_response"
            elif action_id == "revoke_support_independence":
                reader_name = "read_native_support_independence_execution"
            elif action_id == "ask_military_access":
                reader_name = "read_native_military_access_response"
            elif action_id == "cancel_military_access":
                reader_name = "read_native_military_access_execution"
            elif action_id in _INSULT_ACTIONS:
                reader_name = "read_native_insult_execution"
            elif action_id == "offer_vassalization":
                reader_name = "read_native_vassalization_response"
            elif action_id == "cancel_vassalization":
                reader_name = "read_native_vassalization_execution"
            elif action_id == "declare_war":
                reader_name = "read_native_declare_war_execution"
            elif action_id in _PEACE_EXECUTION_ACTIONS:
                reader_name = "read_native_peace_execution"
            elif action_id in _RIVAL_ACTIONS:
                reader_name = "read_native_rival_execution"
            else:
                reader_name = "read_native_alliance_response"
            reader = getattr(self.session, reader_name, None)
        else:
            context = self._native_inbound_submission_context(record)
            action_id = getattr(record, "payload", {}).get("action_id")
            reader_name = (
                "read_native_royal_marriage_inbound_response"
                if action_id == "offer_royal_marriage"
                else "read_native_support_independence_inbound_response"
                if action_id == "support_independence"
                else "read_native_military_access_inbound_response"
                if action_id == "ask_military_access"
                else "read_native_vassalization_inbound_response"
                if action_id == "offer_vassalization"
                else "read_native_peace_inbound_response"
                if action_id == "peace_offer"
                else "read_native_alliance_inbound_response")
            reader = getattr(self.session, reader_name, None)
        if context is None or not callable(reader):
            return
        if inbound_context:
            # Family-specific inbound readers already encode the action id;
            # passing it as an extra positional argument would make Support
            # inbound results unreadable because its reader is intentionally
            # narrower than the shared outbound task readers.
            response = reader(getattr(record, "request_id"), *context)
        elif action_id in _INSULT_ACTIONS:
            response = reader(getattr(record, "request_id"), *context[:4], action_id, context[4])
        elif action_id in ("improve_relations", "stop_improving_relations",
                         "build_spy_network", "stop_building_spy_network",
                         "proclaim_guarantee", "revoke_guarantee",
                         "support_independence", "revoke_support_independence",
                         "ask_military_access", "cancel_military_access",
                         "set_rival", "remove_rival"):
            response = reader(getattr(record, "request_id"), *context, action_id)
        elif action_id == "declare_war":
            response = reader(getattr(record, "request_id"), *context[:4], context[4])
        elif action_id in _PEACE_EXECUTION_ACTIONS:
            response = reader(getattr(record, "request_id"), *context[:4], action_id, context[4])
        else:
            response = reader(getattr(record, "request_id"), *context)
        if not isinstance(response, dict):
            return
        status = response.get("status")
        result = response.get("result")
        if status not in {"accepted", "rejected", "executed", "invalidated", "unknown"} or not isinstance(result, dict):
            return
        event_id = self._native_response_event_id(result)
        if status == "executed":
            try:
                self.journal.mark_executed(
                    getattr(record, "request_id"), result,
                    evidence_type="native_execution_consequence", arrival_layer="native_consequence",
                    event_id=event_id, result=result)
            except InvalidTransitionError:
                return
        elif status == "accepted":
            try:
                self.journal.mark_accepted(
                    getattr(record, "request_id"), result,
                    evidence_type="native_response",
                    arrival_layer="native_consequence",
                    event_id=event_id,
                    result=result,
                )
            except InvalidTransitionError:
                return
        elif status == "rejected":
            try:
                self.journal.mark_rejected(
                    getattr(record, "request_id"), result,
                    evidence_type="native_response",
                    arrival_layer="native_response",
                    event_id=event_id,
                    result=result,
                )
            except InvalidTransitionError:
                return
        elif status == "invalidated":
            try:
                self.journal.mark_invalidated(
                    getattr(record, "request_id"), result,
                    evidence_type="native_rival_execution",
                    arrival_layer="native_consequence",
                    event_id=event_id)
            except InvalidTransitionError:
                return
        else:
            self.journal.record_result(
                getattr(record, "request_id"), result,
                evidence_type="native_response",
                arrival_layer="native_response",
                event_id=event_id,
            )

    def reconcile_native_inbound_response(
        self,
        request_id: str,
        native_submission: object,
        native_response: object,
        *,
        native_proposal_id: object,
    ) -> dict:
        """Repair one recorded Royal inbound receipt validation failure.

        The method consumes already observed native events; it never publishes
        a request.  It is intentionally limited to Royal inbound rejection
        records whose durable error is exactly
        ``NATIVE_SUBMISSION_RESULT_INVALID``.  Every request/session/action/
        actor/recipient/phase/date/proposal binding is checked before the
        journal's narrow invalidated-to-rejected reconciliation is called.
        """

        try:
            record = self.journal.lookup_request(request_id)
        except (UnknownRequestError, AmbiguousRequestError):
            return self.get_diplomatic_result(request_id)
        payload = getattr(record, "payload", None)
        old_result = getattr(record, "result", None)
        if (getattr(record, "status", None) != "invalidated"
                or not isinstance(payload, dict)
                or payload.get("action_id") != "offer_royal_marriage"
                or payload.get("recipient") != "FRA"
                or payload.get("phase") not in ("accept", "reject")
                or not isinstance(payload.get("actor"), str)
                or payload.get("actor") == "FRA"
                or not re.fullmatch(r"[A-Z0-9]{3}", payload.get("actor", ""))
                or not isinstance(payload.get("parameters"), dict)
                or set(payload["parameters"]) != {"proposal_id"}
                or not isinstance(payload["parameters"].get("proposal_id"), str)
                or not re.fullmatch(r"[0-9a-f]{32}", payload["parameters"]["proposal_id"])
                or not isinstance(old_result, dict)):
            return self.get_diplomatic_result(request_id)
        old_reason = old_result.get("reason")
        if (not isinstance(old_reason, dict)
                or old_reason.get("code") != "NATIVE_SUBMISSION_RESULT_INVALID"):
            return self.get_diplomatic_result(request_id)
        inspection = old_result.get("inspection")
        session_info = inspection.get("session") if isinstance(inspection, dict) else None
        date_raw = session_info.get("date_raw") if isinstance(session_info, dict) else None
        if ObserverSession._safe_submission_date(date_raw) is None:
            return self.get_diplomatic_result(request_id)
        actor = payload["actor"]
        phase = payload["phase"]
        session_id = getattr(record, "session_id", None)
        action_id = "offer_royal_marriage"
        if not isinstance(session_id, str):
            return self.get_diplomatic_result(request_id)
        if not ObserverSession._valid_native_inbound_submission_result(
                native_submission, request_id, session_id, actor, "FRA", phase,
                date_raw, native_proposal_id, action_id):
            return self.get_diplomatic_result(request_id)
        if not isinstance(native_submission, dict):
            return self.get_diplomatic_result(request_id)
        receipt = ObserverSession._public_native_inbound_submission_receipt(
            native_submission, request_id, actor, phase, date_raw, action_id)
        response = ObserverSession._public_native_inbound_response_result(
            native_response, request_id, session_id, actor, phase, date_raw,
            native_proposal_id, action_id)
        if response is None or response.get("native_outcome") != "rejected":
            return self.get_diplomatic_result(request_id)
        evidence_content = {
            "reconciled_from": "invalidated",
            "original_reason_code": "NATIVE_SUBMISSION_RESULT_INVALID",
            "native_receipt": receipt,
            "native_response": response,
        }
        event_id = "native-reconcile:" + hashlib.sha256(
            json.dumps(evidence_content, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest()
        try:
            self.journal.reconcile_rejected(
                request_id,
                response,
                receipt,
                expected_reason_code="NATIVE_SUBMISSION_RESULT_INVALID",
                expected_payload=payload,
                evidence_content=evidence_content,
                event_id=event_id,
            )
        except (EvidenceConflictError, InvalidTransitionError, ValueError, TypeError):
            # A concurrent reader or a changed journal record must not turn a
            # verified native event into a second write or a generic result.
            return self.get_diplomatic_result(request_id)
        return self.get_diplomatic_result(request_id)

    @staticmethod
    def _execution_result(inspection: dict, code: str, text: str) -> dict:
        return {"submitted": False, "game_outcome": "unknown", "inspection": inspection,
                "reason": reason(code, text, "bridge_policy", True)}

    def _persist_unsubmitted(self, request_id: str, result: dict, *, timeout: bool = False) -> dict:
        """Persist a failed or uncertain hand-off without manufacturing an outcome."""

        if timeout:
            self.journal.mark_unknown(request_id, result,
                                      evidence_type="native_submission_timeout",
                                      arrival_layer="bridge_timeout",
                                      event_id="native-submit-timeout:" + request_id)
        else:
            self.journal.mark_invalidated(request_id, result,
                                          evidence_type="native_submission_failure",
                                          arrival_layer="bridge_validation",
                                          event_id="native-submit-failure:" + request_id)
        return self.get_diplomatic_result(request_id)

    def _execute_native_inbound_response(self, request_id: str, inspection: dict,
                                         actor: str, recipient: str, phase: str) -> dict:
        """Claim, publish and journal one r22 inbound response."""

        date_raw = inspection.get("session", {}).get("date_raw")
        parameters = inspection.get("parameters", {}).get("requested", {})
        public_id = parameters.get("proposal_id") if isinstance(parameters, dict) else None
        action_id = inspection.get("action_id")
        context = self._private_inbound_context(
            inspection.get("session", {}), public_id, action_id)
        if (isinstance(date_raw, bool) or not isinstance(date_raw, int)
                or context is None or context["actor"] != actor
                or context["recipient"] != recipient):
            failed = self._execution_result(
                inspection, "NATIVE_INBOUND_CONTEXT_UNAVAILABLE",
                "执行时没有取得当前入站提议的私有原生绑定，未向游戏提交。")
            return self._persist_unsubmitted(request_id, failed)
        inspection["interface_support"] = {
            **inspection.get("interface_support", {}),
            "execute": "native_inbound_response",
        }
        result = {"submitted": False, "game_outcome": "unknown", "inspection": inspection,
                  "reason": reason("NATIVE_INBOUND_SUBMISSION_PENDING",
                                    "已通过fresh pending与响应规则检查，等待原生提交回执。",
                                    "bridge_policy", False)}
        for status in ("queued", "consumed", "constructed"):
            self.journal.transition(request_id, status, result=result)
        claim = self.journal.claim_submission(request_id, submission_id="native_" + request_id)
        if not claim.claimed:
            if claim.submission_id is not None:
                return self.get_diplomatic_result(request_id)
            busy = self._execution_result(inspection, "EXECUTE_CHANNEL_BUSY",
                                          "另一个请求占用原生提交通道，本请求未发送。")
            return self._persist_unsubmitted(request_id, busy)
        submitter = getattr(self.session, "submit_native_inbound_response", None)
        if not callable(submitter):
            failed = self._execution_result(
                inspection, "NATIVE_INBOUND_RESPONSE_ADAPTER_UNAVAILABLE",
                "当前安装没有可调用的入站响应原生适配。")
            return self._persist_unsubmitted(request_id, failed)
        try:
            if action_id in ("offer_royal_marriage", "support_independence",
                             "ask_military_access", "offer_vassalization",
                             "peace_offer"):
                native = submitter(request_id, actor, recipient, phase, date_raw,
                                   context["native_proposal_id"], action_id=action_id)
            else:
                native = submitter(request_id, actor, recipient, phase, date_raw,
                                   context["native_proposal_id"])
        except Exception:
            unknown = self._execution_result(
                inspection, "NATIVE_INBOUND_SUBMISSION_CALL_UNKNOWN",
                "原生入站响应调用未返回可验证结果，业务结果未知。")
            return self._persist_unsubmitted(request_id, unknown, timeout=True)
        if not isinstance(native, dict):
            failed = self._execution_result(
                inspection, "NATIVE_INBOUND_SUBMISSION_RESULT_INVALID",
                "原生入站响应适配返回了无法验证的结果。")
            return self._persist_unsubmitted(request_id, failed)
        native_status = native.get("status")
        if native_status == "submitted" or native.get("submitted") is True:
            raw_receipt = native.get("receipt", native)
            if (isinstance(raw_receipt, dict)
                    and "native_proposal_id" in raw_receipt):
                valid = ObserverSession._valid_native_inbound_submission_result(
                    raw_receipt, request_id, getattr(self.session, "session_id", ""),
                    actor, recipient, phase, date_raw, context["native_proposal_id"],
                    action_id)
                receipt = (ObserverSession._public_native_inbound_submission_receipt(
                    raw_receipt, request_id, actor, phase, date_raw, action_id)
                    if valid else None)
            else:
                # ObserverSession has already validated the private native id
                # before reducing its receipt.  Revalidate every public-safe
                # field here without requiring that id to enter the result.
                receipt = (
                    self._public_vassalization_inbound_submission_receipt(
                        raw_receipt, request_id, actor, recipient, phase,
                        date_raw, action_id)
                    if action_id == "offer_vassalization" else
                    ObserverSession._public_native_inbound_submission_receipt(
                        raw_receipt, request_id, actor, phase, date_raw, action_id)
                    if action_id == "peace_offer" else
                    self._public_submission_receipt(
                        raw_receipt, request_id, actor, recipient, phase,
                        date_raw, action_id))
                if (actor == "FRA" or phase not in ("accept", "reject")
                        or not isinstance(receipt, dict)):
                    receipt = None
            if receipt is None:
                failed = self._execution_result(
                    inspection, "NATIVE_INBOUND_SUBMISSION_RECEIPT_INVALID",
                    "原生入站响应未提供与当前提议绑定的完整transport回执。")
                return self._persist_unsubmitted(request_id, failed)
            self.journal.mark_submitted(request_id, claim.claim_token, receipt)
            return self.get_diplomatic_result(request_id)
        code = native.get("reason_code")
        if not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9_]{1,80}", code):
            code = "NATIVE_INBOUND_SUBMISSION_FAILED"
        if native_status == "timeout":
            unknown = self._execution_result(
                inspection, code, "原生入站响应等待超时，是否到达游戏未知，未自动重试。")
            return self._persist_unsubmitted(request_id, unknown, timeout=True)
        failed = self._execution_result(
            inspection, code, "原生入站响应没有取得有效transport回执，未标记为已提交。")
        return self._persist_unsubmitted(request_id, failed)

    def _execute_native_peace(self, request_id: str, inspection: dict,
                              actor: str, recipient: str, phase: str,
                              action_id: str) -> dict:
        """Claim, publish and journal one parameter-bound Peace request."""

        date_raw = inspection.get("session", {}).get("date_raw")
        requested = inspection.get("parameters", {}).get("requested")
        try:
            normalized = normalize_peace_execution_parameters(
                action_id, actor, recipient, phase, requested)
        except (TypeError, ValueError):
            normalized = None
        if (normalized is None or ObserverSession._safe_submission_date(date_raw) is None):
            return self._persist_unsubmitted(
                request_id, self._execution_result(
                    inspection, "NATIVE_PEACE_SUBMISSION_SCOPE_INVALID",
                    "当前议和提交的参数、法国决策方、阶段或日期绑定无效，未向游戏提交。"))
        inspection["interface_support"] = {
            **inspection.get("interface_support", {}),
            "execute": "native_peace_submission",
        }
        inspection["authorization"] = {
            "status": "available", "complete": True,
            "reasons": [reason(
                "NATIVE_PEACE_SUBMISSION_CAPABILITY_ACKNOWLEDGED",
                "安装确认允许桥接提交法国发起的议和操作；原生规则复查已单独完成。",
                "installation_capability", True)],
        }
        result = {
            "submitted": False, "game_outcome": "unknown", "inspection": inspection,
            "reason": reason("NATIVE_PEACE_SUBMISSION_PENDING",
                              "已通过议和执行前检查，等待独立原生提交回执。",
                              "bridge_policy", False),
        }
        for status in ("queued", "consumed", "constructed"):
            self.journal.transition(request_id, status, result=result)
        claim = self.journal.claim_submission(request_id, submission_id="native_" + request_id)
        if not claim.claimed:
            if claim.submission_id is not None:
                return self.get_diplomatic_result(request_id)
            return self._persist_unsubmitted(
                request_id, self._execution_result(
                    inspection, "EXECUTE_CHANNEL_BUSY",
                    "另一个请求占用原生提交通道，本请求未发送。"))
        submitter = getattr(self.session, "submit_peace", None)
        if not callable(submitter):
            return self._persist_unsubmitted(
                request_id, self._execution_result(
                    inspection, "NATIVE_PEACE_SUBMISSION_ADAPTER_UNAVAILABLE",
                    "当前安装没有可调用的议和原生提交适配。"))
        try:
            native = submitter(
                request_id, actor, recipient, phase, date_raw, action_id, normalized)
        except Exception:
            return self._persist_unsubmitted(
                request_id, self._execution_result(
                    inspection, "NATIVE_PEACE_SUBMISSION_CALL_UNKNOWN",
                    "议和原生提交调用未返回可验证结果，业务结果未知。"),
                timeout=True)
        if not isinstance(native, dict):
            return self._persist_unsubmitted(
                request_id, self._execution_result(
                    inspection, "NATIVE_PEACE_SUBMISSION_RESULT_INVALID",
                    "议和原生提交适配返回了无法验证的结果。"))
        native_status = native.get("status")
        if native_status == "submitted" or native.get("submitted") is True:
            receipt = self._public_peace_submission_receipt(
                native.get("receipt", native), request_id, actor, recipient,
                phase, date_raw, action_id, normalized)
            if receipt is None:
                return self._persist_unsubmitted(
                    request_id, self._execution_result(
                        inspection, "NATIVE_PEACE_SUBMISSION_RECEIPT_INVALID",
                        "议和原生提交没有提供完整绑定回执。"))
            self.journal.mark_submitted(request_id, claim.claim_token, receipt)
            return self.get_diplomatic_result(request_id)
        code = native.get("reason_code")
        if not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9_]{1,96}", code):
            code = "NATIVE_PEACE_SUBMISSION_FAILED"
        if native_status == "timeout":
            return self._persist_unsubmitted(
                request_id, self._execution_result(
                    inspection, code,
                    "议和原生提交等待超时，是否到达游戏未知，未自动重试。"),
                timeout=True)
        return self._persist_unsubmitted(
            request_id, self._execution_result(
                inspection, code,
                "议和原生提交没有取得有效transport回执，未标记为已提交。"))

    def _execute_native_declare_war(self, request_id: str, inspection: dict,
                                     actor: str, recipient: str, phase: str) -> dict:
        """Claim, publish and journal one authorized parameter-bound war command."""

        date_raw = inspection.get("session", {}).get("date_raw")
        requested = inspection.get("parameters", {}).get("requested")
        try:
            selected = ObserverSession._normalize_declare_war_selection(requested)
        except (TypeError, ValueError):
            selected = None
        if (selected is None or actor != "FRA" or phase != "initiate"
                or ObserverSession._safe_submission_date(date_raw) is None):
            failed = self._execution_result(
                inspection, "NATIVE_DECLARE_WAR_SUBMISSION_SCOPE_INVALID",
                "当前宣战提交的参数、法国决策方、阶段或日期绑定无效，未向游戏提交。")
            return self._persist_unsubmitted(request_id, failed)
        inspection["interface_support"] = {
            **inspection.get("interface_support", {}),
            "execute": "native_declare_war_submission",
        }
        inspection["authorization"] = {
            "status": "available", "complete": True,
            "reasons": [reason(
                "NATIVE_DECLARE_WAR_SUBMISSION_CAPABILITY_ACKNOWLEDGED",
                "安装确认允许桥接提交法国发起的宣战操作；本次宣战参数和原生合法性已经单独复核。",
                "installation_capability", True)],
        }
        result = {
            "submitted": False, "game_outcome": "unknown", "inspection": inspection,
            "reason": reason("NATIVE_DECLARE_WAR_SUBMISSION_PENDING",
                              "已通过宣战执行前检查，等待独立原生提交回执。",
                              "bridge_policy", False),
        }
        for status in ("queued", "consumed", "constructed"):
            self.journal.transition(request_id, status, result=result)
        claim = self.journal.claim_submission(request_id, submission_id="native_" + request_id)
        if not claim.claimed:
            if claim.submission_id is not None:
                return self.get_diplomatic_result(request_id)
            return self._persist_unsubmitted(
                request_id,
                self._execution_result(inspection, "EXECUTE_CHANNEL_BUSY",
                                       "另一个请求占用原生提交通道，本请求未发送。"))
        submitter = getattr(self.session, "submit_declare_war", None)
        if not callable(submitter):
            return self._persist_unsubmitted(
                request_id,
                self._execution_result(
                    inspection, "NATIVE_DECLARE_WAR_SUBMISSION_ADAPTER_UNAVAILABLE",
                    "当前安装没有可调用的宣战原生提交适配。"))
        try:
            native = submitter(request_id, actor, recipient, phase, date_raw,
                               parameters=requested)
        except Exception:
            return self._persist_unsubmitted(
                request_id,
                self._execution_result(
                    inspection, "NATIVE_DECLARE_WAR_SUBMISSION_CALL_UNKNOWN",
                    "宣战原生提交调用未返回可验证结果，业务结果未知。"),
                timeout=True)
        if not isinstance(native, dict):
            return self._persist_unsubmitted(
                request_id,
                self._execution_result(
                    inspection, "NATIVE_DECLARE_WAR_SUBMISSION_RESULT_INVALID",
                    "宣战原生提交适配返回了无法验证的结果。"))
        native_status = native.get("status")
        if native_status == "submitted" or native.get("submitted") is True:
            # ``submit_declare_war`` already reduces the raw native event to
            # the journal-safe receipt.  Re-running the raw-event projector
            # here drops the session_id and makes a valid receipt fail its
            # second binding check.  Validate the reduced shape at this
            # boundary; the session reader remains responsible for reducing
            # the raw native submission event exactly once.
            receipt = DiplomacyTools._public_declare_war_submission_receipt(
                native.get("receipt", native), request_id, actor, recipient,
                phase, date_raw, selected)
            if receipt is None:
                return self._persist_unsubmitted(
                    request_id,
                    self._execution_result(
                        inspection, "NATIVE_DECLARE_WAR_SUBMISSION_RECEIPT_INVALID",
                        "宣战原生提交没有提供完整绑定回执。"))
            self.journal.mark_submitted(request_id, claim.claim_token, receipt)
            return self.get_diplomatic_result(request_id)
        code = native.get("reason_code")
        if not isinstance(code, str) or re.fullmatch(r"[A-Z0-9_]{1,96}", code) is None:
            code = "NATIVE_DECLARE_WAR_SUBMISSION_FAILED"
        if native_status == "timeout":
            return self._persist_unsubmitted(
                request_id,
                self._execution_result(
                    inspection, code,
                    "宣战原生提交等待超时，是否到达游戏未知，未自动重试。"),
                timeout=True)
        return self._persist_unsubmitted(
            request_id,
            self._execution_result(
                inspection, code,
                "宣战原生提交没有取得有效transport回执，未标记为已提交。"))

    def _execute_native_rival(self, request_id: str, inspection: dict,
                              actor: str, recipient: str, phase: str,
                              action_id: str) -> dict:
        """Claim, publish and journal one authorized Rival command."""

        date_raw = inspection.get("session", {}).get("date_raw")
        if (action_id not in _RIVAL_ACTIONS or actor != "FRA"
                or phase != "initiate"
                or ObserverSession._safe_submission_date(date_raw) is None):
            failed = self._execution_result(
                inspection, "NATIVE_RIVAL_SUBMISSION_SCOPE_INVALID",
                "当前宿敌提交的动作、法国决策方或日期绑定无效，未向游戏提交。")
            return self._persist_unsubmitted(request_id, failed)
        inspection["interface_support"] = {
            **inspection.get("interface_support", {}),
            "execute": "native_rival_submission",
        }
        inspection["authorization"] = {
            "status": "available",
            "complete": True,
            "reasons": [reason(
                "NATIVE_RIVAL_SUBMISSION_CAPABILITY_ACKNOWLEDGED",
                "安装确认允许桥接提交法国发起的宿敌操作。",
                "installation_capability", True)],
        }
        result = {
            "submitted": False, "game_outcome": "unknown", "inspection": inspection,
            "reason": reason("NATIVE_RIVAL_SUBMISSION_PENDING",
                              "已通过宿敌执行前检查，等待独立原生提交回执。",
                              "bridge_policy", False),
        }
        for status in ("queued", "consumed", "constructed"):
            self.journal.transition(request_id, status, result=result)
        claim = self.journal.claim_submission(request_id, submission_id="native_" + request_id)
        if not claim.claimed:
            if claim.submission_id is not None:
                return self.get_diplomatic_result(request_id)
            return self._persist_unsubmitted(
                request_id,
                self._execution_result(inspection, "EXECUTE_CHANNEL_BUSY",
                                       "另一个请求占用原生提交通道，本请求未发送。"))
        submitter = getattr(self.session, "submit_" + action_id, None)
        if not callable(submitter):
            return self._persist_unsubmitted(
                request_id,
                self._execution_result(
                    inspection, "NATIVE_RIVAL_SUBMISSION_ADAPTER_UNAVAILABLE",
                    "当前安装没有可调用的宿敌原生提交适配。"))
        try:
            native = submitter(request_id, actor, recipient, phase, date_raw)
        except Exception:
            return self._persist_unsubmitted(
                request_id,
                self._execution_result(
                    inspection, "NATIVE_RIVAL_SUBMISSION_CALL_UNKNOWN",
                    "宿敌原生提交调用未返回可验证结果，业务结果未知。"),
                timeout=True)
        if not isinstance(native, dict):
            return self._persist_unsubmitted(
                request_id,
                self._execution_result(
                    inspection, "NATIVE_RIVAL_SUBMISSION_RESULT_INVALID",
                    "宿敌原生提交适配返回了无法验证的结果。"))
        native_status = native.get("status")
        if native_status == "submitted" or native.get("submitted") is True:
            receipt = self._public_rival_submission_receipt(
                native.get("receipt", native), request_id, actor, recipient,
                phase, date_raw, action_id)
            if receipt is None:
                return self._persist_unsubmitted(
                    request_id,
                    self._execution_result(
                        inspection, "NATIVE_RIVAL_SUBMISSION_RECEIPT_INVALID",
                        "宿敌原生提交没有提供完整绑定回执。"))
            self.journal.mark_submitted(request_id, claim.claim_token, receipt)
            return self.get_diplomatic_result(request_id)
        code = native.get("reason_code")
        if not isinstance(code, str) or re.fullmatch(r"[A-Z0-9_]{1,96}", code) is None:
            code = "NATIVE_RIVAL_SUBMISSION_FAILED"
        if native_status == "timeout":
            return self._persist_unsubmitted(
                request_id,
                self._execution_result(
                    inspection, code,
                    "宿敌原生提交等待超时，是否到达游戏未知，未自动重试。"),
                timeout=True)
        return self._persist_unsubmitted(
            request_id,
            self._execution_result(
                inspection, code,
                "宿敌原生提交没有取得有效transport回执，未标记为已提交。"))

    def _execute_native_offer(self, request_id: str, inspection: dict,
                              actor: str, recipient: str, phase: str,
                              action_id: str = "offer_alliance") -> dict:
        """Claim, publish and journal one capability-authorized alliance offer."""

        date_raw = inspection.get("session", {}).get("date_raw")
        if isinstance(date_raw, bool) or not isinstance(date_raw, int):
            result = self._execution_result(
                inspection, "NATIVE_SUBMISSION_DATE_UNAVAILABLE",
                "执行时没有取得当前原生日期，未向游戏提交。")
            return self._persist_unsubmitted(request_id, result)
        capability = {
            "offer_alliance": _NATIVE_OFFER_SUBMISSION_CAPABILITY,
            "dissolve_alliance": _NATIVE_DISSOLVE_SUBMISSION_CAPABILITY,
            "offer_royal_marriage": _NATIVE_ROYAL_MARRIAGE_SUBMISSION_CAPABILITY,
            "break_royal_ties": _NATIVE_ROYAL_MARRIAGE_SUBMISSION_CAPABILITY,
            "improve_relations": _NATIVE_IMPROVE_RELATIONS_SUBMISSION_CAPABILITY,
            "stop_improving_relations": _NATIVE_IMPROVE_RELATIONS_SUBMISSION_CAPABILITY,
            "build_spy_network": _NATIVE_SPY_NETWORK_SUBMISSION_CAPABILITY,
            "stop_building_spy_network": _NATIVE_SPY_NETWORK_SUBMISSION_CAPABILITY,
            "proclaim_guarantee": _NATIVE_GUARANTEE_SUBMISSION_CAPABILITY,
            "revoke_guarantee": _NATIVE_GUARANTEE_SUBMISSION_CAPABILITY,
            "support_independence": _NATIVE_SUPPORT_INDEPENDENCE_SUBMISSION_CAPABILITY,
            "revoke_support_independence": _NATIVE_SUPPORT_INDEPENDENCE_SUBMISSION_CAPABILITY,
            "ask_military_access": _NATIVE_MILITARY_ACCESS_SUBMISSION_CAPABILITY,
            "cancel_military_access": _NATIVE_MILITARY_ACCESS_SUBMISSION_CAPABILITY,
            "send_insult": _NATIVE_INSULT_SUBMISSION_CAPABILITY,
            "scornful_insult": _NATIVE_INSULT_SUBMISSION_CAPABILITY,
            "offer_vassalization": _NATIVE_VASSALIZATION_SUBMISSION_CAPABILITY,
            "cancel_vassalization": _NATIVE_VASSALIZATION_SUBMISSION_CAPABILITY,
        }.get(action_id)
        if capability is None:
            failed = self._execution_result(
                inspection, "NATIVE_SUBMISSION_ACTION_UNSUPPORTED",
                "当前原生提交适配不支持此动作家族。")
            return self._persist_unsubmitted(request_id, failed)
        description = {
            "dissolve_alliance": "法国主动断绝同盟",
            "offer_royal_marriage": "法国发起王室联姻提议",
            "break_royal_ties": "法国主动断绝王室联姻",
            "improve_relations": "法国开始改善与目标国家的关系",
            "stop_improving_relations": "法国停止改善与目标国家的关系",
            "build_spy_network": "法国开始向目标国家建立间谍网",
            "stop_building_spy_network": "法国停止向目标国家建立间谍网",
            "proclaim_guarantee": "法国向目标国家保证独立",
            "revoke_guarantee": "法国撤销对目标国家的独立保证",
            "support_independence": "法国支持目标国家独立",
            "revoke_support_independence": "法国撤销对目标国家的独立支持",
            "ask_military_access": "法国请求进入目标国家的军事通行权",
            "cancel_military_access": "法国取消进入目标国家的军事通行权",
            "send_insult": "法国向目标国家发起普通侮辱",
            "scornful_insult": "法国向目标国家发起指定轻蔑侮辱",
            "offer_vassalization": "法国向目标国家提议建立附庸关系",
            "cancel_vassalization": "法国取消与目标国家的附庸关系",
        }.get(action_id, "法国发起联盟提议")
        insult_id = None
        if action_id == "send_insult":
            insult_id = -1
        elif action_id == "scornful_insult":
            actual_parameters = inspection.get("parameters", {})
            actual = actual_parameters.get("actual") if isinstance(actual_parameters, dict) else None
            insult_id = actual.get("insult_id") if isinstance(actual, dict) else None
            if ObserverSession._safe_int(insult_id, 0, 2147483647) is None:
                failed = self._execution_result(
                    inspection, "INSULT_PARAMETER_NOT_SELECTED",
                    "轻蔑侮辱尚未选择并复查原生候选编号，未向游戏提交。")
                return self._persist_unsubmitted(request_id, failed)
        inspection["interface_support"] = {**inspection.get("interface_support", {}),
                                            "execute": capability}
        inspection["authorization"] = {
            "status": "available",
            "reasons": [reason(capability.upper() + "_CAPABILITY_ACKNOWLEDGED",
                                "安装确认允许桥接提交" + description + "。",
                                "installation_capability", True)],
            "complete": True,
        }
        result = {"submitted": False, "game_outcome": "unknown", "inspection": inspection,
                  "reason": reason("NATIVE_SUBMISSION_PENDING", "已通过执行前检查，等待原生提交回执。",
                                    "bridge_policy", False)}
        for status in ("queued", "consumed", "constructed"):
            self.journal.transition(request_id, status, result=result)
        claim = self.journal.claim_submission(request_id, submission_id="native_" + request_id)
        if not claim.claimed:
            # A previous claim owns this request.  Never call the submitter a
            # second time; a different active claim is a channel failure.
            if claim.submission_id is not None:
                return self.get_diplomatic_result(request_id)
            busy = self._execution_result(inspection, "EXECUTE_CHANNEL_BUSY",
                                          "另一个请求占用原生提交通道，本请求未发送。")
            return self._persist_unsubmitted(request_id, busy)
        submitter = getattr(self.session, "submit_" + action_id, None)
        if not callable(submitter) and action_id == "offer_alliance":
            submitter = getattr(self.session, "submit_native_offer", None)
        if not callable(submitter) and action_id == "offer_alliance":
            submitter = getattr(self.session, "submit_alliance", None)
        if not callable(submitter):
            failed = self._execution_result(inspection, "NATIVE_SUBMISSION_ADAPTER_UNAVAILABLE",
                                            "当前安装没有可调用的原生外交提交适配。")
            return self._persist_unsubmitted(request_id, failed)
        try:
            if action_id == "send_insult":
                native = submitter(request_id, actor, recipient, phase, date_raw)
            elif action_id == "scornful_insult":
                native = submitter(request_id, actor, recipient, phase, date_raw,
                                   insult_id=insult_id)
            else:
                native = submitter(request_id, actor, recipient, phase, date_raw)
        except Exception:
            # After an acquired claim, the native side may have seen the wire;
            # this is therefore an unknown hand-off, never an automatic retry.
            unknown = self._execution_result(inspection, "NATIVE_SUBMISSION_CALL_UNKNOWN",
                                             "原生提交调用未返回可验证结果，业务结果未知。")
            return self._persist_unsubmitted(request_id, unknown, timeout=True)
        if not isinstance(native, dict):
            failed = self._execution_result(inspection, "NATIVE_SUBMISSION_RESULT_INVALID",
                                            "原生提交适配返回了无法验证的结果。")
            return self._persist_unsubmitted(request_id, failed)
        native_status = native.get("status")
        if native_status == "submitted" or native.get("submitted") is True:
            receipt = (
                self._public_vassalization_submission_receipt(
                    native.get("receipt", native), request_id, actor, recipient,
                    phase, date_raw, action_id)
                if action_id in _VASSALIZATION_ACTIONS else
                self._public_submission_receipt(
                    native.get("receipt", native), request_id, actor, recipient,
                    phase, date_raw, action_id))
            if receipt is None:
                failed = self._execution_result(inspection, "NATIVE_SUBMISSION_RECEIPT_INVALID",
                                                "原生提交未提供完整 transport 回执，未标记为已提交。")
                return self._persist_unsubmitted(request_id, failed)
            self.journal.mark_submitted(request_id, claim.claim_token, receipt)
            return self.get_diplomatic_result(request_id)
        code = native.get("reason_code")
        if not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9_]{1,80}", code):
            code = "NATIVE_SUBMISSION_FAILED"
        if native_status == "timeout":
            unknown = self._execution_result(inspection, code,
                                             "原生提交等待超时，是否到达游戏未知，未自动重试。")
            return self._persist_unsubmitted(request_id, unknown, timeout=True)
        failed = self._execution_result(inspection, code,
                                        "原生提交没有取得有效 transport 回执，未标记为已提交。")
        return self._persist_unsubmitted(request_id, failed)

    @staticmethod
    def _public_acceptance_items(raw_items: object, metadata_acknowledged: bool = False) -> list[dict]:
        if not isinstance(raw_items, (list, tuple)):
            return []
        items = []
        for raw in raw_items[:_MAX_REASON_ITEMS]:
            if not isinstance(raw, dict):
                continue
            name = raw.get("name")
            if not isinstance(name, str) or not name.strip() or len(name.encode("utf-8")) > 1024:
                name = None
            native_value = raw.get("native_value")
            if (isinstance(native_value, bool) or not isinstance(native_value, int)
                    or native_value < -2147483648 or native_value > 2147483647):
                native_value = None
            value_verified = (metadata_acknowledged and native_value is not None
                              and raw.get("native_value_verified") is True
                              and raw.get("value_representation") == "signed_int32"
                              and raw.get("value_normalized") is False)
            identifier = raw.get("native_identifier")
            identifier_verified = (value_verified and raw.get("identifier_verified") is True
                                   and raw.get("identity_source") == "native_localization_key"
                                   and isinstance(identifier, str)
                                   and re.fullmatch(r"DIPLO_[A-Z0-9_]{1,41}", identifier) is not None)
            items.append({
                "name": name,
                "text_decoded": raw.get("text_decoded") is True,
                "native_value": native_value,
                "source": "native_rule",
                "complete": False,
                "text_encoding_verified": False,
                "text_complete": False,
                "native_identifier": identifier if identifier_verified else None,
                "identifier_verified": identifier_verified,
                "identity_source": "native_localization_key" if identifier_verified else None,
                "native_value_verified": value_verified,
                "value_representation": "signed_int32" if value_verified else "unknown",
                "value_normalized": False,
                "unit": "unknown",
                "unit_verified": False,
                "truncated": raw.get("truncated") is True,
            })
        return items

    @staticmethod
    def _normalize_peace_money_amount(value: object) -> int:
        """Convert one-decimal ducats to the native currency integer."""

        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ValueError("PEACE_MONEY_AMOUNT_INVALID")
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError("PEACE_MONEY_AMOUNT_INVALID") from None
        if (not amount.is_finite() or amount <= 0
                or amount.as_tuple().exponent < -1
                or amount > Decimal("2147483.647")):
            raise ValueError("PEACE_MONEY_AMOUNT_INVALID")
        raw = amount * Decimal(1000)
        if raw != raw.to_integral_value():
            raise ValueError("PEACE_MONEY_AMOUNT_INVALID")
        normalized = int(raw)
        if (normalized <= 0 or normalized > 2147483647
                or normalized % 100 != 0):
            raise ValueError("PEACE_MONEY_AMOUNT_INVALID")
        return normalized

    @staticmethod
    def _normalize_peace_money_offer_parameters(
            parameters: object, actor: str, recipient: str) -> dict:
        """Validate a minimal money selection in either direction."""

        if (not isinstance(parameters, dict)
                or set(parameters) != {"peace_context"}):
            raise ValueError("PEACE_MONEY_PARAMETERS_REQUIRED")
        context = parameters.get("peace_context")
        if (not isinstance(context, dict)
                or set(context) != {"war_id", "direction", "terms"}
                or not isinstance(context.get("war_id"), str)
                or re.fullmatch(_PEACE_WAR_ID_PATTERN, context["war_id"]) is None
                or context.get("direction") not in ("demand", "offer")
                or not isinstance(context.get("terms"), list)
                or len(context["terms"]) != 1):
            raise ValueError("PEACE_MONEY_CONTEXT_INVALID")
        term = context["terms"][0]
        if (not isinstance(term, dict)
                or set(term) != {"action_id", "amount", "payer", "claimant"}
                or term.get("action_id") != "demand_ducats"
                or term.get("payer") != (
                    actor if context["direction"] == "offer" else recipient)
                or term.get("claimant") != (
                    recipient if context["direction"] == "offer" else actor)):
            raise ValueError("PEACE_MONEY_TERM_INVALID")
        amount_raw = DiplomacyTools._normalize_peace_money_amount(
            term.get("amount"))
        return {
            "war_id": context["war_id"],
            "direction": context["direction"],
            "amount_raw": amount_raw,
            "payer": actor if context["direction"] == "offer" else recipient,
            "claimant": recipient if context["direction"] == "offer" else actor,
        }

    @staticmethod
    def _normalize_peace_province_offer_parameters(
            parameters: object, actor: str, recipient: str) -> dict:
        """Validate a QUERY6/QUERY7 candidate or selected province context."""
        if (not isinstance(parameters, dict)
                or set(parameters) != {"peace_context"}):
            raise ValueError("PEACE_PROVINCE_PARAMETERS_REQUIRED")
        context = parameters.get("peace_context")
        if (not isinstance(context, dict)
                or set(context) != {"war_id", "direction", "terms"}
                or not isinstance(context.get("war_id"), str)
                or re.fullmatch(_PEACE_WAR_ID_PATTERN,
                                context["war_id"]) is None
                or context.get("direction") not in ("demand", "offer")
                or not isinstance(context.get("terms"), list)
                or len(context["terms"]) > 1):
            raise ValueError("PEACE_PROVINCE_CONTEXT_INVALID")
        terms = context["terms"]
        if not terms:
            return {
                "war_id": context["war_id"], "direction": context["direction"],
                "province_ids": [], "beneficiary": None,
            }
        term = terms[0]
        if (not isinstance(term, dict)
                or set(term) != {"action_id", "province_ids", "beneficiary"}
                or term.get("action_id") != "cede_province"
                or not isinstance(term.get("province_ids"), list)
                or not 1 <= len(term["province_ids"]) <= 16):
            raise ValueError("PEACE_PROVINCE_TERM_INVALID")
        province_ids = term["province_ids"]
        if any(isinstance(value, bool) or not isinstance(value, int)
               or value < 1 or value > 2147483647
               for value in province_ids):
            raise ValueError("PEACE_PROVINCE_IDS_INVALID")
        if len(set(province_ids)) != len(province_ids):
            raise ValueError("PEACE_PROVINCE_IDS_INVALID")
        beneficiary = term.get("beneficiary")
        if (not isinstance(beneficiary, str)
                or re.fullmatch(r"[A-Z0-9]{3}", beneficiary) is None):
            raise ValueError("PEACE_PROVINCE_BENEFICIARY_INVALID")
        return {
            "war_id": context["war_id"], "direction": context["direction"],
            "province_ids": list(province_ids), "beneficiary": beneficiary,
        }

    @staticmethod
    def _normalize_peace_empty_offer_parameters(parameters: object) -> str:
        """Validate the inspect-only minimal QUERY4/QUERY7 selection."""

        if (not isinstance(parameters, dict)
                or set(parameters) != {"peace_context"}):
            raise ValueError("PEACE_EMPTY_OFFER_PARAMETERS_REQUIRED")
        context = parameters.get("peace_context")
        if (not isinstance(context, dict)
                or set(context) not in ({"war_id", "terms"}, {"war_id", "direction", "terms"})
                or context.get("direction", "demand") not in ("demand", "offer")
                or not isinstance(context.get("war_id"), str)
                or re.fullmatch(_PEACE_WAR_ID_PATTERN, context["war_id"]) is None
                or context.get("terms") != []):
            raise ValueError("PEACE_EMPTY_OFFER_CONTEXT_INVALID")
        return context["war_id"]

    @staticmethod
    def _validate(action_id: str, actor: str, recipient: str, phase: str,
                  parameters: dict, *, allow_peace_discovery: bool = False,
                  allow_peace_empty_offer: bool = False,
                  allow_peace_money_offer: bool = False,
                  allow_peace_province_offer: bool = False) -> None:
        if action_id not in ACTIONS and action_id not in INBOUND_ACTIONS:
            raise ValueError("UNKNOWN_ACTION_ID")
        if not all(isinstance(tag, str) and re.fullmatch(r"[A-Z0-9]{3}", tag) for tag in (actor, recipient)):
            raise ValueError("INVALID_COUNTRY_TAG")
        if actor == recipient:
            raise ValueError("ACTOR_RECIPIENT_IDENTICAL")
        if phase not in ("initiate", "accept", "reject", "withdraw"):
            raise ValueError("INVALID_PHASE")
        if not isinstance(parameters, dict):
            raise ValueError("PARAMETERS_MUST_BE_OBJECT")
        encoded = json.dumps(parameters, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode("utf-8")) > 16384:
            raise ValueError("PARAMETERS_TOO_LARGE")
        if action_id == "peace_offer":
            if (not re.fullmatch(r"[A-Z0-9]{3}", actor)
                    or actor == "FRA" or recipient != "FRA"
                    or phase not in ("accept", "reject")):
                raise ValueError("PEACE_INBOUND_RESPONSE_PHASE_UNSUPPORTED")
            if (set(parameters) != {"proposal_id"}
                    or not isinstance(parameters.get("proposal_id"), str)
                    or re.fullmatch(r"[0-9a-f]{32}", parameters["proposal_id"]) is None):
                raise ValueError("INBOUND_RESPONSE_PARAMETERS_UNSUPPORTED")
            return
        peace_discovery = (
            ACTIONS[action_id].category == "peace_term"
            and allow_peace_discovery and phase == "initiate"
            and parameters == {})
        selected_context = (
            parameters.get("peace_context")
            if isinstance(parameters, dict) else None)
        peace_empty_offer = (
            action_id == "white_peace"
            and allow_peace_empty_offer and phase == "initiate"
            and isinstance(selected_context, dict)
            and selected_context.get("terms") == [])
        peace_money_offer = (
            action_id == "demand_ducats"
            and allow_peace_money_offer
            and phase == "initiate"
            and isinstance(selected_context, dict))
        peace_province_offer = (
            action_id == "cede_province"
            and allow_peace_province_offer
            and phase == "initiate"
            and isinstance(selected_context, dict))
        if peace_empty_offer:
            DiplomacyTools._normalize_peace_empty_offer_parameters(parameters)
        if peace_money_offer:
            DiplomacyTools._normalize_peace_money_offer_parameters(
                parameters, actor, recipient)
        if peace_province_offer:
            DiplomacyTools._normalize_peace_province_offer_parameters(
                parameters, actor, recipient)
        if ACTIONS[action_id].category == "peace_term" \
                and not peace_discovery and not peace_empty_offer \
                and not peace_money_offer and not peace_province_offer:
            context = parameters.get("peace_context")
            required = ("war_id", "direction", "actor_war_role", "recipient_war_role", "terms")
            if not isinstance(context, dict) or any(key not in context for key in required):
                raise ValueError("PEACE_CONTEXT_REQUIRED")
            if context["direction"] not in ("demand", "offer") or not isinstance(context["war_id"], str):
                raise ValueError("INVALID_PEACE_CONTEXT")
            if not isinstance(context["terms"], list):
                raise ValueError("INVALID_PEACE_TERMS")
            if not any(isinstance(term, dict) and term.get("action_id") == action_id for term in context["terms"]):
                raise ValueError("ACTION_MISSING_FROM_FULL_PEACE_PROPOSAL")
        if action_id == "declare_war":
            if phase != "initiate":
                raise ValueError("DECLARE_WAR_INITIATE_ONLY")
            ObserverSession._normalize_declare_war_parameters(parameters)
        if action_id in ("offer_alliance", "dissolve_alliance") and phase == "initiate" and parameters:
            raise ValueError("OFFER_ALLIANCE_PARAMETERS_UNSUPPORTED")
        if action_id in ("offer_royal_marriage", "break_royal_ties") \
                and phase == "initiate" and parameters:
            raise ValueError("ROYAL_MARRIAGE_PARAMETERS_UNSUPPORTED")
        if action_id in ("improve_relations", "stop_improving_relations") \
                and phase != "initiate":
            raise ValueError("IMPROVE_RELATIONS_INITIATE_ONLY")
        if action_id in ("improve_relations", "stop_improving_relations") \
                and phase == "initiate" and parameters:
            raise ValueError("IMPROVE_RELATIONS_PARAMETERS_UNSUPPORTED")
        if action_id in ("build_spy_network", "stop_building_spy_network") \
                and phase != "initiate":
            raise ValueError("SPY_NETWORK_INITIATE_ONLY")
        if action_id in ("build_spy_network", "stop_building_spy_network") \
                and phase == "initiate" and parameters:
            raise ValueError("SPY_NETWORK_PARAMETERS_UNSUPPORTED")
        if action_id in ("proclaim_guarantee", "revoke_guarantee") \
                and phase != "initiate":
            raise ValueError("GUARANTEE_INITIATE_ONLY")
        if action_id in ("proclaim_guarantee", "revoke_guarantee") \
                and phase == "initiate" and parameters:
            raise ValueError("GUARANTEE_PARAMETERS_UNSUPPORTED")
        if action_id in ("set_rival", "remove_rival") and phase != "initiate":
            raise ValueError("RIVAL_INITIATE_ONLY")
        if action_id in ("set_rival", "remove_rival") \
                and phase == "initiate" and parameters:
            raise ValueError("RIVAL_PARAMETERS_UNSUPPORTED")
        if action_id == "cancel_vassalization" and phase != "initiate":
            raise ValueError("VASSALIZATION_INITIATE_ONLY")
        if action_id == "offer_vassalization" and phase not in ("initiate", "accept", "reject"):
            raise ValueError("VASSALIZATION_PHASE_UNSUPPORTED")
        if action_id in _VASSALIZATION_ACTIONS \
                and phase == "initiate" and parameters:
            raise ValueError("VASSALIZATION_PARAMETERS_UNSUPPORTED")
        if action_id == "revoke_support_independence" and phase != "initiate":
            raise ValueError("SUPPORT_INDEPENDENCE_INITIATE_ONLY")
        if action_id == "revoke_support_independence" and phase == "initiate" and parameters:
            raise ValueError("SUPPORT_INDEPENDENCE_PARAMETERS_UNSUPPORTED")
        if action_id == "support_independence" and phase not in ("initiate", "accept", "reject"):
            raise ValueError("SUPPORT_INDEPENDENCE_PHASE_UNSUPPORTED")
        if action_id == "support_independence" and phase == "initiate" and parameters:
            raise ValueError("SUPPORT_INDEPENDENCE_PARAMETERS_UNSUPPORTED")
        if action_id == "cancel_military_access" and phase != "initiate":
            raise ValueError("MILITARY_ACCESS_INITIATE_ONLY")
        if action_id == "cancel_military_access" and phase == "initiate" and parameters:
            raise ValueError("MILITARY_ACCESS_PARAMETERS_UNSUPPORTED")
        if action_id == "ask_military_access" and phase not in ("initiate", "accept", "reject"):
            raise ValueError("MILITARY_ACCESS_PHASE_UNSUPPORTED")
        if action_id == "ask_military_access" and phase == "initiate" and parameters:
            raise ValueError("MILITARY_ACCESS_PARAMETERS_UNSUPPORTED")
        if action_id in _INSULT_ACTIONS and phase != "initiate":
            raise ValueError("INSULT_INITIATE_ONLY")
        if action_id == "send_insult" and parameters:
            raise ValueError("INSULT_PARAMETERS_UNSUPPORTED")
        if action_id == "scornful_insult" and parameters:
            if set(parameters) != {"insult_id"}:
                raise ValueError("SCORNFUL_INSULT_PARAMETERS_UNSUPPORTED")
            if ObserverSession._safe_int(parameters.get("insult_id"), 0, 2147483647) is None:
                raise ValueError("SCORNFUL_INSULT_ID_INVALID")
        if (action_id in ("offer_alliance", "offer_royal_marriage")
                and phase in ("accept", "reject")
                and any(key != "proposal_id" for key in parameters)):
            raise ValueError("INBOUND_RESPONSE_PARAMETERS_UNSUPPORTED")
        if (action_id == "ask_military_access"
                and phase in ("accept", "reject")
                and (set(parameters) != {"proposal_id"}
                     or not isinstance(parameters.get("proposal_id"), str)
                     or re.fullmatch(r"[0-9a-f]{32}", parameters["proposal_id"]) is None)):
            raise ValueError("INBOUND_RESPONSE_PARAMETERS_UNSUPPORTED")
        if (action_id == "support_independence"
                and phase in ("accept", "reject")
                and (set(parameters) != {"proposal_id"}
                     or not isinstance(parameters.get("proposal_id"), str)
                     or re.fullmatch(r"[0-9a-f]{32}", parameters["proposal_id"]) is None)):
            raise ValueError("INBOUND_RESPONSE_PARAMETERS_UNSUPPORTED")
        if (action_id == "offer_vassalization"
                and phase in ("accept", "reject")
                and (set(parameters) != {"proposal_id"}
                     or not isinstance(parameters.get("proposal_id"), str)
                     or re.fullmatch(r"[0-9a-f]{32}", parameters["proposal_id"]) is None)):
            raise ValueError("INBOUND_RESPONSE_PARAMETERS_UNSUPPORTED")

    def list_diplomatic_actions(self, actor: str | None = None, recipient: str | None = None,
                               category: str | None = None) -> dict:
        if category not in (None, "diplomatic_action", "peace_term"):
            raise ValueError("UNKNOWN_ACTION_CATEGORY")
        actions = [action.describe() for action in ACTIONS.values() if category is None or action.category == category]
        health = self._health()
        query_capabilities: set[str] = set()
        safe_installation_capabilities: set[str] = set()
        if self.session is not None and health["status"] == "ready":
            read_caps = getattr(self.session, "installation_capabilities", None)
            if callable(read_caps):
                try:
                    advertised = read_caps()
                    if isinstance(advertised, dict):
                        query_capabilities.update(key for key, value in advertised.items()
                                                  if isinstance(key, str) and value is True
                                                  and key not in (
                                                      _NATIVE_INBOUND_ROYAL_RESPONSE_CAPABILITY,
                                                      _NATIVE_IMPROVE_RELATIONS_QUERY_CAPABILITY,
                                                      _NATIVE_IMPROVE_RELATIONS_SUBMISSION_CAPABILITY,
                                                      _NATIVE_SPY_NETWORK_QUERY_CAPABILITY,
                                                      _NATIVE_SPY_NETWORK_SUBMISSION_CAPABILITY,
                                                      _NATIVE_GUARANTEE_QUERY_CAPABILITY,
                                                      _NATIVE_GUARANTEE_SUBMISSION_CAPABILITY,
                                                      _NATIVE_SUPPORT_INDEPENDENCE_QUERY_CAPABILITY,
                                                      _NATIVE_SUPPORT_INDEPENDENCE_SUBMISSION_CAPABILITY,
                                                       _NATIVE_MILITARY_ACCESS_QUERY_CAPABILITY,
                                                       _NATIVE_MILITARY_ACCESS_SUBMISSION_CAPABILITY,
                                                       _NATIVE_INSULT_QUERY_CAPABILITY,
                                                       _NATIVE_INSULT_SUBMISSION_CAPABILITY,
                                                       _NATIVE_RIVAL_QUERY_CAPABILITY,
                                                       _NATIVE_RIVAL_SUBMISSION_CAPABILITY,
                                                       _NATIVE_DECLARE_WAR_QUERY_CAPABILITY,
                                                       _NATIVE_DECLARE_WAR_SUBMISSION_CAPABILITY,
                                                       _NATIVE_VASSALIZATION_QUERY_CAPABILITY,
                                                       _NATIVE_VASSALIZATION_SUBMISSION_CAPABILITY,
                                                       _NATIVE_PEACE_CONTEXT_QUERY_CAPABILITY,
                                                       _NATIVE_PEACE_EMPTY_OFFER_QUERY_CAPABILITY,
                                                       _NATIVE_PEACE_MONEY_OFFER_QUERY_CAPABILITY,
                                                       _NATIVE_PEACE_PROVINCE_OFFER_QUERY_CAPABILITY,
                                                       _NATIVE_PEACE_COMBINED_QUERY_CAPABILITY,
                                                       _NATIVE_PEACE_OFFER_EVALUATION_QUERY_CAPABILITY,
                                                       _NATIVE_PEACE_WRAPPER_RULE_QUERY_CAPABILITY,
                                                       _NATIVE_INBOUND_PEACE_RESPONSE_CAPABILITY,
                                                       _NATIVE_INBOUND_VASSAL_RESPONSE_CAPABILITY,
                                                       _NATIVE_INBOUND_SUPPORT_RESPONSE_CAPABILITY,
                                                       _NATIVE_INBOUND_MILITARY_ACCESS_RESPONSE_CAPABILITY))
                    elif isinstance(advertised, (set, frozenset)):
                        query_capabilities.update(value for value in advertised if isinstance(value, str))
                    elif isinstance(advertised, (list, tuple)):
                        query_capabilities.update(value for value in advertised
                                                  if isinstance(value, str)
                                                  and value not in (
                                                      _NATIVE_ROYAL_MARRIAGE_QUERY_CAPABILITY,
                                                      _NATIVE_IMPROVE_RELATIONS_QUERY_CAPABILITY,
                                                      _NATIVE_INBOUND_ROYAL_RESPONSE_CAPABILITY,
                                                      _NATIVE_IMPROVE_RELATIONS_SUBMISSION_CAPABILITY,
                                                      _NATIVE_SPY_NETWORK_QUERY_CAPABILITY,
                                                      _NATIVE_SPY_NETWORK_SUBMISSION_CAPABILITY,
                                                      _NATIVE_GUARANTEE_QUERY_CAPABILITY,
                                                      _NATIVE_GUARANTEE_SUBMISSION_CAPABILITY,
                                                      _NATIVE_SUPPORT_INDEPENDENCE_QUERY_CAPABILITY,
                                                      _NATIVE_SUPPORT_INDEPENDENCE_SUBMISSION_CAPABILITY,
                                                       _NATIVE_MILITARY_ACCESS_QUERY_CAPABILITY,
                                                       _NATIVE_MILITARY_ACCESS_SUBMISSION_CAPABILITY,
                                                       _NATIVE_INSULT_QUERY_CAPABILITY,
                                                       _NATIVE_INSULT_SUBMISSION_CAPABILITY,
                                                      _NATIVE_RIVAL_QUERY_CAPABILITY,
                                                      _NATIVE_RIVAL_SUBMISSION_CAPABILITY,
                                                      _NATIVE_DECLARE_WAR_QUERY_CAPABILITY,
                                                       _NATIVE_DECLARE_WAR_SUBMISSION_CAPABILITY,
                                                       _NATIVE_VASSALIZATION_QUERY_CAPABILITY,
                                                       _NATIVE_VASSALIZATION_SUBMISSION_CAPABILITY,
                                                       _NATIVE_PEACE_CONTEXT_QUERY_CAPABILITY,
                                                       _NATIVE_PEACE_EMPTY_OFFER_QUERY_CAPABILITY,
                                                        _NATIVE_PEACE_MONEY_OFFER_QUERY_CAPABILITY,
                                                        _NATIVE_PEACE_PROVINCE_OFFER_QUERY_CAPABILITY,
                                                         _NATIVE_PEACE_COMBINED_QUERY_CAPABILITY,
                                                        _NATIVE_PEACE_OFFER_EVALUATION_QUERY_CAPABILITY,
                                                       _NATIVE_PEACE_WRAPPER_RULE_QUERY_CAPABILITY,
                                                       _NATIVE_INBOUND_PEACE_RESPONSE_CAPABILITY,
                                                       _NATIVE_INBOUND_VASSAL_RESPONSE_CAPABILITY,
                                                       _NATIVE_INBOUND_SUPPORT_RESPONSE_CAPABILITY,
                                                       _NATIVE_INBOUND_MILITARY_ACCESS_RESPONSE_CAPABILITY))
                except (OSError, TypeError, ValueError):
                    query_capabilities.clear()
            # ObserverSession also normalizes exact top-level boolean ACKs,
            # including r21's inbound observation flag.
            safe_installation_capabilities = set(self._installation_capabilities())
            query_capabilities.update(safe_installation_capabilities)
        native_query_acknowledged = bool(query_capabilities & _NATIVE_QUERY_CAPS)
        native_offer_submission_acknowledged = (
            _NATIVE_OFFER_SUBMISSION_CAPABILITY in query_capabilities)
        native_dissolve_submission_acknowledged = (
            _NATIVE_DISSOLVE_SUBMISSION_CAPABILITY in query_capabilities)
        native_royal_marriage_submission_acknowledged = (
            _NATIVE_ROYAL_MARRIAGE_SUBMISSION_CAPABILITY in query_capabilities)
        native_inbound_response_acknowledged = (
            _NATIVE_INBOUND_RESPONSE_CAPABILITY in query_capabilities)
        native_inbound_royal_response_acknowledged = (
            _NATIVE_INBOUND_ROYAL_RESPONSE_CAPABILITY in query_capabilities)
        native_royal_marriage_query_acknowledged = (
            _NATIVE_ROYAL_MARRIAGE_QUERY_CAPABILITY in query_capabilities)
        native_improve_relations_query_acknowledged = (
            _NATIVE_IMPROVE_RELATIONS_QUERY_CAPABILITY in query_capabilities)
        native_improve_relations_submission_acknowledged = (
            _NATIVE_IMPROVE_RELATIONS_SUBMISSION_CAPABILITY in query_capabilities)
        native_spy_network_query_acknowledged = (
            _NATIVE_SPY_NETWORK_QUERY_CAPABILITY in query_capabilities)
        native_spy_network_submission_acknowledged = (
            _NATIVE_SPY_NETWORK_SUBMISSION_CAPABILITY in query_capabilities)
        native_guarantee_query_acknowledged = (
            _NATIVE_GUARANTEE_QUERY_CAPABILITY in query_capabilities)
        native_guarantee_submission_acknowledged = (
            _NATIVE_GUARANTEE_SUBMISSION_CAPABILITY in query_capabilities)
        native_support_independence_query_acknowledged = (
            _NATIVE_SUPPORT_INDEPENDENCE_QUERY_CAPABILITY in query_capabilities)
        native_support_independence_submission_acknowledged = (
            _NATIVE_SUPPORT_INDEPENDENCE_SUBMISSION_CAPABILITY in query_capabilities)
        native_inbound_support_response_acknowledged = (
            _NATIVE_INBOUND_SUPPORT_RESPONSE_CAPABILITY in query_capabilities)
        native_inbound_peace_response_acknowledged = (
            _NATIVE_INBOUND_PEACE_RESPONSE_CAPABILITY in query_capabilities)
        native_military_access_query_acknowledged = (
            _NATIVE_MILITARY_ACCESS_QUERY_CAPABILITY in query_capabilities)
        native_military_access_submission_acknowledged = (
            _NATIVE_MILITARY_ACCESS_SUBMISSION_CAPABILITY in query_capabilities)
        native_insult_query_acknowledged = (
            _NATIVE_INSULT_QUERY_CAPABILITY in query_capabilities)
        native_insult_submission_acknowledged = (
            _NATIVE_INSULT_SUBMISSION_CAPABILITY in query_capabilities)
        native_rival_query_acknowledged = (
            _NATIVE_RIVAL_QUERY_CAPABILITY in query_capabilities)
        native_rival_submission_acknowledged = (
            _NATIVE_RIVAL_SUBMISSION_CAPABILITY in query_capabilities)
        native_vassalization_query_acknowledged = (
            _NATIVE_VASSALIZATION_QUERY_CAPABILITY in query_capabilities)
        native_vassalization_submission_acknowledged = (
            _NATIVE_VASSALIZATION_SUBMISSION_CAPABILITY in query_capabilities)
        native_declare_war_query_acknowledged = (
            _NATIVE_DECLARE_WAR_QUERY_CAPABILITY in query_capabilities)
        native_declare_war_submission_acknowledged = (
            _NATIVE_DECLARE_WAR_SUBMISSION_CAPABILITY in query_capabilities)
        native_peace_context_query_acknowledged = (
            _NATIVE_PEACE_CONTEXT_QUERY_CAPABILITY in query_capabilities)
        native_peace_empty_offer_query_acknowledged = (
            _NATIVE_PEACE_EMPTY_OFFER_QUERY_CAPABILITY in query_capabilities)
        native_peace_money_offer_query_acknowledged = (
            _NATIVE_PEACE_MONEY_OFFER_QUERY_CAPABILITY in query_capabilities)
        native_peace_province_offer_query_acknowledged = (
            _NATIVE_PEACE_PROVINCE_OFFER_QUERY_CAPABILITY in query_capabilities)
        native_peace_combined_query_acknowledged = (
            _NATIVE_PEACE_COMBINED_QUERY_CAPABILITY in query_capabilities)
        native_peace_submission_acknowledged = (
            _NATIVE_PEACE_SUBMISSION_CAPABILITY in safe_installation_capabilities)
        native_inbound_vassal_response_acknowledged = (
            _NATIVE_INBOUND_VASSAL_RESPONSE_CAPABILITY in query_capabilities)
        native_inbound_military_access_response_acknowledged = (
            _NATIVE_INBOUND_MILITARY_ACCESS_RESPONSE_CAPABILITY in query_capabilities)
        for action in actions:
            if action["action_id"] in ("offer_alliance", "dissolve_alliance"):
                action["identification_status"] = "static_object_and_live_offer_matched"
                if self.session is not None and health["status"] == "ready":
                    for phase_name, phase in action["phases"].items():
                        if native_query_acknowledged and phase_name == "initiate":
                            phase["query"] = "native_alliance_inspection"
                            phase["reason_code"] = "NATIVE_ALLIANCE_QUERY_ACKNOWLEDGED"
                        elif not native_query_acknowledged:
                            phase["query"] = "partial_native_queue_read"
                            phase["reason_code"] = "NATIVE_RULES_AND_RESPONSE_LIFECYCLE_UNRECOVERED"
                        if (action["action_id"] == "offer_alliance" and phase_name == "initiate"
                                and native_offer_submission_acknowledged):
                            phase["execute"] = "native_offer_submission"
                            phase["execute_reason_code"] = "NATIVE_OFFER_SUBMISSION_CAPABILITY_ACKNOWLEDGED"
                        if (action["action_id"] == "dissolve_alliance" and phase_name == "initiate"
                                and native_dissolve_submission_acknowledged):
                            phase["execute"] = "native_dissolve_submission"
                            phase["execute_reason_code"] = "NATIVE_DISSOLVE_SUBMISSION_CAPABILITY_ACKNOWLEDGED"
                        if (action["action_id"] == "offer_alliance"
                                and phase_name in ("accept", "reject")
                                and native_inbound_response_acknowledged):
                            phase["query"] = "native_inbound_response_inspection"
                            phase["reason_code"] = "NATIVE_INBOUND_RESPONSE_CAPABILITY_ACKNOWLEDGED"
                            phase["execute"] = "native_inbound_response"
                            phase["execute_reason_code"] = "NATIVE_INBOUND_RESPONSE_CAPABILITY_ACKNOWLEDGED"
            elif action["action_id"] == "declare_war":
                action["identification_status"] = "static_native_action_family"
                if (self.session is not None and health["status"] == "ready"
                        and native_declare_war_query_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["query"] = "native_declare_war_inspection"
                        initiate["reason_code"] = (
                            "NATIVE_DECLARE_WAR_QUERY_ACKNOWLEDGED")
                if (self.session is not None and health["status"] == "ready"
                        and native_declare_war_submission_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["execute"] = "native_declare_war_submission"
                        initiate["execute_reason_code"] = (
                            "NATIVE_DECLARE_WAR_SUBMISSION_CAPABILITY_ACKNOWLEDGED")
            elif action["category"] == "peace_term":
                action["identification_status"] = "static_native_action_family"
                if (self.session is not None and health["status"] == "ready"
                        and native_peace_context_query_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["query"] = "native_peace_context_inspection"
                        initiate["reason_code"] = (
                            "NATIVE_PEACE_CONTEXT_QUERY_ACKNOWLEDGED")
                        if (action["action_id"] == "white_peace"
                                and native_peace_empty_offer_query_acknowledged):
                            initiate["selected_query"] = (
                                "native_peace_empty_offer_inspection")
                            initiate["selected_query_reason_code"] = (
                                "NATIVE_PEACE_EMPTY_OFFER_QUERY_ACKNOWLEDGED")
                        if (action["action_id"] == "demand_ducats"
                                and native_peace_money_offer_query_acknowledged):
                            initiate["selected_query"] = (
                                "native_peace_money_offer_inspection")
                            initiate["selected_query_reason_code"] = (
                                "NATIVE_PEACE_MONEY_OFFER_QUERY_ACKNOWLEDGED")
                        if (action["action_id"] == "cede_province"
                                and native_peace_province_offer_query_acknowledged):
                            initiate["selected_query"] = (
                                "native_peace_province_offer_inspection")
                            initiate["selected_query_reason_code"] = (
                                "NATIVE_PEACE_PROVINCE_OFFER_QUERY_ACKNOWLEDGED")
                        if (action["action_id"] in ("demand_ducats", "cede_province")
                                and native_peace_combined_query_acknowledged):
                            initiate["combined_query"] = (
                                "native_peace_combined_offer_inspection")
                            initiate["combined_query_reason_code"] = (
                                "NATIVE_PEACE_COMBINED_QUERY_ACKNOWLEDGED")
                elif (self.session is not None and health["status"] == "ready"
                      and action["action_id"] == "white_peace"
                      and native_peace_empty_offer_query_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["selected_query"] = (
                            "native_peace_empty_offer_inspection")
                        initiate["selected_query_reason_code"] = (
                            "NATIVE_PEACE_EMPTY_OFFER_QUERY_ACKNOWLEDGED")
                elif (self.session is not None and health["status"] == "ready"
                      and action["action_id"] == "demand_ducats"
                      and native_peace_money_offer_query_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["selected_query"] = (
                            "native_peace_money_offer_inspection")
                        initiate["selected_query_reason_code"] = (
                            "NATIVE_PEACE_MONEY_OFFER_QUERY_ACKNOWLEDGED")
                elif (self.session is not None and health["status"] == "ready"
                      and action["action_id"] == "cede_province"
                      and native_peace_province_offer_query_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["selected_query"] = (
                            "native_peace_province_offer_inspection")
                        initiate["selected_query_reason_code"] = (
                            "NATIVE_PEACE_PROVINCE_OFFER_QUERY_ACKNOWLEDGED")
                if (self.session is not None and health["status"] == "ready"
                        and action["action_id"] in ("demand_ducats", "cede_province")
                        and native_peace_combined_query_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["combined_query"] = (
                            "native_peace_combined_offer_inspection")
                        initiate["combined_query_reason_code"] = (
                            "NATIVE_PEACE_COMBINED_QUERY_ACKNOWLEDGED")
                if (self.session is not None and health["status"] == "ready"
                        and native_peace_submission_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["execute"] = "native_peace_submission"
                        initiate["execute_reason_code"] = (
                            "NATIVE_PEACE_SUBMISSION_CAPABILITY_ACKNOWLEDGED")
            elif action["action_id"] in ("offer_royal_marriage", "break_royal_ties"):
                action["identification_status"] = "static_native_action_family"
                if (self.session is not None and health["status"] == "ready"
                        and native_royal_marriage_query_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["query"] = "partial_native_rules"
                        initiate["reason_code"] = "NATIVE_ROYAL_MARRIAGE_QUERY_ACKNOWLEDGED"
                if (self.session is not None and health["status"] == "ready"
                        and native_royal_marriage_submission_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["execute"] = "native_royal_marriage_submission"
                        initiate["execute_reason_code"] = (
                            "NATIVE_ROYAL_MARRIAGE_SUBMISSION_CAPABILITY_ACKNOWLEDGED")
                if (action["action_id"] == "offer_royal_marriage"
                        and self.session is not None and health["status"] == "ready"
                        and native_inbound_royal_response_acknowledged):
                    for phase_name in ("accept", "reject"):
                        response_phase = action["phases"].get(phase_name)
                        if response_phase is None:
                            continue
                        response_phase["query"] = "native_inbound_response_inspection"
                        response_phase["reason_code"] = (
                            "NATIVE_INBOUND_ROYAL_MARRIAGE_RESPONSE_CAPABILITY_ACKNOWLEDGED")
                        response_phase["execute"] = "native_inbound_response"
                        response_phase["execute_reason_code"] = (
                            "NATIVE_INBOUND_ROYAL_MARRIAGE_RESPONSE_CAPABILITY_ACKNOWLEDGED")
            elif action["action_id"] in ("improve_relations", "stop_improving_relations"):
                action["identification_status"] = "static_native_action_family"
                if (self.session is not None and health["status"] == "ready"
                        and native_improve_relations_query_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["query"] = "partial_native_rules"
                        initiate["reason_code"] = "NATIVE_IMPROVE_RELATIONS_QUERY_ACKNOWLEDGED"
                if (self.session is not None and health["status"] == "ready"
                        and native_improve_relations_submission_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["execute"] = "native_improve_relations_submission"
                        initiate["execute_reason_code"] = (
                            "NATIVE_IMPROVE_RELATIONS_SUBMISSION_CAPABILITY_ACKNOWLEDGED")
            elif action["action_id"] in ("build_spy_network", "stop_building_spy_network"):
                action["identification_status"] = "static_native_action_family"
                if (self.session is not None and health["status"] == "ready"
                        and native_spy_network_query_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["query"] = "partial_native_rules"
                        initiate["reason_code"] = "NATIVE_SPY_NETWORK_QUERY_ACKNOWLEDGED"
                if (self.session is not None and health["status"] == "ready"
                        and native_spy_network_submission_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["execute"] = "native_spy_network_submission"
                        initiate["execute_reason_code"] = (
                            "NATIVE_SPY_NETWORK_SUBMISSION_CAPABILITY_ACKNOWLEDGED")
            elif action["action_id"] in ("proclaim_guarantee", "revoke_guarantee"):
                action["identification_status"] = "static_native_action_family"
                if (self.session is not None and health["status"] == "ready"
                        and native_guarantee_query_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["query"] = "partial_native_rules"
                        initiate["reason_code"] = "NATIVE_GUARANTEE_QUERY_ACKNOWLEDGED"
                if (self.session is not None and health["status"] == "ready"
                        and native_guarantee_submission_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["execute"] = "native_guarantee_submission"
                        initiate["execute_reason_code"] = (
                            "NATIVE_GUARANTEE_SUBMISSION_CAPABILITY_ACKNOWLEDGED")
            elif action["action_id"] in ("support_independence", "revoke_support_independence"):
                action["identification_status"] = "static_native_action_family"
                if (self.session is not None and health["status"] == "ready"
                        and native_support_independence_query_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["query"] = "partial_native_rules"
                        initiate["reason_code"] = (
                            "NATIVE_SUPPORT_INDEPENDENCE_QUERY_ACKNOWLEDGED")
                if (self.session is not None and health["status"] == "ready"
                        and native_support_independence_submission_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["execute"] = "native_support_independence_submission"
                        initiate["execute_reason_code"] = (
                            "NATIVE_SUPPORT_INDEPENDENCE_SUBMISSION_CAPABILITY_ACKNOWLEDGED")
                if (action["action_id"] == "support_independence"
                        and self.session is not None and health["status"] == "ready"
                        and native_inbound_support_response_acknowledged):
                    for phase_name in ("accept", "reject"):
                        response_phase = action["phases"].get(phase_name)
                        if response_phase is None:
                            continue
                        response_phase["query"] = "native_inbound_response_inspection"
                        response_phase["reason_code"] = (
                            "NATIVE_INBOUND_SUPPORT_INDEPENDENCE_RESPONSE_CAPABILITY_ACKNOWLEDGED")
                        response_phase["execute"] = "native_inbound_response"
                        response_phase["execute_reason_code"] = (
                            "NATIVE_INBOUND_SUPPORT_INDEPENDENCE_RESPONSE_CAPABILITY_ACKNOWLEDGED")
            elif action["action_id"] in ("ask_military_access", "cancel_military_access"):
                action["identification_status"] = "static_native_action_family"
                if (self.session is not None and health["status"] == "ready"
                        and native_military_access_query_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["query"] = "partial_native_rules"
                        initiate["reason_code"] = "NATIVE_MILITARY_ACCESS_QUERY_ACKNOWLEDGED"
                if (self.session is not None and health["status"] == "ready"
                        and native_military_access_submission_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["execute"] = "native_military_access_submission"
                        initiate["execute_reason_code"] = (
                            "NATIVE_MILITARY_ACCESS_SUBMISSION_CAPABILITY_ACKNOWLEDGED")
                if (action["action_id"] == "ask_military_access"
                        and self.session is not None and health["status"] == "ready"
                        and native_inbound_military_access_response_acknowledged):
                    for phase_name in ("accept", "reject"):
                        response_phase = action["phases"].get(phase_name)
                        if response_phase is None:
                            continue
                        response_phase["query"] = "native_inbound_response_inspection"
                        response_phase["reason_code"] = (
                            "NATIVE_INBOUND_MILITARY_ACCESS_RESPONSE_CAPABILITY_ACKNOWLEDGED")
                        response_phase["execute"] = "native_inbound_response"
                        response_phase["execute_reason_code"] = (
                            "NATIVE_INBOUND_MILITARY_ACCESS_RESPONSE_CAPABILITY_ACKNOWLEDGED")
            elif action["action_id"] in _INSULT_ACTIONS:
                action["identification_status"] = "static_native_action_family"
                initiate = action["phases"].get("initiate")
                if (self.session is not None and health["status"] == "ready"
                        and native_insult_query_acknowledged and initiate is not None):
                    initiate["query"] = "native_insult_query2"
                    initiate["reason_code"] = "NATIVE_INSULT_QUERY_ACKNOWLEDGED"
                if (self.session is not None and health["status"] == "ready"
                        and native_insult_submission_acknowledged and initiate is not None):
                    initiate["execute"] = "native_insult_submission"
                    initiate["execute_reason_code"] = (
                        "NATIVE_INSULT_SUBMISSION_CAPABILITY_ACKNOWLEDGED")
                # Both variants are one-sided; catalog response phases are
                # absent and acceptance remains not applicable.
            elif action["action_id"] in ("set_rival", "remove_rival"):
                action["identification_status"] = "static_native_action_family"
                if (self.session is not None and health["status"] == "ready"
                        and native_rival_query_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["query"] = "partial_native_rules"
                        initiate["reason_code"] = "NATIVE_RIVAL_QUERY_ACKNOWLEDGED"
                if (self.session is not None and health["status"] == "ready"
                        and native_rival_submission_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["execute"] = "native_rival_submission"
                        initiate["execute_reason_code"] = (
                            "NATIVE_RIVAL_SUBMISSION_CAPABILITY_ACKNOWLEDGED")
            elif action["action_id"] in _VASSALIZATION_ACTIONS:
                action["identification_status"] = "static_native_action_family"
                if (self.session is not None and health["status"] == "ready"
                        and native_vassalization_query_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["query"] = "partial_native_rules"
                        initiate["reason_code"] = (
                            "NATIVE_VASSALIZATION_QUERY_ACKNOWLEDGED")
                if (self.session is not None and health["status"] == "ready"
                        and native_vassalization_submission_acknowledged):
                    initiate = action["phases"].get("initiate")
                    if initiate is not None:
                        initiate["execute"] = "native_vassalization_submission"
                        initiate["execute_reason_code"] = (
                            "NATIVE_VASSALIZATION_SUBMISSION_CAPABILITY_ACKNOWLEDGED")
                if (action["action_id"] == "offer_vassalization"
                        and self.session is not None and health["status"] == "ready"
                        and native_inbound_vassal_response_acknowledged):
                    for phase_name in ("accept", "reject"):
                        response_phase = action["phases"].get(phase_name)
                        if response_phase is None:
                            continue
                        response_phase["query"] = "native_inbound_response_inspection"
                        response_phase["reason_code"] = (
                            "NATIVE_INBOUND_VASSALIZATION_RESPONSE_CAPABILITY_ACKNOWLEDGED")
                        response_phase["execute"] = "native_inbound_response"
                        response_phase["execute_reason_code"] = (
                            "NATIVE_INBOUND_VASSALIZATION_RESPONSE_CAPABILITY_ACKNOWLEDGED")
        incoming_proposals = self._read_inbound_proposals(health, recipient=recipient)
        for proposal in incoming_proposals:
            response_capability = _inbound_response_capability(proposal.get("action_id"))
            if response_capability in self._installation_capabilities():
                proposal["execute"] = {
                    "accept": "native_inbound_response", "reject": "native_inbound_response"}
        incoming_action_definitions = [spec.describe()
                                       for spec in INBOUND_ACTIONS.values()]
        if native_inbound_peace_response_acknowledged and self.session is not None \
                and health["status"] == "ready":
            for definition in incoming_action_definitions:
                if definition.get("action_id") != "peace_offer":
                    continue
                definition["identification_status"] = "native_inbound_aggregate_contract"
                for phase_name in ("accept", "reject"):
                    response_phase = definition["phases"].get(phase_name)
                    if response_phase is None:
                        continue
                    response_phase["query"] = "native_inbound_response_inspection"
                    response_phase["reason_code"] = (
                        "NATIVE_INBOUND_PEACE_RESPONSE_CAPABILITY_ACKNOWLEDGED")
                    response_phase["execute"] = "native_inbound_response"
                    response_phase["execute_reason_code"] = (
                        "NATIVE_INBOUND_PEACE_RESPONSE_CAPABILITY_ACKNOWLEDGED")
        return {"contract_version": 1, "actor": actor, "recipient": recipient,
                "session": health, "actions": actions, "catalog_complete": False,
                "incoming_action_definitions": incoming_action_definitions,
                "incoming_proposals": incoming_proposals,
                "incoming_proposals_complete": False,
                "priority_scope": "19常用外交操作、19常用议和条款及独立的支持独立标识"}

    @staticmethod
    def _peace_execution_capability_for(parameters: object, action_id: str) -> str | None:
        """Return the read capability needed for the selected Peace term."""

        try:
            normalized = normalize_peace_execution_parameters(
                action_id, "FRA", "ENG", "initiate", parameters)
        except (TypeError, ValueError):
            return None
        terms = normalized["peace_context"]["terms"]
        if not terms:
            return _NATIVE_PEACE_EMPTY_OFFER_QUERY_CAPABILITY
        required = set()
        for term in terms:
            required.add(
                _NATIVE_PEACE_MONEY_OFFER_QUERY_CAPABILITY
                if term["action_id"] == "demand_ducats"
                else _NATIVE_PEACE_PROVINCE_OFFER_QUERY_CAPABILITY)
        if len(required) > 1:
            return _NATIVE_PEACE_COMBINED_QUERY_CAPABILITY
        return next(iter(required)) if len(required) == 1 else None

    @classmethod
    def _apply_peace_execution_inspection(
            cls, inspection: dict, native: object, parameters: dict) -> dict:
        """Project one fresh native term inspection into the execution view."""

        inspection["family"] = "peace"
        inspection["interface_support"]["query"] = (
            "native_peace_execution_inspection")
        if not isinstance(native, dict):
            native = {"error_code": "QUERY_NATIVE_RESULT_INVALID"}
        if "error_code" in native:
            code = native.get("error_code")
            if not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9_]{1,96}", code):
                code = "QUERY_NATIVE_RESULT_INVALID"
            inspection["legality"] = {
                "status": "unknown", "reasons": [reason(
                    code, "议和执行前的最新原生上下文检查没有取得可验证结果。",
                    "runtime_error")], "complete": False}
            inspection["parameters"] = {
                "requested": parameters, "actual": None,
                "candidates": None, "complete": False}
            return inspection

        safe_keys = (
            "selected_war_id", "identity_scope", "peace_context",
            "query_complete", "native_offer_inspected", "pair_at_war",
            "unique_shared_war", "offer_constructed", "action_constructed",
            "participant_copy_verified", "offer_identity_verified",
            "object_unchanged", "cleanup_verified", "validity_called",
            "native_validity", "common_gate_checked", "common_action_gate",
            "initiation_gate_checked", "initiation_gate",
            "native_wrapper_gate_checked", "native_wrapper_gate",
            "wrapper_identity_verified", "wrapper_payload_unchanged",
            "native_diagnostic_text", "native_diagnostic_text_decoded",
            "native_diagnostic_truncated", "diagnostics", "native_evaluation",
            "native_money", "native_provinces", "native_war_context",
            "native_payload", "full_rules_complete", "reasons_complete",
            "parameters_matched", "submitted")
        for key in safe_keys:
            if key in native:
                inspection[key] = native[key]
        wrapper_state = ObserverSession._peace_wrapper_rule_state(native)
        requested = parameters
        matched = native.get("parameters_matched")
        if not isinstance(matched, bool):
            matched = native.get("query_complete") is True
        inspection["parameters"] = {
            "requested": requested,
            "actual": requested if matched else None,
            "candidates": None,
            "complete": (matched is True
                         and native.get("full_rules_complete") is True
                         and wrapper_state == "verified"),
        }
        execution_parameters_complete = inspection["parameters"]["complete"] is True
        normalized_context = (
            parameters.get("peace_context")
            if isinstance(parameters, dict)
            else None)
        if isinstance(normalized_context, dict):
            execution_context = {
                "war_id": normalized_context.get("war_id"),
                "direction": normalized_context.get("direction"),
                "terms": list(normalized_context.get("terms", [])),
                "complete": execution_parameters_complete,
                # The selected execution context can be complete even while
                # the broader war-side/leader discovery remains partial.
                "war_context_complete": (
                    isinstance(native.get("native_war_context"), dict)
                    and native["native_war_context"].get("context_complete") is True),
            }
            inspection["execution_context"] = execution_context
            public_context = {
                "war_id": execution_context["war_id"],
                "direction": execution_context["direction"],
                "terms": execution_context["terms"],
                "complete": execution_parameters_complete,
            }
            if ObserverSession._valid_public_peace_context(public_context):
                # A selected, normalized context is the contract consumed by
                # execute. Keep native_war_context.context_complete separate
                # so unknown leader/role discovery is never promoted.
                inspection["peace_context"] = public_context
        failures = []
        for field, code, text, diagnostic_key in (
                ("native_validity", "NATIVE_PEACE_VALIDITY_FALSE",
                 "原生议和条款合法性检查返回false。", "validity"),
                ("common_action_gate", "NATIVE_PEACE_COMMON_GATE_FALSE",
                 "原生通用外交动作条件返回false。", "common_action_gate"),
                ("initiation_gate", "NATIVE_PEACE_INITIATION_GATE_FALSE",
                 "原生议和发起条件返回false。", "initiation_gate")):
            if native.get(field) is False:
                item = reason(code, text, "native_rule")
                diagnostic = native.get("diagnostics", {}).get(diagnostic_key)
                if isinstance(diagnostic, dict) and isinstance(diagnostic.get("text"), str):
                    item["text"] = diagnostic["text"]
                failures.append(item)
        if wrapper_state == "failed":
            failures.append(reason(
                "NATIVE_PEACE_WRAPPER_GATE_FALSE",
                "原生议和wrapper规则检查返回false。",
                "native_rule", True))
        if failures:
            inspection["legality"] = {
                "status": "unavailable", "reasons": failures, "complete": False}
        elif (wrapper_state == "verified"
              and native.get("full_rules_complete") is True
              and native.get("native_validity") is True
              and native.get("common_action_gate") is True
              and native.get("initiation_gate") is True
              and matched is True):
            inspection["legality"] = {
                "status": "available",
                "reasons": [reason(
                    "NATIVE_PEACE_EXECUTION_RULES_TRUE",
                    "当前议和参数、原生合法性和执行前条件均已复查通过。",
                    "native_rule", True)], "complete": True}
        else:
            inspection["legality"] = {
                "status": "unknown", "reasons": [reason(
                    "NATIVE_PEACE_EXECUTION_RULES_INCOMPLETE",
                    "原生议和条款检查尚未覆盖完整执行规则，不能提交。",
                    "native_rule")], "complete": False}
        inspection["native_rule_components"] = {
            "validity_called": native.get("validity_called"),
            "native_validity": native.get("native_validity"),
            "common_gate_checked": native.get("common_gate_checked"),
            "common_action_gate": native.get("common_action_gate"),
            "initiation_gate_checked": native.get("initiation_gate_checked"),
            "initiation_gate": native.get("initiation_gate"),
            "native_wrapper_gate_checked": native.get(
                "native_wrapper_gate_checked"),
            "native_wrapper_gate": native.get("native_wrapper_gate"),
            "wrapper_identity_verified": native.get(
                "wrapper_identity_verified"),
            "wrapper_payload_unchanged": native.get(
                "wrapper_payload_unchanged"),
            "full_rules_complete": native.get("full_rules_complete"),
            "complete": wrapper_state == "verified",
        }
        evaluation = native.get("native_evaluation")
        if isinstance(evaluation, dict):
            score_available = evaluation.get("score_available") is True
            aggregate_available = evaluation.get("aggregate_score_available") is True
            inspection["acceptance"].update({
                "prediction_available": False,
                "native_total": evaluation.get("score_raw") if score_available else None,
                "unit": "unknown", "scale_verified": False,
                "predicted_response": "unknown", "details_available": bool(
                    evaluation.get("items")),
                "details_complete": evaluation.get("factors_complete") is True,
                "items": list(evaluation.get("items", [])), "complete": False})
            inspection["costs"]["native_evaluation"] = {
                "aggregate_score_raw": evaluation.get("aggregate_score_raw")
                if aggregate_available else None,
                "aggregate_score_available": aggregate_available,
                "unit": "unknown", "scale_verified": False, "complete": False}
        if isinstance(native.get("date_raw"), int) and not isinstance(native.get("date_raw"), bool):
            inspection["session"]["date_raw"] = native["date_raw"]
        return inspection

    def inspect_diplomatic_action(self, action_id: str, actor: str, recipient: str,
                                  phase: str = "initiate", parameters: dict | None = None,
                                  *, _execution_request: bool = False) -> dict:
        parameters = {} if parameters is None else parameters
        peace_execution_parameters = None
        if action_id in _PEACE_EXECUTION_ACTIONS:
            native_peace_combined_query_acknowledged = (
                _NATIVE_PEACE_COMBINED_QUERY_CAPABILITY
                in self._installation_capabilities())
            mixed_parameters_requested = (
                isinstance(parameters, dict)
                and isinstance(parameters.get("peace_context"), dict)
                and isinstance(parameters["peace_context"].get("terms"), list)
                and len(parameters["peace_context"]["terms"]) == 2)
            # A complete public Peace inspection must use the same normalized
            # parameter object and native preflight as execute.  Legacy
            # discovery/candidate queries remain on their old paths when the
            # submission ACK is absent or parameters are empty/incomplete.
            public_execution_scope = (
                not _execution_request
                and actor == "FRA"
                and phase == "initiate"
                and parameters != {}
                and (_NATIVE_PEACE_SUBMISSION_CAPABILITY
                     in self._installation_capabilities()
                     or (native_peace_combined_query_acknowledged
                         and mixed_parameters_requested)))
            if _execution_request or public_execution_scope:
                try:
                    peace_execution_parameters = normalize_peace_execution_parameters(
                        action_id, actor, recipient, phase, parameters)
                except (TypeError, ValueError):
                    if _execution_request:
                        raise
                    peace_execution_parameters = None
            if peace_execution_parameters is not None:
                parameters = peace_execution_parameters
        allow_peace_discovery = (
            action_id in PEACE_ACTION_IDS
            and self.session is not None
            and parameters == {}
            and _NATIVE_PEACE_CONTEXT_QUERY_CAPABILITY
            in self._installation_capabilities())
        allow_peace_empty_offer = (
            action_id == "white_peace"
            and self.session is not None
            and _NATIVE_PEACE_EMPTY_OFFER_QUERY_CAPABILITY
            in self._installation_capabilities())
        allow_peace_money_offer = (
            action_id == "demand_ducats"
            and self.session is not None
            and _NATIVE_PEACE_MONEY_OFFER_QUERY_CAPABILITY
            in self._installation_capabilities())
        allow_peace_province_offer = (
            action_id == "cede_province"
            and self.session is not None
            and _NATIVE_PEACE_PROVINCE_OFFER_QUERY_CAPABILITY
            in self._installation_capabilities())
        if peace_execution_parameters is None:
            self._validate(action_id, actor, recipient, phase, parameters,
                           allow_peace_discovery=allow_peace_discovery,
                           allow_peace_empty_offer=allow_peace_empty_offer,
                           allow_peace_money_offer=allow_peace_money_offer,
                           allow_peace_province_offer=allow_peace_province_offer)
        peace_money_selection = (
            self._normalize_peace_money_offer_parameters(
                parameters, actor, recipient)
            if allow_peace_money_offer and action_id == "demand_ducats"
            and phase == "initiate" and isinstance(parameters.get("peace_context"), dict)
            and not (isinstance(parameters["peace_context"].get("terms"), list)
                     and len(parameters["peace_context"]["terms"]) > 1)
            else None)
        peace_province_selection = (
            self._normalize_peace_province_offer_parameters(
                parameters, actor, recipient)
            if allow_peace_province_offer and action_id == "cede_province"
            and phase == "initiate" and isinstance(parameters.get("peace_context"), dict)
            and not (isinstance(parameters["peace_context"].get("terms"), list)
                     and len(parameters["peace_context"]["terms"]) > 1)
            else None)
        action = ACTIONS.get(action_id) or INBOUND_ACTIONS.get(action_id)
        if action is None:
            # _validate normally raises this first; keep the guard explicit so
            # a malformed caller cannot turn a missing registry entry into a
            # KeyError while building an inspection response.
            raise ValueError("UNKNOWN_ACTION_ID")
        applies = action.response and phase == "initiate"
        inspection = {
            "contract_version": 1, "action_id": action_id, "native_identifier": action.native_identifier,
            "actor": actor, "recipient": recipient, "phase": phase,
            "decision_country": None, "decision_country_verified": False,
            "requested_decision_country": recipient if phase in ("accept", "reject") else actor,
            "interface_support": {"query": "catalog_only", "execute": "unimplemented", "complete": False},
            "session": self._health(),
            "visibility": {"status": "unknown", "complete": False},
            "legality": {"status": "unknown", "reasons": [reason("NATIVE_RULE_QUERY_UNIMPLEMENTED",
                "该动作的完整原生显示与合法性查询尚未实现，不能从目录或历史实验推定当前可用性。", "runtime_error")],
                "complete": False},
            "authorization": {"status": "unavailable", "reasons": [reason("EXECUTION_ADAPTER_UNIMPLEMENTED",
                "本会话只安装观察模块，尚未建立该动作的授权执行路径。", "bridge_policy", True)], "complete": True},
            "parameters": {"requested": parameters, "actual": None, "candidates": None, "complete": False},
            "costs": {"status": "unknown", "items": [], "complete": False},
            "acceptance": {"applicability": "applicable" if applies else "not_applicable",
                "prediction_available": False, "native_total": None, "unit": "unknown" if applies else None,
                "scale_verified": False, "predicted_response": "unknown" if applies else "not_applicable",
                "details_available": False, "items": [], "complete": not applies},
        }
        if action_id in ("proclaim_guarantee", "revoke_guarantee"):
            inspection["relationship_state"] = {
                "guarantee_active": None,
                "complete": False,
            }
        if action_id in ("support_independence", "revoke_support_independence"):
            inspection["relationship_state"] = {
                "support_independence_active": None,
                "complete": False,
            }
        if action_id in ("ask_military_access", "cancel_military_access"):
            inspection["relationship_state"] = {
                "military_access_active": None,
                "complete": False,
            }
        if action_id in ("set_rival", "remove_rival"):
            inspection["relationship_state"] = {
                "rival_active": None,
                "rival_since_date_raw": None,
                "complete": False,
            }
        if action_id in _VASSALIZATION_ACTIONS:
            inspection["relationship_state"] = {
                "vassal_active": None,
                "complete": False,
            }
        if action_id in _INSULT_ACTIONS:
            inspection.update({
                "family": "insult",
                "insult_id": -1 if action_id == "send_insult" else None,
                "insult_parameter_selected": action_id == "send_insult",
                "insult_state_verified": False,
                "insult_active": None,
                "opinion_modifier_raw": None,
                "actor_prestige_raw": None,
                "prestige_cost_raw": None,
                "candidates_available": False,
                "candidate_count": 0,
                "candidates_complete": False,
            })
        inbound_response_phase = (
            action_id in ("offer_alliance", "offer_royal_marriage", "support_independence",
                          "ask_military_access", "offer_vassalization", "peace_offer")
            and phase in ("accept", "reject"))
        if inbound_response_phase:
            # A proposal id is a public opaque reference.  r21 only observes
            # it; r22 may query response rules but still requires a fresh
            # native pending check before any response wire is authorized.
            observed = self._find_inbound_proposal(
                inspection["session"], parameters.get("proposal_id"))
            inspection["interface_support"] = {
                **inspection["interface_support"],
                "query": "native_inbound_observation",
                "execute": "unimplemented",
            }
            private_context = None
            if observed is not None and actor == observed["actor"] and recipient == "FRA":
                private_context = self._private_inbound_context(
                    inspection["session"], parameters.get("proposal_id"), action_id)
            if observed is not None and private_context is not None:
                inspection["decision_country"] = "FRA"
                inspection["decision_country_verified"] = True
                inspection["observed_inbound_proposal"] = observed
                inspection["parameters"]["actual"] = {
                    "proposal_id": observed["proposal_id"],
                    "decision_country": "FRA",
                }
                family_label = (
                    "王室联姻" if action_id == "offer_royal_marriage"
                    else "支持独立" if action_id == "support_independence"
                    else "军事通行权" if action_id == "ask_military_access"
                    else "附庸关系" if action_id == "offer_vassalization"
                    else "议和提议" if action_id == "peace_offer"
                    else "联盟")
                inspection["legality"]["reasons"] = [reason(
                    "INBOUND_RULES_UNIMPLEMENTED",
                    f"已观察到匹配的入站{family_label}提议，但接受或拒绝的原生规则与响应适配尚未实现。",
                    "bridge_policy")]
                response_capability_name = _inbound_response_capability(action_id)
                response_capability = (
                    inspection["session"]["status"] == "ready"
                    and response_capability_name in self._installation_capabilities())
                if response_capability:
                    # The installation capability proves that the bridge has a
                    # native response adapter.  It does not prove that this
                    # particular proposal is still pending or that native
                    # response rules are currently valid.  Keep adapter
                    # support and authorization visible on all native query
                    # outcomes; legality and decision-country proof remain
                    # separate fields below and still gate execution.
                    inbound_capability_code = (
                        "NATIVE_INBOUND_ROYAL_MARRIAGE_RESPONSE_CAPABILITY_ACKNOWLEDGED"
                        if action_id == "offer_royal_marriage"
                        else "NATIVE_INBOUND_SUPPORT_INDEPENDENCE_RESPONSE_CAPABILITY_ACKNOWLEDGED"
                        if action_id == "support_independence"
                        else "NATIVE_INBOUND_MILITARY_ACCESS_RESPONSE_CAPABILITY_ACKNOWLEDGED"
                        if action_id == "ask_military_access"
                        else "NATIVE_INBOUND_VASSALIZATION_RESPONSE_CAPABILITY_ACKNOWLEDGED"
                        if action_id == "offer_vassalization"
                        else "NATIVE_INBOUND_PEACE_RESPONSE_CAPABILITY_ACKNOWLEDGED"
                        if action_id == "peace_offer"
                        else "NATIVE_INBOUND_RESPONSE_CAPABILITY_ACKNOWLEDGED")
                    inbound_family_text = (
                        "王室联姻" if action_id == "offer_royal_marriage"
                        else "支持独立" if action_id == "support_independence"
                        else "军事通行权" if action_id == "ask_military_access"
                        else "附庸关系" if action_id == "offer_vassalization"
                        else "议和提议" if action_id == "peace_offer"
                        else "联盟")
                    inspection["interface_support"]["execute"] = "native_inbound_response"
                    inspection["authorization"] = {
                        "status": "available",
                        "reasons": [reason(
                            inbound_capability_code,
                            f"安装确认允许桥接使用当前入站{inbound_family_text}响应适配器；本次原生合法性和决策方证明仍由复查结果单独决定。",
                            "installation_capability", True)],
                        "complete": True,
                    }
                if response_capability:
                    inspector = getattr(self.session, "inspect_native_inbound_response", None)
                    date_raw = inspection["session"].get("date_raw")
                    if callable(inspector) and isinstance(date_raw, int) and not isinstance(date_raw, bool):
                        try:
                            query_id = "inbound_inspect_" + uuid.uuid4().hex
                            if action_id in ("offer_royal_marriage", "support_independence",
                                             "ask_military_access", "offer_vassalization",
                                             "peace_offer"):
                                native = inspector(
                                    query_id, private_context["actor"], phase, date_raw,
                                    private_context["native_proposal_id"], action_id=action_id)
                            else:
                                native = inspector(
                                    query_id, private_context["actor"], phase, date_raw,
                                    private_context["native_proposal_id"])
                        except Exception:
                            native = {"error_code": "QUERY_NATIVE_INBOUND_CALL_UNKNOWN"}
                    else:
                        native = {"error_code": "NATIVE_INBOUND_QUERY_ADAPTER_UNAVAILABLE"}
                    inspection["interface_support"]["query"] = "native_inbound_rules"
                    if not isinstance(native, dict):
                        native = {"error_code": "QUERY_NATIVE_INBOUND_RESULT_INVALID"}
                    if "error_code" in native:
                        code = native.get("error_code")
                        if not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9_]{1,80}", code):
                            code = "QUERY_NATIVE_INBOUND_RESULT_INVALID"
                        inspection["legality"]["reasons"] = [reason(
                            code, "本次入站响应规则查询没有取得完整结果，不能执行。", "runtime_error")]
                    else:
                        before_field = (
                            "royal_marriage_before" if action_id == "offer_royal_marriage"
                            else "support_independence_before" if action_id == "support_independence"
                            else "military_access_before" if action_id == "ask_military_access"
                            else "vassalization_before" if action_id == "offer_vassalization"
                            else "war_before" if action_id == "peace_offer"
                            else "alliance_before")
                        inspection["native_inbound_inspection"] = {
                            key: native.get(key) for key in (
                                "event", "action_id", "actor", "recipient", "phase", "date_raw",
                                "pending_active", "decision_country", "decision_country_verified",
                                "native_validity", "response_rules_complete", "family", "reason",
                                 "war_before", "native_current_war", "native_current_war_readable",
                                 "war_active", "war_readable", "peace_payload_complete",
                                 "selected_terms_complete", "term_count", "selected_term_count",
                                 "peace_context", "costs",
                                 before_field, "native_current_support_independence",
                                 "native_current_support_independence_readable",
                                 "military_access_active",
                                 "military_access_state_verified",
                                 "native_current_military_access",
                                 "native_current_military_access_readable",
                                 "native_current_vassalization",
                                 "native_current_vassalization_readable")
                            if key in native
                        }
                        if action_id == "peace_offer":
                            # Keep the stable semantic context at the public
                            # top level for the runner.  The nested native
                            # inspection remains available for diagnostics,
                            # but no native proposal id or process metadata
                            # crosses this boundary.
                            for key in (
                                    "war_before", "native_current_war",
                                    "native_current_war_readable", "war_active",
                                    "war_readable", "peace_payload_complete",
                                    "selected_terms_complete", "term_count",
                                    "selected_term_count"):
                                if key in native:
                                    inspection[key] = native[key]
                            context = ObserverSession._copy_public_peace_context(
                                native.get("peace_context"))
                            nested_costs = inspection["native_inbound_inspection"].get("costs")
                            if nested_costs is not None and not ObserverSession._safe_public_peace_value(
                                    nested_costs):
                                inspection["native_inbound_inspection"].pop("costs", None)
                            if context is not None:
                                inspection["peace_context"] = context
                                inspection["parameters"]["actual"] = {
                                    **inspection["parameters"]["actual"],
                                    "original_actor": observed["actor"],
                                    "original_recipient": observed["recipient"],
                                    "peace_context": context,
                                }
                            inspection["family"] = "peace"
                        pending_active = native.get("pending_active") is True
                        observed["currently_pending"] = pending_active
                        decision_verified = native.get("decision_country_verified") is True
                        native_validity = native.get("native_validity") is True
                        rules_complete = native.get("response_rules_complete") is True
                        inspection["decision_country_verified"] = decision_verified
                        raw_native_reason = native.get("reason")
                        if raw_native_reason is None:
                            native_reason = "none"
                        elif (not isinstance(raw_native_reason, str)
                              or (raw_native_reason != "none"
                                  and not re.fullmatch(r"[A-Z0-9_]{1,96}", raw_native_reason))):
                            native_reason = "NATIVE_INBOUND_RESULT_INVALID"
                        else:
                            native_reason = raw_native_reason
                        if native_reason not in ("none", "PENDING_NOT_ACTIVE"):
                            inspection["legality"]["reasons"] = [reason(
                                native_reason,
                                "原生入站响应检查因运行时错误未完成，不能判断提议是否失效或当前响应是否合法。",
                                "runtime_error")]
                        elif native_reason == "PENDING_NOT_ACTIVE":
                            inspection["proposal_status"] = "invalidated"
                            inspection["legality"]["status"] = "unavailable"
                            inspection["legality"]["reasons"] = [reason(
                                "NATIVE_INBOUND_PENDING_INVALIDATED",
                                "原生复查显示该入站提议已不再处于可响应的pending状态。",
                                "native_rule", True)]
                        elif not pending_active and "reason" not in native:
                            # Preserve the pre-reason event contract emitted by
                            # older adapters. New native inspection events carry
                            # an explicit reason, so only PENDING_NOT_ACTIVE can
                            # invalidate them.
                            inspection["proposal_status"] = "invalidated"
                            inspection["legality"]["status"] = "unavailable"
                            inspection["legality"]["reasons"] = [reason(
                                "NATIVE_INBOUND_PENDING_INVALIDATED",
                                "原生复查显示该入站提议已不再处于可响应的pending状态。",
                                "native_rule", True)]
                        elif not pending_active:
                            inspection["legality"]["reasons"] = [reason(
                                "NATIVE_INBOUND_INSPECTION_INCONSISTENT",
                                "原生检查标记提议不处于pending，但没有提供PENDING_NOT_ACTIVE原因。",
                                "runtime_error")]
                        elif not decision_verified:
                            inspection["legality"]["reasons"] = [reason(
                                "NATIVE_INBOUND_DECISION_COUNTRY_UNVERIFIED",
                                "原生复查没有验证法国为当前响应决策方。", "native_rule")]
                        elif (action_id == "peace_offer"
                              and (native.get("peace_payload_complete") is not True
                                   or native.get("selected_terms_complete") is not True
                                   or not isinstance(native.get("peace_context"), dict)
                                   or native["peace_context"].get("complete") is not True)):
                            inspection["legality"]["reasons"] = [reason(
                                "NATIVE_PEACE_PAYLOAD_INCOMPLETE",
                                "原生入站议和上下文尚未完整读取，不能执行接受或拒绝。",
                                "native_rule")]
                        elif not native_validity:
                            inspection["legality"]["status"] = "unavailable"
                            inspection["legality"]["reasons"] = [reason(
                                "NATIVE_INBOUND_VALIDITY_FALSE",
                                "原生入站响应合法性检查返回false。", "native_rule")]
                        elif not rules_complete:
                            inspection["legality"]["reasons"] = [reason(
                                "NATIVE_INBOUND_RESPONSE_RULES_INCOMPLETE",
                                "原生入站响应规则查询尚未覆盖完整UI guard，不能执行。", "native_rule")]
                        else:
                            inspection["legality"] = {
                                "status": "available",
                                "reasons": [reason(
                                    "NATIVE_INBOUND_RESPONSE_RULES_TRUE",
                                    "当前session、法国决策方、pending状态及原生响应规则均已复查通过。",
                                    "native_rule", True)],
                                "complete": True,
                            }
            else:
                family_label = (
                    "王室联姻" if action_id == "offer_royal_marriage"
                    else "支持独立" if action_id == "support_independence"
                    else "军事通行权" if action_id == "ask_military_access"
                    else "附庸关系" if action_id == "offer_vassalization"
                    else "议和提议" if action_id == "peace_offer"
                    else "联盟")
                inspection["legality"]["reasons"] = [reason(
                    "INVALID_PROPOSAL_REFERENCE",
                    f"没有与该公开编号匹配的已观察入站{family_label}提议，不能执行响应。",
                    "bridge_policy", True)]
        native_offer_submission_acknowledged = (
            inspection["session"]["status"] == "ready"
            and self._native_offer_scope(action_id, actor, phase)
            and _NATIVE_OFFER_SUBMISSION_CAPABILITY in self._installation_capabilities())
        if native_offer_submission_acknowledged:
            inspection["interface_support"] = {
                **inspection["interface_support"],
                "execute": "native_offer_submission",
            }
            inspection["authorization"] = {
                "status": "available",
                "reasons": [reason("NATIVE_OFFER_SUBMISSION_CAPABILITY_ACKNOWLEDGED",
                                    "安装确认明确允许桥接提交法国发起的联盟提议。",
                                    "installation_capability", True)],
                "complete": True,
            }
        native_royal_submission_acknowledged = (
            inspection["session"]["status"] == "ready"
            and self._native_royal_scope(action_id, actor, phase)
            and _NATIVE_ROYAL_MARRIAGE_SUBMISSION_CAPABILITY in self._installation_capabilities())
        if native_royal_submission_acknowledged:
            inspection["interface_support"] = {
                **inspection["interface_support"],
                "execute": "native_royal_marriage_submission",
            }
            inspection["authorization"] = {
                "status": "available",
                "reasons": [reason(
                    "NATIVE_ROYAL_MARRIAGE_SUBMISSION_CAPABILITY_ACKNOWLEDGED",
                    "安装确认允许桥接提交法国发起的王室联姻操作。",
                    "installation_capability", True)],
                "complete": True,
            }
        if (inspection["session"]["status"] == "ready"
                and action_id == "dissolve_alliance" and actor == "FRA" and phase == "initiate"
                and _NATIVE_DISSOLVE_SUBMISSION_CAPABILITY in self._installation_capabilities()):
            inspection["interface_support"]["execute"] = "native_dissolve_submission"
            inspection["authorization"] = {
                "status": "available", "complete": True,
                "reasons": [reason("NATIVE_DISSOLVE_SUBMISSION_CAPABILITY_ACKNOWLEDGED",
                                   "安装确认允许桥接提交法国主动断绝同盟。",
                                   "installation_capability", True)]}
        native_improve_submission_acknowledged = (
            inspection["session"]["status"] == "ready"
            and self._native_improve_scope(action_id, actor, phase)
            and _NATIVE_IMPROVE_RELATIONS_SUBMISSION_CAPABILITY
            in self._installation_capabilities())
        if native_improve_submission_acknowledged:
            inspection["interface_support"]["execute"] = "native_improve_relations_submission"
            inspection["authorization"] = {
                "status": "available", "complete": True,
                "reasons": [reason(
                    "NATIVE_IMPROVE_RELATIONS_SUBMISSION_CAPABILITY_ACKNOWLEDGED",
                    "安装确认允许桥接提交法国对目标国家的改善关系任务。",
                    "installation_capability", True)]}
        native_spy_network_submission_acknowledged = (
            inspection["session"]["status"] == "ready"
            and self._native_spy_network_scope(action_id, actor, phase)
            and _NATIVE_SPY_NETWORK_SUBMISSION_CAPABILITY
            in self._installation_capabilities())
        if native_spy_network_submission_acknowledged:
            inspection["interface_support"]["execute"] = "native_spy_network_submission"
            inspection["authorization"] = {
                "status": "available", "complete": True,
                "reasons": [reason(
                    "NATIVE_SPY_NETWORK_SUBMISSION_CAPABILITY_ACKNOWLEDGED",
                    "安装确认允许桥接提交法国对目标国家的间谍网任务。",
                    "installation_capability", True)]}
        native_guarantee_submission_acknowledged = (
            inspection["session"]["status"] == "ready"
            and self._native_guarantee_scope(action_id, actor, phase)
            and _NATIVE_GUARANTEE_SUBMISSION_CAPABILITY
            in self._installation_capabilities())
        if native_guarantee_submission_acknowledged:
            inspection["interface_support"]["execute"] = "native_guarantee_submission"
            inspection["authorization"] = {
                "status": "available", "complete": True,
                "reasons": [reason(
                    "NATIVE_GUARANTEE_SUBMISSION_CAPABILITY_ACKNOWLEDGED",
                    "安装确认允许桥接提交法国对目标国家的独立保证操作。",
                    "installation_capability", True)]}
        native_support_independence_submission_acknowledged = (
            inspection["session"]["status"] == "ready"
            and self._native_support_independence_scope(action_id, actor, phase)
            and _NATIVE_SUPPORT_INDEPENDENCE_SUBMISSION_CAPABILITY
            in self._installation_capabilities())
        if native_support_independence_submission_acknowledged:
            inspection["interface_support"]["execute"] = (
                "native_support_independence_submission")
            inspection["authorization"] = {
                "status": "available", "complete": True,
                "reasons": [reason(
                    "NATIVE_SUPPORT_INDEPENDENCE_SUBMISSION_CAPABILITY_ACKNOWLEDGED",
                    "安装确认允许桥接提交法国对目标国家的支持独立操作。",
                    "installation_capability", True)]}
        native_military_access_submission_acknowledged = (
            inspection["session"]["status"] == "ready"
            and self._native_military_access_scope(action_id, actor, phase)
            and _NATIVE_MILITARY_ACCESS_SUBMISSION_CAPABILITY
            in self._installation_capabilities())
        if native_military_access_submission_acknowledged:
            inspection["interface_support"]["execute"] = (
                "native_military_access_submission")
            inspection["authorization"] = {
                "status": "available", "complete": True,
                "reasons": [reason(
                    "NATIVE_MILITARY_ACCESS_SUBMISSION_CAPABILITY_ACKNOWLEDGED",
                    "安装确认允许桥接提交法国发起的军事通行权操作。",
                    "installation_capability", True)]}
        native_insult_submission_acknowledged = (
            inspection["session"]["status"] == "ready"
            and self._native_insult_scope(action_id, actor, phase)
            and _NATIVE_INSULT_SUBMISSION_CAPABILITY
            in self._installation_capabilities())
        if native_insult_submission_acknowledged:
            inspection["interface_support"]["execute"] = "native_insult_submission"
            inspection["authorization"] = {
                "status": "available", "complete": True,
                "reasons": [reason(
                    "NATIVE_INSULT_SUBMISSION_CAPABILITY_ACKNOWLEDGED",
                    "安装确认允许桥接提交法国发起的侮辱操作。",
                    "installation_capability", True)]}
        native_rival_submission_acknowledged = (
            inspection["session"]["status"] == "ready"
            and self._native_rival_scope(action_id, actor, phase)
            and _NATIVE_RIVAL_SUBMISSION_CAPABILITY
            in self._installation_capabilities())
        if native_rival_submission_acknowledged:
            # The submission ACK proves adapter support for this FRA/initiate
            # scope. It does not prove that the current target is legal;
            # target, membership, slot, and war checks remain legality data.
            inspection["interface_support"]["execute"] = "native_rival_submission"
            inspection["authorization"] = {
                "status": "available", "complete": True,
                "reasons": [reason(
                    "NATIVE_RIVAL_SUBMISSION_CAPABILITY_ACKNOWLEDGED",
                    "安装确认允许桥接提交法国发起的宿敌操作；本次目标是否合法由原生合法性查询单独决定。",
                    "installation_capability", True)]}
        native_vassalization_submission_acknowledged = (
            inspection["session"]["status"] == "ready"
            and self._native_vassalization_scope(action_id, actor, phase)
            and _NATIVE_VASSALIZATION_SUBMISSION_CAPABILITY
            in self._installation_capabilities())
        if native_vassalization_submission_acknowledged:
            inspection["interface_support"]["execute"] = (
                "native_vassalization_submission")
            inspection["authorization"] = {
                "status": "available", "complete": True,
                "reasons": [reason(
                    "NATIVE_VASSALIZATION_SUBMISSION_CAPABILITY_ACKNOWLEDGED",
                    "安装确认允许桥接提交法国发起的附庸关系操作；本次目标是否合法由原生查询单独决定。",
                    "installation_capability", True)]}
        native_declare_war_submission_acknowledged = (
            inspection["session"]["status"] == "ready"
            and self._native_declare_war_scope(action_id, actor, phase)
            and _NATIVE_DECLARE_WAR_SUBMISSION_CAPABILITY
            in self._installation_capabilities())
        if native_declare_war_submission_acknowledged:
            inspection["interface_support"]["execute"] = (
                "native_declare_war_submission")
            inspection["authorization"] = {
                "status": "available", "complete": True,
                "reasons": [reason(
                    "NATIVE_DECLARE_WAR_SUBMISSION_CAPABILITY_ACKNOWLEDGED",
                    "安装确认允许桥接提交法国发起的宣战操作；本次参数和原生合法性仍需单独决定。",
                    "installation_capability", True)]}
        peace_submission_parameters = peace_execution_parameters
        if peace_submission_parameters is None and action_id in _PEACE_EXECUTION_ACTIONS:
            try:
                peace_submission_parameters = normalize_peace_execution_parameters(
                    action_id, actor, recipient, phase, parameters)
            except (TypeError, ValueError):
                peace_submission_parameters = None
        native_peace_submission_acknowledged = (
            peace_submission_parameters is not None
            and inspection["session"]["status"] == "ready"
            and _NATIVE_PEACE_SUBMISSION_CAPABILITY
            in self._installation_capabilities())
        if native_peace_submission_acknowledged:
            inspection["interface_support"] = {
                **inspection["interface_support"],
                "execute": "native_peace_submission",
                "complete": True,
            }
            inspection["authorization"] = {
                "status": "available", "complete": True,
                "reasons": [reason(
                    "NATIVE_PEACE_SUBMISSION_CAPABILITY_ACKNOWLEDGED",
                    "安装确认允许桥接提交法国发起的议和操作；本次原生合法性由最新议和检查单独决定。",
                    "installation_capability", True)]}
        alliance_query_scope = (
            action_id in ("offer_alliance", "dissolve_alliance")
            and (phase == "initiate" or not inbound_response_phase))
        royal_query_scope = (
            action_id in ("offer_royal_marriage", "break_royal_ties")
            and phase == "initiate"
            and _NATIVE_ROYAL_MARRIAGE_QUERY_CAPABILITY in self._installation_capabilities())
        improve_query_scope = (
            action_id in ("improve_relations", "stop_improving_relations")
            and phase == "initiate"
            and _NATIVE_IMPROVE_RELATIONS_QUERY_CAPABILITY in self._installation_capabilities())
        spy_network_query_scope = (
            action_id in ("build_spy_network", "stop_building_spy_network")
            and phase == "initiate"
            and _NATIVE_SPY_NETWORK_QUERY_CAPABILITY in self._installation_capabilities())
        guarantee_query_scope = (
            action_id in ("proclaim_guarantee", "revoke_guarantee")
            and phase == "initiate"
            and _NATIVE_GUARANTEE_QUERY_CAPABILITY in self._installation_capabilities())
        support_independence_query_scope = (
            action_id in ("support_independence", "revoke_support_independence")
            and phase == "initiate"
            and _NATIVE_SUPPORT_INDEPENDENCE_QUERY_CAPABILITY
            in self._installation_capabilities())
        military_access_query_scope = (
            action_id in ("ask_military_access", "cancel_military_access")
            and phase == "initiate"
            and _NATIVE_MILITARY_ACCESS_QUERY_CAPABILITY
            in self._installation_capabilities())
        insult_query_scope = (
            action_id in _INSULT_ACTIONS
            and phase == "initiate"
            and _NATIVE_INSULT_QUERY_CAPABILITY in self._installation_capabilities())
        rival_query_scope = (
            action_id in ("set_rival", "remove_rival")
            and phase == "initiate"
            and _NATIVE_RIVAL_QUERY_CAPABILITY in self._installation_capabilities())
        vassalization_query_scope = (
            action_id in _VASSALIZATION_ACTIONS
            and phase == "initiate"
            and _NATIVE_VASSALIZATION_QUERY_CAPABILITY
            in self._installation_capabilities())
        declare_war_query_scope = (
            action_id == "declare_war"
            and phase == "initiate"
            and _NATIVE_DECLARE_WAR_QUERY_CAPABILITY
            in self._installation_capabilities())
        peace_empty_offer_query_scope = (
            action_id == "white_peace"
            and phase == "initiate"
            and isinstance(parameters.get("peace_context"), dict)
            and set(parameters["peace_context"]) in (
                {"war_id", "terms"}, {"war_id", "direction", "terms"})
            and parameters["peace_context"].get("terms") == []
            and parameters["peace_context"].get("direction", "demand")
            in ("demand", "offer")
            and _NATIVE_PEACE_EMPTY_OFFER_QUERY_CAPABILITY
            in self._installation_capabilities())
        peace_money_offer_query_scope = (
            action_id == "demand_ducats"
            and phase == "initiate"
            and peace_money_selection is not None
            and _NATIVE_PEACE_MONEY_OFFER_QUERY_CAPABILITY
            in self._installation_capabilities())
        peace_province_offer_query_scope = (
            action_id == "cede_province"
            and phase == "initiate"
            and peace_province_selection is not None
            and _NATIVE_PEACE_PROVINCE_OFFER_QUERY_CAPABILITY
            in self._installation_capabilities())
        peace_execution_query_capability = (
            self._peace_execution_capability_for(
                peace_execution_parameters, action_id)
            if peace_execution_parameters is not None else None)
        peace_execution_query_scope = (
            peace_execution_parameters is not None
            and peace_execution_query_capability is not None
            and phase == "initiate"
            and peace_execution_query_capability in self._installation_capabilities())
        peace_empty_offer_selection = (
            parameters.get("peace_context", {}).get("war_id")
            if peace_empty_offer_query_scope
            and isinstance(parameters.get("peace_context"), dict) else None)
        peace_empty_offer_direction = (
            parameters.get("peace_context", {}).get("direction", "demand")
            if peace_empty_offer_query_scope
            and isinstance(parameters.get("peace_context"), dict) else "demand")
        peace_context_query_scope = (
            action.category == "peace_term"
            and phase == "initiate"
            and parameters == {}
            and _NATIVE_PEACE_CONTEXT_QUERY_CAPABILITY
            in self._installation_capabilities())
        if ((alliance_query_scope or royal_query_scope or improve_query_scope
             or spy_network_query_scope or guarantee_query_scope
             or support_independence_query_scope or military_access_query_scope
             or insult_query_scope or rival_query_scope or vassalization_query_scope
             or declare_war_query_scope or peace_context_query_scope
             or peace_empty_offer_query_scope or peace_money_offer_query_scope
             or peace_province_offer_query_scope or peace_execution_query_scope)
                and self.session is not None and inspection["session"]["status"] == "ready"):
            if alliance_query_scope:
                inspection["observed_native_objects"] = self.session.alliance_objects(actor, recipient)
            inspection["interface_support"]["query"] = (
                "partial_native_rules" if (improve_query_scope or spy_network_query_scope
                                             or support_independence_query_scope
                                             or military_access_query_scope or insult_query_scope
                                             or rival_query_scope or vassalization_query_scope
                                              or declare_war_query_scope
                                              or peace_execution_query_scope
                                             or peace_money_offer_query_scope
                                             or peace_province_offer_query_scope)
                else "partial_native_queue_read")
            if royal_query_scope:
                inspector = getattr(self.session, "inspect_royal_marriage", None)
                if callable(inspector):
                    try:
                        native = inspector(action_id, actor, recipient, phase)
                    except Exception:
                        native = {"error_code": "QUERY_NATIVE_ROYAL_CALL_UNKNOWN"}
                else:
                    native = {"error_code": "NATIVE_ROYAL_MARRIAGE_QUERY_ADAPTER_UNAVAILABLE"}
            elif improve_query_scope:
                inspector = getattr(self.session, "inspect_improve_relations", None)
                if callable(inspector):
                    try:
                        native = inspector(action_id, actor, recipient, phase)
                    except Exception:
                        native = {"error_code": "QUERY_NATIVE_IMPROVE_RELATIONS_CALL_UNKNOWN"}
                else:
                    native = {"error_code": "NATIVE_IMPROVE_RELATIONS_QUERY_ADAPTER_UNAVAILABLE"}
            elif spy_network_query_scope:
                inspector = getattr(self.session, "inspect_spy_network", None)
                if callable(inspector):
                    try:
                        native = inspector(action_id, actor, recipient, phase)
                    except Exception:
                        native = {"error_code": "QUERY_NATIVE_SPY_NETWORK_CALL_UNKNOWN"}
                else:
                    native = {"error_code": "NATIVE_SPY_NETWORK_QUERY_ADAPTER_UNAVAILABLE"}
            elif guarantee_query_scope:
                inspector = getattr(self.session, "inspect_guarantee", None)
                if callable(inspector):
                    try:
                        native = inspector(action_id, actor, recipient, phase)
                    except Exception:
                        native = {"error_code": "QUERY_NATIVE_GUARANTEE_CALL_UNKNOWN"}
                else:
                    native = {"error_code": "NATIVE_GUARANTEE_QUERY_ADAPTER_UNAVAILABLE"}
            elif support_independence_query_scope:
                inspector = getattr(self.session, "inspect_support_independence", None)
                if callable(inspector):
                    try:
                        native = inspector(action_id, actor, recipient, phase)
                    except Exception:
                        native = {"error_code": "QUERY_NATIVE_SUPPORT_INDEPENDENCE_CALL_UNKNOWN"}
                else:
                    native = {"error_code": "NATIVE_SUPPORT_INDEPENDENCE_QUERY_ADAPTER_UNAVAILABLE"}
            elif military_access_query_scope:
                inspector = getattr(self.session, "inspect_military_access", None)
                if callable(inspector):
                    try:
                        native = inspector(action_id, actor, recipient, phase)
                    except Exception:
                        native = {"error_code": "QUERY_NATIVE_MILITARY_ACCESS_CALL_UNKNOWN"}
                else:
                    native = {"error_code": "NATIVE_MILITARY_ACCESS_QUERY_ADAPTER_UNAVAILABLE"}
            elif insult_query_scope:
                inspector = getattr(self.session, "inspect_insult", None)
                selected_id = (parameters.get("insult_id")
                               if action_id == "scornful_insult"
                               and "insult_id" in parameters else
                               -1 if action_id == "send_insult" else None)
                if callable(inspector):
                    try:
                        native = inspector(action_id, actor, recipient, phase, selected_id)
                    except Exception:
                        native = {"error_code": "QUERY_NATIVE_INSULT_CALL_UNKNOWN"}
                else:
                    native = {"error_code": "NATIVE_INSULT_QUERY_ADAPTER_UNAVAILABLE"}
            elif rival_query_scope:
                inspector = getattr(self.session, "inspect_rival", None)
                if callable(inspector):
                    try:
                        native = inspector(action_id, actor, recipient, phase)
                    except Exception:
                        native = {"error_code": "QUERY_NATIVE_RIVAL_CALL_UNKNOWN"}
                else:
                    native = {"error_code": "NATIVE_RIVAL_QUERY_ADAPTER_UNAVAILABLE"}
            elif vassalization_query_scope:
                inspector = getattr(self.session, "inspect_vassalization", None)
                if callable(inspector):
                    try:
                        native = inspector(action_id, actor, recipient, phase)
                    except Exception:
                        native = {"error_code": "QUERY_NATIVE_VASSALIZATION_CALL_UNKNOWN"}
                else:
                    native = {"error_code": "NATIVE_VASSALIZATION_QUERY_ADAPTER_UNAVAILABLE"}
            elif declare_war_query_scope:
                inspector = getattr(self.session, "inspect_declare_war", None)
                if callable(inspector):
                    try:
                        native = inspector(action_id, actor, recipient, phase,
                                           parameters=parameters)
                    except Exception:
                        native = {"error_code": "QUERY_NATIVE_DECLARE_WAR_CALL_UNKNOWN"}
                else:
                    native = {"error_code": "NATIVE_DECLARE_WAR_QUERY_ADAPTER_UNAVAILABLE"}
            elif peace_execution_query_scope:
                inspector = getattr(self.session, "inspect_peace_execution", None)
                if callable(inspector):
                    try:
                        native = inspector(action_id, actor, recipient, phase,
                                           peace_execution_parameters)
                    except Exception:
                        native = {"error_code": "QUERY_NATIVE_PEACE_EXECUTION_CALL_UNKNOWN"}
                else:
                    native = {"error_code":
                              "NATIVE_PEACE_EXECUTION_INSPECTION_ADAPTER_UNAVAILABLE"}
            elif peace_context_query_scope:
                inspector = getattr(self.session, "inspect_peace_contexts", None)
                if callable(inspector):
                    try:
                        native = inspector(action_id, actor, recipient, phase)
                    except Exception:
                        native = {"error_code": "QUERY_NATIVE_PEACE_CONTEXT_CALL_UNKNOWN"}
                else:
                    native = {"error_code": "NATIVE_PEACE_CONTEXT_QUERY_ADAPTER_UNAVAILABLE"}
            elif peace_empty_offer_query_scope:
                inspector = getattr(self.session, "inspect_peace_empty_offer", None)
                if callable(inspector):
                    try:
                        native = inspector(
                            action_id, actor, recipient, phase,
                            peace_empty_offer_selection,
                            peace_empty_offer_direction)
                    except Exception:
                        native = {"error_code": "QUERY_NATIVE_PEACE_EMPTY_OFFER_CALL_UNKNOWN"}
                else:
                    native = {"error_code": "NATIVE_PEACE_EMPTY_OFFER_QUERY_ADAPTER_UNAVAILABLE"}
            elif peace_money_offer_query_scope:
                inspector = getattr(self.session, "inspect_peace_money_offer", None)
                if callable(inspector):
                    try:
                        native = inspector(
                            action_id, actor, recipient, phase,
                            peace_money_selection)
                    except Exception:
                        native = {"error_code": "QUERY_NATIVE_PEACE_MONEY_CALL_UNKNOWN"}
                else:
                    native = {"error_code": "NATIVE_PEACE_MONEY_QUERY_ADAPTER_UNAVAILABLE"}
            elif peace_province_offer_query_scope:
                inspector = getattr(self.session, "inspect_peace_province_offer", None)
                if callable(inspector):
                    try:
                        native = inspector(
                            action_id, actor, recipient, phase,
                            peace_province_selection)
                    except Exception:
                        native = {"error_code": "QUERY_NATIVE_PEACE_PROVINCE_CALL_UNKNOWN"}
                else:
                    native = {"error_code": "NATIVE_PEACE_PROVINCE_QUERY_ADAPTER_UNAVAILABLE"}
            else:
                native = self.session.inspect_alliance(action_id, actor, recipient, phase)
            if native is not None:
                if peace_execution_query_scope:
                    return self._apply_peace_execution_inspection(
                        inspection, native, peace_execution_parameters)
                if peace_context_query_scope:
                    inspection["interface_support"]["query"] = (
                        "native_peace_context_inspection")
                    if "error_code" in native:
                        code = native.get("error_code")
                        if not isinstance(code, str) or not re.fullmatch(
                                r"[A-Z0-9_]{1,80}", code):
                            code = "QUERY_NATIVE_RESULT_INVALID"
                        inspection["legality"]["reasons"] = [reason(
                            code,
                            "本次原生战争上下文发现没有取得完整结果，不能推定议和合法性。",
                            "bridge_policy" if code == "QUERY_INFORMATION_SCOPE_UNAVAILABLE"
                            else "runtime_error")]
                    else:
                        inspection["family"] = "peace"
                        inspection["context_discovery"] = native.get(
                            "context_discovery") is True
                        inspection["query_complete"] = native.get(
                            "query_complete") is True
                        inspection["war_context_enumeration_complete"] = native.get(
                            "war_context_enumeration_complete") is True
                        inspection["native_offer_inspected"] = native.get(
                            "native_offer_inspected") is True
                        inspection["full_rules_complete"] = native.get(
                            "full_rules_complete") is True
                        inspection["submitted"] = native.get("submitted") is True
                        inspection["war_contexts"] = list(native.get(
                            "war_contexts", []))
                        inspection["parameters"] = {
                            "requested": {},
                            "actual": None,
                            "candidates": inspection["war_contexts"],
                            "complete": False,
                        }
                        inspection["interface_support"]["execute"] = "unimplemented"
                        inspection["authorization"] = {
                            "status": "unavailable",
                            "reasons": [reason(
                                "PEACE_OFFER_CONTEXT_REQUIRED",
                                "当前查询只发现战争上下文；完整peace_context和议和条款仍需提供，执行适配尚未开放。",
                                "bridge_policy", True)],
                            "complete": True,
                        }
                        inspection["legality"] = {
                            "status": "unknown",
                            "reasons": [reason(
                                "NATIVE_PEACE_CONTEXT_ONLY",
                                "原生查询只枚举当前战争上下文，尚未检查选定议和条款的合法性。",
                                "native_rule")],
                            "complete": False,
                        }
                        inspection["costs"] = {
                            "status": "unknown", "items": [], "complete": False,
                        }
                        inspection["acceptance"] = {
                            "applicability": "applicable" if applies else "not_applicable",
                            "prediction_available": False,
                            "native_total": None,
                            "unit": "unknown" if applies else None,
                            "scale_verified": False,
                            "predicted_response": "unknown" if applies else "not_applicable",
                            "details_available": False,
                            "items": [], "complete": False,
                        }
                    if isinstance(native, dict) and native.get("date_raw") is not None:
                        inspection["session"]["date_raw"] = native.get("date_raw")
                    return inspection
                if peace_empty_offer_query_scope:
                    inspection["interface_support"]["query"] = (
                        "native_peace_empty_offer_inspection")
                    if "error_code" in native:
                        code = native.get("error_code")
                        if not isinstance(code, str) or not re.fullmatch(
                                r"[A-Z0-9_]{1,80}", code):
                            code = "QUERY_NATIVE_RESULT_INVALID"
                        inspection["legality"]["reasons"] = [reason(
                            code,
                            "本次原生空白和平提议检查没有取得完整结果。",
                            "bridge_policy" if code == "QUERY_INFORMATION_SCOPE_UNAVAILABLE"
                            else "runtime_error")]
                    else:
                        inspection["family"] = "peace"
                        for key in (
                                "selected_war_id", "identity_scope",
                                "peace_context", "query_complete",
                                "native_offer_inspected", "pair_at_war",
                                "unique_shared_war", "offer_constructed",
                                "action_constructed", "participant_copy_verified",
                                "offer_identity_verified", "object_unchanged",
                                "cleanup_verified", "validity_called",
                                "native_validity", "common_gate_checked",
                                "common_action_gate", "initiation_gate_checked",
                                "initiation_gate", "native_wrapper_gate_checked",
                                "native_wrapper_gate", "wrapper_identity_verified",
                                "wrapper_payload_unchanged", "native_diagnostic_text",
                                "native_diagnostic_text_decoded",
                                "native_diagnostic_truncated", "diagnostics",
                                "native_evaluation", "native_war_context", "native_payload",
                                "full_rules_complete", "reasons_complete",
                                "submitted"):
                            if key in native:
                                inspection[key] = native[key]
                        inspection["parameters"] = {
                            "requested": parameters,
                            "actual": {"peace_context": {
                                "war_id": native.get("selected_war_id"),
                                "direction": native.get(
                                    "direction",
                                    parameters.get("peace_context", {}).get(
                                        "direction", "demand")),
                                "terms": []}},
                            "candidates": None,
                            "complete": False,
                        }
                        failures = []
                        gate_diagnostics = (
                            ("native_validity", "NATIVE_PEACE_EMPTY_OFFER_VALIDITY_FALSE",
                             "空白和平提议的原生合法性检查返回false。", "validity"),
                            ("common_action_gate", "NATIVE_PEACE_EMPTY_OFFER_COMMON_GATE_FALSE",
                             "空白和平提议的原生通用动作条件返回false。", "common_action_gate"),
                            ("initiation_gate", "NATIVE_PEACE_EMPTY_OFFER_INITIATION_GATE_FALSE",
                             "空白和平提议的原生发起条件返回false。", "initiation_gate"),
                        )
                        for field, code, text, diagnostic_key in gate_diagnostics:
                            if native.get(field) is False:
                                item = reason(code, text, "native_rule")
                                diagnostic = native.get("diagnostics", {}).get(diagnostic_key)
                                if isinstance(diagnostic, dict) and isinstance(
                                        diagnostic.get("text"), str):
                                    item["text"] = diagnostic["text"]
                                failures.append(item)
                        wrapper_state = ObserverSession._peace_wrapper_rule_state(native)
                        if wrapper_state == "failed":
                            failures.append(reason(
                                "NATIVE_PEACE_WRAPPER_GATE_FALSE",
                                "原生议和wrapper规则检查返回false。",
                                "native_rule", True))
                        if failures:
                            inspection["legality"] = {
                                "status": "unavailable", "reasons": failures,
                                "complete": False,
                            }
                        elif (wrapper_state == "verified"
                              and native.get("full_rules_complete") is True
                              and native.get("native_validity") is True
                              and native.get("common_action_gate") is True
                              and native.get("initiation_gate") is True):
                            inspection["legality"] = {
                                "status": "available",
                                "reasons": [reason(
                                    "NATIVE_PEACE_EMPTY_OFFER_RULES_TRUE",
                                    "议和wrapper与三个原生条件检查均已通过。",
                                    "native_rule", True)],
                                "complete": True,
                            }
                        else:
                            inspection["legality"] = {
                                "status": "unknown",
                                "reasons": [reason(
                                    "NATIVE_PEACE_EMPTY_OFFER_RULES_INCOMPLETE",
                                    "三个原生条件检查已读取；完整UI显示、战争角色、议和条款和原因集合仍未核验。",
                                    "native_rule")],
                                "complete": False,
                            }
                        inspection["native_rule_components"] = {
                            "validity_called": native.get("validity_called"),
                            "native_validity": native.get("native_validity"),
                            "common_gate_checked": native.get("common_gate_checked"),
                            "common_action_gate": native.get("common_action_gate"),
                            "initiation_gate_checked": native.get(
                                "initiation_gate_checked"),
                            "initiation_gate": native.get("initiation_gate"),
                            "native_wrapper_gate_checked": native.get(
                                "native_wrapper_gate_checked"),
                            "native_wrapper_gate": native.get("native_wrapper_gate"),
                            "wrapper_identity_verified": native.get(
                                "wrapper_identity_verified"),
                            "wrapper_payload_unchanged": native.get(
                                "wrapper_payload_unchanged"),
                            "full_rules_complete": native.get(
                                "full_rules_complete"),
                            "complete": False,
                        }
                        evaluation = native.get("native_evaluation")
                        if isinstance(evaluation, dict):
                            score_available = evaluation.get("score_available") is True
                            score_raw = evaluation.get("score_raw")
                            aggregate_score_available = (
                                evaluation.get("aggregate_score_available") is True)
                            aggregate_score_raw = evaluation.get(
                                "aggregate_score_raw")
                            factor_items = evaluation.get("items", [])
                            inspection["acceptance"].update({
                                "prediction_available": False,
                                "native_total": (
                                    score_raw if score_available else None),
                                "unit": "unknown",
                                "scale_verified": False,
                                "predicted_response": "unknown",
                                "details_available": (
                                    evaluation.get("factors_available") is True
                                    or bool(factor_items)),
                                "details_complete": (
                                    evaluation.get("factors_complete") is True),
                                "items": list(factor_items),
                                "complete": False,
                            })
                            inspection["costs"]["native_evaluation"] = {
                                "aggregate_score_raw": aggregate_score_raw,
                                "aggregate_score_available": aggregate_score_available,
                                "unit": "unknown",
                                "scale_verified": False,
                                "complete": False,
                            }
                    if isinstance(native, dict) and native.get("date_raw") is not None:
                        inspection["session"]["date_raw"] = native.get("date_raw")
                    return inspection
                if peace_money_offer_query_scope:
                    inspection["interface_support"]["query"] = (
                        "native_peace_money_offer_inspection")
                    if "error_code" in native:
                        code = native.get("error_code")
                        if not isinstance(code, str) or not re.fullmatch(
                                r"[A-Z0-9_]{1,80}", code):
                            code = "QUERY_NATIVE_RESULT_INVALID"
                        inspection["legality"]["reasons"] = [reason(
                            code,
                            "本次原生索取金钱提议检查没有取得完整结果。",
                            "bridge_policy" if code == "QUERY_INFORMATION_SCOPE_UNAVAILABLE"
                            else "runtime_error")]
                    else:
                        inspection["family"] = "peace"
                        for key in (
                                "selected_war_id", "identity_scope",
                                "peace_context", "query_complete",
                                "native_offer_inspected", "pair_at_war",
                                "unique_shared_war", "offer_constructed",
                                "action_constructed", "participant_copy_verified",
                                "offer_identity_verified", "object_unchanged",
                                "cleanup_verified", "validity_called",
                                "native_validity", "common_gate_checked",
                                "common_action_gate", "initiation_gate_checked",
                                "initiation_gate", "native_wrapper_gate_checked",
                                "native_wrapper_gate", "wrapper_identity_verified",
                                "wrapper_payload_unchanged", "native_diagnostic_text",
                                "native_diagnostic_text_decoded",
                                "native_diagnostic_truncated", "diagnostics",
                                "native_evaluation", "native_money", "native_war_context", "native_payload",
                                "full_rules_complete", "reasons_complete",
                                "submitted"):
                            if key in native:
                                inspection[key] = native[key]
                        money = native.get("native_money", {})
                        matched = money.get("parameters_matched") is True
                        actual_terms = []
                        if matched:
                            amount_raw = money.get("requested_amount_raw")
                            if (isinstance(amount_raw, int)
                                    and not isinstance(amount_raw, bool)):
                                actual_terms = [{
                                    "action_id": "demand_ducats",
                                    "amount": f"{amount_raw // 1000}.{(amount_raw % 1000) // 100}",
                                    "amount_raw": amount_raw,
                                    "payer": money.get("payer"),
                                    "claimant": money.get("claimant"),
                                }]
                        inspection["parameters"] = {
                            "requested": parameters,
                            "actual": {"peace_context": {
                                "war_id": native.get("selected_war_id"),
                                "direction": money.get(
                                    "direction", parameters.get(
                                        "peace_context", {}).get(
                                            "direction", "demand")),
                                "terms": actual_terms}},
                            "candidates": None,
                            "complete": matched,
                        }
                        failures = []
                        if money.get("amount_within_limit") is False:
                            failures.append(reason(
                                "NATIVE_PEACE_MONEY_AMOUNT_EXCEEDS_LIMIT",
                                "索取金额超过原生钱款条款上限。",
                                "native_rule", True))
                        gate_diagnostics = (
                            ("native_validity", "NATIVE_PEACE_MONEY_VALIDITY_FALSE",
                             "索取金钱提议的原生合法性检查返回false。", "validity"),
                            ("common_action_gate", "NATIVE_PEACE_MONEY_COMMON_GATE_FALSE",
                             "索取金钱提议的原生通用动作条件返回false。", "common_action_gate"),
                            ("initiation_gate", "NATIVE_PEACE_MONEY_INITIATION_GATE_FALSE",
                             "索取金钱提议的原生发起条件返回false。", "initiation_gate"),
                        )
                        if not failures:
                            for field, code, text, diagnostic_key in gate_diagnostics:
                                if native.get(field) is False:
                                    item = reason(code, text, "native_rule")
                                    diagnostic = native.get("diagnostics", {}).get(
                                        diagnostic_key)
                                    if (isinstance(diagnostic, dict)
                                            and isinstance(diagnostic.get("text"), str)):
                                        item["text"] = diagnostic["text"]
                                    failures.append(item)
                        wrapper_state = ObserverSession._peace_wrapper_rule_state(native)
                        if wrapper_state == "failed":
                            failures.append(reason(
                                "NATIVE_PEACE_WRAPPER_GATE_FALSE",
                                "原生议和wrapper规则检查返回false。",
                                "native_rule", True))
                        if failures:
                            inspection["legality"] = {
                                "status": "unavailable", "reasons": failures,
                                "complete": any(item["code"] ==
                                                 "NATIVE_PEACE_MONEY_AMOUNT_EXCEEDS_LIMIT"
                                                 for item in failures),
                            }
                        elif (wrapper_state == "verified"
                              and native.get("full_rules_complete") is True
                              and native.get("native_validity") is True
                              and native.get("common_action_gate") is True
                              and native.get("initiation_gate") is True
                              and money.get("parameters_matched") is True):
                            inspection["legality"] = {
                                "status": "available",
                                "reasons": [reason(
                                    "NATIVE_PEACE_MONEY_OFFER_RULES_TRUE",
                                    "金钱条款的议和wrapper、金额复制和原生条件均已通过。",
                                    "native_rule", True)],
                                "complete": True,
                            }
                        else:
                            inspection["legality"] = {
                                "status": "unknown",
                                "reasons": [reason(
                                    "NATIVE_PEACE_MONEY_OFFER_RULES_INCOMPLETE",
                                    "金钱条款的三项原生条件已读取；完整UI、战争角色、其他议和条款和原因集合仍未核验。",
                                    "native_rule")],
                                "complete": False,
                            }
                        inspection["native_rule_components"] = {
                            "validity_called": native.get("validity_called"),
                            "native_validity": native.get("native_validity"),
                            "common_gate_checked": native.get("common_gate_checked"),
                            "common_action_gate": native.get("common_action_gate"),
                            "initiation_gate_checked": native.get(
                                "initiation_gate_checked"),
                            "initiation_gate": native.get("initiation_gate"),
                            "native_wrapper_gate_checked": native.get(
                                "native_wrapper_gate_checked"),
                            "native_wrapper_gate": native.get("native_wrapper_gate"),
                            "wrapper_identity_verified": native.get(
                                "wrapper_identity_verified"),
                            "wrapper_payload_unchanged": native.get(
                                "wrapper_payload_unchanged"),
                            "native_money": native.get("native_money"),
                            "full_rules_complete": native.get(
                                "full_rules_complete"),
                            "complete": False,
                        }
                        evaluation = native.get("native_evaluation")
                        if isinstance(evaluation, dict):
                            score_available = evaluation.get("score_available") is True
                            score_raw = evaluation.get("score_raw")
                            aggregate_score_available = (
                                evaluation.get("aggregate_score_available") is True)
                            aggregate_score_raw = evaluation.get(
                                "aggregate_score_raw")
                            factor_items = evaluation.get("items", [])
                            inspection["acceptance"].update({
                                "prediction_available": False,
                                "native_total": (
                                    score_raw if score_available else None),
                                "unit": "unknown",
                                "scale_verified": False,
                                "predicted_response": "unknown",
                                "details_available": (
                                    evaluation.get("factors_available") is True
                                    or bool(factor_items)),
                                "details_complete": (
                                    evaluation.get("factors_complete") is True),
                                "items": list(factor_items),
                                "complete": False,
                            })
                            inspection["costs"]["native_evaluation"] = {
                                "aggregate_score_raw": aggregate_score_raw,
                                "aggregate_score_available": aggregate_score_available,
                                "unit": "unknown",
                                "scale_verified": False,
                                "complete": False,
                            }
                    if isinstance(native, dict) and native.get("date_raw") is not None:
                        inspection["session"]["date_raw"] = native.get("date_raw")
                    return inspection
                if peace_province_offer_query_scope:
                    inspection["interface_support"]["query"] = (
                        "native_peace_province_offer_inspection")
                    if "error_code" in native:
                        code = native.get("error_code")
                        if not isinstance(code, str) or not re.fullmatch(
                                r"[A-Z0-9_]{1,80}", code):
                            code = "QUERY_NATIVE_RESULT_INVALID"
                        message = (
                            "当前原生 QUERY7 只接受至少一个省份的 offer；空候选 offer 没有对应的查询协议。"
                            if code == "QUERY_PEACE_PROVINCE_OFFER_CANDIDATE_ENUMERATION_UNAVAILABLE"
                            else "本次原生割让省份条款检查没有取得完整结果。")
                        inspection["legality"]["reasons"] = [reason(
                            code, message,
                            "bridge_policy" if code in (
                                "QUERY_INFORMATION_SCOPE_UNAVAILABLE",
                                "QUERY_PEACE_PROVINCE_OFFER_CANDIDATE_ENUMERATION_UNAVAILABLE")
                            else "runtime_error")]
                    else:
                        inspection["family"] = "peace"
                        for key in (
                                "selected_war_id", "identity_scope",
                                "peace_context", "query_complete",
                                "native_offer_inspected", "pair_at_war",
                                "unique_shared_war", "offer_constructed",
                                "action_constructed", "participant_copy_verified",
                                "offer_identity_verified", "object_unchanged",
                                "cleanup_verified", "validity_called",
                                "native_validity", "common_gate_checked",
                                "common_action_gate", "initiation_gate_checked",
                                "initiation_gate", "native_wrapper_gate_checked",
                                "native_wrapper_gate", "wrapper_identity_verified",
                                "wrapper_payload_unchanged", "native_diagnostic_text",
                                "native_diagnostic_text_decoded",
                                "native_diagnostic_truncated", "diagnostics",
                                "native_evaluation", "native_war_context",
                                "native_payload", "native_provinces",
                                "full_rules_complete", "reasons_complete",
                                "submitted"):
                            if key in native:
                                inspection[key] = native[key]
                        provinces = native.get("native_provinces", {})
                        matched = provinces.get("parameters_matched") is True
                        selected_ids = provinces.get("selected_province_ids", [])
                        selected_beneficiary = provinces.get("selected_beneficiary")
                        actual_terms = []
                        if (isinstance(selected_ids, list) and selected_ids
                                and isinstance(selected_beneficiary, str)):
                            actual_terms = [{
                                "action_id": "cede_province",
                                "province_ids": list(selected_ids),
                                "beneficiary": selected_beneficiary,
                            }]
                        inspection["parameters"] = {
                            "requested": parameters,
                            "actual": {"peace_context": {
                                "war_id": native.get("selected_war_id"),
                                "direction": provinces.get(
                                    "direction", parameters.get(
                                        "peace_context", {}).get(
                                            "direction", "demand")),
                                "terms": actual_terms}},
                            "candidates": native.get("native_provinces", {}).get(
                                "candidates", []),
                            "complete": matched,
                        }
                        failures = []
                        province_reason = provinces.get("reason_code")
                        if province_reason is not None:
                            failures.append(reason(
                                province_reason,
                                "原生没有找到与请求匹配的割让省份选择。",
                                "native_rule", True))
                        gate_diagnostics = (
                            ("native_validity", "NATIVE_PEACE_PROVINCE_VALIDITY_FALSE",
                             "割让省份条款的原生合法性检查返回false。", "validity"),
                            ("common_action_gate", "NATIVE_PEACE_PROVINCE_COMMON_GATE_FALSE",
                             "割让省份条款的原生通用动作条件返回false。", "common_action_gate"),
                            ("initiation_gate", "NATIVE_PEACE_PROVINCE_INITIATION_GATE_FALSE",
                             "割让省份条款的原生发起条件返回false。", "initiation_gate"),
                        )
                        if not failures:
                            for field, code, text, diagnostic_key in gate_diagnostics:
                                if native.get(field) is False:
                                    item = reason(code, text, "native_rule")
                                    diagnostic = native.get("diagnostics", {}).get(
                                        diagnostic_key)
                                    if (isinstance(diagnostic, dict)
                                            and isinstance(diagnostic.get("text"), str)):
                                        item["text"] = diagnostic["text"]
                                    failures.append(item)
                        wrapper_state = ObserverSession._peace_wrapper_rule_state(native)
                        if wrapper_state == "failed":
                            failures.append(reason(
                                "NATIVE_PEACE_WRAPPER_GATE_FALSE",
                                "原生议和wrapper规则检查返回false。",
                                "native_rule", True))
                        if failures:
                            inspection["legality"] = {
                                "status": "unavailable", "reasons": failures,
                                "complete": False,
                            }
                        elif (wrapper_state == "verified"
                              and native.get("full_rules_complete") is True
                              and native.get("native_validity") is True
                              and native.get("common_action_gate") is True
                              and native.get("initiation_gate") is True
                              and matched is True):
                            inspection["legality"] = {
                                "status": "available",
                                "reasons": [reason(
                                    "NATIVE_PEACE_PROVINCE_OFFER_RULES_TRUE",
                                    "割让省份条款的议和wrapper、选中省份复制和原生条件均已通过。",
                                    "native_rule", True)],
                                "complete": True,
                            }
                        else:
                            inspection["legality"] = {
                                "status": "unknown",
                                "reasons": [reason(
                                    "NATIVE_PEACE_PROVINCE_RULES_INCOMPLETE",
                                    "割让省份的候选与选择结果已读取；完整条款规则、战争角色和原因集合仍未核验。",
                                    "native_rule")],
                                "complete": False,
                            }
                        inspection["native_rule_components"] = {
                            "validity_called": native.get("validity_called"),
                            "native_validity": native.get("native_validity"),
                            "common_gate_checked": native.get("common_gate_checked"),
                            "common_action_gate": native.get("common_action_gate"),
                            "initiation_gate_checked": native.get(
                                "initiation_gate_checked"),
                            "initiation_gate": native.get("initiation_gate"),
                            "native_wrapper_gate_checked": native.get(
                                "native_wrapper_gate_checked"),
                            "native_wrapper_gate": native.get("native_wrapper_gate"),
                            "wrapper_identity_verified": native.get(
                                "wrapper_identity_verified"),
                            "wrapper_payload_unchanged": native.get(
                                "wrapper_payload_unchanged"),
                            "native_provinces": provinces,
                            "full_rules_complete": native.get(
                                "full_rules_complete"),
                            "complete": False,
                        }
                        evaluation = native.get("native_evaluation")
                        if isinstance(evaluation, dict):
                            score_available = evaluation.get("score_available") is True
                            score_raw = evaluation.get("score_raw")
                            aggregate_score_available = (
                                evaluation.get("aggregate_score_available") is True)
                            aggregate_score_raw = evaluation.get("aggregate_score_raw")
                            factor_items = evaluation.get("items", [])
                            inspection["acceptance"].update({
                                "prediction_available": False,
                                "native_total": score_raw if score_available else None,
                                "unit": "unknown",
                                "scale_verified": False,
                                "predicted_response": "unknown",
                                "details_available": (
                                    evaluation.get("factors_available") is True
                                    or bool(factor_items)),
                                "details_complete": (
                                    evaluation.get("factors_complete") is True),
                                "items": list(factor_items),
                                "complete": False,
                            })
                            inspection["costs"]["native_evaluation"] = {
                                "aggregate_score_raw": aggregate_score_raw,
                                "aggregate_score_available": aggregate_score_available,
                                "unit": "unknown", "scale_verified": False,
                                "complete": False,
                            }
                    if isinstance(native, dict) and native.get("date_raw") is not None:
                        inspection["session"]["date_raw"] = native.get("date_raw")
                    return inspection
                if not alliance_query_scope:
                    inspection["interface_support"]["query"] = "partial_native_rules"
                if "error_code" in native:
                    inspection["legality"]["reasons"] = [reason(native["error_code"],
                        "本次原生查询没有取得完整结果，不能推定合法或非法。",
                        "bridge_policy" if native["error_code"] == "QUERY_INFORMATION_SCOPE_UNAVAILABLE" else "runtime_error")]
                else:
                    # +0x88 formats a description AND evaluates shared date,
                    # resource and action rules. Its bool is not UI visibility.
                    inspection["visibility"] = {"status": "unknown", "complete": False}
                    visibility = native.get("native_visibility")
                    selection_checked = native.get("ui_selection_checked") is True
                    if selection_checked and isinstance(visibility, bool):
                        inspection["visibility"] = {
                            "status": "visible" if visibility else "hidden", "complete": True}
                    if "common_action_gate" in native:
                        common_gate = native["common_action_gate"]
                    else:
                        common_gate = native.get("display_predicate")
                    if common_gate is False:
                        inspection["legality"]["status"] = "unavailable"
                        inspection["legality"]["reasons"] = [reason("NATIVE_COMMON_ACTION_GATE_FALSE",
                            "原生通用动作条件检查返回false，尚未恢复具体失败条件。", "native_rule")]
                    if native.get("validity_called") is True:
                        if native.get("native_validity") is False:
                            inspection["legality"]["status"] = "unavailable"
                            failure = reason("NATIVE_VALIDITY_FALSE",
                                f"{action.name_zh}的原生合法性检查返回false。", "native_rule")
                            if common_gate is True:
                                inspection["legality"]["reasons"] = [failure]
                            else:
                                inspection["legality"]["reasons"].append(failure)
                        elif native.get("native_validity") is True and common_gate is True:
                            inspection["legality"]["reasons"] = [reason("NATIVE_VALIDITY_TRUE_COVERAGE_INCOMPLETE",
                                "已调用原生动作条件；UI动作选择及全部原因仍未恢复。", "native_rule")]
                    if native.get("initiation_gate") is False:
                        inspection["legality"]["status"] = "unavailable"
                        inspection["legality"]["reasons"].append(reason("NATIVE_INITIATION_GATE_FALSE",
                            "原生发起时序或待处理请求检查返回false。", "native_rule"))
                    if selection_checked and visibility is False:
                        inspection["legality"]["status"] = "unavailable"
                        inspection["legality"]["reasons"].append(reason("NATIVE_ACTION_NOT_VISIBLE",
                            "原生外交列表在当前双方关系中不选择此动作变体。", "native_rule", True))
                    complete_rules = (native.get("full_rules_complete") is True
                        and selection_checked and isinstance(visibility, bool)
                        and native.get("ui_enabled_gate_checked") is True
                        and native.get("validity_called") is True
                        and all(isinstance(value, bool) for value in (
                            common_gate, native.get("native_validity"),
                            native.get("initiation_gate"), native.get("tooltip_gate"))))
                    if action_id in _INSULT_ACTIONS and native.get("family") == "insult":
                        # R33's native Insult query marks full_rules_complete
                        # after the UI-selection, common-action, initiation,
                        # and action-validity checks. It does not emit the
                        # generic tooltip_gate field. Keep the generic
                        # contract strict for other families while accepting
                        # this observed Insult schema; an explicitly emitted
                        # tooltip gate is still checked below.
                        insult_tooltip = native.get("tooltip_gate")
                        complete_rules = (native.get("full_rules_complete") is True
                            and selection_checked and isinstance(visibility, bool)
                            and native.get("ui_enabled_gate_checked") is True
                            and native.get("validity_called") is True
                            and all(isinstance(value, bool) for value in (
                                common_gate, native.get("native_validity"),
                                native.get("initiation_gate")))
                            and (insult_tooltip is None or isinstance(insult_tooltip, bool)))
                    if complete_rules:
                        tooltip_gate = native.get("tooltip_gate")
                        if (isinstance(tooltip_gate, bool)
                                and tooltip_gate != native["initiation_gate"]):
                            inspection["legality"]["status"] = "unknown"
                            inspection["legality"]["reasons"] = [reason("NATIVE_UI_GATE_INCONSISTENT",
                                "原生按钮条件与提示条件结果不一致，需要重新查询。", "runtime_error")]
                            complete_rules = False
                        elif all((visibility, common_gate, native["native_validity"], native["initiation_gate"])):
                            inspection["legality"]["status"] = "available"
                            inspection["legality"]["reasons"] = [reason("NATIVE_INITIATION_RULES_TRUE",
                                "原生外交列表选择、按钮发起条件及执行有效性检查均通过。", "native_rule", True)]
                        inspection["legality"]["complete"] = complete_rules
                    if native.get("diagnostic_readable") and native.get("native_diagnostic_text") is not None:
                        inspection["native_diagnostic"] = {
                            "text": native["native_diagnostic_text"],
                            "source": "native_rule", "complete": False,
                            "text_decoded": native.get("native_diagnostic_text_decoded") is True,
                            "text_encoding_verified": False,
                            "truncated": native.get("diagnostic_truncated") is True}
                    controlled = getattr(self.session, "record", {}).get("controlled_countries", ["FRA"])
                    if (native.get("diplomat_context_readable") is True
                            and isinstance(native.get("diplomat_required"), bool)
                            and ObserverSession._safe_int(native.get("available_diplomat_count"), 0, 256) is not None):
                        inspection["resources"] = {"diplomats": {
                            "native_requirement": native["diplomat_required"],
                            "available_count": native["available_diplomat_count"],
                            "availability_verified": True, "allocation_verified": False,
                            "source": "native_rule", "complete": False}}
                    acceptance_visible = (
                        action_id in _NEGOTIATED_INITIATION_ACTIONS
                        and applies and recipient not in controlled and recipient != "POR")
                    components = {
                        "ui_action_selection": visibility if selection_checked else None,
                        "ui_enabled_gate_verified": native.get("ui_enabled_gate_checked") is True,
                        "common_action_gate": common_gate, "initiation_gate": native.get("initiation_gate"),
                        "specific_validity_query_called": native.get("validity_called"),
                        "executor_validity": native.get("native_validity")
                            if native.get("validity_called") is True else None,
                        "complete": complete_rules}
                    if isinstance(native.get("ui_selection_checked"), bool):
                        components.update(
                            ui_selection_checked=native["ui_selection_checked"],
                            native_visibility=visibility,
                            ui_enabled_gate_checked=native.get("ui_enabled_gate_checked"),
                            tooltip_gate=native.get("tooltip_gate"),
                            full_rules_complete=complete_rules)
                    if acceptance_visible and native.get("score_available") is True and native.get("score_applicable") is True:
                        total = native.get("native_total_raw")
                        threshold = native.get("acceptance_threshold_raw")
                        if isinstance(total, int) and not isinstance(total, bool) \
                                and isinstance(threshold, int) and not isinstance(threshold, bool):
                            components["acceptance_gate"] = total >= threshold
                    inspection["native_rule_components"] = components
                    if acceptance_visible:
                        raw_items = native.get("reason_items", [])
                        items = self._public_acceptance_items(
                            raw_items, _NATIVE_REASON_METADATA_CAPABILITY in self._installation_capabilities())
                        native_items_truncated = (native.get("reason_items_truncated") is True
                                                  or isinstance(raw_items, (list, tuple))
                                                  and len(raw_items) > _MAX_REASON_ITEMS)
                        details_available = any(isinstance(item.get("name"), str)
                                                for item in items)
                        inspection["acceptance"].update(
                            reason_count=native.get("reason_count"),
                            items=items,
                            items_truncated=native_items_truncated,
                            details_available=details_available,
                            complete=False)
                    if (acceptance_visible and native.get("score_available") is True
                            and native.get("score_applicable") is True
                            and isinstance(native.get("native_total_raw"), int)
                            and not isinstance(native.get("native_total_raw"), bool)
                            and isinstance(native.get("acceptance_threshold_raw"), int)
                            and not isinstance(native.get("acceptance_threshold_raw"), bool)):
                        inspection["acceptance"].update(prediction_available=True, native_total=native["native_total_raw"],
                            unit="unknown", scale_verified=False, predicted_response="unknown",
                            native_threshold=native["acceptance_threshold_raw"], complete=False)
                    if (acceptance_visible and native.get("acceptance_predicate_available") is True
                            and isinstance(native.get("native_would_accept"), bool)):
                        components["acceptance_gate"] = native["native_would_accept"]
                        inspection["acceptance"].update(
                            prediction_available=True,
                            predicted_response="accept" if native["native_would_accept"] else "reject",
                            prediction_basis="native_current_acceptance_check",
                            native_would_accept=native["native_would_accept"],
                            actual_response_verified=False, complete=False)
                    if guarantee_query_scope:
                        relationship_state = native.get("relationship_state")
                        if (isinstance(relationship_state, dict)
                                and isinstance(relationship_state.get("guarantee_active"), bool)
                                and relationship_state.get("complete") is True):
                            inspection["relationship_state"] = {
                                "guarantee_active": relationship_state["guarantee_active"],
                                "complete": True,
                            }
                        else:
                            inspection["relationship_state"] = {
                                "guarantee_active": None,
                                "complete": False,
                            }
                    if support_independence_query_scope:
                        relationship_state = native.get("relationship_state")
                        if (isinstance(relationship_state, dict)
                                and isinstance(relationship_state.get(
                                    "support_independence_active"), bool)
                                and relationship_state.get("complete") is True):
                            inspection["relationship_state"] = {
                                "support_independence_active": relationship_state[
                                    "support_independence_active"],
                                "complete": True,
                            }
                        else:
                            inspection["relationship_state"] = {
                                "support_independence_active": None,
                                "complete": False,
                            }
                    if military_access_query_scope:
                        relationship_state = native.get("relationship_state")
                        if (isinstance(relationship_state, dict)
                                and isinstance(relationship_state.get(
                                    "military_access_active"), bool)
                                and relationship_state.get("complete") is True):
                            inspection["relationship_state"] = {
                                "military_access_active": relationship_state[
                                    "military_access_active"],
                                "complete": True,
                            }
                        else:
                            inspection["relationship_state"] = {
                                "military_access_active": None,
                                "complete": False,
                            }
                    if vassalization_query_scope:
                        for key in (
                                "family", "vassal_active", "vassal_state_verified",
                                "actor_is_overlord", "actor_is_subject", "subject_type",
                                "prestige_raw", "cancel_prestige_delta_raw",
                                "cancel_prestige_effect_allowed", "prestige_scale",
                                "cancel_prestige_cost_verified"):
                            if key in native:
                                inspection[key] = native[key]
                        relationship_state = native.get("relationship_state")
                        if (isinstance(relationship_state, dict)
                                and isinstance(relationship_state.get("vassal_active"), bool)
                                and relationship_state.get("complete") is True):
                            inspection["relationship_state"] = {
                                "vassal_active": relationship_state["vassal_active"],
                                "complete": True,
                            }
                        else:
                            inspection["relationship_state"] = {
                                "vassal_active": None,
                                "complete": False,
                            }
                        if action_id == "cancel_vassalization":
                            inspection["costs"] = ObserverSession._public_vassalization_costs(
                                action_id, native)
                            inspection["acceptance"] = {
                                "applicability": "not_applicable",
                                "prediction_available": False,
                                "native_total": None,
                                "unit": None,
                                "scale_verified": False,
                                "predicted_response": "not_applicable",
                                "details_available": False,
                                "items": [],
                                "complete": True,
                            }
                    if declare_war_query_scope:
                        # QUERY1 observes the default object. QUERY3 echoes
                        # the requested CB/province/beneficiary and may make
                        # the selected native rule result complete.
                        for key in (
                                "family", "initiation_gate_checked",
                                "parameter_context_complete",
                                "native_default_payload",
                                "candidate_context_complete", "candidates",
                                "candidate_enumeration_called",
                                "candidate_enumeration_complete",
                                "candidate_native_count",
                                "candidate_capture_truncated",
                                "candidate_cleanup_verified",
                                "candidate_enumeration",
                                "full_rules_complete", "submitted",
                                "selection_requested", "selection_matched",
                                "selection_match_count", "requested_casus_belli",
                                "requested_province_id", "requested_beneficiary"):
                            if key in native:
                                inspection[key] = native[key]
                        selected_parameters = bool(parameters)
                        selection_matched = (
                            selected_parameters
                            and native.get("selection_matched") is True)
                        actual_parameters = None
                        if selection_matched:
                            actual_parameters = {
                                "casus_belli": native.get("requested_casus_belli"),
                                "war_goal": {
                                    "province_id": native.get("requested_province_id"),
                                    "beneficiary": native.get("requested_beneficiary"),
                                },
                                "call_allies": [],
                            }
                        inspection["parameters"] = {
                            "requested": parameters,
                            "actual": actual_parameters,
                            "candidates": native.get("candidates", []),
                            "complete": native.get(
                                "parameter_context_complete") is True,
                        }
                        if isinstance(native.get("costs"), dict):
                            if (selected_parameters
                                    and native.get("selection_matched") is not True):
                                inspection["costs"] = {
                                    "status": "unknown",
                                    "items": [],
                                    "complete": False,
                                    "context": "requested_selection_unavailable",
                                }
                            else:
                                inspection["costs"] = {
                                    **native["costs"],
                                    "context": ("selected_parameters"
                                                 if selected_parameters
                                                 else native["costs"].get(
                                                     "context", "default_parameters_unselected")),
                                }
                        inspection["native_rule_components"] = native.get(
                            "native_rule_components", {
                                "ui_selection_checked": native.get(
                                    "ui_selection_checked"),
                                "native_visibility": native.get(
                                    "native_visibility"),
                                "ui_enabled_gate_checked": native.get(
                                    "ui_enabled_gate_checked"),
                                "common_action_gate": native.get(
                                    "common_action_gate"),
                                "validity_called": native.get("validity_called"),
                                "native_validity": native.get("native_validity"),
                                "initiation_gate_checked": native.get(
                                    "initiation_gate_checked"),
                                "initiation_gate": native.get("initiation_gate"),
                                "parameter_context_complete": native.get(
                                    "parameter_context_complete"),
                                "native_default_payload": native.get(
                                    "native_default_payload"),
                                "candidate_context_complete": native.get(
                                    "candidate_context_complete"),
                                "full_rules_complete": native.get(
                                    "full_rules_complete"),
                                "complete": False,
                            })
                        if isinstance(inspection["native_rule_components"], dict):
                            inspection["native_rule_components"].update({
                                "selection_requested": native.get("selection_requested"),
                                "selection_matched": native.get("selection_matched"),
                                "selection_match_count": native.get(
                                    "selection_match_count"),
                            })
                        inspection["acceptance"] = {
                            "applicability": "not_applicable",
                            "prediction_available": False,
                            "native_total": None,
                            "unit": None,
                            "scale_verified": False,
                            "predicted_response": "not_applicable",
                            "details_available": False,
                            "items": [],
                            "complete": True,
                        }
                        if not selected_parameters:
                            inspection["legality"] = {
                                "status": "unknown",
                                "reasons": [reason(
                                    "NATIVE_DECLARE_WAR_PARAMETER_CONTEXT_INCOMPLETE",
                                    "原生宣战默认对象查询已取得当前界面与规则布尔值，但尚未选择宣战理由、战争目标和召集盟友参数。",
                                    "native_rule")],
                                "complete": False,
                            }
                        elif native.get("selection_matched") is not True:
                            inspection["legality"] = {
                                "status": "unavailable",
                                "reasons": [reason(
                                    "NATIVE_DECLARE_WAR_SELECTION_NOT_FOUND",
                                    "原生查询没有找到与请求的宣战理由、战争目标和受益方完全匹配的候选项。",
                                    "native_rule", True)],
                                "complete": False,
                            }
                        else:
                            selected_rules = all(
                                native.get(field) is True for field in (
                                    "native_visibility", "common_action_gate",
                                    "native_validity", "initiation_gate",
                                    "parameter_context_complete",
                                    "candidate_context_complete",
                                    "full_rules_complete"))
                            inspection["legality"] = {
                                "status": "available" if selected_rules else "unavailable",
                                "reasons": [reason(
                                    "NATIVE_DECLARE_WAR_SELECTED_RULES_TRUE"
                                    if selected_rules
                                    else "NATIVE_DECLARE_WAR_SELECTED_RULE_FALSE",
                                    "原生查询已按请求参数匹配宣战候选，并完成当前选定对象的规则检查。"
                                    if selected_rules else
                                    "原生查询已匹配请求参数，但当前选定宣战对象的一个或多个原生规则检查返回false。",
                                    "native_rule", selected_rules)],
                                "complete": selected_rules,
                            }
                    if insult_query_scope:
                        native_parameters = native.get("parameters")
                        if not isinstance(native_parameters, dict):
                            native_parameters = {}
                        for key in (
                                "family", "insult_id", "insult_parameter_selected",
                                "insult_state_verified", "insult_active",
                                "opinion_modifier_raw", "actor_prestige_raw",
                                "prestige_cost_raw", "candidates_available",
                                "candidate_count", "candidates_complete"):
                            if key in native:
                                inspection[key] = native[key]
                        inspection["parameters"] = {
                            "requested": parameters,
                            "actual": native_parameters.get("actual"),
                            "candidates": native_parameters.get("candidates"),
                            "complete": native_parameters.get("complete") is True,
                        }
                        inspection["acceptance"] = {
                            "applicability": "not_applicable",
                            "prediction_available": False,
                            "native_total": None,
                            "unit": None,
                            "scale_verified": False,
                            "predicted_response": "not_applicable",
                            "details_available": False,
                            "items": [],
                            "complete": True,
                        }
                        inspection["costs"] = ObserverSession._public_insult_costs(action_id, native)
                        if (action_id == "scornful_insult"
                                and "insult_id" not in parameters):
                            inspection["legality"] = {
                                "status": "unknown",
                                "reasons": [reason(
                                    "INSULT_PARAMETER_NOT_SELECTED",
                                    "轻蔑侮辱尚未选择原生候选编号；当前查询只返回候选，不判断具体动作合法性。",
                                    "bridge_policy")],
                                "complete": False,
                            }
                    if rival_query_scope:
                        # Rival has no counterparty response.  The native
                        # command predicate and relation membership are
                        # useful evidence, while the missing UI/full-rule
                        # proof keeps a true predicate at ``unknown``.
                        for key in (
                                "family", "rules_schema",
                                "native_command_validity_called",
                                "native_command_validity", "rival_state_verified",
                                "rival_active", "rival_since_date_raw", "rival_count",
                                "max_rivals", "diplomatic_power_raw", "at_war",
                                "candidate_eligible", "target_exists", "ui_war_allowed",
                                "cost_query_called", "diplomatic_power_cost_raw",
                                "candidate_eligibility_available", "full_rules_complete",
                                "native_action_available",
                                "submitted"):
                            if key in native:
                                inspection[key] = native[key]
                        relationship_state = native.get("relationship_state")
                        if (isinstance(relationship_state, dict)
                                and isinstance(relationship_state.get("rival_active"), bool)
                                and relationship_state.get("complete") is True):
                            inspection["relationship_state"] = {
                                "rival_active": relationship_state["rival_active"],
                                "rival_since_date_raw": relationship_state.get(
                                    "rival_since_date_raw"),
                                "complete": True,
                            }
                        else:
                            inspection["relationship_state"] = {
                                "rival_active": None,
                                "rival_since_date_raw": None,
                                "complete": False,
                            }
                        if isinstance(native.get("resources"), dict):
                            inspection["resources"] = native["resources"]
                        if isinstance(native.get("costs"), dict):
                            inspection["costs"] = native["costs"]
                        inspection["at_war"] = native.get("at_war")
                        inspection["acceptance"] = {
                            "applicability": "not_applicable",
                            "prediction_available": False,
                            "native_total": None,
                            "unit": None,
                            "scale_verified": False,
                            "predicted_response": "not_applicable",
                            "details_available": False,
                            "items": [],
                            "complete": True,
                        }
                        native_validity = native.get("native_command_validity")
                        active = native.get("rival_active")
                        rules_schema = native.get("rules_schema", 1)
                        candidate_available = native.get(
                            "candidate_eligibility_available")
                        failures = []
                        candidate_rules_incomplete = False

                        def add_failure(code: str, text: str,
                                        source: str = "native_rule") -> None:
                            if not any(item.get("code") == code for item in failures):
                                failures.append(reason(code, text, source))

                        if native.get("native_command_validity_called") is not True:
                            add_failure(
                                "NATIVE_RIVAL_VALIDITY_NOT_CALLED",
                                "原生宿敌条件检查没有完成，不能判断当前操作。",
                                "runtime_error")
                        elif native_validity is False:
                            add_failure(
                                "NATIVE_RIVAL_COMMAND_VALIDITY_FALSE",
                                "原生宿敌操作条件检查返回false。",
                                "native_rule")

                        # These fields are independent native observations.  A
                        # false command predicate must not hide a more useful
                        # target, candidate, war-gate, membership, or capacity
                        # reason that the same query proved.
                        if (action_id == "set_rival" and rules_schema == 2
                                and candidate_available is True
                                and native.get("target_exists") is False):
                            add_failure(
                                "NATIVE_RIVAL_TARGET_NOT_FOUND",
                                "原生候选检查显示目标国家不存在或已失效。",
                                "native_rule")
                        if (action_id == "set_rival" and rules_schema == 2
                                and candidate_available is True
                                and native.get("candidate_eligible") is False):
                            add_failure(
                                "NATIVE_RIVAL_CANDIDATE_INELIGIBLE",
                                "原生候选检查显示当前目标不符合宣布宿敌条件。",
                                "native_rule")
                        if (action_id == "set_rival" and rules_schema == 2
                                and candidate_available is True
                                and native.get("ui_war_allowed") is False):
                            add_failure(
                                "NATIVE_RIVAL_WAR_GATE_FALSE",
                                "原生UI战争条件检查禁止当前宣布宿敌操作。",
                                "native_rule")
                        if (action_id == "set_rival"
                                and isinstance(native.get("rival_count"), int)
                                and isinstance(native.get("max_rivals"), int)
                                and native.get("rival_count") >= native.get("max_rivals")):
                            add_failure(
                                "NATIVE_RIVAL_SLOTS_FULL",
                                "原生宿敌数量已达到上限，当前没有可用宿敌名额。",
                                "native_rule")
                        if action_id == "set_rival" and active is True:
                            add_failure(
                                "NATIVE_RIVAL_ALREADY_ACTIVE",
                                "原生关系状态显示目标已经是宿敌。",
                                "native_rule")
                        if action_id == "remove_rival" and active is False:
                            add_failure(
                                "NATIVE_RIVAL_MEMBERSHIP_FALSE",
                                "原生关系状态显示目标当前不是宿敌。",
                                "native_rule")

                        diagnostic = native.get("native_diagnostic_text")
                        if native_validity is False and isinstance(diagnostic, str) and diagnostic:
                            add_failure(
                                "NATIVE_RIVAL_DIAGNOSTIC",
                                diagnostic,
                                "native_rule")

                        if (action_id == "set_rival" and rules_schema == 2
                                and candidate_available is not True):
                            candidate_rules_incomplete = True
                        if failures:
                            inspection["legality"] = {
                                "status": "unavailable",
                                "reasons": failures,
                                "complete": False,
                            }
                        elif candidate_rules_incomplete:
                            inspection["legality"] = {
                                "status": "unknown",
                                "reasons": [reason(
                                    "NATIVE_RIVAL_CANDIDATE_RULE_UNAVAILABLE",
                                    "原生候选条件查询尚未完成，不能判断宣布宿敌是否合法。",
                                    "native_rule")],
                                "complete": False,
                            }
                        elif rules_schema == 3:
                            full_rules = native.get("full_rules_complete")
                            action_available = native.get("native_action_available")
                            if full_rules is not True:
                                inspection["legality"] = {
                                    "status": "unknown",
                                    "reasons": [reason(
                                        "NATIVE_RIVAL_FULL_RULES_INCOMPLETE",
                                        "原生宿敌查询尚未完成状态、命令谓词及目标条件的联合验证。",
                                        "native_rule")],
                                    "complete": False,
                                }
                            elif action_available is False:
                                if native.get("at_war") is True:
                                    add_failure(
                                        "NATIVE_RIVAL_WAR_GATE_FALSE",
                                        "原生战争条件禁止当前宿敌操作。", "native_rule")
                                if action_id == "set_rival":
                                    if native.get("target_exists") is False:
                                        add_failure(
                                            "NATIVE_RIVAL_TARGET_NOT_FOUND",
                                            "原生目标国家检查返回false。", "native_rule")
                                    if native.get("candidate_eligible") is False:
                                        add_failure(
                                            "NATIVE_RIVAL_CANDIDATE_INELIGIBLE",
                                            "原生宿敌候选谓词返回false。", "native_rule")
                                    if native.get("ui_war_allowed") is False:
                                        add_failure(
                                            "NATIVE_RIVAL_WAR_GATE_FALSE",
                                            "原生UI战争条件检查禁止当前宣布宿敌操作。",
                                            "native_rule")
                                    if active is True:
                                        add_failure(
                                            "NATIVE_RIVAL_ALREADY_ACTIVE",
                                            "原生关系状态显示目标已经是宿敌。", "native_rule")
                                    if (isinstance(native.get("rival_count"), int)
                                            and isinstance(native.get("max_rivals"), int)
                                            and native["rival_count"] >= native["max_rivals"]):
                                        add_failure(
                                            "NATIVE_RIVAL_SLOTS_FULL",
                                            "原生宿敌数量已达到上限。", "native_rule")
                                elif active is False:
                                    add_failure(
                                        "NATIVE_RIVAL_MEMBERSHIP_FALSE",
                                        "原生关系状态显示目标当前不是宿敌。", "native_rule")
                                if (action_id == "remove_rival"
                                        and native.get("cost_query_called") is not True):
                                    add_failure(
                                        "NATIVE_RIVAL_COST_RULE_UNAVAILABLE",
                                        "原生撤销宿敌费用检查尚未完成。", "runtime_error")
                                elif (action_id == "remove_rival"
                                      and isinstance(native.get("diplomatic_power_cost_raw"), int)
                                      and isinstance(native.get("diplomatic_power_raw"), int)
                                      and native["diplomatic_power_cost_raw"] > native["diplomatic_power_raw"]):
                                    add_failure(
                                        "NATIVE_RIVAL_COST_UNAFFORDABLE",
                                        "原生外交点数不足以支付撤销宿敌费用。", "native_rule")
                                inspection["legality"] = {
                                    "status": "unavailable",
                                    "reasons": failures or [reason(
                                        "NATIVE_RIVAL_ACTION_UNAVAILABLE",
                                        "原生宿敌动作条件返回false。", "native_rule")],
                                    "complete": False,
                                }
                            elif action_available is True:
                                inspection["legality"] = {
                                    "status": "available",
                                    "reasons": [reason(
                                        "NATIVE_RIVAL_ACTION_AVAILABLE",
                                        "原生宿敌状态、命令谓词和目标条件均已验证通过。",
                                        "native_rule", True)],
                                    "complete": True,
                                }
                            else:
                                inspection["legality"] = {
                                    "status": "unknown",
                                    "reasons": [reason(
                                        "NATIVE_RIVAL_ACTION_AVAILABILITY_UNKNOWN",
                                        "原生宿敌动作可用性字段缺失，不能执行。",
                                        "runtime_error")],
                                    "complete": False,
                                }
                        elif rules_schema == 2:
                            inspection["legality"] = {
                                "status": "unknown",
                                "reasons": [reason(
                                    "NATIVE_RIVAL_EXECUTION_PREFLIGHT_INCOMPLETE",
                                    "原生宿敌条件、关系状态和候选谓词已读取；完整费用与执行前规则验收仍待补齐。",
                                    "native_rule")],
                                "complete": False,
                            }
                        else:
                            inspection["legality"] = {
                                "status": "unknown",
                                "reasons": [reason(
                                    "NATIVE_RIVAL_UI_RULES_INCOMPLETE",
                                    "原生宿敌条件与关系状态已读取，但完整UI候选规则尚未恢复。",
                                    "native_rule")],
                                "complete": False,
                            }
                        inspection["native_rule_components"] = native.get(
                            "native_rule_components", {
                                "specific_validity_query_called": native.get(
                                    "native_command_validity_called"),
                                "executor_validity": native_validity,
                                "rival_state_verified": native.get(
                                    "rival_state_verified"),
                                "candidate_eligibility_available": native.get(
                                    "candidate_eligibility_available"),
                                "full_rules_complete": native.get(
                                    "full_rules_complete", False),
                                "native_action_available": native.get(
                                    "native_action_available"),
                                "complete": False,
                            })
                    inspection["session"]["date_raw"] = native.get("date_raw")
        return inspection

    def execute_diplomatic_action(self, request_id: str, action_id: str, actor: str, recipient: str,
                                 phase: str = "initiate", parameters: dict | None = None) -> dict:
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id):
            raise ValueError("INVALID_REQUEST_ID")
        parameters = {} if parameters is None else parameters
        if action_id in _PEACE_EXECUTION_ACTIONS:
            try:
                parameters = normalize_peace_execution_parameters(
                    action_id, actor, recipient, phase, parameters)
            except ValueError as exc:
                # Preserve the long-standing public error for a missing or
                # incomplete Peace context.  The dedicated normalizer keeps
                # finer-grained PEACE_EXECUTION_* codes for direct callers;
                # this facade historically exposed PEACE_CONTEXT_REQUIRED.
                if exc.args and exc.args[0] in {
                        "PEACE_EXECUTION_PARAMETERS_REQUIRED",
                        "PEACE_EXECUTION_CONTEXT_INVALID"}:
                    raise ValueError("PEACE_CONTEXT_REQUIRED") from None
                raise
        else:
            self._validate(action_id, actor, recipient, phase, parameters)
        payload = {"action_id": action_id, "actor": actor, "recipient": recipient,
                   "phase": phase, "parameters": parameters}
        try:
            record = self.journal.register(request_id, payload)
        except RequestConflictError:
            return {"request_id": request_id, "submitted": False, "status": "conflict",
                    "reason": reason("REQUEST_ID_PAYLOAD_CONFLICT", "此请求编号已绑定另一组动作或参数。", "bridge_policy", True)}
        except ContextMismatchError:
            return {"request_id": request_id, "submitted": False, "status": "invalidated",
                    "reason": reason("REQUEST_ID_SESSION_CONFLICT", "此编号已属于另一游戏会话，不能在重载后自动重新提交。", "bridge_policy", True)}
        if record.status != "received":
            result = self.get_diplomatic_result(request_id)
            result.update({"idempotent": True})
            return result
        # Re-read current identity and frame health at execution time. No query
        # grants authority, and unsupported paths never reach native transport.
        inspection = self.inspect_diplomatic_action(
            action_id, actor, recipient, phase, parameters,
            _execution_request=action_id in _PEACE_EXECUTION_ACTIONS)
        native_capabilities = self._installation_capabilities()
        native_capability = _NATIVE_OFFER_SUBMISSION_CAPABILITY in native_capabilities
        royal_native_capability = _NATIVE_ROYAL_MARRIAGE_SUBMISSION_CAPABILITY in native_capabilities
        improve_native_capability = _NATIVE_IMPROVE_RELATIONS_SUBMISSION_CAPABILITY in native_capabilities
        spy_network_native_capability = _NATIVE_SPY_NETWORK_SUBMISSION_CAPABILITY in native_capabilities
        guarantee_native_capability = _NATIVE_GUARANTEE_SUBMISSION_CAPABILITY in native_capabilities
        support_independence_native_capability = (
            _NATIVE_SUPPORT_INDEPENDENCE_SUBMISSION_CAPABILITY in native_capabilities)
        military_access_native_capability = (
            _NATIVE_MILITARY_ACCESS_SUBMISSION_CAPABILITY in native_capabilities)
        insult_native_capability = (
            _NATIVE_INSULT_SUBMISSION_CAPABILITY in native_capabilities)
        rival_native_capability = (
            _NATIVE_RIVAL_SUBMISSION_CAPABILITY in native_capabilities)
        vassalization_native_capability = (
            _NATIVE_VASSALIZATION_SUBMISSION_CAPABILITY in native_capabilities)
        declare_war_native_capability = (
            _NATIVE_DECLARE_WAR_SUBMISSION_CAPABILITY in native_capabilities)
        peace_native_capability = (
            _NATIVE_PEACE_SUBMISSION_CAPABILITY in native_capabilities)
        inbound_response_capability_name = _inbound_response_capability(action_id)
        inbound_response_capability = inbound_response_capability_name in native_capabilities
        inbound_response_phase = (
            action_id in ("offer_alliance", "offer_royal_marriage", "support_independence",
                          "ask_military_access", "offer_vassalization", "peace_offer")
            and phase in ("accept", "reject"))
        if inbound_response_phase and inbound_response_capability:
            session_info = inspection.get("session", {}) if isinstance(inspection, dict) else {}
            legality = inspection.get("legality", {}) if isinstance(inspection, dict) else {}
            if session_info.get("status") != "ready":
                result = self._execution_result(
                    inspection, "NATIVE_SESSION_UNREADY",
                    "执行前原生会话未通过最新健康检查，未向游戏提交。")
                self.journal.mark_invalidated(request_id, result,
                                              event_id="bridge-inbound-execution-session-unready")
                return self.get_diplomatic_result(request_id)
            if (legality.get("status") != "available"
                    or inspection.get("authorization", {}).get("status") != "available"):
                codes = [item.get("code") for item in legality.get("reasons", [])
                         if isinstance(item, dict)]
                if inspection.get("proposal_status") == "invalidated" or "INVALID_PROPOSAL_REFERENCE" in codes:
                    code = "NATIVE_INBOUND_PROPOSAL_INVALIDATED"
                    text = "原生复查显示入站提议已失效或引用不匹配，未向游戏提交。"
                else:
                    code = "NATIVE_INBOUND_RULES_UNKNOWN"
                    text = "未取得完整原生入站响应规则，未向游戏提交。"
                result = self._execution_result(inspection, code, text)
                self.journal.mark_invalidated(request_id, result,
                                              event_id="bridge-inbound-execution-not-authorized")
                return self.get_diplomatic_result(request_id)
            return self._execute_native_inbound_response(
                request_id, inspection, actor, recipient, phase)
        dissolve_scope = (action_id == "dissolve_alliance" and actor == "FRA" and phase == "initiate"
                          and _NATIVE_DISSOLVE_SUBMISSION_CAPABILITY in native_capabilities)
        royal_scope = self._native_royal_scope(action_id, actor, phase) and royal_native_capability
        improve_scope = self._native_improve_scope(action_id, actor, phase) and improve_native_capability
        spy_network_scope = (self._native_spy_network_scope(action_id, actor, phase)
                             and spy_network_native_capability)
        guarantee_scope = (self._native_guarantee_scope(action_id, actor, phase)
                           and guarantee_native_capability)
        support_independence_scope = (
            self._native_support_independence_scope(action_id, actor, phase)
            and support_independence_native_capability)
        military_access_scope = (
            self._native_military_access_scope(action_id, actor, phase)
            and military_access_native_capability)
        insult_scope = (
            self._native_insult_scope(action_id, actor, phase)
            and insult_native_capability)
        rival_scope = (
            self._native_rival_scope(action_id, actor, phase)
            and rival_native_capability)
        vassalization_scope = (
            self._native_vassalization_scope(action_id, actor, phase)
            and vassalization_native_capability)
        declare_war_scope = (
            self._native_declare_war_scope(action_id, actor, phase)
            and declare_war_native_capability)
        peace_scope = (
            action_id in _PEACE_EXECUTION_ACTIONS and actor == "FRA"
            and phase == "initiate" and peace_native_capability)
        if ((self._native_offer_scope(action_id, actor, phase) and native_capability)
                or dissolve_scope or royal_scope or improve_scope or spy_network_scope
                or guarantee_scope or support_independence_scope or military_access_scope
                or insult_scope or rival_scope or vassalization_scope
                or declare_war_scope or peace_scope):
            session_info = inspection.get("session", {}) if isinstance(inspection, dict) else {}
            legality = inspection.get("legality", {}) if isinstance(inspection, dict) else {}
            if session_info.get("status") != "ready":
                result = self._execution_result(
                    inspection, "NATIVE_SESSION_UNREADY",
                    "执行前原生会话未通过最新健康检查，未向游戏提交。")
                self.journal.mark_invalidated(request_id, result,
                                              event_id="bridge-execution-session-unready")
                return self.get_diplomatic_result(request_id)
            if (legality.get("status") != "available"
                    and not (action_id == "scornful_insult"
                             and parameters.get("insult_id") is None)):
                result = self._execution_result(
                    inspection, "NATIVE_LEGALITY_UNAVAILABLE",
                    "执行前最新原生合法性不是available，未向游戏提交。")
                self.journal.mark_invalidated(request_id, result,
                                              event_id="bridge-execution-legality-unavailable")
                return self.get_diplomatic_result(request_id)
            if declare_war_scope:
                return self._execute_native_declare_war(
                    request_id, inspection, actor, recipient, phase)
            if peace_scope:
                return self._execute_native_peace(
                    request_id, inspection, actor, recipient, phase, action_id)
            if rival_scope:
                return self._execute_native_rival(
                    request_id, inspection, actor, recipient, phase, action_id)
            return self._execute_native_offer(request_id, inspection, actor, recipient, phase, action_id)
        result = {"submitted": False, "game_outcome": "unknown", "inspection": inspection,
                  "reason": reason("EXECUTION_ADAPTER_UNIMPLEMENTED", "该动作未建立经过验收的原生执行适配，未向游戏提交。", "bridge_policy", True)}
        self.journal.mark_invalidated(request_id, result, event_id="bridge-execution-unimplemented")
        return self.get_diplomatic_result(request_id)

    def get_diplomatic_result(self, request_id: str) -> dict:
        try:
            record = self.journal.lookup_request(request_id)
        except UnknownRequestError:
            return {"request_id": request_id, "status": "unknown", "submitted": False,
                    "game_outcome": "unknown", "reason": reason("REQUEST_NOT_FOUND", "当前实验会话没有此请求的记录。", "runtime_error")}
        except AmbiguousRequestError:
            return {"request_id": request_id, "status": "unknown", "submitted": False,
                    "game_outcome": "unknown", "reason": reason("REQUEST_ID_AMBIGUOUS", "历史命名空间存在重复编号，无法唯一关联结果。", "runtime_error")}
        self._persist_native_response(record)
        try:
            record = self.journal.lookup_request(request_id)
        except (UnknownRequestError, AmbiguousRequestError):
            return {"request_id": request_id, "status": "unknown", "submitted": False,
                    "game_outcome": "unknown", "reason": reason("REQUEST_NOT_FOUND", "当前实验会话没有此请求的记录。", "runtime_error")}
        evidence = self.journal.list_evidence_for_record(record)
        # Claim tokens, process IDs, paths and native debug payloads are private.
        return {"contract_version": 1, "request_id": request_id, "action_id": record.payload["action_id"],
                "status": record.status, "submitted": record.submitted_at is not None,
                "game_outcome": record.status if record.status in ("accepted", "rejected", "executed") else "unknown",
                "result": record.result, "updated_at": record.updated_at,
                "evidence": [{"type": event.evidence_type, "layer": event.arrival_layer,
                              "sha256": event.content_sha256} for event in evidence]}
