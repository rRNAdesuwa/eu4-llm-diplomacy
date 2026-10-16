"""Create isolated v19 bootstrap drafts from preserved v18 bytes; never compile or load."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parent.parent
OLD=ROOT/'work/candidates/v18-spy-bootstrap-lab-1375'
NEW=ROOT/'work/candidates/v19-spy-bootstrap-lab-1375'
FILES=('bootstrap.cpp','bootstrap_codec.h','scheduler.h','installer.h','installer.cpp',
       'thread_freeze.inc','frame.asm','test_bootstrap.cpp','loader.py','build_manifest.py')

def main():
    NEW.mkdir(exist_ok=False)
    pins={}
    for name in FILES:
        raw=(OLD/name).read_bytes()
        assert len(raw)<=128*1024
        pins[(OLD/name).relative_to(ROOT).as_posix()]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        if name in ('thread_freeze.inc','frame.asm'):
            output=raw
        else:
            text=raw.decode('utf-8').replace('eu4_spy_boot18','eu4_spy_boot19')
            if name in ('bootstrap_codec.h','bootstrap.cpp'):
                text=text.replace('../v18-spy-restricted-host-1375/','../v19-spy-restricted-host-1375/')
            text=text.replace('eu4_spy_no_send_lab_1375_v18.dll','eu4_spy_send_lab_1375_v19.dll')
            text=text.replace('restricted_spy_no_send_lab_1375_v18','restricted_spy_lab_1375_v19')
            output=text.encode('utf-8')
        (NEW/name).write_bytes(output)
    (NEW/'v18-preimages.json').write_text(json.dumps(pins,sort_keys=True,indent=2)+'\n',encoding='ascii')
    print(json.dumps({'schema':'EU4SPY19DRAFT/1','copied':len(FILES),'compiled':False,'loaded':False}))

if __name__=='__main__':main()
