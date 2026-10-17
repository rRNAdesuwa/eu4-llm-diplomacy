// Read-only native war-context capture for an already constructed CPeaceOffer.
//
// FUN_14097bba0 resolves the pair stored in offer+0x18/+0x10 through the
// country +0x1510 relation table and returns the native war context used by
// FUN_14097bd10.  This helper calls that getter once, validates the two
// participant vectors, and keeps the returned address private.  It never
// treats the address as a public ID and never modifies the offer or war.

struct PeaceWarSideMembers {
    uint64_t handles[256]{};
    char tags[256][4]{};
    unsigned count=0;
    bool readable=false;
    bool complete=false;
    bool tags_complete=false;
    bool canonical=true;
};

struct PeaceWarOfferContextCapture {
    uint64_t actor=0;
    uint64_t recipient=0;
    unsigned char direction=0;

    PeaceWarSideMembers side_a{}; // war+0x48 / war+0x50 / war+0x58
    PeaceWarSideMembers side_b{}; // war+0x78 / war+0x80 / war+0x88

    unsigned char selected_side=0; // 1=side_a, 2=side_b, 0=ambiguous
    unsigned char actor_side=0;    // 1=side_a, 2=side_b, 0=unknown
    unsigned char recipient_side=0;
    unsigned char claimant_side=0; // native offer +0x18 side
    unsigned char payer_side=0;    // native offer +0x10 side
    bool actor_recipient_opposite=false;
    bool offer_identity_verified=false;
    bool war_context_resolved=false;
    bool offer_vectors_readable=false;
    bool primary_offer_mapping_verified=false;
    bool derived_offer_mapping_verified=false;
    bool offer_vector_mapping_verified=false;
    bool complete=false;

    // Private-only evidence.  Public JSON helpers below never serialize it.
    uintptr_t native_war_context=0;
};

// The native offer stores the claimant at +0x18 and payer at +0x10. An offer
// reverses those native endpoints while the outer action keeps actor/recipient
// in the public request order.
static uint64_t peace_offer_claimant(uint64_t actor,uint64_t recipient,
    bool demand=true) noexcept {
    return demand?actor:recipient;
}

static uint64_t peace_offer_payer(uint64_t actor,uint64_t recipient,
    bool demand=true) noexcept {
    return demand?recipient:actor;
}

static bool peace_war_capture_vector(uintptr_t object,uintptr_t begin_offset,
    uintptr_t end_offset,uintptr_t capacity_offset,PeaceWarSideMembers& output) noexcept {
    output=PeaceWarSideMembers{};
    uintptr_t begin=0,end=0,capacity=0;
    if (!object || !read(object+begin_offset,begin)
        || !read(object+end_offset,end) || !read(object+capacity_offset,capacity)
        || end<begin || capacity<end || (end-begin)%8) return false;
    const uintptr_t bytes=end-begin;
    if (bytes/8>256 || (bytes && !begin)) return false;
    output.readable=true;
    output.count=static_cast<unsigned>(bytes/8);
    for (unsigned i=0;i<output.count;++i) {
        uint64_t handle=0; uintptr_t country=0;
        if (!read(begin+static_cast<uintptr_t>(i)*8,handle)
            || !handle || !peace_query_country_pointer(handle,country)) {
            output.canonical=false;
            output.complete=false;
            return false;
        }
        output.handles[i]=handle;
        const unsigned char tag0=static_cast<unsigned char>(handle&0xffu);
        const unsigned char tag1=static_cast<unsigned char>((handle>>8)&0xffu);
        const unsigned char tag2=static_cast<unsigned char>((handle>>16)&0xffu);
        const auto ascii_alnum=[](unsigned char value) noexcept {
            return (value>='A' && value<='Z')
                || (value>='a' && value<='z')
                || (value>='0' && value<='9');
        };
        if (!ascii_alnum(tag0) || !ascii_alnum(tag1) || !ascii_alnum(tag2)) {
            output.canonical=false;
            output.complete=false;
            output.tags_complete=false;
            return false;
        }
        output.tags[i][0]=static_cast<char>(tag0);
        output.tags[i][1]=static_cast<char>(tag1);
        output.tags[i][2]=static_cast<char>(tag2);
        output.tags[i][3]=0;
    }
    output.tags_complete=true;
    output.complete=true;
    return true;
}

static bool peace_war_side_contains(const PeaceWarSideMembers& side,
    uint64_t handle) noexcept {
    for (unsigned i=0;i<side.count;++i)
        if (side.handles[i]==handle) return true;
    return false;
}

static bool peace_war_side_contains_slot(const PeaceWarSideMembers& side,
    uint64_t handle) noexcept {
    const unsigned slot=static_cast<unsigned>((handle>>32)&0xffffu);
    for (unsigned i=0;i<side.count;++i)
        if (static_cast<unsigned>((side.handles[i]>>32)&0xffffu)==slot) return true;
    return false;
}

static bool peace_war_members_equal(const PeaceWarSideMembers& left,
    const PeaceWarSideMembers& right) noexcept {
    if (!left.readable || !left.complete || !right.readable || !right.complete
        || left.count!=right.count) return false;
    for (unsigned i=0;i<left.count;++i)
        if (left.handles[i]!=right.handles[i]) return false;
    return true;
}

static bool peace_war_side_tags_json(const PeaceWarSideMembers& side,
    char* output,size_t capacity) noexcept {
    if (!output || !capacity || !side.tags_complete || side.count>256) return false;
    size_t used=0;
    if (used+1>=capacity) return false;
    output[used++]='[';
    for (unsigned i=0;i<side.count;++i) {
        if (i && used+1>=capacity) return false;
        if (i) output[used++]=',';
        if (used+5>=capacity) return false;
        output[used++]='"';
        output[used++]=side.tags[i][0];
        output[used++]=side.tags[i][1];
        output[used++]=side.tags[i][2];
        output[used++]='"';
    }
    if (used+2>capacity) return false;
    output[used++]=']';
    output[used]=0;
    return true;
}

static bool peace_war_capture_offer_context(const void* offer_object,
    uint64_t actor,uint64_t recipient,PeaceWarOfferContextCapture& output,
    bool demand=true) noexcept {
    output=PeaceWarOfferContextCapture{};
    const uintptr_t offer=reinterpret_cast<uintptr_t>(offer_object);
    if (!offer) return false;
    uintptr_t vtable=0,owner=0;
    uint32_t discriminator=0;
    uint64_t stored_payer=0,stored_claimant=0;
    const uint64_t expected_payer=peace_offer_payer(actor,recipient,demand);
    const uint64_t expected_claimant=peace_offer_claimant(actor,recipient,demand);
    if (!read(offer,vtable) || vtable!=base+0x1c578b8
        || !read(offer+8,discriminator) || discriminator!=0x165
        || !read(offer+0x10,stored_payer) || stored_payer!=expected_payer
        || !read(offer+0x18,stored_claimant) || stored_claimant!=expected_claimant
        || !read(offer+0x20,output.direction)
        || output.direction!=(demand?1u:0u)
        || !read(offer+0xe8,owner) || owner!=offer) return false;
    output.actor=actor;
    output.recipient=recipient;
    output.offer_identity_verified=true;

    using WarLookup=uint64_t (*)(void*);
    const uintptr_t war=static_cast<uintptr_t>(
        reinterpret_cast<WarLookup>(base+0x97bba0)(const_cast<void*>(offer_object)));
    output.native_war_context=war;
    if (!war) return false;
    output.war_context_resolved=true;

    // 0x97bd10 uses begin/end; the capacity words are checked here as part of
    // the three-pointer vector identity before any element is consumed.
    if (!peace_war_capture_vector(war,0x48,0x50,0x58,output.side_a)
        || !peace_war_capture_vector(war,0x78,0x80,0x88,output.side_b)) return false;

    const bool actor_a=peace_war_side_contains(output.side_a,actor);
    const bool actor_b=peace_war_side_contains(output.side_b,actor);
    const bool recipient_a=peace_war_side_contains(output.side_a,recipient);
    const bool recipient_b=peace_war_side_contains(output.side_b,recipient);
    if ((actor_a==actor_b) || (recipient_a==recipient_b)) return false;
    output.actor_side=actor_a?1:2;
    output.recipient_side=recipient_a?1:2;
    output.actor_recipient_opposite=output.actor_side!=output.recipient_side;
    if (!output.actor_recipient_opposite) return false;

    const bool claimant_a=peace_war_side_contains(output.side_a,expected_claimant);
    const bool claimant_b=peace_war_side_contains(output.side_b,expected_claimant);
    const bool payer_a=peace_war_side_contains(output.side_a,expected_payer);
    const bool payer_b=peace_war_side_contains(output.side_b,expected_payer);
    if ((claimant_a==claimant_b) || (payer_a==payer_b)) return false;
    output.claimant_side=claimant_a?1:2;
    output.payer_side=payer_a?1:2;

    // The native branch compares only the high 16 bits of offer+0x18.
    const bool selector_a=peace_war_side_contains_slot(output.side_a,expected_claimant);
    const bool selector_b=peace_war_side_contains_slot(output.side_b,expected_claimant);
    if (selector_a==selector_b) return false;
    output.selected_side=selector_a?1:2;
    if (output.selected_side!=output.claimant_side
        || output.payer_side==output.claimant_side) return false;

    PeaceWarSideMembers offer_vectors[4]{};
    static constexpr uintptr_t offsets[]={0x28,0x40,0x58,0x70};
    for (unsigned i=0;i<4;++i)
        if (!peace_war_capture_vector(offer,offsets[i],offsets[i]+8,
            offsets[i]+16,offer_vectors[i])) return false;
    output.offer_vectors_readable=true;
    const PeaceWarSideMembers& selected=output.selected_side==1?output.side_a:output.side_b;
    const PeaceWarSideMembers& opposite=output.selected_side==1?output.side_b:output.side_a;
    const bool primary_opposite=peace_war_members_equal(offer_vectors[0],opposite);
    const bool primary_selected=peace_war_members_equal(offer_vectors[1],selected);
    const bool derived_opposite=peace_war_members_equal(offer_vectors[2],opposite);
    const bool derived_selected=peace_war_members_equal(offer_vectors[3],selected);
    output.primary_offer_mapping_verified=primary_opposite && primary_selected;
    output.derived_offer_mapping_verified=derived_opposite && derived_selected;
    output.offer_vector_mapping_verified=output.primary_offer_mapping_verified
        && output.derived_offer_mapping_verified;
    output.complete=true;
    return true;
}

static bool peace_war_offer_context_public_json(
    const PeaceWarOfferContextCapture& capture,char* output,size_t capacity) noexcept {
    if (!output || !capacity) return false;
    char side_a_members[2048]{};
    char side_b_members[2048]{};
    if (!peace_war_side_tags_json(capture.side_a,side_a_members,sizeof(side_a_members))
        || !peace_war_side_tags_json(capture.side_b,side_b_members,sizeof(side_b_members)))
        return false;
    const char* actor_side=capture.actor_side==1?"side_a":
        capture.actor_side==2?"side_b":"unknown";
    const char* recipient_side=capture.recipient_side==1?"side_a":
        capture.recipient_side==2?"side_b":"unknown";
    const char* selected_side=capture.selected_side==1?"side_a":
        capture.selected_side==2?"side_b":"unknown";
    const char* claimant_side=capture.claimant_side==1?"side_a":
        capture.claimant_side==2?"side_b":"unknown";
    const char* payer_side=capture.payer_side==1?"side_a":
        capture.payer_side==2?"side_b":"unknown";
    const int written=snprintf(output,capacity,
        "{\"war_context_resolved\":%s,\"side_a_count\":%u,\"side_b_count\":%u,"
        "\"side_a_members\":%s,\"side_b_members\":%s,"
        "\"participant_lists_complete\":%s,\"members_capture_complete\":%s,"
        "\"selected_side\":\"%s\","
        "\"actor_side\":\"%s\",\"recipient_side\":\"%s\","
        "\"claimant_side\":\"%s\",\"payer_side\":\"%s\","
        "\"actor_side_verified\":%s,\"recipient_side_verified\":%s,"
        "\"actor_recipient_opposite\":%s,\"offer_identity_verified\":%s,"
        "\"offer_vectors_readable\":%s,\"primary_offer_mapping_verified\":%s,"
        "\"derived_offer_mapping_verified\":%s,\"offer_vector_mapping_verified\":%s,"
        "\"roles_verified\":false,\"leaders_verified\":false,\"context_complete\":false}",
        capture.war_context_resolved?"true":"false",capture.side_a.count,capture.side_b.count,
        side_a_members,side_b_members,
        (capture.side_a.complete && capture.side_b.complete
            && capture.side_a.tags_complete && capture.side_b.tags_complete)?"true":"false",
        (capture.side_a.complete && capture.side_b.complete
            && capture.side_a.tags_complete && capture.side_b.tags_complete)?"true":"false",
        selected_side,actor_side,recipient_side,claimant_side,payer_side,
        capture.actor_side!=0?"true":"false",capture.recipient_side!=0?"true":"false",
        capture.actor_recipient_opposite?"true":"false",
        capture.offer_identity_verified?"true":"false",capture.offer_vectors_readable?"true":"false",
        capture.primary_offer_mapping_verified?"true":"false",
        capture.derived_offer_mapping_verified?"true":"false",
        capture.offer_vector_mapping_verified?"true":"false");
    return written>=0 && static_cast<size_t>(written)<capacity;
}

// This helper is for a private JSONL event only.  Never pass its output to the
// public query projection: native_war_context is an address, not a public ID.
static bool peace_war_offer_context_private_json(
    const PeaceWarOfferContextCapture& capture,const char* session_id,
    const char* query_id,
    char* output,size_t capacity) noexcept {
    if (!output || !capacity) return false;
    const int written=snprintf(output,capacity,
        "{\"event\":\"native_peace_war_context_private\",\"private\":true,"
        "\"session_id\":\"%s\",\"query_id\":\"%s\",\"native_war_context\":\"0x%llx\","
        "\"side_a_count\":%u,\"side_b_count\":%u,\"actor_side\":%u,"
        "\"recipient_side\":%u,\"claimant_side\":%u,\"payer_side\":%u,\"selected_side\":%u,"
        "\"members_capture_complete\":%s}\n",
        session_id?session_id:"",query_id?query_id:"",
        static_cast<unsigned long long>(capture.native_war_context),
        capture.side_a.count,capture.side_b.count,static_cast<unsigned>(capture.actor_side),
        static_cast<unsigned>(capture.recipient_side),static_cast<unsigned>(capture.claimant_side),
        static_cast<unsigned>(capture.payer_side),static_cast<unsigned>(capture.selected_side),
        (capture.side_a.complete && capture.side_b.complete
            && capture.side_a.tags_complete && capture.side_b.tags_complete)?
            "true":"false");
    return written>=0 && static_cast<size_t>(written)<capacity;
}
