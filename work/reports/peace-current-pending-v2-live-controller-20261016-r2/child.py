"""Future single status child. Inert without a new exact root once grant."""
from pathlib import Path
import builtins, hashlib, io, json, os, re, stat, sys, traceback, types

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OPEN,IOOPEN=builtins.open,io.open
LIMIT=268435456
CONTROL=[]
CONTROL_RETURNED=0
METER=None

def require(ok,why):
    if not ok:raise ValueError(why)

def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

def decode(raw):
    def pairs(items):
        out={}
        for k,v in items:
            require(k not in out,'Duplicate JSON');out[k]=v
        return out
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:require(False,'Nonfinite JSON'))

def read(path,expected=None):
    global CONTROL_RETURNED
    path=Path(path);size=path.stat().st_size;require(0<=size<=4194304,'Child control ordinary size')
    requested=size+1
    e={'path':str(path),'requested':requested,'returned':0,'completed':False};CONTROL.append(e)
    spent=CONTROL_RETURNED+(0 if METER is None else METER.totals['ordinary'])
    require(spent+requested<=LIMIT,'Child control full-request reserve')
    try:
        with OPEN(path,'rb') as f:raw=f.read(requested)
        e['returned']=len(raw);e['completed']=True;CONTROL_RETURNED+=len(raw)
        if METER is not None:METER.limits['ordinary']=LIMIT-CONTROL_RETURNED
        require(len(raw)==size,'Control file changed size')
        if expected is not None:require(pin(raw)==expected,'Control exact source pin')
        return raw
    except BaseException as exc:e['error']=type(exc).__name__+': '+str(exc);raise

def save(name,value):
    with OPEN(HERE/name,'x',encoding='ascii',newline='\n') as f:json.dump(value,f,ensure_ascii=True,sort_keys=True,indent=2);f.write('\n')

def bootstrap(sha):
    require(re.fullmatch('[0-9a-f]{64}',sha),'Only future grant SHA')
    raw=read(HERE/'run-authorization.json');require(pin(raw)['sha256']==sha,'Grant buffer hash before parse');a=decode(raw)
    p=a['subject_source_manifest'];require(p['path']==(HERE/'source-manifest.json').relative_to(ROOT).as_posix(),'Fixed source manifest')
    mr=read(HERE/'source-manifest.json',{k:p[k] for k in ('bytes','sha256')});m=decode(mr)
    name=(HERE/'runtime_contract.py').relative_to(ROOT).as_posix();code=read(HERE/'runtime_contract.py',m['source_pins'][name])
    module=types.ModuleType('_peace_v2_once_contract_child');module.__file__=str(HERE/'runtime_contract.py')
    exec(compile(code,module.__file__,'exec'),module.__dict__)
    return module,module.verify(read,sha)

def game_meter_class(donor,contract):
    class GamePort(donor.ReadPort):
        def __init__(self,meter,stream,key,entry):
            super().__init__(meter,stream,key,'game_disk',contract.GAME_BYTES)
            self.record=entry;self.digest=hashlib.sha256();self.received=0;self.saw_eof=False;self.done=False
        def read(self,n=-1):
            # Preserve read(-1) reservation semantics; never split or shrink a request.
            data=super().read(n)
            self.digest.update(data);self.received+=len(data)
            if not data:self.saw_eof=True
            self.record.update(returned=self.received,sha256_so_far=self.digest.hexdigest(),eof=self.saw_eof)
            return data
        def readinto(self,buffer):
            data=self.read(len(buffer));buffer[:len(data)]=data;return len(data)
        def readline(self,n=-1):raise ValueError('Game disk is sequential binary read only')
        def seek(self,*args,**kwargs):raise ValueError('No game disk seek route')
        def close(self,normal=False):
            if self.done:return
            self.done=True
            try:
                self.s.close();self.record['closed']=self.s.closed
            finally:
                complete=self.saw_eof and self.received==contract.GAME_BYTES and self.digest.hexdigest()==contract.GAME_SHA
                self.record.update(full_expected_hash=complete,normal_context_exit=normal)
            if normal:require(complete,'Game disk expected full sequential hash')
        def __exit__(self,kind,value,tb):
            self.close(normal=kind is None);return False

    class GameMeter(donor.Meter):
        def __init__(self,paths,budgets):
            super().__init__(paths,LIMIT-CONTROL_RETURNED,budgets['fixed_host_returned'],budgets['fixed_host_attempts'])
            self.limits['game_disk']=budgets['game_disk_returned_with_one_chunk_reservation']
            self.totals['game_disk']=self.requested['game_disk']=self.attempts['game_disk']=0
            self.game_opens=[];self.game_successful_opens=0;self.game_open_limit=budgets['game_disk_max_read_opens']
            self.game_attempt_limit=budgets['game_disk_attempts'];self.game_request_limit=budgets['game_disk_single_request']
            self.game_key=os.path.normcase(os.path.abspath(os.fspath(contract.GAME)))
        def open(self,file,mode='r',*args,**kwargs):
            if isinstance(file,int):return super().open(file,mode,*args,**kwargs)
            path=Path(file);original=os.path.normcase(os.path.abspath(os.fspath(path)));resolved=os.path.normcase(str(path.resolve()))
            is_game=path.name.casefold()=='eu4.exe' or original==self.game_key or resolved==self.game_key
            if not is_game:return super().open(file,mode,*args,**kwargs)
            event={'path':str(path),'mode':mode,'opened':False,'returned':0,'closed':False};self.game_opens.append(event)
            stream=None
            try:
                require(original==resolved==self.game_key,'Target path alias forbidden')
                # Path.open forwards (-1, None, None, None) to io.open. Accept
                # those normal defaults without enabling encodings/openers or writes.
                defaults={'buffering':-1,'encoding':None,'errors':None,'newline':None}
                require(mode=='rb' and len(args)<=4 and set(kwargs)<=set(defaults),'Exact game rb/default open only')
                supplied=dict(zip(defaults,args))
                require(not set(supplied)&set(kwargs),'Duplicate open argument')
                supplied.update(kwargs)
                require(all(v==defaults[k] and type(v)is type(defaults[k]) for k,v in supplied.items()),'Game open defaults only')
                require(self.game_successful_opens<self.game_open_limit,'Fourth game disk open refused')
                stream=OPEN(file,'rb');self.game_successful_opens+=1;event['opened']=True
                info=os.fstat(stream.fileno())
                require(stat.S_ISREG(info.st_mode) and info.st_size==contract.GAME_BYTES,'Exact game disk file/size')
                event['fstat_bytes']=info.st_size
                return GamePort(self,stream,self.game_key,event)
            except BaseException as exc:
                if stream is not None:stream.close();event['closed']=stream.closed
                event['error']=type(exc).__name__+': '+str(exc);self.open_refusals.append(dict(event));raise
        def before(self,key,category,size,stream,n):
            if category!='game_disk':return super().before(key,category,size,stream,n)
            require(type(n)is int and n>=0,'Game integer request')
            v=self.entry(key,category);v['read_attempts']+=1;v['attempted_requested_bytes']+=n
            self.attempts[category]+=1;self.requested[category]+=n
            if n>self.game_request_limit or self.attempts[category]>self.game_attempt_limit or self.totals[category]+n>self.limits[category]:
                v['refused_before_read']+=1;raise ValueError('Game disk request/attempt/full reservation cap')
    return GameMeter

def main():
    global METER
    require(len(sys.argv)==2,'Only one future grant SHA argument')
    require(not any((HERE/n).exists() for n in ('child-claim.json','child-io.json','child-status-start.json')),'Child attempt/history already exists')
    sha=sys.argv[1];contract=None;state=None;after=None;code=1;failure=None;attempts=0;post_attempted=False
    original_main=sys.modules.get('__main__')
    try:
        contract,state=bootstrap(sha)
        claim=decode(read(HERE/'claim.json'));start=decode(read(HERE/'attempt-start.json'))
        require(claim['authorization_sha256']==sha and claim['selection']==contract.SELECTION and claim['source_manifest']==state['auth']['subject_source_manifest'],'Exact parent claim')
        require(start['authorization_sha256']==sha and start['status_attempts_to']==1 and start['selection']==contract.SELECTION,'Exact parent attempt start')
        save('child-claim.json',{'schema':'EU4-PEACE-V2-CHILD-ONCE-CLAIM/1','authorization_sha256':sha,'selection':contract.SELECTION,'exclusive':True,'maximum_status_attempts':1,'automatic_retry':False})
        source=state['data'][contract.CAND+'offline_child.py']
        donor=types.ModuleType('_peace_v2_frozen_meter_only');donor.__file__=str(ROOT/(contract.CAND+'offline_child.py'))
        exec(compile(source,donor.__file__,'exec'),donor.__dict__)
        host=contract.decode(state['data'][contract.HOST])
        require(len(host['source_pins'])==215 and len(host['selected_external_pins'])==11,'Exact host metadata count')
        paths={str((ROOT/n).resolve()).lower():p for n,p in host['source_pins'].items()}
        paths.update({str(Path(n).resolve()).lower():p for n,p in host['selected_external_pins'].items()})
        require(len(paths)==226 and sum(p['bytes'] for p in paths.values())==255828142,'Exact fixed host size inventory')
        adapter_name=(HERE/'text_config_adapter.py').relative_to(ROOT).as_posix()
        adapter=types.ModuleType('_peace_v2_exact_text_config');adapter.__file__=str(HERE/'text_config_adapter.py')
        exec(compile(state['data'][adapter_name],adapter.__file__,'exec'),adapter.__dict__)
        meter_type=adapter.meter_class(game_meter_class(donor,contract),contract,state['auth']['local_configuration_pin'],OPEN)
        METER=meter_type(paths,state['budgets'])
        builtins.open=METER.open;io.open=METER.open
        script=ROOT/(contract.CAND+'peace_current_pending.py')
        raw=script.read_bytes();require(pin(raw)==pin(state['data'][contract.CAND+'peace_current_pending.py']),'Exact CLI at call')
        s=contract.SELECTION
        sys.argv=[str(script),'status','--pid',str(s['pid']),'--creation',s['creation'],'--actor',s['actor'],'--target',s['target']]
        save('child-status-start.json',{'status_attempts_from':0,'status_attempts_to':1,'argv':sys.argv,'authorization_sha256':sha,'selection':s})
        attempts=1
        module=types.ModuleType('__main__');module.__file__=str(script);sys.modules['__main__']=module
        try:exec(compile(raw,str(script),'exec'),module.__dict__);code=0
        except SystemExit as exc:code=exc.code if type(exc.code)is int else (0 if exc.code is None else 1)
        post_attempted=True;after=contract.verify(read,sha)
        require(state['fingerprint']==after['fingerprint'],'Child source/grant/reviews changed after CLI')
        require(code in (0,2),'Frozen CLI exit outside current/unknown contract')
    except BaseException as exc:
        code=1;failure={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()};traceback.print_exc()
    finally:
        builtins.open=OPEN;io.open=IOOPEN
        if original_main is not None:sys.modules['__main__']=original_main
        if state is not None and not post_attempted:
            try:
                post_attempted=True;after=contract.verify(read,sha)
                require(after['fingerprint']==state['fingerprint'],'Child failure postguard differs')
            except BaseException as exc:
                if failure is None:failure={'type':type(exc).__name__,'message':str(exc)}
                code=1
        totals={'ordinary':CONTROL_RETURNED,'delegated_fixed_host':0,'game_disk':0}
        requested={'ordinary':sum(x['requested'] for x in CONTROL),'delegated_fixed_host':0,'game_disk':0}
        attempts_by_category={'ordinary':len(CONTROL),'delegated_fixed_host':0,'game_disk':0}
        if METER is not None:
            for k in totals:totals[k]+=METER.totals[k];requested[k]+=METER.requested[k];attempts_by_category[k]+=METER.attempts[k]
        save('child-io.json',{'schema':'EU4-PEACE-V2-CURRENT-STATUS-CHILD-IO/2','exit_code':code,'failure':failure,
            'status_attempts':attempts,'authorization_sha256':sha,'source_prepost_equal':state is not None and after is not None and state['fingerprint']==after['fingerprint'],
            'control_reads':CONTROL,'explicit_returned':totals,'attempted_requested':requested,'read_attempts':attempts_by_category,
            'per_path':{} if METER is None else METER.files,'open_refusals':[] if METER is None else METER.open_refusals,
            'text_config':None if METER is None else METER.text_config.summary(),
            'game_opens':[] if METER is None else METER.game_opens,'game_successful_opens':0 if METER is None else METER.game_successful_opens,
            'ordinary_limit_including_control':LIMIT,'budgets':None if state is None else state['budgets'],'ordinary_routes_complete':False,
            'scope':'Explicit Python reads only; OS/import/cache internals excluded. Unknown ordinary paths retain original <=4MiB behavior and hard returned budget; only exact host/game paths have large-file exceptions.',
            'automatic_retry':False,'native_game_calls':0,'requests_published':0,'Frida_called':False,'game_fields_written':0,'tests_run':0})
    return code

if __name__=='__main__':raise SystemExit(main())
