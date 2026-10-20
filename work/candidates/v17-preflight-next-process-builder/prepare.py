"""Read-only author source/inventory check; never reads an actual case/prefix."""
import argparse,hashlib,json
from pathlib import Path
import build_case as b
HERE=Path(__file__).resolve().parent

def check():
 index=b.decode(b.bounded(HERE/'candidate-index.json',128*1024))
 b.require(index['purpose']=='explicit_process_offline_case_builder_sources' and index['schema_version']==1,'Index purpose')
 for name,row in index['sources'].items():
  b.require(Path(name).name==name and type(row)==dict and set(row)=={'bytes','sha256'},'Local source schema')
  raw=b.bounded(HERE/name,128*1024)
  b.require(len(raw)==row['bytes'] and b.sha(raw)==row['sha256'],'Candidate source changed: '+name)
 files=b.checked_sources()
 print(json.dumps({'status':'passed','candidate_sources':len(index['sources']),'frozen_sources':len(files),'actual_case_read':False,'process_accessed':False}))
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',required=True,action='store_true');parser.parse_args();check()
