"""Real disk byte gates and temporary publisher boundaries only; no live CLI."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch
import launcher
from test_client import client,f,IO,HeldFake,bound_status

class LauncherTests(unittest.TestCase):
    def test_every_executed_local_pins_and_index_tamper_rejected(self):
        original=Path.open
        names=('client.py','frozen.py','provenance.py','readonly.py','graph.py','pins.json','source-index.json','inventory.json')
        for name in names:
            with self.subTest(name=name):
                target=launcher.HERE/name
                def altered(path,*args,**kwargs):
                    if Path(path)==target and args and args[0]=='rb':return io.BytesIO(b'changed')
                    return original(path,*args,**kwargs)
                # BytesIO cannot fake a regular fstat identity, so this proves a
                # reject before imports too. A second test changes bytes while
                # retaining the real file descriptor and exact length.
                with patch.object(Path,'open',altered):
                    with self.assertRaises((ValueError,OSError,io.UnsupportedOperation)):launcher.verified_graph()
    def test_same_length_disk_bytes_mismatch_before_execution(self):
        original=Path.open
        class Mutated:
            def __init__(self,f):self.f=f
            def __enter__(self):self.f.__enter__();return self
            def __exit__(self,*args):return self.f.__exit__(*args)
            def fileno(self):return self.f.fileno()
            def read(self,n):
                b=self.f.read(n);return bytes([b[0]^1])+b[1:] if b else b
        for name in ('client.py','frozen.py','provenance.py','readonly.py','graph.py','pins.json','source-index.json','inventory.json'):
            with self.subTest(name=name):
                target=launcher.HERE/name
                def altered(path,*args,**kwargs):
                    f0=original(path,*args,**kwargs)
                    return Mutated(f0) if Path(path)==target and args and args[0]=='rb' else f0
                with patch.object(Path,'open',altered):
                    with self.assertRaisesRegex(ValueError,'digest changed|Changed verified payload'):launcher.verified_graph()
    def test_private_graph_ignores_valid_origin_cached_modules(self):
        names=('client','frozen','provenance','readonly','fixed','interval','reader','protocol','build_manifest','wire','inject_probe','probe_native_state','local_config')
        fake={}
        for name in names:
            m=ModuleType(name);m.__file__=str(launcher.HERE/(name+'.py'));m.marker='untrusted';fake[name]=m
        old_path=list(sys.path)
        with patch.dict(sys.modules,fake):
            graph=launcher.verified_graph();real=graph.local('client.py');fixed=graph.local('frozen.py');injector=fixed.readonly_injector()
            self.assertFalse(hasattr(real,'marker'));self.assertFalse(hasattr(injector,'marker'))
            self.assertEqual(Path(injector.__file__),launcher.ROOT/'work/native/inject_probe.py')
            for name in names:self.assertIs(sys.modules[name],fake[name])
            self.assertEqual(sys.path,old_path)
    def test_loaded_bytes_snapshot_not_later_local_reads(self):
        graph=launcher.verified_graph();original=Path.open
        targets={launcher.HERE/n for n in ('client.py','frozen.py','provenance.py','readonly.py','graph.py','pins.json')}
        def no_late(path,*args,**kwargs):
            if Path(path) in targets:raise AssertionError('Late local source read')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',no_late):
            c=graph.local('client.py');self.assertTrue(callable(c.proposed));self.assertTrue(callable(c.readonly.Held))
    def test_missing_noncanonical_duplicate_and_boolean_inventory_refused(self):
        # Exercise parser boundaries with private fixture data and explicit test
        # digest. The public verified_graph always uses the compiled digest.
        original=Path.open;original_raw=(launcher.HERE/'inventory.json').read_bytes();obj=json.loads(original_raw)
        for mutation in ('bool_schema','missing_local','path_traversal','duplicate'):
            value=deepcopy(obj)
            if mutation=='bool_schema':value['schema']=True
            if mutation=='missing_local':value['files'].pop((launcher.HERE/'client.py').relative_to(launcher.ROOT).as_posix())
            if mutation=='path_traversal':value['files']['../bad.py']='0'*64
            raw=json.dumps(value).encode()
            if mutation=='duplicate':raw=b'{"schema":"EU4SPYCLIENTINVENTORY/2","schema":"EU4SPYCLIENTINVENTORY/2","files":{}}'
            # Call the JSON/schema path directly by replacing only the ordinary
            # inventory reader; all actual file reads remain bounded and hashed.
            ordinary=launcher._ordinary
            def supplied(path,root,limit):return raw if Path(path)==launcher.HERE/'inventory.json' else ordinary(path,root,limit)
            with patch.object(launcher,'_ordinary',supplied):
                with self.assertRaises(ValueError):launcher._verify(launcher.ROOT,launcher.HERE,hashlib.sha256(raw).hexdigest())
    def test_untrusted_library_and_public_nonisolated_entry_refuse(self):
        self.assertEqual(sys.flags.isolated,0)
        with self.assertRaisesRegex(ValueError,'python -I -B'):launcher.main(['--help'])
        raw=(launcher.HERE/'frozen.py').read_bytes()
        with self.assertRaisesRegex(RuntimeError,'verified private launcher'):exec(compile(raw,str(launcher.HERE/'frozen.py'),'exec'),{'__file__':str(launcher.HERE/'frozen.py'),'__name__':'not_launcher'})
    def test_legacy_and_bootstrap_origins_preserved(self):
        graph=launcher.verified_graph();x=graph.local('frozen.py')
        self.assertEqual(Path(x.loader.__file__),x.BOOT/'loader.py')
        self.assertEqual(Path(x.reader.__file__),x.PURE/'reader.py')
        self.assertEqual(Path(x.files.__file__),x.PURE/'files.py')
        self.assertEqual(Path(x.b.__file__),x.BOOT/'build_manifest.py')
        self.assertFalse(any(name.startswith('bridge/') for name in x.PINS))

class FinalBoundaryTests(unittest.TestCase):
    def run_after_identity(self,final_time):
        context=tempfile.TemporaryDirectory();self.addCleanup(context.cleanup);temp=Path(context.name)
        s=bound_status();identity=s['identity'];path=f.wire.session_path(temp,identity);path.mkdir()
        io0=IO(s);io0.clock=10001;io0.now=lambda:io0.clock
        held=HeldFake()
        def delay():held.identities+=1;io0.clock=final_time
        held.identity_check=delay
        return temp,identity,path,io0,held
    def test_final_identity_ttl_freshness_rollback_three_original_counterexamples(self):
        for final_time in (70001,12501,10000):
            with self.subTest(final_time=final_time):
                temp,i,path,io0,held=self.run_after_identity(final_time)
                with self.assertRaises(ValueError):client._publish(temp,i,'lifecycle',held,io0)
                self.assertEqual(held.identities,1);self.assertEqual(io0.moves,0)
                self.assertTrue((path/'1.publisher-intent.json').is_file());self.assertTrue((path/'1.publisher-pending').is_file());self.assertFalse((path/'1.request').exists())
                with self.assertRaises(ValueError):client._publish(temp,i,'lifecycle',HeldFake(),IO(bound_status()))
    def test_final_freshness_equal_boundary_allowed_plus_one_rejected(self):
        temp,i,path,io0,held=self.run_after_identity(12500)
        self.assertTrue(client._publish(temp,i,'lifecycle',held,io0)['request_written']);self.assertEqual(io0.moves,1)
    def test_final_clock_type_aliases_and_exceptions_preserve_pending(self):
        for final_time in (True,10001.0,-1,2**64):
            temp,i,path,io0,held=self.run_after_identity(final_time)
            with self.assertRaises(ValueError):client._publish(temp,i,'lifecycle',held,io0)
            self.assertEqual(io0.moves,0);self.assertTrue((path/'1.publisher-pending').exists())
        temp,i,path,io0,held=self.run_after_identity(10001)
        def unknown_identity():raise OSError('Final held identity unavailable')
        held.identity_check=unknown_identity
        with self.assertRaises(OSError):client._publish(temp,i,'lifecycle',held,io0)
        self.assertEqual(io0.moves,0);self.assertTrue((path/'1.publisher-pending').exists())
    def test_final_original_expiry_not_replaced_by_recomputed_ttl(self):
        # A fresh later health report can arrive after preparing the packet;
        # it must not extend that packet's original expiry.
        for final_time,allowed in ((70000,True),(70001,False),(70002,False)):
            with self.subTest(final_time=final_time):
                temp,i,path,io0,held=self.run_after_identity(final_time)
                base=io0.inspect
                def fresh(*args):
                    value=base(*args)
                    if io0.reads==3:
                        io0.clock=69999;value['last_owner_uptime_ms']=69999
                    return value
                io0.inspect=fresh
                if allowed:self.assertTrue(client._publish(temp,i,'lifecycle',held,io0)['request_written'])
                else:
                    with self.assertRaisesRegex(ValueError,'Expired after final'):client._publish(temp,i,'lifecycle',held,io0)
                self.assertEqual(io0.moves,int(allowed))

if __name__=='__main__':unittest.main()
