"""Prepare an isolated single-field fixture, leaving active mod list unchanged.

The fixture uses normal country modifier script, not an action gate patch.
It is only eligibility preparation, never evidence of native API success.
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_diplomacy_catalog import parse_script

NAME = "llm_diplomacy_range_20261015"
KEY = "llm_knowledge_range_fixture_20261015"
USER = Path.home()/"Documents/Paradox Interactive/Europa Universalis IV"


def pin(path):
    raw = path.read_bytes()
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def exclusive(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as f:
        f.write(raw)


def main():
    settings = USER/"dlc_load.json"
    before = settings.read_bytes()
    assert hashlib.sha256(before).hexdigest() == "d75f9abede329fd177497c7dc5ad601f7681cd1962b4b090602d6a6ba7d9bd8b"
    config = json.loads(before)
    assert f"mod/{NAME}.mod" not in config["enabled_mods"]
    source = ROOT/"mod"/NAME
    installed = USER/"mod"/NAME
    descriptor = USER/"mod"/(NAME+".mod")
    assert not source.exists() and not installed.exists() and not descriptor.exists()
    assert installed.resolve().is_relative_to((USER/"mod").resolve())
    text = f"{KEY} = {{ range = 2.2 }}\n"
    parsed = parse_script(text)
    assert len(parsed) == 1 and parsed[0].key == KEY and len(parsed[0].children) == 1
    assert parsed[0].children[0].key == "range" and parsed[0].children[0].value == "2.2"
    desc = f'name="LLM Diplomacy Range Fixture 20261015"\nversion="1.0"\nsupported_version="1.37.5"\n'
    files = {"descriptor.mod":desc, "common/event_modifiers/zz_llm_knowledge_range_20261015.txt":text}
    produced = {}
    for rel, value in files.items():
        raw = value.encode("utf-8")
        exclusive(source/rel, raw)
        exclusive(installed/rel, raw)
        produced[str(source/rel)] = pin(source/rel)
        produced[str(installed/rel)] = pin(installed/rel)
    exclusive(descriptor, (desc+f'path="mod/{NAME}"\n').encode("utf-8"))
    produced[str(descriptor)] = pin(descriptor)
    for operation, effect in (("apply", f"add_country_modifier = {{ name = {KEY} duration = 3650 }}"),
                              ("revert", f"remove_country_modifier = {KEY}")):
        target = ROOT.parent/f"llm_knowledge_range_20261015_{operation}.txt"
        exclusive(target, (f"FRA = {{ {effect} }}\n").encode("utf-8"))
        produced[str(target)] = pin(target)
    assert settings.read_bytes() == before
    receipt = dict(schema="EU4-KNOWLEDGE-RANGE-FIXTURE-PREPARATION/1", files=produced,
        game_sha256=pin(ROOT.parent/"eu4.exe")["sha256"], modifier_key=KEY, field="range", value="2.2",
        settings_sha256=hashlib.sha256(before).hexdigest(), enabled=False, loaded=False, applied=False,
        active_mod_list_unchanged=True, default_unlock_mod_unchanged=True, native_calls=0,
        requests_published=0, action_gate_modified=False, api_success_proven=False,
        requires=["Enable isolated fixture then normally restart/load the preserved test checkpoint once",
            "Use normal script apply once, then verify exact live modifier/range and all remaining conditions",
            "Only an independently eligible clean-rejected action may receive a new test-only ID"])
    out=ROOT/"work/reports/diplomacy-corrective-20261014-r3/knowledge-range-override/fixture-preparation-20261015.json"
    exclusive(out, json.dumps(receipt,indent=2).encode("utf-8"))
    print(json.dumps({k:receipt[k] for k in ("modifier_key","field","value","enabled","loaded","applied",
        "active_mod_list_unchanged","native_calls","api_success_proven")}))


if __name__ == "__main__":
    main()
