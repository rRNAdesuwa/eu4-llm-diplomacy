"""Reproduce the fixed, stopped file's selected layout; never operates a game."""
from pathlib import Path
import argparse,hashlib,json,stat
import parser as p
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SAVE_SHA='8a8f812ab9a33b8479f36007077e05a870128e79afa90961eac579340f1d8566'
SAVE_SIZE=36756072
REPORT=ROOT/'work/runtime/spy-subject-curry-stopped-save-38232.json'
def bounded(path,size):
 with path.open('rb') as stream:raw=stream.read(size+1)
 p.require(len(raw)<=size,'Bounded metadata/source');return raw
def run():
 root_raw=bounded(REPORT,4*1024*1024);root=json.loads(root_raw)
 p.require(root['parsed_complete'] is True and root['evidence_scope']=='serialized_state_only' and root['source']['size_bytes']==SAVE_SIZE
           and root['source']['sha256'].lower()==SAVE_SHA,'Fixed root extraction metadata')
 source=Path(root['source']['path']);before=source.stat()
 p.require(stat.S_ISREG(before.st_mode) and not source.is_symlink() and not (getattr(before,'st_file_attributes',0)&0x400)
           and before.st_size==SAVE_SIZE,'Regular fixed save file')
 with source.open('rb') as stream:parsed=p.parse_stream(stream)
 p.require(parsed['bytes']==SAVE_SIZE and parsed['sha256']==SAVE_SHA,'Complete source SHA/size')
 selected=p.selected(parsed)
 p.require(selected['save_date']=='1444.12.26' and selected['nav']['subject_focus']==5 and selected['nav']['set_positions']==[1,4,6]
           and len(selected['curry']['envoys'])==103 and selected['curry']['linked_envoy_id']==0,'Fixed selected serialized observation differs')
 excerpts=[];total=0
 with source.open('rb') as stream:
  for row in parsed['records']:
   at=row['record']['byte_offset'];length=row['end_byte']-at
   p.require(0<length<=p.g.MAX_CAPTURE,'Bounded raw excerpt');total+=length;p.require(total<=p.g.MAX_RETAINED,'Raw evidence total')
   stream.seek(at);raw=stream.read(length);p.require(len(raw)==length,'Raw excerpt missing')
   excerpts.append({'path':row['path'],'byte_offset':at,'end_byte':row['end_byte'],'line':row['record']['line'],
                    'size_bytes':length,'sha256':p.sha(raw),'latin1':raw.decode('latin1')})
 after=source.stat();p.require((before.st_size,before.st_mtime_ns,before.st_ino)==(after.st_size,after.st_mtime_ns,after.st_ino),'Source changed')
 return {'schema':1,'purpose':'fixed_serialized_layout_research_only','source':{'path':str(source),'sha256':SAVE_SHA,'size_bytes':SAVE_SIZE,
  'root_report_path':REPORT.relative_to(ROOT).as_posix(),'root_report_sha256':p.sha(root_raw),'stat_unchanged':True},
  'limits':{'chunk_bytes':p.g.CHUNK,'total_bytes':p.MAX_SAVE,'token_bytes':p.g.MAX_TOKEN,'depth':p.g.MAX_DEPTH,
            'capture_bytes':p.g.MAX_CAPTURE,'capture_nodes':p.g.MAX_CAPTURE_NODES,'retained_token_bytes':p.g.MAX_RETAINED,'retained_nodes':p.g.MAX_RETAINED_NODES},
  'parsed':parsed,'selected':selected,'raw_excerpts':excerpts,'raw_excerpt_bytes':total,
  'proof_limits':['1444.12.26 serialized state is a different date from 1444.11.11 read-only batches.',
    'No causal, persistence, reload, native request, AI acceptance, full-world, strict-SP or production evidence.',
    'Normal menu exit was reported, but no held exit handle exists: no exit code or exit FILETIME is inferred.',
    'Positions 1/4/6 in the seven-value array match independently known in-memory bit indices, but serialization bit order is not yet independently closed.',
    'Repeated rival records are current selected-country declarations; enemy/historical_rivals and active-relations are preserved separately.',
    'Envoy action omission is preserved as null, not inferred idle. Construction date is not labelled completion/expiry.'],
  'game_process_accessed':False,'native_called':False,'save_modified':False,'persistence_verified':False,'reload_verified':False,'production_ready':False}
def main():
 args=argparse.ArgumentParser();args.add_argument('--check',action='store_true');ns=args.parse_args();report=run()
 raw=(json.dumps(report,sort_keys=True,indent=2,ensure_ascii=True)+'\n').encode('ascii');out=HERE/'report.json'
 if ns.check:p.require(out.read_bytes()==raw,'Reproduced report differs')
 else:
  with out.open('xb') as stream:stream.write(raw)
 print(json.dumps({'checked':ns.check,'sha256':p.sha(raw),'bytes':len(raw),'save_bytes':SAVE_SIZE,'raw_excerpt_bytes':report['raw_excerpt_bytes'],'selected_paths':len(report['parsed']['records'])}))
if __name__=='__main__':main()
