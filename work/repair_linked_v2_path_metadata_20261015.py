"""Correct retained path-address metadata, without repeating suites or captures."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT/'work/candidates/linked-truce-projection-1375-v2'


def pin(path):
    b=path.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())


def functions(raw):
    return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(raw).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}


def main():
    assert pin(HERE/'linked_truce_projection.py')['sha256']=='f75d0a5dd000c6d513d9e14cf784ff95b45a5e4132e153c3758d981f6e8c69a2'
    assert pin(HERE/'source-manifest.json')['sha256']=='32e25244d4486417deffe61de8b048de4a94abb5b06de0400be8ab59ba291e03'
    pre=HERE/'path-metadata-preimage-r1';pre.mkdir(exist_ok=False)
    names=('linked_truce_projection.py','prepare_source.py','source-manifest.json','preparation.json')
    before={n:pin(HERE/n) for n in names}
    for n in names:(pre/n).write_bytes((HERE/n).read_bytes())
    first=(HERE/'linked_truce_projection.py').read_text(encoding='utf-8')
    for path in (HERE/'linked_truce_projection.py',HERE/'prepare_source.py',ROOT/'work/build_linked_truce_v2_20261015.py'):
        text=path.read_text(encoding='utf-8');assert text.count('2f1603->2f160b')==1
        path.write_text(text.replace('2f1603->2f160b','2f1601->2f160b',1),encoding='utf-8',newline='\n')
    assert functions(first)==functions((HERE/'linked_truce_projection.py').read_text(encoding='utf-8'))
    m=json.loads((HERE/'source-manifest.json').read_text(encoding='utf-8'));rel=HERE.relative_to(ROOT).as_posix()
    for n in ('linked_truce_projection.py','prepare_source.py'):m['source_pins'][rel+'/'+n]=pin(HERE/n)
    (HERE/'source-manifest.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
    assert all(pin(ROOT/n)==p for n,p in m['source_pins'].items())
    receipt=dict(schema='EU4-V2-PATH-METADATA-REPAIR/1',before=before,
        after={n:pin(HERE/n) for n in names if n!='preparation.json'},
        change='D path descriptor 2f1603->2f160b becomes exact JNE edge 2f1601->2f160b',
        all_functions_and_classes_AST_equal=True,predicate_sampler_host_logic_changed=False,
        tests_repeated=0,file_queries_repeated=0,game_process_accesses=0,native_game_calls=0,native_ready=False)
    (pre/'repair.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    prep=json.loads((HERE/'preparation.json').read_text(encoding='utf-8'))
    for n in ('linked_truce_projection.py','source-manifest.json'):prep['files'][n]=pin(HERE/n)
    prep['files']['path-metadata-preimage-r1/repair.json']=pin(pre/'repair.json')
    prep['offline_and_file_query_receipts_are_pre_metadata_delta_witnesses']=True
    prep['all_predicate_sampler_host_function_AST_unchanged_after_delta']=True
    (HERE/'preparation.json').write_text(json.dumps(prep,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='passed',CLI=pin(HERE/'linked_truce_projection.py'),draft=pin(HERE/'source-manifest.json'),
        preparation=pin(HERE/'preparation.json'),repair=pin(pre/'repair.json'))))


if __name__=='__main__':main()
