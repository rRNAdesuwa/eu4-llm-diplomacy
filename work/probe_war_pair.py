"""Read only the verified FRA/ENG war association arrays in the current process."""
from pathlib import Path

source_path = Path(__file__).with_name('probe_native_state.py')
source = source_path.read_text(encoding='utf-8')
marker = '        slots = []'
assert source.count(marker) == 1
body = '''
        report = {'pid': args.pid, 'read_only': True, 'player_slot': player_slot,
                  'current_raw_date': int.from_bytes(read(game+0x1dd0,4),'little',signed=True),
                  'countries': []}
        for slot, other in ((122,46),(46,122)):
            country = qword(array+slot*8)
            identity = qword(country+0x20)
            if (identity>>32)&0xffff != slot:
                raise RuntimeError('Country identity mismatch')
            count = int.from_bytes(read(country+0x1554,4),'little',signed=True)
            entries = qword(country+0x1548)
            if not 0 <= count <= 256 or (count and not entries):
                raise RuntimeError('Invalid bounded war association array')
            pairs = [{'slot': int.from_bytes(read(entries+i*16,4),'little',signed=True),
                      'war': hex(qword(entries+i*16+8))} for i in range(count)]
            report['countries'].append({'slot': slot, 'handle': hex(identity),
                 'pairs': pairs, 'pair_at_war': any(p['slot']==other for p in pairs)})
        report['both_pair_at_peace'] = all(not c['pair_at_war'] for c in report['countries'])
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
        return
'''
source = source.replace(marker, body + '\n' + marker)
exec(compile(source, str(source_path), 'exec'),
     {'__name__': '__main__', '__file__': str(source_path)})
