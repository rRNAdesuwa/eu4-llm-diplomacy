"""Bounded offline save and typed reload matchers; no process/native entrypoints."""
from __future__ import annotations
import hashlib,importlib.util,json,re,sys
from datetime import datetime,timezone
from pathlib import Path, PurePosixPath
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from work import inspect_diplomacy_save as grammar
from bridge.native_build import LOCAL_SHA256
from work.probe_diplomacy_current import ProbeError

MAX_SAVE=64*1024*1024
MAX_JSON=4*1024*1024
ORIGINAL_PID=18356
ORIGINAL_CREATION="01dd56aa6f724ea8"
ORIGINAL_WORLD="0x221c8dac040"
POSITIVE_RELOAD={"pid":35552,"creation":"01dd56b0fafda55d","world":"0x24b15e60070","raw_date":56457456}
FINAL_RELOAD={"pid":59012,"creation":"01dd56b271750dad","world":"0x1340dcc6010","raw_date":56457600}
# Direct paired saved-date/native-start observations in this fixed experiment.
# This is deliberately not a general conversion of EU4 calendar/epoch.
DATE_RAW={"1444.11.11":56456976,"1444.11.15":56457072,"1444.11.25":56457312,"1444.12.1":56457456,"1444.12.7":56457600}
LAYOUTS={
 "cancel_military_access":("military_access","FRA","POR",{"first","second","start_date","enforce_peace"}),
 "revoke_military_access":("military_access","POR","FRA",{"first","second","start_date","enforce_peace"}),
 "dissolve_alliance":("alliance","FRA","POR",{"first","second","start_date"}),
 "cancel_subsidies":("subsidies","FRA","POR",{"first","second","start_date","amount","duration"}),
}
RELOAD_ONLY={"cancel_fleet_basing_rights","revoke_fleet_basing_rights","embargo","revoke_embargo"}
class Rejected(ValueError):pass
def require(condition,message):
 if not condition:raise Rejected(message)
def integer(value,low=0,high=2**64-1):return type(value) is int and low<=value<=high
def typed(value):return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)
def same(a,b):return typed(a)==typed(b)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def bounded(path,limit=MAX_JSON):
 with Path(path).open("rb") as stream:raw=stream.read(limit+1)
 require(len(raw)<=limit,"JSON/source byte budget");return raw

def dependencies(root=ROOT):
 pins=json.loads(bounded(HERE/"pins.json"))
 for name,item in pins["files"].items():
  path=Path(root)/name;raw=bounded(path)
  require(len(raw)==item["size_bytes"] and sha(raw)==item["sha256"],"Dependency changed: "+name)
 spec=importlib.util.spec_from_file_location("directional_persistence_observer",Path(root)/"work/candidates/directional-pair-observer-1375/observer.py")
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.verify_contract(root)
 return pins,module

class Reader(grammar.BoundedReader):
 def read(self,count):
  require(type(count) is int and 0<=count<=grammar.CHUNK,"Invalid read size")
  raw=super().read(count);require(self.count<=MAX_SAVE,"Save exceeds 64 MiB budget");return raw

def flat(record):
 require(type(record) is dict and type(record.get("entries")) is list and len(record["entries"])<=32,"Relation fields exceed bound")
 values={}
 for item in record["entries"]:
  require(type(item) is dict and "entries" not in item and set(item)=={"key","value","raw_value","line","byte_offset"},"Nested/unknown relation entry")
  key=item["key"]
  require(type(key) is str and key not in values and type(item["value"]) is str and type(item["raw_value"]) is str
          and integer(item["line"],1) and integer(item["byte_offset"]),"Duplicate/malformed relation field")
  raw=item["raw_value"];value=raw[1:-1] if raw.startswith('"') and raw.endswith('"') else raw
  require(value==item["value"],"Decoded/raw scalar differs")
  values[key]=value
 require(type(values.get("first")) is str and type(values.get("second")) is str
         and re.fullmatch(r"[A-Z0-9]{3}",values["first"]) and re.fullmatch(r"[A-Z0-9]{3}",values["second"]),"Missing strict relation participants")
 return values

def parse_stream(source):
 """Parse all bytes; retain only three exact relation types for the selected pair."""
 reader=Reader(source);path=[];capture=None;records=[];metadata={};countries={"FRA":0,"POR":0};diplomacy_count=0;country_containers=0;scanned=0;map_area_seen=False;map_area_pending=False
 for event,key,token in grammar.events(reader):
  # Exact stock top-level bare key followed by an anonymous container only.
  # This adapter does not relax the shared grammar or selected diplomacy blocks.
  if map_area_pending:
   require(not path and event=="start" and key is None and token[0]=="{" and token[1]==b"{",
           "map_area_data must immediately introduce anonymous block")
   key="map_area_data";map_area_pending=False
  elif not path and event=="bare":
   require(token[0]=="atom" and token[1]==b"map_area_data" and not map_area_seen,
           "Unexpected or duplicate bare top-level token")
   map_area_seen=True;map_area_pending=True;continue
  elif not path and (key=="map_area_data" or (event=="start" and key is None)):
   raise Rejected("Only exact bare map_area_data anonymous container is supported")
  if path==["diplomacy"]:
   require(event!="bare" and not(event=="start" and key is None),"Diplomacy entries require explicit assignments")
  if capture is not None:
   if capture.add(event,key,token):
    fields=flat(capture.root);scanned+=1;require(scanned<=4096,"Relation scan budget")
    if {fields["first"],fields["second"]}=={"FRA","POR"}:
     require(len(records)<32,"Selected relation budget");records.append({"type":capture.root["key"],"fields":fields})
    capture=None
  elif not path and event=="scalar" and key in ("date","player"):
   require(key not in metadata,"Duplicate metadata");metadata[key]=grammar.scalar_entry(key,token)["value"]
  elif not path and event=="start" and key=="diplomacy":
   diplomacy_count+=1;require(diplomacy_count==1,"Duplicate diplomacy container")
  elif not path and event=="start" and key=="countries":
   country_containers+=1;require(country_containers==1,"Duplicate countries container")
  elif path==["countries"] and event=="start" and key in countries:
   countries[key]+=1;require(countries[key]==1,"Duplicate selected country")
  elif path==["diplomacy"] and event=="start" and key in ("alliance","military_access","subsidies"):
   capture=grammar.Capture(key,token,None)
  elif path==["diplomacy"] and event=="scalar" and key in ("alliance","military_access","subsidies"):
   raise Rejected("Selected relation must be block")
  if event=="start":path.append(key)
  elif event=="end":path.pop()
 require(diplomacy_count==1 and country_containers==1 and all(v==1 for v in countries.values()) and capture is None and not map_area_pending,
         "Complete required save containers/countries missing")
 require(set(metadata)=={"date","player"} and metadata["player"]=="FRA" and metadata["date"] in DATE_RAW,"Unsupported selected save date/player")
 return {"schema_version":1,"kind":"bounded_directional_save_projection","parsed_complete":True,"encoding":"plain_text",
   "size_bytes":reader.count,"sha256":reader.sha256.hexdigest(),"metadata":metadata,"selected_records":records,
   "scanned_supported_relation_records":scanned,"runtime_verified":False,"execution_verified":False}

def stream_hash(path,size,digest):
 require(integer(size,1,MAX_SAVE) and type(digest) is str and re.fullmatch(r"[0-9a-f]{64}",digest),"Invalid save descriptor")
 h=hashlib.sha256();count=0
 with Path(path).open("rb") as stream:
  while raw:=stream.read(65536):
   count+=len(raw);require(count<=size,"Save larger than frozen descriptor");h.update(raw)
 require(count==size and h.hexdigest()==digest,"Save bytes changed")

def parse_saved(path,spec):
 path=Path(path)
 require(path.is_file() and not path.is_symlink() and not (hasattr(path,"is_junction") and path.is_junction())
         and path.name==spec["filename"],"Wrong save file/name")
 before=path.stat();identity=(before.st_size,before.st_mtime_ns,before.st_ino)
 stream_hash(path,spec["size_bytes"],spec["sha256"])
 with path.open("rb") as source:parsed=parse_stream(source)
 require(parsed["size_bytes"]==spec["size_bytes"] and parsed["sha256"]==spec["sha256"] and parsed["metadata"]["date"]==spec["date"],"Full parser/input identity differs")
 stream_hash(path,spec["size_bytes"],spec["sha256"])
 after=path.stat();require(identity==(after.st_size,after.st_mtime_ns,after.st_ino),"Save stat changed during bounded replay")
 return parsed

def fixed_save(label,path,root=ROOT):
 pins,_=dependencies(root);require(label in ("positive","final"),"Unknown fixed save")
 return parse_saved(path,pins["saves"][label])

def from_extraction(document):
 """Normalize existing full-stream extraction for comparison with fresh parser."""
 require(type(document["schema_version"]) is int and document["schema_version"]==1 and document["parsed_complete"] is True
         and document["read_only"] is True and document["runtime_effects_verified"] is False
         and document["evidence_scope"]=="serialized_state_only" and document["actor"]=="FRA"
         and type(document["targets"]) is list and "POR" in document["targets"]
         and document["global_diplomacy"]["container_found"] is True,"Not complete selected extraction")
 source=document["source"]
 require(source["format"]=="plain_text" and integer(source["size_bytes"],1,MAX_SAVE)
         and type(source["gamestate_bytes"]) is int and source["gamestate_bytes"]==source["size_bytes"]
         and source["sha256"]==source["gamestate_sha256"],"Save source layout differs")
 records=[]
 for record in document["global_diplomacy"]["records"]:
  if record["key"] in ("alliance","military_access","subsidies"):
   fields=flat(record)
   if {fields["first"],fields["second"]}=={"FRA","POR"}:records.append({"type":record["key"],"fields":fields})
 return {"metadata":{k:document["metadata"][k]["value"] for k in ("date","player")},"selected_records":records}

def compare_extraction(parsed,existing):
 expected=from_extraction(existing)
 require(same(expected,{k:parsed[k] for k in expected}),"Old extraction differs from fresh complete parser")
 require(existing["source"]["sha256"].lower()==parsed["sha256"] and existing["source"]["size_bytes"]==parsed["size_bytes"],"Old extraction source hash/size differs")


def saved_state(parsed,action,expected,start_date):
 require(action in LAYOUTS and expected in ("active","absent"),"Unsupported saved relation")
 kind,first,second,keys=LAYOUTS[action]
 selected=[]
 for item in parsed["selected_records"]:
  require(set(item)=={"type","fields"} and type(item["type"]) is str and type(item["fields"]) is dict,"Projection record schema")
  fields=item["fields"]
  if item["type"]!=kind:continue
  require(all(type(k) is str and type(v) is str for k,v in fields.items()) and "first" in fields and "second" in fields,"Projection fields exact types")
  match={fields["first"],fields["second"]}=={first,second} if kind=="alliance" else (fields["first"],fields["second"])==(first,second)
  if match:selected.append(fields)
 if expected=="absent":require(not selected and start_date is None,"Selected serialized relation remains/absence start invented")
 else:
  require(type(start_date) is str and start_date in DATE_RAW and len(selected)==1,"Missing/duplicate saved active relation")
  fields=selected[0]
  require(set(fields)==keys and fields["start_date"]==start_date,"Unknown saved variant/incorrect start date")
  if kind=="military_access":require(fields["enforce_peace"]=="no","Conditional/enforced access is not ordinary agreement")
  if kind=="subsidies":require(fields["amount"]=="1.000" and fields["duration"]=="10","Wrong fixed subsidy amount/years")
 return {"action":action,"saved_selected_state":expected,"saved_start_date":start_date,"serialized_layout_verified":True}

def filetime(value):
 require(type(value) is str,"Timestamp must be string")
 dt=datetime.fromisoformat(value);require(dt.tzinfo is not None,"Timestamp timezone missing")
 delta=dt.astimezone(timezone.utc)-datetime(1601,1,1,tzinfo=timezone.utc)
 return (delta.days*86400+delta.seconds)*10000000+delta.microseconds*10

def reload_binding(binding,label):
 require(type(binding) is dict and set(binding)=={"pid","creation","world","raw_date"}
         and integer(binding["pid"],1,2**32-1) and binding["pid"]!=ORIGINAL_PID
         and type(binding["creation"]) is str and re.fullmatch(r"[0-9a-f]{16}",binding["creation"])
         and int(binding["creation"],16)>int(ORIGINAL_CREATION,16)
         and type(binding["world"]) is str and re.fullmatch(r"0x[0-9a-f]+",binding["world"])
         and int(binding["world"],16)>=0x10000 and integer(binding["raw_date"],1,2**31-1),"Invalid explicit reload binding")
 if label=="positive":require(same(binding,POSITIVE_RELOAD),"Wrong fixed positive reload")
 else:require(label=="final" and same(binding,FINAL_RELOAD),"Wrong fixed final reload identity")

def semantic(state,action):
 require(state["state"] in ("active","absent"),"Unknown observed state")
 if state["state"]=="absent":
  result={"state":"absent"}
  if action in ("embargo","revoke_embargo"):result.update(outgoing_embargo=state["outgoing_embargo"],incoming_embargo=state["incoming_embargo"])
  return result
 obj=state["object"]
 require(type(obj) is dict,"Expected indexed relation")
 fields=["type_marker","started_raw_date","removed"]
 if "military" in action or "fleet" in action:fields.append("enforce_peace")
 if "subsid" in action:fields.extend(["monthly_milli","duration_years"])
 result={"state":"active",**{k:obj[k] for k in fields}}
 pair=[int(obj[k],16) for k in ("first_handle","second_handle")]
 result["handles"]=sorted(pair) if action=="dissolve_alliance" else pair
 return result

def observed(report,action,observer,allow_positive_subsidy=False):
 allowed={action}|({"give_subsidies"} if action=="cancel_subsidies" and allow_positive_subsidy else set())
 require(report["binding"]["protocol_action_id"] in allowed and report["binding"]["roles"]["actor"]=="FRA"
         and report["binding"]["roles"]["target"]=="POR","Observation action/roles differ")
 try:return observer.validated_report(report)
 except ProbeError as error:raise Rejected("Invalid typed two-pass observation: "+str(error)) from error

def validate_reload_identity(identity,exit_record,report,binding,observer):
 pid=binding["pid"];created=int(binding["creation"],16)
 require(type(exit_record["pid"]) is int and exit_record["pid"]==pid and exit_record["creation"]==binding["creation"]
         and type(exit_record["process_creation_filetime"]) is int and exit_record["process_creation_filetime"]==created
         and exit_record["kind"]=="exact_process_exit_observation" and exit_record["read_only"] is True
         and exit_record["method"]=="held_handle_wait_and_getprocesstimes" and exit_record["exit_observed"] is True
         and integer(exit_record["process_exit_filetime"],created+1)
         and all(integer(exit_record[k],0,0) for k in ("before_exit_filetime","wait_status","exit_code"))
         and exit_record["executable_sha256"].upper()==LOCAL_SHA256.upper()
         and exit_record["access"]=="QUERY_LIMITED_INFORMATION | SYNCHRONIZE" and exit_record["process_stop_requested_by_observer"] is False,"Held normal exit mismatch")
 sample,_,times=observer.validated_report(report)
 source=identity["source"];state=identity["state"];raw=report["family_snapshot"]
 require(type(identity["schema_version"]) is int and identity["schema_version"]==1 and identity["read_only"] is True
         and identity["build"]["sha256"].upper()==LOCAL_SHA256.upper()
         and identity["build"]["executable_sha256"].upper()==LOCAL_SHA256.upper()
         and same(identity["offset_profile"],{"database_pointer_rva":"0x233d8d0","game_pointer_rva":"0x233fe78"})
         and source["kind"]=="live_process" and type(source["pid"]) is int and source["pid"]==pid
         and type(source["process_creation_filetime"]) is int and source["process_creation_filetime"]==created
         and integer(source["process_exit_filetime"],0,0) and source["held_identity_verified_before_and_after"] is True
         and source["atomic_snapshot"] is False and same(source["access"],["PROCESS_QUERY_INFORMATION","PROCESS_VM_READ"])
         and same(source["module_base"],raw["source"]["module_base"]),"Held RO source identity differs")
 require(state["status"]=="bounded_snapshot" and state["game_pointer"]==sample["game"]==binding["world"]
         and state["database_pointer"]==sample["database"] and state["country_array"]==sample["country_array"]
         and type(state["current_raw_date"]) is int and state["current_raw_date"]==sample["current_raw_date"]==binding["raw_date"]
         and same(state["player"],sample["player"]) and same(state["snapshot_consistency"],{"globals_unchanged":True,"player_unchanged":True,"date_unchanged":True,"atomic":False}),"Held RO selected world/player/date differs")
 require(type(state["countries"]) is list and len(state["countries"])<=4096,"Country observation budget")
 for tag in ("FRA","POR"):
  require(same([c for c in state["countries"] if c["tag"]==tag],[sample["pair"][tag]]),"Full selected country identity differs")
 expected={"pid":pid,"creation":binding["creation"],"world_cookie":binding["world"],"player_handle":"0x0100007a00415246","raw_date":binding["raw_date"]}
 require(same(identity["identity_before_and_after"],[expected,expected]),"Held before/after typed identity mismatch")
 start,end=[filetime(identity[k]) for k in ("capture_started_at_utc","captured_at_utc")]
 require(created<=start<=end<exit_record["process_exit_filetime"] and all(created<=filetime(t.isoformat())<exit_record["process_exit_filetime"] for t in times),"RO captures outside held process lifetime")

def validate_launch(launch,spec,binding):
 require(integer(launch["schema_version"],1,1) and launch["purpose"]=="disposable_save_cold_reload_read_only"
         and type(launch["new_pid"]) is int and launch["new_pid"]==binding["pid"] and launch["creation"]==binding["creation"]
         and type(launch["process_creation_filetime"]) is int and launch["process_creation_filetime"]==int(binding["creation"],16)
         and launch["executable_sha256"].upper()==LOCAL_SHA256.upper() and Path(launch["save"]).name==spec["filename"]
         and launch["save_sha256"].lower()==spec["sha256"] and launch["previous_eu4_process_absent"] is True
         and launch["native_injected"] is False and launch["loaded_save_verified"] is False,"Cold reload selector/provenance differs")

def match_reload(label,spec,action,expected,start_date,parsed,prior,reloaded,identity,stopped,launch,binding,observer):
 reload_binding(binding,label)
 require(action in set(LAYOUTS)|RELOAD_ONLY and expected in ("active","absent"),"Unsupported selected reload action")
 require(binding["raw_date"]==spec["raw_date"] and spec["date"] in DATE_RAW and DATE_RAW[spec["date"]]==spec["raw_date"],"Selected save/reload date differs")
 new,new_state,new_times=observed(reloaded,action,observer)
 old,old_state,old_times=observed(prior,action,observer,True)
 require(type(prior["expected_pid"]) is int and prior["expected_pid"]==ORIGINAL_PID and prior["expected_creation"]==ORIGINAL_CREATION
         and old["game"]==ORIGINAL_WORLD and old["current_raw_date"]<=spec["raw_date"],"Original-process selected observation differs")
 require(type(reloaded["expected_pid"]) is int and reloaded["expected_pid"]==binding["pid"] and reloaded["expected_creation"]==binding["creation"]
         and new["game"]==binding["world"] and new["current_raw_date"]==binding["raw_date"]
         and old_times[1]<new_times[0] and new_state["state"]==old_state["state"]==expected
         and same(semantic(old_state,action),semantic(new_state,action)),"Selected reload semantics differ")
 if expected=="active":require(start_date in DATE_RAW and new_state["object"]["started_raw_date"]==DATE_RAW[start_date],"Serialized/native start date anchor differs")
 else:require(start_date is None,"Absent selected state must not invent start")
 if "subsid" in action and expected=="active":require(new_state["nominal_expiry_raw_date"]>new["current_raw_date"],"Subsidy nominally expired at reload")
 validate_launch(launch,spec,binding);validate_reload_identity(identity,stopped,reloaded,binding,observer)
 serialized=False
 if action in LAYOUTS:
  require(parsed["sha256"]==spec["sha256"] and parsed["size_bytes"]==spec["size_bytes"] and parsed["metadata"]["date"]==spec["date"],"Unbound serialized projection")
  saved_state(parsed,action,expected,start_date);serialized=True
 else:require(expected=="absent","Additional unclosed serialized families support only independent absence observation")
 return {"scope":"selected_serialized_relation_and_typed_reload" if serialized else "typed_reload_selected_absence_only",
  "action":action,"state":expected,"start_date":start_date,"selected_serialized_and_reload_consistent":serialized,
  "typed_reload_state_consistent":True,"serialized_layout_supported":serialized,"reload_pid":binding["pid"],"reload_creation":binding["creation"],
  "same_addresses_across_processes_required":False,"request_causality_verified":False,"settlement_verified":False,"whole_world_unchanged":False,
  "exact_loaded_file_path_verified":False,"normal_ai_acceptance_verified":False,"strict_single_player_verified":False,"production_execution_verified":False}


def relative(root,name):
 require(type(name) is str and name and "\\" not in name and ":" not in name,"Canonical relative artifact path required")
 parts=PurePosixPath(name).parts
 require(parts and not PurePosixPath(name).is_absolute() and str(PurePosixPath(name))==name and all(p not in (".","..") for p in parts),"Artifact path escape")
 current=Path(root).resolve()
 for part in parts:
  current=current/part;require(not current.is_symlink() and not (hasattr(current,"is_junction") and current.is_junction()),"Linked artifact path")
 require(current.resolve().is_relative_to(Path(root).resolve()),"Artifact outside explicit root")
 return current

class FrozenJSON:
 def __init__(self,root,descriptors):
  require(type(descriptors) is dict and 1<=len(descriptors)<=64,"JSON evidence count budget")
  self.root,self.descriptors,self.raw,self.used=root,descriptors,{},set();paths=set();total=0
  for key,item in descriptors.items():
   require(type(key) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}",key) and type(item) is dict and set(item)=={"path","size_bytes","sha256"}
           and integer(item["size_bytes"],1,MAX_JSON) and type(item["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}",item["sha256"]),"Malformed JSON descriptor")
   require(item["path"] not in paths,"Duplicate JSON path");paths.add(item["path"])
   raw=bounded(relative(root,item["path"]));total+=len(raw);require(total<=16*1024*1024,"Total evidence byte budget")
   require(len(raw)==item["size_bytes"] and sha(raw)==item["sha256"],"Evidence bytes/hash changed");self.raw[key]=raw
 def doc(self,key):
  require(type(key) is str and key in self.raw,"Explicit evidence key required");self.used.add(key)
  # Same duplicate-key/non-finite rejection used by all reviewed JSON evidence.
  from bridge.diplomacy_api import decode_json
  return decode_json(self.raw[key].decode("utf-8"))
 def finish(self):
  require(self.used==set(self.descriptors),"Unreferenced input cannot be silently accepted")
  for key,item in self.descriptors.items():require(bounded(relative(self.root,item["path"]))==self.raw[key],"Input changed during review")

GROUP_ACTIONS={"positive":("cancel_military_access","dissolve_alliance","cancel_subsidies"),
 "final":("cancel_military_access","dissolve_alliance","cancel_subsidies","cancel_fleet_basing_rights","revoke_military_access","revoke_embargo")}

def case_template():
 return {"schema_version":1,"purpose":"v14_directional_persistence_case","finalized":False,"inputs":{},"groups":[]}

def review_case(case,save_root,root=ROOT):
 require(type(case) is dict and set(case)=={"schema_version","purpose","finalized","inputs","groups"}
         and integer(case["schema_version"],1,1) and case["purpose"]=="v14_directional_persistence_case" and case["finalized"] is True,"Explicit finalized persistence case required")
 require(type(case["groups"]) is list and len(case["groups"])==2 and [g["label"] for g in case["groups"]]==["positive","final"],"Both explicit fixed save groups required")
 pins,observer=dependencies(root);inputs=FrozenJSON(root,case["inputs"]);results=[]
 for group in case["groups"]:
  require(type(group) is dict and set(group)=={"label","binding","extraction","launch","identity","exit","relations"},"Group exact schema")
  label=group["label"];spec=pins["saves"][label];reload_binding(group["binding"],label)
  require(type(group["relations"]) is list and [r["action"] for r in group["relations"]]==list(GROUP_ACTIONS[label]),"Exact ordered selected relation scope required")
  path=relative(save_root,spec["filename"])
  # The full > 10 MiB files are hashed/parsed in bounded chunks, never loaded whole.
  parsed=parse_saved(path,spec);old_extraction=inputs.doc(group["extraction"])
  require(inputs.descriptors[group["extraction"]]["path"]==spec["snapshot_path"]
          and inputs.descriptors[group["extraction"]]["sha256"]==spec["snapshot_sha256"],"Wrong frozen full-save extraction")
  compare_extraction(parsed,old_extraction)
  launch,identity,stopped=[inputs.doc(group[k]) for k in ("launch","identity","exit")]
  for relation in group["relations"]:
   require(type(relation) is dict and set(relation)=={"action","prior","reloaded","expected","start_date"}
           and relation["expected"]==("active" if label=="positive" else "absent"),"Selected relation case differs")
   result=match_reload(label,spec,relation["action"],relation["expected"],relation["start_date"],parsed,
       inputs.doc(relation["prior"]),inputs.doc(relation["reloaded"]),identity,stopped,launch,group["binding"],observer)
   results.append({"save_label":label,"save_sha256":spec["sha256"],**result})
  stream_hash(path,spec["size_bytes"],spec["sha256"])
 inputs.finish();dependencies(root)
 return {"schema_version":1,"purpose":"v14_selected_directional_persistence_review","status":"reviewed_selected_states",
  "results":results,"selected_observation_count":len(results),"selected_serialized_and_reload_count":sum(r["selected_serialized_and_reload_consistent"] for r in results),
  "case_content_sha256":sha(typed(case).encode()),"input_artifacts":case["inputs"],"game_accessed":False,
  "request_causality_verified":False,"whole_world_unchanged":False,"settlement_verified":False,"strict_single_player_verified":False,"production_execution_verified":False,
  "limitations":["Full-save hashes and launch selection bind supplied files; exact engine-loaded path is not independently proven.",
   "Selected state persistence is not request-ID causality, settlement, whole-world preservation or normal-AI acceptance.",
   "Two equal typed passes are bounded observations, not atomic snapshots or a world epoch.",
   "Fleet and embargo absence only has a typed reload observation; their serialized layout remains unsupported.",
   "Launch native_injected=false is a recorded launch premise, not continuous proof no DLL was subsequently loaded."]}


def write_new(path,value):
 raw=(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+"\n").encode()
 with Path(path).open("xb") as output:output.write(raw);output.flush()

def main(argv=None):
 import argparse
 from bridge.diplomacy_api import decode_json
 parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest="mode",required=True)
 t=sub.add_parser("template");t.add_argument("--output",type=Path,required=True)
 r=sub.add_parser("review");r.add_argument("--case",type=Path,required=True);r.add_argument("--save-root",type=Path,required=True);r.add_argument("--output",type=Path,required=True)
 args=parser.parse_args(argv)
 try:
  if args.mode=="template":write_new(args.output,case_template())
  else:
   raw=bounded(args.case,256*1024);case=decode_json(raw.decode());result=review_case(case,args.save_root)
   require(bounded(args.case,256*1024)==raw,"Case changed during review");write_new(args.output,result)
  return 0
 except (ValueError,KeyError,TypeError,OSError,ProbeError) as error:
  print("Persistence review rejected: "+str(error),file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())
