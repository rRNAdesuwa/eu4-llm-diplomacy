"""Read province counts and development for named R35 scenario candidates."""
from pathlib import Path

source_path=Path(__file__).with_name("probe_native_state.py")
source=source_path.read_text(encoding="utf-8")
body=r'''
        wanted={'FRA','LEI','TYR','ULS','BRI','NAV','RAG','SCO','ATH'}
        candidates=[]
        for slot in range(256):
            country=qword(array+slot*8)
            actual=qword(country+0x20)
            if ((actual>>32)&0xffff)!=slot:
                continue
            tag=(actual&0xffffff).to_bytes(3,'little').decode('ascii','replace')
            if tag not in wanted:
                continue
            candidates.append({'tag':tag,'slot':slot,
                'owned_province_count':int.from_bytes(read(country+0x1344,4),'little',signed=True),
                'development_raw':int.from_bytes(read(country+0xe1c,4),'little',signed=True)})
        result={'pid':args.pid,'read_only':True,'date_raw':int.from_bytes(read(game+0x1dd0,4),'little',signed=True),
            'player_slot':player_slot,'candidates':candidates,
            'scope':'Fixed 256 known canonical slots; named candidates only; no calls/writes/heap scan.'}
        args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2)); return
'''
assert source.count("        slots = []")==1
source=source.replace("        slots = []",body+"\n        slots = []")
exec(compile(source,str(source_path),"exec"),
     {"__name__":"__main__","__file__":str(source_path)})
