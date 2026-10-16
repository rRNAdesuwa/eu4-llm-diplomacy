#include "core/spy_send_core.h"
#include "core/v18-preimage/pins.h"
#include "core/sender-pins.h"
#include <cstdio>
#include <cstring>
#include <map>
#include <vector>
#include <algorithm>
#include <cstdlib>

using namespace eu4_spy19;
using eu4_spy18::kCodePins;using eu4_spy18::kSlotPins;
namespace {
constexpr std::uintptr_t BASE=0x100000000ULL,DB=0x200000000ULL,GAME=0x200010000ULL;
constexpr std::uintptr_t COUNTRIES=0x200020000ULL,FRA=0x200030000ULL,ENG=0x200040000ULL;
constexpr std::uintptr_t SERVER=0x200050000ULL,PAUSE=0x200060000ULL;
constexpr std::uint64_t FRA_HANDLE=0x0100007a00415246ULL,ENG_HANDLE=0x0100002e00474e45ULL;
constexpr std::int32_t DATE=56456976,SENTINEL_DATE=43808760;
constexpr std::uintptr_t VTS[]={0x1c7c4a8,0x1c7cfd8,0x1c7c9e8,0x1c7c378,0x1c7c5d8};
constexpr std::uint32_t TOKENS[]={0x337c,0x2ddd,0x2ddf,0x337b,0x33bf};
constexpr std::uintptr_t CLONES[]={0x582b20,0x57eca0,0x5853a0,0x580650,0x581840};
constexpr std::uintptr_t PREVIEWS[]={0x582730,0x57e900,0x585020,0x580260,0x581450};
constexpr const char* SHA="9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a";
unsigned checks=0,failures=0;
void check(bool yes,const char* label) { ++checks;if(!yes) { ++failures;std::printf("FAIL %s\n",label); } }
template<class T> T load(const void* p,std::size_t off) { T v{};std::memcpy(&v,static_cast<const unsigned char*>(p)+off,sizeof(v));return v; }
template<class T> void store(void* p,std::size_t off,T value) { std::memcpy(static_cast<unsigned char*>(p)+off,&value,sizeof(value)); }
enum class Fault { none,factory_null,factory_sentinel,factory_fields,factory_throw,clone_alias,clone_null,
    clone_fields,clone_source_mutated,clone_throw,preview_throw,wrapper_throw,gate_throw,dtor_throw,
    wrapper_return,wrapper_null,wrapper_alias,wrapper_clone_alias,wrapper_fields,gate_consumes,
    original_dtor_consumes_command,clone_dtor_consumes_original,root_after_preview,
    expire_after_preview,clock_back_after_preview,logger_begin,logger_return,logger_complete,
    logger_throw,guard_false,guard_throw,reenter,write_fail,resolver_null,mutate_before_call,
    reenter_resolver,reenter_final_audit,submit_throw,submit_false_consumed,submit_true_unconsumed,submit_false_unconsumed,claim_false,
    expire_after_gate,expire_after_submit,reenter_claim,final_contract_expired,final_contract_date,final_contract_context };
struct Block { void* p;std::size_t size;bool alive;bool command; };
struct Mock;
Mock* current=nullptr;
struct Mock {
    Core core;Host host{};Fault fault=Fault::none;Step fault_step=Step::none;
    std::uint64_t now=10000;std::map<std::uintptr_t,unsigned char> memory;std::vector<Block> blocks;
    std::vector<Event> events;std::vector<std::uintptr_t> resolutions;
    unsigned factory_calls=0,clone_calls=0,preview_calls=0,wrapper_calls=0,gate_calls=0,action_dtors=0,command_dtors=0;
    unsigned abi_errors=0,invalid_reads=0,invalid_writes=0,submit_calls=0,claims=0,fail_log_at=0;bool allow_preview=true,allow_gate=true,guard_triggered=false;
    void* last_original=nullptr;void* last_command=nullptr;Result nested{};bool dispatch_intent_seen=false;
    Mock();~Mock() { for(auto& b:blocks)HeapFree(GetProcessHeap(),0,b.p); }
    Mock(const Mock&)=delete;Mock& operator=(const Mock&)=delete;
    template<class T> void mem(std::uintptr_t p,T value) { const auto* bytes=reinterpret_cast<const unsigned char*>(&value);
        for(std::size_t i=0;i<sizeof(value);++i)memory[p+i]=bytes[i]; }
    void bytes(std::uintptr_t p,const char* h) { for(std::size_t i=0;h[2*i];++i) {
        auto n=[](char c)->unsigned { return c<='9'?static_cast<unsigned>(c-'0'):static_cast<unsigned>(c-'a'+10); };
        memory[p+i]=static_cast<unsigned char>(n(h[2*i])*16+n(h[2*i+1])); } }
    Block* block(const void* p) { for(auto& b:blocks)if(b.p==p)return &b;return nullptr; }
    void* allocate(std::size_t size,bool command=false) { void* p=HeapAlloc(GetProcessHeap(),0,size);
        if(!p)std::abort();std::memset(p,0xa5,size);blocks.push_back({p,size,true,command});return p; }
    unsigned live() const { unsigned n=0;for(const auto& b:blocks)if(b.alive)++n;return n; }
    Result run(Operation op) { current=this;return core.invoke(op,host); }
};
bool read_cb(void* context,std::uintptr_t p,void* out,std::size_t n) {
    auto& m=*static_cast<Mock*>(context);
    for(const auto& b:m.blocks) { const auto a=reinterpret_cast<std::uintptr_t>(b.p);
        if(p>=a && p-a<=b.size && n<=b.size-(p-a)) { if(!b.alive) { ++m.invalid_reads;return false; }
            std::memcpy(out,reinterpret_cast<const void*>(p),n);
            if(m.dispatch_intent_seen && !b.command && b.p!=m.last_original && p==a+0x3c) {
                if(m.fault==Fault::final_contract_expired)m.now=m.host.expires_uptime_ms;
                if(m.fault==Fault::final_contract_date)m.mem<std::int32_t>(GAME+0x1dd0,DATE+24);
                if(m.fault==Fault::final_contract_context)m.mem<std::uint8_t>(0x200080000ULL+0x55,0);
            }
            return true; } }
    auto* bytes=static_cast<unsigned char*>(out);for(std::size_t i=0;i<n;++i) { const auto it=m.memory.find(p+i);
        if(it==m.memory.end()) { ++m.invalid_reads;return false; }bytes[i]=it->second; }return true;
}
bool write_cb(void* context,std::uintptr_t p,const void* data,std::size_t n) {
    auto& m=*static_cast<Mock*>(context);if(m.fault==Fault::write_fail)return false;
    for(auto& b:m.blocks) { const auto a=reinterpret_cast<std::uintptr_t>(b.p);
        if(p>=a && p-a<0x40 && b.alive && !b.command) { const auto off=p-a;
            const bool valid=((off==0x10 || off==0x18 || off==0x20) && n==8)
                || ((off==0x28 || off==0x2c || off==0x30 || off==0x34 || off==0x3c) && n==4)
                || ((off==0x38 || off==0x39) && n==1);
            if(valid) { std::memcpy(reinterpret_cast<void*>(p),data,n);return true; } }
    }++m.invalid_writes;return false;
}
std::uint64_t clock_cb(void* p) { return static_cast<Mock*>(p)->now; }
bool guard_cb(void* context,Point,Step step,const Identity*,const Stamp*) {
    auto& m=*static_cast<Mock*>(context);if(m.fault_step!=step)return true;
    if(m.fault==Fault::guard_false)return false;
    if(m.fault==Fault::guard_throw)RaiseException(0xe0180001,0,0,nullptr);
    if(m.fault==Fault::reenter && !m.guard_triggered) { m.guard_triggered=true;m.nested=m.core.invoke(Operation::next_item,m.host); }
    return true;
}
bool log_cb(void* context,const Event* e) {
    auto& m=*static_cast<Mock*>(context);m.events.push_back(*e);
    if(e->kind==Kind::dispatch_intent)m.dispatch_intent_seen=true;
    if(e->kind==Kind::fault)return true;
    if(m.fail_log_at && m.events.size()==m.fail_log_at)return false;
    if(m.fault==Fault::reenter_final_audit && e->kind==Kind::batch_complete && !m.guard_triggered) {
        m.guard_triggered=true;m.nested=m.core.invoke(Operation::next_item,m.host);
    }
    if(m.fault==Fault::logger_complete && e->kind==Kind::batch_complete)return false;
    if(e->item.step!=m.fault_step)return true;
    if(m.fault==Fault::logger_throw)RaiseException(0xe0180002,0,0,nullptr);
    if(m.fault==Fault::logger_begin && e->kind==Kind::step_intent)return false;
    if(m.fault==Fault::logger_return && e->kind==Kind::step_return)return false;
    if(m.fault==Fault::mutate_before_call && e->kind==Kind::step_intent && m.last_original)
        store<std::uint32_t>(m.last_original,0x34,77);
    return true;
}
void fill_action(void* p,unsigned i) {
    store<std::uintptr_t>(p,0,BASE+VTS[i]);store<std::uint32_t>(p,8,0x165);
    for(auto o:{0x10U,0x18U,0x20U})store<std::uint64_t>(p,o,0x2d2d2d);
    store<std::int32_t>(p,0x28,SENTINEL_DATE);store<std::int32_t>(p,0x2c,SENTINEL_DATE);
    store<std::int32_t>(p,0x30,-1);store<std::uint32_t>(p,0x34,0);
    store<std::uint8_t>(p,0x38,1);store<std::uint8_t>(p,0x39,0);store<std::uint32_t>(p,0x3c,0);
}
void* __fastcall factory_fn(std::uint32_t token,const void* optional) {
    auto& m=*current;++m.factory_calls;if(optional)++m.abi_errors;
    if(m.fault==Fault::factory_throw)RaiseException(0xe0180003,0,0,nullptr);
    if(m.fault==Fault::factory_null)return nullptr;
    if(m.fault==Fault::factory_sentinel)return reinterpret_cast<void*>(BASE+0x1fd1ca0);
    unsigned i=0;while(i<5 && TOKENS[i]!=token)++i;if(i==5) { ++m.abi_errors;return nullptr; }
    void* p=m.allocate(0x40);fill_action(p,i);m.last_original=p;
    if(m.fault==Fault::factory_fields)store<std::uint8_t>(p,0x38,2);
    return p;
}
void* clone_object(const void* original) {
    auto& m=*current;auto* b=m.block(original);if(!b || !b->alive || b->command) { ++m.abi_errors;return nullptr; }
    void* p=m.allocate(0x40);std::memcpy(p,original,0x40);
    // Padding is not a contract. Deliberately differ from the original.
    store<std::uint32_t>(p,0xc,0xcccccccc);store<std::uint16_t>(p,0x3a,0x7777);
    store<std::int32_t>(p,0x2c,load<std::int32_t>(original,0x28));store<std::uint8_t>(p,0x39,0);return p;
}
void* __fastcall clone_fn(const void* original) {
    auto& m=*current;++m.clone_calls;if(m.fault==Fault::clone_throw)RaiseException(0xe0180004,0,0,nullptr);
    if(m.fault==Fault::clone_alias)return const_cast<void*>(original);
    if(m.fault==Fault::clone_null)return nullptr;
    void* p=clone_object(original);
    if(m.fault==Fault::clone_fields)store<std::int32_t>(p,0x2c,-1);
    if(m.fault==Fault::clone_source_mutated)store<std::uint32_t>(const_cast<void*>(original),0x34,2);
    return p;
}
bool __fastcall preview_fn(void* original,void* string_sink,bool mode) {
    auto& m=*current;++m.preview_calls;if(string_sink || mode || !m.block(original)->alive)++m.abi_errors;
    if(m.fault==Fault::preview_throw)RaiseException(0xe0180005,0,0,nullptr);
    if(m.fault==Fault::root_after_preview)m.mem<std::int32_t>(GAME+0x1dd0,DATE+24);
    if(m.fault==Fault::expire_after_preview)m.now=m.host.expires_uptime_ms;
    if(m.fault==Fault::clock_back_after_preview)--m.now;
    return m.allow_preview;
}
void** __fastcall wrapper_fn(void* original,void** output) {
    auto& m=*current;++m.wrapper_calls;if(!output || *output)++m.abi_errors;
    if(m.fault==Fault::wrapper_throw)RaiseException(0xe0180006,0,0,nullptr);
    if(m.fault==Fault::wrapper_null)return output;
    if(m.fault==Fault::wrapper_alias) { *output=original;return output; }
    void* clone=clone_object(original);
    // Native wrapper uses current game date, not a general source-field copy.
    std::int32_t current_date=0;read_cb(&m,GAME+0x1dd0,&current_date,sizeof(current_date));
    store<std::int32_t>(clone,0x2c,current_date);
    void* command=m.allocate(0x58,true);m.last_command=command;std::memset(command,0,0x58);
    store<std::uintptr_t>(command,0,BASE+0x1c814b0);store<std::uint32_t>(command,8,0x165);
    store<std::uint64_t>(command,0x30,15);store<std::int32_t>(command,0x38,-1);
    store<std::uint32_t>(command,0x44,0x2934);store<std::uint64_t>(command,0x48,0xffff);
    store<std::uintptr_t>(command,0x50,reinterpret_cast<std::uintptr_t>(clone));*output=command;
    if(m.fault==Fault::wrapper_fields)store<std::uint64_t>(command,0x30,16);
    if(m.fault==Fault::wrapper_clone_alias)store<std::uintptr_t>(command,0x50,reinterpret_cast<std::uintptr_t>(original));
    if(m.fault==Fault::wrapper_return)return nullptr;
    return output;
}
bool __fastcall gate_fn(void* command) {
    auto& m=*current;++m.gate_calls;auto* b=m.block(command);if(!b || !b->alive || !b->command)++m.abi_errors;
    if(m.fault==Fault::gate_throw)RaiseException(0xe0180007,0,0,nullptr);
    if(m.fault==Fault::gate_consumes)b->alive=false;
    if(m.fault==Fault::expire_after_gate)m.now=m.host.expires_uptime_ms;
    return m.allow_gate;
}
void* __fastcall action_dtor_fn(void* object,unsigned flags) {
    auto& m=*current;++m.action_dtors;auto* b=m.block(object);
    if(flags!=1 || !b || !b->alive || b->command) { ++m.abi_errors;return nullptr; }
    if(m.fault==Fault::dtor_throw)RaiseException(0xe0180008,0,0,nullptr);
    b->alive=false;
    if(m.fault==Fault::original_dtor_consumes_command && object==m.last_original && m.last_command)m.block(m.last_command)->alive=false;
    if(m.fault==Fault::clone_dtor_consumes_original && object!=m.last_original)m.block(m.last_original)->alive=false;
    return reinterpret_cast<void*>(0x12345678); // Caller must ignore deleting-dtor return.
}
void* __fastcall command_dtor_fn(void* object,unsigned flags) {
    auto& m=*current;++m.command_dtors;auto* b=m.block(object);
    if(flags!=1 || !b || !b->alive || !b->command) { ++m.abi_errors;return nullptr; }
    if(m.fault==Fault::dtor_throw)RaiseException(0xe0180009,0,0,nullptr);
    auto* owned=reinterpret_cast<void*>(load<std::uintptr_t>(object,0x50));action_dtor_fn(owned,1);b->alive=false;return nullptr;
}
bool claim_cb(void* context,std::uint32_t sequence,std::uint32_t ordinal,const Identity*,const Stamp*) {
    auto& m=*static_cast<Mock*>(context);
    if(sequence!=4 || ordinal!=m.claims)++m.abi_errors;
    ++m.claims;
    if(m.fault==Fault::reenter_claim&&!m.guard_triggered) { m.guard_triggered=true;m.nested=m.core.invoke(Operation::next_item,m.host); }
    return m.fault!=Fault::claim_false;
}
bool __fastcall submit_fn(void* context,void** slot) {
    auto& m=*current;++m.submit_calls;
    if(context!=reinterpret_cast<void*>(0x200080000ULL)||!slot||!*slot) { ++m.abi_errors;return false; }
    auto* b=m.block(*slot);if(!b||!b->alive||!b->command) { ++m.abi_errors;return false; }
    if(m.fault==Fault::submit_throw)RaiseException(0xe0190001,0,0,nullptr);
    const bool consumes=m.fault!=Fault::submit_true_unconsumed && m.fault!=Fault::submit_false_unconsumed;
    if(consumes) { auto* held=reinterpret_cast<void*>(load<std::uintptr_t>(*slot,0x50));m.block(held)->alive=false;b->alive=false;*slot=nullptr; }
    if(m.fault==Fault::expire_after_submit)m.now=m.host.expires_uptime_ms;
    return m.fault!=Fault::submit_false_consumed && m.fault!=Fault::submit_false_unconsumed;
}
std::uintptr_t resolve_cb(void* context,std::uintptr_t rva) {
    auto& m=*static_cast<Mock*>(context);m.resolutions.push_back(rva);
    if(m.fault==Fault::resolver_null)return 0;
    if(m.fault==Fault::reenter_resolver && !m.guard_triggered) { m.guard_triggered=true;m.nested=m.core.invoke(Operation::next_item,m.host); }
    if(rva==0x14ca210)return reinterpret_cast<std::uintptr_t>(&submit_fn);
    if(rva==0x35d210)return reinterpret_cast<std::uintptr_t>(&factory_fn);
    if(rva==0x4e9930)return reinterpret_cast<std::uintptr_t>(&wrapper_fn);
    if(rva==0x4e8630)return reinterpret_cast<std::uintptr_t>(&gate_fn);
    if(rva==0x129450)return reinterpret_cast<std::uintptr_t>(&action_dtor_fn);
    if(rva==0x4e7470)return reinterpret_cast<std::uintptr_t>(&command_dtor_fn);
    for(unsigned i=0;i<5;++i) { if(rva==CLONES[i])return reinterpret_cast<std::uintptr_t>(&clone_fn);
        if(rva==PREVIEWS[i])return reinterpret_cast<std::uintptr_t>(&preview_fn); }
    ++m.abi_errors;return 0;
}
Mock::Mock() {
    mem<std::uint16_t>(BASE,0x5a4d);mem<std::uint32_t>(BASE+0x3c,0x100);
    mem<std::uint32_t>(BASE+0x100,0x4550);mem<std::uint16_t>(BASE+0x104,0x8664);
    mem<std::uint32_t>(BASE+0x108,0x66fe6ab9);mem<std::uint16_t>(BASE+0x118,0x20b);
    mem<std::uint32_t>(BASE+0x150,0x25e0000);
    for(const auto& pin:kCodePins)bytes(BASE+pin.rva,pin.hex);
    for(const auto& pin:kSlotPins)mem<std::uintptr_t>(BASE+pin.rva,BASE+pin.target);
    for(const auto& pin:eu4_spy19_sender::kCodePins)bytes(BASE+pin.rva,pin.hex);
    for(const auto& pin:eu4_spy19_sender::kSlotPins)mem<std::uintptr_t>(BASE+pin.rva,BASE+pin.target);
    mem<std::uintptr_t>(BASE+0x233d8d0,DB);mem<std::uintptr_t>(BASE+0x233fe78,GAME);
    mem<std::uintptr_t>(DB+0x118,COUNTRIES);mem<std::uintptr_t>(COUNTRIES+122*8,FRA);mem<std::uintptr_t>(COUNTRIES+46*8,ENG);
    mem<std::uint64_t>(FRA+0x20,FRA_HANDLE);mem<std::uint64_t>(ENG+0x20,ENG_HANDLE);
    mem<std::uint64_t>(GAME+0x1e60,FRA_HANDLE);mem<std::int32_t>(GAME+0x1dd0,DATE);
    mem<std::uintptr_t>(GAME+0x1e00,SERVER);mem<std::uintptr_t>(SERVER,BASE+0x1cb8460);
    mem<std::uintptr_t>(SERVER+0x418,PAUSE);mem<std::uintptr_t>(PAUSE+0x50,SERVER);
    mem<std::uint8_t>(PAUSE+0x48,1);mem<std::uint8_t>(GAME+0x7485,0);mem<std::uintptr_t>(GAME+0x74c8,0);
    mem<std::int32_t>(DB+0x124,256);mem<std::uint64_t>(FRA+0x18f0,0x2d2d2d);mem<std::uint64_t>(ENG+0x18f0,0x2d2d2d);
    mem<std::uint8_t>(GAME+0x1e66,0);mem<std::uint8_t>(GAME+0x1e6f,0);mem<std::uint8_t>(GAME+0x24d0,0);
    mem<std::int32_t>(GAME+0x1e08,0);mem<std::uint8_t>(SERVER+0x19f1,0);
    mem<std::uintptr_t>(PAUSE,0);mem<std::uintptr_t>(PAUSE+8,0);
    mem<std::uintptr_t>(SERVER+0x330,0x200070000ULL);mem<std::uintptr_t>(0x200070000ULL+0x370,0x200080000ULL);
    mem<std::uintptr_t>(0x200080000ULL+0x58,0x200090000ULL);mem<std::uintptr_t>(0x200090000ULL,BASE+0x1d96178);
    mem<std::uint8_t>(0x200080000ULL+0x55,1);mem<std::uint8_t>(0x200080000ULL+0x80d,0);
    host.struct_size=sizeof(Host);host.abi_version=1;host.expected_game_thread=GetCurrentThreadId();host.request_sequence=4;
    host.image_base=BASE;host.identity.pid=1234;host.identity.creation_filetime=1;
    std::memset(host.identity.session,'1',32);std::memset(host.identity.dll_sha256,'2',64);std::memset(host.identity.manifest_sha256,'3',64);
    host.game_sha256=SHA;host.frame_id=1;host.expires_uptime_ms=70000;host.full_sha256_verified=true;
    host.same_session_preflight_verified=true;host.disposable_test_authorized=true;host.isolated_mock_resolver=true;
    host.read=read_cb;host.write_owned=write_cb;host.resolve=resolve_cb;host.clock=clock_cb;host.guard=guard_cb;host.log=log_cb;host.claim=claim_cb;host.user=this;
}
