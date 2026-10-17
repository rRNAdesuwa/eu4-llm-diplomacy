#include <cstdint>
#include <cstdio>
#include <cstring>

// The JSON roundtrip fixture calls only the bounded serializer.  Native
// memory readers are deliberately inert because these cases are populated
// directly and must not require a running game.
static std::uintptr_t base=0;
static std::uint64_t observation_creation=1;

template <typename T>
static bool read(std::uintptr_t,T&) noexcept { return false; }

static bool peace_query_country_pointer(std::uint64_t,std::uintptr_t&) noexcept {
    return false;
}

static void line(const char*) noexcept {}

#include "peace-province-candidates.inc"

static constexpr std::uint64_t kFraHandle=0x415246ull;

static bool emit_case(const char* name,PeaceProvinceQueryData& data) {
    if (!peace_province_query_json(data)) {
        std::printf("serializer_failure:%s\n",name);
        return false;
    }
    std::printf("%s\t%s\n",name,data.json);
    return true;
}

static PeaceProvinceCandidate candidate(int32_t province_id,bool selected) {
    PeaceProvinceCandidate value{};
    value.province_id=province_id;
    value.beneficiary=kFraHandle;
    value.selected=selected;
    return value;
}

static bool empty_case() {
    PeaceProvinceQueryData data(true);
    if (!data.valid()) return false;
    data.query_complete=true;
    data.enumeration_complete=true;
    data.direction_raw=1;
    data.direction_verified=true;
    data.selection_requested=false;
    data.requested_candidates_found=false;
    data.toggle_called=false;
    data.parameters_matched=false;
    data.selection_copy_verified=true;
    data.selected_term_records_complete=true;
    return emit_case("empty",data);
}

static bool missing_case() {
    PeaceProvinceQueryData data(true);
    if (!data.valid()) return false;
    data.query_complete=true;
    data.enumeration_complete=true;
    data.direction_raw=1;
    data.direction_verified=true;
    data.candidate_count=1;
    data.candidates[0]=candidate(177,false);
    data.requested_count=1;
    data.requested_ids[0]=2147483647;
    data.requested_beneficiary=kFraHandle;
    data.requested_beneficiary_tag[0]='F';
    data.requested_beneficiary_tag[1]='R';
    data.requested_beneficiary_tag[2]='A';
    data.selection_requested=true;
    data.requested_candidates_found=false;
    data.toggle_called=false;
    data.toggle_call_count=0;
    data.parameters_matched=false;
    data.selection_copy_verified=true;
    data.selected_term_records_complete=true;
    data.reason_code="NATIVE_PEACE_PROVINCE_CANDIDATE_ABSENT";
    return emit_case("missing",data);
}

static bool selected_case() {
    PeaceProvinceQueryData data(true);
    if (!data.valid()) return false;
    data.query_complete=true;
    data.enumeration_complete=true;
    data.direction_raw=1;
    data.direction_verified=true;
    data.candidate_count=1;
    data.candidates[0]=candidate(177,true);
    data.requested_count=1;
    data.requested_ids[0]=177;
    data.requested_beneficiary=kFraHandle;
    data.requested_beneficiary_tag[0]='F';
    data.requested_beneficiary_tag[1]='R';
    data.requested_beneficiary_tag[2]='A';
    data.selection_requested=true;
    data.requested_candidates_found=true;
    data.toggle_called=true;
    data.toggle_call_count=1;
    data.parameters_matched=true;
    data.selected_count=1;
    data.selected_ids[0]=177;
    data.selected_beneficiary=kFraHandle;
    data.selection_copy_verified=true;
    data.selected_term_records_complete=true;
    data.selection_delta_available=true;
    data.selection_delta_raw=5;
    return emit_case("selected",data);
}

static bool reason_state_cases() {
    PeaceProvinceQueryData preserved(true);
    if (!preserved.valid()) return false;
    preserved.reason_code="NATIVE_PEACE_PROVINCE_SELECTION_UNAVAILABLE";
    peace_province_update_request_state(preserved);
    if (std::strcmp(preserved.reason_code,
            "NATIVE_PEACE_PROVINCE_SELECTION_UNAVAILABLE")!=0) return false;

    PeaceProvinceQueryData absent(true);
    if (!absent.valid()) return false;
    absent.candidate_count=1;
    absent.candidates[0]=candidate(177,false);
    absent.requested_count=1;
    absent.requested_ids[0]=2147483647;
    absent.requested_beneficiary=kFraHandle;
    absent.selection_requested=true;
    absent.selected_term_records_complete=true;
    absent.selection_copy_verified=true;
    peace_province_update_request_state(absent);
    if (std::strcmp(absent.reason_code,
            "NATIVE_PEACE_PROVINCE_CANDIDATE_ABSENT")!=0) return false;

    PeaceProvinceQueryData before_copy(true);
    if (!before_copy.valid()) return false;
    before_copy.candidate_count=1;
    before_copy.candidates[0]=candidate(177,false);
    before_copy.requested_count=1;
    before_copy.requested_ids[0]=177;
    before_copy.requested_beneficiary=kFraHandle;
    before_copy.selection_requested=true;
    before_copy.selected_term_records_complete=true;
    // The offer has not yet been compared with its action copy.  A mismatch
    // is therefore not diagnosed during the pre-toggle enumeration phase.
    peace_province_update_request_state(before_copy);
    if (before_copy.reason_code!=nullptr) return false;

    before_copy.selection_copy_verified=true;
    peace_province_update_request_state(before_copy);
    return before_copy.reason_code
        && std::strcmp(before_copy.reason_code,
            "NATIVE_PEACE_PROVINCE_SELECTION_MISMATCH")==0;
}

int main() {
    return empty_case() && missing_case() && selected_case()
        && reason_state_cases() ? 0 : 1;
}
