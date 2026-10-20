"""Deterministic candidate-only generation/check. Never materializes or builds v15."""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re

from candidate_guard import HERE, ROOT, write, writable
import patch_host
import patch_protocol
import patch_manifest
import patch_tools


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode()


def bounded(path, maximum=32*1024*1024):
    with path.open("rb") as source:
        raw = source.read(maximum+1)
    if len(raw) > maximum:
        raise ValueError("Input too large: " + str(path))
    return raw


def frozen_inputs():
    revision = json.loads(bounded(HERE / "plan-revision.json"))
    pins = revision["source_pins"]
    for row in pins.values():
        raw = bounded(ROOT / row["path"])
        if digest(raw) != row["sha256"] or len(raw) != row["size_bytes"]:
            raise ValueError("Revision input changed: " + row["path"])
    original = json.loads(bounded(ROOT / pins["original_plan_pins"]["path"]))
    for row in original["inputs"]:
        raw = bounded(ROOT / row["path"])
        if digest(raw) != row["sha256"] or len(raw) != row["bytes"]:
            raise ValueError("Frozen v14 input changed: " + row["path"])
    if len(original["inputs"]) != 49:
        raise ValueError("Unexpected frozen input inventory")
    return original["inputs"], pins


def renamed(raw):
    return raw.decode("utf-8").replace("\r\n", "\n").replace("v14", "v15").replace("V14", "V15").replace("EU4LAB/2", "EU4LAB/3")


def generate():
    frozen, pins = frozen_inputs()
    lineage = json.loads(bounded(HERE / "copy-lineage.json"))
    if len(lineage) != 31:
        raise ValueError("Expected 20 native and 11 host predecessor sources")
    outputs = {}
    for row in lineage:
        raw = bounded(ROOT / row["source"])
        if digest(raw) != row["source_sha256"]:
            raise ValueError("Copy lineage differs: " + row["source"])
        outputs[row["target"]] = renamed(raw).encode()
    for row in frozen:
        if row["role"] == "frozen_support":
            outputs[row["path"]] = bounded(ROOT / row["path"])
        elif row["role"] == "frozen_fixture_source":
            outputs[row["path"].replace("fixture-v14-", "fixture-v15-")] = bounded(ROOT / row["path"])
    for name in ("test-acceptance-1375.h", "test-acceptance-1375.cpp"):
        outputs["work/native/v15/"+name] = bounded(HERE / "native-core" / name)
    outputs["work/native/v15/lab-request-1375.h"] = bounded(HERE / "assets/lab-request-1375.h")
    outputs["tools/verify_diplomacy_acceptance_v15.py"] = bounded(HERE / "assets/verify_diplomacy_acceptance_v15.py")
    outputs["work/native/v15/research-lab-1375.cpp"] = patch_host.transform(
        outputs["work/native/v15/research-lab-1375.cpp"].decode(),
        bounded(HERE / "host-acceptance.inc").decode()).encode()
    for path, text in patch_tools.outputs().items():
        outputs[path] = text.encode()
    native = {p: digest(b).upper() for p,b in outputs.items() if p.startswith("work/native/v15/") or p.startswith("work/native/test-fixture-v15-")}
    host = [r["target"] for r in lineage if r["source"].endswith(".py")]
    host.append("tools/verify_diplomacy_acceptance_v15.py")
    if len(native) != 22 or len(host) != 12:
        raise ValueError("v15 source cardinality differs")
    abi_review = "work/review-results/offered-fleet-ai-response-native-inventory-20261008a/review.json"
    abi_sha = "a26de50a233662f26f44140bdce8cbe22f2497739ed7540fb75bcf26fd225478"
    if digest(bounded(ROOT/abi_review)) != abi_sha:
        raise ValueError("Independent ABI review changed")
    native_review = {
        "schema_version": 1, "purpose": "v15_unbuilt_native_source_contract",
        "native_source_sha256": native,
        "native_source_count": 22, "cpp_count": 9, "asm_count": 1, "link_object_count": 10,
        "static_evidence": pins["final_static_report"],
        "independent_abi_review": {"path":abi_review,"sha256":abi_sha},
        "interpretation": "Source-contract inventory and prior ABI evidence; not an independent review or compilation of this integration.",
        "native_built": False, "runtime_verified": False, "game_accessed": False,
        "strict_single_player_verified": False, "world_generation_verified": False,
        "production_backend_registered": False,
    }
    review_raw = encoded(native_review)
    protocol = patch_protocol.transform(renamed(bounded(ROOT/"work/native/lab_protocol_v14_1375.py")))
    protocol = patch_manifest.transform(protocol,bounded(HERE/"manifest-extra.py.inc").decode())
    for key, value in (("EXPECTED_NATIVE_SOURCES", native), ("HOST_SOURCES",tuple(host)), ("NATIVE_REVIEW_SHA256",digest(review_raw))):
        protocol,n = re.subn(r"^"+key+r" = .*$",key+" = "+repr(value),protocol,flags=re.M)
        if n != 1:
            raise ValueError("Missing unique generated constant: " + key)
    outputs["work/native/lab_protocol_v15_1375.py"] = protocol.encode()
    for path,raw in outputs.items():
        if path.endswith(".py"):
            ast.parse(raw.decode(), filename=path)
    artifacts = {"native-source-review.json":review_raw}
    deltas = {}
    for row in lineage:
        before=bounded(ROOT/row["source"]).decode().splitlines(keepends=True)
        after=outputs[row["target"]].decode().splitlines(keepends=True)
        delta="".join(difflib.unified_diff(before,after,fromfile=row["source"],tofile=row["target"]))
        if delta:
            path="diffs/"+row["target"].replace("/","__")+".diff"
            artifacts[path]=delta.encode()
            deltas[path]=digest(artifacts[path])
    index={"schema_version":1,"purpose":"isolated_v15_unbuilt_source_proposal",
        "files":{p:{"sha256":digest(b),"bytes":len(b)} for p,b in sorted(outputs.items())},
        "counts":{"native":22,"host":12,"support":8,"fixture":5,"total":47},
        "frozen_inputs_checked":len(frozen), "native_review_sha256":digest(review_raw),
        "diff_sha256":deltas,"materialized":False,"native_built":False,
        "game_accessed":False,"production_backend_registered":False}
    if len(outputs) != 47:
        raise ValueError("Unexpected total candidate source inventory")
    artifacts["candidate-index.json"] = encoded(index)
    return outputs, artifacts


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--check",action="store_true")
    choice.add_argument("--refresh-candidate",action="store_true")
    args=parser.parse_args(argv)
    if args.refresh_candidate:
        writable()
    outputs, artifacts=generate()
    actual=set()
    for path in (HERE/"files").rglob("*"):
        if "__pycache__" in path.parts:
            continue
        if path.is_symlink() or path.is_junction():
            raise ValueError("Candidate source mirror contains a link")
        if path.is_file():
            actual.add(path.relative_to(HERE/"files").as_posix())
        if len(actual)>128:
            raise ValueError("Candidate source mirror exceeds inventory bound")
    if actual-set(outputs):
        raise ValueError("Unexpected candidate source files: "+repr(sorted(actual-set(outputs))))
    all_files={**{"files/"+p:b for p,b in outputs.items()},**artifacts}
    for path,raw in all_files.items():
        if args.check:
            if not (HERE/path).is_file() or bounded(HERE/path)!=raw:
                raise ValueError("Candidate output differs: "+path)
        else:
            write(HERE/path,raw)
    print(json.dumps({"checked":True,"mode":"check" if args.check else "candidate_refresh",
        "proposed_source_count":len(outputs),"frozen_inputs_unchanged":49,
        "materialized":False,"native_built":False,"game_accessed":False},sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
