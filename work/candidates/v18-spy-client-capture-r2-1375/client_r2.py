"""Private no-send client using the independently reviewed R2 capture reader.

CLI parameters remain those of the frozen client. This wrapper does not install
anything or implement a new stage, DLL, game operation, or production backend.
Only root-authorized future use may access a live process or publish a stage.
"""
import sys
from _binding import check,client

def main(argv=None):
    check()
    return client.main(argv)

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,RuntimeError) as exc:
        print(f'v18 R2 no-send client refused: {exc}; no retry',file=sys.stderr)
        raise SystemExit(2)
