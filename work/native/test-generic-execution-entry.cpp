#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

extern "C" int generic_entry_original();
extern "C" int generic_bridge_response_stub();
extern "C" int generic_entry_body();
extern "C" int generic_entry_gate();
extern "C" int generic_call_direct_checked();
extern "C" int generic_call_virtual_checked();

extern "C" {
void* generic_entry_trampoline = nullptr;
void* generic_vtable_slot = nullptr;
}

namespace {

constexpr std::size_t kPrologueSize = 18;
constexpr std::size_t kAbsoluteJumpBytes = 14;
constexpr std::size_t kTrampolineOffset = 0x100;
constexpr std::size_t kUnwindOffset = 0x200;
constexpr std::size_t kBlockSize = 0x1000;
constexpr int kOriginalResult = 0x4242;
constexpr int kBlockedResult = 0x5a5a;
constexpr int kPreservedMask = 0x1f;
constexpr LONG kModeDirect = 1;
constexpr LONG kModeVirtual = 2;

const unsigned char kExpectedPrologue[kPrologueSize] = {
    0x48, 0x89, 0x5c, 0x24, 0x18,
    0x48, 0x89, 0x6c, 0x24, 0x20,
    0x56,
    0x57,
    0x41, 0x56,
    0x48, 0x83, 0xec, 0x20,
};

volatile LONG64 g_original_calls = 0;
volatile LONG64 g_gate_calls = 0;
volatile LONG64 g_direct_gate_calls = 0;
volatile LONG64 g_virtual_gate_calls = 0;
volatile LONG g_gate_mode = 0;
volatile LONG g_gate_allow = 0;

struct CaseResult {
    bool returned = false;
    bool nonvolatile = false;
    bool gate_once = false;
    bool path_once = false;
    bool original_once = false;
};

struct PatchResult {
    bool before_signature = false;
    bool trampoline_copy = false;
    bool trampoline_jump = false;
    bool entry_jump = false;
    bool entry_nop4 = false;
};

struct UnwindResult {
    bool registered = false;
    bool lookup = false;
    bool return_address = false;
    bool stack = false;
    bool rbx = false;
    bool rbp = false;
    bool rsi = false;
    bool rdi = false;
    bool r14 = false;
};

extern "C" __attribute__((noinline)) int generic_entry_body() {
    InterlockedIncrement64(&g_original_calls);
    return kOriginalResult;
}

extern "C" __attribute__((noinline)) int generic_entry_gate() {
    InterlockedIncrement64(&g_gate_calls);
    const LONG mode = InterlockedCompareExchange(&g_gate_mode, 0, 0);
    if (mode == kModeDirect) {
        InterlockedIncrement64(&g_direct_gate_calls);
    } else if (mode == kModeVirtual) {
        InterlockedIncrement64(&g_virtual_gate_calls);
    }
    return InterlockedCompareExchange(&g_gate_allow, 0, 0) != 0 ? 1 : 0;
}

static std::int64_t read_counter(const volatile LONG64* value) {
    return InterlockedCompareExchange64(const_cast<volatile LONG64*>(value),
        0, 0);
}

static void reset_counters() {
    InterlockedExchange64(&g_original_calls, 0);
    InterlockedExchange64(&g_gate_calls, 0);
    InterlockedExchange64(&g_direct_gate_calls, 0);
    InterlockedExchange64(&g_virtual_gate_calls, 0);
}

static bool bytes_equal(const unsigned char* actual,
    const unsigned char* expected, std::size_t count) {
    return actual != nullptr && expected != nullptr
        && std::memcmp(actual, expected, count) == 0;
}

static void write_absolute_jump(unsigned char* destination, const void* target) {
    const std::uint64_t address = reinterpret_cast<std::uint64_t>(target);
    destination[0] = 0x48;
    destination[1] = 0xb8;
    std::memcpy(destination + 2, &address, sizeof(address));
    destination[10] = 0xff;
    destination[11] = 0xe0;
    destination[12] = 0x90;
    destination[13] = 0x90;
}

static const void* function_address(int (*function)()) {
    return reinterpret_cast<const void*>(
        reinterpret_cast<std::uintptr_t>(function));
}

static bool decode_absolute_jump(const unsigned char* source,
    const void* expected_target) {
    if (!source || source[0] != 0x48 || source[1] != 0xb8
        || source[10] != 0xff || source[11] != 0xe0) {
        return false;
    }
    std::uint64_t target = 0;
    std::memcpy(&target, source + 2, sizeof(target));
    return target == reinterpret_cast<std::uint64_t>(expected_target);
}

static bool protect_code(void* address, std::size_t size, DWORD protection,
    DWORD* old_protection) {
    return VirtualProtect(address, size, protection, old_protection) != 0
        && FlushInstructionCache(GetCurrentProcess(), address, size) != 0;
}

static bool make_trampoline(unsigned char* original, unsigned char* block,
    unsigned char*& trampoline) {
    trampoline = block + kTrampolineOffset;
    std::memcpy(trampoline, original, kPrologueSize);
    write_absolute_jump(trampoline + kPrologueSize, original + kPrologueSize);
    DWORD old_protection = 0;
    return protect_code(block, kBlockSize, PAGE_EXECUTE_READ,
        &old_protection);
}

static PatchResult inspect_patch(const unsigned char* original,
    const unsigned char* before, const unsigned char* trampoline) {
    PatchResult result{};
    result.before_signature = bytes_equal(before, kExpectedPrologue,
        kPrologueSize);
    result.trampoline_copy = bytes_equal(trampoline, before, kPrologueSize);
    result.trampoline_jump = decode_absolute_jump(
        trampoline + kPrologueSize, original + kPrologueSize);
    result.entry_jump = decode_absolute_jump(original,
        function_address(&generic_bridge_response_stub));
    result.entry_nop4 = original[14] == 0x90 && original[15] == 0x90
        && original[16] == 0x90 && original[17] == 0x90;
    return result;
}

static CaseResult run_case(LONG mode, bool allow, bool virtual_path) {
    reset_counters();
    InterlockedExchange(&g_gate_mode, mode);
    InterlockedExchange(&g_gate_allow, allow ? 1 : 0);
    const int packed = virtual_path ? generic_call_virtual_checked()
        : generic_call_direct_checked();
    const int value = packed & 0xffff;
    const int preservation = (packed >> 16) & 0x1f;
    const bool expected_return = allow ? value == kOriginalResult
        : value == kBlockedResult;
    CaseResult result{};
    result.returned = expected_return;
    result.nonvolatile = preservation == kPreservedMask;
    result.gate_once = read_counter(&g_gate_calls) == 1;
    result.path_once = virtual_path
        ? read_counter(&g_virtual_gate_calls) == 1
            && read_counter(&g_direct_gate_calls) == 0
        : read_counter(&g_direct_gate_calls) == 1
            && read_counter(&g_virtual_gate_calls) == 0;
    result.original_once = read_counter(&g_original_calls)
        == (allow ? 1 : 0);
    return result;
}

static void set_raw_unwind_code(unsigned char* info, unsigned index,
    unsigned offset, unsigned op, unsigned register_or_info) {
    const unsigned byte_offset = 4 + index * 2;
    info[byte_offset] = static_cast<unsigned char>(offset);
    info[byte_offset + 1] = static_cast<unsigned char>(
        (register_or_info << 4) | op);
}

static void set_raw_unwind_extra(unsigned char* info, unsigned index,
    unsigned value) {
    const unsigned byte_offset = 4 + index * 2;
    const unsigned short encoded = static_cast<unsigned short>(value);
    std::memcpy(info + byte_offset, &encoded, sizeof(encoded));
}

static void build_matching_unwind_info(unsigned char* info) {
    std::memset(info, 0, 4 + 8 * 2);
    info[0] = 1;  // version 1, no handler flags
    info[1] = static_cast<unsigned char>(kPrologueSize);
    info[2] = 8;  // six operations plus two SAVE_NONVOL extra slots
    info[3] = 0;  // no frame register

    // The entries are reverse-prologue order.  The two SAVE_NONVOL entries
    // use their following slots for the final-RSP offsets 0x58/8 and 0x50/8.
    set_raw_unwind_code(info, 0, 18, 2, 3);   // UWOP_ALLOC_SMALL, 32 bytes
    set_raw_unwind_code(info, 1, 14, 0, 14);  // UWOP_PUSH_NONVOL, r14
    set_raw_unwind_code(info, 2, 12, 0, 7);   // UWOP_PUSH_NONVOL, rdi
    set_raw_unwind_code(info, 3, 11, 0, 6);   // UWOP_PUSH_NONVOL, rsi
    set_raw_unwind_code(info, 4, 10, 4, 5);   // UWOP_SAVE_NONVOL, rbp
    set_raw_unwind_extra(info, 5, 11);
    set_raw_unwind_code(info, 6, 5, 4, 3);    // UWOP_SAVE_NONVOL, rbx
    set_raw_unwind_extra(info, 7, 10);
}

static UnwindResult validate_trampoline_unwind(unsigned char* block,
    unsigned char* trampoline, RUNTIME_FUNCTION& function) {
    UnwindResult result{};
    unsigned char* info = block + kUnwindOffset;
    DWORD old_protection = 0;
    if (!VirtualProtect(block, kBlockSize, PAGE_EXECUTE_READWRITE,
        &old_protection)) {
        return result;
    }
    build_matching_unwind_info(info);
    DWORD ignored_protection = 0;
    (void)VirtualProtect(block, kBlockSize, old_protection,
        &ignored_protection);
    function.BeginAddress = static_cast<DWORD>(kTrampolineOffset);
    function.EndAddress = static_cast<DWORD>(kTrampolineOffset + 0x20);
    function.UnwindData = static_cast<DWORD>(kUnwindOffset);
    result.registered = RtlAddFunctionTable(&function, 1,
        reinterpret_cast<DWORD64>(block)) != FALSE;
    std::fprintf(stderr, "unwind-register=%s\n",
        result.registered ? "yes" : "no");
    if (!result.registered) {
        return result;
    }

    DWORD64 image_base = 0;
    PRUNTIME_FUNCTION found = RtlLookupFunctionEntry(
        reinterpret_cast<DWORD64>(trampoline + kPrologueSize), &image_base,
        nullptr);
    std::fprintf(stderr, "unwind-lookup=%s base=%llx\n", found ? "yes" : "no",
        static_cast<unsigned long long>(image_base));
    result.lookup = found != nullptr;
    if (!found) {
        return result;
    }

    constexpr std::uint64_t kRbx = UINT64_C(0x1111111122222222);
    constexpr std::uint64_t kRbp = UINT64_C(0x3333333344444444);
    constexpr std::uint64_t kRsi = UINT64_C(0x5555555566666666);
    constexpr std::uint64_t kRdi = UINT64_C(0x7777777788888888);
    constexpr std::uint64_t kR14 = UINT64_C(0x99999999aaaabbbb);
    constexpr std::uint64_t kReturn = UINT64_C(0x123456789abcdef0);
    unsigned char* stack = static_cast<unsigned char*>(VirtualAlloc(nullptr,
        0x1000, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE));
    if (!stack) {
        return result;
    }
    unsigned char* current_rsp = stack + 0x200;
    *reinterpret_cast<std::uint64_t*>(current_rsp + 0x20) = kR14;
    *reinterpret_cast<std::uint64_t*>(current_rsp + 0x28) = kRdi;
    *reinterpret_cast<std::uint64_t*>(current_rsp + 0x30) = kRsi;
    *reinterpret_cast<std::uint64_t*>(current_rsp + 0x38) = kReturn;
    *reinterpret_cast<std::uint64_t*>(current_rsp + 0x50) = kRbx;
    *reinterpret_cast<std::uint64_t*>(current_rsp + 0x58) = kRbp;

    CONTEXT context{};
    context.ContextFlags = CONTEXT_CONTROL | CONTEXT_INTEGER;
    context.Rip = reinterpret_cast<DWORD64>(trampoline + kPrologueSize);
    context.Rsp = reinterpret_cast<DWORD64>(current_rsp);
    PVOID handler_data = nullptr;
    DWORD64 establisher_frame = 0;
    KNONVOLATILE_CONTEXT_POINTERS nonvolatile{};
    std::fprintf(stderr, "unwind-call pc=%llx rsp=%llx\n",
        static_cast<unsigned long long>(context.Rip),
        static_cast<unsigned long long>(context.Rsp));
    (void)RtlVirtualUnwind(UNW_FLAG_NHANDLER, image_base, context.Rip, found,
        &context, &handler_data, &establisher_frame, &nonvolatile);
    std::fprintf(stderr, "unwind-return rip=%llx rsp=%llx\n",
        static_cast<unsigned long long>(context.Rip),
        static_cast<unsigned long long>(context.Rsp));
    result.return_address = context.Rip == kReturn;
    // RtlVirtualUnwind restores the prologue and consumes the caller's
    // return address after loading it into Rip, so the resulting RSP is
    // current_rsp + 0x40 while the synthetic return address lives at +0x38.
    result.stack = context.Rsp
        == reinterpret_cast<DWORD64>(current_rsp + 0x40);
    result.rbx = context.Rbx == kRbx;
    result.rbp = context.Rbp == kRbp;
    result.rsi = context.Rsi == kRsi;
    result.rdi = context.Rdi == kRdi;
    result.r14 = context.R14 == kR14;
    VirtualFree(stack, 0, MEM_RELEASE);
    return result;
}

static bool all(const CaseResult& value) {
    return value.returned && value.nonvolatile && value.gate_once
        && value.path_once && value.original_once;
}

static bool all(const PatchResult& value) {
    return value.before_signature && value.trampoline_copy
        && value.trampoline_jump && value.entry_jump && value.entry_nop4;
}

static bool all(const UnwindResult& value) {
    return value.registered && value.lookup && value.return_address
        && value.stack && value.rbx && value.rbp && value.rsi && value.rdi
        && value.r14;
}

static void print_case(const char* name, const CaseResult& value) {
    std::printf("%s returned=%s nonvolatile=%s gate_once=%s path_once=%s "
        "original_once=%s status=%s\n", name,
        value.returned ? "PASS" : "FAIL",
        value.nonvolatile ? "PASS" : "FAIL",
        value.gate_once ? "PASS" : "FAIL",
        value.path_once ? "PASS" : "FAIL",
        value.original_once ? "PASS" : "FAIL",
        all(value) ? "PASS" : "FAIL");
}

}  // namespace

int main() {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    std::fprintf(stderr, "phase=read-entry\n");
    unsigned char* original = reinterpret_cast<unsigned char*>(
        &generic_entry_original);
    unsigned char before[kPrologueSize]{};
    std::memcpy(before, original, sizeof(before));

    unsigned char* block = static_cast<unsigned char*>(VirtualAlloc(nullptr,
        kBlockSize, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE));
    if (!block) {
        std::fprintf(stderr, "VirtualAlloc failed: %lu\n",
            static_cast<unsigned long>(GetLastError()));
        return 2;
    }

    unsigned char* trampoline = nullptr;
    if (!make_trampoline(original, block, trampoline)) {
        std::fprintf(stderr, "trampoline setup failed: %lu\n",
            static_cast<unsigned long>(GetLastError()));
        VirtualFree(block, 0, MEM_RELEASE);
        return 2;
    }
    std::fprintf(stderr, "phase=trampoline-ready\n");
    generic_entry_trampoline = trampoline;
    generic_vtable_slot = reinterpret_cast<void*>(
        static_cast<std::uintptr_t>(reinterpret_cast<std::uintptr_t>(
            &generic_entry_original)));
    reset_counters();
    InterlockedExchange(&g_gate_mode, 0);
    InterlockedExchange(&g_gate_allow, 1);
    const int prepatch_probe = generic_call_direct_checked();
    const bool prepatch_ok = (prepatch_probe & 0xffff) == kOriginalResult
        && ((prepatch_probe >> 16) & 0x1f) == kPreservedMask
        && read_counter(&g_original_calls) == 1;
    std::fprintf(stderr, "phase=prepatch status=%s\n",
        prepatch_ok ? "PASS" : "FAIL");

    DWORD old_protection = 0;
    if (!VirtualProtect(original, kPrologueSize, PAGE_EXECUTE_READWRITE,
        &old_protection)) {
        std::fprintf(stderr, "entry protection failed: %lu\n",
            static_cast<unsigned long>(GetLastError()));
        VirtualFree(block, 0, MEM_RELEASE);
        return 2;
    }
    std::fprintf(stderr, "phase=patch-entry\n");
    unsigned char replacement[kPrologueSize];
    std::memset(replacement, 0x90, sizeof(replacement));
    write_absolute_jump(replacement,
        function_address(&generic_bridge_response_stub));
    std::memcpy(original, replacement, sizeof(replacement));
    if (!FlushInstructionCache(GetCurrentProcess(), original,
        kPrologueSize)) {
        std::fprintf(stderr, "entry cache flush failed: %lu\n",
            static_cast<unsigned long>(GetLastError()));
        std::memcpy(original, before, sizeof(before));
        DWORD ignored = 0;
        VirtualProtect(original, kPrologueSize, old_protection, &ignored);
        VirtualFree(block, 0, MEM_RELEASE);
        return 2;
    }

    const PatchResult patch = inspect_patch(original, before, trampoline);
    std::fprintf(stderr, "phase=patched\n");

    const CaseResult direct_allowed = run_case(kModeDirect, true, false);
    std::fprintf(stderr, "phase=direct-allowed\n");
    const CaseResult virtual_allowed = run_case(kModeVirtual, true, true);
    std::fprintf(stderr, "phase=virtual-allowed\n");
    const CaseResult direct_blocked = run_case(kModeDirect, false, false);
    std::fprintf(stderr, "phase=direct-blocked\n");
    const CaseResult virtual_blocked = run_case(kModeVirtual, false, true);
    std::fprintf(stderr, "phase=virtual-blocked\n");

    RUNTIME_FUNCTION function{};
    const UnwindResult unwind = validate_trampoline_unwind(block, trampoline,
        function);
    std::fprintf(stderr, "phase=unwind\n");
    if (unwind.registered) {
        (void)RtlDeleteFunctionTable(&function);
    }

    std::memcpy(original, before, sizeof(before));
    DWORD ignored = 0;
    (void)VirtualProtect(original, kPrologueSize, old_protection, &ignored);
    (void)FlushInstructionCache(GetCurrentProcess(), original,
        kPrologueSize);
    generic_entry_trampoline = nullptr;
    generic_vtable_slot = nullptr;
    VirtualFree(block, 0, MEM_RELEASE);

    std::printf("patch signature=%s copy=%s trampoline_jump=%s entry_jump=%s "
        "entry_nop4=%s status=%s\n",
        patch.before_signature ? "PASS" : "FAIL",
        patch.trampoline_copy ? "PASS" : "FAIL",
        patch.trampoline_jump ? "PASS" : "FAIL",
        patch.entry_jump ? "PASS" : "FAIL",
        patch.entry_nop4 ? "PASS" : "FAIL",
        all(patch) ? "PASS" : "FAIL");
    print_case("direct_allowed", direct_allowed);
    print_case("virtual_allowed", virtual_allowed);
    print_case("direct_blocked", direct_blocked);
    print_case("virtual_blocked", virtual_blocked);
    std::printf("unwind registered=%s lookup=%s return_address=%s stack=%s "
        "rbx=%s rbp=%s rsi=%s rdi=%s r14=%s status=%s\n",
        unwind.registered ? "PASS" : "FAIL",
        unwind.lookup ? "PASS" : "FAIL",
        unwind.return_address ? "PASS" : "FAIL",
        unwind.stack ? "PASS" : "FAIL",
        unwind.rbx ? "PASS" : "FAIL",
        unwind.rbp ? "PASS" : "FAIL",
        unwind.rsi ? "PASS" : "FAIL",
        unwind.rdi ? "PASS" : "FAIL",
        unwind.r14 ? "PASS" : "FAIL",
        all(unwind) ? "PASS" : "FAIL");
    const bool passed = prepatch_ok && all(patch) && all(direct_allowed)
        && all(virtual_allowed) && all(direct_blocked)
        && all(virtual_blocked) && all(unwind);
    std::printf("prepatch_original=%s\n", prepatch_ok ? "PASS" : "FAIL");
    std::printf("original_calls_after_last_case=%lld gate_calls_after_last_case=%lld\n",
        static_cast<long long>(read_counter(&g_original_calls)),
        static_cast<long long>(read_counter(&g_gate_calls)));
    std::printf("RESULT %s\n", passed ? "PASS" : "FAIL");
    return passed ? 0 : 1;
}
