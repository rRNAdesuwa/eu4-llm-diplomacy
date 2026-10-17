// Fresh native offer construction shared by execution preparation and the
// operator's ungranted-entry fixtures. Placement objects never escape; the
// native wrapper owns its own clone of the completed action.
struct PeacePreparedAction {
    alignas(16) unsigned char offer[0x1c0]{};
    alignas(16) unsigned char action[0x210]{};
    bool offer_constructed=false,action_constructed=false;
    bool native_validity=false,common_gate=false,send_gate=false;
    PeaceWrapperRuleCapture wrapper_rule{};
    uint64_t actor=0,recipient=0;
    int32_t date=0;
    uintptr_t dispatcher=0;
    char war_id[30]{};
    ProtocolWrapperShape source{};
    void* wrapper=nullptr;

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
    bool require_available,bool demand=true) noexcept {
    uintptr_t game=0,actor_country=0,recipient_country=0;
    uint64_t player=0;
    if (!read(base+0x233fe58,game) || !read(game+0x1dd0,prepared.date)
        || !read(game+0x1e60,player) || (player&0xffffffu)!=0x524f50u
        || !alliance_query_country(actor_tag,prepared.actor)
        || !alliance_query_country(recipient_tag,prepared.recipient)
        || prepared.actor==prepared.recipient
        || !peace_query_country_pointer(prepared.actor,actor_country)
        || !peace_query_country_pointer(prepared.recipient,recipient_country)) return false;
    const PeaceWarRegistryEntry* selected=nullptr;
    for (unsigned i=0;i<peace_war_registry_size;++i)
        if (!strcmp(peace_war_registry[i].public_id,war_id)) selected=&peace_war_registry[i];
    PeaceWarReferenceList left{},right{};
    if (!selected || !peace_query_pair_references(actor_country,
            static_cast<unsigned>((prepared.recipient>>32)&0xffffu),left)
        || !peace_query_pair_references(recipient_country,
            static_cast<unsigned>((prepared.actor>>32)&0xffffu),right)
        || !peace_query_reference_sets_equal(left,right) || left.count!=1
        || left.references[0]!=selected->native_reference) return false;
    std::memcpy(prepared.war_id,selected->public_id,sizeof(prepared.war_id));
    static constexpr uintptr_t offsets[]={0x80,0x88,0x90};
    static constexpr uintptr_t methods[]={0x59b480,0x59b660,0x59b900};
    for (unsigned i=0;i<3;++i) {
        uintptr_t actual=0;
        if (!read(base+lifecycle_peace_vtable_rva+offsets[i],actual)
            || actual!=base+methods[i]) return false;
    }
    using OfferCtor=void* (*)(void*,uint64_t,uint64_t,unsigned char);
    using ActionCtor=void* (*)(void*,uint64_t,uint64_t,unsigned char,const void*,int32_t);
    if (reinterpret_cast<OfferCtor>(base+0x975bb0)(prepared.offer,
        peace_offer_claimant(prepared.actor,prepared.recipient,demand),
        peace_offer_payer(prepared.actor,prepared.recipient,demand),
        demand?1u:0u)!=prepared.offer) return false;
    prepared.offer_constructed=true;
    PeaceOfferParticipants participants{};
    if (!peace_empty_query_offer(prepared.offer,prepared.actor,prepared.recipient,participants,demand))
        return false;
    PeaceMoneyQuery money{};
    if (amount_raw>=0 && (!peace_money_query_prepare(prepared.offer,amount_raw,money)
        || !money.source_matches)) return false;
    PeaceProvinceQueryData provinces(province_request!=nullptr);
    if (province_request && (!provinces.valid()
        || !peace_province_query_prepare(prepared.offer,*province_request,provinces,demand)
        || !provinces.parameters_matched)) return false;
    bridge::peace_payload::PeacePayloadRef original_offer{};
    if (!peace_capture_offer_snapshot(prepared.offer,original_offer)) return false;
    if (reinterpret_cast<ActionCtor>(base+0x598b20)(prepared.action,prepared.actor,
        prepared.recipient,demand?1u:0u,prepared.offer,prepared.date)!=prepared.action) return false;
    prepared.action_constructed=true;
    if (!peace_empty_query_action(prepared.action,prepared.actor,prepared.recipient,prepared.date,demand)
        || (amount_raw>=0 && !peace_money_query_copy(prepared.action+0x48,money))
        || (province_request && (!peace_province_query_read_selection(prepared.action+0x48,provinces,PeaceProvinceSelectionRole::action_copy)
            || !provinces.selection_copy_verified))) return false;
    PeaceWarOfferContextCapture context{};
    if (!peace_war_capture_offer_context(prepared.action+0x48,prepared.actor,
            prepared.recipient,context,demand) || !context.complete
        || context.native_war_context!=selected->native_reference) return false;
    LifecycleActionShape expected=lifecycle_capture_shape(prepared.action);
    if (!expected.matched || !expected.peace_offer || !expected.peace.valid()
        || expected.peace.offer!=original_offer) return false;
    // Use the same initialized native diagnostic objects as the verified query.
    using Predicate=bool (*)(void*,void*,unsigned char);
    NativeShortString diagnostic{},common_text{},send_text{};
    diagnostic.capacity=common_text.capacity=send_text.capacity=15;
    prepared.native_validity=reinterpret_cast<Predicate>(base+0x59b480)(prepared.action,&diagnostic,0);
    prepared.common_gate=reinterpret_cast<Predicate>(base+0x59b660)(prepared.action,&common_text,0);
    prepared.send_gate=reinterpret_cast<Predicate>(base+0x59b900)(prepared.action,&send_text,0);
    using StringDtor=void (*)(void*);
    reinterpret_cast<StringDtor>(base+0x95660)(&send_text);
    reinterpret_cast<StringDtor>(base+0x95660)(&common_text);
    reinterpret_cast<StringDtor>(base+0x95660)(&diagnostic);
    if (require_available && (!prepared.native_validity || !prepared.common_gate || !prepared.send_gate))
        return false;
    const auto after=lifecycle_capture_shape(prepared.action);
    if (!protocol_shape_equal(expected,after)) return false;
    uintptr_t transport=0;
    if (!execution_world_dispatcher(prepared.dispatcher,transport) || !lifecycle_wrapper_original)
        return false;
    lifecycle_wrapper_observe(prepared.action,&prepared.wrapper);
    prepared.source=protocol_capture(prepared.wrapper);
    prepared.wrapper_rule=peace_wrapper_rule_inspect(prepared.wrapper);
    if (!prepared.wrapper_rule.complete()
        || (require_available && !prepared.wrapper_rule.available)) return false;
    return prepared.source.identity && prepared.source.readable
        && prepared.source.prefix_readable && prepared.source.payload.peace_offer
        && protocol_shape_equal(expected,prepared.source.payload);
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
