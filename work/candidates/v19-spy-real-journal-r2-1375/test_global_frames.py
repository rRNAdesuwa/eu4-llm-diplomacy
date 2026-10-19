"""Synthetic global owner-frame handoff, never actual session/process reads."""
from copy import deepcopy
from itertools import groupby
import unittest
from fixture import fixture,encode
from reader import validate_stream,sha
from interval import Interval

def framed(prefix=0,idle=0):
    rows,outer,identity,claims=fixture()
    original={e['controller_frame_after']:e for e in outer if e['event']=='owner_call_return'}
    def frame(value):return value+prefix+(idle if value>=7 else 0)
    def recurse(value):
        if type(value)is list:return [recurse(x) for x in value]
        if type(value)is not dict:return value
        result={k:recurse(v) for k,v in value.items()}
        for key in ('frame','owner_frame'):
            if key in result and result[key]:result[key]=frame(result[key])
        if 'third_stage_health_frame' in result:result['third_stage_health_frame']+=prefix
        return result
    actual=[];source_frame={}
    first=deepcopy(rows[0]);first.update(claimed_sequence=0,completed_stages=0)
    for n in range(1,prefix+1):
        row=deepcopy(first);row['frame']=n;actual.append(row);source_frame[n]=0
    for old,group in groupby(rows,key=lambda r:r.get('frame',r.get('owner_frame'))):
        group=list(group);actual.extend(recurse(group));source_frame[frame(old)]=old
        if old==6:
            for n in range(1,idle+1):
                row=deepcopy(group[-1]);row['frame']=6+prefix+n;actual.append(row);source_frame[row['frame']]=6
    for n,row in enumerate(actual,1):row['ordinal']=n
    result=deepcopy(outer[:3]);offset=ordinal=0
    for global_frame,group in groupby(actual,key=lambda r:r.get('frame',r.get('owner_frame'))):
        group=list(group);old=source_frame[global_frame];segment=encode(group)
        template=deepcopy(original[old or 2]);seq=next((r['sequence'] for r in group if r['event']=='claim'),4 if old==7 else 0)
        begin=deepcopy(outer[3]);begin.update(owner_entry=global_frame,controller_frame_before=global_frame-1,
            raw_start=offset,raw_first_ordinal=ordinal+1,request_sequence=seq,ordinal=len(result)+1)
        result.append(begin);offset+=len(segment);ordinal+=len(group)
        template.update(owner_entry=global_frame,controller_frame_after=global_frame,raw_end=offset,
            raw_last_ordinal=ordinal,raw_segment_sha256=sha(segment),ordinal=len(result)+1)
        if not old:template.update(claimed_sequence=0,preflight_stages=0,authenticated_stages=0,preflight_ready=True)
        result.append(template)
    footer=deepcopy(outer[-1]);footer.update(owner_entry=frame(18),controller_frame=frame(18),ordinal=len(result)+1);result.append(footer)
    return actual,result,identity,claims

def rehash(rows,outer):
    lines=encode(rows).splitlines(keepends=True);offset=ordinal=0
    for row in outer:
        if row['event']=='owner_call_begin':row.update(raw_start=offset,raw_first_ordinal=ordinal+1)
        elif row['event']=='owner_call_return':
            end=row['raw_last_ordinal'];segment=b''.join(lines[ordinal:end]);offset+=len(segment);ordinal=end
            row.update(raw_end=offset,raw_segment_sha256=sha(segment))

class GlobalFrameTests(unittest.TestCase):
    def test_complete_no_gap_and_idle_preflight_keep_global_frames(self):
        for prefix,idle in ((0,0),(0,1),(0,18),(60,18)):
            rows,outer,identity,claims=framed(prefix,idle)
            result=validate_stream(encode(rows),encode(outer),identity,claims,True)
            self.assertEqual(result['status'],'complete');self.assertEqual(result['completed_outcomes'],[5]*5)
            mapping=result['send_frame_mapping'];self.assertEqual(mapping['third_stage_health_frame'],6+prefix)
            self.assertEqual(mapping['preceding_global_frame'],6+prefix+idle)
            self.assertEqual(mapping['first_global_frame'],7+prefix+idle)
            self.assertEqual(mapping['last_global_frame'],18+prefix+idle);self.assertEqual(mapping['last_send_local_frame'],12)
            self.assertFalse(mapping['raw_frames_rewritten']);self.assertFalse(mapping['timestamps_rewritten'])
            for interval in result['intervals']:
                self.assertEqual(interval['owner_frame'],mapping['preceding_global_frame']+interval['send_local_frame'])
                self.assertIsNone(interval['entry_uptime'])

    def test_first_send_cannot_borrow_latest_health_as_third_receipt(self):
        rows,outer,identity,claims=framed(3,18)
        for row in rows:
            if row['schema']=='EU4SPYSENDHOST/1':row['third_stage_health_frame']=27
        rehash(rows,outer)
        with self.assertRaises(ValueError):validate_stream(encode(rows),encode(outer),identity,claims,True)

    def test_outer_first_send_before_frame_cannot_skip_or_alias(self):
        for value in (26,28,True,27.0):
            rows,outer,identity,claims=framed(3,18)
            begin=next(e for e in outer if e['event']=='owner_call_begin' and e['request_sequence']==4)
            begin['controller_frame_before']=value
            with self.assertRaises(ValueError):validate_stream(encode(rows),encode(outer),identity,claims,True)

    def test_raw_core_and_retained_item_frames_are_global_not_rebased(self):
        for selector in ('raw','core','item','result'):
            rows,outer,identity,claims=framed(3,18)
            if selector=='raw':next(r for r in rows if r['schema']=='EU4SPYSENDHOST/1')['owner_frame']=1
            elif selector=='core':next(r for r in rows if r['event']=='send_core')['core']['frame']=1
            elif selector=='item':next(r for r in rows if r.get('core',{}).get('item',{}).get('owner_frame',0)>0)['core']['item']['owner_frame']=2
            else:next(r for r in rows if r.get('result',{}).get('current_item',{}).get('owner_frame',0)>0)['result']['current_item']['owner_frame']=2
            rehash(rows,outer)
            with self.assertRaises(ValueError):validate_stream(encode(rows),encode(outer),identity,claims,True)

    def test_clock_unknown_result_and_complete_flags_not_relaxed(self):
        for selector in ('clock','missing_result','unknown_submit'):
            rows,outer,identity,claims=framed(3,18)
            if selector=='clock':next(r for r in rows if r['schema']=='EU4SPYSENDHOST/1')['uptime_ms']=9999
            elif selector=='missing_result':next(r for r in rows if r['event']=='operation_result').pop('result')
            else:
                row=next(r for r in rows if r.get('core',{}).get('item',{}).get('submit_returned'))
                row['core']['item']['submit_value']=False
            rehash(rows,outer)
            with self.assertRaises((ValueError,KeyError)):validate_stream(encode(rows),encode(outer),identity,claims,True)

    def test_missing_intervening_owner_callback_is_not_an_offset_license(self):
        rows,outer,identity,claims=framed(3,18)
        begin_index=next(n for n,e in enumerate(outer) if e['event']=='owner_call_begin' and e['controller_frame_before']==10)
        del outer[begin_index:begin_index+2]
        for n,row in enumerate(outer,1):row['ordinal']=n
        with self.assertRaises(ValueError):validate_stream(encode(rows),encode(outer),identity,claims,True)

    def test_interval_requires_typed_prior_global_and_consecutive_local_mapping(self):
        rows,_,identity,claims=fixture(6);observed=rows[0]['observed'];image=rows[0]['image_base'];thread=rows[0]['thread']
        for prior in (5,True,6.0,-1):
            with self.assertRaises(ValueError):Interval(identity,image,thread,observed,6,dict(expires=70000),prior)
        interval=Interval(identity,image,thread,observed,6,dict(expires=70000),24)
        interval.begin(25,10000,4);self.assertEqual((interval.frame,interval.local_frame),(25,1))
        self.assertEqual(interval.third,6)

if __name__=='__main__':unittest.main()
