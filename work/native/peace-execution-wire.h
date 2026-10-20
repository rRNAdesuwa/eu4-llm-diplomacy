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
constexpr std::size_t kMaxAnnulPartners=16;
constexpr std::size_t kMaxSubjectCountries=16;
constexpr std::size_t kMaxWireBytes=1024;

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
    invalid_trade_power_source,
    invalid_annul_country,
    invalid_annul_partners,
    invalid_return_core_ids,
    invalid_return_core_owner,
    invalid_revoke_core_ids,
    invalid_revoke_core_owner,
    invalid_release_subject_countries,
    invalid_transfer_subject_countries,
    invalid_subject_overlap,
    invalid_country_term_country,
    invalid_country_term_source,
    invalid_country_term_beneficiary,
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
    bool selected_trade_power=false;
    bool white_peace=false;
    bool demand_ducats=false;
    bool cede_province=false;
    bool war_reparations=false;
    bool transfer_trade_power=false;
    // EXEC2's mask is one of r, mr, pr, or mpr.  EXEC3/4 add trade power and
    // use one of t, mt, pt, rt, mpt, mrt, prt, or mprt.  EXEC5 adds concede
    // defeat and accepts every canonical m,p,r,t,c combination containing c.
    // EXEC6 appends annul treaties and accepts every canonical
    // m,p,r,t,c,a combination containing a.  EXEC7 additionally accepts
    // h/s/f in canonical order and requires at least one of those three
    // terms.  EXEC8 appends b/v for return/revoke core and requires one of
    // them.  EXEC9 appends l/x for release/transfer subject and requires one
    // of them. This legacy prefix retains its original layout. EXEC10 stores
    // its longer complete mask in the appended country_term_mask below.
    char term_mask[14]{};
    // EXEC3 derives these two fields for a selected trade-power term without
    // adding wire fields.  EXEC4 carries trade_power_source as its fifteenth
    // field and derives trade_power_beneficiary from direction.  EXEC5 uses
    // the same fifteenth field; it must be '-' when t is absent.  Appending
    // new C flags after these fields preserves the preceding R51 offsets.
    char trade_power_source[4]{};
    char trade_power_beneficiary[4]{};
    bool selected_concede_defeat=false;
    bool concede_defeat=false;
    bool selected_annul_treaties=false;
    bool annul_treaties=false;
    char annul_country[4]{};
    char annul_partners[kMaxAnnulPartners][4]{};
    std::uint8_t annul_partner_count=0;
    // EXEC7 adds three native base-term flags.  They intentionally carry no
    // country fields: the native offer derives the relevant countries from
    // direction and its own participant context.
    bool selected_humiliate_rival=false;
    bool humiliate_rival=false;
    bool selected_show_strength=false;
    bool show_strength=false;
    bool selected_force_religion=false;
    bool force_religion=false;
    bool selected_return_core=false;
    bool return_core=false;
    std::int32_t return_core_ids[kMaxProvinceIds]{};
    std::uint8_t return_core_count=0;
    char return_core_owner[4]{};
    bool selected_revoke_core=false;
    bool revoke_core=false;
    std::int32_t revoke_core_ids[kMaxProvinceIds]{};
    std::uint8_t revoke_core_count=0;
    char revoke_core_owner[4]{};
    bool selected_release_subject=false;
    bool release_subject=false;
    char release_subject_countries[kMaxSubjectCountries][4]{};
    std::uint8_t release_subject_count=0;
    bool selected_transfer_subject=false;
    bool transfer_subject=false;
    char transfer_subject_countries[kMaxSubjectCountries][4]{};
    std::uint8_t transfer_subject_count=0;
    std::uint8_t legacy_tail_padding=0;
    char country_term_mask[19]{};
    // EXEC10 country terms append their public request fields. These are
    // requested countries, separate from any native-expanded province list.
    bool selected_release_nation=false,release_nation=false;
    bool selected_force_vassalization=false,force_vassalization=false;
    bool selected_form_personal_union=false,form_personal_union=false;
    bool selected_grant_independence=false,grant_independence=false;
    bool selected_full_annexation=false,full_annexation=false;
    char release_nation_country[4]{},release_nation_source[4]{};
    char vassal_country[4]{},union_country[4]{},independence_country[4]{};
    char annex_country[4]{};
    char vassal_beneficiary[4]{},union_beneficiary[4]{},annex_beneficiary[4]{};
};

inline const char* effective_term_mask(const PeaceExecutionRequest& request) noexcept {
    return request.country_term_mask[0]?request.country_term_mask:request.term_mask;
}

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
    case ParseError::invalid_trade_power_source: return "invalid_trade_power_source";
    case ParseError::invalid_annul_country: return "invalid_annul_country";
    case ParseError::invalid_annul_partners: return "invalid_annul_partners";
    case ParseError::invalid_return_core_ids: return "invalid_return_core_ids";
    case ParseError::invalid_return_core_owner: return "invalid_return_core_owner";
    case ParseError::invalid_revoke_core_ids: return "invalid_revoke_core_ids";
    case ParseError::invalid_revoke_core_owner: return "invalid_revoke_core_owner";
    case ParseError::invalid_release_subject_countries: return "invalid_release_subject_countries";
    case ParseError::invalid_transfer_subject_countries: return "invalid_transfer_subject_countries";
    case ParseError::invalid_subject_overlap: return "invalid_subject_overlap";
    case ParseError::invalid_country_term_country: return "invalid_country_term_country";
    case ParseError::invalid_country_term_source: return "invalid_country_term_source";
    case ParseError::invalid_country_term_beneficiary: return "invalid_country_term_beneficiary";
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

inline bool parse_annul_partners(Field field,Field country,
    char (&output)[kMaxAnnulPartners][4],std::uint8_t& count) noexcept {
    count=0;
    if (!field.data || field.size==0) return false;
    std::size_t start=0;
    while (start<field.size) {
        std::size_t end=start;
        while (end<field.size && field.data[end]!=',') ++end;
        const Field partner{field.data+start,end-start};
        if (!valid_canonical_tag(partner) || count>=kMaxAnnulPartners)
            return false;
        if (country.size==3 && std::memcmp(partner.data,country.data,3)==0)
            return false;
        if (count>0 && std::memcmp(output[count-1],partner.data,3)>=0)
            return false;
        if (!copy_field(output[count],sizeof(output[count]),partner))
            return false;
        ++count;
        if (end==field.size) break;
        start=end+1;
        if (start==field.size) return false;
    }
    return count>0;
}

inline bool parse_subject_countries(Field field,
    char (&output)[kMaxSubjectCountries][4],std::uint8_t& count) noexcept {
    count=0;
    if (equals(field,"-")) return true;
    if (!field.data || field.size==0 || field.size>63u) return false;
    std::size_t start=0;
    while (start<field.size) {
        std::size_t end=start;
        while (end<field.size && field.data[end]!=',') ++end;
        const Field country{field.data+start,end-start};
        if (!valid_canonical_tag(country) || count>=kMaxSubjectCountries)
            return false;
        for (std::size_t prior=0;prior<count;++prior)
            if (std::memcmp(output[prior],country.data,3)==0) return false;
        if (!copy_field(output[count],sizeof(output[count]),country)) return false;
        ++count;
        if (end==field.size) break;
        start=end+1;
        if (start==field.size) return false;
    }
    return count>0;
}

inline int term_mask_rank(char value) noexcept {
    switch (value) {
    case 'm': return 0;
    case 'p': return 1;
    case 'r': return 2;
    case 't': return 3;
    case 'c': return 4;
    case 'a': return 5;
    case 'h': return 6;
    case 's': return 7;
    case 'f': return 8;
    case 'b': return 9;
    case 'v': return 10;
    case 'l': return 11;
    case 'x': return 12;
    case 'n': return 13;
    case 'z': return 14;
    case 'u': return 15;
    case 'i': return 16;
    case 'e': return 17;
    default: return -1;
    }
}

template<std::size_t N>
inline bool parse_term_mask(Field field,char (&output)[N],bool& money,
    bool& province,bool& reparations,bool& trade_power,
    bool& concede_defeat,bool& annul_treaties,bool& humiliate_rival,
    bool& show_strength,bool& force_religion,bool& return_core,
    bool& revoke_core,bool trade_power_version,bool concede_defeat_version,
    bool annul_treaties_version,bool advanced_terms_version,
    bool core_terms_version,bool subject_terms_version,
    bool country_terms_version=false) noexcept {
    money=false;
    province=false;
    reparations=false;
    trade_power=false;
    concede_defeat=false;
    annul_treaties=false;
    humiliate_rival=false;
    show_strength=false;
    force_religion=false;
    return_core=false;
    revoke_core=false;
    if ((trade_power_version?1:0)+(concede_defeat_version?1:0)
        +(annul_treaties_version?1:0)+(advanced_terms_version?1:0)
        +(subject_terms_version?1:0)>1
        && !core_terms_version)
        return false;
    if (!field.data || field.size==0 || field.size>(country_terms_version?18u:13u)
        || field.size>=N) return false;
    int previous_rank=-1;
    for (std::size_t index=0;index<field.size;++index) {
        const char value=field.data[index];
        const int rank=term_mask_rank(value);
        if (rank<=previous_rank) return false;
        if (value=='a' && !annul_treaties_version && !advanced_terms_version
            && !core_terms_version && !subject_terms_version && !country_terms_version)
            return false;
        if (value=='c' && !concede_defeat_version && !annul_treaties_version)
            if (!advanced_terms_version && !core_terms_version
                && !subject_terms_version && !country_terms_version) return false;
        if (value=='t' && !trade_power_version && !concede_defeat_version
            && !annul_treaties_version && !advanced_terms_version
            && !core_terms_version && !subject_terms_version && !country_terms_version) return false;
        if ((value=='h' || value=='s' || value=='f')
            && !advanced_terms_version && !core_terms_version
            && !subject_terms_version && !country_terms_version) return false;
        if ((value=='b' || value=='v') && !core_terms_version
            && !subject_terms_version && !country_terms_version) return false;
        if ((value=='l' || value=='x') && !subject_terms_version && !country_terms_version)
            return false;
        if (rank>=13 && !country_terms_version) return false;
        if (rank<0) return false;
        previous_rank=rank;
        if (value=='m') money=true;
        else if (value=='p') province=true;
        else if (value=='r') reparations=true;
        else if (value=='t') trade_power=true;
        else if (value=='c') concede_defeat=true;
        else if (value=='a') annul_treaties=true;
        else if (value=='h') humiliate_rival=true;
        else if (value=='s') show_strength=true;
        else if (value=='f') force_religion=true;
        else if (value=='b') return_core=true;
        else if (value=='v') revoke_core=true;
    }
    if (subject_terms_version
        && !std::memchr(field.data,'l',field.size)
        && !std::memchr(field.data,'x',field.size)) return false;
    if (country_terms_version) {
        if (!std::memchr(field.data,'n',field.size)
            && !std::memchr(field.data,'z',field.size)
            && !std::memchr(field.data,'u',field.size)
            && !std::memchr(field.data,'i',field.size)
            && !std::memchr(field.data,'e',field.size)) return false;
    } else if (core_terms_version) {
        if (!return_core && !revoke_core) return false;
    } else if (annul_treaties_version) {
        if (!annul_treaties) return false;
    } else if (concede_defeat_version) {
        if (!concede_defeat) return false;
    } else if (trade_power_version) {
        if (!trade_power) return false;
    } else if (advanced_terms_version) {
        if (!humiliate_rival && !show_strength && !force_religion) return false;
    } else if (subject_terms_version) {
        // EXEC9 requires l/x above; older term requirements remain optional
        // because subject-bearing masks may combine with any prior term.
    } else if (!reparations) {
        return false;
    }
    if (!copy_field(output,sizeof(output),field)) return false;
    return true;
}

} // namespace detail

inline void derive_trade_power_participants(PeaceExecutionRequest& output) noexcept {
    const char* source=output.demand_direction?output.recipient:output.actor;
    const char* beneficiary=output.demand_direction?output.actor:output.recipient;
    std::memcpy(output.trade_power_source,source,sizeof(output.trade_power_source));
    std::memcpy(output.trade_power_beneficiary,beneficiary,
        sizeof(output.trade_power_beneficiary));
}

// Parse exactly one Peace execution request, including its final LF.  EXEC1
// has 13 fields: prefix, creation epoch, request id, action, actor, recipient,
// date, expiry epoch, war id, direction, amount, province CSV, beneficiary.
// EXEC2 and EXEC3 append a fourteenth term_mask field.  EXEC4 and EXEC5 append
// a fifteenth trade_power_source field after the same term_mask.  EXEC5 uses
// '-' in that field when t is absent.  EXEC6 and EXEC7 keep those fifteen
// fields and append annul_country and annul_partner_csv.  The versions
// intentionally
// have separate action/combination contracts so an old request cannot smuggle
// a newer term into the legacy wire.
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

    detail::Field fields[32]{};
    std::size_t field_count=1;
    fields[0].data=bytes;
    for (std::size_t index=0;index<content_length;++index) {
        if (bytes[index]!=' ') continue;
        if (field_count>=32) return ParseResult{ParseError::field_count,field_count};
        fields[field_count-1].size=bytes+index-fields[field_count-1].data;
        fields[field_count].data=bytes+index+1;
        ++field_count;
    }
    fields[field_count-1].size=bytes+content_length-fields[field_count-1].data;
    const bool exec1=detail::equals(fields[0],"EU4PEACE_EXEC1");
    const bool exec2=detail::equals(fields[0],"EU4PEACE_EXEC2");
    const bool exec3=detail::equals(fields[0],"EU4PEACE_EXEC3");
    const bool exec4=detail::equals(fields[0],"EU4PEACE_EXEC4");
    const bool exec5=detail::equals(fields[0],"EU4PEACE_EXEC5");
    const bool exec6=detail::equals(fields[0],"EU4PEACE_EXEC6");
    const bool exec7=detail::equals(fields[0],"EU4PEACE_EXEC7");
    const bool exec8=detail::equals(fields[0],"EU4PEACE_EXEC8");
    const bool exec9=detail::equals(fields[0],"EU4PEACE_EXEC9");
    const bool exec10=detail::equals(fields[0],"EU4PEACE_EXEC10");
    if (!exec1 && !exec2 && !exec3 && !exec4 && !exec5 && !exec6 && !exec7
        && !exec8 && !exec9 && !exec10)
        return ParseResult{ParseError::invalid_prefix,0};
    const std::size_t expected_fields=exec1?13u
        :(exec10?32u:(exec9?23u:(exec8?21u:((exec6||exec7)?17u:((exec4||exec5)?15u:14u)))));
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
    const bool trade_power=detail::equals(fields[3],"transfer_trade_power");
    const bool concede_defeat=detail::equals(fields[3],"concede_defeat");
    const bool annul_treaties=detail::equals(fields[3],"annul_treaties");
    const bool humiliate_rival=detail::equals(fields[3],"humiliate_rival");
    const bool show_strength=detail::equals(fields[3],"show_strength");
    const bool force_religion=detail::equals(fields[3],"force_religion");
    const bool return_core=detail::equals(fields[3],"return_core");
    const bool revoke_core=detail::equals(fields[3],"revoke_core");
    const bool release_subject=detail::equals(fields[3],"release_subject");
    const bool transfer_subject=detail::equals(fields[3],"transfer_subject");
    const bool release_nation=detail::equals(fields[3],"release_nation");
    const bool force_vassalization=detail::equals(fields[3],"force_vassalization");
    const bool form_personal_union=detail::equals(fields[3],"form_personal_union");
    const bool grant_independence=detail::equals(fields[3],"grant_independence");
    const bool full_annexation=detail::equals(fields[3],"full_annexation");
    const bool action_known=white || money || province || reparations
        || trade_power || concede_defeat || annul_treaties || humiliate_rival
        || show_strength || force_religion || return_core || revoke_core
        || release_subject || transfer_subject || release_nation
        || force_vassalization || form_personal_union || grant_independence
        || full_annexation;
    const bool action_allowed=(exec1 && (white || money || province))
        || (exec2 && (money || province || reparations))
        || ((exec3 || exec4) && (money || province || reparations || trade_power));
    const bool exec5_action_allowed=exec5
        && (money || province || reparations || trade_power || concede_defeat);
    const bool exec6_action_allowed=exec6
        && (money || province || reparations || trade_power || concede_defeat
            || annul_treaties);
    const bool exec7_action_allowed=exec7
        && (money || province || reparations || trade_power || concede_defeat
            || annul_treaties || humiliate_rival || show_strength
            || force_religion);
    const bool exec8_action_allowed=exec8
        && (money || province || reparations || trade_power || concede_defeat
            || annul_treaties || humiliate_rival || show_strength
            || force_religion || return_core || revoke_core);
    const bool exec9_action_allowed=exec9
        && (money || province || reparations || trade_power || concede_defeat
            || annul_treaties || humiliate_rival || show_strength
            || force_religion || return_core || revoke_core
            || release_subject || transfer_subject);
    const bool exec10_action_allowed=exec10 && action_known && !white;
    if (!action_known || (!action_allowed && !exec5_action_allowed
                           && !exec6_action_allowed && !exec7_action_allowed
                           && !exec8_action_allowed && !exec9_action_allowed
                           && !exec10_action_allowed)
        || !detail::copy_field(output.action_id,sizeof(output.action_id),fields[3]))
        return ParseResult{ParseError::invalid_action,3};
    output.white_peace=white;
    output.demand_ducats=money;
    output.cede_province=province;
    output.war_reparations=reparations;
    output.transfer_trade_power=trade_power;
    output.concede_defeat=concede_defeat;
    output.annul_treaties=annul_treaties;
    output.humiliate_rival=humiliate_rival;
    output.show_strength=show_strength;
    output.force_religion=force_religion;
    output.return_core=return_core;
    output.revoke_core=revoke_core;
    output.release_subject=release_subject;
    output.transfer_subject=transfer_subject;
    output.release_nation=release_nation;
    output.force_vassalization=force_vassalization;
    output.form_personal_union=form_personal_union;
    output.grant_independence=grant_independence;
    output.full_annexation=full_annexation;

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
    bool mask_trade_power=false;
    bool mask_concede_defeat=false;
    bool mask_annul_treaties=false;
    bool mask_humiliate_rival=false;
    bool mask_show_strength=false;
    bool mask_force_religion=false;
    bool mask_return_core=false;
    bool mask_revoke_core=false;
    const bool subject_terms_version=exec9;
    char complete_mask[19]{};
    if (!detail::parse_term_mask(fields[13],complete_mask,mask_money,
            mask_province,mask_reparations,mask_trade_power,
            mask_concede_defeat,mask_annul_treaties,mask_humiliate_rival,
        mask_show_strength,mask_force_religion,mask_return_core,
        mask_revoke_core,exec3||exec4,exec5,exec6,exec7,exec8,
        subject_terms_version,exec10))
        return ParseResult{ParseError::invalid_term_mask,13};
    if (exec10) std::memcpy(output.country_term_mask,complete_mask,sizeof(complete_mask));
    std::size_t legacy_used=0;
    for (const char* bit=complete_mask;*bit;++bit)
        if (detail::term_mask_rank(*bit)<13) output.term_mask[legacy_used++]=*bit;
    output.term_mask[legacy_used]=0;
    const bool mask_release_subject=std::strchr(complete_mask,'l')!=nullptr;
    const bool mask_transfer_subject=std::strchr(complete_mask,'x')!=nullptr;
    output.selected_reparations=mask_reparations;
    output.selected_trade_power=mask_trade_power;
    output.selected_concede_defeat=mask_concede_defeat;
    output.selected_annul_treaties=mask_annul_treaties;
    output.selected_humiliate_rival=mask_humiliate_rival;
    output.selected_show_strength=mask_show_strength;
    output.selected_force_religion=mask_force_religion;
    output.selected_return_core=mask_return_core;
    output.selected_revoke_core=mask_revoke_core;
    output.selected_release_subject=mask_release_subject;
    output.selected_transfer_subject=mask_transfer_subject;

    if (mask_trade_power) {
        derive_trade_power_participants(output);
        if (exec4 || exec5 || exec6 || exec7 || exec8 || exec9 || exec10) {
            if (!detail::valid_canonical_tag(fields[14])
                || !detail::copy_field(output.trade_power_source,
                    sizeof(output.trade_power_source),fields[14]))
                return ParseResult{ParseError::invalid_trade_power_source,14};
            if (std::memcmp(output.trade_power_source,
                    output.trade_power_beneficiary,
                    sizeof(output.trade_power_source))==0)
                return ParseResult{ParseError::invalid_combination,14};
        }
    } else if ((exec5 || exec6 || exec7 || exec8 || exec9 || exec10)
        && !detail::equals(fields[14],"-")) {
        // Source and beneficiary are meaningful only for a selected T term;
        // EXEC5 still carries the fixed fifteenth field and uses '-' here.
        return ParseResult{ParseError::invalid_trade_power_source,14};
    }

    if (exec6 || ((exec7 || exec8 || exec9 || exec10) && mask_annul_treaties)) {
        if (!detail::valid_canonical_tag(fields[15])
            || !detail::copy_field(output.annul_country,
                sizeof(output.annul_country),fields[15]))
            return ParseResult{ParseError::invalid_annul_country,15};
        if (!detail::parse_annul_partners(fields[16],
                detail::Field{output.annul_country,3},output.annul_partners,
                output.annul_partner_count))
            return ParseResult{ParseError::invalid_annul_partners,16};
    } else if (exec7 || exec8 || exec9 || exec10) {
        // EXEC7 retains the fixed EXEC6 field count, but A is optional.
        // Absent A must carry placeholders, as QUERY13 and the public
        // serializer do; do not fabricate unrelated treaty endpoints.
        if (!detail::equals(fields[15],"-"))
            return ParseResult{ParseError::invalid_annul_country,15};
        if (!detail::equals(fields[16],"-"))
            return ParseResult{ParseError::invalid_annul_partners,16};
    }

    if (exec8 || exec9 || exec10) {
        if (mask_return_core) {
            if (!detail::parse_province_ids(fields[17],output.return_core_ids,
                    output.return_core_count))
                return ParseResult{ParseError::invalid_return_core_ids,17};
            if (!detail::valid_canonical_tag(fields[18])
                || !detail::copy_field(output.return_core_owner,
                    sizeof(output.return_core_owner),fields[18]))
                return ParseResult{ParseError::invalid_return_core_owner,18};
        } else if (!detail::equals(fields[17],"-")) {
            return ParseResult{ParseError::invalid_return_core_ids,17};
        } else if (!detail::equals(fields[18],"-")) {
            return ParseResult{ParseError::invalid_return_core_owner,18};
        }
        if (mask_revoke_core) {
            if (!detail::parse_province_ids(fields[19],output.revoke_core_ids,
                    output.revoke_core_count))
                return ParseResult{ParseError::invalid_revoke_core_ids,19};
            if (!detail::valid_canonical_tag(fields[20])
                || !detail::copy_field(output.revoke_core_owner,
                    sizeof(output.revoke_core_owner),fields[20]))
                return ParseResult{ParseError::invalid_revoke_core_owner,20};
        } else if (!detail::equals(fields[19],"-")) {
            return ParseResult{ParseError::invalid_revoke_core_ids,19};
        } else if (!detail::equals(fields[20],"-")) {
            return ParseResult{ParseError::invalid_revoke_core_owner,20};
        }
    }

    if (exec9 || exec10) {
        if (mask_release_subject) {
            if (!detail::parse_subject_countries(fields[21],
                    output.release_subject_countries,output.release_subject_count))
                return ParseResult{ParseError::invalid_release_subject_countries,21};
            if (!output.release_subject_count)
                return ParseResult{ParseError::invalid_release_subject_countries,21};
        } else if (!detail::equals(fields[21],"-")) {
            return ParseResult{ParseError::invalid_release_subject_countries,21};
        }
        if (mask_transfer_subject) {
            if (!detail::parse_subject_countries(fields[22],
                    output.transfer_subject_countries,output.transfer_subject_count))
                return ParseResult{ParseError::invalid_transfer_subject_countries,22};
            if (!output.transfer_subject_count)
                return ParseResult{ParseError::invalid_transfer_subject_countries,22};
        } else if (!detail::equals(fields[22],"-")) {
            return ParseResult{ParseError::invalid_transfer_subject_countries,22};
        }
        for (std::size_t release_index=0;
             release_index<output.release_subject_count;++release_index)
            for (std::size_t transfer_index=0;
                 transfer_index<output.transfer_subject_count;++transfer_index)
                if (std::memcmp(output.release_subject_countries[release_index],
                        output.transfer_subject_countries[transfer_index],3)==0)
                    return ParseResult{ParseError::invalid_subject_overlap,22};
    }

    if (exec10) {
        output.selected_release_nation=std::strchr(complete_mask,'n')!=nullptr;
        output.selected_force_vassalization=std::strchr(complete_mask,'z')!=nullptr;
        output.selected_form_personal_union=std::strchr(complete_mask,'u')!=nullptr;
        output.selected_grant_independence=std::strchr(complete_mask,'i')!=nullptr;
        output.selected_full_annexation=std::strchr(complete_mask,'e')!=nullptr;
        char* destinations[]={output.release_nation_country,output.release_nation_source,
            output.vassal_country,output.union_country,output.independence_country,
            output.annex_country,output.vassal_beneficiary,output.union_beneficiary,
            output.annex_beneficiary};
        const bool selected[]={output.selected_release_nation,output.selected_release_nation,
            output.selected_force_vassalization,output.selected_form_personal_union,
            output.selected_grant_independence,output.selected_full_annexation,
            output.selected_force_vassalization,output.selected_form_personal_union,
            output.selected_full_annexation};
        for (unsigned index=0;index<9;++index) {
            const auto& field=fields[23u+index];
            if (selected[index]) {
                if (!detail::valid_canonical_tag(field)
                    || !detail::copy_field(destinations[index],4,field))
                    return ParseResult{index==1?ParseError::invalid_country_term_source:
                        index>=6?ParseError::invalid_country_term_beneficiary:
                        ParseError::invalid_country_term_country,23u+index};
            } else if (!detail::equals(field,"-")) {
                return ParseResult{ParseError::invalid_combination,23u+index};
            }
        }
        if ((output.selected_release_nation && !std::strcmp(output.release_nation_country,
                output.release_nation_source))
            || (output.selected_force_vassalization && !std::strcmp(output.vassal_country,
                output.vassal_beneficiary))
            || (output.selected_form_personal_union && !std::strcmp(output.union_country,
                output.union_beneficiary))
            || (output.selected_full_annexation && !std::strcmp(output.annex_country,
                output.annex_beneficiary)))
            return ParseResult{ParseError::invalid_combination,23};
        if (output.selected_grant_independence && std::strcmp(output.independence_country,
                demand?output.recipient:output.actor))
            return ParseResult{ParseError::invalid_country_term_country,27};
    }

    // The mask is an exact summary of the parsed payload.  EXEC2 requires r,
    // EXEC3 requires t, and m/p must agree with the corresponding fields.
    if (mask_money!=output.selected_amount
        || mask_province!=output.selected_provinces)
        return ParseResult{ParseError::invalid_combination,13};
    // The primary action must name one of the selected terms.  White peace
    // was rejected above, so these are the complete versioned action sets.
    const bool primary_term_selected=(money && mask_money)
        || (province && mask_province)
        || (reparations && mask_reparations)
        || (trade_power && mask_trade_power)
        || (concede_defeat && mask_concede_defeat)
        || (annul_treaties && mask_annul_treaties)
        || (humiliate_rival && mask_humiliate_rival)
        || (show_strength && mask_show_strength)
        || (force_religion && mask_force_religion)
        || (return_core && mask_return_core)
        || (revoke_core && mask_revoke_core)
        || (release_subject && mask_release_subject)
        || (transfer_subject && mask_transfer_subject)
        || (release_nation && output.selected_release_nation)
        || (force_vassalization && output.selected_force_vassalization)
        || (form_personal_union && output.selected_form_personal_union)
        || (grant_independence && output.selected_grant_independence)
        || (full_annexation && output.selected_full_annexation);
    if (!primary_term_selected)
        return ParseResult{ParseError::invalid_combination,3};
    return ParseResult{ParseError::ok,0};
}

} // namespace bridge::peace_execution_wire
