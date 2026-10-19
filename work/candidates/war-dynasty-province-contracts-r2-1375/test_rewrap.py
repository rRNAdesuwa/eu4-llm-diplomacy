"""Pure ownership-state regressions; no engine functions or real addresses used."""
from copy import deepcopy
from dataclasses import asdict
import unittest
from unittest.mock import patch
import contract as c
from test_contract import FRA,ENG,DATE,PARAMS,TABLE


def make(name):
    return c.OwnedModel(name,c.initialize(name,FRA,ENG,DATE,deepcopy(PARAMS[name]),TABLE))


class OneShotRegressions(unittest.TestCase):
    def test_exact_four_original_counterexamples_rejected_without_new_clone(self):
        for name in c.PROFILES:
            with self.subTest(name=name):
                model=make(name);model.wrap(DATE);first=model.command_clone;model.destroy_command()
                before=asdict(model)
                with patch.object(c,'clone',side_effect=AssertionError('second clone forbidden')) as clone:
                    with self.assertRaisesRegex(ValueError,'single wrapper'):model.wrap(DATE)
                clone.assert_not_called()
                self.assertEqual(asdict(model),before)
                self.assertIs(model.command_clone,first)
                self.assertFalse(model.command_present)
                self.assertTrue(model.clone_destroyed)
                self.assertTrue(model.ever_wrapped)
                model.destroy_original()

    def test_first_success_sets_latch_for_each_family(self):
        for name in c.PROFILES:
            model=make(name);self.assertFalse(model.ever_wrapped);model.wrap(DATE+24)
            self.assertTrue(model.ever_wrapped);self.assertTrue(model.command_present)
            self.assertIsNot(model.original,model.command_clone)
            self.assertEqual(c.get(model.command_clone,0x2c,'i'),DATE+24)
            self.assertEqual(c.get(model.original,0x2c,'i'),DATE)

    def test_original_first_cleanup_is_still_possible(self):
        for name in c.PROFILES:
            model=make(name);model.wrap(DATE);model.destroy_original();model.destroy_command()
            self.assertTrue(model.ever_wrapped)
            with self.assertRaises(ValueError):model.wrap(DATE)

    def test_rejected_live_second_wrapper_preserves_owned_command_cleanup(self):
        for name in c.PROFILES:
            model=make(name);model.wrap(DATE);before=asdict(model)
            with self.assertRaises(ValueError):model.wrap(DATE+24)
            self.assertEqual(asdict(model),before)
            model.destroy_command();model.destroy_original()

    def test_invalid_date_before_first_wrapper_has_no_allocation_or_latch(self):
        for name in c.PROFILES:
            for value in (True,0,-1,1.0,2**31):
                model=make(name);before=asdict(model)
                with patch.object(c,'clone',side_effect=AssertionError('invalid date allocation')) as clone:
                    with self.assertRaises(ValueError):model.wrap(value)
                clone.assert_not_called();self.assertEqual(asdict(model),before)

    def test_unknown_after_first_wrapper_cannot_rearm_or_cleanup(self):
        for name in c.PROFILES:
            model=make(name);model.wrap(DATE);model.exception();before=asdict(model)
            for op in (model.destroy_command,model.destroy_original,lambda:model.wrap(DATE)):
                with self.assertRaises(ValueError):op()
                self.assertEqual(asdict(model),before)

    def test_original_destroyed_before_wrap_is_rejected(self):
        for name in c.PROFILES:
            model=make(name);model.destroy_original();before=asdict(model)
            with self.assertRaises(ValueError):model.wrap(DATE)
            self.assertEqual(asdict(model),before)

    def test_no_family_gains_sender_or_gate_permission(self):
        for name in c.PROFILES:
            model=make(name);model.wrap(DATE)
            with self.assertRaises(ValueError):model.send()
            self.assertIs(c.gate_observation(True,True,True)['send_permission'],False)


if __name__=='__main__':unittest.main()
