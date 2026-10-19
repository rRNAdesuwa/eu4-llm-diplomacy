// Generated exact-build byte/data constants only. No native callable, resolver or hook.
// Pins do not prove SP, world epoch, lifetime, unwind safety or permission to send.
#pragma once
#include <cstdint>
namespace eu4_spy19_sender {
struct CodePin { std::uintptr_t rva; const char* hex; };
struct SlotPin { std::uintptr_t rva, target; };
inline constexpr CodePin kCodePins[] = {
    { 0xbfe50, "48894c2408534883ec20488bd9488b0514002802488b88001e0000488b01ff9080000000488b1348c703000000004889542438488d542438488bc8e880a3400190488b0b4885c97410488b01ba010000004883c4205b48ff204883c4205bc3" }, // world_context_path
    { 0x811aa0, "488b8130030000488b8070030000c3" }, // server_context_getter
    { 0x14ca210, "48895c240848897424184889542410574883ec20488bf2488bf9488b1a48c702000000004883795800750432dbeb5f4885db745a80795500752a80b90d080000007521488b03488bcbff908000000084c07511488b03488bcbff505884c0750432dbeb2a8b878c0000008943388b4768b9ff7f00003bc1660f4cc866894b48488b4f58488b01488bd3ff5030b301488b0e4885c9740b4c8b01ba0100000041ff100fb6c3488b5c2430488b7424404883c4205fc3" }, // context_submit_owned_slot
    { 0x14ca2d0, "48895c2408574883ec204883795800488bda488bf974664885d2746180795500752680b90d08000000751d488b02488bcaff908000000084c0750d488b03488bcbff505884c074358b878c000000b9ff7f0000894338488bd38b47683bc1660f4cc866894b48488b4f58488b01ff5030b001488b5c24304883c4205fc3488b5c243032c04883c4205fc3" }, // different_raw_pointer_abi_do_not_call
    { 0x1580370, "4885d20f8434090000488954241048894c240853565741544155415641574881ecb00b0000488bda4c8bf933f6" }, // transport_submit_entry
    { 0x1580c4a, "488b8c24f80b0000488b01ba01000000ff1090" }, // transport_original_command_delete
    { 0x8b0e0, "488d81c8000000c3" }, // transport_receiver_queue_getter
    { 0x14ca870, "48895c24205556574154415541564157488dac2460feffff4881eca0020000488bf933f6448bfe89b5e801000089b5e0010000488b4958488b01ff50484c8bf0488b18" }, // receiver_context_queue_entry
    { 0x14cab2a, "488b06488bceff504084c00f859d030000" }, // receiver_gate
    { 0x14caf25, "488d0584198c0048894424504889742458488d44245048894588488d4c2450e8279f000090" }, // receiver_callback_binding
    { 0x14cb130, "488b06ba01000000488bceff10" }, // receiver_command_delete
    { 0x14d4e70, "48894c24084883ec38e852ffffff0fb6c085c0740be886ffffff89442420eb08c7442420000000008b542420488b4c2440e88affffff4883c438c3" }, // callback_instrumentation_entry
    { 0x14d4e30, "8954241048894c24084883ec28837c24380076148b442438ffc88bd0488b4c2430e8daffffffeb0a488b4c2430e8bec0bcff4883c428c3" }, // callback_instrumentation_recursive
    { 0x10a0f20, "4883ec28488b49384885c9740b488b014883c42848ff6010e827b29600cc" }, // callback_function_invoker
    { 0x14cea10, "48895c24104889742418574883ec30488bf1488b4908488b01ff50508bd8" }, // command_callback_entry
    { 0x14ceaca, "488b4e08488b01488b5c2448488b7424504883c4305f48ff6048" }, // command_callback_tail
    { 0x4e7470, "48895c2408574883ec208bfa488bd9488d052aa07901488901488b49504885c97420488b01ff90a800000084c07513488b4b504885c9740a488b01ba01000000ff10488d0557327501488903488d4b18e89be1baff9040f6c701740dba58000000488bcbe817202501488bc3488b5c24304883c4205fc3" }, // owned_command_destructor
};
inline constexpr SlotPin kSlotPins[] = {
    { 0x1cb84e0, 0x811aa0 }, // server_context_getter
    { 0x1d961a8, 0x1580370 }, // transport_submit
    { 0x1d961c0, 0x8b0e0 }, // transport_queue
    { 0x1c814b0, 0x4e7470 }, // command_destructor
    { 0x1c814f0, 0x4e8630 }, // command_gate
    { 0x1c814f8, 0x4e7c50 }, // command_execute
    { 0x1d8c8c0, 0x14cea10 }, // callback_invoke
};
inline constexpr std::uintptr_t kContextSubmit = 0x14ca210;
inline constexpr std::uintptr_t kGameGlobal = 0x233fe78;
inline constexpr std::uintptr_t kGameServerOffset = 0x1e00;
inline constexpr std::uintptr_t kServerHolderOffset = 0x330;
inline constexpr std::uintptr_t kHolderContextOffset = 0x370;
inline constexpr std::uintptr_t kContextTransportOffset = 0x58;
inline constexpr std::uintptr_t kReady55Offset = 0x55, kReady80dOffset = 0x80d;
inline constexpr unsigned kReadyWidth = 1;
inline constexpr std::uintptr_t kServerVtable = 0x1cb8460, kTransportVtable = 0x1d96178;
} // namespace eu4_spy19_sender
