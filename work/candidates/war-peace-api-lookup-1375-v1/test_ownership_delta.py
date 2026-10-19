"""One new pure-file ownership boundary; never import or rerun the original suite."""
import json
import unittest

import war_peace_lookup as lookup


class OwnershipDeltaTest(unittest.TestCase):
    def test_request_destructor_distinct_normal_path_flags_and_sources(self):
        result, code = lookup.query(lookup.SourceGraph(), 'lookup', selector='peace.request_destructor')
        self.assertEqual(code, 0)
        self.assertEqual(result['count'], 1)
        row = result['entries'][0]
        self.assertEqual(row['rva'], '0x598b60')
        self.assertEqual(row['stage'], 'static')
        self.assertEqual(row['ownership']['owned'], [
            '静态正常路径（非运行验证）：embedded offer cleanup 后，EDX bit0=0 preserves caller outer storage。',
            '静态正常路径（非运行验证）：embedded offer cleanup 后，EDX bit0=1 frees engine outer 0x210。'])
        for flag in lookup.FALSE_FLAGS:
            self.assertIs(row[flag], False)
        path = 'work/reports/war-peace-api-20261014-r3/peace/adapter-contract.json'
        refs = {ref['json_pointer']: ref for ref in row['evidence'] if ref['path'] == path}
        self.assertEqual(set(refs), {'/operations/7', '/operations/8'})
        raw = lookup._bounded_read(lookup._source_path(lookup.ROOT, path))
        for ref in refs.values():
            lookup._check_pin(raw, {key: ref[key] for key in ('bytes', 'sha256')})
        source = json.loads(raw)
        original = lookup._pointer(source, '/operations/7')
        clone = lookup._pointer(source, '/operations/8')
        self.assertEqual((original['name'], clone['name']), ('original_dtor0', 'clone_dtor1'))
        self.assertEqual((original['rva'], clone['rva']), ('0x598b60', '0x598b60'))
        self.assertIn('EDX=0', original['args'])
        self.assertIn('EDX=1', clone['args'])
        self.assertEqual(original['owns'], 'destroys embedded graph, preserves caller outer storage')
        self.assertEqual(clone['owns'], 'destroys graph and frees engine outer allocation')


if __name__ == '__main__':
    unittest.main(verbosity=2)
