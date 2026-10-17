#pragma once

#include <cstdio>
#include "alliance-inbound-response-wire.h"

namespace bridge::alliance_inbound_inspection_event {

struct Observation {
    bool pending_active=false;
    bool decision_country_verified=false;
    bool native_validity=false;
    bool response_rules_complete=false;
    bool alliance_before=false;
    bool alliance_readable=false;
    std::int32_t date28=0,date2c=0,envoy30=0,state34=0,proposal3c=0;
    unsigned variant38=0;
    const char* reason="none";
    bool royal_marriage=false;
    bool support_independence=false;
    bool military_access=false;
    bool vassalization=false;
    bool peace_offer=false;
    bool war_active=false;
    bool war_readable=false;
    bool war_before=false;
    bool native_current_war=false;
    bool native_current_war_readable=false;
    bool peace_payload_complete=false;
    bool selected_terms_complete=false;
    unsigned term_count=0;
    unsigned selected_term_count=0;
    const char* peace_context_json="null";
    unsigned char extra60=0;
};

// Request fields and reason codes are bounded ASCII from the wire parser or
// fixed native codes.  This formatter is shared with the cross-language test.
inline bool format(char* buffer,std::size_t capacity,
    const alliance_inbound_response_wire::InspectionRequest& request,
    const Observation& observed) noexcept {
    // Support, Vassalization, and Military Access are checked first so a malformed observation
    // carrying two family flags
    // flags still has one deterministic JSON family and key set.  Production
    // observation construction sets exactly one family flag.
    const char* family=observed.peace_offer
        ? "peace"
        : (observed.military_access
        ? "military_access"
        : (observed.support_independence
        ? "support_independence"
        : (observed.vassalization
        ? "vassalization"
        : (observed.royal_marriage?"royal_marriage":"alliance"))));
    if (observed.peace_offer) {
        const char* peace_context=(observed.peace_context_json
            && observed.peace_context_json[0])?observed.peace_context_json:"null";
        const int written=std::snprintf(buffer,capacity,
            "{\"event\":\"native_alliance_inbound_inspection\",\"query_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"%.23s\",\"family\":\"peace\",\"extra60\":%u,\"actor\":\"%.3s\",\"mirror\":\"%.3s\",\"recipient\":\"FRA\",\"phase\":\"%.6s\",\"native_proposal_id\":%llu,\"date_raw\":%d,\"pending_active\":%s,\"decision_country\":\"FRA\",\"decision_country_verified\":%s,\"native_validity\":%s,\"response_rules_complete\":%s,\"war_active\":%s,\"war_readable\":%s,\"war_before\":%s,\"native_current_war\":%s,\"native_current_war_readable\":%s,\"peace_payload_complete\":%s,\"selected_terms_complete\":%s,\"term_count\":%u,\"selected_term_count\":%u,\"peace_context\":%s,\"date28\":%d,\"date2c\":%d,\"envoy30\":%d,\"state34\":%d,\"variant38\":%u,\"token3c\":%u,\"requested_decision\":\"%.6s\",\"reason\":\"%.96s\"}\n",
            request.query_id,request.session_id,request.action_id,
            static_cast<unsigned>(observed.extra60),request.original_actor,
            request.original_actor,request.decision,
            static_cast<unsigned long long>(request.native_proposal_id),request.date_raw,
            observed.pending_active?"true":"false",
            observed.decision_country_verified?"true":"false",
            observed.native_validity?"true":"false",
            observed.response_rules_complete?"true":"false",
            observed.war_active?"true":"false",
            observed.war_readable?"true":"false",
            observed.war_before?"true":"false",
            observed.native_current_war?"true":"false",
            observed.native_current_war_readable?"true":"false",
            observed.peace_payload_complete?"true":"false",
            observed.selected_terms_complete?"true":"false",
            observed.term_count,observed.selected_term_count,peace_context,
            observed.date28,observed.date2c,observed.envoy30,observed.state34,
            observed.variant38,static_cast<unsigned>(observed.proposal3c),
            request.decision,observed.reason);
        return written>=0 && static_cast<std::size_t>(written)<capacity;
    }
    if (observed.military_access) {
        // The existing relation fields carry the native active and readable
        // values for this response-capable family.  Use dedicated JSON names
        // so callers never mistake them for Alliance/Royal current fields.
        const int written=std::snprintf(buffer,capacity,
            "{\"event\":\"native_alliance_inbound_inspection\",\"query_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"%.23s\",\"family\":\"%s\",\"extra60\":%u,\"actor\":\"%.3s\",\"mirror\":\"%.3s\",\"recipient\":\"FRA\",\"phase\":\"%.6s\",\"native_proposal_id\":%llu,\"date_raw\":%d,\"pending_active\":%s,\"decision_country\":\"FRA\",\"decision_country_verified\":%s,\"native_validity\":%s,\"response_rules_complete\":%s,\"military_access_active\":%s,\"military_access_state_verified\":%s,\"date28\":%d,\"date2c\":%d,\"envoy30\":%d,\"state34\":%d,\"variant38\":%u,\"token3c\":%u,\"requested_decision\":\"%.6s\",\"reason\":\"%.96s\"}\n",
            request.query_id,request.session_id,request.action_id,family,
            static_cast<unsigned>(observed.extra60),request.original_actor,request.original_actor,
            request.decision,static_cast<unsigned long long>(request.native_proposal_id),request.date_raw,
            observed.pending_active?"true":"false",observed.decision_country_verified?"true":"false",
            observed.native_validity?"true":"false",observed.response_rules_complete?"true":"false",
            observed.alliance_before?"true":"false",observed.alliance_readable?"true":"false",
            observed.date28,observed.date2c,observed.envoy30,observed.state34,observed.variant38,
            static_cast<unsigned>(observed.proposal3c),request.decision,observed.reason);
        return written>=0 && static_cast<std::size_t>(written)<capacity;
    }
    const char* before_key=observed.support_independence
        ? "support_independence_before"
        : (observed.vassalization
            ? "vassalization_before"
            : (observed.royal_marriage
                ? "royal_marriage_before":"alliance_before"));
    const char* current_key=observed.support_independence
        ? "native_current_support_independence"
        : (observed.vassalization
            ? "native_current_vassalization"
            : (observed.royal_marriage
                ? "native_current_royal_marriage":"native_current_alliance"));
    const char* readable_key=observed.support_independence
        ? "native_current_support_independence_readable"
        : (observed.vassalization
            ? "native_current_vassalization_readable"
            : (observed.royal_marriage
                ? "native_current_royal_marriage_readable"
                : "native_current_alliance_readable"));
    const int written=std::snprintf(buffer,capacity,
        "{\"event\":\"native_alliance_inbound_inspection\",\"query_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"%.23s\",\"family\":\"%s\",\"extra60\":%u,\"actor\":\"%.3s\",\"mirror\":\"%.3s\",\"recipient\":\"FRA\",\"phase\":\"%.6s\",\"native_proposal_id\":%llu,\"date_raw\":%d,\"pending_active\":%s,\"decision_country\":\"FRA\",\"decision_country_verified\":%s,\"native_validity\":%s,\"response_rules_complete\":%s,\"%s\":%s,\"%s\":%s,\"%s\":%s,\"date28\":%d,\"date2c\":%d,\"envoy30\":%d,\"state34\":%d,\"variant38\":%u,\"token3c\":%u,\"requested_decision\":\"%.6s\",\"reason\":\"%.96s\"}\n",
        request.query_id,request.session_id,request.action_id,family,
        static_cast<unsigned>(observed.extra60),request.original_actor,request.original_actor,
        request.decision,static_cast<unsigned long long>(request.native_proposal_id),request.date_raw,
        observed.pending_active?"true":"false",observed.decision_country_verified?"true":"false",
        observed.native_validity?"true":"false",observed.response_rules_complete?"true":"false",
        before_key,observed.alliance_before?"true":"false",
        current_key,observed.alliance_before?"true":"false",
        readable_key,observed.alliance_readable?"true":"false",observed.date28,observed.date2c,
        observed.envoy30,observed.state34,observed.variant38,
        static_cast<unsigned>(observed.proposal3c),request.decision,observed.reason);
    return written>=0 && static_cast<std::size_t>(written)<capacity;
}

} // namespace bridge::alliance_inbound_inspection_event
