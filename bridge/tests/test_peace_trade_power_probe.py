from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from work.inspect_peace_treaty_save import scan_save
from work.probe_peace_effect_state import (
    ProbeError,
    TRADE_POWER_RELATION_DISCRIMINATOR,
    TRADE_POWER_RELATION_VTABLE_RVA,
    _country_lookup_entry,
    _read_trade_power_state,
)


BASE = 0x140000000
SOURCE_POINTER = 0x200000
BENEFICIARY_POINTER = 0x300000
ROWS = 0x400000
OWNER = 0x500000
VECTOR = 0x600000
TREATY = 0x700000
SOURCE_SLOT = 3
BENEFICIARY_SLOT = 7
SOURCE_HANDLE = (SOURCE_SLOT << 32) | 0x111111
BENEFICIARY_HANDLE = (BENEFICIARY_SLOT << 32) | 0x222222


def _entries() -> tuple[dict[str, object], dict[str, object]]:
    return (
        {
            "tag": "KNI",
            "pointer": SOURCE_POINTER,
            "handle": SOURCE_HANDLE,
            "slot": SOURCE_SLOT,
        },
        {
            "tag": "VEN",
            "pointer": BENEFICIARY_POINTER,
            "handle": BENEFICIARY_HANDLE,
            "slot": BENEFICIARY_SLOT,
        },
    )


def _memory(*, present: bool = True, start: int = 1445_1000) -> tuple[dict[int, int], dict[int, int]]:
    qwords: dict[int, int] = {
        SOURCE_POINTER + 0x1510: ROWS,
        ROWS + BENEFICIARY_SLOT * 0x48: OWNER,
        ROWS + BENEFICIARY_SLOT * 0x48 + 8: SOURCE_HANDLE,
        ROWS + BENEFICIARY_SLOT * 0x48 + 0x10: BENEFICIARY_HANDLE,
        OWNER + 0x228 + 8: VECTOR if present else 0,
    }
    integers: dict[int, int] = {
        OWNER + 0x228 + 0x10: 1 if present else 0,
        OWNER + 0x228 + 0x14: 1 if present else 0,
    }
    if present:
        integers.update({
            VECTOR: BENEFICIARY_SLOT,
            TREATY + 8: TRADE_POWER_RELATION_DISCRIMINATOR,
            TREATY + 0x20: start,
            TREATY + 0x24: 0x29C77F8,
            TREATY + 0x40: 500,
            TREATY + 0x44: 1,
        })
        qwords.update({
            VECTOR + 8: TREATY,
            TREATY: BASE + TRADE_POWER_RELATION_VTABLE_RVA,
            TREATY + 0x10: SOURCE_HANDLE,
            TREATY + 0x18: BENEFICIARY_HANDLE,
        })
    return qwords, integers


def _readers(qwords: dict[int, int], integers: dict[int, int]):
    def qword(address: int) -> int:
        if address not in qwords:
            raise AssertionError(f"unexpected qword read: {address:#x}")
        return qwords[address]

    def integer(address: int, size: int = 4, signed: bool = True) -> int:
        del size, signed
        if address not in integers:
            raise AssertionError(f"unexpected integer read: {address:#x}")
        return integers[address]

    return qword, integer


class PeaceTradePowerProbeTests(unittest.TestCase):
    def test_runtime_country_lookup_entry_keeps_tag_for_treaty_reader(self) -> None:
        entry = _country_lookup_entry("KNI", SOURCE_SLOT, SOURCE_POINTER,
                                     SOURCE_HANDLE)
        self.assertEqual("KNI", entry["tag"])
        self.assertEqual(SOURCE_SLOT, entry["slot"])
        self.assertEqual(SOURCE_POINTER, entry["pointer"])
        self.assertEqual(SOURCE_HANDLE, entry["handle"])

    def test_present_relation_reads_direction_amount_and_open_end(self) -> None:
        source, beneficiary = _entries()
        qwords, integers = _memory()
        qword, integer = _readers(qwords, integers)

        state = _read_trade_power_state(
            source,
            beneficiary,
            BASE,
            1445_1001,
            qword,
            integer,
        )

        self.assertEqual(
            {
                "source": "KNI",
                "beneficiary": "VEN",
                "present": True,
                "start_date_raw": 1445_1000,
                "end_date_raw": 0x29C77F8,
                "amount_raw": 500,
                "amount_scale": 1000,
                "peace_treaty": True,
                "complete": True,
            },
            state,
        )

    def test_absence_is_complete_without_reverse_list(self) -> None:
        source, beneficiary = _entries()
        qwords, integers = _memory(present=False)
        qword, integer = _readers(qwords, integers)

        state = _read_trade_power_state(
            source,
            beneficiary,
            BASE,
            1445_1001,
            qword,
            integer,
        )

        self.assertFalse(state["present"])
        self.assertTrue(state["complete"])
        self.assertEqual(0, state["amount_raw"])
        self.assertEqual(1000, state["amount_scale"])

    def test_future_start_is_readable_but_not_complete(self) -> None:
        source, beneficiary = _entries()
        qwords, integers = _memory(start=1445_1002)
        qword, integer = _readers(qwords, integers)
        state = _read_trade_power_state(
            source,
            beneficiary,
            BASE,
            1445_1001,
            qword,
            integer,
        )
        self.assertTrue(state["present"])
        self.assertFalse(state["complete"])

    def test_identity_mismatch_is_rejected(self) -> None:
        source, beneficiary = _entries()
        qwords, integers = _memory()
        qwords[TREATY] += 1
        qword, integer = _readers(qwords, integers)
        with self.assertRaisesRegex(ProbeError, "identity"):
            _read_trade_power_state(
                source,
                beneficiary,
                BASE,
                1445_1001,
                qword,
                integer,
            )


class PeaceTradePowerSaveTests(unittest.TestCase):
    def test_streams_exact_reverse_and_scaled_trade_power_records(self) -> None:
        text = """EU4txt
date=1445.1.30
transfer_trade_power={
 amount=0.500
 is_enforced=yes
 first="KNI"
 second="VEN"
 start_date=1445.1.30
}
transfer_trade_power={
 amount=0.250
 is_enforced=no
 first="VEN"
 second="KNI"
 start_date=1446.1.30
 end_date=1450.1.30
}
"""
        with tempfile.TemporaryDirectory() as directory:
            save = Path(directory) / "sample.eu4"
            save.write_text(text, encoding="utf-8")
            snapshot = scan_save(
                save,
                trade_power_source="KNI",
                trade_power_beneficiary="VEN",
            )

        self.assertEqual(2, snapshot["parse"]["transfer_trade_power_block_count"])
        self.assertTrue(snapshot["query"]["trade_power_exact_pair_present"])
        self.assertEqual(1, snapshot["query"]["trade_power_matching_count"])
        self.assertTrue(snapshot["query"]["trade_power_reverse_pair_present"])
        record = snapshot["query"]["trade_power_matching_records"][0]
        self.assertEqual(500, record["amount_raw"])
        self.assertEqual(1000, record["amount_scale"])
        self.assertTrue(record["enforced"])
        self.assertEqual("1445.1.30", record["start_date_raw"])
        self.assertIsNone(record["end_date_raw"])
        self.assertEqual(
            {"start_date": "1445.1.30", "end_date": None},
            record["raw_dates"],
        )
        self.assertTrue(snapshot["parse"]["brace_balance_ok"])

    def test_absent_trade_power_pair_is_a_complete_negative_observation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save = Path(directory) / "sample.eu4"
            save.write_text("EU4txt\ndate=1445.1.30\n", encoding="utf-8")
            snapshot = scan_save(
                save,
                trade_power_source="KNI",
                trade_power_beneficiary="VEN",
            )

        self.assertEqual(0, snapshot["parse"]["transfer_trade_power_block_count"])
        self.assertFalse(snapshot["query"]["trade_power_exact_pair_present"])
        self.assertFalse(snapshot["query"]["trade_power_reverse_pair_present"])
        self.assertTrue(snapshot["parse"]["brace_balance_ok"])
        self.assertIn(
            "transfer_trade_power_block_not_found",
            snapshot["parse"]["unknown"],
        )


if __name__ == "__main__":
    unittest.main()
