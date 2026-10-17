// The Peace response/settlement handler is distinct from the generic wrapper
// executor. Guard its virtual entry as well; forwarding uses its proven
// void(action*) ABI, and other countries retain the native handler.
using PeaceHandlerMethod=void (*)(void*);
static PeaceHandlerMethod peace_handler_original=nullptr;
static bool peace_handler_installed=false;

// 4e7c80 assigns an envoy through 4e7580 before 4ea850 calls this handler.
// Verify that assignment against the actor's native diplomat record, rather
// than accepting an arbitrary change to the signed envoy field.
static bool peace_handler_native_envoy_matches(const AlliancePayload& payload) noexcept {
    if (payload.envoy30>=256) return false;
    uintptr_t country=0,holder=0,manager=0,begin=0,end=0;
    if (!peace_query_country_pointer(payload.actor10,country)
        || !read(country+0x1480,holder) || !read(holder+0x18,manager)
        || !read(manager+0x20,begin) || !read(manager+0x28,end)
        || end<begin || (end-begin)%8 || (end-begin)/8>256) return false;
    unsigned matches=0;
    for (uintptr_t item=begin;item<end;item+=8) {
        uintptr_t entry=0,record=0; int32_t id=-1,date=0;
        unsigned char active=0; uint64_t actor=0,recipient=0;
        if (!read(item,entry) || !read(entry+0x44,id)) return false;
        if (id!=static_cast<int32_t>(payload.envoy30)) continue;
        if (!read(entry+0x18,active) || !active || active>2
            || !read(entry+0x10,record) || !record
            || !read(record+0x80,actor) || actor!=payload.actor10
            || !read(record+0x88,recipient) || recipient!=payload.recipient20
            || !read(record+0x20,date)
            || static_cast<uint32_t>(date)!=payload.date2c) return false;
        ++matches;
    }
    return matches==1;
}

static void peace_handler_observe(void* action) {
    const DWORD incoming_error=GetLastError();
    const uintptr_t address=reinterpret_cast<uintptr_t>(action);
    const uintptr_t caller=reinterpret_cast<uintptr_t>(__builtin_return_address(0));
    uint64_t actor=0,recipient=0;
    const bool endpoints=read(address+0x10,actor) && read(address+0x20,recipient);
    const bool controlled=endpoints && (execution_is_fra(actor) || execution_is_fra(recipient));
    bool allowed=endpoints;
    bool native_envoy_verified=false;
    ExecutionBinding* response_binding=nullptr;
    const char* reason=endpoints?"OTHER_COUNTRIES_NATIVE":"PEACE_HANDLER_ENDPOINTS_UNREADABLE";
    LifecycleActionShape shape{};
    if (controlled) {
        shape=lifecycle_capture_shape(action);
        allowed=shape.matched && shape.peace_offer && shape.peace.valid();
        if (!allowed) reason="FRA_PEACE_PAYLOAD_UNREADABLE";
        else if (shape.state34==0 && execution_is_fra(actor)) {
            allowed=false;
            reason="UNAUTHORIZED_FRA_PEACE_OFFER";
            // A future sender can reach this handler only within the consumed
            // generic-entry binding that owns the same complete native offer.
            if (execution_response_scope.active
                && execution_response_scope.parent_slot<kBindingCapacity) {
                auto& binding=execution_bindings[execution_response_scope.parent_slot];
                AlliancePayload payload{};
                const bool decoded=execution_payload(shape,payload);
                native_envoy_verified=decoded && caller==base+0x4ea900
                    && binding.target_action.address==address
                    && peace_handler_native_envoy_matches(payload);
                allowed=binding.used && binding.consumed && !binding.invalidated
                    && binding.payload.family==ActionFamily::peace
                    && decoded && bridge::alliance_authority::peace_handler_payload_matches(
                        binding.payload,payload,native_envoy_verified);
                if (allowed) reason="CONSUMED_PEACE_BINDING";
            }
        } else if (shape.state34==0 && execution_is_fra(recipient)) {
            allowed=bridge_inbound_scope_matches(action);
            reason=allowed?"MATCHED_PEACE_INBOUND_SCOPE":"FRA_PEACE_INBOUND_SCOPE_UNAVAILABLE";
        } else if ((shape.state34==1 || shape.state34==2) && execution_is_fra(recipient)) {
            allowed=false; reason="UNAUTHORIZED_FRA_PEACE_RESPONSE";
            if (execution_response_scope.active
                && execution_response_scope.parent_slot<kBindingCapacity) {
                auto& binding=execution_bindings[execution_response_scope.parent_slot];
                AlliancePayload payload{};
                allowed=binding.used && binding.consumed && !binding.invalidated
                    && binding.inbound_response_request && binding.transport_verified
                    && binding.pending_proposal_id && binding.pending_generation
                    && binding.target_action.address==address
                    && binding.payload.family==ActionFamily::peace
                    && execution_payload(shape,payload) && payload==binding.payload
                    && ((shape.state34==2 && binding.phase==Phase::accept)
                        || (shape.state34==1 && binding.phase==Phase::reject));
                if (allowed) {
                    reason="CONSUMED_PEACE_INBOUND_RESPONSE_BINDING";
                    response_binding=&binding;
                }
            }
        } else if (shape.state34!=1 && shape.state34!=2) {
            allowed=false; reason="FRA_PEACE_STATE_UNSUPPORTED";
        } else reason="NPC_PEACE_RESPONSE_NATIVE";
    }
    // Generic entry observations are queued, whereas this event is written
    // synchronously. Record the live scope and comparison here so physical
    // log order cannot be mistaken for a separate ungranted request.
    const ExecutionBinding* scoped_binding=nullptr;
    if (execution_response_scope.active && execution_response_scope.parent_slot<kBindingCapacity)
        scoped_binding=&execution_bindings[execution_response_scope.parent_slot];
    AlliancePayload current_payload{};
    const bool decoded=controlled && execution_payload(shape,current_payload);
    const char* comparison="NO_RESPONSE_SCOPE";
    if (scoped_binding) {
        const auto& expected=scoped_binding->payload;
        if (!scoped_binding->used) comparison="BINDING_UNUSED";
        else if (!scoped_binding->consumed) comparison="BINDING_NOT_CONSUMED";
        else if (scoped_binding->invalidated) comparison="BINDING_INVALIDATED";
        else if (!decoded) comparison="PAYLOAD_DECODE_FAILED";
        else if (current_payload.family!=expected.family) comparison="FAMILY_CHANGED";
        else if (current_payload.actor10!=expected.actor10) comparison="ACTOR_CHANGED";
        else if (current_payload.mirror18!=expected.mirror18) comparison="MIRROR_CHANGED";
        else if (current_payload.recipient20!=expected.recipient20) comparison="RECIPIENT_CHANGED";
        else if (current_payload.date28!=expected.date28) comparison="DATE28_CHANGED";
        else if (current_payload.date2c!=expected.date2c) comparison="DATE2C_CHANGED";
        else if (current_payload.envoy30!=expected.envoy30) comparison="ENVOY_CHANGED";
        else if (current_payload.state34!=expected.state34) comparison="STATE_CHANGED";
        else if (current_payload.variant38!=expected.variant38) comparison="VARIANT_CHANGED";
        else if (current_payload.proposal3c!=expected.proposal3c) comparison="PROPOSAL_CHANGED";
        else if (current_payload.extra60!=expected.extra60) comparison="EXTRA60_CHANGED";
        else if (current_payload.parameter40!=expected.parameter40) comparison="PARAMETER40_CHANGED";
        else if (current_payload.war!=expected.war) comparison="WAR_PAYLOAD_CHANGED";
        else if (current_payload.peace!=expected.peace) comparison="PEACE_PAYLOAD_CHANGED";
        else comparison="PAYLOAD_EQUAL";
    }
    char message[2000]{};
    snprintf(message,sizeof(message),
        "{\"event\":\"native_peace_handler_entry\",\"private\":true,\"session_id\":\"%lu-%llx\","
        "\"callback_sequence\":%llu,\"action\":\"0x%llx\",\"caller_return_rva\":\"0x%llx\","
        "\"endpoints_readable\":%s,\"controlled_endpoint\":%s,\"snapshot_complete\":%s,"
        "\"state_raw\":%d,\"allowed\":%s,\"reason\":\"%s\",\"native_forward_count\":%u,"
        "\"thread_id\":%lu,\"response_scope_active\":%s,\"sender_scope_active\":%s,"
        "\"binding_request_id\":\"%.64s\",\"binding_consumed\":%s,\"payload_decoded\":%s,"
        "\"binding_payload_comparison\":\"%s\",\"native_envoy_verified\":%s,"
        "\"current_envoy\":%llu,\"expected_envoy\":%llu}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
        static_cast<unsigned long long>(lifecycle_next_sequence()),static_cast<unsigned long long>(address),
        static_cast<unsigned long long>(caller>=base+0x1000 && caller<base+0x1b66000?caller-base:0),
        endpoints?"true":"false",controlled?"true":"false",shape.peace.valid()?"true":"false",
        controlled?shape.state34:-1,allowed?"true":"false",reason,allowed?1u:0u,
        static_cast<unsigned long>(GetCurrentThreadId()),execution_response_scope.active?"true":"false",
        execution_sender_scope.active?"true":"false",
        scoped_binding && scoped_binding->used?scoped_binding->ledger_request_id:"-",
        scoped_binding && scoped_binding->consumed?"true":"false",decoded?"true":"false",comparison,
        native_envoy_verified?"true":"false",
        static_cast<unsigned long long>(current_payload.envoy30),
        static_cast<unsigned long long>(scoped_binding?scoped_binding->payload.envoy30:0));
    line(message);
    if (!allowed) {
        execution_failure("unknown",reason);
        SetLastError(incoming_error);
        return;
    }
    SetLastError(incoming_error);
    if (peace_handler_original) peace_handler_original(action);
    if (response_binding && peace_handler_original) {
        response_binding->peace_handler_returned=true;
        // Emit after the native handler returned. The binding was consumed
        // by the generic entry; no business result is inferred here.
        char returned[1100]{};
        snprintf(returned,sizeof(returned),
            "{\"event\":\"native_peace_handler_return\",\"family\":\"peace\",\"action_id\":\"peace_offer\","
            "\"session_id\":\"%.27s\",\"request_id\":\"%.64s\",\"actor\":\"%.3s\",\"recipient\":\"FRA\","
            "\"phase\":\"%.6s\",\"native_state\":%d,\"native_forward_count\":1,\"handler_consumed\":true,"
            "\"peace_payload_complete\":%s,\"transport_verified\":true}\n",
            response_binding->response_request.session_id,response_binding->response_request.request_id,
            response_binding->response_request.original_actor,response_binding->response_request.decision,
            shape.state34,shape.peace.valid()?"true":"false");
        line(returned);
    }
}

static bool peace_handler_authority_install() noexcept {
    auto* slot=reinterpret_cast<void**>(base+lifecycle_peace_vtable_rva+0x48);
    void* expected=reinterpret_cast<void*>(base+0x598f00);
    void* actual=nullptr;
    if (!read(reinterpret_cast<uintptr_t>(slot),actual) || actual!=expected) return false;
    peace_handler_original=reinterpret_cast<PeaceHandlerMethod>(expected);
    DWORD protection=0,ignored=0;
    if (!VirtualProtect(slot,8,PAGE_READWRITE,&protection)) return false;
    void* hook=reinterpret_cast<void*>(&peace_handler_observe);
    const bool installed=InterlockedCompareExchangePointer(
        reinterpret_cast<void* volatile*>(slot),hook,expected)==expected;
    const bool restored=VirtualProtect(slot,8,protection,&ignored)!=FALSE;
    if (!installed || !restored) {
        const bool reverted=!installed || InterlockedCompareExchangePointer(
            reinterpret_cast<void* volatile*>(slot),expected,hook)==hook;
        const bool protection_restored=VirtualProtect(slot,8,protection,&ignored)!=FALSE;
        lifecycle_rollback_incomplete=lifecycle_rollback_incomplete || !reverted || !protection_restored;
        return false;
    }
    peace_handler_installed=true;
    return true;
}

static bool peace_handler_authority_rollback() noexcept {
    if (!peace_handler_installed) return true;
    auto* slot=reinterpret_cast<void**>(base+lifecycle_peace_vtable_rva+0x48);
    DWORD protection=0,ignored=0;
    if (!VirtualProtect(slot,8,PAGE_READWRITE,&protection)) return false;
    void* expected=reinterpret_cast<void*>(base+0x598f00);
    void* hook=reinterpret_cast<void*>(&peace_handler_observe);
    void* previous=InterlockedCompareExchangePointer(
        reinterpret_cast<void* volatile*>(slot),expected,hook);
    const bool restored=VirtualProtect(slot,8,protection,&ignored)!=FALSE;
    const bool complete=(previous==hook || previous==expected) && restored;
    if (complete) peace_handler_installed=false;
    return complete;
}
