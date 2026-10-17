#pragma once

// Fixed-size wire contract for the Rival country-command family.
//
// This protocol is intentionally independent from the generic diplomatic
// execution wire.  It carries only the two currently supported one-sided
// commands.  The public producer supplies a session creation value rather
// than a process identifier or an RVA; the native integration layer binds
// that value to its live session before touching the authority ledger.

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>

namespace bridge::rival_command_wire {

constexpr std::size_t kMaxRequestIdLength=64;
constexpr std::size_t kMaxSessionHexLength=16;
constexpr std::size_t kMaxWireBytes=256;
constexpr std::uint64_t kMaxDeadlineWindowTicks=60000u;

enum class CommandKind : std::uint8_t {
    set_rival=0,
    remove_rival=1
};

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
    invalid_session_hex,
    invalid_expiry_tick,
    invalid_date,
    invalid_action,
    invalid_actor,
    invalid_recipient
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
    deadline_window_exceeded,
    date_mismatch
};

struct ContextResult {
    ContextError error=ContextError::session_mismatch;

    constexpr bool ok() const noexcept { return error==ContextError::ok; }
};

// The fields are copied into fixed arrays.  `session_epoch` is the parsed
// sessioncreationhex token; no process identifier, native address, or RVA is
// present in this public wire result.
struct ExecutionRequest {
    char request_id[kMaxRequestIdLength+1]{};
    char session_creation_hex[kMaxSessionHexLength+1]{};
    char action_id[13]{};
    char actor[4]{};
    char recipient[4]{};
    std::uint64_t session_epoch=0;
    std::uint64_t expiry_tick=0;
    std::int32_t date_raw=0;
    CommandKind command=CommandKind::set_rival;
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
    case ParseError::invalid_session_hex: return "invalid_session_hex";
    case ParseError::invalid_expiry_tick: return "invalid_expiry_tick";
    case ParseError::invalid_date: return "invalid_date";
    case ParseError::invalid_action: return "invalid_action";
    case ParseError::invalid_actor: return "invalid_actor";
    case ParseError::invalid_recipient: return "invalid_recipient";
    }
    return "unknown";
}

inline const char* context_error_name(ContextError error) noexcept {
    switch (error) {
    case ContextError::ok: return "ok";
    case ContextError::expected_session_missing: return "expected_session_missing";
    case ContextError::session_mismatch: return "session_mismatch";
    case ContextError::expired: return "expired";
    case ContextError::deadline_window_exceeded: return "deadline_window_exceeded";
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

inline bool copy_field(char* destination,std::size_t capacity,
    Field field) noexcept {
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
        const std::uint64_t digit=static_cast<std::uint64_t>(
            field.data[index]-'0');
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
    const Field magnitude{field.data+offset,field.size-offset};
    std::uint64_t value=0;
    if (!parse_unsigned_decimal(magnitude,maximum,value)) return false;
    if (negative) {
        result=value==2147483648ull
            ? static_cast<std::int32_t>(-2147483647-1)
            : -static_cast<std::int32_t>(value);
    } else {
        result=static_cast<std::int32_t>(value);
    }
    return true;
}

inline bool parse_session_hex(Field field,std::uint64_t& result) noexcept {
    if (!field.data || field.size==0 || field.size>kMaxSessionHexLength)
        return false;
    std::uint64_t value=0;
    for (std::size_t index=0;index<field.size;++index) {
        std::uint8_t digit=0;
        if (!hex_digit(field.data[index],digit)) return false;
        if (value>(std::numeric_limits<std::uint64_t>::max()-digit)/16u)
            return false;
        value=value*16u+digit;
    }
    if (value==0) return false;
    result=value;
    return true;
}

inline bool valid_request_id(Field field) noexcept {
    if (!field.data || field.size==0 || field.size>kMaxRequestIdLength)
        return false;
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
    if (!field.data || field.size!=3) return false;
    for (std::size_t index=0;index<3;++index)
        if (field.data[index]<'A' || field.data[index]>'Z') return false;
    return !(field.data[0]=='F' && field.data[1]=='R' && field.data[2]=='A');
}

} // namespace detail

// Parse exactly one ASCII line.  The explicit byte length is part of the
// contract: an embedded NUL cannot truncate the input before validation.
inline ParseResult parse_request(const char* bytes,std::size_t length,
    ExecutionRequest& output) noexcept {
    output=ExecutionRequest{};
    if (!bytes) return ParseResult{ParseError::null_input,0};
    if (length==0) return ParseResult{ParseError::empty_input,0};
    if (length>kMaxWireBytes) return ParseResult{ParseError::wire_too_long,0};
    if (bytes[length-1]!='\n')
        return ParseResult{ParseError::missing_final_lf,0};
    if (length>=2 && bytes[length-2]=='\r')
        return ParseResult{ParseError::crlf_rejected,0};

    const std::size_t content_length=length-1;
    for (std::size_t index=0;index<content_length;++index) {
        if (bytes[index]==0) return ParseResult{ParseError::embedded_nul,0};
        if (bytes[index]=='\n')
            return ParseResult{ParseError::embedded_newline,0};
        if (bytes[index]=='\r')
            return ParseResult{ParseError::embedded_carriage_return,0};
    }

    constexpr std::size_t kFieldCount=8;
    detail::Field fields[kFieldCount]{};
    std::size_t field_count=1;
    fields[0].data=bytes;
    for (std::size_t index=0;index<content_length;++index) {
        if (bytes[index]!=' ') continue;
        if (field_count>=kFieldCount)
            return ParseResult{ParseError::field_count,field_count};
        fields[field_count-1].size=bytes+index-fields[field_count-1].data;
        fields[field_count].data=bytes+index+1;
        ++field_count;
    }
    fields[field_count-1].size=
        bytes+content_length-fields[field_count-1].data;
    if (field_count!=kFieldCount)
        return ParseResult{ParseError::field_count,field_count};
    for (std::size_t index=0;index<kFieldCount;++index)
        if (fields[index].size==0)
            return ParseResult{ParseError::empty_field,index};

    if (!detail::equals(fields[0],"RIVAL_EXEC1"))
        return ParseResult{ParseError::invalid_version,0};
    if (!detail::valid_request_id(fields[1])
        || !detail::copy_field(output.request_id,sizeof(output.request_id),fields[1]))
        return ParseResult{ParseError::invalid_request_id,1};
    if (!detail::parse_session_hex(fields[2],output.session_epoch)
        || !detail::copy_field(output.session_creation_hex,
            sizeof(output.session_creation_hex),fields[2]))
        return ParseResult{ParseError::invalid_session_hex,2};
    if (!detail::parse_unsigned_decimal(fields[3],
        std::numeric_limits<std::uint64_t>::max(),output.expiry_tick))
        return ParseResult{ParseError::invalid_expiry_tick,3};
    if (!detail::parse_signed_int32(fields[4],output.date_raw))
        return ParseResult{ParseError::invalid_date,4};
    if (detail::equals(fields[5],"set_rival")) {
        output.command=CommandKind::set_rival;
    } else if (detail::equals(fields[5],"remove_rival")) {
        output.command=CommandKind::remove_rival;
    } else {
        return ParseResult{ParseError::invalid_action,5};
    }
    if (!detail::copy_field(output.action_id,sizeof(output.action_id),fields[5]))
        return ParseResult{ParseError::invalid_action,5};
    if (!detail::equals(fields[6],"FRA")
        || !detail::copy_field(output.actor,sizeof(output.actor),fields[6]))
        return ParseResult{ParseError::invalid_actor,6};
    if (!detail::valid_recipient(fields[7])
        || !detail::copy_field(output.recipient,sizeof(output.recipient),fields[7]))
        return ParseResult{ParseError::invalid_recipient,7};
    return ParseResult{ParseError::ok,0};
}

inline ContextResult validate_context(const ExecutionRequest& request,
    std::uint64_t expected_session_epoch,std::uint64_t current_tick,
    std::int32_t current_date) noexcept {
    if (expected_session_epoch==0)
        return ContextResult{ContextError::expected_session_missing};
    if (request.session_epoch!=expected_session_epoch)
        return ContextResult{ContextError::session_mismatch};
    if (request.expiry_tick<=current_tick)
        return ContextResult{ContextError::expired};
    if (request.expiry_tick-current_tick>kMaxDeadlineWindowTicks)
        return ContextResult{ContextError::deadline_window_exceeded};
    if (request.date_raw!=current_date)
        return ContextResult{ContextError::date_mismatch};
    return ContextResult{ContextError::ok};
}

} // namespace bridge::rival_command_wire
