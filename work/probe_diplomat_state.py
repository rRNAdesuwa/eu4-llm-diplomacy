"""Bounded read-only FRA/ENG/POR diplomat and native queue probe.

This is a structural snapshot only.  It opens the verified process with
QUERY_INFORMATION|VM_READ through the shared probe implementation and never
calls an engine method or writes memory.  The country+0x1480 -> +0x18
container and entry +0x44/+0x18/+0x10 fields are retained as raw evidence;
their gameplay meanings are intentionally not guessed here.
"""
from pathlib import Path


source_path = Path(__file__).with_name("probe_native_state.py")
source = source_path.read_text(encoding="utf-8")
marker = "        slots = []"
assert source.count(marker) == 1
body = r'''
        def integer(address, size=4, signed=True):
            return int.from_bytes(read(address, size), 'little', signed=signed)

        def country_identity(value):
            slot = (value >> 32) & 0xffff
            if slot >= 4096:
                raise RuntimeError('Country handle slot out of bounds')
            country = qword(array + slot * 8)
            if qword(country + 0x20) != value:
                raise RuntimeError('Country handle identity mismatch')
            return (value & 0xffffff).to_bytes(3, 'little').decode('ascii')

        def describe_action(action):
            vtable = qword(action)
            result = {'pointer': hex(action), 'vtable_rva': hex(vtable - base),
                      'is_peace_action': vtable == base + 0x1c7b840}
            if not result['is_peace_action']:
                return result
            result.update(raw_actor_10=hex(qword(action + 0x10)),
                          raw_recipient_20=hex(qword(action + 0x20)),
                          raw_28=integer(action + 0x28),
                          state=integer(action + 0x34),
                          raw_30=integer(action + 0x30),
                          preview_flag=integer(action + 0x208, 1, False))
            return result

        report = {'pid': args.pid, 'read_only': True, 'player_slot': player_slot,
                  'current_raw_date': integer(game + 0x1dd0), 'countries': [],
                  'native_methods_invoked': False}
        requested_slots = []
        for slot in (122, 46, player_slot):
            if slot not in requested_slots:
                requested_slots.append(slot)
        for slot in requested_slots:
            country = qword(array + slot * 8)
            identity = qword(country + 0x20)
            if (identity >> 32) & 0xffff != slot:
                raise RuntimeError('Country slot identity mismatch')
            tag = country_identity(identity)
            item = {'slot': slot, 'tag': tag, 'handle': hex(identity),
                    'last_sent_raw': integer(country + 0x24a0),
                    'ai_queue_count_raw': integer(country + 0x18e8),
                    'ai_queue': [], 'diplomacy_entries': []}

            node = qword(country + 0x18d8)
            seen = set()
            while node and node not in seen and len(seen) < 128:
                seen.add(node)
                try:
                    action = qword(node)
                    item['ai_queue'].append(describe_action(action))
                    node = qword(node + 0x10)
                except (OSError, RuntimeError) as error:
                    item['ai_queue'].append({'node': hex(node), 'read_error': str(error)})
                    break
            item['ai_queue_truncated'] = bool(node)

            holder = qword(country + 0x1480)
            container = qword(holder + 0x18)
            begin = qword(container + 0x20)
            end = qword(container + 0x28)
            item['diplomacy_control_raw_14'] = integer(container + 0x14, 1, False)
            if begin <= end and (end - begin) % 8 == 0 and end - begin <= 2048:
                for offset in range(0, end - begin, 8):
                    entry = qword(begin + offset)
                    details = {'pointer': hex(entry), 'raw_id_44': integer(entry + 0x44),
                               'active_raw_18': integer(entry + 0x18, 1, False),
                               'record': hex(qword(entry + 0x10))}
                    record = qword(entry + 0x10)
                    if record:
                        details.update(record_vtable_rva=hex(qword(record) - base),
                                       raw_actor_80=hex(qword(record + 0x80)),
                                       raw_recipient_88=hex(qword(record + 0x88)),
                                       raw_action_type_a8=integer(record + 0xa8),
                                       raw_20=integer(record + 0x20),
                                       raw_24=integer(record + 0x24),
                                       raw_2c=integer(record + 0x2c))
                    item['diplomacy_entries'].append(details)
            else:
                item['diplomacy_vector_invalid_or_exceeds_256'] = True
            if item.get('diplomacy_vector_invalid_or_exceeds_256'):
                item['available_diplomat_count'] = None
            else:
                item['available_diplomat_count'] = sum(
                    entry.get('active_raw_18') == 0
                    for entry in item['diplomacy_entries'])
            report['countries'].append(item)

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'output': str(args.output), 'read_only': True,
                          'countries': [item['tag'] for item in report['countries']]},
                         ensure_ascii=False))
        return
'''
source = source.replace(marker, body + "\n" + marker)
exec(compile(source, str(source_path), "exec"),
     {"__name__": "__main__", "__file__": str(source_path)})
