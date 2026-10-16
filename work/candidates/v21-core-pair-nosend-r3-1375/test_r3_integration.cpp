// The sealed adapter's actual private code + faithful Fake; real Win32Platform
// is neither compiled here nor linked. Old adapter/R2 sources remain untouched.
#define main retained_adapter_suite_main
#include "adapter/test_native_pair_engine.cpp"
#undef main
#include "typed_fixture.h"
#include <algorithm>
using typed_fixture::Memory;
using typed_fixture::spy_fixture;
unsigned groups=0;
void group(const char* name,const std::function<void()>& f){f();++groups;std::cout<<"PASS "<<name<<'\n';}
Request req(Action action){Request r{};r.action=action;r.actor.bytes={'F','R','A'};r.target.bytes={'E','N','G'};return r;}
bool read_at(const Memory& m,std::uint64_t a){return std::find(m.addresses.begin(),m.addresses.end(),a)!=m.addresses.end();}
void typed_rejections() {
    using namespace typed_fixture;
    // Each tuple is (mutation, last safe type read, first forbidden derived read).
    struct Bad {const char* name;std::function<void(Memory&,const PairStamp&)> mutate;std::uint64_t forbidden;};
    const std::vector<Bad> cases={
      {"holder_short",[](Memory& m,const PairStamp&s){m.put(s.actor_object+0x1488,holder+24);},holder+0x18},
      {"holder_overcap",[](Memory& m,const PairStamp&s){m.put(s.actor_object+0x1490,holder+17*8);},holder+0x18},
      {"holder_end_aftercap",[](Memory& m,const PairStamp&s){m.put(s.actor_object+0x1488,holder+40);},holder+0x18},
      {"holder_unaligned",[](Memory& m,const PairStamp&s){m.put(s.actor_object+0x1490,holder+33);},holder+0x18},
      {"manager_vt",[](Memory&m,const PairStamp&){m.put(manager,module+0x1234);},manager+8},
      {"manager_marker",[](Memory&m,const PairStamp&){m.put(manager+8,std::uint32_t{0x182});},manager+0x10},
      {"manager_token",[](Memory&m,const PairStamp&){m.put(manager+0x10,std::uint32_t{0x3378});},manager+0x14},
      {"manager_kind",[](Memory&m,const PairStamp&){m.put(manager+0x14,std::uint8_t{2});},manager+0x16},
      {"manager_owner_generation",[](Memory&m,const PairStamp&s){m.put(manager+0x16,s.actor.value^0x0100000000000000ULL);},manager+0x20},
      {"entry_vector_capacity",[](Memory&m,const PairStamp&){m.put(manager+0x30,begin+257*8);},begin},
      {"entry_vector_end",[](Memory&m,const PairStamp&){m.put(manager+0x28,begin+16);},begin},
      {"entry_vector_cap_before",[](Memory&m,const PairStamp&){m.put(manager+0x30,begin-8);},begin},
      {"entry_vector_cap_unaligned",[](Memory&m,const PairStamp&){m.put(manager+0x30,begin+9);},begin},
      {"entry_vt",[](Memory&m,const PairStamp&){m.put(entry,module+0x1234);},entry+8},
      {"entry_marker",[](Memory&m,const PairStamp&){m.put(entry+8,std::uint32_t{0x182});},entry+0x40},
      {"entry_kind",[](Memory&m,const PairStamp&){m.put(entry+0x40,std::uint8_t{2});},entry+0x18},
      {"entry_idle",[](Memory&m,const PairStamp&){m.put(entry+0x18,std::uint8_t{0});},entry+0x10},
      {"entry_unknown_state",[](Memory&m,const PairStamp&){m.put(entry+0x18,std::uint8_t{255});},entry+0x10},
      {"mission_vt",[](Memory&m,const PairStamp&){m.put(mission,module+0x1234);},mission+8},
      {"mission_marker",[](Memory&m,const PairStamp&){m.put(mission+8,std::uint32_t{0x165});},mission+0xa0},
      {"task_vt",[](Memory&m,const PairStamp&){m.put(task,module+0x1234);},task+0x20},
    };
    for(const auto& bad:cases)group(bad.name,[&]{Memory m;const auto s=sample();spy_fixture(m,s);bad.mutate(m,s);SpyBinding b{};
       CHECK(!bind_spy_once(m,module,s,b));CHECK(!read_at(m,bad.forbidden));CHECK(m.reads<=8192);});
    group("valid_typed_transcript",[]{Memory m;auto s=sample();spy_fixture(m,s);SpyBinding b{};CHECK(bind_spy_two_pass(m,module,s,b));
       CHECK(read_at(m,manager+0x16) && read_at(m,entry+0x40) && read_at(m,mission+8));CHECK(b.envoy==17);});
    group("changed_type_between_passes",[]{Memory m;auto s=sample();spy_fixture(m,s);unsigned n=0;m.hook=[&](Memory& x,std::uint64_t a){if(a==manager && ++n==2)x.put(manager,module+0x1234);};
       SpyBinding b{};CHECK(!bind_spy_two_pass(m,module,s,b));});
    group("duplicate_idle_entry",[]{Memory m;auto s=sample();spy_fixture(m,s);m.put(manager+0x28,begin+16);m.put(manager+0x30,begin+16);m.put(begin+8,entry);m.put(entry+0x18,std::uint8_t{0});
       SpyBinding b{};CHECK(!bind_spy_once(m,module,s,b));});
}
int main(){try{
    group("all_twelve_with_faithful_adapter",[]{for(unsigned n=0;n<12;++n){Fake f;f.native_envoy=17;Guard g;Memory m;spy_fixture(m,g.s);NativePairEngineDraft e(f);
        const auto r=preflight_no_send(req(static_cast<Action>(n)),g,e,100,&m,f.module());CHECK(r.status==Status::ModelComplete);
        CHECK(e.diagnostics().live==0 && f.deletes==2 && !r.submitted && !r.native_ready && !e.diagnostics().runtime_verified);CHECK(f.writes==9);
    }});
    for(auto envoy:{0,17,2147483647})group("native_envoy_exact_endpoint",[&]{using namespace typed_fixture;Fake f;f.native_envoy=envoy;Guard g;Memory m;spy_fixture(m,g.s);
        m.put(entry+0x44,envoy);m.put(mission+0x50,envoy);m.put(task+0x2c,envoy);NativePairEngineDraft e(f);
        CHECK(preflight_no_send(req(Action::StopSpyNetwork),g,e,100,&m,f.module()).status==Status::ModelComplete);CHECK(f.writes==9);});
    for(auto envoy:{-1,18,2147483647})group("native_envoy_mismatch_no_overwrite",[&]{Fake f;f.native_envoy=envoy;Guard g;Memory m;spy_fixture(m,g.s);NativePairEngineDraft e(f);
        CHECK(preflight_no_send(req(Action::StopSpyNetwork),g,e,100,&m,f.module()).status==Status::Frozen);
        CHECK(f.native_entries==2 && f.deletes==0 && f.writes==9);CHECK(f.get<std::int32_t>(f.last_original+0x30)==envoy);});
    group("native_setter_state_change",[]{Fake f;f.native_envoy=17;f.after=[](Call c,Fake&q){if(c==Call::Setter)q.set(q.last_original+0x34,std::uint32_t{2});};
        Guard g;Memory m;spy_fixture(m,g.s);NativePairEngineDraft e(f);CHECK(preflight_no_send(req(Action::StopSpyNetwork),g,e,100,&m,f.module()).status==Status::Frozen);
        CHECK(f.native_entries==2 && f.deletes==0);});
    for(unsigned variant=0;variant<4;++variant)group("post_setter_graph_or_clock_change",[&]{using namespace typed_fixture;Fake f;f.native_envoy=17;Guard g;Memory m;spy_fixture(m,g.s);NativePairEngineDraft e(f);
        m.hook=[&](Memory& x,std::uint64_t a){if(f.native_entries==2 && a==g.s.game+0x7485){
          if(variant==0)g.now=100;if(variant==1)g.now=0;if(variant==2)x.put(entry+0x40,std::uint8_t{4});if(variant==3)g.s.session=444;}};
        CHECK(preflight_no_send(req(Action::StopSpyNetwork),g,e,100,&m,f.module()).status==Status::Frozen);CHECK(f.native_entries==2 && f.deletes==0);});
    group("readonly_confirmation_no_write",[]{Fake f;f.native_envoy=17;NativePairEngineDraft e(f);const auto&p=profiles()[4];auto a=e.factory(p);e.initialize_owned(a,sample());e.mode_setter(p,a,false);
        const auto writes=f.writes;CHECK(e.bind_envoy_owned(a,17));CHECK(f.writes==writes);ActionView v{};e.action_view(a,v);CHECK(v.envoy==17);});
    typed_rejections();
    std::cout<<"r3_groups="<<groups<<" checks="<<checks<<" twelve_component_modes=true native_calls=0 fake_only=true\n";return 0;
}catch(const std::exception&e){std::cerr<<"R3 FAIL "<<e.what()<<" groups="<<groups<<'\n';return 1;}catch(...){std::cerr<<"R3 unexpected fault groups="<<groups<<'\n';return 2;}}
