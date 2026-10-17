from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from work.inspect_peace_treaty_save import (
    TreatySaveParseError,
    build_payload,
    parse_war_reparations_block,
    scan_save,
)


GSTATE = """EU4txt
date=1455.5.12
player="POR"
war_reparations={
 first="FRA"
 second="ENG"
 end_date=1458.5.12
 start_date=1448.5.12
}
war_reparations={
 first="HAM"
 second="SWE"
 end_date=1458.8.14
 start_date=1448.8.14
}
"""


class PeaceTreatySaveTests(unittest.TestCase):
    def test_streams_pair_and_preserves_serialized_roles_and_dates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save = Path(directory) / "sample.eu4"
            save.write_text(GSTATE, encoding="utf-8")

            snapshot = scan_save(save, "FRA", "ENG")

            self.assertEqual(snapshot["parse"]["war_reparations_block_count"], 2)
            self.assertTrue(snapshot["query"]["exact_pair_present"])
            self.assertEqual(snapshot["query"]["matching_count"], 1)
            record = snapshot["query"]["matching_records"][0]
            self.assertEqual(record["payer"], "FRA")
            self.assertEqual(record["claimant"], "ENG")
            self.assertEqual(record["role_mapping"]["payer"]["serialized_field"], "first")
            self.assertEqual(record["role_mapping"]["claimant"]["serialized_field"], "second")
            self.assertEqual(record["start_date"], "1448.5.12")
            self.assertEqual(record["end_date"], "1458.5.12")
            self.assertEqual(record["date_status"]["status"], "active")
            self.assertEqual(record["fields"]["first"], '"FRA"')
            self.assertEqual(record["line_start"], 4)
            self.assertEqual(record["line_end"], 9)

    def test_reverse_pair_is_distinguished_and_zip_is_streamed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save = root / "sample.eu4"
            with zipfile.ZipFile(save, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("gamestate", GSTATE)

            reverse = scan_save(save, "ENG", "FRA")
            self.assertEqual(reverse["source"]["container"], "zip")
            self.assertFalse(reverse["query"]["exact_pair_present"])
            self.assertTrue(reverse["query"]["reverse_pair_present"])
            payload = build_payload(save, "FRA", "ENG")
            self.assertEqual(payload["tool"]["serialized_role_mapping"]["payer"], "first")
            self.assertEqual(payload["save"]["query"]["matching_count"], 1)

    def test_missing_pair_and_incomplete_block_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save = Path(directory) / "sample.eu4"
            save.write_text(
                "EU4txt\ndate=1455.5.12\nwar_reparations={ first=FRA\n",
                encoding="utf-8",
            )
            snapshot = scan_save(save, "FRA", "ENG")
            self.assertFalse(snapshot["query"]["exact_pair_present"])
            self.assertFalse(snapshot["parse"]["brace_balance_ok"])
            self.assertIn("record_1:war_reparations_capture_incomplete", snapshot["parse"]["unknown"])

    def test_block_parser_retains_raw_field_mapping(self) -> None:
        record = parse_war_reparations_block(
            'war_reparations={ first="FRA" second="ENG" start_date=1.1.1 end_date=2.1.1 }',
            line_start=10,
            line_end=10,
            bytes_captured=82,
            bytes_seen=82,
            complete=True,
            scope_depth=1,
            save_date="1.6.1",
            index=1,
        )
        self.assertEqual(record["payer"], "FRA")
        self.assertEqual(record["claimant"], "ENG")
        self.assertEqual(record["date_status"]["status"], "active")

    def test_same_country_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save = Path(directory) / "sample.eu4"
            save.write_text(GSTATE, encoding="utf-8")
            with self.assertRaisesRegex(TreatySaveParseError, "must differ"):
                scan_save(save, "FRA", "FRA")


if __name__ == "__main__":
    unittest.main()
