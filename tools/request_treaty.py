"""Create one explicit v7 treaty marker beside the DLL; never touches EU4."""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--terms', choices=('whitepeace', 'gold'), required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    metadata = (root / 'release/release.json').read_text(encoding='utf-8')
    if 'eu4_bridge_authorized_peace_v7.dll' not in metadata:
        raise RuntimeError('This helper is only for the v7 authorized release')
    name = 'whitepeace.request' if args.terms == 'whitepeace' else 'gold-peace.request'
    marker = root / 'work/native' / name
    with marker.open('x', encoding='ascii') as stream:
        stream.write(f'manual {args.terms} request\n')
    print(f'Queued marker: {marker}')
    print('The DLL will consume it on a later game frame; this command did not contact EU4.')


if __name__ == '__main__':
    main()
