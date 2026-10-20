// New v15 phase only; included after the unchanged audited marker consumer.
static int32_t owned_peace_start_date = 0;
static bool owned_peace_guard(void*, eu4_owned_peace_lifecycle_1375::GuardPoint point) {
    if (static_cast<unsigned>(point) > 3 || !owned_peace.tested || !owned_peace.claim || !owned_peace.in_call
        || owned_peace.frozen || owned_peace.core_returned || !tested || !selftest_passed
        || session_frozen || audit_failed || world_changed || !world_locked || lease_active
        || GetCurrentThreadId() != window_thread || InterlockedCompareExchange(&thread_changed, 0, 0)) return false;
    FILETIME created{}, exited{}, kernel{}, user{};
    if (!GetProcessTimes(GetCurrentProcess(), &created, &exited, &kernel, &user)) return false;
    const uint64_t creation = (static_cast<uint64_t>(created.dwHighDateTime) << 32) | created.dwLowDateTime;
    return creation == process_created && !exited.dwHighDateTime && !exited.dwLowDateTime
        && observe_world(true, false) && locked_date == owned_peace_start_date;
}
static bool owned_peace_logger(void*, const char* core, size_t bytes) {
    if (!owned_peace.in_call || !owned_peace.claim || bytes < 2 || bytes >= 2048
        || !core || core[0] != '{' || core[bytes - 1] != '}' || strnlen_s(core, bytes + 1) != bytes
        || GetCurrentThreadId() != window_thread) return false;
    char line[3072]{};
    const int count = sprintf_s(line,
        "{\"event\":\"owned_peace_core_record\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\","
        "\"thread_id\":%lu,\"core\":%.*s,\"submitted\":false}",
        GetCurrentProcessId(), static_cast<unsigned long long>(process_created), GetCurrentThreadId(),
        static_cast<int>(bytes), core);
    return count > 0 && static_cast<size_t>(count) < sizeof(line) && durable_log(line);
}
static void run_owned_peace_phase() {
    if (!input_waits[4].active && marker_absent(owned_peace_request_file)) return;
    if (!tested || !selftest_passed || owned_peace.tested || owned_peace.frozen
        || last_health_frame <= last_phase_frame || !observe_world(true, false)) {
        owned_phase::reject(owned_peace); freeze("owned_peace_prerequisite_failed"); return;
    }
    wchar_t claim[MAX_PATH]{};
    char expected[192]{}, raw[eu4_lab_1375::kMaxRequestBytes + 1]{};
    size_t expected_size = 0; DWORD length = 0;
    if (!in_session_path(claim, L"phase-owned-peace-lifecycle.claim")
        || !owned_phase::format_marker(expected, sizeof(expected), GetCurrentProcessId(), process_created, expected_size)) {
        owned_phase::reject(owned_peace); freeze("owned_peace_marker_identity_failed"); return;
    }
    const InputState consumed = consume_input(owned_peace_request_file, claim, expected, expected_size,
        raw, length, input_waits[4], "owned_peace", 0);
    if (consumed != InputState::consumed) {
        if (consumed == InputState::failed) { owned_phase::reject(owned_peace); freeze("owned_peace_marker_failed"); }
        return;
    }
    if (!owned_phase::begin(owned_peace, tested, selftest_passed, last_health_frame > last_phase_frame, true)) {
        freeze("owned_peace_begin_rejected"); return;
    }
    owned_peace_start_date = locked_date;
    char line[2048]{};
    sprintf_s(line,
        "{\"event\":\"owned_peace_selftest_begin\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\","
        "\"thread_id\":%lu,\"durable_claim\":true,\"base_lifecycle_count\":20,\"send_enabled\":false,\"submitted\":false}",
        GetCurrentProcessId(), static_cast<unsigned long long>(process_created), GetCurrentThreadId());
    if (!durable_log(line)) { owned_phase::reject(owned_peace); freeze("owned_peace_begin_audit_failed"); return; }
    using namespace eu4_owned_peace_lifecycle_1375;
    Host host{sizeof(host), kAbiVersion, window_thread, true, selftest_passed, true,
              owned_peace_guard, owned_peace_logger, nullptr};
    const Result result = run_once(host);
    // Core has returned. The phase stays in_call until finish() so its last
    // read-only guard uses exactly the same session/identity preconditions.
    const bool post_guard = owned_phase::result_ok(result)
        && result.thread_id == window_thread && owned_peace_guard(nullptr, GuardPoint::before_clone_destroy);
    const bool candidate_passed = owned_phase::result_ok(result) && post_guard;
    sprintf_s(line,
        "{\"event\":\"owned_peace_selftest_complete\",\"record_kind\":\"wrapper_result\","
        "\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"thread_id\":%lu,\"passed\":%s,"
        "\"reason\":%u,\"core_passed\":%s,\"core_audit_complete\":%s,\"post_guard_ok\":%s,"
        "\"factory_entered\":%s,\"factory_returned\":%s,\"clone_entered\":%s,\"clone_returned\":%s,"
        "\"original_destroy_entered\":%s,\"original_destroy_returned\":%s,\"clone_destroy_entered\":%s,\"clone_destroy_returned\":%s,"
        "\"original_mismatch_mask\":%llu,\"clone_mismatch_mask\":%llu,\"distinct_owned_ranges\":%s,"
        "\"original_unchanged_after_clone\":%s,\"clone_unchanged_after_original_destroy\":%s,"
        "\"exception\":%u,\"freeze_session\":%s,\"retry_allowed\":false,\"execution_verified\":false,\"submitted\":false}",
        GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long>(result.thread_id), candidate_passed ? "true" : "false",
        static_cast<unsigned>(result.reason), result.passed ? "true" : "false", result.audit_complete ? "true" : "false", post_guard ? "true" : "false",
        result.factory_entered ? "true" : "false", result.factory_returned ? "true" : "false",
        result.clone_entered ? "true" : "false", result.clone_returned ? "true" : "false",
        result.original_destroy_entered ? "true" : "false", result.original_destroy_returned ? "true" : "false",
        result.clone_destroy_entered ? "true" : "false", result.clone_destroy_returned ? "true" : "false",
        static_cast<unsigned long long>(result.original_mismatch_mask), static_cast<unsigned long long>(result.clone_mismatch_mask),
        result.distinct_owned_ranges ? "true" : "false", result.original_unchanged_after_clone ? "true" : "false",
        result.clone_unchanged_after_original_destroy ? "true" : "false", result.exception_code,
        (!candidate_passed || result.freeze_session) ? "true" : "false");
    const bool wrapper_durable = durable_log(line);
    const bool passed = owned_phase::finish(owned_peace, result, post_guard, wrapper_durable);
    last_phase_frame = InterlockedCompareExchange(&frames, 0, 0);
    if (!passed) freeze("owned_peace_default_lifecycle_failed");
}
