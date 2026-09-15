# 决策记录

> 只记「为什么这么选」，不重复图里已有的信息。

| # | 决策 | 备选 | 理由 | 日期 |
|---|------|------|------|------|
| 1 | ai-design 改造为 DiagramMind | 新建 ai-diagram / 保留 Handoff 并存 | 用户拍板：设计层直接以图承载 | 2026-09-14 |
| 2 | 图引擎 V1 只做 Mermaid + D2 | 5 种全上 / 只做 Mermaid | Mermaid 覆盖 80% 场景，D2 补复杂分层 | 2026-09-14 |
| 3 | ~~D2 用 WASM（`@terrastruct/d2`）而非二进制~~ | 官方 d2.exe | 免下载 Go 二进制 —— **已被决策 8 推翻** | 2026-09-14 |
| 4 | Mermaid 复用系统 Chrome，跳过 Chromium 下载 | 让 puppeteer 下 Chromium | 省 ~300MB 且不落 C 盘 | 2026-09-14 |
| 5 | 工具链装到项目 `.tools/diagram` | 全局 npm / C 盘 | 项目隔离，可整体删除，不污染宿主 | 2026-09-14 |
| 6 | ~~D2 中文字体经 base64 传入~~ | 直接传 Uint8Array | Go 侧 `[]byte` 按 base64 解码 —— **已被决策 8 推翻** | 2026-09-14 |
| 7 | render.mjs 支持从 `.md` 抽取代码块 | 只支持独立 `.mmd/.d2` | 文档与图同源，避免双份维护 | 2026-09-14 |
| 8 | **砍掉 D2，V1 只留 Mermaid** | 修 elk / 换小字体子集 / 保留但标注实验 | 三条独立的坑，见下表 | 2026-09-14 |
| 9 | **一个技术文档 = 一张图**（硬约束） | 一个目录多份图文档 | 用户拍板：图多了没人看，token 也白烧 | 2026-09-14 |
| 10 | 主题 JSON 作为视觉基线，默认注入 | 每张图手写样式 | 同一份 DSL，过不过主题就是「像 demo」和「像草稿」的差别 | 2026-09-14 |
| 11 | 单 Chrome 批量 + hash 增量跳过 | 每图一次 mmdc 子进程 | 2932 ms/张 → 999 ms/张；未变时 0.19s | 2026-09-14 |
| 12 | 交付物收敛为 1 文档 + 1 图 | 保留 overview/architecture/workflow/sequence/risks 六份 | 决策 9 的直接推论；其余图型降级为 `evals/samples/` 范例 | 2026-09-14 |

## 决策 8：为什么砍掉 D2

三条坑各自独立，每条都足以否决：

| # | 症状 | 实测 |
|---|------|------|
| 1 | `layout: 'elk'` 挂死 | >8 分钟无输出；换默认 dagre 才 0.4s |
| 2 | ESM/CJS 解析冲突 | 包声明 `"type":"module"`，`require.resolve` 命中 `node-cjs/index.js` → `module is not defined` |
| 3 | 中文字体往返 | `simhei.ttf` 9.3 MB → base64 12.4 MB，每次渲染 `JSON.stringify` 进 WASM worker → 挂死 >9 分钟 |

**核心矛盾**：D2 不加中文字体就出方块，加了就挂死。中文场景下不可用。
替代方案：Mermaid `architecture-beta` 已能表达分层 + 图标 + 分组，覆盖 D2 的主要用例。

## 说明

- 决策 4/5 是为了**不污染宿主环境**：工具链装在项目内，Chrome 复用系统的，一行 `rm -rf .tools` 就能全清。
- 决策 7 让 `docs/diagram/design.md` 成为唯一真源，`assets/*.svg` 是可重建产物。
- 决策 3/6 的教训：**方案选型要按「中文能不能用」先验一遍**，别等实现完才发现字体是 9MB。
