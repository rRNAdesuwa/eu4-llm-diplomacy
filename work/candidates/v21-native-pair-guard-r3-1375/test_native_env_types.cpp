// Actual NativeEnvironment::sample on analysis-owned synthetic allocations.
// initialize() is NOT called. This is not game identity or OS authorization proof.
#include "native_env.h"
#include <cassert>
namespace eu4_spy_host18 {
struct NativeEnvironmentTests {
    static void run(unsigned bad) {
        auto* image=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x2341000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
        auto* db=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x1000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
        auto* array=static_cast<std::uintptr_t*>(VirtualAlloc(nullptr,0x1000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
        auto* pages=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x3000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
        assert(image&&db&&array&&pages);
        const auto base=reinterpret_cast<std::uintptr_t>(image),actor=reinterpret_cast<std::uintptr_t>(pages+0xff0),target=reinterpret_cast<std::uintptr_t>(pages+0x2000);
        auto store=[](void* p,const auto& value){std::memcpy(p,&value,sizeof(value));};
        store(image+0x233fe78,reinterpret_cast<std::uintptr_t>(db));store(image+0x233d8d0,reinterpret_cast<std::uintptr_t>(db));
        store(db+0x118,reinterpret_cast<std::uintptr_t>(array));store(db+0x124,std::int32_t{123});array[122]=actor;array[46]=target;
        store(pages+0xff0,base+(bad==0?0x1234:0x1c574a0));store(pages+0xff8,std::uint32_t{bad==1?0U:0x165U});
        store(pages+0x2000,base+0x1c574a0);store(pages+0x2008,std::uint32_t{0x165});
        DWORD previous=0;assert(VirtualProtect(pages+0x1000,0x1000,PAGE_NOACCESS,&previous));
        NativeEnvironment env;env.base_=base;env.owner_=GetCurrentThreadId();env.ready_=true;Frame frame{};
        assert(!env.sample(frame));
        // Unknown type/marker returns before the inaccessible derived +20.
        // With valid headers, that armed boundary is reached and the reader latches.
        assert(env.failed_==(bad==2));assert(env.calls_==(bad==0?7U:bad==1?8U:11U));
        assert(VirtualFree(pages,0,MEM_RELEASE)&&VirtualFree(array,0,MEM_RELEASE)&&VirtualFree(db,0,MEM_RELEASE)&&VirtualFree(image,0,MEM_RELEASE));
    }
};
}
int main(){for(unsigned bad=0;bad<3;++bad)eu4_spy_host18::NativeEnvironmentTests::run(bad);
    std::puts("native_env_type_groups=3 own_analysis_memory=true initialize_called=false game_access=0");return 0;}
