"""Create new private send core. Old sealed sources are never edited."""
import hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'work/candidates/v21-core-pair-nosend-r3-1375'
HERE=ROOT/'work/candidates/v24-pair-send-core-1375'
def desc(p):
    b=p.read_bytes(); assert len(b)<4*1024*1024
    return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def put(name,data):
    p=HERE/name;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(data.encode('ascii') if isinstance(data,str) else data)
index=json.loads((OLD/'source-index.json').read_bytes())
assert all(desc(OLD/k)==v for k,v in index.items())
HERE.mkdir(exist_ok=False)
pins={(OLD/k).relative_to(ROOT).as_posix():v for k,v in index.items()}
for name in ['pair_component.cpp','pair_component.h','test_pair_component.cpp','typed_fixture.h']:
    put('preimages/'+name,(OLD/name).read_bytes())
put('pair_send.h',r'''#pragma once
#include "../v21-core-pair-nosend-r2-1375/pair_component.h"
#include <atomic>
namespace v21pair {
enum class TransferOutcome : std::uint8_t { NotAttempted, Dispatched, Unknown };
struct TransferReturn {bool normal{},value{},slot_consumed{};std::uint32_t exception{};};
// Private port only. No addresses, context, flags or credentials are public.
class TransferPort {
public:
    virtual ~TransferPort()=default;
    // Must durably record intent. The core rechecks all fields/world/original TTL
    // AFTER this callback. A record alone never authorizes native entry.
    virtual bool dispatch_intent(const Request&,const PairStamp&,OwnedId command,OwnedId clone)=0;
    // Implementer must consume its OWN ledger IDs, validate its private context,
    // and make a final world/clock check immediately before ABI entry. Any entry
    // relinquishes local ownership, including false, exception or non-NULL slot.
    // The core never reads/destroys transferred objects after this callback.
    virtual TransferReturn submit_owned(OwnedId command)=0;
};
struct SendResult : Result {
    TransferOutcome transfer{TransferOutcome::NotAttempted};
    bool submit_entered{},submit_returned{},submit_value{},slot_consumed{};
    std::uint32_t submit_exception{};
};
class SendCore {
public:
    SendCore()=default;
    SendCore(const SendCore&)=delete;SendCore& operator=(const SendCore&)=delete;
    SendResult invoke(const Request&,SyntheticGuard&,SyntheticEngine&,TransferPort&,
        std::uint64_t original_expires,SyntheticReadPort* spy_reader=nullptr,std::uint64_t module=0) noexcept;
private:
    std::atomic_bool attempted_{false};
};
}
''')
data=(OLD/'pair_component.cpp').read_text()
data=data.replace('#include "pair_component.h"','#include "pair_send.h"',1)
old='''Result preflight_no_send(const Request& request, SyntheticGuard& guard, SyntheticEngine& e,
    std::uint64_t expires, SyntheticReadPort* spy_reader, std::uint64_t module) noexcept {
    Result result{};'''
new='''static SendResult execute_impl(const Request& request, SyntheticGuard& guard, SyntheticEngine& e,
    std::uint64_t expires, SyntheticReadPort* spy_reader, std::uint64_t module, TransferPort* sender) noexcept {
    SendResult result{};'''
assert old in data;data=data.replace(old,new,1)
old='''        if (!cleanup_original() || !cleanup_command()) return freeze("known_cleanup_unconfirmed");
        result.status=gate?Status::ModelComplete:Status::ModelGateRejected;
        result.reason=gate?"synthetic_lifecycle_no_send":"command_gate_normal_false";return result;'''
new='''        if (!cleanup_original()) return freeze("original_cleanup_unconfirmed");
        if (!sender || !gate) {
            if (!cleanup_command()) return freeze("known_cleanup_unconfirmed");
            result.status=gate?Status::ModelComplete:Status::ModelGateRejected;
            result.reason=gate?"synthetic_lifecycle_no_send":"command_gate_normal_false";return result;
        }
        // Independent command clone survives the original destructor. Intent
        // is durable BEFORE submission; fields/binding/stamps/LAST original TTL
        // are re-read AFTER the potentially slow filesystem callback.
        if (!sender->dispatch_intent(request,baseline,command,clone)) return freeze("dispatch_intent_unconfirmed");
        if (!work_guard(objects_fields)) return freeze("final_dispatch_guard");
        result.submit_entered=true;result.transfer=TransferOutcome::Unknown;
        const auto transferred=sender->submit_owned(command);
        result.submit_returned=transferred.normal;result.submit_value=transferred.value;
        result.slot_consumed=transferred.slot_consumed;result.submit_exception=transferred.exception;
        // No object reads, destructor, callback, or retry after submission.
        // A normal true return with consumed slot proves only queue dispatch.
        if (!transferred.normal || transferred.exception || !transferred.value || !transferred.slot_consumed)
            return freeze("dispatch_outcome_unknown_no_retry");
        command={};clone={};result.transfer=TransferOutcome::Dispatched;
        result.status=Status::ModelComplete;result.reason="normal_dispatch_slot_consumed";
        result.submitted=true;return result;'''
assert old in data;data=data.replace(old,new,1)
suffix='''
Result preflight_no_send(const Request& r,SyntheticGuard& g,SyntheticEngine& e,
    std::uint64_t expires,SyntheticReadPort* reader,std::uint64_t module) noexcept {
    return execute_impl(r,g,e,expires,reader,module,nullptr);
}
SendResult SendCore::invoke(const Request& r,SyntheticGuard& g,SyntheticEngine& e,TransferPort& sender,
    std::uint64_t expires,SyntheticReadPort* reader,std::uint64_t module) noexcept {
    if(attempted_.exchange(true)) {SendResult result{};result.status=Status::Frozen;
        result.reason="core_already_attempted_no_rearm";return result;}
    return execute_impl(r,g,e,expires,reader,module,&sender);
}
'''
assert data.endswith('}\n');data=data[:-2]+suffix+'}\n'
put('pair_send.cpp',data)
put('pair_component.h','#pragma once\n#include "pair_send.h"\n')
put('test_pair_component.cpp',(OLD/'test_pair_component.cpp').read_bytes())
put('test_send.cpp',r'''#define main retained_no_send_main
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
''')
put('build_test.cmd',r'''@echo off
setlocal
set "pair24_src=%~dp0"
set "pair24_out=%~1"
mkdir "%pair24_out%" || exit /b 10
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" > "%pair24_out%\environment.stdout" 2>&1
if errorlevel 1 exit /b 11
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS "%pair24_src%pair_send.cpp" "%pair24_src%test_send.cpp" /Fo"%pair24_out%\" /Fe"%pair24_out%\test_send.exe" > "%pair24_out%\compile.stdout" 2> "%pair24_out%\compile.stderr"
if errorlevel 1 exit /b 12
"%pair24_out%\test_send.exe" > "%pair24_out%\test.stdout" 2> "%pair24_out%\test.stderr"
exit /b %errorlevel%
''')
put('README.md',r'''# Private V24 pair send core

Twelve typed start/stop modes in six families. Copied R3 lifecycle algorithm,
with the existing no-send entry kept and tested. New single-use SendCore keeps
the independently cloned command after deleting the original. A durable intent
precedes a fresh fields/cancellation/world/LAST original TTL guard. Private
TransferPort is not implemented by this candidate and exposes no addresses.
Only normal true plus consumed slot is called Dispatched; effects, reception,
strict SP and epoch remain unproved. Every uncertain entry freezes and forbids
all local reads, cleanup, retry and rearm. Old sources/seals are untouched.
Offline tests use the old synthetic engine, never the game. No DLL or API backend.
''')
pins['work/candidates/v21-core-pair-nosend-r2-1375/pair_component.h']=desc(ROOT/'work/candidates/v21-core-pair-nosend-r2-1375/pair_component.h')
pins['work/candidates/v21-core-pair-nosend-1375/validate.py']=desc(ROOT/'work/candidates/v21-core-pair-nosend-1375/validate.py')
pins[Path(__file__).relative_to(ROOT).as_posix()]=desc(Path(__file__))
put('input-pins.json',json.dumps(pins,indent=2,sort_keys=True)+'\n')
put('validate.py',r'''import hashlib,importlib.util,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def desc(p):
 b=p.read_bytes();assert len(b)<=4*1024*1024;return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def own():return {p.name:desc(p) for p in HERE.iterdir() if p.is_file() and p.name not in ('source-index.json','review.json')}
def inputs():
 d=json.loads((HERE/'input-pins.json').read_bytes());assert all(desc(ROOT/k)==v for k,v in d.items());return d
def main():
 assert sys.flags.isolated==1 and len(sys.argv)==2 and sys.argv[1].replace('-','').isalnum()
 out=HERE/sys.argv[1];out.mkdir(exist_ok=False);before=own();pins=inputs()
 spec=importlib.util.spec_from_file_location('bounded_job',ROOT/'work/candidates/v21-core-pair-nosend-1375/validate.py')
 job=importlib.util.module_from_spec(spec);spec.loader.exec_module(job);job.HERE=HERE;job.ROOT=ROOT
 build=job.run_build(out);after=own();after_pins=inputs()
 log=(out/'build/test.stdout').read_text() if (out/'build/test.stdout').exists() else ''
 passed=build['exit_code']==0 and 'send_groups=10 ' in log and before==after and pins==after_pins
 report=dict(passed=passed,build=build,sources_before=before,sources_after=after,inputs_before=pins,inputs_after=after_pins,
  test_stdout=log,game_accessed=False,native_game_called=False,DLL_built=False,production_ready=False)
 with (out/'validation.json').open('x') as f:json.dump(report,f,indent=2,sort_keys=True)
 print(json.dumps(dict(passed=passed,build=build)));return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
''')
put('source-index.json',json.dumps({p.name:desc(p) for p in HERE.iterdir() if p.is_file()},indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(candidate=HERE.name,sources=len(list(HERE.iterdir())),inputs=len(pins))))
