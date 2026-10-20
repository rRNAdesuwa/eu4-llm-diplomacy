// Bounded state readers and effect proofs for the immediate gift and
// great-power influence actions.  This include is shared by the query and
// execution paths; it deliberately exposes only fields established by the
// cached native effect/rule contracts.

struct GiftResourceState {
    bool complete=false;
    int32_t actor_treasury_raw=0;
    int32_t recipient_treasury_raw=0;
};

static bool gift_resource_capture(uint64_t actor,uint64_t recipient,
    GiftResourceState& state) noexcept {
    state=GiftResourceState{};
    uintptr_t source=0,target=0;
    if (!insult_query_country(actor,source)
        || !insult_query_country(recipient,target)
        || !read(source+0xbb0,state.actor_treasury_raw)
        || !read(target+0xbb0,state.recipient_treasury_raw)) return false;
    state.complete=true;
    return true;
}

static bool gift_resource_effect_matches(const GiftResourceState& before,
    const GiftResourceState& after,int32_t amount_raw,int32_t native_state) noexcept {
    if (!before.complete || !after.complete || amount_raw<=0 || native_state!=0)
        return false;
    const int64_t actor_expected=static_cast<int64_t>(before.actor_treasury_raw)-amount_raw;
    const int64_t recipient_expected=static_cast<int64_t>(before.recipient_treasury_raw)+amount_raw;
    return static_cast<int64_t>(after.actor_treasury_raw)==actor_expected
        && static_cast<int64_t>(after.recipient_treasury_raw)==recipient_expected;
}

static bool gift_resource_rejection_matches(const GiftResourceState& before,
    const GiftResourceState& after,int32_t native_state) noexcept {
    return before.complete && after.complete && native_state==1
        && before.actor_treasury_raw==after.actor_treasury_raw
        && before.recipient_treasury_raw==after.recipient_treasury_raw;
}

struct InfluenceResourceState {
    bool complete=false;
    int32_t actor_treasury_raw=0;
    int32_t recipient_treasury_raw=0;
    int32_t native_cost_raw=0;
    int32_t recipient_trust_raw=0;
    bool influencer_relation=false;
    int32_t opinion_raw=0;
    int32_t duration_months=0;
};

static bool influence_relation_row(uint64_t actor,uint64_t recipient,
    uintptr_t& source,uintptr_t& target,uintptr_t& row) noexcept {
    source=target=row=0;
    uint64_t other=0,rows=0;
    const unsigned slot=static_cast<unsigned>((actor>>32)&0xffffu);
    return insult_query_country(actor,source)
        && insult_query_country(recipient,target)
        && read(target+0x1510,rows) && rows
        && read(rows+static_cast<uintptr_t>(slot)*0x48+0x10,other)
        && other==actor
        && (row=rows+static_cast<uintptr_t>(slot)*0x48)!=0;
}

static bool influence_config(int32_t& opinion,int32_t& duration) noexcept {
    opinion=duration=0;
    uintptr_t global=0,config=0;
    return read(base+0x233fee8,global) && global
        && read(global+0xb68,config) && config
        && read(config+0x50,opinion) && read(config+0x54,duration)
        && duration>=0;
}

static bool influence_native_cost(uint64_t recipient,int32_t& cost_raw) noexcept {
    cost_raw=0;
    uintptr_t target=0;
    int32_t global_floor=0;
    if (!insult_query_country(recipient,target)
        || !read(base+0x233fc08,global_floor) || global_floor<0)
        return false;
    using IncomeReader=uint32_t* (*)(void*,uint32_t*);
    uint32_t income_local=0;
    uint32_t* returned=reinterpret_cast<IncomeReader>(base+0x339c40)(
        reinterpret_cast<void*>(target),&income_local);
    if (!returned) return false;
    uint32_t income=0;
    if (!read(reinterpret_cast<uintptr_t>(returned),income)) return false;
    const int64_t selected=income>static_cast<uint32_t>(global_floor)
        ?static_cast<int64_t>(income):static_cast<int64_t>(global_floor);
    const int64_t cost=selected*12;
    if (cost<0 || cost>2147483647ll) return false;
    cost_raw=static_cast<int32_t>(cost);
    return true;
}

static bool influence_influencer_contains(uintptr_t target,uint64_t actor,
    bool& contains) noexcept {
    contains=false;
    // +0xdc8 is the embedded vector itself: begin, end, capacity.  The
    // native effect takes RCX=&target[0xdc8], so treating begin as a second
    // pointer would reject empty vectors and dereference a handle as memory.
    uintptr_t begin=0,end=0,capacity=0;
    if (!read(target+0xdc8,begin) || !read(target+0xdd0,end)
        || !read(target+0xdd8,capacity) || end<begin || capacity<end
        || (end-begin)%8 || (end-begin)/8>4096
        || ((end==0) != (begin==0))) return false;
    for (uintptr_t cursor=begin;cursor<end;cursor+=8) {
        uint64_t value=0;
        if (!read(cursor,value)) return false;
        if (value==actor) { contains=true; break; }
    }
    return true;
}

static bool influence_resource_capture(uint64_t actor,uint64_t recipient,
    InfluenceResourceState& state) noexcept {
    state=InfluenceResourceState{};
    uintptr_t source=0,target=0,row=0;
    if (!influence_relation_row(actor,recipient,source,target,row)
        || !read(source+0xbb0,state.actor_treasury_raw)
        || !read(target+0xbb0,state.recipient_treasury_raw)) return false;
    unsigned char trust=0;
    if (!read(row+0x1e,trust)
        || !influence_native_cost(recipient,state.native_cost_raw)
        || !influence_config(state.opinion_raw,state.duration_months)
        || !influence_influencer_contains(target,actor,state.influencer_relation)) return false;
    state.recipient_trust_raw=static_cast<int32_t>(trust);
    if (state.recipient_trust_raw<0 || state.recipient_trust_raw>100) return false;
    state.complete=true;
    return true;
}

static bool influence_resource_effect_matches(
    const InfluenceResourceState& before,const InfluenceResourceState& after,
    int32_t native_state) noexcept {
    if (!before.complete || !after.complete || native_state!=0
        || before.native_cost_raw<0
        || after.native_cost_raw!=before.native_cost_raw
        || after.actor_treasury_raw!=static_cast<int64_t>(before.actor_treasury_raw)
            -before.native_cost_raw
        || after.recipient_treasury_raw!=before.recipient_treasury_raw
        || !after.influencer_relation) return false;
    const int32_t expected=before.recipient_trust_raw>=95
        ?100:before.recipient_trust_raw+5;
    return after.recipient_trust_raw==expected
        && after.opinion_raw==before.opinion_raw
        && after.duration_months==before.duration_months;
}

static bool influence_resource_rejection_matches(
    const InfluenceResourceState& before,const InfluenceResourceState& after,
    int32_t native_state) noexcept {
    return before.complete && after.complete && native_state==1
        && before.actor_treasury_raw==after.actor_treasury_raw
        && before.recipient_treasury_raw==after.recipient_treasury_raw
        && before.native_cost_raw==after.native_cost_raw
        && before.recipient_trust_raw==after.recipient_trust_raw
        && before.influencer_relation==after.influencer_relation
        && before.opinion_raw==after.opinion_raw
        && before.duration_months==after.duration_months;
}

static bool gift_influence_write_i32(uintptr_t address,int32_t value) noexcept {
    SIZE_T written=0;
    return address>=0x10000
        && WriteProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(address),
            &value,sizeof(value),&written) && written==sizeof(value);
}

static bool gift_influence_amount_valid(int32_t ducats,int32_t& raw) noexcept {
    raw=0;
    if (ducats<25 || ducats>2147475 || ducats%25!=0) return false;
    const int64_t value=static_cast<int64_t>(ducats)*1000;
    if (value>2147475000ll) return false;
    raw=static_cast<int32_t>(value);
    return true;
}

// Gift and influence are immediate actor actions.  They use the ordinary
// factory/visibility path, but are kept out of unilateral task inspection so
// a completed effect is never reported as a persistent task or a proposal.
static void gift_influence_query_run(const char* id,const char* action_id,
    const char* actor_tag,const char* recipient_tag,uint64_t actor,
    uint64_t recipient,int32_t date,bool gift,int32_t ducats) {
    const FactoryActionQueryMethods& family=gift?gift_query_methods:influence_query_methods;
    const uintptr_t vtable=base+family.vtable_rva;
    uintptr_t display=0,validity=0,send_gate=0,requires_diplomat=0;
    if (!read(vtable+0x88,display) || display!=base+family.display_rva
        || !read(vtable+0x80,validity) || validity!=base+family.validity_rva
        || !read(vtable+0x90,send_gate) || send_gate!=base+0x4e9b40
        || !read(vtable+family.diplomat_slot,requires_diplomat)
        || requires_diplomat!=base+family.diplomat_rva) {
        alliance_query_failure(id,"QUERY_GIFT_INFLUENCE_METHOD_IDENTITY_CHANGED"); return;
    }
    int32_t raw=0;
    if (gift && !gift_influence_amount_valid(ducats,raw)) {
        alliance_query_failure(id,"QUERY_GIFT_AMOUNT_INVALID"); return;
    }
    bool visible=false;
    if (!factory_query_visibility(actor,recipient,true,visible,family)) {
        alliance_query_failure(id,"QUERY_GIFT_INFLUENCE_UI_CONTEXT_UNAVAILABLE"); return;
    }
    unsigned available=0;
    if (!alliance_query_diplomats(actor,available)) {
        alliance_query_failure(id,"QUERY_GIFT_INFLUENCE_DIPLOMAT_CONTEXT_UNAVAILABLE"); return;
    }
    void* action=factory_query_create(actor,recipient,true,family);
    if (!action) {
        alliance_query_failure(id,"QUERY_GIFT_INFLUENCE_FACTORY_UNAVAILABLE"); return;
    }
    const uintptr_t action_address=reinterpret_cast<uintptr_t>(action);
    bool amount_binding_verified=!gift;
    if (gift) {
        amount_binding_verified=gift_influence_write_i32(action_address+0x40,raw);
        if (!amount_binding_verified) {
            reinterpret_cast<void* (*)(void*,unsigned)>(base+family.destructor_rva)(action,1);
            alliance_query_failure(id,"QUERY_GIFT_AMOUNT_BINDING_UNAVAILABLE"); return;
        }
        int32_t readback=0;
        amount_binding_verified=read(action_address+0x40,readback) && readback==raw;
    }
    using Predicate=bool (*)(void*,void*,unsigned char);
    NativeShortString diagnostic{}; diagnostic.capacity=15;
    NativeShortString tooltip{}; tooltip.capacity=15;
    observation_active_query=id;
    const bool common=reinterpret_cast<Predicate>(display)(action,nullptr,0);
    const bool native_valid=reinterpret_cast<Predicate>(validity)(action,&diagnostic,0);
    const bool initiation_gate=common;
    const bool tooltip_gate=reinterpret_cast<Predicate>(send_gate)(action,&tooltip,0);
    const bool needs_diplomat=reinterpret_cast<bool (*)(void*)>(requires_diplomat)(action);
    NativeShortString& selected=diagnostic.size?diagnostic:tooltip;
    const unsigned length=static_cast<unsigned>(selected.size<=512?selected.size:512);
    uintptr_t text_address=reinterpret_cast<uintptr_t>(selected.text);
    if (selected.capacity>=16) memcpy(&text_address,selected.text,8);
    unsigned char bytes[512]{}; char hex[1025]{}; SIZE_T copied=0;
    const bool diagnostic_readable=length==0 ||
        (selected.size<=65536 && selected.capacity<=131072
            && ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(text_address),
                bytes,length,&copied) && copied==length);
    if (diagnostic_readable)
        for (unsigned index=0;index<length;++index)
            snprintf(hex+index*2,3,"%02x",bytes[index]);
    const bool diagnostic_truncated=selected.size>512;
    reinterpret_cast<void (*)(void*)>(base+0x95660)(&diagnostic);
    reinterpret_cast<void (*)(void*)>(base+0x95660)(&tooltip);
    GiftResourceState gift_state{};
    InfluenceResourceState influence_state{};
    bool resource_complete=false;
    char resource_fields[1600]{};
    if (gift) {
        resource_complete=gift_resource_capture(actor,recipient,gift_state)
            && amount_binding_verified;
        snprintf(resource_fields,sizeof(resource_fields),
            "\"native_gift\":{\"kind\":\"gift\",\"ducats\":%d,"
            "\"amount_raw\":%d,\"amount_readable\":true,"
            "\"resource_scale\":1000,\"actor_treasury_raw\":%d,"
            "\"recipient_treasury_raw\":%d,\"complete\":%s},"
            "\"gift_amount_binding_verified\":%s,",
            ducats,raw,gift_state.actor_treasury_raw,gift_state.recipient_treasury_raw,
            resource_complete?"true":"false",
            amount_binding_verified?"true":"false");
    } else {
        resource_complete=influence_resource_capture(actor,recipient,influence_state);
        snprintf(resource_fields,sizeof(resource_fields),
            "\"native_influence\":{\"kind\":\"influence\","
            "\"opinion_raw\":%d,\"duration_months\":%d,"
            "\"cost_raw\":%d,\"complete\":%s},"
            "\"influence_state\":{\"actor_treasury_raw\":%d,"
            "\"recipient_treasury_raw\":%d,\"recipient_trust_raw\":%d,"
            "\"influencer_relation\":%s},",
            influence_state.opinion_raw,influence_state.duration_months,
            influence_state.native_cost_raw,resource_complete?"true":"false",
            influence_state.actor_treasury_raw,influence_state.recipient_treasury_raw,
            influence_state.recipient_trust_raw,
            influence_state.influencer_relation?"true":"false");
    }
    const bool complete=native_valid && amount_binding_verified && resource_complete;
    char message[4600];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_alliance_inspection\",\"session_id\":\"%lu-%llx\","
        "\"query_id\":\"%s\",\"action_id\":\"%s\",\"family\":\"%s\","
        "\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"initiate\","
        "\"date_raw\":%d,\"ui_selection_checked\":true,\"native_visibility\":%s,"
        "\"ui_enabled_gate_checked\":true,\"common_action_gate\":%s,"
        "\"display_predicate\":%s,\"initiation_gate\":%s,\"tooltip_gate\":%s,"
        "\"validity_called\":true,\"native_validity\":%s,"
        "\"native_diagnostic_hex\":\"%s\",\"diagnostic_readable\":%s,"
        "\"diagnostic_truncated\":%s,\"diplomat_context_readable\":true,"
        "\"diplomat_required\":%s,\"available_diplomat_count\":%u,"
        "%s\"native_variant\":1,\"acceptance_predicate_available\":false,"
        "\"native_would_accept\":false,\"score_applicable\":false,"
        "\"score_available\":false,\"native_total_raw\":0,"
        "\"acceptance_threshold_raw\":1,\"reason_container_readable\":false,"
        "\"reason_count\":0,\"reason_items_decoded\":false,\"full_rules_complete\":true,"
        "\"reasons_complete\":false,\"submitted\":false,\"complete\":%s,"
        "\"frame_thread\":%lu}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),
        static_cast<unsigned long long>(observation_creation),id,action_id,
        gift?"gift":"influence",actor_tag,recipient_tag,date,visible?"true":"false",
        common?"true":"false",common?"true":"false",initiation_gate?"true":"false",
        tooltip_gate?"true":"false",native_valid?"true":"false",hex,
        diagnostic_readable?"true":"false",diagnostic_truncated?"true":"false",
        needs_diplomat?"true":"false",available,resource_fields,complete?"true":"false",
        static_cast<unsigned long>(GetCurrentThreadId()));
    line(message);
    observation_active_query=nullptr;
    reinterpret_cast<void* (*)(void*,unsigned)>(base+family.destructor_rva)(action,1);
}

