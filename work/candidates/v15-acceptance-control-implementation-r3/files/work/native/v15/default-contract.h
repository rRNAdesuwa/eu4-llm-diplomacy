#pragma once
#include <cstddef>
#include <cstdint>

// Pure bounded reader contract, shared with the synthetic-memory harness.
// The reader copies scalar values only; it NEVER copies/constructs native offers.
namespace eu4_owned_peace_lifecycle_1375::contract {
constexpr std::uint64_t kInvalidHandle = 0x2d2d2d;
constexpr std::uint32_t kDefaultDate = 0x29c77f8;
constexpr std::uintptr_t kActionVtable = 0x1c7b840, kOfferVtable = 0x1c578b8;
struct Range { std::uintptr_t begin; std::size_t bytes; };
struct Snapshot {
    Range owned[8]; // action, 40 type vectors, three sentinels, three hash buffers
    std::uint64_t mismatch;
    std::size_t read_bytes;
    std::size_t read_calls;
};
using Reader = bool (*)(void*, std::uintptr_t, void*, std::size_t);
enum Mismatch : std::uint64_t {
    pointer = 1ull << 0, action_identity = 1ull << 1,
    action_handles = 1ull << 2, action_dates = 1ull << 3,
    action_flags = 1ull << 4, offer_identity = 1ull << 5,
    offer_handles = 1ull << 6, offer_flags = 1ull << 7,
    vectors = 1ull << 8, type_buckets = 1ull << 9,
    owner_self = 1ull << 10, hash_state = 1ull << 11,
    internal_alias = 1ull << 12, read_failed = 1ull << 13
};
inline bool range_valid(Range value) {
    return value.begin >= 0x10000 && value.bytes != 0 && value.bytes <= 0x1000
        && value.begin <= 0x00007fffffffffffULL - value.bytes;
}
inline bool overlap(Range a, Range b) {
    return a.begin < b.begin + b.bytes && b.begin < a.begin + a.bytes;
}
struct View {
    Reader reader; void* user; Snapshot& out;
    template<class T> T read(std::uintptr_t address) {
        T value{};
        if (out.read_bytes + sizeof(T) > 8192 || out.read_calls >= 512
            || address < 0x10000 || address > 0x00007fffffffffffULL - sizeof(T)) {
            out.mismatch |= read_failed; return value;
        }
        out.read_bytes += sizeof(T); ++out.read_calls;
        if (!reader(user, address, &value, sizeof(value))) out.mismatch |= read_failed;
        return value;
    }
    template<class T> void expect(std::uintptr_t address, T expected, std::uint64_t bit) {
        if (read<T>(address) != expected) out.mismatch |= bit;
    }
};
inline Snapshot inspect(std::uintptr_t action, std::uintptr_t module, Reader reader, void* user) {
    Snapshot out{};
    if (reader == nullptr || !range_valid({action, 0x210}) || (action & 7u) != 0) {
        out.mismatch = pointer; return out;
    }
    out.owned[0] = {action, 0x210};
    View view{reader, user, out};
    view.expect<std::uintptr_t>(action, module + kActionVtable, action_identity);
    view.expect<std::uint32_t>(action + 8, 0x165, action_identity);
    constexpr std::uintptr_t handles[] = {0x10, 0x18, 0x20};
    for (std::uintptr_t off : handles)
        view.expect<std::uint64_t>(action + off, kInvalidHandle, action_handles);
    view.expect<std::uint32_t>(action + 0x28, kDefaultDate, action_dates);
    view.expect<std::uint32_t>(action + 0x2c, kDefaultDate, action_dates);
    view.expect<std::uint32_t>(action + 0x30, 0xffffffffu, action_flags);
    view.expect<std::uint32_t>(action + 0x34, 0, action_flags);
    view.expect<std::uint16_t>(action + 0x38, 1, action_flags);
    view.expect<std::uint32_t>(action + 0x3c, 0, action_flags);
    view.expect<std::uint8_t>(action + 0x40, 1, action_flags);
    view.expect<std::uint8_t>(action + 0x41, 1, action_flags);
    view.expect<std::uint8_t>(action + 0x208, 0, action_flags);
    const std::uintptr_t offer = action + 0x48;
    view.expect<std::uintptr_t>(offer, module + kOfferVtable, offer_identity);
    view.expect<std::uint32_t>(offer + 8, 0x165, offer_identity);
    view.expect<std::uint64_t>(offer + 0x10, kInvalidHandle, offer_handles);
    view.expect<std::uint64_t>(offer + 0x18, kInvalidHandle, offer_handles);
    view.expect<std::uint8_t>(offer + 0x20, 0, offer_flags); // NOT outer demand=1
    // Four participant vectors, owned component vector and two auxiliary vectors.
    for (std::uintptr_t off = 0x28; off < 0xd0; off += 8)
        view.expect<std::uint64_t>(offer + off, 0, vectors);
    view.expect<std::uintptr_t>(offer + 0xe8, offer, owner_self);
    view.expect<std::uint32_t>(offer + 0xf0, 0, offer_flags);
    view.expect<std::uint32_t>(offer + 0xf4, 0, offer_flags);
    view.expect<std::uint8_t>(offer + 0x1b8, 0, offer_flags);
    view.expect<std::uint8_t>(offer + 0x1b9, 1, offer_flags);
    const auto buckets = view.read<std::uintptr_t>(offer + 0xd0);
    out.owned[1] = {buckets, 0x3c0};
    if (!range_valid(out.owned[1]) || (buckets & 7u) != 0) out.mismatch |= type_buckets;
    else {
        view.expect<std::uintptr_t>(offer + 0xd8, buckets + 0x3c0, type_buckets);
        view.expect<std::uintptr_t>(offer + 0xe0, buckets + 0x3c0, type_buckets);
        for (std::uintptr_t off = 0; off < 0x3c0; off += 8)
            view.expect<std::uint64_t>(buckets + off, 0, type_buckets);
    }
    constexpr std::uintptr_t hashes[] = {0xf8, 0x138, 0x178};
    for (std::size_t index = 0; index < 3; ++index) {
        const auto hash = offer + hashes[index];
        const auto sentinel = view.read<std::uintptr_t>(hash + 8);
        const auto begin = view.read<std::uintptr_t>(hash + 0x18);
        out.owned[2 + index * 2] = {sentinel, index == 0 ? 0x30u : 0x40u};
        out.owned[3 + index * 2] = {begin, 0x80};
        view.expect<std::uint32_t>(hash, 0x3f800000u, hash_state);
        view.expect<std::uint64_t>(hash + 0x10, 0, hash_state);
        view.expect<std::uint64_t>(hash + 0x30, 7, hash_state);
        view.expect<std::uint64_t>(hash + 0x38, 8, hash_state);
        if (!range_valid(out.owned[2 + index * 2]) || !range_valid(out.owned[3 + index * 2])
            || (sentinel & 7u) != 0 || (begin & 7u) != 0) out.mismatch |= hash_state;
        else {
            view.expect<std::uintptr_t>(sentinel, sentinel, hash_state);
            view.expect<std::uintptr_t>(sentinel + 8, sentinel, hash_state);
            view.expect<std::uintptr_t>(hash + 0x20, begin + 0x80, hash_state);
            view.expect<std::uintptr_t>(hash + 0x28, begin + 0x80, hash_state);
            for (std::uintptr_t off = 0; off < 0x80; off += 8)
                view.expect<std::uintptr_t>(begin + off, sentinel, hash_state);
        }
    }
    for (std::size_t i = 0; i < 8; ++i) {
        if (!range_valid(out.owned[i])) out.mismatch |= pointer;
        for (std::size_t j = 0; j < i; ++j)
            if (range_valid(out.owned[i]) && range_valid(out.owned[j]) && overlap(out.owned[i], out.owned[j]))
                out.mismatch |= internal_alias;
    }
    return out;
}
inline bool distinct(const Snapshot& a, const Snapshot& b) {
    if (a.mismatch != 0 || b.mismatch != 0) return false;
    for (const auto& left : a.owned) for (const auto& right : b.owned)
        if (overlap(left, right)) return false;
    return true;
}
inline bool same(const Snapshot& a, const Snapshot& b) {
    if (a.mismatch != 0 || b.mismatch != 0) return false;
    for (std::size_t i = 0; i < 8; ++i)
        if (a.owned[i].begin != b.owned[i].begin || a.owned[i].bytes != b.owned[i].bytes) return false;
    return true;
}
} // namespace eu4_owned_peace_lifecycle_1375::contract
