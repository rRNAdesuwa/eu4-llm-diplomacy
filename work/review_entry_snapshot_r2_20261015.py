"""Independent R2 source-only acceptance; no runtime or manifest authentication."""
import argparse
from array import array
import ast
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"work/reports/war-peace-api-20261015-r6-entry-observer-r2/war/candidate"
R1=ROOT/"work/reports/war-peace-api-20261015-r6-entry-observer/war/candidate"
OUT=ROOT/"work/reports/war-peace-api-20261015-r6-entry-observer-r2-review"
EXPECTED={"entry_snapshot.py":"8a4e563d7e66a5a9c5359e0e47d662175516fd4939bae0f3b63a15e177cd6bf9",
          "test_entry_snapshot.py":"557fe4e9e623a1f8e461652cd6b9d7143c4a2032501b44c12888a0e225beb851"}
R1_HASHES={"entry_snapshot.py":"d45e5383c6d6aa3998289c5251a71096f2e43f0b6452a05b9c0906b31354e532",
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
        result=json.loads((OUT/"independent-source-ready.json").read_bytes())
        for row in result["source_pins"]:assert pin(ROOT/row["path"])==row
        for row in json.loads((OUT/"manifest.json").read_bytes())["files"]:assert pin(ROOT/row["path"])==row
        print(json.dumps(dict(status="passed",source_pins=len(result["source_pins"]),findings=0,
            original32tests_rerun=False,native_ready=False,game_process_accessed=False)))
        return
    sources=[]
    for name,sha in EXPECTED.items():
        row=pin(SOURCE/name);assert row["sha256"]==sha;sources.append(row)
    for name,sha in R1_HASHES.items():
        row=pin(R1/name);assert row["sha256"]==sha;sources.append(row)
    tree=ast.parse((SOURCE/"entry_snapshot.py").read_text())
    r1=ast.parse((R1/"entry_snapshot.py").read_text())
    byname=lambda t:{n.name:n for n in t.body if isinstance(n,(ast.ClassDef,ast.FunctionDef))}
    now,old=byname(tree),byname(r1)
    unchanged=("ReadPort","Source","CaptureInput","Limits","Refused","_integer","_span","_pointer","_input",
               "Projection","_projection","Evaluation","Observation","ObservationScope")
    assert all(ast.dump(now[n])==ast.dump(old[n]) for n in unchanged)
    imports=[]
    for n in ast.walk(tree):
        if isinstance(n,ast.Import):imports.extend(a.name for a in n.names)
        if isinstance(n,ast.ImportFrom):imports.append(n.module)
    assert set(imports)<={"__future__","dataclasses","enum","struct","typing"}
    read=next(n for n in now["BudgetReader"].body if isinstance(n,ast.FunctionDef) and n.name=="read")
    assert "view.nbytes != size" in ast.unparse(read) and "result = view.tobytes()" in ast.unparse(read)
    OUT.mkdir(parents=True,exist_ok=False)
    snapshot=OUT/"reviewed-source";snapshot.mkdir()
    for name in EXPECTED:
        raw=(SOURCE/name).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==EXPECTED[name]
        with (snapshot/name).open("xb") as f:f.write(raw)
        sources.append(pin(snapshot/name))
    sys.path.insert(0,str(snapshot))
    import entry_snapshot as entry
    from test_entry_snapshot import fixture,observe
    cases=[]
    for kind in ("wide","released","multidimensional","liar_bytearray","negative_stride"):
        c,m=fixture(optional=False)
        class Liar(bytearray):
            def __len__(self):return 8
        class Port:
            def read(self,address,size):
                if kind=="wide":return memoryview(array("Q",[0]*size))
                if kind=="released":
                    view=memoryview(bytes(size));view.release();return view
                if kind=="liar_bytearray":return Liar(64)
                b=m.read(address,size)
                if kind=="multidimensional" and size==8:return memoryview(b).cast("B",shape=[2,4])
                if kind=="negative_stride":return memoryview(b[::-1])[::-1]
                return memoryview(b)
        result=observe(c,Port())
        expected="structural_match" if kind in ("multidimensional","negative_stride") else "unknown"
        assert result.evaluation.status==expected
        assert result.evaluation.native_entry_authenticated is result.evaluation.native_ready is result.evaluation.header_lifetime_lease is result.evaluation.atomic_snapshot is False
        counters=(result.attempted_reads,result.requested_bytes,result.exact_bytes)
        assert counters==((42,308,308) if expected=="structural_match" else (1,8,0))
        cases.append(dict(case=kind,status=expected,reason=result.evaluation.reason,counters=counters,uncaught_exception=False,
            native_entry_authenticated=False,native_ready=False,header_lease=False,atomic=False))
    c,m=fixture(optional=False);valid=observe(c,m).first
    for field in ("outer_vtable","outer_secondary_vtable","game_vtable","current_vtable","current_update"):
        bad=replace(valid,**{field:float(getattr(valid,field))})
        result=entry.evaluate_pair(c,bad,bad)
        assert (result.status,result.reason)==("unknown","invalid_address_or_size")
        cases.append(dict(case="float_"+field,status=result.status,reason=result.reason))
    for source in (entry.Source.EXISTING_BUILD7_TICK,entry.Source.AFTER_CALLBACK_RETURN):
        c,m=fixture(optional=False)
        result=observe(replace(c,source=source,entry_rsp=None,game_sha256=""),m)
        assert result.evaluation.status=="unknown" and m.reads==[]
        cases.append(dict(case="priority_"+source.value,status="unknown",reason=result.evaluation.reason,port_reads=0))
    sources.append(pin(Path(__file__)))
    result=dict(schema="EU4-ENTRY-SNAPSHOT-R2-INDEPENDENT-SOURCE-READY/1",status="source_review_ready_for_exact_two_file_pins",findings=[],
        source_pins=sources,accepted_candidate_source_sha256=EXPECTED["entry_snapshot.py"],accepted_candidate_tests_sha256=EXPECTED["test_entry_snapshot.py"],
        source_bytes=13566,test_bytes=17323,R1_source_and_tests_unchanged=True,
        fixed_R1_findings=[dict(id="memoryview_element_length_is_not_byte_length",status="closed",
            evidence="Zero-copy memoryview acquisition checks nbytes before bounded tobytes; conversion/released-view errors becomeRefused; final length/counters use actualbytes"),
          dict(id="projection_vtable_scalars_lack_exact_int_guard",status="closed",
            evidence="Four vtables use exact-int canonical/aligned_pointer; codecurrent_update uses exact-int canonical_span1, avoiding unjustified code alignment")],
        unchanged_AST_nodes=list(unchanged),pure_module_imports=sorted(set(imports)),independent_counterexamples=cases,
        candidate_test_run=dict(count=32,passed=True,observed_elapsed_seconds=0.010,
            command="python -B -m unittest -v test_entry_snapshot",ran_during_initial_R2_review=True,
            rerun_by_receipt_producer=False),
        review_scope=dict(source_and_offline_bytes_only=True,future_manifest_reviewed=False,contract_reviewed=False,
            runtime_adapter_or_native_capture_reviewed=False,readiness_to_seal_applies_only_to_exact_reviewed_source_pins=True),
        limitations=["Caller-supplied source/thread/Q/register metadata produces structural_match only; native entry is not authenticated.",
            "Selected stackQWORDs are copied owned scalars, not a complete live raw stack window or callback timing proof.",
            "Optional pending/previous vtableQWORDs remain raw diagnostic values; no type/lifetime/transition authorization added.",
            "A future R2 seal/manifest/contract may bind these exact bytes but does not inherit a runtime/lifetime/native-ready conclusion from this source review."],
        native_entry_authenticated=False,native_ready=False,header_lifetime_lease=False,atomic_snapshot=False,
        game_process_accessed=False,native_calls=0,requests_published=0,new_API_effects_verified=0,candidate_files_modified=False,
        resources=dict(new_decoded_bytes=0,PE_bytes_read=0,max_synthetic_return_bytes=64,memory_limit_bytes=768*1024*1024,shell_sessions_remaining=0))
    with (OUT/"independent-source-ready.json").open("x",encoding="ascii") as f:json.dump(result,f,indent=2)
    with (OUT/"report.md").open("x",encoding="utf-8") as f:
        f.write("# Independent entry-snapshot R2 source acceptance\n\nExact source8a4e563d7e66a5a9c5359e0e47d662175516fd4939bae0f3b63a15e177cd6bf9 and tests557fe4e9e623a1f8e461652cd6b9d7143c4a2032501b44c12888a0e225beb851 are ready for independentR2 sealing.32 candidate tests passed0.010s; R1 remains unchanged. No new source finding.\n\nBuffer fix checks zero-copy view.nbytes before bounded copying, catches invalid/released conversions and verifies exact finalbytes. Independent wide/released/lying-bytearray cases now returnunknown1read/8requested/0exact. Multidimensional/negative-stride equivalent byte representations remain structural_match42reads/308exactbytes. Four vtables and code update use appropriate exactinteger address guards; all five float regressions reject. Knownbuild7/returned-stack sources with missingQ/hash still refuse before anyread.\n\nInput/source/scope/authorization AST is unchanged. Only pure byte-reader/synthetic behavior was reviewed, not a future manifest/contract/runtime adapter. Source sealing is not native capture authentication, fullstack/atomic snapshot, header lease, native-ready or API effect approval. No game access, native/injection/send, PE read/decode or candidate edit.\n")
    seal=dict(schema="EU4-ENTRY-SNAPSHOT-R2-SOURCE-REVIEW-MANIFEST/1",files=[pin(Path(__file__)),pin(snapshot/"entry_snapshot.py"),pin(snapshot/"test_entry_snapshot.py"),pin(OUT/"independent-source-ready.json"),pin(OUT/"report.md")])
    with (OUT/"manifest.json").open("x",encoding="ascii") as f:json.dump(seal,f,indent=2)
    print(json.dumps(dict(review=pin(OUT/"independent-source-ready.json"),markdown=pin(OUT/"report.md"),manifest=pin(OUT/"manifest.json"),
        source_pins=len(sources),findings=0,original32tests_rerun=False,native_ready=False)))


if __name__=="__main__":main()
