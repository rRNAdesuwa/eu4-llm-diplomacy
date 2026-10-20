from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bridge import diplomacy_session as subject


class FileHashCacheTests(unittest.TestCase):
    def setUp(self):
        subject.clear_file_hash_cache()

    def tearDown(self):
        subject.clear_file_hash_cache()

    @staticmethod
    def _counted_open():
        calls = []
        real_open = Path.open

        def counted(path, *args, **kwargs):
            if args and args[0] == "rb":
                calls.append(path)
            return real_open(path, *args, **kwargs)

        return calls, counted

    def test_stable_file_is_read_once_and_refresh_reads_again(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "stable.bin"
            path.write_bytes(b"stable content")
            calls, counted_open = self._counted_open()
            with patch.object(subject.Path, "open", counted_open):
                first = subject.file_hash(path)
                second = subject.file_hash(path)
                refreshed = subject.file_hash(path, refresh=True)

            expected = hashlib.sha256(b"stable content").hexdigest()
            self.assertEqual(first, expected)
            self.assertEqual(second, expected)
            self.assertEqual(refreshed, expected)
            self.assertEqual(len(calls), 2)

    def test_size_content_and_timestamp_changes_invalidate_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "mutable.bin"
            path.write_bytes(b"first")
            calls, counted_open = self._counted_open()
            with patch.object(subject.Path, "open", counted_open):
                first = subject.file_hash(path)
                path.write_bytes(b"second-content")
                changed_size = subject.file_hash(path)
                timestamp = path.stat().st_mtime_ns + 2_000_000_000
                os.utime(path, ns=(timestamp, timestamp))
                changed_time = subject.file_hash(path)

            self.assertNotEqual(first, changed_size)
            self.assertEqual(changed_size, changed_time)
            self.assertEqual(len(calls), 3)

    def test_replacement_with_same_path_invalidates_by_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = directory / "module.dll"
            replacement = directory / "module.new"
            path.write_bytes(b"old module")
            calls, counted_open = self._counted_open()
            with patch.object(subject.Path, "open", counted_open):
                old_hash = subject.file_hash(path)
                replacement.write_bytes(b"new module")
                os.replace(replacement, path)
                new_hash = subject.file_hash(path)

            self.assertNotEqual(old_hash, new_hash)
            self.assertEqual(len(calls), 2)

    def test_missing_file_does_not_poison_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "appears-later.bin"
            with self.assertRaises(FileNotFoundError):
                subject.file_hash(path)
            path.write_bytes(b"now present")
            self.assertEqual(
                subject.file_hash(path),
                hashlib.sha256(b"now present").hexdigest(),
            )

    def test_metadata_change_after_read_is_reported_and_not_cached(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "racing.bin"
            path.write_bytes(b"race")
            real_metadata = subject._file_hash_metadata
            calls, counted_open = self._counted_open()
            metadata_calls = [0]

            def changing_metadata(current):
                resolved, key = real_metadata(current)
                metadata_calls[0] += 1
                if metadata_calls[0] == 2:
                    key = (*key[:-1], key[-1] + 1)
                return resolved, key

            with patch.object(subject.Path, "open", counted_open), \
                    patch.object(subject, "_file_hash_metadata", changing_metadata):
                with self.assertRaisesRegex(RuntimeError, "FILE_CHANGED_DURING_HASH"):
                    subject.file_hash(path)
                self.assertEqual(subject.file_hash(path), hashlib.sha256(b"race").hexdigest())

            self.assertEqual(len(calls), 2)

    def test_cache_is_bounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = []
            for index in range(subject.FILE_HASH_CACHE_LIMIT + 1):
                path = Path(temporary) / f"file-{index}.bin"
                path.write_bytes(str(index).encode("ascii"))
                paths.append(path)
            for path in paths:
                subject.file_hash(path)

            self.assertEqual(len(subject._FILE_HASH_CACHE), subject.FILE_HASH_CACHE_LIMIT)
            self.assertNotIn(subject._file_hash_metadata(paths[0])[1], subject._FILE_HASH_CACHE)
            self.assertIn(subject._file_hash_metadata(paths[-1])[1], subject._FILE_HASH_CACHE)


if __name__ == "__main__":
    unittest.main()
