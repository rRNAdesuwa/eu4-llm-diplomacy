// Bounded Win64 inline-patch transaction helper.
//
// This include deliberately contains no game-specific addresses or calls.  A
// caller supplies the target bytes, the expected/replacement signatures, and
// an already allocated executable trampoline which contains the original
// bytes and its return jump.  The trampoline must remain executable for the
// lifetime of the process after the first INT3 is published: a CPU may have
// cached an entry breakpoint after the patch has been rolled back.
//
// The transaction uses a process-local VEH as an INT3 barrier.  It is
// installed and the immutable target -> trampoline table is populated before
// the first byte is changed.  The VEH handles exactly EXCEPTION_BREAKPOINT at
// an owned target address and redirects RIP to that target's trampoline; all
// other exceptions continue the normal search.  No logging or file I/O is
// performed while the barrier or thread suspension is active.

#ifndef BRIDGE_ENTRY_PATCH_TRANSACTION_INC
#define BRIDGE_ENTRY_PATCH_TRANSACTION_INC

#include <windows.h>
#include <tlhelp32.h>
#include <cstddef>
#include <cstdint>
#include <cstring>
#if defined(_MSC_VER)
#include <intrin.h>
#endif

namespace bridge_entry_patch {

static constexpr unsigned kMaxTargets=4;
static constexpr unsigned kMaxPatchBytes=32;
static constexpr unsigned kMaxRegistryTargets=64;
static constexpr unsigned kMaxPages=8;       // 2 pages per target at most.
static constexpr unsigned kMaxThreads=2048;  // bounded snapshot/pending store.
static constexpr unsigned kMaxErrorRecords=256;

enum class PatchStatus : unsigned char {
    fatal=0,
    published=1,
    success=2,
    rollback_complete=3,
    restart_required=4
};

enum class FailureStage : unsigned char {
    none=0,
    busy,
    validation,
    target_query,
    protection_prepare,
    handler_register,
    barrier_publish,
    thread_snapshot,
    thread_open,
    thread_suspend,
    thread_context,
    signature_recheck,
    body_write,
    commit,
    protection_restore,
    thread_resume,
    rollback,
    pending_retry
};

struct PatchErrorRecord {
    FailureStage stage;
    const char* api;
    DWORD code;
};

struct PatchResult {
    PatchStatus status=PatchStatus::fatal;
    bool published=false;          // At least one target byte became INT3.
    bool success=false;            // Final requested byte image is installed.
    bool rollback_complete=false;  // Source image was restored under the barrier.
    bool threads_resumed=false;    // Every suspended thread was resumed.
    bool protection_restored=false;
    FailureStage failure_stage=FailureStage::none;
    DWORD error=ERROR_SUCCESS;
    DWORD error_count=0;
    unsigned error_records=0;
    bool errors_truncated=false;
    unsigned thread_count=0;
    unsigned suspended_count=0;
    unsigned pending_count=0;
    PatchErrorRecord errors[kMaxErrorRecords]{};
};

// `expected` and `replacement` are immutable caller-owned byte arrays.  The
// caller must keep them valid for the duration of the operation.  The
// trampoline is executable memory prepared by the caller; this helper never
// allocates, copies, or frees it.
struct PatchTarget {
    void* address=nullptr;
    unsigned size=0;
    const unsigned char* expected=nullptr;
    const unsigned char* replacement=nullptr;
    const void* original_trampoline=nullptr;
    SIZE_T original_trampoline_size=0;
};

struct PatchPlan {
    unsigned count=0;
    PatchTarget targets[kMaxTargets]{};
};

static void entry_patch_error(PatchResult& result,FailureStage stage,const char* api,DWORD code) {
    if (!code) code=ERROR_GEN_FAILURE;
    if (result.failure_stage==FailureStage::none) result.failure_stage=stage;
    if (result.error==ERROR_SUCCESS) result.error=code;
    ++result.error_count;
    if (result.error_records<kMaxErrorRecords) {
        result.errors[result.error_records++]={stage,api,code};
    } else {
        result.errors_truncated=true;
    }
}

static void entry_patch_failure(PatchResult& result,FailureStage stage,const char* api,DWORD code=ERROR_INVALID_DATA) {
    entry_patch_error(result,stage,api,code);
}

static bool entry_patch_executable_protection(DWORD protection) {
    switch (protection&0xffu) {
    case PAGE_EXECUTE:
    case PAGE_EXECUTE_READ:
    case PAGE_EXECUTE_READWRITE:
    case PAGE_EXECUTE_WRITECOPY:
        return true;
    default:
        return false;
    }
}

struct EntryPatchPage {
    unsigned char* base=nullptr;
    SIZE_T size=0;
    DWORD original_protection=0;
    bool changed=false;
};

enum : LONG {
    entry_patch_free=0,
    entry_patch_reserved=1,
    entry_patch_published=2
};

struct EntryPatchVehTarget {
    volatile LONG state=entry_patch_free;
    unsigned char* target=nullptr;
    const void* trampoline=nullptr;
    SIZE_T trampoline_size=0;
};

// Published entries are never cleared after a target has emitted INT3.  This
// is intentional: removing a handler or freeing a trampoline after a cached
// breakpoint would turn an otherwise harmless stale instruction-cache entry
// into an invalid redirect.  The table is bounded and new transactions fail
// explicitly when it is full.
static EntryPatchVehTarget entry_patch_veh_targets[kMaxRegistryTargets]{};
static PVOID entry_patch_veh_handle=nullptr;
static volatile LONG entry_patch_gate=0;

struct EntryPatchWorkTarget {
    PatchTarget target{};
    const unsigned char* source=nullptr;
    const unsigned char* destination=nullptr;
    unsigned registry_index=0;
    bool reserved_here=false;
    bool barrier_written=false;
    bool committed=false;
};

struct EntryPatchWorkspace {
    EntryPatchWorkTarget targets[kMaxTargets]{};
    unsigned count=0;
    EntryPatchPage pages[kMaxPages]{};
    unsigned page_count=0;
    bool pages_prepared=false;
    bool veh_added_here=false;
    bool any_barrier=false;
    bool any_commit=false;
};

struct EntryPatchThread {
    HANDLE handle=nullptr;
    DWORD id=0;
    bool suspended=false;
    bool resumed=false;
    unsigned resume_attempts=0;
};

struct EntryPatchPendingThread {
    HANDLE handle=nullptr;
    DWORD id=0;
    bool resumed=false;
    unsigned resume_attempts=0;
};

static EntryPatchThread entry_patch_threads[kMaxThreads]{};
static unsigned entry_patch_thread_count=0;
static EntryPatchPendingThread entry_patch_pending[kMaxThreads]{};
static unsigned entry_patch_pending_count=0;

static LONG CALLBACK entry_patch_vectored_handler(PEXCEPTION_POINTERS info) {
    if (!info || !info->ExceptionRecord || !info->ContextRecord
        || info->ExceptionRecord->ExceptionCode!=EXCEPTION_BREAKPOINT) {
        return EXCEPTION_CONTINUE_SEARCH;
    }
    const unsigned char* exception_address=static_cast<const unsigned char*>(info->ExceptionRecord->ExceptionAddress);
    if (!exception_address) return EXCEPTION_CONTINUE_SEARCH;

    for (unsigned i=0;i<kMaxRegistryTargets;++i) {
        EntryPatchVehTarget& entry=entry_patch_veh_targets[i];
        const LONG state=InterlockedCompareExchange(&entry.state,0,0);
        if (state!=entry_patch_published) continue;
        MemoryBarrier();
        if (exception_address!=entry.target || !entry.trampoline) continue;
#if defined(_WIN64)
        info->ContextRecord->Rip=reinterpret_cast<DWORD64>(entry.trampoline);
#else
        info->ContextRecord->Eip=reinterpret_cast<DWORD>(entry.trampoline);
#endif
        return EXCEPTION_CONTINUE_EXECUTION;
    }
    return EXCEPTION_CONTINUE_SEARCH;
}

static bool entry_patch_take_gate(PatchResult& result) {
    if (InterlockedCompareExchange(&entry_patch_gate,1,0)==0) return true;
    entry_patch_failure(result,FailureStage::busy,"InterlockedCompareExchange",ERROR_BUSY);
    result.status=PatchStatus::fatal;
    return false;
}

static void entry_patch_release_gate() {
    InterlockedExchange(&entry_patch_gate,0);
}

// MinGW does not expose the MSVC spelling of the byte exchange intrinsic,
// while both toolchains emit an atomic xchg byte for these forms on Win64.
static unsigned char entry_patch_atomic_byte_exchange(volatile unsigned char* address,unsigned char value) {
#if defined(_MSC_VER)
    return static_cast<unsigned char>(_InterlockedExchange8(
        reinterpret_cast<volatile char*>(address),static_cast<char>(value)));
#else
    return __atomic_exchange_n(address,value,__ATOMIC_SEQ_CST);
#endif
}

static bool entry_patch_range_overlaps(const unsigned char* left,unsigned left_size,
    const unsigned char* right,unsigned right_size) {
    const uintptr_t left_begin=reinterpret_cast<uintptr_t>(left);
    const uintptr_t right_begin=reinterpret_cast<uintptr_t>(right);
    return left_begin<right_begin+right_size && right_begin<left_begin+left_size;
}

static bool entry_patch_validate_executable(const void* address,SIZE_T size,PatchResult& result) {
    if (!address || !size) {
        entry_patch_failure(result,FailureStage::validation,"trampoline_arguments");
        return false;
    }
    MEMORY_BASIC_INFORMATION memory{};
    if (VirtualQuery(address,&memory,sizeof(memory))!=sizeof(memory)) {
        entry_patch_failure(result,FailureStage::target_query,"VirtualQuery",GetLastError());
        return false;
    }
    if (memory.State!=MEM_COMMIT || (memory.Protect&PAGE_GUARD)
        || !entry_patch_executable_protection(memory.Protect)) {
        entry_patch_failure(result,FailureStage::validation,"trampoline_protection",ERROR_ACCESS_DENIED);
        return false;
    }
    const uintptr_t end=reinterpret_cast<uintptr_t>(address)+size-1;
    const uintptr_t region_end=reinterpret_cast<uintptr_t>(memory.BaseAddress)+memory.RegionSize;
    if (end<reinterpret_cast<uintptr_t>(address) || end>=region_end) {
        entry_patch_failure(result,FailureStage::validation,"trampoline_range",ERROR_INVALID_ADDRESS);
        return false;
    }
    return true;
}

static bool entry_patch_validate_plan(const PatchPlan& plan,bool rollback,
    EntryPatchWorkspace& workspace,PatchResult& result) {
    if (!plan.count || plan.count>kMaxTargets) {
        entry_patch_failure(result,FailureStage::validation,"target_count",ERROR_INVALID_PARAMETER);
        return false;
    }
    if (entry_patch_pending_count) {
        entry_patch_failure(result,FailureStage::pending_retry,"pending_thread_handles",ERROR_BUSY);
        result.status=PatchStatus::restart_required;
        return false;
    }

    workspace.count=plan.count;
    for (unsigned i=0;i<plan.count;++i) {
        const PatchTarget& input=plan.targets[i];
        EntryPatchWorkTarget& output=workspace.targets[i];
        output.target=input;
        output.source=rollback?input.replacement:input.expected;
        output.destination=rollback?input.expected:input.replacement;
        if (!input.address || !output.source || !output.destination
            || input.size==0 || input.size>kMaxPatchBytes
            || !input.original_trampoline || !input.original_trampoline_size) {
            entry_patch_failure(result,FailureStage::validation,"target_arguments",ERROR_INVALID_PARAMETER);
            return false;
        }
        const auto address=static_cast<unsigned char*>(input.address);
        if (reinterpret_cast<uintptr_t>(address)<0x10000
            || reinterpret_cast<uintptr_t>(output.source)<0x10000
            || reinterpret_cast<uintptr_t>(output.destination)<0x10000) {
            entry_patch_failure(result,FailureStage::validation,"target_address",ERROR_INVALID_ADDRESS);
            return false;
        }
        // Query the target before the first memcmp so a malformed caller
        // address is reported as a validation error instead of faulting.
        if (!entry_patch_validate_executable(input.address,input.size,result)) return false;
        if (output.source[0]==0xcc || output.destination[0]==0xcc) {
            entry_patch_failure(result,FailureStage::validation,"breakpoint_signature",ERROR_INVALID_DATA);
            return false;
        }
        if (memcmp(address,output.source,input.size)!=0) {
            entry_patch_failure(result,FailureStage::validation,"initial_signature",ERROR_INVALID_DATA);
            return false;
        }
        if (!entry_patch_validate_executable(input.original_trampoline,input.original_trampoline_size,result)) return false;
        for (unsigned j=0;j<i;++j) {
            const auto other=static_cast<unsigned char*>(workspace.targets[j].target.address);
            if (entry_patch_range_overlaps(address,input.size,other,workspace.targets[j].target.size)) {
                entry_patch_failure(result,FailureStage::validation,"target_overlap",ERROR_INVALID_PARAMETER);
                return false;
            }
        }
    }
    return true;
}

static bool entry_patch_reserve_target(EntryPatchWorkTarget& work,PatchResult& result) {
    auto address=static_cast<unsigned char*>(work.target.address);
    for (unsigned i=0;i<kMaxRegistryTargets;++i) {
        EntryPatchVehTarget& entry=entry_patch_veh_targets[i];
        const LONG state=InterlockedCompareExchange(&entry.state,0,0);
        if (state==entry_patch_published && entry.target==address) {
            if (entry.trampoline!=work.target.original_trampoline
                || entry.trampoline_size!=work.target.original_trampoline_size) {
                entry_patch_failure(result,FailureStage::handler_register,"trampoline_identity",ERROR_INVALID_DATA);
                return false;
            }
            work.registry_index=i;
            return true;
        }
    }
    for (unsigned i=0;i<kMaxRegistryTargets;++i) {
        EntryPatchVehTarget& entry=entry_patch_veh_targets[i];
        if (InterlockedCompareExchange(&entry.state,entry_patch_reserved,entry_patch_free)!=entry_patch_free) continue;
        entry.target=address;
        entry.trampoline=work.target.original_trampoline;
        entry.trampoline_size=work.target.original_trampoline_size;
        MemoryBarrier();
        InterlockedExchange(&entry.state,entry_patch_published);
        work.registry_index=i;
        work.reserved_here=true;
        return true;
    }
    entry_patch_failure(result,FailureStage::handler_register,"entry_patch_veh_registry",ERROR_INSUFFICIENT_BUFFER);
    return false;
}

static void entry_patch_release_reserved(EntryPatchWorkspace& workspace) {
    if (workspace.any_barrier) return;
    for (unsigned i=0;i<workspace.count;++i) {
        if (!workspace.targets[i].reserved_here) continue;
        EntryPatchVehTarget& entry=entry_patch_veh_targets[workspace.targets[i].registry_index];
        entry.target=nullptr;
        entry.trampoline=nullptr;
        entry.trampoline_size=0;
        MemoryBarrier();
        InterlockedExchange(&entry.state,entry_patch_free);
        workspace.targets[i].reserved_here=false;
    }
}

static bool entry_patch_ensure_veh(EntryPatchWorkspace& workspace,PatchResult& result) {
    if (entry_patch_veh_handle) return true;
    PVOID handle=AddVectoredExceptionHandler(1,&entry_patch_vectored_handler);
    if (!handle) {
        entry_patch_failure(result,FailureStage::handler_register,"AddVectoredExceptionHandler",GetLastError());
        return false;
    }
    entry_patch_veh_handle=handle;
    workspace.veh_added_here=true;
    return true;
}

static void entry_patch_remove_unpublished_veh(EntryPatchWorkspace& workspace,PatchResult& result) {
    if (!workspace.veh_added_here || workspace.any_barrier || !entry_patch_veh_handle) return;
    if (!RemoveVectoredExceptionHandler(entry_patch_veh_handle)) {
        entry_patch_failure(result,FailureStage::handler_register,"RemoveVectoredExceptionHandler",GetLastError());
        return;
    }
    entry_patch_veh_handle=nullptr;
    workspace.veh_added_here=false;
}

static bool entry_patch_build_pages(EntryPatchWorkspace& workspace,PatchResult& result) {
    SYSTEM_INFO system_info{};
    GetSystemInfo(&system_info);
    const SIZE_T page_size=system_info.dwPageSize;
    if (!page_size || (page_size&(page_size-1))!=0) {
        entry_patch_failure(result,FailureStage::target_query,"GetSystemInfo",ERROR_INVALID_DATA);
        return false;
    }
    for (unsigned i=0;i<workspace.count;++i) {
        const uintptr_t begin=reinterpret_cast<uintptr_t>(workspace.targets[i].target.address);
        const uintptr_t end=begin+workspace.targets[i].target.size-1;
        if (end<begin) {
            entry_patch_failure(result,FailureStage::target_query,"target_range",ERROR_INVALID_ADDRESS);
            return false;
        }
        uintptr_t page=begin&~(page_size-1);
        const uintptr_t final_page=end&~(page_size-1);
        for (;;) {
            MEMORY_BASIC_INFORMATION memory{};
            if (VirtualQuery(reinterpret_cast<const void*>(page),&memory,sizeof(memory))!=sizeof(memory)) {
                entry_patch_failure(result,FailureStage::target_query,"VirtualQuery",GetLastError());
                return false;
            }
            if (memory.State!=MEM_COMMIT || (memory.Protect&PAGE_GUARD)
                || !entry_patch_executable_protection(memory.Protect)) {
                entry_patch_failure(result,FailureStage::target_query,"target_page_protection",ERROR_ACCESS_DENIED);
                return false;
            }
            bool exists=false;
            for (unsigned p=0;p<workspace.page_count;++p) {
                if (reinterpret_cast<uintptr_t>(workspace.pages[p].base)==page) { exists=true; break; }
            }
            if (!exists) {
                if (workspace.page_count>=kMaxPages) {
                    entry_patch_failure(result,FailureStage::target_query,"page_capacity",ERROR_INSUFFICIENT_BUFFER);
                    return false;
                }
                EntryPatchPage& record=workspace.pages[workspace.page_count++];
                record.base=reinterpret_cast<unsigned char*>(page);
                record.size=page_size;
                record.original_protection=0;
                record.changed=false;
            }
            if (page==final_page) break;
            page+=page_size;
        }
    }
    return true;
}

static bool entry_patch_make_pages_writable(EntryPatchWorkspace& workspace,PatchResult& result) {
    for (unsigned i=0;i<workspace.page_count;++i) {
        EntryPatchPage& page=workspace.pages[i];
        DWORD previous=0;
        if (!VirtualProtect(page.base,page.size,PAGE_EXECUTE_READWRITE,&previous)) {
            entry_patch_failure(result,FailureStage::protection_prepare,"VirtualProtect",GetLastError());
            bool restored=true;
            for (unsigned j=i;j>0;--j) {
                EntryPatchPage& old_page=workspace.pages[j-1];
                if (!old_page.changed) continue;
                DWORD ignored=0;
                if (!VirtualProtect(old_page.base,old_page.size,old_page.original_protection,&ignored)) {
                    entry_patch_failure(result,FailureStage::protection_restore,"VirtualProtect",GetLastError());
                    restored=false;
                } else old_page.changed=false;
            }
            result.protection_restored=restored;
            return false;
        }
        page.original_protection=previous;
        page.changed=true;
    }
    workspace.pages_prepared=true;
    return true;
}

static bool entry_patch_restore_pages(EntryPatchWorkspace& workspace,PatchResult& result) {
    bool restored=true;
    for (unsigned i=workspace.page_count;i>0;--i) {
        EntryPatchPage& page=workspace.pages[i-1];
        if (!page.changed) continue;
        DWORD ignored=0;
        if (!VirtualProtect(page.base,page.size,page.original_protection,&ignored)) {
            entry_patch_failure(result,FailureStage::protection_restore,"VirtualProtect",GetLastError());
            restored=false;
        } else page.changed=false;
    }
    result.protection_restored=restored;
    return restored;
}

static bool entry_patch_flush(unsigned char* address,SIZE_T size,PatchResult& result,FailureStage stage) {
    if (FlushInstructionCache(GetCurrentProcess(),address,size)) return true;
    entry_patch_failure(result,stage,"FlushInstructionCache",GetLastError());
    return false;
}

static bool entry_patch_verify_source(const EntryPatchWorkspace& workspace,PatchResult& result,FailureStage stage) {
    for (unsigned i=0;i<workspace.count;++i) {
        const EntryPatchWorkTarget& target=workspace.targets[i];
        if (memcmp(target.target.address,target.source,target.target.size)!=0) {
            entry_patch_failure(result,stage,"signature",ERROR_INVALID_DATA);
            return false;
        }
    }
    return true;
}

static bool entry_patch_publish_barrier(EntryPatchWorkspace& workspace,PatchResult& result) {
    for (unsigned i=0;i<workspace.count;++i) {
        EntryPatchWorkTarget& target=workspace.targets[i];
        entry_patch_atomic_byte_exchange(reinterpret_cast<volatile unsigned char*>(target.target.address),0xcc);
        target.barrier_written=true;
        workspace.any_barrier=true;
        result.published=true;
        if (!entry_patch_flush(static_cast<unsigned char*>(target.target.address),1,result,FailureStage::barrier_publish)) return false;
    }
    return true;
}

static bool entry_patch_verify_barrier(const EntryPatchWorkspace& workspace,PatchResult& result) {
    for (unsigned i=0;i<workspace.count;++i) {
        const EntryPatchWorkTarget& target=workspace.targets[i];
        const auto address=static_cast<const unsigned char*>(target.target.address);
        if (address[0]!=0xcc || (target.target.size>1
            && memcmp(address+1,target.source+1,target.target.size-1)!=0)) {
            entry_patch_failure(result,FailureStage::signature_recheck,"barrier_signature",ERROR_INVALID_DATA);
            return false;
        }
    }
    return true;
}

static bool entry_patch_write_body(EntryPatchWorkspace& workspace,PatchResult& result) {
    for (unsigned i=0;i<workspace.count;++i) {
        EntryPatchWorkTarget& target=workspace.targets[i];
        if (target.target.size>1) {
            memcpy(static_cast<unsigned char*>(target.target.address)+1,target.destination+1,target.target.size-1);
            if (!entry_patch_flush(static_cast<unsigned char*>(target.target.address),target.target.size,result,FailureStage::body_write)) return false;
        }
    }
    return true;
}

static bool entry_patch_commit_bytes(EntryPatchWorkspace& workspace,PatchResult& result) {
    for (unsigned i=0;i<workspace.count;++i) {
        const EntryPatchWorkTarget& target=workspace.targets[i];
        const auto address=static_cast<const unsigned char*>(target.target.address);
        if (address[0]!=0xcc || (target.target.size>1
            && memcmp(address+1,target.destination+1,target.target.size-1)!=0)) {
            entry_patch_failure(result,FailureStage::commit,"replacement_body_signature",ERROR_INVALID_DATA);
            return false;
        }
    }
    for (unsigned i=0;i<workspace.count;++i) {
        EntryPatchWorkTarget& target=workspace.targets[i];
        entry_patch_atomic_byte_exchange(reinterpret_cast<volatile unsigned char*>(target.target.address),
            target.destination[0]);
        target.committed=true;
        workspace.any_commit=true;
        if (!entry_patch_flush(static_cast<unsigned char*>(target.target.address),target.target.size,result,FailureStage::commit)) return false;
    }
    return true;
}

// Restore the image that was current at transaction entry.  It is called
// while the target is still protected by INT3, except in the degenerate case
// where no barrier was published.  The source/destination arguments are
// swapped by guarded_patch_rollback(), so a failed rollback attempt leaves the
// original replacement installed rather than silently losing it.
static bool entry_patch_restore_source(EntryPatchWorkspace& workspace,PatchResult& result) {
    bool restored=true;
    for (unsigned i=0;i<workspace.count;++i) {
        EntryPatchWorkTarget& target=workspace.targets[i];
        auto address=static_cast<unsigned char*>(target.target.address);
        if (memcmp(address,target.source,target.target.size)==0) continue;

        const bool full_destination=memcmp(address,target.destination,target.target.size)==0;
        const bool barrier_body=(address[0]==0xcc && (target.target.size==1
            || memcmp(address+1,target.source+1,target.target.size-1)==0
            || memcmp(address+1,target.destination+1,target.target.size-1)==0));
        if (!full_destination && !barrier_body) {
            entry_patch_failure(result,FailureStage::rollback,"rollback_signature",ERROR_INVALID_DATA);
            restored=false;
            continue;
        }
        if (address[0]!=0xcc) {
            entry_patch_atomic_byte_exchange(reinterpret_cast<volatile unsigned char*>(address),0xcc);
            target.barrier_written=true;
            workspace.any_barrier=true;
            result.published=true;
            if (!entry_patch_flush(address,1,result,FailureStage::rollback)) { restored=false; continue; }
        }
        if (target.target.size>1) {
            memcpy(address+1,target.source+1,target.target.size-1);
            if (!entry_patch_flush(address,target.target.size,result,FailureStage::rollback)) {
                restored=false;
                continue;
            }
        }
        entry_patch_atomic_byte_exchange(reinterpret_cast<volatile unsigned char*>(address),target.source[0]);
        if (!entry_patch_flush(address,target.target.size,result,FailureStage::rollback)) restored=false;
    }
    return restored;
}

static bool entry_patch_rip_in_body(const EntryPatchWorkspace& workspace,uintptr_t rip) {
    for (unsigned i=0;i<workspace.count;++i) {
        const uintptr_t begin=reinterpret_cast<uintptr_t>(workspace.targets[i].target.address)+1;
        const uintptr_t end=reinterpret_cast<uintptr_t>(workspace.targets[i].target.address)+workspace.targets[i].target.size;
        if (begin<end && rip>=begin && rip<end) return true;
    }
    return false;
}

static bool entry_patch_close_snapshot(HANDLE snapshot,PatchResult& result) {
    if (snapshot==INVALID_HANDLE_VALUE) return true;
    if (CloseHandle(snapshot)) return true;
    entry_patch_failure(result,FailureStage::thread_snapshot,"CloseHandle",GetLastError());
    return false;
}

static bool entry_patch_enumerate_and_suspend(const EntryPatchWorkspace& workspace,PatchResult& result) {
    entry_patch_thread_count=0;
    for (unsigned i=0;i<kMaxThreads;++i) entry_patch_threads[i]=EntryPatchThread{};
    const DWORD process_id=GetCurrentProcessId();
    const DWORD current_thread=GetCurrentThreadId();
    HANDLE snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD,0);
    if (snapshot==INVALID_HANDLE_VALUE) {
        entry_patch_failure(result,FailureStage::thread_snapshot,"CreateToolhelp32Snapshot",GetLastError());
        return false;
    }

    bool enumeration_ok=true;
    THREADENTRY32 entry{};
    entry.dwSize=sizeof(entry);
    BOOL has_entry=Thread32First(snapshot,&entry);
    if (!has_entry) {
        const DWORD code=GetLastError();
        if (code!=ERROR_NO_MORE_FILES) {
            entry_patch_failure(result,FailureStage::thread_snapshot,"Thread32First",code);
            enumeration_ok=false;
        }
    }
    while (enumeration_ok && has_entry) {
        if (entry.th32OwnerProcessID==process_id && entry.th32ThreadID!=current_thread) {
            if (entry_patch_thread_count>=kMaxThreads) {
                entry_patch_failure(result,FailureStage::thread_open,"thread_capacity",ERROR_INSUFFICIENT_BUFFER);
                enumeration_ok=false;
                break;
            }
            HANDLE thread=OpenThread(THREAD_SUSPEND_RESUME|THREAD_GET_CONTEXT|THREAD_QUERY_INFORMATION,
                FALSE,entry.th32ThreadID);
            if (!thread) {
                entry_patch_failure(result,FailureStage::thread_open,"OpenThread",GetLastError());
                enumeration_ok=false;
                break;
            }
            EntryPatchThread& slot=entry_patch_threads[entry_patch_thread_count++];
            slot.handle=thread;
            slot.id=entry.th32ThreadID;
        }
        entry.dwSize=sizeof(entry);
        has_entry=Thread32Next(snapshot,&entry);
        if (!has_entry) {
            const DWORD code=GetLastError();
            if (code!=ERROR_NO_MORE_FILES) {
                entry_patch_failure(result,FailureStage::thread_snapshot,"Thread32Next",code);
                enumeration_ok=false;
            }
            break;
        }
    }
    if (!entry_patch_close_snapshot(snapshot,result)) enumeration_ok=false;
    result.thread_count=entry_patch_thread_count;
    if (!enumeration_ok) return false;

    for (unsigned i=0;i<entry_patch_thread_count;++i) {
        EntryPatchThread& slot=entry_patch_threads[i];
        if (SuspendThread(slot.handle)==static_cast<DWORD>(-1)) {
            entry_patch_failure(result,FailureStage::thread_suspend,"SuspendThread",GetLastError());
            return false;
        }
        slot.suspended=true;
        ++result.suspended_count;
        CONTEXT context{};
        context.ContextFlags=CONTEXT_CONTROL;
        if (!GetThreadContext(slot.handle,&context)) {
            entry_patch_failure(result,FailureStage::thread_context,"GetThreadContext",GetLastError());
            return false;
        }
#if defined(_WIN64)
        const uintptr_t rip=static_cast<uintptr_t>(context.Rip);
#else
        const uintptr_t rip=static_cast<uintptr_t>(context.Eip);
#endif
        if (entry_patch_rip_in_body(workspace,rip)) {
            entry_patch_failure(result,FailureStage::thread_context,"thread_instruction_pointer",ERROR_BUSY);
            return false;
        }
    }
    return true;
}

static bool entry_patch_pending_add(HANDLE handle,DWORD id,bool resumed,unsigned attempts,PatchResult& result) {
    if (!handle) return true;
    if (entry_patch_pending_count>=kMaxThreads) {
        entry_patch_failure(result,FailureStage::thread_resume,"pending_thread_capacity",ERROR_INSUFFICIENT_BUFFER);
        return false;
    }
    EntryPatchPendingThread& pending=entry_patch_pending[entry_patch_pending_count++];
    pending.handle=handle;
    pending.id=id;
    pending.resumed=resumed;
    pending.resume_attempts=attempts;
    return true;
}

static bool entry_patch_resume_slot(EntryPatchThread& slot,PatchResult& result) {
    if (!slot.handle) return true;
    if (slot.suspended && !slot.resumed) {
        while (slot.resume_attempts<3) {
            ++slot.resume_attempts;
            if (ResumeThread(slot.handle)!=static_cast<DWORD>(-1)) {
                slot.resumed=true;
                break;
            }
            entry_patch_failure(result,FailureStage::thread_resume,"ResumeThread",GetLastError());
        }
        if (!slot.resumed) {
            if (entry_patch_pending_add(slot.handle,slot.id,false,slot.resume_attempts,result)) slot.handle=nullptr;
            return false;
        }
    }
    if (!CloseHandle(slot.handle)) {
        entry_patch_failure(result,FailureStage::thread_resume,"CloseHandle",GetLastError());
        // A handle whose SuspendThread never succeeded needs no future
        // ResumeThread call; retry_pending must only close it.
        const bool no_resume_needed=!slot.suspended || slot.resumed;
        if (entry_patch_pending_add(slot.handle,slot.id,no_resume_needed,slot.resume_attempts,result)) slot.handle=nullptr;
        return false;
    }
    slot.handle=nullptr;
    return true;
}

static bool entry_patch_resume_all(PatchResult& result) {
    bool all=true;
    for (unsigned i=0;i<entry_patch_thread_count;++i) {
        if (!entry_patch_resume_slot(entry_patch_threads[i],result)) all=false;
    }
    result.pending_count=entry_patch_pending_count;
    result.threads_resumed=all && entry_patch_pending_count==0;
    return result.threads_resumed;
}

static void entry_patch_set_failure_status(PatchResult& result,bool rollback_ok) {
    result.pending_count=entry_patch_pending_count;
    if (entry_patch_pending_count || !result.threads_resumed || !result.protection_restored || !rollback_ok) {
        result.status=PatchStatus::restart_required;
    } else if (rollback_ok && result.published) {
        result.rollback_complete=true;
        result.status=PatchStatus::rollback_complete;
    } else {
        result.status=PatchStatus::fatal;
    }
}

static PatchResult entry_patch_run(const PatchPlan& plan,bool rollback) {
    PatchResult result{};
    EntryPatchWorkspace workspace{};
    if (!entry_patch_take_gate(result)) return result;

    bool rollback_ok=false;
    bool resume_needed=false;
    bool operation_ok=false;

    if (!entry_patch_validate_plan(plan,rollback,workspace,result)) goto finish;
    for (unsigned i=0;i<workspace.count;++i) {
        if (!entry_patch_reserve_target(workspace.targets[i],result)) goto finish;
    }
    if (!entry_patch_ensure_veh(workspace,result)) goto finish;
    if (!entry_patch_build_pages(workspace,result)) goto finish;
    if (!entry_patch_make_pages_writable(workspace,result)) goto finish;
    // Second signature check after page preparation, immediately before CC.
    if (!entry_patch_verify_source(workspace,result,FailureStage::signature_recheck)) goto finish_with_pages;
    if (!entry_patch_publish_barrier(workspace,result)) goto rollback_before_threads;

    resume_needed=true;
    if (!entry_patch_enumerate_and_suspend(workspace,result)) goto rollback_with_threads;
    if (!entry_patch_verify_barrier(workspace,result)) goto rollback_with_threads;
    if (!entry_patch_write_body(workspace,result)) goto rollback_with_threads;
    if (!entry_patch_commit_bytes(workspace,result)) goto rollback_with_threads;

    if (!entry_patch_restore_pages(workspace,result)) goto finish_after_commit;
    if (!entry_patch_resume_all(result)) goto finish_after_commit;
    operation_ok=true;
    result.success=true;
    result.status=rollback?PatchStatus::rollback_complete:PatchStatus::success;
    result.rollback_complete=rollback;
    goto finish;

rollback_with_threads:
    if (workspace.any_commit) goto finish_after_commit;
    rollback_ok=entry_patch_restore_source(workspace,result);
    if (!entry_patch_restore_pages(workspace,result)) rollback_ok=false;
    if (resume_needed) entry_patch_resume_all(result);
    entry_patch_set_failure_status(result,rollback_ok);
    // Once a replacement byte0 was published, a newly-created thread could
    // have entered replacement code before the rollback barrier was restored.
    // Even if the byte image now compares equal to source, require guarded
    // restart/reconciliation rather than claiming a fully safe rollback.
    if (workspace.any_commit) result.status=PatchStatus::restart_required;
    goto finish;

rollback_before_threads:
    rollback_ok=entry_patch_restore_source(workspace,result);
    if (!entry_patch_restore_pages(workspace,result)) rollback_ok=false;
    entry_patch_set_failure_status(result,rollback_ok);
    goto finish;

finish_with_pages:
    if (!entry_patch_restore_pages(workspace,result)) result.status=PatchStatus::restart_required;
    result.threads_resumed=true;
    result.pending_count=entry_patch_pending_count;
    goto finish;

finish_after_commit:
    // A committed byte cannot be made safe to roll back while an unresumed
    // thread may already have entered the replacement.  Leave the published
    // image intact and require the caller's guarded restart/reconciliation.
    result.status=PatchStatus::restart_required;
    result.published=true;
    result.success=false;
    // Preserve a valid committed image while attempting every outstanding
    // cleanup. A failed page restore must never skip thread resumption.
    entry_patch_restore_pages(workspace,result);
    if (resume_needed) entry_patch_resume_all(result);
    goto finish;

finish:
    if (!result.protection_restored) {
        bool pages_clean=true;
        for (unsigned i=0;i<workspace.page_count;++i) pages_clean=pages_clean && !workspace.pages[i].changed;
        result.protection_restored=pages_clean;
    }
    if (!resume_needed && !result.threads_resumed) result.threads_resumed=entry_patch_pending_count==0;
    if (!workspace.any_barrier) {
        entry_patch_release_reserved(workspace);
        entry_patch_remove_unpublished_veh(workspace,result);
    }
    // A failure after a partial commit is intentionally not silently
    // converted into rollback_complete.  The restart_required status is the
    // safe answer when a thread could have observed replacement code.
    if (!operation_ok && workspace.any_commit && result.status!=PatchStatus::restart_required) {
        result.status=PatchStatus::restart_required;
    }
    result.pending_count=entry_patch_pending_count;
    entry_patch_release_gate();
    return result;
}

// Install `replacement` bytes over `expected` bytes.  All byte arrays and the
// executable original trampoline are caller-owned and must remain valid for
// the call; no game/native function is invoked here.
static PatchResult guarded_patch_apply(const PatchPlan& plan) {
    return entry_patch_run(plan,false);
}

// Restore `expected` bytes when the current image is exactly `replacement`.
// The same INT3 barrier is used, and the original trampoline remains
// registered even after a successful rollback.
static PatchResult guarded_patch_rollback(const PatchPlan& plan) {
    return entry_patch_run(plan,true);
}

// Retry only failed ResumeThread/CloseHandle cleanup.  A thread whose resume
// already succeeded is never resumed again; its handle is only closed.
static PatchResult guarded_patch_retry_pending() {
    PatchResult result{};
    if (!entry_patch_take_gate(result)) return result;
    bool all=true;
    unsigned i=0;
    while (i<entry_patch_pending_count) {
        EntryPatchPendingThread& pending=entry_patch_pending[i];
        if (!pending.resumed) {
            unsigned retry_attempts=0;
            while (retry_attempts++<3) {
                ++pending.resume_attempts;
                if (ResumeThread(pending.handle)!=static_cast<DWORD>(-1)) {
                    pending.resumed=true;
                    break;
                }
                entry_patch_failure(result,FailureStage::pending_retry,"ResumeThread",GetLastError());
            }
        }
        if (pending.resumed) {
            if (CloseHandle(pending.handle)) {
                entry_patch_pending[i]=entry_patch_pending[--entry_patch_pending_count];
                continue;
            }
            entry_patch_failure(result,FailureStage::pending_retry,"CloseHandle",GetLastError());
        }
        all=false;
        ++i;
    }
    result.pending_count=entry_patch_pending_count;
    result.threads_resumed=all && !entry_patch_pending_count;
    result.protection_restored=true;
    result.success=result.threads_resumed;
    result.status=result.threads_resumed?PatchStatus::success:PatchStatus::restart_required;
    entry_patch_release_gate();
    return result;
}

} // namespace bridge_entry_patch

#endif // BRIDGE_ENTRY_PATCH_TRANSACTION_INC
