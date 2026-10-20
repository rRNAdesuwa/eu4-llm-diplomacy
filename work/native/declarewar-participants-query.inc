// DeclareWarDialog's participant records (503ea0) and prospective Call action
// context (ee0260). Only the final DeclareWar action owns selected vectors.
#include "declarewar-selection.h"

struct DeclareWarParticipantSelection {
    bridge::CountryTagList call_allies{},promise_land_to{},co_belligerents{};
};
struct DeclareWarParticipantVector { uintptr_t begin=0,end=0,capacity=0; };
struct DeclareWarParticipantNativeList {
    DeclareWarParticipantVector attackers{},defenders{};
    unsigned char flag=0;
};
static_assert(sizeof(DeclareWarParticipantNativeList)==0x38,"participant list ABI");
struct DeclareWarParticipant {
    uint64_t country=0,related=0;
    int32_t join_reason=0;
    bool attacker=false,automatic=false,selected=false,promise=false;
    bool promise_available=false,context_complete=false,legal=false;
    bool score_available=false,reasons_complete=false,would_call=false;
    int32_t score=0;
};
struct DeclareWarParticipantsResult {
    bool called=false,complete=false,selection_applied=false,selection_allowed=false;
    bool action_unchanged=false;
    unsigned count=0;
    DeclareWarParticipant items[64]{};
};

static bool declarewar_participant_tag(uint64_t handle,char (&tag)[4]) {
    tag[0]=static_cast<char>(handle); tag[1]=static_cast<char>(handle>>8);
    tag[2]=static_cast<char>(handle>>16); tag[3]=0;
    uint64_t actual=0;
    return bridge::declarewar_selection::detail::tag_bytes_valid(tag,3)
        && alliance_query_country(tag,actual) && actual==handle;
}
static bool declarewar_participant_country(uint64_t handle,uintptr_t& country) {
    uintptr_t db=0,data=0; uint32_t count=0; uint64_t actual=0;
    const unsigned slot=static_cast<unsigned>((handle>>32)&0xffff);
    return read(base+0x233d8b0,db) && read(db+0x118,data)
        && read(db+0x124,count) && count<=4096 && slot<count
        && read(data+slot*8,country) && read(country+0x20,actual) && actual==handle;
}
static bool declarewar_participant_selected(const bridge::CountryTagList& list,uint64_t handle) {
    char tag[4]{static_cast<char>(handle),static_cast<char>(handle>>8),static_cast<char>(handle>>16),0};
    return bridge::declarewar_selection::detail::list_contains(list,tag);
}
static void declarewar_participant_csv(const bridge::CountryTagList& list,char (&out)[64]) {
    if (!list.count) { strcpy(out,"-"); return; }
    for (unsigned i=0;i<list.count;++i) {
        if (i) out[i*4-1]=',';
        memcpy(out+i*4,list.tags[i],3);
    }
}
static bool declarewar_participants_enumerate(void* action,DeclareWarParticipantsResult& out) {
    DeclareWarParticipantNativeList list{};
    using Enumerate=void* (*)(void*,void*,unsigned char);
    out.called=true;
    const bool returned=reinterpret_cast<Enumerate>(base+0x503ea0)(action,&list,1)==&list;
    bool complete=returned;
    uint64_t actor=0,target=0;
    complete=read(reinterpret_cast<uintptr_t>(action)+0x10,actor)
        && read(reinterpret_cast<uintptr_t>(action)+0x20,target) && complete;
    const DeclareWarParticipantVector vectors[]={list.attackers,list.defenders};
    for (unsigned side=0;side<2;++side) {
        const auto& vector=vectors[side];
        if (vector.end<vector.begin || vector.capacity<vector.end
            || (vector.end-vector.begin)%24 || (vector.capacity-vector.begin)%24
            || (vector.end-vector.begin)/24>4096) { complete=false; continue; }
        for (uintptr_t p=vector.begin;p<vector.end;p+=24) {
            unsigned char raw[24]{};
            if (!read(p,raw)) { complete=false; break; }
            DeclareWarParticipant item{};
            memcpy(&item.country,raw,8); memcpy(&item.join_reason,raw+8,4);
            memcpy(&item.related,raw+12,8);
            if (item.country==actor || item.country==target) continue;
            char country[4]{},related[4]{};
            if (out.count>=64 || raw[20]>1
                || !declarewar_participant_tag(item.country,country)
                || !declarewar_participant_tag(item.related,related)) { complete=false; continue; }
            item.attacker=side==0; item.automatic=raw[20]!=0;
            out.items[out.count++]=item;
        }
    }
    using Cleanup=void (*)(void*);
    reinterpret_cast<Cleanup>(base+0x124150)(&list.attackers);
    reinterpret_cast<Cleanup>(base+0x124150)(&list.defenders);
    out.complete=complete;
    return complete;
}

static bool declarewar_participants_apply(void* action,const DeclareWarParticipantSelection& selection,
    const char* actor,const char* recipient,DeclareWarParticipantsResult& out) {
    if (!bridge::declarewar_selection::validate_participant_selection(selection.call_allies,
            selection.promise_land_to,selection.co_belligerents,actor,recipient).ok()
        || !declarewar_participants_enumerate(action,out)) return false;
    const bridge::CountryTagList* lists[]={&selection.call_allies,&selection.promise_land_to,&selection.co_belligerents};
    const unsigned offsets[]={0x50,0x68,0x80};
    for (unsigned list=0;list<3;++list) for (unsigned i=0;i<lists[list]->count;++i) {
        uint64_t handle=0;
        if (!alliance_query_country(lists[list]->tags[i],handle)) return false;
        bool found=false;
        for (unsigned row=0;row<out.count;++row) {
            const auto& candidate=out.items[row];
            if (candidate.country==handle && candidate.attacker==(list!=2) && !candidate.automatic)
                found=true;
        }
        if (!found) return false;
        auto* vector=reinterpret_cast<DeclareWarParticipantVector*>(static_cast<unsigned char*>(action)+offsets[list]);
        reinterpret_cast<void (*)(void*,uintptr_t,const uint64_t*)>(base+0xdfde0)(vector,vector->end,&handle);
    }
    // 503ea0 starts its defender traversal from recipient plus action+80.
    // Refresh after selecting co-belligerents so their allies are included.
    if (selection.co_belligerents.count) {
        out=DeclareWarParticipantsResult{};
        if (!declarewar_participants_enumerate(action,out)) return false;
    }
    for (unsigned i=0;i<out.count;++i) {
        auto& item=out.items[i];
        item.selected=declarewar_participant_selected(item.attacker?selection.call_allies:selection.co_belligerents,item.country);
        item.promise=declarewar_participant_selected(selection.promise_land_to,item.country);
    }
    out.selection_applied=true;
    return true;
}

// ee0260 checks alliance treaties across the prospective sides before asking
// the Call score method. The treaty records are the same 16-byte membership
// records traversed by that native UI function.
static bool declarewar_participant_allied(uint64_t from,uint64_t to,bool& allied) {
    uintptr_t country=0,relations=0,owner=0,begin=0;
    uint64_t actual=0; int32_t count=0;
    const unsigned slot=static_cast<unsigned>((to>>32)&0xffff);
    allied=false;
    if (!declarewar_participant_country(from,country) || !read(country+0x1510,relations)
        || !read(relations+slot*0x48,owner) || !read(relations+slot*0x48+0x10,actual)
        || actual!=to || !read(owner+0x128,begin) || !read(owner+0x134,count)
        || count<0 || count>4096 || (count && !begin)) return false;
    for (int32_t i=0;i<count;++i) {
        int32_t member=-1;
        if (!read(begin+static_cast<uintptr_t>(i)*16,member)) return false;
        if (member==static_cast<int32_t>(slot)) allied=true;
    }
    return true;
}

static bool declarewar_participant_emit_score(void* action,DeclareWarParticipant& item,
    const DeclareWarParticipantSelection& selection,const char* id,const char* actor_tag,
    const char* recipient_tag,int32_t date,unsigned index,bool emit,bool opposing_willing) {
    DeclareWarQueryHeader header{};
    if (!declarewar_query_header(action,header)) return false;
    uintptr_t country=0,owned_table=0,goal_getter=0,metadata_getter=0;
    if (!declarewar_participant_country(item.country,country)
        || !read(header.owned,owned_table) || !read(owned_table+0x58,goal_getter)
        || !read(owned_table+0x108,metadata_getter)) return false;
    using Get=uintptr_t (*)(void*);
    const uintptr_t goal=reinterpret_cast<Get>(goal_getter)(reinterpret_cast<void*>(header.owned));
    const uintptr_t metadata=reinterpret_cast<Get>(metadata_getter)(reinterpret_cast<void*>(header.owned));
    unsigned char promise_disabled=1,cb_call_flag=1;
    if (metadata && (!read(metadata+0x165,promise_disabled) || !read(metadata+0x167,cb_call_flag))) return false;
    item.promise_available=item.attacker && !item.automatic && metadata && !promise_disabled
        && reinterpret_cast<bool (*)()>(base+0x974f80)()
        && reinterpret_cast<bool (*)(void*)>(base+0x1f74a0)(reinterpret_cast<void*>(metadata));
    if (item.promise && !item.promise_available) return false;
    bool no_union_option=true; uintptr_t options=0; int32_t option_count=0;
    if (!goal || !read(goal+0x1d8,options) || !read(goal+0x1e4,option_count)
        || option_count<0 || option_count>4096 || (option_count && !options)) return false;
    for (int32_t i=0;i<option_count;++i) {
        int32_t kind=0; uintptr_t condition=0;
        if (!read(options+static_cast<uintptr_t>(i)*16,kind)
            || !read(options+static_cast<uintptr_t>(i)*16+8,condition)) return false;
        if (kind==26 && !condition) no_union_option=false;
    }
    uint64_t opponents[17]{}; unsigned opponent_count=1;
    opponents[0]=item.attacker?header.recipient:header.actor;
    const auto& opposing_selection=item.attacker?selection.co_belligerents:selection.call_allies;
    for (unsigned i=0;i<opposing_selection.count;++i)
        if (!alliance_query_country(opposing_selection.tags[i],opponents[opponent_count++])) return false;

    // ee1440 is the non-UI legality path, also used for human-controlled rows.
    alignas(8) unsigned char row[0x80]{};
    memcpy(row+0x60,&item.country,8); memcpy(row+0x68,&item.join_reason,4);
    memcpy(row+0x6c,&item.related,8); row[0x74]=item.automatic; row[0x78]=item.attacker;
    NativeShortString diagnostic{}; diagnostic.capacity=15;
    item.legal=reinterpret_cast<bool (*)(void*,void*,void*)>(base+0xee1440)(row,action,&diagnostic);
    bool context=true;
    uint64_t friends[17]{}; unsigned friend_count=1;
    friends[0]=item.attacker?header.actor:header.recipient;
    const auto& friendly_selection=item.attacker?selection.call_allies:selection.co_belligerents;
    for (unsigned i=0;i<friendly_selection.count;++i)
        context=alliance_query_country(friendly_selection.tags[i],friends[friend_count++]) && context;
    const uintptr_t subject_type=reinterpret_cast<uintptr_t (*)(void*)>(base+0x3d7a20)(reinterpret_cast<void*>(country));
    unsigned char special_alliance=0;
    if (subject_type) context=read(subject_type+0x121,special_alliance) && context;
    for (unsigned enemy=0;enemy<opponent_count;++enemy) {
        bool allied=false;
        context=declarewar_participant_allied(item.country,opponents[enemy],allied) && context;
        if (!allied) continue;
        if (!special_alliance) item.legal=false;
        else for (unsigned friendly=0;friendly<friend_count;++friendly) {
            bool common_ally=false;
            context=declarewar_participant_allied(friends[friendly],opponents[enemy],common_ally) && context;
            if (!common_ally) item.legal=false;
        }
    }

    alignas(8) unsigned char call[0x70]{};
    const uintptr_t call_table=base+0x1c800b0;
    const uint32_t discriminator=0x165; const int32_t envoy=-1; const uint16_t mode=1;
    memcpy(call,&call_table,8); memcpy(call+8,&discriminator,4);
    memcpy(call+0x10,&item.related,8); memcpy(call+0x18,&item.related,8);
    memcpy(call+0x20,&item.country,8); memcpy(call+0x28,&date,4); memcpy(call+0x2c,&date,4);
    memcpy(call+0x30,&envoy,4); memcpy(call+0x38,&mode,2); memcpy(call+0x40,opponents,8);
    call[0x48]=item.attacker; call[0x49]=1; memcpy(call+0x4c,&item.join_reason,4);
    call[0x50]=1; call[0x51]=!declarewar_participant_selected(selection.co_belligerents,item.country);
    call[0x52]=no_union_option; call[0x53]=!item.promise || !item.promise_available;
    call[0x55]=cb_call_flag;
    // Borrowed immutable local range: 542b30 never takes ownership or mutates
    // the prospective Call object. It is never wrapped, queued or destroyed.
    DeclareWarParticipantVector opposing_vector{reinterpret_cast<uintptr_t>(opponents),
        reinterpret_cast<uintptr_t>(opponents+opponent_count),reinterpret_cast<uintptr_t>(opponents+opponent_count)};
    memcpy(call+0x58,&opposing_vector,sizeof(opposing_vector));
    unsigned char call_before[sizeof(call)]{}; memcpy(call_before,call,sizeof(call));
    DeclareWarParticipantVector reasons{};
    item.score=reinterpret_cast<int32_t (*)(void*,void*,unsigned char)>(base+0x542b30)(call,&reasons,1);
    item.score_available=memcmp(call,call_before,sizeof(call))==0;
    bool shape=reasons.end>=reasons.begin && reasons.capacity>=reasons.end
        && (reasons.end-reasons.begin)%48==0 && (reasons.capacity-reasons.begin)%48==0
        && (reasons.end-reasons.begin)/48<=4096;
    const unsigned reason_count=shape?static_cast<unsigned>((reasons.end-reasons.begin)/48):0;
    item.reasons_complete=shape && reason_count<=32;
    char reason_json[43000]{}; size_t used=0; int64_t sum=0;
    for (unsigned i=0;shape && i<reason_count && i<32;++i) {
        unsigned char raw[48]{}; int32_t value=0;
        if (!read(reasons.begin+i*48,raw)) { item.reasons_complete=false; break; }
        memcpy(&value,raw,4); sum+=value;
        NativeShortString text{}; memcpy(&text,raw+8,sizeof(text));
        char hex[1025]{}; bool readable=false,truncated=false;
        declarewar_query_hex(text,hex,readable,truncated);
        item.reasons_complete=item.reasons_complete && readable && !truncated;
        const int n=snprintf(reason_json+used,sizeof(reason_json)-used,
            "%s{\"index\":%u,\"value\":%d,\"text_hex\":\"%s\",\"readable\":%s,\"truncated\":%s}",
            i?",":"",i,value,hex,readable?"true":"false",truncated?"true":"false");
        if (n<0 || static_cast<size_t>(n)>=sizeof(reason_json)-used) { item.reasons_complete=false; break; }
        used+=static_cast<size_t>(n);
    }
    // ee0260 bases the checkbox on the sum of original factor rows. Keep the
    // score method's return independently, including its forced-accept cases.
    item.would_call=item.legal && !opposing_willing && sum>0;
    char diagnostic_hex[1025]{}; bool readable=false,truncated=false;
    declarewar_query_hex(diagnostic,diagnostic_hex,readable,truncated);
    reinterpret_cast<void (*)(void*)>(base+0x95660)(&diagnostic);
    reinterpret_cast<void (*)(void*)>(base+0x418420)(&reasons);
    item.context_complete=context && item.score_available && shape && readable && !truncated;
    if (emit) {
        char country_tag[4]{},related_tag[4]{};
        if (!declarewar_participant_tag(item.country,country_tag)
            || !declarewar_participant_tag(item.related,related_tag)) return false;
        char message[46000];
        snprintf(message,sizeof(message),
            "{\"event\":\"native_declare_war_participant\",\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"date_raw\":%d,\"index\":%u,\"side\":\"%s\",\"country\":\"%.3s\",\"related_country\":\"%.3s\",\"join_reason_raw\":%d,\"automatic\":%s,\"selected\":%s,\"promise_land\":%s,\"promise_available\":%s,\"legality_checked\":true,\"native_legality\":%s,\"diagnostic_hex\":\"%s\",\"diagnostic_readable\":%s,\"diagnostic_truncated\":%s,\"score_available\":%s,\"native_total_raw\":%d,\"acceptance_threshold_raw\":1,\"reason_count\":%u,\"reasons\":[%s],\"reasons_complete\":%s,\"context_complete\":%s}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
            id,actor_tag,recipient_tag,date,index,item.attacker?"attacker":"defender",country_tag,related_tag,
            item.join_reason,item.automatic?"true":"false",item.selected?"true":"false",item.promise?"true":"false",
            item.promise_available?"true":"false",item.legal?"true":"false",diagnostic_hex,
            readable?"true":"false",truncated?"true":"false",item.score_available?"true":"false",item.score,
            reason_count,reason_json,item.reasons_complete?"true":"false",item.context_complete?"true":"false");
        line(message);
    }
    return item.context_complete;
}

static bool declarewar_participants_query(void* action,const DeclareWarParticipantSelection& selection,
    DeclareWarParticipantsResult& out,const char* id,const char* actor,const char* recipient,int32_t date,bool emit) {
    DeclareWarQueryHeader before{},after{};
    if (!declarewar_query_header(action,before) || !out.selection_applied) return false;
    out.selection_allowed=out.complete;
    for (unsigned side=0;side<2;++side) for (unsigned i=0;i<out.count;++i) {
        auto& item=out.items[i];
        if (item.attacker!=(side==1)) continue; // defender willingness first
        bool opposing_willing=false;
        if (item.attacker) for (unsigned enemy=0;enemy<out.count;++enemy) {
            const auto& opposing=out.items[enemy];
            if (!opposing.attacker && opposing.country==item.country
                && (opposing.automatic || opposing.would_call)) opposing_willing=true;
        }
        const bool result=declarewar_participant_emit_score(action,item,selection,id,actor,recipient,date,i,emit,opposing_willing);
        if (item.selected && (!result || item.automatic || (item.attacker && !item.would_call))) out.selection_allowed=false;
    }
    out.action_unchanged=declarewar_query_header(action,after) && declarewar_query_same_header(before,after);
    return out.action_unchanged;
}
