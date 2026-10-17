"""Read one exact-session transport ring's proven metadata; never drain it."""
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
        for field in ('pid', 'creation_filetime', 'game_sha256', 'session_id'):
            if identity[field] != installation[field]:
                raise RuntimeError('Exact process identity changed')
        if len(identity['modules']) != 1 or identity['modules'][0]['sha256'] != installation['dll_sha256']:
            raise RuntimeError('Exact observer module changed')
        server = qword(game + 0x1e00)
        context = qword(server + 0x330)
        dispatcher = qword(context + 0x370)
        ui_context = qword(qword(base + 0x2349550) + 0x330)
        if qword(ui_context + 0x370) != dispatcher:
            raise RuntimeError('UI and server dispatcher differ')
        receiver = qword(dispatcher + 0x58)
        if qword(receiver) != base + 0x1d95fd8 or qword(receiver + 0x70) != dispatcher:
            raise RuntimeError('Native receiver identity changed')
        ring = qword(receiver + 0x118)
        metadata = {'head_ticket': qword(ring), 'tail_ticket': qword(ring + 0x80),
                    'cancelled_tickets': qword(ring + 0x110)}
        metadata['receiver_empty_test'] = (
            metadata['tail_ticket'] == metadata['head_ticket'] + metadata['cancelled_tickets'])
        report = {'session_id': identity['session_id'], 'pid': args.pid,
            'dll_sha256': installation['dll_sha256'], 'read_only': True,
            'native_methods_invoked': False, 'business_submission': False,
            'date_raw': int.from_bytes(read(game + 0x1dd0, 4), 'little', signed=True),
            'metadata': metadata,
            'receiver_pending_count': int.from_bytes(read(receiver + 0xd8, 4), 'little'),
            'private_addresses': {'dispatcher': hex(dispatcher), 'receiver': hex(receiver), 'ring': hex(ring)},
            'scope': 'Only statically proven receiver/ring fields. No slot traversal, heap scan, writes or native calls.'}
        with args.output.open('x', encoding='utf-8') as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=False))
        return
'''
assert source.count("        slots = []") == 1
source = source.replace("        slots = []", body + "\n        slots = []")
exec(compile(source, str(source_path), "exec"),
     {"__name__": "__main__", "__file__": str(source_path)})
