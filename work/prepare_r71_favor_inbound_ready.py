"""Seed a paused positive-budget scene for two native inbound decisions."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from work.prepare_r71_favor_scene import brace_delta


def child_span(lines, name):
    depth = 0
    start = None
    for i, line in enumerate(lines):
        if depth == 1 and line.strip() == name + b"={":
            if start is not None:
                raise ValueError("Duplicate child block")
            start = i
        depth += brace_delta(line)
        if start is not None and depth == 1:
            return start, i + 1
    raise ValueError("Missing child block " + name.decode())


def scalar(lines, name, value):
    depth, found = 0, 0
    for i, line in enumerate(lines):
        if depth == 1 and re.match(rb"\s*" + name + rb"=", line):
            match = re.match(rb"(\s*" + name + rb"=)([^\r\n]*)(.*)", line)
            lines[i] = match[1] + value + line[match.end(2):]
            found += 1
        depth += brace_delta(line)
    return found


def prepare_fra(lines):
    original = b"".join(lines)
    assert scalar(lines, b"treasury", b"1000.000") == 1
    a, b = child_span(lines, b"active_relations")
    relations = lines[a:b]
    c, d = child_span(relations, b"LIT")
    lithuania = relations[c:d]
    old_relation = b"".join(lithuania)
    assert b'"r35_test_vassal_opinion"' not in old_relation
    ending = b"\r\n" if lithuania[0].endswith(b"\r\n") else b"\n"
    indent = re.match(rb"\s*", lithuania[0])[0] + b"\t"
    if scalar(lithuania, b"favors", b"20.000") == 0:
        lithuania.insert(1, indent + b"favors=20.000" + ending)
    old_sum = re.search(rb"(?m)^\s*cached_sum=([-0-9.]+)", old_relation)
    total = Decimal(old_sum[1].decode()) + 200 if old_sum else Decimal(200)
    value = str(total).encode()
    if scalar(lithuania, b"cached_sum", value) == 0:
        lithuania.insert(1, indent + b"cached_sum=" + value + ending)
    lithuania[-1:-1] = [indent + b"opinion={" + ending,
        indent + b'\tmodifier="r35_test_vassal_opinion"' + ending,
        indent + b"\tcurrent_opinion=200.000" + ending, indent + b"}" + ending]
    relations[c:d] = lithuania
    lines[a:b] = relations
    return b"".join(lines), {"paths": ["countries/FRA/treasury", "countries/FRA/active_relations/LIT"],
        "new_treasury": "1000.000", "old_relation": old_relation.decode(),
        "new_relation": b"".join(lithuania).decode(),
        "original_fra_sha256": hashlib.sha256(original).hexdigest()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    assert args.source.resolve() != args.output.resolve() and not args.output.exists() and not args.report.exists()
    depth, countries, fra, buffer, changes = 0, None, None, [], []
    digest = hashlib.sha256()
    with args.source.open("rb") as stream, args.output.open("xb") as target:
        for line in stream:
            before = depth
            if before == 0 and line.strip() == b"countries={":
                countries = before + 1
            if countries is not None and before == countries and line.strip() == b"FRA={":
                fra = before
            if fra is not None:
                buffer.append(line)
            else:
                target.write(line); digest.update(line)
            depth += brace_delta(line)
            if fra is not None and depth == fra:
                assert sum(map(len, buffer)) < 1024 * 1024
                block, edit = prepare_fra(buffer)
                target.write(block); digest.update(block)
                changes.append(edit); fra = None; buffer = []
            if countries is not None and depth < countries:
                countries = None
    assert depth == 0 and len(changes) == 1
    report = {"status": "passed", "source": str(args.source.resolve()),
              "output": str(args.output.resolve()), "sha256": digest.hexdigest(),
              "changes": changes, "ledger_edited": False, "business_result_edited": False}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.open("x", encoding="utf-8").write(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({key: report[key] for key in ("status", "output", "sha256")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
