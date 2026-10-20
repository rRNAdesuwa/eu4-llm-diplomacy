#include "spy_core.h"
#include "pins.h"
#include <cstring>

namespace eu4_spy18 {
namespace {
constexpr std::uint64_t kFra=0x0100007a00415246ULL,kEng=0x0100002e00474e45ULL,kSentinel=0x2d2d2d;
constexpr std::int32_t kDateSentinel=43808760;
constexpr const char* kSha="9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a";
constexpr std::uintptr_t kFactory=0x35d210,kWrapper=0x4e9930,kGate=0x4e8630;
constexpr std::uintptr_t kActionDtor=0x129450,kCommandDtor=0x4e7470,kCommandVtable=0x1c814b0;
struct Family { const char* name; std::uint32_t token; std::uintptr_t vtable,clone,preview; };
constexpr Family kFamilies[]={
    {"corrupt_officials",0x337c,0x1c7c4a8,0x582b20,0x582730},
    {"sabotage_reputation",0x2ddd,0x1c7cfd8,0x57eca0,0x57e900},
    {"sow_discontent",0x2ddf,0x1c7c9e8,0x5853a0,0x585020},
    {"slander_merchants",0x337b,0x1c7c378,0x580650,0x580260},
    {"sabotage_recruitment",0x33bf,0x1c7c5d8,0x581840,0x581450}};
using Factory=void* (__fastcall*)(std::uint32_t,const void*);
using Clone=void* (__fastcall*)(const void*);
using Preview=bool (__fastcall*)(void*,void*,bool);
using Wrapper=void** (__fastcall*)(void*,void**);
using Gate=bool (__fastcall*)(void*);
using Dtor=void* (__fastcall*)(void*,unsigned int);
bool pointer(std::uintptr_t p) { return p>=0x10000 && p<0x0000800000000000ULL && p%8==0; }
bool same_stamp(const Stamp& a,const Stamp& b) {
    return a.game==b.game && a.database==b.database && a.countries==b.countries
        && a.actor_country==b.actor_country && a.target_country==b.target_country
        && a.server==b.server && a.pause_manager==b.pause_manager && a.actor==b.actor
        && a.target==b.target && a.player==b.player && a.date==b.date;
}
bool same_fields(const Fields& a,const Fields& b,bool clone) {
    return a.vtable==b.vtable && a.marker==b.marker && a.actor==b.actor && a.controller==b.controller
        && a.target==b.target && a.primary_date==b.primary_date
        && a.secondary_date==(clone?b.primary_date:b.secondary_date) && a.envoy==b.envoy
        && a.state==b.state && a.value==b.value && a.flag39==(clone?0:b.flag39) && a.identifier==b.identifier;
}
unsigned nibble(char c) { return c>='0' && c<='9'?static_cast<unsigned>(c-'0'):static_cast<unsigned>(c-'a'+10); }
} // namespace

struct Runner {
    Core* core;const Host* host;Result result;Event event;
    std::uintptr_t original,clone,command;
    std::uint64_t last_clock;
    bool fail(Reason reason) {
        if(result.reason==Reason::none)result.reason=reason;
        result.freeze_session=true;result.ownership_uncertain=original!=0 || clone!=0 || command!=0
            || (event.call_entered && !event.call_returned) || reason==Reason::factory_unknown
            || reason==Reason::alias_or_ownership || reason==Reason::native_exception;
        InterlockedExchange(&core->frozen_,1);return false;
    }
    bool read(std::uintptr_t address,void* out,std::size_t size) {
        if(InterlockedCompareExchange(&core->frozen_,0,0))return fail(Reason::frozen);
        if (!address || !size || size>64 || result.reads>=8192 || result.bytes_read>1048576-size)return fail(Reason::read_budget);
        ++result.reads;result.bytes_read+=size;
        if(!host->read(host->user,address,out,size))return fail(Reason::root_guard);
        return InterlockedCompareExchange(&core->frozen_,0,0)==0 || fail(Reason::frozen);
    }
    template<class T> bool get(std::uintptr_t address,T& out) { return read(address,&out,sizeof(out)); }
    template<class T> bool put(std::size_t offset,T value) {
        if(InterlockedCompareExchange(&core->frozen_,0,0))return fail(Reason::frozen);
        if(!original || offset<0x10 || offset+sizeof(T)>0x40)return fail(Reason::alias_or_ownership);
        if(!host->write_owned(host->user,original+offset,&value,sizeof(value)))return fail(Reason::fields_mismatch);
        return InterlockedCompareExchange(&core->frozen_,0,0)==0 || fail(Reason::frozen);
    }
    bool code_pin(std::uintptr_t rva) {
        for(const auto& pin:kCodePins)if(pin.rva==rva) {
            unsigned char actual[32]{};std::size_t length=0;
            while(pin.hex[2*length])++length;
            if(length>sizeof(actual) || !read(host->image_base+rva,actual,length))return false;
            for(std::size_t i=0;i<length;++i)if(actual[i]!=(nibble(pin.hex[2*i])*16+nibble(pin.hex[2*i+1])))return fail(Reason::image_pin);
            return true;
        }
        return fail(Reason::image_pin);
    }
    bool image() {
        std::uint16_t mz=0,machine=0,magic=0;std::uint32_t nt=0,signature=0,timestamp=0,image_size=0;
        if(!get(host->image_base,mz) || !get(host->image_base+0x3c,nt) || mz!=0x5a4d || nt>4096 || !nt)return fail(Reason::image_pin);
        const auto p=host->image_base+nt;
        if(!get(p,signature) || !get(p+4,machine) || !get(p+8,timestamp) || !get(p+24,magic) || !get(p+24+56,image_size)
            || signature!=0x4550 || machine!=0x8664 || timestamp!=0x66fe6ab9 || magic!=0x20b || image_size!=0x25e0000)return fail(Reason::image_pin);
        for(const auto& pin:kCodePins)if(!code_pin(pin.rva))return false;
        for(const auto& pin:kSlotPins) { std::uintptr_t value=0;
            if(!get(host->image_base+pin.rva,value) || value!=host->image_base+pin.target)return fail(Reason::image_pin); }
        return true;
    }
    bool stamp(Stamp& s) {
        std::uintptr_t value=0;std::uint8_t manual=0,reset=0;
        if(!get(host->image_base+0x233d8d0,s.database) || !get(host->image_base+0x233fe78,s.game)
            || !pointer(s.database) || !pointer(s.game) || !get(s.database+0x118,s.countries) || !pointer(s.countries)
            || !get(s.countries+122*8,s.actor_country) || !get(s.countries+46*8,s.target_country)
            || !pointer(s.actor_country) || !pointer(s.target_country) || s.actor_country==s.target_country
            || !get(s.actor_country+0x20,s.actor) || !get(s.target_country+0x20,s.target)
            || s.actor!=kFra || s.target!=kEng || !get(s.game+0x1e60,s.player) || s.player!=kFra
            || !get(s.game+0x1dd0,s.date) || s.date<=0 || !get(s.game+0x1e00,s.server) || !pointer(s.server)
            || !get(s.server,value) || value!=host->image_base+0x1cb8460
            || !get(s.server+0x418,s.pause_manager) || !pointer(s.pause_manager)
            || !get(s.pause_manager+0x50,value) || value!=s.server || !get(s.pause_manager+0x48,manual) || manual!=1
            || !get(s.game+0x7485,reset) || reset!=0 || !get(s.game+0x74c8,value) || value!=0)return fail(Reason::root_guard);
        return true; // Manual pause only; never a strict SP or epoch proof.
    }
    bool barrier(GuardPoint point) {
        if(InterlockedCompareExchange(&core->frozen_,0,0))return fail(Reason::frozen);
        if(GetCurrentThreadId()!=host->expected_game_thread)return fail(Reason::wrong_thread);
        const auto now=host->clock(host->user);
        if(now<last_clock)return fail(Reason::root_guard);
        last_clock=now;
        if(point==GuardPoint::before_work && now>=host->expires_uptime_ms)return fail(Reason::rejected_guard);
        Stamp first{},second{};
        if(!stamp(first) || !stamp(second) || !same_stamp(first,second))return fail(Reason::root_guard);
        if(core->locked_.game==0)core->locked_=first;
        if(!same_stamp(first,core->locked_))return fail(Reason::root_guard);
        event.stamp=first;
        if(!host->guard(host->user,point,result.stage,result.step,&first))return fail(Reason::rejected_guard);
        return InterlockedCompareExchange(&core->frozen_,0,0)==0 || fail(Reason::frozen);
    }
    bool audit(EventKind kind) {
        event.kind=kind;event.reason=result.reason;event.exception_code=result.exception_code;
        if(!host->log(host->user,&event))return fail(Reason::audit_failed);
        return InterlockedCompareExchange(&core->frozen_,0,0)==0 || fail(Reason::frozen);
    }
    bool fields(std::uintptr_t object,Fields& f) {
        if(!pointer(object) || object==host->image_base+0x1fd1ca0)return fail(Reason::factory_unknown);
        return get(object,f.vtable) && get(object+8,f.marker)
            && get(object+0x10,f.actor) && get(object+0x18,f.controller) && get(object+0x20,f.target)
            && get(object+0x28,f.primary_date) && get(object+0x2c,f.secondary_date) && get(object+0x30,f.envoy)
            && get(object+0x34,f.state) && get(object+0x38,f.value) && get(object+0x39,f.flag39) && get(object+0x3c,f.identifier);
    }
    Fields expected(bool initialized) const {
        Fields f{};f.vtable=host->image_base+kFamilies[result.family].vtable;f.marker=0x165;
        f.actor=f.controller=initialized?kFra:kSentinel;f.target=initialized?kEng:kSentinel;
        f.primary_date=f.secondary_date=initialized?core->locked_.date:kDateSentinel;
        f.envoy=-1;f.value=1;return f;
    }
    bool verify_original(bool initialized) {
        Fields f{};const auto wanted=expected(initialized);
        if(!fields(original,f) || !same_fields(f,wanted,false))return fail(Reason::fields_mismatch);
        event.original_fields=f;return true;
    }
    bool verify_clone(bool initialized) {
        Fields f{};const auto wanted=expected(initialized);
        if(!clone || clone==original || clone==command || !fields(clone,f) || !same_fields(f,wanted,true))return fail(Reason::alias_or_ownership);
        event.clone_fields=f;return true;
    }
    bool command_contract() {
        std::uintptr_t vt=0,held=0;std::uint64_t s=0;std::uint32_t marker=0,token=0,u=0;
        std::uint16_t small=0;std::uint8_t byte=0;std::int32_t sentinel=0;
        if(!pointer(command) || command==original || command==clone || command==host->image_base+0x1fd1ca0
            || !get(command,vt) || vt!=host->image_base+kCommandVtable
            || !get(command+8,marker) || marker!=0x165 || !get(command+0x44,token) || token!=0x2934
            || !get(command+0x10,byte) || byte!=0 || !get(command+0x18,s) || s!=0
            || !get(command+0x28,s) || s!=0 || !get(command+0x30,s) || s!=15
            || !get(command+0x38,sentinel) || sentinel!=-1 || !get(command+0x3c,u) || u!=0
            || !get(command+0x40,small) || small!=0 || !get(command+0x48,s) || s!=0xffff
            || !get(command+0x50,held) || held!=clone)return fail(Reason::alias_or_ownership);
        return verify_clone(true);
    }
    bool begin(Step step,std::uintptr_t rva,bool cleanup,std::uintptr_t& fn) {
        result.step=step;event.step=step;event.call_entered=false;event.call_returned=false;
        event.allowed_observed=false;event.allowed=false;
        if(!barrier(cleanup?GuardPoint::before_cleanup:GuardPoint::before_work) || !code_pin(rva) || !audit(EventKind::step_begin))return false;
        if(!barrier(cleanup?GuardPoint::before_cleanup:GuardPoint::before_work))return false;
        fn=host->resolve(host->user,rva);
        if(InterlockedCompareExchange(&core->frozen_,0,0))return fail(Reason::frozen);
        if(!fn || (!host->isolated_mock_resolver && fn!=host->image_base+rva))return fail(Reason::resolver_failed);
        return true; // Mark entered only immediately before the actual engine call.
    }
    bool returned() {
        return barrier(GuardPoint::after_work) && audit(EventKind::step_return);
    }
    bool destroy(Step step,std::uintptr_t& object,std::uintptr_t dtor) {
        if(step==Step::destroy_command) { if(!command_contract())return false; }
        else if(step==Step::destroy_original) { if(!verify_original(result.stage!=Stage::lifecycle))return false; }
        else if(!verify_clone(false))return false;
        std::uintptr_t fn=0;if(!begin(step,dtor,true,fn))return false;
        if(step==Step::destroy_command) { if(!command_contract())return false; }
        else if(step==Step::destroy_original) { if(!verify_original(result.stage!=Stage::lifecycle))return false; }
        else if(!verify_clone(false))return false;
        event.call_entered=true;
        reinterpret_cast<Dtor>(fn)(reinterpret_cast<void*>(object),1U);
        event.call_returned=true;
        object=0; // Never dereference after a normal deleting-dtor return.
        if(step==Step::destroy_original)event.original_destroyed=true;
        else if(step==Step::destroy_clone)event.clone_destroyed=true;
        else { clone=0;event.command_destroyed=true;event.clone_destroyed=true; }
        return returned();
    }
    bool initialize() {
        result.step=Step::initialize;event.step=Step::initialize;event.call_entered=false;event.call_returned=false;
        if(!barrier(GuardPoint::before_work) || !audit(EventKind::step_begin) || !barrier(GuardPoint::before_work)
            || !verify_original(false))return false;
        const auto f=expected(true);
        if(!put(0x10,f.actor) || !put(0x18,f.controller) || !put(0x20,f.target)
            || !put(0x28,f.primary_date) || !put(0x2c,f.secondary_date) || !put(0x30,f.envoy)
            || !put(0x34,f.state) || !put(0x38,f.value) || !put(0x39,f.flag39) || !put(0x3c,f.identifier))return false;
        return verify_original(true) && barrier(GuardPoint::after_work) && audit(EventKind::step_return);
    }
    bool run_case(std::uint32_t index) {
        result.family=index;event={};event.stage=result.stage;event.family=index;event.token=kFamilies[index].token;
        event.mock_resolver=host->isolated_mock_resolver;
        std::uintptr_t fn=0;
        if(!begin(Step::factory,kFactory,false,fn))return false;
        event.call_entered=true;
        original=reinterpret_cast<std::uintptr_t>(reinterpret_cast<Factory>(fn)(kFamilies[index].token,nullptr));
        event.call_returned=true;
        if(!original || original==host->image_base+0x1fd1ca0)return fail(Reason::factory_unknown);
        event.original_id=++core->next_object_id_;
        if(!verify_original(false) || !returned())return false;
        if(result.stage==Stage::lifecycle) {
            if(!begin(Step::clone,kFamilies[index].clone,false,fn))return false;
            if(!verify_original(false))return false;
            event.call_entered=true;
            clone=reinterpret_cast<std::uintptr_t>(reinterpret_cast<Clone>(fn)(reinterpret_cast<const void*>(original)));
            event.call_returned=true;
            if(!clone || clone==original)return fail(Reason::alias_or_ownership);
            event.clone_id=++core->next_object_id_;
            if(!verify_original(false) || !verify_clone(false) || !returned()
                || !destroy(Step::destroy_clone,clone,kActionDtor) || !destroy(Step::destroy_original,original,kActionDtor))return false;
        } else {
            if(!initialize())return false;
            if(result.stage==Stage::family_preview) {
                if(!begin(Step::full_preview,kFamilies[index].preview,false,fn))return false;
                if(!verify_original(true))return false;
                event.call_entered=true;
                event.allowed=reinterpret_cast<Preview>(fn)(reinterpret_cast<void*>(original),nullptr,false);
                event.call_returned=true;
                event.allowed_observed=true;result.allowed[index]=event.allowed;result.allowed_observed[index]=true;
                if(!verify_original(true) || !returned() || !destroy(Step::destroy_original,original,kActionDtor))return false;
            } else {
                if(!begin(Step::wrap_owned,kWrapper,false,fn))return false;
                if(!verify_original(true))return false;
                void* slot=nullptr;
                event.call_entered=true;
                void** returned_slot=reinterpret_cast<Wrapper>(fn)(reinterpret_cast<void*>(original),&slot);
                event.call_returned=true;
                command=reinterpret_cast<std::uintptr_t>(slot);
                if(returned_slot!=&slot || !pointer(command) || command==original
                    || !get(command+0x50,clone) || clone==original || clone==command)return fail(Reason::alias_or_ownership);
                event.command_id=++core->next_object_id_;event.clone_id=++core->next_object_id_;
                if(!verify_original(true) || !command_contract() || !returned()
                    || !destroy(Step::destroy_original,original,kActionDtor))return false;
                if(!begin(Step::command_gate,kGate,false,fn))return false;
                if(!command_contract())return false;
                event.call_entered=true;
                event.allowed=reinterpret_cast<Gate>(fn)(reinterpret_cast<void*>(command));
                event.call_returned=true;
                event.allowed_observed=true;result.allowed[index]=event.allowed;result.allowed_observed[index]=true;
                if(!command_contract() || !returned() || !destroy(Step::destroy_command,command,kCommandDtor))return false;
            }
        }
        if(original || clone || command)return fail(Reason::alias_or_ownership);
        if(!audit(EventKind::case_complete))return false;
        ++result.cases_complete;return true;
    }
    bool execute() {
        if(!image() || !barrier(GuardPoint::before_work) || !audit(EventKind::stage_begin))return false;
        for(std::uint32_t i=0;i<5;++i)if(!run_case(i))return false;
        if(!barrier(GuardPoint::after_work) || !audit(EventKind::stage_complete))return false;
        result.completed=true;result.audit_complete=true;
        core->completed_=static_cast<std::uint32_t>(result.stage);core->completion_frame_=host->frame_id;return true;
    }
};

Core::Core() noexcept : active_(0),frozen_(0),completed_(0),next_object_id_(0),completion_frame_(0),locked_{} {}
Result Core::run(Stage stage,const Host& host) {
    Runner r{};r.core=this;r.host=&host;r.result.stage=stage;r.event.stage=stage;r.event.mock_resolver=host.isolated_mock_resolver;
    if(InterlockedCompareExchange(&active_,1,0)) { r.fail(Reason::busy);return r.result; }
    __try {
        if(InterlockedCompareExchange(&frozen_,0,0))r.fail(Reason::frozen);
        else if(host.struct_size!=sizeof(Host) || host.abi_version!=1 || !host.read || !host.write_owned || !host.resolve
            || !host.clock || !host.guard || !host.log || !host.full_sha256_verified || !host.durable_stage_claimed
            || !host.disposable_test_authorized || !host.later_clean_health_verified || !pointer(host.image_base)
            || !host.game_sha256 || std::memcmp(host.game_sha256,kSha,64)!=0 || host.game_sha256[64]!=0)r.fail(Reason::bad_host);
        else if(GetCurrentThreadId()!=host.expected_game_thread)r.fail(Reason::wrong_thread);
        else if(static_cast<std::uint32_t>(stage)!=completed_+1 || static_cast<std::uint32_t>(stage)>3
            || host.frame_id<=completion_frame_)r.fail(Reason::stage_order);
        else { const auto now=host.clock(host.user);r.last_clock=now;
            if(host.expires_uptime_ms<=now || host.expires_uptime_ms-now>60000)r.fail(Reason::rejected_guard);
            else r.execute(); }
    } __except(EXCEPTION_EXECUTE_HANDLER) {
        r.result.exception_code=GetExceptionCode();r.fail(Reason::native_exception);
        // Ownership after any SEH is unknown. No destructors, retry or repair.
    }
    if(r.result.reason!=Reason::none) {
        // Best-effort typed fault audit only. Logger failure cannot authorize cleanup.
        __try { r.event.kind=EventKind::fault;r.event.reason=r.result.reason;r.event.exception_code=r.result.exception_code;
            if(host.log)host.log(host.user,&r.event); }
        __except(EXCEPTION_EXECUTE_HANDLER) { }
    }
    InterlockedExchange(&active_,0);return r.result;
}
const char* family_name(std::uint32_t family) noexcept { return family<5?kFamilies[family].name:nullptr; }
} // namespace eu4_spy18
