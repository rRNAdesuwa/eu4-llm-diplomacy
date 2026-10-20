"""Fixed-entry diagnostic metadata query. Supplied byte reader; no file/process imports."""
ENTRY = 0xc9d60
WINDOW = {'begin': '0xc9d60', 'end_exclusive': '0xc9e60', 'bytes': 256, 'seeds': ['0xc9d60']}
MAX_SEARCH = 29
MAX_TOTAL = 32


class InvalidMetadata(Exception):
    pass


def diagnose(read_record, count, memory_guard=lambda: None):
    requests, known, issues = [], {}, []
    selected = previous = following = None
    complete = False
    low = high = None

    def refuse(ok, why):
        if not ok:
            raise InvalidMetadata(why)

    def record(index, reason):
        refuse(type(index) is int and 0 <= index < count and len(requests) < MAX_TOTAL, 'metadata_index_or_budget')
        memory_guard()
        raw = read_record(index, reason)
        item = {'index': index, 'reason': reason, 'returned_bytes': len(raw) if type(raw) is bytes else 0,
                'raw_hex': raw[:12].hex() if type(raw) is bytes else None}
        requests.append(item)
        refuse(type(raw) is bytes and len(raw) == 12, 'short_or_invalid_metadata')
        begin, end, unwind = [int.from_bytes(raw[n:n + 4], 'little') for n in (0, 4, 8)]
        item.update(begin_rva=hex(begin), end_exclusive=hex(end), unwind_rva_unfollowed=hex(unwind))
        refuse(begin < end, 'nonpositive_metadata_span')
        if index in known:
            refuse(known[index]['raw_hex'] == item['raw_hex'], 'repeated_record_changed')
        else:
            known[index] = item
        ordered = sorted(known.items())
        for (_, left), (_, right) in zip(ordered, ordered[1:]):
            refuse(int(left['end_exclusive'], 16) <= int(right['begin_rva'], 16), 'observed_metadata_overlap_or_order')
        return item

    try:
        refuse(type(count) is int and 0 < count <= 38462504 // 12, 'cached_metadata_count_bounds')
        low, high = 0, count
        while low < high:
            refuse(len(requests) < MAX_SEARCH, 'metadata_search_budget_incomplete')
            middle = (low + high) // 2
            item = record(middle, 'binary_search')
            if int(item['begin_rva'], 16) <= ENTRY:
                low = middle + 1
            else:
                high = middle
        complete = True
        selected = record(low - 1, 'selected') if low else None
        previous = record(low - 2, 'previous') if low >= 2 else None
        following = record(low, 'next') if low < count else None
        refuse(selected is not None or following is not None, 'no_selected_or_neighbor_diagnostic')
        if selected is not None:
            refuse(int(selected['begin_rva'], 16) <= ENTRY, 'selected_not_lower_bound')
        if following is not None:
            refuse(ENTRY < int(following['begin_rva'], 16), 'following_not_upper_bound')
        containing = selected is not None and ENTRY < int(selected['end_exclusive'], 16)
        exact = containing and int(selected['begin_rva'], 16) == ENTRY
        classification = 'exact_record' if exact else 'contained_nonexact' if containing else 'completed_ordered_gap'
        valid = True
    except InvalidMetadata as error:
        issues.append(str(error))
        containing = exact = valid = False
        classification = 'unknown_invalid_or_incomplete_metadata'
    return {'schema': 'EU4-R89-DIAGNOSTIC-METADATA/1', 'entry_rva': hex(ENTRY),
            'fixed_raw_window': dict(WINDOW), 'requests': requests, 'search_completed': complete,
            'search_low': low, 'search_high': high, 'selected': selected, 'previous': previous, 'following': following,
            'metadata_valid': valid, 'issues': issues, 'classification': classification,
            'seed_pdata_gap': valid and not containing, 'exact_record': exact,
            'function_metadata_unknown': not exact, 'code_extent_selected_from_metadata': False,
            'global_sorted_table_assumed': True, 'global_sorted_table_verified': False,
            'returned_metadata_bytes': sum(item['returned_bytes'] for item in requests),
            'maximum_search_records': MAX_SEARCH, 'maximum_total_records': MAX_TOTAL,
            'whole_function_verified': False, 'callable': False}
