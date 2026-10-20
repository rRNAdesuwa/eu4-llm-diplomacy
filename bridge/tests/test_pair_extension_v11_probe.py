"""Synthetic sparse-memory boundaries only; tests never open a real process."""
from copy import deepcopy
import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from bridge.tests.test_pair_extension_v10_probe import (
    fixture as identity_fixture, BASE, GAME, FRA, TARGET, ROOT_A, ROOT_B,
    RECORDS_A, RECORDS_B, INDEX_A, INDEX_B, OBJ, DATE,
)
from work import probe_pair_extension_v11_1375 as probe

NODE = 0x570000
INVALID = 0x2D2D2D


def fixture(action='warningaction', *, active=False, target='ENG', flow=None):
    mem = identity_fixture(target=target)
    put = mem.write_fixture
    if action in probe.RELATIONS and active:
        flow = probe.flow_for(action, flow)
        aoff, acount, boff, bcount, vt, direction = probe.offsets(action, flow)
        for root, index, other, off, count in ((ROOT_A, INDEX_A, target, aoff, acount), (ROOT_B, INDEX_B, 'FRA', boff, bcount)):
            put(root+off, index); put(root+count, 1, 4)
            put(index, struct.pack('<I4xQ', (probe.HANDLES[other] >> 32)&0xFFFF, OBJ))
        pair = [probe.HANDLES['FRA'], probe.HANDLES[target]]
        if direction == 'reverse': pair.reverse()
        body = bytearray(0x48)
        struct.pack_into('<Q', body, 0, BASE+vt); struct.pack_into('<I', body, 8, 0x165)
        struct.pack_into('<QQi', body, 0x10, *pair, DATE)
        if action == 'transfer_trade_power': struct.pack_into('<i', body, 0x40, 500)
        put(OBJ, body)
    elif action == 'form_coalition':
        put(FRA+0x18F8, probe.HANDLES[target] if active else INVALID)
        put(TARGET+0x1910, struct.pack('<QQIB', NODE if active else 0, NODE if active else 0, int(active), 0))
        if active: put(NODE, struct.pack('<QQQB7x', probe.HANDLES['FRA'], 0, 0, 0))
    elif action in probe.ECONOMIC:
        put(FRA+0xBB0, 100000, 4); put(TARGET+0xBB0, 200000, 4)
        put(RECORDS_A+((probe.HANDLES[target] >> 32)&0xFFFF)*0x48+0x20, 40000, 4)
        put(RECORDS_B+122*0x48+0x20, 50000, 4)
    return mem


def report(mem, action='warningaction', *, target='ENG', flow=None, after=False):
    stamp = '2026-10-08T10:00:01+00:00' if after else '2026-10-08T10:00:00+00:00'
    return {'schema_version': 1, 'kind': 'pair_extension_v11_snapshot', 'profile': probe.PROFILE,
        'static_effect_evidence_sha256': probe.EVIDENCE_SHA256, 'static_extension_evidence_sha256': probe.EXTENSION_SHA256,
        'read_only': True, 'capture_started_at': stamp, 'capture_finished_at': stamp,
        'build': {'sha256': probe.base.LOCAL_SHA256}, 'actor': 'FRA', 'target': target, 'action': action,
        'trade_direction': probe.flow_for(action, flow),
        'source': {'kind': 'live_process', 'pid': 123, 'process_creation_filetime': 134358500000000000,
                   'process_exit_filetime': 0, 'module_base': hex(BASE), 'access_rights': 'QUERY_INFORMATION | VM_READ'},
        'observation': probe.capture(mem, BASE, target, action, flow)}


class ExtensionV11Tests(unittest.TestCase):
    def test_five_relation_families_four_targets_add_and_allowed_cancel(self):
        for action in (*probe.RELATIONS, 'form_coalition'):
            for target in probe.TARGETS:
                with self.subTest(action=action, target=target):
                    before = report(fixture(action, target=target), action, target=target)
                    after = report(fixture(action, active=True, target=target), action, target=target, after=True)
                    result = probe.compare_reports(before, after)
                    self.assertTrue(result['observed_effect'], result)
                    for key in ('execution_verified', 'request_causality_verified', 'ai_acceptance_verified', 'rejection_observed', 'whole_world_unchanged_verified'):
                        self.assertFalse(result[key])
                    before = report(fixture(action, active=True, target=target), action, target=target)
                    after = report(fixture(action, target=target), action, target=target, after=True)
                    self.assertEqual(probe.compare_reports(before, after, 'cancel')['observed_effect'], action != 'warningaction')

    def test_warning_reverse_is_not_outgoing_and_not_a_revocation(self):
        mem = fixture(active=True)
        mem.write_fixture(OBJ+0x10, probe.HANDLES['ENG']); mem.write_fixture(OBJ+0x18, probe.HANDLES['FRA'])
        result = report(mem, after=True)
        self.assertEqual(result['observation']['state']['state'], 'reverse_relation')
        self.assertFalse(probe.compare_reports(report(fixture()), result)['observed_effect'])

    def test_support_treaty_does_not_infer_provider_from_field_order(self):
        mem = fixture('support_independence_action', active=True)
        mem.write_fixture(OBJ+0x10, probe.HANDLES['ENG']); mem.write_fixture(OBJ+0x18, probe.HANDLES['FRA'])
        result = probe.capture(mem, BASE, 'ENG', 'support_independence_action')
        self.assertEqual(result['state']['state'], 'active')
        self.assertEqual(result['state']['object_order'], 'target_first')
        self.assertFalse(result['state']['provider_role_inferred'])

    def test_trade_flow_selects_opposite_indexes_and_exact_object_direction(self):
        for action in probe.TRADE:
            for flow in ('target_to_actor', 'actor_to_target'):
                mem = fixture(action, active=True, flow=flow)
                active = report(mem, action, flow=flow, after=True)
                self.assertEqual(probe.compare_reports(report(fixture(action), action, flow=flow), active)['observed_effect'], flow == 'target_to_actor')
                removed = report(fixture(action), action, flow=flow, after=True)
                self.assertTrue(probe.compare_reports(report(mem, action, flow=flow), removed, 'cancel')['observed_effect'])
                other = 'actor_to_target' if flow == 'target_to_actor' else 'target_to_actor'
                self.assertEqual(probe.capture(mem, BASE, 'ENG', action, other)['state']['state'], 'absent')
                self.assertFalse(probe.compare_reports(report(fixture(action), action, flow=other), active)['observed_effect'])
                pair = [probe.HANDLES['FRA'], probe.HANDLES['ENG']]
                if flow == 'actor_to_target': pair.reverse()
                mem.write_fixture(OBJ+0x10, pair[0]); mem.write_fixture(OBJ+0x18, pair[1])
                self.assertEqual(probe.capture(mem, BASE, 'ENG', action, flow)['status'], 'unknown')

    def test_trade_special_flags_and_unordinary_ratio_do_not_verify(self):
        for action in probe.TRADE:
            mem = fixture(action, active=True)
            mem.write_fixture(OBJ+(0x44 if action == 'transfer_trade_power' else 0x40), 1, 1)
            after = report(mem, action, after=True)
            self.assertEqual(after['observation']['state']['state'], 'special_variant')
            self.assertFalse(probe.compare_reports(report(fixture(action), action), after)['observed_effect'])
        for ratio in (0, -1, 1001):
            mem = fixture('transfer_trade_power', active=True)
            mem.write_fixture(OBJ+0x40, struct.pack('<i', ratio))
            self.assertEqual(probe.capture(mem, BASE, 'ENG', 'transfer_trade_power')['state']['state'], 'unsupported_fraction')

    def test_trade_fraction_expectation_uses_ratio_milli_not_percent(self):
        before = report(fixture('transfer_trade_power'), 'transfer_trade_power')
        after = report(fixture('transfer_trade_power', active=True), 'transfer_trade_power', after=True)
        self.assertTrue(probe.compare_reports(before, after, expected_fraction_milli=500)['observed_effect'])
        for ratio in (50, True, -1, 1001):
            self.assertFalse(probe.compare_reports(before, after, expected_fraction_milli=ratio)['observed_effect'])
        self.assertFalse(probe.compare_reports(report(fixture()), report(fixture(active=True), after=True), expected_fraction_milli=500)['observed_effect'])

    def test_coalition_removed_node_is_not_membership_and_never_resolved(self):
        mem = fixture('form_coalition')
        mem.write_fixture(TARGET+0x1910, struct.pack('<QQIB', NODE, NODE, 1, 1))
        mem.write_fixture(NODE, struct.pack('<QQQB7x', 0xFFFFFFFFFFFFFFFF, 0, 0, 1))
        observed = probe.capture(mem, BASE, 'ENG', 'form_coalition')
        self.assertEqual(observed['state']['state'], 'absent')
        self.assertIsNone(observed['passes'][0]['coalition']['nodes'][0]['member'])

    def test_coalition_count_cycle_tail_prev_duplicate_and_handle_conflict_fail(self):
        changes = ((TARGET+0x1920, 1025, 4), (TARGET+0x1918, NODE+0x100, 8),
                   (NODE+8, NODE, 8), (NODE+0x10, NODE, 8), (NODE+0x18, 2, 1),
                   (NODE, probe.HANDLES['FRA'] ^ (1 << 56), 8), (FRA+0x18F8, INVALID, 8))
        for location, value, size in changes:
            mem = fixture('form_coalition', active=True); mem.write_fixture(location, value, size)
            self.assertEqual(probe.capture(mem, BASE, 'ENG', 'form_coalition')['status'], 'unknown')
        mem = fixture('form_coalition', active=True)
        mem.write_fixture(TARGET+0x1918, NODE+0x20); mem.write_fixture(TARGET+0x1920, 2, 4)
        mem.write_fixture(NODE+0x10, NODE+0x20)
        mem.write_fixture(NODE+0x20, struct.pack('<QQQB7x', probe.HANDLES['FRA'], NODE, 0, 0))
        self.assertEqual(probe.capture(mem, BASE, 'ENG', 'form_coalition')['status'], 'unknown')

    def test_relation_removed_type_vt_generation_duplicate_and_split_indexes_fail(self):
        changes = ((OBJ, BASE+0x1C7FA40, 8), (OBJ+8, 0, 4), (OBJ+0x28, 1, 1),
                   (OBJ+0x18, probe.HANDLES['ENG'] ^ (1 << 56), 8), (INDEX_B+8, OBJ+0x100, 8),
                   (ROOT_A+0x1C4, 4097, 4), (ROOT_B+0x1C4, 0, 4))
        for location, value, size in changes:
            mem = fixture(active=True); mem.write_fixture(location, value, size)
            self.assertEqual(probe.capture(mem, BASE, 'ENG', 'warningaction')['status'], 'unknown')
        mem = fixture(active=True)
        mem.write_fixture(ROOT_A+0x1C4, 2, 4); mem.write_fixture(INDEX_A+16, struct.pack('<I4xQ', 46, OBJ))
        self.assertEqual(probe.capture(mem, BASE, 'ENG', 'warningaction')['status'], 'unknown')

    def test_double_pass_instability_read_budget_and_unreadable_are_unknown(self):
        mem = fixture(active=True); original = mem.read; reads = 0
        def changing(location, size):
            nonlocal reads
            if location == GAME+0x1DD0:
                reads += 1
                if reads == 3: mem.write_fixture(location, DATE+24, 4)
            return original(location, size)
        mem.read = changing
        self.assertEqual(probe.capture(mem, BASE, 'ENG', 'warningaction')['status'], 'unknown')
        mem = fixture(active=True); mem.bytes_read = probe.base.MAX_TOTAL_READ
        self.assertEqual(probe.capture(mem, BASE, 'ENG', 'warningaction')['status'], 'unknown')
        mem = fixture(active=True); del mem.memory[OBJ]
        self.assertEqual(probe.capture(mem, BASE, 'ENG', 'warningaction')['status'], 'unknown')

    def test_gift_requires_exact_paired_delta_expectation_and_same_date(self):
        before = report(fixture('giftaction'), 'giftaction')
        mem = fixture('giftaction'); mem.write_fixture(FRA+0xBB0, 75000, 4); mem.write_fixture(TARGET+0xBB0, 225000, 4)
        after = report(mem, 'giftaction', after=True)
        self.assertTrue(probe.compare_reports(before, after, expected_amount_milli=25000)['observed_effect'])
        for amount in (None, True, 25, -1):
            self.assertFalse(probe.compare_reports(before, after, expected_amount_milli=amount)['observed_effect'])
        mem.write_fixture(TARGET+0xBB0, 224999, 4)
        self.assertFalse(probe.compare_reports(before, report(mem, 'giftaction', after=True), expected_amount_milli=25000)['observed_effect'])
        mem.write_fixture(TARGET+0xBB0, 225000, 4); mem.write_fixture(GAME+0x1DD0, DATE+24, 4)
        self.assertFalse(probe.compare_reports(before, report(mem, 'giftaction', after=True), expected_amount_milli=25000)['observed_effect'])

    def test_favor_gold_uses_target_record_actor_not_reverse_and_exact_cost(self):
        before = report(fixture('trade_favors_for_gold'), 'trade_favors_for_gold')
        mem = fixture('trade_favors_for_gold')
        mem.write_fixture(FRA+0xBB0, 130000, 4); mem.write_fixture(TARGET+0xBB0, 170000, 4)
        mem.write_fixture(RECORDS_B+122*0x48+0x20, 40000, 4)
        after = report(mem, 'trade_favors_for_gold', after=True)
        self.assertTrue(probe.compare_reports(before, after, expected_amount_milli=30000, expected_favors_milli=10000)['observed_effect'])
        for cost in (None, True, 10, 9999):
            self.assertFalse(probe.compare_reports(before, after, expected_amount_milli=30000, expected_favors_milli=cost)['observed_effect'])
        mem.write_fixture(RECORDS_B+122*0x48+0x20, 50000, 4); mem.write_fixture(RECORDS_A+46*0x48+0x20, 30000, 4)
        self.assertFalse(probe.compare_reports(before, report(mem, 'trade_favors_for_gold', after=True), expected_amount_milli=30000, expected_favors_milli=10000)['observed_effect'])

    def test_economic_bounds_and_record_identity_cannot_be_forged(self):
        for loc, val in ((FRA+0xBB0, 1000000001), (RECORDS_B+122*0x48+0x20, 100001)):
            mem = fixture('giftaction'); mem.write_fixture(loc, val, 4)
            self.assertEqual(probe.capture(mem, BASE, 'ENG', 'giftaction')['status'], 'unknown')
        mem = fixture('giftaction'); mem.write_fixture(RECORDS_B+122*0x48+0x10, probe.HANDLES['POR'])
        self.assertEqual(probe.capture(mem, BASE, 'ENG', 'giftaction')['status'], 'unknown')

    def test_insult_is_explicit_unsupported_without_memory_or_process_access(self):
        with patch.object(probe.base, 'ProcessReader', side_effect=AssertionError('must not open')):
            self.assertEqual(probe.capture(None, BASE, 'ENG', 'insultaction')['status'], 'unsupported')
            result = probe.sample_process(123, Path('missing.exe'), 'ENG', 'insultaction')
            self.assertFalse(result['process_opened'])
            self.assertEqual(probe.compare_reports(result, result)['status'], 'unsupported')

    def test_hash_profile_process_world_and_raw_state_binding(self):
        before, after = report(fixture()), report(fixture(active=True), after=True)
        edits = (lambda r:r.update(profile='v10'), lambda r:r.update(static_effect_evidence_sha256='0'*64),
                 lambda r:r['source'].update(process_creation_filetime=1), lambda r:r['build'].update(sha256='0'*64),
                 lambda r:r['observation']['state'].update(state='absent'), lambda r:r.update(trade_direction='actor_to_target'))
        for edit in edits:
            altered = deepcopy(after); edit(altered)
            self.assertFalse(probe.compare_reports(before, altered)['observed_effect'])
        self.assertFalse(probe.compare_reports(after, before)['observed_effect'])
        for active in (False, True):
            difference = probe.compare_reports(report(fixture(active=active)), report(fixture(active=active), after=True))
            self.assertFalse(difference['observed_effect']); self.assertFalse(difference['rejection_observed'])

    def test_offline_cli_and_create_new_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); before, after, out = (folder/n for n in ('b.json','a.json','out.json'))
            before.write_text(json.dumps(report(fixture())), encoding='utf-8')
            after.write_text(json.dumps(report(fixture(active=True), after=True)), encoding='utf-8')
            args = ['compare','--before',str(before),'--after',str(after),'--direction','positive','--output',str(out)]
            with patch.object(probe.base, 'ProcessReader', side_effect=AssertionError('must not open')), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(probe.main(args), 0)
                saved = out.read_bytes(); self.assertEqual(probe.main(args), 2); self.assertEqual(out.read_bytes(), saved)

    def test_exact_static_evidence_hash_and_no_execution_promotion(self):
        for name, sha in (('native-pair-extension-effects-v11-1375.json',probe.EVIDENCE_SHA256), ('native-pair-extension-v11-1375.json',probe.EXTENSION_SHA256)):
            raw = (probe.ROOT/'work/reports'/name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), sha)
            data = json.loads(raw); self.assertFalse(data['runtime_verified']); self.assertFalse(data['execution_verified'])


if __name__ == '__main__': unittest.main()
