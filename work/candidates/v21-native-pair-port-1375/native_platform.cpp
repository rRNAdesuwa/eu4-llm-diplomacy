// Compiled to an object ONLY. Not linked into or executed by the mock program.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cstring>
#include "native_platform.h"
#include "native_pins.h"

namespace v21port {
namespace {
constexpr Address max_user=0x800000000000ULL;
bool safe_fresh(const Authority& a,Address base,std::uint32_t owner) {
    __try{return a.fresh && a.fresh(a.user,base,owner);}
    __except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
bool safe_last(const Authority& a,Call kind,bool write) {
    __try{return write?(a.final_owned_write && a.final_owned_write(a.user)):(a.final_operation && a.final_operation(a.user,kind));}
    __except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
bool range(Address p,std::size_t n,DWORD type,DWORD protect) {
    if(p<0x10000 || p>=max_user || !n || n>max_user-p)return false;
    MEMORY_BASIC_INFORMATION m{};
    if(VirtualQuery(reinterpret_cast<const void*>(p),&m,sizeof(m))!=sizeof(m))return false;
    const auto b=reinterpret_cast<Address>(m.BaseAddress);
    return m.State==MEM_COMMIT && m.Type==type && m.Protect==protect && b<=p && p-b<m.RegionSize && n<=m.RegionSize-(p-b);
}
bool private_copy(Address p,void* out,const void* in,std::size_t n,const Authority* a=nullptr) {
    if(!n || n>64 || !range(p,n,MEM_PRIVATE,PAGE_READWRITE))return false;
    if(in && (!a || !safe_last(*a,Call::Factory,true)))return false;
    __try {if(out)std::memcpy(out,reinterpret_cast<const void*>(p),n);else std::memcpy(reinterpret_cast<void*>(p),in,n);return true;}
    __except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
int digit(char c) {return c>='0' && c<='9'?c-'0':c>='a' && c<='f'?c-'a'+10:-1;}
bool pin(Address base,const CodePin& pin) noexcept {
    const std::size_t n=std::strlen(pin.hex)/2;
    if(!n || n>64 || !range(base+pin.rva,n,MEM_IMAGE,PAGE_EXECUTE_READ))return false;
    __try {for(std::size_t i=0;i<n;++i){const int a=digit(pin.hex[2*i]),b=digit(pin.hex[2*i+1]);
        if(a<0 || b<0 || *reinterpret_cast<const unsigned char*>(base+pin.rva+i)!=static_cast<unsigned char>(a*16+b))return false;}
        return true;}
    __except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
bool slot(Address base,std::uint32_t rva,std::uint32_t target) noexcept {
    if(!range(base+rva,8,MEM_IMAGE,PAGE_READONLY))return false;
    __try{return *reinterpret_cast<const Address*>(base+rva)==base+target;}
    __except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
bool canonical(const v21pair::Profile& p) {
    for(const auto& x:v21pair::profiles())if(x.family==p.family && x.token==p.token && x.size==p.size && x.vtable==p.vtable &&
        x.clone==p.clone && x.destructor==p.destructor && x.setter==p.setter && x.local80==p.local80 && x.full88==p.full88 && x.full_caller==p.full_caller)return true;
    return false;
}
// POD locals only: SEH boundary cannot run guessed object cleanup.
Return native_call(Address base,Call kind,const v21pair::Profile& p,Address object,bool mode) noexcept {
    Return r{};void* result=nullptr;void** returned=nullptr;
    __try {
        switch(kind) {
        case Call::Factory:r.object=reinterpret_cast<Address>(reinterpret_cast<void*(__fastcall*)(std::uint32_t,const void*)>(base+0x35d210)(p.token,nullptr));break;
        case Call::Setter:reinterpret_cast<void(__fastcall*)(void*,bool)>(base+p.setter)(reinterpret_cast<void*>(object),mode);break;
        case Call::Full88:r.boolean=reinterpret_cast<bool(__fastcall*)(void*,void*,bool)>(base+p.full88)(reinterpret_cast<void*>(object),nullptr,false);break;
        case Call::Wrapper:
            returned=reinterpret_cast<void**(__fastcall*)(void*,void**)>(base+0x4e9930)(reinterpret_cast<void*>(object),&result);
            r.object=reinterpret_cast<Address>(result);r.returned_same_slot=returned==&result;break;
        case Call::Gate:r.boolean=reinterpret_cast<bool(__fastcall*)(void*)>(base+0x4e8630)(reinterpret_cast<void*>(object));break;
        case Call::ActionDestructor:reinterpret_cast<void*(__fastcall*)(void*,unsigned)>(base+p.destructor)(reinterpret_cast<void*>(object),1);break;
        case Call::CommandDestructor:reinterpret_cast<void*(__fastcall*)(void*,unsigned)>(base+0x4e7470)(reinterpret_cast<void*>(object),1);break;
        default:return r;
        }
        r.normal=true;
    }__except(EXCEPTION_EXECUTE_HANDLER){r.object=reinterpret_cast<Address>(result);r.exception=GetExceptionCode();}
    return r;
}
}
bool CompiledWin32Platform::ready() {
    if(!authority_.fresh || !authority_.final_operation || !authority_.final_owned_write || !owner_ || GetCurrentThreadId()!=owner_ || base_<0x10000 || base_>=max_user-0x25e0000 || (base_&0xfff))return false;
    if(!safe_fresh(authority_,base_,owner_))return false;
    for(const auto& p:kCodePins)if(!pin(base_,p))return false;
    for(const auto& p:v21pair::profiles())if(!slot(base_,p.vtable,p.destructor) || !slot(base_,p.vtable+0x40,0x4e9930) ||
        !slot(base_,p.vtable+0x88,p.full88) || !slot(base_,p.vtable+0xb0,p.clone))return false;
    return slot(base_,0x1c814b0,0x4e7470) && slot(base_,0x1c814b0+0x40,0x4e8630);
}
bool CompiledWin32Platform::region(Address p,Region& r) {
    MEMORY_BASIC_INFORMATION m{};if(VirtualQuery(reinterpret_cast<const void*>(p),&m,sizeof(m))!=sizeof(m))return false;
    r={reinterpret_cast<Address>(m.BaseAddress),m.RegionSize,m.State==MEM_COMMIT,m.Type==MEM_PRIVATE,m.Protect==PAGE_READWRITE};return true;
}
bool CompiledWin32Platform::read(Address p,void* out,std::size_t n) {return out && private_copy(p,out,nullptr,n);}
bool CompiledWin32Platform::write(Address p,const void* in,std::size_t n) {return in && private_copy(p,nullptr,in,n,&authority_);}
Return CompiledWin32Platform::invoke(Call kind,const v21pair::Profile& p,Address object,bool mode) {
    if(!canonical(p) || !ready())return {};
    if(!safe_last(authority_,kind,false))return {};
    return native_call(base_,kind,p,object,mode);
}
}
