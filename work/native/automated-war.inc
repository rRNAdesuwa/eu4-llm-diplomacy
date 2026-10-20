// Included after v7 peace routines. Native calls occur only on its frame thread.
#include "automated-war-script.h"
struct NativeShortString { char text[16]; uint64_t size,capacity; };
struct NativeStringVector { NativeShortString* begin; NativeShortString* end; NativeShortString* capacity; };
struct NativeConsoleResult { unsigned char success; unsigned char padding[7]; NativeShortString message; };
static_assert(sizeof(NativeShortString)==32 && sizeof(NativeConsoleResult)==40,"Native ABI sizes");
static wchar_t automatic_war_request[MAX_PATH],test_winwars_request[MAX_PATH],automatic_script_config[MAX_PATH];
static bool automatic_war_called=false,test_winwars_called=false;
static bool automated_pair_at_war(uintptr_t database) {
    uintptr_t array=0,fra=0,pairs=0; int32_t count=0;
    if (!read(database+0x118,array) || !read(array+122*8,fra)
        || !read(fra+0x1548,pairs) || !read(fra+0x1554,count) || count<0 || count>4096) return false;
    for (int32_t i=0;i<count;++i) {
        int32_t slot=0;
        if (!read(pairs+static_cast<uintptr_t>(i)*16,slot)) return false;
        if (slot==46) return true;
    }
    return false;
}
static bool automated_war_start(const wchar_t* directory) {
    if (swprintf(automatic_war_request,MAX_PATH,L"%ls\\declare-war.request",directory)<0
        || swprintf(test_winwars_request,MAX_PATH,L"%ls\\test-winwars.request",directory)<0
        || swprintf(automatic_script_config,MAX_PATH,L"%ls\\automatic-war-script.path",directory)<0) return false;
    const wchar_t* paths[]={automatic_war_request,test_winwars_request};
    for (const auto path:paths) {
        if (GetFileAttributesW(path)!=INVALID_FILE_ATTRIBUTES && !DeleteFileW(path)) return false;
    }
    return true;
}
static bool read_exact_file(const wchar_t* path,void* destination,DWORD wanted) {
    HANDLE file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if (file==INVALID_HANDLE_VALUE) return false;
    DWORD size=GetFileSize(file,nullptr),got=0;
    bool valid=size==wanted && ReadFile(file,destination,wanted,&got,nullptr) && got==wanted;
    CloseHandle(file); return valid;
}
static bool fixed_war_script_verified() {
    wchar_t path[MAX_PATH]{};
    HANDLE file=CreateFileW(automatic_script_config,GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if (file==INVALID_HANDLE_VALUE) return false;
    DWORD size=GetFileSize(file,nullptr),got=0;
    bool valid=size>=4 && size<sizeof(path) && size%2==0 && ReadFile(file,path,size,&got,nullptr) && got==size;
    CloseHandle(file);
    if (!valid || path[size/2-1]!=0) return false;
    wchar_t* name=wcsrchr(path,L'\\');
    if (!name || wcscmp(name+1,L"llm_auto.txt")!=0) return false;
    char contents[sizeof(automatic_war_script)]{};
    return read_exact_file(path,contents,sizeof(automatic_war_script)-1)
        && memcmp(contents,automatic_war_script,sizeof(automatic_war_script)-1)==0;
}
static bool fixed_console_call(uintptr_t rva,const char* argument,const char* label) {
    // Registration table and function prologues were reviewed offline.
    uintptr_t run=0,tag=0,win=0;
    if (!read(base+0x1fc2558,run) || run!=base+0xe4f040
        || !read(base+0x1fc5d98,tag) || tag!=base+0xe6a020
        || !read(base+0x1fc45d8,win) || win!=base+0xe61580) {
        line("{\"event\":\"automatic_console_rejected\",\"reason\":\"registration_identity\"}\n"); return false;
    }
    NativeShortString value{}; value.capacity=15;
    NativeStringVector args{};
    if (argument) {
        size_t size=strlen(argument);
        if (size>15) return false;
        memcpy(value.text,argument,size+1); value.size=size;
        args={&value,&value+1,&value+1};
    }
    NativeConsoleResult result{};
    using Evaluate=void* (*)(void*,const void*);
    reinterpret_cast<Evaluate>(base+rva)(&result,&args);
    bool success=result.success!=0;
    char message[256];
    snprintf(message,sizeof(message),"{\"event\":\"automatic_console_result\",\"fixed_command\":\"%s\",\"native_success\":%s,\"thread\":%lu}\n",label,success?"true":"false",static_cast<unsigned long>(GetCurrentThreadId()));
    line(message);
    using StringDtor=void (*)(void*);
    reinterpret_cast<StringDtor>(base+0x95660)(&result.message);
    return success;
}
static bool consume_fixed_request(const wchar_t* path,const char* token) {
    if (GetFileAttributesW(path)==INVALID_FILE_ATTRIBUTES) return false;
    char content[80]{}; size_t length=strlen(token);
    bool valid=length<sizeof(content) && read_exact_file(path,content,static_cast<DWORD>(length))
        && memcmp(content,token,length)==0;
    if (!DeleteFileW(path)) return false;
    if (!valid) line("{\"event\":\"automatic_request_rejected\",\"reason\":\"fixed_token_mismatch\"}\n");
    return valid;
}
static void automated_war_tick(uintptr_t database,uintptr_t game) {
    uint64_t player=0;
    if (!read(game+0x1e60,player) || (player&0xffffff)!=0x524f50 || ((player>>32)&0xffff)!=189) return;
    if (consume_fixed_request(automatic_war_request,"FRA ENG cb_core 177 war_auto_01\n")) {
        if (automatic_war_called || automated_pair_at_war(database) || !fixed_war_script_verified()) {
            line("{\"event\":\"automatic_war_rejected\",\"reason\":\"one_shot_war_or_script_guard\"}\n");
        } else {
            automatic_war_called=true;
            line("{\"event\":\"automatic_war_begin\",\"actor\":\"FRA\",\"target\":\"ENG\",\"unlock\":false}\n");
            bool evaluated=fixed_console_call(0xe4f040,"llm_auto.txt","run_fixed_war");
            bool war=automated_pair_at_war(database);
            line(evaluated && war?"{\"event\":\"automatic_war_runtime_confirmed\",\"war_live\":true}\n":
                "{\"event\":\"automatic_war_not_confirmed\"}\n");
        }
    }
    // Explicit test-only fixture; never part of a normal declare-war request.
    if (consume_fixed_request(test_winwars_request,"TEST_ONLY FRA winwars restore_POR\n")) {
        if (test_winwars_called || !automated_pair_at_war(database)) {
            line("{\"event\":\"test_winwars_rejected\"}\n"); return;
        }
        test_winwars_called=true;
        bool changed=fixed_console_call(0xe6a020,"FRA","test_tag_FRA");
        uint64_t temporary=0;
        bool fra=changed && read(game+0x1e60,temporary) && (temporary&0xffffff)==0x415246;
        bool applied=fra && fixed_console_call(0xe61580,nullptr,"test_winwars");
        // Always attempt to restore the observer if tag changed state.
        fixed_console_call(0xe6a020,"POR","test_restore_POR");
        uint64_t restored=0;
        bool correct=read(game+0x1e60,restored) && restored==player;
        line(applied && correct?"{\"event\":\"test_winwars_fixture_applied\",\"player_restored\":true,\"natural_war_acceptance\":false}\n":
            "{\"event\":\"test_winwars_fixture_failed\"}\n");
    }
}
