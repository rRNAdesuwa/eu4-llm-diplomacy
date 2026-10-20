// Final, complete-offer checks for QUERY18/EXEC10.  Every selected nonzero
// term goes through 97a030. One known selected term is temporarily removed
// through the same transaction used by the existing R/T/C rule adapter so
// native cost checks evaluate the requested offer without double counting.

struct PeaceSelectedRuleCapture {
    bool checked=false,cost_checked=false,available=false;
    bool anchor_identity_verified=false,payload_unchanged=false;
    bool diagnostic_readable=true,diagnostic_truncated=false;
    unsigned selected_term_count=0,checked_term_count=0;
    char diagnostic_hex[1025]{};
    char json[3000]{};
    bool complete() const noexcept {
        return checked && cost_checked && anchor_identity_verified
            && payload_unchanged && checked_term_count>0;
    }
};

static uintptr_t peace_selected_rule_recalculate(uintptr_t vtable) noexcept {
    struct Entry { uintptr_t vtable,recalculate; };
    static constexpr Entry entries[]={
        {0x1cd4ad8u,0x9a8420u}, // Cede / full annexation
        {0x1cd4988u,0x9acb70u}, // Return Core
        {0x1cd3778u,0x9b4b60u}, // Revoke Core
        {0x1cd2940u,0x9c1bc0u}, // Release Subject
        {0x1cd3b58u,0x9ccb30u}, // Transfer Subject
        {0x1cd3100u,0x9b9660u}, // Release Nation
        {0x1cd4d78u,0x9af6b0u}, // Become Vassal
        {0x1cd1a90u,0x9af700u}, // Subjugate Vassal
        {0x1cd3f38u,0x9c67b0u}, // Personal Union
        {0x1cd2a90u,0x9c0440u}, // Grant Independence
    };
    for (const auto& entry:entries)
        if (vtable==base+entry.vtable) return base+entry.recalculate;
    return 0;
}

static bool peace_selected_rule_cost(void* offer,uintptr_t candidate,
    uintptr_t expected_vtable,uintptr_t expected_recalculate,
    NativeShortString& diagnostic,bool& available) noexcept {
    struct Change { uintptr_t term; uint64_t was_added; };
    struct Transaction {
        uintptr_t offer,begin,end,capacity;
        int32_t saved_gold;
        uint32_t padding;
    } transaction{reinterpret_cast<uintptr_t>(offer),0,0,0,0,0};
    static_assert(sizeof(Change)==16 && sizeof(Transaction)==40);
    const uintptr_t address=reinterpret_cast<uintptr_t>(offer),vector=address+0xb8u;
    uintptr_t vtable=0,begin=0,end=0,capacity=0,recalculate=0;
    unsigned char selected=0,direction=0;
    int32_t mode=0;
    if (!candidate || !expected_recalculate
        || !read(candidate,vtable) || vtable!=expected_vtable
        || !read(candidate+0x20u,selected) || selected!=1u
        || !read(address+0x20u,direction) || direction>1u
        || !read(address+0xf4u,mode)
        || !read(vtable+0x118u,recalculate) || recalculate!=expected_recalculate
        || !read(vector,begin) || !read(vector+8u,end) || !read(vector+16u,capacity)
        || end<begin || capacity<end || (end-begin)%8u || (capacity-begin)%8u
        || (end-begin)/8u>=bridge::peace_payload::kMaxPeaceTerms) return false;
    using SaveGold=int32_t* (*)(void*,int32_t*);
    using AppendChange=void (*)(void*,uintptr_t,const Change*);
    using AppendTerm=void (*)(void*,uintptr_t,const uintptr_t*);
    using Recalculate=void (*)(void*,void*,unsigned char,unsigned char);
    using TermRule=bool (*)(void*,void*,const void*,unsigned char,void*);
    reinterpret_cast<SaveGold>(base+0x97b130u)(offer,&transaction.saved_gold);
    const Change change{candidate,0};
    reinterpret_cast<AppendChange>(base+0x142310u)(&transaction.begin,transaction.end,&change);
    selected=0;
    memcpy(reinterpret_cast<void*>(candidate+0x20u),&selected,1);
    if (end==capacity)
        reinterpret_cast<AppendTerm>(base+0xcc220u)(reinterpret_cast<void*>(vector),end,&candidate);
    else {
        memcpy(reinterpret_cast<void*>(end),&candidate,sizeof(candidate)); end+=8u;
        memcpy(reinterpret_cast<void*>(vector+8u),&end,sizeof(end));
    }
    const int32_t trial_mode=1;
    memcpy(reinterpret_cast<void*>(address+0xf4u),&trial_mode,sizeof(trial_mode));
    reinterpret_cast<Recalculate>(recalculate)(reinterpret_cast<void*>(candidate),
        reinterpret_cast<void*>(address+0xe8u),direction,1);
    memcpy(reinterpret_cast<void*>(address+0xf4u),&mode,sizeof(mode));
    uintptr_t empty_descriptors[3]{};
    available=reinterpret_cast<TermRule>(base+0x97a030u)(offer,
        reinterpret_cast<void*>(candidate),empty_descriptors,0,&diagnostic);
    reinterpret_cast<void (*)(Transaction*)>(base+0x993520u)(&transaction);
    return true;
}

static bool peace_selected_rules_inspect(void* offer,
    PeaceSelectedRuleCapture& output) noexcept {
    output=PeaceSelectedRuleCapture{};
    if (!offer) return false;
    PeaceBaseTermCaptureOwner before,after;
    if (!before.value || !after.value
        || !peace_capture_serialized_offer(offer,*before.value)
        || !before.value->payload.complete) return false;
    const auto& capture=*before.value;
    uintptr_t anchor=0,anchor_vtable=0,anchor_recalculate=0;
    for (unsigned index=0;index<capture.payload.term_count;++index) {
        const auto& term=capture.payload.terms[index];
        if (!term.selected) continue;
        ++output.selected_term_count;
        if (term.type_id==0x2d2bu && term.gold_raw==0) continue;
        const uintptr_t recalculate=peace_selected_rule_recalculate(capture.term_vtables[index]);
        if (!anchor && recalculate) {
            anchor=capture.term_addresses[index];
            anchor_vtable=capture.term_vtables[index];
            anchor_recalculate=recalculate;
        }
    }
    if (!anchor) return false;
    output.anchor_identity_verified=true;
    bool all_available=true,first_failure=true;
    using TermRule=bool (*)(void*,void*,const void*,unsigned char,void*);
    uintptr_t empty_descriptors[3]{};
    for (unsigned index=0;index<capture.payload.term_count;++index) {
        const auto& term=capture.payload.terms[index];
        if (!term.selected || (term.type_id==0x2d2bu && term.gold_raw==0)) continue;
        NativeShortString diagnostic{}; diagnostic.capacity=15;
        bool available=false,observed=true;
        if (capture.term_addresses[index]==anchor) {
            observed=peace_selected_rule_cost(offer,anchor,anchor_vtable,
                anchor_recalculate,diagnostic,available);
            output.cost_checked=observed;
        } else available=reinterpret_cast<TermRule>(base+0x97a030u)(offer,
            reinterpret_cast<void*>(capture.term_addresses[index]),empty_descriptors,1,&diagnostic);
        if (observed) ++output.checked_term_count;
        if ((!observed || !available) && first_failure) {
            declarewar_query_hex(diagnostic,output.diagnostic_hex,
                output.diagnostic_readable,output.diagnostic_truncated);
            first_failure=false;
        }
        all_available=all_available && observed && available;
        reinterpret_cast<void (*)(void*)>(base+0x95660u)(&diagnostic);
        if (!observed) return false;
    }
    output.checked=output.checked_term_count>0;
    output.available=output.checked && all_available;
    output.payload_unchanged=peace_capture_serialized_offer(offer,*after.value)
        && after.value->payload.complete && capture.payload==after.value->payload;
    return output.complete();
}

static bool peace_selected_rules_json(PeaceSelectedRuleCapture& output) noexcept {
    const int written=snprintf(output.json,sizeof(output.json),
        "{\"checked\":%s,\"available\":%s,\"cost_checked\":%s,"
        "\"anchor_identity_verified\":%s,\"payload_unchanged\":%s,"
        "\"selected_term_count\":%u,\"checked_term_count\":%u,"
        "\"diagnostic_hex\":\"%s\",\"diagnostic_readable\":%s,"
        "\"diagnostic_truncated\":%s,\"complete\":%s}",
        output.checked?"true":"false",output.available?"true":"false",
        output.cost_checked?"true":"false",output.anchor_identity_verified?"true":"false",
        output.payload_unchanged?"true":"false",output.selected_term_count,
        output.checked_term_count,output.diagnostic_hex,
        output.diagnostic_readable?"true":"false",output.diagnostic_truncated?"true":"false",
        output.complete()?"true":"false");
    return written>0 && static_cast<size_t>(written)<sizeof(output.json);
}
