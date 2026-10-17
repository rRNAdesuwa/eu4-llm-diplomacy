#pragma once

// Cross-platform logical payload for the Declare War action's owned context.
//
// This is not a byte overlay for the native object.  The native capture layer
// reads the listed offsets explicitly and stores the values here.  Several
// fields may contain process-local definition pointers; they remain private
// values for same-process clone/serialization checks and must never be sent
// to the public LLM/API layer.

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace bridge::declarewar_payload {

constexpr std::size_t kMaxWarPayloadVectorElements=128;
constexpr std::size_t kWarPayloadElementBytes=sizeof(std::uint64_t);

struct WarOwnedPayloadLayout {
    static constexpr std::uintptr_t field08=0x08;
    static constexpr std::uintptr_t field10=0x10;
    static constexpr std::uintptr_t field18=0x18;
    static constexpr std::uintptr_t field1c=0x1c;
    static constexpr std::uintptr_t field28=0x28;
    static constexpr std::uintptr_t field30=0x30;
    static constexpr std::uintptr_t field38=0x38;
    static constexpr std::uintptr_t field40=0x40;
    static constexpr std::uintptr_t field48=0x48;
    static constexpr std::uintptr_t field50=0x50;
    static constexpr std::uintptr_t field58=0x58;
};

// Offsets copied by native d9a960.  The names intentionally describe only
// storage positions; they do not assert that a value is a CB, province, war
// goal, or globally stable identifier.
struct WarOwnedPayload {
    std::uint32_t owned_field08=0;
    std::uint64_t owned_field10=0;
    std::uint32_t owned_field18=0;
    std::uint64_t owned_field1c=0;
    std::uint64_t owned_field28=0;
    std::uint64_t owned_field30=0;
    std::uint64_t owned_field38=0;
    std::uint64_t owned_field40=0;
    std::uint64_t owned_field48=0;
    std::uint64_t owned_field50=0;
    std::uint64_t owned_field58=0;

    constexpr bool operator==(const WarOwnedPayload& other) const noexcept {
        return owned_field08==other.owned_field08
            && owned_field10==other.owned_field10
            && owned_field18==other.owned_field18
            && owned_field1c==other.owned_field1c
            && owned_field28==other.owned_field28
            && owned_field30==other.owned_field30
            && owned_field38==other.owned_field38
            && owned_field40==other.owned_field40
            && owned_field48==other.owned_field48
            && owned_field50==other.owned_field50
            && owned_field58==other.owned_field58;
    }
    constexpr bool operator!=(const WarOwnedPayload& other) const noexcept {
        return !(*this==other);
    }
};

struct WarPayloadVector {
    std::uint32_t count=0;
    std::array<std::uint64_t,kMaxWarPayloadVectorElements> values{};

    constexpr bool valid() const noexcept {
        return count<=kMaxWarPayloadVectorElements;
    }

    constexpr bool operator==(const WarPayloadVector& other) const noexcept {
        if (!valid() || !other.valid() || count!=other.count) return false;
        for (std::size_t i=0;i<count;++i) {
            if (values[i]!=other.values[i]) return false;
        }
        return true;
    }
    constexpr bool operator!=(const WarPayloadVector& other) const noexcept {
        return !(*this==other);
    }
};

struct WarPayloadExtension {
    std::uint8_t flag40=0;
    std::uint8_t flag41=0;
    std::uint8_t flag42=0;
    bool owned_present=false;
    WarOwnedPayload owned{};

    // Keep native container positions in the names until a complete semantic
    // mapping is proven.  Each element is copied as one 8-byte value.
    WarPayloadVector container50{};
    WarPayloadVector container68{};
    WarPayloadVector container80{};

    constexpr bool valid() const noexcept {
        if (!container50.valid() || !container68.valid() || !container80.valid())
            return false;
        // An absent owned sentinel has no logical copied fields.  Rejecting a
        // nonzero absent payload prevents stale process-local values from
        // matching the canonical empty state.
        return owned_present || owned==WarOwnedPayload{};
    }

    constexpr bool operator==(const WarPayloadExtension& other) const noexcept {
        return flag40==other.flag40 && flag41==other.flag41
            && flag42==other.flag42 && owned_present==other.owned_present
            && owned==other.owned && container50==other.container50
            && container68==other.container68 && container80==other.container80;
    }
    constexpr bool operator!=(const WarPayloadExtension& other) const noexcept {
        return !(*this==other);
    }
};

struct WarNativeVectorLayout {
    std::uintptr_t begin_offset=0;
    std::uintptr_t end_offset=0;
    std::uintptr_t capacity_offset=0;
};

// The serializer/field-reader assembly proves begin/end/capacity at these
// offsets.  It computes (end-begin)/8 and reads each element at begin+i*8.
constexpr WarNativeVectorLayout kWarContainer50Layout{0x50,0x58,0x60};
constexpr WarNativeVectorLayout kWarContainer68Layout{0x68,0x70,0x78};
constexpr WarNativeVectorLayout kWarContainer80Layout{0x80,0x88,0x90};

constexpr bool war_native_vector_bounds(std::uintptr_t begin,
    std::uintptr_t end,std::uintptr_t capacity,std::uint32_t& count) noexcept {
    count=0;
    if (end<begin || capacity<end) return false;
    const std::uintptr_t span=end-begin;
    const std::uintptr_t capacity_span=capacity-begin;
    if ((span%kWarPayloadElementBytes)!=0
        || (capacity_span%kWarPayloadElementBytes)!=0) return false;
    const std::uintptr_t entries=span/kWarPayloadElementBytes;
    if (entries>kMaxWarPayloadVectorElements
        || entries>std::numeric_limits<std::uint32_t>::max()) return false;
    count=static_cast<std::uint32_t>(entries);
    return true;
}

// Reader must have the form bool reader(std::uintptr_t address,T& value).
// This helper never reads beyond end and rejects a partial/misaligned vector
// before reading any element.  The native layer can use it with its existing
// bounded ReadProcessMemory wrapper.
template<typename Reader>
static bool war_capture_native_u64_vector(Reader& reader,
    std::uintptr_t object,const WarNativeVectorLayout& layout,
    WarPayloadVector& output) {
    output=WarPayloadVector{};
    std::uintptr_t begin=0,end=0,capacity=0;
    if (!reader(object+layout.begin_offset,begin)
        || !reader(object+layout.end_offset,end)
        || !reader(object+layout.capacity_offset,capacity)) return false;
    std::uint32_t count=0;
    if (!war_native_vector_bounds(begin,end,capacity,count)) return false;
    for (std::uint32_t i=0;i<count;++i) {
        std::uint64_t value=0;
        if (!reader(begin+static_cast<std::uintptr_t>(i)
                *kWarPayloadElementBytes,value)) {
            output=WarPayloadVector{};
            return false;
        }
        output.values[i]=value;
    }
    output.count=count;
    return true;
}

} // namespace bridge::declarewar_payload
