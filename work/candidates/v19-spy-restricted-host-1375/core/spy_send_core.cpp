#include "spy_send_core.h"
#include "v18-preimage/pins.h"
#include "sender-pins.h"
#include <cstring>

namespace eu4_spy19 {
namespace {
constexpr std::uint64_t FRA=0x0100007a00415246ULL,ENG=0x0100002e00474e45ULL,SENTINEL=0x2d2d2d;
// The full SHA below is an exact fixed identifier, never a prefix.
constexpr char GAME_SHA[]="9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a";
static_assert(sizeof(GAME_SHA)==65,"Full SHA256 identifier");
constexpr char OLD_DLL[]="6aff9a9fc4d46692c9be0ac39b0c741bf8eeb840abaf8731d0144510a938f00b";
constexpr std::uintptr_t FACTORY=0x35d210,WRAPPER=0x4e9930,GATE=0x4e8630,
    ACTION_DTOR=0x129450,COMMAND_DTOR=0x4e7470,SUBMIT=0x14ca210;
struct Family { const char* name;std::uint32_t token;std::uintptr_t vtable,preview; };
constexpr Family families[]={
    {"corrupt_officials",0x337c,0x1c7c4a8,0x582730},
    {"sabotage_reputation",0x2ddd,0x1c7cfd8,0x57e900},
    {"sow_discontent",0x2ddf,0x1c7c9e8,0x585020},
    {"slander_merchants",0x337b,0x1c7c378,0x580260},
    {"sabotage_recruitment",0x33bf,0x1c7c5d8,0x581450}};
using Factory=void* (__fastcall*)(std::uint32_t,const void*);
using Preview=bool (__fastcall*)(void*,void*,bool);
using Wrapper=void** (__fastcall*)(void*,void**);
using Gate=bool (__fastcall*)(void*);
using Dtor=void* (__fastcall*)(void*,unsigned int);
using Submit=bool (__fastcall*)(void*,void**);
bool pointer(std::uintptr_t p) { return p>=0x10000 && p<0x800000000000ULL && p%8==0; }
bool hex(const char* p,std::size_t n) {
    bool nonzero=false;
    for(std::size_t i=0;i<n;++i) { const char c=p[i];if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return false;nonzero|=c!='0'; }
    return p[n]==0 && nonzero;
}
bool same_identity(const Identity& a,const Identity& b) {
    return a.pid==b.pid && a.creation_filetime==b.creation_filetime
        && std::memcmp(a.session,b.session,33)==0 && std::memcmp(a.dll_sha256,b.dll_sha256,65)==0
        && std::memcmp(a.manifest_sha256,b.manifest_sha256,65)==0;
}
bool same_stamp(const Stamp& a,const Stamp& b) {
    return a.game==b.game && a.database==b.database && a.countries==b.countries
        && a.actor_country==b.actor_country && a.target_country==b.target_country && a.server==b.server
        && a.pause_manager==b.pause_manager && a.actor==b.actor && a.target==b.target && a.player==b.player
        && a.date==b.date && a.holder==b.holder && a.context==b.context && a.transport==b.transport
        && a.actor_overlord==b.actor_overlord && a.target_overlord==b.target_overlord
        && a.effective_player==b.effective_player && a.country_count==b.country_count
        && a.context_ready55==b.context_ready55 && a.context_ready80d==b.context_ready80d
        && a.native_speed_index==b.native_speed_index;
}
bool same_fields(const Fields& a,const Fields& b) {
    return a.vtable==b.vtable && a.marker==b.marker && a.actor==b.actor && a.controller==b.controller
        && a.target==b.target && a.primary_date==b.primary_date && a.secondary_date==b.secondary_date
        && a.envoy==b.envoy && a.state==b.state && a.value==b.value && a.flag39==b.flag39 && a.identifier==b.identifier;
}
unsigned nibble(char c) { return static_cast<unsigned>(c<='9'?c-'0':c-'a'+10); }
} // namespace

struct Runner {
    Core* core;const Host* host;Operation operation;Result result;Stamp observed;
    std::uintptr_t original,clone,command;
    Item& item() { return result.current_item; }
    bool fail(Reason why) {
        if(result.reason==Reason::none)result.reason=why;
        result.state=State::frozen;result.freeze_session=true;result.accepted_call=false;
        result.ownership_uncertain=item().has_local_original || item().has_local_command || item().has_local_clone
            || (item().submit_entered && item().outcome==Outcome::dispatch_unknown)
            || (item().call_entered && !item().call_returned) || why==Reason::native_exception
            || why==Reason::factory_unknown || why==Reason::alias_or_ownership;
        InterlockedExchange(&core->frozen_,1);return false;
    }
    bool healthy() { return !InterlockedCompareExchange(&core->frozen_,0,0) || fail(Reason::frozen); }
    bool read(std::uintptr_t p,void* out,std::size_t n) {
        if(!healthy())return false;
        if(!p || !n || n>64 || result.read_calls>=8192 || result.bytes_read>1048576-n
            || core->total_reads_>=65536 || core->total_bytes_>8388608-n)return fail(Reason::read_budget);
        ++result.read_calls;result.bytes_read+=n;++core->total_reads_;core->total_bytes_+=n;
        if(!host->read(host->user,p,out,n))return fail(Reason::root_guard);
        return healthy();
    }
    template<class T> bool get(std::uintptr_t p,T& v) { return read(p,&v,sizeof(v)); }
    template<class T> bool put(std::size_t off,T v) {
        if(!healthy())return false;
        if(!original || !item().has_local_original || off<0x10 || off+sizeof(T)>0x40)return fail(Reason::alias_or_ownership);
        if(!host->write_owned(host->user,original+off,&v,sizeof(v)))return fail(Reason::fields_mismatch);
        return healthy();
    }
    bool bytes_pin(std::uintptr_t rva,const char* h) {
        std::size_t length=0;while(h[2*length] && length<512)++length;
        if(!length || length>=512 || h[2*length])return fail(Reason::image_pin);
        for(std::size_t off=0;off<length;off+=32) {
            unsigned char raw[32]{};const auto count=(length-off)<32?length-off:32;
            if(!read(host->image_base+rva+off,raw,count))return false;
            for(std::size_t i=0;i<count;++i)if(raw[i]!=nibble(h[2*(off+i)])*16+nibble(h[2*(off+i)+1]))return fail(Reason::image_pin);
        }return true;
    }
    bool code_pin(std::uintptr_t rva) {
        bool matched=false;
        for(const auto& p:eu4_spy18::kCodePins)if(p.rva==rva) { matched=true;if(!bytes_pin(p.rva,p.hex))return false; }
        for(const auto& p:eu4_spy19_sender::kCodePins)if(p.rva==rva) { matched=true;if(!bytes_pin(p.rva,p.hex))return false; }
        return matched || fail(Reason::image_pin);
    }
    bool image() {
        std::uint16_t mz=0,machine=0,magic=0;std::uint32_t nt=0,signature=0,timestamp=0,size=0;
        if(!get(host->image_base,mz)||!get(host->image_base+0x3c,nt)||mz!=0x5a4d||!nt||nt>4096)return fail(Reason::image_pin);
        const auto p=host->image_base+nt;
        if(!get(p,signature)||!get(p+4,machine)||!get(p+8,timestamp)||!get(p+24,magic)||!get(p+80,size)
            ||signature!=0x4550||machine!=0x8664||timestamp!=0x66fe6ab9||magic!=0x20b||size!=0x25e0000)return fail(Reason::image_pin);
        for(const auto& pin:eu4_spy18::kCodePins)if(!bytes_pin(pin.rva,pin.hex))return false;
        for(const auto& pin:eu4_spy19_sender::kCodePins)if(!bytes_pin(pin.rva,pin.hex))return false;
        for(const auto& pin:eu4_spy18::kSlotPins) { std::uintptr_t v=0;if(!get(host->image_base+pin.rva,v)||v!=host->image_base+pin.target)return fail(Reason::image_pin); }
        for(const auto& pin:eu4_spy19_sender::kSlotPins) { std::uintptr_t v=0;if(!get(host->image_base+pin.rva,v)||v!=host->image_base+pin.target)return fail(Reason::image_pin); }
        return true;
    }
    bool stamp(Stamp& s) {
        std::uintptr_t value=0,begin=0,end=0;std::int32_t count=0;
        std::uint8_t manual=0,reset=0,ironman=0,selector=0,alternate=0,multi=0;
        if(!get(host->image_base+0x233d8d0,s.database)||!get(host->image_base+0x233fe78,s.game)
            ||!pointer(s.database)||!pointer(s.game)||!get(s.database+0x124,count)||count<=122||count>4096
            ||!get(s.database+0x118,s.countries)||!pointer(s.countries))return fail(Reason::root_guard);
        s.country_count=static_cast<std::uint32_t>(count);
        if(!get(s.countries+122*8,s.actor_country)||!get(s.countries+46*8,s.target_country)
            ||!pointer(s.actor_country)||!pointer(s.target_country)||s.actor_country==s.target_country
            ||!get(s.actor_country+0x20,s.actor)||!get(s.target_country+0x20,s.target)||s.actor!=FRA||s.target!=ENG
            ||!get(s.actor_country+0x18f0,s.actor_overlord)||!get(s.target_country+0x18f0,s.target_overlord)
            ||s.actor_overlord>>56||s.target_overlord>>56||!get(s.game+0x1e60,s.player)||s.player!=FRA
            ||!get(s.game+0x1e66,selector)||!get(s.game+0x1e6f,alternate))return fail(Reason::root_guard);
        s.effective_player=s.player;
        if(selector==7&&alternate&&!get(s.game+0x1e68,s.effective_player))return false;
        if(s.effective_player!=FRA||!get(s.game+0x1dd0,s.date)||s.date<=0||!get(s.game+0x1e00,s.server)||!pointer(s.server)
            ||!get(s.server,value)||value!=host->image_base+0x1cb8460||!get(s.server+0x418,s.pause_manager)||!pointer(s.pause_manager)
            ||!get(s.pause_manager+0x50,value)||value!=s.server||!get(s.pause_manager+0x48,manual)||manual!=1
            ||!get(s.pause_manager,begin)||!get(s.pause_manager+8,end)||(begin==0)!=(end==0)
            ||(begin&&(!pointer(begin)||!pointer(end)))||end<begin||(end-begin)%8||(end-begin)/8>256
            ||!get(s.game+0x7485,reset)||reset||!get(s.game+0x74c8,value)||value
            ||!get(s.game+0x24d0,ironman)||ironman||!get(s.game+0x1e08,s.native_speed_index)
            ||s.native_speed_index<0||s.native_speed_index>4||!get(s.server+0x19f1,multi)||multi!=0)return fail(Reason::root_guard);
        // Restrict the reviewed server flag to 0; this is NOT strict SP proof.
        if(!get(s.server+0x330,s.holder)||!pointer(s.holder)||!get(s.holder+0x370,s.context)||!pointer(s.context)
            ||!get(s.context+0x58,s.transport)||!pointer(s.transport)||!get(s.transport,value)||value!=host->image_base+0x1d96178
            ||!get(s.context+0x55,s.context_ready55)||!get(s.context+0x80d,s.context_ready80d)
            ||(!s.context_ready55&&!s.context_ready80d))return fail(Reason::root_guard);
        return true;
    }
    bool barrier(Point point) {
        if(!healthy())return false;
        if(GetCurrentThreadId()!=host->expected_game_thread)return fail(Reason::wrong_thread);
        const auto now=host->clock(host->user);
        if(!healthy()||now<core->last_clock_)return fail(Reason::root_guard);
        core->last_clock_=now;
        if(point==Point::before_work&&now>=host->expires_uptime_ms)return fail(Reason::rejected_guard);
        Stamp first{},second{};if(!stamp(first)||!stamp(second)||!same_stamp(first,second))return fail(Reason::root_guard);
        if(!core->locked_.game)core->locked_=first;
        if(!same_stamp(first,core->locked_))return fail(Reason::root_guard);
        observed=first;
        if(!host->guard(host->user,point,item().step,&host->identity,&first))return fail(Reason::rejected_guard);
        return healthy();
    }
    bool audit(Kind kind) {
        if(!healthy())return false;
        if(core->events_>=256)return fail(Reason::event_budget);
        ++core->events_;Event e{};e.kind=kind;e.operation=operation;e.identity=host->identity;e.stamp=observed;e.item=item();
        e.request_sequence=4;e.completed=result.completed;e.frame=host->frame_id;e.uptime_ms=core->last_clock_;
        e.expires_uptime_ms=host->expires_uptime_ms;e.reason=result.reason;e.state=result.state;
        e.exception_code=result.exception_code;e.mock_resolver=host->isolated_mock_resolver;
        if(!host->log(host->user,&e))return fail(Reason::audit_failed);
        return healthy();
    }
    bool fields(std::uintptr_t p,Fields& f) {
        if(!pointer(p)||p==host->image_base+0x1fd1ca0)return fail(Reason::factory_unknown);
        return get(p,f.vtable)&&get(p+8,f.marker)&&get(p+0x10,f.actor)&&get(p+0x18,f.controller)&&get(p+0x20,f.target)
            &&get(p+0x28,f.primary_date)&&get(p+0x2c,f.secondary_date)&&get(p+0x30,f.envoy)&&get(p+0x34,f.state)
            &&get(p+0x38,f.value)&&get(p+0x39,f.flag39)&&get(p+0x3c,f.identifier);
    }
    Fields expected(bool initialized) const {
        Fields f{};f.vtable=host->image_base+families[result.current_item.family].vtable;f.marker=0x165;
        f.actor=f.controller=initialized?FRA:SENTINEL;f.target=initialized?ENG:SENTINEL;
        f.primary_date=f.secondary_date=initialized?core->locked_.date:43808760;f.envoy=-1;f.value=1;return f;
    }
    bool verify_original(bool initialized) {
        Fields f{};if(!original||!item().has_local_original||!fields(original,f)||!same_fields(f,expected(initialized)))return fail(Reason::fields_mismatch);
        item().original_fields=f;return true;
    }
    bool command_contract() {
        std::uintptr_t vt=0,held=0;std::uint64_t q=0;std::uint32_t marker=0,token=0,d=0;
        std::uint16_t w=0;std::uint8_t b=0;std::int32_t sentinel=0;Fields f{};
        if(!item().has_local_command||!item().has_local_clone||!pointer(command)||!pointer(clone)
            ||command==original||command==clone||clone==original||command==host->image_base+0x1fd1ca0
            ||!get(command,vt)||vt!=host->image_base+0x1c814b0||!get(command+8,marker)||marker!=0x165
            ||!get(command+0x44,token)||token!=0x2934||!get(command+0x10,b)||b!=0
            ||!get(command+0x18,q)||q!=0||!get(command+0x28,q)||q!=0||!get(command+0x30,q)||q!=15
            ||!get(command+0x38,sentinel)||sentinel!=-1||!get(command+0x3c,d)||d!=0||!get(command+0x40,w)||w!=0
            ||!get(command+0x48,q)||q!=0xffff||!get(command+0x50,held)||held!=clone
            ||!fields(clone,f)||!same_fields(f,expected(true)))return fail(Reason::alias_or_ownership);
        item().clone_fields=f;return true;
    }
    bool begin_call(Step step,std::uintptr_t rva,bool cleanup,std::uintptr_t& fn) {
        item().step=step;item().call_entered=item().call_returned=false;
        const auto point=cleanup?Point::before_cleanup:Point::before_work;
        if(!barrier(point)||!code_pin(rva)||!audit(Kind::step_intent)||!barrier(point))return false;
        fn=host->resolve(host->user,rva);
        if(!healthy())return false;
        if(!fn||(!host->isolated_mock_resolver&&fn!=host->image_base+rva))return fail(Reason::resolver_failed);
        return true; // A durable intent is never an actual-enter assertion.
    }
    bool returned() { return barrier(Point::after_work)&&audit(Kind::step_return); }
    bool destroy(bool cmd) {
        if(cmd?!command_contract():!verify_original(true))return false;
        std::uintptr_t fn=0;if(!begin_call(cmd?Step::destroy_command:Step::destroy_original,cmd?COMMAND_DTOR:ACTION_DTOR,true,fn))return false;
        if(cmd?!command_contract():!verify_original(true))return false;
        item().call_entered=true;
        reinterpret_cast<Dtor>(fn)(reinterpret_cast<void*>(cmd?command:original),1U);
        item().call_returned=true;
        if(cmd) { command=clone=0;item().has_local_command=item().has_local_clone=false;item().command_destroyed=item().clone_destroyed=true; }
        else { original=0;item().has_local_original=false;item().original_destroyed=true; }
        return returned();
    }
    bool initialize() {
        item().step=Step::initialize;item().call_entered=item().call_returned=false;
        if(!barrier(Point::before_work)||!audit(Kind::step_intent)||!barrier(Point::before_work)||!verify_original(false))return false;
        const auto f=expected(true);
        if(!put(0x10,f.actor)||!put(0x18,f.controller)||!put(0x20,f.target)||!put(0x28,f.primary_date)||!put(0x2c,f.secondary_date)
            ||!put(0x30,f.envoy)||!put(0x34,f.state)||!put(0x38,f.value)||!put(0x39,f.flag39)||!put(0x3c,f.identifier))return false;
        return verify_original(true)&&returned();
    }
    bool finish_item() {
        if(original||clone||command||item().has_local_original||item().has_local_clone||item().has_local_command)return fail(Reason::alias_or_ownership);
        if(!barrier(Point::after_work)||!audit(Kind::item_return))return false;
        result.state=State::awaiting_health;core->completion_frame_=host->frame_id;result.audit_complete=true;return true;
    }
    bool run_item() {
        if(result.state!=State::ready||result.completed>=5||host->frame_id<=core->completion_frame_)return fail(Reason::order);
        item()={};item().current=true;item().family=result.completed;item().ordinal=result.completed+1;
        item().token=families[item().family].token;item().owner_frame=host->frame_id;item().outcome=Outcome::in_progress;
        item().step=Step::item_claim;
        if(!barrier(Point::before_work)||!host->claim(host->user,4,item().ordinal,&host->identity,&observed))return fail(Reason::claim_failed);
        item().claimed=true; // Retain a true durable receipt even if reentry froze us.
        if(!healthy())return false;
        if(!audit(Kind::item_claimed))return false;
        std::uintptr_t fn=0;if(!begin_call(Step::factory,FACTORY,false,fn))return false;
        item().call_entered=true;
        original=reinterpret_cast<std::uintptr_t>(reinterpret_cast<Factory>(fn)(item().token,nullptr));
        item().call_returned=true;
        if(!original||original==host->image_base+0x1fd1ca0)return fail(Reason::factory_unknown);
        item().has_local_original=true;item().original_id=++core->next_object_id_;
        if(!verify_original(false)||!returned()||!initialize())return false;
        if(!begin_call(Step::full_preview,families[item().family].preview,false,fn)||!verify_original(true))return false;
        item().call_entered=true;item().preview_allowed=reinterpret_cast<Preview>(fn)(reinterpret_cast<void*>(original),nullptr,false);
        item().call_returned=true;item().preview_observed=true;
        if(!verify_original(true)||!returned())return false;
        if(!item().preview_allowed) { item().outcome=Outcome::full_preview_rejected;return destroy(false)&&finish_item(); }
        if(!begin_call(Step::wrap_owned,WRAPPER,false,fn)||!verify_original(true))return false;
        void* slot=nullptr;item().call_entered=true;
        void** output=reinterpret_cast<Wrapper>(fn)(reinterpret_cast<void*>(original),&slot);
        item().call_returned=true;command=reinterpret_cast<std::uintptr_t>(slot);
        if(output!=&slot||!pointer(command)||command==original||!get(command+0x50,clone)||clone==original||clone==command)return fail(Reason::alias_or_ownership);
        item().has_local_command=item().has_local_clone=true;item().command_id=++core->next_object_id_;item().clone_id=++core->next_object_id_;
        if(!verify_original(true)||!command_contract()||!returned())return false;
        if(!begin_call(Step::command_gate,GATE,false,fn)||!verify_original(true)||!command_contract())return false;
        item().call_entered=true;item().gate_allowed=reinterpret_cast<Gate>(fn)(reinterpret_cast<void*>(command));
        item().call_returned=true;item().gate_observed=true;
        if(!verify_original(true)||!command_contract()||!returned())return false;
        if(!item().gate_allowed) { item().outcome=Outcome::command_gate_rejected;return destroy(true)&&destroy(false)&&finish_item(); }
        if(!destroy(false)||!command_contract()||!begin_call(Step::submit,SUBMIT,false,fn)||!command_contract())return false;
        if(!audit(Kind::dispatch_intent)||!barrier(Point::before_work)||!command_contract()
            ||!barrier(Point::before_work))return false;
        // This is the only transfer. From actual entry onward, no object read,
        // destructor or reconstitution is permitted, even if false is returned.
        slot=reinterpret_cast<void*>(command);command=clone=0;
        item().has_local_command=item().has_local_clone=false;item().outcome=Outcome::dispatch_unknown;
        item().call_entered=item().submit_entered=true;
        const bool accepted=reinterpret_cast<Submit>(fn)(reinterpret_cast<void*>(observed.context),&slot);
        item().call_returned=item().submit_returned=true;
        item().submit_value_observed=item().slot_observed=true;item().submit_value=accepted;item().slot_consumed=slot==nullptr;
        if(!returned())return false;
        if(!accepted||slot!=nullptr)return fail(Reason::transfer_unknown);
        item().outcome=Outcome::dispatched;return finish_item();
    }
    bool start() {
        if(result.state!=State::fresh)return fail(Reason::order);
        item().step=Step::batch_claim;
        if(!barrier(Point::before_work)||!host->claim(host->user,4,0,&host->identity,&observed))return fail(Reason::claim_failed);
        if(!healthy()||!audit(Kind::batch_claimed))return false;
        result.state=State::ready;core->completion_frame_=host->frame_id;result.audit_complete=true;return true;
    }
    bool health() {
        if(result.state!=State::awaiting_health||!item().current||host->frame_id<=core->completion_frame_||!barrier(Point::after_work))return fail(Reason::order);
        if(!audit(Kind::later_health))return false;
        result.completed_outcomes[result.completed]=item().outcome;++result.completed;item().current=false;
        result.state=result.completed==5?State::complete:State::ready;core->completion_frame_=host->frame_id;
        if(result.state==State::complete&&!audit(Kind::batch_complete))return false;
        result.audit_complete=true;return true;
    }
    bool validate_host() {
        const auto& h=*host;
        if(h.struct_size!=sizeof(Host)||h.abi_version!=1||!h.read||!h.write_owned||!h.resolve||!h.clock||!h.guard||!h.log||!h.claim
            ||!h.full_sha256_verified||!h.same_session_preflight_verified||!h.disposable_test_authorized||h.request_sequence!=4
            ||!pointer(h.image_base)||!h.game_sha256||std::memcmp(h.game_sha256,GAME_SHA,64)!=0||h.game_sha256[64]
            ||!h.identity.pid||!h.identity.creation_filetime||!hex(h.identity.session,32)||!hex(h.identity.dll_sha256,64)
            ||!hex(h.identity.manifest_sha256,64)||std::memcmp(h.identity.dll_sha256,OLD_DLL,65)==0||!h.frame_id)return fail(Reason::bad_host);
        if(GetCurrentThreadId()!=h.expected_game_thread)return fail(Reason::wrong_thread);
        if(result.state!=State::fresh) {
            const auto& old=core->locked_host_;
            if(!same_identity(old.identity,h.identity)||h.image_base!=old.image_base||h.expected_game_thread!=old.expected_game_thread
                ||h.expires_uptime_ms!=old.expires_uptime_ms||h.isolated_mock_resolver!=old.isolated_mock_resolver
                ||h.read!=old.read||h.write_owned!=old.write_owned||h.resolve!=old.resolve||h.clock!=old.clock
                ||h.guard!=old.guard||h.log!=old.log||h.claim!=old.claim||h.user!=old.user)return fail(Reason::bad_host);
        }
        if(h.frame_id<=core->last_frame_)return fail(Reason::order);
        core->last_frame_=h.frame_id;
        const auto now=h.clock(h.user);if(!healthy()||now<core->last_clock_)return fail(Reason::root_guard);
        core->last_clock_=now;
        if(result.state==State::fresh) {
            if(h.expires_uptime_ms<=now||h.expires_uptime_ms-now>60000)return fail(Reason::rejected_guard);
            core->locked_host_=h;
        }
        return image();
    }
};

Core::Core() noexcept:active_(0),frozen_(0),locked_host_{},locked_{},saved_{},next_object_id_(0),events_(0),
    total_reads_(0),total_bytes_(0),last_clock_(0),last_frame_(0),completion_frame_(0) {}
Result Core::invoke(Operation operation,const Host& host) {
    if(InterlockedCompareExchange(&active_,1,0)) {
        InterlockedExchange(&frozen_,1);Result blocked{};blocked.state=State::frozen;blocked.reason=Reason::busy;
        blocked.freeze_session=blocked.ownership_uncertain=true;return blocked;
    }
    const Host bound=host; // Stable private callback/identity/expiry values for this invocation.
    Runner r{};r.core=this;r.host=&bound;r.operation=operation;r.result=saved_;
    r.result.accepted_call=r.result.audit_complete=false;r.result.read_calls=0;r.result.bytes_read=0;
    __try {
        if(r.healthy()&&r.validate_host()) {
            bool ok=false;
            if(operation==Operation::begin)ok=r.start();
            else if(operation==Operation::next_item)ok=r.run_item();
            else if(operation==Operation::later_health)ok=r.health();
            else r.fail(Reason::order);
            if(ok&&r.healthy())r.result.accepted_call=true;
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) { r.result.exception_code=GetExceptionCode();r.fail(Reason::native_exception); }
    if(r.result.reason!=Reason::none) {
        // Best-effort diagnostic only. This cannot unfreeze or authorize cleanup.
        __try {
            if(bound.log) { Event e{};e.kind=Kind::fault;e.operation=operation;e.identity=bound.identity;e.item=r.item();e.stamp=r.observed;
                e.reason=r.result.reason;e.state=State::frozen;e.exception_code=r.result.exception_code;e.request_sequence=4;
                e.frame=bound.frame_id;e.uptime_ms=last_clock_;e.expires_uptime_ms=bound.expires_uptime_ms;e.completed=r.result.completed;
                e.mock_resolver=bound.isolated_mock_resolver;bound.log(bound.user,&e); }
        } __except(EXCEPTION_EXECUTE_HANDLER) { }
    }
    saved_=r.result;InterlockedExchange(&active_,0);return r.result;
}
const char* family_name(std::uint32_t n) noexcept { return n<5?families[n].name:nullptr; }
} // namespace eu4_spy19
