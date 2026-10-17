// Request-bound execution for the direct Set/Remove Rival commands.
// Hook callbacks copy state only; request consumption and JSON output run on
// the already verified game frame thread.  There is no Alliance action here.
#include "rival-command-authority.h"
#include "rival-command-wire.h"

namespace rival_execution_detail {
namespace authority=bridge::rival_command_authority;
namespace wire=bridge::rival_command_wire;
constexpr unsigned capacity=64;
struct Binding {
    bool used=false,invalidated=false,serialized=false,claimed=false;
    bool postcloned=false,submitted=false,consumed=false,done=false;
    bool submission_emitted=false,result_emitted=false,relationship_verified=false;
    wire::ExecutionRequest request{};
    authority::RivalPayload payload{};
    authority::SeedReceipt seed{};
    authority::ClaimTicket claim{};
    authority::ObjectRef source{},loaded{},target{};
    authority::NativeHeader header{};
    RivalQueryState before{},after{};
    int32_t cost=-1;
    char reason[80]{};
};
static Binding bindings[capacity]{};
static authority::RivalCommandAuthorityLedger ledger(0);
static wchar_t request_path[MAX_PATH]{};
static bool enabled=false;

static bool frame() noexcept {
    return enabled && !thread_changed && frame_thread
        && frame_thread==GetCurrentThreadId();
}
static authority::Context context() noexcept {
    uintptr_t game=0; int32_t date=0;
    if (!read(base+0x233fe58,game) || !read(game+0x1dd0,date)) date=0;
    return {observation_creation,GetTickCount64(),date};
}
static authority::ObjectRef object_ref(const RivalCommandObjectRef& ref) noexcept {
    return {ref.address,ref.generation};
}
static authority::NativeHeader header(const RivalCommandShape& shape) noexcept {
    return {shape.raw10,shape.raw38,shape.raw3c,shape.raw40,
        static_cast<int32_t>(shape.raw44),shape.origin48,shape.flags4a,
        shape.reserved4b,shape.sequence4c};
}
static bool payload_matches(const Binding& b,const RivalCommandShape& s) noexcept {
    const bool set=b.request.command==wire::CommandKind::set_rival;
    return s.matched && s.readable && s.discriminator==0x165
        && s.kind==(set?rival_command_set:rival_command_remove)
        && s.raw44==(set?0x2faeu:0x2fafu)
        && s.actor50==b.payload.actor && s.target58==b.payload.target
        && !s.old_rival60 && observation_country_handle(s.actor50)
        && observation_country_handle(s.target58);
}
static bool world_transport(uintptr_t& dispatcher,uintptr_t& transport) noexcept {
    uintptr_t game=0,server=0,world=0,vptr=0,method=0,host=0,ring=0;
    return read(base+0x233fe58,game) && read(game+0x1e00,server)
        && read(server+0x330,world) && read(world+0x370,dispatcher)
        && read(dispatcher+0x58,transport) && read(transport,vptr)
        && vptr==base+0x1d95fd8 && read(vptr+0x30,method)
        && method==reinterpret_cast<uintptr_t>(&bridge_transport_stub)
        && bridge_transport_original==reinterpret_cast<void*>(base+0x1580270)
        && read(transport+0x70,host) && host==dispatcher
        && read(transport+0x118,ring) && ring>=0x10000;
}
static void reason(Binding& b,const char* value) noexcept {
    snprintf(b.reason,sizeof(b.reason),"%s",value?value:"UNKNOWN");
}
static void invalidate(Binding& b,const char* value) noexcept {
    if (b.consumed || b.done) return;
    if (b.seed.seed_serial) ledger.revoke_request(context(),b.seed);
    b.invalidated=true;
    b.done=true;
    reason(b,value);
}
static void cleanup(void* command) noexcept {
    if (!command) return;
    auto s=rival_command_capture(command);
    auto ref=rival_command_registry_lookup(s.address,s.kind);
    reinterpret_cast<void* (*)(void*,unsigned)>(base+0x98940)(command,1);
    rival_command_registry_release(ref);
}
static void* construct(const wire::ExecutionRequest& request,uint64_t actor,
    uint64_t target) noexcept {
    auto* object=static_cast<unsigned char*>(
        reinterpret_cast<void* (*)(size_t)>(base+0x1a33230)(0x60));
    if (!object) return nullptr;
    memset(object,0,0x60);
    const bool set=request.command==wire::CommandKind::set_rival;
    const uintptr_t vptr=base+(set?0x1c55138:0x1c54a68);
    const int32_t discriminator=0x165,unset=-1;
    const uint64_t short_capacity=15,initial_header=0xffff;
    const uint32_t selector=set?0x2fae:0x2faf;
    memcpy(object,&vptr,8); memcpy(object+8,&discriminator,4);
    memcpy(object+0x30,&short_capacity,8);
    memcpy(object+0x38,&unset,4); memcpy(object+0x44,&selector,4);
    memcpy(object+0x48,&initial_header,8);
    memcpy(object+0x50,&actor,8); memcpy(object+0x58,&target,8);
    return object;
}
} // namespace rival_execution_detail

static void rival_command_observer_on_serialization(const RivalCommandEvent& e) {
    using namespace rival_execution_detail;
    if (!frame() || e.thread!=frame_thread) return;
    uintptr_t dispatcher=0,transport=0;
    if (!world_transport(dispatcher,transport) || e.transport!=transport
        || e.outgoing!=e.source.address) return;
    for (auto& b:bindings) {
        if (!b.used || b.invalidated || b.serialized
            || b.source!=object_ref(e.source_ref) || !payload_matches(b,e.source)) continue;
        const auto value=header(e.source);
        const auto result=ledger.serialize_source(context(),b.seed,b.source,b.payload,value);
        if (result.ok()) { b.serialized=true; b.header=value; }
        else invalidate(b,authority::error_name(result.code));
        return;
    }
}

static void rival_command_observer_on_load(const RivalCommandEvent& e) {
    using namespace rival_execution_detail;
    if (!frame() || e.thread!=frame_thread || !e.native_return_matches
        || e.native_return!=base+0x15808f2) return;
    uintptr_t dispatcher=0,transport=0;
    if (!world_transport(dispatcher,transport) || e.transport!=transport
        || e.peer!=transport || !e.peer_readable) return;
    for (auto& b:bindings) {
        if (!b.used || b.invalidated || !b.serialized || b.claimed
            || b.source.address!=e.outgoing || !payload_matches(b,e.target)) continue;
        const auto loaded=object_ref(e.target_ref);
        auto result=ledger.load_native(context(),b.seed,loaded,header(e.target),b.payload,true);
        if (result.result.ok()) { b.loaded=loaded; b.claim=result.ticket; b.claimed=true; }
        else invalidate(b,authority::error_name(result.result.code));
        return;
    }
}

static void rival_command_observer_on_clone(const RivalCommandEvent& e) {
    using namespace rival_execution_detail;
    if (!frame() || e.thread!=frame_thread || !e.native_return_matches
        || e.native_return!=base+0x15801e2 || !e.receiver_readable) return;
    uintptr_t dispatcher=0,transport=0;
    if (!world_transport(dispatcher,transport) || e.receiver!=transport) return;
    for (auto& b:bindings) {
        if (!b.used || b.invalidated || !b.claimed || b.postcloned
            || b.loaded!=object_ref(e.source_ref) || !payload_matches(b,e.source)
            || !payload_matches(b,e.target)) continue;
        authority::CloneProof proof{b.loaded,object_ref(e.target_ref),b.payload,
            header(e.source),header(e.target)};
        auto result=ledger.clone_native(context(),b.claim,proof);
        if (result.ok()) { b.target=proof.target; b.postcloned=true; }
        else invalidate(b,authority::error_name(result.code));
        return;
    }
}

static void rival_command_observer_on_destruction(const RivalCommandEvent& e) {
    using namespace rival_execution_detail;
    if (!frame() || e.thread!=frame_thread) return;
    const auto ref=object_ref(e.source_ref);
    for (auto& b:bindings) {
        if (!b.used || b.done || b.consumed) continue;
        if (ref==b.source) {
            const auto result=ledger.detach_source(context(),b.seed,
                authority::DetachKind::source,ref);
            if (result.code==authority::ErrorCode::source_destroyed)
                invalidate(b,"SOURCE_DESTROYED_BEFORE_SERIALIZATION");
        } else if (b.claimed && ref==b.loaded) {
            const auto result=ledger.detach_source(context(),b.seed,
                authority::DetachKind::loaded,ref);
            if (result.code==authority::ErrorCode::loaded_destroyed)
                invalidate(b,"LOADED_DESTROYED_BEFORE_CLONE");
        } else if (b.postcloned && ref==b.target) {
            ledger.destroy_target(context(),b.claim,ref);
            invalidate(b,"TARGET_DESTROYED_BEFORE_EXECUTION");
        }
    }
}

static int rival_execution_begin(void* object,unsigned kind) noexcept {
    using namespace rival_execution_detail;
    if (!frame() || !control_ready() || (kind!=1 && kind!=3)) return -1;
    const auto shape=rival_command_capture(object);
    const auto ref=object_ref(rival_command_registry_lookup(shape.address,shape.kind));
    for (unsigned index=0;index<capacity;++index) {
        auto& b=bindings[index];
        if (!b.used || b.done || b.invalidated || b.consumed || !b.submitted
            || !b.postcloned || b.target!=ref || !payload_matches(b,shape)) continue;
        const auto evaluation=rival_evaluate(b.request.action_id,b.payload.actor,b.payload.target);
        if (!evaluation.complete || !evaluation.available) {
            invalidate(b,"NATIVE_RULES_CHANGED"); return -1;
        }
        const auto result=ledger.consume(context(),b.claim,ref,b.payload,header(shape));
        if (!result.ok()) {
            invalidate(b,authority::error_name(result.code)); return -1;
        }
        b.before=evaluation.state;
        b.cost=kind==1?0:evaluation.diplomatic_power_cost;
        b.consumed=true;
        return static_cast<int>(index);
    }
    return -1;
}

static void rival_execution_finish(unsigned index) noexcept {
    using namespace rival_execution_detail;
    if (!frame() || index>=capacity) return;
    auto& b=bindings[index];
    if (!b.used || !b.consumed || b.done) return;
    uintptr_t country=0;
    const bool read_ok=insult_query_country(b.payload.actor,country)
        && rival_query_membership(country,b.payload.target,b.after);
    const bool set=b.request.command==wire::CommandKind::set_rival;
    b.relationship_verified=read_ok
        && b.before.active!=set && b.after.active==set
        && b.after.count==b.before.count+(set?1:-1)
        && b.cost>=0 && b.before.diplomatic_power_raw-b.after.diplomatic_power_raw==b.cost;
    b.done=true;
    reason(b,b.relationship_verified?"NATIVE_RIVAL_EXECUTED":"NATIVE_CONSEQUENCE_UNVERIFIED");
}

static bool rival_execution_set_paths(const wchar_t* directory) noexcept {
    using namespace rival_execution_detail;
    if (!directory || swprintf(request_path,MAX_PATH,L"%ls\\rival-execute.req",directory)<0)
        return false;
    return GetFileAttributesW(request_path)==INVALID_FILE_ATTRIBUTES || DeleteFileW(request_path);
}

static bool rival_execution_install() noexcept {
    using namespace rival_execution_detail;
    if (!observation_creation || !request_path[0]
        || rival_command_observer_install_state!=2
        || !rival_authority_detail::rival_authority_installed) return false;
    ledger.reset_session_epoch(observation_creation);
    enabled=true;
    return true;
}

static void rival_execution_tick() {
    using namespace rival_execution_detail;
    if (!frame() || !control_ready()) return;
    const auto current=context();
    ledger.invalidate_expired(current);
    for (auto& b:bindings) {
        if (b.used && !b.done && !b.consumed
            && (current.current_tick>b.request.expiry_tick
                || current.current_date!=b.request.date_raw))
            invalidate(b,"REQUEST_CONTEXT_EXPIRED");
    }
    char bytes[wire::kMaxWireBytes]{}; DWORD size=0;
    if (!execution_read_request_file(request_path,bytes,sizeof(bytes),size)) return;
    wire::ExecutionRequest request{};
    const auto parsed=wire::parse_request(bytes,size,request);
    if (!parsed.ok()) {
        line("{\"event\":\"native_rival_wire_rejected\",\"submitted\":false}\n"); return;
    }
    for (const auto& b:bindings)
        if (b.used && !strcmp(b.request.request_id,request.request_id)) return;
    rival_execution_detail::Binding* selected=nullptr;
    for (auto& b:bindings) if (!b.used) { selected=&b; break; }
    if (!selected) {
        line("{\"event\":\"native_rival_capacity_exhausted\",\"submitted\":false}\n"); return;
    }
    auto& b=*selected;
    b.used=true; b.request=request;
    const auto check=wire::validate_context(request,observation_creation,
        current.current_tick,current.current_date);
    if (!check.ok()) { invalidate(b,wire::context_error_name(check.error)); return; }
    uint64_t actor=0,target=0; uintptr_t dispatcher=0,transport=0;
    if (!alliance_query_country(request.actor,actor)
        || !alliance_query_country(request.recipient,target)
        || !observation_country_handle(actor) || !observation_country_handle(target)
        || actor==target || !world_transport(dispatcher,transport)) {
        invalidate(b,"NATIVE_CONTEXT_UNAVAILABLE"); return;
    }
    const auto evaluation=rival_evaluate(request.action_id,actor,target);
    if (!evaluation.complete || !evaluation.available) {
        invalidate(b,"NATIVE_PREFLIGHT_UNAVAILABLE"); return;
    }
    b.payload={authority::Family::rival,
        request.command==wire::CommandKind::set_rival?authority::CommandKind::set_rival:
            authority::CommandKind::remove_rival,actor,target,0,request.date_raw};
    void* command=construct(request,actor,target);
    if (!command) { invalidate(b,"NATIVE_ALLOCATION_FAILED"); return; }
    auto shape=rival_command_capture(command);
    const auto source=rival_command_registry_ensure(shape.address,shape.kind,true);
    b.source=object_ref(source);
    const auto seeded=ledger.seed(current,request.request_id,b.payload,b.source,request.expiry_tick);
    b.seed=seeded.receipt;
    if (!seeded.result.ok() || !payload_matches(b,shape)) {
        cleanup(command); invalidate(b,"AUTHORITY_SEED_FAILED"); return;
    }
    // The normal UI submission wrapper accepts the command directly.  Native
    // transport owns a successful submission; never touch that source again.
    const bool accepted=reinterpret_cast<bool (*)(void*,void*)>(base+0x14ca1d0)(
        reinterpret_cast<void*>(dispatcher),command);
    if (!accepted) { cleanup(command); invalidate(b,"NATIVE_SUBMISSION_REJECTED"); return; }
    if (!b.serialized || !b.claimed || b.invalidated) {
        invalidate(b,"NATIVE_TRANSPORT_PROOF_MISSING"); return;
    }
    b.submitted=true;
}

static void rival_execution_flush() {
    using namespace rival_execution_detail;
    if (!frame()) return;
    for (auto& b:bindings) {
        if (!b.used) continue;
        char message[1800]{};
        if (!b.submission_emitted && (b.submitted || b.done)) {
            snprintf(message,sizeof(message),
                "{\"event\":\"native_rival_submission_result\",\"family\":\"rival\",\"session_id\":\"%lu-%llx\",\"request_id\":\"%s\",\"action_id\":\"%s\",\"actor\":\"%s\",\"recipient\":\"%s\",\"phase\":\"initiate\",\"date_raw\":%d,\"submitted\":%s,\"request_binding_verified\":%s,\"protocol_verified\":%s,\"native_origin\":%u,\"native_flags\":%u,\"native_sequence\":%u,\"reason_code\":\"%s\"}\n",
                static_cast<unsigned long>(GetCurrentProcessId()),
                static_cast<unsigned long long>(observation_creation),b.request.request_id,
                b.request.action_id,b.request.actor,b.request.recipient,b.request.date_raw,
                b.submitted?"true":"false",b.submitted?"true":"false",b.submitted?"true":"false",
                b.header.origin48,b.header.flags4a,b.header.sequence4c,b.reason);
            line(message); b.submission_emitted=true;
        }
        if (!b.done || b.result_emitted || !b.submitted) continue;
        const bool executed=b.consumed && b.relationship_verified;
        snprintf(message,sizeof(message),
            "{\"event\":\"native_rival_execution_result\",\"family\":\"rival\",\"session_id\":\"%lu-%llx\",\"request_id\":\"%s\",\"action_id\":\"%s\",\"actor\":\"%s\",\"recipient\":\"%s\",\"phase\":\"initiate\",\"date_raw\":%d,\"status\":\"%s\",\"executed\":%s,\"request_binding_verified\":true,\"native_rule_verified\":%s,\"relationship_verified\":%s,\"before_active\":%s,\"after_active\":%s,\"dip_before\":%d,\"dip_after\":%d,\"cost_raw\":%d,\"rival_count_before\":%d,\"rival_count_after\":%d,\"reason_code\":\"%s\"}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),
            static_cast<unsigned long long>(observation_creation),b.request.request_id,
            b.request.action_id,b.request.actor,b.request.recipient,b.request.date_raw,
            executed?"executed":b.consumed?"unknown":"invalidated",executed?"true":"false",
            b.consumed?"true":"false",b.relationship_verified?"true":"false",
            b.before.active?"true":"false",b.after.active?"true":"false",
            b.before.diplomatic_power_raw,b.after.diplomatic_power_raw,b.cost,
            b.before.count,b.after.count,b.reason);
        line(message); b.result_emitted=true;
    }
}
