// Future isolated compile target only. NOT built or run in this candidate review.
// Exercises the actual portable header state helpers; no game/process/DLL call.
#include "files/work/native/v15/lab-request-1375.h"
#include <cstdio>
#include <cstring>

using namespace eu4_lab_1375;
static unsigned checks = 0, failures = 0;
static void check(bool condition) { ++checks; if (!condition) ++failures; }
static MailboxRequest request(const char* operation, const char* action, std::uint64_t sequence) {
    MailboxRequest r{};
    r.pid=1; r.creation=1; r.sequence=sequence; r.expires=50000;
    strcpy_s(r.operation,operation); strcpy_s(r.action,action); strcpy_s(r.mode,"submit");
    strcpy_s(r.actor,"FRA"); strcpy_s(r.target,"FRA");
    strcpy_s(r.bound_action,"offer_fleet_basing_rights"); strcpy_s(r.bound_target,"POR");
    r.bound_submit_sequence=3;
    return r;
}
int main() {
    AcceptanceWindow w{};
    auto on=request("accept","accept_on",2), off=request("accept","accept_off",4);
    auto pair=request("pair","offer_fleet_basing_rights",3);strcpy_s(pair.target,"POR");
    strcpy_s(pair.bound_action,"none");strcpy_s(pair.bound_target,"none");pair.bound_submit_sequence=0;
    check(!reserve_on(w,on,0,false,1,2,3,4));
    check(!reserve_on(w,on,1,true,1,2,3,4));
    check(reserve_on(w,on,0,true,1,2,3,4));
    check(w.state==WindowState::pending_on);
    check(!permits(w,pair));check(!permits(w,off));
    w.state=WindowState::armed;
    check(permits(w,pair));check(!permits(w,off));check(!permits(w,on));
    auto wrong=pair;strcpy_s(wrong.target,"NAV");check(!permits(w,wrong));
    wrong=pair;strcpy_s(wrong.mode,"legality_only");check(!permits(w,wrong));
    wrong=pair;wrong.sequence=4;check(!permits(w,wrong));
    check(begin_bound_submit(w,pair));check(!begin_bound_submit(w,pair));check(!permits(w,off));
    w.state=WindowState::submitted_known;
    check(permits(w,off));check(!permits(w,pair));
    wrong=off;strcpy_s(wrong.bound_target,"NAV");check(!begin_bound_off(w,wrong));
    check(begin_bound_off(w,off));check(!begin_bound_off(w,off));
    w.state=WindowState::awaiting_health;w.off_frame=20;
    check(!observe_closed_boundary(w,0,true,20));check(!observe_closed_boundary(w,1,true,21));
    check(!observe_closed_boundary(w,0,false,21));check(observe_closed_boundary(w,0,true,21));
    check(w.on_sequence==2 && w.submit_sequence==3 && w.off_sequence==4);
    on.sequence=kMaxSequence-1;on.bound_submit_sequence=kMaxSequence;
    check(!reserve_on(w,on,0,true,1,2,3,4));
    on.sequence=kMaxSequence-2;on.bound_submit_sequence=kMaxSequence-1;
    check(reserve_on(w,on,0,true,1,2,3,4));check(w.off_sequence==kMaxSequence);
    fail_window(w);check(w.state==WindowState::unknown);check(!permits(w,pair));check(!permits(w,off));
    check(!observe_closed_boundary(w,0,true,999));
    std::printf("checks=%u failures=%u\n",checks,failures);
    return failures ? 1 : 0;
}
