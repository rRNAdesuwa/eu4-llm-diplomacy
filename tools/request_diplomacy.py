"""Queue fixed v9 diplomacy requests; no game restart or console interaction."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'work'))
from local_config import get_value


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('declare_war','whitepeace','gold','test_winwars'))
    parser.add_argument('--pid',type=int,required=True)
    args=parser.parse_args()
    events=(ROOT/'work/native/probe.jsonl').read_text(encoding='utf-8').splitlines()
    installations=[event for line in events if line.strip()
                   if (event:=json.loads(line)).get('event')=='automated_diplomacy_installed']
    installed=bool(installations and installations[-1].get('version')==9
                   and installations[-1].get('pid')==args.pid)
    if not installed:raise SystemExit('No v9 installation acknowledgement for this PID; no request queued.')
    if args.action in ('whitepeace','gold'):
        completed=subprocess.run([get_value('EU4_PYTHON'),'-B',str(ROOT/'work/queue_guarded_whitepeace.py'),
                                  '--pid',str(args.pid),'--terms',args.action],check=False)
        raise SystemExit(completed.returncode)
    report=ROOT/'work/runtime/automatic-request-preflight.json'
    completed=subprocess.run([get_value('EU4_PYTHON'),'-B',str(ROOT/'work/probe_native_state.py'),
                              '--pid',str(args.pid),'--output',str(report)],check=False)
    if completed.returncode:raise SystemExit(completed.returncode)
    state=json.loads(report.read_text(encoding='utf-8'))
    if state['player_tag']!='POR':raise SystemExit('Fixed v9 experiment requires player POR.')
    filename,token={
        'declare_war':('declare-war.request','FRA ENG cb_core 177 war_auto_01\n'),
        'test_winwars':('test-winwars.request','TEST_ONLY FRA winwars restore_POR\n'),
    }[args.action]
    # No filename, script, tag, CB or province is provided by the caller.
    with (ROOT/'work/native'/filename).open('x',encoding='ascii',newline='\n') as file:file.write(token)
    print(json.dumps({'queued':args.action,'pid':args.pid,'requires_foreground_frames':True,'success_verified':False}))


if __name__=='__main__':main()
