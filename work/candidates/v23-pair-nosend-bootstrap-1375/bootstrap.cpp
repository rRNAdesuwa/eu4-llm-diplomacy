#include "codec.h"
#include "installer.h"
#include "../v21-native-pair-guard-r3-1375/native_guard.h"
#include <new>
#include <cwchar>
#include <cstdarg>
namespace {
HMODULE self=nullptr;volatile LONG started=0,enabled=0,active=0,frozen=0;
pair23::Identity id{};eu4_spy_host18::NativeEnvironment* native=nullptr;eu4_spy_host18::Environment env{};
HANDLE bootstrap_file=INVALID_HANDLE_VALUE,log_file=INVALID_HANDLE_VALUE;
wchar_t directory[1100]{};std::uint64_t ordinal=0,log_bytes=0,last_poll=0,last_clock=0;
std::uint32_t next_sequence=1,current_sequence=0;bool log_failed=false;
bool terminal(){InterlockedExchange(&frozen,1);return false;}
bool running(){return !InterlockedCompareExchange(&frozen,0,0);}
bool append(const char* bytes,std::size_t n) {
 if(log_failed||log_file==INVALID_HANDLE_VALUE||!n||n>8192||bytes[n-1]!='\n'||ordinal>=4096||log_bytes>2097152-n){log_failed=true;return terminal();}
 DWORD wrote=0;if(!WriteFile(log_file,bytes,static_cast<DWORD>(n),&wrote,nullptr)||wrote!=n||!FlushFileBuffers(log_file)){log_failed=true;return terminal();}
 ++ordinal;log_bytes+=n;return true;
}
bool record(const char* event,const char* format,...) {
 char extra[4096]{},line[8192]{};va_list args;va_start(args,format);const int m=vsnprintf(extra,sizeof(extra),format,args);va_end(args);
 if(m<0||static_cast<std::size_t>(m)>=sizeof(extra))return terminal();
 const int n=std::snprintf(line,sizeof(line),"{\"schema\":\"EU4PAIRNOSEND/1\",\"event\":\"%s\",\"pid\":%u,\"creation\":\"%016llx\",\"session\":\"%s\",\"dll_sha256\":\"%s\",\"manifest_sha256\":\"%s\",\"owner_thread\":%u,\"thread\":%lu,\"ordinal\":%llu,\"uptime_ms\":%llu,\"sequence\":%u,\"no_send\":true,\"production_ready\":false%s}\n",
 event,id.pid,static_cast<unsigned long long>(id.creation),id.session,id.dll_sha256,id.manifest_sha256,env.owner_thread,GetCurrentThreadId(),
 static_cast<unsigned long long>(ordinal+1),static_cast<unsigned long long>(GetTickCount64()),current_sequence,extra);
 return n>0&&static_cast<std::size_t>(n)<sizeof(line)?append(line,static_cast<std::size_t>(n)):terminal();
}
bool safe_file(HANDLE h,DWORD& length) {
 BY_HANDLE_FILE_INFORMATION info{};LARGE_INTEGER size{};
 if(h==INVALID_HANDLE_VALUE||!GetFileInformationByHandle(h,&info)||!GetFileSizeEx(h,&size)||size.QuadPart<1||size.QuadPart>1024
  ||info.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT)||info.nNumberOfLinks!=1)return false;
 length=static_cast<DWORD>(size.QuadPart);return true;
}
bool read_packet(HANDLE h,char* out,std::size_t& length) {
 DWORD expected=0,got=0;if(!safe_file(h,expected)||!ReadFile(h,out,1025,&got,nullptr)||got!=expected)return false;
 out[got]=0;length=got;return true;
}
bool claim(const char* bytes,std::size_t n) {
 wchar_t path[1200]{};if(swprintf_s(path,L"%s\\%u.claim",directory,next_sequence)<=0)return terminal();
 const HANDLE file=CreateFileW(path,GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_WRITE_THROUGH,nullptr);
 if(file==INVALID_HANDLE_VALUE)return terminal();DWORD wrote=0;
 const bool saved=WriteFile(file,bytes,static_cast<DWORD>(n),&wrote,nullptr)&&wrote==n&&FlushFileBuffers(file);
 const bool closed=CloseHandle(file)!=FALSE;return saved&&closed?true:terminal();
}
struct AuditedPlatform final:v21port::Platform {
 v21port::CompiledWin32Platform platform;
 AuditedPlatform(std::uint64_t base,std::uint32_t owner,v21port::Authority authority):platform(base,owner,authority){}
 v21port::Address module()const noexcept override{return platform.module();}
 bool ready()override{return running()&&platform.ready()&&running();}
 bool region(v21port::Address p,v21port::Region& out)override{return running()&&platform.region(p,out);}
 bool read(v21port::Address p,void* out,std::size_t n)override{return running()&&platform.read(p,out,n)&&running();}
 bool write(v21port::Address p,const void* in,std::size_t n)override{return running()&&platform.write(p,in,n)&&running();}
 v21port::Return invoke(v21port::Call kind,const v21pair::Profile& profile,v21port::Address object,bool mode)override {
  if(!running()||!record("native_call_begin",",\"call\":%u,\"family\":%u",static_cast<unsigned>(kind),static_cast<unsigned>(profile.family)))return {};
  const auto r=platform.invoke(kind,profile,object,mode);
  if(!record("native_call_return",",\"call\":%u,\"normal\":%s,\"boolean\":%s,\"returned_same_slot\":%s,\"exception\":%u",static_cast<unsigned>(kind),r.normal?"true":"false",r.boolean?"true":"false",r.returned_same_slot?"true":"false",r.exception))return {};
  return r;
 }
};
struct Job {
 v21guard::NativePairGuardDraft guard;AuditedPlatform platform;v21port::NativePairEngineDraft engine;
 explicit Job():guard(env),platform(env.image_base,env.owner_thread,guard.authority()),engine(platform){}
};
// Retained until process exit, including every quarantined native allocation.
Job* jobs[64]{};
void tick_body() {
 const auto now=GetTickCount64();if(now<last_clock){terminal();return;}last_clock=now;
 if(now-last_poll<100)return;last_poll=now;if(next_sequence>64)return;
 wchar_t path[1200]{};if(swprintf_s(path,L"%s\\%u.request",directory,next_sequence)<=0){terminal();return;}
 const HANDLE request_file=CreateFileW(path,GENERIC_READ,0,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
 if(request_file==INVALID_HANDLE_VALUE){if(GetLastError()!=ERROR_FILE_NOT_FOUND)terminal();return;}
 char bytes[1025]{};std::size_t length=0;pair23::Packet packet{};
 const bool valid=read_packet(request_file,bytes,length)&&pair23::parse(bytes,length,packet)&&eu4_spy_host18::same_identity(packet.identity,id)
  &&packet.sequence==next_sequence;
 if(!valid){CloseHandle(request_file);terminal();return;}
 current_sequence=next_sequence;
 if(!claim(bytes,length)){CloseHandle(request_file);return;}
 if(!CloseHandle(request_file)){terminal();return;}
 if(!record("request_claimed",",\"action\":\"%s\",\"actor\":\"%.3s\",\"target\":\"%.3s\",\"expires\":%llu",
   pair23::Names[static_cast<unsigned>(packet.request.action)],packet.request.actor.bytes.data(),packet.request.target.bytes.data(),static_cast<unsigned long long>(packet.expires)))return;
 auto* job=new(std::nothrow) Job();if(!job){terminal();return;}jobs[next_sequence-1]=job;
 if(!job->guard.begin_frame()||!job->guard.lease(packet.request,packet.expires)){record("lease_rejected",",\"native_call_attempts\":0,\"unknown_no_retry\":true");terminal();return;}
 const auto result=v21pair::preflight_no_send(packet.request,job->guard,job->engine,packet.expires,&job->guard,env.image_base);
 const auto d=job->engine.diagnostics();
 const bool success=result.status!=v21pair::Status::Frozen&&!job->guard.frozen()&&!d.frozen&&d.live==0;
 if(!record("request_result",",\"status\":%u,\"reason\":\"%s\",\"adapter_call_attempts\":%u,\"owned_issued\":%u,\"owned_live\":%u,\"quarantined\":%u,\"adapter_fault\":%u,\"known_cleanup_complete\":%s,\"submitted\":false",
   static_cast<unsigned>(result.status),result.reason,d.calls,d.issued,d.live,d.quarantined,static_cast<unsigned>(d.fault),success?"true":"false"))return;
 if(!success){terminal();return;}
 // A later owner entry may consume the next distinct permanent request.
 ++next_sequence;current_sequence=0;
}
bool install_log(void*,const char* bytes,std::size_t n) {
 if(!n||n>2048||bytes[n-1]!='\n')return terminal();char nested[2049]{};std::memcpy(nested,bytes,n-1);
 return record("hook_attempt",",\"detail\":%s",nested);
}
DWORD start_impl() {
 wchar_t path[1024]{};const DWORD n=GetModuleFileNameW(self,path,1024);if(!n||n>=1024)return 11;
 auto* slash=wcsrchr(path,L'\\');if(!slash||_wcsicmp(slash+1,pair23::DllName))return 12;*slash=0;
 FILETIME c{},e{},k{},u{};if(!GetProcessTimes(GetCurrentProcess(),&c,&e,&k,&u)||e.dwHighDateTime||e.dwLowDateTime)return 13;
 const auto creation=(static_cast<std::uint64_t>(c.dwHighDateTime)<<32)|c.dwLowDateTime;
 wchar_t boot_path[1100]{},manifest[1100]{};
 if(swprintf_s(boot_path,L"%s\\bootstrap-%u-%016llx.request",path,GetCurrentProcessId(),static_cast<unsigned long long>(creation))<=0||swprintf_s(manifest,L"%s\\build.json",path)<=0)return 14;
 bootstrap_file=CreateFileW(boot_path,GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
 char packet[1025]{};std::size_t length=0;
 if(!read_packet(bootstrap_file,packet,length)||!pair23::parse_boot(packet,length,id)||id.pid!=GetCurrentProcessId()||id.creation!=creation)return 15;
 native=new(std::nothrow) eu4_spy_host18::NativeEnvironment();if(!native)return 16;
 if(!native->initialize({id,manifest,true},env))return 17;
 if(swprintf_s(directory,L"%s\\pair23-%u-%016llx-%S",path,id.pid,static_cast<unsigned long long>(id.creation),id.session)<=0||!CreateDirectoryW(directory,nullptr))return 18;
 wchar_t log_path[1200]{};if(swprintf_s(log_path,L"%s\\events.jsonl",directory)<=0)return 19;
 log_file=CreateFileW(log_path,GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_WRITE_THROUGH,nullptr);
 if(log_file==INVALID_HANDLE_VALUE)return 20;
 if(!record("bootstrap_verified",",\"native_environment_initialized\":true,\"game_sha256\":\"%s\",\"strict_SP_verified\":false,\"world_epoch_verified\":false",eu4_spy_host18::kGameSha))return 21;
 if(!eu4_spy_boot19::install_owner_hook(env.image_base,install_log,nullptr))return 22;
 if(!record("hook_installed",",\"request_limit\":64,\"automatic_action\":false,\"hot_unload_supported\":false"))return 23;
 InterlockedExchange(&enabled,1);return 0;
}
}
extern "C" void research_frame_tick() {
 if(!InterlockedCompareExchange(&enabled,0,0)||!running())return;
 if(GetCurrentThreadId()!=env.owner_thread){terminal();return;}
 if(InterlockedCompareExchange(&active,1,0)){terminal();return;}
 __try {tick_body();}__except(EXCEPTION_EXECUTE_HANDLER){terminal();}
 if(!running()&&!log_failed)record("terminal",",\"unknown_no_retry\":true");
 InterlockedExchange(&active,0);
}
extern "C" __declspec(dllexport) DWORD WINAPI BridgeStart(void*) {
 if(InterlockedCompareExchange(&started,1,0))return 10;DWORD result=0;
 __try {result=start_impl();}__except(EXCEPTION_EXECUTE_HANDLER){result=30;}
 if(result)terminal();return result;
}
BOOL WINAPI DllMain(HINSTANCE module,DWORD reason,LPVOID) {
 if(reason==DLL_PROCESS_ATTACH){self=module;DisableThreadLibraryCalls(module);}return TRUE;
}
