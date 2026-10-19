"""Own short-lived Python children only; never opens or instruments EU4."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('entry_probe_job_tree', HERE/'job_tree.py')
job = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job)


class JobTreeTests(unittest.TestCase):
    def run_child(self, code, **options):
        temp = tempfile.TemporaryDirectory()
        try:
            at = Path(temp.name)
            return job.run_cli_tree([sys.executable, '-B', '-c', code], HERE,
                at/'stdout.txt', at/'stderr.txt', **options)
        finally:
            # Windows can retain a terminated child's file handle briefly.
            # This is filesystem cleanup, separate from the job's PID checks.
            for attempt in range(11):
                try:
                    temp.cleanup()
                    break
                except PermissionError:
                    if attempt == 10:
                        raise
                    time.sleep(0.05)

    def test_normal_exact_child_collected(self):
        result = self.run_child("print('local child only')")
        self.assertEqual(result['exit_code'], 0)
        self.assertIsNone(result['error'])
        self.assertEqual(result['job_active_processes_final'], 0)
        self.assertTrue(1 <= result['job_total_processes'] <= 8)
        self.assertTrue(result['direct_child_collected'])
        self.assertFalse(result['existing_target_game_assigned_to_job'])

    def test_timeout_collects_only_owned_job(self):
        result = self.run_child('import time;time.sleep(10)', timeout_seconds=1)
        self.assertEqual(result['error']['type'], 'TimeoutError')
        self.assertIsNotNone(result['exit_code'])
        self.assertEqual(result['job_active_processes_final'], 0)
        self.assertFalse(result['target_cleanup_proven_by_job'])

    def test_malformed_bound_refuses_before_child(self):
        for value in (True, 0, 46):
            with self.subTest(value=value), self.assertRaises(ValueError):
                job.run_cli_tree(['not started'], HERE, 'unused.out', 'unused.err', timeout_seconds=value)

    def test_completed_parent_cannot_leave_owned_descendant(self):
        code = "import subprocess,sys;subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(10)'])"
        result = self.run_child(code)
        self.assertEqual(result['exit_code'], 0)
        self.assertEqual(result['job_active_processes_final'], 0)
        self.assertTrue(result['completed_command_descendants_terminated'])
        self.assertTrue(2 <= result['job_total_processes'] <= 8)

    def test_fast_oversized_output_cannot_return_success(self):
        result = self.run_child("import sys;sys.stdout.buffer.write(b'x'*(2*1024*1024+1))")
        self.assertIsNotNone(result['error'])
        self.assertIn('output bound', result['error']['message'])
        self.assertEqual(result['job_active_processes_final'], 0)
        self.assertTrue(result['output_writer_may_overshoot_before_refusal'])


if __name__ == '__main__':
    unittest.main()
