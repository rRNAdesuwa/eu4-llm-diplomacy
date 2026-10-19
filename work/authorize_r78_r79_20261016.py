"""Root exact one-attempt file-only grants after independent raw/source gates."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pin(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def pair(n, sha):
    return dict(bytes=n, sha256=sha)


def one(number, base, subjects, review_specs, extra, executor):
    out = ROOT / ('work/reports/' + ('server-expected-owner-sample-data-root-authorization-20261016-r78'
        if number == 78 else 'war-peace-api-20261016-r79-root-authorization'))
    assert not out.exists()
    assert not any((ROOT / (base + n)).exists() for n in
        ('run-authorization.json', 'claim.json', 'attempt-claim.json', 'capture.json', 'failure.json', 'owned-code.json'))
    pins = {}; ledger = []
    def read(rel, expected):
        path = (ROOT / rel).resolve()
        assert path.is_relative_to(ROOT) and not rel.startswith('work/deps/') and path.suffix.lower() not in ('.exe', '.dll', '.pyd')
        a = path.stat(); assert a.st_size <= 4 * 1024 * 1024
        assert sum(r['bytes'] for r in ledger) + a.st_size + 262144 <= 2 * 1024 * 1024
        raw = path.read_bytes(); b = path.stat(); ledger.append(dict(path=rel, **pin(raw)))
        assert (len(raw), a.st_size, a.st_mtime_ns) == (b.st_size, b.st_size, b.st_mtime_ns)
        assert pin(raw) == expected and (rel not in pins or pins[rel] == expected), rel
        pins[rel] = expected
        return json.loads(raw) if rel.endswith('.json') else raw
    source = read(base + 'source-manifest.json', subjects['subject_source_manifest'])
    read(base + 'produce.py', subjects['subject_producer']); read(base + 'entry-seed.json', subjects['subject_entry_seed'])
    assert source['source_pins'][base + 'produce.py'] == subjects['subject_producer']
    assert source['source_pins'][base + 'entry-seed.json'] == subjects['subject_entry_seed']
    groups = {}
    for label, folder, fp, mp in review_specs:
        fpath = 'work/reports/' + folder + '/findings.json'; mpath = 'work/reports/' + folder + '/manifest.json'
        f = read(fpath, fp); m = read(mpath, mp)
        assert f['sealed'] and f['passed'] and f['blocking_findings'] == [] and m['sealed']
        if label == 'upstream_actual_review':
            if number == 78:
                assert f['subject_final_manifest'] == pair(18295, '5f32790f03736d35c15483075d37450e55f6aadad751e71d6dfacfc99cd4a5e7')
                assert f['subject_capture_pin'] == pair(345402, '92564d4dc655fe32942bc3b928840854b9c97340fa4fb7fd49f9e5b70cc7b020')
                assert f['subject_contract_pin'] == pair(23528, '82d93800fc8101e5667e848910e07faae5a778326be27935a2b7e19569f525a0')
            else:
                assert f['subject_manifest'] == pair(27579, '3ca9f6aff9c0ceffd0d0096a4ace1a1f7ff294b36acb0f88ed0c3a0f9f9ec69b')
                assert f['subject_capture'] == pair(82235, '16125c7d31832311ef0b67019b01011b2703699f05408feb33ca881692f14c65')
        else:
            assert all(f[k] == v for k, v in subjects.items())
            if label in ('raw_seed_review', 'root_raw_entry_review'):
                if number == 78:
                    assert type(f['data_rva']) is int and f['data_rva'] == 0x1caa8f0 and type(f['requested_bytes']) is int and f['requested_bytes'] == 6
                else:
                    assert f['scope'] == 'raw_direct_call_entry_seed_only' and f['entry_rva'] == '0x97bd30'
                    assert f['call_site_rva'] == '0x99358a' and f['raw_call_hex'] == 'e8a187feff'
        groups[label] = dict(findings=dict(path=fpath, **fp), manifest=dict(path=mpath, **mp))
    for rel, value in dict(pins).items():
        read(rel, value)
    if number == 78:
        auth = dict(schema='EU4-R78-ROOT-AUTHORIZATION/1', explicit_start=True,
            operation='one-fixed6B-file-DATA-only', data_rva=0x1caa8f0, requested_bytes=6,
            reviews=groups, source_bytes_limit=4 * 1024 * 1024, retained_bytes_limit=4 * 1024 * 1024, **subjects)
    else:
        auth = dict(schema='EU4-R79-ROOT-AUTHORIZATION/1', root_explicit_start_received=True,
            operation='one-fixed-callee-97bd30-static', entry_rva='0x97bd30', call_site_rva='0x99358a', raw_call_hex='e8a187feff',
            source_manifest=subjects['subject_source_manifest'], producer_pin=subjects['subject_producer'], entry_seed_pin=subjects['subject_entry_seed'],
            source_bytes_limit=32 * 1024 * 1024, retained_bytes_limit=16 * 1024 * 1024, **groups)
    auth.update(sealed=True, sole_executor=executor, single_attempt=True, authorizes_retry=False,
        software_memory_limit=768 * 1024 * 1024, stop_at_or_above_1GiB=True, native_ready=False,
        host_guard_change_authorized=False, reader_adoption_allowed=False, selected_effect_verified=False,
        world_lease=False, atomic_snapshot=False, scope=extra)
    def save(path, value):
        raw = (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode()
        with path.open('xb') as f:
            f.write(raw)
        return pin(raw)
    out.mkdir()
    ap = save(ROOT / (base + 'run-authorization.json'), auth)
    rp = save(out / 'receipt.json', dict(sealed=True, passed=True, blocking_findings=[],
        input_pins=pins, before_after_equal=True, authorization=ap, sole_executor=executor,
        read_journal=ledger, selected_read_bytes=sum(r['bytes'] for r in ledger),
        manual_inspection_allowance=262144, source_limit=2 * 1024 * 1024,
        actual_runs=0, PE_engine_decoder_game_operations=0, author_programs_or_tests_run=0))
    print(json.dumps(dict(scope=number, authorization=ap, receipt=rp, selected_read_bytes=sum(r['bytes'] for r in ledger)), ensure_ascii=True))


one(78, 'work/reports/server-expected-owner-sample-data-20261016-r78/',
    dict(subject_source_manifest=pair(7700,'d1bce281e91ebca3ff60ce5a5b25acb1dfd91a4178e34acd5a66e1b9d4c10b33'),
        subject_producer=pair(18803,'eca07fe527f95f7db33094ff78f315571ca75bb238a7ebb4676e67e3d5aca2b3'),
        subject_entry_seed=pair(6277,'028f47b32044c1ca47f28c885379a9a69108fd4474157b3cfc7626c11b8ad0fc')),
    [
        ('raw_seed_review','server-expected-owner-sample-data-entry-review-20261016-r78',pair(2065,'85d5f0acb628c915d0ce32b60d3bf32e5fcd4aaf534153d586817259e3c69dd7'),pair(5502,'32b56473ad5d89009430cd25394bdec66281dbf2ff99a72599673050b104ba2e')),
        ('upstream_actual_review','server-expected-vtable-reference-owner-actual-independent-review-20261016-r1',pair(31999,'2e531e9efc7f130e3987fcda16c4fc277d2093ec2fe94f29ef37a0699007a070'),pair(25117,'92ec70f535d90d04fa46354ff4884e48c4ff4f3c80fe30c3af75b46cbe8c6edb')),
        ('source_peer_review','server-expected-owner-sample-data-source-independent-review-20261016-r78',pair(5428,'334b3d12d9575682da771139013dd85af79cf0f5b894f29f698f4807976b67c1'),pair(10956,'fe63125fbc8be143322ee613c816836a2a36de791cf49dd020b604eea07fbf4b')),
    ],
    'One fixed6B cached.rdata sample only;6 is sample budget not consumed length. No byte7/NULsearch/GUI/callee/othercue/header/pdata/code/vslot/unwind/decoder/process/game/UI/native/request/test. Two exact EXE SHA passes separate, rawmanifest and allthree review subjects before/after, normal filecontext exit before committed capture, exclusive attempt/no retry. Sealer4M is a successful post-read accounting assertion, not a failure-path pre-read hardstop.',
    'diplomacy_static')
one(79, 'work/reports/war-peace-api-20261016-r79-null-selector-callee/',
    dict(subject_source_manifest=pair(21830,'a6d3c5282e46c9ede2da9c6cfaee29edb584636941411714a081331bcd584ab8'),
        subject_producer=pair(24180,'29bb97220b025814190a858e36cc24ce67373ed27304e5e7c69e9d4aa013b978'),
        subject_entry_seed=pair(9256,'b1765705ff97112640173079605d3ab077837052be5c4cbeeeb85e71c59d4689')),
    [
        ('root_raw_entry_review','war-peace-api-20261016-r79-entry-independent-review',pair(2552,'8312198cdbe85db7b67f250ede4aedb31bf8de8d598a8b5f4716f068289b5370'),pair(5971,'34f51cec25ea88c8ed8b87832acee950a5a2c50f19de7eb9b57c8a9785b37646')),
        ('upstream_actual_review','war-peace-api-20261016-r69-actual-independent-review',pair(6300,'529f00a30baeba2c1f600018455c1e050f6061429951da8ce2daf9c44de17f56'),pair(13503,'bceee11bb0cc11bb648d0b2e8d65b9862df971ecc10e161118ee762e3acf8058')),
        ('source_peer_review','war-peace-api-20261016-r79-source-independent-review',pair(5645,'76b84b9b2315af87dde111f04f306f3cf5855bc25a5f9fa3ed93183499b8a9cc'),pair(14493,'b1c2be763ce00c1337a6bdeec1840afedd9620a33d161eb132cac2081c6e0da4')),
    ],
    'One disk-only exactcallee97bd30. At most32metadata12B, exactbegin/positiveextent/disjointneighbors; full<=8192elsefirst2048, unknown0code if missing/invalid/no fallback. No callees/RIPdata/vslots/neighborcode/header/unwind/process/game/UI/Frida/native/request/test follow. Rawmanifest authorizedbuffer-first/two basepins and initialouterchecks; twoEXESHA separate; normalclose plus postsource/auth/review before capture; exclusive claim/no retry. CALL return address is loadedbase+99358f; RDXD0 only precallstore.',
    'war_api')
