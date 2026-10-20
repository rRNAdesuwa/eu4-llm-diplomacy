"""Prepare a separate FRA land-maintenance budget; preserve all other bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from work.prepare_r71_favor_scene import brace_delta


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    source, output = args.source.resolve(strict=True), args.output.resolve()
    if output.exists() or args.report.exists() or source == output:
        raise ValueError("Use new output and report files")
    depth = 0
    countries_depth = country_depth = None
    edits = []
    digest = hashlib.sha256()
    with source.open("rb") as stream, output.open("xb") as target:
        for number, line in enumerate(stream, 1):
            before = depth
            if before == 0 and line.strip() == b"countries={":
                countries_depth = before + 1
            if countries_depth is not None and before == countries_depth and line.strip() == b"FRA={":
                country_depth = before + 1
            written = line
            if country_depth is not None and before == country_depth:
                match = re.match(rb"([ \t]*land_maintenance=)([0-9.]+)(.*)", line)
                if match:
                    written = line[:match.start(2)] + b"0.000" + line[match.end(2):]
                    edits.append({"line": number, "path": "countries/FRA/land_maintenance",
                                  "before": line.decode().rstrip(), "after": written.decode().rstrip()})
            target.write(written)
            digest.update(written)
            depth += brace_delta(line)
            if country_depth is not None and depth < country_depth:
                country_depth = None
            if countries_depth is not None and depth < countries_depth:
                countries_depth = None
    if len(edits) != 1 or depth != 0:
        raise ValueError(f"Unexpected save structure or edit count: {len(edits)}")
    report = {"status": "passed", "source": str(source), "output": str(output),
              "output_sha256": digest.hexdigest(), "edits": edits,
              "ledger_or_exchange_result_edited": False,
              "next": "Load and advance the native economy; native query decides affordability"}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.open("x", encoding="utf-8").write(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
