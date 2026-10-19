            if name in ("lab_input_wait", "lab_input_failed"):
                kind = event.get("input_kind")
                require(kind in (*PHASES, "request") and event.get("sequence") == last_sequence
                        and type(event.get("sequence")) is int and event.get("native_invoked") is False
                        and event.get("retry_allowed") is False and pending is None and lease is None,
                        "Input diagnostic has an invalid kind, sequence, or operation boundary")
                input_sequence = event.get("input_sequence")
                require(type(input_sequence) is int and input_sequence == (last_sequence + 1 if kind == "request" else 0),
                        "Input diagnostic refers to the wrong unclaimed input")
                if kind == "request":
                    require("command" in proofs and proofs["command"]["passed"], "Request input preceded complete preflight")
                else:
                    order = tuple(PHASES)
                    require(last_sequence == 0 and kind not in proofs and kind not in complete and all(p in proofs for p in order[:order.index(kind)]),
                            "Input diagnostic refers to an already completed or out-of-order phase")
                require(integer(event.get("uptime_ms"), max(1, previous_uptime, last_input_uptime), 2**64 - 1),
                        "Input diagnostic time regressed")
                last_input_uptime = event["uptime_ms"]
                if name == "lab_input_failed":
                    stages = {"open_wait_budget", "wait_begin_audit", "open", "wait_end_audit", "file_type", "file_info",
                              "file_attributes", "file_links", "file_size", "size_range", "read", "read_length", "marker_token",
                              "parse", "pid", "creation", "sequence", "ttl_expired", "ttl_range", "claim_open", "claim_write",
                              "claim_length", "claim_flush", "claim_close", "disposition", "request_close"}
                    require(event.get("stage") in stages and integer(event.get("win32_error"), 0, 2**32 - 1)
                            and integer(event.get("close_win32_error"), 0, 2**32 - 1) and integer(event.get("expires"), 0, 2**64 - 1)
                            and integer(event.get("bytes"), 0, MAX_RECORD) and integer(event.get("attempts"), 1, 16)
                            and all(type(event.get(k)) is bool for k in ("claim_created", "claim_flushed", "request_deleted"))
                            and (not event["claim_flushed"] or event["claim_created"])
                            and (not event["request_deleted"] or event["claim_flushed"]), "Malformed input failure diagnostic")
                    raise LabError("Native input failed; no retry: " + event["stage"]
                                   + "; win32_error=" + str(event["win32_error"])
                                   + "; claim_created=" + str(event["claim_created"]))
                require(event.get("maximum_wait_ms") == 250 and type(event.get("maximum_wait_ms")) is int
                        and event.get("maximum_attempts") == 16 and type(event.get("maximum_attempts")) is int
                        and event.get("win32_error") == 32 and type(event.get("win32_error")) is int
                        and event.get("claim_created") is False and integer(event.get("attempts"), 1, 16)
                        and integer(event.get("elapsed_ms"), 0, 2**64 - 1), "Malformed bounded sharing wait")
                if event.get("wait_state") == "begin":
                    require(input_wait is None and event.get("outcome") == "sharing_violation"
                            and event["attempts"] == 1 and event["elapsed_ms"] == 0, "Duplicate or malformed wait start")
                    input_wait = event
                elif event.get("wait_state") == "end":
                    require(input_wait is not None and all(event[k] == input_wait[k] for k in ("sequence", "input_sequence", "input_kind"))
                            and event["uptime_ms"] >= input_wait["uptime_ms"]
                            and event["elapsed_ms"] == event["uptime_ms"] - input_wait["uptime_ms"]
                            and event["attempts"] >= input_wait["attempts"], "Unbound sharing wait end")
                    outcome = event.get("outcome")
                    require(outcome in ("opened", "budget_exhausted", "disappeared", "open_error"), "Unknown sharing wait outcome")
                    require(outcome != "opened" or event["elapsed_ms"] < 250 and event["attempts"] >= 2,
                            "Opened input exceeded its sharing wait budget or has no second open attempt")
                    input_wait = None
                    require(outcome == "opened", "Native input wait failed; no retry: " + outcome)
                else:
                    raise LabError("Unknown sharing wait state")
                continue
