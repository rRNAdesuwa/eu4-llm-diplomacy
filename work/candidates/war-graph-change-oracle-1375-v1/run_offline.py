"""First offline preparation of the new pure oracle, never a runtime adapter."""
import ast
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import time
import tracemalloc
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
REL=HERE.relative_to(ROOT).as_posix()
OWN=('war_graph_change_oracle.py','test_war_graph_change_oracle.py','PROTOCOL.md',
     'README.md','source-plan.json','run_offline.py','check_prepared.py')

def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def write(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
 plan=json.loads((HERE/'source-plan.json').read_text(encoding='utf-8'))
 frozen=plan['selected_sources'];reads=[]
 def guard_frozen():
  actual={}
  for name,expected in frozen.items():
   path=ROOT/name
   assert path.is_relative_to(ROOT) and path.suffix.lower() not in ('.exe','.dll','.node')
   assert path.stat().st_size<=4*1024*1024
   with path.open('rb') as f:raw=f.read(4*1024*1024+1)
   actual[name]=pin(raw);assert actual[name]==expected,name
   reads.append(dict(path=name,**actual[name]))
  assert len(frozen)<=20 and sum(r['bytes'] for r in reads)<=16*1024*1024
  return actual
 frozen_before=guard_frozen()
 own_before={REL+'/'+n:pin((HERE/n).read_bytes()) for n in OWN}
 sources={**frozen_before,**own_before}
 draft=dict(schema='WAR-GRAPH-CHANGE-ORACLE-SOURCE-MANIFEST/1',sealed=False,
            source_pins=sources,independent_source_review_pending=True,
            pure_copied_data_only=True,runtime_capture_authorized=False,
            native_ready=False,request_effect_authenticated=False)
 write(HERE/'source-manifest.json',draft)
 folder=HERE/'offline-r1';folder.mkdir(exist_ok=False)
 write(folder/'claim.json',dict(source_pins=sources,source_manifest=pin((HERE/'source-manifest.json').read_bytes()),
                              old_suites_run=0,runtime_reader_run=False,target_access=False))
 tree=ast.parse((HERE/'war_graph_change_oracle.py').read_bytes())
 assert not any(isinstance(n,(ast.Import,ast.ImportFrom)) for n in ast.walk(tree))
 forbidden={'open','exec','eval','compile','__import__','input','print'}
 assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in forbidden for n in ast.walk(tree))
 tracemalloc.start();started=time.perf_counter();output=io.StringIO()
 old_path=list(sys.path)
 try:
  sys.path.insert(0,str(HERE))
  tests=importlib.import_module('test_war_graph_change_oracle')
  suite=unittest.defaultTestLoader.loadTestsFromModule(tests)
  methods=list(unittest.defaultTestLoader.getTestCaseNames(tests.OracleTests))
  result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
 finally:sys.path[:]=old_path
 seconds=time.perf_counter()-started;peak=tracemalloc.get_traced_memory()[1]
 (folder/'tests.log').write_text(output.getvalue(),encoding='utf-8')
 frozen_after=guard_frozen()
 own_after={REL+'/'+n:pin((HERE/n).read_bytes()) for n in OWN}
 same=sources=={**frozen_after,**own_after}
 passed=result.wasSuccessful() and same and peak<768*1024*1024
 receipt=dict(schema='WAR-GRAPH-CHANGE-ORACLE-FIRST-OFFLINE/1',passed=passed,
              source_pins_before=sources,source_pins_after={**frozen_after,**own_after},
              source_guard_equal=same,new_methods=result.testsRun,method_names=methods,
              errors=len(result.errors),failures=len(result.failures),skipped=len(result.skipped),
              seconds=round(seconds,6),traced_Python_heap_peak_bytes=peak,
              memory_measurement='Python allocations only; not OS committed memory or a process-tree measurement',
              frozen_source_read_calls=len(reads),frozen_source_physical_bytes=sum(r['bytes'] for r in reads),
              frozen_source_reads=reads,core_imports=0,forbidden_core_IO_or_source_executors=0,
              old_test_methods_run=0,real_reader_executions=0,CLI_queries=0,
              game_process_accesses=0,target_PE_reads=0,Frida_REA=0,native_game_calls=0,requests=0,
              tests_log=pin((folder/'tests.log').read_bytes()),all_started_processes='only the direct tool Python child; no descendants started by this runner')
 write(folder/'receipt.json',receipt)
 if not passed:
  print(json.dumps(dict(passed=False,receipt=pin((folder/'receipt.json').read_bytes()))));return 1
 preparation=dict(schema='WAR-GRAPH-CHANGE-ORACLE-PREPARATION/1',status='candidate_source_ready_for_independent_review',
                  core=own_before[REL+'/war_graph_change_oracle.py'],
                  tests=own_before[REL+'/test_war_graph_change_oracle.py'],
                  first_offline_receipt=pin((folder/'receipt.json').read_bytes()),
                  new_test_methods=result.testsRun,old_suites_run=0,runtime_capture_authorized=False,
                  native_ready=False,request_effect_authenticated=False,
                  limitations=['No runtime adapter or capture authorization.','Address-keyed patterns do not establish war identity, creation, retirement, request effects or terms.'])
 write(HERE/'preparation.json',preparation)
 files={**own_after,REL+'/source-manifest.json':pin((HERE/'source-manifest.json').read_bytes()),
        REL+'/offline-r1/claim.json':pin((folder/'claim.json').read_bytes()),
        REL+'/offline-r1/receipt.json':pin((folder/'receipt.json').read_bytes()),
        REL+'/offline-r1/tests.log':pin((folder/'tests.log').read_bytes()),
        REL+'/preparation.json':pin((HERE/'preparation.json').read_bytes())}
 write(HERE/'delivery-manifest.json',dict(schema='WAR-GRAPH-CHANGE-ORACLE-DELIVERY/1',
                                       candidate_files=files,selected_frozen_inputs=frozen,
                                       sealed=False,runtime_capture_authorized=False,native_ready=False))
 print(json.dumps(dict(passed=True,new_methods=result.testsRun,seconds=round(seconds,6),traced_heap_peak=peak,
                       core=preparation['core'],tests=preparation['tests'],
                       receipt=pin((folder/'receipt.json').read_bytes()),
                       source_manifest=pin((HERE/'source-manifest.json').read_bytes()),
                       delivery_manifest=pin((HERE/'delivery-manifest.json').read_bytes())),indent=2))
 return 0

if __name__=='__main__':raise SystemExit(main())
