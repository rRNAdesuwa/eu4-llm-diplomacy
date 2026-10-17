// Read-only Rival query.  Include this file after insult-query.inc so the
// bounded country resolver and NativeShortString diagnostic helper are
// available.  No UI action, command transport, lifecycle hook, or executor
// is called here.

struct RivalQueryState {
    bool state_verified=false;
    bool active=false;
    int32_t since_date_raw=-1;
    int32_t count=-1;
    int32_t max_rivals=-1;
    int32_t diplomatic_power_raw=-1;
    bool at_war=false;
};

static constexpr unsigned kRivalQueryMaxWalk=64;

// The Remove UI predicate and executor build this same local power-cost view.
// 952540(mode 0x12) only reads it and returns the final integer cost; it does
// not spend power.  No allocation, destructor, or executable command is used.
static bool rival_query_remove_cost(uint64_t actor,uint64_t target,int32_t& cost) {
    cost=-1;
    uint64_t native_context=0;
    if (!read(base+0x233fe88,native_context)) return false;
    alignas(8) unsigned char view[0x38]{};
    const uintptr_t vptr=base+0x1c55480;
    const int32_t discriminator=0x165,mode=0x12,enabled=1;
    const int32_t target_slot=static_cast<int16_t>((target>>32)&0xffffu),unset=-1;
    memcpy(view,&vptr,8);
    memcpy(view+8,&discriminator,4);
    memcpy(view+0x10,&mode,4);
    memcpy(view+0x14,&enabled,4);
    memcpy(view+0x18,&target_slot,4);
    memcpy(view+0x1c,&unset,4);
    memcpy(view+0x28,&native_context,8);
    using CostQuery=int32_t (*)(void*,uint64_t,void*,void*);
    cost=reinterpret_cast<CostQuery>(base+0x952540)(view,actor,nullptr,nullptr);
    return cost>=0;
}

static bool rival_query_membership(uintptr_t actor_country,uint64_t recipient_handle,
    RivalQueryState& state) {
    state=RivalQueryState{};
    uintptr_t head=0;
    unsigned char at_war_raw=0;
    if (!read(actor_country+0x2258,state.count)
        || !read(base+0x233dd14,state.max_rivals)
        || !read(actor_country+0x264,state.diplomatic_power_raw)
        || !read(actor_country+0x289b,at_war_raw)
        || !read(actor_country+0x2248,head)) return false;
    state.at_war=at_war_raw!=0;
    if (state.count<0 || state.count>static_cast<int32_t>(kRivalQueryMaxWalk)
        || state.max_rivals<0 || state.max_rivals>static_cast<int32_t>(kRivalQueryMaxWalk))
        return false;

    const uint16_t recipient_slot=static_cast<uint16_t>((recipient_handle>>32)&0xffffu);
    uintptr_t node=head;
    uintptr_t visited[kRivalQueryMaxWalk]{};
    bool active=false;
    int32_t since=-1;
    for (int32_t index=0;index<state.count;++index) {
        if (!node || node<0x10000) return false;
        for (int32_t prior=0;prior<index;++prior)
            if (visited[prior]==node) return false; // reject a cycle
        visited[index]=node;
        uint64_t target_handle=0;
        int32_t date_raw=0;
        uintptr_t next=0;
        if (!read(node+0x10,target_handle) || !read(node+0x18,date_raw)
            || !read(node+0x28,next) || !target_handle) return false;
        // The native rival membership comparison uses the 16-bit country slot.
        // Keep the caller's canonical handle for the JSON actor/recipient fields.
        if (static_cast<uint16_t>((target_handle>>32)&0xffffu)==recipient_slot) {
            if (active) return false; // duplicate target is inconsistent state
            active=true;
            since=date_raw;
        }
        node=next;
    }
    if (node!=0) return false; // the counted list must terminate exactly here
    state.state_verified=true;
    state.active=active;
    state.since_date_raw=active?since:-1;
    return true;
}

struct RivalRuleEvaluation {
    RivalQueryState state{};
    bool state_readable=false,command_called=false,command_validity=false;
    bool candidate_called=false,candidate_eligible=false,target_exists=false;
    bool cost_called=false,complete=false,available=false;
    int32_t diplomatic_power_cost=-1;
    bool diagnostic_readable=false,diagnostic_truncated=false;
    char diagnostic_hex[1025]{};
};

// Shared by inspection, submission preflight, and the final execution gate.
// This evaluates the original command and UI predicates without submitting.
static RivalRuleEvaluation rival_evaluate(const char* action_id,
    uint64_t actor_handle,uint64_t recipient_handle) {
    RivalQueryState state{};
    uintptr_t actor_country=0,recipient_country=0;
    const bool countries_readable=insult_query_country(actor_handle,actor_country)
        && insult_query_country(recipient_handle,recipient_country)
        && actor_handle!=recipient_handle;
    const bool state_readable=countries_readable
        && rival_query_membership(actor_country,recipient_handle,state);

    bool command_called=false,command_validity=false;
    bool candidate_called=false,candidate_eligible=false,target_exists=false;
    bool cost_called=false;
    int32_t diplomatic_power_cost=-1;
    int32_t target_province_count=0;
    unsigned char target_type=0;
    const bool target_state_readable=countries_readable
        && read(recipient_country+0x1344,target_province_count)
        && read(recipient_country+0x26,target_type);
    if (target_state_readable)
        target_exists=target_province_count!=0 || target_type==7;
    bool diagnostic_rule_validity=false;
    NativeShortString diagnostic{}; diagnostic.capacity=15;
    if (state_readable
        && (!strcmp(action_id,"set_rival") || !strcmp(action_id,"remove_rival"))) {
        // The original command predicate reads only the two handle fields at
        // +0x50/+0x58 and then reaches the native country/rule helpers.  This
        // is an input view, not a constructed action object: it has no vptr,
        // and it is never passed to a destructor or transport routine.
        alignas(8) unsigned char input_view[0x60]{};
        memcpy(input_view+0x50,&actor_handle,sizeof(actor_handle));
        memcpy(input_view+0x58,&recipient_handle,sizeof(recipient_handle));
        using CommandPredicate=bool (*)(void*);
        const uintptr_t command_rva=!strcmp(action_id,"set_rival")
            ?0x2ab7b0:0x2ad430;
        command_validity=reinterpret_cast<CommandPredicate>(base+command_rva)(input_view);
        command_called=true;

        // The rule helper produces the native diagnostic.  Keep its result
        // separate in the implementation; the public event's validity is the
        // original Set/Remove command predicate above.
        using RulePredicate=bool (*)(void*,uint64_t,NativeShortString*);
        const uintptr_t rule_rva=!strcmp(action_id,"set_rival")
            ?0x3d2790:0x3d29a0;
        diagnostic_rule_validity=reinterpret_cast<RulePredicate>(base+rule_rva)(
            reinterpret_cast<void*>(actor_country),
            recipient_handle,&diagnostic);

        // f14d80 uses this original predicate for its selectable rival rows.
        // Its assembly sets both R8D and R9B to 1: the decompiler's three-arg
        // call omits the fourth ABI argument.  This method also checks that
        // the target belongs to the native relation/additional candidate set.
        // Keep its result separate from the Set/Remove command validity.
        if (target_state_readable) {
            using CandidatePredicate=bool (*)(void*,uint64_t,unsigned char,bool);
            candidate_eligible=reinterpret_cast<CandidatePredicate>(base+0x3d1c60)(
                reinterpret_cast<void*>(actor_country),recipient_handle,1,true);
            candidate_called=true;
        }
        if (!strcmp(action_id,"remove_rival"))
            cost_called=rival_query_remove_cost(actor_handle,recipient_handle,
                diplomatic_power_cost);
    }

    char diagnostic_hex[1025]{};
    bool diagnostic_truncated=false;
    const bool diagnostic_readable=insult_query_text(
        diagnostic,diagnostic_hex,diagnostic_truncated);
    reinterpret_cast<void (*)(void*)>(base+0x95660)(&diagnostic);

    RivalRuleEvaluation result{};
    result.state=state;
    result.state_readable=state_readable;
    result.command_called=command_called;
    result.command_validity=command_validity;
    result.candidate_called=candidate_called;
    result.candidate_eligible=candidate_eligible;
    result.target_exists=target_exists;
    result.cost_called=cost_called;
    result.diplomatic_power_cost=diplomatic_power_cost;
    result.diagnostic_readable=diagnostic_readable;
    result.diagnostic_truncated=diagnostic_truncated;
    memcpy(result.diagnostic_hex,diagnostic_hex,sizeof(diagnostic_hex));
    const bool set=!strcmp(action_id,"set_rival");
    const bool remove=!strcmp(action_id,"remove_rival");
    result.complete=state_readable && command_called
        && ((set && target_state_readable && candidate_called)
            || (remove && cost_called));
    result.available=result.complete && !state.at_war && command_validity
        && (set ? (!state.active && target_exists && candidate_eligible
            && state.count<state.max_rivals)
            : (state.active && diplomatic_power_cost<=state.diplomatic_power_raw));
    (void)diagnostic_rule_validity;
    return result;
}

static void rival_query_run(const char* id,const char* action_id,
    const char* actor_tag,const char* recipient_tag,uint64_t actor_handle,
    uint64_t recipient_handle,int32_t date) {
    const RivalRuleEvaluation result=rival_evaluate(action_id,actor_handle,recipient_handle);
    const auto& state=result.state;
    const bool state_readable=result.state_readable;
    const bool command_called=result.command_called,command_validity=result.command_validity;
    const bool candidate_called=result.candidate_called,candidate_eligible=result.candidate_eligible;
    const bool target_exists=result.target_exists,cost_called=result.cost_called;
    const int32_t diplomatic_power_cost=result.diplomatic_power_cost;
    const bool diagnostic_readable=result.diagnostic_readable;
    const bool diagnostic_truncated=result.diagnostic_truncated;
    const char* diagnostic_hex=result.diagnostic_hex;
    char message[2700];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_rival_inspection\",\"rules_schema\":3,\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"action_id\":\"%s\",\"family\":\"rival\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"initiate\",\"date_raw\":%d,\"native_command_validity_called\":%s,\"native_command_validity\":%s,\"rival_state_verified\":%s,\"rival_active\":%s,\"rival_since_date_raw\":%d,\"rival_count\":%d,\"max_rivals\":%d,\"diplomatic_power_raw\":%d,\"at_war\":%s,\"native_diagnostic_hex\":\"%s\",\"diagnostic_readable\":%s,\"diagnostic_truncated\":%s,\"candidate_eligibility_available\":%s,\"candidate_eligible\":%s,\"target_exists\":%s,\"ui_war_allowed\":%s,\"cost_query_called\":%s,\"diplomatic_power_cost_raw\":%d,\"full_rules_complete\":%s,\"native_action_available\":%s,\"submitted\":false,\"frame_thread\":%lu}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),
        static_cast<unsigned long long>(observation_creation),id?id:"",action_id?action_id:"",
        actor_tag?actor_tag:"",recipient_tag?recipient_tag:"",date,
        command_called?"true":"false",command_validity?"true":"false",
        state_readable&&state.state_verified?"true":"false",
        state_readable&&state.active?"true":"false",
        state_readable?state.since_date_raw:-1,
        state_readable?state.count:-1,state_readable?state.max_rivals:-1,
        state_readable?state.diplomatic_power_raw:-1,
        state_readable&&state.at_war?"true":"false",diagnostic_hex,
        diagnostic_readable?"true":"false",diagnostic_truncated?"true":"false",
        candidate_called?"true":"false",candidate_eligible?"true":"false",
        target_exists?"true":"false",state_readable&&!state.at_war?"true":"false",
        cost_called?"true":"false",diplomatic_power_cost,
        result.complete?"true":"false",result.available?"true":"false",
        static_cast<unsigned long>(GetCurrentThreadId()));
    line(message);
}
