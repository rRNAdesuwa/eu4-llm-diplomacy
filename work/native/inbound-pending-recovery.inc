// Re-register saved native FRA proposals after a process restart. This reads
// the recipient's bounded pending list; it neither creates native proposals
// nor chooses a response. New public ids belong to this observer session.
#ifndef BRIDGE_INBOUND_PENDING_RECOVERY_INC
#define BRIDGE_INBOUND_PENDING_RECOVERY_INC

namespace bridge_alliance_inbound_detail {
static bool inbound_saved_queue_inspected=false;

static bool inbound_saved_shape_supported(const LifecycleActionShape& shape,
    uint64_t recipient) noexcept {
    return shape.readable && shape.matched && shape.handles_canonical
        && !shape.improve_relations && !shape.spy_network && !shape.guarantee
        && !shape.insult && !shape.declare_war
        && (shape.peace_offer ? shape.peace.valid() : shape.peace.empty())
        && shape.extra60==0 && shape.state34==0
        && shape.variant38==1 && shape.proposal3c!=0
        && shape.actor10!=recipient && shape.mirror18==shape.actor10
        && shape.recipient20==recipient;
}

static void inbound_saved_queue_tick() noexcept {
    if (inbound_saved_queue_inspected || !inbound_installed || frame_count<100
        || thread_changed || frame_thread!=GetCurrentThreadId()
        || !control_ready()) return;
    uintptr_t game=0,country=0; uint64_t recipient=0,player=0; int32_t date=0;
    if (!read(base+0x233fe58,game) || !read(game+0x1dd0,date)
        || !read(game+0x1e60,player) || !observation_country_handle(player)
        || !alliance_query_country("FRA",recipient)
        || !inbound_is_fra(recipient,country)) return;
    uintptr_t head=0,tail=0; uint32_t count=0;
    if (!read(country+0x18d8,head) || !read(country+0x18e0,tail)
        || !read(country+0x18e8,count) || count>kQueueCapacity) return;
    // Validate every native link before registering any entry.
    uintptr_t nodes[kQueueCapacity]{},clones[kQueueCapacity]{};
    LifecycleActionShape shapes[kQueueCapacity]{};
    uintptr_t node=head,previous=0;
    if ((count==0 && (head || tail)) || (count && (!head || !tail))) return;
    for (uint32_t index=0;index<count;++index) {
        uintptr_t before=0,next=0,clone=0;
        if (!node || !read(node,clone) || !clone || !read(node+8,before)
            || before!=previous || !read(node+16,next)) return;
        nodes[index]=node; clones[index]=clone;
        shapes[index]=lifecycle_capture_shape(reinterpret_cast<void*>(clone));
        previous=node; node=next;
    }
    if (node || previous!=tail) return;
    inbound_saved_queue_inspected=true;
    unsigned restored_count=0;
    for (uint32_t index=0;index<count;++index) {
        const auto& shape=shapes[index];
        if (!inbound_saved_shape_supported(shape,recipient)) continue;
        bool known=false;
        AcquireSRWLockShared(&inbound_pending_lock);
        for (const auto& record:inbound_pending_records)
            if (record.active && record.node==nodes[index]
                && record.clone==clones[index]) { known=true; break; }
        ReleaseSRWLockShared(&inbound_pending_lock);
        if (known) continue;
        InboundScope scope{};
        scope.country=country;
        scope.peace_offer=shape.peace_offer;
        scope.peace=shape.peace;
        InboundOfferEvent event{};
        event.proposal_id=static_cast<uint64_t>(InterlockedIncrement64(&inbound_sequence));
        event.payload_readable=true; event.decision_country_verified=true;
        event.peace_offer=shape.peace_offer;
        event.peace=shape.peace;
        inbound_pending_record_new(scope,event,nodes[index],clones[index],shape,true);
        InboundPendingView view{};
        char actor[4]{}; inbound_tag(actor,shape.actor10);
        if (!inbound_pending_lookup(event.proposal_id,actor,view)) continue;
        ++restored_count;
        const char* action=shape.peace_offer?"peace_offer":shape.vassalization?"offer_vassalization":
            shape.military_access?"ask_military_access":
            shape.support_independence?"support_independence":
            shape.royal_marriage?"offer_royal_marriage":"offer_alliance";
        const char* family=shape.peace_offer?"peace":shape.vassalization?"vassalization":
            shape.military_access?"military_access":
            shape.support_independence?"support_independence":
            shape.royal_marriage?"royal_marriage":"alliance";
        char peace_json[256]{};
        if (shape.peace_offer)
            lifecycle_peace_payload_json(peace_json,sizeof(peace_json),shape.peace);
        else memcpy(peace_json,"null",5);
        char message[1800];
        snprintf(message,sizeof(message),
            "{\"event\":\"native_diplomacy_inbound_pending_restored\",\"session_id\":\"%lu-%llx\",\"proposal_id\":%llu,\"action_id\":\"%s\",\"family\":\"%s\",\"peace\":%s,\"extra60\":0,\"phase\":\"initiate\",\"actor\":\"%.3s\",\"mirror\":\"%.3s\",\"recipient\":\"FRA\",\"decision_country\":\"FRA\",\"date_raw\":%d,\"date28\":%d,\"date2c\":%d,\"envoy30\":%d,\"state34\":0,\"variant38\":1,\"proposal3c\":%d,\"token3c\":%u,\"created2c\":%d,\"queue_after_count\":%u,\"queue_readable\":true,\"list_integrity\":true,\"new_entry\":false,\"payload_readable\":true,\"decision_country_verified\":true,\"pending_source\":\"native_saved_pending_queue\",\"source_verified\":true,\"call_redirected\":false,\"saved_queue_restored\":true,\"native_queue_membership_verified\":true,\"native_node\":\"0x%llx\",\"native_action\":\"0x%llx\",\"business_result\":\"pending_observed\"}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),
            static_cast<unsigned long long>(observation_creation),
            static_cast<unsigned long long>(event.proposal_id),action,family,peace_json,
            actor,actor,date,shape.date28,shape.date2c,shape.envoy30,
            shape.proposal3c,static_cast<unsigned>(shape.proposal3c),shape.date2c,count,
            static_cast<unsigned long long>(nodes[index]),
            static_cast<unsigned long long>(clones[index]));
        line(message);
    }
    char message[400];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_diplomacy_saved_pending_scan_complete\",\"date_raw\":%d,\"decision_country\":\"FRA\",\"native_queue_count\":%u,\"restored_count\":%u,\"queue_readable\":true,\"list_integrity\":true,\"native_queue_unchanged\":true}\n",
        date,count,restored_count);
    line(message);
}
} // namespace bridge_alliance_inbound_detail
using bridge_alliance_inbound_detail::inbound_saved_queue_tick;
#endif
