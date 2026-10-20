// EU4 1.37.5 no-submit preview experiment, scoped to the exact reviewed build.
// Call only after the separate lifecycle test passed, on the observed game
// thread, after a separate preview marker. No hook or DllMain in this module.
// Static specification: work/reports/native-preview-1375.json.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {
using Logger = void (*)(const char*);
using Factory = void* (__fastcall*)(std::uint32_t, const void*);
using Preview = bool (__fastcall*)(void*, void*, bool);
using Destructor = void* (__fastcall*)(void*, unsigned int);
constexpr std::uintptr_t kFactory = 0x35d210;
constexpr std::uintptr_t kPreview = 0x4e9d00;
constexpr std::uintptr_t kDatabasePointer = 0x233d8d0;
constexpr std::uintptr_t kGamePointer = 0x233fe78;
constexpr const char* kFactoryPrefix = "40555357488dac24a0feffff4881ec60020000488bda33ff89bd8001000081f9";
constexpr const char* kPreviewPrefix = "48895c2410448844241848894c24085556574154415541564157488d6c24d948";

struct Country {
    const char* tag;
    std::uint32_t slot;
    std::uint64_t expected_handle;
};
// Slots and complete handles came from the last read-only identity-checked
// snapshot. Each case re-reads and verifies the actual live country objects.
constexpr Country kFrance{"FRA", 122, 0x0100007a00415246ULL};
constexpr Country kTargets[] = {
    {"ENG", 46, 0x0100002e00474e45ULL},
    {"POR", 189, 0x010000bd00524f50ULL},
};

struct Action {
    const char* name;
    std::uint32_t token;
    std::uintptr_t vtable;
    std::uintptr_t validity;
    std::uintptr_t destructor;
    std::uintptr_t token_getter;
    const char* validity_prefix;
};
constexpr Action kActions[] = {
    {"vassalaction", 0x2940, 0x1c7fd20, 0x51f020, 0x129450, 0x51f570,
     "48895c24105556574154415541564157488d6c24d94881ecc0000000488bf24c"},
    {"royal_marriage", 0x28df, 0x1c80ab0, 0x4ef3b0, 0x4ed5b0, 0x4e3df0,
     "48895c2410488974241848897c2420554154415541564157488bec4883ec6048"},
    {"improve_relation", 0x2ddb, 0x1c7dd68, 0x574460, 0x129450, 0x4e3dc0,
     "48895c2408488974241048897c241841564883ec40488bda488bf140b701488b"},
    {"guaranteeaction", 0x2941, 0x1c7fe50, 0x521ad0, 0x129450, 0x5220b0,
     "48895c241048897424185557415541564157488bec4881ec80000000488bda4c"},
    {"spy_network", 0x3378, 0x1c7cc48, 0x5856a0, 0x129450, 0x585bc0,
     "48895c24104889742418574883ec60488bda488bf140b7014c8b4120488b050d"},
    {"allianceaction", 0x293d, 0x1c80720, 0x511d60, 0x129450, 0x512d40, "48895c24105556574154415541564157488d6c24d94881ecb0000000488bfa4c"},
    {"milaccess", 0x2943, 0x1c7fb70, 0x525500, 0x129450, 0x525c90, "48895c241048897424185557415441564157488bec4883ec604c8bfa4c8bf141"},
    {"offermilaccess", 0x2944, 0x1c7f580, 0x536400, 0x129450, 0x536ba0, "48895c241048897424185557415441564157488bec4881ec800000004c8bfa4c"},
    {"fleet_access", 0x2dd6, 0x1c7ef90, 0x52fbf0, 0x129450, 0x530280, "48895c24105556574154415541564157488bec4883ec50488bf24c8be941b601"},
    {"offer_fleet_access", 0x2dd7, 0x1c7f1f0, 0x533fa0, 0x129450, 0x534660, "48895c2410488974241848897c2420554154415541564157488bec4883ec6048"},
    {"embargoaction", 0x293e, 0x1c80310, 0x518130, 0x129450, 0x518310, "48895c240848896c24104889742418574883ec60488bfa488be94c8b4110488b"},
    {"warsubsidy", 0x2a25, 0x1c7ed30, 0x548c50, 0x129500, 0x549270, "48895c241055565741564157488d6c24a04881ec60010000488bda488bf14533"},
    {"warningaction", 0x2942, 0x1c7fa40, 0x523670, 0x129450, 0x523a00, "48895c241048896c2418565741564881ec80000000488bda4c8bf140b7014c8b"},
    {"insultaction", 0x2947, 0x1c7f6b0, 0x538700, 0x129500, 0x538a60, "48895c241048896c2418565741564883ec60488bda488be941b6014c8b15ae51"},
    {"form_coalition", 0x2de0, 0x1c7c788, 0x58a120, 0x129450, 0x58a700, "4883ec284c8b41104c8bc9488b059e37db0149c1e82080793800488b88180100"},
    {"support_independence_action", 0x2f2e, 0x1c805f0, 0x50e0f0, 0x129450, 0x50ef00, "48895c241048894c24085556574154415541564157488d6c24d94881eca00000"},
    {"transfer_trade_power", 0x2e09, 0x1c7cea8, 0x57a0c0, 0x129500, 0x57ab60, "48895c2408488974241048897c2418554154415541564157488bec4883ec7048"},
    {"steer_trade", 0x3778, 0x1c7d238, 0x57c1c0, 0x129450, 0x57ca30, "48895c240848896c2410565741564883ec60488bda488bf9803d593ddc010074"},
    {"giftaction", 0x2948, 0x1c7f450, 0x53a600, 0x129500, 0x53abb0, "48895c241048897424185557415441564157488d6c24a04881ec60010000488b"},
    {"trade_favors_for_gold", 0x3bce, 0x1c80980, 0x4f4ee0, 0x129450, 0x4f5930, "48895c241048894c24085556574154415541564157488d6c24d94881ecc00000"},
};

template <typename T>
T read_at(std::uintptr_t address) {
    T value{};
    std::memcpy(&value, reinterpret_cast<const void*>(address), sizeof(value));
    return value;
}
template <typename T>
void write_owned(std::uintptr_t object, std::size_t offset, T value) {
    // The only memory writes in this module are into a checked, newly allocated
    // temporary action owned by this function. No country/world memory writes.
    std::memcpy(reinterpret_cast<void*>(object + offset), &value, sizeof(value));
}
bool object_pointer(std::uintptr_t value) {
    return value >= 0x10000 && value < 0x0000800000000000ULL && value % 8 == 0;
}
unsigned nibble(char c) {
    return c >= '0' && c <= '9' ? static_cast<unsigned>(c - '0') : static_cast<unsigned>(c - 'a' + 10);
}
bool prefix_matches(std::uintptr_t address, const char* hex) {
    const auto bytes = reinterpret_cast<const unsigned char*>(address);
    for (std::size_t i = 0; hex[i * 2] != 0; ++i) {
        if (hex[i * 2 + 1] == 0 || bytes[i] != ((nibble(hex[i * 2]) << 4) | nibble(hex[i * 2 + 1]))) return false;
    }
    return true;
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
bool image_matches(std::uintptr_t base) {
    if (!v12_image_pin(base)) return false;
    if (!extension_image_pin(base)) return false;
    if (base != reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr))) return false;
    const auto dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0 || dos->e_lfanew > 4096) return false;
    const auto pe = reinterpret_cast<const IMAGE_NT_HEADERS64*>(base + static_cast<std::uintptr_t>(dos->e_lfanew));
    if (pe->Signature != IMAGE_NT_SIGNATURE || pe->FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64
        || pe->FileHeader.TimeDateStamp != 0x66fe6ab9 || pe->OptionalHeader.SizeOfImage != 0x25e0000) return false;
    if (!prefix_matches(base + kFactory, kFactoryPrefix) || !prefix_matches(base + kPreview, kPreviewPrefix)) return false;
    for (const Action& action : kActions) {
        if (read_at<std::uintptr_t>(base + action.vtable) != base + action.destructor
            || read_at<std::uintptr_t>(base + action.vtable + 0x80) != base + action.validity
            || read_at<std::uintptr_t>(base + action.vtable + 0x98) != base + action.token_getter
            || !prefix_matches(base + action.validity, action.validity_prefix)
            || read_at<unsigned char>(base + action.token_getter) != 0xb8
            || read_at<std::uint32_t>(base + action.token_getter + 1) != action.token
            || read_at<unsigned char>(base + action.token_getter + 5) != 0xc3) return false;
    }
    return true;
}

struct State {
    std::uint64_t actor;
    std::uint64_t target;
    std::int32_t date;
};
bool country_handle(std::uintptr_t array, const Country& country, std::uint64_t& handle) {
    if (country.slot >= 4096) return false;
    const auto object = read_at<std::uintptr_t>(array + static_cast<std::uintptr_t>(country.slot) * 8);
    if (!object_pointer(object)) return false;
    handle = read_at<std::uint64_t>(object + 0x20);
    if (handle != country.expected_handle || (handle >> 56) == 0
        || ((handle >> 32) & 0xffff) != country.slot) return false;
    // Recheck identity in the array before passing any handle to engine code.
    return read_at<std::uintptr_t>(array + static_cast<std::uintptr_t>(country.slot) * 8) == object
        && read_at<std::uint64_t>(object + 0x20) == handle;
}
bool current_state(std::uintptr_t base, const Country& target, State& state) {
    const auto database = read_at<std::uintptr_t>(base + kDatabasePointer);
    const auto game = read_at<std::uintptr_t>(base + kGamePointer);
    if (!object_pointer(database) || !object_pointer(game)) return false;
    const auto array = read_at<std::uintptr_t>(database + 0x118);
    if (!object_pointer(array) || !country_handle(array, kFrance, state.actor)
        || !country_handle(array, target, state.target)) return false;
    state.date = read_at<std::int32_t>(game + 0x1dd0);
    return state.date > 0 && state.actor != state.target
        && read_at<std::uintptr_t>(base + kDatabasePointer) == database
        && read_at<std::uintptr_t>(base + kGamePointer) == game;
}
// Applied only to genuinely owned action memory. Never writes game relations.
bool v12_fixed_fields(std::uintptr_t object, std::uint32_t token, bool factory_default) {
    if (token == 0x2947) return read_at<std::int32_t>(object + 0x40) == -1;
    if (token == 0x2948) return read_at<std::int32_t>(object + 0x40) == (factory_default ? 0 : 25000);
    if (token == 0x2e09) return read_at<std::int32_t>(object + 0x40) == (factory_default ? 0 : 500)
        && read_at<unsigned char>(object + 0x44) == 0;
    return true; // Remaining five new classes are0x40: no derived input field.
}
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
unsigned v12_mode_count(std::uint32_t token) {
    return token == 0x2942 || token == 0x2947 || token == 0x2948 || token == 0x3bce ? 1U : 2U;
}

bool fixed_parameters_match(std::uintptr_t object, const Action& action) {
    if (!v12_fixed_fields(object, action.token, false)) return false;
    return action.token != 0x2a25 || (read_at<std::int32_t>(object + 0x40) == 1000
        && read_at<std::int32_t>(object + 0x44) == 10);
}
bool initialize_owned(std::uintptr_t base, std::uintptr_t object, const Action& action,
                      const State& state, bool value) {
    if (!object_pointer(object) || object == base + 0x1fd1ca0
        || read_at<std::uintptr_t>(object) != base + action.vtable
        || read_at<std::uint32_t>(object + 8) != 0x165) return false;
    write_owned(object, 0x10, state.actor);
    write_owned(object, 0x18, state.actor);
    write_owned(object, 0x20, state.target);
    write_owned(object, 0x28, state.date);
    write_owned(object, 0x2c, state.date);
    write_owned(object, 0x30, static_cast<std::int32_t>(-1));
    write_owned(object, 0x34, static_cast<std::uint32_t>(action.token == 0x2de0 ? 2U : 0U));
    write_owned(object, 0x38, static_cast<unsigned char>(value ? 1 : 0));
    write_owned(object, 0x39, static_cast<unsigned char>(0));
    write_owned(object, 0x3c, static_cast<std::uint32_t>(0));
    v12_initialize_fixed(object, action.token);
    // Fixed research contract: monthly 1.000 ducat, duration 10 YEARS.
    // No external amount, years, offsets or raw fields are accepted.
    if (action.token == 0x2a25) {
        write_owned(object, 0x40, static_cast<std::int32_t>(1000));
        write_owned(object, 0x44, static_cast<std::int32_t>(10));
    }
    // Retain marriage defaults; only fixed, independently evidenced subsidy scalars differ.
    return read_at<std::uint64_t>(object + 0x10) == state.actor
        && read_at<std::uint64_t>(object + 0x18) == state.actor
        && read_at<std::uint64_t>(object + 0x20) == state.target
        && read_at<std::int32_t>(object + 0x28) == state.date
        && read_at<std::int32_t>(object + 0x2c) == state.date
        && read_at<std::int32_t>(object + 0x30) == -1
        && read_at<std::uint32_t>(object + 0x34) == (action.token == 0x2de0 ? 2U : 0U)
        && read_at<unsigned char>(object + 0x38) == static_cast<unsigned char>(value ? 1 : 0) && fixed_parameters_match(object, action);
}

bool run_case(std::uintptr_t base, const Action& action, const Country& target,
              bool value, unsigned case_index, Logger logger, bool& allowed_result) {
    void* owned = nullptr;
    State state{};
    bool state_ok = false;
    bool initialized = false;
    bool allowed = false;
    bool destroyed = false;
    DWORD exception = 0;
    __try {
        state_ok = current_state(base, target, state);
        if (state_ok) {
            owned = reinterpret_cast<Factory>(base + kFactory)(action.token, nullptr);
            const auto address = reinterpret_cast<std::uintptr_t>(owned);
            initialized = initialize_owned(base, address, action, state, value);
            if (initialized) {
                // RDX=null: bool-only, no CString ABI. R8=false: retain normal
                // cooldown/diplomat requirements. The generic method itself
                // invokes the type-specific validity method when appropriate.
                allowed = reinterpret_cast<Preview>(base + kPreview)(owned, nullptr, false);
                initialized = initialized && fixed_parameters_match(address, action);
            }
            if (object_pointer(address) && address != base + 0x1fd1ca0
                && read_at<std::uintptr_t>(address) == base + action.vtable) {
                reinterpret_cast<Destructor>(base + action.destructor)(owned, 1);
                destroyed = true;
            }
        }
    } __except ((exception = GetExceptionCode()), EXCEPTION_EXECUTE_HANDLER) {
        // No speculative second engine call after any fault; stop the suite.
    }
    char line[1024]{};
    std::snprintf(line, sizeof(line),
        "{\"event\":\"pair_preview_case\",\"case_index\":%u,\"action\":\"%s\",\"mode\":\"%s\","
        "\"value\":%s,\"actor\":\"FRA\",\"target\":\"%s\",\"actor_handle\":\"0x%016llx\","
        "\"target_handle\":\"0x%016llx\",\"current_raw_date\":%d,\"state_verified\":%s,"
        "\"initialized\":%s,\"allowed\":%s,\"exception\":%lu,\"destroyed\":%s,\"thread_id\":%lu,\"submitted\":false,"
        "\"fixed_subsidy_amount_milli\":%d,\"fixed_subsidy_duration_years\":%d,"
        "\"fixed_gift_amount_milli\":%d,\"fixed_transfer_fraction_milli\":%d,\"fixed_insult_index\":%d}",
        case_index, action.name, value ? "positive" : "cancel", value ? "true" : "false", target.tag,
        static_cast<unsigned long long>(state.actor), static_cast<unsigned long long>(state.target), state.date,
        state_ok ? "true" : "false", initialized ? "true" : "false", allowed ? "true" : "false",
        exception, destroyed ? "true" : "false", GetCurrentThreadId(), action.token == 0x2a25 ? 1000 : 0, action.token == 0x2a25 ? 10 : 0, action.token == 0x2948 ? 25000 : 0, action.token == 0x2e09 ? 500 : 0, action.token == 0x2947 ? -1 : 0);
    logger(line);
    allowed_result = allowed;
    // Native rejection is a valid preview result. Infrastructure/ownership
    // failure or a structured exception fails the suite and stops all calls.
    return exception == 0 && state_ok && initialized && destroyed;
}
} // namespace

bool pair_preview(std::uintptr_t base, void (*logger)(const char*)) {
    if (logger == nullptr) return false;
    static volatile LONG attempted = 0;
    if (InterlockedCompareExchange(&attempted, 1, 0)) {
        logger("{\"event\":\"pair_preview_rejected\",\"reason\":\"already_attempted\",\"submitted\":false}");
        return false;
    }
    bool pinned = false;
    __try { pinned = image_matches(base); }
    __except (EXCEPTION_EXECUTE_HANDLER) { pinned = false; }
    if (!pinned) {
        logger("{\"event\":\"pair_preview_rejected\",\"reason\":\"build_identity_mismatch\",\"submitted\":false}");
        return false;
    }
    unsigned count = 0;
    unsigned accepted = 0;
    for (const Country& target : kTargets) {
        for (const Action& action : kActions) {
            for (unsigned mode = 0; mode < v12_mode_count(action.token); ++mode) {
                bool allowed = false;
                if (!run_case(base, action, target, mode == 0, ++count, logger, allowed)) return false;
                if (allowed) ++accepted;
            }
        }
    }
    char line[256]{};
    std::snprintf(line, sizeof(line),
        "{\"event\":\"pair_preview_all_cases_complete\",\"cases\":%u,\"accepted\":%u,\"rejected\":%u,\"thread_id\":%lu,\"submitted\":false}",
        count, accepted, count - accepted, GetCurrentThreadId());
    logger(line);
    return count == 72;
}
