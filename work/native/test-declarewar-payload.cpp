#include <cstdint>
#include <cstdio>

#include "declarewar-payload.h"

using namespace bridge::declarewar_payload;

static unsigned checks=0,failures=0;
static void check(bool value,const char* name) {
    ++checks;
    if (!value) { ++failures; std::printf("fixture_check_failed:%s\n",name); }
}

int main() {
    WarPayloadExtension base{};
    check(base.valid(),"empty_valid");
    check(kWarContainer50Layout.begin_offset==0x50
        && kWarContainer50Layout.end_offset==0x58
        && kWarContainer50Layout.capacity_offset==0x60,"vector50_offsets");
    check(kWarContainer68Layout.begin_offset==0x68
        && kWarContainer80Layout.begin_offset==0x80,"vector_offsets");
    check(WarOwnedPayloadLayout::field08==0x08
        && WarOwnedPayloadLayout::field1c==0x1c
        && WarOwnedPayloadLayout::field58==0x58,"owned_offsets");

    std::uint32_t WarOwnedPayload::*owned_dwords[]={
        &WarOwnedPayload::owned_field08,&WarOwnedPayload::owned_field18};
    for (auto field:owned_dwords) {
        WarPayloadExtension changed=base;
        changed.owned_present=true;
        changed.owned.*field=1;
        check(changed!=base,"owned_dword_difference");
    }
    std::uint64_t WarOwnedPayload::*owned_words[]={
        &WarOwnedPayload::owned_field10,&WarOwnedPayload::owned_field1c,
        &WarOwnedPayload::owned_field28,&WarOwnedPayload::owned_field30,
        &WarOwnedPayload::owned_field38,&WarOwnedPayload::owned_field40,
        &WarOwnedPayload::owned_field48,&WarOwnedPayload::owned_field50,
        &WarOwnedPayload::owned_field58};
    for (auto field:owned_words) {
        WarPayloadExtension changed=base;
        changed.owned_present=true;
        changed.owned.*field=1;
        check(changed!=base,"owned_qword_difference");
    }
    std::uint8_t WarPayloadExtension::*flags[]={
        &WarPayloadExtension::flag40,&WarPayloadExtension::flag41,
        &WarPayloadExtension::flag42};
    for (auto flag:flags) {
        WarPayloadExtension changed=base;
        changed.*flag=1;
        check(changed!=base,"flag_difference");
    }

    WarPayloadVector WarPayloadExtension::*containers[]={
        &WarPayloadExtension::container50,&WarPayloadExtension::container68,
        &WarPayloadExtension::container80};
    for (auto field:containers) {
        WarPayloadExtension changed=base;
        (changed.*field).count=1;
        (changed.*field).values[0]=0x1234;
        check(changed!=base,"container_difference");
    }
    WarPayloadExtension vector_changed=base;
    vector_changed.container50.count=1;
    vector_changed.container50.values[0]=0x1234;
    WarPayloadExtension tail_only=vector_changed;
    tail_only.container50.values[1]=0xffff;
    check(tail_only==vector_changed,"tail_outside_count_ignored");
    std::uint32_t count=0;
    check(war_native_vector_bounds(0x2000,0x2000,0x2000,
        count),"empty_vector_bounds");
    check(war_native_vector_bounds(0x2000,0x2400,0x2800,count)
        && count==128,"bounded_vector_count");
    check(war_native_vector_bounds(0x2000,0x2000+128*8,0x2000+128*8,count)
        && count==128,"max_vector_bounds");
    check(!war_native_vector_bounds(0x2000,0x2000+129*8,0x2000+129*8,count),
        "over_limit_rejected");
    check(!war_native_vector_bounds(0x2000,0x2001,0x2008,count),
        "misaligned_span_rejected");
    check(!war_native_vector_bounds(0x2000,0x2010,0x2008,count),
        "capacity_before_end_rejected");

    const std::uintptr_t object=0x1000,begin=0x2000;
    auto reader=[&](std::uintptr_t address,auto& value)->bool {
        if (address==object+0x50) { value=begin; return true; }
        if (address==object+0x58) { value=begin+16; return true; }
        if (address==object+0x60) { value=begin+24; return true; }
        if (address==begin) { value=0xaaaa; return true; }
        if (address==begin+8) { value=0xbbbb; return true; }
        return false;
    };
    WarPayloadVector captured{};
    check(war_capture_native_u64_vector(reader,object,kWarContainer50Layout,captured)
        && captured.count==2 && captured.values[0]==0xaaaa
        && captured.values[1]==0xbbbb,"capture_exact_offsets");
    check(!base.valid() || base.owned_present==false,"canonical_absent_state");
    base.owned.owned_field10=1;
    check(!base.valid(),"stale_absent_owned_rejected");

    std::printf("checks=%u failures=%u\n",checks,failures);
    return failures?1:0;
}
