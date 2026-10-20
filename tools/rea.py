"""Run REA CLI through the existing Codex stdio registration; no shell or setup."""
import os
from pathlib import Path
import subprocess
import sys
import tomllib


def main():
    config_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    config_path = config_home / "config.toml"
    try:
        with config_path.open("rb") as stream:
            server = tomllib.load(stream)["mcp_servers"]["rea"]
        command = server["command"]
        arguments = server.get("args", [])
        overrides = server.get("env", {})
        if (not isinstance(command, str) or not command
                or not isinstance(arguments, list) or not arguments
                or not all(isinstance(item, str) for item in arguments)
                or arguments[-1] not in ("mcp", "--mcp")
                or not isinstance(overrides, dict)
                or not all(isinstance(k, str) and isinstance(v, str)
                           for k, v in overrides.items())):
            raise ValueError("Expected a REA stdio command ending in mcp or --mcp")
        environment = os.environ.copy()
        environment.update(overrides)
        return subprocess.run(
            [command, *arguments[:-1], *(sys.argv[1:] or ["--help"])],
            env=environment, cwd=server.get("cwd"), check=False,
        ).returncode
    except (OSError, KeyError, ValueError) as error:
        print(f"REA launcher failed ({config_path}): {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
