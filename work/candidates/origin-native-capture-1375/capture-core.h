#pragma once
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <type_traits>

// Offline-review source candidate. No exports, hooks, process reads, native
// calls, allocation, locks, file I/O, origin authorization or engine mutex.
// Storage must outlive every producer and consumer; detach/unload is unsupported.
namespace eu4_origin_capture_1375 {
constexpr std::size_t kCapacity = 256, kMaxDepth = 32, kPayloadValues = 40;
constexpr std::uint64_t kGapTimeoutMs = 50;
constexpr std::uint64_t kRevoked = 1, kTerminal = 1ull << 63;
enum class Site : std::uint16_t {
    none, play, fallback, context_ctor, context_install, frontend_update,
    server_ctor, config_copy, holder_server_install, opaque_dispatch,
    application_cleanup, reset_game, load_game, load_parser, game_reinitialize,
    game_destructor, base_game_clear, logical_clear, game_construct,
    database_construct, country_block_build, database_destructor, country_clear,
    index_reallocate, index_clear, context_reset, context_initialize,
    context_transition, context_list_clear, context_destructor,
    context_destructor_body, transport2_close, transport0_close,
    transport1_close, server_destructor, server_destructor_body, count
};
enum class Kind : std::uint16_t { bootstrap, enter, leave, invalidation, frame };
// Values mirror the final offline observer contract. Config/profile arrays are
// flattened; pointer values are observations, never addresses to dereference.
enum class Field : std::uint8_t {
    callback, frontend, holder, game, frontend_vtable, mode, config0, config1,
    context_type, object, context, transport, vtable, flag54, flag55,
    transport_vtable, transport_backlink, input_consumed, holder_context,
    start_pending, config_argument5, holder_argument4, destination, source,
    server, holder_server, database, block, index, player_handle,
    same_generation, double_snapshot_equal, players_complete, only_local_ids,
    pending_transition, bound_identity_match, exact_build_pinned, count
};
struct Payload {
    std::uint64_t present = 0;
    std::array<std::uint64_t, kPayloadValues> values{};
    void set(Field field, std::uint64_t value) noexcept {
        const auto index = static_cast<std::size_t>(field);
        if (index < static_cast<std::size_t>(Field::count)) {
            present |= 1ull << index; values[index] = value;
        }
    }
};
struct Header {
    std::uint64_t ticket = 0, epoch_word = 0, uptime_ms = 0, span = 0, parent = 0;
    std::uint64_t entry_rsp = 0, return_va = 0;
    std::uint32_t thread = 0;
    Kind kind = Kind::bootstrap;
    Site site = Site::none;
};
struct Record { Header header{}; Payload payload{}; };
static_assert(sizeof(Header) == 64 && sizeof(Payload) == 328 && sizeof(Record) == 392);
static_assert(std::is_trivially_copyable_v<Record>);
static_assert(static_cast<unsigned>(Field::count) <= kPayloadValues);
static_assert(std::atomic<std::uint64_t>::is_always_lock_free);
static_assert(std::atomic<std::uint32_t>::is_always_lock_free);

enum class Fault : std::uint32_t {
    none, bad_owner, bad_record, wrong_thread, recorder_reentered, stack_overflow,
    return_mismatch, clock_regressed, ring_full, reservation_contended,
    ticket_exhausted, reservation_invalid, publication_gap, epoch_contended,
    epoch_exhausted, producer_abandoned, unexpected_unwind, incomplete_stop
};
struct Status {
    std::uint64_t epoch_word;
    // high32=first-fault thread, low32=Fault. One atomic publication, no partial
    // ancillary data and no dependency on an available ring slot.
    std::uint64_t first_fault;
    bool terminal;
    bool production_ready = false, engine_lifetime_synchronized = false;
};
class Epoch {
public:
    bool revoke(std::uint32_t thread) noexcept;
    void lose(Fault fault, std::uint32_t thread) noexcept;
    Status status() const noexcept;
private:
    // Permanently revoked in this capture-only candidate. No clear/reset API.
    std::atomic<std::uint64_t> word_{kRevoked}, first_fault_{0};
};
enum class Poll { empty, ready, pending, terminal };

// Reservation exists for fixed producer adapters and the synthetic harness.
// It is NOT an external API or permission to write native memory.
class Ring {
public:
    explicit Ring(Epoch& epoch) noexcept : epoch_(epoch) {}
    class Reservation {
    public:
        Reservation() noexcept = default;
        Reservation(const Reservation&) = delete;
        Reservation& operator=(const Reservation&) = delete;
        Reservation(Reservation&& other) noexcept : ticket_(other.ticket_) { other.ticket_ = 0; }
        Reservation& operator=(Reservation&&) = delete;
        std::uint64_t ticket() const noexcept { return ticket_; }
    private:
        friend class Ring;
        explicit Reservation(std::uint64_t ticket) noexcept : ticket_(ticket) {}
        std::uint64_t ticket_ = 0;
    };
    Reservation reserve(std::uint32_t thread) noexcept;
    bool publish(Reservation&& reservation, const Record& record) noexcept;
    bool push(const Record& record) noexcept;
    Poll pop(std::uint64_t now_ms, Record& record) noexcept; // one consumer only
    void abandon(Reservation&& reservation, std::uint32_t thread) noexcept;
private:
    struct alignas(64) Slot {
        std::atomic<std::uint64_t> ready{0};
        Record record{};
    };
    Epoch& epoch_;
    std::array<Slot, kCapacity> slots_{};
    alignas(64) std::atomic<std::uint64_t> head_{1};
    alignas(64) std::atomic<std::uint64_t> tail_{1};
    std::uint64_t pending_ticket_ = 0, pending_since_ = 0, last_poll_ = 0;
};
struct ReturnToken {
    std::uint64_t span = 0, parent = 0, entry_rsp = 0, return_va = 0;
    Site site = Site::none;
};
class Capture {
public:
    // Initialize in static/private storage before hooks could become reachable.
    // Caller thread/clock/register provenance is a future adapter obligation.
    explicit Capture(std::uint32_t owner_thread) noexcept;
    bool bootstrap(std::uint32_t thread, std::uint64_t now_ms, const Payload& data) noexcept;
    ReturnToken enter(Site site, std::uint32_t thread, std::uint64_t now_ms,
                      std::uint64_t entry_rsp, std::uint64_t return_va,
                      const Payload& data) noexcept;
    bool leave(ReturnToken token, std::uint32_t thread, std::uint64_t now_ms,
               const Payload& data) noexcept;
    bool frame(std::uint32_t thread, std::uint64_t now_ms, const Payload& data) noexcept;
    // This always revokes FIRST, even with unknown binding, a full ring or a
    // foreign thread. Binding classification never suppresses local revocation.
    // Unclassified invalidations cannot be exported as confirmed scoped events.
    bool invalidate(Site site, std::uint32_t thread, std::uint64_t now_ms,
                    std::uint64_t preserved_entry_rcx, bool binding_verified) noexcept;
    void abnormal_return(std::uint32_t thread) noexcept;
    void stop(std::uint32_t thread) noexcept;
    Poll drain(std::uint64_t now_ms, Record& record) noexcept { return ring_.pop(now_ms, record); }
    Status status() const noexcept { return epoch_.status(); }
private:
    bool begin_owner(std::uint32_t thread, std::uint64_t now_ms) noexcept;
    bool owner_record(Kind kind, Site site, std::uint32_t thread, std::uint64_t now_ms,
                      ReturnToken token, const Payload& data) noexcept;
    void end_owner() noexcept { recorder_busy_.clear(std::memory_order_release); }
    Epoch epoch_{};
    Ring ring_;
    const std::uint32_t owner_thread_;
    std::atomic_flag recorder_busy_ = ATOMIC_FLAG_INIT;
    std::array<ReturnToken, kMaxDepth> stack_{}; // owner only; never read by revoker
    std::size_t depth_ = 0;
    std::uint64_t next_span_ = 1, last_owner_ms_ = 0;
    bool bootstrapped_ = false;
};
static_assert(sizeof(Capture) <= 128 * 1024);
} // namespace eu4_origin_capture_1375
