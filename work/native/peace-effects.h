#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace bridge::peace_effects {

constexpr unsigned kMaxCountries=256;
constexpr unsigned kMaxProvinces=16;
constexpr unsigned kMaxAnnulPartners=16;
constexpr unsigned kMaxSubjectCountries=16;
// Country-level territorial terms can carry the complete owned-province set.
// This is deliberately separate from the legacy province request/effect array
// above: the old 16-row protocol remains unchanged.
constexpr unsigned kMaxCountryTermProvinces=512;
constexpr unsigned kSpecialPowerCount=3;
constexpr unsigned kMaxReligionKey=64;
// Core vectors are read through the province's begin/end pair.  The native
// observation never follows an unbounded vector: one province can expose at
// most this many 8-byte country handles in a single before/after capture.
constexpr unsigned kMaxProvinceCores=256;

struct CountryBalance {
    std::uint64_t country=0;
    std::int32_t treasury_raw=0;
    std::int32_t prestige_raw=0;
    bool prestige_readable=false;
};

struct ProvinceState {
    std::int32_t id=0;
    std::uint64_t owner=0,controller=0;
};

// Return Core and Revoke Core share the province owner/controller snapshot but
// differ in the persistent core-vector consequence.  Keep the target handle
// separate from the province owner: a Return Core target may be a third
// country, while a Revoke Core target is the core being removed.
struct CoreProvinceState {
    std::int32_t province_id=0;
    std::uint64_t target_core_owner=0;
    std::uint64_t owner=0,controller=0;
    bool core_owner_present=false;
    bool complete=false;
};

struct CoreEffectState {
    bool requested=false;
    unsigned count=0;
    CoreProvinceState rows[kMaxProvinces]{};
    bool complete=false;
};

struct ReparationsState {
    std::uint64_t payer=0,claimant=0;
    std::int32_t start_date_raw=0,end_date_raw=0;
    bool present=false,active=false,complete=false;
};

struct TradePowerState {
    std::uint64_t source=0,beneficiary=0;
    std::int32_t start_date_raw=0,end_date_raw=0;
    std::int32_t amount_raw=0,amount_scale=1000;
    bool present=false,peace_treaty=false,complete=false;
};

struct AnnulState {
    std::uint64_t country=0,partner=0;
    std::int32_t start_date_raw=0,end_date_raw=0;
    bool present=false,alliance_present=false,complete=false;
};

// Release Subject and Transfer Subject both operate on the selected
// subject-country list.  Keep the native handles in the observation so the
// relation direction is checked by identity; tags are only a JSON projection.
// A beneficiary handle is zero for Release Subject.  In that case the
// beneficiary-side booleans and type are represented as JSON null by the
// serializer, rather than as a guessed negative relation.
struct SubjectRelationState {
    std::uint64_t country=0,source=0,beneficiary=0;
    char country_tag[4]{},source_tag[4]{},beneficiary_tag[4]{};
    char source_subject_type[kMaxReligionKey]{};
    char beneficiary_subject_type[kMaxReligionKey]{};
    bool source_relation_active=false,source_is_overlord=false;
    bool beneficiary_relation_active=false,beneficiary_is_overlord=false;
    bool beneficiary_relation_readable=false;
    bool complete=false;
};

struct SubjectEffectState {
    bool requested=false;
    std::uint64_t source=0,beneficiary=0;
    unsigned count=0;
    SubjectRelationState rows[kMaxSubjectCountries]{};
    bool complete=false;
};

// The country-term territory rows are intentionally lightweight.  They are
// snapshots, not request records; before and after State values are compared
// by province id and the canonical owner/controller handles.
struct CountryTermProvinceState {
    std::int32_t province_id=0;
    std::uint64_t owner=0,controller=0;
    bool complete=false;
};

struct CountryTerritoryEffectState {
    bool requested=false;
    std::uint64_t country=0,source=0;
    std::uint32_t owned_count_before=0,owned_count_after=0;
    std::uint32_t source_owned_count_before=0,source_owned_count_after=0;
    unsigned count=0;
    CountryTermProvinceState rows[kMaxCountryTermProvinces]{};
    bool complete=false,values_readable=false,unchanged=false,verified=false;
    char reason_code[64]{};
};

struct CountryRelationEffectState {
    bool requested=false;
    std::uint64_t country=0,beneficiary=0;
    bool relation_active_before=false,relation_active_after=false;
    bool is_overlord_before=false,is_overlord_after=false;
    char subject_type_before[kMaxReligionKey]{};
    char subject_type_after[kMaxReligionKey]{};
    bool complete=false,values_readable=false,unchanged=false,verified=false;
    char reason_code[64]{};
};

struct GrantIndependenceEffectState {
    bool requested=false;
    std::uint64_t country=0,overlord=0;
    bool relation_active_before=false,relation_active_after=false;
    bool is_overlord_before=false,is_overlord_after=false;
    char subject_type_before[kMaxReligionKey]{};
    char subject_type_after[kMaxReligionKey]{};
    std::uint32_t overlord_count_before=0,overlord_count_after=0;
    bool overlord_scan_complete_before=false,overlord_scan_complete_after=false;
    bool no_other_overlords_before=false,no_other_overlords_after=false;
    bool complete=false,values_readable=false,unchanged=false,verified=false;
    char reason_code[64]{};
};

// H/S use the same native consequence shape for the rival list and prestige.
// Show Strength adds the three native power counters.  The counters remain an
// unnamed ordered vector until their game-specific mapping is independently
// proven; no ADM/DIP/MIL label is implied here.
struct HumiliateRivalState {
    std::uint64_t country=0,beneficiary=0;
    std::int32_t humiliated_index=-1;
    char country_tag[4]{},beneficiary_tag[4]{};
    std::int32_t country_prestige_raw=0,beneficiary_prestige_raw=0;
    bool humiliated=false,values_readable=false,complete=false;
};

struct ShowStrengthState {
    std::uint64_t country=0,beneficiary=0;
    std::int32_t humiliated_index=-1;
    char country_tag[4]{},beneficiary_tag[4]{};
    std::int32_t country_prestige_raw=0,beneficiary_prestige_raw=0;
    std::int32_t powers[kSpecialPowerCount]{};
    std::int32_t powers_requested=0;
    bool humiliated=false,values_readable=false,complete=false;
};

struct ForceReligionState {
    std::uint64_t country=0,beneficiary=0;
    char religion[kMaxReligionKey]{};
    char beneficiary_religion[kMaxReligionKey]{};
    char capital_religion[kMaxReligionKey]{};
    bool values_readable=false,complete=false;
};

struct State {
    CountryBalance countries[kMaxCountries]{};
    ProvinceState provinces[kMaxProvinces]{};
    unsigned country_count=0,province_count=0;
    std::int32_t date_raw=0;
    bool complete=false;
    bool reparations_requested=false;
    ReparationsState reparations{};
    bool trade_power_requested=false;
    TradePowerState trade_power{};
    bool concede_defeat_requested=false;
    bool annul_treaties_requested=false;
    unsigned annul_count=0;
    AnnulState annul_treaties[kMaxAnnulPartners]{};
    bool humiliate_rival_requested=false;
    std::uint64_t humiliate_rival_country=0,humiliate_rival_beneficiary=0;
    HumiliateRivalState humiliate_rival{};
    bool show_strength_requested=false;
    std::uint64_t show_strength_country=0,show_strength_beneficiary=0;
    ShowStrengthState show_strength{};
    bool force_religion_requested=false;
    std::uint64_t force_religion_country=0,force_religion_beneficiary=0;
    ForceReligionState force_religion{};
    bool return_core_requested=false;
    CoreEffectState return_core{};
    bool revoke_core_requested=false;
    CoreEffectState revoke_core{};
    bool release_subject_requested=false;
    SubjectEffectState release_subject{};
    bool transfer_subject_requested=false;
    SubjectEffectState transfer_subject{};
    bool release_nation_requested=false;
    CountryTerritoryEffectState release_nation{};
    bool force_vassalization_requested=false;
    CountryRelationEffectState force_vassalization{};
    bool form_personal_union_requested=false;
    CountryRelationEffectState form_personal_union{};
    bool grant_independence_requested=false;
    GrantIndependenceEffectState grant_independence{};
    bool full_annexation_requested=false;
    CountryTerritoryEffectState full_annexation{};
};

inline bool annul_context_pairs_valid(const State& state) noexcept {
    if (!state.annul_treaties_requested) return state.annul_count==0;
    if (!state.annul_count || state.annul_count>kMaxAnnulPartners) return false;
    for (unsigned i=0;i<state.annul_count;++i) {
        const auto& pair=state.annul_treaties[i];
        if (!pair.country || !pair.partner || pair.country==pair.partner) return false;
        for (unsigned j=0;j<i;++j)
            if (state.annul_treaties[j].country==pair.country
                && state.annul_treaties[j].partner==pair.partner) return false;
    }
    return true;
}

inline bool core_effect_context_valid(const CoreEffectState& effect) noexcept {
    if (!effect.requested)
        return effect.count==0 && !effect.complete;
    if (!effect.count || effect.count>kMaxProvinces || !effect.complete) return false;
    for (unsigned i=0;i<effect.count;++i) {
        const auto& row=effect.rows[i];
        if (row.province_id<=0 || !row.target_core_owner) return false;
        for (unsigned j=0;j<i;++j)
            if (effect.rows[j].province_id==row.province_id) return false;
    }
    return true;
}

inline bool core_effect_values_readable(const CoreProvinceState& row) noexcept {
    return row.complete && row.province_id>0 && row.target_core_owner
        && row.owner && row.controller;
}

inline bool subject_effect_context_valid(const SubjectEffectState& effect) noexcept {
    if (!effect.requested)
        return effect.count==0 && !effect.complete
            && effect.source==0 && effect.beneficiary==0;
    if (!effect.source || effect.count==0 || effect.count>kMaxSubjectCountries
        || !effect.complete || effect.beneficiary==effect.source) return false;
    for (unsigned i=0;i<effect.count;++i) {
        const auto& row=effect.rows[i];
        if (!row.country || row.country==effect.source
            || row.source!=effect.source || row.beneficiary!=effect.beneficiary
            || !row.complete || !row.source_tag[0]) return false;
        for (unsigned j=0;j<i;++j)
            if (effect.rows[j].country==row.country) return false;
    }
    return true;
}

inline bool subject_relation_values_readable(const SubjectRelationState& row) noexcept {
    return row.complete && row.country && row.source && row.country_tag[0] && row.source_tag[0]
        && (row.beneficiary==0 || (row.beneficiary_tag[0]
            && row.beneficiary_relation_readable));
}

inline bool country_territory_effect_context_valid(
    const CountryTerritoryEffectState& effect) noexcept {
    if (!effect.requested)
        return effect.country==0 && effect.source==0 && effect.count==0
            && !effect.complete && !effect.values_readable;
    if (!effect.country || !effect.source || effect.country==effect.source
        || effect.count==0 || effect.count>kMaxCountryTermProvinces
        || !effect.complete || !effect.values_readable) return false;
    for (unsigned i=0;i<effect.count;++i) {
        const auto& row=effect.rows[i];
        if (!row.complete || row.province_id<=0 || !row.owner || !row.controller)
            return false;
        for (unsigned j=0;j<i;++j)
            if (effect.rows[j].province_id==row.province_id) return false;
    }
    return true;
}

inline bool country_relation_effect_context_valid(
    const CountryRelationEffectState& effect) noexcept {
    if (!effect.requested)
        return effect.country==0 && effect.beneficiary==0 && !effect.complete
            && !effect.values_readable && !effect.subject_type_before[0]
            && !effect.subject_type_after[0];
    return effect.country && effect.beneficiary
        && effect.country!=effect.beneficiary && effect.complete
        && effect.values_readable;
}

inline bool grant_independence_effect_context_valid(
    const GrantIndependenceEffectState& effect) noexcept {
    if (!effect.requested)
        return effect.country==0 && effect.overlord==0 && !effect.complete
            && !effect.values_readable && !effect.subject_type_before[0]
            && !effect.subject_type_after[0];
    return effect.country && effect.overlord && effect.country!=effect.overlord
        && effect.complete && effect.values_readable;
}

inline bool country_territory_effect_exactly_equal(
    const CountryTerritoryEffectState& before,
    const CountryTerritoryEffectState& after) noexcept {
    if (!before.requested || !after.requested
        || !country_territory_effect_context_valid(before)
        || !country_territory_effect_context_valid(after)
        || before.country!=after.country || before.source!=after.source
        || before.count!=after.count
        || before.owned_count_before!=after.owned_count_before
        || before.source_owned_count_before!=after.source_owned_count_before)
        return false;
    for (unsigned i=0;i<before.count;++i) {
        const auto& left=before.rows[i];
        const auto& right=after.rows[i];
        if (left.province_id!=right.province_id || left.owner!=right.owner
            || left.controller!=right.controller)
            return false;
    }
    return before.owned_count_after==after.owned_count_after
        && before.source_owned_count_after==after.source_owned_count_after;
}

inline bool country_relation_effect_exactly_equal(
    const CountryRelationEffectState& before,
    const CountryRelationEffectState& after) noexcept {
    return before.requested && after.requested
        && country_relation_effect_context_valid(before)
        && country_relation_effect_context_valid(after)
        && before.country==after.country
        && before.beneficiary==after.beneficiary
        && before.relation_active_before==after.relation_active_before
        && before.relation_active_after==after.relation_active_after
        && before.is_overlord_before==after.is_overlord_before
        && before.is_overlord_after==after.is_overlord_after
        && !std::strcmp(before.subject_type_before,after.subject_type_before)
        && !std::strcmp(before.subject_type_after,after.subject_type_after);
}

inline bool grant_independence_effect_exactly_equal(
    const GrantIndependenceEffectState& before,
    const GrantIndependenceEffectState& after) noexcept {
    return before.requested && after.requested
        && grant_independence_effect_context_valid(before)
        && grant_independence_effect_context_valid(after)
        && before.country==after.country && before.overlord==after.overlord
        && before.relation_active_before==after.relation_active_before
        && before.relation_active_after==after.relation_active_after
        && before.is_overlord_before==after.is_overlord_before
        && before.is_overlord_after==after.is_overlord_after
        && before.overlord_count_before==after.overlord_count_before
        && before.overlord_count_after==after.overlord_count_after
        && before.overlord_scan_complete_before==after.overlord_scan_complete_before
        && before.overlord_scan_complete_after==after.overlord_scan_complete_after
        && before.no_other_overlords_before==after.no_other_overlords_before
        && before.no_other_overlords_after==after.no_other_overlords_after
        && !std::strcmp(before.subject_type_before,after.subject_type_before)
        && !std::strcmp(before.subject_type_after,after.subject_type_after);
}

inline bool subject_effect_exactly_equal(const SubjectEffectState& before,
    const SubjectEffectState& after) noexcept {
    if (!before.requested || !after.requested
        || !subject_effect_context_valid(before)
        || !subject_effect_context_valid(after)
        || before.source!=after.source || before.beneficiary!=after.beneficiary
        || before.count!=after.count) return false;
    for (unsigned i=0;i<before.count;++i) {
        const auto& left=before.rows[i];
        const auto& right=after.rows[i];
        if (left.country!=right.country || left.source!=right.source
            || left.beneficiary!=right.beneficiary
            || left.source_relation_active!=right.source_relation_active
            || left.source_is_overlord!=right.source_is_overlord
            || left.beneficiary_relation_readable!=right.beneficiary_relation_readable
            || left.beneficiary_relation_active!=right.beneficiary_relation_active
            || left.beneficiary_is_overlord!=right.beneficiary_is_overlord
            || std::strcmp(left.source_subject_type,right.source_subject_type)!=0
            || std::strcmp(left.beneficiary_subject_type,right.beneficiary_subject_type)!=0)
            return false;
    }
    return true;
}

inline bool same_observation_context(const State& before,const State& after) noexcept;

inline bool release_subject_established(const State& before,const State& after) noexcept {
    if (!before.release_subject_requested || !after.release_subject_requested
        || !same_observation_context(before,after)
        || !subject_effect_context_valid(before.release_subject)
        || !subject_effect_context_valid(after.release_subject)
        || before.release_subject.beneficiary!=0
        || after.release_subject.beneficiary!=0
        || before.release_subject.count!=after.release_subject.count) return false;
    for (unsigned i=0;i<before.release_subject.count;++i) {
        const auto& left=before.release_subject.rows[i];
        const auto& right=after.release_subject.rows[i];
        if (!subject_relation_values_readable(left)
            || !subject_relation_values_readable(right)
            || left.country!=right.country || !left.source_relation_active
            || !left.source_is_overlord || right.source_relation_active
            || right.source_is_overlord) return false;
    }
    return true;
}

inline bool transfer_subject_established(const State& before,const State& after) noexcept {
    if (!before.transfer_subject_requested || !after.transfer_subject_requested
        || !same_observation_context(before,after)
        || !subject_effect_context_valid(before.transfer_subject)
        || !subject_effect_context_valid(after.transfer_subject)
        || !before.transfer_subject.beneficiary || before.transfer_subject.count!=after.transfer_subject.count
        || before.transfer_subject.source!=after.transfer_subject.source
        || before.transfer_subject.beneficiary!=after.transfer_subject.beneficiary) return false;
    for (unsigned i=0;i<before.transfer_subject.count;++i) {
        const auto& left=before.transfer_subject.rows[i];
        const auto& right=after.transfer_subject.rows[i];
        if (!subject_relation_values_readable(left)
            || !subject_relation_values_readable(right)
            || left.country!=right.country
            || !left.source_relation_active || !left.source_is_overlord
            || !left.beneficiary_relation_readable
            || left.beneficiary_relation_active
            || right.source_relation_active || right.source_is_overlord
            || !right.beneficiary_relation_active || !right.beneficiary_is_overlord)
            return false;
    }
    return true;
}

inline bool same_observation_context(const State& before,const State& after) noexcept {
    if (!before.complete || !after.complete || before.date_raw!=after.date_raw
        || before.country_count>kMaxCountries || before.province_count>kMaxProvinces
        || before.country_count!=after.country_count || before.province_count!=after.province_count
        || before.reparations_requested!=after.reparations_requested
        || (before.reparations_requested
            && (before.reparations.payer!=after.reparations.payer
                || before.reparations.claimant!=after.reparations.claimant))
        || before.concede_defeat_requested!=after.concede_defeat_requested
        || before.trade_power_requested!=after.trade_power_requested
        || (before.trade_power_requested
            && (before.trade_power.source!=after.trade_power.source
                || before.trade_power.beneficiary!=after.trade_power.beneficiary))
        || before.annul_treaties_requested!=after.annul_treaties_requested
        || (before.annul_treaties_requested
            && (before.annul_count!=after.annul_count
                || !annul_context_pairs_valid(before)
                || !annul_context_pairs_valid(after)))
        || before.humiliate_rival_requested!=after.humiliate_rival_requested
        || (before.humiliate_rival_requested
            && (before.humiliate_rival_country!=after.humiliate_rival_country
                || before.humiliate_rival_beneficiary!=after.humiliate_rival_beneficiary))
        || before.show_strength_requested!=after.show_strength_requested
        || (before.show_strength_requested
            && (before.show_strength_country!=after.show_strength_country
                || before.show_strength_beneficiary!=after.show_strength_beneficiary))
        || before.force_religion_requested!=after.force_religion_requested
        || (before.force_religion_requested
            && (before.force_religion_country!=after.force_religion_country
                || before.force_religion_beneficiary!=after.force_religion_beneficiary))
        || before.return_core_requested!=after.return_core_requested
        || before.revoke_core_requested!=after.revoke_core_requested
        || before.release_subject_requested!=after.release_subject_requested
        || (before.release_subject_requested
            && (before.release_subject.count!=after.release_subject.count
                || before.release_subject.source!=after.release_subject.source
                || before.release_subject.beneficiary!=after.release_subject.beneficiary
                || !subject_effect_context_valid(before.release_subject)
                || !subject_effect_context_valid(after.release_subject)))
        || before.transfer_subject_requested!=after.transfer_subject_requested
        || (before.transfer_subject_requested
            && (before.transfer_subject.count!=after.transfer_subject.count
                || before.transfer_subject.source!=after.transfer_subject.source
                || before.transfer_subject.beneficiary!=after.transfer_subject.beneficiary
                || !subject_effect_context_valid(before.transfer_subject)
                || !subject_effect_context_valid(after.transfer_subject)))
        || before.release_nation_requested!=after.release_nation_requested
        || (before.release_nation_requested
            && (before.release_nation.country!=after.release_nation.country
                || before.release_nation.source!=after.release_nation.source
                || before.release_nation.count!=after.release_nation.count
                || !country_territory_effect_context_valid(before.release_nation)
                || !country_territory_effect_context_valid(after.release_nation)))
        || before.force_vassalization_requested!=after.force_vassalization_requested
        || (before.force_vassalization_requested
            && (before.force_vassalization.country!=after.force_vassalization.country
                || before.force_vassalization.beneficiary!=after.force_vassalization.beneficiary
                || !country_relation_effect_context_valid(before.force_vassalization)
                || !country_relation_effect_context_valid(after.force_vassalization)))
        || before.form_personal_union_requested!=after.form_personal_union_requested
        || (before.form_personal_union_requested
            && (before.form_personal_union.country!=after.form_personal_union.country
                || before.form_personal_union.beneficiary!=after.form_personal_union.beneficiary
                || !country_relation_effect_context_valid(before.form_personal_union)
                || !country_relation_effect_context_valid(after.form_personal_union)))
        || before.grant_independence_requested!=after.grant_independence_requested
        || (before.grant_independence_requested
            && (before.grant_independence.country!=after.grant_independence.country
                || before.grant_independence.overlord!=after.grant_independence.overlord
                || !grant_independence_effect_context_valid(before.grant_independence)
                || !grant_independence_effect_context_valid(after.grant_independence)))
        || before.full_annexation_requested!=after.full_annexation_requested
        || (before.full_annexation_requested
            && (before.full_annexation.country!=after.full_annexation.country
                || before.full_annexation.source!=after.full_annexation.source
                || before.full_annexation.count!=after.full_annexation.count
                || !country_territory_effect_context_valid(before.full_annexation)
                || !country_territory_effect_context_valid(after.full_annexation)))
        || (before.return_core_requested
            && (before.return_core.count!=after.return_core.count
                || !core_effect_context_valid(before.return_core)
                || !core_effect_context_valid(after.return_core)))
        || (before.revoke_core_requested
            && (before.revoke_core.count!=after.revoke_core.count
                || !core_effect_context_valid(before.revoke_core)
                || !core_effect_context_valid(after.revoke_core))))
        return false;
    for (unsigned i=0;i<before.country_count;++i)
        if (!before.countries[i].country || before.countries[i].country!=after.countries[i].country)
            return false;
    for (unsigned i=0;i<before.province_count;++i)
        if (before.provinces[i].id<=0 || before.provinces[i].id!=after.provinces[i].id)
            return false;
    if (!before.annul_treaties_requested
        && (!annul_context_pairs_valid(before) || !annul_context_pairs_valid(after)))
        return false;
    if (!before.return_core_requested
        && (!core_effect_context_valid(before.return_core)
            || !core_effect_context_valid(after.return_core)))
        return false;
    if (!before.revoke_core_requested
        && (!core_effect_context_valid(before.revoke_core)
            || !core_effect_context_valid(after.revoke_core)))
        return false;
    if (before.annul_treaties_requested)
        for (unsigned i=0;i<before.annul_count;++i)
            if (before.annul_treaties[i].country!=after.annul_treaties[i].country
                || before.annul_treaties[i].partner!=after.annul_treaties[i].partner)
                return false;
    if (before.return_core_requested)
        for (unsigned i=0;i<before.return_core.count;++i)
            if (before.return_core.rows[i].province_id
                    !=after.return_core.rows[i].province_id
                || before.return_core.rows[i].target_core_owner
                    !=after.return_core.rows[i].target_core_owner)
                return false;
    if (before.revoke_core_requested)
        for (unsigned i=0;i<before.revoke_core.count;++i)
            if (before.revoke_core.rows[i].province_id
                    !=after.revoke_core.rows[i].province_id
                || before.revoke_core.rows[i].target_core_owner
                    !=after.revoke_core.rows[i].target_core_owner)
                return false;
    if (!before.release_subject_requested
        && (!subject_effect_context_valid(before.release_subject)
            || !subject_effect_context_valid(after.release_subject)))
        return false;
    if (!before.transfer_subject_requested
        && (!subject_effect_context_valid(before.transfer_subject)
            || !subject_effect_context_valid(after.transfer_subject)))
        return false;
    if (!before.release_nation_requested
        && (!country_territory_effect_context_valid(before.release_nation)
            || !country_territory_effect_context_valid(after.release_nation)))
        return false;
    if (!before.force_vassalization_requested
        && (!country_relation_effect_context_valid(before.force_vassalization)
            || !country_relation_effect_context_valid(after.force_vassalization)))
        return false;
    if (!before.form_personal_union_requested
        && (!country_relation_effect_context_valid(before.form_personal_union)
            || !country_relation_effect_context_valid(after.form_personal_union)))
        return false;
    if (!before.grant_independence_requested
        && (!grant_independence_effect_context_valid(before.grant_independence)
            || !grant_independence_effect_context_valid(after.grant_independence)))
        return false;
    if (!before.full_annexation_requested
        && (!country_territory_effect_context_valid(before.full_annexation)
            || !country_territory_effect_context_valid(after.full_annexation)))
        return false;
    if (before.release_subject_requested)
        for (unsigned i=0;i<before.release_subject.count;++i)
            if (before.release_subject.rows[i].country
                    !=after.release_subject.rows[i].country
                || before.release_subject.rows[i].source
                    !=after.release_subject.rows[i].source
                || before.release_subject.rows[i].beneficiary
                    !=after.release_subject.rows[i].beneficiary)
                return false;
    if (before.transfer_subject_requested)
        for (unsigned i=0;i<before.transfer_subject.count;++i)
            if (before.transfer_subject.rows[i].country
                    !=after.transfer_subject.rows[i].country
                || before.transfer_subject.rows[i].source
                    !=after.transfer_subject.rows[i].source
                || before.transfer_subject.rows[i].beneficiary
                    !=after.transfer_subject.rows[i].beneficiary)
                return false;
    if (before.release_nation_requested
        && (before.release_nation.country!=after.release_nation.country
            || before.release_nation.source!=after.release_nation.source
            || before.release_nation.count!=after.release_nation.count)) return false;
    if (before.full_annexation_requested
        && (before.full_annexation.country!=after.full_annexation.country
            || before.full_annexation.source!=after.full_annexation.source
            || before.full_annexation.count!=after.full_annexation.count)) return false;
    if (before.force_vassalization_requested
        && (before.force_vassalization.country!=after.force_vassalization.country
            || before.force_vassalization.beneficiary!=after.force_vassalization.beneficiary)) return false;
    if (before.form_personal_union_requested
        && (before.form_personal_union.country!=after.form_personal_union.country
            || before.form_personal_union.beneficiary!=after.form_personal_union.beneficiary)) return false;
    if (before.grant_independence_requested
        && (before.grant_independence.country!=after.grant_independence.country
            || before.grant_independence.overlord!=after.grant_independence.overlord)) return false;
    return true;
}

inline bool release_nation_established(const State& before,
    const State& after) noexcept {
    const auto& left=before.release_nation;
    const auto& right=after.release_nation;
    if (!before.release_nation_requested || !after.release_nation_requested
        || !same_observation_context(before,after)
        || !country_territory_effect_context_valid(left)
        || !country_territory_effect_context_valid(right)
        || left.country!=right.country || left.source!=right.source
        || left.count!=right.count || right.owned_count_after<=left.owned_count_before
        || right.source_owned_count_after>=left.source_owned_count_before)
        return false;
    bool moved=false;
    for (unsigned i=0;i<left.count;++i) {
        const auto& before_row=left.rows[i];
        const auto& after_row=right.rows[i];
        if (before_row.province_id!=after_row.province_id
            || !before_row.complete || !after_row.complete
            || before_row.owner!=left.source
            || (after_row.owner!=left.country && after_row.owner!=left.source))
            return false;
        if (after_row.owner==left.country) moved=true;
    }
    return moved;
}

inline bool full_annexation_established(const State& before,
    const State& after) noexcept {
    const auto& left=before.full_annexation;
    const auto& right=after.full_annexation;
    if (!before.full_annexation_requested || !after.full_annexation_requested
        || !same_observation_context(before,after)
        || !country_territory_effect_context_valid(left)
        || !country_territory_effect_context_valid(right)
        || left.country!=right.country || left.source!=right.source
        || left.count!=right.count || right.owned_count_after!=0)
        return false;
    for (unsigned i=0;i<left.count;++i) {
        const auto& before_row=left.rows[i];
        const auto& after_row=right.rows[i];
        if (before_row.province_id!=after_row.province_id
            || !before_row.complete || !after_row.complete
            || before_row.owner!=left.country || after_row.owner!=left.source)
            return false;
    }
    return true;
}

inline bool force_vassalization_established(const State& before,
    const State& after) noexcept {
    const auto& left=before.force_vassalization;
    const auto& right=after.force_vassalization;
    if (!before.force_vassalization_requested || !after.force_vassalization_requested
        || !same_observation_context(before,after)
        || !country_relation_effect_context_valid(left)
        || !country_relation_effect_context_valid(right)
        || left.country!=right.country || left.beneficiary!=right.beneficiary
        || !right.relation_active_after || !right.is_overlord_after
        || !right.subject_type_after[0]) return false;
    return left.relation_active_after!=right.relation_active_after
        || left.is_overlord_after!=right.is_overlord_after
        || std::strcmp(left.subject_type_after,right.subject_type_after)!=0;
}

inline bool form_personal_union_established(const State& before,
    const State& after) noexcept {
    const auto& left=before.form_personal_union;
    const auto& right=after.form_personal_union;
    if (!before.form_personal_union_requested || !after.form_personal_union_requested
        || !same_observation_context(before,after)
        || !country_relation_effect_context_valid(left)
        || !country_relation_effect_context_valid(right)
        || left.country!=right.country || left.beneficiary!=right.beneficiary
        || !right.relation_active_after || !right.is_overlord_after
        || std::strcmp(right.subject_type_after,"personal_union")!=0)
        return false;
    return left.relation_active_after!=right.relation_active_after
        || left.is_overlord_after!=right.is_overlord_after
        || std::strcmp(left.subject_type_after,right.subject_type_after)!=0;
}

// The pairwise endpoint is observable, but independence requires proving that
// no other overlord remains.  grant_independence_established accepts the
// consequence only when the bounded all-overlords reader supplied a complete
// after snapshot with zero remaining overlords.
inline bool grant_independence_established(const State& before,
    const State& after) noexcept {
    const auto& left=before.grant_independence;
    const auto& right=after.grant_independence;
    if (!before.grant_independence_requested || !after.grant_independence_requested
        || !same_observation_context(before,after)
        || !grant_independence_effect_context_valid(left)
        || !grant_independence_effect_context_valid(right)
        || left.country!=right.country || left.overlord!=right.overlord
        || right.relation_active_after || right.is_overlord_after
        || !left.overlord_scan_complete_before
        || !right.overlord_scan_complete_after
        || !right.no_other_overlords_after
        || right.overlord_count_after!=0) return false;
    // In a native independence war the subject link can already be removed
    // at declaration. The selected Grant marker prevents its restoration at
    // peace; settlement still requires the complete zero-overlord result.
    const bool link_removed=left.relation_active_before && left.is_overlord_before
        && left.overlord_count_before>=1;
    const bool wartime_independent=!left.relation_active_before
        && !left.is_overlord_before && left.overlord_count_before==0
        && left.no_other_overlords_before;
    return link_removed || wartime_independent;
}

inline bool country_terms_any_requested(const State& state) noexcept {
    return state.release_nation_requested || state.force_vassalization_requested
        || state.form_personal_union_requested || state.grant_independence_requested
        || state.full_annexation_requested;
}

struct MoneyAssessment {
    std::int64_t paid_raw=0,total_credit_raw=0;
    bool verified=false;
};

struct PrestigeAssessment {
    std::int32_t conceding_before=0,conceding_after=0;
    std::int32_t beneficiary_before=0,beneficiary_after=0;
    bool readable=false;
};

// Report actual engine values. A refusal can also impose native prestige
// penalties, and accepted values may clamp at the country prestige bounds.
inline PrestigeAssessment assess_prestige(const State& before,const State& after,
    std::uint64_t conceding,std::uint64_t beneficiary) noexcept {
    PrestigeAssessment result{};
    if (!conceding || !beneficiary || conceding==beneficiary
        || !before.concede_defeat_requested || !same_observation_context(before,after)) return result;
    unsigned conceding_count=0,beneficiary_count=0;
    for (unsigned i=0;i<before.country_count;++i) {
        const auto& left=before.countries[i];
        const auto& right=after.countries[i];
        if (left.country!=conceding && left.country!=beneficiary) continue;
        if (!left.prestige_readable || !right.prestige_readable
            || left.prestige_raw < -100000 || left.prestige_raw > 100000
            || right.prestige_raw < -100000 || right.prestige_raw > 100000) return result;
        if (left.country==conceding) {
            ++conceding_count; result.conceding_before=left.prestige_raw;
            result.conceding_after=right.prestige_raw;
        } else {
            ++beneficiary_count; result.beneficiary_before=left.prestige_raw;
            result.beneficiary_after=right.prestige_raw;
        }
    }
    result.readable=conceding_count==1 && beneficiary_count==1;
    return result;
}

inline MoneyAssessment assess_money(const State& before,const State& after,
    std::uint64_t payer,std::int32_t requested_raw) noexcept {
    MoneyAssessment result{};
    if (!payer || requested_raw<=0 || !same_observation_context(before,after)) return result;
    unsigned payer_count=0;
    bool other_debits=false,duplicate=false;
    for (unsigned i=0;i<before.country_count;++i) {
        const auto& left=before.countries[i];
        for (unsigned j=0;j<i;++j)
            if (before.countries[j].country==left.country) duplicate=true;
        const std::int64_t delta=static_cast<std::int64_t>(after.countries[i].treasury_raw)-left.treasury_raw;
        if (left.country==payer) { ++payer_count; result.paid_raw=-delta; }
        else if (delta<0) other_debits=true;
        else result.total_credit_raw+=delta;
    }
    result.verified=payer_count==1 && !duplicate && !other_debits
        && result.paid_raw==requested_raw && result.total_credit_raw==requested_raw;
    return result;
}

inline bool province_transferred(const State& before,const State& after,
    unsigned index,std::uint64_t beneficiary) noexcept {
    return beneficiary && same_observation_context(before,after)
        && index<before.province_count && before.provinces[index].owner!=beneficiary
        && after.provinces[index].owner==beneficiary
        // A third country can retain occupation in a different war. Cession
        // promises ownership; control is independently observed and reported.
        && before.provinces[index].controller && after.provinces[index].controller;
}

inline bool reparations_established(const State& before,const State& after,
    std::uint64_t payer,std::uint64_t claimant) noexcept {
    if (!payer || !claimant || payer==claimant
        || !before.reparations_requested || !after.reparations_requested
        || !before.reparations.complete || !after.reparations.complete
        || !same_observation_context(before,after)) return false;
    if (before.reparations.payer!=payer || before.reparations.claimant!=claimant
        || after.reparations.payer!=payer || after.reparations.claimant!=claimant
        || before.reparations.active || !after.reparations.active
        || !after.reparations.present) return false;
    return after.reparations.start_date_raw<=after.date_raw
        && after.date_raw<after.reparations.end_date_raw;
}

inline bool trade_power_established(const State& before,const State& after,
    std::uint64_t source,std::uint64_t beneficiary) noexcept {
    if (!source || !beneficiary || source==beneficiary
        || !before.trade_power_requested || !after.trade_power_requested
        || !before.trade_power.complete || !after.trade_power.complete
        || !same_observation_context(before,after)) return false;
    const auto& before_trade=before.trade_power;
    const auto& after_trade=after.trade_power;
    if (before_trade.source!=source || before_trade.beneficiary!=beneficiary
        || after_trade.source!=source || after_trade.beneficiary!=beneficiary
        || !after_trade.present || !after_trade.peace_treaty
        || after_trade.amount_raw<=0 || after_trade.amount_scale<=0
        || after_trade.start_date_raw>after.date_raw) return false;
    const bool changed_since_before=!before_trade.present
        || !before_trade.peace_treaty
        || before_trade.start_date_raw!=after_trade.start_date_raw
        || before_trade.amount_raw!=after_trade.amount_raw
        || before_trade.amount_scale!=after_trade.amount_scale;
    return changed_since_before;
}

inline bool annul_state_values_readable(const AnnulState& state) noexcept {
    return state.complete && state.country && state.partner
        && state.country!=state.partner;
}

inline bool annul_treaty_established(const AnnulState& before,const AnnulState& after,
    std::int32_t date_raw) noexcept {
    if (!annul_state_values_readable(before) || !annul_state_values_readable(after)
        || before.country!=after.country || before.partner!=after.partner
        || !after.present || after.alliance_present
        || after.start_date_raw>date_raw) return false;
    const bool changed_since_before=!before.present
        || before.start_date_raw!=after.start_date_raw
        || before.end_date_raw!=after.end_date_raw;
    return changed_since_before;
}

inline bool annul_treaties_established(const State& before,const State& after) noexcept {
    if (!before.annul_treaties_requested || !after.annul_treaties_requested
        || !same_observation_context(before,after)
        || before.annul_count==0 || before.annul_count>kMaxAnnulPartners)
        return false;
    for (unsigned i=0;i<before.annul_count;++i)
        if (!annul_treaty_established(before.annul_treaties[i],after.annul_treaties[i],
                after.date_raw)) return false;
    return true;
}

inline bool peace_prestige_value_readable(std::int32_t value) noexcept {
    return value>=-100000 && value<=100000;
}

inline bool humiliate_rival_values_readable(const HumiliateRivalState& state) noexcept {
    return state.complete && state.values_readable
        && state.country && state.beneficiary && state.country!=state.beneficiary
        && state.country_tag[0] && state.beneficiary_tag[0]
        && peace_prestige_value_readable(state.country_prestige_raw)
        && peace_prestige_value_readable(state.beneficiary_prestige_raw);
}

inline bool show_strength_values_readable(const ShowStrengthState& state) noexcept {
    return state.complete && state.values_readable
        && state.country && state.beneficiary && state.country!=state.beneficiary
        && state.country_tag[0] && state.beneficiary_tag[0]
        && peace_prestige_value_readable(state.country_prestige_raw)
        && peace_prestige_value_readable(state.beneficiary_prestige_raw)
        && state.powers_requested>=0;
}

inline bool force_religion_values_readable(const ForceReligionState& state) noexcept {
    return state.complete && state.values_readable
        && state.country && state.beneficiary && state.country!=state.beneficiary
        && state.religion[0] && state.beneficiary_religion[0]
        && state.capital_religion[0];
}

inline bool humiliate_rival_established(const State& before,const State& after,
    std::uint64_t country,std::uint64_t beneficiary) noexcept {
    if (!country || !beneficiary || country==beneficiary
        || !before.humiliate_rival_requested || !after.humiliate_rival_requested
        || before.humiliate_rival_country!=country
        || before.humiliate_rival_beneficiary!=beneficiary
        || after.humiliate_rival_country!=country
        || after.humiliate_rival_beneficiary!=beneficiary
        || before.humiliate_rival.country!=country
        || before.humiliate_rival.beneficiary!=beneficiary
        || after.humiliate_rival.country!=country
        || after.humiliate_rival.beneficiary!=beneficiary
        || !same_observation_context(before,after)
        || !humiliate_rival_values_readable(before.humiliate_rival)
        || !humiliate_rival_values_readable(after.humiliate_rival)) return false;
    return after.humiliate_rival.humiliated;
}

inline bool show_strength_established(const State& before,const State& after,
    std::uint64_t country,std::uint64_t beneficiary) noexcept {
    if (!country || !beneficiary || country==beneficiary
        || !before.show_strength_requested || !after.show_strength_requested
        || before.show_strength_country!=country || before.show_strength_beneficiary!=beneficiary
        || after.show_strength_country!=country || after.show_strength_beneficiary!=beneficiary
        || before.show_strength.country!=country
        || before.show_strength.beneficiary!=beneficiary
        || after.show_strength.country!=country
        || after.show_strength.beneficiary!=beneficiary
        || !same_observation_context(before,after)
        || !show_strength_values_readable(before.show_strength)
        || !show_strength_values_readable(after.show_strength)) return false;
    return after.show_strength.humiliated;
}

inline bool force_religion_established(const State& before,const State& after,
    std::uint64_t country,std::uint64_t beneficiary) noexcept {
    if (!country || !beneficiary || country==beneficiary
        || !before.force_religion_requested || !after.force_religion_requested
        || before.force_religion_country!=country
        || before.force_religion_beneficiary!=beneficiary
        || after.force_religion_country!=country
        || after.force_religion_beneficiary!=beneficiary
        || before.force_religion.country!=country
        || before.force_religion.beneficiary!=beneficiary
        || after.force_religion.country!=country
        || after.force_religion.beneficiary!=beneficiary
        || !same_observation_context(before,after)
        || !force_religion_values_readable(before.force_religion)
        || !force_religion_values_readable(after.force_religion)) return false;
    return std::strcmp(after.force_religion.religion,
            after.force_religion.beneficiary_religion)==0
        && std::strcmp(after.force_religion.capital_religion,
            after.force_religion.beneficiary_religion)==0;
}

// Return Core is verified from the observed owner transition.  The old core
// vector is deliberately reported but not prescribed: the engine may retain
// or remove that old core depending on its native rule.  Revoke Core has the
// stronger, proven consequence that the requested core is absent afterwards.
inline bool core_effect_established(const State& before,const State& after,
    bool return_core) noexcept {
    if (!same_observation_context(before,after)) return false;
    const CoreEffectState& before_effect=return_core
        ?before.return_core:before.revoke_core;
    const CoreEffectState& after_effect=return_core
        ?after.return_core:after.revoke_core;
    if (!before_effect.requested || !after_effect.requested
        || before_effect.count==0 || before_effect.count!=after_effect.count
        || !core_effect_context_valid(before_effect)
        || !core_effect_context_valid(after_effect)) return false;
    for (unsigned i=0;i<before_effect.count;++i) {
        const auto& left=before_effect.rows[i];
        const auto& right=after_effect.rows[i];
        if (!core_effect_values_readable(left)
            || !core_effect_values_readable(right)
            || left.province_id!=right.province_id
            || left.target_core_owner!=right.target_core_owner)
            return false;
        const bool changed=left.owner!=right.owner
            || left.controller!=right.controller
            || left.core_owner_present!=right.core_owner_present;
        if (!changed) return false;
        if (return_core) {
            // The candidate must have been a real core of the province before
            // settlement, and the returned province must end up with that
            // country as owner.  Do not hard-code the previous owner tag: R58
            // intentionally exercises a third-country core where it varies.
            if (!left.core_owner_present || left.owner==left.target_core_owner
                || right.owner!=right.target_core_owner) return false;
        } else if (!left.core_owner_present || right.core_owner_present) {
            return false;
        }
    }
    return true;
}

} // namespace bridge::peace_effects
