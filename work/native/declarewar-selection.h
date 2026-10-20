#pragma once

// Allocation-free validation for the participant lists carried by the
// Declare War EXEC4 wire.  The same fixed record is intentionally reusable by
// later query protocols; this header has no Win32 or game dependency.

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace bridge {

constexpr std::size_t kMaxCountryTags=16;
constexpr std::size_t kCountryTagBytes=4; // three ASCII bytes plus NUL
constexpr std::size_t kMaxCountryTagCsvBytes=
    kMaxCountryTags*3u+(kMaxCountryTags-1u);

struct CountryTagList {
    char tags[kMaxCountryTags][kCountryTagBytes]{};
    std::uint32_t count=0;
};

namespace declarewar_selection {

enum class CsvError : std::uint8_t {
    ok=0,
    null_input,
    empty_input,
    empty_tag,
    too_many_tags,
    invalid_tag,
    duplicate_tag,
    unsorted_tags,
};

struct CsvResult {
    CsvError error=CsvError::empty_input;
    std::size_t index=0;

    constexpr bool ok() const noexcept { return error==CsvError::ok; }
};

enum class ParticipantError : std::uint8_t {
    ok=0,
    invalid_actor,
    invalid_recipient,
    invalid_call_allies,
    invalid_promise_land_to,
    invalid_co_belligerents,
    promise_not_subset,
    participant_lists_overlap,
    actor_in_participant_list,
    recipient_in_participant_list,
};

struct ParticipantResult {
    ParticipantError error=ParticipantError::invalid_call_allies;
    std::size_t index=0;

    constexpr bool ok() const noexcept { return error==ParticipantError::ok; }
};

inline const char* csv_error_name(CsvError error) noexcept {
    switch (error) {
    case CsvError::ok: return "ok";
    case CsvError::null_input: return "null_input";
    case CsvError::empty_input: return "empty_input";
    case CsvError::empty_tag: return "empty_tag";
    case CsvError::too_many_tags: return "too_many_tags";
    case CsvError::invalid_tag: return "invalid_tag";
    case CsvError::duplicate_tag: return "duplicate_tag";
    case CsvError::unsorted_tags: return "unsorted_tags";
    }
    return "unknown";
}

inline const char* participant_error_name(ParticipantError error) noexcept {
    switch (error) {
    case ParticipantError::ok: return "ok";
    case ParticipantError::invalid_actor: return "invalid_actor";
    case ParticipantError::invalid_recipient: return "invalid_recipient";
    case ParticipantError::invalid_call_allies: return "invalid_call_allies";
    case ParticipantError::invalid_promise_land_to: return "invalid_promise_land_to";
    case ParticipantError::invalid_co_belligerents: return "invalid_co_belligerents";
    case ParticipantError::promise_not_subset: return "promise_not_subset";
    case ParticipantError::participant_lists_overlap: return "participant_lists_overlap";
    case ParticipantError::actor_in_participant_list: return "actor_in_participant_list";
    case ParticipantError::recipient_in_participant_list: return "recipient_in_participant_list";
    }
    return "unknown";
}

namespace detail {

inline bool tag_bytes_valid(const char* bytes,std::size_t length) noexcept {
    if (!bytes || length!=3) return false;
    for (std::size_t index=0;index<3;++index) {
        const char value=bytes[index];
        const bool upper=value>='A' && value<='Z';
        const bool digit=value>='0' && value<='9';
        if (!upper && !digit) return false;
    }
    return true;
}

inline int compare_tags(const char* left,const char* right) noexcept {
    return std::memcmp(left,right,3);
}

inline bool list_contains(const CountryTagList& list,const char* tag) noexcept {
    if (!tag) return false;
    for (std::uint32_t index=0;index<list.count;++index)
        if (std::memcmp(list.tags[index],tag,3)==0) return true;
    return false;
}

inline bool list_canonical(const CountryTagList& list) noexcept {
    if (list.count>kMaxCountryTags) return false;
    for (std::uint32_t index=0;index<list.count;++index) {
        if (!tag_bytes_valid(list.tags[index],3)) return false;
        if (index>0 && compare_tags(list.tags[index-1],list.tags[index])>=0)
            return false;
    }
    return true;
}

inline bool bounded_c_string_length(const char* value,std::size_t& length) noexcept {
    if (!value) return false;
    for (std::size_t index=0;index<=kMaxCountryTagCsvBytes;++index) {
        if (value[index]==0) {
            length=index;
            return true;
        }
    }
    return false;
}

inline CsvResult parse_country_tag_csv_bounded(const char* bytes,
    std::size_t length,CountryTagList& output) noexcept {
    output=CountryTagList{};
    if (!bytes) return CsvResult{CsvError::null_input,0};
    if (length==0) return CsvResult{CsvError::empty_input,0};
    if (length>kMaxCountryTagCsvBytes)
        return CsvResult{CsvError::too_many_tags,0};
    if (length==1 && bytes[0]=='-') return CsvResult{CsvError::ok,0};
    if (bytes[0]=='-') return CsvResult{CsvError::invalid_tag,0};

    std::size_t token_start=0;
    std::size_t token_index=0;
    while (token_start<length) {
        std::size_t token_end=token_start;
        while (token_end<length && bytes[token_end]!=',') ++token_end;
        const std::size_t token_length=token_end-token_start;
        if (token_length==0) return CsvResult{CsvError::empty_tag,token_index};
        if (token_index>=kMaxCountryTags)
            return CsvResult{CsvError::too_many_tags,token_index};
        const char* token=bytes+token_start;
        if (!tag_bytes_valid(token,token_length))
            return CsvResult{CsvError::invalid_tag,token_index};
        if (token_index>0) {
            const int order=compare_tags(output.tags[token_index-1],token);
            if (order==0) return CsvResult{CsvError::duplicate_tag,token_index};
            if (order>0) return CsvResult{CsvError::unsorted_tags,token_index};
        }
        std::memcpy(output.tags[token_index],token,3);
        output.tags[token_index][3]=0;
        ++token_index;
        if (token_end==length) break;
        token_start=token_end+1;
        if (token_start==length) return CsvResult{CsvError::empty_tag,token_index};
    }
    output.count=static_cast<std::uint32_t>(token_index);
    return CsvResult{CsvError::ok,0};
}

inline bool valid_endpoint(const char* tag) noexcept {
    return tag_bytes_valid(tag,tag?3u:0u);
}

} // namespace detail

inline CsvResult parse_country_tag_csv(const char* bytes,std::size_t length,
    CountryTagList& output) noexcept {
    return detail::parse_country_tag_csv_bounded(bytes,length,output);
}

// Convenience overload for callers that already hold a NUL-terminated CSV.
// It still uses a fixed upper bound, so a missing NUL cannot cause an
// unbounded read.
inline CsvResult parse_country_tag_csv(const char* bytes,
    CountryTagList& output) noexcept {
    std::size_t length=0;
    if (!detail::bounded_c_string_length(bytes,length))
        return CsvResult{bytes?CsvError::too_many_tags:CsvError::null_input,0};
    return detail::parse_country_tag_csv_bounded(bytes,length,output);
}

inline ParticipantResult validate_participant_selection(
    const CountryTagList& call_allies,
    const CountryTagList& promise_land_to,
    const CountryTagList& co_belligerents,
    const char* actor,const char* recipient) noexcept {
    if (!detail::valid_endpoint(actor))
        return ParticipantResult{ParticipantError::invalid_actor,0};
    if (!detail::valid_endpoint(recipient))
        return ParticipantResult{ParticipantError::invalid_recipient,0};
    if (!detail::list_canonical(call_allies))
        return ParticipantResult{ParticipantError::invalid_call_allies,0};
    if (!detail::list_canonical(promise_land_to))
        return ParticipantResult{ParticipantError::invalid_promise_land_to,0};
    if (!detail::list_canonical(co_belligerents))
        return ParticipantResult{ParticipantError::invalid_co_belligerents,0};
    for (std::uint32_t index=0;index<call_allies.count;++index) {
        const bool is_actor=std::memcmp(call_allies.tags[index],actor,3)==0;
        const bool is_recipient=std::memcmp(call_allies.tags[index],recipient,3)==0;
        if (is_actor || is_recipient)
            return ParticipantResult{is_actor
                ?ParticipantError::actor_in_participant_list
                :ParticipantError::recipient_in_participant_list,index};
    }
    for (std::uint32_t index=0;index<promise_land_to.count;++index) {
        const bool is_actor=std::memcmp(promise_land_to.tags[index],actor,3)==0;
        const bool is_recipient=std::memcmp(promise_land_to.tags[index],recipient,3)==0;
        if (is_actor || is_recipient)
            return ParticipantResult{is_actor
                ?ParticipantError::actor_in_participant_list
                :ParticipantError::recipient_in_participant_list,index};
        if (!detail::list_contains(call_allies,promise_land_to.tags[index]))
            return ParticipantResult{ParticipantError::promise_not_subset,index};
    }
    for (std::uint32_t index=0;index<co_belligerents.count;++index) {
        const bool is_actor=std::memcmp(co_belligerents.tags[index],actor,3)==0;
        const bool is_recipient=std::memcmp(co_belligerents.tags[index],recipient,3)==0;
        if (is_actor || is_recipient)
            return ParticipantResult{is_actor
                ?ParticipantError::actor_in_participant_list
                :ParticipantError::recipient_in_participant_list,index};
        if (detail::list_contains(call_allies,co_belligerents.tags[index]))
            return ParticipantResult{ParticipantError::participant_lists_overlap,index};
    }
    return ParticipantResult{ParticipantError::ok,0};
}

// Alternate argument order is useful at the observer boundary and keeps the
// contract explicit for callers that start with the two diplomatic parties.
inline ParticipantResult validate_participant_selection(
    const char* actor,const char* recipient,
    const CountryTagList& call_allies,
    const CountryTagList& promise_land_to,
    const CountryTagList& co_belligerents) noexcept {
    return validate_participant_selection(call_allies,promise_land_to,
        co_belligerents,actor,recipient);
}

} // namespace declarewar_selection
} // namespace bridge

