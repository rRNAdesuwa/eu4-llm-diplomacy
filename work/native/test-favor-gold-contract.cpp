#include <cstdint>
#include <cstdio>
#include <cstring>

#include "alliance-authority-ledger.h"
#include "alliance-execution-wire.h"
#include "alliance-inbound-response-wire.h"

using bridge::alliance_authority::AllianceAuthorityLedger;
using bridge::alliance_authority::AlliancePayload;
using bridge::alliance_authority::ActionFamily;
using bridge::alliance_authority::Context;
using bridge::alliance_authority::ErrorCode;
using bridge::alliance_authority::ObjectRef;
using bridge::alliance_authority::Phase;
using bridge::alliance_execution_wire::ExecutionRequest;
using bridge::alliance_execution_wire::ParseError;

static unsigned checks=0;
static unsigned failures=0;

static void check(bool value,const char* name) {
    ++checks;
    if (!value) {
        ++failures;
        std::printf("fixture_check_failed:%s\n",name);
    }
}

static AlliancePayload favor_payload(Phase phase) {
    AlliancePayload payload{};
    payload.actor10=0x100000000ULL+0x415246u;
    payload.mirror18=payload.actor10;
    payload.recipient20=0x200000000ULL+0x504150u;
    payload.date28=56553384u;
    payload.date2c=56553384u;
    payload.envoy30=0;
    payload.state34=phase==Phase::accept?2u:phase==Phase::reject?1u:0u;
    payload.variant38=1u;
    payload.proposal3c=0x71u;
    payload.family=ActionFamily::favor_gold;
    return payload;
}

static void test_authority_phases() {
    check(static_cast<unsigned>(ActionFamily::favor_gold)==11u,
        "favor_family_numeric_id");
    AllianceAuthorityLedger ledger(0x7100u);
    const Context context{0x7100u,10u};
    for (const Phase phase: {Phase::initiate,Phase::accept,Phase::reject}) {
        const AlliancePayload payload=favor_payload(phase);
        const std::uint64_t salt=static_cast<unsigned>(phase)+1u;
        const char* request_id=phase==Phase::initiate?"favor-gold-init":
            phase==Phase::accept?"favor-gold-accept":"favor-gold-reject";
        const ObjectRef wrapper{0x100000u+salt*0x100u,1u+salt};
        const ObjectRef action{0x200000u+salt*0x100u,11u+salt};
        const auto result=ledger.seed(context,request_id,payload,phase,
            wrapper,action,100u);
        check(result.result.ok(),phase==Phase::initiate?"favor_initiate_valid":
            phase==Phase::accept?"favor_accept_valid":"favor_reject_valid");
    }
    const auto dissolve=ledger.seed(context,"favor-gold-dissolve",
        favor_payload(Phase::dissolve),Phase::dissolve,
        ObjectRef{0x310000u,1u},ObjectRef{0x320000u,2u},100u);
    check(dissolve.result.code==ErrorCode::invalid_payload,
        "favor_dissolve_rejected");

    AlliancePayload invalid=favor_payload(Phase::initiate);
    invalid.extra60=1u;
    check(ledger.seed(context,"favor-extra",invalid,Phase::initiate,
        ObjectRef{0x330000u,1u},ObjectRef{0x340000u,2u},100u).result.code
            ==ErrorCode::invalid_payload,"favor_extra_rejected");
    invalid=favor_payload(Phase::initiate);
    invalid.parameter40=1;
    check(ledger.seed(context,"favor-parameter",invalid,Phase::initiate,
        ObjectRef{0x350000u,1u},ObjectRef{0x360000u,2u},100u).result.code
            ==ErrorCode::invalid_payload,"favor_parameter_rejected");
    invalid=favor_payload(Phase::initiate);
    invalid.variant38=0;
    check(ledger.seed(context,"favor-variant",invalid,Phase::initiate,
        ObjectRef{0x370000u,1u},ObjectRef{0x380000u,2u},100u).result.code
            ==ErrorCode::invalid_payload,"favor_variant_rejected");
}

static void test_execution_wire_action() {
    constexpr char wire[]=
        "v1|favor_req|1234-1abc|1100000000|56553384|trade_favors_for_gold|FRA|PAP|initiate\n";
    ExecutionRequest request{};
    const auto parsed=bridge::alliance_execution_wire::parse_request(
        wire,sizeof(wire)-1,request);
    check(parsed.ok(),"favor_wire_accepted");
    check(std::strcmp(request.action_id,"trade_favors_for_gold")==0,
        "favor_wire_action_copied");
    check(request.insult_id==-1,"favor_wire_no_insult_parameter");
    constexpr char response[]=
        "v1|favor_resp|1234-1abc|1100000000|56553384|trade_favors_for_gold|FRA|PAP|accept\n";
    ExecutionRequest rejected{};
    check(bridge::alliance_execution_wire::parse_request(
        response,sizeof(response)-1,rejected).error==ParseError::invalid_phase,
        "favor_wire_response_phase_rejected");
}

static void test_inbound_wire_action() {
    constexpr char inspection_wire[]=
        "v1|favor_inspection|1234-1abc|1100000000|56553384|trade_favors_for_gold|SAV|FRA|accept|47\n";
    bridge::alliance_inbound_response_wire::InspectionRequest inspection{};
    const auto inspection_result=bridge::alliance_inbound_response_wire::parse_inspection_request(
        inspection_wire,sizeof(inspection_wire)-1,inspection);
    check(inspection_result.ok(),"favor_inbound_inspection_accepted");
    check(std::strcmp(inspection.action_id,"trade_favors_for_gold")==0,
        "favor_inbound_inspection_action_copied");
    constexpr char response_wire[]=
        "v1|favor_response|1234-1abc|1100000000|56553384|trade_favors_for_gold|SAV|FRA|reject|47\n";
    bridge::alliance_inbound_response_wire::ResponseRequest response{};
    const auto response_result=bridge::alliance_inbound_response_wire::parse_response_request(
        response_wire,sizeof(response_wire)-1,response);
    check(response_result.ok(),"favor_inbound_response_accepted");
    check(std::strcmp(response.decision,"reject")==0,"favor_inbound_response_decision_copied");
}

int main() {
    test_authority_phases();
    test_execution_wire_action();
    test_inbound_wire_action();
    std::printf("favor_gold_contract_checks:%u failures:%u\n",checks,failures);
    return failures?1:0;
}
