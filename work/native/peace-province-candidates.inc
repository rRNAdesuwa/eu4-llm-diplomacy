// Bounded, read-only capture of native cede-province (peace term type 3)
// candidates.  This file deliberately does not construct a term, call the
// type-3 toggle slot, dispatch an offer, or invoke any peace business method.
// It is included by the native observer after the common read/base/line
// helpers and peace_query_country_pointer have been defined.

#include <windows.h>
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <cstdio>
#include <cstdarg>

static constexpr uintptr_t peace_province_offer_vtable_rva=0x1c578b8u;
static constexpr uintptr_t peace_province_type3_vtable_rva=0x1cd4ad8u;
static constexpr uint32_t peace_province_offer_type=0x165u;
static constexpr uint32_t peace_province_type3_id=0x2d25u;

static constexpr uintptr_t peace_province_game_global_rva=0x233fe58u;
static constexpr uintptr_t peace_province_array_begin_offset=0x1c90u;
static constexpr uintptr_t peace_province_array_end_offset=0x1c98u;
static constexpr uintptr_t peace_province_array_base_offset=0x1ca8u;
static constexpr uintptr_t peace_province_record_stride=0x2e10u;
static constexpr uintptr_t peace_province_record_id_offset=0x20u;
static constexpr uintptr_t peace_province_record_name_offset=0x28u;

static constexpr unsigned peace_province_max_candidates=512u;
static constexpr unsigned peace_province_max_requested=16u;
static constexpr unsigned peace_province_max_name_bytes=512u;
static constexpr size_t peace_province_json_capacity=800000u;

struct PeaceProvinceCandidate {
    uintptr_t term=0;
    uintptr_t province=0;
    int32_t province_id=-1;
    uint64_t beneficiary=0;
    char name_hex[1025]{};
    bool name_readable=false;
    bool name_truncated=false;
    bool selected=false;
    bool native_selectability_checked=false;
    int native_selectable=-1;
};

struct PeaceProvinceQueryData {
    // The large buffers are allocated only for an enabled query.  Keeping
    // candidate rows and the public JSON off the stack is intentional: the
    // native term vector is bounded, but its names can still be large.
    bool enabled=false;
    PeaceProvinceCandidate* candidates=nullptr;
    char* json=nullptr;
    size_t json_size=0;
    size_t json_capacity=0;
    bool json_complete=false;

    unsigned candidate_count=0;
    bool enumeration_complete=false;
    bool query_complete=false;
    // The native raw direction byte is 1 for the existing demand contract
    // and 0 for the explicit offer contract.  Retain the expected byte with
    // the capture so offer-direction candidates are not rejected as malformed.
    unsigned char expected_direction=1;
    unsigned char direction_raw=0;
    bool direction_verified=false;

    int32_t requested_ids[peace_province_max_requested]{};
    unsigned requested_count=0;
    uint64_t requested_beneficiary=0;
    char requested_beneficiary_tag[4]{};
    bool selection_requested=false;
    bool requested_candidates_found=false;

    bool toggle_called=false;
    unsigned toggle_call_count=0;
    bool parameters_matched=false;

    int32_t selected_ids[peace_province_max_candidates]{};
    unsigned selected_count=0;
    uint64_t selected_beneficiary=0;
    bool selection_copy_verified=false;
    bool selected_term_records_complete=false;

    const char* reason_code=nullptr;
    int selection_delta_raw=0;
    bool selection_delta_available=false;

    explicit PeaceProvinceQueryData(bool enable=false) noexcept : enabled(enable) {
        if (!enabled) return;
        candidates=static_cast<PeaceProvinceCandidate*>(
            HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,
                sizeof(PeaceProvinceCandidate)*peace_province_max_candidates));
        json=static_cast<char*>(HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,
            peace_province_json_capacity));
        json_capacity=json?peace_province_json_capacity:0;
        if (!candidates || !json) {
            if (candidates) HeapFree(GetProcessHeap(),0,candidates);
            if (json) HeapFree(GetProcessHeap(),0,json);
            candidates=nullptr;
            json=nullptr;
            json_capacity=0;
        }
    }

    PeaceProvinceQueryData(const PeaceProvinceQueryData&)=delete;
    PeaceProvinceQueryData& operator=(const PeaceProvinceQueryData&)=delete;
    PeaceProvinceQueryData(PeaceProvinceQueryData&&)=delete;
    PeaceProvinceQueryData& operator=(PeaceProvinceQueryData&&)=delete;

    ~PeaceProvinceQueryData() noexcept {
        if (candidates) HeapFree(GetProcessHeap(),0,candidates);
        if (json) HeapFree(GetProcessHeap(),0,json);
    }

    // This predicate intentionally reports allocation state only.  Native
    // contents are checked by the individual read functions.
    bool valid() const noexcept {
        return !enabled || (candidates!=nullptr && json!=nullptr
            && json_capacity==peace_province_json_capacity);
    }
};

struct PeaceProvinceArrayBounds {
    uintptr_t begin=0;
    uintptr_t end=0;
    uintptr_t base=0;
    uint64_t count=0;
    uintptr_t span_end=0;
};

static bool peace_province_tag(uint64_t handle,char (&tag)[4]) noexcept {
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

static bool peace_province_read_bounds(PeaceProvinceArrayBounds& output) noexcept {
    output=PeaceProvinceArrayBounds{};
    uintptr_t game=0;
    if (!read(base+peace_province_game_global_rva,game) || !game
        || !read(game+peace_province_array_begin_offset,output.begin)
        || !read(game+peace_province_array_end_offset,output.end)
        || !read(game+peace_province_array_base_offset,output.base)
        || output.end<output.begin
        || ((output.end-output.begin)%8u)!=0) return false;
    output.count=(output.end-output.begin)/8u;
    // Current EU4 data is far below this bound.  The bound prevents a stale
    // pointer pair from turning a malformed save into a large walk.
    if (output.count>1000000u || (output.count && !output.base)) return false;
    if (output.count>static_cast<uint64_t>(~static_cast<uintptr_t>(0))
            /peace_province_record_stride) return false;
    const uintptr_t span=static_cast<uintptr_t>(output.count)
        *peace_province_record_stride;
    if (output.base>static_cast<uintptr_t>(~static_cast<uintptr_t>(0))-span)
        return false;
    output.span_end=output.base+span;
    return true;
}

static bool peace_province_record_for_id(const PeaceProvinceArrayBounds& bounds,
    int32_t province_id,uintptr_t& record) noexcept {
    record=0;
    if (province_id<0 || static_cast<uint64_t>(province_id)>=bounds.count
        || !bounds.base) return false;
    const uintptr_t offset=static_cast<uintptr_t>(province_id)
        *peace_province_record_stride;
    if (offset>bounds.span_end-bounds.base) return false;
    record=bounds.base+offset;
    if (record<bounds.base || record>bounds.span_end
        || bounds.span_end-record<peace_province_record_stride) return false;
    int32_t stored_id=-1;
    return read(record+peace_province_record_id_offset,stored_id)
        && stored_id==province_id;
}

static bool peace_province_read_name(uintptr_t record,
    PeaceProvinceCandidate& output) noexcept {
    output.name_hex[0]=0;
    output.name_readable=false;
    output.name_truncated=false;
    uintptr_t owner=0;
    if (!read(record+peace_province_record_name_offset,owner) || !owner) return false;
    if (owner>static_cast<uintptr_t>(~static_cast<uintptr_t>(0))-0x10u) return false;
    const uintptr_t string_object=owner+0x10u;
    uint64_t size=0,capacity=0;
    if (!read(string_object+0x10u,size)
        || !read(string_object+0x18u,capacity)
        || capacity<size || (capacity<16u && size>15u)
        || size>0x1000000u || capacity>0x1000000u) return false;
    output.name_truncated=size>peace_province_max_name_bytes;
    const size_t bytes=size<peace_province_max_name_bytes
        ?static_cast<size_t>(size):peace_province_max_name_bytes;
    uintptr_t data=string_object;
    if (capacity>=16u) {
        if (!read(string_object,data) || !data) return false;
    }
    unsigned char raw[peace_province_max_name_bytes]{};
    SIZE_T copied=0;
    if (bytes && (!ReadProcessMemory(GetCurrentProcess(),
            reinterpret_cast<void*>(data),raw,bytes,&copied)
            || copied!=bytes)) return false;
    static constexpr char hex[]="0123456789abcdef";
    for (size_t i=0;i<bytes;++i) {
        output.name_hex[i*2]=hex[raw[i]>>4];
        output.name_hex[i*2+1]=hex[raw[i]&0x0fu];
    }
    output.name_hex[bytes*2]=0;
    output.name_readable=true;
    return true;
}

static bool peace_province_offer_identity(uintptr_t offer,
    unsigned char& direction) noexcept {
    uintptr_t vtable=0,owner=0;
    uint32_t discriminator=0;
    return offer!=0 && read(offer,vtable) && vtable==base+peace_province_offer_vtable_rva
        && read(offer+8u,discriminator) && discriminator==peace_province_offer_type
        && read(offer+0xe8u,owner) && owner==offer
        && read(offer+0x20u,direction);
}

static bool peace_province_offer_terms(uintptr_t offer,uintptr_t& begin,
    unsigned& count,bool& complete) noexcept {
    begin=0;
    count=0;
    complete=true;
    uintptr_t end=0,capacity=0;
    if (!offer || !read(offer+0x88u,begin) || !read(offer+0x90u,end)
        || !read(offer+0x98u,capacity) || end<begin || capacity<end
        || ((end-begin)%8u)!=0 || (end!=begin && !begin)) return false;
    const uint64_t native_count=(end-begin)/8u;
    if (native_count>peace_province_max_candidates) complete=false;
    count=static_cast<unsigned>(native_count>peace_province_max_candidates
        ?peace_province_max_candidates:native_count);
    return true;
}

static bool peace_province_read_term(uintptr_t term,
    const PeaceProvinceArrayBounds& bounds,PeaceProvinceCandidate& output) noexcept {
    output=PeaceProvinceCandidate{};
    output.term=term;
    uintptr_t vtable=0,record=0;
    unsigned char selected=0;
    uint64_t beneficiary=0;
    if (!term || !read(term,vtable) || vtable!=base+peace_province_type3_vtable_rva
        || !read(term+0x20u,selected) || selected>1u
        || !read(term+0x30u,beneficiary) || !beneficiary
        || !peace_query_country_pointer(beneficiary,record)) return false;
    // The country pointer above is only the canonical-handle check.  The
    // province record is independently read from term+0x38 below.
    (void)record;
    uintptr_t province=0;
    if (!read(term+0x38u,province) || !province) return false;
    int32_t province_id=-1;
    if (!read(province+peace_province_record_id_offset,province_id)) return false;
    uintptr_t expected_record=0;
    if (!peace_province_record_for_id(bounds,province_id,expected_record)
        || expected_record!=province) return false;
    char tag[4]{};
    if (!peace_province_tag(beneficiary,tag)) return false;
    output.province=province;
    output.province_id=province_id;
    output.beneficiary=beneficiary;
    output.selected=selected!=0;
    // Name failure is represented in the row; the caller decides whether it
    // makes the complete enumeration false.
    peace_province_read_name(province,output);
    (void)tag;
    return true;
}

static bool peace_province_same_ids(const int32_t* left,unsigned left_count,
    const int32_t* right,unsigned right_count) noexcept {
    if (left_count!=right_count || left_count>peace_province_max_candidates
        || right_count>peace_province_max_candidates) return false;
    for (unsigned i=0;i<left_count;++i) {
        bool found=false;
        for (unsigned j=0;j<right_count;++j)
            if (left[i]==right[j]) { found=true; break; }
        if (!found) return false;
    }
    return true;
}

static bool peace_province_requested(const PeaceProvinceQueryData& data) noexcept {
    return data.selection_requested || data.requested_count!=0
        || data.requested_beneficiary!=0;
}

static bool peace_province_requested_found(const PeaceProvinceQueryData& data) noexcept {
    if (!data.requested_count || data.requested_count>peace_province_max_requested
        || data.candidate_count>peace_province_max_candidates) return false;
    for (unsigned i=0;i<data.requested_count;++i) {
        bool found=false;
        for (unsigned j=0;j<data.candidate_count;++j) {
            if (data.candidates[j].province_id==data.requested_ids[i]
                && (!data.requested_beneficiary
                    || data.candidates[j].beneficiary==data.requested_beneficiary)) {
                found=true;
                break;
            }
        }
        if (!found) return false;
    }
    return true;
}

static bool peace_province_selected_matches_request(
    const PeaceProvinceQueryData& data) noexcept {
    if (!peace_province_requested(data) || !data.requested_count
        || !data.requested_candidates_found
        || !data.selected_term_records_complete) return false;
    if (!peace_province_same_ids(data.requested_ids,data.requested_count,
            data.selected_ids,data.selected_count)) return false;
    return !data.requested_beneficiary
        || data.selected_beneficiary==data.requested_beneficiary;
}

static void peace_province_reset_capture(PeaceProvinceQueryData& data) noexcept {
    const bool enabled=data.enabled;
    PeaceProvinceCandidate* candidates=data.candidates;
    char* json=data.json;
    const size_t capacity=data.json_capacity;
    int32_t requested[peace_province_max_requested]{};
    const unsigned requested_count=data.requested_count;
    const uint64_t requested_beneficiary=data.requested_beneficiary;
    char requested_tag[4]{};
    const bool requested_flag=data.selection_requested;
    if (requested_count<=peace_province_max_requested)
        memcpy(requested,data.requested_ids,sizeof(requested));
    memcpy(requested_tag,data.requested_beneficiary_tag,sizeof(requested_tag));
    data.json_size=0;
    data.json_complete=false;
    data.candidate_count=0;
    data.enumeration_complete=false;
    data.query_complete=false;
    data.direction_raw=0;
    data.direction_verified=false;
    data.requested_candidates_found=false;
    data.toggle_called=false;
    data.toggle_call_count=0;
    data.parameters_matched=false;
    data.selected_count=0;
    data.selected_beneficiary=0;
    data.selection_copy_verified=false;
    data.selected_term_records_complete=false;
    data.reason_code=nullptr;
    data.selection_delta_raw=0;
    data.selection_delta_available=false;
    data.enabled=enabled;
    data.candidates=candidates;
    data.json=json;
    data.json_capacity=capacity;
    memcpy(data.requested_ids,requested,sizeof(requested));
    data.requested_count=requested_count;
    data.requested_beneficiary=requested_beneficiary;
    memcpy(data.requested_beneficiary_tag,requested_tag,sizeof(requested_tag));
    data.selection_requested=requested_flag;
    if (requested_count>peace_province_max_requested) {
        data.requested_count=0;
        data.enumeration_complete=false;
    }
    if (data.candidates) {
        for (unsigned i=0;i<peace_province_max_candidates;++i)
            data.candidates[i]=PeaceProvinceCandidate{};
    }
}

static void peace_province_update_request_state(PeaceProvinceQueryData& data) noexcept {
    data.requested_candidates_found=peace_province_requested_found(data);
    data.parameters_matched=peace_province_selected_matches_request(data);
    // A prior read/selection error is more precise than a later derived
    // state.  In particular, action-copy readback must not erase an
    // UNAVAILABLE or MISMATCH reason established by the source path.
    if (data.reason_code) return;
    if (peace_province_requested(data) && data.requested_count
        && !data.requested_candidates_found) {
        data.reason_code="NATIVE_PEACE_PROVINCE_CANDIDATE_ABSENT";
        return;
    }
    // Enumeration runs before the toggle and therefore cannot diagnose a
    // mismatch: the native offer still contains its initial selection.  The
    // copy flag marks the final source/action comparison as complete.
    const bool comparison_complete=data.selected_term_records_complete
        && data.selection_copy_verified;
    if (data.selection_requested && data.requested_count
        && data.requested_candidates_found && comparison_complete
        && !data.parameters_matched)
        data.reason_code="NATIVE_PEACE_PROVINCE_SELECTION_MISMATCH";
}

static bool peace_province_query_enumerate(void* offer_object,
    PeaceProvinceQueryData& data) noexcept {
    if (!data.enabled || !data.valid() || !offer_object) return false;
    peace_province_reset_capture(data);
    const uintptr_t offer=reinterpret_cast<uintptr_t>(offer_object);
    if (!peace_province_offer_identity(offer,data.direction_raw)) return false;
    data.direction_verified=data.direction_raw==data.expected_direction;
    uintptr_t terms=0;
    unsigned term_count=0;
    bool term_complete=true;
    if (!peace_province_offer_terms(offer,terms,term_count,term_complete)) return false;
    PeaceProvinceArrayBounds bounds{};
    if (!peace_province_read_bounds(bounds)) return false;
    data.query_complete=true;
    data.enumeration_complete=term_complete && data.direction_verified;
    bool selected_complete=true;
    for (unsigned i=0;i<term_count;++i) {
        uintptr_t term=0;
        if (!read(terms+static_cast<uintptr_t>(i)*8u,term) || !term) {
            data.enumeration_complete=false;
            continue;
        }
        uintptr_t vtable=0;
        if (!read(term,vtable)) {
            data.enumeration_complete=false;
            continue;
        }
        if (vtable!=base+peace_province_type3_vtable_rva) continue;
        if (data.candidate_count>=peace_province_max_candidates) {
            data.enumeration_complete=false;
            continue;
        }
        PeaceProvinceCandidate candidate{};
        if (!peace_province_read_term(term,bounds,candidate)) {
            data.enumeration_complete=false;
            selected_complete=false;
            continue;
        }
        bool duplicate=false;
        for (unsigned j=0;j<data.candidate_count;++j)
            duplicate=duplicate || data.candidates[j].province_id==candidate.province_id;
        if (duplicate) {
            data.enumeration_complete=false;
            selected_complete=false;
            continue;
        }
        if (!candidate.name_readable) data.enumeration_complete=false;
        if (candidate.selected) {
            if (data.selected_count>=peace_province_max_candidates) {
                selected_complete=false;
                data.enumeration_complete=false;
            } else {
                data.selected_ids[data.selected_count++]=candidate.province_id;
                if (!data.selected_beneficiary)
                    data.selected_beneficiary=candidate.beneficiary;
                else if (data.selected_beneficiary!=candidate.beneficiary)
                    selected_complete=false;
            }
        }
        data.candidates[data.candidate_count++]=candidate;
    }
    data.selected_term_records_complete=selected_complete;
    peace_province_update_request_state(data);
    return true;
}

static bool peace_province_collect_selected(void* offer_object,
    int32_t (&ids)[peace_province_max_candidates],unsigned& selected_count,
    uint64_t& beneficiary,bool& complete,unsigned char& direction) noexcept {
    selected_count=0;
    beneficiary=0;
    complete=true;
    const uintptr_t offer=reinterpret_cast<uintptr_t>(offer_object);
    if (!peace_province_offer_identity(offer,direction)) return false;
    uintptr_t terms=0;
    unsigned term_count=0;
    bool term_complete=true;
    if (!peace_province_offer_terms(offer,terms,term_count,term_complete)) return false;
    PeaceProvinceArrayBounds bounds{};
    if (!peace_province_read_bounds(bounds)) return false;
    if (!term_complete) complete=false;
    for (unsigned i=0;i<term_count;++i) {
        uintptr_t term=0;
        unsigned char selected=0;
        uintptr_t vtable=0;
        if (!read(terms+static_cast<uintptr_t>(i)*8u,term) || !term
            || !read(term,vtable)) { complete=false; continue; }
        if (vtable!=base+peace_province_type3_vtable_rva) continue;
        if (!read(term+0x20u,selected) || selected>1u) {
            complete=false;
            continue;
        }
        if (!selected) continue;
        PeaceProvinceCandidate row{};
        if (!peace_province_read_term(term,bounds,row)) {
            complete=false;
            continue;
        }
        bool duplicate=false;
        for (unsigned j=0;j<selected_count;++j)
            duplicate=duplicate || ids[j]==row.province_id;
        if (duplicate || selected_count>=peace_province_max_candidates) {
            complete=false;
            continue;
        }
        ids[selected_count++]=row.province_id;
        if (!beneficiary) beneficiary=row.beneficiary;
        else if (beneficiary!=row.beneficiary) complete=false;
    }
    return true;
}

enum class PeaceProvinceSelectionRole { source, action_copy };

static bool peace_province_query_read_selection(void* offer_object,
    PeaceProvinceQueryData& data,PeaceProvinceSelectionRole role) noexcept {
    const bool copied=role==PeaceProvinceSelectionRole::action_copy;
    if (!data.enabled || !data.valid() || !offer_object) return false;
    int32_t ids[peace_province_max_candidates]{};
    unsigned count=0;
    uint64_t beneficiary=0;
    bool complete=false;
    unsigned char direction=0;
    if (!peace_province_collect_selected(offer_object,ids,count,beneficiary,
            complete,direction)) return false;
    data.direction_raw=direction;
    data.direction_verified=direction==data.expected_direction;
    if (!copied) {
        data.selected_count=count;
        data.selected_beneficiary=beneficiary;
        memcpy(data.selected_ids,ids,sizeof(data.selected_ids));
        data.selected_term_records_complete=complete;
        data.selection_copy_verified=false;
        // The source offer is authoritative for candidate selection.  Update
        // only the selected bit on already captured rows so name/beneficiary
        // fields remain the source enumeration's bounded snapshot.
        for (unsigned i=0;i<data.candidate_count;++i)
            data.candidates[i].selected=false;
        for (unsigned i=0;i<count;++i) {
            bool found=false;
            for (unsigned j=0;j<data.candidate_count;++j) {
                if (data.candidates[j].province_id==ids[i]
                    && data.candidates[j].beneficiary==beneficiary) {
                    data.candidates[j].selected=true;
                    found=true;
                    break;
                }
            }
            if (!found) data.selected_term_records_complete=false;
        }
    } else {
        data.selection_copy_verified=complete
            && data.selected_term_records_complete
            && peace_province_same_ids(data.selected_ids,data.selected_count,ids,count)
            && data.selected_beneficiary==beneficiary;
        data.selected_term_records_complete=data.selected_term_records_complete && complete;
    }
    peace_province_update_request_state(data);
    if (!complete && !data.reason_code)
        data.reason_code="NATIVE_PEACE_PROVINCE_SELECTION_UNAVAILABLE";
    else if (copied && !data.selection_copy_verified && !data.reason_code)
        data.reason_code="NATIVE_PEACE_PROVINCE_SELECTION_MISMATCH";
    return true;
}

static bool peace_province_json_append(char* output,size_t capacity,size_t& used,
    const char* text) noexcept {
    if (!output || !text) return false;
    const size_t length=strlen(text);
    if (used>capacity || length>=capacity-used) return false;
    memcpy(output+used,text,length);
    used+=length;
    output[used]=0;
    return true;
}

static bool peace_province_json_append_format(char* output,size_t capacity,
    size_t& used,const char* format,...) noexcept {
    if (!output || !format || used>=capacity) return false;
    va_list args;
    va_start(args,format);
    const int needed=vsnprintf(output+used,capacity-used,format,args);
    va_end(args);
    if (needed<0 || static_cast<size_t>(needed)>=capacity-used) return false;
    used+=static_cast<size_t>(needed);
    return true;
}

static bool peace_province_tag_from_handle(uint64_t handle,char (&tag)[4]) noexcept {
    return handle && peace_province_tag(handle,tag);
}

static bool peace_province_query_json(PeaceProvinceQueryData& data) noexcept {
    if (!data.enabled || !data.valid() || !data.json) return false;
    data.json[0]=0;
    data.json_size=0;
    data.json_complete=false;
    size_t used=0;
    if (!peace_province_json_append(data.json,data.json_capacity,used,"{\"query_complete\":")) return false;
    if (!peace_province_json_append(data.json,data.json_capacity,used,
            data.query_complete?"true":"false")) return false;
    if (!peace_province_json_append_format(data.json,data.json_capacity,used,
            ",\"candidate_enumeration_complete\":%s,\"candidate_count\":%u,\"candidates\":[",
            data.enumeration_complete?"true":"false",data.candidate_count)) return false;
    if (data.candidate_count>peace_province_max_candidates || !data.candidates) return false;
    for (unsigned i=0;i<data.candidate_count;++i) {
        const auto& candidate=data.candidates[i];
        char tag[4]{};
        if (!peace_province_tag_from_handle(candidate.beneficiary,tag)) return false;
        if (i && !peace_province_json_append(data.json,data.json_capacity,used,",")) return false;
        if (!peace_province_json_append_format(data.json,data.json_capacity,used,
                "{\"province_id\":%d,\"beneficiary\":\"%.3s\",\"selected\":%s,\"name_hex\":\"%s\",\"name_readable\":%s,\"name_truncated\":%s,\"native_selectability_checked\":%s,\"native_selectable\":%s}",
                candidate.province_id,tag,candidate.selected?"true":"false",
                candidate.name_hex,candidate.name_readable?"true":"false",
                candidate.name_truncated?"true":"false",
                candidate.native_selectability_checked?"true":"false",
                candidate.native_selectability_checked
                    ?(candidate.native_selectable?"true":"false"):"null")) return false;
    }
    if (!peace_province_json_append(data.json,data.json_capacity,used,"]")) return false;
    if (!peace_province_json_append_format(data.json,data.json_capacity,used,
            ",\"selection_requested\":%s,\"requested_province_ids\":[",
            peace_province_requested(data)?"true":"false")) return false;
    if (data.requested_count>peace_province_max_requested) return false;
    for (unsigned i=0;i<data.requested_count;++i) {
        if (i && !peace_province_json_append(data.json,data.json_capacity,used,",")) return false;
        if (!peace_province_json_append_format(data.json,data.json_capacity,used,"%d",
                data.requested_ids[i])) return false;
    }
    if (!peace_province_json_append(data.json,data.json_capacity,used,"]")) return false;
    char requested_tag[4]{};
    const bool requested_tag_ok=peace_province_tag_from_handle(
        data.requested_beneficiary,requested_tag)
        || (data.requested_beneficiary_tag[0]!=0
            && data.requested_beneficiary_tag[1]!=0
            && data.requested_beneficiary_tag[2]!=0);
    const char* requested_value=requested_tag_ok
        ?(requested_tag[0]?requested_tag:data.requested_beneficiary_tag):nullptr;
    if (!peace_province_json_append(data.json,data.json_capacity,used,",\"requested_beneficiary\":")) return false;
    if (requested_value) {
        if (!peace_province_json_append_format(data.json,data.json_capacity,used,
                "\"%.3s\"",requested_value)) return false;
    } else if (!peace_province_json_append(data.json,data.json_capacity,used,"null")) return false;
    if (!peace_province_json_append_format(data.json,data.json_capacity,used,
            ",\"requested_candidates_found\":%s,\"toggle_called\":%s,\"toggle_call_count\":%u,\"parameters_matched\":%s,\"selected_province_ids\":[",
            data.requested_candidates_found?"true":"false",
            data.toggle_called?"true":"false",data.toggle_call_count,
            data.parameters_matched?"true":"false")) return false;
    if (data.selected_count>peace_province_max_candidates) return false;
    for (unsigned i=0;i<data.selected_count;++i) {
        if (i && !peace_province_json_append(data.json,data.json_capacity,used,",")) return false;
        if (!peace_province_json_append_format(data.json,data.json_capacity,used,"%d",
                data.selected_ids[i])) return false;
    }
    if (!peace_province_json_append(data.json,data.json_capacity,used,"]")) return false;
    char selected_tag[4]{};
    const bool selected_tag_ok=peace_province_tag_from_handle(
        data.selected_beneficiary,selected_tag);
    if (!peace_province_json_append(data.json,data.json_capacity,used,",\"selected_beneficiary\":")) return false;
    if (selected_tag_ok) {
        if (!peace_province_json_append_format(data.json,data.json_capacity,used,
                "\"%.3s\"",selected_tag)) return false;
    } else if (!peace_province_json_append(data.json,data.json_capacity,used,"null")) return false;
    if (!peace_province_json_append_format(data.json,data.json_capacity,used,
            ",\"selection_copy_verified\":%s,\"selected_term_records_complete\":%s,\"direction\":\"%s\",\"direction_raw\":%u,\"direction_verified\":%s,\"reason_code\":",
            data.selection_copy_verified?"true":"false",
            data.selected_term_records_complete?"true":"false",
            data.direction_verified?(data.expected_direction==1u?"demand":"offer"):"unknown",
            static_cast<unsigned>(data.direction_raw),
            data.direction_verified?"true":"false")) return false;
    if (data.reason_code) {
        if (!peace_province_json_append_format(data.json,data.json_capacity,used,
                "\"%s\"",data.reason_code)) return false;
    } else if (!peace_province_json_append(data.json,data.json_capacity,used,"null")) return false;
    if (!peace_province_json_append(data.json,data.json_capacity,used,
            ",\"selection_delta_raw\":")) return false;
    if (data.selection_delta_available) {
        if (!peace_province_json_append_format(data.json,data.json_capacity,used,"%d",
                data.selection_delta_raw)) return false;
    } else if (!peace_province_json_append(data.json,data.json_capacity,used,"null")) return false;
    if (!peace_province_json_append(data.json,data.json_capacity,used,"}")) return false;
    data.json_size=used;
    data.json_complete=true;
    return true;
}

static void peace_province_query_private(const char* id,
    const PeaceProvinceQueryData& data) noexcept {
    if (!data.enabled || !data.candidates || data.candidate_count>peace_province_max_candidates)
        return;
    for (unsigned i=0;i<data.candidate_count;++i) {
        const auto& candidate=data.candidates[i];
        char tag[4]{};
        const bool tag_ok=peace_province_tag_from_handle(candidate.beneficiary,tag);
        char beneficiary_json[8]{};
        if (tag_ok) snprintf(beneficiary_json,sizeof(beneficiary_json),
            "\"%.3s\"",tag);
        else strcpy(beneficiary_json,"null");
        char message[1800]{};
        const int written=snprintf(message,sizeof(message),
            "{\"event\":\"native_peace_province_candidate_private\",\"private\":true,\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"index\":%u,\"candidate_index\":%u,\"term_pointer\":\"0x%llx\",\"province_pointer\":\"0x%llx\",\"province_id\":%d,\"beneficiary\":%s,\"beneficiary_tag\":%s,\"selected\":%s,\"name_readable\":%s,\"name_truncated\":%s,\"native_selectability_checked\":%s,\"native_selectable\":%s,\"complete\":%s}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),
            static_cast<unsigned long long>(observation_creation),id?id:"",i,i,
            static_cast<unsigned long long>(candidate.term),
            static_cast<unsigned long long>(candidate.province),candidate.province_id,
            beneficiary_json,beneficiary_json,candidate.selected?"true":"false",
            candidate.name_readable?"true":"false",candidate.name_truncated?"true":"false",
            candidate.native_selectability_checked?"true":"false",
            candidate.native_selectability_checked
                ?(candidate.native_selectable?"true":"false"):"null",
            candidate.name_readable?"true":"false");
        if (written>0 && static_cast<size_t>(written)<sizeof(message)) line(message);
    }
}
