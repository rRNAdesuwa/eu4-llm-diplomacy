"""Serve the version-gated diplomacy API; no game process is modified."""
from __future__ import annotations

import argparse
import ipaddress
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
    parser.add_argument("--contract-only", action="store_true", help="Contract drafts only; no V1 database or executable inspection")
    parser.add_argument("--api-version", type=int, choices=(1, 2, 3), help="2 or 3 implies contract-only; 3 is loopback only")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--game-exe", type=Path)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--queue-db", type=Path, default=DEFAULT_DATABASE)
    args = parser.parse_args()
    if args.api_version == 1 and args.contract_only:
        parser.error("--api-version 1 cannot be combined with --contract-only")
    if args.api_version in (2, 3):
        args.contract_only = True
    version = args.api_version or (2 if args.contract_only else 1)
    if version == 3:
        try:
            loopback = args.host == "localhost" or ipaddress.ip_address(args.host).is_loopback
        except ValueError:
            loopback = False
        if not loopback or args.allow_remote:
            parser.error("--api-version 3 requires loopback and does not allow remote binding")
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
    route = f"/v{version}/actions" if args.contract_only else "/v1/capabilities"
    print(f"Diplomacy API: http://{args.host}:{server.server_port}{route}", flush=True)
    print(f"V{version}: unsupported drafts only; no request ID reservation or native execution." if args.contract_only else
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
