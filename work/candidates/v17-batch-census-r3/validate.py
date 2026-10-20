"""Offline census dependency and pure binding validation; no memory sampling."""
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
import census

HERE = Path(__file__).resolve().parent


def descriptor(path):
    raw = census.lab.read_bounded(path,128*1024)
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def main():
    files = [census.ROOT / name for name in census.PINS]
    files += [HERE / name for name in ('census.py','test_census.py','test_boundary_bindings.py','test_outer_player.py','README.md','validate.py')]
    before = {p.relative_to(census.ROOT).as_posix():descriptor(p) for p in files}
    census.verify_pins()
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(HERE),pattern='test_*.py')
    result = unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    after = {p.relative_to(census.ROOT).as_posix():descriptor(p) for p in files}
    assert before == after and result.wasSuccessful() and result.testsRun == 21
    report = {'schema_version':1,'purpose':'offline_batch_census_validation',
              'tests':result.testsRun,'passed':True,'input_files':before,'inputs_unchanged':True,
              'test_output':stream.getvalue(),'game_accessed':False,'native_called':False,
              'independent_approval':False}
    with (HERE/'validation.json').open('x',encoding='utf-8',newline='\n') as dst:
        json.dump(report,dst,indent=2); dst.write('\n')
    review = {'schema_version':1,'purpose':'root_authored_batch_census_candidate',
              'status':'sealed_for_independent_review','candidate_sources':{n:descriptor(HERE/n) for n in ('census.py','test_census.py','test_boundary_bindings.py','test_outer_player.py','README.md','validate.py','validation.json')},
              'source_pins':census.PINS,'game_accessed':False,'native_called':False,
              'production_ready':False,'shell_sessions_collected':True}
    with (HERE/'review.json').open('x',encoding='utf-8',newline='\n') as dst:
        json.dump(review,dst,indent=2); dst.write('\n')
    print(json.dumps({'tests':result.testsRun,'passed':True,'inputs_unchanged':True,
                      'review_sha256':descriptor(HERE/'review.json')['sha256']}))


if __name__ == '__main__':main()
