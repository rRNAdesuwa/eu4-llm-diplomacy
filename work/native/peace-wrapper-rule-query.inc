// The receiving session invokes wrapper +0x40 before generic execution.
// Reuse that native rule on a private wrapper; never dispatch the wrapper.
struct PeaceWrapperRuleCapture {
    bool identity_verified=false,checked=false,available=false,payload_unchanged=false;
    bool complete() const noexcept {
        return identity_verified && checked && payload_unchanged;
    }
};

static PeaceWrapperRuleCapture peace_wrapper_rule_inspect(void* wrapper) noexcept {
    PeaceWrapperRuleCapture result{};
    const auto before=protocol_capture(wrapper);
    uintptr_t predicate=0;
    if (!before.identity || !before.readable || !before.prefix_readable
        || !before.payload.peace_offer || !before.payload.peace.valid()
        || !read(before.vtable+0x40,predicate) || predicate!=base+0x4e8660) return result;
    result.identity_verified=true;
    result.checked=true;
    result.available=reinterpret_cast<bool (*)(void*)>(predicate)(wrapper);
    const auto after=protocol_capture(wrapper);
    result.payload_unchanged=after.identity && after.readable && after.prefix_readable
        && before.action==after.action && protocol_shape_equal(before.payload,after.payload)
        && before.raw10==after.raw10 && before.raw38==after.raw38
        && before.raw3c==after.raw3c && before.raw40==after.raw40
        && before.raw44==after.raw44 && before.origin48==after.origin48
        && before.flags4a==after.flags4a && before.sequence4c==after.sequence4c;
    return result;
}

static PeaceWrapperRuleCapture peace_wrapper_rule_query(void* action) noexcept {
    PeaceWrapperRuleCapture result{};
    uintptr_t destructor=0;
    if (!lifecycle_wrapper_original
        || !read(base+lifecycle_generic_wrapper_vtable_rva,destructor)
        || destructor<base+0x1000 || destructor>=base+0x1b66000) return result;
    const auto expected=lifecycle_capture_shape(action);
    if (!expected.peace_offer || !expected.peace.valid()) return result;
    void* wrapper=nullptr;
    lifecycle_wrapper_observe(action,&wrapper);
    if (!wrapper) return result;
    const auto wrapped=protocol_capture(wrapper);
    if (wrapped.identity && protocol_shape_equal(expected,wrapped.payload))
        result=peace_wrapper_rule_inspect(wrapper);
    reinterpret_cast<void* (*)(void*,unsigned)>(destructor)(wrapper,1);
    return result;
}
