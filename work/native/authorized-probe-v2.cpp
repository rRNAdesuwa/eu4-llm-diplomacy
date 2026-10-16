// Build-specific research bridge. Fixed FRA -> ENG native white/gold peace tests.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <cstdint>
#include <cstring>
#include <cstdio>
#if !defined(BRIDGE_PEACE_AUTHORITY_LOCK) || !defined(BRIDGE_TRACE_COMMAND_EXECUTION) || !defined(BRIDGE_ENABLE_PEACE_SEND)
#error Authorized research build requires peace lock, command tracing and sender.
#endif

extern "C" void bridge_frame_stub();
extern "C" void bridge_response_stub();
extern "C" { void* bridge_trampoline = nullptr; }
extern "C" { void* bridge_response_original = nullptr; }
static HMODULE self_module;
static uintptr_t base;
static HANDLE log_file = INVALID_HANDLE_VALUE;
static volatile LONG started = 0, inside = 0, frame_count = 0;
static DWORD frame_thread = 0;
static bool thread_changed = false;
static ULONGLONG last_log = 0;
static wchar_t roundtrip_path[MAX_PATH];
static wchar_t action_path[MAX_PATH];
static wchar_t whitepeace_path[MAX_PATH];
static wchar_t gold_test_path[MAX_PATH];
static wchar_t gold_send_path[MAX_PATH];
static const unsigned char expected[20] = {
    0x4c,0x89,0x44,0x24,0x18,0x55,0x53,0x57,0x48,0x8d,
    0x6c,0x24,0xb0,0x48,0x81,0xec,0x50,0x01,0x00,0x00};

#ifdef BRIDGE_TRACE_PEACE_RESPONSES
struct ResponseEvent {
    volatile LONG ready;
    DWORD thread;
    uint64_t actor,recipient;
    int32_t state,date,gold_cost;
    unsigned char direction,preview_flag,authority_blocked;
    uint64_t authorization;
};
static ResponseEvent response_events[64]{};
static volatile LONG response_count=0;
static LONG response_consumed=0;
#endif

static void line(const char* message) {
    DWORD written;
    if (log_file != INVALID_HANDLE_VALUE) {
        WriteFile(log_file, message, static_cast<DWORD>(strlen(message)), &written, nullptr);
        FlushFileBuffers(log_file);
    }
}
template<typename T> static bool read(uintptr_t address, T& value) {
    SIZE_T size = 0;
    return address >= 0x10000 && ReadProcessMemory(GetCurrentProcess(),
        reinterpret_cast<void*>(address), &value, sizeof(value), &size) && size == sizeof(value);
}


// Sidecar lineage: no action data mutation or permission inferred from terms.
struct Authorization { uintptr_t object; uint64_t id; };
static Authorization authorizations[128]{};
struct LineageEvent { volatile LONG ready; uintptr_t source,result; uint64_t id; bool added; };
static LineageEvent lineage_events[64]{};
static volatile LONG lineage_count=0;
static LONG lineage_consumed=0;
static SRWLOCK authorization_lock=SRWLOCK_INIT;
static uint64_t next_authorization=0;
static bool authorization_test_ready=false;
static bool authorization_test_attempted=false;
static uint64_t authorization_get(uintptr_t object) {
    uint64_t id=0;
    AcquireSRWLockShared(&authorization_lock);
    for (const auto& entry:authorizations) if (entry.object==object) { id=entry.id; break; }
    ReleaseSRWLockShared(&authorization_lock);
    return id;
}
static bool authorization_add(uintptr_t object,uint64_t id) {
    if (!object || !id) return false;
    bool added=false;
    AcquireSRWLockExclusive(&authorization_lock);
    for (const auto& entry:authorizations) if (entry.object==object) {
        bool same=entry.id==id;
        ReleaseSRWLockExclusive(&authorization_lock); return same;
    }
    for (auto& entry:authorizations) if (!entry.object) {
        entry={object,id}; added=true; break;
    }
    ReleaseSRWLockExclusive(&authorization_lock);
    return added; // Full table denies propagation.
}
static void authorization_remove(uintptr_t object) {
    AcquireSRWLockExclusive(&authorization_lock);
    for (auto& entry:authorizations) if (entry.object==object) entry={0,0};
    ReleaseSRWLockExclusive(&authorization_lock);
}
static void* authorized_clone(void* source) {
    uint64_t id=authorization_get(reinterpret_cast<uintptr_t>(source));
    using Clone=void* (*)(void*);
    void* result=reinterpret_cast<Clone>(base+0x59ba70)(source);
    if (id && result) {
        bool added=authorization_add(reinterpret_cast<uintptr_t>(result),id);
        LONG index=InterlockedIncrement(&lineage_count)-1;
        if (index>=0 && index<64) {
            auto& event=lineage_events[index];
            event.source=reinterpret_cast<uintptr_t>(source);
            event.result=reinterpret_cast<uintptr_t>(result);
            event.id=id; event.added=added;
            InterlockedExchange(&event.ready,1);
        }
    }
    return result;
}
static void* authorized_destructor(void* object,unsigned int flags) {
    authorization_remove(reinterpret_cast<uintptr_t>(object));
    using Destructor=void* (*)(void*,unsigned int);
    return reinterpret_cast<Destructor>(base+0x598b90)(object,flags);
}


// Transport assigns an origin and atomic sequence before command serialization.
// These native protocol identities, not peace terms, survive reconstruction.
struct PacketAuthorization { uint64_t key,id; };
static PacketAuthorization packet_authorizations[128]{};
struct PacketEvent { volatile LONG ready; uint64_t key,id; unsigned phase; };
static PacketEvent packet_events[64]{};
static volatile LONG packet_count=0;
static LONG packet_consumed=0;
static bool packet_key(uintptr_t command,uint64_t& key) {
    uint16_t origin=0; uint32_t sequence=0; unsigned char flags=0;
    if (!read(command+0x48,origin) || !read(command+0x4c,sequence)
        || !read(command+0x4a,flags) || flags!=0) return false;
    key=(static_cast<uint64_t>(sequence)<<16)|origin;
    return true;
}
static void packet_event(uint64_t key,uint64_t id,unsigned phase) {
    LONG index=InterlockedIncrement(&packet_count)-1;
    if (index<0 || index>=64) return;
    auto& event=packet_events[index];
    event.key=key; event.id=id; event.phase=phase;
    InterlockedExchange(&event.ready,1);
}
static void authorized_serialize(void* command,void* stream) {
    uintptr_t action=0; uint64_t key=0,id=0;
    if (read(reinterpret_cast<uintptr_t>(command)+0x50,action))
        id=authorization_get(action);
    if (id && packet_key(reinterpret_cast<uintptr_t>(command),key)) {
        bool registered=false;
        AcquireSRWLockExclusive(&authorization_lock);
        for (auto& entry:packet_authorizations) if (!entry.id) {
            entry={key,id}; registered=true; break;
        }
        ReleaseSRWLockExclusive(&authorization_lock);
        packet_event(key,id,registered?1:3);
    }
    using Serialize=void (*)(void*,void*);
    reinterpret_cast<Serialize>(base+0x4e8470)(command,stream);
}
static uint64_t packet_claim(uintptr_t command,uintptr_t action) {
    uint64_t key=0,id=0;
    if (!packet_key(command,key)) return 0;
    AcquireSRWLockExclusive(&authorization_lock);
    for (auto& entry:packet_authorizations) if (entry.id && entry.key==key) {
        id=entry.id; entry={0,0}; break;
    }
    ReleaseSRWLockExclusive(&authorization_lock);
    if (id) {
        bool added=authorization_add(action,id);
        packet_event(key,id,added?2:4);
        if (!added) return 0;
    }
    return id;
}

extern "C" int bridge_response_observe(void* object) {
#ifdef BRIDGE_TRACE_PEACE_RESPONSES
    uintptr_t address=reinterpret_cast<uintptr_t>(object),vtable=0;
    uintptr_t incoming_command=address;
    ResponseEvent event{};
#ifdef BRIDGE_TRACE_COMMAND_EXECUTION
    // Observe the generic command's execution entry, then inspect its owned
    // action. The forwarding stub still receives the original command pointer.
    if (!read(address,vtable) || vtable!=base+0x1c814b0
        || !read(address+0x50,address)) return 1;
#endif
    if (!read(address,vtable) || vtable!=base+0x1c7b840
        || !read(address+0x10,event.actor) || !read(address+0x20,event.recipient)) return 1;
    if (!authorization_get(address)) packet_claim(incoming_command,address);
    bool pair=((event.actor&0xffffff)==0x415246 && (event.recipient&0xffffff)==0x474e45)
        || ((event.actor&0xffffff)==0x474e45 && (event.recipient&0xffffff)==0x415246);
#ifdef BRIDGE_PEACE_AUTHORITY_LOCK
    // Quarantine only the verified peace action class. Match the current full
    // FRA handle, not merely three tag bytes. Block both incoming/outgoing
    // requests and every response state; no guessed actor/state attribution.
    uintptr_t database=0,array=0,country=0;
    uint64_t controlled_handle=0;
    bool controlled_valid=read(base+0x233d8b0,database) && read(database+0x118,array)
        && read(array+122*8,country) && read(country+0x20,controlled_handle)
        && ((controlled_handle>>32)&0xffff)==122 && (controlled_handle&0xffffff)==0x415246;
    event.authority_blocked=controlled_valid
        && (event.actor==controlled_handle || event.recipient==controlled_handle);
    event.authorization=authorization_get(address);
    pair=event.authority_blocked!=0;
    if (event.authorization) event.authority_blocked=0;
#endif
    int forward=event.authority_blocked?0:1;
    if (!pair || !read(address+0x34,event.state) || !read(address+0x2c,event.date)
        || !read(address+0x41,event.direction) || !read(address+0x208,event.preview_flag)
        || !read(address+0x48+0xf0,event.gold_cost)) return forward;
    LONG index=InterlockedIncrement(&response_count)-1;
    if (index<0 || index>=64) return forward;
    ResponseEvent& output=response_events[index];
    output.thread=GetCurrentThreadId();
    output.actor=event.actor; output.recipient=event.recipient;
    output.state=event.state; output.date=event.date; output.gold_cost=event.gold_cost;
    output.direction=event.direction; output.preview_flag=event.preview_flag;
    output.authority_blocked=event.authority_blocked;
    output.authorization=event.authorization;
    // No I/O, engine calls or action mutation here. The frame hook drains it.
    InterlockedExchange(&output.ready,1);
    return forward;
#else
    (void)object;
    return 1;
#endif
}
static void absolute_jump(unsigned char* bytes, uintptr_t destination) {
    bytes[0]=0xff; bytes[1]=0x25;
    memset(bytes+2, 0, 4);
    memcpy(bytes+6, &destination, 8);
}

static void action_roundtrip(uintptr_t database, uintptr_t game, bool send=false, bool gold=false) {
#ifndef BRIDGE_ENABLE_PEACE_SEND
    if (send) {
        line("{\"event\":\"whitepeace_rejected\",\"reason\":\"war_context_acceptance_not_verified\"}\n");
        return;
    }
#endif
    if (send && !authorization_test_ready) {
        line("{\"event\":\"whitepeace_rejected\",\"reason\":\"authorization_selftest_not_passed\"}\n"); return;
    }
    uintptr_t array=0,fra=0,eng=0;
    uint64_t actor=0,recipient=0;
    int32_t date=0;
    if (!read(database+0x118,array) || !read(array+122*8,fra) || !read(array+46*8,eng)
        || !read(fra+0x20,actor) || !read(eng+0x20,recipient) || !read(game+0x1dd0,date)
        || ((actor>>32)&0xffff)!=122 || (actor&0xffffff)!=0x415246
        || ((recipient>>32)&0xffff)!=46 || (recipient&0xffffff)!=0x474e45) {
        line("{\"event\":\"action_roundtrip_rejected\",\"reason\":\"country_identity\"}\n"); return;
    }
    uintptr_t dispatcher=0;
    if (send) {
        uintptr_t root=0,context=0,transport=0,vtable=0,submit=0;
        int32_t country_last_date=0,global_last_date=0;
        uint64_t global_last_actor=0,player=0;
        bool player_valid=read(game+0x1e60,player) && player==recipient;
#ifdef BRIDGE_TEST_AI_RECIPIENT
        uintptr_t por=0;
        uint64_t observer=0;
        player_valid=read(game+0x1e60,player) && read(array+189*8,por)
            && read(por+0x20,observer) && ((observer>>32)&0xffff)==189
            && (observer&0xffffff)==0x524f50 && player==observer && player!=actor && player!=recipient;
        if (player_valid) line("{\"event\":\"ai_recipient_context\",\"player\":\"POR\",\"actor\":\"FRA\",\"recipient\":\"ENG\",\"recipient_is_player\":false}\n");
#endif
        bool valid = player_valid
            && read(base+0x2349550,root) && read(root+0x330,context)
            && read(context+0x370,dispatcher) && read(dispatcher+0x58,transport)
            && read(transport,vtable) && read(vtable+0x30,submit) && submit==base+0x1580270
            && read(fra+0x24a0,country_last_date) && read(game+0x1d9c,global_last_date)
            && read(game+0x1da0,global_last_actor);
        if (!valid) { line("{\"event\":\"whitepeace_rejected\",\"reason\":\"context_identity\"}\n"); return; }
        if (date<=country_last_date || (((global_last_actor>>32)&0xffff)==122 && date<=global_last_date)) {
            line("{\"event\":\"whitepeace_rejected\",\"reason\":\"native_date_guard\"}\n"); return;
        }
    }
    line(send?(gold?"{\"event\":\"gold_peace_begin\",\"actor\":\"FRA\",\"recipient\":\"ENG\"}\n":
        "{\"event\":\"whitepeace_begin\",\"actor\":\"FRA\",\"recipient\":\"ENG\"}\n"):
        "{\"event\":\"action_roundtrip_begin\",\"actor\":\"FRA\",\"recipient\":\"ENG\",\"send\":false}\n");
    alignas(16) unsigned char offer[0x1c0] = {};
    alignas(16) unsigned char action[0x210] = {};
    using OfferCtor = void* (*)(void*,uint64_t,uint64_t,unsigned char);
    using OfferDtor = void (*)(void*);
    using ActionCtor = void* (*)(void*,uint64_t,uint64_t,unsigned char,const void*,int32_t);
    using ActionDtor = void* (*)(void*,unsigned int);
    using Wrap = void** (*)(void*,void**);
    // Full native constructor: RDX -> claimant/+18, R8 -> payer/+10,
    // R9B -> direction/+20. It initializes war participants and derived data.
    reinterpret_cast<OfferCtor>(base+0x975bb0)(offer,actor,recipient,1);
    uint64_t payer=0,claimant=0;
    memcpy(&payer,offer+0x10,8); memcpy(&claimant,offer+0x18,8);
    bool fields_valid=payer==recipient && claimant==actor && offer[0x20]==1;
    bool participants_valid=true;
    const unsigned participant_offsets[]={0x28,0x40,0x58,0x70};
    for (unsigned offset : participant_offsets) {
        uintptr_t begin=0,end=0,capacity=0;
        bool valid=read(reinterpret_cast<uintptr_t>(offer)+offset,begin)
            && read(reinterpret_cast<uintptr_t>(offer)+offset+8,end)
            && read(reinterpret_cast<uintptr_t>(offer)+offset+16,capacity)
            && begin>=0x10000 && end>begin && capacity>=end
            && (end-begin)%8==0 && (end-begin)/8<=4096;
        for (uintptr_t address=begin; valid && address<end; address+=8) {
            uint64_t handle=0,actual=0; uintptr_t country=0;
            valid=read(address,handle) && ((handle>>32)&0xffff)<4096
                && read(array+((handle>>32)&0xffff)*8,country)
                && read(country+0x20,actual) && actual==handle;
            if (valid) {
                char member_message[160];
                snprintf(member_message,sizeof(member_message),"{\"event\":\"war_context_member\",\"offset\":%u,\"handle\":\"0x%llx\",\"tag\":\"%c%c%c\"}\n",
                    offset,static_cast<unsigned long long>(handle),static_cast<char>(handle),static_cast<char>(handle>>8),static_cast<char>(handle>>16));
                line(member_message);
            }
        }
        uint64_t leader=0;
        valid=valid && read(begin,leader) && leader==((offset==0x28 || offset==0x58)?recipient:actor);
        participants_valid=participants_valid&&valid;
        char message[180];
        snprintf(message,sizeof(message),"{\"event\":\"war_context_vector\",\"offset\":%u,\"count\":%llu,\"country_handles_valid\":%s}\n",
            offset,static_cast<unsigned long long>(end>=begin?(end-begin)/8:0),valid?"true":"false");
        line(message);
    }
    if (!fields_valid || !participants_valid) {
        line("{\"event\":\"action_roundtrip_rejected\",\"reason\":\"native_war_participants_invalid\"}\n");
        reinterpret_cast<OfferDtor>(base+0x976030)(offer); return;
    }
    if (gold) {
        // Reuse the offer-level methods called by the native money UI. These
        // update the money clause and its aggregate; never write +0xf0 directly.
        using GoldLimit = int32_t* (*)(void*,int32_t*,const int32_t*);
        using GoldSet = void (*)(void*,const int32_t*);
        using GoldGet = int32_t* (*)(void*,int32_t*);
        using Cost = int32_t (*)(void*,unsigned char);
        // Native + callback converts score step 1000 into a currency delta.
        // Native central updater independently obtains the ceiling from 100000,
        // clamps the currency value, then rounds it to 100-unit precision.
        int32_t score_step=1000,score_ceiling=100000,delta=0,ceiling=0;
        int32_t amount=0,actual=0,aggregate=0;
        reinterpret_cast<GoldLimit>(base+0x97b3a0)(offer,&delta,&score_step);
        reinterpret_cast<GoldLimit>(base+0x97b3a0)(offer,&ceiling,&score_ceiling);
        if (delta>0 && ceiling>0) {
            amount=delta<ceiling?delta:ceiling;
            amount=static_cast<int32_t>((static_cast<int64_t>(amount)+50)/100*100);
            reinterpret_cast<GoldSet>(base+0x97b200)(offer,&amount);
            reinterpret_cast<GoldGet>(base+0x97b130)(offer,&actual);
        }
        memcpy(&aggregate,offer+0xf0,4);
        bool money_valid=amount>0 && actual==amount && aggregate==1000;
        int32_t cost=money_valid?reinterpret_cast<Cost>(base+0x978ed0)(offer,1):0;
        char terms[320];
        snprintf(terms,sizeof(terms),"{\"event\":\"native_gold_terms\",\"score_step_raw\":%d,\"currency_delta_raw\":%d,\"currency_ceiling_raw\":%d,\"currency_requested_raw\":%d,\"currency_clause_raw\":%d,\"aggregate_f0\":%d,\"native_cost_raw\":%d,\"valid\":%s,\"send\":%s}\n",
            score_step,delta,ceiling,amount,actual,aggregate,cost,money_valid?"true":"false",send?"true":"false");
        line(terms);
        if (!money_valid) {
            reinterpret_cast<OfferDtor>(base+0x976030)(offer);
            line("{\"event\":\"native_gold_rejected\",\"reason\":\"clause_or_aggregate_mismatch\"}\n"); return;
        }
    }
    reinterpret_cast<ActionCtor>(base+0x598b20)(action,actor,recipient,1,offer,date);
    uintptr_t action_vtable=0,owner=0;
    memcpy(&action_vtable,action,8); memcpy(&owner,action+0x48+0xe8,8);
    bool identity = action_vtable==base+0x1c7b840 && owner==reinterpret_cast<uintptr_t>(action+0x48);
    if (send && identity) {
        // Follow the native button's thread-local reason context and preview step.
        // The pool owns the context; the original callback does not free it.
        using ReasonContext = void* (*)(void*,bool*);
        using Reset = void (*)(void*);
        using Reserve = void (*)(void*,unsigned int);
        using Preview = int (*)(void*,void*,unsigned char);
        bool existed=false;
        void* reasons=reinterpret_cast<ReasonContext>(base+0xdf320)(reinterpret_cast<void*>(base+0x1fd1c38),&existed);
        if (!reasons) identity=false;
        else {
            reinterpret_cast<Reset>(base+0x5ae8d0)(reasons);
            uintptr_t begin=0,capacity=0;
            if (!read(reinterpret_cast<uintptr_t>(reasons),begin)
                || !read(reinterpret_cast<uintptr_t>(reasons)+0x10,capacity) || capacity<begin
                || (capacity-begin)%48!=0) identity=false;
            else {
                if ((capacity-begin)/48<40) reinterpret_cast<Reserve>(base+0x5aeba0)(reasons,40);
                int value=reinterpret_cast<Preview>(base+0x59bf10)(action,reasons,0);
                if (value>=1) action[0x208]=1;
                char message[128];
                snprintf(message,sizeof(message),"{\"event\":\"%s\",\"raw_result\":%d,\"native_flag_208\":%u}\n",gold?"gold_peace_native_preview":"whitepeace_native_preview",value,action[0x208]);
                line(message);
            }
        }
    }
    void* command=nullptr;
    void** output=nullptr;
    bool submitted=false;
    uint64_t test_id=0;
    bool test_propagated=false,test_cleaned=false,test_unseeded=false;
    if (!send && identity) {
        void* unseeded=authorized_clone(action);
        test_unseeded=unseeded && authorization_get(reinterpret_cast<uintptr_t>(unseeded))==0;
        if (unseeded) authorized_destructor(unseeded,1);
        test_id=++next_authorization;
        if (!authorization_add(reinterpret_cast<uintptr_t>(action),test_id)) identity=false;
    }
    if (identity) output=reinterpret_cast<Wrap>(base+0x4e9960)(action,&command);
    bool wrapped=false;
    if (command) {
        uintptr_t command_vtable=0,clone=0,clone_vtable=0;
        uint64_t clone_actor=0,clone_recipient=0;
        wrapped=output==&command && read(reinterpret_cast<uintptr_t>(command),command_vtable)
            && command_vtable==base+0x1c814b0 && read(reinterpret_cast<uintptr_t>(command)+0x50,clone)
            && read(clone,clone_vtable) && clone_vtable==base+0x1c7b840
            && read(clone+0x10,clone_actor) && read(clone+0x20,clone_recipient)
            && clone_actor==actor && clone_recipient==recipient;
        if (gold) {
            int32_t clone_gold=0;
            wrapped=wrapped && read(clone+0x48+0xf0,clone_gold) && clone_gold==1000;
        }
        if (!send) test_propagated=wrapped && authorization_get(clone)==test_id && test_id!=0;
        // Verify that the queued action owns independent participant vectors
        // with exactly the same contents as the complete source offer.
        for (unsigned offset : participant_offsets) {
            uintptr_t source_begin=0,source_end=0,clone_begin=0,clone_end=0;
            bool copied=read(reinterpret_cast<uintptr_t>(offer)+offset,source_begin)
                && read(reinterpret_cast<uintptr_t>(offer)+offset+8,source_end)
                && read(clone+0x48+offset,clone_begin) && read(clone+0x48+offset+8,clone_end)
                && clone_begin>=0x10000 && clone_end>=clone_begin && clone_begin!=source_begin
                && clone_end-clone_begin==source_end-source_begin;
            for (uintptr_t pos=0; copied && pos<source_end-source_begin; pos+=8) {
                uint64_t source_handle=0,clone_handle=0;
                copied=read(source_begin+pos,source_handle) && read(clone_begin+pos,clone_handle)
                    && source_handle==clone_handle;
            }
            wrapped=wrapped&&copied;
        }
        if (send && wrapped) {
#ifdef BRIDGE_DISPATCH_DIAGNOSTICS
            // Match the executor's first gate exactly: RCX=queued clone,
            // RDX=null, R8B=0. This is a diagnostic preflight, not a forced result.
            uintptr_t validity_method=0;
            int32_t state_before=0,state_after=0;
            bool gate_identity=read(clone_vtable+0x80,validity_method)
                && validity_method==base+0x59b480 && read(clone+0x34,state_before);
            bool native_valid=false;
            if (gate_identity) {
                using Validity = bool (*)(void*,void*,unsigned char);
                native_valid=reinterpret_cast<Validity>(validity_method)(reinterpret_cast<void*>(clone),nullptr,0);
            }
            bool state_read=read(clone+0x34,state_after);
            char diagnostic[320];
            snprintf(diagnostic,sizeof(diagnostic),"{\"event\":\"peace_dispatch_preflight\",\"method_rva\":\"0x%llx\",\"identity_valid\":%s,\"native_valid\":%s,\"state_before\":%d,\"state_after\":%d,\"state_read\":%s,\"flag_208\":%u}\n",
                static_cast<unsigned long long>(validity_method?validity_method-base:0),gate_identity?"true":"false",
                native_valid?"true":"false",state_before,state_after,state_read?"true":"false",
                *reinterpret_cast<unsigned char*>(clone+0x208));
            line(diagnostic);
            wrapped=gate_identity && native_valid && state_read && state_before==0 && state_after==0;
            if (!wrapped) line("{\"event\":\"peace_dispatch_preflight_stopped\",\"forced_result\":false}\n");
#endif
        }
        if (send && wrapped) {
            using Submit = bool (*)(void*,void**);
            uint64_t id=++next_authorization;
            if (!authorization_add(clone,id)) {
                line("{\"event\":\"authorization_seed_failed\"}\n");
            } else {
                char seed[200];
                snprintf(seed,sizeof(seed),"{\"event\":\"llm_peace_authorization_seed\",\"authorization\":%llu,\"action\":\"0x%llx\"}\n",
                    static_cast<unsigned long long>(id),static_cast<unsigned long long>(clone));
                line(seed);
                submitted=reinterpret_cast<Submit>(base+0x14ca110)(reinterpret_cast<void*>(dispatcher),&command);
            }
            // The engine takes ownership by clearing this pointer container.
            // Do not destroy a queued command or its independent cloned action.
        }
        if (command) {
            reinterpret_cast<ActionDtor>(base+0x4e74a0)(command,1);
            if (!send) test_cleaned=authorization_get(clone)==0;
        }
    }
    if (!send) {
        authorization_remove(reinterpret_cast<uintptr_t>(action));
        authorization_test_ready=identity && wrapped && test_propagated && test_cleaned && test_unseeded;
        line(authorization_test_ready?"{\"event\":\"authorization_selftest_passed\",\"native_clone_propagated\":true,\"native_destructor_revoked\":true,\"submitted\":false}\n":
            "{\"event\":\"authorization_selftest_failed\",\"submitted\":false}\n");
    }
    reinterpret_cast<ActionDtor>(base+0x598b90)(action,0);
    reinterpret_cast<OfferDtor>(base+0x976030)(offer);
    if (send) {
        if (gold) line(submitted?"{\"event\":\"gold_peace_submitted\",\"accepted\":\"unknown\"}\n":
            "{\"event\":\"gold_peace_not_submitted\"}\n");
        else line(submitted?"{\"event\":\"whitepeace_submitted\",\"accepted\":\"unknown\"}\n":
            "{\"event\":\"whitepeace_not_submitted\"}\n");
    }
    else line(identity&&wrapped?"{\"event\":\"action_roundtrip_ok\",\"send\":false}\n":
        "{\"event\":\"action_roundtrip_identity_failed\",\"send\":false}\n");
}

extern "C" void bridge_frame_tick(void* frame_context) {
    if (InterlockedCompareExchange(&inside, 1, 0)) return;
    DWORD tid = GetCurrentThreadId();
    if (!frame_thread) frame_thread = tid;
    if (tid != frame_thread) thread_changed = true;
    LONG count = InterlockedIncrement(&frame_count);
    ULONGLONG now = GetTickCount64();
    if (now-last_log >= 1000) {
        last_log = now;
        LONG packet_available=InterlockedCompareExchange(&packet_count,0,0);
        if (packet_available>64) packet_available=64;
        while (packet_consumed<packet_available) {
            auto& event=packet_events[packet_consumed];
            if (!InterlockedCompareExchange(&event.ready,0,0)) break;
            char message[200];
            snprintf(message,sizeof(message),"{\"event\":\"authorization_transport_identity\",\"key\":\"0x%llx\",\"authorization\":%llu,\"phase\":%u}\n",
                static_cast<unsigned long long>(event.key),static_cast<unsigned long long>(event.id),event.phase);
            line(message); ++packet_consumed;
        }
        LONG lineage_available=InterlockedCompareExchange(&lineage_count,0,0);
        if (lineage_available>64) lineage_available=64;
        while (lineage_consumed<lineage_available) {
            auto& event=lineage_events[lineage_consumed];
            if (!InterlockedCompareExchange(&event.ready,0,0)) break;
            char message[240];
            snprintf(message,sizeof(message),"{\"event\":\"authorization_native_clone\",\"source\":\"0x%llx\",\"result\":\"0x%llx\",\"authorization\":%llu,\"propagated\":%s}\n",
                static_cast<unsigned long long>(event.source),static_cast<unsigned long long>(event.result),
                static_cast<unsigned long long>(event.id),event.added?"true":"false");
            line(message); ++lineage_consumed;
        }
#ifdef BRIDGE_TRACE_PEACE_RESPONSES
        LONG available=InterlockedCompareExchange(&response_count,0,0);
        if (available>64) available=64;
        while (response_consumed<available) {
            ResponseEvent& event=response_events[response_consumed];
            if (!InterlockedCompareExchange(&event.ready,0,0)) break;
            char response[400];
            const char* entry_event="native_peace_response_entry";
#ifdef BRIDGE_TRACE_COMMAND_EXECUTION
            entry_event="native_peace_command_execute_entry";
#endif
            if (event.authorization) entry_event="llm_authorized_peace_execute_entry";
            if (event.authority_blocked) entry_event="native_peace_authority_blocked";
            snprintf(response,sizeof(response),"{\"event\":\"%s\",\"thread\":%lu,\"actor_handle\":\"0x%llx\",\"recipient_handle\":\"0x%llx\",\"state_raw\":%d,\"date_raw\":%d,\"direction\":%u,\"preview_flag\":%u,\"gold_cost_raw\":%d,\"authorization\":%llu}\n",entry_event,
                static_cast<unsigned long>(event.thread),static_cast<unsigned long long>(event.actor),
                static_cast<unsigned long long>(event.recipient),event.state,event.date,event.direction,event.preview_flag,event.gold_cost,static_cast<unsigned long long>(event.authorization));
            line(response); ++response_consumed;
        }
#endif
        uintptr_t game=0, database=0, array=0, country=0;
        uint64_t handle=0, object_handle=0;
        bool valid = read(base+0x233fe58,game) && read(base+0x233d8b0,database)
            && read(game+0x1e60,handle) && read(database+0x118,array);
        unsigned slot = static_cast<unsigned>((handle>>32)&0xffff);
        valid = valid && slot<4096 && read(array+slot*8,country)
            && read(country+0x20,object_handle) && handle==object_handle;
        char tag[4] = {static_cast<char>(handle),static_cast<char>(handle>>8),static_cast<char>(handle>>16),0};
        uintptr_t context=0,dispatcher=0,transport=0;
        uintptr_t ui_root=0;
        bool dispatch_valid = read(base+0x2349550,ui_root) && read(ui_root+0x330,context)
            && read(context+0x370,dispatcher) && read(dispatcher+0x58,transport) && transport!=0;
        char output[512];
        snprintf(output,sizeof(output),"{\"event\":\"frame\",\"thread\":%lu,\"frames\":%ld,\"thread_changed\":%s,\"country_valid\":%s,\"player\":\"%.3s\",\"frame_context\":\"0x%llx\",\"dispatcher\":\"0x%llx\",\"dispatch_chain_readable\":%s}\n",
            static_cast<unsigned long>(tid),static_cast<long>(count),thread_changed?"true":"false",valid?"true":"false",tag,
            static_cast<unsigned long long>(reinterpret_cast<uintptr_t>(frame_context)),
            static_cast<unsigned long long>(dispatcher),dispatch_valid?"true":"false");
        line(output);
        if (valid && !thread_changed && count>=100 && !authorization_test_attempted) {
            authorization_test_attempted=true;
            action_roundtrip(database,game);
        }
        // Optional one-shot command, processed only on the observed frame thread.
        // It constructs and destroys an empty offer; it never submits anything.
        if (valid && !thread_changed && count>=100 && GetFileAttributesW(roundtrip_path)!=INVALID_FILE_ATTRIBUTES) {
            if (DeleteFileW(roundtrip_path)) {
                line("{\"event\":\"roundtrip_begin\"}\n");
                alignas(16) unsigned char offer[0x1c0] = {};
                using Constructor = void* (*)(void*);
                using Destructor = void (*)(void*);
                reinterpret_cast<Constructor>(base+0x2c68c0)(offer);
                uintptr_t vtable=0,owner=0;
                memcpy(&vtable,offer,8); memcpy(&owner,offer+0xe8,8);
                bool identity = vtable==base+0x1c578b8 && owner==reinterpret_cast<uintptr_t>(offer);
                reinterpret_cast<Destructor>(base+0x976030)(offer);
                line(identity?"{\"event\":\"roundtrip_ok\"}\n":"{\"event\":\"roundtrip_identity_failed\"}\n");
            }
        }
        if (valid && !thread_changed && count>=100 && GetFileAttributesW(action_path)!=INVALID_FILE_ATTRIBUTES
            && DeleteFileW(action_path)) action_roundtrip(database,game);
        if (valid && !thread_changed && count>=100 && GetFileAttributesW(whitepeace_path)!=INVALID_FILE_ATTRIBUTES
            && DeleteFileW(whitepeace_path)) action_roundtrip(database,game,true);
        if (valid && !thread_changed && count>=100 && GetFileAttributesW(gold_test_path)!=INVALID_FILE_ATTRIBUTES
            && DeleteFileW(gold_test_path)) action_roundtrip(database,game,false,true);
        if (valid && !thread_changed && count>=100 && GetFileAttributesW(gold_send_path)!=INVALID_FILE_ATTRIBUTES
            && DeleteFileW(gold_send_path)) action_roundtrip(database,game,true,true);
    }
    InterlockedExchange(&inside,0);
}

extern "C" __declspec(dllexport) DWORD WINAPI BridgeStart(void*) {
    if (InterlockedCompareExchange(&started,1,0)) return 10;
    wchar_t directory[MAX_PATH];
    DWORD length=GetModuleFileNameW(self_module,directory,MAX_PATH);
    if (!length || length>=MAX_PATH) return 11;
    wchar_t* slash=wcsrchr(directory,L'\\');
    if (!slash) return 11;
    *slash=0;
    wchar_t path[MAX_PATH];
    if (swprintf(path,MAX_PATH,L"%ls\\probe.jsonl",directory)<0 ||
        swprintf(roundtrip_path,MAX_PATH,L"%ls\\roundtrip.request",directory)<0 ||
        swprintf(action_path,MAX_PATH,L"%ls\\action-roundtrip.request",directory)<0 ||
        swprintf(whitepeace_path,MAX_PATH,L"%ls\\whitepeace.request",directory)<0 ||
        swprintf(gold_test_path,MAX_PATH,L"%ls\\gold-roundtrip.request",directory)<0 ||
        swprintf(gold_send_path,MAX_PATH,L"%ls\\gold-peace.request",directory)<0) return 11;
    log_file=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
    if (log_file==INVALID_HANDLE_VALUE) return 12;
    // A stale request must not trigger a native call during first installation.
    if (GetFileAttributesW(roundtrip_path)!=INVALID_FILE_ATTRIBUTES && !DeleteFileW(roundtrip_path)) return 13;
    if (GetFileAttributesW(action_path)!=INVALID_FILE_ATTRIBUTES && !DeleteFileW(action_path)) return 13;
    if (GetFileAttributesW(whitepeace_path)!=INVALID_FILE_ATTRIBUTES && !DeleteFileW(whitepeace_path)) return 13;
    if (GetFileAttributesW(gold_test_path)!=INVALID_FILE_ATTRIBUTES && !DeleteFileW(gold_test_path)) return 13;
    if (GetFileAttributesW(gold_send_path)!=INVALID_FILE_ATTRIBUTES && !DeleteFileW(gold_send_path)) return 13;
    base=reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
    auto serialize_slot=reinterpret_cast<void**>(base+0x1c814b0+0x10);
    if (*serialize_slot!=reinterpret_cast<void*>(base+0x4e8470)) return 23;
    auto lifecycle_slots=reinterpret_cast<void**>(base+0x1c7b840);
    if (lifecycle_slots[0]!=reinterpret_cast<void*>(base+0x598b90)
        || lifecycle_slots[0xb0/8]!=reinterpret_cast<void*>(base+0x59ba70)) {
        line("{\"event\":\"authorization_lifecycle_identity_failed\"}\n"); return 22;
    }
#ifdef BRIDGE_TRACE_PEACE_RESPONSES
    uintptr_t trace_slot_rva=0x1c7b840+0x48,trace_original_rva=0x598f00;
#ifdef BRIDGE_TRACE_COMMAND_EXECUTION
    trace_slot_rva=0x1c814b0+0x48; trace_original_rva=0x4e7c80;
#endif
    auto response_slot=reinterpret_cast<void**>(base+trace_slot_rva);
    uintptr_t response_method=0;
    if (!read(reinterpret_cast<uintptr_t>(response_slot),response_method) || response_method!=base+trace_original_rva) {
        line("{\"event\":\"response_slot_identity_failed\"}\n"); return 20;
    }
    bridge_response_original=reinterpret_cast<void*>(response_method);
#endif
    auto target=reinterpret_cast<unsigned char*>(base+0x10a6d90);
    unsigned char actual[20]; SIZE_T n=0;
    if (!ReadProcessMemory(GetCurrentProcess(),target,actual,20,&n) || n!=20 || memcmp(actual,expected,20)) {
        line("{\"event\":\"signature_mismatch\"}\n"); return 14;
    }
    auto trampoline=static_cast<unsigned char*>(VirtualAlloc(nullptr,34,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    if (!trampoline) return 15;
    memcpy(trampoline,expected,20); absolute_jump(trampoline+20,reinterpret_cast<uintptr_t>(target+20));
    DWORD old=0;
    if (!VirtualProtect(trampoline,34,PAGE_EXECUTE_READ,&old)) return 16;
    FlushInstructionCache(GetCurrentProcess(),trampoline,34);
    bridge_trampoline=trampoline;
    unsigned char patch[20]; memset(patch,0x90,20);
    absolute_jump(patch,reinterpret_cast<uintptr_t>(&bridge_frame_stub));

    // Prepare all allocations/handles before suspending other threads.
    HANDLE threads[2048]; size_t thread_count=0;
    HANDLE snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD,0);
    if (snapshot==INVALID_HANDLE_VALUE) return 17;
    THREADENTRY32 entry{}; entry.dwSize=sizeof(entry);
    bool enumeration_ok=Thread32First(snapshot,&entry);
    bool handles_ok=enumeration_ok;
    if (enumeration_ok) do {
        if (entry.th32OwnerProcessID==GetCurrentProcessId() && entry.th32ThreadID!=GetCurrentThreadId()) {
            HANDLE h=OpenThread(THREAD_SUSPEND_RESUME|THREAD_GET_CONTEXT,FALSE,entry.th32ThreadID);
            if (!h) { handles_ok=false; break; }
            if (thread_count==2048) { CloseHandle(h); handles_ok=false; break; }
            threads[thread_count++]=h;
        }
    } while (Thread32Next(snapshot,&entry));
    CloseHandle(snapshot);
    size_t suspended=0;
    bool safe=handles_ok && thread_count>0;
    if (safe) for (size_t i=0;i<thread_count;++i) {
        HANDLE h=threads[i];
        if (SuspendThread(h)==static_cast<DWORD>(-1)) { safe=false; break; }
        ++suspended;
        CONTEXT context{}; context.ContextFlags=CONTEXT_CONTROL;
        if (!GetThreadContext(h,&context) || (context.Rip>=reinterpret_cast<uintptr_t>(target) &&
            context.Rip<reinterpret_cast<uintptr_t>(target+20))) { safe=false; break; }
    }
    bool patched=false, protection_restored=true, rollback_complete=true;
    bool lifecycle_patched=false; DWORD lifecycle_old=0;
    bool serialize_patched=false; DWORD serialize_old=0;
#ifdef BRIDGE_TRACE_PEACE_RESPONSES
    bool response_patched=false;
    DWORD response_old=0;
#endif
    if (safe && VirtualProtect(target,20,PAGE_EXECUTE_READWRITE,&old)) {
        // Verify again after every existing thread has stopped.
        if (!memcmp(target,expected,20)) {
            memcpy(target,patch,20); FlushInstructionCache(GetCurrentProcess(),target,20); patched=true;
#ifdef BRIDGE_TRACE_PEACE_RESPONSES
            if (*response_slot==bridge_response_original && VirtualProtect(response_slot,8,PAGE_READWRITE,&response_old)) {
                InterlockedExchangePointer(reinterpret_cast<void* volatile*>(response_slot),reinterpret_cast<void*>(&bridge_response_stub));
                response_patched=true;
                DWORD response_ignored;
                if (!VirtualProtect(response_slot,8,response_old,&response_ignored)) {
                    // A failed protection change leaves this slot writable.
                    InterlockedExchangePointer(reinterpret_cast<void* volatile*>(response_slot),bridge_response_original);
                    response_patched=false;
                    VirtualProtect(response_slot,8,response_old,&response_ignored);
                    memcpy(target,expected,20); FlushInstructionCache(GetCurrentProcess(),target,20);
                    patched=false; protection_restored=false;
                }
            } else {
                memcpy(target,expected,20); FlushInstructionCache(GetCurrentProcess(),target,20); patched=false;
            }
#endif
        }
        DWORD ignored;
        if (!VirtualProtect(target,20,old,&ignored)) {
            // Do not leave an installed hook behind an installation error.
            // This failed call leaves the frame page writable.
            memcpy(target,expected,20); FlushInstructionCache(GetCurrentProcess(),target,20);
            patched=false; protection_restored=false;
            VirtualProtect(target,20,old,&ignored);
#ifdef BRIDGE_TRACE_PEACE_RESPONSES
            if (response_patched) {
                DWORD temporary=0;
                if (VirtualProtect(response_slot,8,PAGE_READWRITE,&temporary)) {
                    InterlockedExchangePointer(reinterpret_cast<void* volatile*>(response_slot),bridge_response_original);
                    response_patched=false;
                    VirtualProtect(response_slot,8,response_old,&temporary);
                } else rollback_complete=false;
            }
#endif
        }
    }

    if (patched) {
        if (VirtualProtect(serialize_slot,8,PAGE_READWRITE,&serialize_old)) {
            *serialize_slot=reinterpret_cast<void*>(&authorized_serialize);
            serialize_patched=true;
            DWORD ignored=0;
            if (!VirtualProtect(serialize_slot,8,serialize_old,&ignored)) {
                *serialize_slot=reinterpret_cast<void*>(base+0x4e8470);
                serialize_patched=false;
                VirtualProtect(serialize_slot,8,serialize_old,&ignored);
            }
        }
        if (serialize_patched && lifecycle_slots[0]==reinterpret_cast<void*>(base+0x598b90)
            && lifecycle_slots[0xb0/8]==reinterpret_cast<void*>(base+0x59ba70)
            && VirtualProtect(lifecycle_slots,0xb8,PAGE_READWRITE,&lifecycle_old)) {
            lifecycle_slots[0]=reinterpret_cast<void*>(&authorized_destructor);
            lifecycle_slots[0xb0/8]=reinterpret_cast<void*>(&authorized_clone);
            lifecycle_patched=true;
            DWORD ignored=0;
            if (!VirtualProtect(lifecycle_slots,0xb8,lifecycle_old,&ignored)) {
                lifecycle_slots[0]=reinterpret_cast<void*>(base+0x598b90);
                lifecycle_slots[0xb0/8]=reinterpret_cast<void*>(base+0x59ba70);
                lifecycle_patched=false;
                VirtualProtect(lifecycle_slots,0xb8,lifecycle_old,&ignored);
            }
        }
        if (!lifecycle_patched) {
            DWORD temporary=0;
            if (serialize_patched) {
                if (VirtualProtect(serialize_slot,8,PAGE_READWRITE,&temporary)) {
                    *serialize_slot=reinterpret_cast<void*>(base+0x4e8470);
                    DWORD ignored=0; VirtualProtect(serialize_slot,8,serialize_old,&ignored);
                } else rollback_complete=false;
            }
            if (VirtualProtect(target,20,PAGE_EXECUTE_READWRITE,&temporary)) {
                memcpy(target,expected,20); FlushInstructionCache(GetCurrentProcess(),target,20);
                DWORD ignored=0; VirtualProtect(target,20,temporary,&ignored);
            } else rollback_complete=false;
            if (VirtualProtect(response_slot,8,PAGE_READWRITE,&temporary)) {
                *response_slot=bridge_response_original;
                DWORD ignored=0; VirtualProtect(response_slot,8,temporary,&ignored);
            } else rollback_complete=false;
            patched=false;
        }
    }
    for (size_t i=0;i<suspended;++i) ResumeThread(threads[i]);
    for (size_t i=0;i<thread_count;++i) CloseHandle(threads[i]);
    if (!patched) {
        line(rollback_complete?"{\"event\":\"hook_not_installed\",\"hooks_rolled_back\":true}\n":
            "{\"event\":\"hook_rollback_incomplete\",\"restart_required\":true}\n");
        return rollback_complete?18:21;
    }
#ifdef BRIDGE_TRACE_PEACE_RESPONSES
    char trace_installed[240];
    snprintf(trace_installed,sizeof(trace_installed),"{\"event\":\"%s\",\"slot_rva\":\"0x%llx\",\"original_rva\":\"0x%llx\",\"mutates_actions\":false,\"capacity\":64}\n",
#ifdef BRIDGE_TRACE_COMMAND_EXECUTION
        "command_execution_trace_installed",
#else
        "response_trace_installed",
#endif
        static_cast<unsigned long long>(trace_slot_rva),static_cast<unsigned long long>(trace_original_rva));
    line(trace_installed);
#endif
#ifdef BRIDGE_PEACE_AUTHORITY_LOCK
    line("{\"event\":\"peace_authority_lock_installed\",\"authorization_lineage\":\"native_clone_and_transport_sequence_sidecar\",\"controlled_country\":\"FRA\",\"scope\":\"verified_native_peace_actions_involving_FRA\",\"bridge_sending_enabled\":true,\"other_diplomacy_locked\":false}\n");
#endif
    line(protection_restored?"{\"event\":\"hook_installed\",\"mode\":\"observe\"}\n":
        "{\"event\":\"hook_installed_protection_restore_failed\"}\n");
    return protection_restored?0:19;
}

BOOL WINAPI DllMain(HINSTANCE module,DWORD reason,LPVOID) {
    if (reason==DLL_PROCESS_ATTACH) { self_module=module; DisableThreadLibraryCalls(module); }
    return TRUE;
}
