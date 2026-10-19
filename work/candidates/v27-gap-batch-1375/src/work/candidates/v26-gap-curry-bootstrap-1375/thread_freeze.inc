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

