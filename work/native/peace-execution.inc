// Public Peace execution uses the common native transport/ledger lifecycle.
// This channel never treats a successful preview as a native submission.
using PeaceExecutionRequest=bridge::peace_execution_wire::PeaceExecutionRequest;
static wchar_t execution_peace_path[MAX_PATH]{};
static char execution_peace_seen[kBindingCapacity][65]{};
static unsigned execution_peace_seen_count=0;

static bool execution_peace_set_paths(const wchar_t* directory) noexcept {
    if (!directory || !directory[0]
        || swprintf(execution_peace_path,MAX_PATH,L"%ls\\diplomacy-peace-execute.req",directory)<0)
        return false;
    return GetFileAttributesW(execution_peace_path)==INVALID_FILE_ATTRIBUTES
        || DeleteFileW(execution_peace_path)!=FALSE;
}

static bool execution_peace_war_state(const AlliancePayload& payload,bool& active) noexcept {
    uintptr_t actor=0,recipient=0;
    PeaceWarReferenceList left{},right{};
    if (!peace_query_country_pointer(payload.actor10,actor)
        || !peace_query_country_pointer(payload.recipient20,recipient)
        || !peace_query_pair_references(actor,static_cast<unsigned>((payload.recipient20>>32)&0xffffu),left)
        || !peace_query_pair_references(recipient,static_cast<unsigned>((payload.actor10>>32)&0xffffu),right)
        || !peace_query_reference_sets_equal(left,right)) return false;
    active=left.count!=0;
    return true;
}

static void execution_peace_parameters_json(const PeaceExecutionRequest& request,
    char (&output)[700]) noexcept {
    char provinces[192]{}; std::size_t used=0;
    for (unsigned i=0;i<request.province_count;++i) {
        const int written=snprintf(provinces+used,sizeof(provinces)-used,
            "%s%d",i?",":"",request.province_ids[i]);
        if (written<=0 || static_cast<std::size_t>(written)>=sizeof(provinces)-used) return;
        used+=static_cast<std::size_t>(written);
    }
    snprintf(output,sizeof(output),"\"war_id\":\"%.29s\",\"direction\":\"%.7s\","
        "\"amount_raw\":%d,\"province_ids\":[%s],\"beneficiary\":\"%.3s\"",
        request.war_id,request.direction,request.amount_raw,provinces,
        request.selected_beneficiary?request.beneficiary:"-");
}

static void execution_peace_emit_submission(const PeaceExecutionRequest& request,
    bool submitted,const char* reason,const NativeHeader& header) noexcept {
    char parameters[700]{},message[1800]{};
    execution_peace_parameters_json(request,parameters);
    snprintf(message,sizeof(message),
        "{\"event\":\"native_peace_submission_result\",\"family\":\"peace\","
        "\"session_id\":\"%lu-%llx\",\"request_id\":\"%.64s\",\"action_id\":\"%.24s\","
        "\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"initiate\",\"date_raw\":%d,%s,"
        "\"submitted\":%s,\"transport_verified\":%s,\"request_binding_verified\":%s,"
        "\"reason\":\"%.96s\",\"native_origin\":%u,\"native_flags\":%u,\"native_sequence\":%u}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
        request.request_id,request.action_id,request.actor,request.recipient,request.date_raw,parameters,
        submitted?"true":"false",submitted?"true":"false",submitted?"true":"false",reason,
        static_cast<unsigned>(header.origin),static_cast<unsigned>(header.flags),header.seq);
    line(message);
}

static void execution_peace_submission(const ExecutionBinding& binding,
    const ProtocolWrapperShape& entry) noexcept {
    if (binding.inbound_response_request) {
        char message[1100]{};
        snprintf(message,sizeof(message),
            "{\"event\":\"native_peace_inbound_submission_result\",\"family\":\"peace\","
            "\"session_id\":\"%.27s\",\"request_id\":\"%.64s\",\"action_id\":\"peace_offer\","
            "\"actor\":\"%.3s\",\"recipient\":\"FRA\",\"decision_country\":\"FRA\",\"phase\":\"%.6s\","
            "\"date_raw\":%d,\"submitted\":true,\"transport_verified\":true,\"request_binding_verified\":true}\n",
            binding.response_request.session_id,binding.response_request.request_id,
            binding.response_request.original_actor,binding.response_request.decision,binding.response_request.date_raw);
        line(message); return;
    }
    execution_peace_emit_submission(binding.peace_request,true,"NATIVE_ENTRY_VERIFIED",execution_header(entry));
}

static void execution_peace_inbound_unknown(const ResponseRequest& request,
    int32_t state,bool war_after,bool pending_removed) noexcept {
    char message[1400]{};
    snprintf(message,sizeof(message),
        "{\"event\":\"native_peace_inbound_response_result\",\"family\":\"peace\","
        "\"session_id\":\"%.27s\",\"request_id\":\"%.64s\",\"action_id\":\"peace_offer\","
        "\"actor\":\"%.3s\",\"recipient\":\"FRA\",\"decision_country\":\"FRA\",\"phase\":\"%.6s\","
        "\"date_raw\":%d,\"native_state\":%d,\"outcome\":\"unknown\",\"war_before\":null,\"war_after\":%s,"
        "\"war_state_verified\":false,\"response_verified\":false,\"request_binding_verified\":false,"
        "\"pending_removed\":%s,\"terms_verified\":false,\"peace_context\":null}\n",
        request.session_id,request.request_id,request.original_actor,request.decision,request.date_raw,state,
        war_after?"true":"false",pending_removed?"true":"false");
    line(message);
}

static void execution_peace_response(const ExecutionBinding& binding,
    int32_t state,bool war_after,bool verified,bool pending_removed) noexcept {
    const bool bound=binding.consumed && binding.transport_verified && !binding.invalidated;
    const bool baseline=binding.alliance_before_verified && binding.alliance_before;
    if (binding.inbound_response_request) {
        const auto context=execution_peace_inbound_context(binding.payload,binding.peace_war_id);
        const bool response=verified && bound && baseline && pending_removed && binding.peace_handler_returned;
        const bool accepted=response && state==2 && !war_after;
        const bool rejected=response && state==1 && war_after;
        char message[8000]{};
        snprintf(message,sizeof(message),
            "{\"event\":\"native_peace_inbound_response_result\",\"family\":\"peace\","
            "\"session_id\":\"%.27s\",\"request_id\":\"%.64s\",\"action_id\":\"peace_offer\","
            "\"actor\":\"%.3s\",\"recipient\":\"FRA\",\"decision_country\":\"FRA\",\"phase\":\"%.6s\","
            "\"date_raw\":%d,\"native_state\":%d,\"outcome\":\"%s\",\"war_before\":%s,\"war_after\":%s,"
            "\"war_state_verified\":%s,\"response_verified\":%s,\"request_binding_verified\":%s,"
            "\"execution_verified\":%s,\"pending_removed\":%s,\"terms_verified\":%s,\"peace_context\":%s}\n",
            binding.response_request.session_id,binding.response_request.request_id,
            binding.response_request.original_actor,binding.response_request.decision,binding.response_request.date_raw,
            state,accepted?"accepted":rejected?"rejected":"unknown",baseline?"true":"false",war_after?"true":"false",
            verified && binding.alliance_before_verified?"true":"false",response?"true":"false",bound?"true":"false",
            accepted || rejected?"true":"false",pending_removed?"true":"false",
            accepted && context.white && context.complete?"true":"false",context.json);
        line(message); return;
    }
    const bool settled=verified && bound && baseline && !war_after && (state==0 || state==2);
    const bool rejected=verified && bound && baseline && war_after && state==1;
    const char* outcome=settled?(state==0?"executed":"accepted"):rejected?"rejected":"unknown";
    const auto effects=execution_peace_effects_json(binding.peace_effects_before,binding.peace_request,settled);
    char parameters[700]{},message[24000]{};
    execution_peace_parameters_json(binding.peace_request,parameters);
    snprintf(message,sizeof(message),
        "{\"event\":\"native_peace_execution_result\",\"family\":\"peace\","
        "\"session_id\":\"%lu-%llx\",\"request_id\":\"%.64s\",\"action_id\":\"%.24s\","
        "\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"initiate\",\"date_raw\":%d,%s,"
        "\"native_state\":%d,\"outcome\":\"%s\",\"war_before\":%s,\"war_after\":%s,"
        "\"response_verified\":%s,\"request_binding_verified\":%s,\"execution_verified\":%s,"
        "\"terms_verified\":%s,\"effects\":%s}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
        binding.peace_request.request_id,binding.peace_request.action_id,
        binding.peace_request.actor,binding.peace_request.recipient,binding.peace_request.date_raw,parameters,
        state,outcome,binding.alliance_before?"true":"false",war_after?"true":"false",
        verified?"true":"false",bound?"true":"false",settled?"true":"false",
        settled && (binding.peace_request.white_peace || effects.terms_verified)?"true":"false",effects.json);
    line(message);
}

static void execution_peace_pending_results() noexcept {
    for (auto& binding:execution_bindings) {
        if (!binding.used || !binding.consumed || binding.invalidated || binding.response_queued
            || !binding.inbound_response_request || binding.payload.family!=ActionFamily::peace) continue;
        bool active=true,war_after=true;
        if (!inbound_pending_is_active(binding.pending_proposal_id,binding.pending_generation,active)
            || active || !execution_peace_war_state(binding.payload,war_after)) continue;
        binding.response_queued=true;
        execution_peace_response(binding,static_cast<int32_t>(binding.payload.state34),war_after,true,true);
    }
}

static void execution_peace_tick() noexcept {
    if (!execution_peace_path[0] || thread_changed || !frame_thread
        || frame_thread!=GetCurrentThreadId()) return;
    execution_peace_pending_results();
    char wire[bridge::peace_execution_wire::kMaxWireBytes+1]{};
    DWORD size=0;
    if (!execution_read_request_file(execution_peace_path,wire,sizeof(wire)-1,size)) return;
    PeaceExecutionRequest request{};
    const auto parsed=bridge::peace_execution_wire::parse_request(wire,size,request);
    if (!parsed.ok()) {
        execution_failure("unknown",bridge::peace_execution_wire::parse_error_name(parsed.error)); return;
    }
    const auto fail=[&](const char* reason) noexcept {
        execution_peace_emit_submission(request,false,reason,NativeHeader{});
    };
    if (request.creation_epoch!=observation_creation) { fail("PEACE_EXECUTION_SESSION_MISMATCH"); return; }
    for (unsigned i=0;i<execution_peace_seen_count;++i)
        if (!strcmp(request.request_id,execution_peace_seen[i])) {
            fail("PEACE_EXECUTION_DUPLICATE_REQUEST"); return;
        }
    if (execution_peace_seen_count>=kBindingCapacity) { fail("PEACE_EXECUTION_REQUEST_CAPACITY"); return; }
    std::memcpy(execution_peace_seen[execution_peace_seen_count++],request.request_id,sizeof(request.request_id));
    FILETIME filetime{}; GetSystemTimeAsFileTime(&filetime);
    const uint64_t ticks=(static_cast<uint64_t>(filetime.dwHighDateTime)<<32)|filetime.dwLowDateTime;
    constexpr uint64_t epoch=116444736000000000ull;
    if (ticks<epoch) { fail("PEACE_EXECUTION_CLOCK_UNAVAILABLE"); return; }
    const uint64_t now=(ticks-epoch)/10000u;
    if (request.expiry_epoch_ms<=now) { fail("PEACE_EXECUTION_EXPIRED"); return; }
    if (request.expiry_epoch_ms-now>10000u) { fail("PEACE_EXECUTION_EXPIRY_WINDOW"); return; }
    uintptr_t game=0; int32_t date=0;
    if (!read(base+0x233fe58,game) || !read(game+0x1dd0,date)) {
        fail("PEACE_EXECUTION_GAME_CONTEXT_UNAVAILABLE"); return;
    }
    if (date!=request.date_raw) { fail("PEACE_EXECUTION_DATE_MISMATCH"); return; }
    PeaceProvinceRequest provinces{};
    provinces.count=request.province_count;
    for (unsigned i=0;i<request.province_count;++i) provinces.ids[i]=request.province_ids[i];
    std::memcpy(provinces.beneficiary,request.beneficiary,sizeof(provinces.beneficiary));
    PeacePreparedAction prepared{};
    if (!execution_peace_prepare(prepared,request.actor,request.recipient,request.war_id,
        request.amount_raw,request.selected_provinces?&provinces:nullptr,false,
        !strcmp(request.direction,"demand"))) {
        fail("NATIVE_PEACE_PREFLIGHT_FAILED"); return;
    }
    if (prepared.date!=date) { fail("PEACE_EXECUTION_DATE_CHANGED"); return; }
    if (!prepared.native_validity) { fail("NATIVE_PEACE_VALIDITY_UNAVAILABLE"); return; }
    if (!prepared.common_gate) { fail("NATIVE_PEACE_COMMON_GATE_UNAVAILABLE"); return; }
    if (!prepared.send_gate) { fail("NATIVE_PEACE_SEND_GATE_UNAVAILABLE"); return; }
    if (!prepared.wrapper_rule.available) { fail("NATIVE_PEACE_WRAPPER_GATE_UNAVAILABLE"); return; }
    AlliancePayload payload{};
    bool active=false;
    if (!execution_payload(prepared.source.payload,payload)
        || !execution_peace_war_state(payload,active) || !active) {
        fail("NATIVE_PEACE_WAR_BASELINE_UNVERIFIED"); return;
    }
    const unsigned slot=execution_free_binding();
    if (slot==kInvalidBinding) { fail("LEDGER_CAPACITY_FULL"); return; }
    ExecutionRequest common{};
    std::memcpy(common.request_id,request.request_id,sizeof(request.request_id));
    snprintf(common.session_id,sizeof(common.session_id),"%lu-%llx",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation));
    execution_copy_text(common.action_id,sizeof(common.action_id),request.action_id);
    std::memcpy(common.actor,request.actor,sizeof(request.actor));
    std::memcpy(common.recipient,request.recipient,sizeof(request.recipient));
    std::memcpy(common.phase,"initiate",9); common.date_raw=date;
    execution_bind_sender(common,prepared.source,payload,slot,reinterpret_cast<uintptr_t>(prepared.action));
    ExecutionBinding& binding=execution_bindings[slot];
    binding.peace_request=request;
    // An unavailable observation keeps term verification incomplete; it does
    // not replace the native legality or NPC decision with a bridge veto.
    execution_peace_effects_capture(payload,request,binding.peace_effects_before);
    binding.alliance_before=true; binding.alliance_before_verified=true;
    if (binding.invalidated || !binding.seed.seed_serial) { fail("NATIVE_PEACE_AUTHORITY_SEED_FAILED"); return; }
    void* outgoing=prepared.wrapper; prepared.wrapper=nullptr;
    execution_sender_scope=SenderScope{true,slot};
    const bool accepted=reinterpret_cast<bool (*)(void*,void**)>(base+kDispatcherRva)(
        reinterpret_cast<void*>(prepared.dispatcher),&outgoing);
    execution_sender_scope=SenderScope{};
    if (!accepted || !binding.claim_bound || !binding.transport_verified) {
        execution_ledger.revoke_request(execution_context(),binding.seed,binding.phase);
        execution_mark_invalid(binding);
        fail(accepted?"NATIVE_TRANSPORT_PROOF_MISSING":"NATIVE_DISPATCH_REJECTED");
    }
    if (outgoing) execution_release_constructed(outgoing,nullptr,false);
}

// One explicit NPC offer fixture exercises recipient-FRA pending retention.
// Its native gates are checked before transport, and no FRA authority is made.
static bool execution_peace_inbound_fixture(const char* wire,DWORD size) noexcept {
    constexpr char expected[]="TEST_ONLY ENG_PEACE_FRA_WHITE_PENDING\n";
    if (size!=sizeof(expected)-1 || memcmp(wire,expected,size)) return false;
    static bool consumed=false;
    if (consumed) { execution_failure("peace_inbound_fixture","TEST_ALREADY_CONSUMED"); return true; }
    consumed=true;
    uint64_t actor=0,recipient=0; uintptr_t country=0;
    PeaceWarReferenceList pair{};
    const PeaceWarRegistryEntry* selected=nullptr;
    if (alliance_query_country("ENG",actor) && alliance_query_country("FRA",recipient)
        && peace_query_country_pointer(actor,country)
        && peace_query_pair_references(country,static_cast<unsigned>((recipient>>32)&0xffffu),pair)
        && pair.count==1) {
        selected=peace_query_register_war(pair.references[0]);
    }
    PeacePreparedAction prepared{};
    if (!selected || !execution_peace_prepare(prepared,"ENG","FRA",selected->public_id,-1,nullptr,true)) {
        execution_failure("peace_inbound_fixture","TEST_PEACE_INBOUND_NATIVE_PREFLIGHT_FAILED"); return true;
    }
    void* outgoing=prepared.wrapper; prepared.wrapper=nullptr;
    const bool accepted=reinterpret_cast<bool (*)(void*,void**)>(base+kDispatcherRva)(
        reinterpret_cast<void*>(prepared.dispatcher),&outgoing);
    if (outgoing) execution_release_constructed(outgoing,nullptr,false);
    char message[900]{};
    snprintf(message,sizeof(message),
        "{\"event\":\"native_peace_inbound_fixture_dispatched\",\"private\":true,"
        "\"session_id\":\"%lu-%llx\",\"actor\":\"ENG\",\"recipient\":\"FRA\","
        "\"date_raw\":%d,\"war_id\":\"%s\",\"snapshot_complete\":true,\"native_gates_available\":true,"
        "\"dispatcher_accepted\":%s,\"authority_seed_created\":false}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
        prepared.date,prepared.war_id,accepted?"true":"false");
    line(message); return true;
}
