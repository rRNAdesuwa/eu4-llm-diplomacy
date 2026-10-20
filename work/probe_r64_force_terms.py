"""Read only the four countries' direct terms used by native ee5430.

The bounded probe follows the documented army/regiment links. It never scans
private heaps, calls game functions, or writes game memory.
"""
from pathlib import Path

source_path = Path(__file__).with_name("probe_native_state.py")
source = source_path.read_text(encoding="utf-8")
marker = "        slots = []"
assert source.count(marker) == 1
body = '''
        def integer(address, size=4, signed=True):
            return int.from_bytes(read(address,size),'little',signed=signed)
        wanted={'FRA','BUR','SAV','HSA'}
        found={}
        country_count=integer(database+0x124,signed=False)
        if not 0<country_count<=4096: raise RuntimeError('Invalid country count')
        for slot in range(country_count):
            country=qword(array+slot*8)
            if not country: continue
            identity=qword(country+0x20)
            if ((identity>>32)&0xffff)!=slot: continue
            tag=(identity&0xffffff).to_bytes(3,'little').decode('ascii','replace')
            if tag in wanted: found[tag]=country
            if set(found)==wanted: break
        if set(found)!=wanted: raise RuntimeError('Requested countries not found')
        rows=[]
        for tag,country in sorted(found.items()):
            queued=[]; queued_raw=0
            for index,offset in enumerate((0xd48,0xd50,0xd58)):
                count=integer(country+0x10b8+index*2,2,False)
                unit=qword(country+offset)
                amount=integer(unit+0x54) if count else 0
                queued.append({'kind':index,'count':count,'unit_field54':amount})
                queued_raw+=count*amount
            base_raw=integer(country+0xdb8)
            strengths=[0,0,0]; counts=[0,0,0]; armies=[]
            node=qword(country+0xd18); seen=set()
            while node:
                if node in seen or len(seen)>=512: raise RuntimeError('Army list cycle or limit')
                seen.add(node)
                army=qword(node); begin=qword(army+0x30); end=qword(army+0x38)
                if end<begin or (end-begin)%8 or (end-begin)//8>512:
                    raise RuntimeError('Invalid regiment vector')
                army_strengths=[0,0,0]; army_counts=[0,0,0]
                for item in range(begin,end,8):
                    regiment=qword(item); unit=qword(regiment+0x20)
                    kind=integer(unit+0x10); strength=integer(regiment+0x28)
                    if 0<=kind<3:
                        strengths[kind]+=strength; counts[kind]+=1
                        army_strengths[kind]+=strength; army_counts[kind]+=1
                armies.append({'regiment_count_by_kind':army_counts,'strength_raw_by_kind':army_strengths})
                node=qword(node+0x10)
            rows.append({'country':tag,'country_pointer':hex(country),'regiment_count_by_kind':counts,
                'strength_raw_by_kind':strengths,'country_db8_raw':base_raw,'queued_terms':queued,
                'fourth_slot_direct_raw':base_raw+queued_raw,'all_four_direct_raw':sum(strengths)+base_raw+queued_raw,
                'armies':armies,'special_subject_recursion_applied':False})
        report={'pid':args.pid,'binary_sha256':EXPECTED_HASH,'read_only':True,
            'date_raw':integer(game+0x1dd0),'player_slot':player_slot,'countries':rows,
            'source':'native ee5430 direct country terms; recursive subject part excluded',
            'units_verified':False,'memory_scan':False}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\\n',encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
        return
'''
source = source.replace(marker, body + "\n" + marker)
exec(compile(source, str(source_path), "exec"),
     {"__name__": "__main__", "__file__": str(source_path)})
