    if (id == ActionId::cancel_subsidies) {
        if (!paired_relation(module, live, actor, target, 0x110, 0x11c, 0x1c815d8, object)
            || read_at<std::int32_t>(object + 0x40) != 1000 || read_at<std::int32_t>(object + 0x44) != 10) return false;
        binding.entry = object; // compare only; never an envoy pointer for this family
        binding.mission = read_at<std::uint32_t>(object + 0x20);
        return true;
    }
    if (id == ActionId::dissolve_alliance) {
        std::uintptr_t reverse = 0;
        if (!indexed_object(live.actor_object, target, 0x80, 0x8c, object)
            || !indexed_object(live.target_object, actor, 0x80, 0x8c, reverse) || object != reverse
            || read_at<std::uintptr_t>(object) != module + 0x1c7a740 || read_at<unsigned char>(object + 0x28) != 0) return false;
        const auto first = read_at<std::uint64_t>(object + 0x10), second = read_at<std::uint64_t>(object + 0x18);
        if (!((first == actor.handle && second == target.handle) || (first == target.handle && second == actor.handle))) return false;
        binding.entry = object;
        binding.mission = read_at<std::uint32_t>(object + 0x20);
        return true;
    }
    const bool cancel_military = id == ActionId::cancel_military_access || id == ActionId::revoke_military_access;
    const bool cancel_fleet = id == ActionId::cancel_fleet_basing_rights || id == ActionId::revoke_fleet_basing_rights;
    if (cancel_military || cancel_fleet) {
        const bool actor_holds = id == ActionId::cancel_military_access || id == ActionId::cancel_fleet_basing_rights;
        if (!directional_relation(module, live, actor, target, actor_holds,
                cancel_military ? 0xb0 : 0xe0, cancel_military ? 0xbc : 0xec,
                cancel_military ? 0xc8 : 0xf8, cancel_military ? 0xd4 : 0x104,
                cancel_military ? 0x1cdde60 : 0x1cddee0, object)) return false;
        binding.entry = object;
        binding.mission = read_at<std::uint32_t>(object + 0x20);
        return true;
    }
    if (id == ActionId::revoke_embargo) {
        std::uintptr_t root = 0, record = 0;
        if (!record_root(live.actor_object, target, root, record)
            || !(read_at<unsigned char>(record + 0x46) & 0x02)) return false;
        binding.entry = record;
        return true;
    }
