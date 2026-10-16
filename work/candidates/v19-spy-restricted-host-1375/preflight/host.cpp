#include "host.h"
#include "../core/v18-preimage/pins.h"
#include <cstdarg>
#include <cstring>

namespace eu4_spy_host18 {
namespace {
constexpr std::uint64_t FRA=0x0100007a00415246ULL,ENG=0x0100002e00474e45ULL;
bool ptr(std::uintptr_t p) { return p>=0x10000 && p<0x800000000000ULL && p%8==0; }
bool stamp_equal(const eu4_spy18::Stamp& a,const eu4_spy18::Stamp& b) {
    return a.game==b.game && a.database==b.database && a.countries==b.countries
        && a.actor_country==b.actor_country && a.target_country==b.target_country
        && a.server==b.server && a.pause_manager==b.pause_manager
        && a.actor==b.actor && a.target==b.target && a.player==b.player && a.date==b.date;
}
const char* tf(bool v) { return v?"true":"false"; }
struct Line {
    char bytes[8192];std::size_t used;bool valid;
    Line() noexcept:bytes{},used(0),valid(true) {}
    void add(const char* format,...) {
        if(!valid)return;va_list args;va_start(args,format);
        const int n=vsnprintf(bytes+used,sizeof(bytes)-used,format,args);va_end(args);
        if(n<0 || static_cast<std::size_t>(n)>=sizeof(bytes)-used) { valid=false;return; }used+=static_cast<std::size_t>(n);
    }
    void fields(const eu4_spy18::Fields& f) {
        add("{\"vtable\":%llu,\"marker\":%u,\"actor\":%llu,\"controller\":%llu,\"target\":%llu,\"primary_date\":%d,\"secondary_date\":%d,\"envoy\":%d,\"state\":%u,\"value\":%u,\"flag39\":%u,\"identifier\":%u}",
            static_cast<unsigned long long>(f.vtable),f.marker,static_cast<unsigned long long>(f.actor),static_cast<unsigned long long>(f.controller),
            static_cast<unsigned long long>(f.target),f.primary_date,f.secondary_date,f.envoy,f.state,static_cast<unsigned>(f.value),static_cast<unsigned>(f.flag39),f.identifier);
    }
    void stamp(const eu4_spy18::Stamp& s) {
        add("{\"game\":%llu,\"database\":%llu,\"countries\":%llu,\"actor_country\":%llu,\"target_country\":%llu,\"server\":%llu,\"pause_manager\":%llu,\"actor\":%llu,\"target\":%llu,\"player\":%llu,\"date\":%d}",
            static_cast<unsigned long long>(s.game),static_cast<unsigned long long>(s.database),static_cast<unsigned long long>(s.countries),static_cast<unsigned long long>(s.actor_country),static_cast<unsigned long long>(s.target_country),static_cast<unsigned long long>(s.server),static_cast<unsigned long long>(s.pause_manager),static_cast<unsigned long long>(s.actor),static_cast<unsigned long long>(s.target),static_cast<unsigned long long>(s.player),s.date);
    }
    void frame(const Frame& f) {
        const auto& s=f.stamp;
        add("{\"game\":%llu,\"database\":%llu,\"countries\":%llu,\"actor_country\":%llu,\"target_country\":%llu,\"server\":%llu,\"pause_manager\":%llu,\"actor\":%llu,\"target\":%llu,\"player\":%llu,\"raw_date\":%d,\"country_count\":%u,\"actor_overlord\":%llu,\"target_overlord\":%llu,\"effective_player\":%llu,\"manual_pause\":%u,\"reset\":%u,\"ironman\":%u,\"selector\":%u,\"alternate_selector\":%u,\"speed_index\":%d,\"multiplayer_classifier\":%s,\"load_source\":%llu}",
            static_cast<unsigned long long>(s.game),static_cast<unsigned long long>(s.database),static_cast<unsigned long long>(s.countries),
            static_cast<unsigned long long>(s.actor_country),static_cast<unsigned long long>(s.target_country),static_cast<unsigned long long>(s.server),
            static_cast<unsigned long long>(s.pause_manager),static_cast<unsigned long long>(s.actor),static_cast<unsigned long long>(s.target),static_cast<unsigned long long>(s.player),
            s.date,f.countries_count,static_cast<unsigned long long>(f.actor_overlord),static_cast<unsigned long long>(f.target_overlord),
            static_cast<unsigned long long>(f.effective_player),static_cast<unsigned>(f.manual_pause),static_cast<unsigned>(f.reset),static_cast<unsigned>(f.ironman),
            static_cast<unsigned>(f.selector),static_cast<unsigned>(f.alternate_selector),f.native_speed_index,tf(f.multiplayer_classifier),static_cast<unsigned long long>(f.load_source));
    }
    void envelope(const Identity& id,const Frame& observed,std::uint64_t ordinal,std::uint64_t frame_no,std::uint64_t now,bool mock,std::uintptr_t image_base) {
        add("\"schema\":\"EU4SPYHOST/1\",\"pid\":%u,\"creation\":\"%016llx\",\"session\":\"%s\",\"game_sha256\":\"%s\",\"dll_sha256\":\"%s\",\"manifest_sha256\":\"%s\",\"ordinal\":%llu,\"frame\":%llu,\"uptime_ms\":%llu,\"thread\":%u,\"mock_environment\":%s,\"send_supported\":false,\"strict_sp_verified\":false,\"epoch_verified\":false,\"production_ready\":false,\"observed\":",
            id.pid,static_cast<unsigned long long>(id.creation),id.session,kGameSha,id.dll_sha256,id.manifest_sha256,
            static_cast<unsigned long long>(ordinal),static_cast<unsigned long long>(frame_no),static_cast<unsigned long long>(now),observed.thread,tf(mock));frame(observed);add(",\"image_base\":%llu",static_cast<unsigned long long>(image_base));
    }
};
}
bool same_frame(const Frame& a,const Frame& b) noexcept {
    return stamp_equal(a.stamp,b.stamp) && a.countries_count==b.countries_count && a.thread==b.thread
        && a.actor_overlord==b.actor_overlord && a.target_overlord==b.target_overlord && a.effective_player==b.effective_player
        && a.manual_pause==b.manual_pause && a.reset==b.reset && a.ironman==b.ironman
        && a.selector==b.selector && a.alternate_selector==b.alternate_selector && a.native_speed_index==b.native_speed_index
        && a.multiplayer_classifier==b.multiplayer_classifier && a.load_source==b.load_source;
}
Controller::Controller() noexcept:started_(0),active_(0),frozen_(0),failure_(0),env_{},journal_{},core_{},status_{},locked_{},locked_valid_(false),
    audit_failed_(false),active_request_{},clock_(0),ordinal_(0),completion_frame_(0),read_calls_(0),read_bytes_(0),
    current_step_(eu4_spy18::Step::none),current_family_(0),original_id_(0),write_index_(0),owned_base_(0),factory_return_verified_(false),receipts_{} {}
bool Controller::fail(Failure reason) {
    InterlockedCompareExchange(&failure_,static_cast<LONG>(reason),0);InterlockedExchange(&frozen_,1);return false;
}
bool Controller::start(const Environment& env,const Journal& journal) {
    if(InterlockedCompareExchange(&started_,1,0))return fail(Failure::already_started);
    if(!identity_valid(env.identity)||!ptr(env.image_base)||!env.owner_thread||!env.exact_disk_and_loaded_image_verified
        ||!env.read||!env.write||!env.resolve||!env.clock||!env.sample||!env.current_thread||!env.begin_frame||!journal.append||!journal.claim)
        return fail(Failure::bad_environment);
    env_=env;journal_=journal;status_.state=State::ready;return true;
}
Status Controller::status() const noexcept {
    // Owner-thread only; foreign reentry changes atomic terminal flags only.
    auto result=status_;if(frozen_)result.state=State::frozen;result.failure=static_cast<Failure>(failure_);return result;
}
bool Controller::completed_preflight(PreflightProof& out) const noexcept {
    if(frozen_||!started_||active_||!locked_valid_||status_.state!=State::complete||status_.completed!=3||status_.claimed!=3)return false;
    for(unsigned i=0;i<3;++i) {
        const auto& s=receipts_[i];const auto& r=s.result;
        if(!s.durable_result||!s.later_health||!s.completion_frame||s.later_health_frame<=s.completion_frame
            ||r.stage!=static_cast<eu4_spy18::Stage>(i+1)||!r.completed||!r.audit_complete||r.freeze_session||r.ownership_uncertain
            ||r.reason!=eu4_spy18::Reason::none||r.exception_code||r.cases_complete!=5||r.send_supported||r.runtime_verified||r.production_ready)return false;
        for(unsigned f=0;f<5;++f)if(r.allowed_observed[f]!=(i!=0)||(!r.allowed_observed[f]&&r.allowed[f]))return false;
        if(i&&s.completion_frame<=receipts_[i-1].later_health_frame)return false;
    }
    PreflightProof proof{};proof.identity=env_.identity;proof.world=locked_;
    for(unsigned i=0;i<3;++i)proof.stages[i]=receipts_[i];out=proof;return true;
}
bool Controller::sample(Frame& result) {
    Frame a{},b{};
    if(!env_.sample(env_.user,&a)||!env_.sample(env_.user,&b)||!same_frame(a,b))return fail(Failure::unavailable_world);
    const auto& s=a.stamp;
    if(!ptr(s.game)||!ptr(s.database)||!ptr(s.countries)||!ptr(s.actor_country)||!ptr(s.target_country)||!ptr(s.server)||!ptr(s.pause_manager)
        ||s.actor_country==s.target_country||s.actor!=FRA||s.target!=ENG||s.player!=FRA||s.date<=0
        ||a.countries_count<=122||a.countries_count>4096||a.actor_overlord>>56||a.target_overlord>>56||a.effective_player!=FRA
        ||a.thread!=env_.owner_thread||a.manual_pause!=1||a.reset!=0||a.ironman!=0||a.load_source!=0||a.multiplayer_classifier
        ||a.native_speed_index<0||a.native_speed_index>4)return fail(Failure::unavailable_world);
    if(locked_valid_ && !same_frame(a,locked_))return fail(Failure::changed_world);
    result=a;return true;
}
bool Controller::barrier(bool expiry) {
    if(InterlockedCompareExchange(&frozen_,0,0))return false;
    if(env_.current_thread(env_.user)!=env_.owner_thread)return fail(Failure::wrong_thread);
    const auto now=env_.clock(env_.user);if(now<clock_)return fail(Failure::clock_regressed);clock_=now;
    if(expiry && now>=active_request_.expires)return fail(Failure::expired);
    Frame observed{};if(!sample(observed))return false;
    if(!locked_valid_) { locked_=observed;locked_valid_=true; }
    return InterlockedCompareExchange(&frozen_,0,0)==0;
}
bool Controller::append(const char* data,int length,bool diagnostic) {
    if(audit_failed_||length<=0||length>8192)return fail(Failure::audit_failed);
    if(!journal_.append(journal_.user,data,static_cast<std::size_t>(length))) { audit_failed_=true;return fail(Failure::audit_failed); }
    ++ordinal_;return diagnostic || !InterlockedCompareExchange(&frozen_,0,0);
}
bool Controller::host_record(const char* event,const eu4_spy18::Result* result,bool current_observation) {
    Line line;line.add("{\"event\":\"%s\",",event);line.envelope(env_.identity,locked_,ordinal_+1,status_.frames,clock_,env_.mock,env_.image_base);
    line.add(",\"claimed_sequence\":%u,\"completed_stages\":%u,\"owner_hook_installed\":false,\"loader_implemented\":false,\"runtime_verified\":false",status_.claimed,status_.completed);
    line.add(",\"current_observation_verified\":%s",tf(current_observation));
    if(result) {
        line.add(",\"result\":{\"stage\":%u,\"reason\":%u,\"step\":%u,\"family\":%u,\"cases_complete\":%u,\"exception_code\":%u,\"completed\":%s,\"audit_complete\":%s,\"freeze_session\":%s,\"ownership_uncertain\":%s,\"reads\":%u,\"bytes_read\":%llu,\"allowed_observed\":[",
            static_cast<unsigned>(result->stage),static_cast<unsigned>(result->reason),static_cast<unsigned>(result->step),result->family,result->cases_complete,result->exception_code,
            tf(result->completed),tf(result->audit_complete),tf(result->freeze_session),tf(result->ownership_uncertain),result->reads,static_cast<unsigned long long>(result->bytes_read));
        for(unsigned i=0;i<5;++i)line.add("%s%s",i?",":"",tf(result->allowed_observed[i]));line.add("],\"allowed\":[");
        for(unsigned i=0;i<5;++i)line.add("%s%s",i?",":"",tf(result->allowed[i]));
        line.add("],\"retry_allowed\":false,\"send_supported\":false,\"runtime_verified\":false,\"production_ready\":false}");
    }
    line.add("}\n");if(!line.valid)return fail(Failure::audit_failed);return append(line.bytes,static_cast<int>(line.used),!current_observation);
}
bool Controller::execute_frame(const char* packet,std::size_t length) {
    if(!InterlockedCompareExchange(&started_,0,0)||InterlockedCompareExchange(&frozen_,0,0))return false;
    if(env_.current_thread(env_.user)!=env_.owner_thread)return fail(Failure::wrong_thread);
    if(!env_.begin_frame(env_.user))return fail(Failure::read_budget);
    read_calls_=0;read_bytes_=0;
    if(status_.frames==UINT64_MAX)return fail(Failure::wrong_sequence);++status_.frames;
    if(!barrier(false))return false;
    const bool completes_health=status_.state==State::awaiting_health;
    if(completes_health) {
        if(status_.frames<=completion_frame_)return fail(Failure::wrong_sequence);
        status_.state=status_.completed==3?State::complete:State::ready;
    }
    if(status_.state!=State::ready && status_.state!=State::complete)return fail(Failure::reentered);
    if(!host_record("health"))return false;
    if(completes_health) {
        auto& receipt=receipts_[status_.completed-1];
        if(!receipt.durable_result||receipt.later_health||status_.frames<=receipt.completion_frame)return fail(Failure::core_failed);
        receipt.later_health=true;receipt.later_health_frame=status_.frames;
    }
    status_.last_health_frame=status_.frames;status_.last_health_time=clock_;
    if(!packet && length==0)return true;
    Request request{};
    if(!parse(packet,length,request)||!same_identity(request.identity,env_.identity))return fail(Failure::invalid_request);
    if(status_.state!=State::ready||request.sequence!=status_.claimed+1||request.sequence!=status_.completed+1)return fail(Failure::wrong_sequence);
    const auto now=env_.clock(env_.user);
    if(now<clock_)return fail(Failure::clock_regressed);
    if(request.expires<=now||request.expires-now>60000||now-status_.last_health_time>2500)return fail(Failure::expired);
    active_request_=request;status_.state=State::running;
    // Claim is retained before any core entry; failure can never reopen this slot.
    if(!journal_.claim(journal_.user,request.sequence,packet,length))return fail(Failure::claim_failed);
    status_.claimed=request.sequence;
    if(!barrier(true))return false;
    Line claim;claim.add("{\"event\":\"claim\",");claim.envelope(env_.identity,locked_,ordinal_+1,status_.frames,clock_,env_.mock,env_.image_base);
    claim.add(",\"sequence\":%u,\"stage\":\"%s\",\"expires\":%llu,\"wire_hex\":\"",request.sequence,stage_name(request.stage),static_cast<unsigned long long>(request.expires));
    for(std::size_t i=0;i<length;++i)claim.add("%02x",static_cast<unsigned char>(packet[i]));claim.add("\",\"claim_created_and_flushed\":true,\"current_observation_verified\":true}\n");
    if(!claim.valid)return fail(Failure::audit_failed);if(!append(claim.bytes,static_cast<int>(claim.used)))return false;
    eu4_spy18::Host host{sizeof(eu4_spy18::Host),1,env_.owner_thread,env_.image_base,kGameSha,status_.frames,request.expires,
        true,true,true,true,env_.mock,read_cb,write_cb,resolve_cb,clock_cb,guard_cb,log_cb,this};
    const auto result=core_.run(request.stage,host);
    // Failed final callback is never promoted merely because its bytes exist.
    if(!result.completed||!result.audit_complete||result.freeze_session||result.ownership_uncertain||result.cases_complete!=5
        ||result.reason!=eu4_spy18::Reason::none||result.exception_code||InterlockedCompareExchange(&frozen_,0,0)) {
        fail(Failure::core_failed);if(!audit_failed_)host_record("terminal_result",&result,false);return false;
    }
    if(!barrier(false)||!host_record("run_result",&result))return false;
    auto& receipt=receipts_[request.sequence-1];
    if(receipt.durable_result||receipt.later_health)return fail(Failure::core_failed);
    receipt.result=result;receipt.durable_result=true;receipt.completion_frame=status_.frames;
    status_.completed=request.sequence;completion_frame_=status_.frames;status_.state=State::awaiting_health;
    return true;
}
bool Controller::frame(const char* packet,std::size_t length) {
    if(InterlockedCompareExchange(&active_,1,0))return fail(Failure::reentered);
    bool success=false;
    __try { success=execute_frame(packet,length); }
    __except(EXCEPTION_EXECUTE_HANDLER) { fail(Failure::core_failed); }
    InterlockedExchange(&active_,0);return success && !InterlockedCompareExchange(&frozen_,0,0);
}
bool Controller::read_cb(void* user,std::uintptr_t address,void* out,std::size_t size) {
    auto& self=*static_cast<Controller*>(user);
    if(InterlockedCompareExchange(&self.frozen_,0,0))return false;
    if(!size||size>64||self.read_calls_>=32768||self.read_bytes_>2097152-size)return self.fail(Failure::read_budget);
    ++self.read_calls_;self.read_bytes_+=size;
    return self.env_.read(self.env_.user,address,out,size) && !InterlockedCompareExchange(&self.frozen_,0,0);
}
bool Controller::owned_write(std::uintptr_t address,const void* data,std::size_t size) {
    if(status_.state!=State::running||current_step_!=eu4_spy18::Step::initialize||!factory_return_verified_||write_index_>=10
        ||!original_id_||!data||!barrier(true))return fail(Failure::owned_write_contract);
    constexpr std::size_t offsets[]={0x10,0x18,0x20,0x28,0x2c,0x30,0x34,0x38,0x39,0x3c};
    constexpr std::size_t widths[]={8,8,8,4,4,4,4,1,1,4};
    const std::uint64_t expected[]={FRA,FRA,ENG,static_cast<std::uint32_t>(locked_.stamp.date),
        static_cast<std::uint32_t>(locked_.stamp.date),0xffffffffU,0,1,0,0};
    if(size!=widths[write_index_]||std::memcmp(data,&expected[write_index_],size))return fail(Failure::owned_write_contract);
    if(write_index_==0) { if(address<0x10||!ptr(address-0x10))return fail(Failure::owned_write_contract);owned_base_=address-0x10;
        const auto& s=locked_.stamp;if(owned_base_==s.game||owned_base_==s.database||owned_base_==s.countries
            ||owned_base_==s.actor_country||owned_base_==s.target_country||owned_base_==s.server||owned_base_==s.pause_manager)return fail(Failure::owned_write_contract); }
    if(address!=owned_base_+offsets[write_index_]||!env_.write(env_.user,address,data,size))return fail(Failure::owned_write_contract);
    ++write_index_;return !InterlockedCompareExchange(&frozen_,0,0);
}
bool Controller::write_cb(void* user,std::uintptr_t p,const void* data,std::size_t size) { return static_cast<Controller*>(user)->owned_write(p,data,size); }
std::uintptr_t Controller::resolve_cb(void* user,std::uintptr_t rva) {
    auto& self=*static_cast<Controller*>(user);if(InterlockedCompareExchange(&self.frozen_,0,0))return 0;
    const std::uintptr_t allowed[]={0x35d210,0x129450,0x4e7470,0x4e9930,0x4e8630,0x582b20,0x57eca0,0x5853a0,0x580650,0x581840,0x582730,0x57e900,0x585020,0x580260,0x581450};
    bool known=false;for(const auto fixed:allowed)if(fixed==rva)known=true;if(!known) { self.fail(Failure::bad_environment);return 0; }
    const auto target=self.env_.resolve(self.env_.user,rva);
    return InterlockedCompareExchange(&self.frozen_,0,0)?0:target;
}
std::uint64_t Controller::clock_cb(void* user) { auto& self=*static_cast<Controller*>(user);return self.env_.clock(self.env_.user); }
bool Controller::guard_cb(void* user,eu4_spy18::GuardPoint point,eu4_spy18::Stage stage,eu4_spy18::Step,const eu4_spy18::Stamp* stamp) {
    auto& self=*static_cast<Controller*>(user);
    return stamp && self.status_.state==State::running && stage==self.active_request_.stage
        && self.barrier(point==eu4_spy18::GuardPoint::before_work) && stamp_equal(*stamp,self.locked_.stamp);
}
bool Controller::core_log(const eu4_spy18::Event* e) {
    if(!e||status_.state!=State::running||e->stage!=active_request_.stage)return fail(Failure::core_failed);
    const bool fault=e->kind==eu4_spy18::EventKind::fault;
    if(!fault && (!barrier(false)||!stamp_equal(e->stamp,locked_.stamp)))return fail(Failure::changed_world);
    if(fault)fail(Failure::core_failed); // Preserve diagnostic without any new engine reads.
    current_step_=e->step;current_family_=e->family;
    if(e->kind==eu4_spy18::EventKind::step_begin && e->step==eu4_spy18::Step::factory) { factory_return_verified_=false;original_id_=0;owned_base_=0;write_index_=0; }
    if(e->kind==eu4_spy18::EventKind::step_return && e->step==eu4_spy18::Step::factory) { factory_return_verified_=e->call_entered&&e->call_returned;original_id_=e->original_id; }
    if(e->kind==eu4_spy18::EventKind::step_begin && e->step==eu4_spy18::Step::initialize) { owned_base_=0;write_index_=0; }
    if(e->kind==eu4_spy18::EventKind::step_return && e->step==eu4_spy18::Step::initialize && write_index_!=10)return fail(Failure::owned_write_contract);
    Line line;line.add("{\"event\":\"core_event\",");line.envelope(env_.identity,locked_,ordinal_+1,status_.frames,clock_,env_.mock,env_.image_base);
    line.add(",\"sequence\":%u,\"expires\":%llu,\"allocation_link\":\"pinned_core_control_flow_only\",\"core\":{\"kind\":%u,\"stage\":%u,\"step\":%u,\"family\":%u,\"token\":%u,\"original_id\":%u,\"clone_id\":%u,\"command_id\":%u,\"call_entered\":%s,\"call_returned\":%s,\"allowed_observed\":%s,\"allowed\":%s,\"original_destroyed\":%s,\"clone_destroyed\":%s,\"command_destroyed\":%s,\"mock_resolver\":%s,\"send_supported\":%s,\"reason\":%u,\"exception_code\":%u,\"original_fields\":",
        active_request_.sequence,static_cast<unsigned long long>(active_request_.expires),static_cast<unsigned>(e->kind),static_cast<unsigned>(e->stage),static_cast<unsigned>(e->step),e->family,e->token,
        e->original_id,e->clone_id,e->command_id,tf(e->call_entered),tf(e->call_returned),tf(e->allowed_observed),tf(e->allowed),tf(e->original_destroyed),
        tf(e->clone_destroyed),tf(e->command_destroyed),tf(e->mock_resolver),tf(e->send_supported),static_cast<unsigned>(e->reason),e->exception_code);
    line.fields(e->original_fields);line.add(",\"clone_fields\":");line.fields(e->clone_fields);line.add(",\"stamp\":");line.stamp(e->stamp);line.add("},\"current_observation_verified\":%s}\n",tf(!fault));
    if(!line.valid)return fail(Failure::audit_failed);const bool written=append(line.bytes,static_cast<int>(line.used),fault);return written;
}
bool Controller::log_cb(void* user,const eu4_spy18::Event* event) { return static_cast<Controller*>(user)->core_log(event); }
} // namespace eu4_spy_host18
