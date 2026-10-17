#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

#include "rival-command-wire.h"

using bridge::rival_command_wire::CommandKind;
using bridge::rival_command_wire::ContextError;
using bridge::rival_command_wire::ExecutionRequest;
using bridge::rival_command_wire::ParseError;
using bridge::rival_command_wire::parse_request;
using bridge::rival_command_wire::validate_context;

static unsigned g_checks=0;
static unsigned g_failures=0;

static void check(bool value,const char* name) {
    ++g_checks;
    if (!value) {
        ++g_failures;
        std::printf("fixture_check_failed:%s\n",name);
    }
}

static std::string wire_for(const char* request_id="rival_1",
    const char* session="1abc",const char* expiry="1500",
    const char* date="42",const char* action="set_rival",
    const char* actor="FRA",const char* recipient="BUR") {
    return std::string("RIVAL_EXEC1 ")+request_id+" "+session+" "+expiry
        +" "+date+" "+action+" "+actor+" "+recipient+"\n";
}

static void expect_error(const std::string& wire,ParseError expected,
    const char* name) {
    ExecutionRequest request{};
    check(parse_request(wire.data(),wire.size(),request).error==expected,name);
}

static void test_valid_commands() {
    static_assert(sizeof(ExecutionRequest::request_id)==65,
        "request id is fixed at 64 bytes plus NUL");
    static_assert(sizeof(ExecutionRequest::session_creation_hex)==17,
        "session hex is fixed at 16 bytes plus NUL");

    ExecutionRequest set{};
    const std::string set_wire=wire_for();
    const auto set_result=parse_request(set_wire.data(),set_wire.size(),set);
    check(set_result.ok(),"set_wire_valid");
    check(set.command==CommandKind::set_rival,"set_kind");
    check(std::strcmp(set.action_id,"set_rival")==0,"set_action_id");
    check(std::strcmp(set.request_id,"rival_1")==0,"set_request_id");
    check(std::strcmp(set.session_creation_hex,"1abc")==0,
        "set_session_text");
    check(set.session_epoch==0x1abcu,"set_session_epoch");
    check(set.expiry_tick==1500u,"set_expiry");
    check(set.date_raw==42,"set_date");
    check(std::strcmp(set.actor,"FRA")==0,"set_actor");
    check(std::strcmp(set.recipient,"BUR")==0,"set_recipient");

    ExecutionRequest remove{};
    const std::string remove_wire=wire_for("rival_2","ABCDEF0123456789",
        "60000","-7","remove_rival","FRA","ENG");
    const auto remove_result=parse_request(remove_wire.data(),remove_wire.size(),
        remove);
    check(remove_result.ok(),"remove_wire_valid");
    check(remove.command==CommandKind::remove_rival,"remove_kind");
    check(std::strcmp(remove.action_id,"remove_rival")==0,"remove_action_id");
    check(remove.session_epoch==0xabcdef0123456789ull,"remove_session_epoch");
    check(remove.expiry_tick==60000u,"remove_expiry");
    check(remove.date_raw==-7,"remove_signed_date");
    check(std::strcmp(remove.recipient,"ENG")==0,"remove_recipient");
}

static void test_wire_boundaries() {
    expect_error(std::string(),ParseError::empty_input,"empty_input");
    expect_error(wire_for()+"tail\n",ParseError::embedded_newline,
        "second_line_rejected");

    std::string missing=wire_for();
    missing.pop_back();
    expect_error(missing,ParseError::missing_final_lf,"missing_lf");
    std::string crlf=wire_for();
    crlf.insert(crlf.size()-1,1,'\r');
    expect_error(crlf,ParseError::crlf_rejected,"crlf");

    expect_error(wire_for("rival__","1abc","1500","42","set_rival",
        "POR","BUR"),ParseError::invalid_actor,"actor_must_be_fra");
    expect_error(wire_for("rival__","1abc","1500","42","set_rival",
        "FRA","fra"),ParseError::invalid_recipient,"recipient_uppercase");
    expect_error(wire_for("rival__","1abc","1500","42","set_rival",
        "FRA","FRA"),ParseError::invalid_recipient,
        "recipient_cannot_be_fra");
    expect_error(wire_for("rival__","0","1500"),
        ParseError::invalid_session_hex,"zero_session_rejected");
    expect_error(wire_for("rival__","1agc","1500"),
        ParseError::invalid_session_hex,"session_hex_character");
    expect_error(wire_for("rival__","12345678901234567","1500"),
        ParseError::invalid_session_hex,"session_hex_length");
    expect_error(wire_for("rival__","1abc","-1"),
        ParseError::invalid_expiry_tick,"negative_expiry_rejected");
    expect_error(wire_for("rival__","1abc","1500","2147483648"),
        ParseError::invalid_date,"date_overflow");
    expect_error(wire_for("rival__","1abc","1500","42","replace_rival"),
        ParseError::invalid_action,"replace_not_exposed");
    expect_error(wire_for("rival__","1abc","1500","42","set_rival",
        "FRA","BURX"),ParseError::invalid_recipient,
        "recipient_trailing_character");
    expect_error("RIVAL_EXEC1  rival_1 1abc 1500 42 set_rival FRA BUR\n",
        ParseError::field_count,"repeated_spaces_rejected");
    expect_error("RIVAL_EXEC1|rival_1 1abc 1500 42 set_rival FRA BUR\n",
        ParseError::field_count,"wrong_separator_rejected");

    std::string nul=wire_for();
    nul.insert(15,1,'\0');
    expect_error(nul,ParseError::embedded_nul,"embedded_nul");
    std::string oversized=wire_for();
    oversized.insert(oversized.size()-1,300,'x');
    expect_error(oversized,ParseError::wire_too_long,"wire_size_bound");
}

static void test_context() {
    ExecutionRequest request{};
    const std::string wire=wire_for("rival_ctx","abcd","1600","42");
    check(parse_request(wire.data(),wire.size(),request).ok(),"context_parse");
    check(validate_context(request,0xabcd,1000,42).error==ContextError::ok,
        "context_accepts_window");
    check(validate_context(request,0xabce,1000,42).error==ContextError::session_mismatch,
        "context_session_binding");
    check(validate_context(request,0xabcd,1600,42).error==ContextError::expired,
        "context_expired");
    check(validate_context(request,0xabcd,1001,42).error==ContextError::ok,
        "context_one_tick_before_expiry");

    const std::string long_window=wire_for("rival_long","abcd","62001","42");
    ExecutionRequest long_request{};
    check(parse_request(long_window.data(),long_window.size(),long_request).ok(),
        "long_window_wire_parse");
    check(validate_context(long_request,0xabcd,1000,42).error
        ==ContextError::deadline_window_exceeded,"context_window_limit");
    check(validate_context(request,0xabcd,1000,43).error==ContextError::date_mismatch,
        "context_date_binding");
    check(validate_context(request,0,1000,42).error
        ==ContextError::expected_session_missing,"context_expected_session");
}

int main() {
    test_valid_commands();
    test_wire_boundaries();
    test_context();
    std::printf("checks=%u failures=%u status=%s\n",g_checks,g_failures,
        g_failures==0?"passed":"failed");
    return g_failures==0?0:1;
}
