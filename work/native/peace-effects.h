#pragma once

#include <cstddef>
#include <cstdint>

namespace bridge::peace_effects {

constexpr unsigned kMaxCountries=256;
constexpr unsigned kMaxProvinces=16;

struct CountryBalance {
    std::uint64_t country=0;
    std::int32_t treasury_raw=0;
};

struct ProvinceState {
    std::int32_t id=0;
    std::uint64_t owner=0,controller=0;
};

struct State {
    CountryBalance countries[kMaxCountries]{};
    ProvinceState provinces[kMaxProvinces]{};
    unsigned country_count=0,province_count=0;
    std::int32_t date_raw=0;
    bool complete=false;
};

inline bool same_observation_context(const State& before,const State& after) noexcept {
    if (!before.complete || !after.complete || before.date_raw!=after.date_raw
        || before.country_count>kMaxCountries || before.province_count>kMaxProvinces
        || before.country_count!=after.country_count || before.province_count!=after.province_count)
        return false;
    for (unsigned i=0;i<before.country_count;++i)
        if (!before.countries[i].country || before.countries[i].country!=after.countries[i].country)
            return false;
    for (unsigned i=0;i<before.province_count;++i)
        if (before.provinces[i].id<=0 || before.provinces[i].id!=after.provinces[i].id)
            return false;
    return true;
}

struct MoneyAssessment {
    std::int64_t paid_raw=0,total_credit_raw=0;
    bool verified=false;
};

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

} // namespace bridge::peace_effects
