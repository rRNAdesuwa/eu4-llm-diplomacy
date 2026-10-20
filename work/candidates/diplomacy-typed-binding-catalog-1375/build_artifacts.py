"""Author-only deterministic artifacts. Never writes outside this candidate."""
from pathlib import Path
import argparse
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
COMMON = [
    "No registered production execution backend",
    "No authenticated current process/session/world-generation binding",
    "No strict single-player origin or engine world-lifetime synchronization proof",
    "No consuming-owner-thread recheck of pause, full country identities and native permissions",
    "No durable native dispatch/ownership/unknown-result reconciliation for this binding",
]
SOURCES = ["bridge/diplomacy_api.py", "bridge/diplomacy_catalog.json"]
GROUPS = {
    "spy5": "spy-action-contracts-1375",
    "normal_spy4": "spy-four-normal-callers-contract-1375",
    "curry": "curry-favors-contract-1375",
    "focus": "subject-military-focus-contract-1375",
    "toggle": "subject-toggle-contracts-1375",
    "extra": "spy-extra-parameter-contracts-1375",
}


def read(path):
    with path.open("rb") as stream:
        data = stream.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise ValueError("Source exceeds fixed 2 MiB budget")
    return data

for folder in GROUPS.values():
    for name in ("report.json", "contract.json", "facts.json", "review.json"):
        rel = f"work/candidates/{folder}/{name}"
        if (ROOT / rel).is_file():
            SOURCES.append(rel)
SOURCES += [
    "work/candidates/v18-spy-no-send-contract-1375/review.json",
    "work/candidates/v18-spy-no-send-core-1375/review.json",
    "work/review-results/v18-spy-no-send-native-inventory-20261008a/review.json",
    "work/review-results/v18-spy-core-action-catalog-20261008a/review.json",
    "work/runtime/unpacked-1.37.5/base/common/new_diplomatic_actions/00_diplomatic_actions.txt",
]


def evidence(group):
    return [p for p in SOURCES if f"/{GROUPS[group]}/" in p]


def binding(kind, group, token, fixed, requires, semantics, **extra):
    return dict(binding_kind=kind, evidence=evidence(group), native_token=token,
                fixed_fields=fixed, unresolved=requires, semantics=semantics, **extra)


def artifacts():
    actions = {}
    for name, token in {
        "corrupt_officials": 0x337c, "sabotage_reputation": 0x2ddd,
        "sow_discontent": 0x2ddf, "slander_merchants": 0x337b,
        "sabotage_recruitment": 0x33bf,
    }.items():
        actions[name] = binding("owned_action", "spy5", token,
            {"value": True, "state": 0, "envoy_id": -1},
            ["Current capability and adjusted spy-network cost",
             "Owner-thread full family preview (+88), distinct from action +80 and owned-command gate +40",
             "Live no-send host integration and native transport remain unavailable"],
            ["False is not a proved cancellation/undo mode",
             "Full family preview may initialize TLS/caches; it is not read-only",
             "Owned command destroys its clone; unresolved ownership forbids cleanup guesses/retry"],
            normal_ai_initialization_evidence=True,
            source_mock_profile="v18-spy-no-send: five fixed families, FRA->ENG, lifecycle/family_preview/owned_command only")
        actions[name]["evidence"] += evidence("normal_spy4")
    for name, value in (("curry_favors", True), ("stop_currying_favors", False)):
        actions[name] = binding("owned_action", "curry", 0x3acc,
            {"value": value, "state": 0, "envoy_id": -1},
            ["Full actor/target relationship, mission and envoy graph",
             "Current command/AI acceptance and consuming-thread authorization"],
            ["Cancel uses the same action family and keeps envoy_id=-1",
             "Relation/mission removal does not prove favors amount, accrual rate or persistence"])
    focus = json.loads(read(ROOT / f"work/candidates/{GROUPS['focus']}/contract.json"))
    actions["subject.set_military_focus"] = binding("already_command", "focus", 0x3017,
        {}, ["Full overlord/subject/dependency identity and allowed definition",
             "Both uses_military_focus and can_set_mil_focus plus current enum entitlement",
             "Clone consumes a temporary engine String32; no zero-argument clone ABI",
             "Final queue consumer authorization and ownership"],
        ["Native command gate alone does not prove overlord/player authority",
         "TLS-backed availability helpers are not read-only permission proofs"], enum_binding=focus["enum"])
    toggles = json.loads(read(ROOT / f"work/candidates/{GROUPS['toggle']}/contract.json"))
    for name, facts in toggles["families"].items():
        more = {
            "embargo_rivals": "Enabling requires rival list; per-rival effects may fail independently",
            "scutage": "Both directions require target not at war; cancel modifier vector/layout differs from spy modifiers",
            "divert_trade": "Disabling may restore default 50% trade power, not relation absence",
        }[name]
        actions[f"subject.{name}"] = binding("desired_state_subject_command", "toggle", facts["token"], {},
            ["Full current subject/overlord graph and loaded borrowed singleton registration",
             "Current subject flag and active overlord-handle high byte",
             "Complete common/stale-state/family permissions and exact command clone ownership"],
            ["enabled is a desired state, never a caller-selected raw cancel bit",
             "Only a live binder may return already_desired; this module has no current-state authority",
             "On transition, constructor snapshots current flag as cancel; recheck before handoff; never silently rebuild",
             more], flag_mask=facts["mask"])
    actions["steal_maps"] = binding("selected_region_action", "extra", 0x33c8,
        {"value": True, "state": 0, "envoy_id": -1},
        ["Bounded live region registry, index membership, name/type and lifetime",
         "Full family permissions, adjusted costs and owned transport"],
        ["Native +40 is a signed region index; default -1 is only generic candidate search",
         "value=false is not undo; the selected index is not a public string-to-index mapping"],
        schema_migration={"removed": "region_id", "added": "region_index", "native_binding_complete": False})
    actions["support_rebels"] = binding("borrowed_faction_action", "extra", 0x2dde,
        {"value": True, "state": 0, "envoy_id": -1},
        ["Resolve exactly one matching +10/+14 identity in selected target's bounded faction pointer vector",
         "Prove full target/type/faction/supporter identity and borrowed lifetime through queued execution",
         "Normal selected owning caller, current full preview and treasury cost formula"],
        ["Two DWORD serialized identity is not a pointer or sufficient live ownership proof",
         "Clone borrows the faction; never destroy it as an action-owned allocation"],
        schema_migration={"removed": "rebel_faction_id", "added": "faction_identity", "native_binding_complete": False})
    actions["stop_supporting_rebels"] = binding("unsupported_false_mode", "extra", 0x2dde, {},
        ["No ordinary false-mode interface: full family preview rejects false",
         "False effect searches first actor-supported faction, not selected +40; normal owning caller unclosed"],
        ["Catalog name is discoverable; no executable cancellation is derived from it"])
    actions["steal_modern_ideas"] = binding("fixed_borrowed_script_definition", "extra", 0x3662,
        {"definition_name": "steal_modern_ideas", "value": True, "state": 0, "envoy_id": -1},
        ["Loaded named definition identity, condition, borrowing lifetime and current exact script hashes",
         "Registry getter may initialize data; cannot be treated as read-only resolution",
         "Actual government mechanic and 24/30 spy-network script conditions"],
        ["Stock definition changes Russian modernization government power, not technology levels",
         "No generic steal-technology interface or caller-supplied script/definition/event"])
    actions["steal_modern_ideas"]["evidence"].append(SOURCES[-1])
    return {"schema_version": 1, "protocol": "EU4DIPLOMACY-CONTRACT/2", "common_blockers": COMMON,
            "actions": actions, "production_supported": False, "live_readiness": None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    pins, total = {}, 0
    for name in SOURCES:
        data = read(ROOT / name)
        total += len(data)
        if total > 16 * 1024 * 1024 or len(pins) >= 64:
            raise ValueError("Aggregate source budget")
        pins[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    for path, value in ((HERE / "bindings.json", artifacts()),
                        (HERE / "input-pins.json", pins)):
        data = (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("ascii")
        if args.check:
            if read(path) != data:
                raise ValueError(f"Generated artifact differs: {path.name}")
            continue
        with path.open("xb") as stream:
            stream.write(data)


if __name__ == "__main__":
    main()
