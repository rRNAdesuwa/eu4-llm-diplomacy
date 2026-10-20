import unittest
from bridge.harness import HarnessError, build_prompt, validate_decision, _request_for_decision
from bridge.protocol import Snapshot
from bridge.compiler import compile_request


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.fields = dict(treasury='33.722', manpower_raw='18.354', stability='0',
                           year='1445', ai='1', war='1', locked='1')

    def test_invalid_state_is_rejected_before_model_call(self):
        for change in ({'treasury': ''}, {'treasury': 'NaN'}, {'ai': '0'}, {'war': '2'}):
            with self.subTest(change=change), self.assertRaises(HarnessError):
                build_prompt(Snapshot('live', 'FRA', self.fields | change), '请谈判')
        del self.fields['year']
        with self.assertRaises(HarnessError):
            build_prompt(Snapshot('live', 'FRA', self.fields), '请谈判')

    def test_no_arbitrary_model_actions(self):
        for action in ('unlock_diplomacy', 'declare_war_with_cb', 'run_script'):
            with self.assertRaises(HarnessError):
                validate_decision(dict(reply='好', strategy='等待', action=action, target='ENG'))

    def test_war_decision_reaches_compiler_without_becoming_hold(self):
        decision = validate_decision(dict(reply='收复曼恩', strategy='收复核心',
                                         action='declare_war', target='ENG'), request_id='war01')
        script = compile_request(_request_for_decision(decision))
        self.assertIn('declare_war_with_cb', script)
        self.assertNotIn('clr_country_flag = llm_diplomacy_locked', script)

    def test_hold_snapshot_does_not_depend_on_mod_effect_loading(self):
        script = compile_request({'id': 'hold01', 'action': 'snapshot'})
        self.assertNotIn('llm_bridge_snapshot = yes', script)
        self.assertIn('export_to_variable', script)
        self.assertIn('EU4LLM|FIELD|live|manpower_raw|', script)


if __name__ == '__main__':
    unittest.main()
