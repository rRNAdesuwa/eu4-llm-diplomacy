// Declare War uses a 0x98-byte native object, with owned context and vectors.
// Empty parameters inspect the factory default; explicit parameters select a
// freshly enumerated native candidate. Neither query submits a command.

#include "declarewar-candidates.inc"

struct DeclareWarQueryHeader {
    uintptr_t vtable=0,owned=0;
    uint32_t discriminator=0;
    uint64_t actor=0,mirror=0,recipient=0;
    int32_t date28=0,date2c=0,envoy30=0,state34=0,proposal3c=0;
    uint16_t mode38=0;
    unsigned char flag40=0,flag41=0,flag42=0;
    uintptr_t containers[9]{};
};

static bool declarewar_query_header(void* action,DeclareWarQueryHeader& out) {
    const uintptr_t address=reinterpret_cast<uintptr_t>(action);
    return action && read(address,out.vtable) && out.vtable==base+0x1c80d90
        && read(address+8,out.discriminator) && out.discriminator==0x165
        && read(address+0x10,out.actor) && read(address+0x18,out.mirror)
        && read(address+0x20,out.recipient)
        && read(address+0x28,out.date28) && read(address+0x2c,out.date2c)
        && read(address+0x30,out.envoy30) && read(address+0x34,out.state34)
        && read(address+0x38,out.mode38) && read(address+0x3c,out.proposal3c)
        && read(address+0x40,out.flag40) && read(address+0x41,out.flag41)
        && read(address+0x42,out.flag42) && read(address+0x48,out.owned)
        && read(address+0x50,out.containers);
}

static bool declarewar_query_same_header(const DeclareWarQueryHeader& a,
    const DeclareWarQueryHeader& b) {
    return a.vtable==b.vtable && a.discriminator==b.discriminator
        && a.actor==b.actor && a.mirror==b.mirror && a.recipient==b.recipient
        && a.date28==b.date28 && a.date2c==b.date2c && a.envoy30==b.envoy30
        && a.state34==b.state34 && a.mode38==b.mode38 && a.proposal3c==b.proposal3c
        && a.flag40==b.flag40 && a.flag41==b.flag41 && a.flag42==b.flag42
        && a.owned==b.owned && !memcmp(a.containers,b.containers,sizeof(a.containers));
}

static void declarewar_query_hex(const NativeShortString& text,char (&hex)[1025],
    bool& readable,bool& truncated) {
    const unsigned length=static_cast<unsigned>(text.size<=512?text.size:512);
    uintptr_t address=reinterpret_cast<uintptr_t>(text.text);
    if (text.capacity>=16) memcpy(&address,text.text,8);
    unsigned char bytes[512]{}; SIZE_T copied=0;
    readable=text.size<=65536 && text.capacity<=131072 && (length==0
        || (ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(address),
                bytes,length,&copied) && copied==length));
    truncated=text.size>512;
    if (readable) for (unsigned i=0;i<length;++i) snprintf(hex+i*2,3,"%02x",bytes[i]);
}

#include "declarewar-cost-query.inc"

static void declarewar_query_run(const char* id,const char* actor_tag,
    const char* recipient_tag,uint64_t actor,uint64_t recipient,int32_t date,
    const char* casus_belli=nullptr,int32_t province_id=-1,
    const char* beneficiary_tag=nullptr) {
    static constexpr FactoryActionQueryMethods methods{
        0x293b,0x1c80d90,0x508de0,0x50a0d0,0x100,0x8f440,
        "declare_war",false,0x500550};
    const uintptr_t table=base+methods.vtable_rva;
    uintptr_t validity=0,common_method=0,send_method=0,destructor=0;
    if (!read(table+0x80,validity) || validity!=base+methods.validity_rva
        || !read(table+0x88,common_method) || common_method!=base+methods.display_rva
        || !read(table+0x90,send_method) || send_method!=base+0x509e60
        || !read(table,destructor)
        || (destructor!=base+methods.destructor_rva
            && !(destructor==reinterpret_cast<uintptr_t>(&lifecycle_destructor_observe)
                && lifecycle_declarewar_destructor_original==reinterpret_cast<LifecycleDestructorMethod>(base+methods.destructor_rva)))) {
        alliance_query_failure(id,"QUERY_DECLARE_WAR_METHOD_IDENTITY_CHANGED"); return;
    }
    bool visible=false;
    if (!factory_query_visibility(actor,recipient,true,visible,methods)) {
        alliance_query_failure(id,"QUERY_DECLARE_WAR_VISIBILITY_UNAVAILABLE"); return;
    }
    void* action=factory_query_create(actor,recipient,true,methods);
    if (!action) { alliance_query_failure(id,"QUERY_DECLARE_WAR_FACTORY_UNAVAILABLE"); return; }
    using Destroy=void* (*)(void*,unsigned);
    DeclareWarQueryHeader before{},after{}; uintptr_t empty=0;
    bool default_context=declarewar_query_header(action,before)
        && before.actor==actor && before.mirror==actor && before.recipient==recipient
        && before.state34==0 && before.mode38==1
        && read(base+0x2340010,empty) && empty && before.owned==empty;
    for (uintptr_t value:before.containers) default_context=default_context && value==0;
    if (!default_context) {
        reinterpret_cast<Destroy>(destructor)(action,1);
        alliance_query_failure(id,"QUERY_DECLARE_WAR_DEFAULT_CONTEXT_CHANGED"); return;
    }
    const bool selection_requested=casus_belli && casus_belli[0];
    const bool no_cb=selection_requested && !strcmp(casus_belli,"no_casus_belli");
    DeclareWarCandidateSelection selection{};
    selection.casus_belli=casus_belli;
    selection.province_id=province_id;
    if (selection_requested && beneficiary_tag && strcmp(beneficiary_tag,"---")
        && strcmp(beneficiary_tag,actor_tag)
        && !alliance_query_country(beneficiary_tag,selection.beneficiary_handle)) {
        reinterpret_cast<Destroy>(destructor)(action,1);
        alliance_query_failure(id,"QUERY_DECLARE_WAR_BENEFICIARY_UNAVAILABLE"); return;
    }
    if (no_cb && (province_id!=-1 || selection.beneficiary_handle)) {
        reinterpret_cast<Destroy>(destructor)(action,1);
        alliance_query_failure(id,"QUERY_DECLARE_WAR_NO_CB_PARAMETERS_INVALID"); return;
    }
    DeclareWarCandidateQueryResult candidates{};
    declarewar_candidates_query(actor,recipient,candidates,
        selection_requested && !no_cb?&selection:nullptr);
    const bool selection_matched=selection_requested && (no_cb
        || (candidates.selection_match_count==1 && candidates.selected_owned));
    if (candidates.selected_owned) {
        // The factory currently owns only the shared empty sentinel. This
        // matches ee7100: clone the selected candidate, then transfer it to
        // action+0x48. The action destructor owns the clone from this point.
        memcpy(reinterpret_cast<unsigned char*>(action)+0x48,
            &candidates.selected_owned,sizeof(candidates.selected_owned));
        if (!declarewar_query_header(action,before)) {
            reinterpret_cast<Destroy>(destructor)(action,1);
            alliance_query_failure(id,"QUERY_DECLARE_WAR_SELECTED_CONTEXT_UNREADABLE"); return;
        }
    }
    char candidate_json[131072]{};
    size_t candidate_used=0;
    for (unsigned i=0;i<candidates.captured_count;++i) {
        const DeclareWarCandidateCapture& item=candidates.items[i];
        const uint64_t beneficiary_display=item.beneficiary_identifier_verified
            ?item.beneficiary_raw:0x2d2d2d;
        if (item.private_raw_readable) {
            char raw_hex[193]{};
            for (unsigned byte=0;byte<sizeof(item.private_raw);++byte)
                snprintf(raw_hex+byte*2,3,"%02x",item.private_raw[byte]);
            char private_message[850];
            snprintf(private_message,sizeof(private_message),
                "{\"event\":\"native_declare_war_candidate_private\",\"private\":true,\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"candidate_index\":%u,\"vtable_rva\":\"0x%llx\",\"native_raw_hex\":\"%s\"}\n",
                static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
                id,actor_tag,recipient_tag,i,static_cast<unsigned long long>(item.vtable_rva),raw_hex);
            line(private_message);
        }
        const int written=snprintf(candidate_json+candidate_used,sizeof(candidate_json)-candidate_used,
            "%s{\"candidate_index\":%u,\"native_discriminator\":%u,\"metadata_group_raw\":%d,\"native_metadata_hex\":\"%s\",\"metadata_readable\":%s,\"metadata_text_readable\":%s,\"metadata_text_truncated\":%s,\"identifier_verified\":false,\"casus_belli_key\":\"%s\",\"casus_belli_key_verified\":%s,\"target_province_id\":%d,\"province_identifier_verified\":%s,\"beneficiary_tag\":\"%c%c%c\",\"beneficiary_identifier_verified\":%s}",
            i?",":"",i,item.candidate_discriminator_raw,item.metadata_group_raw,item.metadata_text_utf8_rawhex,
            item.metadata_readable?"true":"false",item.metadata_text_readable?"true":"false",
            item.metadata_text_truncated?"true":"false",item.casus_belli_key,
            item.casus_belli_key_verified?"true":"false",item.target_province_id,
            item.province_identifier_verified?"true":"false",
            static_cast<char>(beneficiary_display),static_cast<char>(beneficiary_display>>8),
            static_cast<char>(beneficiary_display>>16),item.beneficiary_identifier_verified?"true":"false");
        if (written<0 || static_cast<size_t>(written)>=sizeof(candidate_json)-candidate_used) {
            candidates.complete=false; candidates.truncated=true;
            candidate_json[candidate_used]=0; break;
        }
        candidate_used+=static_cast<size_t>(written);
    }
    const bool enumeration_complete=candidates.native_called && candidates.capture_complete
        && candidates.vector_cleanup_ok && candidates.callback_holder_cleanup_ok
        && candidates.callback_holder_empty_after && !candidates.truncated;
    const bool parameter_complete=selection_matched && enumeration_complete;
    DeclareWarCostQueryResult costs{};
    const bool costs_unchanged=declarewar_cost_query_run(action,costs,true);
    NativeShortString diagnostic{},common_text{},send_text{};
    diagnostic.capacity=common_text.capacity=send_text.capacity=15;
    using Predicate=bool (*)(void*,void*,unsigned char);
    const bool valid=reinterpret_cast<Predicate>(validity)(action,&diagnostic,0);
    const bool common=reinterpret_cast<Predicate>(common_method)(action,&common_text,0);
    const bool gate=reinterpret_cast<Predicate>(send_method)(action,&send_text,0);
    const NativeShortString& selected=diagnostic.size?diagnostic:common_text.size?common_text:send_text;
    char hex[1025]{},common_hex[1025]{},send_hex[1025]{};
    bool readable=false,truncated=false,common_readable=false,common_truncated=false;
    bool send_readable=false,send_truncated=false;
    declarewar_query_hex(selected,hex,readable,truncated);
    declarewar_query_hex(common_text,common_hex,common_readable,common_truncated);
    declarewar_query_hex(send_text,send_hex,send_readable,send_truncated);
    const bool unchanged=costs_unchanged && declarewar_query_header(action,after)
        && declarewar_query_same_header(before,after);
    using StringDestroy=void (*)(void*);
    reinterpret_cast<StringDestroy>(base+0x95660)(&diagnostic);
    reinterpret_cast<StringDestroy>(base+0x95660)(&common_text);
    reinterpret_cast<StringDestroy>(base+0x95660)(&send_text);
    reinterpret_cast<Destroy>(destructor)(action,1);
    if (!unchanged) {
        alliance_query_failure(id,"QUERY_DECLARE_WAR_OBJECT_CHANGED"); return;
    }
    char cost_json[2200];
    snprintf(cost_json,sizeof(cost_json),
        "{\"called\":true,\"action_unchanged\":%s,\"stability_available\":%s,\"stability_hit_raw\":%d,\"stability_scale\":1000,\"warex_available\":%s,\"warex_display_raw\":%d,\"primary_available\":%s,\"primary_raw\":%d,\"secondary_available\":%s,\"secondary_raw\":%d,\"native_text_hex\":\"%s\",\"text_readable\":%s,\"text_truncated\":%s,\"complete\":false}",
        costs.action_header_unchanged?"true":"false",costs.stability_hit_raw_available?"true":"false",costs.stability_hit_raw,
        costs.war_exhaustion_raw_available?"true":"false",costs.war_exhaustion_raw,
        costs.primary_raw_available?"true":"false",costs.primary_raw,
        costs.secondary_raw_available?"true":"false",costs.secondary_raw,costs.text_hex,
        costs.text_readable?"true":"false",costs.text_truncated?"true":"false");
    char message[139520];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_declare_war_inspection\",\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"action_id\":\"declare_war\",\"family\":\"declare_war\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"initiate\",\"date_raw\":%d,\"ui_selection_checked\":true,\"native_visibility\":%s,\"ui_enabled_gate_checked\":true,\"common_action_gate\":%s,\"validity_called\":true,\"native_validity\":%s,\"initiation_gate_checked\":true,\"initiation_gate\":%s,\"native_diagnostic_hex\":\"%s\",\"diagnostic_readable\":%s,\"diagnostic_truncated\":%s,\"common_diagnostic_hex\":\"%s\",\"common_diagnostic_readable\":%s,\"common_diagnostic_truncated\":%s,\"send_diagnostic_hex\":\"%s\",\"send_diagnostic_readable\":%s,\"send_diagnostic_truncated\":%s,",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
        id,actor_tag,recipient_tag,date,visible?"true":"false",common?"true":"false",valid?"true":"false",gate?"true":"false",
        hex,readable?"true":"false",truncated?"true":"false",common_hex,common_readable?"true":"false",common_truncated?"true":"false",
        send_hex,send_readable?"true":"false",send_truncated?"true":"false");
    const size_t used=strlen(message);
    snprintf(message+used,sizeof(message)-used,
        "\"native_default_payload\":%s,\"owned_payload_present\":%s,\"owned_payload_source_kind\":\"%s\",\"owned_payload_identity_verified\":true,\"object_unchanged\":true,\"parameter_context_complete\":%s,\"candidate_context_complete\":%s,\"selection_requested\":%s,\"selection_matched\":%s,\"selection_match_count\":%u,\"requested_casus_belli\":\"%s\",\"requested_province_id\":%d,\"requested_beneficiary\":\"%.3s\",\"candidate_enumeration_called\":%s,\"candidate_enumeration_complete\":%s,\"candidate_native_count\":%u,\"candidate_capture_truncated\":%s,\"candidate_cleanup_verified\":%s,\"candidates\":[%s],\"native_costs\":%s,\"score_applicable\":false,\"full_rules_complete\":%s,\"reasons_complete\":false,\"submitted\":false,\"frame_thread\":%lu}\n",
        candidates.selected_owned?"false":"true",candidates.selected_owned?"true":"false",
        candidates.selected_owned?"native_selected_candidate_clone":"canonical_empty_sentinel",
        parameter_complete?"true":"false",parameter_complete?"true":"false",
        selection_requested?"true":"false",selection_matched?"true":"false",
        no_cb?1u:candidates.selection_match_count,casus_belli?casus_belli:"",province_id,
        beneficiary_tag?beneficiary_tag:"---",
        candidates.native_called?"true":"false",enumeration_complete?"true":"false",candidates.native_count,
        candidates.truncated?"true":"false",candidates.vector_cleanup_ok && candidates.callback_holder_cleanup_ok?"true":"false",
        candidate_json,cost_json,parameter_complete?"true":"false",static_cast<unsigned long>(GetCurrentThreadId()));
    line(message);
}
