"""Bounded ASCII fixtures and typed synthetic-memory reload evidence only."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import hashlib,importlib.util,io,json
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
m=load("directional_persistence_tested",HERE/"matcher.py")
f=load("directional_persistence_sparse_fixtures",ROOT/"work/candidates/directional-pair-observer-1375/test_observer.py")
observer=f.candidate
HEADER=b'EU4txt\ndate=1444.12.1\nplayer="FRA"\ncountries={ FRA={} POR={} }\ndiplomacy={\n'
RECORDS={
 "dissolve_alliance":b'alliance={ first="FRA" second="POR" start_date=1444.11.25 }',
 "cancel_military_access":b'military_access={ first="FRA" second="POR" start_date=1444.12.1 enforce_peace=no }',
 "cancel_subsidies":b'subsidies={ first="FRA" second="POR" start_date=1444.11.15 amount=1.000 duration=10 }'}
START={"dissolve_alliance":"1444.11.25","cancel_military_access":"1444.12.1","cancel_subsidies":"1444.11.15"}
def saved_raw(records=None,date="1444.12.1"):
 return HEADER.replace(b'1444.12.1',date.encode(),1)+b'\n'.join(RECORDS.values() if records is None else records)+b'\n}\n'
def parsed(records=None,date="1444.12.1"):return m.parse_stream(io.BytesIO(saved_raw(records,date)))
def stamp(created,seconds):
 t=datetime(1601,1,1,tzinfo=timezone.utc)+timedelta(microseconds=created//10,seconds=seconds)
 return t.isoformat()
def snapshot(action,active,reloaded=False,label="positive"):
 report=f.snapshot(action,active,after=reloaded)
 raw=report["family_snapshot"]
 binding=dict(m.POSITIVE_RELOAD) if label=="positive" else dict(m.FINAL_RELOAD)
 pid=binding["pid"] if reloaded else m.ORIGINAL_PID;creation=binding["creation"] if reloaded else m.ORIGINAL_CREATION
 report["expected_pid"]=pid;report["expected_creation"]=creation
 raw["source"].update(pid=pid,process_creation_filetime=int(creation,16),process_exit_filetime=0)
 raw["capture_started_at"]=stamp(int(creation,16),60);raw["capture_finished_at"]=stamp(int(creation,16),61)
 date=binding["raw_date"] if reloaded else m.DATE_RAW["1444.12.1"] if label=="positive" else m.DATE_RAW["1444.12.7"]
 for sample in raw["observation"]["passes"]:
  sample["game"]=binding["world"] if reloaded else m.ORIGINAL_WORLD;sample["current_raw_date"]=date
  if active:
   obj=sample["relation"]["object"];obj["started_raw_date"]=m.DATE_RAW[START[action]]
 raw["observation"]["state"]=observer.legacy.inspect_state(raw["observation"]["passes"][0])
 return report,binding

def bundle(action="cancel_subsidies",label="positive"):
 active=label=="positive";prior,_=snapshot(action,active,False,label);new,binding=snapshot(action,active,True,label)
 save=parsed(None if active else [],"1444.12.1" if active else "1444.12.7")
 spec=dict(filename="llm_diplomacy_1375_v14_test.eu4",size_bytes=save["size_bytes"],sha256=save["sha256"],date=save["metadata"]["date"],raw_date=binding["raw_date"])
 sample=new["family_snapshot"]["observation"]["passes"][0];created=int(binding["creation"],16)
 identity=dict(schema_version=1,read_only=True,build=dict(sha256=m.LOCAL_SHA256,executable_sha256=m.LOCAL_SHA256),offset_profile=dict(database_pointer_rva="0x233d8d0",game_pointer_rva="0x233fe78"),
  source=dict(kind="live_process",pid=binding["pid"],process_creation_filetime=created,process_exit_filetime=0,held_identity_verified_before_and_after=True,atomic_snapshot=False,
   access=["PROCESS_QUERY_INFORMATION","PROCESS_VM_READ"],module_base=new["family_snapshot"]["source"]["module_base"]),
  state=dict(status="bounded_snapshot",game_pointer=sample["game"],database_pointer=sample["database"],country_array=sample["country_array"],current_raw_date=binding["raw_date"],player=deepcopy(sample["player"]),countries=list(deepcopy(sample["pair"]).values()),snapshot_consistency=dict(globals_unchanged=True,player_unchanged=True,date_unchanged=True,atomic=False)),
  capture_started_at_utc=stamp(created,50),captured_at_utc=stamp(created,51))
 held=dict(pid=binding["pid"],creation=binding["creation"],world_cookie=binding["world"],player_handle="0x0100007a00415246",raw_date=binding["raw_date"])
 identity["identity_before_and_after"]=[dict(held),dict(held)]
 stopped=dict(pid=binding["pid"],creation=binding["creation"],process_creation_filetime=created,kind="exact_process_exit_observation",read_only=True,method="held_handle_wait_and_getprocesstimes",exit_observed=True,process_exit_filetime=created+2000000000,before_exit_filetime=0,wait_status=0,exit_code=0,executable_sha256=m.LOCAL_SHA256,access="QUERY_LIMITED_INFORMATION | SYNCHRONIZE",process_stop_requested_by_observer=False)
 launch=dict(schema_version=1,purpose="disposable_save_cold_reload_read_only",new_pid=binding["pid"],creation=binding["creation"],process_creation_filetime=created,executable_sha256=m.LOCAL_SHA256,save=spec["filename"],save_sha256=spec["sha256"],previous_eu4_process_absent=True,native_injected=False,loaded_save_verified=False)
 return dict(label=label,spec=spec,action=action,expected="active" if active else "absent",start_date=START[action] if active else None,parsed=save,prior=prior,reloaded=new,identity=identity,stopped=stopped,launch=launch,binding=binding,observer=observer)

class SaveTests(unittest.TestCase):
 def test_three_exact_positive_records_and_final_absence(self):
  p=parsed()
  for action in RECORDS:m.saved_state(p,action,"active",START[action]);m.saved_state(parsed([],"1444.12.7"),action,"absent",None)
 def test_access_reverse_is_not_held_right_and_revoke_direction_is_distinct(self):
  p=parsed([RECORDS["cancel_military_access"].replace(b'first="FRA" second="POR"',b'first="POR" second="FRA"')])
  m.saved_state(p,"cancel_military_access","absent",None)
  m.saved_state(p,"revoke_military_access","active","1444.12.1")
  with self.assertRaises(ValueError):m.saved_state(p,"cancel_military_access","active","1444.12.1")
 def test_alliance_symmetric_without_initiator_claim(self):
  p=parsed([RECORDS["dissolve_alliance"].replace(b'first="FRA" second="POR"',b'first="POR" second="FRA"')]);m.saved_state(p,"dissolve_alliance","active","1444.11.25")
 def test_duplicate_or_nested_selected_fields_reject(self):
  for bad in [b'alliance={ first="FRA" first="POR" second="POR" start_date=1444.11.25 }',b'alliance={ first="FRA" second="POR" nested={} start_date=1444.11.25 }']:
   with self.subTest(bad=bad),self.assertRaises(ValueError):parsed([bad])
 def test_duplicate_relation_or_unknown_variant_reject(self):
  for records in [[RECORDS["dissolve_alliance"]]*2,[RECORDS["dissolve_alliance"].replace(b' }',b' end_date=1444.12.1 }')]]:
   with self.assertRaises(ValueError):m.saved_state(parsed(records),"dissolve_alliance","active","1444.11.25")
 def test_subsidy_fixed_milli_and_years_and_explicit_start(self):
  for before,after in [(b'1.000',b'1.001'),(b'duration=10',b'duration=120'),(b'1444.11.15',b'1444.11.25')]:
   with self.subTest(after=after),self.assertRaises(ValueError):m.saved_state(parsed([RECORDS["cancel_subsidies"].replace(before,after)]),"cancel_subsidies","active","1444.11.15")
 def test_enforce_peace_and_missing_field_reject(self):
  for raw in [RECORDS["cancel_military_access"].replace(b'enforce_peace=no',b'enforce_peace=yes'),RECORDS["cancel_military_access"].replace(b'enforce_peace=no',b'')]:
   with self.assertRaises(ValueError):m.saved_state(parsed([raw]),"cancel_military_access","active","1444.12.1")
 def test_quoted_braces_and_unrelated_record_do_not_fake_selected_state(self):
  raw=saved_raw([]).replace(b'FRA={}',b'FRA={ note="{ ignored }" }').replace(b'diplomacy={',b'diplomacy={ alliance={ first="ENG" second="POR" start_date=1444.11.25 }')
  p=m.parse_stream(io.BytesIO(raw));m.saved_state(p,"dissolve_alliance","absent",None)
 def test_missing_duplicate_and_truncated_containers_reject(self):
  raw=saved_raw()
  for bad in [raw[:-3],raw.replace(b'diplomacy={',b'other={'),raw+b'diplomacy={}\n',raw.replace(b'POR={}',b'FRA={}')]:
   with self.subTest(bad=bad[-30:]),self.assertRaises(ValueError):m.parse_stream(io.BytesIO(bad))
 def test_stream_hash_and_pin_size_do_not_accept_changed_save(self):
  raw=saved_raw();spec=dict(filename="fixture.eu4",size_bytes=len(raw),sha256=m.sha(raw),date="1444.12.1")
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory)/spec["filename"];p.write_bytes(raw);self.assertEqual(m.parse_saved(p,spec)["sha256"],m.sha(raw));p.write_bytes(raw+b' ')
   with self.assertRaises(ValueError):m.parse_saved(p,spec)
 def test_bool_int_projection_alias_and_unclosed_family_unsupported(self):
  p=parsed();p["selected_records"][0]["fields"]["start_date"]=True
  with self.assertRaises(ValueError):m.saved_state(p,"dissolve_alliance","active","1444.11.25")
  with self.assertRaises(ValueError):m.saved_state(parsed([]),"cancel_fleet_basing_rights","absent",None)
 def test_parser_bounded_token_and_depth(self):
  for raw in [saved_raw([])+b'x='+b'a'*(grammar.MAX_TOKEN+1),b'EU4txt\n'+b'x={'*129+b'}'*129]:
   with self.assertRaises(ValueError):m.parse_stream(io.BytesIO(raw))

class ReloadTests(unittest.TestCase):
 def test_three_positive_selected_relations_and_final_absence(self):
  for action in RECORDS:
   for label in ("positive","final"):
    result=m.match_reload(**bundle(action,label));self.assertTrue(result["selected_serialized_and_reload_consistent"])
    for k in ("request_causality_verified","settlement_verified","whole_world_unchanged","exact_loaded_file_path_verified","strict_single_player_verified","production_execution_verified"):self.assertFalse(result[k])
 def test_positive_give_subsidy_reference_may_match_cancel_observer_same_roles(self):
  b=bundle();b["prior"]["binding"]=observer.binding("give_subsidies","POR")
  self.assertTrue(m.match_reload(**b)["selected_serialized_and_reload_consistent"])
 def test_later_original_capture_cannot_be_labeled_presave(self):
  b=bundle("cancel_military_access")
  for sample in b["prior"]["family_snapshot"]["observation"]["passes"]:sample["current_raw_date"]+=48
  with self.assertRaises(ValueError):m.match_reload(**b)
 def test_reload_only_fleet_absence_does_not_claim_serialized_layout(self):
  b=bundle("cancel_military_access","final");action="cancel_fleet_basing_rights"
  b["action"]=action;b["prior"],_=snapshot(action,False,False,"final");b["reloaded"],_=snapshot(action,False,True,"final")
  # Bind held RO records to this report's selected addresses, same identity.
  sample=b["reloaded"]["family_snapshot"]["observation"]["passes"][0]
  b["identity"]["state"].update(player=deepcopy(sample["player"]),countries=list(deepcopy(sample["pair"]).values()))
  result=m.match_reload(**b);self.assertFalse(result["serialized_layout_supported"]);self.assertFalse(result["selected_serialized_and_reload_consistent"])
 def test_full_creation_float_or_bool_reject_at_each_evidence_boundary(self):
  for location in ("binding","identity","stopped","launch","reloaded"):
   b=bundle()
   if location=="binding":b[location]["pid"]=float(b[location]["pid"])
   elif location=="identity":b[location]["source"]["process_creation_filetime"]=float(b[location]["source"]["process_creation_filetime"])
   elif location=="reloaded":b[location]["family_snapshot"]["source"]["process_creation_filetime"]=float(b[location]["family_snapshot"]["source"]["process_creation_filetime"])
   else:b[location]["process_creation_filetime"]=float(b[location]["process_creation_filetime"])
   with self.subTest(location=location),self.assertRaises((ValueError,m.ProbeError)):m.match_reload(**b)
 def test_second_pass_malformed_cannot_hide_behind_state_summary(self):
  b=bundle();b["reloaded"]["family_snapshot"]["observation"]["passes"][1]["relation"]["object"]["removed"]=False
  with self.assertRaises((ValueError,m.ProbeError)):m.match_reload(**b)
 def test_stored_state_alias_and_swapped_roles_reject(self):
  for mode in ("state","role"):
   b=bundle()
   if mode=="state":b["reloaded"]["family_snapshot"]["observation"]["state"]["object"]["duration_years"]=10.0
   else:b["reloaded"]["binding"]["roles"]["payer"]="POR"
   with self.subTest(mode=mode),self.assertRaises((ValueError,m.ProbeError)):m.match_reload(**b)
 def test_same_process_or_before_save_or_late_capture_reject(self):
  for change in ("process","date","time"):
   b=bundle()
   if change=="process":b["binding"]["pid"]=m.ORIGINAL_PID
   elif change=="date":b["binding"]["raw_date"]-=24
   else:b["stopped"]["process_exit_filetime"]=int(b["binding"]["creation"],16)+1
   with self.subTest(change=change),self.assertRaises(ValueError):m.match_reload(**b)
 def test_start_date_or_fixed_subsidy_values_cannot_be_invented(self):
  b=bundle();b["start_date"]="1444.11.25"
  with self.assertRaises(ValueError):m.match_reload(**b)
 def test_selected_addresses_may_differ_across_processes(self):
  b=bundle();self.assertNotEqual(b["prior"]["family_snapshot"]["observation"]["passes"][0]["game"],b["reloaded"]["family_snapshot"]["observation"]["passes"][0]["game"])
  raw=b["reloaded"]["family_snapshot"]
  for sample in raw["observation"]["passes"]:
   relation=sample["relation"];relation["object"]["address"]="0x570000"
   for side in ("left","right"):relation[side]["entries"][0]["object"]="0x570000"
  raw["observation"]["state"]=observer.legacy.inspect_state(raw["observation"]["passes"][0])
  self.assertTrue(m.match_reload(**b)["typed_reload_state_consistent"])
 def test_missing_launch_no_injection_and_unverified_path_flags_reject(self):
  for key,value in (("native_injected",True),("loaded_save_verified",True),("previous_eu4_process_absent",False),("save_sha256","0"*64)):
   b=bundle();b["launch"][key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):m.match_reload(**b)
 def test_held_identity_both_equal_float_still_rejected(self):
  b=bundle()
  for h in b["identity"]["identity_before_and_after"]:h["raw_date"]=float(h["raw_date"])
  with self.assertRaises(ValueError):m.match_reload(**b)
 def test_final_missing_identity_is_not_defaulted_equal_none(self):
  b=bundle(label="final");del b["identity"]["source"]["process_creation_filetime"]
  with self.assertRaises((ValueError,KeyError)):m.match_reload(**b)

class CaseTests(unittest.TestCase):
 def test_full_two_save_nine_selection_pipeline_without_live_access(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);save_root=root/"saves";save_root.mkdir();case=m.case_template();case["finalized"]=True;pins={"saves":{}}
   def store(key,doc):
    name=key+".json";raw=(json.dumps(doc,sort_keys=True)+"\n").encode();(root/name).write_bytes(raw)
    case["inputs"][key]=dict(path=name,size_bytes=len(raw),sha256=m.sha(raw));return key
   for label in ("positive","final"):
    date="1444.12.1" if label=="positive" else "1444.12.7";raw=saved_raw(None if label=="positive" else [],date)
    filename=label+".eu4";path=save_root/filename;path.write_bytes(raw)
    extraction=grammar.inspect_save(path,actor="FRA",targets=("POR",));ekey=store(label+"-extraction",extraction)
    b=bundle("cancel_military_access",label)
    spec=dict(filename=filename,size_bytes=len(raw),sha256=m.sha(raw),date=date,raw_date=b["binding"]["raw_date"],snapshot_path=ekey+".json",snapshot_sha256=case["inputs"][ekey]["sha256"])
    pins["saves"][label]=spec;b["launch"].update(save=filename,save_sha256=spec["sha256"])
    group=dict(label=label,binding=b["binding"],extraction=ekey,launch=store(label+"-launch",b["launch"]),identity=store(label+"-identity",b["identity"]),exit=store(label+"-exit",b["stopped"]),relations=[])
    for action in m.GROUP_ACTIONS[label]:
     row=bundle(action,label)
     group["relations"].append(dict(action=action,prior=store(label+"-"+action+"-prior",row["prior"]),reloaded=store(label+"-"+action+"-reload",row["reloaded"]),expected=row["expected"],start_date=row["start_date"]))
    case["groups"].append(group)
   with patch.object(m,"dependencies",return_value=(pins,observer)):
    result=m.review_case(case,save_root,root)
   self.assertEqual(result["selected_observation_count"],9);self.assertEqual(result["selected_serialized_and_reload_count"],7);self.assertFalse(result["production_execution_verified"])
 def test_frozen_json_rejects_bool_size_duplicate_nonfinite_and_mutation(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);path=root/"a.json";raw=b'{"x":1}';path.write_bytes(raw);desc=dict(path="a.json",size_bytes=len(raw),sha256=m.sha(raw))
   with self.assertRaises(ValueError):m.FrozenJSON(root,{"a":dict(desc,size_bytes=True)})
   with self.assertRaises(ValueError):m.FrozenJSON(root,{"a":desc,"b":desc})
   frozen=m.FrozenJSON(root,{"a":desc});self.assertEqual(frozen.doc("a"),{"x":1});path.write_bytes(raw+b' ')
   with self.assertRaises(ValueError):frozen.finish()
 def test_duplicate_json_keys_and_nonfinite_fail_before_semantics(self):
  for raw in (b'{"x":1,"x":2}',b'{"x":NaN}'):
   with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);(root/"a.json").write_bytes(raw);frozen=m.FrozenJSON(root,{"a":dict(path="a.json",size_bytes=len(raw),sha256=m.sha(raw))})
    with self.assertRaises(ValueError):frozen.doc("a")
 def test_unfinalized_case_cannot_run(self):
  with self.assertRaises(ValueError):m.review_case(m.case_template(),Path("unused"))

grammar=m.grammar
if __name__=="__main__":unittest.main(verbosity=2)
