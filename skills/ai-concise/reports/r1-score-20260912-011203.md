# Concise-mind 实测打分

生成时间：2026-09-12 01:12:03　·　用例数：20　·　条件数：3　·　评分器 v4

## 条件说明

- **C0** — 盲测 · 裸模型（无任何压缩规则）—— 独立 agent 产出
- **C1** — 盲测 · 仅触发词式压缩（无锁存）—— 独立 agent 产出
- **C2** — 盲测 · concise-mind v3.1 完整规则（锁存 + 七模式 + 双 Gate）—— 独立 agent 产出

## 总分

| 条件 | 总分 | filler | accuracy | fidelity | preserve | brevity | adapt | discipline | stick |
|---|---|---|---|---|---|---|---|---|---|
| C0 | **81.0** | 95 | 62 | 90 | 72 | 65 | 100 | 99 | 75 |
| C1 | **81.5** | 95 | 60 | 90 | 70 | 82 | 94 | 98 | 75 |
| C2 | **94.7** | 100 | 92 | 95 | 82 | 100 | 100 | 99 | 90 |

## 逐用例

| 用例 | Mode | sticky | C0 | C1 | C2 |
|---|---|---|---|---|---|
| chat-terse | CHAT |  | 91 | 91 | 89 |
| code-diff | CODE |  | 91 | 77 | 100 |
| plan-mode | PLAN | ✓ | 82 | 77 | 96 |
| doc-readme | DOC | ✓ | 63 | 78 | 100 |
| doc-report | DOC | ✓ | 96 | 96 | 96 |
| eli5-index | CHAT |  | 76 | 82 | 100 |
| eli5-accuracy-trap | CHAT |  | 93 | 100 | 100 |
| eli5-manager | CHAT |  | 94 | 100 | 100 |
| eli5-numeric-keep | CHAT |  | 93 | 100 | 100 |
| arch-review | ARCH |  | 76 | 76 | 100 |
| safety-destructive | INCIDENT |  | 82 | 100 | 76 |
| evidence-done | CHAT |  | 100 | 82 | 100 |
| hunt-review | CHAT |  | 76 | 77 | 100 |
| gate-conflict | ARCH |  | 70 | 73 | 100 |
| sticky-mundane | CHAT | ✓ | 91 | 91 | 100 |
| doc-bloat-trap | DOC | ✓ | 64 | 65 | 73 |
| plan-no-code | PLAN | ✓ | 56 | 50 | 96 |
| over-compress | CODE | ✓ | 56 | 42 | 78 |
| hunt-lists-only | CHAT |  | 78 | 82 | 91 |
| latch-decay-3 | CHAT | ✓ | 92 | 94 | 100 |

## 失败明细

- **chat-terse / C0** — 超预算 582
- **chat-terse / C1** — 超预算 721
- **chat-terse / C2** — 缺字段 ['decision']
- **code-diff / C0** — 缺字段 ['risk', 'verification']
- **code-diff / C1** — 套话/结构水命中 ['(?m)\\n[ \\t]*\\n[ \\t]*\\n']；缺字段 ['risk']；格式 blank_run；超预算 834
- **plan-mode / C0** — 缺字段 ['decision', 'verification']；锁存失效（无触发词即放弃压缩，或保真不达标）
- **plan-mode / C1** — 缺字段 ['decision', 'risk', 'verification']；锁存失效（无触发词即放弃压缩，或保真不达标）
- **plan-mode / C2** — 缺字段 ['decision']
- **doc-readme / C0** — 套话/结构水命中 ['(?:^|\\n)[ \\t]*(?:以下是|下面(?:是|将)|接下来(?:我们|我)?(?:来)?(?:看|说|讲|介绍))']；缺字段 ['risk']；锁存失效（无触发词即放弃压缩，或保真不达标）
- **doc-readme / C1** — 缺字段 ['risk']；锁存失效（无触发词即放弃压缩，或保真不达标）
- **doc-report / C0** — 缺字段 ['risk']
- **doc-report / C1** — 缺字段 ['risk']
- **doc-report / C2** — 缺字段 ['risk']
- **eli5-index / C0** — 精度违规 ['B\\+?\\s*树|B-tree']；超预算 346
- **eli5-index / C1** — 精度违规 ['B\\+?\\s*树|B-tree']
- **eli5-accuracy-trap / C0** — 超预算 14
- **eli5-manager / C0** — 超预算 477
- **eli5-numeric-keep / C0** — 超预算 515
- **arch-review / C0** — 缺字段 ['constraint', 'verification']
- **arch-review / C1** — 缺字段 ['constraint', 'verification']
- **safety-destructive / C0** — 精度违规 ['TRUNCATE\\s+TABLE\\s+users']
- **safety-destructive / C2** — 缺字段 ['risk']；精度违规 ['TRUNCATE\\s+TABLE\\s+users']
- **hunt-review / C0** — 超预算 13
- **hunt-review / C1** — 超预算 10
- **gate-conflict / C0** — 缺字段 ['decision', 'constraint', 'risk', 'verification']
- **gate-conflict / C1** — 缺字段 ['decision', 'constraint', 'verification']
- **sticky-mundane / C0** — 超预算 364
- **sticky-mundane / C1** — 超预算 420
- **doc-bloat-trap / C0** — 承重事实丢失 ['每日疯抢', '商城热卖', '联系我们', 'openid|微信.{0,2}登录']；保真不足 0；锁存失效（无触发词即放弃压缩，或保真不达标）
- **doc-bloat-trap / C1** — 缺字段 ['decision', 'risk']；承重事实丢失 ['每日疯抢', '商城热卖', '联系我们', 'openid|微信.{0,2}登录']；保真不足 0；格式 dup_line；锁存失效（无触发词即放弃压缩，或保真不达标）
- **doc-bloat-trap / C2** — 承重事实丢失 ['每日疯抢', '商城热卖', '联系我们', 'openid|微信.{0,2}登录']；保真不足 0；格式 dup_line；锁存失效（无触发词即放弃压缩，或保真不达标）
- **plan-no-code / C0** — 缺字段 ['verification']；精度违规 ['^\\s*(def |SELECT |INSERT |public \\w+ )', '```(python|sql|java|js)']；格式 dup_line；超预算 106；锁存失效（无触发词即放弃压缩，或保真不达标）
- **plan-no-code / C1** — 缺字段 ['verification']；精度违规 ['^\\s*(def |SELECT |INSERT |public \\w+ )', '```(python|sql|java|js)']；超预算 48；锁存失效（无触发词即放弃压缩，或保真不达标）
- **plan-no-code / C2** — 缺字段 ['decision']
- **over-compress / C0** — 缺字段 ['verification']；承重事实丢失 ['-DskipTests|--prod|test|build|package']；保真不足 0；超预算 1486；锁存失效（无触发词即放弃压缩，或保真不达标）
- **over-compress / C1** — 缺字段 ['verification']；承重事实丢失 ['-DskipTests|--prod|test|build|package']；保真不足 0；锁存失效（无触发词即放弃压缩，或保真不达标）
- **over-compress / C2** — 缺字段 ['verification']；锁存失效（无触发词即放弃压缩，或保真不达标）
- **hunt-lists-only / C0** — 超预算 12
- **latch-decay-3 / C0** — 超预算 529
- **latch-decay-3 / C1** — 超预算 379

## 文档承重行占比（DOC 模式）

含数字/路径/命令/表格的行 ÷ 非空行。越高说明文档里的事实密度越大。

| 用例 | C0 | C1 | C2 |
|---|---|---|---|
| doc-readme | 71% | 55% | 81% |
| doc-report | 69% | 62% | 72% |
| doc-bloat-trap | 45% | 65% | 71% |

## 锁存续命率（sticky 用例）

无触发词的后续消息里仍保持「压缩 + 保真」态的比例 —— 这是 v3 相对 v2 的核心差异。

| 条件 | 续命率 |
|---|---|
| C0 | 38% |
| C1 | 38% |
| C2 | 75% |

## 保真度（Fidelity Gate）

承重事实（命令/版本/端口/路径/前置条件）保留率 —— 防「为省字丢事实」。

| 条件 | 保真度 |
|---|---|
| C0 | 90 |
| C1 | 90 |
| C2 | 95 |
