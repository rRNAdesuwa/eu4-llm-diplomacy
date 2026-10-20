#ifndef BRIDGE_RELIGION_WAR_CONTEXT_SCRIPT_H
#define BRIDGE_RELIGION_WAR_CONTEXT_SCRIPT_H

// Operator-only, fixed scenario. The engine creates and serializes the war.
// This is not the LLM diplomacy interface and sends no peace proposal.
static const char religion_war_context_script[]=R"EU4REL56(ENG = {
    change_religion = hussite
    capital_scope = { change_religion = hussite }
}
FRA = {
    set_country_flag = war_against_heresy_flag
    declare_war_with_cb = {
        who = ENG
        casus_belli = cb_war_against_heresy
    }
}
)EU4REL56";

// Independent small-country scenario for the same native peace rule.
static const char religion_small_war_context_script[]=R"EU4REL56B(LEI = {
    change_religion = hussite
    capital_scope = { change_religion = hussite }
}
FRA = {
    set_country_flag = war_against_heresy_flag
    declare_war_with_cb = {
        who = LEI
        casus_belli = cb_war_against_heresy
    }
}
)EU4REL56B";

#endif
