from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from reverse_engineering.catalog import format_rva, iter_symbols, validate_catalog


def fixture_catalog(*, digest: str | None = None, rva: int | str = 0x20) -> dict:
    return {
        "schema_version": 1,
        "title": "联盟链路 fixture",
        "scope": "小型合同测试",
        "binary": {
            "version": "test",
            "sha256": digest or ("0" * 64),
            "image_base": "0x140000000",
        },
        "sources": [
            {"id": "src-fixture", "path": "evidence/fixture.txt", "kind": "fixture"},
        ],
        "nodes": [
            {
                "id": "n-entry",
                "label": "入口",
                "stage": "submit",
                "rva": rva,
                "status": "fixture_verified",
                "sources": ["src-fixture"],
            },
        ],
        "edges": [],
        "questions": [
            {
                "id": "q-one",
                "title": "下一步需要运行时确认什么？",
                "priority": "high",
                "status": "open",
                "nodes": ["n-entry"],
                "sources": [],
                "next_step": "补充运行时证据",
            },
        ],
    }


class CatalogValidationTests(unittest.TestCase):
    def test_valid_fixture_and_static_va_format(self) -> None:
        data = fixture_catalog(rva="0x20")
        result = validate_catalog(data)
        self.assertTrue(result.valid, result.error_messages)
        self.assertEqual(format_rva(data["nodes"][0], data["binary"]["image_base"]), "RVA=0x20；静态 VA=0x140000020")
        self.assertEqual(len(iter_symbols(data, "0x20")), 1)
        self.assertEqual(len(iter_symbols(data, "0x140000020")), 1)
        data["nodes"][0]["addresses"] = {"runtime": "0x7FF00020"}
        self.assertEqual(len(iter_symbols(data, "0x7ff00020")), 1)

    def test_rejects_dangling_references(self) -> None:
        data = fixture_catalog()
        data["edges"] = [
            {
                "id": "e-bad",
                "from": "n-entry",
                "to": "n-missing",
                "kind": "call",
                "status": "inferred",
                "sources": ["src-missing"],
            }
        ]
        data["questions"][0]["nodes"] = ["n-missing"]
        result = validate_catalog(data)
        self.assertFalse(result.valid)
        rendered = "\n".join(result.error_messages)
        self.assertIn("不存在的 source", rendered)
        self.assertIn("不存在的 node", rendered)

    def test_fixture_source_cannot_masquerade_as_runtime(self) -> None:
        data = fixture_catalog()
        data["nodes"][0]["status"] = "runtime_observed"
        result = validate_catalog(data)
        self.assertFalse(result.valid)
        self.assertIn("fixture 不能冒充 runtime", "\n".join(result.error_messages))

    def test_binary_hash_mismatch_and_non_pe_boundary_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            binary = Path(temp_dir) / "tiny.bin"
            binary.write_bytes(b"1234")
            data = fixture_catalog(digest="0" * 64, rva=4)
            result = validate_catalog(data, binary_path=binary)
            self.assertFalse(result.valid)
            rendered = "\n".join(result.error_messages)
            self.assertIn("SHA-256 不匹配", rendered)
            self.assertTrue(any("仅完成 SHA-256" in message for message in result.warning_messages))

    def test_pe_rva_can_be_in_virtual_padding_but_not_beyond_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            binary = Path(temp_dir) / "tiny.exe"
            binary.write_bytes(minimal_pe(size_of_image=0x5000))
            data = fixture_catalog(
                digest=hashlib.sha256(binary.read_bytes()).hexdigest(),
                rva=0x3000,
            )
            result = validate_catalog(data, binary_path=binary)
            self.assertTrue(result.valid, result.error_messages)
            self.assertTrue(any("虚拟映像布局" in message for message in result.warning_messages))

            data["nodes"][0]["rva"] = 0x6000
            result = validate_catalog(data, binary_path=binary)
            self.assertFalse(result.valid)
            self.assertIn("超出 PE SizeOfImage", "\n".join(result.error_messages))


def minimal_pe(*, size_of_image: int) -> bytes:
    """Return a tiny PE32+ header with no section data, for bounded tests."""

    image = bytearray(0x200)
    image[0:2] = b"MZ"
    image[0x3C:0x40] = (0x80).to_bytes(4, "little")
    image[0x80:0x84] = b"PE\0\0"
    # COFF header: x64 machine, one section, 0xF0-byte optional header.
    image[0x84:0x86] = (0x8664).to_bytes(2, "little")
    image[0x86:0x88] = (1).to_bytes(2, "little")
    image[0x94:0x96] = (0xF0).to_bytes(2, "little")
    optional = 0x98
    image[optional : optional + 2] = (0x20B).to_bytes(2, "little")
    image[optional + 56 : optional + 60] = size_of_image.to_bytes(4, "little")
    return bytes(image)


if __name__ == "__main__":
    unittest.main()

