#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

#include "alliance-execution-wire.h"

using bridge::alliance_execution_wire::ContextError;
using bridge::alliance_execution_wire::ExecutionRequest;
using bridge::alliance_execution_wire::ParseError;
using bridge::alliance_execution_wire::kMaxExpiryWindowFiletime;
using bridge::alliance_execution_wire::kMaxWireBytes;
using bridge::alliance_execution_wire::parse_request;
using bridge::alliance_execution_wire::validate_context;

static unsigned g_checks=0;
static unsigned g_failures=0;

static void check(bool condition,const char* name) {
    ++g_checks;
    if (!condition) {
        ++g_failures;
        std::printf("fixture_check_failed:%s\n",name);
    }
}

static std::string wire_for_action(const char* action,const char* recipient,
    const char* phase="initiate",std::uint64_t expiry=1100000000ull,
    std::int32_t date=42,const char* request_id="req_01",
    const char* session_id="1234-1abc") {
    return std::string("v1|")+request_id+"|"+session_id+"|"
        +std::to_string(expiry)+"|"+std::to_string(date)
        +"|"+action+"|FRA|"+recipient+"|"+phase+"\n";
}

static std::string wire_for_insult(const char* action,std::int32_t insult_id,
    const char* recipient="USA",const char* phase="initiate",
    std::uint64_t expiry=1100000000ull,std::int32_t date=42,
    const char* request_id="req_01",const char* session_id="1234-1abc") {
    return std::string("v2|")+request_id+"|"+session_id+"|"
        +std::to_string(expiry)+"|"+std::to_string(date)
        +"|"+action+"|FRA|"+recipient+"|"+phase+"|"
        +std::to_string(insult_id)+"\n";
}

static std::string wire_for_v3_action(const char* action,const char* cbkey,
    std::int32_t province,const char* beneficiary,const char* recipient="SAV",
    const char* phase="initiate",std::uint64_t expiry=1100000000ull,
    std::int32_t date=42,const char* request_id="req_01",
    const char* session_id="1234-1abc") {
    return std::string("EU4DIP_EXEC3|")+request_id+"|"+session_id+"|"
        +std::to_string(expiry)+"|"+std::to_string(date)
        +"|"+action+"|FRA|"+recipient+"|"+phase+"|"+cbkey+"|"
        +std::to_string(province)+"|"+beneficiary+"\n";
}

static std::string wire_for_declare_war(const char* cbkey="conquest",
    std::int32_t province=123,const char* beneficiary="---",
    const char* recipient="SAV",std::uint64_t expiry=1100000000ull,
    std::int32_t date=42,const char* request_id="req_01",
    const char* session_id="1234-1abc") {
    return wire_for_v3_action("declare_war",cbkey,province,beneficiary,
        recipient,"initiate",expiry,date,request_id,session_id);
}

static std::string wire_for(std::uint64_t expiry=1100000000ull,
    std::int32_t date=42,const char* request_id="req_01",
    const char* session_id="1234-1abc",const char* recipient="USA") {
    return wire_for_action("offer_alliance",recipient,"initiate",expiry,
        date,request_id,session_id);
}

static void expect_error(const std::string& wire,ParseError expected,const char* name) {
    ExecutionRequest request{};
    const auto result=parse_request(wire.data(),wire.size(),request);
    check(result.error==expected,name);
}

static void test_valid_and_boundaries() {
    ExecutionRequest request{};
    const std::string wire=wire_for();
    const auto result=parse_request(wire.data(),wire.size(),request);
    check(result.ok(),"valid_wire");
    check(std::strcmp(request.request_id,"req_01")==0,"request_id_copied");
    check(std::strcmp(request.session_id,"1234-1abc")==0,"session_id_copied");
    check(std::strcmp(request.action_id,"offer_alliance")==0,"action_copied");
    check(std::strcmp(request.actor,"FRA")==0,"actor_copied");
    check(std::strcmp(request.recipient,"USA")==0,"recipient_copied");
    check(std::strcmp(request.phase,"initiate")==0,"phase_copied");
    check(request.session_pid==1234u,"pid_decoded");
    check(request.session_creation_filetime==0x1abcu,"creation_hex_decoded");
    check(request.expires_filetime==1100000000ull,"expiry_decoded");
    check(request.date_raw==42,"date_decoded");
    check(request.insult_id==-1,"v1_insult_id_default");

    std::string max_request(64,'a');
    expect_error(wire_for(1100000000ull,42,max_request.c_str()),ParseError::ok,
        "request_id_maximum");
    expect_error(wire_for(1100000000ull,42,"r"),ParseError::ok,"short_request_id");
    expect_error(wire_for(1100000000ull,-2147483648),ParseError::ok,"date_minimum");
    expect_error(wire_for(1100000000ull,2147483647),ParseError::ok,"date_maximum");
}

static void test_structure_rejections() {
    std::string missing_lf=wire_for();
    missing_lf.pop_back();
    expect_error(missing_lf,ParseError::missing_final_lf,"missing_final_lf");

    std::string crlf=wire_for();
    crlf.insert(crlf.size()-1,1,'\r');
    expect_error(crlf,ParseError::crlf_rejected,"crlf_rejected");

    expect_error(wire_for()+"extra\n",ParseError::embedded_newline,"extra_line_rejected");
    expect_error(std::string("v1|req_01|1234-1abc|1100000000|42|offer_alliance|FRA|USA\n"),
        ParseError::field_count,"missing_field");
    expect_error(wire_for()+"|extra\n",ParseError::embedded_newline,"extra_field_line_rejected");

    std::string embedded=wire_for();
    embedded.insert(7,1,'\0');
    expect_error(embedded,ParseError::embedded_nul,"embedded_nul");

    std::string overlong=wire_for();
    overlong.insert(overlong.size()-1,kMaxWireBytes,'x');
    expect_error(overlong,ParseError::wire_too_long,"wire_too_long");
    expect_error(std::string(),ParseError::empty_input,"empty_input");
    expect_error(std::string("v1|req_01|1234-1abc|1100000000|42|offer_alliance|FRA|USA|initiate"),
        ParseError::missing_final_lf,"no_terminal_newline");

    const char* null_bytes=nullptr;
    ExecutionRequest request{};
    check(parse_request(null_bytes,0,request).error==ParseError::null_input,"null_input");
}

static void test_field_rejections() {
    std::string request_too_long(65,'a');
    expect_error(wire_for(1100000000ull,42,request_too_long.c_str()),
        ParseError::invalid_request_id,"request_id_too_long");
    expect_error(wire_for(1100000000ull,42,"bad.id"),ParseError::invalid_request_id,
        "request_id_character");
    expect_error(std::string("v1||1234-1abc|1100000000|42|offer_alliance|FRA|USA|initiate\n"),
        ParseError::empty_field,"empty_request_id");
    expect_error(wire_for(1100000000ull,42,"req","12341abc"),
        ParseError::invalid_session_id,"session_missing_dash");
    expect_error(wire_for(1100000000ull,42,"req","12x4-1abc"),
        ParseError::invalid_session_id,"session_pid_character");
    expect_error(wire_for(1100000000ull,42,"req","4294967296-1abc"),
        ParseError::invalid_session_id,"session_pid_overflow");
    expect_error(wire_for(1100000000ull,42,"req","1234-1abg"),
        ParseError::invalid_session_id,"session_creation_character");
    expect_error(wire_for(1100000000ull,42,"req","1234-1234567890abcdef0"),
        ParseError::invalid_session_id,"session_creation_overflow");
    expect_error(std::string("v1|req_01|1234-1abc|not_number|42|offer_alliance|FRA|USA|initiate\n"),
        ParseError::invalid_expiry,"expiry_character");
    expect_error(std::string("v1|req_01|1234-1abc|18446744073709551616|42|offer_alliance|FRA|USA|initiate\n"),
        ParseError::invalid_expiry,"expiry_overflow");
    expect_error(std::string("v1|req_01|1234-1abc|1100000000|2147483648|offer_alliance|FRA|USA|initiate\n"),
        ParseError::invalid_date,"date_positive_overflow");
    expect_error(std::string("v1|req_01|1234-1abc|1100000000|-2147483649|offer_alliance|FRA|USA|initiate\n"),
        ParseError::invalid_date,"date_negative_overflow");
    expect_error(std::string("v1|req_01|1234-1abc|1100000000|42|wrong_action|FRA|USA|initiate\n"),
        ParseError::invalid_action,"action_rejected");
    expect_error(std::string("v1|req_01|1234-1abc|1100000000|42|offer_alliance|POR|USA|initiate\n"),
        ParseError::invalid_actor,"actor_rejected");
    expect_error(std::string("v1|req_01|1234-1abc|1100000000|42|offer_alliance|FRA|usa|initiate\n"),
        ParseError::invalid_recipient,"recipient_lowercase");
    expect_error(std::string("v1|req_01|1234-1abc|1100000000|42|offer_alliance|FRA|US|initiate\n"),
        ParseError::invalid_recipient,"recipient_length");
    expect_error(std::string("v1|req_01|1234-1abc|1100000000|42|offer_alliance|FRA|USA|accept\n"),
        ParseError::invalid_phase,"phase_rejected");
    expect_error(std::string("v2|req_01|1234-1abc|1100000000|42|offer_alliance|FRA|USA|initiate\n"),
        ParseError::field_count,"v2_requires_insult_parameter");
    expect_error(std::string("v1|req_01|1234-1abc|1100000000|42|send_insult|FRA|USA|initiate\n"),
        ParseError::invalid_action,"insult_requires_v2");
    expect_error(std::string("v1|req_01|1234-1abc|1100000000|42|initiate|FRA|USA|initiate|0\n"),
        ParseError::field_count,"v1_trailing_field_rejected");
}

static void test_action_variants() {
    static_assert(sizeof(ExecutionRequest::action_id)==28,
        "action_id must retain revoke-support action plus NUL");
    static_assert(sizeof("stop_improving_relations")==25,
        "stop-improving action is 24 characters plus NUL");
    static_assert(sizeof("stop_building_spy_network")==26,
        "stop-building-spy action is 25 characters plus NUL");
    static_assert(sizeof("proclaim_guarantee")<sizeof(ExecutionRequest::action_id),
        "proclaim-guarantee action must fit");
    static_assert(sizeof("revoke_guarantee")<sizeof(ExecutionRequest::action_id),
        "revoke-guarantee action must fit");
    static_assert(sizeof("support_independence")<sizeof(ExecutionRequest::action_id),
        "support-independence action must fit");
    static_assert(sizeof("revoke_support_independence")==28,
        "revoke-support action is 27 characters plus NUL");
    static_assert(sizeof("ask_military_access")<sizeof(ExecutionRequest::action_id),
        "ask-military-access action must fit");
    static_assert(sizeof("cancel_military_access")<sizeof(ExecutionRequest::action_id),
        "cancel-military-access action must fit");
    static_assert(sizeof("offer_vassalization")==20,
        "offer-vassalization action is 19 characters plus NUL");
    static_assert(sizeof("cancel_vassalization")==21,
        "cancel-vassalization action is 20 characters plus NUL");

    ExecutionRequest dissolve{};
    const std::string dissolve_wire=wire_for_action("dissolve_alliance","PRO");
    const auto dissolve_result=parse_request(dissolve_wire.data(),dissolve_wire.size(),dissolve);
    check(dissolve_result.ok(),"dissolve_valid");
    check(std::strcmp(dissolve.action_id,"dissolve_alliance")==0,
        "dissolve_action_full");
    check(std::strlen(dissolve.action_id)==17,"dissolve_action_length");
    check(std::strcmp(dissolve.recipient,"PRO")==0,"dissolve_recipient_copied");
    check(std::strcmp(dissolve.phase,"initiate")==0,"dissolve_phase_initiate");

    expect_error(wire_for_action("dissolve_alliance","PRO","accept"),
        ParseError::invalid_phase,"dissolve_accept_rejected");
    expect_error(wire_for_action("dissolve_alliance","PRO","reject"),
        ParseError::invalid_phase,"dissolve_reject_rejected");
    expect_error(wire_for_action("unknown_action","PRO"),
        ParseError::invalid_action,"unknown_action_rejected");

    ExecutionRequest offer{};
    const std::string offer_wire=wire_for();
    const auto offer_result=parse_request(offer_wire.data(),offer_wire.size(),offer);
    check(offer_result.ok(),"offer_still_valid");
    check(std::strcmp(offer.action_id,"offer_alliance")==0,
        "offer_action_still_copied");

    ExecutionRequest royal_offer{};
    const std::string royal_offer_wire=wire_for_action(
        "offer_royal_marriage","SAV");
    const auto royal_offer_result=parse_request(royal_offer_wire.data(),
        royal_offer_wire.size(),royal_offer);
    check(royal_offer_result.ok(),"royal_offer_valid");
    check(std::strcmp(royal_offer.action_id,"offer_royal_marriage")==0,
        "royal_offer_action_full");
    check(std::strlen(royal_offer.action_id)==20,
        "royal_offer_action_length");
    check(std::strcmp(royal_offer.recipient,"SAV")==0,
        "royal_offer_recipient_copied");
    check(std::strcmp(royal_offer.phase,"initiate")==0,
        "royal_offer_phase_initiate");

    ExecutionRequest royal_break{};
    const std::string royal_break_wire=wire_for_action(
        "break_royal_ties","SAV");
    const auto royal_break_result=parse_request(royal_break_wire.data(),
        royal_break_wire.size(),royal_break);
    check(royal_break_result.ok(),"royal_break_valid");
    check(std::strcmp(royal_break.action_id,"break_royal_ties")==0,
        "royal_break_action_full");
    check(std::strlen(royal_break.action_id)==16,
        "royal_break_action_length");
    check(std::strcmp(royal_break.phase,"initiate")==0,
        "royal_break_phase_initiate");

    ExecutionRequest improve{};
    const std::string improve_wire=wire_for_action(
        "improve_relations","SAV");
    const auto improve_result=parse_request(improve_wire.data(),
        improve_wire.size(),improve);
    check(improve_result.ok(),"improve_relations_valid");
    check(std::strcmp(improve.action_id,"improve_relations")==0,
        "improve_relations_action_full");
    check(std::strlen(improve.action_id)==17,
        "improve_relations_action_length");
    check(std::strcmp(improve.recipient,"SAV")==0,
        "improve_relations_recipient_copied");
    check(std::strcmp(improve.phase,"initiate")==0,
        "improve_relations_phase_initiate");

    ExecutionRequest stop_improving{};
    const std::string stop_improving_wire=wire_for_action(
        "stop_improving_relations","SAV");
    const auto stop_improving_result=parse_request(stop_improving_wire.data(),
        stop_improving_wire.size(),stop_improving);
    check(stop_improving_result.ok(),"stop_improving_relations_valid");
    check(std::strcmp(stop_improving.action_id,
        "stop_improving_relations")==0,
        "stop_improving_relations_action_full");
    check(std::strlen(stop_improving.action_id)==24,
        "stop_improving_relations_action_length");
    check(std::strcmp(stop_improving.recipient,"SAV")==0,
        "stop_improving_relations_recipient_copied");
    check(std::strcmp(stop_improving.phase,"initiate")==0,
        "stop_improving_relations_phase_initiate");

    ExecutionRequest spy_build{};
    const std::string spy_build_wire=wire_for_action(
        "build_spy_network","SAV");
    const auto spy_build_result=parse_request(spy_build_wire.data(),
        spy_build_wire.size(),spy_build);
    check(spy_build_result.ok(),"build_spy_network_valid");
    check(std::strcmp(spy_build.action_id,"build_spy_network")==0,
        "build_spy_network_action_full");
    check(std::strlen(spy_build.action_id)==17,
        "build_spy_network_action_length");
    check(std::strcmp(spy_build.recipient,"SAV")==0,
        "build_spy_network_recipient_copied");
    check(std::strcmp(spy_build.phase,"initiate")==0,
        "build_spy_network_phase_initiate");

    ExecutionRequest spy_stop{};
    const std::string spy_stop_wire=wire_for_action(
        "stop_building_spy_network","SAV");
    const auto spy_stop_result=parse_request(spy_stop_wire.data(),
        spy_stop_wire.size(),spy_stop);
    check(spy_stop_result.ok(),"stop_building_spy_network_valid");
    check(std::strcmp(spy_stop.action_id,
        "stop_building_spy_network")==0,
        "stop_building_spy_network_action_full");
    check(std::strlen(spy_stop.action_id)==25,
        "stop_building_spy_network_action_length");
    check(std::strcmp(spy_stop.recipient,"SAV")==0,
        "stop_building_spy_network_recipient_copied");
    check(std::strcmp(spy_stop.phase,"initiate")==0,
        "stop_building_spy_network_phase_initiate");

    ExecutionRequest guarantee_proclaim{};
    const std::string guarantee_proclaim_wire=wire_for_action(
        "proclaim_guarantee","SAV");
    const auto guarantee_proclaim_result=parse_request(
        guarantee_proclaim_wire.data(),guarantee_proclaim_wire.size(),
        guarantee_proclaim);
    check(guarantee_proclaim_result.ok(),"proclaim_guarantee_valid");
    check(std::strcmp(guarantee_proclaim.action_id,
        "proclaim_guarantee")==0,"proclaim_guarantee_action_full");
    check(std::strlen(guarantee_proclaim.action_id)==18,
        "proclaim_guarantee_action_length");
    check(std::strcmp(guarantee_proclaim.recipient,"SAV")==0,
        "proclaim_guarantee_recipient_copied");
    check(std::strcmp(guarantee_proclaim.phase,"initiate")==0,
        "proclaim_guarantee_phase_initiate");

    ExecutionRequest guarantee_revoke{};
    const std::string guarantee_revoke_wire=wire_for_action(
        "revoke_guarantee","SAV");
    const auto guarantee_revoke_result=parse_request(
        guarantee_revoke_wire.data(),guarantee_revoke_wire.size(),
        guarantee_revoke);
    check(guarantee_revoke_result.ok(),"revoke_guarantee_valid");
    check(std::strcmp(guarantee_revoke.action_id,
        "revoke_guarantee")==0,"revoke_guarantee_action_full");
    check(std::strlen(guarantee_revoke.action_id)==16,
        "revoke_guarantee_action_length");
    check(std::strcmp(guarantee_revoke.recipient,"SAV")==0,
        "revoke_guarantee_recipient_copied");
    check(std::strcmp(guarantee_revoke.phase,"initiate")==0,
        "revoke_guarantee_phase_initiate");

    ExecutionRequest support_offer{};
    const std::string support_offer_wire=wire_for_action(
        "support_independence","SAV");
    const auto support_offer_result=parse_request(
        support_offer_wire.data(),support_offer_wire.size(),support_offer);
    check(support_offer_result.ok(),"support_independence_valid");
    check(std::strcmp(support_offer.action_id,
        "support_independence")==0,"support_independence_action_full");
    check(std::strlen(support_offer.action_id)==20,
        "support_independence_action_length");
    check(std::strcmp(support_offer.recipient,"SAV")==0,
        "support_independence_recipient_copied");
    check(std::strcmp(support_offer.phase,"initiate")==0,
        "support_independence_phase_initiate");

    ExecutionRequest support_revoke{};
    const std::string support_revoke_wire=wire_for_action(
        "revoke_support_independence","SAV");
    const auto support_revoke_result=parse_request(
        support_revoke_wire.data(),support_revoke_wire.size(),support_revoke);
    check(support_revoke_result.ok(),"revoke_support_independence_valid");
    check(std::strcmp(support_revoke.action_id,
        "revoke_support_independence")==0,
        "revoke_support_independence_action_full");
    check(std::strlen(support_revoke.action_id)==27,
        "revoke_support_independence_action_length");
    check(std::strcmp(support_revoke.recipient,"SAV")==0,
        "revoke_support_independence_recipient_copied");
    check(std::strcmp(support_revoke.phase,"initiate")==0,
        "revoke_support_independence_phase_initiate");

    ExecutionRequest military_ask{};
    const std::string military_ask_wire=wire_for_action(
        "ask_military_access","SAV");
    const auto military_ask_result=parse_request(
        military_ask_wire.data(),military_ask_wire.size(),military_ask);
    check(military_ask_result.ok(),"ask_military_access_valid");
    check(std::strcmp(military_ask.action_id,"ask_military_access")==0,
        "ask_military_access_action_full");
    check(std::strlen(military_ask.action_id)==19,
        "ask_military_access_action_length");
    check(std::strcmp(military_ask.recipient,"SAV")==0,
        "ask_military_access_recipient_copied");
    check(std::strcmp(military_ask.phase,"initiate")==0,
        "ask_military_access_phase_initiate");

    ExecutionRequest military_cancel{};
    const std::string military_cancel_wire=wire_for_action(
        "cancel_military_access","SAV");
    const auto military_cancel_result=parse_request(
        military_cancel_wire.data(),military_cancel_wire.size(),military_cancel);
    check(military_cancel_result.ok(),"cancel_military_access_valid");
    check(std::strcmp(military_cancel.action_id,"cancel_military_access")==0,
        "cancel_military_access_action_full");
    check(std::strlen(military_cancel.action_id)==22,
        "cancel_military_access_action_length");
    check(std::strcmp(military_cancel.recipient,"SAV")==0,
        "cancel_military_access_recipient_copied");
    check(std::strcmp(military_cancel.phase,"initiate")==0,
        "cancel_military_access_phase_initiate");

    ExecutionRequest vassalization_offer{};
    const std::string vassalization_offer_wire=wire_for_action(
        "offer_vassalization","SAV");
    const auto vassalization_offer_result=parse_request(
        vassalization_offer_wire.data(),vassalization_offer_wire.size(),
        vassalization_offer);
    check(vassalization_offer_result.ok(),"offer_vassalization_valid");
    check(std::strcmp(vassalization_offer.action_id,
        "offer_vassalization")==0,"offer_vassalization_action_full");
    check(std::strlen(vassalization_offer.action_id)==19,
        "offer_vassalization_action_length");
    check(std::strcmp(vassalization_offer.recipient,"SAV")==0,
        "offer_vassalization_recipient_copied");
    check(std::strcmp(vassalization_offer.phase,"initiate")==0,
        "offer_vassalization_phase_initiate");

    ExecutionRequest vassalization_cancel{};
    const std::string vassalization_cancel_wire=wire_for_action(
        "cancel_vassalization","SAV");
    const auto vassalization_cancel_result=parse_request(
        vassalization_cancel_wire.data(),vassalization_cancel_wire.size(),
        vassalization_cancel);
    check(vassalization_cancel_result.ok(),"cancel_vassalization_valid");
    check(std::strcmp(vassalization_cancel.action_id,
        "cancel_vassalization")==0,"cancel_vassalization_action_full");
    check(std::strlen(vassalization_cancel.action_id)==20,
        "cancel_vassalization_action_length");
    check(std::strcmp(vassalization_cancel.recipient,"SAV")==0,
        "cancel_vassalization_recipient_copied");
    check(std::strcmp(vassalization_cancel.phase,"initiate")==0,
        "cancel_vassalization_phase_initiate");

    expect_error(wire_for_action("break_royal_ties","SAV","accept"),
        ParseError::invalid_phase,"royal_break_accept_rejected");
    expect_error(wire_for_action("offer_royal_marriage","SAV","reject"),
        ParseError::invalid_phase,"royal_offer_reject_rejected");
    expect_error(wire_for_action("improve_relations","SAV","accept"),
        ParseError::invalid_phase,"improve_accept_rejected");
    expect_error(wire_for_action("stop_improving_relations","SAV","reject"),
        ParseError::invalid_phase,"stop_improving_reject_rejected");
    expect_error(wire_for_action("build_spy_network","SAV","accept"),
        ParseError::invalid_phase,"build_spy_network_accept_rejected");
    expect_error(wire_for_action("stop_building_spy_network","SAV","reject"),
        ParseError::invalid_phase,"stop_building_spy_network_reject_rejected");
    expect_error(wire_for_action("proclaim_guarantee","SAV","accept"),
        ParseError::invalid_phase,"proclaim_guarantee_accept_rejected");
    expect_error(wire_for_action("revoke_guarantee","SAV","reject"),
        ParseError::invalid_phase,"revoke_guarantee_reject_rejected");
    expect_error(wire_for_action("support_independence","SAV","accept"),
        ParseError::invalid_phase,"support_independence_accept_rejected");
    expect_error(wire_for_action("revoke_support_independence","SAV","reject"),
        ParseError::invalid_phase,"revoke_support_independence_reject_rejected");
    expect_error(wire_for_action("ask_military_access","SAV","accept"),
        ParseError::invalid_phase,"ask_military_access_accept_rejected");
    expect_error(wire_for_action("cancel_military_access","SAV","reject"),
        ParseError::invalid_phase,"cancel_military_access_reject_rejected");
    expect_error(wire_for_action("offer_vassalization","SAV","accept"),
        ParseError::invalid_phase,"offer_vassalization_accept_rejected");
    expect_error(wire_for_action("cancel_vassalization","SAV","reject"),
        ParseError::invalid_phase,"cancel_vassalization_reject_rejected");
    expect_error(wire_for_action("build_spy_networ","SAV"),
        ParseError::invalid_action,"build_spy_network_near_miss_rejected");
    expect_error(wire_for_action("stop_building_spy_networ","SAV"),
        ParseError::invalid_action,
        "stop_building_spy_network_near_miss_rejected");
    expect_error(wire_for_action("proclaim_guarante","SAV"),
        ParseError::invalid_action,"proclaim_guarantee_near_miss_rejected");
    expect_error(wire_for_action("revoke_guarante","SAV"),
        ParseError::invalid_action,"revoke_guarantee_near_miss_rejected");
    expect_error(wire_for_action("support_independenc","SAV"),
        ParseError::invalid_action,"support_independence_near_miss_rejected");
    expect_error(wire_for_action("revoke_support_independenc","SAV"),
        ParseError::invalid_action,
        "revoke_support_independence_near_miss_rejected");
    expect_error(wire_for_action("ask_military_acces","SAV"),
        ParseError::invalid_action,"ask_military_access_near_miss_rejected");
    expect_error(wire_for_action("cancel_military_acces","SAV"),
        ParseError::invalid_action,"cancel_military_access_near_miss_rejected");
    expect_error(wire_for_action("offer_vassalizatio","SAV"),
        ParseError::invalid_action,"offer_vassalization_near_miss_rejected");
    expect_error(wire_for_action("cancel_vassalizatio","SAV"),
        ParseError::invalid_action,"cancel_vassalization_near_miss_rejected");
    expect_error(wire_for_action("build_spy_network","SAV","initiate",
        1100000000ull,42,"bad.id"),ParseError::invalid_request_id,
        "spy_invalid_request_id_rejected");
}

static void test_insult_v2_wire() {
    static_assert(sizeof("send_insult")==12,
        "ordinary-insult action length must remain exact");
    static_assert(sizeof("scornful_insult")==16,
        "scornful-insult action length must remain exact");

    ExecutionRequest ordinary{};
    const std::string ordinary_wire=wire_for_insult("send_insult",-1,"SAV");
    const auto ordinary_result=parse_request(ordinary_wire.data(),
        ordinary_wire.size(),ordinary);
    check(ordinary_result.ok(),"ordinary_insult_v2_valid");
    check(std::strcmp(ordinary.action_id,"send_insult")==0,
        "ordinary_insult_action_copied");
    check(std::strcmp(ordinary.recipient,"SAV")==0,
        "ordinary_insult_recipient_copied");
    check(ordinary.insult_id==-1,"ordinary_insult_parameter_minus_one");

    ExecutionRequest scornful_zero{};
    const std::string scornful_zero_wire=wire_for_insult(
        "scornful_insult",0,"LIT");
    const auto scornful_zero_result=parse_request(scornful_zero_wire.data(),
        scornful_zero_wire.size(),scornful_zero);
    check(scornful_zero_result.ok(),"scornful_insult_zero_valid");
    check(std::strcmp(scornful_zero.action_id,"scornful_insult")==0,
        "scornful_insult_action_copied");
    check(scornful_zero.insult_id==0,"scornful_insult_zero_parameter");

    ExecutionRequest scornful_max{};
    const std::string scornful_max_wire=wire_for_insult(
        "scornful_insult",2147483647,"PRO");
    const auto scornful_max_result=parse_request(scornful_max_wire.data(),
        scornful_max_wire.size(),scornful_max);
    check(scornful_max_result.ok(),"scornful_insult_int32_max_valid");
    check(scornful_max.insult_id==2147483647,
        "scornful_insult_int32_max_decoded");

    expect_error(wire_for_insult("send_insult",0),
        ParseError::invalid_insult_id,"ordinary_insult_rejects_scornful_id");
    expect_error(wire_for_insult("scornful_insult",-1),
        ParseError::invalid_insult_id,"scornful_insult_rejects_minus_one");
    expect_error(wire_for_insult("scornful_insult",-2),
        ParseError::invalid_insult_id,"scornful_insult_rejects_negative_id");
    expect_error(std::string(
        "v2|req_01|1234-1abc|1100000000|42|scornful_insult|FRA|USA|initiate|2147483648\n"),
        ParseError::invalid_insult_id,"scornful_insult_positive_overflow");
    expect_error(std::string(
        "v2|req_01|1234-1abc|1100000000|42|send_insult|FRA|USA|initiate|-2147483649\n"),
        ParseError::invalid_insult_id,"ordinary_insult_negative_overflow");

    expect_error(wire_for_insult("send_insult",-1,"USA","accept"),
        ParseError::invalid_phase,"ordinary_insult_accept_rejected");
    expect_error(wire_for_insult("scornful_insult",0,"USA","reject"),
        ParseError::invalid_phase,"scornful_insult_reject_rejected");
    expect_error(wire_for_insult("send_insult",-1,"USA","dissolve"),
        ParseError::invalid_phase,"ordinary_insult_dissolve_rejected");

    // Existing actions remain v1-only even when a tenth field is present.
    expect_error(std::string(
        "v2|req_01|1234-1abc|1100000000|42|offer_alliance|FRA|USA|initiate|-1\n"),
        ParseError::invalid_action,"existing_action_rejects_v2");
    expect_error(wire_for_insult("send_insul",-1),
        ParseError::invalid_action,"ordinary_insult_near_miss_rejected");

    std::string extra=wire_for_insult("send_insult",-1);
    extra.insert(extra.size()-1,"|tail");
    expect_error(extra,ParseError::field_count,"v2_trailing_field_rejected");
}

static void test_declare_war_v3_wire() {
    static_assert(sizeof("EU4DIP_EXEC3")==13,
        "Declare War protocol marker must remain exact");
    static_assert(sizeof("declare_war")==12,
        "Declare War action length must remain exact");
    static_assert(sizeof(ExecutionRequest::casus_belli)==129,
        "casus-belli storage must hold 128 bytes plus NUL");
    static_assert(sizeof(ExecutionRequest::war_goal_beneficiary)==4,
        "war-goal beneficiary must hold a three-letter tag plus NUL");

    ExecutionRequest request{};
    const std::string valid=wire_for_declare_war("conquest",123,"---");
    check(valid.size()<=kMaxWireBytes,"declare_war_wire_within_bound");
    const auto valid_result=parse_request(valid.data(),valid.size(),request);
    check(valid_result.ok(),"declare_war_v3_valid");
    check(std::strcmp(request.action_id,"declare_war")==0,
        "declare_war_action_copied");
    check(std::strcmp(request.casus_belli,"conquest")==0,
        "declare_war_casus_belli_copied");
    check(request.war_goal_province==123,
        "declare_war_province_decoded");
    check(std::strcmp(request.war_goal_beneficiary,"---")==0,
        "declare_war_beneficiary_empty_marker");
    check(request.insult_id==-1,"declare_war_insult_default");

    ExecutionRequest no_cb_fra{};
    const std::string no_cb_fra_wire=wire_for_declare_war(
        "no_casus_belli",-1,"FRA");
    check(parse_request(no_cb_fra_wire.data(),no_cb_fra_wire.size(),no_cb_fra).ok(),
        "declare_war_no_cb_fra_valid");
    check(no_cb_fra.war_goal_province==-1,
        "declare_war_no_cb_province_default");

    ExecutionRequest no_cb_empty{};
    const std::string no_cb_empty_wire=wire_for_declare_war(
        "no_casus_belli",-1,"---");
    check(parse_request(no_cb_empty_wire.data(),no_cb_empty_wire.size(),no_cb_empty).ok(),
        "declare_war_no_cb_empty_valid");

    std::string max_cb(128,'A');
    ExecutionRequest max_cb_request{};
    const std::string max_cb_wire=wire_for_v3_action(
        "declare_war",max_cb.c_str(),2147483647,"SAV");
    check(max_cb_wire.size()<=kMaxWireBytes,"declare_war_max_cb_within_bound");
    check(parse_request(max_cb_wire.data(),max_cb_wire.size(),max_cb_request).ok(),
        "declare_war_casus_belli_maximum");
    check(std::strlen(max_cb_request.casus_belli)==128,
        "declare_war_casus_belli_maximum_copied");

    std::string too_long_cb(129,'A');
    expect_error(wire_for_v3_action("declare_war",too_long_cb.c_str(),123,"---"),
        ParseError::invalid_casus_belli,"declare_war_casus_belli_too_long");
    expect_error(wire_for_v3_action("declare_war","conquest-key",123,"---"),
        ParseError::invalid_casus_belli,"declare_war_casus_belli_character");
    expect_error(wire_for_v3_action("declare_war","",123,"---"),
        ParseError::empty_field,"declare_war_empty_casus_belli");

    expect_error(wire_for_v3_action("declare_war","conquest",0,"---"),
        ParseError::invalid_war_goal_province,"declare_war_zero_province");
    expect_error(wire_for_v3_action("declare_war","conquest",-2,"---"),
        ParseError::invalid_war_goal_province,"declare_war_negative_province");
    expect_error(std::string(
        "EU4DIP_EXEC3|req_01|1234-1abc|1100000000|42|declare_war|FRA|SAV|initiate|conquest|2147483648|---\n"),
        ParseError::invalid_war_goal_province,"declare_war_province_overflow");
    expect_error(wire_for_v3_action("declare_war","conquest",123,"fra"),
        ParseError::invalid_war_goal_beneficiary,"declare_war_beneficiary_lowercase");
    expect_error(wire_for_v3_action("declare_war","conquest",123,"FR4"),
        ParseError::invalid_war_goal_beneficiary,"declare_war_beneficiary_character");
    expect_error(wire_for_v3_action("declare_war","conquest",123,"--"),
        ParseError::invalid_war_goal_beneficiary,"declare_war_beneficiary_length");
    expect_error(wire_for_v3_action("declare_war","no_casus_belli",123,"FRA"),
        ParseError::invalid_war_goal_province,"declare_war_no_cb_requires_minus_one");
    expect_error(wire_for_v3_action("declare_war","no_casus_belli",-1,"SAV"),
        ParseError::invalid_war_goal_beneficiary,
        "declare_war_no_cb_beneficiary_restricted");

    // A non-CB action cannot use the v3 record, and Declare War cannot use a
    // legacy record.  This also prevents a tenth/eleventh field from being
    // interpreted as a legacy insult parameter.
    expect_error(wire_for_v3_action("offer_alliance","conquest",123,"---"),
        ParseError::invalid_action,"ordinary_action_rejects_v3");
    expect_error(wire_for_action("declare_war","SAV"),
        ParseError::invalid_action,"declare_war_rejects_v1");
    expect_error(wire_for_insult("declare_war",-1),
        ParseError::invalid_action,"declare_war_rejects_v2");

    std::string ally_tail=valid;
    ally_tail.insert(ally_tail.size()-1,"|SAV");
    expect_error(ally_tail,ParseError::field_count,
        "declare_war_call_allies_not_yet_in_wire");
}

static void test_context_validation() {
    constexpr std::uint64_t now=1000000000ull;
    ExecutionRequest request{};
    std::string wire=wire_for(now+kMaxExpiryWindowFiletime,42);
    check(parse_request(wire.data(),wire.size(),request).ok(),"context_setup");
    check(validate_context(request,"1234-1abc",now,42).ok(),"context_valid_at_ten_seconds");
    check(validate_context(request,"9999-1abc",now,42).error==ContextError::session_mismatch,
        "context_session_mismatch");
    check(validate_context(request,nullptr,now,42).error==ContextError::expected_session_missing,
        "context_missing_expected_session");
    check(validate_context(request,"1234-1abc",request.expires_filetime,42).error==ContextError::expired,
        "context_expired");

    wire=wire_for(now+kMaxExpiryWindowFiletime+1u,42);
    check(parse_request(wire.data(),wire.size(),request).ok(),"context_window_setup");
    check(validate_context(request,"1234-1abc",now,42).error==ContextError::expiry_window_exceeded,
        "context_window_exceeded");

    wire=wire_for(now+kMaxExpiryWindowFiletime,43);
    check(parse_request(wire.data(),wire.size(),request).ok(),"context_date_setup");
    check(validate_context(request,"1234-1abc",now,42).error==ContextError::date_mismatch,
        "context_date_mismatch");

    wire=wire_for_declare_war("conquest",123,"---","SAV",
        now+kMaxExpiryWindowFiletime,42);
    check(parse_request(wire.data(),wire.size(),request).ok(),
        "declare_war_context_setup");
    check(validate_context(request,"1234-1abc",now,42).ok(),
        "declare_war_context_valid");
    check(validate_context(request,"1234-1abc",request.expires_filetime,42).error
        ==ContextError::expired,"declare_war_context_expired");
}

int main() {
    test_valid_and_boundaries();
    test_structure_rejections();
    test_field_rejections();
    test_action_variants();
    test_insult_v2_wire();
    test_declare_war_v3_wire();
    test_context_validation();
    std::printf("fixture=alliance_execution_wire checks=%u failures=%u\n",g_checks,g_failures);
    return g_failures==0?0:1;
}
