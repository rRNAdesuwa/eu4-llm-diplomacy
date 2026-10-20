#pragma once
#include <cstddef>
#include <cstdint>

// Isolated source candidate only. No host integration/export/hook/mailbox/send.
namespace eu4_owned_peace_lifecycle_1375 {
constexpr std::uint32_t kAbiVersion = 1;
enum class GuardPoint : std::uint32_t {
    before_factory, before_clone, before_original_destroy, before_clone_destroy
};
using Guard = bool (*)(void* user, GuardPoint point);
// Host must persist the complete line and flush it before returning true.
using Logger = bool (*)(void* user, const char* json, std::size_t bytes);
struct Host {
    std::uint32_t struct_size;
    std::uint32_t abi_version;
    std::uint32_t expected_game_thread;
    bool durable_attempt_claimed;
    bool exact_process_and_game_sha256_verified;
    // Host owns main-thread, paused disposable session, world/context/epoch
    // validity and no competing experiment. This flag does not prove them.
    bool isolated_lifecycle_authorized;
    Guard guard;
    Logger log;
    void* user;
};
enum class Reason : std::uint32_t {
    none, host_contract, already_attempted, wrong_thread, image_pin,
    guard_rejected, audit_failed, factory_contract, clone_contract,
    ownership_alias, original_changed, surviving_clone_changed, native_exception
};
struct Result {
    Reason reason;
    bool passed;
    bool factory_entered;
    bool factory_returned;
    bool clone_entered;
    bool clone_returned;
    bool original_destroy_entered;
    bool original_destroy_returned;
    bool clone_destroy_entered;
    bool clone_destroy_returned;
    bool distinct_owned_ranges;
    bool original_unchanged_after_clone;
    bool clone_unchanged_after_original_destroy;
    bool audit_complete;
    bool freeze_session;
    bool retry_allowed; // Always false, including rejection and SEH.
    bool execution_verified; // Always false: no legality/wrapper/submit call.
    std::uint64_t original_mismatch_mask;
    std::uint64_t clone_mismatch_mask;
    std::uint32_t exception_code;
    std::uint32_t thread_id;
};

// Once per loaded candidate. Exactly one factory(293c,null), one virtual clone,
// and two independent deleting destructors on a fully matching, disjoint pair.
// Delete original first, re-inspect the surviving clone, then delete the clone.
// Factory-internal temporary is already cleaned before factory returns and is
// not directly inspected. There are only TWO simultaneously observable offers.
// After SEH/audit/guard/layout/alias failure: freeze, no speculative cleanup or
// retry. Partial allocations may remain; host must retire this research session.
Result run_once(const Host& host);
} // namespace eu4_owned_peace_lifecycle_1375
