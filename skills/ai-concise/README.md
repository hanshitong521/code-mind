# concise-mind (ai-concise)

会话锁存的「输出形状」技能。一次挂上，整个会话（含文档与 Plan）都按模式压缩，**但不许为省字丢事实**。

- 技能名：`concise-mind`　·　目录：`ai-concise`　·　当前版本：**v5.1**
- 触发：`/concise-mind`、`@concise-mind`、`简洁模式`、`说人话模式`、`别废话`
- 关闭：`stop concise-mind`、`normal mode`、`关闭简洁`

## 结构

| 路径 | 作用 |
|------|------|
| `SKILL.md` | 路由器（~2KB）。Latch / Mode / Level / 路由表 |
| `references/reader-first.md` | 五条形状硬规则、列表上限 5、破例、错误报告格式 |
| `references/compression-modes.md` | 七模式预算表、对抗姿态、冲突优先级 |
| `references/gates.md` | Preservation + Fidelity 两道门 |
| `references/levels-and-eli5.md` | L0–L3 强度阶梯、Explain 受众档、精度护栏 |
| `references/intent-router.md` | 一句话 → 模式 |
| `references/preflight.md` | 落笔前 12 条自检 |
| `references/filler-blacklist.md` | 套话/结构水正则（**打分器 SSOT**） |
| `references/hunt.md` | 只砍复杂度的瘦身清单 |
| `schemas/must-preserve.yaml` | 各模式不可省的字段与形状 |
| `scripts/latch.py` | 锁存开关：`on` / `off` / `status` / `check` |
| `scripts/score_concise.py` | 零依赖评测打分器（v5，8 维度） |
| `scripts/make_judge_bundle.py` | 把样本匿名成 A/B/C + 密封对照表，供盲评 |
| `scripts/score_judge.py` | 汇总盲评分数 + 判定发布门（PASS/FAILED） |
| `evals.json` · `evals/runs.json` | 26 条用例 + 标定样本 + 12 条探针 |
| `evals/judge/rubric.md` | 盲评判据 SSOT（5 维加权 + blocker + 发布门 + 已知局限） |
| `tests/test_score_concise.py` | 12 个零依赖 unittest |
| `reports/compare-vs-i-have-adhd.md` | 与 i-have-adhd 的逐维度对比、盲评实录与优化记录 |
| `assets/AGENTS.snippet.md` · `assets/cursor/concise-mind.mdc` | 常驻注入兜底（AGENTS.md / Cursor） |

## 验证

```bash
# 机检评测（26 用例 × 3 条件 + 12 探针）
python scripts/score_concise.py --runs evals/runs.json --out reports --tag v5

# 自检（契约 / 不误伤 C2 黄金样本 / 探针全检出 / 形状门正负例）
python -m unittest discover -s tests -v

# 盲评三步：匿名 → 外部 judge 打分 → 汇总判门
python scripts/make_judge_bundle.py --runs evals/runs-blind.json --round r11
#   ↑ 把 evals/judge/bundle.json 交给独立 judge，结果写成 scores-r11.jsonl
python scripts/score_judge.py --scores evals/judge/scores-r11.jsonl \
    --key evals/judge/key.json --out reports --tag r11
```

- 机检：C0 63.3 · C1 80.1 · **C2 100.0**；探针 **12/12**；unittest **12 OK**。
- 盲评 r9（真实独立样本 60 份）：**gate FAILED**，抓出 4 个真实设计 bug，已修（v5.1）。
- 盲评 r10（修完的 4 条定向复评）：**gate PASS**，C2 4.638 / C0 2.325，候选 0 blocker。
- CI：`.github/workflows/skill-check.yml`（单测 + 打分器 + 探针 + C2 不掉分，零模型调用）。

## 说清它的边界（别把它当证据）

- `reports/` 里的**机检**分数是自评分器给自己打分。它能证明「改了规则没把达标输出误杀」，**不能证明「比不用它更好」**。
- 盲评 r9 用的是既有独立样本，**gate FAILED 是真实结果，没有藏**；r10 用的是标定样本，只能算回归检查。
- 要「比 baseline 好」的证据，必须跑 r11：真实模型重新产出各条件输出 + 第三方 judge。步骤见 `reports/compare-vs-i-have-adhd.md` §9.5。
- `evals/runs.json` 是**标定样本**（按各条件的行为手写），真实模型盲测样本在 `evals/runs-blind.json`。引用分数时不要混。
- 判据由本技能作者撰写，不是第三方；盲评者与被评者同属一个模型族；只看文本，看不到工具调用轨迹。
- 锁存靠「每轮读状态文件」，本质仍是模型自觉；没有 hook 式硬注入。

## 不要做的事

- 不要批读 `references/` —— 按当轮模式单读一个文件。
- 不要叠第二个压缩器（caveman / 别的 hook 已压过 → 本技能只做路由 + Gate）。
- 不要让它替代 `ai-code` / `requirement-mind` 的门禁：它是 Overlay，不是工作流。
