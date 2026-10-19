"""Run real candidate modules and existing V1 tests from an isolated temporary tree."""
from pathlib import Path
import hashlib,json,sys,tempfile,types,unittest
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def main():
    index=json.loads((HERE/'candidate-index.json').read_bytes())
    with tempfile.TemporaryDirectory(prefix='eu4-v2-offline-')as td:
        tree=Path(td)
        # Only known pinned sources and generated outputs, no process artifacts.
        merged={p:(ROOT/p,d)for p,d in index['inputs'].items()}
        merged.update({p:(HERE/'files'/p,d)for p,d in index['outputs'].items()})
        for p,(source,d)in merged.items():
            b=source.read_bytes();assert len(b)==d['bytes']and hashlib.sha256(b).hexdigest()==d['sha256']
            dest=tree/p;dest.parent.mkdir(parents=True,exist_ok=True)
            with dest.open('xb')as f:f.write(b)
        sys.path.insert(0,str(ROOT))
        # Namespace overlay serves unchanged support from the repository.
        for name,paths in [('bridge',[tree/'bridge',ROOT/'bridge']),('bridge.tests',[tree/'bridge/tests',ROOT/'bridge/tests']),('tools',[tree/'tools',ROOT/'tools'])]:
            m=types.ModuleType(name);m.__path__=[str(p)for p in paths];sys.modules[name]=m
            if '.' in name:
                parent,child=name.rsplit('.',1);setattr(sys.modules[parent],child,m)
        from bridge import diplomacy_api as api,diplomacy_contract_v2 as contract,diplomacy_service as service
        from tools import diplomacy as cli,serve_diplomacy as serve
        for m in (api,contract,service,cli,serve):assert Path(m.__file__).is_relative_to(tree)
        names=['bridge.tests.test_diplomacy_api','bridge.tests.test_diplomacy_reconciliation','bridge.tests.test_diplomacy_contract_v2']
        suite=unittest.defaultTestLoader.loadTestsFromNames(names)
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful()else 1
if __name__=='__main__':raise SystemExit(main())
