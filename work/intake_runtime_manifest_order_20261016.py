"""File-only intake for manifest-buffer guard order; never import target tools."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "work/reports/runtime-manifest-order-intake-20261016-r1"
COUNT = 0
PINS = {}


def read(rel, expected):
    global COUNT
    path = (ROOT / rel).resolve()
    assert path.is_relative_to(ROOT) and not path.is_relative_to((ROOT / "work/deps").resolve())
    assert path.stat().st_size <= 4 * 1024 * 1024
    raw = path.read_bytes()
    COUNT += len(raw)
    assert COUNT <= 2 * 1024 * 1024
    actual = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    assert actual == expected, rel
    assert rel not in PINS or PINS[rel] == actual
    PINS[rel] = actual
    return raw


assert not OUT.exists()
map_rel = "docs/runtime-capability-map-1375-v4.json"
raw = read(map_rel, {"bytes": 13120, "sha256": "25886c3d1f60f2625e0f2c2aa953bc5a5447bed86ba802252eb62911c5e502a5"})
discovery = json.loads(raw)
assert len(discovery["tools"]) == 7
owned = {map_rel: raw}
entries = []
for item in discovery["tools"]:
    entry, manifest = item["entry"], item["manifest"]
    owned[entry] = read(entry, item["entry_pin"])
    owned[manifest] = read(manifest, item["manifest_pin"])
    entries.append({"id": item["id"], "entry": entry, "manifest": manifest})
before = dict(PINS)
for rel, expected in before.items():
    read(rel, expected)
OUT.mkdir()
for index, (rel, raw) in enumerate(owned.items()):
    with (OUT / (str(index).zfill(2) + "__" + Path(rel).name)).open("xb") as stream:
        stream.write(raw)
index = {"sealed": True, "purpose": "Guard-order intake only, no source closure or runtime acceptance",
    "entries": entries, "pins": before, "before_after_equal": True,
    "selected_read_bytes": COUNT, "maximum": 2 * 1024 * 1024,
    "PE_engine_process_old_program_test_operations": 0,
    "actual_authorized": False, "reader_adoption_allowed": False}
data = (json.dumps(index, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()
with (OUT / "index.json").open("xb") as stream:
    stream.write(data)
print(json.dumps({"owned_files": len(owned), "selected_read_bytes": COUNT,
    "index_bytes": len(data), "index_sha256": hashlib.sha256(data).hexdigest()}, ensure_ascii=True))
