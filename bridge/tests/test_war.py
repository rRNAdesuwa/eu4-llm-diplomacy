"""War authorization boundaries and result-based receipts."""
import unittest

from bridge.compiler import ActionRequest, RequestError, compile_request
from bridge.protocol import parse_log


class AuthorizedWarTests(unittest.TestCase):
    def test_locked_war_has_guards_and_only_marks_success_after_result(self):
        script = compile_request({'id': 'war01', 'action': 'declare_war', 'target': 'ENG'})
        for guard in ('ai = yes', 'is_subject = no', 'has_country_flag = llm_diplomacy_locked',
                      'NOT = { war_with = ENG }', 'NOT = { truce_with = ENG }',
                      'NOT = { alliance_with = ENG }',
                      'has_casus_belli = { type = cb_core target = ENG }',
                      '177 = { owned_by = ENG is_core = FRA }',
                      'NOT = { has_country_flag = llm_req_war01 }'):
            self.assertIn(guard, script)
        effect = script.index('declare_war_with_cb =')
        result = script.index('limit = { war_with = ENG has_country_flag')
        mark = script.index('set_country_flag = llm_req_war01')
        ack = script.index('EU4LLM|ACK|war01|applied')
        self.assertLess(effect, result)
        self.assertLess(result, mark)
        self.assertLess(mark, ack)
        self.assertEqual(script.count('declare_war_with_cb ='), 1)
        self.assertNotIn('clr_country_flag', script)
        self.assertNotIn('set_country_flag = llm_diplomacy_locked', script)
        self.assertEqual(script.count('{'), script.count('}'))

    def test_untrusted_war_parameters_and_targets_are_rejected(self):
        invalid = [
            {'id': 'war01', 'action': 'declare_war'},
            {'id': 'war01', 'action': 'declare_war', 'target': 'POR'},
            {'id': 'war01', 'action': 'declare_war', 'target': 'ENG', 'casus_belli': 'cb_core'},
            {'id': 'war01', 'action': 'declare_war', 'target': 'ENG', 'war_goal_province': 177},
            {'id': 'war01', 'action': 'declare_war', 'target': 'ENG } log = hacked'},
        ]
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(RequestError):
                compile_request(raw)
        with self.assertRaises(RequestError):
            ActionRequest('war01', 'declare_war', 'FRA')

    def test_diagnostics_do_not_break_ack_parser(self):
        parsed = parse_log('EU4LLM_DIAG|war01|locked_war_effect_entered\n'
                           'EU4LLM|ACK|war01|applied\n')
        self.assertEqual(parsed.acks[0].status, 'applied')


if __name__ == '__main__':
    unittest.main()
