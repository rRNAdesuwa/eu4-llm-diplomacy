"""Pure file replay of fresh selected registry hash chain and dispatch cells."""
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
REPORT=ROOT/"work/reports/war-peace-api-20261015-r8-stack-scope/war/live-80340-registry-and-dispatch-r2.json"
PRODUCER=ROOT/"work/capture_nocb_registry_dispatch_r2_20261015.py"
OLD_REPORT=ROOT/"work/reports/war-peace-api-20261015-r8-stack-scope/war/live-80340-registry-current.json"
OLD_PRODUCER=ROOT/"work/capture_nocb_registry_live_20261015.py"
OUT=ROOT/"work/reports/war-peace-api-20261015-r8-registry-dispatch-r2-review"
EXPECTED="c9ec7d7d8176d53008f00697d9fd224467fe22e937fce48cb910373df2ad0180"
OLD_EXPECTED="b9608f0c6343834e6ffa3fec8a7a355f51a91b45080e8d8e04add31c0490e9a5"
CELLS=(("creator",0x1fb0058,0x1738d30),("wait",0x1fb0db8,0x1739460),("guard_dispatch",0x1b67860,0x1a79a30))


def pin(path):
    raw=path.read_bytes()
    assert len(raw)<16*1024*1024
    return dict(path=path.relative_to(ROOT).as_posix(),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def pointer(v):
    assert type(v) is int and 0x10000<=v<2**47
    return v


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check",action="store_true")
    args=ap.parse_args()
    if args.check:
        result=json.loads((OUT/"independent-file-audit.json").read_bytes())
        for row in result["source_pins"]:
            assert pin(ROOT/row["path"])==row
        for row in json.loads((OUT/"manifest.json").read_bytes())["files"]:
            assert pin(ROOT/row["path"])==row
        print(json.dumps(dict(status="passed",source_pins=len(result["source_pins"]),new_decoded_bytes=0,game_process_accessed=False)))
        return
    sources={}
    def fixed(path):
        row=pin(path)
        sources[row["path"]]=row
        return row
    assert fixed(REPORT)["sha256"]==EXPECTED and fixed(OLD_REPORT)["sha256"]==OLD_EXPECTED
    data=json.loads(REPORT.read_bytes())
    old=json.loads(OLD_REPORT.read_bytes())
    assert data["schema"]=="EU4-NOCB-REGISTRY-AND-DISPATCH-READONLY/2"
    manifest_paths=set()
    for doc in (data,old):
        for group in ("source_pins","observer_source_pins"):
            for name,row in doc[group].items():
                path=ROOT/name
                got=fixed(path)
                assert (got["bytes"],got["sha256"])==(row["bytes"],row["sha256"])
                if path.name=="manifest.json" or name=="bridge/diplomacy_observer_manifest_1375.json":
                    manifest_paths.add(path)
    child_rows=0
    for path in manifest_paths:
        manifest=json.loads(path.read_bytes())
        items=manifest.get("files",manifest.get("sources",[]))
        if isinstance(items,dict):
            items=[dict(path=name,**row) for name,row in items.items()]
        for row in items:
            target=Path(row["absolute_path"]) if "absolute_path" in row else ROOT/row["path"]
            if not target.is_file():
                target=path.parent/row["path"]
            got=fixed(target)
            assert (got["bytes"],got["sha256"])==(row["bytes"],row["sha256"])
            child_rows+=1
    expected_old_pin=old["source_pins"][OLD_PRODUCER.relative_to(ROOT).as_posix()]
    got=fixed(OLD_PRODUCER)
    assert (got["bytes"],got["sha256"])==(expected_old_pin["bytes"],expected_old_pin["sha256"])
    # Parse source order as data. Importing either live producer is prohibited.
    tree=ast.parse(PRODUCER.read_text())
    assertions=[n for n in tree.body if isinstance(n,ast.Assert)]
    assert len(assertions)>=2
    assert OLD_EXPECTED in ast.unparse(assertions[0])
    assert "producer_raw" in ast.unparse(assertions[1]) and "expected" in ast.unparse(assertions[1])
    exec_calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and ast.unparse(n.func)=="spec.loader.exec_module"]
    assert len(exec_calls)==1 and assertions[0].lineno<assertions[1].lineno<exec_calls[0].lineno
    source_sample=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="sample")
    assert "old.sample(reader, base)" in ast.unparse(source_sample)
    assert 'json.loads(old_raw)[\'source_pins\']' in ast.unparse(tree)
    assert not any(isinstance(n,ast.Subscript) and isinstance(n.slice,ast.Constant) and n.slice.value=="samples"
        for n in ast.walk(tree))
    assert data["identity"]["pid"]==80340 and data["identity"]["creation"]=="01dd5c075fcf8c26"
    assert data["identity"]["session"]!=old["identity"]["session"] and len(data["identity"]["session"])==32
    assert data["two_pass_equal"] is True and len(data["samples"])==2 and data["samples"][0]==data["samples"][1]
    base=pointer(int(data["base"],16))
    replays=[]
    raw_bytes=0
    for number,sample in enumerate(data["samples"],1):
        root=sample["roots"]
        assert root["count"]==1380 and root["count"]<=root["capacity"]<=4096
        assert root["manual_pause"]==1 and root["date"]>0
        assert root["reset"]==root["load_source"]==root["recalculating"]==root["ironman"]==root["selector"]==0
        app,reg,goal,definition=[sample[n] for n in ("application","registry","sentinel","definition")]
        app_raw,reg_raw,goal_raw,def_raw=[bytes.fromhex(v["raw_hex"]) for v in (app,reg,goal,definition)]
        assert list(map(len,(app_raw,reg_raw,goal_raw,def_raw)))==[24,40,24,64]
        assert int(app["address"],16)!=int(root["database"],16)
        assert struct.unpack_from("<Q",app_raw,0)[0]==base+0x1c48bf8 and struct.unpack_from("<Q",app_raw,16)[0]==base+0x1c48c80
        assert struct.unpack_from("<Q",goal_raw,0)[0]==base+0x1d207f8
        def_address=pointer(int(definition["address"],16))
        assert struct.unpack_from("<Q",goal_raw,16)[0]==int(goal["definition"],16)==def_address
        assert struct.unpack_from("<Q",def_raw,0)[0]==base+0x1d20ae0 and struct.unpack_from("<i",def_raw,56)[0]==definition["enum"]==12
        count,buckets,storage,begin,end,cap=struct.unpack("<IIQQQQ",reg_raw)
        assert 1<=buckets<=4096 and count==reg["hash_count"]==91
        assert buckets==reg["bucket_count"]==511
        assert begin<=end<=cap and (end-begin)%8==(cap-begin)%8==0
        assert (end-begin)//8==reg["vector_count"]==91 and (cap-begin)//8==94
        for name,value in (("bucket_storage",storage),("vector_begin",begin),("vector_end",end),("vector_capacity",cap)):
            assert int(reg[name],16)==pointer(value)
        vector_raw=bytes.fromhex(reg["vector_raw_hex"])
        assert len(vector_raw)==end-begin==728
        vector=[v for v, in struct.iter_unpack("<Q",vector_raw)]
        assert vector.count(def_address)==reg["current_definition_occurrences"]==1
        assert sample["current_definition_in_registry_vector"] is True and sample["current_slot_and_sentinel_definition_match"] is True
        length,capacity=struct.unpack_from("<QQ",def_raw,40)
        name_raw=def_raw[24:24+length]
        assert (length,capacity,name_raw)==(9,15,b"nowargoal")
        h=0
        for byte in name_raw:
            h=((h+(byte if byte<128 else byte-256))*61)&0xffffffff
        selected=sample["selected_hash"]
        assert selected["name"]=="nowargoal" and selected["hash_u32"]==h==112898354
        bucket=h%buckets
        assert bucket==selected["bucket_index"]==58
        assert int(selected["head_address"],16)==storage+8*bucket
        head_raw=bytes.fromhex(selected["head_raw_hex"])
        assert len(head_raw)==8
        node=struct.unpack("<Q",head_raw)[0]
        seen=set()
        occurrences=0
        for item in selected["nodes"]:
            assert node==int(item["address"],16) and pointer(node)%8==0 and node not in seen
            assert len(seen)<min(256,count+1)
            seen.add(node)
            node_raw=bytes.fromhex(item["raw_hex"])
            assert len(node_raw)==16
            obj,next_node=struct.unpack("<QQ",node_raw)
            assert pointer(obj)==int(item["definition"],16) and next_node==int(item["next"],16)
            occurrences+=obj==def_address
            node=next_node
        assert node==0 and len(seen)==1 and occurrences==selected["current_definition_occurrences"]==1
        dispatch=[]
        for item,(name,slot,target) in zip(sample["dispatch_bindings"],CELLS,strict=True):
            cell_raw=bytes.fromhex(item["raw_hex"])
            assert len(cell_raw)==8
            address=struct.unpack("<Q",cell_raw)[0]
            assert item["name"]==name and int(item["slot_rva"],16)==slot
            assert address==int(item["address"],16)==base+target
            assert int(item["expected_target_rva"],16)==target and item["current_expected_binding"] is True
            dispatch.append(dict(name=name,slot_rva=hex(slot),target_rva=hex(address-base),current_builtin_binding=True))
        raw_bytes+=len(app_raw)+len(reg_raw)+len(goal_raw)+len(def_raw)+len(vector_raw)+len(head_raw)+16*len(seen)+24
        # Source-derived shared budget: old sample49/1154 +head/node/cells/recheck/finalroots.
        calls=49+1+len(seen)+3+1+4+18
        total_bytes=1154+8+16*len(seen)+24+64+32+105
        replays.append(dict(pass_number=number,vector_count=91,vector_capacity=94,exact_definition_vector_indices=[i for i,v in enumerate(vector) if v==def_address],
            definition=hex(def_address),sentinel_definition_matches=True,definition_enum=12,
            name=name_raw.decode(),hash_u32=h,bucket=bucket,node_count=len(seen),exact_definition_hash_occurrences=occurrences,
            raw_hash_chain_terminated=True,dispatch_bindings=dispatch,expected_calls=calls,expected_bytes=total_bytes))
    assert data["rpm_budget"]==dict(calls=sum(r["expected_calls"] for r in replays),bytes=sum(r["expected_bytes"] for r in replays),largest_read=728)
    assert data["rpm_budget"]==dict(calls=154,bytes=2806,largest_read=728) and raw_bytes==1856
    for key in ("atomic_world_snapshot","native_lifetime_authority","native_ready","memory_written","injection_performed","new_API_effect_tested"):
        assert data[key] is False
    for key in ("native_calls","requests_published","hooks_installed","saves_written","reloads"):
        assert data[key]==0
    assert data["current_hash_membership_only"] is True and data["current_dispatch_binding_only"] is True
    fixed(Path(__file__))
    result=dict(schema="EU4-REGISTRY-DISPATCH-R2-INDEPENDENT-FILE-AUDIT/1",review_status="fresh_selected_membership_and_current_slot_bytes_consistent",findings=[],
        report_sha256=EXPECTED,source_pins=list(sources.values()),original_source_pin_count=5,observer_source_pin_count=len(data["observer_source_pins"]),
        manifest_child_rows_checked=child_rows,identity=data["identity"],new_nonce_distinct_from_prior_report=True,
        source_gate=dict(prior_report_literal_digest=OLD_EXPECTED,old_producer_digest=expected_old_pin["sha256"],
            prior_receipt_assert_line=assertions[0].lineno,producer_pin_assert_line=assertions[1].lineno,
            load_line=exec_calls[0].lineno,gate_before_load=True,old_samples_not_consumed=True,
            old_sample_resolves_roots_again=True,producers_imported_or_executed_by_auditor=False),
        two_fresh_report_samples_equal=True,raw_replays=replays,total_selected_retained_raw_bytes=raw_bytes,
        shared_RPM_budget_consistent=data["rpm_budget"],duration_ms_reported=data["duration_ms_including_host_and_source_checks"],
        boundaries=["Only the supplied raw selected objects/vector/hash chain/cells are replayed; no process access or recapture.",
            "All game-root/PE-header/module/process identity and final reread raw bytes are not retained; those guards remain pinned-reader report assertions.",
            "The three cells contain exact base+builtin addresses in two samples; target implementation code bytes were not supplied as runtime RPM raw, so this is current pointer binding, not a live full-code integrity transcript.",
            "Selected nowargoal hash chain has one exact current definition; other buckets/definitions and full registry semantic uniqueness are not verified.",
            "Fresh globals/nonce source path is consistent and historical samples are not used as pointers; source gate order is inspected, not executed by this auditor.",
            "Two-pass equality/current membership/current dispatch do not establish atomic world snapshot, full-interval dispatch stability, OS join success, callback thread identity or borrowed-object lease.",
            "No new API effect, native executor, lifetime test, save/reload or readiness promotion is established."],
        current_membership_only=True,current_dispatch_binding_only=True,atomic_world_snapshot=False,native_lifetime_authority=False,native_ready=False,
        new_API_effects_verified=0,game_process_accessed=False,native_calls=0,requests_published=0,saves_written=0,reloads=0,frozen_sources_modified=False,
        resources=dict(new_decoded_bytes=0,peak_committed_bytes=check_memory_budget(),memory_limit_bytes=768*1024*1024,shell_sessions_remaining=0))
    OUT.mkdir(parents=True,exist_ok=False)
    with (OUT/"independent-file-audit.json").open("x",encoding="ascii") as f:
        json.dump(result,f,indent=2)
    with (OUT/"report.md").open("x",encoding="utf-8") as f:
        f.write("# Independent registry/dispatch R2 file audit\n\n"
            "The fixed receipt and its source pins match. Source AST confirms the prior receipt digest and old producer pin assertions precede module loading. Historical samples are not read; old.sample resolves current globals/roots afresh. Neither producer was imported or executed in this audit. The new nonce differs from the old receipt.\n\n"
            "Both supplied fresh samples are equal. Replayed1856B selected raw bytes: vector91/cap94 contains exact definition once at index0; sentinel+10 matches; definition vt/enum12 and SSO nowargoal9/cap15 match. Signed-char32-bit hash is112898354, bucket58; its retained one-node chain contains the same definition once and endsNULL. Creator/wait/CFG cell values equal loadedbase+1738D30/1739460/1A79A30 in both samples.\n\n"
            "Source-derived accounting is77 reads/1403B per sample, hence154/2806B with728B largest read; reported duration972.269ms includes host/source checks. Missing complete roots/PE/modules/identity/final reread raw bytes remain pinned-reader assertions. Runtime target code bytes are not provided; cells prove current pointer bindings only. No atomicity, full-interval stability, join/thread/lifetime lease, new API effect or native readiness follows. No game access, new decode, calls, save/reload or frozen edits. native_ready=false.\n")
    seal=dict(schema="EU4-REGISTRY-DISPATCH-R2-REVIEW-MANIFEST/1",files=[pin(Path(__file__)),pin(OUT/"independent-file-audit.json"),pin(OUT/"report.md")])
    with (OUT/"manifest.json").open("x",encoding="ascii") as f:
        json.dump(seal,f,indent=2)
    print(json.dumps(dict(review=pin(OUT/"independent-file-audit.json"),markdown=pin(OUT/"report.md"),manifest=pin(OUT/"manifest.json"),
        source_pins=len(sources),raw_bytes=raw_bytes,new_decoded_bytes=0,native_ready=False)))


if __name__=="__main__":
    main()
