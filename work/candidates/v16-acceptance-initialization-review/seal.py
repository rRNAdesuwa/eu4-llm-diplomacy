"""CreateNew final candidate inventory after completed offline validation."""
import json
import re
import prepare

HERE,ROOT=prepare.HERE,prepare.ROOT


def descriptor(path):
    raw=prepare.bounded(path)
    return {"bytes":len(raw),"sha256":prepare.digest(raw)}


def main():
    frozen,lineage=prepare.frozen_inputs()
    outputs,artifacts=prepare.generate()
    for name,raw in {**{"files/"+name:raw for name,raw in outputs.items()},**artifacts}.items():
        assert prepare.bounded(HERE/name)==raw,name
    validation=json.loads(prepare.bounded(HERE/"validation-results/validation.json"))
    assert [r["exit_code"] for r in validation["runs"]]==[0,0]
    previous=json.loads(prepare.bounded(ROOT/prepare.PREDECESSOR/"candidate-index.json"))
    comparisons={}
    semantic=[]
    for source,row in previous["files"].items():
        target=source.replace("v15","v16")
        old=prepare.bounded(ROOT/source)
        new=outputs[target]
        support=source in lineage["support_sources"]
        fixture=source.startswith("work/candidates/fixture-v15-")
        normalized=old if support or fixture else prepare.renamed(old).encode()
        if normalized!=new:semantic.append(target)
        if support or fixture:assert old==new
        comparisons[target]={"source":source,"source_sha256":prepare.digest(old),"target_sha256":prepare.digest(new),
            "version_only_or_exact":normalized==new,"support_or_fixture_unchanged":old==new if support or fixture else None}
    assert set(semantic)=={"work/native/v16/lab-request-1375.h","work/native/v16/research-lab-bootstrap-1375.inc","work/native/lab_protocol_v16_1375.py"}
    protocol="work/native/lab_protocol_v16_1375.py"
    normalized=prepare.renamed(prepare.bounded(ROOT/"work/native/lab_protocol_v15_1375.py"))
    actual=outputs[protocol].decode()
    for name in ("EXPECTED_NATIVE_SOURCES","NATIVE_REVIEW_PATH","NATIVE_REVIEW_SHA256"):
        normalized=re.sub(r"^"+name+r" = .*$",name+" = <PIN>",normalized,flags=re.M)
        actual=re.sub(r"^"+name+r" = .*$",name+" = <PIN>",actual,flags=re.M)
    assert normalized==actual
    sources={}
    for path in sorted(HERE.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.name!="review.json":
            sources[path.relative_to(HERE).as_posix()]=descriptor(path)
    report={"schema_version":1,"purpose":"v16_pristine_window_candidate_review","status":"ready_for_independent_source_review",
        "source_files":sources,"candidate_index":descriptor(HERE/"candidate-index.json"),
        "startup_only_diff":descriptor(HERE/"startup-only.diff"),"validation":descriptor(HERE/"validation-results/validation.json"),
        "output_comparison":comparisons,"semantic_native_deltas":["startup-window helper","one-shot BridgeStart call before hook/log"],
        "python_semantic_changes":[],"python_pin_changes":["EXPECTED_NATIVE_SOURCES","NATIVE_REVIEW_PATH","NATIVE_REVIEW_SHA256"],
        "counts":{"native":22,"host":12,"support":8,"fixture":5,"total":47},"lineage_files_unchanged":len(lineage["files"]),
        "old_frozen_inputs_unchanged":len(frozen),"offline_tests_passed":56,"check_exit_code":0,
        "cpp_mock_tests_compiled":False,"actual_frozen_v15_blank_frame_still_rejected":True,
        "initialized_first_frame_is_synthetic":True,"closed_historical_binding_preserved":True,
        "strict_single_player_verified":False,"world_generation_verified":False,"production_ready":False,
        "materialized":False,"native_built":False,"runtime_verified":False,"game_accessed":False,
        "server_started":False,"requests_published":False,"all_shell_sessions_collected":True}
    with (HERE/"review.json").open("x",encoding="utf-8") as stream:json.dump(report,stream,indent=2);stream.write("\n")
    print(json.dumps({"review":descriptor(HERE/"review.json"),"index":report["candidate_index"],
        "delta":report["startup_only_diff"],"validation":report["validation"]}))


if __name__=="__main__":main()
