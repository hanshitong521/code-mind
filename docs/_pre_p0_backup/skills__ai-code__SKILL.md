---
name: ai-code
version: 7.0.0
description: >-
  /ai-code only. L-DO 纯实现器: TDD→CONTRACT→LOCATE→REUSE→DELETE→IMPLEMENT→LEAN REVIEW→VERIFY→CHANGE MANIFEST.
  WHAT=FROZEN; HOW=Handoff; CTX=orient+TaskBundle. 吸收TDD纪律+verification铁律.
disable-model-invocation: true
---
encoding:../../shared/core.md
trig:/ai-code prio:rules>this load:本页 ref命中单读 禁ref批
axiom:evidence>falsify>premise stated accept measurable 本期做|明确不做
ssot:../../shared/core.md contract:../../shared/core.md
paradigm:TDD先行>负代码DELETE>REUSE>SIMPLIFY>EXTEND>CREATE|约束终局>逐行人审|判据=G0+Manifest+SELF-CHECK|人价值=闸门测矩阵|仓内无基建禁装
pipeline:Handoff死规矩→TDD Red-Green→负代码门→最小diff→SELF-CHECK→zero-bloat→Manifest→brain摘要
改Java/Mapper前:`get_change_context(file=相对路径)`;踩坑:`save_bug_memory`;收尾:`record_task_outcome`(candidate,见/lessons晋升)

# 核心增强(v7.0)
## 1. TDD纪律(来自superpowers)
- G1新增: 先写失败测试(Red)→写最小实现(Green)→重构(Refactor)
- 铁律: NO PRODUCTION CODE WITHOUT FAILING TEST FIRST
- 但保持ai-code极简: 不强制类组织,允许函数级测试

## 2. Verification铁律(来自verification-before-completion)
- G4强化: EVIDENCE BEFORE CLAIMS - 未Fresh跑验证禁宣称完成
- 五步法: IDENTIFY命令→RUN全量→READ输出→VERIFY宣称→CLAIM附证据
- 禁"should/probably/看起来对",必须cmd+exit或SELECT摘要

## 3. Systematic Debugging集成(替代独立/ai-debug)
- G2增强: 遇bug走P0-P6循环(OBSERVE→REPRODUCE→LOCALIZE→HYPOTHESIZE→DISPROVE→ROOTCAUSE→FIXCONTRACT)
- 铁律: NO FIXES WITHOUT ROOT CAUSE
- 但保持简洁: 不强制写debug报告,根因一句话+证据即可

G-pre:ssot0错前提STOP;FROZEN≠代码→BLOCKER回RM禁私裁

G0:改|不改|完成判据?否→/ai-design;消费Handoff范围+验证档位;OoS禁做;micro可无Handoff须1行判据

G1:TDD RED→写最小测试(一行为)→运行必失败→确认失败原因正确
   orient/codegraph1次同轮禁再Read;SQL grep;reuse;新建文件/方法/依赖过lean四问门→lean-gate;契约字面量;排序钉;过滤状态→扫读者;≥2独立子面→并行explore/shell禁同文件写;micro禁Task

G2:TDD GREEN→写最少代码让测试通过→YAGNI不添加额外功能
   数据证伪;false-alarm先;证伪→test_to_design禁改码;遇bug→systematic-debugging P0-P6

G3:Handoff范围;状态/过滤→扫读者;禁删口径;宁新列;禁静默丢;合并替入口→删死码+grep引用+同步契约;仅用户留兼容才双轨(须删除条件+期限);touch-clean触及区死码顺带删禁扩面;DB/SSH须接入门

G4:SELF-CHECK=TDD VERIFY→构建+触及单测绿(FRESH RUN);写SQL→探针;性能/索引宣称→执行计划+双向对拍
   verification铁律: IDENTIFY→RUN→READ→VERIFY→CLAIM;未Fresh跑禁完成;zero-bloat提交门→lean-gate;档位对照verification-gate+policy;未绿→回G0;禁自宣完成

G5:CHANGE MANIFEST→change-manifest.md=code_to_test字段 change_id|scope|files|behavior_changed|contracts_changed|data_semantics_changed|assumptions|risk.proposed|self_tests|unverified
   lean块:reused/deleted/bloat/parallel_implementation=yes禁完成

domain-pack:JDK8/ADS→domain-packs/java8/INDEX.md或ads/pitfalls-shejiuPro.md
ship:`改动|验证exit|风险`;Handoff:变更面|plan引用|已跑验证|未跑验证|建议下一步
ref:细则→references/refs.md |栈/假阳性→../../shared/core.md |验证档位→shared/verification-policy.yaml

STOP:错前提|裸✓|有测未跑|幻读|无查询|代跑|过滤仅build|状态一处|猜契约|删口径|未扫读者|筛≠响应|静默丢|回填COUNT|未钉金标|宣称完成无self-check|逐行审替闸门|子代理代ship|并行改同文件|micro开Task|自宣PASS|合并替入口默留双轨|无orient整读ServiceImpl|search_knowledge+build_task_context双开|叠grilling|未过四问建新文件|无业务含义抽方法|语义重复未收敛|IDE灰即删|动态入口未查就删|双轨无删除条件|见慢加索引|性能宣称无对拍|小需求大diff无理由|引库做十几行小事|无Red写Green|无证据宣称|未钉根因修复

link:/ai-design(前提) requirement-mind(BLOCKER) systematic-debugging(难bug) 禁git add.
lex:负代码 复用 简洁 变更面 验证档位 证伪 Handoff 完成判据 单一事实源 深模块 接缝 规则演进 抢跑 ADR 进度披露 场景-行为表 复述 恢复 反馈环 领域语言 TDD Red-Green-Refactor verification iron-law root-cause
