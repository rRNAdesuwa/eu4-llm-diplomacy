"""Stable bridge semantics; identification and runtime support are separate.

These names do not assert a native class, vtable or rule implementation. Native
identifiers are populated only from independently reviewed evidence.
"""
from __future__ import annotations

from dataclasses import dataclass


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
        # it is kept outside ``ACTIONS`` so the stable 21+19 catalog count is
        # unchanged.
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
                    "exact_length": 1,
                    "path": "peace_context.terms",
                },
                "peace_context.terms[0].action_id": {
                    "status": "required_for_selected",
                    "type": "string",
                    "const": "demand_ducats",
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
            ]
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
                    "max_length": 1,
                    "path": "peace_context.terms",
                },
                "peace_context.terms[0].action_id": {
                    "status": "required_for_selected",
                    "type": "string",
                    "const": "cede_province",
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
            ]
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
    ("full_annexation", "完全吞并", "Full Annexation", ("annexed_country",)),
    ("return_core", "归还核心省份", "Return Core", ("province_ids", "core_owner")),
    ("release_nation", "释放国家", "Release Nation", ("released_country",)),
    ("revoke_core", "放弃核心", "Revoke Core", ("province_ids", "core_owner")),
    ("force_vassalization", "强迫附庸", "Force Vassalization", ("subject", "overlord")),
    ("form_personal_union", "建立共主邦联", "Form Personal Union", ("subject", "overlord")),
    ("release_subject", "释放附属国", "Release Subject", ("subject",)),
    ("transfer_subject", "转移附属国", "Transfer Subject", ("subject", "new_overlord")),
    ("grant_independence", "承认独立", "Grant Independence", ("subject",)),
    ("demand_ducats", "索取金钱", "Demand Ducats", ("amount", "payer", "claimant")),
    ("war_reparations", "战争赔款", "War Reparations", ("payer", "claimant")),
    ("transfer_trade_power", "转移贸易竞争力", "Transfer Trade Power", ("payer", "claimant")),
    ("annul_treaties", "取消条约", "Annul Treaties", ("country", "treaty_partners")),
    ("humiliate_rival", "羞辱宿敌", "Humiliate Rival", ("humiliated_country",)),
    ("show_strength", "展示霸权", "Show Strength", ("defeated_country",)),
    ("force_religion", "强制信仰", "Force Religion", ("converted_country",)),
    ("concede_defeat", "承认战败", "Concede Defeat", ("defeated_country",)),
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
ACTIONS["offer_vassalization"] = Action(
    "offer_vassalization", "提议附庸", "Offer Vassalization", "diplomatic_action", True,
    (), "vassalization", "R35 native vassalization inspection contract; query-only")
ACTIONS["cancel_vassalization"] = Action(
    "cancel_vassalization", "取消附庸关系", "Cancel Vassalization", "diplomatic_action", False,
    (), "vassalization", "R35 native vassalization inspection contract; query-only")

# Aggregate inbound proposals are exposed beside, rather than inside, the
# stable action catalog.  A Peace proposal may contain any of the 19 term
# records, so treating it as another ``peace_term`` would misstate the public
# range and the execution parameter contract.
INBOUND_ACTIONS = {
    "peace_offer": Action(
        "peace_offer", "外来议和提议", "Incoming Peace Offer",
        "inbound_diplomatic_action", True, ("proposal_id",), "peace_offer",
        "R44 native inbound Peace aggregate response contract"),
}
