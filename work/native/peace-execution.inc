// Public Peace execution uses the common native transport/ledger lifecycle.
// This channel never treats a successful preview as a native submission.
using PeaceExecutionRequest=bridge::peace_execution_wire::PeaceExecutionRequest;
struct PeaceExecutionEventBuffer {
    char* text=nullptr;
    size_t capacity=0;
    explicit PeaceExecutionEventBuffer(size_t bytes) noexcept : capacity(bytes) {
        text=static_cast<char*>(HeapAlloc(GetProcessHeap(),0,capacity));
    }
    ~PeaceExecutionEventBuffer() noexcept {
        if (text) HeapFree(GetProcessHeap(),0,text);
    }
    PeaceExecutionEventBuffer(const PeaceExecutionEventBuffer&)=delete;
    PeaceExecutionEventBuffer& operator=(const PeaceExecutionEventBuffer&)=delete;
};
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

static bool execution_peace_subject_csv(
    const char countries[bridge::peace_execution_wire::kMaxSubjectCountries][4],
    std::uint8_t count,char (&output)[64]) noexcept {
    if (count>bridge::peace_execution_wire::kMaxSubjectCountries) return false;
    size_t used=0; output[0]=0;
    for (unsigned i=0;i<count;++i) {
        const int written=snprintf(output+used,sizeof(output)-used,
            "%s%.3s",i?",":"",countries[i]);
        if (written<0 || static_cast<size_t>(written)>=sizeof(output)-used) return false;
        used+=static_cast<size_t>(written);
    }
    return count>0;
}

static void execution_peace_parameters_json(const PeaceExecutionRequest& request,
    char (&output)[4096]) noexcept {
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
    if (request.selected_reparations || request.selected_trade_power || request.selected_concede_defeat || request.selected_annul_treaties
        || request.selected_humiliate_rival || request.selected_show_strength || request.selected_force_religion
        || request.selected_return_core || request.selected_revoke_core
        || request.selected_release_subject || request.selected_transfer_subject
        || request.selected_release_nation || request.selected_force_vassalization
        || request.selected_form_personal_union || request.selected_grant_independence
        || request.selected_full_annexation) {
        const size_t mask_used=strlen(output);
            snprintf(output+mask_used,sizeof(output)-mask_used,",\"term_mask\":\"%.18s\"",
                bridge::peace_execution_wire::effective_term_mask(request));
    }
    if (request.selected_reparations) {
        const size_t used=strlen(output);
        snprintf(output+used,sizeof(output)-used,
            ",\"reparations_payer\":\"%.3s\","
            "\"reparations_claimant\":\"%.3s\"",
            request.demand_direction?request.recipient:request.actor,
            request.demand_direction?request.actor:request.recipient);
    }
    if (request.selected_trade_power) {
        const size_t used=strlen(output);
        snprintf(output+used,sizeof(output)-used,
            ",\"trade_power_source\":\"%.3s\",\"trade_power_beneficiary\":\"%.3s\"",
            request.trade_power_source,request.trade_power_beneficiary);
    }
    if (request.selected_concede_defeat) {
        const size_t used=strlen(output);
        snprintf(output+used,sizeof(output)-used,
            ",\"conceding_country\":\"%.3s\",\"concede_beneficiary\":\"%.3s\"",
            request.demand_direction?request.recipient:request.actor,
            request.demand_direction?request.actor:request.recipient);
    }
    if (request.selected_annul_treaties) {
        char partners[128]{};size_t partner_used=0;
        for (unsigned i=0;i<request.annul_partner_count;++i) {
            const int n=snprintf(partners+partner_used,sizeof(partners)-partner_used,
                "%s\"%.3s\"",i?",":"",request.annul_partners[i]);
            if (n<0 || static_cast<size_t>(n)>=sizeof(partners)-partner_used) return;
            partner_used+=static_cast<size_t>(n);
        }
        const size_t used=strlen(output);
        snprintf(output+used,sizeof(output)-used,",\"annul_country\":\"%.3s\",\"annul_partners\":[%s]",
            request.annul_country,partners);
    }
    if (request.selected_return_core) {
        char ids[192]{}; size_t ids_used=0;
        for (unsigned i=0;i<request.return_core_count;++i) {
            const int n=snprintf(ids+ids_used,sizeof(ids)-ids_used,
                "%s%d",i?",":"",request.return_core_ids[i]);
            if (n<0 || static_cast<size_t>(n)>=sizeof(ids)-ids_used) return;
            ids_used+=static_cast<size_t>(n);
        }
        const size_t used=strlen(output);
        snprintf(output+used,sizeof(output)-used,
            ",\"return_core_ids\":[%s],\"return_core_owner\":\"%.3s\"",
            ids,request.return_core_owner);
    }
    if (request.selected_revoke_core) {
        char ids[192]{}; size_t ids_used=0;
        for (unsigned i=0;i<request.revoke_core_count;++i) {
            const int n=snprintf(ids+ids_used,sizeof(ids)-ids_used,
                "%s%d",i?",":"",request.revoke_core_ids[i]);
            if (n<0 || static_cast<size_t>(n)>=sizeof(ids)-ids_used) return;
            ids_used+=static_cast<size_t>(n);
        }
        const size_t used=strlen(output);
        snprintf(output+used,sizeof(output)-used,
            ",\"revoke_core_ids\":[%s],\"revoke_core_owner\":\"%.3s\"",
            ids,request.revoke_core_owner);
    }
    if (request.selected_release_subject || request.selected_transfer_subject) {
        char release_csv[64]{} ,transfer_csv[64]{};
        const bool release_ok=request.selected_release_subject
            ?execution_peace_subject_csv(request.release_subject_countries,
                request.release_subject_count,release_csv):true;
        const bool transfer_ok=request.selected_transfer_subject
            ?execution_peace_subject_csv(request.transfer_subject_countries,
                request.transfer_subject_count,transfer_csv):true;
        if (!release_ok || !transfer_ok) return;
        if (request.selected_release_subject) {
            const size_t used=strlen(output);
            snprintf(output+used,sizeof(output)-used,
                ",\"release_subject_countries\":\"%s\",\"release_subject_count\":%u",
                release_csv,static_cast<unsigned>(request.release_subject_count));
        }
        if (request.selected_transfer_subject) {
            const size_t used=strlen(output);
            snprintf(output+used,sizeof(output)-used,
                ",\"transfer_subject_countries\":\"%s\",\"transfer_subject_count\":%u",
                transfer_csv,static_cast<unsigned>(request.transfer_subject_count));
        }
    }
    const auto tag=[&](const char* key,const char* value) noexcept {
        const size_t used=strlen(output);
        snprintf(output+used,sizeof(output)-used,",\"%s\":\"%.3s\"",key,value);
    };
    if (request.selected_release_nation) {
        tag("release_nation_country",request.release_nation_country);
        tag("release_nation_source",request.release_nation_source);
    }
    if (request.selected_force_vassalization) {
        tag("vassal_country",request.vassal_country);
        tag("vassal_beneficiary",request.vassal_beneficiary);
    }
    if (request.selected_form_personal_union) {
        tag("union_country",request.union_country);
        tag("union_beneficiary",request.union_beneficiary);
    }
    if (request.selected_grant_independence)
        tag("independence_country",request.independence_country);
    if (request.selected_full_annexation) {
        tag("annex_country",request.annex_country);
        tag("annex_beneficiary",request.annex_beneficiary);
    }
}

static void execution_peace_emit_submission(const PeaceExecutionRequest& request,
    bool submitted,const char* reason,const NativeHeader& header) noexcept {
    char parameters[4096]{},message[6144]{};
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

// Preparation and native gate failures are emitted separately from a
// transport submission.  This keeps submitted=false explicit while retaining
// the exact fresh-prepare stage and bounded native diagnostic that produced
// the rejection.  The event is deliberately side-effect free.
static const char* execution_peace_failure_source(PeaceFailureOrigin origin) noexcept {
    switch (origin) {
    case PeaceFailureOrigin::native_rule: return "native_rule";
    case PeaceFailureOrigin::bridge_policy: return "bridge_policy";
    default: return "runtime_error";
    }
}

static void execution_peace_emit_rejected(const PeaceExecutionRequest& request,
    const PeacePreparedAction* prepared,const char* fallback_reason,
    const char* fallback_source) noexcept {
    const char* reason=prepared && prepared->failure_code[0]
        ?prepared->failure_code:fallback_reason;
    const char* stage=prepared && prepared->failure_source[0]
        ?prepared->failure_source:fallback_source;
    const char* source=prepared
        ?execution_peace_failure_source(prepared->failure_origin):"runtime_error";
    const char* diagnostic=(prepared && prepared->native_diagnostic_hex[0])
        ?prepared->native_diagnostic_hex:"";
    const bool diagnostic_complete=prepared && prepared->native_diagnostic_complete;
    const bool failure_complete=reason && reason[0] && source && source[0]
        && request.request_id[0] && request.action_id[0]
        && request.actor[0] && request.recipient[0] && request.war_id[0]
        && request.date_raw!=0;
    char message[7600]{};
    const int written=snprintf(message,sizeof(message),
        "{\"event\":\"native_peace_execution_rejected\",\"family\":\"peace\","
        "\"session_id\":\"%lu-%llx\",\"request_id\":\"%.64s\","
        "\"action_id\":\"%.24s\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\","
        "\"phase\":\"initiate\",\"direction\":\"%.6s\",\"date_raw\":%d,"
        "\"war_id\":\"%.30s\","
        "\"submitted\":false,\"reason_code\":\"%.127s\","
        "\"reason_stage\":\"%.63s\",\"reason_source\":\"%.20s\","
        "\"native_diagnostic_hex\":\"%.1024s\","
        "\"native_diagnostic_readable\":%s,\"native_diagnostic_truncated\":%s,"
        "\"native_diagnostic_complete\":%s,\"failure_complete\":%s,\"complete\":%s}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),
        static_cast<unsigned long long>(observation_creation),request.request_id,
        request.action_id,request.actor,request.recipient,
        request.demand_direction?"demand":"offer",
        request.date_raw,request.war_id,reason?reason:"NATIVE_PEACE_EXECUTION_REJECTED",
        stage?stage:"unknown",source,diagnostic,
        prepared && prepared->native_diagnostic_readable?"true":"false",
        prepared && prepared->native_diagnostic_truncated?"true":"false",
        diagnostic_complete?"true":"false",failure_complete?"true":"false",
        failure_complete?"true":"false");
    if (written>0 && static_cast<size_t>(written)<sizeof(message)) line(message);
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
        const auto context=execution_peace_inbound_context(binding.payload,binding.peace_war_id,
            nullptr,&binding.peace_request);
        const bool response=verified && bound && baseline && pending_removed && binding.peace_handler_returned;
        const bool accepted=response && state==2 && !war_after;
        const bool rejected=response && state==1 && war_after;
        PeaceEffectSummary effects{};
        if (binding.peace_effects_supported)
            effects=execution_peace_effects_json(binding.peace_effects_before,binding.peace_request,accepted);
        else if (effects.json && effects.capacity>=5u) strcpy(effects.json,"null");
        const bool terms_verified=accepted && context.complete
            && (context.white || (binding.peace_effects_supported && effects.terms_verified));
        PeaceExecutionEventBuffer message(strlen(effects.text())+sizeof(context.json)+2048u);
        if (!message.text) return;
        const int written=snprintf(message.text,message.capacity,
            "{\"event\":\"native_peace_inbound_response_result\",\"family\":\"peace\","
            "\"session_id\":\"%.27s\",\"request_id\":\"%.64s\",\"action_id\":\"peace_offer\","
            "\"actor\":\"%.3s\",\"recipient\":\"FRA\",\"decision_country\":\"FRA\",\"phase\":\"%.6s\","
            "\"date_raw\":%d,\"native_state\":%d,\"outcome\":\"%s\",\"war_before\":%s,\"war_after\":%s,"
            "\"war_state_verified\":%s,\"response_verified\":%s,\"request_binding_verified\":%s,"
            "\"execution_verified\":%s,\"pending_removed\":%s,\"terms_verified\":%s,\"peace_context\":%s,\"effects\":%s}\n",
            binding.response_request.session_id,binding.response_request.request_id,
            binding.response_request.original_actor,binding.response_request.decision,binding.response_request.date_raw,
            state,accepted?"accepted":rejected?"rejected":"unknown",baseline?"true":"false",war_after?"true":"false",
            verified && binding.alliance_before_verified?"true":"false",response?"true":"false",bound?"true":"false",
            accepted || rejected?"true":"false",pending_removed?"true":"false",
            terms_verified?"true":"false",context.json,effects.text());
        if (written>=0 && static_cast<size_t>(written)<message.capacity) line(message.text);
        return;
    }
    const bool settled=verified && bound && baseline && !war_after && (state==0 || state==2);
    const bool rejected=verified && bound && baseline && war_after && state==1;
    const char* outcome=settled?(state==0?"executed":"accepted"):rejected?"rejected":"unknown";
    const auto effects=execution_peace_effects_json(binding.peace_effects_before,binding.peace_request,settled);
    char parameters[4096]{};
    PeaceExecutionEventBuffer message(strlen(effects.text())+sizeof(parameters)+2048u);
    if (!message.text) return;
    execution_peace_parameters_json(binding.peace_request,parameters);
    const int written=snprintf(message.text,message.capacity,
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
        settled && (binding.peace_request.white_peace || effects.terms_verified)?"true":"false",effects.text());
    if (written>=0 && static_cast<size_t>(written)<message.capacity) line(message.text);
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
    PeaceAnnulRequest annul{};
    annul.count=request.annul_partner_count;
    memcpy(annul.country,request.annul_country,4);
    for (unsigned i=0;i<annul.count;++i) memcpy(annul.partners[i],request.annul_partners[i],4);
    PeaceCoreRequest return_core_request{};
    return_core_request.return_core=true;
    return_core_request.selection_requested=request.selected_return_core;
    return_core_request.province_count=request.return_core_count;
    for (unsigned i=0;i<request.return_core_count;++i)
        return_core_request.province_ids[i]=request.return_core_ids[i];
    memcpy(return_core_request.core_owner,request.return_core_owner,
        sizeof(return_core_request.core_owner));
    PeaceCoreRequest revoke_core_request{};
    revoke_core_request.return_core=false;
    revoke_core_request.selection_requested=request.selected_revoke_core;
    revoke_core_request.province_count=request.revoke_core_count;
    for (unsigned i=0;i<request.revoke_core_count;++i)
        revoke_core_request.province_ids[i]=request.revoke_core_ids[i];
    memcpy(revoke_core_request.core_owner,request.revoke_core_owner,
        sizeof(revoke_core_request.core_owner));
    PeaceSubjectRequest release_subject_request{};
    release_subject_request.release_subject=true;
    release_subject_request.selection_requested=request.selected_release_subject;
    release_subject_request.country_count=request.release_subject_count;
    for (unsigned i=0;i<request.release_subject_count;++i)
        memcpy(release_subject_request.countries[i],request.release_subject_countries[i],4);
    if (request.release_subject_count)
        memcpy(release_subject_request.country,request.release_subject_countries[0],4);
    PeaceSubjectRequest transfer_subject_request{};
    transfer_subject_request.release_subject=false;
    transfer_subject_request.selection_requested=request.selected_transfer_subject;
    transfer_subject_request.country_count=request.transfer_subject_count;
    for (unsigned i=0;i<request.transfer_subject_count;++i)
        memcpy(transfer_subject_request.countries[i],request.transfer_subject_countries[i],4);
    if (request.transfer_subject_count)
        memcpy(transfer_subject_request.country,request.transfer_subject_countries[0],4);
    PeaceCountryRequest release_nation_request{},vassal_request{},union_request{},independence_request{};
    release_nation_request.kind=PeaceCountryKind::release_nation;
    vassal_request.kind=PeaceCountryKind::force_vassal;
    union_request.kind=PeaceCountryKind::pu;
    independence_request.kind=PeaceCountryKind::grant_independence;
    release_nation_request.selection_requested=request.selected_release_nation;
    vassal_request.selection_requested=request.selected_force_vassalization;
    union_request.selection_requested=request.selected_form_personal_union;
    independence_request.selection_requested=request.selected_grant_independence;
    memcpy(release_nation_request.country,request.release_nation_country,4);
    memcpy(release_nation_request.source,request.release_nation_source,4);
    memcpy(vassal_request.country,request.vassal_country,4);
    memcpy(union_request.country,request.union_country,4);
    memcpy(independence_request.country,request.independence_country,4);
    PeaceCountryRequestSet country_requests{};
    country_requests.release_nation=request.selected_release_nation?&release_nation_request:nullptr;
    country_requests.force_vassal=request.selected_force_vassalization?&vassal_request:nullptr;
    country_requests.pu=request.selected_form_personal_union?&union_request:nullptr;
    country_requests.grant_independence=request.selected_grant_independence?&independence_request:nullptr;
    country_requests.force_vassal_beneficiary=request.vassal_beneficiary;
    country_requests.pu_beneficiary=request.union_beneficiary;
    PeaceAnnexRequest annex_request{};
    annex_request.selection_requested=request.selected_full_annexation;
    memcpy(annex_request.country,request.annex_country,4);
    memcpy(annex_request.beneficiary,request.annex_beneficiary,4);
    PeacePreparedAction prepared{};
    if (!execution_peace_prepare(prepared,request.actor,request.recipient,request.war_id,
        request.amount_raw,request.selected_provinces?&provinces:nullptr,false,
        !strcmp(request.direction,"demand"),request.selected_reparations,request.selected_trade_power,
        request.selected_trade_power?request.trade_power_source:nullptr,request.selected_concede_defeat,
        request.selected_annul_treaties?&annul:nullptr,request.selected_humiliate_rival,
        request.selected_show_strength,request.selected_force_religion,
        request.selected_return_core?&return_core_request:nullptr,
        request.selected_revoke_core?&revoke_core_request:nullptr,
        request.selected_release_subject?&release_subject_request:nullptr,
        request.selected_transfer_subject?&transfer_subject_request:nullptr,
        country_requests.any()?&country_requests:nullptr,
        request.selected_full_annexation?&annex_request:nullptr)) {
        execution_peace_emit_rejected(request,&prepared,
            "NATIVE_PEACE_PREFLIGHT_FAILED","preflight"); return;
    }
    if (prepared.date!=date) {
        prepared.mark_failure("PEACE_EXECUTION_DATE_CHANGED","date_check");
        execution_peace_emit_rejected(request,&prepared,
            "PEACE_EXECUTION_DATE_CHANGED","date_check"); return;
    }
    if (!prepared.native_validity) {
        prepared.mark_failure("NATIVE_PEACE_VALIDITY_UNAVAILABLE","native_validity_gate",
            PeaceFailureOrigin::native_rule);
        execution_peace_emit_rejected(request,&prepared,
            "NATIVE_PEACE_VALIDITY_UNAVAILABLE","native_validity_gate"); return;
    }
    if (!prepared.common_gate) {
        prepared.mark_failure("NATIVE_PEACE_COMMON_GATE_UNAVAILABLE","native_common_gate",
            PeaceFailureOrigin::native_rule);
        execution_peace_emit_rejected(request,&prepared,
            "NATIVE_PEACE_COMMON_GATE_UNAVAILABLE","native_common_gate"); return;
    }
    if (!prepared.send_gate) {
        prepared.mark_failure("NATIVE_PEACE_SEND_GATE_UNAVAILABLE","native_send_gate",
            PeaceFailureOrigin::native_rule);
        execution_peace_emit_rejected(request,&prepared,
            "NATIVE_PEACE_SEND_GATE_UNAVAILABLE","native_send_gate"); return;
    }
    if (!prepared.wrapper_rule.available) {
        prepared.mark_failure("NATIVE_PEACE_WRAPPER_GATE_UNAVAILABLE","native_wrapper_gate",
            PeaceFailureOrigin::native_rule);
        execution_peace_emit_rejected(request,&prepared,
            "NATIVE_PEACE_WRAPPER_GATE_UNAVAILABLE","native_wrapper_gate"); return;
    }
    AlliancePayload payload{};
    bool active=false;
    if (!execution_payload(prepared.source.payload,payload)
        || !execution_peace_war_state(payload,active) || !active) {
        prepared.mark_failure("NATIVE_PEACE_WAR_BASELINE_UNVERIFIED","war_baseline");
        execution_peace_emit_rejected(request,&prepared,
            "NATIVE_PEACE_WAR_BASELINE_UNVERIFIED","war_baseline"); return;
    }
    const unsigned slot=execution_free_binding();
    if (slot==kInvalidBinding) {
        prepared.mark_failure("LEDGER_CAPACITY_FULL","execution_ledger",
            PeaceFailureOrigin::bridge_policy);
        execution_peace_emit_rejected(request,&prepared,
            "LEDGER_CAPACITY_FULL","execution_ledger"); return;
    }
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
    if (binding.invalidated || !binding.seed.seed_serial) {
        prepared.mark_failure("NATIVE_PEACE_AUTHORITY_SEED_FAILED","authority_seed",
            PeaceFailureOrigin::bridge_policy);
        execution_peace_emit_rejected(request,&prepared,
            "NATIVE_PEACE_AUTHORITY_SEED_FAILED","authority_seed"); return;
    }
    void* outgoing=prepared.wrapper; prepared.wrapper=nullptr;
    execution_sender_scope=SenderScope{true,slot};
    const bool accepted=reinterpret_cast<bool (*)(void*,void**)>(base+kDispatcherRva)(
        reinterpret_cast<void*>(prepared.dispatcher),&outgoing);
    execution_sender_scope=SenderScope{};
    if (!accepted || !binding.claim_bound || !binding.transport_verified) {
        execution_ledger.revoke_request(execution_context(),binding.seed,binding.phase);
        execution_mark_invalid(binding);
        prepared.mark_failure(accepted?"NATIVE_TRANSPORT_PROOF_MISSING":"NATIVE_DISPATCH_REJECTED",
            accepted?"transport_proof":"dispatcher",PeaceFailureOrigin::bridge_policy);
        execution_peace_emit_rejected(request,&prepared,
            accepted?"NATIVE_TRANSPORT_PROOF_MISSING":"NATIVE_DISPATCH_REJECTED",
            accepted?"transport_proof":"dispatcher");
    }
    if (outgoing) execution_release_constructed(outgoing,nullptr,false);
}

// One explicit NPC offer fixture exercises recipient-FRA pending retention.
// Its native gates are checked before transport, and no FRA authority is made.
static bool execution_peace_country_inbound_fixture(const char* wire,DWORD size) noexcept {
    struct Scenario { const char* name; const char* actor; unsigned kind; };
    static constexpr Scenario scenarios[]={
        {"ENG_PEACE_FRA_RELEASE_FLY","ENG",0},
        {"ENG_PEACE_FRA_ANNEX_TYR","ENG",1},
        {"ENG_PEACE_FRA_COUNTRY_COMBINED","ENG",2},
        {"LEI_PEACE_FRA_FORCE_VASSAL","LEI",3},
        {"LEI_PEACE_FRA_PERSONAL_UNION","LEI",4},
        {"ENG_PEACE_FRA_INDEPENDENCE","ENG",5},
    };
    unsigned selected=6,slot=2;
    for (unsigned index=0;index<6;++index) for (unsigned choice=0;choice<2;++choice) {
        char expected[128]{};
        const int length=snprintf(expected,sizeof(expected),"TEST_ONLY %s_PENDING_%u\n",
            scenarios[index].name,choice+1u);
        if (length>0 && size==static_cast<DWORD>(length) && !memcmp(wire,expected,size)) {
            selected=index; slot=choice;
        }
    }
    if (selected==6) return false;
    static bool consumed[6][2]{};
    if (consumed[selected][slot]) {
        execution_failure("peace_country_inbound_fixture","TEST_ALREADY_CONSUMED"); return true;
    }
    const auto& scenario=scenarios[selected];
    uint64_t actor=0,recipient=0; uintptr_t country=0;
    PeaceWarReferenceList pair{};
    const PeaceWarRegistryEntry* war=nullptr;
    if (alliance_query_country(scenario.actor,actor) && alliance_query_country("FRA",recipient)
        && peace_query_country_pointer(actor,country)
        && peace_query_pair_references(country,static_cast<unsigned>((recipient>>32)&0xffffu),pair)
        && pair.count==1) war=peace_query_register_war(pair.references[0]);
    PeaceCountryRequest release{},vassal{},personal_union{},independence{};
    release.kind=PeaceCountryKind::release_nation;
    release.selection_requested=true;
    memcpy(release.country,"FLY",4); memcpy(release.source,"ENG",4);
    vassal.kind=PeaceCountryKind::force_vassal;
    vassal.selection_requested=true; memcpy(vassal.country,"LEI",4);
    personal_union.kind=PeaceCountryKind::pu;
    personal_union.selection_requested=true; memcpy(personal_union.country,"LEI",4);
    independence.kind=PeaceCountryKind::grant_independence;
    independence.selection_requested=true; memcpy(independence.country,"ENG",4);
    PeaceCountryRequestSet requests{};
    requests.release_nation=scenario.kind==0 || scenario.kind==2?&release:nullptr;
    requests.force_vassal=scenario.kind==3?&vassal:nullptr;
    requests.pu=scenario.kind==4?&personal_union:nullptr;
    requests.grant_independence=scenario.kind==5?&independence:nullptr;
    requests.force_vassal_beneficiary="FRA"; requests.pu_beneficiary="FRA";
    PeaceAnnexRequest annex{};
    annex.selection_requested=true;
    memcpy(annex.country,"TYR",4); memcpy(annex.beneficiary,"FRA",4);
    const bool annex_selected=scenario.kind==1 || scenario.kind==2;
    PeacePreparedAction prepared{};
    if (!war || !execution_peace_prepare(prepared,scenario.actor,"FRA",war->public_id,
        -1,nullptr,true,false,false,false,nullptr,false,nullptr,false,false,false,
        nullptr,nullptr,nullptr,nullptr,requests.any()?&requests:nullptr,
        annex_selected?&annex:nullptr)) {
        execution_failure("peace_country_inbound_fixture","TEST_PEACE_INBOUND_NATIVE_PREFLIGHT_FAILED");
        return true;
    }
    void* outgoing=prepared.wrapper; prepared.wrapper=nullptr;
    const bool accepted=reinterpret_cast<bool (*)(void*,void**)>(base+kDispatcherRva)(
        reinterpret_cast<void*>(prepared.dispatcher),&outgoing);
    if (outgoing) execution_release_constructed(outgoing,nullptr,false);
    if (accepted) consumed[selected][slot]=true;
    char message[1300]{};
    snprintf(message,sizeof(message),
        "{\"event\":\"native_peace_inbound_fixture_dispatched\",\"private\":true,"
        "\"session_id\":\"%lu-%llx\",\"actor\":\"%.3s\",\"recipient\":\"FRA\","
        "\"fixture_index\":%u,\"fixture_kind\":\"%s\",\"date_raw\":%d,\"war_id\":\"%s\","
        "\"snapshot_complete\":true,\"native_gates_available\":true,"
        "\"dispatcher_accepted\":%s,\"slot_consumed\":%s,\"direction\":\"offer\"}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
        scenario.actor,slot+1u,scenario.name,prepared.date,prepared.war_id,
        accepted?"true":"false",accepted?"true":"false");
    line(message); return true;
}

static bool execution_peace_inbound_fixture(const char* wire,DWORD size) noexcept {
    if (execution_peace_country_inbound_fixture(wire,size)) return true;
    // Two explicit operator proposals in one process allow reject then accept
    // without loading a result save. Each slot is spent only at dispatch.
    constexpr char subject_first[]="TEST_ONLY ENG_PEACE_FRA_SUBJECT_RELEASE_PENDING_1\n";
    constexpr char subject_second[]="TEST_ONLY ENG_PEACE_FRA_SUBJECT_RELEASE_PENDING_2\n";
    const int subject_slot=size==sizeof(subject_first)-1 && !memcmp(wire,subject_first,size)?0:
        size==sizeof(subject_second)-1 && !memcmp(wire,subject_second,size)?1:-1;
    if (subject_slot>=0) {
        static bool subject_consumed[2]{};
        if (subject_consumed[subject_slot]) {
            execution_failure("peace_inbound_fixture","TEST_ALREADY_CONSUMED"); return true;
        }
        uint64_t actor=0,recipient=0; uintptr_t country=0;
        PeaceWarReferenceList pair{};
        const PeaceWarRegistryEntry* selected=nullptr;
        if (alliance_query_country("ENG",actor) && alliance_query_country("FRA",recipient)
            && peace_query_country_pointer(actor,country)
            && peace_query_pair_references(country,static_cast<unsigned>((recipient>>32)&0xffffu),pair)
            && pair.count==1) selected=peace_query_register_war(pair.references[0]);
        PeaceSubjectRequest release{};
        release.release_subject=true; release.selection_requested=true;
        release.country_count=1; memcpy(release.country,"TYR",4);
        memcpy(release.countries[0],"TYR",4);
        PeacePreparedAction prepared{};
        if (!selected || !execution_peace_prepare(prepared,"ENG","FRA",selected->public_id,
            1000,nullptr,true,false,true,false,nullptr,false,nullptr,false,false,false,
            nullptr,nullptr,&release,nullptr)) {
            execution_failure("peace_inbound_fixture","TEST_PEACE_INBOUND_NATIVE_PREFLIGHT_FAILED"); return true;
        }
        void* outgoing=prepared.wrapper; prepared.wrapper=nullptr;
        const bool accepted=reinterpret_cast<bool (*)(void*,void**)>(base+kDispatcherRva)(
            reinterpret_cast<void*>(prepared.dispatcher),&outgoing);
        if (outgoing) execution_release_constructed(outgoing,nullptr,false);
        if (accepted) subject_consumed[subject_slot]=true;
        char message[1500]{};
        snprintf(message,sizeof(message),
            "{\"event\":\"native_peace_inbound_fixture_dispatched\",\"private\":true,"
            "\"session_id\":\"%lu-%llx\",\"actor\":\"ENG\",\"recipient\":\"FRA\","
            "\"fixture_index\":%d,\"fixture_kind\":\"release_subject\",\"date_raw\":%d,\"war_id\":\"%s\","
            "\"snapshot_complete\":true,\"native_gates_available\":true,"
            "\"dispatcher_accepted\":%s,\"slot_consumed\":%s,"
            "\"money_requested\":true,\"amount_raw\":1000,\"reparations_requested\":true,"
            "\"release_subject_requested\":true,\"release_subject_countries\":[\"TYR\"],"
            "\"direction\":\"offer\"}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),
            static_cast<unsigned long long>(observation_creation),subject_slot+1,
            prepared.date,prepared.war_id,accepted?"true":"false",accepted?"true":"false");
        line(message); return true;
    }
    constexpr char subject_combined_first[]="TEST_ONLY ENG_PEACE_FRA_SUBJECT_COMBINED_PENDING_1\n";
    constexpr char subject_combined_second[]="TEST_ONLY ENG_PEACE_FRA_SUBJECT_COMBINED_PENDING_2\n";
    const int subject_combined_slot=
        size==sizeof(subject_combined_first)-1 && !memcmp(wire,subject_combined_first,size)?0:
        size==sizeof(subject_combined_second)-1 && !memcmp(wire,subject_combined_second,size)?1:-1;
    if (subject_combined_slot>=0) {
        static bool subject_combined_consumed[2]{};
        if (subject_combined_consumed[subject_combined_slot]) {
            execution_failure("peace_inbound_fixture","TEST_ALREADY_CONSUMED"); return true;
        }
        uint64_t actor=0,recipient=0; uintptr_t country=0;
        PeaceWarReferenceList pair{};
        const PeaceWarRegistryEntry* selected=nullptr;
        if (alliance_query_country("ENG",actor) && alliance_query_country("FRA",recipient)
            && peace_query_country_pointer(actor,country)
            && peace_query_pair_references(country,static_cast<unsigned>((recipient>>32)&0xffffu),pair)
            && pair.count==1) selected=peace_query_register_war(pair.references[0]);
        PeaceSubjectRequest release{},transfer{};
        release.release_subject=true; release.selection_requested=true; release.country_count=1;
        memcpy(release.country,"TYR",4); memcpy(release.countries[0],"TYR",4);
        transfer.release_subject=false; transfer.selection_requested=true; transfer.country_count=1;
        memcpy(transfer.country,"LEI",4); memcpy(transfer.countries[0],"LEI",4);
        PeacePreparedAction prepared{};
        if (!selected || !execution_peace_prepare(prepared,"ENG","FRA",selected->public_id,
            1000,nullptr,true,false,true,false,nullptr,false,nullptr,false,false,false,
            nullptr,nullptr,&release,&transfer)) {
            execution_failure("peace_inbound_fixture","TEST_PEACE_INBOUND_NATIVE_PREFLIGHT_FAILED"); return true;
        }
        void* outgoing=prepared.wrapper; prepared.wrapper=nullptr;
        const bool accepted=reinterpret_cast<bool (*)(void*,void**)>(base+kDispatcherRva)(
            reinterpret_cast<void*>(prepared.dispatcher),&outgoing);
        if (outgoing) execution_release_constructed(outgoing,nullptr,false);
        if (accepted) subject_combined_consumed[subject_combined_slot]=true;
        char message[1600]{};
        snprintf(message,sizeof(message),
            "{\"event\":\"native_peace_inbound_fixture_dispatched\",\"private\":true,"
            "\"session_id\":\"%lu-%llx\",\"actor\":\"ENG\",\"recipient\":\"FRA\","
            "\"fixture_index\":%d,\"fixture_kind\":\"combined_subject\",\"date_raw\":%d,\"war_id\":\"%s\","
            "\"snapshot_complete\":true,\"native_gates_available\":true,"
            "\"dispatcher_accepted\":%s,\"slot_consumed\":%s,"
            "\"money_requested\":true,\"amount_raw\":1000,\"reparations_requested\":true,"
            "\"release_subject_requested\":true,\"release_subject_countries\":[\"TYR\"],"
            "\"transfer_subject_requested\":true,\"transfer_subject_countries\":[\"LEI\"],"
            "\"direction\":\"offer\"}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),
            static_cast<unsigned long long>(observation_creation),subject_combined_slot+1,
            prepared.date,prepared.war_id,accepted?"true":"false",accepted?"true":"false");
        line(message); return true;
    }
    constexpr char core_first[]="TEST_ONLY ENG_PEACE_FRA_CORE_COMBINED_PENDING_1\n";
    constexpr char core_second[]="TEST_ONLY ENG_PEACE_FRA_CORE_COMBINED_PENDING_2\n";
    const int core_slot=size==sizeof(core_first)-1 && !memcmp(wire,core_first,size)?0:
        size==sizeof(core_second)-1 && !memcmp(wire,core_second,size)?1:-1;
    if (core_slot>=0) {
        static bool core_consumed[2]{};
        if (core_consumed[core_slot]) {
            execution_failure("peace_inbound_fixture","TEST_ALREADY_CONSUMED"); return true;
        }
        uint64_t actor=0,recipient=0; uintptr_t country=0;
        PeaceWarReferenceList pair{};
        const PeaceWarRegistryEntry* selected=nullptr;
        if (alliance_query_country("ENG",actor) && alliance_query_country("FRA",recipient)
            && peace_query_country_pointer(actor,country)
            && peace_query_pair_references(country,static_cast<unsigned>((recipient>>32)&0xffffu),pair)
            && pair.count==1) selected=peace_query_register_war(pair.references[0]);
        PeaceCoreRequest returning{},revoking{};
        if (!peace_core_parse_request("173","AMG",returning)
            || !peace_core_parse_request("175","ENG",revoking)) {
            execution_failure("peace_inbound_fixture","TEST_CORE_PARAMETERS_INVALID"); return true;
        }
        returning.return_core=true;
        PeacePreparedAction prepared{};
        if (!selected || !execution_peace_prepare(prepared,"ENG","FRA",selected->public_id,
            1000,nullptr,true,false,true,false,nullptr,false,nullptr,false,false,false,
            &returning,&revoking)) {
            execution_failure("peace_inbound_fixture","TEST_PEACE_INBOUND_NATIVE_PREFLIGHT_FAILED"); return true;
        }
        core_consumed[core_slot]=true;
        void* outgoing=prepared.wrapper; prepared.wrapper=nullptr;
        const bool accepted=reinterpret_cast<bool (*)(void*,void**)>(base+kDispatcherRva)(
            reinterpret_cast<void*>(prepared.dispatcher),&outgoing);
        if (outgoing) execution_release_constructed(outgoing,nullptr,false);
        char message[1300]{};
        snprintf(message,sizeof(message),
            "{\"event\":\"native_peace_inbound_fixture_dispatched\",\"private\":true,"
            "\"session_id\":\"%lu-%llx\",\"actor\":\"ENG\",\"recipient\":\"FRA\","
            "\"fixture_index\":%d,\"date_raw\":%d,\"war_id\":\"%s\","
            "\"snapshot_complete\":true,\"native_gates_available\":true,"
            "\"dispatcher_accepted\":%s,\"authority_seed_created\":false,"
            "\"money_requested\":true,\"amount_raw\":1000,\"reparations_requested\":true,"
            "\"return_core_requested\":true,\"revoke_core_requested\":true,"
            "\"return_core_ids\":[173],\"return_core_owner\":\"AMG\","
            "\"revoke_core_ids\":[175],\"revoke_core_owner\":\"ENG\",\"direction\":\"offer\"}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),
            static_cast<unsigned long long>(observation_creation),core_slot+1,
            prepared.date,prepared.war_id,accepted?"true":"false");
        line(message); return true;
    }
    constexpr char expected[]="TEST_ONLY ENG_PEACE_FRA_WHITE_PENDING\n";
    constexpr char bur_white_wire[]="TEST_ONLY BUR_PEACE_FRA_WHITE_PENDING\n";
    const bool bur_white=size==sizeof(bur_white_wire)-1 && !memcmp(wire,bur_white_wire,size);
    constexpr char reparations_wire[]="TEST_ONLY ENG_PEACE_FRA_REPARATIONS_PENDING\n";
    constexpr char trade_power_wire[]="TEST_ONLY ENG_PEACE_FRA_TRADE_POWER_PENDING\n";
    constexpr char concede_wire[]="TEST_ONLY ENG_PEACE_FRA_CONCEDE_DEFEAT_PENDING\n";
    const bool concede=size==sizeof(concede_wire)-1 && !memcmp(wire,concede_wire,size);
    constexpr char humiliate_wire[]="TEST_ONLY ENG_PEACE_FRA_HUMILIATE_RIVAL_PENDING\n";
    constexpr char strength_wire[]="TEST_ONLY ENG_PEACE_FRA_SHOW_STRENGTH_PENDING\n";
    constexpr char strength_offer_wire[]="TEST_ONLY ENG_PEACE_FRA_SHOW_STRENGTH_OFFER_PENDING\n";
    constexpr char religion_wire[]="TEST_ONLY ENG_PEACE_FRA_FORCE_RELIGION_PENDING\n";
    constexpr char religion_small_offer_wire[]="TEST_ONLY LEI_PEACE_FRA_FORCE_RELIGION_OFFER_PENDING\n";
    const bool humiliate=size==sizeof(humiliate_wire)-1 && !memcmp(wire,humiliate_wire,size);
    const bool strength_offer=size==sizeof(strength_offer_wire)-1
        && !memcmp(wire,strength_offer_wire,size);
    const bool strength=strength_offer
        || (size==sizeof(strength_wire)-1 && !memcmp(wire,strength_wire,size));
    const bool religion_small_offer=size==sizeof(religion_small_offer_wire)-1
        && !memcmp(wire,religion_small_offer_wire,size);
    const bool religion=religion_small_offer
        || (size==sizeof(religion_wire)-1 && !memcmp(wire,religion_wire,size));
    PeaceAnnulRequest annul_request{};
    char annul_country[4]{},annul_csv[64]{};int annul_used=0;
    const bool annul=sscanf(wire,"TEST_ONLY ENG_PEACE_FRA_ANNUL_TREATIES_PENDING %3s %63s%n",
        annul_country,annul_csv,&annul_used)==2 && annul_used>0
        && static_cast<DWORD>(annul_used)+1==size && wire[annul_used]=='\n'
        && peace_annul_parse_request(annul_country,annul_csv,annul_request) && annul_request.count;

    const bool white=bur_white || (size==sizeof(expected)-1 && !memcmp(wire,expected,size));
    const bool reparations=size==sizeof(reparations_wire)-1 && !memcmp(wire,reparations_wire,size);
    char offered_source[4]{}; int consumed_bytes=0;
    bool trade_power_offer=sscanf(wire,
        "TEST_ONLY ENG_PEACE_FRA_TRADE_POWER_OFFER_PENDING %3s%n",offered_source,&consumed_bytes)==1
        && consumed_bytes>0 && static_cast<DWORD>(consumed_bytes)+1==size
        && wire[consumed_bytes]=='\n' && strlen(offered_source)==3;
    for (const char* p=offered_source;trade_power_offer && *p;++p)
        trade_power_offer=(*p>='A' && *p<='Z') || (*p>='0' && *p<='9');
    const bool trade_power=trade_power_offer
        || (size==sizeof(trade_power_wire)-1 && !memcmp(wire,trade_power_wire,size));
    const bool offer_direction=trade_power_offer || strength_offer || religion_small_offer;
    if (!white && !reparations && !trade_power && !concede && !annul
        && !humiliate && !strength && !religion) return false;
    static bool consumed=false;
    if (consumed) { execution_failure("peace_inbound_fixture","TEST_ALREADY_CONSUMED"); return true; }
    consumed=true;
    uint64_t actor=0,recipient=0; uintptr_t country=0;
    const char* proposer=bur_white?"BUR":religion_small_offer?"LEI":"ENG";
    PeaceWarReferenceList pair{};
    const PeaceWarRegistryEntry* selected=nullptr;
    if (alliance_query_country(proposer,actor) && alliance_query_country("FRA",recipient)
        && peace_query_country_pointer(actor,country)
        && peace_query_pair_references(country,static_cast<unsigned>((recipient>>32)&0xffffu),pair)
        && pair.count==1) {
        selected=peace_query_register_war(pair.references[0]);
    }
    PeacePreparedAction prepared{};
    if (!selected || !execution_peace_prepare(prepared,proposer,"FRA",selected->public_id,
        -1,nullptr,true,!offer_direction,reparations,trade_power,
        trade_power_offer?offered_source:nullptr,concede,annul?&annul_request:nullptr,
        humiliate,strength,religion)) {
        execution_failure("peace_inbound_fixture","TEST_PEACE_INBOUND_NATIVE_PREFLIGHT_FAILED"); return true;
    }
    void* outgoing=prepared.wrapper; prepared.wrapper=nullptr;
    const bool accepted=reinterpret_cast<bool (*)(void*,void**)>(base+kDispatcherRva)(
        reinterpret_cast<void*>(prepared.dispatcher),&outgoing);
    if (outgoing) execution_release_constructed(outgoing,nullptr,false);
    char message[1300]{};
    snprintf(message,sizeof(message),
        "{\"event\":\"native_peace_inbound_fixture_dispatched\",\"private\":true,"
        "\"session_id\":\"%lu-%llx\",\"actor\":\"%.3s\",\"recipient\":\"FRA\","
        "\"date_raw\":%d,\"war_id\":\"%s\",\"snapshot_complete\":true,\"native_gates_available\":true,"
        "\"dispatcher_accepted\":%s,\"authority_seed_created\":false,\"reparations_requested\":%s,\"trade_power_requested\":%s,\"concede_defeat_requested\":%s,\"annul_treaties_requested\":%s,"
        "\"humiliate_rival_requested\":%s,\"show_strength_requested\":%s,\"force_religion_requested\":%s,"
        "\"direction\":\"%s\",\"trade_power_source\":\"%.3s\"}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
        proposer,prepared.date,prepared.war_id,accepted?"true":"false",reparations?"true":"false",trade_power?"true":"false",concede?"true":"false",annul?"true":"false",
        humiliate?"true":"false",strength?"true":"false",religion?"true":"false",
        offer_direction?"offer":"demand",trade_power_offer?offered_source:trade_power?"FRA":"-");
    line(message); return true;
}
