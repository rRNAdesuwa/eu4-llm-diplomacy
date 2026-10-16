"""Preserve R2 partial archive; allow its own empty stderr artifacts in new R3."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];b=(ROOT/'work/archive_pair22_stopped_r2_1375.py').read_bytes()
old=b"    data=m.bounded(path,4*1024*1024);total+=len(data);m.need(total<=40*1024*1024 and len(files)<512,'Archive budget')"
new=b'''    if path.stat().st_size==0:
        st=path.lstat();m.need(path.suffix=='.stderr' and path.is_relative_to(m.OUT) and path.resolve()==path and st.st_nlink==1 and not path.is_symlink() and not getattr(st,'st_file_attributes',0)&0x400,'Empty output artifact guard')
        data=path.read_bytes();m.need(data==b'','Changed empty output')
    else:data=m.bounded(path,4*1024*1024)
    total+=len(data);m.need(total<=40*1024*1024 and len(files)<512,'Archive budget')'''
assert b.count(old)==1;b=b.replace(old,new).replace(b'pair22-stopped-archive-r2-50684-20261012a',b'pair22-stopped-archive-r3-50684-20261012a')
with (ROOT/'work/archive_pair22_stopped_r3_1375.py').open('xb') as f:f.write(b)
