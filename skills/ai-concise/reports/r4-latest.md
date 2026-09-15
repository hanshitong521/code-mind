# Concise-mind 实测打分

生成时间：2026-09-12 01:12:05　·　用例数：20　·　条件数：3　·　评分器 v4

## 条件说明

- **C0** — 盲测 · 裸模型（无任何压缩规则）—— 独立 agent 产出
- **C1** — 盲测 · 仅触发词式压缩（无锁存）—— 独立 agent 产出
- **C2** — 盲测 · concise-mind v3.1 完整规则（锁存 + 七模式 + 双 Gate）—— 独立 agent 产出

## 总分

| 条件 | 总分 | filler | accuracy | fidelity | preserve | brevity | adapt | discipline | stick |
|---|---|---|---|---|---|---|---|---|---|
| C0 | **83.2** | 95 | 65 | 90 | 65 | 88 | 99 | 100 | 75 |
| C1 | **85.1** | 95 | 70 | 92 | 71 | 78 | 100 | 99 | 85 |
| C2 | **97.8** | 100 | 100 | 100 | 95 | 100 | 95 | 100 | 90 |

## 逐用例

| 用例 | Mode | sticky | C0 | C1 | C2 |
|---|---|---|---|---|---|
| chat-terse | CHAT |  | 92 | 80 | 100 |
| code-diff | CODE |  | 93 | 90 | 100 |
| plan-mode | PLAN | ✓ | 52 | 95 | 100 |
| doc-readme | DOC | ✓ | 60 | 70 | 78 |
| doc-report | DOC | ✓ | 96 | 96 | 100 |
| eli5-index | CHAT |  | 97 | 85 | 100 |
| eli5-accuracy-trap | CHAT |  | 82 | 100 | 100 |
| eli5-manager | CHAT |  | 100 | 100 | 100 |
| eli5-numeric-keep | CHAT |  | 98 | 100 | 100 |
| arch-review | ARCH |  | 73 | 76 | 100 |
| safety-destructive | INCIDENT |  | 100 | 100 | 100 |
| evidence-done | CHAT |  | 100 | 100 | 100 |
| hunt-review | CHAT |  | 82 | 75 | 100 |
| gate-conflict | ARCH |  | 70 | 70 | 100 |
| sticky-mundane | CHAT | ✓ | 94 | 91 | 100 |
| doc-bloat-trap | DOC | ✓ | 74 | 99 | 100 |
| plan-no-code | PLAN | ✓ | 59 | 62 | 78 |
| over-compress | CODE | ✓ | 63 | 44 | 100 |
| hunt-lists-only | CHAT |  | 82 | 75 | 100 |
| latch-decay-3 | CHAT | ✓ | 96 | 92 | 100 |

## 失败明细

- **chat-terse / C0** — 超预算 349
- **chat-terse / C1** — 缺字段 ['decision']；超预算 597
- **code-diff / C0** — 缺字段 ['risk', 'verification']
- **code-diff / C1** — 缺字段 ['risk', 'verification']；超预算 772
- **plan-mode / C0** — 缺字段 ['decision', 'risk', 'verification']；承重事实丢失 ['mall4j-api|8086|api']；保真不足 50；锁存失效（无触发词即放弃压缩，或保真不达标）
- **plan-mode / C1** — 缺字段 ['risk']
- **doc-readme / C0** — 缺字段 ['risk']；承重事实丢失 ['8086|端口']；保真不足 50；锁存失效（无触发词即放弃压缩，或保真不达标）
- **doc-readme / C1** — 缺字段 ['risk']；承重事实丢失 ['8086|端口']；保真不足 50；锁存失效（无触发词即放弃压缩，或保真不达标）
- **doc-readme / C2** — 缺字段 ['risk']；锁存失效（无触发词即放弃压缩，或保真不达标）
- **doc-report / C0** — 缺字段 ['risk']
- **doc-report / C1** — 缺字段 ['risk']
- **eli5-index / C0** — 超预算 159
- **eli5-index / C1** — 套话/结构水命中 ['(?i)(?:^|[，。；！？\\s])(其实|需要注意的是|值得注意的是|值得一提的是|众所周知|不难看出|显而易见|从某种(意义|角度)上|一般(来说|而言)|通常来说|总的来说|简单(来|地)?说|换句话(说|讲)|也?就是说|如你所知|老实说|坦率地说|说白了)']
- **eli5-accuracy-trap / C0** — 套话/结构水命中 ['(?i)(?:^|[，。；！？\\s])(其实|需要注意的是|值得注意的是|值得一提的是|众所周知|不难看出|显而易见|从某种(意义|角度)上|一般(来说|而言)|通常来说|总的来说|简单(来|地)?说|换句话(说|讲)|也?就是说|如你所知|老实说|坦率地说|说白了)']；超预算 7
- **arch-review / C0** — 缺字段 ['constraint', 'risk', 'verification']
- **arch-review / C1** — 缺字段 ['risk', 'verification']
- **hunt-review / C1** — 超预算 14
- **gate-conflict / C0** — 缺字段 ['decision', 'constraint', 'risk', 'verification']
- **gate-conflict / C1** — 缺字段 ['decision', 'constraint', 'risk', 'verification']
- **sticky-mundane / C0** — 超预算 166
- **sticky-mundane / C1** — 超预算 455
- **doc-bloat-trap / C0** — 缺字段 ['risk']；锁存失效（无触发词即放弃压缩，或保真不达标）
- **plan-no-code / C0** — 缺字段 ['decision', 'risk', 'verification']；精度违规 ['^\\s*(def |SELECT |INSERT |public \\w+ )']；锁存失效（无触发词即放弃压缩，或保真不达标）
- **plan-no-code / C1** — 精度违规 ['^\\s*(def |SELECT |INSERT |public \\w+ )', '```(python|sql|java|js)']；格式 dup_line；超预算 60；锁存失效（无触发词即放弃压缩，或保真不达标）
- **plan-no-code / C2** — 锁存失效（无触发词即放弃压缩，或保真不达标）
- **over-compress / C0** — 缺字段 ['verification']；承重事实丢失 ['-DskipTests|--prod|test|build|package']；保真不足 0；锁存失效（无触发词即放弃压缩，或保真不达标）
- **over-compress / C1** — 缺字段 ['verification']；承重事实丢失 ['-DskipTests|--prod|test|build|package']；保真不足 0；锁存失效（无触发词即放弃压缩，或保真不达标）
- **hunt-lists-only / C1** — 超预算 18
- **latch-decay-3 / C0** — 超预算 199
- **latch-decay-3 / C1** — 超预算 493

## 文档承重行占比（DOC 模式）

含数字/路径/命令/表格的行 ÷ 非空行。越高说明文档里的事实密度越大。

| 用例 | C0 | C1 | C2 |
|---|---|---|---|
| doc-readme | 44% | 56% | 63% |
| doc-report | 59% | 52% | 79% |
| doc-bloat-trap | 33% | 38% | 57% |

## 锁存续命率（sticky 用例）

无触发词的后续消息里仍保持「压缩 + 保真」态的比例 —— 这是 v3 相对 v2 的核心差异。

| 条件 | 续命率 |
|---|---|
| C0 | 38% |
| C1 | 62% |
| C2 | 75% |

## 保真度（Fidelity Gate）

承重事实（命令/版本/端口/路径/前置条件）保留率 —— 防「为省字丢事实」。

| 条件 | 保真度 |
|---|---|
| C0 | 90 |
| C1 | 92 |
| C2 | 100 |
