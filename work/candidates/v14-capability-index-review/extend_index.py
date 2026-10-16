from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from bridge.diplomacy_api import canonical
index_path=ROOT/"bridge/diplomacy_research_evidence.json"
r=json.loads((HERE/"before/bridge/diplomacy_research_evidence.json").read_bytes())
def sha(b):return hashlib.sha256(b).hexdigest()
def doc(path):return json.loads((ROOT/path).read_bytes())
def add(group,path,expected=None):
 p=ROOT/path;raw=p.read_bytes();d={"path":path,"size_bytes":len(raw),"sha256":sha(raw),"read_mode":"whole"}
 assert 0<len(raw)<=8*1024*1024,path
 if expected:
  assert d["sha256"]==expected["sha256"].lower(),path
  if "size_bytes" in expected:assert d["size_bytes"]==expected["size_bytes"],path
  if "bytes" in expected:assert d["size_bytes"]==expected["bytes"],path
 existing=next((key for key,value in r["artifacts"].items() if value==d),None)
 if existing is None:
  existing=f"v14-{group}-{len(r['artifacts']):03d}";r["artifacts"][existing]=d
 if existing not in groups[group]:groups[group].append(existing)
 return existing

groups={"e":[],"p":[]}
def add_review(group,base):
 report=doc(base+"/review.json");add(group,base+"/review.json")
 for name,item in report["source_files"].items():add(group,base+"/"+name,item)
 for item in report.get("validation_history",[]):
  add(group,base+"/"+item["path"],item)
  v=doc(base+"/"+item["path"])
  if "stdout_sha256" in v:add(group,str(Path(base,item["path"]).parent/"output.txt").replace("\\","/"),{"sha256":v["stdout_sha256"]})
 pins=doc(base+"/pins.json")
 for name,item in pins["files"].items():add(group,name,item)

summary_path="work/runtime/native1375-v14/directional-finalized-summary-r3-18356.json"
summary=doc(summary_path);assert sha((ROOT/summary_path).read_bytes())=="19f9203fe5eed194c02d8bead92a7503bf296f7f28db3baa50b2882ddfc7d967"
assert summary["observed_effect_count"]==8 and len(summary["requests"])==43 and len(summary["input_artifacts"])==266
assert summary["save_reload_verified"] is False
add("e",summary_path);add("e","work/runtime/native1375-v14/directional-finalized-case-18356.json")
for item in summary["input_artifacts"].values():add("e",item["path"],item)
add_review("e","work/candidates/v14-directional-experiment-review-r3")
add("e","work/review-results/v14-directional-r3-native-inventory-20261008a/review.json",{"sha256":"9a3c1f5410909499106136789a69ea65406d0838960962b0f71b63ba56bf4133"})
manifest=doc("work/runtime/native1375-v14/build.json");add("e","work/runtime/native1375-v14/build.json")
add("e","work/runtime/native1375-v14/eu4_pair_lab_v14_1375.dll",{"sha256":manifest["dll_sha256"]})
for groupname in ("source_sha256","host_source_sha256","support_source_sha256"):
 for path,h in manifest[groupname].items():add("e",path,{"sha256":h})
for path,h in manifest["fixture_profile"]["source_sha256"].items():add("e","work/candidates/fixture-v14-1375/"+path,{"sha256":h})

persistence_path="work/runtime/native1375-v14/directional-persistence-summary-r2-18356.json"
persistence=doc(persistence_path);assert sha((ROOT/persistence_path).read_bytes())=="efd863a3252812ee6481f98f3bfc695a23128a2f3a07c70c459cc216fc2bf5b4"
assert persistence["selected_observation_count"]==9 and persistence["selected_serialized_and_reload_count"]==7
add("p",persistence_path);add("p","work/runtime/native1375-v14/directional-persistence-case-18356.json")
for item in persistence["input_artifacts"].values():add("p",item["path"],item)
add_review("p","work/candidates/v14-directional-persistence-review-r2")
add("p","work/review-results/v14-directional-persistence-r2-native-inventory-20261008a/review.json")

rows=[]
for effect in summary["effects"]:
 seq=effect["sequence"];request=next(x for x in summary["requests"] if x["sequence"]==seq)
 assert request["outcome"]=="dispatched" and request["action"]==effect["action"]
 rows.append({"experiment_id":f"v14-{effect['action']}-fra-por-stopped-session","action_id":effect["action"],
 "scope":{"version":"v14","protocol":"EU4LAB/2","purpose":"restricted_pair_lab_1375_v14","pid":18356,"process_creation_filetime":summary["creation"],"world_cookie":summary["world_cookie"],"window_thread":summary["window_thread"],"dll_sha256":summary["dll_sha256"],"manifest_sha256":summary["manifest_sha256"],"fixture_profile_sha256":"f3507bb78f665443c5dad20efee0aef2dd86a8b6741130ee03e883b2ecc1a507","actor":"FRA","target":"POR","sequence":seq,"world_generation_verified":False,"test_fixture_active":True},
 "claims":{"native_dispatch_returned":True,"observed_state_change":effect["observed_effect"],"saved_state_verified":False,"reload_verified":False,"request_causality_verified":False,"ai_acceptance_verified":False,"reply_rejection_correlated":False,"reply_acceptance_correlated":False,"native_legality_checked":True},
 "findings":{"status":effect["status"],"binding":effect["binding"],"native_rejection_verified":False,"selected_effect_observed":effect["observed_effect"],"native_consumer_ownership_reported_consumed":True,"inventoried_session_requests":43,"session_stopped":True,"phase_case_counts":summary["phase_case_counts"],"experimental_summary_save_reload_verified":False,"persistence_evidence_scope":"independent_selected_state_review_not_combined_action_causality","root_ui_annotation":next((a["text"] for a in summary["annotations"] if a["sequence"]==seq),None),"root_ui_annotation_is_native_evidence":False},
 "evidence":groups["e"],"limitations":["Historical exact FRA/POR direction only; 43-step stopped-session review does not authorize a live process.","Known native return and consumed ownership are not AI acceptance; absent offered fleet state remains unknown despite a separate UI refusal annotation.","Independent persistence review reports seven serialized-plus-typed states and two typed-only absences; this experiment review itself retains save_reload_verified=false.","No request-ID causality, natural AI acceptance, strict single-player, reliable world epoch or production execution proof."]})
r["observations"].extend(rows)
r["historical_persistence_reviews"]=[{"version":"v14","purpose":"v14_selected_directional_persistence_review","scope":"independent_selected_state_review","source_summary_sha256":sha((ROOT/persistence_path).read_bytes()),"results":persistence["results"],"evidence":groups["p"],"large_save_hashes_recorded":sorted({x["save_sha256"] for x in persistence["results"]}),"large_saves_rehashed_in_discovery":False,"limitations":persistence["limitations"]}]
r["cutoff"].update({"description":"v5/v6/v7/v8/v9/v10/v12 plus reviewed stopped v14 43-step session; v15 acceptance candidate is not runtime evidence","v14_sequence":43,"v14_pid":18356,"v14_effects":8,"v14_unknown_selected_effects":1})
# Keep old observations, preflight and all old artifact descriptors byte-content equivalent.
before=json.loads((HERE/"before/bridge/diplomacy_research_evidence.json").read_bytes())
assert r["observations"][:len(before["observations"])]==before["observations"]
assert r["historical_preflights"]==before["historical_preflights"]
assert all(r["artifacts"][k]==v for k,v in before["artifacts"].items())
pins={"effect":sha(canonical({"observations":rows,"artifacts":{k:r["artifacts"][k] for k in groups["e"]}}).encode()),"persistence":sha(canonical({"record":r["historical_persistence_reviews"][0],"artifacts":{k:r["artifacts"][k] for k in groups["p"]}}).encode())}
raw=(json.dumps(r,ensure_ascii=False,indent=2)+"\n").encode();total=sum(x["size_bytes"] for x in r["artifacts"].values())
assert len(r["artifacts"])<=1024 and total<=32*1024*1024 and len(raw)<=512*1024,(len(r["artifacts"]),total,len(raw))
index_path.write_bytes(raw)
result={"artifacts":len(r["artifacts"]),"total_bytes":total,"index_bytes":len(raw),"effect_references":len(groups["e"]),"persistence_references":len(groups["p"]),"observations":len(r["observations"]),"review_pins":pins,"index_sha256":sha(raw),"large_save_files_read":False}
with (HERE/"index-build-r2.json").open("x",encoding="utf-8") as out:json.dump(result,out,indent=2);out.write("\n")
print(json.dumps(result,indent=2))
