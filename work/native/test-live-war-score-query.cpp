#include <cstdio>
#include <cstring>

#include "live-war-score-query.h"

using bridge::live_war_score_query::Mode;
using bridge::live_war_score_query::Request;
using bridge::live_war_score_query::Result;

static unsigned checks=0;
static unsigned failures=0;

static void check(bool value,const char* name) {
    ++checks;
    if (!value) {
        ++failures;
        std::printf("live_war_score_check_failed:%s\n",name);
    }
}

int main() {
    static_assert(sizeof(Mode)==sizeof(std::uint8_t),
        "mode remains one native byte");
    static_assert(bridge::live_war_score_query::kMaxNativeTooltipBytes==8192,
        "tooltip bound is fixed");
    static_assert(bridge::live_war_score_query::kMaxNativeTooltipHexBytes==16385,
        "hex buffer includes terminator");

    check(bridge::live_war_score_query::valid_mode(0),"whole_war_mode");
    check(bridge::live_war_score_query::valid_mode(1),"separate_mode");
    check(!bridge::live_war_score_query::valid_mode(2),"unknown_mode_rejected");
    check(std::strcmp(bridge::live_war_score_query::mode_name(
        Mode::whole_war),"whole_war")==0,"whole_war_name");
    check(std::strcmp(bridge::live_war_score_query::mode_name(
        Mode::separate),"separate")==0,"separate_name");

    Result result{};
    check(!bridge::live_war_score_query::has_error(result),
        "empty_result_has_no_error");
    check(!bridge::live_war_score_query::result_complete(result),
        "empty_result_incomplete");
    bridge::live_war_score_query::set_error(result,"WAR_CONTEXT_STALE");
    check(bridge::live_war_score_query::has_error(result),
        "error_code_set");
    check(std::strcmp(result.error_code,"WAR_CONTEXT_STALE")==0,
        "error_code_preserved");
    bridge::live_war_score_query::set_error(result,nullptr);
    check(!bridge::live_war_score_query::has_error(result),
        "error_code_cleared");

    result.complete=true;
    result.verified=true;
    check(bridge::live_war_score_query::result_complete(result),
        "complete_verified_result");
    result.goal_called=true;
    result.goal_return_verified=true;
    result.goal_presence_readable=true;
    result.goal_present=false;
    result.goal_inapplicable=true;
    result.goal_complete=false;
    check(!result.goal_complete,
        "inapplicable_goal_is_not_complete");
    check(result.goal_inapplicable && !result.goal_present,
        "inapplicable_goal_is_explicit");
    result.verified=false;
    check(!bridge::live_war_score_query::result_complete(result),
        "unverified_result_rejected");

    Request request{};
    request.mode=static_cast<std::uint8_t>(Mode::whole_war);
    check(bridge::live_war_score_query::valid_mode(request.mode),
        "request_default_mode");

    std::printf("live_war_score_query_contract_checks:%u failures:%u\n",
        checks,failures);
    return failures?1:0;
}
