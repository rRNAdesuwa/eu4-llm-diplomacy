"""One-use checkpoint prepend; preserve both document preimages."""
import hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/runtime/pair23-checkpoint-r2-20261012a'
r=json.loads((OUT/'report.json').read_bytes())
assert r['complete_no_send_lifecycles'] and r['native_calls']==r['native_returns']==36
assert not r['completed_batch_final_effects_sample'] and not r['sender_called']
vpath=ROOT/'work/candidates/v24-pair-send-core-r2-1375/development-attempt1/validation.json'
v=json.loads(vpath.read_bytes());assert v['passed'] and v['build']['all_children_collected']
text='''**2026-10-12：V23 六族真实原生无发送生命周期整批结束；V24 十二动作单次发送核心已通过离线测试，未加载。** 52236/01dd5a1a23ab2258/session f9f96b8607268273594fcf942afdb94d/owner53064。V23原封DLL单次加载BridgeStart0，六请求全部一次发布并完成：87 audit rows，36进入/36正常返回，全部known cleanup、live/quarantine/fault0。附庸及保独full+88正常false（各4调用）；联姻、改善关系、间谍网、拉拢人情full+88与command gate均true（各7调用）。所有submitted=false，没有sender/transport/effect调用；不提升正式backend或完整外交覆盖。完成日志纯文件严格复核 `work/runtime/pair23-checkpoint-r2-20261012a/completed-audit.json` SHA a6d0276492559cba462628ec4b0fa106d28278900d4bcf1aea56ce87c467e1bb。

本轮观测顺序有一处错误：首次inspect快照仅完成seq1，seq2仍在执行；root未等待complete便取了final.json。该文件永久保留并明确标为提前采样，不能证明整批末态；没有重采效果或补发。initial与提前样本各自两遍相同，选定状态也相同，但不作整批效果或世界无副作用证明。后续只读完整文件审计确认全部六结果。首checkpoint helper错用pending_call键而失败、partial目录和原helper保留；新R2核对正确pending_native_call字段完成，不访问游戏。

新 `v24-pair-send-core-r2-1375` 复用R3生命周期与取消绑定，新增单次SendCore/私有TransferPort：游戏检查拒绝时正常清理；通过后先删原对象、保留独立command/clone，持久意图后再核所有字段/取消/世界/原始TTL；仅normal true+NULL consumed算队列dispatch，所有未知冻结，无移交后读/析构/重试。旧24组+新10组（含12模式、重复调用、7未知返回组合、异常、慢意图/回退/世界和字段突变）通过 /W4/WX；68分析子进程3.578s全部收齐，peak单进程83423232B/整job123445248B，active0。纯fake，无实际TransferPort、DLL或API backend。首候选构建因/Fo尾反斜杠引号失败，原树保留，新R2只修逐源编译路径。当前游戏仍为V23进程，不热替换、不补发；下一步私有原生发送适配器与上下文绑定，再新进程整批测试。

完整目标仍未完成：274描述/270静态映射/历史28选定kind、production backend0不变，贴吧正文未读。下方日期段落均为历史记录。

'''
changes={}
for name in ['HANDOFF.md','VALIDATION.md']:
 p=ROOT/name;b=p.read_bytes();assert len(b)<4*1024*1024
 pre=OUT/(name+'.preimage')
 with pre.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 first,sep,rest=b.partition(b'\n');assert sep
 after=first+b'\n\n'+text.encode('utf-8')+rest.lstrip(b'\r\n')
 p.write_bytes(after)
 changes[name]=dict(before=hashlib.sha256(b).hexdigest(),after=hashlib.sha256(after).hexdigest())
with (OUT/'document-update.json').open('x') as f:json.dump(changes,f,indent=2,sort_keys=True)
print(json.dumps(changes))
