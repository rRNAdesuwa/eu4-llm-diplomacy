"""Check only pinned files and the original DLL bytes; never load or publish."""
import argparse,json
from _binding import check
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true',required=True);p.parse_args()
    print(json.dumps(check(),sort_keys=True))
