#pragma once
#include <cstddef>
#include <cstdint>
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

// Private candidate ABI. No exports, native resolver, public request pointers,
// wire consumer or host implementation is supplied. Tests use isolated mocks.
namespace eu4_spy18 {
enum class Stage : std::uint32_t { lifecycle=1, family_preview=2, owned_command=3 };
enum class Step : std::uint32_t { none, factory, clone, destroy_clone, initialize,
    full_preview, wrap_owned, destroy_original, command_gate, destroy_command };
enum class EventKind : std::uint32_t { stage_begin, step_begin, step_return, case_complete, stage_complete, fault };
enum class Reason : std::uint32_t { none, bad_host, busy, frozen, stage_order, wrong_thread,
    image_pin, root_guard, rejected_guard, audit_failed, resolver_failed,
    factory_unknown, fields_mismatch, alias_or_ownership, native_exception, read_budget };
enum class GuardPoint : std::uint32_t { before_work, after_work, before_cleanup };
struct Stamp {
    std::uintptr_t game, database, countries, actor_country, target_country, server, pause_manager;
    std::uint64_t actor, target, player;
    std::int32_t date;
};
struct Fields {
    std::uintptr_t vtable;
    std::uint32_t marker;
    std::uint64_t actor, controller, target;
    std::int32_t primary_date, secondary_date, envoy;
    std::uint32_t state;
    std::uint8_t value, flag39;
    std::uint32_t identifier;
};
struct Event {
    EventKind kind;
    Stage stage;
    Step step;
    std::uint32_t family, token, original_id, clone_id, command_id;
    bool call_entered, call_returned, allowed_observed, allowed;
    bool original_destroyed, clone_destroyed, command_destroyed;
    bool mock_resolver, send_supported; // send_supported is always false.
    Fields original_fields, clone_fields;
    Stamp stamp;
    Reason reason;
    std::uint32_t exception_code;
};
// Read is bounded by the core, and WriteOwned is invoked only for a just-
// allocated verified original action at the exact fixed 1/4/8-byte fields.
using Read = bool (*)(void*,std::uintptr_t,void*,std::size_t);
using WriteOwned = bool (*)(void*,std::uintptr_t,const void*,std::size_t);
using Resolve = std::uintptr_t (*)(void*,std::uintptr_t fixed_rva);
using Clock = std::uint64_t (*)(void*);
using Guard = bool (*)(void*,GuardPoint,Stage,Step,const Stamp*);
using Logger = bool (*)(void*,const Event*);
struct Host {
    std::uint32_t struct_size, abi_version, expected_game_thread;
    std::uintptr_t image_base;
    const char* game_sha256;
    std::uint64_t frame_id, expires_uptime_ms;
    bool full_sha256_verified, durable_stage_claimed, later_clean_health_verified;
    bool disposable_test_authorized, isolated_mock_resolver;
    Read read; WriteOwned write_owned; Resolve resolve; Clock clock;
    Guard guard; Logger log; void* user;
};
struct Result {
    Stage stage;
    Reason reason;
    Step step;
    std::uint32_t family, cases_complete, exception_code;
    bool completed, audit_complete, freeze_session, ownership_uncertain;
    bool allowed_observed[5], allowed[5];
    bool retry_allowed, send_supported, runtime_verified, production_ready; // always false
    std::uint32_t reads;
    std::size_t bytes_read;
};
// A production host would need a process-singleton, never-reset Core, durable
// claims and independently verified later health. That host does not exist.
class Core {
public:
    Core() noexcept;
    Core(const Core&)=delete;
    Core& operator=(const Core&)=delete;
    Result run(Stage stage,const Host& host);
private:
    volatile LONG active_, frozen_;
    std::uint32_t completed_, next_object_id_;
    std::uint64_t completion_frame_;
    Stamp locked_;
    friend struct Runner;
};
const char* family_name(std::uint32_t family) noexcept;
} // namespace eu4_spy18
