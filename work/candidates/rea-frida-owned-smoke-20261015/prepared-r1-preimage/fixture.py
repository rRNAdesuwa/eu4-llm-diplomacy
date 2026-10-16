"""Our waiting child only. No game, Frida, filesystem or network operations."""
import json
import os
import re
import sys


def main():
    if len(sys.argv) != 2 or re.fullmatch('[0-9a-f]{32}', sys.argv[1]) is None:
        return 2
    nonce = sys.argv[1]
    print(json.dumps(dict(schema='REA-OWNED-FIXTURE-READY/1', pid=os.getpid(), nonce=nonce),
                     separators=(',', ':')), flush=True)
    # Controller owns this pipe and remains alive during attach/load/cleanup.
    # A closed pipe also ends our fixture; no self-spawn or background work.
    stop = sys.stdin.readline(64)
    return 0 if stop == nonce+'\n' else 3


if __name__ == '__main__':
    raise SystemExit(main())
