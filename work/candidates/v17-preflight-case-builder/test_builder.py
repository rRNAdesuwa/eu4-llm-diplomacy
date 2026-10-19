"""Construction-only fixtures; no phase execution or reviewer invocation."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import build_case as b


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in b.decode(b.bounded(b.HERE / 'source-pins.json')):
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b.bounded(b.ROOT / name))
        self.config = b.template(); self.c = self.config
        self.c['prefix_directory'] = b.RUNTIME + 'directional-preflight-prefix-101'
        self.c['output_directory'] = b.RUNTIME + 'constructed-101'
        self.c['scope'] = dict(pid=101, creation='01dd000000000001', world_cookie='0x100000', window_thread=202,
            initial_raw_date=56456976, dll_sha256='d'*64, manifest_sha256='b'*64, bridge_start_rva=28832,
            prefix_bytes=1, prefix_sha256='c'*64, preflight_case=self.c['output_directory']+'/preflight-case.json',
            preflight_summary=self.c['output_directory']+'/preflight-summary.json')
        for key in b.FILES:
            value = b'{"event":"research_frame","last_sequence":0}\n' if key == 'research-1375.jsonl' else b'fixed\n'
            self.add(key, self.c['prefix_directory']+'/'+key, value)
        log = self.c['inputs']['research-1375.jsonl']; self.c['scope'].update(prefix_bytes=log['size_bytes'], prefix_sha256=log['sha256'])
        build = {'purpose':'restricted_pair_lab_1375_v17','protocol_version':'EU4LAB/3','dll_sha256':'D'*64,'bridge_start_export_rva':28832}
        self.add('build', b.RUNTIME+'build.json', b.wire(build)); self.c['scope']['manifest_sha256'] = self.c['inputs']['build']['sha256']
        state = dict(game_pointer='0x100000',current_raw_date=56456976,player={},actor='FRA',target='ENG',actor_diplomats={'entry_count':3},relation_cooldown={})
        d = dict(read_only=True,source={'pid':101,'process_creation_filetime':int('01dd000000000001',16),'held_identity_verified_before_and_after':True},
                 state=state,capture_started_at_utc='2026-10-08T00:00:00+00:00',captured_at_utc='2026-10-08T00:00:01+00:00')
        self.add('before',b.RUNTIME+'before.json',b.wire(d))
        d = deepcopy(d);d['capture_started_at_utc']='2026-10-08T00:00:02+00:00';d['captured_at_utc']='2026-10-08T00:00:03+00:00'
        self.add('after',b.RUNTIME+'after.json',b.wire(d))
        self.add('loader',b.RUNTIME+'loader.json',b.wire({'unreviewed_synthetic_loader':True}))
        status = {'report':{'pid':101,'creation':'01dd000000000001','last_sequence':0,'log_sha256':log['sha256']}}
        self.add('status',b.RUNTIME+'status.json',b.wire(status))
        snapshot = {'pid':101,'creation':'01dd000000000001','prefix_sha256':log['sha256'],'prefix_bytes':log['size_bytes'],
                    'source_process_exit_observed':False,'whole_active_log_unchanged_verified':False,
                    'snapshot_file_sha256':{k:self.c['inputs'][k]['sha256'] for k in b.FILES},'status_sha256':self.c['inputs']['status']['sha256']}
        self.add('snapshot',b.RUNTIME+'snapshot.json',b.wire(snapshot))
        for key in b.CAPTURES:self.add(key,b.RUNTIME+key+'.json',b.wire({'capture':key}),captures=True)

    def add(self,key,name,raw,captures=False):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        self.c['captures' if captures else 'inputs'][key]={'path':name,'size_bytes':len(raw),'sha256':b.sha(raw)}

    def test_construct_and_createnew_no_review_or_summary(self):
        packet=b.construct(self.c,self.root)
        self.assertFalse(packet['construction']['formal_review_performed']);self.assertFalse(packet['construction']['finalized'])
        self.assertEqual(set(packet['case']['inputs']),set(b.FILES)|{'before','after','loader','status'})
        out=b.publish(self.c,self.root)
        self.assertTrue((out/'preflight-case.json').is_file());self.assertFalse((out/'preflight-summary.json').exists())
        with self.assertRaises(FileExistsError):b.publish(self.c,self.root)

    def test_missing_after_never_creates_case(self):
        (self.root/self.c['inputs']['after']['path']).unlink()
        with self.assertRaises(FileNotFoundError):b.publish(self.c,self.root)
        self.assertFalse((self.root/self.c['output_directory']).exists())

    def test_same_file_cannot_supply_before_and_after(self):
        self.c['inputs']['after']=deepcopy(self.c['inputs']['before'])
        with self.assertRaisesRegex(ValueError,'independent files'):b.construct(self.c,self.root)

    def test_status_cannot_replace_full_diagnostic(self):
        self.c['inputs']['after']=deepcopy(self.c['inputs']['status'])
        with self.assertRaises((ValueError,KeyError)):b.construct(self.c,self.root)

    def test_post_fixture_changed_diplomat_count_rejected(self):
        path=self.c['inputs']['after']['path'];doc=b.decode(b.bounded(self.root/path))
        doc['state']['actor_diplomats']['entry_count']=103;self.add('after',path,b.wire(doc))
        with self.assertRaisesRegex(ValueError,'Selected diagnostic'):b.construct(self.c,self.root)

    def test_scope_types_and_growing_session_path_rejected(self):
        saved=deepcopy(self.c)
        for key,value in (('pid',True),('window_thread',202.0),('creation','01DD000000000001')):
            self.c=deepcopy(saved);self.c['scope'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):b.construct(self.c,self.root)
        self.c=deepcopy(saved);self.c['prefix_directory']=b.RUNTIME+'session-101-01dd000000000001'
        with self.assertRaises(ValueError):b.construct(self.c,self.root)

    def test_tampered_input_and_extra_prefix_file_rejected(self):
        path=self.root/self.c['inputs']['loader']['path'];old=path.read_bytes();path.write_bytes(old+b' ')
        with self.assertRaisesRegex(ValueError,'bytes/hash'):b.construct(self.c,self.root)
        path.write_bytes(old);(self.root/self.c['prefix_directory']/'00000000000000000001.claim').write_bytes(b'claim')
        with self.assertRaisesRegex(ValueError,'inventory'):b.construct(self.c,self.root)

    def test_duplicate_json_and_hard_read_budget_rejected(self):
        with self.assertRaisesRegex(ValueError,'Duplicate'):b.decode(b'{"a":1,"a":2}')
        path=self.root/'too-large';path.write_bytes(b'x'*17)
        with self.assertRaisesRegex(ValueError,'Read limit'):b.bounded(path,16)

    def test_template_missing_explicit_fields_fails_closed(self):
        with self.assertRaises(ValueError):b.construct(b.template(),self.root)

    def test_copied_baseline_is_not_a_second_chronological_observation(self):
        raw=b.bounded(self.root/self.c['inputs']['before']['path'])
        self.add('after',self.c['inputs']['after']['path'],raw)
        with self.assertRaisesRegex(ValueError,'chronological'):b.construct(self.c,self.root)


if __name__=='__main__':unittest.main()
