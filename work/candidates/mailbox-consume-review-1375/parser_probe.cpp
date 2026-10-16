// Disk-only regression for the preserved speed request. No game or process APIs.
#include "../../native/v10/lab-request-1375.h"
#include <cstdio>
#include <cstring>

// Pair parsing is outside this speed-only probe and must never be reached.
static bool unexpected_pair_parse = false;
namespace eu4_pair_1375 {
bool parse_action_id(const char*, std::size_t, ActionId*) {
    unexpected_pair_parse = true;
    return false;
}
}

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    FILE* input = nullptr;
    if (fopen_s(&input, argv[1], "rb") || input == nullptr) return 3;
    char raw[eu4_lab_1375::kMaxRequestBytes + 1]{};
    const std::size_t length = std::fread(raw, 1, sizeof(raw), input);
    const bool read_okay = !std::ferror(input) && std::feof(input);
    const bool closed = std::fclose(input) == 0;
    eu4_lab_1375::MailboxRequest request{};
    const bool parsed = read_okay && closed && eu4_lab_1375::parse_request(raw, length, request);
    const bool identity = parsed && request.pid == 46408 && request.creation == 0x01dd568ed7034bcbULL
        && request.sequence == 13 && request.expires == 396305218 && request.speed == 5
        && !std::strcmp(request.operation, "speed") && !unexpected_pair_parse;
    std::printf("{\"native_parser_accepted\":%s,\"exact_identity\":%s,\"request_bytes\":%zu,"
                "\"pair_parser_called\":%s,\"game_process_access\":false}\n",
                parsed ? "true" : "false", identity ? "true" : "false", length,
                unexpected_pair_parse ? "true" : "false");
    return identity ? 0 : 4;
}
