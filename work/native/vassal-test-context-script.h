#ifndef BRIDGE_VASSAL_TEST_CONTEXT_SCRIPT_H
#define BRIDGE_VASSAL_TEST_CONTEXT_SCRIPT_H

// Fixed, test-only context preparation.  The evaluator receives only the
// short file name "llm_vassal2.txt"; the operator writes this exact byte
// sequence to the configured user-data path and the native tick verifies it
// before calling the fixed evaluator.  This script creates no subject and
// never chooses an Offer Vassalization response.
static const char vassal_test_context_script[]=R"EU4VASSAL2(FRA = {
    create_alliance = SAV
    create_alliance = PRO
    create_alliance = GEN
    create_alliance = LEI
    create_alliance = TYR
    create_alliance = ULS
    add_opinion = { who = SAV modifier = r35_test_vassal_opinion }
    add_opinion = { who = PRO modifier = r35_test_vassal_opinion }
    add_opinion = { who = GEN modifier = r35_test_vassal_opinion }
    add_opinion = { who = LEI modifier = r35_test_vassal_opinion }
    add_opinion = { who = TYR modifier = r35_test_vassal_opinion }
    add_opinion = { who = ULS modifier = r35_test_vassal_opinion }
}
SAV = {
    add_opinion = { who = FRA modifier = r35_test_vassal_opinion }
}
PRO = {
    add_opinion = { who = FRA modifier = r35_test_vassal_opinion }
}
GEN = {
    add_opinion = { who = FRA modifier = r35_test_vassal_opinion }
}
LEI = {
    add_opinion = { who = FRA modifier = r35_test_vassal_opinion }
}
TYR = {
    add_opinion = { who = FRA modifier = r35_test_vassal_opinion }
}
ULS = {
    add_opinion = { who = FRA modifier = r35_test_vassal_opinion }
}
)EU4VASSAL2";

static_assert(sizeof(vassal_test_context_script)>1,
    "the fixed Vassalization context script must not be empty");

#endif
