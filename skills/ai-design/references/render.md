# render · 渲染、构图审计与工具链

**规则：没渲染成功 + 没通过构图审计，不算出图。** 只贴 DSL 源码不算交付。

## 用法

```bash
node scripts/render.mjs docs/diagram/                        # 渲染目录 → assets/（单 Chrome 批量 + 未变跳过 + 审计）
node scripts/render.mjs docs/diagram/ --strict               # 审计超标 → 退出码 1（交付前必跑）
node scripts/render.mjs docs/diagram/ --variants             # 额外出 主题×方向 变体
node scripts/render.mjs <输入.mmd|.md> <输出.svg|.png>        # 单文件；.md 自动抽代码块
node scripts/render.mjs --check                              # 探测工具链
node scripts/render.mjs docs/diagram/ --json                 # 机器可读结果（含审计明细）
```

| 选项 | 作用 |
|------|------|
| `--theme light\|dark\|none` | 主题，默认 `light`；`none` = Mermaid 原始默认样式 |
| `--bg <color>` | 背景，默认随主题（`#ffffff` / `#0d1117`） |
| `--direction tb\|lr` | 强制流程图方向；**只对 `flowchart` 生效**，其余图型忽略并告警 |
| `--layout auto\|dagre\|elk` | 布局引擎。`auto`（默认）= dagre 先算，**审计不达标才**追加 elk 复算取优 |
| `--strict` | 任一图审计超标 → 退出码 1 |
| `--no-audit` | 关掉审计输出 |
| `--variants` | 产出 `主题(浅/深) × 方向(竖/横)` 网格 → `assets/variants/`，供查看页切换 |
| `--force` | 忽略增量缓存，强制重渲（**换了主题/布局才需要**） |
| `--all-blocks` | 允许一个 `.md` 渲多个图块（**默认关**） |

## 构图审计（出图后自动跑）

渲染完顺带体检，把「一目了然」变成可机检指标。阈值 SSOT = `references/layout.md`。

```
构图审计（预算见 references/layout.md）:
  FAIL docs\diagram\assets\design.svg  935x2105 r=0.44  节点26 边25 填充14% [elk]
        - 节点 26 > 12（该砍信息进表）
        - 边 25 > 14
        - 存在 4 处孤岛空档
  ok   templates\assets\flowchart.svg  413x786 r=0.53  节点7 边6 填充22% [elk]
  → 1/2 张超标。先把信息砍进表（§关键数字/§排查脉络/§解决方案），再考虑换方向或 --layout elk。
```

| 指标 | 判据 | 报出来意味着 |
|------|------|-------------|
| 画布宽 | 320 ~ 1200px | 上限：文档里按 900~1200 显示，超了字号被等比压小（1952px → 7px 字）。下限：比 320 窄就是一根竖条 |
| 宽高比 | 0.32 ~ 2.6 | 上限治「横幅」；下限只兜「塌成竖条」—— 纵向长图本身没问题 |
| 节点 / 边 | ≤12 / ≤14 | 信息超载，**该砍进表** |
| 填充率 | ≥12% | 节点面积 / 内容包围盒，太低 = 图被拉散 |
| 孤岛空档 | 0 处 | 图里出现「一大片空地」 |
| 单行标签 | ≤26 字 | 标签越长画布越宽 |

- **只有 flowchart 系列算节点账**；sequence / state / er / architecture 只量画布宽与宽高比。
- 结果会写进 `.diagramrender.json`，跳过的图也能在报告里看到。
- **超标的第一动作是砍信息进表**，不是换主题。

## 布局引擎（dagre / ELK）

| 引擎 | 特点 |
|------|------|
| `dagre`（主题默认） | 阅读顺序自然；但容易留大片空白、跨 subgraph 边会让 `direction` 静默失效 |
| `elk` | 填空白的能手（实测 1952×2319 → **935×2123**）；但会打乱阅读顺序（主链绕行、cluster 框易错位） |
| `auto`（默认） | dagre 先算；审计有违规才追加一次 elk，**取违规少者**。达标时零额外成本 |

**别急着上 elk**：elk 治「留白」不治「看不懂」。先把信息量砍下来。

## 查看页（横竖 + 主题 + 缩放）

```bash
node scripts/viewer.mjs docs/diagram/design.md            # → docs/diagram/design.viewer.html
node scripts/viewer.mjs docs/diagram/                     # 目录里每个含图的 .md 各出一个
```

单个自包含 HTML（4 个变体 SVG 内联、无外部依赖，可直接发给别人）。三组开关：**方向**（非 `flowchart` 自动隐藏）· **主题** · **缩放**（画布很宽的图靠"原始"横向滚动看细节）。内部就是调 `render.mjs --variants`，**增量缓存照样生效**。

## 效率

| 机制 | 说明 |
|------|------|
| **单次 Chrome** | 一次 `puppeteer.launch` 服务目录下全部图，不是每图一次冷启动 |
| **增量跳过** | 按 `sha1(主题\|背景\|方向\|布局\|图型\|源码)` 记进 `.diagramrender.json`，未变直接复用 |
| **A/B 仅在必要时** | 只有 dagre 结果审计违规时才多渲一次 elk |

实测：4 张图全量 ≈ 4.6s；6 张模板 ≈ 9.5s；**5 个变体一次 Chrome ≈ 8.5s**；全部未变 **≈ 0.19s**。**别加 `--force` 除非真的改了主题或怀疑产物损坏。**

## 一文一图

`render.mjs` 默认**一个 `.md` 只渲第一个图块**，多图块打警告并忽略其余（多主题 → 拆多份文档）。

## 工具链位置（按序探测）

1. `<项目>/.tools/diagram/node_modules/`（项目本地，推荐）
2. `<skill>/.tools/diagram/node_modules/`
3. `~/.workbuddy-ai/binaries/diagram/node_modules/`

**注意**：按 `process.cwd()` 向上找 6 层。从不含 `.tools/diagram` 的目录调用会报「未安装」—— 到项目根执行即可。

## 首次安装（国内镜像 · 装到非系统盘）

```bash
mkdir -p .tools/diagram && cd .tools/diagram
export PUPPETEER_SKIP_DOWNLOAD=true                        # 复用系统 Chrome，不下载 Chromium
export PUPPETEER_EXECUTABLE_PATH="/c/Program Files/Google/Chrome/Application/chrome.exe"
npm init -y && npm i @mermaid-js/mermaid-cli --registry=https://registry.npmmirror.com
```

`@mermaid-js/layout-elk` 随 mermaid-cli 一起装（`--layout elk/auto` 依赖它，`--check` 会报有没有）。
**不要装 `@terrastruct/d2`**（v6.1 已下线，理由见下）。

## 主题

`assets/mermaid-theme.json`（浅）/ `mermaid-theme-dark.json`（暗）是**视觉基线**，直接作为 `mermaidConfig` 传给 Mermaid：

- **三级字阶**：带标题 15px/600（`.cluster-label`）> 节点 15px > 边注 13px（`.edgeLabel`）
- **形状语言**：节点圆角 8 + 极浅投影；带框圆角 10 + 冷灰底 `#f4f8fd`
- 副标题降级：`.nodeLabel .s` → 13px 次要色（配合 `"标题<br/><span class='s'>副标题</span>"`）
- `archEdgeColor` / `archEdgeArrowColor` / `archGroupBorderColor`：`architecture-beta` **不走通用变量**，漏了就还是默认紫
- `fillType0..7` 是 `classDef` 未指定时的兜底色阶；分图型块控制 `curve`/`nodeSpacing`/`rankSpacing`

改主题只动这两个 JSON，不用改图源。

## 渲染细节

| 引擎 | 调用 | 注意 |
|------|------|------|
| Mermaid | `renderMermaid(browser, src, 'svg', { backgroundColor, mermaidConfig })` | 复用同一 `browser`；从 `mermaid-cli/src/index.js` 直接 import |

### 关于「elk 挂死」（v6.5 复核结论）

v6.1 记的「`layout:'elk'` 挂死 >8 分钟」是 **D2（terrastruct）** 链路的坑，**不是 Mermaid 侧**：
`mermaid-cli` 在渲染页里**无条件**注册 `@mermaid-js/layout-elk`，本机复测（mermaid 11.17.2）秒级出图、几何与 dagre 明显不同 → 确实生效。故 v6.5 重新开放 `--layout elk`。

D2 仍下线的三条理由（对 D2 依然成立）：D2 的 elk 挂死 >8 分钟 ｜ ESM/CJS 解析冲突（`require.resolve` 拿到 `node-cjs/index.js`）｜ 中文字体 `simhei.ttf` base64 12.4 MB 进 WASM worker，挂死 >9 分钟。
**结论**：Mermaid `architecture-beta` 足够表达分层架构；`.d2` 输入显式拒绝。

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

## 产物

```
docs/diagram/
├── design.md            唯一技术文档（图源在这里）
├── design.viewer.html   查看页（自包含，横竖/主题可切换）
└── assets/
    ├── design.svg       主产物 = light + 源方向（md 里引用的就是它）
    └── variants/        --variants 产出的 4 个组合，供查看页切换
```

md 里用 `![](assets/design.svg)` 引用。**`assets/**` 全部可重建**，不要手工编辑 —— 改图只改 md 里的图块，重跑即可。
