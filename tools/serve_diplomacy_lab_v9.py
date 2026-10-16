"""Explicit localhost EU4LAB/2 research service, separate from the production API."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.diplomacy_lab_http import ResearchError, ResearchService, V9ResearchRuntime, make_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--creation", required=True, help="Exact process creation FILETIME, 16 lowercase hex characters")
    parser.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1",))
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    try:
        service = ResearchService(V9ResearchRuntime(args.pid, args.creation))
        server = make_server(service, host=args.host, port=args.port, token=os.environ.get("EU4_LAB_HTTP_TOKEN"))
    except (ResearchError, OSError) as error:
        parser.error(str(error))
    print(f"Research only: http://127.0.0.1:{args.port}/research/v9/capabilities", flush=True)
    print("Bound PID/creation; ten pair actions only. Production backend remains unregistered. No automatic retries.", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
