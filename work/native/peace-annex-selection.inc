// Bounded native full-annexation (cede-all-provinces) selection helper.
//
// The offer constructor is the source of truth for candidate terms.  This
// file deliberately does not synthesize a cede term, dispatch an offer, or
// call a peace business method other than the read-only 0x982050 all-province
// consistency predicate requested by the caller.  It is included after the
// common native readers, peace_payload_span, peace_query_country_pointer,
// peace_province_read_bounds, and peace_province_record_for_id helpers.

#include <windows.h>
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <cstdio>
#include <cstdarg>

static constexpr unsigned peace_annex_max_candidates=512u;
static constexpr size_t peace_annex_json_capacity=180000u;

// Cede/province terms are the native type-3 rows.  The bucket and the
// descriptor/recalculate slots are the values recovered from the existing
// province selection path.  +0x120 is intentionally not used here.
static constexpr uintptr_t peace_annex_type3_vtable_rva=0x1cd4ad8u;
static constexpr uint32_t peace_annex_type3_id=0x2d25u;
static constexpr uint32_t peace_annex_bucket=3u;
static constexpr uintptr_t peace_annex_descriptor_rva=0x99adb0u;
static constexpr uintptr_t peace_annex_recalculate_rva=0x9a8420u;

// The country record owns a bounded vector of province indices at +0x1338;
// its element count is the observed int32 at +0x1344.  Entries are province
// indices, not pointers.  A count above the helper capacity is reported as a
// bridge-capacity/incomplete condition and is never silently truncated into a
// partial selection.
static constexpr uintptr_t peace_annex_owned_begin_offset=0x1338u;
static constexpr uintptr_t peace_annex_owned_count_offset=0x1344u;
static constexpr uintptr_t peace_annex_owned_stride=sizeof(int32_t);
static constexpr unsigned peace_annex_owned_max=peace_annex_max_candidates;

static constexpr uintptr_t peace_annex_native_check_rva=0x982050u;
static constexpr uintptr_t peace_annex_owned_count_rva=0x301b20u;
// 0x982170 initializes the out-country word to the inline "---" handle
// (assembly stores 0x2d2d2d followed by a NUL), matching the established
// native candidate sentinel used by the other observer.
static constexpr uint64_t peace_annex_output_sentinel=0x2d2d2dull;

struct PeaceAnnexRequest {
    char country[4]{};       // country losing all of its provinces
    char beneficiary[4]{};  // claimant; zero means derive from the offer
    bool selection_requested=false;
};

static bool peace_annex_valid_tag(const char* tag) noexcept {
    if (!tag || strlen(tag)!=3u) return false;
    for (unsigned i=0;i<3u;++i) {
        const unsigned char value=static_cast<unsigned char>(tag[i]);
        if (!((value>='A' && value<='Z') || (value>='0' && value<='9'))) return false;
    }
    return true;
}

// The public operator supplies the loser and optionally an explicit claimant.
// A '-' claimant means “use the offer claimant”; selection_requested is kept
// separate so discovery never mutates a fresh offer.
static bool peace_annex_parse_request(const char* country,const char* beneficiary,
    bool selection_requested,PeaceAnnexRequest& request) noexcept {
    request=PeaceAnnexRequest{};
    if (!peace_annex_valid_tag(country)) return false;
    if (!beneficiary) return false;
    if (strcmp(beneficiary,"-")!=0 && !peace_annex_valid_tag(beneficiary)) return false;
    memcpy(request.country,country,sizeof(request.country));
    if (strcmp(beneficiary,"-")!=0) memcpy(request.beneficiary,beneficiary,4u);
    request.selection_requested=selection_requested;
    return true;
}

struct PeaceAnnexCandidate {
    uintptr_t term=0;
    uintptr_t province=0;
    int32_t province_id=-1;
    uint64_t payer=0;
    uint64_t claimant=0;
    uint64_t term_owner=0;       // term +0x22, original owner filter
    uint64_t province_owner=0;   // province +0x468, independent owner filter
    uint64_t owner=0;            // canonical owner used by the public row
    uint64_t beneficiary=0;      // term +0x30, claimant receiving the province
    char owner_tag[4]{};
    char beneficiary_tag[4]{};
    bool selected=false;
    bool owner_match=false;
    bool readcomplete=false;
};

struct PeaceAnnexQueryData {
    bool enabled=false;
    PeaceAnnexCandidate* candidates=nullptr;
    char* json=nullptr;
    size_t json_size=0;
    size_t json_capacity=0;

    uint64_t payer=0;
    uint64_t claimant=0;
    uint64_t target_country=0;
    uintptr_t target_country_record=0;
    uint64_t requested_beneficiary=0;
    char target_country_tag[4]{};
    char requested_beneficiary_tag[4]{};

    unsigned candidate_count=0;
    bool candidate_enumeration_complete=false;
    bool query_complete=false;
    bool capacity_exceeded=false;
    bool candidate_duplicates=false;

    int32_t owned_ids[peace_annex_owned_max]{};
    unsigned target_owned_count=0;
    bool owned_index_complete=false;
    bool owned_index_duplicates=false;
    bool native_owned_count_called=false;
    int32_t native_owned_count_raw=-1;
    bool native_owned_count_matches=false;

    bool selection_requested=false;
    unsigned candidate_match_count=0;
    bool candidate_matches_complete=false;
    bool requested_candidates_found=false;
    unsigned selected_term_count=0;
    bool selection_applied=false;
    bool source_selection_complete=false;
    bool action_copy_checked=false;
    bool action_copy_matched=false;
    bool selection_delta_available=false;
    int32_t selection_delta_raw=0;

    bool native_annex_check_called=false;
    bool native_annex_bool=false;
    bool native_output_country_present=false;
    uint64_t native_output_country_raw=0;
    char native_output_country_tag[4]{};

    const char* reason_code=nullptr;

    explicit PeaceAnnexQueryData(bool enable=false) noexcept : enabled(enable) {
        if (!enabled) return;
        candidates=static_cast<PeaceAnnexCandidate*>(HeapAlloc(GetProcessHeap(),
            HEAP_ZERO_MEMORY,sizeof(PeaceAnnexCandidate)*peace_annex_max_candidates));
        json=static_cast<char*>(HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,
            peace_annex_json_capacity));
        json_capacity=json?peace_annex_json_capacity:0u;
        if (!candidates || !json) {
            if (candidates) HeapFree(GetProcessHeap(),0,candidates);
            if (json) HeapFree(GetProcessHeap(),0,json);
            candidates=nullptr;
            json=nullptr;
            json_capacity=0u;
        }
    }
    PeaceAnnexQueryData(const PeaceAnnexQueryData&)=delete;
    PeaceAnnexQueryData& operator=(const PeaceAnnexQueryData&)=delete;
    ~PeaceAnnexQueryData() noexcept {
        if (candidates) HeapFree(GetProcessHeap(),0,candidates);
        if (json) HeapFree(GetProcessHeap(),0,json);
    }
    bool valid() const noexcept {
        return !enabled || (candidates && json
            && json_capacity==peace_annex_json_capacity);
    }
    bool complete() const noexcept {
        return query_complete && candidate_enumeration_complete
            && owned_index_complete && candidate_matches_complete
            && source_selection_complete
            && native_annex_check_called
            && (!selection_requested
                || (selection_applied && action_copy_checked && action_copy_matched));
    }
};

static bool peace_annex_tag_from_handle(uint64_t handle,char (&tag)[4]) noexcept {
    const unsigned char a=static_cast<unsigned char>(handle&0xffu);
    const unsigned char b=static_cast<unsigned char>((handle>>8u)&0xffu);
    const unsigned char c=static_cast<unsigned char>((handle>>16u)&0xffu);
    if (!((a>='A' && a<='Z') || (a>='0' && a<='9'))
        || !((b>='A' && b<='Z') || (b>='0' && b<='9'))
        || !((c>='A' && c<='Z') || (c>='0' && c<='9'))) return false;
    tag[0]=static_cast<char>(a); tag[1]=static_cast<char>(b);
    tag[2]=static_cast<char>(c); tag[3]=0;
    return true;
}

static bool peace_annex_offer_terms(uintptr_t offer,uintptr_t& begin,
    unsigned& count,bool& complete,bool& capacity_exceeded) noexcept {
    begin=0; count=0; complete=true; capacity_exceeded=false;
    uintptr_t end=0,capacity=0;
    if (!offer || !read(offer+0x88u,begin) || !read(offer+0x90u,end)
        || !read(offer+0x98u,capacity) || end<begin || capacity<end
        || ((end-begin)%8u)!=0u || ((capacity-begin)%8u)!=0u
        || (end!=begin && !begin)) return false;
    const uint64_t native_count=(end-begin)/8u;
    if (native_count>peace_annex_max_candidates) {
        complete=false;
        capacity_exceeded=true;
        count=peace_annex_max_candidates;
    } else count=static_cast<unsigned>(native_count);
    return true;
}

static bool peace_annex_read_owned_index(uint64_t country,
    PeaceAnnexQueryData& data,const PeaceProvinceArrayBounds& bounds) noexcept {
    data.target_country_record=0;
    uintptr_t record=0;
    if (!country || !peace_query_country_pointer(country,record)) return false;
    data.target_country_record=record;
    uintptr_t begin=0;
    int32_t count=-1;
    if (!read(record+peace_annex_owned_begin_offset,begin)
        || !read(record+peace_annex_owned_count_offset,count)
        || count<0) return false;
    if (static_cast<unsigned>(count)>peace_annex_owned_max) {
        data.capacity_exceeded=true;
        data.target_owned_count=static_cast<unsigned>(count);
        data.owned_index_complete=false;
        return true;
    }
    data.target_owned_count=static_cast<unsigned>(count);
    if (count!=0 && !begin) return false;
    bool complete=true;
    for (int32_t i=0;i<count;++i) {
        int32_t province_id=-1;
        const uintptr_t slot=begin+static_cast<uintptr_t>(i)*peace_annex_owned_stride;
        if (slot<begin || !read(slot,province_id) || province_id<0) {
            complete=false; continue;
        }
        uintptr_t province=0;
        if (!peace_province_record_for_id(bounds,province_id,province)) {
            complete=false; continue;
        }
        for (int32_t j=0;j<i;++j)
            if (data.owned_ids[j]==province_id) {
                data.owned_index_duplicates=true;
                complete=false;
            }
        data.owned_ids[i]=province_id;
    }
    data.owned_index_complete=complete;

    // 0x301b20 is the native owned-province count used by 0x982050.  It is
    // only a cross-check; the actual index above remains the selection source.
    using OwnedCount= int (*)(uintptr_t);
    const int native_count=reinterpret_cast<OwnedCount>(base+peace_annex_owned_count_rva)(record);
    data.native_owned_count_called=true;
    data.native_owned_count_raw=native_count;
    data.native_owned_count_matches=native_count>=0
        && native_count==count;
    if (!data.native_owned_count_matches) data.owned_index_complete=false;
    return true;
}

static bool peace_annex_read_term(uintptr_t term,
    const PeaceProvinceArrayBounds& bounds,uint64_t payer,uint64_t claimant,
    PeaceAnnexCandidate& output) noexcept {
    output=PeaceAnnexCandidate{};
    output.term=term;
    uintptr_t vtable=0,province=0,record=0;
    unsigned char selected=0;
    uint64_t field10=0,field18=0,field22=0,beneficiary=0;
    if (!term || !read(term,vtable) || vtable!=base+peace_annex_type3_vtable_rva
        || !read(term+0x10u,field10) || !read(term+0x18u,field18)
        || !read(term+0x22u,field22) || !read(term+0x30u,beneficiary)
        || !read(term+0x20u,selected) || selected>1u
        || !read(term+0x38u,province) || !province
        || field10!=payer || field18!=claimant
        || !peace_query_country_pointer(beneficiary,record)
        || !peace_annex_tag_from_handle(beneficiary,output.beneficiary_tag)) return false;
    int32_t province_id=-1;
    uintptr_t expected=0;
    uint64_t province_owner=0;
    if (!read(province+0x20u,province_id)
        || !peace_province_record_for_id(bounds,province_id,expected)
        || expected!=province
        || !read(province+0x468u,province_owner)) return false;

    uintptr_t ignored=0;
    const bool term_owner_ok=field22!=0
        && peace_query_country_pointer(field22,ignored);
    const bool province_owner_ok=province_owner!=0
        && peace_query_country_pointer(province_owner,ignored);
    if (!term_owner_ok && !province_owner_ok) return false;
    output.province=province;
    output.province_id=province_id;
    output.payer=field10;
    output.claimant=field18;
    output.term_owner=field22;
    output.province_owner=province_owner;
    output.owner=term_owner_ok?field22:province_owner;
    output.beneficiary=beneficiary;
    output.selected=selected!=0;
    if (!peace_annex_tag_from_handle(output.owner,output.owner_tag)) return false;
    // Either native owner field is sufficient to bind the candidate to the
    // losing country; the private row keeps both raw handles so a caller can
    // diagnose a disagreement without using the beneficiary as that filter.
    output.readcomplete=term_owner_ok || province_owner_ok;
    return true;
}

static void peace_annex_reset(PeaceAnnexQueryData& data) noexcept {
    const bool enabled=data.enabled;
    PeaceAnnexCandidate* candidates=data.candidates;
    char* json=data.json;
    const size_t capacity=data.json_capacity;
    data.json_size=0;
    data.payer=0; data.claimant=0; data.target_country=0;
    data.target_country_record=0; data.requested_beneficiary=0;
    memset(data.target_country_tag,0,sizeof(data.target_country_tag));
    memset(data.requested_beneficiary_tag,0,sizeof(data.requested_beneficiary_tag));
    data.candidate_count=0; data.candidate_enumeration_complete=false;
    data.query_complete=false; data.capacity_exceeded=false;
    data.candidate_duplicates=false;
    memset(data.owned_ids,0,sizeof(data.owned_ids));
    data.target_owned_count=0; data.owned_index_complete=false;
    data.owned_index_duplicates=false; data.native_owned_count_called=false;
    data.native_owned_count_raw=-1; data.native_owned_count_matches=false;
    data.selection_requested=false; data.candidate_match_count=0;
    data.candidate_matches_complete=false; data.requested_candidates_found=false;
    data.selected_term_count=0; data.selection_applied=false;
    data.source_selection_complete=false; data.action_copy_checked=false;
    data.action_copy_matched=false; data.selection_delta_available=false;
    data.selection_delta_raw=0; data.native_annex_check_called=false;
    data.native_annex_bool=false; data.native_output_country_present=false;
    data.native_output_country_raw=0;
    memset(data.native_output_country_tag,0,sizeof(data.native_output_country_tag));
    data.reason_code=nullptr;
    data.enabled=enabled;
    data.candidates=candidates;
    data.json=json;
    data.json_capacity=capacity;
    if (data.candidates)
        for (unsigned i=0;i<peace_annex_max_candidates;++i)
            data.candidates[i]=PeaceAnnexCandidate{};
}

static bool peace_annex_same_candidate(const PeaceAnnexCandidate& left,
    const PeaceAnnexCandidate& right) noexcept {
    return left.province_id==right.province_id
        && left.owner==right.owner
        && left.beneficiary==right.beneficiary
        && left.selected==right.selected
        && left.readcomplete==right.readcomplete;
}

static bool peace_annex_candidate_matches(const PeaceAnnexCandidate& row,
    const PeaceAnnexQueryData& data) noexcept {
    // The losing country is selected by term +0x22 or province +0x468.  The
    // beneficiary is a separate claimant constraint and is never used to
    // identify the loser.
    return row.owner_match && row.beneficiary==data.requested_beneficiary;
}

static bool peace_annex_collect_selection(void* offer,
    const PeaceAnnexQueryData& data,PeaceAnnexCandidate* rows,unsigned& count,
    bool& complete,unsigned& selected_count) noexcept {
    count=0; selected_count=0; complete=true;
    uintptr_t terms=0; unsigned term_count=0; bool term_complete=true;
    bool capacity_exceeded=false;
    if (!peace_annex_offer_terms(reinterpret_cast<uintptr_t>(offer),terms,
        term_count,term_complete,capacity_exceeded)) return false;
    if (!term_complete || capacity_exceeded) complete=false;
    PeaceProvinceArrayBounds bounds{};
    if (!peace_province_read_bounds(bounds)) return false;
    for (unsigned i=0;i<term_count;++i) {
        uintptr_t term=0,vtable=0;
        if (!read(terms+static_cast<uintptr_t>(i)*8u,term)
            || !term || !read(term,vtable)) { complete=false; continue; }
        if (vtable!=base+peace_annex_type3_vtable_rva) continue;
        if (count>=peace_annex_max_candidates) { complete=false; continue; }
        PeaceAnnexCandidate row{};
        if (!peace_annex_read_term(term,bounds,data.payer,data.claimant,row)) {
            complete=false; continue;
        }
        for (unsigned j=0;j<count;++j)
            if (rows[j].province_id==row.province_id) {
                complete=false;
                row.readcomplete=false;
            }
        if (!row.readcomplete) complete=false;
        if (row.selected) ++selected_count;
        rows[count++]=row;
    }
    return true;
}

static bool peace_annex_query_read_selection(void* offer,
    PeaceAnnexQueryData& data,bool action_copy) noexcept {
    if (!data.enabled || !data.valid() || !offer) return false;
    PeaceAnnexCandidate rows[peace_annex_max_candidates]{};
    unsigned count=0,selected_count=0; bool complete=false;
    if (!peace_annex_collect_selection(offer,data,rows,count,complete,
        selected_count)) return false;
    if (action_copy) {
        data.action_copy_checked=true;
        data.action_copy_matched=count==data.candidate_count && complete
            && data.source_selection_complete;
        if (data.action_copy_matched) {
            for (unsigned i=0;i<count;++i) {
                bool found=false;
                for (unsigned j=0;j<data.candidate_count;++j)
                    if (peace_annex_same_candidate(rows[i],data.candidates[j])) {
                        found=true; break;
                    }
                if (!found) { data.action_copy_matched=false; break; }
            }
        }
        return true;
    }
    data.selected_term_count=selected_count;
    data.source_selection_complete=complete;
    for (unsigned i=0;i<data.candidate_count;++i) {
        data.candidates[i].selected=false;
        for (unsigned j=0;j<count;++j)
            if (data.candidates[i].province_id==rows[j].province_id
                && data.candidates[i].beneficiary==rows[j].beneficiary) {
                data.candidates[i].selected=rows[j].selected;
                break;
            }
    }
    return true;
}

static void peace_annex_update_matches(PeaceAnnexQueryData& data) noexcept {
    data.candidate_match_count=0;
    for (unsigned i=0;i<data.candidate_count;++i) {
        auto& row=data.candidates[i];
        row.owner_match=(row.term_owner==data.target_country
            || row.province_owner==data.target_country);
        if (peace_annex_candidate_matches(row,data)) ++data.candidate_match_count;
    }
    data.requested_candidates_found=false;
    data.candidate_matches_complete=data.candidate_enumeration_complete
        && data.owned_index_complete && !data.candidate_duplicates
        && !data.owned_index_duplicates
        && data.candidate_count<=peace_annex_max_candidates;
    if (!data.candidate_matches_complete) return;
    if (data.candidate_match_count!=data.target_owned_count) {
        data.candidate_matches_complete=false;
        return;
    }
    for (unsigned i=0;i<data.target_owned_count;++i) {
        unsigned matches=0;
        for (unsigned j=0;j<data.candidate_count;++j)
            if (peace_annex_candidate_matches(data.candidates[j],data)
                && data.candidates[j].province_id==data.owned_ids[i]) ++matches;
        if (matches!=1u) {
            data.candidate_matches_complete=false;
            return;
        }
    }
    for (unsigned j=0;j<data.candidate_count;++j)
        if (peace_annex_candidate_matches(data.candidates[j],data)) {
            bool found=false;
            for (unsigned i=0;i<data.target_owned_count;++i)
                if (data.owned_ids[i]==data.candidates[j].province_id) {
                    found=true; break;
                }
            if (!found) { data.candidate_matches_complete=false; return; }
        }
    data.requested_candidates_found=true;
}

static bool peace_annex_call_native_check(void* offer,
    PeaceAnnexQueryData& data) noexcept {
    if (!offer || !data.target_country) return false;
    uint64_t output=peace_annex_output_sentinel;
    using NativeCheck=bool (*)(void*,uint64_t,uint64_t*);
    const bool result=reinterpret_cast<NativeCheck>(base+peace_annex_native_check_rva)(
        offer,data.target_country,&output);
    data.native_annex_check_called=true;
    data.native_annex_bool=result;
    data.native_output_country_raw=output;
    data.native_output_country_present=output!=peace_annex_output_sentinel;
    data.native_output_country_tag[0]=0;
    if (data.native_output_country_present)
        peace_annex_tag_from_handle(output,data.native_output_country_tag);
    return true;
}

static bool peace_annex_select_all(void* offer,PeaceAnnexQueryData& data,
    unsigned char direction) noexcept {
    uintptr_t descriptor_method=0,recalculate=0;
    if (!read(base+peace_annex_type3_vtable_rva+0x78u,descriptor_method)
        || descriptor_method!=base+peace_annex_descriptor_rva
        || !read(base+peace_annex_type3_vtable_rva+0x118u,recalculate)
        || recalculate!=base+peace_annex_recalculate_rva) return false;
    uintptr_t address=reinterpret_cast<uintptr_t>(offer);
    uintptr_t buckets=0;
    unsigned bucket_count=0;
    if (!peace_payload_span(address,0xd0u,24u,
        bridge::peace_payload::kPeaceBucketCount,buckets,bucket_count)) return false;
    using Descriptor=void* (*)(void*,void*);
    using DependencyUpdate=void (*)(void*,void*,unsigned char);
    using Recalculate=void (*)(void*,void*,unsigned char,unsigned char);
    using Append=void (*)(void*,uintptr_t,const uintptr_t*);
    using Aggregate=int32_t (*)(void*,unsigned char);
    const auto aggregate=reinterpret_cast<Aggregate>(base+0x978ed0u);

    // Preflight every matching term and its typed vector before changing the
    // first selected bit.  A descriptor/vector failure therefore cannot
    // leave a partially selected annex request behind.
    unsigned preflight_count=0;
    for (unsigned i=0;i<data.candidate_count;++i) {
        const auto& row=data.candidates[i];
        if (!peace_annex_candidate_matches(row,data)) continue;
        unsigned char selected=0;
        if (!read(row.term+0x20u,selected) || selected) return false;
        alignas(8) unsigned char descriptor[16]{};
        if (reinterpret_cast<Descriptor>(descriptor_method)(
                reinterpret_cast<void*>(row.term),descriptor)!=descriptor) return false;
        uint32_t bucket=0;
        memcpy(&bucket,descriptor,sizeof(bucket));
        if (bucket!=peace_annex_bucket || bucket>=bucket_count) return false;
        const uintptr_t vector=buckets+static_cast<uintptr_t>(bucket)*24u;
        uintptr_t begin=0,end=0,capacity=0;
        if (!read(vector,begin) || !read(vector+8u,end)
            || !read(vector+16u,capacity) || end<begin || capacity<end
            || (end-begin)%8u || (capacity-begin)%8u
            || (end-begin)/8u>=bridge::peace_payload::kMaxPeaceTerms) return false;
        ++preflight_count;
    }
    if (preflight_count!=data.candidate_match_count) return false;
    const int32_t before=aggregate(offer,1u);
    unsigned applied=0;
    for (unsigned i=0;i<data.candidate_count;++i) {
        auto& row=data.candidates[i];
        if (!peace_annex_candidate_matches(row,data)) continue;
        unsigned char selected=0;
        if (!read(row.term+0x20u,selected) || selected) return false;
        alignas(8) unsigned char descriptor[16]{};
        if (reinterpret_cast<Descriptor>(descriptor_method)(
                reinterpret_cast<void*>(row.term),descriptor)!=descriptor) return false;
        uint32_t bucket=0;
        memcpy(&bucket,descriptor,sizeof(bucket));
        if (bucket!=peace_annex_bucket || bucket>=bucket_count) return false;
        uintptr_t vector=buckets+static_cast<uintptr_t>(bucket)*24u;
        uintptr_t begin=0,end=0,capacity=0;
        if (!read(vector,begin) || !read(vector+8u,end)
            || !read(vector+16u,capacity) || end<begin || capacity<end
            || (end-begin)%8u || (capacity-begin)%8u
            || (end-begin)/8u>=bridge::peace_payload::kMaxPeaceTerms) return false;
        selected=1;
        memcpy(reinterpret_cast<void*>(row.term+0x20u),&selected,1u);
        reinterpret_cast<DependencyUpdate>(base+0x97a4e0u)(offer,
            reinterpret_cast<void*>(row.term),1u);
        if (!peace_payload_span(address,0xd0u,24u,
            bridge::peace_payload::kPeaceBucketCount,buckets,bucket_count)
            || bucket>=bucket_count) return false;
        vector=buckets+static_cast<uintptr_t>(bucket)*24u;
        if (!read(vector,begin) || !read(vector+8u,end)
            || !read(vector+16u,capacity) || end<begin || capacity<end
            || (end-begin)%8u || (capacity-begin)%8u
            || (end-begin)/8u>=bridge::peace_payload::kMaxPeaceTerms) return false;
        if (end==capacity)
            reinterpret_cast<Append>(base+0xcc220u)(reinterpret_cast<void*>(vector),
                end,&row.term);
        else {
            memcpy(reinterpret_cast<void*>(end),&row.term,sizeof(row.term));
            end+=8u;
            memcpy(reinterpret_cast<void*>(vector+8u),&end,sizeof(end));
        }
        reinterpret_cast<Recalculate>(recalculate)(reinterpret_cast<void*>(row.term),
            reinterpret_cast<void*>(address+0xe8u),direction,0u);
        reinterpret_cast<DependencyUpdate>(base+0x97a4e0u)(offer,
            reinterpret_cast<void*>(row.term),0u);
        ++applied;
    }
    data.selection_applied=applied==data.candidate_match_count
        && applied==data.target_owned_count;
    const int64_t delta=static_cast<int64_t>(aggregate(offer,1u))
        -static_cast<int64_t>(before);
    if (delta>=(-2147483647ll-1ll) && delta<=2147483647ll) {
        data.selection_delta_available=true;
        data.selection_delta_raw=static_cast<int32_t>(delta);
    }
    return data.selection_applied;
}

static bool peace_annex_query_enumerate(void* offer,PeaceAnnexQueryData& data) noexcept {
    if (!data.enabled || !data.valid() || !offer) return false;
    uintptr_t terms=0; unsigned term_count=0; bool terms_complete=true;
    bool term_capacity=false;
    if (!peace_annex_offer_terms(reinterpret_cast<uintptr_t>(offer),terms,
        term_count,terms_complete,term_capacity)) return false;
    PeaceProvinceArrayBounds bounds{};
    if (!peace_province_read_bounds(bounds)) return false;
    data.candidate_enumeration_complete=terms_complete;
    data.capacity_exceeded=data.capacity_exceeded || term_capacity;
    data.query_complete=true;
    for (unsigned i=0;i<term_count;++i) {
        uintptr_t term=0,vtable=0;
        if (!read(terms+static_cast<uintptr_t>(i)*8u,term)
            || !term || !read(term,vtable)) {
            data.candidate_enumeration_complete=false; continue;
        }
        if (vtable!=base+peace_annex_type3_vtable_rva) continue;
        if (data.candidate_count>=peace_annex_max_candidates) {
            data.capacity_exceeded=true;
            data.candidate_enumeration_complete=false;
            continue;
        }
        PeaceAnnexCandidate row{};
        if (!peace_annex_read_term(term,bounds,data.payer,data.claimant,row)) {
            data.candidate_enumeration_complete=false; continue;
        }
        for (unsigned j=0;j<data.candidate_count;++j)
            if (data.candidates[j].province_id==row.province_id) {
                data.candidate_duplicates=true;
                data.candidate_enumeration_complete=false;
                row.readcomplete=false;
            }
        if (!row.readcomplete) data.candidate_enumeration_complete=false;
        data.candidates[data.candidate_count++]=row;
    }
    return true;
}

static bool peace_annex_query_prepare(void* offer,uint64_t actor,uint64_t recipient,
    bool demand,const PeaceAnnexRequest& request,PeaceAnnexQueryData& data) noexcept {
    if (!data.enabled || !data.valid() || !offer
        || !peace_annex_valid_tag(request.country)) return false;
    peace_annex_reset(data);
    data.selection_requested=request.selection_requested;
    data.payer=peace_offer_payer(actor,recipient,demand);
    data.claimant=peace_offer_claimant(actor,recipient,demand);
    if (!alliance_query_country(request.country,data.target_country)
        || !peace_annex_tag_from_handle(data.target_country,data.target_country_tag)) return false;
    if (request.beneficiary[0]) {
        if (!peace_annex_valid_tag(request.beneficiary)) return false;
        if (!alliance_query_country(request.beneficiary,data.requested_beneficiary)
            || !peace_annex_tag_from_handle(data.requested_beneficiary,
                data.requested_beneficiary_tag)) return false;
    } else {
        data.requested_beneficiary=data.claimant;
        if (!peace_annex_tag_from_handle(data.claimant,data.requested_beneficiary_tag)) return false;
    }
    PeaceProvinceArrayBounds bounds{};
    if (!peace_province_read_bounds(bounds)
        || !peace_annex_read_owned_index(data.target_country,data,bounds)
        || !peace_annex_query_enumerate(offer,data)) return false;
    peace_annex_update_matches(data);
    if (!data.candidate_matches_complete) {
        data.reason_code=data.capacity_exceeded
            ?"NATIVE_PEACE_ANNEX_SELECTION_CAPACITY"
            :"NATIVE_PEACE_ANNEX_CANDIDATE_SET_INCOMPLETE";
    } else if (!data.requested_candidates_found) {
        data.reason_code="NATIVE_PEACE_ANNEX_CANDIDATE_ABSENT";
    }
    if (!peace_annex_call_native_check(offer,data)) return false;
    if (!request.selection_requested) {
        data.source_selection_complete=true;
        if (!data.reason_code) data.reason_code="NATIVE_PEACE_ANNEX_DISCOVERY_ONLY";
        return true;
    }
    if (data.reason_code) return true;
    for (unsigned i=0;i<data.candidate_count;++i)
        if (data.candidates[i].selected) {
            data.reason_code="NATIVE_PEACE_ANNEX_UNEXPECTED_PRESELECTION";
            data.source_selection_complete=true;
            return true;
        }
    unsigned char direction=0;
    if (!read(reinterpret_cast<uintptr_t>(offer)+0x20u,direction) || direction>1u)
        return false;
    if (!peace_annex_select_all(offer,data,direction)) {
        if (!data.reason_code) data.reason_code="NATIVE_PEACE_ANNEX_SELECTION_UNAVAILABLE";
        return true;
    }
    if (!peace_annex_query_read_selection(offer,data,false)) return false;
    if (!peace_annex_call_native_check(offer,data)) return false;
    if (!data.source_selection_complete && !data.reason_code)
        data.reason_code="NATIVE_PEACE_ANNEX_SELECTION_READBACK_INCOMPLETE";
    return true;
}

static bool peace_annex_query_verify_copy(void* action_offer,
    PeaceAnnexQueryData& data) noexcept {
    return peace_annex_query_read_selection(action_offer,data,true);
}

static bool peace_annex_json_append(char* output,size_t capacity,size_t& used,
    const char* text) noexcept {
    if (!output || !text || used>capacity) return false;
    const size_t length=strlen(text);
    if (length>=capacity-used) return false;
    memcpy(output+used,text,length); used+=length; output[used]=0; return true;
}

static bool peace_annex_json_append_format(char* output,size_t capacity,size_t& used,
    const char* format,...) noexcept {
    if (!output || !format || used>=capacity) return false;
    va_list args; va_start(args,format);
    const int needed=vsnprintf(output+used,capacity-used,format,args);
    va_end(args);
    if (needed<0 || static_cast<size_t>(needed)>=capacity-used) return false;
    used+=static_cast<size_t>(needed); return true;
}

static bool peace_annex_query_json(PeaceAnnexQueryData& data) noexcept {
    if (!data.enabled || !data.valid() || !data.json) return false;
    data.json[0]=0; data.json_size=0; size_t used=0;
    if (!peace_annex_json_append_format(data.json,data.json_capacity,used,
        "{\"action_id\":\"full_annexation\",\"country\":\"%.3s\",\"beneficiary\":\"%.3s\",\"selection_requested\":%s,\"candidates\":[",
        data.target_country_tag,data.requested_beneficiary_tag,
        data.selection_requested?"true":"false")) return false;
    for (unsigned i=0;i<data.candidate_count;++i) {
        const auto& row=data.candidates[i];
        if (i && !peace_annex_json_append(data.json,data.json_capacity,used,",")) return false;
        if (!peace_annex_json_append_format(data.json,data.json_capacity,used,
            "{\"province_id\":%d,\"owner\":\"%.3s\",\"beneficiary\":\"%.3s\",\"owner_match\":%s,\"selected\":%s,\"readcomplete\":%s}",
            row.province_id,row.owner_tag,row.beneficiary_tag,
            row.owner_match?"true":"false",row.selected?"true":"false",
            row.readcomplete?"true":"false")) return false;
    }
    if (!peace_annex_json_append_format(data.json,data.json_capacity,used,
        "],\"candidate_count\":%u,\"candidate_enumeration_complete\":%s,\"target_owned_count\":%u,\"owned_index_complete\":%s,\"candidate_match_count\":%u,\"candidate_matches_complete\":%s,\"requested_candidates_found\":%s,\"selection_applied\":%s,\"source_selection_complete\":%s,\"action_copy_checked\":%s,\"action_copy_matched\":%s,\"selection_delta_available\":%s,\"selection_delta_raw\":",
        data.candidate_count,data.candidate_enumeration_complete?"true":"false",
        data.target_owned_count,data.owned_index_complete?"true":"false",
        data.candidate_match_count,data.candidate_matches_complete?"true":"false",
        data.requested_candidates_found?"true":"false",data.selection_applied?"true":"false",
        data.source_selection_complete?"true":"false",data.action_copy_checked?"true":"false",
        data.action_copy_matched?"true":"false",
        data.selection_delta_available?"true":"false")) return false;
    if (data.selection_delta_available) {
        if (!peace_annex_json_append_format(data.json,data.json_capacity,used,"%d",
            data.selection_delta_raw)) return false;
    } else if (!peace_annex_json_append(data.json,data.json_capacity,used,"null")) return false;
    if (!peace_annex_json_append_format(data.json,data.json_capacity,used,
        ",\"native_annex_check_called\":%s,\"native_annex_bool\":",
        data.native_annex_check_called?"true":"false")) return false;
    if (data.native_annex_check_called) {
        if (!peace_annex_json_append(data.json,data.json_capacity,used,
            data.native_annex_bool?"true":"false")) return false;
    } else if (!peace_annex_json_append(data.json,data.json_capacity,used,"null")) return false;
    if (!peace_annex_json_append(data.json,data.json_capacity,used,
        ",\"native_output_country\":")) return false;
    if (data.native_output_country_present && data.native_output_country_tag[0]) {
        if (!peace_annex_json_append_format(data.json,data.json_capacity,used,
            "\"%.3s\"",data.native_output_country_tag)) return false;
    } else if (!peace_annex_json_append(data.json,data.json_capacity,used,"null")) return false;
    if (!peace_annex_json_append_format(data.json,data.json_capacity,used,
        ",\"native_output_country_raw\":\"0x%llx\",\"native_owned_count_called\":%s,\"native_owned_count_raw\":%d,\"native_owned_count_matches\":%s,\"capacity_exceeded\":%s,\"complete\":%s,\"reason_code\":",
        static_cast<unsigned long long>(data.native_output_country_raw),
        data.native_owned_count_called?"true":"false",data.native_owned_count_raw,
        data.native_owned_count_matches?"true":"false",data.capacity_exceeded?"true":"false",
        data.complete()?"true":"false")) return false;
    if (data.reason_code) {
        if (!peace_annex_json_append_format(data.json,data.json_capacity,used,"\"%s\"",
            data.reason_code)) return false;
    } else if (!peace_annex_json_append(data.json,data.json_capacity,used,"null")) return false;
    if (!peace_annex_json_append(data.json,data.json_capacity,used,"}")) return false;
    data.json_size=used; return true;
}

static void peace_annex_query_private(const char* id,
    const PeaceAnnexQueryData& data) noexcept {
    if (!data.enabled || !data.candidates) return;
    for (unsigned i=0;i<data.candidate_count;++i) {
        const auto& row=data.candidates[i];
        char message[1200]{};
        const int written=snprintf(message,sizeof(message),
            "{\"event\":\"native_peace_annex_candidate_private\",\"private\":true,\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"index\":%u,\"province_id\":%d,\"term_owner\":\"0x%llx\",\"province_owner\":\"0x%llx\",\"beneficiary\":\"0x%llx\",\"selected\":%s,\"readcomplete\":%s}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),
            static_cast<unsigned long long>(observation_creation),id?id:"",i,
            row.province_id,static_cast<unsigned long long>(row.term_owner),
            static_cast<unsigned long long>(row.province_owner),
            static_cast<unsigned long long>(row.beneficiary),row.selected?"true":"false",
            row.readcomplete?"true":"false");
        if (written>0 && static_cast<size_t>(written)<sizeof(message)) line(message);
    }
}
