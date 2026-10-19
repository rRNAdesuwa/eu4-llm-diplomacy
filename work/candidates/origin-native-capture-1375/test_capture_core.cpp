// Synthetic source only in this review. Not compiled or run; no game dependency.
#include "capture-core.h"
#include <cstdio>
#include <utility>
using namespace eu4_origin_capture_1375;
namespace {
unsigned checks = 0, failures = 0;
#define CHECK(expr) do { ++checks; if (!(expr)) { ++failures; std::printf("FAIL line %u: %s\n", static_cast<unsigned>(__LINE__), #expr); } } while (false)
Record record(unsigned value = 0) {
    Record r{}; r.header.thread = 7; r.payload.set(Field::object, value); return r;
}
Fault reason(Status status) { return static_cast<Fault>(static_cast<std::uint32_t>(status.first_fault)); }
void fifo_wrap() {
    Epoch epoch; Ring ring(epoch); Record out{};
    for (unsigned i = 0; i < kCapacity * 3; ++i) {
        CHECK(ring.push(record(i)));
        CHECK(ring.pop(i, out) == Poll::ready);
        CHECK(out.header.ticket == static_cast<std::uint64_t>(i) + 1);
        CHECK(out.payload.values[static_cast<unsigned>(Field::object)] == i);
    }
    CHECK(ring.pop(10000, out) == Poll::empty); CHECK(!epoch.status().terminal);
}
void hole_does_not_reorder() {
    Epoch epoch; Ring ring(epoch); Record out{};
    auto first = ring.reserve(7), second = ring.reserve(8);
    CHECK(first.ticket() == 1 && second.ticket() == 2);
    CHECK(ring.publish(std::move(second), record(2)));
    CHECK(ring.pop(1, out) == Poll::pending);
    CHECK(out.header.ticket == 0);
    CHECK(ring.publish(std::move(first), record(1)));
    CHECK(ring.pop(2, out) == Poll::ready && out.header.ticket == 1);
    CHECK(ring.pop(2, out) == Poll::ready && out.header.ticket == 2);
}
void gap_timeout_and_late_publish() {
    Epoch epoch; Ring ring(epoch); Record out{};
    auto first = ring.reserve(7);
    CHECK(ring.push(record(2)));
    CHECK(ring.pop(100, out) == Poll::pending);
    CHECK(ring.pop(149, out) == Poll::pending);
    CHECK(ring.pop(150, out) == Poll::terminal);
    CHECK(reason(epoch.status()) == Fault::publication_gap);
    CHECK(!ring.publish(std::move(first), record(1)));
    CHECK(ring.pop(151, out) == Poll::terminal);
}
void capacity_and_abandon() {
    { Epoch epoch; Ring ring(epoch);
      for (unsigned i = 0; i < kCapacity; ++i) CHECK(ring.push(record(i)));
      CHECK(!ring.push(record(999))); CHECK(reason(epoch.status()) == Fault::ring_full); }
    { Epoch epoch; Ring ring(epoch); auto reservation = ring.reserve(7);
      ring.abandon(std::move(reservation), 7);
      CHECK(reason(epoch.status()) == Fault::producer_abandoned);
      CHECK(!ring.push(record())); }
}
void revoked_even_when_log_fails() {
    Capture capture(7); Payload data{}; CHECK(capture.bootstrap(7, 1, data));
    for (unsigned i = 1; i < kCapacity; ++i) CHECK(capture.frame(7, i + 1, data));
    const auto before = capture.status().epoch_word;
    CHECK(!capture.invalidate(Site::server_destructor, 9, 999, 0x90000, false));
    const auto after = capture.status();
    CHECK(after.terminal && (after.epoch_word & kRevoked) != 0);
    CHECK((after.epoch_word & ~kTerminal) == before + 2);
    CHECK(reason(after) == Fault::ring_full);
}
void nested_tokens_and_frame() {
    Capture capture(7); Payload data{}; Record out{};
    CHECK(capture.bootstrap(7, 1, data));
    const auto outer = capture.enter(Site::play, 7, 2, 0x90000, 0x140112000, data);
    const auto inner = capture.enter(Site::context_install, 7, 3, 0x8f000, 0x140112100, data);
    CHECK(outer.span == 1 && outer.parent == 0 && inner.parent == outer.span);
    CHECK(capture.leave(inner, 7, 4, data)); CHECK(capture.leave(outer, 7, 5, data));
    CHECK(capture.frame(7, 6, data));
    for (unsigned i = 0; i < 6; ++i) CHECK(capture.drain(100, out) == Poll::ready);
    CHECK(capture.drain(100, out) == Poll::empty);
    CHECK(!capture.status().terminal && !capture.status().production_ready);
}
void wrong_return_identity() {
    for (unsigned variation = 0; variation < 5; ++variation) {
        Capture capture(7); Payload data{}; CHECK(capture.bootstrap(7, 1, data));
        auto token = capture.enter(Site::play, 7, 2, 0x90000, 0x140112000, data);
        switch (variation) {
        case 0: ++token.span; break; case 1: ++token.parent; break;
        case 2: ++token.entry_rsp; break; case 3: ++token.return_va; break;
        default: token.site = Site::fallback; break;
        }
        CHECK(!capture.leave(token, 7, 3, data));
        CHECK(reason(capture.status()) == Fault::return_mismatch);
    }
}
void thread_clock_depth_and_unwind() {
    { Capture capture(7); Payload data{}; CHECK(!capture.bootstrap(8, 1, data));
      CHECK(reason(capture.status()) == Fault::wrong_thread); }
    { Capture capture(7); Payload data{}; CHECK(capture.bootstrap(7, 2, data));
      CHECK(!capture.frame(7, 1, data)); CHECK(reason(capture.status()) == Fault::clock_regressed); }
    { Capture capture(7); Payload data{}; CHECK(capture.bootstrap(7, 1, data));
      for (unsigned i = 0; i < kMaxDepth; ++i)
          CHECK(capture.enter(Site::fallback, 7, i + 2, 0x90000 - i * 0x100, 0x140112000, data).span != 0);
      CHECK(capture.enter(Site::fallback, 7, 99, 0x80000, 0x140112000, data).span == 0);
      CHECK(reason(capture.status()) == Fault::stack_overflow); }
    { Capture capture(7); capture.abnormal_return(7);
      CHECK(reason(capture.status()) == Fault::unexpected_unwind); }
}
void invalid_payload_and_active_scope() {
    { Capture capture(7); Payload data{}; data.values[39] = 1;
      CHECK(!capture.bootstrap(7, 1, data)); CHECK(reason(capture.status()) == Fault::bad_record); }
    { Capture capture(7); Payload data{}; CHECK(capture.bootstrap(7, 1, data));
      CHECK(capture.enter(Site::play, 7, 2, 0x90000, 0x140112000, data).span != 0);
      CHECK(!capture.frame(7, 3, data)); CHECK(capture.status().terminal); }
}
void foreign_revoke_and_stop() {
    Capture capture(7); Payload data{}; Record out{};
    CHECK(capture.bootstrap(7, 1, data));
    CHECK(capture.invalidate(Site::context_transition, 9, 2, 0x50000, true));
    CHECK(capture.status().epoch_word == 3);
    CHECK(capture.drain(3, out) == Poll::ready);
    CHECK(capture.drain(3, out) == Poll::ready && out.header.thread == 9);
    capture.stop(7); CHECK(capture.status().terminal); CHECK(!capture.status().production_ready);
}
}
int main() {
    fifo_wrap(); hole_does_not_reorder(); gap_timeout_and_late_publish(); capacity_and_abandon();
    revoked_even_when_log_fails(); nested_tokens_and_frame(); wrong_return_identity();
    thread_clock_depth_and_unwind(); invalid_payload_and_active_scope(); foreign_revoke_and_stop();
    std::printf("checks=%u failures=%u\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
