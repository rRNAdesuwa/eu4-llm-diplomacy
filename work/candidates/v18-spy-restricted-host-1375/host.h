#pragma once
#include "codec.h"

namespace eu4_spy_host18 {
struct Frame {
    eu4_spy18::Stamp stamp;
    std::uint32_t countries_count,thread;
    std::uint64_t actor_overlord,target_overlord,effective_player;
    std::uint8_t manual_pause,reset,ironman,selector,alternate_selector;
    std::int32_t native_speed_index;
    bool multiplayer_classifier;
    std::uintptr_t load_source;
};
struct Environment {
    void* user;Identity identity;std::uintptr_t image_base;std::uint32_t owner_thread;
    bool mock,exact_disk_and_loaded_image_verified;
    eu4_spy18::Read read;eu4_spy18::WriteOwned write;eu4_spy18::Resolve resolve;
    eu4_spy18::Clock clock;
    bool (*sample)(void*,Frame*);
    std::uint32_t (*current_thread)(void*);
    bool (*begin_frame)(void*);
};
// Journal writes are one-shot. Short write, flush or close failures are terminal.
struct Journal {
    void* user;
    bool (*append)(void*,const char*,std::size_t);
    bool (*claim)(void*,std::uint32_t,const char*,std::size_t);
};
enum class State:unsigned { cold,ready,running,awaiting_health,complete,frozen };
enum class Failure:unsigned { none,already_started,bad_environment,wrong_thread,reentered,clock_regressed,
    unavailable_world,changed_world,invalid_request,wrong_sequence,claim_failed,expired,audit_failed,
    core_failed,owned_write_contract,read_budget,unsupported_owner_hook };
struct Status {
    State state;Failure failure;std::uint32_t claimed,completed;
    std::uint64_t frames,last_health_frame,last_health_time;
    bool owner_hook_installed,loader_implemented,send_supported,runtime_verified,strict_sp_verified,epoch_verified,production_ready;
};
// No reset/rearm, exported ABI or external mutation API. A future owner hook
// would call frame() with one explicitly supplied canonical stage packet.
// There is deliberately no owner hook installer or file-input consumer here.
class Controller {
public:
    Controller() noexcept;
    Controller(const Controller&)=delete;Controller& operator=(const Controller&)=delete;
    bool start(const Environment&,const Journal&);
    bool frame(const char* packet=nullptr,std::size_t length=0);
    Status status() const noexcept;
private:
    volatile LONG started_,active_,frozen_,failure_;
    Environment env_;Journal journal_;eu4_spy18::Core core_;
    Status status_;Frame locked_;bool locked_valid_,audit_failed_;
    Request active_request_;std::uint64_t clock_,ordinal_,completion_frame_;
    std::uint32_t read_calls_;std::size_t read_bytes_;
    eu4_spy18::Step current_step_;std::uint32_t current_family_,original_id_,write_index_;
    std::uintptr_t owned_base_;bool factory_return_verified_;
    bool fail(Failure);
    bool sample(Frame&);
    bool barrier(bool expiry);
    bool append(const char*,int,bool diagnostic=false);
    bool host_record(const char* event,const eu4_spy18::Result* result=nullptr,bool current_observation=true);
    bool execute_frame(const char*,std::size_t);
    bool core_log(const eu4_spy18::Event*);
    bool owned_write(std::uintptr_t,const void*,std::size_t);
    static bool read_cb(void*,std::uintptr_t,void*,std::size_t);
    static bool write_cb(void*,std::uintptr_t,const void*,std::size_t);
    static std::uintptr_t resolve_cb(void*,std::uintptr_t);
    static std::uint64_t clock_cb(void*);
    static bool guard_cb(void*,eu4_spy18::GuardPoint,eu4_spy18::Stage,eu4_spy18::Step,const eu4_spy18::Stamp*);
    static bool log_cb(void*,const eu4_spy18::Event*);
};
bool same_frame(const Frame&,const Frame&) noexcept;
} // namespace eu4_spy_host18
