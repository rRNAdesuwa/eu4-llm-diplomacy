// Native Annul Treaties candidates carry the constrained country at +22
// and its treaty partner at +30. 9becb0 copies that pair to the native
// relation; 98bf50's non-Gold selection branch remains the shared selector.
struct PeaceAnnulRequest {
    char country[4]{};
    char partners[16][4]{};
    unsigned count=0;
};
static bool peace_annul_parse_request(const char* country,const char* csv,
    PeaceAnnulRequest& out) noexcept {
    out=PeaceAnnulRequest{};
    if (!country || !csv) return false;
    if (!strcmp(country,"-") && !strcmp(csv,"-")) return true;
    using namespace bridge::peace_execution_wire::detail;
    if (!valid_canonical_tag(Field{country,strlen(country)})) return false;
    memcpy(out.country,country,4);
    const size_t length=strlen(csv);
    if (!length || length>63) return false;
    size_t at=0;
    while (at<length) {
        size_t end=at; while (end<length && csv[end]!=',') ++end;
        if (out.count>=16 || !valid_canonical_tag(Field{csv+at,end-at})) return false;
        memcpy(out.partners[out.count],csv+at,3);
        if (!strcmp(out.country,out.partners[out.count])
            || (out.count && strcmp(out.partners[out.count-1],out.partners[out.count])>=0)) return false;
        ++out.count;
        if (end==length) break;
        at=end+1; if (at==length) return false;
    }
    return out.count!=0;
}
struct PeaceAnnulQueryData {
    PeaceAnnulRequest request{};
    uint64_t payer=0,claimant=0;
    struct Candidate { char country[4]{},partner[4]{}; bool selected=false; } candidates[256]{};
    unsigned candidate_count=0,exported_candidates=0,matching_candidate_count=0,selected_term_count=0;
    unsigned matches[16]{}; uintptr_t addresses[16]{};
    bool candidates_available=false,candidates_complete=false,candidates_truncated=false;
    bool candidate_found=false,selection_requested=false,selection_available=false,selected=false;
    bool selection_copy_verified=false,parameters_matched=false;
    PeaceBaseTermQueryData rules{};
};
static bool peace_annul_read_selection(const void* offer,PeaceAnnulQueryData& data,
    bool action_copy=false) noexcept {
    PeaceBaseTermCaptureOwner owned; if (!owned.value) return false;
    auto& capture=*owned.value;
    if (!peace_capture_serialized_offer(offer,capture) || !capture.payload.complete) return false;
    unsigned count=0,selected=0,matches[16]{}; uintptr_t addresses[16]{};
    if (!action_copy) {
        data.exported_candidates=0; data.candidates_available=true;
        data.candidates_complete=true; data.candidates_truncated=false;
    }
    const auto spec=peace_base_term_spec(PeaceBaseTermKind::annul_treaties);
    for (unsigned i=0;i<capture.payload.term_count;++i) {
        const auto& term=capture.payload.terms[i];
        if (term.type_id!=spec.type || term.bucket!=spec.bucket) continue;
        char country[4]{},partner[4]{};
        if (!term.complete || capture.term_vtables[i]!=base+spec.vtable
            || term.field10!=data.payer || term.field18!=data.claimant
            || term.field22==term.extra30
            || !peace_base_term_source_tag(term.field22,country)
            || !peace_base_term_source_tag(term.extra30,partner)) return false;
        ++count; if (term.selected) ++selected;
        if (!action_copy) {
            if (data.exported_candidates<256) {
                auto& row=data.candidates[data.exported_candidates++];
                memcpy(row.country,country,4); memcpy(row.partner,partner,4);
                row.selected=term.selected!=0;
            } else { data.candidates_truncated=true; data.candidates_complete=false; }
        }
        if (data.selection_requested && !strcmp(country,data.request.country))
            for (unsigned j=0;j<data.request.count;++j)
                if (!strcmp(partner,data.request.partners[j])) {
                    ++matches[j]; addresses[j]=capture.term_addresses[i];
                }
    }
    bool found=data.selection_requested; unsigned total=0;
    for (unsigned j=0;j<data.request.count;++j) { total+=matches[j]; found=found && matches[j]==1; }
    if (action_copy) {
        data.selection_copy_verified=count==data.candidate_count
            && selected==data.selected_term_count && total==data.matching_candidate_count;
        for (unsigned j=0;j<data.request.count;++j)
            data.selection_copy_verified=data.selection_copy_verified && matches[j]==data.matches[j];
        return data.selection_copy_verified;
    }
    data.candidate_count=count; data.selected_term_count=selected;
    data.matching_candidate_count=total; data.candidate_found=found;
    data.selected=data.selection_requested && selected==data.request.count;
    data.parameters_matched=found && data.selected;
    for (unsigned j=0;j<data.request.count;++j) {data.matches[j]=matches[j];data.addresses[j]=addresses[j];}
    return true;
}
static bool peace_annul_select_candidate(void* offer,uintptr_t candidate,bool demand) noexcept {
    const auto spec=peace_base_term_spec(PeaceBaseTermKind::annul_treaties);
    uintptr_t descriptor_method=0,recalculate=0;
    if (!read(base+spec.vtable+0x78,descriptor_method) || descriptor_method!=base+spec.descriptor
        || !read(base+spec.vtable+0x118,recalculate) || recalculate!=base+spec.recalculate)
        return false;
    using Descriptor=void* (*)(void*,void*);
    using DependencyUpdate=void (*)(void*,void*,unsigned char);
    using Recalculate=void (*)(void*,void*,unsigned char,unsigned char);
    using Append=void (*)(void*,uintptr_t,const uintptr_t*);
    const uintptr_t address=reinterpret_cast<uintptr_t>(offer);
    void* term=reinterpret_cast<void*>(candidate);
    alignas(8) unsigned char descriptor[16]{};
    unsigned char direction=0,selected=0;
    if (!read(address+0x20,direction) || direction!=(demand?1u:0u)
        || !read(candidate+0x20,selected) || selected
        || reinterpret_cast<Descriptor>(descriptor_method)(term,descriptor)!=descriptor) return false;
    uint32_t bucket=0; memcpy(&bucket,descriptor,sizeof(bucket));
    uintptr_t buckets=0; unsigned bucket_count=0;
    if (bucket!=spec.bucket || !peace_payload_span(address,0xd0,24,
        bridge::peace_payload::kPeaceBucketCount,buckets,bucket_count) || bucket>=bucket_count)
        return false;
    selected=1;
    memcpy(reinterpret_cast<void*>(candidate+0x20),&selected,1);
    reinterpret_cast<DependencyUpdate>(base+0x97a4e0)(offer,term,1);
    // Resolve the typed vector after dependency notification, as in 98bf50.
    if (!peace_payload_span(address,0xd0,24,bridge::peace_payload::kPeaceBucketCount,
        buckets,bucket_count) || bucket>=bucket_count) return false;
    const uintptr_t vector=buckets+static_cast<uintptr_t>(bucket)*24;
    uintptr_t begin=0,end=0,capacity=0;
    if (!read(vector,begin) || !read(vector+8,end) || !read(vector+16,capacity)
        || end<begin || capacity<end || (end-begin)%8 || (capacity-begin)%8
        || (end-begin)/8>=bridge::peace_payload::kMaxPeaceTerms) return false;
    if (end==capacity)
        reinterpret_cast<Append>(base+0xcc220)(reinterpret_cast<void*>(vector),end,&candidate);
    else {
        memcpy(reinterpret_cast<void*>(end),&candidate,sizeof(candidate)); end+=8;
        memcpy(reinterpret_cast<void*>(vector+8),&end,sizeof(end));
    }
    reinterpret_cast<Recalculate>(recalculate)(term,reinterpret_cast<void*>(address+0xe8),direction,0);
    reinterpret_cast<DependencyUpdate>(base+0x97a4e0)(offer,term,0);

    return true;
}
static bool peace_annul_query_prepare(void* offer,uint64_t actor,uint64_t recipient,
    bool demand,const PeaceAnnulRequest& request,PeaceAnnulQueryData& data,
    bool check_rules=true) noexcept {
    data=PeaceAnnulQueryData{}; data.request=request;
    data.payer=peace_offer_payer(actor,recipient,demand);
    data.claimant=peace_offer_claimant(actor,recipient,demand);
    data.selection_requested=request.count!=0;
    data.rules.kind=PeaceBaseTermKind::annul_treaties;
    if (!peace_annul_read_selection(offer,data)) return false;
    if (!data.selection_requested) return true;
    if (!data.candidate_found) { data.rules.reason_code="NATIVE_PEACE_ANNUL_CANDIDATE_NOT_UNIQUE"; return true; }
    if (data.selected_term_count) { data.rules.reason_code="NATIVE_PEACE_ANNUL_UNEXPECTED_PRESELECTION"; return true; }
    for (unsigned j=0;j<request.count;++j)
        if (!peace_annul_select_candidate(offer,data.addresses[j],demand)) return false;
    data.selection_available=true;
    if (!peace_annul_read_selection(offer,data)) return false;
    if (!data.parameters_matched) {data.rules.reason_code="NATIVE_PEACE_ANNUL_SELECTION_MISMATCH";return true;}
    if (!check_rules) return true;
    PeaceBaseTermCaptureOwner owned,after;
    if (!owned.value || !after.value) return false;
    auto& capture=*owned.value;
    if (!peace_capture_serialized_offer(offer,capture) || !capture.payload.complete) return false;
    bool all=true; data.rules.rule_diagnostic_readable=true;
    uintptr_t empty_descriptors[3]{};
    using TermRule=bool (*)(void*,void*,const void*,unsigned char,void*);
    for (unsigned i=0;i<capture.payload.term_count;++i) {
        const auto& term=capture.payload.terms[i];
        if (!term.selected || (term.type_id==0x2d2bu && term.gold_raw==0)) continue;
        NativeShortString diagnostic{};diagnostic.capacity=15;bool available=false;
        if (term.type_id==0x2d2eu && term.bucket==0x0eu) {
            if (!peace_base_term_rule_with_current_term_removed(offer,capture.term_addresses[i],
                    diagnostic,available,PeaceBaseTermKind::annul_treaties)) {
                reinterpret_cast<void (*)(void*)>(base+0x95660)(&diagnostic);return false;
            }
        } else available=reinterpret_cast<TermRule>(base+0x97a030)(offer,
            reinterpret_cast<void*>(capture.term_addresses[i]),empty_descriptors,1,&diagnostic);
        ++data.rules.rule_term_count;
        if (!available && all) declarewar_query_hex(diagnostic,data.rules.rule_diagnostic_hex,
            data.rules.rule_diagnostic_readable,data.rules.rule_diagnostic_truncated);
        all=all && available;
        reinterpret_cast<void (*)(void*)>(base+0x95660)(&diagnostic);
    }
    data.rules.rule_checked=data.rules.rule_term_count!=0;
    data.rules.rule_available=data.rules.rule_checked && all;
    if (!data.rules.rule_available) data.rules.reason_code="NATIVE_PEACE_SELECTED_TERM_RULE_UNAVAILABLE";
    return peace_capture_serialized_offer(offer,*after.value) && capture.payload==after.value->payload;
}
static void peace_annul_query_json(const PeaceAnnulQueryData& data,char* out,size_t capacity) noexcept {
    char partners[128]{},candidates[23000]{},country[10]="null",reason[130]="null";
    size_t used=0;
    for (unsigned i=0;i<data.request.count;++i) {
        const int n=snprintf(partners+used,sizeof(partners)-used,"%s\"%.3s\"",i?",":"",data.request.partners[i]);
        if (n<0 || static_cast<size_t>(n)>=sizeof(partners)-used) return;
        used+=static_cast<size_t>(n);
    }
    used=0;
    for (unsigned i=0;i<data.exported_candidates;++i) {
        const auto& row=data.candidates[i];
        const int n=snprintf(candidates+used,sizeof(candidates)-used,
            "%s{\"country\":\"%.3s\",\"partner\":\"%.3s\",\"selected\":%s,\"complete\":true}",
            i?",":"",row.country,row.partner,row.selected?"true":"false");
        if (n<0 || static_cast<size_t>(n)>=sizeof(candidates)-used) return;
        used+=static_cast<size_t>(n);
    }
    if (data.request.country[0]) snprintf(country,sizeof(country),"\"%.3s\"",data.request.country);
    if (data.rules.reason_code) snprintf(reason,sizeof(reason),"\"%.110s\"",data.rules.reason_code);
    snprintf(out,capacity,
        "{\"requested\":true,\"candidate_count\":%u,\"matching_candidate_count\":%u,\"candidate_found\":%s,"
        "\"selection_requested\":%s,\"selection_available\":%s,\"selected\":%s,\"selected_term_count\":%u,"
        "\"country\":%s,\"treaty_partners\":[%s],\"selection_copy_verified\":%s,\"parameters_matched\":%s,"
        "\"candidates_available\":%s,\"candidates_complete\":%s,\"candidates_truncated\":%s,\"candidates\":[%s],"
        "\"reason_code\":%s,\"rule_checked\":%s,\"rule_available\":%s,\"rule_term_count\":%u,"
        "\"rule_scope\":\"selected_nonzero_terms\",\"rule_diagnostic_hex\":\"%s\","
        "\"rule_diagnostic_readable\":%s,\"rule_diagnostic_truncated\":%s}",
        data.candidate_count,data.matching_candidate_count,data.candidate_found?"true":"false",
        data.selection_requested?"true":"false",data.selection_available?"true":"false",data.selected?"true":"false",data.selected_term_count,
        country,partners,data.selection_copy_verified?"true":"false",data.parameters_matched?"true":"false",
        data.candidates_available?"true":"false",data.candidates_complete?"true":"false",data.candidates_truncated?"true":"false",candidates,
        reason,data.rules.rule_checked?"true":"false",data.rules.rule_available?"true":"false",data.rules.rule_term_count,
        data.rules.rule_diagnostic_hex,data.rules.rule_diagnostic_readable?"true":"false",data.rules.rule_diagnostic_truncated?"true":"false");
}
