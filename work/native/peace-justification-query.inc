// Native term justification/eligibility inspection on an already-owned
// CPeaceOffer.  This include is deliberately read-only: it never constructs,
// mutates, submits, or executes a peace offer.  Include it after
// peace-native-payload.inc so PeaceSerializedCapture and
// peace_capture_serialized_offer are available.

#include <cstddef>
#include <cstdint>
#include <cstdarg>
#include <cstdio>
#include <cstring>

struct PeaceJustificationTermRow {
    std::uint32_t index=0;
    std::uint32_t type_id=0;
    std::uint32_t bucket=0;
    bool selected=false;
    bool applicable=false;
    bool evaluated=false;
    bool justified=false;
    bool justified_known=false;
    std::int32_t province_id=0;
    bool province_id_present=false;
    char object_country[4]{};
    bool complete=false;
};

struct PeaceJustificationQueryResult {
    bool called=false;
    bool complete=false;
    std::uint8_t direction=0;
    std::uint32_t term_count=0;
    std::uint32_t unsupported_count=0;
    std::uint32_t row_count=0;
    PeaceJustificationTermRow terms[bridge::peace_payload::kMaxPeaceTerms]{};
};

namespace peace_justification_detail {

enum class CallbackAbi : std::uint8_t {
    offer_and_direction=0,
    offer_only=1,
};

struct CallbackSpec {
    std::uintptr_t vtable_rva;
    std::uint32_t type_id;
    std::uint32_t bucket;
    std::uintptr_t callback_rva;
    CallbackAbi abi;
};

// Nineteen public actions are represented by eighteen physical term vtables:
// full_annexation shares the cede-province term.  The +0x140 identities below
// are the only callback identities admitted by this helper.  The two one-arg
// callbacks are kept separate from the offer+direction ABI because their
// closed callers do not pass a direction byte.
inline constexpr CallbackSpec kCallbackSpecs[]={
    {0x1cd2190u,0x2d2bu,0x00u,0x99cd90u,CallbackAbi::offer_and_direction},
    {0x1cd4ad8u,0x2d25u,0x03u,0x99e6b0u,CallbackAbi::offer_and_direction},
    {0x1cd3a10u,0x30a0u,0x07u,0x99cd90u,CallbackAbi::offer_and_direction},
    {0x1cd38c8u,0x2e07u,0x08u,0x9b7010u,CallbackAbi::offer_only},
    {0x1cd2d20u,0x2d2du,0x0bu,0x99cd90u,CallbackAbi::offer_and_direction},
    {0x1cd2e68u,0x2d2eu,0x0eu,0x99cd90u,CallbackAbi::offer_and_direction},
    {0x1cd34e0u,0x30a3u,0x09u,0x99cd90u,CallbackAbi::offer_and_direction},
    {0x1cd3398u,0x2f20u,0x0au,0x99cd90u,CallbackAbi::offer_and_direction},
    {0x1cd45b0u,0x2d29u,0x15u,0x99cd90u,CallbackAbi::offer_and_direction},
    {0x1cd4988u,0x2e00u,0x05u,0x99e6b0u,CallbackAbi::offer_and_direction},
    {0x1cd3778u,0x2d26u,0x04u,0x99e6b0u,CallbackAbi::offer_and_direction},
    {0x1cd2940u,0x2d27u,0x13u,0x9c3160u,CallbackAbi::offer_only},
    {0x1cd3b58u,0x35f0u,0x14u,0x9ce500u,CallbackAbi::offer_only},
    {0x1cd3100u,0x2d28u,0x0fu,0x99cd90u,CallbackAbi::offer_and_direction},
    {0x1cd4d78u,0x2d2cu,0x01u,0x99cd90u,CallbackAbi::offer_and_direction},
    {0x1cd1a90u,0x3c05u,0x02u,0x99cd90u,CallbackAbi::offer_and_direction},
    {0x1cd3f38u,0x2d2au,0x1au,0x99cd90u,CallbackAbi::offer_and_direction},
    {0x1cd2a90u,0x2e4au,0x12u,0x99cd90u,CallbackAbi::offer_and_direction},
};

static const CallbackSpec* callback_spec(std::uintptr_t vtable_rva) noexcept {
    for (const CallbackSpec& spec: kCallbackSpecs)
        if (spec.vtable_rva==vtable_rva) return &spec;
    return nullptr;
}

static bool native_address(std::uintptr_t address) noexcept {
    // Keep the same image bound used by the existing serialized-payload
    // verifier.  This is only an address identity guard before an indirect
    // call; it is not a new executable scan.
    return address>=base && address<base+0x2465000u;
}

static bool canonical_tag_bytes(std::uint64_t handle,char (&tag)[4]) noexcept {
    if (!handle) return false;
    const unsigned char a=static_cast<unsigned char>(handle&0xffu);
    const unsigned char b=static_cast<unsigned char>((handle>>8)&0xffu);
    const unsigned char c=static_cast<unsigned char>((handle>>16)&0xffu);
    const auto canonical=[](unsigned char value) noexcept {
        return (value>='A' && value<='Z') || (value>='0' && value<='9');
    };
    if (!canonical(a) || !canonical(b) || !canonical(c)) return false;
    tag[0]=static_cast<char>(a);
    tag[1]=static_cast<char>(b);
    tag[2]=static_cast<char>(c);
    tag[3]=0;
    return true;
}

static bool country_tag_from_handle(std::uint64_t handle,char (&tag)[4]) noexcept {
    // A tag alone is not enough to identify a live country.  Reuse the
    // existing bounded country resolver, which validates the slot and the
    // record's identity before exposing a tag.
    std::uintptr_t country=0;
    if (!canonical_tag_bytes(handle,tag)
        || !peace_query_country_pointer(handle,country) || !country) {
        tag[0]=0;
        return false;
    }
    return true;
}

static bool term_record(std::uintptr_t term,std::int32_t& kind,
    std::uint64_t& auxiliary) noexcept {
    std::uintptr_t vtable=0,getter=0;
    if (!term || !read(term,vtable) || vtable<base
        || !read(vtable+0x78u,getter) || !native_address(getter)) return false;
    using Getter=void* (*)(void*,void*);
    alignas(8) unsigned char local[16]{};
    void* returned=reinterpret_cast<Getter>(getter)(reinterpret_cast<void*>(term),local);
    const std::uintptr_t address=reinterpret_cast<std::uintptr_t>(returned);
    if (!address) return false;
    if (address==reinterpret_cast<std::uintptr_t>(local)) {
        std::memcpy(&kind,local,sizeof(kind));
        std::memcpy(&auxiliary,local+8,sizeof(auxiliary));
        return true;
    }
    return read(address,kind) && read(address+8u,auxiliary);
}

static bool direct_term_context_ready(std::uintptr_t term,
    const CallbackSpec& spec,std::int32_t& kind,std::uint64_t& auxiliary) noexcept {
    std::uintptr_t vtable=0,method=0;
    std::uint64_t field10=0,field18=0;
    unsigned char selected=0;
    if (!read(term,vtable) || vtable!=base+spec.vtable_rva
        || !read(vtable+0x140u,method) || method!=base+spec.callback_rva
        || !read(term+0x10u,field10) || !read(term+0x18u,field18)
        || !field10 || !field18 || !read(term+0x20u,selected) || selected>1u
        || !term_record(term,kind,auxiliary)) return false;
    // 99e6b0 consumes the type-specific +0x30/+0x38/+0x40 context.  The
    // serialized capture already validates these fields for its three term
    // families; re-read the live words to make the call-time guard explicit.
    if (spec.callback_rva==0x99e6b0u) {
        std::uint64_t field30=0,nested=0;
        unsigned char flag40=0;
        if (!read(term+0x30u,field30) || !read(term+0x38u,nested)
            || !read(term+0x40u,flag40)) return false;
    } else if (spec.abi==CallbackAbi::offer_only) {
        // 9b7010/9c3160/9ce500 read the term's type-specific target word
        // while resolving their goal/context route.
        std::uint64_t field30=0;
        if (!read(term+0x30u,field30)) return false;
    }
    return true;
}

static bool call_callback(const CallbackSpec& spec,std::uintptr_t term,
    std::uint8_t direction,bool& value) noexcept {
    if (spec.abi==CallbackAbi::offer_and_direction) {
        using Gate=unsigned char (*)(void*,unsigned char);
        value=reinterpret_cast<Gate>(base+spec.callback_rva)(
            reinterpret_cast<void*>(term),direction)!=0;
    } else {
        using Gate=unsigned char (*)(void*);
        value=reinterpret_cast<Gate>(base+spec.callback_rva)(
            reinterpret_cast<void*>(term))!=0;
    }
    return true;
}

static bool term_equal_unchecked(const bridge::peace_payload::PeaceTermPayload& left,
    const bridge::peace_payload::PeaceTermPayload& right) noexcept {
    if (left.type_id!=right.type_id || left.bucket!=right.bucket
        || left.field10!=right.field10 || left.field18!=right.field18
        || left.field22!=right.field22 || left.extra30!=right.extra30
        || left.definition_name_size!=right.definition_name_size
        || left.nested_id!=right.nested_id || left.flag40!=right.flag40
        || left.gold_raw!=right.gold_raw || left.selected!=right.selected
        || left.nested_present!=right.nested_present
        || left.selected_index!=right.selected_index
        || left.complete!=right.complete) return false;
    if (left.definition_name_size>bridge::peace_payload::kMaxPeaceDefinitionNameBytes
        || right.definition_name_size>bridge::peace_payload::kMaxPeaceDefinitionNameBytes)
        return false;
    return std::memcmp(left.definition_name.data(),right.definition_name.data(),
        left.definition_name_size)==0;
}

static bool payload_equal_unchecked(
    const bridge::peace_payload::PeaceOfferPayload& left,
    const bridge::peace_payload::PeaceOfferPayload& right) noexcept {
    if (left.payer!=right.payer || left.claimant!=right.claimant
        || left.direction!=right.direction || left.flag1b9!=right.flag1b9
        || left.term_count!=right.term_count || left.complete!=right.complete)
        return false;
    for (std::size_t group=0;group<left.participants.size();++group) {
        if (left.participants[group].count!=right.participants[group].count
            || left.participants[group].count>bridge::peace_payload::kMaxPeaceParticipants)
            return false;
        for (std::uint32_t i=0;i<left.participants[group].count;++i)
            if (left.participants[group].values[i]!=right.participants[group].values[i])
                return false;
    }
    const std::uint32_t count=left.term_count<=bridge::peace_payload::kMaxPeaceTerms
        ?left.term_count:static_cast<std::uint32_t>(bridge::peace_payload::kMaxPeaceTerms);
    if (left.term_count>bridge::peace_payload::kMaxPeaceTerms
        || right.term_count>bridge::peace_payload::kMaxPeaceTerms) return false;
    for (std::uint32_t i=0;i<count;++i)
        if (!term_equal_unchecked(left.terms[i],right.terms[i])) return false;
    return true;
}

static void attach_known_object(const bridge::peace_payload::PeaceTermPayload& term,
    PeaceJustificationTermRow& row) noexcept {
    // Existing candidate/effect contracts prove these fields as packed
    // country handles.  Keep the per-family field choice explicit: some
    // families use the serialized +0x30 object and others use +0x22.
    if ((term.type_id==0x2d25u && term.bucket==3u)
        || (term.type_id==0x2e00u && term.bucket==5u)) {
        if (term.nested_present && term.nested_id<=0x7fffffffU) {
            row.province_id=static_cast<std::int32_t>(term.nested_id);
            row.province_id_present=true;
        }
        country_tag_from_handle(term.extra30,row.object_country);
    } else if (term.type_id==0x2d26u && term.bucket==4u) {
        if (term.nested_present && term.nested_id<=0x7fffffffU) {
            row.province_id=static_cast<std::int32_t>(term.nested_id);
            row.province_id_present=true;
        }
        country_tag_from_handle(term.field22,row.object_country);
    } else if ((term.type_id==0x2d28u && term.bucket==0x0fu)
        || (term.type_id==0x2d27u && term.bucket==0x13u)
        || (term.type_id==0x2d2eu && term.bucket==0x0eu)) {
        // Release Nation, Release Subject, and Annul Treaties expose their
        // target/partner country in the proven +0x30 handle.
        country_tag_from_handle(term.extra30,row.object_country);
    } else if ((term.type_id==0x2d2cu && term.bucket==1u)
        || (term.type_id==0x3c05u && term.bucket==2u)
        || (term.type_id==0x2d2au && term.bucket==0x1au)
        || (term.type_id==0x2e4au && term.bucket==0x12u)
        || (term.type_id==0x35f0u && term.bucket==0x14u)
        || (term.type_id==0x2e07u && term.bucket==8u)) {
        // Country candidate specs/effects bind these families through +0x22
        // (including Grant Independence's existing identity offset).
        country_tag_from_handle(term.field22,row.object_country);
    }
}

static void invalidate_rows(PeaceJustificationQueryResult& result) noexcept {
    for (std::uint32_t i=0;i<result.row_count;++i) {
        auto& row=result.terms[i];
        row.evaluated=false;
        row.justified=false;
        row.justified_known=false;
        row.complete=false;
    }
}

static bool append(char* output,size_t capacity,size_t& used,
    const char* format,...) noexcept {
    if (!output || !format || used>=capacity) return false;
    va_list args;
    va_start(args,format);
    const int written=std::vsnprintf(output+used,capacity-used,format,args);
    va_end(args);
    if (written<0 || static_cast<size_t>(written)>=capacity-used) return false;
    used+=static_cast<size_t>(written);
    return true;
}

} // namespace peace_justification_detail

static bool peace_justification_query(void* offer,
    const bridge::peace_payload::PeaceOfferPayload& payload,
    PeaceJustificationQueryResult& output) noexcept {
    using namespace bridge::peace_payload;
    using namespace peace_justification_detail;
    output=PeaceJustificationQueryResult{};
    output.term_count=payload.term_count;
    output.direction=payload.direction;
    // If the owned object cannot be captured, no term row was inspected; the
    // bounded input count therefore accounts for every omitted row.  This
    // keeps the raw contract self-consistent even on the failure path.
    output.unsupported_count=payload.term_count<=kMaxPeaceTerms
        ?payload.term_count:0u;
    if (!offer) return false;

    PeaceSerializedCapture before{};
    if (!peace_capture_serialized_offer(offer,before)) return false;
    output.called=true;
    output.term_count=payload.term_count;
    output.unsupported_count=0;
    const bool source_matches=before.owner_verified && before.structure_complete
        && before.payload.complete
        && payload_equal_unchecked(before.payload,payload)
        && payload.term_count<=kMaxPeaceTerms && payload.direction<=1u;

    const unsigned source_count=before.payload.term_count<=kMaxPeaceTerms
        ?before.payload.term_count:0u;
    for (unsigned i=0;i<source_count;++i) {
        const auto& term=before.payload.terms[i];
        const CallbackSpec* spec=callback_spec(before.term_vtables[i]-base);
        if (!spec) {
            // A term with no admitted vtable identity is omitted and counted.
            ++output.unsupported_count;
            continue;
        }
        if (output.row_count>=kMaxPeaceTerms) {
            ++output.unsupported_count;
            continue;
        }
        auto& row=output.terms[output.row_count++];
        row.index=i;
        row.type_id=term.type_id;
        row.bucket=term.bucket;
        row.selected=term.selected!=0;
        row.applicable=true;
        if (term.complete) attach_known_object(term,row);
        std::int32_t kind=0;
        std::uint64_t auxiliary=0;
        if (term.complete && source_matches
            && direct_term_context_ready(before.term_addresses[i],*spec,kind,auxiliary)) {
            bool value=false;
            if (call_callback(*spec,before.term_addresses[i],payload.direction,value)) {
                row.evaluated=true;
                row.justified=value;
                row.justified_known=true;
                row.complete=true;
            }
        }
    }

    PeaceSerializedCapture after{};
    const bool after_captured=peace_capture_serialized_offer(offer,after);
    const bool unchanged=after_captured && after.owner_verified
        && after.structure_complete && after.payload.complete
        && payload_equal_unchecked(before.payload,after.payload)
        && payload_equal_unchecked(after.payload,payload);
    if (!unchanged) invalidate_rows(output);

    bool rows_complete=true;
    for (std::uint32_t i=0;i<output.row_count;++i)
        rows_complete=rows_complete && output.terms[i].complete;
    output.complete=output.called && source_matches && unchanged
        && output.unsupported_count==0 && output.row_count==source_count
        && rows_complete;
    return output.complete;
}

static bool peace_justification_query_json(const PeaceJustificationQueryResult& value,
    char* output,size_t capacity) noexcept {
    using namespace peace_justification_detail;
    if (!output || !capacity) return false;
    output[0]=0;
    size_t used=0;
    const char* direction=value.direction==1u?"demand":value.direction==0u?"offer":nullptr;
    if (!append(output,capacity,used,"{\"called\":%s,\"complete\":%s,\"direction\":%s,\"term_count\":%u,\"unsupported_count\":%u,\"terms\":[",
        value.called?"true":"false",value.complete?"true":"false",
        direction? (value.direction==1u?"\"demand\"":"\"offer\"") : "null",
        value.term_count,value.unsupported_count)) return false;
    for (std::uint32_t i=0;i<value.row_count;++i) {
        const auto& row=value.terms[i];
        const char* justified=row.justified_known?(row.justified?"true":"false"):"null";
        char province[32]{};
        if (row.province_id_present) snprintf(province,sizeof(province),"%d",row.province_id);
        else snprintf(province,sizeof(province),"null");
        char country_json[8]{};
        if (row.object_country[0])
            snprintf(country_json,sizeof(country_json),"\"%.3s\"",row.object_country);
        else
            snprintf(country_json,sizeof(country_json),"null");
        if (!append(output,capacity,used,
            "%s{\"index\":%u,\"type_id\":%u,\"bucket\":%u,\"selected\":%s,\"applicable\":%s,\"evaluated\":%s,\"justified\":%s,\"province_id\":%s,\"object_country\":%s,\"complete\":%s}",
            i?",":"",row.index,row.type_id,row.bucket,row.selected?"true":"false",
            row.applicable?"true":"false",row.evaluated?"true":"false",justified,
            province,country_json,row.complete?"true":"false")) return false;
    }
    return append(output,capacity,used,"]}");
}

