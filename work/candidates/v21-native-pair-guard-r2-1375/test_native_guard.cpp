// Reuse the sealed in-memory fixture, not its tests or any OS reader.
#define main stored_country_fixture_entry
#include "../current-country-tag-cpp-1375/test_country_resolver.cpp"
#undef main
#include "native_guard.h"
#include "fake_platform.h"
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
constexpr std::uint64_t Records=0x230000000,Root=0x230100000,Holder=0x230200000,Manager=0x230300000,
    Entries=0x230400000,Entry=0x230500000,Mission=0x230600000,Task=0x230700000,Owner=0x230800000,Node=0x230900000;
void spy_fixture(Model& m) {
    auto& x=m.memory;const auto actor=handle("FRA",1),target=handle("ENG",2);
    x.put(Objects+0x1000+0x1510,Records);const auto rec=Records+2*0x48;
    x.put(rec,Root);x.put(rec+8,actor);x.put(rec+0x10,target);x.put(rec+0x46,std::uint8_t{8});
    x.put(Objects+0x1000+0x1480,Holder);x.put(Objects+0x1000+0x1488,Holder+32);x.put(Objects+0x1000+0x1490,Holder+32);
    x.put(Holder+0x18,Manager);x.put(Manager,Base+0x1cac380);x.put(Manager+8,std::uint32_t{0x165});
    x.put(Manager+0x10,std::uint32_t{0x2746});x.put(Manager+0x14,std::uint8_t{3});x.put(Manager+0x16,actor);
    x.put(Manager+0x20,Entries);x.put(Manager+0x28,Entries+8);x.put(Manager+0x30,Entries+8);x.put(Entries,Entry);
    x.put(Entry,Base+0x1cac2f0);x.put(Entry+8,std::uint32_t{0x165});x.put(Entry+0x40,std::uint8_t{3});
    x.put(Entry+0x18,std::uint8_t{2});x.put(Entry+0x10,Mission);x.put(Entry+0x44,std::int32_t{17});
    x.put(Mission,Base+0x1c4b2b8);x.put(Mission+8,std::uint32_t{0x182});x.put(Mission+0xa0,Task);
    x.put(Mission+0x80,actor);x.put(Mission+0x88,target);x.put(Mission+0xa8,std::uint32_t{0x3378});
    x.put(Mission+0x48,Entry);x.put(Mission+0x50,std::int32_t{17});
    x.put(Task,Base+0x1ce3ba0);x.put(Task+0x20,target);x.put(Task+0x18,actor);x.put(Task+0x28,std::uint8_t{0});
    x.put(Task+0x2c,std::int32_t{17});x.put(Task+0x10,Owner);
    x.put(Objects+0x2000+0x14b0,Owner);x.put(Owner+0x4f0,Node);x.put(Owner+0x4f8,Node);x.put(Owner+0x500,std::uint32_t{1});
    x.put(Node,Task);x.put(Node+8,std::uint64_t{0});x.put(Node+0x10,std::uint64_t{0});x.put(Node+0x18,std::uint8_t{0});
}
v21pair::Request stop_spy() {auto r=request();r.action=v21pair::Action::StopSpyNetwork;return r;}
struct BoundPlatform final:v21port::Platform {
    fixture::Fake memory;v21port::Authority auth;std::function<void(v21port::Call)> preparation;
    explicit BoundPlatform(v21guard::NativePairGuardDraft& guard):auth(guard.authority()){memory.native_envoy=17;}
    v21port::Address module()const noexcept override{return Base;}
    bool ready()override{return auth.fresh(auth.user,Base,12);}
    bool region(v21port::Address p,v21port::Region& out)override{return memory.region(p,out);}
    bool read(v21port::Address p,void* out,std::size_t n)override{return memory.read(p,out,n);}
    bool write(v21port::Address p,const void* in,std::size_t n)override{
        return auth.final_owned_write(auth.user)&&memory.write(p,in,n);
    }
    v21port::Return invoke(v21port::Call call,const v21pair::Profile& profile,v21port::Address object,bool mode)override {
        if(preparation)preparation(call);if(!auth.final_operation(auth.user,call))return {};
        return memory.invoke(call,profile,object,mode);
    }
};
}
int main() {
    groups=0;
    group("private_source_full_pair_and_labels",[] {Model m;v21guard::NativePairGuardDraft g(m.environment());bind(g,m);v21pair::PairStamp s{};
        assert(g.stamp(request(),s)&&s.actor.value==handle("FRA",1)&&s.target.value==handle("ENG",2)&&s.current_player==s.actor&&s.process_creation==777);
        assert(g.authority().fresh(&g,Base,12)&&g.authority().final_operation(&g,v21port::Call::Full88)&&!g.frozen());});
    group("single_lease_no_rearm",[] {Model m;v21guard::NativePairGuardDraft g(m.environment());bind(g,m);assert(!g.lease(request(),m.now+1000)&&g.frozen());});
    group("bounded_original_ttl",[] {for(const std::uint64_t delta:{std::uint64_t{0},std::uint64_t{60001}}) {Model m;v21guard::NativePairGuardDraft g(m.environment());assert(g.begin_frame());assert(!g.lease(request(),m.now+delta));}});
    group("stop_spy_requires_typed_graph",[] {Model m;v21guard::NativePairGuardDraft g(m.environment());assert(g.begin_frame());v21pair::Request r{};
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
    group("stop_spy_typed_lease_and_final_authority",[] {Model m;spy_fixture(m);v21guard::NativePairGuardDraft g(m.environment());
        assert(g.begin_frame()&&g.lease(stop_spy(),1020));assert(g.authority().final_operation(&g,v21port::Call::Full88));});
    group("spy_last_graph_change_refuses",[] {Model m;spy_fixture(m);v21guard::NativePairGuardDraft g(m.environment());assert(g.begin_frame()&&g.lease(stop_spy(),1020));
        m.memory.put(Entry+0x40,std::uint8_t{2});assert(!g.authority().final_operation(&g,v21port::Call::Setter)&&g.frozen());});
    group("spy_graph_read_cannot_lend_expired_clock",[] {Model m;spy_fixture(m);v21guard::NativePairGuardDraft g(m.environment());assert(g.begin_frame()&&g.lease(stop_spy(),1020));
        m.memory.callback=[&](Memory&,std::uint64_t a,std::size_t){if(a==Task)m.now=1020;};assert(!g.authority().final_owned_write(&g));});
    group("six_positive_modes_with_actual_guard_and_adapter",[] {for(unsigned i=0;i<12;i+=2) {
        Model m;v21guard::NativePairGuardDraft g(m.environment());auto r=request();r.action=static_cast<v21pair::Action>(i);
        assert(g.begin_frame()&&g.lease(r,1020));BoundPlatform p(g);v21port::NativePairEngineDraft engine(p);
        const auto result=v21pair::preflight_no_send(r,g,engine,1020,&g,Base);
        assert(result.status==v21pair::Status::ModelComplete&&!g.frozen()&&p.memory.deletes==2&&engine.diagnostics().live==0);
    }});
    group("stop_spy_with_actual_guard_and_adapter",[] {Model m;spy_fixture(m);v21guard::NativePairGuardDraft g(m.environment());
        assert(g.begin_frame()&&g.lease(stop_spy(),1020));BoundPlatform p(g);v21port::NativePairEngineDraft engine(p);
        const auto result=v21pair::preflight_no_send(stop_spy(),g,engine,1020,&g,Base);
        assert(result.status==v21pair::Status::ModelComplete&&!g.frozen()&&p.memory.deletes==2&&p.memory.writes==9);
    });
    group("late_bound_platform_change_prevents_fake_entry",[] {Model m;v21guard::NativePairGuardDraft g(m.environment());bind(g,m);BoundPlatform p(g);v21port::NativePairEngineDraft engine(p);
        p.preparation=[&](v21port::Call c){if(c==v21port::Call::Full88)m.now=1020;};
        const auto result=v21pair::preflight_no_send(request(),g,engine,1020,&g,Base);
        assert(result.status==v21pair::Status::Frozen&&p.memory.native_entries==2&&p.memory.deletes==0);
    });
    std::printf("guard_groups=%zu native_calls=0 game_access=0\n",groups);return 0;
}
