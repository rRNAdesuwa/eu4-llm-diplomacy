// This executable calls only the exact pure helpers included by the candidate
// host. It does not link the host/core, call Win32, or open the game process.
#include "generated/work/native/v13/owned-peace-stage-1375.h"
#include <cstring>
#include <cstdio>
namespace s = eu4_owned_peace_stage_1375;
namespace p = eu4_owned_peace_lifecycle_1375;
static unsigned checks = 0, failures = 0;
static void check(bool value, const char* label) {
    ++checks; if (!value) { ++failures; std::printf("FAIL: %s\n", label); }
}
static p::Result good() {
    p::Result r{}; r.reason = p::Reason::none; r.passed = true; r.audit_complete = true;
    r.factory_entered = r.factory_returned = r.clone_entered = r.clone_returned = true;
    r.original_destroy_entered = r.original_destroy_returned = true;
    r.clone_destroy_entered = r.clone_destroy_returned = true;
    r.distinct_owned_ranges = r.original_unchanged_after_clone = r.clone_unchanged_after_original_destroy = true;
    return r;
}
static s::State ready() {
    s::State state{};
    s::begin(state, true, true, true, true);
    s::finish(state, good(), true, true);
    return state;
}
int main() {
    s::State state{};
    check(!s::permits_later(state), "fresh stage never permits later work");
    check(s::next(false,false,state,false,false,false,false,false) == s::Next::lifecycle, "base lifecycle first");
    check(s::next(true,false,state,false,false,false,false,true) == s::Next::none, "failed base closes stage");
    check(s::next(true,true,state,false,false,false,false,false) == s::Next::none, "post-base healthy frame required");
    check(s::next(true,true,state,false,false,false,false,true) == s::Next::owned_peace, "owned stage before preview");
    for (unsigned missing = 0; missing < 4; ++missing) {
        s::State failed{}; bool args[4] = {true,true,true,true}; args[missing] = false;
        check(!s::begin(failed,args[0],args[1],args[2],args[3]) && failed.frozen && !s::permits_later(failed),
              "each missing prerequisite freezes before native entry");
    }
    check(s::begin(state,true,true,true,true) && state.tested && state.claim && state.in_call,
          "durable claim sets once and in-call before native entry");
    check(s::next(true,true,state,false,false,false,false,true) == s::Next::none, "in-call cannot run preview");
    check(!s::permits_later(state), "claim alone never passes");
    s::State duplicate = state;
    check(!s::begin(duplicate,true,true,true,true) && duplicate.frozen, "second begin freezes no retry");
    const auto result = good();
    check(s::result_ok(result), "complete core result accepted");
    check(s::finish(state,result,true,true) && s::permits_later(state), "post guard and durable wrapper permit stage");
    check(s::next(true,true,state,false,false,false,false,false) == s::Next::none, "core and wrapper do not substitute health");
    check(s::next(true,true,state,false,false,false,false,true) == s::Next::preview, "post-owned health allows preview");
    check(s::next(true,true,state,true,false,false,false,true) == s::Next::none, "failed preview blocks command");
    check(s::next(true,true,state,true,true,false,false,false) == s::Next::none, "post-preview health required");
    check(s::next(true,true,state,true,true,false,false,true) == s::Next::command, "healthy preview allows command");
    check(s::next(true,true,state,true,true,true,false,true) == s::Next::none, "failed command blocks mailbox");
    check(s::next(true,true,state,true,true,true,true,false) == s::Next::none, "post-command health required");
    check(s::next(true,true,state,true,true,true,true,true) == s::Next::mailbox, "all stages and health allow mailbox");
    check(!s::finish(state,result,true,true) && state.frozen, "duplicate completion freezes");

    bool p::Result::* required[] = {&p::Result::passed,&p::Result::audit_complete,&p::Result::factory_entered,
        &p::Result::factory_returned,&p::Result::clone_entered,&p::Result::clone_returned,
        &p::Result::original_destroy_entered,&p::Result::original_destroy_returned,
        &p::Result::clone_destroy_entered,&p::Result::clone_destroy_returned,&p::Result::distinct_owned_ranges,
        &p::Result::original_unchanged_after_clone,&p::Result::clone_unchanged_after_original_destroy};
    for (auto field : required) {
        auto bad = good(); bad.*field = false; s::State failed{}; s::begin(failed,true,true,true,true);
        check(!s::result_ok(bad) && !s::finish(failed,bad,true,true) && failed.frozen && !s::permits_later(failed),
              "each missing native-return ownership or audit proof freezes");
    }
    bool p::Result::* prohibited[] = {&p::Result::freeze_session,&p::Result::retry_allowed,&p::Result::execution_verified};
    for (auto field : prohibited) { auto bad=good(); bad.*field=true; check(!s::result_ok(bad), "prohibited success flag rejected"); }
    for (unsigned reason=1; reason<=static_cast<unsigned>(p::Reason::native_exception); ++reason) {
        auto bad=good(); bad.reason=static_cast<p::Reason>(reason); check(!s::result_ok(bad), "all non-none core reasons rejected");
    }
    auto bad=good(); bad.exception_code=0xc0000005; check(!s::result_ok(bad), "SEH cannot be successful");
    bad=good(); bad.original_mismatch_mask=1; check(!s::result_ok(bad), "original layout mismatch rejects");
    bad=good(); bad.clone_mismatch_mask=1ULL<<63; check(!s::result_ok(bad), "clone high mismatch bit rejects");
    for (unsigned missing=0; missing<2; ++missing) {
        s::State failed{}; s::begin(failed,true,true,true,true);
        check(!s::finish(failed,good(),missing!=0,missing!=1) && failed.frozen,
              "post guard or wrapper audit failure closes stage");
    }
    state={}; check(!s::finish(state,good(),true,true) && state.frozen, "fabricated completion without attempt rejected");
    bool s::State::* stage_required[] = {&s::State::tested,&s::State::claim,&s::State::core_returned,&s::State::wrapper_durable,&s::State::passed};
    for (auto field:stage_required) { state=ready(); state.*field=false; check(!s::permits_later(state), "each host stage fact required"); }
    state=ready(); state.in_call=true; check(!s::permits_later(state), "in-call prevents later native work");
    state=ready(); s::reject(state); check(!s::permits_later(state) && s::next(true,true,state,true,true,true,true,true)==s::Next::none,
                                        "revocation stops scheduler and dispatch guard");
    check(!s::begin(state,true,true,true,true), "frozen stage cannot rearm");

    char marker[192]{}; std::size_t written=999;
    check(s::format_marker(marker,sizeof(marker),12345,0x123456789abcdefULL,written), "marker formats exact binding");
    const char expected[]="OWNED_PEACE_LIFECYCLE/1\npurpose=restricted_pair_lab_1375_v13\npid=12345\ncreation=0123456789abcdef\n";
    check(written==sizeof(expected)-1 && std::strcmp(marker,expected)==0, "marker bytes include version pid creation newline");
    char other[192]{}; std::size_t other_size=0;
    s::format_marker(other,sizeof(other),12346,0x123456789abcdefULL,other_size);
    check(std::strcmp(marker,other)!=0, "other pid changes exact marker");
    s::format_marker(other,sizeof(other),12345,0x123456789abcdeeULL,other_size);
    check(std::strcmp(marker,other)!=0, "reused pid new creation changes marker");
    check(!s::format_marker(other,sizeof(other),0,1,other_size) && other_size==0, "zero pid rejected");
    check(!s::format_marker(other,sizeof(other),1,0,other_size) && other_size==0, "zero creation rejected");
    check(!s::format_marker(nullptr,192,1,1,other_size) && other_size==0, "null marker output rejected");
    check(!s::format_marker(other,0,1,1,other_size) && other_size==0, "zero marker capacity rejected");
    check(!s::format_marker(other,sizeof(expected)-1,12345,0x123456789abcdefULL,other_size) && other_size==0,
          "no room for terminator rejected");
    check(s::format_marker(other,sizeof(expected),12345,0x123456789abcdefULL,other_size), "exact capacity works");
    check(s::format_marker(other,sizeof(other),0xffffffffU,0xffffffffffffffffULL,other_size), "maximum scalar identity bounded");
    std::printf("%u synthetic checks; %u failures\n",checks,failures);
    return failures ? 1 : 0;
}
