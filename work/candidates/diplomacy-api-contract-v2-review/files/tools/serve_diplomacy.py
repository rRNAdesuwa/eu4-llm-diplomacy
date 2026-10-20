"""Serve the version-gated diplomacy API; no game process is modified."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.diplomacy_api import DEFAULT_CATALOG, DEFAULT_DATABASE, DiplomacyAPI
from bridge.diplomacy_service import make_server
from work.local_config import get_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-only", action="store_true", help="V2 drafts only; no V1 database or executable inspection")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--game-exe", type=Path)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--queue-db", type=Path, default=DEFAULT_DATABASE)
    args = parser.parse_args()
    if args.contract_only and (args.game_exe is not None or args.catalog != DEFAULT_CATALOG or args.queue_db != DEFAULT_DATABASE):
        parser.error("--contract-only has fixed evidence and no executable/queue options")
    api = None
    if not args.contract_only:
        game_root = get_path("EU4_GAME_ROOT", required=False)
        executable = args.game_exe or (game_root / "eu4.exe" if game_root else None)
        api = DiplomacyAPI(args.catalog, args.queue_db, executable)
    try:
        server = make_server(api, args.host, args.port, os.environ.get("EU4_DIPLOMACY_TOKEN"),
                             allow_remote=args.allow_remote)
    except ValueError as exc:
        if api is not None:
            api.close()
        parser.error(str(exc))
    route = "/v2/actions" if args.contract_only else "/v1/capabilities"
    print(f"Diplomacy API: http://{args.host}:{server.server_port}{route}", flush=True)
    print("V2: unsupported drafts only; no request ID reservation or native execution." if args.contract_only else
          "V1 durable audit active; V2 drafts have no reservation. Execution adapter unavailable.", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if api is not None:
            api.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
