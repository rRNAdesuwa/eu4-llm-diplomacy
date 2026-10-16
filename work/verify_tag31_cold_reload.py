"""Compare selected final-save state with a UI save after cold reload."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work.inspect_diplomacy_save import inspect_save
from work.compare_tag31_saves import compare


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2)+"\n").encode("utf-8")


def main():
    pid = 61988
    creation = "01dd5acc83b0078c"
    user_data = Path.home()/"Documents/Paradox Interactive/Europa Universalis IV"
    source = user_data/"save games/法兰西1445_02_16r.eu4"
    copied = user_data/"save games/llm_diplomacy_1375_tag31_reload.eu4"
    finish_existing = sys.argv[1:] == ["--finish-existing"]
    assert sys.argv[1:] in ([], ["--finish-existing"])
    assert source.stat().st_size < 512*1024*1024
    if not finish_existing:
        with source.open("rb") as stream, copied.open("xb") as target:
            while chunk := stream.read(1024*1024):
                target.write(chunk)
    health = ROOT/f"work/runtime/tag31-health-{pid}.json"
    mod_load = ROOT/f"work/runtime/tag31-mod-load-{pid}.json"
    load = json.loads(mod_load.read_bytes())
    assert (load["pid"], load["creation"]) == (pid, creation)
    assert load["tag_diplomacy_dll_loaded"] is False and load["native_calls"] == 0
    groups = []
    for suffix in ("group1", "group2", "rivals-coalition"):
        before_path = ROOT/f"work/runtime/tag31-effects-final-20261013-{suffix}.json"
        before_raw = before_path.read_bytes()
        before = json.loads(before_raw)
        assert before["source"]["sha256"].lower() == "7bf6d888747d178d9f545fc7278cbf7342be28ea84a0f4e7a4ecd82fde83ae07"
        after_path = ROOT/f"work/runtime/tag31-effects-reload-20261013-{suffix}.json"
        if finish_existing:
            after_raw = after_path.read_bytes()
            after = json.loads(after_raw)
        else:
            after = inspect_save(copied, actor=before["actor"], targets=before["targets"], effect_fields=True)
            after_raw = encoded(after)
            with after_path.open("xb") as stream:
                stream.write(after_raw)
        assert before["metadata"]["date"]["value"] == after["metadata"]["date"]["value"] == "1445.2.16"
        extra_fields = set(after["selected_effect_fields"])-set(before["selected_effect_fields"])
        assert set(before["selected_effect_fields"]) <= set(after["selected_effect_fields"])
        if extra_fields:
            after["selected_effect_fields"] = before["selected_effect_fields"]
            for country in after["countries"].values():
                country["fields"] = [n for n in country["fields"] if n["key"] not in extra_fields]
            after["comparison_scope_projection"] = dict(
                original_extract_sha256=hashlib.sha256(after_raw).hexdigest(),
                removed_extra_field_keys=sorted(extra_fields), raw_extract_preserved=True)
            after_raw = encoded(after)
            scoped_path = after_path.with_name(after_path.stem+"-scoped.json")
            with scoped_path.open("xb") as stream:
                stream.write(after_raw)
        groups.append((before_raw, after_raw))
    delta = compare(groups)
    delta_path = ROOT/"work/runtime/tag31-effects-reload-diff-20261013.json"
    with delta_path.open("xb") as stream:
        stream.write(encoded(delta))
    counts = {}
    for tag, entry in delta["countries"].items():
        counts[tag] = dict(fields_added=len(entry["fields"]["added"]),
                          fields_removed=len(entry["fields"]["removed"]),
                          diplomats_added=len(entry["diplomats"]["added"]),
                          diplomats_removed=len(entry["diplomats"]["removed"]),
                          changed_pair_relations=len(entry["relations"]))
    report = dict(schema="EU4TAG31-COLD-RELOAD/1", pid=pid, creation=creation,
                  native_calls=0, diplomatic_requests_sent=0, date="1445.2.16",
                  input_save_sha256=delta["before_save_sha256"],
                  reserialized_save_sha256=delta["after_save_sha256"],
                  ui_saved_path=str(source), named_copy_path=str(copied),
                  loaded_mod_evidence_sha256=hashlib.sha256(mod_load.read_bytes()).hexdigest(),
                  health_sha256=hashlib.sha256(health.read_bytes()).hexdigest(),
                  diff_sha256=hashlib.sha256(delta_path.read_bytes()).hexdigest(),
                  selected_country_count=len(counts), differences=counts,
                  global_added=len(delta["global_diplomacy"]["added"]),
                  global_removed=len(delta["global_diplomacy"]["removed"]),
                  all_diplomatic_effects_verified=False, gameplay_causality_proven=False,
                  comparison_scope_projected=True, initial_scope_mismatch_preserved=True,
                  limitations=["Cold load, followed by paused reserialization of selected state only.",
                               "Neither the 120 actions nor any successful action was executed again.",
                               "Differences may be reload normalization and do not prove new command effects.",
                               "The saved original vassal types cannot be repaired retroactively by the new helper guard."])
    output = ROOT/"work/runtime/tag31-cold-reload-20261013.json"
    with output.open("xb") as stream:
        stream.write(encoded(report))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
