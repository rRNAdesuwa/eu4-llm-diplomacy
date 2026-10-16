"""File-only fresh current-app binding, common registry and dispatch replay."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"work"))
from discover_diplomacy import check_memory_budget
SOURCE=ROOT/"work/reports/war-peace-api-20261015-r8-stack-scope/war/live-80340-current-app-r3.json"
PRODUCER=ROOT/"work/capture_nocb_current_app_r3_20261015.py"
PRIOR=ROOT/"work/reports/war-peace-api-20261015-r8-stack-scope/war/live-80340-registry-and-dispatch-r2.json"
INITIAL=ROOT/"work/reports/war-peace-api-20261015-r8-stack-scope/war/live-80340-registry-current.json"
OUT=ROOT/"work/reports/war-peace-api-20261015-r8-current-app-r3-review"
SHA="095cb1a85b215e54bfc99a292782dfe21d687abb7bd7c30888d1fbe00f6210a7"
PRIOR_SHA="c9ec7d7d8176d53008f00697d9fd224467fe22e937fce48cb910373df2ad0180"


def pin(path):
    raw=path.read_bytes()
    assert len(raw)<16*1024*1024
    return dict(path=path.relative_to(ROOT).as_posix(),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check",action="store_true")
    args=ap.parse_args()
    if args.check:
        data=json.loads((OUT/"independent-file-audit.json").read_bytes())
        for row in data["source_pins"]:
            assert pin(ROOT/row["path"])==row
        for row in json.loads((OUT/"manifest.json").read_bytes())["files"]:
            assert pin(ROOT/row["path"])==row
        print(json.dumps(dict(status="passed",source_pins=len(data["source_pins"]),new_decoded_bytes=0,game_process_accessed=False)))
        return
    sources={}
    def fixed(path):
        row=pin(path)
        sources[row["path"]]=row
        return row
    assert fixed(SOURCE)["sha256"]==SHA and fixed(PRIOR)["sha256"]==PRIOR_SHA
    data=json.loads(SOURCE.read_bytes())
    prior=json.loads(PRIOR.read_bytes())
    initial=json.loads(INITIAL.read_bytes())
    manifests=set()
    for doc in (data,prior,initial):
        for group in ("source_pins","observer_source_pins"):
            for name,row in doc[group].items():
                path=ROOT/name
                got=fixed(path)
                assert (got["bytes"],got["sha256"])==(row["bytes"],row["sha256"])
                if path.name=="manifest.json" or name=="bridge/diplomacy_observer_manifest_1375.json":
                    manifests.add(path)
    child_count=0
    for path in manifests:
        doc=json.loads(path.read_bytes())
        items=doc.get("files",doc.get("sources",[]))
        if isinstance(items,dict):items=[dict(path=n,**r) for n,r in items.items()]
        for row in items:
            p=Path(row["absolute_path"]) if "absolute_path" in row else ROOT/row["path"]
            if not p.is_file():p=path.parent/row["path"]
            got=fixed(p)
            assert (got["bytes"],got["sha256"])==(row["bytes"],row["sha256"])
            child_count+=1
    tree=ast.parse(PRODUCER.read_text())
    assertions=[n for n in tree.body if isinstance(n,ast.Assert)]
    load=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and ast.unparse(n.func)=="spec.loader.exec_module"]
    assert len(load)==1 and PRIOR_SHA in ast.unparse(assertions[0])
    assert "code" in ast.unparse(assertions[1]) and "expect" in ast.unparse(assertions[1])
    assert assertions[0].lineno<assertions[1].lineno<load[0].lineno
    sample_ast=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="sample")
    assert "prior.sample(reader, base)" in ast.unparse(sample_ast)
    assert not any(isinstance(n,ast.Subscript) and isinstance(n.slice,ast.Constant) and n.slice.value=="samples" for n in ast.walk(tree))
    assert data["identity"]["pid"]==80340 and data["identity"]["creation"]=="01dd5c075fcf8c26"
    assert len({d["identity"]["session"] for d in (data,prior,initial)})==3
    assert data["two_pass_equal"] is True and len(data["samples"])==2 and data["samples"][0]==data["samples"][1]
    base=int(data["base"],16)
    replays=[]
    raw_bytes=0
    for number,sample in enumerate(data["samples"],1):
        roots=sample["roots"]
        assert roots["manual_pause"]==1 and roots["count"]==1380
        assert roots["reset"]==roots["load_source"]==roots["recalculating"]==roots["ironman"]==roots["selector"]==0
        app,reg,sentinel,definition=[sample[k] for k in ("application","registry","sentinel","definition")]
        app_raw,reg_raw,goal_raw,def_raw=[bytes.fromhex(v["raw_hex"]) for v in (app,reg,sentinel,definition)]
        assert list(map(len,(app_raw,reg_raw,goal_raw,def_raw)))==[24,40,24,64]
        assert struct.unpack_from("<Q",app_raw,0)[0]==base+0x1c48bf8 and struct.unpack_from("<Q",app_raw,16)[0]==base+0x1c48c80
        assert int(app["address"],16)!=int(roots["database"],16)
        hash_count,buckets,storage,begin,end,cap=struct.unpack("<IIQQQQ",reg_raw)
        assert (hash_count,buckets,(end-begin)//8,(cap-begin)//8)==(91,511,91,94)
        assert begin<=end<=cap and (end-begin)%8==(cap-begin)%8==0
        vector_raw=bytes.fromhex(reg["vector_raw_hex"])
        assert len(vector_raw)==end-begin==728
        values=[v for v, in struct.iter_unpack("<Q",vector_raw)]
        D=int(definition["address"],16)
        assert values.count(D)==reg["current_definition_occurrences"]==1
        assert struct.unpack_from("<Q",goal_raw,0)[0]==base+0x1d207f8 and struct.unpack_from("<Q",goal_raw,16)[0]==D
        assert struct.unpack_from("<Q",def_raw,0)[0]==base+0x1d20ae0 and struct.unpack_from("<i",def_raw,56)[0]==12
        length,capacity=struct.unpack_from("<QQ",def_raw,40)
        name=def_raw[24:24+length]
        assert (length,capacity,name)==(9,15,b"nowargoal")
        h=0
        for ch in name:h=((h+(ch if ch<128 else ch-256))*61)&0xffffffff
        selected=sample["selected_hash"]
        assert selected["hash_u32"]==h==112898354 and selected["bucket_index"]==h%buckets==58
        assert int(selected["head_address"],16)==storage+58*8
        head=bytes.fromhex(selected["head_raw_hex"])
        assert len(head)==8 and len(selected["nodes"])==1
        node=selected["nodes"][0]
        node_raw=bytes.fromhex(node["raw_hex"])
        assert len(node_raw)==16 and struct.unpack("<Q",head)[0]==int(node["address"],16)
        assert struct.unpack("<QQ",node_raw)==(D,0) and selected["current_definition_occurrences"]==1
        for binding,(name,slot,target) in zip(sample["dispatch_bindings"],(("creator",0x1fb0058,0x1738d30),("wait",0x1fb0db8,0x1739460),("guard_dispatch",0x1b67860,0x1a79a30)),strict=True):
            assert binding["name"]==name and int(binding["slot_rva"],16)==slot
            assert len(bytes.fromhex(binding["raw_hex"]))==8
            assert struct.unpack("<Q",bytes.fromhex(binding["raw_hex"]))[0]==int(binding["address"],16)==base+target
            assert binding["current_expected_binding"] is True
        children=sample["application_children"]
        fields=[]
        for item,(name,offset) in zip(children["fields"],(("current",0x40),("pending",0x70),("previous",0x78)),strict=True):
            raw=bytes.fromhex(item["raw_hex"])
            assert len(raw)==8 and item["name"]==name and int(item["offset"],16)==offset
            value=struct.unpack("<Q",raw)[0]
            assert value==int(item["address"],16)
            fields.append(value)
        current,pending,previous=fields
        assert current==int(roots["server"],16) and pending==previous==0
        assert current!=int(roots["game"],16)+0x1e00
        typed=children["current_typed_header"]
        header=bytes.fromhex(typed["raw_header_hex"])
        slot_raw=bytes.fromhex(typed["update_slot_raw_hex"])
        assert len(header)==16 and len(slot_raw)==8
        assert int(typed["address"],16)==current
        assert struct.unpack_from("<Q",header)[0]==int(typed["vtable"],16)==base+0x1cb8460
        assert struct.unpack("<Q",slot_raw)[0]==int(typed["update_target"],16)==base+0x8137c0
        assert typed["expected_server_type"] is True and typed["expected_update_target"] is True
        assert children["current_equals_game_server_pointer_value"] is True and children["current_server_update_binding_matches_static_chain"] is True
        assert children["fields_are_current_reads_not_native_stack_witness"] is True
        # R2 selected raw payload928B, plus fields24/header16/vtslot8=976B.
        raw_bytes+=sum(map(len,(app_raw,reg_raw,goal_raw,def_raw,vector_raw,head,node_raw)))+24+24+16+8
        replays.append(dict(pass_number=number,outer_address=app["address"],current=hex(current),pending=hex(pending),previous=hex(previous),
            current_equals_reported_server_pointee=True,current_differs_from_game_plus_1e00_field_address=True,
            current_vtable_rva=hex(struct.unpack_from("<Q",header)[0]-base),update_target_rva=hex(struct.unpack("<Q",slot_raw)[0]-base),
            vector_count=91,vector_capacity=94,definition_vector_indices=[i for i,v in enumerate(values) if v==D],hash_bucket=58,exact_definition_hash_occurrences=1,
            SDL_and_CFG_current_builtin_addresses_match=True,common_R2_raw_projection_equal_to_prior_report={k:v for k,v in sample.items() if k!="application_children"}==prior["samples"][0]))
    assert raw_bytes==1952
    # Per pass R2=77/1403; additional3fields+header+slot+3rechecks+appslot+roots=27/185.
    assert data["rpm_budget"]==dict(calls=2*(77+3+1+1+3+1+18),bytes=2*(1403+24+16+8+24+8+105),largest_read=728)
    assert data["rpm_budget"]==dict(calls=208,bytes=3176,largest_read=728)
    for key in ("native_callback_observed","native_stack_sampled","callback_thread_identity_proved","native_lifetime_authority","native_ready","memory_written","injection_performed","new_API_effect_tested"):
        assert data[key] is False
    for key in ("native_calls","requests_published","hooks_installed","saves_written","reloads"):assert data[key]==0
    assert data["current_application_binding_only"] is True
    fixed(Path(__file__))
    result=dict(schema="EU4-CURRENT-APP-R3-INDEPENDENT-FILE-AUDIT/1",status="fresh_current_app_and_selected_common_raw_bindings_consistent",findings=[],
        report_sha256=SHA,source_pins=list(sources.values()),original_source_pin_count=5,observer_source_pin_count=len(data["observer_source_pins"]),
        direct_manifest_child_rows_checked=child_count,identity=data["identity"],three_distinct_report_nonces=True,
        source_gate=dict(prior_receipt_assert_line=assertions[0].lineno,prior_producer_pin_assert_line=assertions[1].lineno,load_line=load[0].lineno,
            gate_before_load=True,historical_samples_not_consumed_by_producer=True,sample_calls_fresh_prior_reader=True,producer_imported_or_executed_by_auditor=False),
        samples_equal=True,raw_replays=replays,total_selected_retained_raw_bytes=raw_bytes,
        shared_RPM_budget_consistent=data["rpm_budget"],duration_ms_reported=data["duration_ms_including_host_and_source_checks"],
        boundaries=["Replay is file-only; fresh reads/nonce are source-consistent receipt claims, not a new sample by this auditor.",
            "Current/pending/previous and current header/vtable slot raw bytes are retained; game root/PE/modules/process identity and final reread complete raw bytes are not, so those guard claims remain pinned-reader assertions.",
            "Raw slot20 points at base+8137c0, but target function body runtime bytes and actual execution are not supplied.",
            "Historical raw projection equality is an extra consistency fact; producer never uses historical samples/pointers as capture inputs.",
            "The current outer+40 binding equals reported server pointee and typed server with pending/previousNULL; this does not observe a native callback, thread ID, numeric entryQ or any stack witness.",
            "No atomicity/full-interval dispatch/lifetime lease, owner exclusion, OS join or native readiness follows from these two external RPM samples.",
            "No new API effects, injection/hook/native calls, save/reload or frozen changes were verified/performed in this audit."],
        current_binding_only=True,native_callback_observed=False,native_stack_sampled=False,callback_thread_identity_proved=False,
        native_lifetime_authority=False,native_ready=False,new_API_effects_verified=0,game_process_accessed=False,native_calls=0,requests_published=0,
        saves_written=0,reloads=0,frozen_sources_modified=False,
        resources=dict(new_decoded_bytes=0,peak_committed_bytes=check_memory_budget(),memory_limit_bytes=768*1024*1024,shell_sessions_remaining=0))
    OUT.mkdir(parents=True,exist_ok=False)
    with (OUT/"independent-file-audit.json").open("x",encoding="ascii") as f:json.dump(result,f,indent=2)
    with (OUT/"report.md").open("x",encoding="utf-8") as f:
        f.write("# Independent current-app R3 file audit\n\nThe fixed receipt and named source/observer pins match. Source assertions gate the R2 receipt/producer before loading; the fresh prior reader resolves roots again and historical samples are not capture inputs. No producer was imported/executed by this auditor. Two complete supplied samples are equal.\n\nReplayed1952B selected raw bytes: outer current+0x40 equals reported server pointee, not game+0x1e00 field address; pending+0x70/previous+0x78 areNULL. Current header vt is base+1CB8460 and its live slot+0x20 raw pointer is base+8137C0. Common current registry91/cap94, exact definition in vector/hash bucket58 once, and three builtin SDL/CFG addresses are consistent.\n\nAccounting is104reads/1588B per pass, hence208/3176B/728Bmax, with reported1006.337ms host/source duration. Missing complete root/identity/PE/module/final reread bytes remain pinned-reader assertions. Target function runtime body bytes/execution are not retained. This is externalRPM current binding only: no callback/thread/entryQ/raw stack, lease, new API effect or native safety proof. No game access, new decode, capture, call, injection, save/reload or frozen edit. native_ready=false.\n")
    seal=dict(schema="EU4-CURRENT-APP-R3-REVIEW-MANIFEST/1",files=[pin(Path(__file__)),pin(OUT/"independent-file-audit.json"),pin(OUT/"report.md")])
    with (OUT/"manifest.json").open("x",encoding="ascii") as f:json.dump(seal,f,indent=2)
    print(json.dumps(dict(review=pin(OUT/"independent-file-audit.json"),markdown=pin(OUT/"report.md"),manifest=pin(OUT/"manifest.json"),source_pins=len(sources),raw_bytes=raw_bytes,new_decode=0,native_ready=False)))


if __name__=="__main__":main()
