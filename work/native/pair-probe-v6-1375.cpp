// EU4 1.37.5 bounded lifecycle experiment. No validity, command or send calls.
// The caller MUST invoke pair_selftest on the observed game/frame thread.
// This module never installs hooks, creates threads, or runs in DllMain.
// Current build evidence: work/reports/native-diplomacy-1.37.5.json.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <bcrypt.h>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {
using Logger = void (*)(const char*);
using Factory = void* (__fastcall*)(std::uint32_t, const void*);
using Clone = void* (__fastcall*)(const void*);
using Destructor = void* (__fastcall*)(void*, unsigned int);

constexpr std::uintptr_t kFactoryRva = 0x35d210;
constexpr std::uint32_t kTimestamp = 0x66fe6ab9;
constexpr std::uint32_t kImageSize = 0x025e0000;
constexpr unsigned char kFactoryPrefix[] = {
    0x40, 0x55, 0x53, 0x57, 0x48, 0x8d, 0xac, 0x24, 0xa0, 0xfe,
    0xff, 0xff, 0x48, 0x81, 0xec, 0x60, 0x02, 0x00, 0x00, 0x48,
};
constexpr unsigned char kExpectedSha256[] = {
    0x9a, 0xd3, 0xef, 0xe1, 0xaf, 0x16, 0x9f, 0x40,
    0xee, 0x57, 0x7f, 0x9d, 0xae, 0x5d, 0xeb, 0xbc,
    0x87, 0xaf, 0x6f, 0xb8, 0xb5, 0x45, 0x0f, 0xb3,
    0x45, 0xeb, 0xf1, 0x10, 0xdc, 0x4d, 0x77, 0x1a,
};

struct Action {
    const char* name;
    std::uint32_t token;
    std::size_t size;
    std::uintptr_t vtable;
    std::uintptr_t clone;
    std::uintptr_t destructor;
    std::uintptr_t token_getter;
};
constexpr Action kActions[] = {
    {"vassalaction", 0x2940, 0x40, 0x1c7fd20, 0x51fa00, 0x129450, 0x51f570},
    {"royal_marriage", 0x28df, 0x68, 0x1c80ab0, 0x4f07d0, 0x4ed5b0, 0x4e3df0},
    {"improve_relation", 0x2ddb, 0x40, 0x1c7dd68, 0x574b20, 0x129450, 0x4e3dc0},
    {"guaranteeaction", 0x2941, 0x40, 0x1c7fe50, 0x5224c0, 0x129450, 0x5220b0},
    {"spy_network", 0x3378, 0x40, 0x1c7cc48, 0x586200, 0x129450, 0x585bc0},
};

template <typename T>
T read_at(std::uintptr_t address) {
    T value{};
    std::memcpy(&value, reinterpret_cast<const void*>(address), sizeof(value));
    return value;
}

template <typename T>
bool load_export(HMODULE module, const char* name, T& target) {
    const FARPROC address = GetProcAddress(module, name);
    static_assert(sizeof(target) == sizeof(address), "x64 function pointer required");
    std::memcpy(&target, &address, sizeof(target));
    return address != nullptr;
}

// Resolve the Windows SHA-256 provider dynamically; no additional import lib.
bool executable_hash_matches() {
    wchar_t path[32768]{};
    constexpr DWORD path_capacity = static_cast<DWORD>(sizeof(path) / sizeof(path[0]));
    const DWORD length = GetModuleFileNameW(nullptr, path, path_capacity);
    if (length == 0 || length >= path_capacity) return false;
    HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                              nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) return false;
    HMODULE module = LoadLibraryExW(L"bcrypt.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (module == nullptr) { CloseHandle(file); return false; }
    decltype(&BCryptOpenAlgorithmProvider) open_algorithm = nullptr;
    decltype(&BCryptCreateHash) create_hash = nullptr;
    decltype(&BCryptHashData) hash_data = nullptr;
    decltype(&BCryptFinishHash) finish_hash = nullptr;
    decltype(&BCryptDestroyHash) destroy_hash = nullptr;
    decltype(&BCryptCloseAlgorithmProvider) close_algorithm = nullptr;
    bool ok = load_export(module, "BCryptOpenAlgorithmProvider", open_algorithm)
           && load_export(module, "BCryptCreateHash", create_hash)
           && load_export(module, "BCryptHashData", hash_data)
           && load_export(module, "BCryptFinishHash", finish_hash)
           && load_export(module, "BCryptDestroyHash", destroy_hash)
           && load_export(module, "BCryptCloseAlgorithmProvider", close_algorithm);
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    unsigned char digest[32]{};
    if (ok) ok = open_algorithm(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) >= 0;
    // On supported Windows versions BCrypt allocates its hash object when null.
    if (ok) ok = create_hash(algorithm, &hash, nullptr, 0, nullptr, 0, 0) >= 0;
    unsigned char buffer[65536];
    while (ok) {
        DWORD bytes = 0;
        if (!ReadFile(file, buffer, static_cast<DWORD>(sizeof(buffer)), &bytes, nullptr)) {
            ok = false;
            break;
        }
        if (bytes == 0) break;
        ok = hash_data(hash, buffer, bytes, 0) >= 0;
    }
    if (ok) ok = finish_hash(hash, digest, static_cast<ULONG>(sizeof(digest)), 0) >= 0;
    if (hash != nullptr) destroy_hash(hash);
    if (algorithm != nullptr) close_algorithm(algorithm, 0);
    FreeLibrary(module);
    CloseHandle(file);
    return ok && std::memcmp(digest, kExpectedSha256, sizeof(digest)) == 0;
}

bool loaded_image_matches(std::uintptr_t base) {
    if (base != reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr))) return false;
    const auto dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0 || dos->e_lfanew > 4096) return false;
    const auto nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(base + static_cast<std::uintptr_t>(dos->e_lfanew));
    if (nt->Signature != IMAGE_NT_SIGNATURE || nt->FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64
        || nt->FileHeader.TimeDateStamp != kTimestamp || nt->OptionalHeader.SizeOfImage != kImageSize) return false;
    if (std::memcmp(reinterpret_cast<const void*>(base + kFactoryRva), kFactoryPrefix, sizeof(kFactoryPrefix)) != 0) return false;
    for (const Action& action : kActions) {
        if (read_at<std::uintptr_t>(base + action.vtable) != base + action.destructor
            || read_at<std::uintptr_t>(base + action.vtable + 0xb0) != base + action.clone
            || read_at<std::uintptr_t>(base + action.vtable + 0x98) != base + action.token_getter) return false;
        const auto getter = reinterpret_cast<const unsigned char*>(base + action.token_getter);
        if (getter[0] != 0xb8 || read_at<std::uint32_t>(base + action.token_getter + 1) != action.token
            || getter[5] != 0xc3) return false;
    }
    return true;
}

bool default_fields_match(std::uintptr_t object, const Action& action, std::uintptr_t base) {
    if (object == 0 || object == base + 0x1fd1ca0) return false;
    if (read_at<std::uintptr_t>(object) != base + action.vtable
        || read_at<std::uint32_t>(object + 8) != 0x165
        || read_at<std::uint64_t>(object + 0x10) != 0x2d2d2d
        || read_at<std::uint64_t>(object + 0x18) != 0x2d2d2d
        || read_at<std::uint64_t>(object + 0x20) != 0x2d2d2d
        || read_at<std::uint32_t>(object + 0x28) != 0x29c77f8
        || read_at<std::uint32_t>(object + 0x2c) != 0x29c77f8
        || read_at<std::uint32_t>(object + 0x30) != 0xffffffff
        || read_at<std::uint32_t>(object + 0x34) != 0
        || read_at<std::uint16_t>(object + 0x38) != 1
        || read_at<std::uint32_t>(object + 0x3c) != 0) return false;
    if (action.size == 0x68) {
        return read_at<unsigned char>(object + 0x40) == 0
            && read_at<std::uint64_t>(object + 0x50) == 0
            && read_at<std::uint64_t>(object + 0x58) == 15
            && read_at<unsigned char>(object + 0x60) == 0;
    }
    return true;
}

bool one_lifecycle(std::uintptr_t base, const Action& action, Logger logger) {
    void* original = nullptr;
    void* copy = nullptr;
    bool original_ok = false;
    bool copy_ok = false;
    bool original_destroyed = false;
    bool copy_destroyed = false;
    DWORD exception = 0;
    __try {
        const auto factory = reinterpret_cast<Factory>(base + kFactoryRva);
        original = factory(action.token, nullptr);
        original_ok = default_fields_match(reinterpret_cast<std::uintptr_t>(original), action, base);
        if (original_ok) {
            copy = reinterpret_cast<Clone>(base + action.clone)(original);
            copy_ok = copy != original && default_fields_match(reinterpret_cast<std::uintptr_t>(copy), action, base);
        }
        // Only destroy objects with their independently checked derived identity.
        if (copy != nullptr && copy != original
            && read_at<std::uintptr_t>(reinterpret_cast<std::uintptr_t>(copy)) == base + action.vtable) {
            reinterpret_cast<Destructor>(base + action.destructor)(copy, 1);
            copy_destroyed = true;
        }
        if (original != nullptr
            && read_at<std::uintptr_t>(reinterpret_cast<std::uintptr_t>(original)) == base + action.vtable) {
            reinterpret_cast<Destructor>(base + action.destructor)(original, 1);
            original_destroyed = true;
        }
    } __except ((exception = GetExceptionCode()), EXCEPTION_EXECUTE_HANDLER) {
        // Stop after the first fault. Do not speculate about ownership or retry.
    }
    char line[512]{};
    std::snprintf(line, sizeof(line),
                  "{\"event\":\"pair_lifecycle\",\"action\":\"%s\",\"size\":%zu,\"thread_id\":%lu,"
                  "\"factory_fields_ok\":%s,\"clone_fields_ok\":%s,\"original_destroyed\":%s,"
                  "\"clone_destroyed\":%s,\"exception\":%lu,\"submitted\":false}",
                  action.name, action.size, GetCurrentThreadId(), original_ok ? "true" : "false",
                  copy_ok ? "true" : "false", original_destroyed ? "true" : "false",
                  copy_destroyed ? "true" : "false", exception);
    logger(line);
    return exception == 0 && original_ok && copy_ok && original_destroyed && copy_destroyed;
}
} // namespace

// This function is intentionally unexported. Link it into an independently
// reviewed frame observer and call once after that observer has identified the
// game thread. It neither sets country handles nor touches diplomatic state.
bool pair_selftest(std::uintptr_t base, void (*logger)(const char*)) {
    if (logger == nullptr) return false;
    bool image_ok = false;
    __try { image_ok = loaded_image_matches(base); }
    __except (EXCEPTION_EXECUTE_HANDLER) { image_ok = false; }
    if (!image_ok || !executable_hash_matches()) {
        logger("{\"event\":\"pair_lifecycle_rejected\",\"reason\":\"build_identity_mismatch\",\"submitted\":false}");
        return false;
    }
    for (const Action& action : kActions) {
        if (!one_lifecycle(base, action, logger)) return false;
    }
    logger("{\"event\":\"pair_lifecycle_complete\",\"passed\":5,\"submitted\":false}");
    return true;
}
