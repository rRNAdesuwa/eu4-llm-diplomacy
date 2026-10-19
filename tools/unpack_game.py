"""Copy loose scripts and extract installed archive scripts for offline research.

Assets stay in their original package namespaces; this is not a DLC loader and
does not infer load order. No executable, archive, save or game file is changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

SCRIPT_ROOTS = {"common", "events", "decisions", "missions", "interface",
                "localisation", "localisation_synced", "history", "tests"}
EXTENSIONS = {".txt", ".lua", ".gui", ".gfx", ".yml", ".json", ".csv"}
MAX_MEMBER = 64 * 1024 * 1024
MAX_TOTAL = 2 * 1024 * 1024 * 1024


def safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or not path.parts or any(p in ("..", "") or ":" in p for p in path.parts):
        raise ValueError(f"Unsafe archive path: {name!r}")
    return path


def selected(path: PurePosixPath) -> bool:
    return path.parts[0].lower() in SCRIPT_ROOTS and path.suffix.lower() in EXTENSIONS


def unpack(game: Path, destination: Path) -> dict:
    game, destination = game.resolve(), destination.resolve()
    if not (game / "eu4.exe").is_file():
        raise ValueError("game root must contain eu4.exe")
    if destination.exists():
        raise ValueError("output already exists; choose a fresh directory")
    destination.mkdir(parents=True)
    total = 0
    entries, packages = [], []

    def copy_stream(source, target: Path, expected_size: int, origin: str):
        nonlocal total
        if expected_size > MAX_MEMBER or total + expected_size > MAX_TOTAL:
            raise ValueError("research extraction size limit exceeded")
        target.parent.mkdir(parents=True, exist_ok=True)
        digest, actual = hashlib.sha256(), 0
        with target.open("xb") as out:
            while chunk := source.read(1024 * 1024):
                actual += len(chunk)
                if actual > expected_size:
                    raise ValueError("source grew beyond declared size")
                digest.update(chunk)
                out.write(chunk)
        if actual != expected_size:
            raise ValueError("source size changed while extracting")
        total += actual
        entries.append({"origin": origin, "path": target.relative_to(destination).as_posix(),
                        "bytes": actual, "sha256": digest.hexdigest()})

    for root in sorted(SCRIPT_ROOTS):
        for file in sorted((game / root).rglob("*")):
            if file.is_file() and not file.is_symlink() and file.suffix.lower() in EXTENSIONS:
                relative = file.relative_to(game)
                with file.open("rb") as source:
                    copy_stream(source, destination / "base" / relative, file.stat().st_size, relative.as_posix())
    archives = sorted(path for root in ("dlc", "builtin_dlc") for path in (game / root).rglob("*.zip"))
    for archive in archives:
        relative = archive.relative_to(game)
        count = 0
        with zipfile.ZipFile(archive) as package:
            for info in package.infolist():
                member = safe_member(info.filename)
                if info.is_dir() or not selected(member):
                    continue
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError("archive symlinks are not supported")
                with package.open(info) as source:
                    copy_stream(source, destination / "archives" / relative.with_suffix("") / Path(member),
                                info.file_size, f"{relative.as_posix()}!{member}")
                count += 1
            packages.append({"archive": relative.as_posix(), "members": len(package.infolist()),
                             "extracted_scripts": count})
    result = {"schema_version": 1, "scope": "installed loose and archived scripts; graphics/audio excluded",
              "load_order_resolved": False, "packages": packages, "files": entries, "total_bytes": total}
    (destination / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"output": str(destination), "archives": len(packages), "files": len(entries), "bytes": total}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(unpack(args.game_root, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
