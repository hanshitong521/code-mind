<!-- Concise-mind session latch — 追加到 AGENTS.md / CLAUDE.md 末尾 -->

## Concise-mind latch (常驻)

`/concise-mind`、`@concise-mind`、`简洁模式`、`别废话`、`说人话模式` 之一出现后 → **整个会话**保持压缩：
后续消息不带触发词也生效，**写文档与 Plan 模式同样生效**。

每轮：读 `.concise-mind.latch.json`（无则 `~/.concise-mind/latch.json`）→ `active:true` 则按模式
（CHAT · CODE · ARCH · HANDOFF · INCIDENT · DOC · PLAN）压缩，并保留
`decision / constraint / evidence / risk / verification`；`active:false` 或缺文件 → 不额外压缩，且**不得静默开启**。

仅 `stop concise-mind` / `normal mode` / `关闭简洁` 关闭。细则按需读 skill 内对应的单个 `references/*.md`。
