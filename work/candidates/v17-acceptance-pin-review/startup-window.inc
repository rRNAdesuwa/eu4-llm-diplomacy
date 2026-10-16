// BridgeStart-only initialization: do not depend on static aggregate defaults.
// This cannot clear a pending/closed historical grant or any unknown field.
inline bool startup_name(const char* value, std::size_t capacity, bool allow_zero) {
    bool all_zero = true;
    for (std::size_t i = 0; i < capacity; ++i) if (value[i] != 0) all_zero = false;
    if (allow_zero && all_zero) return true;
    if (capacity < 5 || std::memcmp(value, "none", 5)) return false;
    for (std::size_t i = 5; i < capacity; ++i) if (value[i] != 0) return false;
    return true;
}
inline bool startup_window(const AcceptanceWindow& w, bool allow_zero_names) {
    return w.state == WindowState::closed && w.on_sequence == 0 && w.submit_sequence == 0
        && w.off_sequence == 0 && w.world == 0 && w.player == 0 && w.date == 0
        && w.thread == 0 && w.off_frame == 0
        && startup_name(w.action, sizeof(w.action), allow_zero_names)
        && startup_name(w.target, sizeof(w.target), allow_zero_names);
}
inline bool initialize_startup_window(AcceptanceWindow& w) {
    if (!startup_window(w, true)) return false;
    // Every logical field is assigned explicitly before the first hook/log.
    w.state = WindowState::closed;
    w.on_sequence = 0; w.submit_sequence = 0; w.off_sequence = 0;
    std::memset(w.action, 0, sizeof(w.action)); std::memcpy(w.action, "none", 5);
    std::memset(w.target, 0, sizeof(w.target)); std::memcpy(w.target, "none", 5);
    w.world = 0; w.player = 0; w.date = 0; w.thread = 0; w.off_frame = 0;
    return startup_window(w, false);
}

