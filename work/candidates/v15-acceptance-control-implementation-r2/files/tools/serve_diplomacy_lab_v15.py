"""Explicit localhost v15 EU4LAB/3 research service; production stays disabled."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy_lab_http import ResearchError
from bridge.diplomacy_lab_http_v15 import V15ResearchRuntime, ResearchService, make_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--creation", required=True, help="Exact creation FILETIME, 16 lowercase hex characters")
    parser.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1",))
    parser.add_argument("--port", type=int, default=8771)
    args = parser.parse_args()
    try:
        service = ResearchService(V15ResearchRuntime(args.pid, args.creation))
        server = make_server(service, host=args.host, port=args.port, token=os.environ.get("EU4_LAB_HTTP_TOKEN"))
    except (ResearchError, OSError) as error:
        parser.error(str(error))
    print(f"Research only: http://127.0.0.1:{args.port}/research/v15/capabilities", flush=True)
    print("Fixed 36-action v15 candidate; fixed gift 25.000, trade fraction 500, insult -1; subsidy 1.000/month for 10 years. No automatic retries or production backend.", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
