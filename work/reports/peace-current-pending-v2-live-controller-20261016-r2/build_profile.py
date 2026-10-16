"""Single source-only builder. No actual configuration, PE, process, or CLI access."""
from pathlib import Path
import ast, ctypes, hashlib, json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT / "work/reports/peace-current-pending-v2-live-controller-20261016-r1"
AUTH = "work/reports/peace-current-pending-v2-text-config-source-authorization-20261016-r1/authorization.json"
AUTH_PIN = {"bytes": 6172, "sha256": "58e3ab5f51a73c47e0b1119f9554712c91e34f5289ca228e339cb0f2c9e33d50"}
READS = []
MANUAL_RESERVED = 200000  # Prior explicit small-source reads plus bounded PowerShell tail; not measured OS I/O.


def memory():
    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [(n, ctypes.c_size_t) for n in
          ("peakws", "ws", "peakpaged", "paged", "peaknonpaged", "nonpaged", "pagefile", "peakpagefile", "private")]
    p = PMC(); p.cb = ctypes.sizeof(p)
    get = ctypes.windll.kernel32.GetCurrentProcess; get.restype = ctypes.c_void_p
    q = ctypes.windll.psapi.GetProcessMemoryInfo; q.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    assert q(get(), ctypes.byref(p), p.cb)
    assert p.private <= 805306368 and p.peakpagefile <= 1073741824
    return {"private": p.private, "peak_commit": p.peakpagefile}


def pin(raw): return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def read(path, expected=None):
    assert path.name != "local.env" and path.name.casefold() != "eu4.exe"
    size = path.stat().st_size; assert size <= 4194304
    assert MANUAL_RESERVED + sum(x["bytes"] for x in READS) + size <= 33554432
    raw = path.read_bytes(); p = pin(raw)
    READS.append({"path": path.relative_to(ROOT).as_posix(), **p})
    if expected is not None: assert p == expected
    memory()
    return raw


def write(name, data):
    raw = data.encode("utf-8") if isinstance(data, str) else (json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("ascii")
    with (HERE / name).open("xb") as f: f.write(raw)
    return pin(raw)


def replace(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def definitions(raw):
    return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(raw).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}


def main():
    write("source-build-claim.json", {"source_only": True, "one_build": True, "actual": False})
    auth_raw = read(ROOT / AUTH, AUTH_PIN); auth = json.loads(auth_raw)
    old_manifest = json.loads(read(OLD / "source-manifest.json", auth["fixed_inputs"][(OLD / "source-manifest.json").relative_to(ROOT).as_posix()]))
    inputs = dict(old_manifest["source_pins"])
    inputs.update(auth["fixed_inputs"]); inputs[AUTH] = AUTH_PIN
    data = {n: read(ROOT / n, p) for n, p in inputs.items()}
    def old(name): return data[(OLD / name).relative_to(ROOT).as_posix()].decode("utf-8")
    child = old("child.py")
    old_line = "        METER=game_meter_class(donor,contract)(paths,state['budgets'])"
    new_line = """        adapter_name=(HERE/'text_config_adapter.py').relative_to(ROOT).as_posix()
        adapter=types.ModuleType('_peace_v2_exact_text_config');adapter.__file__=str(HERE/'text_config_adapter.py')
        exec(compile(state['data'][adapter_name],adapter.__file__,'exec'),adapter.__dict__)
        meter_type=adapter.meter_class(game_meter_class(donor,contract),contract,state['auth']['local_configuration_pin'],OPEN)
        METER=meter_type(paths,state['budgets'])"""
    child = replace(child, old_line, new_line)
    child = replace(child, "'game_opens':[] if METER is None else METER.game_opens,", "'text_config':None if METER is None else METER.text_config.summary(),\n            'game_opens':[] if METER is None else METER.game_opens,")
    child = child.replace("EU4-PEACE-V2-CURRENT-STATUS-CHILD-IO/1", "EU4-PEACE-V2-CURRENT-STATUS-CHILD-IO/2")
    assert definitions(child)["game_meter_class"] == definitions(old("child.py"))["game_meter_class"]
    for name in ("require", "pin", "decode", "read", "save", "bootstrap"):
        assert definitions(child)[name] == definitions(old("child.py"))[name]
    write("child.py", child)

    contract = old("runtime_contract.py")
    contract = replace(contract, "BUILD = 'work/reports/peace-current-pending-v2-controller-build-authorization-20261016-r1/authorization.json'", "BUILD = " + repr(AUTH))
    contract = replace(contract, "BUILD_PIN = {'bytes':5494,'sha256':'92df2dd3bfba2b8d364889d57d4794ed1dea9fa86dde1ebfbdda6f79e5351a06'}", "BUILD_PIN = " + repr(AUTH_PIN))
    contract = replace(contract, "require(build['controller_build_only'] is True and build['live_authorized'] is False,'Build grant is source only')", "require(build['source_build_only'] is True and build['runtime_authorized'] is False,'Build grant is source only')")
    contract = contract.replace("EU4-PEACE-V2-CURRENT-STATUS-ONCE/1", "EU4-PEACE-V2-CURRENT-STATUS-ONCE/2")
    contract = contract.replace("EU4-PEACE-V2-CONTROLLER-SOURCE/1", "EU4-PEACE-V2-CONTROLLER-SOURCE/2")
    contract = replace(contract, "    require(auth.get('operation')=='status','Only current status')", """    require(auth.get('operation')=='status','Only current status')
    config=auth.get('local_configuration_pin')
    require(type(config)is dict and set(config)=={'path','bytes','sha256'},'Exact new configuration triple')
    require(config['path']=='local.env' and type(config['bytes'])is int and 0<=config['bytes']<=65536,'Fixed bounded configuration path')
    require(type(config['sha256'])is str and re.fullmatch('[0-9a-f]{64}',config['sha256']),'Root configuration raw SHA')""")
    contract = replace(contract, "[('subject_controller_pin','controller.py'),('subject_child_pin','child.py')]", "[('subject_controller_pin','controller.py'),('subject_child_pin','child.py'),('subject_adapter_pin','text_config_adapter.py')]")
    contract = replace(contract, "('subject_source_manifest','subject_controller_pin','subject_child_pin'):", "('subject_source_manifest','subject_controller_pin','subject_child_pin','subject_adapter_pin'):")
    write("runtime_contract.py", contract)

    controller = old("controller.py")
    function = """
def validate_config_io(value,expected,observed=False):
    require(type(value)is dict and value.get('schema')=='EU4-EXACT-CONFIG-SNAPSHOT/1','New configuration ledger required')
    require(value['expected_pin']=={k:expected[k] for k in ('bytes','sha256')},'Configuration exact grant pin')
    require(value['maximum_bytes']==65536 and value['maximum_snapshots']==16,'Configuration bounds')
    require(type(value['opened_snapshots'])is int and 0<=value['opened_snapshots']<=16,'Configuration snapshot limit')
    require(value['physical_category']=='ordinary' and value['virtual_reads_add_physical_bytes']is False,'Configuration physical accounting')
    require(value['configuration_values_logged']is False and value['real_path_override_argument']is False,'Configuration redaction/path contract')
    if observed:
        require(1<=value['opened_snapshots']<=16 and value['events'],'Selected status requires pinned configuration snapshot')
        require(all(e.get('accepted')is True and e.get('binary_closed')is True and e.get('virtual_closed')is True and e.get('virtual_normal_exit')is True and e.get('raw_pin')==value['expected_pin'] and e.get('error')is None for e in value['events']),'Configuration accepted/closed snapshots only')

"""
    controller = replace(controller, "def main():\n", function + "def main():\n")
    controller = replace(controller, "        require(child_io['exit_code']==job['exit_code'],'Child receipt exit differs')", "        require(child_io['exit_code']==job['exit_code'],'Child receipt exit differs')\n        validate_config_io(child_io['text_config'],before['auth']['local_configuration_pin'])")
    controller = replace(controller, "        if state!='unknown':\n", "        if state!='unknown':\n            validate_config_io(child_io['text_config'],before['auth']['local_configuration_pin'],observed=True)\n")
    for token in ("CURRENT-STATUS-CONTROL", "CURRENT-STATUS-DELIVERY"):
        controller = controller.replace("EU4-PEACE-V2-" + token + "/1", "EU4-PEACE-V2-" + token + "/2")
    for name, tree in definitions(old("controller.py")).items():
        if name != "main": assert definitions(controller)[name] == tree
    write("controller.py", controller)

    budget = {"source_build_and_new_tests_limits": auth["source_build_and_new_tests_limits"], "future_live_budget_design": auth["future_live_budget_design"], "text_configuration_profile": auth["text_configuration_profile"], "manual_source_upper_bound": MANUAL_RESERVED, "whole_OS_IO_proven": False}
    write("budget.json", budget)
    write("source-delta.json", {"donor": (OLD / "source-manifest.json").relative_to(ROOT).as_posix(), "child_unchanged_AST": ["require", "pin", "decode", "read", "save", "bootstrap", "game_meter_class"], "controller_unchanged_AST": [n for n in definitions(old("controller.py")) if n != "main"], "new": ["exact text snapshot adapter", "configuration ledger and selected-state closure check", "schema2/config triple/four-subject source peer"], "runtime_contract_changed": ["BUILD identity/shape", "manifest schema2", "once grant schema2", "config raw triple metadata", "adapter executable and peer subject"], "original_candidate_or_donor_modified": False, "new_case_count_max": 8, "runtime_grant_created": False, "real_config_operations": 0})
    protocol = """# Exact text configuration source profile R2

This is a new source-only profile. R1, its one failed status, original v2 CLI and
all old tests remain frozen. No new live grant or config pin is created here.

Future authorization must be EU4-PEACE-V2-CURRENT-STATUS-ONCE/2 and bind this
source manifest, controller, child, adapter, a sealed/passed independent review
with those four subject triples, and local_configuration_pin exactly
{path: local.env, bytes: integer 0..65536, sha256: lowercase64}. Build authorization
alone and the old /1 grant fail closed. Runtime config path is ROOT/local.env,
not a command-line parameter. Selection and original budgets remain fixed.

The adapter accepts only r/rt, utf-8-sig, strict/default errors and universal
newlines. It rejects aliases, writes, other text and custom opening options.
Each snapshot opens binary, verifies regular size <=64KiB and expected size,
reserves and accounts the full size+1 request through the unchanged ordinary
Meter, reads once, charges returned raw bytes, compares the raw SHA and size,
closes binary, then privately decodes and validates the frozen KEY grammar.
Generic errors suppress exception context; no raw line/value/text is logged.
Valid text enters a read-only in-memory stream; virtual reads add no physical
bytes. Up to16 snapshots are allowed. Every accepted current result additionally
requires accepted exact-pin snapshots and closed binary/virtual streams.

This validates syntax and byte identity, not configured-path semantics, all
Mods, world compatibility or downstream arbitrary value usage. No global stdout
scrubber is installed and the frozen parser/CLI is not modified. Malformed
syntax/encoding is blocked before that parser can format raw_line. Existing
whole-IO limitations remain: intercepted explicit Python reads, not OS/import
cache internals or full delegated API coverage. Generic donor __getattr__ routes
remain unchanged. Required unmetered routes must block a future live decision.

Only eight new fictional adapter cases may run once, after source freeze.
Fixtures and injected opener paths remain inside this namespace; the real
local.env is never statted, opened, hashed, read, imported or used as a fixture.
The runner compiles only the frozen donor Meter/ReadPort class definitions;
no donor main, old fake/tests, CLI, status, PE, game or native calls run.
First failure stops; no automatic repair/retry. Job45s/768MiB/output2MiB bounds
apply to the new tests, and software source guards remain768MiB/1GiB stop.

Current presence is never original-request effect, acceptance, settlement or
peace completion. All existing false authority and unknown closure remain.
"""
    write("PROTOCOL.md", protocol)

    own = ["child.py", "controller.py", "runtime_contract.py", "text_config_adapter.py", "test_text_config_adapter.py", "run_adapter_once.py", "build_profile.py", "PROTOCOL.md", "budget.json", "source-delta.json"]
    pins = dict(inputs)
    for name in own:
        raw = read(HERE / name)
        if name.endswith(".py"): ast.parse(raw); compile(raw, str(HERE / name), "exec")
        pins[(HERE / name).relative_to(ROOT).as_posix()] = pin(raw)
    assert len(pins) <= 64
    manifest = {"schema": "EU4-PEACE-V2-CONTROLLER-SOURCE/2", "sealed": True, "runtime_grant_required": True,
                "stage": "source_frozen_new_adapter_tests_and_peer_pending", "native_ready": False, "selected_effect_verified": False,
                "build_authorization": {"path": AUTH, **AUTH_PIN}, "fixed_inputs": auth["fixed_inputs"], "source_pins": pins,
                "source_graph_sha256": hashlib.sha256(json.dumps(pins, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                "candidate_source_graph_sha256": auth["candidate_source_graph_sha256"], "real_env_operations": 0,
                "controller_or_child_executed": False, "old_tests_executed": 0}
    mp = write("source-manifest.json", manifest)
    for n, p in pins.items(): assert pin(read(ROOT / n, p)) == p
    assert pin(read(HERE / "source-manifest.json")) == mp
    result = {"schema": "EU4-TEXT-CONFIG-SOURCE-PREPARATION/1", "passed": True, "source_manifest": mp,
              "source_graph_count": len(pins), "read_events": READS, "explicit_source_returned": sum(v["bytes"] for v in READS),
              "manual_source_upper_bound": MANUAL_RESERVED, "source_total_with_manual_upper": MANUAL_RESERVED + sum(v["bytes"] for v in READS),
              "source_cap": 33554432, "memory": memory(), "real_env_operations": 0, "subject_execution": 0,
              "tests_run": 0, "live_authorized": False, "runtime_grant_created": False}
    pp = write("source-preparation.json", result)
    print(json.dumps({"passed": True, "source_manifest": mp, "preparation": pp, "source_count": len(pins), "explicit_source_returned": result["explicit_source_returned"], "manual_upper": MANUAL_RESERVED}, ensure_ascii=True))


if __name__ == "__main__": main()
