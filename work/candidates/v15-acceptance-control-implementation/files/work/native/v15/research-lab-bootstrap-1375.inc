// v6 copy of audited v5 frame patch/thread freeze logic; independent source.
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
    FILETIME created{}, exited{}, kernel{}, user{};
    if (!GetProcessTimes(GetCurrentProcess(), &created, &exited, &kernel, &user)) return 29;
    process_created = (static_cast<uint64_t>(created.dwHighDateTime) << 32) | created.dwLowDateTime;
    if (!process_created || exited.dwHighDateTime || exited.dwLowDateTime || !create_private_session(path)) return 31;
    if (!in_session_path(request_file, L"pair-selftest.request")
        || !in_session_path(preview_request_file, L"pair-preview.request")
        || !in_session_path(command_request_file, L"pair-command.request")
        || !in_session_path(owned_peace_request_file, L"owned-peace-lifecycle.request")) return 15;
    wchar_t log_path[MAX_PATH]{}, binding_path[MAX_PATH]{}, install_claim[MAX_PATH]{};
    if (!in_session_path(log_path, L"research-1375.jsonl") || !in_session_path(binding_path, L"session.json")
        || !in_session_path(install_claim, L"install.claim")) return 16;
    output = CreateFileW(log_path, FILE_APPEND_DATA, FILE_SHARE_READ, nullptr, CREATE_NEW,
        FILE_ATTRIBUTE_NORMAL | FILE_FLAG_WRITE_THROUGH, nullptr);
    if (output == INVALID_HANDLE_VALUE) return 17;
    char binding[768]{};
    const int binding_length = sprintf_s(binding,
        "{\"schema_version\":1,\"purpose\":\"restricted_pair_lab_1375_v15\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"window_thread\":%lu,\"game_sha256\":\"9AD3EFE1AF169F40EE577F9DAE5DEBBC87AF6FB8B5450FB345EBF110DC4D771A\",\"world_generation_verified\":false,\"runtime_verified\":false}\n",
        GetCurrentProcessId(), static_cast<unsigned long long>(process_created), window_thread);
    if (binding_length <= 0 || !create_durable_file(binding_path, binding, static_cast<DWORD>(binding_length))
        || !create_durable_file(install_claim, binding, static_cast<DWORD>(binding_length))) return 32;
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
        if (!durable_log(failure_message)) return 30;
        if (!retry) return result;
        Sleep(1); // Our suspension increments and handles have been released before waiting.
    }
    char message[640];
    sprintf_s(message, "{\"event\":\"research_hook_installed\",\"pid\":%lu,\"window_thread\":%lu,\"process_creation_filetime\":\"%016llx\",\"attempt\":%u,\"terminated_skipped\":%u,\"frame_rva\":\"0x10a6ec0\",\"send_enabled\":false,\"selftest_automatic\":false,\"owned_peace_automatic\":false,\"preview_automatic\":false,\"command_automatic\":false,\"submit_automatic\":false,\"explicit_research_submit_available\":true}\n", GetCurrentProcessId(), window_thread, static_cast<unsigned long long>(process_created), attempt, terminated_skipped);
    if (!durable_log(message)) return 30;
    InterlockedExchange(&research_enabled, 1);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE module, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) { self_module = module; DisableThreadLibraryCalls(module); }
    return TRUE;
}
