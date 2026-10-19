'use strict';
// Node VM byte-layout simulation only. No Frida module or target is loaded.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, 'entry_observer.js'), 'utf8');
const B = 0x140000000n, Q = 0x100008n, OUTER = 0x500000n, GAME = 0x600000n;
const SERVER = 0x700000n, HOLDER = 0x800000n, MAP = 0x900000n, PENDING = 0xa00000n, PREVIOUS = 0xb00000n;
const PREFIX = '4c89442418555357488d6c24b04881ec50010000488b159d8f2901488bf9440f';
const SHA = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a';
const h = value => '0x' + BigInt(value).toString(16).padStart(16, '0');
function config(changes) {
  return Object.assign({schema: 'EU4-FRIDA-ENTRY-CONFIG/1', pid: 80340,
    creation: '01dd5c075fcf8c26', game_sha256: SHA, base: h(B), expected_prefix_hex: PREFIX,
    observer_nonce: '0123456789abcdef0123456789abcdef', max_attempts: 16}, changes);
}
function fixture(options) {
  options = options || {};
  const memory = new Map(), reads = [], messages = [], immediates = [], timers = new Map();
  let handler = null, activeStack = false, hookCount = 0, detachCount = 0, nextTimer = 0;
  let beforeRead = null, forbiddenCalls = 0, hookAddress = null;
  const put = (address, bytes) => {
    for (let index = 0; index < bytes.length; ++index) memory.set(BigInt(address) + BigInt(index), bytes[index]);
  };
  const qword = (address, value) => {
    const buffer = Buffer.alloc(8); buffer.writeBigUInt64LE(BigInt(value)); put(address, buffer);
  };
  const remove = (address, size) => {
    for (let index = 0; index < size; ++index) memory.delete(BigInt(address) + BigInt(index));
  };
  put(B + 0x10a6ec0n, Buffer.from(PREFIX, 'hex'));
  for (const pair of [[0n, 0x10a6d61n], [0x40n, 0x81582en], [0x370n, 0x14c2818n],
    [0x3f0n, 0x14c2e18n], [0x440n, 0x8781b9n]]) qword(Q + pair[0], B + pair[1]);
  qword(Q + 0x4a8n, OUTER);
  qword(B + 0x242bf50n, OUTER); qword(B + 0x233fe78n, GAME);
  qword(OUTER, B + 0x1c48bf8n); qword(OUTER + 0x10n, B + 0x1c48c80n);
  qword(OUTER + 0x40n, SERVER);
  qword(OUTER + 0x70n, options.optional === false ? 0n : PENDING);
  qword(OUTER + 0x78n, options.optional === false ? 0n : PREVIOUS);
  put(OUTER + 0x48n, [1]); put(OUTER + 0x80n, [1]);
  qword(GAME, B + 0x1cb00c8n); qword(GAME + 0x1e00n, SERVER);
  qword(SERVER, B + 0x1cb8460n); qword(B + 0x1cb8480n, B + 0x8137c0n);
  qword(SERVER + 0x330n, HOLDER); qword(HOLDER + 0x360n, MAP);
  qword(PENDING, B + 0x1d5a8c8n); qword(PREVIOUS, B + 0x1d5a8c8n);
  class Pointer {
    constructor(value) { this.value = BigInt(value); }
    toString() { return '0x' + this.value.toString(16); }
    add(value) { return new Pointer(BigInt.asUintN(64, this.value + BigInt(value))); }
    readByteArray(size) {
      reads.push({address: this.value, size: size, activeStack: activeStack});
      if (this.value >= Q && this.value < Q + 0x4b0n && !activeStack) throw Error('stack borrow already returned');
      if (beforeRead) {
        const override = beforeRead(this.value, size);
        if (override !== undefined) return override;
      }
      const output = new Uint8Array(size);
      for (let index = 0; index < size; ++index) {
        const at = this.value + BigInt(index);
        if (!memory.has(at)) throw Error('unmapped byte');
        output[index] = memory.get(at);
      }
      return output.buffer;
    }
  }
  const context = {
    ArrayBuffer: ArrayBuffer, Uint8Array: Uint8Array,
    ptr: value => new Pointer(value),
    Process: {id: options.processId || 80340, arch: 'x64', platform: 'windows', pointerSize: 8,
      getModuleByName: name => {
        assert.equal(name, 'eu4.exe');
        return {name: 'eu4.exe', base: new Pointer(options.moduleBase || B), size: 0x2434000};
      }},
    Interceptor: {
      attach: (target, callbacks) => {
        ++hookCount; hookAddress = target.value; handler = callbacks.onEnter;
        assert.equal(target.value, B + 0x10a6ec0n);
        put(target.value, Buffer.alloc(32, 0xcc)); // simulated temporary CODE write
        if (options.attachThrows) throw Error('simulated attach failure');
        return {detach: () => {
          ++detachCount;
          if (options.detachThrows) throw Error('simulated detach failure');
          put(target.value, Buffer.from(PREFIX, 'hex'));
        }};
      },
      flush: () => {
        if (options.flushThrows) throw Error('simulated flush failure');
      }
    },
    send: payload => {
      const encoded = JSON.stringify({type: 'send', payload: payload});
      assert.ok(Buffer.byteLength(encoded, 'utf8') <= 16384);
      messages.push(JSON.parse(JSON.stringify(payload)));
    },
    setImmediate: callback => { immediates.push(callback); return 1; },
    setTimeout: (callback, milliseconds) => {
      assert.equal(milliseconds, 1000); const id = ++nextTimer; timers.set(id, callback); return id;
    },
    clearTimeout: id => timers.delete(id),
    NativeFunction: () => { ++forbiddenCalls; throw Error('forbidden'); },
    NativeCallback: () => { ++forbiddenCalls; throw Error('forbidden'); },
    Memory: {alloc: () => { ++forbiddenCalls; throw Error('forbidden'); }}
  };
  function load(changes) {
    const rendered = 'const EU4_ENTRY_OBSERVER_CONFIG = ' + JSON.stringify(config(changes)) + ';\n' + source;
    vm.runInNewContext(rendered, context, {timeout: 1000, filename: 'entry_observer.js'});
  }
  function invoke(changes) {
    assert.ok(handler);
    const invocation = Object.assign({context: Object.freeze({rsp: new Pointer(Q),
      rcx: new Pointer(MAP), r8: new Pointer(SERVER)}), threadId: 4412, depth: 0,
      returnAddress: new Pointer(B + 0x10a6d61n)}, changes);
    activeStack = true;
    try { handler.call(invocation, Object.freeze([])); } finally { activeStack = false; }
  }
  function drain() {
    while (immediates.length) immediates.shift()();
    assert.equal(forbiddenCalls, 0);
  }
  function deadline() {
    for (const callback of Array.from(timers.values())) callback();
    drain();
  }
  function final() {
    drain(); assert.equal(messages.length, 1); return messages[0];
  }
  return {load, invoke, drain, deadline, final, reads, messages, put, qword, remove,
    setBeforeRead: value => { beforeRead = value; },
    stats: () => ({hookCount, detachCount, hookAddress, timers: timers.size})};
}
function unknown(result, reason) {
  assert.equal(result.status, 'unknown');
  if (reason) assert.equal(result.reason, reason);
  assert.equal(result.native_game_calls, 0); assert.equal(result.field_game_data_writes, 0);
  assert.equal(result.lifetime_lease, false); assert.equal(result.atomic_snapshot, false);
  assert.equal(result.native_ready, false); assert.equal(result.native_entry_authenticated, false);
}
test('first chain captures only six literal slots per pass and typed graph', () => {
  const f = fixture(); f.load(); f.invoke();
  assert.equal(f.messages.length, 0); // owned record sent only after callback return
  const r = f.final();
  assert.equal(r.status, 'structural_match'); assert.equal(r.temporary_code_hook, true);
  assert.equal(r.pure_RPM, false); assert.equal(r.observation.Q, h(Q));
  assert.equal(r.observation.original_rcx, h(MAP)); assert.equal(r.observation.original_r8, h(SERVER));
  assert.equal(r.observation.thread_id, 4412); assert.equal(r.observation.two_pass_equal, true);
  assert.equal(r.observation.first.slots.length, 6);
  for (const row of r.observation.first.slots) {
    assert.equal(row.address, h(Q + BigInt(row.offset))); assert.equal(row.raw8_hex.length, 16);
  }
  assert.equal(r.observation.first.fields.current_app, h(SERVER));
  assert.deepEqual(r.counters, {reads: 48, requested_bytes: 404, exact_bytes: 404, categories: {
    prefix_before: {reads: 1, bytes: 32}, prefilter: {reads: 5, bytes: 40}, stack: {reads: 7, bytes: 56},
    world: {reads: 34, bytes: 244}, prefix_cleanup: {reads: 1, bytes: 32}}});
  assert.equal(r.cleanup.original_prefix32_matches, true); assert.equal(r.cleanup.listener_detach_returned, true);
  assert.equal(f.stats().detachCount, 1); assert.equal(f.stats().timers, 0);
  assert.ok(f.reads.filter(row => row.address >= Q && row.address < Q + 0x4b0n).every(row => row.size === 8 && row.activeStack));
  const before = f.reads.length; f.invoke(); f.drain(); assert.equal(f.reads.length, before);
});
test('null optional pointers have no dereference and lower exact count', () => {
  const f = fixture({optional: false}); f.load(); f.invoke(); const r = f.final();
  assert.equal(r.status, 'structural_match'); assert.equal(r.counters.reads, 44);
  assert.equal(r.counters.exact_bytes, 372);
  assert.equal(r.observation.first.fields.pending_vtable, null);
  assert.equal(r.observation.first.fields.previous_vtable, null);
  assert.ok(!f.reads.some(row => row.address === 0n));
});
test('fifteenth wrong last return then sixteenth match stays globally bounded', () => {
  const f = fixture(); f.load(); f.qword(Q + 0x440n, B + 0x8781ban);
  for (let index = 0; index < 15; ++index) f.invoke();
  assert.equal(f.messages.length, 0);
  f.qword(Q + 0x440n, B + 0x8781b9n); f.invoke(); const r = f.final();
  assert.equal(r.status, 'structural_match'); assert.equal(r.attempts, 16);
  assert.equal(r.counters.reads, 123); assert.equal(r.counters.requested_bytes, 1004);
  assert.equal(r.counters.categories.prefilter.reads, 80);
});
test('sixteenth chain mismatch terminates with no world or holder follow', () => {
  const f = fixture(); f.load(); f.qword(Q + 0x440n, 0n);
  for (let index = 0; index < 16; ++index) f.invoke();
  const r = f.final(); unknown(r, 'no_static_chain_within_16_callbacks');
  assert.equal(r.attempts, 16); assert.equal(r.counters.categories.world.reads, 0);
  assert.equal(r.counters.categories.stack.reads, 0);
  const count = f.reads.length; f.invoke(); f.drain(); assert.equal(f.reads.length, count);
});
test('every one of the five prefilter slots independently rejects the wrong chain', () => {
  for (const offset of [0n, 0x40n, 0x370n, 0x3f0n, 0x440n]) {
    const f = fixture(); f.load(); f.qword(Q + offset, B);
    f.invoke(); f.deadline(); const r = f.final();
    unknown(r, 'deadline_without_qualified_callback');
    assert.equal(r.attempts, 1); assert.equal(r.counters.categories.world.reads, 0);
    assert.equal(r.counters.categories.stack.reads, 0);
  }
});
test('deadline without callbacks detaches exactly once and sends unknown', () => {
  const f = fixture(); f.load(); f.deadline(); const r = f.final();
  unknown(r, 'deadline_without_qualified_callback');
  assert.equal(r.attempts, 0); assert.equal(r.counters.reads, 2); assert.equal(f.stats().detachCount, 1);
});
test('configuration cannot change target, bytes, budgets or identity types', () => {
  for (const changes of [{max_attempts: 17}, {expected_prefix_hex: '00'.repeat(32)}, {game_sha256: 'a'.repeat(64)},
    {pid: true}, {base: Number(B)}, {creation: 'not-creation'}, {observer_nonce: 'x'.repeat(32)},
    {entry_rva: 1}, {max_bytes: 999999}, {base: h(B + 8n)}]) {
    const f = fixture(); f.load(changes); const r = f.final(); unknown(r);
    assert.equal(f.stats().hookCount, 0); assert.equal(f.reads.length, 0);
  }
});
test('runtime PID/module and original prefix fail before any hook', () => {
  for (const options of [{processId: 99}, {moduleBase: B + 0x1000n}]) {
    const f = fixture(options); f.load(); unknown(f.final()); assert.equal(f.stats().hookCount, 0);
  }
  const f = fixture(); f.put(B + 0x10a6ec0n, [0]); f.load();
  unknown(f.final(), 'original_prefix_mismatch'); assert.equal(f.stats().hookCount, 0);
});
test('malformed callback context or nesting stops without retry', () => {
  for (const changes of [{threadId: true}, {depth: 1}, {returnAddress: {toString: () => h(B)}},
    {context: {rsp: h(Q + 8n), rcx: h(MAP), r8: h(SERVER)}},
    {context: {rsp: 1.5, rcx: h(MAP), r8: h(SERVER)}}]) {
    const f = fixture(); f.load(); f.invoke(changes); unknown(f.final());
    const count = f.reads.length; f.invoke(); f.drain(); assert.equal(f.reads.length, count);
  }
});
test('each retained return/holder and type/current/map guard is effective', () => {
  const cases = [[Q + 0x4a8n, PENDING, 'main_holder_root_mismatch'],
    [OUTER, B + 0x1cb8460n, 'outer_type_mismatch'],
    [OUTER + 0x10n, B + 0x1cb8460n, 'outer_type_mismatch'],
    [GAME, B + 0x1cb8460n, 'game_type_mismatch'],
    [OUTER + 0x40n, PENDING, 'current_server_r8_mismatch'],
    [GAME + 0x1e00n, GAME + 0x1e00n, 'current_server_r8_mismatch'],
    [SERVER, B + 0x1d5a8c8n, 'current_type_mismatch'],
    [B + 0x1cb8480n, B + 0x10d2e80n, 'current_update_mismatch'],
    [HOLDER + 0x360n, PENDING, 'map_rcx_mismatch']];
  for (const [at, value, reason] of cases) {
    const f = fixture(); f.load(); f.qword(at, value); f.invoke(); unknown(f.final(), reason);
  }
});
test('noncanonical pointers are refused and never followed', () => {
  for (const at of [B + 0x242bf50n, B + 0x233fe78n, OUTER + 0x70n, SERVER + 0x330n]) {
    const f = fixture(); f.load(); f.qword(at, 0xfffffffffffffff8n); f.invoke();
    unknown(f.final(), 'address_span_out_of_range');
    assert.ok(!f.reads.some(row => row.address === 0xfffffffffffffff8n));
  }
});
test('second pass retired pending is re-resolved and old pointer is not read', () => {
  const f = fixture(); f.load(); let roots = 0, marker = 0;
  f.setBeforeRead((address) => {
    if (address === B + 0x242bf50n && ++roots === 2) {
      marker = f.reads.length; f.qword(OUTER + 0x70n, 0n); f.remove(PENDING, 8);
    }
  });
  f.invoke(); const r = f.final(); unknown(r, 'projection_changed_between_passes');
  assert.equal(r.observation.first.fields.pending_app, h(PENDING));
  assert.equal(r.observation.second.fields.pending_app, h(0n));
  assert.ok(!f.reads.slice(marker).some(row => row.address === PENDING));
});
test('second pass return slot corruption yields unknown without modifying CPU slot', () => {
  const f = fixture(); f.load(); let reads = 0;
  f.setBeforeRead((address) => {
    if (address === Q && ++reads === 2) return new ArrayBuffer(8);
  });
  f.invoke(); unknown(f.final(), 'return_chain_changed');
});
test('invalid byte buffer, detached buffer and read error close to unknown', () => {
  for (const make of [() => new ArrayBuffer(64), () => '12345678', () => {
    const value = new ArrayBuffer(8); structuredClone(value, {transfer: [value]}); return value;
  }, () => { throw Error('DO_NOT_PRINT_TOKEN'); }]) {
    const f = fixture(); f.load(); f.setBeforeRead(address => address === Q ? make() : undefined);
    f.invoke(); const r = f.final(); unknown(r);
    assert.ok(['short_or_invalid_read', 'read_failed'].includes(r.reason));
    assert.equal(r.counters.exact_bytes, 64); // only pre/cleanup prefix succeeded
    assert.ok(!JSON.stringify(r).includes('DO_NOT_PRINT_TOKEN'));
  }
});
test('reentry becomes terminal and cannot publish a later success', () => {
  const f = fixture(); f.load(); let entered = false;
  f.setBeforeRead(address => {
    if (address === B + 0x242bf50n && !entered) { entered = true; f.invoke({depth: 1}); }
  });
  f.invoke(); unknown(f.final(), 'callback_reentered'); assert.equal(f.stats().detachCount, 1);
});
test('detach/flush failures retain unknown and never claim full cleanup', () => {
  for (const options of [{detachThrows: true}, {flushThrows: true}]) {
    const f = fixture(options); f.load(); f.invoke(); const r = f.final();
    unknown(r, 'cleanup_not_confirmed'); assert.equal(r.cleanup.host_cleanup_still_required, true);
    assert.equal(f.stats().detachCount, 1);
  }
});
test('attach exception does not pretend no code write or create retry', () => {
  const f = fixture({attachThrows: true}); f.load(); const r = f.final();
  unknown(r, 'setup_or_hook_failed'); assert.equal(r.temporary_code_hook, true);
  assert.equal(r.cleanup.original_prefix32_matches, false); assert.equal(f.stats().hookCount, 1);
});
test('no game-call, write, allocation, blanket detach or whole-stack APIs in source', () => {
  for (const forbidden of [/\bNativeFunction\s*\(/, /\bNativeCallback\s*\(/, /\bMemory\.alloc\s*\(/,
    /\.write[A-Z]\w*\s*\(/, /Interceptor\.detachAll\s*\(/, /readByteArray\s*\(\s*1200\s*\)/])
    assert.equal(forbidden.test(source), false, String(forbidden));
});
