// Pure VM capability model. No child, REA, Frida binding, OS or real NativeFunction.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync(path.join(__dirname, 'smoke.js'), 'utf8');
const config = {schema: 'REA-OWNED-FFI-SMOKE-CONFIG/1', pid: 31415, nonce: 'ab'.repeat(16)};
const expectedOptions = {abi: 'win64', scheduling: 'exclusive', exceptions: 'propagate', traps: 'none'};

function run({c = config, metadata = {}, lengthResult = 3, pidResult = 31415, failAPI = ''} = {}) {
  const calls = [], messages = [], owned = {kind: 'only-owned-rea-string'};
  const symbols = {lstrlenA: {name: 'lstrlenA'}, GetCurrentProcessId: {name: 'GetCurrentProcessId'}};
  const forbid = new Proxy({}, {get() { throw new Error('Forbidden capability'); }});
  const Process = {id: 31415, platform: 'windows', arch: 'x64', pointerSize: 8, ...metadata,
    getModuleByName(name) {
      calls.push(['module', name]);
      assert.equal(name, 'kernel32.dll');
      if (failAPI === 'module') throw new Error('Unavailable module API');
      return {getExportByName(symbol) {
        calls.push(['export', symbol]);
        assert.ok(Object.hasOwn(symbols, symbol));
        if (failAPI === 'export') throw new Error('Unavailable export API');
        return symbols[symbol];
      }};
    }};
  const context = {REA_OWNED_FFI_CONFIG: c, Process,
    Memory: {allocUtf8String(text) {
      calls.push(['alloc', text]); assert.equal(text, 'rea');
      if (failAPI === 'alloc') throw new Error('Unavailable allocation');
      return owned;
    }},
    NativeFunction: function(pointer, result, args, options) {
      calls.push(['construct', pointer.name]);
      assert.deepEqual(JSON.parse(JSON.stringify(options)), expectedOptions);
      if (failAPI === 'options') throw new Error('Unsupported options');
      if (pointer === symbols.lstrlenA) {
        assert.equal(result, 'int'); assert.deepEqual(Array.from(args), ['pointer']);
        return function(...values) {
          calls.push(['call', 'lstrlenA']);
          assert.deepEqual(values, [owned]);
          return lengthResult;
        };
      }
      assert.equal(pointer, symbols.GetCurrentProcessId);
      assert.equal(result, 'uint32'); assert.deepEqual(Array.from(args), []);
      return function(...values) {
        calls.push(['call', 'GetCurrentProcessId']);
        assert.deepEqual(values, []);
        return pidResult;
      };
    },
    send(payload, binary) {
      calls.push(['send']); assert.equal(binary, undefined);
      messages.push(JSON.parse(JSON.stringify(payload)));
    },
    Interceptor: forbid, Module: forbid, Stalker: forbid,
    NativeCallback() { throw new Error('Forbidden callback'); },
    ptr() { throw new Error('Forbidden external pointer'); },
    setTimeout() { throw new Error('Unexpected timer'); }};
  let error = null;
  try { vm.runInNewContext(source, context, {timeout: 150}); }
  catch (e) { error = e; }
  return {calls, messages, error};
}

test('exact owned pointer and two synchronous FFI calls produce one small ASCII result', () => {
  const actual = run();
  assert.equal(actual.error, null);
  assert.deepEqual(actual.calls, [['module', 'kernel32.dll'], ['export', 'lstrlenA'],
    ['construct', 'lstrlenA'], ['export', 'GetCurrentProcessId'], ['construct', 'GetCurrentProcessId'],
    ['alloc', 'rea'], ['call', 'lstrlenA'], ['call', 'GetCurrentProcessId'], ['send']]);
  assert.deepEqual(actual.messages, [{schema: 'REA-OWNED-FFI-OBSERVATION/1', pid: 31415,
    platform: 'windows', arch: 'x64', pointer_size: 8, nonce: config.nonce,
    lstrlenA: 3, GetCurrentProcessId: 31415}]);
  const wire = JSON.stringify(actual.messages[0]);
  assert.ok(wire.length <= 256 && /^[\x00-\x7f]*$/.test(wire));
});

test('malformed config and extra selectors stop before module, allocation or FFI access', () => {
  for (const c of [null, [], {...config, pid: true}, {...config, pid: 0},
    {...config, pid: 1.5}, {...config, pid: 0x100000000}, {...config, nonce: 'bad'},
    {...config, schema: 'REA-OWNED-SMOKE-CONFIG/1'}, {...config, address: '0x500560'},
    {...config, export: 'arbitrary'}]) {
    const actual = run({c});
    assert.ok(actual.error); assert.deepEqual(actual.calls, []); assert.deepEqual(actual.messages, []);
  }
});

test('wrong target metadata cannot reach any NativeFunction or allocation', () => {
  for (const metadata of [{id: 31416}, {id: true}, {platform: 'linux'}, {arch: 'ia32'}, {pointerSize: 4}]) {
    const actual = run({metadata});
    assert.ok(actual.error); assert.deepEqual(actual.calls, []); assert.deepEqual(actual.messages, []);
  }
});

test('wrong scalar results produce no success send and no retry', () => {
  for (const values of [{lengthResult: 4}, {lengthResult: true}, {lengthResult: NaN},
    {lengthResult: '3'}, {pidResult: 31416}, {pidResult: true}, {pidResult: '31415'}]) {
    const actual = run(values);
    assert.ok(actual.error); assert.deepEqual(actual.messages, []);
    assert.deepEqual(actual.calls.filter(x => x[0] === 'call'),
      [['call', 'lstrlenA'], ['call', 'GetCurrentProcessId']]);
  }
});

test('unsupported runtime API/options fail without fallback or alternate ABI', () => {
  for (const failAPI of ['module', 'export', 'options', 'alloc']) {
    const actual = run({failAPI});
    assert.ok(actual.error); assert.deepEqual(actual.messages, []);
    assert.deepEqual(actual.calls.filter(x => x[0] === 'call'), []);
    assert.ok(actual.calls.filter(x => x[0] === 'module').length === 1);
  }
});
