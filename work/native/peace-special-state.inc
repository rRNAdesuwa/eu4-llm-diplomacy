// Bounded read-only consequences for the three special peace terms.
// H/S observe the beneficiary's humiliated-rival vector and both countries'
// prestige.  S additionally reads the three native power counters.  F reads
// the three religion names involved in the native SetReligion path.  This
// file performs no writes and never calls a native mutator.

static constexpr std::uint32_t kPeaceHumiliateRivalType=0x30a3u;
static constexpr std::uint32_t kPeaceHumiliateRivalBucket=9u;
static constexpr std::uint32_t kPeaceShowStrengthType=0x2f20u;
static constexpr std::uint32_t kPeaceShowStrengthBucket=10u;
static constexpr std::uint32_t kPeaceForceReligionType=0x2d29u;
static constexpr std::uint32_t kPeaceForceReligionBucket=21u;

static bool execution_peace_effects_read_humiliated_vector(
    std::uint64_t beneficiary,std::uint64_t victim,std::int32_t& victim_index,
    char (&victim_tag)[4],char (&beneficiary_tag)[4]) noexcept {
    victim_index=-1;
    if (!beneficiary || !victim || beneficiary==victim) return false;
    uintptr_t beneficiary_country=0,begin=0;
    std::int32_t count=0;
    if (!peace_query_country_pointer(beneficiary,beneficiary_country)
        || !peace_province_tag_from_handle(victim,victim_tag)
        || !peace_province_tag_from_handle(beneficiary,beneficiary_tag)
        || !read(beneficiary_country+0x2408,begin)
        || !read(beneficiary_country+0x2414,count)
        || count<0 || count>256 || (count && !begin)) return false;
    for (std::int32_t index=0;index<count;++index) {
        std::uint64_t handle=0;
        const uintptr_t item=begin+static_cast<uintptr_t>(index)*sizeof(handle);
        if (!read(item,handle)) return false;
        if (handle!=victim) continue;
        if (victim_index>=0) return false;
        victim_index=index;
    }
    return true;
}

static bool execution_peace_effects_read_special_common(
    std::uint64_t country,std::uint64_t beneficiary,std::int32_t& victim_index,
    char (&country_tag)[4],char (&beneficiary_tag)[4],
    std::int32_t& country_prestige,std::int32_t& beneficiary_prestige,
    std::int32_t* powers,std::int32_t& powers_requested,bool read_powers,
    bool& humiliated) noexcept {
    uintptr_t country_object=0,beneficiary_object=0;
    if (!country || !beneficiary || country==beneficiary
        || !peace_query_country_pointer(country,country_object)
        || !peace_query_country_pointer(beneficiary,beneficiary_object)
        || !read(country_object+0xcf8,country_prestige)
        || !read(beneficiary_object+0xcf8,beneficiary_prestige)
        || !execution_peace_effects_read_humiliated_vector(beneficiary,country,
            victim_index,country_tag,beneficiary_tag)) return false;
    if (read_powers) {
        if (!powers) return false;
        if (!read(beneficiary_object+0x260,powers[0])
            || !read(beneficiary_object+0x264,powers[1])
            || !read(beneficiary_object+0x268,powers[2])
            || !read(base+0x233f910,powers_requested)) return false;
    } else {
        powers_requested=0;
    }
    humiliated=victim_index>=0;
    return true;
}

static bool execution_peace_effects_read_humiliate_state(
    std::uint64_t country,std::uint64_t beneficiary,
    bridge::peace_effects::HumiliateRivalState& output) noexcept {
    output=bridge::peace_effects::HumiliateRivalState{};
    output.country=country; output.beneficiary=beneficiary;
    std::int32_t powers_requested=0;
    bool read_ok=false;
    if (!execution_peace_effects_read_special_common(country,beneficiary,
            output.humiliated_index,output.country_tag,output.beneficiary_tag,
            output.country_prestige_raw,output.beneficiary_prestige_raw,nullptr,
            powers_requested,false,read_ok)) return false;
    output.humiliated=read_ok;
    output.values_readable=true;
    output.complete=true;
    return true;
}

static bool execution_peace_effects_read_show_strength_state(
    std::uint64_t country,std::uint64_t beneficiary,
    bridge::peace_effects::ShowStrengthState& output) noexcept {
    output=bridge::peace_effects::ShowStrengthState{};
    output.country=country; output.beneficiary=beneficiary;
    bool read_ok=false;
    if (!execution_peace_effects_read_special_common(country,beneficiary,
            output.humiliated_index,output.country_tag,output.beneficiary_tag,
            output.country_prestige_raw,output.beneficiary_prestige_raw,
            output.powers,output.powers_requested,true,read_ok)) return false;
    output.humiliated=read_ok;
    output.values_readable=true;
    output.complete=true;
    return true;
}

static constexpr bool execution_peace_effects_valid_religion_char(char value) noexcept {
    return (value>='A' && value<='Z') || (value>='a' && value<='z')
        || (value>='0' && value<='9') || value=='_';
}

static bool execution_peace_effects_read_religion_name(uintptr_t religion,
    char (&output)[bridge::peace_effects::kMaxReligionKey]) noexcept {
    output[0]=0;
    if (!religion) return false;
    std::size_t size=0,capacity=0;
    if (!read(religion+0xa0,size) || !read(religion+0xa8,capacity)
        || size==0 || size>=bridge::peace_effects::kMaxReligionKey
        || capacity<size) return false;
    uintptr_t data=0;
    if (capacity>15) {
        if (!read(religion+0x90,data) || !data) return false;
    } else if (size>15) {
        return false;
    } else {
        data=religion+0x90;
    }
    for (std::size_t index=0;index<size;++index)
        if (!read(data+index,output[index])
            || !execution_peace_effects_valid_religion_char(output[index])) {
            output[0]=0; return false;
        }
    output[size]=0;
    return true;
}

static bool execution_peace_effects_read_force_religion_state(
    std::uint64_t country,std::uint64_t beneficiary,
    bridge::peace_effects::ForceReligionState& output) noexcept {
    output=bridge::peace_effects::ForceReligionState{};
    output.country=country; output.beneficiary=beneficiary;
    uintptr_t country_object=0,beneficiary_object=0,country_religion=0;
    uintptr_t beneficiary_religion=0,capital=0,capital_religion=0;
    if (!country || !beneficiary || country==beneficiary
        || !peace_query_country_pointer(country,country_object)
        || !peace_query_country_pointer(beneficiary,beneficiary_object)
        || !read(country_object+0xf30,country_religion)
        || !read(beneficiary_object+0xf30,beneficiary_religion)
        || !read(country_object+0x14b0,capital) || !capital
        || !read(capital+0x448,capital_religion)
        || !execution_peace_effects_read_religion_name(country_religion,
            output.religion)
        || !execution_peace_effects_read_religion_name(beneficiary_religion,
            output.beneficiary_religion)
        || !execution_peace_effects_read_religion_name(capital_religion,
            output.capital_religion)) return false;
    output.values_readable=true;
    output.complete=true;
    return true;
}

static bool execution_peace_effects_capture_special(
    const AlliancePayload& payload,
    const bridge::peace_execution_wire::PeaceExecutionRequest& request,
    PeaceEffectState& output) noexcept {
    const auto* offer=payload.peace.offer.get();
    if (!offer || !offer->valid()) return false;
    const bool demand=offer->direction==1;
    const std::uint64_t expected_payer=demand?payload.recipient20:payload.actor10;
    const std::uint64_t expected_claimant=demand?payload.actor10:payload.recipient20;
    const std::uint64_t expected_country=expected_payer;
    const std::uint64_t expected_beneficiary=expected_claimant;
    if (offer->payer!=expected_payer || offer->claimant!=expected_claimant) return false;

    output.humiliate_rival_requested=request.selected_humiliate_rival;
    output.humiliate_rival_country=expected_country;
    output.humiliate_rival_beneficiary=expected_beneficiary;
    if (output.humiliate_rival_requested) {
        unsigned matches=0;
        for (unsigned i=0;i<offer->term_count;++i) {
            const auto& term=offer->terms[i];
            if (!term.selected || term.type_id!=kPeaceHumiliateRivalType
                || term.bucket!=kPeaceHumiliateRivalBucket) continue;
            if (!term.complete || term.field10!=expected_payer
                || term.field18!=expected_claimant || term.field22!=expected_country)
                return false;
            ++matches;
        }
        if (matches!=1 || !execution_peace_effects_read_humiliate_state(
                expected_country,expected_beneficiary,output.humiliate_rival)) return false;
    }

    output.show_strength_requested=request.selected_show_strength;
    output.show_strength_country=expected_country;
    output.show_strength_beneficiary=expected_beneficiary;
    if (output.show_strength_requested) {
        unsigned matches=0;
        for (unsigned i=0;i<offer->term_count;++i) {
            const auto& term=offer->terms[i];
            if (!term.selected || term.type_id!=kPeaceShowStrengthType
                || term.bucket!=kPeaceShowStrengthBucket) continue;
            if (!term.complete || term.field10!=expected_payer
                || term.field18!=expected_claimant || term.field22!=expected_country)
                return false;
            ++matches;
        }
        if (matches!=1 || !execution_peace_effects_read_show_strength_state(
                expected_country,expected_beneficiary,output.show_strength)) return false;
    }

    output.force_religion_requested=request.selected_force_religion;
    output.force_religion_country=expected_country;
    output.force_religion_beneficiary=expected_beneficiary;
    if (output.force_religion_requested) {
        unsigned matches=0;
        for (unsigned i=0;i<offer->term_count;++i) {
            const auto& term=offer->terms[i];
            if (!term.selected || term.type_id!=kPeaceForceReligionType
                || term.bucket!=kPeaceForceReligionBucket) continue;
            if (!term.complete || term.field10!=expected_payer
                || term.field18!=expected_claimant || term.field22!=expected_country)
                return false;
            ++matches;
        }
        if (matches!=1 || !execution_peace_effects_read_force_religion_state(
                expected_country,expected_beneficiary,output.force_religion)) return false;
    }
    return true;
}

static bool execution_peace_effects_read_special_after(
    const PeaceEffectState& before,PeaceEffectState& output) noexcept {
    output.humiliate_rival_requested=before.humiliate_rival_requested;
    output.humiliate_rival_country=before.humiliate_rival_country;
    output.humiliate_rival_beneficiary=before.humiliate_rival_beneficiary;
    if (output.humiliate_rival_requested
        && !execution_peace_effects_read_humiliate_state(output.humiliate_rival_country,
            output.humiliate_rival_beneficiary,output.humiliate_rival)) return false;
    output.show_strength_requested=before.show_strength_requested;
    output.show_strength_country=before.show_strength_country;
    output.show_strength_beneficiary=before.show_strength_beneficiary;
    if (output.show_strength_requested
        && !execution_peace_effects_read_show_strength_state(output.show_strength_country,
            output.show_strength_beneficiary,output.show_strength)) return false;
    output.force_religion_requested=before.force_religion_requested;
    output.force_religion_country=before.force_religion_country;
    output.force_religion_beneficiary=before.force_religion_beneficiary;
    if (output.force_religion_requested
        && !execution_peace_effects_read_force_religion_state(
            output.force_religion_country,output.force_religion_beneficiary,
            output.force_religion)) return false;
    return true;
}

