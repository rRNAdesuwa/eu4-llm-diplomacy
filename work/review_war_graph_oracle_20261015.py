"""Independent file/AST review. Never executes the candidate or tests."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'work/candidates/war-graph-change-oracle-1375-v1'
OUT = ROOT / 'work/reports/war-graph-change-oracle-root-review-20261015-r1'
READS = []


def read(p):
 p = p.resolve(); assert p.is_relative_to(ROOT)
 with p.open('rb') as stream: b = stream.read(4 * 1024 * 1024 + 1)
 assert len(b) <= 4 * 1024 * 1024
 READS.append((p.relative_to(ROOT).as_posix(), len(b)))
 assert sum(n for _, n in READS) <= 16 * 1024 * 1024
 return b


def pin(p):
 b = read(p); return dict(bytes=len(b), sha256=hashlib.sha256(b).hexdigest())


def main():
 assert not OUT.exists()
 subject = HERE / 'source-manifest.json'; delivery = HERE / 'delivery-manifest.json'
 mb, db = read(subject), read(delivery)
 assert hashlib.sha256(mb).hexdigest() == '7ab9ad84b0590730c0770bfb6809a170ff7d5ef715536e8ed0c00a56eb16b33f'
 assert hashlib.sha256(db).hexdigest() == 'd64829229ecb3f27f83d39c2c0f09decd2a0a4023e6489f9528efe03fe557850'
 m, d = json.loads(mb), json.loads(db)
 assert m['sealed'] is False and m['runtime_capture_authorized'] is False and m['native_ready'] is False
 wanted = {}
 for group in (m['source_pins'], d['candidate_files'], d['selected_frozen_inputs']):
  for name, value in group.items():
   assert name not in wanted or wanted[name] == value
   wanted[name] = value
 wanted[delivery.relative_to(ROOT).as_posix()] = dict(bytes=len(db), sha256=hashlib.sha256(db).hexdigest())
 assert all(pin(ROOT / name) == value for name, value in wanted.items())
 raw = read(HERE / 'war_graph_change_oracle.py'); tree = ast.parse(raw)
 assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(tree))
 forbidden = {'open', 'exec', 'eval', 'compile', '__import__', 'input'}
 assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in forbidden for n in ast.walk(tree))
 assert all(isinstance(n, (ast.Assign, ast.ClassDef, ast.FunctionDef, ast.Expr)) for n in tree.body)
 flags = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == 'AUTHORITY_FIELDS' for t in n.targets))
 assert len(flags) == len(set(flags)) == 19
 auth = [n for n in ast.walk(tree) if isinstance(n, ast.DictComp)
         and isinstance(n.value, ast.Constant) and n.value.value is False]
 assert len(auth) == 2
 for n in ast.walk(tree):
  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'update':
   assert all(k.arg != 'authority' for k in n.keywords)
 testtree = ast.parse(read(HERE / 'test_war_graph_change_oracle.py'))
 methods = sorted(n.name for n in ast.walk(testtree) if isinstance(n, ast.FunctionDef) and n.name.startswith('test_'))
 receipt = json.loads(read(HERE / 'offline-r1/receipt.json'))
 assert receipt['passed'] is True and receipt['new_methods'] == len(methods) == 26
 assert sorted(n.split('.')[-1] for n in receipt['method_names']) == methods
 assert receipt['errors'] == receipt['failures'] == receipt['skipped'] == 0
 assert all(receipt[k] == 0 for k in ('old_test_methods_run', 'real_reader_executions', 'CLI_queries',
                                    'game_process_accesses', 'target_PE_reads', 'Frida_REA', 'native_game_calls', 'requests'))
 assert b'Ran 26 tests' in read(HERE / 'offline-r1/tests.log')
 assert all(pin(ROOT / name) == value for name, value in wanted.items())
 OUT.mkdir()
 (OUT / 'subject-draft-manifest.json').write_bytes(mb)
 (OUT / 'subject-delivery-manifest.json').write_bytes(db)
 findings = dict(schema='EU4-PURE-WAR-GRAPH-ORACLE-ROOT-REVIEW/1', status='SOURCE-READY', sealed=True,
  blocking_findings=[], core_sha256=hashlib.sha256(raw).hexdigest(), source_pin_count=len(m['source_pins']),
  inspected_source_and_delivery_files=len(wanted), first26_test_receipt_checked=True, tests_repeated=0,
  independent_new_tests=0, reason_no_extra_tests='Existing first26 cover the reviewed cycles, subclasses, aliases, limits, multi-war and ABA concerns; no uncovered blocker found.',
  semantic_review=['Fixed builtin-only schema bounds traversal and rejects raw captures/authority keys.',
   'Canonical full handles preserve nonzero generation, reserved bytes, bounded slots and TAGs.',
   'Within-view identities/sides/leaders and across-view shared handle/slot bindings are checked as data only.',
   'Comparison keys wars by observed address, reports raw/member/order patterns and never proves continuity.',
   'Empty, added, removed and multiple opposing views cannot grant creation/retirement/peace/request authority.',
   'Inputs are normalized into immutable scalars/tuples; returned mutable containers do not alias inputs.',
   'All19 output authorities are literal false on normal and unknown paths; source has no imports/I/O/executors.'],
  limitations=['Copied completeness, process identity and world metadata are not authenticated.',
   'Frozen runtime reader rejects multiple opposing wars; this copied schema cannot promote a failed capture.',
   'No host/HTTP/current-world adapter, genuine request binding, terms or persistence verification.'],
  operations=dict(candidate_executions=0, catalog_queries=0, PE_reads=0, process_accesses=0, decoder_imports=0,
                  old_tests=0, native_game_calls=0, requests=0),
  authority={name: False for name in flags}, review_read_calls=len(READS), review_physical_bytes=sum(n for _, n in READS))
 (OUT / 'independent-source-ready.json').write_text(json.dumps(findings, indent=2) + '\n', encoding='utf-8')
 evidence = dict(file_pins=wanted, read_events=READS, source_before_after_equal=True, core_AST_checked=True)
 (OUT / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
 pins = dict(wanted)
 for p in (Path(__file__), OUT / 'subject-draft-manifest.json', OUT / 'subject-delivery-manifest.json',
           OUT / 'independent-source-ready.json', OUT / 'evidence.json'):
  pins[p.relative_to(ROOT).as_posix()] = pin(p)
 manifest = dict(schema='EU4-PURE-ORACLE-ROOT-REVIEW-MANIFEST/1', file_pins=pins,
                 runtime_capture_authorized=False, native_ready=False)
 (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
 print(json.dumps(dict(status='SOURCE-READY', pins=len(pins),
  findings=pin(OUT / 'independent-source-ready.json'), manifest=pin(OUT / 'manifest.json'))))


if __name__ == '__main__': main()
