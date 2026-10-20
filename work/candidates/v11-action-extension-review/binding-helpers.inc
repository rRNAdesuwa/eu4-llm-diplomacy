// New-family guards only. Called before allocation, after native setter and
// before dispatch by the unchanged engine ownership pipeline. No native calls.
bool v11_optional_index(std::uintptr_t owner, const Country& other, std::uintptr_t offset,
                        std::uintptr_t count_offset, std::uintptr_t& object) {
    std::uintptr_t root = 0, record = 0;
    if (!record_root(owner, other, root, record)) return false;
    const auto array = read_at<std::uintptr_t>(root + offset);
    const auto count = read_at<std::uint32_t>(root + count_offset);
    if (count > kMaxRelations || (array != 0 && !pointer(array)) || (count != 0 && array == 0)) return false;
    bool slots[kMaxRelations]{};
    object = 0;
    for (unsigned i = 0; i < count; ++i) {
        const auto item = array + static_cast<std::uintptr_t>(i) * 0x10;
        const auto slot = read_at<std::uint32_t>(item);
        const auto value = read_at<std::uintptr_t>(item + 8);
        if (slot >= kMaxRelations || slots[slot] || !pointer(value)) return false;
        slots[slot] = true;
        if (slot == other.slot) object = value;
    }
    return true; // object==0 means a validated absent slot, not a read error.
}
bool v11_pair_index(const Live& live, const Country& actor, const Country& target,
                    std::uintptr_t a, std::uintptr_t ac, std::uintptr_t b, std::uintptr_t bc,
                    std::uintptr_t& object) {
    std::uintptr_t reverse = 0;
    return v11_optional_index(live.actor_object, target, a, ac, object)
        && v11_optional_index(live.target_object, actor, b, bc, reverse) && object == reverse;
}
bool v11_header(std::uintptr_t module, const Live& live, std::uintptr_t object, std::uintptr_t vt,
                std::uint64_t first, std::uint64_t second) {
    if (!pointer(object) || read_at<std::uintptr_t>(object) != module + vt
        || read_at<std::uint32_t>(object + 8) != 0x165 || read_at<unsigned char>(object + 0x28) != 0
        || read_at<std::uint64_t>(object + 0x10) != first || read_at<std::uint64_t>(object + 0x18) != second) return false;
    const auto start = read_at<std::int32_t>(object + 0x20);
    return start > 0 && start <= live.stamp.raw_date;
}
bool v11_coalition(const Live& live, const Country& actor, const Country& target, bool positive, Binding& binding) {
    if (!pointer(live.database) || !pointer(live.array)
        || read_at<std::uintptr_t>(live.database + 0x118) != live.array) return false;
    const auto country_count = read_at<std::uint32_t>(live.database + 0x124);
    if (country_count == 0 || country_count > kMaxRelations || actor.slot >= country_count || target.slot >= country_count) return false;
    const auto existing = read_at<std::uint64_t>(live.actor_object + 0x18f8);
    if (positive ? existing != 0x2d2d2d : existing != target.handle) return false;
    const auto head = read_at<std::uintptr_t>(live.target_object + 0x1910);
    const auto tail = read_at<std::uintptr_t>(live.target_object + 0x1918);
    const auto count = read_at<std::uint32_t>(live.target_object + 0x1920);
    if (count > 1024 || read_at<unsigned char>(live.target_object + 0x1924) != 0) return false;
    std::uintptr_t current = head, previous = 0, selected = 0;
    bool slots[kMaxRelations]{};
    for (unsigned i = 0; i < count; ++i) {
        if (!pointer(current) || read_at<std::uintptr_t>(current + 8) != previous) return false;
        const auto removed = read_at<unsigned char>(current + 0x18);
        if (removed > 1) return false;
        if (removed == 0) {
            const auto handle = read_at<std::uint64_t>(current);
            const auto slot = static_cast<unsigned>((handle >> 32) & 0xffff);
            if ((handle >> 56) == 0 || slot >= country_count || slots[slot]) return false;
            slots[slot] = true;
            const auto member = read_at<std::uintptr_t>(live.array + static_cast<std::uintptr_t>(slot) * 8);
            if (!pointer(member) || read_at<std::uint64_t>(member + 0x20) != handle
                || read_at<std::uint64_t>(member + 0x18f8) != target.handle) return false;
            if (slot == actor.slot) {
                if (handle != actor.handle || selected != 0) return false;
                selected = current;
            }
        }
        previous = current;
        current = read_at<std::uintptr_t>(current + 0x10);
    }
    if (current != 0 || previous != tail || (count == 0 && (head != 0 || tail != 0))) return false;
    if (read_at<std::uintptr_t>(live.database + 0x118) != live.array
        || read_at<std::uint32_t>(live.database + 0x124) != country_count) return false;
    if (positive ? selected != 0 : selected == 0) return false;
    binding.entry = selected;
    binding.mission = read_at<std::uint32_t>(live.actor_object + 0x1940);
    binding.scope[0] = existing; binding.scope[1] = head; binding.scope[2] = tail; binding.scope[3] = count;
    binding.scope[4] = country_count;
    return true;
}
bool v11_subject_scope(std::uintptr_t module, const Live& live, const Country& actor, const Country& target, Binding& binding) {
    const auto ao = read_at<std::uint64_t>(live.actor_object + 0x18f0);
    const auto to = read_at<std::uint64_t>(live.target_object + 0x18f0);
    const bool actor_subject = (ao >> 56) != 0, target_subject = (to >> 56) != 0;
    if (actor_subject == target_subject) return false;
    const Country& dependent = actor_subject ? actor : target;
    const Country& provider = actor_subject ? target : actor;
    const auto dependent_object = actor_subject ? live.actor_object : live.target_object;
    const auto provider_overlord = actor_subject ? to : ao;
    const auto overlord_handle = actor_subject ? ao : to;
    if (provider_overlord != 0x2d2d2d || overlord_handle == provider.handle) return false;
    const Country* overlord = nullptr;
    for (const Country& item : kCountries) if (item.handle == overlord_handle) overlord = &item;
    if (overlord == nullptr) return false; // Deliberately bounded to independently resolved known TAGs.
    std::uintptr_t overlord_object = 0;
    if (!resolve_country(live.array, *overlord, overlord_object)) return false;
    Live relation_live = live;
    relation_live.actor_object = overlord_object; relation_live.target_object = dependent_object;
    std::uintptr_t dependency = 0;
    if (!v11_pair_index(relation_live, *overlord, dependent, 0x128, 0x134, 0x128, 0x134, dependency)
        || !v11_header(module, live, dependency, 0x1c81758, overlord_handle, dependent.handle)) return false;
    const auto definition = read_at<std::uintptr_t>(dependency + 0x40);
    const auto registry = read_at<std::uintptr_t>(module + kSubjectRegistry);
    if (!pointer(registry) || !pointer(definition)) return false;
    const bool known = (definition == read_at<std::uintptr_t>(registry + 0x58) && definition_name(definition, "vassal"))
        || (definition == read_at<std::uintptr_t>(registry + 0x60) && definition_name(definition, "client_vassal"));
    if (!known || read_at<unsigned char>(definition + 0x11a) == 0) return false;
    binding.scope[0] = dependent.handle; binding.scope[1] = provider.handle; binding.scope[2] = overlord_handle;
    binding.scope[3] = dependency; binding.scope[4] = definition;
    binding.scope[5] = read_at<std::uint32_t>(dependency + 0x20);
    return true;
}
bool v11_binding(std::uintptr_t module, const Live& live, const Country& actor, const Country& target,
                 unsigned family, bool positive, Binding& binding) {
    binding = {-1, 0, 0, 0};
    std::uintptr_t object = 0;
    if (family == 12) { // Warning true only; preserve an existing warning in either direction.
        return positive && v11_pair_index(live, actor, target, 0x1b8, 0x1c4, 0x1b8, 0x1c4, object) && object == 0;
    }
    if (family == 13 || family == 18 || family == 19) return positive;
    if (family == 14) return v11_coalition(live, actor, target, positive, binding);
    if (family == 15) {
        if (!v11_subject_scope(module, live, actor, target, binding)
            || !v11_pair_index(live, actor, target, 0x170, 0x17c, 0x170, 0x17c, object)) return false;
        if (positive) return object == 0;
        if (!v11_header(module, live, object, 0x1c80570, actor.handle, target.handle)
            && !v11_header(module, live, object, 0x1c80570, target.handle, actor.handle)) return false;
        binding.entry = object; binding.mission = read_at<std::uint32_t>(object + 0x20);
        binding.scope[6] = read_at<std::uint64_t>(object + 0x10);
        binding.scope[7] = read_at<std::uint64_t>(object + 0x18);
        return true;
    }
    if (family == 16 || family == 17) {
        const bool transfer = family == 16;
        const std::uintptr_t supplier = transfer ? 0x230 : 0x260, supplier_count = transfer ? 0x23c : 0x26c;
        const std::uintptr_t receiver = transfer ? 0x248 : 0x278, receiver_count = transfer ? 0x254 : 0x284;
        std::uintptr_t incoming = 0, outgoing = 0;
        if (!v11_pair_index(live, actor, target, receiver, receiver_count, supplier, supplier_count, incoming)
            || !v11_pair_index(live, actor, target, supplier, supplier_count, receiver, receiver_count, outgoing)) return false;
        if (positive) return incoming == 0 && outgoing == 0;
        if ((incoming == 0) == (outgoing == 0)) return false; // no direction guessing or ambiguous bidirectional state
        object = incoming != 0 ? incoming : outgoing;
        if (!v11_header(module, live, object, transfer ? 0x1c571f0 : 0x1c7d498,
                incoming ? target.handle : actor.handle, incoming ? actor.handle : target.handle)) return false;
        if (read_at<unsigned char>(object + (transfer ? 0x44 : 0x40)) != 0
            || (transfer && read_at<std::int32_t>(object + 0x40) != 500)) return false;
        binding.entry = object; binding.mission = read_at<std::uint32_t>(object + 0x20);
        binding.scope[0] = incoming != 0 ? 1 : 2;
        binding.scope[1] = read_at<std::uint64_t>(object + 0x10);
        binding.scope[2] = read_at<std::uint64_t>(object + 0x18);
        binding.scope[3] = transfer ? 500 : 0;
        return true;
    }
    return false;
}
