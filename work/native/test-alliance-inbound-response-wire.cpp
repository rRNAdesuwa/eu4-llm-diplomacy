#include "alliance-inbound-response-wire.h"

#include <cstdio>
#include <cstring>
#include <limits>

namespace wire=bridge::alliance_inbound_response_wire;

static int failures=0;

static void check(bool condition,const char* label) {
    if (!condition) {
        std::printf("FAIL %s\n",label);
        ++failures;
    }
}

static const char* valid_wire() {
    return "v1|q_01|6248-1dd5bcf4df44308|1000000100|56459880|offer_alliance|SAV|FRA|accept|1\n";
}

static const char* valid_royal_wire() {
    return "v1|q_royal|6248-1dd5bcf4df44308|1000000100|56459880|offer_royal_marriage|SAV|FRA|reject|47\n";
}

static const char* valid_support_wire() {
    return "v1|q_support|6248-1dd5bcf4df44308|1000000100|56459880|support_independence|SAV|FRA|accept|49\n";
}

static const char* valid_military_access_wire() {
    return "v1|q_military|6248-1dd5bcf4df44308|1000000100|56459880|ask_military_access|SAV|FRA|accept|50\n";
}

static const char* valid_vassalization_wire() {
    return "v1|q_vassal|6248-1dd5bcf4df44308|1000000100|56459880|offer_vassalization|SAV|FRA|accept|51\n";
}

static const char* valid_peace_wire() {
    return "v1|q_peace|6248-1dd5bcf4df44308|1000000100|56459880|peace_offer|SAV|FRA|accept|52\n";
}

static void test_valid() {
    wire::InspectionRequest inspection{};
    wire::ParseResult parsed=wire::parse_inspection_request(
        valid_wire(),std::strlen(valid_wire()),inspection);
    check(parsed.ok(),"valid inspection");
    check(std::strcmp(inspection.query_id,"q_01")==0
        && std::strcmp(inspection.original_actor,"SAV")==0
        && std::strcmp(inspection.decision,"accept")==0
        && inspection.native_proposal_id==1,"inspection fields");
    wire::ResponseRequest response{};
    parsed=wire::parse_response_request(valid_wire(),std::strlen(valid_wire()),response);
    check(parsed.ok() && std::strcmp(response.request_id,"q_01")==0,
        "valid response");
}

static void test_cross_action_context() {
    wire::InspectionRequest inspection{};
    wire::ParseResult parsed=wire::parse_inspection_request(
        valid_royal_wire(),std::strlen(valid_royal_wire()),inspection);
    check(parsed.ok(),"valid Royal inspection");
    check(std::strcmp(inspection.query_id,"q_royal")==0
        && std::strcmp(inspection.session_id,"6248-1dd5bcf4df44308")==0
        && std::strcmp(inspection.action_id,"offer_royal_marriage")==0
        && std::strcmp(inspection.original_actor,"SAV")==0
        && std::strcmp(inspection.decision_country,"FRA")==0
        && std::strcmp(inspection.decision,"reject")==0
        && inspection.session_pid==6248
        && inspection.session_creation_filetime==0x1dd5bcf4df44308ull
        && inspection.expires_filetime==1000000100ull
        && inspection.date_raw==56459880
        && inspection.native_proposal_id==47,
        "Royal inspection preserves all context");
    wire::ResponseRequest response{};
    parsed=wire::parse_response_request(
        valid_royal_wire(),std::strlen(valid_royal_wire()),response);
    check(parsed.ok() && std::strcmp(response.request_id,"q_royal")==0
        && std::strcmp(response.action_id,"offer_royal_marriage")==0
        && std::strcmp(response.original_actor,"SAV")==0
        && std::strcmp(response.decision_country,"FRA")==0
        && std::strcmp(response.decision,"reject")==0
        && response.session_pid==6248
        && response.session_creation_filetime==0x1dd5bcf4df44308ull
        && response.expires_filetime==1000000100ull
        && response.date_raw==56459880
        && response.native_proposal_id==47,
        "Royal response preserves all context");
    check(wire::validate_context(inspection,"6248-1dd5bcf4df44308",
        1000000000ull,56459880).ok(),"Royal context valid");
}

static void test_support_action_context() {
    static_assert(sizeof(wire::InspectionRequest::action_id)==24,
        "inbound action storage remains 24 bytes");
    static_assert(sizeof("support_independence")==21,
        "support action is 20 characters plus NUL");
    wire::InspectionRequest inspection{};
    wire::ParseResult parsed=wire::parse_inspection_request(
        valid_support_wire(),std::strlen(valid_support_wire()),inspection);
    check(parsed.ok(),"valid Support Independence inspection");
    check(std::strcmp(inspection.action_id,"support_independence")==0
        && std::strcmp(inspection.original_actor,"SAV")==0
        && std::strcmp(inspection.decision_country,"FRA")==0
        && std::strcmp(inspection.decision,"accept")==0
        && inspection.native_proposal_id==49,
        "Support Independence inspection preserves family context");
    wire::ResponseRequest response{};
    parsed=wire::parse_response_request(valid_support_wire(),
        std::strlen(valid_support_wire()),response);
    check(parsed.ok()
        && std::strcmp(response.action_id,"support_independence")==0
        && std::strcmp(response.request_id,"q_support")==0
        && response.native_proposal_id==49,
        "Support Independence response preserves family context");
    check(wire::validate_context(inspection,"6248-1dd5bcf4df44308",
        1000000000ull,56459880).ok(),"Support Independence context valid");
}

static void test_military_access_action_context() {
    static_assert(sizeof(wire::InspectionRequest::action_id)==24,
        "inbound action storage remains 24 bytes");
    static_assert(sizeof("ask_military_access")==20,
        "military-access action is 19 characters plus NUL");
    wire::InspectionRequest inspection{};
    wire::ParseResult parsed=wire::parse_inspection_request(
        valid_military_access_wire(),std::strlen(valid_military_access_wire()),inspection);
    check(parsed.ok(),"valid Military Access inspection");
    check(std::strcmp(inspection.action_id,"ask_military_access")==0
        && std::strcmp(inspection.original_actor,"SAV")==0
        && std::strcmp(inspection.decision_country,"FRA")==0
        && std::strcmp(inspection.decision,"accept")==0
        && inspection.native_proposal_id==50,
        "Military Access inspection preserves family context");
    wire::ResponseRequest response{};
    parsed=wire::parse_response_request(valid_military_access_wire(),
        std::strlen(valid_military_access_wire()),response);
    check(parsed.ok()
        && std::strcmp(response.action_id,"ask_military_access")==0
        && std::strcmp(response.request_id,"q_military")==0
        && response.native_proposal_id==50,
        "Military Access response preserves family context");
    check(wire::validate_context(inspection,"6248-1dd5bcf4df44308",
        1000000000ull,56459880).ok(),"Military Access context valid");
}

static void test_vassalization_action_context() {
    static_assert(sizeof(wire::InspectionRequest::action_id)==24,
        "inbound action storage remains 24 bytes");
    static_assert(sizeof("offer_vassalization")==20,
        "vassalization action is 19 characters plus NUL");
    wire::InspectionRequest inspection{};
    const auto parsed=wire::parse_inspection_request(
        valid_vassalization_wire(),std::strlen(valid_vassalization_wire()),inspection);
    check(parsed.ok(),"valid Vassalization inspection");
    check(std::strcmp(inspection.action_id,"offer_vassalization")==0
        && std::strcmp(inspection.original_actor,"SAV")==0
        && std::strcmp(inspection.decision_country,"FRA")==0
        && std::strcmp(inspection.decision,"accept")==0
        && inspection.native_proposal_id==51,
        "Vassalization inspection preserves family context");
    wire::ResponseRequest response{};
    const auto response_parsed=wire::parse_response_request(
        valid_vassalization_wire(),std::strlen(valid_vassalization_wire()),response);
    check(response_parsed.ok()
        && std::strcmp(response.action_id,"offer_vassalization")==0
        && std::strcmp(response.request_id,"q_vassal")==0
        && response.native_proposal_id==51,
        "Vassalization response preserves family context");
    check(wire::validate_context(inspection,"6248-1dd5bcf4df44308",
        1000000000ull,56459880).ok(),"Vassalization context valid");
}

static void test_peace_action_context() {
    static_assert(sizeof(wire::InspectionRequest::action_id)==24,
        "inbound action storage remains 24 bytes");
    wire::InspectionRequest inspection{};
    const auto parsed=wire::parse_inspection_request(
        valid_peace_wire(),std::strlen(valid_peace_wire()),inspection);
    check(parsed.ok(),"valid Peace inspection");
    check(std::strcmp(inspection.action_id,"peace_offer")==0
        && std::strcmp(inspection.original_actor,"SAV")==0
        && std::strcmp(inspection.decision_country,"FRA")==0
        && std::strcmp(inspection.decision,"accept")==0
        && inspection.native_proposal_id==52,
        "Peace inspection preserves family context");
    wire::ResponseRequest response{};
    const auto response_parsed=wire::parse_response_request(
        valid_peace_wire(),std::strlen(valid_peace_wire()),response);
    check(response_parsed.ok()
        && std::strcmp(response.action_id,"peace_offer")==0
        && std::strcmp(response.request_id,"q_peace")==0
        && response.native_proposal_id==52,
        "Peace response preserves family context");
    check(wire::validate_context(inspection,"6248-1dd5bcf4df44308",
        1000000000ull,56459880).ok(),"Peace context valid");
}

static void test_negative() {
    wire::InspectionRequest output{};
    const char* cases[]={
        "v1|bad id|6248-1dd5bcf4df44308|1000000100|56459880|offer_alliance|SAV|FRA|accept|1\n",
        "v1|q|6248-1dd5bcf4df44308|1000000100|56459880|offer_alliance|sav|FRA|accept|1\n",
        "v1|q|6248-1dd5bcf4df44308|1000000100|56459880|offer_alliance|SAV|POR|accept|1\n",
        "v1|q|6248-1dd5bcf4df44308|1000000100|56459880|offer_alliance|SAV|FRA|maybe|1\n",
        "v1|q|6248-1dd5bcf4df44308|1000000100|56459880|offer_alliance|SAV|FRA|accept|0\n",
        "v1|q|6248-1dd5bcf4df44308|1000000100|56459880|support_independenc|SAV|FRA|accept|1\n",
        "v1|q|6248-1dd5bcf4df44308|1000000100|56459880|ask_military_acces|SAV|FRA|accept|1\n",
        "v1|q|6248-1dd5bcf4df44308|1000000100|56459880|offer_vassalizatio|SAV|FRA|accept|1\n",
        "v1|q|6248-1dd5bcf4df44308|18446744073709551616|56459880|offer_alliance|SAV|FRA|accept|1\n",
        "v1|q|6248-1dd5bcf4df44308|1000000100|56459880|offer_alliance|SAV|FRA|accept|1\r\n",
        "v1|q|6248-1dd5bcf4df44308|1000000100|56459880|offer_alliance|SAV|FRA|accept|1",
        "v1|q|6248-1dd5bcf4df44308|1000000100|56459880|offer_alliance|SAV|FRA|accept|1|extra\n",
    };
    for (const char* value:cases)
        check(!wire::parse_inspection_request(value,std::strlen(value),output).ok(),
            "negative wire");
    char embedded[128]{};
    const char* base=valid_wire();
    std::size_t length=std::strlen(base);
    std::memcpy(embedded,base,length);
    embedded[5]=0;
    check(!wire::parse_inspection_request(embedded,length,output).ok(),"embedded nul");
}

static void test_context() {
    wire::InspectionRequest request{};
    check(wire::parse_inspection_request(valid_wire(),std::strlen(valid_wire()),request).ok(),
        "context setup");
    const std::uint64_t now=1000000000ull;
    wire::ContextResult result=wire::validate_context(request,
        "6248-1dd5bcf4df44308",now,56459880);
    check(result.ok(),"context valid");
    result=wire::validate_context(request,"6248-aaaaaaaaaaaaaaaa",now,56459880);
    check(result.error==wire::ContextError::session_mismatch,"context session");
    request.expires_filetime=now;
    result=wire::validate_context(request,"6248-1dd5bcf4df44308",now,56459880);
    check(result.error==wire::ContextError::expired,"context expiry");
    request.expires_filetime=now+wire::kMaxExpiryWindowFiletime+1;
    result=wire::validate_context(request,"6248-1dd5bcf4df44308",now,56459880);
    check(result.error==wire::ContextError::expiry_window_exceeded,"context window");
    request.expires_filetime=now+100;
    result=wire::validate_context(request,"6248-1dd5bcf4df44308",now,56459881);
    check(result.error==wire::ContextError::date_mismatch,"context date");
}

int main() {
    test_valid();
    test_cross_action_context();
    test_support_action_context();
    test_military_access_action_context();
    test_vassalization_action_context();
    test_peace_action_context();
    test_negative();
    test_context();
    if (failures) {
        std::printf("alliance-inbound-response-wire fixture FAILED count=%d\n",failures);
        return 1;
    }
    std::puts("alliance-inbound-response-wire fixture PASS: valid, negative, context");
    return 0;
}
