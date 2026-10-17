// The world's transport vtable +0x48 returns &receiver.pending_head.
// Observe actual callers of that accessor to identify the native consumer.
// This observer forwards once and reads only the three established list words.
using PeaceReceiverHeadMethod=void* (*)(void*);
static PeaceReceiverHeadMethod peace_receiver_head_original=nullptr;
static bool peace_receiver_head_installed=false;
static uintptr_t peace_receiver_head_callers[16]{};
static unsigned peace_receiver_head_caller_count=0;
static SRWLOCK peace_receiver_head_lock=SRWLOCK_INIT;

static void* peace_receiver_head_observe(void* receiver) {
    const DWORD incoming_error=GetLastError();
    const uintptr_t caller=reinterpret_cast<uintptr_t>(__builtin_return_address(0));
    void* result=peace_receiver_head_original?peace_receiver_head_original(receiver):nullptr;
    const DWORD outgoing_error=GetLastError();
    bool emit=false;
    if (caller>=base+0x1000 && caller<base+0x1b66000
        && TryAcquireSRWLockExclusive(&peace_receiver_head_lock)) {
        bool seen=false;
        for (unsigned i=0;i<peace_receiver_head_caller_count;++i)
            seen=seen || peace_receiver_head_callers[i]==caller;
        if (!seen && peace_receiver_head_caller_count<16) {
            peace_receiver_head_callers[peace_receiver_head_caller_count++]=caller;
            emit=true;
        }
        ReleaseSRWLockExclusive(&peace_receiver_head_lock);
    }
    if (emit) {
        const uintptr_t address=reinterpret_cast<uintptr_t>(receiver);
        uintptr_t head=0,tail=0; uint32_t count=0;
        const bool readable=read(address+0xc8,head) && read(address+0xd0,tail)
            && read(address+0xd8,count);
        char message[800]{};
        snprintf(message,sizeof(message),
            "{\"event\":\"native_peace_receiver_head_access\",\"private\":true,"
            "\"session_id\":\"%lu-%llx\",\"caller_return_rva\":\"0x%llx\","
            "\"receiver\":\"0x%llx\",\"native_return_matches\":%s,\"list_readable\":%s,"
            "\"head\":\"0x%llx\",\"tail\":\"0x%llx\",\"count\":%u,\"thread\":%lu}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
            static_cast<unsigned long long>(caller-base),static_cast<unsigned long long>(address),
            result==reinterpret_cast<void*>(address+0xc8)?"true":"false",readable?"true":"false",
            static_cast<unsigned long long>(head),static_cast<unsigned long long>(tail),count,
            static_cast<unsigned long>(GetCurrentThreadId()));
        line(message);
    }
    (void)incoming_error;
    SetLastError(outgoing_error);
    return result;
}

static bool peace_receiver_observer_install() noexcept {
    auto* slot=reinterpret_cast<void**>(base+0x1d95fd8+0x48);
    void* expected=reinterpret_cast<void*>(base+0x8b0e0),*actual=nullptr;
    if (!read(reinterpret_cast<uintptr_t>(slot),actual) || actual!=expected) return false;
    peace_receiver_head_original=reinterpret_cast<PeaceReceiverHeadMethod>(expected);
    DWORD protection=0,ignored=0;
    if (!VirtualProtect(slot,8,PAGE_READWRITE,&protection)) return false;
    void* hook=reinterpret_cast<void*>(&peace_receiver_head_observe);
    const bool installed=InterlockedCompareExchangePointer(
        reinterpret_cast<void* volatile*>(slot),hook,expected)==expected;
    const bool restored=VirtualProtect(slot,8,protection,&ignored)!=FALSE;
    if (!installed || !restored) {
        const bool reverted=!installed || InterlockedCompareExchangePointer(
            reinterpret_cast<void* volatile*>(slot),expected,hook)==hook;
        const bool protection_restored=VirtualProtect(slot,8,protection,&ignored)!=FALSE;
        lifecycle_rollback_incomplete=lifecycle_rollback_incomplete || !reverted || !protection_restored;
        return false;
    }
    peace_receiver_head_installed=true;
    return true;
}

static bool peace_receiver_observer_rollback() noexcept {
    if (!peace_receiver_head_installed) return true;
    auto* slot=reinterpret_cast<void**>(base+0x1d95fd8+0x48);
    DWORD protection=0,ignored=0;
    if (!VirtualProtect(slot,8,PAGE_READWRITE,&protection)) return false;
    void* expected=reinterpret_cast<void*>(base+0x8b0e0);
    void* hook=reinterpret_cast<void*>(&peace_receiver_head_observe);
    void* previous=InterlockedCompareExchangePointer(
        reinterpret_cast<void* volatile*>(slot),expected,hook);
    const bool restored=VirtualProtect(slot,8,protection,&ignored)!=FALSE;
    const bool complete=(previous==hook || previous==expected) && restored;
    if (complete) peace_receiver_head_installed=false;
    return complete;
}
