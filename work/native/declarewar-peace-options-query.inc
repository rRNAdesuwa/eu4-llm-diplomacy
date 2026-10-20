// Read-only structured CB/war-goal peace-option tables.
//
// The goal object contains two native term-match tables:
//   +0x1d8 / +0x1e4  attacker-declared records
//   +0x410 / +0x41c  defender-declared records
// CB metadata contains the disabled-description records at +0x130/+0x13c.
// Each record is 0x10 bytes: int32 kind at +0 and an auxiliary/object value
// at +8.  The auxiliary value is deliberately reduced to a presence bit in
// the public projection; no native address is exposed.
//
// The including translation unit supplies `base`, `read`, the DeclareWarQuery
// helpers, and the candidate sentinel/vtable helpers.

static constexpr unsigned declarewar_peace_options_max_records=256;

struct DeclareWarPeaceOptionRecord {
    int32_t kind=0;
    bool auxiliary_present=false;
};

struct DeclareWarPeaceOptionTable {
    bool available=false;
    bool complete=false;
    unsigned count=0;
    DeclareWarPeaceOptionRecord records[
        declarewar_peace_options_max_records]{};
};

struct DeclareWarPeaceOptionsQueryResult {
    bool called=false;
    bool action_unchanged=false;
    bool complete=false;
    DeclareWarPeaceOptionTable disabled;
    DeclareWarPeaceOptionTable attacker_declared;
    DeclareWarPeaceOptionTable defender_declared;
};

static bool declarewar_peace_options_read_table(
    uintptr_t object,uintptr_t records_offset,uintptr_t count_offset,
    DeclareWarPeaceOptionTable& out) noexcept {
    out=DeclareWarPeaceOptionTable{};
    out.available=object!=0;
    if (!object) return true;
    uintptr_t records=0;
    int32_t raw_count=0;
    if (!read(object+records_offset,records)
        || !read(object+count_offset,raw_count)) return true;
    if (raw_count<0 || raw_count>static_cast<int32_t>(
            declarewar_peace_options_max_records)
        || (raw_count!=0 && !records)) return true;
    out.count=static_cast<unsigned>(raw_count);
    for (unsigned i=0;i<out.count;++i) {
        unsigned char raw[0x10]{};
        if (!read(records+static_cast<uintptr_t>(i)*0x10,raw)) {
            out.count=i;
            return true;
        }
        int32_t kind=0;
        uintptr_t auxiliary=0;
        memcpy(&kind,raw,sizeof(kind));
        memcpy(&auxiliary,raw+8,sizeof(auxiliary));
        if (kind<0 || kind>65535) { out.count=i; return true; }
        out.records[i].kind=kind;
        out.records[i].auxiliary_present=auxiliary!=0;
    }
    out.complete=true;
    return true;
}

static bool declarewar_peace_options_read_goal(
    uintptr_t goal,DeclareWarPeaceOptionTable& attacker,
    DeclareWarPeaceOptionTable& defender) noexcept {
    attacker=DeclareWarPeaceOptionTable{};
    defender=DeclareWarPeaceOptionTable{};
    if (!goal) return true;
    return declarewar_peace_options_read_table(
        goal,0x1d8,0x1e4,attacker)
        && declarewar_peace_options_read_table(
            goal,0x410,0x41c,defender);
}

static bool declarewar_peace_options_table_json(
    const DeclareWarPeaceOptionTable& table,const char* name,
    char* output,size_t capacity,size_t& used) noexcept {
    if (!name || !output || used>=capacity) return false;
    int written=snprintf(output+used,capacity-used,
        "%s\"%s\":{\"available\":%s,\"complete\":%s,\"records\":[",
        used?",":"",name,table.available?"true":"false",
        table.complete?"true":"false");
    if (written<0 || static_cast<size_t>(written)>=capacity-used) return false;
    used+=static_cast<size_t>(written);
    for (unsigned i=0;i<table.count;++i) {
        written=snprintf(output+used,capacity-used,
            "%s{\"kind\":%d,\"auxiliary_present\":%s}",
            i?",":"",table.records[i].kind,
            table.records[i].auxiliary_present?"true":"false");
        if (written<0 || static_cast<size_t>(written)>=capacity-used) return false;
        used+=static_cast<size_t>(written);
    }
    written=snprintf(output+used,capacity-used,"]}");
    if (written<0 || static_cast<size_t>(written)>=capacity-used) return false;
    used+=static_cast<size_t>(written);
    return true;
}

static bool declarewar_peace_options_query_json(
    const DeclareWarPeaceOptionsQueryResult& out,char* output,
    size_t capacity) noexcept {
    if (!output || capacity==0) return false;
    const int written=snprintf(output,capacity,
        "{\"called\":%s,\"action_unchanged\":%s,\"complete\":%s",
        out.called?"true":"false",out.action_unchanged?"true":"false",
        out.complete?"true":"false");
    if (written<0 || static_cast<size_t>(written)>=capacity) return false;
    size_t used=static_cast<size_t>(written);
    if (!declarewar_peace_options_table_json(out.disabled,"disabled",
            output,capacity,used)
        || !declarewar_peace_options_table_json(out.attacker_declared,
            "attacker_declared",output,capacity,used)
        || !declarewar_peace_options_table_json(out.defender_declared,
            "defender_declared",output,capacity,used)
        || used+2>capacity) return false;
    output[used++]='}';
    output[used]=0;
    return true;
}

static bool declarewar_peace_options_query_run(
    void* action,DeclareWarPeaceOptionsQueryResult& out) noexcept {
    out=DeclareWarPeaceOptionsQueryResult{};
    DeclareWarQueryHeader before{},after{};
    if (!declarewar_query_header(action,before)) return false;

    uintptr_t table=0,goal_getter=0,metadata_getter=0;
    if (!before.owned || !read(before.owned,table)
        || !read(table+0x58,goal_getter)
        || !read(table+0x108,metadata_getter)) return false;

    // Match the existing details-query identity guard.  The canonical empty
    // action may use the sentinel's table; a selected action must expose a
    // known Declare War candidate-owned table/vtable.
    uintptr_t sentinel=0;
    if (!declarewar_candidates_read_empty_sentinel(sentinel)
        || (before.owned!=sentinel && (table<base
            || !declarewar_candidates_known_vtable(table-base)))) return false;

    out.called=true;
    using Get=uintptr_t (*)(void*);
    uintptr_t goal=0,metadata=0;
    if (goal_getter) goal=reinterpret_cast<Get>(goal_getter)(
        reinterpret_cast<void*>(before.owned));
    if (metadata_getter) metadata=reinterpret_cast<Get>(metadata_getter)(
        reinterpret_cast<void*>(before.owned));

    // A missing goal is a valid observation with both side tables unknown;
    // metadata remains independently observable for the disabled description.
    declarewar_peace_options_read_table(
        metadata,0x130,0x13c,out.disabled);
    declarewar_peace_options_read_goal(
        goal,out.attacker_declared,out.defender_declared);

    out.action_unchanged=declarewar_query_header(action,after)
        && declarewar_query_same_header(before,after);
    out.complete=out.action_unchanged && goal!=0
        && out.disabled.complete && out.attacker_declared.complete
        && out.defender_declared.complete;
    return out.action_unchanged;
}
