from __future__ import annotations

import contextlib
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile

from work import inspect_diplomacy_save as save


FIXTURE = b'''EU4txt
date=1444.11.11 player="FRA"
savegame_version={first=1 second=37 third=5}
countries={FRA={human=yes subjects={ORL}
 diplomats={envoy={id=0 type=3 name="a \\"quote\\" { } #" task="improve_relation" target="ENG"}}
 active_relations={ENG={trust_value=38 opinion={modifier="improved_relation" current_opinion=5} opinion={modifier="other" current_opinion=-2}} POR={attitude="neutral"} CAS={spy_network=99}}
 spy_networks={ENG={value=12.5}} unrelated_secret="omit"} ENG={diplomats={} active_relations={FRA={trust_value=40}}}
POR={active_relations={FRA={attitude="neutral"}}} CAS={diplomats={envoy={id=99}}}}
other_container={FRA={diplomats={envoy={id=999}}}}
diplomacy={royal_marriage={first="FRA" second="ENG" start_date=1444.1.1}
 guarantee={first="POR" second="FRA"}
 dependency={first="FRA" second="ORL" subject_type="appanage"}
 alliance={first="CAS" second="ARA"}
 # fake_relation={first="FRA"}
 unknown_new_relation={parties={FRA ENG} note="future field"}}
'''


def children(block, key):
    return [entry for entry in block["entries"] if entry["key"] == key]


class StreamingDiplomacySaveTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write(self, raw=FIXTURE, name="fixture.eu4"):
        path = self.root / name
        path.write_bytes(raw)
        return path

    def test_selected_state_preserves_directions_repeated_records_and_raw_evidence(self):
        path = self.write()
        report = save.inspect_save(path)
        self.assertTrue(report["read_only"])
        self.assertEqual(report["evidence_scope"], "serialized_state_only")
        self.assertFalse(report["runtime_effects_verified"])
        fra = report["countries"]["FRA"]
        relation = fra["relations"]["ENG"]["blocks"][0]
        self.assertEqual(children(relation, "trust_value")[0]["value"], "38")
        self.assertEqual(len(children(relation, "opinion")), 2)
        reverse = report["countries"]["ENG"]["relations"]["FRA"]["blocks"][0]
        self.assertEqual(children(reverse, "trust_value")[0]["value"], "40")
        envoy = children(fra["diplomats"]["blocks"][0], "envoy")[0]
        self.assertEqual(children(envoy, "task")[0]["value"], "improve_relation")
        self.assertEqual(children(envoy, "target")[0]["value"], "ENG")
        self.assertEqual(children(envoy, "name")[0]["raw_value"], '"a \\"quote\\" { } #"')
        self.assertNotIn("CAS", fra["relations"])
        self.assertNotIn("unrelated_secret", [entry["key"] for entry in fra["fields"]])
        self.assertIn("unrelated_secret", fra["field_inventory"])
        self.assertEqual([record["key"] for record in report["global_diplomacy"]["records"]],
                         ["royal_marriage", "guarantee", "dependency", "unknown_new_relation"])
        self.assertEqual(report["global_diplomacy"]["record_counts_scanned"]["alliance"], 1)
        position = children(relation, "trust_value")[0]["byte_offset"]
        self.assertEqual(FIXTURE[position:position + 2], b"38")
        self.assertEqual(report["source"]["sha256"], hashlib.sha256(FIXTURE).hexdigest().upper())
        self.assertEqual(path.read_bytes(), FIXTURE)

    def test_missing_fields_and_empty_block_are_distinct_without_inventing_absence(self):
        report = save.inspect_save(self.write(b"EU4txt\ncountries={FRA={diplomats={}} ENG={}}"))
        self.assertEqual(report["countries"]["FRA"]["diplomats"]["status"], "found")
        self.assertEqual(report["countries"]["ENG"]["diplomats"]["status"], "not_found")
        self.assertEqual(report["countries"]["POR"]["status"], "not_found")
        self.assertEqual(report["countries"]["FRA"]["relations"]["ENG"]["status"], "not_found")
        self.assertFalse(report["global_diplomacy"]["container_found"])
        self.assertTrue(any("does not prove" in line for line in report["limitations"]))

    def test_optional_effect_fields_are_selected_and_keep_repeated_modifiers(self):
        path = self.write(b'EU4txt countries={FRA={treasury=12 modifier={modifier="a"} modifier={modifier="b"} flags={x=1445.1.1} rival={country="BUR"} rival={country="ENG"} coalition_target="SAV"} ENG={manpower=7} CAS={treasury=99}}')
        ordinary = save.inspect_save(path)
        effects = save.inspect_save(path, effect_fields=True)
        self.assertEqual(ordinary['countries']['FRA']['fields'], [])
        fields = effects['countries']['FRA']['fields']
        self.assertEqual([x['key'] for x in fields], ['treasury', 'modifier', 'modifier', 'flags', 'rival', 'rival', 'coalition_target'])
        self.assertEqual(effects['countries']['ENG']['fields'][0]['value'], '7')
        self.assertNotIn('CAS', effects['countries'])
        self.assertFalse(effects['runtime_effects_verified'])

    def test_zip_streams_only_gamestate_and_matches_plain_semantics(self):
        path = self.root / "compressed.eu4"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("gamestate", FIXTURE)
            archive.writestr("meta", b"unused metadata")
            archive.writestr("../not_extracted", b"ignored")
        zipped = save.inspect_save(path)
        plain = save.inspect_save(self.write())
        for field in ("countries", "metadata", "global_diplomacy"):
            self.assertEqual(zipped[field], plain[field])
        self.assertEqual(zipped["source"]["format"], "zip_gamestate")
        self.assertEqual(zipped["source"]["gamestate_sha256"], plain["source"]["sha256"])
        self.assertEqual(zipped["source"]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest().upper())
        self.assertFalse((self.root.parent / "not_extracted").exists())

    def test_binary_save_rejected_plain_and_in_zip(self):
        with self.assertRaisesRegex(save.SaveError, "EU4bin"):
            save.inspect_save(self.write(b"EU4bin\x00\x01"))
        path = self.root / "binary.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("gamestate", b"EU4bin\x00\x01")
        with self.assertRaisesRegex(save.SaveError, "EU4bin"):
            save.inspect_save(path)

    def test_duplicate_missing_or_oversized_zip_directory_rejected(self):
        for names in (("meta",), ("gamestate", "gamestate"), tuple(f"item{i}" for i in range(129))):
            with self.subTest(names=names[:2]):
                path = self.root / "invalid.zip"
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    with zipfile.ZipFile(path, "w") as archive:
                        for name in names:
                            archive.writestr(name, FIXTURE)
                with self.assertRaises(save.SaveError):
                    save.inspect_save(path)

    def test_large_unselected_country_is_skipped_with_chunk_bounded_reads(self):
        class GuardedStream(io.BytesIO):
            def read(self, count=-1):
                if not 0 <= count <= save.CHUNK:
                    raise AssertionError(f"unbounded read {count}")
                return super().read(count)
        raw = b"EU4txt\ncountries={CAS={" + b"unrelated=0\n" * 30000 + b"} FRA={diplomats={}}}"
        reader = save.BoundedReader(GuardedStream(raw))
        report = save.extract(reader, "FRA", ("ENG",))
        self.assertGreater(reader.count, save.MAX_CAPTURE)
        self.assertLess(report["selected_serialized_bytes"], 100)
        self.assertEqual(report["countries"]["FRA"]["diplomats"]["status"], "found")

    def test_chunk_boundaries_multiline_quotes_comments_and_byte_mapping(self):
        # Very short chunks put keys, quotes, escapes and braces across reads.
        raw = b'EU4txt\n# ignored { "\ncountries={FRA={diplomats={envoy={name="a\n\\"b\\"\xe7}"}}}}'
        with mock.patch.object(save, "CHUNK", 7):
            report = save.inspect_save(self.write(raw))
        envoy = children(report["countries"]["FRA"]["diplomats"]["blocks"][0], "envoy")[0]
        name = children(envoy, "name")[0]
        self.assertEqual(name["value"], 'a\n\\"b\\"\u00e7}')
        self.assertEqual(raw[name["byte_offset"]:name["byte_offset"] + 1], b'"')

    def test_unclosed_blocks_quotes_and_invalid_assignments_fail_closed(self):
        for tail in (b"countries={FRA={}", b'key="unterminated', b"key=}", b"}", b"countries={FRA={} FRA={}}"):
            with self.subTest(tail=tail), self.assertRaises(save.SaveError):
                save.inspect_save(self.write(b"EU4txt\n" + tail))

    def test_stream_token_depth_capture_and_node_budgets(self):
        cases = [
            ("MAX_STREAM", 24, b"EU4txt\n" + b"x=0\n" * 12),
            ("MAX_TOKEN", 10, b'EU4txt\nx="' + b"x" * 11 + b'"'),
            ("MAX_DEPTH", 2, b"EU4txt\na={b={c={}}}"),
            ("MAX_CAPTURE", 25, b"EU4txt\ncountries={FRA={diplomats={name=abcdefghijklmnop}}}"),
            ("MAX_CAPTURE_NODES", 2, b"EU4txt\ncountries={FRA={diplomats={a=1 b=2}}}"),
            ("MAX_RETAINED_NODES", 2, b"EU4txt\ncountries={FRA={diplomats={a=1 b=2}}}"),
        ]
        for setting, limit, raw in cases:
            with self.subTest(setting=setting), mock.patch.object(save, setting, limit), self.assertRaises(save.SaveError):
                save.inspect_save(self.write(raw))

    def test_targets_are_validated_and_missing_custom_country_stays_unknown(self):
        path = self.write()
        for actor, targets in (("../", ("ENG",)), ("FRA", ("FRA",)), ("FRA", ()), ("FRA", ("bad",))):
            with self.subTest(actor=actor, targets=targets), self.assertRaises(save.SaveError):
                save.inspect_save(path, actor, targets)
        report = save.inspect_save(path, "FRA", ("D00",))
        self.assertEqual(report["countries"]["D00"]["status"], "not_found")

    def test_cli_cannot_overwrite_save_and_parse_failure_does_not_write_report(self):
        source = self.write()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            save.main(["--save", str(source), "--output", str(source)])
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(source.read_bytes(), FIXTURE)
        bad = self.write(b"EU4txt\nbroken={", "bad.eu4")
        output = self.root / "report.json"
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            save.main(["--save", str(bad), "--output", str(output)])
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
