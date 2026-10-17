#include "peace-payload-ref.h"
#include <array>
#include <cstdio>
#include <utility>

using bridge::peace_payload::PeacePayloadRef;
static unsigned checks=0,failures=0;
static void check(bool result,const char* name) {
    ++checks;
    if (!result) { ++failures; std::printf("failed:%s\n",name); }
}
static PeacePayloadRef offer(int amount) {
    auto value=PeacePayloadRef::allocate();
    auto* data=value.builder();
    if (!data) return {};
    data->payer=0x454e47;
    data->claimant=0x465241;
    data->direction=1;
    data->term_count=1;
    auto& gold=data->terms[0];
    gold.type_id=0x2d2b;
    gold.bucket=0;
    gold.selected=1;
    gold.selected_index=0;
    gold.gold_raw=amount;
    gold.complete=true;
    data->complete=true;
    if (!value.seal()) return {};
    return value;
}
int main() {
    PeacePayloadRef empty;
    check(empty.empty() && !empty.valid() && !empty.get(),"empty_has_no_authority");
    auto incomplete=PeacePayloadRef::allocate();
    check(!incomplete.empty() && incomplete.builder() && !incomplete.seal(),
        "incomplete_snapshot_cannot_be_sealed");
    check(!(incomplete==incomplete),"unsealed_identity_is_not_payload_equality");
    PeacePayloadRef unfinished_copy=incomplete;
    check(!incomplete.builder() && !incomplete.seal(),"shared_builder_cannot_mutate");
    unfinished_copy.reset();
    check(incomplete.builder()!=nullptr,"unique_builder_restored_after_release");
    auto first=offer(10000);
    check(first.valid() && first.use_count()==1,"valid_offer_is_owned");
    check(!first.builder() && !first.seal(),"published_offer_is_immutable");
    {
        PeacePayloadRef source=first;
        check(source.use_count()==2 && source==first,"copy_keeps_full_payload");
        PeacePayloadRef target=std::move(source);
        check(source.empty() && target==first && target.use_count()==2,
            "move_transfers_reference");
        target=target;
        check(target.use_count()==2,"self_assignment_preserves_reference_count");
    }
    check(first.use_count()==1,"scope_exit_releases_reference");
    auto same=offer(10000),different=offer(20000);
    check(first==same && first!=different,"equality_compares_values_not_addresses");
    bridge::peace_payload::PeaceActionPayload action{first,1,1,0};
    check(action.valid() && !action.empty(),"action_binds_outer_direction_to_offer");
    auto changed=action;
    changed.direction41=0;
    check(!changed.valid() && changed!=action,"outer_direction_mismatch_is_invalid");
    changed=action;
    changed.preview208=1;
    check(changed.valid() && changed!=action,"preview_flag_is_part_of_identity");
    action={}; changed={};
    std::array<PeacePayloadRef,4> records{};
    for (auto& record:records) record=first;
    check(first.use_count()==5,"ledger_records_share_snapshot");
    records={};
    check(first.use_count()==1,"ledger_reset_releases_snapshot_references");
    same=std::move(different);
    check(different.empty() && same.valid() && same!=first,"move_assignment_replaces_value");
    first.reset();
    check(first.empty() && same.valid(),"independent_snapshot_survives_source_reset");
    std::printf("peace_payload_ref:checks=%u failures=%u handle_bytes=%zu payload_bytes=%zu\n",
        checks,failures,sizeof(PeacePayloadRef),sizeof(bridge::peace_payload::PeaceOfferPayload));
    return failures?1:0;
}
