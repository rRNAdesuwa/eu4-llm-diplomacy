"""Generate the isolated v15 host delta from frozen v14; no build/live action."""
from pathlib import Path


def transform(s, acceptance_source):
    def replace(old, new, count=1):
        nonlocal s
        assert s.count(old) == count, (old[:100], s.count(old))
        s = s.replace(old, new)
    replace('#include "lab-request-1375.h"', '#include "lab-request-1375.h"\n#include "test-acceptance-1375.h"')
    replace('static ULONGLONG last_log = 0;', '''static ULONGLONG last_log = 0;
static eu4_lab_1375::AcceptanceWindow acceptance_window{};
struct LastLegality {
    bool valid = false;
    eu4_lab_1375::MailboxRequest request{};
    uintptr_t world = 0;
    int32_t date = 0;
};
static LastLegality last_legality{};''')
    replace('    session_frozen = true;\n    if (newly_frozen', '    session_frozen = true;\n    eu4_lab_1375::fail_window(acceptance_window);\n    if (newly_frozen')
    replace('audit_failed = true; session_frozen = true;', 'audit_failed = true; session_frozen = true; eu4_lab_1375::fail_window(acceptance_window);', 3)
    replace('    if (require_pause && !observed.paused) return false;', '''    unsigned char acceptance_flag = 0;
    if (!read_value(world + 0x23a1, acceptance_flag) || acceptance_flag > 1) return freeze("acceptance_flag_unknown");
    const auto window_state = acceptance_window.state;
    if ((window_state == eu4_lab_1375::WindowState::closed || window_state == eu4_lab_1375::WindowState::awaiting_health)
        && acceptance_flag != 0) return freeze("acceptance_expected_zero");
    if ((window_state == eu4_lab_1375::WindowState::armed || window_state == eu4_lab_1375::WindowState::pending_submit
            || window_state == eu4_lab_1375::WindowState::submitted_known) && acceptance_flag != 1) return freeze("acceptance_expected_one");
    if (window_state != eu4_lab_1375::WindowState::closed && (world != acceptance_window.world
        || player != acceptance_window.player || observed.raw_date != acceptance_window.date
        || !observed.paused || GetCurrentThreadId() != acceptance_window.thread)) return freeze("acceptance_grant_world_changed");
    if (require_pause && !observed.paused) return false;''')
    replace('// v15: bounded pre-handle sharing wait.', acceptance_source + '\n\n// v15: bounded pre-handle sharing wait.')
    replace('            if (parsed.expires - now > eu4_lab_1375::kMaxTtlMs) { input_fault(fault, "ttl_range", ERROR_SUCCESS); break; }', '''            if (parsed.expires - now > eu4_lab_1375::kMaxTtlMs) { input_fault(fault, "ttl_range", ERROR_SUCCESS); break; }
            // Before CREATE_NEW claim: even a no-native diagnostic cannot consume a reserved slot.
            if (!eu4_lab_1375::permits(acceptance_window, parsed)) { input_fault(fault, "acceptance_window", ERROR_SUCCESS); break; }''')
    replace('static void process_mailbox() {\n', 'static void process_mailbox() {\n    if (acceptance_window.state == eu4_lab_1375::WindowState::awaiting_health) return;\n')
    replace('    char line[1024]{};\n    sprintf_s(line, "{\\"event\\":\\"lab_request_claimed', '    char line[2048]{};\n    sprintf_s(line, "{\\"event\\":\\"lab_request_claimed')
    replace('\\"speed\\":%u,\\"durable_claim\\":true,\\"retry_allowed\\":false}', '\\"speed\\":%u,\\"bound_action\\":\\"%s\\",\\"bound_target\\":\\"%s\\",\\"bound_submit_sequence\\":%llu,\\"claimed_uptime_ms\\":%llu,\\"durable_claim\\":true,\\"retry_allowed\\":false}')
    replace('static_cast<unsigned long long>(operation.request.expires), operation.request.speed);', '''static_cast<unsigned long long>(operation.request.expires), operation.request.speed,
        operation.request.bound_action, operation.request.bound_target, static_cast<unsigned long long>(operation.request.bound_submit_sequence),
        static_cast<unsigned long long>(GetTickCount64()));''')
    replace('    if (!durable_log(line)) return;\n    if (!std::strcmp(operation.request.operation, "speed")', '''    if (!durable_log(line)) return;
    if (!std::strcmp(operation.request.operation, "accept")) { process_acceptance(operation); return; }
    if (!std::strcmp(operation.request.operation, "speed")''')
    replace('    if (!std::strcmp(operation.request.operation, "pair")) {\n        eu4_pair_1375::Request request{};', '''    if (!std::strcmp(operation.request.operation, "pair")) {
        const bool forced_bound = acceptance_window.state == eu4_lab_1375::WindowState::armed;
        if (forced_bound && !eu4_lab_1375::begin_bound_submit(acceptance_window, operation.request)) {
            freeze("acceptance_bound_submit_mismatch"); return;
        }
        eu4_pair_1375::Request request{};''')
    replace('\\"ownership_uncertain\\":%s,\\"session_frozen\\":%s,\\"applied_verified\\":false', '\\"ownership_uncertain\\":%s,\\"session_frozen\\":%s,\\"audit_complete\\":%s,\\"applied_verified\\":false')
    replace('session_frozen ? "true" : "false");\n    } else if (!std::strcmp(operation.request.operation, "fixture"))', '''session_frozen ? "true" : "false", result.audit_complete ? "true" : "false");
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
    } else if (!std::strcmp(operation.request.operation, "fixture"))''')
    replace('    durable_log(line);\n}\n\nextern "C" void research_frame_tick()', '    last_legality.valid = false;\n    durable_log(line);\n}\n\nextern "C" void research_frame_tick()')
    replace('            last_log = now;\n            char line[2048]{};', '''            last_log = now;
            unsigned char flag = 2; // 2 is an explicit invalid/unknown health value, never guessed zero.
            if (!ready || !read_value(observed.game_cookie + 0x23a1, flag) || flag > 1) freeze("acceptance_health_flag_unknown");
            const bool closes_acceptance = acceptance_window.state == eu4_lab_1375::WindowState::awaiting_health
                && flag == 0 && ready && observed.paused && !session_frozen && !world_changed && count > acceptance_window.off_frame;
            char line[3000]{};''')
    replace('\\"lease_deadline_uptime_ms\\":%llu,\\"send_enabled\\":%s}', '\\"lease_deadline_uptime_ms\\":%llu,\\"send_enabled\\":%s,\\"acceptance_flag\\":%u,\\"acceptance_state\\":\\"%s\\",\\"acceptance_origin_sequence\\":%llu,\\"acceptance_submit_sequence\\":%llu,\\"acceptance_off_sequence\\":%llu,\\"acceptance_action\\":\\"%s\\",\\"acceptance_target\\":\\"%s\\"}')
    replace('static_cast<unsigned long long>(lease_deadline), any_dispatch_entered ? "true" : "false");', '''static_cast<unsigned long long>(lease_deadline), any_dispatch_entered ? "true" : "false",
                static_cast<unsigned>(flag), closes_acceptance ? "closed" : acceptance_state_name(), static_cast<unsigned long long>(acceptance_window.on_sequence),
                static_cast<unsigned long long>(acceptance_window.submit_sequence), static_cast<unsigned long long>(acceptance_window.off_sequence),
                acceptance_window.action, acceptance_window.target);''')
    replace('            if (durable_log(line) && ready && !session_frozen) last_health_frame = count;', '''            if (durable_log(line) && ready && !session_frozen) {
                if (closes_acceptance) eu4_lab_1375::observe_closed_boundary(acceptance_window, flag, true, count);
                last_health_frame = count;
            }''')
    replace('        session_frozen = true;\n        if (!audit_failed)', '        session_frozen = true;\n        eu4_lab_1375::fail_window(acceptance_window);\n        if (!audit_failed)')
    return s


if __name__ == "__main__":
    raise SystemExit("Use prepare.py --check or --refresh-candidate; patch helpers cannot write independently")
