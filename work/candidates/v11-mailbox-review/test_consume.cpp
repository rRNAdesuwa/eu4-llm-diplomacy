// Real Win32 filesystem fixture, synthetic files only. No game/process access.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include "../../native/v11/lab-request-1375.h"

namespace eu4_pair_1375 {
bool parse_action_id(const char*, std::size_t, ActionId*) { return false; }
}
static uint64_t process_created = 0x1234, last_sequence = 0;
static ULONGLONG fake_tick = 100000;
static std::vector<std::string> records;
static bool fail_audit = false, fail_end_audit = false, fail_claim_flush = false;
static ULONGLONG fixture_tick() { return fake_tick; }
static bool durable_log(const char* row) {
    if (fail_audit || (fail_end_audit && std::strstr(row, "\"wait_state\":\"end\""))) return false;
    records.emplace_back(row);
    return true;
}
static BOOL fixture_flush(HANDLE file) {
    if (fail_claim_flush) { SetLastError(ERROR_WRITE_FAULT); return FALSE; }
    return FlushFileBuffers(file);
}
#define GetTickCount64 fixture_tick
#define FlushFileBuffers fixture_flush
#include "consume-input.inc"
#undef FlushFileBuffers
#undef GetTickCount64

static unsigned checks = 0, failed = 0;
static void expect(bool yes, const char* name) {
    ++checks;
    if (!yes) { ++failed; std::printf("FAIL %s\n", name); }
}
static bool exists(const wchar_t* path) { return GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES; }
static bool write_file(const wchar_t* path, const std::string& raw) {
    FILE* file = nullptr;
    if (_wfopen_s(&file, path, L"wb") || file == nullptr) return false;
    const bool good = std::fwrite(raw.data(), 1, raw.size(), file) == raw.size();
    return std::fclose(file) == 0 && good;
}
static std::string read_file(const wchar_t* path) {
    FILE* file = nullptr;
    if (_wfopen_s(&file, path, L"rb") || file == nullptr) return {};
    char data[2048]{};
    const auto length = std::fread(data, 1, sizeof(data), file);
    std::fclose(file);
    return std::string(data, length);
}
static bool has(const char* fragment) {
    for (const auto& row : records) if (row.find(fragment) != std::string::npos) return true;
    return false;
}
static std::string speed_wire(ULONGLONG expires) {
    eu4_lab_1375::MailboxRequest r{};
    r.pid = GetCurrentProcessId(); r.creation = process_created; r.sequence = 1; r.expires = expires;
    strcpy_s(r.operation, "speed"); strcpy_s(r.mode, "submit"); strcpy_s(r.action, "none");
    strcpy_s(r.actor, "FRA"); strcpy_s(r.target, "FRA"); r.speed = 5;
    char text[1025]{};
    const int size = eu4_lab_1375::render_request(r, text, sizeof(text));
    return size > 0 ? std::string(text, static_cast<size_t>(size)) : std::string();
}
int main() {
    (void)input_waits;
    wchar_t folder[MAX_PATH]{}, request[MAX_PATH]{}, claim[MAX_PATH]{}, alias[MAX_PATH]{};
    swprintf_s(folder, L"synthetic-consume-%lu", GetCurrentProcessId());
    if (!CreateDirectoryW(folder, nullptr)) return 2;
    swprintf_s(request, L"%s\\input.txt", folder); swprintf_s(claim, L"%s\\claim.txt", folder);
    swprintf_s(alias, L"%s\\alias.txt", folder);
    auto clear = [&]() {
        DeleteFileW(alias); DeleteFileW(request); DeleteFileW(claim);
        records.clear(); fake_tick = 100000; fail_audit = fail_end_audit = fail_claim_flush = false;
    };
    auto consume = [&](InputWait& wait, bool phase = true) {
        char raw[eu4_lab_1375::kMaxRequestBytes + 1]{}; DWORD length = 0;
        return consume_input(request, claim, phase ? "TOKEN\n" : nullptr, phase ? 6 : 0, raw, length,
                             wait, phase ? "lifecycle" : "request", phase ? 0 : 1);
    };
    auto lock = [&]() {
        return CreateFileW(request, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                           nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    };
    {
        InputWait wait{};
        expect(consume(wait) == InputState::absent, "missing input absent");
        expect(records.empty() && !exists(claim), "absence has no log/claim");
    }
    clear();
    {
        expect(write_file(request, "TOKEN\n"), "write valid marker"); InputWait wait{};
        HANDLE held = lock(); expect(held != INVALID_HANDLE_VALUE, "existing all-sharing reader opened");
        expect(consume(wait) == InputState::deferred && wait.active && wait.attempts == 1, "share32 defers before claim");
        expect(!exists(claim) && records.size() == 1 && has("sharing_violation"), "first wait only once");
        expect(consume(wait) == InputState::deferred && records.size() == 1, "second wait no log flood");
        CloseHandle(held); fake_tick += 1;
        expect(consume(wait) == InputState::consumed, "same marker consumes after unlock");
        expect(!wait.active && !exists(request) && read_file(claim) == "TOKEN\n", "one durable claim exact bytes and deletion");
        expect(records.size() == 2 && has("\"outcome\":\"opened\""), "wait one begin one end");
        expect(consume(wait) == InputState::absent && records.size() == 2, "consumed marker is never reinvoked");
    }
    clear();
    {
        write_file(request, "TOKEN\n"); InputWait wait{}; HANDLE held = lock();
        for (unsigned i = 1; i < 16; ++i) expect(consume(wait) == InputState::deferred, "bounded locked attempts before16");
        expect(consume(wait) == InputState::failed && wait.attempts == 16, "16th sharing failure ends wait");
        expect(!wait.active && records.size() == 3 && has("open_wait_budget"), "attempt budget logs once end plus failure");
        expect(!exists(claim) && exists(request), "budget no claim/delete"); CloseHandle(held);
    }
    clear();
    {
        write_file(request, "TOKEN\n"); InputWait wait{}; HANDLE held = lock(); consume(wait);
        CloseHandle(held); fake_tick += 250;
        expect(consume(wait) == InputState::failed && !exists(claim), "250ms elapsed forbids late successful open");
        expect(wait.attempts == 1 && records.size() == 3, "elapsed budget stops before another open");
    }
    clear();
    {
        write_file(request, "TOKEN\n"); InputWait wait{}; HANDLE held = lock(); consume(wait);
        CloseHandle(held); DeleteFileW(request);
        expect(consume(wait) == InputState::failed && has("disappeared"), "disappearance after sharing wait freezes");
        expect(!exists(claim), "disappeared input no claim");
    }
    clear();
    {
        write_file(request, "WRONG\n"); InputWait wait{};
        expect(consume(wait) == InputState::failed && has("marker_token"), "invalid marker not deferred");
        expect(!exists(claim) && exists(request), "bad marker retained with no claim");
    }
    clear();
    {
        write_file(request, speed_wire(fake_tick + 100)); InputWait wait{}; HANDLE held = lock();
        expect(consume(wait, false) == InputState::deferred, "request shares bounded wait policy");
        CloseHandle(held); fake_tick += 150;
        expect(consume(wait, false) == InputState::failed && has("ttl_expired"), "original TTL continues during wait");
        expect(!exists(claim) && exists(request), "expired input never claimed");
    }
    clear();
    {
        write_file(request, speed_wire(fake_tick + 60001)); InputWait wait{};
        expect(consume(wait, false) == InputState::failed && has("ttl_range"), "overlong TTL rejected");
    }
    clear();
    {
        write_file(request, "TOKEN\n"); write_file(claim, "PERMANENT\n"); InputWait wait{};
        expect(consume(wait) == InputState::failed && has("claim_open"), "existing claim rejected not deferred");
        expect(read_file(claim) == "PERMANENT\n" && exists(request), "claim never overwritten");
    }
    clear();
    {
        write_file(request, "TOKEN\n"); InputWait wait{}; fail_claim_flush = true;
        expect(consume(wait) == InputState::failed && has("claim_flush"), "claim flush failure freezes");
        expect(exists(claim) && exists(request) && has("\"claim_created\":true"), "partial claim retained");
        fail_claim_flush = false;
        expect(consume(wait) == InputState::failed && has("claim_open"), "retry cannot claim existing partial file");
    }
    clear();
    {
        write_file(request, "TOKEN\n"); expect(CreateHardLinkW(alias, request, nullptr) != FALSE, "create isolated hardlink");
        InputWait wait{};
        expect(consume(wait) == InputState::failed && has("file_links") && !exists(claim), "hardlinks still rejected");
    }
    clear();
    {
        InputWait wait{}; wchar_t nonexistent_parent[MAX_PATH]{};
        swprintf_s(nonexistent_parent, L"%s\\no-parent\\input.txt", folder);
        char raw[1025]{}; DWORD length = 0;
        expect(consume_input(nonexistent_parent, claim, "TOKEN\n", 6, raw, length, wait, "lifecycle", 0) == InputState::failed,
               "path-not-found is not sharing wait or absent");
        expect(has("\"stage\":\"open\"") && records.size() == 1, "other open error precise log");
    }
    clear();
    {
        write_file(request, "TOKEN\n"); InputWait wait{}; HANDLE held = lock(); fail_audit = true;
        expect(consume(wait) == InputState::failed && !wait.active && !exists(claim), "failed wait-begin audit cannot progress");
        CloseHandle(held);
    }
    clear();
    {
        write_file(request, "TOKEN\n"); InputWait wait{}; HANDLE held = lock(); consume(wait); CloseHandle(held); fail_end_audit = true;
        expect(consume(wait) == InputState::failed && !exists(claim), "failed wait-end audit cannot claim");
        expect(has("wait_end_audit") && exists(request), "audit failure diagnosed before mutation");
    }
    clear();
    {
        write_file(request, speed_wire(fake_tick + 5000)); InputWait wait{};
        expect(consume(wait, false) == InputState::consumed && read_file(claim) == speed_wire(fake_tick + 5000), "valid speed claimed once");
    }
    clear();
    expect(RemoveDirectoryW(folder) != FALSE, "fixture cleanup own directory");
    std::printf("{\"checks\":%u,\"failures\":%u,\"real_file_locks\":true,\"game_access\":false,\"native_operation_invoked\":false}\n", checks, failed);
    return failed ? 1 : 0;
}
