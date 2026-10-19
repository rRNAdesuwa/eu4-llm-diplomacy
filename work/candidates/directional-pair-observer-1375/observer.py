"""Isolated read-only candidate for ten unreviewed ordinary protocol directions.

No process access on import. sample is explicitly PID/creation bound and opens
QUERY_INFORMATION | VM_READ only. compare and describe never open a process.
This candidate is not registered in a host, HTTP service or capability index.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from work import probe_pair_extension_v10_1375 as legacy

base, require = legacy.base, legacy.require
PROFILE = "1375_directional_pair_observation_candidate_1"
CONTRACT_SHA256 = "fb1e47ca36655a1ef371e8ef5e85ae7bd77de0e747c50a19cf06d787de8307a7"
MAX_CONTRACT = 128 * 1024
MAX_DEPENDENCY = 4 * 1024 * 1024
MAX_DEPENDENCIES = 16
MAX_DEPENDENCY_TOTAL = 8 * 1024 * 1024
# Native family + true/false mode are fixed, never supplied separately by a caller.
ACTIONS = {
    "dissolve_alliance": ("allianceaction", False),
    "cancel_military_access": ("milaccess", False),
    "revoke_military_access": ("offermilaccess", False),
    "offer_fleet_basing_rights": ("offer_fleet_access", True),
    "cancel_fleet_basing_rights": ("fleet_access", False),
    "revoke_fleet_basing_rights": ("offer_fleet_access", False),
    "embargo": ("embargoaction", True),
    "revoke_embargo": ("embargoaction", False),
    "give_subsidies": ("warsubsidy", True),
    "cancel_subsidies": ("warsubsidy", False),
}
LIMITATIONS = legacy.LIMITATIONS + [
    "This isolated candidate has synthetic tests only; no new live effect has been reviewed.",
    "Comparison requires the same raw date, but does not verify pause or prove request-ID causality.",
    "Subsidy observations are fixed to outgoing FRA payer, 1000 monthly milli and ten years, including cancellation baseline.",
    "A normal indexed-access object is distinct from conditional movement permission and enforce-peace access.",
    "Full process creation time prevents PID reuse confusion; it does not establish a same-process world epoch.",
]


def bounded(path, maximum):
    with Path(path).open("rb") as stream:
        raw = stream.read(maximum + 1)
    require(len(raw) <= maximum, "Candidate input exceeds bounded read limit")
    return raw


def canonical_typed(value):
    """Compare JSON evidence without Python's bool/int/float equality coercion."""
    def check(item):
        if type(item) is dict:
            require(all(type(key) is str for key in item), "Evidence object keys must be strings")
            for child in item.values():
                check(child)
        elif type(item) is list:
            for child in item:
                check(child)
        else:
            require(type(item) in (str, int, float, bool, type(None)), "Evidence must contain JSON types only")
    check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def verify_contract(root=ROOT):
    path = Path(root)/"work/candidates/directional-pair-observer-1375/evidence-contract.json"
    raw = bounded(path, MAX_CONTRACT)
    require(hashlib.sha256(raw).hexdigest() == CONTRACT_SHA256, "Candidate evidence contract changed")
    contract = base.decode(raw)
    require(contract["profile"] == PROFILE and contract["game_sha256"] == base.LOCAL_SHA256
            and contract["runtime_verified"] is False and contract["production_ready"] is False,
            "Wrong candidate profile/build")
    require(contract["action_bindings"] == {key:{"family":value[0],"value":value[1]} for key,value in ACTIONS.items()},
            "Candidate action scope changed")
    entries = contract["dependencies"]
    require(isinstance(entries, dict) and 0 < len(entries) <= MAX_DEPENDENCIES, "Wrong dependency inventory")
    total = 0
    for name, item in entries.items():
        parts = PurePosixPath(name).parts
        require(isinstance(name, str) and "\\" not in name and ":" not in name
                and parts and not PurePosixPath(name).is_absolute() and all(p not in (".","..") for p in parts),
                "Dependency escapes repository")
        data = bounded(Path(root).joinpath(*parts), MAX_DEPENDENCY)
        total += len(data)
        require(total <= MAX_DEPENDENCY_TOTAL and len(data) == item["size_bytes"]
                and hashlib.sha256(data).hexdigest() == item["sha256"], "Pinned observer dependency changed")
    return contract


def binding(action, target):
    require(action in ACTIONS and target in legacy.TARGETS, "Unsupported protocol action/target")
    family, value = ACTIONS[action]
    roles = {"actor":"FRA", "target":target}
    if family in legacy.ACCESS:
        holder, grantor = (target,"FRA") if family.startswith("offer") else ("FRA",target)
        roles.update(rights_holder=holder, rights_grantor=grantor)
    elif family == "warsubsidy":
        roles.update(payer="FRA", payee=target)
    elif family == "embargoaction":
        roles.update(imposer="FRA", embargoed=target)
    else:
        roles.update(participants=["FRA",target], initiating_country_verified=False)
    return {"protocol_action_id":action, "family":family, "native_value":value,
            "transition":"positive" if value else "cancel", "roles":roles,
            "fixed_parameters":{"monthly_milli":1000,"duration_years":10} if family=="warsubsidy" else {}}


def describe(action=None):
    verify_contract()
    if action is not None and action not in ACTIONS:
        return {"profile":PROFILE,"action":action,"status":"unsupported","production_ready":False,
                "reason":"No reviewed directional layout in this candidate; no fallback or inferred role"}
    names = [action] if action else sorted(ACTIONS)
    return {"profile":PROFILE,"kind":"isolated_read_only_observer_candidate","protocol":"EU4LAB/2",
            "candidate_only":True,"runtime_verified":False,"production_ready":False,
            "contract_sha256":CONTRACT_SHA256,"actions":[binding(name,"POR") for name in names],
            "targets":list(legacy.TARGETS),"same_raw_date_required":True,"paused_verified":False,
            "live_process_inspected":False,"limitations":LIMITATIONS}


def wrap_snapshot(family_snapshot, action, expected_pid, expected_creation):
    base.integer(expected_pid, 1)
    require(isinstance(expected_creation,str) and re.fullmatch(r"[0-9a-f]{16}",expected_creation)
            and int(expected_creation,16)>0, "Creation must be a positive 16-character lowercase FILETIME")
    selected = binding(action,family_snapshot["target"])
    require(family_snapshot["action"] == selected["family"], "Wrong native family for selected protocol action")
    return {"schema_version":1,"kind":"directional_pair_candidate_snapshot","profile":PROFILE,
            "contract_sha256":CONTRACT_SHA256,"read_only":True,"runtime_verified":False,
            "execution_verified":False,"request_causality_verified":False,"paused_verified":False,
            "expected_pid":expected_pid,"expected_creation":expected_creation,"binding":selected,
            "family_snapshot":family_snapshot}


def sample_process(pid, creation, executable, target, action):
    # All file/build/parameter gates precede process opening; no arbitrary RVA input.
    verify_contract()
    selected = binding(action,target)
    base.integer(pid,1)
    require(isinstance(creation,str) and re.fullmatch(r"[0-9a-f]{16}",creation)
            and int(creation,16)>0, "Invalid required process creation time")
    build, signature = base.verified_executable(executable)
    reader = base.ProcessReader(pid,executable,signature)
    try:
        source = base.process_identity(reader,pid)
        require(source["process_creation_filetime"] == int(creation,16)
                and source["process_exit_filetime"] == 0, "PID/creation is not the requested live process")
        started = base.timestamp()
        observation = legacy.capture(reader,reader.base,target,selected["family"])
        finished = base.timestamp()
        require(base.process_identity(reader,pid) == source, "Process identity changed during observation")
        raw = {"schema_version":1,"kind":"pair_extension_snapshot","profile":legacy.PROFILE,
               "static_effect_evidence_sha256":legacy.EVIDENCE_SHA256,
               "static_extension_evidence_sha256":legacy.EXTENSION_SHA256,"read_only":True,
               "capture_started_at":started,"capture_finished_at":finished,"build":build,"source":source,
               "action":selected["family"],"actor":"FRA","target":target,"observation":observation,
               "execution_verified":False,"request_causality_verified":False,
               "read_budget":{"bytes_read":reader.bytes_read,"maximum_total":base.MAX_TOTAL_READ,
                  "maximum_single":base.MAX_READ,"maximum_relation_entries":base.MAX_RELATION_ENTRIES,"passes":2}}
        report=wrap_snapshot(raw,action,pid,creation)
        if observation["status"]=="consistent_bounded_observation":
            validated_report(report)
        return report
    finally:
        reader.close()


def validated_report(report):
    require(type(report["schema_version"]) is int and report["schema_version"]==1
            and report["kind"]=="directional_pair_candidate_snapshot" and report["profile"]==PROFILE
            and report["contract_sha256"]==CONTRACT_SHA256, "Wrong candidate snapshot profile/evidence")
    require(report["read_only"] is True and all(report[k] is False for k in
        ("runtime_verified","execution_verified","request_causality_verified","paused_verified")), "Overstated snapshot claims")
    raw = report["family_snapshot"]
    selected = binding(report["binding"]["protocol_action_id"],raw["target"])
    require(canonical_typed(report["binding"])==canonical_typed(selected)
            and raw["action"]==selected["family"], "Protocol/family/role binding differs")
    base.integer(report["expected_pid"],1)
    creation=report["expected_creation"]
    require(isinstance(creation,str) and re.fullmatch(r"[0-9a-f]{16}",creation) and int(creation,16)>0,
            "Invalid bound creation")
    require(raw["source"]["pid"]==report["expected_pid"]
            and raw["source"]["process_creation_filetime"]==int(creation,16), "Bound process identity differs")
    budget=raw["read_budget"]
    require({k:budget[k] for k in ("maximum_total","maximum_single","maximum_relation_entries","passes")}
            == {"maximum_total":base.MAX_TOTAL_READ,"maximum_single":base.MAX_READ,
                "maximum_relation_entries":base.MAX_RELATION_ENTRIES,"passes":2}
            and all(type(v) is int for v in budget.values()), "Read budget differs from bounded observer")
    base.integer(budget["bytes_read"],1,base.MAX_TOTAL_READ)
    observation=raw["observation"]
    passes=observation["passes"]
    require(type(passes) is list and len(passes)==2, "Two complete passes required")
    require(observation["atomic_snapshot"] is False, "Bounded observation is not atomic")
    # The pinned legacy reader validates only pass zero on imported reports and
    # compares Python objects with ==. Recheck each pass here before delegating
    # metadata/time checks, including when both malformed passes compare equal.
    states=[]
    for sample in passes:
        require(type(sample) is dict, "Missing complete sample")
        state=legacy.inspect_state(sample)
        require(sample["target"]==raw["target"] and sample["action"]==raw["action"]
                and sample["module_base"]==raw["source"]["module_base"], "Report/sample identity differs")
        require(canonical_typed(sample["player"])==canonical_typed(sample["pair"]["FRA"]),
                "Selected player is not fixed FRA")
        states.append(state)
    require(canonical_typed(passes[0])==canonical_typed(passes[1]),
            "Two type-identical complete passes required")
    require(canonical_typed(states[0])==canonical_typed(states[1])
            and canonical_typed(states[0])==canonical_typed(observation["state"]),
            "Stored state differs in value or type from reconstructed raw state")
    sample,state,times=legacy.validated_report(raw)
    return sample,state,times


def compare_reports(before, after):
    result={"schema_version":1,"kind":"directional_pair_candidate_comparison","profile":PROFILE,
            "contract_sha256":CONTRACT_SHA256,"status":"unknown","observed_effect":False,
            "runtime_verified":False,"execution_verified":False,"production_ready":False,
            "request_causality_verified":False,"ai_acceptance_verified":False,"rejection_observed":False,
            "world_epoch_verified":False,"strict_single_player_verified":False,
            "whole_world_unchanged_verified":False,"paused_verified":False,"errors":[],"limitations":LIMITATIONS}
    try:
        prior,old,_=validated_report(before)
        current,new,_=validated_report(after)
        require(before["binding"]==after["binding"], "Selected protocol operation/roles changed")
        require((before["expected_pid"],before["expected_creation"])==(after["expected_pid"],after["expected_creation"]),
                "Bound process changed")
        require(prior["current_raw_date"]==current["current_raw_date"], "Same raw date required; elapsed-time effects remain unknown")
        selected=before["binding"]
        expected=(1000,10) if selected["family"]=="warsubsidy" else None
        if expected:
            state=new if selected["native_value"] else old
            require(state["state"]=="active" and state["nominal_expiry_raw_date"]>prior["current_raw_date"],
                    "Fixed outgoing subsidy must be active and not nominally expired")
        if selected["family"]=="embargoaction":
            require(old["incoming_embargo"]==new["incoming_embargo"], "Opposite embargo state changed too")
        compared=legacy.compare_reports(before["family_snapshot"],after["family_snapshot"],selected["transition"],expected)
        result.update(binding=selected,source=after["family_snapshot"]["source"],raw_field_comparison=compared)
        result["errors"].extend(compared["errors"])
        if compared["observed_effect"]:
            result.update(status="observed_effect",observed_effect=True,transition=compared["transition"])
    except (base.ProbeError,KeyError,TypeError,ValueError) as exc:
        result["errors"].append(str(exc))
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    info=sub.add_parser("describe");info.add_argument("--action")
    sample=sub.add_parser("sample")
    sample.add_argument("--pid",type=int,required=True);sample.add_argument("--creation",required=True)
    sample.add_argument("--exe",type=Path);sample.add_argument("--target",choices=legacy.TARGETS,required=True)
    sample.add_argument("--action",choices=tuple(ACTIONS),required=True);sample.add_argument("--output",type=Path,required=True)
    compare=sub.add_parser("compare")
    compare.add_argument("--before",type=Path,required=True);compare.add_argument("--after",type=Path,required=True)
    compare.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=="describe":
            print(json.dumps(describe(args.action)));return 0
        verify_contract()
        require(args.output.suffix==".json", "Observer output must be a .json evidence file")
        require(not args.output.exists(), "Output already exists; choose a new evidence file")
        if args.command=="sample":
            executable=args.exe or base.game_exe()
            report=sample_process(args.pid,args.creation,executable,args.target,args.action)
            base.write_report(args.output,report,(executable,))
            valid=report["family_snapshot"]["observation"]["status"]=="consistent_bounded_observation"
        else:
            before,bh=base.read_report(args.before);after,ah=base.read_report(args.after)
            report=compare_reports(before,after);report["inputs"]={"before_sha256":bh,"after_sha256":ah}
            base.write_report(args.output,report,(args.before,args.after));valid=report["observed_effect"]
        print(json.dumps({"output":str(args.output),"observed_effect":report.get("observed_effect",False),
                          "status":report.get("status",report.get("family_snapshot",{}).get("observation",{}).get("status")),
                          "execution_verified":False}))
        return 0 if valid else 2
    except (base.ProbeError,base.EvidenceError,OSError,ValueError,RuntimeError,KeyError) as exc:
        print("Directional observer candidate: "+str(exc),file=sys.stderr);return 2


if __name__=="__main__":
    raise SystemExit(main())
