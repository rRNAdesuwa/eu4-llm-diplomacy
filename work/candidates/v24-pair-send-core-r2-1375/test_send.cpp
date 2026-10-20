#define main retained_no_send_main
#include "test_pair_component.cpp"
#undef main
#include "pair_send.h"
#include <algorithm>
struct Sender final:TransferPort {
    Guard& g;Engine& e;unsigned intents{},submits{};bool durable=true,throws=false;
    TransferReturn ret{true,true,true,0};std::function<void()> in_intent;
    Sender(Guard& a,Engine& b):g(a),e(b){}
    bool dispatch_intent(const Request&,const PairStamp& s,OwnedId c,OwnedId clone) override {
        ++intents;CHECK(s==g.s);CHECK(e.commands.at(c.value).clone==clone);
        CHECK(e.actions.size()==1); // original has already been deleted
        if(in_intent)in_intent();return durable;
    }
    TransferReturn submit_owned(OwnedId c) override {
        ++submits;CHECK(e.commands.count(c.value)==1);CHECK(e.calls.back()=="action_dtor");
        if(ret.slot_consumed){auto clone=e.commands.at(c.value).clone;e.commands.erase(c.value);e.actions.erase(clone.value);}
        if(throws)throw std::runtime_error("uncertain transfer");return ret;
    }
};
SendResult send(Action action,SendCore& c,Guard& g,Engine& e,Sender& s,Memory* m=nullptr) {
    e.guard=&g;return c.invoke(request(action),g,e,s,1000,m,module);
}
int main(){unsigned n=0;try{
    CHECK(retained_no_send_main()==0);
    group("all_twelve_normal_consumed_once",[]{for(unsigned i=0;i<12;++i){SendCore c;Guard g;Engine e;Sender s(g,e);Memory m;spy_fixture(m,g.s);
        auto r=send(static_cast<Action>(i),c,g,e,s,&m);CHECK(r.status==Status::ModelComplete && r.submitted);
        CHECK(r.transfer==TransferOutcome::Dispatched && s.submits==1 && s.intents==1);
        CHECK(e.actions.empty() && e.commands.empty());CHECK(e.calls.back()=="action_dtor");
        CHECK(std::find(e.calls.begin(),e.calls.end(),"command_dtor")==e.calls.end());
        auto count=e.calls.size();auto again=send(static_cast<Action>(i),c,g,e,s,&m);
        CHECK(again.status==Status::Frozen && !again.submitted && e.calls.size()==count && s.submits==1);
        CHECK(!r.production_ready && !r.runtime_verified && !r.native_ready);
    }},n);
    group("normal_refusals_never_submit",[]{for(unsigned i=0;i<12;++i){for(unsigned v=0;v<2;++v){SendCore c;Guard g;Engine e;Sender s(g,e);Memory m;spy_fixture(m,g.s);
        e.allow=v!=0;e.gate=false;auto r=send(static_cast<Action>(i),c,g,e,s,&m);
        CHECK(r.status==(v?Status::ModelGateRejected:Status::ModelPreviewRejected));CHECK(!r.submitted && s.submits==0 && s.intents==0);
        CHECK(e.commands.empty() && e.actions.empty());
    }}},n);
    group("all_unknown_transfer_forms_no_local_cleanup",[]{for(unsigned normal=0;normal<2;++normal)for(unsigned value=0;value<2;++value)for(unsigned consumed=0;consumed<2;++consumed){
        if(normal && value && consumed)continue;SendCore c;Guard g;Engine e;Sender s(g,e);s.ret={normal!=0,value!=0,consumed!=0,0};
        auto r=send(Action::Improve,c,g,e,s);CHECK(r.status==Status::Frozen && r.transfer==TransferOutcome::Unknown);
        CHECK(!r.submitted && s.submits==1 && e.calls.back()=="action_dtor");
        CHECK((e.commands.empty())==(consumed!=0));CHECK(r.quarantined_command.value && r.quarantined_clone.value);
    }},n);
    group("native_exception_return_no_guessed_cleanup",[]{SendCore c;Guard g;Engine e;Sender s(g,e);s.ret.exception=0xc0000005;
        auto r=send(Action::Marriage,c,g,e,s);CHECK(r.status==Status::Frozen && !r.submitted && r.submit_exception==0xc0000005);
        CHECK(s.submits==1 && e.calls.back()=="action_dtor");},n);
    group("throw_before_or_after_consumption",[]{for(bool consumed:{false,true}){SendCore c;Guard g;Engine e;Sender s(g,e);s.throws=true;s.ret.slot_consumed=consumed;
        auto r=send(Action::Curry,c,g,e,s);CHECK(r.status==Status::Frozen && r.transfer==TransferOutcome::Unknown && !r.submitted);
        CHECK(s.submits==1 && e.calls.back()=="action_dtor");}},n);
    group("failed_durable_intent_no_transfer",[]{SendCore c;Guard g;Engine e;Sender s(g,e);s.durable=false;auto r=send(Action::SpyNetwork,c,g,e,s);
        CHECK(r.status==Status::Frozen && s.intents==1 && s.submits==0 && !r.submit_entered);CHECK(e.commands.size()==1 && e.actions.size()==1);},n);
    group("intent_latency_rollback_and_world_mutation",[]{for(unsigned v=0;v<3;++v){SendCore c;Guard g;Engine e;Sender s(g,e);
        s.in_intent=[&]{if(v==0)g.now=1000;else if(v==1)g.now=0;else ++g.s.date;};auto r=send(Action::Improve,c,g,e,s);
        CHECK(r.status==Status::Frozen && s.intents==1 && s.submits==0 && !r.submit_entered);CHECK(e.commands.size()==1);
    }},n);
    group("intent_mutates_each_command_clone_field",[]{for(unsigned v=0;v<4;++v){SendCore c;Guard g;Engine e;Sender s(g,e);
        s.in_intent=[&]{auto& cmd=e.commands.begin()->second;auto& clone=e.actions.at(cmd.clone.value);
            if(v==0)cmd.token=0;else if(v==1)clone.vtable=0;else if(v==2)clone.target.value^=0x100000000000000ULL;else cmd.clone={99999};};
        auto r=send(Action::Marriage,c,g,e,s);CHECK(r.status==Status::Frozen && s.submits==0 && e.calls.back()=="action_dtor");
    }},n);
    group("cancel_revision_changed_in_intent",[]{SendCore c;Guard g;Engine e;Sender s(g,e);s.in_intent=[&]{g.changed=true;};
        auto r=send(Action::StopImprove,c,g,e,s);CHECK(r.status==Status::Frozen && s.submits==0);},n);
    group("missing_cancel_before_native",[]{SendCore c;Guard g;Engine e;Sender s(g,e);g.missing=true;
        auto r=send(Action::CancelVassal,c,g,e,s);CHECK(r.status==Status::PreconditionRejected && e.calls.empty() && s.submits==0);},n);
    std::cout<<"send_groups="<<n<<" native_game_called=false production_ready=false\n";return 0;
}catch(const std::exception& x){std::cerr<<x.what()<<'\n';return 1;}}
