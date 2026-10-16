"""New port candidate: distinguish transport object data from vtable slots."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'work/candidates/v24-pair-send-port-1375'
HERE=ROOT/'work/candidates/v24-pair-send-port-r2-1375'
def desc(p):
 b=p.read_bytes();assert len(b)<4*1024*1024
 return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
ix=json.loads((OLD/'source-index.json').read_bytes());assert all(desc(OLD/n)==v for n,v in ix.items())
HERE.mkdir(exist_ok=False);pins=json.loads((OLD/'input-pins.json').read_bytes())
pins.update({(OLD/n).relative_to(ROOT).as_posix():v for n,v in ix.items()})
for name in ix:
 if name=='input-pins.json':continue
 data=(OLD/name).read_bytes();(HERE/'preimages').mkdir(exist_ok=True)
 with (HERE/'preimages'/name).open('xb') as f:f.write(data)
 text=data.decode('ascii')
 if name=='submission_guard.cpp':
  before='at(c.transport,0x30,vt)';assert text.count(before)==1
  text=text.replace(before,'at(env_.base+0x1d96178,0x30,vt)')
 elif name=='test_transfer.cpp':
  before='m.set(TRANSPORT,BASE+0x1d96178);m.set(TRANSPORT+0x30,BASE+0x1580370);'
  assert text.count(before)==1
  text=text.replace(before,'m.set(TRANSPORT,BASE+0x1d96178);m.set(TRANSPORT+0x30,Address{0});m.set(BASE+0x1d961a8,BASE+0x1580370);')
  at='    group("binder_rejects_context_world_callback_change"'
  pos=text.index(at)
  text=text[:pos]+'''    group("transport_vtable_slot_is_not_instance_data",[]{
        for(unsigned v=0;v<4;++v){SendFake f;NativePairEngineDraft e(f);auto env=prepared(f,e,profiles()[1]);BinderMemory m;
            for(const auto& pair:f.memory)for(std::size_t i=0;i<pair.second.bytes.size();++i)m.data[pair.first+i]=pair.second.bytes[i];context_fixture(m,env);
            if(v==0)m.set(TRANSPORT+0x30,Address{0});
            else if(v==1)m.set(TRANSPORT+0x30,Address{0x12345678});
            else if(v==2){m.set(BASE+0x1d961a8,BASE+0x1580371);m.set(TRANSPORT+0x30,BASE+0x1580370);}
            else {for(unsigned i=0;i<8;++i)m.data.erase(BASE+0x1d961a8+i);m.set(TRANSPORT+0x30,BASE+0x1580370);}
            SubmissionGuard guard({BASE,100,&m,BinderMemory::world,BinderMemory::read,BinderMemory::clock});auto a=guard.authority();SubmissionContext c{};
            CHECK(a.prepare(a.user,c)==(v<2));if(v<2)CHECK(a.final(a.user,c,env));
        }
    });
'''+text[pos:]
 elif name=='validate.py':
  assert "'transfer_groups=7 '" in text;text=text.replace("'transfer_groups=7 '","'transfer_groups=8 '")
 elif name=='README.md':
  text+='\nR2 fixes the transport vtable +0x30 slot address. The instance +0x30 is data; the synthetic fixture now deliberately sets it to zero/arbitrary data, and rejects a bad/missing vtable slot even when instance data resembles the function.\n'
 with (HERE/name).open('xb') as f:f.write(text.encode('ascii'))
with (HERE/'input-pins.json').open('x') as f:json.dump(pins,f,indent=2,sort_keys=True)
index={p.name:desc(p) for p in HERE.iterdir() if p.is_file()}
with (HERE/'source-index.json').open('x') as f:json.dump(index,f,indent=2,sort_keys=True)
print(json.dumps(dict(candidate=str(HERE),source_index=desc(HERE/'source-index.json'))))
