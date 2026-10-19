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
    {"allianceaction", 0x293d, 0x40, 0x1c80720, 0x513060, 0x129450, 0x512d40},
    {"milaccess", 0x2943, 0x40, 0x1c7fb70, 0x525d70, 0x129450, 0x525c90},
    {"offermilaccess", 0x2944, 0x40, 0x1c7f580, 0x536c40, 0x129450, 0x536ba0},
    {"fleet_access", 0x2dd6, 0x40, 0x1c7ef90, 0x5304b0, 0x129450, 0x530280},
    {"offer_fleet_access", 0x2dd7, 0x40, 0x1c7f1f0, 0x534900, 0x129450, 0x534660},
    {"embargoaction", 0x293e, 0x40, 0x1c80310, 0x5183c0, 0x129450, 0x518310},
    {"warsubsidy", 0x2a25, 0x48, 0x1c7ed30, 0x5492e0, 0x129500, 0x549270},
    {"warningaction", 0x2942, 0x40, 0x1c7fa40, 0x523a70, 0x129450, 0x523a00},
    {"insultaction", 0x2947, 0x48, 0x1c7f6b0, 0x538e20, 0x129500, 0x538a60},
    {"form_coalition", 0x2de0, 0x40, 0x1c7c788, 0x58a840, 0x129450, 0x58a700},
    {"support_independence_action", 0x2f2e, 0x40, 0x1c805f0, 0x50f090, 0x129450, 0x50ef00},
    {"transfer_trade_power", 0x2e09, 0x48, 0x1c7cea8, 0x57ad40, 0x129500, 0x57ab60},
    {"steer_trade", 0x3778, 0x40, 0x1c7d238, 0x57ce60, 0x129450, 0x57ca30},
    {"giftaction", 0x2948, 0x48, 0x1c7f450, 0x53b090, 0x129500, 0x53abb0},
    {"trade_favors_for_gold", 0x3bce, 0x40, 0x1c80980, 0x4f5bd0, 0x129450, 0x4f5930},
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


// Independently pinned v10 extension ABI; no calls or process writes.
bool extension_prefix(std::uintptr_t address, const char* hex) {
    for (std::size_t i = 0; hex[i * 2] != 0; ++i) {
        const auto digit = [](char c) { return c <= '9' ? c - '0' : c - 'a' + 10; };
        if (hex[i * 2 + 1] == 0 || read_at<unsigned char>(address + i)
            != static_cast<unsigned char>((digit(hex[i * 2]) << 4) | digit(hex[i * 2 + 1]))) return false;
    }
    return true;
}
bool extension_image_pin(std::uintptr_t base) {
    if (!extension_prefix(base + 0x129450, "40534883ec20488d051b51b101488bd9488901f6c201740aba40000000e87e00")) return false;
    if (!extension_prefix(base + 0x4e9930, "48895c2408574883ec20488b01488bfaff90b0000000488b0d2b65e501488bd8")) return false;
    if (!extension_prefix(base + 0x513060, "40534883ec20488bd9b940000000e8610252014c8bc04889442438c740086501")) return false;
    if (!extension_prefix(base + 0x4e99d0, "885138c3cccccccccccccccccccccccc48895c2408574883ec60488bda488bf9")) return false;
    if (!extension_prefix(base + 0x35d448, "b940000000e8825e6d01488bc84889859001000066c785980100002d2dc7859a")) return false;
    if (!extension_prefix(base + 0x525d70, "40534883ec20488bd9b940000000e851d550014c8bc04889442438c740086501")) return false;
    if (!extension_prefix(base + 0x35d742, "b940000000e8885b6d01488bc84889859001000066c785980100002d2dc7859a")) return false;
    if (!extension_prefix(base + 0x536c40, "40534883ec20488bd9b940000000e881c64f014c8bc04889442438c740086501")) return false;
    if (!extension_prefix(base + 0x35d7c1, "b940000000e8095b6d01488bc84889859001000066c785980100002d2dc7859a")) return false;
    if (!extension_prefix(base + 0x5304b0, "40534883ec20488bd9b940000000e8112e50014c8bc04889442438c740086501")) return false;
    if (!extension_prefix(base + 0x35e40c, "b940000000e8be4e6d01488bc84889859001000066c785980100002d2dc7859a")) return false;
    if (!extension_prefix(base + 0x534900, "40534883ec20488bd9b940000000e8c1e94f014c8bc04889442438c740086501")) return false;
    if (!extension_prefix(base + 0x35e48b, "b940000000e83f4e6d01488bc84889859001000066c785980100002d2dc7859a")) return false;
    if (!extension_prefix(base + 0x5183c0, "40534883ec20488bd9b940000000e801af51014c8bc04889442438c740086501")) return false;
    if (!extension_prefix(base + 0x35d4c7, "b940000000e8035e6d01488bc84889859001000066c785980100002d2dc7859a")) return false;
    if (!extension_prefix(base + 0x129500, "40534883ec20488d056b50b101488bd9488901f6c201740aba48000000e8ceff")) return false;
    if (!extension_prefix(base + 0x5492e0, "40534883ec20488bd9b948000000e8e19f4e014c8bc04889442438c740086501")) return false;
    if (!extension_prefix(base + 0x35dc73, "b948000000e857566d01488bc84889859001000066c785980100002d2dc7859a")) return false;
    if (read_at<std::uintptr_t>(base + 0x1c80720 + 0x0) != base + 0x129450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c80720 + 0x40) != base + 0x4e9930) return false;
    if (read_at<std::uintptr_t>(base + 0x1c80720 + 0xb0) != base + 0x513060) return false;
    if (read_at<std::uintptr_t>(base + 0x1c80720 + 0xe0) != base + 0x4e99d0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7fb70 + 0x0) != base + 0x129450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7fb70 + 0x40) != base + 0x4e9930) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7fb70 + 0xb0) != base + 0x525d70) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7fb70 + 0xe0) != base + 0x4e99d0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f580 + 0x0) != base + 0x129450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f580 + 0x40) != base + 0x4e9930) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f580 + 0xb0) != base + 0x536c40) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f580 + 0xe0) != base + 0x4e99d0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7ef90 + 0x0) != base + 0x129450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7ef90 + 0x40) != base + 0x4e9930) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7ef90 + 0xb0) != base + 0x5304b0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7ef90 + 0xe0) != base + 0x4e99d0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f1f0 + 0x0) != base + 0x129450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f1f0 + 0x40) != base + 0x4e9930) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f1f0 + 0xb0) != base + 0x534900) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f1f0 + 0xe0) != base + 0x4e99d0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c80310 + 0x0) != base + 0x129450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c80310 + 0x40) != base + 0x4e9930) return false;
    if (read_at<std::uintptr_t>(base + 0x1c80310 + 0xb0) != base + 0x5183c0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c80310 + 0xe0) != base + 0x4e99d0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7ed30 + 0x0) != base + 0x129500) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7ed30 + 0x40) != base + 0x4e9930) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7ed30 + 0xb0) != base + 0x5492e0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7ed30 + 0xe0) != base + 0x4e99d0) return false;
    return true;
}

bool v12_image_pin(std::uintptr_t base) {
    if (!extension_prefix(base + 0x129450, "40534883ec20488d051b51b101488bd9488901f6c201740aba40000000e87e00")) return false;
    if (!extension_prefix(base + 0x4e9930, "48895c2408574883ec20488b01488bfaff90b0000000488b0d2b65e501488bd8")) return false;
    if (!extension_prefix(base + 0x5229f0, "48894c2408555356574154415541564157488d6c24984881ec68010000488bf1")) return false;
    if (!extension_prefix(base + 0x523a10, "40534883ec20488b4120488bda48c1e8204533c94c0fbfc033d2488b059f9ee1")) return false;
    if (!extension_prefix(base + 0x523670, "48895c241048896c2418565741564881ec80000000488bda4c8bf140b7014c8b")) return false;
    if (!extension_prefix(base + 0x523a00, "b842290000c3")) return false;
    if (!extension_prefix(base + 0x8f450, "32c0c3")) return false;
    if (!extension_prefix(base + 0x523a70, "40534883ec20488bd9b940000000e851f850014c8bc04889442438c740086501")) return false;
    if (!extension_prefix(base + 0x4e99d0, "885138c3")) return false;
    if (!extension_prefix(base + 0x8f440, "b001c3")) return false;
    if (!extension_prefix(base + 0x35d6c3, "b940000000e8075c6d01488bc84889859001000066c785980100002d2dc7859a")) return false;
    if (!extension_prefix(base + 0x129500, "40534883ec20488d056b50b101488bd9488901f6c201740aba48000000e8ceff")) return false;
    if (!extension_prefix(base + 0x5378f0, "48894c2408555356574154415541564157488d6c24984881ec68010000488bf1")) return false;
    if (!extension_prefix(base + 0x538a80, "48895c241848895424105556574154415541564157488d6c24804881ec800100")) return false;
    if (!extension_prefix(base + 0x538700, "48895c241048896c2418565741564883ec60488bda488be941b6014c8b15ae51")) return false;
    if (!extension_prefix(base + 0x538a60, "b847290000c3")) return false;
    if (!extension_prefix(base + 0x538e20, "40534883ec20488bd9b948000000e8a1a44f014c8bc04889442438c740086501")) return false;
    if (!extension_prefix(base + 0x35d840, "b948000000e88a5a6d01488bc84889859001000066c785980100002d2dc7859a")) return false;
    if (!extension_prefix(base + 0x588e10, "48894c2408555356574154415541564157488dac24e8fbffff4881ec18050000")) return false;
    if (!extension_prefix(base + 0x58a710, "48895c2408574881ec800000000f297424700f297c2460488bda807938000f84")) return false;
    if (!extension_prefix(base + 0x58a120, "4883ec284c8b41104c8bc9488b059e37db0149c1e82080793800488b88180100")) return false;
    if (!extension_prefix(base + 0x58a700, "b8e02d0000c3")) return false;
    if (!extension_prefix(base + 0x58a840, "40534883ec20488bd9b940000000e8818a4a014c8bc04889442438c740086501")) return false;
    if (!extension_prefix(base + 0x35dfde, "b940000000e8ec526d01488bc84889859001000066c785980100002d2dc7859a")) return false;
    if (!extension_prefix(base + 0x50c4c0, "48894c2408555356574154415541564157488d6c24984881ec680100004c8be1")) return false;
    if (!extension_prefix(base + 0x50ef10, "48895c240848897424184889542410574883ec50488bda4c8bd133f689742420")) return false;
    if (!extension_prefix(base + 0x50e0f0, "48895c241048894c24085556574154415541564157488d6c24d94881eca00000")) return false;
    if (!extension_prefix(base + 0x50ef00, "b82e2f0000c3")) return false;
    if (!extension_prefix(base + 0x50f090, "40534883ec20488bd9b940000000e8314252014c8bc04889442438c740086501")) return false;
    if (!extension_prefix(base + 0x50f120, "807938000f95c0c3cccccccccccccccc40534883ec304c8b153b0de301488bda")) return false;
    if (!extension_prefix(base + 0x35e84f, "b940000000e87b4a6d01488bc84889859001000066c785980100002d2dc7859a")) return false;
    if (!extension_prefix(base + 0x579340, "48894c2408555356574154415541564157488d6c24984881ec68010000488bf1")) return false;
    if (!extension_prefix(base + 0x57ab70, "48895c24084889742410574881eca0000000488bfa488bd9488d71204533c945")) return false;
    if (!extension_prefix(base + 0x57a0c0, "48895c2408488974241048897c2418554154415541564157488bec4883ec7048")) return false;
    if (!extension_prefix(base + 0x57ab60, "b8092e0000c3")) return false;
    if (!extension_prefix(base + 0x57ad40, "40534883ec20488bd9b948000000e881854b014c8bc04889442438c740086501")) return false;
    if (!extension_prefix(base + 0x4e4d50, "0fb64138c3")) return false;
    if (!extension_prefix(base + 0x35e25c, "b948000000e86e506d01488bc84889859001000066c785980100002d2dc7859a")) return false;
    if (!extension_prefix(base + 0x57b460, "48894c2408555356574154415541564157488d6c24984881ec68010000488bf1")) return false;
    if (!extension_prefix(base + 0x57ca40, "488bc44889581048897018488978205541564157488da858ffffff4881ec9001")) return false;
    if (!extension_prefix(base + 0x57c1c0, "48895c240848896c2410565741564883ec60488bda488bf9803d593ddc010074")) return false;
    if (!extension_prefix(base + 0x57ca30, "b878370000c3")) return false;
    if (!extension_prefix(base + 0x57ce60, "40534883ec20488bd9b940000000e861644b014c8bc04889442438c740086501")) return false;
    if (!extension_prefix(base + 0x35f9ae, "b940000000e81c396d01488bc84889859001000066c785980100002d2dc7859a")) return false;
    if (!extension_prefix(base + 0x539540, "48895c24185556574154415541564157488dac24a0feffff4881ec600200004c")) return false;
    if (!extension_prefix(base + 0x53abf0, "48895c2420488954241048894c24085556574154415541564157488dac24a0fe")) return false;
    if (!extension_prefix(base + 0x53a600, "48895c241048897424185557415441564157488d6c24a04881ec60010000488b")) return false;
    if (!extension_prefix(base + 0x53abb0, "b848290000c3")) return false;
    if (!extension_prefix(base + 0x53b090, "40534883ec20488bd9b948000000e831824f014c8bc04889442438c740086501")) return false;
    if (!extension_prefix(base + 0x35d8c5, "b948000000e8055a6d01488bc84889859001000066c785980100002d2dc7859a")) return false;
    if (!extension_prefix(base + 0x4f40a0, "48895c24185556574154415541564157488d6c24a04881ec600100004c8be948")) return false;
    if (!extension_prefix(base + 0x4f5950, "48895c24184889742420488954241055574156488dac24c0feffff4881ec4002")) return false;
    if (!extension_prefix(base + 0x4f4ee0, "48895c241048894c24085556574154415541564157488d6c24d94881ecc00000")) return false;
    if (!extension_prefix(base + 0x4f5930, "b8ce3b0000c3")) return false;
    if (!extension_prefix(base + 0x4f5bd0, "40534883ec20488bd9b940000000e8f1d653014c8bc04889442438c740086501")) return false;
    if (!extension_prefix(base + 0x35fe28, "b940000000e8a2346d01488bc84889859001000066c785980100002d2dc7859a")) return false;
    if (!extension_prefix(base + 0x36044d, "48890189793c66c741380100897934c7412cf8779c02c74128f8779c02488bc14881c4600200005f5b5dc3")) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7fa40 + 0x0) != base + 0x129450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7fa40 + 0x40) != base + 0x4e9930) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7fa40 + 0x48) != base + 0x5229f0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7fa40 + 0x70) != base + 0x523a10) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7fa40 + 0x80) != base + 0x523670) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7fa40 + 0x98) != base + 0x523a00) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7fa40 + 0xa8) != base + 0x8f450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7fa40 + 0xb0) != base + 0x523a70) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7fa40 + 0xd0) != base + 0x8f450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7fa40 + 0xe0) != base + 0x4e99d0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7fa40 + 0x100) != base + 0x8f440) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7fa40 + 0x108) != base + 0x8f450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f6b0 + 0x0) != base + 0x129500) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f6b0 + 0x40) != base + 0x4e9930) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f6b0 + 0x48) != base + 0x5378f0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f6b0 + 0x70) != base + 0x538a80) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f6b0 + 0x80) != base + 0x538700) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f6b0 + 0x98) != base + 0x538a60) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f6b0 + 0xa8) != base + 0x8f450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f6b0 + 0xb0) != base + 0x538e20) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f6b0 + 0xd0) != base + 0x8f450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f6b0 + 0xe0) != base + 0x4e99d0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f6b0 + 0x100) != base + 0x8f440) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f6b0 + 0x108) != base + 0x8f450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7c788 + 0x0) != base + 0x129450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7c788 + 0x40) != base + 0x4e9930) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7c788 + 0x48) != base + 0x588e10) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7c788 + 0x70) != base + 0x58a710) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7c788 + 0x80) != base + 0x58a120) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7c788 + 0x98) != base + 0x58a700) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7c788 + 0xa8) != base + 0x8f450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7c788 + 0xb0) != base + 0x58a840) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7c788 + 0xd0) != base + 0x8f450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7c788 + 0xe0) != base + 0x4e99d0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7c788 + 0x100) != base + 0x8f440) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7c788 + 0x108) != base + 0x8f450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c805f0 + 0x0) != base + 0x129450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c805f0 + 0x40) != base + 0x4e9930) return false;
    if (read_at<std::uintptr_t>(base + 0x1c805f0 + 0x48) != base + 0x50c4c0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c805f0 + 0x70) != base + 0x50ef10) return false;
    if (read_at<std::uintptr_t>(base + 0x1c805f0 + 0x80) != base + 0x50e0f0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c805f0 + 0x98) != base + 0x50ef00) return false;
    if (read_at<std::uintptr_t>(base + 0x1c805f0 + 0xa8) != base + 0x8f450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c805f0 + 0xb0) != base + 0x50f090) return false;
    if (read_at<std::uintptr_t>(base + 0x1c805f0 + 0xd0) != base + 0x50f120) return false;
    if (read_at<std::uintptr_t>(base + 0x1c805f0 + 0xe0) != base + 0x4e99d0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c805f0 + 0x100) != base + 0x8f440) return false;
    if (read_at<std::uintptr_t>(base + 0x1c805f0 + 0x108) != base + 0x8f450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7cea8 + 0x0) != base + 0x129500) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7cea8 + 0x40) != base + 0x4e9930) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7cea8 + 0x48) != base + 0x579340) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7cea8 + 0x70) != base + 0x57ab70) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7cea8 + 0x80) != base + 0x57a0c0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7cea8 + 0x98) != base + 0x57ab60) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7cea8 + 0xa8) != base + 0x8f450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7cea8 + 0xb0) != base + 0x57ad40) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7cea8 + 0xd0) != base + 0x4e4d50) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7cea8 + 0xe0) != base + 0x4e99d0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7cea8 + 0x100) != base + 0x8f440) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7cea8 + 0x108) != base + 0x8f450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7d238 + 0x0) != base + 0x129450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7d238 + 0x40) != base + 0x4e9930) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7d238 + 0x48) != base + 0x57b460) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7d238 + 0x70) != base + 0x57ca40) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7d238 + 0x80) != base + 0x57c1c0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7d238 + 0x98) != base + 0x57ca30) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7d238 + 0xa8) != base + 0x8f450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7d238 + 0xb0) != base + 0x57ce60) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7d238 + 0xd0) != base + 0x4e4d50) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7d238 + 0xe0) != base + 0x4e99d0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7d238 + 0x100) != base + 0x8f440) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7d238 + 0x108) != base + 0x8f450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f450 + 0x0) != base + 0x129500) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f450 + 0x40) != base + 0x4e9930) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f450 + 0x48) != base + 0x539540) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f450 + 0x70) != base + 0x53abf0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f450 + 0x80) != base + 0x53a600) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f450 + 0x98) != base + 0x53abb0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f450 + 0xa8) != base + 0x8f450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f450 + 0xb0) != base + 0x53b090) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f450 + 0xd0) != base + 0x8f450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f450 + 0xe0) != base + 0x4e99d0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f450 + 0x100) != base + 0x8f440) return false;
    if (read_at<std::uintptr_t>(base + 0x1c7f450 + 0x108) != base + 0x8f450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c80980 + 0x0) != base + 0x129450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c80980 + 0x40) != base + 0x4e9930) return false;
    if (read_at<std::uintptr_t>(base + 0x1c80980 + 0x48) != base + 0x4f40a0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c80980 + 0x70) != base + 0x4f5950) return false;
    if (read_at<std::uintptr_t>(base + 0x1c80980 + 0x80) != base + 0x4f4ee0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c80980 + 0x98) != base + 0x4f5930) return false;
    if (read_at<std::uintptr_t>(base + 0x1c80980 + 0xa8) != base + 0x8f450) return false;
    if (read_at<std::uintptr_t>(base + 0x1c80980 + 0xb0) != base + 0x4f5bd0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c80980 + 0xd0) != base + 0x8f440) return false;
    if (read_at<std::uintptr_t>(base + 0x1c80980 + 0xe0) != base + 0x4e99d0) return false;
    if (read_at<std::uintptr_t>(base + 0x1c80980 + 0x100) != base + 0x8f440) return false;
    if (read_at<std::uintptr_t>(base + 0x1c80980 + 0x108) != base + 0x8f450) return false;
    return true;
}
bool loaded_image_matches(std::uintptr_t base) {
    if (!v12_image_pin(base)) return false;
    if (!extension_image_pin(base)) return false;
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

// Applied only to genuinely owned action memory. Never writes game relations.
void v12_initialize_fixed(std::uintptr_t object, std::uint32_t token) {
    const std::int32_t insult = -1, gift = 25000, fraction = 500;
    const unsigned char ordinary = 0;
    if (token == 0x2947) std::memcpy(reinterpret_cast<void*>(object + 0x40), &insult, sizeof(insult));
    if (token == 0x2948) std::memcpy(reinterpret_cast<void*>(object + 0x40), &gift, sizeof(gift));
    if (token == 0x2e09) {
        std::memcpy(reinterpret_cast<void*>(object + 0x40), &fraction, sizeof(fraction));
        std::memcpy(reinterpret_cast<void*>(object + 0x44), &ordinary, sizeof(ordinary));
    }
}

// Factory/clone defaults are separate from initialized request state.
// 35e051 writes coalition state=2 and jumps past the shared state=0 store.
struct ContractDiagnostic {
    bool completed = false;
    bool state_read = false;
    std::uint32_t state = 0;
    std::uint32_t failure_mask = 0;
};
template <typename T>
void contract_field(std::uintptr_t object, std::uintptr_t offset, T expected,
                    unsigned bit, ContractDiagnostic& diagnostic) {
    if (read_at<T>(object + offset) != expected) diagnostic.failure_mask |= (1U << bit);
}
bool default_fields_match(std::uintptr_t object, const Action& action, std::uintptr_t base,
                          ContractDiagnostic& diagnostic, bool fixed_parameters = false) {
    if (object == 0 || object == base + 0x1fd1ca0) {
        diagnostic.failure_mask |= 1U;
        diagnostic.completed = true;
        return false;
    }
    contract_field(object, 0, base + action.vtable, 1, diagnostic);
    if (diagnostic.failure_mask != 0) {
        diagnostic.completed = true;
        return false; // Do not inspect fields of an object with the wrong derived identity.
    }
    contract_field(object, 8, static_cast<std::uint32_t>(0x165), 2, diagnostic);
    contract_field(object, 0x10, static_cast<std::uint64_t>(0x2d2d2d), 3, diagnostic);
    contract_field(object, 0x18, static_cast<std::uint64_t>(0x2d2d2d), 4, diagnostic);
    contract_field(object, 0x20, static_cast<std::uint64_t>(0x2d2d2d), 5, diagnostic);
    contract_field(object, 0x28, static_cast<std::uint32_t>(0x29c77f8), 6, diagnostic);
    contract_field(object, 0x2c, static_cast<std::uint32_t>(0x29c77f8), 7, diagnostic);
    contract_field(object, 0x30, static_cast<std::uint32_t>(0xffffffff), 8, diagnostic);
    diagnostic.state = read_at<std::uint32_t>(object + 0x34);
    diagnostic.state_read = true;
    if (diagnostic.state != (action.token == 0x2de0 ? 2U : 0U)) diagnostic.failure_mask |= 1U << 9;
    contract_field(object, 0x38, static_cast<std::uint16_t>(1), 10, diagnostic);
    contract_field(object, 0x3c, static_cast<std::uint32_t>(0), 11, diagnostic);
    if (action.token == 0x2947) contract_field(object, 0x40, static_cast<std::int32_t>(-1), 12, diagnostic);
    if (action.token == 0x2948) contract_field(object, 0x40, static_cast<std::int32_t>(fixed_parameters ? 25000 : 0), 13, diagnostic);
    if (action.token == 0x2e09) {
        contract_field(object, 0x40, static_cast<std::int32_t>(fixed_parameters ? 500 : 0), 14, diagnostic);
        contract_field(object, 0x44, static_cast<unsigned char>(0), 15, diagnostic);
    }
    if (action.token == 0x2a25) {
        contract_field(object, 0x40, static_cast<std::int32_t>(fixed_parameters ? 1000 : 0), 16, diagnostic);
        contract_field(object, 0x44, static_cast<std::int32_t>(fixed_parameters ? 10 : 0), 17, diagnostic);
    }
    if (action.size == 0x68) {
        contract_field(object, 0x40, static_cast<unsigned char>(0), 18, diagnostic);
        contract_field(object, 0x50, static_cast<std::uint64_t>(0), 19, diagnostic);
        contract_field(object, 0x58, static_cast<std::uint64_t>(15), 20, diagnostic);
        contract_field(object, 0x60, static_cast<unsigned char>(0), 21, diagnostic);
    }
    diagnostic.completed = true;
    return diagnostic.failure_mask == 0;
}
void format_diagnostic(const ContractDiagnostic& diagnostic, char (&state)[16], char (&mask)[16]) {
    if (diagnostic.state_read) std::snprintf(state, sizeof(state), "%u", diagnostic.state);
    else std::memcpy(state, "null", 5);
    if (diagnostic.completed) std::snprintf(mask, sizeof(mask), "%u", diagnostic.failure_mask);
    else std::memcpy(mask, "null", 5);
}

bool one_lifecycle(std::uintptr_t base, const Action& action, Logger logger) {
    void* original = nullptr;
    void* copy = nullptr;
    bool original_ok = false;
    bool copy_ok = false;
    bool original_destroyed = false;
    bool copy_destroyed = false;
    DWORD exception = 0;
    ContractDiagnostic factory_diagnostic{}, clone_diagnostic{}, retained_diagnostic{};
    __try {
        const auto factory = reinterpret_cast<Factory>(base + kFactoryRva);
        original = factory(action.token, nullptr);
        original_ok = default_fields_match(reinterpret_cast<std::uintptr_t>(original), action, base, factory_diagnostic);
        if (original_ok) {
            v12_initialize_fixed(reinterpret_cast<std::uintptr_t>(original), action.token);
            if (action.token == 0x2a25) {
                const std::int32_t amount = 1000, years = 10;
                std::memcpy(static_cast<unsigned char*>(original) + 0x40, &amount, sizeof(amount));
                std::memcpy(static_cast<unsigned char*>(original) + 0x44, &years, sizeof(years));
            }
            copy = reinterpret_cast<Clone>(base + action.clone)(original);
            copy_ok = copy != original && default_fields_match(reinterpret_cast<std::uintptr_t>(copy), action, base, clone_diagnostic, true)
                && default_fields_match(reinterpret_cast<std::uintptr_t>(original), action, base, retained_diagnostic, true);
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
    char factory_state[16]{}, factory_mask[16]{}, clone_state[16]{}, clone_mask[16]{}, retained_state[16]{}, retained_mask[16]{};
    format_diagnostic(factory_diagnostic, factory_state, factory_mask);
    format_diagnostic(clone_diagnostic, clone_state, clone_mask);
    format_diagnostic(retained_diagnostic, retained_state, retained_mask);
    char line[4096]{};
    const int count = std::snprintf(line, sizeof(line),
                  "{\"event\":\"pair_lifecycle\",\"action\":\"%s\",\"size\":%zu,\"thread_id\":%lu,"
                  "\"factory_fields_ok\":%s,\"clone_fields_ok\":%s,\"original_destroyed\":%s,"
                  "\"clone_destroyed\":%s,\"exception\":%lu,\"submitted\":false,"
                  "\"fixed_subsidy_amount_milli\":%d,\"fixed_subsidy_duration_years\":%d,"
        "\"fixed_gift_amount_milli\":%d,\"fixed_transfer_fraction_milli\":%d,\"fixed_insult_index\":%d,"
                  "\"factory_contract_checked\":%s,\"factory_state\":%s,\"factory_contract_failure_mask\":%s,"
                  "\"clone_contract_checked\":%s,\"clone_state\":%s,\"clone_contract_failure_mask\":%s,"
                  "\"retained_original_contract_checked\":%s,\"retained_original_state\":%s,\"retained_original_contract_failure_mask\":%s}",
                  action.name, action.size, GetCurrentThreadId(), original_ok ? "true" : "false",
                  copy_ok ? "true" : "false", original_destroyed ? "true" : "false",
                  copy_destroyed ? "true" : "false", exception, action.token == 0x2a25 ? 1000 : 0, action.token == 0x2a25 ? 10 : 0, action.token == 0x2948 ? 25000 : 0, action.token == 0x2e09 ? 500 : 0, action.token == 0x2947 ? -1 : 0,
                  factory_diagnostic.completed ? "true" : "false", factory_state, factory_mask,
                  clone_diagnostic.completed ? "true" : "false", clone_state, clone_mask,
                  retained_diagnostic.completed ? "true" : "false", retained_state, retained_mask);
    if (count <= 0 || static_cast<std::size_t>(count) >= sizeof(line)) return false;
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
    logger("{\"event\":\"pair_lifecycle_complete\",\"passed\":20,\"submitted\":false}");
    return true;
}
