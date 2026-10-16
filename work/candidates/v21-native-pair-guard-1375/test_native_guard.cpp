// Reuse the sealed in-memory fixture, not its tests or any OS reader.
#define main stored_country_fixture_entry
#include "../current-country-tag-cpp-1375/test_country_resolver.cpp"
#undef main
#include "native_guard.h"
#include <cstring>
#include <limits>

namespace {
struct Model {
    Memory memory;
    std::uint64_t now{20};std::uint32_t thread{12};std::uint8_t pause{1},ironman{};
    bool multiplayer{},fail_frame{},fail_sample{};unsigned begin_calls{};
    std::function<void(Model&)> sample_callback;
    template<class T>T value(std::uint64_t a) {
        T result{};auto* p=reinterpret_cast<std::uint8_t*>(&result);
        for(std::size_t i=0;i<sizeof(T);++i)p[i]=memory.data.at(a+i);return result;
    }
    static bool read(void* p,std::uintptr_t a,void* b,std::size_t n) {return static_cast<Model*>(p)->memory.read(a,b,n);}
    static std::uint64_t clock(void* p) {return static_cast<Model*>(p)->now;}
    static std::uint32_t current_thread(void* p) {return static_cast<Model*>(p)->thread;}
    static bool begin(void* p) {auto& m=*static_cast<Model*>(p);++m.begin_calls;return !m.fail_frame;}
    static bool sample(void* p,eu4_spy_host18::Frame* frame) {
        auto& m=*static_cast<Model*>(p);if(m.sample_callback)m.sample_callback(m);if(m.fail_sample)return false;
        eu4_spy_host18::Frame f{};auto& s=f.stamp;
        s.game=Game;s.database=DB;s.countries=Array;s.actor_country=Objects+0x1000;s.target_country=Objects+0x2000;
        s.server=0x220000000;s.pause_manager=0x220100000;s.actor=m.value<std::uint64_t>(s.actor_country+0x20);s.target=m.value<std::uint64_t>(s.target_country+0x20);
        s.player=m.value<std::uint64_t>(Game+0x1e60);s.date=m.value<std::int32_t>(Game+0x1dd0);
        f.countries_count=m.value<std::uint32_t>(DB+0x124);f.thread=m.thread;f.actor_overlord=f.target_overlord=0x2d2d2d;f.effective_player=s.player;
        f.manual_pause=m.pause;f.ironman=m.ironman;f.multiplayer_classifier=m.multiplayer;f.reset=m.value<std::uint8_t>(Game+0x7485);
        f.selector=m.value<std::uint8_t>(Game+0x1e66);f.load_source=m.value<std::uint64_t>(Game+0x74c8);*frame=f;return true;
    }
    eu4_spy_host18::Environment environment() {
        eu4_spy_host18::Environment e{};e.user=this;e.image_base=Base;e.owner_thread=12;e.mock=false;e.exact_disk_and_loaded_image_verified=true;
        e.identity.pid=111;e.identity.creation=777;
        std::memset(e.identity.session,'1',32);std::memset(e.identity.dll_sha256,'a',64);std::memset(e.identity.manifest_sha256,'b',64);
        e.read=read;e.clock=clock;e.sample=sample;e.current_thread=current_thread;e.begin_frame=begin;return e;
    }
};
v21pair::Request request() {v21pair::Request r{};assert(v21pair::make_request("guarantee","FRA","ENG",r));return r;}
void bind(v21guard::NativePairGuardDraft& g,Model& m) {assert(g.begin_frame());assert(g.lease(request(),m.now+1000));}
}
int main() {
    groups=0;
    group("private_source_full_pair_and_labels",[] {Model m;v21guard::NativePairGuardDraft g(m.environment());bind(g,m);v21pair::PairStamp s{};
        assert(g.stamp(request(),s)&&s.actor.value==handle("FRA",1)&&s.target.value==handle("ENG",2)&&s.current_player==s.actor&&s.process_creation==777);
        assert(g.authority().fresh(&g,Base,12)&&g.authority().final_operation(&g,v21port::Call::Full88)&&!g.frozen());});
    group("single_lease_no_rearm",[] {Model m;v21guard::NativePairGuardDraft g(m.environment());bind(g,m);assert(!g.lease(request(),m.now+1000)&&g.frozen());});
    group("bounded_original_ttl",[] {for(const std::uint64_t delta:{std::uint64_t{0},std::uint64_t{60001}}) {Model m;v21guard::NativePairGuardDraft g(m.environment());assert(g.begin_frame());assert(!g.lease(request(),m.now+delta));}});
    group("stop_spy_explicit_integration_block",[] {Model m;v21guard::NativePairGuardDraft g(m.environment());assert(g.begin_frame());v21pair::Request r{};
        assert(v21pair::make_request("stop_building_spy_network","FRA","ENG",r));assert(!g.lease(r,m.now+1000));});
    group("mock_flag_does_not_authenticate",[] {Model m;auto e=m.environment();e.mock=true;v21guard::NativePairGuardDraft g(e);assert(!g.begin_frame());});
    group("source_identity_and_owner",[] {for(unsigned i=0;i<4;++i) {Model m;auto e=m.environment();
        if(i==0)e.identity.creation=0;if(i==1)e.exact_disk_and_loaded_image_verified=false;if(i==2)m.thread=13;if(i==3)e.read=nullptr;
        v21guard::NativePairGuardDraft g(e);assert(!g.begin_frame());}});
    group("health_pause_ironman_classifier",[] {for(unsigned i=0;i<3;++i) {Model m;if(i==0)m.pause=0;if(i==1)m.ironman=1;if(i==2)m.multiplayer=true;
        v21guard::NativePairGuardDraft g(m.environment());assert(g.begin_frame());assert(!g.lease(request(),m.now+1000));}});
    group("read64_adapter_exact_logical_extent",[] {Model m;v21guard::NativePairGuardDraft g(m.environment());assert(g.begin_frame());std::array<std::uint8_t,128> b{};
        for(std::size_t i=0;i<b.size();++i)m.memory.data[0x230000000+i]=static_cast<std::uint8_t>(i);
        assert(g.read(0x230000000,b.data(),b.size()));assert(m.memory.reads.size()==2&&m.memory.reads[0].second==64&&m.memory.reads[1].second==64);});
    group("wrong_request_or_module_owner",[] {Model m;v21guard::NativePairGuardDraft g(m.environment());bind(g,m);auto r=request();r.target.bytes={'P','O','R'};v21pair::PairStamp s{};
        assert(!g.stamp(r,s));Model n;v21guard::NativePairGuardDraft h(n.environment());bind(h,n);assert(!h.authority().fresh(&h,Base,13));});
    group("light_world_generation_and_date",[] {for(bool generation:{false,true}) {Model m;v21guard::NativePairGuardDraft g(m.environment());bind(g,m);
        if(generation)m.memory.put(Objects+0x2020,handle("ENG",2,3));else m.memory.put(Game+0x1dd0,std::int32_t{56456977});
        assert(!g.authority().fresh(&g,Base,12));}});
    group("final_read_expiry_and_rewind",[] {for(bool rewind:{false,true}) {Model m;v21guard::NativePairGuardDraft g(m.environment());bind(g,m);
        m.memory.callback=[&](Memory&,std::uint64_t a,std::size_t){if(a==Game+0x7485)m.now=rewind?0:1020;};
        assert(!g.authority().final_operation(&g,v21port::Call::Full88)&&g.frozen());}});
    group("expired_known_cleanup_only",[] {Model m;v21guard::NativePairGuardDraft g(m.environment());bind(g,m);m.now=1020;
        assert(g.authority().final_operation(&g,v21port::Call::ActionDestructor));assert(g.authority().final_operation(&g,v21port::Call::CommandDestructor));
        assert(!g.authority().final_owned_write(&g));});
    group("late_sample_changes_owner",[] {Model m;v21guard::NativePairGuardDraft g(m.environment());bind(g,m);m.sample_callback=[](Model& x){x.thread=13;};
        assert(!g.authority().final_owned_write(&g));});
    group("untrusted_type_before_light_handle",[] {Model m;v21guard::NativePairGuardDraft g(m.environment());bind(g,m);m.memory.put(Objects+0x2000,std::uint64_t{Base+0x1234});
        m.memory.reads.clear();assert(!g.authority().fresh(&g,Base,12));for(const auto& r:m.memory.reads)assert(r.first!=Objects+0x2020);});
    group("partial_short_read_terminal",[] {Model m;v21guard::NativePairGuardDraft g(m.environment());bind(g,m);m.memory.data.erase(Game+0x7485);
        assert(!g.authority().fresh(&g,Base,12)&&g.frozen());assert(!g.begin_frame());});
    group("reentry_terminal",[] {Model m;v21guard::NativePairGuardDraft g(m.environment());bind(g,m);bool tried=false;
        m.sample_callback=[&](Model&){if(!tried){tried=true;v21pair::PairStamp s{};assert(!g.stamp(request(),s));}};
        assert(!g.authority().fresh(&g,Base,12)&&g.frozen());});
    std::printf("guard_groups=%zu native_calls=0 game_access=0\n",groups);return 0;
}
