"""Stable bridge semantics; identification and runtime support are separate.

These names do not assert a native class, vtable or rule implementation. Native
identifiers are populated only from independently reviewed evidence.
"""
from __future__ import annotations

from dataclasses import dataclass

from .peace_country import (
    COUNTRY_TERM_ACTIONS,
    PEACE_TERM_CANONICAL_ORDER,
)


@dataclass(frozen=True)
class Action:
    id: str
    name_zh: str
    name_en: str
    category: str
    response: bool
    parameters: tuple[str, ...] = ()
    native_identifier: str | None = None
    identification_source: str | None = None

    def describe(self) -> dict:
        # ``peace_offer`` is an aggregate inbound proposal.  The controlled
        # country only chooses accept/reject for an already observed proposal;
        # it is kept outside ``ACTIONS`` so inbound proposals remain separate
        # from the diplomatic-action and peace-term catalog.
        phases = (['accept', 'reject'] if self.id == 'peace_offer'
                  else ["initiate", "accept", "reject", "withdraw"]
                  if self.response else ["initiate"])
        parameter_definitions = {
            key: {"status": "context_required"} for key in self.parameters}
        inspection_parameter_forms = None
        if self.id == "peace_offer":
            parameter_definitions = {
                "proposal_id": {
                    "status": "required",
                    "type": "opaque_proposal_id",
                    "path": "parameters.proposal_id",
                },
            }
        elif self.id == "declare_war":
            parameter_definitions = {
                "casus_belli": {
                    "status": "required_for_selected",
                    "type": "string", "path": "parameters.casus_belli",
                },
                "war_goal": {
                    "status": "required_for_selected",
                    "type": "object", "path": "parameters.war_goal",
                },
                "war_goal.province_id": {
                    "status": "required_for_selected",
                    "type": "int32", "allow_sentinel": -1,
                    "path": "parameters.war_goal.province_id",
                },
                "war_goal.beneficiary": {
                    "status": "required_for_selected",
                    "type": "country_tag_or_sentinel",
                    "path": "parameters.war_goal.beneficiary",
                },
                "call_allies": {
                    "status": "required_for_selected",
                    "type": "array", "item_type": "country_tag",
                    "min_length": 0, "max_length": 16,
                    "unique_items": True, "sorted": True,
                    "path": "parameters.call_allies",
                },
                "promise_land_to": {
                    "status": "optional_for_selected",
                    "type": "array", "item_type": "country_tag",
                    "min_length": 0, "max_length": 16,
                    "unique_items": True, "sorted": True,
                    "subset_of": "parameters.call_allies",
                    "path": "parameters.promise_land_to",
                },
                "co_belligerents": {
                    "status": "optional_for_selected",
                    "type": "array", "item_type": "country_tag",
                    "min_length": 0, "max_length": 16,
                    "unique_items": True, "sorted": True,
                    "disjoint_from": ["parameters.call_allies",
                                      "parameters.promise_land_to"],
                    "path": "parameters.co_belligerents",
                },
            }
        elif self.id == "white_peace":
            parameter_definitions = {
                "peace_context": {
                    "status": "context_required",
                    "type": "object",
                    "path": "peace_context",
                },
                "peace_context.war_id": {
                    "status": "required_for_selected",
                    "type": "war_id",
                    "path": "peace_context.war_id",
                },
                "peace_context.terms": {
                    "status": "required_for_selected",
                    "type": "array",
                    "exact_length": 0,
                    "path": "peace_context.terms",
                },
                "peace_context.direction": {
                    "status": "optional_for_selected",
                    "type": "string",
                    "enum": ["demand", "offer"],
                    "default": "demand",
                    "path": "peace_context.direction",
                },
            }
            inspection_parameter_forms = [
                {
                    "name": "discovery",
                    "parameters": {},
                    "purpose": "发现当前会话中双方共同战争。",
                },
                {
                    "name": "selected",
                    "parameters": {
                        "peace_context": {
                            "war_id": "<war_id>",
                            "terms": [],
                        },
                    },
                    "purpose": "检查已选战争的空白和平提议对象。",
                },
                {
                    "name": "selected_offer",
                    "parameters": {
                        "peace_context": {
                            "war_id": "<war_id>",
                            "direction": "offer",
                            "terms": [],
                        },
                    },
                    "purpose": "检查法国向目标国家提出的空白和平对象。",
                },
            ]
        elif self.id == "demand_ducats":
            parameter_definitions = {
                "peace_context": {
                    "status": "context_required",
                    "type": "object",
                    "path": "peace_context",
                },
                "peace_context.war_id": {
                    "status": "required_for_selected",
                    "type": "war_id",
                    "path": "peace_context.war_id",
                },
                "peace_context.direction": {
                    "status": "required_for_selected",
                    "type": "string",
                    "enum": ["demand", "offer"],
                    "path": "peace_context.direction",
                },
                "peace_context.terms": {
                    "status": "required_for_selected",
                    "type": "array",
                    "min_length": 1,
                    "max_length": 6,
                    "allowed_action_ids": [
                        "demand_ducats", "cede_province", "war_reparations",
                        "transfer_trade_power", "concede_defeat", "annul_treaties",
                    ],
                    "primary_action_id": "demand_ducats",
                    "required_action_ids": ["demand_ducats"],
                    "unique_action_ids": True,
                    "max_occurrences_by_action_id": {
                        "demand_ducats": 1,
                        "cede_province": 1,
                        "war_reparations": 1,
                        "transfer_trade_power": 1,
                        "concede_defeat": 1,
                        "annul_treaties": 1,
                    },
                    "canonical_order": [
                        "demand_ducats", "cede_province", "war_reparations",
                        "transfer_trade_power", "concede_defeat", "annul_treaties",
                    ],
                    "path": "peace_context.terms",
                },
                "peace_context.terms[0].action_id": {
                    "status": "required_for_selected",
                    "type": "string",
                    "allowed_action_ids": [
                        "demand_ducats", "cede_province", "war_reparations",
                        "transfer_trade_power", "concede_defeat", "annul_treaties",
                    ],
                    "path": "peace_context.terms[0].action_id",
                },
                "peace_context.terms[0].amount": {
                    "status": "required_for_selected",
                    "type": ["number", "string"],
                    "unit": "ducats",
                    "precision": 0.1,
                    "path": "peace_context.terms[0].amount",
                },
                "peace_context.terms[0].payer": {
                    "status": "required_for_selected",
                    "type": "country_tag",
                    "equals": "recipient",
                    "equals_by_direction": {
                        "demand": "recipient", "offer": "actor",
                    },
                    "path": "peace_context.terms[0].payer",
                },
                "peace_context.terms[0].claimant": {
                    "status": "required_for_selected",
                    "type": "country_tag",
                    "equals": "actor",
                    "equals_by_direction": {
                        "demand": "actor", "offer": "recipient",
                    },
                    "path": "peace_context.terms[0].claimant",
                },
            }
            inspection_parameter_forms = [
                {
                    "name": "discovery",
                    "parameters": {},
                    "purpose": "发现当前会话中双方共同战争。",
                },
                {
                    "name": "selected",
                    "parameters": {
                        "peace_context": {
                            "war_id": "<war_id>",
                            "direction": "demand",
                            "terms": [{
                                "action_id": "demand_ducats",
                                "amount": "10.0",
                                "payer": "<recipient>",
                                "claimant": "<actor>",
                            }],
                        },
                    },
                    "purpose": "检查已选战争的索取金钱条款。",
                },
                {
                    "name": "selected_offer",
                    "parameters": {
                        "peace_context": {
                            "war_id": "<war_id>",
                            "direction": "offer",
                            "terms": [{
                                "action_id": "demand_ducats",
                                "amount": "10.0",
                                "payer": "<actor>",
                                "claimant": "<recipient>",
                            }],
                        },
                    },
                    "purpose": "检查法国向目标国家支付金钱的和平条款。",
                },
                {
                    "name": "selected_reparations",
                    "parameters": {
                        "peace_context": {
                            "war_id": "<war_id>",
                            "direction": "demand",
                            "terms": [
                                {
                                    "action_id": "demand_ducats",
                                    "amount": "10.0",
                                    "payer": "<recipient>",
                                    "claimant": "<actor>",
                                },
                                {
                                    "action_id": "war_reparations",
                                    "payer": "<recipient>",
                                    "claimant": "<actor>",
                                },
                            ],
                        },
                    },
                    "purpose": "检查索取金钱与战争赔款的组合条款。",
                },
                {
                    "name": "selected_offer_reparations",
                    "parameters": {
                        "peace_context": {
                            "war_id": "<war_id>",
                            "direction": "offer",
                            "terms": [
                                {
                                    "action_id": "demand_ducats",
                                    "amount": "10.0",
                                    "payer": "<actor>",
                                    "claimant": "<recipient>",
                                },
                                {
                                    "action_id": "war_reparations",
                                    "payer": "<actor>",
                                    "claimant": "<recipient>",
                                },
                            ],
                        },
                    },
                    "purpose": "检查支付金钱与战争赔款的组合条款。",
                },
            ]
        elif self.id == "send_gift":
            parameter_definitions = {
                "ducats": {
                    "status": "required",
                    "type": "integer",
                    "min": 25,
                    "max": 2147475,
                    "multiple_of": 25,
                    "unit": "ducats",
                    "raw_scale": 1000,
                    "path": "parameters.ducats",
                },
            }
        elif self.id == "influence_nation":
            # The native Influence object chooses its own cost and duration;
            # callers deliberately cannot supply a rule parameter.
            parameter_definitions = {}
        elif self.id == "cede_province":
            parameter_definitions = {
                "peace_context": {
                    "status": "context_required",
                    "type": "object",
                    "path": "peace_context",
                },
                "peace_context.war_id": {
                    "status": "required_for_selected",
                    "type": "war_id",
                    "path": "peace_context.war_id",
                },
                "peace_context.direction": {
                    "status": "required_for_selected",
                    "type": "string",
                    "enum": ["demand", "offer"],
                    "path": "peace_context.direction",
                },
                "peace_context.terms": {
                    "status": "required_for_selected",
                    "type": "array",
                    "max_length": 6,
                    "allowed_action_ids": [
                        "demand_ducats", "cede_province", "war_reparations",
                        "transfer_trade_power", "concede_defeat", "annul_treaties",
                    ],
                    "primary_action_id": "cede_province",
                    "required_action_ids": ["cede_province"],
                    "unique_action_ids": True,
                    "max_occurrences_by_action_id": {
                        "demand_ducats": 1,
                        "cede_province": 1,
                        "war_reparations": 1,
                        "transfer_trade_power": 1,
                        "concede_defeat": 1,
                        "annul_treaties": 1,
                    },
                    "canonical_order": [
                        "demand_ducats", "cede_province", "war_reparations",
                        "transfer_trade_power", "concede_defeat", "annul_treaties",
                    ],
                    "path": "peace_context.terms",
                },
                "peace_context.terms[0].action_id": {
                    "status": "required_for_selected",
                    "type": "string",
                    "allowed_action_ids": [
                        "demand_ducats", "cede_province", "war_reparations",
                        "transfer_trade_power", "concede_defeat", "annul_treaties",
                    ],
                    "path": "peace_context.terms[0].action_id",
                },
                "peace_context.terms[0].province_ids": {
                    "status": "required_for_selected",
                    "type": "array",
                    "min_items": 1,
                    "max_items": 16,
                    "unique": True,
                    "item_type": "positive_integer",
                    "path": "peace_context.terms[0].province_ids",
                },
                "peace_context.terms[0].beneficiary": {
                    "status": "required_for_selected",
                    "type": "country_tag",
                    "path": "peace_context.terms[0].beneficiary",
                },
            }
            inspection_parameter_forms = [
                {
                    "name": "discovery",
                    "parameters": {},
                    "purpose": "发现当前会话中双方共同战争。",
                },
                {
                    "name": "candidate_enumeration",
                    "parameters": {
                        "peace_context": {
                            "war_id": "<war_id>",
                            "direction": "demand",
                            "terms": [],
                        },
                    },
                    "purpose": "枚举当前战争可观察的割让省份候选。",
                },
                {
                    "name": "selected",
                    "parameters": {
                        "peace_context": {
                            "war_id": "<war_id>",
                            "direction": "demand",
                            "terms": [{
                                "action_id": "cede_province",
                                "province_ids": [177],
                                "beneficiary": "<beneficiary>",
                            }],
                        },
                    },
                    "purpose": "检查指定省份割让条款及原生选择结果。",
                },
                {
                    "name": "selected_offer",
                    "parameters": {
                        "peace_context": {
                            "war_id": "<war_id>",
                            "direction": "offer",
                            "terms": [{
                                "action_id": "cede_province",
                                "province_ids": [177],
                                "beneficiary": "<recipient-or-native-candidate>",
                            }],
                        },
                    },
                    "purpose": "检查法国提出的省份条款及原生选择结果。",
                },
                {
                    "name": "selected_combined",
                    "parameters": {
                        "peace_context": {
                            "war_id": "<war_id>",
                            "direction": "demand",
                            "terms": [
                                {
                                    "action_id": "demand_ducats",
                                    "amount": "10.0",
                                    "payer": "<recipient>",
                                    "claimant": "<actor>",
                                },
                                {
                                    "action_id": "cede_province",
                                    "province_ids": [177],
                                    "beneficiary": "<actor>",
                                },
                                {
                                    "action_id": "war_reparations",
                                    "payer": "<recipient>",
                                    "claimant": "<actor>",
                                },
                            ],
                        },
                    },
                    "purpose": "检查金钱、省份与战争赔款的组合条款。",
                },
            ]
        elif self.id == "war_reparations":
            # Reparations are a first-class term that can be sent alone or
            # alongside the money/province terms.  The indexed [0] entries
            # deliberately remain public compatibility keys for callers that
            # already address a single reparations term by that path.
            parameter_definitions = {
                "peace_context": {
                    "status": "context_required",
                    "type": "object",
                    "path": "peace_context",
                },
                "peace_context.war_id": {
                    "status": "required_for_selected",
                    "type": "war_id",
                    "path": "peace_context.war_id",
                },
                "peace_context.direction": {
                    "status": "required_for_selected",
                    "type": "string",
                    "enum": ["demand", "offer"],
                    "path": "peace_context.direction",
                },
                "peace_context.terms": {
                    "status": "required_for_selected",
                    "type": "array",
                    "min_length": 1,
                    "max_length": 6,
                    "allowed_action_ids": [
                        "demand_ducats", "cede_province", "war_reparations",
                        "transfer_trade_power", "concede_defeat", "annul_treaties",
                    ],
                    "primary_action_id": "war_reparations",
                    "required_action_ids": ["war_reparations"],
                    "unique_action_ids": True,
                    "max_occurrences_by_action_id": {
                        "demand_ducats": 1,
                        "cede_province": 1,
                        "war_reparations": 1,
                        "transfer_trade_power": 1,
                        "concede_defeat": 1,
                        "annul_treaties": 1,
                    },
                    "canonical_order": [
                        "demand_ducats", "cede_province", "war_reparations",
                        "transfer_trade_power", "concede_defeat", "annul_treaties",
                    ],
                    "path": "peace_context.terms",
                },
                "peace_context.terms[0].action_id": {
                    "status": "required_for_selected",
                    "type": "string",
                    "allowed_action_ids": [
                        "demand_ducats", "cede_province", "war_reparations",
                        "transfer_trade_power", "concede_defeat", "annul_treaties",
                    ],
                    "path": "peace_context.terms[0].action_id",
                },
                "peace_context.terms[0].payer": {
                    "status": "required_for_selected",
                    "type": "country_tag",
                    "equals": "recipient",
                    "equals_by_direction": {
                        "demand": "recipient", "offer": "actor",
                    },
                    "path": "peace_context.terms[0].payer",
                },
                "peace_context.terms[0].claimant": {
                    "status": "required_for_selected",
                    "type": "country_tag",
                    "equals": "actor",
                    "equals_by_direction": {
                        "demand": "actor", "offer": "recipient",
                    },
                    "path": "peace_context.terms[0].claimant",
                },
            }
            inspection_parameter_forms = [
                {
                    "name": "discovery",
                    "parameters": {},
                    "purpose": "发现当前会话中双方共同战争。",
                },
                {
                    "name": "selected",
                    "parameters": {
                        "peace_context": {
                            "war_id": "<war_id>",
                            "direction": "demand",
                            "terms": [{
                                "action_id": "war_reparations",
                                "payer": "<recipient>",
                                "claimant": "<actor>",
                            }],
                        },
                    },
                    "purpose": "检查被索取方支付战争赔款的和平条款。",
                },
                {
                    "name": "selected_offer",
                    "parameters": {
                        "peace_context": {
                            "war_id": "<war_id>",
                            "direction": "offer",
                            "terms": [{
                                "action_id": "war_reparations",
                                "payer": "<actor>",
                                "claimant": "<recipient>",
                            }],
                        },
                    },
                    "purpose": "检查法国支付战争赔款的和平条款。",
                },
                {
                    "name": "selected_combined",
                    "parameters": {
                        "peace_context": {
                            "war_id": "<war_id>",
                            "direction": "demand",
                            "terms": [
                                {
                                    "action_id": "demand_ducats",
                                    "amount": "10.0",
                                    "payer": "<recipient>",
                                    "claimant": "<actor>",
                                },
                                {
                                    "action_id": "cede_province",
                                    "province_ids": [177],
                                    "beneficiary": "<actor>",
                                },
                                {
                                    "action_id": "war_reparations",
                                    "payer": "<recipient>",
                                    "claimant": "<actor>",
                                },
                            ],
                        },
                    },
                    "purpose": "检查金钱、省份与战争赔款的规范组合条款。",
                },
            ]
        elif self.id == "transfer_trade_power":
            # Trade-power transfer is a non-numeric treaty term.  The native
            # define supplies its ratio; callers bind only the direction-bound
            # source and beneficiary roles.
            parameter_definitions = {
                "peace_context": {
                    "status": "context_required",
                    "type": "object",
                    "path": "peace_context",
                },
                "peace_context.war_id": {
                    "status": "required_for_selected",
                    "type": "war_id",
                    "path": "peace_context.war_id",
                },
                "peace_context.direction": {
                    "status": "required_for_selected",
                    "type": "string",
                    "enum": ["demand", "offer"],
                    "path": "peace_context.direction",
                },
                "peace_context.terms": {
                    "status": "required_for_selected",
                    "type": "array",
                    "min_length": 1,
                    "max_length": 6,
                    "allowed_action_ids": [
                        "demand_ducats", "cede_province", "war_reparations",
                        "transfer_trade_power", "concede_defeat", "annul_treaties",
                    ],
                    "primary_action_id": "transfer_trade_power",
                    "required_action_ids": ["transfer_trade_power"],
                    "unique_action_ids": True,
                    "max_occurrences_by_action_id": {
                        "demand_ducats": 1,
                        "cede_province": 1,
                        "war_reparations": 1,
                        "transfer_trade_power": 1,
                        "concede_defeat": 1,
                        "annul_treaties": 1,
                    },
                    "canonical_order": [
                        "demand_ducats", "cede_province", "war_reparations",
                        "transfer_trade_power", "concede_defeat", "annul_treaties",
                    ],
                    "path": "peace_context.terms",
                },
                "peace_context.terms[0].action_id": {
                    "status": "required_for_selected",
                    "type": "string",
                    "allowed_action_ids": [
                        "demand_ducats", "cede_province", "war_reparations",
                        "transfer_trade_power", "concede_defeat", "annul_treaties",
                    ],
                    "path": "peace_context.terms[0].action_id",
                },
                "peace_context.terms[0].source": {
                    "status": "required_for_selected",
                    "type": "country_tag",
                    # The native treaty can select a third-country source when
                    # the source-capability ACK is present.  The only public
                    # relation that remains invariant is that source and
                    # beneficiary are distinct; direction still binds the
                    # beneficiary below.
                    "canonical": True,
                    "not_equal_path": "peace_context.terms[0].beneficiary",
                    "path": "peace_context.terms[0].source",
                },
                "peace_context.terms[0].beneficiary": {
                    "status": "required_for_selected",
                    "type": "country_tag",
                    "equals_by_direction": {
                        "demand": "actor", "offer": "recipient",
                    },
                    "path": "peace_context.terms[0].beneficiary",
                },
            }
            inspection_parameter_forms = [
                {
                    "name": "discovery",
                    "parameters": {},
                    "purpose": "发现当前会话中双方共同战争。",
                },
                {
                    "name": "source_discovery",
                    "parameters": {
                        "peace_context": {
                            "war_id": "<war_id>",
                            "direction": "demand",
                            "terms": [],
                        },
                    },
                    "purpose": "发现可用于转移贸易竞争力条款的原生来源候选。",
                },
                {
                    "name": "selected",
                    "parameters": {
                        "peace_context": {
                            "war_id": "<war_id>",
                            "direction": "demand",
                            "terms": [{
                                "action_id": "transfer_trade_power",
                                "source": "<recipient>",
                                "beneficiary": "<actor>",
                            }],
                        },
                    },
                    "purpose": "检查被索取方转移贸易竞争力的和平条款。",
                },
                {
                    "name": "selected_offer",
                    "parameters": {
                        "peace_context": {
                            "war_id": "<war_id>",
                            "direction": "offer",
                            "terms": [{
                                "action_id": "transfer_trade_power",
                                "source": "<actor>",
                                "beneficiary": "<recipient>",
                            }],
                        },
                    },
                    "purpose": "检查法国向目标国家转移贸易竞争力的和平条款。",
                },
                {
                    "name": "selected_combined",
                    "parameters": {
                        "peace_context": {
                            "war_id": "<war_id>",
                            "direction": "demand",
                            "terms": [
                                {
                                    "action_id": "demand_ducats",
                                    "amount": "10.0",
                                    "payer": "<recipient>",
                                    "claimant": "<actor>",
                                },
                                {
                                    "action_id": "cede_province",
                                    "province_ids": [177],
                                    "beneficiary": "<actor>",
                                },
                                {
                                    "action_id": "war_reparations",
                                    "payer": "<recipient>",
                                    "claimant": "<actor>",
                                },
                                {
                                    "action_id": "transfer_trade_power",
                                    "source": "<recipient>",
                                    "beneficiary": "<actor>",
                                },
                            ],
                        },
                    },
                    "purpose": "检查四类规范和平条款的完整组合。",
                },
            ]
        elif self.id in COUNTRY_TERM_ACTIONS:
            # R61 country-shaped terms expose only their public target and
            # optional role override.  Native candidate selection remains the
            # authority for whether that country/role is legal in the war.
            country_term_definition = {
                "status": "required_for_selected",
                "type": "country_tag",
                "canonical": True,
                "path": "peace_context.terms[0].country",
            }
            term_example: dict[str, object] = {
                "action_id": self.id,
                "country": "<country>",
            }
            if self.id == "release_nation":
                parameter_definitions = {
                    "peace_context": {
                        "status": "context_required", "type": "object",
                        "path": "peace_context",
                    },
                    "peace_context.war_id": {
                        "status": "required_for_selected", "type": "war_id",
                        "path": "peace_context.war_id",
                    },
                    "peace_context.direction": {
                        "status": "required_for_selected", "type": "string",
                        "enum": ["demand", "offer"],
                        "path": "peace_context.direction",
                    },
                    "peace_context.terms": {
                        "status": "required_for_selected", "type": "array",
                        "min_length": 1, "max_length": 1,
                        "allowed_action_ids": [self.id],
                        "primary_action_id": self.id,
                        "required_action_ids": [self.id],
                        "unique_action_ids": True,
                        "max_occurrences_by_action_id": {self.id: 1},
                        "canonical_order": [self.id],
                        "path": "peace_context.terms",
                    },
                    "peace_context.terms[0].action_id": {
                        "status": "required_for_selected", "type": "string",
                        "allowed_action_ids": [self.id],
                        "path": "peace_context.terms[0].action_id",
                    },
                    "peace_context.terms[0].country": country_term_definition,
                    "peace_context.terms[0].source": {
                        "status": "optional_for_selected", "type": "country_tag",
                        "canonical": True,
                        "path": "peace_context.terms[0].source",
                    },
                }
                term_example["source"] = "<source>"
            elif self.id == "grant_independence":
                parameter_definitions = {
                    "peace_context": {
                        "status": "context_required", "type": "object",
                        "path": "peace_context",
                    },
                    "peace_context.war_id": {
                        "status": "required_for_selected", "type": "war_id",
                        "path": "peace_context.war_id",
                    },
                    "peace_context.direction": {
                        "status": "required_for_selected", "type": "string",
                        "enum": ["demand", "offer"],
                        "path": "peace_context.direction",
                    },
                    "peace_context.terms": {
                        "status": "required_for_selected", "type": "array",
                        "min_length": 1, "max_length": 1,
                        "allowed_action_ids": [self.id],
                        "primary_action_id": self.id,
                        "required_action_ids": [self.id],
                        "unique_action_ids": True,
                        "max_occurrences_by_action_id": {self.id: 1},
                        "canonical_order": [self.id],
                        "path": "peace_context.terms",
                    },
                    "peace_context.terms[0].action_id": {
                        "status": "required_for_selected", "type": "string",
                        "allowed_action_ids": [self.id],
                        "path": "peace_context.terms[0].action_id",
                    },
                }
                term_example = {"action_id": self.id}
            else:
                parameter_definitions = {
                    "peace_context": {
                        "status": "context_required", "type": "object",
                        "path": "peace_context",
                    },
                    "peace_context.war_id": {
                        "status": "required_for_selected", "type": "war_id",
                        "path": "peace_context.war_id",
                    },
                    "peace_context.direction": {
                        "status": "required_for_selected", "type": "string",
                        "enum": ["demand", "offer"],
                        "path": "peace_context.direction",
                    },
                    "peace_context.terms": {
                        "status": "required_for_selected", "type": "array",
                        "min_length": 1, "max_length": 1,
                        "allowed_action_ids": [self.id],
                        "primary_action_id": self.id,
                        "required_action_ids": [self.id],
                        "unique_action_ids": True,
                        "max_occurrences_by_action_id": {self.id: 1},
                        "canonical_order": [self.id],
                        "path": "peace_context.terms",
                    },
                    "peace_context.terms[0].action_id": {
                        "status": "required_for_selected", "type": "string",
                        "allowed_action_ids": [self.id],
                        "path": "peace_context.terms[0].action_id",
                    },
                    "peace_context.terms[0].country": country_term_definition,
                    "peace_context.terms[0].beneficiary": {
                        "status": "optional_for_selected", "type": "country_tag",
                        "canonical": True,
                        "path": "peace_context.terms[0].beneficiary",
                    },
                }
                term_example["beneficiary"] = "<beneficiary>"
            inspection_parameter_forms = [
                {
                    "name": "discovery",
                    "parameters": {},
                    "purpose": "发现当前会话中双方共同战争。",
                },
                {
                    "name": "candidate_discovery",
                    "parameters": {"peace_context": {
                        "war_id": "<war_id>", "direction": "demand",
                        "terms": [],
                    }},
                    "purpose": "发现该战争中的原生国家条款候选。",
                },
                {
                    "name": "selected",
                    "parameters": {"peace_context": {
                        "war_id": "<war_id>", "direction": "demand",
                        "terms": [term_example],
                    }},
                    "purpose": "检查一个已选国家条款。",
                },
            ]
        elif self.id in {"humiliate_rival", "show_strength", "force_religion"}:
            # The three R54 special terms share the same public role contract.
            # Their native rule predicates and consequences remain separate;
            # this catalog only describes the direction-bound selection shape.
            special_names = {
                "humiliate_rival": "羞辱宿敌",
                "show_strength": "展示霸权",
                "force_religion": "强制信仰",
            }
            shared_actions = [
                "demand_ducats", "cede_province", "war_reparations",
                "transfer_trade_power", "concede_defeat", "annul_treaties",
                "humiliate_rival", "show_strength", "force_religion",
            ]
            shared_counts = {action_id: 1 for action_id in shared_actions}
            parameter_definitions = {
                "peace_context": {
                    "status": "context_required", "type": "object",
                    "path": "peace_context",
                },
                "peace_context.war_id": {
                    "status": "required_for_selected", "type": "war_id",
                    "path": "peace_context.war_id",
                },
                "peace_context.direction": {
                    "status": "required_for_selected", "type": "string",
                    "enum": ["demand", "offer"],
                    "path": "peace_context.direction",
                },
                "peace_context.terms": {
                    "status": "required_for_selected", "type": "array",
                    "min_length": 1, "max_length": 9,
                    "allowed_action_ids": shared_actions,
                    "primary_action_id": self.id,
                    "required_action_ids": [self.id],
                    "unique_action_ids": True,
                    "max_occurrences_by_action_id": shared_counts,
                    "canonical_order": shared_actions,
                    "path": "peace_context.terms",
                },
                "peace_context.terms[0].action_id": {
                    "status": "required_for_selected", "type": "string",
                    "allowed_action_ids": shared_actions,
                    "path": "peace_context.terms[0].action_id",
                },
                "peace_context.terms[0].country": {
                    "status": "optional_for_selected", "type": "country_tag",
                    "canonical": True,
                    "equals_by_direction": {
                        "demand": "recipient", "offer": "actor",
                    },
                    "path": "peace_context.terms[0].country",
                },
                "peace_context.terms[0].beneficiary": {
                    "status": "optional_for_selected", "type": "country_tag",
                    "canonical": True,
                    "equals_by_direction": {
                        "demand": "actor", "offer": "recipient",
                    },
                    "path": "peace_context.terms[0].beneficiary",
                },
            }
            inspection_parameter_forms = [
                {
                    "name": "discovery",
                    "parameters": {},
                    "purpose": "发现当前会话中双方共同战争。",
                },
                {
                    "name": "selected",
                    "parameters": {"peace_context": {
                        "war_id": "<war_id>", "direction": "demand",
                        "terms": [{"action_id": self.id,
                                   "country": "<recipient>",
                                   "beneficiary": "<actor>"}],
                    }},
                    "purpose": f"检查{special_names[self.id]}和平条款。",
                },
                {
                    "name": "selected_offer",
                    "parameters": {"peace_context": {
                        "war_id": "<war_id>", "direction": "offer",
                        "terms": [{"action_id": self.id,
                                   "country": "<actor>",
                                   "beneficiary": "<recipient>"}],
                    }},
                    "purpose": f"检查法国提出的{special_names[self.id]}和平条款。",
                },
            ]
        elif self.id == "concede_defeat":
            # Concede Defeat is a direction-bound, non-financial term.  The
            # public roles describe the treaty parties; native legality and
            # prestige consequences remain evidence supplied by the adapter.
            parameter_definitions = {
                "peace_context": {
                    "status": "context_required",
                    "type": "object",
                    "path": "peace_context",
                },
                "peace_context.war_id": {
                    "status": "required_for_selected",
                    "type": "war_id",
                    "path": "peace_context.war_id",
                },
                "peace_context.direction": {
                    "status": "required_for_selected",
                    "type": "string",
                    "enum": ["demand", "offer"],
                    "path": "peace_context.direction",
                },
                "peace_context.terms": {
                    "status": "required_for_selected",
                    "type": "array",
                    "min_length": 1,
                    "max_length": 6,
                    "allowed_action_ids": [
                        "demand_ducats", "cede_province", "war_reparations",
                        "transfer_trade_power", "concede_defeat", "annul_treaties",
                    ],
                    "primary_action_id": "concede_defeat",
                    "required_action_ids": ["concede_defeat"],
                    "unique_action_ids": True,
                    "max_occurrences_by_action_id": {
                        "demand_ducats": 1,
                        "cede_province": 1,
                        "war_reparations": 1,
                        "transfer_trade_power": 1,
                        "concede_defeat": 1,
                        "annul_treaties": 1,
                    },
                    "canonical_order": [
                        "demand_ducats", "cede_province", "war_reparations",
                        "transfer_trade_power", "concede_defeat", "annul_treaties",
                    ],
                    "path": "peace_context.terms",
                },
                "peace_context.terms[0].action_id": {
                    "status": "required_for_selected",
                    "type": "string",
                    "allowed_action_ids": [
                        "demand_ducats", "cede_province", "war_reparations",
                        "transfer_trade_power", "concede_defeat", "annul_treaties",
                    ],
                    "path": "peace_context.terms[0].action_id",
                },
                "peace_context.terms[0].conceding_country": {
                    "status": "required_for_selected",
                    "type": "country_tag",
                    "equals_by_direction": {
                        "demand": "recipient", "offer": "actor",
                    },
                    "path": "peace_context.terms[0].conceding_country",
                },
                "peace_context.terms[0].beneficiary": {
                    "status": "required_for_selected",
                    "type": "country_tag",
                    "equals_by_direction": {
                        "demand": "actor", "offer": "recipient",
                    },
                    "path": "peace_context.terms[0].beneficiary",
                },
            }
            inspection_parameter_forms = [
                {
                    "name": "discovery",
                    "parameters": {},
                    "purpose": "发现当前会话中双方共同战争。",
                },
                {
                    "name": "selected",
                    "parameters": {
                        "peace_context": {
                            "war_id": "<war_id>",
                            "direction": "demand",
                            "terms": [{
                                "action_id": "concede_defeat",
                                "conceding_country": "<recipient>",
                                "beneficiary": "<actor>",
                            }],
                        },
                    },
                    "purpose": "检查被索取方承认战败的和平条款。",
                },
                {
                    "name": "selected_offer",
                    "parameters": {
                        "peace_context": {
                            "war_id": "<war_id>",
                            "direction": "offer",
                            "terms": [{
                                "action_id": "concede_defeat",
                                "conceding_country": "<actor>",
                                "beneficiary": "<recipient>",
                            }],
                        },
                    },
                    "purpose": "检查法国承认战败的和平条款。",
                },
                {
                    "name": "selected_combined",
                    "parameters": {
                        "peace_context": {
                            "war_id": "<war_id>",
                            "direction": "demand",
                            "terms": [
                                {"action_id": "demand_ducats", "amount": "10.0",
                                 "payer": "<recipient>", "claimant": "<actor>"},
                                {"action_id": "cede_province", "province_ids": [177],
                                 "beneficiary": "<actor>"},
                                {"action_id": "war_reparations", "payer": "<recipient>",
                                 "claimant": "<actor>"},
                                {"action_id": "transfer_trade_power", "source": "<recipient>",
                                 "beneficiary": "<actor>"},
                                {"action_id": "concede_defeat",
                                 "conceding_country": "<recipient>",
                                 "beneficiary": "<actor>"},
                            ],
                        },
                    },
                    "purpose": "检查五类规范和平条款的完整组合。",
                },
            ]
        elif self.id == "annul_treaties":
            # Annul Treaties has an explicit country and a sorted, bounded
            # partner set.  It may be queried with empty terms as a native
            # candidate-discovery request; legality and candidate selection
            # remain native evidence.
            shared_actions = [
                "demand_ducats", "cede_province", "war_reparations",
                "transfer_trade_power", "concede_defeat", "annul_treaties",
            ]
            shared_counts = {action_id: 1 for action_id in shared_actions}
            parameter_definitions = {
                "peace_context": {
                    "status": "context_required", "type": "object",
                    "path": "peace_context",
                },
                "peace_context.war_id": {
                    "status": "required_for_selected", "type": "war_id",
                    "path": "peace_context.war_id",
                },
                "peace_context.direction": {
                    "status": "required_for_selected", "type": "string",
                    "enum": ["demand", "offer"],
                    "path": "peace_context.direction",
                },
                "peace_context.terms": {
                    "status": "required_for_selected", "type": "array",
                    "min_length": 0, "max_length": 6,
                    "allowed_action_ids": shared_actions,
                    "primary_action_id": "annul_treaties",
                    "required_action_ids": ["annul_treaties"],
                    "unique_action_ids": True,
                    "max_occurrences_by_action_id": shared_counts,
                    "canonical_order": shared_actions,
                    "path": "peace_context.terms",
                },
                "peace_context.terms[0].action_id": {
                    "status": "required_for_selected", "type": "string",
                    "allowed_action_ids": shared_actions,
                    "path": "peace_context.terms[0].action_id",
                },
                "peace_context.terms[0].country": {
                    "status": "required_for_selected", "type": "country_tag",
                    "canonical": True,
                    "path": "peace_context.terms[0].country",
                },
                "peace_context.terms[0].treaty_partners": {
                    "status": "required_for_selected", "type": "array",
                    "min_length": 1, "max_length": 16,
                    "item_type": "country_tag", "canonical": True,
                    "unique_items": True, "sorted": True,
                    "not_equal_path": "peace_context.terms[0].country",
                    "path": "peace_context.terms[0].treaty_partners",
                },
            }
            inspection_parameter_forms = [
                {
                    "name": "discovery",
                    "parameters": {"peace_context": {
                        "war_id": "<war_id>", "direction": "demand", "terms": [],
                    }},
                    "purpose": "发现原生可取消条约候选；空条款不是白和平。",
                },
                {
                    "name": "selected",
                    "parameters": {"peace_context": {
                        "war_id": "<war_id>", "direction": "demand",
                        "terms": [{"action_id": "annul_treaties",
                                   "country": "<country>",
                                   "treaty_partners": ["<partner>"]}],
                    }},
                    "purpose": "检查指定国家与条约伙伴的取消条款。",
                },
                {
                    "name": "selected_offer",
                    "parameters": {"peace_context": {
                        "war_id": "<war_id>", "direction": "offer",
                        "terms": [{"action_id": "annul_treaties",
                                   "country": "<country>",
                                   "treaty_partners": ["<partner>"]}],
                    }},
                    "purpose": "检查议和提议中的取消条款。",
                },
            ]
        elif self.id in {"release_subject", "transfer_subject"}:
            parameter_definitions = {
                "peace_context": {
                    "status": "context_required", "type": "object",
                    "path": "peace_context",
                },
                "peace_context.war_id": {
                    "status": "required_for_selected", "type": "war_id",
                    "path": "peace_context.war_id",
                },
                "peace_context.direction": {
                    "status": "optional_for_selected", "type": "string",
                    "enum": ["demand", "offer"], "default": "demand",
                    "path": "peace_context.direction",
                },
                "peace_context.terms": {
                    "status": "required_for_selected", "type": "array",
                    "min_length": 0, "max_length": 1,
                    "allowed_action_ids": [self.id],
                    "primary_action_id": self.id,
                    "required_action_ids": [self.id],
                    "unique_action_ids": True,
                    "path": "peace_context.terms",
                },
                "peace_context.terms[0].action_id": {
                    "status": "required_for_selected", "type": "string",
                    "allowed_action_ids": [self.id],
                    "path": "peace_context.terms[0].action_id",
                },
                "peace_context.terms[0].country": {
                    "status": "required_for_selected", "type": "country_tag",
                    "canonical": True,
                    "path": "peace_context.terms[0].country",
                },
                "peace_context.terms[0].countries": {
                    "status": "required_for_selected_multi", "type": "array",
                    "min_length": 1, "max_length": 16,
                    "item_type": "country_tag", "canonical": True,
                    "unique_items": True, "sorted": True,
                    "path": "peace_context.terms[0].countries",
                },
            }
            inspection_parameter_forms = [
                {
                    "name": "discovery",
                    "parameters": {"peace_context": {
                        "war_id": "<war_id>", "direction": "demand",
                        "terms": [],
                    }},
                    "purpose": "发现原生附属国候选；空条款不是已选议和条款。",
                },
                {
                    "name": "selected",
                    "parameters": {"peace_context": {
                        "war_id": "<war_id>", "direction": "demand",
                        "terms": [{"action_id": self.id,
                                   "country": "<country>"}],
                    }},
                    "purpose": "检查指定附属国候选和原生完整规则。",
                },
                {
                    "name": "selected_offer",
                    "parameters": {"peace_context": {
                        "war_id": "<war_id>", "direction": "offer",
                        "terms": [{"action_id": self.id,
                                   "country": "<country>"}],
                    }},
                    "purpose": "检查offer方向中的指定附属国候选。",
                },
            ]
        elif self.id in {"return_core", "revoke_core"}:
            # QUERY14 remains the candidate-discovery/standalone core query.
            # Explicit selections may also be carried by the EXEC8 mixed
            # peace contract, which uses the same bounded core term shape.
            parameter_definitions = {
                "peace_context": {
                    "status": "context_required", "type": "object",
                    "path": "peace_context",
                },
                "peace_context.war_id": {
                    "status": "required_for_selected", "type": "war_id",
                    "path": "peace_context.war_id",
                },
                "peace_context.direction": {
                    "status": "optional_for_selected", "type": "string",
                    "enum": ["demand", "offer"], "default": "demand",
                    "path": "peace_context.direction",
                },
                "peace_context.terms": {
                    "status": "required_for_selected", "type": "array",
                    "min_length": 0, "max_length": 11,
                    "allowed_action_ids": [
                        "demand_ducats", "cede_province", "war_reparations",
                        "transfer_trade_power", "concede_defeat",
                        "annul_treaties", "humiliate_rival", "show_strength",
                        "force_religion", "return_core", "revoke_core",
                    ],
                    "primary_action_id": self.id,
                    "required_action_ids": [self.id],
                    "unique_action_ids": True,
                    "max_occurrences_by_action_id": {
                        action_id: 1 for action_id in (
                            "demand_ducats", "cede_province", "war_reparations",
                            "transfer_trade_power", "concede_defeat",
                            "annul_treaties", "humiliate_rival", "show_strength",
                            "force_religion", "return_core", "revoke_core")},
                    "canonical_order": [
                        "demand_ducats", "cede_province", "war_reparations",
                        "transfer_trade_power", "concede_defeat", "annul_treaties",
                        "humiliate_rival", "show_strength", "force_religion",
                        "return_core", "revoke_core"],
                    "path": "peace_context.terms",
                },
                "peace_context.terms[0].action_id": {
                    "status": "required_for_selected", "type": "string",
                    "allowed_action_ids": [
                        "demand_ducats", "cede_province", "war_reparations",
                        "transfer_trade_power", "concede_defeat",
                        "annul_treaties", "humiliate_rival", "show_strength",
                        "force_religion", "return_core", "revoke_core"],
                    "path": "peace_context.terms[0].action_id",
                },
                "peace_context.terms[0].province_ids": {
                    "status": "required_for_selected", "type": "array",
                    "min_length": 1, "max_length": 16,
                    "unique_items": True, "item_type": "positive_int",
                    "path": "peace_context.terms[0].province_ids",
                },
                "peace_context.terms[0].core_owner": {
                    "status": "required_for_selected", "type": "country_tag",
                    "canonical": True,
                    "path": "peace_context.terms[0].core_owner",
                },
            }
            inspection_parameter_forms = [
                {
                    "name": "discovery",
                    "parameters": {},
                    "purpose": "发现当前会话中双方共同战争。",
                },
                {
                    "name": "candidate_discovery",
                    "parameters": {"peace_context": {
                        "war_id": "<war_id>", "direction": "demand",
                        "terms": [],
                    }},
                    "purpose": "发现该战争中可用于核心条款的原生候选省份。",
                },
                {
                    "name": "selected",
                    "parameters": {"peace_context": {
                        "war_id": "<war_id>", "direction": "demand",
                        "terms": [{
                            "action_id": self.id,
                            "province_ids": [177],
                            "core_owner": "<country>",
                        }],
                    }},
                    "purpose": "检查一个已选核心省份条款。",
                },
            ]
        # All selected non-white peace terms share the bounded mixed-term
        # contract.  QUERY14 discovery remains the explicit empty-term form
        # for the two core-primary actions; selected core and mixed forms use
        # the execution inspection/EXEC8 path when acknowledged.
        if (self.category == "peace_term" and self.id != "white_peace"):
            shared_actions = [
                "demand_ducats", "cede_province", "war_reparations",
                "transfer_trade_power", "concede_defeat", "annul_treaties",
                "humiliate_rival", "show_strength", "force_religion",
                "return_core", "revoke_core", "release_subject",
                "transfer_subject", "release_nation",
                "force_vassalization", "form_personal_union",
                "grant_independence", "full_annexation",
            ]
            terms_definition = parameter_definitions.get("peace_context.terms")
            if isinstance(terms_definition, dict):
                terms_definition.update({
                    "min_length": 0 if self.id in COUNTRY_TERM_ACTIONS
                    else terms_definition.get("min_length", 1),
                    "max_length": 18,
                    "allowed_action_ids": shared_actions,
                    "max_occurrences_by_action_id": {
                        action_id: 1 for action_id in shared_actions
                    },
                    "canonical_order": list(PEACE_TERM_CANONICAL_ORDER),
                })
            action_definition = parameter_definitions.get(
                "peace_context.terms[0].action_id")
            if isinstance(action_definition, dict):
                action_definition["allowed_action_ids"] = shared_actions
            parameter_definitions.setdefault(
                "peace_context.terms[*].province_ids", {
                    "status": "required_for_selected",
                    "type": "array", "min_length": 1, "max_length": 16,
                    "unique_items": True, "item_type": "positive_int",
                    "path": "peace_context.terms[*].province_ids",
                })
            parameter_definitions.setdefault(
                "peace_context.terms[*].core_owner", {
                    "status": "required_for_selected",
                    "type": "country_tag", "canonical": True,
                    "path": "peace_context.terms[*].core_owner",
                })
            parameter_definitions.setdefault(
                "peace_context.terms[*].countries", {
                    "status": "required_for_selected_multi",
                    "type": "array", "min_length": 1, "max_length": 16,
                    "item_type": "country_tag", "canonical": True,
                    "unique_items": True, "sorted": True,
                    "path": "peace_context.terms[*].countries",
                })

        result = {
            "action_id": self.id, "name_zh": self.name_zh, "name_en": self.name_en,
            "category": self.category, "native_identifier": self.native_identifier,
            "identification_source": self.identification_source,
            "parameter_definitions": parameter_definitions,
            "phases": {phase: {"query": "unimplemented", "execute": "unimplemented",
                                "reason_code": "NATIVE_INTERFACE_UNIDENTIFIED"} for phase in phases},
            "runtime_verified": False,
        }
        if inspection_parameter_forms is not None:
            result["inspection_parameter_forms"] = inspection_parameter_forms
        if self.id == "declare_war":
            # Force counts are an optional native observation.  They are
            # exposed only when the installation publishes the dedicated ACK;
            # the static catalog describes the public shape without claiming
            # that every producer supplies it.
            result["observed_outputs"] = {
                "forces": {
                    "status": "optional_when_capability_acknowledged",
                    "capability": "native_declare_war_forces",
                    "source": "native_declare_war_dialog",
                    "path": "inspection.forces",
                    "unit": "men",
                    "sides": ["attackers", "defenders"],
                },
            }
        return result


_DIPLOMACY = (
    ("declare_war", "宣战", "Declare War", False, ("casus_belli", "war_goal", "call_allies")),
    ("offer_alliance", "提议结盟", "Offer Alliance", True, ()),
    ("dissolve_alliance", "断绝同盟", "Dissolve Alliance", False, ()),
    ("improve_relations", "改善关系", "Improve Relations", False, ()),
    ("stop_improving_relations", "停止改善关系", "Stop Improving Relations", False, ()),
    ("offer_royal_marriage", "提议王室联姻", "Offer Royal Marriage", True, ()),
    ("break_royal_ties", "断绝王室联姻", "Break Royal Ties", False, ()),
    ("build_spy_network", "建立间谍网", "Build Spy Network", False, ()),
    ("stop_building_spy_network", "停止建立间谍网", "Stop Building Spy Network", False, ()),
    ("curry_favors", "获取人情", "Curry Favors", False, ()),
    ("stop_curry_favors", "停止获取人情", "Stop Currying Favors", False, ()),
    ("proclaim_guarantee", "保证独立", "Proclaim Guarantee", False, ()),
    ("revoke_guarantee", "撤销保证独立", "Revoke Guarantee", False, ()),
    ("ask_military_access", "请求军事通行权", "Ask for Military Access", True, ()),
    ("cancel_military_access", "取消军事通行权", "Cancel Military Access", False, ()),
    ("send_insult", "侮辱", "Send Insult", False, ()),
    ("scornful_insult", "轻蔑地侮辱", "Scornful Insult", False, ()),
    ("set_rival", "宣布宿敌", "Set Rival", False, ()),
    ("remove_rival", "移除宿敌", "Remove Rival", False, ()),
    ("offer_vassalization", "提议附庸", "Offer Vassalization", True, ()),
    ("cancel_vassalization", "取消附庸关系", "Cancel Vassalization", False, ()),
)
_PEACE = (
    ("cede_province", "割让省份", "Cede Province", ("province_ids", "beneficiary")),
    ("full_annexation", "完全吞并", "Full Annexation", ("country", "beneficiary")),
    ("return_core", "归还核心省份", "Return Core", ("province_ids", "core_owner")),
    ("release_nation", "释放国家", "Release Nation", ("country", "source")),
    ("revoke_core", "放弃核心", "Revoke Core", ("province_ids", "core_owner")),
    ("force_vassalization", "强迫附庸", "Force Vassalization", ("country", "beneficiary")),
    ("form_personal_union", "建立共主邦联", "Form Personal Union", ("country", "beneficiary")),
    ("release_subject", "释放附属国", "Release Subject", ("country",)),
    ("transfer_subject", "转移附属国", "Transfer Subject", ("country",)),
    ("grant_independence", "承认独立", "Grant Independence", ()),
    ("demand_ducats", "索取金钱", "Demand Ducats", ("amount", "payer", "claimant")),
    ("war_reparations", "战争赔款", "War Reparations", ("payer", "claimant")),
    ("transfer_trade_power", "转移贸易竞争力", "Transfer Trade Power", ("source", "beneficiary")),
    ("annul_treaties", "取消条约", "Annul Treaties", ("country", "treaty_partners")),
    ("humiliate_rival", "羞辱宿敌", "Humiliate Rival", ("country", "beneficiary")),
    ("show_strength", "展示霸权", "Show Strength", ("country", "beneficiary")),
    ("force_religion", "强制信仰", "Force Religion", ("country", "beneficiary")),
    ("concede_defeat", "承认战败", "Concede Defeat", ("conceding_country", "beneficiary")),
    ("white_peace", "无条件和平", "White Peace", ()),
)

# The peace directory is a stable public set.  Native context discovery is
# query-only for every member of this set; a later offer adapter must still
# require a complete ``peace_context`` before it can execute a term.
PEACE_ACTION_IDS = frozenset(row[0] for row in _PEACE)

ACTIONS = {row[0]: Action(*row[:3], "diplomatic_action", row[3], row[4]) for row in _DIPLOMACY}
ACTIONS.update({row[0]: Action(*row[:3], "peace_term", True,
                              ("peace_context",) + row[3]) for row in _PEACE})
# Context discovery identifies the shared native peace family for all terms;
# the term-specific offer object and rule adapter remain unimplemented.
for _peace_action_id in PEACE_ACTION_IDS:
    _peace_action = ACTIONS[_peace_action_id]
    ACTIONS[_peace_action_id] = Action(
        _peace_action.id, _peace_action.name_zh, _peace_action.name_en,
        _peace_action.category, _peace_action.response,
        _peace_action.parameters, "peace",
        "native_peace_context_inspection")
# Declare War remains a catalog action with explicit CB/war-goal/ally context
# requirements.  R36 added the bounded QUERY1/QUERY3 inspection; R37 adds a
# separately ACK-gated EXEC3 submission path whose result is only business
# success after the native war transition is verified.
ACTIONS["declare_war"] = Action(
    "declare_war", "宣战", "Declare War", "diplomatic_action", False,
    ("casus_belli", "war_goal", "call_allies"), "declare_war",
    "work/runtime/declarewar-action-contract-20261016-001/report.md；"
    "work/runtime/declarewar-identification-20261016-002/report.md")
# A distinct semantic action even when the UI occupies the guarantee position.
ACTIONS["support_independence"] = Action("support_independence", "支持独立", "Support Independence",
    "diplomatic_action", True, (), "support_independence_action",
    "docs/外交接口开发方案.md: 本机1.37.4 static_actions只读登记")
ACTIONS["revoke_support_independence"] = Action(
    "revoke_support_independence", "撤销支持独立", "Revoke Support Independence",
    "diplomatic_action", False, (), "support_independence_action",
    "docs/外交接口开发方案.md: 本机1.37.4 static_actions只读登记")
ACTIONS["offer_alliance"] = Action("offer_alliance", "提议结盟", "Offer Alliance", "diplomatic_action",
    True, (), "allianceaction", "work/runtime/alliance-static-20261013/alliance-static-audit.md；r3实测匹配Offer对象")
ACTIONS["dissolve_alliance"] = Action("dissolve_alliance", "断绝同盟", "Dissolve Alliance", "diplomatic_action",
    False, (), "allianceaction", "work/runtime/alliance-static-20261013/alliance-static-audit.md：Cancel变体静态识别（同一原生动作家族）")
ACTIONS["proclaim_guarantee"] = Action("proclaim_guarantee", "保证独立", "Proclaim Guarantee",
    "diplomatic_action", False, (), "guaranteeaction",
    "docs/保证独立接口与运行验收.md；work/runtime/guarantee-support-identification-20261015-001/report.md")
ACTIONS["revoke_guarantee"] = Action("revoke_guarantee", "撤销保证独立", "Revoke Guarantee",
    "diplomatic_action", False, (), "guaranteeaction",
    "docs/保证独立接口与运行验收.md；work/runtime/guarantee-support-identification-20261015-001/report.md")
ACTIONS["ask_military_access"] = Action(
    "ask_military_access", "请求军事通行权", "Ask for Military Access",
    "diplomatic_action", True, (), "military_access",
    "work/runtime/military-access-integration-20261015-001/report.md")
ACTIONS["cancel_military_access"] = Action(
    "cancel_military_access", "取消军事通行权", "Cancel Military Access",
    "diplomatic_action", False, (), "military_access",
    "work/runtime/military-access-integration-20261015-001/report.md")
ACTIONS["offer_royal_marriage"] = Action("offer_royal_marriage", "提议王室联姻", "Offer Royal Marriage",
    "diplomatic_action", True, (), "royal_marriage",
    "work/runtime/royal-marriage-identification-20261015-001/report.md；"
    "work/runtime/royal-marriage-identification-20261015-001/query-methods-20261015-001/report.md")
ACTIONS["break_royal_ties"] = Action("break_royal_ties", "断绝王室联姻", "Break Royal Ties",
    "diplomatic_action", False, (), "royal_marriage",
    "work/runtime/royal-marriage-identification-20261015-001/report.md；"
    "work/runtime/royal-marriage-identification-20261015-001/query-methods-20261015-001/report.md")
ACTIONS["improve_relations"] = Action("improve_relations", "改善关系", "Improve Relations",
    "diplomatic_action", False, (), "improve_relations",
    "native ImproveRelations query contract; native UI chooses the diplomat")
ACTIONS["stop_improving_relations"] = Action(
    "stop_improving_relations", "停止改善关系", "Stop Improving Relations",
    "diplomatic_action", False, (), "improve_relations",
    "native ImproveRelations query contract; native UI chooses the diplomat")
ACTIONS["build_spy_network"] = Action(
    "build_spy_network", "建立间谍网", "Build Spy Network",
    "diplomatic_action", False, (), "spy_network",
    "native Spy Network query contract; native UI chooses the diplomat")
ACTIONS["stop_building_spy_network"] = Action(
    "stop_building_spy_network", "停止建立间谍网", "Stop Building Spy Network",
    "diplomatic_action", False, (), "spy_network",
    "native Spy Network query contract; native UI chooses the diplomat")
ACTIONS["curry_favors"] = Action(
    "curry_favors", "获取人情", "Curry Favors",
    "diplomatic_action", False, (), "curry_favors",
    "work/runtime/r71-curry-contract-20261020-001/report.md；native selector 0x3acc")
ACTIONS["stop_curry_favors"] = Action(
    "stop_curry_favors", "停止获取人情", "Stop Currying Favors",
    "diplomatic_action", False, (), "curry_favors",
    "work/runtime/r71-curry-contract-20261020-001/report.md；native selector 0x3acc")
ACTIONS["send_insult"] = Action(
    "send_insult", "侮辱", "Send Insult", "diplomatic_action", False, (), "insult",
    "R33 native insult query2/submission contract")
ACTIONS["scornful_insult"] = Action(
    "scornful_insult", "轻蔑地侮辱", "Scornful Insult", "diplomatic_action", False,
    ("insult_id",), "insult", "R33 native insult query2 candidate contract")
ACTIONS["set_rival"] = Action(
    "set_rival", "宣布宿敌", "Set Rival", "diplomatic_action", False, (), "rival",
    "R34 native countrycommands query contract; query-only")
ACTIONS["remove_rival"] = Action(
    "remove_rival", "移除宿敌", "Remove Rival", "diplomatic_action", False, (), "rival",
    "R34 native countrycommands query contract; query-only")
ACTIONS["trade_favors_for_gold"] = Action(
    "trade_favors_for_gold", "用人情换取金币", "Trade Favors for Ducats", "diplomatic_action", True,
    (), "trade_favors_for_gold", "R71 native factory, rules and income-derived amount")
ACTIONS["trade_favors_for_trust"] = Action(
    "trade_favors_for_trust", "用人情提升信任", "Trade Favors for Trust", "diplomatic_action", True,
    (), "trade_favors_for_trust", "R73 native favor resource contract; trust amount from native rule")
ACTIONS["trade_favors_for_men"] = Action(
    "trade_favors_for_men", "用人情换取人力", "Trade Favors for Men", "diplomatic_action", True,
    (), "trade_favors_for_men", "R73 native favor resource contract; manpower amount from native rule")
ACTIONS["send_gift"] = Action(
    "send_gift", "赠送金币", "Send Gift", "diplomatic_action", False,
    ("ducats",), "send_gift",
    "R74 native gift factory/effect contract; ducats is a positive 25-multiple")
ACTIONS["influence_nation"] = Action(
    "influence_nation", "影响国家", "Influence Nation", "diplomatic_action", False,
    (), "influence_nation",
    "R74 native influence object/config/effect contract; native chooses cost and duration")
ACTIONS["offer_vassalization"] = Action(
    "offer_vassalization", "提议附庸", "Offer Vassalization", "diplomatic_action", True,
    (), "vassalization", "R35 native vassalization inspection contract; query-only")
ACTIONS["cancel_vassalization"] = Action(
    "cancel_vassalization", "取消附庸关系", "Cancel Vassalization", "diplomatic_action", False,
    (), "vassalization", "R35 native vassalization inspection contract; query-only")

# Aggregate inbound proposals are exposed beside, rather than inside, the
# stable action catalog.  A Peace proposal may contain any of the 20 term
# records, so treating it as another ``peace_term`` would misstate the public
# range and the execution parameter contract.
INBOUND_ACTIONS = {
    "peace_offer": Action(
        "peace_offer", "外来议和提议", "Incoming Peace Offer",
        "inbound_diplomatic_action", True, ("proposal_id",), "peace_offer",
        "R44 native inbound Peace aggregate response contract"),
}
