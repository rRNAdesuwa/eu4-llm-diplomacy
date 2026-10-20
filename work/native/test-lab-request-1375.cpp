// Offline parser-only executable. It never invokes eu4_pair_1375::invoke,
// opens a process, loads a DLL, creates a mailbox, or calls game code.
#include "lab-request-1375.h"
#include <string>
#include <limits>

static unsigned checks = 0;
static unsigned failures = 0;
static void expect(bool condition, const char* label) {
    ++checks;
    if (!condition) { ++failures; std::printf("FAIL: %s\n", label); }
}
static std::string encoded(const eu4_lab_1375::MailboxRequest& request) {
    char text[eu4_lab_1375::kMaxRequestBytes + 1]{};
    const int count = eu4_lab_1375::render_request(request, text, sizeof(text));
    return count > 0 && static_cast<std::size_t>(count) < sizeof(text)
        ? std::string(text, static_cast<std::size_t>(count)) : std::string();
}
static bool accepted(const std::string& text) {
    eu4_lab_1375::MailboxRequest request{};
    return eu4_lab_1375::parse_request(text.data(), text.size(), request);
}
static std::string changed(std::string text, const char* before, const char* after) {
    const std::size_t offset = text.find(before);
    if (offset == std::string::npos) { expect(false, "mutation source exists"); return {}; }
    text.replace(offset, std::strlen(before), after);
    return text;
}
int main() {
    using namespace eu4_lab_1375;
    MailboxRequest request{};
    request.pid = 45564;
    request.creation = 0x01dd566ec360fab7ULL;
    request.sequence = 1;
    request.expires = 123456;
    strcpy_s(request.operation, "pair");
    strcpy_s(request.mode, "legality_only");
    strcpy_s(request.actor, "FRA");
    strcpy_s(request.target, "ENG");
    for (unsigned index = 0; index < 10; ++index) {
        const auto action = static_cast<eu4_pair_1375::ActionId>(index);
        const char* name = eu4_pair_1375::action_name(action);
        strcpy_s(request.action, name);
        expect(accepted(encoded(request)), name);
        strcpy_s(request.mode, "submit");
        expect(accepted(encoded(request)), "each action submit grammar");
        strcpy_s(request.mode, "legality_only");
    }
    strcpy_s(request.action, "improve_relations");
    const std::string good = encoded(request);
    MailboxRequest parsed{};
    expect(parse_request(good.data(), good.size(), parsed), "roundtrip parsed");
    expect(parsed.pid == request.pid && parsed.creation == request.creation
        && parsed.sequence == request.sequence && parsed.expires == request.expires
        && std::strcmp(parsed.action, request.action) == 0, "roundtrip identity");
    expect(!parse_request(nullptr, good.size(), parsed), "null input");
    expect(!parse_request(good.data(), 0, parsed), "empty input");
    expect(!parse_request(good.data(), kMaxRequestBytes + 1, parsed), "overlong before read");
    expect(!accepted(good.substr(0, good.size() - 1)), "missing final LF");
    expect(!accepted(good + "\n"), "trailing LF");
    expect(!accepted(good + "action=guarantee\n"), "duplicate action");
    expect(!accepted(good + "pointer=0x1234\n"), "extra pointer field");
    expect(!accepted(changed(good, "EU4LAB/1", "EU4LAB/2")), "unknown protocol");
    expect(!accepted(changed(good, "pid=45564", "pid=045564")), "leading decimal zero");
    expect(!accepted(changed(good, "pid=45564", "pid=+45564")), "signed pid");
    expect(!accepted(changed(good, "pid=45564", "pid=4294967296")), "pid overflow");
    expect(!accepted(changed(good, "pid=45564", "pid=0")), "zero pid");
    expect(!accepted(changed(good, "creation=01dd", "creation=01DD")), "uppercase hex");
    expect(!accepted(changed(good, "creation=01dd", "creation=1dd")), "short creation hex");
    expect(!accepted(changed(good, "sequence=1", "sequence=0")), "zero sequence");
    expect(!accepted(changed(good, "sequence=1", "sequence=-1")), "negative sequence");
    expect(!accepted(changed(good, "sequence=1", "sequence=9223372036854775808")), "sequence bound");
    expect(!accepted(changed(good, "expires=123456", "expires=18446744073709551616")), "expiry overflow");
    expect(!accepted(changed(good, "expires=123456", "expires=0")), "zero expiry");
    expect(!accepted(changed(good, "actor=FRA", "actor=SPA")), "unknown country");
    expect(!accepted(changed(good, "target=ENG", "target=FRA")), "same pair");
    expect(!accepted(changed(good, "target=ENG", "target=eng")), "lowercase country");
    expect(!accepted(changed(good, "mode=legality_only", "mode=execute")), "unknown mode");
    expect(!accepted(changed(good, "action=improve_relations", "action=arbitrary_script")), "unknown action");
    expect(!accepted(changed(good, "speed=0", "speed=1")), "pair cannot set speed");
    expect(!accepted(changed(good, "\npid=", "\r\npid=")), "CRLF rejected");
    expect(!accepted(changed(good, "\npid=", "\npid= ")), "space rejected");
    std::string embedded = good;
    embedded[good.find("action=")] = '\0';
    expect(!accepted(embedded), "embedded NUL rejected");
    embedded = good; embedded[0] = static_cast<char>(0x80);
    expect(!accepted(embedded), "non ASCII rejected");
    request.sequence = kMaxSequence;
    request.expires = (std::numeric_limits<std::uint64_t>::max)();
    expect(accepted(encoded(request)), "bounded numeric maxima grammar");
    // Expiry freshness and sequence monotonicity are host-state requirements,
    // deliberately not claimed by this syntax-only test.
    strcpy_s(request.operation, "speed");
    strcpy_s(request.mode, "submit");
    strcpy_s(request.action, "none");
    strcpy_s(request.target, "FRA");
    for (unsigned speed = 0; speed <= 5; ++speed) {
        request.speed = speed;
        expect(accepted(encoded(request)), "speed zero through five grammar");
    }
    const std::string speed = encoded(request);
    expect(!accepted(changed(speed, "speed=5", "speed=6")), "speed maximum");
    expect(!accepted(changed(speed, "speed=5", "speed=10")), "multi digit speed");
    expect(!accepted(changed(speed, "mode=submit", "mode=legality_only")), "speed mode");
    expect(!accepted(changed(speed, "action=none", "action=guarantee")), "speed action");
    expect(!accepted(changed(speed, "target=FRA", "target=ENG")), "speed target");
    eu4_pair_1375::ActionId action{};
    expect(!eu4_pair_1375::parse_action_id("improve_relations\0extra", 23, &action), "action embedded NUL length");
    expect(!eu4_pair_1375::parse_action_id("improve_relations", 17, nullptr), "action null destination");
    std::printf("Native lab grammar: %u checks, %u failures; no process or game calls.\n", checks, failures);
    return failures ? 1 : 0;
}
