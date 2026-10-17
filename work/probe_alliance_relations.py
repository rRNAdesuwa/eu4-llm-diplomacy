"""Read-only samples of the native alliance UI selector's relation inputs."""
from pathlib import Path

source_path = Path(__file__).with_name("probe_native_state.py")
source = source_path.read_text(encoding="utf-8")
body = r'''
        def integer(address, size=4, signed=True):
            return int.from_bytes(read(address, size), 'little', signed=signed)
        identities = {}
        for slot in range(256):
            country = qword(array + slot * 8)
            if not country:
                continue
            value = qword(country + 0x20)
            if (value >> 32) & 0xffff != slot:
                continue
            tag = (value & 0xffffff).to_bytes(3, 'little').decode('ascii')
            identities[tag] = (slot, country, value)
        actor_slot, actor_country, actor_handle = identities['FRA']
        relation_table = qword(actor_country + 0x1510)
        report = {'pid': args.pid, 'game_sha256': EXPECTED_HASH,
                  'read_only': True, 'native_methods_invoked': False,
                  'date_raw': integer(game + 0x1dd0), 'pairs': []}
        for tag in ('SAV', 'PRO', 'ENG', 'SCO', 'POR'):
            recipient_slot, recipient_country, recipient_handle = identities[tag]
            row = relation_table + recipient_slot * 72
            owner = qword(row)
            relation_handle = qword(row + 0x10)
            start = qword(owner + 0x80)
            count = integer(owner + 0x8c)
            if not 0 <= count <= 4096 or (count and not start):
                raise RuntimeError('Invalid bounded native alliance membership array')
            slots = [integer(start + index * 16) for index in range(count)]
            report['pairs'].append({
                'actor': 'FRA', 'recipient': tag,
                'actor_handle': hex(actor_handle), 'recipient_handle': hex(recipient_handle),
                'row_owner_matches_actor_country': owner == actor_country,
                'row_recipient_handle': hex(relation_handle),
                'row_recipient_matches_full_handle': relation_handle == recipient_handle,
                'membership_slots': slots, 'membership_count': count,
                'recipient_slot_present': recipient_slot in slots,
                'native_selector_return': 'not_called', 'complete': True})
        with args.output.open('x', encoding='utf-8') as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
'''
assert source.count("        slots = []") == 1
source = source.replace("        slots = []", body + "\n        slots = []")
exec(compile(source, str(source_path), "exec"),
     {"__name__": "__main__", "__file__": str(source_path)})
