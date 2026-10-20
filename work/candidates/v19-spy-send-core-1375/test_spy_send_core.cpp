#include "mock_support.inc"

Result start(Mock& m) { auto r=m.run(Operation::begin);check(r.accepted_call&&r.audit_complete,"batch claimed once");++m.host.frame_id;return r; }
Result item(Mock& m) { auto r=m.run(Operation::next_item);++m.host.frame_id;return r; }
Result health(Mock& m) { auto r=m.run(Operation::later_health);++m.host.frame_id;return r; }
void denied_flags(const Result& r) {
    check(!r.retry_allowed&&!r.runtime_verified&&!r.production_ready&&!r.effect_verified&&!r.strict_sp_verified&&!r.epoch_verified,"no runtime/effect/production grant");
}
void stable_matrix() {
    for(unsigned mode=0;mode<4;++mode) {
        Mock m;start(m);
        for(unsigned i=0;i<5;++i) {
            m.allow_preview=mode!=0 && (mode!=3 || i%3!=0);
            m.allow_gate=mode!=1 && (mode!=3 || i%3!=1);
            const auto r=item(m);const auto wanted=!m.allow_preview?Outcome::full_preview_rejected:!m.allow_gate?Outcome::command_gate_rejected:Outcome::dispatched;
            check(r.accepted_call&&r.audit_complete&&r.state==State::awaiting_health&&r.completed==i,"normal item awaits later health");
            check(r.current_item.family==i&&r.current_item.ordinal==i+1&&r.current_item.token==TOKENS[i]&&r.current_item.current,"fixed family item identity");
            check(r.current_item.outcome==wanted,"false gates and dispatched distinct");
            check(r.current_item.preview_observed&&r.current_item.preview_allowed==m.allow_preview,"full88 result preserved");
            check(r.current_item.gate_observed==m.allow_preview,"no wrapper gate after full false");
            check(r.current_item.submit_entered==(wanted==Outcome::dispatched),"enter only two allowed gates");
            check(!r.current_item.has_local_original&&!r.current_item.has_local_clone&&!r.current_item.has_local_command,"all local ownership resolved");
            if(wanted==Outcome::dispatched)check(r.current_item.submit_value_observed&&r.current_item.submit_value&&r.current_item.slot_observed&&r.current_item.slot_consumed,"strict normal submit acknowledgement");
            else check(!r.current_item.submit_value_observed&&!r.current_item.slot_observed,"no fabricated submit observation");
            denied_flags(r);const auto h=health(m);check(h.accepted_call&&h.completed==i+1&&!h.current_item.current&&h.completed_outcomes[i]==wanted,"later owner health commits row");
            check(m.live()==0&&m.abi_errors==0&&m.invalid_reads==0&&m.invalid_writes==0,"normal exact owned cleanup");
        }
        const auto factories=m.factory_calls;auto again=m.run(Operation::next_item);
        check(again.freeze_session&&m.factory_calls==factories,"completed batch never rearmed");
        check(m.claims==6&&m.factory_calls==5&&m.preview_calls==5,"one batch and five item claims");
        check(std::find(m.resolutions.begin(),m.resolutions.end(),0x4e9d00)==m.resolutions.end(),"generic action preview never substitutes family88");
        for(auto preview:PREVIEWS)check(std::count(m.resolutions.begin(),m.resolutions.end(),preview)==1,"full family preview once");
    }
}
void failure_matrix() {
    for(auto fault:{Fault::factory_null,Fault::factory_sentinel,Fault::factory_fields,Fault::factory_throw,Fault::preview_throw,
        Fault::wrapper_throw,Fault::wrapper_return,Fault::wrapper_null,Fault::wrapper_alias,Fault::wrapper_clone_alias,
        Fault::wrapper_fields,Fault::gate_throw,Fault::gate_consumes,Fault::dtor_throw,Fault::original_dtor_consumes_command,
        Fault::root_after_preview,Fault::clock_back_after_preview,Fault::write_fail,Fault::resolver_null,Fault::reenter_resolver}) {
        Mock m;start(m);m.fault=fault;
        const auto r=item(m);check(r.freeze_session&&!r.accepted_call&&r.reason!=Reason::none,"allocation/layout/call failure terminal");denied_flags(r);
        const auto factories=m.factory_calls,actions=m.action_dtors,commands=m.command_dtors,submits=m.submit_calls;
        const auto again=item(m);check(again.freeze_session&&m.factory_calls==factories&&m.action_dtors==actions&&m.command_dtors==commands&&m.submit_calls==submits,"unknown never retried or cleaned");
        check(m.abi_errors==0&&m.invalid_writes==0,"fault never foreign call/free");
        if(fault==Fault::factory_throw||fault==Fault::preview_throw||fault==Fault::wrapper_throw||fault==Fault::gate_throw||fault==Fault::dtor_throw)
            check(r.exception_code!=0&&r.ownership_uncertain,"SEH explicitly unknown");
    }
}
void transfer_unknown() {
    for(unsigned prefix=0;prefix<5;++prefix) {
        for(auto fault:{Fault::submit_throw,Fault::submit_false_consumed,Fault::submit_true_unconsumed,Fault::submit_false_unconsumed}) {
            Mock m;start(m);
            for(unsigned i=0;i<prefix;++i) { check(item(m).accepted_call,"prior dispatch");check(health(m).accepted_call,"prior health"); }
            m.fault=fault;const auto before_actions=m.action_dtors,before_commands=m.command_dtors,before_submits=m.submit_calls;
            auto r=item(m);
            check(r.freeze_session&&!r.accepted_call&&r.completed==prefix,"unknown keeps completed rows separate");
            check(r.current_item.current&&r.current_item.family==prefix&&r.current_item.outcome==Outcome::dispatch_unknown,"unknown current family preserved");
            check(r.current_item.submit_entered&&!r.current_item.has_local_original&&!r.current_item.has_local_command&&!r.current_item.has_local_clone,"entry always relinquishes local ownership");
            check(m.submit_calls==before_submits+1&&m.action_dtors==before_actions+1&&m.command_dtors==before_commands,"only original destroyed before transfer");
            check(r.current_item.submit_returned==(fault!=Fault::submit_throw),"normal return distinguish SEH");
            check(r.current_item.slot_observed==(fault!=Fault::submit_throw)&&r.current_item.submit_value_observed==(fault!=Fault::submit_throw),"unknown nullable record remains unobserved on exception");
            const auto reads=m.invalid_reads;const auto again=health(m);
            check(again.freeze_session&&again.current_item.submit_entered&&again.current_item.family==prefix,"frozen laterhealth retains current item");
            check(m.submit_calls==before_submits+1&&m.command_dtors==before_commands&&m.invalid_reads==reads,"no read/free/resend after transfer");denied_flags(r);
        }
    }
}
void ordering_ttl_identity() {
    { Mock m;auto r=item(m);check(r.freeze_session&&m.claims==0&&m.factory_calls==0,"no item before batch"); }
    { Mock m;start(m);auto r=m.run(Operation::begin);check(r.freeze_session&&m.claims==1,"batch cannot claim twice"); }
    { Mock m;start(m);auto r=item(m);check(r.accepted_call,"first item");r=item(m);check(r.freeze_session&&m.factory_calls==1,"requires later independent health"); }
    { Mock m;start(m);auto r=m.run(Operation::next_item);check(r.accepted_call,"first before same frame health");r=m.run(Operation::later_health);check(r.freeze_session&&r.completed==0,"same frame health denied"); }
    for(unsigned kind=0;kind<8;++kind) {
        Mock m;start(m);
        if(kind==0)++m.host.identity.creation_filetime;
        if(kind==1)m.host.identity.session[0]='4';
        if(kind==2)m.host.request_sequence=5;
        if(kind==3)m.host.same_session_preflight_verified=false;
        if(kind==4)++m.host.expires_uptime_ms;
        if(kind==5)m.mem<std::uint64_t>(ENG+0x20,ENG_HANDLE+(1ULL<<48));
        if(kind==6)m.mem<std::uintptr_t>(0x200070000ULL+0x370,0x200080008ULL);
        if(kind==7)++m.host.expected_game_thread;
        auto r=item(m);check(r.freeze_session&&m.factory_calls==0,"fixed session/world/thread identity");
    }
    { Mock m;start(m);m.now=m.host.expires_uptime_ms;auto r=item(m);check(r.freeze_session&&m.factory_calls==0,"expiry equality before work"); }
    for(bool full_false:{true,false}) {
        Mock m;start(m);m.allow_preview=!full_false;m.allow_gate=false;m.fault=Fault::expire_after_preview;
        auto r=item(m);
        if(full_false) { check(r.accepted_call&&m.live()==0,"known false cleanup may cross TTL");check(health(m).accepted_call,"later health may cross TTL");check(item(m).freeze_session,"next work after TTL forbidden"); }
        else check(r.freeze_session&&m.wrapper_calls==0&&m.action_dtors==0,"new wrapper work cannot cross TTL; no guessed cleanup");
    }
    { Mock m;m.fault=Fault::claim_false;auto r=m.run(Operation::begin);check(r.freeze_session&&m.factory_calls==0,"batch durable claim failure"); }
    { Mock m;start(m);m.fault=Fault::claim_false;auto r=item(m);check(r.freeze_session&&m.factory_calls==0&&!r.current_item.claimed,"item durable claim failure before factory"); }
    { Mock m;start(m);m.fault=Fault::reenter_claim;auto r=item(m);check(r.freeze_session&&m.factory_calls==0&&r.current_item.claimed,"durable true claim retained even after reentry freeze"); }
    { Mock m;start(m);m.fault=Fault::expire_after_gate;m.allow_gate=false;auto r=item(m);
      check(r.accepted_call&&m.live()==0&&m.command_dtors==1&&r.current_item.outcome==Outcome::command_gate_rejected,"gate false known cleanup after TTL");
      check(health(m).accepted_call&&item(m).freeze_session,"gate cleanup never grants next expired work"); }
    { Mock m;start(m);m.fault=Fault::expire_after_submit;auto r=item(m);
      check(r.accepted_call&&r.current_item.outcome==Outcome::dispatched&&m.live()==0,"normal submit return can be observed after TTL");
      check(health(m).accepted_call&&item(m).freeze_session&&m.submit_calls==1,"postreturn TTL cannot resend next item"); }
}
void exact_image_and_environment() {
    for(const auto& pin:kCodePins) { Mock m;m.memory[BASE+pin.rva]^=1;auto r=m.run(Operation::begin);check(r.freeze_session&&m.claims==0&&m.factory_calls==0,"every inherited code pin required"); }
    for(const auto& pin:eu4_spy19_sender::kCodePins) { Mock m;m.memory[BASE+pin.rva]^=1;auto r=m.run(Operation::begin);check(r.freeze_session&&m.claims==0&&m.factory_calls==0,"every sender code pin required"); }
    for(const auto& pin:kSlotPins) { Mock m;m.mem<std::uintptr_t>(BASE+pin.rva,BASE+pin.target+1);auto r=m.run(Operation::begin);check(r.freeze_session&&m.claims==0,"every inherited slot required"); }
    for(const auto& pin:eu4_spy19_sender::kSlotPins) { Mock m;m.mem<std::uintptr_t>(BASE+pin.rva,BASE+pin.target+1);auto r=m.run(Operation::begin);check(r.freeze_session&&m.claims==0,"every sender slot required"); }
    for(unsigned n=0;n<12;++n) {
        Mock m;
        if(n==0)m.mem<std::int32_t>(DB+0x124,122);
        if(n==1)m.mem<std::int32_t>(DB+0x124,4097);
        if(n==2)m.mem<std::uint64_t>(ENG+0x18f0,FRA_HANDLE);
        if(n==3)m.mem<std::uint8_t>(PAUSE+0x48,0);
        if(n==4)m.mem<std::uint8_t>(GAME+0x24d0,1);
        if(n==5)m.mem<std::uint8_t>(SERVER+0x19f1,1);
        if(n==6)m.mem<std::uint8_t>(0x200080000ULL+0x55,0);
        if(n==7)m.host.resolve=nullptr;
        if(n==8)m.host.identity.dll_sha256[0]='X';
        if(n==9)m.host.full_sha256_verified=false;
        if(n==10)m.host.expires_uptime_ms=m.now+60001;
        if(n==11)m.host.expires_uptime_ms=m.now;
        auto r=m.run(Operation::begin);check(r.freeze_session&&m.claims==0&&m.factory_calls==0,"bounded identity readiness contract");
    }
    { Mock m;m.mem<std::uint8_t>(0x200080000ULL+0x55,0);m.mem<std::uint8_t>(0x200080000ULL+0x80d,2);
      check(m.run(Operation::begin).accepted_call,"readiness exact BYTE nonzero OR, not invented bool restriction"); }
}
void audit_boundaries() {
    unsigned count=0;
    { Mock m;start(m);for(unsigned i=0;i<5;++i) { item(m);health(m); }count=static_cast<unsigned>(m.events.size());check(count<256,"finite audit count"); }
    for(unsigned failure_at=1;failure_at<=count;++failure_at) {
        Mock m;m.fail_log_at=failure_at;Result r=m.run(Operation::begin);++m.host.frame_id;
        for(unsigned i=0;i<5&&!r.freeze_session;++i) { r=item(m);if(!r.freeze_session)r=health(m); }
        check(r.freeze_session&&!r.accepted_call,"every durable audit boundary stops");
        const auto calls=m.factory_calls+m.preview_calls+m.wrapper_calls+m.gate_calls+m.action_dtors+m.command_dtors+m.submit_calls;
        item(m);const auto after=m.factory_calls+m.preview_calls+m.wrapper_calls+m.gate_calls+m.action_dtors+m.command_dtors+m.submit_calls;
        check(after==calls,"audit failure never resumes native");
        if(r.current_item.submit_entered)check(!r.current_item.has_local_command&&!r.current_item.has_local_clone,"postentry audit failure has no cleanup right");
    }
    for(auto fault:{Fault::guard_false,Fault::guard_throw,Fault::reenter,Fault::logger_throw,Fault::mutate_before_call}) {
        Mock m;start(m);m.fault=fault;m.fault_step=Step::full_preview;auto r=item(m);
        check(r.freeze_session&&m.preview_calls==0,"guard/audit/reentry blocks next native call");
    }
}
void final_transfer_guard() {
    for(auto fault:{Fault::final_contract_expired,Fault::final_contract_date,Fault::final_contract_context}) {
        Mock m;start(m);m.fault=fault;const auto r=item(m);
        check(m.dispatch_intent_seen&&r.freeze_session&&!r.accepted_call,"last owned reads cannot bypass fresh transfer guard");
        check(!r.current_item.submit_entered&&m.submit_calls==0&&r.current_item.has_local_command&&r.current_item.has_local_clone,"no transfer after final read invalidates TTL or roots");
        const auto dtors=m.command_dtors;item(m);
        check(m.submit_calls==0&&m.command_dtors==dtors,"failed final transfer guard cannot retry or guess cleanup");
    }
}
} // namespace (mock_support opens it)
int main() {
    stable_matrix();failure_matrix();transfer_unknown();ordering_ttl_identity();exact_image_and_environment();audit_boundaries();final_transfer_guard();
    std::printf("{\"checks\":%u,\"failures\":%u,\"mock_only\":true,\"game_access\":false}\n",checks,failures);
    return failures?1:0;
}
