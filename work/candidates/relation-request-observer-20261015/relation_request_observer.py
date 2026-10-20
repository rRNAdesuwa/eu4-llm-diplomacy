"""Unsealed candidate: original-request relation observation, never dispatch.

Only this new adapter may create request baselines. The current-only relation
service's random nonce/capture is deliberately not imported or re-labelled.
All source guards here detect change relative to frozen dependencies and the
capture/baseline; candidate self-pins become authoritative only after review.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import struct
import time

from bridge.diplomacy_effect_observer import (
    RuntimeCapture, BudgetReader, HeldRPMPort, LIMITS, roots, country,
    full_handle, ptr, pins as effect_pins)
from bridge.diplomacy_live_observer import (
    LiveDiplomacyObserver, live_source_pins, live_catalog, write_journal, ERRORS)
from bridge.diplomacy_reply_observer import reply_source_pins
from bridge.knowledge_effect_reader_v2 import verify_manifest as knowledge_pins
from bridge.relation_effect_reader import (
    ACTIONS, PROFILES, read_relation_pair, evaluate_relation_effect,
    _capture as replay_relation_capture, verify_manifest as reader_pins)
from bridge.tag_command_backend import (
    ROOT, GAME_SHA, DEFAULT_MANIFEST, boot, decode, digest, read, require,
    validate_identity, validate_command)
from bridge.tag_command_audit import recorded_snapshot

CANDIDATE = Path(__file__).resolve().parent
NATIVE_MANIFEST_SHA = 'd4b3069cfac70cf9ff8e1270733ad64592c3d545a6d005fd0ed8b26c6070728a'
CAPTURE_SCHEMA = 'EU4DIPLOMACY-RELATION-REQUEST-CAPTURE/1'
BASELINE_SCHEMA = 'EU4DIPLOMACY-RELATION-REQUEST-BASELINE/1'
PURPOSE = 'Original installed TAG session; request observer, not a current-query nonce'
BASELINE_KIND = 'fresh_absent_relation_before_original_request_publication'


def source_pins():
    """Frozen dependency verification plus unsealed candidate change detection."""
    require(digest(read(DEFAULT_MANIFEST, 1024*1024)) == NATIVE_MANIFEST_SHA,
            'Default native manifest changed')
    result = {}
    for graph in (live_source_pins(), effect_pins(), reply_source_pins(),
                  knowledge_pins(), reader_pins()):
        for name, pin in graph.items():
            require(name not in result or result[name] == pin, 'Conflicting dependency pin: '+name)
            result[name] = pin
    for path in (CANDIDATE/'relation_request_observer.py', CANDIDATE/'test_relation_request_observer.py'):
        raw = read(path, 1024*1024)
        result[path.relative_to(ROOT).as_posix()] = dict(bytes=len(raw), sha256=digest(raw))
    return result


def installed_session(backend, identity, *, ready=False):
    """File-only proof of the original installation, not proof of a live hook.

    A made-up nonce cannot pass the retained bootstrap, installation and audit
    identity checks. No installer, runtime check, publisher or loader is called.
    """
    identity = validate_identity(identity)
    require(Path(backend.manifest_path).resolve() == DEFAULT_MANIFEST.resolve()
            and Path(backend.build).resolve() == DEFAULT_MANIFEST.parent.resolve(),
            'Only the frozen default TAG host is supported')
    manifest = backend.verify()
    require(backend.manifest_sha == NATIVE_MANIFEST_SHA == identity['manifest_sha256']
            and manifest == backend.manifest and len(manifest['source_pins']) == 44,
            'Default native metadata or 44-pin graph changed')
    directory = backend.session(identity)
    names = [backend.build/f'session-{identity["pid"]}-{identity["creation"]}.json',
             backend.build/f'loader-intent-{identity["pid"]}-{identity["creation"]}.json',
             backend.build/f'bootstrap-{identity["pid"]}-{identity["creation"]}.request']
    blobs = [read(path, 131072) for path in names]
    report, intent = decode(blobs[0]), decode(blobs[1])
    require(validate_identity(report['identity']) == identity
            and validate_identity(intent['identity']) == identity
            and report['experimental'] is True
            and intent['outcome'] == 'unknown_until_loader_returns',
            'Installed session identity differs')
    installation = report['installation']
    require(type(installation['pid']) is int and installation['pid'] == identity['pid']
            and Path(installation['dll']).resolve() == (backend.build/manifest['DLL']).resolve()
            and installation['bridge_thread_exit_status'] == '0x0'
            and installation['test_save_acknowledged'] is True
            and installation['dll_unloaded'] is False,
            'Successful original installation report unavailable')
    require(blobs[2] == boot(identity, purpose=backend.purpose), 'Original bootstrap packet differs')
    snapshot = recorded_snapshot(backend.manifest_path, identity)
    require(snapshot.directory.resolve() == directory.resolve() and snapshot.raw == snapshot.complete,
            'Installed session path or complete audit unavailable')
    installed = [row for row in snapshot.rows if row['event'] == 'hook_installed']
    require(len(installed) == 1 and installed[0]['sequence'] == 0
            and snapshot.rows[0]['sequence'] == 0 and snapshot.summary['hook_installed'] is True,
            'Unique installed-session audit unavailable')
    owner = snapshot.summary['owner_thread']
    require(type(owner) is int and 1 <= owner <= 0xffffffff, 'Installed audit owner thread exceeds DWORD')
    for row in snapshot.rows:
        require(all(type(row[k]) is type(v) and row[k] == v for k,v in identity.items())
                and type(row['thread']) is int and 1 <= row['thread'] <= 0xffffffff
                and (row['sequence'] == 0 or row['thread'] == owner)
                and type(row['owner_thread']) is int and 1 <= row['owner_thread'] <= 0xffffffff
                and row['owner_thread'] == owner,
                'Installed-session audit identity/thread encoding differs')
    require(not ready or snapshot.summary['terminal'] is False, 'Installed host is terminal')
    proof = dict(identity=deepcopy(identity), session_directory=str(directory),
                 files={str(path): dict(bytes=len(raw), sha256=digest(raw))
                        for path,raw in zip(names,blobs)},
                 installation_record_verified=True, live_hook_proven=False)
    return proof, snapshot


def checked_capture(capture, command, identity, installation):
    """Replay raw typed indexes/objects before using a persisted capture."""
    require(capture['schema'] == CAPTURE_SCHEMA and capture['command'] == command
            and validate_identity(capture['identity']) == identity
            and capture['identity_purpose'] == PURPOSE
            and capture['installation'] == installation
            and capture['game_sha256'] == GAME_SHA,
            'Request capture identity, command or installation differs')
    require('native_session_installed' not in capture
            and type(capture['current_tag_host_observed']) is bool,
            'Current-only nonce capture cannot be used as a request capture')
    state = capture['state']
    require(validate_identity(state['identity']) == identity
            and 'identity_purpose' not in state and 'native_session_installed' not in state,
            'Inner relation capture is not original-session evidence')
    selected = replay_relation_capture(state, command['action'])
    pair = selected['pair']
    require((pair['actor_tag'], pair['target_tag']) == (command['actor'], command['target']),
            'Relation command direction differs')
    for role in ('actor','target'):
        value = selected[role]
        expected = int(pair[role+'_handle'], 16)
        slot, tag = full_handle(expected, selected['roots']['count'], tag=command[role])
        require(value['handle'] == hex(expected) and value['tag'] == tag and value['slot'] == slot,
                'Relation full country identity differs')
    obj = selected['object']
    if obj is not None:
        forward = (obj['first_handle'], obj['second_handle']) == (pair['actor_handle'], pair['target_handle'])
        require(obj['requested_direction_matches'] is (PROFILES[command['action']]['symmetric'] or forward),
                'Relation direction projection differs')
    return state


class RelationRequestCapture(RuntimeCapture):
    """Fresh true-session adapter on the frozen held QUERY/VM_READ port."""
    def __init__(self, identity, backend=None, *, allow_tag_host=False):
        super().__init__(identity, backend)
        require(type(allow_tag_host) is bool, 'Explicit tag-host option must be boolean')
        self.allow_tag_host = allow_tag_host

    def __enter__(self):
        self.request_pins = source_pins()
        self.installation, _ = installed_session(self.backend, self.identity)
        return super().__enter__()

    def capture_relation(self, command, binding=None):
        command = validate_command(command, ACTIONS)
        started = time.perf_counter()
        require(source_pins() == self.request_pins, 'Candidate sources changed before capture')
        r = BudgetReader(HeldRPMPort(self.held))
        canonical = self.held.injector._canonical
        research = [(b,p) for b,p in self.modules if Path(p).name.lower().startswith(
            ('eu4_bridge_', 'eu4_pair_', 'eu4_spy_', 'eu4_tag_command_', 'tag_diplomacy'))]
        expected = self.backend.build/self.backend.manifest['DLL']
        require(not research or (self.allow_tag_host and len(research) == 1
                and canonical(research[0][1]) == canonical(expected)), 'Unexpected research module')
        if research:
            header = self.runtime.readonly.pe_header(r.read(ptr(research[0][0]), 8192))
            require(header['machine'] == 0x8664 and header['timestamp'] == self.backend.manifest['PE_timestamp']
                    and header['size_of_image'] == self.backend.manifest['SizeOfImage'],
                    'Loaded default TAG host header differs')
        require(binding is not None or len(research) == 1,
                'New request baseline requires the authenticated installed TAG host to be present')
        root = roots(r, self.base)
        require(root['manual_pause'] == 1, 'Manual pause required')
        # Discover both TAGs afresh, even with a binding: never retain pointers
        # from a prior capture and never trust only the low TAG bits.
        table = r.read(int(root['array'],16), root['count']*8)
        selected = {}
        for address, in struct.iter_unpack('<Q', table):
            if not address:
                continue
            value = r.q(ptr(address)+0x20)
            tag_bytes = (value & 0xffffff).to_bytes(3,'little')
            for tag in (command['actor'], command['target']):
                if tag_bytes == tag.encode('ascii'):
                    require(tag not in selected, 'Duplicate selected TAG')
                    full_handle(value, root['count'], tag=tag)
                    selected[tag] = country(r, self.base, root, value, tag)
                    require(int(selected[tag]['address'],16) == address, 'Country table slot differs')
        require(set(selected) == {command['actor'],command['target']}, 'Selected country unavailable')
        handles = tuple(int(selected[command[role]]['handle'],16) for role in ('actor','target'))
        if binding is not None:
            require(binding['event'] == 'pair_bound' and binding['no_send'] is False
                    and all(type(binding[k]) is type(v) and binding[k] == v for k,v in self.identity.items()),
                    'Original binding identity differs')
            require(all(type(binding[role+'_handle']) is int and binding[role+'_handle'] == value
                        for role,value in zip(('actor','target'), handles)), 'Original full binding differs')
        state = read_relation_pair(r, self.base, command['action'], *handles, self.identity)
        require(state.get('two_pass_equal') is True and len(state['passes']) == 2
                and all(item['roots'] == root for item in state['passes']), 'Relation two-pass world proof unavailable')
        require(roots(r, self.base) == root and r.read(int(root['array'],16),root['count']*8) == table,
                'Country table/world guards changed')
        self.held.identity_check()
        require(self.held.modules() == self.modules and effect_pins() == self.initial_pins,
                'Process modules or frozen sources changed')
        proof, _ = installed_session(self.backend, self.identity)
        require(proof == self.installation and source_pins() == self.request_pins,
                'Installation or candidate sources changed during capture')
        value = dict(schema=CAPTURE_SCHEMA, identity=deepcopy(self.identity), command=command,
            identity_purpose=PURPOSE, installation=proof, current_tag_host_observed=bool(research),
            state=state, game_sha256=GAME_SHA, captured_utc=datetime.now(timezone.utc).isoformat(),
            source_pins=self.request_pins, duration_ms=round((time.perf_counter()-started)*1000,3),
            rpm_budget=dict(calls=r.calls, bytes=r.bytes, largest_read=r.largest, limits=dict(LIMITS)),
            native_calls=0, memory_written=False, requests_published=0, saves_written=0,
            atomic_snapshot_proven=False, world_epoch_proven=False, exclusive_causality_proven=False)
        checked_capture(value, command, self.identity, proof)
        return value


def unknown_effect(reason, exc=None):
    value = dict(schema='EU4DIPLOMACY-RELATION-EFFECT/1', status='unknown',
        selected_effect_verified=False, reason=reason, automatic_command_retry=False,
        AI_acceptance_verified=False, exact_external_request_id_causality_verified=False,
        exclusive_causality_proven=False, world_epoch_proven=False, atomic_snapshot_proven=False,
        global_membership_verified=False, saved_state_verified=False, cold_reload_verified=False)
    if exc is not None:
        value['failure'] = dict(type=type(exc).__name__, message=str(exc))
    return value


class RelationRequestObserver(LiveDiplomacyObserver):
    """Three candidate profiles; all fifteen frozen profiles still delegate."""
    def __init__(self, identity, *, relation_capture_factory=RelationRequestCapture, **kwargs):
        super().__init__(identity, **kwargs)
        require(type(self.allow_tag_host) is bool, 'Explicit tag-host option must be boolean')
        self.relation_capture_factory = relation_capture_factory

    def _publication_paths(self, command):
        session = self.backend.session(self.identity)
        return self.backend.key_path(session, command['request_id']), session/'publisher.lock'

    def prepare(self, command, *, legacy_probe=None):
        command = validate_command(command, self.backend.actions)
        if command['action'] not in ACTIONS:
            return super().prepare(command, legacy_probe=legacy_probe)
        require(legacy_probe is None, 'Relation preparation requires a fresh true-session capture')
        initial = source_pins()
        proof, audit = installed_session(self.backend, self.identity, ready=True)
        directory = self.directory(command['request_id'])
        path = directory/'relation-request-baseline.json'
        commit_path = directory/'relation-request-baseline-commit.json'
        require(not path.exists() and not commit_path.exists(),
                'Original relation baseline already exists; never replace it')
        intent, lock = self._publication_paths(command)
        require(not intent.exists() and not lock.exists(), 'Request reserved or publisher locked before baseline')
        with self.relation_capture_factory(self.identity, self.backend, allow_tag_host=self.allow_tag_host) as reader:
            capture = reader.capture_relation(command)
        state = checked_capture(capture, command, self.identity, proof)
        require(capture['source_pins'] == initial and capture['current_tag_host_observed'] is True,
                'Baseline source/installed host evidence differs')
        require(state['status'] == 'pair_absent_observed' and state['current_relation_observed'] is False,
                'Fresh absent exact relation required before original dispatch')
        require(not intent.exists() and not lock.exists(), 'Publication started during baseline capture')
        final_proof, final_audit = installed_session(self.backend, self.identity, ready=True)
        require(final_proof == proof and final_audit.raw == audit.raw and source_pins() == initial,
                'Installation, audit or sources changed during baseline')
        value = dict(schema=BASELINE_SCHEMA, identity=deepcopy(self.identity), command=command,
            capture=capture, installation=proof, source_pins=initial,
            provenance=dict(kind=BASELINE_KIND, intent_path=str(intent), publisher_lock_path=str(lock),
                intent_absent_before=True, intent_absent_after=True,
                publisher_lock_absent_before=True, publisher_lock_absent_after=True,
                audit_sha256_before=digest(audit.raw), audit_sha256_after=digest(final_audit.raw),
                atomic_publication_lock_held=False, exclusive_causality_proven=False),
            recorded_utc=datetime.now(timezone.utc).isoformat(), candidate_unsealed=True)
        directory.mkdir(parents=True, exist_ok=True)
        require(not intent.exists() and not lock.exists(), 'Publication started before baseline write')
        record = write_journal(path, value)
        # The final prewrite check is not an atomic publisher lock. A separate
        # exclusive commit makes a late-write race leave an unusable baseline.
        require(not intent.exists() and not lock.exists(), 'Publication started during baseline write')
        committed_proof, committed_audit = installed_session(self.backend, self.identity, ready=True)
        require(committed_proof == proof and committed_audit.raw == audit.raw and source_pins() == initial,
                'Installation, audit or sources changed during baseline write')
        require(not intent.exists() and not lock.exists(), 'Publication started before baseline commit')
        commit = dict(schema='EU4DIPLOMACY-RELATION-REQUEST-BASELINE-COMMIT/1',
            identity=deepcopy(self.identity), command=command, baseline_path=str(path),
            baseline_sha256=record['sha256'], source_pins=initial,
            intent_absent_after_baseline_write=True, publisher_lock_absent_after_baseline_write=True,
            audit_sha256_after_baseline_write=digest(committed_audit.raw),
            atomic_publication_lock_held=False, candidate_unsealed=True)
        committed = write_journal(commit_path, commit)
        return dict(request_id=command['request_id'], baseline=record, baseline_commit=committed,
                    pair_status=state['status'],
                    native_calls=0, requests_published=0, memory_written=False, saves_written=0,
                    automatic_command_retry=False, candidate_unsealed=True)

    def observe(self, request_id, *, record=True):
        # Validate ID even if the audit is absent; invalid paths never reach disk.
        directory = self.directory(request_id)
        require(type(record) is bool, 'Record option must be boolean')
        result = dict(schema='EU4DIPLOMACY-RELATION-REQUEST-OBSERVATION/1', request_id=request_id,
            identity=deepcopy(self.identity), request_state='unknown', transport_state='unknown',
            completion_state='evidence_insufficient', native_receipt=None, relation=None,
            effect=unknown_effect('Original relation evidence not yet validated'),
            AI_acceptance_verified=False, persistence_verified=False, native_calls=0,
            requests_published=0, memory_written=False, saves_written=0, automatic_command_retry=False,
            candidate_unsealed=True)
        try:
            # Preserve a file-proven transport receipt even if the new source
            # graph later fails. Never use that receipt as effect proof alone.
            audit = recorded_snapshot(self.backend.manifest_path, self.identity)
            require(audit.raw == audit.complete, 'Complete original audit unavailable')
            status = audit.status(request_id)
            command = status['command']
            result.update(command=command, native_receipt=deepcopy(status),
                          transport_state=status['state'], audit_sha256=status['audit_sha256'])
            initial = source_pins()
            if command['action'] not in ACTIONS:
                return super().observe(request_id, record=record)
            proof, installed_audit = installed_session(self.backend, self.identity)
            require(installed_audit.raw == audit.raw and installed_audit.status(request_id) == status,
                    'Original installed-session audit changed before observation')
            require(status['state'] == 'dispatched' and status['binding'] is not None,
                    'Original relation request has no proven dispatch; observation never authorizes retry')
            path = directory/'relation-request-baseline.json'
            raw = read(path, 2*1024*1024)
            baseline = decode(raw)
            commit_path = directory/'relation-request-baseline-commit.json'
            commit_raw = read(commit_path, 2*1024*1024)
            commit = decode(commit_raw)
            require(commit['schema'] == 'EU4DIPLOMACY-RELATION-REQUEST-BASELINE-COMMIT/1'
                    and validate_identity(commit['identity']) == self.identity and commit['command'] == command
                    and commit['baseline_path'] == str(path) and commit['baseline_sha256'] == digest(raw)
                    and commit['source_pins'] == initial and commit['atomic_publication_lock_held'] is False
                    and commit['intent_absent_after_baseline_write'] is True
                    and commit['publisher_lock_absent_after_baseline_write'] is True,
                    'Original baseline postwrite commit unavailable or changed')
            require(baseline['schema'] == BASELINE_SCHEMA
                    and validate_identity(baseline['identity']) == self.identity
                    and baseline['command'] == command and baseline['installation'] == proof
                    and baseline['source_pins'] == initial,
                    'Original relation baseline identity/source/installation differs')
            provenance = baseline['provenance']
            intent, lock = self._publication_paths(command)
            require(provenance['kind'] == BASELINE_KIND and provenance['intent_path'] == str(intent)
                    and provenance['publisher_lock_path'] == str(lock)
                    and all(provenance[k] is True for k in ('intent_absent_before','intent_absent_after',
                        'publisher_lock_absent_before','publisher_lock_absent_after'))
                    and provenance['atomic_publication_lock_held'] is False
                    and provenance['audit_sha256_before'] == provenance['audit_sha256_after']
                    == commit['audit_sha256_after_baseline_write'],
                    'Original relation baseline publication guards unavailable')
            # Baseline audit is a strict prefix of the original complete audit.
            # This ties before-publication timing to retained bytes, not a label.
            prefix_hash, prefix_length, prefix_rows = hashlib.sha256(), 0, []
            baseline_audit_found = False
            for line in audit.complete.splitlines(keepends=True):
                prefix_hash.update(line)
                prefix_length += len(line)
                prefix_rows.append(decode(line))
                if prefix_hash.hexdigest() == provenance['audit_sha256_before']:
                    baseline_audit_found = True
                    break
            require(baseline_audit_found and prefix_length < len(audit.complete)
                    and not any(row['sequence'] == status['sequence'] for row in prefix_rows),
                    'Baseline installed audit is not a strict original-audit prefix')
            before = checked_capture(baseline['capture'], command, self.identity, proof)
            require(baseline['capture']['source_pins'] == initial
                    and baseline['capture']['current_tag_host_observed'] is True
                    and before['status'] == 'pair_absent_observed' and before['current_relation_observed'] is False,
                    'Baseline is not a prepublication absent relation')
            # Validate the complete receipt against the baseline before opening
            # a process. Identical before/after is valid evidence of no change.
            receipt_check = evaluate_relation_effect(command['action'], before, before, status)
            require(receipt_check['status'] == 'not_observed', 'Original dispatch receipt/binding incomplete')
            with self.relation_capture_factory(self.identity, self.backend, allow_tag_host=self.allow_tag_host) as reader:
                capture = reader.capture_relation(command, status['binding'])
            after = checked_capture(capture, command, self.identity, proof)
            proof_after, audit_after = installed_session(self.backend, self.identity)
            require(proof_after == proof and audit_after.raw == audit.raw
                    and audit_after.status(request_id) == status,
                    'Original installation/audit/request changed during observation')
            require(read(path, 2*1024*1024) == raw and read(commit_path, 2*1024*1024) == commit_raw
                    and capture['source_pins'] == initial
                    and source_pins() == initial, 'Baseline or source graph changed during observation')
            effect = evaluate_relation_effect(command['action'], before, after, status)
            result['effect'] = effect
            result['baseline_sha256'] = digest(raw)
            result['relation'] = dict(status=after['status'], snapshot=after['snapshot'],
                two_pass_equal=True, duration_ms=capture['duration_ms'], rpm_budget=capture['rpm_budget'],
                capture_record=None, global_membership_verified=False)
            if effect['selected_effect_verified'] is True:
                result['completion_state'] = 'selected_effect_observed'
            if record:
                directory.mkdir(parents=True, exist_ok=True)
                result['relation']['capture_record'] = write_journal(
                    directory/f'relation-request-capture-{time.time_ns()}.json', capture)
        except ERRORS as exc:
            result['effect'] = unknown_effect('Baseline, original dispatch or current relation proof unavailable', exc)
            result['completion_state'] = 'evidence_insufficient'
            result['relation'] = None
        if record:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                result['record'] = write_journal(directory/f'relation-request-observation-{time.time_ns()}.json', result)
            except ERRORS as exc:
                result['record_failure'] = dict(type=type(exc).__name__, message=str(exc))
        return result


def candidate_catalog():
    initial = source_pins()
    result = deepcopy(live_catalog())
    for action in ACTIONS:
        result['profiles'].append(dict(action=action, candidate_unsealed=True,
            runtime_snapshot_kind='original_request_exact_typed_relation_pair_two_pass',
            completion_stage='selected_indexed_relation_observed', symmetric=PROFILES[action]['symmetric'],
            recipient_reply_state_observed=False, AI_acceptance_verified=False,
            required_fields=['real_installed_session_identity', 'fresh_absent_prepublication_baseline',
                'complete_original_dispatch_receipt', 'same_full_handle_pair', 'both_typed_native_indexes',
                'raw_object_full_endpoints_and_lifecycle_flags', 'source_and_audit_guards'],
            limitations=['Only observed absent-to-indexed relation, not exclusive request causality.',
                'No AI acceptance, global membership, persistence, world lease or atomicity proof.']))
    require(source_pins() == initial, 'Candidate catalog sources changed')
    result.update(schema='EU4DIPLOMACY-RELATION-REQUEST-CATALOG-CANDIDATE/1',
        candidate_relation_request_profiles=list(ACTIONS), source_pins=initial,
        candidate_unsealed=True, stable_public_request_profile_count=15,
        synthetic_integration_only=True, new_runtime_effects_verified=0)
    return result
