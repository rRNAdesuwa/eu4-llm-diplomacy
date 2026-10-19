"""Read-only candidate/file-source check. --check never reads the large save."""
from pathlib import Path
import argparse,json
import parser as p
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def read(path,limit=4*1024*1024):
 with path.open('rb') as stream:raw=stream.read(limit+1)
 p.require(len(raw)<=limit,'Bounded source');return raw
def check():
 index=json.loads(read(HERE/'source-index.json',131072))
 p.require(len(index['inputs'])<=32 and len(index['candidate_files'])<=20,'Source inventory bound')
 for label,folder in (('inputs',ROOT),('candidate_files',HERE)):
  for name,descriptor in index[label].items():
   path=(folder/name).resolve();p.require(path.is_relative_to(folder),'Escaped source')
   raw=read(path);p.require(descriptor=={'bytes':len(raw),'sha256':p.sha(raw)},'Source changed: '+name)
 report=json.loads(read(HERE/'report.json'))
 p.require(p.canonical(report['selected'])==p.canonical(p.selected(report['parsed'])),'Stored selected model differs')
 p.require(report['parsed']['sha256']==index['save']['sha256'] and report['parsed']['bytes']==index['save']['bytes'],'Fixed save declaration')
 p.require(len(report['raw_excerpts'])==len(report['parsed']['records']),'Evidence count')
 for raw,row in zip(report['raw_excerpts'],report['parsed']['records']):
  data=raw['latin1'].encode('latin1')
  p.require(raw['path']==row['path'] and raw['byte_offset']==row['record']['byte_offset'] and raw['end_byte']==row['end_byte']
            and raw['size_bytes']==len(data)==raw['end_byte']-raw['byte_offset'] and raw['sha256']==p.sha(data),'Raw evidence binding')
 return {'checked':True,'input_count':len(index['inputs']),'candidate_count':len(index['candidate_files']),'save_opened':False,'runtime_verified':False}
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--check',action='store_true',required=True);a.parse_args();print(json.dumps(check(),sort_keys=True))
