// Strict binding of constructor captures to the final reason vector.
// Included only by alliance-query.inc when BRIDGE_ALLIANCE_REASON_METADATA is
// defined. The row index is bound to the constructor sequence, initialized
// row fields, string storage identity and all text bytes. Alignment padding
// and unused std::string storage are not initialized by the constructor.

#ifndef BRIDGE_ALLIANCE_REASON_METADATA_BIND_INC
#define BRIDGE_ALLIANCE_REASON_METADATA_BIND_INC

#include "alliance-reason-metadata.inc"
#include "alliance-reason-row.h"

namespace bridge_alliance_reason_metadata_bind_detail {

constexpr unsigned kBindRowBytes=48;
constexpr unsigned kBindTextBytes=512;
constexpr unsigned kBindCapacity=32;

struct Binding {
    const ReasonMetadataRecord* capture=nullptr;
    bool final_row_readable=false;
    bool final_string_shape_valid=false;
    bool final_text_readable=false;
    bool final_raw_matches=false;
    bool final_text_matches=false;
    bool constructor_value_verified=false;
    bool strict_match=false;
    int32_t final_value=0;
    unsigned char final_flag=0;
    uint64_t final_string_size=0;
    uint64_t final_string_capacity=0;
    unsigned final_text_bytes=0;
    unsigned char final_raw[kBindRowBytes]{};
    unsigned char final_text[kBindTextBytes]{};
};

static bool read_final_row(uintptr_t address,Binding& binding) noexcept {
    SIZE_T copied=0;
    if (!address || !ReadProcessMemory(GetCurrentProcess(),
        reinterpret_cast<void*>(address),binding.final_raw,kBindRowBytes,&copied)
        || copied!=kBindRowBytes) return false;
    binding.final_row_readable=true;
    memcpy(&binding.final_value,binding.final_raw,
        sizeof(binding.final_value));
    binding.final_flag=binding.final_raw[0x28];
    memcpy(&binding.final_string_size,binding.final_raw+0x08+0x10,
        sizeof(binding.final_string_size));
    memcpy(&binding.final_string_capacity,binding.final_raw+0x08+0x18,
        sizeof(binding.final_string_capacity));
    const bool inline_string=binding.final_string_capacity<16;
    binding.final_text_bytes=static_cast<unsigned>(
        binding.final_string_size<=kBindTextBytes
            ?binding.final_string_size:kBindTextBytes);
    binding.final_string_shape_valid=binding.final_string_size
        <=binding.final_string_capacity
        && binding.final_string_capacity<=131072
        && (inline_string || binding.final_string_capacity>=16)
        && binding.final_string_size<=kBindTextBytes;
    if (!binding.final_string_shape_valid) return true;
    if (!binding.final_text_bytes) {
        binding.final_text_readable=true;
        return true;
    }
    uintptr_t text_address=address+0x08;
    if (!inline_string) memcpy(&text_address,binding.final_raw+0x08,
        sizeof(text_address));
    if (!text_address) return true;
    copied=0;
    binding.final_text_readable=ReadProcessMemory(GetCurrentProcess(),
        reinterpret_cast<void*>(text_address),binding.final_text,
        binding.final_text_bytes,&copied)!=FALSE
        && copied==binding.final_text_bytes;
    return true;
}

static bool bind_rows(uintptr_t vector_begin,unsigned reason_count,
    Binding* bindings,unsigned binding_capacity,unsigned* capture_count,
    bool* capture_overflow) noexcept {
    if (capture_count) *capture_count=0;
    if (capture_overflow) *capture_overflow=false;
    if (!bindings || binding_capacity<kBindCapacity) return false;
    bool overflow=false;
    const unsigned captured=bridge_alliance_reason_metadata_scope_count(
        &overflow);
    if (capture_count) *capture_count=captured;
    if (capture_overflow) *capture_overflow=overflow;
    const bool count_shape=reason_count<=kBindCapacity
        && captured==reason_count && !overflow;
    const unsigned limit=reason_count<binding_capacity
        ?reason_count:binding_capacity;
    bool all=count_shape;
    for (unsigned index=0;index<limit;++index) {
        bindings[index]=Binding{};
        Binding& binding=bindings[index];
        binding.capture=bridge_alliance_reason_metadata_scope_record(index);
        if (!vector_begin || index>=(UINTPTR_MAX-vector_begin)/kBindRowBytes)
            { all=false; continue; }
        const bool row_readable=read_final_row(
            vector_begin+static_cast<uintptr_t>(index)*kBindRowBytes,binding);
        if (!row_readable || !binding.capture) { all=false; continue; }
        const ReasonMetadataRecord& capture=*binding.capture;
        binding.final_raw_matches=
            bridge_alliance_reason_row::same_initialized_storage(
                capture.row_raw,binding.final_raw);
        binding.constructor_value_verified=capture.row_readable
            && capture.returned_row_matches
            && capture.constructor_argument_value==capture.raw_value
            && capture.raw_value==binding.final_value
            && capture.derived_flag==binding.final_flag;
        binding.final_text_matches=capture.string_shape_valid
            && capture.text_readable && !capture.text_truncated
            && binding.final_string_shape_valid
            && binding.final_text_readable
            && capture.string_size==binding.final_string_size
            && capture.string_capacity==binding.final_string_capacity
            && capture.text_bytes==binding.final_text_bytes
            && memcmp(capture.text,binding.final_text,
                capture.text_bytes)==0;
        binding.strict_match=capture.sequence==static_cast<uint64_t>(index+1)
            && binding.final_raw_matches
            && binding.constructor_value_verified
            && binding.final_text_matches;
        if (!binding.strict_match) all=false;
    }
    if (limit!=reason_count) all=false;
    return all;
}

} // namespace bridge_alliance_reason_metadata_bind_detail

using bridge_alliance_reason_metadata_bind_detail::Binding;
using bridge_alliance_reason_metadata_bind_detail::bind_rows;

#endif
