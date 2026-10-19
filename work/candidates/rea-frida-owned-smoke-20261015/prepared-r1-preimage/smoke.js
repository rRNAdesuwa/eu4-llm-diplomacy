// Source-only candidate. The approved host supplies an ASCII JSON literal.
// Only Frida Process metadata is inspected; no hook or target data is read.
'use strict';
(() => {
  const c = REA_OWNED_SMOKE_CONFIG;
  if (c === null || typeof c !== 'object' || Array.isArray(c) ||
      Object.keys(c).sort().join(',') !== 'nonce,pid,schema' ||
      c.schema !== 'REA-OWNED-SMOKE-CONFIG/1' ||
      !Number.isSafeInteger(c.pid) || c.pid <= 0 || c.pid > 0xffffffff ||
      typeof c.nonce !== 'string' || !/^[0-9a-f]{32}$/.test(c.nonce)) {
    throw new Error('Invalid owned fixture configuration');
  }
  if (Process.id !== c.pid || Process.platform !== 'windows' ||
      Process.arch !== 'x64' || Process.pointerSize !== 8) {
    throw new Error('Owned fixture metadata differs');
  }
  send({schema: 'REA-OWNED-FIXTURE-SMOKE/1', pid: Process.id,
    platform: Process.platform, arch: Process.arch,
    pointer_size: Process.pointerSize, nonce: c.nonce});
})();
