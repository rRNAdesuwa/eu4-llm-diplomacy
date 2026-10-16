#include "native_rival.h"
#include <cstring>
namespace tagcommand31 {
namespace {
using Address=std::uint64_t;
bool code(Address base,std::uint32_t rva,const char* expected,std::size_t size) {
    MEMORY_BASIC_INFORMATION region{};
    if(VirtualQuery(reinterpret_cast<void*>(base+rva),&region,sizeof(region))!=sizeof(region)
      ||region.State!=MEM_COMMIT||region.Type!=MEM_IMAGE||region.Protect!=PAGE_EXECUTE_READ)return false;
    __try {return !std::memcmp(reinterpret_cast<void*>(base+rva),expected,size);}__except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
struct NativeReturn {Address pointer{};bool normal{},value{};std::uint32_t exception{};};
NativeReturn clone(Address base,unsigned kind,void* source) noexcept {
    NativeReturn out{};alignas(8) unsigned char string[32]{};const Address capacity=15;std::memcpy(string+24,&capacity,8);
    __try {
        out.pointer=reinterpret_cast<Address>(reinterpret_cast<void*(__fastcall*)(void*,void*)>(base+(kind==1?0x2ab6c0:0x2ad340))(source,string));out.normal=true;
    }__except(EXCEPTION_EXECUTE_HANDLER){out.exception=GetExceptionCode();}
    return out;
}
NativeReturn gate(Address base,unsigned kind,Address object) noexcept {
    NativeReturn out{};
    __try {out.value=reinterpret_cast<bool(__fastcall*)(void*)>(base+(kind==1?0x2ab780:0x2ad400))(reinterpret_cast<void*>(object));out.normal=true;}
    __except(EXCEPTION_EXECUTE_HANDLER){out.exception=GetExceptionCode();}return out;
}
NativeReturn destroy(Address base,Address object) noexcept {
    NativeReturn out{};
    __try {reinterpret_cast<void*(__fastcall*)(void*,unsigned)>(base+0x98940)(reinterpret_cast<void*>(object),1);out.normal=true;}
    __except(EXCEPTION_EXECUTE_HANDLER){out.exception=GetExceptionCode();}return out;
}
template<class T>void put(unsigned char* data,unsigned off,T value){std::memcpy(data+off,&value,sizeof(value));}
bool owned(v21guard::NativePairGuardDraft& guard,Address object,const unsigned char* expected) {
    MEMORY_BASIC_INFORMATION region{};unsigned char actual[96]{};
    if(object<0x10000||(object&7)||VirtualQuery(reinterpret_cast<void*>(object),&region,sizeof(region))!=sizeof(region)
      ||region.State!=MEM_COMMIT||region.Type!=MEM_PRIVATE||region.Protect!=PAGE_READWRITE)return false;
    if(!guard.read(object,actual,sizeof(actual)))return false;
    // Padding and reserved engine bytes are deliberately not interpreted.
    for(const auto field:std::array<std::pair<unsigned,unsigned>,15>{{{0,8},{8,4},{0x10,1},{0x18,1},{0x28,8},{0x30,8},
       {0x38,4},{0x3c,4},{0x40,2},{0x44,4},{0x48,2},{0x4a,1},{0x4b,1},{0x50,8},{0x58,8}}})
       if(std::memcmp(actual+field.first,expected+field.first,field.second))return false;
    return true;
}
}
RivalResult rival(const v21pair::Request& request,v21guard::NativePairGuardDraft& guard,v24port::Platform& platform,std::uint64_t expires,Audit audit) noexcept {
    using namespace v21pair;RivalResult out{};Address object=0;bool transferred=false;
    auto freeze=[&](const char* why){out.result.status=Status::Frozen;out.result.reason=why;out.diagnostics.frozen=true;
      out.diagnostics.fault=v24port::Fault::NativeException;if(object&&!transferred){out.diagnostics.live=out.diagnostics.quarantined=1;}return out;};
    try {
        const auto kind=request.action==Action::N_select_rival?1u:request.action==Action::N_remove_rival?2u:0u;
        if(!kind||!audit)return out;
        const auto baseline=guard.baseline();const auto base=platform.module();const auto authority=guard.authority();
        alignas(8) unsigned char source[96]{};
        put(source,0,base+(kind==1?0x1c55138:0x1c54a68));put(source,8,std::uint32_t{0x165});put(source,0x30,Address{15});
        put(source,0x38,std::int32_t{-1});put(source,0x44,std::uint32_t{kind==1?0x2faeu:0x2fafu});put(source,0x48,Address{0xffff});
        put(source,0x50,baseline.actor.value);put(source,0x58,baseline.target.value);
        auto barrier=[&](bool cleanup){PairStamp now{};return guard.stamp(request,now)&&now==baseline&&platform.ready()
          &&authority.final_operation(authority.user,cleanup?v21port::Call::CommandDestructor:v21port::Call::Gate)
          &&(cleanup||guard.clock()<expires);};
        if(!code(base,kind==1?0x2ab6c0:0x2ad340,"\x48\x89\x5c\x24\x08\x48\x89\x74\x24\x18",10)
          ||!code(base,kind==1?0x2ab780:0x2ad400,"\x48\x83\xec\x28",4)
          ||!code(base,0x98940,"\x48\x89\x5c\x24",4)||!barrier(false))return freeze("independent_preflight");
        if(!audit("native_call_begin",",\"call\":8,\"independent_kind\":%u",kind))return freeze("audit_failed");
        ++out.diagnostics.calls;const auto made=clone(base,kind,source);object=made.pointer;
        if(!audit("native_call_return",",\"call\":8,\"normal\":%s,\"exception\":%u",made.normal?"true":"false",made.exception)
          ||!made.normal||made.exception||!object)return freeze("independent_clone_unknown");
        out.diagnostics.issued=out.diagnostics.live=1;
        if(!owned(guard,object,source)||!barrier(false))return freeze("independent_owned_fields");
        if(!audit("native_call_begin",",\"call\":9,\"independent_kind\":%u",kind))return freeze("audit_failed");
        ++out.diagnostics.calls;const auto allowed=gate(base,kind,object);
        if(!audit("native_call_return",",\"call\":9,\"normal\":%s,\"boolean\":%s,\"exception\":%u",allowed.normal?"true":"false",allowed.value?"true":"false",allowed.exception)
          ||!allowed.normal||allowed.exception||!owned(guard,object,source))return freeze("independent_gate_unknown");
        if(!allowed.value) {
            if(!barrier(true)||!owned(guard,object,source))return freeze("independent_cleanup_preflight");
            if(!audit("native_call_begin",",\"call\":10,\"independent_kind\":%u",kind))return freeze("audit_failed");
            ++out.diagnostics.calls;const auto freed=destroy(base,object);
            if(!audit("native_call_return",",\"call\":10,\"normal\":%s,\"exception\":%u",freed.normal?"true":"false",freed.exception)||!freed.normal||freed.exception)return freeze("independent_cleanup_unknown");
            object=0;out.diagnostics.live=0;out.result.status=Status::ModelGateRejected;out.result.reason="command_gate_normal_false";return out;
        }
        if(!audit("dispatch_intent",",\"independent_kind\":%u,\"owned_objects\":1",kind)||!owned(guard,object,source)||!barrier(false))return freeze("independent_dispatch_preflight");
        v24port::TransferEnvelope envelope{};envelope.profile=profiles()[0];envelope.stamp=baseline;envelope.command=object;envelope.independent_kind=static_cast<std::uint8_t>(kind);
        // From this point the adapter has sole responsibility. Never inspect/free/retry the command.
        transferred=true;out.diagnostics.live=0;out.result.submit_entered=true;out.result.transfer=TransferOutcome::Unknown;++out.diagnostics.calls;
        const auto sent=platform.submit(envelope);
        out.result.submit_returned=sent.normal;out.result.submit_value=sent.value;out.result.slot_consumed=sent.slot_consumed;out.result.submit_exception=sent.exception;
        if(!sent.normal||sent.exception||!sent.value||!sent.slot_consumed)return freeze("dispatch_outcome_unknown_no_retry");
        out.result.status=Status::ModelComplete;out.result.reason="normal_dispatch_slot_consumed";out.result.transfer=TransferOutcome::Dispatched;out.result.submitted=true;return out;
    }catch(...){return freeze("independent_exception_unknown_no_retry");}
}
}
