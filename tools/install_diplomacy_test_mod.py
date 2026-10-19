"""Install an isolated zero-cooldown test mod; preserve other enabled mods."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work"))
sys.path.insert(0, str(ROOT))
from local_config import game_root, user_data

NAME = "llm_diplomacy_test"
ENTRY = f"mod/{NAME}.mod"


def install(destination: Path, game: Path, tags: list[str], *, enable=False, disable=False,
            fixture_profile="original") -> dict:
    if enable and disable:
        raise ValueError("enable and disable are mutually exclusive")
    if not tags or len(tags) > 100 or any(not re.fullmatch(r"[A-Z][A-Z0-9]{2}", tag) for tag in tags):
        raise ValueError("countries must be up to 100 three-character uppercase EU4 tags")
    destination = destination.resolve()
    settings = destination / "dlc_load.json"
    original = settings.read_bytes()
    config = json.loads(original.decode("utf-8-sig"))
    enabled = config.get("enabled_mods")
    if not isinstance(enabled, list) or not all(isinstance(item, str) for item in enabled):
        raise ValueError("dlc_load.json enabled_mods must be a string array")
    source = ROOT / "mod" / NAME
    profile_sha = None
    if fixture_profile in ("v8", "v9", "v10"):
        if fixture_profile == "v8":
            from work.native import lab_protocol_v8_1375 as lab
        elif fixture_profile == "v9":
            from work.native import lab_protocol_v9_1375 as lab
        else:
            from work.native import lab_protocol_v10_1375 as lab
        lab.fixture_profile()  # Hash all five reviewed candidate files before mutation.
        source = ROOT / lab.FIXTURE_CANDIDATE_ROOT / "mod" / NAME
        profile_sha = lab.FIXTURE_PROFILE_SHA256
        for path in (settings, destination / "mod" / NAME, destination / "mod" / f"{NAME}.mod"):
            lab._no_links(path)
    elif fixture_profile != "original":
        raise ValueError("unknown test fixture profile")
    defines = (game / "common/defines.lua").read_text(encoding="utf-8-sig")
    if not re.search(r"DIPLOMAT_COOLDOWN_TIME\s*=\s*1\s*,", defines):
        raise ValueError("unexpected base-game diplomat cooldown; review before installing")
    backup = ROOT / "work/backup" / ("diplomacy-test-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    backup.mkdir(parents=True)
    (backup / "dlc_load.json").write_bytes(original)
    mod_dir = destination / "mod" / NAME
    descriptor = destination / "mod" / f"{NAME}.mod"
    for item in (mod_dir, descriptor, destination / "llm_test_diplomats_on.txt", destination / "llm_test_diplomats_off.txt"):
        if item.exists():
            if item.is_dir():
                shutil.copytree(item, backup / item.name)
            else:
                shutil.copy2(item, backup / item.name)
    if not disable:
        shutil.copytree(source, mod_dir, dirs_exist_ok=True)
        descriptor.write_text((source / "descriptor.mod").read_text(encoding="utf-8") + f'\npath="mod/{NAME}"\n', encoding="utf-8")
        for state, effect in (("on", "remove_country_modifier = llm_diplomacy_test_pool add_country_modifier = { name = llm_diplomacy_test_pool duration = -1 }"),
                              ("off", "remove_country_modifier = llm_diplomacy_test_pool")):
            script = "\n".join(f"{tag} = {{ {effect} }}" for tag in dict.fromkeys(tags)) + "\n"
            (destination / f"llm_test_diplomats_{state}.txt").write_text(script, encoding="ascii")
    if disable:
        config["enabled_mods"] = [entry for entry in enabled if entry != ENTRY]
    elif enable and ENTRY not in enabled:
        config["enabled_mods"] = enabled + [ENTRY]
    if enable or disable:
        # Do not replace a configuration concurrently changed by the launcher.
        if settings.read_bytes() != original:
            raise RuntimeError("launcher settings changed during install; no configuration written")
        temp = settings.with_name("dlc_load.llm_test.tmp")
        with temp.open("x", encoding="utf-8", newline="\n") as file:
            json.dump(config, file, ensure_ascii=False)
        temp.replace(settings)
    return {"installed": not disable, "enabled": ENTRY in config["enabled_mods"],
            "mod": str(mod_dir), "backup": str(backup), "countries": tags,
            "additional_diplomats": 100, "cooldown_months": 0, "runtime_verified": False,
            "fixture_profile": fixture_profile, "fixture_profile_sha256": profile_sha,
            "restart_required": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path)
    parser.add_argument("--user-data", type=Path)
    parser.add_argument("--countries", nargs="+", default=["FRA", "ENG", "POR"])
    parser.add_argument("--fixture-profile", choices=("original", "v8", "v9", "v10"), default="original",
                        help="v8 adds empty close options; v9/v10 use the same NAV-vassal fixture on an independent, unallied test baseline; original preserves historical definitions")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--enable", action="store_true")
    group.add_argument("--disable", action="store_true")
    args = parser.parse_args()
    print(json.dumps(install(args.user_data or user_data(), args.game_root or game_root(), args.countries,
                             enable=args.enable, disable=args.disable, fixture_profile=args.fixture_profile), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
