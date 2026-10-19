"""Small synthetic text; no actual saved file, process, or native call."""
import copy,io,json,unittest
from pathlib import Path
import parser as p

def fixture():
 mods=' '.join('modifier={modifier="'+name+'" date=1449.11.11}' for name in sorted(p.MODIFIERS))
 return ('EU4txt\ndate=1444.12.26 player="FRA" map_area_data { ignored={nested=yes} }\n'
 'provinces={-227={owner="POR" controller="POR" diplomacy_construction={'
 'start_date=1444.11.11 total=12 original_total=12 date=1444.11.23 envoy=0 country="FRA" actor="FRA" recipient="POR" '
 'from_province=183 to_province=227 once=no action_token=curry_favors}}}\n'
 'countries={ENG={'+mods+'} FRA={initialized_rivals=yes rival={country="BUR" date=1444.11.11} enemy="ENG" '
 'diplomats={envoy={action=2 name="A \\"quoted\\" {name}" type=3 id=0} envoy={name="Other" type=3 id=1}} '
 'active_relations={POR={last_send_diplomat=1444.11.11 attitude="attitude_neutral"} BUR={attitude="attitude_rivalry"}}} '
 'BUR={initialized_rivals=yes rival={country="FRA" date=1444.11.11} enemy="FRA" trade_embargoed_by={NAV} '
 'active_relations={FRA={attitude="attitude_rivalry"} NAV={attitude="attitude_neutral"}}} '
 'NAV={subject_focus=5 overlord="FRA" num_of_trade_embargos=1 trade_embargoes={BUR} transfer_trade_power_to={FRA} '
 'subject_interactions={no yes no no yes no yes} active_relations={BUR={attitude="attitude_neutral" is_embargoing=yes}}} '
 'POR={active_relations={FRA={favors=0.053 attitude="attitude_neutral"}}}}\n'
 'diplomacy={curry_favors={first="FRA" second="POR" start_date=1444.11.11 envoy=0} '
 'dependency={first="FRA" second="NAV" subject_type="vassal" start_date=1444.11.11} '
 'transfer_trade_power={first="NAV" second="FRA" amount=1.000 is_enforced=yes start_date=1444.11.11}}\n').encode('latin1')
def parse(raw):return p.parse_stream(io.BytesIO(raw))
def selected(raw):return p.selected(parse(raw))
class Tests(unittest.TestCase):
 def reject(self,raw):
  with self.assertRaises((p.Rejected,p.g.SaveError,ValueError)):selected(raw)
 def test_minimal_whole_text_and_three_links(self):
  result=selected(fixture());self.assertEqual(result['nav']['set_positions'],[1,4,6]);self.assertEqual(result['curry']['linked_envoy_id'],0)
  self.assertEqual(result['curry']['envoys'][1]['action_serialized'],None)
  self.assertFalse(result['nav']['named_bit_order_verified']);self.assertFalse(result['persistence_verified']);self.assertFalse(result['production_ready'])
 def test_quoted_braces_and_chunks(self):
  class Chunked(io.BytesIO):
   def read(self,n=-1):return super().read(min(n,7) if self.tell()>=6 else min(n,6))
  self.assertEqual(p.selected(p.parse_stream(Chunked(fixture()))),selected(fixture()))
 def test_complete_signature_and_syntax(self):
  for raw in (fixture().replace(b'EU4txt',b'EU4bin',1),fixture()[:-3],fixture()+b'}',fixture()+b'broken=',fixture()+b'unclosed={'):
   with self.subTest(raw=raw[-20:]):self.reject(raw)
 def test_map_area_exact_anonymous_only(self):
  for value in (b'map_area_data={x=1}',b'"map_area_data" {x=1}',b'map_area_data 5',b'{x=1}',b'other {x=1}'):
   self.reject(fixture().replace(b'map_area_data { ignored={nested=yes} }',value))
  self.reject(fixture()+b'map_area_data {}')
 def test_required_container_duplicates_and_shape(self):
  for ending in (b'countries={}',b'provinces={}',b'diplomacy={}',b'date=1444.12.26',b'player="FRA"'):
   self.reject(fixture()+ending)
  self.reject(fixture().replace(b'ENG={',b'ENG=no fake={'))
 def test_country_and_province_duplicates(self):
  self.reject(fixture().replace(b'countries={',b'countries={FRA={} ',1))
  self.reject(fixture().replace(b'provinces={',b'provinces={-227={} ',1))
 def test_modifier_missing_duplicate_and_wrong_shape(self):
  token=b'modifier={modifier="corrupt_officials" date=1449.11.11}'
  for new in (b'',token+token,token.replace(b'date=',b'date=1449.11.11 date='),token.replace(b'date=1449.11.11',b'date={x=1}')):
   self.reject(fixture().replace(token,new))
 def test_subject_list_shape_length_and_boolean(self):
  for new in (b'{no yes no no yes no}',b'{no yes no no yes no yes no}',b'{no 1 no no yes no yes}',b'{no yes x=no no yes no yes}',b'yes'):
   self.reject(fixture().replace(b'{no yes no no yes no yes}',new))
 def test_focus_canonical_integer_and_range(self):
  for value in (b'true',b'5.0',b'05',b'-1',b'6',b'"5"'):
   # Quoted integers are valid scalar text under the shared grammar; it is
   # recorded verbatim and not a JSON int alias. All other variants reject.
   if value==b'"5"':self.assertEqual(selected(fixture().replace(b'subject_focus=5',b'subject_focus='+value))['nav']['subject_focus'],5)
   else:self.reject(fixture().replace(b'subject_focus=5',b'subject_focus='+value))
 def test_rival_current_vs_enemy_direction(self):
  result=selected(fixture());self.assertEqual(result['rivals']['FRA'][0]['country'],'BUR');self.assertEqual(result['enemies']['FRA'],['ENG'])
  token=b'rival={country="BUR" date=1444.11.11}'
  self.reject(fixture().replace(token,token+token))
  self.reject(fixture().replace(token,b'rival={country="FRA" date=1444.11.11}'))
 def test_curry_relation_direction_and_required_envoy(self):
  for value in (b'first="POR" second="FRA"',b'first="FRA" second="ENG"'):
   self.reject(fixture().replace(b'first="FRA" second="POR"',value))
  self.reject(fixture().replace(b'curry_favors={first="FRA" second="POR" start_date=1444.11.11 envoy=0}',b'curry_favors={first="FRA" second="POR" start_date=1444.11.11}'))
 def test_mission_reference_token_province_and_roles(self):
  for old,new in ((b'to_province=227',b'to_province=228'),(b'action_token=curry_favors',b'action_token=improve_relation'),
   (b'country="FRA" actor="FRA"',b'country="FRA" actor="POR"'),(b'once=no',b'once=yes'),(b'date=1444.11.23 envoy=0',b'date=1444.11.23 envoy=1')):
   self.reject(fixture().replace(old,new))
 def test_mission_owner_and_start_binding(self):
  self.reject(fixture().replace(b'owner="POR"',b'owner="ENG"'))
  self.reject(fixture().replace(b'diplomacy_construction={start_date=1444.11.11',b'diplomacy_construction={start_date=1444.11.12'))
 def test_diplomat_id_action_type_and_duplicates(self):
  for old,new in ((b'type=3 id=0',b'type=4 id=0'),(b'type=3 id=1',b'type=3 id=0'),(b'action=2 name=',b'action=0 name='),(b'id=0}',b'id=9}')):
   self.reject(fixture().replace(old,new))
 def test_dependency_exact_roles_and_variant(self):
  self.reject(fixture().replace(b'subject_type="vassal"',b'subject_type="tributary"'))
  self.reject(fixture().replace(b'subject_type="vassal"',b'subject_type="vassal" hidden=yes'))
  self.reject(fixture().replace(b'first="FRA" second="NAV"',b'first="NAV" second="FRA"'))
 def test_trade_and_embargo_serialized_values(self):
  for old,new in ((b'amount=1.000',b'amount=1.500'),(b'is_enforced=yes',b'is_enforced=1'),(b'num_of_trade_embargos=1',b'num_of_trade_embargos=2')):
   self.reject(fixture().replace(old,new))
 def test_active_fields_bare_nested_and_duplicates(self):
  for value in (b'FRA={favors={x=1}',b'FRA={favors=0.053 favors=0.053',b'FRA={favors=nan',b'FRA={unknown=0.053'):
   self.reject(fixture().replace(b'FRA={favors=0.053',value))
 def test_token_and_depth_budget(self):
  self.reject(fixture()+b'x="'+b'a'*(p.g.MAX_TOKEN+1)+b'"')
  self.reject(fixture()+b'x={'*129+b'}'*129)
 def test_reader_and_projected_type_aliases(self):
  for x in (True,1.0,'1'):
   with self.assertRaises(p.Rejected):p.Reader(io.BytesIO()).read(x)
  parsed=parse(fixture())
  for key in ('schema','parsed_complete'):
   altered=copy.deepcopy(parsed);altered[key]=1.0 if key=='schema' else 1
   with self.assertRaises(p.Rejected):p.selected(altered)
  for key in ('line','byte_offset'):
   altered=copy.deepcopy(parsed);altered['records'][0]['record'][key]=True
   with self.assertRaises(p.Rejected):p.selected(altered)
 def test_unrelated_nested_names_do_not_satisfy(self):
  raw=fixture().replace(b'subject_focus=5',b'ignored={subject_focus=5}')
  self.reject(raw)
 def test_companion_unknown_modifier_is_preserved_without_claim(self):
  raw=fixture().replace(b'ENG={',b'ENG={modifier={modifier="other" date=1449.1.1 permanent=yes} ',1)
  self.assertEqual(set(selected(raw)['spy_modifiers']),p.MODIFIERS)

if __name__=='__main__':unittest.main(verbosity=2)
