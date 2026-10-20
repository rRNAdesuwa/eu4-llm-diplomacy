"""Read the bounded war fields used by the existing Grant candidate builder."""
from pathlib import Path

source_path = Path(__file__).with_name("probe_native_state.py")
source = source_path.read_text(encoding="utf-8")
marker = "        slots = []"
body = '''
        fra = qword(array + 122 * 8)
        eng = qword(array + 46 * 8)
        fra_id = qword(fra + 0x20)
        eng_id = qword(eng + 0x20)
        if (fra_id & 0xffffff) != int.from_bytes(b'FRA','little') or (eng_id & 0xffffff) != int.from_bytes(b'ENG','little'):
            raise RuntimeError('Country identities differ')
        entries = qword(fra + 0x1548)
        count = int.from_bytes(read(fra + 0x1554,4),'little',signed=True)
        if not 0 <= count <= 256:
            raise RuntimeError('War association count invalid')
        wars = [qword(entries + i*16 + 8) for i in range(count)
                if int.from_bytes(read(entries + i*16,4),'little',signed=True) == 46]
        if len(wars) != 1:
            raise RuntimeError('Unique current pair war required')
        war = wars[0]
        vtable = qword(war)
        result = {'pid':args.pid,'read_only':True,'war':hex(war),
                  'date_raw':int.from_bytes(read(game+0x1dd0,4),'little',signed=True),
                  'vtable_rva':hex(vtable-base),
                  'vtable_methods':[hex(qword(vtable+i*8)-base) for i in range(8)],
                  'fields':{hex(o):hex(qword(war+o)) for o in (0x18,0x150,0x158)}}
        token_table = qword(base + 0x242b868)
        token_count = int.from_bytes(read(base+0x2357b08,4),'little')
        tokens = {}
        for token_id in (0x352a,0x2d3e,0x2d3f):
            if not token_id < token_count:
                raise RuntimeError('Requested token is outside current native table')
            row = token_table + token_id*32
            length = qword(row+16)
            capacity = qword(row+24)
            if not 0 < length <= 128 or capacity < length:
                raise RuntimeError('Token string bounds invalid')
            data = qword(row) if capacity > 15 else row
            tokens[hex(token_id)] = read(data,length).decode('ascii')
        result['tokens'] = tokens
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\\n',encoding='utf-8')
        print(json.dumps(result))
        return
'''
assert source.count(marker) == 1
exec(compile(source.replace(marker, body + "\n" + marker), str(source_path), "exec"),
     {"__name__": "__main__", "__file__": str(source_path)})
