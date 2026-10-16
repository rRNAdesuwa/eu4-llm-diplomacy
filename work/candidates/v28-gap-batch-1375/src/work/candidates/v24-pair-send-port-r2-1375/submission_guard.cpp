#include "submission_guard.h"
namespace v24port {
bool SubmissionGuard::read(Address p,void* out,std::size_t n) {
    if(failed_ || !env_.read || p<0x10000 || p>=0x800000000000ULL || !n || n>8 || n>0x800000000000ULL-p || ++reads_>512)return false;
    return env_.read(env_.user,p,out,n);
}
bool SubmissionGuard::context(SubmissionContext& c) {
    Address vt=0;
    return at(env_.base,0x233fe78,c.game) && at(c.game,0x1e00,c.server)
        && at(c.server,0,vt) && vt==env_.base+0x1cb8460
        && at(c.server,0x330,c.holder) && at(c.holder,0x370,c.context)
        && at(c.context,0x58,c.transport) && at(c.transport,0,vt) && vt==env_.base+0x1d96178
        && at(env_.base+0x1d96178,0x30,vt) && vt==env_.base+0x1580370
        && at(c.context,0x55,c.ready55) && at(c.context,0x80d,c.ready80d)
        && (c.ready55==1 || c.ready80d==1) && c.ready55<=1 && c.ready80d<=1;
}
bool SubmissionGuard::owned(const TransferEnvelope& e) {
    using namespace v21pair;
    if(!valid(e.stamp) || e.command<0x10000 || e.clone<0x10000 || e.command==e.clone
        || (e.command&7) || (e.clone&7) || e.stamp.game!=prepared_.game)return false;
    Address a=0;std::uint32_t u=0;std::uint8_t b=0;std::uint16_t w=0;std::int32_t s=0;
    if(!at(e.command,0,a) || a!=env_.base+0x1c814b0 || !at(e.command,8,u) || u!=0x165)return false;
    if(!at(e.command,0x10,b) || b || !at(e.command,0x18,a) || a || !at(e.command,0x28,a) || a
        || !at(e.command,0x30,a) || a!=15 || !at(e.command,0x38,s) || s!=-1 || !at(e.command,0x3c,u) || u
        || !at(e.command,0x40,w) || w || !at(e.command,0x44,u) || u!=0x2934
        || !at(e.command,0x48,a) || a!=0xffff || !at(e.command,0x50,a) || a!=e.clone)return false;
    if(!at(e.clone,0,a) || a!=env_.base+e.profile.vtable || !at(e.clone,8,u) || u!=0x165)return false;
    if(!at(e.clone,0x10,a) || a!=e.stamp.actor.value || !at(e.clone,0x18,a) || a!=e.stamp.actor.value
        || !at(e.clone,0x20,a) || a!=e.stamp.target.value || !at(e.clone,0x28,u) || u!=e.stamp.date
        || !at(e.clone,0x2c,u) || u!=e.stamp.date || !at(e.clone,0x30,s) || s!=e.envoy
        || !at(e.clone,0x34,u) || u!=(e.profile.family==Family::Coalition?2u:0u) || !at(e.clone,0x38,b) || b!=(e.mode?1:0)
        || !at(e.clone,0x39,b) || b || !at(e.clone,0x3c,u) || u)return false;
    if(e.profile.family==Family::Insult && (!at(e.clone,0x40,s) || s!=-1))return false;
    if(e.profile.family==Family::Marriage) {
        if(!at(e.clone,0x50,a) || a || !at(e.clone,0x58,a) || a!=15
            || !at(e.clone,0x40,b) || b || !at(e.clone,0x60,b) || b)return false;
    }
    return true;
}
bool SubmissionGuard::prepare(SubmissionContext& out) {
    if(attempted_ || failed_)return false;attempted_=true;
    if(!env_.world || !env_.clock || !env_.original_expires || !env_.world(env_.user))return false;
    last_clock_=env_.clock(env_.user);if(last_clock_>=env_.original_expires)return false;
    SubmissionContext a{},b{};
    if(!context(a) || !context(b) || !(a==b))return false;prepared_=b;out=b;return true;
}
bool SubmissionGuard::final(const SubmissionContext& expected,const TransferEnvelope& e) {
    if(!attempted_ || final_attempted_ || failed_ || !(expected==prepared_))return false;final_attempted_=true;
    // This callback includes all fresh identity/world reads, then two exact
    // context passes around the owned fields. Only the final clock follows.
    if(!env_.world(env_.user))return false;
    SubmissionContext a{},b{};
    if(!context(a) || !(a==prepared_) || !owned(e) || !context(b) || !(b==prepared_))return false;
    const auto now=env_.clock(env_.user);
    return now>=last_clock_ && now<env_.original_expires;
}
bool SubmissionGuard::prepare_cb(void* p,SubmissionContext& c) {
    auto& self=*static_cast<SubmissionGuard*>(p);try{const bool ok=self.prepare(c);if(!ok)self.failed_=true;return ok;}catch(...){self.failed_=true;return false;}
}
bool SubmissionGuard::final_cb(void* p,const SubmissionContext& c,const TransferEnvelope& e) {
    auto& self=*static_cast<SubmissionGuard*>(p);try{const bool ok=self.final(c,e);if(!ok)self.failed_=true;return ok;}catch(...){self.failed_=true;return false;}
}
}
