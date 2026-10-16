#include "native_env.h"
#include "../v19-spy-restricted-host-r2-1375/core/v18-preimage/pins.h"
#include <bcrypt.h>
#include <cwchar>
#include <cstring>
#include <initializer_list>
namespace eu4_spy_host18 {
namespace {
volatile LONG native_attempted=0; // Process singleton, never reset after any failure.
bool pointer(std::uintptr_t p) { return p>=0x10000 && p<0x800000000000ULL && p%8==0; }
bool transfer(std::uintptr_t p,void* buffer,std::size_t size,bool write) {
    if(!p||!buffer||!size||size>64||p>0x800000000000ULL-size)return false;
    MEMORY_BASIC_INFORMATION info{};if(!VirtualQuery(reinterpret_cast<void*>(p),&info,sizeof(info))||info.State!=MEM_COMMIT
        ||(info.Protect&(PAGE_GUARD|PAGE_NOACCESS))||p<reinterpret_cast<std::uintptr_t>(info.BaseAddress)
        ||p-reinterpret_cast<std::uintptr_t>(info.BaseAddress)>info.RegionSize
        ||size>info.RegionSize-(p-reinterpret_cast<std::uintptr_t>(info.BaseAddress)))return false;
    const DWORD protection=info.Protect&0xff;
    const bool readable=protection==PAGE_READONLY||protection==PAGE_READWRITE||protection==PAGE_WRITECOPY
        ||protection==PAGE_EXECUTE_READ||protection==PAGE_EXECUTE_READWRITE||protection==PAGE_EXECUTE_WRITECOPY;
    if(!readable || (write && (info.Type!=MEM_PRIVATE || protection!=PAGE_READWRITE)))return false;
    __try { if(write)std::memcpy(reinterpret_cast<void*>(p),buffer,size);else std::memcpy(buffer,reinterpret_cast<const void*>(p),size);return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool hash_file(const wchar_t* path,const char* expected,HANDLE& held,std::uint64_t maximum) {
    held=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_FLAG_SEQUENTIAL_SCAN|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
    if(held==INVALID_HANDLE_VALUE)return false;
    BY_HANDLE_FILE_INFORMATION info{};LARGE_INTEGER size{};
    if(!GetFileInformationByHandle(held,&info)||(info.dwFileAttributes&(FILE_ATTRIBUTE_REPARSE_POINT|FILE_ATTRIBUTE_DIRECTORY))
        ||!GetFileSizeEx(held,&size)||size.QuadPart<=0||static_cast<std::uint64_t>(size.QuadPart)>maximum)return false;
    BCRYPT_ALG_HANDLE algorithm=nullptr;BCRYPT_HASH_HANDLE hash=nullptr;
    bool ok=BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0;
    if(ok)ok=BCryptCreateHash(algorithm,&hash,nullptr,0,nullptr,0,0)>=0;
    unsigned char buffer[65536]{};std::uint64_t total=0;
    while(ok) { DWORD count=0;if(!ReadFile(held,buffer,sizeof(buffer),&count,nullptr)) { ok=false;break; }
        if(!count)break;total+=count;if(total>maximum||BCryptHashData(hash,buffer,count,0)<0)ok=false;
    }
    unsigned char digest[32]{};if(ok)ok=total==static_cast<std::uint64_t>(size.QuadPart)&&BCryptFinishHash(hash,digest,sizeof(digest),0)>=0;
    if(hash && BCryptDestroyHash(hash)<0)ok=false;if(algorithm && BCryptCloseAlgorithmProvider(algorithm,0)<0)ok=false;
    constexpr char hex[]="0123456789abcdef";char actual[65]{};
    for(unsigned i=0;i<32;++i) { actual[2*i]=hex[digest[i]>>4];actual[2*i+1]=hex[digest[i]&15]; }
    return ok && !std::strcmp(actual,expected); // Held handle denies write/delete until destruction.
}
struct Window { DWORD pid,thread;bool ambiguous; };
BOOL CALLBACK window(HWND h,LPARAM data) {
    auto& w=*reinterpret_cast<Window*>(data);DWORD pid=0;const DWORD thread=GetWindowThreadProcessId(h,&pid);
    if(pid==w.pid && IsWindowVisible(h)&&!GetWindow(h,GW_OWNER)) {
        if(w.thread && w.thread!=thread)w.ambiguous=true;w.thread=thread;
    }return TRUE;
}
}
NativeEnvironment::NativeEnvironment() noexcept:files_{INVALID_HANDLE_VALUE,INVALID_HANDLE_VALUE,INVALID_HANDLE_VALUE},base_(0),owner_(0),calls_(0),bytes_(0),attempted_(false),ready_(false),failed_(false) {}
NativeEnvironment::~NativeEnvironment() { for(auto h:files_)if(h!=INVALID_HANDLE_VALUE)CloseHandle(h); }
bool NativeEnvironment::initialize(const Bootstrap& config,Environment& output) {
    if(attempted_||InterlockedCompareExchange(&native_attempted,1,0))return false;attempted_=true;
    if(!config.disposable_test_authorized||!identity_valid(config.expected)||!config.manifest_path||config.expected.pid!=GetCurrentProcessId())return false;
    FILETIME created{},exited{},kernel{},user{};
    if(!GetProcessTimes(GetCurrentProcess(),&created,&exited,&kernel,&user)
        ||((static_cast<std::uint64_t>(created.dwHighDateTime)<<32)|created.dwLowDateTime)!=config.expected.creation)return false;
    wchar_t exe[1024]{},self[1024]{};HMODULE image=GetModuleHandleW(nullptr),module=nullptr;
    const DWORD n=GetModuleFileNameW(image,exe,1024);if(!n||n>=1024)return false;
    const wchar_t* name=wcsrchr(exe,L'\\');if(!name||_wcsicmp(name+1,L"eu4.exe"))return false;
    if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCWSTR>(&NativeEnvironment::clock_cb),&module)||module==image)return false;
    const DWORD m=GetModuleFileNameW(module,self,1024);if(!m||m>=1024)return false;
    if(!hash_file(exe,kGameSha,files_[0],268435456)||!hash_file(self,config.expected.dll_sha256,files_[1],16777216)
        ||!hash_file(config.manifest_path,config.expected.manifest_sha256,files_[2],1048576))return false;
    Window w{GetCurrentProcessId(),0,false};if(!EnumWindows(window,reinterpret_cast<LPARAM>(&w))||!w.thread||w.ambiguous)return false;
    owner_=w.thread;base_=reinterpret_cast<std::uintptr_t>(image);if(!this->image())return false;ready_=true;
    output={this,config.expected,base_,owner_,false,true,read_cb,write_cb,resolve_cb,clock_cb,sample_cb,thread_cb,frame_cb};return true;
}
bool NativeEnvironment::read(std::uintptr_t p,void* out,std::size_t n) {
    if(failed_||!n||n>64||calls_>=262144||bytes_>16777216-n)return failed_=true,false;
    ++calls_;bytes_+=n;if(!transfer(p,out,n,false))return failed_=true,false;return true;
}
bool NativeEnvironment::write(std::uintptr_t p,const void* in,std::size_t n) {
    if(failed_||!ready_||GetCurrentThreadId()!=owner_||(n!=1&&n!=4&&n!=8))return failed_=true,false;
    // Only Controller's private exact ordered just-owned writer can reach this.
    if(!transfer(p,const_cast<void*>(in),n,true))return failed_=true,false;return true;
}
bool NativeEnvironment::image() {
    std::uint16_t mz=0,machine=0,magic=0;std::int32_t pe=0;std::uint32_t sig=0,time=0,size=0;
    if(!get(base_,mz)||mz!=0x5a4d||!get(base_+0x3c,pe)||pe<=0||pe>4096)return false;
    const auto nt=base_+static_cast<unsigned>(pe);
    if(!get(nt,sig)||sig!=0x4550||!get(nt+4,machine)||machine!=0x8664||!get(nt+8,time)||time!=0x66fe6ab9
        ||!get(nt+24,magic)||magic!=0x20b||!get(nt+0x50,size)||size!=0x25e0000)return false;
    for(const auto& pin:eu4_spy18::kCodePins)for(std::size_t i=0;pin.hex[i*2];++i) {
        auto digit=[](char c) { return static_cast<unsigned>(c<='9'?c-'0':c-'a'+10); };std::uint8_t byte=0;
        if(!get(base_+pin.rva+i,byte)||byte!=(digit(pin.hex[2*i])*16+digit(pin.hex[2*i+1])))return false;
    }
    for(const auto& pin:eu4_spy18::kSlotPins) { std::uintptr_t target=0;if(!get(base_+pin.rva,target)||target!=base_+pin.target)return false; }
    // Reviewed root getter vtable slots, not a claim of strict single-player.
    const std::uintptr_t slots[][2]={{0x1cb84e0,0x811aa0},{0x1cb8560,0x8024d0},{0x1cb8778,0x80ff80}};
    for(const auto& slot:slots) { std::uintptr_t p=0;if(!get(base_+slot[0],p)||p!=base_+slot[1])return false; }
    return true;
}
bool NativeEnvironment::multiplayer(std::uintptr_t game,std::uintptr_t server,bool& result) {
    std::uint8_t gate=0;if(!get(server+0x19f1,gate)||gate>1)return false;result=false;if(!gate)return true;
    std::uintptr_t holder=0,context=0;if(!get(server+0x330,holder)||!pointer(holder)||!get(holder+0x370,context)||!pointer(context))return false;
    std::uint8_t a=0,b=0;if(!get(context+0x54,a)||!get(context+0x55,b)||a>1||b>1)return false;
    if(!a&&!b) { result=true;return true; }
    std::uint32_t local=0;std::uintptr_t node=0,seen[256]{};if(!get(context+0x8c,local)||!get(game+0xa50,node))return false;
    for(unsigned n=0;node;++n) { if(n>=256||!pointer(node))return false;for(unsigned i=0;i<n;++i)if(seen[i]==node)return false;
        seen[n]=node;std::uint32_t id=0;if(!get(node+0x18,id))return false;if(id!=local)result=true;if(!get(node+0x60,node))return false; }
    return true;
}
bool NativeEnvironment::sample(Frame& out) {
    if(!ready_||failed_||GetCurrentThreadId()!=owner_)return false;Frame f{};auto& s=f.stamp;
    if(!get(base_+0x233fe78,s.game)||!pointer(s.game)||!get(base_+0x233d8d0,s.database)||!pointer(s.database)
        ||!get(s.database+0x118,s.countries)||!pointer(s.countries))return false;
    std::int32_t count=0;if(!get(s.database+0x124,count)||count<=0||count>4096)return false;f.countries_count=static_cast<std::uint32_t>(count);
    // Frame fields describe only the human player's unchanged context.
    // The requested actor/target are resolved independently by NativePairGuard.
    if(!get(s.game+0x1e60,s.player) || !(s.player>>56) || ((s.player>>48)&255)!=0)return false;
    const auto player_slot=(s.player>>32)&65535;
    if(player_slot>=f.countries_count || !get(s.countries+player_slot*8,s.actor_country) || !pointer(s.actor_country))return false;
    s.target_country=s.actor_country;
    // Prove both country headers before reading derived handles/overlords.
    for(const auto country:{s.actor_country,s.target_country}) {
        std::uintptr_t type=0;std::uint32_t marker=0;
        if(!get(country,type)||type!=base_+0x1c574a0||!get(country+8,marker)||marker!=0x165)return false;
    }
    if(!get(s.actor_country+0x20,s.actor)||s.actor!=s.player||!get(s.target_country+0x20,s.target)||s.target!=s.player
        ||!get(s.actor_country+0x18f0,f.actor_overlord)||!get(s.target_country+0x18f0,f.target_overlord)
        ||!get(s.game+0x1e60,s.player)||!get(s.game+0x1dd0,s.date)||!get(s.game+0x1e00,s.server)||!pointer(s.server))return false;
    std::uintptr_t vt=0,back=0,begin=0,end=0;
    if(!get(s.server,vt)||vt!=base_+0x1cb8460||!get(s.server+0x418,s.pause_manager)||!pointer(s.pause_manager)
        ||!get(s.pause_manager+0x50,back)||back!=s.server||!get(s.pause_manager+0x48,f.manual_pause)
        ||!get(s.pause_manager,begin)||!get(s.pause_manager+8,end)||(begin==0)!=(end==0)
        ||(begin&&(!pointer(begin)||!pointer(end)))||end<begin||(end-begin)%8||(end-begin)/8>256)return false;
    if(!get(s.game+0x7485,f.reset)||!get(s.game+0x74c8,f.load_source)||!get(s.game+0x24d0,f.ironman)
        ||!get(s.game+0x1e66,f.selector)||!get(s.game+0x1e6f,f.alternate_selector)||!get(s.game+0x1e08,f.native_speed_index)
        ||!multiplayer(s.game,s.server,f.multiplayer_classifier))return false;
    f.effective_player=s.player;if(f.selector==7 && f.alternate_selector && !get(s.game+0x1e68,f.effective_player))return false;
    f.thread=GetCurrentThreadId();out=f;return true;
}
bool NativeEnvironment::read_cb(void* p,std::uintptr_t a,void* b,std::size_t n) { return static_cast<NativeEnvironment*>(p)->read(a,b,n); }
bool NativeEnvironment::write_cb(void* p,std::uintptr_t a,const void* b,std::size_t n) { return static_cast<NativeEnvironment*>(p)->write(a,b,n); }
std::uintptr_t NativeEnvironment::resolve_cb(void* p,std::uintptr_t rva) { auto& self=*static_cast<NativeEnvironment*>(p);return self.ready_&&!self.failed_&&GetCurrentThreadId()==self.owner_?self.base_+rva:0; }
std::uint64_t NativeEnvironment::clock_cb(void*) { return GetTickCount64(); }
bool NativeEnvironment::sample_cb(void* p,Frame* out) { return out&&static_cast<NativeEnvironment*>(p)->sample(*out); }
std::uint32_t NativeEnvironment::thread_cb(void*) { return GetCurrentThreadId(); }
bool NativeEnvironment::frame_cb(void* p) { auto& self=*static_cast<NativeEnvironment*>(p);if(!self.ready_||self.failed_||GetCurrentThreadId()!=self.owner_)return false;
    self.calls_=0;self.bytes_=0;if(!self.image())return self.failed_=true,false;return true; }
}
