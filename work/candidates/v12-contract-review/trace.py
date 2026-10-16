"""Bounded disk-only evidence for v11 coalition factory-contract failure."""
from __future__ import annotations
import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'work'))
from discover_diplomacy import PE, check_memory_budget, make_disassembler

SHA = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
INPUT = ROOT / 'work/reports/native-pair-extension-v11-1375.json'
INPUT_SHA = 'ac4559379e218aaf1fa8ffc1dd7dc6b8332ed5b7bf681c4b66bfc59349944344'
QUEUE = ROOT / 'work/reports/native-coalition-queue-1375.json'
QUEUE_SHA = 'b36c788c3eeb589abaa208df83cb3f97bf3697023188149588b41bb60dde5b65'


def main():
    raw = INPUT.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == INPUT_SHA
    source = json.loads(raw)
    pe = PE(ROOT.parent / 'eu4.exe')
    assert hashlib.sha256(pe.data).hexdigest() == SHA
    md, _ = make_disassembler(Path(os.environ['TEMP']) / 'eu4-native-analysis-deps')
    assert md is not None
    queue_raw = QUEUE.read_bytes()
    assert hashlib.sha256(queue_raw).hexdigest() == QUEUE_SHA
    queue = json.loads(queue_raw)
    queue_verified_bytes = 0
    for function in queue['functions'].values():
        for row in function['instructions']:
            raw = bytes.fromhex(row['bytes'])
            assert pe.bytes_at(int(row['rva'],16), len(raw)) == raw
            queue_verified_bytes += len(raw)
    slices = {}

    def decode(start, size, stop=True):
        assert 0 < size <= 512
        result = []
        for ins in md.disasm(pe.bytes_at(start, size), start):
            result.append({'rva': hex(ins.address), 'bytes': ins.bytes.hex(),
                           'instruction': ins.mnemonic + ' ' + ins.op_str})
            if stop and ins.mnemonic in ('ret', 'jmp'):
                break
        slices[hex(start)] = result
        check_memory_budget()
        return result

    decode(0x35d210, 0x20, False)
    decode(0x36044d, 0x2b)
    decode(0x588dc0, 0x50)
    decode(0x59828e, 0x6b, False)
    decode(0x6836f2, 0x29, False)
    decode(0x13b010, 0x33, False)
    contracts = []
    for action in source['actions']:
        block = int(action['factory_block_rva'], 16)
        instructions = decode(block, 0xa0)
        jump = instructions[-1]['instruction']
        is_coalition = action['name'] == 'form_coalition'
        assert jump == ('jmp 0x36045c' if is_coalition else
                        'jmp 0x360450' if action['name'] == 'insultaction' else
                        'jmp 0x360453' if action['name'] in ('giftaction', 'transfer_trade_power') else 'jmp 0x36044d')
        if is_coalition:
            assert next(i for i in instructions if i['rva'] == '0x35e051')['bytes'] == 'c7413402000000'
        clone = int(action['slots']['0xb0'], 16)
        clone_ins = decode(clone, 0x100)
        assert any('[rbx + 0x34]' in i['instruction'] for i in clone_ins)
        contracts.append({'name': action['name'], 'token': action['token_id'],
            'size': action['size_bytes'], 'factory_entry': hex(block), 'tail_entry': jump.split()[1],
            'factory_state34': 2 if is_coalition else 0, 'clone_state34': 'copied_from_source',
            'clone_entry': hex(clone), 'default_envoy30': -1, 'default_value38_flag39': 1,
            'default_date28_date2c': 0x29c77f8,
            'derived_default': ({'0x40:int32': -1} if action['name'] == 'insultaction' else
                                {'0x40:int32': 0} if action['name'] == 'giftaction' else
                                {'0x40:int32': 0, '0x44:byte': 0} if action['name'] == 'transfer_trade_power' else {})})
    result = {'schema': 1, 'purpose': 'static_factory_contract_correction', 'game_sha256': SHA,
              'input_sha256': INPUT_SHA, 'contracts': contracts, 'slices': slices,
              'ordinary_queue_report': QUEUE.relative_to(ROOT).as_posix(),
              'ordinary_queue_report_sha256': QUEUE_SHA,
              'ordinary_queue_disk_verified_bytes': queue_verified_bytes,
              'decoded_bytes': sum(len(bytes.fromhex(i['bytes'])) for rows in slices.values() for i in rows),
              'failure_explanation': 'Factory writes coalition state34=2, whereas v11 demanded0. The aggregate live failure did not directly record state34.',
              'execution_state_status': 'Ordinary native AI helper12b860 writes coalition state2 at12c54f for both modes, calls129b60, then virtual+40 wrapper4e9930 transfers its clone-containing command into owner+a68. This agrees with leaf/specialized/script construction. It proves native queued-action initialization, not human GUI identity, final transport submission or application.',
              'runtime_state34_observed': False, 'process_access': False, 'native_invoked': False}
    (HERE / 'factory-contract-evidence.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'contracts': len(contracts), 'decoded_bytes': result['decoded_bytes'],
                      'report_sha256': hashlib.sha256((HERE / 'factory-contract-evidence.json').read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
