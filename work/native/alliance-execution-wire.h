#pragma once

// Bounded parser for the native alliance, royal-marriage, military-access,
// vassalization, insult, and one-sided diplomatic execution request channel.  Existing
// actions use v1; insult actions use v2 with one appended signed parameter;
// Declare War uses the explicitly versioned v3 record with its bounded war
// goal fields.  The v3 record intentionally has no call-allies field yet.
//
// The parser is deliberately independent from Win32 and the game.  Callers
// pass an explicit byte length so an embedded NUL cannot be hidden by a C
// string terminator.  Successful output contains only fixed-capacity fields.

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>

namespace bridge::alliance_execution_wire {

constexpr std::size_t kMaxRequestIdLength=64;
constexpr std::size_t kMaxSessionIdLength=27; // ten decimal PID digits, '-', sixteen hex digits
// v3 carries a 128-byte casus-belli key in addition to the existing context.
// Keep the line bound comfortably above the exact maximum while retaining a
// fixed-size native read buffer.
constexpr std::size_t kMaxWireBytes=512;
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
    field_count,
    empty_field,
    invalid_version,
    invalid_request_id,
    invalid_session_id,
    invalid_expiry,
    invalid_date,
    invalid_action,
    invalid_actor,
    invalid_recipient,
    invalid_phase,
    invalid_insult_id,
    invalid_casus_belli,
    invalid_war_goal_province,
    invalid_war_goal_beneficiary,
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

// All strings include a terminating NUL and are bounded by their named
// capacity.  actor/action/phase are fixed by the protocol and are retained in
// the output so native callers can log or dispatch without reparsing.
struct ExecutionRequest {
    char request_id[kMaxRequestIdLength+1]{};
    char session_id[kMaxSessionIdLength+1]{};
    // revoke_support_independence is 27 characters, so retain its NUL too.
    // This keeps the fixed wire record allocation-free while accommodating
    // every currently supported action identifier.
    char action_id[28]{};
    char actor[4]{};      // "FRA" + NUL
    char recipient[4]{};  // three uppercase ASCII letters + NUL
    char phase[9]{};      // "initiate" + NUL
    std::uint32_t session_pid=0;
    std::uint64_t session_creation_filetime=0;
    std::uint64_t expires_filetime=0;
    std::int32_t date_raw=0;
    // v2 is reserved for insult actions.  Ordinary insults use -1;
    // scornful insults use a nonnegative signed int32 identifier.
    std::int32_t insult_id=-1;
    // v3 Declare War fields.  call_allies is intentionally absent from the
    // current wire contract and is therefore fixed to the empty protocol
    // state until a bounded representation is specified.
    char casus_belli[129]{};
    std::int32_t war_goal_province=-1;
    char war_goal_beneficiary[4]{};
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
    case ParseError::field_count: return "field_count";
    case ParseError::empty_field: return "empty_field";
    case ParseError::invalid_version: return "invalid_version";
    case ParseError::invalid_request_id: return "invalid_request_id";
    case ParseError::invalid_session_id: return "invalid_session_id";
    case ParseError::invalid_expiry: return "invalid_expiry";
    case ParseError::invalid_date: return "invalid_date";
    case ParseError::invalid_action: return "invalid_action";
    case ParseError::invalid_actor: return "invalid_actor";
    case ParseError::invalid_recipient: return "invalid_recipient";
    case ParseError::invalid_phase: return "invalid_phase";
    case ParseError::invalid_insult_id: return "invalid_insult_id";
    case ParseError::invalid_casus_belli: return "invalid_casus_belli";
    case ParseError::invalid_war_goal_province: return "invalid_war_goal_province";
    case ParseError::invalid_war_goal_beneficiary: return "invalid_war_goal_beneficiary";
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

struct Field {
    const char* data=nullptr;
    std::size_t size=0;
};

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

inline bool hex_digit(char value,std::uint8_t& result) noexcept {
    if (value>='0' && value<='9') {
        result=static_cast<std::uint8_t>(value-'0');
        return true;
    }
    if (value>='a' && value<='f') {
        result=static_cast<std::uint8_t>(value-'a'+10);
        return true;
    }
    if (value>='A' && value<='F') {
        result=static_cast<std::uint8_t>(value-'A'+10);
        return true;
    }
    return false;
}

inline bool parse_unsigned_decimal(Field field,std::uint64_t maximum,
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

inline bool parse_signed_int32(Field field,std::int32_t& result) noexcept {
    if (!field.data || field.size==0) return false;
    bool negative=false;
    std::size_t offset=0;
    if (field.data[0]=='-') {
        negative=true;
        offset=1;
    }
    if (offset==field.size) return false;
    const std::uint64_t maximum=negative?2147483648ull:2147483647ull;
    Field magnitude{field.data+offset,field.size-offset};
    std::uint64_t value=0;
    if (!parse_unsigned_decimal(magnitude,maximum,value)) return false;
    if (negative) {
        if (value==2147483648ull) result=static_cast<std::int32_t>(-2147483647-1);
        else result=-static_cast<std::int32_t>(value);
    } else {
        result=static_cast<std::int32_t>(value);
    }
    return true;
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
    const Field pid_field{field.data,dash};
    const Field creation_field{field.data+dash+1,field.size-dash-1};
    std::uint64_t parsed_pid=0;
    if (!parse_unsigned_decimal(pid_field,
            std::numeric_limits<std::uint32_t>::max(),parsed_pid) || parsed_pid==0) return false;
    std::uint64_t parsed_creation=0;
    for (std::size_t index=0;index<creation_field.size;++index) {
        std::uint8_t digit=0;
        if (!hex_digit(creation_field.data[index],digit)) return false;
        if (parsed_creation>(std::numeric_limits<std::uint64_t>::max()-digit)/16u) return false;
        parsed_creation=parsed_creation*16u+digit;
    }
    if (parsed_creation==0) return false;
    pid=static_cast<std::uint32_t>(parsed_pid);
    creation=parsed_creation;
    return true;
}

inline bool valid_request_id(Field field) noexcept {
    if (field.size==0 || field.size>kMaxRequestIdLength) return false;
    for (std::size_t index=0;index<field.size;++index) {
        const char value=field.data[index];
        const bool alpha_numeric=(value>='A' && value<='Z')
            || (value>='a' && value<='z')
            || (value>='0' && value<='9');
        if (!alpha_numeric && value!='_' && value!='-') return false;
    }
    return true;
}

inline bool valid_recipient(Field field) noexcept {
    if (field.size!=3) return false;
    for (std::size_t index=0;index<3;++index)
        if (field.data[index]<'A' || field.data[index]>'Z') return false;
    return true;
}

inline bool valid_casus_belli(Field field) noexcept {
    if (field.size==0 || field.size>128) return false;
    for (std::size_t index=0;index<field.size;++index) {
        const char value=field.data[index];
        const bool alpha_numeric=(value>='A' && value<='Z')
            || (value>='a' && value<='z')
            || (value>='0' && value<='9');
        if (!alpha_numeric && value!='_') return false;
    }
    return true;
}

inline bool valid_war_goal_beneficiary(Field field) noexcept {
    if (equals(field,"---")) return true;
    return valid_recipient(field);
}

inline bool exact_session(const char* actual,const char* expected) noexcept {
    if (!actual || !expected) return false;
    for (std::size_t index=0;index<=kMaxSessionIdLength;++index) {
        if (actual[index]!=expected[index]) return false;
        if (expected[index]==0) return true;
    }
    return false;
}

} // namespace detail

// Parse exactly one ASCII protocol line, including its final LF.  `length`
// must include that LF; it is intentionally not inferred with strlen().
inline ParseResult parse_request(const char* bytes,std::size_t length,
    ExecutionRequest& output) noexcept {
    output=ExecutionRequest{};
    if (!bytes) return ParseResult{ParseError::null_input,0};
    if (length==0) return ParseResult{ParseError::empty_input,0};
    if (length>kMaxWireBytes) return ParseResult{ParseError::wire_too_long,0};
    if (bytes[length-1]!='\n') return ParseResult{ParseError::missing_final_lf,0};
    if (length>=2 && bytes[length-2]=='\r') return ParseResult{ParseError::crlf_rejected,0};

    const std::size_t content_length=length-1;
    for (std::size_t index=0;index<content_length;++index) {
        if (bytes[index]==0) return ParseResult{ParseError::embedded_nul,0};
        if (bytes[index]=='\n') return ParseResult{ParseError::embedded_newline,0};
        if (bytes[index]=='\r') return ParseResult{ParseError::embedded_carriage_return,0};
    }

    // v1 has nine fields including the version.  v2 appends one insult-id
    // field, making ten total fields.  v3 appends casus-belli, province and
    // beneficiary fields, making twelve total fields.  Keep the split
    // bounded so a malformed tail cannot grow an unbounded temporary
    // structure.
    detail::Field fields[12]{};
    std::size_t field_count=1;
    fields[0].data=bytes;
    for (std::size_t index=0;index<content_length;++index) {
        if (bytes[index]!='|') continue;
        if (field_count>=12) return ParseResult{ParseError::field_count,field_count};
        fields[field_count-1].size=bytes+index-fields[field_count-1].data;
        fields[field_count].data=bytes+index+1;
        ++field_count;
    }
    if (field_count>0)
        fields[field_count-1].size=bytes+content_length-fields[field_count-1].data;
    if (field_count==0 || field_count>12)
        return ParseResult{ParseError::field_count,field_count};
    const bool v1=detail::equals(fields[0],"v1");
    const bool v2=detail::equals(fields[0],"v2");
    const bool v3=detail::equals(fields[0],"EU4DIP_EXEC3");
    if (!v1 && !v2 && !v3) return ParseResult{ParseError::invalid_version,0};
    if ((v1 && field_count!=9) || (v2 && field_count!=10)
        || (v3 && field_count!=12))
        return ParseResult{ParseError::field_count,field_count};
    const std::size_t required_fields=v3?12u:(v2?10u:9u);
    for (std::size_t index=0;index<required_fields;++index)
        if (fields[index].size==0) return ParseResult{ParseError::empty_field,index};

    if (!detail::valid_request_id(fields[1])
        || !detail::copy_field(output.request_id,sizeof(output.request_id),fields[1]))
        return ParseResult{ParseError::invalid_request_id,1};
    if (!detail::parse_session(fields[2],output.session_pid,output.session_creation_filetime)
        || !detail::copy_field(output.session_id,sizeof(output.session_id),fields[2]))
        return ParseResult{ParseError::invalid_session_id,2};
    if (!detail::parse_unsigned_decimal(fields[3],
            std::numeric_limits<std::uint64_t>::max(),output.expires_filetime))
        return ParseResult{ParseError::invalid_expiry,3};
    if (!detail::parse_signed_int32(fields[4],output.date_raw))
        return ParseResult{ParseError::invalid_date,4};
    const bool declare_war=detail::equals(fields[5],"declare_war");
    if ((!detail::equals(fields[5],"offer_alliance")
            && !detail::equals(fields[5],"dissolve_alliance")
            && !detail::equals(fields[5],"offer_royal_marriage")
            && !detail::equals(fields[5],"break_royal_ties")
            && !detail::equals(fields[5],"improve_relations")
            && !detail::equals(fields[5],"stop_improving_relations")
            && !detail::equals(fields[5],"build_spy_network")
            && !detail::equals(fields[5],"stop_building_spy_network")
            && !detail::equals(fields[5],"proclaim_guarantee")
            && !detail::equals(fields[5],"revoke_guarantee")
            && !detail::equals(fields[5],"support_independence")
            && !detail::equals(fields[5],"revoke_support_independence")
            && !detail::equals(fields[5],"ask_military_access")
            && !detail::equals(fields[5],"cancel_military_access")
            && !detail::equals(fields[5],"offer_vassalization")
            && !detail::equals(fields[5],"cancel_vassalization")
            && !detail::equals(fields[5],"send_insult")
            && !detail::equals(fields[5],"scornful_insult")
            && !declare_war)
        || !detail::copy_field(output.action_id,sizeof(output.action_id),fields[5]))
        return ParseResult{ParseError::invalid_action,5};
    const bool insult_action=detail::equals(fields[5],"send_insult")
        || detail::equals(fields[5],"scornful_insult");
    // Insults deliberately use v2 because the appended signed parameter is
    // part of their authority identity.  Existing actions remain v1-only.
    if (insult_action!=v2)
        return ParseResult{ParseError::invalid_action,5};
    // Declare War is deliberately isolated to the v3 shape.  Conversely, a
    // v3 record cannot smuggle an existing action into the larger field
    // layout.
    if (declare_war!=v3)
        return ParseResult{ParseError::invalid_action,5};
    if (!detail::equals(fields[6],"FRA")
        || !detail::copy_field(output.actor,sizeof(output.actor),fields[6]))
        return ParseResult{ParseError::invalid_actor,6};
    if (!detail::valid_recipient(fields[7])
        || !detail::copy_field(output.recipient,sizeof(output.recipient),fields[7]))
        return ParseResult{ParseError::invalid_recipient,7};
    if (!detail::equals(fields[8],"initiate")
        || !detail::copy_field(output.phase,sizeof(output.phase),fields[8]))
        return ParseResult{ParseError::invalid_phase,8};
    if (v2) {
        if (!detail::parse_signed_int32(fields[9],output.insult_id))
            return ParseResult{ParseError::invalid_insult_id,9};
        if ((detail::equals(fields[5],"send_insult")
                && output.insult_id!=-1)
            || (detail::equals(fields[5],"scornful_insult")
                && output.insult_id<0))
            return ParseResult{ParseError::invalid_insult_id,9};
    }
    if (v3) {
        if (!detail::valid_casus_belli(fields[9])
            || !detail::copy_field(output.casus_belli,sizeof(output.casus_belli),
                fields[9]))
            return ParseResult{ParseError::invalid_casus_belli,9};
        if (!detail::parse_signed_int32(fields[10],output.war_goal_province)
            || (output.war_goal_province!=-1 && output.war_goal_province<=0))
            return ParseResult{ParseError::invalid_war_goal_province,10};
        if (!detail::valid_war_goal_beneficiary(fields[11])
            || !detail::copy_field(output.war_goal_beneficiary,
                sizeof(output.war_goal_beneficiary),fields[11]))
            return ParseResult{ParseError::invalid_war_goal_beneficiary,11};
        // The no-CB marker is a real protocol value, not an empty placeholder:
        // without a CB there is no province target, and the beneficiary is
        // either the initiating country or the explicit empty marker.
        if (detail::equals(fields[9],"no_casus_belli")
            && output.war_goal_province!=-1)
            return ParseResult{ParseError::invalid_war_goal_province,10};
        if (detail::equals(fields[9],"no_casus_belli")
            && !detail::equals(fields[11],"FRA")
            && !detail::equals(fields[11],"---"))
            return ParseResult{ParseError::invalid_war_goal_beneficiary,11};
    }
    return ParseResult{ParseError::ok,0};
}

inline ContextResult validate_context(const ExecutionRequest& request,
    const char* expected_session_id,std::uint64_t current_filetime,
    std::int32_t current_date) noexcept {
    if (!expected_session_id || expected_session_id[0]==0)
        return ContextResult{ContextError::expected_session_missing};
    if (!detail::exact_session(request.session_id,expected_session_id))
        return ContextResult{ContextError::session_mismatch};
    if (request.expires_filetime<=current_filetime)
        return ContextResult{ContextError::expired};
    if (request.expires_filetime-current_filetime>kMaxExpiryWindowFiletime)
        return ContextResult{ContextError::expiry_window_exceeded};
    if (request.date_raw!=current_date)
        return ContextResult{ContextError::date_mismatch};
    return ContextResult{ContextError::ok};
}

} // namespace bridge::alliance_execution_wire
