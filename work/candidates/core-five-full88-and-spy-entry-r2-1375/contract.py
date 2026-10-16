"""Pure typed projections of static evidence; no raw reader or execution adapter."""
import copy,json,pathlib
HERE=pathlib.Path(__file__).resolve().parent
def document():
 with (HERE/'report.json').open('rb') as f:b=f.read(1024*1024+1)
 if len(b)>1024*1024:raise ValueError('report budget')
 return json.loads(b)
def profile(family,cancel):
 if type(family) is not str or type(cancel) is not bool:raise ValueError('exact family/bool required')
 data=document()['profiles']
 if family not in data:raise ValueError('unsupported family')
 p=copy.deepcopy(data[family]);p['selected_mode']=p['cancel' if cancel else 'positive']
 p['constructor_authorized']=False;p['native_ready']=False;p['runtime_verified']=False;p['production_ready']=False
 return p
def integer(value,lo,hi):return type(value) is int and lo<=value<=hi
def handle(value):
 return integer(value,0,0xffffffffffffffff) and value>>56!=0 and ((value>>32)&0xffff)<4096
def typed_manager(manager,actor):
 # This is an injected record validator, not a loaded-registry or memory attestation.
 if not isinstance(manager,dict) or not handle(actor):return False
 if type(manager.get('vtable_rva')) is not int or manager['vtable_rva']!=0x1cac380:return False
 for k,v in [('marker',0x165),('token',0x2746),('kind',3),('owner',actor)]:
  if type(manager.get(k)) is not int or manager[k]!=v:return False
 return True
def typed_spy_entry(entry,manager,actor):
 if not typed_manager(manager,actor) or not isinstance(entry,dict):return False
 # Unknown type must short-circuit before inspecting derived fields.
 if type(entry.get('vtable_rva')) is not int or entry['vtable_rva']!=0x1cac2f0:return False
 if type(entry.get('marker')) is not int or entry['marker']!=0x165:return False
 if type(entry.get('kind')) is not int or entry['kind']!=3:return False
 return integer(entry.get('status'),0,255) and entry['status']==2 and integer(entry.get('id'),0,0x7fffffff)
