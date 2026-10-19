#include "native_pair_engine.h"
#include <cstring>
#include <functional>
#include <iostream>
#include <map>
#include <stdexcept>
#include <vector>
using namespace v21pair;
using namespace v24port;
unsigned checks=0;
#define CHECK(x) do{++checks;if(!(x))throw std::runtime_error(#x);}while(false)
PairStamp sample() {
    PairStamp s{};s.process_creation=111;s.session=222;s.module_pin=333;s.database=0x20000;s.game=0x30000;s.array=0x40000;
    s.actor_object=0x50000;s.target_object=0x60000;s.owner_thread=7;s.world_witness=8;s.count=512;s.date=0x2f20000;
    s.actor={0x0100007a00415246ULL};s.target={0x0100002e00474e45ULL};s.current_player=s.actor;s.effective_player=s.actor;return s;
}
struct Fake:Platform {
    struct Block {std::vector<unsigned char> bytes;bool live=true,priv=true,rw=true;};
    std::vector<Address> read_addresses;
    std::map<Address,Block> memory;Address next=0x100000,last_original{},last_command{},last_clone{};
    unsigned calls=0,deletes=0,reads=0,writes=0,read_after_free=0,native_entries=0;
    std::uint64_t now=1,expires=100,highwater=1;bool work_identity=true;
    std::function<void(Fake&)> ready_hook,read_hook,write_hook;
    bool authority=true,throw_ready=false,fail_read=false,fail_write=false,short_write=false,preview=true,gate=true;
    bool null_factory=false,null_wrapper=false,bad_slot=false,command_alias=false,clone_alias=false,clone_cmd_alias=false;
    bool fail_region=false,heap_string=false;Call fault_call=Call::Factory;bool fault=false,throw_call=false;
    std::int32_t native_envoy=0;
    std::function<void(Call,Fake&)> before,after;
    Address module()const noexcept override{return 0x140000000ULL;}
    bool ready()override {if(throw_ready)throw 7;if(ready_hook)ready_hook(*this);return authority;}
    bool final_gate(bool cleanup) {if(!work_identity || now<highwater)return false;highwater=now;return cleanup || now<expires;}
    auto locate(Address p,std::size_t n) {
        auto it=memory.upper_bound(p);if(it==memory.begin())return memory.end();--it;
        if(p-it->first>it->second.bytes.size() || n>it->second.bytes.size()-(p-it->first))return memory.end();return it;
    }
    bool region(Address p,Region& r)override {
        if(fail_region)return false;
        auto it=locate(p,1);if(it==memory.end())return false;
        r={it->first,it->second.bytes.size(),it->second.live,it->second.priv,it->second.rw};return true;
    }
    bool read(Address p,void* out,std::size_t n)override {
        ++reads;read_addresses.push_back(p);CHECK(n>0 && n<=64);auto it=locate(p,n);if(it==memory.end())return false;
        if(!it->second.live){++read_after_free;return false;}if(fail_read)return false;
        std::memcpy(out,it->second.bytes.data()+p-it->first,n);if(read_hook)read_hook(*this);return true;
    }
    bool write(Address p,const void* in,std::size_t n)override {
        ++writes;auto it=locate(p,n);if(it==memory.end() || !it->second.live || fail_write)return false;
        CHECK(n==1 || n==4 || n==8);CHECK(p-it->first>=0x10 && p-it->first+n<=0x40);
        if(write_hook)write_hook(*this);if(!final_gate(false))return false;
        if(!short_write)std::memcpy(it->second.bytes.data()+p-it->first,in,n);return true;
    }
    Address allocate(std::size_t n) {Address p=next;next+=0x1000;memory[p]={std::vector<unsigned char>(n,0)};return p;}
    template<class T>void set(Address p,T v) {auto it=locate(p,sizeof(v));CHECK(it!=memory.end());std::memcpy(it->second.bytes.data()+p-it->first,&v,sizeof(v));}
    template<class T>T get(Address p) {T v{};auto it=locate(p,sizeof(v));CHECK(it!=memory.end());std::memcpy(&v,it->second.bytes.data()+p-it->first,sizeof(v));return v;}
    Address action(const Profile& p) {
        const auto a=allocate(p.size);set(a,module()+p.vtable);set(a+8,std::uint32_t{0x165});
        for(unsigned off:{0x10U,0x18U,0x20U})set(a+off,Address{0x2d2d2d});
        set(a+0x28,std::uint32_t{0x29c77f8});set(a+0x2c,std::uint32_t{0x29c77f8});set(a+0x30,std::int32_t{-1});set(a+0x38,std::uint8_t{1});
        if(p.family==Family::Marriage)set(a+0x58,Address{15});return a;
    }
    Return invoke(Call kind,const Profile& p,Address a,bool mode)override {
        ++calls;if(before)before(kind,*this);
        if(!final_gate(kind==Call::ActionDestructor || kind==Call::CommandDestructor))return {};
        ++native_entries;
        if(throw_call && kind==fault_call)throw 5;
        if(fault && kind==fault_call)return {false,false,false,0,0xc0000005};
        Return r{};r.normal=true;
        switch(kind) {
        case Call::Factory:if(!null_factory)r.object=last_original=action(p);break;
        case Call::Setter:set(a+0x38,static_cast<std::uint8_t>(mode));if(p.family==Family::SpyNetwork && !mode)set(a+0x30,native_envoy);break;
        case Call::Full88:
            r.boolean=preview;
            if(p.family==Family::Marriage){const auto text=heap_string?allocate(129):a+0x40;set(text,std::uint8_t{'s'});set(text+1,std::uint8_t{'a'});set(text+2,std::uint8_t{0});
                if(heap_string)set(a+0x40,text);set(a+0x50,Address{2});set(a+0x58,Address{heap_string?128U:15U});}
            break;
        case Call::Wrapper:
            r.returned_same_slot=!bad_slot;if(null_wrapper)break;
            last_clone=action(p);
            // Synthetic engine emulates a native clone field-by-field. The adapter
            // never copies String32 storage or the original into a clone.
            for(unsigned off:{0x10U,0x18U,0x20U})set(last_clone+off,get<Address>(a+off));
            for(unsigned off:{0x28U,0x2cU,0x30U,0x34U,0x3cU})set(last_clone+off,get<std::uint32_t>(a+off));
            set(last_clone+0x38,get<std::uint8_t>(a+0x38));
            last_command=allocate(0x58);set(last_command,module()+0x1c814b0);set(last_command+8,std::uint32_t{0x165});
            set(last_command+0x30,Address{15});set(last_command+0x38,std::int32_t{-1});set(last_command+0x44,std::uint32_t{0x2934});set(last_command+0x48,Address{0xffff});
            set(last_command+0x50,clone_alias?a:clone_cmd_alias?last_command:last_clone);
            r.object=command_alias?a:last_command;break;
        case Call::Gate:r.boolean=gate;break;
        case Call::ActionDestructor:++deletes;memory.at(a).live=false;break;
        case Call::CommandDestructor:++deletes;memory.at(get<Address>(a+0x50)).live=false;memory.at(a).live=false;break;
        }
        if(after)after(kind,*this);return r;
    }
};
struct Guard: SyntheticGuard {
    PairStamp s=sample();std::uint64_t now=1;
    std::uint64_t clock()override{return now;}
    bool stamp(const Request&,PairStamp& out)override{out=s;return true;}
    bool cancellation(Family f,const PairStamp&,CancelObservation& c)override {
        c={};c.family=f;c.active=c.known_type=c.outgoing=c.reciprocal=c.mission_linked=true;c.actor=s.actor;c.target=s.target;
        c.actor_overlord={0x2d2d2d};c.target_overlord=s.actor;c.dependency=Dependency::Vassal;c.object=0x71000;c.mission=0x72000;c.revision=1;return true;
    }
};
OwnedId initialized(NativePairEngineDraft& e,const Profile& p,bool positive=true) {
    auto a=e.factory(p);CHECK(a.value>0 && (a.value&0xffffffffULL)<100);CHECK(e.initialize_owned(a,sample()));e.mode_setter(p,a,positive);
    if(p.family==Family::SpyNetwork && !positive)CHECK(e.bind_envoy_owned(a,0));return a;
}
struct Flow {OwnedId a,c,k;};
Flow wrapped(NativePairEngineDraft& e,const Profile& p,bool positive=true) {
    const auto a=initialized(e,p,positive);e.full88(p,a,nullptr,false);const auto w=e.wrapper(p,a);CHECK(w.returned_same_slot && w.command.value);
    CommandView v{};CHECK(e.command_view(w.command,v));return {a,w.command,v.clone};
}
template<class F>void rejects(F f,NativePairEngineDraft& e,Fake& p) {
    bool threw=false;try{f();}catch(...){threw=true;}CHECK(threw && e.diagnostics().frozen);
    const unsigned n=p.calls;try{e.factory(profiles()[0]);}catch(...){}CHECK(p.calls==n);CHECK(p.read_after_free==0);
}
void success() {
    for(const auto& p:profiles())for(bool mode:{false,true})for(bool allow:{false,true})for(bool gate:{false,true}) {
        Fake f;f.preview=allow;f.gate=gate;NativePairEngineDraft e(f);const auto a=initialized(e,p,mode);
        CHECK(e.full88(p,a,nullptr,false)==allow);const auto w=e.wrapper(p,a);CHECK(w.command.value && w.returned_same_slot);
        CHECK(e.command_gate(w.command)==gate);CommandView c{};e.command_view(w.command,c);CHECK(c.clone.value!=a.value && c.clone.value!=w.command.value);
        CHECK(e.destroy_action(p,a));CHECK(e.destroy_command(w.command));const auto d=e.diagnostics();
        CHECK(!d.frozen && d.live==0 && f.deletes==2 && f.read_after_free==0 && !d.submitted && !d.production_ready && !d.runtime_verified);
        CHECK(f.writes==9);
    }
    for(const auto& p:profiles())for(bool allowed:{false,true})for(bool gate:{false,true}) {
        Fake f;f.preview=allowed;f.gate=gate;Guard g;NativePairEngineDraft e(f);
        Request r{};r.action=static_cast<Action>(static_cast<unsigned>(p.family)*2);r.actor.bytes={'F','R','A'};r.target.bytes={'E','N','G'};
        auto result=preflight_no_send(r,g,e,100);CHECK(result.status==(allowed?(gate?Status::ModelComplete:Status::ModelGateRejected):Status::ModelPreviewRejected));
        CHECK(e.diagnostics().live==0 && !result.submitted && !e.diagnostics().frozen);
    }
    // Heap storage is conservatively unsupported until allocator ownership is proven.
    {Fake f;f.heap_string=true;NativePairEngineDraft e(f);auto a=initialized(e,profiles()[1]);
     rejects([&]{e.full88(profiles()[1],a,nullptr,false);},e,f);CHECK(f.deletes==0 && e.diagnostics().fault==Fault::Ownership);}
    for(std::int32_t envoy:{0,2147483647}){Fake q;q.native_envoy=envoy;NativePairEngineDraft a(q);auto id=a.factory(profiles()[4]);a.initialize_owned(id,sample());a.mode_setter(profiles()[4],id,false);a.bind_envoy_owned(id,envoy);ActionView view{};a.action_view(id,view);CHECK(view.envoy==envoy && q.writes==9);}
}
void identities() {
    for(int k=0;k<13;++k){Fake f;NativePairEngineDraft e(f);auto x=wrapped(e,profiles()[0]);
        rejects([&]{switch(k){case 0:{ActionView view{};e.action_view({f.last_original},view);break;}
        case 1:e.destroy_action(profiles()[0],x.k);break;case 2:e.destroy_action(profiles()[1],x.a);break;
        case 3:e.destroy_command(x.a);break;case 4:e.wrapper(profiles()[0],x.a);break;case 5:e.initialize_owned(x.a,sample());break;
        case 6:e.mode_setter(profiles()[0],x.a,false);break;case 7:e.full88(profiles()[0],x.a,nullptr,false);break;
        case 8:e.bind_envoy_owned(x.a,0);break;case 9:{auto p=profiles()[0];++p.token;e.factory(p);break;}
        case 10:f.set(f.last_original+8,std::uint32_t{0});e.destroy_action(profiles()[0],x.a);break;
        case 11:f.set(f.last_clone,f.module()+profiles()[1].vtable);e.destroy_command(x.c);break;
        case 12:f.set(f.last_command+0x50,f.last_original);e.destroy_command(x.c);break;}},e,f);CHECK(f.deletes==0);
    }
    for(int k=0;k<7;++k){Fake f;NativePairEngineDraft e(f);auto a=initialized(e,profiles()[0]);e.full88(profiles()[0],a,nullptr,false);
        if(k==0)f.command_alias=true;if(k==1)f.clone_alias=true;if(k==2)f.clone_cmd_alias=true;if(k==3)f.bad_slot=true;
        if(k>=4)f.after=[=](Call c,Fake& q){if(c==Call::Wrapper){if(k==4)q.memory.at(q.last_clone).priv=false;if(k==5)q.set(q.last_command+0x44,std::uint32_t{0});if(k==6)q.set(q.last_clone+0x2c,std::uint32_t{0});}};
        rejects([&]{e.wrapper(profiles()[0],a);},e,f);CHECK(f.deletes==0 && e.diagnostics().quarantined>=1);
        if(k==3)CHECK(e.diagnostics().unresolved_returns==1);
    }
}
void memory_and_failure() {
    for(int k=0;k<9;++k){Fake f;NativePairEngineDraft e(f);auto a=e.factory(profiles()[1]);
        if(k==0)f.fail_read=true;if(k==1)f.fail_write=true;if(k==2)f.short_write=true;if(k==3)f.memory.at(f.last_original).rw=false;
        if(k==4)f.memory.at(f.last_original).priv=false;if(k==5)f.fail_region=true;if(k==6)f.authority=false;if(k==7)f.throw_ready=true;
        if(k==8)f.memory.at(f.last_original).bytes.resize(0x40);
        rejects([&]{e.initialize_owned(a,sample());},e,f);CHECK(f.deletes==0);
    }
    for(int k=0;k<6;++k){Fake f;NativePairEngineDraft e(f);auto a=initialized(e,profiles()[1]);
        f.after=[=](Call c,Fake& q){if(c==Call::Full88){if(k==0)q.set(q.last_original+0x50,Address{129});if(k==1)q.set(q.last_original+0x58,Address{1});
            if(k==2)q.set(q.last_original+0x42,std::uint8_t{1});if(k==3)q.set(q.last_original+0x60,std::uint8_t{1});
            if(k==4){q.set(q.last_original+0x58,Address{128});q.set(q.last_original+0x40,Address{0x1234000});}if(k==5)q.set(q.last_original+0x39,std::uint8_t{1});}};
        rejects([&]{e.full88(profiles()[1],a,nullptr,false);},e,f);CHECK(f.deletes==0);
    }
    for(Call kind:{Call::Factory,Call::Setter,Call::Full88,Call::Wrapper,Call::Gate,Call::ActionDestructor,Call::CommandDestructor})for(bool cpp:{false,true}) {
        Fake f;NativePairEngineDraft e(f);const auto& p=profiles()[0];Flow x{};
        if(kind!=Call::Factory)x.a=e.factory(p);
        if(kind!=Call::Factory && kind!=Call::Setter){e.initialize_owned(x.a,sample());e.mode_setter(p,x.a,true);}
        if(kind==Call::Setter)e.initialize_owned(x.a,sample());
        if(kind==Call::Wrapper || kind==Call::Gate || kind==Call::ActionDestructor || kind==Call::CommandDestructor)e.full88(p,x.a,nullptr,false);
        if(kind==Call::Gate || kind==Call::CommandDestructor)x.c=e.wrapper(p,x.a).command;
        f.fault_call=kind;f.fault=!cpp;f.throw_call=cpp;
        rejects([&]{switch(kind){case Call::Factory:e.factory(p);break;case Call::Setter:e.mode_setter(p,x.a,true);break;case Call::Full88:e.full88(p,x.a,nullptr,false);break;
            case Call::Wrapper:e.wrapper(p,x.a);break;case Call::Gate:e.command_gate(x.c);break;case Call::ActionDestructor:e.destroy_action(p,x.a);break;case Call::CommandDestructor:e.destroy_command(x.c);break;}},e,f);CHECK(f.deletes==0);
    }
    {Fake f;NativePairEngineDraft e(f);f.after=[](Call,Fake& q){q.authority=false;};rejects([&]{e.factory(profiles()[0]);},e,f);CHECK(e.diagnostics().unresolved_returns==1);}
    {Fake f;NativePairEngineDraft e(f);f.after=[&](Call,Fake&){try{e.factory(profiles()[0]);}catch(...){};};rejects([&]{e.factory(profiles()[0]);},e,f);CHECK(f.calls==1);}
    {Fake f;NativePairEngineDraft e(f);auto x=wrapped(e,profiles()[0]);e.destroy_action(profiles()[0],x.a);const auto n=f.calls;rejects([&]{e.destroy_action(profiles()[0],x.a);},e,f);CHECK(f.calls==n);}
    {Fake f;NativePairEngineDraft e(f);f.null_factory=true;CHECK(!e.factory(profiles()[0]).value && !e.diagnostics().frozen);}
    {Fake f;NativePairEngineDraft e(f);auto a=initialized(e,profiles()[0]);e.full88(profiles()[0],a,nullptr,false);f.null_wrapper=true;CHECK(!e.wrapper(profiles()[0],a).command.value);e.destroy_action(profiles()[0],a);CHECK(!e.diagnostics().frozen);}
    {Fake f;NativePairEngineDraft e(f);const auto a=e.factory(profiles()[0]);ActionView v{};rejects([&]{for(unsigned n=0;n<1500;++n)e.action_view(a,v);},e,f);CHECK(e.diagnostics().reads==16384);}
}
void final_barriers() {
    {Fake f;NativePairEngineDraft e(f);auto a=e.factory(profiles()[4]);e.initialize_owned(a,sample());e.mode_setter(profiles()[4],a,false);
        rejects([&]{e.bind_envoy_owned(a,123);},e,f);CHECK(f.writes==9);}
    {Fake f;NativePairEngineDraft e(f);auto a=e.factory(profiles()[4]);e.initialize_owned(a,sample());f.native_envoy=-1;
        rejects([&]{e.mode_setter(profiles()[4],a,false);},e,f);CHECK(f.writes==9);}
    {Fake f,g;NativePairEngineDraft a(f),b(g);const auto x=a.factory(profiles()[0]),y=b.factory(profiles()[0]);CHECK(x.value!=y.value);ActionView v{};
        rejects([&]{b.action_view(x,v);},b,g);CHECK(!a.diagnostics().frozen);}
    {Fake f;NativePairEngineDraft e(f);const auto a=e.factory(profiles()[0]);f.read_hook=[](Fake&){throw 55;};ActionView v{};rejects([&]{e.action_view(a,v);},e,f);}
    for(unsigned mode=0;mode<3;++mode){Fake f;NativePairEngineDraft e(f);auto a=initialized(e,profiles()[0]);const auto n=f.native_entries;
        if(mode==0)f.read_hook=[](Fake& q){q.now=q.expires;};
        if(mode==1)f.ready_hook=[](Fake& q){q.now=q.expires;};
        if(mode==2)f.before=[](Call,Fake& q){q.work_identity=false;};
        rejects([&]{e.full88(profiles()[0],a,nullptr,false);},e,f);CHECK(f.native_entries==n && f.deletes==0);
    }
    for(unsigned at=1;at<=9;++at){Fake f;NativePairEngineDraft e(f);auto a=e.factory(profiles()[0]);f.write_hook=[=](Fake& q){if(q.writes==at)q.now=q.expires;};
        rejects([&]{e.initialize_owned(a,sample());},e,f);CHECK(f.writes==at && f.deletes==0 && f.native_entries==1);
    }
    for(unsigned mode=0;mode<3;++mode){Fake f;NativePairEngineDraft e(f);auto x=wrapped(e,profiles()[0]);f.now=1000;
        if(mode==0){CHECK(e.destroy_action(profiles()[0],x.a));CHECK(e.destroy_command(x.c));CHECK(!e.diagnostics().frozen);}
        if(mode==1){f.work_identity=false;rejects([&]{e.destroy_action(profiles()[0],x.a);},e,f);CHECK(f.deletes==0);}
        if(mode==2){f.highwater=1001;rejects([&]{e.destroy_command(x.c);},e,f);CHECK(f.deletes==0);}
    }
    {Fake f;NativePairEngineDraft e(f);Guard g;
     for(unsigned i=0;i<12;++i){if(i==9)continue;Request r{};r.action=static_cast<Action>(i);r.actor.bytes={'F','R','A'};r.target.bytes={'E','N','G'};
        const auto out=preflight_no_send(r,g,e,100);CHECK(out.status==Status::ModelComplete);}
     CHECK(e.diagnostics().live==0 && !e.diagnostics().frozen && e.diagnostics().issued==33);}
}
int main(){try{success();identities();memory_and_failure();final_barriers();std::cout<<"checks="<<checks<<" fake_only=true native_platform_linked=false native_calls=0 submitted=0\n";return 0;}
    catch(const std::exception& e){std::cerr<<"FAILED: "<<e.what()<<" checks="<<checks<<'\n';return 1;}
    catch(const NativeFault& f){std::cerr<<"UNEXPECTED fault="<<static_cast<unsigned>(f.reason)<<" checks="<<checks<<'\n';return 2;}}
