#pragma once

// Bounded frame-thread request protocol for inspecting and answering a native
// inbound Alliance, Royal, Support Independence, Military Access,
// Vassalization, or favor-for-resource proposal.
// The wire carries an opaque session-local native
// proposal number; it never carries an address or a decision-country object.

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>

namespace bridge::alliance_inbound_response_wire {

constexpr std::size_t kMaxIdentifierLength=64;
constexpr std::size_t kMaxSessionIdLength=27;
constexpr std::size_t kMaxWireBytes=320;
constexpr std::uint64_t kFiletimeTicksPerSecond=10000000u;
constexpr std::uint64_t kMaxExpiryWindowFiletime=10u*kFiletimeTicksPerSecond;

enum class ParseError : std::uint8_t {
    ok=0,
    null_input,
    empty_input,
    wire_too_long,
    missing_final_lf,
    crlf_rejected,
    embedded_nul,
    embedded_newline,
    embedded_carriage_return,
    non_ascii,
    field_count,
    empty_field,
    invalid_version,
    invalid_identifier,
    invalid_session_id,
    invalid_expiry,
    invalid_date,
    invalid_action,
    invalid_actor,
    invalid_decision_country,
    invalid_decision,
    invalid_native_proposal_id,
};

struct ParseResult {
    ParseError error=ParseError::invalid_version;
    std::size_t field=0;
    constexpr bool ok() const noexcept { return error==ParseError::ok; }
};

enum class ContextError : std::uint8_t {
    ok=0,
    expected_session_missing,
    session_mismatch,
    expired,
    expiry_window_exceeded,
    date_mismatch,
};

struct ContextResult {
    ContextError error=ContextError::session_mismatch;
    constexpr bool ok() const noexcept { return error==ContextError::ok; }
};

struct InspectionRequest {
    char query_id[kMaxIdentifierLength+1]{};
    char session_id[kMaxSessionIdLength+1]{};
    char action_id[24]{};
    char original_actor[4]{};
    char decision_country[4]{};
    char decision[7]{};
    std::uint32_t session_pid=0;
    std::uint64_t session_creation_filetime=0;
    std::uint64_t expires_filetime=0;
    std::int32_t date_raw=0;
    std::uint64_t native_proposal_id=0;
};

struct ResponseRequest {
    char request_id[kMaxIdentifierLength+1]{};
    char session_id[kMaxSessionIdLength+1]{};
    char action_id[24]{};
    char original_actor[4]{};
    char decision_country[4]{};
    char decision[7]{};
    std::uint32_t session_pid=0;
    std::uint64_t session_creation_filetime=0;
    std::uint64_t expires_filetime=0;
    std::int32_t date_raw=0;
    std::uint64_t native_proposal_id=0;
};

inline const char* parse_error_name(ParseError error) noexcept {
    switch (error) {
    case ParseError::ok: return "ok";
    case ParseError::null_input: return "null_input";
    case ParseError::empty_input: return "empty_input";
    case ParseError::wire_too_long: return "wire_too_long";
    case ParseError::missing_final_lf: return "missing_final_lf";
    case ParseError::crlf_rejected: return "crlf_rejected";
    case ParseError::embedded_nul: return "embedded_nul";
    case ParseError::embedded_newline: return "embedded_newline";
    case ParseError::embedded_carriage_return: return "embedded_carriage_return";
    case ParseError::non_ascii: return "non_ascii";
    case ParseError::field_count: return "field_count";
    case ParseError::empty_field: return "empty_field";
    case ParseError::invalid_version: return "invalid_version";
    case ParseError::invalid_identifier: return "invalid_identifier";
    case ParseError::invalid_session_id: return "invalid_session_id";
    case ParseError::invalid_expiry: return "invalid_expiry";
    case ParseError::invalid_date: return "invalid_date";
    case ParseError::invalid_action: return "invalid_action";
    case ParseError::invalid_actor: return "invalid_actor";
    case ParseError::invalid_decision_country: return "invalid_decision_country";
    case ParseError::invalid_decision: return "invalid_decision";
    case ParseError::invalid_native_proposal_id: return "invalid_native_proposal_id";
    }
    return "unknown";
}

inline const char* context_error_name(ContextError error) noexcept {
    switch (error) {
    case ContextError::ok: return "ok";
    case ContextError::expected_session_missing: return "expected_session_missing";
    case ContextError::session_mismatch: return "session_mismatch";
    case ContextError::expired: return "expired";
    case ContextError::expiry_window_exceeded: return "expiry_window_exceeded";
    case ContextError::date_mismatch: return "date_mismatch";
    }
    return "unknown";
}

namespace detail {

struct Field { const char* data=nullptr; std::size_t size=0; };

inline bool equals(Field field,const char* literal) noexcept {
    if (!literal) return false;
    std::size_t length=0;
    while (literal[length]!=0) ++length;
    return field.size==length
        && (length==0 || std::memcmp(field.data,literal,length)==0);
}

inline bool copy_field(char* destination,std::size_t capacity,Field field) noexcept {
    if (!destination || field.size+1>capacity) return false;
    if (field.size) std::memcpy(destination,field.data,field.size);
    destination[field.size]=0;
    return true;
}

inline bool decimal_digit(char value) noexcept {
    return value>='0' && value<='9';
}

inline bool parse_unsigned(Field field,std::uint64_t maximum,
    std::uint64_t& result) noexcept {
    if (!field.data || field.size==0) return false;
    std::uint64_t value=0;
    for (std::size_t index=0;index<field.size;++index) {
        if (!decimal_digit(field.data[index])) return false;
        const std::uint64_t digit=static_cast<std::uint64_t>(field.data[index]-'0');
        if (value>(maximum-digit)/10u) return false;
        value=value*10u+digit;
    }
    result=value;
    return true;
}

inline bool parse_signed(Field field,std::int32_t& result) noexcept {
    if (!field.data || field.size==0) return false;
    const bool negative=field.data[0]=='-';
    const std::size_t offset=negative?1:0;
    if (offset==field.size) return false;
    const std::uint64_t maximum=negative?2147483648ull:2147483647ull;
    std::uint64_t value=0;
    if (!parse_unsigned(Field{field.data+offset,field.size-offset},maximum,value)) return false;
    if (negative) {
        result=value==2147483648ull?static_cast<std::int32_t>(-2147483647-1)
            :-static_cast<std::int32_t>(value);
    } else result=static_cast<std::int32_t>(value);
    return true;
}

inline bool hex_digit(char value,std::uint8_t& digit) noexcept {
    if (value>='0' && value<='9') { digit=static_cast<std::uint8_t>(value-'0'); return true; }
    if (value>='a' && value<='f') { digit=static_cast<std::uint8_t>(value-'a'+10); return true; }
    if (value>='A' && value<='F') { digit=static_cast<std::uint8_t>(value-'A'+10); return true; }
    return false;
}

inline bool parse_session(Field field,std::uint32_t& pid,
    std::uint64_t& creation) noexcept {
    if (!field.data || field.size<3 || field.size>kMaxSessionIdLength) return false;
    std::size_t dash=field.size;
    for (std::size_t index=0;index<field.size;++index) {
        if (field.data[index]!='-') continue;
        if (dash!=field.size) return false;
        dash=index;
    }
    if (dash==0 || dash+1>=field.size || dash>10 || field.size-dash-1>16) return false;
    std::uint64_t parsed_pid=0;
    if (!parse_unsigned(Field{field.data,dash},std::numeric_limits<std::uint32_t>::max(),parsed_pid)
        || parsed_pid==0) return false;
    std::uint64_t parsed_creation=0;
    for (std::size_t index=dash+1;index<field.size;++index) {
        std::uint8_t digit=0;
        if (!hex_digit(field.data[index],digit)
            || parsed_creation>(std::numeric_limits<std::uint64_t>::max()-digit)/16u) return false;
        parsed_creation=parsed_creation*16u+digit;
    }
    if (parsed_creation==0) return false;
    pid=static_cast<std::uint32_t>(parsed_pid);
    creation=parsed_creation;
    return true;
}

inline bool valid_identifier(Field field) noexcept {
    if (!field.data || field.size==0 || field.size>kMaxIdentifierLength) return false;
    for (std::size_t index=0;index<field.size;++index) {
        const char value=field.data[index];
        const bool alpha_numeric=(value>='A' && value<='Z')
            || (value>='a' && value<='z') || (value>='0' && value<='9');
        if (!alpha_numeric && value!='_' && value!='-') return false;
    }
    return true;
}

inline bool valid_country(Field field) noexcept {
    if (!field.data || field.size!=3) return false;
    for (std::size_t index=0;index<3;++index)
        if (field.data[index]<'A' || field.data[index]>'Z') return false;
    return true;
}

inline bool exact_session(const char* actual,const char* expected) noexcept {
    if (!actual || !expected) return false;
    for (std::size_t index=0;index<=kMaxSessionIdLength;++index) {
        if (actual[index]!=expected[index]) return false;
        if (expected[index]==0) return true;
    }
    return false;
}

inline ParseResult split(const char* bytes,std::size_t length,Field (&fields)[10]) noexcept {
    if (!bytes) return ParseResult{ParseError::null_input,0};
    if (length==0) return ParseResult{ParseError::empty_input,0};
    if (length>kMaxWireBytes) return ParseResult{ParseError::wire_too_long,0};
    if (bytes[length-1]!='\n') return ParseResult{ParseError::missing_final_lf,0};
    if (length>=2 && bytes[length-2]=='\r') return ParseResult{ParseError::crlf_rejected,0};
    const std::size_t content_length=length-1;
    for (std::size_t index=0;index<content_length;++index) {
        const unsigned char value=static_cast<unsigned char>(bytes[index]);
        if (value==0) return ParseResult{ParseError::embedded_nul,0};
        if (value=='\n') return ParseResult{ParseError::embedded_newline,0};
        if (value=='\r') return ParseResult{ParseError::embedded_carriage_return,0};
        if (value>=0x80u) return ParseResult{ParseError::non_ascii,0};
    }
    std::size_t count=1;
    fields[0].data=bytes;
    for (std::size_t index=0;index<content_length;++index) {
        if (bytes[index]!='|') continue;
        if (count>=10) return ParseResult{ParseError::field_count,count};
        fields[count-1].size=bytes+index-fields[count-1].data;
        fields[count].data=bytes+index+1;
        ++count;
    }
    fields[count-1].size=bytes+content_length-fields[count-1].data;
    if (count!=10) return ParseResult{ParseError::field_count,count};
    for (std::size_t index=0;index<10;++index)
        if (fields[index].size==0) return ParseResult{ParseError::empty_field,index};
    return ParseResult{ParseError::ok,0};
}

struct ParsedFields {
    char id[kMaxIdentifierLength+1]{};
    char session[kMaxSessionIdLength+1]{};
    char action[24]{};
    char actor[4]{};
    char country[4]{};
    char decision[7]{};
    std::uint32_t pid=0;
    std::uint64_t creation=0;
    std::uint64_t expiry=0;
    std::int32_t date=0;
    std::uint64_t proposal=0;
};

inline ParseResult parse_fields(const char* bytes,std::size_t length,
    ParsedFields& output) noexcept {
    output=ParsedFields{};
    Field fields[10]{};
    ParseResult split_result=split(bytes,length,fields);
    if (!split_result.ok()) return split_result;
    if (!equals(fields[0],"v1")) return ParseResult{ParseError::invalid_version,0};
    if (!valid_identifier(fields[1]) || !copy_field(output.id,sizeof(output.id),fields[1]))
        return ParseResult{ParseError::invalid_identifier,1};
    if (!parse_session(fields[2],output.pid,output.creation)
        || !copy_field(output.session,sizeof(output.session),fields[2]))
        return ParseResult{ParseError::invalid_session_id,2};
    if (!parse_unsigned(fields[3],std::numeric_limits<std::uint64_t>::max(),output.expiry))
        return ParseResult{ParseError::invalid_expiry,3};
    if (!parse_signed(fields[4],output.date)) return ParseResult{ParseError::invalid_date,4};
    if (!equals(fields[5],"offer_alliance")
        && !equals(fields[5],"offer_royal_marriage")
        && !equals(fields[5],"support_independence")
        && !equals(fields[5],"ask_military_access")
        && !equals(fields[5],"offer_vassalization")
        && !equals(fields[5],"trade_favors_for_gold")
        && !equals(fields[5],"trade_favors_for_trust")
        && !equals(fields[5],"trade_favors_for_men")
        && !equals(fields[5],"peace_offer"))
        return ParseResult{ParseError::invalid_action,5};
    if (!copy_field(output.action,sizeof(output.action),fields[5])) return ParseResult{ParseError::invalid_action,5};
    if (!valid_country(fields[6]) || !copy_field(output.actor,sizeof(output.actor),fields[6]))
        return ParseResult{ParseError::invalid_actor,6};
    if (!equals(fields[7],"FRA") || !copy_field(output.country,sizeof(output.country),fields[7]))
        return ParseResult{ParseError::invalid_decision_country,7};
    if ((!equals(fields[8],"accept") && !equals(fields[8],"reject"))
        || !copy_field(output.decision,sizeof(output.decision),fields[8]))
        return ParseResult{ParseError::invalid_decision,8};
    if (!parse_unsigned(fields[9],std::numeric_limits<std::uint64_t>::max(),output.proposal)
        || output.proposal==0) return ParseResult{ParseError::invalid_native_proposal_id,9};
    return ParseResult{ParseError::ok,0};
}

template<typename Request>
inline ContextResult validate_context_impl(const Request& request,
    const char* expected_session_id,std::uint64_t current_filetime,
    std::int32_t current_date) noexcept {
    if (!expected_session_id || expected_session_id[0]==0)
        return ContextResult{ContextError::expected_session_missing};
    if (!exact_session(request.session_id,expected_session_id))
        return ContextResult{ContextError::session_mismatch};
    if (request.expires_filetime<=current_filetime)
        return ContextResult{ContextError::expired};
    if (request.expires_filetime-current_filetime>kMaxExpiryWindowFiletime)
        return ContextResult{ContextError::expiry_window_exceeded};
    if (request.date_raw!=current_date)
        return ContextResult{ContextError::date_mismatch};
    return ContextResult{ContextError::ok};
}

} // namespace detail

inline ParseResult parse_inspection_request(const char* bytes,std::size_t length,
    InspectionRequest& output) noexcept {
    output=InspectionRequest{};
    detail::ParsedFields parsed{};
    ParseResult result=detail::parse_fields(bytes,length,parsed);
    if (!result.ok()) return result;
    std::strcpy(output.query_id,parsed.id);
    std::strcpy(output.session_id,parsed.session);
    std::strcpy(output.action_id,parsed.action);
    std::strcpy(output.original_actor,parsed.actor);
    std::strcpy(output.decision_country,parsed.country);
    std::strcpy(output.decision,parsed.decision);
    output.session_pid=parsed.pid;
    output.session_creation_filetime=parsed.creation;
    output.expires_filetime=parsed.expiry;
    output.date_raw=parsed.date;
    output.native_proposal_id=parsed.proposal;
    return result;
}

inline ParseResult parse_response_request(const char* bytes,std::size_t length,
    ResponseRequest& output) noexcept {
    output=ResponseRequest{};
    detail::ParsedFields parsed{};
    ParseResult result=detail::parse_fields(bytes,length,parsed);
    if (!result.ok()) return result;
    std::strcpy(output.request_id,parsed.id);
    std::strcpy(output.session_id,parsed.session);
    std::strcpy(output.action_id,parsed.action);
    std::strcpy(output.original_actor,parsed.actor);
    std::strcpy(output.decision_country,parsed.country);
    std::strcpy(output.decision,parsed.decision);
    output.session_pid=parsed.pid;
    output.session_creation_filetime=parsed.creation;
    output.expires_filetime=parsed.expiry;
    output.date_raw=parsed.date;
    output.native_proposal_id=parsed.proposal;
    return result;
}

inline ContextResult validate_context(const InspectionRequest& request,
    const char* expected_session_id,std::uint64_t current_filetime,
    std::int32_t current_date) noexcept {
    return detail::validate_context_impl(request,expected_session_id,current_filetime,current_date);
}

inline ContextResult validate_context(const ResponseRequest& request,
    const char* expected_session_id,std::uint64_t current_filetime,
    std::int32_t current_date) noexcept {
    return detail::validate_context_impl(request,expected_session_id,current_filetime,current_date);
}

} // namespace bridge::alliance_inbound_response_wire
