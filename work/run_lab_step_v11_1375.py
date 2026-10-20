"""Capture one explicit v11 CLI operation. Never retries or batches publication."""
from __future__ import annotations
import argparse
from contextlib import redirect_stdout, redirect_stderr
import importlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work.native import lab_protocol_v11_1375 as lab


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('kind', choices=('loader', 'request', 'speed'))
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    lab.require(output.parent == lab.OUTPUT.resolve(), 'Capture must use the v11 output directory')
    modules = {'loader': 'work.native.inject_lab_v11_1375',
               'request': 'tools.request_diplomacy_lab_v11',
               'speed': 'work.native.run_lab_speed_v11_1375'}
    module = importlib.import_module(modules[args.kind])
    stream_out, stream_err = io.StringIO(), io.StringIO()
    # Reserve the audit path before any operation. Existing paths stop here.
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        result = dict(purpose='one_explicit_v11_cli_capture', kind=args.kind,
                      arguments=args.arguments, automatic_retry=False, applied_verified=False)
        try:
            with redirect_stdout(stream_out), redirect_stderr(stream_err):
                if args.kind == 'speed':
                    original = sys.argv
                    try:
                        sys.argv = [str(module.__file__), *args.arguments]
                        code = module.main()
                    finally:
                        sys.argv = original
                else:
                    code = module.main(args.arguments)
            result['exit_code'] = code
        except (Exception, SystemExit) as exc:
            result.update(exit_code=2, exception_type=type(exc).__name__, exception_message=str(exc))
        raw_out = stream_out.getvalue()
        result['stderr'] = stream_err.getvalue()
        try:
            result['report'] = json.loads(raw_out)
        except ValueError:
            result['stdout_raw'] = raw_out
        json.dump(result, stream, ensure_ascii=True, indent=2)
        stream.write('\n')
    report = result.get('report', {})
    request = report.get('request') or {}
    records = request.get('records') or []
    core = records[-1] if records else {}
    summary = {'output': str(output), 'exit_code': result['exit_code'],
               'stderr': result['stderr'], 'exception': result.get('exception_message'),
               'phases': report.get('phases'), 'last_sequence': report.get('last_sequence'),
               'pending': report.get('pending'), 'lease_pending': report.get('lease_pending'),
               'frame': {k: report.get('latest_frame', {}).get(k) for k in
                         ('world_cookie','raw_date','paused','session_frozen','mailbox_ready')},
               'native': {k: core.get(k) for k in
                          ('event','status','reason','preview_allowed','gate_allowed','submit_entered',
                           'submit_returned','context_submit_return','caller_container_consumed',
                           'ownership_uncertain','freeze_session','exception')}}
    print(json.dumps(summary))
    return result['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
