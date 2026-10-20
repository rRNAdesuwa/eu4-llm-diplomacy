// Effects for the five country-level peace terms introduced by EXEC10.
//
// This file only reads the selected typed terms and the established country,
// province, and subject endpoints.  It never constructs, selects, or
// dispatches a native offer.  The old 16-row province request remains a
// separate contract; country territory snapshots use the bounded 512-row
// array declared in peace-effects.h.

#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>

static constexpr std::uint32_t peace_effect_release_type=0x2d28u;
static constexpr std::uint32_t peace_effect_release_bucket=0x0fu;
static constexpr std::uint32_t peace_effect_force_type_a=0x2d2cu;
static constexpr std::uint32_t peace_effect_force_type_b=0x3c05u;
static constexpr std::uint32_t peace_effect_force_bucket_a=0x01u;
static constexpr std::uint32_t peace_effect_force_bucket_b=0x02u;
static constexpr std::uint32_t peace_effect_union_type=0x2d2au;
static constexpr std::uint32_t peace_effect_union_bucket=0x1au;
static constexpr std::uint32_t peace_effect_grant_type=0x2e4au;
static constexpr std::uint32_t peace_effect_grant_bucket=0x12u;
// Full Annexation is the all-province Cede selection: the same type-3 rows
// used by the bounded province helper, with nested_id as the province id.
static constexpr std::uint32_t peace_effect_annex_type=0x2d25u;
static constexpr std::uint32_t peace_effect_annex_bucket=0x03u;

static constexpr std::uintptr_t peace_effect_owned_begin_offset=0x1338u;
static constexpr std::uintptr_t peace_effect_owned_count_offset=0x1344u;
static constexpr std::uintptr_t peace_effect_release_core_chain_offset=0x1378u;

static bool peace_effect_country_tag(std::uint64_t handle,char (&output)[4]) noexcept {
    output[0]=0;
    return handle && peace_province_tag_from_handle(handle,output);
}

static bool peace_effect_read_country_record(std::uint64_t handle,
    std::uintptr_t& record) noexcept {
    return handle && peace_query_country_pointer(handle,record) && record;
}

static bool peace_effect_read_owned_count(std::uint64_t handle,
    std::uint32_t& count) noexcept {
    count=0;
    std::uintptr_t record=0;
    std::int32_t raw_count=0;
    if (!peace_effect_read_country_record(handle,record)
        || !read(record+peace_effect_owned_count_offset,raw_count)
        || raw_count<0 || static_cast<std::uint32_t>(raw_count)
            >bridge::peace_effects::kMaxCountryTermProvinces) return false;
    count=static_cast<std::uint32_t>(raw_count);
    return true;
}

static bool peace_effect_read_owned_ids(std::uint64_t handle,
    std::int32_t (&ids)[bridge::peace_effects::kMaxCountryTermProvinces],
    unsigned& count) noexcept {
    count=0;
    std::uintptr_t record=0,begin=0;
    std::int32_t raw_count=0;
    if (!peace_effect_read_country_record(handle,record)
        || !read(record+peace_effect_owned_begin_offset,begin)
        || !read(record+peace_effect_owned_count_offset,raw_count)
        || raw_count<0 || static_cast<std::uint32_t>(raw_count)
            >bridge::peace_effects::kMaxCountryTermProvinces)
        return false;
    if (raw_count && !begin) return false;
    count=static_cast<unsigned>(raw_count);
    for (unsigned i=0;i<count;++i) {
        if (!read(begin+static_cast<std::uintptr_t>(i)*sizeof(std::int32_t),ids[i])
            || ids[i]<=0) return false;
        for (unsigned j=0;j<i;++j)
            if (ids[j]==ids[i]) return false;
    }
    return true;
}

static bool peace_effect_read_country_term_row(std::int32_t province_id,
    bridge::peace_effects::CountryTermProvinceState& output) noexcept {
    output=bridge::peace_effects::CountryTermProvinceState{};
    bridge::peace_effects::ProvinceState row{};
    if (province_id<=0 || !execution_peace_effects_read_province(province_id,row))
        return false;
    output.province_id=row.id;
    output.owner=row.owner;
    output.controller=row.controller;
    output.complete=output.province_id>0 && output.owner && output.controller;
    return output.complete;
}

// Release Nation uses the target country's established core chain.  The
// chain nodes contain a province index at +0 and the next node at +0x10; only
// nodes whose current owner is the requested source are part of the effect
// snapshot.  The chain is bounded before any row is written.
static bool peace_effect_read_release_rows(std::uint64_t country,
    std::uint64_t source,bridge::peace_effects::CountryTerritoryEffectState& output)
    noexcept {
    std::uintptr_t record=0,node=0;
    if (!peace_effect_read_country_record(country,record)
        || !read(record+peace_effect_release_core_chain_offset,node)) return false;
    bool seen_any=false;
    unsigned steps=0;
    while (node) {
        if (++steps>bridge::peace_effects::kMaxCountryTermProvinces
            || output.count>=bridge::peace_effects::kMaxCountryTermProvinces) return false;
        std::int32_t province_id=0;
        std::uintptr_t next=0;
        if (!read(node,province_id) || !read(node+0x10u,next)
            || province_id<=0) return false;
        bridge::peace_effects::CountryTermProvinceState row{};
        if (!peace_effect_read_country_term_row(province_id,row)) return false;
        if (row.owner==source) {
            for (unsigned i=0;i<output.count;++i)
                if (output.rows[i].province_id==row.province_id) return false;
            output.rows[output.count++]=row;
            seen_any=true;
        }
        if (next==node) return false;
        node=next;
    }
    return seen_any;
}

static bool peace_effect_selected_term_matches(const bridge::peace_payload::PeaceTermPayload& term,
    std::uint32_t type,std::uint32_t bucket,std::uint64_t payer,
    std::uint64_t claimant) noexcept {
    return term.selected && term.complete && term.type_id==type
        && term.bucket==bucket && term.field10==payer && term.field18==claimant;
}

static bool peace_effect_read_relation(std::uint64_t country,std::uint64_t beneficiary,
    bool& active,bool& overlord,char (&subject_type)[bridge::peace_effects::kMaxReligionKey])
    noexcept {
    char country_tag[4]{},beneficiary_tag[4]{};
    if (!peace_effect_country_tag(country,country_tag)
        || !peace_effect_country_tag(beneficiary,beneficiary_tag)) return false;
    return peace_effect_subject_endpoint(beneficiary,country,active,overlord,subject_type);
}

// Grant Independence needs a bounded global check: the pairwise endpoint is
// insufficient when the country can still have another overlord.  The country
// relation table exposes 256 slot rows; each row's owner object has the
// bounded 16-byte association vector used by vassal_query_entry.  Validate the
// vector rows and their canonical helper result before counting associations
// whose +0x18 subject is the queried country.
static bool peace_effect_read_global_overlords(std::uint64_t country,
    std::uint64_t known_other,std::uint32_t& overlord_count,
    bool& scan_complete,bool& no_other_overlords) noexcept {
    overlord_count=0; scan_complete=false; no_other_overlords=false;
    std::uintptr_t record=0,rows=0,owner=0,begin=0;
    std::uint64_t actual_other=0;
    std::int32_t count=0;
    const unsigned known_slot=static_cast<unsigned>((known_other>>32u)&0xffffu);
    if (!country || !known_other || country==known_other || known_slot>=256u
        || !peace_query_country_pointer(country,record) || !record
        || !read(record+0x1510u,rows) || !rows) return false;
    const std::uintptr_t known_row=rows+static_cast<std::uintptr_t>(known_slot)*0x48u;
    if (!read(known_row+0x10u,actual_other) || actual_other!=known_other
        || !read(known_row,owner) || !owner
        || !read(owner+0x128u,begin) || !read(owner+0x134u,count)
        || count<0 || count>4096 || (count && !begin)) return false;
    bool seen_slots[256]{};
    for (std::int32_t index=0;index<count;++index) {
        unsigned char item[16]{};
        if (!read(begin+static_cast<std::uintptr_t>(index)*16u,item)) return false;
        std::int32_t item_slot=0; std::uintptr_t association=0;
        std::memcpy(&item_slot,item,sizeof(item_slot));
        std::memcpy(&association,item+8,sizeof(association));
        if (item_slot<0 || item_slot>=256 || !association
            || seen_slots[item_slot]) return false;
        seen_slots[item_slot]=true;
        const std::uintptr_t item_row=rows+static_cast<std::uintptr_t>(item_slot)*0x48u;
        std::uint64_t item_other=0,subject=0; std::uintptr_t item_owner=0,canonical=0;
        if (!read(item_row+0x10u,item_other) || !item_other
            || ((item_other>>32u)&0xffffu)!=static_cast<unsigned>(item_slot)
            || !read(item_row,item_owner) || item_owner!=owner
            || !vassal_query_entry(record,item_other,canonical) || canonical!=association
            || !read(association+0x18u,subject) || !subject) return false;
        if (subject==country) ++overlord_count;
    }
    std::uintptr_t final_owner=0,final_begin=0,final_rows=0;
    std::int32_t final_count=0;
    if (!read(record+0x1510u,final_rows) || final_rows!=rows
        || !read(known_row,final_owner) || final_owner!=owner
        || !read(owner+0x128u,final_begin) || final_begin!=begin
        || !read(owner+0x134u,final_count) || final_count!=count) return false;
    scan_complete=true; no_other_overlords=overlord_count==0;
    return true;
}

static bool peace_effect_capture_release_nation(
    const bridge::peace_payload::PeaceOfferPayload& offer,
    const bridge::peace_execution_wire::PeaceExecutionRequest& request,
    bridge::peace_effects::State& output) noexcept {
    auto& effect=output.release_nation;
    effect=bridge::peace_effects::CountryTerritoryEffectState{};
    output.release_nation_requested=request.selected_release_nation;
    effect.requested=request.selected_release_nation;
    if (!effect.requested) return true;
    const char* country_tag=request.release_nation_country;
    const char* source_tag=request.release_nation_source[0]
        ?request.release_nation_source:nullptr;
    std::uint64_t country=0,source=0;
    if (!country_tag[0] || !alliance_query_country(country_tag,country)
        || !country || country==offer.payer
        || (source_tag && (!alliance_query_country(source_tag,source) || !source))
        || (!source_tag && !(source=offer.payer)) || source==country) return false;
    unsigned matches=0;
    for (unsigned i=0;i<offer.term_count;++i) {
        const auto& term=offer.terms[i];
        if (!term.selected || term.type_id!=peace_effect_release_type
            || term.bucket!=peace_effect_release_bucket) continue;
        if (!peace_effect_selected_term_matches(term,peace_effect_release_type,
                peace_effect_release_bucket,offer.payer,offer.claimant)
            || term.field22!=source || term.extra30!=country) return false;
        ++matches;
    }
    if (matches!=1u) return false;
    effect.country=country; effect.source=source;
    if (!peace_effect_read_owned_count(country,effect.owned_count_before)
        || !peace_effect_read_owned_count(source,effect.source_owned_count_before)
        || !peace_effect_read_release_rows(country,source,effect)) return false;
    effect.owned_count_after=effect.owned_count_before;
    effect.source_owned_count_after=effect.source_owned_count_before;
    effect.complete=true; effect.values_readable=true;
    return true;
}

static bool peace_effect_capture_full_annexation(
    const bridge::peace_payload::PeaceOfferPayload& offer,
    const bridge::peace_execution_wire::PeaceExecutionRequest& request,
    bridge::peace_effects::State& output) noexcept {
    auto& effect=output.full_annexation;
    effect=bridge::peace_effects::CountryTerritoryEffectState{};
    output.full_annexation_requested=request.selected_full_annexation;
    effect.requested=request.selected_full_annexation;
    if (!effect.requested) return true;
    if (!request.annex_country[0] || !request.annex_beneficiary[0]) return false;
    std::uint64_t country=0,beneficiary=0;
    if (!alliance_query_country(request.annex_country,country)
        || !alliance_query_country(request.annex_beneficiary,beneficiary)
        || !country || !beneficiary || country==beneficiary) return false;
    std::int32_t ids[bridge::peace_effects::kMaxCountryTermProvinces]{};
    unsigned count=0;
    if (!peace_effect_read_owned_ids(country,ids,count) || count==0) return false;
    bool matched[bridge::peace_effects::kMaxCountryTermProvinces]{};
    unsigned selected=0;
    for (unsigned i=0;i<offer.term_count;++i) {
        const auto& term=offer.terms[i];
        if (!term.selected || term.type_id!=peace_effect_annex_type
            || term.bucket!=peace_effect_annex_bucket) continue;
        if (!peace_effect_selected_term_matches(term,peace_effect_annex_type,
                peace_effect_annex_bucket,offer.payer,offer.claimant)
            || !term.nested_present || term.nested_id<=0
            || term.extra30!=beneficiary) return false;
        unsigned index=count;
        for (unsigned j=0;j<count;++j)
            if (ids[j]==static_cast<std::int32_t>(term.nested_id)) { index=j; break; }
        if (index==count || matched[index]) return false;
        // The selected cede term must bind to the target by its recorded
        // owner; the province table is read independently as a second check.
        bridge::peace_effects::CountryTermProvinceState row{};
        if (!peace_effect_read_country_term_row(ids[index],row)
            || row.owner!=country || (term.field22!=country && term.field22!=row.owner))
            return false;
        matched[index]=true; ++selected;
    }
    if (selected!=count) return false;
    for (unsigned i=0;i<count;++i) {
        if (!matched[i] || !peace_effect_read_country_term_row(ids[i],effect.rows[i]))
            return false;
        if (effect.rows[i].owner!=country) return false;
    }
    effect.country=country; effect.source=beneficiary; effect.count=count;
    if (!peace_effect_read_owned_count(country,effect.owned_count_before)
        || !peace_effect_read_owned_count(beneficiary,effect.source_owned_count_before))
        return false;
    effect.owned_count_after=effect.owned_count_before;
    effect.source_owned_count_after=effect.source_owned_count_before;
    effect.complete=true; effect.values_readable=true;
    return true;
}

static bool peace_effect_capture_country_relation(
    const bridge::peace_payload::PeaceOfferPayload& offer,
    const bridge::peace_execution_wire::PeaceExecutionRequest& request,
    bool personal_union,bridge::peace_effects::State& output) noexcept {
    auto& effect=personal_union?output.form_personal_union:output.force_vassalization;
    bool& requested=personal_union?output.form_personal_union_requested:
        output.force_vassalization_requested;
    effect=bridge::peace_effects::CountryRelationEffectState{};
    requested=personal_union?request.selected_form_personal_union:
        request.selected_force_vassalization;
    effect.requested=requested;
    if (!requested) return true;
    const char* country_tag=personal_union?request.union_country:request.vassal_country;
    const char* beneficiary_tag=personal_union?request.union_beneficiary:
        request.vassal_beneficiary;
    if (!country_tag[0] || !beneficiary_tag[0]) return false;
    std::uint64_t country=0,beneficiary=0;
    if (!alliance_query_country(country_tag,country)
        || !alliance_query_country(beneficiary_tag,beneficiary)
        || !country || !beneficiary || country==beneficiary) return false;
    unsigned matches=0;
    for (unsigned i=0;i<offer.term_count;++i) {
        const auto& term=offer.terms[i];
        const bool force=term.type_id==peace_effect_force_type_a
            || term.type_id==peace_effect_force_type_b;
        const bool typed=personal_union
            ?term.type_id==peace_effect_union_type
            :force;
        const bool bucket=personal_union?term.bucket==peace_effect_union_bucket:
            ((term.type_id==peace_effect_force_type_a
                && term.bucket==peace_effect_force_bucket_a)
                || (term.type_id==peace_effect_force_type_b
                    && term.bucket==peace_effect_force_bucket_b));
        if (!term.selected || !typed || !bucket) continue;
        if (!term.complete || term.field10!=offer.payer
            || term.field18!=offer.claimant || term.field22!=country) return false;
        ++matches;
    }
    if (matches!=1u) return false;
    effect.country=country; effect.beneficiary=beneficiary;
    if (!peace_effect_read_relation(country,beneficiary,effect.relation_active_before,
            effect.is_overlord_before,effect.subject_type_before)) return false;
    effect.relation_active_after=effect.relation_active_before;
    effect.is_overlord_after=effect.is_overlord_before;
    std::memcpy(effect.subject_type_after,effect.subject_type_before,
        sizeof(effect.subject_type_after));
    effect.complete=true; effect.values_readable=true;
    return true;
}

static bool peace_effect_capture_grant_independence(
    const bridge::peace_payload::PeaceOfferPayload& offer,
    const bridge::peace_execution_wire::PeaceExecutionRequest& request,
    bridge::peace_effects::State& output) noexcept {
    auto& effect=output.grant_independence;
    effect=bridge::peace_effects::GrantIndependenceEffectState{};
    output.grant_independence_requested=request.selected_grant_independence;
    effect.requested=request.selected_grant_independence;
    if (!effect.requested) return true;
    unsigned matches=0;
    for (unsigned i=0;i<offer.term_count;++i) {
        const auto& term=offer.terms[i];
        if (!term.selected || term.type_id!=peace_effect_grant_type
            || term.bucket!=peace_effect_grant_bucket) continue;
        if (!peace_effect_selected_term_matches(term,peace_effect_grant_type,
                peace_effect_grant_bucket,offer.payer,offer.claimant)
            || term.field22!=offer.payer) return false;
        ++matches;
    }
    if (matches!=1u || !offer.claimant || !offer.payer
        || offer.claimant==offer.payer) return false;
    effect.country=offer.claimant; effect.overlord=offer.payer;
    if (!peace_effect_read_relation(effect.country,effect.overlord,
            effect.relation_active_before,effect.is_overlord_before,
            effect.subject_type_before)) return false;
    (void)peace_effect_read_global_overlords(effect.country,effect.overlord,
        effect.overlord_count_before,effect.overlord_scan_complete_before,
        effect.no_other_overlords_before);
    effect.overlord_count_after=effect.overlord_count_before;
    effect.overlord_scan_complete_after=effect.overlord_scan_complete_before;
    effect.no_other_overlords_after=effect.no_other_overlords_before;
    effect.relation_active_after=effect.relation_active_before;
    effect.is_overlord_after=effect.is_overlord_before;
    std::memcpy(effect.subject_type_after,effect.subject_type_before,
        sizeof(effect.subject_type_after));
    std::snprintf(effect.reason_code,sizeof(effect.reason_code),
        "%s","INDEPENDENCE_GLOBAL_OVERLORD_NOT_VERIFIED");
    effect.complete=true; effect.values_readable=true;
    return true;
}

static bool execution_peace_effects_capture_country_terms(
    const bridge::peace_payload::PeaceOfferPayload& offer,
    const bridge::peace_execution_wire::PeaceExecutionRequest& request,
    bridge::peace_effects::State& output) noexcept {
    if (!peace_effect_capture_release_nation(offer,request,output)
        || !peace_effect_capture_country_relation(offer,request,false,output)
        || !peace_effect_capture_country_relation(offer,request,true,output)
        || !peace_effect_capture_grant_independence(offer,request,output)
        || !peace_effect_capture_full_annexation(offer,request,output)) return false;
    return true;
}

static bool peace_effect_after_territory(
    const bridge::peace_effects::CountryTerritoryEffectState& before,
    bridge::peace_effects::CountryTerritoryEffectState& after) noexcept {
    after=bridge::peace_effects::CountryTerritoryEffectState{};
    after.requested=before.requested; after.country=before.country;
    after.source=before.source; after.count=before.count;
    after.owned_count_before=before.owned_count_before;
    after.source_owned_count_before=before.source_owned_count_before;
    if (!before.requested) return true;
    if (!before.complete || !before.values_readable || before.count==0
        || before.count>bridge::peace_effects::kMaxCountryTermProvinces)
        return false;
    if (!peace_effect_read_owned_count(after.country,after.owned_count_after)
        || !peace_effect_read_owned_count(after.source,after.source_owned_count_after))
        return false;
    for (unsigned i=0;i<before.count;++i)
        if (!peace_effect_read_country_term_row(before.rows[i].province_id,after.rows[i]))
            return false;
    after.complete=true; after.values_readable=true;
    return true;
}

static bool peace_effect_after_relation(
    const bridge::peace_effects::CountryRelationEffectState& before,
    bridge::peace_effects::CountryRelationEffectState& after) noexcept {
    after=bridge::peace_effects::CountryRelationEffectState{};
    after.requested=before.requested; after.country=before.country;
    after.beneficiary=before.beneficiary;
    std::memcpy(after.subject_type_before,before.subject_type_before,
        sizeof(after.subject_type_before));
    after.relation_active_before=before.relation_active_before;
    after.is_overlord_before=before.is_overlord_before;
    if (!before.requested) return true;
    if (!before.complete || !before.values_readable
        || !peace_effect_read_relation(after.country,after.beneficiary,
            after.relation_active_after,after.is_overlord_after,
            after.subject_type_after)) return false;
    after.complete=true; after.values_readable=true;
    return true;
}

static bool peace_effect_after_grant(
    const bridge::peace_effects::GrantIndependenceEffectState& before,
    bridge::peace_effects::GrantIndependenceEffectState& after) noexcept {
    after=bridge::peace_effects::GrantIndependenceEffectState{};
    after.requested=before.requested; after.country=before.country;
    after.overlord=before.overlord;
    after.overlord_count_before=before.overlord_count_before;
    after.overlord_scan_complete_before=before.overlord_scan_complete_before;
    after.no_other_overlords_before=before.no_other_overlords_before;
    after.relation_active_before=before.relation_active_before;
    after.is_overlord_before=before.is_overlord_before;
    std::memcpy(after.subject_type_before,before.subject_type_before,
        sizeof(after.subject_type_before));
    std::snprintf(after.reason_code,sizeof(after.reason_code),
        "%s","INDEPENDENCE_GLOBAL_OVERLORD_NOT_VERIFIED");
    if (!before.requested) return true;
    if (!before.complete || !before.values_readable
        || !peace_effect_read_relation(after.country,after.overlord,
            after.relation_active_after,after.is_overlord_after,
            after.subject_type_after)) return false;
    (void)peace_effect_read_global_overlords(after.country,after.overlord,
        after.overlord_count_after,after.overlord_scan_complete_after,
        after.no_other_overlords_after);
    if (after.overlord_scan_complete_after && after.no_other_overlords_after)
        after.reason_code[0]=0;
    after.complete=true; after.values_readable=true;
    return true;
}

static bool execution_peace_effects_after_country_terms(
    const bridge::peace_effects::State& before,
    bridge::peace_effects::State& output) noexcept {
    output.release_nation_requested=before.release_nation_requested;
    output.force_vassalization_requested=before.force_vassalization_requested;
    output.form_personal_union_requested=before.form_personal_union_requested;
    output.grant_independence_requested=before.grant_independence_requested;
    output.full_annexation_requested=before.full_annexation_requested;
    return peace_effect_after_territory(before.release_nation,output.release_nation)
        && peace_effect_after_relation(before.force_vassalization,output.force_vassalization)
        && peace_effect_after_relation(before.form_personal_union,output.form_personal_union)
        && peace_effect_after_grant(before.grant_independence,output.grant_independence)
        && peace_effect_after_territory(before.full_annexation,output.full_annexation);
}

static bool peace_effect_json_append(char* output,std::size_t capacity,
    std::size_t& used,const char* text) noexcept {
    if (!output || !text || used>=capacity) return false;
    const std::size_t length=std::strlen(text);
    if (length>=capacity-used) return false;
    std::memcpy(output+used,text,length); used+=length; output[used]=0;
    return true;
}

static bool peace_effect_json_append_format(char* output,std::size_t capacity,
    std::size_t& used,const char* format,...) noexcept {
    if (!output || !format || used>=capacity) return false;
    va_list args; va_start(args,format);
    const int written=std::vsnprintf(output+used,capacity-used,format,args);
    va_end(args);
    if (written<0 || static_cast<std::size_t>(written)>=capacity-used) return false;
    used+=static_cast<std::size_t>(written); return true;
}

static bool peace_effect_json_tag(char* output,std::size_t capacity,
    std::size_t& used,std::uint64_t handle) noexcept {
    char tag[4]{};
    if (!peace_effect_country_tag(handle,tag))
        return peace_effect_json_append(output,capacity,used,"null");
    return peace_effect_json_append_format(output,capacity,used,"\"%.3s\"",tag);
}

static bool peace_effect_json_subject_type(char* output,std::size_t capacity,
    std::size_t& used,const char (&type)[bridge::peace_effects::kMaxReligionKey]) noexcept {
    if (!type[0]) return peace_effect_json_append(output,capacity,used,"null");
    return peace_effect_json_append_format(output,capacity,used,"\"%.63s\"",type);
}

static bool peace_effect_append_territory(char* output,std::size_t capacity,
    std::size_t& used,const char* key,const bridge::peace_effects::CountryTerritoryEffectState& before,
    const bridge::peace_effects::CountryTerritoryEffectState& after,bool full,
    bool verified_value,bool& complete,bool& readable,bool& verified) noexcept {
    const bool context=bridge::peace_effects::country_territory_effect_context_valid(before)
        && bridge::peace_effects::country_territory_effect_context_valid(after)
        && before.country==after.country && before.source==after.source
        && before.count==after.count;
    bool rows_readable=context;
    if (!peace_effect_json_append_format(output,capacity,used,
        "\"%s\":{\"country\":",key)
        || !peace_effect_json_tag(output,capacity,used,before.country)
        || !peace_effect_json_append_format(output,capacity,used,",\"%s\":",
            full?"beneficiary":"source")
        || !peace_effect_json_tag(output,capacity,used,before.source)
        || !peace_effect_json_append_format(output,capacity,used,
            ",\"owned_count_before\":%u,\"owned_count_after\":%u,\"%s\":%u,\"%s\":%u,\"province_rows\":[",
            before.owned_count_before,after.owned_count_after,
            full?"beneficiary_owned_count_before":"source_owned_count_before",
            before.source_owned_count_before,
            full?"beneficiary_owned_count_after":"source_owned_count_after",
            after.source_owned_count_after)) return false;
    for (unsigned i=0;i<before.count && i<bridge::peace_effects::kMaxCountryTermProvinces;++i) {
        const auto& left=before.rows[i]; const auto& right=after.rows[i];
        char owner_before[4]{},owner_after[4]{},controller_before[4]{},controller_after[4]{};
        const bool row=left.complete && right.complete
            && left.province_id==right.province_id
            && peace_effect_country_tag(left.owner,owner_before)
            && peace_effect_country_tag(right.owner,owner_after)
            && peace_effect_country_tag(left.controller,controller_before)
            && peace_effect_country_tag(right.controller,controller_after);
        rows_readable=rows_readable && row;
        if (i && !peace_effect_json_append(output,capacity,used,",")) return false;
        if (!peace_effect_json_append_format(output,capacity,used,
            "{\"province_id\":%d,\"owner_before\":",left.province_id)
            || !peace_effect_json_tag(output,capacity,used,left.owner)
            || !peace_effect_json_append(output,capacity,used,",\"owner_after\":")
            || !peace_effect_json_tag(output,capacity,used,right.owner)
            || !peace_effect_json_append(output,capacity,used,",\"controller_before\":")
            || !peace_effect_json_tag(output,capacity,used,left.controller)
            || !peace_effect_json_append(output,capacity,used,",\"controller_after\":")
            || !peace_effect_json_tag(output,capacity,used,right.controller)
            || !peace_effect_json_append_format(output,capacity,used,
                ",\"complete\":%s}",row?"true":"false")) return false;
    }
    const bool unchanged=bridge::peace_effects::country_territory_effect_exactly_equal(before,after);
    const bool effect_complete=context && rows_readable && before.complete && after.complete;
    complete=complete && effect_complete;
    readable=readable && rows_readable;
    verified=verified && verified_value;
    if (!peace_effect_json_append_format(output,capacity,used,
        "],\"complete\":%s,\"values_readable\":%s,\"unchanged\":%s,\"verified\":%s}",
        effect_complete?"true":"false",rows_readable?"true":"false",
        unchanged?"true":"false",verified_value && effect_complete?"true":"false")) return false;
    return true;
}

static bool peace_effect_append_relation(char* output,std::size_t capacity,
    std::size_t& used,const char* key,
    const bridge::peace_effects::CountryRelationEffectState& before,
    const bridge::peace_effects::CountryRelationEffectState& after,
    bool verified_value,bool& complete,bool& readable,bool& verified) noexcept {
    const bool context=bridge::peace_effects::country_relation_effect_context_valid(before)
        && bridge::peace_effects::country_relation_effect_context_valid(after)
        && before.country==after.country && before.beneficiary==after.beneficiary;
    char country_tag[4]{},beneficiary_tag[4]{};
    const bool tag_values=peace_effect_country_tag(before.country,country_tag)
        && peace_effect_country_tag(before.beneficiary,beneficiary_tag);
    const bool effect_complete=context && before.complete && after.complete;
    const bool effect_readable=effect_complete && tag_values;
    const bool unchanged=bridge::peace_effects::country_relation_effect_exactly_equal(
        before,after);
    complete=complete && effect_complete;
    readable=readable && effect_readable;
    verified=verified && verified_value;
    if (!peace_effect_json_append_format(output,capacity,used,
            "\"%s\":{\"country\":",key)
        || !peace_effect_json_tag(output,capacity,used,before.country)
        || !peace_effect_json_append(output,capacity,used,",\"beneficiary\":")
        || !peace_effect_json_tag(output,capacity,used,before.beneficiary)
        || !peace_effect_json_append_format(output,capacity,used,
            ",\"relation_active_before\":%s,\"relation_active_after\":%s,"
            "\"is_overlord_before\":%s,\"is_overlord_after\":%s,"
            "\"subject_type_before\":",
            before.relation_active_before?"true":"false",
            after.relation_active_after?"true":"false",
            before.is_overlord_before?"true":"false",
            after.is_overlord_after?"true":"false")
        || !peace_effect_json_subject_type(output,capacity,used,before.subject_type_before)
        || !peace_effect_json_append(output,capacity,used,",\"subject_type_after\":")
        || !peace_effect_json_subject_type(output,capacity,used,after.subject_type_after)
        || !peace_effect_json_append_format(output,capacity,used,
            ",\"complete\":%s,\"values_readable\":%s,\"unchanged\":%s,\"verified\":%s}",
            effect_complete?"true":"false",effect_readable?"true":"false",
            unchanged?"true":"false",verified_value && effect_readable?"true":"false"))
        return false;
    return true;
}

static bool peace_effect_append_grant(char* output,std::size_t capacity,
    std::size_t& used,const bridge::peace_effects::GrantIndependenceEffectState& before,
    const bridge::peace_effects::GrantIndependenceEffectState& after,
    bool verified_value,bool& complete,bool& readable,bool& verified) noexcept {
    const bool context=bridge::peace_effects::grant_independence_effect_context_valid(before)
        && bridge::peace_effects::grant_independence_effect_context_valid(after)
        && before.country==after.country && before.overlord==after.overlord;
    char country_tag[4]{},overlord_tag[4]{};
    const bool tag_values=peace_effect_country_tag(before.country,country_tag)
        && peace_effect_country_tag(before.overlord,overlord_tag);
    const bool effect_complete=context && before.complete && after.complete;
    const bool effect_readable=effect_complete && tag_values;
    const bool unchanged=bridge::peace_effects::grant_independence_effect_exactly_equal(
        before,after);
    complete=complete && effect_complete;
    readable=readable && effect_readable;
    verified=verified && verified_value;
    if (!peace_effect_json_append(output,capacity,used,
            "\"grant_independence\":{\"country\":")
        || !peace_effect_json_tag(output,capacity,used,before.country)
        || !peace_effect_json_append(output,capacity,used,",\"overlord\":")
        || !peace_effect_json_tag(output,capacity,used,before.overlord)
        || !peace_effect_json_append_format(output,capacity,used,
            ",\"relation_active_before\":%s,\"relation_active_after\":%s,"
            "\"is_overlord_before\":%s,\"is_overlord_after\":%s,"
            "\"subject_type_before\":",
            before.relation_active_before?"true":"false",
            after.relation_active_after?"true":"false",
            before.is_overlord_before?"true":"false",
            after.is_overlord_after?"true":"false")
        || !peace_effect_json_subject_type(output,capacity,used,before.subject_type_before)
        || !peace_effect_json_append(output,capacity,used,",\"subject_type_after\":")
        || !peace_effect_json_subject_type(output,capacity,used,after.subject_type_after)
        || !peace_effect_json_append_format(output,capacity,used,
            ",\"overlord_count_before\":%u,\"overlord_count_after\":%u,"
            "\"overlord_scan_complete_before\":%s,\"overlord_scan_complete_after\":%s,"
            "\"no_other_overlords_before\":%s,\"no_other_overlords_after\":%s,"
            "\"complete\":%s,\"values_readable\":%s,\"unchanged\":%s,"
            "\"verified\":%s,\"reason_code\":%s}",
            before.overlord_count_before,after.overlord_count_after,
            before.overlord_scan_complete_before?"true":"false",
            after.overlord_scan_complete_after?"true":"false",
            before.no_other_overlords_before?"true":"false",
            after.no_other_overlords_after?"true":"false",
            effect_complete?"true":"false",effect_readable?"true":"false",
            unchanged?"true":"false",verified_value && effect_readable?"true":"false",
            (verified_value && effect_complete && effect_readable)
                ?"null":"\"INDEPENDENCE_GLOBAL_OVERLORD_NOT_VERIFIED\"")) return false;
    return true;
}

static bool execution_peace_effects_country_terms_json_append(
    char* output,std::size_t capacity,std::size_t& used,
    const bridge::peace_effects::State& before,
    const bridge::peace_effects::State& after,bool settled,bool endpoints,
    bool& complete,bool& readable,bool& verified) noexcept {
    complete=true; readable=true; verified=true;
    if (!bridge::peace_effects::country_terms_any_requested(before)) return true;
    if (!peace_effect_json_append(output,capacity,used,",\"country_terms\":{")) return false;
    bool first=true;
    const auto comma=[&]() noexcept {
        if (!first && !peace_effect_json_append(output,capacity,used,",")) return false;
        first=false; return true;
    };
    const auto append_null=[&](const char* key) noexcept {
        return comma() && peace_effect_json_append_format(output,capacity,used,
            "\"%s\":null",key);
    };
    if (before.release_nation_requested) {
        if (!comma() || !peace_effect_append_territory(output,capacity,used,
                "release_nation",before.release_nation,after.release_nation,false,
                settled && endpoints
                    && bridge::peace_effects::release_nation_established(before,after),
                complete,readable,verified)) return false;
    } else if (!append_null("release_nation")) return false;
    if (before.force_vassalization_requested) {
        if (!comma() || !peace_effect_append_relation(output,capacity,used,
                "force_vassalization",before.force_vassalization,
                after.force_vassalization,settled && endpoints
                    && bridge::peace_effects::force_vassalization_established(before,after),
                complete,readable,verified)) return false;
    } else if (!append_null("force_vassalization")) return false;
    if (before.form_personal_union_requested) {
        if (!comma() || !peace_effect_append_relation(output,capacity,used,
                "form_personal_union",before.form_personal_union,
                after.form_personal_union,settled && endpoints
                    && bridge::peace_effects::form_personal_union_established(before,after),
                complete,readable,verified)) return false;
    } else if (!append_null("form_personal_union")) return false;
    if (before.grant_independence_requested) {
        if (!comma() || !peace_effect_append_grant(output,capacity,used,
                before.grant_independence,after.grant_independence,
                settled && endpoints
                    && bridge::peace_effects::grant_independence_established(before,after),
                complete,readable,verified)) return false;
    } else if (!append_null("grant_independence")) return false;
    if (before.full_annexation_requested) {
        if (!comma() || !peace_effect_append_territory(output,capacity,used,
                "full_annexation",before.full_annexation,after.full_annexation,true,
                settled && endpoints
                    && bridge::peace_effects::full_annexation_established(before,after),
                complete,readable,verified)) return false;
    } else if (!append_null("full_annexation")) return false;
    return peace_effect_json_append(output,capacity,used,"}");
}

