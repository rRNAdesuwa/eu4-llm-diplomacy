#include "journal.h"
#include <sddl.h>
#include <cwchar>
namespace eu4_spy_host18 {
namespace {
bool ordinary_directory(HANDLE h) {
    BY_HANDLE_FILE_INFORMATION info{};
    return h!=INVALID_HANDLE_VALUE && GetFileInformationByHandle(h,&info)
        && (info.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY) && !(info.dwFileAttributes&FILE_ATTRIBUTE_REPARSE_POINT);
}
bool durable(HANDLE h,const char* bytes,std::size_t size) {
    DWORD written=0;return WriteFile(h,bytes,static_cast<DWORD>(size),&written,nullptr)
        && written==size && FlushFileBuffers(h);
}
bool security(PSECURITY_DESCRIPTOR& descriptor) {
    HANDLE token=nullptr;if(!OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token))return false;
    alignas(TOKEN_USER) unsigned char buffer[4096]{};DWORD needed=0;
    const bool ok=GetTokenInformation(token,TokenUser,buffer,sizeof(buffer),&needed)!=0;
    const bool closed=CloseHandle(token)!=0;if(!ok||!closed)return false;
    LPWSTR sid=nullptr;if(!ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(buffer)->User.Sid,&sid))return false;
    wchar_t sddl[1024]{};const int n=swprintf_s(sddl,L"D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;%s)",sid);LocalFree(sid);
    return n>0 && ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl,SDDL_REVISION_1,&descriptor,nullptr);
}
}
FileJournal::FileJournal() noexcept:parent_(INVALID_HANDLE_VALUE),directory_(INVALID_HANDLE_VALUE),file_(INVALID_HANDLE_VALUE),identity_{},path_{},attempted_(false),failed_(false),lines_(0),claims_(0),bytes_(0) {}
FileJournal::~FileJournal() { close(); }
bool FileJournal::close() {
    bool ok=true;HANDLE* handles[]={&file_,&directory_,&parent_};for(HANDLE* h:handles)if(*h!=INVALID_HANDLE_VALUE) {
        const HANDLE value=*h;*h=INVALID_HANDLE_VALUE;if(!CloseHandle(value))ok=false;
    }if(!ok)failed_=true;return ok;
}
bool FileJournal::create(const wchar_t* parent,const Identity& identity) {
    if(attempted_) { failed_=true;return false; }attempted_=true;
    if(!parent||!identity_valid(identity)||wcsnlen_s(parent,900)>=900)return failed_=true,false;
    parent_=CreateFileW(parent,FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
    if(!ordinary_directory(parent_))return failed_=true,false;
    wchar_t resolved[1024]{};const DWORD n=GetFinalPathNameByHandleW(parent_,resolved,900,FILE_NAME_NORMALIZED);
    if(!n||n>=900)return failed_=true,false;
    wchar_t nonce[33]{};for(unsigned i=0;i<32;++i)nonce[i]=identity.session[i];
    if(swprintf_s(path_,L"%s\\spy18-%u-%016llx-%s",resolved,identity.pid,static_cast<unsigned long long>(identity.creation),nonce)<=0)return failed_=true,false;
    PSECURITY_DESCRIPTOR descriptor=nullptr;if(!security(descriptor))return failed_=true,false;
    SECURITY_ATTRIBUTES sa{sizeof(sa),descriptor,FALSE};const bool made=CreateDirectoryW(path_,&sa)!=0;LocalFree(descriptor);
    if(!made)return failed_=true,false; // Never reuse a pre-existing or partial session.
    directory_=CreateFileW(path_,FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
    if(!ordinary_directory(directory_))return failed_=true,false;
    wchar_t log[1100]{};if(swprintf_s(log,L"%s\\raw-events.jsonl",path_)<=0)return failed_=true,false;
    file_=CreateFileW(log,GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_WRITE_THROUGH,nullptr);
    if(file_==INVALID_HANDLE_VALUE)return failed_=true,false;identity_=identity;return true;
}
bool FileJournal::append(const char* bytes,std::size_t size) {
    if(failed_||file_==INVALID_HANDLE_VALUE||!bytes||!size||size>8192||lines_>=512||bytes_>1048576-size)
        return failed_=true,false;
    if(bytes[size-1]!='\n')return failed_=true,false;
    for(std::size_t i=0;i<size;++i)if((bytes[i]<32||bytes[i]>126) && !(i+1==size&&bytes[i]=='\n'))return failed_=true,false;
    if(!durable(file_,bytes,size))return failed_=true,false;++lines_;bytes_+=size;return true;
}
bool FileJournal::claim(std::uint32_t sequence,const char* wire,std::size_t size) {
    Request request{};
    if(failed_||file_==INVALID_HANDLE_VALUE||sequence!=claims_+1||!parse(wire,size,request)
        ||request.sequence!=sequence||!same_identity(request.identity,identity_))return failed_=true,false;
    wchar_t name[1100]{};if(swprintf_s(name,L"%s\\%u.claim",path_,sequence)<=0)return failed_=true,false;
    HANDLE h=CreateFileW(name,GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_WRITE_THROUGH,nullptr);
    if(h==INVALID_HANDLE_VALUE)return failed_=true,false;
    const bool wrote=durable(h,wire,size);const bool closed=CloseHandle(h)!=0;
    if(!wrote||!closed)return failed_=true,false;++claims_;return true; // Partial claims deliberately retained.
}
bool FileJournal::append_cb(void* p,const char* s,std::size_t n) { return static_cast<FileJournal*>(p)->append(s,n); }
bool FileJournal::claim_cb(void* p,std::uint32_t q,const char* s,std::size_t n) { return static_cast<FileJournal*>(p)->claim(q,s,n); }
Journal FileJournal::callbacks() noexcept { return {this,append_cb,claim_cb}; }
}
