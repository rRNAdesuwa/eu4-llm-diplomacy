enum class PeaceFailureOrigin : unsigned char {
    runtime_error,
    native_rule,
    bridge_policy,
};

// Fresh native offer construction shared by execution preparation and the
// operator's ungranted-entry fixtures. Placement objects never escape; the
// native wrapper owns its own clone of the completed action.
struct PeacePreparedAction {
    alignas(16) unsigned char offer[0x1c0]{};
    alignas(16) unsigned char action[0x210]{};
    bool offer_constructed=false,action_constructed=false;
    bool native_validity=false,common_gate=false,send_gate=false;
    // A failed fresh preparation is still a bound, inspectable native result.
    // Keep the stage separate from the stable code so callers can distinguish
    // malformed protocol/object state from a native legality decision.
    char failure_code[128]{};
    char failure_source[64]{};
    char native_diagnostic_hex[1025]{};
    bool native_diagnostic_readable=false;
    bool native_diagnostic_truncated=false;
    bool native_diagnostic_complete=false;
    bool failure_complete=false;
    PeaceFailureOrigin failure_origin=PeaceFailureOrigin::runtime_error;
    PeaceWrapperRuleCapture wrapper_rule{};
    uint64_t actor=0,recipient=0;
    int32_t date=0;
    uintptr_t dispatcher=0;
    char war_id[30]{};
    ProtocolWrapperShape source{};
    void* wrapper=nullptr;

    void mark_failure(const char* code,const char* source,
        PeaceFailureOrigin origin=PeaceFailureOrigin::runtime_error) noexcept {
        failure_code[0]=failure_source[0]=0;
        if (code && code[0]) snprintf(failure_code,sizeof(failure_code),"%.127s",code);
        if (source && source[0]) snprintf(failure_source,sizeof(failure_source),"%.63s",source);
        failure_origin=origin;
        failure_complete=failure_code[0]!=0 && failure_source[0]!=0;
    }
    void copy_diagnostic(const NativeShortString& text) noexcept {
        declarewar_query_hex(text,native_diagnostic_hex,native_diagnostic_readable,
            native_diagnostic_truncated);
        native_diagnostic_complete=native_diagnostic_readable
            && !native_diagnostic_truncated;
    }

    PeacePreparedAction() noexcept=default;
    PeacePreparedAction(const PeacePreparedAction&)=delete;
    PeacePreparedAction& operator=(const PeacePreparedAction&)=delete;
    ~PeacePreparedAction() noexcept {
        if (wrapper) execution_release_constructed(wrapper,nullptr,false);
        if (action_constructed)
            reinterpret_cast<void* (*)(void*,unsigned)>(base+0x598b90)(action,0);
        if (offer_constructed) reinterpret_cast<void (*)(void*)>(base+0x976030)(offer);
    }
};

static bool execution_peace_prepare(PeacePreparedAction& prepared,
    const char* actor_tag,const char* recipient_tag,const char* war_id,
    int32_t amount_raw,const PeaceProvinceRequest* province_request,
    bool require_available,bool demand=true,bool reparations_requested=false,
    bool trade_power_requested=false,const char* trade_source_tag=nullptr,
    bool concede_requested=false,const PeaceAnnulRequest* annul_request=nullptr,
    bool humiliate_requested=false,bool strength_requested=false,
    bool religion_requested=false,const PeaceCoreRequest* return_core_request=nullptr,
    const PeaceCoreRequest* revoke_core_request=nullptr,
    const PeaceSubjectRequest* release_subject_request=nullptr,
    const PeaceSubjectRequest* transfer_subject_request=nullptr,
    const PeaceCountryRequestSet* country_requests=nullptr,
    const PeaceAnnexRequest* annex_request=nullptr) noexcept {
    auto fail=[&](const char* code,const char* source) noexcept -> bool {
        prepared.mark_failure(code,source); return false;
    };
    auto fail_native=[&](const char* code,const char* source) noexcept -> bool {
        prepared.mark_failure(code,source,PeaceFailureOrigin::native_rule); return false;
    };
    auto fail_reason=[&](const char* code,const char* source,
        const char* fallback) noexcept -> bool {
        prepared.mark_failure(code && code[0]?code:fallback,source,
            PeaceFailureOrigin::native_rule); return false;
    };
    auto fail_base=[&](const PeaceBaseTermQueryData& data,const char* source,
        const char* fallback) noexcept -> bool {
        if (data.rule_diagnostic_hex[0]) {
            std::memcpy(prepared.native_diagnostic_hex,data.rule_diagnostic_hex,
                sizeof(prepared.native_diagnostic_hex));
            prepared.native_diagnostic_hex[sizeof(prepared.native_diagnostic_hex)-1]=0;
        }
        prepared.native_diagnostic_readable=data.rule_diagnostic_readable;
        prepared.native_diagnostic_truncated=data.rule_diagnostic_truncated;
        prepared.native_diagnostic_complete=prepared.native_diagnostic_readable
            && !prepared.native_diagnostic_truncated;
        return fail_reason(data.reason_code,source,fallback);
    };
    const PeaceCountryRequestSet empty_country_requests{};
    PeaceCountryQuerySet countries(country_requests?*country_requests:empty_country_requests);
    PeaceAnnexQueryData annex(annex_request!=nullptr);
    if (!countries.valid() || !annex.valid())
        return fail("NATIVE_PEACE_REQUEST_STORAGE_UNAVAILABLE","request_storage");
    PeaceSpecialQueryData special(humiliate_requested,strength_requested,religion_requested);
    const bool special_requested=special.any();
    const bool annul_requested=annul_request!=nullptr;
    uintptr_t game=0,actor_country=0,recipient_country=0;
    uint64_t player=0;
    if (!read(base+0x233fe58,game) || !read(game+0x1dd0,prepared.date)
        || !read(game+0x1e60,player) || (player&0xffffffu)!=0x524f50u
        || !alliance_query_country(actor_tag,prepared.actor)
        || !alliance_query_country(recipient_tag,prepared.recipient)
        || prepared.actor==prepared.recipient
        || !peace_query_country_pointer(prepared.actor,actor_country)
        || !peace_query_country_pointer(prepared.recipient,recipient_country))
        return fail("NATIVE_PEACE_GAME_OR_COUNTRY_CONTEXT_UNAVAILABLE","game_context");
    const PeaceWarRegistryEntry* selected=nullptr;
    for (unsigned i=0;i<peace_war_registry_size;++i)
        if (!strcmp(peace_war_registry[i].public_id,war_id)) selected=&peace_war_registry[i];
    PeaceWarReferenceList left{},right{};
    if (!selected || !peace_query_pair_references(actor_country,
            static_cast<unsigned>((prepared.recipient>>32)&0xffffu),left)
        || !peace_query_pair_references(recipient_country,
            static_cast<unsigned>((prepared.actor>>32)&0xffffu),right)
        || !peace_query_reference_sets_equal(left,right) || left.count!=1
        || left.references[0]!=selected->native_reference)
        return fail("NATIVE_PEACE_WAR_REFERENCE_MISMATCH","war_context");
    std::memcpy(prepared.war_id,selected->public_id,sizeof(prepared.war_id));
    static constexpr uintptr_t offsets[]={0x80,0x88,0x90,0x100};
    static constexpr uintptr_t methods[]={0x59b480,0x59b660,0x59b900,0x59bef0};
    for (unsigned i=0;i<4;++i) {
        uintptr_t actual=0;
        if (!read(base+lifecycle_peace_vtable_rva+offsets[i],actual)
            || actual!=base+methods[i])
            return fail("NATIVE_PEACE_LIFECYCLE_ABI_MISMATCH","native_abi");
    }
    using OfferCtor=void* (*)(void*,uint64_t,uint64_t,unsigned char);
    using ActionCtor=void* (*)(void*,uint64_t,uint64_t,unsigned char,const void*,int32_t);
    if (reinterpret_cast<OfferCtor>(base+0x975bb0)(prepared.offer,
        peace_offer_claimant(prepared.actor,prepared.recipient,demand),
        peace_offer_payer(prepared.actor,prepared.recipient,demand),
        demand?1u:0u)!=prepared.offer)
        return fail("NATIVE_PEACE_OFFER_CONSTRUCTOR_FAILED","offer_constructor");
    prepared.offer_constructed=true;
    PeaceOfferParticipants participants{};
    if (!peace_empty_query_offer(prepared.offer,prepared.actor,prepared.recipient,participants,demand))
        return fail("NATIVE_PEACE_OFFER_PARTICIPANTS_UNAVAILABLE","offer_participants");
    PeaceMoneyQuery money{};
    if (amount_raw>=0 && (!peace_money_query_prepare(prepared.offer,amount_raw,money)
        || !money.source_matches))
        return fail_native("NATIVE_PEACE_MONEY_SELECTION_MISMATCH","money_selection");
    PeaceProvinceQueryData provinces(province_request!=nullptr);
    if (province_request && (!provinces.valid()
        || !peace_province_query_prepare(prepared.offer,*province_request,provinces,demand)
         || !provinces.parameters_matched)) {
        return fail_reason(provinces.reason_code,"province_selection",
            "NATIVE_PEACE_PROVINCE_SELECTION_UNAVAILABLE");
    }
    PeaceBaseTermQueryData reparations{},trade_power{},concede{};
    PeaceAnnulQueryData annul{};
    PeaceCoreQueryData return_core(return_core_request!=nullptr);
    PeaceCoreQueryData revoke_core(revoke_core_request!=nullptr);
    PeaceSubjectQueryData release_subject(release_subject_request!=nullptr);
    PeaceSubjectQueryData transfer_subject(transfer_subject_request!=nullptr);
    if (!release_subject.valid() || !transfer_subject.valid())
        return fail("NATIVE_PEACE_SUBJECT_SELECTION_STORAGE_UNAVAILABLE","subject_selection");
    if (return_core_request
        && (!peace_core_query_prepare(prepared.offer,prepared.actor,prepared.recipient,
            demand,*return_core_request,return_core)
            || !return_core.selection_applied || !return_core.parameters_matched
             || !return_core.selection_records_complete)) {
        return fail_reason(return_core.reason_code,"return_core_selection",
            "NATIVE_PEACE_RETURN_CORE_SELECTION_UNAVAILABLE");
    }
    if (revoke_core_request
        && (!peace_core_query_prepare(prepared.offer,prepared.actor,prepared.recipient,
            demand,*revoke_core_request,revoke_core)
            || !revoke_core.selection_applied || !revoke_core.parameters_matched
             || !revoke_core.selection_records_complete)) {
        return fail_reason(revoke_core.reason_code,"revoke_core_selection",
            "NATIVE_PEACE_REVOKE_CORE_SELECTION_UNAVAILABLE");
    }
    if (reparations_requested
        && (!peace_base_term_query_prepare(prepared.offer,prepared.actor,
            prepared.recipient,demand,reparations,PeaceBaseTermKind::reparations,!trade_power_requested && !concede_requested && !annul_requested && !special_requested)
            || !reparations.parameters_matched
            || (!trade_power_requested && !concede_requested && !annul_requested && !special_requested && (!reparations.rule_checked || !reparations.rule_available))))
        return fail_base(reparations,"reparations_selection","NATIVE_PEACE_REPARATIONS_SELECTION_UNAVAILABLE");
    if (trade_power_requested
        && (!peace_base_term_query_prepare(prepared.offer,prepared.actor,
            prepared.recipient,demand,trade_power,PeaceBaseTermKind::trade_power,!concede_requested && !annul_requested && !special_requested,trade_source_tag)
            || !trade_power.parameters_matched
            || (!concede_requested && !annul_requested && !special_requested && (!trade_power.rule_checked || !trade_power.rule_available))))
        return fail_base(trade_power,"trade_power_selection","NATIVE_PEACE_TRADE_POWER_SELECTION_UNAVAILABLE");
    if (reparations_requested && trade_power_requested && !annul_requested && !special_requested)
        peace_base_term_copy_rules(trade_power,reparations);
    if (concede_requested) {
        if (!peace_base_term_query_prepare(prepared.offer,prepared.actor,prepared.recipient,
            demand,concede,PeaceBaseTermKind::concede_defeat,!annul_requested && !special_requested)
            || !concede.parameters_matched
            || (!annul_requested && !special_requested && (!concede.rule_checked || !concede.rule_available)))
            return fail_base(concede,"concede_defeat_selection","NATIVE_PEACE_CONCEDE_DEFEAT_SELECTION_UNAVAILABLE");
        if (reparations_requested && !annul_requested && !special_requested) peace_base_term_copy_rules(concede,reparations);
        if (trade_power_requested && !annul_requested && !special_requested) peace_base_term_copy_rules(concede,trade_power);
    }
    if (annul_requested) {
        if (!annul_request->count || !peace_annul_query_prepare(prepared.offer,prepared.actor,
            prepared.recipient,demand,*annul_request,annul,!special_requested) || !annul.parameters_matched
            || (!special_requested && (!annul.rules.rule_checked || !annul.rules.rule_available))) {
            if (annul.rules.rule_diagnostic_hex[0]) {
                std::memcpy(prepared.native_diagnostic_hex,annul.rules.rule_diagnostic_hex,
                    sizeof(prepared.native_diagnostic_hex));
                prepared.native_diagnostic_hex[sizeof(prepared.native_diagnostic_hex)-1]=0;
            }
            prepared.native_diagnostic_readable=annul.rules.rule_diagnostic_readable;
            prepared.native_diagnostic_truncated=annul.rules.rule_diagnostic_truncated;
            prepared.native_diagnostic_complete=prepared.native_diagnostic_readable
                && !prepared.native_diagnostic_truncated;
            return fail_reason(annul.rules.reason_code,"annul_selection",
                "NATIVE_PEACE_ANNUL_SELECTION_UNAVAILABLE");
        }
        if (reparations_requested && !special_requested) peace_base_term_copy_rules(annul.rules,reparations);
        if (trade_power_requested && !special_requested) peace_base_term_copy_rules(annul.rules,trade_power);
        if (concede_requested && !special_requested) peace_base_term_copy_rules(annul.rules,concede);
    }
    if (!special.prepare(prepared.offer,prepared.actor,prepared.recipient,demand)
        || !special.available())
        return fail_native("NATIVE_PEACE_SPECIAL_SELECTION_UNAVAILABLE","special_selection");
    if (special_requested) {
        if (reparations_requested) special.copy_rules(reparations);
        if (trade_power_requested) special.copy_rules(trade_power);
        if (concede_requested) special.copy_rules(concede);
        if (annul_requested) special.copy_rules(annul.rules);
    }
    if (release_subject_request
        && (!release_subject_request->selection_requested
            || !peace_subject_query_prepare(prepared.offer,prepared.actor,
                prepared.recipient,demand,*release_subject_request,release_subject)
            || !release_subject.selection_applied || !release_subject.parameters_matched
             || !release_subject.selection_records_complete))
        return fail_reason(release_subject.reason_code,"release_subject_selection",
            "NATIVE_PEACE_RELEASE_SUBJECT_SELECTION_UNAVAILABLE");
    if (transfer_subject_request
        && (!transfer_subject_request->selection_requested
            || !peace_subject_query_prepare(prepared.offer,prepared.actor,
                prepared.recipient,demand,*transfer_subject_request,transfer_subject)
            || !transfer_subject.selection_applied || !transfer_subject.parameters_matched
             || !transfer_subject.selection_records_complete))
        return fail_reason(transfer_subject.reason_code,"transfer_subject_selection",
            "NATIVE_PEACE_TRANSFER_SUBJECT_SELECTION_UNAVAILABLE");
    if (country_requests && (!country_requests->any()
        || !peace_country_query_set_prepare(prepared.offer,prepared.actor,
            prepared.recipient,demand,*country_requests,countries)
             || !countries.parameters_matched())) {
        const char* reason=countries.release_nation.reason_code
            ?countries.release_nation.reason_code
            :countries.force_vassal.reason_code
            ?countries.force_vassal.reason_code
            :countries.pu.reason_code
            ?countries.pu.reason_code
            :countries.grant_independence.reason_code;
        return fail_reason(reason,"country_selection","NATIVE_PEACE_COUNTRY_SELECTION_UNAVAILABLE");
    }
    if (annex_request && (!annex_request->selection_requested
        || !peace_annex_query_prepare(prepared.offer,prepared.actor,
            prepared.recipient,demand,*annex_request,annex)
        || !annex.selection_applied || !annex.requested_candidates_found
        || !annex.source_selection_complete || !annex.native_annex_check_called
         || !annex.native_annex_bool))
        return fail_reason(annex.reason_code,"annex_selection",
            "NATIVE_PEACE_ANNEX_SELECTION_UNAVAILABLE");
    PeaceSelectedRuleCapture selected_rules{};
    if ((countries.any() || annex_request || province_request
            || return_core_request || revoke_core_request
            || release_subject_request || transfer_subject_request)
         && (!peace_selected_rules_inspect(prepared.offer,selected_rules)
            || !selected_rules.available)) {
        if (selected_rules.diagnostic_hex[0]) {
            std::memcpy(prepared.native_diagnostic_hex,selected_rules.diagnostic_hex,
                sizeof(prepared.native_diagnostic_hex));
            prepared.native_diagnostic_hex[sizeof(prepared.native_diagnostic_hex)-1]=0;
        }
        prepared.native_diagnostic_readable=selected_rules.diagnostic_readable;
        prepared.native_diagnostic_truncated=selected_rules.diagnostic_truncated;
        prepared.native_diagnostic_complete=prepared.native_diagnostic_readable
            && !prepared.native_diagnostic_truncated;
        prepared.mark_failure(selected_rules.available
            ?"NATIVE_PEACE_SELECTED_RULES_INCOMPLETE"
            :"NATIVE_PEACE_SELECTED_TERM_RULE_UNAVAILABLE","selected_rules",
            PeaceFailureOrigin::native_rule);
        return false;
    }
    bridge::peace_payload::PeacePayloadRef original_offer{};
    if (!peace_capture_offer_snapshot(prepared.offer,original_offer))
        return fail("NATIVE_PEACE_OFFER_SNAPSHOT_UNAVAILABLE","offer_snapshot");
    if (reinterpret_cast<ActionCtor>(base+0x598b20)(prepared.action,prepared.actor,
        prepared.recipient,demand?1u:0u,prepared.offer,prepared.date)!=prepared.action)
        return fail("NATIVE_PEACE_ACTION_CONSTRUCTOR_FAILED","action_constructor");
    prepared.action_constructed=true;
    if (!peace_empty_query_action(prepared.action,prepared.actor,prepared.recipient,prepared.date,demand)
        || (amount_raw>=0 && !peace_money_query_copy(prepared.action+0x48,money))
        || (province_request && (!peace_province_query_read_selection(prepared.action+0x48,provinces,PeaceProvinceSelectionRole::action_copy)
            || !provinces.selection_copy_verified))
        || (reparations_requested && !peace_base_term_read_selection(prepared.action+0x48,
            reparations,PeaceBaseTermSelectionRole::action_copy))
        || (trade_power_requested && !peace_base_term_read_selection(prepared.action+0x48,
            trade_power,PeaceBaseTermSelectionRole::action_copy))
        || (concede_requested && !peace_base_term_read_selection(prepared.action+0x48,
            concede,PeaceBaseTermSelectionRole::action_copy))
        || (annul_requested && !peace_annul_read_selection(prepared.action+0x48,annul,true))
        || (return_core_request && (!peace_core_query_read_selection(prepared.action+0x48,
            return_core,*return_core_request,true) || !return_core.action_copy_matched))
        || (revoke_core_request && (!peace_core_query_read_selection(prepared.action+0x48,
            revoke_core,*revoke_core_request,true) || !revoke_core.action_copy_matched))
        || (release_subject_request && (!peace_subject_query_read_selection(prepared.action+0x48,
            release_subject,*release_subject_request,true) || !release_subject.action_copy_matched))
        || (transfer_subject_request && (!peace_subject_query_read_selection(prepared.action+0x48,
            transfer_subject,*transfer_subject_request,true) || !transfer_subject.action_copy_matched))
        || (countries.any() && !peace_country_query_set_verify_source_copy(
            prepared.action+0x48,countries))
        || (annex_request && (!peace_annex_query_verify_copy(prepared.action+0x48,annex)
            || !annex.action_copy_matched))
        || !special.copy(prepared.action+0x48))
        return fail("NATIVE_PEACE_ACTION_COPY_MISMATCH","action_copy");
    PeaceWarOfferContextCapture context{};
    if (!peace_war_capture_offer_context(prepared.action+0x48,prepared.actor,
            prepared.recipient,context,demand) || !context.complete
        || context.native_war_context!=selected->native_reference)
        return fail("NATIVE_PEACE_ACTION_WAR_CONTEXT_MISMATCH","action_war_context");
    LifecycleActionShape expected=lifecycle_capture_shape(prepared.action);
    if (!expected.matched || !expected.peace_offer || !expected.peace.valid()
        || expected.peace.offer!=original_offer)
        return fail("NATIVE_PEACE_LIFECYCLE_SHAPE_MISMATCH","lifecycle");
    unsigned available_diplomats=0;
    if (!alliance_query_diplomats(prepared.actor,available_diplomats)) {
        prepared.mark_failure("NATIVE_DIPLOMAT_CONTEXT_UNAVAILABLE","diplomat_context");
        return false;
    }
    const bool diplomat_required=reinterpret_cast<bool (*)(void*)>(base+0x59bef0)(prepared.action);
    if (diplomat_required && available_diplomats==0) {
        prepared.mark_failure("NATIVE_DIPLOMAT_UNAVAILABLE","diplomat_availability",
            PeaceFailureOrigin::native_rule);
        return false;
    }
    // Use the same initialized native diagnostic objects as the verified query.
    using Predicate=bool (*)(void*,void*,unsigned char);
    NativeShortString diagnostic{},common_text{},send_text{};
    diagnostic.capacity=common_text.capacity=send_text.capacity=15;
    prepared.native_validity=reinterpret_cast<Predicate>(base+0x59b480)(prepared.action,&diagnostic,0);
    prepared.common_gate=reinterpret_cast<Predicate>(base+0x59b660)(prepared.action,&common_text,0);
    prepared.send_gate=reinterpret_cast<Predicate>(base+0x59b900)(prepared.action,&send_text,0);
    // Preserve the diagnostic belonging to the first failing gate.  The
    // objects are destroyed below, so copy the bounded representation first.
    if (!prepared.native_validity) prepared.copy_diagnostic(diagnostic);
    else if (!prepared.common_gate) prepared.copy_diagnostic(common_text);
    else if (!prepared.send_gate) prepared.copy_diagnostic(send_text);
    else if (diagnostic.size) prepared.copy_diagnostic(diagnostic);
    else if (common_text.size) prepared.copy_diagnostic(common_text);
    else if (send_text.size) prepared.copy_diagnostic(send_text);
    using StringDtor=void (*)(void*);
    reinterpret_cast<StringDtor>(base+0x95660)(&send_text);
    reinterpret_cast<StringDtor>(base+0x95660)(&common_text);
    reinterpret_cast<StringDtor>(base+0x95660)(&diagnostic);
    if (require_available && !prepared.native_validity) {
        prepared.mark_failure("NATIVE_PEACE_VALIDITY_UNAVAILABLE","native_validity_gate",
            PeaceFailureOrigin::native_rule);
        return false;
    }
    if (require_available && !prepared.common_gate) {
        prepared.mark_failure("NATIVE_PEACE_COMMON_GATE_UNAVAILABLE","native_common_gate",
            PeaceFailureOrigin::native_rule);
        return false;
    }
    if (require_available && !prepared.send_gate) {
        prepared.mark_failure("NATIVE_PEACE_SEND_GATE_UNAVAILABLE","native_send_gate",
            PeaceFailureOrigin::native_rule);
        return false;
    }
    const auto after=lifecycle_capture_shape(prepared.action);
    if (!protocol_shape_equal(expected,after))
        return fail("NATIVE_PEACE_ACTION_MUTATED_DURING_GATE_CHECK","gate_lifecycle");
    uintptr_t transport=0;
    if (!execution_world_dispatcher(prepared.dispatcher,transport) || !lifecycle_wrapper_original)
        return fail("NATIVE_PEACE_TRANSPORT_CONTEXT_UNAVAILABLE","transport_context");
    lifecycle_wrapper_observe(prepared.action,&prepared.wrapper);
    prepared.source=protocol_capture(prepared.wrapper);
    prepared.wrapper_rule=peace_wrapper_rule_inspect(prepared.wrapper);
    if (!prepared.wrapper_rule.complete())
        return fail("NATIVE_PEACE_WRAPPER_RULE_INCOMPLETE","native_wrapper_gate");
    if (require_available && !prepared.wrapper_rule.available) {
        prepared.mark_failure("NATIVE_PEACE_WRAPPER_GATE_UNAVAILABLE","native_wrapper_gate",
            PeaceFailureOrigin::native_rule);
        return false;
    }
    if (!(prepared.source.identity && prepared.source.readable
        && prepared.source.prefix_readable && prepared.source.payload.peace_offer
        && protocol_shape_equal(expected,prepared.source.payload)))
        return fail("NATIVE_PEACE_WRAPPER_PAYLOAD_MISMATCH","wrapper_payload");
    return true;
}

static bool execution_peace_authority_test(const char* wire,DWORD size) noexcept {
    static unsigned consumed=0;
    static constexpr const char* terms[]={"WHITE","MONEY","PROVINCE"};
    static constexpr const char* public_terms[]={"white","money","province"};
    unsigned selected=9;
    for (unsigned kind=0;kind<3;++kind) for (unsigned route=0;route<3;++route) {
        char expected[96]{};
        const int length=snprintf(expected,sizeof(expected),"TEST_ONLY FRA_PEACE_ENG_%s%s_WITHOUT_AUTHORITY\n",
            terms[kind],route==2?"_HANDLER":route==1?"_DIRECT":"");
        if (length>0 && size==static_cast<DWORD>(length) && !memcmp(wire,expected,size))
            selected=kind*3+route;
    }
    if (selected==9) return false;
    if (consumed&(1u<<selected)) {
        execution_failure("authority_test","TEST_ALREADY_CONSUMED"); return true;
    }
    consumed|=1u<<selected;
    const unsigned kind=selected/3,route=selected%3;
    const bool direct=route==1,handler=route==2;
    const char* route_name=handler?"handler_entry":direct?"direct_entry":"transport";
    uint64_t actor=0,recipient=0;
    if (!alliance_query_country("FRA",actor) || !alliance_query_country("ENG",recipient)) {
        execution_failure("authority_test","TEST_PEACE_COUNTRY_UNAVAILABLE"); return true;
    }
    uintptr_t country=0;
    PeaceWarReferenceList pair{};
    const PeaceWarRegistryEntry* selected_war=nullptr;
    if (peace_query_country_pointer(actor,country)
        && peace_query_pair_references(country,static_cast<unsigned>((recipient>>32)&0xffffu),pair)
        && pair.count==1) for (unsigned i=0;i<peace_war_registry_size;++i)
            if (peace_war_registry[i].native_reference==pair.references[0]) selected_war=&peace_war_registry[i];
    PeaceProvinceRequest province{};
    province.count=1; province.ids[0]=177; std::memcpy(province.beneficiary,"FRA",4);
    PeacePreparedAction prepared{};
    if (!selected_war || !execution_peace_prepare(prepared,"FRA","ENG",selected_war->public_id,
        kind==1?10000:-1,kind==2?&province:nullptr,false)) {
        execution_failure("authority_test","TEST_PEACE_PREPARATION_FAILED"); return true;
    }
    void* outgoing=prepared.wrapper;
    prepared.wrapper=nullptr;
    bool dispatched=true;
    if (handler) {
        uintptr_t method=0;
        if (read(base+lifecycle_peace_vtable_rva+0x48,method) && method)
            reinterpret_cast<void (*)(void*)>(method)(reinterpret_cast<void*>(prepared.source.action));
        else dispatched=false;
    } else if (direct) reinterpret_cast<void (*)(void*)>(base+0x4e7c80)(outgoing);
    else dispatched=reinterpret_cast<bool (*)(void*,void**)>(base+kDispatcherRva)(
        reinterpret_cast<void*>(prepared.dispatcher),&outgoing);
    if (outgoing) execution_release_constructed(outgoing,nullptr,false);
    char message[1500]{};
    snprintf(message,sizeof(message),
        "{\"event\":\"native_peace_authority_test_dispatched\",\"session_id\":\"%lu-%llx\","
        "\"term\":\"%s\",\"route\":\"%s\",\"dispatch_route\":\"%s\",\"actor\":\"FRA\",\"recipient\":\"ENG\","
        "\"date_raw\":%d,\"war_id\":\"%s\",\"war_context_complete\":true,"
        "\"source_wrapper\":\"0x%llx\",\"source_action\":\"0x%llx\",\"family\":\"peace\","
        "\"snapshot_complete\":true,\"logical_copy_equal\":true,\"term_count\":%u,"
        "\"native_validity\":%s,\"common_gate\":%s,\"send_gate\":%s,"
        "\"native_wrapper_gate_checked\":%s,\"native_wrapper_gate\":%s,"
        "\"dispatcher_accepted\":%s,\"authority_seed_created\":false}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
        public_terms[kind],route_name,route_name,
        prepared.date,prepared.war_id,static_cast<unsigned long long>(prepared.source.address),
        static_cast<unsigned long long>(prepared.source.action),prepared.source.payload.peace.offer.get()->term_count,
        prepared.native_validity?"true":"false",prepared.common_gate?"true":"false",
        prepared.send_gate?"true":"false",prepared.wrapper_rule.complete()?"true":"false",
        prepared.wrapper_rule.available?"true":"false",dispatched?"true":"false");
    line(message); return true;
}
