#pragma once
#include "../v21-core-pair-nosend-r2-1375/pair_component.h"
#include <atomic>
#include "../v24-pair-send-core-r2-1375/pair_send.h"

// Private implementation port; no wire, public pointer, sender or process API.
namespace v24port {
using Address=std::uint64_t;
enum class Call : std::uint8_t { Factory, Setter, Full88, Wrapper, Gate, ActionDestructor, CommandDestructor };
enum class Fault : std::uint8_t { None, Reentry, Authority, Profile, UnknownId, Region, Read, Write,
    Type, Fields, Alias, Budget, NativeException, WrapperSlot, Ownership, Order };
struct NativeFault { Fault reason; std::uint32_t exception; };
struct Region { Address base{}; std::uint64_t size{}; bool committed{}, private_memory{}, read_write{}; };
struct Return {
    bool normal{}, boolean{}, returned_same_slot{};
    Address object{};std::uint32_t exception{};
};
struct TransferEnvelope {
    v21pair::Profile profile{};v21pair::PairStamp stamp{};
    Address command{},clone{};bool mode{};std::int32_t envoy{-1};
};
// An injected private platform, never accepted from public JSON or module API.
// ready() must freshly establish the owner thread and exact image/permission
// proof. No implementation here certifies SP, world epoch or live roots.
// Implementations must enforce a last fresh world + monotonic/original-TTL
// check inside invoke AFTER all preparation reads, and inside each write AFTER
// region validation. The real compiled platform takes private typed callbacks.
class Platform {
public:
    virtual ~Platform()=default;
    virtual Address module() const noexcept=0;
    virtual bool ready()=0;
    virtual bool region(Address,Region&)=0;
    virtual bool read(Address,void*,std::size_t)=0;
    virtual bool write(Address,const void*,std::size_t)=0;
    virtual Return invoke(Call,const v21pair::Profile&,Address,bool)=0;
    virtual v21pair::TransferReturn submit(const TransferEnvelope&) {return {};}
};
struct Diagnostics {
    bool frozen{};Fault fault{};std::uint32_t exception{}, issued{}, live{}, quarantined{}, calls{}, reads{}, writes{};
    std::uint64_t read_bytes{};std::uint32_t unresolved_returns{};
    bool runtime_verified{},native_ready{},submitted{},production_ready{};
};
class NativePairEngineDraft final : public v21pair::SyntheticEngine {
public:
    explicit NativePairEngineDraft(Platform&) noexcept;
    ~NativePairEngineDraft() override=default; // Never guesses cleanup on scope exit.
    NativePairEngineDraft(const NativePairEngineDraft&)=delete;
    NativePairEngineDraft& operator=(const NativePairEngineDraft&)=delete;
    v21pair::OwnedId factory(const v21pair::Profile&) override;
    bool action_view(v21pair::OwnedId,v21pair::ActionView&) override;
    bool initialize_owned(v21pair::OwnedId,const v21pair::PairStamp&) override;
    void mode_setter(const v21pair::Profile&,v21pair::OwnedId,bool) override;
    bool bind_envoy_owned(v21pair::OwnedId,std::int32_t) override;
    bool full88(const v21pair::Profile&,v21pair::OwnedId,std::nullptr_t,bool) override;
    v21pair::Wrapped wrapper(const v21pair::Profile&,v21pair::OwnedId) override;
    bool command_view(v21pair::OwnedId,v21pair::CommandView&) override;
    bool command_gate(v21pair::OwnedId) override;
    bool destroy_action(const v21pair::Profile&,v21pair::OwnedId) override;
    bool destroy_command(v21pair::OwnedId) override;
    v21pair::TransferReturn transfer_owned(v21pair::OwnedId);
    Diagnostics diagnostics() const noexcept;
private:
    enum class Kind : std::uint8_t { Original, Command, Clone };
    struct Entry { v21pair::OwnedId id{};Address address{};const v21pair::Profile* profile{};Kind kind{};
        bool live{},quarantined{},initialized{},mode_set{},mode{true},envoy_bound{},previewed{},wrapped{},gate_checked{},gate_allowed{},transferred{};
        v21pair::PairStamp stamp{};std::int32_t envoy{-1};v21pair::OwnedId peer{},source{}; };
    struct Operation;
    Platform& platform_;std::array<Entry,64> entries_{};std::uint32_t issued_{},reads_{},writes_{},calls_{};
    std::uint64_t bytes_{},owner_serial_{};std::atomic_bool active_{false},frozen_{false};Fault fault_{Fault::None};std::uint32_t exception_{};
    // Raw candidate addresses retained privately even when ownership cannot be established.
    std::array<Address,64> unresolved_{};std::uint32_t unresolved_count_{};
    void latch(Fault,std::uint32_t=0) noexcept;
    void retain(Address);void resolved(Address) noexcept;
    [[noreturn]] void fail(Fault,std::uint32_t=0);
    void check();const v21pair::Profile& fixed(const v21pair::Profile&);
    Entry& lookup(v21pair::OwnedId);Entry& insert(Address,const v21pair::Profile&,Kind);
    bool private_range(Address,std::size_t);
    void read(Address,void*,std::size_t);void write(Entry&,std::uint32_t,const void*,std::size_t);
    template<class T> T get(Address p) { T result{};read(p,&result,sizeof(result));return result; }
    template<class T> void put(Entry& e,std::uint32_t off,const T& v) {write(e,off,&v,sizeof(v));}
    void header(Entry&);v21pair::ActionView view(Entry&);v21pair::CommandView command(Entry&);
    void expected(Entry&,bool empty);Return call(Call,const v21pair::Profile&,Address,bool=false);
};
}
