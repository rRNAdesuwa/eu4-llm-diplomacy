#pragma once

// A small owning snapshot reference for native command proofs.  The complete
// logical offer lives on the observer's heap, never in the game's containers.
// Builders must seal a valid snapshot before publishing it to another owner.
#include "peace-payload.h"
#include <atomic>
#include <cstdlib>
#include <new>
#include <utility>

namespace bridge::peace_payload {

class PeacePayloadRef {
    struct Storage {
        std::atomic<std::uint32_t> references{1};
        std::atomic<bool> sealed{false};
        PeaceOfferPayload payload{};
    };
    Storage* storage_=nullptr;

    explicit PeacePayloadRef(Storage* storage) noexcept : storage_(storage) {}

    void retain() noexcept {
        if (storage_) storage_->references.fetch_add(1,std::memory_order_relaxed);
    }
    void release() noexcept {
        if (storage_ && storage_->references.fetch_sub(1,std::memory_order_acq_rel)==1) {
            storage_->~Storage();
            std::free(storage_);
        }
        storage_=nullptr;
    }

public:
    PeacePayloadRef() noexcept=default;
    PeacePayloadRef(const PeacePayloadRef& other) noexcept : storage_(other.storage_) {
        retain();
    }
    PeacePayloadRef(PeacePayloadRef&& other) noexcept : storage_(other.storage_) {
        other.storage_=nullptr;
    }
    PeacePayloadRef& operator=(const PeacePayloadRef& other) noexcept {
        if (this!=&other) {
            PeacePayloadRef retained(other);
            swap(retained);
        }
        return *this;
    }
    PeacePayloadRef& operator=(PeacePayloadRef&& other) noexcept {
        if (this!=&other) {
            release();
            storage_=other.storage_;
            other.storage_=nullptr;
        }
        return *this;
    }
    ~PeacePayloadRef() noexcept { release(); }

    static PeacePayloadRef allocate() noexcept {
        void* memory=std::malloc(sizeof(Storage));
        if (!memory) return {};
        return PeacePayloadRef(new(memory) Storage());
    }
    void reset() noexcept { release(); }
    void swap(PeacePayloadRef& other) noexcept {
        Storage* previous=storage_;
        storage_=other.storage_;
        other.storage_=previous;
    }
    bool empty() const noexcept { return storage_==nullptr; }
    std::uint32_t use_count() const noexcept {
        return storage_?storage_->references.load(std::memory_order_acquire):0;
    }
    PeaceOfferPayload* builder() noexcept {
        if (!storage_ || storage_->sealed.load(std::memory_order_acquire)
            || use_count()!=1) return nullptr;
        return &storage_->payload;
    }
    bool seal() noexcept {
        PeaceOfferPayload* value=builder();
        if (!value || !value->valid()) return false;
        storage_->sealed.store(true,std::memory_order_release);
        return true;
    }
    const PeaceOfferPayload* get() const noexcept {
        return storage_ && storage_->sealed.load(std::memory_order_acquire)
            ?&storage_->payload:nullptr;
    }
    bool valid() const noexcept {
        const auto* value=get();
        return value && value->valid();
    }
    bool operator==(const PeacePayloadRef& other) const noexcept {
        if (empty() || other.empty()) return empty() && other.empty();
        const auto* left=get();
        const auto* right=other.get();
        return left && right && *left==*right;
    }
    bool operator!=(const PeacePayloadRef& other) const noexcept {
        return !(*this==other);
    }
};

static_assert(sizeof(PeacePayloadRef)==sizeof(void*),
    "A native proof snapshot must add only one pointer to each frame/ledger record");

// These three bytes are copied by the native Peace action clone in addition
// to its common diplomatic fields and the embedded logical offer.
struct PeaceActionPayload {
    PeacePayloadRef offer{};
    std::uint8_t flag40=0;
    std::uint8_t direction41=0;
    std::uint8_t preview208=0;

    bool empty() const noexcept {
        return offer.empty() && flag40==0 && direction41==0 && preview208==0;
    }
    bool valid() const noexcept {
        const auto* value=offer.get();
        return value && value->valid() && flag40<=1 && direction41<=1
            && preview208<=1 && value->direction==direction41;
    }
    bool operator==(const PeaceActionPayload& other) const noexcept {
        return flag40==other.flag40 && direction41==other.direction41
            && preview208==other.preview208 && offer==other.offer;
    }
    bool operator!=(const PeaceActionPayload& other) const noexcept {
        return !(*this==other);
    }
};

} // namespace bridge::peace_payload
