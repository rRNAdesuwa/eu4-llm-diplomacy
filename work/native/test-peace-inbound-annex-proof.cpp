#include <cstdint>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include <type_traits>
#include <utility>

#include "alliance-authority-ledger.h"
#include "peace-execution-wire.h"
#include "peace-payload-ref.h"

// Focused production-helper test.  It does not load the bridge DLL or a game
// process.  The native reader/capture callbacks below are inert, while the
// helper from peace-inbound-context.inc is exercised with sealed payloads and
// a typed preflight request.
static std::uintptr_t base=0;

template <typename T>
static bool read(std::uintptr_t,T& output) noexcept {
    output=T{};
    return false;
}

struct PeaceWarRegistryEntry {
    std::uintptr_t native_reference=0;
    char public_id[30]{};
};

struct PeaceWarReferenceList {
    std::uintptr_t references[32]{};
    unsigned count=0;
    bool complete=false,truncated=false;
};

using bridge::alliance_authority::ActionFamily;
using bridge::alliance_authority::AlliancePayload;

static bool peace_query_country_pointer(std::uint64_t handle,
    std::uintptr_t& output) noexcept {
    if (handle==11u) { output=0x1100u; return true; } // ENG
    if (handle==22u) { output=0x2200u; return true; } // FRA
    if (handle==33u) { output=0x3300u; return true; } // extra conflicting owner
    output=0;
    return false;
}

static bool peace_province_tag_from_handle(std::uint64_t handle,
    char (&output)[4]) noexcept {
    const char* tag=handle==11u?"ENG":handle==22u?"FRA":handle==33u?"AMG":nullptr;
    if (!tag) { output[0]=0; return false; }
    std::memcpy(output,tag,4u);
    return true;
}

[[maybe_unused]] static bool peace_base_term_source_tag(std::uint64_t handle,
    char (&output)[4]) noexcept {
    return peace_province_tag_from_handle(handle,output);
}

static bool peace_capture_offer_snapshot(const void* native_offer,
    bridge::peace_payload::PeacePayloadRef& output) noexcept {
    // This callback intentionally never dereferences a native address.  The
    // tests below use the sealed preflight proof path, where live_offer may be
    // absent after settlement.
    (void)native_offer;
    output.reset();
    return false;
}

[[maybe_unused]] static bool peace_query_pair_references(std::uintptr_t,unsigned,
    PeaceWarReferenceList&) noexcept { return false; }

static bool peace_query_reference_sets_equal(const PeaceWarReferenceList&,
    const PeaceWarReferenceList&) noexcept { return false; }

static const PeaceWarRegistryEntry* peace_query_register_war(
    std::uintptr_t) noexcept { return nullptr; }

[[maybe_unused]] static void line(const char*) noexcept {}

#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#include "peace-inbound-context.inc"
#pragma GCC diagnostic pop

using bridge::peace_execution_wire::PeaceExecutionRequest;
using bridge::peace_payload::PeaceOfferPayload;
using bridge::peace_payload::PeacePayloadRef;
using bridge::peace_payload::PeaceTermPayload;

static PeaceTermPayload cede(std::uint32_t id,std::uint64_t owner,
    std::uint32_t index,bool selected=true) {
    PeaceTermPayload term{};
    term.type_id=0x2d25u;
    term.bucket=3u;
    term.field10=11u; // offer.payer: ENG
    term.field18=22u; // offer.claimant: FRA
    term.field22=owner;
    term.extra30=22u;
    term.nested_id=id;
    term.nested_present=true;
    term.selected=selected?1u:0u;
    term.selected_index=selected?index:bridge::peace_payload::kInvalidSelectedIndex;
    term.complete=true;
    return term;
}

static PeacePayloadRef sealed_offer(std::initializer_list<PeaceTermPayload> terms) {
    PeacePayloadRef reference=PeacePayloadRef::allocate();
    auto* offer=reference.builder();
    if (!offer) return {};
    offer->payer=11u;
    offer->claimant=22u;
    offer->direction=0u;
    offer->term_count=static_cast<std::uint32_t>(terms.size());
    unsigned index=0;
    for (const auto& term:terms) offer->terms[index++]=term;
    offer->complete=true;
    if (!reference.seal()) return {};
    return reference;
}

static PeaceExecutionRequest proven_request(const char* country="ENG",
    const char* beneficiary="FRA") {
    PeaceExecutionRequest request{};
    request.selected_full_annexation=true;
    request.full_annexation=true;
    std::snprintf(request.annex_country,sizeof(request.annex_country),"%s",country);
    std::snprintf(request.annex_beneficiary,sizeof(request.annex_beneficiary),
        "%s",beneficiary);
    return request;
}

static bool valid_preflight_without_live_offer() {
    PeacePayloadRef reference=sealed_offer({cede(173,11u,0)});
    const auto* sealed=reference.get();
    if (!sealed) return false;
    PeaceExecutionRequest request=proven_request();
    PeaceExecutionRequest derived{};
    InboundFullAnnexProof proof{};
    if (!inbound_full_annex_prepare(*sealed,nullptr,&request,derived,proof)) return false;
    return proof.preflight_proof_reused
        && proof.request_identity_matches
        && proof.derived
        && !proof.live_offer_present
        && !proof.native_check_called
        && proof.selected_cede_complete
        && proof.selected_cede_unique
        && proof.selected_cede_count==1u
        && std::strcmp(proof.owner_tag,"ENG")==0
        && std::strcmp(proof.beneficiary_tag,"FRA")==0
        && derived.selected_full_annexation
        && derived.full_annexation
        && std::strcmp(derived.annex_country,"ENG")==0
        && std::strcmp(derived.annex_beneficiary,"FRA")==0
        && std::strcmp(proof.reason_code,"PREFLIGHT_PROOF_REUSED")==0;
}

static bool wrong_roles_rejected() {
    PeacePayloadRef reference=sealed_offer({cede(173,11u,0)});
    const auto* sealed=reference.get();
    if (!sealed) return false;
    for (const auto& pair: {std::pair<const char*,const char*>("AMG","FRA"),
                            std::pair<const char*,const char*>("ENG","AMG")}) {
        PeaceExecutionRequest request=proven_request(pair.first,pair.second);
        PeaceExecutionRequest derived{};
        InboundFullAnnexProof proof{};
        if (inbound_full_annex_prepare(*sealed,nullptr,&request,derived,proof)) return false;
        if (std::strcmp(proof.reason_code,
                "PREFLIGHT_FULL_ANNEX_IDENTITY_MISMATCH")!=0) return false;
        if (proof.derived || proof.native_check_called) return false;
    }
    return true;
}

static bool malformed_or_unselected_rejected() {
    PeacePayloadRef unselected=sealed_offer({cede(173,11u,0,false)});
    PeacePayloadRef malformed=sealed_offer({cede(173,11u,0)});
    auto* malformed_builder=const_cast<PeaceTermPayload*>(&malformed.get()->terms[0]);
    malformed_builder->complete=false;
    // The sealed object is intentionally made malformed only for this test;
    // collect_cede_identity must reject before any native/live read.
    for (const PeacePayloadRef* reference: {&unselected,&malformed}) {
        const auto* sealed=reference->get();
        if (!sealed) return false;
        PeaceExecutionRequest request=proven_request();
        PeaceExecutionRequest derived{};
        InboundFullAnnexProof proof{};
        if (inbound_full_annex_prepare(*sealed,nullptr,&request,derived,proof)) return false;
        if (proof.derived || proof.native_check_called) return false;
    }
    return true;
}

static bool conflicting_owner_rejected() {
    PeacePayloadRef reference=sealed_offer({cede(173,11u,0),cede(175,33u,1)});
    const auto* sealed=reference.get();
    if (!sealed) return false;
    PeaceExecutionRequest request=proven_request();
    PeaceExecutionRequest derived{};
    InboundFullAnnexProof proof{};
    if (inbound_full_annex_prepare(*sealed,nullptr,&request,derived,proof)) return false;
    return proof.selected_cede_complete
        && !proof.selected_cede_unique
        && proof.selected_cede_count==2u
        && !proof.derived
        && !proof.native_check_called
        && std::strcmp(proof.reason_code,
            "SELECTED_CEDE_IDENTITY_INCOMPLETE")==0;
}

static bool live_path_never_calls_native_address() {
    PeacePayloadRef reference=sealed_offer({cede(173,11u,0)});
    const auto* sealed=reference.get();
    if (!sealed) return false;
    PeaceExecutionRequest derived{};
    InboundFullAnnexProof proof{};
    const std::uintptr_t inert_live=0x12345678u;
    if (inbound_full_annex_prepare(*sealed,
        reinterpret_cast<const void*>(inert_live),nullptr,derived,proof)) return false;
    return proof.live_offer_present
        && !proof.live_snapshot_complete
        && !proof.sealed_snapshot_equal
        && !proof.native_check_called
        && std::strcmp(proof.reason_code,"LIVE_OFFER_SNAPSHOT_MISMATCH")==0;
}

int main() {
    const bool first=valid_preflight_without_live_offer();
    const bool second=wrong_roles_rejected();
    const bool third=malformed_or_unselected_rejected();
    const bool fourth=conflicting_owner_rejected();
    const bool fifth=live_path_never_calls_native_address();
    const bool passed=first && second && third && fourth && fifth;
    std::printf("cases preflight=%s roles=%s malformed=%s conflict=%s live=%s\n",
        first?"ok":"fail",second?"ok":"fail",third?"ok":"fail",
        fourth?"ok":"fail",fifth?"ok":"fail");
    std::printf("peace inbound full-annex proof focused: %s\n",
        passed?"passed":"failed");
    return passed?0:1;
}
