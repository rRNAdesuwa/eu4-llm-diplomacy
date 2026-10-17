// Bounded read-only capture for the Declare War action's owned payload.
//
// This include is pulled in by alliance-lifecycle.inc after control-probe.cpp
// has supplied `base` and the bounded `read` helper.  It deliberately keeps
// the native storage offsets in the cross-platform declarewar-payload.h model;
// no native method is called while observing an action.

#pragma once

#include "declarewar-payload.h"

static constexpr uintptr_t lifecycle_declarewar_empty_sentinel_rva=0x2340010;

static bool lifecycle_declarewar_capture_owned(
    uintptr_t owned,bridge::declarewar_payload::WarOwnedPayload& output) {
    using bridge::declarewar_payload::WarOwnedPayload;
    if (!owned || owned<0x10000) return false;

    WarOwnedPayload captured{};
    if (!read(owned+bridge::declarewar_payload::WarOwnedPayloadLayout::field08,
            captured.owned_field08)
        || !read(owned+bridge::declarewar_payload::WarOwnedPayloadLayout::field10,
            captured.owned_field10)
        || !read(owned+bridge::declarewar_payload::WarOwnedPayloadLayout::field18,
            captured.owned_field18)
        || !read(owned+bridge::declarewar_payload::WarOwnedPayloadLayout::field1c,
            captured.owned_field1c)
        || !read(owned+bridge::declarewar_payload::WarOwnedPayloadLayout::field28,
            captured.owned_field28)
        || !read(owned+bridge::declarewar_payload::WarOwnedPayloadLayout::field30,
            captured.owned_field30)
        || !read(owned+bridge::declarewar_payload::WarOwnedPayloadLayout::field38,
            captured.owned_field38)
        || !read(owned+bridge::declarewar_payload::WarOwnedPayloadLayout::field40,
            captured.owned_field40)
        || !read(owned+bridge::declarewar_payload::WarOwnedPayloadLayout::field48,
            captured.owned_field48)
        || !read(owned+bridge::declarewar_payload::WarOwnedPayloadLayout::field50,
            captured.owned_field50)
        || !read(owned+bridge::declarewar_payload::WarOwnedPayloadLayout::field58,
            captured.owned_field58)) return false;
    output=captured;
    return true;
}

static bool lifecycle_declarewar_capture_payload(uintptr_t action,
    bridge::declarewar_payload::WarPayloadExtension& output) {
    using bridge::declarewar_payload::WarPayloadExtension;
    output=WarPayloadExtension{};
    if (!action || action<0x10000) return false;

    if (!read(action+0x40,output.flag40)
        || !read(action+0x41,output.flag41)
        || !read(action+0x42,output.flag42)) return false;

    uintptr_t owned=0,empty_sentinel=0;
    if (!read(action+0x48,owned)
        || !read(base+lifecycle_declarewar_empty_sentinel_rva,empty_sentinel)) return false;

    // The native constructor uses the process-global object at 2340010 as
    // the empty owned-payload sentinel.  It is not a payload object and must
    // never be dereferenced as one.
    output.owned_present=owned!=empty_sentinel;
    // A native empty action points at the canonical sentinel. A null or any
    // other pointer is therefore an owned payload candidate, and must pass
    // the complete fixed-field read before it can participate in equality.
    if (output.owned_present
        && (!owned || !lifecycle_declarewar_capture_owned(owned,output.owned))) return false;

    // Each vector is independently bounded before any element is read.  A
    // malformed span makes the whole snapshot incomplete instead of allowing
    // a partial payload to participate in clone/transport equality.
    auto bounded_reader=[](uintptr_t address,auto& value)->bool {
        return read(address,value);
    };
    if (!bridge::declarewar_payload::war_capture_native_u64_vector(
            bounded_reader,action,
            bridge::declarewar_payload::kWarContainer50Layout,output.container50)
        || !bridge::declarewar_payload::war_capture_native_u64_vector(
            bounded_reader,action,
            bridge::declarewar_payload::kWarContainer68Layout,output.container68)
        || !bridge::declarewar_payload::war_capture_native_u64_vector(
            bounded_reader,action,
            bridge::declarewar_payload::kWarContainer80Layout,output.container80)) {
        output=WarPayloadExtension{};
        return false;
    }
    return output.valid();
}

// Keep process-local owned values private while making shape JSON explicit
// about family and completeness.  The equality contract still compares every
// captured vector element; this summary intentionally exposes only counts and
// scalar storage, so the public AI projection cannot receive raw definition
// pointers or vector contents.
static void lifecycle_declarewar_payload_json(char* output,size_t capacity,
    const bridge::declarewar_payload::WarPayloadExtension& payload,
    bool complete,bool compact=false) {
    if (compact) {
        snprintf(output,capacity,
            "{\"payload_complete\":%s,\"valid\":%s,\"flag40\":%u,\"flag41\":%u,\"flag42\":%u,\"owned_present\":%s,\"owned_fields_captured\":%s,\"container50_count\":%u,\"container68_count\":%u,\"container80_count\":%u}",
            complete?"true":"false",payload.valid()?"true":"false",
            static_cast<unsigned>(payload.flag40),static_cast<unsigned>(payload.flag41),
            static_cast<unsigned>(payload.flag42),payload.owned_present?"true":"false",
            payload.owned_present?"true":"false",
            static_cast<unsigned>(payload.container50.count),
            static_cast<unsigned>(payload.container68.count),
            static_cast<unsigned>(payload.container80.count));
        return;
    }
    const auto& owned=payload.owned;
    snprintf(output,capacity,
        "{\"payload_complete\":%s,\"valid\":%s,\"flag40\":%u,\"flag41\":%u,\"flag42\":%u,\"owned_present\":%s,\"owned_field08\":%u,\"owned_field10\":\"0x%llx\",\"owned_field18\":%u,\"owned_field1c\":\"0x%llx\",\"owned_field28\":\"0x%llx\",\"owned_field30\":\"0x%llx\",\"owned_field38\":\"0x%llx\",\"owned_field40\":\"0x%llx\",\"owned_field48\":\"0x%llx\",\"owned_field50\":\"0x%llx\",\"owned_field58\":\"0x%llx\",\"container50_count\":%u,\"container68_count\":%u,\"container80_count\":%u}",
        complete?"true":"false",payload.valid()?"true":"false",
        static_cast<unsigned>(payload.flag40),static_cast<unsigned>(payload.flag41),
        static_cast<unsigned>(payload.flag42),payload.owned_present?"true":"false",
        static_cast<unsigned>(owned.owned_field08),
        static_cast<unsigned long long>(owned.owned_field10),
        static_cast<unsigned>(owned.owned_field18),
        static_cast<unsigned long long>(owned.owned_field1c),
        static_cast<unsigned long long>(owned.owned_field28),
        static_cast<unsigned long long>(owned.owned_field30),
        static_cast<unsigned long long>(owned.owned_field38),
        static_cast<unsigned long long>(owned.owned_field40),
        static_cast<unsigned long long>(owned.owned_field48),
        static_cast<unsigned long long>(owned.owned_field50),
        static_cast<unsigned long long>(owned.owned_field58),
        static_cast<unsigned>(payload.container50.count),
        static_cast<unsigned>(payload.container68.count),
        static_cast<unsigned>(payload.container80.count));
}
