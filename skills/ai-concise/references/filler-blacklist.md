# Filler Blacklist — 机检清单

`scripts/score_concise.py` 直接读本文件里的 ```regex``` 块做断言。改这里 = 改评分标准。

## FORBIDDEN_PHRASES（套话/表扬/旁白）

```regex
(?i)好问题|问得好|很高兴|乐意为您|希望对你有帮助|希望这能帮到你|如有需要|随时告诉我|以上(就)?是全部|综上所属|综上所述
(?i)great question|happy to help|i'?d be happy|certainly!|sure thing|let me know if|hope (this|that) helps|feel free to
(?i)作为(一个)?AI|作为一个语言模型|我无法|我作为助手
(?i)→\s*(工具|正在|开始)调用|让我(先)?(查看|读一下|看看)文件|我先(去)?读取
(?i)(?:^|[，。；！？\s])(其实|需要注意的是|值得注意的是|值得一提的是|众所周知|不难看出|显而易见|从某种(意义|角度)上|一般(来说|而言)|通常来说|总的来说|简单(来|地)?说|换句话(说|讲)|也?就是说|如你所知|老实说|坦率地说|说白了)
(?i)(?:^|[，。；！？\s])(你|您)(问|说)的是|关于(你|您)提到的|针对(你|您)的问题
(?i)^\s*(?:让我|我来|接下来我|下面我|下面我们|接下来我们|首先我)\s*(?:先|来|先来)?\s*(?:看|查|读|分析|梳理|说明|介绍|解释|看一下|看看|帮你|给你)
(?i)(拉通对齐|对齐一下|形成闭环|抓手|赋能|颗粒度|组合拳|多快好省|降本增效|打通任督二脉)
(?i)(顺便(说|提)(一下|一句)?|另外提一句|补充一句|by the way|on a side note|quick note|side note)
(?i)(还有什么(需要|要)|需要我(再|继续|接着)|要不要我|要我继续|继续吗|随时(喊|找)我|有问题(随时)?找我|需要的话我)
(?i)(let me (start|begin|take a look|check|explain)|i'?ll start by|before (we|i) (dive|begin|get started)|circling back|get the ball rolling|on the same page|at the end of the day|touch base|loop you in)
```

## FORBIDDEN_SHAPES

```regex
(?m)^\s*[-—=*_]{3,}\s*$
^#{0,6}\s*(总结|小结|结语|Summary|Conclusion)\s*$
(?i)^\s*(总结|总而言之|综上)[:：]
[\u2705\u274c\u2b50\u2728\u26a1\U0001F300-\U0001FAFF]
(?m)\n[ \t]*\n[ \t]*\n
^#{0,6}\s*(背景介绍|前言|导语|写在前面|写在最后|致谢)\s*$
(?:^|\n)[ \t]*(?:以下是|下面(?:是|将)|接下来(?:我们|我)?(?:来)?(?:看|说|讲|介绍))
```

> 新增（v4）：**结构性水**也是水。冗语填充词（其实/值得注意的是/换句话说…）、复述提问、连续空段、装饰性小标题、预告式开场白 —— 与套话同等计价，命中即 `filler` 维度 0 分。
> 例外：DOC 模式中「现象 / 证据 / 风险 / 验证 / 影响 / 原因」这类**承重小标题**不受装饰小标题禁令约束（见 `compression-modes.md`）。

> 例外：用户显式要求 emoji、或模式为 DOC 且 emoji 属于交付物本身（如公众号稿）。

## REQUIRED_MARKERS（按模式）

| Mode | 必须出现的语义标记（任一形式） |
|------|-------------------------------|
| CODE | 文件/函数名 + 变更理由；有风险时显式 `风险`/`risk`；有验证时显式 `验证`/`verified`/`未验证` |
| ARCH / HANDOFF | `目标`\|`goal`、`决策`\|`decision`、`风险`\|`risk`、`验证`\|`verification` |
| DOC | 至少一个标题层级 `#` + （表格或列表）；含数字或路径等具体事实 |
| PLAN | `步骤`\|`step`、涉及文件路径、`验证`\|`verify`、`风险`\|`risk` |
| INCIDENT | `影响`\|`impact`、`原因`\|`cause`、`验证`\|`verify` |

## 长度门

| Mode | 门 |
|------|----|
| CHAT | ≤ 3 句 或 ≤ 160 字 |
| CODE | 代码后 prose ≤ 3 行 |
| PLAN | 总 ≤ 20 行 |
| ARCH / HANDOFF / INCIDENT | ≤ 12 行 |
| DOC | 无上限；去水率 ≥ 25%（对照 baseline 同题输出）；**同时承重行占比 ≥ 50%，低于下限即触发保真扣分** |

## 形状门（v5 新增）

与套话同源：**首行铺垫**和**末行客套**是结构性的水。细则见 `reader-first.md`。

| 门 | 机检 key（`evals.json` 的 `check`） | 判据 |
|----|-----------------------------------|------|
| 首行不是宣告 | `first_line_forbid_regex` | 第一非空行不匹配任一铺垫式开头 |
| 末行有下一步 | `last_line_regex` | 末行含 `下一步：`/`验证：`/`回滚：` 或一个可执行动作 |
| 列表 ≤ 5 项 | `max_list_items` | 计数 `- ` / `1. ` 型列表项 |

## 保真铁律（v4 新增）

压缩**不得**吃掉下列承重事实。删一个 = `fidelity` 维度归零：

| 类型 | 例 | 为什么不能删 |
|------|----|--------------|
| 可执行命令 | `mvn -DskipTests package` | 删了读者跑不起来 |
| 版本 / 端口 / 时长 | `7200`、`:8086`、`TLSv1.2` | 数字即事实 |
| 文件路径 / 接口 | `src/utils/request.js`、`POST /api/auth/wechat/login` | 定位锚点 |
| 前置条件 | 「仅当 X 成立时」 | 前提即事实 |
| 错误原文 | `curl: (35) reset by peer` | 复现依据 |

**反向门（防压过头）**：声明 `min_chars` 的用例，产出低于其 **60%** → `fidelity` 按比例扣分。

## 判分口径

每条用例得分 = 各维度加权命中率 × 100。维度（v4）：
`filler`(2.0) · `accuracy`(2.5) · `fidelity`(2.0) · `preserve`(1.5) · `brevity`(1.5) · `adapt`(1.5) · `discipline`(1.0) · `stick`(1.5)

- `filler` / `accuracy` 的 `forbidden` 命中一次即该维度 **0 分**——套话与说错话是最贵的失败。
- `accuracy` 权重最高：宁可不简洁，不可不准确。
- `discipline`：格式纯净度（无连续空段、无重复行、标题层级不跳级、无尾随装饰行）。
- `stick`：仅 `sticky=true` 用例计分；须同时满足 `filler=100 且 accuracy≥80 且 adapt≥80 且 preserve≥60`。
