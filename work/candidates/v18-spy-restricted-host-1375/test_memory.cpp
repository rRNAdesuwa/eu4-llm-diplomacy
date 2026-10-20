#include "native_env.h"
#include <cstdio>
#include <cstring>
#include <initializer_list>
namespace eu4_spy_host18 {
struct NativeEnvironmentTests {
    unsigned checks=0,failed=0;
    void check(bool yes,const char* name) { ++checks;if(!yes) { ++failed;std::printf("FAIL %s\n",name); } }
    template<class T> void put(std::uintptr_t p,T v) { std::memcpy(reinterpret_cast<void*>(p),&v,sizeof(v)); }
    unsigned run() {
        // Only mock-owned VirtualAlloc pages; initialize()/process introspection
        // and every resolved engine function remain completely uncalled.
        auto memory=reinterpret_cast<std::uintptr_t>(VirtualAlloc(nullptr,0x2600000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
        check(memory!=0,"mock pages");if(!memory)return failed;
        const auto game=memory+0x10000,db=memory+0x20000,countries=memory+0x30000,actor=memory+0x40000,target=memory+0x50000;
        const auto server=memory+0x60000,pause=memory+0x70000,holder=memory+0x80000,context=memory+0x90000,node=memory+0xa0000;
        put(memory+0x233fe78,game);put(memory+0x233d8d0,db);put(db+0x118,countries);put<std::int32_t>(db+0x124,4096);
        put(countries+122*8,actor);put(countries+46*8,target);put<std::uint64_t>(actor+0x20,0x0100007a00415246ULL);put<std::uint64_t>(target+0x20,0x0100002e00474e45ULL);
        put<std::uint64_t>(actor+0x18f0,0x2d2d2d);put<std::uint64_t>(target+0x18f0,0x2d2d2d);
        put<std::uint64_t>(game+0x1e60,0x0100007a00415246ULL);put<std::int32_t>(game+0x1dd0,56456976);put(game+0x1e00,server);
        put(server,memory+0x1cb8460);put(server+0x418,pause);put(pause+0x50,server);put<std::uint8_t>(pause+0x48,1);
        NativeEnvironment env;env.base_=memory;env.owner_=GetCurrentThreadId();env.ready_=true;
        Frame f{};check(env.sample(f)&&f.countries_count==4096&&f.stamp.actor==0x0100007a00415246ULL&&f.effective_player==f.stamp.actor,"exact fake-world sampling");
        check(!f.multiplayer_classifier,"classifier gate0");
        put<std::uint8_t>(server+0x19f1,1);put(server+0x330,holder);put(holder+0x370,context);
        check(env.sample(f)&&f.multiplayer_classifier,"context00 classifier true");
        put<std::uint8_t>(context+0x54,1);put<std::uint32_t>(context+0x8c,22);
        check(env.sample(f)&&!f.multiplayer_classifier,"empty chain false is not strictSP proof");
        put(game+0xa50,node);put<std::uint32_t>(node+0x18,22);
        check(env.sample(f)&&!f.multiplayer_classifier,"local only chain");put<std::uint32_t>(node+0x18,23);
        check(env.sample(f)&&f.multiplayer_classifier,"foreign chain member");put(node+0x60,node);
        check(!env.sample(f),"cycle rejected");put<std::uintptr_t>(node+0x60,0);put<std::uintptr_t>(game+0xa50,0);
        put<std::uint8_t>(context+0x55,2);check(!env.sample(f),"bool width strict");put<std::uint8_t>(context+0x55,0);
        put<std::int32_t>(db+0x124,122);check(!env.sample(f),"count excludes actor");put<std::int32_t>(db+0x124,4097);check(!env.sample(f),"count upper bound");put<std::int32_t>(db+0x124,4096);
        put<std::uint8_t>(game+0x1e66,7);put<std::uint8_t>(game+0x1e6f,1);put<std::uint64_t>(game+0x1e68,0x0100002e00474e45ULL);
        check(env.sample(f)&&f.effective_player==0x0100002e00474e45ULL,"effective alternate read not guessed current");
        // Sampler reports raw profile values; Controller tests enforce reject.
        for(unsigned size:{0U,65U}) { NativeEnvironment e;char bytes[65]{};check(!e.read(memory,bytes,size)&&e.failed_,"read size failure terminal"); }
        { NativeEnvironment e;e.calls_=262144;std::uint8_t v=0;check(!e.read(memory,&v,1)&&e.failed_,"call budget"); }
        { NativeEnvironment e;e.bytes_=16777216;std::uint8_t v=0;check(!e.read(memory,&v,1)&&e.failed_,"byte budget"); }
        { NativeEnvironment e;e.ready_=true;e.owner_=GetCurrentThreadId();std::uint32_t value=42;check(e.write(memory,&value,4),"mock private write");
            check(!e.write(memory,&value,2)&&e.failed_,"write widths restricted"); }
        { NativeEnvironment e;DWORD prior=0;check(VirtualProtect(reinterpret_cast<void*>(memory),4096,PAGE_NOACCESS,&prior)!=0,"protect mockpage");
            std::uint8_t v=0;check(!e.read(memory,&v,1)&&e.failed_,"unreadable VM fails closed");check(VirtualProtect(reinterpret_cast<void*>(memory),4096,prior,&prior)!=0,"restore own mockpage"); }
        check(VirtualFree(reinterpret_cast<void*>(memory),0,MEM_RELEASE)!=0,"release exact allocation");
        std::printf("memory_checks=%u failures=%u actual_initialize_called=false\n",checks,failed);return failed;
    }
};
}
int main() { eu4_spy_host18::NativeEnvironmentTests test;return test.run()?1:0; }
