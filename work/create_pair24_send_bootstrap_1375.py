"""Create separate send-enabled DLL sources. No loader or process access."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'work/candidates/v23-pair-nosend-bootstrap-1375'
HERE=ROOT/'work/candidates/v24-pair-send-bootstrap-1375'
def desc(p):
 b=p.read_bytes();assert len(b)<4*1024*1024;return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def put(name,b):
 p=HERE/name;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(b.encode('ascii') if isinstance(b,str) else b)
index=json.loads((OLD/'source-index.json').read_bytes());pins=json.loads((OLD/'input-pins.json').read_bytes())
assert all(desc(OLD/k)==v for k,v in index.items()) and all(desc(ROOT/k)==v for k,v in pins.items())
HERE.mkdir(exist_ok=False)
for name in index:
 if name=='input-pins.json':continue
 original=(OLD/name).read_bytes();put('preimages/'+name,original);pins[(OLD/name).relative_to(ROOT).as_posix()]=desc(OLD/name)
 data=original.decode('ascii').replace('pair23','pair24').replace('v23','v24').replace('V23','V24')
 data=data.replace('restricted_pair_nosend','restricted_pair_send').replace('eu4_pair_nosend','eu4_pair_send')
 data=data.replace('EU4PAIRNOSEND/1','EU4PAIRSEND/1').replace('EU4PAIRBOOT/1','EU4PAIRSENDBOOT/1').replace('EU4PAIR/1','EU4PAIRSEND/1').replace('EU4PAIR/2','EU4PAIRSEND/2')
 data=data.replace('no_send=','send=')
 if name=='bootstrap.cpp':
  data=data.replace('#include <new>','#include "../v24-pair-send-port-1375/submission_guard.h"\n#include <new>',1)
  data=data.replace('v21port::','v24port::').replace('\\"no_send\\":true','\\"no_send\\":false')
  old='''  if(!record("native_call_return",",\\"call\\":%u,\\"normal\\":%s,\\"boolean\\":%s,\\"returned_same_slot\\":%s,\\"exception\\":%u",static_cast<unsigned>(kind),r.normal?"true":"false",r.boolean?"true":"false",r.returned_same_slot?"true":"false",r.exception))return {};'''
  new='''  if(!record("native_call_return",",\\"call\\":%u,\\"normal\\":%s,\\"boolean\\":%s,\\"returned_same_slot\\":%s,\\"exception\\":%u,\\"slot_consumed\\":false",static_cast<unsigned>(kind),r.normal?"true":"false",r.boolean?"true":"false",r.returned_same_slot?"true":"false",r.exception))return {};'''
  assert old in data;data=data.replace(old,new,1)
  at='''  return r;
 }
};
struct Job {'''
  added='''  return r;
 }
 v21pair::TransferReturn submit(const v24port::TransferEnvelope& e) override {
  if(!running()||!record("native_call_begin",",\\"call\\":7,\\"family\\":%u",static_cast<unsigned>(e.profile.family)))return {};
  const auto r=platform.submit(e);
  if(!record("native_call_return",",\\"call\\":7,\\"normal\\":%s,\\"boolean\\":%s,\\"returned_same_slot\\":false,\\"exception\\":%u,\\"slot_consumed\\":%s",
      r.normal?"true":"false",r.value?"true":"false",r.exception,r.slot_consumed?"true":"false"))return {};
  return r;
 }
};
struct Job :v21pair::TransferPort {'''
  assert at in data;data=data.replace(at,added,1)
  data=data.replace('AuditedPlatform(std::uint64_t base,std::uint32_t owner,v24port::Authority authority):platform(base,owner,authority){}',
    'AuditedPlatform(std::uint64_t base,std::uint32_t owner,v24port::Authority authority,v24port::SubmissionAuthority send):platform(base,owner,authority,send){}',1)
  old=''' v21guard::NativePairGuardDraft guard;AuditedPlatform platform;v24port::NativePairEngineDraft engine;
 explicit Job():guard(env),platform(env.image_base,env.owner_thread,guard.authority()),engine(platform){}'''
  new=''' v21guard::NativePairGuardDraft guard;v24port::SubmissionGuard submission_guard;
 AuditedPlatform platform;v24port::NativePairEngineDraft engine;v21pair::SendCore core;
 v21pair::Request request;bool intent{},transfer_attempted{};v21pair::OwnedId intended_command{},intended_clone{};
 explicit Job(const pair24::Packet& p):guard(env),submission_guard({env.image_base,p.expires,this,world_cb,read_cb,clock_cb}),
  platform(env.image_base,env.owner_thread,{this,fresh_cb,last_cb,write_cb},submission_guard.authority()),engine(platform),request(p.request){}
 static bool fresh_cb(void* p,v24port::Address base,std::uint32_t owner) {
  auto& j=*static_cast<Job*>(p);const auto a=j.guard.authority();return running()&&a.fresh(a.user,base,owner);
 }
 static bool last_cb(void* p,v24port::Call call) {
  auto& j=*static_cast<Job*>(p);const auto a=j.guard.authority();
  const auto k=static_cast<unsigned>(call);return running()&&k<=6&&a.final_operation(a.user,static_cast<v21port::Call>(k));
 }
 static bool write_cb(void* p) {auto& j=*static_cast<Job*>(p);const auto a=j.guard.authority();return running()&&a.final_owned_write(a.user);}
 static bool world_cb(void* p) {return last_cb(p,v24port::Call::Gate);}
 static bool read_cb(void* p,v24port::Address a,void* out,std::size_t n) {return running()&&static_cast<Job*>(p)->guard.read(a,out,n);}
 static std::uint64_t clock_cb(void* p) {return static_cast<Job*>(p)->guard.clock();}
 bool dispatch_intent(const v21pair::Request& r,const v21pair::PairStamp& s,v21pair::OwnedId command,v21pair::OwnedId clone) override {
  if(intent||transfer_attempted||!running()||r.action!=request.action||r.actor.bytes!=request.actor.bytes||r.target.bytes!=request.target.bytes
      ||!(s==guard.baseline())||!command.value||!clone.value||command==clone)return false;
  intent=true;intended_command=command;intended_clone=clone;
  return record("dispatch_intent",",\\"command_id\\":%llu,\\"clone_id\\":%llu,\\"original_deleted\\":true",
   static_cast<unsigned long long>(command.value),static_cast<unsigned long long>(clone.value));
 }
 v21pair::TransferReturn submit_owned(v21pair::OwnedId command) override {
  if(!intent||transfer_attempted||!running()||!(command==intended_command))return {};
  transfer_attempted=true;return engine.transfer_owned(command);
 }'''
  assert old in data;data=data.replace(old,new,1)
  data=data.replace('new(std::nothrow) Job()','new(std::nothrow) Job(packet)',1)
  data=data.replace('v21pair::preflight_no_send(packet.request,job->guard,job->engine,packet.expires,&job->guard,env.image_base)',
                    'job->core.invoke(packet.request,job->guard,job->engine,*job,packet.expires,&job->guard,env.image_base)',1)
  start=data.index(' if(!record("request_result"')
  end=data.index('\n if(!success)',start)
  data=data[:start]+''' if(!record("request_result",",\\"status\\":%u,\\"reason\\":\\"%s\\",\\"adapter_call_attempts\\":%u,\\"owned_issued\\":%u,\\"owned_live\\":%u,\\"quarantined\\":%u,\\"adapter_fault\\":%u,\\"known_cleanup_complete\\":%s,\\"ownership_closed\\":%s,\\"submitted\\":%s,\\"transfer_outcome\\":%u,\\"submit_attempted\\":%s,\\"submit_returned\\":%s,\\"submit_value\\":%s,\\"slot_consumed\\":%s,\\"submit_exception\\":%u",
   static_cast<unsigned>(result.status),result.reason,d.calls,d.issued,d.live,d.quarantined,static_cast<unsigned>(d.fault),
   success&&!result.submit_entered?"true":"false",success?"true":"false",result.submitted?"true":"false",static_cast<unsigned>(result.transfer),
   result.submit_entered?"true":"false",result.submit_returned?"true":"false",result.submit_value?"true":"false",result.slot_consumed?"true":"false",result.submit_exception))return;'''+data[end:]
 elif name=='prepare.py':
  data=data.replace("'v21-native-pair-port-r2-1375/native_pair_engine.cpp','v21-native-pair-port-r2-1375/native_platform.cpp'",
    "'v24-pair-send-port-1375/native_pair_engine.cpp','v24-pair-send-port-1375/native_platform.cpp','v24-pair-send-port-1375/submission_guard.cpp'")
  data=data.replace("'v21-core-pair-nosend-r3-1375/pair_component.cpp'","'v24-pair-send-core-r2-1375/pair_send.cpp'")
 elif name=='build_test.cmd':
  data=data.replace('(native_pair_engine native_platform)','(native_pair_engine native_platform submission_guard)')
  data=data.replace('..\\v21-native-pair-port-r2-1375\\','..\\v24-pair-send-port-1375\\')
  data=data.replace('..\\v21-core-pair-nosend-r3-1375\\pair_component.cpp','..\\v24-pair-send-core-r2-1375\\pair_send.cpp')
  data=data.replace('"%pair24_out%\\native_platform.obj"','"%pair24_out%\\native_platform.obj" "%pair24_out%\\submission_guard.obj"')
 put(name,data)
for dirname in ['v24-pair-send-core-r2-1375','v24-pair-send-port-1375']:
 base=ROOT/'work/candidates'/dirname
 ix=json.loads((base/'source-index.json').read_bytes());v=json.loads((base/'development-attempt1/validation.json').read_bytes())
 assert v['passed'] and v['sources_before']==v['sources_after']==ix and v['build']['all_children_collected']
 for name,pin in ix.items():pins[(base/name).relative_to(ROOT).as_posix()]=pin
 for name in ['source-index.json','development-attempt1/validation.json']:pins[(base/name).relative_to(ROOT).as_posix()]=desc(base/name)
pins['work/runtime/pair23-checkpoint-r2-20261012a/report.json']=desc(ROOT/'work/runtime/pair23-checkpoint-r2-20261012a/report.json')
pins[Path(__file__).relative_to(ROOT).as_posix()]=desc(Path(__file__))
put('input-pins.json',json.dumps(pins,indent=2,sort_keys=True)+'\n')
(HERE/'README.md').write_text('''# V24 private pair send DLL

Separate build and fresh process required. Twelve codec modes; fixed positive
batch client is separate. Actual initialized NativeEnvironment and one claimed
lease per Job. Uses SendCore + native ledger + SubmissionGuard, not the V19 spy
sender. World callbacks bind the same actual guard and original expires.
Audits dispatch intent, submit adapter entry/return and ownership-closed result.
Queue dispatch is normal true+NULL consumed only. No transferred object reads,
cleanup or retries. Unknown freezes the whole Host. No receiver drain, SP/epoch
or effect proof. Volatile-XMM frame hook limitation inherited. No production API.
''',encoding='ascii')
print(json.dumps(dict(candidate=HERE.name,initial_inputs=len(pins))))
