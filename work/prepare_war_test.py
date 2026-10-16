"""Prepare a fixed authorized reconquest test; never unlock AI diplomacy."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.compiler import compile_request
from local_config import user_data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request-id', default='war_v7_01')
    args = parser.parse_args()
    script = compile_request({'id': args.request_id, 'action': 'declare_war', 'target': 'ENG'})
    script += '\n' + compile_request({'id': 'war_observe', 'action': 'snapshot'})
    destination = user_data() / 'llm_war_test.txt'
    destination.write_text(script, encoding='utf-8', newline='\n')
    print(destination)


if __name__ == '__main__':
    main()
