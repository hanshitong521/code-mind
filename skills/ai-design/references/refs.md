# ai-design references (merged)


---
# approaches-and-gates

# approaches gates · PRD写WHAT本文HOW选型
禁进/ai-code:未确认假设验收|≥2解读未选|≥2子系统未拆|YAGNI未过且未写不做|权限组合矩阵非YAGNI是验收最小集 身份×入参矩阵(verification-gate)
micro-fix: typo唯一解读→/ai-code;不适用Mapper tenant filter
bug-micro:现象清晰→bug-micro;难复现无red→/ai-debug
澄清:Explore能答不问|多解读破坏性状态必问|一次一问|大项目先分解|模糊慢贵优化无判据→写前门四问
方案对比≥2模: A推荐优缺点|B|C;用户选定后Implementation;无分歧写无方案分歧;interface分歧→design-it-twice;评深度→deep-modules
plan自检:无TBD|方案一致|OoS含speculative不做|字段Explore|scope对应验收|过滤identity_matrix或na|文档六项本期做不做环境爆炸半径回滚验收SELECT|缺数慢三路证伪|bug-micro七问|新MCP/新文件/新抽象/新依赖→负代码四问(../ai-code/references/lean-gate.md):同职责已存在?为何不能改现有?增概念还是减?可删?全过才建否则进不做;兼容双轨须删除条件+期限
≥5步→implementation-plan-tasks再Handoff


---
# axis-checklist

# axis-checklist · micro typo可只Always
Always|轴|不过则
判据|1行改+完成判据|STOP问或/ai-design
范围|本期做+明确不做|补OoS
证据|Explore字段接口|幻读STOP
宣称|Fresh证据|禁裸✓
层|通用vs项目私货|私货→pitfalls
Trigger|信号|最小动作
状态cron|生命周期|生回流归档硬删边≥1
改谓词过滤汇总|读者|grep读者≥3或抽公共
权限tenant|身份矩阵|无skip无理由
筛列表|响应=请求|验结果列
perf删分支|语义守恒|钉口径对拍
外部指标|金标|公式层未钉禁改码
回填迁口径|多维|每维对拍或OoS
跨端字段|契约字面量|禁UI译名
升skill|distill|≥3跨仓或用户升通用
回流原态|假阳性|false-alarm先于改码
模糊慢贵优化|无SELECT/数字判据|写前门四问后再写
产出:plan→验收或不做;code→验证档位;skill→skill-meta EVOLVE落点


---
# bottleneck-radar

# bottleneck-radar G0 G5
瓶颈问:哪步最慢最依赖人脑=加速它非顺手环;虚假吞吐行数↑上线不变→STOP
阶段|瓶颈
需求|歧义反复
架构|跳过设计返工
评审|AI输出走过场
测试|只happy path
部署|人肉checklist
30%|项|问
1空值|空零超长
2并发|竞态重复提交
3兼容|老接口数据
4权限|越权租户
5日志|可定位
6回滚|炸了怎么退
意图锚G2:唯一目的|改|不改|为什么 3-5句


---
# bug-micro

# bug-micro →/ai-code;难复现→/ai-debug
走:唯一解读或Explore钉|≤1模块|小bug验收|不走:≥2解读未选|跨子系统|无red难复现
问:一次≤2未决;Explore能答不问
Q1金标:入口+身份+期望vs实际|Q2时间:一直/变更后/环境|Q3三路证伪接口事实源|Q4身份矩阵或na|Q5回流vs bug|Q6爆炸半径旁路|Q7验收1命令+明确不做
ship模板:假设|根因Explore证据|本期做|明确不做|改点File#|爆炸半径回滚|验收1-3|identity na|下一步/ai-code|/ai-debug
无分歧:写无方案分歧根因Explore


---
# deep-modules

# deep-modules 词汇
Module|Interface|Implementation|Adapter|Depth深=小interface多behavior|Seam|Leverage|Locality
自检:interface更少方法?|Deletion test删模块复杂度散调用方?|Interface即测试面|One adapter假想Two adapter真seam
依赖:in-process合并测|local-substitutable PGLite|remote-owned port+HTTP|external Stripe mock
测试:replace don't layer;测behavior非implementation
接缝:优先现有最高层理想1个;Testing Decisions写测哪interface
≥2模块interface分歧→design-it-twice


---
# design-it-twice

# design-it-twice · interface形状分歧时
1框约束依赖示意非提案 2并行≥3种interface subagent不同约束最小/灵活/极简/ports 3按depth locality seam推荐可hybrid
禁:未Explore spawn|paste全文进plan|单点bug跳过


---
# domain-language

# domain-language CONTEXT.md · glossary=skill词 CONTEXT=业务词
维护:统一行话→grep复用少token
模板根目录: ##语言 ###术语 定义 避免易混 ##关系 ##已标定歧义
何时更新:新术语|一词多义|改plan前对齐CONTEXT|grill-with-docs
禁:把skill词汇写进CONTEXT|把业务词写进glossary


---
# gate-router

# gate-router · G5 hit→单读;禁ref批
信号|必动作|ref
权限矩阵|identity_matrix=yes;身份×入参|../../ai-code/references/verification-gate.md
状态机全链路|行为表+回流边≥1|lifecycle-expected-vs-bug.md + ../../shared/false-alarm-missed-detection.md
涉库环境回滚|接入门;爆炸半径|bottleneck-radar.md
筛证伪|筛=响应;对照主键|../../ai-code/references/common-pitfalls.md
契约字面量|调用方原样;禁UI译|why-incomplete.md W7
排序|字面量待确认|pitfalls P29→ai-code
对拍/金标|钉金标+公式层|verification-gate 外部对齐
共享列|读者清单|why-incomplete W4
侧效|主成功⇒下游行|pitfalls P34
回填|多维对拍|W6/P35
缓存|失效键与读者|axis-checklist
外部金标矩阵|未钉禁改码|金标
interface分歧|≥2模形状|design-it-twice.md
≥2模块深度|deletion test|deep-modules.md
≥5task|拆任务|implementation-plan-tasks.md
现象清晰小bug|七问|bug-micro.md
难复现无red|/ai-debug|STOP本skill
模糊慢贵无判据|写前门四问|axis-checklist
过滤/状态/排序/perf|验证档位≥surface|handoff-template.md
新MCP/新抽象/新依赖|复用grep+谁维护+可删|../../ai-code/references/reuse-patterns.md
命中升档|verification_escalation=yes|../../../verification-policy.yaml


---
# handoff-template

# handoff · 契约→shared/handoff-schema.yaml validate_handoff.py
禁文件路径行号;引用@plan不贴全文;脱敏;建议下一步枚举{/ai-design,/ai-code,/ai-debug,无}
stated可写:用户原话|Explore所见|调用方字面量|用户选的方案
须标待确认:模型补全|UI翻camelCase|惯例推测|无字面量白名单
design→code必填:变更面 plan路径 范围 验收 验证档位 建议下一步 |选:假设 待代码确认 规则演进 接入门 identity_matrix verification_escalation
design→test必填:plan路径 只验SQL或含API 测试库写操作 建议下一步 |选:基址 夹具 接入门
code→test必填:变更面 plan引用 已跑验证 未跑验证 建议下一步 |选:改动文件 验证写库恢复 剩余风险 规则演进 接入门 identity_matrix
test→design必填:结论(SQL证伪|SQL证实Bug|全部PASS) 证据 建议 建议下一步 |选:数据恢复结果 接入门
分流:L1绿再升档;未跑验证=只补所列维
验证档位enum:micro-fix local-fix surface pr-ready release

## 示例（design_to_code · 校验用）

```yaml
# 设计 Handoff → 编码 / design_to_code
变更面: backend/api
plan路径: "@docs/plan/foo.plan.md"
范围: 模块X 表Y 接口Z
验收: 验收表 #1-#3 可独立测
验证档位: surface
建议下一步: /ai-code
```


---
# implementation-plan-tasks

# implementation-plan ≥5步或跨模块
micro单点→ai-design简版;本文多任务subagent
头必填:Goal Architecture TechStack GlobalConstraints 建议执行方式subagent或单会话
任务:一步2-5分钟可验证;末步verify mvn pytest SELECT;配置并入服务任务
单任务:行为契约输入输出依赖前序|verify cmd|Step checklist
禁:TBD implement later|无断言覆盖|无verify
TDD仅用户要求;默认compile SELECT /ai-code
Handoff:@plan路径 任务数N 验证档位 下一步/ai-code


---
# lifecycle-expected-vs-bug

# lifecycle vs bug · SSOT shared/false-alarm-missed-detection.md F1-C1
本文件不维护特例;状态机回流边按SSOT C1 F1


---
# prd-template

# prd-template 复制填空
节:Problem Statement用户视角|Solution用户视角|User Stories角色能力价值
Implementation Decisions:模块|状态机|API契约|数据表字段|复用清单grep|新建项理由|DB方言|架构对齐;禁文件路径
Testing Decisions:测外部行为|接缝草图优先现有最高层理想1|deep-modules词汇|runner名|验收表列# 项 场景id 验证 skip
Out of Scope|Further Notes待确认风险


---
# why-incomplete

# why-incomplete W1-W12 · 写前对照
W1|happy path|无OoS无回流|OoS+生命周期边
W2|层搞混|本仓写进通用|通用模式项目pitfalls
W3|一例升STOP|疼一次绑死|≥3跨仓才升
W4|只改写口|未扫读者|读者清单或新列surface
W5|身份单维|一种角色|身份×入参矩阵
W6|空完成|裸✓compile|cmd+exit或SELECT
W7|契约猜名|UI当wire|调用方字面量
W8|提速删语义|删公式兜底|对拍删口径=改产品
W9|错前提|谄媚|公理0拆
W10|口号门禁|散文|GATE/STOP可执行
W11|平行skill膨胀|每疼新建|ponytail+gates组合
W12|假阳性|回流当bug|false-alarm先
社区对照:skill-meta/references/forum-distill.md
禁:通用主文写mvn ads-sql P37全文|无不做Handoff|优化删口径|单次事故通用STOP
