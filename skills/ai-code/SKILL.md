---
name: ai-code
version: 8.0.0
description: >-
  Use when /ai-code: implement frozen docs/diagram/design.md, or bug root-cause then min diff.
  Least code; same-PR delete dead/redundant in touched files. Not for /ai-design, requirement freeze, log-only ops.
disable-model-invocation: true
---
encoding:../../shared/core.md
trig:/ai-code prio:rules>this load:本页+references/lean.md 其余ref命中单读 禁批读
axiom:evidence>falsify>premise; 改后仓库须更简单; bug=一次一假设 未钉根因禁修
ssot:../../shared/core.md contract:../../shared/core.md

Goal: 设计交付范围内行为正确, 净代码下降或持平(有deleted证据).
Constraints: FROZEN/design.md范围; 语义守恒; 触及区外不扫仓; 禁git add.
DoD: tight red→green; HIST-CLEAN; Fresh档位验证; ship含deleted.
Evidence: cmd+exit或SELECT; deleted=路径 或 `none:`+grep.

mode: 无判据→/ai-design; 现象/报错未钉根因→DBG再G1; Handoff已冻→G0

# DBG（未钉根因只走这段）
D0现象+环境+1行判据 · D1最小复现(不可复现禁猜修) · D2 git show+调用链 · D3单一假设 · D4最小实验 false-alarm先 · D5根因一句+证据 未钉禁修 · D6修复边界→G1 禁失败扩diff
DBG-ship:`根因|假设|证据|证伪项|修复边界|回归面`
P0:单测|SELECT|curl|CLI|replay|bisect; 建不了→列尝试+artifact禁改码
投喂:复现|预期|实际|原始日志|范围; 缺项禁盲改

G0:改|不改|完成判据?否→/ai-design. 消费design.md范围+档位. OoS禁做. micro可无设计交付须1行判据.
G1 RED:最小失败测试且原因对. 无tight red禁改生产. orient/codegraph1次. 新建过lean四问. 过滤状态→扫读者.
G2 GREEN:按lean梯写最少码让红变绿. 数据证伪→停改回设计. 未钉根因→DBG.
G3 契约:禁删口径宁新列; 合并替入口→同PR删旧+grep引用; 仅用户留兼容才双轨(条件+期限). 改wire→contract.md. DB/SSH须接入门.
G4 VERIFY:Fresh build+触及单测; 写SQL→探针; 性能→执行计划+双向对拍. 未跑禁完成. 档位=verification-policy.yaml. 未绿→G0.
G5 ship:`改动|deleted|skipped|验证exit|风险` + yaml(变更面|plan引用|已跑|未跑|下一步). deleted空→`none:`+grep. parallel_implementation=yes禁完成.

Java/Mapper前:`get_change_context(file=相对路径)`; 坑:`save_bug_memory`; 收尾:`record_task_outcome`(candidate)
domain-pack:JDK8/ADS→domain-packs/java8或ads/pitfalls-shejiuPro.md; 改wire先探测本仓落api-wire.md 禁套外部默认

ref:
  已随skill加载→references/lean.md
  难bug→references/gates.md#debug
  宣称完成→references/gates.md#verify
  交付yaml→references/gates.md#manifest
  双实现/桥接→references/gates.md#rigid
  PR审查→references/gates.md#review
  改响应/GET参→references/contract.md
  空列表/过滤/慢/Px→references/pitfalls.md
  栈/假阳性→../../shared/core.md
  旧锚跳转→references/refs.md

STOP:错前提|无判据抢跑|未钉根因修|无red改生产|净增无deleted|触及区未扫死码|为简洁删口径|双轨无期限|平行实现未收敛|裸✓|有测未跑|猜契约|幻读|子代理代ship|叠grilling|未过四问建文件|IDE灰即删|动态入口未查就删
link:/ai-design(前提) requirement-mind(BLOCKER) 禁git add.
lex:负代码 触及区 HIST-CLEAN 复用 变更面 验证档位 证伪 设计交付 TDD root-cause
