"""Small offline tests for the bounded province-effect probe."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

try:
    from work.probe_peace_province_effects import (
        _top_level_province_fields,
        parse_requested_ids,
        scan_baseline_save,
    )
except ModuleNotFoundError:
    from probe_peace_province_effects import (
        _top_level_province_fields,
        parse_requested_ids,
        scan_baseline_save,
    )


class ProvinceEffectProbeTests(unittest.TestCase):
    def test_requested_id_count_and_range(self) -> None:
        self.assertEqual(parse_requested_ids(["1", "0x2"]), [1, 2])
        with self.assertRaises(Exception):
            parse_requested_ids([])
        with self.assertRaises(Exception):
            parse_requested_ids([str(index) for index in range(17)])
        with self.assertRaises(Exception):
            parse_requested_ids(["1", "1"])

    def test_top_level_owner_controller_fields(self) -> None:
        fields = _top_level_province_fields([
            "1={\n",
            "\towner=FRA\n",
            "\tcontroller=ENG\n",
            "\tmodifier={ owner=NOPE }\n",
            "}\n",
        ])
        self.assertEqual(fields, {"owner": "FRA", "controller": "ENG"})

    def test_streaming_save_scan_keeps_differing_rows_only(self) -> None:
        gamestate = (
            "provinces={\n"
            "1={ owner=FRA controller=ENG }\n"
            "2={ owner=FRA controller=FRA }\n"
            "}\n"
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.eu4"
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("gamestate", gamestate)
            report = scan_baseline_save(path)
        self.assertTrue(report["found"])
        self.assertTrue(report["provinces_block_complete"])
        self.assertEqual(report["different_owner_controller_count"], 1)
        candidate = report["candidates"][0]
        self.assertEqual(candidate["province_key"], 1)
        self.assertEqual(candidate["owner_raw"], "FRA")
        self.assertEqual(candidate["controller_raw"], "ENG")


if __name__ == "__main__":
    unittest.main()
