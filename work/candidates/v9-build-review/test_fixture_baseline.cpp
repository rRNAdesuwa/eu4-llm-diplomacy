// Pure synthetic-memory checks. Never observes a process or invokes an engine method.
#include "../../native/test-fixture-v9-1375.cpp"

namespace eu4_test_controls_1375 {
bool observe(Snapshot&, std::uint32_t&) { return false; }
}
namespace {
alignas(8) unsigned char france[0x1900]{}, navarra[0x1900]{};
alignas(8) unsigned char fra_records[189 * 0x48]{}, nav_records[189 * 0x48]{};
alignas(8) unsigned char fra_root[0x100]{}, nav_root[0x100]{};
alignas(8) unsigned char fra_index[4096 * 0x10]{}, nav_index[4096 * 0x10]{};
std::uintptr_t countries[256]{};
unsigned checks = 0, failures = 0;
template <typename T> void put(unsigned char* base, std::size_t offset, T value) {
    std::memcpy(base + offset, &value, sizeof(value));
}
std::uintptr_t addr(const void* value) { return reinterpret_cast<std::uintptr_t>(value); }
void reset() {
    std::memset(france, 0, sizeof(france)); std::memset(navarra, 0, sizeof(navarra));
    std::memset(fra_records, 0, sizeof(fra_records)); std::memset(nav_records, 0, sizeof(nav_records));
    std::memset(fra_root, 0, sizeof(fra_root)); std::memset(nav_root, 0, sizeof(nav_root));
    std::memset(fra_index, 0, sizeof(fra_index)); std::memset(nav_index, 0, sizeof(nav_index));
    std::memset(countries, 0, sizeof(countries));
    countries[122] = addr(france); countries[188] = addr(navarra);
    put(france, 0x20, eu4_test_fixture_1375::kFrance);
    put(navarra, 0x20, eu4_test_fixture_1375::kNavarra);
    put(france, 0x1510, addr(fra_records)); put(navarra, 0x1510, addr(nav_records));
    put(fra_records, 188 * 0x48, addr(fra_root)); put(nav_records, 122 * 0x48, addr(nav_root));
    put(fra_records, 188 * 0x48 + 0x10, eu4_test_fixture_1375::kNavarra);
    put(nav_records, 122 * 0x48 + 0x10, eu4_test_fixture_1375::kFrance);
}
void check(const char* name, bool expected) {
    const eu4_test_fixture_1375::Identity id{0, addr(countries), addr(france)};
    eu4_test_fixture_1375::Baseline state{};
    const bool actual = eu4_test_fixture_1375::fixture_baseline(id, state);
    ++checks;
    if (actual != expected) { ++failures; std::printf("FAIL %s\n", name); }
}
void entry(unsigned char* root, unsigned char* index, std::uint32_t slot) {
    put(root, 0x80, addr(index)); put(root, 0x8c, std::uint32_t{1});
    put(index, 0, slot); put(index, 8, addr(france));
}
}
int main() {
    reset(); check("empty clean pair", true);
    reset(); put(navarra, 0x20, eu4_test_fixture_1375::kFrance); check("wrong full NAV handle", false);
    reset(); put(navarra, 0x18f0, eu4_test_fixture_1375::kFrance); check("NAV subject", false);
    reset(); put(navarra, 0x18f0, std::uint64_t{0x2d2d2d}); check("native invalid overlord", true);
    reset(); fra_records[188 * 0x48 + 0x45] = 1; check("FRA active truce mask1", false);
    reset(); nav_records[122 * 0x48 + 0x45] = 1; check("NAV active truce mask1", false);
    reset(); fra_records[188 * 0x48 + 0x45] = 2; check("different flag mask2", true);
    reset(); entry(fra_root, fra_index, 188); check("FRA alliance with NAV", false);
    reset(); entry(nav_root, nav_index, 122); check("NAV alliance with FRA", false);
    reset(); entry(fra_root, fra_index, 123); check("unrelated alliance", true);
    reset(); entry(fra_root, fra_index, 123); put(fra_index, 8, std::uintptr_t{0}); check("null indexed object", false);
    reset(); entry(fra_root, fra_index, 4096); check("invalid indexed slot", false);
    reset(); put(fra_root, 0x8c, std::uint32_t{1}); check("nonempty null index", false);
    reset(); put(fra_root, 0x80, std::uintptr_t{1}); check("malformed empty index", false);
    reset(); entry(fra_root, fra_index, 123); put(fra_root, 0x8c, std::uint32_t{4097}); check("count above bound", false);
    reset(); put(fra_records, 188 * 0x48 + 0x10, eu4_test_fixture_1375::kFrance); check("wrong counterpart", false);
    reset(); put(fra_records, 188 * 0x48, std::uintptr_t{0}); check("missing root", false);
    reset(); put(france, 0x1510, std::uintptr_t{0}); check("missing records", false);
    reset(); countries[188] = 0; check("missing NAV country", false);
    reset(); entry(fra_root, fra_index, 123); put(fra_root, 0x8c, std::uint32_t{4096});
    for (std::uint32_t i = 0; i < 4096; ++i) {
        put(fra_index, i * 0x10, std::uint32_t{123}); put(fra_index, i * 0x10 + 8, addr(france));
    }
    check("maximum bounded complete index", true);
    reset();
    const eu4_test_fixture_1375::Identity id{0, addr(countries), addr(france)};
    eu4_test_fixture_1375::Baseline first{}, second{};
    bool matched = eu4_test_fixture_1375::fixture_baseline(id, first)
        && eu4_test_fixture_1375::fixture_baseline(id, second)
        && eu4_test_fixture_1375::same_baseline(first, second);
    ++checks; if (!matched) { ++failures; std::puts("FAIL stable double pass"); }
    entry(fra_root, fra_index, 123);
    matched = eu4_test_fixture_1375::fixture_baseline(id, second)
        && !eu4_test_fixture_1375::same_baseline(first, second);
    ++checks; if (!matched) { ++failures; std::puts("FAIL changed relation index between passes"); }
    reset(); put(navarra, 0x18f0, std::uint64_t{0x2d2d2d});
    matched = eu4_test_fixture_1375::fixture_baseline(id, second)
        && !eu4_test_fixture_1375::same_baseline(first, second);
    ++checks; if (!matched) { ++failures; std::puts("FAIL changed overlord sentinel between passes"); }
    std::printf("fixture baseline: %u checks, %u failures; synthetic memory only\n", checks, failures);
    return failures ? 1 : 0;
}
