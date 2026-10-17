// Read-only Declare War candidate enumeration and optional candidate selection.
//
// The selection path only clones the uniquely matched native candidate.  It
// does not write an action, emit JSON, or submit a command.  The including
// translation unit supplies the existing `base` and `read` helpers from
// control-probe.cpp.
// The native call and cleanup order follow ee6930 exactly:
//   d9e9b0(actor,target,&vector,&zero_callback_holder)
//   destroy each returned candidate once
//   FUN_141739420(vector.begin)
//
// The fourth d9e9b0 argument is a 0x40-byte std::function-like callback
// storage.  A zero storage is the UI's empty callback case.  d9d090 receives
// the same holder as its sixth argument; there is no seventh entry parameter.

static constexpr uintptr_t declarewar_candidates_enumerator_rva=0xd9e9b0;
static constexpr uintptr_t declarewar_candidates_clone_rva=0xd9a960;
static constexpr uintptr_t declarewar_candidates_native_vector_vtable_rva=0x1c3d1e0;
static constexpr uintptr_t declarewar_candidates_candidate_vtable_rva=0x1d20290;
// ee6930 passes the value at this global as the empty candidate sentinel when
// it has no default selection.  A selected clone equal to this value is not
// transferred to the caller.
static constexpr uintptr_t declarewar_candidates_empty_sentinel_global_rva=
    0x2340010;
// ee6930 destroys each element and then calls FUN_141739420(begin) directly.
// The vector vtable at +0xa0 is not part of this cleanup path.
static constexpr uintptr_t declarewar_candidates_native_free_rva=0x1739420;
static constexpr unsigned declarewar_candidates_max_items=64;
static constexpr unsigned declarewar_candidates_max_native_walk=4096;
static constexpr unsigned declarewar_candidates_text_bytes=512;
static constexpr unsigned declarewar_candidates_text_hex_bytes=
    declarewar_candidates_text_bytes*2+1;
static constexpr unsigned declarewar_candidates_casus_belli_key_bytes=128;
static constexpr unsigned declarewar_candidates_casus_belli_key_storage=
    declarewar_candidates_casus_belli_key_bytes+1;
static constexpr uint64_t declarewar_candidates_beneficiary_sentinel_low24=
    0x2d2d2dull;

struct DeclareWarCandidateSelection {
    const char* casus_belli=nullptr;
    int32_t province_id=-1;
    uint64_t beneficiary_handle=0;
};

struct DeclareWarCandidateNativeVector {
    void* vtable=nullptr;
    void** begin=nullptr;
    uint32_t capacity=0;
    uint32_t count=0;
};
static_assert(sizeof(DeclareWarCandidateNativeVector)==0x18,
    "Declare War native candidate vector ABI");

struct DeclareWarCandidateCallbackHolder {
    alignas(8) unsigned char storage[0x40]{};
};
static_assert(sizeof(DeclareWarCandidateCallbackHolder)==0x40,
    "Declare War empty callback storage ABI");

struct DeclareWarCandidateMetadataString {
    char text[16];
    uint64_t size;
    uint64_t capacity;
};
static_assert(sizeof(DeclareWarCandidateMetadataString)==0x20,
    "Declare War metadata short string ABI");

struct DeclareWarCandidateCapture {
    uintptr_t address=0;
    unsigned candidate_index=0;
    uintptr_t vtable=0;
    uint32_t vtable_rva=0;
    uintptr_t metadata=0;
    // candidate+0x08 is the common object discriminator (observed 0x165),
    // not a user-facing family/type identifier.
    uint32_t candidate_discriminator_raw=0;
    // +0x18 is a target-province index only for the observed candidate vtable.
    // Keep -1 for another vtable or an unreadable field.
    int32_t target_province_id=-1;
    bool target_province_id_verified=false;
    // Public query code uses this name in its JSON contract; keep it as an
    // explicit alias of target_province_id_verified.
    bool province_identifier_verified=false;
    // +0x38 is a packed native beneficiary handle.  The low 24-bit ASCII
    // `---` sentinel is normalized to beneficiary_handle=0 for matching.
    uint64_t beneficiary_raw=0;
    uint64_t beneficiary_handle=0;
    bool beneficiary_raw_readable=false;
    bool beneficiary_identifier_verified=false;
    int32_t metadata_group_raw=-1;
    uint64_t metadata_string_size=0;
    uint64_t metadata_string_capacity=0;
    unsigned metadata_text_bytes=0;
    bool readable=false;
    bool metadata_readable=false;
    bool metadata_text_readable=false;
    bool metadata_text_truncated=false;
    bool metadata_text_bytes_complete=false;
    char casus_belli_key[declarewar_candidates_casus_belli_key_storage]{};
    bool casus_belli_key_readable=false;
    bool casus_belli_key_verified=false;
    bool private_raw_readable=false;
    // The constructor evidence gives the candidate class a fixed 0x60-byte
    // extent.  This is an internal correlation sample only; no pointer inside
    // the bytes is dereferenced or exposed by the public projection.
    unsigned char private_raw[0x60]{};
    // The bytes are copied unchanged and rendered as lowercase hex.  The
    // field is named rawhex because no localization or key interpretation is
    // performed here; the native UI currently treats the source as UTF-8-like
    // text, but its stable CB/war-goal identifier meaning is not established.
    char metadata_text_utf8_rawhex[declarewar_candidates_text_hex_bytes]{};
};

struct DeclareWarCandidateQueryResult {
    uint64_t actor=0;
    uint64_t target=0;
    bool native_called=false;
    bool native_returned=false;
    bool callback_holder_empty_before=true;
    bool callback_holder_empty_after=true;
    bool callback_holder_cleanup_ok=true;
    bool vector_cleanup_ok=false;
    bool native_vector_shape_valid=false;
    bool all_items_readable=true;
    bool capture_complete=false;
    bool has_candidates=false;
    bool selection_requested=false;
    bool selection_clone_attempted=false;
    bool selection_clone_valid=false;
    bool truncated=false;
    bool complete=false;
    uint32_t native_count=0;
    unsigned captured_count=0;
    unsigned selection_match_count=0;
    uintptr_t selected_owned=0;
    int32_t selected_candidate_index=-1;
    DeclareWarCandidateCapture items[declarewar_candidates_max_items]{};
};

static bool declarewar_candidates_ascii_key(const unsigned char* bytes,
    unsigned length,char (&key)[declarewar_candidates_casus_belli_key_storage])
    noexcept {
    key[0]=0;
    if (!bytes || length==0 || length>declarewar_candidates_casus_belli_key_bytes)
        return false;
    for (unsigned index=0;index<length;++index) {
        const unsigned char value=bytes[index];
        const bool alpha=(value>='a' && value<='z')
            || (value>='A' && value<='Z');
        const bool digit=value>='0' && value<='9';
        if (!alpha && !digit && value!='_' && value!='-') return false;
    }
    memcpy(key,bytes,length);
    key[length]=0;
    return true;
}

static bool declarewar_candidates_normalize_beneficiary(uint64_t raw,
    uint64_t& handle) noexcept {
    if ((raw&0xffffffull)==declarewar_candidates_beneficiary_sentinel_low24) {
        handle=0;
        return true;
    }
    if (!raw) {
        handle=0;
        return false;
    }
    handle=raw;
    return true;
}

static bool declarewar_candidates_capture_text(uintptr_t metadata,
    DeclareWarCandidateCapture& output) noexcept {
    DeclareWarCandidateMetadataString text{};
    if (!metadata || !read(metadata+0x18,text)) return false;
    if (text.size>0x10000 || text.capacity>0x20000 || text.size>text.capacity)
        return false;

    output.metadata_string_size=text.size;
    output.metadata_string_capacity=text.capacity;
    const unsigned length=static_cast<unsigned>(
        text.size<declarewar_candidates_text_bytes
            ?text.size:declarewar_candidates_text_bytes);
    output.metadata_text_bytes=length;
    output.metadata_text_truncated=text.size>declarewar_candidates_text_bytes;
    output.metadata_text_bytes_complete=false;

    uintptr_t data=reinterpret_cast<uintptr_t>(text.text);
    if (text.capacity>=16) memcpy(&data,text.text,sizeof(data));
    unsigned char bytes[declarewar_candidates_text_bytes]{};
    if (length) {
        if (!data) return false;
        SIZE_T copied=0;
        if (!ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(data),
                bytes,length,&copied) || copied!=length) return false;
        for (unsigned index=0;index<length;++index)
            snprintf(output.metadata_text_utf8_rawhex+index*2,3,
                "%02x",bytes[index]);
        output.casus_belli_key_readable=declarewar_candidates_ascii_key(
            bytes,length,output.casus_belli_key);
        // The key comes from the CB definition returned by the native
        // metadata getter. Its identity is not limited to the two CB names
        // observed in the first experiment.
        output.casus_belli_key_verified=output.casus_belli_key_readable;
    }
    output.metadata_text_utf8_rawhex[length*2]=0;
    output.metadata_text_bytes_complete=!output.metadata_text_truncated;
    return true;
}

// Reads only fields already used by the UI candidate path.  candidate+0x08 is
// the observed common native discriminator (0x165), while the candidate vtable
// distinguishes the type-specific family.  candidate+0x58 is not read as a
// selection payload; the UI row owns that pointer at row+0x58.
static bool declarewar_candidates_capture_one(uintptr_t candidate,
    unsigned index,DeclareWarCandidateCapture& output) noexcept {
    output=DeclareWarCandidateCapture{};
    output.address=candidate;
    output.candidate_index=index;
    if (!candidate || candidate<0x10000) return false;
    if (!read(candidate,output.vtable)
        || !read(candidate+0x08,output.candidate_discriminator_raw)
        || !read(candidate+0x40,output.metadata)) return false;
    output.readable=true;
    if (output.vtable>=base && output.vtable-base<=0xffffffffull)
        output.vtable_rva=static_cast<uint32_t>(output.vtable-base);
    if (output.vtable_rva==declarewar_candidates_candidate_vtable_rva) {
        if (read(candidate+0x18,output.target_province_id)) {
            output.target_province_id_verified=true;
            output.province_identifier_verified=true;
        }
        if (read(candidate+0x38,output.beneficiary_raw)) {
            output.beneficiary_raw_readable=true;
            output.beneficiary_identifier_verified=
                declarewar_candidates_normalize_beneficiary(
                    output.beneficiary_raw,output.beneficiary_handle);
        }
    }
    output.private_raw_readable=read(candidate,output.private_raw);
    if (!output.metadata || output.metadata<0x10000) return true;

    output.metadata_readable=read(output.metadata+0x10,
        output.metadata_group_raw);
    output.metadata_text_readable=declarewar_candidates_capture_text(
        output.metadata,output);
    return true;
}

static bool declarewar_candidates_holder_pointer(
    const DeclareWarCandidateCallbackHolder& holder,uintptr_t& pointer) noexcept {
    pointer=0;
    memcpy(&pointer,holder.storage+0x38,sizeof(pointer));
    return pointer!=0;
}

// ee6930 invokes the result object's +0x20 method as (object,bool), where the
// bool is true only when the object is not the holder's inline storage.  The
// empty callback holder should stay zero, so this path is normally a no-op.
static bool declarewar_candidates_cleanup_holder(
    DeclareWarCandidateCallbackHolder& holder) noexcept {
    uintptr_t object=0;
    if (!declarewar_candidates_holder_pointer(holder,object)) return true;
    uintptr_t vtable=0,cleanup=0;
    if (object<0x10000 || !read(object,vtable)
        || !read(vtable+0x20,cleanup) || !cleanup) return false;
    using HolderCleanup=void* (*)(void*,bool);
    reinterpret_cast<HolderCleanup>(cleanup)(reinterpret_cast<void*>(object),
        object!=reinterpret_cast<uintptr_t>(holder.storage));
    memset(holder.storage,0,sizeof(holder.storage));
    return true;
}

static bool declarewar_candidates_destroy_one(uintptr_t candidate) noexcept {
    if (!candidate || candidate<0x10000) return true;
    uintptr_t vtable=0,destructor=0;
    if (!read(candidate,vtable) || !read(vtable,destructor) || !destructor)
        return false;
    using CandidateDestructor=void* (*)(void*,unsigned);
    reinterpret_cast<CandidateDestructor>(destructor)(
        reinterpret_cast<void*>(candidate),1);
    return true;
}

// A clone returned by d9a960 is owned by the caller.  Match the native action
// destructor contract: call the object +0x78 presence method first, then call
// vtable +0x00 with flag 1 only when the presence method reports true.
[[maybe_unused]] static bool declarewar_candidates_release_selected_owned(
    uintptr_t owned) noexcept {
    if (!owned || owned<0x10000) return true;
    uintptr_t vtable=0,present=0,destructor=0;
    if (!read(owned,vtable) || !vtable
        || !read(vtable+0x78,present) || !present) return false;
    using OwnedPresent=bool (*)(void*);
    if (!reinterpret_cast<OwnedPresent>(present)(
            reinterpret_cast<void*>(owned))) return true;
    if (!read(vtable,destructor) || !destructor) return false;
    using CandidateDestructor=void* (*)(void*,unsigned);
    reinterpret_cast<CandidateDestructor>(destructor)(
        reinterpret_cast<void*>(owned),1);
    return true;
}

static bool declarewar_candidates_read_empty_sentinel(
    uintptr_t& sentinel) noexcept {
    sentinel=0;
    return read(base+declarewar_candidates_empty_sentinel_global_rva,sentinel)
        && sentinel!=0;
}

static bool declarewar_candidates_selection_match(
    const DeclareWarCandidateSelection& selection,
    const DeclareWarCandidateCapture& item) noexcept {
    if (!selection.casus_belli || !*selection.casus_belli
        || !item.casus_belli_key_verified
        || !item.target_province_id_verified
        || !item.beneficiary_identifier_verified) return false;
    return !strcmp(selection.casus_belli,item.casus_belli_key)
        && selection.province_id==item.target_province_id
        && selection.beneficiary_handle==item.beneficiary_handle;
}

static bool declarewar_candidates_cleanup_vector(
    DeclareWarCandidateNativeVector& vector) noexcept {
    bool complete=true;
    const uintptr_t begin=reinterpret_cast<uintptr_t>(vector.begin);
    const uint32_t count=vector.count;
    if (count>declarewar_candidates_max_native_walk) complete=false;
    const uint32_t walk=count>declarewar_candidates_max_native_walk
        ?declarewar_candidates_max_native_walk:count;
    for (uint32_t index=0;index<walk;++index) {
        uintptr_t candidate=0;
        if (!begin || !read(begin+static_cast<uintptr_t>(index)*8,candidate)) {
            complete=false;
            continue;
        }
        if (!declarewar_candidates_destroy_one(candidate)) complete=false;
    }

    // Match ee6930 exactly: after the element destructor loop, RCX is the
    // begin pointer and the native allocator helper is called directly.
    // Calling an assumed vector-vtable slot here caused the r36-B crash at
    // DLL RVA 0x16372 (the indirect call after reading +0xa0).
    if (begin) {
        using NativeVectorStorageFree=void (*)(void*);
        reinterpret_cast<NativeVectorStorageFree>(base+
            declarewar_candidates_native_free_rva)(
                reinterpret_cast<void*>(begin));
    }
    vector.begin=nullptr;
    vector.capacity=0;
    vector.count=0;
    return complete;
}

// Enumerates at most 64 candidates and captures only stable, directly observed
// fields.  The native vector can contain more entries; all entries up to the
// bounded cleanup walk are destroyed even when the public capture is full.
// When selection is provided, exactly one matching candidate is cloned before
// the native candidates are destroyed.  A zero or ambiguous match is a hard
// selection failure and never clones a candidate.
static bool declarewar_candidates_query(uint64_t actor,uint64_t target,
    DeclareWarCandidateQueryResult& output,
    const DeclareWarCandidateSelection* selection=nullptr) noexcept {
    output=DeclareWarCandidateQueryResult{};
    output.actor=actor;
    output.target=target;
    output.selection_requested=selection!=nullptr;
    if (!base) return false;

    DeclareWarCandidateNativeVector vector{};
    vector.vtable=reinterpret_cast<void*>(base+
        declarewar_candidates_native_vector_vtable_rva);
    DeclareWarCandidateCallbackHolder holder{};
    uintptr_t holder_pointer=0;
    output.callback_holder_empty_before=
        !declarewar_candidates_holder_pointer(holder,holder_pointer);

    using Enumerator=bool (*)(uint64_t,uint64_t,void*,void*);
    output.native_called=true;
    output.native_returned=reinterpret_cast<Enumerator>(base+
        declarewar_candidates_enumerator_rva)(actor,target,&vector,&holder);

    output.native_count=vector.count;
    output.has_candidates=vector.count!=0;
    const uintptr_t native_begin=reinterpret_cast<uintptr_t>(vector.begin);
    output.native_vector_shape_valid=vector.count<=vector.capacity
        && (vector.count==0 || native_begin!=0);
    if (!output.native_vector_shape_valid) output.all_items_readable=false;
    if (vector.count>declarewar_candidates_max_items) output.truncated=true;
    const unsigned capture_count=vector.count<declarewar_candidates_max_items
        ?vector.count:declarewar_candidates_max_items;
    const uintptr_t begin=native_begin;
    for (unsigned index=0;index<capture_count;++index) {
        uintptr_t candidate=0;
        if (!begin || !read(begin+static_cast<uintptr_t>(index)*8,candidate)) {
            output.all_items_readable=false;
            continue;
        }
        DeclareWarCandidateCapture& item=output.items[output.captured_count];
        const bool item_readable=declarewar_candidates_capture_one(
            candidate,index,item);
        ++output.captured_count;
        if (!item_readable || !item.private_raw_readable
            || !item.metadata_readable
            || !item.metadata_text_readable) output.all_items_readable=false;
        if (item.metadata_text_truncated) output.truncated=true;
    }

    uintptr_t selected_candidate=0;
    if (selection) {
        for (unsigned index=0;index<output.captured_count;++index) {
            const DeclareWarCandidateCapture& item=output.items[index];
            if (!declarewar_candidates_selection_match(*selection,item)) continue;
            ++output.selection_match_count;
            if (output.selection_match_count==1) {
                selected_candidate=item.address;
                output.selected_candidate_index=
                    static_cast<int32_t>(item.candidate_index);
            } else {
                selected_candidate=0;
                output.selected_candidate_index=-1;
            }
        }
        if (output.selection_match_count==1 && selected_candidate) {
            uintptr_t empty_sentinel=0;
            if (declarewar_candidates_read_empty_sentinel(empty_sentinel)) {
                output.selection_clone_attempted=true;
                using CandidateClone=void* (*)(void*);
                const uintptr_t clone=reinterpret_cast<uintptr_t>(
                    reinterpret_cast<CandidateClone>(base+
                        declarewar_candidates_clone_rva)(
                            reinterpret_cast<void*>(selected_candidate)));
                if (clone && clone!=empty_sentinel) {
                    output.selected_owned=clone;
                    output.selection_clone_valid=true;
                } else {
                    output.selected_candidate_index=-1;
                }
            }
        }
        if (!output.selection_clone_valid)
            output.selected_candidate_index=-1;
    }

    output.vector_cleanup_ok=declarewar_candidates_cleanup_vector(vector);
    output.callback_holder_empty_after=
        !declarewar_candidates_holder_pointer(holder,holder_pointer);
    if (!output.callback_holder_empty_after) {
        output.callback_holder_cleanup_ok=declarewar_candidates_cleanup_holder(holder);
        output.callback_holder_empty_after=
            !declarewar_candidates_holder_pointer(holder,holder_pointer);
    }
    output.capture_complete=output.native_vector_shape_valid
        && output.all_items_readable && !output.truncated
        && output.captured_count==output.native_count;
    // d9e9b0 returns false for an ordinary empty candidate set.  That raw
    // return remains in native_returned, while capture_complete describes
    // whether the empty (or non-empty) output was read and cleaned safely.
    output.complete=output.native_called && output.capture_complete
        && output.vector_cleanup_ok && output.callback_holder_cleanup_ok
        && output.callback_holder_empty_after
        && (!selection || (output.selection_match_count==1
            && output.selection_clone_valid && output.selected_owned!=0));
    return output.complete;
}

