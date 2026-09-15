---
name: <SKILL_NAME>
description: Use when <TRIGGER>. Not for <STOP_LIST>.
---
trig:<TRIGGER> prio:rules>this load:本页+必读ref 其余命中单读 禁批读
axiom:最小充分上下文; 证据先于宣称; 假阳性先于改动; 复用先于新建
ssot:../../shared/core.md

Goal: <SKILL_NAME> 负责的任务达成可被证据判定的结果; 范围外一行不动。
Constraints: 只碰任务范围; 复用 > 扩展 > 新建; 语义守恒(不删生效口径/权限谓词/状态边); 触及区外不扫仓。
DoD: 每条判据可跑; 未跑禁宣称完成; 未覆盖项显式列出。
Evidence: cmd+exit 或 SELECT 摘要或产物路径; 关键报错原文保留。

何时用: <TRIGGER>
何时不用: <STOP_LIST> → 不加载, 交给对应 skill。
默认最小: 先报告后改; 用户说「直接改」才动文件。

G0:入口判定 — 范围/档位/完成判据三问; 缺判据 → 停, 回上游 skill 补。
G1:Explore — 先 Read/grep/工具见真源; 禁凭记忆写表名/接口/字段/配置。
G2:证伪 — 先判「是不是问题」; 命中假阳性则改动为零, 只输出设计引用。
G3:最小改动 — 一次一个 choke point; 复用现有实现优先; 顺手改相邻内容 = 禁。
G4:自检 — 跑 DoD 每条, 记 cmd+exit; 未绿禁完成; 未绿 → 回 G0。
G5:交付 — 结论 + 证据 + 未覆盖项 + 回滚点。

Hard Gate(任一即 FAIL): 丢 P0 证据 | 成功率下降 | 权限扩大 | 该用时找不到(Recall 崩)

ref:命中单读, 一条一行「信号 → 路径」, 禁批读; 单条 ≤2000 tokens, 超则再拆或改由 scripts/ 预处理
  格式: 信号用用户原话里的词, 不用内部术语; 一条只指一个文件
  细节/长表/API 原文/完整示例 → references/(一文件一主题, 文件名=主题名)
  机械判断/可复制命令 → scripts/(禁把机械检查写进正文)
  产出格式 → templates/
  基线任务与基线指标 → benchmark/
  触发金标用例 → tests/trigger-cases.md

STOP:<STOP_LIST>|无判据抢跑|未验证宣称完成|裸 ✓|删 P0 证据|为省 token 删证据|自动删除资源|越权扩大权限|猜契约|幻读字段|复述其他 skill 已有流程|description 写工作流|根文档塞参考资料
link:上游产出 → 本技能 → 下游交接物; 交接字段以 ../../shared/handoff-schema.yaml 为准
lex:词汇与 ../../shared/core.md《Skill 词汇》一致; 本技能自造词在此列一行
