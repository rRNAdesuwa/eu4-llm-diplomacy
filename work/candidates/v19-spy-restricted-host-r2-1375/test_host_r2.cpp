#define main sealed_host_mock_main
#include "test_host.cpp"
#undef main

namespace {
unsigned begin_count=0,begin_failure=0;
bool begin_checked(void*) { return ++begin_count!=begin_failure; }
void begin_failures() {
    // Six preflight callbacks, seq4 begin, then five item/health pairs.
    for(unsigned at=1;at<=17;++at) {
        Rig r;begin_count=0;begin_failure=at;r.env.begin_frame=begin_checked;
        bool ok=r.preflight();if(ok)ok=r.run(4);
        for(unsigned n=0;ok&&n<10;++n)ok=r.frame();
        check(!ok&&begin_count==at,"each failed begin_frame stops in its exact callback");
        check(r.controller.status().state==h::State::frozen&&r.controller.status().failure==h::Failure::world,"failed begin_frame latched at Host");
        const auto calls=r.calls();const auto claims=r.claims.size();begin_failure=0;
        check(!r.frame()&&!r.run(4)&&r.calls()==calls&&r.claims.size()==claims&&begin_count==at,"restored callback cannot resume or reclaim");
        r.terminal();
    }
}
void clock_boundaries() {
    {
        Rig r;r.expiry=60000;check(r.preflight(),"F2 actual nested preflight setup");
        const auto calls=r.calls();--r.mock.now;
        check(!r.run(4)&&r.controller.status().failure==h::Failure::clock,"preflight10000 seq4 9999 rejected before claim");
        check(r.claims.size()==3&&r.calls()==calls&&r.mock.now==9999,"failed true timestamp not clamped and no effects");
        r.mock.now=10000;r.terminal();
    }
    for(unsigned after=0;after<=1;++after) {
        Rig r;check(r.preflight()&&r.run(4),"postclaim clock setup");
        if(after)check(r.frame(),"normal item before rollback health");
        const auto calls=r.calls();const auto claims=r.claims.size();--r.mock.now;
        check(!r.frame()&&r.controller.status().failure==h::Failure::clock,"batch or later health rollback latches");
        check(r.calls()==calls&&r.claims.size()==claims&&r.controller.status().completed_items==0,"regression cannot dispatch or certify completion");
        r.mock.now=10000;r.terminal();
    }
    for(unsigned advance=0;advance<=1;++advance) {
        Rig r;check(r.preflight(),"legal clock equality/advance setup");r.mock.now+=advance;
        check(r.run(4)&&r.frame()&&r.frame(),"equal or advanced real clock permits known item and later health");
        check(r.controller.status().completed_items==1&&r.mock.submit_calls==1&&r.mock.now==10000+advance,"legal timestamp retained exactly");
    }
    {
        Rig r;check(r.start()&&r.run(1),"preflight ongoing clock setup");
        const auto calls=r.calls();--r.mock.now;
        check(!r.frame()&&r.controller.status().failure==h::Failure::clock&&r.calls()==calls,"preflight health participates in shared high water");r.terminal();
    }
}
}
int main(int argc,char** argv) {
    // Exact sealed tests are included unchanged, followed by new actual CPP paths.
    codec();proofs();full_batches(argc==2?argv[1]:nullptr);fault_cases();file_journal();
    begin_failures();clock_boundaries();
    std::printf("{\"checks\":%u,\"failures\":%u,\"mock_only\":true,\"game_access\":false}\n",checks,failures);
    return failures?1:0;
}
