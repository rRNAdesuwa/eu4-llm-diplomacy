"""Offline synthetic contract only. No machine context acquisition or native calls."""
import json
import re

GPRS = tuple('rax rcx rdx rbx rsp rbp rsi rdi r8 r9 r10 r11 r12 r13 r14 r15'.split())
SITES = {'entry': 0x80b4c0, 'continuation': 0x803d2c}
MAX_PACKET = 16384
STAGES = ('entry_save', 'entry_recorder', 'relocated_prefix', 'engine_body',
          'continuation_save', 'continuation_recorder', 'restore')
FAULTS = ('recorder_fault', 'engine_exception', 'foreign_thread', 'reentry',
          'missing_return', 'ring_loss', 'unsupported_state')


class ContractError(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise ContractError(reason)


def keys(value, expected, label):
    require(type(value) is dict and all(type(k) is str for k in value)
            and set(value) == set(expected), label + ': exact keys')


def uint(value, bits, label, minimum=0):
    require(type(value) is int and minimum <= value < 1 << bits, label + ': integer')


def blob(value, length, label):
    require(type(value) is str and len(value) == length * 2
            and re.fullmatch('[0-9a-f]+', value) is not None, label + ': bytes')


def _unique(pairs):
    result = {}
    for k, v in pairs:
        require(k not in result, 'duplicate key')
        result[k] = v
    return result


def decode_packet(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_PACKET, 'packet bound')
    try:
        packet = json.loads(raw.decode('ascii'), object_pairs_hook=_unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(ContractError('constant')))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ContractError('invalid JSON') from exc
    validate(packet)
    return packet


def validate(s):
    keys(s, ('schema', 'site', 'module_base', 'thread', 'span', 'parent', 'generation',
             'rip', 'gpr', 'rflags', 'stack_top', 'xstate', 'thread_observables'), 'snapshot')
    require(s['schema'] == 'synthetic_c02_state_v1', 'synthetic schema')
    require(type(s['site']) is str and s['site'] in SITES, 'site')
    uint(s['module_base'], 47, 'module base', 0x10000)
    require(s['module_base'] % 0x10000 == 0, 'module alignment')
    uint(s['thread'], 32, 'thread', 1)
    for k in ('span', 'generation'):
        uint(s[k], 64, k, 1)
    uint(s['parent'], 64, 'parent')
    require(s['parent'] < s['span'], 'parent ordering')
    uint(s['rip'], 64, 'rip')
    require(s['rip'] == s['module_base'] + SITES[s['site']], 'original boundary PC')
    keys(s['gpr'], GPRS, 'gpr')
    for k, v in s['gpr'].items():
        uint(v, 64, k)
    uint(s['rflags'], 64, 'rflags')
    # This is an opaque synthetic value, NOT proof all these bits are user-restorable.
    require(s['gpr']['rsp'] % 16 == (8 if s['site'] == 'entry' else 0), 'boundary rsp alignment')
    require(0 < s['gpr']['rsp'] < (1 << 47) - 64, 'bounded synthetic stack address')
    blob(s['stack_top'], 64, 'stack observation')
    if s['site'] == 'entry':
        ret = int.from_bytes(bytes.fromhex(s['stack_top'][:16]), 'little')
        require(ret == s['module_base'] + SITES['continuation'], 'original return address')
    x = s['xstate']
    keys(x, ('profile', 'enabled', 'x87', 'sse', 'avx_upper'), 'xstate')
    require(x['profile'] in ('synthetic_legacy_sse', 'synthetic_avx'), 'unmodeled XSTATE profile')
    expected = ['x87', 'sse'] + (['avx_upper'] if x['profile'] == 'synthetic_avx' else [])
    require(type(x['enabled']) is list and x['enabled'] == expected, 'exact synthetic enabled components')
    f = x['x87']
    keys(f, ('control', 'status', 'tag', 'opcode', 'ip', 'dp', 'st'), 'x87')
    for k in ('control', 'status', 'tag', 'opcode'):
        uint(f[k], 16, 'x87 ' + k)
    for k in ('ip', 'dp'):
        uint(f[k], 64, 'x87 ' + k)
    require(type(f['st']) is list and len(f['st']) == 8, 'x87 count')
    for item in f['st']:
        blob(item, 10, 'x87 semantic value')
    keys(x['sse'], ('mxcsr', 'xmm'), 'sse')
    uint(x['sse']['mxcsr'], 32, 'mxcsr')
    require(type(x['sse']['xmm']) is list and len(x['sse']['xmm']) == 16, 'xmm count')
    for item in x['sse']['xmm']:
        blob(item, 16, 'xmm value')
    if x['profile'] == 'synthetic_avx':
        require(type(x['avx_upper']) is list and len(x['avx_upper']) == 16, 'avx count')
        for item in x['avx_upper']:
            blob(item, 16, 'upper ymm value')
    else:
        require(x['avx_upper'] is None, 'unexpected upper state')
    keys(s['thread_observables'], ('last_error', 'errno'), 'thread observables')
    uint(s['thread_observables']['last_error'], 32, 'last error')
    e = s['thread_observables']['errno']
    require(type(e) is int and -(1 << 31) <= e < (1 << 31), 'errno')


def compare_recorder(before, restored):
    """Same original PC, before/after recorder ONLY; no original instruction between."""
    validate(before)
    validate(restored)
    require(before == restored, 'recorder changed a modeled value or identity')
    return {'synthetic_modeled_equality': True, 'machine_capture_verified': False,
            'hook_supported': False, 'native_execution_authorized': False}


def correlate_return(entry, continuation):
    """Only the bounded C01 normal-return relation, not full callee emulation."""
    validate(entry)
    validate(continuation)
    require(entry['site'] == 'entry' and continuation['site'] == 'continuation', 'pair sites')
    for k in ('module_base', 'thread', 'span', 'parent', 'generation'):
        require(entry[k] == continuation[k], 'pair identity ' + k)
    require(continuation['gpr']['rsp'] == entry['gpr']['rsp'] + 8, 'normal return stack')
    require(continuation['gpr']['rax'] == entry['gpr']['rcx'], 'constructor return destination')
    return {'synthetic_normal_return_correlated': True, 'full_callee_emulated': False,
            'origin_witness_verified': False, 'hook_supported': False}


def exception_requirement(stage, fault):
    require(type(stage) is str and stage in STAGES, 'stage')
    require(type(fault) is str and fault in FAULTS, 'fault')
    return {'required_terminal_revocation': True, 'automatic_recovery_allowed': False,
            'engine_cleanup_by_observer_allowed': False, 'normal_return_event_allowed': False,
            'original_engine_exception_must_propagate': fault == 'engine_exception',
            'installed_exception_policy_verified': False,
            'recorder_fault_transparent_propagation_proved': False}
