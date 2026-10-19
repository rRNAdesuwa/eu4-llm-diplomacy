"""Deterministic CreateNew pure-reader frame repair from the sealed R1 sources.
No native build, process access, publication, or actual-session parsing.
"""
from pathlib import Path
import difflib,hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OLD=ROOT/'work/candidates/v19-spy-real-journal-1375'
def digest(raw):return hashlib.sha256(raw).hexdigest()
def source(name):
    path=OLD/name
    with path.open('rb') as f:raw=f.read(2*1024*1024+1)
    assert len(raw)<=2*1024*1024 and digest(raw)==old_index[path.relative_to(ROOT).as_posix()]
    return raw
def once(text,old,new):assert text.count(old)==1;return text.replace(old,new)
old_review=(OLD/'review.json').read_bytes();assert digest(old_review)=='cd61b0a27240314e2a814f986203b46e95637a69ec90d7e1bd514ed77fb2bd7f'
old_index=json.loads((OLD/'source-index.json').read_bytes())['files']
names=('fixed.py','files.py','wire.py','fixture.py','interval.py','reader.py','dependencies.json','test_files.py','test_intervals.py','test_reader.py','test_semantics.py',
       'preflight/native_trace.py','preflight/native_projection.py','preflight/protocol.py','preflight/model.py')
inputs={};diff=[]
for name in names:
    raw=source(name);inputs[(OLD/name).relative_to(ROOT).as_posix()]=digest(raw);new=raw
    if name=='interval.py':
        text=raw.decode();newline='\r\n' if '\r\n' in text else '\n';text=text.replace('\r\n','\n')
        text=once(text,'def __init__(self, identity, image, thread, observed, third_health, claim):','def __init__(self, identity, image, thread, observed, third_health, claim, previous_global_frame=None):')
        text=once(text,'        self.next_id=0;self.frame=third_health;self.now=0;self.pending=None;self.next=None',
            '        # The immutable stage-3 proof is not necessarily the immediately\n'
            '        # preceding callback: idle preflight health can continue afterward.\n'
            '        # The complete reader supplies the already paired outer before-frame.\n'
            '        integer(third_health,1)\n'
            '        self.origin_frame=third_health if previous_global_frame is None else previous_global_frame\n'
            '        integer(self.origin_frame,third_health)\n'
            '        self.local_frame=0\n'
            '        self.next_id=0;self.frame=self.origin_frame;self.now=0;self.pending=None;self.next=None')
        text=once(text,'        integer(frame,self.frame+1,self.frame+1);integer(begin_time,self.now)\n        self.frame=frame;',
            '        integer(frame,self.frame+1,self.frame+1);integer(begin_time,self.now)\n'
            '        integer(frame,self.origin_frame+self.local_frame+1,self.origin_frame+self.local_frame+1)\n'
            '        self.local_frame+=1\n        self.frame=frame;')
        text=once(text,'owner_frame=self.frame,intent_uptime=self.intent_time','owner_frame=self.frame,send_local_frame=self.local_frame,intent_uptime=self.intent_time')
        new=text.replace('\n',newline).encode()
    if name=='reader.py':
        text=raw.decode();newline='\r\n' if '\r\n' in text else '\n';text=text.replace('\r\n','\n')
        text=once(text,"                    require(seq==4 and '4' in requests,'First send request/claim');send=Interval(identity,image,owner,pre[0]['observed'],third,requests['4'])",
            "                    require(seq==4 and '4' in requests,'First send request/claim')\n"
            "                    # Both values came from the complete monotonic outer/raw\n"
            "                    # pairing above. Retain global raw/Core frames unchanged;\n"
            "                    # local send frame 1 starts only after this exact boundary.\n"
            "                    same(begin['controller_frame_before'],frame-1)\n"
            "                    send=Interval(identity,image,owner,pre[0]['observed'],third,requests['4'],\n"
            "                                  previous_global_frame=begin['controller_frame_before'])")
        text=once(text,'                intervals=send.intervals if send else [],completed_outcomes=send.outcomes if send else [0]*5,',
            '                send_frame_mapping=(dict(third_stage_health_frame=send.third,preceding_global_frame=send.origin_frame,\n'
            '                    first_global_frame=send.origin_frame+1,last_global_frame=send.frame,last_send_local_frame=send.local_frame,\n'
            "                    source='complete_outer_raw_core_pairing',raw_frames_rewritten=False,timestamps_rewritten=False) if send else None),\n"
            '                intervals=send.intervals if send else [],completed_outcomes=send.outcomes if send else [0]*5,')
        new=text.replace('\n',newline).encode()
    target=HERE/name;target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as f:f.write(new)
    if new!=raw:diff.extend(difflib.unified_diff(raw.decode().splitlines(True),new.decode().splitlines(True),fromfile='R1/'+name,tofile='R2/'+name))
with (HERE/'repair.diff').open('x',encoding='utf8',newline='') as f:f.writelines(diff)
with (HERE/'preimages.json').open('x',encoding='utf8') as f:json.dump(inputs,f,indent=2);f.write('\n')
print(json.dumps(dict(copied=len(names),changed=['interval.py','reader.py'],new_native_decoded_bytes=0)))
