#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <string_view>
#include <vector>

// Private bounded reader component. No OS access, native calls or public handles.
namespace country1375 {
struct Tag { std::array<char,3> bytes{}; bool operator==(const Tag&) const noexcept; };
bool parse_tag(std::string_view, Tag&) noexcept;
class ReadPort {
public:
    virtual ~ReadPort() = default;
    virtual bool read(std::uint64_t, void*, std::size_t) = 0;
};
struct Roots {
    std::uint64_t module{}, database{}, game{}, array{}, current{}, alternate{}, load{};
    std::uint32_t capacity{}, count{}, date{};
    std::uint8_t selector{}, alternate_flag{}, reset{};
    bool operator==(const Roots&) const noexcept;
};
struct Row {
    std::uint64_t address{}, vtable{}, handle{};
    std::uint32_t marker{}, slot{};
    Tag tag{};
    bool sentinel{};
    bool operator==(const Row&) const noexcept;
};
struct Snapshot {
    Roots roots{};
    std::vector<std::uint64_t> array;
    std::vector<Row> rows;
    bool operator==(const Snapshot&) const noexcept;
};
// These bindings stay inside the adapter; callers submit only TAG strings.
struct Binding { Tag tag{}; std::uint32_t slot{}; std::uint64_t address{}, handle{}; };
enum class Status { InvalidRequest, UnavailableRead, UnsupportedLayout, InvalidObservation, Changed, MissingTag, Resolved };
struct Result {
    Status status{Status::InvalidRequest};
    const char* reason{"invalid request"};
    Snapshot snapshot;
    std::vector<Binding> bindings;
    std::uint32_t read_calls{};
    std::uint64_t read_bytes{};
    bool stable_two_pass{}, atomic{}, runtime_verified{}, native_authorized{}, production_ready{};
};
// Port of the independently reviewed Python resolver, ordinary selector0 only.
// Whole typed passes are compared; equal observations do not exclude ABA.
Result resolve(ReadPort&, std::uint64_t module, const std::vector<std::string_view>& tags) noexcept;
}
