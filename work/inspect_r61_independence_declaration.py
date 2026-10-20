"""Inspect a native independence declaration in the current paused scene."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work.local_config import game_exe

directory = ROOT / "work/runtime/r61-independence-native-declaration-20261019-002"
directory.mkdir(exist_ok=False)
installation = ROOT / "work/runtime/diplomacy-query-20261019-r61-country-independence-c/installation.json"
session = ObserverSession(installation, game_exe())
with DurableJournal(directory / "diplomacy.sqlite3", session.experiment_id,
                    session.session_id, global_request_ids=True) as journal:
    api = DiplomacyTools(journal, session)
    for name, parameters in (
            ("discover", {}),
            ("selected", {"casus_belli": "cb_independence_war",
                          "war_goal": {"province_id": -1, "beneficiary": "FRA"},
                          "call_allies": []})):
        result = api.inspect_diplomatic_action("declare_war", "FRA", "ENG",
                                               parameters=parameters)
        (directory / (name + ".json")).write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"case": name, "legality": result.get("legality"),
                          "parameters": result.get("parameters")}, ensure_ascii=False)[:6500])
