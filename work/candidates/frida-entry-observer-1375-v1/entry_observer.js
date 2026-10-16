/* SOURCE/OFFLINE CANDIDATE. Loading this script applies a temporary code hook.
 * It never constructs/calls a game object, writes game fields, or grants lease.
 * Only the reviewed root host may render the fixed config and authorize a load.
 */
(function () {
  'use strict';
  const SHA = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a';
  const PREFIX = '4c89442418555357488d6c24b04881ec50010000488b159d8f2901488bf9440f';
  const ENTRY = 0x10a6ec0, DEADLINE_MS = 1000, MAX_READS = 128, MAX_BYTES = 8192;
  const RETS = [[0, 0x10a6d61], [0x40, 0x81582e], [0x370, 0x14c2818],
    [0x3f0, 0x14c2e18], [0x440, 0x8781b9]];
  const MIN = '0000000000010000', MAX = '00007fffffff0000';
  const state = {done: false, busy: false, attempts: 0, hookAttempted: false,
    listener: null, timer: null, config: null, base: null, target: null,
    counters: {reads: 0, requested_bytes: 0, exact_bytes: 0, categories: {
      prefix_before: {reads: 0, bytes: 0}, prefilter: {reads: 0, bytes: 0},
      stack: {reads: 0, bytes: 0}, world: {reads: 0, bytes: 0},
      prefix_cleanup: {reads: 0, bytes: 0}}}};
  class Refused extends Error { constructor(code) { super(code); this.code = code; } }
  function refuse(code) { throw new Refused(code); }
  function integer(value) { return typeof value === 'number' && Number.isInteger(value); }
  function hex(value) {
    let text;
    if (typeof value === 'string') text = value;
    else if (value !== null && typeof value === 'object') text = value.toString();
    else refuse('invalid_address_type');
    if (typeof text !== 'string' || !/^0x[0-9a-f]{1,16}$/i.test(text)) refuse('invalid_address_encoding');
    return '0x' + text.slice(2).toLowerCase().padStart(16, '0');
  }
  function plus(value, offset) {
    if (!integer(offset) || offset < 0 || offset > 0x40000000) refuse('invalid_offset');
    return hex(ptr(value).add(offset));
  }
  function span(value, size) {
    const at = hex(value), digits = at.slice(2);
    if (!integer(size) || size < 1 || size > 0x40000000 ||
        digits < MIN || digits >= MAX) refuse('address_span_out_of_range');
    const end = plus(at, size).slice(2);
    if (end <= digits || end > MAX) refuse('address_span_out_of_range');
    return at;
  }
  function pointer(value, optional) {
    const at = hex(value);
    if (optional && at === '0x0000000000000000') return at;
    span(at, 8);
    if (!/[08]$/.test(at)) refuse('unaligned_object_pointer');
    return at;
  }
  function byteHex(bytes) {
    let out = '';
    for (let index = 0; index < bytes.length; ++index) out += bytes[index].toString(16).padStart(2, '0');
    return out;
  }
  function decode64(raw) {
    if (raw.length !== 16) refuse('invalid_qword_bytes');
    let text = '';
    for (let index = 14; index >= 0; index -= 2) text += raw.slice(index, index + 2);
    return '0x' + text;
  }
  function read(address, size, category) {
    const at = span(address, size);
    if (state.done && category !== 'prefix_cleanup') refuse('terminal_read_forbidden');
    if (!Object.prototype.hasOwnProperty.call(state.counters.categories, category)) refuse('invalid_read_category');
    const isPrefix = category === 'prefix_before' || category === 'prefix_cleanup';
    if ((isPrefix && size !== 32) || (!isPrefix && size !== 1 && size !== 8)) refuse('single_read_size');
    const budget = state.counters;
    if (budget.reads >= MAX_READS || size > MAX_BYTES - budget.requested_bytes) refuse('read_budget_exhausted');
    ++budget.reads; budget.requested_bytes += size;
    ++budget.categories[category].reads; budget.categories[category].bytes += size;
    let buffer;
    try { buffer = ptr(at).readByteArray(size); } catch (_) { refuse('read_failed'); }
    let bytes;
    try {
      // Use the buffer intrinsic, not a spoofable view's element count.
      const nbytes = Object.getOwnPropertyDescriptor(ArrayBuffer.prototype, 'byteLength').get.call(buffer);
      if (nbytes !== size) refuse('short_or_invalid_read');
      bytes = new Uint8Array(new Uint8Array(buffer)); // bounded owned copy
      if (bytes.byteLength !== size) refuse('short_or_invalid_read');
    } catch (error) {
      if (error instanceof Refused) throw error;
      refuse('short_or_invalid_read');
    }
    budget.exact_bytes += bytes.byteLength;
    return byteHex(bytes);
  }
  function slot(q, offset, category) {
    const address = plus(q, offset), raw = read(address, 8, category);
    return {offset: offset, address: address, raw8_hex: raw, value: decode64(raw)};
  }
  function returns(q, category) {
    const rows = [];
    for (const pair of RETS) {
      const row = slot(q, pair[0], category);
      rows.push(row);
      if (row.value !== plus(state.base, pair[1])) return {matches: false, slots: rows};
    }
    return {matches: true, slots: rows};
  }
  function project(q, originalRcx, originalR8, firstReturns) {
    const chain = firstReturns || returns(q, 'stack');
    if (!chain.matches) refuse('return_chain_changed');
    const slots = chain.slots.slice();
    slots.push(slot(q, 0x4a8, 'stack'));
    const fields = {}, reads = [];
    function take(name, address, size) {
      const at = hex(address), raw = read(at, size || 8, 'world');
      reads.push({field: name, address: at, size: size || 8, raw_hex: raw});
      const value = size === 1 ? parseInt(raw, 16) : decode64(raw);
      fields[name] = value;
      return value;
    }
    const outer = pointer(take('outer', plus(state.base, 0x242bf50)));
    const game = pointer(take('game', plus(state.base, 0x233fe78)));
    if (slots[5].value !== outer) refuse('main_holder_root_mismatch');
    const outerVt = take('outer_vtable', outer);
    const secondaryVt = take('outer_secondary_vtable', plus(outer, 0x10));
    if (outerVt !== plus(state.base, 0x1c48bf8) || secondaryVt !== plus(state.base, 0x1c48c80))
      refuse('outer_type_mismatch');
    const current = pointer(take('current_app', plus(outer, 0x40)));
    const pending = pointer(take('pending_app', plus(outer, 0x70)), true);
    const previous = pointer(take('previous_app', plus(outer, 0x78)), true);
    take('transition_byte', plus(outer, 0x48), 1);
    take('retain_previous_byte', plus(outer, 0x80), 1);
    if (take('game_vtable', game) !== plus(state.base, 0x1cb00c8)) refuse('game_type_mismatch');
    const server = pointer(take('game_server', plus(game, 0x1e00)));
    if (current !== server || server !== originalR8) refuse('current_server_r8_mismatch');
    const currentVt = take('current_vtable', current);
    if (currentVt !== plus(state.base, 0x1cb8460)) refuse('current_type_mismatch');
    if (take('current_update', plus(currentVt, 0x20)) !== plus(state.base, 0x8137c0))
      refuse('current_update_mismatch');
    const holder = pointer(take('server_holder', plus(server, 0x330)));
    if (take('map_object', plus(holder, 0x360)) !== originalRcx) refuse('map_rcx_mismatch');
    fields.pending_vtable = pending === '0x0000000000000000' ? null : take('pending_vtable', pending);
    fields.previous_vtable = previous === '0x0000000000000000' ? null : take('previous_vtable', previous);
    return {slots: slots, fields: fields, reads: reads};
  }
  function envelope(status, reason, observation) {
    return {schema: 'EU4-FRIDA-ENTRY-OBSERVATION/1', status: status, reason: reason,
      observer_nonce: state.config ? state.config.observer_nonce : null,
      configured_pid: state.config ? state.config.pid : null,
      configured_creation: state.config ? state.config.creation : null,
      configured_game_sha256: SHA, module_base: state.base, entry_rva: ENTRY,
      attempts: state.attempts, observation: observation || null,
      temporary_code_hook: state.hookAttempted, field_game_data_writes: 0, native_game_calls: 0,
      native_game_objects_constructed: 0, pure_RPM: false, native_ready: false,
      native_entry_authenticated: false, creation_authenticated_in_script: false,
      image_sha_verified_in_script: false, lifetime_lease: false, atomic_snapshot: false,
      budgets: {scope: 'all explicit readByteArray requests in this script', max_reads: MAX_READS,
        max_bytes: MAX_BYTES, max_message_envelope_bytes: 16384, stack_window_read: false},
      counters: state.counters};
  }
  function emit(payload) {
    let serialized = JSON.stringify({type: 'send', payload: payload});
    if (!/^[\x20-\x7e]*$/.test(serialized) || serialized.length > 16384) {
      payload = envelope('unknown', 'message_budget_exhausted', null);
      payload.cleanup = {host_cleanup_still_required: true};
      serialized = JSON.stringify({type: 'send', payload: payload});
    }
    if (!/^[\x20-\x7e]*$/.test(serialized) || serialized.length > 16384) return;
    send(payload);
  }
  function finish(status, reason, observation) {
    if (state.done) return;
    state.done = true;
    if (state.timer !== null) { clearTimeout(state.timer); state.timer = null; }
    const payload = envelope(status, reason, observation);
    if (!state.hookAttempted) {
      payload.cleanup = {listener_detach_attempted: false, host_cleanup_still_required: true};
      emit(payload); return;
    }
    // No callback/context/Q object is captured here: only owned values and the
    // fixed module code address survive. Cleanup occurs after onEnter returns.
    setImmediate(function () {
      const cleanup = {listener_detach_attempted: state.listener !== null,
        listener_detach_returned: false, interceptor_flush_returned: false,
        original_prefix32_matches: false, host_cleanup_still_required: true};
      if (state.listener !== null) {
        try { state.listener.detach(); cleanup.listener_detach_returned = true; } catch (_) {}
        state.listener = null;
      }
      try { Interceptor.flush(); cleanup.interceptor_flush_returned = true; } catch (_) {}
      try { cleanup.original_prefix32_matches = read(state.target, 32, 'prefix_cleanup') === PREFIX; } catch (_) {}
      payload.cleanup = cleanup;
      if (status === 'structural_match' && (!cleanup.listener_detach_returned ||
          !cleanup.interceptor_flush_returned || !cleanup.original_prefix32_matches)) {
        payload.status = 'unknown'; payload.reason = 'cleanup_not_confirmed';
      }
      emit(payload);
    });
  }
  function validateConfig(input) {
    const keys = ['schema', 'pid', 'creation', 'game_sha256', 'base',
      'expected_prefix_hex', 'observer_nonce', 'max_attempts'].sort();
    if (input === null || typeof input !== 'object' || Array.isArray(input) ||
        Object.getPrototypeOf(input) !== Object.prototype ||
        JSON.stringify(Object.keys(input).sort()) !== JSON.stringify(keys)) refuse('invalid_config_fields');
    if (input.schema !== 'EU4-FRIDA-ENTRY-CONFIG/1' || input.game_sha256 !== SHA ||
        input.expected_prefix_hex !== PREFIX || input.max_attempts !== 16) refuse('invalid_fixed_profile');
    if (!integer(input.pid) || input.pid < 1 || input.pid > 0xffffffff ||
        typeof input.creation !== 'string' || !/^[0-9a-f]{16}$/.test(input.creation) ||
        typeof input.observer_nonce !== 'string' || !/^[0-9a-f]{32}$/.test(input.observer_nonce) ||
        typeof input.base !== 'string') refuse('invalid_identity_metadata');
    const base = pointer(input.base);
    span(base, 0x2433e90);
    if (!base.endsWith('000')) refuse('module_base_alignment');
    return Object.freeze({schema: input.schema, pid: input.pid, creation: input.creation,
      game_sha256: SHA, base: base, expected_prefix_hex: PREFIX,
      observer_nonce: input.observer_nonce, max_attempts: 16});
  }
  try {
    state.config = validateConfig(typeof EU4_ENTRY_OBSERVER_CONFIG === 'undefined' ? null : EU4_ENTRY_OBSERVER_CONFIG);
    if (Process.id !== state.config.pid || Process.arch !== 'x64' || Process.platform !== 'windows' ||
        Process.pointerSize !== 8 || typeof setImmediate !== 'function' ||
        typeof setTimeout !== 'function' || typeof clearTimeout !== 'function') refuse('process_or_runtime_mismatch');
    const module = Process.getModuleByName('eu4.exe');
    if (typeof module.name !== 'string' || module.name.toLowerCase() !== 'eu4.exe' ||
        hex(module.base) !== state.config.base || !integer(module.size) ||
        module.size < 0x2433e90 || module.size > 0x40000000) refuse('module_identity_mismatch');
    span(state.config.base, module.size);
    state.base = state.config.base; state.target = plus(state.base, ENTRY);
    if (read(state.target, 32, 'prefix_before') !== PREFIX) refuse('original_prefix_mismatch');
    state.hookAttempted = true;
    state.listener = Interceptor.attach(ptr(state.target), {
      onEnter: function () {
        if (state.done) return;
        if (state.busy) { finish('unknown', 'callback_reentered', null); return; }
        state.busy = true; ++state.attempts;
        try {
          if (!integer(this.threadId) || this.threadId < 1 || this.threadId > 0xffffffff ||
              this.depth !== 0) refuse('invalid_thread_or_nested_callback');
          const q = span(hex(this.context.rsp), 0x4b0);
          if (!q.endsWith('8')) refuse('native_entry_stack_alignment');
          const rcx = pointer(this.context.rcx), r8 = pointer(this.context.r8);
          const prefilter = returns(q, 'prefilter');
          if (!prefilter.matches) {
            if (state.attempts >= 16) finish('unknown', 'no_static_chain_within_16_callbacks', null);
            return;
          }
          if (hex(this.returnAddress) !== prefilter.slots[0].value) refuse('invocation_return_address_mismatch');
          const first = project(q, rcx, r8, prefilter);
          const second = project(q, rcx, r8, null);
          const observation = {source: 'Frida_Interceptor_onEnter_before_original_prologue',
            Q: q, original_rcx: rcx, original_r8: r8, thread_id: this.threadId,
            interceptor_depth: this.depth, first: first, second: second,
            two_pass_equal: JSON.stringify(first) === JSON.stringify(second)};
          if (!observation.two_pass_equal) finish('unknown', 'projection_changed_between_passes', observation);
          else finish('structural_match', 'selected_entry_chain_observed', observation);
        } catch (error) {
          finish('unknown', error instanceof Refused ? error.code : 'unexpected_callback_error', null);
        } finally { state.busy = false; }
      }
    });
    if (!state.done) state.timer = setTimeout(function () {
      finish('unknown', 'deadline_without_qualified_callback', null);
    }, DEADLINE_MS);
  } catch (error) {
    finish('unknown', error instanceof Refused ? error.code : 'setup_or_hook_failed', null);
  }
})();
