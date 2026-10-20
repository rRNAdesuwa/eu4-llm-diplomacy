// Factory/clone defaults are separate from initialized request state.
// 35e051 writes coalition state=2 and jumps past the shared state=0 store.
struct ContractDiagnostic {
    bool completed = false;
    bool state_read = false;
    std::uint32_t state = 0;
    std::uint32_t failure_mask = 0;
};
template <typename T>
void contract_field(std::uintptr_t object, std::uintptr_t offset, T expected,
                    unsigned bit, ContractDiagnostic& diagnostic) {
    if (read_at<T>(object + offset) != expected) diagnostic.failure_mask |= (1U << bit);
}
bool default_fields_match(std::uintptr_t object, const Action& action, std::uintptr_t base,
                          ContractDiagnostic& diagnostic, bool fixed_parameters = false) {
    if (object == 0 || object == base + 0x1fd1ca0) {
        diagnostic.failure_mask |= 1U;
        diagnostic.completed = true;
        return false;
    }
    contract_field(object, 0, base + action.vtable, 1, diagnostic);
    if (diagnostic.failure_mask != 0) {
        diagnostic.completed = true;
        return false; // Do not inspect fields of an object with the wrong derived identity.
    }
    contract_field(object, 8, static_cast<std::uint32_t>(0x165), 2, diagnostic);
    contract_field(object, 0x10, static_cast<std::uint64_t>(0x2d2d2d), 3, diagnostic);
    contract_field(object, 0x18, static_cast<std::uint64_t>(0x2d2d2d), 4, diagnostic);
    contract_field(object, 0x20, static_cast<std::uint64_t>(0x2d2d2d), 5, diagnostic);
    contract_field(object, 0x28, static_cast<std::uint32_t>(0x29c77f8), 6, diagnostic);
    contract_field(object, 0x2c, static_cast<std::uint32_t>(0x29c77f8), 7, diagnostic);
    contract_field(object, 0x30, static_cast<std::uint32_t>(0xffffffff), 8, diagnostic);
    diagnostic.state = read_at<std::uint32_t>(object + 0x34);
    diagnostic.state_read = true;
    if (diagnostic.state != (action.token == 0x2de0 ? 2U : 0U)) diagnostic.failure_mask |= 1U << 9;
    contract_field(object, 0x38, static_cast<std::uint16_t>(1), 10, diagnostic);
    contract_field(object, 0x3c, static_cast<std::uint32_t>(0), 11, diagnostic);
    if (action.token == 0x2947) contract_field(object, 0x40, static_cast<std::int32_t>(-1), 12, diagnostic);
    if (action.token == 0x2948) contract_field(object, 0x40, static_cast<std::int32_t>(fixed_parameters ? 25000 : 0), 13, diagnostic);
    if (action.token == 0x2e09) {
        contract_field(object, 0x40, static_cast<std::int32_t>(fixed_parameters ? 500 : 0), 14, diagnostic);
        contract_field(object, 0x44, static_cast<unsigned char>(0), 15, diagnostic);
    }
    if (action.token == 0x2a25) {
        contract_field(object, 0x40, static_cast<std::int32_t>(fixed_parameters ? 1000 : 0), 16, diagnostic);
        contract_field(object, 0x44, static_cast<std::int32_t>(fixed_parameters ? 10 : 0), 17, diagnostic);
    }
    if (action.size == 0x68) {
        contract_field(object, 0x40, static_cast<unsigned char>(0), 18, diagnostic);
        contract_field(object, 0x50, static_cast<std::uint64_t>(0), 19, diagnostic);
        contract_field(object, 0x58, static_cast<std::uint64_t>(15), 20, diagnostic);
        contract_field(object, 0x60, static_cast<unsigned char>(0), 21, diagnostic);
    }
    diagnostic.completed = true;
    return diagnostic.failure_mask == 0;
}
void format_diagnostic(const ContractDiagnostic& diagnostic, char (&state)[16], char (&mask)[16]) {
    if (diagnostic.state_read) std::snprintf(state, sizeof(state), "%u", diagnostic.state);
    else std::memcpy(state, "null", 5);
    if (diagnostic.completed) std::snprintf(mask, sizeof(mask), "%u", diagnostic.failure_mask);
    else std::memcpy(mask, "null", 5);
}
