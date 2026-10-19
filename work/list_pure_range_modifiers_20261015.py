"""Offline inventory of original event modifiers containing only range.

This is preparation evidence, not loaded-definition or applied-effect proof.
Uses the existing bounded Clausewitz parser; never changes game/mod files.
"""
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work.inspect_diplomacy_save import BoundedReader, events


def main():
    directory = ROOT.parent / "common/event_modifiers"
    files, candidates = [], []
    for path in sorted(directory.glob("*.txt")):
        raw = path.read_bytes()
        if len(raw) > 2*1024*1024:
            raise ValueError("Original modifier file exceeds input bound")
        files.append(dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
        reader = BoundedReader(io.BytesIO(b"EU4txt\n" + raw.removeprefix(b"\xef\xbb\xbf")))
        depth, current = 0, None
        for kind, key, token in events(reader):
            if kind == "start":
                if depth == 0:
                    current = dict(key=key, path=str(path), line=token[2]-1, fields=[], nested=False)
                elif current:
                    current["nested"] = True
                depth += 1
            elif kind == "end":
                depth -= 1
                if depth == 0 and current:
                    if not current["nested"] and len(current["fields"]) == 1 and current["fields"][0][0] == "range":
                        try:
                            bonus = float(current["fields"][0][1])
                        except ValueError:
                            bonus = 0
                        if 0 < bonus <= 100:
                            candidates.append({k:v for k,v in current.items() if k not in ("fields", "nested")} | {"range":bonus})
                    current = None
            elif current:
                if depth == 1 and kind == "scalar":
                    current["fields"].append((key, token[1].decode("ascii")))
                else:
                    current["nested"] = True
    output = ROOT / "work/reports/diplomacy-corrective-20261014-r3/knowledge-range-override/pure-original-modifiers.json"
    result = dict(schema="EU4-PURE-RANGE-INVENTORY/1", files=files, candidates=candidates,
        native_calls=0, memory_written=False, loaded_definition_identity_verified=False,
        installed_mod_overrides_checked=False, fixture_applied=False,
        limitations=["Original file inventory does not prove the active mod stack preserves these definitions.",
            "No candidate is authorized as a repaired native eligibility condition until loaded identity and live range are read."])
    with output.open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(dict(output=str(output), file_count=len(files), candidates=len(candidates),
        largest=sorted(candidates,key=lambda x:-x["range"])[:8], native_calls=0, fixture_applied=False)))


if __name__ == "__main__":
    main()
