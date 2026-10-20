// Native favors are stored by the country that owes them, indexed by the
// beneficiary's country slot. The Gold rule compares this value with
// DAT_233f3d0 * 1000; the native effect consumes the same relation entry.
struct FavorGoldState {
    bool complete=false;
    int32_t actor_treasury_raw=0,recipient_treasury_raw=0,favors_raw=0,cost_raw=0;
};

static bool favor_gold_capture(uint64_t actor,uint64_t recipient,FavorGoldState& state) noexcept {
    state=FavorGoldState{};
    uintptr_t source=0,target=0,rows=0;
    uint64_t other=0; int32_t cost=0;
    const unsigned slot=static_cast<unsigned>((actor>>32)&0xffffu);
    if (!insult_query_country(actor,source) || !insult_query_country(recipient,target)
        || !read(target+0x1510,rows) || !rows
        || !read(rows+static_cast<uintptr_t>(slot)*0x48+0x10,other) || other!=actor
        || !read(rows+static_cast<uintptr_t>(slot)*0x48+0x20,state.favors_raw)
        || !read(source+0xbb0,state.actor_treasury_raw)
        || !read(target+0xbb0,state.recipient_treasury_raw)
        || !read(base+0x233f3d0,cost) || cost<0 || cost>2147483) return false;
    state.cost_raw=cost*1000;
    state.complete=true;
    return true;
}

static bool favor_gold_amount(void* action,int32_t& amount) noexcept {
    amount=0;
    using Compute=uint32_t* (*)(void*,uint32_t*);
    uint32_t raw=0;
    const auto result=reinterpret_cast<Compute>(base+0x4f4010)(action,&raw);
    amount=static_cast<int32_t>(raw);
    return result==&raw && amount>=0;
}

static void favor_gold_query_json(const FavorGoldState& state,int32_t amount,bool amount_readable,
    char* output,size_t capacity) noexcept {
    snprintf(output,capacity,
        ",\"native_favor_trade\":{\"kind\":\"gold\",\"amount_raw\":%d,"
        "\"amount_readable\":%s,\"favor_cost_raw\":%d,\"favors_available_raw\":%d,"
        "\"actor_treasury_raw\":%d,\"recipient_treasury_raw\":%d,"
        "\"resource_scale\":1000,\"complete\":%s}",
        amount,amount_readable?"true":"false",state.cost_raw,state.favors_raw,
        state.actor_treasury_raw,state.recipient_treasury_raw,
        state.complete && amount_readable?"true":"false");
}

// Trust and manpower use the same recipient->actor relation row as the gold
// action, but their native unit is one integer point.  Keep this state
// separate from FavorGoldState so the gold public schema remains unchanged.
struct FavorTradeState {
    bool complete=false;
    int32_t recipient_trust_raw=0;
    int32_t actor_manpower_raw=0;
    int32_t recipient_manpower_raw=0;
    int32_t favors_raw=0;
    int32_t cost_raw=0;
};

static bool favor_trade_relation_row(uint64_t actor,uint64_t recipient,
    uintptr_t& source,uintptr_t& target,uintptr_t& row) noexcept {
    source=target=row=0;
    uint64_t other=0,rows=0;
    const unsigned slot=static_cast<unsigned>((actor>>32)&0xffffu);
    return insult_query_country(actor,source)
        && insult_query_country(recipient,target)
        && read(target+0x1510,rows) && rows
        && read(rows+static_cast<uintptr_t>(slot)*0x48+0x10,other)
        && other==actor
        && (row=rows+static_cast<uintptr_t>(slot)*0x48)!=0;
}

static bool favor_trade_capture(bool trust,uint64_t actor,uint64_t recipient,
    int32_t cost_raw,FavorTradeState& state) noexcept {
    state=FavorTradeState{};
    uintptr_t source=0,target=0,row=0;
    if (!favor_trade_relation_row(actor,recipient,source,target,row)
        || cost_raw<0) return false;
    if (!read(row+0x20,state.favors_raw)) return false;
    if (trust) {
        unsigned char value=0;
        if (!read(row+0x1e,value)) return false;
        state.recipient_trust_raw=static_cast<int32_t>(value);
        if (state.recipient_trust_raw<0 || state.recipient_trust_raw>100) return false;
    } else if (!read(source+0xdb8,state.actor_manpower_raw)
        || !read(target+0xdb8,state.recipient_manpower_raw)
        || state.actor_manpower_raw<0 || state.recipient_manpower_raw<0) return false;
    state.cost_raw=cost_raw;
    state.complete=true;
    return true;
}

static bool favor_trade_capture_action(bool trust,uint64_t actor,uint64_t recipient,
    void* action,FavorTradeState& state) noexcept {
    int32_t cost=0;
    if (trust) {
        if (!action || !read(reinterpret_cast<uintptr_t>(action)+0x40,cost)) return false;
    } else {
        if (!read(base+0x233f3c8,cost) || cost<0 || cost>2147483) return false;
        cost*=1000;
    }
    return favor_trade_capture(trust,actor,recipient,cost,state);
}

static bool favor_trade_amount(bool trust,void* action,int32_t& amount) noexcept {
    amount=0;
    if (trust) {
        int32_t raw=0;
        if (!action || !read(reinterpret_cast<uintptr_t>(action)+0x44,raw)
            || raw<0) return false;
        amount=raw;
        return true;
    }
    using Compute=uint32_t* (*)(void*,uint32_t*);
    uint32_t raw=0;
    const auto result=reinterpret_cast<Compute>(base+0x4f6690)(action,&raw);
    amount=static_cast<int32_t>(raw);
    return result==&raw && amount>=0;
}

static bool favor_trade_query_json(bool trust,const FavorTradeState& state,
    int32_t amount,bool amount_readable,char* output,size_t capacity) noexcept {
    if (trust) {
        const int written=snprintf(output,capacity,
            ",\"native_favor_trade\":{\"kind\":\"trust\",\"amount_raw\":%d,"
            "\"amount_readable\":%s,\"favor_cost_raw\":%d,\"favors_available_raw\":%d,"
            "\"recipient_trust_raw\":%d,\"resource_scale\":1,\"complete\":%s}",
            amount,amount_readable?"true":"false",state.cost_raw,state.favors_raw,
            state.recipient_trust_raw,state.complete && amount_readable?"true":"false");
        return written>=0 && static_cast<size_t>(written)<capacity;
    }
    const int written=snprintf(output,capacity,
        ",\"native_favor_trade\":{\"kind\":\"men\",\"amount_raw\":%d,"
        "\"amount_readable\":%s,\"favor_cost_raw\":%d,\"favors_available_raw\":%d,"
        "\"actor_manpower_raw\":%d,\"recipient_manpower_raw\":%d,\"resource_scale\":1,\"complete\":%s}",
        amount,amount_readable?"true":"false",state.cost_raw,state.favors_raw,
        state.actor_manpower_raw,state.recipient_manpower_raw,
        state.complete && amount_readable?"true":"false");
    return written>=0 && static_cast<size_t>(written)<capacity;
}
