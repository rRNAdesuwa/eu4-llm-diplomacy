"""Independent retained-file/raw arithmetic review. Never imports author code."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import hashlib
import json
import struct
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/war-peace-api-20261016-r62-independent-review'
SUBJECT = 'work/reports/war-peace-api-20261016-r62-gold-recipient-generator/'
SHA = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
M_SHA = 'd3516fdbc60b2c66115b9a0aa907daace7e5a8adac0c5dbd4c53f0840eba6db4'
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 24 * 1024 * 1024
MEMORY = 768 * 1024 * 1024
SNAP = 'work/reports/war-peace-api-20261016-r62-independent-review/retention-r2/retained-sources.json'

class PMC(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
        'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
        'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]

kernel = ctypes.WinDLL('kernel32', use_last_error=True)
psapi = ctypes.WinDLL('psapi', use_last_error=True)
kernel.GetCurrentProcess.restype = wintypes.HANDLE
psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
peak = 0
own_reads = []

def guard():
    global peak
    p = PMC()
    p.cb = ctypes.sizeof(p)
    assert psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(p), p.cb)
    peak = max(peak, p.PrivateUsage, p.WorkingSetSize, p.PeakWorkingSetSize, p.PeakPagefileUsage)
    assert peak <= MEMORY

def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def read(path, expected=None):
    guard()
    file = ROOT / path
    before = file.stat()
    assert before.st_size <= MAX_FILE, (path, before.st_size)
    raw = file.read_bytes()
    after = file.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    assert len(raw) == before.st_size
    actual = pin(raw)
    if expected is not None:
        assert actual == expected, (path, actual, expected)
    own_reads.append({'path': path, **actual})
    guard()
    return raw

def write(name, value):
    raw = ((json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode()
           if not isinstance(value, bytes) else value)
    assert len(raw) <= MAX_FILE
    with (OUT / name).open('xb') as f:
        f.write(raw)
    guard()
    return pin(raw)

def n(value):
    return int(value, 16) if isinstance(value, str) else value

def control_target(row):
    raw = bytes.fromhex(row['bytes'])
    site = n(row['rva'])
    if raw[0] in (0xe8, 0xe9):
        assert len(raw) == 5
        disp = struct.unpack('<i', raw[1:])[0]
    elif raw[0] == 0xeb or 0x70 <= raw[0] <= 0x7f:
        assert len(raw) == 2
        disp = struct.unpack('<b', raw[1:])[0]
    else:
        assert raw[0] == 0x0f and 0x80 <= raw[1] <= 0x8f and len(raw) == 6
        disp = struct.unpack('<i', raw[2:])[0]
    return site + len(raw) + disp

def raw_store_form(row):
    """Check retained opcode direction only; not a disassembler or engine invocation."""
    raw = bytes.fromhex(row['bytes'])
    i = 0
    while raw[i] in (0x66, 0xf2, 0xf3) or 0x40 <= raw[i] <= 0x4f:
        i += 1
    op = raw[i]
    if op == 0x0f:
        second = raw[i + 1]
        if second == 0x7f:
            return raw[i + 2] >> 6 != 3
        assert second in (0x1f, 0x57, 0xaf) or 0x80 <= second <= 0x8f
        return False
    if op in (0x89, 0x01):
        return raw[i + 1] >> 6 != 3
    if op in (0x81, 0x83):
        modrm = raw[i + 1]
        # Observed ADD/SUB/CMP. Only register ADD/SUB and memory ADD in this body.
        assert (modrm >> 3) & 7 in (0, 5, 7)
        return modrm >> 6 != 3 and (modrm >> 3) & 7 != 7
    assert op in (0x03, 0x2b, 0x33, 0x3b, 0x63, 0x69, 0x85, 0x8b, 0x8d,
                  0x99, 0xb8, 0xb9, 0xc1, 0xc3, 0xcc, 0xe8, 0xeb, 0xf7) or 0x50 <= op <= 0x5f or 0x70 <= op <= 0x7f, row
    return False

def main():
    retained_raw = read(SNAP)
    retained = json.loads(retained_raw)
    files = retained['files']
    for path, item in files.items():
        assert pin(bytes.fromhex(item['raw_hex'])) == {k: item[k] for k in ('bytes', 'sha256')}
    def raw(name):
        return bytes.fromhex(files[SUBJECT + name]['raw_hex'])
    def obj(name):
        return json.loads(raw(name))
    manifest = obj('manifest.json')
    assert pin(raw('manifest.json')) == {'bytes': 14300, 'sha256': M_SHA}
    assert manifest['sealed'] is True and manifest['game_sha256'] == SHA
    assert len(manifest['actual_file_pins']) == 35
    assert len(manifest['decoder_producer_authenticated_witness_pins']) == 38
    owned, selected, capture, contract = [obj(x) for x in
        ('owned-code.json', 'selected-evidence.json', 'capture.json', 'contract.json')]
    code = bytes.fromhex(owned['raw_hex'])
    assert len(code) == 684 and hashlib.sha256(code).hexdigest() == owned['sha256']
    assert owned['window'] == ['0x9844d0', '0x98477c'] and owned['full_extent_owned'] is True
    assert selected['raw_hex'] == owned['raw_hex'] and selected['raw_sha256'] == owned['sha256']
    assert selected['capture_pin'] == pin(raw('capture.json'))
    assert selected['owned_pin'] == pin(raw('owned-code.json'))
    rows = selected['instructions']
    assert len(rows) == 174
    cursor = 0x9844d0
    joined = bytearray()
    rowmap = {}
    for row in rows:
        at = n(row['rva'])
        rb = bytes.fromhex(row['bytes'])
        assert at == cursor and 1 <= len(rb) <= 15
        assert rb == code[at - 0x9844d0: at - 0x9844d0 + len(rb)]
        assert at not in rowmap
        rowmap[at] = row
        joined.extend(rb)
        cursor += len(rb)
    assert cursor == 0x98477c and bytes(joined) == code
    captured = capture['analysis']['instructions']
    assert len(captured) == len(rows)
    capmap = {n(r['rva']): r for r in captured}
    assert set(capmap) == set(rowmap)
    for at, r in rowmap.items():
        assert all(r[k] == capmap[at][k] for k in ('rva', 'bytes', 'mnemonic', 'operands'))
    expected_text = ''.join(f"{r['rva']} {r['bytes']} {r['mnemonic']} {r['operands']}\n" for r in rows)
    assert raw('disassembly.txt').decode() == expected_text
    calls = [r for r in rows if r['mnemonic'] == 'call']
    branches = [r for r in rows if r['mnemonic'].startswith('j')]
    assert len(calls) == 8 and len(branches) == 24
    targets = {}
    for r in calls + branches:
        target = control_target(r)
        assert n(r['operands']) == target
        targets[r['rva']] = hex(target)
    assert len({targets[r['rva']] for r in calls}) == 7
    assert [targets[r['rva']] for r in calls] == ['0x97b2c0', '0x975110', '0x993570',
        '0x996e30', '0x994f00', '0x17394f0', '0x996e30', '0x1a41c6c']
    edges = capture['analysis']['edges']
    assert len(edges) == 32
    assert {n(e['site']) for e in edges} == {n(r['rva']) for r in calls + branches}
    for edge in edges:
        r = rowmap[n(edge['site'])]
        t = control_target(r)
        assert n(edge['target_rva']) == t
        assert edge['inside_owned_window'] is (0x9844d0 <= t < 0x98477c)
        assert edge['callee_followed'] is False
        if r['mnemonic'] != 'jmp':
            assert n(edge['fallthrough']) == n(r['rva']) + len(bytes.fromhex(r['bytes']))
    # Independent finite local graph, with external calls assumed to return normally.
    successors = {}
    for at, r in rowmap.items():
        nxt = at + len(bytes.fromhex(r['bytes']))
        if r['mnemonic'] in ('ret', 'int3'):
            successors[at] = []
        elif r['mnemonic'] == 'jmp':
            successors[at] = [control_target(r)]
        elif r['mnemonic'].startswith('j'):
            successors[at] = [control_target(r), nxt]
        else:
            successors[at] = [nxt]
        assert all(dst in rowmap for dst in successors[at])
    pending = [0x9844d0]
    reachable = set()
    while pending:
        at = pending.pop()
        if at not in reachable:
            reachable.add(at)
            pending.extend(successors[at])
    assert len(reachable) == 174
    assert [r['rva'] for r in rows if r['mnemonic'] == 'ret'] == ['0x984775']
    assert [r['rva'] for r in rows if r['mnemonic'] == 'int3'] == ['0x98477b']
    # Raw opcode direction, independently of engine access metadata.
    stores = [r for r in rows if raw_store_form(r)]
    assert len(stores) == 21
    assert [r['rva'] for r in stores] == [r['rva'] for r in selected['explicit_store_rows']]
    stack_sites = [r['rva'] for r in stores if r['memory_operands'][0]['base'] == 'rsp']
    end_sites = [r['rva'] for r in stores if r['memory_operands'][0]['base'] == 'r14']
    payload_sites = [r['rva'] for r in stores if r['rva'] not in stack_sites + end_sites]
    assert len(stack_sites) == 13 and end_sites == ['0x984616', '0x98474a']
    assert payload_sites == ['0x984610', '0x984612', '0x9846c1', '0x9846c8', '0x984744', '0x984746']
    assert selected['store_counts'] == {'total': 21, 'stack': 13, 'output_header_end': 2, 'record_payload': 6}
    assert not [r for r in rows if any(m['base'] == 'rip' for m in r['memory_operands'])]
    # Selected instructions underpin machine semantics, not business/type inference.
    expected = {
        0x9844e5:'4883ec50', 0x9844e9:'4c8bf2', 0x9844ec:'488bf1',
        0x9844ef:'488d9424a0000000', 0x9844fc:'4863bc24a0000000',
        0x984504:'85ff', 0x984506:'0f8e52020000', 0x984511:'84c0',
        0x984519:'498b1e', 0x98451c:'0f57c0', 0x98451f:'f30f7f442438',
        0x984528:'4c897c2448', 0x98452d:'4c8d442438', 0x984532:'488d9424a8000000',
        0x98453a:'488bce', 0x984551:'4863b424a8000000', 0x984559:'85f6',
        0x984566:'492bc4', 0x984569:'48c1f802', 0x98456d:'490fafc1',
        0x984571:'4c63c0', 0x984579:'85c0', 0x984581:'48899c24a8000000',
        0x984589:'48897c2428', 0x98459b:'4c8ba42490000000',
        0x9845b0:'498b5d04', 0x9845b4:'49634d00', 0x9845b8:'480fafcf',
        0x9845bc:'48f7e9', 0x9845bf:'48c1fa07', 0x9845c3:'488bc2',
        0x9845c6:'48c1e83f', 0x9845ca:'4803d0', 0x9845cd:'8d8273931800',
        0x9845d3:'3d0d583900', 0x9845da:'69c2e8030000', 0x9845e0:'99',
        0x9845e1:'f7fe', 0x9845e3:'8be8', 0x9845e7:'4863c2',
        0x9845ea:'4869c0e8030000', 0x9845f1:'4899', 0x9845f3:'48f7fe',
        0x9845f6:'488be8', 0x9845f9:'85ed', 0x9845fb:'7e3f',
        0x984606:'498b5608', 0x98460a:'493b5610', 0x984639:'4403fd',
        0x98463c:'498b442418', 0x984641:'48c1e820', 0x984645:'48c1eb20',
        0x984649:'663bd8', 0x984660:'85c0', 0x984664:'488d59f4',
        0x98467a:'4983c50c', 0x98467e:'4983e801', 0x984682:'4c89442420',
        0x984691:'0f8519ffffff', 0x984697:'8bbc24a0000000',
        0x9846a3:'413bff', 0x9846be:'412bff', 0x9846c1:'0139',
        0x9846c5:'412bff', 0x9846c8:'013b', 0x9846ca:'488d9424a0000000',
        0x9846d2:'498bce', 0x9846e9:'488b442448', 0x984711:'4d8b6424f8',
        0x984723:'498bcc', 0x98472d:'897c2428', 0x984731:'488b4618',
        0x984735:'488944242c', 0x984744:'893a', 0x984746:'48894204',
        0x984766:'4883c450', 0x984775:'c3', 0x98477b:'cc'}
    for at, value in expected.items():
        assert rowmap[at]['bytes'] == value, hex(at)
    # Stack mapping and uninitialized local cells: explicit stores before the calls.
    assert sum(r['mnemonic'] == 'push' for r in rows) == 7
    steady_delta = -7 * 8 - 0x50
    assert steady_delta == -0x88
    assert steady_delta + 0x90 == 8 and steady_delta + 0x98 == 0x10
    assert steady_delta + 0xa0 == 0x18 and steady_delta + 0xa8 == 0x20
    assert not [r for r in stores if n(r['rva']) < 0x9844f7 and
                r['memory_operands'][0]['base'] == 'rsp' and
                r['memory_operands'][0]['displacement'] == 0xa0]
    assert not [r for r in stores if n(r['rva']) < 0x98453d and
                r['memory_operands'][0]['base'] == 'rsp' and
                r['memory_operands'][0]['displacement'] == 0xa8]
    # Metadata is replayed from retained bytes, never from PE.
    pdata = capture['pdata_requests']
    assert len(pdata) == 19 and len({r['index'] for r in pdata}) == 16
    for r in pdata:
        b, e, u = struct.unpack('<III', bytes.fromhex(r['raw_hex']))
        assert (b, e, u) == (n(r['begin_rva']), n(r['end_exclusive']), n(r['unwind_rva']))
        assert b < e
    chosen = capture['selected']
    assert chosen['index'] == 19115 and chosen['raw_hex'] == 'd04498007c4798003cc9e701'
    assert n(chosen['begin_rva']) == 0x9844d0 and n(chosen['end_exclusive']) == 0x98477c
    anchors = json.loads(bytes.fromhex(files['work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json']['raw_hex']))
    sections = anchors['sections']
    def offset(rva, size):
        for sec in sections:
            # The original cached mapping's keys are checked by the existing seed/source review.
            va = n(sec['rva'])
            rs = sec['raw_size']
            if va <= rva and rva + size <= va + rs:
                return sec['raw_file_offset'] + rva - va
        raise AssertionError(('unmapped_retained_rva', hex(rva), size))
    assert offset(0x9844d0, 684) == owned['file_offset'] == 9976016
    for r in pdata:
        assert offset(n(r['rva']), 12) == r['file_offset']
    # Source/engine records are producer witnesses; no engine file is reopened here.
    base = obj('source-manifest.json')
    assert len(base['actual_source_pins']) == 13 and len(base['decoder_expected_witness_pins']) == 38
    assert capture['source_pins'] == base['source_pins']
    assert capture['source_engine_before_after_equal'] is True
    for path, expected_pin in base['actual_source_pins'].items():
        assert {k:files[path][k] for k in ('bytes','sha256')} == expected_pin
    assert manifest['decoder_producer_authenticated_witness_pins'] == base['decoder_expected_witness_pins']
    source_journal = capture['source_file_reads']
    assert sum(e['bytes'] for e in source_journal) == capture['source_file_read_bytes'] == 16403116
    for phase in ('source_engine_before', 'source_engine_after'):
        relevant = [e for e in source_journal if e['phase'] == phase]
        for path, expected_pin in base['source_pins'].items():
            matching = [e for e in relevant if e['path'].replace('\\', '/').endswith('/'+path)]
            assert matching and all(e['bytes'] == expected_pin['bytes'] for e in matching), (phase, path)
    for h in capture['full_PE_authentication_reads']:
        assert h['bytes_read'] == 38462504 and h['completed'] is True and h['sha256'] == SHA
    assert len(capture['full_PE_authentication_reads']) == 2
    assert capture['total_PE_physical_bytes'] == 2 * 38462504 + 19 * 12 + 684 == 76925920
    assert capture['pdata_physical_bytes'] == 228 and capture['pdata_unique_bytes'] == 192
    sparse = capture['sparse_reads']
    assert len(sparse) == 20 and sum(r['bytes'] for r in sparse) == 228 + 684
    assert [r['bytes'] for r in sparse if r['kind'] == 'single_entry_code'] == [684]
    look = capture['analysis']['lookahead_inputs']
    assert len(look) == 174 and sum(r['bytes'] for r in look) == 2557
    look_union = set()
    for r in look:
        assert n(r['rva']) in rowmap and r['bytes'] == min(15, 0x98477c - n(r['rva']))
        look_union.update(range(n(r['rva']), n(r['rva'])+r['bytes']))
    assert len(look_union) == 684 and 2557 - len(look_union) == 1873
    receipt = obj('acquisition-receipt.json')
    stdout = obj('producer.stdout.json')
    assert stdout['capture_pin'] == pin(raw('capture.json'))
    assert receipt['exit_code'] == 0 and receipt['direct_owned_child_collected'] is True
    assert receipt['automatic_retry'] is False and receipt['elapsed_ns'] == 431429100
    assert receipt['hard_Job_installed'] is False and capture['hard_Job_installed'] is False
    assert receipt['stdout'] == pin(raw('producer.stdout.json'))
    assert receipt['stderr'] == pin(raw('producer.stderr.txt'))
    assert receipt['wrapper_explicit_file_read_bytes'] == sum(e['bytes'] for e in receipt['wrapper_file_read_journal'])
    delivery, delta = obj('actual-delivery.json'), obj('actual-delivery-accounting-delta.json')
    assert delta['subject_delivery'] == pin(raw('actual-delivery.json'))
    assert delivery['last_delivery_read_bytes'] == sum(x['bytes'] for x in delivery['last_delivery_pin_reads']) == 486509
    for name, expected_pin in delivery['file_pins'].items():
        assert expected_pin == pin(raw(name))
    assert delta['additional_explicit_bytes'] == sum(e['bytes'] for e in delta['additional_explicit_reads']) == 204263
    assert delta['corrected_retained_seal_check_delivery_explicit_bytes'] == 2419919 + 204263 == 2624182
    assert 16403116 + len(raw('capture.json')) == 16601838
    assert delta['corrected_combined_producer_retained_delivery_explicit_source_bytes'] == 16601838 + 2624182 == 19226020
    assert 19226020 < delta['combined_budget'] == 48 * 1024 * 1024
    assert capture['peak_committed_bytes_observed'] == 24289280 < capture['memory_guard_bytes'] == MEMORY
    # All data/semantic/call permissions stay false after an author-side static capture.
    assert all(v is False for v in contract['authority'].values())
    for name in ('native_ready','callable','reader_adoption_allowed','selected_effect_verified',
                 'amount_units_verified','recipient_direction_verified','world_lease',
                 'atomic_snapshot','authorizes_retry'):
        assert capture[name] is False
    assert capture['new_header_data_literal_vtable_unwind_callee_bytes'] == 0
    assert all(capture[x] == 0 for x in ('game_process_accesses','Frida_operations','native_game_calls','requests','tests'))
    seed = obj('entry-seed.json')
    assert bytes.fromhex(seed['raw_call'])[0] == 0xe8
    assert n(seed['call_site_rva']) + 5 + struct.unpack('<i', bytes.fromhex(seed['raw_call'])[1:])[0] == 0x9844d0
    assert seed['XMM0_at_call'] == 'all128bits_zero_by_XORPS_at9b4064'
    # Explicit modulo/signed width formulas from the retained instructions.
    integer_contract = {
        'temporary_count':'s32(low32(low64(sar64(submod64(E,B),2)*0xaaaaaaaaaaaaaaab)))',
        'record_a':'s64(s32(load32(record+0)))', 'record_q':'unaligned load64(record+4), copied bitwise',
        'P':'low64(record_a*T)', 'V':'sar64(signed_high64(0x20c49ba5e353f7cf*P),7)',
        'L':'low64(V+logical_shr64(V,63))', 'k':'s32(low32(L))',
        'fast_gate':'u32(k+0x189373)<=0x39580d',
        'fast':'IMUL32(k,1000); CDQ; IDIV32(D); EBP=quotient; 32bit write zeroextends RBP',
        'slow':'s64(k)*1000; CQO; IDIV64(s64(D)); RBP=quotient',
        'append_gate':'s32(low32(RBP))>0, not full64 quotient range validation',
        'sum':'R15D=addmod32(R15D,EBP)',
        'slot_compare':'u16(q>>32)==u16(fresh load64(W+0x18)>>32), no fullhandle comparison',
        'candidate_nonempty':'low32(transformed current output span)!=0, no positive count or typed proof',
        'remainder_gate':'s32(EDI)>s32(R15D)', 'remainder_value':'submod32(EDI,R15D)',
        'remainder_write':'ADD32 candidate record DWORD, or first record DWORD when nonempty',
        'loop':'R13+=12; R8 full64 decrement; MOVs preserve SUB flags until JNE; 996e30 path reloads R8 from stack20',
        'guarded_limit':'Only normal external returns, valid readable/writable memory and appropriate ABI/stack discipline. Callee aliases may change data/headers; no world lifetime.'}
    raw_review = {'schema':'EU4-R62-INDEPENDENT-RAW-REVIEW/1','sealed':True,
        'subject_manifest':pin(raw('manifest.json')),'full_raw_byte_match':True,
        'rows':rows,'bytes':684,'calls':selected['calls'],'branches':selected['branches'],
        'control_targets_recomputed':targets,'recorded_control_edges':32,
        'independent_local_successors':{hex(k):[hex(x) for x in v] for k,v in successors.items()},
        'possible_local_reachable_rows_under_normal_external_returns':174,
        'normal_RET':'0x984775','INT3':'0x98477b','all_execution_normal':False,
        'explicit_store_sites':{'stack':stack_sites,'output_header_end':end_sites,'record_payload':payload_sites},
        'implicit_push_call_RET_stack_access_excluded_from_explicit_store_count':True,
        'steady_rsp_minus_entryQ':steady_delta,'T_address_Q_plus':0x18,'D_address_Q_plus':0x20,
        'T_D_not_locally_initialized_before_their_calls':True,'callee_writes_outparams_proved':False,
        'integer_machine_contract':integer_contract,
        'pdata_physical_records':19,'pdata_unique_records':16,'pdata_physical_bytes':228,
        'full_loaded_bytes_verified':False,'live_inputs_authenticated':False,
        'decoder_engine_opened':False,'PE_opened':False,'native_calls':0}
    raw_review_pin = write('raw-review.json', raw_review)
    # Independent postguard of the same 41 retained subject/control sources, no engine closure expansion.
    for path, item in files.items():
        read(path, {k:item[k] for k in ('bytes','sha256')})
    guard()
    own_explicit_known = retained['source_physical_bytes'] + 4*len(retained_raw) + sum(x['bytes'] for x in own_reads)
    # Four prior inspection invocations read this owned snapshot, separately from subject reads.
    assert own_explicit_known < MAX_TOTAL
    precision = [
        '13 stack stores count explicit instructions only; PUSH/CALL/RET implicit stack accesses remain.',
        '32 recorded edges count control-transfer records with conditional fallthrough fields, not every graph successor.',
        'T/D are post-call cell reads. No pre-call local initialization or actual helper out-write is inferred.',
        'The tail 994f00 may replace/mutate H or records. Intermediate record writes do not prove final recipients or conservation.',
        '16-bit comparison establishes no complete handle/generation/country identity; R9 magic is restored on the append-helper return path.',
        'Source/PE/engine and resource execution facts are authenticated retained producer witnesses, not rerun by this review.',
        'The source accounting delta corrects two omitted retained reads; its original delivery remains immutable.',
        'RAX is not normalized as a new balance/BOOL/count; the caller immediately reloads its own header end.',
    ]
    findings = {'schema':'EU4-R62-INDEPENDENT-FINDINGS/1','sealed':True,'passed':True,
        'scope':'full retained-file/raw arithmetic and semantic-boundary review, no author execution',
        'subject_manifest':pin(raw('manifest.json')),'subject_contract':pin(raw('contract.json')),
        'blocking_findings':[],'author_frozen_sources_need_change':False,'raw_review':raw_review_pin,
        'verified':{'actual_pins':35,'extra_accounting_files':5,'engine_witness_metadata_pins_unopened':38,
            'rows':174,'unique_code_bytes':684,'CALL_sites':8,'CALL_targets':7,
            'branches':24,'recorded_control_edges':32,'RET_sites':1,'INT3_sites':1,
            'explicit_stores':{'stack':13,'output_header_end':2,'record_payload':6},
            'full_raw_coverage':True,'call_and_branch_rel32_rel8_arithmetic':True,
            'finite_local_CFG_replay':True,'GP_stack_integer_alias_loop_review':True,
            'cached_section_and_pdata_arithmetic':True,'producer_accounting_replayed':True,
            'original_source_postguard_equal':True},
        'semantics':{'inputRCX':'opaque W','inputRDX':'opaque output header H',
            'first_T':'post97b2c0 signed DWORD at Q+18; signed-positive gate',
            'second_D':'post993570 signed DWORD at Q+20; signed-positive gate',
            'simple_record':'DWORD low32(T), fresh QWORD [W+18]',
            'complex_record':'transformed signed DWORD component and same bitwise QWORD+4',
            'integer':integer_contract,'final_output_after994f00':'unknown',
            'types_currency_units_direction_complete_recipients':'unknown',
            'callee_cleanup_allocator_exception_ownership':'unknown'},
        'precision_notes':precision,
        'author_resource_witness':{'source_engine_journal_through_capture':16403116,
            'stdout_capture_pin_read':198722,'producer_plus_stdout_capture_pin':16601838,
            'retained_with_correction':2624182,'combined_explicit_source_stages':19226020,
            'combined_budget':50331648,'PE_separate':76925920,'PE_twoSHA':76925008,
            'target_pdata':228,'target_code':684,'decoder_input_total':2557,
            'decoder_input_unique':684,'decoder_overlap':1873,'observed_committed_peak':24289280,
            'elapsed_ns':431429100,'elapsed_scope':receipt['elapsed_scope'],
            'hard_Job_installed':False,'direct_child_collected_exit0':True,
            'not_all_OS_IO_or_tree_memory_proof':True},
        'independent_review_resources':{'initial_subject_retention_ledger_bytes':retained['source_physical_bytes'],
            'prior_owned_snapshot_inspections':4,'owned_snapshot_bytes':len(retained_raw),
            'current_explicit_reads':sum(x['bytes'] for x in own_reads),
            'known_explicit_data_reads_before_output_sealing':own_explicit_known,
            'software_memory_guard':MEMORY,'self_peak_bytes':peak,
            'source_file_cap':MAX_FILE,'source_budget':MAX_TOTAL,
            'read_scope':'listed source/owned snapshot bytes; interpreter/tool-source loading and later own seal pin loop separately excluded'},
        'self_diagnostic':{'retention_r1':'actual_file_pins dict mistaken for list; preserved TypeError before source pin iteration',
            'retention_r2':'only dict path/pin iteration, no author change/PE/decoder',
            'all_shells_collected':True},
        'operations':{'PE_reads':0,'engine_opens':0,'decoder_imports':0,'author_program_runs':0,
            'old_tests':0,'game_process_accesses':0,'Frida':0,'native_calls':0,'requests':0},
        'authority':{k:False for k in ('native_ready','callable','reader_adoption_allowed',
            'selected_effect_verified','amount_units_verified','recipient_direction_verified',
            'complete_gold_transfer_verified','world_lease','atomic_snapshot','authorizes_retry')},
        'next_scope_auto_authorized':False}
    findings_pin = write('findings.json', findings)
    write('postguard-ledger.json', {'schema':'EU4-R62-INDEPENDENT-POSTGUARD/1','reads':own_reads,
        'bytes':sum(x['bytes'] for x in own_reads),'self_peak_bytes':peak,
        'original_source_postguard_equal':True,'engine_opened':False,'PE_opened':False})
    report = ('# R62 independent retained-file review\n\n'
        'Passed with no blocking discrepancy; frozen author files need no change. All 174 rows/684 bytes, '
        '8 CALL sites, 24 branches, the RET/INT3 split and 21 explicit stores were independently replayed.\n\n'
        'The first and second scalars are reads after unknown callees, not proven outputs of those callees. '
        'The body forms 12-byte DWORD/QWORD records. Complex arithmetic checks signed low32 EBP, accumulates '
        'and adds remainders modulo32, compares only 16-bit slots, and invokes unknown 994f00 after the writes. '
        'Final recipients, gold units/direction, handle identity and cleanup ownership remain unknown.\n\n'
        'Producer source accounting is 16,403,116 + 198,722 + corrected retained 2,624,182 = 19,226,020 bytes. '
        'PE 76,925,920 bytes and the 38 unopened decoder witness pins are separate. The elapsed 431.4291 ms '
        'and 24,289,280-byte peak are retained producer witnesses, not runtime API/HTTP evidence.\n\n'
        'Own preliminary loader TypeError is retained; its R2 only fixes dictionary iteration. '
        'No PE, engine, author program, tests, game, Frida or native call was run. '
        'All callable/effect/reader/lease/retry permissions remain false.\n').encode()
    write('report.md', report)
    print(json.dumps({'passed':True,'findings':findings_pin,'raw_review':raw_review_pin,
        'known_explicit_bytes':own_explicit_known,'self_peak_bytes':peak}))

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        guard()
        with (OUT / 'semantic-review-failure.json').open('xb') as f:
            f.write((json.dumps({'type':type(exc).__name__,'detail':str(exc),
                'own_reads':own_reads,'self_peak_bytes':peak}, indent=2)+'\n').encode())
        raise
