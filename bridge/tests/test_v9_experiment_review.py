"""Small negative controls for the fixed offline reviewer; no live operations."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from work import verify_v9_experiment_1375 as review


class V9ReviewTests(unittest.TestCase):
    def saved(self):
        return {"parsed_complete": True, "read_only": True, "evidence_scope": "serialized_state_only",
                "runtime_effects_verified": False, "actor": "FRA", "targets": ["NAV"],
                "metadata": {"date": {"value": "1444.11.20"}, "player": {"value": "FRA"}, "multi_player": {"value": "no"}},
                "global_diplomacy": {"container_found": True, "record_counts_scanned": {"dependency": 1}, "records": []},
                "countries": {actor: {"status": "found", "active_relations_container_found": True,
                    "field_inventory": [], "fields": [], "relations": {target: {"status": "found", "blocks": [
                        {"entries": [{"key": "truce", "value": "yes"}]}]}}} for actor, target in (("FRA", "NAV"), ("NAV", "FRA"))}}

    def fixture(self):
        sample = {"live": {"pid": review.PID, "creation": review.CREATION, "world_cookie": review.WORLD,
                           "raw_date": review.INITIAL_DATE, "player_handle": hex(review.fixture.HANDLES["FRA"])},
                  "countries": {tag: {"handle": hex(handle), "overlord": "0x2d2d2d"} for tag, handle in review.fixture.HANDLES.items()},
                  "relations": {key: {"alliance_count": 0, "entries": [], "matching_alliance": False,
                                      "truce_flags": 1, "active_truce_bit0": True} for key in ("FRA->NAV", "NAV->FRA")}}
        return {"schema": "fixed_fixture_pair_v9_1375_observation_v1", "read_only": True,
                "layout_evidence_sha256": review.fixture.EVIDENCE_SHA, "consistent": True,
                "atomic_snapshot": False, "request_causality_verified": False,
                "nav_independent": True, "bilateral_no_alliance": True, "bilateral_no_truce": False,
                "passes": [sample, deepcopy(sample)]}

    def verify_fixture(self, record):
        return review.fixture_state(record, pid=review.PID, creation=review.CREATION,
            world=review.WORLD, date=review.INITIAL_DATE, independent=True, truce=True)

    def test_saved_absence_requires_complete_selected_scan_and_bilateral_truce(self):
        result = review.selected_save_state(self.saved())
        self.assertTrue(result["dependency_absent"])
        mutations = [lambda x: x.update(parsed_complete=False),
                     lambda x: x["global_diplomacy"].update(container_found=False),
                     lambda x: x["global_diplomacy"].update(record_counts_scanned={}),
                     lambda x: x["countries"]["NAV"].update(status="not_found"),
                     lambda x: x["countries"]["NAV"]["relations"]["FRA"].update(blocks=[]),
                     lambda x: x["countries"]["NAV"]["relations"]["FRA"]["blocks"][0]["entries"].clear(),
                     lambda x: x["countries"]["NAV"]["field_inventory"].append("overlord"),
                     lambda x: x["metadata"]["date"].update(value="1444.11.19")]
        for mutation in mutations:
            row = self.saved()
            mutation(row)
            with self.assertRaises(ValueError):
                review.selected_save_state(row)

    def test_dependency_in_either_direction_invalidates_saved_cancellation(self):
        for first, second in (("FRA", "NAV"), ("NAV", "FRA")):
            row = self.saved()
            row["global_diplomacy"]["records"].append({"key": "dependency", "entries": [
                {"key": "first", "value": first}, {"key": "second", "value": second}]})
            with self.assertRaises(ValueError):
                review.selected_save_state(row)

    def test_fixture_report_summary_cannot_hide_raw_overlord_truce_or_alliance(self):
        self.verify_fixture(self.fixture())
        mutations = [lambda x: x["countries"]["NAV"].update(overlord=hex(review.fixture.HANDLES["FRA"])),
                     lambda x: x["countries"]["NAV"].update(handle="0x100007a00415246"),
                     lambda x: x["relations"]["NAV->FRA"].update(truce_flags=0),
                     lambda x: x["relations"]["FRA->NAV"].update(alliance_count=1, entries=[{"slot": 188}]),
                     lambda x: x["live"].update(creation=review.RELOAD_CREATION)]
        for mutation in mutations:
            row = self.fixture()
            mutation(row["passes"][0])
            row["passes"][1] = deepcopy(row["passes"][0])
            with self.assertRaises(ValueError):
                self.verify_fixture(row)

    def test_two_pass_and_overclaim_rejections(self):
        row = self.fixture()
        row["passes"][1]["live"]["raw_date"] += 1
        with self.assertRaises(ValueError):
            self.verify_fixture(row)
        row = self.fixture()
        row["request_causality_verified"] = True
        with self.assertRaises(ValueError):
            self.verify_fixture(row)

    def test_exact_log_prefix_and_full_stopped_hash_are_both_required(self):
        frames = [{"event": "research_frame", "raw_date": date} for date in (56457168, review.FINAL_DATE)]
        first = (json.dumps(frames[0]) + "\n").encode()
        whole = first + (json.dumps(frames[1]) + "\n").encode()
        statuses = [{"log_sha256": hashlib.sha256(first).hexdigest(), "latest_frame": frames[0]}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.jsonl"
            path.write_bytes(whole)
            with patch.object(review, "LOG_BYTES", len(whole)), patch.object(review, "LOG_SHA", hashlib.sha256(whole).hexdigest()):
                self.assertEqual(list(review.verify_prefixes(path, statuses).values()), [len(first)])
                bad = deepcopy(statuses)
                bad[0]["latest_frame"] = frames[1]
                with self.assertRaises(ValueError):
                    review.verify_prefixes(path, bad)
                path.write_bytes(whole + b'{}\n')
                with self.assertRaises(ValueError):
                    review.verify_prefixes(path, statuses)


if __name__ == "__main__":
    unittest.main()
