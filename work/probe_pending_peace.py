"""Bounded read-only native diplomacy/AI queue inspection for the verified build.

Reuses probe_native_state.py's executable hash, process path, and VM_READ-only
handle checks. Does not invoke engine methods or change game memory.
"""
from pathlib import Path

source_path = Path(__file__).with_name('probe_native_state.py')
source = source_path.read_text(encoding='utf-8')
marker = '        slots = []'
assert source.count(marker) == 1
body = '''
        def integer(address, size=4, signed=True):
            return int.from_bytes(read(address,size),'little',signed=signed)
        def describe_action(action):
            vtable=qword(action)
            result={'pointer':hex(action),'vtable_rva':hex(vtable-base),
                    'is_peace_action':vtable==base+0x1c7b840}
            if not result['is_peace_action']:
                return result
            result.update(actor=hex(qword(action+0x10)),recipient=hex(qword(action+0x20)),
                          raw_28=integer(action+0x28),state=integer(action+0x34),
                          raw_30=integer(action+0x30),preview_flag=integer(action+0x208,1,False))
            counts=[]
            for off in (0x70,0x88,0xa0,0xb8):
                begin,end=qword(action+off),qword(action+off+8)
                counts.append((end-begin)//8 if begin<=end and (end-begin)%8==0 and end-begin<=32768 else None)
            result['participant_counts']=counts
            return result
        report={'pid':args.pid,'read_only':True,'current_raw_date':integer(game+0x1dd0),'countries':[]}
        fra=qword(array+122*8)
        relation=qword(fra+0x1510)+46*72
        threshold=integer(relation+0x30)
        bypass=integer(game+0x23a9,1,False)
        report['fra_eng_command_date_guard']={'threshold_raw':threshold,'bypass_raw':bypass,
             'passes':report['current_raw_date']>threshold or bool(bypass)}
        for slot in (122,46,player_slot):
            country=qword(array+slot*8)
            candidate=qword(country+0x20)
            if (candidate>>32)&0xffff != slot:
                raise RuntimeError('Country slot identity mismatch')
            tag=(candidate&0xffffff).to_bytes(3,'little').decode('ascii')
            item={'slot':slot,'tag':tag,'handle':hex(candidate),'last_sent_raw':integer(country+0x24a0),
                  'ai_queue_count_raw':integer(country+0x18e8),'ai_queue':[],'diplomacy_entries':[]}
            node=qword(country+0x18d8)
            seen=set()
            while node and node not in seen and len(seen)<128:
                seen.add(node)
                try:
                    action=qword(node)
                    item['ai_queue'].append(describe_action(action))
                    node=qword(node+0x10)
                except (OSError,RuntimeError) as exc:
                    item['ai_queue'].append({'node':hex(node),'read_error':str(exc)})
                    break
            item['ai_queue_truncated']=bool(node)
            holder=qword(country+0x1480)
            container=qword(holder+0x18)
            begin,end=qword(container+0x20),qword(container+0x28)
            item['diplomacy_control_raw_14']=integer(container+0x14,1,False)
            if begin<=end and (end-begin)%8==0 and end-begin<=2048:
                for offset in range(0,end-begin,8):
                    entry=qword(begin+offset)
                    record=qword(entry+0x10)
                    details={'pointer':hex(entry),'raw_id_44':integer(entry+0x44),
                             'active_raw_18':integer(entry+0x18,1,False),'record':hex(record)}
                    if record:
                        details.update(record_vtable_rva=hex(qword(record)-base),
                                       actor=hex(qword(record+0x80)),recipient=hex(qword(record+0x88)),
                                       raw_action_type_a8=integer(record+0xa8),raw_20=integer(record+0x20),
                                       raw_24=integer(record+0x24),raw_2c=integer(record+0x2c))
                    item['diplomacy_entries'].append(details)
            else:
                item['diplomacy_vector_invalid_or_exceeds_256']=True
            item['available_diplomat_count']=sum(e['active_raw_18']==0 for e in item['diplomacy_entries']) if not item.get('diplomacy_vector_invalid_or_exceeds_256') else None
            report['countries'].append(item)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return
'''
source = source.replace(marker, body + '\n' + marker)
exec(compile(source,str(source_path),'exec'),{'__name__':'__main__','__file__':str(source_path)})
