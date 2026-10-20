// Standalone synthetic Win64 EXE. No Windows/process/game APIs or native calls.
#include "forward_layout.h"
#include <cstdio>
#include <cstring>
#include <limits>

using namespace entry_forward_model;
extern "C" {
void model_run();
extern unsigned char model_return_to_wrapper_call, model_return_to_wrapper_jump;
extern unsigned char model_return_to_server, model_return_to_relay;
extern unsigned char model_return_to_loop, model_return_to_main;
std::uint64_t model_outer_root = 0, model_map = 0, model_server = 0;
std::uint32_t model_mode = 0, model_clobber_count = 0;
std::uint64_t model_callback_entry_rsp = 0, model_after_rsp = 0;
std::uint64_t model_after_gprs[7]{}, model_before_nonvolatile[8]{}, model_after_nonvolatile[8]{};
alignas(16) unsigned char model_xmm_patterns[96]{}, model_after_xmm[96]{};
alignas(16) unsigned char model_before_nonvolatile_xmm[160]{}, model_after_nonvolatile_xmm[160]{};
}

namespace {
static_assert(sizeof(void*) == 8, "This is a Win64 ABI model only");
struct alignas(8) Fixture {
    unsigned char outer[0x88]{}, game[0x1e08]{}, server[0x338]{}, holder[0x368]{};
    unsigned char map[8]{}, pending[8]{}, previous[8]{};
    unsigned char vt_outer[8]{}, vt_secondary[8]{}, vt_game[8]{}, vt_server[0x28]{};
};
Fixture world;
OwnedSnapshot snapshot;
std::uint32_t fault = 0, root_reads = 0, pending_reads_second_pass = 0;
bool shadow_ok = false, descriptor_ok = false;
unsigned checks = 0, cases = 0;
std::uint64_t address(const void* pointer) noexcept {
    return static_cast<std::uint64_t>(reinterpret_cast<std::uintptr_t>(pointer));
}
std::uint64_t update_label() noexcept {
    return static_cast<std::uint64_t>(reinterpret_cast<std::uintptr_t>(&model_run));
}
void put(unsigned char* at, std::uint64_t value) noexcept { std::memcpy(at, &value, 8); }
void require(bool condition, const char* name) {
    ++checks;
    if (!condition) { std::fprintf(stderr, "FAIL: %s\n", name); throw name; }
}
bool span(std::uint64_t pointer, std::size_t size) noexcept {
    constexpr std::uint64_t upper = (1ull << 47)-0x10000;
    return size > 0 && pointer >= 0x10000 && pointer < upper && size <= upper-pointer;
}
bool object(std::uint64_t pointer, bool optional = false) noexcept {
    return (optional && pointer == 0) || (span(pointer, 8) && !(pointer & 7));
}
bool within(std::uint64_t pointer, std::size_t size, std::uint64_t start, std::size_t extent) noexcept {
    return pointer >= start && pointer-start <= extent && size <= extent-(pointer-start);
}
template<std::size_t N>
bool within_array(std::uint64_t pointer, std::size_t size, const unsigned char (&data)[N]) noexcept {
    return within(pointer, size, address(data), N);
}
std::array<std::uint64_t, 5> expected_returns() noexcept {
    return {address(model_mode ? &model_return_to_wrapper_jump : &model_return_to_wrapper_call),
        address(&model_return_to_server), address(&model_return_to_relay),
        address(&model_return_to_loop), address(&model_return_to_main)};
}
bool valid_entry(const OwnedEntry& entry, std::uint64_t descriptor_address,
                 std::uint64_t callback_entry) noexcept {
    return span(entry.entry_rsp, 0x4b0) && (entry.entry_rsp & 15) == 8 &&
        entry.frame_rsp == entry.entry_rsp-0xe8 && (entry.frame_rsp & 15) == 0 &&
        descriptor_address == entry.frame_rsp+0xc0 && callback_entry == entry.frame_rsp-8 &&
        entry.original_rcx == model_map && entry.original_r8 == model_server;
}
class Reader {
public:
    explicit Reader(const OwnedEntry& entry, OwnedSnapshot& output) noexcept : entry_(entry), output_(output) {}
    bool read(std::uint64_t pointer, std::size_t size, std::uint64_t& value) noexcept {
        if (!span(pointer, size) || size > 8) { output_.reason = Reason::read_refused; return false; }
        const auto max_reads = fault == 3 ? 1u : 64u;
        if (output_.attempted_reads >= max_reads || size > 1024-output_.requested_bytes) {
            output_.reason = Reason::budget; return false;
        }
        ++output_.attempted_reads;
        output_.requested_bytes += size;
        if (fault == 1 && output_.attempted_reads == 1) { output_.reason = Reason::short_read; return false; }
        if (pointer == address(&model_outer_root)) {
            ++root_reads;
            if (root_reads == 2 && fault == 4) put(world.outer+0x70, 0);
            if (root_reads == 2 && fault == 5) world.outer[0x48] ^= 1;
        }
        if (root_reads >= 2 && pointer == address(world.pending)) ++pending_reads_second_pass;
        bool allowed = within(pointer, size, entry_.entry_rsp, 0x4b0) ||
            within(pointer, size, address(&model_outer_root), 8);
        // There is no game root in this model: this qword belongs to fixture storage.
        allowed = allowed || within(pointer, size, address(&game_root), 8);
        allowed = allowed || within_array(pointer, size, world.outer) || within_array(pointer, size, world.game) ||
            within_array(pointer, size, world.server) || within_array(pointer, size, world.holder) ||
            within_array(pointer, size, world.map) || within_array(pointer, size, world.pending) ||
            within_array(pointer, size, world.previous) || within_array(pointer, size, world.vt_outer) ||
            within_array(pointer, size, world.vt_secondary) || within_array(pointer, size, world.vt_game) ||
            within_array(pointer, size, world.vt_server);
        if (!allowed) { output_.reason = Reason::read_refused; return false; }
        value = 0;
        std::memcpy(&value, reinterpret_cast<const void*>(static_cast<std::uintptr_t>(pointer)), size);
        output_.exact_bytes += size;
        // Corrupt the returned number, never the CPU's actual return slot.
        if (fault == 2 && output_.attempted_reads == 1) value = 0;
        return true;
    }
    static std::uint64_t game_root;
private:
    const OwnedEntry& entry_;
    OwnedSnapshot& output_;
};
std::uint64_t Reader::game_root = 0;
std::uint64_t value(const OwnedProjection& projection, Field field) noexcept {
    return projection.values[static_cast<std::size_t>(field)];
}
bool project(Reader& reader, const OwnedEntry& entry, OwnedProjection& out) noexcept {
    const auto take = [&](Field field, std::uint64_t at, std::size_t size = 8) {
        return reader.read(at, size, out.values[static_cast<std::size_t>(field)]);
    };
    constexpr std::array<std::uint64_t, 5> offsets{0, 0x40, 0x370, 0x3f0, 0x440};
    const auto expected = expected_returns();
    for (std::size_t index = 0; index < 5; ++index) {
        if (!reader.read(entry.entry_rsp+offsets[index], 8, out.values[index])) return false;
        if (out.values[index] != expected[index]) { snapshot.reason = Reason::return_chain; return false; }
    }
    if (!take(Field::stack_holder, entry.entry_rsp+0x4a8) ||
        !take(Field::outer, address(&model_outer_root)) || !take(Field::game, address(&Reader::game_root))) return false;
    const auto outer = value(out, Field::outer), game = value(out, Field::game);
    if (!object(outer) || !object(game) || value(out, Field::stack_holder) != outer) {
        snapshot.reason = Reason::identity; return false;
    }
    if (!take(Field::outer_vtable, outer) || !take(Field::outer_secondary_vtable, outer+0x10)) return false;
    if (value(out, Field::outer_vtable) != address(world.vt_outer) ||
        value(out, Field::outer_secondary_vtable) != address(world.vt_secondary)) { snapshot.reason = Reason::type; return false; }
    if (!take(Field::current_app, outer+0x40) || !take(Field::pending_app, outer+0x70) ||
        !take(Field::previous_app, outer+0x78) || !take(Field::transition_byte, outer+0x48, 1) ||
        !take(Field::retain_previous_byte, outer+0x80, 1) || !take(Field::game_vtable, game) ||
        !take(Field::game_server, game+0x1e00)) return false;
    const auto current = value(out, Field::current_app), server = value(out, Field::game_server);
    const auto pending = value(out, Field::pending_app), previous = value(out, Field::previous_app);
    if (!object(current) || !object(server) || !object(pending, true) || !object(previous, true) ||
        current != server || server != entry.original_r8) { snapshot.reason = Reason::identity; return false; }
    if (value(out, Field::game_vtable) != address(world.vt_game)) { snapshot.reason = Reason::type; return false; }
    if (!take(Field::current_vtable, current)) return false;
    if (value(out, Field::current_vtable) != address(world.vt_server)) { snapshot.reason = Reason::type; return false; }
    if (!take(Field::current_update, value(out, Field::current_vtable)+0x20)) return false;
    if (value(out, Field::current_update) != update_label()) { snapshot.reason = Reason::type; return false; }
    if (!take(Field::server_holder, server+0x330)) return false;
    const auto holder = value(out, Field::server_holder);
    if (!object(holder)) { snapshot.reason = Reason::identity; return false; }
    if (!take(Field::map_object, holder+0x360)) return false;
    if (value(out, Field::map_object) != entry.original_rcx) { snapshot.reason = Reason::identity; return false; }
    if (pending && !take(Field::pending_vtable, pending)) return false;
    if (previous && !take(Field::previous_vtable, previous)) return false;
    return true;
}
bool evaluate_owned(const OwnedSnapshot& owned) noexcept {
    // No Reader, descriptor or pointer dereference. Status is synthetic only.
    return owned.complete_passes == 2 && owned.passes[0].values == owned.passes[1].values &&
        owned.status == Status::model_structural_match && owned.reason == Reason::none;
}
void initialize(bool optional, std::uint32_t mode) noexcept {
    world = Fixture{};
    snapshot = OwnedSnapshot{};
    model_mode = mode;
    model_clobber_count = fault = root_reads = pending_reads_second_pass = 0;
    shadow_ok = descriptor_ok = false;
    model_outer_root = address(world.outer);
    Reader::game_root = address(world.game);
    model_map = address(world.map);
    model_server = address(world.server);
    put(world.outer, address(world.vt_outer));
    put(world.outer+0x10, address(world.vt_secondary));
    put(world.outer+0x40, model_server);
    put(world.outer+0x70, optional ? address(world.pending) : 0);
    put(world.outer+0x78, optional ? address(world.previous) : 0);
    world.outer[0x48] = 1; world.outer[0x80] = 1;
    put(world.game, address(world.vt_game));
    put(world.game+0x1e00, model_server);
    put(world.server, address(world.vt_server));
    put(world.vt_server+0x20, update_label());
    put(world.server+0x330, address(world.holder));
    put(world.holder+0x360, model_map);
    put(world.pending, address(world.vt_outer));
    put(world.previous, address(world.vt_outer));
    for (std::size_t index = 0; index < sizeof(model_xmm_patterns); ++index)
        model_xmm_patterns[index] = static_cast<unsigned char>((index*13+7)&255);
}
void check_abi() {
    require(descriptor_ok && shadow_ok, "entry Q/RCX/R8/S and shadow disjoint");
    require(model_callback_entry_rsp == snapshot.entry.entry_rsp-0xf0, "actual callback T=Q-f0");
    require(model_after_rsp == snapshot.entry.entry_rsp+8, "RET restored actual wrapper stack");
    const std::array<std::uint64_t, 7> expected{0x1111111111111111, model_map,
        0x2222222222222222, model_server, 0x4444444444444444, 0x5555555555555555, 0x6666666666666666};
    require(std::memcmp(expected.data(), model_after_gprs, sizeof(model_after_gprs)) == 0, "volatile GPR restored");
    require(std::memcmp(model_xmm_patterns, model_after_xmm, 96) == 0, "XMM0-5 low128 restored");
    require(std::memcmp(model_before_nonvolatile, model_after_nonvolatile, 64) == 0, "nonvolatile GPR ABI preserved");
    require(std::memcmp(model_before_nonvolatile_xmm, model_after_nonvolatile_xmm, 160) == 0, "XMM6-15 low128 ABI preserved");
    require(model_clobber_count == 1, "callback explicitly clobbered volatiles once");
}
}  // namespace

extern "C" void model_capture_impl(const EntryBorrow* borrow) noexcept {
    // Called synchronously only by this EXE's model_capture_entry assembly.
    // The borrowed descriptor/reader never escapes this function.
    const OwnedEntry entry{borrow->entry_rsp, borrow->original_rcx, borrow->original_r8, borrow->frame_rsp};
    snapshot.entry = entry;
    descriptor_ok = valid_entry(entry, address(borrow), model_callback_entry_rsp);
    if (!descriptor_ok) { snapshot.reason = Reason::descriptor_mismatch; return; }
    shadow_ok = true;
    for (std::uint64_t index = 0; index < 4; ++index) {
        std::uint64_t word = 0;
        std::memcpy(&word, reinterpret_cast<const void*>(static_cast<std::uintptr_t>(entry.frame_rsp+index*8)), 8);
        shadow_ok = shadow_ok && word == 0xa1a1a1a1a1a1a1a1;
    }
    if (!shadow_ok) { snapshot.reason = Reason::descriptor_mismatch; return; }
    Reader reader(entry, snapshot);
    for (std::size_t pass = 0; pass < 2; ++pass) {
        if (!project(reader, entry, snapshot.passes[pass])) return;
        ++snapshot.complete_passes;
    }
    if (snapshot.passes[0].values != snapshot.passes[1].values) { snapshot.reason = Reason::changed; return; }
    snapshot.status = Status::model_structural_match;
}

int main() {
    try {
        for (std::uint32_t mode = 0; mode < 2; ++mode) for (bool optional : {false, true}) {
            ++cases; initialize(optional, mode); model_run(); check_abi();
            require(evaluate_owned(snapshot), "two actual nested-frame projections");
            require(snapshot.attempted_reads == (optional ? 46u : 42u), "bounded selected reads");
            require(snapshot.requested_bytes == (optional ? 340u : 308u), "selected byte budget");
            require(snapshot.exact_bytes == snapshot.requested_bytes, "exact successful bytes");
            require(value(snapshot.passes[0], Field::stack_holder) == model_outer_root, "real main RSP+60 holder");
            const auto owned = snapshot;
            world = Fixture{};
            require(evaluate_owned(owned), "after return/fixture clear only owned values evaluated");
            auto bad = owned.entry;
            bad.entry_rsp += 8;
            require(!valid_entry(bad, bad.frame_rsp+0xc0, model_callback_entry_rsp), "malformed owned Q rejected without dereference");
        }
        for (std::uint32_t kind = 1; kind <= 5; ++kind) {
            ++cases; initialize(true, kind & 1); fault = kind; model_run(); check_abi();
            require(snapshot.status == Status::unknown, "invalid reader/unstable graph remains unknown");
            const auto expected = kind == 1 ? Reason::short_read : kind == 2 ? Reason::return_chain :
                kind == 3 ? Reason::budget : Reason::changed;
            require(snapshot.reason == expected, "precise reader failure reason");
            if (kind == 4) require(pending_reads_second_pass == 0, "second pass never follows removed pending");
        }
        for (unsigned kind = 0; kind < 5; ++kind) {
            ++cases; initialize(true, kind & 1);
            if (kind == 0) put(world.outer, address(world.vt_game));
            if (kind == 1) put(world.outer+0x40, address(world.pending));
            if (kind == 2) put(world.holder+0x360, address(world.pending));
            if (kind == 3) put(world.outer+0x70, std::numeric_limits<std::uint64_t>::max());
            if (kind == 4) put(world.server+0x330, address(world.map)+0x100000);
            model_run(); check_abi();
            require(snapshot.status == Status::unknown, "corrupt typed/pointer graph refused");
        }
        require(!kNativeEntryAuthenticated && !kNativeReady && !kLifetimeLease && !kAtomicSnapshot &&
            !kExceptionUnwindVerified && !kAvxXstatePreserved && !kGameInstallationProvenance, "all authority false");
        std::printf("{\"passed\":true,\"cases\":%u,\"checks\":%u,\"call_and_jump_models\":true,"
            "\"real_nested_return_slots\":true,\"native_ready\":false,\"native_entry_authenticated\":false,"
            "\"header_lifetime_lease\":false,\"atomic_snapshot\":false,\"game_accessed\":false,"
            "\"selected_reads_optional\":46,\"selected_bytes_optional\":340,"
            "\"selected_reads_null\":42,\"selected_bytes_null\":308,\"descriptor_copy_bytes\":32,"
            "\"shadow_probe_bytes\":32,\"game_native_calls\":0}\n", cases, checks);
        return 0;
    } catch (const char*) { return 1; }
}
