#include "host.h"
#include <cstring>
#include <cstdarg>
namespace eu4_spy_send_host19 {
namespace {
volatile LONG real_instance=0;
constexpr std::uint64_t FRA=0x0100007a00415246ULL,ENG=0x0100002e00474e45ULL;
bool ptr(std::uintptr_t p) { return p>=0x10000&&p<0x800000000000ULL&&p%8==0; }
bool equal_stamp(const eu4_spy18::Stamp& a,const eu4_spy18::Stamp& b) {
    return a.game==b.game&&a.database==b.database&&a.countries==b.countries&&a.actor_country==b.actor_country
        &&a.target_country==b.target_country&&a.server==b.server&&a.pause_manager==b.pause_manager
        &&a.actor==b.actor&&a.target==b.target&&a.player==b.player&&a.date==b.date;
}
eu4_spy19::Identity identity(const Identity& x) {
    eu4_spy19::Identity out{};out.pid=x.pid;out.creation_filetime=x.creation;
    std::memcpy(out.session,x.session,33);std::memcpy(out.dll_sha256,x.dll_sha256,65);std::memcpy(out.manifest_sha256,x.manifest_sha256,65);return out;
}
bool identity_equal(const eu4_spy19::Identity& a,const Identity& b) {
    return a.pid==b.pid&&a.creation_filetime==b.creation&&!std::memcmp(a.session,b.session,33)
        &&!std::memcmp(a.dll_sha256,b.dll_sha256,65)&&!std::memcmp(a.manifest_sha256,b.manifest_sha256,65);
}
const char* tf(bool b) { return b?"true":"false"; }
struct Line {
    char text[8192]{};std::size_t used=0;bool valid=true;
    void add(const char* fmt,...) {
        if(!valid)return;va_list args;va_start(args,fmt);int n=vsnprintf(text+used,sizeof(text)-used,fmt,args);va_end(args);
        if(n<0||static_cast<std::size_t>(n)>=sizeof(text)-used) { valid=false;return; }used+=static_cast<std::size_t>(n);
    }
    void fields(const eu4_spy18::Fields& f) {
        add("{\"vtable\":%llu,\"marker\":%u,\"actor\":%llu,\"controller\":%llu,\"target\":%llu,\"primary_date\":%d,\"secondary_date\":%d,\"envoy\":%d,\"state\":%u,\"value\":%u,\"flag39\":%u,\"identifier\":%u}",
            static_cast<unsigned long long>(f.vtable),f.marker,static_cast<unsigned long long>(f.actor),static_cast<unsigned long long>(f.controller),
            static_cast<unsigned long long>(f.target),f.primary_date,f.secondary_date,f.envoy,f.state,static_cast<unsigned>(f.value),static_cast<unsigned>(f.flag39),f.identifier);
    }
    void stamp(const eu4_spy18::Stamp& s) {
        add("{\"game\":%llu,\"database\":%llu,\"countries\":%llu,\"actor_country\":%llu,\"target_country\":%llu,\"server\":%llu,\"pause_manager\":%llu,\"actor\":%llu,\"target\":%llu,\"player\":%llu,\"date\":%d}",
            static_cast<unsigned long long>(s.game),static_cast<unsigned long long>(s.database),static_cast<unsigned long long>(s.countries),
            static_cast<unsigned long long>(s.actor_country),static_cast<unsigned long long>(s.target_country),static_cast<unsigned long long>(s.server),
            static_cast<unsigned long long>(s.pause_manager),static_cast<unsigned long long>(s.actor),static_cast<unsigned long long>(s.target),static_cast<unsigned long long>(s.player),s.date);
    }
    void item(const eu4_spy19::Item& v) {
        add("{\"ordinal\":%u,\"family\":%u,\"token\":%u,\"original_id\":%u,\"clone_id\":%u,\"command_id\":%u,\"owner_frame\":%llu,\"step\":%u,\"outcome\":%u,",
            v.ordinal,v.family,v.token,v.original_id,v.clone_id,v.command_id,static_cast<unsigned long long>(v.owner_frame),static_cast<unsigned>(v.step),static_cast<unsigned>(v.outcome));
        add("\"claimed\":%s,\"call_entered\":%s,\"call_returned\":%s,\"preview_observed\":%s,\"preview_allowed\":%s,\"gate_observed\":%s,\"gate_allowed\":%s,",
            tf(v.claimed),tf(v.call_entered),tf(v.call_returned),tf(v.preview_observed),tf(v.preview_allowed),tf(v.gate_observed),tf(v.gate_allowed));
        add("\"original_destroyed\":%s,\"command_destroyed\":%s,\"clone_destroyed\":%s,\"submit_entered\":%s,\"submit_returned\":%s,\"submit_value_observed\":%s,\"submit_value\":%s,\"slot_observed\":%s,\"slot_consumed\":%s,",
            tf(v.original_destroyed),tf(v.command_destroyed),tf(v.clone_destroyed),tf(v.submit_entered),tf(v.submit_returned),tf(v.submit_value_observed),tf(v.submit_value),tf(v.slot_observed),tf(v.slot_consumed));
        add("\"has_local_original\":%s,\"has_local_command\":%s,\"has_local_clone\":%s,\"current\":%s,\"original_fields\":",tf(v.has_local_original),tf(v.has_local_command),tf(v.has_local_clone),tf(v.current));
        fields(v.original_fields);add(",\"clone_fields\":");fields(v.clone_fields);add("}");
    }
};
}
Controller::Controller() noexcept:started_(0),active_(0),frozen_(0),failure_(0),env_{},journal_{},preflight_{},core_{},proof_{},status_{},batch_{},wire_{},wire_size_(0),
    proof_valid_(false),audit_failed_(false),factory_verified_(false),clock_(0),ordinal_(0),bytes_(0),stage3_health_(0),lines_(0),read_calls_(0),write_index_(0),original_id_(0),current_item_(0),operation_(0),read_bytes_(0),owned_base_(0),step_(eu4_spy19::Step::none) {}
bool Controller::healthy() const { return InterlockedCompareExchange(const_cast<volatile LONG*>(&frozen_),0,0)==0; }
bool Controller::fail(Failure f) { InterlockedCompareExchange(&failure_,static_cast<LONG>(f),0);InterlockedExchange(&frozen_,1);return false; }
Status Controller::status() const noexcept { auto s=status_;if(frozen_)s.state=State::frozen;s.failure=static_cast<Failure>(failure_);return s; }
bool Controller::start(const Environment& env,const Journal& journal) {
    if(InterlockedCompareExchange(&started_,1,0))return fail(Failure::already_started);
    if(!env.mock&&InterlockedCompareExchange(&real_instance,1,0))return fail(Failure::already_started);
    if(!eu4_spy_host18::identity_valid(env.identity)||!ptr(env.image_base)||!env.owner_thread||!env.exact_disk_and_loaded_image_verified
        ||!env.read||!env.write||!env.resolve||!env.clock||!env.sample||!env.current_thread||!env.begin_frame||!journal.append||!journal.claim)return fail(Failure::bad_environment);
    env_=env;journal_=journal;Environment wrapped=env;
    wrapped.user=this;wrapped.read=read_cb;wrapped.write=write_cb;wrapped.resolve=resolve_cb;wrapped.clock=clock_cb;
    wrapped.sample=sample_cb;wrapped.current_thread=thread_cb;wrapped.begin_frame=begin_frame_cb;
    if(!preflight_.start(wrapped,{this,preflight_append_cb,preflight_claim_cb}))return fail(Failure::bad_environment);
    status_.state=State::preflight;status_.preflight_ready=true;return true;
}
bool Controller::append(const char* raw,std::size_t n,bool diagnostic) {
    if(audit_failed_||!raw||!n||n>8192||lines_>=512||bytes_>1048576-n||raw[n-1]!='\n')return fail(Failure::audit);
    if(!journal_.append(journal_.user,raw,n)) { audit_failed_=true;return fail(Failure::audit); }
    ++lines_;bytes_+=n;++ordinal_;return diagnostic||healthy();
}
bool Controller::barrier(bool ttl) {
    if(!healthy()||env_.current_thread(env_.user)!=env_.owner_thread)return fail(Failure::wrong_thread);
    const auto now=env_.clock(env_.user);if(!healthy()||now<clock_)return fail(Failure::clock);clock_=now;
    if(ttl&&now>=batch_.expires)return fail(Failure::expired);
    Frame a{},b{};if(!env_.sample(env_.user,&a)||!env_.sample(env_.user,&b)||!healthy()||!eu4_spy_host18::same_frame(a,b)
        ||!proof_valid_||!eu4_spy_host18::same_frame(a,proof_.world))return fail(Failure::world);
    return healthy();
}
bool Controller::record(const char* name,const eu4_spy19::Event* e,const eu4_spy19::Result* r) {
    Line line;line.add("{\"schema\":\"EU4SPYSENDHOST/1\",\"event\":\"%s\",\"ordinal\":%llu,\"owner_frame\":%llu,\"uptime_ms\":%llu,\"sequence\":4,\"pid\":%u,\"creation\":\"%016llx\",\"session\":\"%s\",\"game_sha256\":\"%s\",\"dll_sha256\":\"%s\",\"manifest_sha256\":\"%s\",\"owner_thread\":%u,\"mock_environment\":%s,\"image_base\":%llu,\"world\":",
        name,static_cast<unsigned long long>(ordinal_+1),static_cast<unsigned long long>(status_.owner_frames),static_cast<unsigned long long>(clock_),
        env_.identity.pid,static_cast<unsigned long long>(env_.identity.creation),env_.identity.session,eu4_spy_host18::kGameSha,
        env_.identity.dll_sha256,env_.identity.manifest_sha256,env_.owner_thread,tf(env_.mock),static_cast<unsigned long long>(env_.image_base));line.stamp(proof_.world.stamp);
    line.add(",\"proof_source\":\"same_controller_typed_run_result_and_later_health\",\"third_stage_health_frame\":%llu,\"host_state\":%u,\"host_failure\":%u,\"operation\":%u,\"expires\":%llu,",
        static_cast<unsigned long long>(stage3_health_),static_cast<unsigned>(status_.state),static_cast<unsigned>(failure_),operation_,static_cast<unsigned long long>(batch_.expires));
    line.add("\"runtime_verified\":false,\"effect_verified\":false,\"strict_sp_verified\":false,\"epoch_verified\":false,\"production_ready\":false");
    if(e) {
        line.add(",\"core\":{\"kind\":%u,\"operation\":%u,\"request_sequence\":%u,\"completed\":%u,\"exception_code\":%u,\"frame\":%llu,\"uptime_ms\":%llu,\"expires_uptime_ms\":%llu,\"reason\":%u,\"state\":%u,\"mock_resolver\":%s,\"stamp\":",
            static_cast<unsigned>(e->kind),static_cast<unsigned>(e->operation),e->request_sequence,e->completed,e->exception_code,static_cast<unsigned long long>(e->frame),
            static_cast<unsigned long long>(e->uptime_ms),static_cast<unsigned long long>(e->expires_uptime_ms),static_cast<unsigned>(e->reason),static_cast<unsigned>(e->state),tf(e->mock_resolver));line.stamp(e->stamp);
        line.add(",\"holder\":%llu,\"context\":%llu,\"transport\":%llu,\"actor_overlord\":%llu,\"target_overlord\":%llu,\"effective_player\":%llu,\"country_count\":%u,\"context_ready55\":%u,\"context_ready80d\":%u,\"native_speed_index\":%d,\"item\":",
            static_cast<unsigned long long>(e->stamp.holder),static_cast<unsigned long long>(e->stamp.context),static_cast<unsigned long long>(e->stamp.transport),
            static_cast<unsigned long long>(e->stamp.actor_overlord),static_cast<unsigned long long>(e->stamp.target_overlord),static_cast<unsigned long long>(e->stamp.effective_player),
            e->stamp.country_count,static_cast<unsigned>(e->stamp.context_ready55),static_cast<unsigned>(e->stamp.context_ready80d),e->stamp.native_speed_index);line.item(e->item);
        line.add(",\"identity\":{\"pid\":%u,\"creation_filetime\":%llu,\"session\":\"%s\",\"dll_sha256\":\"%s\",\"manifest_sha256\":\"%s\"},\"production_ready\":%s,\"strict_sp_verified\":%s,\"epoch_verified\":%s,\"effect_verified\":%s}",
            e->identity.pid,static_cast<unsigned long long>(e->identity.creation_filetime),e->identity.session,e->identity.dll_sha256,e->identity.manifest_sha256,
            tf(e->production_ready),tf(e->strict_sp_verified),tf(e->epoch_verified),tf(e->effect_verified));
    }
    if(r) {
        line.add(",\"result\":{\"state\":%u,\"reason\":%u,\"completed\":%u,\"exception_code\":%u,\"read_calls\":%u,\"bytes_read\":%llu,\"accepted_call\":%s,\"audit_complete\":%s,\"freeze_session\":%s,\"ownership_uncertain\":%s,\"current_item\":",
            static_cast<unsigned>(r->state),static_cast<unsigned>(r->reason),r->completed,r->exception_code,r->read_calls,static_cast<unsigned long long>(r->bytes_read),tf(r->accepted_call),tf(r->audit_complete),tf(r->freeze_session),tf(r->ownership_uncertain));line.item(r->current_item);
        line.add(",\"completed_outcomes\":[");for(unsigned i=0;i<5;++i)line.add("%s%u",i?",":"",static_cast<unsigned>(r->completed_outcomes[i]));
        line.add("],\"retry_allowed\":false,\"runtime_verified\":false,\"production_ready\":false,\"effect_verified\":false,\"strict_sp_verified\":false,\"epoch_verified\":false}");
    }
    line.add("}\n");if(!line.valid)return fail(Failure::audit);
    return append(line.text,line.used,e&&e->kind==eu4_spy19::Kind::fault);
}
bool Controller::call(eu4_spy19::Operation operation) {
    operation_=static_cast<std::uint32_t>(operation);
    eu4_spy19::Host h{sizeof(eu4_spy19::Host),1,env_.owner_thread,4,env_.image_base,identity(env_.identity),eu4_spy_host18::kGameSha,
        status_.owner_frames,batch_.expires,env_.exact_disk_and_loaded_image_verified,proof_valid_,true,env_.mock,
        read_cb,write_cb,resolve_cb,clock_cb,guard_cb,log_cb,claim_cb,this};
    status_.result=core_.invoke(operation,h);status_.completed_items=status_.result.completed;
    const auto& r=status_.result;
    if(!r.accepted_call||!r.audit_complete||r.freeze_session||r.ownership_uncertain||r.exception_code||r.reason!=eu4_spy19::Reason::none
        ||r.retry_allowed||r.runtime_verified||r.production_ready||r.effect_verified||r.strict_sp_verified||r.epoch_verified||!healthy()) {
        fail(Failure::core);if(!audit_failed_)record("terminal_result",nullptr,&r);return false;
    }
    if(!barrier(false)||!record("operation_result",nullptr,&r))return false;
    if(r.state==eu4_spy19::State::ready)status_.state=State::batch_ready;
    else if(r.state==eu4_spy19::State::awaiting_health)status_.state=State::awaiting_health;
    else if(r.state==eu4_spy19::State::complete)status_.state=State::complete;
    else return fail(Failure::core);
    return true;
}
bool Controller::execute(const char* packet,std::size_t size) {
    if(!started_||!healthy())return false;
    if(env_.current_thread(env_.user)!=env_.owner_thread)return fail(Failure::wrong_thread);
    if(status_.owner_frames>=4096)return fail(Failure::budget);++status_.owner_frames;read_calls_=0;read_bytes_=0;
    if((packet==nullptr)!=(size==0))return fail(Failure::packet);
    if(status_.state==State::preflight) {
        BatchRequest request{};
        if(packet&&parse(packet,size,request)) {
            if(!proof_valid_||!stage3_health_||stage3_health_>=status_.owner_frames||!eu4_spy_host18::same_identity(request.identity,env_.identity))return fail(Failure::order);
            PreflightProof current{};if(!preflight_.completed_preflight(current)||!eu4_spy_host18::same_identity(current.identity,proof_.identity)
                ||!eu4_spy_host18::same_frame(current.world,proof_.world))return fail(Failure::world);
            if(!env_.begin_frame(env_.user)||!barrier(false))return false;
            if(request.expires<=clock_||request.expires-clock_>60000)return fail(Failure::expired);
            batch_=request;std::memcpy(wire_,packet,size);wire_size_=size;status_.preflight_ready=false;
            return call(eu4_spy19::Operation::begin);
        }
        if(packet&&preflight_.status().state==eu4_spy_host18::State::awaiting_health)return fail(Failure::order);
        if(!preflight_.frame(packet,size)||!healthy())return fail(Failure::core);
        const auto s=preflight_.status();status_.preflight_stages=s.completed;status_.claimed_sequence=s.claimed;
        status_.preflight_ready=s.state==eu4_spy_host18::State::ready||s.state==eu4_spy_host18::State::complete;
        PreflightProof actual{};
        if(preflight_.completed_preflight(actual)) {
            if(!proof_valid_) { proof_=actual;proof_valid_=true;stage3_health_=status_.owner_frames;status_.authenticated_stages=3; }
            else if(!eu4_spy_host18::same_identity(actual.identity,proof_.identity)||!eu4_spy_host18::same_frame(actual.world,proof_.world))return fail(Failure::world);
        }
        return true;
    }
    if(packet)return fail(Failure::order);
    if(!env_.begin_frame(env_.user)||!barrier(false))return fail(Failure::world);
    if(status_.state==State::batch_ready)return call(eu4_spy19::Operation::next_item);
    if(status_.state==State::awaiting_health)return call(eu4_spy19::Operation::later_health);
    if(status_.state==State::complete)return record("final_health");
    return fail(Failure::order);
}
bool Controller::frame(const char* packet,std::size_t size) {
    if(InterlockedCompareExchange(&active_,1,0))return fail(Failure::reentry);
    bool ok=false;__try { ok=execute(packet,size); } __except(EXCEPTION_EXECUTE_HANDLER) { fail(Failure::core); }
    InterlockedExchange(&active_,0);return ok&&healthy();
}
bool Controller::send_log(const eu4_spy19::Event* e) {
    if(!e||e->request_sequence!=4||!identity_equal(e->identity,env_.identity)||e->frame!=status_.owner_frames||e->expires_uptime_ms!=batch_.expires
        ||e->mock_resolver!=env_.mock||e->production_ready||e->strict_sp_verified||e->epoch_verified||e->effect_verified)return fail(Failure::core);
    const bool fault=e->kind==eu4_spy19::Kind::fault;
    if(!fault&&(!barrier(false)||!equal_stamp(e->stamp,proof_.world.stamp)))return fail(Failure::world);
    if(fault)fail(Failure::core);
    step_=e->item.step;
    if(e->kind==eu4_spy19::Kind::step_intent&&step_==eu4_spy19::Step::factory) { factory_verified_=false;original_id_=0;owned_base_=0;write_index_=0; }
    if(e->kind==eu4_spy19::Kind::step_return&&step_==eu4_spy19::Step::factory) { factory_verified_=e->item.call_entered&&e->item.call_returned;original_id_=e->item.original_id; }
    if(e->kind==eu4_spy19::Kind::step_intent&&step_==eu4_spy19::Step::initialize) { owned_base_=0;write_index_=0; }
    if(e->kind==eu4_spy19::Kind::step_return&&step_==eu4_spy19::Step::initialize&&write_index_!=10)return fail(Failure::write_contract);
    return record("send_core",e);
}
bool Controller::send_claim(std::uint32_t sequence,std::uint32_t item,const eu4_spy19::Identity* id,const eu4_spy19::Stamp* s) {
    if(!id||!s||sequence!=4||!proof_valid_||!identity_equal(*id,env_.identity)||!equal_stamp(*s,proof_.world.stamp)||!barrier(true))return fail(Failure::claim);
    if(item==0) {
        if(status_.batch_claimed||status_.claimed_sequence!=3||!wire_size_)return fail(Failure::claim);
        if(!journal_.claim(journal_.user,4,0,wire_,wire_size_))return fail(Failure::claim);
        status_.batch_claimed=true;status_.claimed_sequence=4;
    } else {
        if(!status_.batch_claimed||item!=current_item_+1||item>5)return fail(Failure::claim);
        char text[1025]{};const int n=render_item(batch_,item,text,sizeof(text));
        if(n<1||static_cast<std::size_t>(n)>=sizeof(text)||!journal_.claim(journal_.user,4,item,text,static_cast<std::size_t>(n)))return fail(Failure::claim);
        current_item_=item;
    }
    // A flushed claim remains permanent even if its callback consumed the TTL.
    return healthy()&&barrier(true);
}
bool Controller::owned_write(std::uintptr_t p,const void* data,std::size_t n) {
    if(!healthy()||step_!=eu4_spy19::Step::initialize||!factory_verified_||!original_id_||write_index_>=10||!data||!barrier(true))return fail(Failure::write_contract);
    constexpr std::size_t offsets[]={0x10,0x18,0x20,0x28,0x2c,0x30,0x34,0x38,0x39,0x3c};
    constexpr std::size_t widths[]={8,8,8,4,4,4,4,1,1,4};
    const std::uint64_t values[]={FRA,FRA,ENG,static_cast<std::uint32_t>(proof_.world.stamp.date),static_cast<std::uint32_t>(proof_.world.stamp.date),0xffffffffU,0,1,0,0};
    if(n!=widths[write_index_]||std::memcmp(data,&values[write_index_],n))return fail(Failure::write_contract);
    if(write_index_==0) {
        if(p<0x10||!ptr(p-0x10))return fail(Failure::write_contract);owned_base_=p-0x10;const auto& s=proof_.world.stamp;
        if(owned_base_==s.game||owned_base_==s.database||owned_base_==s.countries||owned_base_==s.actor_country||owned_base_==s.target_country||owned_base_==s.server||owned_base_==s.pause_manager)return fail(Failure::write_contract);
    }
    if(p!=owned_base_+offsets[write_index_]||!env_.write(env_.user,p,data,n))return fail(Failure::write_contract);++write_index_;return healthy();
}
bool Controller::read_cb(void* p,std::uintptr_t a,void* b,std::size_t n) {
    auto& c=*static_cast<Controller*>(p);if(!c.healthy())return false;
    if(!n||n>64||c.read_calls_>=32768||c.read_bytes_>2097152-n)return c.fail(Failure::budget);
    ++c.read_calls_;c.read_bytes_+=n;return c.env_.read(c.env_.user,a,b,n)&&c.healthy();
}
bool Controller::write_cb(void* p,std::uintptr_t a,const void* b,std::size_t n) {
    auto& c=*static_cast<Controller*>(p);if(!c.healthy())return false;
    if(c.status_.state==State::preflight&&!c.status_.batch_claimed)return c.env_.write(c.env_.user,a,b,n)&&c.healthy();
    return c.owned_write(a,b,n);
}
std::uintptr_t Controller::resolve_cb(void* p,std::uintptr_t rva) {
    auto& c=*static_cast<Controller*>(p);if(!c.healthy())return 0;
    const std::uintptr_t fixed[]={0x35d210,0x129450,0x4e7470,0x4e9930,0x4e8630,0x582b20,0x57eca0,0x5853a0,0x580650,0x581840,0x582730,0x57e900,0x585020,0x580260,0x581450};
    bool allowed=rva==0x14ca210&&c.status_.batch_claimed;
    for(auto n:fixed)if(n==rva)allowed=true;
    if(!allowed) { c.fail(Failure::bad_environment);return 0; }
    const auto result=c.env_.resolve(c.env_.user,rva);return c.healthy()?result:0;
}
std::uint64_t Controller::clock_cb(void* p) { auto& c=*static_cast<Controller*>(p);return c.env_.clock(c.env_.user); }
bool Controller::sample_cb(void* p,Frame* f) { auto& c=*static_cast<Controller*>(p);return c.healthy()&&c.env_.sample(c.env_.user,f)&&c.healthy(); }
std::uint32_t Controller::thread_cb(void* p) { auto& c=*static_cast<Controller*>(p);return c.healthy()?c.env_.current_thread(c.env_.user):0; }
bool Controller::begin_frame_cb(void* p) { auto& c=*static_cast<Controller*>(p);return c.healthy()&&c.env_.begin_frame(c.env_.user)&&c.healthy(); }
bool Controller::preflight_append_cb(void* p,const char* s,std::size_t n) { return static_cast<Controller*>(p)->append(s,n); }
bool Controller::preflight_claim_cb(void* p,std::uint32_t seq,const char* s,std::size_t n) {
    auto& c=*static_cast<Controller*>(p);return c.healthy()&&seq>=1&&seq<=3&&c.journal_.claim(c.journal_.user,seq,0,s,n)&&c.healthy();
}
bool Controller::guard_cb(void* p,eu4_spy19::Point point,eu4_spy19::Step,const eu4_spy19::Identity* id,const eu4_spy19::Stamp* s) {
    auto& c=*static_cast<Controller*>(p);return id&&s&&identity_equal(*id,c.env_.identity)&&c.proof_valid_
        &&equal_stamp(*s,c.proof_.world.stamp)&&c.barrier(point==eu4_spy19::Point::before_work);
}
bool Controller::log_cb(void* p,const eu4_spy19::Event* e) { return static_cast<Controller*>(p)->send_log(e); }
bool Controller::claim_cb(void* p,std::uint32_t q,std::uint32_t i,const eu4_spy19::Identity* id,const eu4_spy19::Stamp* s) { return static_cast<Controller*>(p)->send_claim(q,i,id,s); }
} // namespace
