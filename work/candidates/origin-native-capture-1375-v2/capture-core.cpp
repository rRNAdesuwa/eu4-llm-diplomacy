#include "capture-core.h"
#include <limits>

namespace eu4_origin_capture_1375 {
namespace {
bool invalidation_site(Site site) noexcept {
    return site == Site::context_install || site == Site::holder_server_install
        || (site >= Site::application_cleanup && site < Site::count);
}
bool origin_scope(Site site) noexcept { return site >= Site::play && site <= Site::opaque_dispatch; }
bool pointer(std::uint64_t value) noexcept { return value >= 0x10000 && value < 0x0000800000000000ull; }
bool payload_valid(const Payload& data) noexcept {
    constexpr auto count = static_cast<unsigned>(Field::count);
    if ((data.present >> count) != 0) return false;
    for (std::size_t i = 0; i < data.values.size(); ++i)
        if ((i >= count || (data.present & (1ull << i)) == 0) && data.values[i] != 0) return false;
    return true;
}
}
void Epoch::lose(Fault fault, std::uint32_t thread) noexcept {
    // Terminal bit first: logging failure cannot undo an invalidation.
    word_.fetch_or(kTerminal | kRevoked, std::memory_order_acq_rel);
    std::uint64_t expected = 0;
    const auto packed = (static_cast<std::uint64_t>(thread) << 32) | static_cast<std::uint32_t>(fault);
    first_fault_.compare_exchange_strong(expected, packed, std::memory_order_release, std::memory_order_relaxed);
}
bool Epoch::revoke(std::uint32_t thread) noexcept {
    auto previous = word_.load(std::memory_order_acquire);
    if ((previous & kTerminal) != 0) return false;
    if (previous >= kTerminal - 2) { lose(Fault::epoch_exhausted, thread); return false; }
    const auto next = (previous + 2) | kRevoked;
    if (!word_.compare_exchange_strong(previous, next, std::memory_order_acq_rel, std::memory_order_acquire)) {
        lose(Fault::epoch_contended, thread); return false;
    }
    return true;
}
Status Epoch::status() const noexcept {
    const auto state = word_.load(std::memory_order_acquire);
    const auto fault = first_fault_.load(std::memory_order_acquire);
    // A concurrent loss may publish its fault after our earlier word load.
    // Never return nonterminal beside a visible terminal-fault publication.
    return {state, fault, (state & kTerminal) != 0 || fault != 0};
}
Ring::Reservation Ring::reserve(std::uint32_t thread) noexcept {
    if (epoch_.status().terminal) return {};
    auto ticket = head_.load(std::memory_order_acquire);
    const auto consumed = tail_.load(std::memory_order_acquire);
    if (ticket < consumed || ticket == std::numeric_limits<std::uint64_t>::max()) {
        epoch_.lose(Fault::ticket_exhausted, thread); return {};
    }
    if (ticket - consumed >= kCapacity) { epoch_.lose(Fault::ring_full, thread); return {}; }
    if (!head_.compare_exchange_strong(ticket, ticket + 1, std::memory_order_acq_rel, std::memory_order_acquire)) {
        epoch_.lose(Fault::reservation_contended, thread); return {};
    }
    return Reservation(ticket);
}
bool Ring::publish(Reservation&& reservation, const Record& record) noexcept {
    const auto ticket = reservation.ticket_;
    reservation.ticket_ = 0;
    if (ticket == 0) return false;
    // Only the unique producer holding this ticket may call publish ONCE.
    // No API recovery is possible if that producer abandons its reservation.
    if (epoch_.status().terminal) return false;
    const auto consumed = tail_.load(std::memory_order_acquire);
    const auto reserved = head_.load(std::memory_order_acquire);
    auto& slot = slots_[ticket % kCapacity];
    if (ticket < consumed || ticket >= reserved
        || ticket - consumed >= kCapacity || slot.ready.load(std::memory_order_acquire) != 0) {
        epoch_.lose(Fault::reservation_invalid, record.header.thread); return false;
    }
    slot.record = record;
    slot.record.header.ticket = ticket;
    slot.ready.store(ticket, std::memory_order_release);
    return !epoch_.status().terminal;
}
bool Ring::push(const Record& record) noexcept {
    return publish(reserve(record.header.thread), record);
}
void Ring::abandon(Reservation&& reservation, std::uint32_t thread) noexcept {
    const auto ticket = reservation.ticket_;
    reservation.ticket_ = 0;
    if (ticket != 0) epoch_.lose(Fault::producer_abandoned, thread);
}
Poll Ring::pop(std::uint64_t now_ms, Record& record) noexcept {
    if (epoch_.status().terminal) return Poll::terminal;
    if (now_ms < last_poll_) { epoch_.lose(Fault::clock_regressed, 0); return Poll::terminal; }
    last_poll_ = now_ms;
    const auto ticket = tail_.load(std::memory_order_relaxed);
    if (ticket == head_.load(std::memory_order_acquire)) return Poll::empty;
    auto& slot = slots_[ticket % kCapacity];
    if (slot.ready.load(std::memory_order_acquire) != ticket) {
        if (pending_ticket_ != ticket) { pending_ticket_ = ticket; pending_since_ = now_ms; }
        else if (now_ms - pending_since_ >= kGapTimeoutMs) {
            epoch_.lose(Fault::publication_gap, 0); return Poll::terminal;
        }
        return Poll::pending; // NEVER inspect, copy or skip a later ready slot.
    }
    record = slot.record;
    slot.ready.store(0, std::memory_order_relaxed);
    tail_.store(ticket + 1, std::memory_order_release);
    pending_ticket_ = 0;
    return epoch_.status().terminal ? Poll::terminal : Poll::ready;
}
Capture::Capture(std::uint32_t owner_thread) noexcept : ring_(epoch_), owner_thread_(owner_thread) {
    if (owner_thread == 0) epoch_.lose(Fault::bad_owner, 0);
}
bool Capture::begin_owner(std::uint32_t thread, std::uint64_t now_ms) noexcept {
    if (epoch_.status().terminal) return false;
    if (thread != owner_thread_) { epoch_.lose(Fault::wrong_thread, thread); return false; }
    if (recorder_busy_.test_and_set(std::memory_order_acquire)) {
        epoch_.lose(Fault::recorder_reentered, thread); return false;
    }
    if (now_ms < last_owner_ms_) {
        epoch_.lose(Fault::clock_regressed, thread); end_owner(); return false;
    }
    last_owner_ms_ = now_ms;
    return true;
}
bool Capture::owner_record(Kind kind, Site site, std::uint32_t thread, std::uint64_t now_ms,
                           ReturnToken token, const Payload& data) noexcept {
    if (!payload_valid(data)) { epoch_.lose(Fault::bad_record, thread); return false; }
    Record record{};
    record.header = {0, epoch_.status().epoch_word, now_ms, token.span, token.parent,
                     token.entry_rsp, token.return_va, thread, kind, site};
    record.payload = data;
    return ring_.push(record);
}
bool Capture::bootstrap(std::uint32_t thread, std::uint64_t now_ms, const Payload& data) noexcept {
    if (!begin_owner(thread, now_ms)) return false;
    bool result = false;
    if (bootstrapped_ || depth_ != 0) epoch_.lose(Fault::bad_record, thread);
    else { result = owner_record(Kind::bootstrap, Site::none, thread, now_ms, {}, data); bootstrapped_ = result; }
    end_owner(); return result;
}
ReturnToken Capture::enter(Site site, std::uint32_t thread, std::uint64_t now_ms,
                            std::uint64_t entry_rsp, std::uint64_t return_va,
                            const Payload& data) noexcept {
    ReturnToken token{};
    if (!begin_owner(thread, now_ms)) return token;
    if (!bootstrapped_ || !origin_scope(site) || !pointer(entry_rsp) || !pointer(return_va))
        epoch_.lose(Fault::bad_record, thread);
    else if (depth_ == kMaxDepth) epoch_.lose(Fault::stack_overflow, thread);
    else if (next_span_ == std::numeric_limits<std::uint64_t>::max()) epoch_.lose(Fault::ticket_exhausted, thread);
    else {
        token = {next_span_++, depth_ == 0 ? 0 : stack_[depth_ - 1].span, entry_rsp, return_va, site};
        if (site == Site::play && !epoch_.revoke(thread)) token = {};
        if (token.span != 0 && owner_record(Kind::enter, site, thread, now_ms, token, data)) stack_[depth_++] = token;
        else token = {};
    }
    end_owner(); return token;
}
bool Capture::leave(ReturnToken token, std::uint32_t thread, std::uint64_t now_ms,
                     const Payload& data) noexcept {
    if (!begin_owner(thread, now_ms)) return false;
    bool result = false;
    if (depth_ == 0 || token.span == 0) epoch_.lose(Fault::return_mismatch, thread);
    else {
        const auto& top = stack_[depth_ - 1];
        if (token.span != top.span || token.parent != top.parent || token.site != top.site
            || token.entry_rsp != top.entry_rsp || token.return_va != top.return_va)
            epoch_.lose(Fault::return_mismatch, thread);
        else { result = owner_record(Kind::leave, token.site, thread, now_ms, token, data); if (result) --depth_; }
    }
    end_owner(); return result;
}
bool Capture::frame(std::uint32_t thread, std::uint64_t now_ms, const Payload& data) noexcept {
    if (!begin_owner(thread, now_ms)) return false;
    bool result = false;
    if (!bootstrapped_ || depth_ != 0) epoch_.lose(Fault::bad_record, thread);
    else result = owner_record(Kind::frame, Site::none, thread, now_ms, {}, data);
    end_owner(); return result;
}
bool Capture::invalidate(Site site, std::uint32_t thread, std::uint64_t now_ms,
                          std::uint64_t preserved_entry_rcx, bool binding_verified) noexcept {
    if (!epoch_.revoke(thread)) return false;
    if (!invalidation_site(site) || thread == 0) { epoch_.lose(Fault::bad_record, thread); return false; }
    Record record{};
    record.header = {0, epoch_.status().epoch_word, now_ms, 0, 0, 0, 0, thread, Kind::invalidation, site};
    record.payload.set(Field::object, preserved_entry_rcx);
    record.payload.set(Field::bound_identity_match, binding_verified ? 1 : 0);
    return ring_.push(record);
}
void Capture::abnormal_return(std::uint32_t thread) noexcept { epoch_.lose(Fault::unexpected_unwind, thread); }
void Capture::stop(std::uint32_t thread) noexcept {
    // Even a clean stop disables further capture; no restart in this storage.
    epoch_.lose(Fault::incomplete_stop, thread);
}
} // namespace eu4_origin_capture_1375
