"""Four new fabricated metadata/one-seed cases; no target/decoder/producer execution."""
from pathlib import Path
import hashlib,json,sys,types
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
READS=[]
def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def read(path,expected=None):
 if path.stat().st_size>4194304:raise ValueError('Ordinary4MiB')
 raw=path.read_bytes();READS.append({'path':str(path),**pin(raw)})
 if sum(x['bytes'] for x in READS)>33554432:raise ValueError('Source32MiB')
 if expected is not None and pin(raw)!=expected:raise ValueError('Source changed')
 return raw
def main():
 if len(sys.argv)!=2 or any((HERE/n).exists() for n in ['cases-claim.json','cases.json']):raise ValueError('One new frozen-case attempt')
 raw=read(HERE/'source-manifest.json')
 if pin(raw)['sha256']!=sys.argv[1]:raise ValueError('Frozen manifest hash before parse')
 manifest=json.loads(raw);sources=manifest['actual_source_pins'];owned={}
 for name,p in sources.items():owned[name]=read(ROOT/name,p)
 with(HERE/'cases-claim.json').open('x',encoding='ascii')as f:json.dump({'schema':'EU4-R89-NEW-CASES-CLAIM/1','source_manifest':pin(raw),'each_attempts':1},f)
 modules={}
 for name in ['metadata_core.py','cfg_core.py']:
  module=types.ModuleType('_r89_case_'+name.replace('.','_'));module.__file__=str(HERE/name)
  exec(compile(owned[(HERE/name).relative_to(ROOT).as_posix()],module.__file__,'exec'),module.__dict__);modules[name]=module
 meta=modules['metadata_core.py'];cfg=modules['cfg_core.py'];cases=[];failure=None
 def packed(begin,end):return begin.to_bytes(4,'little')+end.to_bytes(4,'little')+(0x1234).to_bytes(4,'little')
 def diagnostic(records):
  calls=[]
  def reader(index,reason):calls.append({'index':index,'reason':reason,'raw_hex':records[index].hex()});return records[index]
  result=meta.diagnose(reader,len(records));return {'fixture_raw_records':[v.hex()for v in records],'callback_reads':calls,'projection':result}
 def run(name,body):
  evidence=body();cases.append({'name':name,'passed':True,'runs':1,'evidence':evidence})
 try:
  def exact_and_contained():
   exact=diagnostic([packed(0xc9d00,0xc9d20),packed(0xc9d60,0xc9d70),packed(0xc9e00,0xc9e20)])
   containing=diagnostic([packed(0xc9d00,0xc9d20),packed(0xc9d40,0xc9d80),packed(0xc9e00,0xc9e20)])
   assert exact['projection']['classification']=='exact_record' and exact['projection']['metadata_valid']is True
   assert containing['projection']['classification']=='contained_nonexact' and containing['projection']['function_metadata_unknown']is True
   assert all(v['projection']['fixed_raw_window']==meta.WINDOW and v['projection']['code_extent_selected_from_metadata']is False for v in [exact,containing])
   return {'exact_extent16_not_window256':exact,'contained_local_span64_not_window256':containing}
  run('new_exact_and_nonexact_diagnostics_keep_fixed_window',exact_and_contained)
  def gap():
   value=diagnostic([packed(0xc9d00,0xc9d20),packed(0xc9e00,0xc9e20)])
   result=value['projection'];assert result['metadata_valid']is True and result['search_completed']is True
   assert result['classification']=='completed_ordered_gap' and result['seed_pdata_gap']is True and result['function_metadata_unknown']is True
   return value
  run('new_valid_ordered_gap_does_not_invent_function',gap)
  def invalid():
   overlap=diagnostic([packed(0xc9d00,0xc9e20),packed(0xc9e00,0xc9e40)])
   short=diagnostic([packed(0xc9d60,0xc9d80)[:11]])
   assert overlap['projection']['metadata_valid']is False and short['projection']['metadata_valid']is False
   assert overlap['projection']['classification']==short['projection']['classification']=='unknown_invalid_or_incomplete_metadata'
   return {'overlap':overlap,'short':short}
  run('new_overlap_and_short_record_fail_closed',invalid)
  def single_seed():
   owned_raw=b'\xe8'+(0x777777-0xc9d65).to_bytes(4,'little',signed=True)+b'\xc3'+b'\xcc'*250;starts=[]
   def decoder(chunk,cursor):
    starts.append(cursor)
    if cursor==0xc9d60:return {'rva':hex(cursor),'bytes':chunk[:5].hex(),'mnemonic':'call'}, {'kind':'call','target':0x777777,'unconditional':False}
    if cursor==0xc9d65:return {'rva':hex(cursor),'bytes':chunk[:1].hex(),'mnemonic':'ret'}, {'kind':'ret','target':None,'unconditional':False}
    raise AssertionError('Callee or unselected seed followed')
   value=cfg.run_cfg(owned_raw,decoder)
   assert cfg.SEEDS==(0xc9d60,) and starts==[0xc9d60,0xc9d65]
   assert value['explicit_seeds']==['0xc9d60'] and value['seed_semantics']=={'0xc9d60':'direct_CALL_encoding_target_not_safe_callable_proof'}
   assert value['edges'][0]['callee_followed']is False and value['instruction_count']==2
   try:cfg.run_cfg(owned_raw[:-1],decoder)
   except ValueError:refused=True
   else:refused=False
   assert refused
   return {'raw_hex':owned_raw.hex(),'decode_starts':[hex(v)for v in starts],'projection':value,'wrong255byte_window_refused_before_decode':refused}
  run('new_single_seed_call_fallthrough_and_exact_window',single_seed)
 except BaseException as error:failure={'type':type(error).__name__,'message':str(error)}
 post=read(HERE/'source-manifest.json')
 if post!=raw:failure={'type':'SourceChanged','message':'Manifest postguard'}
 for name,p in sources.items():read(ROOT/name,p)
 value={'schema':'EU4-R89-FOUR-NEW-SYNTHETIC-CASES/1','passed':failure is None,'failure':failure,'cases':cases,
  'source_manifest':pin(raw),'source_prepost_equal':post==raw,'source_reads':READS,'source_bytes':sum(x['bytes']for x in READS),
  'Capstone_imports':0,'PE_reads':0,'producer_main_executions':0,'old_cases_or_tests':0,'game_process_accesses':0,'native_game_calls':0,
  'metadata_callbacks_are_fabricated_bytes':True,'fake_decoder_used':True,'actual_authorized':False,'native_ready':False}
 with(HERE/'cases.json').open('x',encoding='ascii')as f:json.dump(value,f,indent=2);f.write('\n')
 print(json.dumps({'passed':value['passed'],'cases':len(cases),'native_ready':False}))
 return 0 if value['passed']else 1
if __name__=='__main__':raise SystemExit(main())
