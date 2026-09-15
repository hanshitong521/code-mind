# gates · 证伪 / 验证 / 交付（命中才读）

---
# debug

# systematic-debugging · 循环 SSOT = SKILL.md DBG；本文不另起编号
P0环:单测|SELECT|curl|CLI|playwright|replay|harness|fuzz|bisect|diff;收紧快尖稳;非确定→提repro率;建不了→列尝试+artifact禁改码
P0.1投喂:复现步骤|预期|实际|原始日志|范围;缺项禁盲改
P0.5假阳性:回流F1|看错列F2|库无id F3|写日志F4-5|乐观F6-7→shared/core 假阳性;未过禁方言/CAST修
D2补:只看最终文件不够; git show HEAD --path; 全栈grep callers choke修一次
D4补:一次一假设;一变+log前缀DEBUG;证伪回D3禁连续补丁
D6后:G1最小red;修完清DEBUG/harness;失败禁扩diff
分工:SELECT证伪设计→G4探针;证实改Mapper→G1;造数须用户授权;根因=设计缺陷→/ai-design
禁:未复现改|多假设并改|症状patch不查空因|无red就修|手抄旧版|独立debug skill第二套正文

---
# verify

# verification-gate · 宣称证据
范式:Agent产出=草稿;质量由可执行闸门裁决,非人眼逐行读码
## tier
|档|必跑|适用|
|m|lint/format|纯文案/注释无行为|
|l|build+触及单测+写SQL探针|默认业务改码|
|s|l+身份/状态/过滤矩阵或SELECT对拍|tenant/状态机/排序/共享列|
|p|s+一条API/E2E或回放金标|PR-ready/对外契约|
未达设计交付档位→禁 ship|升档→../../shared/verification-policy.yaml
铁律:未Fresh跑禁完成|有测未跑触及单测禁完成|写SQL未探针禁SQL可执行|MCP只读须node/CLI探针|仅回填UPDATE≠INSERT探针|禁裸✓须cmd+exit或SELECT摘要|无轨迹禁PASS|L1未绿禁PR-ready
五步:IDENTIFY→RUN→READ+exit→VERIFY→CLAIM附证据
宣称|证据|非证据
测过|0 fail exit0|上次跑过/裸✓
触及单测绿|过滤包/类 exit0|仅compile
Bug修|原步骤+验证|看起来对
过滤权限|身份矩阵+SELECT|仅compile
SQL可执行|INSERT SELECT DELETE同形或UPDATE+回查|只读XML
状态机|grep字段全mapper对齐|只改一条SQL
更快|baseline同窗对拍|只更快无对拍
筛选|响应状态=请求值+对照主键|只total>0
回填口径|身份维+A−B差集|只COUNT
外部对齐|金标+公式矩阵每层|只终值接近
侧效|主成功⇒下游行|仅API200
人审:档位l绿+ship Fresh → 不必逐行。必须人眼:权限/金钱/PII|新对外契约无测|跨模块接缝|用户要review
禁:「我读过了」替未跑闸门|信子agent|让用户测SQL

---
# manifest

# change-manifest · 交付=code_to_test;禁散文完成
必填:变更面|plan引用|已跑验证|未跑验证|建议下一步
lean块每次必填: reused_* | removed_*(空则`none:`+grep)| new_* | complexity_*+justification | lean_verdict | parallel_implementation=yes禁完成
plan引用:`@path.plan.md`或`@docs/diagram/design.md`
已跑:cmd+exit或SELECT摘要。未跑:无|维:原因
建议下一步: /ai-design|/ai-code|无
contracts_changed=yes→breaking表+用户确认;纯新增=additive
ship三行外可贴yaml; `python scripts/validate_handoff.py`

```yaml
变更面: backend/api
plan引用: "@docs/diagram/design.md"
已跑验证: "mvn -pl m -am test -Dtest=FooTest -q exit=0"
未跑验证: 无
建议下一步: 无
identity_matrix: na
verification_escalation: na
```

# delivery-report · 用户要PR才展开§1-7;默认用 SKILL ship 行
must:改码|SQL未验证禁标题完成
§1用户收益 §2 diffstat新建/复用 §3证伪+lean+compile+探针 §4写路径INSERT→SELECT→DELETE或UPDATE回查 `__AI_TEST__` §5风险 §6规则自检 §7速查一行

---
# rigid

# rigid-validation · 大规模重构/双实现/桥接
独立内核绿≠桥接绿。禁「compile+自拟清单」当验收。
刚性(按可得性):旧测迁新0 fail|测不可为绿改期望|固定seed状态对拍|金标回放|一条真实E2E cmd+exit
开写前:旧测全列入?对拍谁生成?桥接谁验?测文件受保护?判据可机检? 任一否→/ai-design
柔性仅:原型/文档/非行为UI草稿

---
# review

# code-review · 先过 verification-gate
双轴:Standards=AGENTS/lint · Spec=plan/scope creep;分开报
有 ocr 走其六步;无则 `git diff` 双轴手工注 OCR❌
Critical直改(用户要fix时)|Important描述|Minor有价值才报
禁:未pr-ready就review|review替compile
