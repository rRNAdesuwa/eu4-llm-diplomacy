// Synthetic memory only; shares the candidate's actual bounded layout checker.
// Not compiled/run in this preparation task. No Windows/native/game dependency.
#include "default-contract.h"
#include <array>
#include <cstdio>
#include <cstring>

namespace c = eu4_owned_peace_lifecycle_1375::contract;
constexpr std::uintptr_t base = 0x140000000ULL, memory_base = 0x100000;
struct Memory {
    std::array<unsigned char, 0x4000> data{};
    bool original_dead = false;
    std::size_t calls = 0;
    std::size_t fail_after = 10000;
    template<class T> void put(std::uintptr_t address, T value) {
        std::memcpy(data.data() + (address - memory_base), &value, sizeof(value));
    }
    static bool get(void* user, std::uintptr_t address, void* output, std::size_t bytes) {
        auto& self = *static_cast<Memory*>(user);
        ++self.calls;
        if (self.calls > self.fail_after || address < memory_base
            || bytes > self.data.size() || address - memory_base > self.data.size() - bytes
            || (self.original_dead && address < memory_base + 0x2000)) return false;
        std::memcpy(output, self.data.data() + address - memory_base, bytes); return true;
    }
    void build(std::uintptr_t action) {
        const auto offer = action + 0x48;
        put<std::uintptr_t>(action, base + c::kActionVtable);
        put<std::uint32_t>(action + 8, 0x165);
        for (std::uintptr_t off = 0x10; off <= 0x20; off += 8) put<std::uint64_t>(action + off, c::kInvalidHandle);
        put<std::uint32_t>(action + 0x28, c::kDefaultDate);
        put<std::uint32_t>(action + 0x2c, c::kDefaultDate);
        put<std::uint32_t>(action + 0x30, 0xffffffffu);
        put<std::uint32_t>(action + 0x34, 0);
        put<std::uint16_t>(action + 0x38, 1);
        put<std::uint32_t>(action + 0x3c, 0);
        put<std::uint8_t>(action + 0x40, 1);
        put<std::uint8_t>(action + 0x41, 1);
        put<std::uint8_t>(action + 0x208, 0);
        put<std::uintptr_t>(offer, base + c::kOfferVtable);
        put<std::uint32_t>(offer + 8, 0x165);
        put<std::uint64_t>(offer + 0x10, c::kInvalidHandle);
        put<std::uint64_t>(offer + 0x18, c::kInvalidHandle);
        put<std::uint8_t>(offer + 0x20, 0);
        for (std::uintptr_t off = 0x28; off < 0xd0; off += 8) put<std::uint64_t>(offer + off, 0);
        const auto types = action + 0x400;
        put<std::uintptr_t>(offer + 0xd0, types);
        put<std::uintptr_t>(offer + 0xd8, types + 0x3c0);
        put<std::uintptr_t>(offer + 0xe0, types + 0x3c0);
        for (std::uintptr_t off = 0; off < 0x3c0; off += 8) put<std::uint64_t>(types + off, 0);
        put<std::uintptr_t>(offer + 0xe8, offer);
        put<std::uint64_t>(offer + 0xf0, 0);
        put<std::uint8_t>(offer + 0x1b8, 0);
        put<std::uint8_t>(offer + 0x1b9, 1);
        constexpr std::uintptr_t hashes[] = {0xf8, 0x138, 0x178};
        for (std::size_t n = 0; n < 3; ++n) {
            const auto hash = offer + hashes[n], sentinel = action + 0x800 + n * 0x200;
            const auto buffer = sentinel + 0x100;
            put<std::uint32_t>(hash, 0x3f800000u);
            put<std::uintptr_t>(hash + 8, sentinel);
            put<std::uint64_t>(hash + 0x10, 0);
            put<std::uintptr_t>(hash + 0x18, buffer);
            put<std::uintptr_t>(hash + 0x20, buffer + 0x80);
            put<std::uintptr_t>(hash + 0x28, buffer + 0x80);
            put<std::uint64_t>(hash + 0x30, 7);
            put<std::uint64_t>(hash + 0x38, 8);
            put<std::uintptr_t>(sentinel, sentinel);
            put<std::uintptr_t>(sentinel + 8, sentinel);
            for (std::uintptr_t off = 0; off < 0x80; off += 8) put<std::uintptr_t>(buffer + off, sentinel);
        }
    }
    Memory() { data.fill(0xcc); build(memory_base); build(memory_base + 0x2000); }
};
unsigned checks = 0, failures = 0;
void check(bool yes, const char* name) {
    ++checks;
    if (!yes) { ++failures; std::printf("FAIL: %s\n", name); }
}
template<class T> void mutation(std::uintptr_t offset, T value, std::uint64_t expected, const char* name) {
    Memory mem;
    mem.put<T>(memory_base + offset, value);
    const auto result = c::inspect(memory_base, base, Memory::get, &mem);
    check((result.mismatch & expected) != 0, name);
}
int main() {
    Memory mem;
    auto a = c::inspect(memory_base, base, Memory::get, &mem);
    auto b = c::inspect(memory_base + 0x2000, base, Memory::get, &mem);
    check(a.mismatch == 0 && b.mismatch == 0, "valid independently allocated defaults, nonzero unknown padding");
    check(c::distinct(a, b), "all eight ownership ranges are independent");
    check(c::same(a, a), "stable selected fields and allocation identity");
    check(!c::distinct(a, a), "same action cannot be its clone");
    check(a.read_bytes <= 8192 && a.read_calls <= 512, "inspection read limits");
    mutation<std::uintptr_t>(0, base + c::kOfferVtable, c::action_identity, "wrong action vtable");
    mutation<std::uint32_t>(8, 0, c::action_identity, "wrong action type");
    mutation<std::uint64_t>(0x10, 1, c::action_handles, "real country invalid in default-only test");
    mutation<std::uint32_t>(0x2c, 0, c::action_dates, "clone date contract");
    mutation<std::uint32_t>(0x30, 0, c::action_flags, "envoy sentinel");
    mutation<std::uint32_t>(0x34, 2, c::action_flags, "peace does not inherit coalition state2");
    mutation<std::uint8_t>(0x39, 1, c::action_flags, "base secondary bool");
    mutation<std::uint8_t>(0x41, 0, c::action_flags, "outer demand remains true");
    mutation<std::uint8_t>(0x208, 1, c::action_flags, "force starts false");
    mutation<std::uintptr_t>(0x48, base + c::kActionVtable, c::offer_identity, "wrong embedded type");
    mutation<std::uint8_t>(0x48 + 0x20, 1, c::offer_flags, "embedded demand remains false");
    mutation<std::uint64_t>(0x48 + 0x88, memory_base + 0xf00, c::vectors, "no populated component pointer traversal");
    mutation<std::uintptr_t>(0x48 + 0xd0, 0, c::type_buckets, "returned copy has allocated type index");
    mutation<std::uintptr_t>(0x48 + 0xd8, memory_base + 0x400 + 0x3d8, c::type_buckets, "reject 41 buckets without traversal");
    mutation<std::uintptr_t>(0x48 + 0xe0, memory_base + 0x400 + 0x1000, c::type_buckets, "reject oversized capacity");
    mutation<std::uint64_t>(0x400 + 39 * 24 + 16, 1, c::type_buckets, "last inner vector capacity must zero");
    mutation<std::uintptr_t>(0x48 + 0xe8, memory_base, c::owner_self, "owner must embedded offer, not outer action");
    mutation<std::uint32_t>(0x48 + 0xf0, 1, c::offer_flags, "aux state remains default");
    mutation<std::uint8_t>(0x48 + 0x1b9, 0, c::offer_flags, "apply penalties default true");
    mutation<std::uint64_t>(0x48 + 0xf8 + 0x10, 1, c::hash_state, "reject populated hash without walking nodes");
    mutation<std::uint32_t>(0x48 + 0x138, 0, c::hash_state, "known hash load-factor bits");
    mutation<std::uint64_t>(0x48 + 0x178 + 0x30, 3, c::hash_state, "default mask7");
    mutation<std::uint64_t>(0x48 + 0xf8 + 0x38, 16, c::hash_state, "default8 buckets, not16 buckets");
    mutation<std::uintptr_t>(0x800, memory_base + 0x810, c::hash_state, "sentinel next must self");
    mutation<std::uintptr_t>(0x808, 0, c::hash_state, "sentinel previous must self");
    mutation<std::uintptr_t>(0x900 + 15 * 8, 0, c::hash_state, "last hash entry sentinel");
    mutation<std::uintptr_t>(0x48 + 0xf8 + 0x28, memory_base + 0xa00, c::hash_state, "capacity exactly16 pointers");
    mutation<std::uintptr_t>(0x48 + 0xf8 + 8, 0xfffffffffffffff0ULL, c::hash_state, "reject wrapped hash range");
    {
        Memory alias;
        const auto offer = memory_base + 0x2000 + 0x48;
        alias.put<std::uintptr_t>(offer + 0xd0, memory_base + 0x400);
        alias.put<std::uintptr_t>(offer + 0xd8, memory_base + 0x7c0);
        alias.put<std::uintptr_t>(offer + 0xe0, memory_base + 0x7c0);
        const auto copied = c::inspect(memory_base + 0x2000, base, Memory::get, &alias);
        check(copied.mismatch == 0, "shallow index alias can look locally valid");
        check(!c::distinct(a, copied), "cross-object index alias rejects before either destructor");
    }
    {
        Memory stale;
        stale.put<std::uintptr_t>(memory_base + 0x2000 + 0x48 + 0xe8, memory_base + 0x48);
        const auto copied = c::inspect(memory_base + 0x2000, base, Memory::get, &stale);
        check((copied.mismatch & c::owner_self) != 0, "copy's self pointer may not retain source");
    }
    {
        Memory failure; failure.fail_after = 10;
        const auto bad = c::inspect(memory_base, base, Memory::get, &failure);
        check((bad.mismatch & c::read_failed) != 0, "read failure cannot pass");
        check(failure.calls <= 512, "failure retains fixed read budget");
    }
    mem.original_dead = true;
    const auto survivor = c::inspect(memory_base + 0x2000, base, Memory::get, &mem);
    check(c::same(b, survivor), "survivor checker does not read destroyed original ranges");
    check(c::inspect(0, base, Memory::get, &mem).mismatch == c::pointer, "null result rejected without reads");
    check(c::inspect(0xfffffffffffffff8ULL, base, Memory::get, &mem).mismatch == c::pointer, "overflow pointer rejected");
    std::printf("%u synthetic checks; %u failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
