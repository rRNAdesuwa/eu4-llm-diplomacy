"""Read-only load/configuration evidence; never tests a diplomacy action."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.tag_command_backend import WindowsRuntime
from tools.install_diplomacy_unlock_mod import ENTRY, NAME, verify_source


def main():
    pid, creation = int(sys.argv[1]), sys.argv[2]
    output = ROOT / f"work/runtime/tag31-mod-load-{pid}.json"
    if output.exists():
        raise ValueError("Load evidence already exists; do not overwrite")
    source = ROOT / "mod" / NAME
    user_data = Path.home() / "Documents/Paradox Interactive/Europa Universalis IV"
    installed = user_data / "mod" / NAME
    manifest = verify_source(source)
    installed_manifest = verify_source(installed)
    assert manifest == installed_manifest
    config_raw = (user_data / "dlc_load.json").read_bytes()
    config = json.loads(config_raw.decode("utf-8-sig"))
    assert config["enabled_mods"][-1] == ENTRY
    health_raw = (ROOT / f"work/runtime/tag31-health-{pid}.json").read_bytes()
    health = json.loads(health_raw)
    assert (health["pid"], health["creation"]) == (pid, creation)
    assert health["manual_pause"] == 1 and health["ironman"] == 0
    assert health["reset"] == 0 and health["load_source"] == 0
    definitions_raw = (ROOT / f"work/runtime/tag31-loaded-definitions-{pid}.json").read_bytes()
    definitions = json.loads(definitions_raw)
    assert (definitions["pid"], definitions["creation"]) == (pid, creation)
    assert not definitions["missing"] and definitions["all_types_match"]
    runtime = WindowsRuntime()
    identity = dict(pid=pid, creation=creation, session="1"*32,
                    dll_sha256="f"*64, manifest_sha256="e"*64)
    held = runtime.readonly.Held(identity)
    try:
        held.identity_check()
        modules = held.modules()
        canonical = held.injector._canonical
        matches = [b for b, p in modules if canonical(p) == canonical(held.injector.GAME)]
        assert len(matches) == 1
        assert not any("tag_diplomacy" in str(p).lower() for _, p in modules)
        base = matches[0]
        data = C.create_string_buffer(4)
        got = C.c_size_t()
        assert held.kernel.ReadProcessMemory(held.handle, C.c_void_p(base + 0x233e064),
                                             data, 4, C.byref(got)) and got.value == 4
        months = struct.unpack("<i", data.raw)[0]
        held.identity_check()
    finally:
        held.close()
    assert months == -1
    error_path = user_data / "logs/error.log"
    assert error_path.stat().st_size <= 1024 * 1024
    error_raw = error_path.read_bytes()
    relevant = [line for line in error_raw.decode("utf-8", "replace").splitlines()
                if any(key in line.lower() for key in (
                    "llm_diplomacy_unlock", "01_scripted_effects_for_diplomacy",
                    "00_diplomatic_actions", "llm_unlock", "subject_types/"))]
    report = dict(schema="EU4TAG31-MOD-LOAD/1", pid=pid, creation=creation,
                  native_calls=0, memory_written=False, game_sha256=manifest["exe_sha256"],
                  installed_files_match_source=True, enabled_last=True,
                  mod_manifest_sha256=hashlib.sha256((source/"unlock-manifest.json").read_bytes()).hexdigest(),
                  health_sha256=hashlib.sha256(health_raw).hexdigest(),
                  definitions_sha256=hashlib.sha256(definitions_raw).hexdigest(),
                  dlc_load_sha256=hashlib.sha256(config_raw).hexdigest(),
                  ordinary_cooldown_months=months, cooldown_rva="0x233e064",
                  special_subject_fallback_disabled_in_installed_script=True,
                  tag_diplomacy_dll_loaded=False, error_log_sha256=hashlib.sha256(error_raw).hexdigest(),
                  error_log_bytes=len(error_raw), relevant_error_lines=relevant,
                  all_native_conditions_bypassed=False, same_day_actions_verified=False,
                  special_subject_effects_verified=False,
                  limitations=["Configuration, definitions and the live cooldown value only; no action sent.",
                               "Existing saved deadlines are unchanged.",
                               "Installed helper bytes do not prove its execution or the resulting subject type.",
                               "Other error-log entries remain; absence of selected lines is not a clean-log claim."])
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({k: v for k, v in report.items() if k != "limitations"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
