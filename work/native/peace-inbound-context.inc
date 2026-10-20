// Public meaning of a retained native offer. Authorization still compares the
// entire sealed payload; this view exports identified selected terms only.
// Full-annex derivation is deliberately stricter than ordinary Cede export:
// it needs a complete live native offer snapshot, an exact sealed-payload
// match, an exact selected-Cede owner/beneficiary set, and the native
// all-owned predicate.  A response may instead reuse a preflight proof via
// the typed request pointer; it never infers annexation from post-settlement
// ownership.
struct InboundFullAnnexProof {
    bool live_offer_present=false;
    bool live_snapshot_complete=false;
    bool sealed_snapshot_equal=false;
    bool selected_cede_complete=false;
    bool selected_cede_unique=false;
    bool owner_owned_ids_complete=false;
    bool native_check_called=false;
    bool native_check_result=false;
    bool preflight_proof_reused=false;
    bool request_identity_matches=false;
    bool derived=false;
    std::uint64_t owner=0,beneficiary=0;
    unsigned selected_cede_count=0,owned_count=0;
    char owner_tag[4]{},beneficiary_tag[4]{};
    const char* reason_code="NOT_REQUESTED";
};

static constexpr unsigned kInboundFullAnnexMaxProvinces=512u;

static bool inbound_full_annex_read_owned_ids(std::uint64_t owner,
    std::int32_t (&ids)[kInboundFullAnnexMaxProvinces],unsigned& count) noexcept {
    count=0;
    uintptr_t record=0,begin=0;
    std::int32_t raw_count=-1;
    if (!owner || !peace_query_country_pointer(owner,record)
        || !read(record+0x1338u,begin) || !read(record+0x1344u,raw_count)
        || raw_count<=0 || static_cast<unsigned>(raw_count)>kInboundFullAnnexMaxProvinces
        || !begin) return false;
    count=static_cast<unsigned>(raw_count);
    for (unsigned i=0;i<count;++i) {
        const uintptr_t slot=begin+static_cast<uintptr_t>(i)*sizeof(std::int32_t);
        if (slot<begin || !read(slot,ids[i]) || ids[i]<=0) return false;
        for (unsigned j=0;j<i;++j) if (ids[j]==ids[i]) return false;
    }
    return true;
}

static bool inbound_full_annex_collect_cede_identity(
    const bridge::peace_payload::PeaceOfferPayload& offer,
    InboundFullAnnexProof& proof,
    std::int32_t (&selected_ids)[kInboundFullAnnexMaxProvinces]) noexcept {
    proof.selected_cede_complete=true;
    proof.selected_cede_unique=true;
    proof.selected_cede_count=0;
    for (unsigned i=0;i<offer.term_count;++i) {
        const auto& term=offer.terms[i];
        if (!term.selected || term.type_id!=0x2d25u || term.bucket!=3u) continue;
        uintptr_t owner_record=0;
        if (!term.complete || !term.nested_present || term.nested_id==0
            || term.field10!=offer.payer || term.field18!=offer.claimant
            || !term.field22 || !term.extra30
            || !peace_query_country_pointer(term.field22,owner_record)) {
            proof.selected_cede_complete=false;
            continue;
        }
        // The query above only validates the owner handle.  Validate the
        // beneficiary separately without retaining either native record.
        uintptr_t beneficiary_record=0;
        if (!peace_query_country_pointer(term.extra30,beneficiary_record)) {
            proof.selected_cede_complete=false;
            continue;
        }
        if (!proof.selected_cede_count) {
            proof.owner=term.field22;
            proof.beneficiary=term.extra30;
            const bool tags_readable=peace_province_tag_from_handle(proof.owner,proof.owner_tag)
                && peace_province_tag_from_handle(proof.beneficiary,proof.beneficiary_tag);
            if (!tags_readable || proof.owner==proof.beneficiary)
                proof.selected_cede_unique=false;
        } else if (proof.owner!=term.field22 || proof.beneficiary!=term.extra30) {
            proof.selected_cede_unique=false;
        }
        if (proof.selected_cede_count>=kInboundFullAnnexMaxProvinces) {
            proof.selected_cede_complete=false;
            continue;
        }
        selected_ids[proof.selected_cede_count++]=static_cast<std::int32_t>(term.nested_id);
        for (unsigned j=0;j+1<proof.selected_cede_count;++j)
            if (selected_ids[j]==selected_ids[proof.selected_cede_count-1])
                proof.selected_cede_unique=false;
    }
    proof.selected_cede_complete=proof.selected_cede_complete
        && proof.selected_cede_count>0;
    return proof.selected_cede_complete && proof.selected_cede_unique;
}

static bool inbound_full_annex_exact_ids(
    const std::int32_t (&selected_ids)[kInboundFullAnnexMaxProvinces],unsigned selected_count,
    const std::int32_t (&owned_ids)[kInboundFullAnnexMaxProvinces],unsigned owned_count) noexcept {
    if (!selected_count || selected_count!=owned_count) return false;
    for (unsigned i=0;i<selected_count;++i) {
        bool found=false;
        for (unsigned j=0;j<owned_count;++j) if (selected_ids[i]==owned_ids[j]) { found=true; break; }
        if (!found) return false;
    }
    return true;
}

static bool inbound_full_annex_set_request(
    bridge::peace_execution_wire::PeaceExecutionRequest& request,
    const InboundFullAnnexProof& proof) noexcept {
    if (!proof.owner_tag[0] || !proof.beneficiary_tag[0]
        || proof.owner==proof.beneficiary) return false;
    request.selected_full_annexation=true;
    request.full_annexation=true;
    std::memcpy(request.annex_country,proof.owner_tag,sizeof(request.annex_country));
    std::memcpy(request.annex_beneficiary,proof.beneficiary_tag,
        sizeof(request.annex_beneficiary));
    return true;
}

static bool inbound_full_annex_prepare(
    const bridge::peace_payload::PeaceOfferPayload& sealed,
    const void* live_offer,
    const bridge::peace_execution_wire::PeaceExecutionRequest* proven_request,
    bridge::peace_execution_wire::PeaceExecutionRequest& request,
    InboundFullAnnexProof& proof) noexcept {
    proof=InboundFullAnnexProof{};
    std::int32_t selected_ids[kInboundFullAnnexMaxProvinces]{};
    const bool cede_identity=inbound_full_annex_collect_cede_identity(
        sealed,proof,selected_ids);
    if (!cede_identity) {
        proof.reason_code=proof.selected_cede_count
            ?"SELECTED_CEDE_IDENTITY_INCOMPLETE":"NO_SELECTED_CEDE";
        return false;
    }
    bridge::peace_payload::PeacePayloadRef live_snapshot{};
    if (live_offer) {
        proof.live_offer_present=true;
        proof.live_snapshot_complete=peace_capture_offer_snapshot(live_offer,live_snapshot)
            && live_snapshot.valid();
        const auto* live=live_snapshot.get();
        proof.sealed_snapshot_equal=proof.live_snapshot_complete && live && *live==sealed;
    }
    if (proven_request) {
        proof.preflight_proof_reused=proven_request->selected_full_annexation;
        if (!proof.preflight_proof_reused) {
            proof.reason_code="PROVEN_REQUEST_HAS_NO_FULL_ANNEX";
            return false;
        }
        // The caller supplies the same sealed binding payload and the
        // request derived before the native response. Settlement can free
        // the live action and changes the owned list, so neither is read
        // again here. All selected Cede identities were checked above.
        proof.request_identity_matches=sealed.valid()
            && proof.selected_cede_complete && proof.selected_cede_unique
            && !std::strcmp(proven_request->annex_country,proof.owner_tag)
            && !std::strcmp(proven_request->annex_beneficiary,proof.beneficiary_tag);
        if (!proof.request_identity_matches) {
            proof.reason_code="PREFLIGHT_FULL_ANNEX_IDENTITY_MISMATCH";
            return false;
        }
        if (!inbound_full_annex_set_request(request,proof)) {
            proof.reason_code="PREFLIGHT_FULL_ANNEX_REQUEST_INVALID";
            return false;
        }
        proof.derived=true;
        proof.reason_code="PREFLIGHT_PROOF_REUSED";
        return true;
    }
    if (!proof.live_snapshot_complete || !proof.sealed_snapshot_equal) {
        proof.reason_code=proof.live_offer_present
            ?"LIVE_OFFER_SNAPSHOT_MISMATCH":"LIVE_OFFER_UNAVAILABLE";
        return false;
    }
    std::int32_t owned_ids[kInboundFullAnnexMaxProvinces]{};
    if (!inbound_full_annex_read_owned_ids(proof.owner,owned_ids,proof.owned_count)
        || !inbound_full_annex_exact_ids(selected_ids,proof.selected_cede_count,
            owned_ids,proof.owned_count)) {
        proof.reason_code="SELECTED_CEDE_NOT_EXACT_OWNER_OWNED_SET";
        return false;
    }
    proof.owner_owned_ids_complete=true;
    std::uint64_t native_output=0x2d2d2dull;
    using NativeCheck=bool (*)(void*,std::uint64_t,std::uint64_t*);
    proof.native_check_called=true;
    proof.native_check_result=reinterpret_cast<NativeCheck>(base+0x982050u)(
        const_cast<void*>(live_offer),proof.owner,&native_output);
    if (!proof.native_check_result) {
        proof.reason_code="NATIVE_FULL_ANNEX_PREDICATE_FALSE";
        return false;
    }
    if (!inbound_full_annex_set_request(request,proof)) {
        proof.reason_code="FULL_ANNEX_REQUEST_INVALID";
        return false;
    }
    proof.derived=true;
    proof.reason_code="LIVE_NATIVE_FULL_ANNEX_PROVEN";
    return true;
}

struct InboundPeaceContext {
    char json[6000]{};
    char war_id[30]{};
    unsigned term_count=0,selected_count=0;
    bool payload_complete=false,selected_complete=false,complete=false,white=false;
    // Consequence capture for an inbound offer.  request_id/date_raw are
    // intentionally left for the response binding to fill; actor/recipient
    // remain the original proposal endpoints even when FRA answers it.
    bridge::peace_execution_wire::PeaceExecutionRequest effect_request{};
    bool effects_supported=false;
    InboundFullAnnexProof full_annex_proof{};
};

static bool execution_peace_pending_war_id(const AlliancePayload& payload,
    char (&war_id)[30]) noexcept {
    uintptr_t actor=0,recipient=0;
    PeaceWarReferenceList left{},right{};
    if (!peace_query_country_pointer(payload.actor10,actor)
        || !peace_query_country_pointer(payload.recipient20,recipient)
        || !peace_query_pair_references(actor,static_cast<unsigned>((payload.recipient20>>32)&0xffffu),left)
        || !peace_query_pair_references(recipient,static_cast<unsigned>((payload.actor10>>32)&0xffffu),right)
        || !peace_query_reference_sets_equal(left,right) || left.count!=1) return false;
    const auto* entry=peace_query_register_war(left.references[0]);
    if (!entry) return false;
    std::memcpy(war_id,entry->public_id,sizeof(war_id));
    return true;
}

static InboundPeaceContext execution_peace_inbound_context(const AlliancePayload& payload,
    const char* known_war_id=nullptr,const void* live_offer=nullptr,
    const bridge::peace_execution_wire::PeaceExecutionRequest* proven_request=nullptr) noexcept {
    InboundPeaceContext result{};
    const auto* offer=payload.peace.offer.get();
    result.payload_complete=payload.family==ActionFamily::peace && payload.peace.valid();
    if (!result.payload_complete || !offer) { strcpy(result.json,"null"); return result; }
    result.term_count=offer->term_count;
    if (known_war_id && known_war_id[0])
        snprintf(result.war_id,sizeof(result.war_id),"%.29s",known_war_id);
    else execution_peace_pending_war_id(payload,result.war_id);
    char proposer[4]{},recipient[4]{};
    const bool endpoints=peace_province_tag_from_handle(payload.actor10,proposer)
        && peace_province_tag_from_handle(payload.recipient20,recipient);
    if (endpoints) {
        std::memcpy(result.effect_request.actor,proposer,sizeof(result.effect_request.actor));
        std::memcpy(result.effect_request.recipient,recipient,sizeof(result.effect_request.recipient));
    }
    const bool direction_valid=offer->direction<=1
        && payload.peace.direction41==offer->direction;
    result.effect_request.demand_direction=offer->direction==1;
    if (direction_valid)
        snprintf(result.effect_request.direction,sizeof(result.effect_request.direction),
            "%s",offer->direction==1?"demand":"offer");
    if (result.war_id[0])
        snprintf(result.effect_request.war_id,sizeof(result.effect_request.war_id),
            "%.29s",result.war_id);
    char terms[4800]{}; size_t used=0; unsigned exported=0;
    bool understood=true;
    bool effects_supported=endpoints && result.war_id[0] && direction_valid;
    bool reparations_seen=false,trade_power_seen=false,concede_seen=false,money_seen=false;
    bool return_core_seen=false,revoke_core_seen=false;
    bool release_nation_seen=false,force_vassal_seen=false;
    bool personal_union_seen=false,grant_independence_seen=false;
    bool special_seen[3]{};
    const uint64_t expected_payer=offer->direction==1?payload.recipient20:payload.actor10;
    const uint64_t expected_claimant=offer->direction==1?payload.actor10:payload.recipient20;
    const bool offer_roles=direction_valid && offer->payer==expected_payer
        && offer->claimant==expected_claimant;
    char payer_tag[4]{},claimant_tag[4]{};
    const bool role_tags=peace_province_tag_from_handle(offer->payer,payer_tag)
        && peace_province_tag_from_handle(offer->claimant,claimant_tag);
    const bool full_annex_derived=inbound_full_annex_prepare(*offer,live_offer,
        proven_request,result.effect_request,result.full_annex_proof);
    if (proven_request && proven_request->selected_full_annexation
        && !full_annex_derived) {
        // A settlement carrying a preflight Full Annex proof must still bind
        // to the same sealed selected-Cede owner/beneficiary identity.
        understood=false;
        effects_supported=false;
    }
    for (unsigned i=0;i<offer->term_count;++i) {
        const auto& term=offer->terms[i];
        if (!term.selected) continue;
        ++result.selected_count;
        char item[256]{};
        if (term.type_id==0x2d2b && term.bucket==0 && term.gold_raw>=0) {
            // A selected zero-gold term is the native empty/white offer.
            if (!term.gold_raw) continue;
            result.effect_request.selected_amount=true;
            result.effect_request.demand_ducats=true;
            if (!money_seen) {
                money_seen=true;
                result.effect_request.amount_raw=term.gold_raw;
            } else if (result.effect_request.amount_raw!=term.gold_raw) {
                effects_supported=false;
            }
            snprintf(item,sizeof(item),"{\"action_id\":\"demand_ducats\",\"amount_raw\":%d,\"scale\":1000}",term.gold_raw);
        } else if (term.type_id==0x2d25 && term.bucket==3 && term.nested_present) {
            if (full_annex_derived) continue;
            char beneficiary[4]{};
            if (!peace_province_tag_from_handle(term.extra30,beneficiary)) {
                understood=false; effects_supported=false; continue;
            }
            result.effect_request.selected_provinces=true;
            result.effect_request.cede_province=true;
            if (!result.effect_request.selected_beneficiary) {
                std::memcpy(result.effect_request.beneficiary,beneficiary,
                    sizeof(result.effect_request.beneficiary));
                result.effect_request.selected_beneficiary=true;
            } else if (std::strcmp(result.effect_request.beneficiary,beneficiary)!=0) {
                effects_supported=false;
            }
            if (result.effect_request.province_count>=
                bridge::peace_execution_wire::kMaxProvinceIds) {
                effects_supported=false;
            } else {
                result.effect_request.province_ids[result.effect_request.province_count++]=
                    static_cast<std::int32_t>(term.nested_id);
            }
            snprintf(item,sizeof(item),"{\"action_id\":\"cede_province\",\"province_id\":%u,\"beneficiary\":\"%.3s\"}",term.nested_id,beneficiary);
        } else if (term.type_id==0x30a0 && term.bucket==7) {
            result.effect_request.selected_reparations=true;
            result.effect_request.war_reparations=true;
            const bool fields_match=term.field10==offer->payer
                && term.field18==offer->claimant && term.field22==offer->payer;
            const bool roles_match=fields_match && offer_roles && endpoints;
            if (!roles_match) {
                understood=false; effects_supported=false; continue;
            }
            snprintf(item,sizeof(item),
                "{\"action_id\":\"war_reparations\",\"payer\":\"%.3s\",\"claimant\":\"%.3s\"}",
                offer->direction==1?recipient:proposer,
                offer->direction==1?proposer:recipient);
            if (reparations_seen) {
                // Keep the duplicate visible in the semantic JSON, but never
                // expose it as a supported single-R consequence request.
                understood=false; effects_supported=false;
            } else reparations_seen=true;
        } else if (term.type_id==0x2e07 && term.bucket==8) {
            result.effect_request.selected_trade_power=true;
            result.effect_request.transfer_trade_power=true;
            char trade_source[4]{},trade_beneficiary[4]{};
            const bool fields_match=term.field10==offer->payer
                && term.field18==offer->claimant && term.field22!=offer->claimant
                && peace_base_term_source_tag(term.field22,trade_source)
                && peace_base_term_source_tag(term.field18,trade_beneficiary);
            const bool roles_match=fields_match && offer_roles && endpoints;
            if (!roles_match) {
                understood=false; effects_supported=false; continue;
            }
            snprintf(item,sizeof(item),
                "{\"action_id\":\"transfer_trade_power\",\"source\":\"%.3s\",\"beneficiary\":\"%.3s\"}",
                trade_source,trade_beneficiary);
            memcpy(result.effect_request.trade_power_source,trade_source,sizeof(trade_source));
            memcpy(result.effect_request.trade_power_beneficiary,trade_beneficiary,sizeof(trade_beneficiary));
            if (trade_power_seen) {
                // Keep the duplicate visible in the semantic JSON, but never
                // expose it as a supported single-trade-power consequence request.
                understood=false; effects_supported=false;
            } else trade_power_seen=true;
        } else if (term.type_id==0x2d27u && term.bucket==0x13u) {
            char country[4]{};
            const bool roles_match=term.complete && offer_roles && endpoints
                && term.field10==offer->payer && term.field18==offer->claimant
                && term.extra30 && peace_base_term_source_tag(term.extra30,country);
            if (!roles_match || result.effect_request.release_subject_count
                >= bridge::peace_execution_wire::kMaxSubjectCountries) {
                understood=false; effects_supported=false; continue;
            }
            bool duplicate=false;
            for (unsigned j=0;j<result.effect_request.release_subject_count;++j)
                if (!strcmp(result.effect_request.release_subject_countries[j],country)) duplicate=true;
            if (duplicate) { understood=false; effects_supported=false; continue; }
            memcpy(result.effect_request.release_subject_countries[
                result.effect_request.release_subject_count++],country,4);
            result.effect_request.selected_release_subject=true;
            result.effect_request.release_subject=true;
            snprintf(item,sizeof(item),
                "{\"action_id\":\"release_subject\",\"country\":\"%.3s\"}",country);
        } else if (term.type_id==0x35f0u && term.bucket==0x14u) {
            char country[4]{};
            const bool roles_match=term.complete && offer_roles && endpoints
                && term.field10==offer->payer && term.field18==offer->claimant
                && term.field22 && peace_base_term_source_tag(term.field22,country);
            if (!roles_match || result.effect_request.transfer_subject_count
                >= bridge::peace_execution_wire::kMaxSubjectCountries) {
                understood=false; effects_supported=false; continue;
            }
            bool duplicate=false;
            for (unsigned j=0;j<result.effect_request.transfer_subject_count;++j)
                if (!strcmp(result.effect_request.transfer_subject_countries[j],country)) duplicate=true;
            if (duplicate) { understood=false; effects_supported=false; continue; }
            memcpy(result.effect_request.transfer_subject_countries[
                result.effect_request.transfer_subject_count++],country,4);
            result.effect_request.selected_transfer_subject=true;
            result.effect_request.transfer_subject=true;
            snprintf(item,sizeof(item),
                "{\"action_id\":\"transfer_subject\",\"country\":\"%.3s\"}",country);
        } else if ((term.type_id==0x30a3u && term.bucket==9u)
            || (term.type_id==0x2f20u && term.bucket==10u)
            || (term.type_id==0x2d29u && term.bucket==21u)) {
            const unsigned kind=term.type_id==0x30a3u?0u:term.type_id==0x2f20u?1u:2u;
            const bool roles_match=term.complete && offer_roles && endpoints
                && term.field10==offer->payer && term.field18==offer->claimant
                && term.field22==offer->payer;
            if (!roles_match || special_seen[kind]) { understood=false; effects_supported=false; continue; }
            special_seen[kind]=true;
            auto& request=result.effect_request;
            if (kind==0) {request.selected_humiliate_rival=true;request.humiliate_rival=true;}
            else if (kind==1) {request.selected_show_strength=true;request.show_strength=true;}
            else {request.selected_force_religion=true;request.force_religion=true;}
            static constexpr const char* names[]={"humiliate_rival","show_strength","force_religion"};
            snprintf(item,sizeof(item),
                "{\"action_id\":\"%s\",\"country\":\"%.3s\",\"beneficiary\":\"%.3s\"}",
                names[kind],offer->direction==1?recipient:proposer,offer->direction==1?proposer:recipient);
        } else if (term.type_id==0x2d28u && term.bucket==0x0fu) {
            char source[4]{},country[4]{};
            const bool roles_match=term.complete && offer_roles && endpoints && role_tags
                && term.field10==offer->payer && term.field18==offer->claimant
                && peace_base_term_source_tag(term.field22,source)
                && peace_base_term_source_tag(term.extra30,country)
                && std::strcmp(source,country)!=0;
            if (!roles_match || release_nation_seen) {
                understood=false; effects_supported=false; continue;
            }
            release_nation_seen=true;
            auto& request=result.effect_request;
            request.selected_release_nation=true;
            request.release_nation=true;
            std::memcpy(request.release_nation_country,country,sizeof(country));
            std::memcpy(request.release_nation_source,source,sizeof(source));
            snprintf(item,sizeof(item),
                "{\"action_id\":\"release_nation\",\"country\":\"%.3s\",\"source\":\"%.3s\"}",
                country,source);
        } else if ((term.type_id==0x2d2cu && term.bucket==0x01u)
            || (term.type_id==0x3c05u && term.bucket==0x02u)) {
            char country[4]{};
            const bool roles_match=term.complete && offer_roles && endpoints && role_tags
                && term.field10==offer->payer && term.field18==offer->claimant
                && peace_base_term_source_tag(term.field22,country);
            if (!roles_match || force_vassal_seen) {
                understood=false; effects_supported=false; continue;
            }
            force_vassal_seen=true;
            auto& request=result.effect_request;
            request.selected_force_vassalization=true;
            request.force_vassalization=true;
            std::memcpy(request.vassal_country,country,sizeof(country));
            // The second country-like field is an opaque native term field.
            // The public beneficiary is always the sealed offer claimant.
            std::memcpy(request.vassal_beneficiary,claimant_tag,sizeof(claimant_tag));
            snprintf(item,sizeof(item),
                "{\"action_id\":\"force_vassalization\",\"country\":\"%.3s\",\"beneficiary\":\"%.3s\"}",
                country,claimant_tag);
        } else if (term.type_id==0x2d2au && term.bucket==0x1au) {
            char country[4]{};
            const bool roles_match=term.complete && offer_roles && endpoints && role_tags
                && term.field10==offer->payer && term.field18==offer->claimant
                && peace_base_term_source_tag(term.field22,country);
            if (!roles_match || personal_union_seen) {
                understood=false; effects_supported=false; continue;
            }
            personal_union_seen=true;
            auto& request=result.effect_request;
            request.selected_form_personal_union=true;
            request.form_personal_union=true;
            std::memcpy(request.union_country,country,sizeof(country));
            std::memcpy(request.union_beneficiary,claimant_tag,sizeof(claimant_tag));
            snprintf(item,sizeof(item),
                "{\"action_id\":\"form_personal_union\",\"country\":\"%.3s\",\"beneficiary\":\"%.3s\"}",
                country,claimant_tag);
        } else if (term.type_id==0x2e4au && term.bucket==0x12u) {
            const bool roles_match=term.complete && offer_roles && endpoints && role_tags
                && term.field10==offer->payer && term.field18==offer->claimant
                && term.field22==offer->payer;
            if (!roles_match || grant_independence_seen) {
                understood=false; effects_supported=false; continue;
            }
            grant_independence_seen=true;
            auto& request=result.effect_request;
            request.selected_grant_independence=true;
            request.grant_independence=true;
            // Grant has no public country argument.  Keep the native payer
            // identity internally for the effect/context contract.
            std::memcpy(request.independence_country,payer_tag,sizeof(payer_tag));
            snprintf(item,sizeof(item),"{\"action_id\":\"grant_independence\"}");
        } else if (term.type_id==0x2d2du && term.bucket==0x0bu) {
            const bool roles_match=term.complete && offer_roles && endpoints
                && term.field10==offer->payer && term.field18==offer->claimant
                && term.field22==offer->payer;
            if (!roles_match) { understood=false; effects_supported=false; continue; }
            result.effect_request.selected_concede_defeat=true;
            result.effect_request.concede_defeat=true;
            snprintf(item,sizeof(item),
                "{\"action_id\":\"concede_defeat\",\"conceding_country\":\"%.3s\",\"beneficiary\":\"%.3s\"}",
                offer->direction==1?recipient:proposer,offer->direction==1?proposer:recipient);
            if (concede_seen) { understood=false; effects_supported=false; }
            else concede_seen=true;
        } else if (term.type_id==0x2d2eu && term.bucket==0x0eu) {
            char country[4]{},partner[4]{};
            const bool roles_match=term.complete && offer_roles && endpoints
                && term.field10==offer->payer && term.field18==offer->claimant
                && term.field22!=term.extra30
                && peace_base_term_source_tag(term.field22,country)
                && peace_base_term_source_tag(term.extra30,partner);
            if (!roles_match) {understood=false;effects_supported=false;continue;}
            auto& request=result.effect_request;
            if (!request.selected_annul_treaties) memcpy(request.annul_country,country,4);
            else if (strcmp(request.annul_country,country)) {
                understood=false;effects_supported=false;continue;
            }
            request.selected_annul_treaties=true;request.annul_treaties=true;
            if (request.annul_partner_count>=bridge::peace_execution_wire::kMaxAnnulPartners) {
                understood=false;effects_supported=false;continue;
            }
            bool duplicate=false;
            for (unsigned j=0;j<request.annul_partner_count;++j)
                if (!strcmp(request.annul_partners[j],partner)) duplicate=true;
            if (duplicate) {understood=false;effects_supported=false;continue;}
            unsigned position=request.annul_partner_count++;
            while (position && strcmp(request.annul_partners[position-1],partner)>0) {
                memcpy(request.annul_partners[position],request.annul_partners[position-1],4);--position;
            }
            memcpy(request.annul_partners[position],partner,4);
            continue;
        } else if (term.type_id==0x2e00u && term.bucket==5u
            && term.nested_present) {
            char core_owner[4]{};
            auto& request=result.effect_request;
            bool duplicate=false;
            for (unsigned i=0;i<request.return_core_count;++i)
                if (request.return_core_ids[i]==static_cast<std::int32_t>(term.nested_id))
                    duplicate=true;
            const bool roles_match=term.complete && offer_roles && endpoints
                && term.field10==offer->payer && term.field18==offer->claimant
                && term.field22==offer->payer && term.extra30
                && peace_base_term_source_tag(term.extra30,core_owner)
                && term.nested_id>0 && !duplicate
                && (!return_core_seen || std::memcmp(request.return_core_owner,core_owner,3)==0)
                && request.return_core_count<bridge::peace_execution_wire::kMaxProvinceIds;
            if (!roles_match) {
                understood=false; effects_supported=false; continue;
            }
            return_core_seen=true;
            request.selected_return_core=true;
            request.return_core=true;
            memcpy(request.return_core_owner,core_owner,sizeof(core_owner));
            request.return_core_ids[request.return_core_count++]=
                static_cast<std::int32_t>(term.nested_id);
            snprintf(item,sizeof(item),
                "{\"action_id\":\"return_core\",\"province_id\":%u,\"core_owner\":\"%.3s\"}",
                term.nested_id,core_owner);
        } else if (term.type_id==0x2d26u && term.bucket==4u
            && term.nested_present) {
            char core_owner[4]{};
            auto& request=result.effect_request;
            bool duplicate=false;
            for (unsigned i=0;i<request.revoke_core_count;++i)
                if (request.revoke_core_ids[i]==static_cast<std::int32_t>(term.nested_id))
                    duplicate=true;
            const bool roles_match=term.complete && offer_roles && endpoints
                && term.field10==offer->payer && term.field18==offer->claimant
                && term.field22 && term.extra30 && term.field22!=term.extra30
                && peace_base_term_source_tag(term.field22,core_owner)
                && term.nested_id>0 && !duplicate
                && (!revoke_core_seen || std::memcmp(request.revoke_core_owner,core_owner,3)==0)
                && request.revoke_core_count<bridge::peace_execution_wire::kMaxProvinceIds;
            if (!roles_match) {
                understood=false; effects_supported=false; continue;
            }
            revoke_core_seen=true;
            request.selected_revoke_core=true;
            request.revoke_core=true;
            memcpy(request.revoke_core_owner,core_owner,sizeof(core_owner));
            request.revoke_core_ids[request.revoke_core_count++]=
                static_cast<std::int32_t>(term.nested_id);
            snprintf(item,sizeof(item),
                "{\"action_id\":\"revoke_core\",\"province_id\":%u,\"core_owner\":\"%.3s\"}",
                term.nested_id,core_owner);
        } else { understood=false; effects_supported=false; continue; }
        const int written=snprintf(terms+used,sizeof(terms)-used,"%s%s",exported?",":"",item);
        if (written<0 || static_cast<size_t>(written)>=sizeof(terms)-used) {
            understood=false; effects_supported=false; break;
        }
        used+=static_cast<size_t>(written); ++exported;
    }
    if (full_annex_derived) {
        char item[256]{};
        snprintf(item,sizeof(item),
            "{\"action_id\":\"full_annexation\",\"country\":\"%.3s\",\"beneficiary\":\"%.3s\"}",
            result.effect_request.annex_country,result.effect_request.annex_beneficiary);
        const int written=snprintf(terms+used,sizeof(terms)-used,"%s%s",
            exported?",":"",item);
        if (written<0 || static_cast<size_t>(written)>=sizeof(terms)-used) {
            understood=false; effects_supported=false;
        } else {
            used+=static_cast<size_t>(written); ++exported;
        }
    }
    if (result.effect_request.selected_annul_treaties) {
        char partners[128]{},item[320]{};size_t partner_used=0;
        for (unsigned i=0;i<result.effect_request.annul_partner_count;++i) {
            const int n=snprintf(partners+partner_used,sizeof(partners)-partner_used,
                "%s\"%.3s\"",i?",":"",result.effect_request.annul_partners[i]);
            if (n<0 || static_cast<size_t>(n)>=sizeof(partners)-partner_used) {understood=false;effects_supported=false;break;}
            partner_used+=static_cast<size_t>(n);
        }
        snprintf(item,sizeof(item),"{\"action_id\":\"annul_treaties\",\"country\":\"%.3s\",\"treaty_partners\":[%s]}",
            result.effect_request.annul_country,partners);
        const int written=snprintf(terms+used,sizeof(terms)-used,"%s%s",exported?",":"",item);
        if (written<0 || static_cast<size_t>(written)>=sizeof(terms)-used) {understood=false;effects_supported=false;}
        else {used+=static_cast<size_t>(written);++exported;}
    }
    for (unsigned i=1;i<result.effect_request.release_subject_count;++i) {
        char tag[4]{}; memcpy(tag,result.effect_request.release_subject_countries[i],4);
        unsigned j=i;
        while (j && strcmp(result.effect_request.release_subject_countries[j-1],tag)>0) {
            memcpy(result.effect_request.release_subject_countries[j],
                result.effect_request.release_subject_countries[j-1],4); --j;
        }
        memcpy(result.effect_request.release_subject_countries[j],tag,4);
    }
    for (unsigned i=1;i<result.effect_request.transfer_subject_count;++i) {
        char tag[4]{}; memcpy(tag,result.effect_request.transfer_subject_countries[i],4);
        unsigned j=i;
        while (j && strcmp(result.effect_request.transfer_subject_countries[j-1],tag)>0) {
            memcpy(result.effect_request.transfer_subject_countries[j],
                result.effect_request.transfer_subject_countries[j-1],4); --j;
        }
        memcpy(result.effect_request.transfer_subject_countries[j],tag,4);
    }
    for (unsigned i=0;i<result.effect_request.release_subject_count;++i)
        for (unsigned j=0;j<result.effect_request.transfer_subject_count;++j)
            if (!strcmp(result.effect_request.release_subject_countries[i],
                result.effect_request.transfer_subject_countries[j])) {
                understood=false; effects_supported=false;
            }
    if (result.effect_request.selected_amount) result.effect_request.demand_ducats=true;
    if (result.effect_request.selected_provinces) result.effect_request.cede_province=true;
    if (result.effect_request.selected_reparations) result.effect_request.war_reparations=true;
    if (result.effect_request.selected_trade_power) result.effect_request.transfer_trade_power=true;
    size_t mask_used=0;
    if (result.effect_request.selected_amount)
        result.effect_request.term_mask[mask_used++]='m';
    if (result.effect_request.selected_provinces)
        result.effect_request.term_mask[mask_used++]='p';
    if (result.effect_request.selected_reparations)
        result.effect_request.term_mask[mask_used++]='r';
    if (result.effect_request.selected_trade_power)
        result.effect_request.term_mask[mask_used++]='t';
    if (result.effect_request.selected_concede_defeat)
        result.effect_request.term_mask[mask_used++]='c';
    if (result.effect_request.selected_annul_treaties)
        result.effect_request.term_mask[mask_used++]='a';
    if (result.effect_request.selected_humiliate_rival) result.effect_request.term_mask[mask_used++]='h';
    if (result.effect_request.selected_show_strength) result.effect_request.term_mask[mask_used++]='s';
    if (result.effect_request.selected_force_religion) result.effect_request.term_mask[mask_used++]='f';
    if (result.effect_request.selected_return_core) result.effect_request.term_mask[mask_used++]='b';
    if (result.effect_request.selected_revoke_core) result.effect_request.term_mask[mask_used++]='v';
    if (result.effect_request.selected_release_subject) result.effect_request.term_mask[mask_used++]='l';
    if (result.effect_request.selected_transfer_subject) result.effect_request.term_mask[mask_used++]='x';
    result.effect_request.term_mask[mask_used]=0;
    // Keep the legacy 13-bit term_mask ABI unchanged.  The appended country
    // mask carries that same canonical prefix plus country-object flags.  The
    // e bit is emitted only after the typed live/preflight proof above; when
    // that proof is unavailable, selected Cede rows remain physical province
    // terms.
    size_t country_mask_used=mask_used;
    std::memcpy(result.effect_request.country_term_mask,
        result.effect_request.term_mask,country_mask_used);
    if (result.effect_request.selected_release_nation)
        result.effect_request.country_term_mask[country_mask_used++]='n';
    if (result.effect_request.selected_force_vassalization)
        result.effect_request.country_term_mask[country_mask_used++]='z';
    if (result.effect_request.selected_form_personal_union)
        result.effect_request.country_term_mask[country_mask_used++]='u';
    if (result.effect_request.selected_grant_independence)
        result.effect_request.country_term_mask[country_mask_used++]='i';
    if (result.effect_request.selected_full_annexation)
        result.effect_request.country_term_mask[country_mask_used++]='e';
    result.effect_request.country_term_mask[country_mask_used]=0;
    result.selected_complete=understood;
    result.white=understood && exported==0;
    if (result.effect_request.selected_full_annexation)
        snprintf(result.effect_request.action_id,sizeof(result.effect_request.action_id),
            "%s","full_annexation");
    else if (result.effect_request.selected_release_nation)
        snprintf(result.effect_request.action_id,sizeof(result.effect_request.action_id),
            "%s","release_nation");
    else if (result.effect_request.selected_force_vassalization)
        snprintf(result.effect_request.action_id,sizeof(result.effect_request.action_id),
            "%s","force_vassalization");
    else if (result.effect_request.selected_form_personal_union)
        snprintf(result.effect_request.action_id,sizeof(result.effect_request.action_id),
            "%s","form_personal_union");
    else if (result.effect_request.selected_grant_independence)
        snprintf(result.effect_request.action_id,sizeof(result.effect_request.action_id),
            "%s","grant_independence");
    else if (result.effect_request.selected_transfer_subject)
        snprintf(result.effect_request.action_id,sizeof(result.effect_request.action_id),
            "%s","transfer_subject");
    else if (result.effect_request.selected_release_subject)
        snprintf(result.effect_request.action_id,sizeof(result.effect_request.action_id),
            "%s","release_subject");
    else if (result.effect_request.selected_revoke_core)
        snprintf(result.effect_request.action_id,sizeof(result.effect_request.action_id),
            "%s","revoke_core");
    else if (result.effect_request.selected_return_core)
        snprintf(result.effect_request.action_id,sizeof(result.effect_request.action_id),
            "%s","return_core");
    else if (result.effect_request.selected_force_religion)
        snprintf(result.effect_request.action_id,sizeof(result.effect_request.action_id),"%s","force_religion");
    else if (result.effect_request.selected_show_strength)
        snprintf(result.effect_request.action_id,sizeof(result.effect_request.action_id),"%s","show_strength");
    else if (result.effect_request.selected_humiliate_rival)
        snprintf(result.effect_request.action_id,sizeof(result.effect_request.action_id),"%s","humiliate_rival");
    else if (result.effect_request.selected_annul_treaties)
        snprintf(result.effect_request.action_id,sizeof(result.effect_request.action_id),
            "%s","annul_treaties");
    else if (result.effect_request.selected_concede_defeat)
        snprintf(result.effect_request.action_id,sizeof(result.effect_request.action_id),
            "%s","concede_defeat");
    else if (result.effect_request.selected_trade_power)
        snprintf(result.effect_request.action_id,sizeof(result.effect_request.action_id),
            "%s","transfer_trade_power");
    else if (result.effect_request.selected_reparations)
        snprintf(result.effect_request.action_id,sizeof(result.effect_request.action_id),
            "%s","war_reparations");
    else if (result.effect_request.selected_provinces)
        snprintf(result.effect_request.action_id,sizeof(result.effect_request.action_id),
            "%s","cede_province");
    else if (result.effect_request.selected_amount)
        snprintf(result.effect_request.action_id,sizeof(result.effect_request.action_id),
            "%s","demand_ducats");
    else if (result.white)
        snprintf(result.effect_request.action_id,sizeof(result.effect_request.action_id),
            "%s","white_peace");
    result.effect_request.white_peace=result.white;
    result.effects_supported=effects_supported;
    result.complete=understood && result.war_id[0] && offer->direction<=1
        && payload.peace.direction41==offer->direction;
    result.complete=result.complete && endpoints;
    snprintf(result.json,sizeof(result.json),
        "{\"war_id\":\"%.29s\",\"direction\":\"%s\",\"original_actor\":\"%.3s\",\"original_recipient\":\"%.3s\",\"terms\":[%s],\"white_peace\":%s,\"complete\":%s,\"selected_terms_complete\":%s,\"full_annex_proof\":{\"live_offer_present\":%s,\"live_snapshot_complete\":%s,\"sealed_snapshot_equal\":%s,\"selected_cede_complete\":%s,\"selected_cede_unique\":%s,\"owner_owned_ids_complete\":%s,\"native_check_called\":%s,\"native_check_result\":%s,\"preflight_proof_reused\":%s,\"request_identity_matches\":%s,\"derived\":%s,\"owner\":\"%.3s\",\"beneficiary\":\"%.3s\",\"selected_cede_count\":%u,\"owned_count\":%u,\"reason\":\"%.64s\"},\"reason\":\"%s\"}",
        result.war_id,offer->direction==1?"demand":"offer",proposer,recipient,terms,
        result.white?"true":"false",result.complete?"true":"false",understood?"true":"false",
        result.full_annex_proof.live_offer_present?"true":"false",
        result.full_annex_proof.live_snapshot_complete?"true":"false",
        result.full_annex_proof.sealed_snapshot_equal?"true":"false",
        result.full_annex_proof.selected_cede_complete?"true":"false",
        result.full_annex_proof.selected_cede_unique?"true":"false",
        result.full_annex_proof.owner_owned_ids_complete?"true":"false",
        result.full_annex_proof.native_check_called?"true":"false",
        result.full_annex_proof.native_check_result?"true":"false",
        result.full_annex_proof.preflight_proof_reused?"true":"false",
        result.full_annex_proof.request_identity_matches?"true":"false",
        result.full_annex_proof.derived?"true":"false",
        result.full_annex_proof.owner_tag,result.full_annex_proof.beneficiary_tag,
        result.full_annex_proof.selected_cede_count,result.full_annex_proof.owned_count,
        result.full_annex_proof.reason_code,
        result.complete?"none":!understood?"PEACE_SELECTED_TERM_SEMANTICS_UNAVAILABLE":"PEACE_WAR_CONTEXT_UNAVAILABLE");
    return result;
}
