#ifndef BRIDGE_VASSAL_INBOUND_TEST_CONTEXT_INC
#define BRIDGE_VASSAL_INBOUND_TEST_CONTEXT_INC

// R35 inbound-context preparation is deliberately separate from the
// Vassalization response path.  It loads one reviewed script so that the
// later SAV -> FRA proposal is made in a legal native context.  This include
// never creates a subject and never chooses FRA's response.
#include "vassal-inbound-test-context-script.h"

static wchar_t vassal_inbound_test_context_request[MAX_PATH]{};
static wchar_t vassal_inbound_test_context_script_config[MAX_PATH]{};
static bool vassal_inbound_test_context_consumed=false;
static bool vassal_inbound_test_context_called=false;

struct VassalInboundTestNativeShortString { char text[16]; uint64_t size,capacity; };
struct VassalInboundTestNativeStringVector {
    VassalInboundTestNativeShortString* begin;
    VassalInboundTestNativeShortString* end;
    VassalInboundTestNativeShortString* capacity;
};
struct VassalInboundTestNativeConsoleResult {
    unsigned char success;
    unsigned char padding[7];
    VassalInboundTestNativeShortString message;
};
static_assert(sizeof(VassalInboundTestNativeShortString)==32 &&
    sizeof(VassalInboundTestNativeConsoleResult)==40,
    "R35 inbound context console ABI sizes");

static bool vassal_inbound_test_context_read_exact(const wchar_t* path,
    void* destination,DWORD wanted) noexcept {
    HANDLE file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,nullptr);
    if (file==INVALID_HANDLE_VALUE) return false;
    DWORD size=GetFileSize(file,nullptr),got=0;
    bool valid=size==wanted && ReadFile(file,destination,wanted,&got,nullptr)
        && got==wanted;
    CloseHandle(file);
    return valid;
}

static bool vassal_inbound_test_context_script_path(
    wchar_t (&path)[MAX_PATH]) noexcept {
    HANDLE file=CreateFileW(vassal_inbound_test_context_script_config,GENERIC_READ,
        FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if (file==INVALID_HANDLE_VALUE) return false;
    DWORD size=GetFileSize(file,nullptr),got=0;
    bool valid=size>=4 && size<sizeof(path) && (size%sizeof(wchar_t))==0
        && ReadFile(file,path,size,&got,nullptr) && got==size;
    CloseHandle(file);
    if (!valid) return false;
    path[size/sizeof(wchar_t)]=0;
    if (size<sizeof(wchar_t) || path[size/sizeof(wchar_t)-1]!=0) return false;
    wchar_t* slash=wcsrchr(path,L'\\');
    wchar_t* other=wcsrchr(path,L'/');
    const wchar_t* name=path;
    if (slash && (!other || slash>other)) name=slash+1;
    else if (other) name=other+1;
    return wcscmp(name,L"llm_vas_in.txt")==0;
}

static bool vassal_inbound_test_context_script_verified() noexcept {
    wchar_t path[MAX_PATH]{};
    if (!vassal_inbound_test_context_script_path(path)) return false;
    constexpr DWORD bytes=static_cast<DWORD>(sizeof(
        vassal_inbound_test_context_script)-1);
    char contents[sizeof(vassal_inbound_test_context_script)]{};
    return vassal_inbound_test_context_read_exact(path,contents,bytes)
        && memcmp(contents,vassal_inbound_test_context_script,bytes)==0;
}

static bool vassal_inbound_test_context_paused(uintptr_t game) noexcept {
    uintptr_t server=0,server_vtable=0,get_pause=0,pause=0;
    unsigned char paused=0;
    if (!read(game+0x1e00,server) || !read(server,server_vtable)
        || !read(server_vtable+0x100,get_pause)
        || get_pause<base+0x1000 || get_pause>=base+0x1c00000) return false;
    pause=reinterpret_cast<uintptr_t (*)(void*)>(get_pause)(
        reinterpret_cast<void*>(server));
    return pause>=0x10000 && read(pause+0x48,paused) && paused==1;
}

static bool vassal_inbound_test_context_native_run(bool& native_success) noexcept {
    uintptr_t run=0;
    if (!read(base+0x1fc2558,run) || run!=base+0xe4f040) return false;
    VassalInboundTestNativeShortString value{};
    value.capacity=15;
    constexpr char filename[]="llm_vas_in.txt";
    constexpr size_t filename_size=sizeof(filename)-1;
    static_assert(filename_size<=15,
        "fixed inbound context script filename exceeds native short string");
    memcpy(value.text,filename,sizeof(filename));
    value.size=filename_size;
    VassalInboundTestNativeStringVector args{&value,&value+1,&value+1};
    VassalInboundTestNativeConsoleResult result{};
    using Evaluate=void* (*)(void*,const void*);
    reinterpret_cast<Evaluate>(base+0xe4f040)(&result,&args);
    native_success=result.success!=0;
    using StringDtor=void (*)(void*);
    reinterpret_cast<StringDtor>(base+0x95660)(&result.message);
    return true;
}

static bool vassal_inbound_test_context_read_request(int32_t& expected_date,
    bool remove_request) noexcept {
    if (GetFileAttributesW(vassal_inbound_test_context_request)==INVALID_FILE_ATTRIBUTES)
        return false;
    char content[128]{};
    HANDLE file=CreateFileW(vassal_inbound_test_context_request,GENERIC_READ,
        FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    DWORD size=0,got=0;
    bool readable=file!=INVALID_HANDLE_VALUE;
    if (readable) {
        size=GetFileSize(file,nullptr);
        readable=size<sizeof(content) && ReadFile(file,content,size,&got,nullptr)
            && got==size;
        CloseHandle(file);
    }
    bool valid=false;
    int used=0,value=0;
    if (readable && size>0) {
        valid=sscanf_s(content,"TEST_ONLY VASSAL_INBOUND_CONTEXT %d%n",
            &value,&used)==1 && used>=0
            && static_cast<DWORD>(used+1)==size && content[used]=='\n';
        if (valid) expected_date=value;
    }
    if (remove_request && !DeleteFileW(vassal_inbound_test_context_request))
        valid=false;
    if (remove_request && !valid) {
        line("{\"event\":\"native_vassal_inbound_context_failed\",\"reason\":\"fixed_request_invalid\",\"submitted\":false}\n");
    }
    return valid;
}

static bool vassal_inbound_test_context_start(const wchar_t* directory) noexcept {
    vassal_inbound_test_context_consumed=false;
    vassal_inbound_test_context_called=false;
    if (!directory
        || swprintf(vassal_inbound_test_context_request,MAX_PATH,
            L"%ls\\vassal-inbound-test-context.req",directory)<0
        || swprintf(vassal_inbound_test_context_script_config,MAX_PATH,
            L"%ls\\vassal-inbound-test-context-script.path",directory)<0)
        return false;
    const wchar_t* paths[]={vassal_inbound_test_context_request,
        vassal_inbound_test_context_script_config};
    for (const wchar_t* path:paths) {
        if (GetFileAttributesW(path)!=INVALID_FILE_ATTRIBUTES
            && !DeleteFileW(path)) return false;
    }
    return true;
}

static void vassal_inbound_test_context_tick(uintptr_t game) noexcept {
    if (vassal_inbound_test_context_consumed
        || vassal_inbound_test_context_called || !game
        || GetFileAttributesW(vassal_inbound_test_context_request)
            ==INVALID_FILE_ATTRIBUTES) return;
    uint64_t player=0;
    int32_t date=0;
    if (!read(game+0x1dd0,date) || !read(game+0x1e60,player)
        || static_cast<uint32_t>(player&0xffffffu)!=0x524f50u
        || static_cast<unsigned>((player>>32)&0xffffu)!=189
        || !vassal_inbound_test_context_paused(game)) return;
    int32_t expected_date=0;
    if (!vassal_inbound_test_context_read_request(expected_date,false)) {
        vassal_inbound_test_context_consumed=true;
        vassal_inbound_test_context_read_request(expected_date,true);
        return;
    }
    if (date!=expected_date) return;
    vassal_inbound_test_context_consumed=true;
    if (!vassal_inbound_test_context_read_request(expected_date,true)) return;
    bool script_ok=vassal_inbound_test_context_script_verified();
    if (!script_ok) {
        line("{\"event\":\"native_vassal_inbound_context_failed\",\"reason\":\"script_bytes_or_path_mismatch\",\"submitted\":false}\n");
        return;
    }
    vassal_inbound_test_context_called=true;
    bool native_success=false;
    bool registration_ok=vassal_inbound_test_context_native_run(native_success);
    char message[1024];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_vassal_inbound_context_result\",\"pid\":%lu,\"thread\":%lu,"
        "\"expected_date_raw\":%d,\"date_raw\":%d,\"player\":\"POR\",\"player_slot\":189,\"paused\":true,"
        "\"request_verified\":true,\"script_verified\":%s,\"script_name\":\"llm_vas_in.txt\","
        "\"run_registration_rva\":\"0x1fc2558\",\"run_evaluator_rva\":\"0xe4f040\","
        "\"registration_verified\":%s,\"native_success\":%s,"
        "\"business_result\":\"context_preparation_only\",\"vassalization_business_submitted\":false,"
        "\"response_decision_made\":false,\"development_fixture\":\"FRA_every_owned_province_set_base_1\","
        "\"expected_owned_province_count\":20,\"expected_development_operations\":60}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),
        static_cast<unsigned long>(GetCurrentThreadId()),expected_date,date,
        script_ok?"true":"false",registration_ok?"true":"false",
        native_success?"true":"false");
    line(message);
}

#endif
