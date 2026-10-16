"""First check/catalog only; no runtime status or old suite."""
import ast
import hashlib
import json
from pathlib import Path
import types
import sys

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'work/candidates/linked-truce-projection-1375-v2'
EXPECTED = '32e25244d4486417deffe61de8b048de4a94abb5b06de0400be8ab59ba291e03'


def pin(path):
    with path.open('rb') as stream:
        raw = stream.read(4*1024*1024+1)
    assert len(raw) <= 4*1024*1024
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def guard():
    assert pin(HERE/'source-manifest.json')['sha256'] == EXPECTED
    graph = json.loads((HERE/'source-manifest.json').read_text(encoding='utf-8'))
    assert graph['sealed'] is False and graph['runtime_capture_authorized'] is False
    assert all(pin(ROOT/name) == value for name, value in graph['source_pins'].items())
    return graph


def main():
    before = guard()
    old = ROOT/'work/candidates/linked-truce-projection-1375-v1/linked_truce_projection.py'
    def functions(path):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        return {node.name: ast.dump(node, include_attributes=False) for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
    a, b = functions(old), functions(HERE/'linked_truce_projection.py')
    assert a.keys() == b.keys()
    changed = sorted(name for name in a if a[name] != b[name])
    assert changed == ['base_result','project_facts','run'], changed
    assert all(a[name] == b[name] for name in ('sample_selected','observe','Libraries','JournalPort','code_guard','result_code'))
    job_path = ROOT/'work/candidates/frida-entry-observer-1375-v1/job_tree.py'
    source = job_path.read_bytes()
    assert hashlib.sha256(source).hexdigest() == '5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011'
    helper = types.ModuleType('_v2_file_jobs'); helper.__file__ = str(job_path)
    exec(compile(source,str(job_path),'exec'),helper.__dict__)
    out = HERE/'file-queries-r1';out.mkdir(exist_ok=False)
    cases = []
    for operation in ('check','catalog'):
        stdout,stderr=out/(operation+'.stdout.json'),out/(operation+'.stderr.txt')
        job = helper.run_cli_tree([sys.executable,'-B',str(HERE/'linked_truce_projection.py'),operation],str(ROOT),
            str(stdout),str(stderr),timeout_seconds=45,memory_limit=768*1024*1024)
        assert job['exit_code']==0 and job['error'] is None and job['direct_child_collected'] is True
        assert job['job_active_processes_final']==0 and job['job_total_processes']==2 and stderr.stat().st_size==0
        result=json.loads(stdout.read_text(encoding='utf-8'))
        assert result['status']=='files_verified'
        assert result['native_game_calls']==result['requests_published']==result['game_fields_written']==result['saves']==result['reloads']==0
        if operation=='catalog':assert len(result['profiles'])==4
        cases.append(dict(operation=operation,job=job,stdout=pin(stdout),stderr=pin(stderr)))
    assert guard()==before
    receipt=dict(schema='EU4-LINKED-TRUCE-V2-FILE-QUERIES/1',status='passed',source_manifest=pin(HERE/'source-manifest.json'),
        cases=cases,changed_function_AST=changed,all_other_functions_and_classes_AST_equal=True,
        game_process_accesses=0,tests_run=0,old_queries_repeated=0,native_game_calls=0,native_ready=False)
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='passed',cases=len(cases),changed_function_AST=changed,receipt=pin(out/'receipt.json'))))


if __name__=='__main__':main()
