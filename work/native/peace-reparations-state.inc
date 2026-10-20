// 9b6270 creates treaty 1cddee0 and inserts it in both country relations.
// a68c40 -> 28d840 stores {other slot, treaty pointer} at owner+90:
// vector data +8, capacity +10, count +14, item stride 10 (all hexadecimal).
// These helpers only read that native state; they never create a treaty.
static bool peace_reparations_relation_entry(uint64_t self,uint64_t other,
    uintptr_t& entry,uintptr_t vector_offset=0x90) noexcept {
    entry=0;
    uintptr_t country=0,rows=0,owner=0,begin=0;
    uint64_t row_self=0,row_other=0;
    int32_t count=0,capacity=0;
    const unsigned slot=static_cast<unsigned>((other>>32)&0xffffu);
    if (slot>=256 || !peace_query_country_pointer(self,country)
        || !read(country+0x1510,rows) || !rows) return false;
    const uintptr_t row=rows+static_cast<uintptr_t>(slot)*0x48;
    if (!read(row,owner) || !owner || !read(row+8,row_self) || row_self!=self
        || !read(row+0x10,row_other) || row_other!=other
        || !read(owner+vector_offset+8,begin) || !read(owner+vector_offset+0x10,capacity)
        || !read(owner+vector_offset+0x14,count) || count<0 || count>4096
        || capacity<count || (count && !begin)) return false;
    for (int32_t i=0;i<count;++i) {
        int32_t other_slot=0; uintptr_t candidate=0;
        const uintptr_t item=begin+static_cast<uintptr_t>(i)*16;
        if (!read(item,other_slot) || !read(item+8,candidate)) return false;
        if (other_slot!=static_cast<int32_t>(slot)) continue;
        if (entry || !candidate) return false;
        entry=candidate;
    }
    return true;
}

static bool peace_reparations_state_read(uint64_t payer,uint64_t claimant,int32_t date,
    bridge::peace_effects::ReparationsState& state) noexcept {
    state=bridge::peace_effects::ReparationsState{};
    state.payer=payer; state.claimant=claimant;
    uintptr_t forward=0,reverse=0;
    if (!payer || !claimant || payer==claimant
        || !peace_reparations_relation_entry(payer,claimant,forward)
        || !peace_reparations_relation_entry(claimant,payer,reverse)
        || forward!=reverse) return false;
    if (!forward) { state.complete=true; return true; }
    uintptr_t table=0; uint32_t discriminator=0;
    uint64_t first=0,second=0;
    if (!read(forward,table) || table!=base+0x1cddee0u
        || !read(forward+8,discriminator) || discriminator!=0x165u
        || !read(forward+0x10,first) || !read(forward+0x18,second)
        || !read(forward+0x20,state.start_date_raw)
        || !read(forward+0x24,state.end_date_raw)
        || state.end_date_raw<=state.start_date_raw) return false;
    if (first==claimant && second==payer) {
        state.start_date_raw=state.end_date_raw=0;
        state.complete=true; return true;
    }
    if (first!=payer || second!=claimant) return false;
    state.present=true;
    state.active=state.start_date_raw<=date && date<state.end_date_raw;
    state.complete=true;
    return true;
}

// 9b6ae0 creates treaty 1c571f0. a74860/a6a660 register its source
// relation in owner+228. This is the current relation, with an explicit
// peace_treaty flag; its end date is not assumed to be a fixed duration.
static bool peace_trade_power_state_read(uint64_t source,uint64_t beneficiary,int32_t date,
    bridge::peace_effects::TradePowerState& state) noexcept {
    state=bridge::peace_effects::TradePowerState{};
    state.source=source; state.beneficiary=beneficiary;
    uintptr_t entry=0;
    if (!source || !beneficiary || source==beneficiary
        || !peace_reparations_relation_entry(source,beneficiary,entry,0x228)) return false;
    if (!entry) { state.complete=true; return true; }
    uintptr_t table=0; uint32_t discriminator=0;
    uint64_t actual_source=0,actual_beneficiary=0;
    unsigned char peace_treaty=0;
    if (!read(entry,table) || table!=base+0x1c571f0u
        || !read(entry+8,discriminator) || discriminator!=0x165u
        || !read(entry+0x10,actual_source) || actual_source!=source
        || !read(entry+0x18,actual_beneficiary) || actual_beneficiary!=beneficiary
        || !read(entry+0x20,state.start_date_raw)
        || !read(entry+0x24,state.end_date_raw)
        || !read(entry+0x40,state.amount_raw)
        || !read(entry+0x44,peace_treaty) || peace_treaty>1) return false;
    state.present=true;
    state.peace_treaty=peace_treaty!=0;
    state.complete=state.start_date_raw<=date;
    return state.complete;
}

// 9becb0 creates treaty 1cb3b48.  Annul rows are registered in the
// owner+180 pair vector in both directions.  The saved row keeps the
// requested country at +10 and its partner at +18; a reverse row is
// readable but is deliberately not reported as the requested orientation.
static bool peace_annul_treaty_state_read(uint64_t country,uint64_t partner,int32_t date,
    bridge::peace_effects::AnnulState& state) noexcept {
    (void)date;
    state=bridge::peace_effects::AnnulState{};
    state.country=country; state.partner=partner;
    uintptr_t forward=0,reverse=0;
    if (!country || !partner || country==partner
        || !peace_reparations_relation_entry(country,partner,forward,0x180)
        || !peace_reparations_relation_entry(partner,country,reverse,0x180)
        || forward!=reverse) return false;

    uintptr_t alliance_forward=0,alliance_reverse=0;
    if (!peace_reparations_relation_entry(country,partner,alliance_forward,0x78)
        || !peace_reparations_relation_entry(partner,country,alliance_reverse,0x78))
        return false;
    state.alliance_present=alliance_forward!=0
        && alliance_forward==alliance_reverse;
    if (!forward) { state.complete=true; return true; }

    uintptr_t table=0; uint32_t discriminator=0;
    uint64_t actual_country=0,actual_partner=0;
    if (!read(forward,table) || table!=base+0x1cb3b48u
        || !read(forward+8,discriminator) || discriminator!=0x165u
        || !read(forward+0x10,actual_country)
        || !read(forward+0x18,actual_partner)
        || !read(forward+0x20,state.start_date_raw)
        || !read(forward+0x24,state.end_date_raw)) return false;
    if (actual_country==country && actual_partner==partner) {
        state.present=true;
    } else if (actual_country==partner && actual_partner==country) {
        // Preserve the same observable shape as the older relation readers:
        // a reverse object is a complete read, but not an exact-direction
        // presence proof for this request.
        state.start_date_raw=state.end_date_raw=0;
    } else return false;
    state.complete=true;
    return true;
}
