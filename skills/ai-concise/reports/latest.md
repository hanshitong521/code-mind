# Concise-mind 实测打分

生成时间：2026-09-12 00:18:09　·　用例数：14　·　条件数：3

## 条件说明

- **C0** — 裸模型（无任何压缩规则）—— 即 Cursor Plan 模式下 skill 未加载时的真实行为
- **C1** — concise-mind v2 已加载：CHAT/CODE/ARCH/HUNT 命中触发词时压缩；无锁存 → 后续消息 / DOC / PLAN 全部回退默认行为
- **C2** — concise-mind v3 锁存：一次 ON 后整会话持续，含文档与 Plan，带 Preservation Gate 与精度护栏
- **PROBE** — 评分器灵敏度探针：人为植入缺陷输出，验证打分器能否检出（不计入总分）

## 总分

| 条件 | 总分 | filler | accuracy | preserve | brevity | adapt | stick |
|---|---|---|---|---|---|---|---|
| C0 | **53.2** | 0 | 32 | 56 | 86 | 98 | 71 |
| C1 | **80.5** | 100 | 64 | 51 | 99 | 89 | 79 |
| C2 | **100.0** | 100 | 100 | 100 | 100 | 100 | 100 |

## 逐用例

| 用例 | Mode | sticky | C0 | C1 | C2 |
|---|---|---|---|---|---|
| chat-terse | CHAT |  | 54 | 85 | 100 |
| code-diff | CODE |  | 40 | 90 | 100 |
| plan-mode | PLAN | ✓ | 60 | 40 | 100 |
| doc-readme | DOC | ✓ | 53 | 59 | 100 |
| doc-report | DOC | ✓ | 47 | 67 | 100 |
| eli5-index | CHAT |  | 58 | 98 | 100 |
| eli5-accuracy-trap | CHAT |  | 58 | 100 | 100 |
| eli5-manager | CHAT |  | 60 | 80 | 100 |
| arch-review | ARCH |  | 52 | 96 | 100 |
| safety-destructive | INCIDENT |  | 45 | 61 | 100 |
| evidence-done | CHAT |  | 52 | 92 | 100 |
| hunt-review | CHAT |  | 60 | 90 | 100 |
| gate-conflict | ARCH |  | 49 | 69 | 100 |
| sticky-mundane | CHAT | ✓ | 56 | 100 | 100 |

## 失败明细

- **chat-terse / C0** — 套话命中 ['(?i)好问题|问得好|很高兴|乐意为您|希望对你有帮助|希望这能帮到你|如有需要|随时告诉我|以上(就)?是全部|综上所属|综上所述', '[\\u2705\\u274c\\u2b50\\u2728\\u26a1\\U0001F300-\\U0001FAFF]']；缺字段 ['decision']；超预算 335
- **chat-terse / C1** — 缺字段 ['decision']
- **code-diff / C0** — 套话命中 ['(?i)好问题|问得好|很高兴|乐意为您|希望对你有帮助|希望这能帮到你|如有需要|随时告诉我|以上(就)?是全部|综上所属|综上所述']；缺字段 ['decision', 'risk', 'verification']；精度违规 ['class\\s+\\w*Cache']；超预算 931
- **code-diff / C1** — 缺字段 ['decision', 'verification']
- **plan-mode / C0** — 套话命中 ['(?i)好问题|问得好|很高兴|乐意为您|希望对你有帮助|希望这能帮到你|如有需要|随时告诉我|以上(就)?是全部|综上所属|综上所述']；缺字段 ['decision']；锁存失效（无触发词即放弃压缩）
- **plan-mode / C1** — 缺字段 ['decision', 'risk']；锁存失效（无触发词即放弃压缩）
- **doc-readme / C0** — 套话命中 ['(?i)好问题|问得好|很高兴|乐意为您|希望对你有帮助|希望这能帮到你|如有需要|随时告诉我|以上(就)?是全部|综上所属|综上所述', '[\\u2705\\u274c\\u2b50\\u2728\\u26a1\\U0001F300-\\U0001FAFF]', '总结|小结|结语|Conclusion|Summary']；锁存失效（无触发词即放弃压缩）
- **doc-readme / C1** — 缺字段 ['risk']；锁存失效（无触发词即放弃压缩）
- **doc-report / C0** — 套话命中 ['(?i)好问题|问得好|很高兴|乐意为您|希望对你有帮助|希望这能帮到你|如有需要|随时告诉我|以上(就)?是全部|综上所属|综上所述', '总结|小结|结语|Conclusion|Summary']；缺字段 ['evidence', 'risk', 'verification']；锁存失效（无触发词即放弃压缩）
- **doc-report / C1** — 缺字段 ['evidence', 'risk', 'verification']；锁存失效（无触发词即放弃压缩）
- **eli5-index / C0** — 套话命中 ['(?i)好问题|问得好|很高兴|乐意为您|希望对你有帮助|希望这能帮到你|如有需要|随时告诉我|以上(就)?是全部|综上所属|综上所述']；精度违规 ['B\\+?\\s*树|B-tree']
- **eli5-accuracy-trap / C0** — 套话命中 ['(?i)好问题|问得好|很高兴|乐意为您|希望对你有帮助|希望这能帮到你|如有需要|随时告诉我|以上(就)?是全部|综上所属|综上所述']；精度违规 ['可以解密']
- **eli5-manager / C0** — 套话命中 ['(?i)好问题|问得好|很高兴|乐意为您|希望对你有帮助|希望这能帮到你|如有需要|随时告诉我|以上(就)?是全部|综上所属|综上所述']；精度违规 ['member|zrangebyscore|zadd']
- **eli5-manager / C1** — 精度违规 ['member|zrangebyscore|zadd']
- **arch-review / C0** — 套话命中 ['(?i)好问题|问得好|很高兴|乐意为您|希望对你有帮助|希望这能帮到你|如有需要|随时告诉我|以上(就)?是全部|综上所属|综上所述']；缺字段 ['constraint', 'verification']
- **arch-review / C1** — 缺字段 ['verification']
- **safety-destructive / C0** — 套话命中 ['(?i)好问题|问得好|很高兴|乐意为您|希望对你有帮助|希望这能帮到你|如有需要|随时告诉我|以上(就)?是全部|综上所属|综上所述']；缺字段 ['risk', 'verification']；精度违规 ['DELETE\\s+FROM\\s+users']
- **safety-destructive / C1** — 缺字段 ['risk', 'verification']；精度违规 ['DELETE\\s+FROM\\s+users', 'TRUNCATE\\s+TABLE\\s+users']
- **evidence-done / C0** — 套话命中 ['(?i)好问题|问得好|很高兴|乐意为您|希望对你有帮助|希望这能帮到你|如有需要|随时告诉我|以上(就)?是全部|综上所属|综上所述', '[\\u2705\\u274c\\u2b50\\u2728\\u26a1\\U0001F300-\\U0001FAFF]']；缺字段 ['evidence']
- **evidence-done / C1** — 缺字段 ['evidence']
- **hunt-review / C0** — 套话命中 ['(?i)好问题|问得好|很高兴|乐意为您|希望对你有帮助|希望这能帮到你|如有需要|随时告诉我|以上(就)?是全部|综上所属|综上所述']
- **gate-conflict / C0** — 套话命中 ['(?i)好问题|问得好|很高兴|乐意为您|希望对你有帮助|希望这能帮到你|如有需要|随时告诉我|以上(就)?是全部|综上所属|综上所述']；缺字段 ['decision', 'risk', 'verification']
- **gate-conflict / C1** — 缺字段 ['constraint', 'risk', 'verification']
- **sticky-mundane / C0** — 套话命中 ['(?i)好问题|问得好|很高兴|乐意为您|希望对你有帮助|希望这能帮到你|如有需要|随时告诉我|以上(就)?是全部|综上所属|综上所述']；超预算 165；锁存失效（无触发词即放弃压缩）

## 文档承重行占比（DOC 模式）

含数字/路径/命令/表格的行 ÷ 非空行。越高说明文档里的事实密度越大。

| 用例 | C0 | C1 | C2 |
|---|---|---|---|
| doc-readme | 31% | 67% | 80% |
| doc-report | 42% | 56% | 53% |

## 锁存续命率（sticky 用例）

无触发词的后续消息里仍保持压缩态的比例 —— 这是 v3 相对 v2 的核心差异。

| 条件 | 续命率 |
|---|---|
| C0 | 0% |
| C1 | 25% |
| C2 | 100% |

## 评分器灵敏度探针

人为植入缺陷输出，验证打分器能否检出。**检出率 6/6 = 100%**

| 用例 | 植入缺陷维度 | 打分器给出 | 是否检出 |
|---|---|---|---|
| chat-terse | filler | 0.0 | ✓ |
| arch-review | preserve | 25.0 | ✓ |
| eli5-accuracy-trap | accuracy | 0.0 | ✓ |
| chat-terse | brevity | 60.0 | ✓ |
| plan-mode | stick | 0.0 | ✓ |
| doc-readme | adapt | 83.5 | ✓ |
