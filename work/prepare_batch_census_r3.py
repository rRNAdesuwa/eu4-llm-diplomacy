"""Fresh one-line outer-player repair; preserve both sealed predecessors."""
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT/'work/candidates/v17-batch-census-r2'
NEW = ROOT/'work/candidates/v17-batch-census-r3'

TEST = '''"""Exercise the real sample call chain up to the first selected observer."""
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import census
import test_census


class Sentinel(Exception): pass


class OuterPlayerTests(unittest.TestCase):
    def call_boundary(self, reference_handle):
        fixture=test_census.CensusTests();fixture.setUp()
        command=fixture.command
        held={'player_handle':'0x0100007a00415246'}
        reference={'module_base':'0x10000','player':{'handle':reference_handle,'slot':122}}
        state={**fixture.state,'game_pointer':command['world_cookie'],
               'current_raw_date':command['raw_date'],'player':reference['player']}
        class Process:
            reader=SimpleNamespace(base=0x10000)
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def snapshot(self):return held
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(census.lab,'OUTPUT',Path(directory)), \\
                 patch.object(census,'verify_pins'),patch.object(census,'health'), \\
                 patch.object(census.lab,'_no_links'), \\
                 patch.object(census.lab,'session_path',return_value=Path(directory)), \\
                 patch.object(census.lab,'LiveLabProcess',return_value=Process()), \\
                 patch.object(census.lab,'read_session_metadata',return_value={}), \\
                 patch.object(census.lab,'read_evidence',return_value={}), \\
                 patch.object(census.probe,'inspect_state',return_value=state), \\
                 patch.object(census.core,'read_identity',return_value=reference), \\
                 patch.object(census.core,'sample_process',side_effect=Sentinel('first observer')):
                census.sample(command)

    def test_reference_and_diagnostic_other_player_rejected_before_observers(self):
        with self.assertRaisesRegex(ValueError,'Full handle differs'):
            self.call_boundary('0x010000d800524f50')

    def test_padded_outer_handle_reaches_first_selected_observer(self):
        with self.assertRaises(Sentinel):
            self.call_boundary('0x100007a00415246')


if __name__=='__main__':unittest.main()
'''


def main():
    review_raw=(OLD/'review.json').read_bytes()
    assert hashlib.sha256(review_raw).hexdigest()=='b5cd08ce934656fbf1d1b8bb732b9bbc4753cdeef2c6b7455cc4c19d8aa06451'
    review=json.loads(review_raw)
    original={name:(OLD/name).read_bytes() for name in ('census.py','test_census.py','test_boundary_bindings.py','README.md','validate.py')}
    assert all(hashlib.sha256(raw).hexdigest()==review['candidate_sources'][name]['sha256'] for name,raw in original.items())
    code=original['census.py'].decode()
    anchor="            diagnostic_binding(first,command,identity)"
    assert code.count(anchor)==1
    code=code.replace(anchor,"            same_handle(identity['player']['handle'],first_identity['player_handle'])\n"+anchor,1)
    validation=original['validate.py'].decode().replace("'test_boundary_bindings.py'","'test_boundary_bindings.py','test_outer_player.py'").replace('result.testsRun == 19','result.testsRun == 21')
    new={**original,'census.py':code.encode(),'validate.py':validation.encode(),'test_outer_player.py':TEST.encode(),
         'README.md':original['README.md']+b'\nR3 binds the selected observers reference full player handle to the held outer process snapshot before any selected observer. Two fake-memory pipeline regressions exercise this call site. R1/R2 remain sealed.\n'}
    NEW.mkdir(exist_ok=False)
    delta=''
    for name,raw in new.items():
        if name.endswith('.py'):compile(raw.decode(),name,'exec')
        with (NEW/name).open('xb') as dst:dst.write(raw)
        delta+=''.join(difflib.unified_diff(original.get(name,b'').decode().splitlines(True),raw.decode().splitlines(True),fromfile='r2/'+name,tofile='r3/'+name))
    with (NEW/'repair.diff').open('x',encoding='utf-8',newline='\n') as dst:dst.write(delta)
    assert (OLD/'review.json').read_bytes()==review_raw
    assert all((OLD/name).read_bytes()==raw for name,raw in original.items())
    print(json.dumps({'directory':str(NEW),'census_sha256':hashlib.sha256(new['census.py']).hexdigest(),'semantic_delta':1}))


if __name__=='__main__':main()
