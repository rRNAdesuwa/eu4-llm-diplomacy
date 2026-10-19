"""Explicit read-only sample for the new paused baseline; no engine call."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'work/candidates/spy-modifier-observer-1375'
BASE=ROOT/'work/runtime'
PID=65304
CREATION='01dd56d71677eb60'
WORLD=0x2691a70c040
DATE=56456976
FAMILIES=('corrupt_officials','sabotage_reputation','sow_discontent','slander_merchants','sabotage_recruitment')
PINS={
 'work/candidates/spy-modifier-observer-1375/review.json':'9b9830cf4eafbc5620fa53810ce1b790dfec9c96a44afb9f45b93660ec73ee85',
 'work/candidates/spy-modifier-observer-1375/observer.py':'d386524d543d96509fe4230e5fd02b01bc7f404f5419054ae2a84f66fdb13e48',
 'work/review-results/spy-modifier-observer-native-inventory-20261008a/review.json':'cba5fc6a916bdeaae7d9f4b8d903d992120357788b8fe011e0c0ae86c5131f00',
}

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(65536): h.update(block)
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--family',required=True,choices=FAMILIES)
    args=parser.parse_args()
    for key,value in PINS.items():
        if sha(ROOT/key)!=value: raise ValueError('Reviewed source changed: '+key)
    output=BASE/f'spy-ro-65304-{args.family}.json'
    with output.open('xb') as stream:
        record=dict(schema_version=1,kind='explicit_spy_ro_attempt',pid=PID,creation=CREATION,
                    world_cookie=hex(WORLD),raw_date=DATE,family=args.family,target='ENG',
                    source_pins=PINS,game_native_calls=False,individual_effect_verified=False,
                    production_ready=False,window_pause_observed=True,paused_native_verified=False)
        try:
            spec=importlib.util.spec_from_file_location('_root_spy_ro_65304',HERE/'observer.py')
            observer=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(observer)
            result=observer.sample_process(pid=PID,creation=CREATION,executable=ROOT.parent/'eu4.exe',family=args.family,target='ENG')
            identity=result['snapshot']['identity']
            if identity['game']!=WORLD or identity['date']!=DATE:
                raise ValueError('Explicit baseline world/date changed')
            record.update(status='captured',report=result)
        except Exception as error:
            record.update(status='unsupported_or_read_failed',error_type=type(error).__name__,error=str(error))
        stream.write((json.dumps(record,sort_keys=True,indent=2)+'\n').encode())
    print(json.dumps(dict(output=output.relative_to(ROOT).as_posix(),status=record['status'],
                         error=record.get('error'),sha256=sha(output),native_calls=False)))
    return 0 if record['status']=='captured' else 1

if __name__=='__main__':
    raise SystemExit(main())
