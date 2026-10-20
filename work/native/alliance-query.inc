// Frame-thread queries on owned native alliance/royal-marriage actions. No wrapper,
// dispatcher, transport, authorization seed or business executor is called.
#if defined(BRIDGE_ALLIANCE_REASON_METADATA)
#include "alliance-reason-metadata-bind.inc"
#endif

static wchar_t alliance_query_path[MAX_PATH];
static char alliance_query_ids[128][65]{};
static uint64_t alliance_query_expiries[128]{};

static uint64_t alliance_query_clock() {
    FILETIME now{}; GetSystemTimeAsFileTime(&now);
    return (static_cast<uint64_t>(now.dwHighDateTime)<<32)|now.dwLowDateTime;
}
static bool alliance_query_country(const char* tag,uint64_t& handle) {
    handle=0;
    uintptr_t database=0,table=0,array=0;
    uint32_t capacity=0,count=0;
    // CountryDB+110 is CArray<Country*>. Its native 8f560 method reads
    // count+14 and capacity+10 and allocates count*8 bytes. R63's live
    // header records 1380 entries; 256 was only the first experiment's scope.
    if (strlen(tag)!=3 || !read(base+0x233d8b0,database)
        || !read(database+0x110,table) || table!=base+0x1c38348
        || !read(database+0x118,array) || !array
        || !read(database+0x120,capacity) || !read(database+0x124,count)
        || !count || count>4096 || capacity<count || capacity>8192) return false;
    for (unsigned slot=0;slot<count;++slot) {
        uintptr_t country=0; uint64_t candidate=0;
        if (!read(array+slot*8,country)) return false;
        if (!country) continue;
        if (!read(country+0x20,candidate)) return false;
        if (((candidate>>32)&0xffff)!=slot) continue;
        if (static_cast<char>(candidate)==tag[0] && static_cast<char>(candidate>>8)==tag[1]
            && static_cast<char>(candidate>>16)==tag[2]) { handle=candidate; return true; }
    }
    return false;
}
static void alliance_query_failure(const char* id,const char* code) {
    char message[280];
    snprintf(message,sizeof(message),"{\"event\":\"native_alliance_inspection_failed\",\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"reason_code\":\"%s\",\"submitted\":false}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),id,code);
    line(message);
}
static bool alliance_query_visibility(uint64_t actor,uint64_t recipient,bool offer,bool& visible,
    int32_t selector=0x293d) {
    // The actual diplomacy-view list calls this selector before it constructs
    // action 0x293d. The recovered case is a bounded native membership read;
    // this is separate from +0x90, which controls the button's enabled state.
    static const unsigned char selector_entry[]={0x48,0x89,0x5c,0x24,0x08};
    static const unsigned char alliance_case[]={0x48,0x8b,0xce,0xe8,0xd5,0xe1,0x70,0x00,
        0x0f,0xb6,0xf8,0x40,0x32,0xfd,0xe9,0x6d,0x14,0x00,0x00};
    static const unsigned char marriage_case[]={0x48,0x8b,0xce,0xe8,0xf7,0xdd,0x70,0x00,
        0x0f,0xb6,0xf8,0x40,0x32,0xfd,0xe9,0x3f,0x12,0x00,0x00};
    if (selector!=0x293d && selector!=0x28df) return false;
    const bool marriage=selector==0x28df;
    const uintptr_t case_rva=marriage?0x35ac11:0x35a9e3;
    const unsigned char* expected_case=marriage?marriage_case:alliance_case;
    unsigned char entry[sizeof(selector_entry)]{},case_bytes[sizeof(alliance_case)]{};
    SIZE_T copied=0; unsigned char switch_index=0; uint32_t switch_target=0;
    if (!ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(base+0x35a920),entry,sizeof(entry),&copied)
        || copied!=sizeof(entry) || memcmp(entry,selector_entry,sizeof(entry))
        || !ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(base+case_rva),case_bytes,sizeof(case_bytes),&copied)
        || copied!=sizeof(case_bytes) || memcmp(case_bytes,expected_case,sizeof(case_bytes))
        || !read(base+0x35bebc+(selector-0x28df),switch_index) || switch_index!=(marriage?0:3)
        || !read(base+0x35be80+switch_index*4,switch_target) || switch_target!=case_rva) return false;
    unsigned actor_slot=static_cast<unsigned>((actor>>32)&0xffff);
    unsigned recipient_slot=static_cast<unsigned>((recipient>>32)&0xffff);
    uintptr_t database=0,countries=0,country=0,table=0,owner=0,start=0;
    uint64_t actual_actor=0,actual_recipient=0; int32_t count=0;
    uint32_t country_count=0;
    if (!read(base+0x233d8b0,database) || !read(database+0x124,country_count)
        || !country_count || country_count>4096 || actor_slot>=country_count || recipient_slot>=country_count
        || !read(database+0x118,countries)
        || !read(countries+actor_slot*8,country) || !read(country+0x20,actual_actor) || actual_actor!=actor
        || !read(country+0x1510,table) || !table) return false;
    uintptr_t relation=table+recipient_slot*72;
    if (!read(relation,owner) || !read(relation+0x10,actual_recipient) || actual_recipient!=recipient
        || !read(owner+(marriage?0x68:0x80),start)
        || !read(owner+(marriage?0x74:0x8c),count) || count<0 || count>4096
        || (count && !start)) return false;
    // Validate the entire range the native helper traverses before calling it.
    for (int32_t i=0;i<count;++i) {
        unsigned char row[16]{};
        if (!ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(start+static_cast<uintptr_t>(i)*16),
            row,sizeof(row),&copied) || copied!=sizeof(row)) return false;
    }
    using Selector=bool (*)(void*,int32_t,uint64_t,void*,unsigned char,void*);
    visible=reinterpret_cast<Selector>(base+0x35a920)(reinterpret_cast<void*>(country),selector,recipient,
        reinterpret_cast<void*>(relation),offer?1:0,nullptr);
    return true;
}
static bool alliance_query_diplomats(uint64_t actor,unsigned& available) {
    uintptr_t database=0,countries=0,country=0,context=0,manager=0,begin=0,end=0;
    uint64_t actual=0;
    uint32_t country_count=0;
    unsigned slot=static_cast<unsigned>((actor>>32)&0xffff);
    if (!read(base+0x233d8b0,database) || !read(database+0x124,country_count)
        || !country_count || country_count>4096 || slot>=country_count || !read(database+0x118,countries)
        || !read(countries+slot*8,country) || !read(country+0x20,actual) || actual!=actor
        || !read(country+0x1480,context) || !read(context+0x18,manager)
        || !read(manager+0x20,begin) || !read(manager+0x28,end) || end<begin
        || (end-begin)%8 || (end-begin)/8>256) return false;
    available=0;
    for (uintptr_t item=begin;item<end;item+=8) {
        uintptr_t entry=0; unsigned char active=0;
        if (!read(item,entry) || !read(entry+0x18,active)) return false;
        if (!active) ++available;
    }
    return true;
}
#if !defined(BRIDGE_ALLIANCE_REASON_METADATA)
static void alliance_query_reason(const char* id,unsigned index,const unsigned char* raw) {
    // The row helpers independently establish value +0, string +8 and flag
    // +40. Copy the string while the native frame still owns this container;
    // a heap pointer in a later log is not a persistent string reference.
    int32_t value=0; uint64_t size=0,capacity=0; uintptr_t address=0;
    memcpy(&value,raw,4); memcpy(&size,raw+24,8); memcpy(&capacity,raw+32,8);
    bool shape=size<=capacity && capacity<=131072 && raw[40]<=1;
    if (capacity<16) { shape=shape && capacity==15; address=reinterpret_cast<uintptr_t>(raw+8); }
    else memcpy(&address,raw+8,8);
    unsigned bytes=static_cast<unsigned>(size<=512?size:512);
    unsigned char text[512]{}; char hex[1025]{}; SIZE_T copied=0;
    bool readable=shape && (bytes==0 || (ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(address),text,bytes,&copied) && copied==bytes));
    if (readable) for (unsigned i=0;i<bytes;++i) snprintf(hex+i*2,3,"%02x",text[i]);
    char message[1500];
    snprintf(message,sizeof(message),"{\"event\":\"native_alliance_reason_item\",\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"index\":%u,\"native_value\":%d,\"native_flag\":%s,\"text_hex\":\"%s\",\"text_readable\":%s,\"text_truncated\":%s,\"native_identifier_verified\":false,\"complete\":false}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),id,index,value,
        raw[40]?"true":"false",hex,readable?"true":"false",size>512?"true":"false");
    line(message);
}
#endif

#if defined(BRIDGE_ALLIANCE_REASON_METADATA)
static void alliance_query_reason_hex(const unsigned char* bytes,unsigned size,
    char* output,unsigned output_size) {
    if (!output || !output_size) return;
    output[0]='\0';
    if (!bytes || output_size<3) return;
    const unsigned limit=(size*2+1<output_size)
        ?size:(output_size-1)/2;
    for (unsigned index=0;index<limit;++index)
        snprintf(output+index*2,3,"%02x",bytes[index]);
    output[limit*2]='\0';
}

static void alliance_query_reason_metadata_text(const unsigned char* raw,
    unsigned char* text,unsigned& text_bytes,uint64_t& string_size,
    uint64_t& string_capacity,bool& readable,bool& truncated) {
    string_size=0; string_capacity=0; text_bytes=0; readable=false;
    truncated=false;
    if (!raw) return;
    uintptr_t address=0;
    memcpy(&string_size,raw+24,8);
    memcpy(&string_capacity,raw+32,8);
    truncated=string_size>512;
    text_bytes=static_cast<unsigned>(string_size<=512?string_size:512);
    const bool shape=string_size<=string_capacity && string_capacity<=131072
        && (string_capacity<16?string_capacity==15:string_capacity>=16);
    if (!shape) return;
    if (string_capacity<16) address=reinterpret_cast<uintptr_t>(raw+8);
    else memcpy(&address,raw+8,8);
    SIZE_T copied=0;
    readable=text_bytes==0 || (address && ReadProcessMemory(GetCurrentProcess(),
        reinterpret_cast<void*>(address),text,text_bytes,&copied)
        && copied==text_bytes);
}

static void alliance_query_reason_provenance(const char* id,unsigned index,
    const Binding& binding,bool final_row_binding) {
    const ReasonMetadataRecord* capture=binding.capture;
    if (!capture) return;
    char raw_hex[97]{},text_hex[1025]{},key_json[80]{},rdata_json[32]{};
    alliance_query_reason_hex(capture->row_raw,48,raw_hex,sizeof(raw_hex));
    alliance_query_reason_hex(capture->text,capture->text_bytes,text_hex,
        sizeof(text_hex));
    const bool key_verified=capture->constructor_source_confirmed;
    if (key_verified) {
        snprintf(key_json,sizeof(key_json),"\"%s\"",
            capture->localization_key);
        snprintf(rdata_json,sizeof(rdata_json),"\"0x%x\"",
            capture->localization_rdata_rva);
    } else {
        strcpy(key_json,"null");
        strcpy(rdata_json,"null");
    }
    char message[2800];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_alliance_reason_provenance\",\"private\":true,\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"index\":%u,\"constructor_sequence\":%llu,\"constructor_caller_rva\":\"0x%x\",\"constructor_call_rva\":\"0x%x\",\"native_value\":%d,\"constructor_argument_value\":%d,\"native_flag\":%s,\"string_size\":%llu,\"string_capacity\":%llu,\"text_hex\":\"%s\",\"raw48\":\"%s\",\"constructor_source_confirmed\":%s,\"conditional_key_caller\":%s,\"conditional_flags_readable\":%s,\"native_text_flag\":%u,\"native_overlord_flag\":%u,\"native_text_flag_row_offset\":%u,\"native_overlord_flag_row_offset\":%u,\"branch_condition_readable\":%s,\"branch_condition_value\":%u,\"branch_condition_row_offset\":%u,\"localization_rdata_rva\":%s,\"localization_key\":%s,\"constructor_value_verified\":%s,\"final_row_binding\":%s,\"complete\":%s}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),
        static_cast<unsigned long long>(observation_creation),id,index,
        static_cast<unsigned long long>(capture->sequence),
        capture->caller_return_rva,capture->constructor_call_rva,
        capture->raw_value,capture->constructor_argument_value,
        capture->derived_flag?"true":"false",
        static_cast<unsigned long long>(capture->string_size),
        static_cast<unsigned long long>(capture->string_capacity),text_hex,
        raw_hex,key_verified?"true":"false",
        capture->key_branch.matched?"true":"false",
        capture->key_branch.flags_readable?"true":"false",
        static_cast<unsigned>(capture->key_branch.text_flag),
        static_cast<unsigned>(capture->key_branch.overlord_flag),
        static_cast<unsigned>(capture->key_branch.text_offset),
        static_cast<unsigned>(capture->key_branch.overlord_offset),
        capture->key_branch.condition_readable?"true":"false",
        static_cast<unsigned>(capture->key_branch.condition_value),
        static_cast<unsigned>(capture->key_branch.condition_offset),rdata_json,key_json,
        binding.constructor_value_verified?"true":"false",
        final_row_binding?"true":"false",
        (final_row_binding && binding.strict_match)?"true":"false");
    line(message);
}

static void alliance_query_reason_bound(const char* id,unsigned index,
    const unsigned char* raw,const Binding& binding,bool all_bound) {
    int32_t value=0; unsigned char flag=0; memcpy(&value,raw,4);
    flag=raw[40];
    unsigned char fallback_text[512]{}; unsigned text_bytes=0;
    uint64_t string_size=0,string_capacity=0; bool text_readable=false;
    bool text_truncated=false;
    alliance_query_reason_metadata_text(raw,fallback_text,text_bytes,
        string_size,string_capacity,text_readable,text_truncated);
    const unsigned char* text=fallback_text;
    if (binding.final_row_readable) {
        value=binding.final_value;
        flag=binding.final_flag;
        string_size=binding.final_string_size;
        string_capacity=binding.final_string_capacity;
        text_bytes=binding.final_text_bytes;
        text_readable=binding.final_text_readable;
        text_truncated=string_size>512;
        text=binding.final_text;
    }
    const ReasonMetadataRecord* capture=binding.capture;
    const bool value_verified=binding.constructor_value_verified;
    const bool row_binding_verified=all_bound && binding.strict_match;
    const bool identifier_verified=row_binding_verified && capture
        && capture->constructor_source_confirmed;
    char text_hex[1025]{},key_json[80]{},source_json[64]{};
    alliance_query_reason_hex(text,text_bytes,text_hex,sizeof(text_hex));
    if (identifier_verified) {
        snprintf(key_json,sizeof(key_json),"\"%s\"",
            capture->localization_key);
        strcpy(source_json,"\"native_localization_key\"");
    } else {
        strcpy(key_json,"null");
        strcpy(source_json,"null");
    }
    char message[2400];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_alliance_reason_item\",\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"index\":%u,\"native_value\":%d,\"native_flag\":%s,\"text_hex\":\"%s\",\"text_readable\":%s,\"text_truncated\":%s,\"text_size\":%llu,\"string_capacity\":%llu,\"native_identifier\":%s,\"native_identifier_verified\":%s,\"identifier_verified\":%s,\"identity_source\":%s,\"value_representation\":\"signed_int32\",\"value_normalized\":false,\"native_unit\":\"unknown\",\"constructor_value_verified\":%s,\"row_binding_verified\":%s,\"text_encoding_verified\":false,\"complete\":%s}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),
        static_cast<unsigned long long>(observation_creation),id,index,value,
        flag?"true":"false",text_hex,text_readable?"true":"false",
        text_truncated?"true":"false",
        static_cast<unsigned long long>(string_size),
        static_cast<unsigned long long>(string_capacity),key_json,
        identifier_verified?"true":"false",identifier_verified?"true":"false",
        source_json,value_verified?"true":"false",
        row_binding_verified?"true":"false",
        row_binding_verified?"true":"false");
    line(message);
}

static void alliance_query_reason_scale(const char* id,int32_t total,
    unsigned reason_count,unsigned capture_count,bool overflow,bool bound) {
    char message[720];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_alliance_reason_scale\",\"private\":true,\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"native_total_raw\":%d,\"native_total_value_representation\":\"signed_int32\",\"native_total_normalized\":false,\"native_total_unit\":\"unknown\",\"acceptance_threshold_raw\":1,\"acceptance_threshold_representation\":\"signed_int32\",\"reason_count\":%u,\"constructor_capture_count\":%u,\"constructor_capture_overflow\":%s,\"constructor_vector_binding_verified\":%s,\"divide_by_1000\":false}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),
        static_cast<unsigned long long>(observation_creation),id,total,
        reason_count,capture_count,overflow?"true":"false",
        bound?"true":"false");
    line(message);
}
#endif

struct FactoryActionQueryMethods {
    int32_t selector;
    uintptr_t vtable_rva,validity_rva,display_rva;
    unsigned diplomat_slot;
    uintptr_t diplomat_rva;
    const char* name;
    bool task;
    uintptr_t destructor_rva=0x129450;
};
static constexpr FactoryActionQueryMethods unilateral_improve{
    0x2ddb,0x1c7dd68,0x574490,0x574700,0xf8,0x4e4d80,"improve_relations",true};
static constexpr FactoryActionQueryMethods unilateral_spy{
    0x3378,0x1c7cc48,0x5856d0,0x585910,0xf8,0x4e4d80,"spy_network",true};
static constexpr FactoryActionQueryMethods unilateral_guarantee{
    0x2941,0x1c7fe50,0x521b00,0x521f30,0x100,0x8f440,"guarantee",false};

static constexpr FactoryActionQueryMethods support_query_methods{
    0x2f2e,0x1c805f0,0x50e120,0x50ee20,0x100,0x8f440,"support_independence",false};
static constexpr FactoryActionQueryMethods military_query_methods{
    0x2943,0x1c7fb70,0x525530,0x525bf0,0x100,0x8f440,"military_access",false};
static constexpr FactoryActionQueryMethods vassal_query_methods{
    0x2940,0x1c7fd20,0x51f050,0x51f4d0,0x100,0x8f440,"vassalization",false};
static constexpr FactoryActionQueryMethods favor_gold_query_methods{
    0x3bce,0x1c80980,0x4f4f10,0x4f56b0,0x100,0x8f440,"favor_trade",false};
static constexpr FactoryActionQueryMethods favor_trust_query_methods{
    0x3bd3,0x1c80c60,0x4fdfd0,0x4fe2d0,0x100,0x8f440,"favor_trade",false,0x129500};
static constexpr FactoryActionQueryMethods favor_men_query_methods{
    0x3bcf,0x1c80ff0,0x4f7600,0x4f7ca0,0x100,0x8f440,"favor_trade",false};
static constexpr FactoryActionQueryMethods curry_favors_query_methods{
    0x3acc,0x1c7aef8,0x5ade90,0x5ae140,0xf8,0x4e4d80,"curry_favors",true};
static constexpr FactoryActionQueryMethods insult_query_methods{
    0x2947,0x1c7f6b0,0x538730,0x538a00,0x100,0x8f440,"insult",false,0x129500};
// R74 immediate one-sided actions.  Their +0x80/+0x88 rules and display
// guards are family-specific; both use the common diplomat predicate slot.
static constexpr FactoryActionQueryMethods gift_query_methods{
    0x2948,0x1c7f450,0x53a630,0x53a8d0,0xf8,0x8f450,"gift",false,0x129500};
static constexpr FactoryActionQueryMethods influence_query_methods{
    0x346e,0x1cb3cf8,0x7c4430,0x7c48a0,0xf8,0x8f450,"influence",false};

static const FactoryActionQueryMethods* unilateral_query_family(const char* action_id) {
    if (!strcmp(action_id,"improve_relations") || !strcmp(action_id,"stop_improving_relations"))
        return &unilateral_improve;
    if (!strcmp(action_id,"build_spy_network") || !strcmp(action_id,"stop_building_spy_network"))
        return &unilateral_spy;
    if (!strcmp(action_id,"proclaim_guarantee") || !strcmp(action_id,"revoke_guarantee"))
        return &unilateral_guarantee;
    if (!strcmp(action_id,"curry_favors") || !strcmp(action_id,"stop_curry_favors"))
        return &curry_favors_query_methods;
    return nullptr;
}

static void* factory_query_create(uint64_t actor,uint64_t recipient,bool start,
    const FactoryActionQueryMethods& family) {
    uintptr_t database=0,countries=0,country=0;
    uint64_t actual=0;
    if (!read(base+0x233d8b0,database) || !read(database+0x118,countries)
        || !read(countries+static_cast<uintptr_t>((actor>>32)&0xffffu)*8,country)
        || !read(country+0x20,actual) || actual!=actor) return nullptr;
    using Creator=void* (*)(void*,int32_t,uint64_t,unsigned char,void*);
    void* action=reinterpret_cast<Creator>(base+0x35a8b0)(
        reinterpret_cast<void*>(country),family.selector,recipient,start?1:0,nullptr);
    if (!action) return nullptr;
    uintptr_t table=0; uint64_t a=0,r=0; unsigned char mode=0;
    if (!read(reinterpret_cast<uintptr_t>(action),table) || table!=base+family.vtable_rva
        || !read(reinterpret_cast<uintptr_t>(action)+0x10,a) || a!=actor
        || !read(reinterpret_cast<uintptr_t>(action)+0x20,r) || r!=recipient
        || !read(reinterpret_cast<uintptr_t>(action)+0x38,mode) || mode!=(start?1:0)) {
        // The owned object came from the pinned factory. Release only when
        // the returned class is exactly the expected 0x40-byte family.
        if (table==base+family.vtable_rva)
            reinterpret_cast<void* (*)(void*,unsigned)>(base+family.destructor_rva)(action,1);
        return nullptr;
    }
    return action;
}

static bool factory_query_visibility(uint64_t actor,uint64_t recipient,
    bool start,bool& visible,const FactoryActionQueryMethods& family) {
    uintptr_t database=0,countries=0,country=0,relations=0;
    uint64_t actual=0,other=0;
    const unsigned slot=static_cast<unsigned>((actor>>32)&0xffffu);
    const unsigned target_slot=static_cast<unsigned>((recipient>>32)&0xffffu);
    uint32_t country_count=0;
    if (!read(base+0x233d8b0,database) || !read(database+0x124,country_count)
        || !country_count || country_count>4096 || slot>=country_count || target_slot>=country_count
        || !read(database+0x118,countries) || !read(countries+slot*8,country)
        || !read(country+0x20,actual) || actual!=actor
        || !read(country+0x1510,relations) || !relations) return false;
    const uintptr_t relation=relations+target_slot*72;
    if (!read(relation+0x10,other) || other!=recipient) return false;
    using Selector=bool (*)(void*,int32_t,uint64_t,void*,unsigned char,void*);
    visible=reinterpret_cast<Selector>(base+0x35a920)(
        reinterpret_cast<void*>(country),family.selector,recipient,
        reinterpret_cast<void*>(relation),start?1:0,nullptr);
    return true;
}

static bool factory_query_relation_active(uint64_t actor,uint64_t recipient,bool& active,
    const FactoryActionQueryMethods& family) {
    void* action=factory_query_create(actor,recipient,false,family);
    if (!action) return false;
    // The native stop validity branch returns whether this actor has the
    // corresponding task or persistent Guarantee association with this recipient.
    active=reinterpret_cast<bool (*)(void*,void*,unsigned char)>(base+family.validity_rva)(action,nullptr,0);
    reinterpret_cast<void* (*)(void*,unsigned)>(base+0x129450)(action,1);
    return true;
}

static bool support_query_active(uint64_t actor,uint64_t recipient,bool& active) {
    // Native mode-0 validity returns immediately from the exact support list
    // membership branch; start rules do not affect this relationship query.
    return factory_query_relation_active(actor,recipient,active,support_query_methods);
}

static bool military_query_active(uint64_t actor,uint64_t recipient,bool& active) {
    // Ask and Cancel use the requester's own relation row. Cancel validity
    // also checks troops, so it cannot serve as a pure relationship query.
    uintptr_t database=0,countries=0,country=0,relations=0,owner=0,begin=0;
    uint64_t actual=0,other=0; int32_t count=0;
    const unsigned slot=static_cast<unsigned>((actor>>32)&0xffffu);
    const unsigned target_slot=static_cast<unsigned>((recipient>>32)&0xffffu);
    uint32_t country_count=0;
    if (!read(base+0x233d8b0,database) || !read(database+0x124,country_count)
        || !country_count || country_count>4096 || slot>=country_count || target_slot>=country_count
        || !read(database+0x118,countries) || !read(countries+slot*8,country)
        || !read(country+0x20,actual) || actual!=actor
        || !read(country+0x1510,relations) || !relations) return false;
    const uintptr_t relation=relations+target_slot*72;
    if (!read(relation+0x10,other) || other!=recipient || !read(relation,owner)
        || !read(owner+0xb0,begin) || !read(owner+0xbc,count)
        || count<0 || count>4096 || (count && !begin)) return false;
    for (int32_t index=0;index<count;++index) {
        unsigned char row[16]{}; SIZE_T copied=0;
        if (!ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(
                begin+static_cast<uintptr_t>(index)*16),row,sizeof(row),&copied)
            || copied!=sizeof(row)) return false;
    }
    active=reinterpret_cast<bool (*)(void*)>(base+0xa68e60)(reinterpret_cast<void*>(relation));
    return true;
}

static void unilateral_query_run(const char* id,const char* action_id,
    const char* actor_tag,const char* recipient_tag,uint64_t actor,
    uint64_t recipient,int32_t date,const FactoryActionQueryMethods& family) {
    const bool start=strcmp(action_id,"improve_relations")==0 || strcmp(action_id,"build_spy_network")==0
        || strcmp(action_id,"proclaim_guarantee")==0
        || strcmp(action_id,"curry_favors")==0;
    const uintptr_t vtable=base+family.vtable_rva;
    uintptr_t display=0,validity=0,send_gate=0,requires_diplomat=0;
    if (!read(vtable+0x88,display) || display!=base+family.display_rva
        || !read(vtable+0x80,validity) || validity!=base+family.validity_rva
        || !read(vtable+0x90,send_gate) || send_gate!=base+0x4e9b40
        || !read(vtable+family.diplomat_slot,requires_diplomat) || requires_diplomat!=base+family.diplomat_rva) {
        alliance_query_failure(id,"QUERY_UNILATERAL_METHOD_IDENTITY_CHANGED"); return;
    }
    bool visible=false,active=false; unsigned available=0;
    if (!factory_query_visibility(actor,recipient,start,visible,family)
        || !alliance_query_diplomats(actor,available)
        || !factory_query_relation_active(actor,recipient,active,family)) {
        alliance_query_failure(id,"QUERY_UNILATERAL_CONTEXT_UNAVAILABLE"); return;
    }
    void* action=factory_query_create(actor,recipient,start,family);
    if (!action) { alliance_query_failure(id,"QUERY_UNILATERAL_FACTORY_UNAVAILABLE"); return; }
    using Predicate=bool (*)(void*,void*,unsigned char);
    NativeShortString diagnostic{}; diagnostic.capacity=15;
    NativeShortString tooltip{}; tooltip.capacity=15;
    const bool common=reinterpret_cast<Predicate>(display)(action,nullptr,0);
    const bool valid=reinterpret_cast<Predicate>(validity)(action,&diagnostic,0);
    // +0x90 supplies tooltip/cost text; +0x88 is the native enabled guard.
    const bool gate=common;
    const bool tooltip_gate=reinterpret_cast<Predicate>(send_gate)(action,&tooltip,0);
    const bool needs_diplomat=reinterpret_cast<bool (*)(void*)>(requires_diplomat)(action);
    NativeShortString& selected=diagnostic.size ? diagnostic : tooltip;
    unsigned length=static_cast<unsigned>(selected.size<=512?selected.size:512);
    uintptr_t address=reinterpret_cast<uintptr_t>(selected.text);
    if (selected.capacity>=16) memcpy(&address,selected.text,8);
    unsigned char bytes[512]{}; char hex[1025]{}; SIZE_T copied=0;
    bool readable=length==0 || (selected.size<=65536 && selected.capacity<=131072
        && ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(address),bytes,length,&copied)
        && copied==length);
    if (readable) for (unsigned index=0;index<length;++index) snprintf(hex+index*2,3,"%02x",bytes[index]);
    const bool truncated=selected.size>512;
    reinterpret_cast<void (*)(void*)>(base+0x95660)(&diagnostic);
    reinterpret_cast<void (*)(void*)>(base+0x95660)(&tooltip);
    reinterpret_cast<void* (*)(void*,unsigned)>(base+0x129450)(action,1);
    char message[3200];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_alliance_inspection\",\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"action_id\":\"%s\",\"family\":\"%s\",\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"initiate\",\"date_raw\":%d,\"ui_selection_checked\":true,\"native_visibility\":%s,\"ui_enabled_gate_checked\":true,\"common_action_gate\":%s,\"display_predicate\":%s,\"initiation_gate\":%s,\"tooltip_gate\":%s,\"validity_called\":true,\"native_validity\":%s,\"native_diagnostic_hex\":\"%s\",\"diagnostic_readable\":%s,\"diagnostic_truncated\":%s,\"diplomat_context_readable\":true,\"diplomat_required\":%s,\"available_diplomat_count\":%u,\"diplomat_assignment_verified\":false,\"%s\":%s,\"%s\":true,\"score_applicable\":false,\"score_available\":false,\"acceptance_predicate_available\":false,\"native_would_accept\":false,\"native_total_raw\":0,\"acceptance_threshold_raw\":1,\"reason_container_readable\":false,\"reason_count\":0,\"reason_items_decoded\":false,\"full_rules_complete\":true,\"reasons_complete\":false,\"submitted\":false,\"frame_thread\":%lu}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
        id,action_id,family.name,actor_tag,recipient_tag,date,visible?"true":"false",common?"true":"false",common?"true":"false",
        gate?"true":"false",tooltip_gate?"true":"false",valid?"true":"false",hex,
        readable?"true":"false",truncated?"true":"false",needs_diplomat?"true":"false",available,
        family.task?"task_active":"guarantee_active",active?"true":"false",
        family.task?"task_state_verified":"guarantee_state_verified",static_cast<unsigned long>(GetCurrentThreadId()));
    line(message);
}

#include "insult-query.inc"
#include "rival-query.inc"
#include "vassal-query.inc"
#include "favor-state.inc"
#include "gift-influence-state.inc"
#include "declarewar-query.inc"
#include "peace-context-query.inc"
#include "peace-offer-evaluation-query.inc"
#include "peace-money-query.inc"
#include "peace-war-context-query.inc"
#include "peace-province-candidates.inc"
#include "peace-province-selection.inc"
#include "peace-core-candidates.inc"
#include "peace-subject-candidates.inc"
#include "peace-country-candidates.inc"
#include "peace-annex-selection.inc"
#include "peace-reparations-selection.inc"
#include "peace-selected-rules.inc"
#include "peace-annul-selection.inc"
#include "peace-special-selection.inc"
#include "peace-reparations-state.inc"
#include "peace-wrapper-rule-query.inc"
#include "peace-consequences-query.inc"
#include "peace-empty-offer-query.inc"

static void alliance_query_tick() {
    if (GetFileAttributesW(alliance_query_path)==INVALID_FILE_ATTRIBUTES || !control_ready()) return;
    char wire[1024]{}; DWORD got=0;
    HANDLE file=CreateFileW(alliance_query_path,GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if (file==INVALID_HANDLE_VALUE) return;
    DWORD size=GetFileSize(file,nullptr);
    bool bytes=size<sizeof(wire) && ReadFile(file,wire,size,&got,nullptr) && got==size;
    CloseHandle(file);
    if (!DeleteFileW(alliance_query_path)) return;
    unsigned long long creation=0,expiry=0;
    char id[65]{},action_id[32]{},actor_tag[4]{},recipient_tag[4]{};
    int expected_date=0,consumed=0,insult_id=-1,gift_ducats=0;
    int32_t gift_raw=0,canonical_gift_raw=0;
    char insult_token[16]{};
    char war_cb_key[129]{},war_province_token[16]{},war_beneficiary[4]{};
    int war_province=-1;
    char peace_war_id[30]{};
    char peace_amount_token[16]{};
    int peace_amount=-1;
    char peace_province_token[177]{},peace_province_beneficiary[4]{};
    PeaceProvinceRequest peace_provinces{};
    char peace_direction_token[8]{};
    bool peace_demand=true;
    bool parsed=bytes && sscanf(wire,"EU4DIP_QUERY1 %llx %64s %31s %3s %3s %d %llu%n",
        &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,&consumed)==7
        && strcmp(wire+consumed,"\n")==0;
    bool query2=false;
    bool query3=false;
    bool query4=false;
    bool query5=false;
    bool query6=false;
    bool query7=false;
    bool query8=false;
    bool query9=false;
    bool query10=false;
    bool query11=false;
    bool query12=false;
    bool query13=false;
    bool query14=false;
    bool query15=false;
    bool query16=false;
    bool query17=false;
    bool query18=false;
    bool query19=false;
    bool query20=false;
    bool query21=false;
    char war_call_csv[64]{},war_promise_csv[64]{},war_co_csv[64]{};
    DeclareWarParticipantSelection war_participants{};
    char peace_term_mask[19]{};
    char peace_annul_country[4]{},peace_annul_csv[64]{};
    PeaceAnnulRequest peace_annul{};
    char peace_trade_source[4]{};
    char peace_core_ids[177]{},peace_core_owner[4]{};
    PeaceCoreRequest peace_core{};
    char peace_return_ids[177]{},peace_return_owner[4]{};
    char peace_revoke_ids[177]{},peace_revoke_owner[4]{};
    PeaceCoreRequest peace_return_core{},peace_revoke_core{};
    char peace_subject_target[4]{};
    PeaceSubjectRequest peace_subject{};
    char peace_release_csv[64]{},peace_transfer_csv[64]{};
    PeaceSubjectRequest peace_release_subject{},peace_transfer_subject{};
    bool peace_subject_overlap_invalid=false;
    char peace_release_nation_country[4]{},peace_release_nation_source[4]{};
    char peace_vassal_country[4]{},peace_union_country[4]{},peace_independence_country[4]{};
    char peace_annex_country[4]{},peace_vassal_beneficiary[4]{},peace_union_beneficiary[4]{},peace_annex_beneficiary[4]{};
    PeaceCountryRequest peace_release_nation{},peace_force_vassal{},peace_personal_union{},peace_grant_independence{};
    PeaceCountryRequestSet peace_country_requests{};
    PeaceAnnexRequest peace_annex{};
    if (!parsed && bytes) {
        consumed=0;
        parsed=sscanf(wire,"EU4DIP_QUERY20 %llx %64s %31s %3s %3s %d %llu %d %d%n",
            &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,
            &gift_ducats,&gift_raw,&consumed)==9
            && strcmp(wire+consumed,"\n")==0
            && !strcmp(action_id,"send_gift")
            && gift_influence_amount_valid(gift_ducats,canonical_gift_raw)
            && gift_raw==canonical_gift_raw;
        query20=parsed;
        consumed=0;
    }
    if (!parsed && bytes) {
        consumed=0;
        parsed=sscanf(wire,"EU4DIP_QUERY21 %llx %64s %31s %3s %3s %d %llu%n",
            &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,&consumed)==7
            && strcmp(wire+consumed,"\n")==0
            && !strcmp(action_id,"influence_nation");
        query21=parsed;
        consumed=0;
    }
    if (!parsed && bytes) {
        consumed=0;
        parsed=sscanf(wire,"EU4DIP_QUERY19 %llx %64s %31s %3s %3s %d %llu %128s %15s %3s %63s %63s %63s%n",
            &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,
            war_cb_key,war_province_token,war_beneficiary,war_call_csv,war_promise_csv,war_co_csv,&consumed)==13
            && strcmp(wire+consumed,"\n")==0
            && insult_query_parse_id(war_province_token,war_province)
            && (war_province==-1 || war_province>0)
            && bridge::declarewar_selection::parse_country_tag_csv(war_call_csv,war_participants.call_allies).ok()
            && bridge::declarewar_selection::parse_country_tag_csv(war_promise_csv,war_participants.promise_land_to).ok()
            && bridge::declarewar_selection::parse_country_tag_csv(war_co_csv,war_participants.co_belligerents).ok()
            && bridge::declarewar_selection::validate_participant_selection(war_participants.call_allies,
                war_participants.promise_land_to,war_participants.co_belligerents,actor_tag,recipient_tag).ok();
        for (const char* p=war_cb_key;parsed && *p;++p)
            parsed=(*p>='A' && *p<='Z') || (*p>='a' && *p<='z')
                || (*p>='0' && *p<='9') || *p=='_';
        query19=parsed;
    }
    if (!parsed && bytes) {
        consumed=0;
        parsed=sscanf(wire,"EU4DIP_QUERY2 %llx %64s %31s %3s %3s %d %llu %15s%n",
            &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,insult_token,&consumed)==8
            && strcmp(wire+consumed,"\n")==0;
        parsed=parsed && insult_query_parse_id(insult_token,insult_id);
        query2=parsed;
    }
    if (!parsed && bytes) {
        consumed=0;
        parsed=sscanf(wire,"EU4DIP_QUERY3 %llx %64s %31s %3s %3s %d %llu %128s %15s %3s%n",
            &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,
            war_cb_key,war_province_token,war_beneficiary,&consumed)==10
            && strcmp(wire+consumed,"\n")==0
            && insult_query_parse_id(war_province_token,war_province)
            && (war_province==-1 || war_province>0);
        for (const char* p=war_cb_key;parsed && *p;++p)
            parsed=(*p>='A' && *p<='Z') || (*p>='a' && *p<='z')
                || (*p>='0' && *p<='9') || *p=='_';
        query3=parsed;
    }
    if (!parsed && bytes) {
        consumed=0;
        parsed=sscanf(wire,"EU4DIP_QUERY4 %llx %64s %31s %3s %3s %d %llu %29s%n",
            &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,
            peace_war_id,&consumed)==8 && strcmp(wire+consumed,"\n")==0;
        query4=parsed;
    }
    if (!parsed && bytes) {
        consumed=0;
        parsed=sscanf(wire,"EU4DIP_QUERY5 %llx %64s %31s %3s %3s %d %llu %29s %15s%n",
            &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,
            peace_war_id,peace_amount_token,&consumed)==9 && strcmp(wire+consumed,"\n")==0
            && insult_query_parse_id(peace_amount_token,peace_amount)
            && peace_amount>0 && peace_amount%100==0;
        query5=parsed;
    }
    if (!parsed && bytes) {
        consumed=0;
        parsed=sscanf(wire,"EU4DIP_QUERY6 %llx %64s %31s %3s %3s %d %llu %29s %176s %3s%n",
            &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,
            peace_war_id,peace_province_token,peace_province_beneficiary,&consumed)==10
            && strcmp(wire+consumed,"\n")==0
            && peace_province_parse_request(peace_province_token,
                peace_province_beneficiary,peace_provinces);
        query6=parsed;
    }
    if (!parsed && bytes) {
        consumed=0;
        peace_amount=-1;
        parsed=sscanf(wire,"EU4DIP_QUERY7 %llx %64s %31s %3s %3s %d %llu %29s %7s %15s %176s %3s%n",
            &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,
            peace_war_id,peace_direction_token,peace_amount_token,
            peace_province_token,peace_province_beneficiary,&consumed)==12
            && strcmp(wire+consumed,"\n")==0
            && (!strcmp(peace_direction_token,"demand")
                || !strcmp(peace_direction_token,"offer"))
            && insult_query_parse_id(peace_amount_token,peace_amount)
            && (peace_amount==-1 || (peace_amount>0 && peace_amount%100==0))
            && peace_province_parse_request(peace_province_token,
                peace_province_beneficiary,peace_provinces);
        query7=parsed;
        peace_demand=!strcmp(peace_direction_token,"demand");
    }
    if (!parsed && bytes) {
        consumed=0; peace_amount=-1;
        parsed=sscanf(wire,"EU4DIP_QUERY8 %llx %64s %31s %3s %3s %d %llu %29s %7s %15s %176s %3s %3s%n",
            &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,
            peace_war_id,peace_direction_token,peace_amount_token,
            peace_province_token,peace_province_beneficiary,peace_term_mask,&consumed)==13
            && !strcmp(wire+consumed,"\n")
            && (!strcmp(peace_direction_token,"demand") || !strcmp(peace_direction_token,"offer"))
            && insult_query_parse_id(peace_amount_token,peace_amount)
            && (peace_amount==-1 || (peace_amount>0 && peace_amount%100==0))
            && peace_province_parse_request(peace_province_token,peace_province_beneficiary,peace_provinces)
            && (!strcmp(peace_term_mask,"r") || !strcmp(peace_term_mask,"mr")
                || !strcmp(peace_term_mask,"pr") || !strcmp(peace_term_mask,"mpr"))
            && ((strchr(peace_term_mask,'m')!=nullptr)==(peace_amount>0))
            && ((strchr(peace_term_mask,'p')!=nullptr)==(peace_provinces.count>0));
        query8=parsed; peace_demand=!strcmp(peace_direction_token,"demand");
    }
    if (!parsed && bytes) {
        consumed=0; peace_amount=-1;
        parsed=sscanf(wire,"EU4DIP_QUERY9 %llx %64s %31s %3s %3s %d %llu %29s %7s %15s %176s %3s %4s%n",
            &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,
            peace_war_id,peace_direction_token,peace_amount_token,
            peace_province_token,peace_province_beneficiary,peace_term_mask,&consumed)==13
            && !strcmp(wire+consumed,"\n")
            && (!strcmp(peace_direction_token,"demand") || !strcmp(peace_direction_token,"offer"))
            && insult_query_parse_id(peace_amount_token,peace_amount)
            && (peace_amount==-1 || (peace_amount>0 && peace_amount%100==0))
            && peace_province_parse_request(peace_province_token,peace_province_beneficiary,peace_provinces)
            && (!strcmp(peace_term_mask,"t") || !strcmp(peace_term_mask,"mt")
                || !strcmp(peace_term_mask,"pt") || !strcmp(peace_term_mask,"rt")
                || !strcmp(peace_term_mask,"mpt") || !strcmp(peace_term_mask,"mrt")
                || !strcmp(peace_term_mask,"prt") || !strcmp(peace_term_mask,"mprt"))
            && ((strchr(peace_term_mask,'m')!=nullptr)==(peace_amount>0))
            && ((strchr(peace_term_mask,'p')!=nullptr)==(peace_provinces.count>0));
        query9=parsed; peace_demand=!strcmp(peace_direction_token,"demand");
    }
    if (!parsed && bytes) {
        consumed=0; peace_amount=-1;
        parsed=sscanf(wire,"EU4DIP_QUERY10 %llx %64s %31s %3s %3s %d %llu %29s %7s %15s %176s %3s %4s %3s%n",
            &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,
            peace_war_id,peace_direction_token,peace_amount_token,
            peace_province_token,peace_province_beneficiary,peace_term_mask,peace_trade_source,&consumed)==14
            && !strcmp(wire+consumed,"\n")
            && (!strcmp(peace_direction_token,"demand") || !strcmp(peace_direction_token,"offer"))
            && insult_query_parse_id(peace_amount_token,peace_amount)
            && (peace_amount==-1 || (peace_amount>0 && peace_amount%100==0))
            && peace_province_parse_request(peace_province_token,peace_province_beneficiary,peace_provinces)
            && (!strcmp(peace_term_mask,"t") || !strcmp(peace_term_mask,"mt")
                || !strcmp(peace_term_mask,"pt") || !strcmp(peace_term_mask,"rt")
                || !strcmp(peace_term_mask,"mpt") || !strcmp(peace_term_mask,"mrt")
                || !strcmp(peace_term_mask,"prt") || !strcmp(peace_term_mask,"mprt"))
            && ((strchr(peace_term_mask,'m')!=nullptr)==(peace_amount>0))
            && ((strchr(peace_term_mask,'p')!=nullptr)==(peace_provinces.count>0));
        if (parsed && strcmp(peace_trade_source,"-")) {
            parsed=strlen(peace_trade_source)==3;
            for (const char* p=peace_trade_source;parsed && *p;++p)
                parsed=(*p>='A' && *p<='Z') || (*p>='0' && *p<='9');
            const char* beneficiary=!strcmp(peace_direction_token,"demand")?actor_tag:recipient_tag;
            parsed=parsed && strcmp(peace_trade_source,beneficiary);
        } else if (parsed) {
            parsed=!strcmp(action_id,"transfer_trade_power") && !strcmp(peace_term_mask,"t")
                && peace_amount==-1 && peace_provinces.count==0;
        }
        query10=parsed; peace_demand=!strcmp(peace_direction_token,"demand");
    }
    if (!parsed && bytes) {
        consumed=0; peace_amount=-1;
        parsed=sscanf(wire,"EU4DIP_QUERY11 %llx %64s %31s %3s %3s %d %llu %29s %7s %15s %176s %3s %5s %3s%n",
            &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,
            peace_war_id,peace_direction_token,peace_amount_token,
            peace_province_token,peace_province_beneficiary,peace_term_mask,peace_trade_source,&consumed)==14
            && !strcmp(wire+consumed,"\n")
            && (!strcmp(peace_direction_token,"demand") || !strcmp(peace_direction_token,"offer"))
            && insult_query_parse_id(peace_amount_token,peace_amount)
            && (peace_amount==-1 || (peace_amount>0 && peace_amount%100==0))
            && peace_province_parse_request(peace_province_token,peace_province_beneficiary,peace_provinces)
            && strchr(peace_term_mask,'c');
        const char* order="mprtc"; int previous=-1;
        for (const char* p=peace_term_mask;parsed && *p;++p) {
            const char* position=strchr(order,*p);
            if (!position || position-order<=previous) parsed=false;
            else previous=static_cast<int>(position-order);
        }
        parsed=parsed && (static_cast<bool>(strchr(peace_term_mask,'m'))==(peace_amount>0))
            && (static_cast<bool>(strchr(peace_term_mask,'p'))==(peace_provinces.count>0));
        if (parsed && strchr(peace_term_mask,'t')) {
            parsed=strlen(peace_trade_source)==3;
            for (const char* p=peace_trade_source;parsed && *p;++p)
                parsed=(*p>='A' && *p<='Z') || (*p>='0' && *p<='9');
            parsed=parsed && strcmp(peace_trade_source,
                !strcmp(peace_direction_token,"demand")?actor_tag:recipient_tag);
        } else if (parsed) parsed=!strcmp(peace_trade_source,"-");
        query11=parsed; peace_demand=!strcmp(peace_direction_token,"demand");
    }
    if (!parsed && bytes) {
        consumed=0; peace_amount=-1;
        parsed=sscanf(wire,"EU4DIP_QUERY12 %llx %64s %31s %3s %3s %d %llu %29s %7s %15s %176s %3s %6s %3s %3s %63s%n",
            &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,
            peace_war_id,peace_direction_token,peace_amount_token,peace_province_token,
            peace_province_beneficiary,peace_term_mask,peace_trade_source,peace_annul_country,
            peace_annul_csv,&consumed)==16 && !strcmp(wire+consumed,"\n")
            && (!strcmp(peace_direction_token,"demand") || !strcmp(peace_direction_token,"offer"))
            && insult_query_parse_id(peace_amount_token,peace_amount)
            && (peace_amount==-1 || (peace_amount>0 && peace_amount%100==0))
            && peace_province_parse_request(peace_province_token,peace_province_beneficiary,peace_provinces)
            && strchr(peace_term_mask,'a')
            && peace_annul_parse_request(peace_annul_country,peace_annul_csv,peace_annul);
        const char* order="mprtca";int previous=-1;
        for (const char* p=peace_term_mask;parsed && *p;++p) {
            const char* pos=strchr(order,*p);
            if (!pos || pos-order<=previous) parsed=false;
            else previous=static_cast<int>(pos-order);
        }
        parsed=parsed && (static_cast<bool>(strchr(peace_term_mask,'m'))==(peace_amount>0))
            && (static_cast<bool>(strchr(peace_term_mask,'p'))==(peace_provinces.count>0));
        if (parsed && strchr(peace_term_mask,'t')) {
            parsed=bridge::peace_execution_wire::detail::valid_canonical_tag(
                {peace_trade_source,strlen(peace_trade_source)})
                && strcmp(peace_trade_source,!strcmp(peace_direction_token,"demand")?actor_tag:recipient_tag);
        } else if (parsed) parsed=!strcmp(peace_trade_source,"-");
        if (parsed && !peace_annul.count)
            parsed=!strcmp(action_id,"annul_treaties") && !strcmp(peace_term_mask,"a");
        query12=parsed;peace_demand=!strcmp(peace_direction_token,"demand");
    }
    if (!parsed && bytes) {
        consumed=0; peace_amount=-1;
        parsed=sscanf(wire,"EU4DIP_QUERY13 %llx %64s %31s %3s %3s %d %llu %29s %7s %15s %176s %3s %9s %3s %3s %63s%n",
            &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,
            peace_war_id,peace_direction_token,peace_amount_token,peace_province_token,
            peace_province_beneficiary,peace_term_mask,peace_trade_source,peace_annul_country,
            peace_annul_csv,&consumed)==16 && !strcmp(wire+consumed,"\n")
            && (!strcmp(peace_direction_token,"demand") || !strcmp(peace_direction_token,"offer"))
            && insult_query_parse_id(peace_amount_token,peace_amount)
            && (peace_amount==-1 || (peace_amount>0 && peace_amount%100==0))
            && peace_province_parse_request(peace_province_token,peace_province_beneficiary,peace_provinces)
            && (strchr(peace_term_mask,'h') || strchr(peace_term_mask,'s') || strchr(peace_term_mask,'f'))
            && peace_annul_parse_request(peace_annul_country,peace_annul_csv,peace_annul);
        if (parsed) {
            const char* cursor="mprtcahsf";
            for (const char* bit=peace_term_mask;parsed && *bit;++bit) {
                const char* found=strchr(cursor,*bit);
                if (!found) parsed=false;
                else cursor=found+1;
            }
            parsed=parsed && ((strchr(peace_term_mask,'m')!=nullptr)==(peace_amount>0))
                && ((strchr(peace_term_mask,'p')!=nullptr)==(peace_provinces.count>0))
                && ((strchr(peace_term_mask,'a')!=nullptr)==(peace_annul.count>0));
        }
        if (parsed && strchr(peace_term_mask,'t')) {
            parsed=bridge::peace_execution_wire::detail::valid_canonical_tag(
                {peace_trade_source,strlen(peace_trade_source)})
                && strcmp(peace_trade_source,!strcmp(peace_direction_token,"demand")?actor_tag:recipient_tag);
        } else if (parsed) parsed=!strcmp(peace_trade_source,"-");
        if (parsed && !strchr(peace_term_mask,'a'))
            parsed=!strcmp(peace_annul_country,"-") && !strcmp(peace_annul_csv,"-");
        query13=parsed; peace_demand=!strcmp(peace_direction_token,"demand");
    }
    if (!parsed && bytes) {
        consumed=0;
        parsed=sscanf(wire,"EU4DIP_QUERY14 %llx %64s %31s %3s %3s %d %llu %29s %7s %176s %3s%n",
            &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,
            peace_war_id,peace_direction_token,peace_core_ids,peace_core_owner,&consumed)==11
            && !strcmp(wire+consumed,"\n")
            && (!strcmp(peace_direction_token,"demand") || !strcmp(peace_direction_token,"offer"))
            && peace_core_parse_request(peace_core_ids,peace_core_owner,peace_core);
        if (parsed) {
            peace_core.return_core=!strcmp(action_id,"return_core");
            parsed=peace_core.return_core || !strcmp(action_id,"revoke_core");
        }
        query14=parsed; peace_demand=!strcmp(peace_direction_token,"demand");
    }
    if (!parsed && bytes) {
        consumed=0; peace_amount=-1;
        parsed=sscanf(wire,"EU4DIP_QUERY15 %llx %64s %31s %3s %3s %d %llu %29s %7s %15s %176s %3s %11s %3s %3s %63s %176s %3s %176s %3s%n",
            &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,
            peace_war_id,peace_direction_token,peace_amount_token,peace_province_token,
            peace_province_beneficiary,peace_term_mask,peace_trade_source,
            peace_annul_country,peace_annul_csv,peace_return_ids,peace_return_owner,
            peace_revoke_ids,peace_revoke_owner,&consumed)==20
            && !strcmp(wire+consumed,"\n")
            && (!strcmp(peace_direction_token,"demand") || !strcmp(peace_direction_token,"offer"))
            && insult_query_parse_id(peace_amount_token,peace_amount)
            && (peace_amount==-1 || (peace_amount>0 && peace_amount%100==0))
            && peace_province_parse_request(peace_province_token,
                peace_province_beneficiary,peace_provinces)
            && peace_core_parse_request(peace_return_ids,peace_return_owner,
                peace_return_core)
            && peace_core_parse_request(peace_revoke_ids,peace_revoke_owner,
                peace_revoke_core)
            && (strchr(peace_term_mask,'b') || strchr(peace_term_mask,'v'));
        if (parsed) {
            const char* order="mprtcahsfbv"; int previous=-1;
            for (const char* bit=peace_term_mask;parsed && *bit;++bit) {
                const char* found=strchr(order,*bit);
                if (!found || found-order<=previous) parsed=false;
                else previous=static_cast<int>(found-order);
            }
            parsed=parsed
                && ((strchr(peace_term_mask,'m')!=nullptr)==(peace_amount>0))
                && ((strchr(peace_term_mask,'p')!=nullptr)==(peace_provinces.count>0));
            if (parsed && strchr(peace_term_mask,'t')) {
                parsed=bridge::peace_execution_wire::detail::valid_canonical_tag(
                    {peace_trade_source,strlen(peace_trade_source)})
                    && strcmp(peace_trade_source,
                        !strcmp(peace_direction_token,"demand")?actor_tag:recipient_tag);
            } else if (parsed) parsed=!strcmp(peace_trade_source,"-");
            if (parsed && strchr(peace_term_mask,'a'))
                parsed=peace_annul_parse_request(peace_annul_country,peace_annul_csv,
                    peace_annul);
            else if (parsed)
                parsed=!strcmp(peace_annul_country,"-") && !strcmp(peace_annul_csv,"-");
            peace_return_core.return_core=true;
            peace_revoke_core.return_core=false;
        }
        query15=parsed; peace_demand=!strcmp(peace_direction_token,"demand");
    }
    if (!parsed && bytes) {
        consumed=0;
        parsed=sscanf(wire,"EU4DIP_QUERY16 %llx %64s %31s %3s %3s %d %llu %29s %7s %3s%n",
            &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,
            peace_war_id,peace_direction_token,peace_subject_target,&consumed)==10
            && !strcmp(wire+consumed,"\n")
            && (!strcmp(peace_direction_token,"demand") || !strcmp(peace_direction_token,"offer"))
            && peace_subject_parse_request(peace_subject_target,
                !strcmp(action_id,"release_subject"),peace_subject);
        query16=parsed; peace_demand=!strcmp(peace_direction_token,"demand");
    }
    if (!parsed && bytes) {
        consumed=0; peace_amount=-1;
        parsed=sscanf(wire,"EU4DIP_QUERY17 %llx %64s %31s %3s %3s %d %llu %29s %7s %15s %176s %3s %13s %3s %3s %63s %176s %3s %176s %3s %63s %63s%n",
            &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,
            peace_war_id,peace_direction_token,peace_amount_token,peace_province_token,
            peace_province_beneficiary,peace_term_mask,peace_trade_source,
            peace_annul_country,peace_annul_csv,peace_return_ids,peace_return_owner,
            peace_revoke_ids,peace_revoke_owner,peace_release_csv,peace_transfer_csv,
            &consumed)==22
            && !strcmp(wire+consumed,"\n")
            && (!strcmp(peace_direction_token,"demand") || !strcmp(peace_direction_token,"offer"))
            && insult_query_parse_id(peace_amount_token,peace_amount)
            && (peace_amount==-1 || (peace_amount>0 && peace_amount%100==0))
            && peace_province_parse_request(peace_province_token,
                peace_province_beneficiary,peace_provinces)
            && peace_core_parse_request(peace_return_ids,peace_return_owner,
                peace_return_core)
            && peace_core_parse_request(peace_revoke_ids,peace_revoke_owner,
                peace_revoke_core);
        if (parsed) {
            const char* order="mprtcahsfbvlx"; int previous=-1;
            for (const char* bit=peace_term_mask;parsed && *bit;++bit) {
                const char* found=strchr(order,*bit);
                if (!found || found-order<=previous) parsed=false;
                else previous=static_cast<int>(found-order);
            }
            parsed=parsed
                && ((strchr(peace_term_mask,'m')!=nullptr)==(peace_amount>0))
                && ((strchr(peace_term_mask,'p')!=nullptr)==(peace_provinces.count>0))
                && (strchr(peace_term_mask,'l') || strchr(peace_term_mask,'x'));
            if (parsed && strchr(peace_term_mask,'t')) {
                parsed=bridge::peace_execution_wire::detail::valid_canonical_tag(
                    {peace_trade_source,strlen(peace_trade_source)})
                    && strcmp(peace_trade_source,
                        !strcmp(peace_direction_token,"demand")?actor_tag:recipient_tag);
            } else if (parsed) parsed=!strcmp(peace_trade_source,"-");
            if (parsed && strchr(peace_term_mask,'a'))
                parsed=peace_annul_parse_request(peace_annul_country,peace_annul_csv,
                    peace_annul);
            else if (parsed)
                parsed=!strcmp(peace_annul_country,"-") && !strcmp(peace_annul_csv,"-");
            peace_return_core.return_core=true;
            peace_revoke_core.return_core=false;
            if (parsed && strchr(peace_term_mask,'l'))
                parsed=peace_subject_parse_countries(peace_release_csv,true,
                    peace_release_subject);
            else if (parsed) parsed=!strcmp(peace_release_csv,"-");
            if (parsed && strchr(peace_term_mask,'x'))
                parsed=peace_subject_parse_countries(peace_transfer_csv,false,
                    peace_transfer_subject);
            else if (parsed) parsed=!strcmp(peace_transfer_csv,"-");
            if (parsed && peace_release_subject.selection_requested
                && peace_transfer_subject.selection_requested)
                for (unsigned i=0;i<peace_release_subject.country_count && parsed;++i)
                    for (unsigned j=0;j<peace_transfer_subject.country_count;++j)
                        if (!strcmp(peace_release_subject.countries[i],
                            peace_transfer_subject.countries[j])) {
                            peace_subject_overlap_invalid=true; break;
                        }
        }
        query17=parsed; peace_demand=!strcmp(peace_direction_token,"demand");
    }
    if (!parsed && bytes) {
        consumed=0; peace_amount=-1;
        parsed=sscanf(wire,"EU4DIP_QUERY18 %llx %64s %31s %3s %3s %d %llu %29s %7s %15s %176s %3s %18s %3s %3s %63s %176s %3s %176s %3s %63s %63s %3s %3s %3s %3s %3s %3s %3s %3s %3s%n",
            &creation,id,action_id,actor_tag,recipient_tag,&expected_date,&expiry,
            peace_war_id,peace_direction_token,peace_amount_token,peace_province_token,
            peace_province_beneficiary,peace_term_mask,peace_trade_source,
            peace_annul_country,peace_annul_csv,peace_return_ids,peace_return_owner,
            peace_revoke_ids,peace_revoke_owner,peace_release_csv,peace_transfer_csv,
            peace_release_nation_country,peace_release_nation_source,
            peace_vassal_country,peace_union_country,peace_independence_country,
            peace_annex_country,peace_vassal_beneficiary,peace_union_beneficiary,
            peace_annex_beneficiary,&consumed)==31
            && !strcmp(wire+consumed,"\n")
            && (!strcmp(peace_direction_token,"demand") || !strcmp(peace_direction_token,"offer"))
            && insult_query_parse_id(peace_amount_token,peace_amount)
            && peace_province_parse_request(peace_province_token,
                peace_province_beneficiary,peace_provinces)
            && peace_core_parse_request(peace_return_ids,peace_return_owner,
                peace_return_core)
            && peace_core_parse_request(peace_revoke_ids,peace_revoke_owner,
                peace_revoke_core);
        if (parsed) {
            const char* order="mprtcahsfbvlxnzuie"; int previous=-1;
            bool old_bit=false,new_bit=false;
            unsigned new_count=0;
            for (const char* bit=peace_term_mask;parsed && *bit;++bit) {
                const char* found=strchr(order,*bit);
                if (!found || found-order<=previous) parsed=false;
                else {
                    previous=static_cast<int>(found-order);
                    // Country offers can carry the established money setter.
                    // Other legacy families remain on their own query paths.
                    if (strchr("prtcahsfbvlx",*bit)) old_bit=true;
                    if (strchr("nzuie",*bit)) { new_bit=true; ++new_count; }
                }
            }
            parsed=parsed && new_bit && !old_bit;
            const bool money_bit=strchr(peace_term_mask,'m')!=nullptr;
            parsed=parsed && (money_bit?(peace_amount>0 && peace_amount%100==0):peace_amount==-1)
                && peace_provinces.count==0
                && !strcmp(peace_trade_source,"-")
                && !strcmp(peace_annul_country,"-") && !strcmp(peace_annul_csv,"-")
                && !strcmp(peace_return_ids,"-") && !strcmp(peace_return_owner,"-")
                && !strcmp(peace_revoke_ids,"-") && !strcmp(peace_revoke_owner,"-")
                && !strcmp(peace_release_csv,"-") && !strcmp(peace_transfer_csv,"-");

            const bool release_bit=strchr(peace_term_mask,'n')!=nullptr;
            const bool vassal_bit=strchr(peace_term_mask,'z')!=nullptr;
            const bool union_bit=strchr(peace_term_mask,'u')!=nullptr;
            const bool grant_bit=strchr(peace_term_mask,'i')!=nullptr;
            const bool annex_bit=strchr(peace_term_mask,'e')!=nullptr;
            if (parsed && release_bit)
                parsed=peace_country_parse_request(PeaceCountryKind::release_nation,
                    peace_release_nation_country,peace_release_nation_source,
                    strcmp(peace_release_nation_country,"-")!=0,
                    peace_release_nation);
            else if (parsed)
                parsed=!strcmp(peace_release_nation_country,"-")
                    && !strcmp(peace_release_nation_source,"-");
            if (parsed && vassal_bit) {
                const bool selected=strcmp(peace_vassal_country,"-")!=0;
                parsed=peace_country_parse_request(PeaceCountryKind::force_vassal,
                    peace_vassal_country,"-",selected,peace_force_vassal)
                    && ((selected && strcmp(peace_vassal_beneficiary,"-")!=0)
                        || (!selected && !strcmp(peace_vassal_beneficiary,"-")));
                if (parsed && selected)
                    parsed=peace_country_valid_tag(peace_vassal_beneficiary);
            } else if (parsed)
                parsed=!strcmp(peace_vassal_country,"-")
                    && !strcmp(peace_vassal_beneficiary,"-");
            if (parsed && union_bit) {
                const bool selected=strcmp(peace_union_country,"-")!=0;
                parsed=peace_country_parse_request(PeaceCountryKind::pu,
                    peace_union_country,"-",selected,peace_personal_union)
                    && ((selected && strcmp(peace_union_beneficiary,"-")!=0)
                        || (!selected && !strcmp(peace_union_beneficiary,"-")));
                if (parsed && selected)
                    parsed=peace_country_valid_tag(peace_union_beneficiary);
            } else if (parsed)
                parsed=!strcmp(peace_union_country,"-")
                    && !strcmp(peace_union_beneficiary,"-");
            if (parsed && grant_bit)
                parsed=peace_country_parse_request(PeaceCountryKind::grant_independence,
                    peace_independence_country,"-",
                    strcmp(peace_independence_country,"-")!=0,
                    peace_grant_independence);
            else if (parsed) parsed=!strcmp(peace_independence_country,"-");
            if (parsed && annex_bit) {
                if (!strcmp(peace_annex_country,"-")) {
                    parsed=!strcmp(peace_annex_beneficiary,"-");
                } else {
                    parsed=peace_annex_parse_request(peace_annex_country,
                        peace_annex_beneficiary,true,peace_annex);
                }
            } else if (parsed) {
                parsed=!strcmp(peace_annex_country,"-")
                    && !strcmp(peace_annex_beneficiary,"-");
            }
            const bool discovery=(release_bit && !peace_release_nation.selection_requested)
                || (vassal_bit && !peace_force_vassal.selection_requested)
                || (union_bit && !peace_personal_union.selection_requested)
                || (grant_bit && !peace_grant_independence.selection_requested)
                || (annex_bit && !peace_annex.country[0]);
            const bool selected=(release_bit && peace_release_nation.selection_requested)
                || (vassal_bit && peace_force_vassal.selection_requested)
                || (union_bit && peace_personal_union.selection_requested)
                || (grant_bit && peace_grant_independence.selection_requested)
                || (annex_bit && peace_annex.country[0]);
            // One wire cannot combine a discovery family with a selected
            // family.  Multiple selected families are retained for the
            // aggregate wrapper, while discovery remains one-family-only so
            // the primary action is unambiguous.
            parsed=parsed && !(discovery && selected)
                && (!discovery || (new_count==1u && !money_bit));
            peace_country_requests.release_nation=release_bit?&peace_release_nation:nullptr;
            peace_country_requests.force_vassal=vassal_bit?&peace_force_vassal:nullptr;
            peace_country_requests.pu=union_bit?&peace_personal_union:nullptr;
            peace_country_requests.grant_independence=grant_bit?&peace_grant_independence:nullptr;
            peace_country_requests.force_vassal_beneficiary=vassal_bit?peace_vassal_beneficiary:nullptr;
            peace_country_requests.pu_beneficiary=union_bit?peace_union_beneficiary:nullptr;
        }
        query18=parsed; peace_demand=!strcmp(peace_direction_token,"demand");
    }
    bool identifier=parsed && id[0];
    for (const char* p=id;identifier && *p;++p)
        identifier=(*p>='A' && *p<='Z') || (*p>='a' && *p<='z') || (*p>='0' && *p<='9') || *p=='_' || *p=='-';
    if (!parsed || !identifier) { alliance_query_failure("invalid","QUERY_WIRE_INVALID"); return; }
    if (creation!=observation_creation) { alliance_query_failure(id,"QUERY_SESSION_CHANGED"); return; }
    uint64_t now=alliance_query_clock();
    if (now>expiry) { alliance_query_failure(id,"QUERY_EXPIRED"); return; }
    if (expiry-now>600000000) { alliance_query_failure(id,"QUERY_EXPIRY_OUT_OF_RANGE"); return; }
    unsigned free_slot=128;
    for (unsigned i=0;i<128;++i) {
        if (alliance_query_expiries[i]<now) alliance_query_ids[i][0]=0;
        if (!alliance_query_ids[i][0]) { if (free_slot==128) free_slot=i; }
        else if (strcmp(id,alliance_query_ids[i])==0) { alliance_query_failure(id,"QUERY_ID_DUPLICATE"); return; }
    }
    if (free_slot==128) { alliance_query_failure(id,"QUERY_ID_CAPACITY_EXHAUSTED"); return; }
    strcpy(alliance_query_ids[free_slot],id); alliance_query_expiries[free_slot]=expiry;
    bool marriage=strcmp(action_id,"offer_royal_marriage")==0 || strcmp(action_id,"break_royal_ties")==0;
    const bool support=strcmp(action_id,"support_independence")==0 || strcmp(action_id,"revoke_support_independence")==0;
    const bool military=strcmp(action_id,"ask_military_access")==0 || strcmp(action_id,"cancel_military_access")==0;
    const bool vassal=strcmp(action_id,"offer_vassalization")==0 || strcmp(action_id,"cancel_vassalization")==0;
    const bool insult=strcmp(action_id,"send_insult")==0 || strcmp(action_id,"scornful_insult")==0;
    const bool rival=strcmp(action_id,"set_rival")==0 || strcmp(action_id,"remove_rival")==0;
    const bool declarewar=strcmp(action_id,"declare_war")==0;
    const bool peace=peace_query_action(action_id);
    const bool country_action=strcmp(action_id,"release_nation")==0
        || strcmp(action_id,"force_vassalization")==0
        || strcmp(action_id,"form_personal_union")==0
        || strcmp(action_id,"grant_independence")==0
        || strcmp(action_id,"full_annexation")==0;
    if (query4 && strcmp(action_id,"white_peace")) {
        alliance_query_failure(id,"QUERY_PEACE_EMPTY_OFFER_ACTION_REQUIRED"); return;
    }
    if (query5 && strcmp(action_id,"demand_ducats")) {
        alliance_query_failure(id,"QUERY_PEACE_MONEY_ACTION_REQUIRED"); return;
    }
    if (query6 && strcmp(action_id,"cede_province")) {
        alliance_query_failure(id,"QUERY_PEACE_PROVINCE_ACTION_REQUIRED"); return;
    }
    if (query7 && (!peace || (strcmp(action_id,"white_peace")
            && strcmp(action_id,"demand_ducats")
            && strcmp(action_id,"cede_province")))) {
        alliance_query_failure(id,"QUERY_PEACE_QUERY_ACTION_REQUIRED"); return;
    }
    if (query8 && (!peace || (strcmp(action_id,"war_reparations")
            && strcmp(action_id,"demand_ducats") && strcmp(action_id,"cede_province")))) {
        alliance_query_failure(id,"QUERY_PEACE_QUERY_ACTION_REQUIRED"); return;
    }
    if (query8 && ((!strcmp(action_id,"demand_ducats") && peace_amount<0)
        || (!strcmp(action_id,"cede_province") && !peace_provinces.count))) {
        alliance_query_failure(id,"QUERY_PEACE_QUERY_PARAMETERS_INVALID"); return;
    }
    if ((query9 || query10 || query11 || query12 || query13) && (!peace || (strcmp(action_id,"transfer_trade_power")
            && strcmp(action_id,"war_reparations")
            && strcmp(action_id,"demand_ducats") && strcmp(action_id,"cede_province")
            && !((query11 || query12 || query13) && !strcmp(action_id,"concede_defeat"))
            && !((query12 || query13) && !strcmp(action_id,"annul_treaties"))
            && !(query13 && (!strcmp(action_id,"humiliate_rival") || !strcmp(action_id,"show_strength") || !strcmp(action_id,"force_religion")))))) {
        alliance_query_failure(id,"QUERY_PEACE_QUERY_ACTION_REQUIRED"); return;
    }
    if (query14 && (!peace || (strcmp(action_id,"return_core")
            && strcmp(action_id,"revoke_core")))) {
        alliance_query_failure(id,"QUERY_PEACE_CORE_QUERY_ACTION_REQUIRED"); return;
    }
    if (query15 && (!peace || (strcmp(action_id,"transfer_trade_power")
            && strcmp(action_id,"war_reparations")
            && strcmp(action_id,"demand_ducats") && strcmp(action_id,"cede_province")
            && strcmp(action_id,"concede_defeat") && strcmp(action_id,"annul_treaties")
            && strcmp(action_id,"humiliate_rival") && strcmp(action_id,"show_strength")
            && strcmp(action_id,"force_religion") && strcmp(action_id,"return_core")
            && strcmp(action_id,"revoke_core")))) {
        alliance_query_failure(id,"QUERY_PEACE_COMBINED_CORE_QUERY_ACTION_REQUIRED"); return;
    }
    if (query16 && (!peace || (strcmp(action_id,"release_subject")
            && strcmp(action_id,"transfer_subject")))) {
        alliance_query_failure(id,"QUERY_PEACE_SUBJECT_QUERY_ACTION_REQUIRED"); return;
    }
    if (query17 && (!peace || (strcmp(action_id,"transfer_trade_power")
            && strcmp(action_id,"war_reparations")
            && strcmp(action_id,"demand_ducats") && strcmp(action_id,"cede_province")
            && strcmp(action_id,"concede_defeat") && strcmp(action_id,"annul_treaties")
            && strcmp(action_id,"humiliate_rival") && strcmp(action_id,"show_strength")
            && strcmp(action_id,"force_religion") && strcmp(action_id,"return_core")
            && strcmp(action_id,"revoke_core") && strcmp(action_id,"release_subject")
            && strcmp(action_id,"transfer_subject")))) {
        alliance_query_failure(id,"QUERY_PEACE_COMBINED_SUBJECT_QUERY_ACTION_REQUIRED"); return;
    }
    if (query18 && !country_action) {
        alliance_query_failure(id,"QUERY_PEACE_COMBINED_COUNTRY_QUERY_ACTION_REQUIRED"); return;
    }
    if (query18 && ((strcmp(action_id,"release_nation")==0
            && !strchr(peace_term_mask,'n'))
        || (strcmp(action_id,"force_vassalization")==0
            && !strchr(peace_term_mask,'z'))
        || (strcmp(action_id,"form_personal_union")==0
            && !strchr(peace_term_mask,'u'))
        || (strcmp(action_id,"grant_independence")==0
            && !strchr(peace_term_mask,'i'))
        || (strcmp(action_id,"full_annexation")==0
            && !strchr(peace_term_mask,'e')))) {
        alliance_query_failure(id,"QUERY_PEACE_COMBINED_COUNTRY_QUERY_PARAMETERS_INVALID"); return;
    }
    if (query17 && peace_subject_overlap_invalid) {
        alliance_query_failure(id,"QUERY_PEACE_SUBJECT_COUNTRY_OVERLAP"); return;
    }
    if ((query9 || query10 || query11 || query12 || query13) && ((!strcmp(action_id,"war_reparations") && !strchr(peace_term_mask,'r'))
        || (!strcmp(action_id,"demand_ducats") && peace_amount<0)
        || (!strcmp(action_id,"cede_province") && !peace_provinces.count)
        || (!strcmp(action_id,"transfer_trade_power") && !strchr(peace_term_mask,'t'))
        || (!strcmp(action_id,"concede_defeat") && !strchr(peace_term_mask,'c'))
        || (!strcmp(action_id,"annul_treaties") && !strchr(peace_term_mask,'a'))
        || (!strcmp(action_id,"humiliate_rival") && !strchr(peace_term_mask,'h'))
        || (!strcmp(action_id,"show_strength") && !strchr(peace_term_mask,'s'))
        || (!strcmp(action_id,"force_religion") && !strchr(peace_term_mask,'f')))) {
        alliance_query_failure(id,"QUERY_PEACE_QUERY_PARAMETERS_INVALID"); return;
    }
    if (query15 && ((!strcmp(action_id,"war_reparations") && !strchr(peace_term_mask,'r'))
        || (!strcmp(action_id,"demand_ducats") && (peace_amount<0 || !strchr(peace_term_mask,'m')))
        || (!strcmp(action_id,"cede_province") && (!peace_provinces.count || !strchr(peace_term_mask,'p')))
        || (!strcmp(action_id,"transfer_trade_power") && !strchr(peace_term_mask,'t'))
        || (!strcmp(action_id,"concede_defeat") && !strchr(peace_term_mask,'c'))
        || (!strcmp(action_id,"annul_treaties") && !strchr(peace_term_mask,'a'))
        || (!strcmp(action_id,"humiliate_rival") && !strchr(peace_term_mask,'h'))
        || (!strcmp(action_id,"show_strength") && !strchr(peace_term_mask,'s'))
        || (!strcmp(action_id,"force_religion") && !strchr(peace_term_mask,'f'))
        || (!strcmp(action_id,"return_core") && !strchr(peace_term_mask,'b'))
        || (!strcmp(action_id,"revoke_core") && !strchr(peace_term_mask,'v')))) {
        alliance_query_failure(id,"QUERY_PEACE_COMBINED_CORE_QUERY_PARAMETERS_INVALID"); return;
    }
    if (query17 && ((!strcmp(action_id,"war_reparations") && !strchr(peace_term_mask,'r'))
        || (!strcmp(action_id,"demand_ducats") && (peace_amount<0 || !strchr(peace_term_mask,'m')))
        || (!strcmp(action_id,"cede_province") && (!peace_provinces.count || !strchr(peace_term_mask,'p')))
        || (!strcmp(action_id,"transfer_trade_power") && !strchr(peace_term_mask,'t'))
        || (!strcmp(action_id,"concede_defeat") && !strchr(peace_term_mask,'c'))
        || (!strcmp(action_id,"annul_treaties") && !strchr(peace_term_mask,'a'))
        || (!strcmp(action_id,"humiliate_rival") && !strchr(peace_term_mask,'h'))
        || (!strcmp(action_id,"show_strength") && !strchr(peace_term_mask,'s'))
        || (!strcmp(action_id,"force_religion") && !strchr(peace_term_mask,'f'))
        || (!strcmp(action_id,"return_core") && !strchr(peace_term_mask,'b'))
        || (!strcmp(action_id,"revoke_core") && !strchr(peace_term_mask,'v'))
        || (!strcmp(action_id,"release_subject") && !strchr(peace_term_mask,'l'))
        || (!strcmp(action_id,"transfer_subject") && !strchr(peace_term_mask,'x'))
        || (strchr(peace_term_mask,'l') && !peace_release_subject.selection_requested)
        || (strchr(peace_term_mask,'x') && !peace_transfer_subject.selection_requested))) {
        alliance_query_failure(id,"QUERY_PEACE_COMBINED_SUBJECT_QUERY_PARAMETERS_INVALID"); return;
    }
    // A cede-province QUERY7 with "- -" is the read-only
    // candidate-enumeration form; selected terms use the same wire
    // with a non-empty province list and beneficiary.
    if (query7 && ((strcmp(action_id,"white_peace")==0
            && (peace_amount!=-1 || peace_provinces.count!=0))
        || (strcmp(action_id,"demand_ducats")==0
            && peace_amount<0)
        || (strcmp(action_id,"cede_province")==0
            && peace_amount>=0 && peace_provinces.count==0))) {
        alliance_query_failure(id,"QUERY_PEACE_QUERY_PARAMETERS_INVALID"); return;
    }
    if ((query3 || query19) && !declarewar) {
        alliance_query_failure(id,"QUERY_DECLARE_WAR_ACTION_REQUIRED"); return;
    }
    if ((query2!=insult) || (insult && (insult_id<-2
            || (!strcmp(action_id,"send_insult") && insult_id!=-1)
            || (!strcmp(action_id,"scornful_insult") && insult_id==-1)))) {
        alliance_query_failure(id,"QUERY_INSULT_PARAMETERS_INVALID"); return;
    }
    const bool gift=!strcmp(action_id,"send_gift");
    const bool influence=!strcmp(action_id,"influence_nation");
    if ((gift!=query20) || (influence!=query21) || (gift && gift_raw<=0)) {
        alliance_query_failure(id,"QUERY_GIFT_INFLUENCE_PARAMETERS_INVALID"); return;
    }
    const bool favor_gold=!strcmp(action_id,"trade_favors_for_gold");
    const bool favor_trust=!strcmp(action_id,"trade_favors_for_trust");
    const bool favor_men=!strcmp(action_id,"trade_favors_for_men");
    const bool favor_resource=favor_trust || favor_men;
    const bool favor_trade=favor_gold || favor_resource;
    const bool small_negotiated=support || military || vassal || favor_trade;
    const FactoryActionQueryMethods* negotiated=favor_gold?&favor_gold_query_methods:
        favor_trust?&favor_trust_query_methods:favor_men?&favor_men_query_methods:
        vassal?&vassal_query_methods:military?&military_query_methods:
        support?&support_query_methods:nullptr;
    const FactoryActionQueryMethods* unilateral=unilateral_query_family(action_id);
    bool offer=favor_trade || strcmp(action_id,"offer_alliance")==0 || strcmp(action_id,"offer_royal_marriage")==0 || strcmp(action_id,"support_independence")==0 || strcmp(action_id,"ask_military_access")==0 || strcmp(action_id,"offer_vassalization")==0;
    if (!peace && !query18 && !declarewar && !rival && !insult && !marriage
        && !gift && !influence && !small_negotiated && !unilateral && !offer
        && strcmp(action_id,"dissolve_alliance")!=0) {
        alliance_query_failure(id,"QUERY_ACTION_UNSUPPORTED"); return;
    }
    uintptr_t game=0; uint64_t player=0,actor=0,recipient=0; int32_t date=0;
    if (!read(base+0x233fe58,game) || !read(game+0x1dd0,date) || !read(game+0x1e60,player)
        || (player&0xffffff)!=0x524f50 || date!=expected_date) {
        alliance_query_failure(id,"QUERY_GAME_CONTEXT_CHANGED"); return;
    }
    if (!alliance_query_country(actor_tag,actor) || !alliance_query_country(recipient_tag,recipient) || actor==recipient) {
        alliance_query_failure(id,"QUERY_COUNTRY_RESOLUTION_UNAVAILABLE"); return;
    }
    if (gift || influence) {
        gift_influence_query_run(id,action_id,actor_tag,recipient_tag,actor,recipient,
            date,gift,gift?gift_ducats:0);
        return;
    }
    if (insult) { insult_query_run(id,action_id,actor_tag,recipient_tag,actor,recipient,date,insult_id); return; }
    if (peace || query18) {
        if (query4 || query5 || query6) peace_empty_offer_query_run(id,actor_tag,recipient_tag,
            actor,recipient,date,peace_war_id,query5?peace_amount:-1,query6?&peace_provinces:nullptr);
        else if (query18) peace_empty_offer_query_run(id,actor_tag,recipient_tag,
            actor,recipient,date,peace_war_id,peace_amount,nullptr,peace_demand,action_id,
            false,false,nullptr,true,false,nullptr,false,false,false,nullptr,nullptr,
            false,nullptr,nullptr,nullptr,false,
            peace_country_requests.any()?&peace_country_requests:nullptr,
            strchr(peace_term_mask,'e')?&peace_annex:nullptr);
        else if (query17) peace_empty_offer_query_run(id,actor_tag,recipient_tag,
            actor,recipient,date,peace_war_id,peace_amount>=0?peace_amount:-1,
            (strcmp(action_id,"cede_province")==0 || peace_provinces.count)
                ?&peace_provinces:nullptr,peace_demand,action_id,
            strchr(peace_term_mask,'r')!=nullptr,
            strchr(peace_term_mask,'t')!=nullptr,
            strchr(peace_term_mask,'t')?peace_trade_source:nullptr,true,
            strchr(peace_term_mask,'c')!=nullptr,
            strchr(peace_term_mask,'a')?&peace_annul:nullptr,
            strchr(peace_term_mask,'h')!=nullptr,
            strchr(peace_term_mask,'s')!=nullptr,
            strchr(peace_term_mask,'f')!=nullptr,
            strchr(peace_term_mask,'b')?&peace_return_core:nullptr,
            strchr(peace_term_mask,'v')?&peace_revoke_core:nullptr,true,nullptr,
            strchr(peace_term_mask,'l')?&peace_release_subject:nullptr,
            strchr(peace_term_mask,'x')?&peace_transfer_subject:nullptr,true);
        else if (query15) peace_empty_offer_query_run(id,actor_tag,recipient_tag,
            actor,recipient,date,peace_war_id,peace_amount>=0?peace_amount:-1,
            (strcmp(action_id,"cede_province")==0 || peace_provinces.count)
                ?&peace_provinces:nullptr,peace_demand,action_id,
            strchr(peace_term_mask,'r')!=nullptr,
            strchr(peace_term_mask,'t')!=nullptr,
            strchr(peace_term_mask,'t')?peace_trade_source:nullptr,true,
            strchr(peace_term_mask,'c')!=nullptr,
            strchr(peace_term_mask,'a')?&peace_annul:nullptr,
            strchr(peace_term_mask,'h')!=nullptr,
            strchr(peace_term_mask,'s')!=nullptr,
            strchr(peace_term_mask,'f')!=nullptr,
            strchr(peace_term_mask,'b')?&peace_return_core:nullptr,
            strchr(peace_term_mask,'v')?&peace_revoke_core:nullptr,true);
        else if (query14) peace_empty_offer_query_run(id,actor_tag,recipient_tag,
            actor,recipient,date,peace_war_id,-1,nullptr,peace_demand,action_id,
            false,false,nullptr,true,false,nullptr,false,false,false,&peace_core);
        else if (query16) peace_empty_offer_query_run(id,actor_tag,recipient_tag,
            actor,recipient,date,peace_war_id,-1,nullptr,peace_demand,action_id,
            false,false,nullptr,true,false,nullptr,false,false,false,nullptr,nullptr,
            false,&peace_subject);
        else if (query7 || query8 || query9 || query10 || query11 || query12 || query13) peace_empty_offer_query_run(id,actor_tag,recipient_tag,
            actor,recipient,date,peace_war_id,peace_amount>=0?peace_amount:-1,
            // Keep an empty cede request enabled so the native candidate
            // population runs; passing nullptr would downgrade it to the
            // unrelated white-peace inspection path.
            (strcmp(action_id,"cede_province")==0 || peace_provinces.count)
                ?&peace_provinces:nullptr,peace_demand,action_id,
            query8 || ((query9 || query10 || query11 || query12 || query13) && strchr(peace_term_mask,'r')),
            query9 || query10 || ((query11 || query12 || query13) && strchr(peace_term_mask,'t')),
            (query10 || query11 || query12 || query13) && strcmp(peace_trade_source,"-")?peace_trade_source:nullptr,
            !query10 || strcmp(peace_trade_source,"-"),
            query11 || ((query12 || query13) && strchr(peace_term_mask,'c')),
            (query12 || (query13 && strchr(peace_term_mask,'a')))?&peace_annul:nullptr,
            query13 && strchr(peace_term_mask,'h'),query13 && strchr(peace_term_mask,'s'),
            query13 && strchr(peace_term_mask,'f'));
        else peace_context_query_run(id,action_id,actor_tag,recipient_tag,actor,recipient,date);
        return;
    }
    if (declarewar) {
        declarewar_query_run(id,actor_tag,recipient_tag,actor,recipient,date,
            (query3 || query19)?war_cb_key:nullptr,war_province,
            (query3 || query19)?war_beneficiary:nullptr,query19?&war_participants:nullptr);
        return;
    }
    if (rival) { rival_query_run(id,action_id,actor_tag,recipient_tag,actor,recipient,date); return; }
    if (unilateral) { unilateral_query_run(id,action_id,actor_tag,recipient_tag,actor,recipient,date,*unilateral); return; }
    uintptr_t display=0,validity=0,preview=0,send_gate=0,accept_check=0,requires_diplomat_method=0;
    const uintptr_t vtable=base+(negotiated?negotiated->vtable_rva:marriage?0x1c80ab0:0x1c80720);
    const uintptr_t validity_rva=negotiated?negotiated->validity_rva:marriage?0x4ef3e0:0x511d90;
    if (!read(vtable+0x88,display) || display!=base+(negotiated?negotiated->display_rva:marriage?0x4ef7e0:0x512ca0)
        || !read(vtable+0x80,validity)
        || (validity!=base+validity_rva
            && (small_negotiated || marriage || validity!=reinterpret_cast<uintptr_t>(&observation_alliance_validity)))
        || (!read(vtable+0x120,preview) || preview!=base+(favor_trust?0x4fd130:favor_men?0x4f85d0:favor_gold?0x4f5e90:vassal?0x51fae0:military?0x525e30:support?0x50f160:marriage?0x4f0c20:0x513120))
        || !read(vtable+0x90,send_gate) || send_gate!=base+(small_negotiated||marriage?0x4e9b40:0x512a00)
        || !read(vtable+0xb8,accept_check) || accept_check!=base+0x4ea210
        || !read(vtable+0x100,requires_diplomat_method) || requires_diplomat_method!=base+0x8f440) {
        alliance_query_failure(id,"QUERY_METHOD_IDENTITY_CHANGED"); return;
    }
    bool native_visibility=false;
    bool support_active=false;
    bool military_active=false;
    VassalQueryState vassal_state{};
    if ((military && !military_query_active(actor,recipient,military_active))
        || (support && !support_query_active(actor,recipient,support_active))
        || (vassal && !vassal_query_relation(actor,recipient,vassal_state))) {
        alliance_query_failure(id,"QUERY_RELATION_CONTEXT_UNAVAILABLE"); return;
    }
    const bool visible_read=negotiated?factory_query_visibility(actor,recipient,offer,native_visibility,*negotiated)
        :alliance_query_visibility(actor,recipient,offer,native_visibility,marriage?0x28df:0x293d);
    if (!visible_read) {
        alliance_query_failure(id,"QUERY_UI_CONTEXT_UNAVAILABLE"); return;
    }
    unsigned available_diplomats=0;
    if (!alliance_query_diplomats(actor,available_diplomats)) {
        alliance_query_failure(id,"QUERY_DIPLOMAT_CONTEXT_UNAVAILABLE"); return;
    }
    alignas(16) unsigned char alliance_action[0x40]{};
    void* action=alliance_action;
    using Constructor=void* (*)(void*,uint64_t,uint64_t,int32_t);
    using Predicate=bool (*)(void*,void*,unsigned char);
    using Destructor=void* (*)(void*,unsigned int);
    if (marriage || small_negotiated) {
        // The pinned UI creator initializes the family's owned heap object,
        // assigns both endpoints and invokes +0xe0 for the selected variant.
        uintptr_t database=0,countries=0,country=0,actual_vtable=0;
        uint64_t actual_actor=0,actual_recipient=0;
        unsigned char actual_variant=0;
        if (!read(base+0x233d8b0,database) || !read(database+0x118,countries)
            || !read(countries+static_cast<uintptr_t>((actor>>32)&0xffff)*8,country)) {
            alliance_query_failure(id,"QUERY_UI_CREATOR_CONTEXT_UNAVAILABLE"); return;
        }
        using UiCreator=void* (*)(void*,int32_t,uint64_t,unsigned char,void*);
        action=reinterpret_cast<UiCreator>(base+0x35a8b0)(reinterpret_cast<void*>(country),
            negotiated?negotiated->selector:0x28df,recipient,offer?1:0,nullptr);
        if (!action || !read(reinterpret_cast<uintptr_t>(action),actual_vtable)
            || actual_vtable!=vtable) {
            alliance_query_failure(id,"QUERY_UI_CREATED_ACTION_IDENTITY_INVALID"); return;
        }
        if (!read(reinterpret_cast<uintptr_t>(action)+0x10,actual_actor) || actual_actor!=actor
            || !read(reinterpret_cast<uintptr_t>(action)+0x20,actual_recipient) || actual_recipient!=recipient
            || !read(reinterpret_cast<uintptr_t>(action)+0x38,actual_variant) || actual_variant!=(offer?1:0)) {
            reinterpret_cast<Destructor>(base+(small_negotiated?0x129450:0x4ed5e0))(action,1);
            alliance_query_failure(id,"QUERY_UI_CREATED_ACTION_ENDPOINT_INVALID"); return;
        }
    } else {
        reinterpret_cast<Constructor>(base+0x50f780)(action,actor,recipient,date);
        // Only this temporary object's variant is changed, never a live action.
        if (!offer) alliance_action[0x38]=0;
    }
    bool diplomat_required=reinterpret_cast<bool (*)(void*)>(requires_diplomat_method)(action);
    NativeShortString diagnostic{}; diagnostic.capacity=15;
    NativeShortString tooltip{}; tooltip.capacity=15;
    observation_active_query=id;
    bool common_gate=vassal?reinterpret_cast<bool (*)(void*,void*)>(display)(action,nullptr)
        :reinterpret_cast<Predicate>(display)(action,nullptr,0);
    bool native_valid=vassal?reinterpret_cast<bool (*)(void*,void*)>(base+validity_rva)(action,&diagnostic)
        :reinterpret_cast<Predicate>(base+validity_rva)(action,small_negotiated?&diagnostic:nullptr,0);
    bool initiation_gate=small_negotiated?common_gate:reinterpret_cast<Predicate>(send_gate)(action,nullptr,0);
    // Match the tooltip's diagnostic call too, including its initiation-date
    // and pending-response checks. Its result never grants execution authority.
    bool tooltip_gate=reinterpret_cast<Predicate>(send_gate)(action,small_negotiated?&tooltip:&diagnostic,0);
    NativeShortString& selected=(small_negotiated && !diagnostic.size)?tooltip:diagnostic;
    char diagnostic_hex[1025]{};
    unsigned diagnostic_bytes=static_cast<unsigned>(selected.size<=512?selected.size:512);
    unsigned char diagnostic_raw[512]{}; SIZE_T diagnostic_read=0;
    uintptr_t diagnostic_address=reinterpret_cast<uintptr_t>(selected.text);
    if (selected.capacity>=16) memcpy(&diagnostic_address,selected.text,8);
    bool diagnostic_readable=diagnostic_bytes==0 || (selected.size<=65536 && selected.capacity<=131072
        && ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(diagnostic_address),diagnostic_raw,diagnostic_bytes,&diagnostic_read)
        && diagnostic_read==diagnostic_bytes);
    if (diagnostic_readable) for (unsigned i=0;i<diagnostic_bytes;++i)
        snprintf(diagnostic_hex+i*2,3,"%02x",diagnostic_raw[i]);
    bool diagnostic_truncated=selected.size>512;
    reinterpret_cast<void (*)(void*)>(base+0x95660)(&diagnostic);
    reinterpret_cast<void (*)(void*)>(base+0x95660)(&tooltip);
    bool prediction_applies=offer && recipient!=player && (recipient&0xffffff)!=0x415246;
    bool score_available=false; int score=0; unsigned reason_count=0; bool reasons_readable=false;
#if defined(BRIDGE_ALLIANCE_REASON_METADATA)
    Binding reason_metadata_bindings[32]{};
    unsigned reason_metadata_capture_count=0;
    bool reason_metadata_capture_overflow=false;
    bool reason_metadata_binding_verified=false;
#endif
    if (prediction_applies && (native_valid || favor_resource)) {
        using Context=void* (*)(void*,bool*);
        bool existed=false;
        void* reasons=reinterpret_cast<Context>(base+0xdf320)(reinterpret_cast<void*>(base+0x1fd1c38),&existed);
        if (reasons) {
            reinterpret_cast<void (*)(void*)>(base+0x5ae8d0)(reasons);
            uintptr_t begin=0,end=0,capacity=0;
            bool shape=read(reinterpret_cast<uintptr_t>(reasons),begin)
                && read(reinterpret_cast<uintptr_t>(reasons)+0x10,capacity)
                && capacity>=begin && (capacity-begin)%48==0 && (capacity-begin)/48<=4096;
            if (shape) {
                if ((capacity-begin)/48<40) reinterpret_cast<void (*)(void*,unsigned)>(base+0x5aeba0)(reasons,40);
                // +0xb8 passes this mode as (caller_reason_container != null).
                // A text-bearing native caller also passes 1. We own a valid
                // reason container, so request its native detail text here.
#if defined(BRIDGE_ALLIANCE_REASON_METADATA)
                // The scope covers the text-bearing preview for this family. The
                // later +0xb8 numeric acceptance check deliberately runs
                // after this scope has ended.
                bridge_alliance_reason_metadata_scope_begin();
#endif
                score=reinterpret_cast<int (*)(void*,void*,unsigned char)>(preview)(action,reasons,1);
#if defined(BRIDGE_ALLIANCE_REASON_METADATA)
                bridge_alliance_reason_metadata_scope_end();
                bridge_alliance_reason_metadata_scope_count(
                    &reason_metadata_capture_overflow);
#endif
                score_available=true;
                reasons_readable=read(reinterpret_cast<uintptr_t>(reasons),begin)
                    && read(reinterpret_cast<uintptr_t>(reasons)+8,end) && end>=begin
                    && (end-begin)%48==0 && (end-begin)/48<=4096;
                if (reasons_readable) reason_count=static_cast<unsigned>((end-begin)/48);
#if defined(BRIDGE_ALLIANCE_REASON_METADATA)
                if (reasons_readable) {
                    reason_metadata_binding_verified=
                        bind_rows(begin,reason_count,reason_metadata_bindings,
                            32,&reason_metadata_capture_count,
                            &reason_metadata_capture_overflow);
                } else {
                    bridge_alliance_reason_metadata_scope_count(
                        &reason_metadata_capture_overflow);
                    reason_metadata_capture_count=
                        bridge_alliance_reason_metadata_scope_count(nullptr);
                }
#endif
                // Raw bounded evidence stays in the operator log until field
                // identity, native units and localization have been proved.
                for (unsigned index=0;reasons_readable && index<reason_count && index<32;++index) {
                    unsigned char raw[48]{}; SIZE_T got_row=0; char hex[97]{};
                    bool readable=ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(begin+index*48),raw,48,&got_row) && got_row==48;
                    if (readable) for (unsigned byte=0;byte<48;++byte) snprintf(hex+byte*2,3,"%02x",raw[byte]);
                    char row[380];
                    snprintf(row,sizeof(row),"{\"event\":\"native_alliance_reason_raw\",\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"index\":%u,\"readable\":%s,\"raw48\":\"%s\",\"decoded\":false}\n",
                        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),id,index,readable?"true":"false",hex);
                    line(row);
#if defined(BRIDGE_ALLIANCE_REASON_METADATA)
                    if (readable) alliance_query_reason_bound(id,index,raw,
                        reason_metadata_bindings[index],
                        reason_metadata_binding_verified);
#else
                    if (readable) alliance_query_reason(id,index,raw);
#endif
                }
#if defined(BRIDGE_ALLIANCE_REASON_METADATA)
                for (unsigned index=0;index<reason_metadata_capture_count
                    && index<32;++index) {
                    const ReasonMetadataRecord* capture=
                        bridge_alliance_reason_metadata_scope_record(index);
                    if (!capture) continue;
                    const Binding& binding=reason_metadata_bindings[index];
                    alliance_query_reason_provenance(id,index,binding,
                        reason_metadata_binding_verified && binding.strict_match);
                }
                alliance_query_reason_scale(id,score,reason_count,
                    reason_metadata_capture_count,
                    reason_metadata_capture_overflow,
                    reason_metadata_binding_verified);
#endif
            }
        }
    }
    bool acceptance_predicate_available=false,native_would_accept=false;
    if (prediction_applies && (native_valid || favor_resource) && score_available) {
        // This is the exact +0xb8 predicate used by the native AI response
        // branch. It is called only after copying reason text, since its
        // numeric mode may reuse the native thread-local reason container.
        native_would_accept=reinterpret_cast<bool (*)(void*,void*)>(accept_check)(action,nullptr);
        acceptance_predicate_available=true;
    }
    char favor_fields[640]{};
    if (favor_gold) {
        FavorGoldState state{}; int32_t amount=0;
        favor_gold_capture(actor,recipient,state);
        const bool amount_readable=favor_gold_amount(action,amount);
        favor_gold_query_json(state,amount,amount_readable,favor_fields,sizeof(favor_fields));
    } else if (favor_resource) {
        FavorTradeState state{}; int32_t amount=0;
        const bool amount_readable=favor_trade_capture_action(favor_trust,actor,recipient,action,state)
            && favor_trade_amount(favor_trust,action,amount);
        favor_trade_query_json(favor_trust,state,amount,amount_readable,
            favor_fields,sizeof(favor_fields));
    }
    if (marriage || small_negotiated) reinterpret_cast<Destructor>(base+(
        favor_trust?0x129500:small_negotiated?0x129450:0x4ed5e0))(action,1);
    else reinterpret_cast<Destructor>(base+0x129450)(action,0);
    observation_active_query=nullptr;
    char support_fields[768]{};
    if (favor_trade) strcpy(support_fields,"\"family\":\"favor_trade\",");
    if (support) snprintf(support_fields,sizeof(support_fields),
        "\"family\":\"support_independence\",\"support_independence_active\":%s,\"support_independence_state_verified\":true,",
        support_active?"true":"false");
    if (military) snprintf(support_fields,sizeof(support_fields),
        "\"family\":\"military_access\",\"military_access_active\":%s,\"military_access_state_verified\":true,",
        military_active?"true":"false");
    if (vassal) snprintf(support_fields,sizeof(support_fields),
        "\"family\":\"vassalization\",\"vassal_state_verified\":true,\"vassal_active\":%s,\"actor_is_overlord\":%s,\"actor_is_subject\":%s,\"subject_type\":%s,\"prestige_raw\":%d,\"cancel_prestige_delta_raw\":%d,\"cancel_prestige_effect_allowed\":%s,\"prestige_scale\":1000,\"cancel_prestige_cost_verified\":true,",
        vassal_state.active?"true":"false",vassal_state.actor_is_overlord?"true":"false",
        vassal_state.actor_is_subject?"true":"false",vassal_state.subject_type_json,
        vassal_state.prestige_raw,vassal_state.cancel_prestige_delta_raw,
        vassal_state.cancel_prestige_effect_allowed?"true":"false");
    char message[4096];
    snprintf(message,sizeof(message),"{\"event\":\"native_alliance_inspection\",\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"action_id\":\"%s\",%s\"actor\":\"%.3s\",\"recipient\":\"%.3s\",\"phase\":\"initiate\",\"date_raw\":%d,\"ui_selection_checked\":true,\"native_visibility\":%s,\"ui_enabled_gate_checked\":true,\"common_action_gate\":%s,\"display_predicate\":%s,\"initiation_gate\":%s,\"tooltip_gate\":%s,\"validity_called\":true,\"native_validity\":%s,\"native_diagnostic_hex\":\"%s\",\"diagnostic_readable\":%s,\"diagnostic_truncated\":%s,\"diplomat_context_readable\":true,\"diplomat_required\":%s,\"available_diplomat_count\":%u,\"diplomat_assignment_verified\":false,\"score_applicable\":%s,\"score_available\":%s,\"acceptance_predicate_available\":%s,\"native_would_accept\":%s,\"native_total_raw\":%d,\"acceptance_threshold_raw\":1,\"reason_container_readable\":%s,\"reason_count\":%u,\"reason_items_decoded\":false,\"full_rules_complete\":true,\"reasons_complete\":false,\"submitted\":false%s,\"frame_thread\":%lu}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
        id,action_id,support_fields,actor_tag,recipient_tag,date,native_visibility?"true":"false",common_gate?"true":"false",
        common_gate?"true":"false",initiation_gate?"true":"false",tooltip_gate?"true":"false",native_valid?"true":"false",
        diagnostic_hex,diagnostic_readable?"true":"false",diagnostic_truncated?"true":"false",
        diplomat_required?"true":"false",available_diplomats,
        prediction_applies?"true":"false",score_available?"true":"false",
        acceptance_predicate_available?"true":"false",native_would_accept?"true":"false",
        score,reasons_readable?"true":"false",reason_count,
        favor_fields,static_cast<unsigned long>(GetCurrentThreadId()));
    line(message);
}
