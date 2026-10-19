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
