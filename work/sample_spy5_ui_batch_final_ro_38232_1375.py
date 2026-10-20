"""One new, fixed-identity final census after the whole manual UI spy batch."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETUP_PATH = ROOT / 'work/sample_spy_test_setup_ro_38232_1375.py'
SETUP_SHA = 'e739b6fd9af0f695350844b7dc9aa9565649488e0a72b5b6e1fafd1372b4b0c6'
INITIAL = ROOT / 'work/runtime/spy-test-setup-ro-38232-after_fixture.json'
INITIAL_SHA = '21d40a44976fdc053c575740442bd99180b192ec87210c27e9989247270de81c'
JOURNAL = ROOT / 'work/runtime/spy5-ui-batch-38232.jsonl'
OUTPUT = ROOT / 'work/runtime/spy5-ui-batch-final-ro-38232.json'


def main():
    import hashlib
    if hashlib.sha256(SETUP_PATH.read_bytes()).hexdigest() != SETUP_SHA:
        raise ValueError('Fixed setup helper changed')
    spec = importlib.util.spec_from_file_location('_fixed_setup_ui_final', SETUP_PATH)
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)
    if Path(setup.__file__).resolve() != SETUP_PATH:
        raise ValueError('Setup provenance')
    setup.verify()
    if setup.sha(INITIAL) != INITIAL_SHA or JOURNAL.stat().st_size > 32768:
        raise ValueError('Initial or journal differs')
    initial = json.loads(INITIAL.read_text('utf-8'))
    journal_sha = setup.sha(JOURNAL)
    rows = [json.loads(line) for line in JOURNAL.read_text('utf-8').splitlines()]
    expected = [('start', None)]
    for family in setup.FAMILIES:
        expected.extend([('intent', family), ('ui_confirmed', family)])
    if [(row['event'], row['family']) for row in rows] != expected:
        raise ValueError('Whole fixed UI batch not recorded; never resend')
    if initial['status'] != 'captured' or initial['pid'] != setup.PID or initial['creation'] != setup.CREATION or initial['world'] != 0x1a0cb39c020:
        raise ValueError('Same-process initial identity')
    world = initial['world']
    with OUTPUT.open('xb') as stream:
        record = dict(kind='fixed_spy_mod_setup_ro_census', phase='after_ui_spy_batch',
                      pid=setup.PID, creation=setup.CREATION, expected_raw_date=setup.DATE,
                      source_pins=setup.PINS, spy_reports={}, subject_report=None,
                      diagnostic_report=None, game_native_calls=False, game_memory_written=False,
                      individual_effect_verified=False, production_ready=False, group_atomic=False,
                      actual_cost_verified=False, initial_reference_sha256=INITIAL_SHA,
                      ui_journal_sha256=journal_sha, setup_helper_sha256=SETUP_SHA,
                      capture_helper_sha256=setup.sha(__file__),
                      capture_scope='read_only_final_after_manual_ui_batch',
                      native_request_receipt=False)
        try:
            full = setup.module('_ui_final_dense_r2', 'spy-dense-full-observer-r2-1375')
            subject = setup.module('_ui_final_subject', 'subject-toggle-observer-1375')
            for family in setup.FAMILIES:
                x = full.sample_process(pid=setup.PID, creation=setup.CREATION,
                                        executable=ROOT.parent / 'eu4.exe', family=family)
                identity = x['before']['snapshot']['identity']
                if identity['game'] != world or identity['date'] != setup.DATE:
                    raise ValueError('Fixed final world/date differs')
                record['spy_reports'][family] = x
            x = subject.sample_process(pid=setup.PID, creation=setup.CREATION,
                                       executable=ROOT.parent / 'eu4.exe')
            identity = x['snapshot']['graph']['identity']
            if identity['game'] != world or identity['date'] != setup.DATE:
                raise ValueError('Subject world/date differs')
            record['subject_report'] = x
            diag = setup.diagnostics(full.dependencies()[0])
            if int(diag['state']['game_pointer'], 16) != world or diag['state']['current_raw_date'] != setup.DATE:
                raise ValueError('Diagnostic world/date differs')
            record['diagnostic_report'] = diag
            setup.verify()
            if setup.sha(INITIAL) != INITIAL_SHA or setup.sha(JOURNAL) != journal_sha or setup.sha(SETUP_PATH) != SETUP_SHA:
                raise ValueError('Pinned inputs changed during capture')
            record.update(status='captured', world=world)
        except Exception as error:
            record.update(status='unsupported_or_read_failed', error_type=type(error).__name__, error=str(error))
        stream.write((json.dumps(record, sort_keys=True, indent=2) + '\n').encode())
    print(json.dumps(dict(status=record['status'], error=record.get('error'),
                          bytes=OUTPUT.stat().st_size, sha256=setup.sha(OUTPUT),
                          ui_journal_sha256=journal_sha,
                          networks={f: x['before']['snapshot']['cost']['network_centipoints']
                                    for f, x in record['spy_reports'].items()},
                          capture_native_calls=False, individual_effect_verified=False)))
    return 0 if record['status'] == 'captured' else 1


if __name__ == '__main__':
    raise SystemExit(main())
