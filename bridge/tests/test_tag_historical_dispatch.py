"""Cross-version dispatch exclusions fail before runtime or publication."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bridge.tag_command_backend import ROOT
from bridge.tag_test_policy import HISTORICAL_DISPATCH_POLICY, historical_dispatch_blocks
from bridge.tests import test_tag_command_backend as fixtures


class HistoricalDispatchTests(unittest.TestCase):
    def test_original_receipts_block_both_actions(self):
        self.assertEqual(historical_dispatch_blocks(),
            {'offer_fleet_basing_rights', 'revoke_fleet_basing_rights'})

    def copy_evidence(self, root):
        raw = (ROOT/HISTORICAL_DISPATCH_POLICY).read_bytes()
        target = root/HISTORICAL_DISPATCH_POLICY
        target.parent.mkdir(parents=True)
        target.write_bytes(raw)
        policy = json.loads(raw)
        for name in policy['source_pins']:
            target = root/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT/name).read_bytes())
        return policy

    def test_changed_old_source_cannot_reopen_action(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = self.copy_evidence(root)
            source = root/policy['evidence'][1]['source']
            source.write_bytes(source.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError, 'Historical dispatch evidence changed'):
                historical_dispatch_blocks(root)

    def test_missing_policy_cannot_reopen_action(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(OSError):
                historical_dispatch_blocks(Path(directory))

    def test_removed_policy_action_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_evidence(root)
            path = root/HISTORICAL_DISPATCH_POLICY
            policy = json.loads(path.read_bytes())
            policy['blocked_actions'] = []
            path.write_text(json.dumps(policy), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Historical dispatch policy changed'):
                historical_dispatch_blocks(root)

    def test_changed_pair_and_id_block_before_runtime_or_reservation(self):
        fixture = fixtures.TagCommandTests(methodName='runTest')
        try:
            fixture.setUp()
            command = dict(fixture.command, action='offer_fleet_basing_rights',
                           actor='ENG', target='SCO', request_id='different-version-pair-id')
            with patch.object(fixture.backend, 'verify', side_effect=AssertionError('runtime boundary')):
                with self.assertRaisesRegex(ValueError, 'Historically dispatched action'):
                    fixture.backend.publish(fixture.identity, [command], test_only=True)
            self.assertEqual(fixture.runtime.checks, [])
            self.assertFalse((fixture.directory/'publisher.lock').exists())
            self.assertFalse((fixture.directory/'1.request').exists())
            self.assertFalse((fixture.path/'isolated-development-history').exists())
        finally:
            fixture.doCleanups()


if __name__ == '__main__':
    unittest.main()
