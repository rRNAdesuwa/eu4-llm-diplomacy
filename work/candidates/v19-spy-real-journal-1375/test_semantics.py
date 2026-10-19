from copy import deepcopy
import unittest
from fixture import fixture,encode
from reader import validate_stream,sha

def rehash(rows,outer):
    for n,r in enumerate(rows,1):r['ordinal']=n
    offset=ordinal=0
    for e in outer:
        if e['event']=='owner_call_begin':e['raw_start']=offset;e['raw_first_ordinal']=ordinal+1
        elif e['event']=='owner_call_return':
            group=[r for r in rows if r.get('frame',r.get('owner_frame'))==e['controller_frame_after']]
            raw=encode(group);offset+=len(raw);ordinal+=len(group);e.update(raw_end=offset,raw_last_ordinal=ordinal,raw_segment_sha256=sha(raw))
    for n,e in enumerate(outer,1):e['ordinal']=n

class SemanticTests(unittest.TestCase):
    def reject(self,mutate):
        r,o,i,c=fixture();mutate(r,o,c);rehash(r,o)
        with self.assertRaises((ValueError,KeyError)):validate_stream(encode(r),encode(o),i,c,True)
    def test_core_types_every_boundary(self):
        for kind in (0,1,2,3,4,5,6,7):
            for key in ('frame','completed','operation','request_sequence','uptime_ms','expires_uptime_ms'):
                with self.subTest(kind=kind,key=key):
                    def mutate(r,o,c):
                        e=next(x['core'] for x in r if x['event']=='send_core' and x['core']['kind']==kind);e[key]=float(e[key])
                    self.reject(mutate)
    def test_item_fullhandle_and_cleanup(self):
        for key in ('actor','controller','target','envoy','state','value','vtable'):
            def mutate(r,o,c):
                e=next(x['core'] for x in r if x['event']=='send_core' and x['core']['kind']==3 and x['core']['item']['step']==4)
                e['item']['original_fields'][key]+=1
            self.reject(mutate)
        for key in ('has_local_command','has_local_clone','submit_returned','slot_consumed','original_destroyed'):
            def mutate(r,o,c):
                e=next(x['core'] for x in r if x['event']=='send_core' and x['core']['kind']==5);e['item'][key]=not e['item'][key]
            self.reject(mutate)
    def test_missing_result_or_intent_or_health(self):
        for event,kind in [('operation_result',None),('send_core',4),('send_core',6),('send_core',7),('final_health',None)]:
            self.reject(lambda r,o,c:r.pop(next(n for n,x in enumerate(r) if x['event']==event and (kind is None or x['core']['kind']==kind))))
    def test_partial_does_not_use_future_health(self):
        r,o,i,c=fixture(5);s=validate_stream(encode(r),encode(o),i,c)
        self.assertFalse(s['preflight_ready']);self.assertEqual(s['authenticated_stages'],0);self.assertIsNone(s['next_sequence'])
    def test_wrong_world_or_identity(self):
        for key in ('holder','context','transport','actor_overlord','target_overlord'):
            self.reject(lambda r,o,c:next(x['core'] for x in r if x['event']=='send_core' and x['core']['kind']==1).__setitem__(key,0))
    def test_raw_ordinal_alias(self):
        r,o,i,c=fixture();r[-1]['ordinal']=float(r[-1]['ordinal'])
        # Deliberately preserve the alias but update segment hash.
        o[-2]['raw_segment_sha256']=sha(encode([r[-1]]));o[-2]['raw_end']+=2
        with self.assertRaises(ValueError):validate_stream(encode(r),encode(o),i,c)
    def test_native_return_after_expiry_is_interval_not_point(self):
        # Last submit call may normally return after its pre-entry barrier TTL.
        r,o,i,c=fixture();start=next(n for n,x in enumerate(r) if x['event']=='send_core' and x['core']['kind']==3 and x['core']['item']['ordinal']==5 and x['core']['item']['step']==10)
        for x in r[start:]:
            x['uptime_ms']=70001
            if 'core'in x:x['core']['uptime_ms']=70001
        for x in o:
            if x.get('controller_frame_after',0)>=16 or x.get('controller_frame_before',0)>=16 or x['event']=='completed_send_batch':x['uptime_ms']=70001
        rehash(r,o);s=validate_stream(encode(r),encode(o),i,c,True)
        interval=next(x for x in s['intervals'] if x['family']==4 and x['step']==10)
        self.assertEqual(interval['return_observed_uptime'],70001);self.assertIsNone(interval['entry_uptime'])
    def test_unknown_submit_retains_full_result_frozen(self):
        r,o,i,c=fixture(8);ret=next(n for n,x in enumerate(r) if x['event']=='send_core' and x['core']['kind']==3 and x['core']['item']['step']==10)
        r[ret]['core']['item']['submit_value']=False
        fault=deepcopy(r[ret]);fault['core'].update(kind=8,state=4,reason=17);fault['host_failure']=12
        result=deepcopy(r[-1]);result.update(event='terminal_result',host_failure=12)
        result['result'].update(state=4,reason=17,accepted_call=False,audit_complete=False,freeze_session=True,ownership_uncertain=True,current_item=deepcopy(fault['core']['item']))
        r=r[:ret+1]+[fault,result]
        o[-1].update(state=5,failure=12,controller_returned=False,success=False)
        term={k:v for k,v in o[-1].items() if k in __import__('reader').COMMON};term.update(event='terminal',owner_entry=8,unknown_no_retry=True);o.append(term)
        rehash(r,o);s=validate_stream(encode(r),encode(o),i,c)
        self.assertEqual(s['status'],'frozen');self.assertEqual(s['terminal_result']['result']['current_item']['outcome'],4)
        self.assertFalse(s['retry_allowed']);self.assertIsNone(s['next_sequence'])

if __name__=='__main__':unittest.main()
