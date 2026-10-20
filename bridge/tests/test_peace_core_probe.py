"""Bounded unit tests for the province core-vector probe helper.

These tests use a tiny address/value map and assert the helper's read boundary;
they never attach to a game process or exercise the runtime CLI.
"""

from __future__ import annotations

import unittest

from work import probe_peace_effect_state as probe


PROVINCE = 0x200000
VECTOR = 0x80000


class _QwordMemory:
    def __init__(self, values: dict[int, int]) -> None:
        self.values = dict(values)
        self.reads: list[int] = []

    def qword(self, address: int) -> int:
        self.reads.append(address)
        try:
            return self.values[address]
        except KeyError as exc:
            raise AssertionError(f"unexpected qword read at {address:#x}") from exc


def _headers(begin: int, end: int) -> dict[int, int]:
    return {
        PROVINCE + probe.PROVINCE_CORES_BEGIN_OFFSET: begin,
        PROVINCE + probe.PROVINCE_CORES_END_OFFSET: end,
    }


def _canonical_table(mapping: dict[int, str]):
    def canonical(raw: int) -> dict[str, object]:
        return {
            "raw_handle": hex(raw),
            "tag": mapping.get(raw),
            "identity_verified": raw in mapping,
        }

    return canonical


class ProvinceCoreProbeTests(unittest.TestCase):
    def test_reads_multiple_core_handles_in_vector_order(self) -> None:
        handles = [0x10000001, 0x20000002, 0x30000003]
        memory = _QwordMemory({
            **_headers(VECTOR, VECTOR + 3 * 8),
            VECTOR + 0 * 8: handles[0],
            VECTOR + 1 * 8: handles[1],
            VECTOR + 2 * 8: handles[2],
        })

        state = probe._read_province_cores(
            PROVINCE,
            memory.qword,
            _canonical_table(dict(zip(handles, ("FRA", "ENG", "SCO")))),
        )

        self.assertEqual(3, state["count"])
        self.assertEqual(["FRA", "ENG", "SCO"], state["tags"])
        self.assertTrue(state["complete"])
        self.assertTrue(state["vector_readable"])
        self.assertEqual(
            ["FRA", "ENG", "SCO"],
            [row["tag"] for row in state["countries"]],
        )
        self.assertEqual(
            {
                PROVINCE + probe.PROVINCE_CORES_BEGIN_OFFSET,
                PROVINCE + probe.PROVINCE_CORES_END_OFFSET,
                VECTOR,
                VECTOR + 8,
                VECTOR + 16,
            },
            set(memory.reads),
        )

    def test_empty_vector_is_complete_and_does_not_read_body(self) -> None:
        memory = _QwordMemory(_headers(0, 0))

        state = probe._read_province_cores(
            PROVINCE,
            memory.qword,
            _canonical_table({}),
        )

        self.assertEqual(
            {
                "count": 0,
                "countries": [],
                "tags": [],
                "complete": True,
                "vector_readable": True,
                "begin_field_offset": hex(probe.PROVINCE_CORES_BEGIN_OFFSET),
                "end_field_offset": hex(probe.PROVINCE_CORES_END_OFFSET),
            },
            state,
        )
        self.assertEqual(
            {
                PROVINCE + probe.PROVINCE_CORES_BEGIN_OFFSET,
                PROVINCE + probe.PROVINCE_CORES_END_OFFSET,
            },
            set(memory.reads),
        )

    def test_invalid_span_is_rejected_before_body_reads(self) -> None:
        cases = (
            ("reversed", 0x80020, 0x80018),
            ("unaligned", 0x80020, 0x80029),
            ("too_large", 0x80020, 0x80020 + (probe.MAX_PROVINCE_CORE_COUNT + 1) * 8),
            ("low_nonempty_begin", 0x1000, 0x1008),
        )
        for name, begin, end in cases:
            with self.subTest(name=name):
                memory = _QwordMemory({
                    **_headers(begin, end),
                    begin: 0xDEADBEEF,
                })
                with self.assertRaisesRegex(
                        probe.ProbeError, "invalid bounded province core vector"):
                    probe._read_province_cores(
                        PROVINCE, memory.qword, _canonical_table({}))
                self.assertEqual(
                    [
                        PROVINCE + probe.PROVINCE_CORES_BEGIN_OFFSET,
                        PROVINCE + probe.PROVINCE_CORES_END_OFFSET,
                    ],
                    memory.reads,
                )

    def test_unknown_handle_is_retained_without_fake_tag_or_complete(self) -> None:
        unknown = 0xABCDEF01
        memory = _QwordMemory({
            **_headers(VECTOR, VECTOR + 8),
            VECTOR: unknown,
        })

        state = probe._read_province_cores(
            PROVINCE,
            memory.qword,
            _canonical_table({}),
        )

        self.assertFalse(state["complete"])
        self.assertEqual([], state["tags"])
        self.assertEqual(1, state["count"])
        self.assertEqual(
            {
                "raw_handle": hex(unknown),
                "tag": None,
                "identity_verified": False,
            },
            state["countries"][0],
        )
        self.assertNotEqual("", state["countries"][0]["tag"])

    def test_duplicate_handles_are_rejected_before_identity_projection(self) -> None:
        duplicate = 0x11112222
        memory = _QwordMemory({
            **_headers(VECTOR, VECTOR + 2 * 8),
            VECTOR: duplicate,
            VECTOR + 8: duplicate,
        })
        canonical_calls: list[int] = []

        def canonical(raw: int) -> dict[str, object]:
            canonical_calls.append(raw)
            return {"raw_handle": hex(raw), "tag": "FRA", "identity_verified": True}

        with self.assertRaisesRegex(
                probe.ProbeError, "duplicate province core country handles"):
            probe._read_province_cores(PROVINCE, memory.qword, canonical)

        self.assertEqual([], canonical_calls)
        self.assertEqual(
            [
                PROVINCE + probe.PROVINCE_CORES_BEGIN_OFFSET,
                PROVINCE + probe.PROVINCE_CORES_END_OFFSET,
                VECTOR,
                VECTOR + 8,
            ],
            memory.reads,
        )


if __name__ == "__main__":
    unittest.main()

