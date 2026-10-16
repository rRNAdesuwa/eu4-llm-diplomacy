"""At most three append-only whole-file reads; R2 semantics never relaxed."""
from pathlib import Path
import time,types
from _base import base,require,sha

TAIL_ERROR='No unbound raw tail/incomplete owner call'
MAX_ATTEMPTS=3;MAX_TOTAL_BYTES=64*1024*1024;MAX_READ_CALLS=384
RETRY_DELAY_SECONDS=0.01

class CoherentReadError(ValueError):
    def __init__(self,reason,attempts):
        super().__init__(reason);self.attempts=attempts;self.retry_allowed=False

class _Reads:
    def __init__(self,session):
        self.log_paths={str((session/name).resolve()):name for name in ('raw-events.jsonl','bootstrap-events.jsonl')}
        self.total_bytes=0;self.calls=0;self.previous={};self.previous_claims=set();self.fixed={};self.logs={};self.claims=set();self.start_bytes=0;self.start_calls=0
    def begin(self):
        self.logs={};self.claims=set();self.start_bytes=self.total_bytes;self.start_calls=self.calls
    def bounded(self,path,limit):
        require(type(limit)is int and 0<=limit<=16777216,'Read-size contract')
        require(self.calls<MAX_READ_CALLS,'Coherent read-call budget');self.calls+=1
        remaining=MAX_TOTAL_BYTES-self.total_bytes;require(remaining>=0,'Coherent total-byte budget')
        # One read at most the remaining total+sentinel, never limit then stat.
        raw=base.client.b.bounded(path,min(limit,remaining));self.total_bytes+=len(raw)
        key=str(Path(path).resolve());descriptor=(len(raw),sha(raw))
        if key in self.log_paths:
            name=self.log_paths[key]
            require(name not in self.logs,'Exactly one whole read of each log per attempt')
            self.logs[name]=raw
            if name in self.previous:
                previous=self.previous[name]
                require(raw.startswith(previous),'Log rewritten/truncated between attempts')
                suffix=raw[len(previous):]
                if suffix:
                    require(suffix.endswith(b'\n'),'Partial appended log line')
                    for line in suffix.splitlines():
                        require(0<len(line)<=8192,'Appended log row budget')
                        row=base.client.b.json_value(line)
                        require(type(row)is dict,'Appended row type')
                        if name=='raw-events.jsonl':require(row.get('event')=='health','Only health may append during coherent reread')
                        else:
                            require(row.get('event') in ('owner_call_begin','owner_call_return','completed_no_send'),'Only health pairing may append during coherent reread')
                            if row['event']=='owner_call_begin':require(type(row.get('request_sequence'))is int and row['request_sequence']==0,'New request callback during coherent reread')
        else:
            if key in self.fixed:require(self.fixed[key]==descriptor,'Non-log input changed between attempts')
            self.fixed[key]=descriptor
            if Path(key).parent==Path(next(iter(self.log_paths))).parent and Path(key).name in ('1.claim','2.claim','3.claim'):
                sequence=int(Path(key).stem)
                require(not self.previous or sequence in self.previous_claims,'New claim during coherent reread')
                self.claims.add(sequence)
        return raw
    def metadata(self):
        return {'read_calls':self.calls-self.start_calls,'read_bytes':self.total_bytes-self.start_bytes,
                'total_read_calls':self.calls,'total_read_bytes':self.total_bytes,
                'logs':{k:{'bytes':len(v),'sha256':sha(v)} for k,v in sorted(self.logs.items())}}
    def retain(self):self.previous=dict(self.logs);self.previous_claims=set(self.claims)

def _reader(reads):
    # A new private module namespace per inspect. The verified source bytes and
    # original __file__ stay exact; only its bounded-file function records reads.
    b=base._module(base.OLD/'build_manifest.py',{})
    b.bounded=reads.bounded
    frozen=types.SimpleNamespace(b=b,wire=base.client.wire,trace=base.reader.trace)
    return base._module(base.R2/'real_capture.py',{'_frozen':frozen})

def _health_tail(reader,reads):
    require(set(reads.logs)=={'raw-events.jsonl','bootstrap-events.jsonl'},'Both whole logs required')
    raw=reads.logs['raw-events.jsonl'];outer=reads.logs['bootstrap-events.jsonl']
    rows,lines=reader.records(raw,reader.trace.MAX_BYTES,reader.trace.MAX_LINES)
    outside,_=reader.records(outer,2097152,1024)
    # Check every raw row, including the unmatched health. No prefix is cut,
    # no row is synthesized, and no partially executed stage may be retried.
    semantic=reader.trace.inspect(rows,complete=False)
    pending=outside[-1] if outside[-1]['event']=='owner_call_begin' else None
    previous=outside[-2] if pending is not None else outside[-1]
    require(previous['event']=='owner_call_return','A previous complete healthy owner call is required')
    completed=semantic['completed_stages']
    require(reads.claims==set(range(1,completed+1)) and previous['claimed']==previous['completed']==completed,'No extra/unbound stage claim')
    bound=previous['raw_last_ordinal'];offset=previous['raw_end'];frame=previous['controller_frame_after']
    require(type(bound)is int and type(offset)is int and type(frame)is int and
            len(rows) in (bound,bound+1) and sum(len(x) for x in lines[:bound])==offset,'At most one complete health row beyond paired data')
    if pending is not None:
        require(type(pending['request_sequence'])is int and pending['request_sequence']==0,'Request callback tails are never retried')
        require(pending['controller_frame_before']==frame and pending['raw_start']==offset and pending['raw_first_ordinal']==bound+1,'Health begin continuation')
    else:require(len(rows)==bound+1,'No incomplete health tail')
    if len(rows)==bound+1:
        row=rows[-1];minimum=(pending or previous)['uptime_ms']
        require(row['event']=='health' and type(row['frame'])is int and row['frame']==frame+1 and
                type(row['uptime_ms'])is int and row['uptime_ms']>=minimum,'Unpaired row is not the next typed health')
    return 'complete_health_begin_waiting_for_return' if pending is not None else 'one_complete_health_waiting_for_outer_pair'

def inspect(directory,identity,complete=False):
    require(type(complete)is bool,'Exact complete flag')
    directory=base.client.b.no_links(directory).resolve();identity=base.client.wire.identity(identity)
    reads=_Reads(base.client.wire.session_path(directory,identity));reader=_reader(reads);attempts=[]
    for number in range(1,MAX_ATTEMPTS+1):
        reads.begin()
        try:
            result=reader.inspect(directory,identity,complete)
        except (ValueError,OSError,TypeError,KeyError,IndexError,RecursionError) as exc:
            record=dict(attempt=number,error=str(exc),error_type=type(exc).__name__,**reads.metadata())
            classification=None
            if type(exc)is ValueError and str(exc)==TAIL_ERROR:
                try:classification=_health_tail(reader,reads)
                except (ValueError,TypeError,KeyError,IndexError,RecursionError) as semantic:
                    record['terminal_detail']=str(semantic)
            record['classification']=classification or 'terminal_nonretryable'
            record['will_reread']=classification is not None and number<MAX_ATTEMPTS
            attempts.append(record)
            if not record['will_reread']:raise CoherentReadError(str(exc),attempts) from exc
            reads.retain();time.sleep(RETRY_DELAY_SECONDS)
        else:
            attempts.append(dict(attempt=number,result='complete_original_R2_inspect_passed',will_reread=False,**reads.metadata()))
            result['coherent_read']={'revision':'v18_health_tail_r3','attempts':attempts,'max_attempts':MAX_ATTEMPTS,
                'max_total_bytes':MAX_TOTAL_BYTES,'max_read_calls':MAX_READ_CALLS,'prefix_discarded':False,
                'semantic_validator':'unchanged_sealed_R2','publication_retried':False}
            return result
    raise AssertionError('Unreachable')
