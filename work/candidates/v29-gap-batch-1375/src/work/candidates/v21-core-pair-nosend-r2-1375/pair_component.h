#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <string_view>
#include <vector>

// Private, synthetic-only component. There is no OS/native adapter or sender.
namespace v21pair {
enum class Family : std::uint8_t { Vassal, Marriage, Improve, Guarantee, SpyNetwork, Curry, FleetOffer, Insult, Coalition, Independence, FavorGold, FavorMen, FavorSailors, FavorTrust, FavorWarPrep };
enum class Action : std::uint8_t {
    OfferVassal, CancelVassal, Marriage, BreakMarriage, Improve, StopImprove,
    Guarantee, RevokeGuarantee, SpyNetwork, StopSpyNetwork, Curry, StopCurry, FleetOffer, Insult, Coalition, Independence, FavorGold, FavorMen, FavorSailors, FavorTrust, FavorWarPrep
};
enum class FullCallerEvidence : std::uint8_t { StaticSlotOnly, SealedNormalCaller };
struct Profile {
    Family family;
    std::uint32_t token, size, vtable, clone, destructor, setter, local80, full88;
    FullCallerEvidence full_caller;
};
const std::array<Profile, 15>& profiles() noexcept;
const Profile& profile(Action action);
bool positive(Action action) noexcept;
bool parse_action(std::string_view text, Action& result) noexcept;
struct Tag { std::array<char, 3> bytes{}; };
struct Request { Action action{}; Tag actor{}, target{}; };
// Only action name and two TAGs. No native inputs, flags, handles, or credentials.
bool make_request(std::string_view action, std::string_view actor, std::string_view target, Request& out) noexcept;
struct FullHandle { std::uint64_t value{}; };
bool operator==(FullHandle a, FullHandle b) noexcept;
bool valid(FullHandle h) noexcept;
struct OwnedId { std::uint64_t value{}; }; // synthetic object key, never a native pointer
bool operator==(OwnedId a, OwnedId b) noexcept;
struct PairStamp {
    std::uint64_t process_creation{}, session{}, module_pin{}, database{}, game{}, array{},
        actor_object{}, target_object{}, owner_thread{}, world_witness{};
    std::uint32_t count{}, date{}, reset{};
    FullHandle actor{}, target{}, current_player{}, effective_player{};
    bool operator==(const PairStamp& b) const noexcept;
};
bool valid(const PairStamp& s) noexcept;
enum class Dependency : std::uint8_t { None, Vassal, ClientVassal, Appanage, Union };
// Supplied only by a future private reader; current tests inject these observations.
// This struct is NOT authentication, a lifetime lock, SP, epoch, or permission proof.
struct CancelObservation {
    Family family{};
    bool active{}, known_type{}, outgoing{}, reciprocal{}, mission_linked{};
    FullHandle actor{}, target{}, actor_overlord{}, target_overlord{};
    Dependency dependency{};
    std::uint64_t object{}, mission{}, revision{};
    bool operator==(const CancelObservation& b) const noexcept;
};
bool cancel_matches(const Profile&, const PairStamp&, const CancelObservation&) noexcept;
struct String32View {
    std::uint64_t length{}, capacity{15};
    bool storage_valid{true};
    std::uint8_t first{}, terminator{}, force{};
};
struct ActionView {
    std::uint32_t size{}, vtable{}, marker{0x165}, primary{0x29c77f8}, secondary{0x29c77f8}, state{}, id{};
    FullHandle actor{0x2d2d2d}, controller{0x2d2d2d}, target{0x2d2d2d};
    std::int32_t envoy{-1};
    std::uint8_t value{1}, flag{};
    String32View text{};
};
struct CommandView {
    std::uint32_t size{0x58}, vtable{0x1c814b0}, marker{0x165}, token{0x2934}, field3c{};
    std::uint8_t field10{};
    std::uint64_t field18{}, field28{}, field30{15}, field48{0xffff};
    std::int32_t field38{-1};
    std::uint16_t field40{};
    OwnedId clone{};
};
// Read-only bounded graph port. It is an injected byte source, not OS attestation.
class SyntheticReadPort {
public:
    virtual ~SyntheticReadPort() = default;
    virtual bool read(std::uint64_t address, void* output, std::size_t size) = 0;
};
struct ReadWord {
    std::uint64_t address{};
    std::size_t size{};
    std::array<std::uint8_t,8> bytes{};
    bool operator==(const ReadWord& b) const noexcept {return address==b.address && size==b.size && bytes==b.bytes;}
};
struct SpyBinding {
    std::int32_t envoy{-1};
    std::uint64_t record{}, root{}, holder{}, manager{}, begin{}, end{}, entry{}, mission{}, task{},
        target_owner{}, head{}, tail{};
    std::uint32_t count{};
    std::vector<ReadWord> observations; // exact bounded transcript, no hash/padding equality
    bool operator==(const SpyBinding& b) const noexcept;
};
// All three calls read afresh. Equal snapshots do not exclude ABA or lock lifetimes.
bool bind_spy_once(SyntheticReadPort&, std::uint64_t module, const PairStamp&, SpyBinding&);
bool bind_spy_two_pass(SyntheticReadPort&, std::uint64_t module, const PairStamp&, SpyBinding&);
bool recheck_spy(SyntheticReadPort&, std::uint64_t module, const PairStamp&, const SpyBinding&);

class SyntheticGuard {
public:
    virtual ~SyntheticGuard() = default;
    virtual std::uint64_t clock() = 0;
    virtual bool stamp(const Request&, PairStamp&) = 0;
    virtual bool cancellation(Family, const PairStamp&, CancelObservation&) = 0;
};
struct Wrapped { OwnedId command{}; bool returned_same_slot{}; };
class SyntheticEngine {
public:
    virtual ~SyntheticEngine() = default;
    virtual OwnedId factory(const Profile&) = 0;
    virtual bool action_view(OwnedId, ActionView&) = 0;
    virtual bool initialize_owned(OwnedId, const PairStamp&) = 0;
    virtual void mode_setter(const Profile&, OwnedId, bool) = 0; // native setter is void
    virtual bool bind_envoy_owned(OwnedId, std::int32_t) = 0;
    // Exact family+88 arguments are always NULL text / false, never local80/generic4e9d00.
    virtual bool full88(const Profile&, OwnedId, std::nullptr_t text, bool option) = 0;
    virtual Wrapped wrapper(const Profile&, OwnedId) = 0;
    virtual bool command_view(OwnedId, CommandView&) = 0;
    virtual bool command_gate(OwnedId) = 0;
    virtual bool destroy_action(const Profile&, OwnedId) = 0;
    virtual bool destroy_command(OwnedId) = 0; // owns the independent clone
};
enum class Status : std::uint8_t { Invalid, PreconditionRejected, ModelPreviewRejected, ModelGateRejected, ModelComplete, Frozen };
struct Result {
    Status status{Status::Invalid};
    const char* reason{"invalid"};
    OwnedId quarantined_original{}, quarantined_command{}, quarantined_clone{};
    bool runtime_verified{false}, native_ready{false}, production_ready{false}, submitted{false};
};
// No ownership transfer, context, sender, durable intent, reservation or transport exists.
Result preflight_no_send(const Request&, SyntheticGuard&, SyntheticEngine&,
    std::uint64_t expires, SyntheticReadPort* spy_reader = nullptr, std::uint64_t module = 0) noexcept;
}
