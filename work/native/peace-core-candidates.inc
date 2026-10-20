// Read-only Return Core/Revoke Core candidate and selection observations.
// Candidates are native terms already populated by CPeaceOffer construction.
// This file never calls a peace business/finalization method; selection only
// follows the verified persistent 98bf50 vector path on a fresh temporary offer.

#include <windows.h>
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <cstdio>
#include <cstdarg>

static constexpr unsigned peace_core_max_candidates=512u;
static constexpr unsigned peace_core_max_requested=16u;
static constexpr size_t peace_core_name_bytes=512u;
static constexpr size_t peace_core_json_capacity=360000u;

struct PeaceCoreRequest {
    int32_t province_ids[peace_core_max_requested]{};
    unsigned province_count=0;
    char core_owner[4]{};
    bool selection_requested=false;
    bool return_core=false;
};

static bool peace_core_valid_tag(const char* tag) noexcept {
    if (!tag || strlen(tag)!=3) return false;
    for (unsigned i=0;i<3;++i) {
        const char value=tag[i];
        if (!((value>='A' && value<='Z') || (value>='0' && value<='9'))) return false;
    }
    return true;
}

static bool peace_core_parse_request(const char* ids,const char* owner,
    PeaceCoreRequest& request) noexcept {
    request=PeaceCoreRequest{};
    if (!ids || !owner) return false;
    const bool ids_empty=!strcmp(ids,"-");
    const bool owner_empty=!strcmp(owner,"-");
    if (!ids_empty && (!ids[0] || strlen(ids)>176u)) return false;
    if (!owner_empty && !peace_core_valid_tag(owner)) return false;
    if (ids_empty != owner_empty) return false;
    if (ids_empty) return true;
    const char* cursor=ids;
    while (*cursor) {
        if (request.province_count>=peace_core_max_requested
            || *cursor<'1' || *cursor>'9') return false;
        uint64_t value=0;
        while (*cursor>='0' && *cursor<='9') {
            value=value*10u+static_cast<unsigned>(*cursor-'0');
            if (value>2147483647u) return false;
            ++cursor;
        }
        for (unsigned i=0;i<request.province_count;++i)
            if (request.province_ids[i]==static_cast<int32_t>(value)) return false;
        request.province_ids[request.province_count++]=static_cast<int32_t>(value);
        if (!*cursor) break;
        if (*cursor++!=',' || !*cursor) return false;
    }
    if (!request.province_count) return false;
    memcpy(request.core_owner,owner,sizeof(request.core_owner));
    request.selection_requested=true;
    return true;
}

struct PeaceCoreSpec {
    uint32_t type=0;
    uint32_t bucket=0;
    uintptr_t vtable=0;
    uintptr_t descriptor=0;
    uintptr_t recalculate=0;
};

static PeaceCoreSpec peace_core_spec(const PeaceCoreRequest& request) noexcept {
    return request.return_core
        ?PeaceCoreSpec{0x2e00u,5u,0x1cd4988u,0x99ae00u,0x9acb70u}
        :PeaceCoreSpec{0x2d26u,4u,0x1cd3778u,0x99ae70u,0x9b4b60u};
}

struct PeaceCoreCandidate {
    uintptr_t term=0;
    uintptr_t province=0;
    int32_t province_id=-1;
    uint64_t core_owner=0;
    uint64_t province_owner=0;
    char core_owner_tag[4]{};
    char province_owner_tag[4]{};
    char name_hex[peace_core_name_bytes*2+1]{};
    bool name_readable=false;
    bool name_truncated=false;
    bool selected=false;
    bool record_complete=false;
};

struct PeaceCoreQueryData {
    bool enabled=false;
    PeaceCoreCandidate* candidates=nullptr;
    char* json=nullptr;
    size_t json_size=0;
    size_t json_capacity=0;
    unsigned candidate_count=0;
    bool candidate_enumeration_complete=false;
    bool query_complete=false;
    bool return_core=false;
    uint64_t payer=0,claimant=0,requested_core_owner=0;
    char requested_core_owner_tag[4]{};
    int32_t requested_province_ids[peace_core_max_requested]{};
    unsigned requested_province_count=0;
    bool selection_requested=false;
    bool requested_candidates_found=false;
    unsigned selected_term_count=0;
    bool parameters_matched=false;
    bool selection_applied=false;
    bool selection_records_complete=false;
    bool action_copy_matched=false;
    bool selection_delta_available=false;
    int32_t selection_delta_raw=0;
    int32_t aggregate_before_raw=0,aggregate_after_raw=0;
    const char* reason_code=nullptr;

    explicit PeaceCoreQueryData(bool enable=false) noexcept : enabled(enable) {
        if (!enabled) return;
        candidates=static_cast<PeaceCoreCandidate*>(HeapAlloc(GetProcessHeap(),
            HEAP_ZERO_MEMORY,sizeof(PeaceCoreCandidate)*peace_core_max_candidates));
        json=static_cast<char*>(HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,
            peace_core_json_capacity));
        json_capacity=json?peace_core_json_capacity:0;
        if (!candidates || !json) {
            if (candidates) HeapFree(GetProcessHeap(),0,candidates);
            if (json) HeapFree(GetProcessHeap(),0,json);
            candidates=nullptr; json=nullptr; json_capacity=0;
        }
    }
    PeaceCoreQueryData(const PeaceCoreQueryData&)=delete;
    PeaceCoreQueryData& operator=(const PeaceCoreQueryData&)=delete;
    ~PeaceCoreQueryData() noexcept {
        if (candidates) HeapFree(GetProcessHeap(),0,candidates);
        if (json) HeapFree(GetProcessHeap(),0,json);
    }
    bool valid() const noexcept {
        return !enabled || (candidates && json
            && json_capacity==peace_core_json_capacity);
    }
};

static bool peace_core_tag_from_handle(uint64_t handle,char (&tag)[4]) noexcept {
    return handle && peace_province_tag(handle,tag);
}

static bool peace_core_read_candidate(uintptr_t term,
    const PeaceCoreSpec& spec,const PeaceProvinceArrayBounds& bounds,
    uint64_t payer,uint64_t claimant,PeaceCoreCandidate& output) noexcept {
    output=PeaceCoreCandidate{};
    output.term=term;
    uintptr_t vtable=0,province=0,expected=0;
    unsigned char selected=0;
    uint64_t field10=0,field18=0,field22=0,extra30=0,owner=0;
    if (!term || !read(term,vtable) || vtable!=base+spec.vtable
        || !read(term+0x10u,field10) || field10!=payer
        || !read(term+0x18u,field18) || field18!=claimant
        || !read(term+0x22u,field22)
        || !read(term+0x20u,selected) || selected>1u
        || !read(term+0x30u,extra30)
        || !read(term+0x38u,province) || !province) return false;
    if (spec.type==0x2e00u && field22!=payer) return false;
    int32_t province_id=-1;
    if (!read(province+peace_province_record_id_offset,province_id)
        || !peace_province_record_for_id(bounds,province_id,expected)
        || expected!=province
        || !read(province+0x468u,owner)) return false;
    const uint64_t core_owner=spec.type==0x2e00u?extra30:field22;
    if (!core_owner || !owner
        || !peace_query_country_pointer(core_owner,expected)
        || !peace_query_country_pointer(owner,expected)
        || !peace_core_tag_from_handle(core_owner,output.core_owner_tag)
        || !peace_core_tag_from_handle(owner,output.province_owner_tag)) return false;
    PeaceProvinceCandidate name{};
    name.province=province;
    const bool name_ok=peace_province_read_name(province,name);
    output.province=province;
    output.province_id=province_id;
    output.core_owner=core_owner;
    output.province_owner=owner;
    output.selected=selected!=0;
    output.name_readable=name_ok;
    output.name_truncated=name.name_truncated;
    if (name_ok) memcpy(output.name_hex,name.name_hex,sizeof(output.name_hex));
    output.record_complete=name_ok;
    return true;
}

static void peace_core_reset(PeaceCoreQueryData& data) noexcept {
    data.candidate_count=0;
    data.candidate_enumeration_complete=false;
    data.query_complete=false;
    data.requested_candidates_found=false;
    data.selected_term_count=0;
    data.parameters_matched=false;
    data.selection_applied=false;
    data.selection_records_complete=false;
    data.action_copy_matched=false;
    data.selection_delta_available=false;
    data.selection_delta_raw=0;
    data.aggregate_before_raw=0;
    data.aggregate_after_raw=0;
    data.reason_code=nullptr;
    if (data.candidates)
        for (unsigned i=0;i<peace_core_max_candidates;++i)
            data.candidates[i]=PeaceCoreCandidate{};
}

static bool peace_core_query_enumerate(void* offer,
    PeaceCoreQueryData& data,const PeaceCoreRequest& request,
    bool preserve_request=true) noexcept {
    if (!data.enabled || !data.valid() || !offer) return false;
    const unsigned requested_count=data.requested_province_count;
    const uint64_t requested_owner=data.requested_core_owner;
    const bool selection_requested=data.selection_requested;
    if (preserve_request) peace_core_reset(data);
    data.requested_province_count=requested_count;
    data.requested_core_owner=requested_owner;
    data.selection_requested=selection_requested;
    const PeaceCoreSpec spec=peace_core_spec(request);
    const uintptr_t address=reinterpret_cast<uintptr_t>(offer);
    uintptr_t terms=0;
    unsigned count=0;
    if (!peace_payload_span(address,0x88u,8u,peace_core_max_candidates,terms,count)) return false;
    PeaceProvinceArrayBounds bounds{};
    if (!peace_province_read_bounds(bounds)) return false;
    data.query_complete=true;
    data.candidate_enumeration_complete=true;
    for (unsigned i=0;i<count;++i) {
        uintptr_t term=0,vtable=0;
        if (!read(terms+static_cast<uintptr_t>(i)*8u,term)
            || !term || !read(term,vtable)) {
            data.candidate_enumeration_complete=false; continue;
        }
        if (vtable!=base+spec.vtable) continue;
        if (data.candidate_count>=peace_core_max_candidates) {
            data.candidate_enumeration_complete=false; continue;
        }
        PeaceCoreCandidate row{};
        if (!peace_core_read_candidate(term,spec,bounds,data.payer,data.claimant,row)) {
            data.candidate_enumeration_complete=false; continue;
        }
        for (unsigned j=0;j<data.candidate_count;++j)
            if (data.candidates[j].province_id==row.province_id) {
                data.candidate_enumeration_complete=false;
                row.record_complete=false;
            }
        if (!row.record_complete) data.candidate_enumeration_complete=false;
        data.candidates[data.candidate_count++]=row;
    }
    data.requested_candidates_found=false;
    if (selection_requested) {
        data.requested_candidates_found=true;
        for (unsigned i=0;i<data.requested_province_count;++i) {
            bool found=false;
            for (unsigned j=0;j<data.candidate_count;++j)
                if (data.candidates[j].province_id==data.requested_province_ids[i]
                    && data.candidates[j].core_owner==requested_owner) {
                    found=true; break;
                }
            if (!found) data.requested_candidates_found=false;
        }
    }
    return true;
}

struct PeaceCoreSelectionRow {
    int32_t province_id=-1;
    uint64_t core_owner=0,province_owner=0;
    bool selected=false,complete=false;
};

static bool peace_core_collect_selection(void* offer,const PeaceCoreSpec& spec,
    uint64_t payer,uint64_t claimant,PeaceCoreSelectionRow* rows,
    unsigned& count,bool& complete,unsigned& selected_count) noexcept {
    count=0; selected_count=0; complete=true;
    uintptr_t terms=0; unsigned term_count=0;
    if (!peace_payload_span(reinterpret_cast<uintptr_t>(offer),0x88u,8u,
        peace_core_max_candidates,terms,term_count)) return false;
    PeaceProvinceArrayBounds bounds{};
    if (!peace_province_read_bounds(bounds)) return false;
    for (unsigned i=0;i<term_count;++i) {
        uintptr_t term=0,vtable=0;
        if (!read(terms+static_cast<uintptr_t>(i)*8u,term)
            || !term || !read(term,vtable)) { complete=false; continue; }
        if (vtable!=base+spec.vtable) continue;
        if (count>=peace_core_max_candidates) { complete=false; continue; }
        PeaceCoreCandidate candidate{};
        if (!peace_core_read_candidate(term,spec,bounds,payer,claimant,candidate)) {
            complete=false; continue;
        }
        rows[count].province_id=candidate.province_id;
        rows[count].core_owner=candidate.core_owner;
        rows[count].province_owner=candidate.province_owner;
        rows[count].selected=candidate.selected;
        rows[count].complete=candidate.record_complete;
        if (!candidate.record_complete) complete=false;
        if (candidate.selected) ++selected_count;
        ++count;
    }
    return true;
}

static bool peace_core_query_read_selection(void* offer,
    PeaceCoreQueryData& data,const PeaceCoreRequest& request,bool action_copy) noexcept {
    if (!data.enabled || !data.valid() || !offer) return false;
    const PeaceCoreSpec spec=peace_core_spec(request);
    PeaceCoreSelectionRow rows[peace_core_max_candidates]{};
    unsigned count=0,selected=0; bool complete=false;
    if (!peace_core_collect_selection(offer,spec,data.payer,data.claimant,
        rows,count,complete,selected)) return false;
    if (action_copy) {
        data.action_copy_matched=count==data.candidate_count && complete
            && data.selection_records_complete;
        if (data.action_copy_matched) {
            for (unsigned i=0;i<count;++i) {
                bool found=false;
                for (unsigned j=0;j<data.candidate_count;++j)
                    if (data.candidates[j].province_id==rows[i].province_id
                        && data.candidates[j].core_owner==rows[i].core_owner
                        && data.candidates[j].province_owner==rows[i].province_owner
                        && data.candidates[j].selected==rows[i].selected
                        && rows[i].complete==data.candidates[j].record_complete) {
                        found=true; break;
                    }
                if (!found) { data.action_copy_matched=false; break; }
            }
        }
        return true;
    }
    data.selected_term_count=selected;
    data.selection_records_complete=complete;
    for (unsigned i=0;i<data.candidate_count;++i) {
        data.candidates[i].selected=false;
        for (unsigned j=0;j<count;++j)
            if (data.candidates[i].province_id==rows[j].province_id
                && data.candidates[i].core_owner==rows[j].core_owner) {
                data.candidates[i].selected=rows[j].selected; break;
            }
    }
    if (!data.selection_requested) {
        data.parameters_matched=false;
        return true;
    }
    data.parameters_matched=data.requested_candidates_found
        && data.selection_records_complete;
    for (unsigned i=0;i<data.requested_province_count && data.parameters_matched;++i) {
        bool found=false;
        for (unsigned j=0;j<count;++j)
            if (rows[j].province_id==data.requested_province_ids[i]
                && rows[j].core_owner==data.requested_core_owner
                && rows[j].selected) { found=true; break; }
        if (!found) data.parameters_matched=false;
    }
    if (data.parameters_matched && selected!=data.requested_province_count)
        data.parameters_matched=false;
    return true;
}

static bool peace_core_query_prepare(void* offer,uint64_t actor,uint64_t recipient,
    bool demand,const PeaceCoreRequest& request,PeaceCoreQueryData& data) noexcept {
    if (!data.valid()) return false;
    data.return_core=request.return_core;
    data.payer=peace_offer_payer(actor,recipient,demand);
    data.claimant=peace_offer_claimant(actor,recipient,demand);
    data.requested_province_count=request.province_count;
    data.selection_requested=request.selection_requested;
    memcpy(data.requested_province_ids,request.province_ids,
        sizeof(data.requested_province_ids));
    if (request.selection_requested) {
        if (!peace_core_valid_tag(request.core_owner)
            || !alliance_query_country(request.core_owner,data.requested_core_owner))
            return false;
        memcpy(data.requested_core_owner_tag,request.core_owner,sizeof(data.requested_core_owner_tag));
    }
    if (!peace_core_query_enumerate(offer,data,request)) return false;
    if (!request.selection_requested) {
        data.selection_records_complete=true;
        data.parameters_matched=false;
        data.selection_applied=false;
        return true;
    }
    if (!data.candidate_enumeration_complete || !data.requested_candidates_found) {
        data.selection_records_complete=data.candidate_enumeration_complete;
        data.selected_term_count=0;
        data.parameters_matched=false;
        data.selection_applied=false;
        data.reason_code=data.requested_candidates_found
            ?"NATIVE_PEACE_CORE_CANDIDATE_ENUMERATION_INCOMPLETE"
            :"NATIVE_PEACE_CORE_CANDIDATE_ABSENT";
        return true;
    }
    for (unsigned i=0;i<data.candidate_count;++i)
        if (data.candidates[i].selected) {
            data.selection_records_complete=true;
            data.reason_code="NATIVE_PEACE_CORE_UNEXPECTED_PRESELECTION";
            return true;
        }
    const PeaceCoreSpec spec=peace_core_spec(request);
    uintptr_t descriptor_method=0,recalculate=0;
    const uintptr_t address=reinterpret_cast<uintptr_t>(offer);
    if (!read(base+spec.vtable+0x78u,descriptor_method)
        || descriptor_method!=base+spec.descriptor
        || !read(base+spec.vtable+0x118u,recalculate)
        || recalculate!=base+spec.recalculate) return false;
    using Descriptor=void* (*)(void*,void*);
    using DependencyUpdate=void (*)(void*,void*,unsigned char);
    using Recalculate=void (*)(void*,void*,unsigned char,unsigned char);
    using Append=void (*)(void*,uintptr_t,const uintptr_t*);
    using Aggregate=int32_t (*)(void*,unsigned char);
    const auto aggregate=reinterpret_cast<Aggregate>(base+0x978ed0);
    const int32_t aggregate_before=aggregate(offer,1);
    unsigned toggles=0;
    for (unsigned requested=0;requested<request.province_count;++requested) {
        PeaceCoreCandidate* candidate=nullptr;
        for (unsigned i=0;i<data.candidate_count;++i)
            if (data.candidates[i].province_id==request.province_ids[requested]
                && data.candidates[i].core_owner==data.requested_core_owner) {
                candidate=&data.candidates[i]; break;
            }
        if (!candidate) return false;
        alignas(8) unsigned char descriptor[16]{};
        unsigned char direction=0,selected=0;
        if (!read(address+0x20u,direction) || direction>1u
            || !read(candidate->term+0x20u,selected) || selected
            || reinterpret_cast<Descriptor>(descriptor_method)(
                reinterpret_cast<void*>(candidate->term),descriptor)!=descriptor) return false;
        uint32_t bucket=0; memcpy(&bucket,descriptor,sizeof(bucket));
        if (bucket!=spec.bucket) return false;
        uintptr_t buckets=0; unsigned bucket_count=0;
        if (!peace_payload_span(address,0xd0u,24u,bridge::peace_payload::kPeaceBucketCount,
            buckets,bucket_count) || bucket>=bucket_count) return false;
        candidate->selected=true;
        selected=1;
        memcpy(reinterpret_cast<void*>(candidate->term+0x20u),&selected,1);
        reinterpret_cast<DependencyUpdate>(base+0x97a4e0)(offer,
            reinterpret_cast<void*>(candidate->term),1);
        if (!peace_payload_span(address,0xd0u,24u,bridge::peace_payload::kPeaceBucketCount,
            buckets,bucket_count) || bucket>=bucket_count) return false;
        const uintptr_t vector=buckets+static_cast<uintptr_t>(bucket)*24u;
        uintptr_t begin=0,end=0,capacity=0;
        if (!read(vector,begin) || !read(vector+8u,end) || !read(vector+16u,capacity)
            || end<begin || capacity<end || (end-begin)%8u || (capacity-begin)%8u
            || (end-begin)/8u>=bridge::peace_payload::kMaxPeaceTerms) return false;
        if (end==capacity)
            reinterpret_cast<Append>(base+0xcc220)(reinterpret_cast<void*>(vector),end,
                &candidate->term);
        else {
            memcpy(reinterpret_cast<void*>(end),&candidate->term,sizeof(candidate->term));
            end+=8u; memcpy(reinterpret_cast<void*>(vector+8u),&end,sizeof(end));
        }
        reinterpret_cast<Recalculate>(recalculate)(reinterpret_cast<void*>(candidate->term),
            reinterpret_cast<void*>(address+0xe8u),direction,0);
        reinterpret_cast<DependencyUpdate>(base+0x97a4e0)(offer,
            reinterpret_cast<void*>(candidate->term),0);
        ++toggles;
    }
    data.selection_applied=toggles==request.province_count;
    if (data.selection_applied) {
        const int32_t aggregate_after=aggregate(offer,1);
        const int64_t delta=static_cast<int64_t>(aggregate_after)
            -static_cast<int64_t>(aggregate_before);
        if (delta>=(-2147483647ll-1) && delta<=2147483647ll) {
            data.selection_delta_available=true;
            data.selection_delta_raw=static_cast<int32_t>(delta);
            data.aggregate_before_raw=aggregate_before;
            data.aggregate_after_raw=aggregate_after;
        }
    }
    if (!peace_core_query_read_selection(offer,data,request,false)) return false;
    if (!data.parameters_matched && !data.reason_code)
        data.reason_code="NATIVE_PEACE_CORE_SELECTION_MISMATCH";
    return true;
}

static bool peace_core_json_append(char* output,size_t capacity,size_t& used,
    const char* text) noexcept {
    if (!output || !text || used>capacity) return false;
    const size_t length=strlen(text);
    if (length>=capacity-used) return false;
    memcpy(output+used,text,length); used+=length; output[used]=0; return true;
}

static bool peace_core_json_append_format(char* output,size_t capacity,size_t& used,
    const char* format,...) noexcept {
    if (!output || !format || used>=capacity) return false;
    va_list args; va_start(args,format);
    const int needed=vsnprintf(output+used,capacity-used,format,args);
    va_end(args);
    if (needed<0 || static_cast<size_t>(needed)>=capacity-used) return false;
    used+=static_cast<size_t>(needed); return true;
}

static bool peace_core_query_json(PeaceCoreQueryData& data) noexcept {
    if (!data.enabled || !data.valid() || !data.json) return false;
    data.json[0]=0; data.json_size=0; size_t used=0;
    if (!peace_core_json_append_format(data.json,data.json_capacity,used,
        "{\"action_id\":\"%s\",\"candidate_count\":%u,\"candidate_enumeration_complete\":%s,\"candidates\":[",
        data.return_core?"return_core":"revoke_core",data.candidate_count,
        data.candidate_enumeration_complete?"true":"false")) return false;
    for (unsigned i=0;i<data.candidate_count;++i) {
        const auto& row=data.candidates[i];
        if (i && !peace_core_json_append(data.json,data.json_capacity,used,",")) return false;
        if (!peace_core_json_append_format(data.json,data.json_capacity,used,
            "{\"province_id\":%d,\"name\":\"%s\",\"name_readable\":%s,\"core_owner\":\"%.3s\",\"province_owner\":\"%.3s\",\"selected\":%s,\"record_complete\":%s}",
            row.province_id,row.name_hex,row.name_readable?"true":"false",
            row.core_owner_tag,row.province_owner_tag,
            row.selected?"true":"false",row.record_complete?"true":"false")) return false;
    }
    if (!peace_core_json_append(data.json,data.json_capacity,used,"]")) return false;
    if (!peace_core_json_append_format(data.json,data.json_capacity,used,
        ",\"requested_core_owner\":")) return false;
    if (data.selection_requested) {
        if (!peace_core_json_append_format(data.json,data.json_capacity,used,
            "\"%.3s\"",data.requested_core_owner_tag)) return false;
    } else if (!peace_core_json_append(data.json,data.json_capacity,used,"null")) return false;
    if (!peace_core_json_append(data.json,data.json_capacity,used,",\"requested_province_ids\":[")) return false;
    for (unsigned i=0;i<data.requested_province_count;++i) {
        if (i && !peace_core_json_append(data.json,data.json_capacity,used,",")) return false;
        if (!peace_core_json_append_format(data.json,data.json_capacity,used,"%d",
            data.requested_province_ids[i])) return false;
    }
    if (!peace_core_json_append_format(data.json,data.json_capacity,used,
        "],\"selection_requested\":%s,\"requested_candidates_found\":%s,\"selected_term_count\":%u,\"parameters_matched\":%s,\"selection_applied\":%s,\"selection_records_complete\":%s,\"action_copy_matched\":%s,\"selection_delta_available\":%s,\"selection_delta_raw\":",
        data.selection_requested?"true":"false",data.requested_candidates_found?"true":"false",
        data.selected_term_count,data.parameters_matched?"true":"false",
        data.selection_applied?"true":"false",data.selection_records_complete?"true":"false",
        data.action_copy_matched?"true":"false",data.selection_delta_available?"true":"false")) return false;
    if (data.selection_delta_available) {
        if (!peace_core_json_append_format(data.json,data.json_capacity,used,
            "%d,\"aggregate_before_raw\":%d,\"aggregate_after_raw\":%d",
            data.selection_delta_raw,data.aggregate_before_raw,data.aggregate_after_raw)) return false;
    } else if (!peace_core_json_append(data.json,data.json_capacity,used,
        "null,\"aggregate_before_raw\":null,\"aggregate_after_raw\":null")) return false;
    if (!peace_core_json_append(data.json,data.json_capacity,used,"}")) return false;
    data.json_size=used; return true;
}

static void peace_core_query_private(const char* id,const char* action_id,
    const PeaceCoreQueryData& data) noexcept {
    if (!data.enabled || !data.candidates) return;
    for (unsigned i=0;i<data.candidate_count;++i) {
        const auto& row=data.candidates[i];
        char message[2200]{};
        const int written=snprintf(message,sizeof(message),
            "{\"event\":\"native_peace_core_candidate_private\",\"private\":true,\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"action_id\":\"%s\",\"index\":%u,\"term_pointer\":\"0x%llx\",\"province_pointer\":\"0x%llx\",\"province_id\":%d,\"core_owner\":\"%.3s\",\"province_owner\":\"%.3s\",\"selected\":%s,\"name_readable\":%s,\"record_complete\":%s}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),
            static_cast<unsigned long long>(observation_creation),id?id:"",action_id?action_id:"",i,
            static_cast<unsigned long long>(row.term),static_cast<unsigned long long>(row.province),
            row.province_id,row.core_owner_tag,row.province_owner_tag,row.selected?"true":"false",
            row.name_readable?"true":"false",row.record_complete?"true":"false");
        if (written>0 && static_cast<size_t>(written)<sizeof(message)) line(message);
    }
}
