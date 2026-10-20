// Consequence preview on the same owned CPeaceOffer used by the query.
// 9794d0 -> 9791b0 receives RCX=offer (the cached pseudocode's zero is
// corrected by its call-site instructions). No UI object is constructed.

#include "peace-coalition-capture.inc"
#include "peace-overextension-query.inc"
#include "peace-justification-query.inc"

static constexpr size_t peace_consequence_json_capacity=400000u;

struct PeaceConsequenceText {
    bool returned=false,readable=false,truncated=false;
    char hex[32769]{};
};
struct PeaceConsequenceTotals {
    uint64_t claimant=0,payer=0;
    int32_t diplomatic_power=0,maximum_ae_raw=0;
    bool called=false,identity_verified=false,diplomatic_power_available=false;
    bool aggressive_expansion_available=false,coalition_possible=false;
    PeaceConsequenceText aggressive_expansion_text{};
    CoalitionCapture coalition{};
};

struct PeaceConsequenceProvince {
    int32_t id=0,administrative_power=0,overextension_raw=0;
    bool already_core=false,adds_overextension=false;
};
struct PeaceConsequenceTerritory {
    uint64_t country=0;
    bool called=false,complete=false,truncated=false;
    unsigned count=0;
    int32_t administrative_power=0,overextension_added_raw=0;
    PeaceConsequenceProvince provinces[512]{};
};

static bool peace_consequence_integer(int64_t raw,int32_t& out) noexcept {
    if (raw<0 || raw>INT32_MAX) return false;
    out=static_cast<int32_t>(raw); return true;
}

static bool peace_consequence_territory(void* offer,uint64_t country,
    PeaceConsequenceTerritory& out) noexcept {
    out.country=country;
    uintptr_t country_record=0;
    PeaceProvinceArrayBounds bounds{};
    if (!peace_query_country_pointer(country,country_record) || !peace_province_read_bounds(bounds)) return false;
    // The UI divides its province sum by FixedPoint(100.0), then renders a
    // fixed-point percentage. Read the same conversion rather than treating
    // the development sum itself as an OE percentage.
    int32_t denominator=0;
    using Fixed= int32_t* (*)(int32_t*,float);
    if (reinterpret_cast<Fixed>(base+0xcfb50)(&denominator,100.0f)!=&denominator
        || denominator!=100000) return false;
    DeclareWarParticipantVector provinces{};
    using Collect=void (*)(void*,uint64_t,void*);
    out.called=true;
    reinterpret_cast<Collect>(base+0x981dd0)(offer,country,&provinces);
    bool complete=provinces.end>=provinces.begin && provinces.capacity>=provinces.end
        && (provinces.end-provinces.begin)%8==0 && (provinces.capacity-provinces.begin)%8==0
        && (provinces.end-provinces.begin)/8<=4096;
    const unsigned count=complete?static_cast<unsigned>((provinces.end-provinces.begin)/8):0;
    out.truncated=count>512;
    complete=complete && !out.truncated;
    int64_t administrative=0,overextension=0;
    for (unsigned i=0;i<count && i<512;++i) {
        uintptr_t province=0,expected=0,core_begin=0,core_end=0;
        PeaceConsequenceProvince row{};
        bool readable=read(provinces.begin+i*8,province)
            && read(province+0x20,row.id) && peace_province_record_for_id(bounds,row.id,expected)
            && expected==province && read(province+0x490,core_begin) && read(province+0x498,core_end)
            && core_end>=core_begin && (core_end-core_begin)%8==0 && (core_end-core_begin)/8<=4096;
        for (uintptr_t p=core_begin;readable && p<core_end;p+=8) {
            uint64_t core=0;
            if (!read(p,core)) { readable=false; break; }
            if (((core>>32)&0xffff)==((country>>32)&0xffff)) row.already_core=true;
        }
        if (!readable) { complete=false; continue; }
        row.adds_overextension=reinterpret_cast<unsigned char (*)(void*,uint64_t)>(base+0xa25b90)(
            reinterpret_cast<void*>(province),country)!=0;
        if (row.adds_overextension) {
            int32_t development=0,modifier=0;
            // Native parameter five is an optional 8-byte pointer at stack
            // +0x28. A byte declaration leaves stale high bytes in that slot.
            using Development=int32_t* (*)(void*,int32_t*,unsigned char,unsigned char,void*);
            using Modifier=int32_t* (*)(void*,int32_t*);
            const bool values=reinterpret_cast<Development>(base+0xa0cff0)(
                    reinterpret_cast<void*>(province),&development,0,0,nullptr)==&development
                && reinterpret_cast<Modifier>(base+0x3cf290)(reinterpret_cast<void*>(country_record),&modifier)==&modifier
                && development>=0 && modifier>=0;
            if (!values || !peace_consequence_integer(
                    ((static_cast<int64_t>(development)*modifier)/1000)*1000/denominator,
                    row.overextension_raw)) complete=false;
            else overextension+=(static_cast<int64_t>(development)*modifier)/1000;
        }
        if (!row.already_core) {
            alignas(8) unsigned char action[0x38]{};
            const uintptr_t table=base+0x1c55480;
            const uint32_t discriminator=0x165,kind=0x11;
            const int32_t unknown=-1; uint64_t native_date=0;
            if (!read(base+0x233fe88,native_date)) { complete=false; continue; }
            memcpy(action,&table,8); memcpy(action+8,&discriminator,4);
            memcpy(action+0x10,&kind,4); memcpy(action+0x18,&row.id,4);
            memcpy(action+0x1c,&unknown,4); memcpy(action+0x28,&native_date,8);
            using Cost=uint64_t (*)(void*,uint64_t,void*,void*);
            const uint64_t cost=reinterpret_cast<Cost>(base+0x952540)(action,country,nullptr,nullptr);
            if (cost>INT32_MAX) complete=false;
            else { row.administrative_power=static_cast<int32_t>(cost); administrative+=row.administrative_power; }
        }
        out.provinces[out.count++]=row;
    }
    // 981dd0's vector owns only its pointer buffer, not province records.
    reinterpret_cast<void (*)(void*)>(base+0x8eac0)(&provinces);
    complete=peace_consequence_integer(administrative,out.administrative_power) && complete;
    complete=peace_consequence_integer(overextension*1000/denominator,out.overextension_added_raw) && complete;
    out.complete=complete && out.count==count;
    return out.complete;
}

static bool peace_consequence_text(NativeShortString& text,PeaceConsequenceText& out) noexcept {
    constexpr unsigned limit=16384;
    const unsigned length=static_cast<unsigned>(text.size<limit?text.size:limit);
    uintptr_t address=reinterpret_cast<uintptr_t>(text.text);
    if (text.capacity>=16) memcpy(&address,text.text,8);
    unsigned char bytes[limit]{}; SIZE_T copied=0;
    out.truncated=text.size>limit;
    out.readable=text.size<=65536 && text.capacity<=131072 && text.size<=text.capacity
        && (!length || (address && ReadProcessMemory(GetCurrentProcess(),
            reinterpret_cast<void*>(address),bytes,length,&copied) && copied==length));
    if (out.readable) for (unsigned i=0;i<length;++i) snprintf(out.hex+i*2,3,"%02x",bytes[i]);
    reinterpret_cast<void (*)(void*)>(base+0x95660)(&text);
    return out.returned && out.readable && !out.truncated;
}

static bool peace_consequence_totals(void* offer,uint64_t actor,uint64_t recipient,
    bool demand,PeaceConsequenceTotals& out) noexcept {
    const uintptr_t address=reinterpret_cast<uintptr_t>(offer);
    uintptr_t table=0; uint32_t discriminator=0; unsigned char direction=0;
    if (!read(address,table) || table!=base+0x1c578b8
        || !read(address+8,discriminator) || discriminator!=0x165
        || !read(address+0x10,out.payer) || out.payer!=peace_offer_payer(actor,recipient,demand)
        || !read(address+0x18,out.claimant) || out.claimant!=peace_offer_claimant(actor,recipient,demand)
        || !read(address+0x20,direction) || direction!=(demand?1u:0u)) return false;
    out.identity_verified=true;
    out.called=true;
    out.diplomatic_power=reinterpret_cast<int32_t (*)(void*,uint64_t)>(base+0x978840)(offer,out.claimant);
    out.diplomatic_power_available=out.diplomatic_power>=0;
    NativeShortString text{}; text.capacity=15;
    unsigned char coalition=0;
    using AggressiveExpansion=NativeShortString* (*)(void*,NativeShortString*,int32_t*,unsigned char*);
    coalition_scope_begin();
    out.aggressive_expansion_text.returned=reinterpret_cast<AggressiveExpansion>(base+0x9794d0)(
        offer,&text,&out.maximum_ae_raw,&coalition)==&text;
    out.coalition=coalition_scope_end();
    out.coalition_possible=coalition!=0;
    out.aggressive_expansion_available=peace_consequence_text(text,out.aggressive_expansion_text)
        && out.maximum_ae_raw>=0 && coalition<=1;
    return out.diplomatic_power_available && out.aggressive_expansion_available;
}

struct PeaceConsequenceQuery {
    char* json=nullptr;
    size_t used=0;
    bool output_complete=true;
    PeaceConsequenceTotals totals{};
    PeaceConsequenceTerritory territorial[3]{};
    unsigned territorial_count=0;
    PeaceOverextensionQueryResult overextension{};
    PeaceJustificationQueryResult justification{};
    PeaceConsequenceQuery() noexcept {
        json=static_cast<char*>(HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,
            peace_consequence_json_capacity));
    }
    ~PeaceConsequenceQuery() noexcept {
        if (json) HeapFree(GetProcessHeap(),0,json);
    }
    PeaceConsequenceQuery(const PeaceConsequenceQuery&)=delete;
    PeaceConsequenceQuery& operator=(const PeaceConsequenceQuery&)=delete;
    bool append(const char* format,...) noexcept {
        if (!json || !output_complete) return false;
        va_list args; va_start(args,format);
        const int length=vsnprintf(json+used,peace_consequence_json_capacity-used,
            format,args);
        va_end(args);
        if (length<0 || static_cast<size_t>(length)>=peace_consequence_json_capacity-used) {
            output_complete=false; return false;
        }
        used+=static_cast<size_t>(length); return true;
    }
};

static bool peace_consequence_query(void* offer,uint64_t actor,uint64_t recipient,
    bool demand,uint64_t beneficiary,const bridge::peace_payload::PeaceOfferPayload& payload,
    PeaceConsequenceQuery& query) noexcept {
    if (!query.json) return false;
    PeaceConsequenceTotals& t=query.totals;
    const bool totals_complete=peace_consequence_totals(offer,actor,recipient,demand,t);
    if (!t.identity_verified) return query.append("null");
    const bool overextension_complete=peace_overextension_query(payload,query.overextension);
    const bool justification_complete=peace_justification_query(offer,payload,query.justification);
    const uint64_t countries[]={t.claimant,t.payer,beneficiary};
    bool territories_complete=true;
    for (unsigned i=0;i<3;++i) {
        if (!countries[i] || (i && countries[i]==countries[0])
            || (i==2 && countries[i]==countries[1])) continue;
        PeaceConsequenceTerritory& territory=query.territorial[query.territorial_count++];
        territories_complete=peace_consequence_territory(offer,countries[i],territory)
            && territories_complete;
    }
    // 388e50 only calls the coalition sort when its candidate vector is
    // nonempty. A false native flag therefore proves an empty result even
    // when the optional capture hook was unavailable.
    bool coalition_complete=t.aggressive_expansion_available && !t.coalition_possible;
    if (t.coalition_possible) coalition_complete=coalition_installed_state()
        && t.coalition.complete && t.coalition.coalition_seen
        && t.coalition.coalition.complete;
    unsigned visible_rows=0;
    if (coalition_complete && t.coalition_possible) {
        for (unsigned i=0;i<t.coalition.coalition.count;++i) {
            const CoalitionRow& row=t.coalition.coalition.rows[i];
            uintptr_t record=0; int32_t province_count=0; unsigned char kind=0;
            if (!peace_query_country_pointer(row.country,record)
                || !read(record+0x1344,province_count) || !read(record+0x26,kind)) {
                coalition_complete=false; break;
            }
            if (province_count!=0 || kind==7) ++visible_rows;
        }
    }
    char claimant[4]{};
    if (!peace_province_tag(t.claimant,claimant)) return false;
    query.append("{\"called\":%s,\"offer_identity_verified\":true,\"complete\":%s,"
        "\"diplomatic_power\":{\"country\":\"%s\",\"available\":%s,\"value\":%d,\"unit\":\"power_points\"},"
        "\"aggressive_expansion\":{\"available\":%s,\"maximum_raw\":%d,\"scale\":1000,"
        "\"native_text_hex\":\"%s\",\"text_readable\":%s,\"text_truncated\":%s,\"coalition_possible\":%s},"
        "\"coalition\":{\"available\":%s,\"complete\":%s,\"native_count\":%u,"
        "\"current_value_semantics_verified\":true,\"countries\":[",
        t.called?"true":"false",totals_complete && territories_complete
            && coalition_complete && overextension_complete && justification_complete?"true":"false",
        claimant,t.diplomatic_power_available?"true":"false",t.diplomatic_power,
        t.aggressive_expansion_available?"true":"false",t.maximum_ae_raw,
        t.aggressive_expansion_text.hex,t.aggressive_expansion_text.readable?"true":"false",
        t.aggressive_expansion_text.truncated?"true":"false",t.coalition_possible?"true":"false",
        coalition_complete?"true":"false",coalition_complete?"true":"false",
        t.coalition_possible?t.coalition.coalition.native_count:0u);
    unsigned written=0;
    if (coalition_complete && visible_rows) for (unsigned i=0;i<t.coalition.coalition.count;++i) {
        const CoalitionRow& row=t.coalition.coalition.rows[i];
        uintptr_t record=0; int32_t province_count=0; unsigned char kind=0;
        char tag[4]{};
        if (!peace_query_country_pointer(row.country,record)
            || !read(record+0x1344,province_count) || !read(record+0x26,kind)
            || !peace_province_tag(row.country,tag)) return false;
        if (province_count==0 && kind!=7) continue;
        query.append("%s{\"tag\":\"%s\",\"aggressive_expansion_delta\":%d,\"current_value\":%d}",
            written++?",":"",tag,row.delta,row.current);
    }
    query.append("]},\"territorial\":[");
    for (unsigned i=0;i<query.territorial_count;++i) {
        const PeaceConsequenceTerritory& territory=query.territorial[i];
        char tag[4]{};
        if (!peace_province_tag(territory.country,tag)) return false;
        query.append("%s{\"country\":\"%s\",\"called\":%s,\"complete\":%s,\"truncated\":%s,"
            "\"administrative_power\":%d,\"overextension_added_raw\":%d,\"scale\":1000,\"provinces\":[",
            i?",":"",tag,territory.called?"true":"false",territory.complete?"true":"false",
            territory.truncated?"true":"false",territory.administrative_power,territory.overextension_added_raw);
        for (unsigned j=0;j<territory.count;++j) {
            const PeaceConsequenceProvince& p=territory.provinces[j];
            query.append("%s{\"province_id\":%d,\"administrative_power\":%d,\"already_core\":%s,"
                "\"adds_overextension\":%s,\"overextension_added_raw\":%d}",
                j?",":"",p.id,p.administrative_power,p.already_core?"true":"false",
                p.adds_overextension?"true":"false",p.overextension_raw);
        }
        query.append("]}");
    }
    if (!query.append("],\"overextension\":")) return false;
    if (!peace_overextension_query_json(query.overextension,query.json+query.used,
            peace_consequence_json_capacity-query.used)) return false;
    query.used+=strlen(query.json+query.used);
    if (!query.append(",\"justification\":")) return false;
    if (!peace_justification_query_json(query.justification,query.json+query.used,
            peace_consequence_json_capacity-query.used)) return false;
    query.used+=strlen(query.json+query.used);
    return query.append("}") && query.output_complete;
}
