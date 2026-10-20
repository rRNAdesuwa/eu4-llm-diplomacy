#define main retained_port_main
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
    m.set(TRANSPORT,BASE+0x1d96178);m.set(TRANSPORT+0x30,Address{0});m.set(BASE+0x1d961a8,BASE+0x1580370);
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
    group("transport_vtable_slot_is_not_instance_data",[]{
        for(unsigned v=0;v<4;++v){SendFake f;NativePairEngineDraft e(f);auto env=prepared(f,e,profiles()[1]);BinderMemory m;
            for(const auto& pair:f.memory)for(std::size_t i=0;i<pair.second.bytes.size();++i)m.data[pair.first+i]=pair.second.bytes[i];context_fixture(m,env);
            if(v==0)m.set(TRANSPORT+0x30,Address{0});
            else if(v==1)m.set(TRANSPORT+0x30,Address{0x12345678});
            else if(v==2){m.set(BASE+0x1d961a8,BASE+0x1580371);m.set(TRANSPORT+0x30,BASE+0x1580370);}
            else {for(unsigned i=0;i<8;++i)m.data.erase(BASE+0x1d961a8+i);m.set(TRANSPORT+0x30,BASE+0x1580370);}
            SubmissionGuard guard({BASE,100,&m,BinderMemory::world,BinderMemory::read,BinderMemory::clock});auto a=guard.authority();SubmissionContext c{};
            CHECK(a.prepare(a.user,c)==(v<2));if(v<2)CHECK(a.final(a.user,c,env));
        }
    });
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
