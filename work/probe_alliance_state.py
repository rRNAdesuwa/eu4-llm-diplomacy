"""Bounded read-only alliance object identification in native AI queues.

Reuses the verified process/hash checks. No engine calls or memory writes;
response state and decision-country semantics remain unknown.
"""
from pathlib import Path

source_path = Path(__file__).with_name("probe_native_state.py")
source = source_path.read_text(encoding="utf-8")
body = r'''
        def integer(address, size=4, signed=True):
            return int.from_bytes(read(address,size),'little',signed=signed)
        def country_identity(value):
            slot=(value>>32)&0xffff
            if slot>=4096:
                raise RuntimeError('Handle slot out of bounds')
            country=qword(array+slot*8)
            if qword(country+0x20)!=value:
                raise RuntimeError('Full country handle mismatch')
            return (value&0xffffff).to_bytes(3,'little').decode('ascii')
        report={'pid':args.pid,'game_sha256':EXPECTED_HASH,'read_only':True,
                'date_raw':integer(game+0x1dd0),'player':country_identity(qword(game+0x1e60)),
                'native_methods_invoked':False,'countries':[]}
        for slot in (122,46,189):
            country=qword(array+slot*8)
            item={'country':country_identity(qword(country+0x20)), 'actions':[]}
            node=qword(country+0x18d8); seen=set()
            while node and node not in seen and len(seen)<128:
                seen.add(node)
                try:
                    action=qword(node); vtable=qword(action)
                    obj={'object':hex(action),'vtable_rva':hex(vtable-base),
                         'identification':'unknown','decision_country':None,'complete':False}
                    if vtable==base+0x1c80720:
                        discriminator=integer(action+8)
                        variant=integer(action+0x38,1,False)
                        actor=country_identity(qword(action+0x10))
                        recipient=country_identity(qword(action+0x20))
                        obj.update(discriminator=hex(discriminator),variant_raw=variant,
                                   actor_field=actor,recipient_field=recipient,
                                   state_raw=integer(action+0x34),date_field_28=integer(action+0x28),
                                   date_field_2c=integer(action+0x2c))
                        if discriminator==0x165 and variant in (0,1):
                            obj['identification']='static_vtable_layout_matched_live'
                            obj['action_id']='offer_alliance' if variant else 'dissolve_alliance'
                            obj['native_action_id']='0x293d'
                    item['actions'].append(obj)
                    node=qword(node+0x10)
                except (OSError,RuntimeError,UnicodeDecodeError) as error:
                    item['actions'].append({'read_error':str(error),'complete':False}); break
            item['queue_truncated']=bool(node)
            report['countries'].append(item)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2)); return
'''
assert source.count("        slots = []") == 1
source = source.replace("        slots = []", body + "\n        slots = []")
exec(compile(source, str(source_path), "exec"),
     {"__name__": "__main__", "__file__": str(source_path)})
