#pragma once
#include "preflight/host.h"
#include "core/spy_send_core.h"
#include "codec.h"
namespace eu4_spy_send_host19 {
using Environment=eu4_spy_host18::Environment;
using Frame=eu4_spy_host18::Frame;
using PreflightProof=eu4_spy_host18::PreflightProof;
// Private synchronous durable sink. Claims are stage(1..4,0), then item(4,1..5).
struct Journal {
    void* user;
    bool (*append)(void*,const char*,std::size_t);
    bool (*claim)(void*,std::uint32_t sequence,std::uint32_t item,const char*,std::size_t);
};
enum class State:std::uint32_t { cold,preflight,batch_ready,awaiting_health,complete,frozen };
enum class Failure:std::uint32_t { none,reentry,already_started,bad_environment,wrong_thread,world,clock,
    order,packet,expired,claim,audit,core,write_contract,budget };
struct Status {
    State state;Failure failure;std::uint64_t owner_frames;
    std::uint32_t preflight_stages,authenticated_stages,claimed_sequence,completed_items;
    eu4_spy19::Result result;
    bool preflight_ready,batch_claimed,runtime_verified,production_ready,strict_sp_verified,epoch_verified,effect_verified;
};
class Controller {
public:
    Controller() noexcept;
    Controller(const Controller&)=delete;Controller& operator=(const Controller&)=delete;
    bool start(const Environment&,const Journal&);
    bool frame(const char* packet=nullptr,std::size_t size=0);
    Status status() const noexcept; // Owner-thread only; never a concurrent public read API.
private:
    volatile LONG started_,active_,frozen_,failure_;
    Environment env_;Journal journal_;eu4_spy_host18::Controller preflight_;eu4_spy19::Core core_;
    PreflightProof proof_;Status status_;BatchRequest batch_;char wire_[1025];std::size_t wire_size_;
    bool proof_valid_,audit_failed_,factory_verified_;std::uint64_t clock_,ordinal_,bytes_,stage3_health_;
    std::uint32_t lines_,read_calls_,write_index_,original_id_,current_item_,operation_;
    std::size_t read_bytes_;std::uintptr_t owned_base_;eu4_spy19::Step step_;
    bool fail(Failure);bool healthy() const;bool barrier(bool ttl);bool execute(const char*,std::size_t);
    bool append(const char*,std::size_t,bool diagnostic=false);
    bool record(const char*,const eu4_spy19::Event* event=nullptr,const eu4_spy19::Result* result=nullptr);
    bool send_log(const eu4_spy19::Event*);bool send_claim(std::uint32_t,std::uint32_t,const eu4_spy19::Identity*,const eu4_spy19::Stamp*);
    bool owned_write(std::uintptr_t,const void*,std::size_t);bool call(eu4_spy19::Operation);
    static bool read_cb(void*,std::uintptr_t,void*,std::size_t);static bool write_cb(void*,std::uintptr_t,const void*,std::size_t);
    static std::uintptr_t resolve_cb(void*,std::uintptr_t);static std::uint64_t clock_cb(void*);
    static bool sample_cb(void*,Frame*);static std::uint32_t thread_cb(void*);static bool begin_frame_cb(void*);
    static bool preflight_append_cb(void*,const char*,std::size_t);static bool preflight_claim_cb(void*,std::uint32_t,const char*,std::size_t);
    static bool guard_cb(void*,eu4_spy19::Point,eu4_spy19::Step,const eu4_spy19::Identity*,const eu4_spy19::Stamp*);
    static bool log_cb(void*,const eu4_spy19::Event*);
    static bool claim_cb(void*,std::uint32_t,std::uint32_t,const eu4_spy19::Identity*,const eu4_spy19::Stamp*);
};
} // namespace
