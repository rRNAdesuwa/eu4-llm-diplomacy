import copy
import json
import unittest
from pathlib import Path
from observer import Observer, EXE_SHA, REVOKERS, SITES

FRONT, CALLBACK, HOLDER, GAME, CTX, TRANSPORT, SERVER = (0x100000,0x200000,0x300000,0x400000,0x500000,0x600000,0x700000)


def trace():
    rows = []
    def event(kind, **data):
        rows.append(dict(event=kind,seq=len(rows)+1,uptime_ms=1000+len(rows),thread=7,**data))
    def enter(name,span,parent=0,**data):
        event('enter',name=name,rva=SITES[name],span=span,parent=parent,**data)
    def leave(name,span,**data):
        event('exit',name=name,span=span,normal_return=True,**data)
    event('bootstrap',exe_sha256=EXE_SHA,hooks_before_play=True)
    enter('play',1,callback=CALLBACK,frontend=FRONT,holder=HOLDER,game=GAME,mode=0,config=[1,0],frontend_vtable=0x1d5a8c8)
    enter('context_install',2,1,frontend=FRONT,holder=HOLDER,context=0)
    leave('context_install',2,input_consumed=True,holder_context=0)
    enter('fallback',3,1,context_type=2)
    enter('context_ctor',4,3,context_type=2,object=CTX)
    leave('context_ctor',4,object=CTX,vtable=0x1d8c900,context_type=2,flag54=0,flag55=1,
          transport=TRANSPORT,transport_vtable=0x1d96178,transport_backlink=CTX)
    leave('fallback',3)
    enter('context_install',5,1,frontend=FRONT,holder=HOLDER,context=CTX)
    leave('context_install',5,input_consumed=True,holder_context=CTX)
    leave('play',1,mode=0,config=[1,0],start_pending=1)
    enter('frontend_update',6,frontend=FRONT)
    enter('server_ctor',7,6,return_rva=0x10daeb2,config_argument5=FRONT+0x400,holder_argument4=HOLDER,object=SERVER)
    enter('config_copy',8,7,return_rva=0x803d2c,destination=SERVER+0x1708,source=FRONT+0x400)
    leave('config_copy',8,config=[1,0])
    leave('server_ctor',7,object=SERVER,vtable=0x1cb8460,holder=HOLDER,config=[1,0])
    enter('holder_server_install',9,6,holder=HOLDER,server=SERVER)
    leave('holder_server_install',9,input_consumed=True,holder_server=SERVER)
    leave('frontend_update',6)
    event('frame_snapshot',rva=0x10a6ec0,game=GAME,server=SERVER,holder=HOLDER,context=CTX,transport=TRANSPORT,
          config=[1,0],mode=0,context_profile=[2,0,1,0x1d96178],transport_backlink=CTX,same_generation=1,
          double_snapshot_equal=True,players_complete=True,only_local_ids=True,pending_transition=False,
          database=0x800000,block=0x900000,index=0xa00000,player_handle=0x100007a00415246)
    return rows


def observe(rows):
    observer = Observer()
    for row in rows:
        observer.observe(row)
    return observer


class ObserverTests(unittest.TestCase):
    def test_complete_sequence_observes_but_never_authorizes(self):
        status = observe(trace()).status()
        self.assertTrue(status['origin_sequence_observed'])
        self.assertFalse(status['production_ready'])
        self.assertFalse(status['engine_lifetime_synchronized'])

    def test_existing_world_snapshot_cannot_create_history(self):
        rows = trace()
        row = rows[-1]; row['seq'] = 2
        self.assertFalse(observe([rows[0],row]).status()['origin_sequence_observed'])

    def test_missing_copy_and_return_cannot_commit(self):
        rows = trace(); del rows[13:15]
        for n,row in enumerate(rows,1): row['seq'] = n
        self.assertFalse(observe(rows).status()['origin_sequence_observed'])

    def test_exact_invocation_and_config_identity(self):
        for index,key,value in ((12,'config_argument5',FRONT+0x408),(12,'holder_argument4',HOLDER+8),
                                (13,'parent',1),(13,'destination',SERVER+0x1700),
                                (13,'return_rva',0x803d27),(14,'span',7),(6,'transport_backlink',CTX+8)):
            with self.subTest(key=key):
                rows = trace(); rows[index][key] = value
                self.assertFalse(observe(rows).status()['origin_sequence_observed'])

    def test_foreign_thread_and_lost_order(self):
        for key,value in (('thread',8),('seq',999),('uptime_ms',0)):
            rows = trace(); rows[13][key] = value
            self.assertTrue(observe(rows).status()['closed'])

    def test_noncanonical_and_network_profiles_rejected(self):
        for index,key,value in ((1,'config',[0,1]),(14,'config',[1,1]),(14,'config',[True,False]),
                                (6,'flag54',False),(5,'context_type',1),(19,'context_profile',[2,1,1,0x1d96178])):
            rows = trace(); rows[index][key] = value
            self.assertFalse(observe(rows).status()['origin_sequence_observed'])

    def test_every_declared_invalidation_revokes_same_addresses(self):
        for reason,rva in REVOKERS.items():
            with self.subTest(reason=reason):
                observer = observe(trace())
                observer.observe(dict(event='invalidate',seq=21,uptime_ms=1021,thread=8,reason=reason,rva=rva,bound_identity_match=True))
                self.assertFalse(observer.status()['origin_sequence_observed'])
                self.assertEqual(observer.generation,2)
                stale = copy.deepcopy(trace()[-1]); stale.update(seq=22,uptime_ms=1022,same_generation=2)
                observer.observe(stale)
                self.assertFalse(observer.status()['origin_sequence_observed'])

    def test_reentrant_invalidation_is_not_repaired_by_return(self):
        rows = trace()
        rows.insert(6,dict(event='invalidate',seq=0,uptime_ms=1006,thread=7,reason='load_game',rva=0x74b8a0,bound_identity_match=True))
        for n,row in enumerate(rows,1): row.update(seq=n,uptime_ms=1000+n)
        self.assertFalse(observe(rows).status()['origin_sequence_observed'])

    def test_opaque_callback_scope_is_not_snapshot_safe(self):
        observer = observe(trace())
        observer.observe(dict(event='enter',seq=21,uptime_ms=1021,thread=7,name='opaque_dispatch',rva=SITES['opaque_dispatch'],span=10,parent=0,context=CTX))
        frame = copy.deepcopy(trace()[-1]); frame.update(seq=22,uptime_ms=1022)
        self.assertFalse(observer.observe(frame)['origin_sequence_observed'])

    def test_capture_loss_and_incomplete_return(self):
        observer = observe(trace()[:7])
        self.assertFalse(observer.status()['origin_sequence_observed'])
        observer.observe(dict(event='capture_loss',seq=8,uptime_ms=1010,thread=7))
        self.assertTrue(observer.status()['closed'])

    def test_startup_timeout(self):
        rows = trace(); rows[-1]['uptime_ms'] = 200000
        self.assertFalse(observe(rows).status()['origin_sequence_observed'])


if __name__ == '__main__':
    unittest.main()
