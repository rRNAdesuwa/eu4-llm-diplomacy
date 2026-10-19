#pragma once
#include <cstdint>

namespace eu4_spy_boot18 {
enum class Decision:unsigned { wait,health,request,terminal };
// Pure owner-entry pacing. No engine date is fabricated, and controller frame
// ordinals are intentionally distinct from these actual hook-entry counts.
struct Scheduler {
    std::uint64_t owner_entries=0,last_clock=0,last_sample=0,last_poll=0;
    std::uint32_t owner=0,completed=0;
    bool started=false,frozen=false,stopped=false;
    bool start(std::uint32_t thread) {
        if(started||!thread) { frozen=true;return false; }started=true;owner=thread;return true;
    }
    bool enter(std::uint32_t thread,std::uint64_t clock) {
        if(!started||frozen||thread!=owner||clock<last_clock||owner_entries==UINT64_MAX) { frozen=true;return false; }
        ++owner_entries;last_clock=clock;return true;
    }
    bool should_poll() const { return !frozen&&!stopped&&(last_poll==0||last_clock-last_poll>=100); }
    Decision decide(bool request_present) {
        if(frozen||!started)return Decision::terminal;
        if(stopped)return Decision::wait;
        if(request_present) { last_poll=last_clock;last_sample=last_clock;return Decision::request; }
        if(last_sample==0||last_clock-last_sample>=1000) { last_poll=last_clock;last_sample=last_clock;return Decision::health; }
        last_poll=last_clock;return Decision::wait;
    }
    void fail() { frozen=true; }
    void finish() { stopped=true; } // Only after third stage's independent later health.
};
}
