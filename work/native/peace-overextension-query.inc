// Read-only overextension preview for the selected territorial payload.
//
// This module consumes the process-independent PeaceOfferPayload and resolves
// only the native province/country records needed for the preview.  It must be
// included after peace-payload.h, peace-context-query.inc and the province
// bounds helpers.  It never calls a country/cache writer.

#include <algorithm>
#include <cstdarg>

static constexpr unsigned peace_overextension_max_countries=64u;
static constexpr unsigned peace_overextension_max_provinces=512u;
static constexpr int32_t peace_overextension_max_owned_count=16384;
static constexpr uint16_t peace_overextension_invalid_country_index=0xffffu;

struct PeaceOverextensionCountry {
    uint64_t country=0;
    char tag[4]{};
    bool complete=false;
    int32_t current_raw=0;
    int32_t current_recomputed_raw=0;
    bool cache_matches_recomputed=false;
    int32_t gained_raw=0;
    int32_t lost_raw=0;
    int32_t delta_raw=0;
    int32_t projected_raw=0;

    // Native working values are kept out of JSON.  They avoid recomputing
    // the current country total when the selected cede rows are applied.
    int64_t current_development=0;
    int64_t gained_development=0;
    int64_t lost_development=0;
    int32_t modifier_raw=0;
};

struct PeaceOverextensionImpact {
    int32_t province_id=-1;
    uint16_t owner_index=peace_overextension_invalid_country_index;
    uint16_t beneficiary_index=peace_overextension_invalid_country_index;
};

struct PeaceOverextensionQueryResult {
    bool called=false;
    bool complete=false;
    bool unsupported_territorial_terms=false;
    unsigned country_count=0;
    unsigned impact_count=0;
    PeaceOverextensionCountry countries[peace_overextension_max_countries]{};
    PeaceOverextensionImpact impacts[peace_overextension_max_provinces]{};
};

static bool peace_overextension_add_country(
    uint64_t country,PeaceOverextensionQueryResult& output,
    unsigned& index) noexcept {
    index=peace_overextension_invalid_country_index;
    if (!country) return false;
    for (unsigned i=0;i<output.country_count;++i) {
        if (output.countries[i].country==country) {
            index=i;
            return true;
        }
    }
    if (output.country_count>=peace_overextension_max_countries) return false;
    uintptr_t record=0;
    char tag[4]{};
    if (!peace_query_country_pointer(country,record)
        || !record || !peace_province_tag(country,tag)) return false;
    index=output.country_count++;
    auto& row=output.countries[index];
    row=PeaceOverextensionCountry{};
    row.country=country;
    memcpy(row.tag,tag,sizeof(row.tag));
    return true;
}

static bool peace_overextension_projected_raw(
    int64_t development,int32_t modifier,int32_t& raw) noexcept {
    if (development<0 || development>INT32_MAX || modifier<0) return false;
    const int64_t adjusted=(development*static_cast<int64_t>(modifier))/1000;
    const int64_t projected=(adjusted*1000)/100000;
    if (projected<INT32_MIN || projected>INT32_MAX) return false;
    raw=static_cast<int32_t>(projected);
    return true;
}

static bool peace_overextension_read_current_country(
    PeaceOverextensionCountry& row,const PeaceProvinceArrayBounds& bounds) noexcept {
    uintptr_t country_record=0,owned_begin=0;
    int32_t owned_count=0,current_raw=0,modifier=0;
    if (!peace_query_country_pointer(row.country,country_record)
        || !country_record
        || !read(country_record+0xe48u,current_raw)
        || !read(country_record+0x1338u,owned_begin)
        || !read(country_record+0x1344u,owned_count)
        || owned_count<0 || owned_count>peace_overextension_max_owned_count
        || (owned_count!=0 && !owned_begin)) return false;

    using Modifier=int32_t* (*)(void*,int32_t*);
    if (reinterpret_cast<Modifier>(base+0x3cf290u)(
            reinterpret_cast<void*>(country_record),&modifier)
            !=&modifier || modifier<0) return false;

    // The native owner vector is bounded at 16K.  Keep one bounded scratch
    // list so duplicate province IDs cannot silently double-count development.
    int32_t owned_ids[peace_overextension_max_owned_count]{};
    for (int32_t i=0;i<owned_count;++i) {
        if (!read(owned_begin+static_cast<uintptr_t>(i)*4u,owned_ids[i])) return false;
    }
    std::sort(owned_ids,owned_ids+owned_count);
    for (int32_t i=1;i<owned_count;++i)
        if (owned_ids[i]==owned_ids[i-1]) return false;

    using Gate=unsigned char (*)(void*,uint64_t);
    using Development=int32_t* (*)(void*,int32_t*,unsigned char,
        unsigned char,void*);
    const auto gate=reinterpret_cast<Gate>(base+0xa25b90u);
    const auto development=reinterpret_cast<Development>(base+0xa0cff0u);
    int64_t total=0;
    for (int32_t i=0;i<owned_count;++i) {
        uintptr_t province=0;
        uint64_t owner=0;
        if (!peace_province_record_for_id(bounds,owned_ids[i],province)
            || !province || !read(province+0x468u,owner)
            || owner!=row.country) return false;
        if (gate(reinterpret_cast<void*>(province),row.country)==0) continue;
        int32_t value=0;
        if (development(reinterpret_cast<void*>(province),&value,0,1,nullptr)
                !=&value || value<0) return false;
        total+=value;
    }
    row.current_raw=current_raw;
    row.current_development=total;
    row.modifier_raw=modifier;
    if (!peace_overextension_projected_raw(total,modifier,
            row.current_recomputed_raw)) return false;
    row.cache_matches_recomputed=row.current_raw==row.current_recomputed_raw;
    row.complete=row.cache_matches_recomputed;
    return true;
}

static bool peace_overextension_add_impact(
    int32_t province_id,unsigned owner_index,unsigned beneficiary_index,
    PeaceOverextensionQueryResult& output) noexcept {
    if (province_id<0 || owner_index>=output.country_count
        || beneficiary_index>=output.country_count) return false;
    for (unsigned i=0;i<output.impact_count;++i)
        if (output.impacts[i].province_id==province_id) return false;
    if (output.impact_count>=peace_overextension_max_provinces) return false;
    output.impacts[output.impact_count++]={province_id,
        static_cast<uint16_t>(owner_index),
        static_cast<uint16_t>(beneficiary_index)};
    return true;
}

// Release Nation does not encode a single province in the payload.  The
// target country owns the established core chain at +0x1378; each node stores
// the province id at +0 and the next node at +0x10.  Keep this reader local to
// the read-only preview because peace-effect-state.inc is an execution-side
// include and is not visible from this query include.
static bool peace_overextension_capture_release_nation(
    const bridge::peace_payload::PeaceTermPayload& term,
    const PeaceProvinceArrayBounds& bounds,
    PeaceOverextensionQueryResult& output) noexcept {
    if (!term.field22 || !term.extra30 || term.field22==term.extra30) return false;

    unsigned source_index=peace_overextension_invalid_country_index;
    unsigned target_index=peace_overextension_invalid_country_index;
    if (!peace_overextension_add_country(term.field22,output,source_index)
        || !peace_overextension_add_country(term.extra30,output,target_index))
        return false;

    uintptr_t target_record=0,node=0;
    if (!peace_query_country_pointer(term.extra30,target_record)
        || !target_record || !read(target_record+0x1378u,node)) return false;

    // Track both links and province ids.  A step bound alone detects only a
    // very long chain; these arrays reject short cycles and duplicate rows.
    uintptr_t seen_nodes[peace_overextension_max_provinces]{};
    int32_t seen_provinces[peace_overextension_max_provinces]{};
    unsigned steps=0,seen_count=0;
    bool seen_any=false;
    while (node) {
        if (++steps>peace_overextension_max_provinces) return false;
        for (unsigned i=0;i<steps-1u;++i)
            if (seen_nodes[i]==node) return false;
        seen_nodes[steps-1u]=node;

        int32_t province_id=0;
        uintptr_t next=0,province=0;
        if (!read(node,province_id) || !read(node+0x10u,next)
            || province_id<=0
            || !peace_province_record_for_id(bounds,province_id,province)
            || !province) return false;
        for (unsigned i=0;i<seen_count;++i)
            if (seen_provinces[i]==province_id) return false;
        if (seen_count>=peace_overextension_max_provinces) return false;
        seen_provinces[seen_count++]=province_id;

        uint64_t owner=0;
        if (!read(province+0x468u,owner) || !owner) return false;
        if (owner==term.field22) {
            if (!peace_overextension_add_impact(province_id,source_index,
                    target_index,output)) return false;
            seen_any=true;
        }
        if (next==node) return false;
        node=next;
    }
    return seen_any;
}

static bool peace_overextension_capture_selected_terms(
    const bridge::peace_payload::PeaceOfferPayload& payload,
    const PeaceProvinceArrayBounds& bounds,PeaceOverextensionQueryResult& output) noexcept {
    using namespace bridge::peace_payload;
    for (uint32_t i=0;i<payload.term_count;++i) {
        const PeaceTermPayload& term=payload.terms[i];
        if (!term.selected) continue;
        if (term.field10!=payload.payer || term.field18!=payload.claimant) {
            output.complete=false;
            continue;
        }
        if ((term.type_id==0x2d25u && term.bucket==3u)
            || (term.type_id==0x2e00u && term.bucket==5u)) {
            if (!term.nested_present || term.nested_id==0u
                || term.nested_id>0x7fffffffU || !term.extra30) {
                output.complete=false;
                continue;
            }
            const int32_t province_id=static_cast<int32_t>(term.nested_id);
            uintptr_t province=0;
            uint64_t owner=0;
            if (!peace_province_record_for_id(bounds,province_id,province)
                || !read(province+0x468u,owner) || !owner) {
                output.complete=false;
                continue;
            }
            unsigned owner_index=0,beneficiary_index=0;
            if (!peace_overextension_add_country(owner,output,owner_index)
                || !peace_overextension_add_country(term.extra30,output,
                    beneficiary_index)
                || !peace_overextension_add_impact(province_id,owner_index,
                    beneficiary_index,output)) output.complete=false;
            continue;
        }
        if (term.type_id==0x2d28u && term.bucket==0x0fu) {
            if (!peace_overextension_capture_release_nation(term,bounds,output)) {
                output.unsupported_territorial_terms=true;
                output.complete=false;
            }
        }
    }
    return true;
}

static bool peace_overextension_apply_impacts(
    const PeaceProvinceArrayBounds& bounds,PeaceOverextensionQueryResult& output) noexcept {
    using Gate=unsigned char (*)(void*,uint64_t);
    using Development=int32_t* (*)(void*,int32_t*,unsigned char,
        unsigned char,void*);
    const auto gate=reinterpret_cast<Gate>(base+0xa25b90u);
    const auto development=reinterpret_cast<Development>(base+0xa0cff0u);
    for (unsigned i=0;i<output.impact_count;++i) {
        const PeaceOverextensionImpact& impact=output.impacts[i];
        if (impact.owner_index>=output.country_count
            || impact.beneficiary_index>=output.country_count) return false;
        uintptr_t province=0;
        uint64_t owner=0;
        if (!peace_province_record_for_id(bounds,impact.province_id,province)
            || !read(province+0x468u,owner)
            || owner!=output.countries[impact.owner_index].country) return false;
        if (gate(reinterpret_cast<void*>(province),
                output.countries[impact.owner_index].country)!=0) {
            int32_t value=0;
            if (development(reinterpret_cast<void*>(province),&value,0,1,nullptr)
                    !=&value || value<0) return false;
            output.countries[impact.owner_index].lost_development+=value;
        }
        if (gate(reinterpret_cast<void*>(province),
                output.countries[impact.beneficiary_index].country)!=0) {
            int32_t value=0;
            if (development(reinterpret_cast<void*>(province),&value,0,0,nullptr)
                    !=&value || value<0) return false;
            output.countries[impact.beneficiary_index].gained_development+=value;
        }
    }
    return true;
}

static bool peace_overextension_finish_country(
    PeaceOverextensionCountry& row) noexcept {
    int32_t gained_projection=0,lost_projection=0,projected=0;
    if (!peace_overextension_projected_raw(
            row.current_development+row.gained_development,row.modifier_raw,
            gained_projection)
        || !peace_overextension_projected_raw(
            row.current_development-row.lost_development,row.modifier_raw,
            lost_projection)
        || !peace_overextension_projected_raw(
            row.current_development-row.lost_development
                +row.gained_development,row.modifier_raw,projected)) return false;
    row.gained_raw=gained_projection-row.current_raw;
    row.lost_raw=row.current_raw-lost_projection;
    row.projected_raw=projected;
    row.delta_raw=row.projected_raw-row.current_raw;
    row.complete=row.complete && row.cache_matches_recomputed;
    return row.complete;
}

static bool peace_overextension_query(
    const bridge::peace_payload::PeaceOfferPayload& payload,
    PeaceOverextensionQueryResult& output) noexcept {
    output=PeaceOverextensionQueryResult{};
    output.called=true;
    output.complete=payload.valid();
    if (!output.complete) return false;
    PeaceProvinceArrayBounds bounds{};
    if (!peace_province_read_bounds(bounds)) {
        output.complete=false;
        return false;
    }
    unsigned ignored=0;
    if (!peace_overextension_add_country(payload.payer,output,ignored)
        || !peace_overextension_add_country(payload.claimant,output,ignored)) {
        output.complete=false;
        return false;
    }
    peace_overextension_capture_selected_terms(payload,bounds,output);
    for (unsigned i=0;i<output.country_count;++i) {
        if (!peace_overextension_read_current_country(
                output.countries[i],bounds)) output.complete=false;
    }
    if (!peace_overextension_apply_impacts(bounds,output)) output.complete=false;
    for (unsigned i=0;i<output.country_count;++i)
        if (!peace_overextension_finish_country(output.countries[i]))
            output.complete=false;
    return output.complete;
}

static bool peace_overextension_append(
    char* output,size_t capacity,size_t& used,const char* format,...) noexcept {
    if (!output || used>=capacity) return false;
    va_list args;
    va_start(args,format);
    const int written=vsnprintf(output+used,capacity-used,format,args);
    va_end(args);
    if (written<0 || static_cast<size_t>(written)>=capacity-used) return false;
    used+=static_cast<size_t>(written);
    return true;
}

static bool peace_overextension_query_json(
    const PeaceOverextensionQueryResult& query,char* output,size_t capacity) noexcept {
    size_t used=0;
    if (!peace_overextension_append(output,capacity,used,
            "{\"called\":%s,\"complete\":%s,\"scope\":\"selected_territorial_preview\",\"unsupported_territorial_terms\":%s,\"countries\":[",
            query.called?"true":"false",query.complete?"true":"false",
            query.unsupported_territorial_terms?"true":"false")) return false;
    for (unsigned i=0;i<query.country_count;++i) {
        const auto& row=query.countries[i];
        if (!peace_overextension_append(output,capacity,used,
                "%s{\"country\":\"%s\",\"complete\":%s,\"current_raw\":%d,\"current_recomputed_raw\":%d,\"cache_matches_recomputed\":%s,\"gained_raw\":%d,\"lost_raw\":%d,\"delta_raw\":%d,\"projected_raw\":%d,\"scale\":1000,\"gained_province_ids\":[",
                i?",":"",row.tag,row.complete?"true":"false",
                row.current_raw,row.current_recomputed_raw,
                row.cache_matches_recomputed?"true":"false",row.gained_raw,
                row.lost_raw,row.delta_raw,row.projected_raw)) return false;
        unsigned written=0;
        for (unsigned j=0;j<query.impact_count;++j) {
            if (query.impacts[j].beneficiary_index!=i) continue;
            if (!peace_overextension_append(output,capacity,used,"%s%d",
                    written++?",":"",query.impacts[j].province_id)) return false;
        }
        if (!peace_overextension_append(output,capacity,used,
                "],\"lost_province_ids\":[")) return false;
        written=0;
        for (unsigned j=0;j<query.impact_count;++j) {
            if (query.impacts[j].owner_index!=i) continue;
            if (!peace_overextension_append(output,capacity,used,"%s%d",
                    written++?",":"",query.impacts[j].province_id)) return false;
        }
        if (!peace_overextension_append(output,capacity,used,"]}")) return false;
    }
    return peace_overextension_append(output,capacity,used,"]}");
}
