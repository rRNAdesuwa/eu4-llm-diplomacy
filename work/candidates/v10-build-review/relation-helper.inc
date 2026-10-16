// Directional rights use distinct holder/grantor indexes. No native getter call.
bool directional_relation(std::uintptr_t module, const Live& live, const Country& actor, const Country& target,
                          bool actor_holds, std::uintptr_t holder_offset, std::uintptr_t holder_count,
                          std::uintptr_t grantor_offset, std::uintptr_t grantor_count,
                          std::uintptr_t vtable, std::uintptr_t& object) {
    std::uintptr_t reverse = 0;
    const auto holder_object = actor_holds ? live.actor_object : live.target_object;
    const auto grantor_object = actor_holds ? live.target_object : live.actor_object;
    const Country& holder = actor_holds ? actor : target;
    const Country& grantor = actor_holds ? target : actor;
    return indexed_object(holder_object, grantor, holder_offset, holder_count, object)
        && indexed_object(grantor_object, holder, grantor_offset, grantor_count, reverse) && object == reverse
        && read_at<std::uintptr_t>(object) == module + vtable && read_at<unsigned char>(object + 0x28) == 0
        && read_at<std::uint64_t>(object + 0x10) == holder.handle && read_at<std::uint64_t>(object + 0x18) == grantor.handle
        && read_at<unsigned char>(object + 0x40) == 0; // reject enforce_peace variants
}
