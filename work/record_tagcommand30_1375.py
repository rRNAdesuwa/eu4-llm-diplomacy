"""Record the existing nonplayer dispatch audit. File-only; never sends or reads EU4."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bridge.tag_command_backend import TagCommandBackend, decode, encode, read

backend = TagCommandBackend()
session = backend.build/"session-37816-01dd5a40957e7dea.json"
identity = decode(read(session,32768))["identity"]
request_id = "tag30-por-bri-fleet-1"
status = backend.status(identity,request_id)
assert status["state"] == "dispatched" and status["binding"]["actor_is_human_player"] is False
assert status["command"] == {"request_id":request_id,"actor":"POR","target":"BRI","action":"offer_fleet_basing_rights"}
assert status["binding"]["human_player_handle"]&0xffffff == int.from_bytes(b"FRA","little")
raw = read(backend.session(identity)/"events.jsonl",2*1024*1024)
rows = [decode(line) for line in raw.splitlines()]
returns = [r for r in rows if r["event"] == "native_call_return"]
assert [r["call"] for r in returns] == [0,1,2,3,4,5,7]
assert all(r["normal"] and not r["exception"] for r in returns)
assert returns[2]["boolean"] and returns[4]["boolean"]
policy = decode(read(ROOT/"work/reports/diplomacy-no-repeat-test-policy-1375.json",1024*1024))
assert status["command"]["action"] not in policy["blocked_actions"]
report = {"schema":"tag_command_nonplayer_dispatch_evidence_1","file_only_audit":True,
          "status":status,"native_returns":returns,"gameplay_effects_verified":False,
          "AI_acceptance_verified":False,"previously_successful_action_retested":False,
          "historical_effect_success_count":policy["blocked_count"],
          "audit_path":str(backend.session(identity)/"events.jsonl"),
          "audit_sha256":hashlib.sha256(raw).hexdigest(),
          "manifest_sha256":backend.manifest_sha,"validation":decode(read(backend.build.parent/"validation.json",1024*1024))}
output = ROOT/"work/runtime/tagcommand30-nonplayer-dispatch-37816.json"
with output.open("xb") as stream:
    stream.write(encode(report))
notice = ("**2026-10-12 目标纠偏：外部命令必须能指定AI国家TAG，不能限定当前玩家。** "
          "新 `tools/tag_command.py`／`bridge/tag_command_backend.py`／`bridge/tag_command_service.py` "
          "已接到真实主线程注入宿主，21个动作绑定，CLI及HTTP可指定actor/target/action并查询幂等回执。"
          "原生核心和Guard已移除actor==player限制，采样器不再固定FRA/ENG。"
          "真实进程37816／01dd5a40957e7dea，V30 DLL单次加载BridgeStart0，session d6917d789cbd7f1ec477807246a51d24。"
          "单条 tag30-por-bri-fleet-1 为POR→BRI提供驻港权，玩家仍FRA；full88及gate true，发送normal true+NULL consumed，"
          "明确actor_is_human_player=false、ownership closed、无隔离或原生异常。"
          "只证明非玩家发送，AI接受和实际关系效果未核验；历史效果成功台账仍38，禁止重发此未知接受结果。"
          "没有重跑历史成功动作，没有切换玩家，没有新的测试夹具或控制台操作。"
          "C++29协议组+4实际Guard模拟组及Python11项传输+4项HTTP离线通过。"
          "详见 `docs/tag-command-interface-1375.md` 和 `work/runtime/tagcommand30-nonplayer-dispatch-37816.json`。"
          "V29未加载／发送，信任字段合同+40/+44含义写反，禁止加载旧V29；新V30保留原生工厂值并验证clone一致，尚未实际测试信任。"
          "旧274合同目录／270静态映射并非可执行数量，旧正式V3仍501；完整外交覆盖仍待补齐。"
          "本轮无后台shell或HTTP服务。\n\n")
for name in ("HANDOFF.md","VALIDATION.md"):
    path = ROOT/name
    assert path.stat().st_size < 4*1024*1024
    old = path.read_text(encoding="utf-8")
    assert not old.startswith(notice)
    path.write_text(notice+old,encoding="utf-8",newline="\n")
print(json.dumps({"evidence":str(output),"state":status["state"],"actor":"POR","human_player":"FRA",
                  "AI_acceptance_verified":False,"gameplay_effects_verified":False}))
