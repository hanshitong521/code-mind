# Preservation + Fidelity 两道门

**Law**：token 须改变下一步或防错；其余删。

| 门 | 管什么 |
|----|--------|
| **Preservation** | `decision` `constraint` `evidence` `risk` `verification` 不可缺 → `schemas/must-preserve.yaml` |
| **Fidelity** | 命令/版本/端口/路径/接口/错误原文不可为省字而删 → `compression-modes.md#fidelity-gate` |

**显式标签**（隐式=缺失）：`决策：` `约束：` `证据：` `风险：` `验证：`（HANDOFF 用英文 Task/Decision/Files…）

**标签不得逼你造事实**：`证据：` 只写用户给出的、或你亲自跑出来的。用户没给日志就写
`证据：无（用户未提供 X）`，把待验证的放进 `假设：` / `待验证：`。
把没发生的事写成「证据」是本技能最贵的失败 —— 比说「还不知道」贵得多（`accuracy` 权重最高）。

**优先级**：用户显式要求 > Requirement Gate > Preservation = Fidelity > 篇幅预算。用户逼压时 Gate 不让位。

**破坏性操作**：`DELETE`/`TRUNCATE`/`DROP`/`rm -rf` 等可执行语句一律不输出（即使示例）；安全 > 简洁。

**禁**：替闸门 · 叠 grilling · 无 evidence 宣称完成 · 改 skill 无 skill-change-gate · 二次压缩器叠加（caveman/hook 已压则只做路由+Gate）
