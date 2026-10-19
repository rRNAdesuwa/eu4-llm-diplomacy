// Use the frozen real guard and its existing bounded fake-memory fixture.
// This is not a game process, an injected module, or an action sender.
#define main original_actor_guard_tests
#include "../../../bridge/native/tag_diplomacy_1375_v31/src/work/candidates/v26-gap-curry-bootstrap-1375/test_actor_guard.cpp"
#undef main
#include <limits>

namespace {
std::uint64_t Now=20;
std::uint64_t test_clock(void*) {return Now;}
eu4_spy_host18::Environment timed(Model& m) {auto e=m.env();e.clock=test_clock;return e;}
}

int main() {
    assert(original_actor_guard_tests()==0);
    {Model m;Now=20;v21guard::NativePairGuardDraft g(timed(m));
     assert(g.begin_frame()&&g.lease(request(),60021));assert(g.authority().final_owned_write(&g));}
    {Model m;Now=20;v21guard::NativePairGuardDraft g(timed(m));
     assert(g.begin_frame()&&g.lease(request(),21));assert(g.authority().final_owned_write(&g));Now=21;
     assert(!g.authority().final_owned_write(&g)&&g.frozen());}
    {Model m;Now=20;v21guard::NativePairGuardDraft g(timed(m));
     assert(g.begin_frame()&&g.lease(request(),1800020));Now=1800019;
     assert(g.authority().final_owned_write(&g));Now=1800020;
     assert(!g.authority().final_owned_write(&g)&&g.frozen());}
    for(const auto expiry:{19ULL,20ULL,1800021ULL,std::numeric_limits<unsigned long long>::max()}) {
     Model m;Now=20;v21guard::NativePairGuardDraft g(timed(m));
     assert(g.begin_frame()&&!g.lease(request(),expiry)&&g.frozen());}
    {Model m;Now=20;v21guard::NativePairGuardDraft g(timed(m));
     assert(g.begin_frame()&&g.lease(request(),1020));Now=19;
     assert(!g.authority().final_owned_write(&g)&&g.frozen());}
    {Model m;Now=20;v21guard::NativePairGuardDraft g(timed(m));
     assert(g.begin_frame()&&g.lease(request(),1020));Now=1021;
     // Known cleanup is separately authorized; an expired lease still cannot write.
     assert(g.authority().final_operation(&g,v21port::Call::ActionDestructor));
     assert(!g.authority().final_owned_write(&g)&&g.frozen());}
    std::puts("batch_ttl_boundary_cases=9 native_calls=0 game_access=0");return 0;
}
