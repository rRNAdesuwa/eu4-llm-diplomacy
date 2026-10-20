"""CreateNew exact version/session adaptation of the reviewed v14 prefix helper."""
from pathlib import Path
import difflib
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'work/snapshot_v14_directional_preflight_prefix_1375.py'
NEW = ROOT / 'work/snapshot_v17_directional_preflight_prefix_1375.py'
OLD_SHA = '7f7e455f124eb4f9c42742ceef5bc88b6d585e041ee0e59a2bdac46b2d2dc0de'
CHANGES = {
    'v14': 'v17',
    "18356, '01dd56aa6f724ea8', '0x221c8dac040'": "22784, '01dd56bf28902f93', '0x21e8dbe8060'",
    'directional-health-after-command-{PID}.json': 'stage-command-status-{PID}.json',
    'aa09084d3d1d7c9adff164b67356d72e2c511b519e79b382e7bc54a80c96ec75': 'b7cf7bb7b31cddf621729e0d541404d80bdb155c6f804082e2a25f651c97067d',
    'ABFB2E343F7E7332EFA96C45B1DD2B89C00AC2B4085CBD9FC32E8F90DB299296': 'D8B962B19D489FD366F346416BB72A8958F3DC53B504A29EC835D3B99CAFA1EE',
}

def main():
    with OLD.open('rb') as stream:
        raw = stream.read(16385)
    if len(raw) > 16384 or hashlib.sha256(raw).hexdigest() != OLD_SHA:
        raise ValueError('Frozen prefix helper changed')
    text = raw.decode()
    counts = {}
    for before, after in CHANGES.items():
        counts[before] = text.count(before)
        if not counts[before] or (before != 'v14' and counts[before] != 1):
            raise ValueError('Unexpected exact adaptation token: ' + before)
        text = text.replace(before, after)
    result = text.encode()
    compile(result, str(NEW), 'exec')
    delta = ''.join(difflib.unified_diff(raw.decode().splitlines(True), text.splitlines(True))).encode()
    report = {'purpose': 'root_v17_exact_preoperation_prefix_helper_adaptation',
              'predecessor_sha256': OLD_SHA, 'source_sha256': hashlib.sha256(result).hexdigest(),
              'diff_sha256': hashlib.sha256(delta).hexdigest(), 'replacement_counts': counts,
              'identity': {'pid': 22784, 'creation': '01dd56bf28902f93', 'world': '0x21e8dbe8060'},
              'files_only': True, 'snapshot_performed': False, 'game_accessed': False}
    outputs = ((NEW, result), (ROOT/'work/review-results/root-v17-prefix-helper-adaptation-20261008a.diff', delta),
               (ROOT/'work/review-results/root-v17-prefix-helper-adaptation-20261008a.json', (json.dumps(report, indent=2)+'\n').encode()))
    if any(path.exists() for path, _ in outputs):
        raise ValueError('Never overwrite helper adaptation')
    for path, data in outputs:
        with path.open('xb') as stream:
            stream.write(data)
    print(json.dumps(report))

if __name__ == '__main__':
    main()
