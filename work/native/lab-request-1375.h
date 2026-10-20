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
};
inline int render_request(const MailboxRequest& r, char* output, std::size_t capacity) {
    return std::snprintf(output, capacity,
        "EU4LAB/1\npid=%u\ncreation=%016llx\nsequence=%llu\nexpires=%llu\noperation=%s\nmode=%s\naction=%s\nactor=%s\ntarget=%s\nspeed=%u\n",
        r.pid, static_cast<unsigned long long>(r.creation), static_cast<unsigned long long>(r.sequence),
        static_cast<unsigned long long>(r.expires), r.operation, r.mode, r.action, r.actor, r.target, r.speed);
}
inline bool known_tag(const char* text) { return !std::strcmp(text, "FRA") || !std::strcmp(text, "ENG") || !std::strcmp(text, "POR"); }
inline bool parse_request(const char* data, std::size_t length, MailboxRequest& r) {
    if (data == nullptr || length == 0 || length > kMaxRequestBytes) return false;
    char input[kMaxRequestBytes + 1]{};
    for (std::size_t i = 0; i < length; ++i) if ((data[i] < 0x20 || data[i] > 0x7e) && data[i] != '\n') return false;
    std::memcpy(input, data, length);
    unsigned long long creation = 0, sequence = 0, expires = 0;
    const int fields = sscanf_s(input,
        "EU4LAB/1\npid=%u\ncreation=%16llx\nsequence=%20llu\nexpires=%20llu\noperation=%7[a-z_]\nmode=%19[a-z_]\naction=%31[a-z_]\nactor=%3[A-Z]\ntarget=%3[A-Z]\nspeed=%1u\n",
        &r.pid, &creation, &sequence, &expires, r.operation, static_cast<unsigned>(sizeof(r.operation)),
        r.mode, static_cast<unsigned>(sizeof(r.mode)), r.action, static_cast<unsigned>(sizeof(r.action)),
        r.actor, static_cast<unsigned>(sizeof(r.actor)), r.target, static_cast<unsigned>(sizeof(r.target)), &r.speed);
    if (fields != 10) return false;
    r.creation = creation; r.sequence = sequence; r.expires = expires;
    if (!r.pid || !r.creation || !r.sequence || r.sequence > kMaxSequence || !r.expires) return false;
    if (!std::strcmp(r.operation, "pair")) {
        eu4_pair_1375::ActionId action{};
        if (!eu4_pair_1375::parse_action_id(r.action, std::strlen(r.action), &action) || !known_tag(r.actor) || !known_tag(r.target)
            || !std::strcmp(r.actor, r.target) || (std::strcmp(r.mode, "legality_only") && std::strcmp(r.mode, "submit")) || r.speed != 0) return false;
    } else if (!std::strcmp(r.operation, "speed")) {
        if (std::strcmp(r.mode, "submit") || std::strcmp(r.action, "none") || std::strcmp(r.actor, "FRA")
            || std::strcmp(r.target, "FRA") || r.speed > 5) return false;
    } else return false;
    char canonical[kMaxRequestBytes + 1]{};
    const int written = render_request(r, canonical, sizeof(canonical));
    return written > 0 && static_cast<std::size_t>(written) == length && !std::memcmp(data, canonical, length);
}
} // namespace eu4_lab_1375
