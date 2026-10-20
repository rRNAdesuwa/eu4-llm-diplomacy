"""Read only the verified FRA/target war association arrays in the current process.

The target is supplied by ``EU4_WAR_PAIR_RECIPIENT`` so reviewed runners can
bind the bounded pair probe to a small recipient such as LEI.  ENG remains the
default for existing artifacts.
"""
from pathlib import Path

source_path = Path(__file__).with_name('probe_native_state.py')
source = source_path.read_text(encoding='utf-8')
marker = '        slots = []'
assert source.count(marker) == 1
body = '''
        import os
        target_tag = os.environ.get('EU4_WAR_PAIR_RECIPIENT', 'ENG').upper()
        if len(target_tag) != 3 or not target_tag.isascii() or not target_tag.isalnum() or target_tag == 'FRA':
            raise RuntimeError('Invalid war pair recipient tag')
        tag_slots = {}
        for index in range(256):
            try:
                country = qword(array + index * 8)
                if not country:
                    continue
                identity = qword(country + 0x20)
                if ((identity >> 32) & 0xffff) != index:
                    continue
                tag_bytes = (identity & 0xffffff).to_bytes(3, 'little')
                if not all(0x20 <= byte <= 0x7e for byte in tag_bytes):
                    continue
                tag = tag_bytes.decode('ascii')
                if tag in ('FRA', target_tag):
                    tag_slots[tag] = index
            except OSError:
                continue
        if set(('FRA', target_tag)) - set(tag_slots):
            raise RuntimeError('Requested war pair tags were not found')
        report = {'pid': args.pid, 'read_only': True, 'player_slot': player_slot,
                  'current_raw_date': int.from_bytes(read(game+0x1dd0,4),'little',signed=True),
                  'actor': 'FRA', 'recipient': target_tag,
                  'countries': []}
        for tag, other_tag in (('FRA', target_tag), (target_tag, 'FRA')):
            slot = tag_slots[tag]
            other = tag_slots[other_tag]
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
            report['countries'].append({'tag': tag, 'slot': slot, 'handle': hex(identity),
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
