#include <cstdio>
#include <cstdint>
#include <cstring>

#include "alliance-authority-ledger.h"
#include "alliance-execution-wire.h"

using bridge::alliance_authority::ActionFamily;
using bridge::alliance_authority::AllianceAuthorityLedger;
using bridge::alliance_authority::AlliancePayload;
using bridge::alliance_authority::Context;
using bridge::alliance_authority::ObjectRef;
using bridge::alliance_authority::Phase;
using bridge::alliance_execution_wire::ExecutionRequest;

static unsigned checks=0;
static unsigned failures=0;
static void check(bool value,const char* label) {
    ++checks;
    if (!value) { ++failures; std::printf("FAIL: %s\n",label); }
}

static AlliancePayload payload(std::uint64_t actor,std::uint64_t recipient,
    std::uint64_t variant) {
    AlliancePayload value{};
    value.actor10=actor;
    value.mirror18=actor;
    value.recipient20=recipient;
    value.date28=56459880;
    value.date2c=56459880;
    value.envoy30=0xffffffffu;
    value.state34=0;
    value.variant38=variant;
    value.proposal3c=0;
    value.family=ActionFamily::curry_favors;
    return value;
}

int main() {
    constexpr std::uint64_t actor=0x1000000000000001ull;
    constexpr std::uint64_t recipient=0x2000000000000002ull;
    check(static_cast<unsigned>(ActionFamily::curry_favors)==12u,
        "curry family value");

    AlliancePayload start=payload(actor,recipient,1);
    AllianceAuthorityLedger ledger(77);
    Context context{77,1000};
    auto seeded=ledger.seed(context,"curry-start",start,Phase::initiate,
        ObjectRef{0x500000,1},ObjectRef{0x600000,1},2000);
    check(seeded.result.ok(),"start seed accepted");

    AlliancePayload stop=payload(actor,recipient,0);
    auto stop_seed=ledger.seed(context,"curry-stop",stop,Phase::dissolve,
        ObjectRef{0x500100,1},ObjectRef{0x600100,1},2000);
    check(stop_seed.result.ok(),"stop seed accepted");

    AlliancePayload bad_accept=start;
    auto bad=ledger.seed(context,"curry-accept",bad_accept,Phase::accept,
        ObjectRef{0x500200,1},ObjectRef{0x600200,1},2000);
    check(bad.result.code==bridge::alliance_authority::ErrorCode::invalid_payload,
        "accept rejected for one-sided task");

    ExecutionRequest request{};
    constexpr char wire[]=
        "v1|curry-start|1234-1abc|1100000000|56459880|curry_favors|FRA|SAV|initiate\n";
    auto parsed=bridge::alliance_execution_wire::parse_request(
        wire,sizeof(wire)-1,request);
    check(parsed.ok(),"start wire accepted");
    check(std::strcmp(request.action_id,"curry_favors")==0,
        "start action preserved");

    ExecutionRequest stop_request{};
    constexpr char stop_wire[]=
        "v1|curry-stop|1234-1abc|1100000000|56459880|stop_curry_favors|FRA|SAV|initiate\n";
    auto stop_parsed=bridge::alliance_execution_wire::parse_request(
        stop_wire,sizeof(stop_wire)-1,stop_request);
    check(stop_parsed.ok(),"stop wire accepted");
    check(std::strcmp(stop_request.action_id,"stop_curry_favors")==0,
        "stop action preserved");

    constexpr char unknown_wire[]=
        "v1|curry-bad|1234-1abc|1100000000|56459880|curry_favors_bad|FRA|SAV|initiate\n";
    ExecutionRequest unknown{};
    auto unknown_parsed=bridge::alliance_execution_wire::parse_request(
        unknown_wire,sizeof(unknown_wire)-1,unknown);
    check(unknown_parsed.error==bridge::alliance_execution_wire::ParseError::invalid_action,
        "unknown curry action rejected");

    std::printf("curry_favors_contract_checks:%u failures:%u\n",checks,failures);
    return failures ? 1 : 0;
}
