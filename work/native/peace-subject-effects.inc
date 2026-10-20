// Bounded observation of the persistent subject relation used by Release
// Subject and Transfer Subject.  Candidate discovery lives in
// peace-subject-candidates.inc; this file verifies the selected term list and
// reads the source/beneficiary relation endpoints for the effects snapshot.

static constexpr unsigned peace_effect_subject_max=16u;

static bool peace_effect_subject_tag(uint64_t handle,char (&tag)[4]) noexcept {
    return handle && peace_province_tag_from_handle(handle,tag);
}

static bool peace_effect_subject_type(uintptr_t association,
    char (&output)[bridge::peace_effects::kMaxReligionKey]) noexcept {
    output[0]=0;
    if (!association) return true;
    uint64_t subject=0; uintptr_t descriptor=0;
    NativeShortString name{};
    if (!read(association+0x18u,subject) || !subject
        || !read(association+0x40u,descriptor) || !descriptor
        || !read(descriptor+0x10u,name) || !name.size
        || name.size>=bridge::peace_effects::kMaxReligionKey
        || name.capacity<name.size || name.capacity>65536u) return false;
    uintptr_t text=descriptor+0x10u;
    if (name.capacity>=16u) memcpy(&text,name.text,sizeof(text));
    if (!text) return false;
    SIZE_T copied=0;
    if (!ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(text),
            output,static_cast<SIZE_T>(name.size),&copied)
        || copied!=name.size) return false;
    for (uint64_t i=0;i<name.size;++i) {
        const unsigned char ch=static_cast<unsigned char>(output[i]);
        if (ch<0x20u || ch>0x7eu || ch=='"' || ch=='\\') {
            output[0]=0; return false;
        }
    }
    output[name.size]=0;
    return true;
}

static bool peace_effect_subject_endpoint(uint64_t source,uint64_t country,
    bool& relation_active,bool& is_overlord,
    char (&subject_type)[bridge::peace_effects::kMaxReligionKey]) noexcept {
    relation_active=false; is_overlord=false; subject_type[0]=0;
    uintptr_t source_object=0,association=0;
    if (!source || !country || source==country
        || !peace_query_country_pointer(source,source_object) || !source_object
        || !vassal_query_entry(source_object,country,association)) return false;
    if (!association) return true;
    uint64_t subject=0;
    if (!read(association+0x18u,subject) || !subject
        || !peace_effect_subject_type(association,subject_type)) return false;
    relation_active=true;
    is_overlord=subject==country;
    return true;
}

static bool peace_effect_subject_relation_read(uint64_t country,uint64_t source,
    uint64_t beneficiary,bridge::peace_effects::SubjectRelationState& output) noexcept {
    output=bridge::peace_effects::SubjectRelationState{};
    output.country=country; output.source=source; output.beneficiary=beneficiary;
    if (!peace_effect_subject_tag(country,output.country_tag)
        || !peace_effect_subject_tag(source,output.source_tag)
        || (beneficiary && !peace_effect_subject_tag(beneficiary,output.beneficiary_tag)))
        return false;
    if (!peace_effect_subject_endpoint(source,country,output.source_relation_active,
            output.source_is_overlord,output.source_subject_type)) return false;
    if (beneficiary) {
        output.beneficiary_relation_readable=true;
        if (!peace_effect_subject_endpoint(beneficiary,country,
                output.beneficiary_relation_active,output.beneficiary_is_overlord,
                output.beneficiary_subject_type)) return false;
    }
    output.complete=true;
    return true;
}

static bool peace_effect_subject_request_row(const char (*countries)[4],
    unsigned count,unsigned index,uint64_t& handle) noexcept {
    if (!countries || index>=count || count==0 || count>peace_effect_subject_max
        || !countries[index][0]
        || !alliance_query_country(countries[index],handle) || !handle) return false;
    for (unsigned i=0;i<index;++i)
        if (!strcmp(countries[i],countries[index])) return false;
    return true;
}

static bool execution_peace_effects_capture_subject(
    const bridge::peace_payload::PeaceOfferPayload& offer,
    const bridge::peace_execution_wire::PeaceExecutionRequest& request,
    bool transfer_subject,PeaceEffectState& output) noexcept {
    const bool selected=transfer_subject?request.selected_transfer_subject:
        request.selected_release_subject;
    const unsigned count=transfer_subject?request.transfer_subject_count:
        request.release_subject_count;
    const char (*countries)[4]=transfer_subject?request.transfer_subject_countries:
        request.release_subject_countries;
    auto& effect=transfer_subject?output.transfer_subject:output.release_subject;
    bool& requested=transfer_subject?output.transfer_subject_requested:
        output.release_subject_requested;
    effect=bridge::peace_effects::SubjectEffectState{};
    requested=selected;
    effect.requested=selected;
    if (!selected) return true;
    if (!offer.payer || !offer.claimant || offer.payer==offer.claimant
        || count==0 || count>peace_effect_subject_max) return false;
    const uint64_t source=offer.payer;
    const uint64_t beneficiary=transfer_subject?offer.claimant:0;
    effect.source=source; effect.beneficiary=beneficiary;
    uint64_t handles[peace_effect_subject_max]{};
    for (unsigned i=0;i<count;++i)
        if (!peace_effect_subject_request_row(countries,count,i,handles[i])) return false;

    bool matched[peace_effect_subject_max]{};
    unsigned selected_terms=0;
    const uint32_t expected_type=transfer_subject?0x35f0u:0x2d27u;
    const uint32_t expected_bucket=transfer_subject?0x14u:0x13u;
    for (unsigned i=0;i<offer.term_count;++i) {
        const auto& term=offer.terms[i];
        if (!term.selected || term.type_id!=expected_type || term.bucket!=expected_bucket)
            continue;
        if (!term.complete || term.field10!=source || term.field18!=offer.claimant)
            return false;
        const uint64_t target=transfer_subject?term.field22:term.extra30;
        unsigned index=count;
        for (unsigned j=0;j<count;++j)
            if (handles[j]==target) { index=j; break; }
        if (index==count || matched[index]) return false;
        matched[index]=true; ++selected_terms;
    }
    if (selected_terms!=count) return false;
    for (unsigned i=0;i<count;++i) {
        if (!matched[i] || !peace_effect_subject_relation_read(handles[i],source,
                beneficiary,effect.rows[i])) return false;
    }
    effect.count=count; effect.complete=true;
    return true;
}

static bool execution_peace_effects_after_subject(
    const bridge::peace_effects::SubjectEffectState& before,
    bridge::peace_effects::SubjectEffectState& after) noexcept {
    after=bridge::peace_effects::SubjectEffectState{};
    after.requested=before.requested; after.source=before.source;
    after.beneficiary=before.beneficiary; after.count=before.count;
    if (!before.requested) return true;
    if (!before.source || before.count==0 || before.count>peace_effect_subject_max)
        return false;
    for (unsigned i=0;i<before.count;++i) {
        const auto& before_row=before.rows[i];
        if (!peace_effect_subject_relation_read(before_row.country,before.source,
                before.beneficiary,after.rows[i])) return false;
    }
    after.complete=true;
    return true;
}

