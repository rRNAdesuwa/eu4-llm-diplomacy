// Controlled native offer_alliance execution and proof-bound entry handling.
//
// This include is intentionally placed after query/protocol/transport
// observers.  The request file is the only source of an execution seed.  A
// native FRA state-0 action observed without a live ledger target is rejected;
// every other command is forwarded to its original executor exactly once.

#include <new>
#include "alliance-inbound-inspection-event.h"

namespace alliance_execution_detail {

// Keep the existing bounded command-entry observation in the execution
// wrapper.  It records every generic command before the authority gate.
extern "C" int bridge_response_observe(void* value);

using bridge::alliance_authority::AlliancePayload;
using bridge::alliance_authority::ActionFamily;
using bridge::alliance_authority::AllianceAuthorityLedger;
using bridge::alliance_authority::ClaimTicket;
using bridge::alliance_authority::CloneProof;
using bridge::alliance_authority::Context;
using bridge::alliance_authority::ErrorCode;
using bridge::alliance_authority::NativeHeader;
using bridge::alliance_authority::ObjectRef;
using bridge::alliance_authority::Phase;
using bridge::alliance_authority::SeedReceipt;

using bridge::alliance_execution_wire::ExecutionRequest;
using bridge::alliance_inbound_response_wire::InspectionRequest;
using bridge::alliance_inbound_response_wire::ResponseRequest;

static bool execution_unilateral_family(ActionFamily family) noexcept {
    return family==ActionFamily::improve_relations || family==ActionFamily::spy_network
        || family==ActionFamily::guarantee || family==ActionFamily::insult
        || family==ActionFamily::declare_war || family==ActionFamily::curry_favors;
}

static bool execution_read_after(const AlliancePayload& payload,bool& relation_after) noexcept;

constexpr unsigned kBindingCapacity=64;
constexpr unsigned kInvalidBinding=0xffffu;
constexpr uintptr_t kDispatcherRva=0x14ca110;
constexpr uintptr_t kConstructorRva=0x50f780;
constexpr uintptr_t kWrapperMethodRva=0x4e9960;
constexpr uintptr_t kServerGetterRva=0x811ad0;
constexpr uintptr_t kWorldTransportRva=0x1580270;
constexpr uintptr_t kLoadReturnRva=0x15808f2;
constexpr uintptr_t kCloneReturnRva=0x15801e2;

#include "declarewar-execution-state.inc"
#include "peace-inbound-context.inc"
#include "peace-effect-state.inc"

struct ExecutionBinding {
    bool used=false;
    bool sender=false;
    bool response=false;
    bool transport_verified=false;
    bool claim_bound=false;
    bool postcloned=false;
    bool consumed=false;
    bool invalidated=false;
    bool submission_queued=false;
    bool response_queued=false;
    bool inbound_response_request=false;
    bool peace_handler_returned=false;
    bool alliance_before=false;
    bool alliance_before_verified=false;
    FavorGoldState favor_before{};
    FavorGoldState favor_after{};
    int32_t favor_amount_raw=0;
    bool favor_before_verified=false;
    bool favor_after_verified=false;
    bool favor_amount_verified=false;
    bool favor_effect_verified=false;
    FavorTradeState favor_trade_before{};
    FavorTradeState favor_trade_after{};
    int32_t favor_trade_amount_raw=0;
    bool favor_trade_before_verified=false;
    bool favor_trade_after_verified=false;
    bool favor_trade_amount_verified=false;
    bool favor_trade_effect_verified=false;
    int32_t gift_ducats=0;
    GiftResourceState gift_before{};
    GiftResourceState gift_after{};
    int32_t gift_amount_raw=0;
    bool gift_before_verified=false;
    bool gift_after_verified=false;
    bool gift_effect_verified=false;
    InfluenceResourceState influence_before{};
    InfluenceResourceState influence_after{};
    bool influence_before_verified=false;
    bool influence_after_verified=false;
    bool influence_effect_verified=false;
    bool diplomat_required=false;
    bool diplomat_context_verified=false;
    unsigned diplomat_available_count=0;
    bool diplomat_assignment_verified=false;
    unsigned parent_slot=kInvalidBinding;
    unsigned response_slot=kInvalidBinding;
    ExecutionRequest request{};
    bridge::peace_execution_wire::PeaceExecutionRequest peace_request{};
    bool peace_effects_supported=false;
    char peace_war_id[30]{};
    ResponseRequest response_request{};
    uint64_t pending_proposal_id=0;
    uint64_t pending_generation=0;
    char ledger_request_id[bridge::alliance_authority::kMaxRequestId+1]{};
    Phase phase=Phase::initiate;
    SeedReceipt seed{};
    ClaimTicket claim{};
    ObjectRef expected_wrapper{};
    ObjectRef expected_action{};
    uintptr_t constructor_action=0;
    ObjectRef incoming_wrapper{};
    ObjectRef incoming_action{};
    ObjectRef target_wrapper{};
    ObjectRef target_action{};
    AlliancePayload payload{};
    InsultEffectState insult_before{};
    VassalQueryState vassal_before{};
    int32_t war_id_before=-1;
    int32_t stability_before_raw=0;
    bool stability_before_verified=false;
    PeaceEffectState peace_effects_before{};
    NativeHeader source_header{};
    NativeHeader final_entry_header{};
    ProtocolWrapperShape source{};
    ProtocolWrapperShape loaded{};
    ProtocolWrapperShape target{};
};

struct SubmissionResult {
    char request_id[65]{};
    char session_id[28]{};
    char actor[4]{};
    char recipient[4]{};
    char action_id[28]{};
    char phase[9]{};
    int32_t date_raw=0;
    bool submitted=false;
    uint16_t native_origin=0;
    unsigned char native_flags=0;
    uint32_t native_sequence=0;
    bool inbound_response=false;
    char casus_belli[129]{};
    int32_t war_goal_province=-1;
    char war_goal_beneficiary[4]{};
    bridge::CountryTagList call_allies{};
    bridge::CountryTagList promise_land_to{};
    bridge::CountryTagList co_belligerents{};
    FavorGoldState favor_before{};
    int32_t favor_amount_raw=0;
    bool favor_before_verified=false;
    bool favor_amount_verified=false;
    FavorTradeState favor_trade_before{};
    FavorTradeState favor_trade_after{};
    int32_t favor_trade_amount_raw=0;
    bool favor_trade_before_verified=false;
    bool favor_trade_after_verified=false;
    bool favor_trade_amount_verified=false;
    bool favor_trade_effect_verified=false;
    int32_t gift_ducats=0;
    GiftResourceState gift_before{};
    GiftResourceState gift_after{};
    int32_t gift_amount_raw=0;
    bool gift_before_verified=false;
    bool gift_after_verified=false;
    bool gift_amount_verified=false;
    bool gift_effect_verified=false;
    InfluenceResourceState influence_before{};
    InfluenceResourceState influence_after{};
    bool influence_before_verified=false;
    bool influence_after_verified=false;
    bool influence_effect_verified=false;
    bool diplomat_required=false;
    bool diplomat_context_verified=false;
    unsigned diplomat_available_count=0;
    bool diplomat_assignment_verified=false;
    bool curry_before_active=false;
};

struct ResponseResult {
    char request_id[65]{};
    char session_id[28]{};
    char actor[4]{};
    char recipient[4]{};
    char action_id[28]{};
    char phase[9]{};
    int32_t date_raw=0;
    char outcome[9]{};
    int32_t native_state=0;
    bool alliance_after=false;
    bool alliance_before=false;
    bool response_verified=false;
    bool request_binding_verified=false;
    bool pending_removed=false;
    bool inbound_response=false;
    FavorGoldState favor_before{};
    FavorGoldState favor_after{};
    int32_t favor_amount_raw=0;
    bool favor_before_verified=false;
    bool favor_after_verified=false;
    bool favor_amount_verified=false;
    bool favor_effect_verified=false;
    FavorTradeState favor_trade_before{};
    FavorTradeState favor_trade_after{};
    int32_t favor_trade_amount_raw=0;
    bool favor_trade_before_verified=false;
    bool favor_trade_after_verified=false;
    bool favor_trade_amount_verified=false;
    bool favor_trade_effect_verified=false;
    int32_t gift_ducats=0;
    int32_t gift_amount_raw=0;
    GiftResourceState gift_before{};
    GiftResourceState gift_after{};
    bool gift_before_verified=false;
    bool gift_after_verified=false;
    bool gift_effect_verified=false;
    InfluenceResourceState influence_before{};
    InfluenceResourceState influence_after{};
    bool influence_before_verified=false;
    bool influence_after_verified=false;
    bool influence_effect_verified=false;
    bool diplomat_required=false;
    bool diplomat_context_verified=false;
    unsigned diplomat_available_count=0;
    bool diplomat_assignment_verified=false;
    int32_t insult_id=-1,modifier_before=0,modifier_after=0,prestige_before=0,prestige_after=0;
    char casus_belli[129]{};
    int32_t war_goal_province=-1;
    char war_goal_beneficiary[4]{};
    int32_t war_id=-1,stability_before_raw=0,stability_after_raw=0;
    bool war_identity_verified=false,stability_verified=false;
    uint64_t private_war_reference=0;
    bridge::CountryTagList call_allies{};
    bridge::CountryTagList promise_land_to{};
    bridge::CountryTagList co_belligerents{};
};

struct SenderScope {
    bool active=false;
    unsigned binding_slot=kInvalidBinding;
};

struct ResponseScope {
    bool active=false;
    unsigned parent_slot=kInvalidBinding;
};

static AllianceAuthorityLedger execution_ledger(0);
static bool execution_initialized=false;
static bool execution_handler_enabled=false;
static wchar_t execution_request_path[MAX_PATH]{};
static wchar_t execution_authority_test_path[MAX_PATH]{};
static std::uint64_t execution_authority_tests_consumed=0;
static wchar_t inbound_inspection_request_path[MAX_PATH]{};
static wchar_t inbound_response_request_path[MAX_PATH]{};
static bool inbound_response_paths_ready=false;
static bool inbound_response_handler_enabled=false;
static ExecutionBinding execution_bindings[kBindingCapacity]{};
static volatile LONG64 execution_generation=0;
static SRWLOCK execution_result_lock=SRWLOCK_INIT;
static SubmissionResult execution_submission_results[kBindingCapacity]{};
static unsigned execution_submission_head=0,execution_submission_size=0;
static ResponseResult execution_response_results[kBindingCapacity]{};
static unsigned execution_response_head=0,execution_response_size=0;
static volatile LONG execution_result_dropped=0;
static thread_local SenderScope execution_sender_scope{};
static thread_local ResponseScope execution_response_scope{};
static void execution_peace_submission(const ExecutionBinding& binding,
    const ProtocolWrapperShape& entry) noexcept;
static void execution_peace_response(const ExecutionBinding& binding,
    int32_t state,bool war_after,bool verified,bool pending_removed) noexcept;
static void execution_peace_inbound_unknown(const ResponseRequest& request,
    int32_t state,bool war_after,bool pending_removed) noexcept;
static bool execution_peace_war_state(const AlliancePayload& payload,bool& active) noexcept;
// Native AI also calls this executor directly.  Retain its vtable hook, and
// route the function entry through the same gate before any native effects.
static const unsigned char execution_entry_signature[18]={
    0x48,0x89,0x5c,0x24,0x18,0x48,0x89,0x6c,0x24,0x20,
    0x56,0x57,0x41,0x56,0x48,0x83,0xec,0x20};
static unsigned char execution_entry_replacement[18]{};
static unsigned char* execution_entry_block=nullptr;
static unsigned char* execution_entry_original=nullptr;
static RUNTIME_FUNCTION execution_entry_runtime_function{};
static bool execution_entry_runtime_registered=false;
static bool execution_entry_published=false;
static bridge_entry_patch::PatchPlan execution_entry_patch_plan{};

static uint64_t execution_next_generation() noexcept {
    return static_cast<uint64_t>(InterlockedIncrement64(&execution_generation));
}

static Context execution_context() noexcept {
    return Context{observation_creation,GetTickCount64()};
}

static bool execution_set_inbound_response_paths(const wchar_t* directory) noexcept {
    inbound_inspection_request_path[0]=0;
    inbound_response_request_path[0]=0;
    inbound_response_paths_ready=false;
    if (!directory || !directory[0]) return false;
    if (swprintf(inbound_inspection_request_path,MAX_PATH,
            L"%ls\\diplomacy-inbound-query.req",directory)<0
        || swprintf(inbound_response_request_path,MAX_PATH,
            L"%ls\\diplomacy-respond.req",directory)<0) {
        inbound_inspection_request_path[0]=0;
        inbound_response_request_path[0]=0;
        return false;
    }
    if (GetFileAttributesW(inbound_inspection_request_path)!=INVALID_FILE_ATTRIBUTES
        && !DeleteFileW(inbound_inspection_request_path)) return false;
    if (GetFileAttributesW(inbound_response_request_path)!=INVALID_FILE_ATTRIBUTES
        && !DeleteFileW(inbound_response_request_path)) return false;
    inbound_response_paths_ready=true;
    return true;
}

static bool execution_inbound_response_install() noexcept {
    inbound_response_handler_enabled=inbound_response_paths_ready
        && execution_initialized && execution_handler_enabled;
    return inbound_response_handler_enabled;
}

static NativeHeader execution_header(const ProtocolWrapperShape& shape) noexcept {
    return NativeHeader{shape.origin48,shape.flags4a,shape.sequence4c};
}

static bool execution_payload(const LifecycleActionShape& shape,
    AlliancePayload& payload) noexcept {
    if (!shape.readable || !shape.matched || !shape.handles_canonical) return false;
    payload.actor10=shape.actor10;
    payload.mirror18=shape.mirror18;
    payload.recipient20=shape.recipient20;
    payload.date28=static_cast<uint64_t>(static_cast<uint32_t>(shape.date28));
    payload.date2c=static_cast<uint64_t>(static_cast<uint32_t>(shape.date2c));
    payload.envoy30=static_cast<uint64_t>(static_cast<uint32_t>(shape.envoy30));
    payload.state34=static_cast<uint64_t>(static_cast<uint32_t>(shape.state34));
    payload.variant38=shape.variant38;
    payload.proposal3c=static_cast<uint64_t>(static_cast<uint32_t>(shape.proposal3c));
    payload.family=shape.peace_offer?ActionFamily::peace:
        shape.favor_gold?ActionFamily::favor_gold:
        shape.favor_trust?ActionFamily::favor_trust:
        shape.favor_men?ActionFamily::favor_men:
        shape.curry_favors?ActionFamily::curry_favors:
        shape.gift?ActionFamily::gift:
        shape.influence?ActionFamily::influence:
        shape.declare_war?ActionFamily::declare_war:shape.vassalization?ActionFamily::vassalization:
        shape.insult?ActionFamily::insult:shape.military_access?ActionFamily::military_access:
        shape.support_independence?ActionFamily::support_independence:
        shape.guarantee?ActionFamily::guarantee:shape.spy_network?ActionFamily::spy_network:
        shape.improve_relations?ActionFamily::improve_relations:
        shape.royal_marriage?ActionFamily::royal_marriage:ActionFamily::alliance;
    payload.extra60=shape.extra60;
    payload.parameter40=shape.parameter40;
    payload.favor_cost40=shape.favor_cost40;
    payload.favor_amount44=shape.favor_amount44;
    payload.war=shape.war;
    payload.peace=shape.peace;
    return true;
}

static bool execution_same_payload(const ProtocolWrapperShape& left,
    const ProtocolWrapperShape& right) noexcept {
    AlliancePayload l{},r{};
    return left.identity && right.identity && left.readable && right.readable
        && left.prefix_readable && right.prefix_readable
        && left.raw10==right.raw10 && left.raw38==right.raw38
        && left.raw3c==right.raw3c && left.raw40==right.raw40
        && left.raw44==right.raw44 && execution_payload(left.payload,l)
        && execution_payload(right.payload,r) && l==r;
}

static bool execution_world_dispatcher(uintptr_t& dispatcher,
    uintptr_t& transport) noexcept {
    uintptr_t game=0,server=0,server_vtable=0,getter=0,world=0;
    uintptr_t ui=0,ui_context=0,ui_dispatcher=0,transport_vtable=0,counter=0;
    if (!read(base+0x233fe58,game) || !read(game+0x1e00,server)
        || !read(server,server_vtable) || !read(server_vtable+0x80,getter)
        || getter!=base+kServerGetterRva
        || !read(server+0x330,world) || !read(world+0x370,dispatcher)
        || !read(base+0x2349550,ui) || !read(ui+0x330,ui_context)
        || !read(ui_context+0x370,ui_dispatcher) || ui_dispatcher!=dispatcher
        || !read(dispatcher+0x58,transport)
        || !read(transport,transport_vtable)
        || !read(transport+0x128,counter)
        || counter<0x10000) return false;
    using ServerGetter=void* (*)(void*);
    void* getter_context=reinterpret_cast<ServerGetter>(getter)(
        reinterpret_cast<void*>(server));
    if (reinterpret_cast<uintptr_t>(getter_context)!=dispatcher) return false;
    uintptr_t submit=0;
    if (!read(transport_vtable+transport_vtable_slot,submit)) return false;
    const bool original_transport=submit==base+kWorldTransportRva;
    const bool installed_transport=submit==reinterpret_cast<uintptr_t>(&bridge_transport_stub)
        && bridge_transport_original==reinterpret_cast<void*>(base+kWorldTransportRva);
    return original_transport || installed_transport;
}

static bool execution_target_allowed(const char* recipient,const char* action_id) noexcept {
    // Every resolved canonical recipient uses the native Dissolve selector
    // and rules. Offer's previously reviewed target scope is unchanged.
    if (action_id && (strcmp(action_id,"declare_war")==0
        || strcmp(action_id,"dissolve_alliance")==0
        || strcmp(action_id,"offer_royal_marriage")==0
        || strcmp(action_id,"break_royal_ties")==0
        || strcmp(action_id,"improve_relations")==0
        || strcmp(action_id,"stop_improving_relations")==0
        || strcmp(action_id,"build_spy_network")==0
        || strcmp(action_id,"stop_building_spy_network")==0
        || strcmp(action_id,"proclaim_guarantee")==0
        || strcmp(action_id,"revoke_guarantee")==0
        || strcmp(action_id,"support_independence")==0
        || strcmp(action_id,"revoke_support_independence")==0
        || strcmp(action_id,"ask_military_access")==0
        || strcmp(action_id,"cancel_military_access")==0
        || strcmp(action_id,"offer_vassalization")==0
        || strcmp(action_id,"cancel_vassalization")==0
        || strcmp(action_id,"trade_favors_for_gold")==0
        || strcmp(action_id,"trade_favors_for_trust")==0
        || strcmp(action_id,"trade_favors_for_men")==0
        || strcmp(action_id,"curry_favors")==0
        || strcmp(action_id,"stop_curry_favors")==0
        || strcmp(action_id,"send_gift")==0
        || strcmp(action_id,"influence_nation")==0
        || strcmp(action_id,"send_insult")==0 || strcmp(action_id,"scornful_insult")==0)) return recipient!=nullptr;
    return recipient && ((recipient[0]=='S' && recipient[1]=='A' && recipient[2]=='V')
        || (recipient[0]=='L' && recipient[1]=='I' && recipient[2]=='T'));
}

static bool execution_is_fra(uint64_t handle) noexcept {
    return static_cast<uint32_t>(handle&0xffffffu)==0x415246u;
}

static unsigned execution_free_binding() noexcept {
    for (unsigned index=0;index<kBindingCapacity;++index)
        if (!execution_bindings[index].used) return index;
    return kInvalidBinding;
}

static bool execution_binding_matches(const ExecutionBinding& binding,
    const ProtocolWrapperShape& shape) noexcept {
    return binding.used && shape.identity && shape.readable
        && shape.address==binding.target_wrapper.address
        && shape.action==binding.target_action.address;
}

static int execution_find_target(const ProtocolWrapperShape& shape) noexcept {
    for (unsigned index=0;index<kBindingCapacity;++index)
        if (execution_binding_matches(execution_bindings[index],shape)
            && execution_bindings[index].postcloned
            && !execution_bindings[index].consumed
            && !execution_bindings[index].invalidated) return static_cast<int>(index);
    return -1;
}

static int execution_find_action(uintptr_t action) noexcept {
    for (unsigned index=0;index<kBindingCapacity;++index) {
        const ExecutionBinding& binding=execution_bindings[index];
        if (!binding.used || binding.invalidated || binding.consumed) continue;
        if ((binding.constructor_action==action && !binding.consumed)
            || (binding.expected_action.address==action && !binding.consumed)
            || (binding.incoming_action.address==action && binding.claim_bound)
            || (binding.target_action.address==action && binding.postcloned))
            return static_cast<int>(index);
    }
    return -1;
}

// Before the native dispatcher receives the wrapper, ownership has not moved
// to the game.  Release the separately allocated wrapper through its verified
// deleting-destructor slot, then destroy the stack-owned alliance action.
static void execution_release_constructed(void* wrapper,unsigned char* action,
    bool action_constructed) noexcept {
    if (wrapper) {
        uintptr_t vtable=0,destructor=0;
        const uintptr_t address=reinterpret_cast<uintptr_t>(wrapper);
        if (read(address,vtable) && vtable==base+lifecycle_generic_wrapper_vtable_rva
            && read(vtable,destructor) && destructor>=base+0x1000
            && destructor<base+0x1b66000) {
            using WrapperDestructor=void* (*)(void*,unsigned);
            reinterpret_cast<WrapperDestructor>(destructor)(wrapper,1);
        }
    }
    if (action_constructed) {
        using ActionDestructor=void* (*)(void*,unsigned);
        uintptr_t vtable=0;
        if (read(reinterpret_cast<uintptr_t>(action),vtable)
            && vtable==base+0x1c80ab0)
            reinterpret_cast<ActionDestructor>(base+0x4ed5e0)(action,1);
        else if (vtable==base+lifecycle_peace_vtable_rva)
            reinterpret_cast<ActionDestructor>(base+0x598b90)(action,1);
        else if (vtable==base+lifecycle_insult_vtable_rva)
            reinterpret_cast<ActionDestructor>(base+lifecycle_insult_destructor_rva)(action,1);
        else if (vtable==base+lifecycle_favor_trust_vtable_rva)
            reinterpret_cast<ActionDestructor>(base+lifecycle_insult_destructor_rva)(action,1);
        else if (vtable==base+0x1c80d90)
            reinterpret_cast<ActionDestructor>(base+0x500550)(action,1);
        else if (vtable==base+lifecycle_improve_vtable_rva || vtable==base+lifecycle_spy_vtable_rva
            || vtable==base+unilateral_guarantee.vtable_rva || vtable==base+lifecycle_support_vtable_rva
            || vtable==base+lifecycle_military_access_vtable_rva
            || vtable==base+lifecycle_vassalization_vtable_rva
            || vtable==base+lifecycle_favor_gold_vtable_rva
            || vtable==base+lifecycle_favor_trust_vtable_rva
            || vtable==base+lifecycle_favor_men_vtable_rva
            || vtable==base+lifecycle_curry_favors_vtable_rva
            || vtable==base+lifecycle_influence_vtable_rva)
            reinterpret_cast<ActionDestructor>(base+lifecycle_destructor_rva)(action,1);
        else if (vtable==base+lifecycle_gift_vtable_rva)
            reinterpret_cast<ActionDestructor>(base+0x129500)(action,1);
        else reinterpret_cast<ActionDestructor>(base+lifecycle_destructor_rva)(action,0);
    }
}

static void execution_failure(const char* request_id,const char* reason) {
    char message[420];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_alliance_execution_rejected\",\"session_id\":\"%lu-%llx\",\"request_id\":\"%.64s\",\"reason\":\"%.96s\",\"submitted\":false}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),
        static_cast<unsigned long long>(observation_creation),request_id?request_id:"",reason?reason:"unknown");
    line(message);
}

static void execution_preflight_failure(const ExecutionRequest& request,const char* reason) {
    const bool no_diplomat=reason && !strcmp(reason,"NATIVE_DIPLOMAT_UNAVAILABLE");
    const bool context_unavailable=reason && !strcmp(reason,"NATIVE_DIPLOMAT_CONTEXT_UNAVAILABLE");
    char message[900];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_alliance_execution_rejected\",\"session_id\":\"%lu-%llx\",\"request_id\":\"%.64s\",\"action_id\":\"%.48s\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"%.16s\",\"date_raw\":%d,\"reason\":\"%.96s\",\"reason_code\":\"%.96s\",\"reason_source\":\"%s\",\"reason_stage\":\"%s\",\"submitted\":false,\"complete\":false}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),
        static_cast<unsigned long long>(observation_creation),request.request_id,
        request.action_id,request.actor,request.recipient,request.phase,request.date_raw,
        reason,reason,no_diplomat?"native_rule":"runtime_error",
        no_diplomat || context_unavailable?"diplomat_availability":"native_preflight");
    line(message);
}

static void execution_copy_text(char* destination,std::size_t capacity,
    const char* source) noexcept {
    if (!destination || capacity==0) return;
    std::size_t index=0;
    if (source) for (;index+1<capacity && source[index]!=0;++index)
        destination[index]=source[index];
    destination[index]=0;
}

static void execution_copy_external_id(char (&destination)[65],
    const ExecutionBinding& binding) noexcept {
    const char* source=binding.inbound_response_request
        ? binding.response_request.request_id : binding.request.request_id;
    execution_copy_text(destination,sizeof(destination),source);
}

static const char* execution_binding_session(const ExecutionBinding& binding) noexcept {
    return binding.inbound_response_request
        ? binding.response_request.session_id : binding.request.session_id;
}

static const char* execution_binding_actor(const ExecutionBinding& binding) noexcept {
    return binding.inbound_response_request
        ? binding.response_request.original_actor : binding.request.actor;
}

static const char* execution_binding_recipient(const ExecutionBinding& binding) noexcept {
    return binding.inbound_response_request
        ? binding.response_request.decision_country : binding.request.recipient;
}

static const char* execution_binding_action(const ExecutionBinding& binding) noexcept {
    return binding.inbound_response_request
        ? binding.response_request.action_id : binding.request.action_id;
}

static const char* execution_binding_phase(const ExecutionBinding& binding) noexcept {
    if (binding.inbound_response_request) return binding.response_request.decision;
    // Receipts refer to the external request. An NPC response belongs to its
    // parent's initiate request; native_state/outcome describe that response.
    return binding.request.phase;
}

static int32_t execution_binding_date(const ExecutionBinding& binding) noexcept {
    return binding.inbound_response_request
        ? binding.response_request.date_raw : binding.request.date_raw;
}

static bool execution_favor_effect_matches(const FavorGoldState& before,
    const FavorGoldState& after,int32_t amount,int32_t native_state) noexcept {
    if (!before.complete || !after.complete || amount<0 || before.cost_raw<0)
        return false;
    if (native_state==1) {
        // A rejection must not settle either side of the negotiation.
        return after.actor_treasury_raw==before.actor_treasury_raw
            && after.recipient_treasury_raw==before.recipient_treasury_raw
            && after.favors_raw==before.favors_raw
            && after.cost_raw==before.cost_raw;
    }
    if (native_state!=2) return false;
    // The actor receives the native amount and spends the favor cost. The
    // recipient is the payer; compare in int64 before narrowing so a corrupt
    // or saturated native write cannot pass as a valid proof.
    const int64_t actor_expected=static_cast<int64_t>(before.actor_treasury_raw)+amount;
    const int64_t recipient_expected=static_cast<int64_t>(before.recipient_treasury_raw)-amount;
    const int64_t favors_expected=static_cast<int64_t>(before.favors_raw)-before.cost_raw;
    return static_cast<int64_t>(after.actor_treasury_raw)==actor_expected
        && static_cast<int64_t>(after.recipient_treasury_raw)==recipient_expected
        && static_cast<int64_t>(after.favors_raw)==favors_expected
        && after.cost_raw==before.cost_raw;
}

static bool execution_favor_trade_effect_matches(bool trust,
    const FavorTradeState& before,const FavorTradeState& after,
    int32_t amount,int32_t native_state) noexcept {
    if (!before.complete || !after.complete || amount<0 || before.cost_raw<0)
        return false;
    if (native_state==1) {
        if (after.favors_raw!=before.favors_raw || after.cost_raw!=before.cost_raw)
            return false;
        if (trust) return after.recipient_trust_raw==before.recipient_trust_raw;
        return after.actor_manpower_raw==before.actor_manpower_raw
            && after.recipient_manpower_raw==before.recipient_manpower_raw;
    }
    if (native_state!=2) return false;
    // The native rules reject an empty favor balance, a capped trust target,
    // or a manpower transfer larger than the recipient's available pool. Keep
    // the post-effect proof subject to those same bounded preconditions so a
    // malformed or saturated native write cannot be reported as settled.
    if (before.favors_raw<before.cost_raw) return false;
    if (after.favors_raw!=static_cast<int64_t>(before.favors_raw)-before.cost_raw
        || after.cost_raw!=before.cost_raw) return false;
    if (trust) {
        if (before.recipient_trust_raw>=100) return false;
        const int64_t summed=static_cast<int64_t>(before.recipient_trust_raw)+amount;
        const int64_t expected=summed>100?100:summed;
        return after.recipient_trust_raw==expected;
    }
    if (before.recipient_manpower_raw<amount) return false;
    return after.actor_manpower_raw==static_cast<int64_t>(before.actor_manpower_raw)+amount
        && after.recipient_manpower_raw==static_cast<int64_t>(before.recipient_manpower_raw)-amount;
}

static bool execution_favor_trade_cost(bool trust,const AlliancePayload& payload,
    int32_t& cost) noexcept {
    if (trust) {
        cost=static_cast<int32_t>(payload.favor_cost40);
        return cost>=0;
    }
    if (!read(base+0x233f3c8,cost) || cost<0 || cost>2147483) return false;
    cost*=1000;
    return true;
}

static void execution_queue_submission(const ExecutionBinding& binding,
    const ProtocolWrapperShape& entry) noexcept {
    if (binding.payload.family==ActionFamily::peace) {
        execution_peace_submission(binding,entry); return;
    }
    SubmissionResult result{};
    execution_copy_external_id(result.request_id,binding);
    execution_copy_text(result.session_id,sizeof(result.session_id),execution_binding_session(binding));
    execution_copy_text(result.actor,sizeof(result.actor),execution_binding_actor(binding));
    execution_copy_text(result.recipient,sizeof(result.recipient),execution_binding_recipient(binding));
    execution_copy_text(result.action_id,sizeof(result.action_id),execution_binding_action(binding));
    execution_copy_text(result.phase,sizeof(result.phase),execution_binding_phase(binding));
    result.date_raw=execution_binding_date(binding);
    result.inbound_response=binding.inbound_response_request;
    memcpy(result.casus_belli,binding.request.casus_belli,sizeof(result.casus_belli));
    result.war_goal_province=binding.request.war_goal_province;
    memcpy(result.war_goal_beneficiary,binding.request.war_goal_beneficiary,sizeof(result.war_goal_beneficiary));
    result.call_allies=binding.request.call_allies;
    result.promise_land_to=binding.request.promise_land_to;
    result.co_belligerents=binding.request.co_belligerents;
    if (binding.payload.family==ActionFamily::favor_gold) {
        result.favor_before=binding.favor_before;
        result.favor_amount_raw=binding.favor_amount_raw;
        result.favor_before_verified=binding.favor_before_verified;
        result.favor_amount_verified=binding.favor_amount_verified;
    } else if (binding.payload.family==ActionFamily::favor_trust
        || binding.payload.family==ActionFamily::favor_men) {
        result.favor_trade_before=binding.favor_trade_before;
        result.favor_trade_amount_raw=binding.favor_trade_amount_raw;
        result.favor_trade_before_verified=binding.favor_trade_before_verified;
        result.favor_trade_amount_verified=binding.favor_trade_amount_verified;
    } else if (binding.payload.family==ActionFamily::curry_favors) {
        result.curry_before_active=binding.alliance_before;
        result.diplomat_required=binding.diplomat_required;
        result.diplomat_context_verified=binding.diplomat_context_verified;
        result.diplomat_available_count=binding.diplomat_available_count;
        result.diplomat_assignment_verified=binding.diplomat_assignment_verified;
    } else if (binding.payload.family==ActionFamily::gift) {
        result.gift_ducats=binding.request.gift_ducats;
        result.gift_amount_raw=binding.request.gift_amount_raw;
    }
    result.submitted=true;
    result.native_origin=entry.origin48;
    result.native_flags=entry.flags4a;
    result.native_sequence=entry.sequence4c;
    if (!TryAcquireSRWLockExclusive(&execution_result_lock)) {
        InterlockedIncrement(&execution_result_dropped); return;
    }
    if (execution_submission_size<kBindingCapacity) {
        execution_submission_results[(execution_submission_head+execution_submission_size)%kBindingCapacity]=result;
        ++execution_submission_size;
    } else InterlockedIncrement(&execution_result_dropped);
    ReleaseSRWLockExclusive(&execution_result_lock);
}

static void execution_queue_submission_failure(const ExecutionRequest& request) noexcept {
    SubmissionResult result{};
    memcpy(result.request_id,request.request_id,sizeof(result.request_id));
    memcpy(result.session_id,request.session_id,sizeof(result.session_id));
    memcpy(result.actor,request.actor,sizeof(result.actor));
    memcpy(result.recipient,request.recipient,sizeof(result.recipient));
    memcpy(result.action_id,request.action_id,sizeof(result.action_id));
    memcpy(result.phase,request.phase,sizeof(result.phase));
    result.date_raw=request.date_raw;
    memcpy(result.casus_belli,request.casus_belli,sizeof(result.casus_belli));
    result.war_goal_province=request.war_goal_province;
    memcpy(result.war_goal_beneficiary,request.war_goal_beneficiary,sizeof(result.war_goal_beneficiary));
    result.call_allies=request.call_allies;
    result.promise_land_to=request.promise_land_to;
    result.co_belligerents=request.co_belligerents;
    result.submitted=false;
    if (!TryAcquireSRWLockExclusive(&execution_result_lock)) {
        InterlockedIncrement(&execution_result_dropped); return;
    }
    if (execution_submission_size<kBindingCapacity) {
        execution_submission_results[(execution_submission_head+execution_submission_size)%kBindingCapacity]=result;
        ++execution_submission_size;
    } else InterlockedIncrement(&execution_result_dropped);
    ReleaseSRWLockExclusive(&execution_result_lock);
}

static void execution_queue_response(const ExecutionBinding& binding,
    int32_t native_state,bool alliance_after,bool verified,
    bool pending_removed) noexcept {
    if (binding.payload.family==ActionFamily::peace) {
        execution_peace_response(binding,native_state,alliance_after,verified,pending_removed); return;
    }
    ResponseResult result{};
    execution_copy_external_id(result.request_id,binding);
    execution_copy_text(result.session_id,sizeof(result.session_id),execution_binding_session(binding));
    execution_copy_text(result.actor,sizeof(result.actor),execution_binding_actor(binding));
    execution_copy_text(result.recipient,sizeof(result.recipient),execution_binding_recipient(binding));
    execution_copy_text(result.action_id,sizeof(result.action_id),execution_binding_action(binding));
    execution_copy_text(result.phase,sizeof(result.phase),execution_binding_phase(binding));
    result.date_raw=execution_binding_date(binding);
    result.inbound_response=binding.inbound_response_request;
    memcpy(result.casus_belli,binding.request.casus_belli,sizeof(result.casus_belli));
    result.war_goal_province=binding.request.war_goal_province;
    memcpy(result.war_goal_beneficiary,binding.request.war_goal_beneficiary,sizeof(result.war_goal_beneficiary));
    result.call_allies=binding.request.call_allies;
    result.promise_land_to=binding.request.promise_land_to;
    result.co_belligerents=binding.request.co_belligerents;
    result.native_state=native_state;
    result.alliance_after=alliance_after;
    result.alliance_before=binding.alliance_before;
    result.pending_removed=pending_removed;
    result.response_verified=verified && (!binding.inbound_response_request || pending_removed);
    result.request_binding_verified=verified && binding.consumed
        && binding.transport_verified && (!binding.inbound_response_request || pending_removed);
    if (binding.payload.family==ActionFamily::curry_favors) {
        result.diplomat_required=binding.diplomat_required;
        result.diplomat_context_verified=binding.diplomat_context_verified;
        result.diplomat_available_count=binding.diplomat_available_count;
        result.diplomat_assignment_verified=binding.diplomat_assignment_verified;
    }
    if (binding.payload.family==ActionFamily::gift) {
        const bool raw_accepted=native_state==0 && gift_resource_effect_matches(
            binding.gift_before,binding.gift_after,binding.gift_amount_raw,native_state);
        const bool raw_rejected=native_state==1 && gift_resource_rejection_matches(
            binding.gift_before,binding.gift_after,native_state);
        result.gift_ducats=binding.request.gift_ducats;
        result.gift_amount_raw=binding.gift_amount_raw;
        result.gift_before=binding.gift_before;
        result.gift_before_verified=binding.gift_before_verified;
        result.gift_after_verified=binding.gift_after_verified;
        result.gift_after=binding.gift_after;
        result.gift_effect_verified=raw_accepted || raw_rejected;
        result.native_state=raw_accepted?2:(raw_rejected?1:1);
        result.response_verified=result.response_verified && result.gift_effect_verified;
        result.request_binding_verified=result.request_binding_verified
            && result.gift_effect_verified;
        if (result.response_verified && result.request_binding_verified
            && (raw_accepted || raw_rejected))
            strcpy(result.outcome,raw_accepted?"accepted":"rejected");
        else strcpy(result.outcome,"unknown");
    } else if (binding.payload.family==ActionFamily::influence) {
        const bool raw_accepted=native_state==0 && influence_resource_effect_matches(
            binding.influence_before,binding.influence_after,native_state);
        const bool raw_rejected=native_state==1 && influence_resource_rejection_matches(
            binding.influence_before,binding.influence_after,native_state);
        result.influence_before=binding.influence_before;
        result.influence_after=binding.influence_after;
        result.influence_before_verified=binding.influence_before_verified;
        result.influence_after_verified=binding.influence_after_verified;
        result.influence_effect_verified=raw_accepted || raw_rejected;
        result.native_state=raw_accepted?2:(raw_rejected?1:1);
        result.response_verified=result.response_verified && result.influence_effect_verified;
        result.request_binding_verified=result.request_binding_verified
            && result.influence_effect_verified;
        if (result.response_verified && result.request_binding_verified
            && (raw_accepted || raw_rejected))
            strcpy(result.outcome,raw_accepted?"accepted":"rejected");
        else strcpy(result.outcome,"unknown");
    } else if (binding.payload.family==ActionFamily::favor_gold) {
        result.favor_before=binding.favor_before;
        result.favor_amount_raw=binding.favor_amount_raw;
        result.favor_before_verified=binding.favor_before_verified;
        result.favor_amount_verified=binding.favor_amount_verified;
        result.favor_after_verified=favor_gold_capture(binding.payload.actor10,
            binding.payload.recipient20,result.favor_after);
        result.favor_effect_verified=result.favor_before_verified
            && result.favor_after_verified && result.favor_amount_verified
            && execution_favor_effect_matches(result.favor_before,result.favor_after,
                result.favor_amount_raw,native_state);
        result.response_verified=result.response_verified && result.favor_effect_verified;
        result.request_binding_verified=result.request_binding_verified
            && result.favor_effect_verified;
        if (result.response_verified && result.request_binding_verified
            && (native_state==2 || native_state==1))
            strcpy(result.outcome,native_state==2?"accepted":"rejected");
        else strcpy(result.outcome,"unknown");
    }
    else if (binding.payload.family==ActionFamily::favor_trust
        || binding.payload.family==ActionFamily::favor_men) {
        const bool trust=binding.payload.family==ActionFamily::favor_trust;
        int32_t cost=0;
        result.favor_trade_before=binding.favor_trade_before;
        result.favor_trade_amount_raw=binding.favor_trade_amount_raw;
        result.favor_trade_before_verified=binding.favor_trade_before_verified;
        result.favor_trade_amount_verified=binding.favor_trade_amount_verified;
        result.favor_trade_after_verified=execution_favor_trade_cost(
            trust,binding.payload,cost)
            && favor_trade_capture(trust,binding.payload.actor10,
                binding.payload.recipient20,cost,result.favor_trade_after);
        result.favor_trade_effect_verified=result.favor_trade_before_verified
            && result.favor_trade_after_verified && result.favor_trade_amount_verified
            && execution_favor_trade_effect_matches(trust,result.favor_trade_before,
                result.favor_trade_after,result.favor_trade_amount_raw,native_state);
        result.response_verified=result.response_verified && result.favor_trade_effect_verified;
        result.request_binding_verified=result.request_binding_verified
            && result.favor_trade_effect_verified;
        if (result.response_verified && result.request_binding_verified
            && (native_state==2 || native_state==1))
            strcpy(result.outcome,native_state==2?"accepted":"rejected");
        else strcpy(result.outcome,"unknown");
    }
    else if (binding.payload.family==ActionFamily::vassalization && binding.phase==Phase::dissolve) {
        VassalQueryState after{};
        const bool readable=vassal_query_relation(binding.payload.actor10,binding.payload.recipient20,after);
        result.prestige_before=binding.vassal_before.prestige_raw;
        result.prestige_after=after.prestige_raw;
        result.response_verified=result.response_verified && readable;
    }
    else if (binding.payload.family==ActionFamily::declare_war) {
        DeclareWarExecutionState after{};
        const bool state=execution_declarewar_state(binding.payload.actor10,binding.payload.recipient20,after);
        result.war_id=after.war_id;
        result.private_war_reference=after.war_object;
        result.stability_before_raw=binding.stability_before_raw;
        result.stability_after_raw=after.stability_raw;
        result.war_identity_verified=state && after.war_id_verified;
        result.stability_verified=state && binding.stability_before_verified && after.stability_verified;
        result.response_verified=result.response_verified && state;
        if (result.response_verified && result.request_binding_verified
            && binding.alliance_before_verified && !binding.alliance_before
            && native_state==0 && alliance_after && after.active)
            strcpy(result.outcome,"executed");
        else strcpy(result.outcome,"unknown");
    }
    else if (binding.payload.family==ActionFamily::insult) {
        InsultEffectState after{};
        const bool state=insult_query_state(binding.payload.actor10,binding.payload.recipient20,
            binding.payload.parameter40>=0,after);
        result.insult_id=binding.payload.parameter40;
        result.modifier_before=binding.insult_before.modifier_raw;
        result.modifier_after=after.modifier_raw;
        result.prestige_before=binding.insult_before.prestige_raw;
        result.prestige_after=after.prestige_raw;
        result.response_verified=result.response_verified && state;
        if (result.response_verified && result.request_binding_verified
            && binding.alliance_before_verified && !binding.alliance_before
            && native_state==0 && after.active && after.modifier_raw<0)
            strcpy(result.outcome,"executed");
        else strcpy(result.outcome,"unknown");
    }
    else if (execution_unilateral_family(binding.payload.family)) {
        const bool start=strcmp(execution_binding_action(binding),"improve_relations")==0
            || strcmp(execution_binding_action(binding),"build_spy_network")==0
            || strcmp(execution_binding_action(binding),"proclaim_guarantee")==0
            || strcmp(execution_binding_action(binding),"curry_favors")==0;
        if (result.response_verified && result.request_binding_verified
            && binding.alliance_before_verified && native_state==0
            && binding.alliance_before!=start && alliance_after==start)
            strcpy(result.outcome,"executed");
        else strcpy(result.outcome,"unknown");
    }
    else if (binding.phase==Phase::dissolve && result.response_verified
        && result.request_binding_verified && binding.alliance_before_verified
        && binding.alliance_before && native_state==0 && !alliance_after)
        strcpy(result.outcome,"executed");
    else if (result.response_verified && result.request_binding_verified
        && native_state==2 && alliance_after) strcpy(result.outcome,"accepted");
    else if (result.response_verified && result.request_binding_verified
        && native_state==1 && !alliance_after) strcpy(result.outcome,"rejected");
    else strcpy(result.outcome,"unknown");
    if (!TryAcquireSRWLockExclusive(&execution_result_lock)) {
        InterlockedIncrement(&execution_result_dropped); return;
    }
    if (execution_response_size<kBindingCapacity) {
        execution_response_results[(execution_response_head+execution_response_size)%kBindingCapacity]=result;
        ++execution_response_size;
    } else InterlockedIncrement(&execution_result_dropped);
    ReleaseSRWLockExclusive(&execution_result_lock);
}

static void execution_make_ledger_id(char (&destination)[65],
    const ExecutionBinding& parent,uint64_t serial) noexcept {
    int written=snprintf(destination,sizeof(destination),"%.48s-r%llu",
        parent.request.request_id,static_cast<unsigned long long>(serial));
    if (written<0 || static_cast<unsigned>(written)>=sizeof(destination)) {
        snprintf(destination,sizeof(destination),"r%llu",static_cast<unsigned long long>(serial));
    }
}

static bool execution_response_endpoint(const AlliancePayload& parent,
    const AlliancePayload& response) noexcept {
    return parent.family==response.family && parent.extra60==response.extra60
        && ((parent.family!=ActionFamily::favor_trust
            && parent.family!=ActionFamily::favor_men)
            || (parent.favor_cost40==response.favor_cost40
                && parent.favor_amount44==response.favor_amount44))
        && (parent.family!=ActionFamily::peace || parent.peace==response.peace)
        && ((response.actor10==parent.actor10 && response.recipient20==parent.recipient20)
        || (response.actor10==parent.recipient20 && response.recipient20==parent.actor10));
}

static void execution_mark_invalid(ExecutionBinding& binding) noexcept {
    if (binding.inbound_response_request && !binding.consumed)
        inbound_pending_release(binding.pending_proposal_id,binding.pending_generation);
    binding.invalidated=true;
    binding.transport_verified=false;
}

static void execution_bind_sender(const ExecutionRequest& request,
    const ProtocolWrapperShape& source,const AlliancePayload& payload,
    unsigned binding_slot,uintptr_t constructor_action) noexcept {
    ExecutionBinding& binding=execution_bindings[binding_slot];
    binding=ExecutionBinding{};
    binding.used=true;
    binding.sender=true;
    binding.request=request;
    binding.phase=(strcmp(request.action_id,"dissolve_alliance")==0
        || strcmp(request.action_id,"break_royal_ties")==0
        || strcmp(request.action_id,"stop_improving_relations")==0
        || strcmp(request.action_id,"stop_building_spy_network")==0
        || strcmp(request.action_id,"stop_curry_favors")==0
        || strcmp(request.action_id,"revoke_guarantee")==0
        || strcmp(request.action_id,"revoke_support_independence")==0
        || strcmp(request.action_id,"cancel_military_access")==0
        || strcmp(request.action_id,"cancel_vassalization")==0)
        ?Phase::dissolve:Phase::initiate;
    memcpy(binding.ledger_request_id,request.request_id,sizeof(binding.ledger_request_id));
    binding.source=source;
    binding.payload=payload;
    binding.constructor_action=constructor_action;
    binding.expected_wrapper=ObjectRef{source.address,execution_next_generation()};
    binding.expected_action=ObjectRef{source.action,execution_next_generation()};
    Context context=execution_context();
    bridge::alliance_authority::SeedResult seeded=execution_ledger.seed(context,
        binding.ledger_request_id,payload,binding.phase,binding.expected_wrapper,
        binding.expected_action,context.current_tick+10000u);
    if (!seeded.result.ok()) {
        execution_mark_invalid(binding);
        execution_failure(request.request_id,bridge::alliance_authority::error_name(seeded.result.code));
        return;
    }
    binding.seed=seeded.receipt;
}

static bool execution_bind_inbound_response(const ResponseRequest& request,
    const InboundPendingView& pending,const ProtocolWrapperShape& source,
    const AlliancePayload& payload,unsigned binding_slot,
    uintptr_t constructor_action) noexcept {
    if (binding_slot>=kBindingCapacity || !source.identity || !source.readable
        || !source.prefix_readable) return false;
    const Phase phase=strcmp(request.decision,"accept")==0
        ? Phase::accept : Phase::reject;
    ExecutionBinding& binding=execution_bindings[binding_slot];
    binding=ExecutionBinding{};
    binding.used=true;
    binding.sender=true;
    binding.response=true;
    binding.inbound_response_request=true;
    binding.response_request=request;
    binding.phase=phase;
    binding.pending_proposal_id=pending.proposal_id;
    binding.pending_generation=pending.generation;
    binding.constructor_action=constructor_action;
    if (payload.family==ActionFamily::favor_gold) {
        binding.favor_before_verified=favor_gold_capture(payload.actor10,
            payload.recipient20,binding.favor_before);
        binding.favor_amount_verified=favor_gold_amount(
            reinterpret_cast<void*>(constructor_action),binding.favor_amount_raw);
        binding.alliance_before=false;
        binding.alliance_before_verified=binding.favor_before_verified;
    } else if (payload.family==ActionFamily::favor_trust
        || payload.family==ActionFamily::favor_men) {
        const bool trust=payload.family==ActionFamily::favor_trust;
        binding.favor_trade_before_verified=favor_trade_capture_action(trust,
            payload.actor10,payload.recipient20,reinterpret_cast<void*>(constructor_action),
            binding.favor_trade_before);
        binding.favor_trade_amount_verified=favor_trade_amount(trust,
            reinterpret_cast<void*>(constructor_action),binding.favor_trade_amount_raw);
        binding.alliance_before=false;
        binding.alliance_before_verified=binding.favor_trade_before_verified
            && binding.favor_trade_amount_verified;
    } else binding.alliance_before_verified=execution_read_after(payload,binding.alliance_before);
    if (!binding.alliance_before_verified
        || (payload.family==ActionFamily::favor_gold && !binding.favor_amount_verified)
        || ((payload.family==ActionFamily::favor_trust || payload.family==ActionFamily::favor_men)
            && (!binding.favor_trade_before_verified || !binding.favor_trade_amount_verified))) {
        execution_mark_invalid(binding); return false;
    }
    if (pending.peace_offer) {
        const auto context=execution_peace_inbound_context(payload,nullptr,
            reinterpret_cast<void*>(source.action+0x48u));
        if (!context.complete || !binding.alliance_before) {
            execution_mark_invalid(binding); return false;
        }
        std::memcpy(binding.peace_war_id,context.war_id,sizeof(binding.peace_war_id));
        binding.peace_request=context.effect_request;
        snprintf(binding.peace_request.request_id,sizeof(binding.peace_request.request_id),
            "%.64s",request.request_id);
        binding.peace_request.date_raw=request.date_raw;
        binding.peace_effects_supported=context.effects_supported
            && execution_peace_effects_capture(payload,binding.peace_request,binding.peace_effects_before);
        if (context.effects_supported && !binding.peace_effects_supported) {
            execution_mark_invalid(binding); return false;
        }
    }
    binding.source=source;
    binding.payload=payload;
    binding.constructor_action=constructor_action;
    binding.expected_wrapper=ObjectRef{source.address,execution_next_generation()};
    binding.expected_action=ObjectRef{source.action,execution_next_generation()};
    memcpy(binding.ledger_request_id,request.request_id,sizeof(binding.ledger_request_id));
    Context context=execution_context();
    bridge::alliance_authority::SeedResult seeded=execution_ledger.seed(context,
        binding.ledger_request_id,payload,phase,binding.expected_wrapper,
        binding.expected_action,context.current_tick+10000u);
    if (!seeded.result.ok()) {
        execution_mark_invalid(binding);
        return false;
    }
    binding.seed=seeded.receipt;
    return true;
}

static bool execution_bind_response(const TransportCompletedEvent& event,
    const TransportLoadedRecord& record,unsigned parent_slot) noexcept {
    if (parent_slot>=kBindingCapacity || !execution_bindings[parent_slot].used) return false;
    ExecutionBinding& parent=execution_bindings[parent_slot];
    if (parent.response_slot!=kInvalidBinding) return false;
    if (!record.caller_verified || record.native_return!=base+kLoadReturnRva
        || !record.header_equal || !record.payload_equal
        || !record.peer_readable || !record.world_transport_readable
        || !record.peer_is_world_transport || record.peer_owner!=record.world_dispatcher
        || !record.peer_input_ring || !record.world_dispatcher
        || !event.source.identity || !event.source.readable
        || !record.loaded.identity || !record.loaded.readable
        || !record.loaded.prefix_readable || !event.source.prefix_readable) return false;
    AlliancePayload payload{};
    if (!execution_payload(record.loaded.payload,payload)
        || (payload.variant38!=1 || (payload.state34!=1 && payload.state34!=2))
        || !execution_response_endpoint(parent.payload,payload)) return false;
    unsigned slot=execution_free_binding();
    if (slot==kInvalidBinding) return false;
    ExecutionBinding& binding=execution_bindings[slot];
    binding=ExecutionBinding{};
    binding.used=true;
    binding.response=true;
    binding.parent_slot=parent_slot;
    binding.request=parent.request;
    binding.peace_request=parent.peace_request;
    binding.peace_effects_before=parent.peace_effects_before;
    binding.peace_effects_supported=parent.peace_effects_supported;
    binding.alliance_before=parent.alliance_before;
    binding.alliance_before_verified=parent.alliance_before_verified;
    binding.favor_before=parent.favor_before;
    binding.favor_amount_raw=parent.favor_amount_raw;
    binding.favor_before_verified=parent.favor_before_verified;
    binding.favor_amount_verified=parent.favor_amount_verified;
    binding.favor_trade_before=parent.favor_trade_before;
    binding.favor_trade_amount_raw=parent.favor_trade_amount_raw;
    binding.favor_trade_before_verified=parent.favor_trade_before_verified;
    binding.favor_trade_amount_verified=parent.favor_trade_amount_verified;
    binding.phase=payload.state34==2?Phase::accept:Phase::reject;
    binding.source=event.source;
    binding.loaded=record.loaded;
    binding.payload=payload;
    binding.expected_wrapper=ObjectRef{event.source.address,execution_next_generation()};
    binding.expected_action=ObjectRef{event.source.action,execution_next_generation()};
    binding.incoming_wrapper=ObjectRef{record.loaded.address,execution_next_generation()};
    binding.incoming_action=ObjectRef{record.loaded.action,execution_next_generation()};
    execution_make_ledger_id(binding.ledger_request_id,parent,
        static_cast<uint64_t>(slot)+1u);
    Context context=execution_context();
    bridge::alliance_authority::SeedResult seeded=execution_ledger.seed(context,
        binding.ledger_request_id,payload,binding.phase,binding.expected_wrapper,
        binding.expected_action,context.current_tick+10000u);
    if (!seeded.result.ok()) { execution_mark_invalid(binding); return false; }
    binding.seed=seeded.receipt;
    binding.source_header=execution_header(record.loaded);
    bridge::alliance_authority::OperationResult serialized=execution_ledger.serializer(
        context,binding.seed,binding.phase,binding.expected_wrapper,binding.expected_action,
        payload,binding.source_header);
    if (!serialized.ok()) { execution_ledger.revoke_request(context,binding.seed,binding.phase); execution_mark_invalid(binding); return false; }
    bridge::alliance_authority::ClaimResult claimed=execution_ledger.incoming_preclone(
        context,binding.seed,binding.phase,binding.incoming_wrapper,binding.incoming_action,
        binding.source_header,payload,true);
    if (!claimed.result.ok()) { execution_ledger.revoke_request(context,binding.seed,binding.phase); execution_mark_invalid(binding); return false; }
    binding.claim=claimed.ticket;
    binding.claim_bound=true;
    binding.transport_verified=true;
    parent.response_slot=slot;
    return true;
}

static bool execution_transport_pipeline_ok(const TransportCompletedEvent& event,
    const TransportLoadedRecord& record) noexcept {
    return record.caller_verified && record.native_return==base+kLoadReturnRva
        && event.source_captured && event.source.identity && event.source.readable
        && event.source.prefix_readable && record.loaded.identity
        && record.loaded.readable && record.loaded.prefix_readable
        && record.header_equal && record.payload_equal
        && record.peer_readable && record.world_transport_readable
        && record.peer_is_world_transport && record.peer_owner==record.world_dispatcher
        && record.peer_input_ring!=0 && record.world_dispatcher!=0
        && record.peer==record.world_transport;
}

static void execution_transport_loaded(const TransportCompletedEvent& event,
    const TransportLoadedRecord& record) {
    if (!execution_initialized || !execution_handler_enabled) return;
    if (!execution_transport_pipeline_ok(event,record)) return;
    if (execution_sender_scope.active
        && execution_sender_scope.binding_slot<kBindingCapacity) {
        ExecutionBinding& binding=execution_bindings[execution_sender_scope.binding_slot];
        if (!binding.used || !binding.sender || binding.invalidated
            || event.source.address!=binding.expected_wrapper.address
            || event.source.action!=binding.expected_action.address
            || !execution_same_payload(event.source,record.loaded)) return;
        AlliancePayload payload{};
        if (!execution_payload(record.loaded.payload,payload) || payload!=binding.payload) return;
        binding.loaded=record.loaded;
        binding.source=event.source;
        binding.source_header=execution_header(record.loaded);
        Context context=execution_context();
        bridge::alliance_authority::OperationResult serialized=execution_ledger.serializer(
            context,binding.seed,binding.phase,binding.expected_wrapper,binding.expected_action,
            payload,binding.source_header);
        if (!serialized.ok()) { execution_ledger.revoke_request(context,binding.seed,binding.phase); execution_mark_invalid(binding); return; }
        binding.incoming_wrapper=ObjectRef{record.loaded.address,execution_next_generation()};
        binding.incoming_action=ObjectRef{record.loaded.action,execution_next_generation()};
        bridge::alliance_authority::ClaimResult claimed=execution_ledger.incoming_preclone(
            context,binding.seed,binding.phase,binding.incoming_wrapper,binding.incoming_action,
            binding.source_header,payload,true);
        if (!claimed.result.ok()) { execution_ledger.revoke_request(context,binding.seed,binding.phase); execution_mark_invalid(binding); return; }
        binding.claim=claimed.ticket;
        binding.claim_bound=true;
        binding.transport_verified=true;
        return;
    }
    if (execution_response_scope.active)
        execution_bind_response(event,record,execution_response_scope.parent_slot);
}

static void execution_protocol_clone_completed(const ProtocolCloneEvent& event) {
    if (!execution_initialized || !execution_handler_enabled
        || event.caller_return!=base+kCloneReturnRva
        || !event.caller_return_matches || !event.receiver_readable
        || !event.world_transport_readable || !event.receiver_is_world_transport
        || event.receiver_host!=event.world_dispatcher || !event.receiver_input_ring
        || !event.source.identity || !event.source.readable || !event.source.prefix_readable
        || !event.target.identity || !event.target.readable || !event.target.prefix_readable) return;
    for (unsigned index=0;index<kBindingCapacity;++index) {
        ExecutionBinding& binding=execution_bindings[index];
        if (!binding.used || !binding.claim_bound || binding.invalidated || binding.postcloned
            || event.source.address!=binding.incoming_wrapper.address
            || event.source.action!=binding.incoming_action.address) continue;
        AlliancePayload payload{};
        if (!execution_payload(event.source.payload,payload) || payload!=binding.payload
            || event.source.origin48!=binding.source_header.origin
            || event.source.flags4a!=binding.source_header.flags
            || event.source.sequence4c!=binding.source_header.seq
            || event.target.origin48!=0xffffu
            || event.target.flags4a!=0 || event.target.sequence4c!=0
            || !event.source.payload.readable || !binding.loaded.payload.readable
            || event.source.payload.actor10!=binding.loaded.payload.actor10
            || event.source.payload.mirror18!=binding.loaded.payload.mirror18
            || event.source.payload.recipient20!=binding.loaded.payload.recipient20
            || event.source.payload.date28!=binding.loaded.payload.date28
            || event.source.payload.date2c!=binding.loaded.payload.date2c
            || event.source.payload.envoy30!=binding.loaded.payload.envoy30
            || event.source.payload.state34!=binding.loaded.payload.state34
            || event.source.payload.variant38!=binding.loaded.payload.variant38
            || event.source.payload.proposal3c!=binding.loaded.payload.proposal3c
            || event.source.raw10!=binding.loaded.raw10
            || event.source.raw38!=binding.loaded.raw38
            || event.source.raw3c!=binding.loaded.raw3c
            || event.source.raw40!=binding.loaded.raw40
            || event.source.raw44!=binding.loaded.raw44) return;
        AlliancePayload target_payload{};
        if (!execution_payload(event.target.payload,target_payload)
            || target_payload!=binding.payload) return;
        CloneProof proof{};
        proof.source_wrapper=binding.incoming_wrapper;
        proof.source_action=binding.incoming_action;
        proof.target_wrapper=ObjectRef{event.target.address,execution_next_generation()};
        proof.target_action=ObjectRef{event.target.action,execution_next_generation()};
        proof.payload=binding.payload;
        // The clone returned by 4e8550 carries the transfer marker
        // ffff/0/0.  The later command-entry wrapper receives the same
        // marker with the transport sequence restored; ledger postclone
        // validates that expected entry header before consume_entry.
        proof.observed_clone_header=execution_header(event.target);
        proof.final_entry_header=NativeHeader{0xffffu,0u,binding.source_header.seq};
        Context context=execution_context();
        bridge::alliance_authority::OperationResult posted=execution_ledger.postclone(
            context,binding.claim,binding.phase,proof);
        if (!posted.ok()) { execution_mark_invalid(binding); return; }
        binding.target=event.target;
        binding.target_wrapper=proof.target_wrapper;
        binding.target_action=proof.target_action;
        binding.final_entry_header=proof.final_entry_header;
        binding.postcloned=true;
        return;
    }
}

static void execution_lifecycle_source_destroyed(void* source,
    const LifecycleActionShape& snapshot,unsigned flags) {
    (void)source; (void)flags;
    bridge_inbound_pending_destroyed(source,snapshot,flags);
    if (!execution_initialized || !execution_handler_enabled || !snapshot.readable) return;
    int found=execution_find_action(snapshot.address);
    if (found<0) return;
    ExecutionBinding& binding=execution_bindings[static_cast<unsigned>(found)];
    Context context=execution_context();
    if (binding.postcloned && !binding.consumed
        && binding.target_action.address==snapshot.address) {
        bridge::alliance_authority::OperationResult result=execution_ledger.target_destroyed(
            context,binding.claim,binding.phase,binding.target_wrapper,binding.target_action);
        if (result.code==ErrorCode::target_destroyed || result.code==ErrorCode::already_invalidated)
            execution_mark_invalid(binding);
        return;
    }
    if (binding.claim_bound && binding.incoming_action.address==snapshot.address) {
        bridge::alliance_authority::OperationResult result=execution_ledger.source_destroyed(
            context,binding.seed,binding.phase,bridge::alliance_authority::SourceKind::incoming,
            binding.incoming_wrapper,binding.incoming_action);
        if (result.code==ErrorCode::source_destroyed || result.code==ErrorCode::already_invalidated)
            execution_mark_invalid(binding);
        return;
    }
    if (binding.expected_action.address==snapshot.address
        || binding.constructor_action==snapshot.address) {
        bridge::alliance_authority::OperationResult result=execution_ledger.source_destroyed(
            context,binding.seed,binding.phase,bridge::alliance_authority::SourceKind::outgoing,
            binding.expected_wrapper,binding.expected_action);
        if (result.code==ErrorCode::source_destroyed || result.code==ErrorCode::already_invalidated)
            execution_mark_invalid(binding);
    }
}

static bool execution_read_after(const AlliancePayload& payload,bool& alliance_after) noexcept {
    if (payload.family==ActionFamily::peace)
        return execution_peace_war_state(payload,alliance_after);
    if (payload.family==ActionFamily::favor_gold) {
        FavorGoldState state{};
        alliance_after=false;
        return favor_gold_capture(payload.actor10,payload.recipient20,state);
    }
    if (payload.family==ActionFamily::favor_trust || payload.family==ActionFamily::favor_men) {
        FavorTradeState state{};
        int32_t cost=0;
        alliance_after=false;
        return execution_favor_trade_cost(payload.family==ActionFamily::favor_trust,
            payload,cost) && favor_trade_capture(
                payload.family==ActionFamily::favor_trust,payload.actor10,
                payload.recipient20,cost,state);
    }
    if (payload.family==ActionFamily::gift) {
        GiftResourceState state{};
        alliance_after=false;
        return gift_resource_capture(payload.actor10,payload.recipient20,state);
    }
    if (payload.family==ActionFamily::influence) {
        InfluenceResourceState state{};
        alliance_after=false;
        return influence_resource_capture(payload.actor10,payload.recipient20,state);
    }
    if (payload.family==ActionFamily::declare_war) {
        DeclareWarExecutionState state{};
        const bool okay=execution_declarewar_state(payload.actor10,payload.recipient20,state);
        alliance_after=state.active; return okay;
    }
    if (payload.family==ActionFamily::vassalization) {
        VassalQueryState state{};
        const bool okay=vassal_query_relation(payload.actor10,payload.recipient20,state);
        alliance_after=state.active; return okay;
    }
    if (payload.family==ActionFamily::insult) {
        InsultEffectState effect{};
        const bool okay=insult_query_state(payload.actor10,payload.recipient20,payload.parameter40>=0,effect);
        alliance_after=effect.active; return okay;
    }
    if (payload.family==ActionFamily::military_access)
        return military_query_active(payload.actor10,payload.recipient20,alliance_after);
    if (payload.family==ActionFamily::support_independence)
        return support_query_active(payload.actor10,payload.recipient20,alliance_after);
    if (execution_unilateral_family(payload.family)) {
        const FactoryActionQueryMethods& family=payload.family==ActionFamily::curry_favors
            ?curry_favors_query_methods:payload.family==ActionFamily::guarantee?unilateral_guarantee:
            payload.family==ActionFamily::spy_network?unilateral_spy:unilateral_improve;
        return factory_query_relation_active(payload.actor10,payload.recipient20,alliance_after,family);
    }
    return alliance_query_visibility(payload.actor10,payload.recipient20,false,alliance_after,
        payload.family==ActionFamily::royal_marriage?0x28df:0x293d);
}

static bool execution_pending_shape_matches(const InboundPendingView& pending,
    const LifecycleActionShape& shape,int32_t expected_state) noexcept {
    return shape.readable && shape.matched && shape.handles_canonical
        && shape.royal_marriage==pending.royal_marriage
        && shape.support_independence==pending.support_independence && shape.extra60==pending.extra60
        && shape.military_access==pending.military_access
        && shape.vassalization==pending.vassalization
        && shape.favor_gold==pending.favor_gold
        && shape.favor_trust==pending.favor_trust
        && shape.favor_men==pending.favor_men
        && shape.favor_cost40==pending.favor_cost40
        && shape.favor_amount44==pending.favor_amount44
        && shape.peace_offer==pending.peace_offer
        && (pending.peace_offer?shape.peace==pending.peace:shape.peace.empty())
        && shape.actor10==pending.actor && shape.mirror18==pending.mirror
        && shape.recipient20==pending.recipient && shape.date28==pending.date28
        // Royal +b0 copies source.date28 into both date words. The normal
        // wrapper later stamps date2c with the current date before transport.
        && shape.date2c==((pending.royal_marriage || pending.support_independence || pending.military_access || pending.vassalization || pending.favor_gold || pending.favor_trust || pending.favor_men || pending.peace_offer)?pending.date28:pending.date2c)
        && shape.envoy30==pending.envoy30 && shape.variant38==pending.variant38
        && shape.proposal3c==pending.proposal3c && shape.state34==expected_state;
}

static bool execution_response_validity(void* action,bool& native_validity) noexcept {
    native_validity=false;
    uintptr_t vtable=0,validity=0;
    if (!read(reinterpret_cast<uintptr_t>(action),vtable)
        || (vtable!=base+lifecycle_alliance_vtable_rva && vtable!=base+0x1c80ab0
            && vtable!=base+lifecycle_support_vtable_rva && vtable!=base+lifecycle_military_access_vtable_rva
            && vtable!=base+lifecycle_vassalization_vtable_rva
            && vtable!=base+lifecycle_favor_gold_vtable_rva
            && vtable!=base+lifecycle_favor_trust_vtable_rva
            && vtable!=base+lifecycle_favor_men_vtable_rva
            && vtable!=base+lifecycle_peace_vtable_rva)
        || !read(vtable+0x80,validity)
        || (vtable==base+lifecycle_peace_vtable_rva ? validity!=base+0x59b480 :
            vtable==base+lifecycle_vassalization_vtable_rva ? validity!=base+0x51f050 :
            vtable==base+lifecycle_favor_gold_vtable_rva ? validity!=base+0x4f4f10 :
            vtable==base+lifecycle_favor_trust_vtable_rva ? validity!=base+0x4fdfd0 :
            vtable==base+lifecycle_favor_men_vtable_rva ? validity!=base+0x4f7600 :
            vtable==base+lifecycle_military_access_vtable_rva ? validity!=base+0x525530 :
            vtable==base+lifecycle_support_vtable_rva ? validity!=base+0x50e120 :
            vtable==base+0x1c80ab0 ? validity!=base+0x4ef3e0 :
            (validity!=base+0x511d90
            && validity!=reinterpret_cast<uintptr_t>(&observation_alliance_validity)))) return false;
    using Predicate=bool (*)(void*,void*,unsigned char);
    native_validity=vtable==base+lifecycle_vassalization_vtable_rva
        ?reinterpret_cast<bool (*)(void*,void*)>(validity)(action,nullptr)
        :reinterpret_cast<Predicate>(validity)(action,nullptr,0);
    return true;
}

static void execution_destroy_temp_action(void* action) noexcept {
    if (!action) return;
    uintptr_t vtable=0;
    if (!read(reinterpret_cast<uintptr_t>(action),vtable)) return;
    const bool marriage=vtable==base+0x1c80ab0;
    const bool peace=vtable==base+lifecycle_peace_vtable_rva;
    const bool favor_gold=vtable==base+lifecycle_favor_gold_vtable_rva;
    const bool favor_trust=vtable==base+lifecycle_favor_trust_vtable_rva;
    LifecycleDestructorMethod destructor=peace?lifecycle_peace_destructor_original:
        marriage?lifecycle_royal_destructor_original:
        favor_trust?lifecycle_favor_trust_destructor_original:lifecycle_destructor_original;
    if (destructor) destructor(action,(marriage || vtable==base+lifecycle_support_vtable_rva
        || vtable==base+lifecycle_military_access_vtable_rva
        || vtable==base+lifecycle_vassalization_vtable_rva || favor_gold
        || favor_trust || vtable==base+lifecycle_favor_men_vtable_rva || peace)?1:0);
}

static bool execution_clone_pending_for_state(const InboundPendingView& pending,
    int32_t state,void*& clone,LifecycleActionShape& shape,
    bool& native_validity) noexcept {
    clone=nullptr;
    shape=LifecycleActionShape{};
    native_validity=false;
    LifecycleCloneMethod native_clone=pending.peace_offer?lifecycle_peace_clone_original:
        pending.favor_gold?lifecycle_favor_gold_clone_original:
        pending.favor_trust?lifecycle_favor_trust_clone_original:
        pending.favor_men?lifecycle_favor_men_clone_original:
        pending.vassalization?lifecycle_vassalization_clone_original:
        pending.military_access?lifecycle_military_access_clone_original:
        pending.support_independence?lifecycle_support_clone_original:
        pending.royal_marriage?lifecycle_royal_clone_original:lifecycle_clone_original;
    if (!native_clone || !pending.active || pending.state34!=0 || pending.extra60!=0
        || pending.variant38!=1) return false;
    clone=native_clone(reinterpret_cast<void*>(pending.clone));
    if (!clone) return false;
    LifecycleActionShape original=lifecycle_capture_shape(clone);
    if (!execution_pending_shape_matches(pending,original,0)) {
        execution_destroy_temp_action(clone); clone=nullptr; return false;
    }
    std::memcpy(reinterpret_cast<void*>(reinterpret_cast<uintptr_t>(clone)+0x34),
        &state,sizeof(state));
    shape=lifecycle_capture_shape(clone);
    if (!execution_pending_shape_matches(pending,shape,state)) {
        execution_destroy_temp_action(clone); clone=nullptr; return false;
    }
    if (!execution_response_validity(clone,native_validity)) {
        execution_destroy_temp_action(clone); clone=nullptr; return false;
    }
    return true;
}

static bool execution_response_rules_complete(bool marriage=false,bool support=false,
    bool military=false,bool vassal=false,bool favor=false,bool favor_trust=false,
    bool favor_men=false,bool peace=false) noexcept {
    // For Alliance responses, +0x80 is the native action legality predicate.
    // The executor also reads +0x100 (constant true) and, for state 2, +0xf8
    // (constant false).  +0xb8 selects an NPC decision; LLM responses do not
    // call it.  Context, transport and business effects remain native and are
    // verified separately through the authorized entry and resulting state.
    uintptr_t validity=0,forward=0,accept_skip=0,cost_skip=0;
    const uintptr_t vtable=base+(peace?lifecycle_peace_vtable_rva:
        favor_trust?lifecycle_favor_trust_vtable_rva:favor_men?lifecycle_favor_men_vtable_rva:
        favor?lifecycle_favor_gold_vtable_rva:
        vassal?lifecycle_vassalization_vtable_rva:military?lifecycle_military_access_vtable_rva:
        support?lifecycle_support_vtable_rva:marriage?0x1c80ab0:lifecycle_alliance_vtable_rva);
    return base && read(vtable+0x80,validity)
        && (validity==base+(peace?0x59b480:favor_trust?0x4fdfd0:favor_men?0x4f7600:favor?0x4f4f10:vassal?0x51f050:military?0x525530:support?0x50e120:marriage?0x4ef3e0:0x511d90)
            || (!peace && !favor && !favor_trust && !favor_men && !marriage && !support && !military && !vassal && validity==reinterpret_cast<uintptr_t>(&observation_alliance_validity)))
        && read(vtable+0x100,forward) && forward==base+(peace?0x59bef0:0x8f440)
        && read(vtable+0xf8,accept_skip) && accept_skip==base+0x8f450
        && (!peace || (read(vtable+0x108,cost_skip) && cost_skip==base+0x8f450));
}

static AlliancePayload execution_pending_payload(const InboundPendingView& pending) noexcept {
    AlliancePayload payload{};
    payload.actor10=pending.actor;
    payload.mirror18=pending.mirror;
    payload.recipient20=pending.recipient;
    payload.date28=static_cast<uint64_t>(static_cast<uint32_t>(pending.date28));
    payload.date2c=static_cast<uint64_t>(static_cast<uint32_t>(pending.date2c));
    payload.envoy30=static_cast<uint64_t>(static_cast<uint32_t>(pending.envoy30));
    payload.state34=static_cast<uint64_t>(static_cast<uint32_t>(pending.state34));
    payload.variant38=pending.variant38;
    payload.proposal3c=static_cast<uint64_t>(static_cast<uint32_t>(pending.proposal3c));
    payload.family=pending.peace_offer?ActionFamily::peace:pending.favor_gold?ActionFamily::favor_gold:
        pending.favor_trust?ActionFamily::favor_trust:pending.favor_men?ActionFamily::favor_men:
        pending.vassalization?ActionFamily::vassalization:pending.military_access?ActionFamily::military_access:
        pending.support_independence?ActionFamily::support_independence:
        pending.royal_marriage?ActionFamily::royal_marriage:ActionFamily::alliance;
    payload.extra60=pending.extra60;
    payload.favor_cost40=pending.favor_cost40;
    payload.favor_amount44=pending.favor_amount44;
    payload.peace=pending.peace;
    return payload;
}

static bool execution_peace_response_rule(void* action,int32_t current_date,
    bool& native_available) noexcept {
    auto expected=lifecycle_capture_shape(action);
    void* wrapper=nullptr;
    using Wrapper=void* (*)(void*,void**);
    if (!expected.peace_offer || !expected.peace.valid()
        || !reinterpret_cast<Wrapper>(base+kWrapperMethodRva)(action,&wrapper) || !wrapper) return false;
    // The native wrapper method stamps the response send date. Its clone
    // keeps every term and the pending token; no bridge date write is used.
    expected.date2c=current_date;
    const auto wrapped=protocol_capture(wrapper);
    PeaceWrapperRuleCapture rule{};
    if (wrapped.identity && wrapped.readable && wrapped.prefix_readable
        && protocol_shape_equal(expected,wrapped.payload)) rule=peace_wrapper_rule_inspect(wrapper);
    execution_release_constructed(wrapper,nullptr,false);
    native_available=native_available && rule.available;
    return rule.complete();
}

static bool execution_read_request_file(const wchar_t* path,char* buffer,
    DWORD capacity,DWORD& size) noexcept {
    size=0;
    if (!path || !path[0]
        || GetFileAttributesW(path)==INVALID_FILE_ATTRIBUTES) return false;
    HANDLE file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,nullptr,
        OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if (file==INVALID_HANDLE_VALUE) return false;
    DWORD file_size=GetFileSize(file,nullptr),got=0;
    const bool readable=file_size!=INVALID_FILE_SIZE && file_size<=capacity
        && ReadFile(file,buffer,file_size,&got,nullptr) && got==file_size;
    CloseHandle(file);
    DeleteFileW(path);
    if (!readable) return false;
    size=file_size;
    return true;
}

static void execution_emit_inspection_failure(const InspectionRequest& request,
    const char* reason) noexcept {
    bridge::alliance_inbound_inspection_event::Observation observed{};
    observed.royal_marriage=strcmp(request.action_id,"offer_royal_marriage")==0;
    observed.support_independence=strcmp(request.action_id,"support_independence")==0;
    observed.military_access=strcmp(request.action_id,"ask_military_access")==0;
    observed.vassalization=strcmp(request.action_id,"offer_vassalization")==0;
    observed.favor_gold=strcmp(request.action_id,"trade_favors_for_gold")==0;
    observed.favor_trust=strcmp(request.action_id,"trade_favors_for_trust")==0;
    observed.favor_men=strcmp(request.action_id,"trade_favors_for_men")==0;
    observed.peace_offer=strcmp(request.action_id,"peace_offer")==0;
    observed.reason=reason?reason:"unknown";
    char message[1600];
    if (bridge::alliance_inbound_inspection_event::format(
            message,sizeof(message),request,observed)) line(message);
}

static void execution_queue_response_unknown(const ResponseRequest& request,
    int32_t native_state,bool alliance_after,bool pending_removed) noexcept {
    if (!strcmp(request.action_id,"peace_offer")) {
        execution_peace_inbound_unknown(request,native_state,alliance_after,pending_removed); return;
    }
    ResponseResult result{};
    memcpy(result.request_id,request.request_id,sizeof(result.request_id));
    memcpy(result.session_id,request.session_id,sizeof(result.session_id));
    memcpy(result.actor,request.original_actor,sizeof(result.actor));
    memcpy(result.recipient,request.decision_country,sizeof(result.recipient));
    execution_copy_text(result.action_id,sizeof(result.action_id),request.action_id);
    execution_copy_text(result.phase,sizeof(result.phase),request.decision);
    result.date_raw=request.date_raw;
    result.inbound_response=true;
    result.native_state=native_state;
    result.alliance_after=alliance_after;
    result.pending_removed=pending_removed;
    result.response_verified=false;
    result.request_binding_verified=false;
    strcpy(result.outcome,"unknown");
    if (!TryAcquireSRWLockExclusive(&execution_result_lock)) {
        InterlockedIncrement(&execution_result_dropped); return;
    }
    if (execution_response_size<kBindingCapacity) {
        execution_response_results[(execution_response_head+execution_response_size)%kBindingCapacity]=result;
        ++execution_response_size;
    } else InterlockedIncrement(&execution_result_dropped);
    ReleaseSRWLockExclusive(&execution_result_lock);
}

static void execution_emit_inspection(const InspectionRequest& request,
    const InboundPendingView& pending,bool native_validity,bool alliance_after,
    bool alliance_readable) noexcept {
    bridge::alliance_inbound_inspection_event::Observation observed{};
    observed.pending_active=true;
    observed.decision_country_verified=true;
    observed.native_validity=native_validity;
    const bool native_response_rules=execution_response_rules_complete(pending.royal_marriage,
        pending.support_independence,pending.military_access,pending.vassalization,
        pending.favor_gold || pending.favor_trust || pending.favor_men,
        pending.favor_trust,pending.favor_men,pending.peace_offer);
    observed.royal_marriage=pending.royal_marriage;
    observed.support_independence=pending.support_independence;
    observed.military_access=pending.military_access;
    observed.vassalization=pending.vassalization;
    observed.favor_gold=pending.favor_gold;
    observed.favor_trust=pending.favor_trust;
    observed.favor_men=pending.favor_men;
    observed.peace_offer=pending.peace_offer;
    observed.extra60=pending.extra60;
    observed.alliance_before=alliance_after;
    observed.alliance_readable=alliance_readable;
    if (pending.favor_gold) {
        // QUERY1 context is captured from the live pending endpoints and the
        // native amount helper.  Do not substitute Alliance relation fields:
        // favor_trade has independent treasury/favor state and its response
        // proof depends on these exact raw values.
        FavorGoldState favor_state{};
        const bool state_read=favor_gold_capture(
            pending.actor,pending.recipient,favor_state);
        int32_t amount=0;
        const bool amount_read=pending.action!=0
            && favor_gold_amount(reinterpret_cast<void*>(pending.action),amount);
        observed.favor_context_complete=state_read;
        observed.favor_amount_readable=amount_read;
        observed.favor_amount_raw=amount;
        if (state_read) {
            observed.favor_cost_raw=favor_state.cost_raw;
            observed.favor_favors_available_raw=favor_state.favors_raw;
            observed.favor_actor_treasury_raw=favor_state.actor_treasury_raw;
            observed.favor_recipient_treasury_raw=favor_state.recipient_treasury_raw;
        }
        observed.response_rules_complete=native_response_rules
            && state_read && amount_read;
        // These are deliberately left false for favor_trade.  The formatter
        // must never emit an alliance_before/current field for this family.
        observed.alliance_before=false;
        observed.alliance_readable=false;
    } else if (pending.favor_trust || pending.favor_men) {
        const bool trust=pending.favor_trust;
        FavorTradeState favor_state{};
        const bool state_read=favor_trade_capture_action(trust,pending.actor,
            pending.recipient,reinterpret_cast<void*>(pending.action),favor_state);
        int32_t amount=0;
        const bool amount_read=pending.action!=0
            && favor_trade_amount(trust,reinterpret_cast<void*>(pending.action),amount);
        observed.favor_context_complete=state_read;
        observed.favor_amount_readable=amount_read;
        observed.favor_amount_raw=amount;
        if (state_read) {
            observed.favor_cost_raw=favor_state.cost_raw;
            observed.favor_favors_available_raw=favor_state.favors_raw;
            observed.favor_recipient_trust_raw=favor_state.recipient_trust_raw;
            observed.favor_actor_manpower_raw=favor_state.actor_manpower_raw;
            observed.favor_recipient_manpower_raw=favor_state.recipient_manpower_raw;
        }
        observed.response_rules_complete=native_response_rules
            && state_read && amount_read;
        observed.alliance_before=false;
        observed.alliance_readable=false;
    } else {
        observed.response_rules_complete=native_response_rules && alliance_readable;
    }
    observed.date28=pending.date28;
    observed.date2c=pending.date2c;
    observed.envoy30=pending.envoy30;
    observed.state34=pending.state34;
    observed.variant38=pending.variant38;
    observed.proposal3c=pending.proposal3c;
    const auto peace_context=pending.peace_offer
        ?execution_peace_inbound_context(execution_pending_payload(pending),nullptr,
            reinterpret_cast<void*>(pending.action+0x48u)):InboundPeaceContext{};
    if (pending.peace_offer) {
        observed.war_active=observed.war_before=observed.native_current_war=alliance_after;
        observed.war_readable=observed.native_current_war_readable=alliance_readable;
        observed.peace_payload_complete=peace_context.payload_complete;
        observed.selected_terms_complete=peace_context.selected_complete;
        observed.term_count=peace_context.term_count;
        observed.selected_term_count=peace_context.selected_count;
        observed.peace_context_json=peace_context.json;
    }
    char message[8000];
    if (bridge::alliance_inbound_inspection_event::format(
            message,sizeof(message),request,observed)) line(message);
}

static bool execution_submit_inbound_response(const ResponseRequest& request,
    const InboundPendingView& pending,int32_t current_date) noexcept {
    const int32_t response_state=strcmp(request.decision,"accept")==0?2:1;
    auto release_reservation=[&]() noexcept {
        inbound_pending_release(pending.proposal_id,pending.generation);
    };
    void* response_action=nullptr;
    LifecycleActionShape response_shape{};
    bool native_validity=false;
    if (!execution_clone_pending_for_state(pending,response_state,response_action,
        response_shape,native_validity) || !native_validity) {
        execution_destroy_temp_action(response_action);
        release_reservation();
        execution_queue_response_unknown(request,response_state,false,false);
        return false;
    }
    uintptr_t action_vtable=0,wrapper_slot=0;
    if (!read(reinterpret_cast<uintptr_t>(response_action),action_vtable)
        || action_vtable!=base+(pending.peace_offer?lifecycle_peace_vtable_rva:pending.favor_gold?lifecycle_favor_gold_vtable_rva:pending.favor_trust?lifecycle_favor_trust_vtable_rva:pending.favor_men?lifecycle_favor_men_vtable_rva:pending.vassalization?lifecycle_vassalization_vtable_rva:pending.military_access?lifecycle_military_access_vtable_rva:
            pending.support_independence?lifecycle_support_vtable_rva:pending.royal_marriage?0x1c80ab0:lifecycle_alliance_vtable_rva)
        || !read(action_vtable+0x40,wrapper_slot)
        || (wrapper_slot!=base+kWrapperMethodRva
            && wrapper_slot!=reinterpret_cast<uintptr_t>(&lifecycle_wrapper_observe))) {
        execution_destroy_temp_action(response_action);
        release_reservation();
        execution_queue_response_unknown(request,response_state,false,false);
        return false;
    }
    void* wrapper=nullptr;
    using Wrapper=void* (*)(void*,void**);
    if (!reinterpret_cast<Wrapper>(base+kWrapperMethodRva)(response_action,&wrapper)
        || !wrapper) {
        execution_destroy_temp_action(response_action);
        release_reservation();
        execution_queue_response_unknown(request,response_state,false,false);
        return false;
    }
    ProtocolWrapperShape source=protocol_capture(wrapper);
    AlliancePayload payload{};
    const bool payload_ok=source.identity && source.readable && source.prefix_readable
        && execution_payload(source.payload,payload)
        && payload.actor10==pending.actor && payload.mirror18==pending.mirror
        && payload.recipient20==pending.recipient
        && payload.date28==static_cast<uint64_t>(static_cast<uint32_t>(pending.date28))
        && payload.date2c==static_cast<uint64_t>(static_cast<uint32_t>(current_date))
        && payload.envoy30==static_cast<uint64_t>(static_cast<uint32_t>(pending.envoy30))
        && payload.state34==static_cast<uint64_t>(static_cast<uint32_t>(response_state))
        && payload.variant38==1
        && payload.proposal3c==static_cast<uint64_t>(static_cast<uint32_t>(pending.proposal3c))
        && payload.family==(pending.peace_offer?ActionFamily::peace:pending.favor_gold?ActionFamily::favor_gold:pending.favor_trust?ActionFamily::favor_trust:pending.favor_men?ActionFamily::favor_men:pending.vassalization?ActionFamily::vassalization:pending.military_access?ActionFamily::military_access:
            pending.support_independence?ActionFamily::support_independence:
            pending.royal_marriage?ActionFamily::royal_marriage:ActionFamily::alliance)
        && payload.extra60==pending.extra60
         && ((pending.favor_trust || pending.favor_men)
             ? payload.favor_cost40==pending.favor_cost40
                 && payload.favor_amount44==pending.favor_amount44
             : true)
        && (pending.peace_offer?payload.peace==pending.peace:payload.peace.empty());
    if (!payload_ok) {
        execution_release_constructed(wrapper,
            reinterpret_cast<unsigned char*>(response_action),true);
        release_reservation();
        execution_queue_response_unknown(request,response_state,false,false);
        return false;
    }
    if (pending.peace_offer) {
        const auto rule=peace_wrapper_rule_inspect(wrapper);
        if (!rule.complete() || !rule.available) {
            execution_release_constructed(wrapper,reinterpret_cast<unsigned char*>(response_action),true);
            release_reservation();
            execution_queue_response_unknown(request,response_state,true,false);
            return false;
        }
    }
    unsigned slot=execution_free_binding();
    if (slot==kInvalidBinding) {
        execution_release_constructed(wrapper,
            reinterpret_cast<unsigned char*>(response_action),true);
        release_reservation();
        execution_queue_response_unknown(request,response_state,false,false);
        return false;
    }
    if (!execution_bind_inbound_response(request,pending,source,payload,slot,
            reinterpret_cast<uintptr_t>(response_action))) {
        execution_release_constructed(wrapper,
            reinterpret_cast<unsigned char*>(response_action),true);
        release_reservation();
        execution_queue_response_unknown(request,response_state,false,false);
        return false;
    }
    uintptr_t dispatcher=0,transport=0;
    if (!execution_world_dispatcher(dispatcher,transport) || !dispatcher || !transport) {
        ExecutionBinding& binding=execution_bindings[slot];
        execution_ledger.revoke_request(execution_context(),binding.seed,binding.phase);
        execution_mark_invalid(binding);
        inbound_pending_release(pending.proposal_id,pending.generation);
        execution_release_constructed(wrapper,
            reinterpret_cast<unsigned char*>(response_action),true);
        execution_queue_response_unknown(request,response_state,false,false);
        return false;
    }
    void* outgoing=wrapper;
    execution_sender_scope=SenderScope{true,slot};
    using Submit=bool (*)(void*,void**);
    const bool accepted=reinterpret_cast<Submit>(base+kDispatcherRva)(
        reinterpret_cast<void*>(dispatcher),&outgoing);
    execution_sender_scope=SenderScope{};
    ExecutionBinding& binding=execution_bindings[slot];
    const bool proven=accepted && binding.claim_bound && binding.transport_verified;
    if (!proven) {
        execution_ledger.revoke_request(execution_context(),binding.seed,binding.phase);
        execution_mark_invalid(binding);
        inbound_pending_release(pending.proposal_id,pending.generation);
        if (outgoing) execution_release_constructed(outgoing,nullptr,false);
        execution_destroy_temp_action(response_action);
        execution_queue_response_unknown(request,response_state,false,false);
        return false;
    }
    // Peace retains the reservation until its bound target is consumed.
    // A transport receipt alone must not permanently mark it responded.
    if (!pending.peace_offer && !inbound_pending_commit(pending.proposal_id,pending.generation)) {
        execution_ledger.revoke_request(execution_context(),binding.seed,binding.phase);
        execution_mark_invalid(binding);
        if (outgoing) execution_release_constructed(outgoing,nullptr,false);
        execution_destroy_temp_action(response_action);
        execution_queue_response_unknown(request,response_state,false,false);
        return false;
    }
    if (outgoing) execution_release_constructed(outgoing,nullptr,false);
    execution_destroy_temp_action(response_action);
    return true;
}

static bool execution_frame_context(int32_t& date,std::uint64_t& now_filetime,
    char (&expected_session)[bridge::alliance_execution_wire::kMaxSessionIdLength+1]) noexcept {
    if (thread_changed || !frame_thread || frame_thread!=GetCurrentThreadId()
        || !control_ready()) return false;
    uintptr_t game=0;
    if (!read(base+0x233fe58,game) || !read(game+0x1dd0,date)) return false;
    FILETIME now{};
    GetSystemTimeAsFileTime(&now);
    now_filetime=(static_cast<std::uint64_t>(now.dwHighDateTime)<<32)|now.dwLowDateTime;
    snprintf(expected_session,sizeof(expected_session),"%lu-%llx",
        static_cast<unsigned long>(GetCurrentProcessId()),
        static_cast<unsigned long long>(observation_creation));
    return true;
}

static void execution_inbound_inspection_tick() noexcept {
    if (!inbound_response_handler_enabled) return;
    char wire[bridge::alliance_inbound_response_wire::kMaxWireBytes+1]{};
    DWORD size=0;
    if (!execution_read_request_file(inbound_inspection_request_path,wire,
        bridge::alliance_inbound_response_wire::kMaxWireBytes,size)) return;
    InspectionRequest request{};
    bridge::alliance_inbound_response_wire::ParseResult parsed=
        bridge::alliance_inbound_response_wire::parse_inspection_request(wire,size,request);
    if (!parsed.ok()) return;
    int32_t date=0; std::uint64_t now=0;
    char expected_session[bridge::alliance_execution_wire::kMaxSessionIdLength+1]{};
    if (!execution_frame_context(date,now,expected_session)) {
        execution_emit_inspection_failure(request,
            "FRAME_CONTEXT_UNAVAILABLE"); return;
    }
    auto context=bridge::alliance_inbound_response_wire::validate_context(
        request,expected_session,now,date);
    if (!context.ok()) {
        execution_emit_inspection_failure(request,
            bridge::alliance_inbound_response_wire::context_error_name(context.error));
        return;
    }
    InboundPendingView pending{};
    if (!inbound_pending_lookup(request.native_proposal_id,request.original_actor,pending)
        || (pending.royal_marriage!=(strcmp(request.action_id,"offer_royal_marriage")==0)
            || pending.support_independence!=(strcmp(request.action_id,"support_independence")==0)
            || pending.military_access!=(strcmp(request.action_id,"ask_military_access")==0)
            || pending.vassalization!=(strcmp(request.action_id,"offer_vassalization")==0)
            || pending.favor_gold!=(strcmp(request.action_id,"trade_favors_for_gold")==0)
            || pending.favor_trust!=(strcmp(request.action_id,"trade_favors_for_trust")==0)
            || pending.favor_men!=(strcmp(request.action_id,"trade_favors_for_men")==0)
            || pending.peace_offer!=(strcmp(request.action_id,"peace_offer")==0))) {
        execution_emit_inspection_failure(request,
            "PENDING_NOT_ACTIVE"); return;
    }
    bool alliance_after=false;
    const bool alliance_readable=execution_read_after(
        execution_pending_payload(pending),alliance_after);
    void* clone=nullptr;
    LifecycleActionShape shape{};
    bool native_validity=false;
    const int32_t response_state=strcmp(request.decision,"accept")==0?2:1;
    bool cloned=execution_clone_pending_for_state(pending,response_state,
        clone,shape,native_validity);
    if (cloned && pending.peace_offer)
        cloned=execution_peace_response_rule(clone,date,native_validity);
    if (clone) execution_destroy_temp_action(clone);
    if (!cloned) {
        execution_emit_inspection_failure(request,"NATIVE_RESPONSE_CLONE_UNVERIFIED"); return;
    }
    execution_emit_inspection(request,pending,native_validity,alliance_after,
        alliance_readable);
}

static void execution_inbound_response_tick() noexcept {
    if (!inbound_response_handler_enabled) return;
    char wire[bridge::alliance_inbound_response_wire::kMaxWireBytes+1]{};
    DWORD size=0;
    if (!execution_read_request_file(inbound_response_request_path,wire,
        bridge::alliance_inbound_response_wire::kMaxWireBytes,size)) return;
    ResponseRequest request{};
    bridge::alliance_inbound_response_wire::ParseResult parsed=
        bridge::alliance_inbound_response_wire::parse_response_request(wire,size,request);
    if (!parsed.ok()) return;
    int32_t date=0; std::uint64_t now=0;
    char expected_session[bridge::alliance_execution_wire::kMaxSessionIdLength+1]{};
    if (!execution_frame_context(date,now,expected_session)) {
        execution_queue_response_unknown(request,-1,false,false); return;
    }
    auto context=bridge::alliance_inbound_response_wire::validate_context(
        request,expected_session,now,date);
    if (!context.ok()) {
        execution_queue_response_unknown(request,-1,false,false); return;
    }
    if (!execution_response_rules_complete(strcmp(request.action_id,"offer_royal_marriage")==0,
        strcmp(request.action_id,"support_independence")==0,
        strcmp(request.action_id,"ask_military_access")==0,
        strcmp(request.action_id,"offer_vassalization")==0,
        strcmp(request.action_id,"trade_favors_for_gold")==0
            || strcmp(request.action_id,"trade_favors_for_trust")==0
            || strcmp(request.action_id,"trade_favors_for_men")==0,
        strcmp(request.action_id,"trade_favors_for_trust")==0,
        strcmp(request.action_id,"trade_favors_for_men")==0,
        strcmp(request.action_id,"peace_offer")==0)) {
        execution_queue_response_unknown(request,-1,false,false); return;
    }
    InboundPendingView pending{};
    if (!inbound_pending_reserve(request.native_proposal_id,
            request.original_actor,pending)) {
        execution_queue_response_unknown(request,-1,false,false); return;
    }
    if ((pending.royal_marriage!=(strcmp(request.action_id,"offer_royal_marriage")==0)
            || pending.support_independence!=(strcmp(request.action_id,"support_independence")==0)
            || pending.military_access!=(strcmp(request.action_id,"ask_military_access")==0)
            || pending.vassalization!=(strcmp(request.action_id,"offer_vassalization")==0)
            || pending.favor_gold!=(strcmp(request.action_id,"trade_favors_for_gold")==0)
            || pending.favor_trust!=(strcmp(request.action_id,"trade_favors_for_trust")==0)
            || pending.favor_men!=(strcmp(request.action_id,"trade_favors_for_men")==0)
            || pending.peace_offer!=(strcmp(request.action_id,"peace_offer")==0))) {
        inbound_pending_release(pending.proposal_id,pending.generation);
        execution_queue_response_unknown(request,-1,false,false); return;
    }
    execution_submit_inbound_response(request,pending,date);
}

static void execution_inbound_tick() noexcept {
    if (!inbound_response_handler_enabled) return;
    execution_inbound_inspection_tick();
    execution_inbound_response_tick();
}

static void execution_call_original(void* value) noexcept {
    using Original=void (*)(void*);
    Original original=reinterpret_cast<Original>(execution_entry_original
        ?static_cast<void*>(execution_entry_original):bridge_response_original);
    if (original) original(value);
}

static bool execution_consume_target(ExecutionBinding& binding,
    const ProtocolWrapperShape& entry) noexcept {
    AlliancePayload entry_payload{};
    if (!binding.postcloned || binding.consumed || binding.invalidated
        || !binding.target.prefix_readable || !entry.prefix_readable
        || entry.raw10!=binding.target.raw10 || entry.raw38!=binding.target.raw38
        || entry.raw3c!=binding.target.raw3c || entry.raw40!=binding.target.raw40
        || entry.raw44!=binding.target.raw44
        || !execution_payload(entry.payload,entry_payload)
        || entry_payload!=binding.payload) return false;
    NativeHeader header=execution_header(entry);
    if (entry.origin48!=0xffffu || entry.flags4a!=0
        || entry.sequence4c!=binding.source_header.seq) return false;
    Context context=execution_context();
    bridge::alliance_authority::OperationResult consumed=execution_ledger.consume_entry(
        context,binding.claim,binding.phase,binding.target_wrapper,binding.target_action,
        binding.payload,header);
    if (!consumed.ok()) return false;
    binding.final_entry_header=header;
    binding.consumed=true;
    return true;
}

static bool execution_entry_is_offer(const ProtocolWrapperShape& shape) noexcept {
    AlliancePayload payload{};
    return execution_payload(shape.payload,payload) && payload.variant38==1
        && payload.state34==0;
}

static bool execution_entry_is_response(const ProtocolWrapperShape& shape,
    AlliancePayload& payload) noexcept {
    return execution_payload(shape.payload,payload) && payload.variant38==1
        && (payload.state34==1 || payload.state34==2);
}

static bool execution_entry_is_dissolve(const ProtocolWrapperShape& shape) noexcept {
    AlliancePayload payload{};
    return execution_payload(shape.payload,payload) && payload.variant38==0
        && payload.state34==0;
}

// Called by the response shim.  It owns the one call to the generic native
// executor, which has the confirmed void(this) ABI.  The shim returns without
// jumping to the original a second time.
extern "C" int bridge_execution_execute(void* value) {
    bridge_response_observe(value);
    ProtocolWrapperShape entry=protocol_capture(value);
    AlliancePayload payload{};
    if (!entry.identity || !entry.readable || !execution_payload(entry.payload,payload)) {
        uintptr_t action=0,table=0; uint64_t actor=0,recipient=0;
        if (entry.identity && read(entry.address+0x50,action)
            && read(action,table)
            && (table==base+lifecycle_declarewar_vtable_rva || table==base+lifecycle_peace_vtable_rva)
            && read(action+0x10,actor) && read(action+0x20,recipient)
            && (execution_is_fra(actor)
                || (table==base+lifecycle_peace_vtable_rva && execution_is_fra(recipient)))) {
            execution_failure("unknown",table==base+lifecycle_peace_vtable_rva
                ?"FRA_PEACE_PAYLOAD_UNREADABLE":"FRA_DECLARE_WAR_PAYLOAD_UNREADABLE"); return 0;
        }
        execution_call_original(value); return 1;
    }
    int target_slot=execution_find_target(entry);
    if (target_slot>=0) {
        ExecutionBinding& binding=execution_bindings[static_cast<unsigned>(target_slot)];
        if (!execution_consume_target(binding,entry)) {
            execution_mark_invalid(binding);
            return 0;
        }
        if (binding.inbound_response_request && payload.family==ActionFamily::peace
            && !inbound_pending_commit(binding.pending_proposal_id,binding.pending_generation)) {
            execution_mark_invalid(binding);
            execution_peace_inbound_unknown(binding.response_request,static_cast<int32_t>(payload.state34),true,false);
            return 0;
        }
        ResponseScope previous=execution_response_scope;
        if (binding.sender)
            execution_response_scope=ResponseScope{true,static_cast<unsigned>(target_slot)};
        execution_call_original(value);
        execution_response_scope=previous;
        if (binding.sender) {
            if (!binding.submission_queued) {
                binding.submission_queued=true;
                execution_queue_submission(binding,entry);
            }
            if (payload.family==ActionFamily::peace) {
                bool war_after=true;
                const bool verified=execution_peace_war_state(payload,war_after);
                bool pending_active=true;
                const bool pending_removed=binding.inbound_response_request
                    && inbound_pending_is_active(binding.pending_proposal_id,binding.pending_generation,pending_active)
                    && !pending_active;
                if ((binding.inbound_response_request?pending_removed:(verified && !war_after)) && !binding.response_queued) {
                    binding.response_queued=true;
                    execution_queue_response(binding,static_cast<int32_t>(payload.state34),
                        war_after,verified,pending_removed);
                }
            } else if (payload.family==ActionFamily::gift) {
                binding.gift_after_verified=gift_resource_capture(
                    payload.actor10,payload.recipient20,binding.gift_after);
                if (!binding.response_queued) {
                    binding.response_queued=true;
                    execution_queue_response(binding,static_cast<int32_t>(payload.state34),false,
                        binding.gift_after_verified,false);
                }
            } else if (payload.family==ActionFamily::influence) {
                binding.influence_after_verified=influence_resource_capture(
                    payload.actor10,payload.recipient20,binding.influence_after);
                if (!binding.response_queued) {
                    binding.response_queued=true;
                    execution_queue_response(binding,static_cast<int32_t>(payload.state34),false,
                        binding.influence_after_verified,false);
                }
            } else if (execution_unilateral_family(payload.family)) {
                bool after=false;
                const bool verified=execution_read_after(payload,after);
                if (payload.family==ActionFamily::curry_favors) {
                    const bool start=strcmp(execution_binding_action(binding),"curry_favors")==0;
                    // A task assignment is considered proven only after the
                    // authorized transport target was consumed and the
                    // native effect produced the expected active transition.
                    // The query path intentionally leaves this field false;
                    // it has no post-effect assignment evidence.
                    binding.diplomat_assignment_verified=binding.diplomat_required
                        && binding.diplomat_context_verified && binding.transport_verified
                        && binding.consumed && verified
                        && binding.alliance_before!=start && after==start;
                }
                if (!binding.response_queued) {
                    binding.response_queued=true;
                    execution_queue_response(binding,static_cast<int32_t>(payload.state34),after,verified,false);
                }
            } else if (binding.phase==Phase::dissolve) {
                bool after=false;
                const bool verified=execution_read_after(payload,after);
                if (!binding.response_queued) {
                    binding.response_queued=true;
                    execution_queue_response(binding,0,after,verified,false);
                }
            } else if (binding.inbound_response_request) {
                bool after=false;
                const bool after_verified=execution_read_after(payload,after);
                bool pending_active=false;
                const bool pending_found=inbound_pending_is_active(
                    binding.pending_proposal_id,binding.pending_generation,pending_active);
                const bool pending_removed=pending_found && !pending_active;
                if (!binding.response_queued) {
                    binding.response_queued=true;
                    execution_queue_response(binding,
                        static_cast<int32_t>(payload.state34),after,
                        after_verified,pending_removed);
                }
            }
        } else if (binding.response) {
            bool after=false;
            bool verified=execution_read_after(payload,after);
            if (!binding.response_queued) {
                binding.response_queued=true;
                execution_queue_response(binding,static_cast<int32_t>(payload.state34),after,verified,false);
            }
        }
        return 1;
    }
    // Peace has its own outer flags and full offer. Until its inbound decision
    // path is integrated, keep controlled-country choices explicit here rather
    // than passing them through the Alliance pending/response interpretation.
    if (payload.family==ActionFamily::peace) {
        if (payload.state34==0 && execution_is_fra(payload.actor10)) {
            execution_failure("unknown","UNAUTHORIZED_FRA_PEACE_OFFER"); return 0;
        }
        if ((payload.state34==1 || payload.state34==2) && execution_is_fra(payload.recipient20)) {
            execution_failure("unknown","UNAUTHORIZED_FRA_PEACE_RESPONSE"); return 0;
        }
        if (payload.state34==0 && execution_is_fra(payload.recipient20)) {
            bridge_inbound_scope_begin(reinterpret_cast<void*>(entry.action),payload.actor10,
                payload.recipient20,0,payload.variant38);
            if (!bridge_inbound_scope_active()) {
                execution_failure("unknown","FRA_PEACE_INBOUND_SCOPE_UNAVAILABLE"); return 0;
            }
            execution_call_original(value);
            if (bridge_inbound_scope_active()) bridge_inbound_observe_pending();
            bridge_inbound_scope_end();
            return 1;
        }
        execution_call_original(value); return 1;
    }
    if ((payload.family==ActionFamily::gift || payload.family==ActionFamily::influence)
        && execution_is_fra(payload.actor10)) {
        execution_failure("unknown",payload.family==ActionFamily::gift
            ?"UNAUTHORIZED_FRA_GIFT":"UNAUTHORIZED_FRA_INFLUENCE");
        return 0;
    }
    // Diplomat tasks and Guarantee are unilateral. Other actors' native processing
    // is forwarded even when its recipient is FRA; no LLM acceptance exists.
    if (execution_unilateral_family(payload.family)) {
        if (execution_is_fra(payload.actor10)) {
            execution_failure("unknown",payload.family==ActionFamily::declare_war?"UNAUTHORIZED_FRA_DECLARE_WAR":
                payload.family==ActionFamily::insult?"UNAUTHORIZED_FRA_INSULT":
                payload.family==ActionFamily::guarantee?"UNAUTHORIZED_FRA_GUARANTEE":
                payload.family==ActionFamily::curry_favors
                ?"UNAUTHORIZED_FRA_CURRY_FAVORS_TASK":
                payload.family==ActionFamily::spy_network
                ?"UNAUTHORIZED_FRA_SPY_TASK":"UNAUTHORIZED_FRA_IMPROVE_TASK"); return 0;
        }
        execution_call_original(value); return 1;
    }
    // Only the canonical FRA state-0 offer is isolated.  Other countries,
    // other alliance phases, military and economic commands remain native.
    if (execution_entry_is_offer(entry) && execution_is_fra(payload.actor10)) {
        execution_failure("unknown",payload.family==ActionFamily::vassalization
            ?"UNAUTHORIZED_FRA_VASSALIZATION_OFFER":payload.family==ActionFamily::military_access
            ?"UNAUTHORIZED_FRA_MILITARY_ACCESS_REQUEST":payload.family==ActionFamily::support_independence
            ?"UNAUTHORIZED_FRA_SUPPORT_OFFER":payload.family==ActionFamily::royal_marriage
            ?"UNAUTHORIZED_FRA_ROYAL_OFFER":payload.family==ActionFamily::favor_gold
            ?"UNAUTHORIZED_FRA_FAVOR_GOLD_OFFER":"UNAUTHORIZED_FRA_OFFER");
        return 0;
    }
    if (execution_entry_is_dissolve(entry) && execution_is_fra(payload.actor10)) {
        execution_failure("unknown",payload.family==ActionFamily::vassalization
            ?"UNAUTHORIZED_FRA_VASSALIZATION_CANCEL":payload.family==ActionFamily::military_access
            ?"UNAUTHORIZED_FRA_MILITARY_ACCESS_CANCEL":payload.family==ActionFamily::support_independence
            ?"UNAUTHORIZED_FRA_SUPPORT_REVOKE":payload.family==ActionFamily::royal_marriage
            ?"UNAUTHORIZED_FRA_ROYAL_BREAK":"UNAUTHORIZED_FRA_DISSOLVE");
        return 0;
    }
    if (execution_entry_is_response(entry,payload)
        && execution_is_fra(payload.recipient20)) {
        execution_failure("unknown",payload.family==ActionFamily::vassalization
            ?"UNAUTHORIZED_FRA_VASSALIZATION_RESPONSE":payload.family==ActionFamily::military_access
            ?"UNAUTHORIZED_FRA_MILITARY_ACCESS_RESPONSE":payload.family==ActionFamily::support_independence
            ?"UNAUTHORIZED_FRA_SUPPORT_RESPONSE":payload.family==ActionFamily::royal_marriage
            ?"UNAUTHORIZED_FRA_ROYAL_RESPONSE":payload.family==ActionFamily::favor_gold
            ?"UNAUTHORIZED_FRA_FAVOR_GOLD_RESPONSE":"UNAUTHORIZED_FRA_RESPONSE");
        return 0;
    }
    // A non-FRA state-0 offer addressed to the canonical FRA is allowed to
    // take the native pending path under a private TLS scope.  The predicate
    // relay consumes this scope only at the exact 4e81b8 callsite; it never
    // changes the global roster or country AI and is ended after the original
    // executor returns and the bounded pending list snapshot is taken.
    bridge_inbound_scope_begin(reinterpret_cast<void*>(entry.action),payload.actor10,
        payload.recipient20,static_cast<int32_t>(payload.state34),payload.variant38);
    execution_call_original(value);
    if (bridge_inbound_scope_active()) bridge_inbound_observe_pending();
    bridge_inbound_scope_end();
    return 1;
}

#include "declarewar-execution-preflight.inc"
#include "peace-execution-preflight.inc"
#include "peace-execution.inc"

static bool execution_preflight(const ExecutionRequest& request,
    uint64_t& actor,uint64_t& recipient,int32_t& date,
    unsigned char*& action,void*& wrapper,
    ProtocolWrapperShape& source,AlliancePayload& payload,
    uintptr_t& dispatcher,bool& action_constructed,
    const char** failure_reason=nullptr) noexcept {
    if (failure_reason) *failure_reason=nullptr;
    if (!strcmp(request.action_id,"declare_war"))
        return execution_declarewar_preflight(request,actor,recipient,date,action,wrapper,
            source,payload,dispatcher,action_constructed,failure_reason);
    action_constructed=false;
    uintptr_t game=0; uint64_t player=0;
    if (!read(base+0x233fe58,game) || !read(game+0x1dd0,date)
        || !read(game+0x1e60,player)
        || static_cast<uint32_t>(player&0xffffffu)!=0x524f50u
        || !alliance_query_country("FRA",actor)
        || !execution_target_allowed(request.recipient,request.action_id)
        || !alliance_query_country(request.recipient,recipient) || actor==recipient)
        return false;
    const bool marriage=strcmp(request.action_id,"offer_royal_marriage")==0
        || strcmp(request.action_id,"break_royal_ties")==0;
    const bool improve=strcmp(request.action_id,"improve_relations")==0
        || strcmp(request.action_id,"stop_improving_relations")==0;
    const bool spy=strcmp(request.action_id,"build_spy_network")==0
        || strcmp(request.action_id,"stop_building_spy_network")==0;
    const bool guarantee=strcmp(request.action_id,"proclaim_guarantee")==0
        || strcmp(request.action_id,"revoke_guarantee")==0;
    const bool support=strcmp(request.action_id,"support_independence")==0
        || strcmp(request.action_id,"revoke_support_independence")==0;
    const bool military=strcmp(request.action_id,"ask_military_access")==0
        || strcmp(request.action_id,"cancel_military_access")==0;
    const bool vassal=strcmp(request.action_id,"offer_vassalization")==0
        || strcmp(request.action_id,"cancel_vassalization")==0;
    const bool favor_gold=strcmp(request.action_id,"trade_favors_for_gold")==0;
    const bool favor_trust=strcmp(request.action_id,"trade_favors_for_trust")==0;
    const bool favor_men=strcmp(request.action_id,"trade_favors_for_men")==0;
    const bool curry=strcmp(request.action_id,"curry_favors")==0
        || strcmp(request.action_id,"stop_curry_favors")==0;
    const bool gift=strcmp(request.action_id,"send_gift")==0;
    const bool influence=strcmp(request.action_id,"influence_nation")==0;
    const FactoryActionQueryMethods* unilateral=unilateral_query_family(request.action_id);
    const bool insult=!strcmp(request.action_id,"send_insult") || !strcmp(request.action_id,"scornful_insult");
    const FactoryActionQueryMethods* factory_methods=gift?&gift_query_methods:
        influence?&influence_query_methods:favor_gold?&favor_gold_query_methods:
        favor_trust?&favor_trust_query_methods:favor_men?&favor_men_query_methods:
        insult?&insult_query_methods:vassal?&vassal_query_methods:military?&military_query_methods:support?&support_query_methods:unilateral;
    const uintptr_t expected_vtable=base+(factory_methods?factory_methods->vtable_rva:marriage?0x1c80ab0:0x1c80720);
    uintptr_t display=0,validity=0,send_gate=0,requires_diplomat=0;
    if (!read(expected_vtable+0x88,display) || display!=base+(factory_methods?factory_methods->display_rva:marriage?0x4ef7e0:0x512ca0)
        || !read(expected_vtable+0x80,validity)
        || (validity!=base+(factory_methods?factory_methods->validity_rva:marriage?0x4ef3e0:0x511d90)
            && (factory_methods || marriage || validity!=reinterpret_cast<uintptr_t>(&observation_alliance_validity)))
        || !read(expected_vtable+0x90,send_gate) || send_gate!=base+(factory_methods||marriage?0x4e9b40:0x512a00)
        || !read(expected_vtable+(factory_methods?factory_methods->diplomat_slot:0x100),requires_diplomat)
        || requires_diplomat!=base+(factory_methods?factory_methods->diplomat_rva:0x8f440))
        return false;
    if (curry) {
        uintptr_t effect=0;
        // Curry's +0x48 is the native start/stop mutation path.  Verify the
        // confirmed method identity, then let the original executor perform
        // the effect; the bridge never edits the relation rows itself.
        if (!read(expected_vtable+0x48,effect) || effect!=base+0x5ace80) return false;
    }
    bool visible=false;
    const bool offer=strcmp(request.action_id,"offer_alliance")==0
        || strcmp(request.action_id,"offer_royal_marriage")==0
        || strcmp(request.action_id,"improve_relations")==0
        || strcmp(request.action_id,"build_spy_network")==0
        || strcmp(request.action_id,"proclaim_guarantee")==0
        || strcmp(request.action_id,"support_independence")==0
        || strcmp(request.action_id,"ask_military_access")==0
        || strcmp(request.action_id,"offer_vassalization")==0
        || strcmp(request.action_id,"curry_favors")==0
        || strcmp(request.action_id,"send_gift")==0
        || strcmp(request.action_id,"influence_nation")==0
        || favor_gold || favor_trust || favor_men || insult;
    const bool visible_read=factory_methods ? factory_query_visibility(actor,recipient,offer,visible,*factory_methods)
        : alliance_query_visibility(actor,recipient,offer,visible,marriage?0x28df:0x293d);
    if (!visible_read || !visible) return false;
    if (marriage || factory_methods) {
        uintptr_t database=0,countries=0,country=0;
        if (!read(base+0x233d8b0,database) || !read(database+0x118,countries)
            || !read(countries+static_cast<uintptr_t>((actor>>32)&0xffff)*8,country)) return false;
        using UiCreator=void* (*)(void*,int32_t,uint64_t,unsigned char,void*);
        action=static_cast<unsigned char*>(reinterpret_cast<UiCreator>(base+0x35a8b0)(
            reinterpret_cast<void*>(country),factory_methods?factory_methods->selector:0x28df,recipient,offer?1:0,nullptr));
        if (!action) return false;
        action_constructed=true;
        if (insult) {
            if (request.insult_id>=0 && !insult_query_candidates("",actor,recipient,request.insult_id,false).selected_valid)
                return false;
            memcpy(action+0x40,&request.insult_id,sizeof(request.insult_id));
        }
        if (gift) {
            int32_t canonical_raw=0;
            if (!gift_influence_amount_valid(request.gift_ducats,canonical_raw)
                || canonical_raw!=request.gift_amount_raw
                || !gift_influence_write_i32(reinterpret_cast<uintptr_t>(action)+0x40,canonical_raw))
                return false;
            int32_t readback=0;
            if (!read(reinterpret_cast<uintptr_t>(action)+0x40,readback)
                || readback!=canonical_raw) return false;
        }
    } else {
        using Constructor=void* (*)(void*,uint64_t,uint64_t,int32_t);
        reinterpret_cast<Constructor>(base+kConstructorRva)(action,actor,recipient,date);
        if (!offer) action[0x38]=0;
    }
    action_constructed=true;
    uintptr_t action_vtable=0,wrapper_method=0;
    if (!read(reinterpret_cast<uintptr_t>(action),action_vtable)
        || action_vtable!=expected_vtable
        || !read(action_vtable+0x40,wrapper_method)) return false;
    const bool original_wrapper=wrapper_method==base+kWrapperMethodRva;
    const bool installed_wrapper=wrapper_method==reinterpret_cast<uintptr_t>(&lifecycle_wrapper_observe)
        && lifecycle_wrapper_original==reinterpret_cast<LifecycleWrapperMethod>(base+kWrapperMethodRva);
    if (!original_wrapper && !installed_wrapper) return false;
    if (marriage || factory_methods) {
        // Native UI sender 597920 and Royal constructor 4f0950 initialize
        // both words at send time. The factory's old sentinel is query-only;
        // pending cleanup 3607f0 rejects that sentinel in date28.
        std::memcpy(action+0x28,&date,sizeof(date));
        std::memcpy(action+0x2c,&date,sizeof(date));
    }
    const bool needs_diplomat=reinterpret_cast<bool (*)(void*)>(requires_diplomat)(action);
    if (needs_diplomat) {
        unsigned available=0;
        if (!alliance_query_diplomats(actor,available)) {
            if (failure_reason) *failure_reason="NATIVE_DIPLOMAT_CONTEXT_UNAVAILABLE";
            return false;
        }
        if (available==0) {
            if (failure_reason) *failure_reason="NATIVE_DIPLOMAT_UNAVAILABLE";
            return false;
        }
    }
    using Predicate=bool (*)(void*,void*,unsigned char);
    bool common=vassal?reinterpret_cast<bool (*)(void*,void*)>(display)(action,nullptr)
        :reinterpret_cast<Predicate>(display)(action,nullptr,0);
    bool native_valid=vassal?reinterpret_cast<bool (*)(void*,void*)>(validity)(action,nullptr)
        :reinterpret_cast<Predicate>(validity)(action,nullptr,0);
    // These unilateral families use +0x90 for tooltip/cost text; +0x88 is
    // their native enabled guard, and +0x80 checks the action-specific rules.
    bool gate=factory_methods || reinterpret_cast<Predicate>(send_gate)(action,nullptr,0);
    if (!common || !native_valid || !gate) return false;
    using Wrapper=void* (*)(void*,void**);
    wrapper=nullptr;
    Wrapper wrap=reinterpret_cast<Wrapper>(wrapper_method);
    if (!wrap(action,&wrapper) || !wrapper) return false;
    source=protocol_capture(wrapper);
    if (!source.identity || !source.readable || !source.prefix_readable
        || !execution_payload(source.payload,payload)
        || payload.actor10!=actor || payload.mirror18!=actor
        || payload.recipient20!=recipient || payload.state34!=0
        || payload.variant38!=(offer?1u:0u) || payload.extra60!=0
        || payload.parameter40!=(gift?request.gift_amount_raw:insult?request.insult_id:0)
        || payload.family!=(gift?ActionFamily::gift:influence?ActionFamily::influence:favor_gold?ActionFamily::favor_gold:favor_trust?ActionFamily::favor_trust:favor_men?ActionFamily::favor_men:curry?ActionFamily::curry_favors:insult?ActionFamily::insult:vassal?ActionFamily::vassalization:military?ActionFamily::military_access:support?ActionFamily::support_independence:guarantee?ActionFamily::guarantee:spy?ActionFamily::spy_network:improve?ActionFamily::improve_relations:
            marriage?ActionFamily::royal_marriage:ActionFamily::alliance)) return false;
    int32_t favor_amount=0;
    if (favor_gold && !favor_gold_amount(action,favor_amount)) return false;
    if ((favor_trust || favor_men) && !favor_trade_amount(favor_trust,action,favor_amount)) return false;
    (void)favor_amount;
    uintptr_t transport=0;
    if (!execution_world_dispatcher(dispatcher,transport)) return false;
    return true;
}

static bool execution_read_wire(ExecutionRequest& request) noexcept {
    if (GetFileAttributesW(execution_request_path)==INVALID_FILE_ATTRIBUTES) return false;
    char wire[bridge::alliance_execution_wire::kMaxWireBytes+1]{};
    HANDLE file=CreateFileW(execution_request_path,GENERIC_READ,FILE_SHARE_READ,
        nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if (file==INVALID_HANDLE_VALUE) return false;
    DWORD size=GetFileSize(file,nullptr),got=0;
    bool read_ok=size<=bridge::alliance_execution_wire::kMaxWireBytes
        && ReadFile(file,wire,size,&got,nullptr) && got==size;
    CloseHandle(file);
    DeleteFileW(execution_request_path);
    if (!read_ok) { execution_failure("unknown","EXECUTION_WIRE_READ_FAILED"); return false; }
    bridge::alliance_execution_wire::ParseResult parsed=
        bridge::alliance_execution_wire::parse_request(wire,size,request);
    if (!parsed.ok()) {
        // The parser may have copied a partial or invalid request id.  Keep
        // malformed input out of JSON and out of the native result channel.
        execution_failure("",
            bridge::alliance_execution_wire::parse_error_name(parsed.error));
        return false;
    }
    return true;
}

// Operator fixture: construct a legal native packet without creating any
// authority seed. It uses the ordinary transport and must be blocked at entry.
// The production four-tool adapter never publishes this channel.
static void execution_authority_test_tick() noexcept {
    if (!execution_authority_test_path[0]) return;
    char wire[96]{}; DWORD size=0;
    if (!execution_read_request_file(execution_authority_test_path,wire,sizeof(wire)-1,size)) return;
    if (execution_declarewar_authority_test(wire,size)) return;
    if (execution_peace_inbound_fixture(wire,size)) return;
    if (execution_peace_authority_test(wire,size)) return;
    constexpr char dissolve_wire[]="TEST_ONLY FRA_DISSOLVE_PRO_WITHOUT_AUTHORITY\n";
    constexpr char offer_wire[]="TEST_ONLY FRA_OFFER_SAV_WITHOUT_AUTHORITY\n";
    constexpr char royal_offer_wire[]="TEST_ONLY FRA_ROYAL_OFFER_SAV_WITHOUT_AUTHORITY\n";
    constexpr char royal_break_wire[]="TEST_ONLY FRA_ROYAL_BREAK_PRO_WITHOUT_AUTHORITY\n";
    constexpr char improve_wire[]="TEST_ONLY FRA_IMPROVE_SAV_WITHOUT_AUTHORITY\n";
    constexpr char improve_direct_wire[]="TEST_ONLY FRA_IMPROVE_SAV_DIRECT_WITHOUT_AUTHORITY\n";
    constexpr char spy_wire[]="TEST_ONLY FRA_SPY_SAV_WITHOUT_AUTHORITY\n";
    constexpr char spy_direct_wire[]="TEST_ONLY FRA_SPY_SAV_DIRECT_WITHOUT_AUTHORITY\n";
    constexpr char spy_stop_wire[]="TEST_ONLY FRA_STOP_SPY_SAV_WITHOUT_AUTHORITY\n";
    constexpr char spy_stop_direct_wire[]="TEST_ONLY FRA_STOP_SPY_SAV_DIRECT_WITHOUT_AUTHORITY\n";
    constexpr char guarantee_wire[]="TEST_ONLY FRA_GUARANTEE_SAV_WITHOUT_AUTHORITY\n";
    constexpr char guarantee_direct_wire[]="TEST_ONLY FRA_GUARANTEE_SAV_DIRECT_WITHOUT_AUTHORITY\n";
    constexpr char revoke_wire[]="TEST_ONLY FRA_REVOKE_GUARANTEE_SAV_WITHOUT_AUTHORITY\n";
    constexpr char revoke_direct_wire[]="TEST_ONLY FRA_REVOKE_GUARANTEE_SAV_DIRECT_WITHOUT_AUTHORITY\n";
    constexpr char curry_wire[]="TEST_ONLY FRA_CURRY_SAV_WITHOUT_AUTHORITY\n";
    constexpr char curry_direct_wire[]="TEST_ONLY FRA_CURRY_SAV_DIRECT_WITHOUT_AUTHORITY\n";
    constexpr char curry_stop_wire[]="TEST_ONLY FRA_STOP_CURRY_SAV_WITHOUT_AUTHORITY\n";
    constexpr char curry_stop_direct_wire[]="TEST_ONLY FRA_STOP_CURRY_SAV_DIRECT_WITHOUT_AUTHORITY\n";
    const bool dissolve=size==sizeof(dissolve_wire)-1 && !memcmp(wire,dissolve_wire,size);
    const bool offer=size==sizeof(offer_wire)-1 && !memcmp(wire,offer_wire,size);
    const bool royal_offer=size==sizeof(royal_offer_wire)-1 && !memcmp(wire,royal_offer_wire,size);
    const bool royal_break=size==sizeof(royal_break_wire)-1 && !memcmp(wire,royal_break_wire,size);
    const bool improve=size==sizeof(improve_wire)-1 && !memcmp(wire,improve_wire,size);
    const bool improve_direct=size==sizeof(improve_direct_wire)-1 && !memcmp(wire,improve_direct_wire,size);
    const bool spy=size==sizeof(spy_wire)-1 && !memcmp(wire,spy_wire,size);
    const bool spy_direct=size==sizeof(spy_direct_wire)-1 && !memcmp(wire,spy_direct_wire,size);
    const bool spy_stop=size==sizeof(spy_stop_wire)-1 && !memcmp(wire,spy_stop_wire,size);
    const bool spy_stop_direct=size==sizeof(spy_stop_direct_wire)-1 && !memcmp(wire,spy_stop_direct_wire,size);
    const bool guarantee=size==sizeof(guarantee_wire)-1 && !memcmp(wire,guarantee_wire,size);
    const bool guarantee_direct=size==sizeof(guarantee_direct_wire)-1 && !memcmp(wire,guarantee_direct_wire,size);
    const bool revoke=size==sizeof(revoke_wire)-1 && !memcmp(wire,revoke_wire,size);
    const bool revoke_direct=size==sizeof(revoke_direct_wire)-1 && !memcmp(wire,revoke_direct_wire,size);
    const bool curry=size==sizeof(curry_wire)-1 && !memcmp(wire,curry_wire,size);
    const bool curry_direct=size==sizeof(curry_direct_wire)-1 && !memcmp(wire,curry_direct_wire,size);
    const bool curry_stop=size==sizeof(curry_stop_wire)-1 && !memcmp(wire,curry_stop_wire,size);
    const bool curry_stop_direct=size==sizeof(curry_stop_direct_wire)-1 && !memcmp(wire,curry_stop_direct_wire,size);
    char support_kind[56]{},support_recipient[4]{}; int support_consumed=0;
    const bool support_wire=sscanf(wire,"TEST_ONLY %55s %3s%n",support_kind,
        support_recipient,&support_consumed)==2 && strcmp(wire+support_consumed,"\n")==0
        && strlen(support_recipient)==3;
    const bool support=support_wire && strcmp(support_kind,"FRA_SUPPORT_WITHOUT_AUTHORITY")==0;
    const bool support_direct=support_wire && strcmp(support_kind,"FRA_SUPPORT_DIRECT_WITHOUT_AUTHORITY")==0;
    const bool support_revoke=support_wire && strcmp(support_kind,"FRA_REVOKE_SUPPORT_WITHOUT_AUTHORITY")==0;
    const bool support_revoke_direct=support_wire && strcmp(support_kind,"FRA_REVOKE_SUPPORT_DIRECT_WITHOUT_AUTHORITY")==0;
    const bool military=support_wire && strcmp(support_kind,"FRA_MILITARY_ACCESS_WITHOUT_AUTHORITY")==0;
    const bool military_direct=support_wire && strcmp(support_kind,"FRA_MILITARY_ACCESS_DIRECT_WITHOUT_AUTHORITY")==0;
    const bool military_cancel=support_wire && strcmp(support_kind,"FRA_CANCEL_MILITARY_ACCESS_WITHOUT_AUTHORITY")==0;
    const bool military_cancel_direct=support_wire && strcmp(support_kind,"FRA_CANCEL_MILITARY_ACCESS_DIRECT_WITHOUT_AUTHORITY")==0;
    const bool vassal_offer=support_wire && !strcmp(support_kind,"FRA_VASSALIZATION_WITHOUT_AUTHORITY");
    const bool vassal_offer_direct=support_wire && !strcmp(support_kind,"FRA_VASSALIZATION_DIRECT_WITHOUT_AUTHORITY");
    const bool vassal_cancel=support_wire && !strcmp(support_kind,"FRA_CANCEL_VASSALIZATION_WITHOUT_AUTHORITY");
    const bool vassal_cancel_direct=support_wire && !strcmp(support_kind,"FRA_CANCEL_VASSALIZATION_DIRECT_WITHOUT_AUTHORITY");
    const bool curry_kind=support_wire && !strcmp(support_kind,"FRA_CURRY_SAV_WITHOUT_AUTHORITY");
    const bool curry_direct_kind=support_wire && !strcmp(support_kind,"FRA_CURRY_SAV_DIRECT_WITHOUT_AUTHORITY");
    const bool curry_stop_kind=support_wire && !strcmp(support_kind,"FRA_STOP_CURRY_SAV_WITHOUT_AUTHORITY");
    const bool curry_stop_direct_kind=support_wire && !strcmp(support_kind,"FRA_STOP_CURRY_SAV_DIRECT_WITHOUT_AUTHORITY");
    char insult_parameter[16]{}; int insult_value=-1,insult_consumed=0;
    const bool insult_wire=sscanf(wire,"TEST_ONLY %55s %3s %15s%n",support_kind,
        support_recipient,insult_parameter,&insult_consumed)==3
        && strcmp(wire+insult_consumed,"\n")==0
        && strlen(support_recipient)==3 && insult_query_parse_id(insult_parameter,insult_value)
        && insult_value>=-1;
    const bool insult=insult_wire && !strcmp(support_kind,"FRA_INSULT_WITHOUT_AUTHORITY");
    const bool insult_direct=insult_wire && !strcmp(support_kind,"FRA_INSULT_DIRECT_WITHOUT_AUTHORITY");
    const bool direct=insult_direct || improve_direct || spy_direct || spy_stop_direct || guarantee_direct || revoke_direct
        || support_direct || support_revoke_direct || military_direct || military_cancel_direct
        || vassal_offer_direct || vassal_cancel_direct || curry_direct || curry_stop_direct
        || curry_direct_kind || curry_stop_direct_kind;
    if (!dissolve && !offer && !royal_offer && !royal_break && !improve && !improve_direct
        && !spy && !spy_direct && !spy_stop && !spy_stop_direct && !guarantee && !guarantee_direct
        && !revoke && !revoke_direct && !support && !support_direct && !support_revoke && !support_revoke_direct
        && !military && !military_direct && !military_cancel && !military_cancel_direct && !insult && !insult_direct
        && !vassal_offer && !vassal_offer_direct && !vassal_cancel && !vassal_cancel_direct
        && !curry && !curry_direct && !curry_stop && !curry_stop_direct
        && !curry_kind && !curry_direct_kind && !curry_stop_kind && !curry_stop_direct_kind) {
        execution_failure("authority_test","TEST_WIRE_INVALID"); return;
    }
    const std::uint64_t test_bit=dissolve?1ull:offer?2ull:royal_offer?4ull:royal_break?8ull:improve?16ull:improve_direct?32ull:
        spy?64u:spy_direct?128u:spy_stop?256u:spy_stop_direct?512u:
        guarantee?1024u:guarantee_direct?2048u:revoke?4096u:revoke_direct?8192u:
        support?16384u:support_direct?32768u:support_revoke?65536u:support_revoke_direct?131072u:
        military?262144u:military_direct?524288u:military_cancel?1048576u:military_cancel_direct?2097152u:
        vassal_offer?(1u<<26):vassal_offer_direct?(1u<<27):vassal_cancel?(1u<<28):vassal_cancel_direct?(1u<<29):
        (curry||curry_kind)?(1ull<<30):(curry_direct||curry_direct_kind)?(1ull<<31):
        (curry_stop||curry_stop_kind)?(1ull<<32):(curry_stop_direct||curry_stop_direct_kind)?(1ull<<33):
        (insult_value>=0?(insult_direct?33554432ull:16777216ull):(insult_direct?8388608ull:4194304ull));
    if (execution_authority_tests_consumed&test_bit) {
        execution_failure("authority_test","TEST_ALREADY_CONSUMED"); return;
    }
    execution_authority_tests_consumed|=test_bit;
    ExecutionRequest request{};
    strcpy(request.action_id,royal_offer?"offer_royal_marriage":royal_break?"break_royal_ties":
        dissolve?"dissolve_alliance":(improve||improve_direct)?"improve_relations":
        (spy||spy_direct)?"build_spy_network":(spy_stop||spy_stop_direct)?"stop_building_spy_network":
        (guarantee||guarantee_direct)?"proclaim_guarantee":(revoke||revoke_direct)?"revoke_guarantee":
        (support||support_direct)?"support_independence":
        (support_revoke||support_revoke_direct)?"revoke_support_independence":
        (military||military_direct)?"ask_military_access":
        (military_cancel||military_cancel_direct)?"cancel_military_access":
        (vassal_offer||vassal_offer_direct)?"offer_vassalization":
        (vassal_cancel||vassal_cancel_direct)?"cancel_vassalization":
        (curry||curry_direct||curry_kind||curry_direct_kind)?"curry_favors":
        (curry_stop||curry_stop_direct||curry_stop_kind||curry_stop_direct_kind)?"stop_curry_favors":
        (insult||insult_direct)?(insult_value>=0?"scornful_insult":"send_insult"):"offer_alliance");
    if (insult || insult_direct) request.insult_id=insult_value;
    strcpy(request.actor,"FRA");
    strcpy(request.recipient,(curry||curry_direct||curry_stop||curry_stop_direct)
        ?"SAV":(support||support_direct||support_revoke||support_revoke_direct
        ||military||military_direct||military_cancel||military_cancel_direct||insult||insult_direct
        ||vassal_offer||vassal_offer_direct||vassal_cancel||vassal_cancel_direct
        )
        ?support_recipient:(dissolve || royal_break)?"PRO":"SAV");
    strcpy(request.phase,"initiate");
    alignas(16) unsigned char action_storage[0x58]{};
    unsigned char* action=action_storage;
    void* wrapper=nullptr; ProtocolWrapperShape source{}; AlliancePayload payload{};
    uint64_t actor=0,recipient=0; int32_t date=0; uintptr_t dispatcher=0;
    bool constructed=false;
    if (!execution_preflight(request,actor,recipient,date,action,wrapper,source,payload,dispatcher,constructed)) {
        execution_release_constructed(wrapper,action,constructed);
        execution_failure("authority_test","TEST_NATIVE_PREFLIGHT_FAILED"); return;
    }
    // No execution_bind_sender, no ledger seed and no sender TLS scope.
    void* outgoing=wrapper;
    bool dispatched=false;
    if (direct) {
        // Exercise the real patched function entry with the same void(this)
        // ABI used by native command callers; no ledger seed or transport claim exists.
        reinterpret_cast<void (*)(void*)>(base+0x4e7c80)(wrapper);
    } else {
        dispatched=reinterpret_cast<bool (*)(void*,void**)>(base+kDispatcherRva)(
            reinterpret_cast<void*>(dispatcher),&outgoing);
    }
    if (outgoing) execution_release_constructed(outgoing,nullptr,false);
    execution_release_constructed(nullptr,action,constructed);
    char message[800];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_alliance_authority_test_dispatched\",\"session_id\":\"%lu-%llx\",\"action_id\":\"%.27s\",\"actor\":\"FRA\",\"recipient\":\"%.3s\",\"phase\":\"initiate\",\"date_raw\":%d,\"source_wrapper\":\"0x%llx\",\"source_action\":\"0x%llx\",\"variant38\":%llu,\"state34\":%llu,\"dispatch_route\":\"%s\",\"dispatcher_accepted\":%s,\"authority_seed_created\":false}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
        request.action_id,request.recipient,date,static_cast<unsigned long long>(source.address),
        static_cast<unsigned long long>(source.action),static_cast<unsigned long long>(payload.variant38),
        static_cast<unsigned long long>(payload.state34),direct?"direct_entry":"transport",
        dispatched?"true":"false");
    line(message);
}

static void execution_tick() {
    if (!execution_initialized || !execution_handler_enabled || !control_ready()) return;
    execution_authority_test_tick();
    Context context=execution_context();
    execution_ledger.invalidate_expired(context);
    execution_peace_tick();
    ExecutionRequest request{};
    if (!execution_read_wire(request)) return;
    char expected_session[bridge::alliance_execution_wire::kMaxSessionIdLength+1]{};
    snprintf(expected_session,sizeof(expected_session),"%lu-%llx",
        static_cast<unsigned long>(GetCurrentProcessId()),
        static_cast<unsigned long long>(observation_creation));
    FILETIME now_filetime{}; GetSystemTimeAsFileTime(&now_filetime);
    uint64_t now=(static_cast<uint64_t>(now_filetime.dwHighDateTime)<<32)|now_filetime.dwLowDateTime;
    uintptr_t game=0; int32_t date=0;
    if (!read(base+0x233fe58,game) || !read(game+0x1dd0,date)) {
        execution_queue_submission_failure(request);
        execution_failure(request.request_id,"EXECUTION_GAME_CONTEXT_UNAVAILABLE"); return;
    }
    bridge::alliance_execution_wire::ContextResult context_check=
        bridge::alliance_execution_wire::validate_context(request,expected_session,now,date);
    if (!context_check.ok()) {
        execution_queue_submission_failure(request);
        execution_failure(request.request_id,
            bridge::alliance_execution_wire::context_error_name(context_check.error)); return;
    }
    alignas(16) unsigned char action_storage[0x58]{};
    unsigned char* action=action_storage;
    void* wrapper=nullptr; ProtocolWrapperShape source{}; AlliancePayload payload{};
    uint64_t actor=0,recipient=0; int32_t constructed_date=0; uintptr_t dispatcher=0;
    bool action_constructed=false;
    const char* preflight_reason=nullptr;
    if (!execution_preflight(request,actor,recipient,constructed_date,action,wrapper,
        source,payload,dispatcher,action_constructed,&preflight_reason)) {
        execution_release_constructed(wrapper,action,action_constructed);
        execution_preflight_failure(request,preflight_reason?preflight_reason:"EXECUTION_NATIVE_PREFLIGHT_FAILED");
        execution_queue_submission_failure(request);
        return;
    }
    unsigned slot=execution_free_binding();
    if (slot==kInvalidBinding) {
        execution_release_constructed(wrapper,action,action_constructed);
        execution_queue_submission_failure(request);
        execution_failure(request.request_id,"LEDGER_CAPACITY_FULL"); return;
    }
    execution_bind_sender(request,source,payload,slot,reinterpret_cast<uintptr_t>(action));
    ExecutionBinding& binding=execution_bindings[slot];
    {
        if (payload.family==ActionFamily::curry_favors) {
            // The native +0xf8 predicate has already been checked during
            // preflight.  Capture the bounded native diplomat context and
            // independently read the current task relation before dispatch.
            // The relation read is required for the generic baseline gate;
            // leaving it at its default false would reject every start/stop
            // request as NATIVE_RELATION_BASELINE_UNVERIFIED.
            binding.diplomat_required=true;
            binding.diplomat_context_verified=alliance_query_diplomats(
                payload.actor10,binding.diplomat_available_count);
            binding.alliance_before_verified=execution_read_after(
                payload,binding.alliance_before);
        } else if (payload.family==ActionFamily::favor_gold) {
            binding.favor_before_verified=favor_gold_capture(payload.actor10,
                payload.recipient20,binding.favor_before);
            binding.favor_amount_verified=favor_gold_amount(action,
                binding.favor_amount_raw);
            binding.alliance_before=false;
            binding.alliance_before_verified=binding.favor_before_verified
                && binding.favor_amount_verified;
        } else if (payload.family==ActionFamily::favor_trust
            || payload.family==ActionFamily::favor_men) {
            const bool trust=payload.family==ActionFamily::favor_trust;
            binding.favor_trade_before_verified=favor_trade_capture_action(trust,
                payload.actor10,payload.recipient20,action,binding.favor_trade_before);
            binding.favor_trade_amount_verified=favor_trade_amount(trust,action,
                binding.favor_trade_amount_raw);
            binding.alliance_before=false;
            binding.alliance_before_verified=binding.favor_trade_before_verified
                && binding.favor_trade_amount_verified;
        } else if (payload.family==ActionFamily::gift) {
            binding.gift_amount_raw=payload.parameter40;
            binding.gift_before_verified=gift_resource_capture(
                payload.actor10,payload.recipient20,binding.gift_before);
            binding.alliance_before=false;
            binding.alliance_before_verified=binding.gift_before_verified
                && binding.gift_amount_raw>0;
        } else if (payload.family==ActionFamily::influence) {
            binding.influence_before_verified=influence_resource_capture(
                payload.actor10,payload.recipient20,binding.influence_before);
            binding.alliance_before=false;
            binding.alliance_before_verified=binding.influence_before_verified;
        } else if (payload.family==ActionFamily::declare_war) {
            DeclareWarExecutionState before{};
            binding.alliance_before_verified=execution_declarewar_state(payload.actor10,payload.recipient20,before);
            binding.alliance_before=before.active;
            binding.war_id_before=before.war_id;
            binding.stability_before_raw=before.stability_raw;
            binding.stability_before_verified=before.stability_verified;
        } else if (payload.family==ActionFamily::insult) {
            binding.alliance_before_verified=insult_query_state(payload.actor10,payload.recipient20,
                payload.parameter40>=0,binding.insult_before);
            binding.alliance_before=binding.insult_before.active;
        } else if (payload.family==ActionFamily::vassalization) {
            binding.alliance_before_verified=vassal_query_relation(payload.actor10,payload.recipient20,binding.vassal_before);
            binding.alliance_before=binding.vassal_before.active;
        } else binding.alliance_before_verified=execution_read_after(payload,binding.alliance_before);
        if (!binding.alliance_before_verified
            || binding.alliance_before!=(binding.phase==Phase::dissolve)) {
            execution_release_constructed(wrapper,action,action_constructed);
            execution_mark_invalid(binding);
            execution_queue_submission_failure(request);
            execution_failure(request.request_id,"NATIVE_RELATION_BASELINE_UNVERIFIED");
            return;
        }
    }
    if (binding.invalidated || !binding.seed.seed_serial) {
        execution_release_constructed(wrapper,action,action_constructed);
        execution_queue_submission_failure(request);
        return;
    }
    void* outgoing=wrapper;
    execution_sender_scope=SenderScope{true,slot};
    using Submit=bool (*)(void*,void**);
    bool accepted=reinterpret_cast<Submit>(base+kDispatcherRva)(
        reinterpret_cast<void*>(dispatcher),&outgoing);
    execution_sender_scope=SenderScope{};
    // The native dispatcher owns/destroys the wrapper after it clears the
    // pointer.  A missing transport proof revokes this seed; no JSON value can
    // turn it into a queue receipt.
    if (!accepted || !binding.claim_bound || !binding.transport_verified) {
        Context current=execution_context();
        execution_ledger.revoke_request(current,binding.seed,binding.phase);
        execution_mark_invalid(binding);
        execution_failure(request.request_id,accepted?"NATIVE_TRANSPORT_PROOF_MISSING":"NATIVE_DISPATCH_REJECTED");
    }
    if (outgoing) execution_release_constructed(outgoing,nullptr,false);
    execution_release_constructed(nullptr,action,action_constructed);
}

static void execution_entry_release_unpublished() noexcept {
    if (execution_entry_published) return;
    if (execution_entry_runtime_registered) {
        RtlDeleteFunctionTable(&execution_entry_runtime_function);
        execution_entry_runtime_registered=false;
    }
    if (execution_entry_block) VirtualFree(execution_entry_block,0,MEM_RELEASE);
    execution_entry_block=nullptr;
    execution_entry_original=nullptr;
}

static bool execution_entry_install() {
    constexpr size_t trampoline_size=sizeof(execution_entry_signature)+14;
    auto target=reinterpret_cast<unsigned char*>(base+0x4e7c80);
    unsigned char actual[sizeof(execution_entry_signature)]{};
    if (!read(reinterpret_cast<uintptr_t>(target),actual)
        || memcmp(actual,execution_entry_signature,sizeof(actual))) return false;
    execution_entry_block=bridge_alliance_inbound_detail::inbound_allocate_near();
    if (!execution_entry_block) return false;
    execution_entry_original=execution_entry_block+0x100;
    memcpy(execution_entry_original,execution_entry_signature,sizeof(actual));
    absolute_jump(execution_entry_original+sizeof(actual),base+0x4e7c92);
    DWORD64 image_base=0;
    PRUNTIME_FUNCTION parent=RtlLookupFunctionEntry(
        static_cast<DWORD64>(base+0x4e7c80),&image_base,nullptr);
    const uintptr_t trampoline_rva=reinterpret_cast<uintptr_t>(execution_entry_original)-base;
    if (!parent || image_base!=static_cast<DWORD64>(base)
        || parent->BeginAddress!=0x4e7c80 || trampoline_rva+trampoline_size>0xffffffffull) {
        execution_entry_release_unpublished(); return false;
    }
    // The trampoline starts with the identical complete native prologue, so
    // its instruction offsets use the original unwind recipe unchanged.
    execution_entry_runtime_function.BeginAddress=static_cast<DWORD>(trampoline_rva);
    execution_entry_runtime_function.EndAddress=static_cast<DWORD>(trampoline_rva+trampoline_size);
    execution_entry_runtime_function.UnwindData=parent->UnwindData;
    execution_entry_runtime_registered=RtlAddFunctionTable(
        &execution_entry_runtime_function,1,static_cast<DWORD64>(base))!=FALSE;
    if (!execution_entry_runtime_registered) {
        execution_entry_release_unpublished(); return false;
    }
    DWORD protection=0;
    if (!VirtualProtect(execution_entry_block,0x1000,PAGE_EXECUTE_READ,&protection)) {
        execution_entry_release_unpublished(); return false;
    }
    FlushInstructionCache(GetCurrentProcess(),execution_entry_block,0x1000);
    memset(execution_entry_replacement,0x90,sizeof(execution_entry_replacement));
    absolute_jump(execution_entry_replacement,reinterpret_cast<uintptr_t>(&bridge_response_stub));
    execution_entry_patch_plan=bridge_entry_patch::PatchPlan{};
    execution_entry_patch_plan.count=1;
    execution_entry_patch_plan.targets[0]={target,sizeof(actual),execution_entry_signature,
        execution_entry_replacement,execution_entry_original,trampoline_size};
    const auto result=bridge_entry_patch::guarded_patch_apply(execution_entry_patch_plan);
    execution_entry_published=result.published;
    if (!result.success) {
        char message[420];
        snprintf(message,sizeof(message),"{\"event\":\"generic_execution_guarded_install_failed\",\"published\":%s,\"threads_resumed\":%s,\"rollback_complete\":%s,\"failure_stage\":%u,\"win32_error\":%lu,\"restart_required\":true}\n",
            result.published?"true":"false",result.threads_resumed?"true":"false",
            result.rollback_complete?"true":"false",static_cast<unsigned>(result.failure_stage),
            static_cast<unsigned long>(result.error));
        line(message);
        execution_entry_release_unpublished();
        return false;
    }
    line("{\"event\":\"native_generic_execution_entry_guard_installed\",\"covers_direct_calls\":true,\"covers_vtable_calls\":true,\"original_unwind_registered\":true}\n");
    return true;
}

static bool execution_install() {
    if (!bridge_response_original || bridge_response_original!=reinterpret_cast<void*>(base+0x4e7c80)) return false;
    execution_ledger.reset_session_epoch(observation_creation);
    for (auto& binding:execution_bindings) binding=ExecutionBinding{};
    inbound_response_handler_enabled=false;
    execution_initialized=true;
    execution_handler_enabled=true;
    return execution_entry_install();
}

static bool execution_rollback() {
    execution_handler_enabled=false;
    inbound_response_handler_enabled=false;
    execution_sender_scope=SenderScope{};
    execution_response_scope=ResponseScope{};
    if (!execution_entry_patch_plan.count) return true;
    unsigned char actual[sizeof(execution_entry_signature)]{};
    if (!read(base+0x4e7c80,actual)) return false;
    if (!memcmp(actual,execution_entry_signature,sizeof(actual))) return true;
    if (memcmp(actual,execution_entry_replacement,sizeof(actual))) return false;
    const auto result=bridge_entry_patch::guarded_patch_rollback(execution_entry_patch_plan);
    // Published trampolines and unwind tables stay alive for in-flight calls.
    return result.success && result.threads_resumed && result.protection_restored;
}

static void execution_favor_state_json(const FavorGoldState& state,
    bool verified,char* output,size_t capacity) noexcept {
    snprintf(output,capacity,
        "{\"complete\":%s,\"actor_treasury_raw\":%d,\"recipient_treasury_raw\":%d,\"favors_raw\":%d,\"cost_raw\":%d}",
        state.complete && verified?"true":"false",state.actor_treasury_raw,
        state.recipient_treasury_raw,state.favors_raw,state.cost_raw);
}

static void execution_favor_trade_state_json(bool trust,
    const FavorTradeState& state,bool verified,char* output,size_t capacity) noexcept {
    if (trust) snprintf(output,capacity,
        "{\"complete\":%s,\"recipient_trust_raw\":%d,\"favors_raw\":%d,\"cost_raw\":%d}",
        state.complete && verified?"true":"false",state.recipient_trust_raw,
        state.favors_raw,state.cost_raw);
    else snprintf(output,capacity,
        "{\"complete\":%s,\"actor_manpower_raw\":%d,\"recipient_manpower_raw\":%d,\"favors_raw\":%d,\"cost_raw\":%d}",
        state.complete && verified?"true":"false",state.actor_manpower_raw,
        state.recipient_manpower_raw,state.favors_raw,state.cost_raw);
}

static void execution_gift_state_json(const GiftResourceState& state,
    bool verified,char* output,size_t capacity) noexcept {
    snprintf(output,capacity,
        "{\"complete\":%s,\"actor_treasury_raw\":%d,\"recipient_treasury_raw\":%d}",
        state.complete && verified?"true":"false",state.actor_treasury_raw,
        state.recipient_treasury_raw);
}

static void execution_influence_state_json(const InfluenceResourceState& state,
    bool verified,char* output,size_t capacity) noexcept {
    snprintf(output,capacity,
        "{\"complete\":%s,\"actor_treasury_raw\":%d,\"recipient_trust_raw\":%d,\"influencer_active\":%s}",
        state.complete && verified?"true":"false",state.actor_treasury_raw,
        state.recipient_trust_raw,state.influencer_relation?"true":"false");
}

static void execution_flush() {
    for (unsigned at=0;at<16;++at) {
        SubmissionResult result{};
        AcquireSRWLockExclusive(&execution_result_lock);
        if (!execution_submission_size) { ReleaseSRWLockExclusive(&execution_result_lock); break; }
        result=execution_submission_results[execution_submission_head];
        execution_submission_head=(execution_submission_head+1)%kBindingCapacity;
        --execution_submission_size;
        ReleaseSRWLockExclusive(&execution_result_lock);
        char message[2048];
        const bool favor=!strcmp(result.action_id,"trade_favors_for_gold");
        const bool favor_resource=!strcmp(result.action_id,"trade_favors_for_trust")
            || !strcmp(result.action_id,"trade_favors_for_men");
        const char* family_fields=(!strcmp(result.action_id,"offer_vassalization")
            || !strcmp(result.action_id,"cancel_vassalization"))?"\"family\":\"vassalization\",":"";
        if (!strcmp(result.action_id,"send_gift") && result.submitted) {
            snprintf(message,sizeof(message),
                "{\"event\":\"native_alliance_submission_result\",\"family\":\"gift\",\"request_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"send_gift\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"%.8s\",\"date_raw\":%d,\"native_variant\":1,\"ducats\":%d,\"amount_raw\":%d,\"submitted\":true,\"native_queue_verified\":true,\"transport_ring\":true,\"native_origin\":%u,\"native_flags\":%u,\"native_sequence\":%u}\n",
                result.request_id,result.session_id,result.actor,result.recipient,
                result.phase,result.date_raw,result.gift_ducats,result.gift_amount_raw,
                static_cast<unsigned>(result.native_origin),static_cast<unsigned>(result.native_flags),
                result.native_sequence);
        } else if (!strcmp(result.action_id,"influence_nation") && result.submitted) {
            snprintf(message,sizeof(message),
                "{\"event\":\"native_alliance_submission_result\",\"family\":\"influence\",\"request_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"influence_nation\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"%.8s\",\"date_raw\":%d,\"native_variant\":1,\"submitted\":true,\"native_queue_verified\":true,\"transport_ring\":true,\"native_origin\":%u,\"native_flags\":%u,\"native_sequence\":%u}\n",
                result.request_id,result.session_id,result.actor,result.recipient,
                result.phase,result.date_raw,static_cast<unsigned>(result.native_origin),
                static_cast<unsigned>(result.native_flags),result.native_sequence);
        } else if (favor) {
            char before_json[240]{};
            execution_favor_state_json(result.favor_before,result.favor_before_verified,
                before_json,sizeof(before_json));
            snprintf(message,sizeof(message),
                "{\"event\":\"native_alliance_submission_result\",\"family\":\"favor_trade\",\"request_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"trade_favors_for_gold\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"%.8s\",\"date_raw\":%d,\"submitted\":%s,\"native_queue_verified\":%s,\"transport_ring\":%s,\"native_origin\":%u,\"native_flags\":%u,\"native_sequence\":%u,\"favor_trade\":{\"before\":%s,\"after\":null,\"amount_raw\":%d,\"complete\":%s,\"verified\":false}}\n",
                result.request_id,result.session_id,result.actor,result.recipient,result.phase,
                result.date_raw,result.submitted?"true":"false",result.submitted?"true":"false",
                result.submitted?"true":"false",static_cast<unsigned>(result.native_origin),
                static_cast<unsigned>(result.native_flags),result.native_sequence,before_json,
                result.favor_amount_raw,(result.favor_before_verified
                    && result.favor_amount_verified)?"true":"false");
        } else if (favor_resource) {
            const bool trust=!strcmp(result.action_id,"trade_favors_for_trust");
            char before_json[320]{};
            execution_favor_trade_state_json(trust,result.favor_trade_before,
                result.favor_trade_before_verified,before_json,sizeof(before_json));
            snprintf(message,sizeof(message),
                "{\"event\":\"native_alliance_submission_result\",\"family\":\"favor_trade\",\"request_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"%.27s\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"%.8s\",\"date_raw\":%d,\"native_variant\":1,\"submitted\":%s,\"native_queue_verified\":%s,\"transport_ring\":%s,\"native_origin\":%u,\"native_flags\":%u,\"native_sequence\":%u,\"favor_trade\":{\"kind\":\"%s\",\"before\":%s,\"after\":null,\"amount_raw\":%d,\"complete\":%s,\"verified\":false}}\n",
                result.request_id,result.session_id,result.action_id,result.actor,result.recipient,
                result.phase,result.date_raw,result.submitted?"true":"false",
                result.submitted?"true":"false",result.submitted?"true":"false",
                static_cast<unsigned>(result.native_origin),static_cast<unsigned>(result.native_flags),
                result.native_sequence,trust?"trust":"men",before_json,
                result.favor_trade_amount_raw,(result.favor_trade_before_verified
                    && result.favor_trade_amount_verified)?"true":"false");
        } else if (!strcmp(result.action_id,"curry_favors")
            || !strcmp(result.action_id,"stop_curry_favors")) {
            snprintf(message,sizeof(message),
                "{\"event\":\"native_alliance_submission_result\",\"family\":\"curry_favors\",\"request_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"%.27s\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"%.8s\",\"date_raw\":%d,\"native_variant\":%u,\"submitted\":%s,\"native_queue_verified\":%s,\"transport_ring\":%s,\"native_origin\":%u,\"native_flags\":%u,\"native_sequence\":%u,\"before_active\":%s,\"after_active\":null,\"diplomat_required\":%s,\"diplomat_context_verified\":%s,\"available_diplomat_count\":%u,\"diplomat_assignment_verified\":%s}\n",
                result.request_id,result.session_id,result.action_id,result.actor,result.recipient,
                result.phase,result.date_raw,!strcmp(result.action_id,"curry_favors")?1u:0u,
                result.submitted?"true":"false",result.submitted?"true":"false",
                result.submitted?"true":"false",static_cast<unsigned>(result.native_origin),
                static_cast<unsigned>(result.native_flags),result.native_sequence,
                result.curry_before_active?"true":"false",
                result.diplomat_required?"true":"false",
                result.diplomat_context_verified?"true":"false",
                result.diplomat_available_count,
                result.diplomat_assignment_verified?"true":"false");
        } else if (!strcmp(result.action_id,"declare_war")) {
            char call_allies_csv[64]{},promise_land_to_csv[64]{},co_belligerents_csv[64]{};
            declarewar_participant_csv(result.call_allies,call_allies_csv);
            declarewar_participant_csv(result.promise_land_to,promise_land_to_csv);
            declarewar_participant_csv(result.co_belligerents,co_belligerents_csv);
            snprintf(message,sizeof(message),
                "{\"event\":\"native_declare_war_submission_result\",\"family\":\"declare_war\",\"request_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"declare_war\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"%.8s\",\"date_raw\":%d,\"casus_belli\":\"%.128s\",\"war_goal_province\":%d,\"war_goal_beneficiary\":\"%.3s\",\"call_allies_csv\":\"%.63s\",\"promise_land_to_csv\":\"%.63s\",\"co_belligerents_csv\":\"%.63s\",\"submitted\":%s,\"transport_verified\":%s,\"request_binding_verified\":%s,\"native_origin\":%u,\"native_flags\":%u,\"native_sequence\":%u}\n",
                result.request_id,result.session_id,result.actor,result.recipient,result.phase,result.date_raw,
                result.casus_belli,result.war_goal_province,result.war_goal_beneficiary,
                call_allies_csv,promise_land_to_csv,co_belligerents_csv,
                result.submitted?"true":"false",result.submitted?"true":"false",result.submitted?"true":"false",
                static_cast<unsigned>(result.native_origin),static_cast<unsigned>(result.native_flags),result.native_sequence);
        } else if (result.submitted) {
            snprintf(message,sizeof(message),
                "{\"event\":\"native_alliance_submission_result\",\"request_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"%.27s\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"%.8s\",\"date_raw\":%d,%s\"submitted\":true,\"native_queue_verified\":true,\"transport_ring\":true,\"native_origin\":%u,\"native_flags\":%u,\"native_sequence\":%u}\n",
                result.request_id,result.session_id,result.action_id,result.actor,result.recipient,result.phase,result.date_raw,family_fields,
                static_cast<unsigned>(result.native_origin),static_cast<unsigned>(result.native_flags),result.native_sequence);
        } else {
            snprintf(message,sizeof(message),
                "{\"event\":\"native_alliance_submission_result\",\"request_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"%.27s\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"%.8s\",\"date_raw\":%d,%s\"submitted\":false,\"native_queue_verified\":false,\"transport_ring\":false}\n",
                result.request_id,result.session_id,result.action_id,result.actor,result.recipient,result.phase,result.date_raw,family_fields);
        }
        line(message);
    }
    for (unsigned at=0;at<16;++at) {
        ResponseResult result{};
        AcquireSRWLockExclusive(&execution_result_lock);
        if (!execution_response_size) { ReleaseSRWLockExclusive(&execution_result_lock); break; }
        result=execution_response_results[execution_response_head];
        execution_response_head=(execution_response_head+1)%kBindingCapacity;
        --execution_response_size;
        ReleaseSRWLockExclusive(&execution_result_lock);
        char message[2048];
        const bool marriage=strcmp(result.action_id,"offer_royal_marriage")==0
            || strcmp(result.action_id,"break_royal_ties")==0;
        const bool improve=strcmp(result.action_id,"improve_relations")==0
            || strcmp(result.action_id,"stop_improving_relations")==0;
        const bool spy=strcmp(result.action_id,"build_spy_network")==0
            || strcmp(result.action_id,"stop_building_spy_network")==0;
        const bool guarantee=strcmp(result.action_id,"proclaim_guarantee")==0
            || strcmp(result.action_id,"revoke_guarantee")==0;
        const bool support=strcmp(result.action_id,"support_independence")==0
            || strcmp(result.action_id,"revoke_support_independence")==0;
        const bool military=strcmp(result.action_id,"ask_military_access")==0
            || strcmp(result.action_id,"cancel_military_access")==0;
        const bool vassal=strcmp(result.action_id,"offer_vassalization")==0
            || strcmp(result.action_id,"cancel_vassalization")==0;
        const bool favor=!strcmp(result.action_id,"trade_favors_for_gold");
        const bool favor_resource=!strcmp(result.action_id,"trade_favors_for_trust")
            || !strcmp(result.action_id,"trade_favors_for_men");
        const bool curry=!strcmp(result.action_id,"curry_favors")
            || !strcmp(result.action_id,"stop_curry_favors");
        const char* before_key=vassal?"vassalization_before":military?"military_access_before":support?"support_independence_before":marriage?"royal_marriage_before":"alliance_before";
        const char* after_key=vassal?"vassalization_after":military?"military_access_after":support?"support_independence_after":marriage?"royal_marriage_after":"alliance_after";
        const char* family=vassal?"vassalization":military?"military_access":support?"support_independence":marriage?"royal_marriage":"alliance";
        char vassal_cost_fields[160]{};
        if (vassal && !strcmp(result.action_id,"cancel_vassalization"))
            snprintf(vassal_cost_fields,sizeof(vassal_cost_fields),
                "\"prestige_before_raw\":%d,\"prestige_after_raw\":%d,\"prestige_scale\":1000,",
                result.prestige_before,result.prestige_after);
        if (!strcmp(result.action_id,"send_gift")) {
            char before_json[180]{},after_json[180]{};
            execution_gift_state_json(result.gift_before,result.gift_before_verified,
                before_json,sizeof(before_json));
            execution_gift_state_json(result.gift_after,result.gift_after_verified,
                after_json,sizeof(after_json));
            const bool complete=result.gift_before_verified && result.gift_after_verified;
            const bool verified=result.gift_effect_verified && result.response_verified
                && result.request_binding_verified;
            snprintf(message,sizeof(message),
                "{\"event\":\"native_diplomacy_gift_execution_result\",\"request_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"send_gift\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"%.8s\",\"date_raw\":%d,\"outcome\":\"%.8s\",\"native_state\":%d,\"native_variant\":1,\"family\":\"gift\",\"gift\":{\"kind\":\"gift\",\"before\":%s,\"after\":%s,\"ducats\":%d,\"amount_raw\":%d,\"complete\":%s,\"verified\":%s},\"execution_verified\":%s,\"request_binding_verified\":%s}\n",
                result.request_id,result.session_id,result.actor,result.recipient,result.phase,
                result.date_raw,result.outcome,result.native_state,before_json,after_json,
                result.gift_ducats,result.gift_amount_raw,complete?"true":"false",
                verified?"true":"false",result.response_verified?"true":"false",
                result.request_binding_verified?"true":"false");
        } else if (!strcmp(result.action_id,"influence_nation")) {
            char before_json[180]{},after_json[180]{};
            execution_influence_state_json(result.influence_before,
                result.influence_before_verified,before_json,sizeof(before_json));
            execution_influence_state_json(result.influence_after,
                result.influence_after_verified,after_json,sizeof(after_json));
            const bool complete=result.influence_before_verified
                && result.influence_after_verified;
            const bool verified=result.influence_effect_verified && result.response_verified
                && result.request_binding_verified;
            snprintf(message,sizeof(message),
                "{\"event\":\"native_diplomacy_influence_execution_result\",\"request_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"influence_nation\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"%.8s\",\"date_raw\":%d,\"outcome\":\"%.8s\",\"native_state\":%d,\"native_variant\":1,\"family\":\"influence\",\"influence\":{\"kind\":\"influence\",\"before\":%s,\"after\":%s,\"cost_raw\":%d,\"opinion_raw\":%d,\"duration_months\":%d,\"complete\":%s,\"verified\":%s},\"execution_verified\":%s,\"request_binding_verified\":%s}\n",
                result.request_id,result.session_id,result.actor,result.recipient,result.phase,
                result.date_raw,result.outcome,result.native_state,before_json,after_json,
                result.influence_before.native_cost_raw,result.influence_before.opinion_raw,
                result.influence_before.duration_months,complete?"true":"false",
                verified?"true":"false",result.response_verified?"true":"false",
                result.request_binding_verified?"true":"false");
        } else if (favor_resource) {
            const bool trust=!strcmp(result.action_id,"trade_favors_for_trust");
            char before_json[320]{},after_json[320]{};
            execution_favor_trade_state_json(trust,result.favor_trade_before,
                result.favor_trade_before_verified,before_json,sizeof(before_json));
            execution_favor_trade_state_json(trust,result.favor_trade_after,
                result.favor_trade_after_verified,after_json,sizeof(after_json));
            snprintf(message,sizeof(message),
                "{\"event\":\"%s\",\"request_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"%.27s\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"%.8s\",\"date_raw\":%d,\"outcome\":\"%.8s\",\"native_state\":%d,\"native_variant\":1,\"family\":\"favor_trade\",\"favor_trade\":{\"kind\":\"%s\",\"before\":%s,\"after\":%s,\"amount_raw\":%d,\"complete\":%s,\"verified\":%s},\"execution_verified\":%s,\"request_binding_verified\":%s,\"pending_removed\":%s}\n",
                result.inbound_response?"native_diplomacy_favor_trade_response_result":"native_diplomacy_favor_trade_execution_result",
                result.request_id,result.session_id,result.action_id,result.actor,result.recipient,
                result.phase,result.date_raw,result.outcome,result.native_state,
                trust?"trust":"men",before_json,after_json,result.favor_trade_amount_raw,
                (result.favor_trade_before_verified && result.favor_trade_after_verified
                    && result.favor_trade_amount_verified)?"true":"false",
                (result.favor_trade_effect_verified && result.response_verified
                    && result.request_binding_verified)?"true":"false",
                result.response_verified?"true":"false",result.request_binding_verified?"true":"false",
                result.pending_removed?"true":"false");
        } else if (favor) {
            char before_json[240]{},after_json[240]{};
            execution_favor_state_json(result.favor_before,result.favor_before_verified,
                before_json,sizeof(before_json));
            execution_favor_state_json(result.favor_after,result.favor_after_verified,
                after_json,sizeof(after_json));
            snprintf(message,sizeof(message),
                "{\"event\":\"%s\",\"request_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"trade_favors_for_gold\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"%.8s\",\"date_raw\":%d,\"outcome\":\"%.8s\",\"native_state\":%d,\"native_variant\":1,\"family\":\"favor_trade\",\"favor_trade\":{\"before\":%s,\"after\":%s,\"amount_raw\":%d,\"complete\":%s,\"verified\":%s},\"execution_verified\":%s,\"request_binding_verified\":%s,\"pending_removed\":%s}\n",
                result.inbound_response?"native_diplomacy_favor_trade_response_result":
                    "native_diplomacy_favor_trade_execution_result",
                result.request_id,result.session_id,result.actor,result.recipient,result.phase,
                result.date_raw,result.outcome,result.native_state,before_json,after_json,
                result.favor_amount_raw,(result.favor_before_verified
                    && result.favor_after_verified && result.favor_amount_verified)?"true":"false",
                (result.favor_effect_verified && result.response_verified
                    && result.request_binding_verified)?"true":"false",
                result.response_verified?"true":"false",
                result.request_binding_verified?"true":"false",
                result.pending_removed?"true":"false");
        } else if (curry) {
            snprintf(message,sizeof(message),
                "{\"event\":\"native_diplomacy_task_execution_result\",\"request_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"%.27s\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"%.8s\",\"date_raw\":%d,\"outcome\":\"%.8s\",\"native_state\":%d,\"native_variant\":%u,\"family\":\"curry_favors\",\"before_active\":%s,\"after_active\":%s,\"task_before\":%s,\"task_after\":%s,\"diplomat_required\":%s,\"diplomat_context_verified\":%s,\"available_diplomat_count\":%u,\"diplomat_assignment_verified\":%s,\"execution_verified\":%s,\"request_binding_verified\":%s}\n",
                result.request_id,result.session_id,result.action_id,result.actor,result.recipient,
                result.phase,result.date_raw,result.outcome,result.native_state,
                !strcmp(result.action_id,"curry_favors")?1u:0u,
                result.alliance_before?"true":"false",result.alliance_after?"true":"false",
                result.alliance_before?"true":"false",result.alliance_after?"true":"false",
                result.diplomat_required?"true":"false",
                result.diplomat_context_verified?"true":"false",
                result.diplomat_available_count,
                result.diplomat_assignment_verified?"true":"false",
                result.response_verified?"true":"false",
                result.request_binding_verified?"true":"false");
        } else if (!strcmp(result.action_id,"declare_war")) {
            char war_id[24]="null",stability_before[24]="null",stability_after[24]="null";
            char call_allies_csv[64]{},promise_land_to_csv[64]{},co_belligerents_csv[64]{};
            declarewar_participant_csv(result.call_allies,call_allies_csv);
            declarewar_participant_csv(result.promise_land_to,promise_land_to_csv);
            declarewar_participant_csv(result.co_belligerents,co_belligerents_csv);
            if (result.war_identity_verified) snprintf(war_id,sizeof(war_id),"%d",result.war_id);
            if (result.stability_verified) {
                snprintf(stability_before,sizeof(stability_before),"%d",result.stability_before_raw);
                snprintf(stability_after,sizeof(stability_after),"%d",result.stability_after_raw);
            }
            snprintf(message,sizeof(message),
                "{\"event\":\"native_declare_war_execution_result\",\"request_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"declare_war\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"%.8s\",\"date_raw\":%d,\"casus_belli\":\"%.128s\",\"war_goal_province\":%d,\"war_goal_beneficiary\":\"%.3s\",\"call_allies_csv\":\"%.63s\",\"promise_land_to_csv\":\"%.63s\",\"co_belligerents_csv\":\"%.63s\",\"outcome\":\"%.8s\",\"native_state\":%d,\"family\":\"declare_war\",\"war_before\":%s,\"war_after\":%s,\"war_id\":%s,\"stability_before_raw\":%s,\"stability_after_raw\":%s,\"war_identity_verified\":%s,\"stability_verified\":%s,\"execution_verified\":%s,\"request_binding_verified\":%s}\n",
                result.request_id,result.session_id,result.actor,result.recipient,result.phase,result.date_raw,
                result.casus_belli,result.war_goal_province,result.war_goal_beneficiary,
                call_allies_csv,promise_land_to_csv,co_belligerents_csv,result.outcome,result.native_state,
                result.alliance_before?"true":"false",result.alliance_after?"true":"false",war_id,
                stability_before,stability_after,result.war_identity_verified?"true":"false",result.stability_verified?"true":"false",
                result.response_verified?"true":"false",result.request_binding_verified?"true":"false");
            line(message);
            snprintf(message,sizeof(message),
                "{\"event\":\"native_declare_war_consequence_private\",\"private\":true,\"request_id\":\"%.64s\",\"session_id\":\"%.27s\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"date_raw\":%d,\"native_war_reference\":\"0x%llx\",\"association_source\":\"symmetric_country_opponent_rows\",\"war_after\":%s,\"association_verified\":%s}\n",
                result.request_id,result.session_id,result.actor,result.recipient,result.date_raw,
                static_cast<unsigned long long>(result.private_war_reference),result.alliance_after?"true":"false",
                result.response_verified?"true":"false");
        } else if (!strcmp(result.action_id,"send_insult") || !strcmp(result.action_id,"scornful_insult")) {
            snprintf(message,sizeof(message),
                "{\"event\":\"native_diplomacy_insult_execution_result\",\"request_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"%.27s\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"%.8s\",\"date_raw\":%d,\"outcome\":\"%.8s\",\"native_state\":%d,\"native_variant\":1,\"family\":\"insult\",\"insult_id\":%d,\"insult_before\":%s,\"insult_after\":%s,\"opinion_modifier_before_raw\":%d,\"opinion_modifier_after_raw\":%d,\"prestige_before_raw\":%d,\"prestige_after_raw\":%d,\"execution_verified\":%s,\"request_binding_verified\":%s}\n",
                result.request_id,result.session_id,result.action_id,result.actor,result.recipient,result.phase,result.date_raw,
                result.outcome,result.native_state,result.insult_id,result.alliance_before?"true":"false",result.alliance_after?"true":"false",
                result.modifier_before,result.modifier_after,result.prestige_before,result.prestige_after,
                result.response_verified?"true":"false",result.request_binding_verified?"true":"false");
        } else if (improve || spy || guarantee) {
            snprintf(message,sizeof(message),
                "{\"event\":\"%s\",\"request_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"%.27s\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"%.8s\",\"date_raw\":%d,\"outcome\":\"%.8s\",\"native_state\":%d,\"native_variant\":%u,\"family\":\"%s\",\"%s\":%s,\"%s\":%s,\"execution_verified\":%s,\"request_binding_verified\":%s}\n",
                guarantee?"native_diplomacy_relation_execution_result":"native_diplomacy_task_execution_result",
                result.request_id,result.session_id,result.action_id,result.actor,result.recipient,result.phase,result.date_raw,result.outcome,
                result.native_state,(strcmp(result.action_id,"improve_relations")==0
                    || strcmp(result.action_id,"build_spy_network")==0 || strcmp(result.action_id,"proclaim_guarantee")==0)?1u:0u,
                guarantee?"guarantee":spy?"spy_network":"improve_relations",
                guarantee?"guarantee_before":"task_before",result.alliance_before?"true":"false",
                guarantee?"guarantee_after":"task_after",result.alliance_after?"true":"false",
                result.response_verified?"true":"false",result.request_binding_verified?"true":"false");
        } else if (strcmp(result.action_id,"dissolve_alliance")==0
            || strcmp(result.action_id,"break_royal_ties")==0
            || strcmp(result.action_id,"revoke_support_independence")==0
            || strcmp(result.action_id,"cancel_military_access")==0
            || strcmp(result.action_id,"cancel_vassalization")==0) {
            snprintf(message,sizeof(message),
                "{\"event\":\"%s\",\"request_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"%.27s\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"%.8s\",\"date_raw\":%d,\"outcome\":\"%.8s\",\"native_state\":%d,\"native_variant\":0,\"family\":\"%s\",\"%s\":%s,\"%s\":%s,%s\"execution_verified\":%s,\"request_binding_verified\":%s}\n",
                (support||military||vassal)?"native_diplomacy_relation_execution_result":"native_alliance_execution_result",
                result.request_id,result.session_id,result.action_id,result.actor,result.recipient,result.phase,result.date_raw,result.outcome,
                result.native_state,family,before_key,result.alliance_before?"true":"false",after_key,result.alliance_after?"true":"false",vassal_cost_fields,
                result.response_verified?"true":"false",result.request_binding_verified?"true":"false");
        } else snprintf(message,sizeof(message),
            "{\"event\":\"%s\",\"request_id\":\"%.64s\",\"session_id\":\"%.27s\",\"action_id\":\"%.27s\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"%.8s\",\"date_raw\":%d,\"outcome\":\"%.8s\",\"native_state\":%d,\"native_variant\":1,\"family\":\"%s\",\"%s\":%s,\"%s\":%s,\"response_verified\":%s,\"request_binding_verified\":%s,\"pending_removed\":%s}\n",
            (support||military||vassal)?"native_diplomacy_relation_response_result":"native_alliance_response_result",
            result.request_id,result.session_id,result.action_id,result.actor,result.recipient,result.phase,result.date_raw,result.outcome,
            result.native_state,family,before_key,result.alliance_before?"true":"false",after_key,result.alliance_after?"true":"false",
            result.response_verified?"true":"false",result.request_binding_verified?"true":"false",
            result.pending_removed?"true":"false");
        line(message);
    }
    LONG dropped=InterlockedExchange(&execution_result_dropped,0);
    if (dropped) {
        char message[180];
        snprintf(message,sizeof(message),"{\"event\":\"native_alliance_execution_result_drop\",\"dropped\":%ld,\"complete\":false}\n",static_cast<long>(dropped));
        line(message);
    }
}

} // namespace alliance_execution_detail

// The earlier observer includes use these callbacks before this file is
// included.  Keep the bridge symbols at global scope while the implementation
// remains namespaced and bounded.
static void execution_transport_loaded(const TransportCompletedEvent& event,
    const TransportLoadedRecord& record) {
    alliance_execution_detail::execution_transport_loaded(event,record);
}
static void execution_protocol_clone_completed(const ProtocolCloneEvent& event) {
    alliance_execution_detail::execution_protocol_clone_completed(event);
}
static void execution_lifecycle_source_destroyed(void* source,
    const LifecycleActionShape& snapshot,unsigned flags) {
    alliance_execution_detail::execution_lifecycle_source_destroyed(source,snapshot,flags);
}

using namespace alliance_execution_detail;
