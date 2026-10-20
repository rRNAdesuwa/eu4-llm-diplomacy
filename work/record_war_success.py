"""Preserve the confirmed war snapshot and prepare a read-only next probe."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.protocol import parse_file
from bridge.compiler import compile_request
from local_config import user_data

user = user_data()
parsed = parse_file(user / 'logs/game.log')
latest = parsed.snapshots[-1]
assert latest.fields['war'] == '1' and latest.fields['ai'] == '1'
runtime = ROOT / 'work/runtime'
runtime.mkdir(exist_ok=True)
(runtime / 'war-success.json').write_text(json.dumps({
    'snapshot': latest.to_dict(),
    'receipts': [ack.to_dict() for ack in parsed.acks],
}, ensure_ascii=False, indent=2), encoding='utf-8')
(user / 'llm_observe.txt').write_text(compile_request({'id': 'observe01', 'action': 'snapshot'}), encoding='utf-8')
validation = ROOT / 'VALIDATION.md'
content = validation.read_text(encoding='utf-8').replace('`n', '\n')
content += '\n### 宣战实测成功（1445.02.10）\n日志为 effect_entered → ACK applied，没有临时解锁分支；快照 ai=1、war=1、locked=1。确认收复曼恩战争可由带锁脚本发起，法国仍为 AI。用户也确认看到战争。证据保存于 work/runtime/war-success.json。普通原生 AI 宣战是否确实被外交锁阻止仍未验证。\n\n桥接 snapshot 动作改为已验证的内联导出，模型入口拒绝缺字段、空数值、非有限数值、非法标记及非 AI 法国。自动月度导出仍待修复与实测。\n'
validation.write_text(content, encoding='utf-8')
print('Evidence saved; prepared run llm_observe.txt')
