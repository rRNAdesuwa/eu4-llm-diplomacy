// Future pure Node VM tests. No child process, Frida binding, REA or game.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync(path.join(__dirname, 'smoke.js'), 'utf8');
const base = {schema: 'REA-OWNED-SMOKE-CONFIG/1', pid: 31415, nonce: 'ab'.repeat(16)};

function run(config = base, changes = {}) {
  const messages = [], accessed = [];
  const metadata = {...{id: 31415, platform: 'windows', arch: 'x64', pointerSize: 8}, ...changes};
  const Process = new Proxy(metadata, {get(target, key) {
    if (!Object.hasOwn(target, key)) throw new Error('Unexpected Process access');
    accessed.push(key);
    return target[key];
  }});
  const forbidden = new Proxy({}, {get() { throw new Error('Forbidden instrumentation API'); }});
  const context = {REA_OWNED_SMOKE_CONFIG: config, Process,
    send(payload, binary) {
      assert.equal(binary, undefined);
      messages.push(JSON.parse(JSON.stringify(payload)));
    }, Interceptor: forbidden, Memory: forbidden, Module: forbidden,
    NativeFunction() { throw new Error('Forbidden native call'); },
    ptr() { throw new Error('Forbidden pointer'); },
    setTimeout() { throw new Error('Unexpected timer'); }};
  vm.runInNewContext(source, context, {timeout: 100});
  return {messages, accessed};
}

test('one ASCII owned metadata send, with no instrumentation or memory APIs', () => {
  const actual = run();
  assert.deepEqual(actual.messages, [{schema: 'REA-OWNED-FIXTURE-SMOKE/1', pid: 31415,
    platform: 'windows', arch: 'x64', pointer_size: 8, nonce: base.nonce}]);
  assert.equal(JSON.stringify(actual.messages[0]).length < 256, true);
  assert.equal([...JSON.stringify(actual.messages[0])].every(x => x.charCodeAt(0) < 128), true);
  assert.deepEqual(new Set(actual.accessed), new Set(['id', 'platform', 'arch', 'pointerSize']));
});

test('invalid config, extra target selectors and wrong nonce fail before send', () => {
  for (const c of [null, [], {...base, pid: true}, {...base, pid: 3.5},
    {...base, pid: 0}, {...base, pid: 0x100000000}, {...base, nonce: 'xyz'},
    {...base, schema: 'other'}, {...base, address: '0x10a6ec0'}]) {
    assert.throws(() => run(c));
  }
});

test('a mismatched owned PID, platform, arch or pointer width produces no success', () => {
  for (const c of [{id: 31416}, {platform: 'linux'}, {arch: 'ia32'}, {pointerSize: 4}]) {
    assert.throws(() => run(base, c));
  }
});
