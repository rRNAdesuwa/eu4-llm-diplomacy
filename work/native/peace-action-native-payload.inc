// Read-only action snapshots used by lifecycle, protocol and authority proofs.
// The large capture scratch and published logical offer both live on the heap.
#include "peace-payload-ref.h"

static bool peace_capture_offer_snapshot(const void* native_offer,
    bridge::peace_payload::PeacePayloadRef& output) noexcept {
    using namespace bridge::peace_payload;
    output.reset();
    void* memory=std::malloc(sizeof(PeaceSerializedCapture));
    if (!memory) return false;
    auto* captured=new(memory) PeaceSerializedCapture();
    auto offer=PeacePayloadRef::allocate();
    auto* destination=offer.builder();
    const bool complete=destination
        && peace_capture_serialized_offer(native_offer,*captured)
        && captured->owner_verified && captured->structure_complete
        && captured->fields_complete && captured->selected_index_complete
        && captured->unsupported_count==0 && captured->payload.valid();
    if (complete) *destination=captured->payload;
    captured->~PeaceSerializedCapture();
    std::free(captured);
    if (!complete || !offer.seal()) return false;
    output=std::move(offer);
    return true;
}

static bool lifecycle_peace_capture_payload(uintptr_t action,
    bridge::peace_payload::PeaceActionPayload& output) noexcept {
    using namespace bridge::peace_payload;
    output=PeaceActionPayload{};
    if (!action || !read(action+0x40,output.flag40)
        || !read(action+0x41,output.direction41)
        || !read(action+0x208,output.preview208)
        || output.flag40>1 || output.direction41>1 || output.preview208>1
        || !peace_capture_offer_snapshot(reinterpret_cast<void*>(action+0x48),output.offer))
        return false;
    return output.valid();
}

static void lifecycle_peace_payload_json(char* output,size_t capacity,
    const bridge::peace_payload::PeaceActionPayload& peace) noexcept {
    const auto* offer=peace.offer.get();
    unsigned selected=0;
    if (offer) for (unsigned i=0;i<offer->term_count;++i)
        if (offer->terms[i].selected) ++selected;
    snprintf(output,capacity,
        "{\"complete\":%s,\"term_count\":%u,\"selected_term_count\":%u,"
        "\"participant_counts\":[%u,%u,%u,%u],\"flag40\":%u,"
        "\"direction41\":%u,\"preview208\":%u}",
        peace.valid()?"true":"false",offer?offer->term_count:0,selected,
        offer?offer->participants[0].count:0,offer?offer->participants[1].count:0,
        offer?offer->participants[2].count:0,offer?offer->participants[3].count:0,
        static_cast<unsigned>(peace.flag40),static_cast<unsigned>(peace.direction41),
        static_cast<unsigned>(peace.preview208));
}
