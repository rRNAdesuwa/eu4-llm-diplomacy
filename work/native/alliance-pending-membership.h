#pragma once

// Bounded, side-effect-free traversal of the native pending-list shape.
//
// The caller supplies a reader for one uintptr_t field.  A result of absent
// is emitted only after the complete counted list and both links have been
// read successfully.  This helper deliberately does not inspect action
// payloads, tombstones, or an external record.active bit.

#include <cstdint>
#include <limits>

namespace bridge::alliance_pending_membership {

enum class Result : std::uint8_t {
    unknown=0,
    present,
    absent,
};

constexpr std::uintptr_t kCloneOffset=0x00;
constexpr std::uintptr_t kPreviousOffset=0x08;
constexpr std::uintptr_t kNextOffset=0x10;

namespace detail {

template <typename Reader>
bool read_field(Reader& reader,std::uintptr_t base,std::uintptr_t offset,
    std::uintptr_t& value) noexcept {
    constexpr std::uintptr_t maximum=std::numeric_limits<std::uintptr_t>::max();
    if (base>maximum-offset) return false;
    return static_cast<bool>(reader(base+offset,value));
}

} // namespace detail

// `count` is the native list count and `max_count` is the caller's hard
// observation bound.  Node layout is {clone,+0x08 previous,+0x10 next}.
// expected_node/expected_clone must identify the captured native objects for
// a non-empty list; zero identities produce unknown rather than a false
// absence claim.
template <typename Reader>
Result inspect(std::uintptr_t head,std::uintptr_t tail,std::uint32_t count,
    std::uintptr_t expected_node,std::uintptr_t expected_clone,
    std::uint32_t max_count,Reader&& reader) noexcept {
    if (count>max_count) return Result::unknown;

    if (count==0)
        return (head==0 && tail==0) ? Result::absent : Result::unknown;

    if (head==0 || tail==0 || expected_node==0 || expected_clone==0)
        return Result::unknown;

    std::uintptr_t node=head;
    std::uintptr_t previous_node=0;
    bool found=false;

    for (std::uint32_t index=0;index<count;++index) {
        if (node==0) return Result::unknown;

        std::uintptr_t clone=0;
        std::uintptr_t previous=0;
        std::uintptr_t next=0;
        if (!detail::read_field(reader,node,kCloneOffset,clone)
            || !detail::read_field(reader,node,kPreviousOffset,previous)
            || !detail::read_field(reader,node,kNextOffset,next)) {
            return Result::unknown;
        }

        if ((index==0 && previous!=0)
            || (index!=0 && previous!=previous_node)) {
            return Result::unknown;
        }

        if (node==expected_node || clone==expected_clone) found=true;
        previous_node=node;
        node=next;
    }

    // A valid counted list must terminate exactly after count nodes and the
    // final node must be the advertised tail.  This also rejects cycles and
    // chains longer than the bound.
    if (node!=0 || previous_node!=tail) return Result::unknown;
    return found ? Result::present : Result::absent;
}

} // namespace bridge::alliance_pending_membership
