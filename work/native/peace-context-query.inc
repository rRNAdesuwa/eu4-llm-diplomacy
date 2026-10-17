// Native war-context discovery. This reads the verified country/opponent
// association arrays; it does not construct, send, or execute a peace offer.
// The registry gives the public interface an opaque session-scoped identifier.
// Native object references remain private and are never used as integer IDs.

static constexpr const char* peace_query_actions[]={
    "cede_province","full_annexation","return_core","release_nation",
    "revoke_core","force_vassalization","form_personal_union",
    "release_subject","transfer_subject","grant_independence","demand_ducats",
    "war_reparations","transfer_trade_power","annul_treaties","humiliate_rival",
    "show_strength","force_religion","concede_defeat","white_peace"};

static bool peace_query_action(const char* action) noexcept {
    for (const char* item:peace_query_actions) if (!strcmp(item,action)) return true;
    return false;
}

struct PeaceWarRegistryEntry {
    uintptr_t native_reference=0;
    char public_id[30]{};
};
static PeaceWarRegistryEntry peace_war_registry[256]{};
static unsigned peace_war_registry_size=0;

static const PeaceWarRegistryEntry* peace_query_register_war(uintptr_t reference) noexcept {
    if (!reference) return nullptr;
    for (unsigned i=0;i<peace_war_registry_size;++i)
        if (peace_war_registry[i].native_reference==reference) return &peace_war_registry[i];
    if (peace_war_registry_size>=256) return nullptr;
    // SplitMix64 mixing hides the raw FILETIME. The public ID contains no PID,
    // RVA, native address, request-file marker, or native object handle.
    uint64_t epoch=observation_creation+0x9e3779b97f4a7c15ull;
    epoch=(epoch^(epoch>>30))*0xbf58476d1ce4e5b9ull;
    epoch=(epoch^(epoch>>27))*0x94d049bb133111ebull;
    epoch^=epoch>>31;
    PeaceWarRegistryEntry& entry=peace_war_registry[peace_war_registry_size];
    entry.native_reference=reference;
    snprintf(entry.public_id,sizeof(entry.public_id),"war_%016llx_%08x",
        static_cast<unsigned long long>(epoch),peace_war_registry_size+1);
    ++peace_war_registry_size;
    return &entry;
}

struct PeaceWarReferenceList {
    uintptr_t references[32]{};
    unsigned count=0;
    bool complete=false,truncated=false;
};

static bool peace_query_country_pointer(uint64_t handle,uintptr_t& country) noexcept {
    uintptr_t database=0,array=0; uint64_t identity=0;
    const unsigned slot=static_cast<unsigned>((handle>>32)&0xffffu);
    return read(base+0x233d8b0,database) && read(database+0x118,array)
        && read(array+static_cast<uintptr_t>(slot)*8,country)
        && read(country+0x20,identity) && identity==handle;
}

static bool peace_query_pair_references(uintptr_t country,unsigned other,
    PeaceWarReferenceList& output) noexcept {
    output=PeaceWarReferenceList{};
    uintptr_t rows=0; int32_t count=0;
    if (!read(country+0x1548,rows) || !read(country+0x1554,count)
        || count<0 || count>256 || (count && !rows)) return false;
    for (int32_t i=0;i<count;++i) {
        int32_t slot=-1; uintptr_t reference=0;
        const uintptr_t row=rows+static_cast<uintptr_t>(i)*16;
        if (!read(row,slot) || !read(row+8,reference)) return false;
        if (slot!=static_cast<int32_t>(other)) continue;
        if (!reference) return false;
        bool duplicate=false;
        for (unsigned j=0;j<output.count;++j)
            duplicate=duplicate || output.references[j]==reference;
        if (duplicate) continue;
        if (output.count>=32) { output.truncated=true; continue; }
        output.references[output.count++]=reference;
    }
    output.complete=!output.truncated;
    return true;
}

static bool peace_query_reference_sets_equal(const PeaceWarReferenceList& left,
    const PeaceWarReferenceList& right) noexcept {
    if (!left.complete || !right.complete || left.count!=right.count) return false;
    for (unsigned i=0;i<left.count;++i) {
        bool found=false;
        for (unsigned j=0;j<right.count;++j)
            found=found || left.references[i]==right.references[j];
        if (!found) return false;
    }
    return true;
}

static void peace_context_query_run(const char* id,const char* action_id,
    const char* actor_tag,const char* recipient_tag,uint64_t actor,
    uint64_t recipient,int32_t date) noexcept {
    uintptr_t actor_country=0,recipient_country=0;
    PeaceWarReferenceList left{},right{};
    if (!peace_query_country_pointer(actor,actor_country)
        || !peace_query_country_pointer(recipient,recipient_country)
        || !peace_query_pair_references(actor_country,
            static_cast<unsigned>((recipient>>32)&0xffffu),left)
        || !peace_query_pair_references(recipient_country,
            static_cast<unsigned>((actor>>32)&0xffffu),right)
        || !peace_query_reference_sets_equal(left,right)) {
        alliance_query_failure(id,"QUERY_PEACE_WAR_ASSOCIATIONS_UNAVAILABLE"); return;
    }
    char wars[24576]{}; size_t used=0;
    for (unsigned i=0;i<left.count;++i) {
        const PeaceWarRegistryEntry* entry=peace_query_register_war(left.references[i]);
        if (!entry) { alliance_query_failure(id,"QUERY_PEACE_WAR_REGISTRY_FULL"); return; }
        const int added=snprintf(wars+used,sizeof(wars)-used,
            "%s{\"war_id\":\"%s\",\"identity_scope\":\"observer_session\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"pair_at_war\":true,\"actor_war_role\":null,\"recipient_war_role\":null,\"roles_verified\":false,\"actor_is_war_leader\":null,\"recipient_is_war_leader\":null,\"leaders_verified\":false,\"context_complete\":false}",
            i?",":"",entry->public_id,actor_tag,recipient_tag);
        if (added<0 || static_cast<size_t>(added)>=sizeof(wars)-used) {
            alliance_query_failure(id,"QUERY_PEACE_WAR_OUTPUT_LIMIT"); return;
        }
        used+=static_cast<size_t>(added);
        char detail[600];
        snprintf(detail,sizeof(detail),
            "{\"event\":\"native_peace_context_private\",\"private\":true,\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"war_id\":\"%s\",\"native_war_reference\":\"0x%llx\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"association_verified\":true}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
            id,entry->public_id,static_cast<unsigned long long>(entry->native_reference),actor_tag,recipient_tag);
        line(detail);
    }
    char message[26000];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_peace_context_inspection\",\"family\":\"peace\",\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"action_id\":\"%s\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"initiate\",\"date_raw\":%d,\"discovery\":true,\"query_complete\":true,\"enumeration_complete\":true,\"native_offer_inspected\":false,\"full_rules_complete\":false,\"wars\":[%s],\"submitted\":false,\"frame_thread\":%lu}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
        id,action_id,actor_tag,recipient_tag,date,wars,static_cast<unsigned long>(GetCurrentThreadId()));
    line(message);
}
