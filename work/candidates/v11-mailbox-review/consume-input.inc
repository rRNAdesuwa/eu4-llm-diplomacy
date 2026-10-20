// v11: bounded pre-handle sharing wait. This never retries a claimed operation.
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
static InputWait input_waits[4]{};
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
