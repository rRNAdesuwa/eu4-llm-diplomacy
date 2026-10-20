#include <cstdint>
#include <cstdio>
#include <cstring>
#include <windows.h>

// Focused contract tests only.  They never attach to a game process: the
// reader and native callbacks are inert, while parser/matching/JSON behavior
// is exercised with bounded synthetic rows.
static std::uintptr_t base=0;
static std::uint64_t observation_creation=1;

template <typename T>
static bool read(std::uintptr_t,T&) noexcept { return false; }

static bool peace_query_country_pointer(std::uint64_t,std::uintptr_t&) noexcept {
    return false;
}

static bool alliance_query_country(const char* tag,std::uint64_t& handle) noexcept {
    if (!tag || std::strlen(tag)!=3u) return false;
    handle=static_cast<std::uint64_t>(static_cast<unsigned char>(tag[0]))
        |(static_cast<std::uint64_t>(static_cast<unsigned char>(tag[1]))<<8u)
        |(static_cast<std::uint64_t>(static_cast<unsigned char>(tag[2]))<<16u);
    return true;
}

static std::uint64_t peace_offer_payer(std::uint64_t actor,
    std::uint64_t recipient,bool demand) noexcept {
    return demand?recipient:actor;
}

static std::uint64_t peace_offer_claimant(std::uint64_t actor,
    std::uint64_t recipient,bool demand) noexcept {
    return demand?actor:recipient;
}

static void line(const char*) noexcept {}

struct PeaceProvinceArrayBounds {
    std::uintptr_t begin=0,end=0,base=0;
    std::uint64_t count=0,span_end=0;
};

static bool peace_province_read_bounds(PeaceProvinceArrayBounds&) noexcept {
    return false;
}

static bool peace_province_record_for_id(const PeaceProvinceArrayBounds&,
    std::int32_t,std::uintptr_t&) noexcept {
    return false;
}

#include "peace-payload.h"
static bool peace_payload_span(std::uintptr_t,unsigned,unsigned,unsigned,
    std::uintptr_t&,unsigned&) noexcept { return false; }

#include "peace-annex-selection.inc"

static bool parser_contract() {
    PeaceAnnexRequest explicit_request{};
    if (!peace_annex_parse_request("AMG","FRA",true,explicit_request)
        || !explicit_request.selection_requested
        || std::strcmp(explicit_request.country,"AMG")!=0
        || std::strcmp(explicit_request.beneficiary,"FRA")!=0) return false;

    PeaceAnnexRequest derived_request{};
    if (!peace_annex_parse_request("AMG","-",false,derived_request)
        || derived_request.selection_requested || derived_request.beneficiary[0]!=0) return false;

    PeaceAnnexRequest bad{};
    return !peace_annex_parse_request("amg","FRA",true,bad)
        && !peace_annex_parse_request("AMG","FR",true,bad)
        && !peace_annex_parse_request("AMG","fra",true,bad);
}

static PeaceAnnexCandidate row(int province_id,const char* owner,
    const char* beneficiary,bool selected=false) {
    PeaceAnnexCandidate value{};
    value.province_id=province_id;
    value.owner=static_cast<std::uint64_t>(static_cast<unsigned char>(owner[0]))
        |(static_cast<std::uint64_t>(static_cast<unsigned char>(owner[1]))<<8u)
        |(static_cast<std::uint64_t>(static_cast<unsigned char>(owner[2]))<<16u);
    value.term_owner=value.owner;
    value.province_owner=value.owner;
    value.beneficiary=static_cast<std::uint64_t>(static_cast<unsigned char>(beneficiary[0]))
        |(static_cast<std::uint64_t>(static_cast<unsigned char>(beneficiary[1]))<<8u)
        |(static_cast<std::uint64_t>(static_cast<unsigned char>(beneficiary[2]))<<16u);
    std::memcpy(value.owner_tag,owner,4u);
    std::memcpy(value.beneficiary_tag,beneficiary,4u);
    value.selected=selected;
    value.readcomplete=true;
    return value;
}

static bool owner_and_claimant_are_separate() {
    PeaceAnnexQueryData data(true);
    if (!data.valid()) return false;
    data.target_country=0x474d41ull; // AMG
    data.requested_beneficiary=0x415246ull; // FRA
    std::memcpy(data.target_country_tag,"AMG",4u);
    std::memcpy(data.requested_beneficiary_tag,"FRA",4u);
    data.candidate_count=2;
    data.candidates[0]=row(173,"AMG","FRA");
    data.candidates[1]=row(177,"ENG","AMG");
    data.target_owned_count=1;
    data.owned_ids[0]=173;
    data.candidate_enumeration_complete=true;
    data.owned_index_complete=true;
    data.source_selection_complete=true;
    data.native_annex_check_called=true;
    peace_annex_update_matches(data);
    return data.candidate_match_count==1u
        && data.requested_candidates_found
        && data.candidate_matches_complete
        && data.candidates[0].owner_match
        && !data.candidates[1].owner_match;
}

static bool json_contract() {
    PeaceAnnexQueryData data(true);
    if (!data.valid()) return false;
    std::memcpy(data.target_country_tag,"AMG",4u);
    std::memcpy(data.requested_beneficiary_tag,"FRA",4u);
    data.candidate_count=1;
    data.candidates[0]=row(173,"AMG","FRA",true);
    data.query_complete=true;
    data.candidate_enumeration_complete=true;
    data.target_owned_count=1;
    data.owned_index_complete=true;
    data.owned_ids[0]=173;
    data.candidate_match_count=1;
    data.candidate_matches_complete=true;
    data.requested_candidates_found=true;
    data.selection_requested=true;
    data.selection_applied=true;
    data.source_selection_complete=true;
    data.action_copy_checked=true;
    data.action_copy_matched=true;
    data.native_annex_check_called=true;
    data.native_annex_bool=true;
    if (!peace_annex_query_json(data)) return false;
    return std::strstr(data.json,"\"action_id\":\"full_annexation\"")
        && std::strstr(data.json,"\"province_id\":173")
        && std::strstr(data.json,"\"owner\":\"AMG\"")
        && std::strstr(data.json,"\"beneficiary\":\"FRA\"")
        && std::strstr(data.json,"\"native_annex_bool\":true")
        && std::strstr(data.json,"\"complete\":true");
}

static bool capacity_is_incomplete() {
    PeaceAnnexQueryData data(true);
    if (!data.valid()) return false;
    data.query_complete=true;
    data.capacity_exceeded=true;
    data.reason_code="NATIVE_PEACE_ANNEX_SELECTION_CAPACITY";
    if (!peace_annex_query_json(data)) return false;
    return !data.complete()
        && std::strstr(data.json,"\"capacity_exceeded\":true")
        && std::strstr(data.json,"NATIVE_PEACE_ANNEX_SELECTION_CAPACITY");
}

int main() {
    return parser_contract() && owner_and_claimant_are_separate()
        && json_contract() && capacity_is_incomplete() ? 0 : 1;
}
