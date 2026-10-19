"""Pure boundary binding tests. Never calls a memory sampler."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import census


class CensusTests(unittest.TestCase):
    def setUp(self):
        self.command = dict(kind='observe',boundary='initial',raw_date=100,last_sequence=1,
                            pid=12,creation='0000000000000001',world_cookie='0x20000',run_id='a',issued_uptime_ms=200)
        self.state = {'status':'bounded_snapshot','country_identities_verified':True,'memory_bytes_requested':10,
                      'snapshot_consistency':{'globals_unchanged':True,'player_unchanged':True,'date_unchanged':True,'atomic':False},
                      'actor_diplomats':{'entry_count':2,'state_zero_count':1,'entries':[
                          {'state_raw_18':0,'state_zero_available_candidate':True},
                          {'state_raw_18':1,'state_zero_available_candidate':False}]}}
        self.identity = {'module_base':'0x10000','player':{'handle':'0x123','slot':3}}
        self.source = {'pid':12,'process_creation_filetime':1,'process_exit_filetime':0,'module_base':'0x10000'}
        self.raw = {'module_base':'0x10000','game':'0x20000','current_raw_date':100,'player':self.identity['player']}

    def test_boundary_only_exact_command(self):
        census.validate_command(self.command)
        for key,value in (('boundary','each'),('pid',True),('last_sequence',1.0),('world_cookie','0x0'),('run_id','../x')):
            changed={**self.command,key:value}
            with self.subTest(key=key),self.assertRaises(ValueError):census.validate_command(changed)

    def test_unknown_command_fields_rejected(self):
        with self.assertRaises(ValueError):census.validate_command({**self.command,'action':'insult'})

    def test_resource_read_counter_may_differ(self):
        second={**self.state,'memory_bytes_requested':900}
        self.assertEqual(census.resource_fields(self.state,second),(2,1))

    def test_changed_resource_state_is_not_consistent(self):
        second=deepcopy(self.state);second['actor_diplomats']['entries'][0]['state_raw_18']=1
        with self.assertRaises(ValueError):census.resource_fields(self.state,second)

    def test_resource_scalar_coercion_rejected(self):
        for key,value in (('entry_count',2.0),('state_zero_count',True)):
            changed=deepcopy(self.state);changed['actor_diplomats'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):census.resource_fields(changed,changed)

    def test_resource_count_must_recompute(self):
        changed=deepcopy(self.state);changed['actor_diplomats']['state_zero_count']=2
        with self.assertRaises(ValueError):census.resource_fields(changed,changed)

    def test_resource_boolean_state_not_an_integer(self):
        changed=deepcopy(self.state);changed['actor_diplomats']['entries'][1]['state_raw_18']=True
        with self.assertRaises(ValueError):census.resource_fields(changed,changed)

    def test_resource_candidate_boolean_matches_actual_byte(self):
        changed=deepcopy(self.state);changed['actor_diplomats']['entries'][1]['state_zero_available_candidate']=True
        with self.assertRaises(ValueError):census.resource_fields(changed,changed)

    def test_binding_exact_identity(self):
        census.binding(self.raw,self.source,self.command,self.identity)
        for key,value in (('pid',13),('process_creation_filetime',2),('process_exit_filetime',1),('module_base','0x20000')):
            changed={**self.source,key:value}
            with self.subTest(key=key),self.assertRaises(ValueError):census.binding(self.raw,changed,self.command,self.identity)

    def test_binding_world_date_and_full_player(self):
        for key,value in (('game','0x20001'),('current_raw_date',101),('player',{'handle':'0x124','slot':3})):
            with self.subTest(key=key),self.assertRaises(ValueError):census.binding({**self.raw,key:value},self.source,self.command,self.identity)

    def test_binding_typed_player_equality(self):
        with self.assertRaises(ValueError):census.binding({**self.raw,'player':{'handle':'0x123','slot':3.0}},self.source,self.command,self.identity)

    def test_health_boundary_does_not_allow_changed_sequence(self):
        evidence={'last_sequence':2}
        with self.assertRaises(ValueError):census.health(evidence,{},self.command)


if __name__ == '__main__':unittest.main()
