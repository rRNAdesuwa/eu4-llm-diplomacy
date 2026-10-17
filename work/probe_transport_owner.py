"""Read-only identity-bound comparison of native UI and server transport roots."""
from pathlib import Path

source_path = Path(__file__).with_name("probe_native_state.py")
source = source_path.read_text(encoding="utf-8")
source = source.replace("    args = parser.parse_args()",
    "    parser.add_argument('--operator-session', type=Path, required=True)\n    args = parser.parse_args()")
body = r'''
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from bridge.diplomacy_session import probe_identity
        installation = json.loads(args.operator_session.read_text(encoding='utf-8-sig'))
        identity = probe_identity(args.pid, GAME)
        expected = {key: installation[key] for key in ('pid', 'creation_filetime', 'game_sha256', 'session_id')}
        if any(identity[key] != value for key, value in expected.items()):
            raise RuntimeError('Exact process identity changed')
        if len(identity['modules']) != 1 or identity['modules'][0]['sha256'] != installation['dll_sha256']:
            raise RuntimeError('Exact observer module changed')
        server = qword(game + 0x1e00)
        server_vtable = qword(server)
        getter = qword(server_vtable + 0x80)
        world_context = qword(server + 0x330)
        world_dispatcher = qword(world_context + 0x370)
        ui = qword(base + 0x2349550)
        ui_context = qword(ui + 0x330)
        ui_dispatcher = qword(ui_context + 0x370)
        transport = qword(world_dispatcher + 0x58)
        transport_vtable = qword(transport)
        submit = qword(transport_vtable + 0x30)
        counter = qword(transport + 0x128)
        counter_bytes = read(counter, 16)
        report = {'session': identity, 'read_only': True,
            'native_methods_invoked': False, 'business_submission': False,
            'date_raw': int.from_bytes(read(game + 0x1dd0, 4), 'little', signed=True),
            'raw': {'server_vtable_rva': hex(server_vtable - base),
                    'server_getter_rva': hex(getter - base),
                    'ui_dispatcher': hex(ui_dispatcher), 'world_dispatcher': hex(world_dispatcher),
                    'transport_vtable_rva': hex(transport_vtable - base),
                    'transport_submit_rva': hex(submit - base),
                    'counter_address': hex(counter), 'counter_raw16': counter_bytes.hex()},
            'checks': {'server_getter_matches_static_candidate': getter == base + 0x811ad0,
                       'ui_and_server_dispatcher_identical': ui_dispatcher == world_dispatcher,
                       'transport_method_matches_static_candidate': submit == base + 0x1580270,
                       'counter_readable': len(counter_bytes) == 16},
            'alliance_sender_runtime_verified': False,
            'authorization_lifecycle_runtime_verified': False}
        with args.output.open('x', encoding='utf-8') as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
'''
assert source.count("        slots = []") == 1
source = source.replace("        slots = []", body + "\n        slots = []")
exec(compile(source, str(source_path), "exec"),
     {"__name__": "__main__", "__file__": str(source_path)})
