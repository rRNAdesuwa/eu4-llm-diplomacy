#include "installer.h"
#include <cstdio>
#include <cstring>
extern "C" void research_frame_stub();
extern "C" void research_original_trampoline();
extern "C" { void* research_trampoline=nullptr;void* research_return=nullptr; }
namespace eu4_spy_boot19 {
namespace {
using NextThread=LONG(NTAPI*)(HANDLE,HANDLE,ACCESS_MASK,ULONG,ULONG,PHANDLE);
NextThread next_thread=nullptr;
constexpr unsigned char prefix[20]={0x4c,0x89,0x44,0x24,0x18,0x55,0x53,0x57,0x48,0x8d,0x6c,0x24,0xb0,0x48,0x81,0xec,0x50,0x01,0x00,0x00};
constexpr std::uintptr_t frame_rva=0x10a6ec0;
#include "thread_freeze.inc"
bool matches(const unsigned char* target) {
    __try { return !std::memcmp(target,prefix,sizeof(prefix))&&target[20]==0x48&&target[21]==0x8b&&target[22]==0x15; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
unsigned patch_once(unsigned char* target,const unsigned char* patch) {
    DWORD old=0;if(!VirtualProtect(target,sizeof(prefix),PAGE_EXECUTE_READWRITE,&old))return 23;
    unsigned result=0;
    __try {
        std::memcpy(target,patch,sizeof(prefix));DWORD ignored=0;
        if(!FlushInstructionCache(GetCurrentProcess(),target,sizeof(prefix))||!VirtualProtect(target,sizeof(prefix),old,&ignored)) {
            std::memcpy(target,prefix,sizeof(prefix));
            const bool flushed=FlushInstructionCache(GetCurrentProcess(),target,sizeof(prefix))!=FALSE;
            const bool restored=VirtualProtect(target,sizeof(prefix),old,&ignored)!=FALSE;
            result=flushed&&restored?24:29;
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) { result=29; }
    return result; // Any patch-stage failure is terminal; never try patching again.
}
}
bool install_owner_hook(std::uintptr_t base,InstallLog log,void* user) {
    if(!base||!log)return false;
    const HMODULE module=GetModuleHandleW(L"ntdll.dll");const auto address=module?GetProcAddress(module,"NtGetNextThread"):nullptr;
    static_assert(sizeof(next_thread)==sizeof(address));std::memcpy(&next_thread,&address,sizeof(address));if(!next_thread)return false;
    auto* target=reinterpret_cast<unsigned char*>(base+frame_rva);if(!matches(target))return false;
    research_return=target+sizeof(prefix);research_trampoline=reinterpret_cast<void*>(&research_original_trampoline);
    unsigned char patch[20];std::memset(patch,0x90,sizeof(patch));patch[0]=0xff;patch[1]=0x25;std::memset(patch+2,0,4);
    const auto destination=reinterpret_cast<std::uintptr_t>(&research_frame_stub);std::memcpy(patch+6,&destination,8);
    for(unsigned attempt=1;attempt<=3;++attempt) {
        unsigned result=0,details[8]{};std::uintptr_t rip=0;
        {
            ThreadSet threads;
            if(!threads.collect()||!threads.freeze(reinterpret_cast<std::uintptr_t>(target)))result=21;
            else if(!matches(target))result=22;
            else result=patch_once(target,patch);
            if(!threads.release())result=28;
            details[0]=threads.failure;details[1]=threads.error;details[2]=threads.failure_thread;
            details[3]=threads.count;details[4]=threads.suspended;details[5]=threads.resume_failures;
            details[6]=threads.resume_error;details[7]=threads.resume_failure_thread;rip=threads.failure_rip;
        }
        const bool unchanged=matches(target);const bool retry=result==21&&unchanged&&attempt<3;
        char record[1024]{};const int n=std::snprintf(record,sizeof(record),
            "{\"event\":\"hook_install_attempt\",\"attempt\":%u,\"result\":%u,\"prefix_unchanged\":%s,\"retrying\":%s,\"failure_stage\":%u,\"error\":%u,\"failure_thread\":%u,\"collected\":%u,\"suspended\":%u,\"resume_failures\":%u,\"resume_error\":%u,\"resume_thread\":%u,\"rip\":%llu,\"send_supported\":false}\n",
            attempt,result,unchanged?"true":"false",retry?"true":"false",details[0],details[1],details[2],details[3],details[4],details[5],details[6],details[7],static_cast<unsigned long long>(rip));
        if(n<1||static_cast<std::size_t>(n)>=sizeof(record)||!log(user,record,static_cast<std::size_t>(n)))return false;
        if(!result)return true;
        if(!retry)return false;
        Sleep(1); // Owned suspension counts and handles have all been released.
    }
    return false;
}
}
