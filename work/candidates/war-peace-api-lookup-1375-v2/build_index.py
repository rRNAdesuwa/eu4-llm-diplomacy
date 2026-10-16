"""One-time manual catalog extension from exact, retained JSON evidence."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT / 'work/candidates/war-peace-api-lookup-1375-v1'
BASE_SHA = 'd4237d98c58e89be9419ff736f01d97f5fde0129c07c5c7f778baf010071746e'
REPORTS = 'work/reports/war-peace-api-20261015-'
DOCS = {
    'r23': ('r23-truce-observation-contract/war/contract.json',
            'da506a026f1cbfa9c95929d43313283c12fc34ac073dfa711686a5e48f0ffab6'),
    'r25': ('r25-linked-truce-callees/war/contract.json',
            'e0c0f4cd8369ddb63b0f8f6739377d7cd99e60291e8537bba7f80da979975d21'),
    'r26': ('r26-linked-truce-tails/war/conclusions.json',
            '67c2af2fd010b16a40b0103993241cb4e3e3bf76cc4e00fcd0f2e1351f430178'),
    'r35': ('r35-forward-input9-path/war/contract.json',
            'ab35063beaa9c8c3e36fcad071261a8ef04009ea3632e6fba3afdcc9586554b0'),
    'r37': ('r37-linked-leaf-entry/war/contract.json',
            '24ca7959cc69478b25bc0bd3266b62f3da6d9a57b03f1c74a4884acfee50cecb'),
    'r38': ('r38-dependency-crosswalk/war/crosswalk.json',
            'aab78fe19dddd2197e6acd3eb98f06da41537eb6cf89da2cec9bf54fd8102d7e'),
    'r40': ('r40-linked-condition-closure/war/contract.json',
            '7c5e6208276fe8c4edfea20f02956b1e2ce4fe5d27dc319cf6d09acbc5828bad'),
}


def raw(path):
    with path.open('rb') as stream:
        data = stream.read(4 * 1024 * 1024 + 1)
    assert 0 < len(data) <= 4 * 1024 * 1024
    return data


def pin(data):
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def write(name, value):
    data = (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode()
    with (HERE / name).open('xb') as stream:
        stream.write(data)
    return pin(data)


def main():
    assert not (HERE / 'index.json').exists() and not (HERE / 'data-manifest.json').exists()
    code = raw(OLD / 'war_peace_lookup.py')
    assert pin(code)['sha256'] == BASE_SHA
    base = types.ModuleType('_frozen_lookup_builder_engine')
    base.__file__ = str(OLD / 'war_peace_lookup.py')
    exec(compile(code, base.__file__, 'exec'), base.__dict__)
    old_index, _ = base.SourceGraph().verify(parse=True)
    old_manifest = base._json(raw(OLD / 'data-manifest.json'))
    index = copy.deepcopy(old_index)
    sources = copy.deepcopy(old_manifest['sources'])
    refs = {}
    for key, (suffix, digest) in DOCS.items():
        path = REPORTS + suffix
        data = raw(ROOT / path)
        assert pin(data)['sha256'] == digest, (key, 'unsealed_or_changed')
        base._json(data)
        sources[path] = pin(data)
        refs[key] = dict(path=path, **pin(data))

    def ref(key, pointer):
        return dict(refs[key], json_pointer=pointer)

    def entry(identifier, rva, title, summary, params, returns, evidence,
              aliases, unknowns, owned, borrowed, callsites=()):
        return dict(id=identifier, rva=rva, kind='function', stage='static',
            actions=['declare_war'], title=title, summary=summary,
            stage_scope='bounded ordinary static evidence; no observed execution or callable authority',
            signature=dict(status='partial_static', complete_prototype='unknown',
                           parameters=params, returns=returns),
            ownership=dict(owned=owned, borrowed=borrowed),
            call_sites=[dict(rva=site, relationship=relationship) for site, relationship in callsites],
            aliases=aliases, unresolved=unknowns, evidence=evidence,
            **{key: False for key in base.FALSE_FLAGS})

    extras = [
        entry('declare_war.truce_check', '0x506d70', '宣战停战检查消费者',
            'Always evaluates the linked condition first; then may use a linked-country shortcut, '
            'otherwise returns directional pair+45 mask1. Direct cache is not the complete helper.',
            ['RCX=declarewar action; actor full handle at+10; target full handle at+20'],
            'Normal result in AL; all selected internal branches/RET covered, external effects unknown.',
            [ref('r23', '/native_consumer'), ref('r23', '/pair_cache')],
            ['停战检查', 'truce predicate'],
            ['Transitive callee effects, reentrancy and object lifetimes', 'Typed truce object and expiry'],
            ['No ownership transfer established'], ['Action, country graph, pair rows and linked callees']),
        entry('shared.linked_country_condition', '0x2f1590', '关联国家条件调用链',
            'Gets U, checks U+11a on one branch, and calls b1e020(U+1c8,...); AL result is inverted '
            'on the latter reaching normal path. No business class name is assigned.',
            ['RCX=target country', 'RDX=actor full handle', 'R8=flag; 0 in retained506d70 caller'],
            'Selected normal AL0/1 exits closed by R26; external callee contracts remain conditional.',
            [ref('r25', '/windows/0'), ref('r26', '/false_2f'), ref('r37', '/register_contract')],
            ['关联国家检查', 'linked truce condition'],
            ['U fields business meaning', 'b1e020 and other transitive effects/lifetime'],
            ['Only selected stack scratch is owned'], ['Country graph and U definition path'],
            [('0x506dba', 'direct call from truce_check')]),
        entry('shared.dependency_definition_lookup', '0x3d79f0', '条件从属定义取值叶函数',
            'A known direct-CALL entry in a pdata gap scans D+128 sixteen-byte entries and returns '
            'P+40. Conditional field match to the frozen dependency reader, with an extra linked-pair premise.',
            ['RCX=C country pointer; incoming RDX/R8 overwritten before use'],
            'RAX=0 or QWORD[P+40]; concrete selected normal paths preserve R9/R10, not an ABI assumption.',
            [ref('r37', '/entry'), ref('r37', '/dataflow'), ref('r37', '/register_contract'),
             ref('r38', '/mapping'), ref('r38', '/limits')],
            ['从属定义取值', 'dependency definition', 'pdata gap leaf'],
            ['Native has no typed/bounds/fullhandle guards', 'Exact U class/size/owner/lifetime',
             'Reader pair must equal C and its C+18f0 linked country; sample_pair does not enforce that premise'],
            ['No allocations or explicit stores in selected leaf CFG'], ['Country graph, index entries, P and U'],
            [('0x2f159f', 'direct call in linked_country_condition')]),
        entry('shared.linked_condition_evaluator', '0xb1e020', '关联条件函数（非只读保证）',
            'Complete owned-byte instruction coverage supplements the earlier512-byte prefix; '
            'normal-return paths are address-bounded, while an INT3 terminal and unfollowed callees '
            'remain unresolved. The normal epilogue preserves AL; module/alias writes prevent a read-only API claim.',
            ['RCX=U+1c8', 'RDX=target full handle', 'R8=actor full handle', 'R9=flag; 0 at retained caller'],
            'Conditional normal return contract in R40; not a total business predicate or arbitrary-input guarantee.',
            [ref('r40', '/entry'), ref('r40', '/control_flow'), ref('r40', '/return_contract'),
             ref('r40', '/writes'), ref('r40', '/callee_boundary')],
            ['关联条件求值', 'linked evaluator'],
            ['Transitive effects, return/termination and volatile preservation', 'Class, AND/OR and expiry semantics'],
            ['Selected stack frame'], ['U interior, country graph, module/TLS and unfollowed callees'],
            [('0x2f15fa', 'direct call in linked_country_condition')]),
        entry('shared.linked_property_address', '0x40a6d0', '关联属性地址选择函数',
            'If country+1420 P is nonnull, reads P+10 and returns P+38; null branch calls unreviewed fallbacks.',
            ['RCX=resolved linked-country pointer'],
            'P+38 or fallback return+78/+58; no safe external ownership or class established.',
            [ref('r25', '/windows/1')], ['关联属性地址', 'linked interior address'],
            ['Fallback effects and return validity', 'P class/ownership/lifetime'],
            ['Only selected stack scratch'], ['Country and P/fallback objects'],
            [('0x506e05', 'direct call from truce_check')]),
        entry('shared.linked_property_byte', '0x7ae260', '关联属性字节返回函数',
            'Selected branch returns a zero-extended byte, not normalized boolean. Another tail calls45b280 '
            'then executes INT3 if it returns; transitive effects and exception meaning are unknown.',
            ['RCX=interior address returned by40a6d0'],
            'EAX=selected byte on normal RET7ae2c6; not every path has a proved normal return.',
            [ref('r25', '/windows/2'), ref('r26', '/tail_7ae')],
            ['关联属性字节', 'linked byte result'],
            ['Unreviewed callees, caching and lifetime', 'Data/literal identity', 'Nonreturn/exception class'],
            ['Selected stack scratch'], ['Interior address, pointed object and byte source'],
            [('0x506e0d', 'direct call from truce_check')]),
        entry('shared.literal_state_writer', '0x6ec450', 'truce字符串追踪所得状态写函数',
            'Input9 changed-state path stores receiver+2c=9 and +40=7 before subsequent calls; '
            'this endpoint is an excluded read-only getter candidate. Display/view purpose remains inference.',
            ['RCX=receiver', 'EDX=input9 in retained string path', 'R8B=0', 'R9B=0'],
            'Selected input9 normal RET covered; this is state mutation, not a truce status getter.',
            [ref('r35', '/findings'), ref('r35', '/analyst_inference'), ref('r35', '/unknowns')],
            ['停战字符串状态写', 'excluded truce getter', 'state writer'],
            ['Business class/display meaning', 'Callee effects, final values and lifetime'],
            ['Selected stack frame'], ['Receiver and conditional module/alias destinations']),
    ]
    assert len(extras) == 7 and len(index['entries']) == 43
    index['entries'] = sorted(index['entries'] + extras, key=lambda row: row['id'])
    docs = {path: base._json(raw(ROOT / path)) for path in sources}
    temporary_manifest = dict(sources=sources)
    base._validate_index(index, temporary_manifest, docs)
    index_pin = write('index.json', index)
    data_manifest = dict(schema='EU4-WAR-PEACE-LOOKUP-DATA-MANIFEST/1', version='1.37.5',
        game_sha256=base.GAME_SHA256, scope='offline_selected_evidence_only', index=index_pin, sources=sources)
    manifest_pin = write('data-manifest.json', data_manifest)
    print(json.dumps(dict(entries=len(index['entries']), selected_sources=len(sources),
                         index=index_pin, data_manifest=manifest_pin), sort_keys=True))


if __name__ == '__main__':
    main()
