#pragma once

// Allocation-free, bounded parser for the independent Peace execution wire.
// The parser consumes an explicit byte length, so a hidden NUL or trailing
// bytes cannot be accepted through a C-string view.  The native execution
// layer receives the complete user-selected term summary and constructs the
// private native offer separately.

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>

namespace bridge::peace_execution_wire {

constexpr std::size_t kMaxRequestIdLength=64;
constexpr std::size_t kMaxActionIdLength=24;
constexpr std::size_t kMaxWarIdLength=29;
constexpr std::size_t kMaxProvinceIds=16;
constexpr std::size_t kMaxWireBytes=512;

// amount_raw is -1 when no money term is selected.  A selected amount is a
// positive int32 value in 100-raw-unit increments; zero is not a money term.

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
    invalid_prefix,
    invalid_creation_epoch,
    invalid_request_id,
    invalid_action,
    invalid_actor,
    invalid_recipient,
    invalid_date,
    invalid_expiry_epoch_ms,
    invalid_war_id,
    invalid_direction,
    invalid_amount,
    invalid_province_ids,
    invalid_beneficiary,
    invalid_term_mask,
    invalid_combination,
};

struct ParseResult {
    ParseError error=ParseError::invalid_prefix;
    std::size_t field=0;

    constexpr bool ok() const noexcept { return error==ParseError::ok; }
};

// All text fields are NUL-terminated fixed-capacity buffers.  The selected
// flags describe what the wire carries; they do not authorize a native call.
struct PeaceExecutionRequest {
    char request_id[kMaxRequestIdLength+1]{};
    char action_id[kMaxActionIdLength+1]{};
    char actor[4]{};
    char recipient[4]{};
    char war_id[kMaxWarIdLength+1]{};
    char direction[8]{};
    // The text is retained for the public wire contract.  This flag is a
    // parsed convenience for the native constructor's raw direction byte:
    // demand=1, offer=0.  It does not claim that the game's business labels
    // for those raw values are independently recovered.
    bool demand_direction=true;
    char beneficiary[4]{};
    std::uint64_t creation_epoch=0;
    std::uint64_t expiry_epoch_ms=0;
    std::int32_t date_raw=0;
    std::int32_t amount_raw=-1;
    std::int32_t province_ids[kMaxProvinceIds]{};
    std::uint8_t province_count=0;
    bool selected_amount=false;
    bool selected_provinces=false;
    bool selected_beneficiary=false;
    bool selected_reparations=false;
    bool white_peace=false;
    bool demand_ducats=false;
    bool cede_province=false;
    bool war_reparations=false;
    // EXEC2's mask is one of r, mr, pr, or mpr.  Four bytes hold the
    // longest value and its NUL terminator.
    char term_mask[4]{};
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
    case ParseError::invalid_prefix: return "invalid_prefix";
    case ParseError::invalid_creation_epoch: return "invalid_creation_epoch";
    case ParseError::invalid_request_id: return "invalid_request_id";
    case ParseError::invalid_action: return "invalid_action";
    case ParseError::invalid_actor: return "invalid_actor";
    case ParseError::invalid_recipient: return "invalid_recipient";
    case ParseError::invalid_date: return "invalid_date";
    case ParseError::invalid_expiry_epoch_ms: return "invalid_expiry_epoch_ms";
    case ParseError::invalid_war_id: return "invalid_war_id";
    case ParseError::invalid_direction: return "invalid_direction";
    case ParseError::invalid_amount: return "invalid_amount";
    case ParseError::invalid_province_ids: return "invalid_province_ids";
    case ParseError::invalid_beneficiary: return "invalid_beneficiary";
    case ParseError::invalid_term_mask: return "invalid_term_mask";
    case ParseError::invalid_combination: return "invalid_combination";
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

inline bool lowercase_hex_digit(char value) noexcept {
    return (value>='0' && value<='9') || (value>='a' && value<='f');
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
    const Field magnitude{field.data+offset,field.size-offset};
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

inline bool valid_canonical_tag(Field field) noexcept {
    if (field.size!=3) return false;
    for (std::size_t index=0;index<3;++index) {
        const char value=field.data[index];
        if (!((value>='A' && value<='Z') || (value>='0' && value<='9')))
            return false;
    }
    return true;
}

inline bool valid_war_id(Field field) noexcept {
    if (field.size!=kMaxWarIdLength
        || std::memcmp(field.data,"war_",4)!=0
        || field.data[20]!='_') return false;
    for (std::size_t index=4;index<20;++index)
        if (!lowercase_hex_digit(field.data[index])) return false;
    for (std::size_t index=21;index<29;++index)
        if (!lowercase_hex_digit(field.data[index])) return false;
    return true;
}

inline bool parse_province_ids(Field field,
    std::int32_t (&output)[kMaxProvinceIds],std::uint8_t& count) noexcept {
    count=0;
    if (equals(field,"-")) return true;
    if (!field.data || field.size==0) return false;
    std::size_t start=0;
    while (start<field.size) {
        std::size_t end=start;
        while (end<field.size && field.data[end]!=',') ++end;
        if (end==start || count>=kMaxProvinceIds) return false;
        std::int32_t value=0;
        if (!parse_signed_int32(Field{field.data+start,end-start},value)
            || value<=0) return false;
        for (std::size_t prior=0;prior<count;++prior)
            if (output[prior]==value) return false;
        output[count++]=value;
        if (end==field.size) break;
        start=end+1;
        if (start==field.size) return false;
    }
    return count>0;
}

inline bool parse_term_mask(Field field,char (&output)[4],bool& money,
    bool& province,bool& reparations) noexcept {
    money=false;
    province=false;
    reparations=false;
    if (!equals(field,"r") && !equals(field,"mr")
        && !equals(field,"pr") && !equals(field,"mpr")) return false;
    if (!copy_field(output,4,field)) return false;
    for (std::size_t index=0;index<field.size;++index) {
        if (field.data[index]=='m') money=true;
        else if (field.data[index]=='p') province=true;
        else if (field.data[index]=='r') reparations=true;
    }
    return reparations;
}

} // namespace detail

// Parse exactly one Peace execution request, including its final LF.  EXEC1
// has 13 fields: prefix, creation epoch, request id, action, actor, recipient,
// date, expiry epoch, war id, direction, amount, province CSV, beneficiary.
// EXEC2 appends a fourteenth term_mask field.  The two versions intentionally
// have separate action/combination contracts so an old request cannot smuggle
// the new reparations term into the legacy wire.
inline ParseResult parse_request(const char* bytes,std::size_t length,
    PeaceExecutionRequest& output) noexcept {
    output=PeaceExecutionRequest{};
    if (!bytes) return ParseResult{ParseError::null_input,0};
    if (length==0) return ParseResult{ParseError::empty_input,0};
    if (length>kMaxWireBytes) return ParseResult{ParseError::wire_too_long,0};
    if (bytes[length-1]!='\n') return ParseResult{ParseError::missing_final_lf,0};
    if (length>=2 && bytes[length-2]=='\r')
        return ParseResult{ParseError::crlf_rejected,0};

    const std::size_t content_length=length-1;
    for (std::size_t index=0;index<content_length;++index) {
        if (bytes[index]==0) return ParseResult{ParseError::embedded_nul,0};
        if (bytes[index]=='\n') return ParseResult{ParseError::embedded_newline,0};
        if (bytes[index]=='\r') return ParseResult{ParseError::embedded_carriage_return,0};
    }

    detail::Field fields[14]{};
    std::size_t field_count=1;
    fields[0].data=bytes;
    for (std::size_t index=0;index<content_length;++index) {
        if (bytes[index]!=' ') continue;
        if (field_count>=14) return ParseResult{ParseError::field_count,field_count};
        fields[field_count-1].size=bytes+index-fields[field_count-1].data;
        fields[field_count].data=bytes+index+1;
        ++field_count;
    }
    fields[field_count-1].size=bytes+content_length-fields[field_count-1].data;
    const bool exec1=detail::equals(fields[0],"EU4PEACE_EXEC1");
    const bool exec2=detail::equals(fields[0],"EU4PEACE_EXEC2");
    if (!exec1 && !exec2) return ParseResult{ParseError::invalid_prefix,0};
    const std::size_t expected_fields=exec2?14u:13u;
    if (field_count!=expected_fields)
        return ParseResult{ParseError::field_count,field_count};
    for (std::size_t index=0;index<expected_fields;++index)
        if (fields[index].size==0) return ParseResult{ParseError::empty_field,index};

    if (!detail::parse_unsigned_decimal(fields[1],
            std::numeric_limits<std::uint64_t>::max(),output.creation_epoch))
        return ParseResult{ParseError::invalid_creation_epoch,1};
    if (!detail::valid_request_id(fields[2])
        || !detail::copy_field(output.request_id,sizeof(output.request_id),fields[2]))
        return ParseResult{ParseError::invalid_request_id,2};

    const bool white=detail::equals(fields[3],"white_peace");
    const bool money=detail::equals(fields[3],"demand_ducats");
    const bool province=detail::equals(fields[3],"cede_province");
    const bool reparations=detail::equals(fields[3],"war_reparations");
    if ((!white && !money && !province && !reparations)
        || (exec1 && reparations)
        || (exec2 && white)
        || !detail::copy_field(output.action_id,sizeof(output.action_id),fields[3]))
        return ParseResult{ParseError::invalid_action,3};
    output.white_peace=white;
    output.demand_ducats=money;
    output.cede_province=province;
    output.war_reparations=reparations;

    if (!detail::equals(fields[4],"FRA")
        || !detail::copy_field(output.actor,sizeof(output.actor),fields[4]))
        return ParseResult{ParseError::invalid_actor,4};
    if (!detail::valid_canonical_tag(fields[5])
        || detail::equals(fields[5],"FRA")
        || !detail::copy_field(output.recipient,sizeof(output.recipient),fields[5]))
        return ParseResult{ParseError::invalid_recipient,5};
    if (!detail::parse_signed_int32(fields[6],output.date_raw))
        return ParseResult{ParseError::invalid_date,6};
    if (!detail::parse_unsigned_decimal(fields[7],
            std::numeric_limits<std::uint64_t>::max(),output.expiry_epoch_ms))
        return ParseResult{ParseError::invalid_expiry_epoch_ms,7};
    if (!detail::valid_war_id(fields[8])
        || !detail::copy_field(output.war_id,sizeof(output.war_id),fields[8]))
        return ParseResult{ParseError::invalid_war_id,8};
    const bool demand=detail::equals(fields[9],"demand");
    const bool offer=detail::equals(fields[9],"offer");
    if ((!demand && !offer)
        || !detail::copy_field(output.direction,sizeof(output.direction),fields[9]))
        return ParseResult{ParseError::invalid_direction,9};
    output.demand_direction=demand;

    if (!detail::parse_signed_int32(fields[10],output.amount_raw)
        || output.amount_raw<-1
        || (output.amount_raw==0)
        || (output.amount_raw>0 && output.amount_raw%100!=0))
        return ParseResult{ParseError::invalid_amount,10};
    output.selected_amount=output.amount_raw>=0;
    if (!detail::parse_province_ids(fields[11],output.province_ids,
            output.province_count))
        return ParseResult{ParseError::invalid_province_ids,11};
    output.selected_provinces=output.province_count>0;

    if (output.selected_provinces) {
        if (!detail::valid_canonical_tag(fields[12])
            || !detail::copy_field(output.beneficiary,sizeof(output.beneficiary),fields[12]))
            return ParseResult{ParseError::invalid_beneficiary,12};
        output.selected_beneficiary=true;
    } else {
        if (!detail::equals(fields[12],"-")
            || !detail::copy_field(output.beneficiary,sizeof(output.beneficiary),fields[12]))
            return ParseResult{ParseError::invalid_beneficiary,12};
    }

    if (exec1) {
        if ((white && (output.amount_raw!=-1 || output.selected_provinces
                       || output.selected_beneficiary))
            || (money && output.amount_raw<0)
            || (province && !output.selected_provinces))
            return ParseResult{ParseError::invalid_combination,3};
        return ParseResult{ParseError::ok,0};
    }

    bool mask_money=false;
    bool mask_province=false;
    bool mask_reparations=false;
    if (!detail::parse_term_mask(fields[13],output.term_mask,mask_money,
            mask_province,mask_reparations))
        return ParseResult{ParseError::invalid_term_mask,13};
    output.selected_reparations=mask_reparations;

    // The mask is an exact summary of the parsed payload.  The r flag is
    // mandatory in EXEC2, while m/p must agree with the corresponding fields.
    if (mask_money!=output.selected_amount
        || mask_province!=output.selected_provinces)
        return ParseResult{ParseError::invalid_combination,13};
    if ((money && !mask_money)
        || (province && !mask_province)
        || (reparations && !mask_reparations))
        return ParseResult{ParseError::invalid_combination,3};
    return ParseResult{ParseError::ok,0};
}

} // namespace bridge::peace_execution_wire
