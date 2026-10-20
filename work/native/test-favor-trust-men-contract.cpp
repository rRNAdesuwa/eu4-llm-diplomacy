#include <cstdint>
#include <cstdio>
#include <cstring>

#include "alliance-authority-ledger.h"
#include "alliance-execution-wire.h"
#include "alliance-inbound-inspection-event.h"
#include "alliance-inbound-response-wire.h"

using bridge::alliance_authority::ActionFamily;
using bridge::alliance_authority::AllianceAuthorityLedger;
using bridge::alliance_authority::AlliancePayload;
using bridge::alliance_authority::Context;
using bridge::alliance_authority::ErrorCode;
using bridge::alliance_authority::ObjectRef;
using bridge::alliance_authority::Phase;

static unsigned checks=0;
static unsigned failures=0;

static void check(bool value,const char* label) {
    ++checks;
    if (!value) {
        ++failures;
        std::printf("favor_trade_contract_failed:%s\n",label);
    }
}

static AlliancePayload payload(ActionFamily family,Phase phase) {
    AlliancePayload value{};
    value.actor10=0x100000000ULL+0x465241u;
    value.mirror18=value.actor10;
    value.recipient20=0x200000000ULL+0x534156u;
    value.date28=56553384u;
    value.date2c=56553384u;
    value.state34=phase==Phase::accept?2u:phase==Phase::reject?1u:0u;
    value.variant38=1u;
    value.proposal3c=0x73u;
    value.family=family;
    if (family==ActionFamily::favor_trust) {
        value.favor_cost40=2000;
        value.favor_amount44=40;
    }
    return value;
}

static void test_authority() {
    check(static_cast<unsigned>(ActionFamily::favor_trust)==13u,
        "trust_family_numeric_id");
    check(static_cast<unsigned>(ActionFamily::favor_men)==14u,
        "men_family_numeric_id");
    AllianceAuthorityLedger ledger(0x7300u);
    const Context context{0x7300u,10u};
    unsigned serial=0;
    for (const ActionFamily family: {ActionFamily::favor_trust,ActionFamily::favor_men}) {
        for (const Phase phase: {Phase::initiate,Phase::accept,Phase::reject}) {
            AlliancePayload value=payload(family,phase);
            const char* name=family==ActionFamily::favor_trust?"trust":"men";
            const char* phase_name=phase==Phase::initiate?"init":
                phase==Phase::accept?"accept":"reject";
            char request_id[32]{};
            std::snprintf(request_id,sizeof(request_id),"favor-%s-%s",name,phase_name);
            const std::uint64_t salt=++serial;
            auto result=ledger.seed(context,request_id,value,phase,
                ObjectRef{0x500000u+salt*0x100u,1u+salt},
                ObjectRef{0x600000u+salt*0x100u,2u+salt},100u);
            check(result.result.ok(),request_id);
        }
    }
    AlliancePayload bad=payload(ActionFamily::favor_trust,Phase::initiate);
    bad.favor_amount44=-1;
    check(ledger.seed(context,"trust-negative-amount",bad,Phase::initiate,
        ObjectRef{0x710000u,1u},ObjectRef{0x720000u,1u},100u).result.code
            ==ErrorCode::invalid_payload,"trust_negative_amount_rejected");
    bad=payload(ActionFamily::favor_men,Phase::initiate);
    bad.favor_cost40=1;
    check(ledger.seed(context,"men_action_cost",bad,Phase::initiate,
        ObjectRef{0x730000u,1u},ObjectRef{0x740000u,1u},100u).result.code
            ==ErrorCode::invalid_payload,"men_action_cost_rejected");
}

static void test_action_wires() {
    for (const char* action: {"trade_favors_for_trust","trade_favors_for_men"}) {
        char wire[180]{};
        std::snprintf(wire,sizeof(wire),
            "v1|favor-trade|1234-1abc|1100000000|56553384|%s|FRA|SAV|initiate\n",action);
        bridge::alliance_execution_wire::ExecutionRequest request{};
        auto result=bridge::alliance_execution_wire::parse_request(
            wire,std::strlen(wire),request);
        check(result.ok(),action);
        check(std::strcmp(request.action_id,action)==0,"action_id_preserved");
    }
    constexpr char inspection[]=
        "v1|trust-inspection|1234-1abc|1100000000|56553384|trade_favors_for_trust|SAV|FRA|accept|73\n";
    bridge::alliance_inbound_response_wire::InspectionRequest inspection_request{};
    check(bridge::alliance_inbound_response_wire::parse_inspection_request(
        inspection,sizeof(inspection)-1,inspection_request).ok(),
        "trust_inspection_wire");
    constexpr char response[]=
        "v1|men-response|1234-1abc|1100000000|56553384|trade_favors_for_men|SAV|FRA|reject|74\n";
    bridge::alliance_inbound_response_wire::ResponseRequest response_request{};
    check(bridge::alliance_inbound_response_wire::parse_response_request(
        response,sizeof(response)-1,response_request).ok(),
        "men_response_wire");
}

static void test_inspection_shape(const char* action,bool trust) {
    char wire[220]{};
    std::snprintf(wire,sizeof(wire),
        "v1|favor-format|1234-1abc|1100000000|56553384|%s|SAV|FRA|accept|75\n",action);
    bridge::alliance_inbound_response_wire::InspectionRequest request{};
    check(bridge::alliance_inbound_response_wire::parse_inspection_request(
        wire,std::strlen(wire),request).ok(),"formatter_request_wire");
    bridge::alliance_inbound_inspection_event::Observation observed{};
    observed.pending_active=true;
    observed.decision_country_verified=true;
    observed.native_validity=true;
    observed.response_rules_complete=true;
    observed.favor_context_complete=true;
    observed.favor_amount_readable=true;
    observed.favor_amount_raw=trust?40:3;
    observed.favor_cost_raw=trust?2000:1000;
    observed.favor_favors_available_raw=8000;
    if (trust) {
        observed.favor_trust=true;
        observed.favor_recipient_trust_raw=27;
    } else {
        observed.favor_men=true;
        observed.favor_actor_manpower_raw=1200;
        observed.favor_recipient_manpower_raw=800;
    }
    char output[2400]{};
    check(bridge::alliance_inbound_inspection_event::format(
        output,sizeof(output),request,observed),"formatter_output");
    check(std::strstr(output,trust?"\"kind\":\"trust\"":"\"kind\":\"men\"")!=nullptr,
        "formatter_kind");
    check(std::strstr(output,"\"family\":\"favor_trade\"")!=nullptr,
        "formatter_family");
    check(std::strstr(output,"\"complete\":true")!=nullptr,
        "formatter_complete");
    check(std::strstr(output,"\"alliance_before\"")==nullptr,
        "formatter_no_alliance_state");
}

int main() {
    test_authority();
    test_action_wires();
    test_inspection_shape("trade_favors_for_trust",true);
    test_inspection_shape("trade_favors_for_men",false);
    std::printf("favor_trust_men_contract_checks:%u failures:%u\n",checks,failures);
    return failures?1:0;
}
