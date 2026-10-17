#pragma once

// Allocation-free, process-address-independent representation of the
// CPeaceOffer payload.  This is a logical capture contract, not a native
// object overlay.  The capture layer must decode values from the native
// object into these fixed-size fields and must leave complete=false until all
// required fields and bounds have been verified.

#include <array>
#include <cstddef>
#include <cstdint>

namespace bridge::peace_payload {

constexpr std::size_t kMaxPeaceParticipants=256;
constexpr std::size_t kMaxPeaceTerms=512;
constexpr std::size_t kPeaceBucketCount=40;
constexpr std::size_t kMaxPeaceDefinitionNameBytes=128;
constexpr std::uint32_t kInvalidSelectedIndex=0xffffffffu;

struct PeaceParticipantVector {
    std::uint32_t count=0;
    std::array<std::uint64_t,kMaxPeaceParticipants> values{};

    constexpr bool valid() const noexcept {
        return count<=kMaxPeaceParticipants;
    }

    constexpr bool operator==(const PeaceParticipantVector& other) const noexcept {
        if (!valid() || !other.valid() || count!=other.count) return false;
        for (std::uint32_t i=0;i<count;++i) {
            if (values[i]!=other.values[i]) return false;
        }
        return true;
    }

    constexpr bool operator!=(const PeaceParticipantVector& other) const noexcept {
        return !(*this==other);
    }
};

enum class PeaceTermExtraKind : std::uint8_t {
    base=0,
    handle30=1,
    gold=2,
    nested38=3,
    nested38flag40=4,
    unsupported=5,
    definition_name30=6,
    region_name30=7
};

// The type descriptor deliberately contains only static identity metadata.
// vtable_rva and serializer_rva are image-relative code identities used by
// the capture verifier; no process pointer is stored in a payload.
struct PeaceTermTypeDescriptor {
    std::uintptr_t vtable_rva=0;
    std::uint32_t type_id=0;
    std::uint32_t bucket=0;
    std::uintptr_t serializer_rva=0;
    PeaceTermExtraKind extra_kind=PeaceTermExtraKind::unsupported;
};

struct PeaceTermPayload {
    std::uint32_t type_id=0;
    std::uint32_t bucket=0;
    std::uint64_t field10=0;
    std::uint64_t field18=0;
    std::uint64_t field22=0;
    std::uint64_t extra30=0;
    std::array<std::uint8_t,kMaxPeaceDefinitionNameBytes> definition_name{};
    std::uint32_t definition_name_size=0;
    std::uint32_t nested_id=0;
    std::uint8_t flag40=0;
    std::int32_t gold_raw=0;
    std::uint8_t selected=0;
    bool nested_present=false;
    std::uint32_t selected_index=kInvalidSelectedIndex;
    bool complete=false;

    constexpr bool valid() const noexcept {
        if (!complete || type_id==0 || bucket>=kPeaceBucketCount
            || definition_name_size>kMaxPeaceDefinitionNameBytes
            || selected>1u) return false;
        if (nested_present==false && nested_id!=0u) return false;
        if (selected!=0u && selected_index==kInvalidSelectedIndex) return false;
        if (selected==0u && selected_index!=kInvalidSelectedIndex) return false;
        return true;
    }

    constexpr bool operator==(const PeaceTermPayload& other) const noexcept {
        if (!valid() || !other.valid()) return false;
        if (type_id!=other.type_id
            || bucket!=other.bucket
            || field10!=other.field10
            || field18!=other.field18
            || field22!=other.field22
            || extra30!=other.extra30
            || definition_name_size!=other.definition_name_size
            || nested_id!=other.nested_id
            || flag40!=other.flag40
            || gold_raw!=other.gold_raw
            || selected!=other.selected
            || nested_present!=other.nested_present
            || selected_index!=other.selected_index) return false;
        for (std::uint32_t i=0;i<definition_name_size;++i) {
            if (definition_name[i]!=other.definition_name[i]) return false;
        }
        return true;
    }

    constexpr bool operator!=(const PeaceTermPayload& other) const noexcept {
        return !(*this==other);
    }
};

struct PeaceOfferPayload {
    std::uint64_t payer=0;
    std::uint64_t claimant=0;
    std::uint8_t direction=0;
    std::uint8_t flag1b9=0;
    std::array<PeaceParticipantVector,4> participants{};
    std::array<PeaceTermPayload,kMaxPeaceTerms> terms{};
    std::uint32_t term_count=0;
    bool complete=false;

    constexpr bool valid() const noexcept {
        if (!complete || term_count>kMaxPeaceTerms) return false;
        for (const auto& participant: participants) {
            if (!participant.valid()) return false;
        }
        for (std::uint32_t i=0;i<term_count;++i) {
            if (!terms[i].valid()) return false;
        }
        return true;
    }

    constexpr bool operator==(const PeaceOfferPayload& other) const noexcept {
        if (!valid() || !other.valid()) return false;
        if (payer!=other.payer || claimant!=other.claimant
            || direction!=other.direction || flag1b9!=other.flag1b9
            || term_count!=other.term_count) return false;
        for (std::size_t i=0;i<participants.size();++i) {
            if (participants[i]!=other.participants[i]) return false;
        }
        for (std::uint32_t i=0;i<term_count;++i) {
            if (terms[i]!=other.terms[i]) return false;
        }
        return true;
    }

    constexpr bool operator!=(const PeaceOfferPayload& other) const noexcept {
        return !(*this==other);
    }
};

// Static whitelist recovered from the R40 PE contract.  The original R39
// table supplied 34 rows; the R40 factory audit adds the six rows for type
// buckets 3, 5, 6, 15, 30 and 31 below.  Rows using 0x9c9c90
// The 0xac9a50 and 0x9c9c90 serializers carry bounded native string values;
// the capture layer normalizes their first-NUL text into definition_name.
inline constexpr std::array<PeaceTermTypeDescriptor,40>
    kPeaceTermTypeWhitelist{{
    {0x1cd4ad8u,0x2d25u,0x03u,0x9a37d0u,PeaceTermExtraKind::nested38flag40},
    {0x1cd4988u,0x2e00u,0x05u,0x99e630u,PeaceTermExtraKind::nested38},
    {0x1cd3628u,0x301bu,0x06u,0x99e480u,PeaceTermExtraKind::handle30},
    {0x1cd3100u,0x2d28u,0x0fu,0x99e480u,PeaceTermExtraKind::handle30},
    {0x1cd41c8u,0x35c5u,0x1eu,0x99e480u,PeaceTermExtraKind::handle30},
    {0x1cd17f8u,0x3c06u,0x1fu,0x99e480u,PeaceTermExtraKind::handle30},
    {0x1cd1a90u,0x3c05u,0x02u,0x99e480u,PeaceTermExtraKind::handle30},
    {0x1cd4d78u,0x2d2cu,0x01u,0x99e480u,PeaceTermExtraKind::handle30},
    {0x1cd1948u,0x3c0du,0x26u,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd1f00u,0x3662u,0x27u,0xac9a50u,PeaceTermExtraKind::definition_name30},
    {0x1cd2048u,0x396fu,0x21u,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd2190u,0x2d2bu,0x00u,0x9b42b0u,PeaceTermExtraKind::gold},
    {0x1cd22d8u,0x3a4cu,0x22u,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd2420u,0x35d2u,0x1du,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd2568u,0x3240u,0x1bu,0x9c9c90u,PeaceTermExtraKind::region_name30},
    {0x1cd26b0u,0x2fb9u,0x11u,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd27f8u,0x2fbau,0x10u,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd2940u,0x2d27u,0x13u,0x99e480u,PeaceTermExtraKind::handle30},
    {0x1cd2a90u,0x2e4au,0x12u,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd2bd8u,0x27c1u,0x0cu,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd2d20u,0x2d2du,0x0bu,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd2e68u,0x2d2eu,0x0eu,0x99e480u,PeaceTermExtraKind::handle30},
    {0x1cd2fb8u,0x3094u,0x0du,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd3250u,0x3777u,0x20u,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd3398u,0x2f20u,0x0au,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd34e0u,0x30a3u,0x09u,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd3778u,0x2d26u,0x04u,0x99e630u,PeaceTermExtraKind::nested38},
    {0x1cd38c8u,0x2e07u,0x08u,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd3a10u,0x30a0u,0x07u,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd3b58u,0x35f0u,0x14u,0x99e480u,PeaceTermExtraKind::handle30},
    {0x1cd3ca8u,0x3ae7u,0x24u,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd3df0u,0x32f3u,0x23u,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd3f38u,0x2d2au,0x1au,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd4080u,0x302du,0x19u,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd4318u,0x3541u,0x1cu,0x99e480u,PeaceTermExtraKind::handle30},
    {0x1cd4468u,0x2d2fu,0x16u,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd45b0u,0x2d29u,0x15u,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd46f8u,0x2e04u,0x18u,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd4840u,0x3065u,0x17u,0x99b3c0u,PeaceTermExtraKind::base},
    {0x1cd4c28u,0x3bbdu,0x25u,0x99e480u,PeaceTermExtraKind::handle30}
}};

constexpr const PeaceTermTypeDescriptor* peace_find_term_type(
    std::uintptr_t vtable_rva) noexcept {
    for (const auto& descriptor: kPeaceTermTypeWhitelist) {
        if (descriptor.vtable_rva==vtable_rva) return &descriptor;
    }
    return nullptr;
}

constexpr const PeaceTermTypeDescriptor* peace_find_term_type_id(
    std::uint32_t type_id) noexcept {
    for (const auto& descriptor: kPeaceTermTypeWhitelist) {
        if (descriptor.type_id==type_id) return &descriptor;
    }
    return nullptr;
}

constexpr bool peace_term_type_supported(const PeaceTermTypeDescriptor& descriptor)
    noexcept {
    return descriptor.extra_kind!=PeaceTermExtraKind::unsupported;
}

} // namespace bridge::peace_payload
