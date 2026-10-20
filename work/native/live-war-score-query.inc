// Read-only live war-score inspection.  Include this file after
// peace-context-query.inc and peace-war-context-query.inc: it reuses their
// observer-session registry and participant-vector validators.  It does not
// create, submit, or mutate a peace offer or a war.

#ifndef BRIDGE_LIVE_WAR_SCORE_QUERY_INC_INCLUDED
#define BRIDGE_LIVE_WAR_SCORE_QUERY_INC_INCLUDED

#include <climits>
#include <cstdio>
#include "live-war-score-query.h"

using bridge::live_war_score_query::BoundContext;
using bridge::live_war_score_query::Mode;
using bridge::live_war_score_query::Request;
using bridge::live_war_score_query::Result;
using bridge::live_war_score_query::Tooltip;

static constexpr uintptr_t live_war_score_method_rva=0xd91be0;
static constexpr uintptr_t live_war_goal_progress_method_rva=0xd932d0;
static constexpr uintptr_t live_war_score_string_destroy_rva=0x95660;
static constexpr uintptr_t live_war_score_cap_rva=0x233dba0;
static constexpr uintptr_t live_war_score_overview_goal_cap_rva=0x233f130;
// d932d0 reads the selected war-goal object from this field.  A readable
// null value means that the war has no applicable goal; it must not be
// reported as a configured goal whose cumulative score happens to be zero.
static constexpr uintptr_t live_war_goal_object_offset=0x160;

using LiveWarScoreMethod=int (__fastcall *)(void*,std::uint64_t,std::uint64_t,
    NativeShortString*,unsigned char);
using LiveWarGoalProgressMethod=std::int32_t* (__fastcall *)(void*,
    std::int32_t*,std::uint64_t);
using LiveWarStringDestroy=void (__fastcall *)(void*);

static bool live_war_score_copy_hex(const unsigned char* bytes,unsigned size,
    char* output,std::size_t output_capacity) noexcept {
    if (!output || output_capacity==0 || size*2u+1u>output_capacity) return false;
    for (unsigned index=0;index<size;++index)
        std::snprintf(output+index*2,3,"%02x",bytes[index]);
    output[size*2]=0;
    return true;
}

static bool live_war_score_capture_tooltip(NativeShortString& text,
    Tooltip& output) noexcept {
    output=Tooltip{};
    output.requested=true;
    output.size=text.size;
    output.capacity=text.capacity;
    const std::uint64_t bounded_size=
        text.size<bridge::live_war_score_query::kMaxNativeTooltipBytes
        ? text.size
        : bridge::live_war_score_query::kMaxNativeTooltipBytes;
    output.truncated=text.size>
        bridge::live_war_score_query::kMaxNativeTooltipBytes;
    if (text.size>text.capacity || text.capacity>131072u) return false;

    uintptr_t address=reinterpret_cast<uintptr_t>(text.text);
    if (text.capacity>=16) std::memcpy(&address,text.text,sizeof(address));
    if (bounded_size==0) {
        output.readable=true;
        output.text_hex[0]=0;
        return true;
    }
    if (!address || bounded_size>static_cast<std::uint64_t>(UINT_MAX))
        return false;
    unsigned char bytes[
        bridge::live_war_score_query::kMaxNativeTooltipBytes]{};
    SIZE_T copied=0;
    const bool copied_ok=ReadProcessMemory(GetCurrentProcess(),
        reinterpret_cast<void*>(address),bytes,
        static_cast<SIZE_T>(bounded_size),&copied)!=0
        && copied==static_cast<SIZE_T>(bounded_size);
    if (!copied_ok) return false;
    output.readable=live_war_score_copy_hex(bytes,
        static_cast<unsigned>(bounded_size),output.text_hex,
        sizeof(output.text_hex));
    return output.readable;
}

static bool live_war_score_capture_goal_presence(uintptr_t native_war,
    bool& readable,bool& present) noexcept {
    readable=false;
    present=false;
    uintptr_t goal_object=0;
    if (!native_war || !read(native_war+live_war_goal_object_offset,goal_object))
        return false;
    readable=true;
    present=goal_object!=0;
    return true;
}

static const PeaceWarRegistryEntry* live_war_score_find_registry(
    const char* war_id) noexcept {
    if (!war_id || !war_id[0]) return nullptr;
    std::size_t length=0;
    while (length<=bridge::live_war_score_query::kMaxWarIdLength
        && war_id[length]) ++length;
    if (length==0 || length>bridge::live_war_score_query::kMaxWarIdLength)
        return nullptr;
    for (unsigned index=0;index<peace_war_registry_size;++index)
        if (std::strcmp(peace_war_registry[index].public_id,war_id)==0)
            return &peace_war_registry[index];
    return nullptr;
}

static bool live_war_score_reference_contains(
    const PeaceWarReferenceList& list,uintptr_t reference) noexcept {
    if (!reference || !list.complete) return false;
    for (unsigned index=0;index<list.count;++index)
        if (list.references[index]==reference) return true;
    return false;
}

static bool live_war_score_bind_context(const char* war_id,
    std::uint64_t actor,std::uint64_t recipient,
    std::uint64_t perspective,BoundContext& output,
    char* error,std::size_t error_capacity) noexcept {
    output=BoundContext{};
    if (error && error_capacity) error[0]=0;
    const auto fail=[&](const char* code) noexcept {
        if (error && error_capacity) {
            std::size_t index=0;
            for (;index+1<error_capacity && code && code[index];++index)
                error[index]=code[index];
            error[index]=0;
        }
        return false;
    };
    const PeaceWarRegistryEntry* entry=live_war_score_find_registry(war_id);
    if (!entry) return fail("WAR_ID_NOT_FOUND");
    if (!actor || !recipient || actor==recipient
        || (perspective!=actor && perspective!=recipient))
        return fail("WAR_HANDLE_INVALID");

    uintptr_t actor_country=0,recipient_country=0;
    PeaceWarReferenceList actor_refs{},recipient_refs{};
    const unsigned actor_slot=static_cast<unsigned>((actor>>32)&0xffffu);
    const unsigned recipient_slot=static_cast<unsigned>((recipient>>32)&0xffffu);
    if (!peace_query_country_pointer(actor,actor_country)
        || !peace_query_country_pointer(recipient,recipient_country)
        || !peace_query_pair_references(actor_country,recipient_slot,actor_refs)
        || !peace_query_pair_references(recipient_country,actor_slot,recipient_refs)
        || !peace_query_reference_sets_equal(actor_refs,recipient_refs))
        return fail("WAR_CONTEXT_STALE");
    if (!live_war_score_reference_contains(actor_refs,entry->native_reference))
        return fail("WAR_ID_NOT_BOUND_TO_PAIR");

    PeaceWarSideMembers side_a{},side_b{};
    if (!peace_war_capture_vector(entry->native_reference,0x48,0x50,0x58,side_a)
        || !peace_war_capture_vector(entry->native_reference,0x78,0x80,0x88,side_b))
        return fail("WAR_PARTICIPANTS_UNREADABLE");
    const bool actor_a=peace_war_side_contains(side_a,actor);
    const bool actor_b=peace_war_side_contains(side_b,actor);
    const bool recipient_a=peace_war_side_contains(side_a,recipient);
    const bool recipient_b=peace_war_side_contains(side_b,recipient);
    if (actor_a==actor_b || recipient_a==recipient_b
        || (actor_a==recipient_a))
        return fail("WAR_SIDE_MEMBERSHIP_AMBIGUOUS");

    const bool perspective_a=perspective==actor?actor_a:recipient_a;
    const PeaceWarSideMembers& opposite=perspective_a?side_b:side_a;
    if (!opposite.complete || opposite.count==0)
        return fail("WAR_OPPOSITE_SIDE_EMPTY");

    output.native_war=entry->native_reference;
    output.actor=actor;
    output.recipient=recipient;
    output.perspective=perspective;
    output.side_anchor=opposite.handles[0];
    output.actor_side=actor_a?1:2;
    output.recipient_side=recipient_a?1:2;
    output.side_a_count=side_a.count;
    output.side_b_count=side_b.count;
    output.registry_match=true;
    output.pair_reference_verified=true;
    output.participant_lists_complete=side_a.complete && side_b.complete;
    output.actor_handle_verified=true;
    output.recipient_handle_verified=true;
    output.perspective_handle_verified=true;
    output.side_anchor_verified=output.side_anchor!=0;
    output.actor_recipient_opposite=output.actor_side!=output.recipient_side;
    output.complete=output.registry_match
        && output.pair_reference_verified
        && output.participant_lists_complete
        && output.perspective_handle_verified
        && output.side_anchor_verified
        && output.actor_recipient_opposite;
    return output.complete;
}

static bool live_war_score_capture_native(const Request& request,
    const BoundContext& context,Result& output) noexcept {
    output=Result{};
    output.context=context;
    if (!context.complete) {
        bridge::live_war_score_query::set_error(output,"WAR_CONTEXT_INCOMPLETE");
        return false;
    }
    if (!bridge::live_war_score_query::valid_mode(request.mode)) {
        bridge::live_war_score_query::set_error(output,"WAR_MODE_INVALID");
        return false;
    }
    NativeShortString tooltip{};
    tooltip.capacity=15;
    const auto method=reinterpret_cast<LiveWarScoreMethod>(
        base+live_war_score_method_rva);
    const unsigned char mode=request.mode;
    // d91be0 derives its sign from the RDX country (param_2), unlike the
    // d932d0 out-parameter ABI below. Keep actor perspective in RDX.
    output.total_raw=method(reinterpret_cast<void*>(context.native_war),
        context.perspective,context.side_anchor,&tooltip,mode);
    output.total_called=true;
    output.total_return_verified=true;
    const bool tooltip_ok=live_war_score_capture_tooltip(tooltip,output.tooltip);
    reinterpret_cast<LiveWarStringDestroy>(
        base+live_war_score_string_destroy_rva)(&tooltip);
    output.native_string_destroy_called=true;
    output.total_complete=output.total_called
        && output.total_return_verified && tooltip_ok
        && output.tooltip.readable && !output.tooltip.truncated
        && output.native_string_destroy_called;
    if (!tooltip_ok) {
        bridge::live_war_score_query::set_error(output,
            "WAR_TOOLTIP_UNREADABLE");
        return false;
    }

    live_war_score_capture_goal_presence(
        context.native_war,output.goal_presence_readable,output.goal_present);
    output.goal_inapplicable=output.goal_presence_readable
        && !output.goal_present;
    std::int32_t goal=0;
    const auto goal_method=reinterpret_cast<LiveWarGoalProgressMethod>(
        base+live_war_goal_progress_method_rva);
    const std::int32_t* goal_return=goal_method(
        reinterpret_cast<void*>(context.native_war),&goal,context.perspective);
    output.goal_called=true;
    output.goal_return_verified=goal_return==&goal;
    output.goal_out_written=output.goal_return_verified;
    if (output.goal_return_verified && output.goal_present)
        output.goal_cumulative_raw=goal;
    output.goal_complete=output.goal_called
        && output.goal_return_verified && output.goal_presence_readable
        && output.goal_present && output.tooltip.readable
        && !output.tooltip.truncated && output.native_string_destroy_called;

    output.max_score_readable=read(base+live_war_score_cap_rva,
        output.max_score_raw);
    output.overview_goal_cap_readable=read(
        base+live_war_score_overview_goal_cap_rva,
        output.overview_goal_cap_raw);
    // The outer result is complete when the score and its full native text
    // were captured and d932d0 was actually called with a classified goal
    // presence.  An inapplicable goal is a valid query outcome, while its
    // own goal_complete flag deliberately remains false.
    output.complete=output.context.complete && output.total_complete
        && output.goal_called && output.goal_return_verified
        && output.goal_presence_readable;
    output.verified=output.complete
        && output.max_score_readable
        && output.overview_goal_cap_readable;
    if (!output.complete) {
        if (!output.total_complete)
            bridge::live_war_score_query::set_error(output,
                output.tooltip.truncated?"WAR_TOOLTIP_TRUNCATED":
                    "WAR_SCORE_INCOMPLETE");
        else if (!output.goal_called || !output.goal_return_verified)
            bridge::live_war_score_query::set_error(output,
                "WAR_GOAL_RETURN_UNVERIFIED");
        else if (!output.goal_presence_readable)
            bridge::live_war_score_query::set_error(output,
                "WAR_GOAL_PRESENCE_UNREADABLE");
        else
            bridge::live_war_score_query::set_error(output,
                "WAR_NATIVE_CALL_UNAVAILABLE");
    }
    else if (!output.verified)
        bridge::live_war_score_query::set_error(output,
            "WAR_CAP_READ_UNAVAILABLE");
    return output.complete && output.verified;
}

static bool live_war_score_query_run(const Request& request,Result& output) noexcept {
    output=Result{};
    if (!request.war_id || !request.war_id[0]) {
        bridge::live_war_score_query::set_error(output,"WAR_ID_EMPTY");
        return false;
    }
    if (!bridge::live_war_score_query::valid_mode(request.mode)) {
        bridge::live_war_score_query::set_error(output,"WAR_MODE_INVALID");
        return false;
    }
    BoundContext context{};
    if (!live_war_score_bind_context(request.war_id,request.actor,
            request.recipient,request.perspective,context,
            output.error_code,sizeof(output.error_code)))
        return false;
    return live_war_score_capture_native(request,context,output);
}

static bool live_war_score_json_int(char* output,std::size_t capacity,
    bool readable,std::int32_t value) noexcept {
    if (!output || !capacity) return false;
    const int written=std::snprintf(output,capacity,readable?"%d":"null",
        readable?value:0);
    return written>=0 && static_cast<std::size_t>(written)<capacity;
}

static const char* live_war_score_goal_presence(const Result& result) noexcept {
    if (!result.goal_presence_readable) return "unknown";
    return result.goal_present ? "configured" : "inapplicable";
}

// This is the pointer-free score object used below both by the private event
// and by the already-selected peace query's public war_context.war_score.
// The two native caps intentionally retain their distinct proven scales:
// d91be0/max-score is scale 1, while d932d0/overview goal cap is scale 1000.
static bool live_war_score_score_json(const Request& request,
    const Result& result,char* output,std::size_t capacity) noexcept {
    if (!output || !capacity) return false;
    char total_raw[32]{},max_score[32]{},goal_cap[32]{},goal_raw[32]{};
    const bool goal_value_readable=result.goal_present
        && result.goal_return_verified;
    if (!live_war_score_json_int(total_raw,sizeof(total_raw),
            result.total_called,result.total_raw)
        || !live_war_score_json_int(max_score,sizeof(max_score),
            result.max_score_readable,result.max_score_raw)
        || !live_war_score_json_int(goal_cap,sizeof(goal_cap),
            result.overview_goal_cap_readable,result.overview_goal_cap_raw)
        || !live_war_score_json_int(goal_raw,sizeof(goal_raw),
            goal_value_readable,result.goal_cumulative_raw))
        return false;
    const char* mode=bridge::live_war_score_query::mode_name(
        static_cast<Mode>(request.mode));
    const char* perspective=request.perspective==request.actor?"actor":
        request.perspective==request.recipient?"recipient":"unknown";
    const int written=std::snprintf(output,capacity,
        "{\"war_id\":\"%.29s\",\"mode\":\"%s\",\"mode_raw\":%u,"
        "\"perspective\":\"%s\",\"total_raw\":%s,"
        "\"total_available\":%s,\"total_complete\":%s,"
        "\"total_unit\":\"war_score_points\",\"total_scale\":1,"
        "\"max_score_raw\":%s,\"max_score_scale\":1,"
        "\"overview_goal_cap_raw\":%s,\"overview_goal_cap_scale\":1000,"
        "\"goal\":{\"called\":%s,\"return_is_out_pointer\":%s,"
        "\"out_written\":%s,\"presence\":\"%s\","
        "\"presence_verified\":%s,\"present\":%s,"
        "\"inapplicable\":%s,\"available\":%s,\"cumulative_raw\":%s,"
        "\"cumulative_unit\":\"war_goal_score_raw\","
        "\"cumulative_scale\":1000,\"complete\":%s},"
        "\"daily\":{\"available\":false,\"score_raw\":null,"
        "\"unit\":\"war_score_points\","
        "\"reason\":\"NO_CONFIRMED_DAILY_GETTER\"},"
        "\"scale_verified\":true,\"tooltip\":{\"requested\":%s,"
        "\"text\":null,\"text_hex\":null,\"text_hex_omitted\":true,"
        "\"text_readable\":%s,\"text_truncated\":%s,"
        "\"text_size\":%llu,\"string_capacity\":%llu,"
        "\"codec\":\"configured_native_text_codec\",\"complete\":%s},"
        "\"complete\":%s,\"verified\":%s}",
        request.war_id?request.war_id:"",mode,static_cast<unsigned>(request.mode),
        perspective,total_raw,result.total_called?"true":"false",
        result.total_complete?"true":"false",max_score,goal_cap,
        result.goal_called?"true":"false",
        result.goal_return_verified?"true":"false",
        result.goal_out_written?"true":"false",
        live_war_score_goal_presence(result),
        result.goal_presence_readable?"true":"false",
        result.goal_present?"true":"false",
        result.goal_inapplicable?"true":"false",
        goal_value_readable?"true":"false",goal_raw,
        result.goal_complete?"true":"false",
        result.tooltip.requested?"true":"false",
        result.tooltip.readable?"true":"false",
        result.tooltip.truncated?"true":"false",
        static_cast<unsigned long long>(result.tooltip.size),
        static_cast<unsigned long long>(result.tooltip.capacity),
        (result.tooltip.readable && !result.tooltip.truncated
            && result.native_string_destroy_called)?"true":"false",
        result.complete?"true":"false",result.verified?"true":"false");
    return written>=0 && static_cast<std::size_t>(written)<capacity;
}

static bool live_war_score_tooltip_json(const Result& result,
    bool include_hex,char* output,std::size_t capacity) noexcept {
    if (!output || !capacity) return false;
    const char* hex_json=include_hex?"\"":"null";
    const char* hex=include_hex?result.tooltip.text_hex:"";
    const int written=std::snprintf(output,capacity,
        "{\"requested\":%s,\"text\":null,\"text_hex\":%s%s%s,"
        "\"text_hex_omitted\":%s,\"text_readable\":%s,"
        "\"text_truncated\":%s,\"text_size\":%llu,"
        "\"string_capacity\":%llu,\"codec\":\"configured_native_text_codec\","
        "\"complete\":%s}",
        result.tooltip.requested?"true":"false",hex_json,hex,
        include_hex?"\"":"",
        include_hex?"false":"true",
        result.tooltip.readable?"true":"false",
        result.tooltip.truncated?"true":"false",
        static_cast<unsigned long long>(result.tooltip.size),
        static_cast<unsigned long long>(result.tooltip.capacity),
        (result.tooltip.readable && !result.tooltip.truncated
            && result.native_string_destroy_called)?"true":"false");
    return written>=0 && static_cast<std::size_t>(written)<capacity;
}

// Returns one complete `"war_score":{...}` member.  The caller appends it
// to the existing pointer-free peace `war_context` object.  Tooltip bytes are
// deliberately omitted here; the private inspection event carries the full
// bounded hex payload without enlarging every public peace context buffer.
[[maybe_unused]] static bool live_war_score_war_context_member_json(const Request& request,
    const Result& result,char* output,std::size_t capacity) noexcept {
    if (!output || !capacity) return false;
    char score[4096]{};
    if (!live_war_score_score_json(request,result,score,sizeof(score)))
        return false;
    const int written=std::snprintf(output,capacity,
        "\"war_score\":%s",score);
    return written>=0 && static_cast<std::size_t>(written)<capacity;
}

static bool live_war_score_private_event_json(const char* session_id,
    const char* query_id,const char* action_id,const char* actor_tag,
    const char* recipient_tag,int date_raw,const Request& request,
    const Result& result,char* output,std::size_t capacity) noexcept {
    if (!output || !capacity) return false;
    char score[4096]{},tooltip[bridge::live_war_score_query::
        kMaxNativeTooltipHexBytes+512]{},calls[1024]{},verification[1024]{};
    if (!live_war_score_score_json(request,result,score,sizeof(score))
        || !live_war_score_tooltip_json(result,true,tooltip,sizeof(tooltip)))
        return false;
    // The return value is formatted separately so that a failed native call
    // is emitted as JSON null instead of a fabricated zero.
    char total_raw[32]{};
    if (!live_war_score_json_int(total_raw,sizeof(total_raw),
            result.total_called,result.total_raw)) return false;
    const int fixed_calls=std::snprintf(calls,sizeof(calls),
        "{\"d91be0_called\":%s,\"d91be0_return_raw\":%s,"
        "\"d91be0_text_requested\":%s,"
        "\"d91be0_text_captured_before_destroy\":%s,"
        "\"native_string_destroy_called\":%s,\"d932d0_called\":%s,"
        "\"d932d0_return_is_out_pointer\":%s,\"d932d0_out_written\":%s,"
        "\"goal_presence_readable\":%s}",
        result.total_called?"true":"false",total_raw,
        result.tooltip.requested?"true":"false",
        result.tooltip.readable?"true":"false",
        result.native_string_destroy_called?"true":"false",
        result.goal_called?"true":"false",
        result.goal_return_verified?"true":"false",
        result.goal_out_written?"true":"false",
        result.goal_presence_readable?"true":"false");
    if (fixed_calls<0 || static_cast<std::size_t>(fixed_calls)>=sizeof(calls))
        return false;
    const int verification_written=std::snprintf(verification,sizeof(verification),
        "{\"actor_handle_valid\":%s,\"recipient_handle_valid\":%s,"
        "\"pair_reference_sets_equal\":%s,\"war_id_bound_to_pair\":%s,"
        "\"side_vectors_verified\":%s,\"score_perspective_verified\":%s,"
        "\"goal_direction_verified\":%s,\"goal_presence_verified\":%s,"
        "\"complete\":%s,\"verified\":%s}",
        result.context.actor_handle_verified?"true":"false",
        result.context.recipient_handle_verified?"true":"false",
        result.context.pair_reference_verified?"true":"false",
        result.context.registry_match?"true":"false",
        result.context.participant_lists_complete?"true":"false",
        result.context.perspective_handle_verified?"true":"false",
        result.goal_called && result.goal_return_verified?"true":"false",
        result.goal_presence_readable?"true":"false",
        result.complete?"true":"false",result.verified?"true":"false");
    if (verification_written<0
        || static_cast<std::size_t>(verification_written)>=sizeof(verification))
        return false;
    const char* error=result.error_code[0]?result.error_code:"";
    const char* error_json=result.error_code[0]?"\"":"null";
    const char* actor_side=result.context.actor_side==1?"side_a":
        result.context.actor_side==2?"side_b":"unknown";
    const char* recipient_side=result.context.recipient_side==1?"side_a":
        result.context.recipient_side==2?"side_b":"unknown";
    const int written=std::snprintf(output,capacity,
        "{\"event\":\"native_live_war_score_inspection\","
        "\"family\":\"war_score\",\"action_id\":\"%.63s\","
        "\"query_id\":\"%.64s\",\"session_id\":\"%.79s\","
        "\"actor\":\"%.3s\",\"recipient\":\"%.3s\","
        "\"phase\":\"query\",\"date_raw\":%d,\"submitted\":false,"
        "\"war_id\":\"%.29s\",\"war_context\":{\"war_id\":\"%.29s\","
        "\"identity_scope\":\"observer_session\",\"pair_at_war\":%s,"
        "\"registry_match\":%s,\"war_context_resolved\":%s,"
        "\"association_verified\":%s,\"actor_side\":\"%s\","
        "\"recipient_side\":\"%s\",\"actor_side_verified\":%s,"
        "\"recipient_side_verified\":%s,\"actor_recipient_opposite\":%s,"
        "\"side_a_count\":%u,\"side_b_count\":%u,"
        "\"participant_lists_complete\":%s,\"members_capture_complete\":%s,"
        "\"context_complete\":%s},\"score\":%s,\"tooltip\":%s,"
        "\"native_calls\":%s,\"verification\":%s,\"error\":%s%s%s}\n",
        action_id?action_id:"live_war_score",query_id?query_id:"",
        session_id?session_id:"",actor_tag?actor_tag:"",recipient_tag?recipient_tag:"",
        date_raw,request.war_id?request.war_id:"",request.war_id?request.war_id:"",
        result.context.actor_recipient_opposite?"true":"false",
        result.context.registry_match?"true":"false",
        result.context.complete?"true":"false",
        result.context.pair_reference_verified?"true":"false",actor_side,recipient_side,
        result.context.actor_side!=0?"true":"false",
        result.context.recipient_side!=0?"true":"false",
        result.context.actor_recipient_opposite?"true":"false",
        result.context.side_a_count,result.context.side_b_count,
        result.context.participant_lists_complete?"true":"false",
        result.context.participant_lists_complete?"true":"false",
        result.context.complete?"true":"false",score,tooltip,calls,verification,
        error_json,error,result.error_code[0]?"\"":"");
    return written>=0 && static_cast<std::size_t>(written)<capacity;
}

[[maybe_unused]] static bool live_war_score_result_json(const char* query_id,
    const char* action_id,const char* actor_tag,const char* recipient_tag,
    const Request& request,const Result& result,
    char* output,std::size_t capacity) noexcept {
    return live_war_score_private_event_json("",query_id,action_id,
        actor_tag,recipient_tag,0,request,result,output,capacity);
}

#endif // BRIDGE_LIVE_WAR_SCORE_QUERY_INC_INCLUDED
