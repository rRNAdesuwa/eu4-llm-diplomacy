import argparse,json
from census import check
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',required=True,action='store_true');p.parse_args();print(json.dumps(check(),sort_keys=True))
