// Native Insult queries. Candidate enumeration preserves the native filter;
// it never invokes the random-selection function or an execution method.
static bool insult_query_parse_id(const char* text,int& value) {
    if (!text || !*text) return false;
    const bool negative=*text=='-';
    if (negative) ++text;
    if (!*text) return false;
    uint64_t magnitude=0;
    for (;*text;++text) {
        if (*text<'0' || *text>'9') return false;
        magnitude=magnitude*10+static_cast<unsigned>(*text-'0');
        if (magnitude>2147483647u) return false;
    }
    value=negative?-static_cast<int>(magnitude):static_cast<int>(magnitude);
    return value>=-2;
}

struct InsultEffectState {
    bool active=false;
    int32_t modifier_raw=0;
    int32_t prestige_raw=0;
    unsigned modifier_rows=0;
};

static bool insult_query_country(uint64_t handle,uintptr_t& country) {
    uintptr_t database=0,array=0; uint32_t country_count=0; uint64_t actual=0;
    const unsigned slot=static_cast<unsigned>((handle>>32)&0xffffu);
    // CountryDB+124 is the live country count; the first 256 slots are only
    // the historical bridge scope. Keep the canonical handle check below so
    // a readable slot cannot be mistaken for the requested country.
    return read(base+0x233d8b0,database) && read(database+0x118,array)
        && read(database+0x124,country_count) && country_count<=4096
        && slot<country_count
        && read(array+slot*8,country) && read(country+0x20,actual) && actual==handle;
}

static bool insult_query_state(uint64_t actor,uint64_t recipient,bool scornful,
    InsultEffectState& state) {
    state=InsultEffectState{};
    uintptr_t source=0,target=0,relations=0,owner=0,definition_db=0,definition=0;
    uint64_t relation_target=0; uintptr_t buckets=0,entries=0;
    int32_t bucket_count=0,count=0;
    if (!insult_query_country(actor,source) || !insult_query_country(recipient,target)
        || !read(source+0xcf8,state.prestige_raw)
        || !read(base+0x233fee8,definition_db) || !definition_db
        || !read(definition_db+(scornful?0x320:0x2f8),definition) || !definition
        || !read(target+0x1510,relations)) return false;
    const uintptr_t relation=relations+static_cast<uintptr_t>((actor>>32)&0xffffu)*0x48;
    if (!read(relation,owner) || !owner || !read(relation+0x10,relation_target)
        || relation_target!=actor || !read(owner+0x314,bucket_count)
        || bucket_count<0 || bucket_count>4096) return false;
    const unsigned slot=static_cast<unsigned>((actor>>32)&0xffffu);
    uintptr_t bucket=owner+0x318;
    if (slot<static_cast<unsigned>(bucket_count)) {
        if (!read(owner+0x308,buckets) || !buckets) return false;
        const uintptr_t candidate=buckets+static_cast<uintptr_t>(slot)*0x18;
        int32_t candidate_count=0;
        if (!read(candidate+0x14,candidate_count)) return false;
        if (candidate_count) bucket=candidate;
    }
    if (!read(bucket+0x14,count) || count<0 || count>4096
        || (count && (!read(bucket+8,entries) || !entries))) return false;
    for (int32_t index=0;index<count;++index) {
        uintptr_t entry=0,type=0; int32_t value=0;
        if (!read(entries+static_cast<uintptr_t>(index)*8,entry) || !entry
            || !read(entry+0x10,type)) return false;
        if (type!=definition) continue;
        if (!read(entry+0x20,value)) return false;
        ++state.modifier_rows;
        // Native validity uses the same raw /1000 !=0 test.
        if (value/1000!=0) { state.active=true; state.modifier_raw=value; }
    }
    return state.modifier_rows<=1;
}

static bool insult_query_text(NativeShortString& text,char (&hex)[1025],
    bool& truncated) {
    hex[0]=0; truncated=text.size>512;
    if (text.size>65536 || text.capacity>131072 || text.size>text.capacity) return false;
    uintptr_t address=reinterpret_cast<uintptr_t>(text.text);
    if (text.capacity>=16) memcpy(&address,text.text,8);
    const unsigned length=static_cast<unsigned>(text.size<=512?text.size:512);
    unsigned char bytes[512]{}; SIZE_T copied=0;
    if (length && (!address || !ReadProcessMemory(GetCurrentProcess(),
            reinterpret_cast<void*>(address),bytes,length,&copied) || copied!=length)) return false;
    for (unsigned i=0;i<length;++i) snprintf(hex+i*2,3,"%02x",bytes[i]);
    return true;
}

struct InsultCandidates {
    bool available=false,complete=false,selected_valid=false;
    unsigned count=0;
};

static InsultCandidates insult_query_candidates(const char* query_id,uint64_t actor,
    uint64_t recipient,int32_t selected,bool emit) {
    InsultCandidates result{};
    // 859910 is the native singleton getter; filtering and rendering use
    // the same methods as SendInsultDiplomacyDialog, without RNG selection.
    uintptr_t dataset=reinterpret_cast<uintptr_t>(reinterpret_cast<void* (*)()>(base+0x859910)());
    uintptr_t array=0; int32_t count=0;
    if (!dataset || !read(dataset+0x48,array) || !read(dataset+0x54,count)
        || count<0 || count>4096 || (count && !array)) return result;
    result.available=true; result.complete=true;
    for (int32_t index=0;index<count;++index) {
        uintptr_t candidate=0; int32_t id=-1;
        if (!read(array+static_cast<uintptr_t>(index)*8,candidate) || !candidate
            || !read(candidate+0x10,id)) { result.complete=false; continue; }
        // The executor resolves action+40 by indexing this exact array.
        // Never expose a mismatched ID that would select another record.
        if (id!=index) { result.complete=false; continue; }
        if (!reinterpret_cast<bool (*)(void*,uint64_t,uint64_t)>(base+0x858fc0)(
                reinterpret_cast<void*>(candidate),actor,recipient)) continue;
        if (id==selected) result.selected_valid=true;
        if (result.count>=64) { result.complete=false; continue; }
        ++result.count;
        if (!emit) continue;
        NativeShortString text{}; text.capacity=15;
        void* returned=reinterpret_cast<void* (*)(void*,void*,uint64_t,uint64_t)>(base+0x859430)(
            reinterpret_cast<void*>(candidate),&text,actor,recipient);
        char hex[1025]{}; bool truncated=false;
        const bool readable=returned==&text && insult_query_text(text,hex,truncated);
        result.complete=result.complete && readable && !truncated;
        char message[1500];
        snprintf(message,sizeof(message),
            "{\"event\":\"native_insult_candidate\",\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"insult_id\":%d,\"text_hex\":\"%s\",\"text_readable\":%s,\"text_truncated\":%s,\"native_candidate_valid\":true}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
            query_id,id,hex,readable?"true":"false",truncated?"true":"false");
        line(message);
        reinterpret_cast<void (*)(void*)>(base+0x95660)(&text);
    }
    return result;
}

static void insult_query_run(const char* id,const char* action_id,const char* actor_tag,
    const char* recipient_tag,uint64_t actor,uint64_t recipient,int32_t date,int32_t insult_id) {
    const bool scornful=!strcmp(action_id,"scornful_insult");
    const bool selected=!scornful || insult_id>=0;
    const auto candidates=scornful?insult_query_candidates(id,actor,recipient,insult_id,true):InsultCandidates{};
    uintptr_t display=0,validity=0,diplomat=0;
    const uintptr_t vtable=base+insult_query_methods.vtable_rva;
    if (!read(vtable+0x80,validity) || validity!=base+0x538730
        || !read(vtable+0x88,display) || display!=base+0x538a00
        || !read(vtable+0x100,diplomat) || diplomat!=base+0x8f440) {
        alliance_query_failure(id,"QUERY_INSULT_METHOD_IDENTITY_CHANGED"); return;
    }
    bool visible=false; unsigned available=0;
    if (!factory_query_visibility(actor,recipient,true,visible,insult_query_methods)
        || !alliance_query_diplomats(actor,available)) {
        alliance_query_failure(id,"QUERY_INSULT_CONTEXT_UNAVAILABLE"); return;
    }
    void* action=factory_query_create(actor,recipient,true,insult_query_methods);
    if (!action) { alliance_query_failure(id,"QUERY_INSULT_FACTORY_UNAVAILABLE"); return; }
    const int32_t native_id=selected?insult_id:-1;
    memcpy(static_cast<unsigned char*>(action)+0x40,&native_id,4);
    NativeShortString diagnostic{}; diagnostic.capacity=15;
    using Predicate=bool (*)(void*,void*,unsigned char);
    const bool common=selected && reinterpret_cast<Predicate>(display)(action,nullptr,0);
    const bool rules=selected && reinterpret_cast<Predicate>(validity)(action,&diagnostic,0);
    const bool valid=rules && (!scornful || candidates.selected_valid);
    InsultEffectState effect{};
    const bool state_verified=insult_query_state(actor,recipient,scornful,effect);
    // Defines SCORNFUL_INSULT_PRESTIGE_COST is stored at this exact global.
    // The handler loads this int32, negates it and passes the same raw unit
    // to 333680; native AI compares it with country+cf8 prestige.
    int32_t prestige_cost=0;
    const bool cost_verified=!scornful || (read(base+0x233db54,prestige_cost) && prestige_cost>=0);
    char cost_json[24]{};
    if (cost_verified) snprintf(cost_json,sizeof(cost_json),"%d",prestige_cost);
    else strcpy(cost_json,"null");
    char hex[1025]{}; bool truncated=false;
    const bool readable=insult_query_text(diagnostic,hex,truncated);
    reinterpret_cast<void (*)(void*)>(base+0x95660)(&diagnostic);
    reinterpret_cast<void* (*)(void*,unsigned)>(base+0x129500)(action,1);
    char message[3300];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_alliance_inspection\",\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"action_id\":\"%s\",\"family\":\"insult\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"initiate\",\"date_raw\":%d,\"insult_id\":%d,\"insult_parameter_selected\":%s,\"ui_selection_checked\":true,\"native_visibility\":%s,\"ui_enabled_gate_checked\":%s,\"common_action_gate\":%s,\"display_predicate\":%s,\"initiation_gate\":%s,\"validity_called\":%s,\"native_validity\":%s,\"native_diagnostic_hex\":\"%s\",\"diagnostic_readable\":%s,\"diagnostic_truncated\":%s,\"diplomat_context_readable\":true,\"diplomat_required\":true,\"available_diplomat_count\":%u,\"diplomat_assignment_verified\":false,\"insult_state_verified\":%s,\"insult_active\":%s,\"opinion_modifier_raw\":%d,\"actor_prestige_raw\":%d,\"prestige_cost_raw\":%s,\"candidates_available\":%s,\"candidate_count\":%u,\"candidates_complete\":%s,\"score_applicable\":false,\"score_available\":false,\"acceptance_predicate_available\":false,\"native_would_accept\":false,\"native_total_raw\":0,\"acceptance_threshold_raw\":1,\"reason_container_readable\":false,\"reason_count\":0,\"reason_items_decoded\":false,\"full_rules_complete\":%s,\"reasons_complete\":false,\"submitted\":false,\"frame_thread\":%lu}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
        id,action_id,actor_tag,recipient_tag,date,insult_id,selected?"true":"false",visible?"true":"false",
        selected?"true":"false",common?"true":"false",common?"true":"false",common?"true":"false",
        selected?"true":"false",valid?"true":"false",hex,readable?"true":"false",truncated?"true":"false",available,
        state_verified?"true":"false",effect.active?"true":"false",effect.modifier_raw,effect.prestige_raw,
        cost_json,candidates.available?"true":"false",candidates.count,candidates.complete?"true":"false",
        selected?"true":"false",static_cast<unsigned long>(GetCurrentThreadId()));
    line(message);
}
