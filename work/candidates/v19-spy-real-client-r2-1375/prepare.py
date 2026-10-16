"""Check the compiled launcher's payload gate; file-only, no public live main."""
from pathlib import Path
import argparse,json
import launcher

def check():
    graph=launcher.verified_graph();f=graph.local('frozen.py');f.verify_build(f.BUILD)
    return dict(checked=len(graph.snapshot),bytes=sum(map(len,graph.snapshot.values())),private_graph=True,actual_process_access=False,publication_attempted=False)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',required=True,action='store_true');p.parse_args();print(json.dumps(check(),sort_keys=True))
