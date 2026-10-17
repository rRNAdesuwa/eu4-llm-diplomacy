// Public meaning of a retained native offer. Authorization still compares the
// entire sealed payload; this view exports identified selected terms only.
struct InboundPeaceContext {
    char json[6000]{};
    char war_id[30]{};
    unsigned term_count=0,selected_count=0;
    bool payload_complete=false,selected_complete=false,complete=false,white=false;
};

static bool execution_peace_pending_war_id(const AlliancePayload& payload,
    char (&war_id)[30]) noexcept {
    uintptr_t actor=0,recipient=0;
    PeaceWarReferenceList left{},right{};
    if (!peace_query_country_pointer(payload.actor10,actor)
        || !peace_query_country_pointer(payload.recipient20,recipient)
        || !peace_query_pair_references(actor,static_cast<unsigned>((payload.recipient20>>32)&0xffffu),left)
        || !peace_query_pair_references(recipient,static_cast<unsigned>((payload.actor10>>32)&0xffffu),right)
        || !peace_query_reference_sets_equal(left,right) || left.count!=1) return false;
    const auto* entry=peace_query_register_war(left.references[0]);
    if (!entry) return false;
    std::memcpy(war_id,entry->public_id,sizeof(war_id));
    return true;
}

static InboundPeaceContext execution_peace_inbound_context(const AlliancePayload& payload,
    const char* known_war_id=nullptr) noexcept {
    InboundPeaceContext result{};
    const auto* offer=payload.peace.offer.get();
    result.payload_complete=payload.family==ActionFamily::peace && payload.peace.valid();
    if (!result.payload_complete || !offer) { strcpy(result.json,"null"); return result; }
    result.term_count=offer->term_count;
    if (known_war_id && known_war_id[0])
        snprintf(result.war_id,sizeof(result.war_id),"%.29s",known_war_id);
    else execution_peace_pending_war_id(payload,result.war_id);
    char terms[4800]{}; size_t used=0; unsigned exported=0;
    bool understood=true;
    for (unsigned i=0;i<offer->term_count;++i) {
        const auto& term=offer->terms[i];
        if (!term.selected) continue;
        ++result.selected_count;
        char item[256]{};
        if (term.type_id==0x2d2b && term.bucket==0 && term.gold_raw>=0) {
            // A selected zero-gold term is the native empty/white offer.
            if (!term.gold_raw) continue;
            snprintf(item,sizeof(item),"{\"action_id\":\"demand_ducats\",\"amount_raw\":%d,\"scale\":1000}",term.gold_raw);
        } else if (term.type_id==0x2d25 && term.bucket==3 && term.nested_present) {
            char beneficiary[4]{};
            if (!peace_province_tag_from_handle(term.extra30,beneficiary)) { understood=false; continue; }
            snprintf(item,sizeof(item),"{\"action_id\":\"cede_province\",\"province_id\":%u,\"beneficiary\":\"%.3s\"}",term.nested_id,beneficiary);
        } else { understood=false; continue; }
        const int written=snprintf(terms+used,sizeof(terms)-used,"%s%s",exported?",":"",item);
        if (written<0 || static_cast<size_t>(written)>=sizeof(terms)-used) { understood=false; break; }
        used+=static_cast<size_t>(written); ++exported;
    }
    result.selected_complete=understood;
    result.white=understood && exported==0;
    result.complete=understood && result.war_id[0] && offer->direction<=1
        && payload.peace.direction41==offer->direction;
    char proposer[4]{},recipient[4]{};
    const bool endpoints=peace_province_tag_from_handle(payload.actor10,proposer)
        && peace_province_tag_from_handle(payload.recipient20,recipient);
    result.complete=result.complete && endpoints;
    snprintf(result.json,sizeof(result.json),
        "{\"war_id\":\"%.29s\",\"direction\":\"%s\",\"original_actor\":\"%.3s\",\"original_recipient\":\"%.3s\",\"terms\":[%s],\"white_peace\":%s,\"complete\":%s,\"selected_terms_complete\":%s,\"reason\":\"%s\"}",
        result.war_id,offer->direction==1?"demand":"offer",proposer,recipient,terms,
        result.white?"true":"false",result.complete?"true":"false",understood?"true":"false",
        result.complete?"none":!understood?"PEACE_SELECTED_TERM_SEMANTICS_UNAVAILABLE":"PEACE_WAR_CONTEXT_UNAVAILABLE");
    return result;
}
