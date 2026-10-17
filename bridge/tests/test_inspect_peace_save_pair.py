from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from work.inspect_peace_save_pair import (
    PeaceSaveParseError,
    build_payload,
    parse_province_ids,
    render_report,
)


BASELINE = """EU4txt
date=1455.1.5
player=\"POR\"
countries={
 FRA={
  treasury=22.759
  ai={ treasury=500.000 }
 }
 ENG={
  treasury=52.082
 }
}
provinces={
-177={
 owner=\"ENG\"
 controller=\"ENG\"
 previous_controller=\"REB\"
 cores={ ENG FRA }
}
-187={
 owner=\"PRO\"
 controller=\"PRO\"
 cores={ PRO }
}
}
diplomacy={
 active_war={
  original_attacker=\"FRA\"
  original_defender=\"ENG\"
  action=1455.1.1
  attackers={ FRA }
  defenders={ ENG }
 }
}
"""

RESULT = BASELINE.replace("treasury=22.759", "treasury=32.759", 1).replace(
    'owner="ENG"\n controller="ENG"',
    'owner="FRA"\n controller="FRA"',
    1,
).replace("date=1455.1.5", "date=1455.2.5", 1)


class InspectPeaceSavePairTests(unittest.TestCase):
    def test_streamed_plain_pair_preserves_fields_and_deltas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = root / "before.eu4"
            after = root / "after.eu4"
            before.write_text(BASELINE, encoding="utf-8")
            after.write_text(RESULT, encoding="utf-8")

            payload = build_payload(before, after, "FRA", "ENG", (177, 187))

            self.assertEqual(payload["before"]["metadata"]["date"], "1455.1.5")
            self.assertEqual(payload["before"]["metadata"]["player"], "POR")
            self.assertEqual(payload["before"]["countries"]["FRA"]["treasury"]["raw"], "22.759")
            self.assertEqual(payload["comparison"]["countries"]["FRA"]["treasury"]["delta"], "10.000")
            province = payload["comparison"]["provinces"]["177"]
            self.assertTrue(province["changed"])
            self.assertEqual(province["field_changes"]["owner"]["before"]["value"], "ENG")
            self.assertEqual(province["field_changes"]["owner"]["after"]["value"], "FRA")
            self.assertEqual(payload["before"]["provinces"]["177"]["serialized_id"], "-177")
            self.assertEqual(payload["before"]["provinces"]["177"]["fields"]["cores"]["tags"], ["ENG", "FRA"])
            self.assertTrue(payload["before"]["war_scan"]["matching_active_wars"])
            self.assertIn("treasury", render_report(payload))

    def test_zip_gamestate_and_bounded_id_parser(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = root / "before.eu4"
            after = root / "after.eu4"
            with zipfile.ZipFile(before, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("gamestate", BASELINE)
            after.write_text(RESULT, encoding="utf-8")

            payload = build_payload(before, after, "FRA", "ENG", parse_province_ids(["177,187"], []))
            self.assertEqual(payload["before"]["source"]["container"], "zip")
            self.assertEqual(payload["before"]["provinces"]["187"]["fields"]["owner"]["value"], "PRO")
            self.assertEqual(parse_province_ids(["177", "177,187"], [187]), (177, 187))

    def test_province_id_bound_is_explicit(self) -> None:
        with self.assertRaisesRegex(PeaceSaveParseError, "at most 16"):
            parse_province_ids([",".join(str(index) for index in range(17))], [])


if __name__ == "__main__":
    unittest.main()
