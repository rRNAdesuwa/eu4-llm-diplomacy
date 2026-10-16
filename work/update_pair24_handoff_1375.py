"""Preserve document preimages and record terminal V24 plus sealed V25 facts."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'work/runtime/pair24-handoff-20261012a'
archive=ROOT/'work/runtime/pair24-stopped-archive-11084-20261012a/archive.json'
a=json.loads(archive.read_bytes());assert a['terminal'] and a['held_exit']['normal_exit_verified']
OUT.mkdir(exist_ok=False)
text='''**2026-10-12：V24 六项发送批次在联姻提交适配器拒绝后冻结，旧进程正常退出；V25 修复候选已封存，正从原始基线重新测试。** V24 11084/01dd5a221571a340/session dfd56862d97a41dd56e3595228011b3a/owner40972，BridgeStart0，六请求一次发布。seq1附庸full+88正常false并已知清理；seq2联姻full+88与gate true、独立clone/wrapper及原对象析构均正常，持久dispatch_intent后adapter7返回normal=false/exception0/slot未消费，整个Host终止。31日志行、11适配器进入，10正常返回，实际14ca210是否进入未单独记录，不能把适配器进入当ABI进入；dispatched0，seq3..6未claim且永不补发。初末整组各一次，两遍一致，final明确在terminal之后；103外交官均空闲，五选定关系仍无对象。只作选定观测，不声称全局无副作用或游戏效果通过。

终止后另做22次/148字节只读上下文核验，没有重采效果：transport实例+0x30为0，实际vtable+0x30为预期base+1580370，ready55/80d均1。定位新SubmissionGuard误把虚函数表槽读自实例数据；旧fake夹具也复制了同一错误。原树/日志不改，新 `v24-pair-send-port-r2-1375` 修正槽地址，夹具明确instance+30=0/任意数据、错误/缺失vtable槽即使instance伪装函数也拒绝；旧组+8新transfer组作者离线通过，实际native_platform只编译不在fake中执行，未独立复审。

V24正常菜单退出，held精确进程证据exit0/FILETIME134362681340788813；完整归档536文件/11194082B，`work/runtime/pair24-stopped-archive-11084-20261012a/archive.json` SHA7bcc9f9ceda1d0ee292ab9a56aceb3257d497a3a58a4e3ee2804934a61e22cbb，audit SHAe1b067f269043140faafb0ada94d0dedd02c6124fb3e1f8605188b2d380eb8b8。V23此前也已正常UI关闭并归档504files/11222468B、SHAbae6f2be51541b715e9ab9a5d882ab2e59f5d4cd5806cf93254907ef43addd4d，但V23 held watcher超时，只有后续exact signaled exit0，不冒充held贯穿退出。

新V25 DLL SHA d24acf080d92500cc83d720965528a319686f864c449f91a37f2fb96edf3472d，manifest40738e72bdbf1c6442d9a6b55ef83ac6bf8e6211669db9b83bda41660e8f9929、BridgeStart0x3f10、295来源/19codec通过；新私有客户端19离线测试与C++/Python字节一致性通过，clientSHA9a6b722d725e8090f85b31f82910bee0d856e488598c7c31c5dc362b75a10d15。旧V24 SendCore、Port、DLL、client全部封存不热改，V25使用新5936/01dd5a2634826e4b；baseline SHA276f88afecdbc1f1a24ed6314845351b1ba5640715b7ed1fd14513b3376664fb未变。V25当前仅file-only check0，未load/发布；继续批量先发送、完成或终止后才统一末态观测。

完整目标仍未完成：274描述/270静态映射/历史28选定kind、production backend0保持；正式Contract/3仍验证接口、执行501。贴吧正文未读。下方段落为历史记录。

'''
changes={}
for name in ['HANDOFF.md','VALIDATION.md']:
 p=ROOT/name;b=p.read_bytes();assert len(b)<4*1024*1024
 with (OUT/(name+'.preimage')).open('xb') as f:f.write(b)
 first,sep,rest=b.partition(b'\n');assert sep
 after=first+b'\n\n'+text.encode('utf-8')+rest.lstrip(b'\r\n');p.write_bytes(after)
 changes[name]=dict(before=hashlib.sha256(b).hexdigest(),after=hashlib.sha256(after).hexdigest())
with (OUT/'document-update.json').open('x') as f:json.dump(changes,f,indent=2,sort_keys=True)
print(json.dumps(changes))
