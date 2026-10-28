"""Reconcile saved owner results into the delivery index; no game access."""
import collections
import json
from pathlib import Path


def reconcile(payload):
    base = Path(__file__).parent
    owner = json.loads((base / "live-owner-results.json").read_text(encoding="utf-8-sig"))
    payload["live"]["scope"] = "historical_tag_host_session"
    payload["owner_live"] = owner
    outcomes = {row["action"]: row for row in owner["production"]}
    for row in payload["action_rows"]:
        if row["live_state"] == "offline_validated_typed_backend_unavailable":
            row["live_state"] = "offline_validated"
        if row["action"] in outcomes:
            value = outcomes[row["action"]]
            row.setdefault("prior_evidence", row["evidence"])
            row["live_state"] = "live_effect_observed" if value.get("status", {}).get("submitted") is True and value.get("effect", {}).get("after") else "live_native_rejected"
            row["evidence"] = {"source": "live-owner-results.json", "request_id": value["request_id"],
                               "status": value.get("status"), "effect": value.get("effect")}
    payload["summary"]["by_live_state"] = dict(collections.Counter(row["live_state"] for row in payload["action_rows"]))
    payload["summary"]["current_evidence_source"] = "live-owner-results.json"
    payload["followups"] = [
        "Connect send=0 to the current release build before live preview testing.",
        "Choose an eligible subject action using the actual subject type and ability; support_loyalists was rejected.",
        "Cover call_to_arms, enforce_peace and intervene_in_war in real wars; the latest saved fixture has no wars.",
        "Use actual units, fleets, rebel factions, tributary pending objects and governor events for typed action coverage.",
        "Join governor-option execution to its selected-effect evidence.",
        "Reuse successful evidence; perform one concentrated regression before final release."
    ]
    return payload


if __name__ == "__main__":
    path = Path(__file__).with_name("results.json")
    payload = reconcile(json.loads(path.read_text(encoding="utf-8-sig")))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=True))
