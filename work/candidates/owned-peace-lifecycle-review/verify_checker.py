"""Disk audit and isolated MSVC build/run of the actual shared synthetic checker.

Never compiles the lifecycle module or a DLL. Never opens a game process.
Each invocation creates a new exclusive directory; evidence files use mode xb.
"""
from __future__ import annotations
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'work'))
from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg
from trace_change_subject_type import rows

EXPECTED_REVIEW = 'd54536724c804f436aef58b59722cb768bc6c40e77787d676837b871faa97fec'
FLAGS = ['/nologo', '/std:c++17', '/EHsc', '/O2', '/W4', '/WX', '/MT', '/GS', '/utf-8', '/showIncludes']

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def create_file(path, raw):
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
def json_bytes(value): return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
def run(args, cwd, env=None, timeout=60):
    value = subprocess.run(args, cwd=cwd, env=env, capture_output=True, timeout=timeout)
    if len(value.stdout) + len(value.stderr) > 1024 * 1024: raise ValueError('Output budget exceeded')
    return value

def audit(out):
    review_path = HERE / 'review.json'
    if digest(review_path) != EXPECTED_REVIEW: raise ValueError('Reviewed candidate changed')
    review = json.loads(review_path.read_bytes())
    input_hashes = [{'path': 'review.json', 'sha256': EXPECTED_REVIEW}]
    for source in review['files']:
        path = HERE / source['path']
        if digest(path) != source['sha256']: raise ValueError('Changed source: ' + source['path'])
        input_hashes.append(source)
    evidence_path = HERE / 'default-layout-evidence.json'
    if digest(evidence_path) != review['evidence_sha256']: raise ValueError('Evidence changed')
    evidence = json.loads(evidence_path.read_bytes())
    input_hashes.append({'path': evidence_path.name, 'sha256': digest(evidence_path)})
    input_hashes.append({'path': Path(__file__).name, 'sha256': digest(Path(__file__))})
    for source in evidence['inputs']:
        if digest(ROOT / source['path']) != source['sha256']: raise ValueError('Changed native report input')
    checked = run([sys.executable, '-B', str(HERE / 'prepare.py'), '--check'], ROOT)
    create_file(out / 'prepare-check.stdout.txt', checked.stdout)
    create_file(out / 'prepare-check.stderr.txt', checked.stderr)
    if checked.returncode != 0: raise ValueError('Generator check failed')
    pe = PE(ROOT.parent / 'eu4.exe')
    if hashlib.sha256(pe.data).hexdigest() != SHA: raise ValueError('Game SHA mismatch')
    md, _ = make_disassembler(Path(tempfile.gettempdir()) / 'eu4-native-analysis-deps')
    instructions = {item['rva']: item for function in evidence['new_helper_functions'].values()
                    for item in function['instructions']}
    if len(instructions) != 655: raise ValueError('Unexpected original instruction count')
    for rva, item in instructions.items():
        address = int(rva, 16); raw = bytes.fromhex(item['bytes'])
        if pe.bytes_at(address, len(raw)) != raw: raise ValueError('Instruction bytes mismatch: ' + rva)
        actual = list(md.disasm(raw, address, count=1))
        if len(actual) != 1 or actual[0].size != len(raw) or (actual[0].mnemonic + ' ' + actual[0].op_str).rstrip() != item['instruction']:
            raise ValueError('Decoded instruction mismatch: ' + rva)
    for pin in evidence['runtime_pins']:
        if pe.bytes_at(int(pin['rva'], 16), pin['size']).hex() != pin['bytes']: raise ValueError('Code pin mismatch')
    for pin in evidence['runtime_slots']:
        if pe.u64(pe.to_offset(int(pin['address'], 16))) - pe.base != int(pin['method'], 16): raise ValueError('Vtable slot mismatch')
    # Additional independent closure of c9b40's equal-size path: cad70 fills
    # existing [begin,end) with the sentinel value; it does not grow the vector.
    code, edges = bounded_cfg(pe, md, 0xcad70, window=0x1000, max_instructions=200)
    supplemental = {'entry': '0xcad70', 'instructions': rows(pe, code), 'edges': edges,
                    'role': 'c9b40 same-length hash vector sentinel fill; no allocation or container metadata write'}
    if any(i.mnemonic == 'call' for i in code): raise ValueError('Unexpected fill helper call')
    if not any(i.mnemonic == 'rep stosq' for i in code): raise ValueError('Missing expected fill loop')
    create_file(out / 'supplemental-fill-evidence.json', json_bytes(supplemental))
    check_memory_budget()
    contract = evidence['default_contract']
    if (contract['outer_demand'], contract['embedded_is_demand'], contract['known_owned_ranges_per_action']) != (1, 0, 8):
        raise ValueError('Default contract mismatch')
    if contract['type_index']['count'] != 40 or contract['type_index']['allocated_bytes'] != 0x3c0:
        raise ValueError('Type bucket contract mismatch')
    if any((h['size'], h['mask'], h['bucket_count'], h['bucket_pointer_count'], h['bucket_capacity']) != (0, 7, 8, 16, 16)
           for h in contract['hashes']): raise ValueError('Hash contract mismatch')
    source = (HERE / 'test_contract.cpp').read_text()
    if '#include "default-contract.h"' not in source or 'c::inspect(' not in source:
        raise ValueError('Harness does not directly use shared checker')
    return input_hashes, {'prepare_check_exit': checked.returncode,
                         'original_instruction_count': len(instructions),
                         'original_decoded_bytes': sum(len(bytes.fromhex(v['bytes'])) for v in instructions.values()),
                         'code_pins': len(evidence['runtime_pins']), 'vtable_slots': len(evidence['runtime_slots']),
                         'supplemental_fill_instruction_count': len(code),
                         'supplemental_fill_sha256': digest(out / 'supplemental-fill-evidence.json'),
                         'layout_contract_reviewed': True, 'passed': True}

def compiler_environment(out):
    installer = Path(os.environ['ProgramFiles(x86)']) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    found = run([str(installer), '-latest', '-products', '*', '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
                 '-property', 'installationPath'], out)
    if found.returncode != 0: raise ValueError('vswhere failed')
    install = Path(found.stdout.decode('utf-8-sig').strip())
    vcvars = install / 'VC/Auxiliary/Build/vcvars64.bat'
    if not vcvars.is_file(): raise ValueError('No x64 MSVC environment')
    if any(c in str(vcvars) for c in '&|<>^%\r\n"'): raise ValueError('Unsafe compiler batch path')
    batch = '@echo off\r\ncall "' + str(vcvars) + '" >nul\r\nif errorlevel 1 exit /b 1\r\nset\r\n'
    create_file(out / 'compiler-env.cmd', batch.encode())
    captured = run(['cmd.exe', '/u', '/d', '/c', str(out / 'compiler-env.cmd')], out)
    if captured.returncode != 0: raise ValueError('vcvars failed')
    env = dict(os.environ)
    for line in captured.stdout.decode('utf-16-le', errors='strict').splitlines():
        if '=' in line and not line.startswith('='):
            key, value = line.split('=', 1); env[key] = value
    env['VSLANG'] = '1033'
    compiler = shutil.which('cl.exe', path=env.get('Path', env.get('PATH')))
    if compiler is None: raise ValueError('cl.exe unavailable')
    return compiler, env

def main():
    parent = HERE / 'validation-results'
    parent.mkdir(exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = parent / (stamp + '-' + uuid.uuid4().hex)
    out.mkdir() # Exclusive CreateDirectory: never reuse a prior output directory.
    create_file(out / 'claim.json', json_bytes({'created_utc': stamp, 'purpose': 'shared_checker_only', 'retry': False}))
    report = {'schema': 'owned_peace_shared_checker_validation_v1', 'created_utc': stamp,
              'output_directory': out.relative_to(ROOT).as_posix(), 'passed': False,
              'game_process_access': False, 'native_peace_called': False, 'dll_built': False,
              'lifecycle_module_compiled': False, 'runtime_verified': False, 'execution_verified': False,
              'compile_exit': None, 'run_exit': None, 'check_count': 0, 'failure_count': None, 'failure_points': []}
    try:
        inputs, static = audit(out)
        report['inputs'] = inputs; report['static_audit'] = static
        compiler, env = compiler_environment(out)
        obj, exe, pdb = (out / name for name in ('test_contract.obj', 'test_contract.exe', 'compiler.pdb'))
        if any(p.exists() for p in (obj, exe, pdb)): raise FileExistsError('Refuse existing build output')
        command = [compiler, *FLAGS, str(HERE / 'test_contract.cpp'), '/Fo' + str(obj), '/Fe' + str(exe), '/Fd' + str(pdb)]
        result = run(command, out, env=env)
        create_file(out / 'compile.stdout.txt', result.stdout)
        create_file(out / 'compile.stderr.txt', result.stderr)
        report['compile_exit'] = result.returncode
        report['compiler'] = {'path': compiler, 'sha256': digest(Path(compiler)), 'flags': FLAGS}
        includes = result.stdout.decode('mbcs', errors='replace').replace('/', '\\').lower()
        report['shared_header_in_compiler_dependencies'] = str(HERE / 'default-contract.h').lower() in includes
        if result.returncode == 0:
            if not report['shared_header_in_compiler_dependencies']: raise ValueError('Actual checker header missing from compiler dependency output')
            run_result = run([str(exe)], out, timeout=15)
            create_file(out / 'run.stdout.txt', run_result.stdout)
            create_file(out / 'run.stderr.txt', run_result.stderr)
            report['run_exit'] = run_result.returncode
            text = run_result.stdout.decode('ascii', errors='strict')
            match = re.fullmatch(r'(?:FAIL: [^\r\n]+\r?\n)*(\d+) synthetic checks; (\d+) failures\r?\n', text)
            if match is None: raise ValueError('Unexpected test output')
            report['check_count'], report['failure_count'] = map(int, match.groups())
            report['failure_points'] = re.findall(r'^FAIL: (.+)$', text, re.M)
            report['artifacts'] = [{'path': p.name, 'sha256': digest(p), 'bytes': p.stat().st_size} for p in (obj, exe)]
            # Capture all actual inputs and reject a concurrent edit during build/run.
            if any(digest(HERE / source['path']) != source['sha256'] for source in inputs):
                raise ValueError('Candidate inputs changed during verification')
            report['passed'] = run_result.returncode == 0 and report['failure_count'] == 0 and report['check_count'] > 0
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    create_file(out / 'validation.json', json_bytes(report))
    print(json.dumps({'path': str(out / 'validation.json'), 'sha256': digest(out / 'validation.json'),
                      'passed': report['passed'], 'compile_exit': report['compile_exit'], 'run_exit': report['run_exit'],
                      'checks': report['check_count'], 'failures': report['failure_count'], 'error': report.get('error')}))
    return 0 if report['passed'] else 1

if __name__ == '__main__': raise SystemExit(main())
