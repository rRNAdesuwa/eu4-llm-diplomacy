// Exact-build standalone research core. No DllMain, hook, exports, mailbox,
// marker reader, native execution on import, linking or automatic retries.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
#include <cstring>
#include "pair-engine-1375.h"

namespace eu4_pair_1375 {
namespace {
using Factory = void* (__fastcall*)(std::uint32_t, const void*);
using Setter = void (__fastcall*)(void*, bool);
using Preview = bool (__fastcall*)(void*, void*, bool);
using Wrapper = void** (__fastcall*)(void*, void**);
using Gate = bool (__fastcall*)(void*);
using Destructor = void* (__fastcall*)(void*, unsigned int);
using Submit = bool (__fastcall*)(void*, void**);
constexpr std::uintptr_t kFactory = 0x35d210, kPreview = 0x4e9d00;
constexpr std::uintptr_t kWrapper = 0x4e9930, kGate = 0x4e8630;
constexpr std::uintptr_t kCommandVtable = 0x1c814b0, kCommandDestructor = 0x4e7470;
constexpr std::uintptr_t kDatabase = 0x233d8d0, kGame = 0x233fe78, kSentinel = 0x1fd1ca0;
constexpr std::uintptr_t kContextSubmit = 0x14ca210, kServerVtable = 0x1cb8460;
constexpr std::uintptr_t kTransportVtable = 0x1d96178, kTransportSubmit = 0x1580370;
constexpr std::uintptr_t kMissionVtable = 0x1c4b2b8, kSpyTaskVtable = 0x1ce3ba0;
constexpr std::uintptr_t kSubjectRegistry = 0x233ffd8;
constexpr unsigned kMaxRelations = 4096, kMaxEnvoys = 256, kMaxTasks = 1024;
volatile LONG g_busy = 0;
volatile LONG g_frozen = 0;

struct Pin { std::uintptr_t rva; const char* bytes; };
constexpr Pin kPins[] = {
    {kFactory, "40555357488dac24a0feffff4881ec60020000488bda33ff89bd8001000081f9"},
    {kPreview, "48895c2410448844241848894c24085556574154415541564157488d6c24d948"},
    {kWrapper, "48895c2408574883ec20488b01488bfaff90b0000000488b0d2b65e501488bd8"},
    {kGate, "48896c24184889742420574883ec20488bf9488b4950837934007567488b01ff"},
    {kCommandDestructor, "48895c2408574883ec208bfa488bd9488d052aa07901488901488b49504885c9"},
    {0x129450, "40534883ec20488d051b51b101488bd9488901f6c201740aba40000000e87e00"},
    {0x4ed5b0, "48895c2408574883ec20488bf98bda4883c140e89880baff488d05a90f750148"},
    {0x8f450, "32c0c3"}, {0x8f440, "b001c3"}, {0x4e4d50, "0fb64138c3"},
    {0x4e99d0, "885138c3"},
    {0x586330, "40554883ec30885138488be984d20f85fc000000488b41104c8b492048c1e820"},
    {0x585bc0, "b878330000c3"},
    {0x811aa0, "488b8130030000488b8070030000c3"},
    {kContextSubmit, "48895c240848897424184889542410574883ec20488bf2488bf9488b1a48c702"},
    {0x14ca29c, "b301488b0e4885c9740b4c8b01ba0100000041ff100fb6c3"},
    {kTransportSubmit, "4885d20f8434090000488954241048894c240853565741544155415641574881"},
};
struct Action {
    std::uint32_t token, size;
    std::uintptr_t vtable, clone, destructor, getter, validity, envoy_predicate, favor_predicate, setter;
    const char* clone_prefix;
    const char* validity_prefix;
};
constexpr Action kActions[] = {
    {0x2940, 0x40, 0x1c7fd20, 0x51fa00, 0x129450, 0x51f570, 0x51f020, 0x8f440, 0x8f450, 0x4e99d0,
     "40534883ec20488bd9b940000000e8c13851014c8bc04889442438c740086501",
     "48895c24105556574154415541564157488d6c24d94881ecc0000000488bf24c"},
    {0x28df, 0x68, 0x1c80ab0, 0x4f07d0, 0x4ed5b0, 0x4e3df0, 0x4ef3b0, 0x8f440, 0x8f450, 0x4e99d0,
     "40534883ec20488bd9b968000000e8f12a54014c8bc04889442438c740086501",
     "48895c2410488974241848897c2420554154415541564157488bec4883ec6048"},
    {0x2ddb, 0x40, 0x1c7dd68, 0x574b20, 0x129450, 0x4e3dc0, 0x574460, 0x4e4d50, 0x8f450, 0x4e99d0,
     "40534883ec20488bd9b940000000e8a1e74b014c8bc04889442438c740086501",
     "48895c2408488974241048897c241841564883ec40488bda488bf140b701488b"},
    {0x2941, 0x40, 0x1c7fe50, 0x5224c0, 0x129450, 0x5220b0, 0x521ad0, 0x8f440, 0x8f450, 0x4e99d0,
     "40534883ec20488bd9b940000000e8010e51014c8bc04889442438c740086501",
     "48895c241048897424185557415541564157488bec4881ec80000000488bda4c"},
    {0x3378, 0x40, 0x1c7cc48, 0x586200, 0x129450, 0x585bc0, 0x5856a0, 0x4e4d50, 0x8f440, 0x586330,
     "40534883ec20488bd9b940000000e8c1d04a014c8bc04889442438c740086501",
     "48895c24104889742418574883ec60488bda488bf140b7014c8b4120488b050d"},
};
constexpr const char* kNames[] = {
    "offer_vassalization", "cancel_vassalization", "royal_marriage", "break_marriage",
    "improve_relations", "stop_improving_relations", "guarantee", "revoke_guarantee",
    "build_spy_network", "stop_building_spy_network"
};
struct Country { const char* tag; std::uint32_t slot; std::uint64_t handle; };
constexpr Country kCountries[] = {
    {"FRA", 122, 0x0100007a00415246ULL}, {"ENG", 46, 0x0100002e00474e45ULL},
    {"POR", 189, 0x010000bd00524f50ULL}
};
struct Live {
    std::uintptr_t database, game, array, actor_object, target_object;
    Stamp stamp;
};
struct Binding {
    std::int32_t envoy;
    std::uintptr_t entry, mission, task;
};
struct Context { std::uintptr_t server, holder, context, transport; };

template<typename T> T read_at(std::uintptr_t p) {
    T result{};
    std::memcpy(&result, reinterpret_cast<const void*>(p), sizeof(result));
    return result;
}
template<typename T> void write_owned(std::uintptr_t p, std::size_t offset, T value) {
    std::memcpy(reinterpret_cast<void*>(p + offset), &value, sizeof(value));
}
bool pointer(std::uintptr_t p) { return p >= 0x10000 && p < 0x0000800000000000ULL && p % 8 == 0; }
const Country* country(const char (&tag)[4]) {
    for (const Country& known : kCountries) if (std::memcmp(tag, known.tag, 4) == 0) return &known;
    return nullptr;
}
unsigned nibble(char c) { return c >= '0' && c <= '9' ? static_cast<unsigned>(c - '0') : static_cast<unsigned>(c - 'a' + 10); }
bool prefix(std::uintptr_t p, const char* expected) {
    for (std::size_t i = 0; expected[i * 2] != 0; ++i) {
        if (expected[i * 2 + 1] == 0 || read_at<unsigned char>(p + i) != ((nibble(expected[i * 2]) << 4) | nibble(expected[i * 2 + 1]))) return false;
    }
    return true;
}
bool image_pin(std::uintptr_t module) {
    const auto dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(module);
    if (!pointer(module) || dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0 || dos->e_lfanew > 4096) return false;
    const auto pe = reinterpret_cast<const IMAGE_NT_HEADERS64*>(module + static_cast<std::uintptr_t>(dos->e_lfanew));
    if (pe->Signature != IMAGE_NT_SIGNATURE || pe->FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64
        || pe->FileHeader.TimeDateStamp != 0x66fe6ab9 || pe->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC
        || pe->OptionalHeader.SizeOfImage != 0x25e0000) return false;
    for (const Pin& pin : kPins) if (!prefix(module + pin.rva, pin.bytes)) return false;
    if (read_at<std::uintptr_t>(module + kCommandVtable) != module + kCommandDestructor
        || read_at<std::uintptr_t>(module + kCommandVtable + 0x40) != module + kGate
        || read_at<std::uintptr_t>(module + kServerVtable) != module + 0x80b420
        || read_at<std::uintptr_t>(module + kServerVtable + 0x80) != module + 0x811aa0
        || read_at<std::uintptr_t>(module + kTransportVtable) != module + 0x15800d0
        || read_at<std::uintptr_t>(module + kTransportVtable + 0x30) != module + kTransportSubmit
        || read_at<std::uintptr_t>(module + kMissionVtable + 0x70) != module + 0x8f440
        || read_at<std::uintptr_t>(module + kSpyTaskVtable + 0x70) != module + 0x585bc0) return false;
    for (const Action& a : kActions) {
        if (read_at<std::uintptr_t>(module + a.vtable) != module + a.destructor
            || read_at<std::uintptr_t>(module + a.vtable + 0x40) != module + kWrapper
            || read_at<std::uintptr_t>(module + a.vtable + 0x80) != module + a.validity
            || read_at<std::uintptr_t>(module + a.vtable + 0x98) != module + a.getter
            || read_at<std::uintptr_t>(module + a.vtable + 0xa8) != module + 0x8f450
            || read_at<std::uintptr_t>(module + a.vtable + 0xb0) != module + a.clone
            || read_at<std::uintptr_t>(module + a.vtable + 0xe0) != module + a.setter
            || read_at<std::uintptr_t>(module + a.vtable + 0x100) != module + a.envoy_predicate
            || read_at<std::uintptr_t>(module + a.vtable + 0x108) != module + a.favor_predicate
            || !prefix(module + a.clone, a.clone_prefix) || !prefix(module + a.validity, a.validity_prefix)
            || read_at<unsigned char>(module + a.getter) != 0xb8 || read_at<std::uint32_t>(module + a.getter + 1) != a.token
            || read_at<unsigned char>(module + a.getter + 5) != 0xc3) return false;
    }
    return true;
}
bool resolve_country(std::uintptr_t array, const Country& spec, std::uintptr_t& found) {
    found = read_at<std::uintptr_t>(array + static_cast<std::uintptr_t>(spec.slot) * 8);
    return pointer(found) && read_at<std::uint64_t>(found + 0x20) == spec.handle
        && read_at<std::uintptr_t>(array + static_cast<std::uintptr_t>(spec.slot) * 8) == found;
}
bool current(std::uintptr_t module, const Country& actor, const Country& target, Live& live) {
    live.database = read_at<std::uintptr_t>(module + kDatabase);
    live.game = read_at<std::uintptr_t>(module + kGame);
    if (!pointer(live.database) || !pointer(live.game)) return false;
    live.array = read_at<std::uintptr_t>(live.database + 0x118);
    if (!pointer(live.array) || !resolve_country(live.array, actor, live.actor_object)
        || !resolve_country(live.array, target, live.target_object)) return false;
    live.stamp.actor_handle = actor.handle;
    live.stamp.target_handle = target.handle;
    live.stamp.player_handle = read_at<std::uint64_t>(live.game + 0x1e60);
    const auto player_slot = static_cast<std::uint32_t>((live.stamp.player_handle >> 32) & 0xffff);
    if (player_slot >= 4096 || (live.stamp.player_handle >> 56) == 0) return false;
    const auto player = read_at<std::uintptr_t>(live.array + static_cast<std::uintptr_t>(player_slot) * 8);
    if (!pointer(player) || read_at<std::uint64_t>(player + 0x20) != live.stamp.player_handle) return false;
    live.stamp.raw_date = read_at<std::int32_t>(live.game + 0x1dd0);
    live.stamp.world_cookie = live.game;
    live.stamp.pid = GetCurrentProcessId();
    live.stamp.thread_id = GetCurrentThreadId();
    FILETIME created{}, exited{}, kernel{}, user{};
    if (!GetProcessTimes(GetCurrentProcess(), &created, &exited, &kernel, &user) || exited.dwLowDateTime || exited.dwHighDateTime) return false;
    live.stamp.process_creation_filetime = (static_cast<std::uint64_t>(created.dwHighDateTime) << 32) | created.dwLowDateTime;
    return live.stamp.raw_date > 0 && live.stamp.process_creation_filetime != 0
        && read_at<std::uintptr_t>(module + kDatabase) == live.database
        && read_at<std::uintptr_t>(module + kGame) == live.game
        && read_at<std::uintptr_t>(live.database + 0x118) == live.array;
}
bool same_state(std::uintptr_t module, const Country& actor, const Country& target, const Live& expected) {
    Live now{};
    return current(module, actor, target, now) && now.database == expected.database && now.game == expected.game
        && now.array == expected.array && now.actor_object == expected.actor_object && now.target_object == expected.target_object
        && now.stamp.raw_date == expected.stamp.raw_date && now.stamp.player_handle == expected.stamp.player_handle
        && now.stamp.process_creation_filetime == expected.stamp.process_creation_filetime
        && now.stamp.thread_id == expected.stamp.thread_id;
}
bool record_root(std::uintptr_t owner, const Country& other, std::uintptr_t& root, std::uintptr_t& record) {
    const auto records = read_at<std::uintptr_t>(owner + 0x1510);
    if (!pointer(records)) return false;
    record = records + static_cast<std::uintptr_t>(other.slot) * 0x48;
    root = read_at<std::uintptr_t>(record);
    return pointer(root) && read_at<std::uint64_t>(record + 0x10) == other.handle;
}
bool indexed_object(std::uintptr_t owner, const Country& other, std::uintptr_t offset, std::uintptr_t count_offset, std::uintptr_t& object) {
    std::uintptr_t root = 0, record = 0;
    if (!record_root(owner, other, root, record)) return false;
    const auto array = read_at<std::uintptr_t>(root + offset);
    const auto count = read_at<std::uint32_t>(root + count_offset);
    if (count > kMaxRelations || (count != 0 && !pointer(array))) return false;
    object = 0;
    for (unsigned i = 0; i < count; ++i) {
        const auto item = array + static_cast<std::uintptr_t>(i) * 0x10;
        const auto slot = read_at<std::uint32_t>(item);
        if (slot >= 4096) return false;
        if (slot == other.slot) {
            if (object != 0) return false;
            object = read_at<std::uintptr_t>(item + 8);
            if (!pointer(object)) return false;
        }
    }
    return object != 0;
}
bool paired_relation(std::uintptr_t module, const Live& live, const Country& actor, const Country& target,
                     std::uintptr_t offset, std::uintptr_t count_offset, std::uintptr_t vtable, std::uintptr_t& object) {
    std::uintptr_t reverse = 0;
    return indexed_object(live.actor_object, target, offset, count_offset, object)
        && indexed_object(live.target_object, actor, offset, count_offset, reverse) && object == reverse
        && read_at<std::uintptr_t>(object) == module + vtable && read_at<unsigned char>(object + 0x28) == 0
        && read_at<std::uint64_t>(object + 0x10) == actor.handle && read_at<std::uint64_t>(object + 0x18) == target.handle;
}
bool definition_name(std::uintptr_t definition, const char* expected) {
    if (!pointer(definition)) return false;
    const auto string = definition + 0x10;
    const auto length = read_at<std::uint64_t>(string + 0x10), capacity = read_at<std::uint64_t>(string + 0x18);
    if (length == 0 || length > 128 || length > capacity || length != std::strlen(expected)) return false;
    const auto chars = capacity < 16 ? string : read_at<std::uintptr_t>(string);
    return pointer(chars) && read_at<unsigned char>(chars + static_cast<std::uintptr_t>(length)) == 0
        && std::memcmp(reinterpret_cast<const void*>(chars), expected, static_cast<std::size_t>(length)) == 0;
}
bool spy_list(std::uintptr_t module, const Live& live, const Binding& binding) {
    const auto owner = read_at<std::uintptr_t>(live.target_object + 0x14b0);
    if (!pointer(owner)) return false;
    const auto head = read_at<std::uintptr_t>(owner + 0x4f0), tail = read_at<std::uintptr_t>(owner + 0x4f8);
    const auto count = read_at<std::uint32_t>(owner + 0x500);
    if (count == 0 || count > kMaxTasks || !pointer(head) || !pointer(tail)) return false;
    std::uintptr_t previous = 0, node = head;
    unsigned matches = 0;
    // Bounded count and backwards linkage reject cycles without dynamic memory.
    for (unsigned i = 0; i < count; ++i) {
        if (!pointer(node) || read_at<std::uintptr_t>(node + 8) != previous) return false;
        const auto removed = read_at<unsigned char>(node + 0x18);
        if (removed > 1) return false;
        if (!removed) {
            const auto task = read_at<std::uintptr_t>(node);
            if (!pointer(task)) return false;
            if (read_at<std::uintptr_t>(task) == module + kSpyTaskVtable) {
                if (read_at<unsigned char>(task + 0x28) != 0 || read_at<std::uintptr_t>(task + 0x10) != owner
                    || read_at<std::uint64_t>(task + 0x20) != live.stamp.target_handle) return false;
                if (read_at<std::uint64_t>(task + 0x18) == live.stamp.actor_handle) {
                    if (task != binding.task || read_at<std::int32_t>(task + 0x2c) != binding.envoy) return false;
                    ++matches;
                }
            }
        } // A marked node can retain a freed task pointer; never follow it.
        previous = node;
        node = read_at<std::uintptr_t>(node + 0x10);
    }
    return node == 0 && previous == tail && matches == 1;
}
bool spy_binding(std::uintptr_t module, const Live& live, const Country& target, Binding& binding) {
    std::uintptr_t root = 0, record = 0;
    if (!record_root(live.actor_object, target, root, record) || !(read_at<unsigned char>(record + 0x46) & 8)) return false;
    const auto holder = read_at<std::uintptr_t>(live.actor_object + 0x1480);
    if (!pointer(holder)) return false;
    const auto manager = read_at<std::uintptr_t>(holder + 0x18);
    if (!pointer(manager)) return false;
    const auto begin = read_at<std::uintptr_t>(manager + 0x20), end = read_at<std::uintptr_t>(manager + 0x28);
    if (!pointer(begin) || end < begin || (end - begin) % 8 || (end - begin) / 8 > kMaxEnvoys) return false;
    unsigned matches = 0;
    for (auto it = begin; it < end; it += 8) {
        const auto entry = read_at<std::uintptr_t>(it);
        if (!pointer(entry)) return false;
        if (read_at<unsigned char>(entry + 0x18) != 2) continue;
        const auto mission = read_at<std::uintptr_t>(entry + 0x10);
        if (!pointer(mission) || read_at<std::uintptr_t>(mission) != module + kMissionVtable) return false;
        const auto task = read_at<std::uintptr_t>(mission + 0xa0);
        if (!task) continue;
        if (!pointer(task)) return false;
        if (read_at<std::uintptr_t>(task) != module + kSpyTaskVtable) continue;
        const auto task_target = read_at<std::uint64_t>(task + 0x20);
        if (((task_target >> 32) & 0xffff) != target.slot) continue;
        const auto envoy = read_at<std::int32_t>(entry + 0x44);
        if (envoy < 0 || read_at<unsigned char>(task + 0x28) != 0 || task_target != live.stamp.target_handle
            || read_at<std::uint64_t>(task + 0x18) != live.stamp.actor_handle
            || read_at<std::uint64_t>(mission + 0x80) != live.stamp.actor_handle
            || read_at<std::uint64_t>(mission + 0x88) != live.stamp.target_handle
            || read_at<std::uint32_t>(mission + 0xa8) != 0x3378
            || read_at<std::uintptr_t>(mission + 0x48) != entry
            || read_at<std::int32_t>(mission + 0x50) != envoy || read_at<std::int32_t>(task + 0x2c) != envoy) return false;
        binding = {envoy, entry, mission, task};
        ++matches;
    }
    return matches == 1 && spy_list(module, live, binding);
}
bool cancellation_binding(std::uintptr_t module, const Live& live, const Country& actor, const Country& target,
                          ActionId id, Binding& binding) {
    binding = {-1, 0, 0, 0};
    std::uintptr_t object = 0;
    if (id == ActionId::stop_building_spy_network) return spy_binding(module, live, target, binding);
    if (id == ActionId::revoke_guarantee)
        return paired_relation(module, live, actor, target, 0x1a0, 0x1ac, 0x1c817d8, object);
    if (id == ActionId::cancel_vassalization) {
        if (!paired_relation(module, live, actor, target, 0x128, 0x134, 0x1c81758, object)
            || read_at<std::uint64_t>(live.target_object + 0x18f0) != actor.handle
            || read_at<std::uint64_t>(live.actor_object + 0x18f0) == target.handle) return false;
        const auto registry = read_at<std::uintptr_t>(module + kSubjectRegistry);
        const auto definition = read_at<std::uintptr_t>(object + 0x40);
        if (!pointer(registry)) return false;
        return (definition == read_at<std::uintptr_t>(registry + 0x58) && definition_name(definition, "vassal"))
            || (definition == read_at<std::uintptr_t>(registry + 0x60) && definition_name(definition, "client_vassal"));
    }
    // Ordinary native validity handles marriage and improvement relations.
    // Improvement retains envoy=-1; its relation destructor recalls the mission.
    return true;
}
bool same_binding(const Binding& a, const Binding& b) {
    return a.envoy == b.envoy && a.entry == b.entry && a.mission == b.mission && a.task == b.task;
}
bool action_identity(std::uintptr_t module, std::uintptr_t object, const Action& action) {
    return pointer(object) && object != module + kSentinel && read_at<std::uintptr_t>(object) == module + action.vtable
        && read_at<std::uint32_t>(object + 8) == 0x165;
}
bool derived_fields(std::uintptr_t object, const Action& action, bool empty_required) {
    if (action.size != 0x68) return true;
    const auto length = read_at<std::uint64_t>(object + 0x50), capacity = read_at<std::uint64_t>(object + 0x58);
    if (read_at<unsigned char>(object + 0x60) != 0 || length > 128 || length > capacity) return false;
    if (empty_required) return length == 0 && capacity == 15 && read_at<unsigned char>(object + 0x40) == 0;
    const auto chars = capacity < 16 ? object + 0x40 : read_at<std::uintptr_t>(object + 0x40);
    return pointer(chars) && read_at<unsigned char>(chars + static_cast<std::uintptr_t>(length)) == 0;
}
bool factory_fields(std::uintptr_t object, const Action& action) {
    return read_at<std::uint64_t>(object + 0x10) == 0x2d2d2d && read_at<std::uint64_t>(object + 0x18) == 0x2d2d2d
        && read_at<std::uint64_t>(object + 0x20) == 0x2d2d2d && read_at<std::uint32_t>(object + 0x28) == 0x29c77f8
        && read_at<std::uint32_t>(object + 0x2c) == 0x29c77f8 && read_at<std::int32_t>(object + 0x30) == -1
        && read_at<std::uint32_t>(object + 0x34) == 0 && read_at<std::uint16_t>(object + 0x38) == 1
        && read_at<std::uint32_t>(object + 0x3c) == 0 && derived_fields(object, action, true);
}
void initialize(std::uintptr_t object, const Live& live) {
    write_owned(object, 0x10, live.stamp.actor_handle);
    write_owned(object, 0x18, live.stamp.actor_handle);
    write_owned(object, 0x20, live.stamp.target_handle);
    write_owned(object, 0x28, live.stamp.raw_date);
    write_owned(object, 0x2c, live.stamp.raw_date);
    write_owned(object, 0x30, static_cast<std::int32_t>(-1));
    write_owned(object, 0x34, static_cast<std::uint32_t>(0));
    write_owned(object, 0x39, static_cast<unsigned char>(0));
    write_owned(object, 0x3c, static_cast<std::uint32_t>(0));
    // Mode is set by the pinned native setter only after the full identities.
    // Marriage EngineString32/+0x60 are never overwritten by this core.
}
bool fields_match(std::uintptr_t object, const Action& action, const Live& live, bool positive, const Binding& binding) {
    return read_at<std::uint64_t>(object + 0x10) == live.stamp.actor_handle
        && read_at<std::uint64_t>(object + 0x18) == live.stamp.actor_handle
        && read_at<std::uint64_t>(object + 0x20) == live.stamp.target_handle
        && read_at<std::int32_t>(object + 0x28) == live.stamp.raw_date
        && read_at<std::int32_t>(object + 0x2c) == live.stamp.raw_date
        && read_at<std::int32_t>(object + 0x30) == binding.envoy
        && read_at<std::uint32_t>(object + 0x34) == 0
        && read_at<unsigned char>(object + 0x38) == static_cast<unsigned char>(positive ? 1 : 0)
        && read_at<unsigned char>(object + 0x39) == 0 && read_at<std::uint32_t>(object + 0x3c) == 0
        && derived_fields(object, action, false);
}
bool command_owned(std::uintptr_t module, std::uintptr_t command, std::uintptr_t clone,
                   const Action& action, const Live& live, bool positive, const Binding& binding) {
    return pointer(command) && command != module + kSentinel && read_at<std::uintptr_t>(command) == module + kCommandVtable
        && read_at<std::uint32_t>(command + 8) == 0x165 && read_at<std::uint32_t>(command + 0x44) == 0x2934
        && read_at<unsigned char>(command + 0x10) == 0 && read_at<std::uint64_t>(command + 0x18) == 0
        && read_at<std::uint64_t>(command + 0x28) == 0 && read_at<std::uint64_t>(command + 0x30) == 15
        && read_at<std::int32_t>(command + 0x38) == -1 && read_at<std::uint32_t>(command + 0x3c) == 0
        && read_at<std::uint16_t>(command + 0x40) == 0 && read_at<std::uint64_t>(command + 0x48) == 0xffff
        && clone != command && read_at<std::uintptr_t>(command + 0x50) == clone
        && action_identity(module, clone, action) && fields_match(clone, action, live, positive, binding);
}
bool live_context(std::uintptr_t module, const Live& live, Context& context) {
    context.server = read_at<std::uintptr_t>(live.game + 0x1e00);
    if (!pointer(context.server) || read_at<std::uintptr_t>(context.server) != module + kServerVtable) return false;
    context.holder = read_at<std::uintptr_t>(context.server + 0x330);
    if (!pointer(context.holder)) return false;
    context.context = read_at<std::uintptr_t>(context.holder + 0x370);
    if (!pointer(context.context)) return false;
    context.transport = read_at<std::uintptr_t>(context.context + 0x58);
    return pointer(context.transport) && read_at<std::uintptr_t>(context.transport) == module + kTransportVtable
        && (read_at<unsigned char>(context.context + 0x55) != 0 || read_at<unsigned char>(context.context + 0x80d) != 0)
        && read_at<std::uintptr_t>(live.game + 0x1e00) == context.server
        && read_at<std::uintptr_t>(context.server + 0x330) == context.holder
        && read_at<std::uintptr_t>(context.holder + 0x370) == context.context
        && read_at<std::uintptr_t>(context.context + 0x58) == context.transport;
}
bool call_guard(const Host& host, const Request& request, Mode mode, const Live& live, GuardPoint point) {
    if (GetCurrentThreadId() != host.expected_game_thread || InterlockedCompareExchange(&g_frozen, 0, 0)) return false;
    GuardInput input{point, mode, request, live.stamp};
    return host.guard(host.user, &input);
}
const char* yes(bool value) { return value ? "true" : "false"; }
bool audit(const Host& host, const Request& request, const Result& result, const char* event) {
    char line[2048]{};
    const int count = std::snprintf(line, sizeof(line),
        "{\"event\":\"%s\",\"action_id\":\"%s\",\"actor\":\"%.3s\",\"target\":\"%.3s\","
        "\"pid\":%u,\"thread_id\":%u,\"process_creation_filetime\":\"%016llx\",\"world\":\"0x%llx\","
        "\"actor_handle\":\"0x%016llx\",\"target_handle\":\"0x%016llx\",\"raw_date\":%d,"
        "\"status\":%u,\"reason\":%u,\"phase\":%u,\"preview_called\":%s,\"preview_allowed\":%s,"
        "\"gate_called\":%s,\"gate_allowed\":%s,\"envoy_id\":%d,\"submit_entered\":%s,\"submit_returned\":%s,"
        "\"context_submit_return\":%s,\"caller_container_consumed\":%s,\"ownership_uncertain\":%s,"
        "\"original_destroyed\":%s,\"command_destroyed_before_dispatch\":%s,\"exception\":%u,"
        "\"freeze_session\":%s,\"retry_allowed\":false,\"applied_verified\":false}",
        event, action_name(request.action), request.actor, request.target, result.stamp.pid, result.stamp.thread_id,
        static_cast<unsigned long long>(result.stamp.process_creation_filetime), static_cast<unsigned long long>(result.stamp.world_cookie),
        static_cast<unsigned long long>(result.stamp.actor_handle), static_cast<unsigned long long>(result.stamp.target_handle), result.stamp.raw_date,
        static_cast<unsigned>(result.status), static_cast<unsigned>(result.reason), static_cast<unsigned>(result.phase),
        yes(result.preview_called), yes(result.preview_allowed), yes(result.gate_called), yes(result.gate_allowed), result.resolved_envoy_id,
        yes(result.submit_entered), yes(result.submit_returned), result.submit_returned ? yes(result.context_submit_return) : "null",
        result.submit_returned ? yes(result.caller_container_consumed) : "null", yes(result.ownership_uncertain),
        yes(result.original_destroyed), yes(result.command_destroyed_before_dispatch), result.exception_code, yes(result.freeze_session));
    return count > 0 && static_cast<std::size_t>(count) < sizeof(line) && host.log(host.user, line, static_cast<std::size_t>(count));
}

// SEH covers callbacks and every native access/call. All locals are trivial;
// after a fault no destructor, secondary game call, or automatic retry runs.
void execute(const Request& request, Mode mode, const Host& host, Result& result) {
    const auto index = static_cast<unsigned>(request.action);
    const Action& action = kActions[index / 2];
    const bool positive = index % 2 == 0;
    const Country& actor = *country(request.actor);
    const Country& target = *country(request.target);
    const auto module = reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
    Live live{};
    Binding binding{-1, 0, 0, 0};
    Context context{};
    void* original = nullptr;
    void* command = nullptr;
    std::uintptr_t clone = 0;
    bool own_original = false, own_command = false, completed_legality = false, allocation_started = false;
    __try {
        do {
            result.phase = Phase::image_pin;
            if (!image_pin(module)) { result.reason = Reason::image_pin_failed; break; }
            result.phase = Phase::live_identity;
            if (!current(module, actor, target, live)) { result.reason = Reason::live_identity_failed; break; }
            result.stamp = live.stamp;
            if (mode == Mode::submit && live.stamp.player_handle != actor.handle) { result.reason = Reason::nonplayer_submit_unverified; break; }
            if (!call_guard(host, request, mode, live, GuardPoint::before_allocation)) { result.reason = Reason::guard_rejected; break; }
            if (!audit(host, request, result, "pair_engine_begin")) { result.reason = Reason::audit_failed; result.freeze_session = true; break; }
            if (!same_state(module, actor, target, live)) { result.reason = Reason::world_changed; break; }
            result.phase = Phase::cancellation_binding;
            if (!cancellation_binding(module, live, actor, target, request.action, binding)) { result.reason = Reason::cancellation_binding_failed; break; }
            result.resolved_envoy_id = binding.envoy;
            result.phase = Phase::factory;
            allocation_started = true;
            original = reinterpret_cast<Factory>(module + kFactory)(action.token, nullptr);
            const auto original_address = reinterpret_cast<std::uintptr_t>(original);
            if (!original || original_address == module + kSentinel) {
                // No returned pointer can be proven owned. This does not prove
                // the factory made no internal allocation; do not free/retry.
                result.reason = Reason::factory_unavailable; result.freeze_session = true;
                original = nullptr; break;
            }
            if (!action_identity(module, original_address, action) || !factory_fields(original_address, action)) {
                result.reason = Reason::action_contract_failed; result.ownership_uncertain = true; break;
            }
            own_original = true;
            result.phase = Phase::initialize;
            initialize(original_address, live);
            reinterpret_cast<Setter>(module + action.setter)(original, positive);
            Binding after_setter{};
            if (!cancellation_binding(module, live, actor, target, request.action, after_setter) || !same_binding(binding, after_setter)
                || !action_identity(module, original_address, action) || !fields_match(original_address, action, live, positive, binding)) {
                result.reason = Reason::action_contract_failed; result.ownership_uncertain = true; break;
            }
            result.initialized = true;
            result.phase = Phase::preview;
            result.preview_called = true;
            result.preview_allowed = reinterpret_cast<Preview>(module + kPreview)(original, nullptr, false);
            if (!action_identity(module, original_address, action) || !fields_match(original_address, action, live, positive, binding)) {
                result.reason = Reason::action_contract_failed; result.ownership_uncertain = true; break;
            }
            if (!same_state(module, actor, target, live)) { result.reason = Reason::world_changed; break; }
            if (!result.preview_allowed) { result.reason = Reason::preview_rejected; completed_legality = true; break; }
            result.phase = Phase::wrapper;
            void** wrapper_result = reinterpret_cast<Wrapper>(module + kWrapper)(original, &command);
            const auto command_address = reinterpret_cast<std::uintptr_t>(command);
            if (wrapper_result != &command || !pointer(command_address) || command_address == original_address) {
                result.reason = Reason::wrapper_contract_failed; result.ownership_uncertain = true; break;
            }
            clone = read_at<std::uintptr_t>(command_address + 0x50);
            if (clone == original_address || !command_owned(module, command_address, clone, action, live, positive, binding)
                || !derived_fields(clone, action, true) || !action_identity(module, original_address, action)
                || !fields_match(original_address, action, live, positive, binding)) {
                result.reason = Reason::wrapper_contract_failed; result.ownership_uncertain = true; break;
            }
            own_command = true;
            result.phase = Phase::command_gate;
            result.gate_called = true;
            result.gate_allowed = reinterpret_cast<Gate>(module + kGate)(command);
            if (!command_owned(module, command_address, clone, action, live, positive, binding)
                || !action_identity(module, original_address, action) || !fields_match(original_address, action, live, positive, binding)) {
                result.reason = Reason::ownership_uncertain; result.ownership_uncertain = true; break;
            }
            if (!same_state(module, actor, target, live)) { result.reason = Reason::world_changed; break; }
            completed_legality = true;
            if (!result.gate_allowed) { result.reason = Reason::command_rejected; break; }
            if (mode == Mode::legality_only) break;
            result.phase = Phase::original_destructor;
            reinterpret_cast<Destructor>(module + action.destructor)(original, 1);
            original = nullptr; own_original = false; result.original_destroyed = true;
            result.phase = Phase::context_pin;
            if (!live_context(module, live, context)) { result.reason = Reason::context_unavailable; break; }
            result.phase = Phase::pre_dispatch_audit;
            if (!audit(host, request, result, "pair_engine_dispatch_intent")) {
                result.reason = Reason::audit_failed; result.freeze_session = true; break;
            }
            result.phase = Phase::final_guard;
            if (!call_guard(host, request, mode, live, GuardPoint::before_dispatch)) { result.reason = Reason::guard_rejected; break; }
            Context final_context{};
            Binding final_binding{};
            if (!same_state(module, actor, target, live)
                || !cancellation_binding(module, live, actor, target, request.action, final_binding) || !same_binding(binding, final_binding)
                || !live_context(module, live, final_context)
                || final_context.server != context.server || final_context.holder != context.holder
                || final_context.context != context.context || final_context.transport != context.transport
                || !command_owned(module, command_address, clone, action, live, positive, binding)) {
                result.reason = Reason::world_changed; break;
            }
            if (!call_guard(host, request, mode, live, GuardPoint::before_dispatch)
                || !same_state(module, actor, target, live)) { result.reason = Reason::guard_rejected; break; }
            // Irreversible ownership boundary: never destroy/retry after this.
            result.phase = Phase::context_submit;
            result.submit_entered = true;
            own_command = false;
            result.context_submit_return = reinterpret_cast<Submit>(module + kContextSubmit)(reinterpret_cast<void*>(context.context), &command);
            result.submit_returned = true;
            result.caller_container_consumed = command == nullptr;
            result.ownership_uncertain = !result.context_submit_return || !result.caller_container_consumed;
            if (result.ownership_uncertain) result.reason = Reason::dispatch_not_acknowledged;
        } while (false);
        if (!result.submit_entered && !result.ownership_uncertain) {
            const Phase outcome_phase = result.phase;
            if (own_command || own_original) result.phase = Phase::pre_dispatch_cleanup;
            if (own_command) {
                if (!command_owned(module, reinterpret_cast<std::uintptr_t>(command), clone, action, live, positive, binding)) {
                    result.reason = Reason::ownership_uncertain; result.ownership_uncertain = true;
                } else {
                    // The command deleting destructor owns/destroys its clone.
                    // Never call the clone destructor separately.
                    reinterpret_cast<Destructor>(module + kCommandDestructor)(command, 1);
                    command = nullptr; clone = 0; own_command = false;
                    result.command_destroyed_before_dispatch = true;
                }
            }
            if (own_original && !result.ownership_uncertain) {
                if (!action_identity(module, reinterpret_cast<std::uintptr_t>(original), action)
                    || !derived_fields(reinterpret_cast<std::uintptr_t>(original), action, false)) {
                    result.reason = Reason::ownership_uncertain; result.ownership_uncertain = true;
                } else {
                    reinterpret_cast<Destructor>(module + action.destructor)(original, 1);
                    original = nullptr; own_original = false; result.original_destroyed = true;
                }
            }
            if (!result.ownership_uncertain) result.phase = outcome_phase;
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        result.exception_code = GetExceptionCode();
        result.reason = Reason::native_exception;
        // A fault inside factory/wrapper can allocate before publishing a
        // result pointer; null caller variables are not evidence of no owner.
        result.ownership_uncertain = allocation_started || own_original || own_command || result.submit_entered;
        result.freeze_session = true;
    }
    if (result.submit_entered) {
        result.status = result.submit_returned && result.context_submit_return && result.caller_container_consumed
            ? Status::dispatched : Status::dispatch_unknown;
    } else if (mode == Mode::legality_only && completed_legality && result.exception_code == 0 && !result.ownership_uncertain
               && !own_original && !own_command) {
        result.status = Status::legality_only;
    }
    result.freeze_session = result.freeze_session || result.ownership_uncertain || result.status == Status::dispatch_unknown;
}
} // namespace

const char* action_name(ActionId action) {
    const auto value = static_cast<unsigned>(action);
    return value < 10 ? kNames[value] : "invalid";
}
bool parse_action_id(const char* text, std::size_t length, ActionId* output) {
    if (text == nullptr || output == nullptr || length == 0 || length > 31) return false;
    for (unsigned i = 0; i < 10; ++i) {
        if (std::strlen(kNames[i]) == length && std::memcmp(text, kNames[i], length) == 0) {
            *output = static_cast<ActionId>(i);
            return true;
        }
    }
    return false;
}
Result invoke(const Request& request, Mode mode, const Host& host) {
    Result result{};
    result.status = Status::pre_dispatch_rejected;
    result.phase = Phase::entry;
    result.resolved_envoy_id = -1;
    if (host.struct_size != sizeof(Host) || host.abi_version != kAbiVersion || host.guard == nullptr || host.log == nullptr) {
        result.reason = Reason::bad_abi; return result;
    }
    if (static_cast<unsigned>(request.action) >= 10 || country(request.actor) == nullptr || country(request.target) == nullptr
        || std::memcmp(request.actor, request.target, 4) == 0 || (mode != Mode::submit && mode != Mode::legality_only)) {
        result.reason = Reason::invalid_request; return result;
    }
    if (!host.authorized) { result.reason = Reason::authorization_missing; return result; }
    if (!host.full_sha256_and_same_session_preflight_verified) { result.reason = Reason::preflight_missing; return result; }
    if (host.expected_game_thread == 0 || host.expected_game_thread != GetCurrentThreadId()) { result.reason = Reason::wrong_thread; return result; }
    if (InterlockedCompareExchange(&g_frozen, 0, 0)) { result.reason = Reason::session_frozen; result.freeze_session = true; return result; }
    if (InterlockedCompareExchange(&g_busy, 1, 0)) { result.reason = Reason::busy; return result; }
    execute(request, mode, host, result);
    if (result.freeze_session) InterlockedExchange(&g_frozen, 1);
    __try {
        const bool completion_persisted = audit(host, request, result, "pair_engine_complete");
        result.audit_complete = completion_persisted && result.reason != Reason::audit_failed && result.exception_code == 0;
        if (!completion_persisted) {
            if (result.reason == Reason::none) result.reason = Reason::audit_failed;
            result.freeze_session = true;
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        result.exception_code = GetExceptionCode();
        result.audit_complete = false;
        result.freeze_session = true;
        // A logging failure does not erase an already returned native dispatch
        // acknowledgement, and never triggers a second engine call or retry.
        if (result.reason == Reason::none) result.reason = Reason::audit_failed;
    }
    if (result.freeze_session) InterlockedExchange(&g_frozen, 1);
    InterlockedExchange(&g_busy, 0);
    return result;
}
} // namespace eu4_pair_1375
