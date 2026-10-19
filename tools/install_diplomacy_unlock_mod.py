"""Install/enable the isolated diplomacy unlock mod, preserving other mods."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_diplomacy_unlock_mod import EXE_SHA, NAME

ENTRY = f"mod/{NAME}.mod"


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_source(source: Path):
    manifest = json.loads((source / "unlock-manifest.json").read_text(encoding="utf-8"))
    if manifest["exe_sha256"] != EXE_SHA or manifest["runtime_verified"] is not False:
        raise ValueError("unexpected unlock manifest")
    for rel, expected in manifest["files"].items():
        path = source / rel
        if not path.resolve().is_relative_to(source.resolve()):
            raise ValueError("manifest escapes mod directory")
        if path.stat().st_size != expected["bytes"] or sha256(path) != expected["sha256"]:
            raise ValueError(f"generated mod bytes changed: {rel}")
    actual = {p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()}
    if actual != set(manifest["files"]) | {"unlock-manifest.json"}:
        raise ValueError("unexpected files in generated mod")
    return manifest


def install(user_data: Path, game_root: Path, *, source=None, disable=False):
    user_data, game_root = user_data.resolve(), game_root.resolve()
    source = (source or ROOT / "mod" / NAME).resolve()
    settings = user_data / "dlc_load.json"
    original = settings.read_bytes()
    config = json.loads(original.decode("utf-8-sig"))
    entries = config.get("enabled_mods")
    if not isinstance(entries, list) or not all(isinstance(x, str) for x in entries):
        raise ValueError("enabled_mods must be a string array")
    if not disable and sha256(game_root / "eu4.exe") != EXE_SHA:
        raise ValueError("this mod is pinned to the exact installed EU4 1.37.5 executable")
    manifest = None if disable else verify_source(source)
    installed = user_data / "mod" / NAME
    descriptor = user_data / "mod" / f"{NAME}.mod"
    for target in (installed, descriptor):
        if not target.resolve().is_relative_to(user_data / "mod") or target.is_symlink():
            raise ValueError("unsafe destination")
    backup = ROOT / "work/backup" / ("diplomacy-unlock-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    backup.mkdir(parents=True)
    (backup / "dlc_load.json").write_bytes(original)
    for path in (installed, descriptor):
        if path.is_dir():
            shutil.copytree(path, backup / path.name)
        elif path.is_file():
            shutil.copy2(path, backup / path.name)
    if disable:
        config["enabled_mods"] = [x for x in entries if x != ENTRY]
    else:
        shutil.copytree(source, installed, dirs_exist_ok=True)
        descriptor.write_text((source / "descriptor.mod").read_text(encoding="utf-8") + f'\npath="mod/{NAME}"\n', encoding="utf-8")
        # Highest precedence among the user's enabled mods; preserve their order.
        config["enabled_mods"] = [x for x in entries if x != ENTRY] + [ENTRY]
        for rel, pin in manifest["files"].items():
            if sha256(installed / rel) != pin["sha256"]:
                raise RuntimeError(f"installed bytes differ: {rel}")
    if settings.read_bytes() != original:
        raise RuntimeError("launcher changed its configuration; configuration not replaced")
    temp = settings.with_name(f"dlc_load.unlock-{uuid.uuid4().hex}.tmp")
    with temp.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(config, stream, ensure_ascii=False)
    temp.replace(settings)
    result = {
        "installed": not disable, "enabled": ENTRY in config["enabled_mods"],
        "mod_path": str(installed), "backup": str(backup),
        "prior_enabled_mods": entries, "enabled_mods": config["enabled_mods"],
        "disabled_dlcs_preserved": config.get("disabled_dlcs"),
        "base_game_modified": False, "restart_required": True,
        "runtime_verified": False, "all_native_conditions_bypassed": False,
        "counts": manifest["counts"] if manifest else None,
    }
    (backup / "install-receipt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-data", type=Path, default=Path.home() / "Documents/Paradox Interactive/Europa Universalis IV")
    parser.add_argument("--game-root", type=Path, default=ROOT.parent)
    parser.add_argument("--disable", action="store_true")
    args = parser.parse_args()
    print(json.dumps(install(args.user_data, args.game_root, disable=args.disable), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
