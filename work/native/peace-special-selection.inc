// Three native-created base terms. Each identity was read from its own
// +100 name method; H/S/F share the verified selection/rule transaction.
//
// 97a030 does not expose its numeric war-score comparison when the rule is
// rejected.  Keep this observation separate from AI acceptance/evaluation:
// it records the same aggregate + candidate-delta + limit values that the
// native rule compares, using the already verified 99d220/993520 transaction
// to remove and restore a currently selected special term.
struct PeaceSpecialCostObservation {
    bool attempted=false;
    bool cost_readable=false;
    bool base_readable=false;
    bool selected_delta_readable=false;
    bool total_readable=false;
    bool limit_readable=false;
    bool transaction_restored=false;
    bool payload_unchanged=false;
    bool unit_scale_verified=false;
    int32_t base_or_existing_raw=0;
    int32_t selected_delta_raw=0;
    int32_t total_raw=0;
    int32_t limit_raw=0;
};

static bool peace_special_cost_observe_one(void* offer,
    const PeaceBaseTermQueryData& data,PeaceBaseTermKind kind,
    PeaceSpecialCostObservation& output) noexcept {
    output=PeaceSpecialCostObservation{};
    output.attempted=true;
    if (!offer || !data.parameters_matched || !data.selected) return false;

    PeaceBaseTermCaptureOwner before_owned;
    if (!before_owned.value) return false;
    auto& before=*before_owned.value;
    unsigned count=0,matches=0,selected_count=0;
    uintptr_t candidate=0;
    if (!peace_base_term_capture(offer,data.payer,data.claimant,before,
            count,matches,selected_count,candidate,kind)
        || !before.payload.complete || !candidate
        || count!=data.candidate_count
        || matches!=data.matching_candidate_count || matches!=1
        || selected_count!=1 || data.selected_term_count!=1) return false;

    const auto spec=peace_base_term_spec(kind);
    const uintptr_t address=reinterpret_cast<uintptr_t>(offer);
    uintptr_t recalculate=0,preview=0,vector=address+0xb8;
    uintptr_t begin=0,end=0,capacity=0;
    unsigned char selected=0,direction=0;
    int32_t mode=0,limit=0;
    if (!read(candidate+0x20,selected) || selected!=1
        || !read(address+0x20,direction) || direction>1
        || !read(address+0xf4,mode)
        || !read(base+spec.vtable+0x118,recalculate)
        || recalculate!=base+spec.recalculate
        || !read(base+spec.vtable+0x120,preview)
        || preview!=base+0x99d220
        || !read(vector,begin) || !read(vector+8,end)
        || !read(vector+16,capacity) || end<begin || capacity<end
        || (end-begin)%8 || (capacity-begin)%8
        || (end-begin)/8>=bridge::peace_payload::kMaxPeaceTerms
        || !read(base+0x233dba0,limit)) return false;

    struct Change { uintptr_t term; uint64_t was_added; };
    struct Transaction {
        uintptr_t offer,begin,end,capacity;
        int32_t saved_gold;
        uint32_t padding;
    } transaction{address,0,0,0,0,0};
    static_assert(sizeof(Change)==16 && sizeof(Transaction)==40);
    struct Cleanup {
        Transaction* transaction=nullptr;
        ~Cleanup() noexcept { restore(); }
        void restore() noexcept {
            if (transaction) {
                reinterpret_cast<void (*)(Transaction*)>(base+0x993520)(transaction);
                transaction=nullptr;
            }
        }
    } cleanup;
    using SaveGold=int32_t* (*)(void*,int32_t*);
    using AppendChange=void (*)(void*,uintptr_t,const Change*);
    using AppendTerm=void (*)(void*,uintptr_t,const uintptr_t*);
    using Recalculate=void (*)(void*,void*,unsigned char,unsigned char);
    using Aggregate=int32_t (*)(void*,unsigned char);
    using CandidateDelta=int32_t (*)(void*,void*,unsigned char);

    reinterpret_cast<SaveGold>(base+0x97b130)(offer,&transaction.saved_gold);
    const Change change{candidate,0};
    reinterpret_cast<AppendChange>(base+0x142310)(&transaction.begin,
        transaction.end,&change);
    cleanup.transaction=&transaction;
    selected=0;
    memcpy(reinterpret_cast<void*>(candidate+0x20),&selected,1);
    if (end==capacity)
        reinterpret_cast<AppendTerm>(base+0xcc220)(reinterpret_cast<void*>(vector),
            end,&candidate);
    else {
        memcpy(reinterpret_cast<void*>(end),&candidate,sizeof(candidate));
        end+=8;
        memcpy(reinterpret_cast<void*>(vector+8),&end,sizeof(end));
    }
    const int32_t trial_mode=1;
    memcpy(reinterpret_cast<void*>(address+0xf4),&trial_mode,sizeof(trial_mode));
    reinterpret_cast<Recalculate>(recalculate)(reinterpret_cast<void*>(candidate),
        reinterpret_cast<void*>(address+0xe8),direction,1);
    memcpy(reinterpret_cast<void*>(address+0xf4),&mode,sizeof(mode));

    const int32_t existing=reinterpret_cast<Aggregate>(base+0x978ed0)(offer,1);
    // preview was read and verified above; call the function address stored in
    // the slot, never the vtable-slot address itself.
    const int32_t selected_delta=reinterpret_cast<CandidateDelta>(preview)(
        reinterpret_cast<void*>(candidate),offer,1);
    output.base_or_existing_raw=existing;
    output.selected_delta_raw=selected_delta;
    output.base_readable=true;
    output.selected_delta_readable=true;
    const int64_t total=static_cast<int64_t>(existing)+selected_delta;
    output.total_readable=total>=(-2147483647ll-1) && total<=2147483647ll;
    if (output.total_readable) output.total_raw=static_cast<int32_t>(total);
    output.limit_raw=limit;
    output.limit_readable=true;
    // The values are in the same native comparison domain, but no external
    // numeric scale has been independently measured yet.
    output.unit_scale_verified=false;

    cleanup.restore();
    output.transaction_restored=true;
    PeaceBaseTermCaptureOwner after_owned;
    if (!after_owned.value || !peace_capture_serialized_offer(offer,*after_owned.value))
        return false;
    output.payload_unchanged=after_owned.value->payload.complete
        && before.payload==after_owned.value->payload;
    output.cost_readable=output.base_readable && output.selected_delta_readable
        && output.total_readable && output.limit_readable
        && output.transaction_restored && output.payload_unchanged;
    return output.cost_readable;
}

template<size_t Capacity>
static bool peace_special_cost_json_append(const PeaceSpecialCostObservation& data,
    char (&output)[Capacity]) noexcept {
    const size_t end=strlen(output);
    if (end<2 || output[end-1]!='}') return false;
    char base[32]="null",delta[32]="null",total[32]="null",limit[32]="null";
    if (data.base_readable) snprintf(base,sizeof(base),"%d",data.base_or_existing_raw);
    if (data.selected_delta_readable)
        snprintf(delta,sizeof(delta),"%d",data.selected_delta_raw);
    if (data.total_readable) snprintf(total,sizeof(total),"%d",data.total_raw);
    if (data.limit_readable) snprintf(limit,sizeof(limit),"%d",data.limit_raw);
    const int written=snprintf(output+end-1,Capacity-end+1,
        ",\"cost_observation_attempted\":%s,\"cost_readable\":%s,"
        "\"base_or_existing_raw\":%s,\"selected_delta_raw\":%s,"
        "\"total_raw\":%s,\"limit_raw\":%s,"
        "\"unit_scale\":\"native_war_score_raw\",\"unit_scale_verified\":%s,"
        "\"cost_transaction_restored\":%s,\"cost_payload_unchanged\":%s}",
        data.attempted?"true":"false",data.cost_readable?"true":"false",
        base,delta,total,limit,data.unit_scale_verified?"true":"false",
        data.transaction_restored?"true":"false",data.payload_unchanged?"true":"false");
    return written>=0 && static_cast<size_t>(written)<Capacity-end+1;
}

struct PeaceSpecialQueryData {
    bool requested[3]{};
    PeaceBaseTermQueryData terms[3]{};
    PeaceSpecialCostObservation costs[3]{};
    unsigned last=3;

    PeaceSpecialQueryData(bool humiliate,bool strength,bool religion) noexcept
        : requested{humiliate,strength,religion} {
        for (unsigned i=0;i<3;++i) if (requested[i]) last=i;
    }
    bool any() const noexcept { return last<3; }
    bool prepare(void* offer,uint64_t actor,uint64_t recipient,bool demand) noexcept {
        static constexpr PeaceBaseTermKind kinds[]={PeaceBaseTermKind::humiliate_rival,
            PeaceBaseTermKind::show_strength,PeaceBaseTermKind::force_religion};
        for (unsigned i=0;i<3;++i) if (requested[i]) {
            if (!peace_base_term_query_prepare(offer,actor,recipient,demand,terms[i],
                    kinds[i],i==last)) return false;
        }
        if (any()) for (unsigned i=0;i<3;++i)
            if (requested[i] && i!=last) peace_base_term_copy_rules(terms[last],terms[i]);
        for (unsigned i=0;i<3;++i) if (requested[i])
            peace_special_cost_observe_one(offer,terms[i],kinds[i],costs[i]);
        return true;
    }
    void copy_rules(PeaceBaseTermQueryData& output) const noexcept {
        if (any()) peace_base_term_copy_rules(terms[last],output);
    }
    bool copy(const void* offer) noexcept {
        for (unsigned i=0;i<3;++i) if (requested[i]
            && !peace_base_term_read_selection(offer,terms[i],PeaceBaseTermSelectionRole::action_copy))
            return false;
        return true;
    }
    bool parameters_matched() const noexcept {
        for (unsigned i=0;i<3;++i) if (requested[i] && !terms[i].parameters_matched) return false;
        return true;
    }
    bool rules_complete() const noexcept {
        for (unsigned i=0;i<3;++i) if (requested[i] && !terms[i].rule_checked) return false;
        return true;
    }
    bool available() const noexcept {
        if (!parameters_matched() || !rules_complete()) return false;
        for (unsigned i=0;i<3;++i) if (requested[i] && !terms[i].rule_available) return false;
        return true;
    }
    template<size_t Capacity>
    bool json(const char* actor,const char* recipient,bool demand,char (&out)[Capacity]) const noexcept {
        static constexpr const char* names[]={"native_humiliate_rival",
            "native_show_strength","native_force_religion"};
        size_t used=0;
        for (unsigned i=0;i<3;++i) if (requested[i]) {
            char value[2600]{};
            peace_base_term_query_json(terms[i],actor,recipient,demand,value);
            if (!peace_special_cost_json_append(costs[i],value)) return false;
            const int written=snprintf(out+used,sizeof(out)-used,",\"%s\":%s",names[i],value);
            if (written<0 || static_cast<size_t>(written)>=sizeof(out)-used) return false;
            used+=static_cast<size_t>(written);
        }
        return true;
    }
};
