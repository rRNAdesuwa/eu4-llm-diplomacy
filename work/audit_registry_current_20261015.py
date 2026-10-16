"""File-only replay of retained current-registry raw bytes; never an RPM probe."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import check_memory_budget

SOURCE = ROOT / "work/reports/war-peace-api-20261015-r8-stack-scope/war/live-80340-registry-current.json"
PRODUCER = ROOT / "work/capture_nocb_registry_live_20261015.py"
OUT = ROOT / "work/reports/war-peace-api-20261015-r8-registry-current-review"
EXPECTED = "b9608f0c6343834e6ffa3fec8a7a355f51a91b45080e8d8e04add31c0490e9a5"


def pin(path):
    raw = path.read_bytes()
    assert len(raw) < 16 * 1024 * 1024
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def pointer(value):
    assert type(value) is int and 0x10000 <= value < 2**47
    return value


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        result = json.loads((OUT / "independent-file-audit.json").read_bytes())
        for row in result["source_pins"]:
            assert pin(ROOT / row["path"]) == row
        for row in json.loads((OUT / "manifest.json").read_bytes())["files"]:
            assert pin(ROOT / row["path"]) == row
        print(json.dumps(dict(status="passed", source_pins=len(result["source_pins"]),
            game_process_accessed=False,new_decoded_bytes=0)))
        return
    sources={}
    def fixed(path):
        row=pin(path)
        sources[row["path"]]=row
        return row
    assert fixed(SOURCE)["sha256"] == EXPECTED
    data=json.loads(SOURCE.read_bytes())
    assert data["schema"] == "EU4-NOCB-REGISTRY-CURRENT-READONLY/1"
    for group in ("source_pins","observer_source_pins"):
        for name,row in data[group].items():
            got=fixed(ROOT/name)
            assert (got["bytes"],got["sha256"]) == (row["bytes"],row["sha256"])
    # Check sealed file graphs, not just the manifest bytes named by the receipt.
    graph_count=0
    manifests=[ROOT/n for n in data["source_pins"] if n.endswith("manifest.json")]
    manifests.append(ROOT/"bridge/diplomacy_observer_manifest_1375.json")
    for path in manifests:
        manifest=json.loads(path.read_bytes())
        items=manifest.get("files",manifest.get("sources",[]))
        if isinstance(items,dict):
            items=[dict(path=name,**row) for name,row in items.items()]
        for row in items:
            target=ROOT/row["path"]
            if not target.is_file():
                target=path.parent/row["path"]
            got=fixed(target)
            assert (got["bytes"],got["sha256"]) == (row["bytes"],row["sha256"])
            graph_count+=1
    assert data["identity"]["pid"]==80340 and data["identity"]["creation"]=="01dd5c075fcf8c26"
    assert len(data["identity"]["session"])==32
    base=pointer(int(data["base"],16))
    assert data["two_pass_equal"] is True and len(data["samples"])==2
    assert data["samples"][0]==data["samples"][1]
    replays=[]
    retained_bytes=0
    for number,sample in enumerate(data["samples"],1):
        root=sample["roots"]
        assert root["count"]==1380 and root["count"]<=root["capacity"]<=4096
        assert root["manual_pause"]==1 and root["date"]>0
        assert root["reset"]==root["load_source"]==root["recalculating"]==root["ironman"]==root["selector"]==0
        assert root["alternate_player"]==2960685
        for name in ("game","database","array","server","pause"):
            pointer(int(root[name],16))
        app=sample["application"]
        app_raw=bytes.fromhex(app["raw_hex"])
        assert len(app_raw)==0x18
        app_address=pointer(int(app["address"],16))
        assert app_address!=int(root["database"],16)
        assert struct.unpack_from("<Q",app_raw,0)[0]==base+0x1c48bf8
        assert struct.unpack_from("<Q",app_raw,0x10)[0]==base+0x1c48c80
        assert app["primary_vtable_rva"]=="0x1c48bf8" and app["secondary_vtable_rva"]=="0x1c48c80"
        reg=sample["registry"]
        pointer(int(reg["address"],16))
        reg_raw=bytes.fromhex(reg["raw_hex"])
        assert len(reg_raw)==0x28
        hash_count,buckets,bucket_storage,begin,end,cap=struct.unpack("<IIQQQQ",reg_raw)
        assert 1<=buckets<=4096 and 0<=hash_count<=256
        for value in (bucket_storage,begin,end,cap):
            pointer(value)
        assert begin<=end<=cap and (end-begin)%8==(cap-begin)%8==0
        assert (end-begin)//8<=256 and (cap-begin)//8<=512
        assert reg["hash_count"]==hash_count and reg["bucket_count"]==buckets
        for name,value in (("bucket_storage",bucket_storage),("vector_begin",begin),("vector_end",end),("vector_capacity",cap)):
            assert int(reg[name],16)==value
        array=bytes.fromhex(reg["vector_raw_hex"])
        assert len(array)==end-begin
        values=[v for v, in struct.iter_unpack("<Q",array)]
        for v in values:
            pointer(v)
        assert reg["vector_count"]==len(values)==91
        goal=sample["sentinel"]
        goal_address=pointer(int(goal["address"],16))
        goal_raw=bytes.fromhex(goal["raw_hex"])
        assert len(goal_raw)==0x18 and struct.unpack_from("<Q",goal_raw,0)[0]==base+0x1d207f8
        definition=sample["definition"]
        def_address=pointer(int(definition["address"],16))
        def_raw=bytes.fromhex(definition["raw_hex"])
        assert len(def_raw)==0x40 and struct.unpack_from("<Q",def_raw,0)[0]==base+0x1d20ae0
        assert struct.unpack_from("<i",def_raw,0x38)[0]==definition["enum"]==12
        assert struct.unpack_from("<Q",goal_raw,0x10)[0]==int(goal["definition"],16)==def_address
        assert values.count(def_address)==reg["current_definition_occurrences"]==1
        assert sample["current_definition_in_registry_vector"] is True
        assert sample["current_slot_and_sentinel_definition_match"] is True
        retained_bytes+=len(app_raw)+len(reg_raw)+len(goal_raw)+len(def_raw)+len(array)
        replays.append(dict(pass_number=number,application_address=hex(app_address),registry_address=reg["address"],
            application_primary_rva=hex(struct.unpack_from("<Q",app_raw,0)[0]-base),
            application_secondary_rva=hex(struct.unpack_from("<Q",app_raw,0x10)[0]-base),
            application_distinct_from_country_database=True,application_distinct_from_reported_server=app_address!=int(root["server"],16),
            raw_markers=dict(application=struct.unpack_from("<I",app_raw,8)[0],sentinel=struct.unpack_from("<I",goal_raw,8)[0],
                definition=struct.unpack_from("<I",def_raw,8)[0]),
            registry_hash_header_count=hash_count,bucket_count=buckets,vector_count=len(values),vector_capacity=(cap-begin)//8,
            vector_sha256=hashlib.sha256(array).hexdigest(),current_definition=hex(def_address),
            definition_vector_indices=[i for i,v in enumerate(values) if v==def_address],
            sentinel_address=hex(goal_address),sentinel_definition_matches=True,
            definition_type_rva=hex(struct.unpack_from("<Q",def_raw,0)[0]-base),definition_enum=12,
            raw_hex_payload_bytes=880))
    # Each roots() has18 reads/105B. A sample calls it twice and performs
    #8 slot QWORD reads plus five supplied object/vector reads:49/1154B.
    expected_calls=2*(2*18+8+5)
    expected_bytes=2*(2*105+8*8+880)
    assert data["rpm_budget"]==dict(calls=expected_calls,bytes=expected_bytes,largest_read=728)
    for key in ("atomic_world_snapshot","native_lifetime_authority","native_ready","memory_written","new_API_effect_tested"):
        assert data[key] is False
    for key in ("native_calls","requests_published","saves_written","reloads"):
        assert data[key]==0
    assert data["current_membership_only"] is True
    # Inspect calls as source data. Do not import or execute the live producer.
    tree=ast.parse(PRODUCER.read_text())
    call_names=sorted({ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n,ast.Call)})
    assert not any(any(part in name.lower() for part in ("writeprocessmemory","createremotethread","inject","publish_request","submit")) for name in call_names)
    fixed(Path(__file__))
    result=dict(schema="EU4-NOCB-REGISTRY-CURRENT-INDEPENDENT-FILE-AUDIT/1",
        review_status="retained_current_membership_bytes_and_pins_consistent",findings=[],
        report_sha256=EXPECTED,source_pins=list(sources.values()),original_research_source_pin_count=len(data["source_pins"]),
        observer_source_pin_count=len(data["observer_source_pins"]),direct_manifest_child_file_rows_verified=graph_count,
        identity=data["identity"],captured_utc=data["captured_utc"],base=data["base"],two_samples_exactly_equal=True,
        raw_hex_replays=replays,total_retained_selected_raw_bytes=retained_bytes,
        expected_budget_from_pinned_reader=dict(calls=expected_calls,bytes=expected_bytes,largest_read=728),
        duration_ms_reported=data["duration_ms_including_host_and_source_checks"],
        boundaries=["This auditor only decodes supplied app/registry/sentinel/definition/vector raw bytes from files; it does not access or re-sample a process.",
            "Complete game-root/PE-header/module-list/process-identity raw bytes and final slot reread values are not retained; these guard claims remain pinned-reader report assertions.",
            "98RPM/2308B accounting is consistent with the pinned producer/roots source; no full read transcript independently proves every read value.",
            "Hash header count91 is observed; bucket contents/nodes/name lookup are not retained or independently validated here.",
            "Exact current definition occurs once in the91-entry vector and sentinel+10 equals it; other definition types/payloads are not inspected.",
            "Primary/secondary vtables and raw markers establish observed type consistency; current slot/header equality and two passes are not atomic snapshot or lifetime lease.",
            "Current membership, enum12 and unchanged sampled roots do not establish future noCB constructor/destructor/check/send safety or reset/load immunity.",
            "Reported held-handle/source/module guards are source-consistent; file replay does not reproduce live API receipts or grant execution authority."],
        current_membership_only=True,atomic_world_snapshot=False,native_lifetime_authority=False,native_ready=False,
        new_API_effects_verified=0,new_API_effect_tested=False,game_process_accessed=False,native_calls=0,requests_published=0,
        saves_written=0,reloads=0,frozen_sources_modified=False,
        resources=dict(new_decoded_bytes=0,peak_committed_bytes=check_memory_budget(),memory_limit_bytes=768*1024*1024,shell_sessions_remaining=0))
    OUT.mkdir(parents=True,exist_ok=False)
    with (OUT/"independent-file-audit.json").open("x",encoding="ascii") as f:
        json.dump(result,f,indent=2)
    with (OUT/"report.md").open("x",encoding="utf-8") as f:
        f.write("# Independent current-registry file audit\n\n"
            "The fixed live receipt, research/observer source pins and direct sealed manifest child files match. Both supplied samples are exactly equal. Replayed1760B selected raw app/registry/vector/sentinel/definition bytes: application primary/secondary vtables match; app differs from countryDB; vector91/capacity94 contains exact current definition once at index0; sentinel+10 equals that definition; definition vtable/enum12 match. Hash header count91/buckets511 are raw observations, not a replay of bucket contents.\n\n"
            "Pinned source accounting yields49 reads/1154B per sample, hence98/2308B with728B largest read, matching the receipt. Duration883.52ms includes the producer's host/source checks. The complete game-root, PE-header, modules and process-identity bytes and final root-slot rereads are not provided, so those are source-consistent pinned-reader assertions, not independently replayed raw proof. The live producer was parsed as source data and never imported/executed.\n\n"
            "This validates current selected membership/type decoding only. Two pass equality, current module slots and type consistency provide no atomic-world snapshot or borrowed-object interval lease. No noCB executor/check/send, new API effect, save/reload or game access occurred in this audit. native_ready=false and existing lifetime/reset/load/allocator/exception boundaries remain open.\n")
    seal=dict(schema="EU4-REGISTRY-CURRENT-FILE-AUDIT-MANIFEST/1",files=[pin(Path(__file__)),pin(OUT/"independent-file-audit.json"),pin(OUT/"report.md")])
    with (OUT/"manifest.json").open("x",encoding="ascii") as f:
        json.dump(seal,f,indent=2)
    print(json.dumps(dict(review=pin(OUT/"independent-file-audit.json"),markdown=pin(OUT/"report.md"),manifest=pin(OUT/"manifest.json"),
        source_pins=len(sources),raw_bytes=retained_bytes,new_decoded_bytes=0,native_ready=False)))


if __name__=="__main__":
    main()
