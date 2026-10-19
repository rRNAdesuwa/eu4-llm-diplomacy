#include "../v21-native-pair-guard-r3-1375/native_guard.h"
#include "../current-country-tag-cpp-r2-1375/selected_pins.h"
#include <cassert>
#include <cstring>
#include <map>
#include <cstdio>

namespace {
constexpr std::uint64_t Base=0x140000000ULL,DB=0x200000000ULL,Game=0x210000000ULL,Array=0x220000000ULL,Objects=0x230000000ULL;
std::uint64_t handle(const char* tag,unsigned slot) {
    return (1ULL<<56)|(static_cast<std::uint64_t>(slot)<<32)|static_cast<unsigned char>(tag[0])|
        (static_cast<std::uint64_t>(static_cast<unsigned char>(tag[1]))<<8)|(static_cast<std::uint64_t>(static_cast<unsigned char>(tag[2]))<<16);
}
struct Model {
    std::map<std::uint64_t,unsigned char> data;
    template<class T> void put(std::uint64_t p,T v) {const auto* b=reinterpret_cast<unsigned char*>(&v);for(unsigned i=0;i<sizeof(v);++i)data[p+i]=b[i];}
    template<class T> T get(std::uint64_t p) {T v{};auto* b=reinterpret_cast<unsigned char*>(&v);for(unsigned i=0;i<sizeof(v);++i)b[i]=data.at(p+i);return v;}
    Model() {
        put(Base+0x233d8d0,DB);put(Base+0x233fe78,Game);put(DB+0x118,Array);put(DB+0x120,4);put(DB+0x124,4);
        put(Game+0x1dd0,56456976);put(Game+0x1e60,handle("FRA",1));put(Game+0x1e68,std::uint64_t{0});
        put(Game+0x7485,std::uint8_t{0});put(Game+0x74c8,std::uint64_t{0});
        const char* tags[]={"---","FRA","ENG","POR"};
        for(unsigned i=0;i<4;++i) {const auto p=Objects+i*0x1000;put(Array+8*i,p);put(p,Base+0x1c574a0);put(p+8,std::uint32_t{0x165});put(p+0x20,i?handle(tags[i],i):std::uint64_t{0x2d2d2d});}
        for(const auto& p:country1375::SelectedPins)for(unsigned i=0;i<p.length;++i)data[Base+p.rva+i]=p.bytes[i];
    }
    static bool read(void* ptr,std::uintptr_t p,void* out,std::size_t n) {
        auto& m=*static_cast<Model*>(ptr);auto* b=static_cast<unsigned char*>(out);
        for(std::size_t i=0;i<n;++i) {const auto it=m.data.find(p+i);if(it==m.data.end())return false;b[i]=it->second;}return true;
    }
    static std::uint64_t clock(void*) {return 20;}
    static std::uint32_t thread(void*) {return 12;}
    static bool begin(void*) {return true;}
    static bool sample(void* ptr,eu4_spy_host18::Frame* out) {
        auto& m=*static_cast<Model*>(ptr);eu4_spy_host18::Frame f{};auto& s=f.stamp;
        s.game=Game;s.database=DB;s.countries=Array;s.player=m.get<std::uint64_t>(Game+0x1e60);s.date=m.get<std::int32_t>(Game+0x1dd0);
        s.actor_country=s.target_country=Objects+0x1000;s.actor=s.target=handle("FRA",1);s.server=0x240000000ULL;s.pause_manager=0x250000000ULL;
        f.countries_count=4;f.thread=12;f.effective_player=s.player;f.manual_pause=1;*out=f;return true;
    }
    eu4_spy_host18::Environment env() {
        eu4_spy_host18::Environment e{};e.user=this;e.image_base=Base;e.owner_thread=12;e.exact_disk_and_loaded_image_verified=true;
        e.identity.pid=111;e.identity.creation=777;std::memset(e.identity.session,'1',32);std::memset(e.identity.dll_sha256,'a',64);std::memset(e.identity.manifest_sha256,'b',64);
        e.read=read;e.clock=clock;e.current_thread=thread;e.begin_frame=begin;e.sample=sample;return e;
    }
};
v21pair::Request request(const char* actor="ENG",const char* target="POR") {v21pair::Request r{};assert(v21pair::make_request("trade_favors_for_gold",actor,target,r));return r;}
}
int main() {
    {Model m;v21guard::NativePairGuardDraft g(m.env());auto r=request();assert(g.begin_frame()&&g.lease(r,1020));v21pair::PairStamp s{};
     assert(g.stamp(r,s));assert(s.actor.value==handle("ENG",2)&&s.target.value==handle("POR",3)&&s.current_player.value==handle("FRA",1));
     assert(!(s.actor==s.current_player)&&g.authority().final_owned_write(&g));}
    {Model m;v21guard::NativePairGuardDraft g(m.env());assert(g.begin_frame()&&g.lease(request(),1020));m.put(Game+0x1e60,handle("POR",3));assert(!g.authority().final_owned_write(&g));}
    {Model m;v21guard::NativePairGuardDraft g(m.env());assert(g.begin_frame()&&g.lease(request(),1020));m.put(Objects+0x2020,handle("ENG",2)|(2ULL<<56));assert(!g.authority().final_owned_write(&g));}
    {Model m;v21guard::NativePairGuardDraft g(m.env());assert(g.begin_frame());assert(!g.lease(request("SCO"),1020));}
    std::puts("actor_guard_groups=4 native_calls=0 game_access=0");return 0;
}
