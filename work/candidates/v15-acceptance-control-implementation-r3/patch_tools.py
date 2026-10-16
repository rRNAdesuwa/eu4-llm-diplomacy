"""Candidate-local CLI/build metadata delta. Does not execute these tools."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = HERE / "files"
ROOT = HERE.parents[2]


def copy_text(name):
    return (ROOT / name.replace("v15", "v14")).read_text(encoding="utf-8").replace("v14", "v15").replace("V14", "V15").replace("EU4LAB/2", "EU4LAB/3")


def outputs():
    result = {}
    name = "tools/request_diplomacy_lab_v15.py"
    s = copy_text(name)
    s = s.replace('    for operation in (pair, speed, fixture):', '''    accept = sub.add_parser("accept", help="Fixed disposable acceptance on/off, bound to one next pair; no console strings")
    accept.add_argument("action", choices=("accept_on", "accept_off"))
    accept.add_argument("--bound-action", choices=sorted(lab.ACTIONS), required=True)
    accept.add_argument("--bound-target", choices=tuple(t for t in lab.TAGS if t != "FRA"), required=True)
    accept.add_argument("--bound-submit-sequence", type=positive, required=True)
    for operation in (pair, speed, fixture, accept):''')
    s = s.replace('"lease_pending": evidence["lease_pending"],', '"lease_pending": evidence["lease_pending"], "acceptance_window": evidence["acceptance_window"],')
    s = s.replace('args.operation in ("pair", "fixture")', 'args.operation in ("pair", "fixture", "accept")')
    s = s.replace('                lab.check_ready(evidence, live, lab.uptime_ms(), phase=keywords.get("phase"), operation=keywords.get("operation"))', '''                if args.operation == "accept":
                    keywords.update(bound_action=args.bound_action, bound_target=args.bound_target,
                                    bound_submit_sequence=args.bound_submit_sequence)
                lab.check_ready(evidence, live, lab.uptime_ms(), phase=keywords.get("phase"), operation=keywords.get("operation"))''')
    result[name] = s
    for name in ("bridge/diplomacy_lab_http_v15.py", "tools/serve_diplomacy_lab_v15.py"):
        s = copy_text(name).replace("8770", "8771")
        if name.startswith("bridge/"):
            shared = (ROOT / "bridge/diplomacy_lab_http.py").read_text(encoding="utf-8")
            validator = shared[shared.index('    def _validate_request('):shared.index('    def _intents(')]
            validator = validator.replace('        require(', '        transport.require(').replace('REQUEST_FIELDS', 'transport.REQUEST_FIELDS')
            validator = validator.replace('raise ResearchError(', 'raise transport.ResearchError(').replace('EU4LAB/2', 'EU4LAB/3')
            validator = validator.replace('"expires": 1}', '"expires": 1, "bound_action": "none", "bound_target": "none", "bound_submit_sequence": 0}')
            s = s.replace('    def pair(self, body):', validator + '    def pair(self, body):')
            s = s.replace('        value["phase_attempted"]', '        value["acceptance_window"] = deepcopy(snapshot["evidence"].get("acceptance_window", {}))\n        value["phase_attempted"]')
            s = s.replace('        return value\n\n    def _validate_request', '''        value["acceptance_control"] = {"publication_surface": "explicit_versioned_CLI_only",
            "actions": ["accept_on", "accept_off"], "requires_exact_single_pair_binding": True,
            "http_accept_endpoint": False, "normal_ai_acceptance_verified": False}
        return value

    def _validate_request''')
        result[name] = s
    name = "work/native/v15/build-lab-1375.cmd"
    s = copy_text(name)
    # A second formal link in a previously used/built output is always forbidden.
    marker = 'pushd "%~dp0"\n'
    s = s.replace(marker, marker + '''if exist "..\\..\\runtime\\native1375-v15\\build.json" (popd & exit /b 91)
if exist "..\\..\\runtime\\native1375-v15\\eu4_pair_lab_v15_1375.dll" (popd & exit /b 92)
''')
    marker = 'ml64 /nologo /c '
    line = 'cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\\..\\runtime\\native1375-v15\\test-acceptance-1375.obj" test-acceptance-1375.cpp\nif errorlevel 1 (popd & exit /b 1)\n'
    s = s.replace(marker, line + marker)
    s = s.replace(' kernel32.lib user32.lib advapi32.lib', ' "..\\..\\runtime\\native1375-v15\\test-acceptance-1375.obj" kernel32.lib user32.lib advapi32.lib')
    result[name] = s

    return result


def main():
    from candidate_guard import write
    for name, value in outputs().items():
        write(FILES / name, value.encode("utf-8"))


if __name__ == "__main__":
    raise SystemExit("Use prepare.py --check or --refresh-candidate; patch helpers cannot write independently")
