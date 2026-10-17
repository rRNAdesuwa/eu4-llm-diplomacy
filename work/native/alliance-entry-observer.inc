// Observe the direct break helper before its first relationship write.
// Opaque native inputs remain opaque; this never grants or denies authority.
extern "C" void bridge_direct_break_stub();
extern "C" void* bridge_direct_break_original;
extern "C" { void* bridge_direct_break_original=nullptr; }
struct DirectBreakObservation {
    uint64_t callback_sequence;
    DWORD thread;
    uintptr_t owner,caller_return;
    uint64_t input_handle,owner_handle;
    unsigned char native_flag;
    int32_t date;
    bool owner_readable,owner_is_country,input_canonical,caller_verified,date_readable;
};
static SRWLOCK direct_break_lock=SRWLOCK_INIT;
static DirectBreakObservation direct_break_events[128]{};
static unsigned direct_break_head=0,direct_break_size=0;
static volatile LONG direct_break_dropped=0;
static const unsigned char direct_break_signature[15]={0x48,0x89,0x5c,0x24,0x08,0x48,0x89,0x6c,0x24,0x10,0x48,0x89,0x74,0x24,0x18};
static unsigned char direct_break_patch[15]{};
static bridge_entry_patch::PatchPlan direct_break_patch_plan{};
static bool direct_break_installed=false;

static bool direct_break_owner_country(uintptr_t owner,uint64_t handle) {
    uintptr_t database=0,array=0,country=0;
    unsigned slot=static_cast<unsigned>((handle>>32)&0xffff);
    return observation_country_handle(handle) && read(base+0x233d8b0,database)
        && read(database+0x118,array) && read(array+slot*8,country) && country==owner;
}

extern "C" void bridge_direct_break_observe(void* owner,uint64_t input,unsigned char flag,uintptr_t caller_return) {
    DirectBreakObservation event{};
    event.callback_sequence=lifecycle_next_sequence();
    event.thread=GetCurrentThreadId();
    event.owner=reinterpret_cast<uintptr_t>(owner);
    event.input_handle=input;
    event.native_flag=flag;
    event.caller_return=caller_return;
    event.owner_readable=read(event.owner+0x20,event.owner_handle);
    event.owner_is_country=event.owner_readable && direct_break_owner_country(event.owner,event.owner_handle);
    event.input_canonical=observation_country_handle(input);
    uintptr_t game=0;
    event.date_readable=read(base+0x233fe58,game) && read(game+0x1dd0,event.date);
    // Validate the call bytes, rather than trusting a return-RVA label alone.
    unsigned char call[5]{};
    if (caller_return>=base+0x1005 && caller_return<base+0x1b66000 && read(caller_return-5,call) && call[0]==0xe8) {
        int32_t displacement=0; memcpy(&displacement,call+1,4);
        event.caller_verified=static_cast<uintptr_t>(static_cast<intptr_t>(caller_return)+displacement)==base+0x3d2350;
    }
    if (!TryAcquireSRWLockExclusive(&direct_break_lock)) { InterlockedIncrement(&direct_break_dropped); return; }
    if (direct_break_size<128) { direct_break_events[(direct_break_head+direct_break_size)%128]=event; ++direct_break_size; }
    else InterlockedIncrement(&direct_break_dropped);
    ReleaseSRWLockExclusive(&direct_break_lock);
}

static void direct_break_flush() {
    for (unsigned i=0;i<32;++i) {
        DirectBreakObservation event{};
        AcquireSRWLockExclusive(&direct_break_lock);
        if (!direct_break_size) { ReleaseSRWLockExclusive(&direct_break_lock); break; }
        event=direct_break_events[direct_break_head]; direct_break_head=(direct_break_head+1)%128; --direct_break_size;
        ReleaseSRWLockExclusive(&direct_break_lock);
        unsigned long long caller_rva=event.caller_return>=base+0x1000 && event.caller_return<base+0x1b66000
            ? static_cast<unsigned long long>(event.caller_return-base):0;
        char message[1400];
        snprintf(message,sizeof(message),"{\"event\":\"native_direct_break_entry\",\"session_id\":\"%lu-%llx\",\"callback_sequence\":%llu,\"thread\":%lu,\"owner\":\"0x%llx\",\"owner_handle\":\"0x%llx\",\"input_handle\":\"0x%llx\",\"native_flag\":%u,\"owner_readable\":%s,\"owner_is_country\":%s,\"input_canonical\":%s,\"caller_return_rva\":\"0x%llx\",\"direct_call_bytes_verified\":%s,\"date_readable\":%s,\"date_raw\":%d,\"decision_country_verified\":false,\"caller_source\":\"unknown\",\"native_forward_count_by_hook_contract\":1,\"native_return_observed\":false,\"authority_enabled\":false,\"business_result\":\"unknown\"}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
            static_cast<unsigned long long>(event.callback_sequence),static_cast<unsigned long>(event.thread),
            static_cast<unsigned long long>(event.owner),static_cast<unsigned long long>(event.owner_handle),
            static_cast<unsigned long long>(event.input_handle),static_cast<unsigned>(event.native_flag),
            event.owner_readable?"true":"false",event.owner_is_country?"true":"false",event.input_canonical?"true":"false",
            caller_rva,event.caller_verified?"true":"false",event.date_readable?"true":"false",event.date);
        line(message);
    }
    LONG dropped=InterlockedExchange(&direct_break_dropped,0);
    if (dropped) {
        char message[180]; snprintf(message,sizeof(message),"{\"event\":\"native_direct_break_drop\",\"dropped\":%ld,\"complete\":false}\n",static_cast<long>(dropped)); line(message);
    }
}

static bool direct_break_rollback() {
    if (!direct_break_installed) {
        unsigned char bytes[15]{};
        return read(base+0x3d2350,bytes) && !memcmp(bytes,direct_break_signature,15);
    }
    auto result=bridge_entry_patch::guarded_patch_rollback(direct_break_patch_plan);
    if (result.success) direct_break_installed=false;
    return result.success && result.threads_resumed && result.protection_restored;
}

static bool direct_break_install() {
    unsigned char actual[15]{};
    auto target=reinterpret_cast<unsigned char*>(base+0x3d2350);
    if (!read(reinterpret_cast<uintptr_t>(target),actual) || memcmp(actual,direct_break_signature,15)) return false;
    auto trampoline=static_cast<unsigned char*>(VirtualAlloc(nullptr,29,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    if (!trampoline) return false;
    memcpy(trampoline,direct_break_signature,15); absolute_jump(trampoline+15,reinterpret_cast<uintptr_t>(target+15));
    DWORD protection=0;
    if (!VirtualProtect(trampoline,29,PAGE_EXECUTE_READ,&protection)) { VirtualFree(trampoline,0,MEM_RELEASE); return false; }
    FlushInstructionCache(GetCurrentProcess(),trampoline,29);
    bridge_direct_break_original=trampoline;
    memset(direct_break_patch,0x90,15); absolute_jump(direct_break_patch,reinterpret_cast<uintptr_t>(&bridge_direct_break_stub));
    direct_break_patch_plan.count=1;
    direct_break_patch_plan.targets[0]={target,15,direct_break_signature,direct_break_patch,trampoline,29};
    auto result=bridge_entry_patch::guarded_patch_apply(direct_break_patch_plan);
    direct_break_installed=result.success;
    if (!result.success) {
        unsigned char current[15]{};
        direct_break_installed=read(reinterpret_cast<uintptr_t>(target),current) && !memcmp(current,direct_break_patch,15);
        if (!result.published) { VirtualFree(trampoline,0,MEM_RELEASE); bridge_direct_break_original=nullptr; }
        auto cleanup=bridge_entry_patch::guarded_patch_retry_pending();
        if (!cleanup.success || !result.protection_restored) lifecycle_rollback_incomplete=true;
        char message[400];
        snprintf(message,sizeof(message),"{\"event\":\"direct_break_guarded_install_failed\",\"published\":%s,\"threads_resumed\":%s,\"rollback_complete\":%s,\"failure_stage\":%u,\"win32_error\":%lu,\"restart_required\":true}\n",
            result.published?"true":"false",result.threads_resumed?"true":"false",result.rollback_complete?"true":"false",
            static_cast<unsigned>(result.failure_stage),static_cast<unsigned long>(result.error));
        line(message);
    }
    return result.success;
}
