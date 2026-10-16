"""Finite native field audit and action/phase-specific envoy counterexamples."""
import json
import unittest
import reviewer as r
import test_pair_contract as pair


class EnvoyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):pair.PairContractTests.setUpClass()
    @classmethod
    def tearDownClass(cls):pair.PairContractTests.tearDownClass()
    def fresh(self):
        self.case=pair.PairContractTests();self.case.setUp();return self.case
    def action(self,action):
        c=self.case;c.request(action=action)
        for row in c.rows:
            if row['event']=='lab_request_complete' and row['sequence']==3:row['action']=action
        for core in c.cores():
            core.update(action_id=action,
                fixed_subsidy_amount_milli=1000 if action in ('give_subsidies','cancel_subsidies') else 0,
                fixed_subsidy_duration_years=10 if action in ('give_subsidies','cancel_subsidies') else 0,
                fixed_gift_amount_milli=25000 if action=='send_gift' else 0,
                fixed_transfer_fraction_milli=500 if action in ('request_trade_power','cancel_trade_power_transfer') else 0,
                fixed_insult_index=-1 if action=='insult' else 0)
    def spy(self,phase=13,reason=0,envoy=0):
        c=self.fresh();self.action('stop_building_spy_network')
        if phase!=13:c.noenter('submit' if phase in (10,12) else 'legality_only',phase,reason)
        for core in c.cores():
            if core['event']!='pair_engine_begin':core['envoy_id']=envoy
        return c

    def test_original_three_full_replay_counterexamples_rejected(self):
        c=self.fresh()
        for core in c.cores()[1:]:core['envoy_id']=123
        c.finish(False)
        for envoy in (-1,2**31):self.spy(envoy=envoy).finish(False)

    def test_nonspy_all_35_actions_keep_unresolved_envoy_even_after_binding(self):
        actions=sorted(self.case_actions())
        self.assertEqual(len(actions),36)
        for action in actions:
            if action=='stop_building_spy_network':continue
            with self.subTest(action=action):
                c=self.fresh();self.action(action);c.finish(True)
                for core in c.cores()[1:]:core['envoy_id']=123
                c.finish(False)

    def case_actions(self):
        c=self.fresh();return c.case.lab.ACTIONS

    def test_stopspy_all_postbinding_phases_accept_exact_int32_endpoints(self):
        for phase,reason in ((6,17),(8,18),(8,0),(10,20),(12,8),(13,0)):
            for envoy in (0,1,123,2**31-1):
                with self.subTest(phase=phase,envoy=envoy):self.spy(phase,reason,envoy).finish(True)

    def test_stopspy_all_postbinding_phases_reject_negative_overflow_and_aliases(self):
        for phase,reason in ((6,17),(8,18),(8,0),(10,20),(12,8),(13,0)):
            for envoy in (-2**31,-2,-1,2**31,2**32-1,False,True,0.0,float(2**31-1),None,'0'):
                with self.subTest(phase=phase,envoy=envoy):self.spy(phase,reason,envoy).finish(False)

    def test_begin_and_binding_failure_remain_minus_one_even_for_stopspy(self):
        self.spy(3,13,-1).finish(True)
        for envoy in (0,1,123,2**31-1,2**31,False,True,-1.0,None):
            with self.subTest(boundary='binding-failure',envoy=envoy):self.spy(3,13,envoy).finish(False)
            with self.subTest(boundary='begin',envoy=envoy):
                c=self.spy();c.cores()[0]['envoy_id']=envoy;c.finish(False)

    def test_each_nonspy_phase_cannot_claim_a_resolved_envoy(self):
        for phase,reason in ((3,13),(6,17),(8,18),(8,0),(10,20),(12,8),(13,0)):
            for envoy in (0,123,2**31-1,2**31,-2,False,-1.0):
                with self.subTest(phase=phase,envoy=envoy):
                    c=self.fresh()
                    if phase!=13:c.noenter('submit' if phase in (10,12) else 'legality_only',phase,reason)
                    for core in c.cores()[1:]:core['envoy_id']=envoy
                    c.finish(False)

    def test_intent_and_final_resolved_envoy_cannot_differ(self):
        for index in (1,2):
            c=self.spy(envoy=0);c.cores()[index]['envoy_id']=1;c.finish(False)

    def test_every_native_pair_field_has_an_enforced_meaning_at_each_boundary(self):
        c=self.fresh();base=c.case.base
        groups=(base.PAIR_INTS,base.PAIR_BOOLS,base.PAIR_NULLABLE,base.PAIR_STRINGS)
        all_fields=set().union(*groups)
        self.assertEqual(len(all_fields),35)
        self.assertEqual(sum(map(len,groups)),35)
        self.assertEqual(set(c.cores()[0]),all_fields)
        # One same-type mutation of every complete schema field at each native
        # boundary. Nullable values deliberately stay within bool-or-null.
        for index in range(3):
            for field in sorted(all_fields):
                with self.subTest(index=index,field=field):
                    c=self.fresh();core=c.cores()[index];value=core[field]
                    if field in base.PAIR_INTS:core[field]=value+1
                    elif field in base.PAIR_BOOLS:core[field]=not value
                    elif field in base.PAIR_NULLABLE:core[field]=False if value is None else None
                    else:core[field]='wrong'
                    if index==2:c.wrapper()
                    c.finish(False)

    def test_frozen_envoy_producer_assignment_closure(self):
        text=r.bounded(r.ROOT/'work/native/v17/pair-engine-1375.cpp').decode()
        self.assertEqual(text.count('binding = {envoy, entry, mission, task};'),1)
        self.assertIn('const auto envoy = read_at<std::int32_t>(entry + 0x44);',text)
        self.assertIn('if (envoy < 0 ||',text)
        self.assertEqual(text.count('result.resolved_envoy_id = binding.envoy;'),1)
        self.assertEqual(text.count('result.resolved_envoy_id = -1;'),1)
        begin=text.index('if (!audit(host, request, result, "pair_engine_begin"))')
        guard=text.index('if (!cancellation_binding(module, live, actor, target, request.action, binding))')
        assigned=text.index('result.resolved_envoy_id = binding.envoy;')
        self.assertLess(begin,guard);self.assertLess(guard,assigned)


if __name__=='__main__':unittest.main()
