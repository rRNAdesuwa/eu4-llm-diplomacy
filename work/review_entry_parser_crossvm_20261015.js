'use strict';
// Produce owned payloads using the real candidate JS inside a fake byte VM.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const crypto=require('node:crypto'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const here=path.join(root,'work/candidates/frida-entry-observer-1375-v1');
const raw=fs.readFileSync(path.join(here,'test_entry_observer.js'));
assert.equal(crypto.createHash('sha256').update(raw).digest('hex'),
  '30afc138b6b98b1fb4d5ddc0790e74ff9f385ca2457561ff27a7fc748eac654e');
assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(here,'entry_observer.js'))).digest('hex'),
  '4b2107d0a912280c271be66e5436482f1e89bfb348b326dfd25daf2d3308820e');
const definitions=raw.toString('utf8').split("test('first chain captures")[0];
const sandbox={require:name=>name==='node:test'?()=>{throw Error('No original test registration');}:require(name),
  __dirname:here,Buffer,structuredClone};
vm.runInNewContext(definitions+'\nglobalThis.api={fixture,config,B,Q,OUTER,SERVER,PENDING,PREVIOUS};',sandbox,{timeout:1000});
const {fixture,config,B,Q,OUTER,SERVER,PENDING,PREVIOUS}=sandbox.api;
const rows=[];
for(const kind of ['optional','null','sixteenth','raw_optional_max','optional_alias_current']){
  const f=fixture({optional:kind!=='null'});f.load();
  if(kind==='sixteenth'){
    f.qword(Q+0x440n,B+0x8781ban);for(let index=0;index<15;++index)f.invoke();
    f.qword(Q+0x440n,B+0x8781b9n);
  }
  if(kind==='raw_optional_max'){f.qword(PENDING,0xffffffffffffffffn);f.qword(PREVIOUS,1n);}
  if(kind==='optional_alias_current'){f.qword(OUTER+0x70n,SERVER);f.qword(OUTER+0x78n,SERVER);}
  f.invoke();const payload=f.final();assert.equal(payload.status,'structural_match');
  rows.push({case:kind,payload,config:config()});
}
console.log(JSON.stringify({schema:'EU4-ENTRY-PARSER-CROSS-LANGUAGE-VM-FIXTURES/1',cases:rows,
  source:'candidateJS in controlled NodeVM byte map; no Frida',Frida_loaded:false,game_accessed:false}));
