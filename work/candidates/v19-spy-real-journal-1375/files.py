"""Bounded passive files only. No build/loader attestation is manufactured."""
from pathlib import Path
import stat
from fixed import wire,require
from reader import coherent,sha

def read(path,limit):
    path=Path(path).absolute()
    for node in (path,*path.parents):
        st=node.stat();require(not node.is_symlink() and not getattr(st,'st_file_attributes',0)&0x400,'No links/reparse points')
    before=path.stat();require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=limit,'Bounded ordinary single-link file')
    with path.open('rb') as f:
        raw=f.read(limit+1)
    require(len(raw)<=limit,'Read budget');return raw

def inspect_files(session,identity,complete=False):
    """Callers must additionally verify frozen build/loader provenance before
    treating next_sequence as a publisher gate. This function cannot publish."""
    identity=wire.identity(identity);session=Path(session).absolute()
    require(session.name==wire.session_path('.',identity).name,'Exact session directory name')
    claims={}
    for name in ('1','2','3','4',*('4.item-'+str(i) for i in range(1,6))):
        path=session/(name+'.claim')
        if path.exists():
            claims[name]=read(path,1024)
            if '.item-' not in name:require(read(session/(name+'.request'),1024)==claims[name],'Exact permanent request/claim bytes')
    raw_path=session/'raw-events.jsonl';outer_path=session/'bootstrap-events.jsonl'
    result=coherent(lambda:(read(raw_path,1048576),read(outer_path,2097152)),identity,claims,complete)
    # A concurrent newly materialized claim cannot be silently omitted.
    for name in ('1','2','3','4',*('4.item-'+str(i) for i in range(1,6))):
        path=session/(name+'.claim');require(path.exists()==(name in claims),'Claim inventory changed during read')
        if name in claims:require(read(path,1024)==claims[name],'Permanent claim changed during read')
    result['claim_sha256']={k:sha(v) for k,v in claims.items()}
    return result
