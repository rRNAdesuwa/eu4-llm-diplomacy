'use strict';
// Independent Node VM probes only; no Frida, REA, target or native module.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const candidate = path.join(root, 'work/candidates/frida-entry-observer-1375-v1');
const raw = fs.readFileSync(path.join(candidate, 'test_entry_observer.js'));
assert.equal(crypto.createHash('sha256').update(raw).digest('hex'),
  '30afc138b6b98b1fb4d5ddc0790e74ff9f385ca2457561ff27a7fc748eac654e');
const script = fs.readFileSync(path.join(candidate, 'entry_observer.js'));
assert.equal(crypto.createHash('sha256').update(script).digest('hex'),
  '4b2107d0a912280c271be66e5436482f1e89bfb348b326dfd25daf2d3308820e');
// Reuse only byte-map/VM fixture definitions, not the author's18 test cases.
const definitions = raw.toString('utf8').split("test('first chain captures")[0];
assert.ok(definitions.length > 5000 && definitions.length < 10000);
const sandbox = {require: name => {
  assert.notEqual(name, 'frida');
  return name === 'node:test' ? () => { throw Error('No original test registration'); } : require(name);
}, __dirname: candidate, Buffer, structuredClone};
vm.runInNewContext(definitions + '\nglobalThis.api={fixture,h,B,Q,OUTER,GAME,SERVER,HOLDER,MAP};',
  sandbox, {timeout: 1000});
const {fixture, h, B, Q, OUTER, SERVER, HOLDER, MAP} = sandbox.api;
const rows = [];
function verifyUnknown(result, reason) {
  assert.equal(result.status, 'unknown');
  if (reason) assert.equal(result.reason, reason);
  for (const name of ['native_ready','native_entry_authenticated','lifetime_lease','atomic_snapshot'])
    assert.equal(result[name], false);
}
// Owned projections must remain interpretable after all borrowed slots/world
// roots are erased; delayed cleanup may read only the fixed code prefix.
{
  const f=fixture(); f.load(); f.invoke(); const before=f.reads.length;
  for (const offset of [0n,0x40n,0x370n,0x3f0n,0x440n,0x4a8n]) f.remove(Q+offset,8);
  f.remove(B+0x242bf50n,8); f.remove(B+0x233fe78n,8);
  const result=f.final(); assert.equal(result.status,'structural_match');
  assert.equal(f.reads.length,before+1);
  assert.equal(f.reads[before].address,B+0x10a6ec0n); assert.equal(f.reads[before].size,32);
  for (const pass of [result.observation.first,result.observation.second]) {
    for (const slot of pass.slots) {
      assert.equal(slot.address,h(Q+BigInt(slot.offset)));
      assert.equal(slot.value,h(Buffer.from(slot.raw8_hex,'hex').readBigUInt64LE()));
    }
    for (const read of pass.reads) {
      const bytes=Buffer.from(read.raw_hex,'hex'); assert.equal(bytes.length,read.size);
      assert.equal(pass.fields[read.field],read.size===1 ? bytes[0] : h(bytes.readBigUInt64LE()));
    }
  }
  assert.equal(f.reads.reduce((sum,read)=>sum+read.size,0),result.counters.requested_bytes);
  assert.equal(result.counters.reads,48);assert.equal(result.counters.requested_bytes,404);
  rows.push({case:'owned_raw_replay_after_borrow_erased',status:result.status,reads:48,bytes:404,
    after_callback_reads:1,after_callback_only_fixed_prefix:true});
}
{
  const f=fixture();f.load();const q=0x7fffffff0000n-0x4b0n+8n;
  f.invoke({context:{rsp:h(q),rcx:h(MAP),r8:h(SERVER)}});
  const result=f.final();verifyUnknown(result,'address_span_out_of_range');
  assert.equal(result.counters.categories.prefilter.reads,0);
  rows.push({case:'entry_Q_span_crosses_canonical_upper',status:result.status,reason:result.reason});
}
{
  const f=fixture();f.load();f.setBeforeRead(at=>at===Q ? new Uint8Array(8) : undefined);
  f.invoke();const result=f.final();verifyUnknown(result,'short_or_invalid_read');
  assert.equal(result.counters.exact_bytes,64);
  rows.push({case:'typed_view_not_ArrayBuffer',status:result.status,reason:result.reason,exact_bytes:64});
}
{
  const f=fixture();f.load();let roots=0,marker=0;const newHolder=0xc00000n;
  f.setBeforeRead(at=>{
    if(at===B+0x242bf50n && ++roots===2){
      marker=f.reads.length;f.qword(SERVER+0x330n,newHolder);f.qword(newHolder+0x360n,MAP);
      f.remove(HOLDER+0x360n,8);
    }
  });
  f.invoke();const result=f.final();verifyUnknown(result,'projection_changed_between_passes');
  assert.equal(result.observation.first.fields.server_holder,h(HOLDER));
  assert.equal(result.observation.second.fields.server_holder,h(newHolder));
  assert.equal(result.observation.first.fields.map_object,result.observation.second.fields.map_object);
  assert.ok(!f.reads.slice(marker).some(read=>read.address===HOLDER+0x360n));
  rows.push({case:'new_holder_same_map_is_changed_not_cached',status:result.status,reason:result.reason});
}
{
  const f=fixture();f.load();f.invoke();f.setBeforeRead((at,size)=>
    at===B+0x10a6ec0n&&size===32 ? new ArrayBuffer(32) : undefined);
  const result=f.final();verifyUnknown(result,'cleanup_not_confirmed');
  assert.equal(result.cleanup.listener_detach_returned,true);
  assert.equal(result.cleanup.interceptor_flush_returned,true);
  assert.equal(result.cleanup.original_prefix32_matches,false);
  rows.push({case:'successful_detach_flush_but_wrong_prefix',status:result.status,reason:result.reason});
}
for (const changes of [{pid:0x100000000},{base:'0x00007fffffff0000'}]) {
  const f=fixture();f.load(changes);const result=f.final();verifyUnknown(result);
  assert.equal(f.stats().hookCount,0);assert.equal(f.reads.length,0);
  rows.push({case:'bad_config_'+Object.keys(changes)[0],status:result.status,reason:result.reason,hook_attempts:0,reads:0});
}
console.log(JSON.stringify({schema:'EU4-FRIDA-INDEPENDENT-NODE-VM-PROBES/1',passed:true,cases:rows,
  original18_tests_reexecuted:false,Frida_loaded:false,REA_invoked:false,game_accessed:false,
  actual_code_hook_installed:false,native_game_calls:0}));
