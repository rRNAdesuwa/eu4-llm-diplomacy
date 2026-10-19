"""Recipient-operated loader. Nothing executes on import; no automatic discovery."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-exe', required=True, type=Path)
    parser.add_argument('--pid', required=True, type=int)
    parser.add_argument('--ack-test-save', required=True, action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    metadata = json.loads((root / 'release/release.json').read_text(encoding='utf-8'))
    dll = root / 'work/native' / metadata['dll']
    try:
        if args.pid <= 0:
            raise RuntimeError('PID must be positive')
        if hashlib.sha256(dll.read_bytes()).hexdigest() != metadata['dll_sha256']:
            raise RuntimeError('DLL hash mismatch; use the complete reviewed release')
        game = args.game_exe.resolve(strict=True)
        if hashlib.sha256(game.read_bytes()).hexdigest() != metadata['game_sha256']:
            raise RuntimeError('Unsupported game executable; do not bypass the check')
        sys.path.insert(0, str(root / 'work/native'))
        import inject_probe
        if inject_probe.EXPECTED_HASH.lower() != metadata['game_sha256']:
            raise RuntimeError('Loader and release disagree about the game build')
        # Change only the local path; all existing build/process/module checks remain.
        inject_probe.GAME = game
        report = inject_probe._run(argparse.Namespace(
            pid=args.pid, dll=str(dll.resolve()), ack_test_save=True, timeout_ms=10000))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (OSError, RuntimeError, TimeoutError) as error:
        print(f'load_release: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
