#include "pair_component.h"
#include <cstring>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <vector>
using namespace v21pair;
#define CHECK(x) do {if (!(x)) throw std::runtime_error(#x);} while(false)
static_assert(!std::is_convertible<FullHandle,OwnedId>::value,"handle is not owned object");
static_assert(!std::is_convertible<std::uint64_t,FullHandle>::value,"no implicit full handle");
static_assert(!std::is_convertible<std::int32_t,Action>::value,"no public native token");

PairStamp stamp() {
    PairStamp s{};s.process_creation=111;s.session=222;s.module_pin=333;s.database=0x20000;s.game=0x30000;s.array=0x40000;
    s.actor_object=0x50000;s.target_object=0x60000;s.owner_thread=7;s.world_witness=8;s.count=512;s.date=0x2f20000;
    s.actor={0x0100007a00415246ULL};s.target={0x0100002e00474e45ULL};s.current_player=s.actor;s.effective_player=s.actor;return s;
}
struct Guard : SyntheticGuard {
    PairStamp s=::stamp();std::uint64_t now=1;unsigned samples=0,cancel_reads=0;
    bool missing=false,changed=false;Dependency dependency=Dependency::Vassal;
    std::function<void(Guard&)> on_stamp;
    std::uint64_t clock() override {return now;}
    bool stamp(const Request&,PairStamp& out) override {++samples;if(on_stamp) on_stamp(*this);out=s;return true;}
    bool cancellation(Family f,const PairStamp& x,CancelObservation& out) override {
        ++cancel_reads;if(missing) return false;
        out={};out.family=f;out.active=true;out.known_type=true;out.outgoing=true;out.reciprocal=true;out.mission_linked=true;
        out.actor=x.actor;out.target=x.target;out.actor_overlord={0x2d2d2d};out.target_overlord=x.actor;
        out.dependency=dependency;out.object=0x71000;out.mission=0x72000;out.revision=changed?2:1;return true;
    }
};
struct Engine : SyntheticEngine {
    Guard* guard{};std::map<std::uint64_t,ActionView> actions;std::map<std::uint64_t,CommandView> commands;
    std::vector<std::string> calls;std::uint64_t next=100;bool allow=true,gate=true,bad_default=false,alias=false,
        bad_wrapper=false,throw_preview=false,throw_wrapper=false,throw_dtor=false,bad_clone_string=false,
        bad_postpreview=false,expires_in_preview=false,rewind_in_preview=false,change_cancel=false;
    const Profile* last=nullptr;
    OwnedId factory(const Profile& p) override {
        calls.push_back("factory");last=&p;OwnedId id{++next};ActionView v{};v.size=p.size;v.vtable=p.vtable;
        if(bad_default)v.state=2;actions[id.value]=v;return id;
    }
    bool action_view(OwnedId id,ActionView& out) override {
        auto it=actions.find(id.value);if(it==actions.end())return false;out=it->second;return true;
    }
    bool initialize_owned(OwnedId id,const PairStamp& s) override {
        calls.push_back("initialize");auto& v=actions.at(id.value);v.actor=s.actor;v.controller=s.actor;v.target=s.target;
        v.primary=s.date;v.secondary=s.date;return true;
    }
    void mode_setter(const Profile& p,OwnedId id,bool mode) override {
        CHECK(actions.at(id.value).actor==guard->s.actor);CHECK(p.setter==last->setter);
        calls.push_back("setter");actions.at(id.value).value=mode?1:0;
    }
    bool bind_envoy_owned(OwnedId id,std::int32_t envoy) override {CHECK(envoy>=0);calls.push_back("envoy");actions.at(id.value).envoy=envoy;return true;}
    bool full88(const Profile& p,OwnedId id,std::nullptr_t text,bool option) override {
        CHECK(text==nullptr && !option);CHECK(p.full88!=0x4e9d00 && p.full88!=p.local80);calls.push_back("full88");
        if(throw_preview)throw std::runtime_error("preview uncertain");
        auto& v=actions.at(id.value);
        if(p.family==Family::Marriage) {v.text.length=7;v.text.capacity=15;v.text.first='r';}
        if(bad_postpreview)v.flag=1;
        if(expires_in_preview)guard->now=9999;
        if(rewind_in_preview)guard->now=0;
        if(change_cancel)guard->changed=true;
        return allow;
    }
    Wrapped wrapper(const Profile&,OwnedId original) override {
        calls.push_back("wrapper");if(throw_wrapper)throw std::runtime_error("wrapper uncertain");
        OwnedId clone{alias?original.value:++next};auto v=actions.at(original.value);
        if(last->family==Family::Marriage && !bad_clone_string)v.text={};
        actions[clone.value]=v;OwnedId command{++next};CommandView cv{};cv.clone=clone;commands[command.value]=cv;
        return {command,!bad_wrapper};
    }
    bool command_view(OwnedId id,CommandView& out) override {
        auto it=commands.find(id.value);if(it==commands.end())return false;out=it->second;return true;
    }
    bool command_gate(OwnedId) override {calls.push_back("gate");return gate;}
    bool destroy_action(const Profile& p,OwnedId id) override {
        calls.push_back("action_dtor");CHECK(p.destructor==(p.family==Family::Marriage?0x4ed5b0U:0x129450U));
        if(throw_dtor)throw std::runtime_error("destructor uncertain");return actions.erase(id.value)==1;
    }
    bool destroy_command(OwnedId id) override {
        calls.push_back("command_dtor");auto c=commands.at(id.value);CHECK(actions.erase(c.clone.value)==1);
        return commands.erase(id.value)==1;
    }
};
struct Memory final : SyntheticReadPort {
    std::map<std::uint64_t,std::uint8_t> bytes;std::size_t reads=0;std::vector<std::uint64_t> addresses;
    std::function<void(Memory&,std::uint64_t)> hook;
    template<class T>void put(std::uint64_t at,T value) {
        unsigned char buffer[sizeof(T)];std::memcpy(buffer,&value,sizeof(T));
        for(std::size_t i=0;i<sizeof(T);++i)bytes[at+i]=buffer[i];
    }
    bool read(std::uint64_t at,void* output,std::size_t size) override {
        ++reads;addresses.push_back(at);if(hook)hook(*this,at);auto* target=static_cast<unsigned char*>(output);
        for(std::size_t i=0;i<size;++i){auto it=bytes.find(at+i);if(it==bytes.end())return false;target[i]=it->second;}return true;
    }
};
constexpr std::uint64_t module=0x140000000ULL,records=0x80000,root=0x90000,holder=0xa0000,manager=0xb0000,
    begin=0xc0000,entry=0xd0000,mission=0xe0000,task=0xf0000,owner=0x100000,node=0x110000;
void spy_fixture(Memory& m,const PairStamp& s) {
    m.put(module+0x233d8d0,s.database);m.put(module+0x233fe78,s.game);m.put(s.database+0x118,s.array);m.put(s.database+0x124,s.count);
    m.put(s.array+122*8,s.actor_object);m.put(s.array+46*8,s.target_object);m.put(s.actor_object+0x20,s.actor.value);m.put(s.target_object+0x20,s.target.value);
    m.put(s.game+0x1dd0,s.date);m.put(s.game+0x1e60,s.current_player.value);m.put(s.game+0x7485,std::uint8_t{0});
    m.put(s.actor_object+0x1510,records);auto rec=records+46*0x48;m.put(rec,root);m.put(rec+8,s.actor.value);m.put(rec+0x10,s.target.value);m.put(rec+0x46,std::uint8_t{8});
    m.put(s.actor_object+0x1480,holder);m.put(holder+0x18,manager);m.put(manager+0x20,begin);m.put(manager+0x28,begin+8);
    m.put(begin,entry);m.put(entry+0x18,std::uint8_t{2});m.put(entry+0x10,mission);m.put(entry+0x44,std::int32_t{17});
    m.put(mission,module+0x1c4b2b8);m.put(mission+0xa0,task);m.put(mission+0x80,s.actor.value);m.put(mission+0x88,s.target.value);
    m.put(mission+0xa8,std::uint32_t{0x3378});m.put(mission+0x48,entry);m.put(mission+0x50,std::int32_t{17});
    m.put(task,module+0x1ce3ba0);m.put(task+0x20,s.target.value);m.put(task+0x18,s.actor.value);m.put(task+0x28,std::uint8_t{0});
    m.put(task+0x2c,std::int32_t{17});m.put(task+0x10,owner);
    m.put(s.target_object+0x14b0,owner);m.put(owner+0x4f0,node);m.put(owner+0x4f8,node);m.put(owner+0x500,std::uint32_t{1});
    m.put(node,task);m.put(node+8,std::uint64_t{0});m.put(node+0x10,std::uint64_t{0});m.put(node+0x18,std::uint8_t{0});
}
Request request(Action a) {Request r{};r.action=a;r.actor.bytes={'F','R','A'};r.target.bytes={'E','N','G'};return r;}
Result run(Action a,Guard& g,Engine& e,Memory* m=nullptr) {e.guard=&g;return preflight_no_send(request(a),g,e,1000,m,module);}
void group(const char* name,const std::function<void()>& test,unsigned& count) {test();++count;std::cout<<"PASS "<<name<<'\n';}
int main() {
    unsigned groups=0;
    try {
        group("all_12_typed_profiles_no_send",[&] {
            for(unsigned i=0;i<12;++i){Guard g;Engine e;Memory m;spy_fixture(m,g.s);auto r=run(static_cast<Action>(i),g,e,&m);
                CHECK(r.status==Status::ModelComplete);CHECK(!r.runtime_verified && !r.native_ready && !r.production_ready && !r.submitted);
                CHECK(e.actions.empty() && e.commands.empty());CHECK(e.calls.back()=="command_dtor");}
        },groups);
        group("public_names_tags_and_no_native_input",[] {
            Request r{};CHECK(make_request("curry_favors","FRA","ENG",r));CHECK(!make_request("0x3acc","FRA","ENG",r));
            CHECK(!make_request("build_spy_network","fra","ENG",r));CHECK(!make_request("curry_favors","FRA","FRA",r));
            CHECK(!make_request("curry_favors","FRA ","ENG",r));CHECK(profile(Action::Marriage).size==0x68);
            for(const auto& p:profiles())CHECK(p.full88!=0x4e9d00);
        },groups);
        group("factory_state2_not_generalized",[] {Guard g;Engine e;e.bad_default=true;auto r=run(Action::SpyNetwork,g,e);
            CHECK(r.status==Status::Frozen && r.quarantined_original.value);CHECK(e.calls.size()==1);},groups);
        group("normal_preview_false_cleanup_all_families",[] {for(unsigned i=0;i<6;++i){Guard g;Engine e;e.allow=false;
            auto r=run(static_cast<Action>(i*2),g,e);CHECK(r.status==Status::ModelPreviewRejected);CHECK(e.actions.empty());
            CHECK(e.commands.empty() && e.calls.back()=="action_dtor");}},groups);
        group("normal_gate_false_cleanup_clone_owned_by_command",[] {Guard g;Engine e;e.gate=false;auto r=run(Action::Curry,g,e);
            CHECK(r.status==Status::ModelGateRejected);CHECK(e.actions.empty() && e.commands.empty());},groups);
        group("exception_preview_freezes_without_dtor",[] {Guard g;Engine e;e.throw_preview=true;auto r=run(Action::Marriage,g,e);
            CHECK(r.status==Status::Frozen && r.quarantined_original.value);CHECK(e.calls.back()=="full88");},groups);
        group("exception_wrapper_no_guessed_clone_or_command",[] {Guard g;Engine e;e.throw_wrapper=true;auto r=run(Action::Guarantee,g,e);
            CHECK(r.status==Status::Frozen);CHECK(e.calls.back()=="wrapper");CHECK(r.quarantined_command.value==0);},groups);
        group("alias_and_wrong_wrapper_return_freeze",[] {for(unsigned i=0;i<2;++i){Guard g;Engine e;e.alias=i==0;e.bad_wrapper=i==1;
            auto r=run(Action::Improve,g,e);CHECK(r.status==Status::Frozen);CHECK(e.calls.back()=="wrapper");}},groups);
        group("marriage_clone_resets_preview_string",[] {Guard g;Engine e;e.bad_clone_string=true;auto r=run(Action::Marriage,g,e);
            CHECK(r.status==Status::Frozen);CHECK(e.calls.back()=="wrapper");CHECK(r.quarantined_clone.value!=0);},groups);
        group("known_cleanup_can_exceed_ttl_new_work_cannot",[] {
            Guard g;Engine e;e.allow=false;e.expires_in_preview=true;CHECK(run(Action::Marriage,g,e).status==Status::ModelPreviewRejected);CHECK(e.actions.empty());
            Guard g2;Engine e2;e2.expires_in_preview=true;CHECK(run(Action::Marriage,g2,e2).status==Status::Frozen);CHECK(e2.calls.back()=="full88");
        },groups);
        group("clock_rewind_and_stamp_change_freeze",[] {
            Guard g;Engine e;e.allow=false;e.rewind_in_preview=true;CHECK(run(Action::Curry,g,e).status==Status::Frozen);CHECK(e.calls.back()=="full88");
            Guard g2;Engine e2;g2.on_stamp=[&](Guard& x){if(!e2.calls.empty())x.s.session=999;};CHECK(run(Action::Curry,g2,e2).status==Status::Frozen);
        },groups);
        group("cancel_missing_and_wrong_dependency_no_factory",[] {
            for(auto d:{Dependency::Appanage,Dependency::Union}){Guard g;Engine e;g.dependency=d;CHECK(run(Action::CancelVassal,g,e).status==Status::PreconditionRejected);CHECK(e.calls.empty());}
            Guard g;Engine e;g.missing=true;CHECK(run(Action::StopCurry,g,e).status==Status::PreconditionRejected);CHECK(e.calls.empty());
        },groups);
        group("cancel_fingerprint_changed_after_preview_freezes",[] {Guard g;Engine e;e.change_cancel=true;auto r=run(Action::StopImprove,g,e);
            CHECK(r.status==Status::Frozen);CHECK(e.calls.back()=="full88");},groups);
        group("full_generation_and_request_identity",[] {
            Guard g;Engine e;g.s.effective_player.value^=0x0100000000000000ULL;CHECK(run(Action::Curry,g,e).status==Status::Invalid);CHECK(e.calls.empty());
            Guard g2;Engine e2;g2.s.target.value=0x0100002e00524f50ULL;CHECK(run(Action::Curry,g2,e2).status==Status::Invalid);CHECK(e2.calls.empty());
        },groups);
        group("destructor_uncertain_freezes_no_second_cleanup",[] {Guard g;Engine e;e.throw_dtor=true;auto r=run(Action::Curry,g,e);
            CHECK(r.status==Status::Frozen);CHECK(e.calls.back()=="action_dtor");CHECK(r.quarantined_command.value!=0);},groups);
        group("spy_2pass_and_immediate_generation_recheck",[] {
            Guard g;Memory m;spy_fixture(m,g.s);SpyBinding b{};CHECK(bind_spy_two_pass(m,module,g.s,b));CHECK(b.envoy==17);
            m.put(task+0x20,g.s.target.value^0x0100000000000000ULL);CHECK(!recheck_spy(m,module,g.s,b));CHECK(m.reads<300);
        },groups);
        group("spy_duplicate_entry_rejected",[] {
            Guard g;Memory m;spy_fixture(m,g.s);m.put(manager+0x28,begin+16);m.put(begin+8,entry);SpyBinding b{};CHECK(!bind_spy_once(m,module,g.s,b));
        },groups);
        group("spy_negative_int32_envoy_and_mismatched_backref",[] {
            Guard g;Memory m;spy_fixture(m,g.s);m.put(entry+0x44,std::int32_t{-1});SpyBinding b{};CHECK(!bind_spy_once(m,module,g.s,b));
            spy_fixture(m,g.s);m.put(mission+0x48,entry+8);CHECK(!bind_spy_once(m,module,g.s,b));
        },groups);
        group("spy_removed_node_never_follows_stale_task",[] {
            Guard g;Memory m;spy_fixture(m,g.s);auto dead=node+0x100;m.put(owner+0x4f0,dead);m.put(owner+0x500,std::uint32_t{2});
            m.put(dead+8,std::uint64_t{0});m.put(dead+0x10,node);m.put(dead+0x18,std::uint8_t{1});m.put(node+8,dead);
            // dead+0 intentionally absent; any dereference fails.
            SpyBinding b{};CHECK(bind_spy_two_pass(m,module,g.s,b));for(auto a:m.addresses)CHECK(a!=dead);
        },groups);
        group("spy_two_pass_change_and_root_after_graph",[] {
            Guard g;Memory m;spy_fixture(m,g.s);unsigned hits=0;
            m.hook=[&](Memory& x,std::uint64_t a){if(a==entry+0x44 && ++hits==2)x.put(entry+0x44,std::int32_t{18});};
            SpyBinding b{};CHECK(!bind_spy_two_pass(m,module,g.s,b));
            Memory m2;spy_fixture(m2,g.s);m2.hook=[&](Memory& x,std::uint64_t a){if(a==node+0x10)x.put(g.s.game+0x1dd0,g.s.date+1);};
            CHECK(!bind_spy_once(m2,module,g.s,b));
        },groups);
        group("spy_bounds_cycle_and_unknown_type_before_derived",[] {
            Guard g;Memory m;spy_fixture(m,g.s);SpyBinding b{};m.put(manager+0x28,begin+257*8);CHECK(!bind_spy_once(m,module,g.s,b));
            spy_fixture(m,g.s);m.put(node+0x10,node);CHECK(!bind_spy_once(m,module,g.s,b));
            spy_fixture(m,g.s);m.put(task,module+0x1234);m.bytes.erase(task+0x20);CHECK(!bind_spy_once(m,module,g.s,b));
            for(auto a:m.addresses)CHECK(a!=0xffffffffffffffffULL);
        },groups);
        group("spy_final_binding_change_prevents_preview",[] {
            Guard g;Engine e;Memory m;spy_fixture(m,g.s);unsigned reads=0;
            m.hook=[&](Memory& x,std::uint64_t a){if(a==entry+0x44 && ++reads==4)x.put(entry+0x44,std::int32_t{19});};
            auto r=run(Action::StopSpyNetwork,g,e,&m);CHECK(r.status==Status::Frozen);
            for(const auto& call:e.calls)CHECK(call!="full88");
        },groups);
        group("equal_snapshots_do_not_exclude_ABA_counterexample",[] {
            Guard g;Memory m;spy_fixture(m,g.s);unsigned mutations=0;
            m.hook=[&](Memory& x,std::uint64_t a){if(a==entry+0x44){x.put(task+0x20,g.s.target.value^0x0100000000000000ULL);
                ++mutations;x.put(task+0x20,g.s.target.value);++mutations;}};
            SpyBinding b{};CHECK(bind_spy_two_pass(m,module,g.s,b));CHECK(recheck_spy(m,module,g.s,b));CHECK(mutations==6);
            // Changed/restored generation is not observed by equal bounded passes.
        },groups);
        group("signed_int32_upper_bound_and_address_overflow",[] {
            Guard g;Memory m;spy_fixture(m,g.s);auto max=std::numeric_limits<std::int32_t>::max();
            m.put(entry+0x44,max);m.put(mission+0x50,max);m.put(task+0x2c,max);SpyBinding b{};
            CHECK(bind_spy_two_pass(m,module,g.s,b) && b.envoy==max);auto reads=m.reads;
            CHECK(!bind_spy_once(m,std::numeric_limits<std::uint64_t>::max()-8,g.s,b));CHECK(reads==m.reads);
            auto wrong=g.s;wrong.count=4097;CHECK(!bind_spy_once(m,module,wrong,b));CHECK(reads==m.reads);
        },groups);
        std::cout<<"groups="<<groups<<" native_calls=0 submitted=0 production_ready=false\n";return 0;
    } catch(const std::exception& e) {std::cerr<<"FAIL after "<<groups<<" groups: "<<e.what()<<'\n';return 1;}
}
