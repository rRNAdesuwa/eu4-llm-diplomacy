#ifndef BRIDGE_RELIGION_WAR_CONTEXT_INC
#define BRIDGE_RELIGION_WAR_CONTEXT_INC
#include "religion-war-context-script.h"

// Reuse the already reviewed run evaluator ABI and bounded file/pause helpers.
static wchar_t religion_war_request[MAX_PATH]{};
static wchar_t religion_war_config[MAX_PATH]{};
static bool religion_war_consumed=false;

static bool religion_war_script_verified(bool small) noexcept {
    wchar_t path[MAX_PATH]{};
    HANDLE file=CreateFileW(religion_war_config,GENERIC_READ,FILE_SHARE_READ,
        nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if (file==INVALID_HANDLE_VALUE) return false;
    DWORD bytes=GetFileSize(file,nullptr),got=0;
    bool valid=bytes>=4 && bytes<sizeof(path) && bytes%sizeof(wchar_t)==0
        && ReadFile(file,path,bytes,&got,nullptr) && got==bytes;
    CloseHandle(file);
    if (!valid || path[bytes/sizeof(wchar_t)-1]!=0) return false;
    wchar_t* slash=wcsrchr(path,L'\\');
    wchar_t* other=wcsrchr(path,L'/');
    const wchar_t* name=path;
    if (slash && (!other || slash>other)) name=slash+1;
    else if (other) name=other+1;
    if (wcscmp(name,small?L"llm_rel56b.txt":L"llm_rel56.txt")) return false;
    char content[sizeof(religion_small_war_context_script)+sizeof(religion_war_context_script)]{};
    const char* expected=small?religion_small_war_context_script:religion_war_context_script;
    const DWORD wanted=static_cast<DWORD>(strlen(expected));
    return vassal_test_context_read_exact(path,content,wanted)
        && !memcmp(content,expected,wanted);
}

static bool religion_war_context_start(const wchar_t* directory) noexcept {
    religion_war_consumed=false;
    if (!directory || swprintf(religion_war_request,MAX_PATH,
            L"%ls\\religion-war-context.req",directory)<0
        || swprintf(religion_war_config,MAX_PATH,
            L"%ls\\religion-war-context-script.path",directory)<0) return false;
    return GetFileAttributesW(religion_war_request)==INVALID_FILE_ATTRIBUTES
        || DeleteFileW(religion_war_request);
}

static void religion_war_context_tick(uintptr_t game) noexcept {
    if (religion_war_consumed || !game
        || GetFileAttributesW(religion_war_request)==INVALID_FILE_ATTRIBUTES) return;
    int32_t date=0;
    uint64_t player=0;
    if (!read(game+0x1dd0,date) || date!=56549088
        || !read(game+0x1e60,player)
        || static_cast<uint32_t>(player&0xffffffu)!=0x524f50u
        || static_cast<unsigned>((player>>32)&0xffffu)!=189
        || !vassal_test_context_paused(game)) return;
    constexpr char wire[]="TEST_ONLY RELIGION_WAR 56549088\n";
    constexpr char small_wire[]="TEST_ONLY RELIGION_SMALL_WAR 56549088\n";
    char request[sizeof(small_wire)]{};
    const bool small=vassal_test_context_read_exact(religion_war_request,
        request,sizeof(small_wire)-1) && !memcmp(request,small_wire,sizeof(small_wire)-1);
    bool request_ok=small || (vassal_test_context_read_exact(religion_war_request,
        request,sizeof(wire)-1) && !memcmp(request,wire,sizeof(wire)-1));
    religion_war_consumed=true;
    if (!DeleteFileW(religion_war_request)) request_ok=false;
    bool script_ok=request_ok && religion_war_script_verified(small);
    uintptr_t run=0;
    bool registration_ok=script_ok && read(base+0x1fc2558,run)
        && run==base+0xe4f040;
    bool native_success=false;
    if (registration_ok) {
        VassalTestNativeShortString name{};
        const char* filename=small?"llm_rel56b.txt":"llm_rel56.txt";
        name.capacity=15; name.size=strlen(filename);
        memcpy(name.text,filename,name.size+1);
        VassalTestNativeStringVector args{&name,&name+1,&name+1};
        VassalTestNativeConsoleResult result{};
        reinterpret_cast<void* (*)(void*,const void*)>(run)(&result,&args);
        native_success=result.success!=0;
        reinterpret_cast<void (*)(void*)>(base+0x95660)(&result.message);
    }
    char message[720];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_religion_war_context_result\",\"pid\":%lu,\"thread\":%lu,"
        "\"date_raw\":%d,\"player\":\"POR\",\"paused\":true,"
        "\"request_verified\":%s,\"script_verified\":%s,\"registration_verified\":%s,"
        "\"native_success\":%s,\"mode\":\"operator_prepared_war_context\","
        "\"script_name\":\"%s\",\"opponent\":\"%s\",\"peace_proposal_submitted\":false}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),
        static_cast<unsigned long>(GetCurrentThreadId()),date,
        request_ok?"true":"false",script_ok?"true":"false",
        registration_ok?"true":"false",native_success?"true":"false",
        small?"llm_rel56b.txt":"llm_rel56.txt",small?"LEI":"ENG");
    line(message);
}
#endif
