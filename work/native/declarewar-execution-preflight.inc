// Included inside alliance_execution_detail after the shared dispatcher and
// payload helpers. A fresh candidate is selected for every business request.
static bool execution_declarewar_preflight(const ExecutionRequest& request,
    uint64_t& actor,uint64_t& recipient,int32_t& date,
    unsigned char*& action,void*& wrapper,ProtocolWrapperShape& source,
    AlliancePayload& payload,uintptr_t& dispatcher,bool& constructed,
    const char** failure_reason=nullptr) noexcept {
    constructed=false;
    if (failure_reason) *failure_reason=nullptr;
    uintptr_t game=0; uint64_t player=0;
    if (!read(base+0x233fe58,game) || !read(game+0x1dd0,date)
        || !read(game+0x1e60,player)
        || static_cast<uint32_t>(player&0xffffffu)!=0x524f50u
        || !alliance_query_country("FRA",actor)
        || !alliance_query_country(request.recipient,recipient) || actor==recipient
        || !request.casus_belli[0]) return false;
    static constexpr FactoryActionQueryMethods methods{
        0x293b,0x1c80d90,0x508de0,0x50a0d0,0x100,0x8f440,
        "declare_war",false,0x500550};
    uintptr_t validity=0,common=0,send=0,diplomat=0;
    const uintptr_t table=base+methods.vtable_rva;
    if (!read(table+0x80,validity) || validity!=base+methods.validity_rva
        || !read(table+0x88,common) || common!=base+methods.display_rva
        || !read(table+0x90,send) || send!=base+0x509e60
        || !read(table+0x100,diplomat) || diplomat!=base+0x8f440) return false;
    bool visible=false; unsigned available=0;
    if (!factory_query_visibility(actor,recipient,true,visible,methods) || !visible) return false;
    if (!alliance_query_diplomats(actor,available)) {
        if (failure_reason) *failure_reason="NATIVE_DIPLOMAT_CONTEXT_UNAVAILABLE";
        return false;
    }
    action=static_cast<unsigned char*>(factory_query_create(actor,recipient,true,methods));
    if (!action) return false;
    constructed=true;
    DeclareWarQueryHeader original{}; uintptr_t empty=0;
    if (!declarewar_query_header(action,original)
        || !read(base+0x2340010,empty) || !empty || original.owned!=empty
        || original.actor!=actor || original.mirror!=actor || original.recipient!=recipient
        || original.state34!=0 || original.mode38!=1) return false;
    for (uintptr_t value:original.containers) if (value) return false;
    const bool diplomat_required=reinterpret_cast<bool (*)(void*)>(diplomat)(action);
    if (diplomat_required && !available) {
        if (failure_reason) *failure_reason="NATIVE_DIPLOMAT_UNAVAILABLE";
        return false;
    }
    DeclareWarCandidateSelection selection{};
    selection.casus_belli=request.casus_belli;
    selection.province_id=request.war_goal_province;
    if (strcmp(request.war_goal_beneficiary,"FRA")
        && strcmp(request.war_goal_beneficiary,"---")
        && !alliance_query_country(request.war_goal_beneficiary,selection.beneficiary_handle))
        return false;
    const bool no_cb=!strcmp(request.casus_belli,"no_casus_belli");
    if (no_cb) {
        if (selection.province_id!=-1 || selection.beneficiary_handle) return false;
    } else {
        DeclareWarCandidateQueryResult candidates{};
        declarewar_candidates_query(actor,recipient,candidates,&selection);
        const bool complete=candidates.native_called && candidates.capture_complete
            && candidates.vector_cleanup_ok && candidates.callback_holder_cleanup_ok
            && candidates.callback_holder_empty_after && !candidates.truncated;
        if (!complete || candidates.selection_match_count!=1 || !candidates.selected_owned) {
            declarewar_candidates_release_selected_owned(candidates.selected_owned);
            return false;
        }
        memcpy(action+0x48,&candidates.selected_owned,sizeof(candidates.selected_owned));
        candidates.selected_owned=0; // ownership transferred to native action
    }
    memcpy(action+0x28,&date,sizeof(date));
    memcpy(action+0x2c,&date,sizeof(date));
    DeclareWarParticipantSelection participants_requested{};
    participants_requested.call_allies=request.call_allies;
    participants_requested.promise_land_to=request.promise_land_to;
    participants_requested.co_belligerents=request.co_belligerents;
    DeclareWarParticipantsResult participants{};
    if (!declarewar_participants_apply(action,participants_requested,request.actor,request.recipient,participants)
        || !declarewar_participants_query(action,participants_requested,participants,
            request.request_id,request.actor,request.recipient,date,false)
        || !participants.selection_allowed) return false;
    using Predicate=bool (*)(void*,void*,unsigned char);
    if (!reinterpret_cast<Predicate>(common)(action,nullptr,0)
        || !reinterpret_cast<Predicate>(validity)(action,nullptr,0)
        || !reinterpret_cast<Predicate>(send)(action,nullptr,0)) return false;
    uintptr_t wrap=0;
    if (!read(table+0x40,wrap)
        || (wrap!=base+kWrapperMethodRva
            && !(wrap==reinterpret_cast<uintptr_t>(&lifecycle_wrapper_observe)
                && lifecycle_wrapper_original==reinterpret_cast<LifecycleWrapperMethod>(base+kWrapperMethodRva))))
        return false;
    using Wrapper=void* (*)(void*,void**);
    wrapper=nullptr;
    if (!reinterpret_cast<Wrapper>(wrap)(action,&wrapper) || !wrapper) return false;
    source=protocol_capture(wrapper);
    if (!source.identity || !source.readable || !source.prefix_readable
        || !execution_payload(source.payload,payload)
        || payload.family!=ActionFamily::declare_war
        || payload.actor10!=actor || payload.mirror18!=actor || payload.recipient20!=recipient
        || payload.state34!=0 || payload.variant38!=1 || payload.extra60
        || payload.parameter40 || !payload.war.valid()
        || payload.war.owned_present==no_cb
        || payload.war.container50.count!=request.call_allies.count
        || payload.war.container68.count!=request.promise_land_to.count
        || payload.war.container80.count!=request.co_belligerents.count) return false;
    const bridge::CountryTagList* lists[]={&request.call_allies,&request.promise_land_to,&request.co_belligerents};
    const bridge::declarewar_payload::WarPayloadVector* vectors[]={&payload.war.container50,&payload.war.container68,&payload.war.container80};
    for (unsigned group=0;group<3;++group) for (unsigned i=0;i<lists[group]->count;++i) {
        uint64_t expected=0;
        if (!alliance_query_country(lists[group]->tags[i],expected)
            || vectors[group]->values[i]!=expected) return false;
    }
    uint64_t beneficiary=0;
    if (!no_cb && (payload.war.owned.owned_field18!=static_cast<uint32_t>(request.war_goal_province)
        || !declarewar_candidates_normalize_beneficiary(payload.war.owned.owned_field38,beneficiary)
        || beneficiary!=selection.beneficiary_handle)) return false;
    uintptr_t transport=0;
    return execution_world_dispatcher(dispatcher,transport);
}

// Fixed operator fixtures exercise the same selected native action through
// transport and the direct generic entry, without a ledger seed or TLS grant.
static bool execution_declarewar_authority_test(const char* wire,DWORD size) noexcept {
    constexpr char transport_wire[]="TEST_ONLY FRA_DECLARE_WAR_ENG_WITHOUT_AUTHORITY\n";
    constexpr char direct_wire[]="TEST_ONLY FRA_DECLARE_WAR_ENG_DIRECT_WITHOUT_AUTHORITY\n";
    const bool transport=size==sizeof(transport_wire)-1 && !memcmp(wire,transport_wire,size);
    const bool direct=size==sizeof(direct_wire)-1 && !memcmp(wire,direct_wire,size);
    if (!transport && !direct) return false;
    const unsigned bit=direct?(1u<<31):(1u<<30);
    if (execution_authority_tests_consumed&bit) {
        execution_failure("authority_test","TEST_ALREADY_CONSUMED"); return true;
    }
    execution_authority_tests_consumed|=bit;
    ExecutionRequest request{};
    strcpy(request.action_id,"declare_war"); strcpy(request.actor,"FRA");
    strcpy(request.recipient,"ENG"); strcpy(request.phase,"initiate");
    strcpy(request.casus_belli,"cb_core"); request.war_goal_province=177;
    strcpy(request.war_goal_beneficiary,"FRA");
    unsigned char* action=nullptr; void* wrapper=nullptr;
    ProtocolWrapperShape source{}; AlliancePayload payload{};
    uint64_t actor=0,recipient=0; int32_t date=0; uintptr_t dispatcher=0;
    bool constructed=false;
    if (!execution_declarewar_preflight(request,actor,recipient,date,action,wrapper,
            source,payload,dispatcher,constructed)) {
        execution_release_constructed(wrapper,action,constructed);
        execution_failure("authority_test","TEST_NATIVE_PREFLIGHT_FAILED"); return true;
    }
    void* outgoing=wrapper; bool dispatched=true;
    if (direct) reinterpret_cast<void (*)(void*)>(base+0x4e7c80)(outgoing);
    else dispatched=reinterpret_cast<bool (*)(void*,void**)>(base+kDispatcherRva)(
        reinterpret_cast<void*>(dispatcher),&outgoing);
    if (outgoing) execution_release_constructed(outgoing,nullptr,false);
    execution_release_constructed(nullptr,action,constructed);
    char message[1000];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_alliance_authority_test_dispatched\",\"session_id\":\"%lu-%llx\",\"action_id\":\"declare_war\",\"actor\":\"FRA\",\"recipient\":\"ENG\",\"phase\":\"initiate\",\"date_raw\":%d,\"source_wrapper\":\"0x%llx\",\"source_action\":\"0x%llx\",\"variant38\":1,\"state34\":0,\"casus_belli\":\"cb_core\",\"war_goal_province\":177,\"war_goal_beneficiary\":\"FRA\",\"dispatch_route\":\"%s\",\"dispatcher_accepted\":%s,\"authority_seed_created\":false}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),date,
        static_cast<unsigned long long>(source.address),static_cast<unsigned long long>(source.action),
        direct?"direct_entry":"transport",dispatched?"true":"false");
    line(message); return true;
}
