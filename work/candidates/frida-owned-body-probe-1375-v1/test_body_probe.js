'use strict';
// Node VM byte-layout simulation only. No Frida module or target is loaded.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, 'body_probe.js'), 'utf8');
const B = 0x7ff7034b0000n, Q = 0x100008n, OUTER = 0x500000n, GAME = 0x600000n;
const SERVER = 0x700000n, HOLDER = 0x800000n, MAP = 0x900000n, PENDING = 0xa00000n, PREVIOUS = 0xb00000n;
const PROFILE = JSON.parse(fs.readFileSync(path.join(__dirname, '../../reports/war-peace-api-20261015-r17-owned-goal-independent-review/war/profiles.json'), 'utf8'));
const A = 0xc00000n, G = 0xd00000n;
const PREFIX = '4c89442418555357488d6c24b04881ec50010000488b159d8f2901488bf9440f';
const SHA = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a';
const h = value => '0x' + BigInt(value).toString(16).padStart(16, '0');
function config(changes) {
  return Object.assign({schema: 'EU4-FRIDA-BODY-PROBE-CONFIG/1', pid: 80340,
    creation: '01dd5c075fcf8c26', game_sha256: SHA, base: h(B), expected_prefix_hex: PREFIX,
    observer_nonce: '0123456789abcdef0123456789abcdef', max_attempts: 16}, changes);
}
function fixture(options) {
  options = options || {};
  const memory = new Map(), reads = [], messages = [], immediates = [], timers = new Map();
  let handler = null, activeStack = false, hookCount = 0, detachCount = 0, nextTimer = 0;
  let beforeRead = null, forbiddenCalls = 0, hookAddress = null;
  const allocations = [], writes = [], native = {constructed:0, attempted:0, returned:0};
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
  for (const row of PROFILE.complete_retained_functions) {
    if (['0x500560','0x8eac0','0x8f450'].includes(row.start)) put(B + BigInt(row.start), Buffer.from(row.raw_hex,'hex'));
  }
  qword(B + 0x1d20870n, B + 0x8f450n);
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
    writeByteArray(bytes) {
      assert.ok(activeStack, 'owned write outside the callback');
      const end = this.value + BigInt(bytes.length);
      assert.ok(allocations.some(row => this.value >= row.address && end <= row.address + BigInt(row.size)));
      writes.push({address: this.value, size:bytes.length});
      if (options.writeThrows && writes.length === 2) throw Error('synthetic write error');
      put(this.value, bytes);
      if (options.corruptVector && writes.length === 4) qword(A+0x80n, 1n);
    }
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
      assert.ok(Buffer.byteLength(encoded, 'utf8') <= 32768);
      messages.push(JSON.parse(JSON.stringify(payload)));
    },
    setImmediate: callback => { immediates.push(callback); return 1; },
    setTimeout: (callback, milliseconds) => {
      assert.equal(milliseconds, 1000); const id = ++nextTimer; timers.set(id, callback); return id;
    },
    clearTimeout: id => timers.delete(id),
    NativeFunction: function (address, ret, args, optionsArg) {
      ++native.constructed;
      assert.equal(address.value, B+0x500560n); assert.equal(ret, 'void');
      assert.deepEqual(Array.from(args), ['pointer']);
      assert.deepEqual(JSON.parse(JSON.stringify(optionsArg)),
        {abi:'win64',scheduling:'exclusive',exceptions:'propagate',traps:'none'});
      if (options.constructThrows) throw Error('unsupported API option');
      return function (a) {
        ++native.attempted; assert.ok(activeStack); assert.equal(a.value, A);
        if (options.nativeReenter) invoke();
        if (options.nativeThrows) throw Error('synthetic native failure');
        qword(A, B+0x1c3e578n); // model only the permitted FINAL postimage
        if (options.wrongPost) put(A+0x40n,[1]);
        if (options.wrongGPost) put(G+8n,[1]);
        if (options.codeAfter) put(B+0x8eb1an,[0]);
        if (options.slotAfter) qword(B+0x1d20870n,B+0x8f451n);
        ++native.returned;
      };
    },
    NativeCallback: () => { ++forbiddenCalls; throw Error('forbidden'); },
    Memory: {alloc: size => {
      const address = allocations.length === 0 ? (options.misaligned ? A+8n : A) :
        options.overlap ? A+0x80n : G;
      assert.equal(size, allocations.length === 0 ? 152 : 96);
      allocations.push({address,size}); put(address,Buffer.alloc(size,0xa5)); // explicitly DIRTY memory
      return new Pointer(address);
    }}
  };
  function load(changes) {
    const rendered = 'const EU4_BODY_PROBE_CONFIG = ' + JSON.stringify(config(changes)) + ';\n' + source;
    vm.runInNewContext(rendered, context, {timeout: 1000, filename: 'body_probe.js'});
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
  return {load, invoke, drain, deadline, final, reads, messages, put, qword, remove, allocations, writes, native,
    setBeforeRead: value => { beforeRead = value; },
    stats: () => ({hookCount, detachCount, hookAddress, timers: timers.size})};
}
function unknown(result, reason) {
  assert.equal(result.status,'unknown');
  if (reason) assert.equal(result.reason,reason);
  assert.equal(result.native_ready,false); assert.equal(result.lifetime_lease,false);
  assert.equal(result.field_game_data_writes,0); assert.equal(result.requires_host_authentication,true);
  assert.equal(result.native_game_calls_attempted,result.probe.call.attempted);
  assert.equal(result.native_game_calls_returned,result.probe.call.returned);
}
function positive(f) {
  f.load(); f.invoke(); const r=f.final();
  assert.equal(r.status,'raw_abi_postcondition_match');
  assert.equal(r.native_game_calls_attempted,1); assert.equal(r.native_game_calls_returned,1);
  assert.deepEqual(f.native,{constructed:1,attempted:1,returned:1});
  assert.equal(r.probe.spent,true); assert.equal(r.probe.allocations.A.address,h(A));
  assert.equal(r.probe.allocations.G.address,h(G));
  assert.deepEqual(r.probe.owned_writes,{attempts:4,returned:4,requested_bytes:264,completed_bytes:264});
  assert.deepEqual(f.writes.map(row=>row.size),[152,96,8,8]);
  assert.equal(r.cleanup.original_prefix32_matches,true);
  assert.equal(r.probe.after.owned.A_hex.slice(16),r.probe.before.owned.A_hex.slice(16));
  assert.equal(r.probe.after.owned.G_hex,r.probe.before.owned.G_hex);
  const before=f.reads.length; f.invoke(); f.drain(); assert.equal(f.reads.length,before);
  assert.equal(f.native.attempted,1);
  return r;
}
const corpus={schema:'EU4-BODY-PROBE-PURE-VM-CORPUS/1',config:config(),samples:{}};
test('full natural chain, dirty allocation explicitly zeroed, exact postimage and accounting',()=>{
  const f=fixture(),r=positive(f); corpus.samples.optional=r;
  assert.equal(r.counters.reads,60); assert.equal(r.counters.exact_bytes,1322);
  assert.equal(r.counters.categories.code_before.bytes,211);
  assert.equal(r.counters.categories.code_after.bytes,211);
  assert.ok(f.reads.filter(row=>row.address>=Q&&row.address<Q+0x4b0n).every(row=>row.activeStack));
  assert.equal(f.stats().detachCount,1); assert.equal(f.stats().timers,0);
});
test('null optional roots reduce only world read counts',()=>{
  const r=positive(fixture({optional:false})); corpus.samples.null=r;
  assert.equal(r.counters.reads,56); assert.equal(r.counters.exact_bytes,1290);
});
test('sixteenth callback after fifteen fifth-slot mismatches has one call and bounded reads',()=>{
  const f=fixture(); f.load(); f.qword(Q+0x440n,B);
  for(let i=0;i<15;++i) f.invoke();
  assert.equal(f.native.attempted,0); assert.equal(f.allocations.length,0);
  f.qword(Q+0x440n,B+0x8781b9n); f.invoke(); const r=f.final(); corpus.samples.sixteenth=r;
  assert.equal(r.status,'raw_abi_postcondition_match'); assert.equal(r.attempts,16);
  assert.equal(r.counters.reads,135); assert.equal(r.counters.exact_bytes,1922);
  assert.equal(f.native.attempted,1);
});
test('each full code scope rejects a changed final byte before any NativeFunction',()=>{
  for(const offset of [0x5005ccn,0x8eb1an,0x8f452n]){
    const f=fixture(); f.load(); f.put(B+offset,[0]); f.invoke(); unknown(f.final(),'body_code_mismatch');
    assert.equal(f.native.constructed,0); f.invoke(); assert.equal(f.native.attempted,0);
  }
});
test('ASLR vtable slot rejects preferred VA and wrong target',()=>{
  for(const value of [0x14008f450n,B+0x8f451n]){
    const f=fixture(); f.load(); f.qword(B+0x1d20870n,value); f.invoke();
    unknown(f.final(),'goal_virtual_slot_mismatch'); assert.equal(f.native.attempted,0);
  }
});
test('nonzero vector is refused before native construction',()=>{
  const f=fixture({corruptVector:true}); f.load(); f.invoke(); unknown(f.final(),'owned_initial_bytes_mismatch');
  assert.equal(f.native.constructed,0); f.invoke(); assert.equal(f.native.attempted,0);
});
test('misaligned or overlapping allocated spans perform zero writes and zero calls',()=>{
  for(const options of [{misaligned:true},{overlap:true}]){
    const f=fixture(options); f.load(); f.invoke(); unknown(f.final());
    assert.equal(f.writes.length,0); assert.equal(f.native.attempted,0);
  }
});
test('partial write failure preserves requested versus completed accounting',()=>{
  const f=fixture({writeThrows:true}); f.load(); f.invoke(); const r=f.final();
  unknown(r,'owned_write_failed'); assert.equal(f.native.constructed,0);
  assert.deepEqual(r.probe.owned_writes,{attempts:2,returned:1,requested_bytes:248,completed_bytes:152});
});
test('unsupported NativeFunction construction is spent unknown with zero call attempts',()=>{
  const f=fixture({constructThrows:true}); f.load(); f.invoke(); const r=f.final();
  unknown(r); assert.equal(r.probe.spent,true); assert.equal(r.native_game_calls_attempted,0);
  f.invoke(); assert.equal(f.native.constructed,1);
});
test('native exception preserves attempted one returned zero, never retries',()=>{
  const f=fixture({nativeThrows:true}); f.load(); f.invoke(); const r=f.final(); corpus.samples.native_exception=r;
  unknown(r); assert.equal(r.native_game_calls_attempted,1); assert.equal(r.native_game_calls_returned,0);
  assert.equal(r.probe.after,null); f.invoke(); assert.equal(f.native.attempted,1);
});
test('reentrant callback cannot call twice and emission includes later normal return',()=>{
  const f=fixture({nativeReenter:true}); f.load(); f.invoke(); const r=f.final();
  unknown(r,'callback_reentered'); assert.equal(r.native_game_calls_attempted,1);
  assert.equal(r.native_game_calls_returned,1); assert.equal(f.native.attempted,1);
  assert.equal(r.probe.after,null);
});
test('changed owned postimages or code/slot after call retain one returned call as unknown',()=>{
  for(const options of [{wrongPost:true},{wrongGPost:true},{codeAfter:true},{slotAfter:true}]){
    const f=fixture(options); f.load(); f.invoke(); const r=f.final(); unknown(r);
    assert.equal(r.native_game_calls_attempted,1); assert.equal(r.native_game_calls_returned,1);
    f.invoke(); assert.equal(f.native.attempted,1);
  }
});
test('cleanup failure cannot preserve postcondition success or trigger retry',()=>{
  const f=fixture({detachThrows:true}); f.load(); f.invoke(); const r=f.final(); corpus.samples.cleanup_unknown=r;
  unknown(r,'cleanup_not_confirmed'); assert.equal(r.native_game_calls_returned,1);
  assert.equal(r.cleanup.original_prefix32_matches,false); f.invoke(); assert.equal(f.native.attempted,1);
});
test('fixed identity cannot be widened; unknown emits no native call counters as old schema',()=>{
  for(const changes of [{pid:80341},{creation:'01dd5c075fcf8c27'},{base:h(B+0x1000n)},
      {schema:'EU4-FRIDA-ENTRY-CONFIG/1'},{max_attempts:17}]){
    const f=fixture(); f.load(changes); const r=f.final(); unknown(r);
    assert.equal(f.stats().hookCount,0); assert.equal('native_game_calls' in r,false);
  }
});
test('unqualified callbacks or deadline allocate nothing and make zero calls',()=>{
  const f=fixture(); f.load(); f.qword(Q+0x440n,0n); f.invoke(); f.deadline();
  const r=f.final(); unknown(r); assert.equal(f.allocations.length,0); assert.equal(f.native.attempted,0);
  assert.equal(r.probe.spent,false);
});
test.after(()=>{
  // New corpus is created once by this first new VM suite, then pure Python
  // replays the actual producer payloads without invoking JS again.
  const destination=path.join(__dirname,'offline-r1','vm-corpus.json');
  fs.writeFileSync(destination,JSON.stringify(corpus,null,2)+'\n',{flag:'wx'});
});
