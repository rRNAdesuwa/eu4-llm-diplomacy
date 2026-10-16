"""Prepare a separate source delta. Never executes an old CLI or opens a process."""
import hashlib
import json
from pathlib import Path

THIS = Path(__file__).resolve()
ROOT = THIS.parents[1] if THIS.parent.name == 'work' else THIS.parents[3]
OLD = ROOT / 'work/candidates/linked-truce-projection-1375-v1'
NEW = ROOT / 'work/candidates/linked-truce-projection-1375-v2'


def raw(name, digest):
    data = (OLD / name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == digest
    return data.decode('utf-8').replace('\r\n', '\n')


def replace_one(text, before, after):
    assert text.count(before) == 1, before[:80]
    return text.replace(before, after, 1)


def main():
    assert not NEW.exists(), 'Prepare only once'
    code = raw('linked_truce_projection.py', '873ea638227e7543dbe2a18d74097559083756f08bc3186c945412c6d9907225')
    code = replace_one(code, 'Three bounded external', 'Four bounded external')
    extra = {
        'work/candidates/linked-truce-projection-1375-v1/linked_truce_projection.py': '873ea638227e7543dbe2a18d74097559083756f08bc3186c945412c6d9907225',
        'work/candidates/linked-truce-projection-1375-v1/source-manifest.json': '176cb7ce2638767be0b98afbe673c06f08fa6430db41cb267a5eb3996b53da47',
        'work/reports/linked-truce-projection-live-review-20261015-r1/findings.json': 'c5faea27aa8164d8cd4fff9fd319dd4c08489b739948a7106018f7077ecd9f70',
        'work/reports/war-peace-api-20261015-r47-header61-projection/war/projection.json': '70bb89b6b7913bb5124ebc83d494266c75d8f1f6b2a50bb51815079d6a53fcb9',
    }
    precision = ROOT / 'work/reports/war-peace-api-20261015-r47-header61-projection/war/precision.json'
    extra[str(precision.relative_to(ROOT)).replace('\\', '/')] = '2cffa3c97b9e4f55b93db2b8b106bb0f0bf59c946b0aec0841808699daedb122'
    review = ROOT / 'work/reports/war-peace-api-20261015-r47-independent-review/war/findings.json'
    assert review.exists(), 'Wait for independently sealed R47 review'
    extra[str(review.relative_to(ROOT)).replace('\\', '/')] = 'a06c0cc61b00200abc7ce02d3fa4906a7fbe34fc87daeebf9d22e4faeab57140'
    for name, digest in extra.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    inserted = ',\n'.join(' '+repr(name)+':'+repr(digest) for name, digest in extra.items())
    code = replace_one(code, 'FIXED={\n', 'FIXED={\n'+inserted+',\n')
    code = replace_one(code, "'README.md','build_manifest.py','run_offline.py')}",
        "'README.md','build_manifest.py','run_offline.py','source-delta.json','prepare_source.py')}")
    old_end = "'506e42|506e54']}"
    new_end = "'506e42|506e54'],\n 'D_independent_actor_header61_nonzero':['2f15ed','2f15f4','b1e066','b1e114->b1e6c3','b1e6c8->b1ebd6','b1ebd8','b1ebe0->b1ec0f','b1ec32','2f1603->2f160b','2f1612','506dd3->506e16','506e2a','506e42|506e54']}"
    code = replace_one(code, old_end, new_end)
    old_block = """    require(linked_value!=a,'C actor-linked selfpair unsupported')
    h=facts.get('definition_header');require(type(h) is dict and set(h)=={'0x60','0x61','0x62','0x63'},'Four explicit header bytes required')
    require(all(type(v) is int and v==0 for v in h.values()),'Unsupported nonempty raw header')
    require(type(facts.get('loaded_K')) is int and facts['loaded_K']==15,'LoadedK15 profile missing')
    cache=facts.get('actor_linked_cache_flag_set');require(type(cache) is bool and cache is False,'Actor-linked cache must be observed clear; external7ae unsupported')
    path='C_independent_actor_zero_header_clear_linked_cache'"""
    new_block = """    require(linked_value!=a,'C/D actor-linked selfpair unsupported')
    require(((linked_value>>32)&0xffff)!=((a>>32)&0xffff),'C/D linked and actor slots alias')
    h=facts.get('definition_header');require(type(h) is dict and set(h)=={'0x60','0x61','0x62','0x63'},'Four explicit header bytes required')
    require(all(type(v) is int and 0<=v<=255 for v in h.values()),'Explicit byte header required')
    require(type(facts.get('loaded_K')) is int and facts['loaded_K']==15,'LoadedK15 profile missing')
    if h['0x61']!=0:
     path='D_independent_actor_header61_nonzero'
    else:
     require(all(v==0 for v in h.values()),'Unsupported nonempty raw header')
     cache=facts.get('actor_linked_cache_flag_set');require(type(cache) is bool and cache is False,'Actor-linked cache must be observed clear; external7ae unsupported')
     path='C_independent_actor_zero_header_clear_linked_cache'"""
    code = replace_one(code, old_block, new_block)
    code = replace_one(code, "for x in ('A_target_exact_sentinel','B_linked_actor_byte11a_nonzero','C_independent_actor_zero_header_clear_linked_cache')",
        "for x in ('A_target_exact_sentinel','B_linked_actor_byte11a_nonzero','C_independent_actor_zero_header_clear_linked_cache','D_independent_actor_header61_nonzero')")
    code = replace_one(code, "schema='EU4-LINKED-TRUCE-PROJECTION/1'", "schema='EU4-LINKED-TRUCE-PROJECTION/2'")
    NEW.mkdir()
    (NEW / 'linked_truce_projection.py').write_text(code, encoding='utf-8', newline='\n')
    (NEW / 'prepare_source.py').write_bytes(Path(__file__).read_bytes())
    (NEW / 'test_linked_truce_projection.py').write_bytes((ROOT / 'work/linked_truce_v2_delta_tests_20261015.py').read_bytes())
    (NEW / 'README.md').write_text('''# 关联停战四路径候选 CLI

在独立 v1 的三个正常路径之外，新增 actor 严格独立、header61 非零、loaded K15 的第四路径。原生 b1e020 条件返回 AL1，使 2f1590 返回 false，506d70 转到直接 pair 缓存。C/D 路径明确拒绝 linked 与 actor 同 slot 的 generation 别名。R47 逐原始指令/边与独立审查是新增依据，保留 v1 所有源码和未知采样。

只使用 QUERY/VM_READ，在外部计算条件返回值，不执行游戏函数。其余 sampler、host、五个 code/K blocks、双遍完整表与原始 journal、上下文退出和 source postguard 与 v1 相同。没有新动作、钩子、世界写入、保存或重载。真实 process 身份由调用者提供；只读 nonce 不是安装 session。

```powershell
python -B work/candidates/linked-truce-projection-1375-v2/linked_truce_projection.py check
python -B work/candidates/linked-truce-projection-1375-v2/linked_truce_projection.py catalog
python -B work/candidates/linked-truce-projection-1375-v2/linked_truce_projection.py status --pid PID --creation CREATION --actor POR --target ORL
```

当前为 draft：运行时入口在 library/process 构造前拒绝，须完成新 delta 离线测试、独立 source-ready、root seal 和 seal delta 审查才可实采。12 个方法只覆盖新增分支、slot 别名及 draft 拒绝，不重跑 v1 的21方法或历史采样。

成功状态为 computed_selected_native_return_projection，true 与 false 均可退出0；未支持路径为 unknown/null，退出2，不自动重试。所有实际 native predicate、请求效果、完整停战、expiry、议和完成、native_ready、atomic 和 lifetime lease 标志始终 false。双遍相等不是原子快照。CloseHandle 的 OS 返回值沿固定组件未核验。

D 分支不消费 C+60/+62/+63 或 actor-linked cache；typed active dependency、完整端点、linked slot 与 actor slot 不同、actor 独立和 loaded K15 仍必须证明。U 只按现有 raw profile 读取，不声称已恢复其完整类型、大小、vtable 或生命周期。其他条件继续 unknown。
''', encoding='utf-8', newline='\n')
    for name, digest in [('build_manifest.py', '7e25e00a37ce48724b4758812360d8c8c95d98e85265a51171482474bd13a7f7'),
                         ('run_offline.py', 'e945a976f1de90a4805325a3c2fe9bb873d65df554cdf45bdf55684aa66c7980')]:
        (NEW / name).write_text(raw(name, digest), encoding='utf-8', newline='\n')
    lineage = dict(schema='EU4-LINKED-TRUCE-V2-SOURCE-DELTA/1', old_cli_sha256='873ea638227e7543dbe2a18d74097559083756f08bc3186c945412c6d9907225',
        changes=['docstring', 'six additional frozen evidence pins and two required lineage files', 'D path metadata', 'C/D slot alias guard and header61 branch',
                 'catalog fourth profile', 'schema version'],
        unchanged=['sample_selected', 'code_guard', 'Libraries', 'observe', 'run status branch; catalog tuple alone changed', 'RuntimeCapture reuse', 'RPM journals', 'CLI arguments'],
        old_sources_mutated=False, old_tests_or_captures_repeated=False, process_accesses=0, native_ready=False)
    (NEW / 'source-delta.json').write_text(json.dumps(lineage, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status='prepared', source_sha256=hashlib.sha256((NEW/'linked_truce_projection.py').read_bytes()).hexdigest(), extra_pins=extra)))


if __name__ == '__main__':
    main()
