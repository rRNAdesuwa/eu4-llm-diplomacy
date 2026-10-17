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
    explicit PeaceOfferQueryMessage(bool provinces) noexcept
        : capacity(74000+(provinces?peace_province_json_capacity:0)) {
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
    const char* primary_action=nullptr) noexcept {
    const bool money_requested=money_amount>=0;
    const bool provinces_requested=province_request!=nullptr;
    const bool combined=money_requested && provinces_requested;
    PeaceProvinceQueryData provinces(provinces_requested);
    provinces.expected_direction=demand?1u:0u;
    PeaceOfferQueryMessage message(provinces_requested);
    if (!provinces.valid() || !message.text) {
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
    static constexpr uintptr_t slots[]={0,0x80,0x88,0x90};
    static constexpr uintptr_t methods[]={0x598b90,0x59b480,0x59b660,0x59b900};
    for (unsigned i=0;i<4;++i) {
        uintptr_t method=0;
        if (!read(base+0x1c7b840+slots[i],method)
            || (method!=base+methods[i]
                && !(i==0 && method==reinterpret_cast<uintptr_t>(&lifecycle_destructor_observe)
                    && lifecycle_peace_destructor_original==reinterpret_cast<LifecycleDestructorMethod>(base+methods[i])))) {
            alliance_query_failure(id,"QUERY_PEACE_METHOD_IDENTITY_CHANGED"); return;
        }
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
                && provinces.selection_copy_verified));
    if (!identity) {
        reinterpret_cast<ActionDtor>(base+0x598b90)(action,0);
        reinterpret_cast<OfferDtor>(base+0x976030)(offer);
        alliance_query_failure(id,"QUERY_PEACE_ACTION_IDENTITY_CHANGED"); return;
    }
    PeaceWarOfferContextCapture war_context{};
    if (!peace_war_capture_offer_context(action+0x48,actor,recipient,war_context,demand)
        || war_context.native_war_context!=selected->native_reference) {
        reinterpret_cast<ActionDtor>(base+0x598b90)(action,0);
        reinterpret_cast<OfferDtor>(base+0x976030)(offer);
        alliance_query_failure(id,"QUERY_PEACE_WAR_CONTEXT_UNAVAILABLE"); return;
    }
    char war_json[8192]{},war_private[2048]{},private_session[80]{};
    snprintf(private_session,sizeof(private_session),"%lu-%llx",
        static_cast<unsigned long>(GetCurrentProcessId()),
        static_cast<unsigned long long>(observation_creation));
    if (!peace_war_offer_context_public_json(war_context,war_json,sizeof(war_json))
        || !peace_war_offer_context_private_json(war_context,private_session,id,
            war_private,sizeof(war_private))) {
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
        && (recipient&0xffffffu)!=0x415246u
        && (recipient&0xffffffu)!=0x524f50u,evaluation);
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
    if (provinces_requested) {
        if (!peace_province_query_json(provinces)) {
            alliance_query_failure(id,"QUERY_PEACE_PROVINCE_OUTPUT_FAILED"); return;
        }
        peace_province_query_private(id,provinces);
    }
    line(war_private);
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
    const int written=snprintf(message.text,message.capacity,
        "{\"event\":\"%s\",\"family\":\"peace\",\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"action_id\":\"%s\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"initiate\",\"date_raw\":%d,\"war_id\":\"%s\",\"direction\":\"%s\",\"direction_raw\":%u,\"direction_semantics_verified\":false,\"identity_scope\":\"observer_session\",\"query_complete\":true,\"native_offer_inspected\":true,\"pair_at_war\":true,\"unique_shared_war\":true,\"offer_constructed\":true,\"action_constructed\":true,\"offer_identity_verified\":true,\"participant_copy_verified\":true,\"object_unchanged\":true,\"cleanup_verified\":true,\"validity_called\":true,\"native_validity\":%s,\"common_gate_checked\":true,\"common_action_gate\":%s,\"initiation_gate_checked\":true,\"initiation_gate\":%s,\"native_diagnostic_hex\":\"%s\",\"diagnostic_readable\":%s,\"diagnostic_truncated\":%s,\"common_diagnostic_hex\":\"%s\",\"common_diagnostic_readable\":%s,\"common_diagnostic_truncated\":%s,\"send_diagnostic_hex\":\"%s\",\"send_diagnostic_readable\":%s,\"send_diagnostic_truncated\":%s,\"native_wrapper_gate_checked\":%s,\"native_wrapper_gate\":%s,\"wrapper_identity_verified\":%s,\"wrapper_payload_unchanged\":%s,\"full_rules_complete\":%s,\"reasons_complete\":false,\"submitted\":false,\"native_evaluation\":%s,\"native_money\":%s,\"native_war_context\":%s,\"native_payload\":%s,\"native_provinces\":%s,\"frame_thread\":%lu}\n",
        combined?"native_peace_combined_offer_inspection":provinces_requested?"native_peace_province_offer_inspection":money_requested?"native_peace_money_offer_inspection":"native_peace_empty_offer_inspection",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
        id,primary_action?primary_action:provinces_requested?"cede_province":money_requested?"demand_ducats":"white_peace",actor_tag,recipient_tag,date,war_id,demand?"demand":"offer",static_cast<unsigned>(demand?1u:0u),valid?"true":"false",common?"true":"false",send?"true":"false",
        diagnostic_hex,readable?"true":"false",truncated?"true":"false",
        common_hex,common_readable?"true":"false",common_truncated?"true":"false",
        send_hex,send_readable?"true":"false",send_truncated?"true":"false",
        wrapper_rule.checked?"true":"false",wrapper_rule.available?"true":"false",
        wrapper_rule.identity_verified?"true":"false",wrapper_rule.payload_unchanged?"true":"false",
        wrapper_rule.complete()?"true":"false",evaluation,money_json,
        war_json,payload_json,provinces_requested?provinces.json:"null",
        static_cast<unsigned long>(GetCurrentThreadId()));
    if (written<0 || static_cast<size_t>(written)>=message.capacity) {
        alliance_query_failure(id,"QUERY_PEACE_OUTPUT_CAPACITY_EXCEEDED"); return;
    }
    line(message.text);
}
