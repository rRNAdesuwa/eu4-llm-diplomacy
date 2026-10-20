"""Create one-use recorder for this fresh process, with completion-gated census."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
old=ROOT/'work/run_pair23_session_1375.py';target=ROOT/'work/run_pair24_session_1375.py'
s=old.read_text().replace('pair23','pair24').replace('V23','V24')
s=s.replace('v24-pair-private-client-r2-1375','v24-pair-send-private-client-1375')
s=s.replace('8091e20aaa67199848c7a6469e9fa693fef52e153c370668c7ea1463b6a99c30','dc715db4d9e4be0ed4fc39b65cbb2aedffff3c3f2bc1bf1bc484b79a45b97387')
s=s.replace('b87daaf64c7afc3ed4abdb36979fc58e2b389c036645d62b97014567778d4502','69070517add1b483d20e3609409f88322fe54394bf66c69072aa21bec7fb4b77')
s=s.replace('79a9494d88ca1a7dda0c082008307eea1fd2348d0e11193e302d67161f9af4c2','0efbe29b2cc5ef406536ffdd8a57525d6cd6712772ce13a03aa36aafa364e88f')
s=s.replace('PID=52236','PID=11084').replace('01dd5a1a23ab2258','01dd5a221571a340').replace('len(values)<=512','len(values)<=768')
s=s.replace('EU4PAIR22GROUPDIAG/1','EU4PAIR24GROUPDIAG/1')
s=s.replace("def census(client,label):\n    m=client.manifest();g=client.graph();ro=g.local('readonly.py')",
'''def census(client,label,session=None):
    need(not (OUT/(label+'.json')).exists(),'One initial/final census only')
    m=client.manifest();g=client.graph();ro=g.local('readonly.py');audit=None
    if label=='final':
        need(session is not None,'Final requires exact session and completed/terminal audit')
        audit=client.inspect(client.identity(PID,CREATION,session,m))
        need(audit['complete'] or audit['terminal'],'No final effects sample while batch is in progress')
        # Allow ordinary game loop receiver work; never invoke/drain its queue.
        import time
        elapsed=ro.now_ms()-audit['rows'][-1]['uptime_ms']
        need(elapsed>=0,'Monotonic audit observation')
        if elapsed<2000:time.sleep((2000-elapsed)/1000)
''',1)
s=s.replace("modules=h.modules();bases=", "modules=h.modules();research=[p for _,p in modules if Path(p).name.lower().startswith(('eu4_bridge_','eu4_pair_','eu4_spy_'))]\n        if label=='initial':need(not research,'Initial census must precede every research DLL')\n        else:client.loaded(h,m,audit)\n        bases=",1)
s=s.replace("observer_sha256=sha(Path(__file__).read_bytes()),production_ready=False,gameplay_effects_verified=False)",
"observer_sha256=sha(Path(__file__).read_bytes()),completed_or_terminal_audit_sha256=audit['audit_sha256'] if audit else None,batch_complete=audit['complete'] if audit else None,production_ready=False,gameplay_effects_verified=False)",1)
s=s.replace("['check','initial','load','batch','inspect','final']","['check','initial','load','batch','inspect','finish','final']")
s=s.replace("census(client,a.op);return 0","census(client,a.op,a.session);return 0",1)
s=s.replace("timeout=40","timeout=65",1)
with target.open('xb') as f:f.write(s.encode('ascii'))
print(str(target))
