"""Only this new pure oracle; synthetic data, no game or frozen observer import."""
import ast
import copy
import pathlib
import unittest

import tributary_effect_oracle as oracle


def handle(tag, slot, generation=1):
    return (generation << 56) | (slot << 32) | int.from_bytes(tag.encode('ascii'), 'little')


def fixture(action='establish_tributary'):
    identity = dict(pid=80340, creation='01dd5c075fcf8c26', session='1'*32, dll_sha256='2'*64, manifest_sha256='3'*64)
    command = dict(request_id='synthetic.original.1', action=action, actor='AAA', target='BBB')
    actor, target = handle('AAA', 1), handle('BBB', 2)
    before = dict(schema=oracle.SNAPSHOT_SCHEMA, game_sha256=oracle.GAME_SHA256,
                  identity=identity, command=command, phase='before', country_count=10,
                  pair=dict(actor_tag='AAA', target_tag='BBB', actor_handle=actor, target_handle=target,
                            actor_overlord_handle=oracle.SENTINEL, target_overlord_handle=oracle.SENTINEL,
                            dependency_present=False, dependency_type=None),
                  dependency_indexes=dict(actor=[], target=[]), dependency_object=None,
                  capture_claims=dict(two_pass_equal=True, typed_countries_and_roots=True, complete_active_indexes=True),
                  baseline_claims=dict(immutable=True, before_publication=True, intent_absent_before=True,
                                       intent_absent_after=True, publisher_lock_absent_before=True, publisher_lock_absent_after=True,
                                       intent_absent_before_commit=True, publisher_lock_absent_before_commit=True))
    if action == 'convert_tributary_to_vassal':
        set_dependency(before, 'tributary_state', 'target', 0x100000)
    after = copy.deepcopy(before)
    after['phase'] = 'after'
    del after['baseline_claims']
    set_dependency(after, 'vassal' if action == 'convert_tributary_to_vassal' else 'tributary_state',
                   'actor' if action == 'ask_to_be_tributary' else 'target', 0x200000)
    receipt = dict(schema=oracle.RECEIPT_SCHEMA, game_sha256=oracle.GAME_SHA256,
                   identity=copy.deepcopy(identity), command=copy.deepcopy(command), sequence=1, state='dispatched',
                   binding=dict(actor_handle=actor, target_handle=target),
                   native_result=dict(status=4, submitted=True, slot_consumed=True, ownership_closed=True,
                                      owned_live=0, quarantined=0, adapter_fault=0, submit_exception=0),
                   audit_claims=dict(installation_record_verified=True, original_request_audit_complete=True,
                                     native_dispatch_audit_complete=True, identity=copy.deepcopy(identity),
                                     request_id=command['request_id'], audit_sha256='4'*64))
    return [action, before, after, receipt]


def set_dependency(snapshot, key, subject, address):
    p = snapshot['pair']
    p.update(dependency_present=True, dependency_type=key)
    p[subject+'_overlord_handle'] = p[('target' if subject == 'actor' else 'actor')+'_handle']
    snapshot['dependency_indexes'] = dict(actor=[dict(slot=2, object_address=address)], target=[dict(slot=1, object_address=address)])
    snapshot['dependency_object'] = dict(address=address, vtable_rva=oracle.DEPENDENCY_VTABLE_RVA,
                                         removed_byte_28=0, endpoints=[p['target_handle'], p['actor_handle']], type_key=key)


class OracleBoundaries(unittest.TestCase):
    def result(self, args, status):
        r = oracle.evaluate(*args)
        self.assertEqual(r['status'], status, r)
        self.assertTrue(all(r[k] is False for k in oracle.FALSE_FLAGS))
        self.assertEqual((r['native_calls'], r['requests_published']), (0, 0))
        self.assertIs(r['candidate_pattern_match'], status == 'candidate_pattern_match')
        return r

    def test_three_candidate_matches_and_no_mutation(self):
        for action, *_ in oracle.PROFILES:
            with self.subTest(action=action):
                a=fixture(action); original=copy.deepcopy(a)
                self.result(a, 'candidate_pattern_match'); self.assertEqual(a, original)

    def test_catalog_fresh_and_no_authority(self):
        c=oracle.catalog();self.assertEqual(c['count'],3);self.assertTrue(all(c[k] is False for k in oracle.FALSE_FLAGS))
        c['profiles'][0]['action']='bad';self.assertEqual(oracle.catalog()['profiles'][0]['action'],'establish_tributary')

    def test_reversed_overlord_does_not_match(self):
        for action, *_ in oracle.PROFILES:
            with self.subTest(action=action):
                a=fixture(action);p=a[2]['pair'];p['actor_overlord_handle'],p['target_overlord_handle']=p['target_overlord_handle'],p['actor_overlord_handle']
                self.result(a,'pattern_not_matched')

    def test_typed_absence_requires_both_indexes_and_no_object(self):
        for mutation in ('actor_index','object','key','missing_index'):
            with self.subTest(mutation=mutation):
                a=fixture()
                if mutation=='actor_index':a[1]['dependency_indexes']['actor']=[dict(slot=2,object_address=0x100000)]
                elif mutation=='object':a[1]['dependency_object']=copy.deepcopy(a[2]['dependency_object'])
                elif mutation=='key':a[1]['pair']['dependency_type']='tributary_state'
                else:del a[1]['dependency_indexes']['target']
                self.result(a,'unknown')

    def test_absence_with_unrelated_valid_entries(self):
        a=fixture();a[1]['dependency_indexes']['actor']=[dict(slot=3,object_address=0x300000)]
        a[1]['dependency_indexes']['target']=[dict(slot=4,object_address=0x400000)]
        self.result(a,'candidate_pattern_match')

    def test_object_type_removal_endpoints(self):
        for key,value in [('vtable_rva',0),('vtable_rva',True),('removed_byte_28',1),('removed_byte_28',False),('endpoints',[handle('AAA',1),handle('CCC',3)]),('type_key','vassal')]:
            with self.subTest(key=key,value=value):
                a=fixture();a[2]['dependency_object'][key]=value;self.result(a,'unknown')

    def test_indices_duplicate_out_of_bounds_and_alias(self):
        for mode in ('duplicate','zero','bool','overflow','pointer','reverseptr','excess'):
            with self.subTest(mode=mode):
                a=fixture();items=a[2]['dependency_indexes']['actor']
                if mode=='duplicate':items.append(copy.deepcopy(items[0]))
                elif mode=='zero':items[0]['slot']=0
                elif mode=='bool':items[0]['slot']=True
                elif mode=='overflow':items[0]['slot']=10
                elif mode=='pointer':items[0]['object_address']=2**47
                elif mode=='reverseptr':a[2]['dependency_indexes']['target'][0]['object_address']=0x300000
                else:a[2]['dependency_indexes']['actor']=[dict(slot=3,object_address=0x300000)]*257
                self.result(a,'unknown')

    def test_full_handle_generation_reuse_in_capture(self):
        a=fixture();a[2]['pair']['actor_handle']=handle('AAA',1,2);a[2]['dependency_object']['endpoints'][1]=handle('AAA',1,2)
        a[2]['pair']['target_overlord_handle']=handle('AAA',1,2);self.result(a,'unknown')

    def test_full_handle_generation_reuse_in_receipt(self):
        a=fixture();a[3]['binding']['target_handle']=handle('BBB',2,2);self.result(a,'unknown')

    def test_handle_encoding_rejects_partial_and_reserved_bytes(self):
        for value in (int.from_bytes(b'AAA','little'),handle('AAA',1)|(1<<24),handle('AAA',1)|(1<<48),True,handle('AAA',32768)):
            with self.subTest(value=value):
                a=fixture();a[1]['pair']['actor_handle']=value;self.result(a,'unknown')

    def test_identity_pid_and_creation_bounds(self):
        for key,value in [('pid',0),('pid',True),('pid',-1),('pid',2**32),('creation','0'*16),('creation','f'*15),('creation',1),('session','0'*32)]:
            with self.subTest(key=key,value=value):
                a=fixture();a[1]['identity'][key]=value;self.result(a,'unknown')

    def test_dword_upper_boundary_and_nonzero_creation(self):
        a=fixture()
        for x in (a[1]['identity'],a[2]['identity'],a[3]['identity'],a[3]['audit_claims']['identity']):x.update(pid=0xffffffff,creation='0000000000000001')
        self.result(a,'candidate_pattern_match')

    def test_session_nonce_and_request_id_mismatch(self):
        for mode in ('capture_session','audit_session','nonce_field','capture_id','receipt_id','audit_id'):
            with self.subTest(mode=mode):
                a=fixture()
                if mode=='capture_session':a[2]['identity']['session']='5'*32
                elif mode=='audit_session':a[3]['audit_claims']['identity']['session']='5'*32
                elif mode=='nonce_field':a[1]['identity']['nonce']=a[1]['identity'].pop('session')
                elif mode=='capture_id':a[2]['command']['request_id']='another'
                elif mode=='receipt_id':a[3]['command']['request_id']='another'
                else:a[3]['audit_claims']['request_id']='another'
                self.result(a,'unknown')

    def test_partial_unknown_or_rejected_receipt(self):
        for mode in ('missing','state','status','owned','audit'):
            with self.subTest(mode=mode):
                a=fixture()
                if mode=='missing':del a[3]['native_result']['slot_consumed']
                elif mode=='state':a[3]['state']='unknown_no_retry'
                elif mode=='status':a[3]['native_result']['status']=3
                elif mode=='owned':a[3]['native_result']['owned_live']=1
                else:a[3]['audit_claims']['native_dispatch_audit_complete']=False
                self.result(a,'unknown')

    def test_boolean_and_integer_receipt_types(self):
        for key,value in [('status',True),('submitted',1),('ownership_closed',1),('owned_live',False),('quarantined',0.0)]:
            with self.subTest(key=key):
                a=fixture();a[3]['native_result'][key]=value;self.result(a,'unknown')

    def test_baseline_timing_and_capture_claims(self):
        for scope,key,value in [('baseline_claims','immutable',False),('baseline_claims','intent_absent_after',1),('baseline_claims','intent_absent_before_commit',False),('baseline_claims','publisher_lock_absent_before_commit',1),('capture_claims','two_pass_equal',False),('capture_claims','complete_active_indexes',1)]:
            with self.subTest(key=key):
                a=fixture();a[1][scope][key]=value;self.result(a,'unknown')

    def test_wrong_old_type_or_old_subject(self):
        for action,subject in (('establish_tributary','target'),('ask_to_be_tributary','actor')):
            for mode in ('already_present','not_sentinel'):
                with self.subTest(action=action,mode=mode):
                    a=fixture(action)
                    if mode=='already_present':set_dependency(a[1],'tributary_state',subject,0x100000)
                    else:a[1]['pair'][subject+'_overlord_handle']=handle('CCC',3)
                    self.result(a,'unknown')
        for mode in ('already_target_type','wrong_subject','convert_absent'):
            with self.subTest(mode=mode):
                a=fixture('convert_tributary_to_vassal')
                if mode=='already_target_type':set_dependency(a[1],'vassal','target',0x100000)
                elif mode=='wrong_subject':a[1]['pair']['target_overlord_handle']=oracle.SENTINEL
                else:
                    a[1]['pair'].update(dependency_present=False,dependency_type=None,target_overlord_handle=oracle.SENTINEL)
                    a[1]['dependency_indexes']=dict(actor=[],target=[]);a[1]['dependency_object']=None
                self.result(a,'unknown')

    def test_same_address_without_transition_is_not_match(self):
        a=fixture('convert_tributary_to_vassal');set_dependency(a[2],'tributary_state','target',0x100000)
        self.result(a,'pattern_not_matched')

    def test_replacement_address_and_same_address_can_match(self):
        for address in (0x100000,0x200000):
            with self.subTest(address=address):
                a=fixture('convert_tributary_to_vassal');set_dependency(a[2],'vassal','target',address);self.result(a,'candidate_pattern_match')

    def test_valid_absent_after_is_nonmatch_not_rejection(self):
        a=fixture();a[2]=copy.deepcopy(a[1]);a[2]['phase']='after';del a[2]['baseline_claims'];self.result(a,'pattern_not_matched')

    def test_invalid_action_schema_and_request_grammar(self):
        for mode in ('action','schema','request_id','sequence','presence'):
            with self.subTest(mode=mode):
                a=fixture()
                if mode=='action':a[0]='declare_war'
                elif mode=='schema':a[2]['schema']='old'
                elif mode=='request_id':a[1]['command']['request_id']='x'*97
                elif mode=='sequence':a[3]['sequence']=True
                else:a[2]['pair']['dependency_present']=1
                self.result(a,'unknown')

    def test_malformed_inputs_stay_unknown(self):
        for index in (1,2,3):
            for value in (None,[],True):
                with self.subTest(index=index,value=value):
                    a=fixture();a[index]=value;self.result(a,'unknown')

    def test_module_has_no_runtime_or_io_import_route(self):
        tree=ast.parse(pathlib.Path(oracle.__file__).read_bytes())
        imports=[n for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom))]
        self.assertEqual(len(imports),1);self.assertEqual([x.name for x in imports[0].names],['re'])
        calls={n.func.id for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
        self.assertFalse(calls & {'open','exec','eval','compile','__import__'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
