// Bounded candidates for country-level peace terms.  The constructors and
// typed descriptors below are shipped-contract observations; this module
// only captures an existing offer and, when explicitly requested, follows
// the persistent selected-bit/vector/recalculate sequence.  It never builds
// a term, dispatches an offer, or calls a peace business method.

#include <windows.h>
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <cstdio>
#include <cstdarg>

static constexpr unsigned peace_country_max_candidates=256u;
static constexpr size_t peace_country_json_capacity=80000u;

enum class PeaceCountryKind : unsigned char {
    release_nation,
    force_vassal,
    pu,
    grant_independence
};

struct PeaceCountryRequest {
    PeaceCountryKind kind=PeaceCountryKind::release_nation;
    char country[4]{};
    char source[4]{}; // Release Nation host (+0x22) only; empty means payer.
    bool selection_requested=false;
};

struct PeaceCountrySpec {
    PeaceCountryKind kind=PeaceCountryKind::release_nation;
    unsigned variant=0;
    uintptr_t vtable=0;
    uint32_t type=0;
    uint32_t bucket=0;
    uintptr_t descriptor=0;
    uintptr_t recalculate=0;
    uintptr_t identity_offset=0x22u;
    bool has_extra30=false;
    bool release_source_field22=false;
};

static constexpr PeaceCountrySpec peace_country_release_spec{
    PeaceCountryKind::release_nation,0,0x1cd3100u,0x2d28u,0x0fu,
    0x99af10u,0x9b9660u,0x30u,true,true};
static constexpr PeaceCountrySpec peace_country_force_spec0{
    PeaceCountryKind::force_vassal,0,0x1cd4d78u,0x2d2cu,0x1u,
    0x99ae20u,0x9af6b0u,0x22u,true,false};
static constexpr PeaceCountrySpec peace_country_force_spec1{
    PeaceCountryKind::force_vassal,1,0x1cd1a90u,0x3c05u,0x2u,
    0x975aa0u,0x9af700u,0x22u,true,false};
static constexpr PeaceCountrySpec peace_country_pu_spec{
    PeaceCountryKind::pu,0,0x1cd3f38u,0x2d2au,0x1au,
    0x99b110u,0x9c67b0u,0x22u,false,false};
static constexpr PeaceCountrySpec peace_country_grant_spec{
    PeaceCountryKind::grant_independence,0,0x1cd2a90u,0x2e4au,0x12u,
    0x99b030u,0x9c0440u,0x22u,false,false};

static bool peace_country_kind_valid(PeaceCountryKind kind) noexcept {
    return kind==PeaceCountryKind::release_nation
        || kind==PeaceCountryKind::force_vassal
        || kind==PeaceCountryKind::pu
        || kind==PeaceCountryKind::grant_independence;
}

static const char* peace_country_kind_name(PeaceCountryKind kind) noexcept {
    switch (kind) {
    case PeaceCountryKind::release_nation: return "release_nation";
    case PeaceCountryKind::force_vassal: return "force_vassalization";
    case PeaceCountryKind::pu: return "form_personal_union";
    case PeaceCountryKind::grant_independence: return "grant_independence";
    }
    return "unknown";
}

static unsigned peace_country_spec_count(PeaceCountryKind kind) noexcept {
    return kind==PeaceCountryKind::force_vassal ? 2u
        : peace_country_kind_valid(kind) ? 1u : 0u;
}

static bool peace_country_get_spec(PeaceCountryKind kind,unsigned variant,
    PeaceCountrySpec& output) noexcept {
    if (kind==PeaceCountryKind::release_nation && variant==0u) {
        output=peace_country_release_spec; return true;
    }
    if (kind==PeaceCountryKind::force_vassal) {
        if (variant==0u) { output=peace_country_force_spec0; return true; }
        if (variant==1u) { output=peace_country_force_spec1; return true; }
    }
    if (kind==PeaceCountryKind::pu && variant==0u) {
        output=peace_country_pu_spec; return true;
    }
    if (kind==PeaceCountryKind::grant_independence && variant==0u) {
        output=peace_country_grant_spec; return true;
    }
    return false;
}

static bool peace_country_valid_tag(const char* tag) noexcept {
    if (!tag || strlen(tag)!=3u) return false;
    for (unsigned i=0;i<3u;++i) {
        const char value=tag[i];
        if (!((value>='A' && value<='Z') || (value>='0' && value<='9')))
            return false;
    }
    return true;
}

static bool peace_country_tag(uint64_t handle,char (&tag)[4]) noexcept {
    const unsigned char a=static_cast<unsigned char>(handle&0xffu);
    const unsigned char b=static_cast<unsigned char>((handle>>8)&0xffu);
    const unsigned char c=static_cast<unsigned char>((handle>>16)&0xffu);
    const auto canonical=[](unsigned char value) noexcept {
        return (value>='A' && value<='Z') || (value>='0' && value<='9');
    };
    if (!canonical(a) || !canonical(b) || !canonical(c)) return false;
    tag[0]=static_cast<char>(a); tag[1]=static_cast<char>(b);
    tag[2]=static_cast<char>(c); tag[3]=0;
    return true;
}

// This parser is intentionally narrow: Grant Independence may omit country;
// an omitted country means the native base field +0x22 must equal payer.
static bool peace_country_parse_request(PeaceCountryKind kind,
    const char* country,const char* source,bool selection_requested,
    PeaceCountryRequest& request) noexcept {
    request=PeaceCountryRequest{};
    request.kind=kind;
    request.selection_requested=selection_requested;
    if (!peace_country_kind_valid(kind) || !country || !source) return false;
    const bool country_empty=!country[0] || !strcmp(country,"-");
    const bool source_empty=!source[0] || !strcmp(source,"-");
    if (!country_empty) {
        if (!peace_country_valid_tag(country)) return false;
        memcpy(request.country,country,4);
    }
    if (!source_empty) {
        if (kind!=PeaceCountryKind::release_nation
            || !peace_country_valid_tag(source)) return false;
        memcpy(request.source,source,4);
    }
    if (!selection_requested) {
        return request.country[0]==0 && request.source[0]==0;
    }
    if (kind==PeaceCountryKind::grant_independence)
        return request.country[0]==0 || peace_country_valid_tag(request.country);
    if (!request.country[0]) return false;
    return kind==PeaceCountryKind::release_nation
        ?(!request.source[0] || peace_country_valid_tag(request.source))
        :request.source[0]==0;
}

struct PeaceCountryCandidate {
    uintptr_t term=0;
    PeaceCountryKind kind=PeaceCountryKind::release_nation;
    unsigned variant=0;
    uint32_t type=0;
    uint32_t bucket=0;
    uint64_t field10=0;
    uint64_t field18=0;
    uint64_t field22=0;
    uint64_t extra30=0; // Opaque for Force Vassal; no role is inferred.
    uint64_t country=0; // Release +0x30; otherwise the contract identity field.
    uint64_t source=0;  // Release +0x22; zero for other families.
    char country_tag[4]{};
    char source_tag[4]{};
    char extra30_tag[4]{};
    bool selected=false;
    bool record_complete=false;
    bool typed_descriptor_valid=false;
};

struct PeaceCountryQueryData {
    bool enabled=false;
    PeaceCountryKind kind=PeaceCountryKind::release_nation;
    PeaceCountryCandidate* candidates=nullptr;
    char* json=nullptr;
    size_t json_size=0;
    size_t json_capacity=0;
    unsigned candidate_count=0;
    bool candidate_enumeration_complete=false;
    bool query_complete=false;
    uint64_t payer=0;
    uint64_t claimant=0;
    char payer_tag[4]{};
    char claimant_tag[4]{};
    uint64_t requested_country=0;
    uint64_t requested_source=0;
    char requested_country_tag[4]{};
    char requested_source_tag[4]{};
    bool requested_country_is_payer=false;
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

    explicit PeaceCountryQueryData(bool enable=false) noexcept : enabled(enable) {
        if (!enabled) return;
        candidates=static_cast<PeaceCountryCandidate*>(HeapAlloc(GetProcessHeap(),
            HEAP_ZERO_MEMORY,sizeof(PeaceCountryCandidate)*peace_country_max_candidates));
        json=static_cast<char*>(HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,
            peace_country_json_capacity));
        json_capacity=json?peace_country_json_capacity:0;
        if (!candidates || !json) {
            if (candidates) HeapFree(GetProcessHeap(),0,candidates);
            if (json) HeapFree(GetProcessHeap(),0,json);
            candidates=nullptr; json=nullptr; json_capacity=0;
        }
    }
    PeaceCountryQueryData(const PeaceCountryQueryData&)=delete;
    PeaceCountryQueryData& operator=(const PeaceCountryQueryData&)=delete;
    PeaceCountryQueryData(PeaceCountryQueryData&&)=delete;
    PeaceCountryQueryData& operator=(PeaceCountryQueryData&&)=delete;
    ~PeaceCountryQueryData() noexcept {
        if (candidates) HeapFree(GetProcessHeap(),0,candidates);
        if (json) HeapFree(GetProcessHeap(),0,json);
    }
    bool valid() const noexcept {
        return !enabled || (candidates && json
            && json_capacity==peace_country_json_capacity);
    }
    bool outer_complete() const noexcept {
        return query_complete && candidate_enumeration_complete
            && selection_records_complete && action_copy_matched
            && (!selection_requested || parameters_matched);
    }
};

static void peace_country_reset(PeaceCountryQueryData& data) noexcept {
    data.candidate_count=0;
    data.candidate_enumeration_complete=false;
    data.query_complete=false;
    data.requested_candidate_found=false;
    data.selected_term_count=0;
    data.parameters_matched=false;
    data.selection_applied=false;
    data.selection_records_complete=false;
    data.action_copy_matched=false;
    data.selection_delta_available=false;
    data.selection_delta_raw=0;
    data.reason_code=nullptr;
    if (data.candidates)
        for (unsigned i=0;i<peace_country_max_candidates;++i)
            data.candidates[i]=PeaceCountryCandidate{};
}

static bool peace_country_spec_for_term(uintptr_t term,
    PeaceCountryKind kind,PeaceCountrySpec& output,uint32_t& discriminator) noexcept {
    uintptr_t vtable=0;
    discriminator=0;
    if (!term || !read(term,vtable)) return false;
    const unsigned count=peace_country_spec_count(kind);
    for (unsigned variant=0;variant<count;++variant) {
        PeaceCountrySpec candidate{};
        if (!peace_country_get_spec(kind,variant,candidate)) continue;
        if (vtable==base+candidate.vtable) {
            output=candidate;
            // The object word at +8 is not a shipped type discriminator for
            // these families.  Identity is the verified vtable/descriptor/
            // bucket contract; expose the static whitelist type instead.
            discriminator=candidate.type;
            return true;
        }
    }
    return false;
}

static bool peace_country_descriptor_check(uintptr_t term,
    const PeaceCountrySpec& spec) noexcept {
    uintptr_t method=0;
    if (!read(base+spec.vtable+0x78u,method)
        || method!=base+spec.descriptor) return false;
    using Descriptor=void* (*)(void*,void*);
    alignas(8) unsigned char descriptor[16]{};
    if (reinterpret_cast<Descriptor>(method)(reinterpret_cast<void*>(term),descriptor)
            !=descriptor) return false;
    uint32_t bucket=0;
    memcpy(&bucket,descriptor,sizeof(bucket));
    return bucket==spec.bucket;
}

static bool peace_country_read_candidate(uintptr_t term,
    const PeaceCountrySpec& spec,uint64_t payer,uint64_t claimant,
    PeaceCountryCandidate& output) noexcept {
    output=PeaceCountryCandidate{};
    output.term=term;
    output.kind=spec.kind;
    output.variant=spec.variant;
    output.type=spec.type;
    output.bucket=spec.bucket;
    uintptr_t vtable=0;
    unsigned char selected=0;
    if (!term || !read(term,vtable) || vtable!=base+spec.vtable
        || !read(term+0x20u,selected) || selected>1u
        || !read(term+0x10u,output.field10)
        || !read(term+0x18u,output.field18)
        || !read(term+0x22u,output.field22)) return false;
    if (!peace_country_descriptor_check(term,spec)) return false;
    output.typed_descriptor_valid=true;
    if (spec.has_extra30 && !read(term+0x30u,output.extra30)) return false;
    output.selected=selected!=0;
    output.country=spec.identity_offset==0x30u?output.extra30:output.field22;
    output.source=spec.release_source_field22?output.field22:0;
    if (!output.country || !peace_country_tag(output.country,output.country_tag)) return false;
    if (spec.release_source_field22
        && (!output.source || !peace_country_tag(output.source,output.source_tag))) return false;
    if (spec.has_extra30) peace_country_tag(output.extra30,output.extra30_tag);
    // Term context is part of the copy contract.  Grant's base field is
    // checked against payer during request matching, not renamed here.
    output.record_complete=output.field10==payer && output.field18==claimant;
    return output.record_complete;
}

static bool peace_country_same_key(const PeaceCountryCandidate& left,
    const PeaceCountryCandidate& right) noexcept {
    if (left.kind!=right.kind || left.country!=right.country) return false;
    return left.kind!=PeaceCountryKind::release_nation
        || left.source==right.source;
}

static bool peace_country_candidate_matches(const PeaceCountryCandidate& row,
    const PeaceCountryQueryData& data) noexcept {
    if (!row.record_complete || row.kind!=data.kind) return false;
    if (data.kind==PeaceCountryKind::grant_independence) {
        if (row.field22!=data.payer) return false;
        return !data.requested_country || row.field22==data.requested_country;
    }
    if (!data.requested_country || row.country!=data.requested_country) return false;
    return data.kind!=PeaceCountryKind::release_nation
        || row.source==data.requested_source;
}

static bool peace_country_query_enumerate(void* offer,
    PeaceCountryQueryData& data) noexcept {
    if (!data.enabled || !data.valid() || !offer
        || !peace_country_kind_valid(data.kind)) return false;
    peace_country_reset(data);
    uintptr_t terms=0; unsigned count=0;
    if (!peace_payload_span(reinterpret_cast<uintptr_t>(offer),0x88u,8u,
        bridge::peace_payload::kMaxPeaceTerms,terms,count)) return false;
    data.query_complete=true;
    data.candidate_enumeration_complete=true;
    for (unsigned i=0;i<count;++i) {
        uintptr_t term=0;
        if (!read(terms+static_cast<uintptr_t>(i)*8u,term) || !term) {
            data.candidate_enumeration_complete=false; continue;
        }
        PeaceCountrySpec spec{}; uint32_t discriminator=0;
        if (!peace_country_spec_for_term(term,data.kind,spec,discriminator)) continue;
        if (data.candidate_count>=peace_country_max_candidates) {
            data.candidate_enumeration_complete=false; continue;
        }
        PeaceCountryCandidate row{};
        if (!peace_country_read_candidate(term,spec,data.payer,data.claimant,
            row)) {
            data.candidate_enumeration_complete=false; continue;
        }
        for (unsigned j=0;j<data.candidate_count;++j) {
            if (peace_country_same_key(data.candidates[j],row)) {
                data.candidate_enumeration_complete=false;
                row.record_complete=false;
                break;
            }
        }
        data.candidates[data.candidate_count++]=row;
    }
    data.requested_candidate_found=false;
    data.selected_term_count=0;
    for (unsigned i=0;i<data.candidate_count;++i) {
        if (data.candidates[i].selected) ++data.selected_term_count;
        if (data.selection_requested
            && peace_country_candidate_matches(data.candidates[i],data)) {
            if (data.requested_candidate_found) {
                data.candidate_enumeration_complete=false;
                data.requested_candidate_found=false;
            } else {
                data.requested_candidate_found=true;
            }
        }
    }
    return true;
}

static bool peace_country_collect_selection(void* offer,
    PeaceCountryQueryData& data,PeaceCountryCandidate* rows,unsigned& count,
    unsigned& selected_count,bool& complete) noexcept {
    count=0; selected_count=0; complete=true;
    uintptr_t terms=0; unsigned term_count=0;
    if (!peace_payload_span(reinterpret_cast<uintptr_t>(offer),0x88u,8u,
        bridge::peace_payload::kMaxPeaceTerms,terms,term_count)) return false;
    for (unsigned i=0;i<term_count;++i) {
        uintptr_t term=0;
        if (!read(terms+static_cast<uintptr_t>(i)*8u,term) || !term) {
            complete=false; continue;
        }
        PeaceCountrySpec spec{}; uint32_t discriminator=0;
        if (!peace_country_spec_for_term(term,data.kind,spec,discriminator)) continue;
        if (count>=peace_country_max_candidates) { complete=false; continue; }
        PeaceCountryCandidate row{};
        if (!peace_country_read_candidate(term,spec,data.payer,data.claimant,row)) {
            complete=false; continue;
        }
        if (row.selected) {
            ++selected_count;
            row.typed_descriptor_valid=peace_country_descriptor_check(term,spec);
            if (!row.typed_descriptor_valid) complete=false;
        }
        for (unsigned j=0;j<count;++j) {
            if (peace_country_same_key(rows[j],row)) {
                complete=false;
                row.record_complete=false;
                break;
            }
        }
        rows[count++]=row;
    }
    return true;
}

static bool peace_country_candidate_equal(const PeaceCountryCandidate& left,
    const PeaceCountryCandidate& right) noexcept {
    return left.kind==right.kind && left.variant==right.variant
        && left.type==right.type && left.bucket==right.bucket
        && left.field10==right.field10 && left.field18==right.field18
        && left.field22==right.field22 && left.extra30==right.extra30
        && left.country==right.country && left.source==right.source
        && left.selected==right.selected
        && left.record_complete==right.record_complete
        && left.typed_descriptor_valid==right.typed_descriptor_valid;
}

static bool peace_country_query_read_selection(void* offer,
    PeaceCountryQueryData& data,bool action_copy) noexcept {
    if (!data.enabled || !data.valid() || !offer) return false;
    PeaceCountryCandidate* rows=static_cast<PeaceCountryCandidate*>(HeapAlloc(
        GetProcessHeap(),HEAP_ZERO_MEMORY,
        sizeof(PeaceCountryCandidate)*peace_country_max_candidates));
    if (!rows) return false;
    unsigned count=0,selected=0; bool complete=false;
    const bool collected=peace_country_collect_selection(offer,data,rows,count,
        selected,complete);
    if (!collected) {
        HeapFree(GetProcessHeap(),0,rows); return false;
    }
    if (action_copy) {
        data.action_copy_matched=count==data.candidate_count && complete
            && data.selection_records_complete;
        if (data.action_copy_matched) {
            for (unsigned i=0;i<count;++i) {
                bool found=false;
                for (unsigned j=0;j<data.candidate_count;++j)
                    if (peace_country_candidate_equal(rows[i],data.candidates[j])) {
                        found=true; break;
                    }
                if (!found) { data.action_copy_matched=false; break; }
            }
        }
        HeapFree(GetProcessHeap(),0,rows);
        return true;
    }
    data.selected_term_count=selected;
    data.selection_records_complete=complete;
    for (unsigned i=0;i<data.candidate_count;++i) {
        data.candidates[i].selected=false;
        data.candidates[i].typed_descriptor_valid=false;
        for (unsigned j=0;j<count;++j)
            if (peace_country_same_key(data.candidates[i],rows[j])) {
                data.candidates[i].selected=rows[j].selected;
                data.candidates[i].typed_descriptor_valid=rows[j].typed_descriptor_valid;
                break;
            }
    }
    if (!data.selection_requested) {
        data.parameters_matched=false;
        HeapFree(GetProcessHeap(),0,rows);
        return true;
    }
    data.parameters_matched=data.requested_candidate_found
        && data.selection_records_complete && selected==1u;
    if (data.parameters_matched) {
        bool found=false;
        for (unsigned i=0;i<count;++i)
            if (rows[i].selected && peace_country_candidate_matches(rows[i],data)
                && rows[i].typed_descriptor_valid && rows[i].record_complete) {
                found=true; break;
            }
        data.parameters_matched=found;
    }
    HeapFree(GetProcessHeap(),0,rows);
    return true;
}

// Explicit name for the action-copy verification call used by the observer;
// it performs no mutation and only compares the cloned native term records.
static bool peace_country_verify_source_copy(void* action_copy_offer,
    PeaceCountryQueryData& data) noexcept {
    return peace_country_query_read_selection(action_copy_offer,data,true);
}

static bool peace_country_query_prepare(void* offer,uint64_t actor,uint64_t recipient,
    bool demand,const PeaceCountryRequest& request,
    PeaceCountryQueryData& data) noexcept {
    if (!data.valid() || !peace_country_kind_valid(request.kind)) return false;
    if (!request.selection_requested
        && (request.country[0] || request.source[0])) return false;
    data.kind=request.kind;
    data.payer=peace_offer_payer(actor,recipient,demand);
    data.claimant=peace_offer_claimant(actor,recipient,demand);
    data.payer_tag[0]=0; data.claimant_tag[0]=0;
    if (!peace_country_tag(data.payer,data.payer_tag)
        || !peace_country_tag(data.claimant,data.claimant_tag)) return false;
    data.selection_requested=request.selection_requested;
    data.requested_country=0; data.requested_source=0;
    data.requested_country_tag[0]=0; data.requested_source_tag[0]=0;
    data.requested_country_is_payer=false;
    if (request.selection_requested) {
        if (request.country[0]) {
            if (!peace_country_valid_tag(request.country)
                || !alliance_query_country(request.country,data.requested_country))
                return false;
            memcpy(data.requested_country_tag,request.country,4);
        } else if (request.kind==PeaceCountryKind::grant_independence) {
            data.requested_country_is_payer=true;
        } else return false;
        if (request.kind==PeaceCountryKind::release_nation) {
            if (request.source[0]) {
                if (!peace_country_valid_tag(request.source)
                    || !alliance_query_country(request.source,data.requested_source))
                    return false;
                memcpy(data.requested_source_tag,request.source,4);
            } else {
                data.requested_source=data.payer;
                memcpy(data.requested_source_tag,data.payer_tag,4);
            }
        } else if (request.source[0]) return false;
    }
    if (!peace_country_query_enumerate(offer,data)) return false;
    if (!request.selection_requested) {
        data.selection_records_complete=data.candidate_enumeration_complete;
        data.reason_code="NATIVE_PEACE_COUNTRY_DISCOVERY_ONLY";
        return true;
    }
    if (!data.candidate_enumeration_complete || !data.requested_candidate_found) {
        data.selection_records_complete=data.candidate_enumeration_complete;
        data.reason_code=data.requested_candidate_found
            ?"NATIVE_PEACE_COUNTRY_CANDIDATE_ENUMERATION_INCOMPLETE"
            :"NATIVE_PEACE_COUNTRY_CANDIDATE_ABSENT";
        return true;
    }
    for (unsigned i=0;i<data.candidate_count;++i)
        if (data.candidates[i].selected) {
            data.selection_records_complete=true;
            data.reason_code="NATIVE_PEACE_COUNTRY_UNEXPECTED_PRESELECTION";
            return true;
        }
    PeaceCountryCandidate* selected_candidate=nullptr;
    for (unsigned i=0;i<data.candidate_count;++i)
        if (peace_country_candidate_matches(data.candidates[i],data)) {
            if (selected_candidate) return false;
            selected_candidate=&data.candidates[i];
        }
    PeaceCountrySpec spec{};
    if (!selected_candidate
        || !peace_country_get_spec(request.kind,selected_candidate->variant,spec)
        || !peace_country_descriptor_check(selected_candidate->term,spec)) return false;
    selected_candidate->typed_descriptor_valid=true;
    uintptr_t recalculate=0;
    if (!read(base+spec.vtable+0x118u,recalculate)
        || recalculate!=base+spec.recalculate) return false;
    using DependencyUpdate=void (*)(void*,void*,unsigned char);
    using Recalculate=void (*)(void*,void*,unsigned char,unsigned char);
    using Append=void (*)(void*,uintptr_t,const uintptr_t*);
    using Aggregate=int32_t (*)(void*,unsigned char);
    const auto aggregate=reinterpret_cast<Aggregate>(base+0x978ed0);
    const int32_t aggregate_before=aggregate(offer,1);
    const uintptr_t address=reinterpret_cast<uintptr_t>(offer);
    unsigned char direction=0;
    if (!read(address+0x20u,direction) || direction>1u) return false;
    uintptr_t buckets=0; unsigned bucket_count=0;
    if (!peace_payload_span(address,0xd0u,24u,bridge::peace_payload::kPeaceBucketCount,
        buckets,bucket_count) || spec.bucket>=bucket_count) return false;
    uintptr_t vector=buckets+static_cast<uintptr_t>(spec.bucket)*24u;
    uintptr_t begin=0,end=0,capacity=0;
    if (!read(vector,begin) || !read(vector+8u,end) || !read(vector+16u,capacity)
        || end<begin || capacity<end || (end-begin)%8u || (capacity-begin)%8u
        || (end-begin)/8u>=bridge::peace_payload::kMaxPeaceTerms) return false;
    unsigned char selected=1;
    selected_candidate->selected=true;
    memcpy(reinterpret_cast<void*>(selected_candidate->term+0x20u),&selected,1);
    reinterpret_cast<DependencyUpdate>(base+0x97a4e0)(offer,
        reinterpret_cast<void*>(selected_candidate->term),1);
    if (!peace_payload_span(address,0xd0u,24u,bridge::peace_payload::kPeaceBucketCount,
        buckets,bucket_count) || spec.bucket>=bucket_count) return false;
    vector=buckets+static_cast<uintptr_t>(spec.bucket)*24u;
    if (!read(vector,begin) || !read(vector+8u,end) || !read(vector+16u,capacity)
        || end<begin || capacity<end || (end-begin)%8u || (capacity-begin)%8u
        || (end-begin)/8u>=bridge::peace_payload::kMaxPeaceTerms) return false;
    if (end==capacity)
        reinterpret_cast<Append>(base+0xcc220)(reinterpret_cast<void*>(vector),end,
            &selected_candidate->term);
    else {
        memcpy(reinterpret_cast<void*>(end),&selected_candidate->term,
            sizeof(selected_candidate->term));
        end+=8u; memcpy(reinterpret_cast<void*>(vector+8u),&end,sizeof(end));
    }
    reinterpret_cast<Recalculate>(recalculate)(
        reinterpret_cast<void*>(selected_candidate->term),
        reinterpret_cast<void*>(address+0xe8u),direction,0);
    reinterpret_cast<DependencyUpdate>(base+0x97a4e0)(offer,
        reinterpret_cast<void*>(selected_candidate->term),0);
    data.selection_applied=true;
    const int64_t delta=static_cast<int64_t>(aggregate(offer,1))
        -static_cast<int64_t>(aggregate_before);
    if (delta>=(-2147483647ll-1) && delta<=2147483647ll) {
        data.selection_delta_available=true;
        data.selection_delta_raw=static_cast<int32_t>(delta);
    }
    if (!peace_country_query_read_selection(offer,data,false)) return false;
    if (!data.parameters_matched && !data.reason_code)
        data.reason_code="NATIVE_PEACE_COUNTRY_SELECTION_MISMATCH";
    return true;
}

static bool peace_country_json_append(char* output,size_t capacity,size_t& used,
    const char* text) noexcept {
    if (!output || !text || used>capacity) return false;
    const size_t length=strlen(text);
    if (length>=capacity-used) return false;
    memcpy(output+used,text,length); used+=length; output[used]=0; return true;
}

static bool peace_country_json_append_format(char* output,size_t capacity,
    size_t& used,const char* format,...) noexcept {
    if (!output || !format || used>=capacity) return false;
    va_list args; va_start(args,format);
    const int needed=vsnprintf(output+used,capacity-used,format,args);
    va_end(args);
    if (needed<0 || static_cast<size_t>(needed)>=capacity-used) return false;
    used+=static_cast<size_t>(needed); return true;
}

static bool peace_country_json_tag(char* output,size_t capacity,size_t& used,
    const char (&tag)[4]) noexcept {
    if (tag[0]) return peace_country_json_append_format(output,capacity,used,
        "\"%.3s\"",tag);
    return peace_country_json_append(output,capacity,used,"null");
}

static bool peace_country_query_json(PeaceCountryQueryData& data) noexcept {
    if (!data.enabled || !data.valid() || !data.json) return false;
    data.json[0]=0; data.json_size=0; size_t used=0;
    if (!peace_country_json_append_format(data.json,data.json_capacity,used,
        "{\"action_id\":\"%s\",\"candidates\":[",
        peace_country_kind_name(data.kind))) return false;
    for (unsigned i=0;i<data.candidate_count;++i) {
        if (i && !peace_country_json_append(data.json,data.json_capacity,used,","))
            return false;
        const auto& row=data.candidates[i];
        // For Grant Independence, country is the observed field22/base value;
        // it is not named as the liberated nation.  The top-level payer and
        // claimant fields remain the authoritative public role context.
        if (!peace_country_json_append_format(data.json,data.json_capacity,used,
            "{\"country\":")) return false;
        if (!peace_country_json_tag(data.json,data.json_capacity,used,row.country_tag))
            return false;
        if (!peace_country_json_append(data.json,data.json_capacity,used,
            ",\"source\":")) return false;
        if (!peace_country_json_tag(data.json,data.json_capacity,used,row.source_tag))
            return false;
        if (!peace_country_json_append(data.json,data.json_capacity,used,
            ",\"field22\":")) return false;
        char field22_tag[4]{}; peace_country_tag(row.field22,field22_tag);
        if (!peace_country_json_tag(data.json,data.json_capacity,used,field22_tag))
            return false;
        if (!peace_country_json_append(data.json,data.json_capacity,used,
            ",\"extra30\":")) return false;
        if (!peace_country_json_tag(data.json,data.json_capacity,used,row.extra30_tag))
            return false;
        if (!peace_country_json_append_format(data.json,data.json_capacity,used,
            ",\"selected\":%s,\"record_complete\":%s,\"typed_descriptor_valid\":%s,\"variant\":%u}",
            row.selected?"true":"false",row.record_complete?"true":"false",
            row.typed_descriptor_valid?"true":"false",row.variant)) return false;
    }
    if (!peace_country_json_append_format(data.json,data.json_capacity,used,
        "],\"candidate_count\":%u,\"candidate_enumeration_complete\":%s,\"selection_requested\":%s,\"requested_country\":",
        data.candidate_count,data.candidate_enumeration_complete?"true":"false",
        data.selection_requested?"true":"false")) return false;
    if (!peace_country_json_tag(data.json,data.json_capacity,used,
        data.requested_country_tag)) return false;
    if (!peace_country_json_append(data.json,data.json_capacity,used,
        ",\"requested_source\":")) return false;
    if (!peace_country_json_tag(data.json,data.json_capacity,used,
        data.requested_source_tag)) return false;
    if (!peace_country_json_append_format(data.json,data.json_capacity,used,
        ",\"requested_country_is_payer\":%s,\"payer\":",
        data.requested_country_is_payer?"true":"false")) return false;
    if (!peace_country_json_tag(data.json,data.json_capacity,used,data.payer_tag))
        return false;
    if (!peace_country_json_append(data.json,data.json_capacity,used,
        ",\"claimant\":")) return false;
    if (!peace_country_json_tag(data.json,data.json_capacity,used,data.claimant_tag))
        return false;
    if (!peace_country_json_append_format(data.json,data.json_capacity,used,
        ",\"requested_candidate_found\":%s,\"selected_term_count\":%u,\"parameters_matched\":%s,\"selection_applied\":%s,\"selection_records_complete\":%s,\"action_copy_matched\":%s,\"selection_delta_available\":%s,\"selection_delta_raw\":",
        data.requested_candidate_found?"true":"false",data.selected_term_count,
        data.parameters_matched?"true":"false",data.selection_applied?"true":"false",
        data.selection_records_complete?"true":"false",data.action_copy_matched?"true":"false",
        data.selection_delta_available?"true":"false")) return false;
    if (data.selection_delta_available) {
        if (!peace_country_json_append_format(data.json,data.json_capacity,used,"%d",
            data.selection_delta_raw)) return false;
    } else if (!peace_country_json_append(data.json,data.json_capacity,used,"null"))
        return false;
    if (!peace_country_json_append(data.json,data.json_capacity,used,",\"reason_code\":"))
        return false;
    if (data.reason_code) {
        if (!peace_country_json_append_format(data.json,data.json_capacity,used,
            "\"%s\"",data.reason_code)) return false;
    } else if (!peace_country_json_append(data.json,data.json_capacity,used,"null"))
        return false;
    if (!peace_country_json_append(data.json,data.json_capacity,used,"}")) return false;
    data.json_size=used; return true;
}

static void peace_country_query_private(const char* id,
    const PeaceCountryQueryData& data) noexcept {
    if (!data.enabled || !data.candidates) return;
    for (unsigned i=0;i<data.candidate_count;++i) {
        const auto& row=data.candidates[i];
        char message[1200]{};
        const int written=snprintf(message,sizeof(message),
            "{\"event\":\"native_peace_country_candidate_private\",\"private\":true,\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"action_id\":\"%s\",\"index\":%u,\"country\":\"%s\",\"source\":\"%s\",\"field22\":\"%s\",\"extra30\":\"%s\",\"selected\":%s,\"record_complete\":%s,\"typed_descriptor_valid\":%s}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),
            static_cast<unsigned long long>(observation_creation),id?id:"",
            peace_country_kind_name(data.kind),i,
            row.country_tag[0]?row.country_tag:"-",
            row.source_tag[0]?row.source_tag:"-",
            row.field22?"present":"-",row.extra30?"present":"-",
            row.selected?"true":"false",row.record_complete?"true":"false",
            row.typed_descriptor_valid?"true":"false");
        if (written>0 && static_cast<size_t>(written)<sizeof(message)) line(message);
    }
}

// Query18 uses one request object per country-term family.  Keeping the
// family pointers in this small aggregate lets the query runner prepare and
// copy-check all requested native vectors without introducing a second
// selection implementation.  A null pointer means that the family was not
// present in the wire mask; an object with selection_requested=false is the
// explicit discovery form.
struct PeaceCountryRequestSet {
    const PeaceCountryRequest* release_nation=nullptr;
    const PeaceCountryRequest* force_vassal=nullptr;
    const PeaceCountryRequest* pu=nullptr;
    const PeaceCountryRequest* grant_independence=nullptr;
    const char* force_vassal_beneficiary=nullptr;
    const char* pu_beneficiary=nullptr;

    bool any() const noexcept {
        return release_nation || force_vassal || pu || grant_independence;
    }
};

static constexpr size_t peace_country_query_set_json_capacity=
    peace_country_json_capacity*4u+256u;

struct PeaceCountryQuerySet {
    PeaceCountryQueryData release_nation;
    PeaceCountryQueryData force_vassal;
    PeaceCountryQueryData pu;
    PeaceCountryQueryData grant_independence;
    char* json=nullptr;
    size_t json_size=0;
    size_t json_capacity=0;

    explicit PeaceCountryQuerySet(const PeaceCountryRequestSet& requests) noexcept
        : release_nation(requests.release_nation!=nullptr),
          force_vassal(requests.force_vassal!=nullptr),
          pu(requests.pu!=nullptr),
          grant_independence(requests.grant_independence!=nullptr) {
        if (!any()) return;
        json=static_cast<char*>(HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,
            peace_country_query_set_json_capacity));
        json_capacity=json?peace_country_query_set_json_capacity:0;
    }
    PeaceCountryQuerySet(const PeaceCountryQuerySet&)=delete;
    PeaceCountryQuerySet& operator=(const PeaceCountryQuerySet&)=delete;
    PeaceCountryQuerySet(PeaceCountryQuerySet&&)=delete;
    PeaceCountryQuerySet& operator=(PeaceCountryQuerySet&&)=delete;
    ~PeaceCountryQuerySet() noexcept {
        if (json) HeapFree(GetProcessHeap(),0,json);
    }
    bool any() const noexcept {
        return release_nation.enabled || force_vassal.enabled
            || pu.enabled || grant_independence.enabled;
    }
    bool valid() const noexcept {
        return !any() || (json && json_capacity==peace_country_query_set_json_capacity
            && release_nation.valid() && force_vassal.valid()
            && pu.valid() && grant_independence.valid());
    }
    bool parameters_matched() const noexcept {
        return (!release_nation.enabled || (release_nation.selection_requested
                && release_nation.parameters_matched))
            && (!force_vassal.enabled || (force_vassal.selection_requested
                && force_vassal.parameters_matched))
            && (!pu.enabled || (pu.selection_requested && pu.parameters_matched))
            && (!grant_independence.enabled || (grant_independence.selection_requested
                && grant_independence.parameters_matched));
    }
    bool outer_complete() const noexcept {
        return (!release_nation.enabled || release_nation.outer_complete())
            && (!force_vassal.enabled || force_vassal.outer_complete())
            && (!pu.enabled || pu.outer_complete())
            && (!grant_independence.enabled || grant_independence.outer_complete());
    }
};

static bool peace_country_set_discovery_request(
    const PeaceCountryRequest& request,PeaceCountryRequest& discovery) noexcept {
    discovery=request;
    discovery.country[0]=0;
    discovery.source[0]=0;
    discovery.selection_requested=false;
    return true;
}

static void peace_country_set_requested_tags(const PeaceCountryRequest& request,
    PeaceCountryQueryData& data) noexcept {
    data.selection_requested=request.selection_requested;
    data.requested_country_tag[0]=0;
    data.requested_source_tag[0]=0;
    data.requested_country_is_payer=false;
    if (request.country[0]) memcpy(data.requested_country_tag,request.country,4);
    else if (request.kind==PeaceCountryKind::grant_independence)
        data.requested_country_is_payer=true;
    if (request.source[0]) memcpy(data.requested_source_tag,request.source,4);
    else if (request.kind==PeaceCountryKind::release_nation)
        memcpy(data.requested_source_tag,data.payer_tag,4);
}

static bool peace_country_prepare_with_beneficiary(void* offer,uint64_t actor,
    uint64_t recipient,bool demand,const PeaceCountryRequest& request,
    const char* expected_beneficiary,PeaceCountryQueryData& data) noexcept {
    if (!expected_beneficiary || !expected_beneficiary[0]
        || !strcmp(expected_beneficiary,"-"))
        return peace_country_query_prepare(offer,actor,recipient,demand,request,data);
    PeaceCountryRequest discovery{};
    peace_country_set_discovery_request(request,discovery);
    if (!peace_country_query_prepare(offer,actor,recipient,demand,discovery,data))
        return false;
    if (!peace_country_valid_tag(expected_beneficiary)) {
        data.selection_requested=true;
        peace_country_set_requested_tags(request,data);
        data.parameters_matched=false;
        data.selection_applied=false;
        data.reason_code="NATIVE_PEACE_COUNTRY_BENEFICIARY_INVALID";
        return true;
    }
    if (strcmp(data.claimant_tag,expected_beneficiary)) {
        data.selection_requested=true;
        peace_country_set_requested_tags(request,data);
        data.parameters_matched=false;
        data.selection_applied=false;
        data.reason_code="NATIVE_PEACE_COUNTRY_BENEFICIARY_MISMATCH";
        return true;
    }
    return peace_country_query_prepare(offer,actor,recipient,demand,request,data);
}

static bool peace_country_query_set_prepare(void* offer,uint64_t actor,
    uint64_t recipient,bool demand,const PeaceCountryRequestSet& requests,
    PeaceCountryQuerySet& data) noexcept {
    if (!data.valid()) return false;
    if (requests.release_nation
        && !peace_country_query_prepare(offer,actor,recipient,demand,
            *requests.release_nation,data.release_nation)) return false;
    if (requests.force_vassal
        && !peace_country_prepare_with_beneficiary(offer,actor,recipient,demand,
            *requests.force_vassal,requests.force_vassal_beneficiary,
            data.force_vassal)) return false;
    if (requests.pu
        && !peace_country_prepare_with_beneficiary(offer,actor,recipient,demand,
            *requests.pu,requests.pu_beneficiary,data.pu)) return false;
    if (requests.grant_independence
        && !peace_country_query_prepare(offer,actor,recipient,demand,
            *requests.grant_independence,data.grant_independence)) return false;
    return true;
}

static bool peace_country_query_set_verify_source_copy(void* action_copy_offer,
    PeaceCountryQuerySet& data) noexcept {
    if (!data.valid()) return false;
    return (!data.release_nation.enabled
        || peace_country_verify_source_copy(action_copy_offer,data.release_nation))
        && (!data.force_vassal.enabled
            || peace_country_verify_source_copy(action_copy_offer,data.force_vassal))
        && (!data.pu.enabled
            || peace_country_verify_source_copy(action_copy_offer,data.pu))
        && (!data.grant_independence.enabled
            || peace_country_verify_source_copy(action_copy_offer,data.grant_independence));
}

static bool peace_country_query_set_json(PeaceCountryQuerySet& data) noexcept {
    if (!data.any() || !data.valid() || !data.json) return false;
    data.json[0]=0; data.json_size=0; size_t used=0;
    if (!peace_country_json_append(data.json,data.json_capacity,used,
        "{\"release_nation\":")) return false;
    if (data.release_nation.enabled) {
        if (!peace_country_query_json(data.release_nation)) return false;
        if (!peace_country_json_append(data.json,data.json_capacity,used,
            data.release_nation.json)) return false;
    } else if (!peace_country_json_append(data.json,data.json_capacity,used,"null"))
        return false;
    if (!peace_country_json_append(data.json,data.json_capacity,used,
        ",\"force_vassalization\":")) return false;
    if (data.force_vassal.enabled) {
        if (!peace_country_query_json(data.force_vassal)) return false;
        if (!peace_country_json_append(data.json,data.json_capacity,used,
            data.force_vassal.json)) return false;
    } else if (!peace_country_json_append(data.json,data.json_capacity,used,"null"))
        return false;
    if (!peace_country_json_append(data.json,data.json_capacity,used,
        ",\"form_personal_union\":")) return false;
    if (data.pu.enabled) {
        if (!peace_country_query_json(data.pu)) return false;
        if (!peace_country_json_append(data.json,data.json_capacity,used,data.pu.json))
            return false;
    } else if (!peace_country_json_append(data.json,data.json_capacity,used,"null"))
        return false;
    if (!peace_country_json_append(data.json,data.json_capacity,used,
        ",\"grant_independence\":")) return false;
    if (data.grant_independence.enabled) {
        if (!peace_country_query_json(data.grant_independence)) return false;
        if (!peace_country_json_append(data.json,data.json_capacity,used,
            data.grant_independence.json)) return false;
    } else if (!peace_country_json_append(data.json,data.json_capacity,used,"null"))
        return false;
    if (!peace_country_json_append(data.json,data.json_capacity,used,"}")) return false;
    data.json_size=used; return true;
}

static const char* peace_country_query_set_json_text(const PeaceCountryQuerySet& data) noexcept {
    return data.json?data.json:"null";
}
