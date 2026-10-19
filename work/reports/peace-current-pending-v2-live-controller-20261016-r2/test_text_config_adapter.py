"""Eight new fictional adapter cases only; no old fixture/CLI/environment import."""
from pathlib import Path
import ast, builtins, hashlib, io, json, os, sys, traceback, types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
READS = []
METERS = []


def pin(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def read(path, expected=None):
    size = path.stat().st_size
    assert size <= 4194304
    raw = path.read_bytes()
    READS.append({"path": str(path), **pin(raw)})
    assert sum(x["bytes"] for x in READS) <= 8388608
    if expected is not None:
        assert pin(raw) == expected
    return raw


def load():
    manifest = json.loads(read(HERE / "source-manifest.json"))
    def source(name):
        return read(ROOT / name, manifest["source_pins"][name])
    adapter = types.ModuleType("_new_fictional_text_adapter")
    adapter.__file__ = str(HERE / "text_config_adapter.py")
    exec(compile(source((HERE / "text_config_adapter.py").relative_to(ROOT).as_posix()), adapter.__file__, "exec"), adapter.__dict__)
    name = "work/candidates/peace-current-pending-observer-1375-v2/offline_child.py"
    tree = ast.parse(source(name))
    selected = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in ("Meter", "ReadPort")]
    assert len(selected) == 2
    donor = {"Path": Path, "os": os, "OPEN": builtins.open, "LIMIT": 4194304}
    exec(compile(ast.Module(body=selected, type_ignores=[]), name, "exec"), donor)
    class TrackedMeter(donor["Meter"]):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            METERS.append(self)
    return adapter, TrackedMeter


def fixture(label, raw):
    directory = HERE / "fictional-fixtures" / label
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "local.env"
    with path.open("xb") as f:
        f.write(raw)
    return path


def rejected(fn):
    try:
        fn()
    except ValueError as exc:
        assert str(exc) == "Configuration snapshot refused (redacted)"
        return traceback.format_exc()
    raise AssertionError("Expected generic refusal")


def case_1_equivalence(a, Meter):
    raw = b"\xef\xbb\xbf# fictional\r\n" + "KEY='\u017e\U0001f600'\r\nSECOND=two\rTHIRD=three\n".encode()
    p = fixture("case1", raw); m = Meter({}, 100000, 1, 1)
    x = a.TextConfigAdapter(m, p, pin(raw), builtins.open)
    expected = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8-sig", errors="strict", newline=None).read()
    with x.open(p, "r", -1, "utf-8-sig", None, None) as f:
        assert f.encoding == "utf-8-sig" and f.errors == "strict" and not f.writable()
        assert f.read() == expected
        f.seek(0); assert f.read().splitlines() == expected.splitlines()
    assert f.closed and x.events[0]["binary_closed"] and x.events[0]["virtual_normal_exit"]
    assert m.totals["ordinary"] == len(raw) and m.attempts["ordinary"] == 1


def case_2_full_reserve(a, Meter):
    raw = b"KEY=fictional\n"; p = fixture("case2", raw)
    m = Meter({}, len(raw), 1, 1); x = a.TextConfigAdapter(m, p, pin(raw), builtins.open)
    rejected(lambda: x.open(p, encoding="utf-8-sig"))
    assert m.totals["ordinary"] == 0 and m.requested["ordinary"] == len(raw) + 1
    assert m.entry(x.key, "ordinary")["refused_before_read"] == 1 and x.events[0]["binary_closed"]
    m2 = Meter({}, len(raw) + 1, 1, 1); y = a.TextConfigAdapter(m2, p, pin(raw), builtins.open)
    with y.open(p, encoding="utf-8-sig") as f: assert f.read() == raw.decode()
    assert m2.totals["ordinary"] == len(raw) and m2.requested["ordinary"] == len(raw) + 1
    assert m2.entry(y.key, "ordinary")["short_reads_including_EOF"] == 1


def case_3_pin_changes(a, Meter):
    raw = b"KEY=first\n"; p = fixture("case3", raw); expected = pin(raw)
    p.write_bytes(b"KEY=other\n")
    m = Meter({}, 10000, 1, 1); x = a.TextConfigAdapter(m, p, expected, builtins.open)
    rejected(lambda: x.open(p, encoding="utf-8-sig"))
    assert m.totals["ordinary"] == len(raw) and not x.events[0]["accepted"]
    p.write_bytes(raw + b"X=longer\n")
    m2 = Meter({}, 10000, 1, 1); y = a.TextConfigAdapter(m2, p, expected, builtins.open)
    rejected(lambda: y.open(p, encoding="utf-8-sig"))
    assert m2.attempts["ordinary"] == 0 and y.events[0]["binary_closed"]


def case_4_profile_refusals(a, Meter):
    raw = b"KEY=value\n"; p = fixture("case4", raw); opens = []
    def opener(*args, **kwargs): opens.append(True); return builtins.open(*args, **kwargs)
    x = a.TextConfigAdapter(Meter({}, 100000, 1, 1), p, pin(raw), opener)
    checks = [lambda: x.open(str(p.parent / ".." / p.parent.name / "local.env"), encoding="utf-8-sig"),
              lambda: x.open(p.parent / "other.env", encoding="utf-8-sig"),
              lambda: x.open(p, "w", encoding="utf-8-sig"), lambda: x.open(p, "rb"),
              lambda: x.open(p, encoding="utf-8"), lambda: x.open(p, encoding="utf-8-sig", errors="ignore"),
              lambda: x.open(p, encoding="utf-8-sig", newline=""),
              lambda: x.open(p, encoding="utf-8-sig", opener=lambda *v: 0)]
    for check in checks: rejected(check)
    assert opens == []
    p.write_bytes(b"#" * 65537)
    y = a.TextConfigAdapter(Meter({}, 100000, 1, 1), p, {"bytes": 65536, "sha256": "0" * 64}, opener)
    rejected(lambda: y.open(p, encoding="utf-8-sig"))
    assert y.meter.totals["ordinary"] == 0 and y.events[0]["binary_closed"]


def case_5_redaction(a, Meter):
    secret = "FICTIONAL_SENSITIVE_LINE"
    raws = [(secret + " no_equals\n").encode(), b"KEY=" + secret.encode() + b"\xff\n"]
    for number, raw in enumerate(raws):
        p = fixture("case5_" + str(number), raw); x = a.TextConfigAdapter(Meter({}, 100000, 1, 1), p, pin(raw), builtins.open)
        tb = rejected(lambda: x.open(p, encoding="utf-8-sig"))
        assert secret not in tb and secret not in json.dumps(x.summary())
        assert not x.events[0]["accepted"] and x.events[0]["binary_closed"]


def case_6_close_and_limit(a, Meter):
    raw = b"KEY=fictional\n"; p = fixture("case6", raw)
    m = Meter({}, 100000, 1, 1); x = a.TextConfigAdapter(m, p, pin(raw), builtins.open)
    for _ in range(16):
        f = x.open(p, encoding="utf-8-sig")
        assert f.read() == raw.decode(); f.close(); f.close(); assert f.closed
    rejected(lambda: x.open(p, encoding="utf-8-sig"))
    assert x.opened == 16 and m.attempts["ordinary"] == 16 and m.totals["ordinary"] == 16 * len(raw)
    assert all(e["virtual_closed"] for e in x.events[:16])
    assert x.events[16]["opened"] is False


def case_7_short_and_error(a, Meter):
    raw = b"KEY=fictional\n"; p = fixture("case7", raw)
    class Fault:
        def __init__(self, mode): self.f = builtins.open(p, "rb"); self.mode = mode
        def fileno(self): return self.f.fileno()
        @property
        def closed(self): return self.f.closed
        def close(self): self.f.close()
        def read(self, n):
            if self.mode == "error": raise OSError("FICTIONAL_PRIVATE_EXCEPTION")
            return self.f.read(n - 2)
    for mode in ("short", "error"):
        m = Meter({}, 100000, 1, 1); x = a.TextConfigAdapter(m, p, pin(raw), lambda *v: Fault(mode))
        tb = rejected(lambda: x.open(p, encoding="utf-8-sig"))
        assert "FICTIONAL_PRIVATE_EXCEPTION" not in tb and x.events[0]["binary_closed"]
        v = m.entry(x.key, "ordinary")
        assert v["read_attempts"] == 1 and v["read_errors"] == int(mode == "error")
        assert m.totals["ordinary"] == (len(raw) - 1 if mode == "short" else 0)


def case_8_routing(a, Meter):
    raw = b"KEY=fictional\n"; p = fixture("case8", raw)
    class Base(Meter):
        def __init__(self): super().__init__({}, 100000, 1, 1); self.delegated = []
        def open(self, file, mode="r", *args, **kwargs): self.delegated.append((str(file), mode)); return "unchanged-binary-delegate"
    contract = types.SimpleNamespace(ROOT=p.parent)
    cls = a.meter_class(Base, contract, {"path": "local.env", **pin(raw)}, builtins.open)
    m = cls(); other = p.parent / "owned.bin"
    assert m.open(other, "rb") == "unchanged-binary-delegate" and len(m.delegated) == 1
    rejected(lambda: m.open(other, encoding="utf-8-sig"))
    with m.open(p, encoding="utf-8-sig") as f: assert f.read() == raw.decode()
    assert len(m.delegated) == 1 and m.text_config.summary()["opened_snapshots"] == 1


def main():
    with (HERE / "adapter-test-claim.json").open("x", encoding="ascii") as f:
        json.dump({"new_cases_max": 8, "runs_per_case_max": 1, "real_config_read": False, "retry": False}, f)
    results = []; failed = None
    try:
        a, Meter = load()
        for case in (case_1_equivalence, case_2_full_reserve, case_3_pin_changes, case_4_profile_refusals,
                     case_5_redaction, case_6_close_and_limit, case_7_short_and_error, case_8_routing):
            case(a, Meter)
            results.append({"name": case.__name__, "passed": True, "runs": 1})
    except BaseException as exc:
        failed = {"case": locals().get("case", main).__name__, "type": type(exc).__name__, "message": "Offline adapter case failed; stopped without retry"}
    receipt = {"schema": "EU4-TEXT-CONFIG-ADAPTER-FIRST-CASES/1", "passed": failed is None,
               "results": results, "failure": failed, "source_reads": READS,
               "source_returned": sum(x["bytes"] for x in READS), "new_case_count": len(results) + int(failed is not None),
               "fictional_snapshot_meters": [{"returned": m.totals, "requested": m.requested,
                    "attempts": m.attempts, "per_path": m.files} for m in METERS],
               "fictional_snapshot_returned": sum(m.totals["ordinary"] for m in METERS),
               "old_tests_run": 0, "CLI_runs": 0, "real_config_operations": 0, "game_reads": 0, "native_calls": 0,
               "automatic_retry": False, "scope": "New fictional fixtures only; donor class definitions, not donor main or old tests"}
    with (HERE / "adapter-first-receipt.json").open("x", encoding="ascii", newline="\n") as f:
        json.dump(receipt, f, indent=2, sort_keys=True, ensure_ascii=True); f.write("\n")
    print(json.dumps({"passed": failed is None, "cases_passed": len(results), "failure": failed}, ensure_ascii=True))
    return 0 if failed is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
