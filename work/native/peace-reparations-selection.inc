// Native-created base terms share 98bf50 selection while retaining exact type identities.
// Reuse 98bf50's persistent non-Gold selection branch.  All mutations stay
// inside a fresh temporary CPeaceOffer and its owned term containers.
#include <new>

struct PeaceBaseTermCaptureOwner {
    PeaceSerializedCapture* value=nullptr;
    PeaceBaseTermCaptureOwner() noexcept {
        void* memory=HeapAlloc(GetProcessHeap(),0,sizeof(PeaceSerializedCapture));
        if (memory) value=new(memory) PeaceSerializedCapture{};
    }
    ~PeaceBaseTermCaptureOwner() noexcept {
        if (value) { value->~PeaceSerializedCapture(); HeapFree(GetProcessHeap(),0,value); }
    }
    PeaceBaseTermCaptureOwner(const PeaceBaseTermCaptureOwner&)=delete;
    PeaceBaseTermCaptureOwner& operator=(const PeaceBaseTermCaptureOwner&)=delete;
};

enum class PeaceBaseTermKind {
    reparations,trade_power,concede_defeat,annul_treaties,
    humiliate_rival,show_strength,force_religion
};
static constexpr bool peace_base_term_is_special(PeaceBaseTermKind kind) noexcept {
    return kind==PeaceBaseTermKind::humiliate_rival
        || kind==PeaceBaseTermKind::show_strength || kind==PeaceBaseTermKind::force_religion;
}
struct PeaceBaseTermSpec {
    uint32_t type,bucket;
    uintptr_t vtable,descriptor,recalculate;
};
static constexpr PeaceBaseTermSpec peace_base_term_spec(PeaceBaseTermKind kind) noexcept {
    return kind==PeaceBaseTermKind::humiliate_rival
        ?PeaceBaseTermSpec{0x30a3u,9u,0x1cd34e0u,0x99af30u,0x9bbe00u}
        :kind==PeaceBaseTermKind::show_strength
        ?PeaceBaseTermSpec{0x2f20u,10u,0x1cd3398u,0x99af50u,0x9bc6b0u}
        :kind==PeaceBaseTermKind::force_religion
        ?PeaceBaseTermSpec{0x2d29u,21u,0x1cd45b0u,0x99b070u,0x9c3510u}
        :kind==PeaceBaseTermKind::annul_treaties
        ?PeaceBaseTermSpec{0x2d2eu,0x0eu,0x1cd2e68u,0x99afd0u,0x9beda0u}
        :kind==PeaceBaseTermKind::concede_defeat
        ?PeaceBaseTermSpec{0x2d2du,0x0bu,0x1cd2d20u,0x99af70u,0x9bcae0u}
        :kind==PeaceBaseTermKind::trade_power
        ?PeaceBaseTermSpec{0x2e07u,8u,0x1cd38c8u,0x99aed0u,0x9b6c90u}
        :PeaceBaseTermSpec{0x30a0u,7u,0x1cd3a10u,0x99aeb0u,0x9b63e0u};
}

struct PeaceBaseTermQueryData {
    PeaceBaseTermKind kind=PeaceBaseTermKind::reparations;
    uint64_t payer=0,claimant=0,source=0;
    char source_tag[4]{},beneficiary_tag[4]{};
    bool selection_requested=true;
    struct Candidate {
        char source[4]{},beneficiary[4]{};
        bool selected=false,complete=false;
    } candidates[32]{};
    unsigned exported_candidates=0;
    bool candidates_available=false,candidates_complete=false,candidates_truncated=false;
    unsigned candidate_count=0,matching_candidate_count=0,selected_term_count=0;
    bool candidate_found=false,selection_available=false,selected=false;
    bool selection_copy_verified=false,parameters_matched=false;
    bool rule_checked=false,rule_available=false;
    unsigned rule_term_count=0;
    bool rule_diagnostic_readable=false,rule_diagnostic_truncated=false;
    char rule_diagnostic_hex[1025]{};
    const char* reason_code=nullptr;
};

enum class PeaceBaseTermSelectionRole { source,action_copy };

// Native 99d220 tests a selection change inside this 40-byte transaction.
// Its 993520 cleanup restores the selection bit, pending a0/b8 vectors,
// Gold value and +118-derived offer state.  Reuse that transaction to call
// 97a030 before re-adding Reparations: its aggregate+delta cost then equals
// the complete requested offer instead of counting Reparations twice.
static bool peace_base_term_rule_with_current_term_removed(void* offer,uintptr_t candidate,
    NativeShortString& diagnostic,bool& available,PeaceBaseTermKind kind) noexcept {
    const auto spec=peace_base_term_spec(kind);
    struct Change { uintptr_t term; uint64_t was_added; };
    struct Transaction {
        uintptr_t offer,begin,end,capacity;
        int32_t saved_gold;
        uint32_t padding;
    } transaction{reinterpret_cast<uintptr_t>(offer),0,0,0,0,0};
    static_assert(sizeof(Change)==16 && sizeof(Transaction)==40);
    const uintptr_t address=reinterpret_cast<uintptr_t>(offer),vector=address+0xb8;
    uintptr_t begin=0,end=0,capacity=0,recalculate=0;
    unsigned char selected=0,direction=0;
    int32_t mode=0;
    if (!read(candidate+0x20,selected) || selected!=1
        || !read(address+0x20,direction) || direction>1
        || !read(address+0xf4,mode)
        || !read(base+spec.vtable+0x118,recalculate) || recalculate!=base+spec.recalculate
        || !read(vector,begin) || !read(vector+8,end) || !read(vector+16,capacity)
        || end<begin || capacity<end || (end-begin)%8 || (capacity-begin)%8
        || (end-begin)/8>=bridge::peace_payload::kMaxPeaceTerms) return false;
    using SaveGold=int32_t* (*)(void*,int32_t*);
    using AppendChange=void (*)(void*,uintptr_t,const Change*);
    using AppendTerm=void (*)(void*,uintptr_t,const uintptr_t*);
    using Recalculate=void (*)(void*,void*,unsigned char,unsigned char);
    using TermRule=bool (*)(void*,void*,const void*,unsigned char,void*);
    reinterpret_cast<SaveGold>(base+0x97b130)(offer,&transaction.saved_gold);
    const Change change{candidate,0};
    reinterpret_cast<AppendChange>(base+0x142310)(&transaction.begin,transaction.end,&change);
    selected=0;
    memcpy(reinterpret_cast<void*>(candidate+0x20),&selected,1);
    if (end==capacity)
        reinterpret_cast<AppendTerm>(base+0xcc220)(reinterpret_cast<void*>(vector),end,&candidate);
    else {
        memcpy(reinterpret_cast<void*>(end),&candidate,sizeof(candidate)); end+=8;
        memcpy(reinterpret_cast<void*>(vector+8),&end,sizeof(end));
    }
    const int32_t trial_mode=1;
    memcpy(reinterpret_cast<void*>(address+0xf4),&trial_mode,sizeof(trial_mode));
    reinterpret_cast<Recalculate>(recalculate)(reinterpret_cast<void*>(candidate),
        reinterpret_cast<void*>(address+0xe8),direction,1);
    memcpy(reinterpret_cast<void*>(address+0xf4),&mode,sizeof(mode));
    uintptr_t empty_descriptors[3]{};
    available=reinterpret_cast<TermRule>(base+0x97a030)(offer,
        reinterpret_cast<void*>(candidate),empty_descriptors,0,&diagnostic);
    reinterpret_cast<void (*)(Transaction*)>(base+0x993520)(&transaction);
    return true;
}

static bool peace_base_term_source_tag(uint64_t handle,char (&tag)[4]) noexcept {
    uintptr_t country=0;
    return peace_query_country_pointer(handle,country) && peace_province_tag_from_handle(handle,tag);
}

static bool peace_base_term_capture(const void* offer,uint64_t payer,uint64_t claimant,
    PeaceSerializedCapture& capture,unsigned& count,unsigned& matches,unsigned& selected,
    uintptr_t& candidate,PeaceBaseTermKind kind=PeaceBaseTermKind::reparations,
    const char* source_tag=nullptr) noexcept {
    const auto spec=peace_base_term_spec(kind);
    count=matches=selected=0; candidate=0;
    if (!peace_capture_serialized_offer(offer,capture) || !capture.payload.complete) return false;
    for (unsigned i=0;i<capture.payload.term_count;++i) {
        const auto& term=capture.payload.terms[i];
        if (term.type_id!=spec.type || term.bucket!=spec.bucket) continue;
        if (capture.term_vtables[i]!=base+spec.vtable || !term.complete) return false;
        ++count;
        if (term.field10!=payer || term.field18!=claimant) continue;
        if (kind==PeaceBaseTermKind::trade_power) {
            char actual_source[4]{};
            if (!source_tag || term.field22==claimant
                || !peace_base_term_source_tag(term.field22,actual_source)
                || strcmp(source_tag,actual_source)) continue;
        } else if (term.field22!=payer) continue;
        ++matches;
        candidate=capture.term_addresses[i];
        if (term.selected) ++selected;
    }
    return true;
}

static void peace_base_term_candidates(const PeaceSerializedCapture& capture,
    PeaceBaseTermQueryData& data) noexcept {
    if (data.kind!=PeaceBaseTermKind::trade_power) return;
    const auto spec=peace_base_term_spec(data.kind);
    data.exported_candidates=0;
    data.candidates_available=true; data.candidates_complete=true;
    data.candidates_truncated=false; data.source=0;
    for (unsigned i=0;i<capture.payload.term_count;++i) {
        const auto& term=capture.payload.terms[i];
        if (term.type_id!=spec.type || term.bucket!=spec.bucket) continue;
        char source[4]{},beneficiary[4]{};
        const bool complete=term.complete && term.field10==data.payer
            && term.field18==data.claimant && term.field22!=data.claimant
            && peace_base_term_source_tag(term.field22,source)
            && peace_base_term_source_tag(term.field18,beneficiary);
        if (!complete) { data.candidates_complete=false; continue; }
        if (!strcmp(source,data.source_tag)) data.source=term.field22;
        if (data.exported_candidates>=32) {
            data.candidates_truncated=true; data.candidates_complete=false; continue;
        }
        auto& item=data.candidates[data.exported_candidates++];
        memcpy(item.source,source,sizeof(item.source));
        memcpy(item.beneficiary,beneficiary,sizeof(item.beneficiary));
        item.selected=term.selected; item.complete=true;
    }
}

static bool peace_base_term_read_selection(const void* offer,PeaceBaseTermQueryData& data,
    PeaceBaseTermSelectionRole role) noexcept {
    PeaceBaseTermCaptureOwner owned;
    if (!owned.value) return false;
    auto& capture=*owned.value;
    unsigned count=0,matches=0,selected=0; uintptr_t candidate=0;
    if (!peace_base_term_capture(offer,data.payer,data.claimant,capture,
        count,matches,selected,candidate,data.kind,data.source_tag)) return false;
    if (role==PeaceBaseTermSelectionRole::action_copy) {
        data.selection_copy_verified=count==data.candidate_count
            && matches==data.matching_candidate_count && selected==data.selected_term_count;
        return data.selection_copy_verified;
    }
    data.candidate_count=count;
    data.matching_candidate_count=matches;
    data.candidate_found=matches==1;
    data.selected_term_count=selected;
    data.selected=selected==1;
    data.parameters_matched=data.candidate_found && data.selected;
    peace_base_term_candidates(capture,data);
    return true;
}

static bool peace_base_term_query_prepare(void* offer,uint64_t actor,uint64_t recipient,
    bool demand,PeaceBaseTermQueryData& data,
    PeaceBaseTermKind kind=PeaceBaseTermKind::reparations,bool check_rules=true,
    const char* trade_source_tag=nullptr,bool selection_requested=true) noexcept {
    const auto spec=peace_base_term_spec(kind);
    data=PeaceBaseTermQueryData{}; data.kind=kind;
    data.payer=peace_offer_payer(actor,recipient,demand);
    data.claimant=peace_offer_claimant(actor,recipient,demand);
    data.selection_requested=selection_requested;
    if (kind==PeaceBaseTermKind::trade_power) {
        if (!peace_province_tag_from_handle(data.claimant,data.beneficiary_tag)) return false;
        if (trade_source_tag) {
            if (strlen(trade_source_tag)!=3) return false;
            memcpy(data.source_tag,trade_source_tag,sizeof(data.source_tag));
        } else if (selection_requested
            && !peace_province_tag_from_handle(data.payer,data.source_tag)) return false;
    }
    PeaceBaseTermCaptureOwner owned;
    if (!owned.value) return false;
    auto& capture=*owned.value;
    unsigned count=0,matches=0,selected_count=0; uintptr_t candidate=0;
    if (!peace_base_term_capture(offer,data.payer,data.claimant,capture,
        count,matches,selected_count,candidate,kind,data.source_tag)) return false;
    data.candidate_count=count; data.matching_candidate_count=matches;
    data.candidate_found=matches==1;
    peace_base_term_candidates(capture,data);
    if (!selection_requested) return true;
    if (!data.candidate_found) {
        data.reason_code=peace_base_term_is_special(kind)
            ?(matches?"NATIVE_PEACE_SPECIAL_CANDIDATE_AMBIGUOUS":"NATIVE_PEACE_SPECIAL_CANDIDATE_NOT_FOUND")
            :kind==PeaceBaseTermKind::concede_defeat
            ?(matches?"NATIVE_PEACE_CONCEDE_DEFEAT_CANDIDATE_AMBIGUOUS":"NATIVE_PEACE_CONCEDE_DEFEAT_CANDIDATE_NOT_FOUND")
            :kind==PeaceBaseTermKind::trade_power
            ?(matches?"NATIVE_PEACE_TRADE_POWER_CANDIDATE_AMBIGUOUS":"NATIVE_PEACE_TRADE_POWER_CANDIDATE_NOT_FOUND")
            :(matches?"NATIVE_PEACE_REPARATIONS_CANDIDATE_AMBIGUOUS":"NATIVE_PEACE_REPARATIONS_CANDIDATE_NOT_FOUND");
        return true;
    }
    if (selected_count) {
        data.reason_code=peace_base_term_is_special(kind)?"NATIVE_PEACE_SPECIAL_UNEXPECTED_PRESELECTION":kind==PeaceBaseTermKind::concede_defeat?"NATIVE_PEACE_CONCEDE_DEFEAT_UNEXPECTED_PRESELECTION":kind==PeaceBaseTermKind::trade_power?"NATIVE_PEACE_TRADE_POWER_UNEXPECTED_PRESELECTION":"NATIVE_PEACE_REPARATIONS_UNEXPECTED_PRESELECTION";
        return true;
    }
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
    data.selection_available=true;
    if (!peace_base_term_read_selection(offer,data,PeaceBaseTermSelectionRole::source))
        return false;
    if (!data.parameters_matched) data.reason_code=peace_base_term_is_special(kind)?"NATIVE_PEACE_SPECIAL_SELECTION_MISMATCH":kind==PeaceBaseTermKind::concede_defeat?"NATIVE_PEACE_CONCEDE_DEFEAT_SELECTION_MISMATCH":kind==PeaceBaseTermKind::trade_power?"NATIVE_PEACE_TRADE_POWER_SELECTION_MISMATCH":"NATIVE_PEACE_REPARATIONS_SELECTION_MISMATCH";
    // Check native restrictions on every selected nonzero term.  Check the
    // complete offer's cost once through Reparations' removal/re-addition
    // transaction.  Other terms use native skip-cost=1, avoiding duplicate
    // contributions from a term that is already in the complete offer.
    if (data.parameters_matched && check_rules) {
        if (!peace_capture_serialized_offer(offer,capture) || !capture.payload.complete) return false;
        uintptr_t empty_descriptors[3]{};
        using TermRule=bool (*)(void*,void*,const void*,unsigned char,void*);
        bool all_available=true;
        data.rule_diagnostic_readable=true;
        for (unsigned i=0;i<capture.payload.term_count;++i) {
            const auto& selected_term=capture.payload.terms[i];
            if (!selected_term.selected
                || (selected_term.type_id==0x2d2bu && selected_term.gold_raw==0)) continue;
            NativeShortString diagnostic{}; diagnostic.capacity=15;
            bool available=false;
            if (selected_term.type_id==spec.type && selected_term.bucket==spec.bucket) {
                if (!peace_base_term_rule_with_current_term_removed(offer,
                    capture.term_addresses[i],diagnostic,available,kind)) {
                    reinterpret_cast<void (*)(void*)>(base+0x95660)(&diagnostic);
                    return false;
                }
            } else available=reinterpret_cast<TermRule>(base+0x97a030)(offer,
                reinterpret_cast<void*>(capture.term_addresses[i]),empty_descriptors,1,&diagnostic);
            ++data.rule_term_count;
            if (!available && all_available) declarewar_query_hex(diagnostic,data.rule_diagnostic_hex,
                data.rule_diagnostic_readable,data.rule_diagnostic_truncated);
            all_available=all_available && available;
            reinterpret_cast<void (*)(void*)>(base+0x95660)(&diagnostic);
        }
        data.rule_checked=data.rule_term_count!=0;
        data.rule_available=data.rule_checked && all_available;
        PeaceBaseTermCaptureOwner after;
        if (!after.value || !peace_capture_serialized_offer(offer,*after.value)
            || !(capture.payload==after.value->payload)) return false;
        if (!data.rule_available) data.reason_code="NATIVE_PEACE_SELECTED_TERM_RULE_UNAVAILABLE";
    }
    return true;
}

static void peace_base_term_copy_rules(const PeaceBaseTermQueryData& from,
    PeaceBaseTermQueryData& to) noexcept {
    to.rule_checked=from.rule_checked; to.rule_available=from.rule_available;
    to.rule_term_count=from.rule_term_count;
    to.rule_diagnostic_readable=from.rule_diagnostic_readable;
    to.rule_diagnostic_truncated=from.rule_diagnostic_truncated;
    memcpy(to.rule_diagnostic_hex,from.rule_diagnostic_hex,sizeof(to.rule_diagnostic_hex));
    if (!from.rule_available && !to.reason_code)
        to.reason_code="NATIVE_PEACE_SELECTED_TERM_RULE_UNAVAILABLE";
    else if (from.rule_available && to.reason_code
        && !strcmp(to.reason_code,"NATIVE_PEACE_SELECTED_TERM_RULE_UNAVAILABLE")) to.reason_code=nullptr;
}

template<size_t Capacity>
static void peace_base_term_query_json(const PeaceBaseTermQueryData& data,
    const char* actor,const char* recipient,bool demand,char (&output)[Capacity]) noexcept {
    static_assert(Capacity>=2600);
    char reason[130]="null";
    if (data.reason_code) snprintf(reason,sizeof(reason),"\"%.110s\"",data.reason_code);
    const bool trade=data.kind==PeaceBaseTermKind::trade_power;
    const bool concede=data.kind==PeaceBaseTermKind::concede_defeat;
    const bool special=peace_base_term_is_special(data.kind);
    char source[10]="null",beneficiary[10]="null";
    if (!trade || data.source_tag[0]) snprintf(source,sizeof(source),"\"%.3s\"",
        trade?data.source_tag:(demand?recipient:actor));
    snprintf(beneficiary,sizeof(beneficiary),"\"%.3s\"",
        trade?data.beneficiary_tag:(demand?actor:recipient));
    snprintf(output,sizeof(output),
        "{\"requested\":true,\"candidate_count\":%u,\"matching_candidate_count\":%u,"
        "\"candidate_found\":%s,\"selection_requested\":%s,\"selection_available\":%s,"
        "\"selected\":%s,\"selected_term_count\":%u,\"%s\":%s,\"%s\":%s,"
        "\"selection_copy_verified\":%s,\"parameters_matched\":%s,\"reason_code\":%s,"
        "\"rule_checked\":%s,\"rule_available\":%s,\"rule_term_count\":%u,"
        "\"rule_scope\":\"selected_nonzero_terms\",\"rule_diagnostic_hex\":\"%s\","
        "\"rule_diagnostic_readable\":%s,\"rule_diagnostic_truncated\":%s}",
        data.candidate_count,data.matching_candidate_count,data.candidate_found?"true":"false",
        data.selection_requested?"true":"false",data.selection_available?"true":"false",
        data.selected?"true":"false",data.selected_term_count,
        trade?"source":concede?"conceding_country":special?"country":"payer",source,
        trade || concede || special?"beneficiary":"claimant",beneficiary,
        data.selection_copy_verified?"true":"false",
        data.parameters_matched?"true":"false",reason,data.rule_checked?"true":"false",
        data.rule_available?"true":"false",data.rule_term_count,data.rule_diagnostic_hex,
        data.rule_diagnostic_readable?"true":"false",data.rule_diagnostic_truncated?"true":"false");
    if (trade) {
        char candidates[4200]{}; size_t used=0;
        for (unsigned i=0;i<data.exported_candidates;++i) {
            const auto& item=data.candidates[i];
            const int written=snprintf(candidates+used,sizeof(candidates)-used,
                "%s{\"source\":\"%.3s\",\"beneficiary\":\"%.3s\",\"selected\":%s,\"complete\":%s}",
                i?",":"",item.source,item.beneficiary,item.selected?"true":"false",
                item.complete?"true":"false");
            if (written<0 || static_cast<size_t>(written)>=sizeof(candidates)-used) return;
            used+=static_cast<size_t>(written);
        }
        const size_t end=strlen(output);
        if (!end || output[end-1]!='}') return;
        snprintf(output+end-1,sizeof(output)-end+1,
            ",\"candidates_available\":%s,\"candidates_complete\":%s,"
            "\"candidates_truncated\":%s,\"candidates\":[%s]}",
            data.candidates_available?"true":"false",data.candidates_complete?"true":"false",
            data.candidates_truncated?"true":"false",candidates);
    }
}
