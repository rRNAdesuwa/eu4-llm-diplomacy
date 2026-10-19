"""EU4LAB/3 restricted research tooling. Not the production EU4PAIR/1 backend.

Pure helpers are import-safe. LiveLabProcess opens QUERY_INFORMATION|VM_READ
only; the separately named loader is the sole injection entry point.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re

from bridge.diplomacy_api import canonical, decode_json
from bridge.native_build import LOCAL_SHA256
from bridge.native_pair_backend import _no_links, _private_root, publish_exclusive, read_bounded, uptime_ms

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "work/runtime/native1375-v15"
DLL_NAME = "eu4_pair_lab_v15_1375.dll"
PURPOSE = "restricted_pair_lab_1375_v15"
# Frozen v15 request allowlist; future production/backend additions cannot widen it.
ACTIONS = frozenset(('offer_vassalization', 'cancel_vassalization', 'royal_marriage', 'break_marriage', 'improve_relations', 'stop_improving_relations', 'guarantee', 'revoke_guarantee', 'build_spy_network', 'stop_building_spy_network', 'offer_alliance', 'dissolve_alliance', 'ask_military_access', 'cancel_military_access', 'offer_military_access', 'revoke_military_access', 'ask_fleet_basing_rights', 'cancel_fleet_basing_rights', 'offer_fleet_basing_rights', 'revoke_fleet_basing_rights', 'embargo', 'revoke_embargo', 'give_subsidies', 'cancel_subsidies', 'warn', 'insult', 'form_coalition', 'leave_coalition', 'support_independence', 'cancel_independence_support', 'request_trade_power', 'cancel_trade_power_transfer', 'steer_trade', 'cancel_steer_trade', 'send_gift', 'trade_favors_for_gold'))
FIXED_RESEARCH_PARAMETERS = {'give_subsidies': {'monthly_amount': '1.000', 'duration_years': 10}, 'cancel_subsidies': {'monthly_amount': '1.000', 'duration_years': 10}, 'send_gift': {'amount': '25.000'}, 'insult': {'index': -1}, 'request_trade_power': {'fraction_milli': 500}, 'cancel_trade_power_transfer': {'fraction_milli': 500}}

PROTOCOL = "EU4LAB/3"
MAX_LOG = 8 * 1024 * 1024
MAX_LINE = 16384
MAX_RECORD = 1024
MAX_SEQUENCE = 2**63 - 1
MAX_TTL = 60000
FRAME_MAX_AGE = 2500
FIELDS = ("pid", "creation", "sequence", "expires", "operation", "mode", "action", "actor", "target", "speed", "bound_action", "bound_target", "bound_submit_sequence")
TAGS = ("FRA", "ENG", "POR", "NAV", "FOI")
FIXTURE_ACTIONS = ("fixture_on", "fixture_off")
FIXTURE_PROFILE_ID = "1375_test_fixture_v3"
FIXTURE_CANDIDATE_ROOT = "work/candidates/fixture-v15-1375"
FIXTURE_SOURCES = tuple("mod/llm_diplomacy_test/" + name for name in (
    "descriptor.mod", "common/defines/zz_llm_diplomacy_test.lua", "events/llmt_fixture.txt",
    "common/event_modifiers/llm_diplomacy_test.txt", "common/opinion_modifiers/llmt_fixture.txt"))
FIXTURE_PROFILE_SHA256 = "f3507bb78f665443c5dad20efee0aef2dd86a8b6741130ee03e883b2ecc1a507"
FIXTURE_EVENT_CONTRACT_READY = True
NATIVE_REVIEW_PATH = "work/candidates/v15-acceptance-control-implementation/native-source-review.json"
NATIVE_REVIEW_SHA256 = '592a8f43b1b900750f3ec104e74fa6e5ec198af7cd59c8ab851bfbb0b171aa70'
EXPECTED_NATIVE_SOURCES = {'work/native/test-fixture-v15-1375.cpp': 'E6D934FA27E7AEA84A5971ED4A91FB5E033DE8E7D85C96E96C31D8169EB1B287', 'work/native/test-fixture-v15-1375.h': 'F4D313E00866D7CC94221317F8123935364B48950F1B7071176D044639951474', 'work/native/v15/build-lab-1375.cmd': '5141508C53E27B817676176C48C8AEA42ADCEE0655519D6CC3D819DA84CBC4F9', 'work/native/v15/default-contract.h': 'BF87B29FEC436D8A9BA16C9E9F3A69F2336D7F94C9004DDC58F3B385342D3853', 'work/native/v15/lab-request-1375.h': '83F3BC56A6A4C3A6646F98D41257AC5D6622A9F93E36273EAD45A1DD7FDB1559', 'work/native/v15/owned-peace-host-1375.inc': 'AA4792CE67DAECEAF4FABBE4497B40B9DECFD97C9D12F77C80EB60B88D601716', 'work/native/v15/owned-peace-stage-1375.h': '707DDB599209D6CFF749B2356A19E8D2D6783D024DAEC72494354F84FECE2CA7', 'work/native/v15/pair-command-v6-1375.cpp': 'DC06CF5D19F7D528E4A1224F7D1EBABD9DE426509A37D20E863167A3C2C4BBCC', 'work/native/v15/pair-engine-1375.cpp': '22CA42EB642B4BAEEBC02BB73ED0CF3E889D782BDF68527C93CA9EA4559A6C3E', 'work/native/v15/pair-engine-1375.h': 'F5257B31CA81E3C886F501433CCE1DA3EABA0DA868BEC3225412CB03FEE2A526', 'work/native/v15/pair-preview-v6-1375.cpp': 'CF14D82D4CE804A3CA7EE38D586F688D1259686DDDD449BE40C9A30BB7EC7B57', 'work/native/v15/pair-probe-v6-1375.cpp': 'A605392C57846C3DF532B290BE6960FAC1EAD144A7611E3CEE3EDA81C60FFCCA', 'work/native/v15/peace-owned-lifecycle-1375.cpp': '60BD30614B16EAF67D1DCB8F85463D1E7DF4DE44418B4B9FB62AD8B014A1A067', 'work/native/v15/peace-owned-lifecycle-1375.h': '56389ED955D527925DCD836AD5E54DD20CC4AA88CC9E4E872685653AF19EB1D9', 'work/native/v15/pins.h': '321C97C0FF0551D0C34D2091563865ECFAFE2E8BB3397AA6A37571F509F72FAE', 'work/native/v15/research-frame-v6-1375.asm': '3D5DA5AEA5408D4991FCE7BB19275025E7D28BCBBFC90C08D82E797AD09D30F0', 'work/native/v15/research-lab-1375.cpp': '52C7706B68C7B2DE797DD1ECC802FB4FA855E0D94484FAB4210DBECEB893D4DC', 'work/native/v15/research-lab-bootstrap-1375.inc': '30AD92E553C28BA21582C26B337A2596AA0BA97E0623F48FB9734907B9FC6EC1', 'work/native/v15/test-controls-1375.cpp': 'C955CA8A4527A1FE6F5A8418B601EECE2363A47C3C82CD3BE2B261798F869615', 'work/native/v15/test-controls-1375.h': '7EFC2CA22D723941086A2E68ED63FC4D6A80392BD78D7902884F437863B338E7', 'work/native/v15/test-acceptance-1375.h': 'C1835F812EE230303FB2F26814D1C848C55706D14AFE4FADF863C01FED078328', 'work/native/v15/test-acceptance-1375.cpp': '9435FB758CD9C1CF45BFA6180BAE9856551C64223C3E6C7C74C04F3F94D2FEFB'}
SOURCES = tuple(EXPECTED_NATIVE_SOURCES)
ACCEPTANCE_CONTROL_CONTRACT = {'protocol': 'EU4LAB/3', 'operations': ['accept_on', 'accept_off'], 'on_max_sequence_reserves': 2, 'submit_delta': 1, 'off_delta': 2, 'window_grants': 1, 'handler_calls_per_transition_max': 1, 'native_callback_rva': '0xe50180', 'normal_string_destructor_rva': '0x95660', 'zero_argument_qwords': [0, 0, 0], 'fresh_result_size_bytes': 40, 'fresh_legality': 'immediately_prior_same_action_target_world_date_unexpired_native_legality_and_gate', 'off_unlock': 'known_cleanup_and_durable_later_healthy_paused_flag_zero', 'unknown_outcome': 'terminal_freeze_without_compensating_toggle', 'effect_observation_authorizes_native_off': False, 'natural_ai_acceptance_verified': False, 'strict_single_player_verified': False, 'world_generation_verified': False, 'production_backend_registered': False}
ACCEPTANCE_STATIC_PATH = "work/candidates/offered-fleet-ai-response-1375/report.json"
ACCEPTANCE_STATIC_SHA256 = "F7EEAE58D29902CA3999C7BD00E47DACDE43E64C72CA215A6DF47417E015EEE5"
HOST_SOURCES = ('bridge/diplomacy_lab_http_v15.py', 'tools/request_diplomacy_lab_v15.py', 'tools/serve_diplomacy_lab_v15.py', 'tools/verify_diplomacy_command_v15.py', 'tools/verify_diplomacy_lifecycle_v15.py', 'tools/verify_diplomacy_owned_peace_v15.py', 'tools/verify_diplomacy_preview_v15.py', 'work/native/inject_lab_v15_1375.py', 'work/native/lab_protocol_v15_1375.py', 'work/native/record_lab_v15_build.py', 'work/native/run_lab_speed_v15_1375.py', 'tools/verify_diplomacy_acceptance_v15.py')
EXPECTED_SUPPORT_SOURCES = {'bridge/diplomacy_api.py': '2887E6AF632B50BE136D88CBFEAA6B861E7760AB34D534E5935E1596F2B33F6A', 'bridge/diplomacy_lab_http.py': '92EE036DAC122B278F8A9E1C9AEFBD624554A6808CC67EB7D62931C1FB2D66B0', 'bridge/native_build.py': '2F8F7F1781F10084ED85CAE59F876080A9CD0EFCF9810E1FC394561682048925', 'bridge/native_pair_backend.py': '0D8E36B56DB7E37B3D36134DE7A0C27130468BFDB8DE6C2710A3FFDDF7A96915', 'work/local_config.py': '55A3BCE5A2BF98F83C58E27884699C780456EA40B84D11BCAC5FE78082262001', 'work/native/inject_probe.py': '18A6E5D7CFAB4607A4B964D23002B71B8C9352D41C8324F1C9E5740534EA0B4F', 'work/native/lab_protocol_v9_1375.py': '0B94213F9FD052A262CA3A700AD19466F388AC34A28D0CE8FF5370FE91383F9E', 'work/probe_diplomacy_current.py': 'A5A0B775A701466CF5F4C85DB671E37F81C165DAF5FDDD2080B71ED6F147BB38'}
SUPPORT_SOURCES = tuple(EXPECTED_SUPPORT_SOURCES)
OWNED_PEACE_STAGE_CONTRACT = {'stages': ['lifecycle', 'owned_peace', 'preview', 'command'], 'counts': [20, 1, 72, 72], 'requires_following_health': True, 'owned_peace_send': False, 'world_generation_verified': False}
PHASES = {
    'lifecycle': ('pair-selftest.request','phase-lifecycle.claim',b'PAIR_SELFTEST_1375\n'),
    'owned_peace': ('owned-peace-lifecycle.request','phase-owned-peace-lifecycle.claim',None),
    'preview': ('pair-preview.request','phase-preview.claim',b'PAIR_PREVIEW_1375\n'),
    'command': ('pair-command.request','phase-command.claim',b'PAIR_COMMAND_1375\n'),
}
TEST_SAVES = {
    "llm_diplomacy_1375_baseline.eu4": "276F88AFECDBC1F1A24ED6314845351B1BA5640715B7ED1FD14513B3376664FB",
    "llm_diplomacy_1375_after_improve.eu4": "7BFABE371E68AE502B806F9B80375FC8A4DAC638AD116D2506966FEF69633C5F",
}


class LabError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise LabError(message)


def integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def phase_wire(phase, metadata):
    require(phase in PHASES, "Unknown explicit research phase")
    if phase != "owned_peace":
        return PHASES[phase][2]
    require(integer(metadata.get("pid"),1,2**32-1)
        and isinstance(metadata.get("process_creation_filetime"),str)
        and re.fullmatch(r"[0-9a-f]{16}",metadata["process_creation_filetime"])
        and int(metadata["process_creation_filetime"],16)>0,"Invalid owned-peace marker process identity")
    return (f"OWNED_PEACE_LIFECYCLE/1\npurpose={PURPOSE}\npid={metadata['pid']}\n"
        f"creation={metadata['process_creation_filetime']}\n").encode("ascii")


def encode_request(record):
    require(isinstance(record, dict) and set(record) == set(FIELDS), "Request has unknown/missing fields")
    require(integer(record["pid"], 1, 2**32 - 1), "Invalid PID")
    require(isinstance(record["creation"], str) and re.fullmatch(r"[0-9a-f]{16}", record["creation"])
            and int(record["creation"], 16) > 0, "Invalid process creation identity")
    require(integer(record["sequence"], 1, MAX_SEQUENCE) and integer(record["expires"], 1, 2**64 - 1), "Invalid sequence/expiry")
    require(integer(record["speed"], 0, 5), "Invalid speed")
    if record["operation"] == "pair":
        require(isinstance(record["action"], str) and record["action"] in ACTIONS, "Unknown pair action")
        require(record["mode"] in ("legality_only", "submit") and record["speed"] == 0, "Invalid pair mode/speed")
        require(record["actor"] in TAGS and record["target"] in TAGS
                and record["actor"] != record["target"], "Invalid research country pair")
    elif record["operation"] == "speed":
        require(record["mode"] == "submit" and record["action"] == "none"
                and record["actor"] == record["target"] == "FRA", "Invalid speed request fields")
    elif record["operation"] == "fixture":
        require(record["mode"] == "submit" and record["action"] in FIXTURE_ACTIONS
                and record["actor"] == record["target"] == "FRA" and record["speed"] == 0,
                "Fixture requests accept only the fixed FRA fixture_on/fixture_off profile")
    elif record["operation"] == "accept":
        require(record["mode"] == "submit" and record["action"] in ("accept_on", "accept_off")
                and record["actor"] == record["target"] == "FRA" and record["speed"] == 0,
                "Invalid fixed acceptance operation")
        require(record["bound_action"] in ACTIONS and record["bound_target"] in TAGS
                and record["bound_target"] != "FRA", "Invalid acceptance binding")
        require(integer(record["bound_submit_sequence"], 1, MAX_SEQUENCE), "Invalid bound sequence")
        if record["action"] == "accept_on":
            require(record["sequence"] <= MAX_SEQUENCE - 2 and record["bound_submit_sequence"] == record["sequence"] + 1,
                    "On must reserve the consecutive submit and off slots")
        else:
            require(record["sequence"] >= 3 and record["bound_submit_sequence"] == record["sequence"] - 1,
                    "Off must use the slot immediately after its original submit")
    else:
        raise LabError("Unknown research operation")
    if record["operation"] != "accept":
        require(record["bound_action"] == record["bound_target"] == "none"
                and type(record["bound_submit_sequence"]) is int and record["bound_submit_sequence"] == 0,
                "Ordinary operations require exact unbound sentinels")
    raw = (PROTOCOL + "\n" + "".join(f"{key}={record[key]}\n" for key in FIELDS)).encode("ascii")
    require(len(raw) <= MAX_RECORD, "Request exceeds protocol limit")
    return raw


def decode_request(raw):
    require(isinstance(raw, bytes) and len(raw) <= MAX_RECORD and raw.endswith(b"\n"), "Invalid request framing")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise LabError("Request must be ASCII") from error
    require(len(lines) == len(FIELDS) + 1 and lines[0] == PROTOCOL, "Wrong protocol or field count")
    record = {}
    for line, key in zip(lines[1:], FIELDS):
        require(line.startswith(key + "="), "Wrong field order, duplicate or unknown key")
        value = line[len(key) + 1:]
        if key in ("pid", "sequence", "expires", "speed", "bound_submit_sequence"):
            require(bool(re.fullmatch(r"0|[1-9][0-9]{0,19}", value)), "Noncanonical integer")
            value = int(value)
        record[key] = value
    require(encode_request(record) == raw, "Request is not canonical")
    return record


def file_hash(path):
    _no_links(Path(path))
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest().upper()


def fixture_source_path(root, name):
    """Reviewed candidate source, separate from the installed mod namespace."""
    require(name in FIXTURE_SOURCES, "Unknown fixed fixture source")
    return Path(root) / FIXTURE_CANDIDATE_ROOT / name


def fixture_profile(root=ROOT):
    profile = {"profile_id": FIXTURE_PROFILE_ID, "source_sha256": {name:file_hash(fixture_source_path(root,name)) for name in FIXTURE_SOURCES}}
    require(hashlib.sha256(canonical(profile).encode("ascii")).hexdigest() == FIXTURE_PROFILE_SHA256,
            "Fixture definitions differ from the fixed native profile")
    return profile


def fixture_proof_wire(metadata, sequence):
    require(integer(metadata.get("pid"), 1, 2**32-1) and integer(sequence, 1, MAX_SEQUENCE)
            and isinstance(metadata.get("process_creation_filetime"), str)
            and re.fullmatch(r"[0-9a-f]{16}", metadata["process_creation_filetime"]), "Invalid fixture proof identity")
    return (f"EU4FIXTURE/1\npid={metadata['pid']}\ncreation={metadata['process_creation_filetime']}\nsequence={sequence}\n"
            f"profile={FIXTURE_PROFILE_SHA256}\n").encode("ascii")


def verify_installed_fixture(manifest, pid, creation, *, root=ROOT, user_root=None):
    """Disk/startup evidence only; never claims engine event registration."""
    from work.local_config import user_data
    require(integer(pid,1,2**32-1) and isinstance(creation,str) and re.fullmatch(r"[0-9a-f]{16}",creation), "Invalid fixture process identity")
    process_ns = (int(creation,16)-116444736000000000)*100
    require(process_ns>0, "Invalid fixture creation timestamp")
    profile = fixture_profile(root)
    require(manifest.get("fixture_profile") == profile, "Manifest fixture profile differs from reviewed definitions")
    destination = Path(user_root) if user_root is not None else user_data()
    settings = destination/"dlc_load.json"
    config = decode_json(read_bounded(settings,1024*1024).decode("utf-8-sig"))
    require(isinstance(config.get("enabled_mods"),list) and "mod/llm_diplomacy_test.mod" in config["enabled_mods"], "Fixed test mod is not enabled")
    checked = [settings]
    for name,digest in profile["source_sha256"].items():
        installed = destination/name
        require(file_hash(installed)==digest, f"Installed fixture definition differs: {name}")
        checked.append(installed)
    descriptor = destination/"mod/llm_diplomacy_test.mod"
    source_descriptor = read_bounded(fixture_source_path(root,FIXTURE_SOURCES[0]),16384).decode("utf-8").replace("\r\n","\n")
    expected = source_descriptor+'\npath="mod/llm_diplomacy_test"\n'
    require(read_bounded(descriptor,32768).decode("utf-8").replace("\r\n","\n")==expected, "Enabled descriptor does not select the fixed fixture directory")
    checked.append(descriptor)
    require(all(0<path.stat().st_mtime_ns<process_ns for path in checked), "Fixture files or enabled-mod configuration changed after process creation")
    return {"pid":pid,"creation":creation,"profile_sha256":FIXTURE_PROFILE_SHA256,
            "fixture_definition_files_verified":True,"installed_before_process_creation":True,
            "engine_registration_verified":False,"files_checked":len(checked),
            "enabled_mod_configuration_sha256":file_hash(settings)}


# The PE export is parsed from the actual new DLL. No mapping, DllMain or callback.
def bridge_start_export_rva(path):
    import struct
    raw = read_bounded(Path(path), 32 * 1024 * 1024)
    def u16(o):
        require(0 <= o <= len(raw) - 2, "Truncated export PE")
        return struct.unpack_from("<H", raw, o)[0]
    def u32(o):
        require(0 <= o <= len(raw) - 4, "Truncated export PE")
        return struct.unpack_from("<I", raw, o)[0]
    require(raw[:2] == b"MZ", "Not a PE image")
    pe = u32(0x3c)
    require(pe <= 4096 and raw[pe:pe+4] == b"PE\0\0" and u16(pe+4) == 0x8664, "Expected AMD64 export PE")
    opt = pe + 24
    require(u16(opt) == 0x20b and u16(pe+20) >= 120 and u32(opt+108) >= 1,
            "Expected PE32+ optional header with an export directory")
    size_image = u32(opt+56)
    export, size_export = u32(opt+112), u32(opt+116)
    section_count, table = u16(pe+6), opt+u16(pe+20)
    require(1 <= section_count <= 96 and 0 < export < size_image and size_export >= 40,
            "Invalid bounded PE export directory")
    sections = []
    for index in range(section_count):
        h = table + 40*index
        sections.append((u32(h+12), u32(h+16), u32(h+20), u32(h+36)))
    def offset(rva, length):
        require(integer(rva,1,size_image-1) and integer(length,1,len(raw)), "Invalid bounded export RVA")
        for start,size,position,_ in sections:
            if start <= rva and rva + length <= start + size and position + rva-start + length <= len(raw):
                return position+rva-start
        raise LabError("Export RVA is outside backed sections")
    e = offset(export,40)
    functions,names = u32(e+20),u32(e+24)
    require(1 <= functions <= 4096 and 1 <= names <= 4096, "Export count bound")
    functions_at,names_at,ordinals_at = offset(u32(e+28),4*functions),offset(u32(e+32),4*names),offset(u32(e+36),2*names)
    matches=[]
    for index in range(names):
        name_at=offset(u32(names_at+4*index),1)
        end=raw.find(b"\0",name_at,min(len(raw),name_at+128))
        require(end != -1,"Unbounded export name")
        if raw[name_at:end] == b"BridgeStart":
            ordinal=u16(ordinals_at+2*index)
            require(ordinal < functions,"Export ordinal out of range")
            rva=u32(functions_at+4*ordinal)
            require(not export <= rva < export+size_export,"Forwarded BridgeStart is unsupported")
            offset(rva,1)
            require(any(start <= rva < start+size and flags & 0x20000000 for start,size,_,flags in sections),
                    "BridgeStart is not in an executable section")
            matches.append(rva)
    require(len(matches)==1,"Expected unique real BridgeStart export")
    return matches[0]

# Versioned recorder; no previous-version export RVA is reused.
def record_build(root=ROOT, output=OUTPUT):
    root,output=Path(root),Path(output)
    dll=output/DLL_NAME
    require(dll.is_file(),'Successful DLL build is required first')
    require(not (output/'build.json').exists(),'Build manifest exists; formal v15 build may not be overwritten')
    require(not any(output.glob('session-*')),'Refuse recording a used v15 runtime')
    require(file_hash(root/NATIVE_REVIEW_PATH).lower()==NATIVE_REVIEW_SHA256,'Native source-contract inventory changed')
    native={name:file_hash(root/name) for name in SOURCES}
    require(native==EXPECTED_NATIVE_SOURCES,'Native sources differ from the fixed reviewed v15 candidate')
    support={name:file_hash(root/name) for name in SUPPORT_SOURCES}
    require(support==EXPECTED_SUPPORT_SOURCES,'Shared host support differs from reviewed inputs')
    speed_flags=re.findall(r'static constexpr bool running_speed_enabled = (true|false);',
        read_bounded(root/'work/native/v15/research-lab-1375.cpp',1024*1024).decode())
    require(speed_flags==['true'],'Reviewed v15 speed lease gate changed')
    manifest={'schema_version':3,'purpose':PURPOSE,'game_sha256':LOCAL_SHA256,
        'built_at_utc':datetime.now(timezone.utc).isoformat(),'dll_sha256':file_hash(dll),
        'source_sha256':native,'host_source_sha256':{name:file_hash(root/name) for name in HOST_SOURCES},
        'support_source_sha256':support,'native_candidate_review_sha256':NATIVE_REVIEW_SHA256,
        'owned_peace_stage_contract':OWNED_PEACE_STAGE_CONTRACT,
        'runtime_verified':False,'production_backend_registered':False,'fixture_profile':fixture_profile(root),
        'lease_duration_ms':5000,'lease_max_raw_date_delta':48,'requires_exact_process_external_watchdog':True,
        'running_speed_enabled':True, 'protocol_version':PROTOCOL,
        'acceptance_control_contract':ACCEPTANCE_CONTROL_CONTRACT,
        'acceptance_static_report_sha256':ACCEPTANCE_STATIC_SHA256,
        'bridge_start_export_rva':bridge_start_export_rva(dll)}
    require(file_hash(root/ACCEPTANCE_STATIC_PATH)==ACCEPTANCE_STATIC_SHA256,'Acceptance static report changed')
    publish_exclusive(output/'build.json',(canonical(manifest)+'\n').encode())
    return manifest

def verify_build(root=ROOT, output=OUTPUT):
    root,output=Path(root),Path(output)
    raw=read_bounded(output/'build.json',65536)
    manifest=decode_json(raw.decode())
    require(isinstance(manifest,dict) and set(manifest)=={'schema_version','purpose','game_sha256','built_at_utc',
        'dll_sha256','source_sha256','host_source_sha256','support_source_sha256','native_candidate_review_sha256',
        'owned_peace_stage_contract','runtime_verified','production_backend_registered','fixture_profile',
        'lease_duration_ms','lease_max_raw_date_delta','requires_exact_process_external_watchdog','running_speed_enabled',
        'protocol_version','acceptance_control_contract','acceptance_static_report_sha256','bridge_start_export_rva'},
        'Unexpected v15 build manifest schema')
    require(type(manifest['schema_version']) is int and manifest['schema_version']==3
        and manifest['purpose']==PURPOSE and manifest['game_sha256']==LOCAL_SHA256
        and manifest['runtime_verified'] is False and manifest['production_backend_registered'] is False
        and manifest['native_candidate_review_sha256']==NATIVE_REVIEW_SHA256
        and canonical(manifest['owned_peace_stage_contract'])==canonical(OWNED_PEACE_STAGE_CONTRACT),
        'Manifest differs from fixed v15 four-stage research contract')
    require(type(manifest['lease_duration_ms']) is int and manifest['lease_duration_ms']==5000
        and type(manifest['lease_max_raw_date_delta']) is int and manifest['lease_max_raw_date_delta']==48
        and manifest['requires_exact_process_external_watchdog'] is True and manifest['running_speed_enabled'] is True,
        'Manifest differs from bounded speed lease contract')
    require(manifest['protocol_version']==PROTOCOL and canonical(manifest['acceptance_control_contract'])==canonical(ACCEPTANCE_CONTROL_CONTRACT)
        and manifest['acceptance_static_report_sha256']==ACCEPTANCE_STATIC_SHA256
        and file_hash(root/ACCEPTANCE_STATIC_PATH)==ACCEPTANCE_STATIC_SHA256
        and file_hash(root/NATIVE_REVIEW_PATH).lower()==NATIVE_REVIEW_SHA256
        and integer(manifest['bridge_start_export_rva'],1,2**32-1)
        and manifest['bridge_start_export_rva']==bridge_start_export_rva(output/DLL_NAME),
        'Acceptance ABI/window/static source or actual DLL export differs')
    require(manifest['source_sha256']==EXPECTED_NATIVE_SOURCES and manifest['support_source_sha256']==EXPECTED_SUPPORT_SOURCES,
        'Native or shared support source pin differs from reviewed candidate')
    require(isinstance(manifest['host_source_sha256'],dict) and set(manifest['host_source_sha256'])==set(HOST_SOURCES),
        'v15 host source manifest is incomplete')
    for section in ('source_sha256','host_source_sha256','support_source_sha256'):
        for name,digest in manifest[section].items():
            require(file_hash(root/name)==digest,'Source changed after build: '+name)
    require(manifest['fixture_profile']==fixture_profile(root),'Fixture differs from fixed reviewed definitions')
    require(file_hash(output/DLL_NAME)==manifest['dll_sha256'],'DLL changed after build')
    return manifest,hashlib.sha256(raw).hexdigest()


def verify_test_save(name, save_root=None):
    from work.local_config import user_data
    require(name in TEST_SAVES, "Only the two audited independent-NAV baseline saves are accepted")
    path = (Path(save_root) if save_root else user_data() / "save games") / name
    require(file_hash(path) == TEST_SAVES[name], "Disposable test save differs from its audited bytes")
    with path.open("rb") as stream:
        head = stream.read(4096)
    require(head.startswith(b"EU4txt\n") and b"\nmulti_player=no\n" in head and b'\nplayer="FRA"\n' in head,
            "Expected serialized single-player FRA test premise")
    return {"path": str(path), "sha256": TEST_SAVES[name], "serialized_single_player": True,
            "loaded_save_identity_verified": False, "strict_live_single_player_verified": False,
            "scope": "isolated disposable test premise; file existence does not identify the live world"}


class LiveLabProcess:
    """A held read-only process handle; does not enumerate unrelated memory."""
    def __init__(self, pid, *, expected_creation=None, output=OUTPUT, require_loaded=True):
        from work.local_config import game_root
        from work.probe_diplomacy_current import ProcessReader, pe_signature, verified_executable
        from work.native import inject_probe
        self.reader = None
        self.output, self.pid = Path(output), pid
        executable = game_root() / "eu4.exe"
        _, signature = verified_executable(executable)
        self.reader = ProcessReader(pid, executable, signature)
        try:
            self.kernel = inject_probe._configure_kernel32()
            self.kernel.GetProcessTimes.argtypes = [W.HANDLE, C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME)]
            self.kernel.GetProcessTimes.restype = W.BOOL
            created, exited, cpu_kernel, cpu_user = W.FILETIME(), W.FILETIME(), W.FILETIME(), W.FILETIME()
            require(self.kernel.GetProcessTimes(self.reader.handle, C.byref(created), C.byref(exited), C.byref(cpu_kernel), C.byref(cpu_user))
                    and not (exited.dwLowDateTime or exited.dwHighDateTime), "Cannot identify the current live process")
            self.creation = f"{(created.dwHighDateTime << 32) | created.dwLowDateTime:016x}"
            require(expected_creation is None or expected_creation == self.creation, "PID creation identity changed")
            self.modules = inject_probe._enum_modules(self.kernel, self.reader.handle)
            matches = inject_probe._find_module(self.modules, self.output / DLL_NAME)
            if require_loaded:
                require(len(matches) == 1, "The exact v15 lab DLL is not uniquely loaded")
                with (self.output / DLL_NAME).open("rb") as stream:
                    local_signature = pe_signature(stream)
                require(pe_signature(self.reader, matches[0].handle) == local_signature, "Loaded DLL PE identity differs from disk")
            else:
                require(not any(Path(module.path).name.lower().startswith(("eu4_pair_", "eu4_bridge_")) for module in self.modules),
                        "A bridge is already loaded; never hot-replace or rearm this process")
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.reader:
            self.reader.close()
            self.reader = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def snapshot(self):
        from work.probe_diplomacy_current import GAME_POINTER_RVA, DATABASE_POINTER_RVA
        import struct
        def u64(address):
            return struct.unpack("<Q", self.reader.read(address, 8))[0]
        game = u64(self.reader.base + GAME_POINTER_RVA)
        database = u64(self.reader.base + DATABASE_POINTER_RVA)
        player = u64(game + 0x1e60)
        date = struct.unpack("<i", self.reader.read(game + 0x1dd0, 4))[0]
        require(game >= 0x10000 and database >= 0x10000 and player == 0x0100007a00415246 and date > 0,
                "Live FRA world identity is unavailable")
        flag = self.reader.read(game + 0x23a1, 1)[0]
        require(flag in (0, 1) and self.reader.read(game + 0x23a1, 1)[0] == flag, "Acceptance flag is noncanonical or changed")
        require(u64(self.reader.base + GAME_POINTER_RVA) == game and u64(game + 0x1e60) == player,
                "Live world changed during observation")
        return {"pid": self.pid, "creation": self.creation, "world_cookie": hex(game),
                "player_handle": f"0x{player:016x}", "raw_date": date, "acceptance_flag": flag}


@contextmanager
def watchdog_parent(pid, creation):
    """Bind an explicitly invoked watchdog subprocess relationship, not an ACL.

The reviewed parent wrapper owns termination authority and the bounded timer.
This prevents accidental direct CLI use; it is not same-user authentication.
"""
    require(integer(pid, 1, 2**32 - 1) and pid == os.getppid()
            and isinstance(creation, str) and re.fullmatch(r"[0-9a-f]{16}", creation),
            "Running speed requires the direct verified watchdog parent")
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.GetProcessTimes.argtypes = [W.HANDLE, C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME)]
    kernel.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
    kernel.WaitForSingleObject.restype = W.DWORD
    kernel.CloseHandle.argtypes = [W.HANDLE]
    handle = kernel.OpenProcess(0x1000 | 0x00100000, False, pid)  # QUERY_LIMITED_INFORMATION | SYNCHRONIZE
    require(handle, "Cannot hold the watchdog process identity")
    try:
        created, exited, cpu_kernel, cpu_user = W.FILETIME(), W.FILETIME(), W.FILETIME(), W.FILETIME()
        require(kernel.GetProcessTimes(handle, C.byref(created), C.byref(exited), C.byref(cpu_kernel), C.byref(cpu_user)),
                "Cannot verify watchdog creation time")
        require(f"{(created.dwHighDateTime << 32) | created.dwLowDateTime:016x}" == creation, "Watchdog PID was reused")
        def healthy():
            require(kernel.WaitForSingleObject(handle, 0) == 0x102, "Watchdog exited; no running request may be published")
        healthy()
        yield healthy
    finally:
        kernel.CloseHandle(handle)


def session_path(output, pid, creation):
    require(integer(pid, 1, 2**32 - 1) and isinstance(creation, str) and re.fullmatch(r"[0-9a-f]{16}", creation), "Invalid session identity")
    result = Path(output) / f"session-{pid}-{creation}"
    _private_root(result)
    return result


def read_session_metadata(session, pid, creation):
    value = decode_json(read_bounded(Path(session) / "session.json", 4096).decode("utf-8"))
    require(isinstance(value, dict) and set(value) == {"schema_version", "purpose", "pid", "process_creation_filetime", "window_thread",
            "game_sha256", "world_generation_verified", "runtime_verified"}, "Unexpected native session metadata")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1 and value["purpose"] == PURPOSE
            and type(value["pid"]) is int and value["pid"] == pid and value["process_creation_filetime"] == creation
            and integer(value["window_thread"], 1, 2**32 - 1) and value["game_sha256"] == LOCAL_SHA256
            and value["world_generation_verified"] is False and value["runtime_verified"] is False,
            "Native metadata has a different process/build or overclaims production verification")
    require(decode_json(read_bounded(Path(session) / "install.claim", 4096).decode("utf-8")) == value,
            "Durable installation claim differs from session identity")
    return value


def read_evidence(session, metadata):
    """Stream a fixed-length bounded snapshot, retain only phase proofs and ACKs."""
    from tools.verify_diplomacy_lifecycle_v15 import Session, PREVIEW_EVENTS, COMMAND_EVENTS
    from tools.verify_diplomacy_preview_v15 import PreviewSession
    from tools.verify_diplomacy_command_v15 import CommandSession
    from tools.verify_diplomacy_owned_peace_v15 import OwnedPeaceSession, OWNED_EVENTS
    from tools.verify_diplomacy_acceptance_v15 import AcceptanceSession
    path = Path(session) / "research-1375.jsonl"
    _no_links(path)
    size = path.stat().st_size
    require(0 < size <= MAX_LOG, "Research log is empty or exceeds its bounded snapshot limit")
    validators, proofs, complete = {}, {}, set()
    owned = OwnedPeaceSession(metadata)
    acceptance = AcceptanceSession(metadata)
    phase_started = set()
    latest, installed, last_sequence, pending, requests = None, False, 0, None, {}
    previous_frame, previous_uptime, previous_date, world = 0, 0, 0, None
    digest = hashlib.sha256()
    phase_events = PREVIEW_EVENTS | COMMAND_EVENTS | {"pair_selftest_begin", "pair_lifecycle", "pair_lifecycle_complete", "pair_selftest_complete"}
    lease = None
    input_wait = None
    last_input_uptime = 0
    with path.open("rb") as stream:
        remaining, line_number = size, 0
        while remaining:
            raw = stream.readline(min(remaining, MAX_LINE + 1))
            require(raw and raw.endswith(b"\n") and len(raw) <= MAX_LINE, "Truncated or oversized research log line")
            remaining -= len(raw)
            digest.update(raw)
            line_number += 1
            event = decode_json(raw.decode("utf-8"))
            require(isinstance(event, dict) and isinstance(event.get("event"), str), "Malformed research event")
            name = event["event"]
            if name.startswith("lab_") or name == "research_hook_installed":
                require(type(event.get("pid")) is int and event["pid"] == metadata["pid"]
                        and event.get("process_creation_filetime") == metadata["process_creation_filetime"],
                        "Native event lacks its exact process identity")
            if "pid" in event:
                require(type(event["pid"]) is int and event["pid"] == metadata["pid"], "Foreign PID in session log")
            if "process_creation_filetime" in event:
                require(event["process_creation_filetime"] == metadata["process_creation_filetime"], "Foreign creation time in session log")
            if name == "research_hook_installed":
                require(not installed and not validators and event.get("window_thread") == metadata["window_thread"], "Duplicate/foreign hook boundary")
                require(event.get("owned_peace_automatic") is False, "Owned-peace phase must have an explicit marker")
                installed = True
                validators = {"lifecycle": Session(event, line_number, metadata["pid"]),
                              "preview": PreviewSession(event, line_number, metadata["pid"]),
                              "command": CommandSession(event, line_number, metadata["pid"])}
                continue
            if not installed and name == "research_hook_refused":
                require(event.get("result") == 21 and event.get("prefix_unchanged") is True
                        and event.get("resume_failures") == 0 and event.get("retrying") is True
                        and event.get("submitted") is False, "Installation refusal was not a safely retried guard failure")
                continue
            require(installed, "Research events precede a verified installation boundary")
            if name in ("lab_session_frozen", "lab_host_exception"):
                raise LabError("Native lab session is frozen; no retry: " + str(event.get("reason", name)))
            if name == "research_frame":
                require(event.get("thread") == metadata["window_thread"] and event.get("thread_changed") is False
                        and event.get("world_changed") is False and event.get("session_frozen") is False, "Frame thread/world/session fault")
                require(event.get("fixture_profile_sha256") == FIXTURE_PROFILE_SHA256, "Frame has a different fixture profile")
                require(integer(event.get("frames"), previous_frame + 1, 2**31 - 1)
                        and integer(event.get("uptime_ms"), max(1, previous_uptime, last_input_uptime), 2**64 - 1), "Frame sequence/time regressed")
                require(type(event.get("pid")) is int and event["pid"] == metadata["pid"]
                        and event.get("process_creation_filetime") == metadata["process_creation_filetime"], "Frame lacks process identity")
                require(event.get("last_sequence") == last_sequence, "Frame sequence differs from observed claimed requests")
                if event.get("world_ready") is True:
                    identity = (event.get("world_cookie"), event.get("player_handle"))
                    require(world is None or world == identity, "Frame world/player identity changed")
                    require(integer(event.get("raw_date"), max(1, previous_date), 2**31 - 1), "Frame date regressed")
                    world, previous_date = identity, event["raw_date"]
                previous_frame, previous_uptime = event["frames"], event["uptime_ms"]
                acceptance.frame(event)
                owned.frame(event,line_number)
                latest = event
            if name in OWNED_EVENTS:
                require(input_wait is None and last_sequence == 0 and not any(p in complete for p in ("preview","command")),
                    "Owned-peace invocation overlaps an input wait or later activity")
                require("lifecycle" in proofs, "Owned-peace requires proved lifecycle and following health")
                require(read_bounded(Path(session)/PHASES["owned_peace"][1],MAX_RECORD)==phase_wire("owned_peace",metadata),
                    "Owned-peace lacks its exact durable PID/creation marker claim")
                owned.accept(event,line_number,lifecycle_proved=True)
                phase_started.add("owned_peace")
                if name == "owned_peace_selftest_complete": complete.add("owned_peace")
                continue
            phase_begins={"pair_selftest_begin":"lifecycle","pair_preview_begin":"preview","pair_command_begin":"command"}
            if name in phase_begins:
                phase=phase_begins[name]
                order=tuple(PHASES)
                require(phase not in phase_started and all(p in proofs for p in order[:order.index(phase)]),
                    "Phase began twice or before all preceding four-stage proofs")
                require(read_bounded(Path(session)/PHASES[phase][1],MAX_RECORD)==phase_wire(phase,metadata),
                    "Phase began without its exact durable marker claim")
                phase_started.add(phase)
            if name == "research_frame" and "owned_peace" in complete and "owned_peace" not in proofs:
                proofs["owned_peace"]=owned.finish()
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
                              "parse", "pid", "creation", "sequence", "ttl_expired", "ttl_range", "acceptance_window", "claim_open", "claim_write",
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

            if name.startswith("lab_"):
                require(input_wait is None, "Mailbox operation preceded the end of its unclaimed input wait")
                require("command" in proofs and proofs["command"]["passed"], "Mailbox activity preceded complete preflight proof")
                sequence = event.get("sequence")
                if name == "lab_request_claimed":
                    require(pending is None and integer(sequence, last_sequence + 1, last_sequence + 1)
                            and event.get("durable_claim") is True and event.get("retry_allowed") is False, "Duplicate/out-of-order native claim")
                    record = {key: event[key] for key in ("pid", "sequence", "expires", "operation", "mode", "action", "actor", "target", "speed", "bound_action", "bound_target", "bound_submit_sequence")}
                    record["creation"] = metadata["process_creation_filetime"]
                    wire = encode_request(record)
                    require(read_bounded(Path(session) / f"{sequence:020}.claim", MAX_RECORD) == wire, "Native claim bytes differ from event")
                    if record["operation"] == "fixture":
                        require(read_bounded(Path(session)/f"{sequence:020}.fixture-profile",512)==fixture_proof_wire(metadata,sequence),
                                "Fixture claim lacks its exact permanent profile proof")
                    acceptance.claim(record, requests, event.get("claimed_uptime_ms"))
                    pending = {"request": record, "records": [], "complete": None}
                    requests[sequence] = pending
                    require(len(requests) <= 4096, "Session request budget exceeded")
                    last_sequence = sequence
                elif name == "lab_acceptance_pending":
                    acceptance.pending_grant(event)
                elif name == "lab_native_record":
                    owner = pending
                    if event.get("lease_pause") is True:
                        require(lease is not None and sequence == lease["sequence"] and pending is None, "Unbound lease-pause audit record")
                        owner = lease
                    require(owner is not None and sequence == last_sequence and isinstance(event.get("record"), dict), "Unbound native audit record")
                    require(len(owner["records"]) < 8, "Native record budget exceeded")
                    core = event["record"]
                    require(type(core.get("thread_id")) is int and core["thread_id"] == metadata["window_thread"]
                            and core.get("retry_allowed") is False, "Core record has a foreign thread or permits retry")
                    pair = pending is not None and pending["request"]["operation"] == "pair"
                    fixture = pending is not None and pending["request"]["operation"] == "fixture"
                    control_accept = pending is not None and pending["request"]["operation"] == "accept"
                    if pair:
                        request = pending["request"]
                        require(core.get("event") in ("pair_engine_begin", "pair_engine_dispatch_intent", "pair_engine_complete")
                                and all(core.get(key) == request[key] for key in ("pid", "actor", "target"))
                                and core.get("process_creation_filetime") == metadata["process_creation_filetime"]
                                and core.get("action_id") == request["action"] and core.get("applied_verified") is False
                                and core.get("world") == latest["world_cookie"]
                                and core.get("raw_date") == latest["raw_date"], "Pair core record differs from request/world")
                        subsidy = request["action"] in ("give_subsidies", "cancel_subsidies")
                        require(type(core.get("fixed_subsidy_amount_milli")) is int and core["fixed_subsidy_amount_milli"] == (1000 if subsidy else 0)
                                and type(core.get("fixed_subsidy_duration_years")) is int and core["fixed_subsidy_duration_years"] == (10 if subsidy else 0),
                                "Pair core fixed research parameters differ")
                        expected_extra = {
                            "fixed_gift_amount_milli": 25000 if request["action"] == "send_gift" else 0,
                            "fixed_transfer_fraction_milli": 500 if request["action"] in ("request_trade_power", "cancel_trade_power_transfer") else 0,
                            "fixed_insult_index": -1 if request["action"] == "insult" else 0,
                        }
                        require(all(type(core.get(k)) is int and core[k] == v for k, v in expected_extra.items()),
                                "Pair core fixed gift/trade/insult parameters differ")
                    elif control_accept:
                        acceptance.core(core)
                    elif fixture:
                        requested_event = "llmt.1" if pending["request"]["action"] == "fixture_on" else "llmt.2"
                        require(core.get("event") in ("test_fixture_begin","test_fixture_complete")
                                and core.get("fixture_event") == requested_event and core.get("target") == "FRA"
                                and core.get("fixture_profile_sha256") == FIXTURE_PROFILE_SHA256
                                and core.get("fixture_effect_verified") is False and core.get("diplomacy_submitted") is False
                                and core.get("before_date") == latest["raw_date"], "Fixture audit differs from fixed request/profile/world")
                    else:
                        wanted_speed = 0 if owner is lease else pending["request"]["speed"]
                        require(core.get("event") in ("test_speed_begin", "test_speed_complete")
                                and core.get("requested_speed") == wanted_speed and core.get("diplomacy_submitted") is False,
                                "Controls record differs from requested speed")
                    expected_begin = "pair_engine_begin" if pair else ("test_acceptance_begin" if control_accept else ("test_fixture_begin" if fixture else "test_speed_begin"))
                    require(owner["records"] or core.get("event") == expected_begin, "Core evidence has no begin boundary")
                    require(not owner["records"] or owner["records"][-1].get("event") not in ("pair_engine_complete", "test_speed_complete", "test_fixture_complete", "test_acceptance_complete"),
                            "Core evidence continues after completion")
                    owner["records"].append(core)
                elif name == "lab_lease_armed":
                    require(pending is not None and lease is None and sequence == last_sequence
                            and pending["request"]["operation"] == "speed" and pending["request"]["speed"] > 0
                            and event.get("automatic_pause") is True and event.get("maximum_raw_date_delta") == 48
                            and event.get("reliable_generation_verified") is False, "Unexpected running lease")
                    lease = {"sequence": sequence, "records": [], "armed": event, "complete": None}
                elif name == "lab_request_complete":
                    require(pending is not None and sequence == last_sequence and event.get("operation") == pending["request"]["operation"]
                            and event.get("session_frozen") is False and event.get("retry_allowed") is False
                            and event.get("applied_verified") is False, "Unbound or uncertain native completion")
                    pending["complete"] = event
                    require(pending["records"] and pending["records"][-1].get("event") in ("pair_engine_complete", "test_speed_complete", "test_fixture_complete", "test_acceptance_complete"),
                            "Completion lacks the core's final audit record")
                    if pending["request"]["operation"] == "pair":
                        require(event.get("action") == pending["request"]["action"] and event.get("ownership_uncertain") is False,
                                "Pair completion differs from the original request or has unknown ownership")
                        fields = ("status", "reason", "submit_entered", "submit_returned", "ownership_uncertain")
                    elif pending["request"]["operation"] == "accept":
                        require(event.get("action") == pending["request"]["action"], "Acceptance completion differs from fixed request")
                        fields = ("reason", "native_invoked", "callback_returned", "callback_success", "result_destroyed", "arguments_unchanged")
                    elif pending["request"]["operation"] == "fixture":
                        require(event.get("action") == pending["request"]["action"] and event.get("fixture_effect_verified") is False,
                                "Fixture completion differs from request or overclaims effects")
                        fields = ("reason","native_invoked","callback_returned","callback_success","result_destroyed",
                                  "arguments_unchanged","callback_flag_restored","world_identity_unchanged")
                        core = pending["records"][-1]
                        require(core.get("event") == "test_fixture_complete" and type(core.get("reason")) is int and core["reason"] == 0
                                and all(core.get(key) is True for key in fields[1:])
                                and type(core.get("exception_code")) is int and core["exception_code"] == 0
                                and core.get("after_date") == core.get("before_date"), "Fixture native callback completion is uncertain")
                    else:
                        require(event.get("speed") == pending["request"]["speed"], "Speed completion differs from request")
                        fields = ("reason", "write_entered", "callback_returned", "readback_matches")
                    core = pending["records"][-1]
                    require(all(key in event and key in core and type(event[key]) is type(core[key]) and event[key] == core[key] for key in fields)
                            and core.get("freeze_session") is False, "Host completion conflicts with its core record")
                    acceptance.complete(event, core)
                    pending = None
                elif name == "lab_lease_complete":
                    require(lease is not None and pending is None and sequence == lease["sequence"]
                            and event.get("session_frozen") is False and event.get("readback_matches") is True
                            and event.get("paused_readback") is True and event.get("retry_allowed") is False,
                            "Automatic pause was not verified")
                    require(lease["records"] and lease["records"][-1].get("event") == "test_speed_complete", "Lease has no controls audit completion")
                    core = lease["records"][-1]
                    require(core.get("after_paused") is True and core.get("readback_matches") is True
                            and core.get("freeze_session") is False and core.get("exception_code") == 0
                            and all(key in core and core[key] == event.get(key) for key in ("reason", "write_entered", "callback_returned")),
                            "Automatic pause completion conflicts with its controls record")
                    claim = decode_json(read_bounded(Path(session) / f"{sequence:020}.lease-pause.claim", 4096).decode("utf-8"))
                    require(claim.get("purpose") == "bounded_running_lease_pause" and claim.get("pid") == metadata["pid"]
                            and claim.get("process_creation_filetime") == metadata["process_creation_filetime"]
                            and claim.get("origin_sequence") == sequence and claim.get("speed") == 0
                            and claim.get("deadline_uptime_ms") == lease["armed"].get("deadline_uptime_ms")
                            and claim.get("maximum_raw_date_delta") == 48
                            and claim.get("retry_allowed") is False, "Automatic pause claim identity differs")
                    requests[sequence]["lease_complete"] = event
                    lease = None
                else:
                    raise LabError("Unknown lab event: " + name)
                continue
            require(input_wait is None or name == "research_frame", "Phase invocation preceded the end of its unclaimed input wait")
            require(name == "research_frame" or name in phase_events, "Unknown non-mailbox event in research log: " + name)
            require(not ("command" in proofs and name in phase_events), "Preflight phases cannot be repeated after completion")
            for phase, validator in validators.items():
                if phase not in proofs:
                    validator.accept(event, line_number)
                    errors = (validator.prior.error_count + validator.command.error_count) if phase == "command" else validator.error_count
                    require(errors == 0, "Failed or malformed partial " + phase + " preflight; no retry")
            for phase, completion in (("lifecycle", "pair_selftest_complete"), ("preview", "pair_preview_complete"), ("command", "pair_command_complete")):
                if name == completion:
                    complete.add(phase)
                if phase in complete and phase not in proofs and name == "research_frame":
                    proof = validators[phase].finish()
                    require(proof["passed"], f"{phase} prefix failed its detailed native lifecycle validator: {proof.get('errors')}")
                    require(read_bounded(Path(session) / PHASES[phase][1], MAX_RECORD) == phase_wire(phase, metadata),
                            "Detailed phase proof lacks its exact durable marker claim")
                    proofs[phase] = proof
            require(len(requests) <= 4096, "Session request budget exceeded")
    require(installed and latest is not None, "Session has no installed healthy frame")
    phase_attempted, phase_attempt_sources = {}, {}
    for phase, (_,claim,_) in PHASES.items():
        paths = (Path(session)/claim, Path(session)/(claim+".host-intent"))
        for path in paths: _no_links(path)
        source = {"native_started": phase in phase_started, "native_claim": paths[0].exists(), "host_intent": paths[1].exists()}
        phase_attempt_sources[phase] = source
        phase_attempted[phase] = any(source.values())
    return {"latest_frame": latest, "phases": {name: name in proofs for name in PHASES}, "phase_proofs": proofs,
            "phase_attempted": phase_attempted, "phase_attempt_sources": phase_attempt_sources,
            "last_sequence": last_sequence, "pending": pending is not None, "lease_pending": lease is not None, "requests": requests,
            "input_wait_pending": input_wait is not None, "acceptance_window": acceptance.snapshot(),
            "log_sha256": digest.hexdigest(), "log_bytes": size, "read_kind": "fixed_size_read_only_snapshot"}


def check_ready(evidence, live, now, *, phase=None, operation=None):
    require(isinstance(evidence.get("phases"),dict) and set(evidence["phases"])==set(PHASES)
        and all(type(v) is bool for v in evidence["phases"].values()), "Missing exact four-phase diagnostics")
    frame = evidence["latest_frame"]
    require(integer(frame.get("acceptance_flag"), 0, 1) and type(live.get("acceptance_flag")) is int
            and live["acceptance_flag"] == frame["acceptance_flag"], "Independent/native acceptance flag differs")
    require(evidence.get("acceptance_window",{}).get("state") not in ("pending_on","pending_submit","pending_off","awaiting_health","unknown"),
            "Acceptance transition or required reset health is unresolved")
    if phase:
        require(evidence["acceptance_window"]["state"] == "closed" and frame["acceptance_flag"] == 0,
                "Preflight requires closed flag0")
    require(type(frame.get("owned_peace_tested")) is bool and type(frame.get("owned_peace_passed")) is bool,
        "Missing owned-peace frame diagnostics")
    require(integer(now, 1, 2**64 - 1) and 0 <= now - frame["uptime_ms"] <= FRAME_MAX_AGE, "Native frame heartbeat is stale")
    require(frame.get("world_ready") is True and frame.get("frames", 0) >= 100, "World/frame preflight is not ready")
    require(frame.get("world_cookie") == live["world_cookie"] and frame.get("player_handle") == live["player_handle"]
            and live["raw_date"] >= frame.get("raw_date", 0), "Independent live world differs from frame evidence")
    require(not evidence.get("input_wait_pending"), "A published input is awaiting its bounded pre-handle sharing wait")
    require(not evidence["pending"], "Prior native request is incomplete; never automatically resubmit")
    require(not evidence.get("lease_pending") and frame.get("lease_active") is not True, "Running lease must finish its automatic pause first")
    if operation != "speed":
        require(frame.get("paused") is True and live["raw_date"] == frame["raw_date"], "Pair/preflight operations require a stable paused world")
    if phase:
        order = tuple(PHASES)
        require(phase in PHASES, "Unknown phase")
        index = order.index(phase)
        require(isinstance(evidence.get("phase_attempted"),dict) and set(evidence["phase_attempted"])==set(PHASES)
            and evidence["phase_attempted"][phase] is False, "Phase already claimed, intended or started; no retry")
        require(not evidence["phases"][phase] and all(evidence["phases"][name] for name in order[:index]), "Phase was already completed or prerequisites are missing")
    else:
        require(all(evidence["phases"].values()) and frame.get("mailbox_ready") is True, "Four detailed preflight phases must pass before mailbox use")
        require(all(frame.get(name + "_passed") is True for name in PHASES), "Frame contradicts detailed preflight evidence")


def prepare_request(metadata, evidence, *, sequence, operation, mode, action, actor, target, speed, ttl_ms, now, bound_action="none", bound_target="none", bound_submit_sequence=0):
    """Validate the same request in plan and publication modes; no file writes."""
    require(integer(sequence, 1, MAX_SEQUENCE) and sequence == evidence["last_sequence"] + 1,
            "Sequence must explicitly match the next native sequence")
    require(integer(ttl_ms, 1, MAX_TTL), "TTL must be 1..60000 ms")
    require(operation != "speed" or speed == 0 or evidence["latest_frame"].get("running_speed_enabled") is True,
            "Running speed is disabled until its bounded automatic-pause lease is reviewed")
    require(operation != "pair" or mode != "submit" or actor == "FRA", "Only current player FRA may submit in this research profile")
    require(operation != "fixture" or FIXTURE_EVENT_CONTRACT_READY, "v15 native fixture audit contract is not finalized")
    record = {"pid": metadata["pid"], "creation": metadata["process_creation_filetime"], "sequence": sequence,
              "expires": now + ttl_ms, "operation": operation, "mode": mode, "action": action,
              "actor": actor, "target": target, "speed": speed, "bound_action": bound_action,
              "bound_target": bound_target, "bound_submit_sequence": bound_submit_sequence}
    raw = encode_request(record)
    from tools.verify_diplomacy_acceptance_v15 import check_publication
    check_publication(record, evidence, now)
    return record, raw


@contextmanager
def _hold_new_phase_intent(path, raw):
    """Own one newly created intent until publication; never reopen an old one.

    Windows sharing permits readers (including read_evidence), but no other
    writer or delete/rename handle. A failed invocation permanently leaves the
    file behind. This is a private publisher helper, not an override parameter.
    """
    require(os.name == "nt", "Held phase intent requires Windows file identity")
    path = Path(path)
    _no_links(path)
    require(type(raw) is bytes and 0 < len(raw) <= 4096, "Invalid bounded phase intent")
    kernel = C.WinDLL("kernel32", use_last_error=True)
    class FileInformation(C.Structure):
        _fields_ = [("attributes", W.DWORD), ("creation", W.FILETIME),
            ("access", W.FILETIME), ("write", W.FILETIME), ("volume", W.DWORD),
            ("size_high", W.DWORD), ("size_low", W.DWORD), ("links", W.DWORD),
            ("index_high", W.DWORD), ("index_low", W.DWORD)]
    kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.CloseHandle.restype = W.BOOL
    kernel.WriteFile.argtypes = [W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p]
    kernel.WriteFile.restype = W.BOOL
    kernel.ReadFile.argtypes = kernel.WriteFile.argtypes
    kernel.ReadFile.restype = W.BOOL
    kernel.FlushFileBuffers.argtypes = [W.HANDLE]
    kernel.FlushFileBuffers.restype = W.BOOL
    kernel.SetFilePointerEx.argtypes = [W.HANDLE, C.c_longlong, C.POINTER(C.c_longlong), W.DWORD]
    kernel.SetFilePointerEx.restype = W.BOOL
    kernel.GetFileInformationByHandle.argtypes = [W.HANDLE, C.POINTER(FileInformation)]
    kernel.GetFileInformationByHandle.restype = W.BOOL
    invalid = C.c_void_p(-1).value
    # CREATE_NEW, GENERIC_READ|WRITE, FILE_SHARE_READ only. A preexisting file,
    # even byte-identical, can never become this invocation's owned intent.
    handle = kernel.CreateFileW(str(path), 0xc0000000, 1, None, 1, 0x80000080, None)
    if handle == invalid:
        raise OSError(C.get_last_error(), "Exclusive held phase intent creation failed")
    def file_identity(h):
        info = FileInformation()
        require(bool(kernel.GetFileInformationByHandle(h, C.byref(info))), "Cannot inspect held intent file identity")
        require(info.links == 1 and not info.attributes & (0x400 | 0x10), "Intent is linked, reparse, or directory")
        return (info.volume, info.index_high, info.index_low,
                info.creation.dwHighDateTime, info.creation.dwLowDateTime,
                info.size_high, info.size_low)
    try:
        written = W.DWORD()
        buffer = C.create_string_buffer(raw)
        require(bool(kernel.WriteFile(handle, buffer, len(raw), C.byref(written), None))
                and written.value == len(raw), "Short/failed held phase intent write")
        require(bool(kernel.FlushFileBuffers(handle)), "Phase intent flush failed")
        pinned = file_identity(handle)
        require(pinned[-2:] == (0, len(raw)), "Held intent size differs")
        def validate_owned():
            _no_links(path)
            require(file_identity(handle) == pinned, "Held intent identity changed")
            # OPEN_EXISTING reader must share this existing writer's access,
            # while the original handle still prohibits writes and deletion.
            current = kernel.CreateFileW(str(path), 0x80000000, 3, None, 3, 0x80, None)
            if current == invalid:
                raise OSError(C.get_last_error(), "Cannot bind intent path to held file")
            try:
                require(file_identity(current) == pinned, "Intent path no longer names owned file")
            finally:
                kernel.CloseHandle(current)
            require(bool(kernel.SetFilePointerEx(handle, 0, None, 0)), "Cannot seek held intent")
            contents, count = C.create_string_buffer(len(raw) + 1), W.DWORD()
            require(bool(kernel.ReadFile(handle, contents, len(raw) + 1, C.byref(count), None))
                    and count.value == len(raw) and contents.raw[:count.value] == raw,
                    "Owned intent contents differ")
        validate_owned()
        yield validate_owned
    finally:
        kernel.CloseHandle(handle)


def _current_owned_phase_evidence(evidence, phase, validate_owned, final, claimed):
    """Internal, invocation-local projection; public readiness stays strict."""
    validate_owned()
    _no_links(final)
    _no_links(claimed)
    require(not final.exists() and not claimed.exists(), "Native request/claim appeared during phase publication")
    sources = evidence.get("phase_attempt_sources")
    require(type(sources) is dict and set(sources) == set(PHASES), "Missing exact phase attempt diagnostics")
    source = sources[phase]
    require(type(source) is dict and set(source) == {"native_started", "native_claim", "host_intent"}
            and source["native_started"] is False and source["native_claim"] is False and source["host_intent"] is True,
            "Phase attempt is not solely this invocation's held intent")
    require(type(evidence.get("phase_attempted")) is dict and set(evidence["phase_attempted"]) == set(PHASES)
            and evidence["phase_attempted"][phase] is True, "Owned phase intent was not observed by fresh evidence")
    return dict(evidence, phase_attempted=dict(evidence["phase_attempted"], **{phase: False}))


def publish_research(session, metadata, manifest_sha, evidence, live, *, sequence=None, operation=None,
                     mode="legality_only", action=None, actor="FRA", target="ENG", speed=0, phase=None, ttl_ms=5000,
                     clock=uptime_ms, recheck=None, watchdog_verified=False, fixture_check=None,
                     bound_action="none", bound_target="none", bound_submit_sequence=0):
    """One explicit publication. Durable host intent precedes the final file."""
    session = Path(session)
    _private_root(session)
    check_ready(evidence, live, clock(), phase=phase, operation=operation)
    require(not list(session.glob("*.request")), "A request/phase marker is already pending")
    require(operation != "fixture" or callable(fixture_check), "Fixture publication requires independent installed-file/startup verification")
    if phase:
        filename, claim, _ = PHASES[phase]
        raw = phase_wire(phase, metadata)
        final, claimed = session / filename, session / claim
        intent_path = session / (claim + ".host-intent")
    else:
        require(operation != "speed" or speed == 0 or watchdog_verified is True,
                "Running speed requires an active exact-process external watchdog")
        record, raw = prepare_request(metadata, evidence, sequence=sequence, operation=operation, mode=mode,
                                      action=action, actor=actor, target=target, speed=speed, ttl_ms=ttl_ms, now=clock(),
                                      bound_action=bound_action, bound_target=bound_target, bound_submit_sequence=bound_submit_sequence)
        final, claimed = session / f"{sequence:020}.request", session / f"{sequence:020}.claim"
        intent_path = session / f"{sequence:020}.host-intent"
    _no_links(final)
    _no_links(claimed)
    require(not final.exists() and not claimed.exists(), "Request/claim already exists; no retry or replacement")
    intent = {"protocol": PROTOCOL, "purpose": PURPOSE, "pid": metadata["pid"], "creation": metadata["process_creation_filetime"],
              "manifest_sha256": manifest_sha, "request_sha256": hashlib.sha256(raw).hexdigest(),
              "body_ascii": raw.decode("ascii"), "automatic_retry": False}
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
            from tools.verify_diplomacy_acceptance_v15 import check_publication
            check_publication(record, current_evidence, clock())
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

    return {"research_only": True, "protocol": PROTOCOL, "status": "published", "path": str(final),
            "request_sha256": intent["request_sha256"], "pid": metadata["pid"], "creation": metadata["process_creation_filetime"],
            "sequence": sequence, "phase": phase, "native_dispatch_verified": False, "applied_verified": False,
            "automatic_retry": False, "production_backend_registered": False}
