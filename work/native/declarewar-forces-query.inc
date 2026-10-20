// Native DeclareWarDialog force counters (ee5430). Unit proof: R64's
// same-date save baseline matched 91 regiments and four reserve pools.
#include "declarewar-force-sides.inc"

struct DeclareWarForceArray {
    uintptr_t vtable=0;
    uint64_t* data=nullptr;
    int32_t capacity=0,count=0;
};
static_assert(sizeof(DeclareWarForceArray)==24,"native force CArray ABI");
struct DeclareWarForceAmounts {
    int32_t infantry=0,cavalry=0,artillery=0,deployed=0,reserve=0;
    bool deployed_complete=false,reserve_complete=false,scope_complete=false;
};
struct DeclareWarForcesResult {
    bool called=false,action_unchanged=false,complete=false;
    DeclareWarForceSides sides{};
    DeclareWarForceAmounts attackers{},defenders{};
};

static bool declarewar_force_contains(const DeclareWarForceSides& sides,uint64_t handle) {
    for (unsigned i=0;i<sides.attacker_count;++i) if (sides.attackers[i]==handle) return true;
    for (unsigned i=0;i<sides.defender_count;++i) if (sides.defenders[i]==handle) return true;
    return false;
}

// ee5430 recursively includes certain subject types which are absent from
// the dialog's explicit rows. Expand that exact relation before counting so
// deployed units and reserve manpower share one unique country scope.
static bool declarewar_force_expand(DeclareWarForceSides& sides,bool attacker) {
    auto* countries=attacker?sides.attackers:sides.defenders;
    auto& count=attacker?sides.attacker_count:sides.defender_count;
    for (unsigned index=0;index<count;++index) {
        uintptr_t country=0,begin=0,end=0;
        if (!declarewar_participant_country(countries[index],country)
            || !read(country+0x1a18,begin) || !read(country+0x1a20,end)
            || end<begin || (end-begin)%8 || (end-begin)/8>4096) return false;
        for (uintptr_t p=begin;p<end;p+=8) {
            uint64_t handle=0,overlord=0,actual=0; uintptr_t child=0,relations=0,owner=0,records=0;
            unsigned char subject=0; int32_t record_count=0;
            if (!read(p,handle)) return false;
            if (declarewar_force_contains(sides,handle)) continue;
            if (!declarewar_participant_country(handle,child) || !read(child+0x18f7,subject)) return false;
            if (!subject) continue;
            if (!read(child+0x18f0,overlord) || !read(child+0x1510,relations)) return false;
            const unsigned slot=static_cast<unsigned>((overlord>>32)&0xffff);
            if (!read(relations+slot*0x48,owner) || !read(relations+slot*0x48+0x10,actual)
                || actual!=overlord || !read(owner+0x128,records) || !read(owner+0x134,record_count)
                || record_count<0 || record_count>4096 || (record_count && !records)) return false;
            for (int32_t row=0;row<record_count;++row) {
                int32_t member=-1; uintptr_t treaty=0,type=0; unsigned char include=0;
                const uintptr_t record=records+static_cast<uintptr_t>(row)*16;
                if (!read(record,member)) return false;
                if (member!=static_cast<int32_t>(slot)) continue;
                if (!read(record+8,treaty)) return false;
                if (treaty) {
                    if (!read(treaty+0x40,type)) return false;
                    if (type && !read(type+0x121,include)) return false;
                }
                if (include) {
                    char tag[4]{};
                    if (count>=128 || !declarewar_participant_tag(handle,tag)) return false;
                    countries[count++]=handle;
                }
                break;
            }
        }
    }
    return true;
}

static bool declarewar_force_amount(int64_t raw,int32_t& amount) {
    if (raw<0 || raw>INT32_MAX) return false;
    amount=static_cast<int32_t>(raw); return true;
}

static void declarewar_force_sum(DeclareWarForceSides& sides,bool attacker,
    DeclareWarForceAmounts& out) {
    auto* countries=attacker?sides.attackers:sides.defenders;
    const unsigned count=attacker?sides.attacker_count:sides.defender_count;
    const bool scope=attacker?sides.attackers_complete:sides.defenders_complete;
    DeclareWarForceArray own{0,countries,static_cast<int32_t>(count),static_cast<int32_t>(count)};
    DeclareWarForceArray other{0,attacker?sides.defenders:sides.attackers,
        static_cast<int32_t>(attacker?sides.defender_count:sides.attacker_count),
        static_cast<int32_t>(attacker?sides.defender_count:sides.attacker_count)};
    bool deployed=true,reserve=true;
    int64_t sums[3]{},reserve_sum=0;
    for (unsigned i=0;i<count;++i) {
        uintptr_t country=0; int32_t manpower=0; int64_t queued=0;
        bool direct=declarewar_participant_country(countries[i],country)
            && read(country+0xdb8,manpower) && manpower>=0;
        for (unsigned kind=0;direct && kind<3;++kind) {
            uint16_t units=0; uintptr_t definition=0; int32_t size=0;
            direct=read(country+0x10b8+kind*2,units);
            if (direct && units) {
                direct=read(country+0xd48+kind*8,definition) && read(definition+0x54,size) && size>=0;
                queued+=static_cast<int64_t>(units)*size;
            }
        }
        if (!direct) { deployed=false; reserve=false; continue; }
        int32_t infantry=0,cavalry=0,artillery=0,fourth=0;
        using Count=void (*)(const uint64_t*,int32_t*,int32_t*,int32_t*,int32_t*,const void*,const void*);
        reinterpret_cast<Count>(base+0xee5430)(&countries[i],&infantry,&cavalry,&artillery,&fourth,&own,&other);
        if (infantry<0 || cavalry<0 || artillery<0) deployed=false;
        else { sums[0]+=infantry; sums[1]+=cavalry; sums[2]+=artillery; }
        // The fourth UI counter contains reserve plus additional unit terms.
        // Only the verified reserve pool is exposed as reserve manpower.
        if (static_cast<int64_t>(fourth)!=static_cast<int64_t>(manpower)+queued) {
            deployed=false; reserve=false;
        }
        reserve_sum+=manpower;
    }
    deployed=declarewar_force_amount(sums[0],out.infantry) && deployed;
    deployed=declarewar_force_amount(sums[1],out.cavalry) && deployed;
    deployed=declarewar_force_amount(sums[2],out.artillery) && deployed;
    deployed=declarewar_force_amount(sums[0]+sums[1]+sums[2],out.deployed) && deployed;
    reserve=declarewar_force_amount(reserve_sum,out.reserve) && reserve;
    if (!deployed) out.infantry=out.cavalry=out.artillery=out.deployed=0;
    out.deployed_complete=deployed && scope;
    out.reserve_complete=reserve && scope;
    out.scope_complete=scope;
}

static bool declarewar_forces_query_run(void* action,const DeclareWarParticipantsResult& participants,
    DeclareWarForcesResult& out) {
    DeclareWarQueryHeader before{},after{};
    if (!declarewar_query_header(action,before)) return false;
    out.called=true;
    const bool built=declarewar_force_sides(action,participants,out.sides);
    if (!built) out.sides.attackers_complete=out.sides.defenders_complete=false;
    const bool attacker_expanded=declarewar_force_expand(out.sides,true);
    const bool defender_expanded=declarewar_force_expand(out.sides,false);
    out.sides.attackers_complete=attacker_expanded && out.sides.attackers_complete;
    out.sides.defenders_complete=defender_expanded && out.sides.defenders_complete;
    // Expansion must finish before either aggregate is computed.
    if (attacker_expanded && defender_expanded) {
        declarewar_force_sum(out.sides,true,out.attackers);
        declarewar_force_sum(out.sides,false,out.defenders);
    }
    out.action_unchanged=declarewar_query_header(action,after) && declarewar_query_same_header(before,after);
    out.complete=out.action_unchanged && out.attackers.deployed_complete
        && out.attackers.reserve_complete && out.defenders.deployed_complete && out.defenders.reserve_complete;
    return out.action_unchanged;
}

static bool declarewar_force_side_json(const uint64_t* countries,unsigned count,
    const DeclareWarForceAmounts& amounts,char* json,size_t capacity) {
    char tags[800]{}; size_t used=0;
    for (unsigned i=0;i<count;++i) {
        char tag[4]{};
        if (!declarewar_participant_tag(countries[i],tag)) return false;
        const int n=snprintf(tags+used,sizeof(tags)-used,"%s\"%.3s\"",i?",":"",tag);
        if (n<0 || static_cast<size_t>(n)>=sizeof(tags)-used) return false;
        used+=static_cast<size_t>(n);
    }
    const int n=snprintf(json,capacity,
        "{\"countries\":[%s],\"infantry_raw\":%d,\"cavalry_raw\":%d,\"artillery_raw\":%d,\"deployed_total_raw\":%d,\"reserve_manpower_raw\":%d,\"deployed_complete\":%s,\"reserve_complete\":%s,\"scope_complete\":%s}",
        tags,amounts.infantry,amounts.cavalry,amounts.artillery,amounts.deployed,amounts.reserve,
        amounts.deployed_complete?"true":"false",amounts.reserve_complete?"true":"false",amounts.scope_complete?"true":"false");
    return n>=0 && static_cast<size_t>(n)<capacity;
}

static bool declarewar_forces_query_json(const DeclareWarForcesResult& forces,char* json,size_t capacity) {
    char attackers[1500]{},defenders[1500]{};
    if (!declarewar_force_side_json(forces.sides.attackers,forces.sides.attacker_count,forces.attackers,attackers,sizeof(attackers))
        || !declarewar_force_side_json(forces.sides.defenders,forces.sides.defender_count,forces.defenders,defenders,sizeof(defenders))) return false;
    const int n=snprintf(json,capacity,
        "{\"called\":%s,\"action_unchanged\":%s,\"unit\":\"men\",\"units_verified\":true,\"complete\":%s,\"attackers\":%s,\"defenders\":%s}",
        forces.called?"true":"false",forces.action_unchanged?"true":"false",forces.complete?"true":"false",attackers,defenders);
    return n>=0 && static_cast<size_t>(n)<capacity;
}
