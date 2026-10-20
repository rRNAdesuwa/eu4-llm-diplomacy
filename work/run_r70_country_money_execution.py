"""Use the country batch operator for one outbound Release PIC + 1 ducat offer."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work import run_peace_country_execution_batch as batch


if __name__ == "__main__":
    # This operator deliberately stops after the native AI response. Incoming
    # synthetic fixtures for a mixed offer have not been added to this scene.
    batch.SCENARIOS["release"] = {
        "primary_action": "release_nation",
        "outbound_recipient": "BUR", "incoming_actor": "BUR",
        "fixture_base": "BUR_PEACE_FRA_RELEASE_PIC_MONEY",
        "terms": (
            {"action_id": "release_nation", "country": "PIC", "source": "BUR"},
            {"action_id": "demand_ducats", "amount": "1.0", "payer": "BUR", "claimant": "FRA"},
        ),
        "countries": ("FRA", "BUR", "PIC"), "provinces": ("88", "89"), "pairs": (),
    }
    if any(arg in sys.argv[1:] for arg in ("--kind", "--through")):
        raise SystemExit("R70_OUTBOUND_ONLY_OPERATOR")
    sys.argv[1:] = ["--kind", "release", "--through", "outbound", *sys.argv[1:]]
    raise SystemExit(batch.main())
