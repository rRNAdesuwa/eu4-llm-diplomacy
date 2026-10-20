#include "peace-effects.h"
#include <cstdio>
#include <cstring>

using namespace bridge::peace_effects;
static unsigned checks=0,failures=0;
static void check(bool value,const char* name) {
    ++checks;
    if (!value) { ++failures; std::printf("failed:%s\n",name); }
}

static SubjectRelationState relation(std::uint64_t country,std::uint64_t source,
    std::uint64_t beneficiary,bool source_active,bool source_overlord,
    bool beneficiary_active,bool beneficiary_overlord) {
    SubjectRelationState row{};
    row.country=country; row.source=source; row.beneficiary=beneficiary;
    std::snprintf(row.country_tag,sizeof(row.country_tag),"TAG");
    std::snprintf(row.source_tag,sizeof(row.source_tag),"SRC");
    if (beneficiary) {
        std::snprintf(row.beneficiary_tag,sizeof(row.beneficiary_tag),"BEN");
        row.beneficiary_relation_readable=true;
        std::snprintf(row.beneficiary_subject_type,
            sizeof(row.beneficiary_subject_type),"vassal");
    }
    std::snprintf(row.source_subject_type,sizeof(row.source_subject_type),"vassal");
    row.source_relation_active=source_active;
    row.source_is_overlord=source_overlord;
    row.beneficiary_relation_active=beneficiary_active;
    row.beneficiary_is_overlord=beneficiary_overlord;
    row.complete=true;
    return row;
}

int main() {
    State release_before{};
    release_before.complete=true; release_before.date_raw=100;
    release_before.country_count=2;
    release_before.countries[0].country=11;
    release_before.countries[1].country=33;
    release_before.release_subject_requested=true;
    release_before.release_subject.requested=true;
    release_before.release_subject.source=11;
    release_before.release_subject.count=1;
    release_before.release_subject.rows[0]=relation(33,11,0,true,true,false,false);
    release_before.release_subject.complete=true;
    State release_after=release_before;
    release_after.release_subject.rows[0]=relation(33,11,0,false,false,false,false);
    release_after.release_subject.rows[0].source_subject_type[0]=0;
    release_after.release_subject.complete=true;
    check(subject_effect_context_valid(release_before.release_subject),
        "release_before_context");
    check(subject_effect_context_valid(release_after.release_subject),
        "release_after_context");
    check(release_subject_established(release_before,release_after),
        "release_subject_removed_from_overlord");
    check(!subject_effect_exactly_equal(release_before.release_subject,
        release_after.release_subject),"release_changed_relation_not_equal");
    State release_rejected=release_before;
    check(subject_effect_exactly_equal(release_before.release_subject,
        release_rejected.release_subject),"release_rejection_relation_equal");
    check(!release_subject_established(release_before,release_rejected),
        "release_rejection_not_established");

    State transfer_before{};
    transfer_before.complete=true; transfer_before.date_raw=100;
    transfer_before.country_count=3;
    transfer_before.countries[0].country=11;
    transfer_before.countries[1].country=22;
    transfer_before.countries[2].country=33;
    transfer_before.transfer_subject_requested=true;
    transfer_before.transfer_subject.requested=true;
    transfer_before.transfer_subject.source=11;
    transfer_before.transfer_subject.beneficiary=22;
    transfer_before.transfer_subject.count=1;
    transfer_before.transfer_subject.rows[0]=relation(33,11,22,true,true,false,false);
    transfer_before.transfer_subject.complete=true;
    State transfer_after=transfer_before;
    transfer_after.transfer_subject.rows[0]=relation(33,11,22,false,false,true,true);
    std::snprintf(transfer_after.transfer_subject.rows[0].beneficiary_subject_type,
        sizeof(transfer_after.transfer_subject.rows[0].beneficiary_subject_type),
        "appanage");
    check(transfer_subject_established(transfer_before,transfer_after),
        "transfer_moves_subject_to_beneficiary");
    State transfer_rejected=transfer_before;
    check(subject_effect_exactly_equal(transfer_before.transfer_subject,
        transfer_rejected.transfer_subject),"transfer_rejection_relation_equal");
    check(!transfer_subject_established(transfer_before,transfer_rejected),
        "transfer_rejection_not_established");
    auto wrong=transfer_after;
    wrong.transfer_subject.rows[0].beneficiary_is_overlord=false;
    check(!transfer_subject_established(transfer_before,wrong),
        "transfer_beneficiary_subject_endpoint_required");
    auto missing=transfer_after;
    missing.transfer_subject.rows[0].beneficiary_relation_readable=false;
    check(!transfer_subject_established(transfer_before,missing),
        "transfer_beneficiary_relation_readability_required");

    std::printf("{\"passed\":%s,\"checks\":%u,\"failures\":%u,\"native_calls\":false}\n",
        failures?"false":"true",checks,failures);
    return failures?1:0;
}
