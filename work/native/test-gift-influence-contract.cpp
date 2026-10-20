#include <cstdio>
#include <cstring>

#include "alliance-authority-ledger.h"
#include "alliance-execution-wire.h"

using bridge::alliance_authority::ActionFamily;
using bridge::alliance_authority::AllianceAuthorityLedger;
using bridge::alliance_authority::AlliancePayload;
using bridge::alliance_authority::Context;
using bridge::alliance_authority::ErrorCode;
using bridge::alliance_authority::ObjectRef;
using bridge::alliance_authority::Phase;

static unsigned checks=0;
static unsigned failures=0;

static void check(bool value,const char* name) {
    ++checks;
    if (!value) {
        ++failures;
        std::printf("gift_influence_contract_failed:%s\n",name);
    }
}

static AlliancePayload payload(ActionFamily family) {
    AlliancePayload value{};
    value.actor10=0x100000000ULL+0x415246u;
    value.mirror18=value.actor10;
    value.recipient20=0x200000000ULL+0x504150u;
    value.date28=56553384u;
    value.date2c=56553384u;
    value.variant38=1u;
    value.family=family;
    if (family==ActionFamily::gift) value.parameter40=25000;
    return value;
}

static void test_authority_shapes() {
    check(static_cast<unsigned>(ActionFamily::gift)==15u,"gift_family_numeric_id");
    check(static_cast<unsigned>(ActionFamily::influence)==16u,"influence_family_numeric_id");
    AllianceAuthorityLedger ledger(0x7400u);
    const Context context{0x7400u,10u};
    for (const ActionFamily family: {ActionFamily::gift,ActionFamily::influence}) {
        const char* name=family==ActionFamily::gift?"gift":"influence";
        const auto result=ledger.seed(context,name,payload(family),Phase::initiate,
            ObjectRef{0x500000u+checks*0x100u,1u},
            ObjectRef{0x600000u+checks*0x100u,2u},100u);
        check(result.result.ok(),name);
        AlliancePayload invalid=payload(family);
        invalid.variant38=0;
        check(ledger.seed(context,"invalid-variant",invalid,Phase::initiate,
            ObjectRef{0x710000u+checks*0x100u,3u},
            ObjectRef{0x720000u+checks*0x100u,4u},100u).result.code
                ==ErrorCode::invalid_payload,"variant_rejected");
    }
    AlliancePayload bad_gift=payload(ActionFamily::gift);
    bad_gift.parameter40=30000;
    check(ledger.seed(context,"bad-gift-step",bad_gift,Phase::initiate,
        ObjectRef{0x730000u,5u},ObjectRef{0x740000u,6u},100u).result.code
            ==ErrorCode::invalid_payload,"gift_step_rejected");
    check(ledger.seed(context,"gift-dissolve",payload(ActionFamily::gift),Phase::dissolve,
        ObjectRef{0x750000u,7u},ObjectRef{0x760000u,8u},100u).result.code
            ==ErrorCode::invalid_payload,"gift_dissolve_rejected");
}

static void test_execution_wires() {
    using bridge::alliance_execution_wire::ExecutionRequest;
    const char* gift_wire=
        "EU4DIP_EXECUTE_GIFT|v1|gift-wire|1234-1abc|1100000000|56553384|send_gift|FRA|PAP|initiate|25|25000\n";
    ExecutionRequest gift{};
    const auto gift_result=bridge::alliance_execution_wire::parse_request(
        gift_wire,std::strlen(gift_wire),gift);
    check(gift_result.ok(),"gift_envelope_parse");
    check(gift.gift_ducats==25 && gift.gift_amount_raw==25000,"gift_amount_binding");
    const char* influence_wire=
        "EU4DIP_EXECUTE_INFLUENCE|v1|influence-wire|1234-1abc|1100000000|56553384|influence_nation|FRA|PAP|initiate\n";
    ExecutionRequest influence{};
    const auto influence_result=bridge::alliance_execution_wire::parse_request(
        influence_wire,std::strlen(influence_wire),influence);
    check(influence_result.ok(),"influence_envelope_parse");
    check(std::strcmp(influence.action_id,"influence_nation")==0,
        "influence_action_binding");
    const char* invalid_amount=
        "EU4DIP_EXECUTE_GIFT|v1|bad-gift|1234-1abc|1100000000|56553384|send_gift|FRA|PAP|initiate|30|30000\n";
    ExecutionRequest ignored{};
    check(!bridge::alliance_execution_wire::parse_request(
        invalid_amount,std::strlen(invalid_amount),ignored).ok(),
        "gift_step_wire_rejected");
}

int main() {
    test_authority_shapes();
    test_execution_wires();
    std::printf("gift_influence_contract_checks:%u failures:%u\n",checks,failures);
    return failures?1:0;
}
