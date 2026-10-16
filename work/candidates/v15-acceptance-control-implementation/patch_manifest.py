"""Add schema3 and exact export/static evidence contract to candidate protocol."""
from pathlib import Path

CONTRACT = {
    "protocol": "EU4LAB/3", "operations": ["accept_on", "accept_off"],
    "on_max_sequence_reserves": 2, "submit_delta": 1, "off_delta": 2,
    "window_grants": 1, "handler_calls_per_transition_max": 1,
    "native_callback_rva": "0xe50180", "normal_string_destructor_rva": "0x95660",
    "zero_argument_qwords": [0, 0, 0], "fresh_result_size_bytes": 40,
    "fresh_legality": "immediately_prior_same_action_target_world_date_unexpired_native_legality_and_gate",
    "off_unlock": "known_cleanup_and_durable_later_healthy_paused_flag_zero",
    "unknown_outcome": "terminal_freeze_without_compensating_toggle",
    "effect_observation_authorizes_native_off": False,
    "natural_ai_acceptance_verified": False, "strict_single_player_verified": False,
    "world_generation_verified": False, "production_backend_registered": False,
}


def transform(s, extra):
    def replace(old,new,count=1):
        nonlocal s
        assert s.count(old)==count,(old[:100],s.count(old))
        s=s.replace(old,new)
    replace('SOURCES = tuple(EXPECTED_NATIVE_SOURCES)', 'SOURCES = tuple(EXPECTED_NATIVE_SOURCES)\nACCEPTANCE_CONTROL_CONTRACT = '+repr(CONTRACT)+'\nACCEPTANCE_STATIC_PATH = "work/candidates/offered-fleet-ai-response-1375/report.json"\nACCEPTANCE_STATIC_SHA256 = "F7EEAE58D29902CA3999C7BD00E47DACDE43E64C72CA215A6DF47417E015EEE5"')
    replace('# This block is inserted into the independent v15 protocol module.', extra+'\n# Versioned recorder; no previous-version export RVA is reused.')
    replace('NATIVE_REVIEW_SHA256 = ', 'NATIVE_REVIEW_PATH = "work/candidates/v15-acceptance-control-implementation/native-source-review.json"\nNATIVE_REVIEW_SHA256 = ')
    replace("manifest={'schema_version':2,'purpose':PURPOSE", "manifest={'schema_version':3,'purpose':PURPOSE")
    replace("'running_speed_enabled':True}", "'running_speed_enabled':True, 'protocol_version':PROTOCOL,\n        'acceptance_control_contract':ACCEPTANCE_CONTROL_CONTRACT,\n        'acceptance_static_report_sha256':ACCEPTANCE_STATIC_SHA256,\n        'bridge_start_export_rva':bridge_start_export_rva(dll)}")
    replace("    publish_exclusive(output/'build.json'", "    require(file_hash(root/ACCEPTANCE_STATIC_PATH)==ACCEPTANCE_STATIC_SHA256,'Acceptance static report changed')\n    publish_exclusive(output/'build.json'")
    replace("'lease_duration_ms','lease_max_raw_date_delta','requires_exact_process_external_watchdog','running_speed_enabled'},", "'lease_duration_ms','lease_max_raw_date_delta','requires_exact_process_external_watchdog','running_speed_enabled',\n        'protocol_version','acceptance_control_contract','acceptance_static_report_sha256','bridge_start_export_rva'},")
    replace("manifest['schema_version']==2", "manifest['schema_version']==3")
    replace("    require(manifest['source_sha256']==EXPECTED_NATIVE_SOURCES", "    require(manifest['protocol_version']==PROTOCOL and canonical(manifest['acceptance_control_contract'])==canonical(ACCEPTANCE_CONTROL_CONTRACT)\n        and manifest['acceptance_static_report_sha256']==ACCEPTANCE_STATIC_SHA256\n        and file_hash(root/ACCEPTANCE_STATIC_PATH)==ACCEPTANCE_STATIC_SHA256\n        and file_hash(root/NATIVE_REVIEW_PATH).lower()==NATIVE_REVIEW_SHA256\n        and integer(manifest['bridge_start_export_rva'],1,2**32-1)\n        and manifest['bridge_start_export_rva']==bridge_start_export_rva(output/DLL_NAME),\n        'Acceptance ABI/window/static source or actual DLL export differs')\n    require(manifest['source_sha256']==EXPECTED_NATIVE_SOURCES")
    replace("    native={name:file_hash(root/name) for name in SOURCES}", "    require(file_hash(root/NATIVE_REVIEW_PATH).lower()==NATIVE_REVIEW_SHA256,'Native source-contract inventory changed')\n    native={name:file_hash(root/name) for name in SOURCES}")
    return s


if __name__ == "__main__":
    raise SystemExit("Use prepare.py --check or --refresh-candidate; patch helpers cannot write independently")
