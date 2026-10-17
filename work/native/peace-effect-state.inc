// Build-specific bounded observation of treaty consequences. The native
// engine performs all effects; these helpers read canonical identities and
// the confirmed treasury/owner/controller fields only.
using PeaceEffectState=bridge::peace_effects::State;

static bool execution_peace_effects_add_country(PeaceEffectState& state,uint64_t handle) noexcept {
    for (unsigned i=0;i<state.country_count;++i)
        if (state.countries[i].country==handle) return true;
    if (!handle || state.country_count>=bridge::peace_effects::kMaxCountries) return false;
    uintptr_t country=0; char tag[4]{}; int32_t treasury=0;
    if (!peace_query_country_pointer(handle,country) || !peace_province_tag_from_handle(handle,tag)
        || !read(country+0xbb0,treasury)) return false;
    state.countries[state.country_count++]={handle,treasury};
    return true;
}

static bool execution_peace_effects_read_province(int32_t id,
    bridge::peace_effects::ProvinceState& output) noexcept {
    PeaceProvinceArrayBounds bounds{}; uintptr_t record=0,owner=0,controller=0;
    uint64_t owner_handle=0,controller_handle=0;
    if (!peace_province_read_bounds(bounds) || !peace_province_record_for_id(bounds,id,record)
        || !read(record+0x468,owner_handle) || !read(record+0x470,controller_handle)
        || !peace_query_country_pointer(owner_handle,owner)
        || !peace_query_country_pointer(controller_handle,controller)) return false;
    output={id,owner_handle,controller_handle};
    return true;
}

static bool execution_peace_effects_capture(const AlliancePayload& payload,
    const bridge::peace_execution_wire::PeaceExecutionRequest& request,
    PeaceEffectState& output) noexcept {
    output=PeaceEffectState{};
    const auto* offer=payload.peace.offer.get();
    uintptr_t game=0;
    if (payload.family!=ActionFamily::peace || !payload.peace.valid() || !offer
        || !read(base+0x233fe58,game) || !read(game+0x1dd0,output.date_raw)
        || output.date_raw!=request.date_raw
        || !execution_peace_effects_add_country(output,payload.actor10)
        || !execution_peace_effects_add_country(output,payload.recipient20)) return false;
    for (const auto& group:offer->participants)
        for (unsigned i=0;i<group.count;++i)
            if (!execution_peace_effects_add_country(output,group.values[i])) return false;
    if (request.province_count>bridge::peace_effects::kMaxProvinces) return false;
    for (unsigned i=0;i<request.province_count;++i) {
        if (!execution_peace_effects_read_province(request.province_ids[i],output.provinces[i])) return false;
        ++output.province_count;
    }
    output.complete=true;
    return true;
}

static bool execution_peace_effects_after(const PeaceEffectState& before,
    PeaceEffectState& output) noexcept {
    output=PeaceEffectState{};
    uintptr_t game=0;
    if (!before.complete || !read(base+0x233fe58,game) || !read(game+0x1dd0,output.date_raw)) return false;
    for (unsigned i=0;i<before.country_count;++i)
        if (!execution_peace_effects_add_country(output,before.countries[i].country)) return false;
    for (unsigned i=0;i<before.province_count;++i) {
        if (!execution_peace_effects_read_province(before.provinces[i].id,output.provinces[i])) return false;
        ++output.province_count;
    }
    output.complete=true;
    return true;
}

struct PeaceEffectSummary {
    char json[20000]{};
    bool terms_verified=false;
};

static PeaceEffectSummary execution_peace_effects_json(const PeaceEffectState& before,
    const bridge::peace_execution_wire::PeaceExecutionRequest& request,bool settled) noexcept {
    PeaceEffectSummary result{};
    PeaceEffectState after{};
    const bool complete=execution_peace_effects_after(before,after);
    const bool same_date=complete && before.date_raw==after.date_raw;
    if (complete) for (unsigned i=0;i<before.country_count;++i) {
        char tag[4]{},observation[420]{};
        if (!peace_province_tag_from_handle(before.countries[i].country,tag)) continue;
        snprintf(observation,sizeof(observation),
            "{\"event\":\"native_peace_effect_observation\",\"private\":true,"
            "\"request_id\":\"%.64s\",\"country\":\"%.3s\",\"date_before\":%d,\"date_after\":%d,"
            "\"treasury_before_raw\":%d,\"treasury_after_raw\":%d,\"currency_scale\":1000}\n",
            request.request_id,tag,before.date_raw,after.date_raw,
            before.countries[i].treasury_raw,after.countries[i].treasury_raw);
        line(observation);
    }
    uint64_t actor=0,recipient=0,beneficiary=0;
    const bool endpoints=alliance_query_country(request.actor,actor)
        && alliance_query_country(request.recipient,recipient);
    const uint64_t payer=!strcmp(request.direction,"offer")?actor:recipient;
    const auto money=bridge::peace_effects::assess_money(before,after,payer,request.amount_raw);
    char money_json[14000]{},credits[13000]{},provinces[4400]{};
    size_t credit_used=0,province_used=0;
    bool json_complete=true;
    const auto append=[](char* destination,size_t capacity,size_t& used,const char* text) noexcept {
        const size_t length=strlen(text);
        if (used+length>=capacity) return false;
        memcpy(destination+used,text,length+1); used+=length; return true;
    };
    if (request.selected_amount) {
        unsigned credit_count=0;
        if (bridge::peace_effects::same_observation_context(before,after))
            for (unsigned i=0;i<before.country_count;++i) {
                const auto& left=before.countries[i];
                const int64_t delta=static_cast<int64_t>(after.countries[i].treasury_raw)-left.treasury_raw;
                if (left.country==payer || delta<=0) continue;
                char tag[4]{},row[90]{};
                if (!peace_province_tag_from_handle(left.country,tag)) { json_complete=false; break; }
                snprintf(row,sizeof(row),"%s{\"country\":\"%.3s\",\"amount_raw\":%lld}",
                    credit_count?",":"",tag,static_cast<long long>(delta));
                if (!append(credits,sizeof(credits),credit_used,row)) { json_complete=false; break; }
                ++credit_count;
            }
        snprintf(money_json,sizeof(money_json),
            "{\"amount_raw\":%d,\"payer\":\"%.3s\",\"paid_raw\":%lld,\"credits\":[%s],\"verified\":%s}",
            request.amount_raw,!strcmp(request.direction,"offer")?request.actor:request.recipient,
            static_cast<long long>(money.paid_raw),credits,
            settled && endpoints && money.verified && json_complete?"true":"false");
    } else strcpy(money_json,"null");
    bool provinces_verified=true;
    if (request.province_count && !alliance_query_country(request.beneficiary,beneficiary))
        provinces_verified=false;
    for (unsigned i=0;i<request.province_count;++i) {
        char owner_before[4]{},owner_after[4]{},control_before[4]{},control_after[4]{},row[350]{};
        const bool readable=complete && i<before.province_count && i<after.province_count
            && peace_province_tag_from_handle(before.provinces[i].owner,owner_before)
            && peace_province_tag_from_handle(after.provinces[i].owner,owner_after)
            && peace_province_tag_from_handle(before.provinces[i].controller,control_before)
            && peace_province_tag_from_handle(after.provinces[i].controller,control_after);
        const bool verified=readable && settled
            && bridge::peace_effects::province_transferred(before,after,i,beneficiary);
        provinces_verified=provinces_verified && verified;
        if (!readable) { json_complete=false; break; }
        snprintf(row,sizeof(row),
            "%s{\"province_id\":%d,\"beneficiary\":\"%.3s\",\"owner_before\":\"%.3s\",\"owner_after\":\"%.3s\","
            "\"controller_before\":\"%.3s\",\"controller_after\":\"%.3s\",\"verified\":%s}",
            i?",":"",request.province_ids[i],request.beneficiary,owner_before,owner_after,
            control_before,control_after,verified?"true":"false");
        if (!append(provinces,sizeof(provinces),province_used,row)) { json_complete=false; break; }
    }
    result.terms_verified=settled && endpoints && complete && same_date && json_complete
        && (!request.selected_amount || money.verified) && provinces_verified;
    snprintf(result.json,sizeof(result.json),
        "{\"complete\":%s,\"date_unchanged\":%s,\"currency_scale\":1000,\"money\":%s,\"provinces\":[%s]}",
        complete && json_complete?"true":"false",same_date?"true":"false",money_json,provinces);
    return result;
}
