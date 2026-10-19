#include "bootstrap_codec.h"
#include "scheduler.h"
#include "installer.h"
#include "../v18-spy-restricted-host-1375/native_env.h"
#include "../v18-spy-restricted-host-1375/journal.h"
#include <bcrypt.h>
#include <new>
#include <cwchar>
#include <cstdarg>

namespace {
namespace host=eu4_spy_host18;
namespace boot=eu4_spy_boot18;
HMODULE self_module=nullptr;
volatile LONG started=0,enabled=0,active=0,frozen=0;
host::Identity identity{};
host::Environment original{},guarded{};
host::Journal durable{};
alignas(host::Controller) unsigned char controller_storage[sizeof(host::Controller)];
alignas(host::NativeEnvironment) unsigned char environment_storage[sizeof(host::NativeEnvironment)];
alignas(host::FileJournal) unsigned char journal_storage[sizeof(host::FileJournal)];
host::Controller* controller=nullptr;
host::NativeEnvironment* environment=nullptr;
host::FileJournal* journal=nullptr;
boot::Scheduler scheduler{};
HANDLE bootstrap_file=INVALID_HANDLE_VALUE,outer_file=INVALID_HANDLE_VALUE,input_file=INVALID_HANDLE_VALUE;
BCRYPT_ALG_HANDLE algorithm=nullptr;
BCRYPT_HASH_HANDLE frame_hash=nullptr;
std::uint64_t raw_bytes=0,raw_lines=0,outer_bytes=0,outer_lines=0;
std::uint64_t sharing_since=0;
unsigned sharing_attempts=0;
bool in_controller=false,outer_failed=false;
char input_packet[1025]{};std::size_t input_length=0;

bool terminal() { InterlockedExchange(&frozen,1);return false; }
bool running() { return !InterlockedCompareExchange(&frozen,0,0); }
bool write_outer(const char* raw,std::size_t length) {
    if(outer_failed||outer_file==INVALID_HANDLE_VALUE||!raw||!length||length>8192||raw[length-1]!='\n'
        ||outer_lines>=1024||outer_bytes>2097152-length) { outer_failed=true;return terminal(); }
    DWORD wrote=0;
    if(!WriteFile(outer_file,raw,static_cast<DWORD>(length),&wrote,nullptr)||wrote!=length||!FlushFileBuffers(outer_file)) {
        outer_failed=true;return terminal();
    }
    ++outer_lines;outer_bytes+=length;return true;
}
bool record(const char* event,const char* fields,...) {
    char extra[4096]{},line[8192]{};va_list args;va_start(args,fields);
    const int m=vsnprintf(extra,sizeof(extra),fields,args);va_end(args);
    if(m<0||static_cast<std::size_t>(m)>=sizeof(extra))return terminal();
    const int n=std::snprintf(line,sizeof(line),
        "{\"schema\":\"EU4SPYBOOTSTRAP/1\",\"event\":\"%s\",\"pid\":%u,\"creation\":\"%016llx\",\"session\":\"%s\",\"game_sha256\":\"%s\",\"dll_sha256\":\"%s\",\"manifest_sha256\":\"%s\",\"image_base\":%llu,\"owner_thread\":%u,\"thread\":%lu,\"ordinal\":%llu,\"uptime_ms\":%llu,\"send_supported\":false,\"strict_sp_verified\":false,\"world_epoch_verified\":false,\"production_ready\":false%s}\n",
        event,identity.pid,static_cast<unsigned long long>(identity.creation),identity.session,host::kGameSha,identity.dll_sha256,identity.manifest_sha256,
        static_cast<unsigned long long>(original.image_base),original.owner_thread,GetCurrentThreadId(),static_cast<unsigned long long>(outer_lines+1),
        static_cast<unsigned long long>(GetTickCount64()),extra);
    return n>0&&static_cast<std::size_t>(n)<sizeof(line)?write_outer(line,static_cast<std::size_t>(n)):terminal();
}
bool install_log(void*,const char* line,std::size_t length) {
    if(length>2048||!length||line[length-1]!='\n')return terminal();
    char nested[2049]{};std::memcpy(nested,line,length-1);
    return record("install_attempt",",\"detail\":%s",nested);
}
bool safe_file(HANDLE h,std::uint64_t maximum,DWORD& size) {
    BY_HANDLE_FILE_INFORMATION info{};LARGE_INTEGER length{};
    if(h==INVALID_HANDLE_VALUE||!GetFileInformationByHandle(h,&info)||!GetFileSizeEx(h,&length)
        ||info.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT)||info.nNumberOfLinks!=1
        ||length.QuadPart<=0||static_cast<std::uint64_t>(length.QuadPart)>maximum)return false;
    size=static_cast<DWORD>(length.QuadPart);return true;
}
bool read_packet(HANDLE h,char* bytes,std::size_t& size) {
    DWORD expected=0,read=0;if(!safe_file(h,1024,expected))return false;
    if(!ReadFile(h,bytes,1025,&read,nullptr)||read!=expected)return false;
    bytes[read]=0;size=read;return true;
}
bool guarded_read(void*,std::uintptr_t address,void* out,std::size_t size) {
    return running()&&original.read(original.user,address,out,size)&&running();
}
bool guarded_write(void*,std::uintptr_t address,const void* value,std::size_t size) {
    return running()&&original.write(original.user,address,value,size)&&running();
}
std::uintptr_t guarded_resolve(void*,std::uintptr_t rva) {
    if(!running())return 0;const auto result=original.resolve(original.user,rva);return running()?result:0;
}
std::uint64_t guarded_clock(void*) { return original.clock(original.user); }
bool guarded_sample(void*,host::Frame* frame) { return running()&&original.sample(original.user,frame)&&running(); }
std::uint32_t guarded_thread(void*) { return GetCurrentThreadId(); }
bool guarded_begin(void*) { return running()&&original.begin_frame(original.user)&&running(); }
bool raw_append(void*,const char* bytes,std::size_t size) {
    if(!in_controller||!frame_hash||GetCurrentThreadId()!=original.owner_thread||!running())return terminal();
    if(!durable.append(durable.user,bytes,size))return terminal();
    if(BCryptHashData(frame_hash,reinterpret_cast<PUCHAR>(const_cast<char*>(bytes)),static_cast<ULONG>(size),0)<0)return terminal();
    raw_bytes+=size;++raw_lines;return running();
}
bool raw_claim(void*,std::uint32_t sequence,const char* wire,std::size_t size) {
    if(!in_controller||input_file==INVALID_HANDLE_VALUE||size!=input_length||std::memcmp(wire,input_packet,size)
        ||GetCurrentThreadId()!=original.owner_thread||!running())return terminal();
    return durable.claim(durable.user,sequence,wire,size)&&running();
}
bool request_path(std::uint32_t sequence,wchar_t* out,std::size_t capacity) {
    return swprintf_s(out,capacity,L"%s\\%u.request",journal->directory(),sequence)>0;
}
// Return 0 missing/transient-unopened; 1 held exact request; -1 terminal input.
int open_request(std::uint32_t sequence,std::uint64_t now) {
    wchar_t path[1100]{};if(!request_path(sequence,path,1100))return -1;
    input_file=CreateFileW(path,GENERIC_READ,0,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
    if(input_file==INVALID_HANDLE_VALUE) {
        const DWORD error=GetLastError();
        if(error==ERROR_FILE_NOT_FOUND) { sharing_since=0;sharing_attempts=0;return 0; }
        if(error==ERROR_SHARING_VIOLATION) {
            if(!sharing_attempts)sharing_since=now;
            if(now<sharing_since||++sharing_attempts>16||now-sharing_since>=250)return -1;
            return 0; // Never reread after a handle or claim has been acquired.
        }
        return -1;
    }
    sharing_since=0;sharing_attempts=0;input_length=0;
    if(!read_packet(input_file,input_packet,input_length))return -1;
    host::Request request{};
    if(!host::parse(input_packet,input_length,request)||!host::same_identity(request.identity,identity)||request.sequence!=sequence)return -1;
    return 1;
}
bool close_input() {
    if(input_file==INVALID_HANDLE_VALUE)return true;const HANDLE h=input_file;input_file=INVALID_HANDLE_VALUE;
    if(!CloseHandle(h))return terminal();return true;
}
bool controller_call(bool with_request) {
    const auto before=controller->status();const auto start_bytes=raw_bytes,start_lines=raw_lines;
    if(BCryptCreateHash(algorithm,&frame_hash,nullptr,0,nullptr,0,0)<0)return terminal();
    if(!record("owner_call_begin",",\"owner_entry\":%llu,\"controller_frame_before\":%llu,\"raw_start\":%llu,\"raw_first_ordinal\":%llu,\"request_sequence\":%u",
        static_cast<unsigned long long>(scheduler.owner_entries),static_cast<unsigned long long>(before.frames),
        static_cast<unsigned long long>(start_bytes),static_cast<unsigned long long>(start_lines+1),with_request?before.claimed+1:0))return false;
    in_controller=true;
    const bool returned=controller->frame(with_request?input_packet:nullptr,with_request?input_length:0);
    in_controller=false;
    unsigned char value[32]{};bool hashed=BCryptFinishHash(frame_hash,value,sizeof(value),0)>=0;
    if(BCryptDestroyHash(frame_hash)<0)hashed=false;frame_hash=nullptr;
    if(!hashed)return terminal();
    constexpr char hex[]="0123456789abcdef";char sha[65]{};
    for(unsigned i=0;i<32;++i) { sha[i*2]=hex[value[i]>>4];sha[i*2+1]=hex[value[i]&15]; }
    const auto after=controller->status();
    const bool closed=close_input();
    const bool success=returned&&closed&&running()&&after.state!=host::State::frozen;
    if(!record("owner_call_return",",\"owner_entry\":%llu,\"controller_frame_after\":%llu,\"raw_end\":%llu,\"raw_last_ordinal\":%llu,\"raw_segment_sha256\":\"%s\",\"controller_returned\":%s,\"input_closed\":%s,\"state\":%u,\"failure\":%u,\"claimed\":%u,\"completed\":%u,\"success\":%s",
        static_cast<unsigned long long>(scheduler.owner_entries),static_cast<unsigned long long>(after.frames),static_cast<unsigned long long>(raw_bytes),
        static_cast<unsigned long long>(raw_lines),sha,returned?"true":"false",closed?"true":"false",static_cast<unsigned>(after.state),
        static_cast<unsigned>(after.failure),after.claimed,after.completed,success?"true":"false"))return false;
    if(!success)return terminal();
    if(after.state==host::State::complete) {
        if(!record("completed_no_send",",\"owner_entry\":%llu,\"controller_frame\":%llu,\"stages\":3,\"owned_objects_remaining\":0,\"individual_effect_verified\":false",
            static_cast<unsigned long long>(scheduler.owner_entries),static_cast<unsigned long long>(after.frames)))return false;
        scheduler.finish();
    }
    return true;
}
void tick_body() {
    if(!scheduler.enter(GetCurrentThreadId(),GetTickCount64())) { terminal();return; }
    if(!scheduler.should_poll())return;
    const auto status=controller->status();
    if(status.state==host::State::frozen) { terminal();return; }
    int pending=0;
    if(status.state==host::State::ready&&status.claimed<3)pending=open_request(status.claimed+1,scheduler.last_clock);
    if(pending<0) { close_input();terminal();return; }
    const auto decision=scheduler.decide(pending==1);
    if(decision==boot::Decision::health||decision==boot::Decision::request) {
        if(!controller_call(decision==boot::Decision::request))terminal();
    }
}
DWORD start_impl() {
    wchar_t path[1024]{};const DWORD length=GetModuleFileNameW(self_module,path,1024);
    if(!length||length>=1024)return 11;wchar_t* slash=wcsrchr(path,L'\\');
    if(!slash||_wcsicmp(slash+1,boot::kDllName))return 12;*slash=0;
    FILETIME created{},exited{},kernel{},user{};
    if(!GetProcessTimes(GetCurrentProcess(),&created,&exited,&kernel,&user)||exited.dwHighDateTime||exited.dwLowDateTime)return 13;
    const auto creation=(static_cast<std::uint64_t>(created.dwHighDateTime)<<32)|created.dwLowDateTime;
    wchar_t packet_path[1100]{},manifest_path[1100]{};
    if(swprintf_s(packet_path,L"%s\\bootstrap-%u-%016llx.request",path,GetCurrentProcessId(),static_cast<unsigned long long>(creation))<=0
        ||swprintf_s(manifest_path,L"%s\\build.json",path)<=0)return 14;
    bootstrap_file=CreateFileW(packet_path,GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
    char packet[1025]{};std::size_t size=0;
    if(!read_packet(bootstrap_file,packet,size)||!boot::parse_boot(packet,size,identity)||identity.pid!=GetCurrentProcessId()||identity.creation!=creation)return 15;
    // Explicit construction, including static-storage state, before any hook.
    environment=new(environment_storage) host::NativeEnvironment();controller=new(controller_storage) host::Controller();journal=new(journal_storage) host::FileJournal();
    scheduler=boot::Scheduler{};
    host::Bootstrap config{identity,manifest_path,true};
    if(!environment->initialize(config,original))return 16;
    if(!journal->create(path,identity))return 17;
    wchar_t outer_path[1100]{};if(swprintf_s(outer_path,L"%s\\bootstrap-events.jsonl",journal->directory())<=0)return 18;
    outer_file=CreateFileW(outer_path,GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_WRITE_THROUGH,nullptr);
    if(outer_file==INVALID_HANDLE_VALUE)return 19;
    if(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)<0)return 20;
    durable=journal->callbacks();guarded=original;guarded.user=nullptr;guarded.read=guarded_read;guarded.write=guarded_write;
    guarded.resolve=guarded_resolve;guarded.clock=guarded_clock;guarded.sample=guarded_sample;guarded.current_thread=guarded_thread;guarded.begin_frame=guarded_begin;
    const host::Journal wrapped{nullptr,raw_append,raw_claim};
    if(!controller->start(guarded,wrapped)||!scheduler.start(original.owner_thread))return 21;
    if(!record("bootstrap_verified",",\"disposable_test_premise\":true,\"native_environment_initialized\":true,\"automatic_stage\":false,\"runtime_verified\":false"))return 22;
    if(!boot::install_owner_hook(original.image_base,install_log,nullptr))return 23;
    if(!record("hook_installed",",\"frame_rva\":17460928,\"prefix_bytes\":20,\"stage_limit\":3,\"health_interval_ms\":1000,\"poll_interval_ms\":100,\"hot_unload_supported\":false"))return 24;
    InterlockedExchange(&enabled,1);return 0;
}
}
extern "C" void research_frame_tick() {
    if(!InterlockedCompareExchange(&enabled,0,0)||!running())return;
    if(GetCurrentThreadId()!=original.owner_thread) { terminal();return; }
    if(InterlockedCompareExchange(&active,1,0)) { terminal();return; }
    __try { tick_body(); }
    __except(EXCEPTION_EXECUTE_HANDLER) { terminal(); }
    if(!running()) {
        scheduler.fail();
        if(input_file!=INVALID_HANDLE_VALUE)close_input();
        if(!outer_failed)record("terminal",",\"owner_entry\":%llu,\"unknown_no_retry\":true",static_cast<unsigned long long>(scheduler.owner_entries));
    }
    InterlockedExchange(&active,0);
}
extern "C" __declspec(dllexport) DWORD WINAPI BridgeStart(void*) {
    if(InterlockedCompareExchange(&started,1,0))return 10;
    DWORD result=0;
    __try { result=start_impl(); }
    __except(EXCEPTION_EXECUTE_HANDLER) { result=30; }
    if(result)terminal();return result;
}
BOOL WINAPI DllMain(HINSTANCE module,DWORD reason,LPVOID) {
    if(reason==DLL_PROCESS_ATTACH) { self_module=module;DisableThreadLibraryCalls(module); }
    return TRUE; // Installed hook and held provenance objects live until process exit.
}
