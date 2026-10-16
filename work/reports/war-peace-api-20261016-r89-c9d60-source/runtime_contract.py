"""R89 future grant/source gate. No target, decoder or process API."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BUILD='work/reports/war-peace-api-20261016-r89-root-source-authorization/authorization.json'
BUILD_PIN={'bytes':9647,'sha256':'c6e844b1d6f8e635d673caab18c5c2eade3c7faa2fa8109810f3bb95f003f012'}
R87='work/reports/war-peace-api-20261016-r87-dual-frontier-source/'
UPSTREAM={'subject_actual_manifest': {'bytes': 34662, 'path': 'work/reports/war-peace-api-20261016-r87-dual-frontier-source/actual-sealed-r1/actual-manifest.json', 'sha256': '71e766158fdaf6f80a2dc55bf5c4fb8177bfcfcdaee35f1f7860c1fec0828b0d'}, 'subject_capture_pin': {'bytes': 140752, 'path': 'work/reports/war-peace-api-20261016-r87-dual-frontier-source/capture.json', 'sha256': '0f4ab901823ec893da60ebdeb9d237c1feec469cf67f4bed223b660a070955ec'}, 'subject_contract_pin': {'bytes': 7679, 'path': 'work/reports/war-peace-api-20261016-r87-dual-frontier-source/actual-sealed-r1/contract.json', 'sha256': '5e114f5c0efd47cbf92279bdf0d638732a40ae3b8a9d0f554d56c51df2304845'}, 'subject_owned_pin': {'bytes': 1099, 'path': 'work/reports/war-peace-api-20261016-r87-dual-frontier-source/owned-code.json', 'sha256': 'dd4d12d21f9903eacfbcaeb1e6769e8ebb8f1bf98715cfdc6f0e0ea7bc125a69'}, 'subject_selected_pin': {'bytes': 47217, 'path': 'work/reports/war-peace-api-20261016-r87-dual-frontier-source/actual-sealed-r1/selected-cfg.json', 'sha256': '659b804677b9ffb2635afcc34ae46c26cd6e9b815a7515bf1faa8d0173db4f40'}}
UPSTREAM_REVIEW={'findings': {'path': 'work/reports/war-peace-api-20261016-r87-actual-independent-review/findings.json', 'bytes': 12526, 'sha256': 'dd62d0fb531ecaccc51d4812ad317b92a04bf121580f5be35b8d65d4abd458e0'}, 'manifest': {'path': 'work/reports/war-peace-api-20261016-r87-actual-independent-review/manifest.json', 'bytes': 30861, 'sha256': '26997cc636afbe1940b8037fca028d85fd70ac2175e5856fbb6c2d94a2424bfd'}}
WINDOW={'begin':'0xc9d60','end_exclusive':'0xc9e60','bytes':256,'seeds':['0xc9d60']}
SEED_SEMANTICS={'0xc9d60':'direct_CALL_encoding_target_not_safe_callable_proof'}

def require(ok,why):
 if not ok:raise ValueError(why)
def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def decode(raw):
 def pairs(items):
  result={}
  for k,v in items:
   require(k not in result,'Duplicate JSON key');result[k]=v
  return result
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:require(False,'Nonfinite JSON'))
def local(name):
 require(type(name)is str and name and '\\' not in name,'Canonical source path')
 p=Path(name);require(not p.is_absolute() and '..' not in p.parts,'Local source path')
 result=ROOT/p;require(result.resolve().is_relative_to(ROOT),'Source path escaped project')
 return result
def reference(read,value):
 require(type(value)is dict and set(value)=={'path','bytes','sha256'},'Exact reference triple')
 require(type(value['bytes'])is int and 0<value['bytes']<=4194304,'Ordinary source bytes')
 require(type(value['sha256'])is str and re.fullmatch('[0-9a-f]{64}',value['sha256']),'Exact source SHA')
 raw=read(local(value['path']));require(pin(raw)=={k:value[k] for k in ('bytes','sha256')},'Reference raw pin')
 return raw
def verify(read,sha):
 require(type(sha)is str and re.fullmatch('[0-9a-f]{64}',sha),'Exact new root grant SHA argument')
 build_raw=read(ROOT/BUILD);require(pin(build_raw)==BUILD_PIN,'Root source grant before parse');build=decode(build_raw)
 auth_raw=read(HERE/'run-authorization.json');require(pin(auth_raw)['sha256']==sha,'Once grant raw SHA before parse');auth=decode(auth_raw)
 require(auth.get('schema')=='EU4-R89-C9D60-FIXED-PREFIX-ROOT-AUTHORIZATION/1' and auth.get('sealed')is True
  and auth.get('root_explicit_start_received')is True and auth.get('single_attempt')is True,'New R89 root once grant required')
 require(auth.get('operation')=='one-fixed-direct-call-prefix-static' and auth.get('fixed_raw_window')==WINDOW,'No range/seed override')
 require(auth.get('seed_semantics')==SEED_SEMANTICS,'Direct CALL evidence does not authorize native execution')
 require(auth.get('metadata_policy')==build['metadata_policy'] and auth.get('gap_policy')==build['gap_policy'],'Exact diagnostic-only policy')
 require(auth.get('Job')==build['Job'] and auth.get('source_limits')==build['source_limits'],'No Job/source budget override')
 require(auth.get('source_build_authorization')=={'path':BUILD,**BUILD_PIN},'Source grant binding')
 manifest_raw=read(HERE/'source-manifest.json');require(pin(manifest_raw)==auth['source_manifest'],'Authorized manifest buffer before parse')
 manifest=decode(manifest_raw)
 require(manifest.get('sealed')is True and manifest.get('schema')=='EU4-R89-FIXED-PREFIX-SOURCE/1'
  and manifest.get('fixed_raw_window')==WINDOW,'Exact R89 frozen source schema')
 data={};pins=manifest['actual_source_pins']
 require(type(pins)is dict and 1<=len(pins)<=64,'Flat ordinary source graph bound')
 for name,p in pins.items():
  require(not name.startswith('work/deps/'),'Engine metadata is excluded before gates')
  raw=read(local(name));require(pin(raw)==p,'Fixed actual source before execution');data[name]=raw
 for name,p in build['fixed_inputs'].items():require(name in data and pin(data[name])==p,'Fixed source-build input')
 fields=[('producer_pin','produce.py'),('entry_seed_pin','entry-seed.json'),('cfg_core_pin','cfg_core.py'),
  ('metadata_core_pin','metadata_core.py'),('launcher_pin','launch_once.py')]
 for field,file in fields:
  name=(HERE/file).relative_to(ROOT).as_posix();require(auth.get(field)==pin(data[name]),'Exact executable subject '+field)
 subjects={'subject_source_manifest':pin(manifest_raw),'subject_producer':auth['producer_pin'],
  'subject_entry_seed':auth['entry_seed_pin'],'subject_cfg_core':auth['cfg_core_pin'],
  'subject_metadata_core':auth['metadata_core_pin'],'subject_launcher':auth['launcher_pin']}
 require(auth.get('upstream_R87_full_review')==UPSTREAM_REVIEW,'Exact accepted R87 full-review pair')
 review_pins={};upstream_findings=None
 for name in ['upstream_R87_full_review','root_raw_entry_review','source_peer_review']:
  group=auth[name];require(type(group)is dict and set(group)=={'findings','manifest'},'Exact review pair')
  raw=reference(read,group['findings']);reference(read,group['manifest']);review=decode(raw)
  review_pins.update({r['path']:{k:r[k] for k in ('bytes','sha256')} for r in group.values()})
  require(review.get('sealed')is True and review.get('passed')is True and review.get('blocking_findings')==[],'Passed non-author review')
  if name=='upstream_R87_full_review':
   require(all(review.get(k)==v for k,v in UPSTREAM.items()),'Exact complete R87 actual subjects')
   upstream_findings=group['findings']
  else:
   require(all(review.get(k)==v for k,v in subjects.items()),'Exact new R89 review subjects')
   if name=='root_raw_entry_review':
    require(review.get('scope')=='raw_direct_call_fixed_prefix_seed_only'
     and review.get('fixed_raw_window')==WINDOW and review.get('metadata_policy')==build['metadata_policy']
     and review.get('gap_policy')==build['gap_policy'],'Exact raw CALL/window/diagnostic policy')
 acceptance_ref=auth['upstream_R87_root_acceptance'];araw=reference(read,acceptance_ref);acceptance=decode(araw)
 require(acceptance.get('sealed')is True and acceptance.get('accepted')is True
  and acceptance.get('subject_full_review')==upstream_findings
  and acceptance.get('subject_actual_manifest')==UPSTREAM['subject_actual_manifest'],'Separate root R87 acceptance')
 review_pins[acceptance_ref['path']]={k:acceptance_ref[k] for k in ('bytes','sha256')}
 return {'auth':auth,'auth_pin':pin(auth_raw),'manifest':manifest,'manifest_pin':pin(manifest_raw),
  'data':data,'review_pins':review_pins,'build':build}
