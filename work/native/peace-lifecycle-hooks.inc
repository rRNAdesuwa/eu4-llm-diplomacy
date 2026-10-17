// Peace Offer field-reader hook.
//
// The Peace vtable has its own +0x20 reader entry and its own native method.
// This include only performs an identity-checked slot installation and
// rollback.  The assembly shim preserves the complete volatile Win64 call
// surface and tail-jumps to the captured original; the shared observer does
// the bounded read-only observation.

static const uintptr_t lifecycle_peace_field_reader_method_rva=0x59be10;

[[maybe_unused]] static bool lifecycle_install_peace_field_reader() {
    LONG state=InterlockedCompareExchange(
        &lifecycle_peace_field_reader_install_state,1,0);
    if (state==2) return true;
    if (state!=0) return false;

    void** slot=reinterpret_cast<void**>(
        base+lifecycle_peace_vtable_rva+0x20);
    void* expected_method=reinterpret_cast<void*>(
        base+lifecycle_peace_field_reader_method_rva);
    void* actual=nullptr;
    if (!read(reinterpret_cast<uintptr_t>(slot),actual)
        || actual!=expected_method) {
        InterlockedExchange(&lifecycle_peace_field_reader_install_state,-1);
        return false;
    }
    bridge_peace_field_reader_original=actual;

    DWORD protection=0,ignored=0;
    if (!VirtualProtect(slot,8,PAGE_READWRITE,&protection)) {
        InterlockedExchange(&lifecycle_peace_field_reader_install_state,-1);
        return false;
    }
    void* hook=reinterpret_cast<void*>(&bridge_peace_field_reader_stub);
    bool installed=InterlockedCompareExchangePointer(
        reinterpret_cast<void* volatile*>(slot),hook,actual)==actual;
    bool restored=VirtualProtect(slot,8,protection,&ignored)!=FALSE;
    if (!restored) {
        bool reverted=!installed || InterlockedCompareExchangePointer(
            reinterpret_cast<void* volatile*>(slot),actual,hook)==hook;
        DWORD retry_protection=0,retry_ignored=0;
        bool retry=VirtualProtect(slot,8,PAGE_READWRITE,&retry_protection)
            && VirtualProtect(slot,8,protection,&retry_ignored);
        lifecycle_rollback_incomplete=lifecycle_rollback_incomplete
            || !reverted || !retry;
        InterlockedExchange(&lifecycle_peace_field_reader_install_state,-1);
        return false;
    }
    if (!installed) {
        InterlockedExchange(&lifecycle_peace_field_reader_install_state,-1);
        return false;
    }
    InterlockedExchange(&lifecycle_peace_field_reader_install_state,2);
    return true;
}

[[maybe_unused]] static bool lifecycle_rollback_peace_field_reader() {
    LONG state=InterlockedCompareExchange(
        &lifecycle_peace_field_reader_install_state,0,0);
    if (state==0) return true;
    void** slot=reinterpret_cast<void**>(
        base+lifecycle_peace_vtable_rva+0x20);
    void* actual=nullptr;
    if (!read(reinterpret_cast<uintptr_t>(slot),actual)) {
        lifecycle_rollback_incomplete=true;
        return false;
    }
    void* expected=reinterpret_cast<void*>(
        base+lifecycle_peace_field_reader_method_rva);
    void* hook=reinterpret_cast<void*>(&bridge_peace_field_reader_stub);
    if (actual==expected) {
        InterlockedExchange(&lifecycle_peace_field_reader_install_state,0);
        return true;
    }
    if (actual!=hook) {
        lifecycle_rollback_incomplete=true;
        return false;
    }
    DWORD protection=0,ignored=0;
    if (!VirtualProtect(slot,8,PAGE_READWRITE,&protection)) {
        lifecycle_rollback_incomplete=true;
        return false;
    }
    void* previous=InterlockedCompareExchangePointer(
        reinterpret_cast<void* volatile*>(slot),expected,hook);
    bool swapped=previous==hook || previous==expected;
    bool restored=VirtualProtect(slot,8,protection,&ignored)!=FALSE;
    if (swapped && restored) InterlockedExchange(
        &lifecycle_peace_field_reader_install_state,0);
    else lifecycle_rollback_incomplete=true;
    return swapped && restored;
}
