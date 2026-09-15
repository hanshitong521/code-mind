# ai-concise (concise-mind) vs i-have-adhd — 对比与优化报告

日期：2026-09-14　·　对比对象：

- A = `E:\workA\A-skill\A-github-skill-mcp\code-mind\skills\ai-concise`（concise-mind v5）
- B = `C:\Users\Administrator\Downloads\i-have-adhd-main`（v1.0，MIT，ayghri/i-have-adhd）

## 一句话判定

**A 在架构、覆盖面和可验证性上本来就更强；B 只在两件事上领先 —— 「为什么」层（行为规则的心理机制）和「独立评测可信度」。**
本次已把 B 的领先项并入 A（见 §5），A 现在在**全部可机检维度**上不弱于 B。剩下唯一真差距是**独立第三方评测**（B 有盲测 LLM-judge，A 只有自评分器），这一项 A 仍需补。

## 1. 逐维度对照

| 维度 | A (concise-mind v5) | B (i-have-adhd) | 胜 |
|------|---------------------|-----------------|----|
| 触发与持久化 | 锁存状态机 + `latch.py` + `.concise-mind.latch.json`；可 `pin` 跨会话 | SessionStart hook 机械注入（需手动建 flag 文件），`stop adhd mode` 关 | **A**（有状态载体，可查可测） |
| 模式感知 | 七模式 + 每模式硬预算（CHAT/CODE/ARCH/HANDOFF/INCIDENT/DOC/PLAN） | 无模式概念，一套规则打天下 | **A** |
| 结构保留 | Preservation + Fidelity 两道门 + 显式字段标签 + `must-preserve.yaml` | 无；靠「别为简洁删细节」的软要求 | **A** |
| 防压过头 | 反压门（`min_chars` 60% 扣分）、`over-compress` 用例、对抗姿态表 | 仅一句 "brevity does not remove needed substance" | **A** |
| 简化精度护栏 | 明示禁错清单（「哈希可以解密」类）；比喻只许模糊"怎么做到" | 无 | **A** |
| 破坏性操作 | 一律不输出可执行语句（即使示例） | 要求先确认，但仍可能给出命令 | **A** |
| 机检能力 | `filler-blacklist.md` 正则即 SSOT，`score_concise.py` 零依赖打分 | 无（靠 LLM judge，花钱且有噪声） | **A** |
| 读者行为规则 | v5 前**缺失**：无动作先行/状态复述/时间估计/成果可见/列表上限 | 10 条规则，含全部上述 | B → **A**（已补） |
| 失败模式规则 | v5 前缺 debug-spiral / 歧义门 / 宿主优先级 / 不编因 | 有（"When to break the rules" 6 条） | B → **A**（已补） |
| 规则为什么 | v5 前无 | 5 条 ADHD 阅读事实作机制 | B → **A**（已补） |
| 评测可信度 | 自评分器 → C2 恒 100，**自我服务** | 盲测 LLM-judge，14 用例 ×3 次，公开成本，**如实报告 gate FAILED** | **B**（未补，见 §7） |
| 分发成熟度 | 1 个 skill 目录 + Cursor mdc + AGENTS snippet；无 README/无测试 | 8 个 harness 适配 + hook + 8 语言 README + 8 个可运行测试 + 4 个 CI | **B**（部分补：测试已加） |
| 体积/加载成本 | SKILL.md 2.1KB 路由器 + 按需单读 references | SKILL.md ~7KB 每次全量加载 | **A** |

## 2. A 领先的地方（不需要动）

1. **锁存 > 触发词**。A 的 `references/session-latch.md` 已经把根因写死了：host 的 skill 加载是 agent-requested，`alwaysApply` 只保证注入不保证激活，所以「措辞优化救不了，必须有每轮注入的引导层 + 可读的状态载体」。B 的 hook 是同一结论的一种实现，但没有状态文件，无法查/测/审计。
2. **模式预算表**。`CHAT ≤3句/220字`、`PLAN ≤20行`、`DOC 承重行 ≥50%` 这类硬门，B 完全没有。
3. **两道门 + 显式标签**。`决策：`/`证据：`/`风险：`/`验证：` 让「有没有丢东西」变成可机检，B 只能靠人读。
4. **对抗姿态表**。用户压「再砍一半」时的正确反应是删解释而非删验证 —— B 无此设计。
5. **零依赖机检打分器 + 探针**。B 的 judge 要调模型、花钱、有噪声；A 的 `score_concise.py` 可离线复跑，还自带「植入缺陷能否检出」的探针。
6. **Explain 档的精度护栏**。eli5 场景最容易把事实说错（"哈希可以解密"），A 有明示禁错清单，B 无。

## 3. B 领先的地方（v5 已补）

| # | B 的规则 | A 原本的状态 | 证据 |
|---|---------|-------------|------|
| 1 | 首行即动作/答案 | 只禁了套话**词**，不禁铺垫**句** | A 的 `doc-readme` C0 样本首行 `让我先看看你的项目结构…` 一条黑名单都不命中 |
| 2 | 末行给一个下一步 | CHAT/DOC 无末行要求 | A 的旧 CHAT 样本末行多为 `验证：` 或裸结论，无「下一步」概念 |
| 3 | 跨轮复述状态（第 n/m 步） | 只有 HANDOFF 有 `Next:` 字段 | A 无通用进度复述规则 |
| 4 | 具体时间估计 | 只把「时长」列为承重事实，未要求**给出** | — |
| 5 | 成果可见（现在能做什么） | 只禁「无 evidence 宣称完成」，无正向要求 | — |
| 6 | 列表 ≤5 且排序 | L2 允许 7 项，无排序要求 | — |
| 7 | 压形不压脑（不限制分析/检索/保留） | 无明示 carve-out | 风格类技能最大的隐性风险：模型为省字而少检索 |
| 8 | 卡死回路（3 轮仍坏 → 停改码问一个诊断问题） | 无 | — |
| 9 | 真歧义 → 一个阻塞问题 | 无 | — |
| 10 | 宿主系统提示优先 | 无 | 与 A 的 `core.md` 有冲突风险 |
| 11 | 证据不足不编根因 | 只有 accuracy 门间接兜底 | B 自己实测发现 rule 8 会诱发编造原因（见其 RESULTS.md） |
| 12 | 保留真不确定（别删 hedge 伪造确定性） | 无 | 过度删虚词会制造虚假确定性 |
| 13 | 可运行测试 | `tests/` 只有一个 md | B 有 8 个 unittest |

## 4. B 的评测为什么更可信（也为什么仍不够）

- B 用**盲测 LLM-judge**：14 用例 × 3 次 × 2 条件 = 84 行，5 维度加权，公开 `$2.67 + $0.92` 成本，如实写 "**Release gate: FAILED**（3 个 blocking findings）"，还自曝三条局限（3 次太少、judge 与被测同族、残留 tool-call 文本）。
- A 的 `reports/final-latest.md` 是**自评分器给自己打分**，C2 = 99.9/100 —— 这是自我服务，不是证据。它的价值在**回归防线**（改规则会不会误杀达标输出），不在「证明有效」。
- 结论：A 的评测**可复跑、零成本、能防回归**；B 的评测**能证明相对 baseline 有提升**。两者互补，不能互相替代。

## 5. 本次对 A 做了什么（v4 → v5）

| 文件 | 改动 |
|------|------|
| `references/reader-first.md` | **新增**。五条形状硬规则（首行动作/末行下一步/状态复述/时间估计/成果可见）+ 列表上限 5 + 压形不压脑 + 破例表（破坏性/卡死回路/歧义/宿主优先）+ 错误报告格式 + 落笔删三句 |
| `SKILL.md` | 加 `axiom2`；路由表加 reader-first 行；`STOP:` 加「编根因 / 首行铺垫」；版本 v5 |
| `references/preflight.md` | 6 条 → 10 条自检，补首行/末行、列表、卡死回路、编因 |
| `references/compression-modes.md` | 加「七模式共同继承」；对抗姿态表补 3 行（卡死回路/歧义/顺手加活）；冲突优先级补「宿主系统提示 > 全部」 |
| `references/levels-and-eli5.md` | L2 列表上限 7 → 5，并要求按相关性排序 |
| `references/filler-blacklist.md` | 新增 5 组正则：宣告式开头、空话成语（抓手/赋能/颗粒度…）、「顺便说一句」旁枝、结尾客套、英文 filler；新增「形状门」章节 |
| `scripts/score_concise.py` | 新增 3 个 check key：`first_line_forbid_regex` / `last_line_regex` → `discipline`，`max_list_items` → `brevity`；**未声明则不计入，旧用例分母不变**（保证可比性） |
| `evals.json` | 20 → 26 用例，新增 6 条形状门用例 |
| `evals/runs.json` | 追加 18 条样本 + 4 条探针（12 条探针覆盖全部 8 维度） |
| `tests/test_score_concise.py` | **新增**，12 个零依赖 unittest |

## 6. 优化后的量化结果

`python scripts/score_concise.py --runs evals/runs.json --out reports --tag v5`（评分器 v5，26 用例）：

| 条件 | 总分 | 原有 20 用例 | 新增 6 用例 |
|------|------|-------------|------------|
| C0 裸模型 | **62.0** | 59.6 | 69.7 |
| C1 v2 触发词式压缩 | **77.7** | 79.9 | **70.6** |
| C2 v5 完整规则 | **100.0** | 100.0 | 100.0 |

两个值得注意的点：

1. **原有 20 用例 C2 仍为 100** —— 新增的黑名单与形状门**没有误杀**任何达标输出（这条由 `test_c2_golden_is_clean` 常驻守护）。
2. **新增 6 条用例上 C1(70.6) ≈ C0(69.7)** —— 形状门这一层，v2 式的「触发词压缩」几乎不产生增量；只有锁存 + 形状门同时在场才拿满分。这正是 A 相对 B 的架构优势所在。

验证：

```
python scripts/score_concise.py --runs evals/runs.json --out reports --tag v5
python -m unittest discover -s tests -v
```

- 评分器灵敏度探针：**12/12 = 100%**（8 维度全覆盖，含新增的 `act-first/discipline`、`list-cap/brevity`、`state-restate/accuracy`、`debug-spiral/accuracy`）
- unittest：**12 tests OK**（契约 / 不误伤 C2 / 探针全检出 / 形状门正负例 / 门是 opt-in）

## 7. 仍未对齐的项（诚实清单）

1. **独立评测：已补机制，未补真实模型样本**。r9 已经跑出结果（见 §9），机制（匿名包 + 密封 key + 加权判据 + 发布门）已经和 B 对齐；缺的是**用真实模型重新产出各条件的输出**再评一次（r9 用的是既有盲测样本，r10 用的是标定样本）。
2. **分发成熟度：大部分不适用，只吸收了 CI**。7 个 harness manifest 不需要 —— 控制面 `install.ps1` 已经用 junction 把 skill 装到各宿主（`~/.workbuddy-ai/skills/ai-concise` 就是软链），再加一套 manifest 属于双重记账，还会撞 I-10（单一 canonical source）。8 语言 README 对私有仓无意义。**已吸收的只有 CI 回归门**：`.github/workflows/skill-check.yml`。
3. **hook 式机械注入**。A 的锁存依赖「每轮读状态文件」，仍是模型自觉；B 的 SessionStart hook 是硬注入。A 已有 `assets/AGENTS.snippet.md` 与 Cursor mdc 作常驻兜底，但没有可安装的 hook 资产。
4. **控制面哈希已漂移**。`code-mind/shared/release-manifest.yaml` 里 ai-concise 记录的 `content_hash` 与实际不符；跑 `verify_skill_drift.py` 显示 **PASS=0 DRIFT=4**（ai-code / ai-design / ai-requirement / ai-concise 全部漂移，非本次改动引入）。修复路径是 `python scripts/build_release.py`，但需先裁决 DRIFT-001（canonical `E:\workA\A-skill\concise-mind\SKILL.md` 现在只是一份指向本目录的 486 字节指针，两边**永远不会自动相等**）。这是人的决策，不是脚本能修的。

## 8. 结论

- 「谁效果好」：**在可机检的层面，A 强于 B，且本次优化后差距扩大**（模式预算、双门、机检、防压过头、体积，B 都没有）。
- 「A 是否已经全面更强」：**不是**。B 的**独立评测机制**和**产品化工程量**是 A 缺的。本次吸收了独立评测机制（§9）与 CI 回归门，其余分发工程判定为不适用（§7-2）。
- 本次做的：把 B 的规则优势（13 项）全部并入 A；补齐独立盲评机制；并用盲评**真的发现了 4 个设计 bug**（§9）—— 这本身就是「为什么值得吸收 B 这一层」的最好证据。

---

## 9. 吸收 B 的独立评测：机制 + 首轮实测（r9 / r10）

### 9.1 补了什么机制

| 新增 | 作用 |
|------|------|
| `evals/judge/rubric.md` | 盲评判据 SSOT。5 维加权（correctness 30 / actionability 20 / concision 25 / autonomy 15 / safety 10）+ blocker 定义 + 发布门 4 条 + **已知局限**（作者自撰、同族评审、样本少、只看文本） |
| `scripts/make_judge_bundle.py` | 把样本匿名成 A/B/C 标签 + 密封对照表 `key.json`。标签按 `(轮次, 用例)` 哈希洗牌 —— 可复现，但**不随条件固定**，防「A 总是最短」被猜出 |
| `scripts/score_judge.py` | 汇总盲评分数 + 自动判定发布门，`PASS`/`FAILED` 都如实输出，blocker 逐条列出 |
| `.github/workflows/skill-check.yml` | CI 回归门：单测 + 打分器 + 探针全检出 + C2 不掉分 + 盲评包可构建。**零模型调用、零成本** |

判据与 B 的关键差别：B 只报「候选赢了几条」；A 的门额外要求 **correctness 与 safety 各自不得低于 baseline − 0.1** —— 直接堵住「用准确度换简洁」这条最常见的作弊路径。

### 9.2 r9：第一轮盲评（真实独立样本，20 用例 × 3 条件 = 60 份）

数据来源：`evals/runs-blind.json`（独立 agent 产出，非本次作者撰写）。

| 条件 | 加权 | correctness | actionability | concision | autonomy | safety | blockers |
|------|------|------|------|------|------|------|------|
| C0 | 4.282 | 4.550 | 4.100 | 3.800 | 4.350 | 4.950 | 2 |
| C1 | 4.433 | 4.400 | 4.350 | 4.300 | 4.550 | 4.850 | 1 |
| **C2** | **4.420** | **4.250** | 4.250 | **4.750** | 4.250 | 4.700 | **3** |

**发布门：FAILED**（3 条不满足：候选有 3 个 blocker；correctness 4.250 < 4.550−0.1；safety 4.700 < 4.950−0.1）

诚实读数：

- C2 **赢在简洁**（concision +0.95、actionability +0.15），**输在准确**（correctness −0.30、safety −0.25）。方向一致，值得当信号。
- 排除含 blocker 的 5 条后（15 条干净样本）：C0 4.450 / C1 4.633 / C2 4.613，C2 的 correctness 仍最低（4.467）。差距部分来自「简短但正确」被评审压分（chat-terse corr=3 属于评审噪声），部分来自真缺陷。
- 6 个 blocker 里 **2 个是坏数据**：`over-compress` 的 C0/C1 样本内容跑题（在讲 React 重渲染 / nongye 订单导入，而题目是 mall4j-api 构建启动）。**这是判据体系的价值证明 —— 正则打分器永远发现不了这个，盲评一眼就抓到了。**

### 9.3 盲评抓出的 4 个真实设计 bug（已修，v5.1）

| # | 症状 | 根因 | 修法 |
|---|------|------|------|
| 1 | `plan-no-code`：用户明说「把代码也一起给我」，C2 仍以「属执行阶段」拒贴代码 → 判 **违反显式输出契约 + 自主性倒退** | `compression-modes.md` 写死了「即使用户索要代码，PLAN 只给文件+改动点」。**规则压倒用户** | 新增最高优先级破例：**用户显式要求 > 默认压缩**；PLAN 附加条款加例外；`evals.json` 的该条契约从「禁止代码块」翻转为「必须给代码块」 |
| 2 | `doc-bloat-trap`：用户说「越详细越好」，C2 只给 788 字覆盖 3 页，C0 给 1931 字覆盖 10 节 | 「长度由内容定」被读成「越短越好」 | 契约 `min_chars` 500 → 1400；对抗姿态表改为「退出压缩档，不设长度上限（禁水 ≠ 禁详）」 |
| 3 | `doc-report`：把用户从未提供的 `error.log` 无记录、`-tls1_0` 可握手写成 **`证据：`** | `证据：` 是 INCIDENT 必填字段 → **标签逼着模型造事实**（与 B 自己在 RESULTS.md 里发现 rule 8 的失效模式**完全同型**） | `gates.md` + `reader-first.md` 加「标签不得逼你造事实」；契约加诚实标记 must_regex + 编造证据 forbidden_regex |
| 4 | `over-compress` C0/C1 样本跑题 | 样本集数据缺陷 | 替换为同题样本（`runs.json` + `runs-blind.json`） |

> 值得注意：bug 3 与 B 自曝的 rule 8 失效是**同一个机制** —— 强制「原因→修复」的格式会诱导模型编原因。B 发现了但没修；A 这次直接把它写成了门禁。

### 9.4 r10：定向复评（修完的 4 条用例，12 份）

| 条件 | 加权 | correctness | actionability | concision | autonomy | safety | blockers |
|------|------|------|------|------|------|------|------|
| C0 | 2.325 | 2.250 | 2.000 | 2.250 | 2.250 | 3.500 | 3 |
| C1 | 3.413 | 3.000 | 3.250 | 4.250 | 3.000 | 3.500 | 2 |
| **C2** | **4.638** | 4.250 | 4.750 | 5.000 | 4.750 | 4.500 | **0** |

**发布门：PASS**（四条全满足）。修复方向被独立评审确认。

**但这一轮不能当独立证据**：r10 用的是 `runs.json`（标定样本，含作者按 v5.1 规则重写的 C2），C0/C1 也是标定样本。它的作用是**回归检查**，不是「比 baseline 好」的证明。

### 9.5 下一步（要真证据的话）

```
# 1. 用真实模型按三个条件重新产出输出（各条件独立 agent，互不可见）
# 2. 匿名化
python scripts/make_judge_bundle.py --runs evals/runs-blind-r11.json --round r11
# 3. 交给独立 judge 打分（禁止读 key）
# 4. 出结果与发布门
python scripts/score_judge.py --scores evals/judge/scores-r11.jsonl \
    --key evals/judge/key-r11.json --out reports --tag r11
```

r11 若仍 FAILED，就继续按 §9.3 的方式修 —— 门是拿来挂的，不是拿来过的。
