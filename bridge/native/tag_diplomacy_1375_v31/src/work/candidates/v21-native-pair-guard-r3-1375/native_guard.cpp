#include "native_guard.h"
#include <algorithm>
#include <limits>
#include <cstring>

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
        if(action>=v21pair::ActionCount)return fail();
        if(request.actor.bytes==request.target.bytes)return fail();
        country1375::Tag tag{};
        if(!country1375::parse_tag(std::string_view(request.actor.bytes.data(),3),tag)||!country1375::parse_tag(std::string_view(request.target.bytes.data(),3),tag))return fail();
        // One bounded V31 batch may contain 128 separately revalidated commands.
        // The original absolute deadline remains checked before every operation.
        const auto now=clock();if(failed_||expires<=now||expires-now>1800000)return fail();
        request_=request;expires_=expires;
        if(!sample_pair(request,baseline_,roots_))return false;bound_=true;
        if(!requested_direction() || !bind_definition())return fail();
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

namespace {
bool name_at(NativePairGuardDraft& reader,std::uint64_t definition,const char* wanted) {
    std::uint64_t n=0,capacity=0,chars=definition+0x10;
    if(!reader.read(definition+0x20,&n,8)||!reader.read(definition+0x28,&capacity,8)
        ||n==0||n>128||n!=std::strlen(wanted)||n>capacity||capacity>1048576)return false;
    if(capacity>=16){if(!reader.read(definition+0x10,&chars,8)||chars<0x10000||chars>=0x800000000000ULL)return false;}
    else if(capacity!=15||n>=16)return false;
    char text[129]{};return reader.read(chars,text,static_cast<std::size_t>(n+1))&&!text[n]&&!std::memcmp(text,wanted,static_cast<std::size_t>(n));
}
}
bool NativePairGuardDraft::bind_definition() noexcept {
    try {
        const auto key=v21pair::script_key(request_.action);if(!*key)return true;
        if(!get(env_.image_base+0x242bba8,definition_registry_)||definition_registry_<0x10000
          ||!get(definition_registry_,definition_begin_)||!get(definition_registry_+8,definition_end_)
          ||!get(definition_registry_+16,definition_cap_)||definition_begin_<0x10000
          ||definition_end_<definition_begin_||definition_cap_<definition_end_||(definition_end_-definition_begin_)%8
          ||(definition_cap_-definition_begin_)%8||(definition_cap_-definition_begin_)/8>4096)return false;
        unsigned matches=0;
        for(auto slot=definition_begin_;slot<definition_end_;slot+=8) {
            std::uint64_t p=0,vt=0;std::uint32_t marker=0;
            if(!get(slot,p)||p<0x10000||!get(p,vt)||vt!=env_.image_base+0x1ce1f70||!get(p+8,marker)||marker!=0x165)return false;
            if(name_at(*this,p,key)){definition_=p;definition_slot_=slot;if(++matches!=1)return false;}
        }
        return matches==1&&definition_current();
    }catch(...){return false;}
}
bool NativePairGuardDraft::definition_current() noexcept {
    try {
        const auto key=v21pair::script_key(request_.action);if(!*key)return !definition_;
        std::uint64_t p=0,vt=0;std::uint32_t marker=0;
        return definition_&&get(env_.image_base+0x242bba8,p)&&p==definition_registry_
          &&get(definition_registry_,p)&&p==definition_begin_&&get(definition_registry_+8,p)&&p==definition_end_
          &&get(definition_registry_+16,p)&&p==definition_cap_&&get(definition_slot_,p)&&p==definition_
          &&get(p,vt)&&vt==env_.image_base+0x1ce1f70&&get(p+8,marker)&&marker==0x165&&name_at(*this,p,key);
    }catch(...){return false;}
}
bool NativePairGuardDraft::requested_direction() noexcept {
    using namespace v21pair;
    try {
        const auto action=request_.action;
        if(action==Action::N_join_coalition){std::int32_t active=0;return get(baseline_.target_object+0x1920,active)&&active>0;}
        if(action==Action::N_kick_from_trade_league || action==Action::N_leave_trade_league) {
            std::uint64_t league=0,other=0,begin=0,end=0,leader=0;
            if(!get(baseline_.actor_object+0x1948,league)||league<0x10000||!get(baseline_.target_object+0x1948,other)
              ||other!=league||!get(league+0x20,begin)||!get(league+0x28,end)||begin<0x10000||end<=begin||(end-begin)%8||(end-begin)/8>4096||!get(begin,leader))return false;
            return action==Action::N_kick_from_trade_league?leader==baseline_.actor.value:leader!=baseline_.actor.value;
        }
        if(action==Action::Independence || action==Action::N_ask_support_independence
          ||action==Action::N_cancel_offered_independence_support ||action==Action::N_cancel_requested_independence_support) {
            std::uint64_t overlord=0;bool dependent=false;
            if(!get(baseline_.actor_object+0x18f0,overlord))return false;
            if(valid(FullHandle{overlord})) {
                std::uint64_t records=0,root=0,array=0;std::int32_t count=0;
                const auto slot=(overlord>>32)&65535;
                if(slot>=baseline_.count||!get(baseline_.actor_object+0x1510,records)||records<0x10000
                 ||!get(records+slot*0x48,root)||root<0x10000||!get(root+0x128,array)||!get(root+0x134,count)
                 ||count<0||count>4096||(count&&array<0x10000))return false;
                for(std::int32_t i=0;i<count;++i) {
                    std::uint32_t id=0;std::uint64_t relation=0,definition=0,vt=0;std::uint8_t flag=0;
                    if(!get(array+std::uint64_t(i)*16,id))return false;
                    if(id!=slot)continue;
                    if(!get(array+std::uint64_t(i)*16+8,relation)||relation<0x10000||!get(relation,vt)||vt!=env_.image_base+0x1c81758
                      ||!get(relation+0x40,definition)||definition<0x10000||!get(definition+0x11a,flag))return false;
                    dependent=flag!=0;break;
                }
            }
            const bool requested=action==Action::N_ask_support_independence||action==Action::N_cancel_requested_independence_support;
            return requested==dependent;
        }
        return true;
    }catch(...){return false;}
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
        if(!cleanup&&v21pair::legacy_cancel(request_.action)) {
            if(request_.action==v21pair::Action::StopSpyNetwork) {
                if(!spy_bound_||!v21pair::recheck_spy(*this,env_.image_base,baseline_,spy_))return fail();
            } else if(!cancel_bound_||!cancel1375::recheck(*this,env_.image_base,v21pair::profile(request_.action).family,baseline_,cancel_))return fail();
        }
        if(!light() || !definition_current() || !requested_direction())return false;
        // All relation/identity/world callbacks are finished before this fresh
        // monotonic clock. Cleanup alone ignores the original lease expiry.
        const auto now=clock();return !failed_&&(cleanup||now<expires_)?true:fail();
    } catch(...) {return fail();}
}
bool NativePairGuardDraft::fresh_cb(void* p,v21port::Address base,std::uint32_t owner) {
    auto& self=*static_cast<NativePairGuardDraft*>(p);
    if(self.busy_||base!=self.env_.image_base||owner!=self.env_.owner_thread)return self.fail();
    Busy lock(self.busy_);return self.light()&&self.definition_current()&&self.requested_direction();
}
bool NativePairGuardDraft::final_cb(void* p,v21port::Call call) {
    return static_cast<NativePairGuardDraft*>(p)->final(call==v21port::Call::ActionDestructor||call==v21port::Call::CommandDestructor);
}
bool NativePairGuardDraft::write_cb(void* p) {return static_cast<NativePairGuardDraft*>(p)->final(false);}
v21port::Authority NativePairGuardDraft::authority() noexcept {return {this,fresh_cb,final_cb,write_cb};}
}
