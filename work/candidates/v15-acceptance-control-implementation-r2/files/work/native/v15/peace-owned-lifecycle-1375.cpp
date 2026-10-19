// Isolated, unbuilt research candidate. No command/legality/submit/GUI call.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
#include <cstring>
#include "peace-owned-lifecycle-1375.h"
#include "default-contract.h"
#include "pins.h"

namespace eu4_owned_peace_lifecycle_1375 {
namespace {
volatile LONG attempted = 0;
using Factory = void* (__fastcall*)(std::uint32_t, const void*);
using Clone = void* (__fastcall*)(const void*);
using Destructor = void* (__fastcall*)(void*, unsigned int);
constexpr std::uintptr_t kFactory = 0x35d210, kClone = 0x59ba40, kDestructor = 0x598b60;

template<class T> T read(std::uintptr_t address) {
    T value{};
    // Scalar observation only; no memcpy of a native owned object.
    std::memcpy(&value, reinterpret_cast<const void*>(address), sizeof(value));
    return value;
}
bool scalar_reader(void*, std::uintptr_t address, void* result, std::size_t bytes) {
    // The enclosing SEH boundary aborts the entire attempt on an invalid read.
    std::memcpy(result, reinterpret_cast<const void*>(address), bytes);
    return true;
}
bool image_matches(std::uintptr_t module) {
    if (module == 0 || read<std::uint16_t>(module) != IMAGE_DOS_SIGNATURE) return false;
    const auto nt_offset = read<std::uint32_t>(module + 0x3c);
    if (nt_offset < 0x40 || nt_offset > 4096) return false;
    const auto nt = module + nt_offset;
    if (read<std::uint32_t>(nt) != IMAGE_NT_SIGNATURE
        || read<std::uint16_t>(nt + 4) != IMAGE_FILE_MACHINE_AMD64
        || read<std::uint32_t>(nt + 8) != 0x66fe6ab9
        || read<std::uint16_t>(nt + 24) != IMAGE_NT_OPTIONAL_HDR64_MAGIC
        || read<std::uint32_t>(nt + 24 + 56) != 0x25e0000) return false;
    for (const auto& pin : generated::pins)
        if (std::memcmp(reinterpret_cast<const void*>(module + pin.rva), pin.bytes, pin.size) != 0) return false;
    for (const auto& pin : generated::slots)
        if (read<std::uintptr_t>(module + pin.address) != module + pin.method) return false;
    return true;
}
bool emit(const Host& host, Result& result, const char* event, unsigned step) {
    char line[2048]{};
    const int count = std::snprintf(line, sizeof(line),
        "{\"event\":\"%s\",\"step\":%u,\"action\":\"requestpeace\",\"token\":10556,"
        "\"thread_id\":%lu,\"reason\":%u,\"factory_entered\":%u,\"factory_returned\":%u,"
        "\"clone_entered\":%u,\"clone_returned\":%u,\"original_destroy_entered\":%u,"
        "\"original_destroy_returned\":%u,\"clone_destroy_entered\":%u,\"clone_destroy_returned\":%u,"
        "\"original_mismatch_mask\":%llu,\"clone_mismatch_mask\":%llu,\"distinct_owned_ranges\":%u,"
        "\"original_unchanged_after_clone\":%u,\"clone_unchanged_after_original_destroy\":%u,"
        "\"exception\":%lu,\"freeze_session\":%u,\"retry_allowed\":false,\"submitted\":false,"
        "\"execution_verified\":false}",
        event, step, static_cast<unsigned long>(result.thread_id), static_cast<unsigned>(result.reason),
        static_cast<unsigned>(result.factory_entered), static_cast<unsigned>(result.factory_returned),
        static_cast<unsigned>(result.clone_entered), static_cast<unsigned>(result.clone_returned),
        static_cast<unsigned>(result.original_destroy_entered), static_cast<unsigned>(result.original_destroy_returned),
        static_cast<unsigned>(result.clone_destroy_entered), static_cast<unsigned>(result.clone_destroy_returned),
        static_cast<unsigned long long>(result.original_mismatch_mask),
        static_cast<unsigned long long>(result.clone_mismatch_mask), static_cast<unsigned>(result.distinct_owned_ranges),
        static_cast<unsigned>(result.original_unchanged_after_clone),
        static_cast<unsigned>(result.clone_unchanged_after_original_destroy),
        static_cast<unsigned long>(result.exception_code), static_cast<unsigned>(result.freeze_session));
    if (count < 0 || static_cast<std::size_t>(count) >= sizeof(line)
        || !host.log(host.user, line, static_cast<std::size_t>(count))) {
        result.reason = Reason::audit_failed;
        result.freeze_session = true;
        return false;
    }
    return true;
}
bool before_call(const Host& host, Result& result, std::uintptr_t module, GuardPoint point, unsigned step) {
    // Durable step begin precedes a fresh guard and every native invocation.
    if (!emit(host, result, "owned_peace_lifecycle_step_begin", step)) return false;
    if (GetCurrentThreadId() != host.expected_game_thread) result.reason = Reason::wrong_thread;
    else if (!image_matches(module)) result.reason = Reason::image_pin;
    else if (!host.guard(host.user, point)) result.reason = Reason::guard_rejected;
    else return true;
    result.freeze_session = true;
    return false;
}
bool fail(Result& result, Reason reason) {
    result.reason = reason; result.freeze_session = true; return false;
}
bool body(const Host& host, Result& result, std::uintptr_t module) {
    if (!before_call(host, result, module, GuardPoint::before_factory, 1)) return false;
    result.factory_entered = true;
    const auto original = reinterpret_cast<std::uintptr_t>(
        reinterpret_cast<Factory>(module + kFactory)(0x293c, nullptr));
    result.factory_returned = true;
    auto original_state = contract::inspect(original, module, scalar_reader, nullptr);
    result.original_mismatch_mask = original_state.mismatch;
    if (original_state.mismatch != 0) return fail(result, Reason::factory_contract);
    if (!emit(host, result, "owned_peace_lifecycle_step_complete", 1)) return false;

    if (!before_call(host, result, module, GuardPoint::before_clone, 2)) return false;
    auto recheck = contract::inspect(original, module, scalar_reader, nullptr);
    if (!contract::same(original_state, recheck)) return fail(result, Reason::original_changed);
    const auto original_vtable = read<std::uintptr_t>(original);
    const auto clone_method = read<std::uintptr_t>(original_vtable + 0xb0);
    if (clone_method != module + kClone) return fail(result, Reason::image_pin);
    result.clone_entered = true;
    const auto copy = reinterpret_cast<std::uintptr_t>(
        reinterpret_cast<Clone>(clone_method)(reinterpret_cast<const void*>(original)));
    result.clone_returned = true;
    const auto copy_state = contract::inspect(copy, module, scalar_reader, nullptr);
    result.clone_mismatch_mask = copy_state.mismatch;
    if (copy_state.mismatch != 0) return fail(result, Reason::clone_contract);
    recheck = contract::inspect(original, module, scalar_reader, nullptr);
    result.original_unchanged_after_clone = contract::same(original_state, recheck);
    if (!result.original_unchanged_after_clone) return fail(result, Reason::original_changed);
    result.distinct_owned_ranges = contract::distinct(original_state, copy_state);
    if (!result.distinct_owned_ranges) return fail(result, Reason::ownership_alias);
    if (!emit(host, result, "owned_peace_lifecycle_step_complete", 2)) return false;

    if (!before_call(host, result, module, GuardPoint::before_original_destroy, 3)) return false;
    recheck = contract::inspect(original, module, scalar_reader, nullptr);
    const auto copy_before_destroy = contract::inspect(copy, module, scalar_reader, nullptr);
    if (!contract::same(original_state, recheck)) return fail(result, Reason::original_changed);
    if (!contract::same(copy_state, copy_before_destroy)) return fail(result, Reason::clone_contract);
    if (!contract::distinct(recheck, copy_before_destroy)) return fail(result, Reason::ownership_alias);
    const auto original_destructor = read<std::uintptr_t>(read<std::uintptr_t>(original));
    if (original_destructor != module + kDestructor) return fail(result, Reason::image_pin);
    result.original_destroy_entered = true;
    reinterpret_cast<Destructor>(original_destructor)(reinterpret_cast<void*>(original), 1);
    result.original_destroy_returned = true;
    // No further read of original, its embedded object, or its former allocations.
    recheck = contract::inspect(copy, module, scalar_reader, nullptr);
    result.clone_unchanged_after_original_destroy = contract::same(copy_state, recheck);
    if (!result.clone_unchanged_after_original_destroy) return fail(result, Reason::surviving_clone_changed);
    if (!emit(host, result, "owned_peace_lifecycle_step_complete", 3)) return false;

    if (!before_call(host, result, module, GuardPoint::before_clone_destroy, 4)) return false;
    recheck = contract::inspect(copy, module, scalar_reader, nullptr);
    if (!contract::same(copy_state, recheck)) return fail(result, Reason::surviving_clone_changed);
    const auto copy_destructor = read<std::uintptr_t>(read<std::uintptr_t>(copy));
    if (copy_destructor != module + kDestructor) return fail(result, Reason::image_pin);
    result.clone_destroy_entered = true;
    reinterpret_cast<Destructor>(copy_destructor)(reinterpret_cast<void*>(copy), 1);
    result.clone_destroy_returned = true;
    return emit(host, result, "owned_peace_lifecycle_step_complete", 4);
}
} // namespace

Result run_once(const Host& host) {
    Result result{};
    result.thread_id = GetCurrentThreadId();
    if (host.struct_size != sizeof(Host) || host.abi_version != kAbiVersion
        || host.expected_game_thread == 0 || !host.durable_attempt_claimed
        || !host.exact_process_and_game_sha256_verified || !host.isolated_lifecycle_authorized
        || host.guard == nullptr || host.log == nullptr) {
        result.reason = Reason::host_contract; return result;
    }
    if (result.thread_id != host.expected_game_thread) {
        result.reason = Reason::wrong_thread; return result;
    }
    if (InterlockedCompareExchange(&attempted, 1, 0) != 0) {
        result.reason = Reason::already_attempted; return result;
    }
    __try {
        const auto module = reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
        const bool steps_ok = body(host, result, module);
        if (result.reason != Reason::audit_failed) {
            result.audit_complete = emit(host, result, "owned_peace_lifecycle_return", 0);
            result.passed = steps_ok && result.audit_complete;
        }
    } __except ((result.exception_code = GetExceptionCode()), EXCEPTION_EXECUTE_HANDLER) {
        result.reason = Reason::native_exception;
        result.freeze_session = true;
        // No logger, native destructor or retry after SEH. Host persists Result
        // outside this call and retires the session. Partial ownership is unknown.
    }
    return result;
}
} // namespace eu4_owned_peace_lifecycle_1375
