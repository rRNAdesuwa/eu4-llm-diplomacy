#pragma once
#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <cstring>
#include "pair-engine-1375.h"

// Canonical ASCII transport for a private research lab, not production API.
// The fixed key order and round-trip check reject duplicates, extra keys,
// whitespace variations, embedded NULs, escapes, arbitrary paths and scripts.
namespace eu4_lab_1375 {
constexpr std::size_t kMaxRequestBytes = 1024;
constexpr std::uint64_t kMaxSequence = 0x7fffffffffffffffULL;
constexpr std::uint64_t kMaxTtlMs = 60000;
struct MailboxRequest {
    std::uint32_t pid;
    std::uint64_t creation, sequence, expires;
    char operation[8], mode[20], action[32], actor[4], target[4];
    unsigned speed;
    char bound_action[32], bound_target[5];
    std::uint64_t bound_submit_sequence;
};
inline int render_request(const MailboxRequest& r, char* output, std::size_t capacity) {
    return std::snprintf(output, capacity,
        "EU4LAB/3\npid=%u\ncreation=%016llx\nsequence=%llu\nexpires=%llu\noperation=%s\nmode=%s\naction=%s\nactor=%s\ntarget=%s\nspeed=%u\nbound_action=%s\nbound_target=%s\nbound_submit_sequence=%llu\n",
        r.pid, static_cast<unsigned long long>(r.creation), static_cast<unsigned long long>(r.sequence),
        static_cast<unsigned long long>(r.expires), r.operation, r.mode, r.action, r.actor, r.target, r.speed, r.bound_action, r.bound_target,
        static_cast<unsigned long long>(r.bound_submit_sequence));
}
inline bool known_tag(const char* text) { return !std::strcmp(text, "FRA") || !std::strcmp(text, "ENG") || !std::strcmp(text, "POR") || !std::strcmp(text, "NAV") || !std::strcmp(text, "FOI"); }
inline bool parse_request(const char* data, std::size_t length, MailboxRequest& r) {
    if (data == nullptr || length == 0 || length > kMaxRequestBytes) return false;
    char input[kMaxRequestBytes + 1]{};
    for (std::size_t i = 0; i < length; ++i) if ((data[i] < 0x20 || data[i] > 0x7e) && data[i] != '\n') return false;
    std::memcpy(input, data, length);
    unsigned long long creation = 0, sequence = 0, expires = 0, bound_sequence = 0;
    const int fields = sscanf_s(input,
        "EU4LAB/3\npid=%u\ncreation=%16llx\nsequence=%20llu\nexpires=%20llu\noperation=%7[a-z_]\nmode=%19[a-z_]\naction=%31[a-z_]\nactor=%3[A-Z]\ntarget=%3[A-Z]\nspeed=%1u\nbound_action=%31[a-z_]\nbound_target=%4[A-Za-z]\nbound_submit_sequence=%20llu\n",
        &r.pid, &creation, &sequence, &expires, r.operation, static_cast<unsigned>(sizeof(r.operation)),
        r.mode, static_cast<unsigned>(sizeof(r.mode)), r.action, static_cast<unsigned>(sizeof(r.action)),
        r.actor, static_cast<unsigned>(sizeof(r.actor)), r.target, static_cast<unsigned>(sizeof(r.target)), &r.speed,
        r.bound_action, static_cast<unsigned>(sizeof(r.bound_action)), r.bound_target, static_cast<unsigned>(sizeof(r.bound_target)), &bound_sequence);
    if (fields != 13) return false;
    r.creation = creation; r.sequence = sequence; r.expires = expires; r.bound_submit_sequence = bound_sequence;
    if (!r.pid || !r.creation || !r.sequence || r.sequence > kMaxSequence || !r.expires) return false;
    if (!std::strcmp(r.operation, "pair")) {
        eu4_pair_1375::ActionId action{};
        if (!eu4_pair_1375::parse_action_id(r.action, std::strlen(r.action), &action) || !known_tag(r.actor) || !known_tag(r.target)
            || !std::strcmp(r.actor, r.target) || (std::strcmp(r.mode, "legality_only") && std::strcmp(r.mode, "submit")) || r.speed != 0) return false;
    } else if (!std::strcmp(r.operation, "speed")) {
        if (std::strcmp(r.mode, "submit") || std::strcmp(r.action, "none") || std::strcmp(r.actor, "FRA")
            || std::strcmp(r.target, "FRA") || r.speed > 5) return false;
    } else if (!std::strcmp(r.operation, "fixture")) {
        if (std::strcmp(r.mode, "submit") || (std::strcmp(r.action, "fixture_on") && std::strcmp(r.action, "fixture_off"))
            || std::strcmp(r.actor, "FRA") || std::strcmp(r.target, "FRA") || r.speed != 0) return false;
    } else if (!std::strcmp(r.operation, "accept")) {
        eu4_pair_1375::ActionId bound{};
        const bool on = !std::strcmp(r.action, "accept_on");
        const bool off = !std::strcmp(r.action, "accept_off");
        if ((!on && !off) || std::strcmp(r.mode, "submit") || std::strcmp(r.actor, "FRA")
            || std::strcmp(r.target, "FRA") || r.speed != 0
            || !eu4_pair_1375::parse_action_id(r.bound_action, std::strlen(r.bound_action), &bound)
            || !known_tag(r.bound_target) || !std::strcmp(r.bound_target, "FRA")) return false;
        if (on && (r.sequence > kMaxSequence - 2 || r.bound_submit_sequence != r.sequence + 1)) return false;
        if (off && (r.sequence < 3 || r.bound_submit_sequence != r.sequence - 1)) return false;
    } else return false;
    if (std::strcmp(r.operation, "accept") && (std::strcmp(r.bound_action, "none")
        || std::strcmp(r.bound_target, "none") || r.bound_submit_sequence != 0)) return false;
    char canonical[kMaxRequestBytes + 1]{};
    const int written = render_request(r, canonical, sizeof(canonical));
    return written > 0 && static_cast<std::size_t>(written) == length && !std::memcmp(data, canonical, length);
}
// Portable transition helper used by the real host; no callback or allocation.
// A pending binding is retained through all failures. Only fresh healthy flag0
// AFTER a successful off can close it. Native claim prechecks use permits().
enum class WindowState : unsigned { closed, pending_on, armed, pending_submit, submitted_known, pending_off, awaiting_health, unknown };
struct AcceptanceWindow {
    WindowState state = WindowState::closed;
    std::uint64_t on_sequence = 0, submit_sequence = 0, off_sequence = 0;
    char action[32] = "none", target[5] = "none";
    std::uint64_t world = 0, player = 0;
    std::int32_t date = 0;
    std::uint32_t thread = 0;
    long off_frame = 0;
};
inline bool same_binding(const AcceptanceWindow& w, const MailboxRequest& r) {
    return !std::strcmp(w.action, r.bound_action) && !std::strcmp(w.target, r.bound_target)
        && w.submit_sequence == r.bound_submit_sequence;
}
inline bool bound_submit(const AcceptanceWindow& w, const MailboxRequest& r) {
    return !std::strcmp(r.operation, "pair") && !std::strcmp(r.mode, "submit")
        && !std::strcmp(r.actor, "FRA") && !std::strcmp(r.action, w.action)
        && !std::strcmp(r.target, w.target) && r.sequence == w.submit_sequence;
}
inline bool permits(const AcceptanceWindow& w, const MailboxRequest& r) {
    if (w.state == WindowState::closed) return true;
    if (w.state == WindowState::armed) return bound_submit(w, r);
    return w.state == WindowState::submitted_known && !std::strcmp(r.operation, "accept")
        && !std::strcmp(r.action, "accept_off") && r.sequence == w.off_sequence && same_binding(w, r);
}
inline bool reserve_on(AcceptanceWindow& w, const MailboxRequest& r, unsigned flag,
                       bool fresh_legality, std::uint64_t world, std::uint64_t player,
                       std::int32_t date, std::uint32_t thread) {
    if (w.state != WindowState::closed || flag != 0 || !fresh_legality
        || std::strcmp(r.operation, "accept") || std::strcmp(r.action, "accept_on")
        || r.sequence > kMaxSequence - 2 || r.bound_submit_sequence != r.sequence + 1) return false;
    w.state = WindowState::pending_on; // Retain before any durable callback attempt.
    w.on_sequence = r.sequence; w.submit_sequence = r.sequence + 1; w.off_sequence = r.sequence + 2;
    std::memcpy(w.action, r.bound_action, sizeof(w.action)); std::memcpy(w.target, r.bound_target, sizeof(w.target));
    w.world = world; w.player = player; w.date = date; w.thread = thread;
    return true;
}
inline bool begin_bound_submit(AcceptanceWindow& w, const MailboxRequest& r) {
    if (w.state != WindowState::armed || !bound_submit(w,r)) return false;
    w.state = WindowState::pending_submit; return true;
}
inline bool begin_bound_off(AcceptanceWindow& w, const MailboxRequest& r) {
    if (!permits(w,r) || w.state != WindowState::submitted_known) return false;
    w.state = WindowState::pending_off; return true;
}
inline void fail_window(AcceptanceWindow& w) {
    if (w.state != WindowState::closed) w.state = WindowState::unknown;
}
inline bool observe_closed_boundary(AcceptanceWindow& w, unsigned flag, bool healthy_paused, long frame) {
    if (w.state != WindowState::awaiting_health || flag != 0 || !healthy_paused || frame <= w.off_frame) return false;
    w.state = WindowState::closed; // Historical binding fields remain for audit.
    return true;
}
} // namespace eu4_lab_1375
