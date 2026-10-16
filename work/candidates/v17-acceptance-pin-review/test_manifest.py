"""Synthetic PE/manifest and write-guard tests; never maps or compiles a DLL."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest

from test_candidate import HERE, ROOT, lab
import candidate_guard
import prepare


def pe_image(*, forwarder=False, duplicate=False, missing=False, executable=True):
    raw=bytearray(0x800)
    def put(offset,format,*values): struct.pack_into(format,raw,offset,*values)
    raw[:2]=b"MZ";put(0x3c,"<I",0x80);raw[0x80:0x84]=b"PE\0\0"
    put(0x84,"<HH",0x8664,1);put(0x94,"<H",240)
    opt=0x98;put(opt,"<H",0x20b);put(opt+56,"<I",0x2000);put(opt+108,"<I",16)
    put(opt+112,"<II",0x1000,0x100)
    section=opt+240;raw[section:section+8]=b".text\0\0\0"
    put(section+8,"<IIII",0x600,0x1000,0x600,0x200)
    put(section+36,"<I",0x60000020 if executable else 0x40000040)
    put(0x214,"<IIIII",1,2 if duplicate else 1,0x1040,0x1050,0x1060)
    put(0x240,"<I",0x1080 if forwarder else 0x1200)
    put(0x250,"<II",0x1080,0x1080);put(0x260,"<HH",0,0)
    name=b"OtherExport\0" if missing else b"BridgeStart\0"
    raw[0x280:0x280+len(name)]=name
    raw[0x400]=0xc3
    return bytes(raw)


class Manifest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"source";self.root.mkdir()
        outputs,artifacts=prepare.generate()
        for path,raw in outputs.items():
            dest=self.root/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        for path,raw in ((lab.NATIVE_REVIEW_PATH,artifacts["native-source-review.json"]),
                         (lab.ACCEPTANCE_STATIC_PATH,(ROOT/lab.ACCEPTANCE_STATIC_PATH).read_bytes())):
            dest=self.root/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        self.output=self.root/"work/runtime/native1375-v17";self.output.mkdir(parents=True)
        self.dll=self.output/lab.DLL_NAME;self.dll.write_bytes(pe_image())

    def test_record_and_verify_new_schema_sources_real_export(self):
        result=lab.record_build(self.root,self.output)
        verified,_=lab.verify_build(self.root,self.output)
        self.assertEqual(verified,result)
        self.assertEqual(result["schema_version"],3)
        self.assertEqual(result["protocol_version"],"EU4LAB/3")
        self.assertEqual(result["bridge_start_export_rva"],0x1200)
        self.assertEqual((len(result["source_sha256"]),len(result["host_source_sha256"]),len(result["support_source_sha256"])),(22,12,8))
        self.assertFalse(result["runtime_verified"])
        self.assertEqual(prepare.digest(lab.canonical(lab.fixture_profile(self.root)).encode()),lab.FIXTURE_PROFILE_SHA256)

    def test_old_contract_missing_control_changed_static_and_mixed_purpose_rejected(self):
        result=lab.record_build(self.root,self.output)
        for update in ({"schema_version":2},{"purpose":"restricted_pair_lab_1375_v14"},
                       {"protocol_version":"EU4LAB/2"},{"bridge_start_export_rva":True},
                       {"bridge_start_export_rva":0x1100},
                       {"acceptance_control_contract":dict(result["acceptance_control_contract"],window_grants=2)},
                       {"native_candidate_review_sha256":"0"*64}):
            changed=result|update;(self.output/"build.json").write_text(json.dumps(changed))
            with self.subTest(update=update),self.assertRaises(ValueError):lab.verify_build(self.root,self.output)
        (self.output/"build.json").write_text(json.dumps(result))
        (self.root/lab.ACCEPTANCE_STATIC_PATH).write_text("{}")
        with self.assertRaises(ValueError):lab.verify_build(self.root,self.output)

    def test_sources_fixture_and_required_new_verifier_are_bound(self):
        result=lab.record_build(self.root,self.output)
        for path in ("tools/verify_diplomacy_acceptance_v17.py","work/native/v17/test-acceptance-1375.cpp",
                     lab.FIXTURE_CANDIDATE_ROOT+"/"+lab.FIXTURE_SOURCES[-1]):
            source=self.root/path;raw=source.read_bytes();source.write_bytes(raw+b"\n")
            with self.subTest(path=path),self.assertRaises(ValueError):lab.verify_build(self.root,self.output)
            source.write_bytes(raw)
        result["host_source_sha256"].pop("tools/verify_diplomacy_acceptance_v17.py")
        (self.output/"build.json").write_text(json.dumps(result))
        with self.assertRaises(ValueError):lab.verify_build(self.root,self.output)

    def test_record_refuses_replacement_or_existing_session(self):
        lab.record_build(self.root,self.output)
        before=(self.output/"build.json").read_bytes()
        with self.assertRaises(ValueError):lab.record_build(self.root,self.output)
        self.assertEqual((self.output/"build.json").read_bytes(),before)
        (self.output/"build.json").unlink();(self.output/"session-test").mkdir()
        with self.assertRaises(ValueError):lab.record_build(self.root,self.output)

    def test_export_parser_rejects_forwarder_duplicate_missing_and_nonexec(self):
        for changes in ({"forwarder":True},{"duplicate":True},{"missing":True},{"executable":False}):
            self.dll.write_bytes(pe_image(**changes))
            with self.subTest(changes=changes),self.assertRaises(ValueError):lab.bridge_start_export_rva(self.dll)
        for content in (b"MZ",pe_image()[:0x240],b"not a DLL"):
            self.dll.write_bytes(content)
            with self.assertRaises(ValueError):lab.bridge_start_export_rva(self.dll)
        changed=bytearray(pe_image());struct.pack_into("<I",changed,0x98+108,0)
        self.dll.write_bytes(changed)
        with self.assertRaises(ValueError):lab.bridge_start_export_rva(self.dll)

    def test_exact_native_build_object_counts_and_unmodified_inputs(self):
        raw=(self.root/"work/native/v17/build-lab-1375.cmd").read_text()
        self.assertEqual(sum(line.startswith("cl ") for line in raw.splitlines()),9)
        self.assertEqual(sum(line.startswith("ml64 ") for line in raw.splitlines()),1)
        link=next(line for line in raw.splitlines() if line.startswith("link "))
        self.assertEqual(link.count(".obj\""),10)
        self.assertEqual(len(prepare.frozen_inputs()[0]),49)


class WriteGuard(unittest.TestCase):
    def test_formal_or_candidate_artifact_permanently_blocks_write(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);here=root/"candidate";here.mkdir();(here/"files").mkdir()
            candidate_guard.writable(here,root)
            for base,name in ((root,"build.json"),(root,"eu4_pair_lab_v17_1375.dll"),(here/"files","session-1234")):
                runtime=base/"work/runtime/native1375-v17";runtime.mkdir(parents=True,exist_ok=True)
                target=runtime/name;target.write_text("sentinel")
                with self.subTest(name=name),self.assertRaises(ValueError):candidate_guard.writable(here,root)
                self.assertEqual(target.read_text(),"sentinel")
                target.unlink()


if __name__ == "__main__":unittest.main()
