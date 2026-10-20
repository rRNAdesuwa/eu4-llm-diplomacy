// Applied only to genuinely owned action memory. Never writes game relations.
bool v11_fixed_fields(std::uintptr_t object, std::uint32_t token, bool factory_default) {
    if (token == 0x2947) return read_at<std::int32_t>(object + 0x40) == -1;
    if (token == 0x2948) return read_at<std::int32_t>(object + 0x40) == (factory_default ? 0 : 25000);
    if (token == 0x2e09) return read_at<std::int32_t>(object + 0x40) == (factory_default ? 0 : 500)
        && read_at<unsigned char>(object + 0x44) == 0;
    return true; // Remaining five new classes are0x40: no derived input field.
}
void v11_initialize_fixed(std::uintptr_t object, std::uint32_t token) {
    const std::int32_t insult = -1, gift = 25000, fraction = 500;
    const unsigned char ordinary = 0;
    if (token == 0x2947) std::memcpy(reinterpret_cast<void*>(object + 0x40), &insult, sizeof(insult));
    if (token == 0x2948) std::memcpy(reinterpret_cast<void*>(object + 0x40), &gift, sizeof(gift));
    if (token == 0x2e09) {
        std::memcpy(reinterpret_cast<void*>(object + 0x40), &fraction, sizeof(fraction));
        std::memcpy(reinterpret_cast<void*>(object + 0x44), &ordinary, sizeof(ordinary));
    }
}
unsigned v11_mode_count(std::uint32_t token) {
    return token == 0x2942 || token == 0x2947 || token == 0x2948 || token == 0x3bce ? 1U : 2U;
}
