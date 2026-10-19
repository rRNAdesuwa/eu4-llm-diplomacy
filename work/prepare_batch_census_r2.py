"""Create a fresh census repair; preserve the sealed original candidate."""
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT/'work/candidates/v17-batch-census'
NEW = ROOT/'work/candidates/v17-batch-census-r2'


def main():
    review_raw=(OLD/'review.json').read_bytes()
    assert hashlib.sha256(review_raw).hexdigest()=='bbf3bc77eb2105728b7680fdfa9f020f618e4143d23fcf53865ebce18f0b85c9'
    review=json.loads(review_raw)
    original={name:(OLD/name).read_bytes() for name in ('census.py','test_census.py','README.md','validate.py')}
    assert all(hashlib.sha256(raw).hexdigest()==review['candidate_sources'][name]['sha256'] for name,raw in original.items())
    code=original['census.py'].decode()
    helper='''def stable_diagnostic(state):
    flags = state['snapshot_consistency']
    require(type(flags) is dict and set(flags) == {'globals_unchanged','player_unchanged','date_unchanged','atomic'}
            and all(flags[k] is True for k in ('globals_unchanged','player_unchanged','date_unchanged'))
            and flags['atomic'] is False, 'Incomplete or unstable diagnostic pass')


def diagnostic_binding(state,command,identity):
    stable_diagnostic(state)
    require(state['game_pointer'] == command['world_cookie'] and type(state['current_raw_date']) is int
            and state['current_raw_date'] == command['raw_date'], 'Diagnostic world/date differs')
    require(canonical(state['player']) == canonical(identity['player']), 'Diagnostic full player differs')


def same_handle(first,second):
    require(all(type(value) is str and re.fullmatch('0x[0-9a-fA-F]{1,16}',value) for value in (first,second)), 'Full handle encoding')
    require(int(first,16) > 0 and int(first,16) == int(second,16), 'Full handle differs')


'''
    changes=[('def resource_fields(first, second):',helper+'def resource_fields(first, second):'),
             ('    # Budget counters depend on cumulative reader traffic, not the selected state.','    stable_diagnostic(first); stable_diagnostic(second)\n    # Budget counters depend on cumulative reader traffic, not the selected state.'),
             ("            executable = ROOT.parent / 'eu4.exe'","            diagnostic_binding(first,command,identity)\n            executable = ROOT.parent / 'eu4.exe'"),
             ("                    and raw['identity']['player_handle'] == first_identity['player_handle'], 'Insult identity/world/date differs')","                    and raw['identity']['module_base'] == identity['module_base'], 'Insult identity/world/date differs')\n            same_handle(raw['identity']['player_handle'],first_identity['player_handle'])"),
             ('            count,idle = resource_fields(first,second)','            diagnostic_binding(second,command,identity)\n            count,idle = resource_fields(first,second)')]
    for before,after in changes:
        assert code.count(before)==1
        code=code.replace(before,after,1)
    tests=original['test_census.py'].decode()
    before="self.state = {'status':'bounded_snapshot','country_identities_verified':True,'memory_bytes_requested':10,"
    after=before+"\n                      'snapshot_consistency':{'globals_unchanged':True,'player_unchanged':True,'date_unchanged':True,'atomic':False},"
    assert tests.count(before)==1
    tests=tests.replace(before,after,1)
    validation=original['validate.py'].decode().replace("'test_census.py'","'test_*.py'").replace('result.testsRun == 12','result.testsRun == 19')
    # Descriptor file inventory must reference the new test, not the glob.
    validation=validation.replace("('census.py','test_*.py','README.md','validate.py')","('census.py','test_census.py','test_boundary_bindings.py','README.md','validate.py')")
    validation=validation.replace("('census.py','test_*.py','README.md','validate.py','validation.json')","('census.py','test_census.py','test_boundary_bindings.py','README.md','validate.py','validation.json')")
    new={'census.py':code.encode(),'test_census.py':tests.encode(),'validate.py':validation.encode(),
         'README.md':original['README.md']+b'\nR2 validates each diagnostic stability flag and boundary binding; compares full handles numerically to preserve canonical padded encodings. Original candidate remains sealed.\n'}
    NEW.mkdir(exist_ok=False)
    delta=''
    for name,raw in new.items():
        if name.endswith('.py'):compile(raw.decode(),name,'exec')
        with (NEW/name).open('xb') as f:f.write(raw)
        delta+=''.join(difflib.unified_diff(original[name].decode().splitlines(True),raw.decode().splitlines(True),fromfile='v1/'+name,tofile='r2/'+name))
    with (NEW/'repair.diff').open('x',encoding='utf-8') as f:f.write(delta)
    print(json.dumps({'directory':str(NEW),'diff':delta}))


if __name__=='__main__':main()
