"""Strict offline v15 default-owned-peace phase validator; no process or native calls."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.verify_diplomacy_lifecycle_v15 import require, integer

OWNED_EVENTS = frozenset(('owned_peace_selftest_begin','owned_peace_core_record','owned_peace_selftest_complete'))
RESULT_FLAGS = ('factory_entered','factory_returned','clone_entered','clone_returned',
    'original_destroy_entered','original_destroy_returned','clone_destroy_entered','clone_destroy_returned',
    'distinct_owned_ranges','original_unchanged_after_clone','clone_unchanged_after_original_destroy')
ZERO_FIELDS = ('reason','original_mismatch_mask','clone_mismatch_mask','exception')
FALSE_FIELDS = ('retry_allowed','execution_verified','submitted')
CORE_KEYS = {'event','step','action','token','thread_id','freeze_session',*RESULT_FLAGS,*ZERO_FIELDS,*FALSE_FIELDS}
WRAPPER_KEYS = {'event','record_kind','pid','process_creation_filetime','thread_id','passed',
    'core_passed','core_audit_complete','post_guard_ok','freeze_session',*RESULT_FLAGS,*ZERO_FIELDS,*FALSE_FIELDS}

def canonical_creation(value):
    # Native %016llx and the marker both serialize FILETIME as a string. Do not
    # accept numeric coercions, even when an integer has an exact float encoding.
    return type(value) is str and re.fullmatch(r'[0-9a-f]{16}',value) is not None and int(value,16)>0

def expected_core_flags(completed):
    # Exactly follows begin-before-invocation and complete-after-contract checks.
    flags={name:0 for name in RESULT_FLAGS}
    if completed >= 1: flags.update(factory_entered=1,factory_returned=1)
    if completed >= 2: flags.update(clone_entered=1,clone_returned=1,distinct_owned_ranges=1,original_unchanged_after_clone=1)
    if completed >= 3: flags.update(original_destroy_entered=1,original_destroy_returned=1,clone_unchanged_after_original_destroy=1)
    if completed >= 4: flags.update(clone_destroy_entered=1,clone_destroy_returned=1)
    return flags

class OwnedPeaceSession:
    """Core (9 records), returned wrapper, and later healthy frame are independent.

    Raises immediately on malformed/failed evidence. A valid partial prefix has
    no proof and may not be retried; the protocol also checks permanent claims.
    """
    def __init__(self,metadata):
        require(isinstance(metadata,dict) and integer(metadata.get('pid'),1)
            and integer(metadata.get('window_thread'),1) and canonical_creation(metadata.get('process_creation_filetime')),
            'Owned-peace metadata needs canonical PID/creation/window-thread identity')
        self.metadata=metadata
        self.begin_line=None;self.complete_line=None;self.health_line=None
        self.last_frame=None;self.start_world=None;self.records=[];self.wrapper=None

    def binding(self,event):
        require(type(event.get('pid')) is int and event['pid']==self.metadata['pid']
            and canonical_creation(event.get('process_creation_filetime'))
            and event['process_creation_filetime']==self.metadata['process_creation_filetime']
            and type(event.get('thread_id')) is int and event['thread_id']==self.metadata['window_thread'],
            'Owned-peace record lacks exact PID/creation/window-thread binding')
        require(event.get('submitted') is False,'Owned-peace phase must not submit')

    def frame(self,event,line):
        require(type(event.get('owned_peace_tested')) is bool and type(event.get('owned_peace_passed')) is bool,
            'Missing or nonboolean owned-peace frame diagnostics')
        require(event['owned_peace_tested']==(self.begin_line is not None)
            and event['owned_peace_passed']==(self.complete_line is not None),
            'Frame contradicts owned-peace begin/wrapper evidence')
        require(self.begin_line is None or self.complete_line is not None,
            'Unexpected frame interleaved with synchronous owned-peace native calls')
        if self.complete_line is not None and self.health_line is None:
            require(line>self.complete_line and event.get('world_ready') is True and event.get('paused') is True
                and event.get('lifecycle_passed') is True and event.get('send_enabled') is False
                and event.get('thread_changed') is False and event.get('session_frozen') is False
                and event.get('world_changed') is False and event.get('thread')==self.metadata['window_thread'],
                'Owned-peace needs a later healthy paused no-send frame')
            require(tuple(event.get(k) for k in ('world_cookie','player_handle','raw_date'))==self.start_world,
                'Owned-peace before/after frame identity or date differs')
            self.health_line=line
        self.last_frame=(line,event)

    def accept(self,event,line,*,lifecycle_proved):
        name=event.get('event'); self.binding(event)
        if name=='owned_peace_selftest_begin':
            require(set(event)=={'event','pid','process_creation_filetime','thread_id','durable_claim',
                'base_lifecycle_count','send_enabled','submitted'},'Unexpected owned-peace begin schema')
            require(self.begin_line is None and lifecycle_proved and self.last_frame is not None,
                'Repeated owned-peace attempt or missing base lifecycle proof')
            prior_line,prior=self.last_frame
            require(prior_line<line and prior.get('world_ready') is True and prior.get('paused') is True
                and prior.get('lifecycle_passed') is True and prior.get('send_enabled') is False,
                'Owned-peace began without healthy paused post-lifecycle frame')
            require(event.get('durable_claim') is True and type(event.get('base_lifecycle_count')) is int
                and event['base_lifecycle_count']==20 and event.get('send_enabled') is False,
                'Owned-peace lacks durable claim or exact base count')
            self.begin_line=line
            self.start_world=tuple(prior.get(k) for k in ('world_cookie','player_handle','raw_date'))
        elif name=='owned_peace_core_record':
            require(self.begin_line is not None and self.complete_line is None and len(self.records)<9,
                'Owned-peace core is duplicate/out of order')
            require(set(event)=={'event','pid','process_creation_filetime','thread_id','core','submitted'},
                'Unexpected owned-peace core envelope schema')
            core=event.get('core'); require(isinstance(core,dict) and set(core)==CORE_KEYS,'Missing/unknown owned-peace core fields')
            index=len(self.records)
            expected_name=('owned_peace_lifecycle_return' if index==8 else
                           'owned_peace_lifecycle_step_begin' if index%2==0 else 'owned_peace_lifecycle_step_complete')
            expected_step=0 if index==8 else index//2+1
            completed=4 if index==8 else (index+1)//2
            require(core.get('event')==expected_name and type(core.get('step')) is int and core['step']==expected_step,
                'Owned-peace requires ordered begin/complete steps 1..4 then return')
            require(core.get('action')=='requestpeace' and type(core.get('token')) is int and core['token']==0x293c
                and type(core.get('thread_id')) is int and core['thread_id']==self.metadata['window_thread'],
                'Owned-peace core action/token/thread differs')
            require(all(type(core.get(k)) is int and core[k]==v for k,v in expected_core_flags(completed).items()),
                'Owned-peace entered/returned/layout flags differ from native step ordering')
            require(all(type(core.get(k)) is int and core[k]==0 for k in (*ZERO_FIELDS,'freeze_session')),
                'Owned-peace core reports exception, ownership/layout mismatch or freeze')
            require(all(core.get(k) is False for k in FALSE_FIELDS),'Owned-peace core overclaims execution or permits retry')
            self.records.append({'line':line,**core})
        elif name=='owned_peace_selftest_complete':
            require(self.begin_line is not None and self.complete_line is None and len(self.records)==9,
                'Owned-peace wrapper lacks all nine native core records')
            require(set(event)==WRAPPER_KEYS and event.get('record_kind')=='wrapper_result',
                'Owned-peace completion is not the exact returned wrapper schema')
            require(all(event.get(k) is True for k in (*RESULT_FLAGS,'passed','core_passed','core_audit_complete','post_guard_ok')),
                'Owned-peace wrapper did not prove return/ownership/audit/post-guard success')
            require(all(type(event.get(k)) is int and event[k]==0 for k in ZERO_FIELDS)
                and all(event.get(k) is False for k in (*FALSE_FIELDS,'freeze_session')),
                'Owned-peace wrapper reports failure or claims execution')
            self.wrapper=dict(event); self.complete_line=line
        else: require(False,'Unknown owned-peace event')

    def finish(self):
        require(self.begin_line is not None and self.complete_line is not None and self.health_line is not None,
            'Owned-peace core/wrapper/following healthy frame is incomplete')
        return {'pid':self.metadata['pid'],'process_creation_filetime':self.metadata['process_creation_filetime'],
            'window_thread':self.metadata['window_thread'],'owned_peace_begin_line':self.begin_line,
            'owned_peace_complete_line':self.complete_line,'healthy_frame_line':self.health_line,
            'core_record_count':len(self.records),'core_records':self.records,'wrapper_result':self.wrapper,
            'frame_identity':dict(zip(('world_cookie','player_handle','raw_date'),self.start_world)),
            'passed':True,'verification_scope':'default_owned_peace_lifecycle_only','execution_verified':False,
            'war_identity_verified':False,'parameterized_offer_verified':False,'heap_release_independently_observed':False,
            'world_generation_verified':False}

def verify(log,pid,before,after,build_manifest):
    from tools.verify_diplomacy_lifecycle_v15 import verify_phase
    return verify_phase('owned_peace',Path(log),pid,Path(before),Path(after),Path(build_manifest))

def main(argv=None):
    from work.native import lab_protocol_v15_1375 as lab
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid',type=int,required=True);parser.add_argument('--creation',required=True)
    args=parser.parse_args(argv)
    try:
        manifest,manifest_sha=lab.verify_build()
        session=lab.session_path(lab.OUTPUT,args.pid,args.creation)
        metadata=lab.read_session_metadata(session,args.pid,args.creation)
        evidence=lab.read_evidence(session,metadata)
        proof=evidence['phase_proofs'].get('owned_peace')
        print(json.dumps({'purpose':lab.PURPOSE,'phase':'owned_peace','proof':proof,'manifest_sha256':manifest_sha,
            'dll_sha256':manifest['dll_sha256'],'log_sha256':evidence['log_sha256'],'game_process_accessed':False,
            'execution_verified':False,'production_backend_registered':False},indent=2))
        return 0 if proof and proof['passed'] else 1
    except (OSError,ValueError,RuntimeError,KeyError) as error:
        print(str(error),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
