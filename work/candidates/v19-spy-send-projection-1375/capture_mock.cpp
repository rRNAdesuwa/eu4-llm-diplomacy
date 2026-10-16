#include <string>
#include "../v19-spy-send-core-1375/mock_support.inc"
const char* scenario="";unsigned ordinal=0;Operation active_op=Operation::begin;
void head(const char* kind) { std::printf("{\"origin\":\"isolated_mock_cpp\",\"scenario\":\"%s\",\"ordinal\":%u,\"kind\":\"%s\",\"data\":",scenario,++ordinal,kind); }
void tail() { std::printf("}\n"); }
void identity(const Identity& v) { std::printf("{");
std::printf("\"pid\":%llu",static_cast<unsigned long long>(v.pid));
std::printf(",\"creation_filetime\":%llu",static_cast<unsigned long long>(v.creation_filetime));
std::printf(",\"session\":\"%s\"",v.session);
std::printf(",\"dll_sha256\":\"%s\"",v.dll_sha256);
std::printf(",\"manifest_sha256\":\"%s\"",v.manifest_sha256);
std::printf("}"); }
void stamp(const Stamp& v) { std::printf("{");
std::printf("\"game\":%llu",static_cast<unsigned long long>(v.game));
std::printf(",\"database\":%llu",static_cast<unsigned long long>(v.database));
std::printf(",\"countries\":%llu",static_cast<unsigned long long>(v.countries));
std::printf(",\"actor_country\":%llu",static_cast<unsigned long long>(v.actor_country));
std::printf(",\"target_country\":%llu",static_cast<unsigned long long>(v.target_country));
std::printf(",\"server\":%llu",static_cast<unsigned long long>(v.server));
std::printf(",\"pause_manager\":%llu",static_cast<unsigned long long>(v.pause_manager));
std::printf(",\"actor\":%llu",static_cast<unsigned long long>(v.actor));
std::printf(",\"target\":%llu",static_cast<unsigned long long>(v.target));
std::printf(",\"player\":%llu",static_cast<unsigned long long>(v.player));
std::printf(",\"holder\":%llu",static_cast<unsigned long long>(v.holder));
std::printf(",\"context\":%llu",static_cast<unsigned long long>(v.context));
std::printf(",\"transport\":%llu",static_cast<unsigned long long>(v.transport));
std::printf(",\"actor_overlord\":%llu",static_cast<unsigned long long>(v.actor_overlord));
std::printf(",\"target_overlord\":%llu",static_cast<unsigned long long>(v.target_overlord));
std::printf(",\"effective_player\":%llu",static_cast<unsigned long long>(v.effective_player));
std::printf(",\"country_count\":%llu",static_cast<unsigned long long>(v.country_count));
std::printf(",\"context_ready55\":%llu",static_cast<unsigned long long>(v.context_ready55));
std::printf(",\"context_ready80d\":%llu",static_cast<unsigned long long>(v.context_ready80d));
std::printf(",\"date\":%lld",static_cast<long long>(v.date));
std::printf(",\"native_speed_index\":%lld",static_cast<long long>(v.native_speed_index));
std::printf("}"); }
void fields(const Fields& v) { std::printf("{");
std::printf("\"vtable\":%llu",static_cast<unsigned long long>(v.vtable));
std::printf(",\"marker\":%llu",static_cast<unsigned long long>(v.marker));
std::printf(",\"actor\":%llu",static_cast<unsigned long long>(v.actor));
std::printf(",\"controller\":%llu",static_cast<unsigned long long>(v.controller));
std::printf(",\"target\":%llu",static_cast<unsigned long long>(v.target));
std::printf(",\"state\":%llu",static_cast<unsigned long long>(v.state));
std::printf(",\"value\":%llu",static_cast<unsigned long long>(v.value));
std::printf(",\"flag39\":%llu",static_cast<unsigned long long>(v.flag39));
std::printf(",\"identifier\":%llu",static_cast<unsigned long long>(v.identifier));
std::printf(",\"primary_date\":%lld",static_cast<long long>(v.primary_date));
std::printf(",\"secondary_date\":%lld",static_cast<long long>(v.secondary_date));
std::printf(",\"envoy\":%lld",static_cast<long long>(v.envoy));
std::printf("}"); }
void item_json(const Item& v) { std::printf("{");
std::printf("\"ordinal\":%llu",static_cast<unsigned long long>(v.ordinal));
std::printf(",\"family\":%llu",static_cast<unsigned long long>(v.family));
std::printf(",\"token\":%llu",static_cast<unsigned long long>(v.token));
std::printf(",\"original_id\":%llu",static_cast<unsigned long long>(v.original_id));
std::printf(",\"clone_id\":%llu",static_cast<unsigned long long>(v.clone_id));
std::printf(",\"command_id\":%llu",static_cast<unsigned long long>(v.command_id));
std::printf(",\"owner_frame\":%llu",static_cast<unsigned long long>(v.owner_frame));
std::printf(",\"step\":%llu",static_cast<unsigned long long>(v.step));
std::printf(",\"outcome\":%llu",static_cast<unsigned long long>(v.outcome));
std::printf(",\"claimed\":%s",v.claimed?"true":"false");
std::printf(",\"call_entered\":%s",v.call_entered?"true":"false");
std::printf(",\"call_returned\":%s",v.call_returned?"true":"false");
std::printf(",\"preview_observed\":%s",v.preview_observed?"true":"false");
std::printf(",\"preview_allowed\":%s",v.preview_allowed?"true":"false");
std::printf(",\"gate_observed\":%s",v.gate_observed?"true":"false");
std::printf(",\"gate_allowed\":%s",v.gate_allowed?"true":"false");
std::printf(",\"original_destroyed\":%s",v.original_destroyed?"true":"false");
std::printf(",\"command_destroyed\":%s",v.command_destroyed?"true":"false");
std::printf(",\"clone_destroyed\":%s",v.clone_destroyed?"true":"false");
std::printf(",\"submit_entered\":%s",v.submit_entered?"true":"false");
std::printf(",\"submit_returned\":%s",v.submit_returned?"true":"false");
std::printf(",\"submit_value_observed\":%s",v.submit_value_observed?"true":"false");
std::printf(",\"submit_value\":%s",v.submit_value?"true":"false");
std::printf(",\"slot_observed\":%s",v.slot_observed?"true":"false");
std::printf(",\"slot_consumed\":%s",v.slot_consumed?"true":"false");
std::printf(",\"has_local_original\":%s",v.has_local_original?"true":"false");
std::printf(",\"has_local_command\":%s",v.has_local_command?"true":"false");
std::printf(",\"has_local_clone\":%s",v.has_local_clone?"true":"false");
std::printf(",\"current\":%s",v.current?"true":"false");
std::printf(",\"original_fields\":");fields(v.original_fields);
std::printf(",\"clone_fields\":");fields(v.clone_fields);
std::printf("}"); }
void event_json(const Event& v) { std::printf("{");
std::printf("\"kind\":%llu",static_cast<unsigned long long>(v.kind));
std::printf(",\"operation\":%llu",static_cast<unsigned long long>(v.operation));
std::printf(",\"request_sequence\":%llu",static_cast<unsigned long long>(v.request_sequence));
std::printf(",\"completed\":%llu",static_cast<unsigned long long>(v.completed));
std::printf(",\"exception_code\":%llu",static_cast<unsigned long long>(v.exception_code));
std::printf(",\"frame\":%llu",static_cast<unsigned long long>(v.frame));
std::printf(",\"uptime_ms\":%llu",static_cast<unsigned long long>(v.uptime_ms));
std::printf(",\"expires_uptime_ms\":%llu",static_cast<unsigned long long>(v.expires_uptime_ms));
std::printf(",\"reason\":%llu",static_cast<unsigned long long>(v.reason));
std::printf(",\"state\":%llu",static_cast<unsigned long long>(v.state));
std::printf(",\"mock_resolver\":%s",v.mock_resolver?"true":"false");
std::printf(",\"production_ready\":%s",v.production_ready?"true":"false");
std::printf(",\"strict_sp_verified\":%s",v.strict_sp_verified?"true":"false");
std::printf(",\"epoch_verified\":%s",v.epoch_verified?"true":"false");
std::printf(",\"effect_verified\":%s",v.effect_verified?"true":"false");
std::printf(",\"identity\":");identity(v.identity);
std::printf(",\"stamp\":");stamp(v.stamp);
std::printf(",\"item\":");item_json(v.item);
std::printf("}"); }
void result_base(const Result& v) { std::printf("{");
std::printf("\"state\":%llu",static_cast<unsigned long long>(v.state));
std::printf(",\"reason\":%llu",static_cast<unsigned long long>(v.reason));
std::printf(",\"completed\":%llu",static_cast<unsigned long long>(v.completed));
std::printf(",\"exception_code\":%llu",static_cast<unsigned long long>(v.exception_code));
std::printf(",\"read_calls\":%llu",static_cast<unsigned long long>(v.read_calls));
std::printf(",\"bytes_read\":%llu",static_cast<unsigned long long>(v.bytes_read));
std::printf(",\"accepted_call\":%s",v.accepted_call?"true":"false");
std::printf(",\"audit_complete\":%s",v.audit_complete?"true":"false");
std::printf(",\"freeze_session\":%s",v.freeze_session?"true":"false");
std::printf(",\"ownership_uncertain\":%s",v.ownership_uncertain?"true":"false");
std::printf(",\"retry_allowed\":%s",v.retry_allowed?"true":"false");
std::printf(",\"runtime_verified\":%s",v.runtime_verified?"true":"false");
std::printf(",\"production_ready\":%s",v.production_ready?"true":"false");
std::printf(",\"effect_verified\":%s",v.effect_verified?"true":"false");
std::printf(",\"strict_sp_verified\":%s",v.strict_sp_verified?"true":"false");
std::printf(",\"epoch_verified\":%s",v.epoch_verified?"true":"false");
std::printf(",\"current_item\":");item_json(v.current_item);
std::printf("}"); }
void result_json(const Result& r) { std::printf("{\"result\":");result_base(r);std::printf(",\"completed_outcomes\":[");for(unsigned i=0;i<5;++i)std::printf("%s%u",i?",":"",static_cast<unsigned>(r.completed_outcomes[i]));std::printf("]}"); }
bool log_capture(void* p,const Event* e) { const bool ok=log_cb(p,e);head("core_event");std::printf("{\"durable\":%s,\"event\":",ok?"true":"false");event_json(*e);std::printf("}");tail();return ok; }
bool claim_capture(void* p,std::uint32_t sequence,std::uint32_t n,const Identity* id,const Stamp* st) { const bool ok=claim_cb(p,sequence,n,id,st);auto& m=*static_cast<Mock*>(p);head("claim");std::printf("{\"sequence\":%u,\"item_ordinal\":%u,\"durable\":%s,\"frame\":%llu,\"uptime_ms\":%llu,\"identity\":",sequence,n,ok?"true":"false",m.host.frame_id,m.now);identity(*id);std::printf(",\"stamp\":");stamp(*st);std::printf("}");tail();return ok; }
void call_enter(Step step,std::uintptr_t rva,void* context=nullptr,void** slot=nullptr) { head("mock_call_enter");std::printf("{\"step\":%u,\"rva\":%llu,\"frame\":%llu,\"uptime_ms\":%llu,\"context\":%llu,\"slot_nonnull\":%s}",static_cast<unsigned>(step),static_cast<unsigned long long>(rva),current->host.frame_id,current->now,static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(context)),slot&&*slot?"true":"false");tail(); }
void* __fastcall factory_capture(std::uint32_t token,const void* optional) { call_enter(Step::factory,0x35d210);return factory_fn(token,optional); }
bool __fastcall preview_capture(void* a,void* sink,bool mode) { call_enter(Step::full_preview,PREVIEWS[current->events.back().item.family]);return preview_fn(a,sink,mode); }
void** __fastcall wrapper_capture(void* a,void** slot) { call_enter(Step::wrap_owned,0x4e9930);return wrapper_fn(a,slot); }
bool __fastcall gate_capture(void* a) { call_enter(Step::command_gate,0x4e8630);return gate_fn(a); }
void* __fastcall action_dtor_capture(void* a,unsigned flags) { call_enter(Step::destroy_original,0x129450);return action_dtor_fn(a,flags); }
void* __fastcall command_dtor_capture(void* a,unsigned flags) { call_enter(Step::destroy_command,0x4e7470);return command_dtor_fn(a,flags); }
bool __fastcall submit_capture(void* c,void** slot) { call_enter(Step::submit,0x14ca210,c,slot);return submit_fn(c,slot); }
std::uintptr_t resolve_capture(void* p,std::uintptr_t rva) { auto fn=resolve_cb(p,rva);if(!fn)return 0;
if(rva==0x35d210)return reinterpret_cast<std::uintptr_t>(&factory_capture);
if(rva==0x4e9930)return reinterpret_cast<std::uintptr_t>(&wrapper_capture);
if(rva==0x4e8630)return reinterpret_cast<std::uintptr_t>(&gate_capture);
if(rva==0x129450)return reinterpret_cast<std::uintptr_t>(&action_dtor_capture);
if(rva==0x4e7470)return reinterpret_cast<std::uintptr_t>(&command_dtor_capture);
if(rva==0x14ca210)return reinterpret_cast<std::uintptr_t>(&submit_capture);
for(auto r:PREVIEWS)if(rva==r)return reinterpret_cast<std::uintptr_t>(&preview_capture);
return fn; }
Result invoke_capture(Mock& m,Operation op) { active_op=op;head("operation_begin");std::printf("{\"operation\":%u,\"frame\":%llu,\"uptime_ms\":%llu}",static_cast<unsigned>(op),m.host.frame_id,m.now);tail();auto r=m.run(op);head("operation_result");result_json(r);tail();++m.host.frame_id;return r; }
void run_case(const char* name,unsigned mode,Fault fault=Fault::none) { scenario=name;ordinal=0;Mock m;m.host.frame_id=4;m.host.log=log_capture;m.host.claim=claim_capture;m.host.resolve=resolve_capture;head("scenario_begin");std::printf("{\"identity\":");identity(m.host.identity);std::printf(",\"image_base\":%llu,\"thread\":%u,\"expires\":%llu,\"preflight_assertions\":[true,true,true],\"initial_sha256\":\"%s\"}",static_cast<unsigned long long>(m.host.image_base),m.host.expected_game_thread,m.host.expires_uptime_ms,std::string(64,'a').c_str());tail();Result r=invoke_capture(m,Operation::begin);for(unsigned i=0;i<5&&!r.freeze_session;++i) { m.allow_preview=mode!=0&&(mode!=3||i%3!=0);m.allow_gate=mode!=1&&(mode!=3||i%3!=1);m.fault=i==0?fault:Fault::none;if(fault==Fault::logger_begin||fault==Fault::logger_return)m.fault_step=Step::submit;r=invoke_capture(m,Operation::next_item);if(!r.freeze_session)r=invoke_capture(m,Operation::later_health); }head("scenario_end");std::printf("{\"frame\":%llu,\"uptime_ms\":%llu,\"final_sha256\":",m.host.frame_id,m.now);if(r.state==State::complete)std::printf("\"%s\"",std::string(64,'b').c_str());else std::printf("null");std::printf(",\"abi_errors\":%u,\"invalid_reads\":%u,\"invalid_writes\":%u,\"mock_only\":true,\"game_accessed\":false}",m.abi_errors,m.invalid_reads,m.invalid_writes);tail(); }
} // anonymous namespace opened by sealed mock_support.inc
int main() { check(true,"capture harness active");run_case("dispatched",2);run_case("preview_false",0);run_case("gate_false",1);run_case("mixed",3);
run_case("factory_null",2,Fault::factory_null);
run_case("preview_throw",2,Fault::preview_throw);
run_case("wrapper_alias",2,Fault::wrapper_alias);
run_case("submit_throw",2,Fault::submit_throw);
run_case("submit_false_consumed",2,Fault::submit_false_consumed);
run_case("submit_true_unconsumed",2,Fault::submit_true_unconsumed);
run_case("submit_false_unconsumed",2,Fault::submit_false_unconsumed);
run_case("logger_begin",2,Fault::logger_begin);
run_case("logger_return",2,Fault::logger_return);
run_case("final_contract_expired",2,Fault::final_contract_expired);
run_case("expire_after_submit",2,Fault::expire_after_submit);
run_case("cleanup_expired",0,Fault::expire_after_preview);return failures?1:0; }
