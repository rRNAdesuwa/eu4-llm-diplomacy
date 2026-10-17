#ifndef BRIDGE_VASSAL_INBOUND_TEST_CONTEXT_SCRIPT_H
#define BRIDGE_VASSAL_INBOUND_TEST_CONTEXT_SCRIPT_H

// Fixed R35 inbound-context preparation.  The operator writes these exact
// bytes to the short native filename llm_vas_in.txt before the one-shot
// evaluator call.  The script only prepares FRA's development and SAV
// relationship; it never creates a subject or chooses an inbound response.
static const char vassal_inbound_test_context_script[]=R"EU4VASSALIN(FRA = {
    every_owned_province = {
        set_base_tax = 1
        set_base_production = 1
        set_base_manpower = 1
    }
    create_alliance = SAV
    add_opinion = { who = SAV modifier = r35_test_vassal_opinion }
}
SAV = {
    add_opinion = { who = FRA modifier = r35_test_vassal_opinion }
}
)EU4VASSALIN";

static_assert(sizeof(vassal_inbound_test_context_script)>1,
    "the fixed inbound Vassalization context script must not be empty");

#endif
