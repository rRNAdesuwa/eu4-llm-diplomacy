"""Independent-pass diagnostics and full handle encoding regression cases."""
from copy import deepcopy
import unittest
import census
import test_census


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        fixture=test_census.CensusTests(); fixture.setUp()
        self.state=deepcopy(fixture.state);self.command=fixture.command;self.identity=fixture.identity
        self.state.update(game_pointer=self.command['world_cookie'],current_raw_date=self.command['raw_date'],player=self.identity['player'])

    def test_all_stable_diagnostic_fields(self):
        census.diagnostic_binding(self.state,self.command,self.identity)

    def test_original_three_unstable_and_four_missing_flags(self):
        for key in self.state['snapshot_consistency']:
            changed=deepcopy(self.state);del changed['snapshot_consistency'][key]
            with self.subTest(missing=key),self.assertRaises(ValueError):census.resource_fields(changed,changed)
            if key!='atomic':
                changed=deepcopy(self.state);changed['snapshot_consistency'][key]=False
                with self.subTest(unstable=key),self.assertRaises(ValueError):census.resource_fields(changed,changed)

    def test_each_pass_must_be_stable(self):
        for ordinal in (0,1):
            passes=[deepcopy(self.state),deepcopy(self.state)];passes[ordinal]['snapshot_consistency']['date_unchanged']=False
            with self.subTest(ordinal=ordinal),self.assertRaises(ValueError):census.resource_fields(*passes)

    def test_atomic_and_scalar_coercion_rejected(self):
        for key,value in (('atomic',True),('globals_unchanged',1),('date_unchanged','true')):
            changed=deepcopy(self.state);changed['snapshot_consistency'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):census.resource_fields(changed,changed)

    def test_diagnostic_world_date_full_player_bound(self):
        for key,value in (('game_pointer','0x20001'),('current_raw_date',101),('current_raw_date',100.0),('player',{'handle':'0x124','slot':3})):
            with self.subTest(key=key),self.assertRaises(ValueError):census.diagnostic_binding({**self.state,key:value},self.command,self.identity)

    def test_leading_zero_full_handles_are_same_value(self):
        census.same_handle('0x100007a00415246','0x0100007a00415246')

    def test_wrong_or_invalid_handles_rejected(self):
        for first,second in (('0x100007a00415246','0x100007b00415246'),('0x0','0x0'),(True,'0x1'),('0x10000000000000000','0x1')):
            with self.subTest(first=first),self.assertRaises(ValueError):census.same_handle(first,second)


if __name__=='__main__':unittest.main()
