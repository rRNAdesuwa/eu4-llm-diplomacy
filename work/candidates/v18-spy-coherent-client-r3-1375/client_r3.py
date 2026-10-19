"""Private no-send client: one publication invocation, bounded coherent reads."""
import json,sys
from _base import base,check
import coherent
client=base._module(base.OLD/'client.py',{'build_manifest':base.client.b,'wire':base.client.wire,'loader':base.loader,'real_capture':coherent})
def main(argv=None):check();return client.main(argv)
if __name__=='__main__':
    try:raise SystemExit(main())
    except coherent.CoherentReadError as exc:
        print(json.dumps({'error':str(exc),'read_attempts':exc.attempts,'retry_allowed':False,'publication_retried':False},sort_keys=True),file=sys.stderr);raise SystemExit(2)
    except (ValueError,OSError,RuntimeError) as exc:
        print(f'v18 R3 client refused: {exc}; no retry',file=sys.stderr);raise SystemExit(2)
