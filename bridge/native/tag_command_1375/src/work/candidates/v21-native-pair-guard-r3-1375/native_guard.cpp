#include "native_guard.h"
#include <algorithm>
#include <limits>

namespace v21guard {
namespace {
bool request_equal(const v21pair::Request& a,const v21pair::Request& b) {
    return a.action==b.action&&a.actor.bytes==b.actor.bytes&&a.target.bytes==b.target.bytes;
}
// Private observation labels only; full Identity remains held by the Host.
// These fingerprints are not cryptographic capabilities or world epochs.
std::uint64_t label(const char* text,std::size_t n) {
    std::uint64_t v=14695981039346656037ULL;
    for(std::size_t i=0;i<n;++i)v=(v^static_cast<unsigned char>(text[i]))*1099511628211ULL;
    return v?v:1;
}
bool frame_equal(const eu4_spy_host18::Frame& a,const eu4_spy_host18::Frame& b) {
    const auto& x=a.stamp;const auto& y=b.stamp;
    return x.game==y.game&&x.database==y.database&&x.countries==y.countries&&x.actor_country==y.actor_country&&x.target_country==y.target_country&&
        x.server==y.server&&x.pause_manager==y.pause_manager&&x.actor==y.actor&&x.target==y.target&&x.player==y.player&&x.date==y.date&&
        a.countries_count==b.countries_count&&a.thread==b.thread&&a.actor_overlord==b.actor_overlord&&a.target_overlord==b.target_overlord&&
        a.effective_player==b.effective_player&&a.manual_pause==b.manual_pause&&a.reset==b.reset&&a.ironman==b.ironman&&
        a.selector==b.selector&&a.alternate_selector==b.alternate_selector&&a.native_speed_index==b.native_speed_index&&
        a.multiplayer_classifier==b.multiplayer_classifier&&a.load_source==b.load_source;
}
struct Busy {
    bool& value;
    explicit Busy(bool& v):value(v){value=true;}
    ~Busy(){value=false;}
};
}
NativePairGuardDraft::NativePairGuardDraft(const eu4_spy_host18::Environment& e) noexcept:env_(e){}
bool NativePairGuardDraft::environment() noexcept {
    try {
        return !failed_&&env_.user&&env_.image_base>=0x10000&&env_.image_base%65536==0&&env_.owner_thread&&
            !env_.mock&&env_.exact_disk_and_loaded_image_verified&&eu4_spy_host18::identity_valid(env_.identity)&&
            env_.read&&env_.clock&&env_.sample&&env_.current_thread&&env_.begin_frame&&env_.current_thread(env_.user)==env_.owner_thread;
    } catch(...) {return fail();}
}
bool NativePairGuardDraft::begin_frame() noexcept {
    try {if(busy_||!environment()||!env_.begin_frame(env_.user))return fail();++frames_;return true;}
    catch(...) {return fail();}
}
std::uint64_t NativePairGuardDraft::clock() {
    if(!environment()) {fail();return std::numeric_limits<std::uint64_t>::max();}
    const auto now=env_.clock(env_.user);
    if(got_clock_&&now<last_clock_) {fail();return std::numeric_limits<std::uint64_t>::max();}
    got_clock_=true;last_clock_=now;return now;
}
bool NativePairGuardDraft::read(std::uint64_t address,void* data,std::size_t size) {
    if(!environment()||!frames_||!data||!size||size>32768||address<0x10000||address>=0x800000000000ULL||size>0x800000000000ULL-address)return fail();
    auto* target=static_cast<std::uint8_t*>(data);
    // NativeEnvironment already supplies bounded region checks and SEH. Its
    // fixed 64B reader is adapted to the resolver's 32KiB logical read limit.
    for(std::size_t i=0;i<size;) {
        const auto n=std::min<std::size_t>(size-i,64);
        if(!env_.read(env_.user,static_cast<std::uintptr_t>(address+i),target+i,n))return fail();i+=n;
    }
    return true;
}
bool NativePairGuardDraft::health(eu4_spy_host18::Frame& out) noexcept {
    try {
        if(!environment()||!frames_||!env_.sample(env_.user,&out))return fail();
        if(out.thread!=env_.owner_thread||out.manual_pause!=1||out.reset!=0||out.load_source!=0||out.ironman!=0||out.selector!=0||out.multiplayer_classifier||
            out.countries_count==0||out.countries_count>4096||out.stamp.date<=0||out.effective_player!=out.stamp.player)return fail();
        return true;
    } catch(...) {return fail();}
}
bool NativePairGuardDraft::sample_pair(const v21pair::Request& request,v21pair::PairStamp& out,country1375::Roots& roots) noexcept {
    try {
        eu4_spy_host18::Frame before{},after{};if(!health(before))return false;
        const std::vector<std::string_view> tags{std::string_view(request.actor.bytes.data(),3),std::string_view(request.target.bytes.data(),3)};
        const auto result=country1375::resolve(*this,env_.image_base,tags);
        if(result.status!=country1375::Status::Resolved||result.bindings.size()!=2||!health(after)||!frame_equal(before,after))return fail();
        const auto& z=result.snapshot.roots;
        if(z.game!=before.stamp.game||z.database!=before.stamp.database||z.array!=before.stamp.countries||z.count!=before.countries_count||
            z.date!=static_cast<std::uint32_t>(before.stamp.date)||z.current!=before.stamp.player)return fail();
        v21pair::PairStamp s{};s.process_creation=env_.identity.creation;s.session=label(env_.identity.session,32);s.module_pin=label(env_.identity.manifest_sha256,64);
        s.database=z.database;s.game=z.game;s.array=z.array;s.count=z.count;s.date=z.date;s.reset=z.reset;
        s.actor_object=result.bindings[0].address;s.target_object=result.bindings[1].address;s.actor.value=result.bindings[0].handle;s.target.value=result.bindings[1].handle;
        s.current_player.value=z.current;s.effective_player.value=z.current;s.owner_thread=env_.owner_thread;s.world_witness=1;
        if(!v21pair::valid(s)||(bound_&&(!frame_equal(before,world_)||!(s==baseline_)||!(z==roots_))))return fail();
        if(!bound_)world_=before;out=s;roots=z;return true;
    } catch(...) {return fail();}
}
bool NativePairGuardDraft::lease(const v21pair::Request& request,std::uint64_t expires) noexcept {
    if(attempted_||busy_)return fail();attempted_=true;
    try {
        Busy lock(busy_);const auto action=static_cast<unsigned>(request.action);
        if(action>=21)return fail();
        if(request.actor.bytes==request.target.bytes)return fail();
        country1375::Tag tag{};
        if(!country1375::parse_tag(std::string_view(request.actor.bytes.data(),3),tag)||!country1375::parse_tag(std::string_view(request.target.bytes.data(),3),tag))return fail();
        const auto now=clock();if(failed_||expires<=now||expires-now>60000)return fail();
        request_=request;expires_=expires;
        if(!sample_pair(request,baseline_,roots_))return false;bound_=true;
        if(request.action==v21pair::Action::StopSpyNetwork) {
            if(!v21pair::bind_spy_two_pass(*this,env_.image_base,baseline_,spy_))return fail();
            spy_bound_=true;
        }
        const auto final_time=clock();if(failed_||final_time>=expires_)return fail();return true;
    } catch(...) {return fail();}
}
bool NativePairGuardDraft::stamp(const v21pair::Request& request,v21pair::PairStamp& out) {
    if(!bound_||busy_||!request_equal(request,request_))return fail();
    Busy lock(busy_);country1375::Roots roots{};return sample_pair(request,out,roots);
}
bool NativePairGuardDraft::cancellation(v21pair::Family family,const v21pair::PairStamp& s,v21pair::CancelObservation& out) {
    if(!bound_||busy_||!(s==baseline_)||family!=v21pair::profile(request_.action).family||v21pair::positive(request_.action))return fail();
    Busy lock(busy_);cancel1375::Snapshot observed{};
    if(!cancel1375::two_pass(*this,env_.image_base,family,s,observed)||(cancel_bound_&&!(observed==cancel_)))return fail();
    if(!cancel_bound_) {cancel_=observed;cancel_bound_=true;}out=observed.selected;return true;
}
bool NativePairGuardDraft::light() noexcept {
    try {
        if(!bound_||!environment())return fail();eu4_spy_host18::Frame before{},after{};
        if(!health(before)||!frame_equal(before,world_))return fail();
        std::uint64_t database{},game{},array{},current{};std::int32_t cap{},count{},date{};std::uint8_t reset{},selector{};
        if(!get(env_.image_base+0x233d8d0,database)||database!=roots_.database||!get(env_.image_base+0x233fe78,game)||game!=roots_.game||
            !get(database+0x118,array)||array!=roots_.array||!get(database+0x120,cap)||cap<=0||static_cast<std::uint32_t>(cap)!=roots_.capacity||
            !get(database+0x124,count)||count<=0||static_cast<std::uint32_t>(count)!=roots_.count)return fail();
        for(const auto& pair:std::array<std::pair<std::uint64_t,v21pair::FullHandle>,2>{{{baseline_.actor_object,baseline_.actor},{baseline_.target_object,baseline_.target}}}) {
            std::uint64_t object{},vt{},handle{};std::uint32_t marker{};
            if(!get(array+((pair.second.value>>32)&65535)*8,object)||object!=pair.first||!get(object,vt)||vt!=env_.image_base+0x1c574a0||
                !get(object+8,marker)||marker!=0x165||!get(object+0x20,handle)||handle!=pair.second.value)return fail();
        }
        if(!get(game+0x1dd0,date)||date<=0||static_cast<std::uint32_t>(date)!=roots_.date||!get(game+0x1e60,current)||current!=roots_.current||
            !get(game+0x1e66,selector)||selector!=0||!get(game+0x7485,reset)||reset!=0||!health(after)||!frame_equal(after,world_))return fail();
        return true;
    } catch(...) {return fail();}
}
bool NativePairGuardDraft::final(bool cleanup) noexcept {
    try {
        if(busy_||!bound_||!environment())return fail();Busy lock(busy_);
        if(!cleanup&&!v21pair::positive(request_.action)) {
            if(request_.action==v21pair::Action::StopSpyNetwork) {
                if(!spy_bound_||!v21pair::recheck_spy(*this,env_.image_base,baseline_,spy_))return fail();
            } else if(!cancel_bound_||!cancel1375::recheck(*this,env_.image_base,v21pair::profile(request_.action).family,baseline_,cancel_))return fail();
        }
        if(!light())return false;
        // All relation/identity/world callbacks are finished before this fresh
        // monotonic clock. Cleanup alone ignores the original lease expiry.
        const auto now=clock();return !failed_&&(cleanup||now<expires_)?true:fail();
    } catch(...) {return fail();}
}
bool NativePairGuardDraft::fresh_cb(void* p,v21port::Address base,std::uint32_t owner) {
    auto& self=*static_cast<NativePairGuardDraft*>(p);
    if(self.busy_||base!=self.env_.image_base||owner!=self.env_.owner_thread)return self.fail();
    Busy lock(self.busy_);return self.light();
}
bool NativePairGuardDraft::final_cb(void* p,v21port::Call call) {
    return static_cast<NativePairGuardDraft*>(p)->final(call==v21port::Call::ActionDestructor||call==v21port::Call::CommandDestructor);
}
bool NativePairGuardDraft::write_cb(void* p) {return static_cast<NativePairGuardDraft*>(p)->final(false);}
v21port::Authority NativePairGuardDraft::authority() noexcept {return {this,fresh_cb,final_cb,write_cb};}
}
