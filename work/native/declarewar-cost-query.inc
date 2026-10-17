// Read-only Declare War rule/description computation.
//
// This include is deliberately separate from declarewar-query.inc.  The
// including translation unit must declare the query helpers first, so that
// base, read, NativeShortString, DeclareWarQueryHeader and the existing
// bounded string cleanup helper are already declared.  It never creates an
// action, selects a candidate, changes an action, or submits a command.

struct DeclareWarCostQueryResult {
    bool action_header_readable=false;
    bool action_header_unchanged=false;

    // These three functions return the RDX output pointer.  They do not
    // return a native bool.  The *_return_identity flags are therefore the
    // result of the pointer identity check, not a business-rule result.
    bool stability_return_identity=false;
    bool warex_return_identity=false;
    bool primary_return_identity=false;

    bool stability_hit_raw_available=false;
    bool war_exhaustion_raw_available=false;
    bool primary_raw_available=false;
    bool secondary_raw_available=false;

    int32_t stability_hit_raw=0;
    int32_t war_exhaustion_raw=0;
    int32_t primary_raw=0;
    int32_t secondary_raw=0;

    bool text_readable=false;
    bool text_truncated=false;
    char text_hex[1025]{};

    // This helper does not prove a diplomatic-power cost or acceptance.
    bool diplomatic_power_cost_complete=false;
    bool acceptance_complete=false;
};

// Compute the same native display path used by the Declare War dialog.
// capture_secondary=true passes an int32_t* as 50bf00's fifth argument, which
// exposes the additional unrounded display value used by the UI's aggressive
// expansion branch.  false matches ee75f0's fifth-argument-null call shape
// and is the default to keep the primary helper call conservative.
static bool declarewar_cost_query_run(void* action,
    DeclareWarCostQueryResult& out,bool capture_secondary=false) {
    out=DeclareWarCostQueryResult{};
    DeclareWarQueryHeader before{},after{};
    if (!declarewar_query_header(action,before)) return false;
    out.action_header_readable=true;

    NativeShortString text{};
    text.capacity=15;
    int32_t stability=0,warex=0,primary=0,secondary=0;
    using StabilityRule=int32_t* (*)(void*,int32_t*,NativeShortString*,
        unsigned char,int32_t);
    using WarExhaustionRule=int32_t* (*)(void*,int32_t*,NativeShortString*);
    using CostDisplay=int32_t* (*)(void*,int32_t*,NativeShortString*,
        uintptr_t,int32_t*);

    const auto stability_rule=reinterpret_cast<StabilityRule>(base+0x507230);
    const auto warex_rule=reinterpret_cast<WarExhaustionRule>(base+0x506e90);
    const auto cost_display=reinterpret_cast<CostDisplay>(base+0x50bf00);
    out.stability_return_identity=stability_rule(action,&stability,&text,0,2)==&stability;
    if (out.stability_return_identity) {
        out.stability_hit_raw=stability;
        out.stability_hit_raw_available=true;
    }
    out.warex_return_identity=warex_rule(action,&warex,&text)==&warex;
    if (out.warex_return_identity) {
        out.war_exhaustion_raw=warex;
        out.war_exhaustion_raw_available=true;
    }
    out.primary_return_identity=cost_display(action,&primary,&text,0,
        capture_secondary?&secondary:nullptr)==&primary;
    if (out.primary_return_identity) {
        out.primary_raw=primary;
        out.primary_raw_available=true;
        // 50bf00 jumps to its tail before assigning the fifth output when
        // the scaled primary value is below one 1000-unit step.
        if (capture_secondary && primary>=1000) {
            out.secondary_raw=secondary;
            out.secondary_raw_available=true;
        }
    }

    declarewar_query_hex(text,out.text_hex,out.text_readable,out.text_truncated);
    using StringDestroy=void (*)(void*);
    reinterpret_cast<StringDestroy>(base+0x95660)(&text);
    out.action_header_unchanged=declarewar_query_header(action,after)
        && declarewar_query_same_header(before,after);
    return out.action_header_unchanged;
}
