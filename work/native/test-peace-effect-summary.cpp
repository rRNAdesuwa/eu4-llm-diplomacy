#include <windows.h>
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <cstdio>
#include <type_traits>

#include "peace-effects.h"
#include "peace-execution-wire.h"
#include "peace-payload.h"
#include "alliance-authority-ledger.h"

using bridge::alliance_authority::AlliancePayload;
using bridge::alliance_authority::ActionFamily;
using bridge::peace_payload::PeaceOfferPayload;
using bridge::peace_effects::State;
using bridge::peace_effects::SubjectRelationState;
using bridge::peace_execution_wire::PeaceExecutionRequest;

// This harness executes the production summary serializer with deterministic
// read-only native stubs.  The before state is supplied by the test, while the
// after state is built through execution_peace_effects_after just as it is in
// the observer.  It therefore exercises JSON construction and the aggregate
// terms_verified path instead of restating its boolean expression.
uintptr_t base=0;
struct PeaceProvinceArrayBounds {
    uintptr_t begin=0,end=0;
    std::int32_t count=0;
};
struct NativeShortString {
    char text[16]{};
    std::uint64_t size=0,capacity=0;
};

enum class Scenario { release_accept,release_reject,transfer_accept };
static Scenario scenario=Scenario::release_accept;

static uintptr_t country_record(std::uint64_t handle) noexcept {
    return 0x100000u+static_cast<uintptr_t>(handle)*0x100u;
}

template<class T> static bool read(uintptr_t address,T& output) noexcept {
    output=T{};
    if constexpr (std::is_arithmetic_v<T>) {
        if (address==base+0x233fe58u) {
            output=static_cast<T>(0x5000u);
            return true;
        }
        if (address==0x5000u+0x1dd0u) {
            output=static_cast<T>(100);
            return true;
        }
        if (address==0x9000u+0x18u) {
            output=static_cast<T>(33);
            return true;
        }
        if (address==0x9000u+0x40u) {
            output=static_cast<T>(0xa000u);
            return true;
        }
    }
    if (address==0xa000u+0x10u) {
        if constexpr (std::is_same_v<T,NativeShortString>) {
            NativeShortString value{};
            value.size=4; value.capacity=4;
            output=value;
            return true;
        }
    }
    if (address>=0xa000u+0x10u && address<0xa000u+0x15u) {
        if constexpr (std::is_integral_v<T>) {
            constexpr char value[]="vass";
            output=static_cast<T>(value[address-(0xa000u+0x10u)]);
            return true;
        }
    }
    if constexpr (std::is_arithmetic_v<T>) {
        for (const std::uint64_t handle : {11ull,22ull,33ull}) {
            const uintptr_t record=country_record(handle);
            if (address==record+0xbb0u || address==record+0xcf8u) {
                output=static_cast<T>(address==record+0xbb0u?1000:0);
                return true;
            }
        }
    }
    return false;
}

template<std::size_t N> static bool read(uintptr_t,
    unsigned char (&output)[N]) noexcept {
    std::memset(output,0,N); return false;
}

static bool peace_query_country_pointer(std::uint64_t handle,
    uintptr_t& output) noexcept {
    if (handle!=11 && handle!=22 && handle!=33) { output=0; return false; }
    output=country_record(handle);
    return true;
}

static bool peace_province_tag_from_handle(std::uint64_t handle,
    char (&output)[4]) noexcept {
    const char* tag=handle==11?"ENG":handle==22?"FRA":handle==33?"TYR":nullptr;
    if (!tag) { output[0]=0; return false; }
    std::memcpy(output,tag,4);
    return true;
}

static bool peace_province_read_bounds(PeaceProvinceArrayBounds& output) noexcept {
    output={}; return false;
}

static bool peace_province_record_for_id(const PeaceProvinceArrayBounds&,std::int32_t,
    uintptr_t& output) noexcept {
    output=0; return false;
}

static bool peace_reparations_state_read(std::uint64_t,std::uint64_t,std::int32_t,
    bridge::peace_effects::ReparationsState& output) noexcept {
    output={}; return false;
}

static bool peace_trade_power_state_read(std::uint64_t,std::uint64_t,std::int32_t,
    bridge::peace_effects::TradePowerState& output) noexcept {
    output={}; return false;
}

static bool peace_annul_treaty_state_read(std::uint64_t,std::uint64_t,std::int32_t,
    bridge::peace_effects::AnnulState& output) noexcept {
    output={}; return false;
}

static bool peace_base_term_source_tag(std::uint64_t,char (&output)[4]) noexcept {
    output[0]=0; return false;
}

static bool alliance_query_country(const char* tag,std::uint64_t& output) noexcept {
    if (tag && !std::strcmp(tag,"ENG")) { output=11; return true; }
    if (tag && !std::strcmp(tag,"FRA")) { output=22; return true; }
    if (tag && !std::strcmp(tag,"TYR")) { output=33; return true; }
    output=0; return false;
}

static bool vassal_query_entry(uintptr_t source,std::uint64_t other,uintptr_t& output) noexcept {
    // The after snapshot is the only native read in this harness.  A release
    // accept removes ENG's relation; the rejection leaves it in place.  A
    // transfer accept adds the beneficiary's reverse relation.
    output=0;
    if (scenario==Scenario::release_reject && source==country_record(11)
        && other==33) output=0x9000u;
    if (scenario==Scenario::transfer_accept && source==country_record(22)
        && other==33) output=0x9000u;
    return true;
}

static void line(const char*) noexcept {}

static BOOL summary_read_process_memory(HANDLE,LPCVOID source,LPVOID destination,
    SIZE_T count,SIZE_T* copied) noexcept {
    if (copied) *copied=0;
    if (reinterpret_cast<uintptr_t>(source)!=0xa010u || count!=4 || !destination)
        return FALSE;
    std::memcpy(destination,"vass",count);
    if (copied) *copied=count;
    return TRUE;
}

#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#define ReadProcessMemory summary_read_process_memory
#include "peace-effect-state.inc"
#undef ReadProcessMemory
#pragma GCC diagnostic pop

static void check(bool value,const char* name,unsigned& checks,unsigned& failures) {
    ++checks;
    if (!value) { ++failures; std::printf("failed:%s\n",name); }
}

static SubjectRelationState relation(std::uint64_t country,std::uint64_t source,
    std::uint64_t beneficiary,bool active,bool overlord) {
    SubjectRelationState row{};
    row.country=country; row.source=source; row.beneficiary=beneficiary;
    std::snprintf(row.country_tag,sizeof(row.country_tag),"TYR");
    std::snprintf(row.source_tag,sizeof(row.source_tag),"ENG");
    std::snprintf(row.source_subject_type,sizeof(row.source_subject_type),"vassal");
    row.source_relation_active=active; row.source_is_overlord=overlord;
    if (beneficiary) {
        std::snprintf(row.beneficiary_tag,sizeof(row.beneficiary_tag),"FRA");
        row.beneficiary_relation_readable=true;
    }
    row.complete=true;
    return row;
}

static bridge::peace_effects::State before_state(bool transfer) {
    bridge::peace_effects::State before{};
    before.complete=true; before.date_raw=100; before.country_count=3;
    before.countries[0].country=11; before.countries[1].country=22;
    before.countries[2].country=33;
    if (transfer) {
        before.transfer_subject_requested=true;
        before.transfer_subject={true,11,22,1,{relation(33,11,22,true,true)},true};
    } else {
        before.release_subject_requested=true;
        before.release_subject={true,11,0,1,{relation(33,11,0,true,true)},true};
    }
    return before;
}

static PeaceExecutionRequest request_for(bool transfer) {
    PeaceExecutionRequest request{};
    std::snprintf(request.request_id,sizeof(request.request_id),"summary-subject");
    std::snprintf(request.actor,sizeof(request.actor),"ENG");
    std::snprintf(request.recipient,sizeof(request.recipient),"FRA");
    std::snprintf(request.direction,sizeof(request.direction),"demand");
    request.demand_direction=true;
    if (transfer) {
        request.selected_transfer_subject=true;
        request.transfer_subject=true;
        request.transfer_subject_count=1;
        std::snprintf(request.transfer_subject_countries[0],4,"TYR");
    } else {
        request.selected_release_subject=true;
        request.release_subject=true;
        request.release_subject_count=1;
        std::snprintf(request.release_subject_countries[0],4,"TYR");
    }
    return request;
}

static bool field_verified(const PeaceEffectSummary& summary,const char* key) {
    const char* field=std::strstr(summary.json,key);
    return field && std::strstr(field,"\"verified\":true");
}

int main() {
    unsigned checks=0,failures=0;

    scenario=Scenario::release_accept;
    const auto release_request=request_for(false);
    const auto release_summary=execution_peace_effects_json(
        before_state(false),release_request,true);
    check(release_summary.terms_verified,"release_summary_terms_verified",checks,failures);
    check(field_verified(release_summary,"\"release_subject\":"),
        "release_summary_row_verified",checks,failures);
    check(std::strstr(release_summary.json,"\"complete\":true")!=nullptr,
        "release_summary_complete_json",checks,failures);

    scenario=Scenario::transfer_accept;
    const auto transfer_request=request_for(true);
    auto transfer_before=before_state(true);
    const auto transfer_summary=execution_peace_effects_json(
        transfer_before,transfer_request,true);
    check(transfer_summary.terms_verified,"transfer_summary_terms_verified",checks,failures);
    check(field_verified(transfer_summary,"\"transfer_subject\":"),
        "transfer_summary_row_verified",checks,failures);

    scenario=Scenario::release_reject;
    const auto rejected_summary=execution_peace_effects_json(
        before_state(false),release_request,true);
    check(!rejected_summary.terms_verified,"rejected_summary_not_verified",checks,failures);
    check(!field_verified(rejected_summary,"\"release_subject\":"),
        "rejected_summary_row_not_verified",checks,failures);

    std::printf("{\"passed\":%s,\"checks\":%u,\"failures\":%u,\"native_calls\":true}\n",
        failures?"false":"true",checks,failures);
    return failures?1:0;
}
