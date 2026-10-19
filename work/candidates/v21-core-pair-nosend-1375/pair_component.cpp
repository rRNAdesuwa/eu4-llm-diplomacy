#include "pair_component.h"
#include <limits>
#include <stdexcept>

namespace v21pair {
namespace {
constexpr std::array<Profile, 6> registry{{
    {Family::Vassal,0x2940,0x40,0x1c7fd20,0x51fa00,0x129450,0x4e99d0,0x51f020,0x51f4a0,FullCallerEvidence::StaticSlotOnly},
    {Family::Marriage,0x28df,0x68,0x1c80ab0,0x4f07d0,0x4ed5b0,0x4e99d0,0x4ef3b0,0x4ef7b0,FullCallerEvidence::StaticSlotOnly},
    {Family::Improve,0x2ddb,0x40,0x1c7dd68,0x574b20,0x129450,0x4e99d0,0x574460,0x5746d0,FullCallerEvidence::StaticSlotOnly},
    {Family::Guarantee,0x2941,0x40,0x1c7fe50,0x5224c0,0x129450,0x4e99d0,0x521ad0,0x521f00,FullCallerEvidence::StaticSlotOnly},
    {Family::SpyNetwork,0x3378,0x40,0x1c7cc48,0x586200,0x129450,0x586330,0x5856a0,0x5858e0,FullCallerEvidence::StaticSlotOnly},
    {Family::Curry,0x3acc,0x40,0x1c7aef8,0x5ae2b0,0x129450,0x4e99d0,0x5ade60,0x5ae110,FullCallerEvidence::SealedNormalCaller}
}};
constexpr std::array<std::string_view, 12> names{{"offer_vassalization","cancel_vassalization","royal_marriage","break_marriage",
    "improve_relations","stop_improving_relations","guarantee","revoke_guarantee","build_spy_network","stop_building_spy_network","curry_favors","stop_currying_favors"}};
bool tag(std::string_view input, Tag& out) noexcept {
    if (input.size()!=3) return false;
    for (std::size_t i=0;i<3;++i) {
        char c=input[i]; if (!((c>='A' && c<='Z') || (c>='0' && c<='9'))) return false;
        out.bytes[i]=c;
    }
    return true;
}
bool action_type(const Profile& p, const ActionView& v) noexcept {
    return v.size==p.size && v.vtable==p.vtable && v.marker==0x165;
}
bool string_fields(const Profile& p, const ActionView& v, bool empty) noexcept {
    if (p.family!=Family::Marriage) return true;
    const auto& t=v.text;
    if (t.force!=0 || !t.storage_valid || t.length>128 || t.length>t.capacity || t.terminator!=0) return false;
    // Inline storage has room for its terminator; heap storage is read by adapter, never freed here.
    if (t.capacity<16 && t.length>=16) return false;
    return !empty || (t.length==0 && t.capacity==15 && t.first==0);
}
bool defaults(const Profile& p, const ActionView& v) noexcept {
    return action_type(p,v) && v.actor.value==0x2d2d2d && v.controller==v.actor && v.target==v.actor
        && v.primary==0x29c77f8 && v.secondary==v.primary && v.envoy==-1 && v.state==0
        && v.value==1 && v.flag==0 && v.id==0 && string_fields(p,v,true);
}
bool initialized(const Profile& p, const ActionView& v, const PairStamp& s, bool mode, std::int32_t envoy, bool empty) noexcept {
    return action_type(p,v) && v.actor==s.actor && v.controller==s.actor && v.target==s.target
        && v.primary==s.date && v.secondary==s.date && v.envoy==envoy && v.state==0
        && v.value==(mode?1:0) && v.flag==0 && v.id==0 && string_fields(p,v,empty);
}
bool command_fields(const CommandView& c) noexcept {
    return c.size==0x58 && c.vtable==0x1c814b0 && c.marker==0x165 && c.token==0x2934
        && c.field10==0 && c.field18==0 && c.field28==0 && c.field30==15 && c.field38==-1
        && c.field3c==0 && c.field40==0 && c.field48==0xffff && c.clone.value!=0;
}
bool pointer(std::uint64_t p) noexcept { return p>=0x10000 && p<0x0000800000000000ULL && (p&7)==0; }
bool add(std::uint64_t a, std::uint64_t b, std::uint64_t& out) noexcept {
    if (a>std::numeric_limits<std::uint64_t>::max()-b) return false;
    out=a+b; return true;
}
template<class T> bool at(SyntheticReadPort& r, std::uint64_t a, std::uint64_t off, T& out) {
    std::uint64_t location=0; if (!pointer(a) || !add(a,off,location) || location>std::numeric_limits<std::uint64_t>::max()-sizeof(T)) return false;
    return r.read(location,&out,sizeof(T));
}
bool vt(SyntheticReadPort& r, std::uint64_t object, std::uint64_t module, std::uint64_t rva) {
    std::uint64_t actual=0,wanted=0; return add(module,rva,wanted) && at(r,object,0,actual) && actual==wanted;
}
std::uint64_t country_slot(FullHandle h) noexcept {return (h.value>>32)&0xffff;}
bool handle_tag(FullHandle h, const Tag& t) noexcept {
    for (unsigned i=0;i<3;++i) if (((h.value>>(8*i))&0xff)!=static_cast<unsigned char>(t.bytes[i])) return false;
    return ((h.value>>24)&0xff)==0;
}
bool raw_roots(SyntheticReadPort& r, std::uint64_t module, const PairStamp& s) {
    std::uint64_t db=0,game=0,array=0,a=0,b=0,ah=0,bh=0,player=0;
    std::uint32_t count=0,date=0;std::uint8_t reset=0;
    return at(r,module,0x233d8d0,db) && db==s.database && at(r,module,0x233fe78,game) && game==s.game
        && at(r,db,0x118,array) && array==s.array && at(r,db,0x124,count) && count==s.count
        && at(r,array,country_slot(s.actor)*8,a) && a==s.actor_object && at(r,array,country_slot(s.target)*8,b) && b==s.target_object
        && at(r,a,0x20,ah) && ah==s.actor.value && at(r,b,0x20,bh) && bh==s.target.value
        && at(r,game,0x1dd0,date) && date==s.date && at(r,game,0x1e60,player) && player==s.current_player.value
        && at(r,game,0x7485,reset) && reset==0;
}
class RecordingPort final : public SyntheticReadPort {
    SyntheticReadPort& source;std::vector<ReadWord>& words;
public:
    RecordingPort(SyntheticReadPort& r,std::vector<ReadWord>& w):source(r),words(w) {}
    bool read(std::uint64_t address,void* output,std::size_t size) override {
        if (words.size()>=8192 || size>8) return false;
        ReadWord w{};w.address=address;w.size=size;
        if (!source.read(address,w.bytes.data(),size)) return false;
        auto* to=static_cast<std::uint8_t*>(output);for(std::size_t i=0;i<size;++i)to[i]=w.bytes[i];
        words.push_back(w);return true;
    }
};
}
const std::array<Profile, 6>& profiles() noexcept { return registry; }
const Profile& profile(Action action) {
    const auto i=static_cast<std::size_t>(action); if (i>=12) throw std::out_of_range("action");
    return registry[i/2];
}
bool positive(Action action) noexcept { return (static_cast<unsigned>(action)&1)==0; }
bool parse_action(std::string_view text, Action& result) noexcept {
    for (std::size_t i=0;i<names.size();++i) if (names[i]==text) {result=static_cast<Action>(i);return true;}
    return false;
}
bool make_request(std::string_view name, std::string_view a, std::string_view b, Request& out) noexcept {
    Request draft{}; if (!parse_action(name,draft.action) || !tag(a,draft.actor) || !tag(b,draft.target) || draft.actor.bytes==draft.target.bytes) return false;
    out=draft; return true;
}
bool operator==(FullHandle a, FullHandle b) noexcept { return a.value==b.value; }
bool operator==(OwnedId a, OwnedId b) noexcept { return a.value==b.value; }
bool valid(FullHandle h) noexcept { return h.value!=0 && h.value!=0x2d2d2d && (h.value>>56)!=0 && country_slot(h)<4096; }
bool PairStamp::operator==(const PairStamp& b) const noexcept {
    return process_creation==b.process_creation && session==b.session && module_pin==b.module_pin
        && database==b.database && game==b.game && array==b.array && actor_object==b.actor_object
        && target_object==b.target_object && owner_thread==b.owner_thread && world_witness==b.world_witness
        && count==b.count && date==b.date && reset==b.reset && actor==b.actor && target==b.target
        && current_player==b.current_player && effective_player==b.effective_player;
}
bool valid(const PairStamp& s) noexcept {
    return s.process_creation && s.session && s.module_pin && s.owner_thread && s.world_witness && s.date
        && pointer(s.database) && pointer(s.game) && pointer(s.array) && pointer(s.actor_object) && pointer(s.target_object)
        && s.actor_object!=s.target_object && s.count>0 && s.count<=4096 && s.reset==0
        && valid(s.actor) && valid(s.target) && !(s.actor==s.target)
        && country_slot(s.actor)<s.count && country_slot(s.target)<s.count
        && s.current_player==s.actor && s.effective_player==s.actor;
}
bool CancelObservation::operator==(const CancelObservation& b) const noexcept {
    return family==b.family && active==b.active && known_type==b.known_type && outgoing==b.outgoing
        && reciprocal==b.reciprocal && mission_linked==b.mission_linked && actor==b.actor && target==b.target
        && actor_overlord==b.actor_overlord && target_overlord==b.target_overlord && dependency==b.dependency
        && object==b.object && mission==b.mission && revision==b.revision;
}
bool cancel_matches(const Profile& p, const PairStamp& s, const CancelObservation& o) noexcept {
    if (o.family!=p.family || !o.active || !o.known_type || !o.outgoing || !o.object
        || !(o.actor==s.actor) || !(o.target==s.target)) return false;
    switch (p.family) {
    case Family::Vassal: return o.reciprocal && o.target_overlord==s.actor && !(o.actor_overlord==s.target)
        && (o.dependency==Dependency::Vassal || o.dependency==Dependency::ClientVassal);
    case Family::Marriage: case Family::Guarantee: return o.reciprocal;
    case Family::Improve: case Family::Curry: return o.mission_linked && o.mission!=0;
    case Family::SpyNetwork: return false; // exclusively private raw graph binder
    }
    return false;
}
bool SpyBinding::operator==(const SpyBinding& b) const noexcept {
    return envoy==b.envoy && record==b.record && root==b.root && holder==b.holder && manager==b.manager
        && begin==b.begin && end==b.end && entry==b.entry && mission==b.mission && task==b.task
        && target_owner==b.target_owner && head==b.head && tail==b.tail && count==b.count && observations==b.observations;
}
bool bind_spy_once(SyntheticReadPort& source, std::uint64_t module, const PairStamp& s, SpyBinding& output) {
    if (!valid(s) || !pointer(module)) return false;
    SpyBinding b{};RecordingPort r(source,b.observations);
    if (!raw_roots(r,module,s)) return false;
    std::uint64_t records=0; std::uint8_t flag=0; FullHandle rh{},ra{};
    const auto slot=country_slot(s.target);
    if (!at(r,s.actor_object,0x1510,records) || !pointer(records) || !add(records,slot*0x48,b.record)
        || !at(r,b.record,0,b.root) || !pointer(b.root) || !at(r,b.record,8,ra.value) || !(ra==s.actor)
        || !at(r,b.record,0x10,rh.value) || !(rh==s.target)
        || !at(r,b.record,0x46,flag) || (flag&8)==0
        || !at(r,s.actor_object,0x1480,b.holder) || !pointer(b.holder)
        || !at(r,b.holder,0x18,b.manager) || !pointer(b.manager)
        || !at(r,b.manager,0x20,b.begin) || !at(r,b.manager,0x28,b.end)
        || !pointer(b.begin) || b.end<b.begin || (b.end-b.begin)%8!=0 || (b.end-b.begin)/8>256) return false;
    unsigned matches=0;
    for (auto a=b.begin;a<b.end;a+=8) {
        std::uint64_t entry=0,mission=0,task=0; std::uint8_t status=0,removed=0; FullHandle actor{},target{},ma{},mt{};
        std::int32_t envoy=0,me=0,te=0; std::uint64_t back=0; std::uint32_t token=0;
        if (!at(r,a,0,entry) || !pointer(entry) || !at(r,entry,0x18,status)) return false;
        if (status!=2) continue;
        if (!at(r,entry,0x10,mission) || !vt(r,mission,module,0x1c4b2b8) || !at(r,mission,0xa0,task)) return false;
        if (task==0) continue;
        std::uint64_t task_type=0; if (!at(r,task,0,task_type)) return false;
        std::uint64_t expected=0; if (!add(module,0x1ce3ba0,expected)) return false;
        if (task_type!=expected) continue; // no derived reads for another task type
        if (!at(r,task,0x20,target.value)) return false;
        if (country_slot(target)!=slot) continue;
        if (!(target==s.target) || !at(r,entry,0x44,envoy) || envoy<0
            || !at(r,task,0x28,removed) || removed!=0 || !at(r,task,0x18,actor.value) || !(actor==s.actor)
            || !at(r,mission,0x80,ma.value) || !(ma==s.actor) || !at(r,mission,0x88,mt.value) || !(mt==s.target)
            || !at(r,mission,0xa8,token) || token!=0x3378 || !at(r,mission,0x48,back) || back!=entry
            || !at(r,mission,0x50,me) || me!=envoy || !at(r,task,0x2c,te) || te!=envoy || ++matches!=1) return false;
        b.entry=entry;b.mission=mission;b.task=task;b.envoy=envoy;
    }
    if (matches!=1 || !at(r,s.target_object,0x14b0,b.target_owner) || !pointer(b.target_owner)
        || !at(r,b.target_owner,0x4f0,b.head) || !at(r,b.target_owner,0x4f8,b.tail)
        || !at(r,b.target_owner,0x500,b.count) || b.count==0 || b.count>1024 || !pointer(b.head) || !pointer(b.tail)) return false;
    auto node=b.head; std::uint64_t previous=0; unsigned selected=0;
    for (std::uint32_t i=0;i<b.count;++i) {
        std::uint64_t prior=0,next=0; std::uint8_t removed=0;
        if (!pointer(node) || !at(r,node,8,prior) || prior!=previous || !at(r,node,0x18,removed) || removed>1) return false;
        if (removed==0) { // removed nodes: do not follow stale node+0 task pointer
            std::uint64_t task=0,type=0,expected=0;
            if (!at(r,node,0,task) || !at(r,task,0,type) || !add(module,0x1ce3ba0,expected)) return false;
            if (type==expected) {
                std::uint8_t gone=0; std::uint64_t owner=0; FullHandle actor{},target{}; std::int32_t envoy=0;
                if (!at(r,task,0x28,gone) || gone!=0 || !at(r,task,0x10,owner) || owner!=b.target_owner
                    || !at(r,task,0x20,target.value) || !(target==s.target) || !at(r,task,0x18,actor.value)) return false;
                if (actor==s.actor && (task!=b.task || !at(r,task,0x2c,envoy) || envoy!=b.envoy || ++selected!=1)) return false;
            }
        }
        if (!at(r,node,0x10,next)) return false;
        previous=node; node=next;
    }
    if (node!=0 || previous!=b.tail || selected!=1 || !raw_roots(r,module,s)) return false;
    output=b;return true;
}
bool bind_spy_two_pass(SyntheticReadPort& r, std::uint64_t m, const PairStamp& s, SpyBinding& out) {
    SpyBinding a{},b{}; if (!bind_spy_once(r,m,s,a) || !bind_spy_once(r,m,s,b) || !(a==b)) return false;
    out=b;return true;
}
bool recheck_spy(SyntheticReadPort& r, std::uint64_t m, const PairStamp& s, const SpyBinding& old) {
    SpyBinding current{};return bind_spy_once(r,m,s,current) && current==old;
}

Result preflight_no_send(const Request& request, SyntheticGuard& guard, SyntheticEngine& e,
    std::uint64_t expires, SyntheticReadPort* spy_reader, std::uint64_t module) noexcept {
    Result result{}; OwnedId original{},command{},clone{}; PairStamp baseline{};
    std::uint64_t last_clock=0; bool got_clock=false; CancelObservation cancellation{}; SpyBinding spy{};
    auto freeze=[&](const char* why) {result.status=Status::Frozen;result.reason=why;result.quarantined_original=original;
        result.quarantined_command=command;result.quarantined_clone=clone;return result;};
    try {
        if (static_cast<unsigned>(request.action)>=12) return result;
        const Profile& p=profile(request.action);const bool mode=positive(request.action);
        // Recheck TAG shape even for a directly constructed C++ Request.
        Tag a{},b{};if (!tag(std::string_view(request.actor.bytes.data(),3),a) || !tag(std::string_view(request.target.bytes.data(),3),b) || a.bytes==b.bytes) return result;
        auto barrier=[&](bool cleanup) {
            auto now=guard.clock(); if ((got_clock && now<last_clock) || (!cleanup && now>=expires)) return false;
            got_clock=true;last_clock=now;
            PairStamp x{},y{};return guard.stamp(request,x) && valid(x) && guard.stamp(request,y) && x==y && x==baseline;
        };
        if (!guard.stamp(request,baseline) || !valid(baseline) || !handle_tag(baseline.actor,request.actor)
            || !handle_tag(baseline.target,request.target) || !barrier(false)) {result.reason="initial_stamp_or_clock";return result;}
        auto cancel_guard=[&](bool initial) {
            if (mode) return true;
            if (p.family==Family::SpyNetwork) {
                if (spy_reader==nullptr) return false;
                return initial?bind_spy_two_pass(*spy_reader,module,baseline,spy):recheck_spy(*spy_reader,module,baseline,spy);
            }
            CancelObservation now{};if (!guard.cancellation(p.family,baseline,now) || !cancel_matches(p,baseline,now)) return false;
            if (initial) {cancellation=now;return true;}return now==cancellation;
        };
        if (!cancel_guard(true) || !barrier(false)) {result.status=Status::PreconditionRejected;result.reason="cancel_precondition";return result;}
        original=e.factory(p);
        if (!original.value) {result.reason="normal_factory_null";return result;}
        ActionView v{};
        if (!e.action_view(original,v) || !defaults(p,v)) return freeze("factory_fields_untrusted");
        if (!barrier(false)) return freeze("guard_before_initialize");
        if (!e.initialize_owned(original,baseline)) return freeze("initialize_unconfirmed");
        if (!barrier(false)) return freeze("guard_before_setter");
        e.mode_setter(p,original,mode);
        const auto envoy=(!mode && p.family==Family::SpyNetwork)?spy.envoy:-1;
        if (envoy!=-1) {if (!barrier(false) || !cancel_guard(false) || !e.bind_envoy_owned(original,envoy)) return freeze("envoy_binding_changed");}
        if (!e.action_view(original,v) || !initialized(p,v,baseline,mode,envoy,true)) return freeze("initialized_fields");
        // Immediate cancellation rebind and current root/clock check precede full+88.
        if (!barrier(false) || !cancel_guard(false)) return freeze("prepreview_binding_or_guard_changed");
        const bool allowed=e.full88(p,original,nullptr,false);
        if (!e.action_view(original,v) || !initialized(p,v,baseline,mode,envoy,false)) return freeze("postpreview_fields");
        auto cleanup_original=[&]() {if (!original.value) return true;if (!barrier(true) || !e.destroy_action(p,original)) return false;original={};return true;};
        auto cleanup_command=[&]() {if (!command.value) return true;if (!barrier(true) || !e.destroy_command(command)) return false;command={};clone={};return true;};
        if (!allowed) {
            if (!cleanup_original()) return freeze("preview_false_cleanup_unknown");
            result.status=Status::ModelPreviewRejected;result.reason="full88_normal_false";return result;
        }
        if (!barrier(false) || !cancel_guard(false)) return freeze("guard_before_wrapper");
        const auto wrapped=e.wrapper(p,original);command=wrapped.command;
        if (!command.value && wrapped.returned_same_slot) {
            if (!cleanup_original()) return freeze("wrapper_null_cleanup_unknown");
            result.reason="normal_wrapper_null";return result;
        }
        if (!command.value || !wrapped.returned_same_slot || command==original) return freeze("wrapper_ownership_unknown");
        CommandView cv{};
        if (!e.command_view(command,cv) || !command_fields(cv)) return freeze("command_fields");
        clone=cv.clone;
        if (clone==original || clone==command || !e.action_view(clone,v) || !initialized(p,v,baseline,mode,envoy,true)) return freeze("clone_independence_or_fields");
        if (!barrier(false)) return freeze("guard_before_command_gate");
        const bool gate=e.command_gate(command);
        if (!e.command_view(command,cv) || !command_fields(cv) || !(cv.clone==clone)
            || !e.action_view(clone,v) || !initialized(p,v,baseline,mode,envoy,true)) return freeze("postgate_fields");
        if (!cleanup_original() || !cleanup_command()) return freeze("known_cleanup_unconfirmed");
        result.status=gate?Status::ModelComplete:Status::ModelGateRejected;
        result.reason=gate?"synthetic_lifecycle_no_send":"command_gate_normal_false";return result;
    } catch (...) { return freeze("synthetic_exception_no_guessed_cleanup"); }
}
}
