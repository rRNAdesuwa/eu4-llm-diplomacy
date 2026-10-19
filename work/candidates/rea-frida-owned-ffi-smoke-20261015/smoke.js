// Source candidate: only our host-created waiting fixture, never a supplied PID.
// Two fixed kernel32 calls, no hook, game object, code write or arbitrary pointer.
'use strict';
(() => {
  const c = REA_OWNED_FFI_CONFIG;
  if (c === null || typeof c !== 'object' || Array.isArray(c) ||
      Object.keys(c).sort().join(',') !== 'nonce,pid,schema' ||
      c.schema !== 'REA-OWNED-FFI-SMOKE-CONFIG/1' ||
      !Number.isSafeInteger(c.pid) || c.pid <= 0 || c.pid > 0xffffffff ||
      typeof c.nonce !== 'string' || !/^[0-9a-f]{32}$/.test(c.nonce)) {
    throw new Error('Invalid owned FFI fixture configuration');
  }
  if (Process.id !== c.pid || Process.platform !== 'windows' ||
      Process.arch !== 'x64' || Process.pointerSize !== 8) {
    throw new Error('Owned FFI fixture metadata differs');
  }
  const kernel = Process.getModuleByName('kernel32.dll');
  const options = {abi: 'win64', scheduling: 'exclusive', exceptions: 'propagate', traps: 'none'};
  const length = new NativeFunction(kernel.getExportByName('lstrlenA'), 'int', ['pointer'], options);
  const processId = new NativeFunction(kernel.getExportByName('GetCurrentProcessId'), 'uint32', [], options);
  // Keep the owning NativePointer local during the synchronous string call.
  const ownedText = Memory.allocUtf8String('rea');
  const observedLength = length(ownedText);
  const observedPid = processId();
  if (!Number.isSafeInteger(observedLength) || observedLength !== 3 ||
      !Number.isSafeInteger(observedPid) || observedPid !== c.pid) {
    throw new Error('Owned FFI return mismatch');
  }
  send({schema: 'REA-OWNED-FFI-OBSERVATION/1', pid: Process.id,
    platform: Process.platform, arch: Process.arch, pointer_size: Process.pointerSize,
    nonce: c.nonce, lstrlenA: observedLength, GetCurrentProcessId: observedPid});
})();
