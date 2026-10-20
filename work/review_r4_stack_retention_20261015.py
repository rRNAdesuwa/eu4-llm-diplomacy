"""Bounded five-file review: static R4 contracts are not retained live stack captures."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"work/reports/r4-stack-retention-review"
PATHS=("work/reports/war-peace-api-20261015-r4/war/host-contract.json",
       "work/reports/war-peace-api-20261015-r4/war/manifest.json",
       "work/reports/war-peace-api-20261015-r4/war/findings.json",
       "work/reports/war-peace-api-20261015-r4/war/report.md",
       "work/reports/war-peace-api-20261014-r3/sink/host-source.json")


def pin(path):
    raw=path.read_bytes()
    return dict(path=path.relative_to(ROOT).as_posix(),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check",action="store_true")
    args=ap.parse_args()
    if args.check:
        result=json.loads((OUT/"independent-review.json").read_bytes())
        for row in result["source_pins"]:
            assert pin(ROOT/row["path"])==row
        for row in json.loads((OUT/"manifest.json").read_bytes())["files"]:
            assert pin(ROOT/row["path"])==row
        print(json.dumps(dict(status="passed",target_input_files=5,target_input_bytes=result["scope"]["unique_input_bytes"],
            whole_workspace_absence_claimed=False,new_decode=0,game_process_accessed=False)))
        return
    sizes={name:(ROOT/name).stat().st_size for name in PATHS}
    assert len(sizes)==5<=12 and sum(sizes.values())<100*1024<16*1024*1024
    # All sizes were inspected first; no large file or recursive workspace scan.
    raw={name:(ROOT/name).read_bytes() for name in PATHS}
    pins=[dict(path=name,bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest()) for name,blob in raw.items()]
    host=json.loads(raw[PATHS[0]])
    manifest=json.loads(raw[PATHS[1]])
    findings=json.loads(raw[PATHS[2]])
    report=raw[PATHS[3]].decode("utf-8")
    source=json.loads(raw[PATHS[4]])
    assert hashlib.sha256(raw[PATHS[1]]).hexdigest()=="9bfa2b6e29791fabc2a2892e481d27ce93f485b4e249b290c8d5765cf98c1305"
    named={Path(r["absolute_path"]).relative_to(ROOT).as_posix():r for r in manifest["files"]}
    for row in pins:
        if row["path"]==PATHS[1]:
            continue
        expected=named[row["path"]]
        assert (row["bytes"],row["sha256"])==(expected["bytes"],expected["sha256"])
    assert host["runtime_verified"] is False and host["native_calls"]==0 and host["native_ready"] is False
    assert manifest["runtime_verified"] is False and manifest["process_accessed"] is False
    assert findings["runtime_verified"] is False
    assert source["runtime_verified"] is False and source["process_accessed"] is False and source["native_calls"]==0
    assert host["capture"]["timing"]=="entry10a6ec0 before original prologue"
    assert host["capture"]["stack_entry_offsets"]=={"0x0":"return base+10a6d61","0x40":"outer return base+81582e"}
    assert host["capture"]["existing_frozen_stub_passes_explicit_capture"] is False
    assert "不是运行 trace" in report
    assert all(r["evidence_type"]=="repository_source_inspection_not_runtime_attestation" for r in source["sources"])
    frame=next(r for r in source["sources"] if r["source_file"].endswith("/frame.asm"))
    frame_lines=[r for r in frame["lines"] if "research_frame_tick" in r["text"] or "sub rsp" in r["text"]]
    assert any("call research_frame_tick" in r["text"] for r in frame_lines)
    required=[dict(label="entry Q+0x370",entry_offset="0x370",raw_qword_retained=False),
              dict(label="entry Q+0x3f0",entry_offset="0x3f0",raw_qword_retained=False),
              dict(label="entry Q+0x440",entry_offset="0x440",raw_qword_retained=False),
              dict(label="proposed holder at entry Q+0x4a8",entry_offset="0x4a8",raw_qword_retained=False,
                   qualification="Only the requested static offset; actual holder/frame binding not observed in these files")]
    result=dict(schema="EU4-R4-STACK-RETENTION-BOUNDED-REVIEW/1",
        status="reviewed_R4_contracts_do_not_supply_requested_live_raw_stack_or_probe_reference",findings=[],
        source_pins=pins+[pin(Path(__file__))],scope=dict(target_input_files=5,unique_input_bytes=sum(sizes.values()),
            input_file_limit=12,input_parse_byte_limit=16*1024*1024,all_input_sizes_checked_first=True,
            manifest_entries_metadata_only=len(manifest["files"]),manifest_entire_child_graph_parsed=False,
            unrelated_work_files_scanned=False,workspace_recursive_scan=False,whole_workspace_absence_proven=False),
        observations=[dict(source=PATHS[0],json_pointer="/runtime_verified",value=False),
            dict(source=PATHS[0],json_pointer="/capture/stack_entry_offsets",value=host["capture"]["stack_entry_offsets"],
                 kind="static required offsets, no numeric captured entryRSP or raw stack values"),
            dict(source=PATHS[0],json_pointer="/capture/existing_frozen_stub_passes_explicit_capture",value=False),
            dict(source=PATHS[1],json_pointer="/runtime_verified",value=False),
            dict(source=PATHS[2],json_pointer="/runtime_verified",value=False),
            dict(source=PATHS[3],kind="report explicitly distinguishes instruction-derived site from runtime trace"),
            dict(source=PATHS[4],json_pointer="/runtime_verified",value=False,
                 kind="seven pinned source excerpts, not seven runtime captures")],
        frozen_stub_source_only=dict(source=frame["source_file"],sha256=frame["source_sha256"],retained_lines=frame_lines,
            volatile_register_save_code_is_live_raw_stack_evidence=False,
            source_only_stack_frame_is_numeric_runtime_entry_Q=False,
            actual_stack_window_start_or_length_retained=False),
        coverage=dict(numeric_entry_Q_retained=False,complete_raw_stack_window_retained=False,
            raw_stack_base_length_and_bytes_available=False,required_qwords=required,
            actual_live_probe_receipt_or_reference_in_reviewed_inputs=False,
            exact_current_callback_thread_observed=False,static_new_main_frame_formula_reviewed_here=False),
        correction=dict(task_wording_previously_assumed_old_live_host_origin_probe=True,
            corrected_classification="old native static caller contract/source evidence",
            no_unlisted_historical_capture_is_assumed=True),
        minimum_future_evidence=[
            "A new separately attributable capture at the exact10a6ec0 pre-prologue entry: process/image identity, module base, actual thread ID/depth, RCX/R8 and numeric entryRSP Q in the same invocation.",
            "Retain raw stack bytes with explicit start Q, exact length and hash. If all four requested witnesses are offsets from Q, Q+[0,0x4b0) (1200 bytes) covers every full QWORD through Q+0x4a8, including return witnesses Q+0/+0x40.",
            "If holder+0x4a8 denotes an independently based address rather than Q+0x4a8, retain its numeric address/base and exact8 raw bytes separately; never infer coverage from the proposed formula alone.",
            "Record actual decoded QWORDs at each requested offset and fresh typed object/outer/server relationship used by the separately reviewed static chain; do not substitute historical pointers or this static contract.",
            "This would establish a new invocation/stack witness only. Lifetime exclusion, allocator/exception authority and native readiness still require separate proof."],
        native_ready=False,new_API_effects_verified=0,game_process_accessed=False,native_calls=0,requests_published=0,
        new_capture_performed=False,injection_performed=False,saves_written=0,reloads=0,frozen_sources_modified=False,
        resources=dict(new_decoded_bytes=0,PE_bytes_read=0,large_file_over10MiB_opened=False,shell_sessions_remaining=0))
    OUT.mkdir(parents=True,exist_ok=False)
    with (OUT/"independent-review.json").open("x",encoding="ascii") as f:
        json.dump(result,f,indent=2)
    with (OUT/"report.md").open("x",encoding="utf-8") as f:
        f.write("# Bounded R4 stack-retention review\n\n"
            "The5 explicitly related files total93,391B. Their R4 manifest pins match. They provide a static host contract/source excerpts, with runtime_verified=false; report.md explicitly says the caller-site derivation is not a runtime trace. No numeric captured entryRSP, raw stack start/length/bytes or live probe receipt/reference is supplied by these reviewed files. This is not a whole-workspace historical absence claim.\n\n"
            "Contract Q+0 and Q+0x40 are required return witnesses, not observed values. The frozen stub source's volatile-register saves and callresearch_frame_tick are source code, not retained raw capture. Therefore Q+0x370/+0x3f0/+0x440 and the proposed holder witness+0x4a8 cannot be replayed from this scope. No old observation is backfilled from the new static formula.\n\n"
            "Minimum new evidence: one exact pre-prologue callback invocation with numeric Q, thread/register/process/image identity, and explicit raw stack start/length/hash. If all witnesses are Q-relative, retain Q+[0,0x4b0),1200B, covering the full last QWORD. If holder has another base, capture its exact address/raw8B separately. Decode the witnesses and fresh typed relationships in that same invocation. Such capture still supplies no lifetime lease or native execution authority.\n\n"
            "The task's old-live-probe assumption was corrected to static caller evidence. No expanded work search, PE read/decode, game access, sample, Frida/injection, native call, send, save/reload or frozen edit. native_ready=false.\n")
    seal=dict(schema="EU4-R4-STACK-RETENTION-REVIEW-MANIFEST/1",files=[pin(Path(__file__)),pin(OUT/"independent-review.json"),pin(OUT/"report.md")])
    with (OUT/"manifest.json").open("x",encoding="ascii") as f:
        json.dump(seal,f,indent=2)
    print(json.dumps(dict(review=pin(OUT/"independent-review.json"),markdown=pin(OUT/"report.md"),manifest=pin(OUT/"manifest.json"),
        target_files=5,target_bytes=sum(sizes.values()),new_decode=0,native_ready=False)))


if __name__=="__main__":
    main()
