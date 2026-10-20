"""Confirm and reuse the existing R68 non-core Release Nation scene."""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work.verify_r67_ally_save import scan_save


def main():
    delivery = json.loads((ROOT / "work/runtime/r68-progress.json").read_text(encoding="utf-8"))
    saved = delivery["save_references"]["save_returned"]
    source = Path(saved["path"])
    output = ROOT / "work/runtime/r69-release-oe-scene-20261019-001"
    assert source.is_file() and not output.exists()
    observed = scan_save(source)
    province = observed["provinces"]["targets"]["88"]
    report = {"stage": "R69", "status": "reused_existing_scene", "source": saved,
              "source_identity_report": "work/runtime/r68-progress.json",
              "purpose": "Release Nation PIC loss/gain net overextension",
              "mutation_count": 0, "save_hash_recomputed": False, "observation": observed,
              "preparation_correction": "The first remove-core attempt found no BUR core; its temporary copy was removed. Reuse the existing non-core scene."}
    report["checks"] = {
        "source_r68_returned": source.name == "llm_diplomacy_r68_diplomats_returned_20261019.eu4",
        "pic_core_present": "PIC" in province["cores"],
        "bur_core_absent": "BUR" not in province["cores"],
        "owner_bur": province["owner"] == "BUR",
        "province_complete": province["complete"] is True,
        "player_por": observed["metadata"]["player"] == "POR",
        "date_1455_10_18": observed["metadata"]["date"] == "1455.10.18",
    }
    assert all(report["checks"].values())
    output.mkdir()
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "save": str(source),
                      "sha256": saved["sha256"], "checks": report["checks"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
