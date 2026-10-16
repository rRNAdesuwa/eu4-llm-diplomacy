v2 源码及六个新fake完成，候选仍禁止真实status。

六个新fake全部通过。首次check在文件读预算前置检查返回unknown/exit2；catalog未执行，批次停止且没有重试。两个Job均active=0、direct child已收齐。冻结direct来源链另外反复整读既有约4.04MB和1.84MB反汇编JSON，未包含在最初host215+11流式估算里；实际普通读取尚未越64MiB，但下一次原read(16MiB+1)的保守预留不够。该拒绝来自新离线meter，不是已发现的candidate语义/来源错误。不能把本批次称全部通过；后续文件验证需另定有限范围。没有真实status、游戏/PE读取、旧31方法或原请求重发。

唯一采样变化是将233e064的未证signed -1条件改为相同共享4B读取和每遍raw/i32/u32诊断；两遍完整样本相等覆盖此字段。稳定-1与1都可在其它结构检查成立时得到当前队列结果；1→2、短读和tombstone仍unknown。23个既有函数/类AST保持，源与结果schema版本元数据变为2。

旧host215+11固定文件hash闭包单独流式计账，不运行其Frida/main，也不把这些二进制文件hash当游戏访问。本次只完成三遍host哈希，实际767,484,426B=3×255,828,142B；原八遍2,046,625,136B只是计划，不冒称已读。精确requested/returned/EOF/refusal、source前后、Job和fake raw日志见offline-r1。

字段语义、通用Mod兼容及真实v2队列仍unknown。所有原请求效果、AI接受/拒绝、议和完成、native/lease/atomic/persistence权限false；v1历史不修改，原48/44/42和稳定15profiles保持。
