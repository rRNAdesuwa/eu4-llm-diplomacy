// Native UI money methods on a fully constructed CPeaceOffer. Quantities are
// currency integers (1000 per ducat), not the offer's aggregate score +0xf0.
struct PeaceMoneyQuery {
    int32_t requested=0,ceiling=0,source=0,copied=0;
    bool within=false,setter_called=false,source_matches=false,copy_verified=false;
};

static bool peace_money_query_prepare(void* offer,int32_t requested,
    PeaceMoneyQuery& result) noexcept {
    result=PeaceMoneyQuery{};
    result.requested=requested;
    if (requested<=0 || requested%100) return false;
    using Get=int32_t* (*)(void*,int32_t*);
    using Limit=int32_t* (*)(void*,int32_t*,const int32_t*);
    using Set=void (*)(void*,const int32_t*);
    const auto get=reinterpret_cast<Get>(base+0x97b130);
    const auto limit=reinterpret_cast<Limit>(base+0x97b3a0);
    int32_t initial=-1,score_ceiling=100000;
    if (get(offer,&initial)!=&initial || initial!=0
        || limit(offer,&result.ceiling,&score_ceiling)!=&result.ceiling
        || result.ceiling<0) return false;
    result.within=requested<=result.ceiling;
    if (result.within) {
        reinterpret_cast<Set>(base+0x97b200)(offer,&requested);
        result.setter_called=true;
    }
    result.source=-1;
    if (get(offer,&result.source)!=&result.source || result.source<0) return false;
    result.source_matches=result.within && result.source==requested;
    return result.within?result.source_matches:result.source==0;
}

static bool peace_money_query_copy(void* copied_offer,PeaceMoneyQuery& result) noexcept {
    using Get=int32_t* (*)(void*,int32_t*);
    result.copied=-1;
    result.copy_verified=reinterpret_cast<Get>(base+0x97b130)(copied_offer,&result.copied)
        ==&result.copied && result.copied==result.source;
    return result.copy_verified;
}

static void peace_money_query_json(const PeaceMoneyQuery& money,
    const char* actor,const char* recipient,bool demand,
    char (&json)[1500]) noexcept {
    snprintf(json,sizeof(json),
        "{\"query_complete\":true,\"requested_amount_raw\":%d,\"currency_scale\":1000,\"currency_precision_raw\":100,\"currency_scale_verified\":true,\"ceiling_input_raw\":100000,\"currency_ceiling_raw\":%d,\"amount_within_limit\":%s,\"setter_called\":%s,\"source_amount_raw\":%d,\"action_amount_raw\":%d,\"source_readback_matches\":%s,\"action_copy_verified\":%s,\"parameters_matched\":%s,\"direction\":\"%s\",\"direction_raw\":%u,\"direction_verified\":true,\"direction_semantics_verified\":%s,\"payer\":\"%.3s\",\"claimant\":\"%.3s\",\"native_payer_field\":\"offer+0x10\",\"native_claimant_field\":\"offer+0x18\",\"payer_claimant_binding_verified\":true}",
        money.requested,money.ceiling,money.within?"true":"false",money.setter_called?"true":"false",
        money.source,money.copied,money.source_matches?"true":"false",money.copy_verified?"true":"false",
        (money.source_matches && money.copy_verified)?"true":"false",
        demand?"demand":"offer",static_cast<unsigned>(demand?1u:0u),
        demand?"true":"false",
        demand?recipient:actor,demand?actor:recipient);
}
