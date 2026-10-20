"""Fresh read-only CRT handler sample; never invokes the getter or handler."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import secrets
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT/'work/reports/war-peace-api-20261015-r8-stack-scope/war/live-80340-current-app-r3.json'
PRODUCER = ROOT/'work/capture_nocb_current_app_r3_20261015.py'
CRT_MANIFEST = ROOT/'work/reports/war-peace-api-20261015-r6-crt/manifest.json'
CRT_EVIDENCE = ROOT/'work/reports/war-peace-api-20261015-r6-crt/evidence.json'
OUT = ROOT/'work/reports/war-peace-api-20261015-r8-stack-scope/war/live-80340-crt-handler-current-r4.json'


def pin(path):
    raw = path.read_bytes()
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def require(value, message):
    if not value:
        raise ValueError(message)


# Authenticate reused Python before executing it. No historical pointer/nonce
# is reused; each sample below resolves all current roots through prior.sample.
raw = PRIOR.read_bytes()
require(hashlib.sha256(raw).hexdigest() ==
        '095cb1a85b215e54bfc99a292782dfe21d687abb7bd7c30888d1fbe00f6210a7', 'R3 receipt differs')
require(pin(PRODUCER) == json.loads(raw)['source_pins'][PRODUCER.relative_to(ROOT).as_posix()],
        'R3 producer differs before import')
require(pin(CRT_MANIFEST)['sha256'] ==
        'f1d167df036525fbb5b29d613168260cc3776829eacf854df6c1cc8d7809ab8f', 'CRT evidence manifest differs')
manifest = json.loads(CRT_MANIFEST.read_bytes())
entry = next(row for row in manifest['files'] if row['path'] == CRT_EVIDENCE.relative_to(ROOT).as_posix())
require(pin(CRT_EVIDENCE) == {k: entry[k] for k in ('bytes', 'sha256')}, 'CRT evidence differs')
evidence = json.loads(CRT_EVIDENCE.read_bytes())
rows = evidence['reused_getter']['instructions']
cursor = 0x1A639AC
GETTER = bytearray()
for row in rows:
    require(int(row['rva'], 16) == cursor, 'Getter rows are not contiguous')
    chunk = bytes.fromhex(row['bytes'])
    GETTER.extend(chunk)
    cursor += len(chunk)
require(cursor == 0x1A639E0, 'Getter extent differs')
GETTER = bytes(GETTER)
spec = importlib.util.spec_from_file_location('fixed_current_app_reader_for_crt', PRODUCER)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
old = prior.old

SOURCES = (PRIOR, PRODUCER, CRT_MANIFEST, CRT_EVIDENCE, Path(__file__).resolve())


def sources():
    return {p.relative_to(ROOT).as_posix(): pin(p) for p in SOURCES}


def ror64(value, count):
    require(type(value) is int and 0 <= value < 1 << 64 and
            type(count) is int and 0 <= count < 64, 'Invalid rotate scalar')
    return ((value >> count) | (value << ((64-count) & 63))) & ((1 << 64)-1)


def sample(reader, base):
    value = prior.sample(reader, base)
    code = reader.read(base+0x1A639AC, len(GETTER))
    require(code == GETTER, 'Loaded getter bytes differ from fixed PE evidence')
    c1 = reader.read(base+0x1FC16B8, 8)
    e1 = reader.read(base+0x233D0C8, 8)
    c2 = reader.read(base+0x1FC16B8, 8)
    e2 = reader.read(base+0x233D0C8, 8)
    require(c1 == c2 and e1 == e2, 'Cookie or encoded handler changed inside sample')
    cookie, encoded = struct.unpack('<Q', c1)[0], struct.unpack('<Q', e1)[0]
    decoded = ror64(cookie ^ encoded, cookie & 63)
    value['crt_handler'] = dict(cookie_rva='0x1fc16b8', encoded_slot_rva='0x233d0c8',
        cookie_reads_hex=[c1.hex(), c2.hex()], encoded_reads_hex=[e1.hex(), e2.hex()],
        getter_rva='0x1a639ac', getter_code_hex=code.hex(), getter_bytes_match=True,
        getter_code_sha256=hashlib.sha256(code).hexdigest(), rotation_count=cookie & 63,
        decoded_pointer=hex(decoded), decoded_null_in_selected_reads=decoded == 0,
        formula='ROR64(cookie XOR encoded_slot, cookie & 63)',
        getter_was_called=False, CRT_lock_was_held=False, interval_null_proven=False,
        allocator_first_attempt_success_proven=False, callback_authority_proven=False)
    require(old.roots(reader, base) == value['roots'], 'World guards changed after CRT sample')
    return value


def main():
    require(not OUT.exists(), 'Exclusive output required')
    initial = sources()
    backend = old.TagCommandBackend()
    identity = dict(pid=80340, creation='01dd5c075fcf8c26', session=secrets.token_hex(16),
        dll_sha256=backend.manifest['dll']['sha256'], manifest_sha256=backend.manifest_sha)
    started = time.perf_counter()
    with old.RuntimeCapture(identity, backend) as cap:
        require(not any(Path(p).name.lower().startswith(('eu4_bridge_', 'eu4_pair_', 'eu4_spy_',
            'eu4_tag_command_', 'tag_diplomacy')) for _, p in cap.modules), 'Unexpected research module')
        reader = old.BudgetReader(old.HeldRPMPort(cap.held))
        first, second = sample(reader, cap.base), sample(reader, cap.base)
        require(first == second, 'Complete current-app/CRT passes differ')
        cap.held.identity_check()
        require(cap.held.modules() == cap.modules and old.pins() == cap.initial_pins
                and sources() == initial, 'Process modules or fixed sources changed')
        base = cap.base
    result = dict(schema='EU4-CRT-HANDLER-CURRENT-READONLY/4',
        captured_utc=datetime.now(timezone.utc).isoformat(), identity=identity,
        identity_purpose='Fresh read-only nonce, not TAG installation/request',
        base=hex(base), source_pins=initial, observer_source_pins=cap.initial_pins,
        samples=[first, second], two_pass_equal=True,
        duration_ms_including_host_and_source_checks=round((time.perf_counter()-started)*1000, 3),
        rpm_budget=dict(calls=reader.calls, bytes=reader.bytes, largest_read=reader.largest),
        native_callback_observed=False, native_stack_sampled=False, native_lifetime_authority=False,
        native_ready=False, native_calls=0, requests_published=0, memory_written=False,
        injection_performed=False, hooks_installed=0, saves_written=0, reloads=0,
        new_API_effect_tested=False, lifetime_or_interval_guarantee=False)
    with OUT.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=True, indent=2)
        f.write('\n')
    print(json.dumps(dict(output=str(OUT), sha256=pin(OUT)['sha256'], two_pass_equal=True,
        decoded_null_in_selected_reads=first['crt_handler']['decoded_null_in_selected_reads'],
        rpm_budget=result['rpm_budget'], duration_ms=result['duration_ms_including_host_and_source_checks'],
        native_ready=False)))


if __name__ == '__main__':
    main()
