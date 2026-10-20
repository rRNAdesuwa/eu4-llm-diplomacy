// DeclareWarDialog's authored display paths. Evidence: R62 50a7b0,
// 1f78c0 and 1f79a0; candidate +0x40/+0x48 are the title/description
// methods used by 50a7b0. All strings are owned temporaries, never commands.
template <unsigned Limit> struct DeclareWarDisplayText {
    bool applicable=true;
    bool called=false;
    bool return_verified=false;
    bool readable=false;
    bool truncated=false;
    char hex[Limit*2+1]{};
};

struct DeclareWarDetailsQueryResult {
    bool called=false;
    bool action_unchanged=false;
    DeclareWarDisplayText<512> casus_belli_name;
    DeclareWarDisplayText<2048> casus_belli_description;
    DeclareWarDisplayText<512> war_goal_name;
    DeclareWarDisplayText<2048> war_goal_description;
    DeclareWarDisplayText<4096> disabled_peace_terms_description;
    DeclareWarDisplayText<8192> declaration_description;
};

template <unsigned Limit> static void declarewar_details_capture_text(
    NativeShortString& text,DeclareWarDisplayText<Limit>& out) {
    out.truncated=text.size>Limit;
    const unsigned length=static_cast<unsigned>(text.size<Limit?text.size:Limit);
    uintptr_t address=reinterpret_cast<uintptr_t>(text.text);
    if (text.capacity>=16) memcpy(&address,text.text,8);
    unsigned char bytes[Limit]{};
    SIZE_T copied=0;
    out.readable=text.size<=65536 && text.capacity<=131072
        && text.size<=text.capacity && (length==0 || (address
            && ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(address),
                bytes,length,&copied) && copied==length));
    if (out.readable) for (unsigned i=0;i<length;++i)
        snprintf(out.hex+i*2,3,"%02x",bytes[i]);
    using Destroy=void (*)(void*);
    reinterpret_cast<Destroy>(base+0x95660)(&text);
}

template <unsigned Limit> static void declarewar_details_call(
    uintptr_t function,void* object,DeclareWarDisplayText<Limit>& out) {
    NativeShortString text{};
    text.capacity=15;
    using Describe=NativeShortString* (*)(void*,NativeShortString*);
    out.called=true;
    out.return_verified=reinterpret_cast<Describe>(function)(object,&text)==&text;
    declarewar_details_capture_text(text,out);
}

static bool declarewar_details_query_run(void* action,
    DeclareWarDetailsQueryResult& out) {
    out=DeclareWarDetailsQueryResult{};
    DeclareWarQueryHeader before{},after{};
    if (!declarewar_query_header(action,before)) return false;
    uintptr_t table=0,metadata_getter=0,presence=0,title=0,description=0;
    if (!before.owned || !read(before.owned,table)
        || !read(table+0x108,metadata_getter) || !metadata_getter
        || !read(table+0x78,presence) || !presence
        || !read(table+0x40,title) || !title
        || !read(table+0x48,description) || !description) return false;
    // Selection binds a concrete class in d9a960's copy family; discovery
    // and no-CB use the engine's canonical sentinel, which the UI also reads.
    uintptr_t sentinel=0;
    if (!declarewar_candidates_read_empty_sentinel(sentinel)
        || (before.owned!=sentinel && (table<base
            || !declarewar_candidates_known_vtable(table-base)))) return false;
    using Metadata=void* (*)(void*);
    void* metadata=reinterpret_cast<Metadata>(metadata_getter)(
        reinterpret_cast<void*>(before.owned));
    DeclareWarCandidateCapture cb{};
    if (!metadata || !declarewar_candidates_capture_text(
            reinterpret_cast<uintptr_t>(metadata),cb)
        || !cb.casus_belli_key_verified) return false;
    out.called=true;
    NativeShortString name{};
    name.capacity=15;
    using Localize=NativeShortString* (*)(NativeShortString*,const char*,uintptr_t,uintptr_t);
    out.casus_belli_name.called=true;
    out.casus_belli_name.return_verified=reinterpret_cast<Localize>(base+0x14b33a0)(
        &name,cb.casus_belli_key,0,0)==&name;
    declarewar_details_capture_text(name,out.casus_belli_name);
    declarewar_details_call(base+0x1f78c0,metadata,out.casus_belli_description);
    declarewar_details_call(base+0x1f79a0,metadata,out.disabled_peace_terms_description);
    using Present=bool (*)(void*);
    const bool present=reinterpret_cast<Present>(presence)(
        reinterpret_cast<void*>(before.owned));
    out.war_goal_name.applicable=present;
    out.war_goal_description.applicable=present;
    if (present) {
        declarewar_details_call(title,reinterpret_cast<void*>(before.owned),out.war_goal_name);
        declarewar_details_call(description,reinterpret_cast<void*>(before.owned),out.war_goal_description);
    }
    declarewar_details_call(base+0x50a7b0,action,out.declaration_description);
    out.action_unchanged=declarewar_query_header(action,after)
        && declarewar_query_same_header(before,after);
    return out.action_unchanged;
}

template <unsigned Limit> static bool declarewar_details_text_complete(
    const DeclareWarDisplayText<Limit>& text) {
    return !text.applicable || (text.called && text.return_verified
        && text.readable && !text.truncated);
}

template <unsigned Limit> static bool declarewar_details_text_json(
    char* output,size_t capacity,size_t& used,const char* name,
    const DeclareWarDisplayText<Limit>& text) {
    const int written=snprintf(output+used,capacity-used,
        ",\"%s\":{\"applicable\":%s,\"called\":%s,\"return_verified\":%s,\"text_hex\":\"%s\",\"readable\":%s,\"truncated\":%s}",
        name,text.applicable?"true":"false",text.called?"true":"false",
        text.return_verified?"true":"false",text.hex,
        text.readable?"true":"false",text.truncated?"true":"false");
    if (written<0 || static_cast<size_t>(written)>=capacity-used) return false;
    used+=static_cast<size_t>(written);
    return true;
}

static bool declarewar_details_query_json(const DeclareWarDetailsQueryResult& out,
    char* output,size_t capacity) {
    const bool complete=declarewar_details_text_complete(out.casus_belli_name)
        && declarewar_details_text_complete(out.casus_belli_description)
        && declarewar_details_text_complete(out.war_goal_name)
        && declarewar_details_text_complete(out.war_goal_description)
        && declarewar_details_text_complete(out.disabled_peace_terms_description)
        && declarewar_details_text_complete(out.declaration_description);
    const int written=snprintf(output,capacity,
        "{\"called\":%s,\"action_unchanged\":%s,\"complete\":%s",
        out.called?"true":"false",out.action_unchanged?"true":"false",complete?"true":"false");
    if (written<0 || static_cast<size_t>(written)>=capacity) return false;
    size_t used=static_cast<size_t>(written);
    if (!declarewar_details_text_json(output,capacity,used,"casus_belli_name",out.casus_belli_name)
        || !declarewar_details_text_json(output,capacity,used,"casus_belli_description",out.casus_belli_description)
        || !declarewar_details_text_json(output,capacity,used,"war_goal_name",out.war_goal_name)
        || !declarewar_details_text_json(output,capacity,used,"war_goal_description",out.war_goal_description)
        || !declarewar_details_text_json(output,capacity,used,"disabled_peace_terms_description",out.disabled_peace_terms_description)
        || !declarewar_details_text_json(output,capacity,used,"declaration_description",out.declaration_description)
        || used+2>capacity) return false;
    output[used++]='}';
    output[used]=0;
    return true;
}
