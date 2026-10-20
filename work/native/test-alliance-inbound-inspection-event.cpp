#include <cstdio>
#include <cstring>
#include "alliance-inbound-inspection-event.h"

int main() {
    constexpr char wire[]="v1|formatter_case|1234-abcdef|100000000|56459880|offer_alliance|SAV|FRA|accept|47\n";
    bridge::alliance_inbound_response_wire::InspectionRequest request{};
    if (!bridge::alliance_inbound_response_wire::parse_inspection_request(
            wire,sizeof(wire)-1,request).ok()) return 1;
    bridge::alliance_inbound_inspection_event::Observation observed{};
    observed.pending_active=true;
    observed.decision_country_verified=true;
    observed.native_validity=true;
    observed.response_rules_complete=true;
    observed.alliance_readable=true;
    observed.date28=56459880;
    observed.date2c=56459880;
    observed.envoy30=7;
    observed.variant38=1;
    observed.proposal3c=15;
    char event[2400]{};
    if (!bridge::alliance_inbound_inspection_event::format(event,sizeof(event),request,observed)) return 2;
    if (!std::strstr(event,"\"action_id\":\"offer_alliance\"")
        || !std::strstr(event,"\"family\":\"alliance\"")
        || !std::strstr(event,"\"extra60\":0")
        || !std::strstr(event,"\"alliance_before\":false")
        || !std::strstr(event,"\"native_current_alliance\":false")
        || !std::strstr(event,"\"native_current_alliance_readable\":true")) return 4;
    std::fputs(event,stdout);
    constexpr char royal_wire[]="v1|royal_formatter|1234-abcdef|100000000|56459880|offer_royal_marriage|SAV|FRA|reject|48\n";
    if (!bridge::alliance_inbound_response_wire::parse_inspection_request(
            royal_wire,sizeof(royal_wire)-1,request).ok()) return 5;
    observed={};
    observed.royal_marriage=true;
    observed.extra60=1;
    observed.pending_active=true;
    observed.alliance_before=true;
    observed.alliance_readable=true;
    observed.reason="ROYAL_PROPOSAL_NOT_ACTIVE";
    if (!bridge::alliance_inbound_inspection_event::format(event,sizeof(event),request,observed)) return 3;
    if (!std::strstr(event,"\"action_id\":\"offer_royal_marriage\"")
        || !std::strstr(event,"\"family\":\"royal_marriage\"")
        || !std::strstr(event,"\"extra60\":1")
        || !std::strstr(event,"\"royal_marriage_before\":true")
        || !std::strstr(event,"\"native_current_royal_marriage\":true")
        || !std::strstr(event,"\"native_current_royal_marriage_readable\":true")
        || std::strstr(event,"\"alliance_before\"")
        || std::strstr(event,"\"native_current_alliance\"")) return 6;
    std::fputs(event,stdout);

    constexpr char support_wire[]="v1|support_formatter|1234-abcdef|100000000|56459880|support_independence|SAV|FRA|accept|49\n";
    if (!bridge::alliance_inbound_response_wire::parse_inspection_request(
            support_wire,sizeof(support_wire)-1,request).ok()) return 7;
    observed={};
    observed.support_independence=true;
    observed.pending_active=true;
    observed.decision_country_verified=true;
    observed.native_validity=true;
    observed.response_rules_complete=true;
    observed.alliance_before=true;
    observed.alliance_readable=true;
    observed.reason="SUPPORT_PROPOSAL_ACTIVE";
    if (!bridge::alliance_inbound_inspection_event::format(event,sizeof(event),
            request,observed)) return 8;
    if (!std::strstr(event,"\"action_id\":\"support_independence\"")
        || !std::strstr(event,"\"family\":\"support_independence\"")
        || !std::strstr(event,"\"support_independence_before\":true")
        || !std::strstr(event,"\"native_current_support_independence\":true")
        || !std::strstr(event,"\"native_current_support_independence_readable\":true")
        || std::strstr(event,"\"alliance_before\"")
        || std::strstr(event,"\"native_current_alliance\"")
        || std::strstr(event,"\"royal_marriage_before\"")) return 9;
    std::fputs(event,stdout);

    constexpr char vassalization_wire[]="v1|vassal_formatter|1234-abcdef|100000000|56459880|offer_vassalization|SAV|FRA|accept|50\n";
    if (!bridge::alliance_inbound_response_wire::parse_inspection_request(
            vassalization_wire,sizeof(vassalization_wire)-1,request).ok()) return 13;
    observed={};
    observed.vassalization=true;
    observed.pending_active=true;
    observed.decision_country_verified=true;
    observed.native_validity=true;
    observed.response_rules_complete=true;
    observed.alliance_before=true;
    observed.alliance_readable=true;
    observed.reason="VASSALIZATION_PROPOSAL_ACTIVE";
    if (!bridge::alliance_inbound_inspection_event::format(event,sizeof(event),
            request,observed)) return 14;
    if (!std::strstr(event,"\"action_id\":\"offer_vassalization\"")
        || !std::strstr(event,"\"family\":\"vassalization\"")
        || !std::strstr(event,"\"vassalization_before\":true")
        || !std::strstr(event,"\"native_current_vassalization\":true")
        || !std::strstr(event,"\"native_current_vassalization_readable\":true")
        || std::strstr(event,"\"alliance_before\"")
        || std::strstr(event,"\"native_current_alliance\"")
        || std::strstr(event,"\"royal_marriage_before\"")
        || std::strstr(event,"\"support_independence_before\"")) return 15;
    std::fputs(event,stdout);

    constexpr char military_wire[]="v1|military_formatter|1234-abcdef|100000000|56459880|ask_military_access|SAV|FRA|accept|50\n";
    if (!bridge::alliance_inbound_response_wire::parse_inspection_request(
            military_wire,sizeof(military_wire)-1,request).ok()) return 10;
    observed={};
    observed.military_access=true;
    observed.pending_active=true;
    observed.decision_country_verified=true;
    observed.native_validity=true;
    observed.response_rules_complete=true;
    observed.alliance_before=true;
    observed.alliance_readable=true;
    observed.reason="MILITARY_ACCESS_ACTIVE";
    if (!bridge::alliance_inbound_inspection_event::format(event,sizeof(event),
            request,observed)) return 11;
    if (!std::strstr(event,"\"action_id\":\"ask_military_access\"")
        || !std::strstr(event,"\"family\":\"military_access\"")
        || !std::strstr(event,"\"military_access_active\":true")
        || !std::strstr(event,"\"military_access_state_verified\":true")
        || std::strstr(event,"\"alliance_before\"")
        || std::strstr(event,"\"native_current_alliance\"")
        || std::strstr(event,"\"support_independence_before\"")) return 12;
    std::fputs(event,stdout);

    constexpr char favor_wire[]="v1|favor_formatter|1234-abcdef|100000000|56459880|trade_favors_for_gold|SAV|FRA|accept|51\n";
    if (!bridge::alliance_inbound_response_wire::parse_inspection_request(
            favor_wire,sizeof(favor_wire)-1,request).ok()) return 19;
    observed={};
    observed.favor_gold=true;
    observed.pending_active=true;
    observed.decision_country_verified=true;
    observed.native_validity=true;
    observed.response_rules_complete=true;
    observed.favor_context_complete=true;
    observed.favor_amount_readable=true;
    observed.favor_amount_raw=10500;
    observed.favor_cost_raw=2000;
    observed.favor_favors_available_raw=7000;
    observed.favor_actor_treasury_raw=50000;
    observed.favor_recipient_treasury_raw=125000;
    observed.reason="FAVOR_PROPOSAL_ACTIVE";
    if (!bridge::alliance_inbound_inspection_event::format(event,sizeof(event),
            request,observed)) return 20;
    if (!std::strstr(event,"\"action_id\":\"trade_favors_for_gold\"")
        || !std::strstr(event,"\"family\":\"favor_trade\"")
        || !std::strstr(event,"\"favor_trade\":{\"kind\":\"gold\"")
        || !std::strstr(event,"\"amount_raw\":10500")
        || !std::strstr(event,"\"favor_cost_raw\":2000")
        || !std::strstr(event,"\"recipient_treasury_raw\":125000")
        || !std::strstr(event,"\"complete\":true")
        || std::strstr(event,"\"alliance_before\"")) return 21;
    std::fputs(event,stdout);

    constexpr char peace_wire[]="v1|peace_formatter|1234-abcdef|100000000|56459880|peace_offer|SAV|FRA|accept|52\n";
    if (!bridge::alliance_inbound_response_wire::parse_inspection_request(
            peace_wire,sizeof(peace_wire)-1,request).ok()) return 16;
    observed={};
    observed.peace_offer=true;
    observed.pending_active=true;
    observed.decision_country_verified=true;
    observed.native_validity=true;
    observed.response_rules_complete=true;
    observed.war_active=true;
    observed.war_readable=true;
    observed.war_before=false;
    observed.native_current_war=true;
    observed.native_current_war_readable=true;
    observed.peace_payload_complete=true;
    observed.selected_terms_complete=true;
    observed.term_count=83;
    observed.selected_term_count=1;
    observed.peace_context_json=
        "{\"war_id\":123,\"direction\":\"demand\",\"terms\":[],\"complete\":true}";
    observed.reason="PEACE_OFFER_ACTIVE";
    if (!bridge::alliance_inbound_inspection_event::format(event,sizeof(event),
            request,observed)) return 17;
    if (!std::strstr(event,"\"action_id\":\"peace_offer\"")
        || !std::strstr(event,"\"family\":\"peace\"")
        || !std::strstr(event,"\"war_active\":true")
        || !std::strstr(event,"\"war_readable\":true")
        || !std::strstr(event,"\"war_before\":false")
        || !std::strstr(event,"\"native_current_war\":true")
        || !std::strstr(event,"\"peace_payload_complete\":true")
        || !std::strstr(event,"\"selected_terms_complete\":true")
        || !std::strstr(event,"\"term_count\":83")
        || !std::strstr(event,"\"selected_term_count\":1")
        || !std::strstr(event,"\"peace_context\":{\"war_id\":123")
        || std::strstr(event,"\"alliance_before\"")) return 18;
    std::fputs(event,stdout);

    return 0;
}
