// Test-save startup confirmation, time control and native saving; v3.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <cstdint>
#include <cstring>
#include <cstdio>
#if defined(BRIDGE_PEACE_AUTHORITY_LOCK) && (!defined(BRIDGE_TRACE_COMMAND_EXECUTION) || defined(BRIDGE_ENABLE_PEACE_SEND))
#error Peace quarantine requires command tracing and disabled bridge sending.
#endif

extern "C" void bridge_frame_stub();
extern "C" void bridge_response_stub();
extern "C" { void* bridge_trampoline = nullptr; }
extern "C" { void* bridge_response_original = nullptr; }
static HMODULE self_module;
static uintptr_t base;
static HANDLE log_file = INVALID_HANDLE_VALUE;
static volatile LONG started = 0, inside = 0, frame_count = 0;
static DWORD frame_thread = 0;
static bool thread_changed = false;
static ULONGLONG last_log = 0;
static const unsigned char expected[20] = {
    0x4c,0x89,0x44,0x24,0x18,0x55,0x53,0x57,0x48,0x8d,
    0x6c,0x24,0xb0,0x48,0x81,0xec,0x50,0x01,0x00,0x00};

static void line(const char* message) {
    DWORD written;
    if (log_file != INVALID_HANDLE_VALUE) {
        WriteFile(log_file, message, static_cast<DWORD>(strlen(message)), &written, nullptr);
        FlushFileBuffers(log_file);
    }
}
template<typename T> static bool read(uintptr_t address, T& value) {
    SIZE_T size = 0;
    return address >= 0x10000 && ReadProcessMemory(GetCurrentProcess(),
        reinterpret_cast<void*>(address), &value, sizeof(value), &size) && size == sizeof(value);
}

#include "entry-patch-transaction.inc"
static bridge_entry_patch::PatchPlan control_frame_patch_plan{};
static unsigned char control_frame_patch_bytes[20]{};
static bool control_frame_installed=false;
static bool control_trace_installed=false;

static bool control_rollback_hooks() {
    bool complete=true;
#ifdef BRIDGE_TRACE_PEACE_RESPONSES
    uintptr_t slot_rva=0x1c7b840+0x48;
#ifdef BRIDGE_TRACE_COMMAND_EXECUTION
    slot_rva=0x1c814b0+0x48;
#endif
    if (control_trace_installed) {
        auto slot=reinterpret_cast<void**>(base+slot_rva);
        DWORD protection=0,ignored=0;
        if (VirtualProtect(slot,8,PAGE_READWRITE,&protection)) {
            void* previous=InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(slot),bridge_response_original,reinterpret_cast<void*>(&bridge_response_stub));
            complete=(previous==reinterpret_cast<void*>(&bridge_response_stub) || previous==bridge_response_original) && complete;
            complete=VirtualProtect(slot,8,protection,&ignored)!=FALSE && complete;
        } else complete=false;
    }
#endif
    if (control_frame_installed) {
        auto result=bridge_entry_patch::guarded_patch_rollback(control_frame_patch_plan);
        complete=result.success && result.threads_resumed && result.protection_restored && complete;
    }
    auto cleanup=bridge_entry_patch::guarded_patch_retry_pending();
    complete=cleanup.success && complete;
    if (complete) { control_frame_installed=false; control_trace_installed=false; }
    return complete;
}

static void absolute_jump(unsigned char* bytes, uintptr_t destination) {
    bytes[0]=0xff; bytes[1]=0x25;
    memset(bytes+2, 0, 4);
    memcpy(bytes+6, &destination, 8);
}

struct NativeShortString { char text[16]; uint64_t size,capacity; };
struct NativeStringVector { NativeShortString* begin; NativeShortString* end; NativeShortString* capacity; };
struct NativeConsoleResult { unsigned char success; unsigned char padding[7]; NativeShortString message; };
static_assert(sizeof(NativeConsoleResult)==40,"ABI");
#include "automated-control.inc"
#include "popup-control.inc"
#ifdef BRIDGE_DIPLOMAT_RECALL
#include "diplomat-recall.inc"
#endif
extern "C" int bridge_response_observe(void*) { return 1; }
extern "C" void bridge_frame_tick(void*) {
    if (InterlockedCompareExchange(&inside,1,0)) return;
    DWORD tid=GetCurrentThreadId();
    if (!frame_thread) frame_thread=tid;
    if (frame_thread!=tid) thread_changed=true;
    LONG count=InterlockedIncrement(&frame_count);
    if (!thread_changed && count>=100) { popup_control_tick(); automated_control_tick(); }
#ifdef BRIDGE_DIPLOMAT_RECALL
    if (!thread_changed && count>=100) diplomat_recall_tick();
#endif
    if (GetTickCount64()-last_log>=1000) {
        last_log=GetTickCount64();
        char message[160];
        snprintf(message,sizeof(message),"{\"event\":\"control_frame\",\"pid\":%lu,\"thread\":%lu,\"frames\":%ld}\n",static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long>(tid),static_cast<long>(count));
        line(message);
    }
    InterlockedExchange(&inside,0);
}
extern "C" __declspec(dllexport) DWORD WINAPI BridgeStart(void*) {
    if (InterlockedCompareExchange(&started,1,0)) return 10;
    wchar_t directory[MAX_PATH];
    DWORD length=GetModuleFileNameW(self_module,directory,MAX_PATH);
    if (!length || length>=MAX_PATH) return 11;
    wchar_t* slash=wcsrchr(directory,L'\\');
    if (!slash) return 11;
    *slash=0;
    wchar_t path[MAX_PATH];
    if (swprintf(path,MAX_PATH,L"%ls\\control-probe.jsonl",directory)<0) return 11;
    log_file=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
    if (log_file==INVALID_HANDLE_VALUE) return 12;
    if (!automated_control_start(directory)) return 25;
    if (swprintf(popup_request,MAX_PATH,L"%ls\\popup-confirm.request",directory)<0) return 25;
    DeleteFileW(popup_request);
#ifdef BRIDGE_DIPLOMAT_RECALL
    if (swprintf(recall_request,MAX_PATH,L"%ls\\diplomat-recall.request",directory)<0) return 25;
    DeleteFileW(recall_request);
#endif
    base=reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
#ifdef BRIDGE_TRACE_PEACE_RESPONSES
    uintptr_t trace_slot_rva=0x1c7b840+0x48,trace_original_rva=0x598f00;
#ifdef BRIDGE_TRACE_COMMAND_EXECUTION
    trace_slot_rva=0x1c814b0+0x48; trace_original_rva=0x4e7c80;
#endif
    auto response_slot=reinterpret_cast<void**>(base+trace_slot_rva);
    uintptr_t response_method=0;
    if (!read(reinterpret_cast<uintptr_t>(response_slot),response_method) || response_method!=base+trace_original_rva) {
        line("{\"event\":\"response_slot_identity_failed\"}\n"); return 20;
    }
    bridge_response_original=reinterpret_cast<void*>(response_method);
#endif
    auto target=reinterpret_cast<unsigned char*>(base+0x10a6d90);
    unsigned char actual[20]; SIZE_T n=0;
    if (!ReadProcessMemory(GetCurrentProcess(),target,actual,20,&n) || n!=20 || memcmp(actual,expected,20)) {
        line("{\"event\":\"signature_mismatch\"}\n"); return 14;
    }
    auto trampoline=static_cast<unsigned char*>(VirtualAlloc(nullptr,34,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    if (!trampoline) return 15;
    memcpy(trampoline,expected,20); absolute_jump(trampoline+20,reinterpret_cast<uintptr_t>(target+20));
    DWORD old=0;
    if (!VirtualProtect(trampoline,34,PAGE_EXECUTE_READ,&old)) return 16;
    FlushInstructionCache(GetCurrentProcess(),trampoline,34);
    bridge_trampoline=trampoline;
    memset(control_frame_patch_bytes,0x90,20);
    absolute_jump(control_frame_patch_bytes,reinterpret_cast<uintptr_t>(&bridge_frame_stub));
    control_frame_patch_plan.count=1;
    control_frame_patch_plan.targets[0]={target,20,expected,control_frame_patch_bytes,trampoline,34};
    auto frame_result=bridge_entry_patch::guarded_patch_apply(control_frame_patch_plan);
    control_frame_installed=frame_result.success;
    if (!frame_result.success) {
        unsigned char current[20]{};
        control_frame_installed=read(reinterpret_cast<uintptr_t>(target),current) && !memcmp(current,control_frame_patch_bytes,20);
        auto cleanup=bridge_entry_patch::guarded_patch_retry_pending();
        bool rolled_back=control_rollback_hooks();
        char failure[420];
        snprintf(failure,sizeof(failure),"{\"event\":\"hook_guarded_install_failed\",\"published\":%s,\"rollback_complete\":%s,\"threads_resumed\":%s,\"protection_restored\":%s,\"failure_stage\":%u,\"win32_error\":%lu,\"pending_cleanup_complete\":%s,\"restart_required\":true}\n",
            frame_result.published?"true":"false",frame_result.rollback_complete?"true":"false",
            frame_result.threads_resumed?"true":"false",frame_result.protection_restored?"true":"false",
            static_cast<unsigned>(frame_result.failure_stage),static_cast<unsigned long>(frame_result.error),(cleanup.success && rolled_back)?"true":"false");
        line(failure);
        if (!frame_result.published) { VirtualFree(trampoline,0,MEM_RELEASE); bridge_trampoline=nullptr; }
        return 18;
    }
    bool protection_restored=frame_result.protection_restored;
#ifdef BRIDGE_TRACE_PEACE_RESPONSES
    DWORD response_old=0,response_ignored=0;
    bool response_ok=VirtualProtect(response_slot,8,PAGE_READWRITE,&response_old)!=FALSE;
    if (response_ok) {
        control_trace_installed=InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(response_slot),
            reinterpret_cast<void*>(&bridge_response_stub),bridge_response_original)==bridge_response_original;
        response_ok=VirtualProtect(response_slot,8,response_old,&response_ignored)!=FALSE && control_trace_installed;
    }
    if (!response_ok) {
        bool complete=control_rollback_hooks();
        line(complete?"{\"event\":\"hook_not_installed\",\"hooks_rolled_back\":true}\n":
            "{\"event\":\"hook_rollback_incomplete\",\"restart_required\":true}\n");
        return complete?20:21;
    }
#endif
#ifdef BRIDGE_TRACE_PEACE_RESPONSES
    char trace_installed[240];
    snprintf(trace_installed,sizeof(trace_installed),"{\"event\":\"%s\",\"slot_rva\":\"0x%llx\",\"original_rva\":\"0x%llx\",\"mutates_actions\":false,\"capacity\":64}\n",
#ifdef BRIDGE_TRACE_COMMAND_EXECUTION
        "command_execution_trace_installed",
#else
        "response_trace_installed",
#endif
        static_cast<unsigned long long>(trace_slot_rva),static_cast<unsigned long long>(trace_original_rva));
    line(trace_installed);
#endif
#ifdef BRIDGE_PEACE_AUTHORITY_LOCK
    line("{\"event\":\"peace_authority_lock_installed\",\"controlled_country\":\"FRA\",\"scope\":\"verified_native_peace_actions_involving_FRA\",\"bridge_sending_enabled\":false,\"other_diplomacy_locked\":false}\n");
#endif
    line(protection_restored?"{\"event\":\"hook_installed\",\"mode\":\"observe\"}\n":
        "{\"event\":\"hook_installed_protection_restore_failed\"}\n");
    return protection_restored?0:19;
}

BOOL WINAPI DllMain(HINSTANCE module,DWORD reason,LPVOID) {
    if (reason==DLL_PROCESS_ATTACH) { self_module=module; DisableThreadLibraryCalls(module); }
    return TRUE;
}
