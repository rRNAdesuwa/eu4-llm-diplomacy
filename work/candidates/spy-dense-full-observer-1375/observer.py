"""Dense fee kernel inside the fixed FRA/ENG held-process RO identity envelope."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
MAX_BYTES = 16 * 1024 * 1024
MAX_CALLS = 8192
PINS = {
    'work/candidates/spy-modifier-observer-1375/observer.py':
        'd386524d543d96509fe4230e5fd02b01bc7f404f5419054ae2a84f66fdb13e48',
    'work/candidates/spy-dense-aggregate-contract-1375/dense_ro.py':
        '5d10d4eb58d3317de70ceed5b900633cca7e26907a28c8e31ebc9958df87391e',
    'work/review-results/spy-dense-aggregate-root-20261008a/review.json':
        '5ee10b2d27be552b4750170e1b5054d24ab9d01ff7b5116b59a32f9e3f5d5795',
    'work/review-results/spy-modifier-observer-native-inventory-20261008a/review.json':
        'cba5fc6a916bdeaae7d9f4b8d903d992120357788b8fe011e0c0ae86c5131f00',
}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(65536):
            digest.update(block)
    return digest.hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    require(Path(loaded.__file__).resolve() == (ROOT / path).resolve(), 'Module provenance')
    return loaded


def dependencies():
    for path, expected in PINS.items():
        require(sha(ROOT / path) == expected, 'Reviewed dependency changed: ' + path)
    spy = module('_dense_envelope_fixed_spy', 'work/candidates/spy-modifier-observer-1375/observer.py')
    dense = module('_dense_envelope_fixed_kernel', 'work/candidates/spy-dense-aggregate-contract-1375/dense_ro.py')
    spy.verify_dependencies()
    return spy, dense


class BudgetReader:
    def __init__(self, reader):
        self.reader, self.bytes, self.calls = reader, 0, 0

    def read(self, address, size):
        require(type(address) is int and 0x10000 <= address < 0x800000000000 and
                type(size) is int and 1 <= size <= 65536 and address + size <= 0x800000000000,
                'Read range')
        require(self.bytes + size <= MAX_BYTES and self.calls < MAX_CALLS, 'Shared outer read budget')
        self.bytes += size
        self.calls += 1
        raw = self.reader.read(address, size)
        require(type(raw) is bytes and len(raw) == size, 'Exact raw read')
        return raw


def capture(reader, base, *, family='corrupt_officials'):
    spy, dense = dependencies()
    require(type(family) is str and family in spy.contract()['families'], 'Fixed spy family')
    budget = BudgetReader(reader)
    before = spy.capture(budget, base, family=family, target='ENG')
    identity = before['snapshot']['identity']
    actor = identity['countries']['FRA']['address']
    cost = dense.capture(budget, base, actor, family)
    after = spy.capture(budget, base, family=family, target='ENG')
    require(spy.canonical(before['snapshot']) == spy.canonical(after['snapshot']),
            'Full country/network/definition/selected state changed around dense read')
    dense.code_pins(dense.Budget(budget), base, dense.report())
    require(cost['base'] == base and cost['actor'] == actor and cost['family'] == family and
            cost['before']['base_milli'] == before['snapshot']['cost']['base_milli'] and
            cost['before']['cache_state'] == before['snapshot']['cost']['cache_state'],
            'Dense result not bound to the full snapshot')
    return dict(schema_version=1, profile='spy_dense_full_ro_1375_1', family=family,
                before=before, dense=cost, after=after, full_envelope_equal=True,
                source_kind='injected_reader_not_process_attested',
                read_budget=dict(bytes=budget.bytes, calls=budget.calls,
                                 max_bytes=MAX_BYTES, max_calls=MAX_CALLS),
                source_pins=PINS, native_calls=False, native_legality_verified=False,
                actual_cost_verified=False, individual_effect_verified=False,
                strict_single_player_verified=False, world_epoch_verified=False,
                paused_verified=False, cache_freshness_verified=False,
                object_lifetime_verified=False, production_ready=False)


def sample_process(*, pid, creation, executable, family='corrupt_officials'):
    """Explicit future RO call. No CLI and no native function is invoked."""
    spy, _ = dependencies()
    spy.integer(pid, 1, 2**32 - 1)
    require(type(creation) is str and re.fullmatch('[0-9a-f]{16}', creation) and int(creation, 16) > 0,
            'Exact creation')
    require(type(family) is str and family in spy.contract()['families'], 'Fixed spy family')
    executable = Path(executable).resolve()
    require(executable == (ROOT.parent / 'eu4.exe').resolve() and sha(executable) == spy.EXE_SHA,
            'Exact executable path/SHA')
    sys.path.insert(0, str(ROOT))
    from work import probe_diplomacy_current as legacy
    require(Path(legacy.__file__).resolve() == (ROOT / 'work/probe_diplomacy_current.py').resolve() and
            legacy.ROOT == ROOT, 'Legacy module provenance')
    _, signature = legacy.verified_executable(executable)
    contract = spy.contract()
    require(signature == dict(timestamp=contract['pe']['timestamp'], size=contract['pe']['image_size']),
            'Exact PE')
    reader = legacy.ProcessReader(pid, executable, signature)
    try:
        held = spy.held_identity(reader, pid, int(creation, 16))
        result = capture(reader, reader.base, family=family)
        require(spy.held_identity(reader, pid, int(creation, 16)) == held, 'Held identity changed')
        legacy.verify_module_signature(legacy.pe_signature(reader, reader.base), signature)
        require(sha(executable) == spy.EXE_SHA and reader.bytes_read <= MAX_BYTES,
                'Final EXE identity or including PE guards read budget')
        dependencies()
        result['source_kind'] = 'held_process_readonly'
        result['process'] = dict(identity=held, path=str(executable), disk_exe_sha256=spy.EXE_SHA,
                                 loaded_full_image_hash_verified=False,
                                 rights=['PROCESS_QUERY_INFORMATION', 'PROCESS_VM_READ'])
        return result
    finally:
        reader.close()
