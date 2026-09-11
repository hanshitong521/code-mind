---
name: ai-design
version: 5.0.0
description: >-
  /ai-design only. L-HOW: 精简Handoff+TDD规划+systematic-debugging前置. WHAT=RequirementMind FROZEN;
  CTX=TaskBundle; DO=/ai-code(TDD增强版). 吸收superpowers规划精华,去冗余.
disable-model-invocation: true
---
encoding:../../shared/core.md
trig:/ai-design|/d prio:rules>this load:本页 ref命中单读 禁ref批
axiom:evidence>explore>premise stated accept measurable 本期做|明确不做
ssot:../../shared/core.md contract:../../shared/core.md ponytail:裁scope

# 核心增强(v5.0)
## 1. 精简Handoff(去50%冗余)
- 保留: 变更面+验收判据+验证档位+待确认(核心契约)
- 精简: 规则演进→一句话;下一步→枚举;去掉过度解释
- 目标: 29行足够(原31行但信息密度翻倍)

## 2. TDD规划支持(为ai-code v7.0铺路)
- G4新增: 验收判据必须可TDD化(每功能一行,如"func('input')=='output'")
- G5增强: 验证档位对照TDD循环(l档=build+触及单测绿)
- 禁: "看起来对""应该没问题"等模糊表述

## 3. Systematic Debugging前置(替代独立/ai-debug)
- G3增强: 遇难复现bug→先走P0-P1(OBSERVE+REPRODUCE)再决定
- 根因分析前置: design阶段识别风险点,而非code阶段才debug
- 铁律: 未钉根因禁进修复方案

gate-写前:axis-checklist|why-incomplete|瓶颈1行;改+不改+因|一次一事|30%空值并发兼容权限日志回滚

G-pre:ssot0;FROZEN优先于brain;冲突→RM BLOCKER非改记忆

G0:纯问答只析;要plan续;DB/SSH→接入门已填|跳过(原因)

G1:≥2解读→选项+ADR一行;Explore能答不问;模糊慢贵无判据;interface分歧→design-it-twice
   新文件/新抽象/新依赖过负代码四问(lean-gate):同职责已存在?为何不能改现有?增概念还是减?可删?
   兼容双轨须写删除条件+期限

G2:codegraph/orient1;读源写口;契约字面量;排序待确认;禁编字段

G3:生命周期cron对账跨日→行为表;回流≠bug→false-alarm
   难复现→systematic-debugging P0-P1(OBSERVE+REPRODUCE);未钉根因禁进修复方案

G4:验收可测=TDD友好;OoS;本期做;无TBD
   bug-micro|micro 3行|单模简版|≥2模PRD|≥5task→refs.md#implementation-plan-tasks
   每判据格式: func('input')=='expected' (可直接转测试)

G5:Handoff引plan;hit→refs.md#gate-router单读;过滤状态排序perf→档位≥surface
   验证档位: l(build+触及单测)|s(+身份矩阵)|p(+E2E)
   yaml→handoff-template+schema;validate_handoff FAIL→禁交/ai-code;PASS→to-bundle

ref:细则→references/refs.md |Handoff→handoff-template.md |栈/假阳性→../../shared/core.md

rule:Explore不问;语义≥2问;破坏性/状态/排序问;禁UI契约;状态机:不变量+触达+全链路
     接缝现有API;Gate READY禁重问WHAT;验收判据必须TDD化

ship Handoff:`变更面|plan|验收行(TDD格式)|identity|接缝|验证档|待确认|规则演进(1行)|下一步(enum)|/ai-code`

STOP:难复现套PRD|无金标|未证伪|错前提plan|未Explore编字段|无验收Handoff|validate失败交码|抢跑码
    |回流当bug|无本期做|猜契约|perf无对拍|共享列|未钉金标|筛无响应|侧效|ref批|静默接入门
    |重问FROZEN|同chat写码|新结构未证复用|双轨无删除条件|为未来假设设计|验收不可TDD化|未钉根因进修复

link:/ai-code(TDD增强版) requirement-mind systematic-debugging(难bug前置)
note:ai-consider/ai-test/ai-verify/handoff/ai-jdk已退役
lex:负代码 复用 简洁 单一事实源 复述 变更面 验证档位 接缝 深模块 证伪 恢复 反馈环 Handoff
    规则演进 领域语言 ADR 进度披露 场景-行为表 完成判据 抢跑 TDD Red-Green root-cause evidence
