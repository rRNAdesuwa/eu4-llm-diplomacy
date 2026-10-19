"""Non-author pinned flat-file intake only; do not execute author tools or queries."""
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
BASE = "work/candidates/war-peace-api-lookup-1375-v5/"
OUT = ROOT / "work/reports/war-peace-api-lookup-v5-independent-review-20261016-r1"
RAW = {}
PINS = {}
COUNT = 0
LIMIT = 16 * 1024 * 1024


def pair(n, sha):
    return {"bytes": n, "sha256": sha}


def read(rel, expected):
    global COUNT
    name = PurePosixPath(rel)
    assert name.as_posix() == rel and not name.is_absolute() and ".." not in name.parts and ":" not in rel and "\\" not in rel
    p = (ROOT / rel).resolve()
    assert p.is_relative_to(ROOT) and not p.is_relative_to((ROOT / "work/deps").resolve())
    assert p.suffix.lower() not in (".exe", ".dll", ".pyd")
    assert set(expected) == {"bytes", "sha256"} and type(expected["bytes"]) is int and 0 <= expected["bytes"] <= 4 * 1024 * 1024
    first = p.stat(); assert first.st_size == expected["bytes"]
    raw = p.read_bytes(); COUNT += len(raw)
    last = p.stat()
    assert COUNT <= LIMIT and first.st_size == last.st_size == len(raw) and first.st_mtime_ns == last.st_mtime_ns
    actual = pair(len(raw), hashlib.sha256(raw).hexdigest())
    assert actual == expected and (rel not in PINS or PINS[rel] == actual), rel
    PINS[rel] = actual
    RAW[rel] = raw


assert not OUT.exists()
for name, n, sha in (
    ("source-manifest.json", 19355, "1c1b0acd82b7ad100c8e6085deb5e994b92defd8212bf61d2a3a5db2b6cdf27f"),
    ("author-manifest.json", 28136, "a1eac6c6fbaa34f797aea4697bd96c529757c65672dea61ea8bba44d7b0bcef3"),
    ("publication-manifest.json", 7834, "f2382bdec4cdbd0db224b825a6f310fdc49510adf7bf1829a9233de8336816ba"),
    ("data-manifest.json", 14774, "39efa19ba26675647379f6be182b26be727762d5eaf906f0be822b7ca0dba69c"),
    ("index.json", 185792, "a8b70f547513def34f88c1dd19e73e573c63fe209aeced61f397db8b22556e6c"),
    ("query_engine.py", 16583, "ea030ce19461b2e414e0cdbc42f4933551fa9e654f7a7a43db948670b27fa466"),
    ("war_peace_lookup.py", 3602, "653530b8d60e789f33786819e43de7d057142de5c75c6841469d2802928a9da6"),
    ("delivery.json", 2461, "c9149b6dddeb07d2016602f5ec72e8c3af58857bc86dff6021ac7232c897b2e6"),
    ("verification.json", 56520, "56056e311ae1cd8964cf46052df23652f8e84df17f9978928fca0cd0f52e69bc"),
):
    read(BASE + name, pair(n, sha))
author = json.loads(RAW[BASE + "author-manifest.json"])
publication = json.loads(RAW[BASE + "publication-manifest.json"])
source = json.loads(RAW[BASE + "source-manifest.json"])
assert author["sealed"] is True and publication["sealed"] is True and source["sealed"] is True
assert author["pin_count"] == len(author["local_and_selected_source_pins"]) == 136
assert author["subject_source_manifest"] == PINS[BASE + "source-manifest.json"]
assert publication["author_manifest"] == PINS[BASE + "author-manifest.json"]
expected = dict(PINS)
for group in (author["local_and_selected_source_pins"], publication["additional_and_delivery_pins"]):
    for rel, value in group.items():
        assert rel not in expected or expected[rel] == value, rel
        expected[rel] = value
assert sum(p["bytes"] for p in expected.values()) <= LIMIT
for rel, value in expected.items():
    if rel in PINS:
        assert PINS[rel] == value
    else:
        read(rel, value)
assert all(expected.get(rel) == value for rel, value in source["files"].items())
OUT.mkdir(); (OUT / "cache").mkdir()
cache = {}
for i, (rel, raw) in enumerate(RAW.items()):
    name = "cache/" + str(i).zfill(3) + ".dat"
    with (OUT / name).open("xb") as f:
        f.write(raw)
    cache[rel] = {"pin": PINS[rel], "owned": name}
value = {"schema": "ROOT-LOOKUP-V5-NONAUTHOR-INTAKE/1", "sealed": True, "intake_passed": True,
    "complete_review_passed": False, "cached": cache, "subject_source_manifest": PINS[BASE + "source-manifest.json"],
    "subject_author_manifest": PINS[BASE + "author-manifest.json"], "subject_publication_manifest": PINS[BASE + "publication-manifest.json"],
    "source_files_read": len(PINS), "selected_read_bytes": COUNT, "intake_limit": LIMIT,
    "whole_review_source_budget": 32 * 1024 * 1024, "whole_review_retained_budget": 8 * 1024 * 1024,
    "manual_initial_inspection_allowance": 2 * 1024 * 1024,
    "whole_original_graph_final_after_pin_not_yet_done": True,
    "source_closure_recursive_authentication": False, "Capstone_PE_game_author_program_queries_tests_operations": 0,
    "authority": {"native_ready": False, "callable": False, "reader_adoption_allowed": False, "selected_effect_verified": False}}
data = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()
with (OUT / "intake.json").open("xb") as f:
    f.write(data)
print(json.dumps({"files": len(PINS), "selected_read_bytes": COUNT, "intake_bytes": len(data), "intake_sha256": hashlib.sha256(data).hexdigest()}, ensure_ascii=True))
