    intent_raw = (canonical(intent) + "\n").encode()
    # The held intent exception exists only in this invocation, after CREATE_NEW
    # and durable write. It never permits another invocation to reuse the file.
    if phase:
        require(callable(recheck), "Stage publication requires fresh filesystem evidence")
        with _hold_new_phase_intent(intent_path, intent_raw) as validate_owned:
            current_evidence, current_live = recheck()
            owned_evidence = _current_owned_phase_evidence(current_evidence, phase, validate_owned, final, claimed)
            check_ready(owned_evidence, current_live, clock(), phase=phase, operation=operation)
            require(current_evidence["last_sequence"] == evidence["last_sequence"]
                    and all(current_live[key] == live[key] for key in ("pid", "creation", "world_cookie", "player_handle")),
                    "Session/world/sequence changed before phase publication")
            _current_owned_phase_evidence(current_evidence, phase, validate_owned, final, claimed)
            require(not list(session.glob("*.request")), "A competing request appeared during phase publication")
            publish_exclusive(final, raw)
    else:
        publish_exclusive(intent_path, intent_raw)
        # Any failure leaves intent in place; a later invocation cannot retry.
        if recheck is not None:
            current_evidence, current_live = recheck()
            check_ready(current_evidence, current_live, clock(), operation=operation)
            require(current_evidence["last_sequence"] == evidence["last_sequence"]
                    and all(current_live[key] == live[key] for key in ("pid", "creation", "world_cookie", "player_handle")),
                    "Session/world/sequence changed before publication")
        require(clock() < record["expires"], "Publication deadline elapsed; retained intent may not be retried")
        if operation == "fixture":
            proof = fixture_check()
            require(proof.get("pid") == metadata["pid"] and proof.get("creation") == metadata["process_creation_filetime"]
                    and proof.get("profile_sha256") == FIXTURE_PROFILE_SHA256
                    and proof.get("fixture_definition_files_verified") is True and proof.get("installed_before_process_creation") is True
                    and proof.get("engine_registration_verified") is False, "Fixture disk/startup evidence is missing or overclaims loaded registration")
            publish_exclusive(session/f"{sequence:020}.fixture-profile",fixture_proof_wire(metadata,sequence))
            require(clock() < record["expires"], "Fixture proof exceeded publication deadline; no retry")
        publish_exclusive(final, raw)

