// Bounded, no-UI force-side reconstruction for a DeclareWar action.
//
// ee44c0 seeds the actor and recipient into the two native side arrays and
// then appends automatic rows plus rows that survive the prospective-call
// gates.  The attacker branch of ee0260 consults dialog UI state, while the
// defender branch (row+0x78 == 0) takes the action-only path.  This module
// never creates a UI object: it uses the closed defender call and keeps the
// attacker side on the participant query's no-UI proof.

#include <cstring>

struct DeclareWarForceSides {
    uint64_t attackers[128]{};
    uint64_t defenders[128]{};
    unsigned attacker_count=0;
    unsigned defender_count=0;
    bool attackers_complete=false;
    bool defenders_complete=false;
};

enum class DeclareWarForceAppend : unsigned char {
    added,
    duplicate,
    full
};

static DeclareWarForceAppend declarewar_force_append(uint64_t* values,
    unsigned& count,uint64_t handle) noexcept {
    if (!handle || count>=128u) return DeclareWarForceAppend::full;
    for (unsigned i=0;i<count;++i) {
        if (values[i]==handle) return DeclareWarForceAppend::duplicate;
    }
    values[count++]=handle;
    return DeclareWarForceAppend::added;
}

static bool declarewar_force_handle(uint64_t handle) {
    char tag[4]{};
    return handle!=0 && declarewar_participant_tag(handle,tag);
}

static bool declarewar_force_related(uint64_t handle) {
    // participant enumeration validates this same +0x6c relation handle.
    return declarewar_force_handle(handle);
}

static bool declarewar_force_relation(uint64_t from,uint64_t to,uintptr_t& relation,uintptr_t& owner) {
    uintptr_t country=0,relations=0; uint64_t actual=0;
    const unsigned slot=static_cast<unsigned>((to>>32)&0xffff);
    if (!declarewar_participant_country(from,country) || !read(country+0x1510,relations)) return false;
    relation=relations+slot*0x48;
    return read(relation,owner) && read(relation+0x10,actual) && actual==to;
}

// The remaining attacker checkbox gates immediately after ee0260 in ee44c0.
static bool declarewar_force_attacker_gate(const DeclareWarParticipant& item,
    uint64_t actor,uint64_t recipient,bool& known) {
    known=item.context_complete;
    if (!item.selected || !item.would_call) return false;
    uintptr_t relation=0,owner=0,records=0,actor_relation=0,actor_owner=0;
    int32_t count=0; int16_t flag=0; unsigned char bits=0;
    if (!declarewar_force_relation(item.country,recipient,relation,owner)
        || !read(owner+0x50,records) || !read(owner+0x5c,count)
        || count<0 || count>4096 || (count && !records)
        || !read(relation+0x1c,flag) || !read(relation+0x45,bits)
        || !declarewar_force_relation(actor,recipient,actor_relation,actor_owner)) {
        known=false; return false;
    }
    const int32_t target=static_cast<int32_t>((recipient>>32)&0xffff);
    for (int32_t i=0;i<count;++i) {
        int32_t member=-1; uintptr_t treaty=0;
        if (!read(records+static_cast<uintptr_t>(i)*16,member)) { known=false; return false; }
        if (member!=target) continue;
        if (!read(records+static_cast<uintptr_t>(i)*16+8,treaty)) { known=false; return false; }
        if (treaty) return false;
        break;
    }
    using RelationPredicate=unsigned char (*)(void*);
    const auto special=reinterpret_cast<RelationPredicate>(base+0xa697a0);
    return !flag && !(bits&1)
        && (!special(reinterpret_cast<void*>(relation)) || special(reinterpret_cast<void*>(actor_relation)));
}

static bool declarewar_force_defender_native_call(void* action,
    const DeclareWarParticipant& item) {
    // ee0260's row+0x78 == 0 branch is the action-only defender path.  The
    // fourth argument is an optional diagnostic string; nullptr avoids the
    // attacker/UI diagnostic path.  The native result is a byte, not a
    // pointer-sized truth value.
    alignas(8) unsigned char row[0x80]{};
    memcpy(row+0x60,&item.country,8);
    memcpy(row+0x68,&item.join_reason,4);
    memcpy(row+0x6c,&item.related,8);
    row[0x74]=item.automatic?1u:0u;
    row[0x78]=0; // defender mode; nonzero is the UI-backed attacker path
    using NativeCall=unsigned char (*)(void*,void*,unsigned char,void*);
    const auto call=reinterpret_cast<NativeCall>(base+0xee0260u);
    return call(row,action,static_cast<unsigned char>(1),nullptr)!=0;
}

static bool declarewar_force_visibility(uintptr_t actor_country,uint64_t country) {
    return reinterpret_cast<unsigned char (*)(void*,uint64_t)>(base+0x378ff0)(
        reinterpret_cast<void*>(actor_country),country)!=0;
}

// Additional non-automatic defender membership branch in ee44c0. The
// native final ee0260 path is tested separately, so only false-call rows
// need this branch. Unknown imperial/UI modes retain an incomplete scope.
static bool declarewar_force_defender_extra(void* action,const DeclareWarParticipant& item,
    uint64_t actor,uint64_t recipient,uintptr_t game,bool& known) {
    uintptr_t country=0,relation=0,owner=0,actor_relation=0,actor_owner=0;
    uint64_t overlord=0; unsigned char relation_bits=0;
    if (!declarewar_participant_country(item.country,country)
        || !declarewar_force_relation(item.country,actor,relation,owner)
        || !declarewar_force_relation(actor,item.country,actor_relation,actor_owner)
        || !read(actor_relation+0x45,relation_bits) || !read(country+0x18f0,overlord)) {
        known=false; return false;
    }
    uint64_t related=0;
    if (!read(relation+0x10,related)) { known=false; return false; }
    using RelationPredicate=unsigned char (*)(void*,uint64_t);
    if (reinterpret_cast<RelationPredicate>(base+0x99fc0)(reinterpret_cast<void*>(owner),related)
        || reinterpret_cast<RelationPredicate>(base+0x2c5af0)(reinterpret_cast<void*>(owner),related)) return false;
    if (!declarewar_force_relation(item.country,recipient,relation,owner)
        || !read(relation+0x10,related)) { known=false; return false; }
    if (reinterpret_cast<RelationPredicate>(base+0x99fc0)(reinterpret_cast<void*>(owner),related)) return false;
    if (relation_bits&1) return false;
    bool special_subject=false;
    if (overlord==item.related) {
        const uintptr_t type=reinterpret_cast<uintptr_t (*)(void*)>(base+0x3d7a20)(reinterpret_cast<void*>(country));
        unsigned char flag121=0,flag122=0;
        if (!type || !read(type+0x121,flag121) || !read(type+0x122,flag122)) { known=false; return false; }
        special_subject=!flag121 && flag122;
    }
    uintptr_t player_begin=0,player_end=0; int32_t human=0;
    const unsigned slot=static_cast<unsigned>((item.country>>32)&0xffff);
    if (!read(game+0x1d48,player_begin) || !read(game+0x1d50,player_end)
        || player_end<player_begin || (player_end-player_begin)%4
        || (player_end-player_begin)/4>4096
        || (player_end!=player_begin && (slot>=(player_end-player_begin)/4
            || !read(player_begin+slot*4,human)))) { known=false; return false; }
    // Normal AI, no accepted Call: ee44c0 jumps directly to the final call
    // test and therefore excludes this country. Rejection is complete data.
    if (player_end!=player_begin && !human && !special_subject) return false;
    // The remaining UI branch may show state 3 while including a country.
    // Evaluate its imperial-information flag from the same action context.
    uint64_t imperial=0;
    if (!read(game+0x15e0,imperial)) { known=false; return false; }
    if (imperial==item.country) { known=false; return false; }
    return !reinterpret_cast<unsigned char (*)(void*,uint64_t)>(base+0x4e4d40)(action,item.country);
}

static bool declarewar_force_sides(void* action,
    const DeclareWarParticipantsResult& participants,
    DeclareWarForceSides& output) {
    output=DeclareWarForceSides{};
    if (!action || participants.count>64u) return false;

    const uintptr_t action_address=reinterpret_cast<uintptr_t>(action);
    uint64_t actor=0,recipient=0;
    if (!read(action_address+0x10u,actor) || !read(action_address+0x20u,recipient)
        || !declarewar_force_handle(actor) || !declarewar_force_handle(recipient)
        || actor==recipient) return false;

    bool attacker_scope=participants.called && participants.complete;
    bool defender_scope=participants.called && participants.complete;
    uintptr_t game=0,actor_country=0,mode_settings=0;
    unsigned char mode=0,observer_mode=0,alternate=0;
    int32_t setting28=0,setting5c=0;
    if (!read(base+0x233fe58,game) || !declarewar_participant_country(actor,actor_country)
        || !read(game+0x1e66,mode) || !read(game+0x1e6f,alternate)
        || !read(game+0x1e67,observer_mode) || !read(game+0x2150,mode_settings)
        || !read(mode_settings+0x28,setting28) || !read(mode_settings+0x5c,setting5c)) return false;
    const unsigned char current_mode=mode==7 && alternate?alternate:observer_mode;
    const bool visibility_mode=current_mode && (setting28 || setting5c);
    bool visibility_gate=false,include_recipient=true;
    if (visibility_mode && !declarewar_force_visibility(actor_country,recipient)) {
        visibility_gate=true;
        include_recipient=declarewar_force_visibility(actor_country,recipient);
        if (!include_recipient) defender_scope=false;
    }

    const DeclareWarForceAppend actor_result=declarewar_force_append(
        output.attackers,output.attacker_count,actor);
    const DeclareWarForceAppend recipient_result=include_recipient?declarewar_force_append(
        output.defenders,output.defender_count,recipient):DeclareWarForceAppend::added;
    if (actor_result!=DeclareWarForceAppend::added
        || recipient_result!=DeclareWarForceAppend::added) return false;

    for (unsigned index=0;index<participants.count;++index) {
        const DeclareWarParticipant& item=participants.items[index];
        const bool attacker=item.attacker;
        bool valid=declarewar_force_handle(item.country)
            && declarewar_force_related(item.related);
        if (!valid) {
            if (attacker) attacker_scope=false;
            else defender_scope=false;
            continue;
        }
        // 503ea0 omits these two seeds.  Treating them as participant rows
        // would make a malformed snapshot look like a third side member.
        if (item.country==actor || item.country==recipient) {
            if (attacker) attacker_scope=false;
            else defender_scope=false;
            continue;
        }

        bool include=false;
        if (attacker) {
            // ee44c0 appends automatic allies directly.  For a manual ally,
            // action+0x50 selection is retained only when the native query's
            // relation/legality/willingness proof is complete.
            bool known=true;
            include=item.automatic || declarewar_force_attacker_gate(item,actor,recipient,known);
            if (item.selected && !item.automatic && !known) attacker_scope=false;
        } else {
            // ee44c0's final defender test is the action-only ee0260 path.
            // Keep its native result, then apply the already observed
            // participant relation gate.  A non-complete participant query
            // cannot prove the surrounding ee44c0 mode gates.
            // ee0260's early automatic-row branch is deliberately not a
            // membership query (its byte return is false); ee44c0 already
            // appends that row directly.  Preserve that direct path.
            bool known=true;
            include=item.automatic || declarewar_force_defender_native_call(action,item);
            if (!include) include=declarewar_force_defender_extra(action,item,actor,recipient,game,known);
            if (!known) defender_scope=false;
            if (include && visibility_gate && !declarewar_force_visibility(actor_country,item.country)) {
                include=false; defender_scope=false;
            }
        }
        if (!include) continue;

        DeclareWarForceAppend result=attacker
            ? declarewar_force_append(output.attackers,output.attacker_count,item.country)
            : declarewar_force_append(output.defenders,output.defender_count,item.country);
        if (result==DeclareWarForceAppend::full) {
            if (attacker) attacker_scope=false;
            else defender_scope=false;
        }
    }
    for (unsigned a=0;a<output.attacker_count;++a) for (unsigned d=0;d<output.defender_count;++d)
        if (output.attackers[a]==output.defenders[d]) return false;
    output.attackers_complete=attacker_scope;
    output.defenders_complete=defender_scope;
    // A true return means both action seeds and every readable candidate row
    // were processed.  The per-side flags carry the stronger native-scope
    // proof; a side can therefore be incomplete without losing its bounded
    // snapshot.
    return true;
}
