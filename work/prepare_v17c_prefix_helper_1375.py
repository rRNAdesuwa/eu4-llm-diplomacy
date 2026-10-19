"""Prepare an identity-only prefix helper for the explicit fresh process."""
import ast,difflib,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PID,CREATION=55580,'01dd56c88c83e81a'
SOURCE=ROOT/'work/snapshot_v17_directional_preflight_prefix_1375.py'
TARGET=ROOT/'work/snapshot_v17c_directional_preflight_prefix_1375.py'


def main():
 raw=SOURCE.read_bytes()
 assert len(raw)<128*1024 and hashlib.sha256(raw).hexdigest()=='02eafbe31a9f067c3a214db11d4d7de073e6714814660bd33d27db8ba0d89428'
 baseline=json.loads((ROOT/f'work/runtime/native1375-v17/baseline-before-injection-{PID}.json').read_bytes())
 assert baseline['read_only'] is True and baseline['source']['pid']==PID and baseline['source']['process_creation_filetime']==int(CREATION,16)
 first,second=baseline['identity_before_and_after']
 assert first==second and first['raw_date']==56456976 and first['acceptance_flag']==0
 world=first['world_cookie'];assert world=='0x27c9a889070'
 code=raw.decode();tree=ast.parse(code)
 nodes=[n for n in tree.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Tuple) and [x.id for x in n.targets[0].elts]==['PID','CREATION','WORLD']]
 assert len(nodes)==1 and nodes[0].lineno==nodes[0].end_lineno
 lines=code.splitlines(True);original=lines[nodes[0].lineno-1]
 replacement=f'PID, CREATION, WORLD = {PID}, {CREATION!r}, {world!r}\n'
 lines[nodes[0].lineno-1]=replacement;new=''.join(lines)
 assert new.replace(replacement,original,1)==code
 compile(new,str(TARGET),'exec')
 with TARGET.open('xb') as dst:dst.write(new.encode())
 diff=''.join(difflib.unified_diff(code.splitlines(True),new.splitlines(True),fromfile='original-helper',tofile='new-explicit-helper'))
 with (ROOT/f'work/runtime/native1375-v17/prefix-helper-adaptation-{PID}.diff').open('x',encoding='utf-8',newline='\n') as dst:dst.write(diff)
 print(json.dumps({'path':str(TARGET),'sha256':hashlib.sha256(new.encode()).hexdigest(),'delta':diff,'identity_only':True}))


if __name__=='__main__':main()
