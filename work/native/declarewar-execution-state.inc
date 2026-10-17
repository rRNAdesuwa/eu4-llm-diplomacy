// Read the existing country-to-opponent war associations on the game frame.
// This layout is also used by the independent probe_war_pair.py operator.
struct DeclareWarExecutionState {
    bool active=false;
    uint64_t war_object=0;
    int32_t war_id=-1;
    int32_t stability_raw=0;
    bool war_id_verified=false;
    bool stability_verified=false;
};

static bool execution_declarewar_country(uint64_t handle,uintptr_t& country) noexcept {
    uintptr_t database=0,array=0; uint64_t identity=0;
    const unsigned slot=static_cast<unsigned>((handle>>32)&0xffffu);
    return read(base+0x233d8b0,database) && read(database+0x118,array)
        && read(array+static_cast<uintptr_t>(slot)*8,country)
        && read(country+0x20,identity) && identity==handle;
}

static bool execution_declarewar_association(uintptr_t country,unsigned other,
    bool& active,uint64_t& war_object) noexcept {
    uintptr_t entries=0; int32_t count=0; unsigned matches=0;
    active=false; war_object=0;
    if (!read(country+0x1548,entries) || !read(country+0x1554,count)
        || count<0 || count>256 || (count && !entries)) return false;
    for (int32_t i=0;i<count;++i) {
        int32_t slot=-1; uint64_t object=0;
        const uintptr_t entry=entries+static_cast<uintptr_t>(i)*0x10;
        if (!read(entry,slot) || !read(entry+8,object)) return false;
        if (slot==static_cast<int32_t>(other)) {
            if (!object || ++matches>1) return false;
            active=true; war_object=object;
        }
    }
    return true;
}

static bool execution_declarewar_state(uint64_t actor,uint64_t recipient,
    DeclareWarExecutionState& state) noexcept {
    state=DeclareWarExecutionState{};
    uintptr_t left=0,right=0; bool left_active=false,right_active=false;
    uint64_t left_war=0,right_war=0;
    if (!execution_declarewar_country(actor,left) || !execution_declarewar_country(recipient,right)
        || !execution_declarewar_association(left,static_cast<unsigned>((recipient>>32)&0xffffu),left_active,left_war)
        || !execution_declarewar_association(right,static_cast<unsigned>((actor>>32)&0xffffu),right_active,right_war)
        || left_active!=right_active || left_war!=right_war) return false;
    state.active=left_active; state.war_object=left_war;
    return true;
}
