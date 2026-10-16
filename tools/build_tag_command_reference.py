"""Generate a reference for the compiled TAG registry. Reads files only."""
import argparse
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.tag_command_backend import TagCommandBackend, decode, digest, read, require

CATEGORIES = {"alliance": "盟约", "influence": "影响", "relations": "关系", "dynasty": "王室",
              "covert": "秘密行动", "economy": "经济行动", "access": "通行权", "favors": "人情"}
REASONS = {
    "deferred_parameterized_action": "需要省份、第三国、数量等额外参数，按本轮范围延期",
    "deferred_existing_unit_faction_or_province_binding": "需要绑定已有单位、叛军派系或省份对象",
    "deferred_insult_definition_selector": "需要选择侮辱定义",
    "legacy_cancel_label_without_verified_cancel_semantics": "只有旧取消文案，尚未证实可取消的任务和效果",
    "no_valid_native_direction": "已检查的原生分支拒绝该发起方向，替代通路未证实",
}


def render(evidence_path=None):
    backend = TagCommandBackend()  # Verifies files; does not construct WindowsRuntime.
    config_raw = read(ROOT / "bridge/tag_actions_1375_v31.json", 1024 * 1024)
    catalog = decode(read(ROOT / "bridge/diplomacy_catalog.json", 4 * 1024 * 1024))["actions"]
    scope = {a["action_id"] for a in catalog if a["category"] in CATEGORIES}
    bound, excluded = set(backend.actions), {a["action"] for a in backend.excluded}
    require(not bound & excluded and bound | excluded == scope, "Eight-category coverage is incomplete")
    evidence_path = Path(evidence_path or ROOT / "work/runtime/tag31-integration-final-20261013.json").resolve()
    evidence_raw = read(evidence_path, 2 * 1024 * 1024)
    evidence = decode(evidence_raw)
    outcomes = {r["command"]["action"]: r for r in evidence["results"]}
    require(set(outcomes) == bound, "Integration evidence and registry differ")
    state_text = {"dispatched": "已提交，接受/效果见独立观测", "native_rejected": "游戏条件/预检拒绝，原请求禁止重发",
                  "unknown_no_retry": "冻结，禁止重发", "not_dispatched": "尚未进入原生调用"}
    counts = Counter(b["category"] for b in backend.bindings)
    states = Counter(r["state"] for r in outcomes.values())
    lines = ["# 1.37.5 TAG 外交接口动作清单", "",
             "本表由 `python -B tools/build_tag_command_reference.py` 从当前已编译注册表生成。"
             "`--check` 只核对文件。动作均只接收 `request_id/action/actor/target`，发起国可为 AI。", "",
             f"本轮八类目录共 {len(scope)} 项：{len(bound)} 个绑定、{len(excluded)} 个排除项。"
             "宣战、议和不在范围内。绑定表示代码通路已编译，不表示游戏接受或效果已通过。", "",
             f"构建：`{backend.manifest_path.relative_to(ROOT).as_posix()}`。",
             f"Manifest SHA-256：`{backend.manifest_sha}`。",
             f"注册表 SHA-256：`{digest(config_raw)}`。", "",
             "| 类别 | 绑定数 | 排除数 |", "| --- | ---: | ---: |"]
    for category, label in CATEGORIES.items():
        lines.append(f"| {label} | {counts[category]} | {sum(a['category'] == category for a in backend.excluded)} |")
    lines += ["", f"实际测试状态取自 `{evidence_path.relative_to(ROOT).as_posix()}`，"
              "只表示这一轮已授权拉通批次的发送情况，不覆盖历史效果记录。",
              f"证据 SHA-256：`{digest(evidence_raw)}`。", "",
              f"合计{states['dispatched']}次派发、{states['native_rejected']}次条件/预检拒绝、"
              f"{states['unknown_no_retry']}项未知；完整效果验收未通过。"
              "具体存档变化及未通过项见[拉通记录](tag-command-integration-1375.md)。", "",
              "本轮只沿已审计的未领取请求继续；已进入、被拒、已提交或未知的请求均未重发。"
              "表中状态属于同一次最终拉通的各段合并结果。"
              "后续开发测试只允许完整审计证明未发送、清理闭合的正常拒绝动作使用新ID；"
              "历史成功、已派发及未知动作仍封禁，不重新运行全量批次。", "",
              "原生条件仍由工厂、full+88、command gate 及发送前检查裁定；测试 Mod 的脚本条件放开"
              "不能保证绕过硬编码条件。精确脚本条款和局部原生检查线索见"
              "[条件查询](tag-command-conditions-1375.md)，可用CLI `conditions --action <action>`"
              "或HTTP `GET /native/v1/conditions/{action}`读取。"
              "百科直读仍失败，搜索缓存中的旧版说明仅作核对线索。", ""]
    for category, label in CATEGORIES.items():
        lines += [f"## {label}", "", "| action | 原生族 | 模式/定义 | 本轮状态 |", "| --- | --- | --- | --- |"]
        for binding in backend.bindings:
            if binding["category"] != category:
                continue
            action = binding["action"]
            mode = binding["script_key"] or ("独立命令" if binding.get("route") == "independent_command"
                                              else "true" if binding["mode"] else "false")
            result = outcomes[action]
            reason = result['native_result']['reason'] if result['native_result'] else 'no_result'
            lines.append(f"| `{action}` | `{binding['native_family']}` | `{mode}` | {state_text[result['state']]}：`{reason}` |")
        lines.append("")
    lines += ["## 排除项", "", "以下标签不出现在接口 actions 中；提交会在发布前被拒绝。", "",
              "| action | 类别 | 原因 |", "| --- | --- | --- |"]
    for item in backend.excluded:
        lines.append(f"| `{item['action']}` | {CATEGORIES[item['category']]} | {REASONS[item['reason']]} |")
    lines += ["", "关于同名取消分支、附庸主动解除方向的证据，见"
              " [原生模式分类](native-diplomacy-modes-1375.md) 和 [取消动作合同](native-pair-cancel-1375.md)。", ""]
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    p.add_argument("--evidence", type=Path, help="Merged integration evidence (files only)")
    args = p.parse_args()
    output = ROOT / "docs/tag-command-actions-1375.md"
    content = render(args.evidence)
    if args.check:
        require(output.read_text("utf-8") == content, "Reference is out of date")
    else:
        output.write_text(content, encoding="utf-8", newline="\n")
    print("TAG reference: 120 bindings + 27 explicit exclusions; files only, game access=0")


if __name__ == "__main__":
    main()
