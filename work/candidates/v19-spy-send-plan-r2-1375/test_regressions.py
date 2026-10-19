"""Finite regressions for two reviewed pure-model omissions; no IO/native work."""
import unittest
from model import FAMILIES
from test_model import ready,prefix,dispatched

def enter(m,s):
    f,t=prefix(m,s)
    for kind,data in [('destroy_original',{'returned':True}),('dispatch_intent',{'durable':True}),('submit_enter',{'guard_passed':True})]:
        m.event(kind,s,f,t,**data)
    return f,t

class RegressionTests(unittest.TestCase):
    def test_non_string_event_is_terminal_before_other_mutation(self):
        for kind in ([],{},None,True,False,1,1.0,b'preview',('preview',),set()):
            for completed in (0,1):
                with self.subTest(kind=repr(kind),completed=completed):
                    m,s=ready()
                    if completed:dispatched(m,s)
                    f,t=prefix(m,s,'initialize');before=(m.frame,m.now,m.events,len(m.rows))
                    with self.assertRaises(ValueError):m.event(kind,s,f,t,allowed=False)
                    self.assertTrue(m.frozen);self.assertEqual(m.state,'frozen')
                    self.assertEqual((m.frame,m.now,m.events,len(m.rows)),before)
                    for k,data in [('preview',{'allowed':False}),('destroy_original',{'returned':True}),('health',{'healthy':True})]:
                        with self.assertRaises(ValueError):m.event(k,s,f+1,t+1,**data)
                    self.assertEqual(len(m.summary()['rows']),completed)

    def test_unknown_transfer_retains_current_item_and_return_fields(self):
        for values in [(True,False,True),(True,True,False),(False,None,None),(True,None,True)]:
            for completed in (0,1,4):
                with self.subTest(values=values,completed=completed):
                    m,s=ready()
                    for _ in range(completed):dispatched(m,s)
                    f,t=enter(m,s);data=dict(zip(('returned','accepted','consumed'),values))
                    with self.assertRaises(ValueError):m.event('submit_result',s,f,t,**data)
                    report=m.summary();current=report['current_item']
                    self.assertEqual(len(report['rows']),completed);self.assertEqual(current['ordinal'],completed+1)
                    self.assertEqual(current['family'],FAMILIES[completed]);self.assertEqual(current['item_frame'],f)
                    self.assertTrue(current['submit_entered']);self.assertEqual(current['outcome'],'dispatch_unknown')
                    self.assertEqual(current['submit_record'],data);self.assertEqual(current['last_recorded_owned_objects'],[])
                    self.assertTrue(current['caller_ownership_relinquished']);self.assertFalse(current['completed_later_health'])
                    self.assertFalse(current['cleanup_authorized']);self.assertFalse(current['retry_allowed'])
                    self.assertEqual(report['unattempted_families'],list(FAMILIES[completed+1:]))
                    with self.assertRaises(ValueError):m.event('destroy_command',s,f,t,returned=True)
                    self.assertEqual(m.summary()['current_item'],current)

    def test_enter_without_return_then_fault_preserves_unknown_nullable_record(self):
        m,s=ready();f,t=enter(m,s)
        before=m.summary()['current_item'];self.assertEqual(before['outcome'],'dispatch_unknown')
        self.assertEqual(before['submit_record'],dict(returned=None,accepted=None,consumed=None))
        with self.assertRaises(ValueError):m.event('fault',s,f,t,reason='synthetic exception')
        self.assertEqual(m.summary()['current_item'],before);self.assertTrue(m.frozen)

    def test_invalid_return_scalar_cannot_become_known_transfer(self):
        for name in ('returned','accepted','consumed'):
            for value in (1,1.0,'true',[],{}):
                with self.subTest(name=name,value=value):
                    m,s=ready();f,t=enter(m,s);data=dict(returned=True,accepted=True,consumed=True);data[name]=value
                    with self.assertRaises(ValueError):m.event('submit_result',s,f,t,**data)
                    item=m.summary()['current_item'];self.assertEqual(item['outcome'],'dispatch_unknown')
                    self.assertEqual(item['submit_record'],dict(returned=None,accepted=None,consumed=None));self.assertTrue(m.frozen)

    def test_known_return_requires_later_health_before_completed_rows(self):
        m,s=ready();f,t=enter(m,s);m.event('submit_result',s,f,t,returned=True,accepted=True,consumed=True)
        self.assertEqual(m.summary()['current_item']['outcome'],'dispatched');self.assertEqual(m.summary()['rows'],[])
        m.event('health',s,f+1,t+1,healthy=True)
        self.assertIsNone(m.summary()['current_item']);self.assertEqual(m.summary()['rows'][0]['outcome'],'dispatched')
        self.assertEqual(m.summary()['unattempted_families'],list(FAMILIES[1:]))

    def test_preenter_failure_preserves_last_recorded_objects_without_cleanup_grant(self):
        m,s=ready();f,t=prefix(m,s,'preview')
        with self.assertRaises(ValueError):m.event('wrapper',s,f,t,verified=False)
        item=m.summary()['current_item'];self.assertFalse(item['submit_entered']);self.assertIsNone(item['submit_record'])
        self.assertEqual(item['last_recorded_owned_objects'],['original']);self.assertFalse(item['cleanup_authorized'])
        self.assertFalse(item['caller_ownership_relinquished']);self.assertIsNone(item['outcome'])

    def test_summary_is_copy_and_no_current_item_before_claim_or_after_five(self):
        m,s=ready();self.assertIsNone(m.summary()['current_item']);self.assertEqual(m.summary()['unattempted_families'],list(FAMILIES))
        f,t=enter(m,s);view=m.summary();view['current_item']['submit_record']['accepted']=True
        view['unattempted_families'].clear();self.assertIsNone(m.summary()['current_item']['submit_record']['accepted'])
        self.assertEqual(len(m.summary()['unattempted_families']),4)
        m.event('submit_result',s,f,t,returned=True,accepted=True,consumed=True);m.event('health',s,f+1,t+1,healthy=True)
        for _ in range(4):dispatched(m,s)
        end=m.summary();self.assertIsNone(end['current_item']);self.assertEqual(end['unattempted_families'],[])
        self.assertTrue(end['all_five_dispatched'])
        for key in ('native_calls_performed','native_runtime_verified','actual_journal_validated','production_ready','effect_verified'):self.assertIs(end[key],False)

if __name__=='__main__':unittest.main()
