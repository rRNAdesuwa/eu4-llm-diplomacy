"""Bounded disk-only native peace GUI send callback and ownership evidence."""
from __future__ import annotations
import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg
from trace_change_subject_type import rows

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'work/reports/native-peace-gui-send-1375.json'
INPUTS = (
    ('work/reports/native-owned-peace-1375.json', 'f78ca33e46e8a7ea153055ffb77f940710b263a7a366acfc7dfee40c35e7488d'),
    ('work/runtime/unpacked-1.37.5/base/interface/peaceview.gui', '821c09cc2cc83dd1239a6a2fe0302f1cca74210b5619448dc85b974c80980e18'),
)
ENTRIES = (0x1309320, 0x1309b70, 0x130f1b0, 0x836430, 0x598af0,
           0x59bee0, 0x4e9930, 0x59ba40, 0x4e7470, 0x14ca210, 0x8f450)

def fact(summary, *anchors):
    return {'summary': summary, 'anchors': anchors}

FACTS = {
    'send_button_binding': fact(
        'The unpacked peaceview.gui send button is labeled SEND_OFFER. GUI constructor1309320 installs listener vtable1cb80c8 at GUI+668, owner=this at+670 and callback130f1b0 at+678. Initialization1309b70 looks up literal send through GUI root+38 virtual68 and registers this exact listener in the button+C8 list after checking for duplicate registration. Listener virtual18=836430 invokes its+10 callback with owner+8 as RCX. This binds the native peace send handler independently of historical version addresses.',
        0x1309452, 0x13096a8, 0x13096af, 0x13096b6, 0x13096bd,
        0x1309fa1, 0x1309fa8, 0x1309faf, 0x1309fb6, 0x1309fbe,
        0x1309fd0, 0x1309fe4, 0x1309fe7, 0x836430, 0x836439, 0x83643d),
    'callback_allocates_original_and_copies_selected_offer': fact(
        '130f1b0 allocates an original requestpeace of0x210 bytes. GUI+660 selects offer pointer GUI+48 when true or+208 when false and becomes demand R9B; GUI+2c supplies target R8. Actor RDX is the effective-country handle from game+1e60, or+1e68 only for game+1e66==7 and+1e6f!=0; it must not be conflated with game.player+1da0. Current game date is stack argument6. Constructor598af0 deep-copies selected offer into original+48 via975f40, sets diplomats+40=1 and force+208=0. The GUI source remains independent and owned by the GUI.',
        0x130f1c2, 0x130f1c7, 0x130f1d8, 0x130f1df, 0x130f1e7,
        0x130f1ec, 0x130f1f5, 0x130f1fc, 0x130f205, 0x130f20e, 0x130f217,
        0x130f21e, 0x130f223, 0x130f228, 0x130f22f,
        0x598b04, 0x598b08, 0x598b0c, 0x598b39, 0x598b3d, 0x598b45, 0x598b4a, 0x598b4f),
    'native_preview_and_force_flag_are_not_acceptance': fact(
        'The handler obtains a native reason-buffer object withdf320, clears it via5ae8a0 and ensures capacity for40 records with5aeb70. It calls request virtual120=59bee0 with RDX=that object,R8=false; return>=1 sets original.force+208=1.59bee0 includes a game+23a1/effective-country special branch returning99999 and a force+208 branch returning1000 when R8=false; otherwise it delegates to1bf150 with recipient country,actor and embedded offer. These are exact native UI decision rules; their existence does not authorize bypasses or establish that the recipient accepted. Constructor starts force at0.',
        0x130f23c, 0x130f243, 0x130f24e, 0x130f26c, 0x130f27a,
        0x130f282, 0x130f285, 0x130f28b, 0x130f291, 0x130f296,
        0x59bef7, 0x59bf4d, 0x59bf58, 0x59bf62, 0x59bf67, 0x59bfa1, 0x59bfa5, 0x59bfb2, 0x59bfb7),
    'native_date_gate_and_context_lookup': fact(
        'Before wrapping, callback compares actor slot with game.player+1da0 slot. If equal, current date must exceed game+1d9c. For every actor current date must exceed actor.country+24a0. A failed date condition skips submission and still destroys the original. The submit context is GUI+978 -> owner+330 -> holder+370. This is a native lookup chain, not evidence that arbitrary current context/world is safe to reuse.',
        0x130f2a4, 0x130f2ab, 0x130f2b3, 0x130f2be, 0x130f2c3, 0x130f2ca,
        0x130f2d7, 0x130f2de, 0x130f2e2, 0x130f2e8, 0x130f2ea, 0x130f2f1, 0x130f2f8),
    'wrapper_clones_whole_owned_offer': fact(
        '130f307 calls4e9930 on the original request. That wrapper invokes action virtual+b0=59ba40, allocates a distinct command0x58, owns the resulting clone at command+50 and returns the address of the caller command container.59ba40 allocates another0x210 action and deep-copies its embedded offer via975f40. The selected GUI offer, original request offer and command-owned clone offer are three independently owned instances; they are not pointer aliases.',
        0x130f2ff, 0x130f304, 0x130f307, 0x4e9940, 0x4e9957, 0x4e9960,
        0x4e9991, 0x4e99ba, 0x4e99bd, 0x59ba4d, 0x59ba52, 0x59babb,
        0x59bac2, 0x59bacd, 0x59bad1, 0x59bad6),
    'submit_consumes_container_not_acceptance_ack': fact(
        '130f312 calls14ca210(context,&command), then ignores its bool result.14ca210 immediately reads and clears the caller container. With a transport present, non-null command and native command/context gates satisfied it writes command scheduling fields and calls transport virtual30, then returns true. False paths also have already consumed the original container; this function does not visibly delete the stolen local command on every early rejection. Therefore after entry ownership is transferred/uncertain even on false; caller must not independently reclaim or retry. A true result proves only the transport call returned, not native command execution, diplomacy acceptance or treaty application.',
        0x130f30c, 0x130f30f, 0x130f312, 0x130f317,
        0x14ca22a, 0x14ca22d, 0x14ca234, 0x14ca244, 0x14ca24a,
        0x14ca259, 0x14ca269, 0x14ca27a, 0x14ca28b, 0x14ca28f,
        0x14ca299, 0x14ca29c, 0x14ca29e, 0x14ca2ae, 0x14ca2b1),
    'original_and_command_have_distinct_cleanup': fact(
        'After a submitted or date-skipped path130f323 calls9761c0 on original+48 then restores the base vtable and tail-frees only its0x210 outer allocation. It does not separately destroy the command-owned clone. Command deleting destructor4e7470 reads owned action+50, checks action virtual+a8, and if false calls its deleting destructor(1).Requestpeace+a8 is the false leaf8f450, so command destruction owns request clone deletion including nested offer cleanup as established in the pinned lifecycle report. Exception unwinding and allocation-failure behavior are not closed.',
        0x130f323, 0x130f327, 0x130f32c, 0x130f333, 0x130f336,
        0x130f34d, 0x4e7489, 0x4e7495, 0x4e749d, 0x4e74a8,
        0x4e74ab, 0x4e74b0, 0x4e74bc, 0x4e74c0, 0x4e74cc, 0x4e74d4),
}

def generate():
    inputs = []
    for name, expected in INPUTS:
        path = ROOT / name
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('Input budget exceeded')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Pinned input changed: ' + name)
        inputs.append({'path': name, 'sha256': expected})
    pe = PE(ROOT.parent / 'eu4.exe')
    if hashlib.sha256(pe.data).hexdigest() != SHA:
        raise ValueError('Executable identity mismatch')
    md, _ = make_disassembler(Path(tempfile.gettempdir()) / 'eu4-native-analysis-deps')
    functions = {}; decoded = 0
    for entry in ENTRIES:
        code, edges = bounded_cfg(pe, md, entry, window=0x2000, max_instructions=2000)
        decoded += sum(i.size for i in code)
        if decoded > 32768:
            raise ValueError('Decode budget exceeded')
        functions[hex(entry)] = {'pdata': list(map(hex, pe.function(entry) or ())),
                                 'instructions': rows(pe, code), 'edges': edges}
        check_memory_budget()
    lookup = {row['rva']: row for value in functions.values() for row in value['instructions']}
    facts = {name: {'summary': item['summary'], 'runtime_verified': False,
                    'instructions': [lookup[hex(rva)] for rva in item['anchors']]}
             for name, item in FACTS.items()}
    slots = {}
    for vt, expected in (
        (0x1cb80c8, {0x18: 0x836430}),
        (0x1c7b840, {0: 0x598b60, 0x40: 0x4e9930, 0xa8: 0x8f450, 0xb0: 0x59ba40, 0x120: 0x59bee0}),
        (0x1c814b0, {0: 0x4e7470, 0x58: 0x8f450, 0x80: 0x8f450}),
    ):
        slots[hex(vt)] = {}
        for slot, method in expected.items():
            actual = pe.u64(pe.to_offset(vt + slot)) - pe.base
            if actual != method:
                raise ValueError('Method table mismatch')
            slots[hex(vt)][hex(slot)] = hex(actual)
    if pe.bytes_at(0x1d593cc, 5) != b'send\0' or pe.bytes_at(0x1d75a18, 11) != b'peace_view\0':
        raise ValueError('GUI string mismatch')
    return {'schema': 'native_peace_gui_send_1375_v1', 'game_sha256': SHA,
            'runtime_verified': False, 'execution_verified': False, 'inputs': inputs,
            'facts': facts, 'functions': functions, 'vtable_slots': slots,
            'gui_source': {'path': INPUTS[1][0], 'lines': [454, 463], 'name': 'send', 'text': 'SEND_OFFER'},
            'strings': {'0x1d593cc': 'send', '0x1d75a18': 'peace_view'},
            'unresolved': [
                'No process access, constructor/clone/destructor/GUI invocation, hook or native submission was performed.',
                'Nested offer lifecycle comes from the separately pinned report; this report does not runtime-verify allocation/ABI/SEH unwinding.',
                'GUI effective-country selection and slot comparisons are documented native behavior, not sufficient public API full-handle/world-epoch guards.',
                'Native preview score and force flag semantics are not recipient acceptance; a public interface may not expose an arbitrary force override.',
                'Transport ring consumption, final command execution, treaty acceptance/application and persistence are not established by this static callback trace.',
                'The complete mouse/keyboard-to-widget event pipeline is not enumerated; the send listener registration, callback dispatch virtual and native send body are identified.'],
            'limits': {'functions': len(functions), 'max_window_bytes': 0x2000,
                       'max_instructions_per_function': 2000, 'decoded_bytes': decoded,
                       'max_decoded_bytes': 32768, 'memory_guard_mib': 768, 'process_access': False}}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    report = generate()
    raw = (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode()
    if args.check:
        if OUTPUT.read_bytes() != raw:
            raise ValueError('Report differs')
    else:
        OUTPUT.write_bytes(raw)
    print(json.dumps({'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                      'decoded_bytes': report['limits']['decoded_bytes'], 'check': args.check}))

if __name__ == '__main__':
    main()
