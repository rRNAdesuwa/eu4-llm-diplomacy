"""Build/run this isolated synthetic EXE with existing VS. Never select the game.

The only queried process handles are Popen handles for this runner's own children.
Each stage is collected, with 768MiB/60s limits; no PID lookup or injection API.
"""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VCVARS = Path('C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Auxiliary/Build/vcvars64.bat')
SOURCES = ('DESIGN.md', 'forward_layout.h', 'entry_forward_model.asm', 'test_forward_model.cpp', 'build_offline.py')
LIMIT = 768*1024*1024


def pin(path):
    raw = path.read_bytes()
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def write_new(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)


def default_pins():
    path = ROOT/'bridge/native/tag_diplomacy_1375_v31/build-7/build/build.json'
    data = json.loads(path.read_bytes())
    assert len(data['source_pins']) == 44
    for name, expected in data['source_pins'].items():
        assert pin(ROOT/name) == expected, name
    assert pin(path.parent/data['DLL']) == data['dll']
    return dict(build_manifest=pin(path), source_pins=data['source_pins'], dll=data['dll'])


class MemoryCounters(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
            'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
            'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]


info = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
info.argtypes = (wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD)
info.restype = wintypes.BOOL


def child_memory(handle):
    counters = MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not info(wintypes.HANDLE(int(handle)), ctypes.byref(counters), counters.cb):
        raise OSError(ctypes.get_last_error(), 'own child memory query failed')
    return counters.PagefileUsage, counters.PeakPagefileUsage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt')
    parser.add_argument('--emit-build-env', action='store_true')
    args = parser.parse_args()
    if args.emit_build_env:
        assert args.attempt is None
        # Never enumerate/log the inherited environment. Emit these four
        # toolchain values only; secrets remain outside every build artifact.
        print(json.dumps({name: os.environ.get(name, '') for name in ('PATH', 'INCLUDE', 'LIB', 'LIBPATH')}))
        return 0
    assert args.attempt is not None
    assert args.attempt.isdecimal() and 1 <= int(args.attempt) < 100
    out = HERE/('build-attempt-'+args.attempt)
    out.mkdir(exist_ok=False)
    before = default_pins()
    source_pins = {name: pin(HERE/name) for name in SOURCES}
    stages = []
    receipt = dict(schema='EU4-ENTRY-FORWARD-OFFLINE-BUILD/1', source_pins=source_pins,
        vcvars=dict(path=str(VCVARS), **pin(VCVARS)), stages=stages,
        sealed=False, independent_review_pending=True, game_accessed=False,
        game_native_calls=0, DLL_created_or_loaded=False, installer_created=False,
        native_entry_authenticated=False, native_ready=False, lifetime_lease=False,
        atomic_snapshot=False, exception_unwind_verified=False, AVX_xstate_preserved=False,
        game_installation_provenance=False, own_child_memory_limit=LIMIT,
        queries_only_Popen_child_handles=True)

    def execute(name, command, env=None):
        output = out/(name+'.stdout.txt')
        started = time.monotonic()
        peak = 0
        code = None
        failure = None
        with output.open('xb') as stream:
            child = subprocess.Popen(command, cwd=out, env=env, stdout=stream,
                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                while child.poll() is None:
                    current, observed_peak = child_memory(child._handle)
                    peak = max(peak, observed_peak)
                    if current > LIMIT:
                        raise MemoryError('own child exceeded 768MiB committed memory')
                    if time.monotonic()-started > 60:
                        raise TimeoutError('own child exceeded 60 seconds')
                    time.sleep(0.02)
                code = child.wait()
                current, observed_peak = child_memory(child._handle)
                peak = max(peak, observed_peak)
                if current > LIMIT:
                    raise MemoryError('own child exceeded 768MiB committed memory')
            except Exception as exc:
                failure = repr(exc)
                if child.poll() is None:
                    child.kill()
                code = child.wait()
            finally:
                # Popen's returned process handle only; never an arbitrary PID.
                child._handle.Close()
        stages.append(dict(name=name, command=command, exit_code=code, error=failure,
            peak_committed_bytes=peak, stdout=output.name, stdout_pin=pin(output),
            elapsed_ms=round((time.monotonic()-started)*1000, 3), collected=True))
        assert code == 0 and failure is None, stages[-1]
        return output.read_text(encoding='utf-8', errors='replace')

    try:
        script = out/'environment.cmd'
        with script.open('x', encoding='utf-8', newline='\r\n') as stream:
            stream.write('@echo off\ncall "'+str(VCVARS)+'" >nul\nif errorlevel 1 exit /b %errorlevel%\n')
            stream.write('"'+sys.executable+'" -B "'+str(HERE/'build_offline.py')+'" --emit-build-env\n')
        environment_text = execute('environment', ['cmd.exe', '/d', '/c', str(script)])
        env = {name.upper(): value for name, value in os.environ.items()}
        selected_environment = json.loads(environment_text)
        assert set(selected_environment) == {'PATH', 'INCLUDE', 'LIB', 'LIBPATH'}
        env.update(selected_environment)
        path_value = env['PATH']
        compiler = shutil.which('cl.exe', path=path_value)
        assembler = shutil.which('ml64.exe', path=path_value)
        assert compiler and assembler
        receipt['tool_inputs'] = {name: dict(path=path, **pin(Path(path))) for name, path in
            (('compiler', compiler), ('assembler', assembler))}
        execute('assemble', [assembler, '/nologo', '/c', '/Fo'+str(out/'entry_forward_model.obj'),
            str(HERE/'entry_forward_model.asm')], env)
        execute('compile', [compiler, '/nologo', '/std:c++17', '/W4', '/WX', '/EHsc', '/Od', '/GS', '/c',
            '/Fo'+str(out/'test_forward_model.obj'), str(HERE/'test_forward_model.cpp')], env)
        execute('link', [compiler, '/nologo', str(out/'test_forward_model.obj'), str(out/'entry_forward_model.obj'),
            '/Fe'+str(out/'test_forward_model.exe'), '/link', '/INCREMENTAL:NO', '/SUBSYSTEM:CONSOLE'], env)
        result = json.loads(execute('run', [str(out/'test_forward_model.exe')], env))
        assert result['passed'] is True and result['cases'] == 14
        assert result['native_ready'] is False and result['game_accessed'] is False
        receipt['test_result'] = result
        receipt['passed'] = True
    except Exception as exc:
        receipt['passed'] = False
        receipt['error'] = repr(exc)
    finally:
        receipt['source_after'] = {name: pin(HERE/name) for name in SOURCES}
        receipt['source_unchanged'] = receipt['source_after'] == source_pins
        receipt['default_44_and_DLL_unchanged'] = default_pins() == before
        receipt['all_children_collected'] = all(item['collected'] for item in stages)
        receipt['output_pins'] = {path.name: pin(path) for path in out.iterdir() if path.is_file()}
        receipt['passed'] = receipt.get('passed', False) and receipt['source_unchanged'] and receipt['default_44_and_DLL_unchanged']
        write_new(out/'receipt.json', receipt)
    print(json.dumps(dict(passed=receipt['passed'], receipt_pin=pin(out/'receipt.json'),
        stages=stages, all_children_collected=receipt['all_children_collected'], sealed=False)))
    return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
