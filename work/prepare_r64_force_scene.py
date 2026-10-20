"""Create a paused force-query scene by removing the identified R63 war.

Only the previously verified active_war block is removed. Country force
fields, the date, alliances and the original save remain unchanged.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from work.prepare_r62_trade_cb_scene import SAVE_DIR


def main() -> int:
    evidence = json.loads((ROOT / "work/runtime/r63-participants-save-fields-20261019-001/report.json")
                          .read_text(encoding="utf-8-sig"))
    source = Path(evidence["source"]["path"])
    destination = SAVE_DIR / "llm_diplomacy_declarewar_forces_20261019_r64.eu4"
    output = ROOT / "work/runtime/r64-force-scene-20261019-001"
    if destination.exists() or output.exists():
        raise FileExistsError("R64_SCENE_ALREADY_EXISTS")
    war = evidence["selected_war"]
    if war["matching_active_war_count"] != 1 or war["currently_active_pair_count"] != 1:
        raise ValueError("SOURCE_WAR_NOT_UNIQUE")
    first, last = war["line_start"], war["line_end"]
    input_hash, output_hash = hashlib.sha256(), hashlib.sha256()
    removed = []
    with source.open("rb") as reader, destination.open("xb") as writer:
        for number, line in enumerate(reader, 1):
            input_hash.update(line)
            if first <= number <= last:
                removed.append(line)
            else:
                writer.write(line)
                output_hash.update(line)
    if input_hash.hexdigest() != evidence["source"]["known_sha256"]:
        raise ValueError("SOURCE_SAVE_CHANGED")
    if not removed[0].strip().startswith(b"active_war={") or removed[-1].strip() != b"}":
        raise ValueError("REMOVED_WAR_BOUNDARY_CHANGED")
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "status": "prepared", "source": str(source), "destination": str(destination),
        "source_sha256": input_hash.hexdigest(), "destination_sha256": output_hash.hexdigest(),
        "date": "1455.9.10", "player": "POR",
        "mutation": "remove one identified FRA-BUR active_war block for independent force queries",
        "removed_line_range": [first, last], "removed_lines": len(removed),
        "removed_block_sha256": hashlib.sha256(b"".join(removed)).hexdigest(),
        "preserved_country_force_fields": True, "scene_loaded": False,
        "basis": "work/runtime/r63-participants-save-fields-20261019-001/report.json",
    }
    (output / "removed-war.txt").write_bytes(b"".join(removed))
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
