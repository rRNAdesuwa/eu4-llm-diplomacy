// Native preview and reason rows for an already constructed peace action.
// The score remains a signed native integer; no response threshold is assumed.
static void peace_offer_evaluation_query(const char* id,void* action,bool eligible,
    char (&output)[49152]) noexcept {
    bool called=false,available=false,readable=false,truncated=false;
    bool aggregate_available=false,factors_complete=false,all_items_verified=true;
    int32_t score=0,aggregate=0;
    unsigned count=0,captured_count=0; char items[46080]{}; size_t used=0;
    if (eligible) {
        uintptr_t preview=0;
        if (read(base+0x1c7b840+0x120,preview) && preview==base+0x59bf10) {
            using Context=void* (*)(void*,bool*);
            bool existed=false;
            void* reasons=reinterpret_cast<Context>(base+0xdf320)(
                reinterpret_cast<void*>(base+0x1fd1c38),&existed);
            if (reasons) {
                reinterpret_cast<void (*)(void*)>(base+0x5ae8d0)(reasons);
                const uintptr_t context=reinterpret_cast<uintptr_t>(reasons);
                uintptr_t begin=0,end=0,capacity=0;
                const bool shape=read(context,begin) && read(context+0x10,capacity)
                    && capacity>=begin && (capacity-begin)%48==0
                    && (capacity-begin)/48<=4096;
                if (shape) {
                    if ((capacity-begin)/48<40)
                        reinterpret_cast<void (*)(void*,unsigned)>(base+0x5aeba0)(reasons,40);
#if defined(BRIDGE_ALLIANCE_REASON_METADATA)
                    bridge_alliance_reason_metadata_scope_begin();
#endif
                    // Peace's mode-one branches use the explicit DIPLO_*
                    // localization keys with the same 48-byte row/vector ABI.
                    called=true;
                    score=reinterpret_cast<int32_t (*)(void*,void*,unsigned char)>(preview)(action,reasons,1);
#if defined(BRIDGE_ALLIANCE_REASON_METADATA)
                    bridge_alliance_reason_metadata_scope_end();
#endif
                    available=true;
                    readable=read(context,begin) && read(context+8,end)
                        && end>=begin && (end-begin)%48==0 && (end-begin)/48<=4096;
                    if (readable) count=static_cast<unsigned>((end-begin)/48);
                    truncated=count>32;
#if defined(BRIDGE_ALLIANCE_REASON_METADATA)
                    Binding bindings[32]{}; unsigned capture_count=0; bool overflow=false;
                    const bool all_bound=readable && bind_rows(begin,count,bindings,32,
                        &capture_count,&overflow);
                    truncated=truncated || overflow;
#endif
                    for (unsigned index=0;readable && index<count && index<32;++index) {
                        unsigned char raw[48]{}; SIZE_T copied=0;
                        if (!ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(begin+index*48),
                                raw,sizeof(raw),&copied) || copied!=sizeof(raw)) { readable=false; break; }
                        int32_t value=0; memcpy(&value,raw,4);
                        NativeShortString text{}; memcpy(&text,raw+8,sizeof(text));
                        char hex[1025]{}; bool text_readable=false,text_truncated=false;
                        declarewar_query_hex(text,hex,text_readable,text_truncated);
                        bool bound=false,identified=false; char identifier[80]="null";
#if defined(BRIDGE_ALLIANCE_REASON_METADATA)
                        const Binding& binding=bindings[index];
                        alliance_query_reason_provenance(id,index,binding,all_bound);
                        bound=all_bound && binding.strict_match;
                        identified=bound && binding.capture && binding.capture->constructor_source_confirmed;
                        if (identified) snprintf(identifier,sizeof(identifier),"\"%s\"",binding.capture->localization_key);
#endif
                        const int added=snprintf(items+used,sizeof(items)-used,
                            "%s{\"native_identifier\":%s,\"identifier_verified\":%s,\"native_value\":%d,\"native_flag\":%s,\"text_hex\":\"%s\",\"text_readable\":%s,\"text_truncated\":%s,\"row_binding_verified\":%s}",
                            index?",":"",identifier,identified?"true":"false",value,raw[40]?"true":"false",
                            hex,text_readable?"true":"false",text_truncated?"true":"false",bound?"true":"false");
                        if (added<0 || static_cast<size_t>(added)>=sizeof(items)-used) {
                            truncated=true; items[used]=0; break;
                        }
                        used+=static_cast<size_t>(added);
                        ++captured_count;
                        all_items_verified=all_items_verified && identified && bound
                            && text_readable && !text_truncated;
                    }
                    factors_complete=readable && !truncated
                        && captured_count==count && all_items_verified;
                    aggregate=reinterpret_cast<int32_t (*)(void*,unsigned char)>(base+0x978ed0)(
                        reinterpret_cast<unsigned char*>(action)+0x48,1);
                    aggregate_available=true;
                }
            }
        }
    }
    snprintf(output,sizeof(output),
        "{\"called\":%s,\"score_available\":%s,\"score_raw\":%d,\"score_representation\":\"signed_int32\",\"factor_native_count\":%u,\"factor_capture_truncated\":%s,\"factors_available\":%s,\"factors_complete\":%s,\"items\":[%s],\"aggregate_score_available\":%s,\"aggregate_score_raw\":%d,\"complete\":false}",
        called?"true":"false",available?"true":"false",score,count,truncated?"true":"false",
        readable?"true":"false",factors_complete?"true":"false",items,aggregate_available?"true":"false",aggregate);
}
