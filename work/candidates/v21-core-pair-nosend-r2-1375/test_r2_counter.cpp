// Reuse the retained synthetic fixture types; counter conditions and expected
// refusal are independent R2 regressions, not the sealed reviewer's bug outputs.
#define main legacy_test_entrypoint
#include "test_pair_component.cpp"
#undef main
#include <algorithm>
bool entered(const Engine& e,const std::string& name) {
    return std::find(e.calls.begin(),e.calls.end(),name)!=e.calls.end();
}
struct FaultEngine : Engine {
    enum class Damage {None,WrapperVtable,GateString,NullString,DtorCommandVtable,DtorCloneAlias,WrapperString};
    Damage damage{Damage::None};OwnedId original{};bool null_late=false;
    OwnedId factory(const Profile& p) override {original=Engine::factory(p);return original;}
    Wrapped wrapper(const Profile& p,OwnedId id) override {
        if(damage==Damage::NullString || null_late) {
            calls.push_back("wrapper");
            if(damage==Damage::NullString)actions.at(id.value).text.storage_valid=false;
            if(null_late)guard->now=2000;
            return {{},true};
        }
        auto result=Engine::wrapper(p,id);
        if(damage==Damage::WrapperVtable)actions.at(id.value).vtable++;
        if(damage==Damage::WrapperString)actions.at(id.value).text.storage_valid=false;
        return result;
    }
    bool command_gate(OwnedId id) override {
        auto result=Engine::command_gate(id);
        if(damage==Damage::GateString)actions.at(original.value).text.capacity=0;
        return result;
    }
    bool destroy_action(const Profile& p,OwnedId id) override {
        auto result=Engine::destroy_action(p,id);
        for(auto& pair:commands) {
            if(damage==Damage::DtorCommandVtable)pair.second.vtable++;
            if(damage==Damage::DtorCloneAlias)pair.second.clone=original;
        }
        return result;
    }
};
int main() {
    unsigned checks=0;
    try {
        const std::array<std::pair<const char*,const char*>,6> work{{
            {"","factory"},{"factory","initialize"},{"initialize","setter"},
            {"setter","full88"},{"full88","wrapper"},{"wrapper","gate"}}};
        for(const auto& stage:work)for(unsigned variant=0;variant<2;++variant) {
            Guard g;Engine e;unsigned stamp_reads=0;
            g.on_stamp=[&](Guard& current) {
                const std::string phase=e.calls.empty()?"":e.calls.back();
                if(phase==stage.first && ++stamp_reads==(phase.empty()?7U:2U))current.now=variant==0?1000:0;
            };
            auto result=run(Action::Curry,g,e);
            CHECK(!entered(e,stage.second));CHECK(result.status==Status::Frozen || result.status==Status::PreconditionRejected);
            CHECK(!result.submitted && !result.runtime_verified);
            ++checks;std::cout<<"PASS final_stamp_clock "<<stage.second<<' '<<variant<<'\n';
        }
        for(const char* phase:{"envoy","full88"})for(unsigned variant=0;variant<3;++variant) {
            Guard g;Engine e;Memory m;spy_fixture(m,g.s);unsigned roots=0;
            m.hook=[&](Memory&,std::uint64_t a) {
                if(!e.calls.empty() && e.calls.back()==phase && a==g.s.game+0x7485 && ++roots==2) {
                    if(variant==0)g.now=1000;
                    if(variant==1)g.now=0;
                    if(variant==2)g.s.session++;
                }
            };
            auto result=run(Action::StopSpyNetwork,g,e,&m);
            CHECK(result.status==Status::Frozen);
            CHECK(!entered(e,std::string(phase)=="envoy"?"full88":"wrapper"));
            ++checks;std::cout<<"PASS final_spy_reader "<<phase<<' '<<variant<<'\n';
        }
        for(auto damage:{FaultEngine::Damage::WrapperVtable,FaultEngine::Damage::GateString,
            FaultEngine::Damage::NullString,FaultEngine::Damage::DtorCommandVtable,
            FaultEngine::Damage::DtorCloneAlias,FaultEngine::Damage::WrapperString}) {
            Guard g;FaultEngine e;e.damage=damage;auto result=run(Action::Marriage,g,e);
            CHECK(result.status==Status::Frozen);CHECK(!entered(e,"command_dtor"));
            const bool dtor_mutation=damage==FaultEngine::Damage::DtorCommandVtable || damage==FaultEngine::Damage::DtorCloneAlias;
            CHECK(entered(e,"action_dtor")==dtor_mutation);
            if(dtor_mutation)CHECK(!result.quarantined_original.value && result.quarantined_command.value && result.quarantined_clone.value);
            else CHECK(result.quarantined_original.value);
            ++checks;std::cout<<"PASS destruction_fresh_fields "<<static_cast<unsigned>(damage)<<'\n';
        }
        for(const char* phase:{"gate","action_dtor"}) {
            Guard g;Engine e;unsigned stamps=0;
            g.on_stamp=[&](Guard& current) {if(!e.calls.empty() && e.calls.back()==phase && ++stamps==2)current.now=0;};
            auto result=run(Action::Curry,g,e);CHECK(result.status==Status::Frozen);
            CHECK(!entered(e,std::string(phase)=="gate"?"action_dtor":"command_dtor"));
            ++checks;std::cout<<"PASS cleanup_final_stamp_rollback "<<phase<<'\n';
        }
        for(const char* phase:{"gate","action_dtor"}) {
            Guard g;Engine e;unsigned stamps=0;
            g.on_stamp=[&](Guard& current) {if(!e.calls.empty() && e.calls.back()==phase && ++stamps==2)current.now=1000;};
            auto result=run(Action::Curry,g,e);CHECK(result.status==Status::ModelComplete);
            CHECK(entered(e,"action_dtor") && entered(e,"command_dtor") && e.actions.empty() && e.commands.empty());
            ++checks;std::cout<<"PASS cleanup_final_stamp_expired_allowed "<<phase<<'\n';
        }
        {Guard g;Engine e;e.allow=false;e.expires_in_preview=true;auto result=run(Action::Marriage,g,e);
            CHECK(result.status==Status::ModelPreviewRejected && e.actions.empty());++checks;std::cout<<"PASS false_late_cleanup\n";}
        {Guard g;Engine e;e.gate=false;g.on_stamp=[&](Guard& current){if(!e.calls.empty() && e.calls.back()=="gate")current.now=2000;};
            auto result=run(Action::Marriage,g,e);CHECK(result.status==Status::ModelGateRejected && e.actions.empty() && e.commands.empty());
            ++checks;std::cout<<"PASS gate_false_late_cleanup\n";}
        {Guard g;FaultEngine e;e.null_late=true;auto result=run(Action::Marriage,g,e);
            CHECK(result.status==Status::Invalid && entered(e,"action_dtor") && e.actions.empty() && e.commands.empty());
            ++checks;std::cout<<"PASS normal_null_wrapper_late_cleanup\n";}
        {Guard g;Engine e;e.alias=true;auto result=run(Action::Curry,g,e);CHECK(result.status==Status::Frozen && e.calls.back()=="wrapper");
            ++checks;std::cout<<"PASS alias_ownership_freeze\n";}
        {Guard g;Engine e;e.throw_wrapper=true;auto result=run(Action::Curry,g,e);CHECK(result.status==Status::Frozen && e.calls.back()=="wrapper");
            ++checks;std::cout<<"PASS wrapper_exception_freeze\n";}
        for(auto family:{Family::Vassal,Family::Marriage,Family::Improve,Family::Guarantee,Family::Curry}) {
            Guard g;CancelObservation observed{};CHECK(g.cancellation(family,g.s,observed));
            CHECK(cancel_matches(profiles().at(static_cast<unsigned>(family)),g.s,observed));
            std::swap(observed.actor,observed.target);CHECK(!cancel_matches(profiles().at(static_cast<unsigned>(family)),g.s,observed));
            ++checks;std::cout<<"PASS private_cancellation_role "<<static_cast<unsigned>(family)<<'\n';
        }
        CHECK(checks==38);std::cout<<"r2_counterchecks="<<checks<<" rejected_late_work=true fresh_cleanup=true native_calls=0\n";return 0;
    }catch(const std::exception& ex){std::cerr<<"FAIL after "<<checks<<" counterchecks: "<<ex.what()<<'\n';return 1;}
}
