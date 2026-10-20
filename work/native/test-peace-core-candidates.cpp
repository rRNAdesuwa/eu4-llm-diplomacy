#include <cstdint>
#include <cstdio>
#include <cstring>

// This fixture exercises the QUERY14 parser and bounded public serializer
// without a game process.  Native memory access remains inert.
static std::uintptr_t base=0;
static std::uint64_t observation_creation=1;

template <typename T>
static bool read(std::uintptr_t,T&) noexcept { return false; }

static bool peace_query_country_pointer(std::uint64_t,std::uintptr_t&) noexcept {
    return false;
}

static bool alliance_query_country(const char* tag,std::uint64_t& handle) noexcept {
    if (!tag || std::strlen(tag)!=3) return false;
    handle=(static_cast<std::uint64_t>(static_cast<unsigned char>(tag[0])))
        |(static_cast<std::uint64_t>(static_cast<unsigned char>(tag[1]))<<8)
        |(static_cast<std::uint64_t>(static_cast<unsigned char>(tag[2]))<<16);
    return true;
}

static std::uint64_t peace_offer_payer(std::uint64_t actor,std::uint64_t recipient,
    bool demand) noexcept { return demand?recipient:actor; }
static std::uint64_t peace_offer_claimant(std::uint64_t actor,std::uint64_t recipient,
    bool demand) noexcept { return demand?actor:recipient; }
static void line(const char*) noexcept {}

#include "peace-province-candidates.inc"
#include "peace-payload.h"
static bool peace_payload_span(std::uintptr_t,unsigned,unsigned,unsigned,
    std::uintptr_t&,unsigned&) noexcept { return false; }
#include "peace-core-candidates.inc"

static bool parser_cases() {
    PeaceCoreRequest discovery{};
    if (!peace_core_parse_request("-","-",discovery)
        || discovery.selection_requested || discovery.province_count) return false;
    PeaceCoreRequest selected{};
    if (!peace_core_parse_request("173,177","ENG",selected)
        || !selected.selection_requested || selected.province_count!=2
        || selected.province_ids[0]!=173 || selected.province_ids[1]!=177
        || std::strcmp(selected.core_owner,"ENG")) return false;
    const char* bad_ids[]={"0","173,173","173,","173,177,","-"};
    for (const char* value:bad_ids) {
        PeaceCoreRequest bad{};
        if ((std::strcmp(value,"-")==0 && peace_core_parse_request(value,"ENG",bad))
            || (std::strcmp(value,"-")!=0 && peace_core_parse_request(value,"-",bad))) return false;
    }
    PeaceCoreRequest bad_owner{};
    if (peace_core_parse_request("173","enG",bad_owner)
        || peace_core_parse_request("173","-",bad_owner)) return false;
    return true;
}

static bool json_case() {
    PeaceCoreQueryData data(true);
    if (!data.valid()) return false;
    data.query_complete=true;
    data.candidate_enumeration_complete=true;
    data.candidate_count=1;
    data.candidates[0].province_id=173;
    std::strcpy(data.candidates[0].name_hex,"454e47");
    data.candidates[0].name_readable=true;
    std::strcpy(data.candidates[0].core_owner_tag,"AMG");
    std::strcpy(data.candidates[0].province_owner_tag,"ENG");
    data.candidates[0].record_complete=true;
    data.selection_requested=true;
    data.requested_core_owner=1;
    std::strcpy(data.requested_core_owner_tag,"AMG");
    data.requested_province_count=1;
    data.requested_province_ids[0]=173;
    data.requested_candidates_found=true;
    data.selected_term_count=1;
    data.parameters_matched=true;
    data.selection_applied=true;
    data.selection_records_complete=true;
    data.action_copy_matched=true;
    data.selection_delta_available=true;
    data.selection_delta_raw=8;
    data.aggregate_before_raw=0;
    data.aggregate_after_raw=8;
    if (!peace_core_query_json(data)) return false;
    std::printf("selected\t%s\n",data.json);
    data.selection_requested=false;
    data.requested_candidates_found=false;
    data.requested_province_count=0;
    data.requested_core_owner=0;
    data.requested_core_owner_tag[0]=0;
    data.selection_delta_available=false;
    data.selection_applied=false;
    data.parameters_matched=false;
    data.selected_term_count=0;
    if (!peace_core_query_json(data)) return false;
    std::printf("discovery\t%s\n",data.json);
    return true;
}

int main() { return parser_cases() && json_case()?0:1; }
