#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <type_traits>

namespace entry_forward_model {
// Integers are owned observations. No pointer/read-port is retained in output.
struct EntryBorrow {
    std::uint64_t entry_rsp, original_rcx, original_r8, frame_rsp;
};
struct OwnedEntry {
    std::uint64_t entry_rsp, original_rcx, original_r8, frame_rsp;
};
enum class Field : std::size_t {
    ret0, ret40, ret370, ret3f0, ret440, stack_holder, outer, game,
    outer_vtable, outer_secondary_vtable, current_app, pending_app, previous_app,
    transition_byte, retain_previous_byte, game_vtable, game_server,
    current_vtable, current_update, server_holder, map_object,
    pending_vtable, previous_vtable, count
};
struct OwnedProjection { std::array<std::uint64_t, 23> values{}; };
enum class Status : std::uint32_t { unknown, model_structural_match };
enum class Reason : std::uint32_t {
    none, descriptor_mismatch, read_refused, budget, return_chain, type,
    identity, changed, short_read
};
struct OwnedSnapshot {
    OwnedEntry entry{};
    std::array<OwnedProjection, 2> passes{};
    std::uint32_t attempted_reads = 0;
    Status status = Status::unknown;
    std::uint64_t requested_bytes = 0, exact_bytes = 0;
    std::uint32_t complete_passes = 0;
    Reason reason = Reason::none;
};
static_assert(sizeof(EntryBorrow) == 32 && sizeof(OwnedEntry) == 32);
static_assert(offsetof(EntryBorrow, original_rcx) == 8);
static_assert(offsetof(EntryBorrow, original_r8) == 16);
static_assert(offsetof(EntryBorrow, frame_rsp) == 24);
static_assert(static_cast<std::size_t>(Field::count) == 23);
static_assert(sizeof(OwnedProjection) == 184 && sizeof(OwnedSnapshot) == 432);
static_assert(offsetof(OwnedSnapshot, passes) == 32);
static_assert(offsetof(OwnedSnapshot, attempted_reads) == 400);
static_assert(offsetof(OwnedSnapshot, requested_bytes) == 408);
static_assert(std::is_standard_layout_v<EntryBorrow> && std::is_trivially_copyable_v<EntryBorrow>);
static_assert(std::is_standard_layout_v<OwnedSnapshot> && std::is_trivially_copyable_v<OwnedSnapshot>);
inline constexpr bool kNativeEntryAuthenticated = false, kNativeReady = false;
inline constexpr bool kLifetimeLease = false, kAtomicSnapshot = false;
inline constexpr bool kExceptionUnwindVerified = false, kAvxXstatePreserved = false;
inline constexpr bool kGameInstallationProvenance = false;
}  // namespace entry_forward_model
