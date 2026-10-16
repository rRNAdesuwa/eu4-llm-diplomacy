def verify_phase(phase, log: Path, pid: int, before: Path, after: Path, build_manifest: Path):
    """Verify a v10 phase prefix plus same-process bounded diagnostic snapshots.

    The on-disk v10 DLL/source manifest and permanent session claims are checked.
    This function never opens a process and does not identify the actually loaded
    DLL independently. Requests after preflight require their own result review.
    """
    from work.native import lab_protocol_v10_1375 as lab
    from tools import verify_diplomacy_preview_v10 as preview
    scopes={"lifecycle":"lifecycle_only", "preview":"native_legality_preview", "command":"command_lifecycle_only"}
    result={"schema_version":1, "verification_scope":scopes.get(phase,"unknown"), "read_only_analysis":True,
            "status":"failed", "runtime_verified":False, "execution_verified":False,
            "diplomatic_submission_verified":False, "ai_acceptance_verified":False, "settlement_verified":False,
            "clone_deallocation_independently_observed":False, "all_game_state_unchanged_verified":False,
            "entire_dll_no_send_verified":False, "pid":pid, "inputs":{}, "errors":[],
            "limitations":["This verifies recorded no-send preflight only; no diplomatic effect or AI acceptance is proved.",
                "Snapshots compare bounded selected fields and are non-atomic; their timestamps do not bracket individual log events.",
                "The disk manifest and claims do not independently identify the actually loaded DLL."]}
    try:
        require(phase in scopes and integer(pid,1), "Unknown phase or invalid PID")
        log, before, after, build_manifest=map(Path,(log,before,after,build_manifest))
        require(log.name == "research-1375.jsonl" and build_manifest.name == "build.json", "Use the v10 session log and build manifest")
        require(before.resolve() != after.resolve(), "Before and after must be separate captured report files")
        manifest,manifest_sha=lab.verify_build(output=build_manifest.parent)
        require(manifest["purpose"] == lab.PURPOSE and set(manifest["source_sha256"]) == set(lab.SOURCES), "Expected the exact v10 fourteen-source build")
        game_hash=hash_value(manifest["game_sha256"])
        initial_report,result["inputs"]["before"]=read_document(before)
        final_report,result["inputs"]["after"]=read_document(after)
        created=initial_report["source"].get("process_creation_filetime")
        require(integer(created,1,2**64-1) and type(final_report["source"].get("process_creation_filetime")) is int
                and final_report["source"]["process_creation_filetime"] == created,
                "Diagnostic reports lack the same complete process creation identity")
        for report in (initial_report,final_report):
            require(report["source"].get("process_exit_filetime") == 0 and type(report["source"].get("process_exit_filetime")) is int,
                    "Diagnostic report lacks an active-process exit identity")
        metadata=lab.read_session_metadata(log.parent,pid,f"{created:016x}")
        evidence=lab.read_evidence(log.parent,metadata)
        require(not evidence["requests"], "Verify the preserved preflight-only prefix; later requests require a separate review")
        proof=evidence["phase_proofs"].get(phase)
        require(proof is not None and proof["passed"] is True, "The exact v10 session phase did not pass")
        result["session"]=proof
        result["inputs"]["log"]={"name":log.name,"sha256":evidence["log_sha256"]}
        result["inputs"]["build_manifest"]={"name":build_manifest.name,"sha256":manifest_sha}
        result["build"]={"game_sha256":game_hash,"dll_sha256":manifest["dll_sha256"],"purpose":manifest["purpose"],
                          "source_and_dll_disk_hashes_verified":True,"loaded_dll_identity_verified":False}
        initial=snapshot_projection(initial_report,pid,game_hash)
        final=snapshot_projection(final_report,pid,game_hash)
        require(initial["captured_at"] < final["captured_at"], "After capture must be later than before")
        require(time_value(manifest["built_at_utc"],"built_at_utc") <= final["captured_at"], "Build postdates the final snapshot")
        require(initial["player"]["tag"] == initial["actor"] == "FRA" and initial["target"] == "ENG", "Diagnostic snapshot must use player/actor FRA and target ENG")
        fields=["module_base","actor","target","player","current_raw_date","relation_cooldown","actor_diplomats"]
        if phase != "lifecycle":
            initial["country_handles"]=preview.identities(initial_report)
            final["country_handles"]=preview.identities(final_report)
            fields.append("country_handles")
            phases=(proof["prior_lifecycle_and_preview"],proof["command_phase"]) if phase == "command" else (proof,)
            for item in phases:
                require(item["raw_dates"] == [initial["current_raw_date"]] and item["country_handles"] == initial["country_handles"],
                        "Phase dates/country handles differ from the diagnostic snapshots")
        comparisons={key:{"equal":initial[key] == final[key],"before":initial[key],"after":final[key]} for key in fields}
        result["snapshot_comparison"]={"fields":comparisons,"all_compared_fields_equal":all(v["equal"] for v in comparisons.values()),
            "before_captured_at_utc":initial["captured_at"].isoformat(),"after_captured_at_utc":final["captured_at"].isoformat(),"atomic":False}
        require(result["snapshot_comparison"]["all_compared_fields_equal"], "A bounded diagnostic field changed")
        result.update(status="passed",runtime_verified=True)
    except (OSError,ValueError,KeyError,TypeError,AttributeError,OverflowError,RuntimeError) as exc:
        result["errors"].append(str(exc))
    return result


def verify(log: Path, pid: int, before: Path, after: Path, build_manifest: Path):
    return verify_phase("lifecycle",log,pid,before,after,build_manifest)

