"""Record only the fixed v14 lab build and its exact native source set."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from work.native.lab_protocol_v14_1375 import record_build
from bridge.diplomacy_api import canonical


def main():
    report = record_build()
    print(canonical({"purpose": report["purpose"], "dll_sha256": report["dll_sha256"], "runtime_verified": False}))


if __name__ == "__main__":
    main()
