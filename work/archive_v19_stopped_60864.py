"""CREATE_NEW file-only source/session archive after held normal exit."""
from pathlib import Path
import hashlib
import json
import os

ROOT=Path(__file__).resolve().parent.parent
BUILD='work/candidates/v19-spy-bootstrap-lab-1375/build-attempt2'
CLIENT='work/candidates/v19-spy-real-client-r2-1375'
PID,CREATION,SESSION=60864,'01dd5714af7e8580','65a3e7a1ea7076f18d06ae0f2e793792'
OUTPUT=ROOT/'work/runtime/v19-stopped-source-archive-60864-20261008a'
MAX_FILE,MAX_TOTAL=4*1024*1024,32*1024*1024

def require(ok,why):
    if not ok:raise ValueError(why)

def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def read(path):
    path=Path(path).absolute();require(path.resolve().is_relative_to(ROOT),'Escaped archive input')
    for node in (path,*path.parents):
        if node.exists():require(not node.is_symlink() and not getattr(node.stat(),'st_file_attributes',0)&0x400,'Linked/reparse input')
    require(path.is_file() and path.stat().st_nlink==1,'Ordinary single-link input')
    with path.open('rb') as stream:raw=stream.read(MAX_FILE+1)
    require(len(raw)<=MAX_FILE,'Individual source budget')
    return raw

def write(path,raw):
    with path.open('xb') as stream:
        require(stream.write(raw)==len(raw),'Short archive write');stream.flush();os.fsync(stream.fileno())

def main():
    require(not OUTPUT.exists(),'Permanent archive already exists')
    files={};total=0
    def add(name,expected=None):
        nonlocal total
        require(type(name)is str and '\\' not in name and not Path(name).is_absolute() and '..' not in Path(name).parts,'Canonical relative source')
        raw=read(ROOT/name)
        if expected is not None:
            require((pin(raw)==expected if type(expected)is dict else pin(raw)['sha256']==expected),'Changed exact source '+name)
        if name in files:require(files[name]==raw,'Conflicting source '+name)
        else:files[name]=raw;total+=len(raw)
        require(len(files)<=512 and total<=MAX_TOTAL,'Aggregate archive budget')
        return raw
    inventory=json.loads(add(CLIENT+'/inventory.json','fe47d0dc016fbaa523d0f5b0010cd879fb57f7dcd33fd4edce39800b9c0b5e9d'))
    require(inventory['schema']=='EU4SPYCLIENTINVENTORY/2' and len(inventory['files'])==230,'Exact execution inventory')
    for name,sha in inventory['files'].items():add(name,sha)
    add(CLIENT+'/launcher.py','a7944c63e044e195a242b417afbea27c001ef2cae1f9d1a721bf3b83352845fe')
    add(CLIENT+'/review.json','808b490acb3845beefcf8aeb9eb7306bdc028887f9c284136749f2dcac74ed1f')
    manifest=json.loads(add(BUILD+'/build.json','b8e85393c96122949a60173ecec83f657a1d6dec24c5af0483aa7abb32d8e49a'))
    require(manifest['dll_sha256']=='d907f38e5bc108489b315a37b564d565b9fc4ff333012b62af586058691ab31f','Reviewed DLL')
    for name,desc in manifest['sources'].items():add(name,desc)
    add(BUILD+'/'+manifest['dll_name'],dict(bytes=manifest['dll_bytes'],sha256=manifest['dll_sha256']))
    for name in ('review.json','candidate-index.json','build-attempt2-validation.json'):
        add('work/candidates/v19-spy-bootstrap-lab-1375/'+name)
    for directory,sha in (
        ('v19-spy-bootstrap-external-20261008a','30d872d4c82a3897e1f5d13bba8a44bcf48368b518254aa18fd86c3001896753'),
        ('v19-real-client-r2-native-inventory-20261008a','ea4f0ccd9197c968b28d29f5aeedf0eafa711c13a5b120e35cdf6d676025ec2f')):
        add('work/review-results/'+directory+'/review.json',sha)
    census='work/candidates/v18-spy-group-census-1375/'
    for name,desc in json.loads(add(census+'input-pins.json')).items():add(name,desc)
    for name,desc in json.loads(add(census+'source-index.json'))['sources'].items():add(census+name,desc)
    add(census+'review.json')
    loader=json.loads(add(f'{BUILD}/loader-{PID}-{CREATION}.json'))
    identity=loader['identity'];require((identity['pid'],identity['creation'],identity['session'])==(PID,CREATION,SESSION),'Exact loaded identity')
    require(loader['installation']['bridge_thread_exit_status']=='0x0','Normal BridgeStart return')
    add(f'{BUILD}/bootstrap-{PID}-{CREATION}.request')
    session=f'{BUILD}/spy19-{PID}-{CREATION}-{SESSION}'
    names={'raw-events.jsonl','bootstrap-events.jsonl'}|{f'{i}.{suffix}' for i in range(1,5) for suffix in ('publisher-intent.json','request','claim')}|{f'4.item-{i}.claim' for i in range(1,6)}
    require({p.name for p in (ROOT/session).iterdir()}==names,'Exact permanent session inventory')
    for name in sorted(names):add(session+'/'+name)
    runtime_names=(
        'test-launch-v19-spy-send-20261008a.json','v19-fixture-ui-60864.json',
        'v19-spy5-census-initial-60864.json','v19-spy5-census-final-60864.json',
        'v19-selected-comparison-60864.json','v19-send-exit-60864.json','v19-stopped-ui-60864.json',
        'v19-original-complete-parser-failure-60864.json','v19-receipt-startup-60864.json',
        'v19-receipt-after-lifecycle-60864.json','v19-receipt-after-family-preview-60864.json',
        'v19-receipt-after-owned-command-60864.json')
    for name in runtime_names:add('work/runtime/'+name)
    exited=json.loads(files['work/runtime/v19-send-exit-60864.json'])
    require(exited['pid']==PID and exited['creation']==CREATION and exited['exit_observed'] is True and exited['exit_code']==0 and exited['wait_status']==0,'Held normal process exit')
    for step in ('load','lifecycle','family_preview','owned_command','send_batch'):
        directory=f'work/runtime/v19-explicit-{PID}-{CREATION}-{step}'
        require({p.name for p in (ROOT/directory).iterdir()}=={'attempt.json','completion.json','stdout','stderr'},'Exact one-shot operator attempt')
        for name in ('attempt.json','completion.json','stdout','stderr'):add(directory+'/'+name)
        completion=json.loads(files[directory+'/completion.json'])
        require(completion['exit_code']==0 and completion['child_collected'] is True and completion['timed_out'] is False,'Collected explicit step')
    for name in ('run_v19_explicit_step_60864.py','read_v19_session_receipt_1375.py',
                 'observe_test_process_exit_1375.py','finalize_v19_selected_records_60864.py',
                 'archive_v19_stopped_60864.py'):
        add('work/'+name)
    OUTPUT.mkdir();index={}
    for name,raw in sorted(files.items()):
        path=OUTPUT/'files'/name;path.parent.mkdir(parents=True,exist_ok=True);write(path,raw)
        require(pin(read(path))==pin(raw),'Archive postimage differs')
        require(read(ROOT/name)==raw,'Source changed while archiving')
        index[name]=pin(raw)
    record=dict(kind='stopped_v19_restricted_spy_source_archive',original_root=str(ROOT),
                identity=identity,files=index,total_bytes=total,
                source_origins={name:name for name in index},
                held_normal_exit_verified=True,exact_exit_filetime=exited['process_exit_filetime'],
                original_complete_parser_failed=True,corrected_complete_validation_pending=True,
                selected_state_comparison_archived=True,game_accessed=False,
                records_rewritten=False,relocated_execution_supported=False,
                effect_causality_verified=False,strict_sp_verified=False,world_epoch_verified=False,
                production_ready=False)
    raw=(json.dumps(record,sort_keys=True,indent=2)+'\n').encode('ascii');write(OUTPUT/'archive.json',raw)
    print(json.dumps(dict(archive=str(OUTPUT),files=len(index),bytes=total,index=pin(raw)),sort_keys=True))

if __name__=='__main__':main()
