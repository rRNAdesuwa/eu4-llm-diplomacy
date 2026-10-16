"""Authoring only: index fixed retained JSON sources, never read EXE/processes."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
P='work/reports/'
W=P+'war-peace-api-20261013/war/'
W2=P+'war-peace-api-20261013-r2/war/'
W3=P+'war-peace-api-20261014-r3/war/'
S=P+'war-peace-api-20261014-r3/sink/'
T=P+'war-peace-api-20261014-r3/sender/'
P3=P+'war-peace-api-20261014-r3/peace/'
P4=P+'war-peace-api-20261015-r4/peace/lifecycle/'
P2=P+'war-peace-api-20261013-r2/peace/'
P1=P+'war-peace-api-20261013/peace/'
OWN=P+'native-owned-peace-1375.json'
GUI=P+'native-peace-gui-send-1375.json'
R18=P+'war-peace-api-20261015-r18-body-probe-contract/war/body-probe-contract.json'
LIVE=P+'frida-owned-body-live-review-20261015-r1/independent-file-audit.json'
documents={}; sources={}; entries=[]


def pin(path):
    raw=path.read_bytes(); assert len(raw)<=4*1024*1024
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def document(path):
    if path not in documents:
        raw=(ROOT/path).read_bytes(); assert len(raw)<=4*1024*1024
        documents[path]=json.loads(raw); sources[path]=pin(ROOT/path)
    return documents[path]


def ref(path,pointer):
    value=document(path)
    for part in pointer.split('/')[1:]:
        part=part.replace('~1','/').replace('~0','~')
        value=value[int(part)] if isinstance(value,list) else value[part]
    return dict(path=path,json_pointer=pointer,**sources[path])


def finding(path,identifier):
    data=document(path)
    key='findings' if 'findings' in data else 'facts'
    index=next(i for i,row in enumerate(data[key]) if row['id']==identifier)
    return ref(path,'/'+key+'/'+str(index))


def op(name):
    return next(row for row in document(P3+'adapter-contract.json')['operations'] if row['name']==name)


def op_ref(name):
    rows=document(P3+'adapter-contract.json')['operations']
    return ref(P3+'adapter-contract.json','/operations/'+str(next(i for i,row in enumerate(rows) if row['name']==name)))


def add(identifier,rva,title,summary,evidence,*,aliases=(),args=(),returns='unknown',owned=(),borrowed=(),
        unresolved=('实际外部调用所需身份、寿命与异常边界未全部闭合。',),sites=(),kind='function',
        stage='static',stage_scope='固定二进制的静态合同；没有该端点的实机 API 效果验收。',signature_status='partial_static'):
    family=identifier.split('.')[0]
    actions=['declare_war','peace'] if family=='shared' else [family]
    entries.append(dict(id=identifier,actions=actions,title=title,summary=summary,
        aliases=sorted(set(aliases)),kind=kind,rva=rva,
        signature=dict(status=signature_status,parameters=list(args),returns=returns,
                       complete_prototype='unknown'),
        call_sites=[dict(rva=a,relationship=b) for a,b in sites],
        ownership=dict(owned=list(owned) or ['unknown'],borrowed=list(borrowed) or ['unknown']),
        stage=stage,stage_scope=stage_scope,unresolved=list(unresolved),
        evidence=evidence,callable=False,native_ready=False,sender_authorized=False,
        gameplay_effect_verified=False,process_authenticated=False))


def build():
    wf=lambda name:finding(W+'findings.json',name)
    sf=lambda name:finding(S+'findings.json',name)
    pf=lambda name:finding(P3+'findings.json',name)
    lf=lambda name:finding(P4+'findings.json',name)
    identity=ref(W+'api-contract.json','/native_identity')
    add('declare_war.factory','0x35d210','宣战通用工厂','token293b选择case35d32a；工厂默认句柄/日期不是可用请求。',
        [identity,wf('declare_war_factory_and_constructor')],aliases=['declarewar_factory'],
        owned=['case分配0x98 action'],unresolved=['通用工厂完整可调用签名 unknown；默认字段不可作正常请求。'])
    add('declare_war.factory_case','0x35d32a','宣战工厂分支','这是已证分支块地址，不是独立可调用函数。',
        [identity,wf('declare_war_factory_and_constructor')],kind='basic_block',signature_status='unknown',
        sites=[('0x35d399','分支中的 constructor call')])
    add('declare_war.constructor','0x500480','宣战动作构造','初始化0x98 action；nonnull goal仍调用d9aaf0，并非直接保存输入。',
        [ref(W3+'api-contract.json','/constructor'),ref(P+'war-peace-api-20261015-r17-owned-goal-independent-review/war/profiles.json','/rejected_ctor_profile')],
        aliases=['declarewar_ctor','宣战构造','war_ctor'],
        args=['RCX=action storage','RDX=actor full country handle','R8=target full country handle',
              'R9B=internal stability flag','entry RSP+0x28=date DWORD','entry RSP+0x30=goal pointer'],
        owned=['caller提供0x98 storage；三个vector初始为空'],borrowed=['输入goal与其definition；NULL分支取2340030 sentinel'],
        sites=[('0x35d399','工厂构造调用')],unresolved=['输入goal不可用手写definition替代；完整构造/异常/借用寿命未验收。'])
    add('declare_war.body_destructor','0x500560','宣战 body：已实采 raw ABI 子范围',
        'R19仅一次自有A98/G60 raw ABI test double正常返回，最终A0=base+1c3e578，其余A/G不变；不等于合法C++析构。',
        [ref(R18,'/top_level'),ref(R18,'/owned_storage'),ref(R18,'/postconditions'),ref(LIVE,'/native_call_accounting'),ref(LIVE,'/owned_raw'),ref(LIVE,'/limits')],
        aliases=['war_body','body_dtor','raw_body_probe','原生body','500560_raw'],
        args=['RCX=A pointer；实采仅独占152B A与96B G test double'],returns='该 raw probe 使用 void(pointer)，不以返回标量判成功',
        owned=['R19仅自有A98/G60；全量pre/post raw比对'],borrowed=['R19此选定路径只引用已校验模块code/vtable；无world sentinel slot'],
        stage='real_rawbody_postcondition',stage_scope='仅R19已审1次顶层尝试/正常wrapper返回的owned raw postcondition；嵌套helper未动态计数。',
        signature_status='raw_probe_only',unresolved=['不是合法C++对象、constructor等价、完整生命周期或宣战效果。','不证明world/header/module lease、TLS/xstate或异常展开；不允许复测。'])
    life=P+'war-peace-api-20261015-r6/war/lifecycle-contract.json'
    add('declare_war.deleting_destructor','0x500520','宣战 deleting wrapper','调用body；flagbit0决定是否释放0x98外层。',
        [ref(life,'/abi'),ref(P+'war-peace-api-20261015-r17-owned-goal-independent-review/war/profiles.json','/complete_retained_functions/1')],
        aliases=['war_delete'],args=['RCX=完整action','EDX=deleting flag'],owned=['完整action及条件拥有的goal/vectors'],
        borrowed=['非拥有sentinel/definition必须保持有效'],unresolved=['R19没有调用此wrapper/free；完整native lifetime未实测。'])
    add('declare_war.clone','0x50b8f0','宣战动作克隆','分配独立0x98 action，复制goal与三组句柄vector；共享sentinel与独占goal须区分。',
        [ref(life,'/abi'),wf('declare_war_goal_and_vector_ownership')],aliases=['war_clone'],
        args=['RCX=完整source action'],returns='RAX=独立拥有的action clone',owned=['新action与vector buffers；具体goal可能独占'],
        borrowed=['source action、goal definition；noCB共享sentinel'],unresolved=['分配失败/new-handler/异常及definition寿命仍未闭合。'])
    for name,rva,title in [('local_check','0x508db0','宣战局部检查'),('full_check','0x50a0a0','宣战完整检查')]:
        add('declare_war.'+name,rva,title,'local/full具有不同职责；检查会解析当前国家和可变engine状态，不能视为任意线程纯查询。',
            [ref(W3+'api-contract.json','/checks'),wf('declare_war_check_boundaries_and_engine_context')],
            aliases=['war_local80' if name=='local_check' else 'war_full88'],args=['RCX=完整action','RDX=optional native reason string'],
            returns='bool；不代表AI接受/效果/持久化',borrowed=['国家、关系、CB/goal及动态条件'],
            unresolved=['完整传递callee/脚本、context和生命周期未知；额外参数未在本记录补猜。'])
    add('declare_war.goal_clone','0xd9aaf0','宣战目标复制/默认目标选择','通过goal virtual58及definition+38分派；NULL及特定enum返回共享sentinel。',
        [ref(W3+'api-contract.json','/tiers/1'),wf('declare_war_goal_dispatch_uses_definition_enum')],
        args=['RCX=goal pointer（NULL有已证默认分支）'],returns='goal pointer；可能是共享sentinel',
        owned=['具体enum0..10可能产生0x60 goal clone'],borrowed=['goal/definition/CB及共享sentinel'],
        unresolved=['definition身份和生命周期；enum本身不是合法外部goal描述。'])
    add('declare_war.gui_send','0xedfa40','普通宣战 GUI 发送回调','更新日期，通过action+40包装command，再直接调用14ca210。',
        [finding(W2+'findings.json','ordinary_declare_war_wrapper_sender_consumes_container')],
        args=['RCX=原生dialog（完整签名 unknown）'],sites=[('0xedfb96','action virtual40'),('0xedfba4','直接sender调用')],
        owned=['dialog缓存action与新command具有不同生命周期'],borrowed=['真实dialog/context/world'],
        unresolved=['正常GUI静态调用链不是可外部派发的TAG接口。','transport返回不等于效果；失败不允许重试。'])
    add('shared.wrapper','0x4e9930','动作包装为拥有式 command','调用action clone+b0，command+50拥有独立clone，并更新clone次日期。',
        [ref(GUI,'/facts/wrapper_clones_whole_owned_offer'),wf('declare_war_wrapper_owns_distinct_clone')],
        aliases=['command_wrapper'],args=['RCX=action','RDX=caller command holder'],returns='caller holder地址',
        owned=['0x58 command与独立action clone'],borrowed=['source action与当前game date'],
        sites=[('0x130f307','peace GUI直接调用wrapper'),('0xedfb96','war GUI virtual40调用')])
    add('shared.sender','0x14ca210','command 发送器','先清caller holder，再按context/transport条件提交；true仅表示本地transport返回。',
        [ref(P3+'adapter-contract.json','/sender'),ref(GUI,'/facts/submit_consumes_container_not_acceptance_ack')],
        aliases=['sender','send_command'],args=['RCX=context','RDX=caller owning command holder'],returns='bool；非执行/接受证明',
        owned=['进入时消费caller holder；正常transport对original command另有清理'],borrowed=['context+58 transport与世界'],
        unresolved=['false/异常后的完整所有权未知；不得据返回值重试或释放。'])
    add('shared.transport_submit','0x1580370','已证 transport virtual30','固定vt1d96178的+30端点；序列化/重新构造队列command，正常路径清理原command。',
        [finding(T+'findings.json','sender_r3_specific_transport'),finding(T+'findings.json','sender_r3_original_command_normal_destruction'),finding(T+'findings.json','sender_r3_reparsed_queue_command')],
        args=['unknown'],owned=['原command正常completion删除；队列使用重解析对象'],borrowed=['transport/recipient队列'],
        unresolved=['完整原型 unknown；动态类型、失败、异常与接受语义未闭合。'])
    add('shared.queue_consumer','0x15801c0','transport 队列首消费者','virtual38取队列command、克隆wrapper进入pending链，再删除旧wrapper。',
        [finding(T+'findings.json','sender_r3_first_queue_consumer')],owned=['新pending wrapper与旧队列wrapper分离'],
        borrowed=['transport队列/pending链'],unresolved=['完整签名 unknown；异常所有权与执行时序未知。'])
    add('shared.pending_handoff','0x14ca870','pending 到执行 context 的移交','从transport容器移交raw command到context vector，仅释放链节点。',
        [sf('war_sink_pending_handoff')],aliases=['sink','pending_sink'],owned=['command指针从pending链移入context vector'],
        borrowed=['context/transport'],sites=[('0x14ca927','已保留移交现场')])
    add('shared.command_gate','0x4e8630','command 检查槽','command+40检查cooldown/cost/local，true后才进入执行；gate本身不调用action效果。',
        [sf('war_sink_gate_is_not_execution')],returns='bool',sites=[('0x14cab30','context调用gate')],
        borrowed=['command/action与当前engine状态'])
    add('shared.command_execute','0x4e7c50','command 执行槽','command+48重新做local80，再经4ea820分派action效果。',
        [sf('war_sink_action_apply'),sf('war_sink_native_execution_holder')],aliases=['command_execute'],
        args=['RCX=command；其余参数 unknown'],sites=[('0x4e8054','调用4ea820')],borrowed=['command+50 action/world'],
        unresolved=['效果前后动态调用与异常未知；此记录不提供执行能力。'])
    add('shared.action_apply','0x4ea820','公共动作效果分派','先检查国家存在，再调用action+48；不是外部合法性预检入口。',
        [sf('war_sink_action_apply')],sites=[('0x4ea8cd','action virtual48分派')],borrowed=['action、country/world'])
    add('declare_war.effect','0x501290','宣战效果入口','费用及legacy回调发生在创建war之前；失败不是事务回滚。',
        [wf('declare_war_effect_writes_before_war_creation'),sf('war_sink_first_world_commit')],aliases=['war_effect'],
        args=['RCX=declarewar action；完整签名 unknown'],owned=['新0x218 war；未提交join失败分支删除'],
        borrowed=['country、goal/definition、关系、脚本及game'],
        unresolved=['不得作为预览/检查；真实宣战效果、完整动态callee和异常边界未验收。'])
    add('declare_war.war_constructor','0xd859b0','战争对象构造','建立0x218 war、clone goal到+160，并写goal+48回指；共享noCB回指不是独占war身份。',
        [sf('war_sink_goal_backpointer'),sf('war_sink_no_cb_backpointer_alias')],owned=['0x218 war与条件拥有goal'],
        borrowed=['输入goal/definition；共享sentinel可能保持alias'])
    add('declare_war.commit_site','0x501921','首次全局战争提交调用现场','两方加入成功后，此CALL调用c06d0把war指针追加到game+1e28。这是callsite，不是函数入口。',
        [sf('war_sink_first_world_commit')],aliases=['commit','war_commit'],kind='callsite',signature_status='unknown',
        sites=[('0x501921','call c06d0')],owned=['提交的war指针'],borrowed=['当前game容器'],
        unresolved=['前序费用可能已发生；单个append不能证明完整效果/持久化。'])
    add('declare_war.global_append','0xc06d0','全局战争数组追加 helper','501921调用的具体数组追加端点，关联game+1e28容器。',
        [sf('war_sink_first_world_commit')],sites=[('0x501921','直接caller')],args=['unknown'],returns='unknown',
        owned=['war指针容器；外层war寿命另论'],borrowed=['当前game'],unresolved=['完整helper函数签名 unknown；不提供通用append调用。'])
    for name,title,operation in [('offer_constructor','议和 offer 构造','offer_ctor'),('request_constructor','议和 request 构造','request_ctor'),
        ('request_clone','议和 request 克隆','clone'),('local_check','议和 local80','local80'),
        ('full_check','议和 full88','full88'),('date_check','议和独立 date90','date90'),
        ('request_destructor','议和 request deleting wrapper','original_dtor0'),('offer_cleanup','议和 offer 清理体','offer_cleanup'),
        ('offer_reset','议和 offer 选择重置','reset')]:
        item=op(operation)
        summary={'offer_constructor':'构造0x1c0 offer并枚举候选；actor/taker与recipient/giver方向明确。',
            'request_constructor':'构造0x210 request，深拷贝offer到+48，force+208为0。',
            'request_clone':'分配独立0x210 request及嵌入offer拥有图。',
            'local_check':'局部检查包括有效type3领土owner/controller；不能替代所有条款合法性。',
            'full_check':'公共/local检查后还拒绝pending enforce_peace；与date90分开。',
            'date_check':'当前date必须严格大于相关国家/player日期；full88成功不替代此检查。',
            'request_destructor':'先清嵌入offer图，flagbit0决定是否释放0x210外层；不能单独删嵌入offer。',
            'offer_cleanup':'清拥有components/容器；保留caller外层storage。',
            'offer_reset':'原生取消/重置选择；不是任意手写selected byte。'}[name]
        extra=[]
        if name in ('local_check','full_check','date_check'):
            key={'local_check':'peace_r2_local_province_check_is_type3_only','full_check':'peace_r2_pending_enforce_peace_extra_gate','date_check':'peace_r2_date90_is_independent_strict_gate'}[name]
            extra=[finding(P2+'findings.json',key),ref(P4+'observer-contract.json','/country_root/alias_arithmetic')]
        if name=='request_destructor':extra=[op_ref('clone_dtor1')]
        args=item['args'] if name!='request_destructor' else ['RCX=完整request','EDX bit0=是否释放外层；0与1对应不同所有权']
        owned=[item.get('owns','offer/request内部拥有图；具体范围见所选合同')]
        if name=='request_destructor':
            owned=['静态正常路径（非运行验证）：embedded offer cleanup 后，EDX bit0=0 preserves caller outer storage。',
                   '静态正常路径（非运行验证）：embedded offer cleanup 后，EDX bit0=1 frees engine outer 0x210。']
        add('peace.'+name,item['rva'],title,summary,[op_ref(operation)]+extra,
            aliases={'date_check':['peace_date90','date90'],'request_constructor':['requestpeace_ctor'],
                     'offer_constructor':['offer_ctor'],'full_check':['peace_full88'],'local_check':['peace_local80']}.get(name,()),
            args=args,returns=item['return'],owned=owned,
            borrowed=['双方country/full handle、当前war、条款definition与其引用对象'],
            unresolved=['已知referent范围不等于完整传递world拥有图；生命周期/动态effects/异常未闭合。','R3 ABI编译或离线case不是本版真实peace调用/效果证据。'])
    add('peace.offer_copy','0x975f40','议和 offer 深拷贝','复制独立participant vectors/hash/component图，修正owner+self；memcpy会形成别名。',
        [ref(OWN,'/facts/offer_copy_and_owner_fixup'),pf('P02_independent_graphs_and_destruction')],
        args=['RCX=destination offer','RDX=source offer'],owned=['独立destination拥有图'],borrowed=['source及其定义/世界引用'],
        sites=[('0x598b4a','request constructor调用'),('0x59bad1','request clone调用')])
    add('peace.gui_send','0x130f1b0','议和 GUI SEND_OFFER 回调','选定GUI offer深拷贝为request，独立日期gate后包装发送，再清原request；三个offer图独立。',
        [ref(GUI,'/facts/send_button_binding'),ref(GUI,'/facts/callback_allocates_original_and_copies_selected_offer'),ref(GUI,'/facts/native_date_gate_and_context_lookup')],
        aliases=['peace_send','SEND_OFFER'],args=['RCX=原生GUI owner；其余参数 unknown'],
        owned=['GUI offer、original request offer、command clone offer各自拥有'],borrowed=['GUI/context/world'],
        sites=[('0x83643d','listener tailcalls owner callback'),('0x130f22f','调用request ctor')])
    for name,rva,title,summary,args in [
        ('term_check','0x97a1c0','议和候选条款检查','读取当前war且没有null保护；必须属于当前原生offer的候选。',['RCX=offer','RDX=component','R8=已初始化diagnostic vector','R9B=false','stack5=null reason']),
        ('term_select','0x97a790','议和条款选择','没有完整合法性/归属/重复检查；非幂等，不得重复加入。',['RCX=offer','RDX=component','R8B=false','R9B=false']),
        ('term_cancel','0x97a8d0','议和条款取消','可能级联取消并重查其它领土条款，不删除component拥有体。',['RCX=offer','RDX=component','R8B=false','R9B=false'])]:
        add('peace.'+name,rva,title,summary,[finding(P1+'findings.json','peace_gui_selection_checker_abi'),finding(P1+'findings.json','peace_selection_not_idempotent_or_owning')],
            args=args,owned=['offer拥有pool；type buckets只存别名'],borrowed=['候选component及当前war/definition'],
            unresolved=['动态virtual check/update与异常未知；完整return ABI未补猜。'])
    add('peace.reply_effect','0x598ed0','议和请求响应效果','state2分支到59a6ea调用976730；禁止通过改state/force伪造接受。',
        [pf('P05_accepted_reply_to_effect'),lf('L07_on_action_has_synchronous_dynamic_effects')],
        args=['RCX=request action；其余参数 unknown'],borrowed=['offer/current war/countries/动态脚本'],
        sites=[('0x59a6ea','accepted分支调用offer apply')],unresolved=['on-action有同步动态effect；完整异常/重入/world寿命未闭合。'])
    add('peace.offer_apply','0x976730','议和 offer 应用/结算','应用条款并移除适用参战者；outcome写入不是war已释放的证明。',
        [pf('P06_whitepeace_zero_gold_application'),pf('P07_native_member_removal_and_terminal_mark'),lf('L06_outcome_is_serialized_state_not_lifetime_flag')],
        args=['offer receiver；完整参数/return unknown'],borrowed=['war、participants、条款引用对象'],
        sites=[('0x59a6ea','request effect直接调用')],unresolved=['只零金额gold叶有窄不转账证据；完整结算/其它条款/最终retirement未验收。'])
    add('peace.remove_members','0x98ffb0','议和结算参战者移除','调用d8ba80/d8e6b0及side-vector移除；不等同最终war释放。',
        [pf('P07_native_member_removal_and_terminal_mark'),lf('L03_bilateral_index_erasure_not_war_free')],
        sites=[('0x9784cc','offer apply caller')],borrowed=['resolved war、countries与双方物理索引'])
    add('peace.ai_score','0x59bee0','议和 AI score 槽','virtual120含特殊override；普通fallback1bf150，不能把score当实际接受回执。',
        [pf('P04_AI_response_ordinary_boundary')],returns='score；普通接受predicate以>=1为阈值',
        borrowed=['request/current AI/world'],unresolved=['1bf150具体接受规则/理由对象寿命 unknown；未实采。'])
    add('shared.war_body_retirement','0xd85c40','战争 body 清理与全局移除','移除全局数组和借用链节点，继续goal/container清理；节点延迟删除不保活war。',
        [lf('L04_actual_global_retirement_and_deleting_destructor')],args=['RCX=完整war；完整原型 unknown'],
        owned=['war goal/容器按其正常拥有条件清理'],borrowed=['game数组/list、manager borrowers与goal'],
        unresolved=['普通accepted-whitepeace最终调用者/时点仍unknown；不能作liveness probe。'])
    add('shared.war_deleting_destructor','0xd85960','战争 deleting wrapper','调用d85c40，flagbit0决定是否释放0x218 outer。',
        [ref(P4+'observer-contract.json','/war'),lf('L04_actual_global_retirement_and_deleting_destructor')],
        args=['RCX=完整war','EDX=flagbit0'],owned=['0x218 war及条件拥有图'],borrowed=['完整有效world/goal图'],
        unresolved=['外部destructor未授权；不能在调用后沿用旧war pointer。'])
    add('peace.clear_all','0x7496c0','全局战争 clear-all 路径','收集wars、移除参战者、清理borrower节点后调用war virtual0(1)。',
        [lf('L05_clear_all_path_cleans_borrowers_before_war_delete')],borrowed=['game/manager/country图'],
        unresolved=['不是普通白和平最终retirement scheduler证明；完整签名 unknown。'])
    # Context corrections are indexed as evidence, never as callable gates.
    corrective=ref(P+'war-peace-api-20261015-r5/peace/adapter-contract.json','/scope')
    for entry in entries:
        if 'peace' in entry['actions']:entry['evidence'].append(corrective)
    entries.sort(key=lambda row:row['id'])
    assert len({row['id'] for row in entries})==len(entries)
    assert all(row['callable'] is row['native_ready'] is False for row in entries)
    doc=dict(schema='EU4-WAR-PEACE-OFFLINE-INDEX/1',version='1.37.5',game_sha256=SHA,
        scope='research_endpoint_lookup_only',not_a_callable_API=True,
        family_aliases={'declare_war':['declarewar','declare_war','war','宣战'],
                        'peace':['peace','requestpeace','request_peace','议和']},entries=entries)
    for name,value in [('index.json',doc)]:
        with (HERE/name).open('x',encoding='utf-8',newline='\n') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')
    manifest=dict(schema='EU4-WAR-PEACE-LOOKUP-DATA-MANIFEST/1',version='1.37.5',game_sha256=SHA,
        scope='offline_selected_evidence_only',index=pin(HERE/'index.json'),sources=dict(sorted(sources.items())))
    with (HERE/'data-manifest.json').open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(manifest,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(entries=len(entries),sources=len(sources),manifest=pin(HERE/'data-manifest.json'))))


if __name__=='__main__': build()
