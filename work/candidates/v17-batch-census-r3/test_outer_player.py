"""Exercise the real sample call chain up to the first selected observer."""
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import census
import test_census


class Sentinel(Exception): pass


class OuterPlayerTests(unittest.TestCase):
    def call_boundary(self, reference_handle):
        fixture=test_census.CensusTests();fixture.setUp()
        command=fixture.command
        held={'player_handle':'0x0100007a00415246'}
        reference={'module_base':'0x10000','player':{'handle':reference_handle,'slot':122}}
        state={**fixture.state,'game_pointer':command['world_cookie'],
               'current_raw_date':command['raw_date'],'player':reference['player']}
        class Process:
            reader=SimpleNamespace(base=0x10000)
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def snapshot(self):return held
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(census.lab,'OUTPUT',Path(directory)), \
                 patch.object(census,'verify_pins'),patch.object(census,'health'), \
                 patch.object(census.lab,'_no_links'), \
                 patch.object(census.lab,'session_path',return_value=Path(directory)), \
                 patch.object(census.lab,'LiveLabProcess',return_value=Process()), \
                 patch.object(census.lab,'read_session_metadata',return_value={}), \
                 patch.object(census.lab,'read_evidence',return_value={}), \
                 patch.object(census.probe,'inspect_state',return_value=state), \
                 patch.object(census.core,'read_identity',return_value=reference), \
                 patch.object(census.core,'sample_process',side_effect=Sentinel('first observer')):
                census.sample(command)

    def test_reference_and_diagnostic_other_player_rejected_before_observers(self):
        with self.assertRaisesRegex(ValueError,'Full handle differs'):
            self.call_boundary('0x010000d800524f50')

    def test_padded_outer_handle_reaches_first_selected_observer(self):
        with self.assertRaises(Sentinel):
            self.call_boundary('0x100007a00415246')


if __name__=='__main__':unittest.main()
