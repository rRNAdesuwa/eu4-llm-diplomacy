#include "native_pair_engine.h"
#include <limits>
#include <exception>

namespace v24port {
using namespace v21pair;
namespace {
constexpr Address MAX_USER=0x800000000000ULL;
std::atomic<std::uint64_t> next_owner{1};
bool pointer(Address p) {return p>=0x10000 && p<MAX_USER && (p&7)==0;}
bool same_profile(const Profile& a,const Profile& b) {
    return a.family==b.family && a.token==b.token && a.size==b.size && a.vtable==b.vtable && a.clone==b.clone
        && a.destructor==b.destructor && a.setter==b.setter && a.local80==b.local80 && a.full88==b.full88 && a.full_caller==b.full_caller;
}
}
struct NativePairEngineDraft::Operation {
    NativePairEngineDraft& engine;int unwinding;
    explicit Operation(NativePairEngineDraft& e):engine(e),unwinding(std::uncaught_exceptions()) {
        // A secondary/reentrant caller may only latch the atomic stop bit; it
        // must not mutate the owner's registry concurrently.
        if(e.active_.exchange(true)){e.frozen_=true;throw NativeFault{Fault::Reentry,0};}
        try {e.check();}catch(...){e.latch(Fault::NativeException);e.active_=false;throw;}
    }
    ~Operation() {if(std::uncaught_exceptions()>unwinding)engine.latch(Fault::NativeException);engine.active_=false;}
};
NativePairEngineDraft::NativePairEngineDraft(Platform& p) noexcept:platform_(p),owner_serial_(next_owner.fetch_add(1)) {
    if(!owner_serial_ || owner_serial_>0xffffffffULL)latch(Fault::Budget);
}
void NativePairEngineDraft::latch(Fault reason,std::uint32_t exception) noexcept {
    frozen_=true;if(fault_==Fault::None){fault_=reason;exception_=exception;}
    for(auto& e:entries_)if(e.live)e.quarantined=true;
}
void NativePairEngineDraft::retain(Address p) {
    if(!p)return;
    if(unresolved_count_==unresolved_.size())fail(Fault::Budget);
    unresolved_[unresolved_count_++]=p;
}
void NativePairEngineDraft::resolved(Address p) noexcept {
    for(std::uint32_t i=0;i<unresolved_count_;++i)if(unresolved_[i]==p){unresolved_[i]=unresolved_[--unresolved_count_];return;}
}
[[noreturn]] void NativePairEngineDraft::fail(Fault reason,std::uint32_t exception) {
    latch(reason,exception);
    throw NativeFault{reason,exception};
}
void NativePairEngineDraft::check() {
    if(frozen_)fail(fault_==Fault::None?Fault::Reentry:fault_);
    if(!pointer(platform_.module()) || platform_.module()>MAX_USER-0x25e0000 || !platform_.ready())fail(Fault::Authority);
    if(frozen_)fail(fault_);
}
const Profile& NativePairEngineDraft::fixed(const Profile& p) {
    for(const auto& f:profiles())if(same_profile(f,p))return f;
    fail(Fault::Profile);
}
NativePairEngineDraft::Entry& NativePairEngineDraft::lookup(OwnedId id) {
    const auto ordinal=id.value&0xffffffffULL;
    if((id.value>>32)!=owner_serial_ || ordinal==0 || ordinal>issued_)fail(Fault::UnknownId);
    auto& e=entries_[static_cast<std::size_t>(ordinal-1)];
    if(!e.live || e.quarantined || !(e.id==id))fail(Fault::UnknownId);
    return e;
}
bool NativePairEngineDraft::private_range(Address p,std::size_t size) {
    if(!size || p<0x10000 || p>=MAX_USER || size>MAX_USER-p)return false;
    Region r{};if(!platform_.region(p,r))return false;
    return r.committed && r.private_memory && r.read_write && r.base>=0x10000 && r.base<MAX_USER && r.base<=p && r.size<=MAX_USER-r.base
        && p-r.base<r.size && size<=r.size-(p-r.base);
}
NativePairEngineDraft::Entry& NativePairEngineDraft::insert(Address address,const Profile& p,Kind kind) {
    if(issued_>=entries_.size())fail(Fault::Budget);
    const std::uint32_t size=kind==Kind::Command?0x58:p.size;
    if(!pointer(address) || !private_range(address,size))fail(Fault::Region);
    for(const auto& e:entries_)if(e.live && address<e.address+(e.kind==Kind::Command?0x58:e.profile->size)
        && e.address<address+size)fail(Fault::Alias);
    auto& e=entries_[issued_];++issued_;e.id={(owner_serial_<<32)|issued_};e.address=address;e.profile=&p;e.kind=kind;e.live=true;
    header(e);resolved(address);return e;
}
void NativePairEngineDraft::read(Address p,void* out,std::size_t size) {
    if(frozen_ || !out || !size || size>64 || reads_>=16384 || bytes_>1048576-size)fail(Fault::Budget);
    ++reads_;bytes_+=size;
    if(!private_range(p,size))fail(Fault::Region);
    if(!platform_.read(p,out,size))fail(Fault::Read);
    if(frozen_)fail(fault_);
}
void NativePairEngineDraft::header(Entry& e) {
    const auto size=e.kind==Kind::Command?0x58:e.profile->size;
    if(!e.live || e.quarantined || !private_range(e.address,size))fail(Fault::Region);
    const auto vt=e.kind==Kind::Command?0x1c814b0:e.profile->vtable;
    if(get<Address>(e.address)!=platform_.module()+vt || get<std::uint32_t>(e.address+8)!=0x165)fail(Fault::Type);
}
ActionView NativePairEngineDraft::view(Entry& e) {
    if(e.kind==Kind::Command)fail(Fault::Type);header(e);ActionView v{};v.size=e.profile->size;v.vtable=e.profile->vtable;
    const auto p=e.address;v.marker=get<std::uint32_t>(p+8);v.actor.value=get<Address>(p+0x10);
    v.controller.value=get<Address>(p+0x18);v.target.value=get<Address>(p+0x20);
    v.primary=get<std::uint32_t>(p+0x28);v.secondary=get<std::uint32_t>(p+0x2c);v.envoy=get<std::int32_t>(p+0x30);
    v.state=get<std::uint32_t>(p+0x34);v.value=get<std::uint8_t>(p+0x38);v.flag=get<std::uint8_t>(p+0x39);v.id=get<std::uint32_t>(p+0x3c);
    if(e.profile->family==Family::Marriage) {
        v.text.length=get<Address>(p+0x50);v.text.capacity=get<Address>(p+0x58);v.text.force=get<std::uint8_t>(p+0x60);
        if(v.text.length>128 || v.text.length>v.text.capacity || v.text.capacity>MAX_USER || v.text.force)fail(Fault::Fields);
        Address chars=p+0x40;
        // RW storage does not prove allocator ownership. Until an allocator-aware
        // certificate exists, refuse every heap String32 before reading its pointer
        // or entering any deleting destructor. Retain all issued objects.
        if(v.text.capacity>=16) fail(Fault::Ownership);
        if(v.text.capacity!=15) fail(Fault::Fields);
        else if(v.text.length>=16)fail(Fault::Fields);
        // Read every selected byte including the terminator, never just a pointer.
        for(Address n=0;n<=v.text.length;++n) {const auto c=get<std::uint8_t>(chars+n);if(n==0)v.text.first=c;if(n==v.text.length)v.text.terminator=c;}
        v.text.storage_valid=true;if(v.text.terminator)fail(Fault::Fields);
    }
    header(e);return v;
}
void NativePairEngineDraft::expected(Entry& e,bool empty) {
    if(e.profile->family==Family::Insult && get<std::int32_t>(e.address+0x40)!=-1)fail(Fault::Fields);
    if(e.profile->family==Family::FavorTrust && (get<std::int32_t>(e.address+0x40)!=5000 || get<std::int32_t>(e.address+0x44)!=1))fail(Fault::Fields);
    const auto v=view(e);const auto h=e.initialized?e.stamp.actor.value:0x2d2d2d;
    const auto target=e.initialized?e.stamp.target.value:0x2d2d2d;
    const auto date=e.initialized?e.stamp.date:0x29c77f8;
    if(v.actor.value!=h || v.controller.value!=h || v.target.value!=target || v.primary!=date || v.secondary!=date
        || v.envoy!=e.envoy || v.state!=(e.profile->family==Family::Coalition?2u:0u) || v.value!=(e.mode?1:0) || v.flag || v.id)fail(Fault::Fields);
    if(e.profile->family==Family::Marriage && empty && (v.text.length || v.text.capacity!=15 || v.text.first || v.text.force))fail(Fault::Fields);
}
void NativePairEngineDraft::write(Entry& e,std::uint32_t off,const void* input,std::size_t size) {
    if(e.kind!=Kind::Original || e.wrapped || e.previewed || !input || (size!=1 && size!=4 && size!=8)
        || off<0x10 || off+size>0x40)fail(Fault::Ownership);
    header(e);++writes_;if(!platform_.write(e.address+off,input,size))fail(Fault::Write);
    if(frozen_)fail(fault_);std::uint8_t actual[8]{};read(e.address+off,actual,size);
    const auto* bytes=static_cast<const std::uint8_t*>(input);for(std::size_t n=0;n<size;++n)if(actual[n]!=bytes[n])fail(Fault::Write);
}
Return NativePairEngineDraft::call(Call kind,const Profile& p,Address object,bool mode) {
    check();++calls_;Return result{};
    try {result=platform_.invoke(kind,p,object,mode);}catch(...){fail(Fault::NativeException);}
    if(kind==Call::Factory || kind==Call::Wrapper)retain(result.object);
    if(!result.normal || result.exception)fail(Fault::NativeException,result.exception);
    check();return result;
}
OwnedId NativePairEngineDraft::factory(const Profile& p) {
    Operation op(*this);const auto& f=fixed(p);const auto result=call(Call::Factory,f,0);
    if(!result.object)return {};
    auto& e=insert(result.object,f,Kind::Original);expected(e,true);return e.id;
}
bool NativePairEngineDraft::action_view(OwnedId id,ActionView& out) {Operation op(*this);auto& e=lookup(id);out=view(e);return true;}
bool NativePairEngineDraft::initialize_owned(OwnedId id,const PairStamp& stamp) {
    Operation op(*this);auto& e=lookup(id);if(e.kind!=Kind::Original || e.initialized || !valid(stamp))fail(Fault::Order);
    expected(e,true);
    put(e,0x10,stamp.actor.value);put(e,0x18,stamp.actor.value);put(e,0x20,stamp.target.value);
    put(e,0x28,stamp.date);put(e,0x2c,stamp.date);put(e,0x30,std::int32_t{-1});put(e,0x34,std::uint32_t{e.profile->family==Family::Coalition?2u:0u});
    put(e,0x39,std::uint8_t{0});put(e,0x3c,std::uint32_t{0});e.stamp=stamp;e.initialized=true;expected(e,true);return true;
}
void NativePairEngineDraft::mode_setter(const Profile& p,OwnedId id,bool mode) {
    Operation op(*this);const auto& f=fixed(p);auto& e=lookup(id);
    if(e.profile!=&f || e.kind!=Kind::Original || !e.initialized || e.mode_set || e.previewed)fail(Fault::Order);
    expected(e,true);call(Call::Setter,f,e.address,mode);e.mode=mode;e.mode_set=true;
    // 586424 writes the entry's int32 envoy into +30 on the false path.
    // Preserve the real field; do not clear/mask it to fit a synthetic model.
    if(f.family==Family::SpyNetwork && !mode){const auto v=view(e);if(v.envoy<0)fail(Fault::Fields);e.envoy=v.envoy;}
    expected(e,true);
}
bool NativePairEngineDraft::bind_envoy_owned(OwnedId id,std::int32_t envoy) {
    Operation op(*this);auto& e=lookup(id);
    if(e.profile->family!=Family::SpyNetwork || !e.mode_set || e.mode || e.envoy_bound || envoy<0)fail(Fault::Order);
    expected(e,true);if(e.envoy!=envoy)fail(Fault::Fields);e.envoy_bound=true;expected(e,true);return true;
}
bool NativePairEngineDraft::full88(const Profile& p,OwnedId id,std::nullptr_t,bool option) {
    Operation op(*this);const auto& f=fixed(p);auto& e=lookup(id);
    if(option || e.profile!=&f || !e.mode_set || e.previewed || (f.family==Family::SpyNetwork && !e.mode && !e.envoy_bound))fail(Fault::Order);
    expected(e,true);const auto result=call(Call::Full88,f,e.address);e.previewed=true;expected(e,false);return result.boolean;
}
Wrapped NativePairEngineDraft::wrapper(const Profile& p,OwnedId id) {
    Operation op(*this);const auto& f=fixed(p);auto& e=lookup(id);
    if(e.profile!=&f || !e.previewed || e.wrapped || e.kind!=Kind::Original)fail(Fault::Order);
    expected(e,false);const auto result=call(Call::Wrapper,f,e.address);e.wrapped=true;
    if(!result.returned_same_slot)fail(Fault::WrapperSlot);
    if(!result.object){expected(e,false);return {{},true};}
    auto& cmd=insert(result.object,f,Kind::Command);cmd.source=e.id;
    const auto clone_ptr=get<Address>(cmd.address+0x50);retain(clone_ptr);auto& clone=insert(clone_ptr,f,Kind::Clone);
    clone.initialized=true;clone.stamp=e.stamp;clone.mode=e.mode;clone.mode_set=true;clone.envoy=e.envoy;clone.envoy_bound=e.envoy_bound;
    clone.source=cmd.id;cmd.peer=clone.id;expected(clone,true);expected(e,false);command(cmd);return {cmd.id,true};
}
CommandView NativePairEngineDraft::command(Entry& e) {
    if(e.kind!=Kind::Command)fail(Fault::Type);header(e);const auto p=e.address;CommandView v{};
    v.marker=get<std::uint32_t>(p+8);v.token=get<std::uint32_t>(p+0x44);v.field10=get<std::uint8_t>(p+0x10);
    v.field18=get<Address>(p+0x18);v.field28=get<Address>(p+0x28);v.field30=get<Address>(p+0x30);
    v.field38=get<std::int32_t>(p+0x38);v.field3c=get<std::uint32_t>(p+0x3c);v.field40=get<std::uint16_t>(p+0x40);v.field48=get<Address>(p+0x48);
    auto& clone=lookup(e.peer);if(clone.kind!=Kind::Clone || !(clone.source==e.id) || get<Address>(p+0x50)!=clone.address)fail(Fault::Ownership);
    if(v.token!=0x2934 || v.field10 || v.field18 || v.field28 || v.field30!=15 || v.field38!=-1 || v.field3c || v.field40 || v.field48!=0xffff)fail(Fault::Fields);
    expected(clone,true);v.clone=clone.id;header(e);return v;
}
bool NativePairEngineDraft::command_view(OwnedId id,CommandView& out) {Operation op(*this);out=command(lookup(id));return true;}
bool NativePairEngineDraft::command_gate(OwnedId id) {
    Operation op(*this);auto& e=lookup(id);command(e);auto& source=lookup(e.source);expected(source,false);
    const auto result=call(Call::Gate,*e.profile,e.address);command(e);expected(source,false);e.gate_checked=true;e.gate_allowed=result.boolean;return result.boolean;
}
bool NativePairEngineDraft::destroy_action(const Profile& p,OwnedId id) {
    Operation op(*this);const auto& f=fixed(p);auto& e=lookup(id);if(e.profile!=&f || e.kind!=Kind::Original)fail(Fault::Ownership);
    expected(e,!e.previewed);call(Call::ActionDestructor,f,e.address);e.live=false;return true;
}
bool NativePairEngineDraft::destroy_command(OwnedId id) {
    Operation op(*this);auto& e=lookup(id);command(e);auto& clone=lookup(e.peer);
    call(Call::CommandDestructor,*e.profile,e.address);e.live=false;clone.live=false;return true;
}
v21pair::TransferReturn NativePairEngineDraft::transfer_owned(OwnedId id) {
    Operation op(*this);auto& e=lookup(id);command(e);auto& clone=lookup(e.peer);
    if(!e.gate_checked || !e.gate_allowed || e.kind!=Kind::Command || clone.kind!=Kind::Clone
        || (e.source.value>>32)!=owner_serial_ || !(e.source.value&0xffffffffULL)
        || (e.source.value&0xffffffffULL)>issued_)fail(Fault::Order);
    auto& source=entries_[static_cast<std::size_t>((e.source.value&0xffffffffULL)-1)];
    if(source.live || source.quarantined || source.transferred || source.kind!=Kind::Original
        || !(source.id==e.source) || source.profile!=e.profile || !source.wrapped)fail(Fault::Ownership);
    TransferEnvelope envelope{*e.profile,clone.stamp,e.address,clone.address,clone.mode,clone.envoy};
    ++calls_;
    // Relinquish locally BEFORE the adapter attempt. Even an uncertain return,
    // pre-entry refusal or throw never permits a destructor or another attempt.
    e.live=false;clone.live=false;e.transferred=true;clone.transferred=true;
    v21pair::TransferReturn result{};
    try {result=platform_.submit(envelope);}catch(...){fail(Fault::NativeException);}
    // No ready(), read(), header(), command(), or object lookup after submit.
    if(!result.normal || result.exception || !result.value || !result.slot_consumed)
        latch(Fault::NativeException,result.exception);
    return result;
}
Diagnostics NativePairEngineDraft::diagnostics() const noexcept {
    Diagnostics d{};d.frozen=frozen_;d.fault=fault_;d.exception=exception_;d.issued=issued_;d.calls=calls_;d.reads=reads_;d.writes=writes_;d.read_bytes=bytes_;d.unresolved_returns=unresolved_count_;
    for(const auto& e:entries_) {if(e.live)++d.live;if(e.quarantined)++d.quarantined;}return d;
}
}
