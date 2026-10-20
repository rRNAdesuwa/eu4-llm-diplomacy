#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

// Public, pointer-free data contract for the read-only live war-score query.
// The implementation in live-war-score-query.inc keeps native war references,
// country handles, and vtable addresses in private stack state.
namespace bridge::live_war_score_query {

inline constexpr std::size_t kMaxWarIdLength=29;
inline constexpr std::size_t kMaxNativeTooltipBytes=8192;
inline constexpr std::size_t kMaxNativeTooltipHexBytes=
    kMaxNativeTooltipBytes*2+1;
inline constexpr unsigned kMaxParticipants=256;

enum class Mode : std::uint8_t {
    whole_war=0,
    separate=1
};

inline const char* mode_name(Mode mode) noexcept {
    return mode==Mode::whole_war ? "whole_war"
        : mode==Mode::separate ? "separate" : "invalid";
}

inline bool valid_mode(std::uint8_t raw) noexcept {
    return raw<=static_cast<std::uint8_t>(Mode::separate);
}

struct Request {
    const char* war_id=nullptr;
    std::uint64_t actor=0;
    std::uint64_t recipient=0;
    std::uint64_t perspective=0;
    std::uint8_t mode=static_cast<std::uint8_t>(Mode::whole_war);
};

struct Tooltip {
    bool requested=false;
    bool readable=false;
    bool truncated=false;
    std::uint64_t size=0;
    std::uint64_t capacity=0;
    char text_hex[kMaxNativeTooltipHexBytes]{};
};

struct BoundContext {
    // Private-only native state.  Do not serialize these fields.
    std::uintptr_t native_war=0;
    std::uint64_t actor=0;
    std::uint64_t recipient=0;
    std::uint64_t perspective=0;
    std::uint64_t side_anchor=0;
    unsigned char actor_side=0;       // 1=side_a, 2=side_b
    unsigned char recipient_side=0;   // 1=side_a, 2=side_b
    unsigned side_a_count=0;
    unsigned side_b_count=0;
    bool registry_match=false;
    bool pair_reference_verified=false;
    bool participant_lists_complete=false;
    bool actor_handle_verified=false;
    bool recipient_handle_verified=false;
    bool perspective_handle_verified=false;
    bool side_anchor_verified=false;
    bool actor_recipient_opposite=false;
    bool complete=false;
};

struct Result {
    BoundContext context{};
    bool total_called=false;
    bool total_return_verified=false;
    std::int32_t total_raw=0;
    bool total_complete=false;
    bool goal_called=false;
    bool goal_return_verified=false;
    bool goal_presence_readable=false;
    bool goal_present=false;
    bool goal_inapplicable=false;
    bool goal_out_written=false;
    std::int32_t goal_cumulative_raw=0;
    bool goal_complete=false;
    bool max_score_readable=false;
    std::int32_t max_score_raw=0;
    bool overview_goal_cap_readable=false;
    std::int32_t overview_goal_cap_raw=0;
    Tooltip tooltip{};
    bool native_string_destroy_called=false;
    bool complete=false;
    bool verified=false;
    char error_code[48]{};
};

inline void set_error(Result& result,const char* code) noexcept {
    result.error_code[0]=0;
    if (!code) return;
    std::size_t index=0;
    for (;index+1<sizeof(result.error_code) && code[index];++index)
        result.error_code[index]=code[index];
    result.error_code[index]=0;
}

inline bool has_error(const Result& result) noexcept {
    return result.error_code[0]!=0;
}

inline bool result_complete(const Result& result) noexcept {
    return result.complete && result.verified && !has_error(result);
}

} // namespace bridge::live_war_score_query
