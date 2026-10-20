// EU4 1.37.5 lifecycle research only. No diplomacy send/execute entrypoint.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <cstring>

extern "C" void research_frame_stub();
extern "C" void research_original_trampoline();
extern "C" { void* research_trampoline = nullptr; }
extern "C" { void* research_return = nullptr; }
extern bool pair_selftest(uintptr_t, void (*)(const char*));
extern bool pair_preview(uintptr_t, void (*)(const char*));

static HMODULE self_module;
static uintptr_t game_base;
static HANDLE output = INVALID_HANDLE_VALUE;
static volatile LONG installed = 0, active = 0, frames = 0;
static volatile LONG research_enabled = 0;
static DWORD window_thread;
static volatile LONG thread_changed = 0;
static bool tested = false, selftest_passed = false, preview_tested = false;
static ULONGLONG last_log;
using NextThread = LONG (NTAPI*)(HANDLE, HANDLE, ACCESS_MASK, ULONG, ULONG, PHANDLE);
static NextThread next_thread;
static wchar_t request_file[MAX_PATH];
static wchar_t preview_request_file[MAX_PATH];
static const unsigned char prefix[20] = {
    0x4c,0x89,0x44,0x24,0x18,0x55,0x53,0x57,0x48,0x8d,
    0x6c,0x24,0xb0,0x48,0x81,0xec,0x50,0x01,0x00,0x00};
static constexpr uintptr_t frame_rva = 0x10a6ec0;

static void log_line(const char* message) {
    DWORD written = 0;
    if (output != INVALID_HANDLE_VALUE) {
        char complete[2048];
        size_t length = strlen(message);
        if (length >= sizeof(complete) - 1) length = sizeof(complete) - 2;
        memcpy(complete, message, length);
        if (length == 0 || complete[length - 1] != '\n') complete[length++] = '\n';
        WriteFile(output, complete, static_cast<DWORD>(length), &written, nullptr);
        FlushFileBuffers(output);
    }
}

template<typename T> static bool read_value(uintptr_t address, T& value) {
    SIZE_T actual = 0;
    return address >= 0x10000 && ReadProcessMemory(GetCurrentProcess(),
        reinterpret_cast<const void*>(address), &value, sizeof(value), &actual)
        && actual == sizeof(value);
}

static bool world_ready() {
    uintptr_t world = 0, database = 0, array = 0, country = 0;
    uint64_t player = 0, identity = 0;
    if (!read_value(game_base + 0x233fe78, world)
        || !read_value(game_base + 0x233d8d0, database)
        || !read_value(world + 0x1e60, player)
        || !read_value(database + 0x118, array)) return false;
    unsigned slot = static_cast<unsigned>((player >> 32) & 0xffff);
    return slot < 4096 && read_value(array + slot * 8, country)
        && read_value(country + 0x20, identity) && identity == player
        && (player >> 56) != 0;
}

enum class MarkerState { absent, rejected, consumed };

static MarkerState consume_marker(const wchar_t* path, const char* expected, DWORD expected_length) {
    HANDLE request = CreateFileW(path, GENERIC_READ, 0, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (request == INVALID_HANDLE_VALUE) return MarkerState::absent;
    char token[64]{};
    DWORD length = 0;
    const bool valid = expected_length <= sizeof(token)
        && ReadFile(request, token, sizeof(token), &length, nullptr)
        && length == expected_length && memcmp(token, expected, expected_length) == 0;
    CloseHandle(request);
    return valid && DeleteFileW(path) ? MarkerState::consumed : MarkerState::rejected;
}

static bool marker_absent(const wchar_t* path) {
    if (GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES) return false;
    return GetLastError() == ERROR_FILE_NOT_FOUND;
}

extern "C" void research_frame_tick() {
    // The hook may become reachable before installation restoration finishes.
    if (!InterlockedCompareExchange(&research_enabled, 0, 0)) return;
    const DWORD thread = GetCurrentThreadId();
    // A concurrent foreign-thread callback must not be hidden by the reentry guard.
    if (thread != window_thread) InterlockedExchange(&thread_changed, 1);
    if (InterlockedCompareExchange(&active, 1, 0)) return;
    const LONG count = InterlockedIncrement(&frames);
    const ULONGLONG now = GetTickCount64();
    if (now - last_log >= 1000) {
        last_log = now;
        const bool ready = world_ready();
        char message[320];
        sprintf_s(message, "{\"event\":\"research_frame\",\"pid\":%lu,\"thread\":%lu,\"frames\":%ld,\"thread_changed\":%s,\"world_ready\":%s,\"send_enabled\":false}\n",
            GetCurrentProcessId(), thread, count, InterlockedCompareExchange(&thread_changed, 0, 0) ? "true" : "false", ready ? "true" : "false");
        log_line(message);
        if (ready && !InterlockedCompareExchange(&thread_changed, 0, 0) && count >= 100) {
            if (!tested) {
                static const char expected_request[] = "PAIR_SELFTEST_1375\n";
                const MarkerState marker = consume_marker(request_file, expected_request,
                    static_cast<DWORD>(sizeof(expected_request) - 1));
                if (marker != MarkerState::absent) {
                    tested = true; // Never retry lifecycle operations in this process.
                    if (marker == MarkerState::consumed) {
                        log_line("{\"event\":\"pair_selftest_begin\",\"send_enabled\":false,\"submitted\":false}\n");
                        selftest_passed = pair_selftest(game_base, log_line);
                        log_line(selftest_passed ? "{\"event\":\"pair_selftest_complete\",\"passed\":true,\"submitted\":false}\n"
                                                : "{\"event\":\"pair_selftest_complete\",\"passed\":false,\"submitted\":false}\n");
                    } else {
                        log_line("{\"event\":\"pair_selftest_request_rejected\",\"submitted\":false}\n");
                    }
                }
            } else if (selftest_passed && !preview_tested) {
                // A distinct explicit marker is required, on a later guarded callback.
                static const char expected_request[] = "PAIR_PREVIEW_1375\n";
                const MarkerState marker = consume_marker(preview_request_file, expected_request,
                    static_cast<DWORD>(sizeof(expected_request) - 1));
                if (marker != MarkerState::absent) {
                    preview_tested = true;
                    if (marker == MarkerState::consumed) {
                        log_line("{\"event\":\"pair_preview_begin\",\"send_enabled\":false,\"submitted\":false}\n");
                        const bool passed = pair_preview(game_base, log_line);
                        log_line(passed ? "{\"event\":\"pair_preview_complete\",\"passed\":true,\"submitted\":false}\n"
                                        : "{\"event\":\"pair_preview_complete\",\"passed\":false,\"submitted\":false}\n");
                    } else {
                        log_line("{\"event\":\"pair_preview_request_rejected\",\"submitted\":false}\n");
                    }
                }
            }
        }
    }
    InterlockedExchange(&active, 0);
}

static void absolute_jump(unsigned char* destination, uintptr_t address) {
    destination[0] = 0xff; destination[1] = 0x25;
    memset(destination + 2, 0, 4);
    memcpy(destination + 6, &address, 8);
}

// Freeze only this process, preserve prior suspension counts, reject patch races.
struct ThreadSet {
    HANDLE handles[512]{};
    DWORD ids[512]{};
    bool suspension_owned[512]{};
    unsigned count = 0, suspended = 0, terminated_skipped = 0;
    unsigned failure = 0;
    DWORD error = 0, failure_thread = 0;
    uintptr_t failure_rip = 0;
    bool released = false;
    unsigned resume_failures = 0;
    DWORD resume_error = 0, resume_failure_thread = 0;
    bool fail(unsigned stage, DWORD code = 0, DWORD thread = 0, uintptr_t rip = 0) {
        failure = stage; error = code; failure_thread = thread; failure_rip = rip;
        return false;
    }
    static bool definitely_exited(HANDLE thread) {
        DWORD code = STILL_ACTIVE;
        FILETIME created{}, exited{}, kernel{}, user{};
        return GetExitCodeThread(thread, &code) && code != STILL_ACTIVE
            && GetThreadTimes(thread, &created, &exited, &kernel, &user)
            && (exited.dwHighDateTime != 0 || exited.dwLowDateTime != 0);
    }
    bool collect() {
        // Use the same native enumeration for collection and verification.
        // ToolHelp and native enumeration differed persistently in the live
        // process; mixing their sets made a complete freeze impossible.
        HANDLE previous = nullptr;
        bool retained = false, complete = false;
        for (unsigned index = 0; index <= 513; ++index) {
            HANDLE current = nullptr;
            const LONG status = next_thread(GetCurrentProcess(), previous,
                THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_LIMITED_INFORMATION,
                0, 0, &current);
            if (previous && !retained) CloseHandle(previous);
            previous = current;
            retained = false;
            if (static_cast<ULONG>(status) == 0x8000001aUL) {
                complete = true;
                break;
            }
            if (status != 0 || !current) { fail(31, static_cast<DWORD>(status)); break; }
            const DWORD id = GetThreadId(current);
            if (!id) { fail(32, GetLastError()); break; }
            const DWORD owner = GetProcessIdOfThread(current);
            if (owner != GetCurrentProcessId()) { fail(33, owner ? ERROR_INVALID_OWNER : GetLastError(), id); break; }
            if (id == GetCurrentThreadId()) continue;
            if (count == 512) { fail(34); break; }
            ids[count] = id;
            handles[count++] = current;
            retained = true; // ThreadSet owns this handle until restoration.
        }
        if (previous && !retained) CloseHandle(previous);
        if (!complete && !failure) fail(35);
        if (complete && count == 0) return fail(34);
        return complete;
    }
    bool freeze(uintptr_t patch_start) {
        for (unsigned index = 0; index < count; ++index) {
            // Native enumeration includes terminated thread objects retained by
            // another handle. Such a thread cannot execute or be suspended.
            if (definitely_exited(handles[index])) { ++terminated_skipped; continue; }
            if (SuspendThread(handles[index]) == static_cast<DWORD>(-1)) {
                const DWORD suspend_error = GetLastError();
                if (definitely_exited(handles[index])) { ++terminated_skipped; continue; }
                return fail(36, suspend_error, ids[index]);
            }
            suspension_owned[index] = true;
            ++suspended;
            CONTEXT context{}; context.ContextFlags = CONTEXT_CONTROL;
            if (!GetThreadContext(handles[index], &context)) return fail(37, GetLastError(), ids[index]);
            if (context.Rip >= patch_start && context.Rip < patch_start + sizeof(prefix)) return fail(38, 0, ids[index], context.Rip);
        }
        // No ToolHelp/heap allocation after suspension: a stopped thread may
        // own a user-mode heap lock. The pre-resolved syscall enumerates handles.
        HANDLE previous = nullptr;
        bool stable = false;
        for (unsigned index = 0; index <= 512; ++index) {
            HANDLE current = nullptr;
            const LONG status = next_thread(GetCurrentProcess(), previous,
                THREAD_QUERY_LIMITED_INFORMATION, 0, 0, &current);
            if (previous) CloseHandle(previous);
            previous = current;
            if (static_cast<ULONG>(status) == 0x8000001aUL) {
                stable = true; // STATUS_NO_MORE_ENTRIES
                break;
            }
            if (status != 0 || !current) { fail(39, static_cast<DWORD>(status)); break; }
            const DWORD id = GetThreadId(current);
            if (!id) { fail(40, GetLastError()); break; }
            if (id != GetCurrentThreadId()) {
                bool found = false;
                for (unsigned known = 0; known < count; ++known) if (ids[known] == id) found = true;
                if (!found) { fail(41, 0, id); break; }
            }
        }
        if (previous) CloseHandle(previous);
        if (!stable && !failure) fail(42);
        return stable;
    }
    bool release() {
        if (released) return resume_failures == 0;
        released = true; // Never decrement a suspend count twice, including on failure.
        for (unsigned index = 0; index < count; ++index) {
            if (!suspension_owned[index]) continue;
            if (ResumeThread(handles[index]) == static_cast<DWORD>(-1)) {
                const DWORD code = GetLastError();
                if (!resume_failures) { resume_error = code; resume_failure_thread = ids[index]; }
                ++resume_failures;
            }
        }
        for (unsigned index = 0; index < count; ++index) CloseHandle(handles[index]);
        return resume_failures == 0;
    }
    ~ThreadSet() { release(); }
};

static BOOL CALLBACK find_window_thread(HWND window, LPARAM parameter) {
    if (!IsWindowVisible(window) || GetWindow(window, GW_OWNER)) return TRUE;
    DWORD owner = 0;
    const DWORD thread = GetWindowThreadProcessId(window, &owner);
    if (owner != GetCurrentProcessId()) return TRUE;
    auto selected = reinterpret_cast<DWORD*>(parameter);
    if (*selected && *selected != thread) { *selected = MAXDWORD; return FALSE; }
    *selected = thread;
    return TRUE;
}

extern "C" __declspec(dllexport) DWORD WINAPI BridgeStart(void*) {
    if (InterlockedCompareExchange(&installed, 1, 0)) return 10;
    game_base = reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
    const auto dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(game_base);
    const auto pe = reinterpret_cast<const IMAGE_NT_HEADERS64*>(game_base + dos->e_lfanew);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || pe->Signature != IMAGE_NT_SIGNATURE
        || pe->FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64
        || pe->FileHeader.TimeDateStamp != 1727949497 || pe->OptionalHeader.SizeOfImage != 0x25e0000) return 11;
    EnumWindows(find_window_thread, reinterpret_cast<LPARAM>(&window_thread));
    if (!window_thread || window_thread == MAXDWORD) return 25;
    const HMODULE ntdll = GetModuleHandleW(L"ntdll.dll");
    const FARPROC next_address = ntdll ? GetProcAddress(ntdll, "NtGetNextThread") : nullptr;
    static_assert(sizeof(next_thread) == sizeof(next_address));
    memcpy(&next_thread, &next_address, sizeof(next_thread));
    if (!next_thread) return 27;
    auto target = reinterpret_cast<unsigned char*>(game_base + frame_rva);
    if (memcmp(target, prefix, sizeof(prefix))) return 12;
    const unsigned char rdx_load[] = {0x48, 0x8b, 0x15};
    if (memcmp(target + sizeof(prefix), rdx_load, sizeof(rdx_load))) return 26;
    wchar_t path[MAX_PATH]{};
    const DWORD length = GetModuleFileNameW(self_module, path, MAX_PATH);
    if (!length || length >= MAX_PATH) return 13;
    wchar_t* slash = wcsrchr(path, L'\\');
    if (!slash) return 14;
    slash[1] = 0;
    if (wcscpy_s(request_file, path) || wcscat_s(request_file, L"pair-selftest.request")) return 15;
    if (wcscpy_s(preview_request_file, path) || wcscat_s(preview_request_file, L"pair-preview.request")) return 15;
    wchar_t log_path[MAX_PATH]{};
    if (wcscpy_s(log_path, path) || wcscat_s(log_path, L"research-1375.jsonl")) return 16;
    output = CreateFileW(log_path, FILE_APPEND_DATA, FILE_SHARE_READ, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (output == INVALID_HANDLE_VALUE) return 17;
    if (!marker_absent(request_file) || !marker_absent(preview_request_file)) {
        log_line("{\"event\":\"stale_or_unreadable_research_request_refused\",\"submitted\":false}\n"); return 18;
    }
    research_return = target + sizeof(prefix);
    research_trampoline = reinterpret_cast<void*>(&research_original_trampoline);
    unsigned char patch[20]; memset(patch, 0x90, sizeof(patch));
    absolute_jump(patch, reinterpret_cast<uintptr_t>(&research_frame_stub));
    DWORD result = 0;
    unsigned terminated_skipped = 0;
    constexpr unsigned max_attempts = 3;
    unsigned attempt = 0;
    for (attempt = 1; attempt <= max_attempts; ++attempt) {
        result = 0;
        DWORD old = 0;
        unsigned failure_details[8]{};
        uintptr_t failure_rip = 0;
        {
            ThreadSet threads;
            if (!threads.collect() || !threads.freeze(reinterpret_cast<uintptr_t>(target))) result = 21;
            else if (memcmp(target, prefix, sizeof(prefix))) result = 22;
            else if (!VirtualProtect(target, sizeof(prefix), PAGE_EXECUTE_READWRITE, &old)) result = 23;
            else {
                memcpy(target, patch, sizeof(patch));
                DWORD ignored = 0;
                const bool flushed = FlushInstructionCache(GetCurrentProcess(), target, sizeof(prefix)) != FALSE;
                if (!flushed || !VirtualProtect(target, sizeof(prefix), old, &ignored)) {
                    memcpy(target, prefix, sizeof(prefix));
                    FlushInstructionCache(GetCurrentProcess(), target, sizeof(prefix));
                    VirtualProtect(target, sizeof(prefix), old, &ignored);
                    result = 24;
                }
            }
            if (!threads.release()) result = 28;
            terminated_skipped = threads.terminated_skipped;
            if (result) {
                // Copy scalars only; restoration must finish before logging or retrying.
                failure_details[0] = threads.failure;
                failure_details[1] = threads.error;
                failure_details[2] = threads.failure_thread;
                failure_details[3] = threads.count;
                failure_details[4] = threads.suspended;
                failure_details[5] = threads.resume_failures;
                failure_details[6] = threads.resume_error;
                failure_details[7] = threads.resume_failure_thread;
                failure_rip = threads.failure_rip;
            }
        }
        if (!result) break; // The patch is installed once; never retry after mutation.
        const bool prefix_unchanged = memcmp(target, prefix, sizeof(prefix)) == 0;
        const bool retry = result == 21 && prefix_unchanged && attempt < max_attempts;
        char failure_message[768]{};
        sprintf_s(failure_message, "{\"event\":\"research_hook_refused\",\"pid\":%lu,\"result\":%lu,\"attempt\":%u,\"max_attempts\":%u,\"retrying\":%s,\"prefix_unchanged\":%s,\"stage\":%u,\"error\":%u,\"thread\":%u,\"collected\":%u,\"suspended\":%u,\"resume_failures\":%u,\"resume_error\":%u,\"resume_thread\":%u,\"rip\":\"0x%llx\",\"submitted\":false}\n",
            GetCurrentProcessId(), result, attempt, max_attempts, retry ? "true" : "false", prefix_unchanged ? "true" : "false",
            failure_details[0], failure_details[1], failure_details[2], failure_details[3], failure_details[4],
            failure_details[5], failure_details[6], failure_details[7], static_cast<unsigned long long>(failure_rip));
        log_line(failure_message);
        if (!retry) return result;
        Sleep(1); // Our suspension increments and handles have been released before waiting.
    }
    char message[320];
    sprintf_s(message, "{\"event\":\"research_hook_installed\",\"pid\":%lu,\"window_thread\":%lu,\"attempt\":%u,\"terminated_skipped\":%u,\"frame_rva\":\"0x10a6ec0\",\"send_enabled\":false,\"selftest_automatic\":false,\"preview_automatic\":false}\n", GetCurrentProcessId(), window_thread, attempt, terminated_skipped);
    log_line(message);
    InterlockedExchange(&research_enabled, 1);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE module, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) { self_module = module; DisableThreadLibraryCalls(module); }
    return TRUE;
}
