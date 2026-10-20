"""Prepare a new R63 scene by adding FRA alliances with SCO and SAV."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from work.prepare_r62_trade_cb_scene import DEFAULT_OUTPUT, SAVE_DIR, _transform_save
from work.prepare_r61_country_scenes import (
    BLOCK_RE, brace_delta, fields_at_depth, iter_block_lines, stripped,
)


def alliances(path: Path) -> list[dict]:
    result = []
    depth = 0
    line_number = 0
    diplomacy_depth = None
    with path.open("rb") as stream:
        while line := stream.readline():
            line_number += 1
            before = depth
            if before == 0 and stripped(line) == b"diplomacy={":
                diplomacy_depth = 1
            match = BLOCK_RE.match(line) if before == diplomacy_depth else None
            if match and match.group("key") == b"alliance":
                block, line_number = iter_block_lines(
                    stream, line, line_number, max_bytes=65536)
                fields = fields_at_depth(block, 1)
                values = {key: value[1] for key, value in fields.items()}
                if "FRA" in (values.get("first"), values.get("second")):
                    result.append(values)
                continue
            depth += brace_delta(line)
            if diplomacy_depth and before == diplomacy_depth and depth == 0:
                return result
    raise ValueError("DIPLOMACY_BLOCK_INCOMPLETE")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--destination", type=Path, default=SAVE_DIR /
                        "llm_diplomacy_declarewar_allies_20261019_r63.eu4")
    parser.add_argument("--output", type=Path, default=ROOT / "work/runtime/r63-ally-scene-20261019-001")
    args = parser.parse_args()
    before = alliances(args.source)
    for target in ("SCO", "SAV"):
        if any({row.get("first"), row.get("second")} == {"FRA", target} for row in before):
            raise ValueError("SOURCE_ALREADY_HAS_REQUESTED_ALLIANCE")
    args.output.mkdir(parents=True, exist_ok=False)
    inserted = []
    for target in ("SCO", "SAV"):
        inserted.extend([
            b"\talliance={\n", b'\t\tfirst="FRA"\n',
            f'\t\tsecond="{target}"\n'.encode("ascii"),
            b"\t\tstart_date=1444.11.11\n", b"\t}\n",
        ])
    transform = _transform_save(args.source, args.destination, inserted)
    after = alliances(args.destination)
    complete = len(after) == len(before) + 2 and all(
        sum({row.get("first"), row.get("second")} == {"FRA", target}
            for row in after) == 1 for target in ("SCO", "SAV"))
    report = {
        "status": "prepared" if complete else "failed",
        "source": str(args.source.resolve()),
        "destination": str(args.destination.resolve()),
        "mutation": "two top-level diplomacy/alliance records: FRA-SCO, FRA-SAV",
        "alliance_start": "1444.11.11", "date": "1455.8.20",
        "before_alliances": before, "after_alliances": after,
        "transform": transform, "complete": complete,
        "scene_loaded": False, "diplomatic_requests_executed": 0,
    }
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(args.output / "report.json")}, ensure_ascii=False))
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
