"""Read the fixed country-database header; never enumerate guessed slots."""
from pathlib import Path

source_path = Path(__file__).with_name("probe_native_state.py")
source = source_path.read_text(encoding="utf-8")
marker = "        slots = []"
body = '''
        if args.peace_ui or args.peace_heap or args.peace_address:
            raise RuntimeError('Only the fixed database header is supported')
        blob = read(database + 0x100, 0x50)
        array_table = int.from_bytes(blob[0x10:0x18], 'little')
        if not base <= array_table < base + 0x4000000:
            raise RuntimeError('Country array header has no module vtable')
        result = {
            'pid': args.pid, 'read_only': True,
            'module_base': hex(base),
            'date_raw': int.from_bytes(read(game + 0x1dd0, 4), 'little', signed=True),
            'database_word0_raw': hex(qword(database)),
            'country_array_vtable_rva': hex(array_table-base),
            'array_methods_rva': [hex(qword(array_table+i*8)-base) for i in range(5)],
            'header_offset': '0x100', 'header_bytes': len(blob),
            'header_hex': blob.hex(),
            'header_u32': {hex(0x100+i):int.from_bytes(blob[i:i+4],'little')
                           for i in range(0,len(blob),4)},
            'known_array_pointer': hex(array),
            'scope': 'Fixed database header only; no slot count assumption or array walk.'}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\\n',encoding='utf-8')
        print(json.dumps(result))
        return
'''
assert source.count(marker) == 1
exec(compile(source.replace(marker, body + "\n" + marker), str(source_path), "exec"),
     {"__name__": "__main__", "__file__": str(source_path)})
