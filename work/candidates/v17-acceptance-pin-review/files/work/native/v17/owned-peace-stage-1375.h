#pragma once
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include "peace-owned-lifecycle-1375.h"

// Pure stage helpers used by BOTH the generated host and synthetic test.
namespace eu4_owned_peace_stage_1375 {
struct State { bool tested; bool claim; bool in_call; bool core_returned; bool wrapper_durable; bool passed; bool frozen; };
enum class Next : unsigned { none, lifecycle, owned_peace, preview, command, mailbox };
inline void reject(State& state) { state.passed = false; state.frozen = true; state.in_call = false; }
inline bool begin(State& state, bool base_tested, bool base_passed, bool following_health, bool durable_claim) {
    if (state.tested || state.frozen || !base_tested || !base_passed || !following_health || !durable_claim) {
        reject(state); return false;
    }
    state.tested = true; state.claim = true; state.in_call = true; return true;
}
inline bool result_ok(const eu4_owned_peace_lifecycle_1375::Result& r) {
    return r.reason == eu4_owned_peace_lifecycle_1375::Reason::none && r.passed && r.audit_complete
        && !r.freeze_session && !r.retry_allowed && !r.execution_verified && r.exception_code == 0
        && r.factory_entered && r.factory_returned && r.clone_entered && r.clone_returned
        && r.original_destroy_entered && r.original_destroy_returned
        && r.clone_destroy_entered && r.clone_destroy_returned && r.distinct_owned_ranges
        && r.original_unchanged_after_clone && r.clone_unchanged_after_original_destroy
        && r.original_mismatch_mask == 0 && r.clone_mismatch_mask == 0;
}
inline bool finish(State& state, const eu4_owned_peace_lifecycle_1375::Result& result,
                   bool post_guard, bool wrapper_durable) {
    const bool active = state.tested && state.claim && state.in_call && !state.core_returned && !state.frozen;
    state.in_call = false; state.core_returned = true; state.wrapper_durable = wrapper_durable;
    state.passed = active && result_ok(result) && post_guard && wrapper_durable;
    if (!state.passed) state.frozen = true;
    return state.passed;
}
inline bool permits_later(const State& state) {
    return state.tested && state.claim && state.core_returned && state.wrapper_durable
        && state.passed && !state.in_call && !state.frozen;
}
inline Next next(bool base_tested, bool base_passed, const State& state,
                 bool preview_tested, bool preview_passed, bool command_tested, bool command_passed,
                 bool following_health) {
    if (state.frozen) return Next::none;
    if (!base_tested) return Next::lifecycle;
    if (!base_passed || !following_health) return Next::none;
    if (!state.tested) return Next::owned_peace;
    if (!permits_later(state)) return Next::none;
    if (!preview_tested) return Next::preview;
    if (!preview_passed) return Next::none;
    if (!command_tested) return Next::command;
    return command_passed ? Next::mailbox : Next::none;
}
inline bool format_marker(char* output, std::size_t capacity, std::uint32_t pid, std::uint64_t creation,
                          std::size_t& written) {
    written = 0;
    if (output == nullptr || capacity == 0 || pid == 0 || creation == 0) return false;
    const int count = std::snprintf(output, capacity,
        "OWNED_PEACE_LIFECYCLE/1\npurpose=restricted_pair_lab_1375_v17\npid=%u\ncreation=%016llx\n",
        static_cast<unsigned>(pid), static_cast<unsigned long long>(creation));
    if (count <= 0 || static_cast<std::size_t>(count) >= capacity) return false;
    written = static_cast<std::size_t>(count); return true;
}
} // namespace eu4_owned_peace_stage_1375
