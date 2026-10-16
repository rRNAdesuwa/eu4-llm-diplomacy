"""Only tempfile/fake-kernel publisher tests; never real process access."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import client
import test_capture as fixture
import wire


class Kernel:
    def __init__(self):self.closed=0;self.wait_result=0x102
    def WaitForSingleObject(self,*args):return self.wait_result
    def CloseHandle(self,*args):self.closed+=1;return True


class Publication(unittest.TestCase):
    def status(self):
        rows=fixture.synthetic();raw,out,i,c=fixture.envelope([rows[0]],False)
        result=fixture.r.validate_stream(raw,out,i,c,False);result.update(identity=i,source_manifest_verified=True)
        return result,i

    def test_publish_exactly_once_repeated_intent_rejected(self):
        status,i=self.status();kernel=Kernel()
        with tempfile.TemporaryDirectory() as td:
            directory=Path(td);session=wire.session_path(directory,i);session.mkdir()
            with patch.object(client,'process_guard',return_value=(kernel,1)),patch.object(client,'now_ms',return_value=10000),\
                 patch.object(client.real_capture,'inspect',return_value=status),patch.object(client.b,'verify_build',return_value=({},'')):
                result=client.publish(directory,i,'lifecycle');self.assertTrue(result['request_written'])
                first=(session/'1.request').read_bytes();self.assertEqual(wire.p.decode(first)['sequence'],1)
                with self.assertRaises(ValueError):client.publish(directory,i,'lifecycle')
                self.assertEqual((session/'1.request').read_bytes(),first);self.assertEqual(kernel.closed,2)

    def test_failure_after_intent_preserves_no_retry_and_no_request(self):
        status,i=self.status()
        for failure in ('recheck','fsync','expired','exit'):
            kernel=Kernel()
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as td:
                directory=Path(td);session=wire.session_path(directory,i);session.mkdir()
                reads=[status,ValueError('Changed private source')] if failure=='recheck' else [status,status]
                clock=[10000,10000,10000,70000] if failure=='expired' else [10000]*8
                with patch.object(client,'process_guard',return_value=(kernel,1)),patch.object(client,'now_ms',side_effect=clock),\
                     patch.object(client.real_capture,'inspect',side_effect=reads),patch.object(client.b,'verify_build',return_value=({},'')):
                    if failure=='exit':kernel.wait_result=0
                    if failure=='fsync':
                        with patch.object(client.loader.os,'fsync',side_effect=OSError('flush failure')):
                            with self.assertRaises(OSError):client.publish(directory,i,'lifecycle')
                    else:
                        with self.assertRaises(ValueError):client.publish(directory,i,'lifecycle')
                self.assertTrue((session/'1.publisher-intent.json').exists());self.assertFalse((session/'1.request').exists())
                self.assertEqual(kernel.closed,1)

    def test_external_existing_request_never_overwritten(self):
        status,i=self.status();kernel=Kernel()
        with tempfile.TemporaryDirectory() as td:
            directory=Path(td);session=wire.session_path(directory,i);session.mkdir();target=session/'1.request'
            target.write_bytes(b'preexisting')
            with patch.object(client,'process_guard',return_value=(kernel,1)),patch.object(client,'now_ms',return_value=10000),\
                 patch.object(client.real_capture,'inspect',return_value=status):
                with self.assertRaises(ValueError):client.publish(directory,i,'lifecycle')
            self.assertEqual(target.read_bytes(),b'preexisting');self.assertFalse((session/'1.publisher-intent.json').exists())


if __name__=='__main__':unittest.main()
