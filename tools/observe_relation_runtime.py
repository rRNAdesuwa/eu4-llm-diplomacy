"""Read-only current alliance, marriage and guarantee status/watch/HTTP."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bridge.relation_state_service import (RelationStateObserver,make_relation_server,
    relation_capabilities,source_pins)
from bridge.tag_command_backend import require


def standalone_server(observer,*,port,token):
    from bridge.diplomacy_observer_service import make_server
    class NoEffects:
        def observe(self,request_id):raise FileNotFoundError('No request observer configured')
    server=make_server(NoEffects(),port=port,token=token)
    original=server.RequestHandlerClass
    class Handler(original):
        def do_GET(self):
            if self.path!='/observer/v1/capabilities':return super().do_GET()
            if not self.authorized():return self.send_json(403,dict(error='unauthorized'))
            try:
                source_pins()
                return self.send_json(200,dict(schema='EU4-RUNTIME-OBSERVER-CATALOG/1',read_only=True,
                    profiles=[],all120_effect_profiles_complete=False,request_effect_observer_configured=False,
                    relation_state=relation_capabilities(),native_calls=0,requests_published=0))
            except (OSError,ValueError,RuntimeError,KeyError,TypeError) as exc:
                return self.send_json(409,dict(status='unknown',message=str(exc),automatic_command_retry=False))
    server.RequestHandlerClass=Handler
    return make_relation_server(observer,server)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid',type=int);p.add_argument('--creation')
    p.add_argument('--store',type=Path,help='Optional complete capture journal directory')
    p.add_argument('--allow-tag-host',action='store_true')
    sub=p.add_subparsers(dest='operation',required=True)
    sub.add_parser('catalog');sub.add_parser('check')
    for name in ('status','watch'):
        item=sub.add_parser(name);item.add_argument('--action',required=True)
        item.add_argument('--actor',required=True);item.add_argument('--target',required=True)
        if name=='watch':
            item.add_argument('--duration-seconds',type=int,default=30)
            item.add_argument('--interval-ms',type=int,default=1000)
    serve=sub.add_parser('serve');serve.add_argument('--port',type=int,default=8775)
    a=p.parse_args()
    verified=source_pins()
    if a.operation in ('catalog','check'):
        print(json.dumps(relation_capabilities()|dict(source_pins_verified=len(verified),game_process_accessed=False)))
        return 0
    require(a.pid is not None and a.creation is not None,'--pid and --creation required')
    if a.operation=='watch':
        require(1<=a.duration_seconds<=300 and 1000<=a.interval_ms<=10000,'Watch duration/interval bounds')
    observer=RelationStateObserver(a.pid,a.creation,store=a.store,allow_tag_host=a.allow_tag_host)
    if a.operation=='serve':
        server=standalone_server(observer,port=a.port,token=os.environ.get('EU4_OBSERVER_TOKEN'))
        print(f'Read-only relation observer: http://127.0.0.1:{server.server_port}/observer/v1/relations/<action>/<actor>/<target>',flush=True)
        try:server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:pass
        finally:server.server_close()
        return 0
    if a.operation=='status':
        value=observer.observe_pair(a.action,a.actor,a.target);print(json.dumps(value))
        return 2 if value['status']=='unknown' else 0
    deadline,prior=time.monotonic()+a.duration_seconds,None
    while True:
        value=observer.observe_pair(a.action,a.actor,a.target)
        key=json.dumps({k:value[k] for k in ('status','requested_direction_matches','object','failure')},sort_keys=True)
        if key!=prior:print(json.dumps(value),flush=True);prior=key
        if time.monotonic()>=deadline:return 2 if value['status']=='unknown' else 0
        time.sleep(min(a.interval_ms/1000,max(0,deadline-time.monotonic())))


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError,KeyError,TypeError) as exc:
        print(json.dumps(dict(status='unknown',error=str(exc),automatic_command_retry=False,
            native_calls=0,requests_published=0)),file=sys.stderr)
        raise SystemExit(2)
