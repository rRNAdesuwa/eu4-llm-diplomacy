"""Pure source/owned-byte review of the current-child reader; never RPM."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import struct
import types

ROOT = Path(__file__).resolve().parents[1]
CAND = ROOT / 'work/candidates/child-context-observer-1375-v1'
STATIC = ROOT / 'work/reports/war-peace-api-20261015-r15-child-context/war'
RECEIPTS = ROOT / 'work/reports/war-peace-api-20261015-r16-child-current'
OUT = ROOT / 'work/reports/current-child-reader-review-20261015-r1'


def pin(path):
    sha = hashlib.sha256()
    count = 0
    with path.open('rb') as stream:
        while raw := stream.read(65536):
            count += len(raw)
            sha.update(raw)
    return {'bytes': count, 'sha256': sha.hexdigest()}


def load(path):
    assert path.stat().st_size <= 1024 * 1024
    return json.loads(path.read_text(encoding='utf-8'))


def write_new(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(value if isinstance(value, str) else json.dumps(value, indent=2) + '\n')


class Owned:
    """Independent literal map, not built from the reader's PLAN or its tests."""
    def __init__(self):
        self.base = b = 0x140000000
        self.outer, self.game, self.server = o, g, s = 0x200000, 0x300000, 0x400000
        self.context, self.transport = c, t = 0x600000, 0x700000
        self.data = {}
        for a, v in ((b+0x242bf50,o),(b+0x233fe78,g),(o,b+0x1c48bf8),
                     (o+0x10,b+0x1c48c80),(g,b+0x1cb00c8),(o+0x40,s),
                     (g+0x1e00,s),(s,b+0x1cb8460),(s+0x330,o),(o+0x360,0x500000),
                     (o+0x370,c),(c,b+0x1d8c900),(c+0x58,t),(t,b+0x1d96178),
                     (t+0x70,c),(b+0x1cb8460+0x80,b+0x811aa0),
                     (b+0x1d8c900,b+0x14c88f0),(b+0x1d96178,b+0x15800d0),
                     (b+0x1d96178+0x30,b+0x1580370)):
            self.q(a,v)
        for a, v in ((c+0x55,255),(c+0x80d,128),(c+0x7d4,254),(c+0x841,253)):
            self.data[a,1] = bytes([v])
        self.data[c+0x68,4] = struct.pack('<i',-2147483648)
        self.data[c+0x8c,4] = struct.pack('<I',0xffffffff)
        self.calls = []
    def q(self,address,value):
        self.data[address,8] = struct.pack('<Q',value)
    def read(self,address,size):
        self.calls.append((address,size))
        return self.data[address,size]


def check():
    manifest = load(OUT / 'manifest.json')
    assert manifest['sealed'] is True
    for name, expected in manifest['source_pins'].items():
        assert pin(ROOT / name) == expected, name
    print(json.dumps({'status':'pass','pins':len(manifest['source_pins']),
                      'process_read':False,'tests_reexecuted':False}))


def main():
    assert pin(CAND/'reader.py') == {'bytes':4962,'sha256':'002ae678831a5e62de245206fba2e5ed5d473739ec980486125fa5a1b0efda8a'}
    assert pin(CAND/'test_reader.py') == {'bytes':4572,'sha256':'65ebeeb266148127d9b918aed4488034a1f93f90a086fa9aeeced6eee627f6fc'}
    assert pin(STATIC/'current-read-contract.json') == {'bytes':11344,'sha256':'829cc4b59c2610c47503821b2cb04cc3c70576eb6787f1ea711fa7e4d7599e07'}
    raw = (CAND/'reader.py').read_bytes()
    tree = ast.parse(raw)
    imports = [n for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom))]
    assert len(imports) == 1 and isinstance(imports[0],ast.Import)
    assert [n.name for n in imports[0].names] == ['struct']
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
    assert not attrs.intersection({'write','write_bytes','write_text','open','system','Popen','ReadProcessMemory','WriteProcessMemory'})
    module = types.ModuleType('independent_owned_child_reader')
    exec(compile(raw,str(CAND/'reader.py'),'exec'),module.__dict__)
    contract = load(STATIC/'current-read-contract.json')
    rows = contract['root_reads'] + contract['core_child_reads'] + contract['sender_diagnostic_reads']
    assert len(rows) == len(module.PLAN) == 25
    for selected, proof in zip(module.PLAN,rows):
        name, receiver, offset, size, kind, expected = selected
        assert name == proof['name'] and receiver == ('base' if proof['receiver']=='module_base' else proof['receiver'])
        assert offset == int(proof['offset'],16) and size == proof['size']
        if expected is not None:
            assert proof['expected'].startswith('module_base+0x')
            assert expected == int(proof['expected'].split(';')[0].split('+')[1],16)
    assert sum(r[3] for r in module.PLAN) == 164
    assert module.PLAN[21][4] == 'int32' and module.PLAN[22][4] == 'uint32'
    initial, delta = load(RECEIPTS/'initial-tests.json'),load(RECEIPTS/'test-delta.json')
    assert initial['exit_code'] == 1 and initial['passed_methods'] == 3
    assert initial['source_pins']['reader.py'] == pin(CAND/'reader.py')
    assert delta['exit_code'] == 0 and delta['methods_rerun'] == 1
    assert delta['reader_sha256'] == pin(CAND/'reader.py')['sha256']
    assert delta['tests_sha256'] == pin(CAND/'test_reader.py')['sha256']
    cases = []
    authority = ('sender_authorized','native_ready','lifetime_lease','atomic_snapshot',
                 'native_entry_authenticated','diagnostics_are_predicate_results',
                 'endpoint_code_bytes_verified','owner_reference_or_lock_acquired')
    def run(label, fixture, status, count, base=None):
        r = module.sample(fixture,fixture.base if base is None else base)
        assert r['status'] == status,(label,r)
        assert len(fixture.calls) == r['requested_reads'] == count,(label,r)
        assert sum(s for _,s in fixture.calls) == r['requested_bytes'] <= 164
        assert all(type(a) is int and type(s) is int and 0 < s <= 8 and module.MIN <= a < a+s <= module.MAX for a,s in fixture.calls)
        assert all(r[k] is False for k in authority)
        assert r['native_game_calls'] == r['game_fields_written'] == 0
        for row in r['reads']:
            assert bytes.fromhex(row['raw_hex']) == fixture.data[int(row['address'],16),row['size']]
        cases.append({'name':label,'status':status,'reads':count,'requested_bytes':r['requested_bytes'],
                      'exact_bytes':r['exact_bytes'],'authority_flags_false':True})
        return r
    f=Owned();r=run('arbitrary_byte_flags_signed_min_uint_max',f,'typed_context_transport_observed',25)
    assert [r['fields'][k] for k in ('sender_flag55','sender_flag80d','dispatch_flag7d4','dispatch_flag841')] == [255,128,254,253]
    assert r['fields']['command_word_source68'] == -2147483648 and r['fields']['command_dword_source8c'] == 0xffffffff
    for label, slot, value, count in (
        ('context_null',lambda f:f.outer+0x370,0,11),
        ('transport_null',lambda f:f.context+0x58,0,13),
        ('current_server_alias_mismatch',lambda f:f.game+0x1e00,0x410000,7),
        ('fresh_holder_alias_mismatch',lambda f:f.server+0x330,0x210000,9),
        ('context_type_stops_before_transport',lambda f:f.context,0x140000000+0x1d8c908,12),
        ('transport_type_stops_before_backlink',lambda f:f.transport,0x140000000+0x1d96180,14),
        ('backlink_stops_before_endpoints',lambda f:f.transport+0x70,0x610000,15),
        ('unaligned_context_stops_before_vtable',lambda f:f.outer+0x370,0x600001,11),
    ):
        f=Owned();f.q(slot(f),value)
        run(label,f,'context_absent' if label=='context_null' else 'transport_absent' if label=='transport_null' else 'unknown',count)
    f=Owned();f.q(f.outer+0x370,module.MAX-8);f.q(module.MAX-8,f.base+0x1d8c900)
    run('valid_final_qword_then_child_addition_overflow',f,'unknown',12)
    assert module.span(module.MAX-8,8) == module.MAX-8
    for label,base in (('bool_base',True),('float_base',1.0),('canonical_base_but_global_addition_overflow',module.MAX-8)):
        run(label,Owned(),'unknown',0,base)
    f=Owned();f.data[f.context+0x58,8]=bytearray(8)
    run('bytearray_not_exact_bytes',f,'unknown',13)
    f=Owned();f.data[f.context+0x58,8]=b'\0'
    r=run('short_child_pointer',f,'unknown',13);assert r['exact_bytes']==96
    original = module.PLAN
    try:
        module.PLAN = original + (('extra','base',0,1,'uint8',None),)
        run('call_budget_refuses_26th_before_callback',Owned(),'unknown',25)
        module.PLAN = tuple((f'budget{i}','base',0x100+8*i,8,'pointer',None) for i in range(21))
        f=Owned()
        for i in range(21):f.q(f.base+0x100+8*i,module.MIN)
        run('byte_budget_refuses_168th_byte_before_callback',f,'unknown',20)
    finally:
        module.PLAN=original
    # A read callback is a trusted interface. The reader intentionally catches
    # the listed ordinary read/validation exception classes, not BaseException.
    # Test the actual OSError read-failure contract without touching any API.
    class Failed(Owned):
        def read(self,address,size):
            if address==self.context+0x58:
                self.calls.append((address,size));raise OSError('synthetic exact-read failure')
            return super().read(address,size)
    run('ordinary_read_failure_unknown',Failed(),'unknown',13)
    report = {
        'schema':'EU4-CURRENT-CHILD-READER-INDEPENDENT-SOURCE-REVIEW/1',
        'status':'source_ready_selected_contract','findings':[],
        'reader':pin(CAND/'reader.py'),'tests':pin(CAND/'test_reader.py'),
        'R15_contract':pin(STATIC/'current-read-contract.json'),
        'contract_rows_matched':25,'complete_pass_reads':25,'complete_pass_bytes':164,
        'independent_owned_cases':cases,'independent_case_count':len(cases),
        'author_test_receipts_reused':{'initial_methods':4,'initial_passed':3,
            'initial_fixture_failure_preserved':True,'fixed_fixture_methods_rerun':1,
            'reader_unchanged':True,'tests_reexecuted_by_reviewer':False},
        'source_boundaries':{'only_import':'struct','only_memory_interface':'injected reader.read(address,size)',
            'span_and_budgets_checked_before_callback':True,'object_type_before_specific_child':True,
            'fresh_required_aliases_checked':True,'null_stop_before_dereference':True,
            'signed68_and_uint8_raw_preserved':True,'flags_are_not_health_or_native_gate':True,
            'endpoint_slots_read_not_called':True},
        'limits':[
            'Review imports only the exact pinned pure reader, using owned synthetic addresses and bytes. No process reader, producer, Frida, REA or game is invoked.',
            'This is one fresh-chain pass only. The parent producer must independently authenticate process/creation/module/base/source/code before and after, take two fresh passes and compare their complete projections.',
            'Unsupported/null/type/required-alias/read/budget paths preserve false authority flags. Arbitrary unproven all-objects-distinct constraints are not added.',
            'Sample catches ValueError/TypeError/KeyError/OverflowError/OSError/struct.error. A callback raising an unrelated exception is outside this narrow callback exception contract; the host must retain failure/cleanup handling.',
            'Reading endpoint pointers does not verify endpoint code bytes or execute them. Matching current roots/types/backlinks and equal future passes do not create an owner reference, lock, lease, atomicity or sender permission.',
            'Static R15 instruction/callee correctness is delegated to the separately requested war review; this review matches its fixed data contract and does not decode or reopen the executable.'
        ],
        'new_decode_bytes':0,'process_read':False,'Frida_called':False,'REA_called':False,
        'native_ready':False,'sender_authorized':False,'lifetime_lease':False,
        'atomic_snapshot':False,'native_entry_authenticated':False,'new_API_effects':0,
    }
    assert not OUT.exists();OUT.mkdir(parents=True)
    write_new(OUT/'independent-source-ready.json',report)
    write_new(OUT/'independent-source-ready.md',
        '# 当前 C/T reader 独立源码审查\n\n通过，未发现阻断问题。25 项读取与固定 R15 合同逐项一致；单遍最多 25 reads / 164B。'
        f'独立执行 {len(cases)} 个纯字节案例，覆盖地址加法越界、类型先行、NULL 停止、当前必需等值、backlink、短读/非 bytes、读次数和字节预算。\n\n'
        'uint8=255/128/254/253、signed32 最小值及 uint32 最大值保留原编码，不解释为健康或调用 gate。原作者 3 pass + 1 fixture 修复后的 delta pass 回执保留，未重跑四个旧方法。\n\n'
        '只审 exact pinned 纯 reader。宿主仍须做身份/源/代码前后核验、两遍 fresh roots 与全投影一致性，异常清理由宿主兜底；当前未运行 RPM producer。所有权限、租约、原子性及 native_ready 保持 false。\n')
    selected = [CAND/'reader.py',CAND/'test_reader.py',STATIC/'current-read-contract.json',STATIC/'manifest.json',
                RECEIPTS/'initial-tests.json',RECEIPTS/'test-delta.json',Path(__file__).resolve(),
                OUT/'independent-source-ready.json',OUT/'independent-source-ready.md']
    write_new(OUT/'manifest.json',{'schema':'EU4-CURRENT-CHILD-READER-INDEPENDENT-REVIEW-MANIFEST/1','sealed':True,
        'source_pins':{p.relative_to(ROOT).as_posix():pin(p) for p in selected}})
    print(json.dumps({'status':report['status'],'cases':len(cases),
                      'report':pin(OUT/'independent-source-ready.json'),
                      'manifest':pin(OUT/'manifest.json')}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    check() if args.check else main()
