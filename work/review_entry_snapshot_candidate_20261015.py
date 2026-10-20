"""Independent synthetic counterexamples for the exact reviewed R1 source only."""
import argparse
from array import array
import ast
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"work/reports/war-peace-api-20261015-r6-entry-observer-review"
SNAPSHOT=OUT/"reviewed-source"
ORIGINAL=ROOT/"work/reports/war-peace-api-20261015-r6-entry-observer/war/candidate"
EXPECTED={"entry_snapshot.py":"d45e5383c6d6aa3998289c5251a71096f2e43f0b6452a05b9c0906b31354e532",
          "test_entry_snapshot.py":"be506bf02fa9199e437e34738e364b2f9310f23a6e27ed2dac8971b5b7ef2c1c"}


def pin(path):
    raw=path.read_bytes()
    assert len(raw)<128*1024
    return dict(path=path.relative_to(ROOT).as_posix(),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check",action="store_true")
    args=ap.parse_args()
    if args.check:
        result=json.loads((OUT/"independent-r1-source-review.json").read_bytes())
        for row in result["source_pins"]:assert pin(ROOT/row["path"])==row
        for row in json.loads((OUT/"manifest.json").read_bytes())["files"]:assert pin(ROOT/row["path"])==row
        print(json.dumps(dict(status="passed",source_pins=len(result["source_pins"]),issues=2,
            original_25_tests_rerun=False,game_process_accessed=False)))
        return
    sources=[]
    for name,wanted in EXPECTED.items():
        for path in (ORIGINAL/name,SNAPSHOT/name):
            row=pin(path)
            assert row["sha256"]==wanted
            sources.append(row)
    tree=ast.parse((SNAPSHOT/"entry_snapshot.py").read_text())
    imports=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):imports.extend(n.name for n in node.names)
        if isinstance(node,ast.ImportFrom):imports.append(node.module)
    assert set(imports)<={"__future__","dataclasses","enum","struct","typing"}
    assert not any(isinstance(node,ast.Call) and any(part in ast.unparse(node.func).lower()
        for part in ("ctypes","readprocessmemory","writeprocessmemory","frida","inject","installer","createremotethread")) for node in ast.walk(tree))
    sys.path.insert(0,str(SNAPSHOT))
    import entry_snapshot as entry
    from test_entry_snapshot import fixture,observe
    counterexamples=[]
    for name in ("wide_element_memoryview","released_memoryview"):
        c,_=fixture(optional=False)
        class Port:
            def read(self,address,size):
                if name=="wide_element_memoryview":return memoryview(array("Q",[0]*size))
                view=memoryview(b"12345678")
                view.release()
                return view
        try:
            result=observe(c,Port())
            counterexamples.append(dict(case=name,status=result.evaluation.status,reason=result.evaluation.reason))
        except Exception as exc:
            counterexamples.append(dict(case=name,uncaught_exception=True,exception_type=type(exc).__name__,message=str(exc)))
    assert counterexamples[0]["exception_type"]=="error" and counterexamples[1]["exception_type"]=="ValueError"
    c,m=fixture(optional=False)
    valid=observe(c,m)
    assert valid.evaluation.status=="structural_match"
    float_results=[]
    for field in ("outer_vtable","outer_secondary_vtable","game_vtable","current_vtable","current_update"):
        bad=replace(valid.first,**{field:float(getattr(valid.first,field))})
        result=entry.evaluate_pair(c,bad,bad)
        assert result.status=="structural_match"
        assert result.native_entry_authenticated is result.native_ready is result.header_lifetime_lease is result.atomic_snapshot is False
        float_results.append(dict(field=field,value_type="float",status=result.status,all_authorization_flags_false=True))
    pre_read=[]
    for changes in ({"source":entry.Source.EXISTING_BUILD7_TICK,"entry_rsp":None,"game_sha256":""},
                    {"source":entry.Source.AFTER_CALLBACK_RETURN,"entry_rsp":None,"game_sha256":""},
                    {"entry_rsp":entry.MAX_ADDRESS-8},{"image_base":entry.MAX_ADDRESS-0x2000},
                    {"server_r8":True},{"callback_thread":1<<32}):
        c,m=fixture(optional=False)
        result=observe(replace(c,**changes),m)
        assert result.evaluation.status=="unknown" and len(m.reads)==0
        pre_read.append(dict(changes={k:str(v) for k,v in changes.items()},reason=result.evaluation.reason,attempted_port_reads=0))
    sources.append(pin(Path(__file__)))
    result=dict(schema="EU4-ENTRY-SNAPSHOT-R1-INDEPENDENT-SOURCE-REVIEW/1",
        status="two_counterexample_gaps_in_exact_R1_source_require_independent_R2_fix",
        reviewed_R1_source_sha256=EXPECTED["entry_snapshot.py"],reviewed_R1_tests_sha256=EXPECTED["test_entry_snapshot.py"],
        source_pins=sources,reviewed_source_snapshots_exact_bytes_preserved=True,R1_manifest_or_contract_reviewed=False,
        candidate_25_tests=dict(command="python -B -m unittest -v test_entry_snapshot",count=25,passed=True,
            observed_elapsed_seconds=0.008,run_during_initial_review=True,rerun_by_this_artifact_producer=False),
        issues=[dict(priority="P2",file="entry_snapshot.py",line=132,id="memoryview_element_length_is_not_byte_length",
            description="Accepted wide-format memoryview can have len8 but nbytes64. BudgetReader returns64B for8B request then struct.unpack raises uncaught error; released view length raises uncaughtValueError.",
            counterexamples=counterexamples,
            requested_fix="Validate buffer byte length before potentially large copy; safely normalize accepted buffers and verify exact final byte length, closing malformed/released/failed conversions asRefused/unknown.",
            authorization_escalation=False),
          dict(priority="P3",file="entry_snapshot.py",line=247,id="projection_vtable_scalars_lack_exact_int_guard",
            description="Five vtable/update scalar fields are compared only numerically. Exact-valued floats pass tuple equality and structural_match despite not being integer owned QWORD projections.",
            counterexamples=float_results,
            requested_fix="Apply exact-int/QWORD or canonical-address validation appropriate to each field before expected-pointer comparisons; rejectfloat/bool/noninteger values.",
            authorization_escalation=False)],
        passed_independent_pre_read_rejections=pre_read,
        source_boundary_review=dict(imports=sorted(set(imports)),pure_read_port_only=True,
            no_embedded_process_API_hook_installer_or_game_call=True,one_shot_context_port_cleared_after_exit=True,
            selects_six_stack_QWORDs_not_complete_0x4b0_raw_stack_window=True,
            claimed_native_source_is_only_structural_match=True,
            native_entry_authenticated_always_false_in_current_return_paths=True,
            native_ready_always_false=True,header_lease_always_false=True,atomic_snapshot_always_false=True),
        limits=["Only exact initialR1 source/tests and pure synthetic graphs reviewed; R2 is separate future scope.",
            "Known bad source/expired stack/read bounds refuse before port reads. Caller-provided native-entry metadata is never authenticated.",
            "The two issues concern malformed buffers/scalars, not observed game behavior or a native privilege/readiness promotion.",
            "No callback adapter/liveentry/thread/rawstack/lease/allocator/TLS/native execution safety was established."],
        R1_and_candidate_files_modified=False,new_manifest_or_contract_examined=False,
        game_process_accessed=False,native_calls=0,requests_published=0,new_API_effects_verified=0,native_ready=False,
        resources=dict(new_decoded_bytes=0,PE_bytes_read=0,max_counterexample_return_buffer_bytes=64,
            memory_limit_bytes=768*1024*1024,shell_sessions_remaining=0))
    with (OUT/"independent-r1-source-review.json").open("x",encoding="ascii") as f:json.dump(result,f,indent=2)
    with (OUT/"report.md").open("x",encoding="utf-8") as f:
        f.write("# Independent entry-snapshot R1 source review\n\nExactR1 sourceSHA d45e5383c6d6aa3998289c5251a71096f2e43f0b6452a05b9c0906b31354e532 is preserved with its tests. Candidate25tests passed0.008s; no manifest/contract or runtime capture was reviewed. Two independent malformed-input gaps were sent before R2 work.\n\nP2,line132: memoryview len counts elements. array('Q')view with8elements returns64bytes for8Brequest and escapes as struct.error; releasedview escapesValueError. Check byte length before copying and safely normalize/recheck, producing unknown on malformed reads.\n\nP3,line247: any one of five vtable/update fields replaced by numerically equalfloat passes structural_match. Require exactinteger pointer/QWORD scalars before comparison. Authorization flags nevertheless stayfalse; this is no native-readiness escalation.\n\nIndependent build7/expired-source inputs with missingQ/hash still reject before reads; Q/module span, R8bool and oversizedthread also refuse at0reads. Module imports are pure dataclasses/enum/struct/typing; no process API/hook/installer/gamecall. One-shot borrowed-port discipline does not authenticate a native entry, provide a full raw stack window, atomicity or header lease. R1/candidate preserved, no game/native/decode; R2 must be reviewed separately before sealing.\n")
    files=[pin(Path(__file__)),pin(SNAPSHOT/"entry_snapshot.py"),pin(SNAPSHOT/"test_entry_snapshot.py"),pin(OUT/"independent-r1-source-review.json"),pin(OUT/"report.md")]
    seal=dict(schema="EU4-ENTRY-SNAPSHOT-R1-REVIEW-MANIFEST/1",files=files)
    with (OUT/"manifest.json").open("x",encoding="ascii") as f:json.dump(seal,f,indent=2)
    print(json.dumps(dict(review=pin(OUT/"independent-r1-source-review.json"),markdown=pin(OUT/"report.md"),manifest=pin(OUT/"manifest.json"),
        source_pins=len(sources),issues=2,original25tests_rerun=False,native_ready=False)))


if __name__=="__main__":main()
