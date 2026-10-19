"""Prepare a file-only unsealed manifest; never imports a process provider."""
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    spec = importlib.util.spec_from_file_location('_entry_host_file_builder',HERE/'capture_once.py')
    host = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(host)
    pins, seen = {},set()
    def add(name, expected=None):
        actual = host.pin(ROOT/name,16*1024*1024)
        if expected is not None:
            host.require(actual == expected,'Source differs during collection: '+name)
        if name in pins:
            host.require(pins[name] == actual,'Repeated inconsistent source pin')
        pins[name] = actual
    pending = list(host.FROZEN)
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        add(name)
        data = host.strict_json(host.read_bound(ROOT/name,1024*1024),1024*1024,evidence_scalars=False)
        children = data['source_pins'] if name != host.WAR_READER else {
            row['path']:{k:row[k] for k in ('bytes','sha256')} for row in data['files']}
        for child,expected in children.items():
            add(child,expected)
            if child == host.NATIVE or (child.endswith('.json') and 'manifest' in Path(child).name):
                parsed = host.strict_json(host.read_bound(ROOT/child,1024*1024),1024*1024,evidence_scalars=False)
                if type(parsed) is dict and 'source_pins' in parsed and 'game_sha256' in parsed:
                    pending.append(child)
        if name == host.NATIVE:
            add(str(Path(host.NATIVE).parent/data['DLL']).replace('\\','/'),data['dll'])
    for p in HERE.iterdir():
        if p.is_file() and p.suffix in ('.py','.js','.md','.json') and 'manifest' not in p.name:
            add(p.relative_to(ROOT).as_posix())
    reports = ROOT/'work/reports/war-peace-api-20261015-r12-host-offline'
    for p in reports.rglob('*'):
        if p.is_file() and p.stat().st_size:
            add(p.relative_to(ROOT).as_posix())
    for name in ('work/reports/frida-entry-script-review-20261015-r1/independent-source-ready.json',
        'work/reports/frida-entry-job-review-20261015-r1/independent-r3-source-ready.json',
        'work/reports/entry-observation-parser-review-20261015-r1/independent-source-ready.json',
        'work/reports/rea-frida-cli-format-audit-20261015/field-contract.json'):
        add(name)
    rea = host.REA
    external = [host.NODE,rea/'scripts/rea.mjs',rea/'package.json',rea/'package-lock.json',
        rea/'dist/cli-runtime/cli.js',rea/'dist/cli-runtime/cliOutput.js',
        rea/'dist/cli-runtime/cliOutput-Nv3hPSQ5.js',rea/'dist/cli-runtime/cliResultOutput.js',
        rea/'dist/cli-runtime/cliResultOutput-7v9FCObq.js',rea/'node_modules/frida/package.json',
        rea/'node_modules/frida/build/frida_binding.node']
    manifest = dict(schema='EU4-FRIDA-ENTRY-HOST-MANIFEST/1',sealed=False,
        game_sha256=host.GAME_SHA,fixed_pid=host.PID,fixed_creation=host.CREATION,
        source_pins=dict(sorted(pins.items())),selected_external_pins={str(p):host.pin(p) for p in external})
    path = HERE/'host-manifest.draft-r4.json'
    with path.open('x') as stream:
        json.dump(manifest,stream,indent=2,sort_keys=True)
        stream.write('\n')
    print(json.dumps(dict(output=str(path),local_pins=len(pins),selected_external_pins=len(external),
        bytes=sum(x['bytes'] for x in pins.values()),Frida_called=False,process_opened=False)))


if __name__ == '__main__':
    main()
