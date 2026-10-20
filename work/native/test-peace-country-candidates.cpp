#include <windows.h>
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <cstdio>
#include <string>
#include <type_traits>

// Focused production-chain harness.  It feeds the real candidate reader and
// typed-descriptor check through bounded native-memory stubs; no game process
// or business dispatch is involved.
static std::uintptr_t base=0;
static std::uint64_t observation_creation=1;

struct FakeCountryTerm {
    std::uintptr_t vtable=0;
    std::uint32_t raw_word_at_8=0;
    unsigned char selected=0;
    std::uint64_t field10=0;
    std::uint64_t field18=0;
    std::uint64_t field22=0;
    std::uint64_t extra30=0;
};

static FakeCountryTerm fake_term{};
static const void* active_spec=nullptr;
static std::uintptr_t active_descriptor_slot=0;
static std::uint32_t active_bucket=0;
static bool wrong_descriptor_method=false;
static bool wrong_descriptor_bucket=false;
static std::string emitted_line;

static void* country_descriptor_stub(void*,void* storage) noexcept {
    const std::uint32_t bucket=wrong_descriptor_bucket?active_bucket+1u:active_bucket;
    std::memcpy(storage,&bucket,sizeof(bucket));
    return storage;
}

static void* wrong_country_descriptor_stub(void*,void* storage) noexcept {
    const std::uint32_t bucket=active_bucket;
    std::memcpy(storage,&bucket,sizeof(bucket));
    return storage;
}

template <typename T>
static bool read(std::uintptr_t address,T& output) noexcept {
    output=T{};
    const std::uintptr_t term_address=reinterpret_cast<std::uintptr_t>(&fake_term);
    if (address==term_address) {
        if constexpr (std::is_same_v<T,std::uintptr_t>) {
            output=fake_term.vtable;
            return true;
        }
        return false;
    }
    if (address==term_address+0x20u) {
        if constexpr (std::is_same_v<T,unsigned char>) {
            output=fake_term.selected;
            return true;
        }
        return false;
    }
    if (address==term_address+0x10u) {
        if constexpr (std::is_same_v<T,std::uint64_t>) {
            output=fake_term.field10;
            return true;
        }
        return false;
    }
    if (address==term_address+0x18u) {
        if constexpr (std::is_same_v<T,std::uint64_t>) {
            output=fake_term.field18;
            return true;
        }
        return false;
    }
    if (address==term_address+0x22u) {
        if constexpr (std::is_same_v<T,std::uint64_t>) {
            output=fake_term.field22;
            return true;
        }
        return false;
    }
    if (address==term_address+0x30u) {
        if constexpr (std::is_same_v<T,std::uint64_t>) {
            output=fake_term.extra30;
            return true;
        }
        return false;
    }
    if (active_spec && address==active_descriptor_slot) {
        if constexpr (std::is_same_v<T,std::uintptr_t>) {
            output=wrong_descriptor_method
                ?reinterpret_cast<std::uintptr_t>(&wrong_country_descriptor_stub)
                :reinterpret_cast<std::uintptr_t>(&country_descriptor_stub);
            return true;
        }
        return false;
    }
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

static bool peace_payload_span(std::uintptr_t,unsigned,unsigned,unsigned,
    std::uintptr_t&,unsigned&) noexcept { return false; }

static void line(const char* value) noexcept {
    emitted_line=value?value:"";
}

#include "peace-payload.h"
#include "peace-country-candidates.inc"

static void keep_country_module_entrypoints() noexcept {
    (void)&peace_country_parse_request;
    (void)&peace_country_query_set_prepare;
    (void)&peace_country_query_set_verify_source_copy;
    (void)&peace_country_query_set_json;
    (void)&peace_country_query_set_json_text;
}

static std::uint64_t tag_handle(const char* tag) noexcept {
    return static_cast<std::uint64_t>(static_cast<unsigned char>(tag[0]))
        |(static_cast<std::uint64_t>(static_cast<unsigned char>(tag[1]))<<8u)
        |(static_cast<std::uint64_t>(static_cast<unsigned char>(tag[2]))<<16u);
}

static void configure(const PeaceCountrySpec& spec) noexcept {
    active_spec=&spec;
    active_bucket=spec.bucket;
    base=reinterpret_cast<std::uintptr_t>(&country_descriptor_stub)-spec.descriptor;
    active_descriptor_slot=base+spec.vtable+0x78u;
    fake_term.vtable=base+spec.vtable;
    fake_term.raw_word_at_8=0xdeadbeefu;
    fake_term.selected=0;
    fake_term.field10=tag_handle("ENG");
    fake_term.field18=tag_handle("FRA");
    fake_term.field22=tag_handle("ENG");
    fake_term.extra30=tag_handle("TYR");
    wrong_descriptor_method=false;
    wrong_descriptor_bucket=false;
}

static bool check(bool value,const char* name,unsigned& checks,unsigned& failures) {
    ++checks;
    if (!value) {
        ++failures;
        std::printf("failed:%s\n",name);
    }
    return value;
}

static bool release_and_force_ignore_word_at_8(unsigned& checks,unsigned& failures) {
    const std::uint64_t payer=tag_handle("ENG");
    const std::uint64_t claimant=tag_handle("FRA");

    configure(peace_country_release_spec);
    PeaceCountrySpec spec{}; std::uint32_t discriminator=0;
    PeaceCountryCandidate row{};
    const bool release_found=peace_country_spec_for_term(
        reinterpret_cast<std::uintptr_t>(&fake_term),
        PeaceCountryKind::release_nation,spec,discriminator);
    check(release_found,"release_vtable_spec_found",checks,failures);
    check(discriminator==peace_country_release_spec.type,
        "release_type_from_static_spec",checks,failures);
    check(peace_country_read_candidate(
        reinterpret_cast<std::uintptr_t>(&fake_term),spec,payer,claimant,row),
        "release_candidate_read_with_nonmatching_word_at_8",checks,failures);
    check(row.type==peace_country_release_spec.type
        && row.bucket==peace_country_release_spec.bucket
        && row.country==tag_handle("TYR")
        && row.source==tag_handle("ENG")
        && row.typed_descriptor_valid,
        "release_identity_and_descriptor",checks,failures);

    configure(peace_country_force_spec0);
    spec=PeaceCountrySpec{}; discriminator=0; row=PeaceCountryCandidate{};
    fake_term.field22=tag_handle("TYR");
    fake_term.extra30=tag_handle("AMG");
    const bool force_found=peace_country_spec_for_term(
        reinterpret_cast<std::uintptr_t>(&fake_term),
        PeaceCountryKind::force_vassal,spec,discriminator);
    check(force_found,"force_vtable_spec_found",checks,failures);
    check(discriminator==peace_country_force_spec0.type,
        "force_type_from_static_spec",checks,failures);
    check(peace_country_read_candidate(
        reinterpret_cast<std::uintptr_t>(&fake_term),spec,payer,claimant,row),
        "force_candidate_read_with_nonmatching_word_at_8",checks,failures);
    check(row.type==peace_country_force_spec0.type
        && row.bucket==peace_country_force_spec0.bucket
        && row.country==tag_handle("TYR")
        && row.extra30==tag_handle("AMG")
        && row.typed_descriptor_valid,
        "force_identity_and_descriptor",checks,failures);
    return failures==0;
}

static bool reject_bad_native_identity(unsigned& checks,unsigned& failures) {
    const std::uint64_t payer=tag_handle("ENG");
    const std::uint64_t claimant=tag_handle("FRA");
    PeaceCountrySpec spec=peace_country_release_spec;
    PeaceCountryCandidate row{};

    configure(spec);
    fake_term.vtable=base+peace_country_force_spec0.vtable;
    std::uint32_t discriminator=0;
    check(!peace_country_spec_for_term(
        reinterpret_cast<std::uintptr_t>(&fake_term),
        PeaceCountryKind::release_nation,spec,discriminator),
        "wrong_vtable_rejected",checks,failures);

    configure(peace_country_release_spec);
    fake_term.field10=tag_handle("AMG");
    check(!peace_country_read_candidate(
        reinterpret_cast<std::uintptr_t>(&fake_term),peace_country_release_spec,
        payer,claimant,row),"wrong_roles_rejected",checks,failures);

    configure(peace_country_release_spec);
    wrong_descriptor_method=true;
    check(!peace_country_read_candidate(
        reinterpret_cast<std::uintptr_t>(&fake_term),peace_country_release_spec,
        payer,claimant,row),"wrong_descriptor_method_rejected",checks,failures);

    configure(peace_country_release_spec);
    wrong_descriptor_bucket=true;
    check(!peace_country_read_candidate(
        reinterpret_cast<std::uintptr_t>(&fake_term),peace_country_release_spec,
        payer,claimant,row),"wrong_descriptor_bucket_rejected",checks,failures);
    return failures==0;
}

static bool private_json_is_quoted(unsigned& checks,unsigned& failures) {
    PeaceCountryQueryData data(true);
    const bool allocated=data.valid();
    check(allocated,"private_json_fixture_allocated",checks,failures);
    if (!allocated) return false;
    data.kind=PeaceCountryKind::release_nation;
    data.candidate_count=1;
    auto& row=data.candidates[0];
    row.country_tag[0]='T'; row.country_tag[1]='Y'; row.country_tag[2]='R';
    row.country_tag[3]=0;
    row.source_tag[0]='E'; row.source_tag[1]='N'; row.source_tag[2]='G';
    row.source_tag[3]=0;
    row.field22=tag_handle("ENG");
    row.extra30=tag_handle("TYR");
    row.selected=true;
    row.record_complete=true;
    row.typed_descriptor_valid=true;
    emitted_line.clear();
    peace_country_query_private("candidate-test",data);
    check(emitted_line.find("\"country\":\"TYR\"")!=std::string::npos,
        "private_country_is_json_string",checks,failures);
    check(emitted_line.find("\"source\":\"ENG\"")!=std::string::npos
        && emitted_line.find("\"field22\":\"present\"")!=std::string::npos
        && emitted_line.find("\"extra30\":\"present\"")!=std::string::npos,
        "private_role_fields_are_json_strings",checks,failures);
    check(emitted_line.find("\"country\":TYR")==std::string::npos,
        "private_country_unquoted_form_absent",checks,failures);
    std::printf("private_json=%s",emitted_line.c_str());
    return failures==0;
}

int main() {
    unsigned checks=0,failures=0;
    keep_country_module_entrypoints();
    release_and_force_ignore_word_at_8(checks,failures);
    reject_bad_native_identity(checks,failures);
    private_json_is_quoted(checks,failures);
    std::printf("checks=%u failures=%u\n",checks,failures);
    return failures?1:0;
}
