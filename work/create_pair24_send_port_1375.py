"""Create private native transfer adapter from the frozen R2 engine."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'work/candidates/v21-native-pair-port-r2-1375'
CORE=ROOT/'work/candidates/v24-pair-send-core-r2-1375'
HERE=ROOT/'work/candidates/v24-pair-send-port-1375'
def desc(p):
 b=p.read_bytes();assert len(b)<4*1024*1024;return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def put(name,b):
 p=HERE/name;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(b.encode('ascii') if isinstance(b,str) else b)
index=json.loads((OLD/'source-index.json').read_bytes());assert all(desc(OLD/k)==v for k,v in index.items())
cv=json.loads((CORE/'development-attempt1/validation.json').read_bytes());assert cv['passed'] and cv['build']['all_children_collected']
assert cv['sources_before']==cv['sources_after']
HERE.mkdir(exist_ok=False);pins={(OLD/k).relative_to(ROOT).as_posix():v for k,v in index.items()}
for p in [CORE/'pair_send.h',CORE/'pair_send.cpp',CORE/'source-index.json',CORE/'development-attempt1/validation.json',
 ROOT/'work/candidates/v21-core-pair-nosend-1375/validate.py',ROOT/'work/candidates/v21-core-pair-nosend-r2-1375/pair_component.h']:
 pins[p.relative_to(ROOT).as_posix()]=desc(p)
for name in ['native_pair_engine.h','native_pair_engine.cpp','native_platform.h','native_platform.cpp','native_pins.h','test_native_pair_engine.cpp']:
 original=(OLD/name).read_bytes();put('preimages/'+name,original)
 data=original.decode('ascii').replace('v21port','v24port')
 if name=='native_pair_engine.h':
  data=data.replace('#include <atomic>','#include <atomic>\n#include "../v24-pair-send-core-r2-1375/pair_send.h"',1)
  at='// An injected private platform'
  structs='''struct TransferEnvelope {
    v21pair::Profile profile{};v21pair::PairStamp stamp{};
    Address command{},clone{};bool mode{};std::int32_t envoy{-1};
};
'''
  assert at in data;data=data.replace(at,structs+at,1)
  at='    virtual Return invoke(Call,const v21pair::Profile&,Address,bool)=0;'
  assert at in data;data=data.replace(at,at+'\n    virtual v21pair::TransferReturn submit(const TransferEnvelope&) {return {};}',1)
  data=data.replace('    Diagnostics diagnostics() const noexcept;','    v21pair::TransferReturn transfer_owned(v21pair::OwnedId);\n    Diagnostics diagnostics() const noexcept;',1)
  data=data.replace('previewed{},wrapped{};','previewed{},wrapped{},gate_checked{},gate_allowed{},transferred{};',1)
 elif name=='native_pair_engine.cpp':
  at='const auto result=call(Call::Gate,*e.profile,e.address);command(e);expected(source,false);return result.boolean;'
  assert at in data;data=data.replace(at,'const auto result=call(Call::Gate,*e.profile,e.address);command(e);expected(source,false);e.gate_checked=true;e.gate_allowed=result.boolean;return result.boolean;',1)
  at='Diagnostics NativePairEngineDraft::diagnostics() const noexcept {'
  method='''v21pair::TransferReturn NativePairEngineDraft::transfer_owned(OwnedId id) {
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
'''
  assert at in data;data=data.replace(at,method+at,1)
 elif name=='native_platform.h':
  at='class CompiledWin32Platform final : public Platform {'
  before='''struct SubmissionContext {Address game{},server{},holder{},context{},transport{};std::uint8_t ready55{},ready80d{};
    bool operator==(const SubmissionContext& b) const noexcept {
        return game==b.game && server==b.server && holder==b.holder && context==b.context && transport==b.transport
            && ready55==b.ready55 && ready80d==b.ready80d;
    }};
struct SubmissionAuthority {
    void* user{};
    bool (*prepare)(void*,SubmissionContext&){};
    bool (*final)(void*,const SubmissionContext&,const TransferEnvelope&){};
};
'''
  assert at in data;data=data.replace(at,before+at,1)
  data=data.replace('Authority a) noexcept:base_(base),owner_(owner),authority_(a){}','Authority a,SubmissionAuthority send={}) noexcept:base_(base),owner_(owner),authority_(a),submission_(send){}',1)
  data=data.replace('    Return invoke(Call,const v21pair::Profile&,Address,bool) override;','    Return invoke(Call,const v21pair::Profile&,Address,bool) override;\n    v21pair::TransferReturn submit(const TransferEnvelope&) override;',1)
  data=data.replace('std::uint32_t owner_;Authority authority_;','std::uint32_t owner_;Authority authority_;SubmissionAuthority submission_;',1)
 elif name=='native_platform.cpp':
  data=data.replace('#include "native_pins.h"','#include "native_pins.h"\n#include "sender_pins.h"',1)
  at='bool CompiledWin32Platform::ready() {'
  safe='''namespace {
bool send_prepare(const SubmissionAuthority& a,SubmissionContext& c) noexcept {
    __try {return a.prepare && a.prepare(a.user,c);}__except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
bool send_final(const SubmissionAuthority& a,const SubmissionContext& c,const TransferEnvelope& e) noexcept {
    __try {return a.final && a.final(a.user,c,e);}__except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
v21pair::TransferReturn native_submit(Address base,Address context,Address command) noexcept {
    v21pair::TransferReturn result{};void* slot_value=reinterpret_cast<void*>(command);
    __try {
        result.value=reinterpret_cast<bool(__fastcall*)(void*,void**)>(base+0x14ca210)(reinterpret_cast<void*>(context),&slot_value);
        result.slot_consumed=slot_value==nullptr;result.normal=true;
    } __except(EXCEPTION_EXECUTE_HANDLER) {result.exception=GetExceptionCode();}
    // The local slot can be read; transferred command/clone memory cannot.
    return result;
}
}
'''
  assert at in data;data=data.replace(at,safe+at,1)
  suffix='''v21pair::TransferReturn CompiledWin32Platform::submit(const TransferEnvelope& e) {
    if(!canonical(e.profile) || !v21pair::valid(e.stamp) || !ready() || !submission_.prepare || !submission_.final)return {};
    for(const auto& p:kSenderCodePins)if(!pin(base_,p))return {};
    if(!slot(base_,0x1d961a8,0x1580370))return {};
    SubmissionContext c{};if(!send_prepare(submission_,c))return {};
    // final callback rereads context + ledger-supplied owned fields and obtains
    // the LAST monotonic/original-TTL check after all preparation and reads.
    if(!send_final(submission_,c,e))return {};
    return native_submit(base_,c.context,e.command);
}
'''
  assert data.endswith('}\n');data=data[:-2]+suffix+'}\n'
 elif name=='test_native_pair_engine.cpp':
  # Derivation is only for the separate analysis test, never a native subclass.
  data=data.replace('struct Fake final:Platform','struct Fake:Platform',1)
 put(name,data)
old_sender=ROOT/'work/candidates/v19-spy-restricted-host-r2-1375/core/sender-pins.h'
pins[old_sender.relative_to(ROOT).as_posix()]=desc(old_sender)
chunks=[]
for address,hexdata in re.findall(r'\{ 0x([0-9a-f]+), "([0-9a-f]+)" \}',old_sender.read_text()):
 if int(address,16) in (0x14ca210,0x1580370,0x811aa0):
  b=bytes.fromhex(hexdata)
  for i in range(0,len(b),64):chunks.append('    {0x%x,"%s"},'%(int(address,16)+i,b[i:i+64].hex()))
assert len(chunks)==5
put('sender_pins.h','#pragma once\nnamespace v24port {\ninline constexpr CodePin kSenderCodePins[] = {\n'+'\n'.join(chunks)+'\n};\n}\n')
put('submission_guard.h',r'''#pragma once
#include "native_platform.h"
namespace v24port {
// A future private Host binds this to the actual same NativePairGuard lease.
// Injected callbacks do not certify OS identity/SP/epoch by themselves.
struct SubmissionEnvironment {
    Address base{};std::uint64_t original_expires{};void* user{};
    bool (*world)(void*){};
    bool (*read)(void*,Address,void*,std::size_t){};
    std::uint64_t (*clock)(void*){};
};
class SubmissionGuard {
public:
    explicit SubmissionGuard(SubmissionEnvironment e) noexcept:env_(e){}
    SubmissionAuthority authority() noexcept {return {this,prepare_cb,final_cb};}
private:
    SubmissionEnvironment env_;SubmissionContext prepared_{};bool attempted_{},final_attempted_{},failed_{};
    unsigned reads_{};std::uint64_t last_clock_{};
    bool read(Address,void*,std::size_t);
    template<class T>bool at(Address p,std::uint32_t off,T& out){return p>=0x10000 && (p&7)==0 && p<0x800000000000ULL-0x810 && read(p+off,&out,sizeof(out));}
    bool context(SubmissionContext&);
    bool owned(const TransferEnvelope&);
    bool prepare(SubmissionContext&);
    bool final(const SubmissionContext&,const TransferEnvelope&);
    static bool prepare_cb(void*,SubmissionContext&);
    static bool final_cb(void*,const SubmissionContext&,const TransferEnvelope&);
};
}
''')
put('submission_guard.cpp',r'''#include "submission_guard.h"
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
        && at(c.transport,0x30,vt) && vt==env_.base+0x1580370
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
        || !at(e.clone,0x34,u) || u || !at(e.clone,0x38,b) || b!=(e.mode?1:0)
        || !at(e.clone,0x39,b) || b || !at(e.clone,0x3c,u) || u)return false;
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
''')
put('test_transfer.cpp',r'''#define main retained_port_main
#include "test_native_pair_engine.cpp"
#undef main
#include "submission_guard.h"
struct SendFake final:Fake {
    unsigned submits{};v21pair::TransferReturn response{true,true,true,0};bool throws{};
    TransferEnvelope captured{};
    v21pair::TransferReturn submit(const TransferEnvelope& e) override {
        ++submits;captured=e;CHECK(!memory.at(last_original).live);CHECK(e.command==last_command && e.clone==last_clone);
        if(response.slot_consumed){memory.at(e.command).live=false;memory.at(e.clone).live=false;}
        if(throws)throw 5;return response;
    }
};
struct Transfer final:TransferPort {
    NativePairEngineDraft& e;unsigned intents{};explicit Transfer(NativePairEngineDraft& q):e(q){}
    bool dispatch_intent(const Request&,const PairStamp&,OwnedId,OwnedId)override{++intents;return true;}
    TransferReturn submit_owned(OwnedId c)override{return e.transfer_owned(c);}
};
struct BinderMemory {
    std::map<Address,std::uint8_t> data;unsigned reads{},worlds{},clocks{};std::uint64_t now=1;
    std::function<void(BinderMemory&)> on_world,on_clock;
    template<class T>void set(Address p,T v){unsigned char b[sizeof(T)]{};std::memcpy(b,&v,sizeof(v));for(unsigned i=0;i<sizeof(T);++i)data[p+i]=b[i];}
    static bool read(void* p,Address a,void* out,std::size_t n){auto& m=*static_cast<BinderMemory*>(p);++m.reads;auto* b=static_cast<unsigned char*>(out);
        for(std::size_t i=0;i<n;++i){auto it=m.data.find(a+i);if(it==m.data.end())return false;b[i]=it->second;}return true;}
    static bool world(void* p){auto& m=*static_cast<BinderMemory*>(p);++m.worlds;if(m.on_world)m.on_world(m);return true;}
    static std::uint64_t clock(void* p){auto& m=*static_cast<BinderMemory*>(p);++m.clocks;if(m.on_clock)m.on_clock(m);return m.now;}
};
constexpr Address BASE=0x140000000,SERVER=0x70000,HOLDER=0x80000,CONTEXT=0x90000,TRANSPORT=0xa0000;
void context_fixture(BinderMemory& m,const TransferEnvelope& e){
    m.set(BASE+0x233fe78,e.stamp.game);m.set(e.stamp.game+0x1e00,SERVER);m.set(SERVER,BASE+0x1cb8460);
    m.set(SERVER+0x330,HOLDER);m.set(HOLDER+0x370,CONTEXT);m.set(CONTEXT+0x58,TRANSPORT);
    m.set(TRANSPORT,BASE+0x1d96178);m.set(TRANSPORT+0x30,BASE+0x1580370);
    m.set(CONTEXT+0x55,std::uint8_t{1});m.set(CONTEXT+0x80d,std::uint8_t{0});
}
TransferEnvelope prepared(SendFake& f,NativePairEngineDraft& e,const Profile& p){auto flow=wrapped(e,p);CHECK(e.command_gate(flow.c));CHECK(e.destroy_action(p,flow.a));
    return {p,sample(),f.last_command,f.last_clone,true,-1};}
unsigned groups=0;
template<class F>void group(const char* n,F f){f();++groups;std::cout<<"PASS "<<n<<'\n';}
int main(){try{
    CHECK(retained_port_main()==0);
    group("actual_adapter_all_six_start_transfers",[]{for(unsigned i=0;i<6;++i){SendFake f;NativePairEngineDraft e(f);Guard g;Transfer t(e);SendCore core;
        Request r{};r.action=static_cast<Action>(i*2);r.actor.bytes={'F','R','A'};r.target.bytes={'E','N','G'};
        auto result=core.invoke(r,g,e,t,100);CHECK(result.submitted && result.transfer==TransferOutcome::Dispatched);
        CHECK(f.submits==1 && f.deletes==1 && f.read_after_free==0 && e.diagnostics().live==0);
        const auto reads=f.reads;bool threw=false;try{e.destroy_command({(1ULL<<32)|2});}catch(...){threw=true;}
        CHECK(threw && f.reads==reads && f.read_after_free==0 && f.submits==1);
    }});
    group("actual_adapter_all_unknown_returns",[]{for(unsigned normal=0;normal<2;++normal)for(unsigned value=0;value<2;++value)for(unsigned consumed=0;consumed<2;++consumed){
        if(normal && value && consumed)continue;SendFake f;NativePairEngineDraft e(f);auto flow=wrapped(e,profiles()[1]);
        CHECK(e.command_gate(flow.c));CHECK(e.destroy_action(profiles()[1],flow.a));f.response={normal!=0,value!=0,consumed!=0,0};
        auto result=e.transfer_owned(flow.c);CHECK(result.normal==(normal!=0) && result.value==(value!=0) && result.slot_consumed==(consumed!=0));
        CHECK(e.diagnostics().frozen && e.diagnostics().live==0 && f.submits==1 && f.deletes==1 && f.read_after_free==0);
        const auto reads=f.reads;bool threw=false;try{e.destroy_command(flow.c);}catch(...){threw=true;}
        CHECK(threw && f.reads==reads && f.submits==1 && f.deletes==1 && f.read_after_free==0);
    }});
    group("adapter_throw_relinquishes_without_object_reads",[]{for(bool consumed:{false,true}){SendFake f;NativePairEngineDraft e(f);auto flow=wrapped(e,profiles()[2]);
        CHECK(e.command_gate(flow.c));CHECK(e.destroy_action(profiles()[2],flow.a));f.response.slot_consumed=consumed;f.throws=true;
        bool threw=false;try{e.transfer_owned(flow.c);}catch(...){threw=true;}CHECK(threw && e.diagnostics().frozen && e.diagnostics().live==0);
        CHECK(f.submits==1 && f.deletes==1 && f.read_after_free==0);
    }});
    group("transfer_requires_deleted_original_and_true_gate",[]{for(unsigned v=0;v<2;++v){SendFake f;NativePairEngineDraft e(f);auto flow=wrapped(e,profiles()[2]);
        if(v==0)CHECK(e.command_gate(flow.c));else {f.gate=false;CHECK(!e.command_gate(flow.c));CHECK(e.destroy_action(profiles()[2],flow.a));}
        bool threw=false;try{e.transfer_owned(flow.c);}catch(...){threw=true;}CHECK(threw && f.submits==0);
    }});
    group("binder_context_owned_fields_and_last_ttl",[]{for(unsigned family=0;family<6;++family){SendFake f;NativePairEngineDraft e(f);auto env=prepared(f,e,profiles()[family]);BinderMemory m;
        for(const auto& pair:f.memory)for(std::size_t i=0;i<pair.second.bytes.size();++i)m.data[pair.first+i]=pair.second.bytes[i];context_fixture(m,env);
        SubmissionGuard guard({BASE,100,&m,BinderMemory::world,BinderMemory::read,BinderMemory::clock});auto a=guard.authority();SubmissionContext c{};
        CHECK(a.prepare(a.user,c));CHECK(a.final(a.user,c,env));CHECK(m.worlds==2 && m.clocks==2 && m.reads<512);
        CHECK(!a.final(a.user,c,env));CHECK(!a.prepare(a.user,c));
    }});
    group("binder_rejects_context_world_callback_change",[]{SendFake f;NativePairEngineDraft e(f);auto env=prepared(f,e,profiles()[2]);BinderMemory m;
        for(const auto& pair:f.memory)for(std::size_t i=0;i<pair.second.bytes.size();++i)m.data[pair.first+i]=pair.second.bytes[i];context_fixture(m,env);
        SubmissionGuard guard({BASE,100,&m,BinderMemory::world,BinderMemory::read,BinderMemory::clock});auto a=guard.authority();SubmissionContext c{};CHECK(a.prepare(a.user,c));
        m.on_world=[](BinderMemory& q){q.set(CONTEXT+0x58,Address{0xb0000});};CHECK(!a.final(a.user,c,env));
    });
    group("binder_rejects_expiry_rollback_and_owned_mutations",[]{for(unsigned v=0;v<9;++v){SendFake f;NativePairEngineDraft e(f);auto env=prepared(f,e,profiles()[1]);BinderMemory m;
        for(const auto& pair:f.memory)for(std::size_t i=0;i<pair.second.bytes.size();++i)m.data[pair.first+i]=pair.second.bytes[i];context_fixture(m,env);
        SubmissionGuard guard({BASE,100,&m,BinderMemory::world,BinderMemory::read,BinderMemory::clock});auto a=guard.authority();SubmissionContext c{};CHECK(a.prepare(a.user,c));
        if(v==0)m.now=100;else if(v==1)m.now=0;else if(v==2)m.set(env.command+0x50,env.command);
        else if(v==3)m.set(env.clone+0x20,env.stamp.actor.value);else if(v==4)m.set(env.clone+0x58,Address{16});
        else if(v==5)m.set(env.command+0x44,std::uint32_t{0});else if(v==6)m.set(env.clone,BASE+0x1234);
        else if(v==7)m.set(TRANSPORT,BASE+0x1234);else m.set(CONTEXT+0x55,std::uint8_t{2});
        CHECK(!a.final(a.user,c,env));
    }});
    std::cout<<"transfer_groups="<<groups<<" checks="<<checks<<" native_game_called=false\n";return 0;
}catch(const std::exception& x){std::cerr<<x.what()<<'\n';return 1;}}
''')
put('build_test.cmd',r'''@echo off
setlocal
set "pair24_src=%~dp0"
set "pair24_out=%~1"
mkdir "%pair24_out%" || exit /b 10
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" > "%pair24_out%\environment.stdout" 2>&1
if errorlevel 1 exit /b 11
for %%f in (native_pair_engine submission_guard native_platform test_transfer) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair24_src%%%f.cpp" /Fo"%pair24_out%\%%f.obj" > "%pair24_out%\%%f.stdout" 2> "%pair24_out%\%%f.stderr"
 if errorlevel 1 exit /b 12
)
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair24_src%..\v24-pair-send-core-r2-1375\pair_send.cpp" /Fo"%pair24_out%\core.obj" > "%pair24_out%\core.stdout" 2> "%pair24_out%\core.stderr"
if errorlevel 1 exit /b 13
link /nologo /OUT:"%pair24_out%\test_transfer.exe" "%pair24_out%\native_pair_engine.obj" "%pair24_out%\submission_guard.obj" "%pair24_out%\test_transfer.obj" "%pair24_out%\core.obj" > "%pair24_out%\link.stdout" 2> "%pair24_out%\link.stderr"
if errorlevel 1 exit /b 14
"%pair24_out%\test_transfer.exe" > "%pair24_out%\test.stdout" 2> "%pair24_out%\test.stderr"
exit /b %errorlevel%
''')
put('README.md','''# Private V24 native pair transfer adapter

New namespace preserves all frozen R2 source bytes. Own ledger only, true gate,
original already deleted, command owns clone. Before adapter submission local
ownership is relinquished; no object reads/cleanup even on refusal or exception.
New SubmissionGuard requires two matching contexts, then world/typed owned
command+clone/context and LAST monotonic/original TTL. Platform pins exact submit
and transport bytes and invokes only 14ca210(context,command**). No receiver drain.
Native platform is compiled but NOT linked to the offline synthetic test EXE.
Private callbacks still need an actual initialized Host and fresh process.
No strict SP/epoch/lifetime/receiver causality/effect proof or production backend.
''')
pins[Path(__file__).relative_to(ROOT).as_posix()]=desc(Path(__file__))
put('input-pins.json',json.dumps(pins,indent=2,sort_keys=True)+'\n')
validator=(CORE/'validate.py').read_text().replace("'send_groups=10 '","'transfer_groups=7 '")
put('validate.py',validator)
put('source-index.json',json.dumps({p.name:desc(p) for p in HERE.iterdir() if p.is_file()},indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(candidate=HERE.name,inputs=len(pins))))
