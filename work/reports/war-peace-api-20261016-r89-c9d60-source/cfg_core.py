"""Pure worklist only. Decoder is supplied; no imports, files, or process APIs."""
BEGIN = 0xc9d60
END = 0xc9e60
SEEDS = (0xc9d60,)


def run_cfg(raw, decode_one, memory_guard=lambda: None):
    if type(raw) is not bytes or len(raw) != 256:
        raise ValueError('Exact fixed 256 owned bytes required')
    queue = list(SEEDS)
    rows, occupied, edges, terminals, lookahead, reused = {}, {}, [], [], [], []
    attempted = set()
    while queue:
        cursor = queue.pop(0)
        while True:
            memory_guard()
            if cursor in rows:
                reused.append(cursor)
                break
            if not BEGIN <= cursor < END:
                terminals.append({'kind': 'outside_owned_window', 'rva': hex(cursor)})
                break
            if cursor in occupied:
                terminals.append({'kind': 'interior_instruction_target', 'rva': hex(cursor), 'owner': hex(occupied[cursor])})
                break
            if cursor in attempted:
                reused.append(cursor)
                break
            if len(rows) >= 256:
                raise ValueError('Fixed row bound')
            n = min(15, END - cursor)
            chunk = raw[cursor - BEGIN:cursor - BEGIN + n]
            attempted.add(cursor)
            lookahead.append({'rva': hex(cursor), 'bytes': n})
            item = decode_one(chunk, cursor)
            if item is None:
                terminals.append({'kind': 'undecodable_or_partial', 'rva': hex(cursor), 'raw_hex': chunk.hex()})
                break
            row, control = item
            size = len(bytes.fromhex(row['bytes']))
            if (int(row['rva'], 16) != cursor or not 0 < size <= n
                    or bytes.fromhex(row['bytes']) != chunk[:size]):
                raise ValueError('Decoder row/raw boundary mismatch')
            if any(p in occupied for p in range(cursor, cursor + size)):
                terminals.append({'kind': 'instruction_overlap_unknown', 'rva': hex(cursor)})
                break
            rows[cursor] = row
            occupied.update({p: cursor for p in range(cursor, cursor + size)})
            following = cursor + size
            if control['kind'] == 'ret':
                terminals.append({'kind': 'normal_ret', 'rva': hex(cursor)})
                break
            if control['kind'] == 'abnormal':
                terminals.append({'kind': 'abnormal_or_unmodelled_terminal', 'rva': hex(cursor)})
                break
            if control['kind'] in ('call', 'jump'):
                target = control['target']
                inside = type(target) is int and BEGIN <= target < END
                jump = control['kind'] == 'jump'
                unconditional = jump and control['unconditional']
                edges.append({'site': hex(cursor), 'kind': row['mnemonic'],
                    'target_rva': hex(target) if type(target) is int else None,
                    'inside_owned_window': inside, 'callee_followed': False,
                    'local_branch_target_enqueued': jump and inside,
                    'fallthrough': None if unconditional else hex(following),
                    'fallthrough_requires_unknown_callee_normal_return': not jump})
                if jump:
                    if inside:
                        queue.append(target)
                    else:
                        terminals.append({'kind': 'external_or_indirect_branch', 'rva': hex(cursor),
                            'target_rva': hex(target) if type(target) is int else None})
                    if unconditional:
                        break
            if following == END:
                terminals.append({'kind': 'window_fallthrough', 'rva': hex(END)})
                break
            cursor = following
    inputs = set()
    for request in lookahead:
        start = int(request['rva'], 16)
        inputs.update(range(start, start + request['bytes']))
    missing, first = [], None
    for p in range(BEGIN, END + 1):
        absent = p < END and p not in occupied
        if absent and first is None: first = p
        if not absent and first is not None:
            missing.append([hex(first), hex(p)]); first = None
    return {'explicit_seeds': [hex(p) for p in SEEDS], 'instructions': [rows[p] for p in sorted(rows)],
        'seed_semantics': {'0xc9d60': 'direct_CALL_encoding_target_not_safe_callable_proof'},
        'actual_CALL_callee_reachability_proved_by_this_worklist': False,
        'edges': edges, 'terminals': terminals, 'reused_row_starts': [hex(p) for p in reused if p in rows],
        'reused_terminal_starts': [hex(p) for p in reused if p not in rows],
        'attempted_decode_starts': [hex(p) for p in sorted(attempted)],
        'lookahead_inputs': lookahead, 'instruction_count': len(rows), 'decoded_unique_bytes': len(occupied),
        'undecoded_owned_intervals': missing, 'decoder_input_total_bytes': sum(x['bytes'] for x in lookahead),
        'decoder_input_unique_bytes': len(inputs), 'decoder_overlap_bytes': sum(x['bytes'] for x in lookahead) - len(inputs),
        'local_normal_CFG_closed': bool(terminals) and all(t['kind'] == 'normal_ret' for t in terminals),
        'whole_function_closed': False, 'external_CALL_normal_return_assumed_for_fallthrough': True,
        'dynamic_reachability_verified': False}
