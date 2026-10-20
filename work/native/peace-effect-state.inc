// Build-specific bounded observation of treaty consequences. The native
// engine performs all effects; these helpers read canonical identities and
// the confirmed treasury/owner/controller fields only.
#include <new>
using PeaceEffectState=bridge::peace_effects::State;

#include "peace-special-state.inc"

static bool execution_peace_effects_add_country(PeaceEffectState& state,uint64_t handle) noexcept {
    for (unsigned i=0;i<state.country_count;++i)
        if (state.countries[i].country==handle) return true;
    if (!handle || state.country_count>=bridge::peace_effects::kMaxCountries) return false;
    uintptr_t country=0; char tag[4]{}; int32_t treasury=0;
    if (!peace_query_country_pointer(handle,country) || !peace_province_tag_from_handle(handle,tag)
        || !read(country+0xbb0,treasury)) return false;
    auto& observation=state.countries[state.country_count++];
    observation.country=handle; observation.treasury_raw=treasury;
    observation.prestige_readable=read(country+0xcf8,observation.prestige_raw);
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

#include "peace-core-effects.inc"
#include "peace-subject-effects.inc"
#include "peace-country-effects.inc"

static bool execution_peace_effects_capture_annul(
    const bridge::peace_payload::PeaceOfferPayload& offer,
    const bridge::peace_execution_wire::PeaceExecutionRequest& request,int32_t date,
    PeaceEffectState& output) noexcept {
    const unsigned count=request.annul_partner_count;
    if (!request.selected_annul_treaties || !request.annul_country[0]
        || !count || count>bridge::peace_effects::kMaxAnnulPartners) return false;
    uint64_t country=0,partners[bridge::peace_effects::kMaxAnnulPartners]{};
    if (!alliance_query_country(request.annul_country,country) || !country) return false;
    for (unsigned i=0;i<count;++i) {
        if (!request.annul_partners[i][0]
            || !alliance_query_country(request.annul_partners[i],partners[i])
            || !partners[i] || partners[i]==country) return false;
        for (unsigned j=0;j<i;++j)
            if (partners[j]==partners[i]) return false;
        output.annul_treaties[i].country=country;
        output.annul_treaties[i].partner=partners[i];
    }
    bool matched[bridge::peace_effects::kMaxAnnulPartners]{};
    unsigned matches=0;
    for (unsigned i=0;i<offer.term_count;++i) {
        const auto& term=offer.terms[i];
        if (!term.selected || term.type_id!=0x2d2eu || term.bucket!=0x0eu) continue;
        if (!term.complete || term.field10!=offer.payer || term.field18!=offer.claimant
            || term.field22!=country) return false;
        unsigned index=count;
        for (unsigned j=0;j<count;++j)
            if (term.extra30==partners[j]) { index=j; break; }
        if (index==count || matched[index]) return false;
        matched[index]=true; ++matches;
    }
    if (matches!=count) return false;
    for (unsigned i=0;i<count;++i) {
        if (!matched[i] || !peace_annul_treaty_state_read(country,partners[i],date,
                output.annul_treaties[i])) return false;
    }
    output.annul_count=count;
    return true;
}

static bool execution_peace_effects_capture_core(
    const bridge::peace_payload::PeaceOfferPayload& offer,
    const bridge::peace_execution_wire::PeaceExecutionRequest& request,
    bool return_core,PeaceEffectState& output) noexcept {
    const bool selected=return_core?request.selected_return_core:request.selected_revoke_core;
    const unsigned count=return_core?request.return_core_count:request.revoke_core_count;
    const auto* ids=return_core?request.return_core_ids:request.revoke_core_ids;
    const char* owner_tag=return_core?request.return_core_owner:request.revoke_core_owner;
    auto& effect=return_core?output.return_core:output.revoke_core;
    bool& requested=return_core?output.return_core_requested:output.revoke_core_requested;
    effect=bridge::peace_effects::CoreEffectState{};
    requested=selected;
    effect.requested=selected;
    if (!selected) return true;
    if (!owner_tag[0] || !count || count>bridge::peace_effects::kMaxProvinces)
        return false;
    uint64_t target=0;
    if (!alliance_query_country(owner_tag,target) || !target) return false;
    unsigned selected_terms=0;
    const uint32_t expected_type=return_core?0x2e00u:0x2d26u;
    const uint32_t expected_bucket=return_core?5u:4u;
    for (unsigned i=0;i<offer.term_count;++i) {
        const auto& term=offer.terms[i];
        if (!term.selected || term.type_id!=expected_type || term.bucket!=expected_bucket)
            continue;
        if (!term.complete || term.field10!=offer.payer || term.field18!=offer.claimant)
            return false;
        const uint64_t term_target=return_core?term.extra30:term.field22;
        if (term_target!=target
            || (return_core && term.field22!=offer.payer)) return false;
        ++selected_terms;
    }
    if (selected_terms!=count) return false;
    for (unsigned i=0;i<count;++i) {
        if (ids[i]<=0) return false;
        for (unsigned j=0;j<i;++j)
            if (ids[j]==ids[i]) return false;
        if (!execution_peace_effects_read_core_province(ids[i],target,
                effect.rows[i])) return false;
    }
    effect.count=count;
    effect.complete=true;
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
    if (!execution_peace_effects_capture_special(payload,request,output)) return false;
    output.reparations_requested=request.selected_reparations;
    if (request.selected_reparations
        && !peace_reparations_state_read(offer->payer,offer->claimant,output.date_raw,
            output.reparations)) return false;
    output.trade_power_requested=request.selected_trade_power;
    if (request.selected_trade_power) {
        uint64_t source=0; unsigned matches=0;
        for (unsigned i=0;i<offer->term_count;++i) {
            const auto& term=offer->terms[i];
            if (!term.selected || term.type_id!=0x2e07u || term.bucket!=8u) continue;
            char source_tag[4]{},beneficiary_tag[4]{};
            if (!term.complete || term.field10!=offer->payer || term.field18!=offer->claimant
                || term.field22==offer->claimant
                || !peace_base_term_source_tag(term.field22,source_tag)
                || !peace_base_term_source_tag(term.field18,beneficiary_tag)
                || strcmp(source_tag,request.trade_power_source)
                || strcmp(beneficiary_tag,request.trade_power_beneficiary)) return false;
            source=term.field22; ++matches;
        }
        if (matches!=1 || !peace_trade_power_state_read(source,offer->claimant,output.date_raw,
            output.trade_power)) return false;
    }
    output.annul_treaties_requested=request.selected_annul_treaties;
    if (request.selected_annul_treaties
        && !execution_peace_effects_capture_annul(*offer,request,output.date_raw,output))
        return false;
    if (!execution_peace_effects_capture_core(*offer,request,true,output)
        || !execution_peace_effects_capture_core(*offer,request,false,output)) return false;
    if (!execution_peace_effects_capture_subject(*offer,request,false,output)
        || !execution_peace_effects_capture_subject(*offer,request,true,output)) return false;
    if (!execution_peace_effects_capture_country_terms(*offer,request,output)) return false;
    output.concede_defeat_requested=request.selected_concede_defeat;
    if (request.selected_concede_defeat) {
        unsigned matches=0;
        for (unsigned i=0;i<offer->term_count;++i) {
            const auto& term=offer->terms[i];
            if (!term.selected || term.type_id!=0x2d2du || term.bucket!=0x0bu) continue;
            if (!term.complete || term.field10!=offer->payer || term.field18!=offer->claimant
                || term.field22!=offer->payer) return false;
            ++matches;
        }
        if (matches!=1) return false;
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
    if (!execution_peace_effects_read_special_after(before,output)) return false;
    output.reparations_requested=before.reparations_requested;
    if (before.reparations_requested
        && !peace_reparations_state_read(before.reparations.payer,before.reparations.claimant,
            output.date_raw,output.reparations)) return false;
    output.trade_power_requested=before.trade_power_requested;
    output.concede_defeat_requested=before.concede_defeat_requested;
    output.annul_treaties_requested=before.annul_treaties_requested;
    output.annul_count=before.annul_count;
    output.return_core_requested=before.return_core_requested;
    output.revoke_core_requested=before.revoke_core_requested;
    output.release_subject_requested=before.release_subject_requested;
    output.transfer_subject_requested=before.transfer_subject_requested;
    if (before.return_core_requested) {
        output.return_core.requested=true;
        output.return_core.count=before.return_core.count;
        for (unsigned i=0;i<before.return_core.count;++i)
            if (!execution_peace_effects_read_core_province(
                    before.return_core.rows[i].province_id,
                    before.return_core.rows[i].target_core_owner,
                    output.return_core.rows[i])) return false;
        output.return_core.complete=true;
    }
    if (before.revoke_core_requested) {
        output.revoke_core.requested=true;
        output.revoke_core.count=before.revoke_core.count;
        for (unsigned i=0;i<before.revoke_core.count;++i)
            if (!execution_peace_effects_read_core_province(
                    before.revoke_core.rows[i].province_id,
                    before.revoke_core.rows[i].target_core_owner,
                    output.revoke_core.rows[i])) return false;
        output.revoke_core.complete=true;
    }
    if (before.trade_power_requested
        && !peace_trade_power_state_read(before.trade_power.source,before.trade_power.beneficiary,
            output.date_raw,output.trade_power)) return false;
    if (before.release_subject_requested
        && !execution_peace_effects_after_subject(before.release_subject,
            output.release_subject)) return false;
    if (before.transfer_subject_requested
        && !execution_peace_effects_after_subject(before.transfer_subject,
            output.transfer_subject)) return false;
    if (!execution_peace_effects_after_country_terms(before,output)) return false;
    if (before.annul_treaties_requested) {
        if (!before.annul_count || before.annul_count>bridge::peace_effects::kMaxAnnulPartners)
            return false;
        for (unsigned i=0;i<before.annul_count;++i)
            if (!peace_annul_treaty_state_read(before.annul_treaties[i].country,
                    before.annul_treaties[i].partner,output.date_raw,
                    output.annul_treaties[i])) return false;
    }
    output.complete=true;
    return true;
}

static constexpr std::size_t kPeaceEffectJsonCapacity=1400000u;

// A full country-term snapshot can contain 512 territory rows.  Keep that
// serialized text off the execution stack and make the result move-only so a
// failed allocation cannot be mistaken for an empty verified observation.
struct PeaceEffectSummary {
    char* json=nullptr;
    std::size_t capacity=0;
    bool terms_verified=false;

    PeaceEffectSummary() noexcept {
        json=new (std::nothrow) char[kPeaceEffectJsonCapacity]();
        capacity=json?kPeaceEffectJsonCapacity:0u;
    }
    PeaceEffectSummary(const PeaceEffectSummary&)=delete;
    PeaceEffectSummary& operator=(const PeaceEffectSummary&)=delete;
    PeaceEffectSummary(PeaceEffectSummary&& other) noexcept
        : json(other.json),capacity(other.capacity),terms_verified(other.terms_verified) {
        other.json=nullptr; other.capacity=0; other.terms_verified=false;
    }
    PeaceEffectSummary& operator=(PeaceEffectSummary&& other) noexcept {
        if (this==&other) return *this;
        delete[] json;
        json=other.json; capacity=other.capacity; terms_verified=other.terms_verified;
        other.json=nullptr; other.capacity=0; other.terms_verified=false;
        return *this;
    }
    ~PeaceEffectSummary() noexcept { delete[] json; }
    const char* text() const noexcept { return json?json:"null"; }
    const char* text() noexcept { return json?json:"null"; }
};

static PeaceEffectSummary execution_peace_effects_json(const PeaceEffectState& before,
    const bridge::peace_execution_wire::PeaceExecutionRequest& request,bool settled) noexcept {
    PeaceEffectSummary result{};
    PeaceEffectState after{};
    const bool complete=execution_peace_effects_after(before,after);
    const bool same_date=complete && before.date_raw==after.date_raw;
    if (complete) for (unsigned i=0;i<before.country_count;++i) {
        char tag[4]{},observation[650]{};
        if (!peace_province_tag_from_handle(before.countries[i].country,tag)) continue;
        snprintf(observation,sizeof(observation),
            "{\"event\":\"native_peace_effect_observation\",\"private\":true,"
            "\"request_id\":\"%.64s\",\"country\":\"%.3s\",\"date_before\":%d,\"date_after\":%d,"
            "\"treasury_before_raw\":%d,\"treasury_after_raw\":%d,\"currency_scale\":1000,"
            "\"prestige_before_raw\":%d,\"prestige_after_raw\":%d,\"prestige_scale\":1000,\"prestige_readable\":%s}\n",
            request.request_id,tag,before.date_raw,after.date_raw,
            before.countries[i].treasury_raw,after.countries[i].treasury_raw,
            before.countries[i].prestige_raw,after.countries[i].prestige_raw,
            before.countries[i].prestige_readable && after.countries[i].prestige_readable?"true":"false");
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
    const uint64_t claimant=!strcmp(request.direction,"offer")?recipient:actor;
    const bool reparations_verified=!request.selected_reparations
        || (settled && endpoints
            && bridge::peace_effects::reparations_established(before,after,payer,claimant));
    char reparations_json[500]="null";
    if (request.selected_reparations) snprintf(reparations_json,sizeof(reparations_json),
        "{\"payer\":\"%.3s\",\"claimant\":\"%.3s\",\"active_before\":%s,\"active_after\":%s,"
        "\"start_date_raw\":%d,\"end_date_raw\":%d,\"verified\":%s}",
        !strcmp(request.direction,"offer")?request.actor:request.recipient,
        !strcmp(request.direction,"offer")?request.recipient:request.actor,
        before.reparations.complete && before.reparations.active?"true":"false",
        after.reparations.complete && after.reparations.active?"true":"false",
        after.reparations.start_date_raw,after.reparations.end_date_raw,
        reparations_verified?"true":"false");
    const bool trade_power_verified=!request.selected_trade_power
        || (settled && endpoints
            && bridge::peace_effects::trade_power_established(before,after,
                before.trade_power.source,before.trade_power.beneficiary));
    char trade_power_json[650]="null",trade_power_fields[700]{};
    if (request.selected_trade_power) {
        snprintf(trade_power_json,sizeof(trade_power_json),
            "{\"source\":\"%.3s\",\"beneficiary\":\"%.3s\",\"present_before\":%s,\"present_after\":%s,"
            "\"start_date_raw\":%d,\"end_date_raw\":%d,\"amount_raw\":%d,\"amount_scale\":%d,\"peace_treaty\":%s,\"verified\":%s}",
            request.trade_power_source,request.trade_power_beneficiary,
            before.trade_power.complete && before.trade_power.present?"true":"false",
            after.trade_power.complete && after.trade_power.present?"true":"false",
            after.trade_power.start_date_raw,after.trade_power.end_date_raw,
            after.trade_power.amount_raw,after.trade_power.amount_scale,
            after.trade_power.peace_treaty?"true":"false",trade_power_verified?"true":"false");
        snprintf(trade_power_fields,sizeof(trade_power_fields),",\"transfer_trade_power\":%s",trade_power_json);
    }
    bool annul_complete=!request.selected_annul_treaties;
    bool annul_verified=!request.selected_annul_treaties;
    char annul_rows[9500]{},annul_fields[10000]{};
    size_t annul_used=0;
    if (request.selected_annul_treaties) {
        const bool annul_context_complete=complete && before.annul_treaties_requested
            && after.annul_treaties_requested
            && request.annul_partner_count>0
            && request.annul_partner_count<=bridge::peace_effects::kMaxAnnulPartners
            && before.annul_count==request.annul_partner_count
            && after.annul_count==request.annul_partner_count;
        annul_complete=annul_context_complete;
        annul_verified=annul_complete && settled && endpoints && same_date;
        for (unsigned i=0;i<request.annul_partner_count
                && i<bridge::peace_effects::kMaxAnnulPartners;++i) {
            const auto& before_row=before.annul_treaties[i];
            const auto& after_row=after.annul_treaties[i];
            const bool readable=annul_context_complete
                && bridge::peace_effects::annul_state_values_readable(before_row)
                && bridge::peace_effects::annul_state_values_readable(after_row);
            const bool verified=readable && settled && endpoints && same_date
                && bridge::peace_effects::annul_treaty_established(before_row,after_row,
                    after.date_raw);
            annul_complete=annul_complete && readable;
            annul_verified=annul_verified && verified;
            char row[520]{};
            snprintf(row,sizeof(row),
                "%s{\"country\":\"%.3s\",\"partner\":\"%.3s\","
                "\"present_before\":%s,\"present_after\":%s,"
                "\"start_date_raw\":%d,\"end_date_raw\":%d,"
                "\"alliance_before\":%s,\"alliance_after\":%s,"
                "\"values_readable\":%s,\"verified\":%s}",
                i?",":"",request.annul_country,request.annul_partners[i],
                before_row.present?"true":"false",after_row.present?"true":"false",
                after_row.start_date_raw,after_row.end_date_raw,
                before_row.alliance_present?"true":"false",
                after_row.alliance_present?"true":"false",readable?"true":"false",
                verified?"true":"false");
            if (!append(annul_rows,sizeof(annul_rows),annul_used,row)) {
                annul_complete=false; annul_verified=false; break;
            }
        }
        snprintf(annul_fields,sizeof(annul_fields),",\"annul_treaties\":[%s]",annul_rows);
    }
    bool humiliate_verified=!request.selected_humiliate_rival;
    bool show_strength_verified=!request.selected_show_strength;
    bool force_religion_verified=!request.selected_force_religion;
    bool humiliate_values_readable=!request.selected_humiliate_rival;
    bool show_strength_values_readable=!request.selected_show_strength;
    bool force_religion_values_readable=!request.selected_force_religion;
    char humiliate_fields[1700]{},show_strength_fields[2400]{},force_religion_fields[2500]{};
    if (request.selected_humiliate_rival) {
        const auto& before_row=before.humiliate_rival;
        const auto& after_row=after.humiliate_rival;
        humiliate_values_readable=bridge::peace_effects::humiliate_rival_values_readable(
            before_row) && bridge::peace_effects::humiliate_rival_values_readable(after_row);
        humiliate_verified=settled && endpoints
            && bridge::peace_effects::humiliate_rival_established(before,after,
                before.humiliate_rival_country,before.humiliate_rival_beneficiary);
        const char* country=before_row.country_tag[0]?before_row.country_tag:
            (request.demand_direction?request.recipient:request.actor);
        const char* beneficiary_tag=before_row.beneficiary_tag[0]?before_row.beneficiary_tag:
            (request.demand_direction?request.actor:request.recipient);
        const int written=snprintf(humiliate_fields,sizeof(humiliate_fields),
            ",\"humiliate_rival\":{\"country\":\"%.3s\",\"beneficiary\":\"%.3s\","
            "\"humiliated_before\":%s,\"humiliated_after\":%s,"
            "\"country_prestige_before_raw\":%d,\"country_prestige_after_raw\":%d,"
            "\"country_prestige_delta_raw\":%d,\"beneficiary_prestige_before_raw\":%d,"
            "\"beneficiary_prestige_after_raw\":%d,\"beneficiary_prestige_delta_raw\":%d,"
            "\"prestige_scale\":1000,\"values_readable\":%s,\"verified\":%s}",
            country,beneficiary_tag,before_row.humiliated?"true":"false",
            after_row.humiliated?"true":"false",before_row.country_prestige_raw,
            after_row.country_prestige_raw,after_row.country_prestige_raw-
                before_row.country_prestige_raw,before_row.beneficiary_prestige_raw,
            after_row.beneficiary_prestige_raw,after_row.beneficiary_prestige_raw-
                before_row.beneficiary_prestige_raw,humiliate_values_readable?"true":"false",
            humiliate_verified?"true":"false");
        if (written<0 || static_cast<size_t>(written)>=sizeof(humiliate_fields)) {
            json_complete=false; humiliate_fields[0]=0; humiliate_values_readable=false;
            humiliate_verified=false;
        }
    }
    if (request.selected_show_strength) {
        const auto& before_row=before.show_strength;
        const auto& after_row=after.show_strength;
        show_strength_values_readable=bridge::peace_effects::show_strength_values_readable(
            before_row) && bridge::peace_effects::show_strength_values_readable(after_row);
        show_strength_verified=settled && endpoints
            && bridge::peace_effects::show_strength_established(before,after,
                before.show_strength_country,before.show_strength_beneficiary);
        const char* country=before_row.country_tag[0]?before_row.country_tag:
            (request.demand_direction?request.recipient:request.actor);
        const char* beneficiary_tag=before_row.beneficiary_tag[0]?before_row.beneficiary_tag:
            (request.demand_direction?request.actor:request.recipient);
        const int written=snprintf(show_strength_fields,sizeof(show_strength_fields),
            ",\"show_strength\":{\"country\":\"%.3s\",\"beneficiary\":\"%.3s\","
            "\"humiliated_before\":%s,\"humiliated_after\":%s,"
            "\"country_prestige_before_raw\":%d,\"country_prestige_after_raw\":%d,"
            "\"country_prestige_delta_raw\":%d,\"beneficiary_prestige_before_raw\":%d,"
            "\"beneficiary_prestige_after_raw\":%d,\"beneficiary_prestige_delta_raw\":%d,"
            "\"prestige_scale\":1000,\"powers_before\":[%d,%d,%d],"
            "\"powers_after\":[%d,%d,%d],\"powers_delta\":[%d,%d,%d],"
            "\"powers_requested\":%d,\"values_readable\":%s,\"verified\":%s}",
            country,beneficiary_tag,before_row.humiliated?"true":"false",
            after_row.humiliated?"true":"false",before_row.country_prestige_raw,
            after_row.country_prestige_raw,after_row.country_prestige_raw-
                before_row.country_prestige_raw,before_row.beneficiary_prestige_raw,
            after_row.beneficiary_prestige_raw,after_row.beneficiary_prestige_raw-
                before_row.beneficiary_prestige_raw,before_row.powers[0],
            before_row.powers[1],before_row.powers[2],after_row.powers[0],
            after_row.powers[1],after_row.powers[2],after_row.powers[0]-before_row.powers[0],
            after_row.powers[1]-before_row.powers[1],after_row.powers[2]-before_row.powers[2],
            after_row.powers_requested,show_strength_values_readable?"true":"false",
            show_strength_verified?"true":"false");
        if (written<0 || static_cast<size_t>(written)>=sizeof(show_strength_fields)) {
            json_complete=false; show_strength_fields[0]=0; show_strength_values_readable=false;
            show_strength_verified=false;
        }
    }
    if (request.selected_force_religion) {
        const auto& before_row=before.force_religion;
        const auto& after_row=after.force_religion;
        force_religion_values_readable=bridge::peace_effects::force_religion_values_readable(
            before_row) && bridge::peace_effects::force_religion_values_readable(after_row);
        force_religion_verified=settled && endpoints
            && bridge::peace_effects::force_religion_established(before,after,
                before.force_religion_country,before.force_religion_beneficiary);
        const char* country=request.demand_direction?request.recipient:request.actor;
        const char* beneficiary_tag=request.demand_direction?request.actor:request.recipient;
        const int written=snprintf(force_religion_fields,sizeof(force_religion_fields),
            ",\"force_religion\":{\"country\":\"%.3s\",\"beneficiary\":\"%.3s\","
            "\"religion_before\":\"%.63s\",\"religion_after\":\"%.63s\","
            "\"beneficiary_religion_before\":\"%.63s\",\"beneficiary_religion_after\":\"%.63s\","
            "\"capital_religion_before\":\"%.63s\",\"capital_religion_after\":\"%.63s\","
            "\"values_readable\":%s,\"verified\":%s}",
            country,beneficiary_tag,before_row.religion,after_row.religion,
            before_row.beneficiary_religion,after_row.beneficiary_religion,
            before_row.capital_religion,after_row.capital_religion,
            force_religion_values_readable?"true":"false",
            force_religion_verified?"true":"false");
        if (written<0 || static_cast<size_t>(written)>=sizeof(force_religion_fields)) {
            json_complete=false; force_religion_fields[0]=0; force_religion_values_readable=false;
            force_religion_verified=false;
        }
    }
    bool core_complete=true;
    bool core_values_readable=true;
    bool core_verified=true;
    char core_fields[18000]{},core_rows[8500]{};
    size_t core_fields_used=0;
    const auto append_core_effect=[&](const char* key,
        const bridge::peace_effects::CoreEffectState& before_effect,
        const bridge::peace_effects::CoreEffectState& after_effect,
        bool return_core) noexcept {
        if (!before_effect.requested) return;
        bool effect_complete=complete && before_effect.complete && after_effect.complete
            && before_effect.count==after_effect.count
            && before_effect.count<=bridge::peace_effects::kMaxProvinces;
        bool effect_readable=effect_complete;
        bool effect_verified=effect_readable && settled && endpoints
            && bridge::peace_effects::core_effect_established(before,after,return_core);
        size_t rows_used=0;
        core_rows[0]=0;
        for (unsigned i=0;i<before_effect.count
                && i<bridge::peace_effects::kMaxProvinces;++i) {
            const auto& before_row=before_effect.rows[i];
            const auto& after_row=after_effect.rows[i];
            char target[4]{},owner_before[4]{},owner_after[4]{},control_before[4]{},control_after[4]{};
            const bool readable=effect_complete
                && bridge::peace_effects::core_effect_values_readable(before_row)
                && bridge::peace_effects::core_effect_values_readable(after_row)
                && peace_province_tag_from_handle(before_row.target_core_owner,target)
                && peace_province_tag_from_handle(before_row.owner,owner_before)
                && peace_province_tag_from_handle(after_row.owner,owner_after)
                && peace_province_tag_from_handle(before_row.controller,control_before)
                && peace_province_tag_from_handle(after_row.controller,control_after);
            effect_readable=effect_readable && readable;
            char row[700]{};
            const int written=snprintf(row,sizeof(row),
                "%s{\"province_id\":%d,\"target_core_owner\":\"%.3s\","
                "\"owner_before\":\"%.3s\",\"owner_after\":\"%.3s\","
                "\"controller_before\":\"%.3s\",\"controller_after\":\"%.3s\","
                "\"core_owner_present_before\":%s,\"core_owner_present_after\":%s,"
                "\"values_readable\":%s,\"verified\":%s}",
                i?",":"",before_row.province_id,target,owner_before,owner_after,
                control_before,control_after,before_row.core_owner_present?"true":"false",
                after_row.core_owner_present?"true":"false",readable?"true":"false",
                readable && effect_verified?"true":"false");
            if (written<0 || static_cast<size_t>(written)>=sizeof(row)
                || !append(core_rows,sizeof(core_rows),rows_used,row)) {
                effect_complete=false; effect_readable=false; effect_verified=false;
                break;
            }
        }
        char field[9000]{};
        const int written=snprintf(field,sizeof(field),",\"%s\":[%s]",key,core_rows);
        if (written<0 || static_cast<size_t>(written)>=sizeof(field)
            || !append(core_fields,sizeof(core_fields),core_fields_used,field)) {
            core_complete=false; core_values_readable=false; core_verified=false;
        } else {
            core_complete=core_complete && effect_complete;
            core_values_readable=core_values_readable && effect_readable;
            core_verified=core_verified && effect_verified;
        }
    };
    append_core_effect("return_core",before.return_core,after.return_core,true);
    append_core_effect("revoke_core",before.revoke_core,after.revoke_core,false);
    bool release_subject_complete=true,release_subject_readable=true;
    bool release_subject_verified=true;
    bool transfer_subject_complete=true,transfer_subject_readable=true;
    bool transfer_subject_verified=true;
    char subject_fields[30000]{},subject_rows[22000]{};
    size_t subject_fields_used=0;
    const auto append_subject_effect=[&](const char* key,
        const bridge::peace_effects::SubjectEffectState& before_effect,
        const bridge::peace_effects::SubjectEffectState& after_effect,
        bool transfer_subject) noexcept {
        if (!before_effect.requested) return;
        bool effect_complete=complete && before_effect.complete && after_effect.complete
            && before_effect.count==after_effect.count
            && before_effect.count<=bridge::peace_effects::kMaxSubjectCountries
            && bridge::peace_effects::subject_effect_context_valid(before_effect)
            && bridge::peace_effects::subject_effect_context_valid(after_effect);
        bool effect_readable=effect_complete;
        bool effect_verified=effect_readable && settled && endpoints
            && (transfer_subject
                ?bridge::peace_effects::transfer_subject_established(before,after)
                :bridge::peace_effects::release_subject_established(before,after));
        size_t rows_used=0; subject_rows[0]=0;
        for (unsigned i=0;i<before_effect.count
                && i<bridge::peace_effects::kMaxSubjectCountries;++i) {
            const auto& before_row=before_effect.rows[i];
            const auto& after_row=after_effect.rows[i];
            const bool readable=effect_complete
                && bridge::peace_effects::subject_relation_values_readable(before_row)
                && bridge::peace_effects::subject_relation_values_readable(after_row)
                && before_row.country==after_row.country
                && before_row.source==after_row.source
                && before_row.beneficiary==after_row.beneficiary;
            effect_readable=effect_readable && readable;
            char country[4]{},source[4]{},beneficiary_tag[4]{};
            const bool tags=readable
                && peace_province_tag_from_handle(before_row.country,country)
                && peace_province_tag_from_handle(before_row.source,source)
                && (!before_row.beneficiary
                    || peace_province_tag_from_handle(before_row.beneficiary,beneficiary_tag));
            char beneficiary_json[8]{};
            if (before_row.beneficiary)
                snprintf(beneficiary_json,sizeof(beneficiary_json),"\"%.3s\"",beneficiary_tag);
            else strcpy(beneficiary_json,"null");
            char source_type_before[70]{},source_type_after[70]{},
                beneficiary_type_before[70]{},beneficiary_type_after[70]{};
            snprintf(source_type_before,sizeof(source_type_before),
                before_row.source_subject_type[0]?"\"%.63s\"":"null",
                before_row.source_subject_type);
            snprintf(source_type_after,sizeof(source_type_after),
                after_row.source_subject_type[0]?"\"%.63s\"":"null",
                after_row.source_subject_type);
            snprintf(beneficiary_type_before,sizeof(beneficiary_type_before),
                before_row.beneficiary && before_row.beneficiary_subject_type[0]
                    ?"\"%.63s\"":"null",before_row.beneficiary_subject_type);
            snprintf(beneficiary_type_after,sizeof(beneficiary_type_after),
                after_row.beneficiary && after_row.beneficiary_subject_type[0]
                    ?"\"%.63s\"":"null",after_row.beneficiary_subject_type);
            const char* beneficiary_active_before=before_row.beneficiary
                ?(before_row.beneficiary_relation_active?"true":"false"):"null";
            const char* beneficiary_active_after=after_row.beneficiary
                ?(after_row.beneficiary_relation_active?"true":"false"):"null";
            const char* beneficiary_overlord_before=before_row.beneficiary
                ?(before_row.beneficiary_is_overlord?"true":"false"):"null";
            const char* beneficiary_overlord_after=after_row.beneficiary
                ?(after_row.beneficiary_is_overlord?"true":"false"):"null";
            char row[1150]{};
            const int written=snprintf(row,sizeof(row),
                "%s{\"country\":\"%.3s\",\"source\":\"%.3s\",\"beneficiary\":%s,"
                "\"source_relation_active_before\":%s,\"source_relation_active_after\":%s,"
                "\"source_is_overlord_before\":%s,\"source_is_overlord_after\":%s,"
                "\"source_subject_type_before\":%s,\"source_subject_type_after\":%s,"
                "\"beneficiary_relation_active_before\":%s,\"beneficiary_relation_active_after\":%s,"
                "\"beneficiary_is_overlord_before\":%s,\"beneficiary_is_overlord_after\":%s,"
                "\"beneficiary_subject_type_before\":%s,\"beneficiary_subject_type_after\":%s,"
                "\"source_relation_active\":%s,\"source_is_overlord\":%s,"
                "\"source_subject_type\":%s,\"beneficiary_relation_active\":%s,"
                "\"beneficiary_is_overlord\":%s,\"beneficiary_subject_type\":%s,"
                "\"complete\":%s,\"values_readable\":%s,\"verified\":%s}",
                i?",":"",country,source,beneficiary_json,
                before_row.source_relation_active?"true":"false",
                after_row.source_relation_active?"true":"false",
                before_row.source_is_overlord?"true":"false",
                after_row.source_is_overlord?"true":"false",source_type_before,source_type_after,
                beneficiary_active_before,beneficiary_active_after,
                beneficiary_overlord_before,beneficiary_overlord_after,
                beneficiary_type_before,beneficiary_type_after,
                after_row.source_relation_active?"true":"false",
                after_row.source_is_overlord?"true":"false",source_type_after,
                beneficiary_active_after,beneficiary_overlord_after,beneficiary_type_after,
                readable && tags?"true":"false",readable && tags?"true":"false",
                readable && tags && effect_verified?"true":"false");
            if (!readable || !tags || written<0 || static_cast<size_t>(written)>=sizeof(row)
                || !append(subject_rows,sizeof(subject_rows),rows_used,row)) {
                effect_complete=false; effect_readable=false; effect_verified=false; break;
            }
        }
        const bool unchanged=bridge::peace_effects::subject_effect_exactly_equal(
            before_effect,after_effect);
        char field[26000]{};
        const int written=snprintf(field,sizeof(field),
            ",\"%s\":{\"requested\":true,\"count\":%u,\"complete\":%s,"
            "\"rows\":[%s],\"unchanged\":%s,\"verified\":%s}",key,
            before_effect.count,effect_complete?"true":"false",subject_rows,
            unchanged?"true":"false",effect_verified?"true":"false");
        if (written<0 || static_cast<size_t>(written)>=sizeof(field)
            || !append(subject_fields,sizeof(subject_fields),subject_fields_used,field)) {
            effect_complete=false; effect_readable=false; effect_verified=false;
        }
        if (transfer_subject) {
            transfer_subject_complete=transfer_subject_complete && effect_complete;
            transfer_subject_readable=transfer_subject_readable && effect_readable;
            transfer_subject_verified=transfer_subject_verified && effect_verified;
        } else {
            release_subject_complete=release_subject_complete && effect_complete;
            release_subject_readable=release_subject_readable && effect_readable;
            release_subject_verified=release_subject_verified && effect_verified;
        }
    };
    append_subject_effect("release_subject",before.release_subject,after.release_subject,false);
    append_subject_effect("transfer_subject",before.transfer_subject,after.transfer_subject,true);
    const auto prestige=bridge::peace_effects::assess_prestige(before,after,payer,claimant);
    char concede_fields[1050]{};
    if (request.selected_concede_defeat) {
        snprintf(concede_fields,sizeof(concede_fields),
            ",\"concede_defeat\":{\"conceding_country\":\"%.3s\",\"beneficiary\":\"%.3s\","
            "\"conceding_prestige_before_raw\":%d,\"conceding_prestige_after_raw\":%d,\"conceding_prestige_delta_raw\":%d,"
            "\"beneficiary_prestige_before_raw\":%d,\"beneficiary_prestige_after_raw\":%d,\"beneficiary_prestige_delta_raw\":%d,"
            "\"prestige_scale\":1000,\"values_readable\":%s,\"verified\":%s}",
            request.demand_direction?request.recipient:request.actor,
            request.demand_direction?request.actor:request.recipient,
            prestige.conceding_before,prestige.conceding_after,
            prestige.conceding_after-prestige.conceding_before,
            prestige.beneficiary_before,prestige.beneficiary_after,
            prestige.beneficiary_after-prestige.beneficiary_before,
            prestige.readable?"true":"false",settled && prestige.readable?"true":"false");
    }
    const bool country_terms_requested=bridge::peace_effects::country_terms_any_requested(before);
    bool country_terms_complete=true;
    bool country_terms_readable=true;
    bool country_terms_verified=!country_terms_requested;
    if (country_terms_requested) {
        if (before.release_nation_requested) {
            country_terms_complete=country_terms_complete
                && before.release_nation.complete && after.release_nation.complete;
            country_terms_readable=country_terms_readable
                && before.release_nation.values_readable && after.release_nation.values_readable;
        }
        if (before.force_vassalization_requested) {
            country_terms_complete=country_terms_complete
                && before.force_vassalization.complete && after.force_vassalization.complete;
            country_terms_readable=country_terms_readable
                && before.force_vassalization.values_readable
                && after.force_vassalization.values_readable;
        }
        if (before.form_personal_union_requested) {
            country_terms_complete=country_terms_complete
                && before.form_personal_union.complete && after.form_personal_union.complete;
            country_terms_readable=country_terms_readable
                && before.form_personal_union.values_readable
                && after.form_personal_union.values_readable;
        }
        if (before.grant_independence_requested) {
            country_terms_complete=country_terms_complete
                && before.grant_independence.complete && after.grant_independence.complete;
            country_terms_readable=country_terms_readable
                && before.grant_independence.values_readable
                && after.grant_independence.values_readable;
            country_terms_verified=false;
        }
        if (before.full_annexation_requested) {
            country_terms_complete=country_terms_complete
                && before.full_annexation.complete && after.full_annexation.complete;
            country_terms_readable=country_terms_readable
                && before.full_annexation.values_readable && after.full_annexation.values_readable;
        }
        country_terms_verified=settled && endpoints && country_terms_complete
            && country_terms_readable
            && (!before.release_nation_requested
                || bridge::peace_effects::release_nation_established(before,after))
            && (!before.force_vassalization_requested
                || bridge::peace_effects::force_vassalization_established(before,after))
            && (!before.form_personal_union_requested
                || bridge::peace_effects::form_personal_union_established(before,after))
            && (!before.grant_independence_requested
                || bridge::peace_effects::grant_independence_established(before,after))
            && (!before.full_annexation_requested
                || bridge::peace_effects::full_annexation_established(before,after));
    }
    result.terms_verified=settled && endpoints && complete && same_date && json_complete
        && (!request.selected_amount || money.verified) && provinces_verified && reparations_verified && trade_power_verified
        && (!request.selected_concede_defeat || prestige.readable) && annul_verified
        && (!request.selected_humiliate_rival || humiliate_verified)
        && (!request.selected_show_strength || show_strength_verified)
        && (!request.selected_force_religion || force_religion_verified)
        && core_verified && release_subject_verified && transfer_subject_verified
        && country_terms_verified;
    if (!result.json || !result.capacity) return result;
    const int base_written=snprintf(result.json,result.capacity,
        "{\"complete\":%s,\"date_unchanged\":%s,\"currency_scale\":1000,\"money\":%s,\"provinces\":[%s],\"war_reparations\":%s%s%s%s%s%s%s%s%s",
        complete && json_complete && annul_complete
            && (!request.selected_concede_defeat || prestige.readable)
            && humiliate_values_readable && show_strength_values_readable
            && force_religion_values_readable && core_complete && core_values_readable
            && release_subject_complete && release_subject_readable
            && transfer_subject_complete && transfer_subject_readable
            && country_terms_complete && country_terms_readable?"true":"false",
        same_date?"true":"false",money_json,provinces,reparations_json,
        trade_power_fields,annul_fields,concede_fields,humiliate_fields,
        show_strength_fields,force_religion_fields,subject_fields,core_fields);
    if (base_written<0 || static_cast<std::size_t>(base_written)>=result.capacity) {
        result.json[0]=0; result.terms_verified=false; return result;
    }
    std::size_t json_used=static_cast<std::size_t>(base_written);
    bool appended_complete=true,appended_readable=true,appended_verified=true;
    if (!execution_peace_effects_country_terms_json_append(result.json,result.capacity,
            json_used,before,after,settled,endpoints,appended_complete,
            appended_readable,appended_verified)
        || json_used+2u>=result.capacity) {
        result.json[0]=0; result.terms_verified=false; return result;
    }
    result.json[json_used++]='}'; result.json[json_used]=0;
    result.terms_verified=result.terms_verified && appended_complete
        && appended_readable && appended_verified;
    return result;
}
