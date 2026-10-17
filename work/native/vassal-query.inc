// Read-only relationship state for the Vassalization UI action family.
// Include after insult-query.inc for the bounded canonical country resolver.
// The relation reader is kept separate from action visibility and validity:
// a blocked cancellation must still describe the existing relation.
struct VassalQueryState {
    bool active=false;
    bool actor_is_overlord=false;
    bool actor_is_subject=false;
    char subject_type_json[131]="null";
    int32_t prestige_raw=0;
    int32_t cancel_prestige_delta_raw=0;
    bool cancel_prestige_effect_allowed=false;
};

// a697e0 searches the owning country's subject associations. The relation row
// starts with its owner pointer; it is not a virtual table. Each 16-byte array
// item stores the other country's slot at +0 and the association pointer at +8.
static bool vassal_query_entry(uintptr_t country,uint64_t other,uintptr_t& entry) {
    uintptr_t rows=0,owner=0,begin=0; uint64_t actual=0; int32_t count=0;
    const unsigned slot=static_cast<unsigned>((other>>32)&0xffffu);
    if (slot>=256 || !read(country+0x1510,rows) || !rows) return false;
    const uintptr_t row=rows+static_cast<uintptr_t>(slot)*0x48;
    if (!read(row+0x10,actual) || actual!=other || !read(row,owner) || !owner
        || !read(owner+0x128,begin) || !read(owner+0x134,count)
        || count<0 || count>4096 || (count && !begin)) return false;
    entry=0;
    for (int32_t index=0;index<count;++index) {
        unsigned char bytes[16]{};
        if (!read(begin+static_cast<uintptr_t>(index)*16,bytes)) return false;
        int32_t item_slot=0; uintptr_t association=0;
        memcpy(&item_slot,bytes,4); memcpy(&association,bytes+8,8);
        if (item_slot!=static_cast<int32_t>(slot)) continue;
        if (entry || !association) return false;
        entry=association;
    }
    return true;
}

static bool vassal_query_relation(uint64_t actor,uint64_t recipient,
    VassalQueryState& state) {
    state=VassalQueryState{};
    uintptr_t source=0,target=0,forward=0,reverse=0;
    if (!insult_query_country(actor,source) || !insult_query_country(recipient,target)
        || !vassal_query_entry(source,recipient,forward)
        || !vassal_query_entry(target,actor,reverse) || forward!=reverse
        || !read(source+0xcf8,state.prestige_raw)
        || !read(base+0x233dd98,state.cancel_prestige_delta_raw)) return false;
    // This is the read-only predicate used by the cancellation confirmation
    // and handler. The prestige-changing function (333680) is never called.
    state.cancel_prestige_effect_allowed=reinterpret_cast<bool (*)(void*)>(base+0x3ed410)(
        reinterpret_cast<void*>(source));
    if (!forward) return true;
    // a6ac50 identifies the subject endpoint by association+18. Checking both
    // directions distinguishes an overlord's subject from its own overlord.
    uint64_t subject=0; uintptr_t descriptor=0;
    NativeShortString name{};
    if (!read(forward+0x18,subject) || (subject!=actor && subject!=recipient)
        || !read(forward+0x40,descriptor) || !descriptor
        || !read(descriptor+0x10,name) || !name.size || name.size>64
        || name.capacity<name.size || name.capacity>65536) return false;
    uintptr_t text=descriptor+0x10;
    if (name.capacity>=16) memcpy(&text,name.text,8);
    char identifier[65]{}; SIZE_T copied=0;
    if (!ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(text),
            identifier,static_cast<SIZE_T>(name.size),&copied) || copied!=name.size) return false;
    // Native subject-type identifiers are ASCII keys. Validate every byte
    // before placing the key in JSON; no localized text is interpreted here.
    for (uint64_t index=0;index<name.size;++index) {
        const unsigned char ch=static_cast<unsigned char>(identifier[index]);
        if (ch<0x20 || ch>0x7e || ch=='"' || ch=='\\') return false;
    }
    snprintf(state.subject_type_json,sizeof(state.subject_type_json),"\"%s\"",identifier);
    state.active=true;
    state.actor_is_overlord=subject==recipient;
    state.actor_is_subject=subject==actor;
    return true;
}
