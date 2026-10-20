#pragma once
#include "host.h"
namespace eu4_spy_host18 {
class FileJournal {
public:
    FileJournal() noexcept;
    ~FileJournal();
    FileJournal(const FileJournal&)=delete;FileJournal& operator=(const FileJournal&)=delete;
    // Private bootstrap path, never a request field. Existing session is refused.
    bool create(const wchar_t* existing_parent,const Identity&);
    Journal callbacks() noexcept;
    bool close();
    const wchar_t* directory() const noexcept { return path_; }
private:
    HANDLE parent_,directory_,file_;Identity identity_;wchar_t path_[1024];
    bool attempted_,failed_;std::uint32_t lines_,claims_;std::uint64_t bytes_;
    bool append(const char*,std::size_t);bool claim(std::uint32_t,const char*,std::size_t);
    static bool append_cb(void*,const char*,std::size_t);
    static bool claim_cb(void*,std::uint32_t,const char*,std::size_t);
};
}
