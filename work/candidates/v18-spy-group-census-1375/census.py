"""Explicit five-family RO group. No calls, requests, DLLs, or game writes."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,re,struct,sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OBSERVER='work/candidates/spy-dense-full-observer-r2-1375/observer.py'
OBSERVER_SHA='f25dace36f14f3ea01928f90c3817e715140b373723a3aa9843a280e01b5bd66'
PIN_SHA='2f0117d3aa98dd44a23ebdf867d014b8088452a21ad3f19ebecc30657759b1d7'
DATE=56456976
FRA=0x0100007a00415246;ENG=0x0100002e00474e45
FAMILIES=('corrupt_officials','sabotage_reputation','sow_discontent','slander_merchants','sabotage_recruitment')
MAX_BYTES=16*1024*1024;MAX_CALLS=8192;MAX_OUTPUT=8*1024*1024

def require(ok,why):
    if not ok:raise ValueError(why)
def integer(x,lo=0,hi=2**64-1):return type(x)is int and lo<=x<=hi
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def no_links(path):
    path=Path(path).absolute()
    for x in (path,*path.parents):
        if x.exists():require(not x.is_symlink() and not(getattr(x.stat(),'st_file_attributes',0)&0x400),'Reparse path')
    return path
def read(path,limit):
    with no_links(path).open('rb') as stream:raw=stream.read(limit+1)
    require(len(raw)<=limit,'Source read budget');return raw
def sha(raw):return hashlib.sha256(raw).hexdigest()
def arguments(pid,creation,phase):
    require(integer(pid,1,2**32-1),'Exact PID')
    require(type(creation)is str and re.fullmatch('[0-9a-f]{16}',creation) and int(creation,16)>0,'Exact creation')
    require(type(phase)is str and phase in ('initial','final'),'Initial/final only')
def check():
    raw=read(HERE/'input-pins.json',131072);require(sha(raw)==PIN_SHA,'Fixed source index')
    pins=json.loads(raw);require(type(pins)is dict and 1<=len(pins)<=48,'Source count')
    total=0
    for name,pin in pins.items():
        path=(ROOT/name).resolve();require(path.is_relative_to(ROOT),'Escaped source')
        data=read(path,4*1024*1024);total+=len(data);require(total<=16*1024*1024,'Source aggregate bound')
        require(pin=={'bytes':len(data),'sha256':sha(data)},'Source changed: '+name)
    index=json.loads(read(HERE/'source-index.json',65536))
    require(index['input_pins_sha256']==PIN_SHA and len(index['sources'])<=8,'Helper index')
    for name,pin in index['sources'].items():
        path=(HERE/name).resolve();require(path.is_relative_to(HERE),'Escaped helper source')
        data=read(path,131072);require(pin=={'bytes':len(data),'sha256':sha(data)},'Helper changed: '+name)
    return {'checked':True,'inputs':len(pins),'observer_sha256':OBSERVER_SHA,'game_accessed':False}
def dependencies():
    path=ROOT/OBSERVER;raw=read(path,32768);require(sha(raw)==OBSERVER_SHA,'Observer source')
    spec=importlib.util.spec_from_file_location('_spy18_group_dense_r2',path)
    full=importlib.util.module_from_spec(spec);spec.loader.exec_module(full)
    spy,_=full.dependencies()
    require(set(spy.contract()['families'])==set(FAMILIES),'Exactly five fixed families')
    return full,spy

class GroupReader:
    def __init__(self,reader):self.reader=reader;self.base=reader.base;self.calls=0;self.bytes=0
    def read(self,address,size):
        require(integer(address,0x10000,0x7fffffffffff) and address%1==0 and integer(size,1,65536)
                and address+size<=0x800000000000,'Read range')
        require(self.calls<MAX_CALLS and self.bytes+size<=MAX_BYTES,'Group read budget')
        self.calls+=1;self.bytes+=size;data=self.reader.read(address,size)
        require(type(data)is bytes and len(data)==size,'Exact group read');return data
    def qword(self,address):return struct.unpack('<Q',self.read(address,8))[0]
    def integer(self,address):return struct.unpack('<i',self.read(address,4))[0]

def pause(reader):
    # The same selected predicate as frozen v17 paused_state, narrowed to
    # manual pause=1. No supervisor imports, termination or engine calls.
    def pointer(p):require(integer(p,0x10000,0x7fffffffffff) and p%8==0,'Aligned selected root');return p
    q=reader.qword;game=pointer(q(reader.base+0x233fe78));server=pointer(q(game+0x1e00))
    require(q(server)==reader.base+0x1cb8460,'Fixed server vtable')
    manager=pointer(q(server+0x418));require(q(manager+0x50)==server,'Pause manager back pointer')
    require(reader.read(server+0x19f1,1)==b'\0','Supported classifier branch only; not strict SP')
    manual=reader.read(manager+0x48,1)[0];begin,end=q(manager),q(manager+8)
    require(manual==1 and (begin==0)==(end==0) and end>=begin and (end-begin)%8==0 and end-begin<=2048,'Manual paused bounded state')
    player=q(game+0x1e60);date=reader.integer(game+0x1dd0);speed=reader.integer(game+0x1e08)
    require(player==FRA and date==DATE and 0<=speed<=4 and reader.read(game+0x7485,1)==b'\0' and q(game+0x74c8)==0,'Fixed world/date/player')
    require(q(reader.base+0x233fe78)==game and q(game+0x1e00)==server and q(server+0x418)==manager,'Pause roots changed')
    return dict(game=game,server=server,pause_manager=manager,player=player,raw_date=date,manual_pause=manual,
                begin=begin,end=end,native_speed_index=speed,paused_observed=True,strict_single_player_verified=False)

def _collect(reader,full,spy,pid,creation,phase):
    held=spy.held_identity(reader,pid,int(creation,16))
    require(type(held)is dict and set(held)=={'pid','creation_filetime','exit_filetime','module_base'} and
            integer(held['pid'],pid,pid) and type(held['creation_filetime'])is str and held['creation_filetime']==creation and
            integer(held['exit_filetime'],0,0) and integer(held['module_base'],reader.base,reader.base),'Exact held identity')
    budget=GroupReader(reader);reports={};pauses=[];identity=None
    for family in FAMILIES:
        before=pause(budget);report=full.capture(budget,reader.base,family=family);after=pause(budget)
        require(canonical(before)==canonical(after),'Pause changed during family')
        require(report['family']==family and report['profile']=='spy_dense_full_ro_1375_2' and report['full_envelope_equal'] is True,'Original full report shape')
        require(all(report[k] is False for k in ('native_calls','native_legality_verified','actual_cost_verified','individual_effect_verified','strict_single_player_verified','world_epoch_verified','paused_verified','production_ready')),'Original limits remain false')
        for part in ('before','after'):
            source=report[part];snapshot=source['snapshot'];spy.inspect(snapshot)
            require(source['two_pass_equal'] is True and canonical(source['selected'])==canonical(spy.selected(snapshot)),'Original typed selected report')
            current=snapshot['identity']
            require(integer(current['base'],reader.base,reader.base) and integer(current['game'],before['game'],before['game']) and
                    integer(current['date'],DATE,DATE) and integer(current['player'],FRA,FRA),'Group date/root binding')
            require(integer(current['countries']['FRA']['handle'],FRA,FRA) and integer(current['countries']['ENG']['handle'],ENG,ENG),'Group full country identities')
            if identity is None:identity=current
            require(canonical(identity)==canonical(current),'Group world/countries changed')
        require(canonical(report['before']['snapshot'])==canonical(report['after']['snapshot']),'Full before/after differ')
        require(canonical(spy.held_identity(reader,pid,int(creation,16)))==canonical(held),'Held identity changed')
        reports[family]=report;pauses.append({'family':family,'before':before,'after':after})
    require(all(canonical(x['before'])==canonical(pauses[0]['before']) for x in pauses),'Group pause roots changed')
    return dict(schema_version=1,profile='spy5_initial_final_readonly_census_1375',phase=phase,pid=pid,creation=creation,
        actor='FRA',target='ENG',raw_date=DATE,process_identity=held,selected_identity=identity,paused_observations=pauses,
        family_order=list(FAMILIES),family_reports=reports,group_atomic=False,selected_identity_consistent=True,
        read_budget={'bytes':budget.bytes,'calls':budget.calls,'max_bytes':MAX_BYTES,'max_calls':MAX_CALLS},
        observer_source={'path':OBSERVER,'sha256':OBSERVER_SHA},native_called=False,game_written=False,individual_effect_verified=False,
        request_causality_verified=False,whole_world_unchanged_verified=False,strict_single_player_verified=False,world_epoch_verified=False,
        cache_freshness_verified=False,object_lifetime_verified=False,actual_cost_verified=False,production_ready=False)

def sample(pid,creation,phase):
    arguments(pid,creation,phase);check();full,spy=dependencies()
    executable=(ROOT.parent/'eu4.exe').resolve()
    require(full.sha(executable)==spy.EXE_SHA,'Exact executable SHA')
    sys.path.insert(0,str(ROOT));from work import probe_diplomacy_current as legacy
    require(Path(legacy.__file__).resolve()==ROOT/'work/probe_diplomacy_current.py' and legacy.ROOT==ROOT,'Legacy reader origin')
    _,signature=legacy.verified_executable(executable);c=spy.contract()
    require(signature=={'timestamp':c['pe']['timestamp'],'size':c['pe']['image_size']},'Exact PE identity')
    reader=legacy.ProcessReader(pid,executable,signature)
    try:
        result=_collect(reader,full,spy,pid,creation,phase)
        legacy.verify_module_signature(legacy.pe_signature(reader,reader.base),signature)
        require(full.sha(executable)==spy.EXE_SHA and reader.bytes_read<=MAX_BYTES,'Final image and inclusive PE byte budget')
        require(canonical(spy.held_identity(reader,pid,int(creation,16)))==canonical(result['process_identity']),'Final held identity')
        check();result['process_read_bytes_including_pe_guards']=reader.bytes_read
        result['source_kind']='held_process_readonly_sequential_group';result['disk_exe_sha256']=spy.EXE_SHA
        return result
    finally:reader.close()

def write_new(path,value):
    raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('ascii');require(len(raw)<=MAX_OUTPUT,'Output budget')
    with no_links(path).open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return {'path':str(path),'bytes':len(raw),'sha256':sha(raw)}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pid',required=True,type=int);p.add_argument('--creation',required=True)
    p.add_argument('--phase',required=True,choices=('initial','final'));p.add_argument('--output',required=True,type=Path);a=p.parse_args(argv)
    arguments(a.pid,a.creation,a.phase);output=no_links(a.output);require(not output.exists(),'CREATE_NEW output already exists')
    value=sample(a.pid,a.creation,a.phase);print(json.dumps(write_new(output,value),sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
