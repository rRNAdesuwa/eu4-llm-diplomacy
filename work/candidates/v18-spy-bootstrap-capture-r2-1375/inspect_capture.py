"""R2 file-only capture inspection; does not replace the original loader/client."""
import argparse,json
from pathlib import Path
from _frozen import HERE,OLD,b,wire,read,sha
from prepare import check
import real_capture


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid',type=int,required=True);parser.add_argument('--creation',required=True)
    parser.add_argument('--session',required=True);parser.add_argument('--complete',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv);check()
    manifest,manifest_sha=b.verify_build(OLD/'build-final')
    identity=wire.identity(dict(pid=args.pid,creation=args.creation,session=args.session,dll_sha256=manifest['dll_sha256'],manifest_sha256=manifest_sha))
    value=real_capture.inspect(OLD/'build-final',identity,args.complete)
    value['capture_reader_revision']={'name':'v18-spy-bootstrap-capture-r2-1375','source_sha256':sha(read(HERE/'real_capture.py',32768)),
                                    'index_sha256':sha(read(HERE/'candidate-index.json',65536)),
                                    'original_manifest_sha256':manifest_sha,'native_recompiled':False}
    raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode('ascii')
    if args.output:
        with args.output.open('xb')as stream:stream.write(raw)
    else:print(raw.decode('ascii'),end='')
    return 0


if __name__=='__main__':raise SystemExit(main())
