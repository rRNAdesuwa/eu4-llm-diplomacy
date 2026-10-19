"""Create/check a bounded source index. No build/materialization elsewhere."""
import argparse
import trace
HERE=trace.HERE;ROOT=trace.ROOT
SOURCES=['README.md','trace.py','contract.py','test_contract.py','prepare.py','validate.py','report.json','sender-pins.h']


def render():
    report=trace.load(HERE/'report.json')
    for r in report['inputs']:assert trace.rec(ROOT/r['path'])==r
    return trace.enc(dict(schema=1,purpose='v19_send_context_pins_static_only',inputs=report['inputs'],
      sources=[trace.rec(HERE/p) for p in SOURCES],new_decode_bytes=0,
      process_accessed=False,compiled=False,runtime_verified=False,production_ready=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args();b=render()
    if a.check:assert trace.read(HERE/'source-index.json')==b
    else:
        with (HERE/'source-index.json').open('xb') as f:f.write(b)
    print(trace.json.dumps(dict(passed=True,check=a.check,index=trace.rec(HERE/'source-index.json'))))
