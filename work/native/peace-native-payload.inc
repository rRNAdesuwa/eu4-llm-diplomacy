// Capture the fields written by CPeaceOffer::serialize (981500) and each
// whitelisted term serializer. This does not authorize or execute an offer.
#include "peace-payload.h"

struct PeaceSerializedCapture {
    bridge::peace_payload::PeaceOfferPayload payload{};
    uintptr_t term_addresses[bridge::peace_payload::kMaxPeaceTerms]{};
    uintptr_t term_vtables[bridge::peace_payload::kMaxPeaceTerms]{};
    unsigned unsupported_count=0;
    unsigned selected_count=0;
    bool owner_verified=false;
    bool structure_complete=false;
    bool fields_complete=false;
    bool selected_index_complete=false;
};

static bool peace_payload_span(uintptr_t object,uintptr_t offset,unsigned stride,
    unsigned maximum,uintptr_t& begin,unsigned& count) noexcept {
    uintptr_t end=0,capacity=0;
    if (!object || !read(object+offset,begin) || !read(object+offset+8,end)
        || !read(object+offset+16,capacity) || end<begin || capacity<end
        || (end-begin)%stride || (capacity-begin)%stride
        || (end-begin)/stride>maximum || (end!=begin && !begin)) return false;
    count=static_cast<unsigned>((end-begin)/stride);
    return true;
}

static bool peace_payload_definition_name(uintptr_t term,
    bridge::peace_payload::PeaceTermExtraKind kind,
    bridge::peace_payload::PeaceTermPayload& output) noexcept {
    using namespace bridge::peace_payload;
    uintptr_t definition=0,string_object=0,data=0;
    if (!read(term+0x30,definition) || !definition) return false;
    if (kind==PeaceTermExtraKind::definition_name30) string_object=definition+0x10;
    else {
        uintptr_t holder=0;
        if (!read(definition+0x10,holder) || !holder) return false;
        string_object=holder+0x138;
    }
    size_t size=0,capacity=0;
    if (!read(string_object+0x10,size) || !read(string_object+0x18,capacity)
        || capacity<size || (capacity<16 && size>15)) return false;
    data=string_object;
    if (capacity>=16 && (!read(string_object,data) || !data)) return false;
    // 1707cc0 serializes the C string through its first NUL, not capacity.
    // Read no further than the declared size and the configured name bound.
    const size_t maximum=size<kMaxPeaceDefinitionNameBytes?size:kMaxPeaceDefinitionNameBytes;
    for (size_t i=0;i<=maximum;++i) {
        uint8_t value=0;
        if (!read(data+i,value)) return false;
        if (!value) { output.definition_name_size=static_cast<uint32_t>(i); return true; }
        if (i==maximum) return false;
        output.definition_name[i]=value;
    }
    return false;
}

static bool peace_capture_serialized_offer(const void* object,
    PeaceSerializedCapture& capture) noexcept {
    using namespace bridge::peace_payload;
    capture=PeaceSerializedCapture{};
    const uintptr_t offer=reinterpret_cast<uintptr_t>(object);
    uintptr_t vtable=0,owner=0;
    uint32_t discriminator=0;
    auto& payload=capture.payload;
    if (!read(offer,vtable) || vtable!=base+0x1c578b8
        || !read(offer+8,discriminator) || discriminator!=0x165
        || !read(offer+0xe8,owner) || owner!=offer
        || !read(offer+0x10,payload.payer)
        || !read(offer+0x18,payload.claimant)
        || !read(offer+0x20,payload.direction)
        || !read(offer+0x1b9,payload.flag1b9)) return false;
    capture.owner_verified=true;
    constexpr unsigned participant_offsets[]={0x28,0x40,0x58,0x70};
    for (unsigned group=0;group<4;++group) {
        uintptr_t begin=0; unsigned count=0;
        if (!peace_payload_span(offer,participant_offsets[group],8,
            kMaxPeaceParticipants,begin,count)) return false;
        auto& values=payload.participants[group];
        values.count=count;
        for (unsigned i=0;i<count;++i) {
            uintptr_t country=0;
            if (!read(begin+static_cast<uintptr_t>(i)*8,values.values[i])
                || !peace_query_country_pointer(values.values[i],country)) return false;
        }
    }
    uintptr_t terms=0; unsigned term_count=0;
    if (!peace_payload_span(offer,0x88,8,kMaxPeaceTerms,terms,term_count)) return false;
    payload.term_count=term_count;
    bool fields_complete=true;
    for (unsigned i=0;i<term_count;++i) {
        uintptr_t address=0,table=0,serializer=0,wrapper=0;
        if (!read(terms+static_cast<uintptr_t>(i)*8,address) || !address
            || !read(address,table) || table<base || table>=base+0x2465000)
            return false;
        capture.term_addresses[i]=address;
        capture.term_vtables[i]=table;
        const auto* descriptor=peace_find_term_type(table-base);
        if (!descriptor) { ++capture.unsupported_count; fields_complete=false; continue; }
        if (!read(table+8,wrapper) || wrapper!=base+0xd2f280
            || !read(table+0x10,serializer)
            || serializer!=base+descriptor->serializer_rva) return false;
        auto& term=payload.terms[i];
        term.type_id=descriptor->type_id;
        term.bucket=descriptor->bucket;
        if (!read(address+0x10,term.field10) || !read(address+0x18,term.field18)
            || !read(address+0x22,term.field22) || !read(address+0x20,term.selected)
            || term.selected>1) return false;
        if (term.selected) ++capture.selected_count;
        switch (descriptor->extra_kind) {
        case PeaceTermExtraKind::base: break;
        case PeaceTermExtraKind::handle30:
            if (!read(address+0x30,term.extra30)) return false;
            break;
        case PeaceTermExtraKind::gold:
            if (!read(address+0x30,term.gold_raw)) return false;
            break;
        case PeaceTermExtraKind::nested38:
        case PeaceTermExtraKind::nested38flag40: {
            uintptr_t nested=0;
            if (!read(address+0x30,term.extra30) || !read(address+0x38,nested)) return false;
            term.nested_present=nested!=0;
            if (nested && !read(nested+0x20,term.nested_id)) return false;
            if (descriptor->extra_kind==PeaceTermExtraKind::nested38flag40
                && !read(address+0x40,term.flag40)) return false;
            break;
        }
        case PeaceTermExtraKind::definition_name30:
        case PeaceTermExtraKind::region_name30:
            if (!peace_payload_definition_name(address,descriptor->extra_kind,term)) {
                ++capture.unsupported_count; fields_complete=false; continue;
            }
            break;
        case PeaceTermExtraKind::unsupported:
            ++capture.unsupported_count; fields_complete=false; continue;
        }
        term.complete=true;
    }
    capture.structure_complete=true;
    capture.fields_complete=fields_complete;

    // 9762a0 and 980fe0 reconstruct a vector of typed pointer vectors at d0.
    // Record logical term indices; owned allocation addresses are discarded.
    uintptr_t buckets=0; unsigned bucket_count=0;
    if (!peace_payload_span(offer,0xd0,24,kPeaceBucketCount,buckets,bucket_count))
        return true;
    bool indices_complete=true;
    for (unsigned bucket=0;bucket<bucket_count;++bucket) {
        uintptr_t begin=0; unsigned count=0;
        if (!peace_payload_span(buckets+static_cast<uintptr_t>(bucket)*24,0,8,
            kMaxPeaceTerms,begin,count)) { indices_complete=false; break; }
        for (unsigned index=0;index<count;++index) {
            uintptr_t selected=0;
            if (!read(begin+static_cast<uintptr_t>(index)*8,selected) || !selected) {
                indices_complete=false; continue;
            }
            unsigned matching=term_count;
            for (unsigned item=0;item<term_count;++item)
                if (capture.term_addresses[item]==selected) {
                    if (matching!=term_count) indices_complete=false;
                    matching=item;
                }
            if (matching==term_count) { indices_complete=false; continue; }
            auto& term=payload.terms[matching];
            if (!term.complete || term.bucket!=bucket || !term.selected
                || term.selected_index!=kInvalidSelectedIndex) {
                indices_complete=false; continue;
            }
            term.selected_index=index;
        }
    }
    for (unsigned i=0;i<term_count;++i)
        if (payload.terms[i].selected
            && payload.terms[i].selected_index==kInvalidSelectedIndex) indices_complete=false;
    capture.selected_index_complete=indices_complete;
    payload.complete=fields_complete && indices_complete;
    if (payload.complete && !payload.valid()) payload.complete=false;
    return true;
}

static void peace_serialized_capture_private(const char* id,const char* stage,
    const PeaceSerializedCapture& capture) noexcept {
    for (unsigned i=0;i<capture.payload.term_count;++i) {
        const auto& term=capture.payload.terms[i];
        char definition_hex[257]{};
        constexpr char hex[]="0123456789abcdef";
        for (unsigned j=0;j<term.definition_name_size && j<128;++j) {
            definition_hex[j*2]=hex[term.definition_name[j]>>4];
            definition_hex[j*2+1]=hex[term.definition_name[j]&15];
        }
        char message[1500];
        snprintf(message,sizeof(message),
            "{\"event\":\"native_peace_payload_term_private\",\"private\":true,"
            "\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"stage\":\"%s\","
            "\"index\":%u,\"vtable_rva\":\"0x%llx\",\"type_id\":%u,\"bucket\":%u,"
            "\"field10\":\"0x%llx\",\"field18\":\"0x%llx\",\"field22\":\"0x%llx\","
            "\"extra30\":\"0x%llx\",\"nested_present\":%s,\"nested_id\":%u,"
            "\"gold_raw\":%d,\"flag40\":%u,\"definition_name_size\":%u,"
            "\"definition_name_hex\":\"%s\",\"selected\":%u,\"selected_index\":%u,\"complete\":%s}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),
            static_cast<unsigned long long>(observation_creation),id,stage,i,
            static_cast<unsigned long long>(capture.term_vtables[i]-base),term.type_id,term.bucket,
            static_cast<unsigned long long>(term.field10),static_cast<unsigned long long>(term.field18),
            static_cast<unsigned long long>(term.field22),static_cast<unsigned long long>(term.extra30),
            term.nested_present?"true":"false",term.nested_id,term.gold_raw,
            static_cast<unsigned>(term.flag40),
            term.definition_name_size,definition_hex,
            static_cast<unsigned>(term.selected),term.selected_index,term.complete?"true":"false");
        line(message);
    }
}

static void peace_serialized_capture_json(const PeaceSerializedCapture& source,
    const PeaceSerializedCapture& copied,const PeaceSerializedCapture& after,
    char* output,size_t capacity) noexcept {
    const bool complete=source.payload.complete && copied.payload.complete
        && after.payload.complete;
    snprintf(output,capacity,
        "{\"schema\":\"native_peace_serialized_fields_v1\",\"capture_available\":%s,"
        "\"serialized_fields_complete\":%s,\"source_copy_equal\":%s,"
        "\"serialized_fields_unchanged\":%s,\"source_owner_verified\":%s,"
        "\"action_owner_verified\":%s,\"term_count\":%u,\"selected_term_count\":%u,"
        "\"unsupported_term_count\":%u,\"selected_index_complete\":%s,"
        "\"authority_bound\":false}",
        source.structure_complete && copied.structure_complete && after.structure_complete?"true":"false",
        complete?"true":"false",complete?(source.payload==copied.payload?"true":"false"):"null",
        complete?(copied.payload==after.payload?"true":"false"):"null",
        source.owner_verified?"true":"false",copied.owner_verified?"true":"false",
        source.payload.term_count,source.selected_count,source.unsupported_count,
        source.selected_index_complete && copied.selected_index_complete && after.selected_index_complete?"true":"false");
}
