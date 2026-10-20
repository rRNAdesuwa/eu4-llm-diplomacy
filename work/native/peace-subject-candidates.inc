// Bounded Release Subject/Transfer Subject candidate capture.  The native
// offer constructor already populates both families; this file only reads the
// typed term rows and, when explicitly requested, follows the verified
// persistent selection sequence.  It never dispatches a peace business
// method or submits an offer.

#include <windows.h>
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <cstdio>
#include <cstdarg>

static constexpr unsigned peace_subject_max_candidates=256u;
static constexpr unsigned peace_subject_max_countries=16u;
static constexpr size_t peace_subject_json_capacity=60000u;

static constexpr uintptr_t peace_release_subject_vtable_rva=0x1cd2940u;
static constexpr uintptr_t peace_transfer_subject_vtable_rva=0x1cd3b58u;
static constexpr uint32_t peace_release_subject_type=0x2d27u;
static constexpr uint32_t peace_transfer_subject_type=0x35f0u;
static constexpr uint32_t peace_release_subject_bucket=0x13u;
static constexpr uint32_t peace_transfer_subject_bucket=0x14u;
static constexpr uintptr_t peace_release_subject_descriptor_rva=0x99b050u;
static constexpr uintptr_t peace_transfer_subject_descriptor_rva=0x99b1b0u;
static constexpr uintptr_t peace_release_subject_recalculate_rva=0x9c1bc0u;
static constexpr uintptr_t peace_transfer_subject_recalculate_rva=0x9ccb30u;

struct PeaceSubjectRequest {
    bool release_subject=false;
    char country[4]{};
    bool selection_requested=false;
    char countries[peace_subject_max_countries][4]{};
    unsigned char country_count=0;
};

static bool peace_subject_valid_tag(const char* tag) noexcept {
    if (!tag || strlen(tag)!=3) return false;
    for (unsigned i=0;i<3;++i) {
        const char value=tag[i];
        if (!((value>='A' && value<='Z') || (value>='0' && value<='9'))) return false;
    }
    return true;
}

static bool peace_subject_parse_request(const char* target,bool release_subject,
    PeaceSubjectRequest& request) noexcept {
    request=PeaceSubjectRequest{};
    request.release_subject=release_subject;
    if (!target) return false;
    if (!strcmp(target,"-")) return true;
    if (!peace_subject_valid_tag(target)) return false;
    memcpy(request.country,target,4);
    memcpy(request.countries[0],target,4);
    request.country_count=1;
    request.selection_requested=true;
    return true;
}

static bool peace_subject_parse_countries(const char* csv,bool release_subject,
    PeaceSubjectRequest& request) noexcept {
    request=PeaceSubjectRequest{};
    request.release_subject=release_subject;
    if (!csv || !strcmp(csv,"-")) return true;
    const size_t length=strlen(csv);
    if (length==0 || length>63u) return false;
    size_t start=0;
    while (start<length) {
        size_t end=start;
        while (end<length && csv[end]!=',') ++end;
        if (end-start!=3u || request.country_count>=peace_subject_max_countries)
            return false;
        char tag[4]{};
        memcpy(tag,csv+start,3); tag[3]=0;
        if (!peace_subject_valid_tag(tag)) return false;
        for (unsigned i=0;i<request.country_count;++i)
            if (!memcmp(request.countries[i],tag,3)) return false;
        memcpy(request.countries[request.country_count],tag,4);
        ++request.country_count;
        if (end==length) break;
        start=end+1;
        if (start==length) return false;
    }
    if (request.country_count==0) return false;
    memcpy(request.country,request.countries[0],4);
    request.selection_requested=true;
    return true;
}

struct PeaceSubjectSpec {
    uint32_t type=0;
    uint32_t bucket=0;
    uintptr_t vtable=0;
    uintptr_t descriptor=0;
    uintptr_t recalculate=0;
    bool target_is_field22=false;
};

static PeaceSubjectSpec peace_subject_spec(const PeaceSubjectRequest& request) noexcept {
    return request.release_subject
        ?PeaceSubjectSpec{peace_release_subject_type,peace_release_subject_bucket,
            peace_release_subject_vtable_rva,peace_release_subject_descriptor_rva,
            peace_release_subject_recalculate_rva,false}
        :PeaceSubjectSpec{peace_transfer_subject_type,peace_transfer_subject_bucket,
            peace_transfer_subject_vtable_rva,peace_transfer_subject_descriptor_rva,
            peace_transfer_subject_recalculate_rva,true};
}

struct PeaceSubjectCandidate {
    uintptr_t term=0;
    uint64_t country=0;
    char country_tag[4]{};
    bool selected=false;
    bool record_complete=false;
};

struct PeaceSubjectQueryData {
    bool enabled=false;
    bool release_subject=false;
    PeaceSubjectCandidate* candidates=nullptr;
    char* json=nullptr;
    size_t json_size=0;
    size_t json_capacity=0;
    unsigned candidate_count=0;
    bool candidate_enumeration_complete=false;
    bool query_complete=false;
    uint64_t payer=0,claimant=0,requested_country=0;
    char requested_country_tag[4]{};
    uint64_t requested_countries[peace_subject_max_countries]{};
    char requested_country_tags[peace_subject_max_countries][4]{};
    unsigned char requested_country_count=0;
    bool selection_requested=false;
    bool requested_candidate_found=false;
    unsigned selected_term_count=0;
    bool parameters_matched=false;
    bool selection_applied=false;
    bool selection_records_complete=false;
    bool action_copy_matched=false;
    bool selection_delta_available=false;
    int32_t selection_delta_raw=0;
    const char* reason_code=nullptr;

    explicit PeaceSubjectQueryData(bool enable=false) noexcept : enabled(enable) {
        if (!enabled) return;
        candidates=static_cast<PeaceSubjectCandidate*>(HeapAlloc(GetProcessHeap(),
            HEAP_ZERO_MEMORY,sizeof(PeaceSubjectCandidate)*peace_subject_max_candidates));
        json=static_cast<char*>(HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,
            peace_subject_json_capacity));
        json_capacity=json?peace_subject_json_capacity:0;
        if (!candidates || !json) {
            if (candidates) HeapFree(GetProcessHeap(),0,candidates);
            if (json) HeapFree(GetProcessHeap(),0,json);
            candidates=nullptr; json=nullptr; json_capacity=0;
        }
    }
    PeaceSubjectQueryData(const PeaceSubjectQueryData&)=delete;
    PeaceSubjectQueryData& operator=(const PeaceSubjectQueryData&)=delete;
    ~PeaceSubjectQueryData() noexcept {
        if (candidates) HeapFree(GetProcessHeap(),0,candidates);
        if (json) HeapFree(GetProcessHeap(),0,json);
    }
    bool valid() const noexcept {
        return !enabled || (candidates && json
            && json_capacity==peace_subject_json_capacity);
    }
    bool outer_complete() const noexcept {
        return query_complete && candidate_enumeration_complete
            && selection_records_complete && action_copy_matched
            && (!selection_requested || parameters_matched);
    }
};

static bool peace_subject_country_tag(uint64_t handle,char (&tag)[4]) noexcept {
    const unsigned char a=static_cast<unsigned char>(handle&0xffu);
    const unsigned char b=static_cast<unsigned char>((handle>>8)&0xffu);
    const unsigned char c=static_cast<unsigned char>((handle>>16)&0xffu);
    const auto canonical=[](unsigned char value) noexcept {
        return (value>='A' && value<='Z') || (value>='0' && value<='9');
    };
    if (!canonical(a) || !canonical(b) || !canonical(c)) return false;
    tag[0]=static_cast<char>(a); tag[1]=static_cast<char>(b);
    tag[2]=static_cast<char>(c); tag[3]=0; return true;
}

static bool peace_subject_read_candidate(uintptr_t term,
    const PeaceSubjectSpec& spec,uint64_t payer,uint64_t claimant,
    PeaceSubjectCandidate& output) noexcept {
    output=PeaceSubjectCandidate{};
    output.term=term;
    uintptr_t vtable=0,country_record=0;
    uint64_t field10=0,field18=0,field22=0,extra30=0;
    unsigned char selected=0;
    if (!term || !read(term,vtable) || vtable!=base+spec.vtable
        || !read(term+0x10u,field10) || field10!=payer
        || !read(term+0x18u,field18) || field18!=claimant
        || !read(term+0x20u,selected) || selected>1u
        || !read(term+0x22u,field22) || !read(term+0x30u,extra30)) return false;
    const uint64_t country=spec.target_is_field22?field22:extra30;
    if (!country || !peace_query_country_pointer(country,country_record)
        || !peace_subject_country_tag(country,output.country_tag)) return false;
    output.country=country;
    output.selected=selected!=0;
    output.record_complete=true;
    return true;
}

static void peace_subject_reset(PeaceSubjectQueryData& data) noexcept {
    data.candidate_count=0; data.candidate_enumeration_complete=false;
    data.query_complete=false; data.requested_candidate_found=false;
    data.selected_term_count=0; data.parameters_matched=false;
    data.selection_applied=false; data.selection_records_complete=false;
    data.action_copy_matched=false; data.selection_delta_available=false;
    data.selection_delta_raw=0; data.reason_code=nullptr;
    if (data.candidates)
        for (unsigned i=0;i<peace_subject_max_candidates;++i)
            data.candidates[i]=PeaceSubjectCandidate{};
}

static unsigned peace_subject_request_count(const PeaceSubjectRequest& request) noexcept {
    if (!request.selection_requested) return 0;
    return request.country_count ? request.country_count : 1u;
}

static const char* peace_subject_request_tag(const PeaceSubjectRequest& request,
    unsigned index) noexcept {
    if (request.country_count) return request.countries[index];
    return request.country;
}

static bool peace_subject_query_enumerate(void* offer,
    PeaceSubjectQueryData& data,const PeaceSubjectRequest& request) noexcept {
    if (!data.enabled || !data.valid() || !offer) return false;
    peace_subject_reset(data);
    const PeaceSubjectSpec spec=peace_subject_spec(request);
    uintptr_t terms=0; unsigned count=0;
    if (!peace_payload_span(reinterpret_cast<uintptr_t>(offer),0x88u,8u,
        bridge::peace_payload::kMaxPeaceTerms,terms,count)) return false;
    data.query_complete=true; data.candidate_enumeration_complete=true;
    for (unsigned i=0;i<count;++i) {
        uintptr_t term=0,vtable=0;
        if (!read(terms+static_cast<uintptr_t>(i)*8u,term)
            || !term || !read(term,vtable)) {
            data.candidate_enumeration_complete=false; continue;
        }
        if (vtable!=base+spec.vtable) continue;
        if (data.candidate_count>=peace_subject_max_candidates) {
            data.candidate_enumeration_complete=false; continue;
        }
        PeaceSubjectCandidate row{};
        if (!peace_subject_read_candidate(term,spec,data.payer,data.claimant,row)) {
            data.candidate_enumeration_complete=false; continue;
        }
        for (unsigned j=0;j<data.candidate_count;++j)
            if (data.candidates[j].country==row.country) {
                data.candidate_enumeration_complete=false;
                row.record_complete=false;
            }
        if (!row.record_complete) data.candidate_enumeration_complete=false;
        data.candidates[data.candidate_count++]=row;
    }
    data.requested_candidate_found=false;
    if (data.selection_requested) {
        data.requested_candidate_found=true;
        for (unsigned requested=0;requested<data.requested_country_count;++requested) {
            bool found=false;
            for (unsigned i=0;i<data.candidate_count;++i)
                if (data.candidates[i].country==data.requested_countries[requested]) {
                    found=true; break;
                }
            if (!found) { data.requested_candidate_found=false; break; }
        }
    }
    return true;
}

static bool peace_subject_collect_selection(void* offer,
    const PeaceSubjectSpec& spec,uint64_t payer,uint64_t claimant,
    PeaceSubjectCandidate* rows,unsigned& count,bool& complete,
    unsigned& selected_count) noexcept {
    count=0; selected_count=0; complete=true;
    uintptr_t terms=0; unsigned term_count=0;
    if (!peace_payload_span(reinterpret_cast<uintptr_t>(offer),0x88u,8u,
        bridge::peace_payload::kMaxPeaceTerms,terms,term_count)) return false;
    for (unsigned i=0;i<term_count;++i) {
        uintptr_t term=0,vtable=0;
        if (!read(terms+static_cast<uintptr_t>(i)*8u,term)
            || !term || !read(term,vtable)) { complete=false; continue; }
        if (vtable!=base+spec.vtable) continue;
        if (count>=peace_subject_max_candidates) { complete=false; continue; }
        PeaceSubjectCandidate row{};
        if (!peace_subject_read_candidate(term,spec,payer,claimant,row)) {
            complete=false; continue;
        }
        if (!row.record_complete) complete=false;
        for (unsigned j=0;j<count;++j)
            if (rows[j].country==row.country) complete=false;
        if (row.selected) ++selected_count;
        rows[count++]=row;
    }
    return true;
}

static bool peace_subject_query_read_selection(void* offer,
    PeaceSubjectQueryData& data,const PeaceSubjectRequest& request,
    bool action_copy) noexcept {
    if (!data.enabled || !data.valid() || !offer) return false;
    const PeaceSubjectSpec spec=peace_subject_spec(request);
    PeaceSubjectCandidate rows[peace_subject_max_candidates]{};
    unsigned count=0,selected=0; bool complete=false;
    if (!peace_subject_collect_selection(offer,spec,data.payer,data.claimant,
        rows,count,complete,selected)) return false;
    if (action_copy) {
        data.action_copy_matched=count==data.candidate_count && complete
            && data.selection_records_complete;
        if (data.action_copy_matched) {
            for (unsigned i=0;i<count;++i) {
                bool found=false;
                for (unsigned j=0;j<data.candidate_count;++j)
                    if (rows[i].country==data.candidates[j].country
                        && rows[i].selected==data.candidates[j].selected
                        && rows[i].record_complete==data.candidates[j].record_complete) {
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
            if (data.candidates[i].country==rows[j].country) {
                data.candidates[i].selected=rows[j].selected; break;
            }
    }
    if (!data.selection_requested) {
        data.parameters_matched=false;
        return true;
    }
    data.parameters_matched=data.requested_candidate_found
        && data.selection_records_complete
        && selected==data.requested_country_count;
    if (data.parameters_matched) {
        for (unsigned requested=0;requested<data.requested_country_count;++requested) {
            bool found=false;
            for (unsigned i=0;i<count;++i)
                if (rows[i].country==data.requested_countries[requested]
                    && rows[i].selected) {
                    found=true; break;
                }
            if (!found) { data.parameters_matched=false; break; }
        }
    }
    return true;
}

static bool peace_subject_query_prepare(void* offer,uint64_t actor,uint64_t recipient,
    bool demand,const PeaceSubjectRequest& request,PeaceSubjectQueryData& data) noexcept {
    if (!data.valid()) return false;
    data.release_subject=request.release_subject;
    data.payer=peace_offer_payer(actor,recipient,demand);
    data.claimant=peace_offer_claimant(actor,recipient,demand);
    data.selection_requested=request.selection_requested;
    data.requested_country=0; data.requested_country_tag[0]=0;
    data.requested_country_count=0;
    memset(data.requested_countries,0,sizeof(data.requested_countries));
    memset(data.requested_country_tags,0,sizeof(data.requested_country_tags));
    memcpy(data.requested_country_tag,request.country,sizeof(data.requested_country_tag));
    if (request.selection_requested) {
        const unsigned requested_count=peace_subject_request_count(request);
        if (!requested_count || requested_count>peace_subject_max_countries) return false;
        data.requested_country_count=static_cast<unsigned char>(requested_count);
        for (unsigned i=0;i<requested_count;++i) {
            const char* tag=peace_subject_request_tag(request,i);
            if (!peace_subject_valid_tag(tag)
                || !alliance_query_country(tag,data.requested_countries[i])) return false;
            memcpy(data.requested_country_tags[i],tag,4);
        }
        data.requested_country=data.requested_countries[0];
        memcpy(data.requested_country_tag,data.requested_country_tags[0],4);
    }
    if (!peace_subject_query_enumerate(offer,data,request)) return false;
    if (!request.selection_requested) {
        data.selection_records_complete=data.candidate_enumeration_complete;
        data.reason_code="NATIVE_PEACE_SUBJECT_DISCOVERY_ONLY";
        return true;
    }
    if (!data.candidate_enumeration_complete || !data.requested_candidate_found) {
        data.selection_records_complete=data.candidate_enumeration_complete;
        data.reason_code=data.requested_candidate_found
            ?"NATIVE_PEACE_SUBJECT_CANDIDATE_ENUMERATION_INCOMPLETE"
            :"NATIVE_PEACE_SUBJECT_CANDIDATE_ABSENT";
        return true;
    }
    for (unsigned i=0;i<data.candidate_count;++i)
        if (data.candidates[i].selected) {
            data.selection_records_complete=true;
            data.reason_code="NATIVE_PEACE_SUBJECT_UNEXPECTED_PRESELECTION";
            return true;
        }
    const PeaceSubjectSpec spec=peace_subject_spec(request);
    uintptr_t descriptor_method=0,recalculate=0;
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
    uintptr_t address=reinterpret_cast<uintptr_t>(offer);
    unsigned char direction=0;
    if (!read(address+0x20u,direction) || direction>1u) return false;
    const unsigned requested_count=data.requested_country_count;
    PeaceSubjectCandidate* selected_candidates[peace_subject_max_countries]{};
    uint32_t selected_buckets[peace_subject_max_countries]{};
    alignas(8) unsigned char descriptor[16]{};
    for (unsigned requested=0;requested<requested_count;++requested) {
        for (unsigned i=0;i<data.candidate_count;++i)
            if (data.candidates[i].country==data.requested_countries[requested]) {
                selected_candidates[requested]=&data.candidates[i]; break;
            }
        if (!selected_candidates[requested]) return false;
        unsigned char selected=0;
        if (!read(selected_candidates[requested]->term+0x20u,selected) || selected
            || reinterpret_cast<Descriptor>(descriptor_method)(
                reinterpret_cast<void*>(selected_candidates[requested]->term),descriptor)
                    !=descriptor)
            return false;
        memcpy(&selected_buckets[requested],descriptor,sizeof(uint32_t));
        if (selected_buckets[requested]!=spec.bucket) return false;
    }
    uintptr_t buckets=0; unsigned bucket_count=0;
    if (!peace_payload_span(address,0xd0u,24u,bridge::peace_payload::kPeaceBucketCount,
        buckets,bucket_count)) return false;
    for (unsigned requested=0;requested<requested_count;++requested) {
        const unsigned bucket=selected_buckets[requested];
        if (bucket>=bucket_count) return false;
        const uintptr_t vector=buckets+static_cast<uintptr_t>(bucket)*24u;
        uintptr_t begin=0,end=0,capacity=0;
        if (!read(vector,begin) || !read(vector+8u,end) || !read(vector+16u,capacity)
            || end<begin || capacity<end || (end-begin)%8u || (capacity-begin)%8u
            || (end-begin)/8u>=bridge::peace_payload::kMaxPeaceTerms) return false;
        unsigned char selected=1;
        PeaceSubjectCandidate* candidate=selected_candidates[requested];
        candidate->selected=true;
        memcpy(reinterpret_cast<void*>(candidate->term+0x20u),&selected,1);
        reinterpret_cast<DependencyUpdate>(base+0x97a4e0)(offer,
            reinterpret_cast<void*>(candidate->term),1);
        if (!peace_payload_span(address,0xd0u,24u,bridge::peace_payload::kPeaceBucketCount,
            buckets,bucket_count) || bucket>=bucket_count) return false;
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
    }
    data.selection_applied=requested_count>0;
    const int64_t delta=static_cast<int64_t>(aggregate(offer,1))
        -static_cast<int64_t>(aggregate_before);
    if (delta>=(-2147483647ll-1) && delta<=2147483647ll) {
        data.selection_delta_available=true;
        data.selection_delta_raw=static_cast<int32_t>(delta);
    }
    if (!peace_subject_query_read_selection(offer,data,request,false)) return false;
    if (!data.parameters_matched && !data.reason_code)
        data.reason_code="NATIVE_PEACE_SUBJECT_SELECTION_MISMATCH";
    return true;
}

static bool peace_subject_json_append(char* output,size_t capacity,size_t& used,
    const char* text) noexcept {
    if (!output || !text || used>capacity) return false;
    const size_t length=strlen(text);
    if (length>=capacity-used) return false;
    memcpy(output+used,text,length); used+=length; output[used]=0; return true;
}

static bool peace_subject_json_append_format(char* output,size_t capacity,size_t& used,
    const char* format,...) noexcept {
    if (!output || !format || used>=capacity) return false;
    va_list args; va_start(args,format);
    const int needed=vsnprintf(output+used,capacity-used,format,args);
    va_end(args);
    if (needed<0 || static_cast<size_t>(needed)>=capacity-used) return false;
    used+=static_cast<size_t>(needed); return true;
}

static bool peace_subject_query_json(PeaceSubjectQueryData& data) noexcept {
    if (!data.enabled || !data.valid() || !data.json) return false;
    data.json[0]=0; data.json_size=0; size_t used=0;
    if (!peace_subject_json_append_format(data.json,data.json_capacity,used,
        "{\"action_id\":\"%s\",\"candidates\":[",
        data.release_subject?"release_subject":"transfer_subject")) return false;
    for (unsigned i=0;i<data.candidate_count;++i) {
        if (i && !peace_subject_json_append(data.json,data.json_capacity,used,",")) return false;
        const auto& row=data.candidates[i];
        if (!peace_subject_json_append_format(data.json,data.json_capacity,used,
            "{\"country\":\"%.3s\",\"selected\":%s,\"record_complete\":%s}",
            row.country_tag,row.selected?"true":"false",row.record_complete?"true":"false")) return false;
    }
    if (!peace_subject_json_append_format(data.json,data.json_capacity,used,
        "],\"candidate_count\":%u,\"candidate_enumeration_complete\":%s,\"selection_requested\":%s,\"requested_country\":",
        data.candidate_count,data.candidate_enumeration_complete?"true":"false",
        data.selection_requested?"true":"false")) return false;
    if (data.selection_requested) {
        if (!peace_subject_json_append_format(data.json,data.json_capacity,used,
            "\"%.3s\"",data.requested_country_tag)) return false;
    } else if (!peace_subject_json_append(data.json,data.json_capacity,used,"null")) return false;
    if (!peace_subject_json_append(data.json,data.json_capacity,used,
        ",\"requested_countries\":[")) return false;
    for (unsigned i=0;i<data.requested_country_count;++i) {
        if (i && !peace_subject_json_append(data.json,data.json_capacity,used,",")) return false;
        if (!peace_subject_json_append_format(data.json,data.json_capacity,used,
            "\"%.3s\"",data.requested_country_tags[i])) return false;
    }
    if (!peace_subject_json_append(data.json,data.json_capacity,used,"]")) return false;
    if (!peace_subject_json_append_format(data.json,data.json_capacity,used,
        ",\"requested_candidate_found\":%s,\"selected_term_count\":%u,\"parameters_matched\":%s,\"selection_applied\":%s,\"selection_records_complete\":%s,\"action_copy_matched\":%s,\"selection_delta_available\":%s,\"selection_delta_raw\":",
        data.requested_candidate_found?"true":"false",data.selected_term_count,
        data.parameters_matched?"true":"false",data.selection_applied?"true":"false",
        data.selection_records_complete?"true":"false",data.action_copy_matched?"true":"false",
        data.selection_delta_available?"true":"false")) return false;
    if (data.selection_delta_available) {
        if (!peace_subject_json_append_format(data.json,data.json_capacity,used,"%d",
            data.selection_delta_raw)) return false;
    } else if (!peace_subject_json_append(data.json,data.json_capacity,used,"null")) return false;
    if (!peace_subject_json_append(data.json,data.json_capacity,used,",\"reason_code\":")) return false;
    if (data.reason_code) {
        if (!peace_subject_json_append_format(data.json,data.json_capacity,used,"\"%s\"",
            data.reason_code)) return false;
    } else if (!peace_subject_json_append(data.json,data.json_capacity,used,"null")) return false;
    if (!peace_subject_json_append(data.json,data.json_capacity,used,"}")) return false;
    data.json_size=used; return true;
}

static void peace_subject_query_private(const char* id,
    const PeaceSubjectQueryData& data) noexcept {
    if (!data.enabled || !data.candidates) return;
    for (unsigned i=0;i<data.candidate_count;++i) {
        const auto& row=data.candidates[i];
        char message[900]{};
        const int written=snprintf(message,sizeof(message),
            "{\"event\":\"native_peace_subject_candidate_private\",\"private\":true,\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"action_id\":\"%s\",\"index\":%u,\"country\":\"%.3s\",\"selected\":%s,\"record_complete\":%s}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),
            static_cast<unsigned long long>(observation_creation),id?id:"",
            data.release_subject?"release_subject":"transfer_subject",i,
            row.country_tag,row.selected?"true":"false",row.record_complete?"true":"false");
        if (written>0 && static_cast<size_t>(written)<sizeof(message)) line(message);
    }
}
