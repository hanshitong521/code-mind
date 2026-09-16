# toolchain · 工具链、主题与查看页

**渲染命令与构图审计在 `render.md`；本页管「环境装在哪、外观长什么样、出问题怎么查」。**

## 工具链位置（按序探测）

1. `<项目>/.tools/diagram/node_modules/`（项目本地，推荐）
2. `<skill>/.tools/diagram/node_modules/`
3. `~/.workbuddy-ai/binaries/diagram/node_modules/`

**注意**：按 `process.cwd()` 向上找 6 层。从不含 `.tools/diagram` 的目录调用会报「未安装」—— 到项目根执行即可。
**工具链装到项目 `.tools/diagram`**：项目隔离，一行 `rm -rf .tools` 就能全清，不污染宿主环境。

## 首次安装（国内镜像 · 装到非系统盘）

```bash
mkdir -p .tools/diagram && cd .tools/diagram
export PUPPETEER_SKIP_DOWNLOAD=true                        # 复用系统 Chrome，不下载 Chromium
export PUPPETEER_EXECUTABLE_PATH="/c/Program Files/Google/Chrome/Application/chrome.exe"
npm init -y && npm i @mermaid-js/mermaid-cli --registry=https://registry.npmmirror.com
```

`@mermaid-js/layout-elk` 随 mermaid-cli 一起装（`--layout elk/auto` 依赖它，`--check` 会报有没有）。
**不要装 `@terrastruct/d2`**（v6.1 已下线，理由见 `render.md` §渲染细节）。

## 主题（视觉基线）

`assets/mermaid-theme.json`（浅）/ `mermaid-theme-dark.json`（暗）是**视觉基线**，直接作为 `mermaidConfig` 传给 Mermaid：

- **三级字阶**：带标题 15px/600（`.cluster-label`）> 节点 15px > 边注 13px（`.edgeLabel`）
- **形状语言**：节点圆角 8 + 极浅投影；带框圆角 10 + 冷灰底 `#f4f8fd`
- **`flowchart` 用 `curve: basis`**（平滑折线，比默认 `basis` 以外的折角更像成品）；**长链走 `LR`**
- 副标题降级：`.nodeLabel .s` → 13px 次要色（配合 `"标题<br/><span class='s'>副标题</span>"`）
- `archEdgeColor` / `archEdgeArrowColor` / `archGroupBorderColor`：`architecture-beta` **不走通用变量**，漏了就还是默认紫
- `fillType0..7` 是 `classDef` 未指定时的兜底色阶；分图型块控制 `curve`/`nodeSpacing`/`rankSpacing`

改主题只动这两个 JSON，不用改图源。

### 视觉基线（不达标就是白画）

| # | 基线 | 细则 |
|---|------|------|
| 1 | 走 `assets/mermaid-theme.json` / `mermaid-theme-dark.json`，**别加 `--theme none`** | 本节 |
| 2 | 双行标签 `标题<br/>副标题`（副标题降级用 `<span class='s'>`） | `mermaid.md` · `annotation.md` |
| 3 | `classDef` **只给关键节点**（症状/瓶颈/对策/排除项），普通步骤共用一色 | `mermaid.md` |
| 4 | 分层架构用 `architecture-beta` 内置图标（`cloud`/`server`/`database`/`disk`/`internet`） | `router.md` |
| 5 | `flowchart` 用 `curve: basis`；长链走 `LR` | 本节 · `layout.md` |

## 查看页（横竖 + 主题 + 缩放）

```bash
node scripts/viewer.mjs docs/diagram/design.md            # → docs/diagram/design.viewer.html
node scripts/viewer.mjs docs/diagram/                     # 目录里每个含图的 .md 各出一个
```

单个自包含 HTML（4 个变体 SVG 内联、无外部依赖，可直接发给别人）。三组开关：**方向**（非 `flowchart` 自动隐藏）· **主题** · **缩放**（画布很宽的图靠"原始"横向滚动看细节）。内部就是调 `render.mjs --variants`，**增量缓存照样生效**。

## 失败处理

| 症状 | 处理 |
|------|------|
| `mermaid-cli 未安装` | 打印安装命令，**不要**静默降级为"只输出源码"；也检查 cwd 是不是在项目根 |
| Mermaid 报 parse error | 回 `mermaid.md` 陷阱表，修 DSL 后重试 |
| `Diagrams beginning with --- are not valid` | 抽源码时没 dedent，YAML front-matter 还带缩进 |
| 中文变方块 | Mermaid 走 Chrome 渲染，一般不会；确认 Chrome 可用 |
| 首次渲染慢 | 冷启动，属正常；第二次走增量（0.2s） |
| 审计报「画布宽超标」 | **先砍节点进表**；确认要保留再试 `--layout elk` 或换 `--direction` |
| `elk 未改善，保留 dagre` | 正常提示：问题在信息量，不在引擎 |
| `elk 复算失败（…）` | 降级继续用 dagre，不阻断；`--check` 看 `layout-elk` 是否装上 |
| `.d2` 被拒绝 | 预期行为，D2 已下线；改用 `architecture-beta` |
