// A selected, current war is revalidated before constructing a native
// CPeaceOffer and its action. An optional amount uses the native money setter.
// Placement objects are destroyed in reverse order.
// A private wrapper is constructed solely to run its native validity rule,
// then destroyed. No dispatcher, transport or business handler is invoked.

struct PeaceOfferParticipants {
    uint64_t handles[4][256]{};
    unsigned counts[4]{};
};

static bool peace_empty_query_offer(const unsigned char* offer,uint64_t actor,
    uint64_t recipient,PeaceOfferParticipants& participants,bool demand=true) noexcept {
    // Public actor/recipient remain the action endpoints.  The native source
    // offer reverses its +0x18 claimant/+0x10 payer fields for offer direction.
    const uintptr_t address=reinterpret_cast<uintptr_t>(offer);
    uintptr_t table=0,owner=0; uint32_t discriminator=0;
    uint64_t payer=0,claimant=0; unsigned char direction=0;
    const uint64_t expected_payer=peace_offer_payer(actor,recipient,demand);
    const uint64_t expected_claimant=peace_offer_claimant(actor,recipient,demand);
    if (!read(address,table) || table!=base+0x1c578b8
        || !read(address+8,discriminator) || discriminator!=0x165
        || !read(address+0x10,payer) || payer!=expected_payer
        || !read(address+0x18,claimant) || claimant!=expected_claimant
        || !read(address+0x20,direction) || direction!=(demand?1u:0u)
        || !read(address+0xe8,owner) || owner!=address) return false;
    static constexpr unsigned offsets[]={0x28,0x40,0x58,0x70};
    for (unsigned group=0;group<4;++group) {
        uintptr_t begin=0,end=0,capacity=0;
        if (!read(address+offsets[group],begin)
            || !read(address+offsets[group]+8,end)
            || !read(address+offsets[group]+16,capacity)
            || !begin || end<=begin || capacity<end || (end-begin)%8
            || (end-begin)/8>256) return false;
        participants.counts[group]=static_cast<unsigned>((end-begin)/8);
        for (unsigned i=0;i<participants.counts[group];++i) {
            uintptr_t country=0;
            if (!read(begin+static_cast<uintptr_t>(i)*8,participants.handles[group][i])
                || !peace_query_country_pointer(participants.handles[group][i],country)) return false;
        }
    }
    return true;
}

static bool peace_empty_query_action(const unsigned char* action,uint64_t actor,
    uint64_t recipient,int32_t date,bool demand=true) noexcept {
    const uintptr_t address=reinterpret_cast<uintptr_t>(action);
    uintptr_t table=0; uint32_t discriminator=0;
    uint64_t a=0,mirror=0,r=0; int32_t d28=0,d2c=0,envoy=0,state=0,variant=0;
    unsigned char flag40=0,direction=0,preview=0;
    return read(address,table) && table==base+0x1c7b840
        && read(address+8,discriminator) && discriminator==0x165
        && read(address+0x10,a) && a==actor
        && read(address+0x18,mirror) && mirror==actor
        && read(address+0x20,r) && r==recipient
        && read(address+0x28,d28) && d28==date
        && read(address+0x2c,d2c) && d2c==date
        && read(address+0x30,envoy) && envoy==-1
        && read(address+0x34,state) && state==0
        && read(address+0x38,variant) && variant==1
        && read(address+0x40,flag40) && flag40==1
        && read(address+0x41,direction) && direction==(demand?1u:0u)
        && read(address+0x208,preview) && preview==0;
}

struct PeaceOfferQueryMessage {
    char* text=nullptr;
    size_t capacity=0;
    explicit PeaceOfferQueryMessage(bool provinces,bool core=false,
        bool second_core=false,unsigned subject_count=0,unsigned country_count=0,
        bool annex=false) noexcept
        : capacity(130000+peace_consequence_json_capacity+(provinces?peace_province_json_capacity:0)
            +(core?peace_core_json_capacity:0)
            +(second_core?peace_core_json_capacity:0)
            +(static_cast<size_t>(subject_count)*peace_subject_json_capacity)
            +(static_cast<size_t>(country_count)*peace_country_json_capacity)
            +(annex?peace_annex_json_capacity:0u)
            +(country_count?peace_country_json_capacity:0u)
            +(annex?peace_annex_json_capacity:0u)) {
        text=static_cast<char*>(HeapAlloc(GetProcessHeap(),0,capacity));
    }
    ~PeaceOfferQueryMessage() noexcept { if (text) HeapFree(GetProcessHeap(),0,text); }
    PeaceOfferQueryMessage(const PeaceOfferQueryMessage&)=delete;
    PeaceOfferQueryMessage& operator=(const PeaceOfferQueryMessage&)=delete;
};

static void peace_empty_offer_query_run(const char* id,const char* actor_tag,
    const char* recipient_tag,uint64_t actor,uint64_t recipient,int32_t date,
    const char* war_id,int32_t money_amount=-1,
    const PeaceProvinceRequest* province_request=nullptr,bool demand=true,
    const char* primary_action=nullptr,bool reparations_requested=false,
    bool trade_power_requested=false,const char* trade_source_tag=nullptr,
    bool trade_selection_requested=true,bool concede_requested=false,
    const PeaceAnnulRequest* annul_request=nullptr,bool humiliate_requested=false,
    bool strength_requested=false,bool religion_requested=false,
    const PeaceCoreRequest* core_request=nullptr,
    const PeaceCoreRequest* revoke_core_request=nullptr,
    bool combined_core=false,
    const PeaceSubjectRequest* subject_request=nullptr,
    const PeaceSubjectRequest* release_subject_request=nullptr,
    const PeaceSubjectRequest* transfer_subject_request=nullptr,
    bool combined_subject_output=false,
    const PeaceCountryRequestSet* country_requests=nullptr,
    const PeaceAnnexRequest* annex_request=nullptr) noexcept {
    // QUERY16 keeps the original single-family pointer.  QUERY17 supplies
    // the two explicit family pointers; normalize the legacy pointer here so
    // the construction, copy and JSON paths use one set of invariants.
    if (subject_request) {
        if (subject_request->release_subject) release_subject_request=subject_request;
        else transfer_subject_request=subject_request;
    }
    PeaceSpecialQueryData special(humiliate_requested,strength_requested,religion_requested);
    const bool special_requested=special.any();
    const bool annul_requested=annul_request!=nullptr;
    const bool core_requested=core_request!=nullptr
        || revoke_core_request!=nullptr;
    const bool release_subject_requested=release_subject_request!=nullptr;
    const bool transfer_subject_requested=transfer_subject_request!=nullptr;
    const bool subject_requested=release_subject_requested || transfer_subject_requested;
    const bool combined_subject_requested=combined_subject_output
        || (release_subject_requested && transfer_subject_requested);
    const bool money_requested=money_amount>=0;
    const bool provinces_requested=province_request!=nullptr;
    const bool combined=money_requested && provinces_requested;
    PeaceCountryRequestSet empty_country_requests{};
    const PeaceCountryRequestSet& country_request_set=country_requests
        ?*country_requests:empty_country_requests;
    const bool country_requested=country_request_set.any();
    PeaceAnnexRequest annex_local{};
    const PeaceAnnexRequest* effective_annex_request=annex_request;
    if (annex_request) {
        annex_local=*annex_request;
        if (!annex_local.country[0]) {
            const char* payer_tag=demand?recipient_tag:actor_tag;
            if (!peace_annex_valid_tag(payer_tag)) {
                alliance_query_failure(id,"QUERY_PEACE_ANNEX_TARGET_UNAVAILABLE"); return;
            }
            memcpy(annex_local.country,payer_tag,4);
            annex_local.selection_requested=false;
        }
        effective_annex_request=&annex_local;
    }
    const bool annex_requested=effective_annex_request!=nullptr;
    PeaceBaseTermQueryData reparations{},trade_power{},concede{};
    PeaceAnnulQueryData annul{};
    PeaceProvinceQueryData provinces(provinces_requested);
    provinces.expected_direction=demand?1u:0u;
    PeaceCoreQueryData core(core_request!=nullptr);
    PeaceCoreQueryData revoke_core(revoke_core_request!=nullptr);
    PeaceSubjectQueryData release_subject(release_subject_requested);
    PeaceSubjectQueryData transfer_subject(transfer_subject_requested);
    PeaceCountryQuerySet country_terms(country_request_set);
    PeaceAnnexQueryData annex(annex_requested);
    PeaceOfferQueryMessage message(provinces_requested,core_request!=nullptr,
        revoke_core_request!=nullptr,
        static_cast<unsigned>(release_subject_requested)
            +static_cast<unsigned>(transfer_subject_requested),
        country_requested?4u:0u,annex_requested);
    if (!provinces.valid() || !core.valid() || !revoke_core.valid()
        || !release_subject.valid() || !transfer_subject.valid()
        || !country_terms.valid() || !annex.valid() || !message.text) {
        alliance_query_failure(id,"QUERY_PEACE_QUERY_BUFFER_UNAVAILABLE"); return;
    }
    const PeaceWarRegistryEntry* selected=nullptr;
    for (unsigned i=0;i<peace_war_registry_size;++i)
        if (!strcmp(peace_war_registry[i].public_id,war_id)) selected=&peace_war_registry[i];
    if (!selected) { alliance_query_failure(id,"QUERY_PEACE_WAR_ID_UNKNOWN"); return; }
    uintptr_t actor_country=0,recipient_country=0;
    PeaceWarReferenceList left{},right{};
    if (!peace_query_country_pointer(actor,actor_country)
        || !peace_query_country_pointer(recipient,recipient_country)
        || !peace_query_pair_references(actor_country,
            static_cast<unsigned>((recipient>>32)&0xffffu),left)
        || !peace_query_pair_references(recipient_country,
            static_cast<unsigned>((actor>>32)&0xffffu),right)
        || !peace_query_reference_sets_equal(left,right)) {
        alliance_query_failure(id,"QUERY_PEACE_WAR_ASSOCIATIONS_UNAVAILABLE"); return;
    }
    // The native constructor chooses a war from the pair, not from a war ID.
    // Therefore an ambiguous pair cannot be inspected as a selected offer.
    if (left.count!=1 || left.references[0]!=selected->native_reference) {
        alliance_query_failure(id,"QUERY_PEACE_SELECTED_WAR_NOT_UNIQUE"); return;
    }
    static constexpr uintptr_t slots[]={0,0x80,0x88,0x90,0x100};
    static constexpr uintptr_t methods[]={0x598b90,0x59b480,0x59b660,0x59b900,0x59bef0};
    for (unsigned i=0;i<5;++i) {
        uintptr_t method=0;
        if (!read(base+0x1c7b840+slots[i],method)
            || (method!=base+methods[i]
                && !(i==0 && method==reinterpret_cast<uintptr_t>(&lifecycle_destructor_observe)
                    && lifecycle_peace_destructor_original==reinterpret_cast<LifecycleDestructorMethod>(base+methods[i])))) {
            alliance_query_failure(id,"QUERY_PEACE_METHOD_IDENTITY_CHANGED"); return;
        }
    }
    unsigned available_diplomats=0;
    if (!alliance_query_diplomats(actor,available_diplomats)) {
        alliance_query_failure(id,"NATIVE_DIPLOMAT_CONTEXT_UNAVAILABLE"); return;
    }
    alignas(16) unsigned char offer[0x1c0]{},action[0x210]{};
    using OfferCtor=void* (*)(void*,uint64_t,uint64_t,unsigned char);
    using ActionCtor=void* (*)(void*,uint64_t,uint64_t,unsigned char,const void*,int32_t);
    using OfferDtor=void (*)(void*);
    using ActionDtor=void* (*)(void*,unsigned);
    if (reinterpret_cast<OfferCtor>(base+0x975bb0)(offer,
            peace_offer_claimant(actor,recipient,demand),
            peace_offer_payer(actor,recipient,demand),
            demand?1u:0u)!=offer) {
        alliance_query_failure(id,"QUERY_PEACE_OFFER_CONSTRUCTION_FAILED"); return;
    }
    PeaceOfferParticipants original{},copied{},after{};
    if (!peace_empty_query_offer(offer,actor,recipient,original,demand)) {
        reinterpret_cast<OfferDtor>(base+0x976030)(offer);
        alliance_query_failure(id,"QUERY_PEACE_OFFER_IDENTITY_CHANGED"); return;
    }
    PeaceSerializedCapture source_fields{},copied_fields{},after_fields{};
    // The same serializer-defined capture used for source/copy comparison
    // also checks all term fields before a province toggle can read them.
    if (provinces_requested && (!peace_capture_serialized_offer(offer,source_fields)
        || !source_fields.payload.complete)) {
        reinterpret_cast<OfferDtor>(base+0x976030)(offer);
        alliance_query_failure(id,"QUERY_PEACE_PROVINCE_PAYLOAD_INCOMPLETE"); return;
    }
    if (core_requested && !peace_core_query_prepare(offer,actor,recipient,demand,
        core_request?*core_request:*revoke_core_request,
        core_request?core:revoke_core)) {
        reinterpret_cast<OfferDtor>(base+0x976030)(offer);
        alliance_query_failure(id,"QUERY_PEACE_CORE_PREPARATION_FAILED"); return;
    }
    if (core_request && revoke_core_request) {
        // The first call above prepares Return Core.  Revoke Core is appended
        // independently so a combined offer retains both native term vectors.
        if (!peace_core_query_prepare(offer,actor,recipient,demand,
            *revoke_core_request,revoke_core)) {
            reinterpret_cast<OfferDtor>(base+0x976030)(offer);
            alliance_query_failure(id,"QUERY_PEACE_REVOKE_CORE_PREPARATION_FAILED"); return;
        }
    }
    PeaceMoneyQuery money{};
    if (money_requested) {
        if (!peace_money_query_prepare(offer,money_amount,money)) {
            reinterpret_cast<OfferDtor>(base+0x976030)(offer);
            alliance_query_failure(id,"QUERY_PEACE_MONEY_PREPARATION_FAILED"); return;
        }
        original=PeaceOfferParticipants{};
        if (!peace_empty_query_offer(offer,actor,recipient,original,demand)) {
            reinterpret_cast<OfferDtor>(base+0x976030)(offer);
            alliance_query_failure(id,"QUERY_PEACE_MONEY_OFFER_IDENTITY_CHANGED"); return;
        }
    }
    if (provinces_requested) {
        if (!peace_province_query_prepare(offer,*province_request,provinces,demand)) {
            reinterpret_cast<OfferDtor>(base+0x976030)(offer);
            alliance_query_failure(id,"QUERY_PEACE_PROVINCE_PREPARATION_FAILED"); return;
        }
        original=PeaceOfferParticipants{};
        if (!peace_empty_query_offer(offer,actor,recipient,original,demand)) {
            reinterpret_cast<OfferDtor>(base+0x976030)(offer);
            alliance_query_failure(id,"QUERY_PEACE_PROVINCE_OFFER_IDENTITY_CHANGED"); return;
        }
    }
    if (reparations_requested
        && !peace_base_term_query_prepare(offer,actor,recipient,demand,reparations,
            PeaceBaseTermKind::reparations,!trade_power_requested && !concede_requested && !annul_requested && !special_requested)) {
        reinterpret_cast<OfferDtor>(base+0x976030)(offer);
        alliance_query_failure(id,"QUERY_PEACE_REPARATIONS_PREPARATION_FAILED"); return;
    }
    if (trade_power_requested
        && !peace_base_term_query_prepare(offer,actor,recipient,demand,trade_power,
            PeaceBaseTermKind::trade_power,!concede_requested && !annul_requested && !special_requested,trade_source_tag,trade_selection_requested)) {
        reinterpret_cast<OfferDtor>(base+0x976030)(offer);
        alliance_query_failure(id,"QUERY_PEACE_TRADE_POWER_PREPARATION_FAILED"); return;
    }
    if (reparations_requested && trade_power_requested && !annul_requested && !special_requested)
        peace_base_term_copy_rules(trade_power,reparations);
    if (concede_requested) {
        if (!peace_base_term_query_prepare(offer,actor,recipient,demand,concede,
            PeaceBaseTermKind::concede_defeat,!annul_requested && !special_requested)) {
            reinterpret_cast<OfferDtor>(base+0x976030)(offer);
            alliance_query_failure(id,"QUERY_PEACE_CONCEDE_DEFEAT_PREPARATION_FAILED"); return;
        }
        if (reparations_requested && !annul_requested && !special_requested) peace_base_term_copy_rules(concede,reparations);
        if (trade_power_requested && !annul_requested && !special_requested) peace_base_term_copy_rules(concede,trade_power);
    }

    if (annul_requested) {
        if (!peace_annul_query_prepare(offer,actor,recipient,demand,*annul_request,annul,!special_requested)) {
            reinterpret_cast<OfferDtor>(base+0x976030)(offer);
            alliance_query_failure(id,"QUERY_PEACE_ANNUL_PREPARATION_FAILED"); return;
        }
        if (reparations_requested && !special_requested) peace_base_term_copy_rules(annul.rules,reparations);
        if (trade_power_requested && !special_requested) peace_base_term_copy_rules(annul.rules,trade_power);
        if (concede_requested && !special_requested) peace_base_term_copy_rules(annul.rules,concede);
    }
    if (!special.prepare(offer,actor,recipient,demand)) {
        reinterpret_cast<OfferDtor>(base+0x976030)(offer);
        alliance_query_failure(id,"QUERY_PEACE_SPECIAL_PREPARATION_FAILED"); return;
    }
    if (special_requested) {
        if (reparations_requested) special.copy_rules(reparations);
        if (trade_power_requested) special.copy_rules(trade_power);
        if (concede_requested) special.copy_rules(concede);
        if (annul_requested) special.copy_rules(annul.rules);
    }
    if (release_subject_requested && !peace_subject_query_prepare(offer,actor,recipient,
        demand,*release_subject_request,release_subject)) {
        reinterpret_cast<OfferDtor>(base+0x976030)(offer);
        alliance_query_failure(id,"QUERY_PEACE_RELEASE_SUBJECT_PREPARATION_FAILED"); return;
    }
    if (transfer_subject_requested && !peace_subject_query_prepare(offer,actor,recipient,
        demand,*transfer_subject_request,transfer_subject)) {
        reinterpret_cast<OfferDtor>(base+0x976030)(offer);
        alliance_query_failure(id,"QUERY_PEACE_TRANSFER_SUBJECT_PREPARATION_FAILED"); return;
    }
    if (country_requested
        && !peace_country_query_set_prepare(offer,actor,recipient,demand,
            country_request_set,country_terms)) {
        reinterpret_cast<OfferDtor>(base+0x976030)(offer);
        alliance_query_failure(id,"QUERY_PEACE_COUNTRY_PREPARATION_FAILED"); return;
    }
    if (annex_requested
        && !peace_annex_query_prepare(offer,actor,recipient,demand,
            *effective_annex_request,annex)) {
        reinterpret_cast<OfferDtor>(base+0x976030)(offer);
        alliance_query_failure(id,"QUERY_PEACE_ANNEX_PREPARATION_FAILED"); return;
    }
    const bool selected_rules_requested=country_requested || annex_requested
        || (provinces_requested && provinces.selection_requested
            && provinces.parameters_matched)
        || (core_request && core.selection_applied && core.parameters_matched)
        || (revoke_core_request && revoke_core.selection_applied
            && revoke_core.parameters_matched)
        || (release_subject_requested && release_subject.selection_applied
            && release_subject.parameters_matched)
        || (transfer_subject_requested && transfer_subject.selection_applied
            && transfer_subject.parameters_matched);
    PeaceSelectedRuleCapture selected_rules{};
    if (selected_rules_requested)
        peace_selected_rules_inspect(offer,selected_rules);

    if (reinterpret_cast<ActionCtor>(base+0x598b20)(action,actor,recipient,
            demand?1u:0u,offer,date)!=action) {
        reinterpret_cast<OfferDtor>(base+0x976030)(offer);
        alliance_query_failure(id,"QUERY_PEACE_ACTION_CONSTRUCTION_FAILED"); return;
    }
    const bool identity=peace_empty_query_action(action,actor,recipient,date,demand)
        && peace_empty_query_offer(action+0x48,actor,recipient,copied,demand)
        && !memcmp(&original,&copied,sizeof(original))
        && (!money_requested || peace_money_query_copy(action+0x48,money))
        && (!provinces_requested
            || (peace_province_query_read_selection(action+0x48,provinces,PeaceProvinceSelectionRole::action_copy)
                && provinces.selection_copy_verified))
        && (!reparations_requested || peace_base_term_read_selection(action+0x48,
            reparations,PeaceBaseTermSelectionRole::action_copy))
        && (!trade_power_requested || peace_base_term_read_selection(action+0x48,
            trade_power,PeaceBaseTermSelectionRole::action_copy))
        && (!concede_requested || peace_base_term_read_selection(action+0x48,
            concede,PeaceBaseTermSelectionRole::action_copy))
        && (!annul_requested || peace_annul_read_selection(action+0x48,annul,true))
        && (!core_request || peace_core_query_read_selection(action+0x48,core,
            *core_request,true))
        && (!revoke_core_request || peace_core_query_read_selection(action+0x48,
            revoke_core,*revoke_core_request,true))
        && (!release_subject_requested || peace_subject_query_read_selection(action+0x48,
            release_subject,*release_subject_request,true))
        && (!transfer_subject_requested || peace_subject_query_read_selection(action+0x48,
            transfer_subject,*transfer_subject_request,true))
        && (!country_requested
            || peace_country_query_set_verify_source_copy(action+0x48,country_terms))
        && (!annex_requested || peace_annex_query_verify_copy(action+0x48,annex))
        && special.copy(action+0x48);
    if (!identity) {
        reinterpret_cast<ActionDtor>(base+0x598b90)(action,0);
        reinterpret_cast<OfferDtor>(base+0x976030)(offer);
        alliance_query_failure(id,"QUERY_PEACE_ACTION_IDENTITY_CHANGED"); return;
    }
    const bool diplomat_required=reinterpret_cast<bool (*)(void*)>(base+0x59bef0)(action);
    PeaceWarOfferContextCapture war_context{};
    if (!peace_war_capture_offer_context(action+0x48,actor,recipient,war_context,demand)
        || war_context.native_war_context!=selected->native_reference) {
        reinterpret_cast<ActionDtor>(base+0x598b90)(action,0);
        reinterpret_cast<OfferDtor>(base+0x976030)(offer);
        alliance_query_failure(id,"QUERY_PEACE_WAR_CONTEXT_UNAVAILABLE"); return;
    }
    char war_json[8192]{},war_private[2048]{},private_session[80]{};
    bridge::live_war_score_query::Request score_request{};
    bridge::live_war_score_query::Result score_result{};
    peace_war_score_capture_for_offer(war_context,war_id,score_request,score_result);
    char score_private[24576]{};
    snprintf(private_session,sizeof(private_session),"%lu-%llx",
        static_cast<unsigned long>(GetCurrentProcessId()),
        static_cast<unsigned long long>(observation_creation));
    if (!peace_war_offer_context_public_json_with_score(war_context,
            score_request,score_result,war_json,sizeof(war_json))
        || !peace_war_offer_context_private_json(war_context,private_session,id,
            war_private,sizeof(war_private))
        || !live_war_score_private_event_json(private_session,id,
            primary_action?primary_action:provinces_requested?"cede_province":
                money_requested?"demand_ducats":"white_peace",
            actor_tag,recipient_tag,date,score_request,score_result,
            score_private,sizeof(score_private))) {
        reinterpret_cast<ActionDtor>(base+0x598b90)(action,0);
        reinterpret_cast<OfferDtor>(base+0x976030)(offer);
        alliance_query_failure(id,"QUERY_PEACE_WAR_CONTEXT_OUTPUT_FAILED"); return;
    }
    if (!peace_capture_serialized_offer(offer,source_fields)
        || !peace_capture_serialized_offer(action+0x48,copied_fields)
        || !(source_fields.payload==copied_fields.payload)) {
        reinterpret_cast<ActionDtor>(base+0x598b90)(action,0);
        reinterpret_cast<OfferDtor>(base+0x976030)(offer);
        alliance_query_failure(id,"QUERY_PEACE_PAYLOAD_COPY_MISMATCH"); return;
    }
    NativeShortString diagnostic{},common_text{},send_text{};
    diagnostic.capacity=common_text.capacity=send_text.capacity=15;
    using Predicate=bool (*)(void*,void*,unsigned char);
    const bool valid=reinterpret_cast<Predicate>(base+0x59b480)(action,&diagnostic,0);
    const bool common=reinterpret_cast<Predicate>(base+0x59b660)(action,&common_text,0);
    const bool send=reinterpret_cast<Predicate>(base+0x59b900)(action,&send_text,0);
    const PeaceWrapperRuleCapture wrapper_rule=peace_wrapper_rule_query(action);
    char diagnostic_hex[1025]{},common_hex[1025]{},send_hex[1025]{};
    bool readable=false,truncated=false,common_readable=false,common_truncated=false;
    bool send_readable=false,send_truncated=false;
    declarewar_query_hex(diagnostic,diagnostic_hex,readable,truncated);
    declarewar_query_hex(common_text,common_hex,common_readable,common_truncated);
    declarewar_query_hex(send_text,send_hex,send_readable,send_truncated);
    char evaluation[49152]{};
    peace_offer_evaluation_query(id,action,valid && (!money_requested || money.source_matches)
        && (!provinces_requested || (provinces.selection_requested && provinces.parameters_matched))
        && (!reparations_requested || (reparations.parameters_matched && reparations.rule_available))
        && (!trade_power_requested || (trade_power.parameters_matched && trade_power.rule_available))
        && (!concede_requested || (concede.parameters_matched && concede.rule_available))
        && (!annul_requested || (annul.parameters_matched && annul.rules.rule_available))
        && (!release_subject_requested || release_subject.outer_complete())
        && (!transfer_subject_requested || transfer_subject.outer_complete())
        && (!country_requested || country_terms.parameters_matched())
        && (!annex_requested || (annex.selection_requested && annex.complete()))
        && special.available()
        && (recipient&0xffffffu)!=0x415246u
        && (recipient&0xffffffu)!=0x524f50u,evaluation);
    PeaceConsequenceQuery consequences;
    const bool consequences_output=peace_consequence_query(action+0x48,actor,recipient,
        demand,provinces_requested?provinces.requested_beneficiary:0,copied_fields.payload,consequences);
    const bool fields_unchanged=peace_capture_serialized_offer(action+0x48,after_fields)
        && copied_fields.payload==after_fields.payload;
    // Native preview/evaluation may refresh derived/cache bytes in the
    // temporary action and offer (the gold aggregate, for example, reads
    // offer+0xf0).  The complete serialized payload, action identity and
    // participant vectors are the stable query contract; comparing every raw
    // byte incorrectly rejects a valid money offer after that refresh.
    const bool action_identity_unchanged=peace_empty_query_action(
        action,actor,recipient,date,demand);
    const bool offer_identity_unchanged=peace_empty_query_offer(
        action+0x48,actor,recipient,after,demand)
        && !memcmp(&copied,&after,sizeof(copied))
        && (!provinces_requested
            || (peace_province_query_read_selection(action+0x48,provinces,PeaceProvinceSelectionRole::action_copy)
                && provinces.selection_copy_verified));
    const bool unchanged=fields_unchanged && action_identity_unchanged
        && offer_identity_unchanged;
    using StringDtor=void (*)(void*);
    reinterpret_cast<StringDtor>(base+0x95660)(&diagnostic);
    reinterpret_cast<StringDtor>(base+0x95660)(&common_text);
    reinterpret_cast<StringDtor>(base+0x95660)(&send_text);
    reinterpret_cast<ActionDtor>(base+0x598b90)(action,0);
    reinterpret_cast<OfferDtor>(base+0x976030)(offer);
    if (!unchanged) { alliance_query_failure(id,"QUERY_PEACE_OFFER_CHANGED"); return; }
    if (!consequences_output) { alliance_query_failure(id,"QUERY_PEACE_CONSEQUENCES_OUTPUT_FAILED"); return; }
    if (provinces_requested) {
        if (!peace_province_query_json(provinces)) {
            alliance_query_failure(id,"QUERY_PEACE_PROVINCE_OUTPUT_FAILED"); return;
        }
        peace_province_query_private(id,provinces);
    }
    if (core_requested) {
        if ((core_request && !peace_core_query_json(core))
            || (revoke_core_request && !peace_core_query_json(revoke_core))) {
            alliance_query_failure(id,"QUERY_PEACE_CORE_OUTPUT_FAILED"); return;
        }
        if (core_request) peace_core_query_private(id,primary_action,core);
        if (revoke_core_request) peace_core_query_private(id,primary_action,revoke_core);
    }
    const char* release_subject_json="null";
    const char* transfer_subject_json="null";
    if (release_subject_requested) {
        if (!peace_subject_query_json(release_subject)) {
            alliance_query_failure(id,"QUERY_PEACE_RELEASE_SUBJECT_OUTPUT_FAILED"); return;
        }
        release_subject_json=release_subject.json;
        peace_subject_query_private(id,release_subject);
    }
    if (transfer_subject_requested) {
        if (!peace_subject_query_json(transfer_subject)) {
            alliance_query_failure(id,"QUERY_PEACE_TRANSFER_SUBJECT_OUTPUT_FAILED"); return;
        }
        transfer_subject_json=transfer_subject.json;
        peace_subject_query_private(id,transfer_subject);
    }
    if (country_requested) {
        if (!peace_country_query_set_json(country_terms)) {
            alliance_query_failure(id,"QUERY_PEACE_COUNTRY_OUTPUT_FAILED"); return;
        }
        if (country_terms.release_nation.enabled)
            peace_country_query_private(id,country_terms.release_nation);
        if (country_terms.force_vassal.enabled)
            peace_country_query_private(id,country_terms.force_vassal);
        if (country_terms.pu.enabled)
            peace_country_query_private(id,country_terms.pu);
        if (country_terms.grant_independence.enabled)
            peace_country_query_private(id,country_terms.grant_independence);
    }
    if (annex_requested) {
        if (!peace_annex_query_json(annex)) {
            alliance_query_failure(id,"QUERY_PEACE_ANNEX_OUTPUT_FAILED"); return;
        }
        peace_annex_query_private(id,annex);
    }
    const char* country_json_output=country_requested
        ?peace_country_query_set_json_text(country_terms):"null";
    const bool country_family_output=country_requested || annex_requested;
    const char* empty_country_terms="{\"release_nation\":null,\"force_vassalization\":null,\"form_personal_union\":null,\"grant_independence\":null}";
    const char* country_field_key=country_family_output?",\"native_country_terms\":" : "";
    const char* country_field_value=country_family_output
        ?(country_requested?country_json_output:empty_country_terms):"";
    const char* annex_field_key=country_family_output?",\"native_annexation\":" : "";
    const char* annex_field_value=country_family_output?(annex_requested?annex.json:"null"):"";
    const char* selected_rules_json="null";
    if (selected_rules_requested) {
        if (!peace_selected_rules_json(selected_rules)) {
            alliance_query_failure(id,"QUERY_PEACE_SELECTED_RULES_OUTPUT_FAILED"); return;
        }
        selected_rules_json=selected_rules.json;
    }
    const char* selected_rules_key=selected_rules_requested
        ?",\"native_selected_rules\":" : "";
    const char* selected_rules_value=selected_rules_requested?selected_rules_json:"";
    line(war_private);
    line(score_private);
    peace_serialized_capture_private(id,"source",source_fields);
    peace_serialized_capture_private(id,"action",copied_fields);
    for (unsigned group=0;group<4;++group) {
        for (unsigned member=0;member<original.counts[group];++member) {
            const uint64_t handle=original.handles[group][member];
            char detail[500];
            snprintf(detail,sizeof(detail),
                "{\"event\":\"native_peace_offer_participant_private\",\"private\":true,\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"war_id\":\"%s\",\"group\":%u,\"index\":%u,\"tag\":\"%c%c%c\",\"handle\":\"0x%llx\"}\n",
                static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
                id,war_id,group,member,static_cast<char>(handle),static_cast<char>(handle>>8),
                static_cast<char>(handle>>16),static_cast<unsigned long long>(handle));
            line(detail);
        }
    }
    char money_json[1500]="null";
    if (money_requested) peace_money_query_json(money,actor_tag,recipient_tag,
        demand,money_json);
    char payload_json[1500]{};
    peace_serialized_capture_json(source_fields,copied_fields,after_fields,
        payload_json,sizeof(payload_json));
    char reparations_json[2600]="null",trade_power_json[9000]="null",concede_json[2600]="null",concede_field[2700]{},base_term_fields[54000]{};
    char annul_json[26000]="null",annul_field[26100]{};
    char special_fields[8000]{};
    char subject_field[60200]{};
    if (!special.json(actor_tag,recipient_tag,demand,special_fields)) {
        alliance_query_failure(id,"QUERY_PEACE_SPECIAL_OUTPUT_FAILED"); return;
    }
    if (annul_requested) {
        peace_annul_query_json(annul,annul_json,sizeof(annul_json));
        snprintf(annul_field,sizeof(annul_field),",\"native_annul_treaties\":%s",annul_json);
    }
    if (reparations_requested) peace_base_term_query_json(reparations,actor_tag,recipient_tag,demand,reparations_json);
    if (trade_power_requested) peace_base_term_query_json(trade_power,actor_tag,recipient_tag,demand,trade_power_json);
    if (concede_requested) {
        peace_base_term_query_json(concede,actor_tag,recipient_tag,demand,concede_json);
        snprintf(concede_field,sizeof(concede_field),",\"native_concede_defeat\":%s",concede_json);
    }
    if (reparations_requested || trade_power_requested || concede_requested || annul_requested || special_requested || core_requested || subject_requested || country_requested || annex_requested) snprintf(base_term_fields,sizeof(base_term_fields),
        ",\"term_mask\":\"%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s\",\"native_reparations\":%s,\"native_trade_power\":%s%s%s%s",
        money_requested?"m":"",provinces_requested?"p":"",reparations_requested?"r":"",trade_power_requested?"t":"",concede_requested?"c":"",annul_requested?"a":"",
        humiliate_requested?"h":"",strength_requested?"s":"",religion_requested?"f":"",
        core_request?"b":"",revoke_core_request?"v":"",
        release_subject_requested?"l":"",transfer_subject_requested?"x":"",
        country_terms.release_nation.enabled?"n":"",
        country_terms.force_vassal.enabled?"z":"",
        country_terms.pu.enabled?"u":"",
        country_terms.grant_independence.enabled?"i":"",
        annex_requested?"e":"",
        reparations_json,trade_power_json,concede_field,annul_field,special_fields);
    if (combined_subject_requested) snprintf(subject_field,sizeof(subject_field),
        ",\"native_subject_terms\":{\"release_subject\":%s,\"transfer_subject\":%s}",
        release_subject_json,transfer_subject_json);
    else if (subject_requested) snprintf(subject_field,sizeof(subject_field),
        ",\"native_subject_terms\":%s",
        release_subject_requested?release_subject_json:transfer_subject_json);
    char* combined_core_json=nullptr;
    const char* core_json_output=core_request?core.json:
        revoke_core_request?revoke_core.json:"null";
    if (combined_core) {
        const size_t combined_capacity=2u*peace_core_json_capacity+128u;
        combined_core_json=static_cast<char*>(HeapAlloc(GetProcessHeap(),0,
            combined_capacity));
        if (!combined_core_json) {
            alliance_query_failure(id,"QUERY_PEACE_CORE_OUTPUT_BUFFER_UNAVAILABLE"); return;
        }
        const int combined_written=snprintf(combined_core_json,combined_capacity,
            "{\"return_core\":%s,\"revoke_core\":%s}",
            core_request?core.json:"null",revoke_core_request?revoke_core.json:"null");
        if (combined_written<0 || static_cast<size_t>(combined_written)>=combined_capacity) {
            HeapFree(GetProcessHeap(),0,combined_core_json);
            alliance_query_failure(id,"QUERY_PEACE_CORE_OUTPUT_CAPACITY_EXCEEDED"); return;
        }
        core_json_output=combined_core_json;
    }
    const int written=snprintf(message.text,message.capacity,
        "{\"event\":\"%s\",\"family\":\"peace\",\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"action_id\":\"%s\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"initiate\",\"date_raw\":%d,\"war_id\":\"%s\",\"direction\":\"%s\",\"direction_raw\":%u,\"direction_semantics_verified\":false,\"identity_scope\":\"observer_session\",\"query_complete\":true,\"native_offer_inspected\":true,\"pair_at_war\":true,\"unique_shared_war\":true,\"offer_constructed\":true,\"action_constructed\":true,\"offer_identity_verified\":true,\"participant_copy_verified\":true,\"object_unchanged\":true,\"cleanup_verified\":true,\"validity_called\":true,\"native_validity\":%s,\"common_gate_checked\":true,\"common_action_gate\":%s,\"initiation_gate_checked\":true,\"initiation_gate\":%s,\"diplomat_context_readable\":true,\"diplomat_required\":%s,\"available_diplomat_count\":%u,\"diplomat_assignment_verified\":false,\"native_diagnostic_hex\":\"%s\",\"diagnostic_readable\":%s,\"diagnostic_truncated\":%s,\"common_diagnostic_hex\":\"%s\",\"common_diagnostic_readable\":%s,\"common_diagnostic_truncated\":%s,\"send_diagnostic_hex\":\"%s\",\"send_diagnostic_readable\":%s,\"send_diagnostic_truncated\":%s,\"native_wrapper_gate_checked\":%s,\"native_wrapper_gate\":%s,\"wrapper_identity_verified\":%s,\"wrapper_payload_unchanged\":%s,\"full_rules_complete\":%s,\"reasons_complete\":false,\"submitted\":false,\"native_evaluation\":%s,\"native_money\":%s,\"native_war_context\":%s,\"native_payload\":%s,\"native_provinces\":%s%s,\"native_core_terms\":%s%s%s%s%s%s%s%s,\"native_consequences\":%s,\"frame_thread\":%lu}\n",
        country_family_output?"native_peace_combined_country_offer_query":combined_subject_requested?"native_peace_combined_subject_offer_query":subject_requested?"native_peace_subject_offer_query":combined_core?"native_peace_combined_core_offer_query":core_requested?"native_peace_core_offer_query":special_requested?"native_peace_special_offer_inspection":annul_requested?"native_peace_annul_treaties_offer_inspection":concede_requested?"native_peace_concede_defeat_offer_inspection":trade_power_requested?"native_peace_trade_power_offer_inspection":reparations_requested?"native_peace_reparations_offer_inspection":combined?"native_peace_combined_offer_inspection":provinces_requested?"native_peace_province_offer_inspection":money_requested?"native_peace_money_offer_inspection":"native_peace_empty_offer_inspection",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
        id,primary_action?primary_action:provinces_requested?"cede_province":money_requested?"demand_ducats":"white_peace",actor_tag,recipient_tag,date,war_id,demand?"demand":"offer",static_cast<unsigned>(demand?1u:0u),valid?"true":"false",common?"true":"false",send?"true":"false",diplomat_required?"true":"false",available_diplomats,
        diagnostic_hex,readable?"true":"false",truncated?"true":"false",
        common_hex,common_readable?"true":"false",common_truncated?"true":"false",
        send_hex,send_readable?"true":"false",send_truncated?"true":"false",
        wrapper_rule.checked?"true":"false",wrapper_rule.available?"true":"false",
        wrapper_rule.identity_verified?"true":"false",wrapper_rule.payload_unchanged?"true":"false",
        wrapper_rule.complete() && (!reparations_requested || reparations.rule_checked)
            && (!trade_power_requested || trade_power.rule_checked)
            && (!concede_requested || concede.rule_checked)
            && (!annul_requested || annul.rules.rule_checked)
            && special.rules_complete()
            && (!core_request || (core.selection_records_complete
                && core.action_copy_matched))
            && (!revoke_core_request || (revoke_core.selection_records_complete
                && revoke_core.action_copy_matched))
            && (!release_subject_requested || release_subject.outer_complete())
            && (!transfer_subject_requested || transfer_subject.outer_complete())
            && (!selected_rules_requested || selected_rules.complete())?"true":"false",evaluation,money_json,
        war_json,payload_json,provinces_requested?provinces.json:"null",base_term_fields,
        core_json_output,subject_field,country_field_key,country_field_value,
        annex_field_key,annex_field_value,
        selected_rules_key,selected_rules_value,
        consequences.json,static_cast<unsigned long>(GetCurrentThreadId()));
    if (written<0 || static_cast<size_t>(written)>=message.capacity) {
        if (combined_core_json) HeapFree(GetProcessHeap(),0,combined_core_json);
        alliance_query_failure(id,"QUERY_PEACE_OUTPUT_CAPACITY_EXCEEDED"); return;
    }
    line(message.text);
    if (combined_core_json) HeapFree(GetProcessHeap(),0,combined_core_json);
}
