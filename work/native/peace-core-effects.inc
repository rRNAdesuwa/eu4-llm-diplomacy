// Bounded before/after state readers for Return Core and Revoke Core.
//
// The province record's core vector is a begin/end pair at +0x490/+0x498.
// Each element is one 8-byte country handle.  This reader observes at most
// kMaxProvinceCores entries and never calls a treaty or core mutator.

static bool execution_peace_effects_read_core_vector(uintptr_t record,
    uint64_t target,bool& present) noexcept {
    present=false;
    uintptr_t begin=0,end=0;
    if (!record || !read(record+0x490u,begin) || !read(record+0x498u,end)
        || end<begin) return false;
    if (begin==end) return true;
    if (!begin || ((end-begin)%sizeof(uint64_t))!=0) return false;
    const uint64_t count=(end-begin)/sizeof(uint64_t);
    if (count>bridge::peace_effects::kMaxProvinceCores) return false;
    for (uint64_t index=0;index<count;++index) {
        uint64_t handle=0;
        if (!read(begin+static_cast<uintptr_t>(index*sizeof(uint64_t)),handle))
            return false;
        if (handle==target) present=true;
    }
    return true;
}

static bool execution_peace_effects_read_core_province(std::int32_t id,
    std::uint64_t target,bridge::peace_effects::CoreProvinceState& output) noexcept {
    output=bridge::peace_effects::CoreProvinceState{};
    if (id<=0 || !target) return false;
    PeaceProvinceArrayBounds bounds{};
    uintptr_t record=0,owner=0,controller=0;
    uint64_t owner_handle=0,controller_handle=0;
    if (!peace_province_read_bounds(bounds)
        || !peace_province_record_for_id(bounds,id,record)
        || !read(record+0x468u,owner_handle)
        || !read(record+0x470u,controller_handle)
        || !peace_query_country_pointer(owner_handle,owner)
        || !peace_query_country_pointer(controller_handle,controller)
        || !peace_query_country_pointer(target,owner)) return false;
    bool present=false;
    if (!execution_peace_effects_read_core_vector(record,target,present)) return false;
    output.province_id=id;
    output.target_core_owner=target;
    output.owner=owner_handle;
    output.controller=controller_handle;
    output.core_owner_present=present;
    output.complete=true;
    return true;
}
