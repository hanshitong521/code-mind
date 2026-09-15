# Session Latch — 会话锁存协议

## 1. 为什么 v2 会「不生效」

宿主（Cursor / Claude Code）的 skill、`description` 型规则都是 **agent-requested** 加载：

1. 只有「最近一条用户消息」语义匹配，才会把 skill 正文 fetch 进上下文；
2. 注入 ≠ 激活。`alwaysApply: true` 只保证**注入**，激活仍靠模型判断；
3. 于是出现三个必然失败：

| 场景 | 失败原因 |
|------|----------|
| 后续消息不带触发词 | 最近消息不含「简洁」，不再 fetch → 规则消失 |
| 写文档 | 正文在讲业务，不含压缩信号 → 不 fetch |
| Cursor Plan 模式 | 只读规划，产出是**计划文本**；除了 alwaysApply 规则，其它一律不重载 |

**结论**：措辞优化救不了，必须有一个**每轮必然注入**的引导层 + 一个**可读的状态载体**。

## 2. 协议

### 2.1 状态机

```
OFF ──ON──▶ ACTIVE(L1) ──/concise-mind l3──▶ ACTIVE(L3)
 ▲                │
 └────OFF─────────┘
```

- `ACTIVE` 期间：**每一条回复**都走 Mode Router + Preservation Gate，含文档、计划、代码、子任务。
- 只有显式 OFF 才退出。会话结束（新 conversation）→ 回落 OFF，除非 `pin`。

### 2.2 状态文件

路径优先级（高 → 低）：

1. `<project>/.concise-mind.latch.json`
2. `~/.concise-mind/latch.json`

```json
{
  "active": true,
  "level": "L1",
  "mode_default": "auto",
  "audience": null,
  "scope": "session",
  "pinned": false,
  "since": "2026-09-12T00:10:00+08:00",
  "off_words": ["stop concise-mind", "normal mode", "关闭简洁"]
}
```

### 2.3 每轮自检（必做，成本 ≈ 0）

回复开始前：

1. 读状态文件（存在且 `active:true` → 继续）；
2. 读不到文件 → **沿用本会话已建立的 ACTIVE 状态**，不得静默退出；
3. 用户消息含 OFF 词 → 改文件 `active:false`，本条起恢复 normal。

### 2.4 优先级

```
显式 OFF 词  >  显式 ON 词  >  latch 文件  >  description 匹配
```

`stop concise-mind` 与 `normal mode` 同时也可用于**关闭 caveman 之外**的其它压缩规则；本 skill 只管自己这一层。

## 3. 宿主适配

### 3.1 Cursor — 必装引导规则

把 `assets/cursor/concise-mind.mdc` 复制到 `.cursor/rules/`（项目级）或 `~/.cursor/rules/`（用户级）：

```
python scripts/install_cursor_rule.py --target user      # ~/.cursor/rules
python scripts/install_cursor_rule.py --target project --project D:\myproj
```

该规则 `alwaysApply: true`，**每轮必注入**，正文只做两件事：读 latch、按 latch 决定是否套用本 skill。体积控制在 ~150 词，避免常驻 token 税。

**与 `caveman-ultra.mdc` 的分工**（两者可共存，禁互相覆盖）：

| | caveman-ultra | concise-mind |
|--|---------------|--------------|
| 管什么 | 语气层面的**短**（砍连接词/虚词） | 模式层面的**该保留什么**（DOC/PLAN/ARCH + Gate） |
| 状态 | 常驻 alwaysApply | latch 控制，可 OFF |
| 冲突时 | 叠加会双重压缩 → 本 skill 在 latch 未 ON 时**不碰文风** |

### 3.2 AGENTS.md 型宿主（Codex / Jules / Copilot / Zed）

把 `assets/AGENTS.snippet.md` 追加进 `AGENTS.md`。无 `alwaysApply` 概念时，靠 AGENTS.md 常驻注入 + latch 文件。

### 3.3 Claude Code

`~/.claude/skills/concise-mind/`，触发靠 `description`；仍建议把 snippet 写进 `CLAUDE.md` 以获得常驻兜底。

### 3.4 WorkBuddy

写 `~/.workbuddy/MEMORY.md` 一行即可（用户级常驻记忆）：

```
- 简洁模式已装：命中 /concise-mind 后整个会话生效（含文档与 Plan），OFF=stop concise-mind。
```

## 4. 故障恢复

| 症状 | 处置 |
|------|------|
| 新会话里它又「不生效」 | 正常：`scope=session` 不跨会话。要跨会话 → `latch.py pin` |
| 同名 skill 冲突 | `~/.cursor/skills/concise-mind/` 若指向**别的**同名 skill，必须改名或归档，否则 Cursor 加载次序不确定 |
| 输出了长文 | 检查是否落在 DOC 模式（DOC 允许长，但必须无套话、每段承重）；CHAT/CODE 超预算即视为失败 |
| 用户说「别压了」但词不在 OFF 表 | 补入 `off_words`，不要默认关闭 |
