// Restricted, session-bound v15 research host. Not a production backend.
// Four explicit preflight markers precede the unchanged 36-ID research mailbox.
// Roots/player/date checks are conservative invariants, NOT a load-generation
// proof. Never unload/rearm a live host, automatically retry, or infer applied
// diplomacy from a native dispatch acknowledgement.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <sddl.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "pair-engine-1375.h"
#include "test-controls-1375.h"
#include "lab-request-1375.h"
#include "test-acceptance-1375.h"
#include "owned-peace-stage-1375.h"
#include "../test-fixture-v15-1375.h"

extern "C" void research_frame_stub();
extern "C" void research_original_trampoline();
extern "C" { void* research_trampoline = nullptr; }
extern "C" { void* research_return = nullptr; }
extern bool pair_selftest(uintptr_t, void (*)(const char*));
extern bool pair_preview(uintptr_t, void (*)(const char*));
extern bool pair_command_selftest(uintptr_t, void (*)(const char*));

static HMODULE self_module;
static uintptr_t game_base;
static HANDLE output = INVALID_HANDLE_VALUE;
static volatile LONG installed = 0, active = 0, frames = 0, research_enabled = 0;
static volatile LONG thread_changed = 0;
static DWORD window_thread;
namespace owned_phase = eu4_owned_peace_stage_1375;
static owned_phase::State owned_peace{};
static wchar_t owned_peace_request_file[MAX_PATH]{};
static bool tested = false, selftest_passed = false, preview_tested = false, preview_passed = false;
static bool command_tested = false, command_passed = false, audit_failed = false;
static bool world_locked = false, world_changed = false, session_frozen = false, any_dispatch_entered = false;
static uintptr_t locked_world = 0, locked_database = 0, locked_array = 0;
static uint64_t locked_player = 0, process_created = 0, last_sequence = 0;
static int32_t locked_date = 0;
static ULONGLONG last_log = 0;
static eu4_lab_1375::AcceptanceWindow acceptance_window{};
struct LastLegality {
    bool valid = false;
    eu4_lab_1375::MailboxRequest request{};
    uintptr_t world = 0;
    int32_t date = 0;
};
static LastLegality last_legality{};
static LONG last_health_frame = 0, last_phase_frame = 0;
static wchar_t session_directory[MAX_PATH]{};
static wchar_t request_file[MAX_PATH]{}, preview_request_file[MAX_PATH]{}, command_request_file[MAX_PATH]{};
using NextThread = LONG (NTAPI*)(HANDLE, HANDLE, ACCESS_MASK, ULONG, ULONG, PHANDLE);
static NextThread next_thread;
static const unsigned char prefix[20] = {
    0x4c,0x89,0x44,0x24,0x18,0x55,0x53,0x57,0x48,0x8d,
    0x6c,0x24,0xb0,0x48,0x81,0xec,0x50,0x01,0x00,0x00};
static constexpr uintptr_t frame_rva = 0x10a6ec0;
static constexpr DWORD audit_exception = 0xe1375006;
static constexpr uint64_t france_handle = 0x0100007a00415246ULL;
// Research-only: positive speed requires an external exact-process watchdog.
// The in-process lease attempts pause at its next healthy frame; a stalled or
// frozen host cannot guarantee cleanup. The manifest records both constraints.
static constexpr bool running_speed_enabled = true;
static constexpr char fixture_profile_sha256[] = "f3507bb78f665443c5dad20efee0aef2dd86a8b6741130ee03e883b2ecc1a507";

static bool durable_log(const char* message) {
    if (output == INVALID_HANDLE_VALUE || audit_failed) { audit_failed = true; session_frozen = true; eu4_lab_1375::fail_window(acceptance_window); return false; }
    char complete[4096]{};
    size_t length = strnlen_s(message, sizeof(complete));
    if (length == 0 || length >= sizeof(complete) - 1) { audit_failed = true; session_frozen = true; eu4_lab_1375::fail_window(acceptance_window); return false; }
    memcpy(complete, message, length);
    if (complete[length - 1] != '\n') complete[length++] = '\n';
    DWORD written = 0;
    const bool okay = WriteFile(output, complete, static_cast<DWORD>(length), &written, nullptr)
        && written == static_cast<DWORD>(length) && FlushFileBuffers(output);
    if (!okay) { audit_failed = true; session_frozen = true; eu4_lab_1375::fail_window(acceptance_window); }
    return okay;
}
// Compatibility with unchanged, separately copied v5 phase functions. Their
// per-case logging occurs after destruction/exception handling. Failed durable
// logging raises immediately into the host SEH; no next case can be invoked.
static void log_line(const char* message) { if (!durable_log(message)) RaiseException(audit_exception, 0, 0, nullptr); }

template<typename T> static bool read_value(uintptr_t address, T& value) {
    SIZE_T actual = 0;
    return address >= 0x10000 && address < 0x0000800000000000ULL - sizeof(value)
        && ReadProcessMemory(GetCurrentProcess(), reinterpret_cast<const void*>(address), &value, sizeof(value), &actual)
        && actual == sizeof(value);
}
static bool object_pointer(uintptr_t p) { return p >= 0x10000 && p < 0x0000800000000000ULL && p % 8 == 0; }
static bool in_session_path(wchar_t (&out)[MAX_PATH], const wchar_t* name) {
    return wcscpy_s(out, session_directory) == 0 && wcscat_s(out, name) == 0;
}
static bool sequence_path(wchar_t (&out)[MAX_PATH], uint64_t sequence, const wchar_t* suffix) {
    wchar_t name[64]{};
    return swprintf_s(name, L"%020llu.%s", static_cast<unsigned long long>(sequence), suffix) > 0 && in_session_path(out, name);
}
static bool marker_absent(const wchar_t* path) {
    if (GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES) return false;
    return GetLastError() == ERROR_FILE_NOT_FOUND;
}
static bool create_durable_file(const wchar_t* path, const char* contents, DWORD length) {
    HANDLE file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, nullptr, CREATE_NEW,
        FILE_ATTRIBUTE_NORMAL | FILE_FLAG_WRITE_THROUGH | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
    if (file == INVALID_HANDLE_VALUE) return false;
    DWORD written = 0;
    const bool okay = WriteFile(file, contents, length, &written, nullptr) && written == length && FlushFileBuffers(file);
    const bool closed = CloseHandle(file) != FALSE;
    // Partial or complete claims are deliberately retained forever.
    return okay && closed;
}
static bool freeze(const char* reason) {
    const bool newly_frozen = !session_frozen;
    session_frozen = true;
    eu4_lab_1375::fail_window(acceptance_window);
    if (newly_frozen && !audit_failed) {
        char line[768]{};
        sprintf_s(line, "{\"event\":\"lab_session_frozen\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"reason\":\"%s\",\"retry_allowed\":false}",
            GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(last_sequence), reason);
        durable_log(line);
    }
    return false;
}

static bool observe_world(bool require_pause, bool acquire, eu4_test_controls_1375::Snapshot* snapshot = nullptr) {
    eu4_test_controls_1375::Snapshot observed{};
    uint32_t fault = 0;
    uintptr_t world = 0, database = 0, array = 0, country = 0;
    uint64_t player = 0;
    if (!eu4_test_controls_1375::observe(observed, fault)
        || !read_value(game_base + 0x233fe78, world) || !object_pointer(world)
        || !read_value(game_base + 0x233d8d0, database) || !object_pointer(database)
        || !read_value(database + 0x118, array) || !object_pointer(array)
        || !read_value(world + 0x1e60, player) || player != france_handle
        || observed.game_cookie != world || observed.player_handle != player || observed.raw_date <= 0
        || observed.world_reset_active || observed.load_source_present || observed.native_multiplayer_classifier
        || !read_value(array + 122 * 8, country) || !object_pointer(country)) {
        if (world_locked) freeze("world_unavailable_or_loading_flag");
        return false;
    }
    uint64_t identity = 0;
    if (!read_value(country + 0x20, identity) || identity != player) {
        if (world_locked) freeze("player_full_identity_changed");
        return false;
    }
    if (world_locked && (world != locked_world || database != locked_database || array != locked_array
        || player != locked_player || observed.raw_date < locked_date)) {
        world_changed = true;
        return freeze("world_roots_player_or_date_regressed");
    }
    unsigned char acceptance_flag = 0;
    if (!read_value(world + 0x23a1, acceptance_flag) || acceptance_flag > 1) return freeze("acceptance_flag_unknown");
    const auto window_state = acceptance_window.state;
    if ((window_state == eu4_lab_1375::WindowState::closed || window_state == eu4_lab_1375::WindowState::awaiting_health)
        && acceptance_flag != 0) return freeze("acceptance_expected_zero");
    if ((window_state == eu4_lab_1375::WindowState::armed || window_state == eu4_lab_1375::WindowState::pending_submit
            || window_state == eu4_lab_1375::WindowState::submitted_known) && acceptance_flag != 1) return freeze("acceptance_expected_one");
    if (window_state != eu4_lab_1375::WindowState::closed && (world != acceptance_window.world
        || player != acceptance_window.player || observed.raw_date != acceptance_window.date
        || !observed.paused || GetCurrentThreadId() != acceptance_window.thread)) return freeze("acceptance_grant_world_changed");
    if (require_pause && !observed.paused) return false; // Running speed itself never invalidates the session.
    if (!world_locked && acquire) {
        locked_world = world; locked_database = database; locked_array = array;
        locked_player = player; locked_date = observed.raw_date; world_locked = true;
    }
    if (world_locked) locked_date = observed.raw_date; // Monotonic, not a permanent date equality gate.
    if (snapshot) *snapshot = observed;
    return true;
}

struct ActiveRequest {
    eu4_lab_1375::MailboxRequest request;
    bool durable_claim;
    bool operation_entered;
    bool lease_pause;
};
static ActiveRequest lease_operation{};
static bool lease_active = false;
static ULONGLONG lease_deadline = 0;
static int32_t lease_start_date = 0;
static constexpr ULONGLONG lease_duration_ms = 5000;
static constexpr int32_t lease_max_raw_date_delta = 48; // Two native 24-hour dates.
static bool request_guard(const ActiveRequest& operation, bool require_pause) {
    return operation.durable_claim && !session_frozen && !audit_failed && !world_changed && world_locked
        && tested && selftest_passed && owned_phase::permits_later(owned_peace)
        && preview_tested && preview_passed && command_tested && command_passed
        && GetCurrentThreadId() == window_thread && !InterlockedCompareExchange(&thread_changed, 0, 0)
        && operation.request.pid == GetCurrentProcessId() && operation.request.creation == process_created
        && operation.request.sequence == last_sequence
        && (operation.operation_entered || GetTickCount64() < operation.request.expires)
        && observe_world(require_pause, false);
}
static bool pair_guard(void* user, const eu4_pair_1375::GuardInput* input) {
    auto operation = static_cast<ActiveRequest*>(user);
    return input != nullptr && !std::strcmp(operation->request.operation, "pair")
        && request_guard(*operation, true) && input->observed.pid == GetCurrentProcessId()
        && input->observed.process_creation_filetime == process_created && input->observed.thread_id == window_thread
        && input->observed.world_cookie == locked_world && input->observed.player_handle == locked_player
        && input->observed.raw_date == locked_date;
}
static bool controls_guard(void* user, const eu4_test_controls_1375::GuardInput* input) {
    auto operation = static_cast<ActiveRequest*>(user);
    if (input == nullptr || std::strcmp(operation->request.operation, "speed") || input->requested_speed != operation->request.speed) return false;
    // TTL applies before native entry; after-call cleanup/readback must not be
    // mistaken for a retry when the original request expires during the call.
    if (input->point == eu4_test_controls_1375::GuardPoint::after_call) operation->operation_entered = true;
    return request_guard(*operation, false) && input->observed.game_cookie == locked_world
        && input->observed.player_handle == locked_player && input->observed.raw_date == locked_date;
}
static bool fixture_guard(void* user, const eu4_test_fixture_1375::GuardInput* input) {
    auto operation = static_cast<ActiveRequest*>(user);
    if (input == nullptr || std::strcmp(operation->request.operation, "fixture")) return false;
    const auto expected = !std::strcmp(operation->request.action, "fixture_on")
        ? eu4_test_fixture_1375::Operation::enable : eu4_test_fixture_1375::Operation::disable;
    if (input->operation != expected) return false;
    if (input->point != eu4_test_fixture_1375::GuardPoint::before_call) operation->operation_entered = true;
    return request_guard(*operation, true) && input->observed.game_cookie == locked_world
        && input->observed.player_handle == locked_player && input->observed.raw_date == locked_date;
}
// This publisher attestation binds reviewed disk definitions installed before
// process start. It is not proof that the engine registered a mod or its effect.
static bool fixture_attestation(uint64_t sequence) {
    wchar_t path[MAX_PATH]{};
    if (!sequence_path(path, sequence, L"fixture-profile")) return false;
    char expected[256]{};
    const int length = sprintf_s(expected,
        "EU4FIXTURE/1\npid=%lu\ncreation=%016llx\nsequence=%llu\nprofile=%s\n",
        GetCurrentProcessId(), static_cast<unsigned long long>(process_created),
        static_cast<unsigned long long>(sequence), fixture_profile_sha256);
    if (length <= 0 || static_cast<size_t>(length) >= sizeof(expected)) return false;
    HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
    if (file == INVALID_HANDLE_VALUE) return false;
    BY_HANDLE_FILE_INFORMATION information{};
    char actual[256]{};
    DWORD bytes = 0;
    const bool okay = GetFileInformationByHandle(file, &information)
        && !(information.dwFileAttributes & (FILE_ATTRIBUTE_REPARSE_POINT | FILE_ATTRIBUTE_DIRECTORY))
        && information.nNumberOfLinks == 1 && information.nFileSizeHigh == 0
        && information.nFileSizeLow == static_cast<DWORD>(length)
        && ReadFile(file, actual, static_cast<DWORD>(length), &bytes, nullptr)
        && bytes == static_cast<DWORD>(length) && !std::memcmp(expected, actual, bytes);
    const bool closed = CloseHandle(file) != FALSE;
    return okay && closed;
}
static bool request_logger(void* user, const char* json, size_t length) {
    auto operation = static_cast<ActiveRequest*>(user);
    if (json == nullptr || length == 0 || length >= 3000 || strnlen_s(json, length + 1) != length) return freeze("invalid_native_audit_record");
    char line[4096]{};
    const int count = std::snprintf(line, sizeof(line),
        "{\"event\":\"lab_native_record\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"lease_pause\":%s,\"record\":%s}",
        GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(operation->request.sequence),
        operation->lease_pause ? "true" : "false", json);
    return count > 0 && static_cast<size_t>(count) < sizeof(line) && durable_log(line);
}

// Generator-only fragment; inserted into the single versioned host .cpp.
static const char* acceptance_state_name() {
    switch (acceptance_window.state) {
        case eu4_lab_1375::WindowState::closed: return "closed";
        case eu4_lab_1375::WindowState::pending_on: return "pending_on";
        case eu4_lab_1375::WindowState::armed: return "armed";
        case eu4_lab_1375::WindowState::pending_submit: return "pending_submit";
        case eu4_lab_1375::WindowState::submitted_known: return "submitted_known";
        case eu4_lab_1375::WindowState::pending_off: return "pending_off";
        case eu4_lab_1375::WindowState::awaiting_health: return "awaiting_health";
        default: return "unknown";
    }
}
static bool fresh_acceptance_legality(const eu4_lab_1375::MailboxRequest& r) {
    return last_legality.valid && last_legality.request.sequence + 1 == r.sequence
        && last_legality.request.expires > GetTickCount64()
        && !strcmp(last_legality.request.action, r.bound_action)
        && !strcmp(last_legality.request.target, r.bound_target)
        && !strcmp(last_legality.request.actor, "FRA")
        && last_legality.world == locked_world && last_legality.date == locked_date;
}
static bool acceptance_guard(void* user, const eu4_test_acceptance_1375::GuardInput* input) {
    auto operation = static_cast<ActiveRequest*>(user);
    if (!input || strcmp(operation->request.operation, "accept")) return false;
    const bool on = !strcmp(operation->request.action, "accept_on");
    if (input->operation != (on ? eu4_test_acceptance_1375::Operation::enable : eu4_test_acceptance_1375::Operation::disable)) return false;
    if (input->point != eu4_test_acceptance_1375::GuardPoint::before_call) operation->operation_entered = true;
    if (!request_guard(*operation, true) || input->observed.game_cookie != locked_world
        || input->observed.player_handle != locked_player || input->observed.raw_date != locked_date) return false;
    if (on) return acceptance_window.state == eu4_lab_1375::WindowState::pending_on
        && eu4_lab_1375::same_binding(acceptance_window, operation->request)
        && operation->request.sequence == acceptance_window.on_sequence
        && (operation->operation_entered || fresh_acceptance_legality(operation->request));
    if (acceptance_window.state == eu4_lab_1375::WindowState::closed)
        return input->point == eu4_test_acceptance_1375::GuardPoint::before_call && input->raw_flag == 0;
    return acceptance_window.state == eu4_lab_1375::WindowState::pending_off
        && eu4_lab_1375::same_binding(acceptance_window, operation->request)
        && operation->request.sequence == acceptance_window.off_sequence;
}
static void process_acceptance(ActiveRequest& operation) {
    const bool on = !strcmp(operation.request.action, "accept_on");
    unsigned char raw_flag = 0;
    if (!request_guard(operation, true) || !read_value(locked_world + 0x23a1, raw_flag) || raw_flag > 1) {
        freeze("acceptance_initial_guard"); return;
    }
    char line[3000]{};
    if (on) {
        if (!eu4_lab_1375::reserve_on(acceptance_window, operation.request, raw_flag,
                fresh_acceptance_legality(operation.request), locked_world, locked_player, locked_date, window_thread)) {
            freeze("acceptance_on_binding_or_legality"); return;
        }
        const int count = std::snprintf(line, sizeof(line),
            "{\"event\":\"lab_acceptance_pending\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\","
            "\"sequence\":%llu,\"bound_action\":\"%s\",\"bound_target\":\"%s\",\"bound_submit_sequence\":%llu,"
            "\"off_sequence\":%llu,\"uptime_ms\":%llu,\"legality_sequence\":%llu,\"legality_expires\":%llu,"
            "\"native_invoked\":false,\"retry_allowed\":false}",
            GetCurrentProcessId(), static_cast<unsigned long long>(process_created),
            static_cast<unsigned long long>(last_sequence), acceptance_window.action, acceptance_window.target,
            static_cast<unsigned long long>(acceptance_window.submit_sequence), static_cast<unsigned long long>(acceptance_window.off_sequence),
            static_cast<unsigned long long>(GetTickCount64()), static_cast<unsigned long long>(last_legality.request.sequence),
            static_cast<unsigned long long>(last_legality.request.expires));
        if (count <= 0 || static_cast<size_t>(count) >= sizeof(line) || !durable_log(line)) { freeze("acceptance_pending_audit"); return; }
    } else if (acceptance_window.state != eu4_lab_1375::WindowState::closed) {
        if (raw_flag != 1 || !eu4_lab_1375::begin_bound_off(acceptance_window, operation.request)) {
            freeze("acceptance_off_binding"); return;
        }
    } else if (raw_flag != 0) { freeze("acceptance_closed_flag_changed"); return; }
    eu4_test_acceptance_1375::Host host{sizeof(host), eu4_test_acceptance_1375::kAbiVersion, window_thread, true,
        selftest_passed && owned_phase::permits_later(owned_peace) && preview_passed && command_passed,
        acceptance_guard, request_logger, &operation};
    const auto result = eu4_test_acceptance_1375::invoke(on ? eu4_test_acceptance_1375::Operation::enable
                                                         : eu4_test_acceptance_1375::Operation::disable, host);
    any_dispatch_entered = any_dispatch_entered || result.native_invoked;
    const bool normal = result.reason == eu4_test_acceptance_1375::Reason::none && !result.no_native
        && result.native_invoked && result.callback_returned && result.callback_success && result.callback_result_identity
        && result.zero_arguments_confirmed && result.arguments_unchanged && result.result_destroyed
        && result.world_identity_unchanged && result.readback_observed && result.readback_matches
        && result.before_flag_observed && result.after_flag_observed
        && result.before_raw_flag == (on ? 0u : 1u) && result.after_raw_flag == (on ? 1u : 0u);
    const bool harmless_no_native = !on && result.reason == eu4_test_acceptance_1375::Reason::already_desired
        && result.no_native && acceptance_window.state == eu4_lab_1375::WindowState::closed
        && result.before_flag_observed && result.after_flag_observed && result.before_raw_flag == 0 && result.after_raw_flag == 0
        && !result.native_invoked && !result.callback_returned && !result.callback_success && !result.result_destroyed;
    if ((!normal && !harmless_no_native) || result.freeze_session || result.exception_code || !result.audit_complete)
        freeze("acceptance_unknown_or_audit_failed");
    const LONG completion_frame = InterlockedCompareExchange(&frames, 0, 0);
    char before[16] = "null", after[16] = "null";
    if (result.before_flag_observed) sprintf_s(before, "%u", result.before_raw_flag);
    if (result.after_flag_observed) sprintf_s(after, "%u", result.after_raw_flag);
    const int count = std::snprintf(line, sizeof(line),
        "{\"event\":\"lab_request_complete\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,"
        "\"operation\":\"accept\",\"action\":\"%s\",\"reason\":%u,\"exception_code\":%u,\"completion_frame\":%ld,"
        "\"before_raw_flag\":%s,\"after_raw_flag\":%s,\"no_native\":%s,\"native_invoked\":%s,\"callback_returned\":%s,"
        "\"callback_success\":%s,\"result_destroyed\":%s,\"arguments_unchanged\":%s,\"readback_observed\":%s,\"readback_matches\":%s,"
        "\"world_identity_unchanged\":%s,\"callback_result_identity\":%s,\"zero_arguments_confirmed\":%s,\"audit_complete\":%s,"
        "\"session_frozen\":%s,\"natural_ai_acceptance_verified\":false,\"applied_verified\":false,\"retry_allowed\":false}",
        GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(last_sequence),
        operation.request.action, static_cast<unsigned>(result.reason), result.exception_code, completion_frame, before, after,
        result.no_native ? "true" : "false", result.native_invoked ? "true" : "false", result.callback_returned ? "true" : "false",
        result.callback_success ? "true" : "false", result.result_destroyed ? "true" : "false", result.arguments_unchanged ? "true" : "false",
        result.readback_observed ? "true" : "false", result.readback_matches ? "true" : "false", result.world_identity_unchanged ? "true" : "false",
        result.callback_result_identity ? "true" : "false", result.zero_arguments_confirmed ? "true" : "false",
        result.audit_complete ? "true" : "false", session_frozen ? "true" : "false");
    if (count <= 0 || static_cast<size_t>(count) >= sizeof(line) || !durable_log(line)) { freeze("acceptance_completion_audit"); return; }
    if (session_frozen) return;
    if (normal) {
        acceptance_window.state = on ? eu4_lab_1375::WindowState::armed : eu4_lab_1375::WindowState::awaiting_health;
        if (!on) acceptance_window.off_frame = completion_frame;
    }
    last_legality.valid = false;
}


// v15: bounded pre-handle sharing wait. This never retries a claimed operation.
// The verified request handle remains exclusive through claim and disposition.
enum class InputState { absent, deferred, consumed, failed };
static constexpr ULONGLONG input_wait_limit_ms = 250;
static constexpr unsigned input_wait_max_attempts = 16;
struct InputWait {
    bool active = false;
    ULONGLONG started = 0;
    unsigned attempts = 0;
    uint64_t sequence = 0;
};
static InputWait input_waits[5]{};
struct InputFault {
    const char* stage = "none";
    DWORD error = 0, close_error = 0;
    ULONGLONG now = 0, expires = 0;
    bool claim_created = false, claim_flushed = false, request_deleted = false;
};
static void input_fault(InputFault& fault, const char* stage, DWORD error) {
    fault.stage = stage;
    fault.error = error;
    fault.now = GetTickCount64();
}
static bool input_wait_log(const char* event, const char* outcome, const char* kind,
                           uint64_t sequence, const InputWait& wait, ULONGLONG now) {
    char line[1024]{};
    sprintf_s(line,
        "{\"event\":\"lab_input_wait\",\"wait_state\":\"%s\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"input_sequence\":%llu,\"input_kind\":\"%s\",\"outcome\":\"%s\",\"win32_error\":32,\"uptime_ms\":%llu,\"attempts\":%u,\"elapsed_ms\":%llu,\"maximum_wait_ms\":250,\"maximum_attempts\":16,\"claim_created\":false,\"native_invoked\":false,\"retry_allowed\":false}",
        event, GetCurrentProcessId(), static_cast<unsigned long long>(process_created),
        static_cast<unsigned long long>(last_sequence), static_cast<unsigned long long>(sequence), kind, outcome,
        static_cast<unsigned long long>(now), wait.attempts, static_cast<unsigned long long>(now >= wait.started ? now - wait.started : 0));
    return durable_log(line);
}
static bool input_wait_finish(InputWait& wait, const char* outcome, const char* kind, uint64_t sequence, ULONGLONG now) {
    if (!wait.active) return true;
    const bool logged = input_wait_log("end", outcome, kind, sequence, wait, now);
    wait.active = false;
    return logged;
}
static InputState input_failed(const InputFault& fault, const InputWait& wait, const char* kind,
                               uint64_t sequence, DWORD length) {
    char line[1400]{};
    sprintf_s(line,
        "{\"event\":\"lab_input_failed\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"input_sequence\":%llu,\"input_kind\":\"%s\",\"stage\":\"%s\",\"win32_error\":%lu,\"close_win32_error\":%lu,\"uptime_ms\":%llu,\"expires\":%llu,\"bytes\":%lu,\"attempts\":%u,\"claim_created\":%s,\"claim_flushed\":%s,\"request_deleted\":%s,\"native_invoked\":false,\"retry_allowed\":false}",
        GetCurrentProcessId(), static_cast<unsigned long long>(process_created),
        static_cast<unsigned long long>(last_sequence), static_cast<unsigned long long>(sequence), kind, fault.stage,
        fault.error, fault.close_error, static_cast<unsigned long long>(fault.now), static_cast<unsigned long long>(fault.expires),
        length, wait.attempts, fault.claim_created ? "true" : "false", fault.claim_flushed ? "true" : "false",
        fault.request_deleted ? "true" : "false");
    durable_log(line);
    return InputState::failed;
}
static bool input_create_claim(const wchar_t* path, const char* raw, DWORD length, InputFault& fault) {
    HANDLE claim = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, nullptr, CREATE_NEW,
        FILE_ATTRIBUTE_NORMAL | FILE_FLAG_WRITE_THROUGH | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
    if (claim == INVALID_HANDLE_VALUE) { input_fault(fault, "claim_open", GetLastError()); return false; }
    fault.claim_created = true;
    DWORD written = 0;
    bool okay = false;
    if (!WriteFile(claim, raw, length, &written, nullptr)) input_fault(fault, "claim_write", GetLastError());
    else if (written != length) input_fault(fault, "claim_length", ERROR_SUCCESS);
    else if (!FlushFileBuffers(claim)) input_fault(fault, "claim_flush", GetLastError());
    else { okay = true; fault.claim_flushed = true; }
    if (!CloseHandle(claim)) {
        const DWORD error = GetLastError();
        if (okay) input_fault(fault, "claim_close", error);
        else fault.close_error = error;
        okay = false;
    }
    // Partial claims survive forever. No retries after successful CREATE_NEW.
    return okay;
}
static InputState consume_input(const wchar_t* path, const wchar_t* claim_path, const char* expected, size_t expected_length,
                                char (&raw)[eu4_lab_1375::kMaxRequestBytes + 1], DWORD& length,
                                InputWait& wait, const char* kind, uint64_t sequence) {
    length = 0;
    InputFault fault{};
    ULONGLONG now = GetTickCount64();
    if (wait.active && (wait.sequence != sequence || now < wait.started
                       || now - wait.started >= input_wait_limit_ms || wait.attempts >= input_wait_max_attempts)) {
        input_wait_finish(wait, "budget_exhausted", kind, sequence, now);
        input_fault(fault, "open_wait_budget", ERROR_SHARING_VIOLATION);
        return input_failed(fault, wait, kind, sequence, length);
    }
    if (wait.active) ++wait.attempts;
    else wait = {false, now, 1, sequence};
    HANDLE file = CreateFileW(path, GENERIC_READ | DELETE, 0, nullptr, OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        const DWORD error = GetLastError(); // Capture before time/log/other APIs.
        now = GetTickCount64();
        if (error == ERROR_FILE_NOT_FOUND && !wait.active) return InputState::absent;
        if (error == ERROR_SHARING_VIOLATION) {
            if (!wait.active) {
                wait = {true, now, 1, sequence};
                if (!input_wait_log("begin", "sharing_violation", kind, sequence, wait, now)) {
                    wait.active = false;
                    input_fault(fault, "wait_begin_audit", ERROR_SUCCESS);
                    return input_failed(fault, wait, kind, sequence, length);
                }
            }
            if (now - wait.started < input_wait_limit_ms && wait.attempts < input_wait_max_attempts) return InputState::deferred;
            input_wait_finish(wait, "budget_exhausted", kind, sequence, now);
            input_fault(fault, "open_wait_budget", error);
        } else {
            input_wait_finish(wait, error == ERROR_FILE_NOT_FOUND ? "disappeared" : "open_error", kind, sequence, now);
            input_fault(fault, "open", error);
        }
        return input_failed(fault, wait, kind, sequence, length);
    }
    bool okay = false;
    now = GetTickCount64();
    do {
        // A successful open delayed beyond the wait budget cannot consume it.
        if (wait.active && (now < wait.started || now - wait.started >= input_wait_limit_ms)) {
            input_wait_finish(wait, "budget_exhausted", kind, sequence, now);
            input_fault(fault, "open_wait_budget", ERROR_SHARING_VIOLATION); break;
        }
        if (!input_wait_finish(wait, "opened", kind, sequence, now)) {
            input_fault(fault, "wait_end_audit", ERROR_SUCCESS); break;
        }
        const DWORD file_type = GetFileType(file);
        if (file_type != FILE_TYPE_DISK) { input_fault(fault, "file_type", file_type == FILE_TYPE_UNKNOWN ? GetLastError() : ERROR_SUCCESS); break; }
        BY_HANDLE_FILE_INFORMATION info{};
        if (!GetFileInformationByHandle(file, &info)) { input_fault(fault, "file_info", GetLastError()); break; }
        if (info.dwFileAttributes & (FILE_ATTRIBUTE_REPARSE_POINT | FILE_ATTRIBUTE_DIRECTORY)) { input_fault(fault, "file_attributes", ERROR_SUCCESS); break; }
        if (info.nNumberOfLinks != 1) { input_fault(fault, "file_links", ERROR_SUCCESS); break; }
        LARGE_INTEGER size{};
        if (!GetFileSizeEx(file, &size)) { input_fault(fault, "file_size", GetLastError()); break; }
        if (size.QuadPart <= 0 || size.QuadPart > static_cast<LONGLONG>(eu4_lab_1375::kMaxRequestBytes)) { input_fault(fault, "size_range", ERROR_SUCCESS); break; }
        if (!ReadFile(file, raw, static_cast<DWORD>(eu4_lab_1375::kMaxRequestBytes), &length, nullptr)) { input_fault(fault, "read", GetLastError()); break; }
        if (length != static_cast<DWORD>(size.QuadPart)) { input_fault(fault, "read_length", ERROR_SUCCESS); break; }
        if (expected) {
            if (length != expected_length || memcmp(raw, expected, length)) { input_fault(fault, "marker_token", ERROR_SUCCESS); break; }
        } else {
            eu4_lab_1375::MailboxRequest parsed{};
            if (!eu4_lab_1375::parse_request(raw, length, parsed)) { input_fault(fault, "parse", ERROR_SUCCESS); break; }
            fault.expires = parsed.expires;
            if (parsed.pid != GetCurrentProcessId()) { input_fault(fault, "pid", ERROR_SUCCESS); break; }
            if (parsed.creation != process_created) { input_fault(fault, "creation", ERROR_SUCCESS); break; }
            if (parsed.sequence != last_sequence + 1 || parsed.sequence > eu4_lab_1375::kMaxSequence) { input_fault(fault, "sequence", ERROR_SUCCESS); break; }
            now = GetTickCount64();
            if (parsed.expires <= now) { input_fault(fault, "ttl_expired", ERROR_SUCCESS); break; }
            if (parsed.expires - now > eu4_lab_1375::kMaxTtlMs) { input_fault(fault, "ttl_range", ERROR_SUCCESS); break; }
            // Before CREATE_NEW claim: even a no-native diagnostic cannot consume a reserved slot.
            if (!eu4_lab_1375::permits(acceptance_window, parsed)) { input_fault(fault, "acceptance_window", ERROR_SUCCESS); break; }
        }
        if (!input_create_claim(claim_path, raw, length, fault)) break;
        FILE_DISPOSITION_INFO disposition{}; disposition.DeleteFile = TRUE;
        if (!SetFileInformationByHandle(file, FileDispositionInfo, &disposition, sizeof(disposition))) {
            input_fault(fault, "disposition", GetLastError()); break;
        }
        fault.request_deleted = true;
        okay = true;
    } while (false);
    if (!CloseHandle(file)) {
        const DWORD error = GetLastError();
        if (okay) input_fault(fault, "request_close", error);
        else fault.close_error = error;
        okay = false;
    }
    return okay ? InputState::consumed : input_failed(fault, wait, kind, sequence, length);
}


#include "owned-peace-host-1375.inc"

static void run_phase(unsigned phase) {
    if (phase > 2 || (phase > 0 && !owned_phase::permits_later(owned_peace))) {
        freeze("owned_peace_phase_gate_failed"); return;
    }
    const wchar_t* paths[] = {request_file, preview_request_file, command_request_file};
    const wchar_t* claims[] = {L"phase-lifecycle.claim", L"phase-preview.claim", L"phase-command.claim"};
    const char* tokens[] = {"PAIR_SELFTEST_1375\n", "PAIR_PREVIEW_1375\n", "PAIR_COMMAND_1375\n"};
    if (!input_waits[phase].active && marker_absent(paths[phase])) return;
    if (!observe_world(true, true)) { freeze("phase_requires_valid_paused_world"); return; }
    wchar_t claim[MAX_PATH]{};
    char raw[eu4_lab_1375::kMaxRequestBytes + 1]{};
    DWORD length = 0;
    if (!in_session_path(claim, claims[phase])) { freeze("phase_claim_path_failed"); return; }
    const InputState state = consume_input(paths[phase], claim, tokens[phase], strlen(tokens[phase]), raw, length,
        input_waits[phase], phase == 0 ? "lifecycle" : (phase == 1 ? "preview" : "command"), 0);
    if (state != InputState::consumed) { if (state == InputState::failed) freeze("invalid_or_claimed_phase_marker"); return; }
    bool passed = false;
    if (phase == 0) {
        tested = true;
        log_line("{\"event\":\"pair_selftest_begin\",\"send_enabled\":false,\"submitted\":false}");
        passed = pair_selftest(game_base, log_line);
        selftest_passed = passed && !audit_failed && observe_world(true, false);
        log_line(selftest_passed ? "{\"event\":\"pair_selftest_complete\",\"passed\":true,\"submitted\":false}"
                                : "{\"event\":\"pair_selftest_complete\",\"passed\":false,\"submitted\":false}");
    } else if (phase == 1) {
        preview_tested = true;
        log_line("{\"event\":\"pair_preview_begin\",\"submitted\":false,\"send_enabled\":false}");
        passed = pair_preview(game_base, log_line);
        preview_passed = passed && !audit_failed && observe_world(true, false);
        log_line(preview_passed ? "{\"event\":\"pair_preview_complete\",\"passed\":true,\"submitted\":false}"
                               : "{\"event\":\"pair_preview_complete\",\"passed\":false,\"submitted\":false}");
    } else {
        command_tested = true;
        log_line("{\"event\":\"pair_command_begin\",\"submitted\":false,\"send_enabled\":false}");
        passed = pair_command_selftest(game_base, log_line);
        command_passed = passed && !audit_failed && observe_world(true, false);
        log_line(command_passed ? "{\"event\":\"pair_command_complete\",\"passed\":true,\"submitted\":false}"
                               : "{\"event\":\"pair_command_complete\",\"passed\":false,\"submitted\":false}");
    }
    last_phase_frame = InterlockedCompareExchange(&frames, 0, 0);
    const bool phase_passed = phase == 0 ? selftest_passed : (phase == 1 ? preview_passed : command_passed);
    if (!passed || !phase_passed || audit_failed || session_frozen) freeze("preflight_failed");
}

static void service_lease() {
    if (!lease_active || session_frozen || audit_failed) return;
    const auto now = GetTickCount64();
    const int64_t elapsed_date = static_cast<int64_t>(locked_date) - lease_start_date;
    if (now < lease_deadline && elapsed_date < lease_max_raw_date_delta) return;
    // No next mailbox request is processed while this lease exists. Its origin
    // sequence therefore remains current, and pause is authorized by that
    // operation's explicit, documented bounded-running contract.
    wchar_t claim[MAX_PATH]{};
    if (!sequence_path(claim, lease_operation.request.sequence, L"lease-pause.claim")) { freeze("lease_claim_path_failed"); return; }
    char line[1024]{};
    const int count = sprintf_s(line,
        "{\"purpose\":\"bounded_running_lease_pause\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"origin_sequence\":%llu,\"deadline_uptime_ms\":%llu,\"maximum_raw_date_delta\":%d,\"speed\":0,\"retry_allowed\":false}\n",
        GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(lease_operation.request.sequence),
        static_cast<unsigned long long>(lease_deadline), lease_max_raw_date_delta);
    if (count <= 0 || !create_durable_file(claim, line, static_cast<DWORD>(count))) { freeze("lease_pause_claim_failed"); return; }
    lease_operation.durable_claim = true;
    lease_operation.operation_entered = true; // Original authorized speed operation already entered; TTL is not a retry timer.
    lease_operation.lease_pause = true;
    lease_operation.request.speed = 0;
    eu4_test_controls_1375::Host host{sizeof(host), eu4_test_controls_1375::kAbiVersion, window_thread, true,
        selftest_passed && owned_phase::permits_later(owned_peace), controls_guard, request_logger, &lease_operation};
    const auto result = eu4_test_controls_1375::set_speed(0, host);
    lease_active = false; // One attempt only, including uncertainty or failure.
    if (result.freeze_session || result.exception_code || !result.audit_complete || !result.readback_matches || !result.after.paused)
        freeze("lease_pause_not_verified");
    sprintf_s(line,
        "{\"event\":\"lab_lease_complete\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"reason\":%u,\"write_entered\":%s,\"callback_returned\":%s,\"paused_readback\":%s,\"readback_matches\":%s,\"session_frozen\":%s,\"retry_allowed\":false}",
        GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(last_sequence), static_cast<unsigned>(result.reason),
        result.write_entered ? "true" : "false", result.callback_returned ? "true" : "false", result.after.paused ? "true" : "false",
        result.readback_matches ? "true" : "false", session_frozen ? "true" : "false");
    durable_log(line);
}

static void process_mailbox() {
    if (acceptance_window.state == eu4_lab_1375::WindowState::awaiting_health) return;
    if (!owned_phase::permits_later(owned_peace) || !selftest_passed || !preview_passed || !command_passed) {
        freeze("mailbox_phase_gate_failed"); return;
    }
    if (last_sequence >= eu4_lab_1375::kMaxSequence) { freeze("sequence_exhausted"); return; }
    wchar_t path[MAX_PATH]{}, claim[MAX_PATH]{};
    if (!sequence_path(path, last_sequence + 1, L"request") || !sequence_path(claim, last_sequence + 1, L"claim")) { freeze("request_path_failed"); return; }
    char raw[eu4_lab_1375::kMaxRequestBytes + 1]{};
    DWORD length = 0;
    const InputState state = consume_input(path, claim, nullptr, 0, raw, length, input_waits[3], "request", last_sequence + 1);
    if (state == InputState::absent || state == InputState::deferred) return;
    if (state != InputState::consumed) { freeze("request_invalid_expired_or_already_claimed"); return; }
    ActiveRequest operation{};
    if (!eu4_lab_1375::parse_request(raw, length, operation.request)) { freeze("claimed_request_roundtrip_failed"); return; }
    operation.durable_claim = true;
    last_sequence = operation.request.sequence;
    char line[2048]{};
    sprintf_s(line, "{\"event\":\"lab_request_claimed\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"operation\":\"%s\",\"mode\":\"%s\",\"action\":\"%s\",\"actor\":\"%s\",\"target\":\"%s\",\"expires\":%llu,\"speed\":%u,\"bound_action\":\"%s\",\"bound_target\":\"%s\",\"bound_submit_sequence\":%llu,\"claimed_uptime_ms\":%llu,\"durable_claim\":true,\"retry_allowed\":false}",
        GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(last_sequence),
        operation.request.operation, operation.request.mode, operation.request.action, operation.request.actor, operation.request.target,
        static_cast<unsigned long long>(operation.request.expires), operation.request.speed,
        operation.request.bound_action, operation.request.bound_target, static_cast<unsigned long long>(operation.request.bound_submit_sequence),
        static_cast<unsigned long long>(GetTickCount64()));
    if (!durable_log(line)) return;
    if (!std::strcmp(operation.request.operation, "accept")) { process_acceptance(operation); return; }
    if (!std::strcmp(operation.request.operation, "speed") && operation.request.speed > 0 && !running_speed_enabled) {
        sprintf_s(line, "{\"event\":\"lab_request_complete\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"operation\":\"speed\",\"speed\":%u,\"pre_dispatch_rejected\":true,\"reason\":\"running_speed_lease_not_enabled\",\"write_entered\":false,\"session_frozen\":false,\"retry_allowed\":false}",
            GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(last_sequence), operation.request.speed);
        durable_log(line);
        return;
    }
    if (!std::strcmp(operation.request.operation, "pair")) {
        const bool forced_bound = acceptance_window.state == eu4_lab_1375::WindowState::armed;
        if (forced_bound && !eu4_lab_1375::begin_bound_submit(acceptance_window, operation.request)) {
            freeze("acceptance_bound_submit_mismatch"); return;
        }
        eu4_pair_1375::Request request{};
        if (!eu4_pair_1375::parse_action_id(operation.request.action, strlen(operation.request.action), &request.action)) { freeze("claimed_action_invalid"); return; }
        memcpy(request.actor, operation.request.actor, 4); memcpy(request.target, operation.request.target, 4);
        const auto mode = !std::strcmp(operation.request.mode, "submit") ? eu4_pair_1375::Mode::submit : eu4_pair_1375::Mode::legality_only;
        eu4_pair_1375::Host host{sizeof(host), eu4_pair_1375::kAbiVersion, window_thread, true,
            selftest_passed && owned_phase::permits_later(owned_peace) && preview_passed && command_passed, pair_guard, request_logger, &operation};
        const auto result = eu4_pair_1375::invoke(request, mode, host);
        any_dispatch_entered = any_dispatch_entered || result.submit_entered;
        if (result.freeze_session || result.ownership_uncertain || result.exception_code || !result.audit_complete) freeze("pair_core_uncertain_or_audit_failed");
        sprintf_s(line, "{\"event\":\"lab_request_complete\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"operation\":\"pair\",\"action\":\"%s\",\"status\":%u,\"reason\":%u,\"submit_entered\":%s,\"submit_returned\":%s,\"ownership_uncertain\":%s,\"session_frozen\":%s,\"audit_complete\":%s,\"applied_verified\":false,\"retry_allowed\":false}",
            GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(last_sequence), operation.request.action,
            static_cast<unsigned>(result.status), static_cast<unsigned>(result.reason), result.submit_entered ? "true" : "false",
            result.submit_returned ? "true" : "false", result.ownership_uncertain ? "true" : "false", session_frozen ? "true" : "false", result.audit_complete ? "true" : "false");
        if (!durable_log(line)) { freeze("pair_completion_audit_failed"); return; }
        if (forced_bound) {
            const bool known = !session_frozen && result.audit_complete && !result.freeze_session
                && !result.ownership_uncertain && !result.exception_code
                && (!result.submit_entered || (result.submit_returned && result.caller_container_consumed));
            if (!known) { freeze("acceptance_bound_submit_unknown"); return; }
            acceptance_window.state = eu4_lab_1375::WindowState::submitted_known;
        }
        last_legality.valid = !forced_bound && mode == eu4_pair_1375::Mode::legality_only && !session_frozen
            && result.status == eu4_pair_1375::Status::legality_only && result.reason == eu4_pair_1375::Reason::none
            && result.preview_called && result.preview_allowed && result.gate_called && result.gate_allowed
            && !result.submit_entered && !result.ownership_uncertain && !result.exception_code && result.audit_complete;
        if (last_legality.valid) {
            last_legality.request = operation.request; last_legality.world = result.stamp.world_cookie;
            last_legality.date = result.stamp.raw_date;
        }
        return;
    } else if (!std::strcmp(operation.request.operation, "fixture")) {
        if (!fixture_attestation(last_sequence)) { freeze("fixture_definition_attestation_missing_or_invalid"); return; }
        const auto choice = !std::strcmp(operation.request.action, "fixture_on")
            ? eu4_test_fixture_1375::Operation::enable : eu4_test_fixture_1375::Operation::disable;
        eu4_test_fixture_1375::Host host{sizeof(host), eu4_test_fixture_1375::kAbiVersion, window_thread,
            true, selftest_passed && owned_phase::permits_later(owned_peace) && preview_passed && command_passed, true, fixture_profile_sha256,
            fixture_guard, request_logger, &operation};
        const auto result = eu4_test_fixture_1375::invoke(choice, host);
        any_dispatch_entered = any_dispatch_entered || result.native_invoked;
        if (result.freeze_session || result.exception_code || !result.audit_complete) freeze("fixture_uncertain_or_audit_failed");
        sprintf_s(line,
            "{\"event\":\"lab_request_complete\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"operation\":\"fixture\",\"action\":\"%s\",\"reason\":%u,"
            "\"native_invoked\":%s,\"callback_returned\":%s,\"callback_success\":%s,\"result_destroyed\":%s,\"arguments_unchanged\":%s,\"callback_flag_restored\":%s,"
            "\"world_identity_unchanged\":%s,\"session_frozen\":%s,\"fixture_effect_verified\":false,\"applied_verified\":false,\"retry_allowed\":false}",
            GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(last_sequence), operation.request.action,
            static_cast<unsigned>(result.reason), result.native_invoked ? "true" : "false", result.callback_returned ? "true" : "false",
            result.callback_success ? "true" : "false", result.result_destroyed ? "true" : "false", result.arguments_unchanged ? "true" : "false",
            result.callback_flag_restored ? "true" : "false", result.world_identity_unchanged ? "true" : "false", session_frozen ? "true" : "false");
    } else {
        if (operation.request.speed > 0) {
            lease_operation = operation;
            lease_deadline = GetTickCount64() + lease_duration_ms;
            lease_start_date = locked_date;
            sprintf_s(line,
                "{\"event\":\"lab_lease_armed\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"deadline_uptime_ms\":%llu,\"maximum_raw_date_delta\":%d,\"initial_raw_date\":%d,\"automatic_pause\":true,\"reliable_generation_verified\":false}",
                GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(last_sequence),
                static_cast<unsigned long long>(lease_deadline), lease_max_raw_date_delta, lease_start_date);
            if (!durable_log(line)) return;
        }
        eu4_test_controls_1375::Host host{sizeof(host), eu4_test_controls_1375::kAbiVersion, window_thread, true,
            selftest_passed && owned_phase::permits_later(owned_peace), controls_guard, request_logger, &operation};
        const auto result = eu4_test_controls_1375::set_speed(operation.request.speed, host);
        if (result.freeze_session || result.exception_code || !result.audit_complete) freeze("controls_uncertain_or_audit_failed");
        if (operation.request.speed > 0 && !session_frozen && result.readback_matches && !result.after.paused) lease_active = true;
        sprintf_s(line, "{\"event\":\"lab_request_complete\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"operation\":\"speed\",\"speed\":%u,\"reason\":%u,\"write_entered\":%s,\"callback_returned\":%s,\"readback_matches\":%s,\"session_frozen\":%s,\"applied_verified\":false,\"retry_allowed\":false}",
            GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(last_sequence), operation.request.speed,
            static_cast<unsigned>(result.reason), result.write_entered ? "true" : "false", result.callback_returned ? "true" : "false",
            result.readback_matches ? "true" : "false", session_frozen ? "true" : "false");
    }
    last_legality.valid = false;
    durable_log(line);
}

extern "C" void research_frame_tick() {
    if (!InterlockedCompareExchange(&research_enabled, 0, 0)) return;
    const DWORD thread = GetCurrentThreadId();
    if (thread != window_thread) InterlockedExchange(&thread_changed, 1);
    if (InterlockedCompareExchange(&active, 1, 0)) return;
    __try {
        if (InterlockedCompareExchange(&thread_changed, 0, 0)) freeze("frame_thread_changed");
        const LONG count = InterlockedIncrement(&frames);
        eu4_test_controls_1375::Snapshot observed{};
        const bool ready = observe_world(false, false, &observed);
        const ULONGLONG now = GetTickCount64();
        if (now - last_log >= 1000 && !audit_failed) {
            last_log = now;
            unsigned char flag = 2; // 2 is an explicit invalid/unknown health value, never guessed zero.
            if (!ready || !read_value(observed.game_cookie + 0x23a1, flag) || flag > 1) freeze("acceptance_health_flag_unknown");
            const bool closes_acceptance = acceptance_window.state == eu4_lab_1375::WindowState::awaiting_health
                && flag == 0 && ready && observed.paused && !session_frozen && !world_changed && count > acceptance_window.off_frame;
            char line[3000]{};
            sprintf_s(line, "{\"event\":\"research_frame\",\"fixture_profile_sha256\":\"%s\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"thread\":%lu,\"uptime_ms\":%llu,\"frames\":%ld,\"thread_changed\":%s,\"world_ready\":%s,\"world_changed\":%s,\"session_frozen\":%s,\"world_cookie\":\"0x%llx\",\"player_handle\":\"0x%016llx\",\"raw_date\":%d,\"paused\":%s,\"native_speed_index\":%d,\"lifecycle_passed\":%s,\"owned_peace_tested\":%s,\"owned_peace_passed\":%s,\"preview_passed\":%s,\"command_passed\":%s,\"last_sequence\":%llu,\"mailbox_ready\":%s,\"running_speed_enabled\":%s,\"lease_active\":%s,\"lease_deadline_uptime_ms\":%llu,\"send_enabled\":%s,\"acceptance_flag\":%u,\"acceptance_state\":\"%s\",\"acceptance_origin_sequence\":%llu,\"acceptance_submit_sequence\":%llu,\"acceptance_off_sequence\":%llu,\"acceptance_action\":\"%s\",\"acceptance_target\":\"%s\"}",
                fixture_profile_sha256, GetCurrentProcessId(), static_cast<unsigned long long>(process_created), thread, static_cast<unsigned long long>(now), count,
                InterlockedCompareExchange(&thread_changed, 0, 0) ? "true" : "false", ready ? "true" : "false", world_changed ? "true" : "false",
                session_frozen ? "true" : "false", static_cast<unsigned long long>(observed.game_cookie), static_cast<unsigned long long>(observed.player_handle),
                observed.raw_date, observed.paused ? "true" : "false", observed.native_speed_index, selftest_passed ? "true" : "false",
                owned_peace.tested ? "true" : "false", owned_phase::permits_later(owned_peace) ? "true" : "false",
                preview_passed ? "true" : "false", command_passed ? "true" : "false", static_cast<unsigned long long>(last_sequence),
                ready && world_locked && selftest_passed && owned_phase::permits_later(owned_peace) && preview_passed && command_passed && !session_frozen && !lease_active ? "true" : "false",
                running_speed_enabled ? "true" : "false", lease_active ? "true" : "false", static_cast<unsigned long long>(lease_deadline), any_dispatch_entered ? "true" : "false",
                static_cast<unsigned>(flag), closes_acceptance ? "closed" : acceptance_state_name(), static_cast<unsigned long long>(acceptance_window.on_sequence),
                static_cast<unsigned long long>(acceptance_window.submit_sequence), static_cast<unsigned long long>(acceptance_window.off_sequence),
                acceptance_window.action, acceptance_window.target);
            if (durable_log(line) && ready && !session_frozen) {
                if (closes_acceptance) eu4_lab_1375::observe_closed_boundary(acceptance_window, flag, true, count);
                last_health_frame = count;
            }
        }
        if (!session_frozen && !audit_failed && ready && count >= 100) {
            // Exactly one phase or mailbox request per callback. No polling wait.
            if (lease_active) service_lease();
            else switch (owned_phase::next(tested, selftest_passed, owned_peace,
                preview_tested, preview_passed, command_tested, command_passed, last_health_frame > last_phase_frame)) {
                case owned_phase::Next::lifecycle: run_phase(0); break;
                case owned_phase::Next::owned_peace: run_owned_peace_phase(); break;
                case owned_phase::Next::preview: run_phase(1); break;
                case owned_phase::Next::command: run_phase(2); break;
                case owned_phase::Next::mailbox: process_mailbox(); break;
                case owned_phase::Next::none: break;
            }
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        const DWORD exception = GetExceptionCode();
        if (owned_peace.in_call) owned_phase::reject(owned_peace);
        session_frozen = true;
        eu4_lab_1375::fail_window(acceptance_window);
        if (!audit_failed) {
            char line[512]{};
            sprintf_s(line, "{\"event\":\"lab_host_exception\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"exception\":%lu,\"session_frozen\":true,\"retry_allowed\":false}",
                GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(last_sequence), exception);
            durable_log(line);
        }
        // Do not attempt any native cleanup or continue a phase after a fault.
    }
    InterlockedExchange(&active, 0);
}

static bool create_private_session(const wchar_t* dll_directory) {
    wchar_t folder[MAX_PATH]{};
    if (swprintf_s(folder, L"%ssession-%lu-%016llx", dll_directory, GetCurrentProcessId(), static_cast<unsigned long long>(process_created)) <= 0) return false;
    HANDLE token = nullptr;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) return false;
    alignas(TOKEN_USER) unsigned char information[4096]{};
    DWORD needed = 0;
    const bool queried = GetTokenInformation(token, TokenUser, information, sizeof(information), &needed) != FALSE;
    CloseHandle(token);
    if (!queried || needed > sizeof(information)) return false;
    LPWSTR sid = nullptr;
    if (!ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(information)->User.Sid, &sid)) return false;
    wchar_t sddl[512]{};
    const int count = swprintf_s(sddl, L"D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;%s)", sid);
    LocalFree(sid);
    if (count <= 0) return false;
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, SDDL_REVISION_1, &descriptor, nullptr)) return false;
    SECURITY_ATTRIBUTES attributes{sizeof(attributes), descriptor, FALSE};
    const bool created = CreateDirectoryW(folder, &attributes) != FALSE;
    LocalFree(descriptor);
    if (!created) return false; // Existing directories/claims can never be rearmed.
    if (wcscpy_s(session_directory, folder) || wcscat_s(session_directory, L"\\")) return false;
    return true;
}

// Copied audited frame installation/thread suspension logic in its own v6
// source. v4/v5 source files and binaries are never edited or overwritten.
#include "research-lab-bootstrap-1375.inc"
