// Candidate source only: root may compile separately after review.
// No DLL build, process, engine function, game memory or mailbox access.
#include "files/work/native/v17/lab-request-1375.h"
#include <cstdio>
#include <cstring>

using namespace eu4_lab_1375;
AcceptanceWindow global_window{};
static AcceptanceWindow namespace_window{};
static AcceptanceWindow& function_window() { static AcceptanceWindow value{}; return value; }
static unsigned checks=0, failures=0;
static void check(bool value) { ++checks; if (!value) ++failures; }
static void initialized(AcceptanceWindow& value) {
    check(startup_window(value,true));
    check(initialize_startup_window(value));
    check(startup_window(value,false));
    check(!std::strcmp(value.action,"none") && !std::strcmp(value.target,"none"));
}
static void rejected_unchanged(AcceptanceWindow& value) {
    unsigned char before[sizeof(value)]; std::memcpy(before,&value,sizeof(value));
    check(!initialize_startup_window(value));
    check(!std::memcmp(before,&value,sizeof(value)));
}
int main() {
    AcceptanceWindow stack_window{};
    // Exercise the actual static/global layouts that v15's old stack-only test missed.
    initialized(global_window); initialized(namespace_window);
    initialized(function_window()); initialized(stack_window);
    AcceptanceWindow value{};
    std::memset(&value,0,sizeof(value)); initialized(value);
    initialized(value); // A still-pristine canonical input is accepted by the helper.
    // BridgeStart's installed CAS, not this helper, prevents a second startup call.
    for (unsigned index=0; index<11; ++index) {
        value=AcceptanceWindow{}; check(initialize_startup_window(value));
        switch(index) {
        case 0:value.state=WindowState::unknown;break;
        case 1:value.on_sequence=2;break;
        case 2:value.submit_sequence=3;break;
        case 3:value.off_sequence=4;break;
        case 4:value.world=0x10000;break;
        case 5:value.player=1;break;
        case 6:value.date=1;break;
        case 7:value.thread=1;break;
        case 8:value.off_frame=1;break;
        case 9:value.action[31]='x';break;
        case 10:value.target[4]='x';break;
        }
        rejected_unchanged(value);
    }
    value=AcceptanceWindow{}; check(initialize_startup_window(value));
    value.action[0]='x'; rejected_unchanged(value);
    value=AcceptanceWindow{}; check(initialize_startup_window(value));
    value.target[0]='x'; rejected_unchanged(value);
    value=AcceptanceWindow{}; check(initialize_startup_window(value));
    value.state=WindowState::awaiting_health;value.on_sequence=2;value.submit_sequence=3;value.off_sequence=4;
    value.world=0x100000;value.player=0x0100007a00415246ULL;value.date=56456976;value.thread=987;value.off_frame=10;
    strcpy_s(value.action,"offer_fleet_basing_rights");strcpy_s(value.target,"POR");
    check(observe_closed_boundary(value,0,true,11));
    check(value.state==WindowState::closed && value.on_sequence==2 && value.submit_sequence==3 && value.off_sequence==4);
    check(!std::strcmp(value.action,"offer_fleet_basing_rights") && !std::strcmp(value.target,"POR"));
    rejected_unchanged(value); // Successful close must retain its historical grant.
    std::printf("{\"event\":\"candidate_startup_window\",\"acceptance_state\":\"closed\",\"acceptance_origin_sequence\":%llu,\"acceptance_submit_sequence\":%llu,\"acceptance_off_sequence\":%llu,\"acceptance_action\":\"%s\",\"acceptance_target\":\"%s\"}\n",
        static_cast<unsigned long long>(global_window.on_sequence),static_cast<unsigned long long>(global_window.submit_sequence),
        static_cast<unsigned long long>(global_window.off_sequence),global_window.action,global_window.target);
    std::printf("checks=%u failures=%u\n",checks,failures);
    return failures ? 1 : 0;
}

