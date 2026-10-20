#pragma once
#include "../v21-core-pair-nosend-r2-1375/pair_component.h"
#include <atomic>
namespace v21pair {
enum class TransferOutcome : std::uint8_t { NotAttempted, Dispatched, Unknown };
struct TransferReturn {bool normal{},value{},slot_consumed{};std::uint32_t exception{};};
// Private port only. No addresses, context, flags or credentials are public.
class TransferPort {
public:
    virtual ~TransferPort()=default;
    // Must durably record intent. The core rechecks all fields/world/original TTL
    // AFTER this callback. A record alone never authorizes native entry.
    virtual bool dispatch_intent(const Request&,const PairStamp&,OwnedId command,OwnedId clone)=0;
    // Implementer must consume its OWN ledger IDs, validate its private context,
    // and make a final world/clock check immediately before ABI entry. Any entry
    // relinquishes local ownership, including false, exception or non-NULL slot.
    // The core never reads/destroys transferred objects after this callback.
    virtual TransferReturn submit_owned(OwnedId command)=0;
};
struct SendResult : Result {
    TransferOutcome transfer{TransferOutcome::NotAttempted};
    bool submit_entered{},submit_returned{},submit_value{},slot_consumed{};
    std::uint32_t submit_exception{};
};
class SendCore {
public:
    SendCore()=default;
    SendCore(const SendCore&)=delete;SendCore& operator=(const SendCore&)=delete;
    SendResult invoke(const Request&,SyntheticGuard&,SyntheticEngine&,TransferPort&,
        std::uint64_t original_expires,SyntheticReadPort* spy_reader=nullptr,std::uint64_t module=0) noexcept;
private:
    std::atomic_bool attempted_{false};
};
}
