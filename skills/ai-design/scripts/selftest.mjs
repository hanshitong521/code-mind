#!/usr/bin/env node
// selftest.mjs — DiagramMind 自测
//
// 每条都是断言，不是"能跑就行":
//   1. 工具链齐备（Chrome / mermaid-cli / puppeteer）
//   2. 批量渲染 —— 一次进程渲染目录下全部图
//   3. 增量跳过 —— 源未变时第二次不重渲
//   4. 一文一图 —— 多图块的 .md 只产 1 张 SVG
//   5. 主题生效 —— 中文无衬线字体族 + classDef 语义色 + architecture-beta 非默认紫
//   6. D2 已下线 —— .d2 输入被拒绝且给出替代方案
//   7. 变体 —— --variants 出 主题×方向 网格，横竖尺寸不同、深浅配色不同
//   8. 查看页 —— viewer.mjs 出含三组开关与多面板的自包含 HTML
//   9. 模板 —— templates/ 下每个模板都能渲染成功
import { spawnSync } from 'node:child_process';
import { mkdirSync, writeFileSync, existsSync, readFileSync, readdirSync, rmSync, statSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SKILL_ROOT = resolve(__dirname, '..');
const OUT = join(SKILL_ROOT, 'evals', 'out');
const ASSETS = join(OUT, 'assets');
const VTEST = join(SKILL_ROOT, 'evals', 'viewer-test');
const TEMPLATES = join(SKILL_ROOT, 'templates');
const RENDER = join(__dirname, 'render.mjs');
const VIEWER = join(__dirname, 'viewer.mjs');
// 断言值从主题文件取，避免"改了主题就误报"这类假失败（v6.5）
const LIGHT_THEME = JSON.parse(readFileSync(join(SKILL_ROOT, 'assets', 'mermaid-theme.json'), 'utf8')).themeVariables;

let pass = 0;
const failures = [];
function check(name, cond, detail = '') {
  if (cond) { pass++; console.log(`  PASS  ${name}`); }
  else { failures.push(`${name}${detail ? ` — ${detail}` : ''}`); console.log(`  FAIL  ${name}${detail ? ` — ${detail}` : ''}`); }
}
function run(script, args) {
  const t = Date.now();
  const r = spawnSync(process.execPath, [script, ...args], { encoding: 'utf8' });
  return { ...r, ms: Date.now() - t, out: `${r.stdout || ''}${r.stderr || ''}` };
}
const svgSize = (p) => {
  const m = readFileSync(p, 'utf8').match(/viewBox="([-\d.]+) ([-\d.]+) ([\d.]+) ([\d.]+)"/);
  return m ? { w: Number(m[3]), h: Number(m[4]) } : null;
};

// ── 准备样例 ─────────────────────────────────────────────
rmSync(OUT, { recursive: true, force: true });
rmSync(VTEST, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });
mkdirSync(VTEST, { recursive: true });

const samples = {
  'a-flow.mmd': `flowchart TD
  Start(["👤 业务开始"]):::actor --> Check{"🚦 条件判断"}:::decision
  Check -->|"✅ 通过"| Proc["⚙️ 业务处理"]:::step
  Check -->|"⛔ 失败"| End["🚫 结束"]:::out
  Proc --> Save[("💾 数据保存")]:::store
  Save --> Notify["📣 结果通知"]:::step
  classDef actor fill:#fde8e8,stroke:#e07272,color:#7a1f1f,stroke-width:1.5px
  classDef decision fill:#fdf2e0,stroke:#dda94f,color:#5c3c07,stroke-width:1.5px
  classDef step fill:#e8f0fe,stroke:#5b8fd6,color:#173a6b,stroke-width:1.5px
  classDef out fill:#e6f6ec,stroke:#5aa877,color:#14452a,stroke-width:1.5px
  classDef store fill:#f2eafd,stroke:#a184d6,color:#3a2159,stroke-width:1.5px
`,
  'b-seq.mmd': `sequenceDiagram
  autonumber
  actor U as 👤 用户
  participant API as 🔧 服务
  participant DB as 💾 数据库
  U->>API: 请求
  API->>DB: 查询
  DB-->>API: 返回
  API-->>U: 响应
`,
  'c-arch.mmd': `architecture-beta
    group client(cloud)[客户端]
    service user(internet)[用户] in client
    group app(cloud)[应用层]
    service api(server)[API 网关] in app
    service svc(server)[业务服务] in app
    group data(cloud)[数据层]
    service db(database)[主库] in data
    user:R -- L:api
    api:R -- L:svc
    svc:B -- T:db
`,
  // 故意塞 2 个图块 —— 验证「一文一图」只渲第一张
  'e-multi.md': `# 多图块文档

\`\`\`mermaid
flowchart LR
  A["第一张"]:::step --> B["保留"]:::step
  classDef step fill:#e8f0fe,stroke:#5b8fd6,color:#173a6b,stroke-width:1.5px
\`\`\`

\`\`\`mermaid
flowchart LR
  C["第二张"] --> D["应被忽略"]
\`\`\`
`,
};
for (const [name, body] of Object.entries(samples)) writeFileSync(join(OUT, name), body);

// 查看页测试用的小文档
writeFileSync(join(VTEST, 'demo.md'), `# 查看页测试文档

> 验证横竖 + 主题切换。

![demo](assets/demo.svg)

\`\`\`mermaid
flowchart TD
  S(["👤 起点"]):::actor --> C{"判据?"}:::decision
  C -->|"是"| P["⚙️ 处理"]:::step
  C -->|"否"| F["🚫 结束"]:::fail
  P --> E(["📦 终点"]):::done
  classDef actor fill:#fde8e8,stroke:#e07272,color:#7a1f1f,stroke-width:1.5px
  classDef decision fill:#fdf2e0,stroke:#dda94f,color:#5c3c07,stroke-width:1.5px
  classDef step fill:#e8f0fe,stroke:#5b8fd6,color:#173a6b,stroke-width:1.5px
  classDef fail fill:#fde8e8,stroke:#e07272,color:#7a1f1f,stroke-width:1.5px
  classDef done fill:#e6f6ec,stroke:#5aa877,color:#14452a,stroke-width:1.5px
\`\`\`
`);

// ── 1. 工具链 ────────────────────────────────────────────
console.log('--- 1. 工具链 ---');
const chk = run(RENDER, ['--check']);
check('render.mjs --check 退出码 0', chk.status === 0, `exit=${chk.status}`);
for (const key of ['Chrome', 'mermaid-cli', 'puppeteer']) {
  const line = chk.out.split('\n').find((l) => l.startsWith(key)) || '';
  check(`${key} 可用`, !line.includes('❌') && line.trim() !== '', line.trim());
}
console.log(chk.out.split('\n').filter(Boolean).map((l) => `        ${l}`).join('\n'));

// ── 2. 批量渲染 ──────────────────────────────────────────
console.log('\n--- 2. 批量渲染（单次 Chrome） ---');
const r1 = run(RENDER, [OUT]);
const svgs = existsSync(ASSETS) ? readdirSync(ASSETS).filter((f) => f.endsWith('.svg')) : [];
check('渲染退出码 0', r1.status === 0, `exit=${r1.status}`);
check('产出 4 张 SVG（3 样例 + 多图块文档的第 1 张）', svgs.length === 4, `实际 ${svgs.length}: ${svgs.join(', ')}`);
check('单次进程渲染（日志只出现一次「启动 Chrome」）', (r1.out.match(/启动 Chrome/g) || []).length === 1,
  `出现 ${(r1.out.match(/启动 Chrome/g) || []).length} 次`);
console.log(`        耗时 ${r1.ms} ms`);

// ── 3. 增量跳过 ──────────────────────────────────────────
console.log('\n--- 3. 增量跳过 ---');
const r2 = run(RENDER, [OUT]);
check('第二次全部跳过', /成功 0 \/ 跳过 4/.test(r2.out), (r2.out.split('\n').find((l) => l.includes('[render]')) || '').trim());
check('增量比重渲快', r2.ms < r1.ms, `${r2.ms} ms vs ${r1.ms} ms`);
console.log(`        耗时 ${r2.ms} ms（全量 ${r1.ms} ms）`);

// ── 4. 一文一图 ──────────────────────────────────────────
console.log('\n--- 4. 一文一图 ---');
check('多图块 .md 只产 1 张 SVG', existsSync(join(ASSETS, 'e-multi.svg')) && !existsSync(join(ASSETS, 'e-multi-2.svg')));
check('多图块有告警', /只渲染第 1 个/.test(r1.out));
const multi = readFileSync(join(ASSETS, 'e-multi.svg'), 'utf8');
check('产物是第一张图（含"保留"）', multi.includes('保留'));
check('产物不含第二张图（无"应被忽略"）', !multi.includes('应被忽略'));

// ── 5. 主题生效 ──────────────────────────────────────────
console.log('\n--- 5. 主题生效 ---');
const flowSvg = readFileSync(join(ASSETS, 'a-flow.svg'), 'utf8');
check('中文字体族已注入', flowSvg.includes('Microsoft YaHei'));
check('classDef 语义色已生效', flowSvg.includes('#fde8e8') && flowSvg.includes('#e8f0fe'));
const archSvg = readFileSync(join(ASSETS, 'c-arch.svg'), 'utf8');
check('architecture-beta 走主题（非默认紫 #9370DB）', !archSvg.includes('#9370DB'), '仍是默认色');
check('architecture-beta 边色已注入', archSvg.includes(LIGHT_THEME.archEdgeColor), `期望 ${LIGHT_THEME.archEdgeColor}`);
check('architecture-beta 分组边框色已注入', archSvg.includes(LIGHT_THEME.archGroupBorderColor), `期望 ${LIGHT_THEME.archGroupBorderColor}`);

// ── 6. D2 已下线 ─────────────────────────────────────────
console.log('\n--- 6. D2 下线确认 ---');
writeFileSync(join(OUT, 'f-legacy.d2'), 'a -> b\n');
const r3 = run(RENDER, [join(OUT, 'f-legacy.d2'), join(OUT, 'f-legacy.svg')]);
check('.d2 输入被拒绝并给出替代方案', /D2 已在 v6\.1 下线/.test(r3.out), r3.out.trim().slice(0, 120));
check('.d2 不产出文件', !existsSync(join(OUT, 'f-legacy.svg')));

// ── 7. 变体（横竖 × 主题） ───────────────────────────────
console.log('\n--- 7. 变体（横竖 × 主题） ---');
const r4 = run(RENDER, ['--force', '--variants', VTEST]);
check('变体渲染退出码 0', r4.status === 0, `exit=${r4.status}`);
check('变体仍单次 Chrome', (r4.out.match(/启动 Chrome/g) || []).length === 1,
  `出现 ${(r4.out.match(/启动 Chrome/g) || []).length} 次`);
const VD = join(VTEST, 'assets', 'variants');
const tbL = join(VD, 'demo.tb.light.svg');
const lrL = join(VD, 'demo.lr.light.svg');
const tbD = join(VD, 'demo.tb.dark.svg');
const lrD = join(VD, 'demo.lr.dark.svg');
check('产出 4 个组合', [tbL, lrL, tbD, lrD].every((p) => existsSync(p)));
const sTb = tbL && existsSync(tbL) ? svgSize(tbL) : null;
const sLr = lrL && existsSync(lrL) ? svgSize(lrL) : null;
check('竖排是"高瘦"', !!sTb && sTb.h > sTb.w, sTb ? `${sTb.w}×${sTb.h}` : '缺失');
check('横排是"矮胖"', !!sLr && sLr.w > sLr.h, sLr ? `${sLr.w}×${sLr.h}` : '缺失');
check('横竖尺寸确实不同', !!sTb && !!sLr && (sTb.w !== sLr.w || sTb.h !== sLr.h));
check('暗色背景生效', readFileSync(tbD, 'utf8').includes('background-color:#0d1117'));
check('浅色背景生效', readFileSync(tbL, 'utf8').includes('background-color:#ffffff'));
check('暗色文字色生效', readFileSync(tbD, 'utf8').includes('#e6edf3'));
console.log(`        耗时 ${r4.ms} ms`);

// ── 8. 查看页 ────────────────────────────────────────────
console.log('\n--- 8. 查看页 ---');
const r5 = run(VIEWER, [join(VTEST, 'demo.md')]);
const vhtml = join(VTEST, 'demo.viewer.html');
check('viewer.mjs 退出码 0', r5.status === 0, `exit=${r5.status} ${r5.out.trim().slice(0, 160)}`);
check('产出 HTML', existsSync(vhtml));
if (existsSync(vhtml)) {
  const h = readFileSync(vhtml, 'utf8');
  check('三组开关齐全（方向/主题/缩放）',
    h.includes('data-set="dir:tb"') && h.includes('data-set="dir:lr"') &&
    h.includes('data-set="theme:light"') && h.includes('data-set="theme:dark"') &&
    h.includes('data-set="zoom:fit"') && h.includes('data-set="zoom:actual"'));
  check('4 个面板', (h.match(/class="pane"/g) || []).length === 4, `实际 ${(h.match(/class="pane"/g) || []).length}`);
  check('SVG 已内联（无外部依赖）', (h.match(/<svg /g) || []).length >= 4);
  check('无残留外部引用', !/src="assets\//.test(h) && !/<img /.test(h));
  check('标题取到 H1', h.includes('查看页测试文档'));
  console.log(`        ${(statSync(vhtml).size / 1024).toFixed(0)} KB`);
}
console.log(`        耗时 ${r5.ms} ms`);

// ── 9. 模板 ──────────────────────────────────────────────
console.log('\n--- 9. 模板 ---');
const tplFiles = readdirSync(TEMPLATES).filter((f) => f.endsWith('.md') && f !== 'README.md');
check('模板文件齐全（>=6）', tplFiles.length >= 6, `实际 ${tplFiles.length}: ${tplFiles.join(', ')}`);
for (const f of tplFiles) {
  const md = readFileSync(join(TEMPLATES, f), 'utf8');
  const blocks = (md.match(/```mermaid/g) || []).length;
  check(`${f} 恰好 1 个图块`, blocks === 1, `实际 ${blocks} 个`);
  check(`${f} 图块里无 <尖括号> 占位`, !/```mermaid[\s\S]*?```/.test(md) || !/(?<!<br)<[A-Za-z\u4e00-\u9fa5]/.test(md.match(/```mermaid[\s\S]*?```/)[0].replace(/<br\s*\/?>/g, '')),
    'htmlLabels 会吃掉它');
}
const r6 = run(RENDER, [TEMPLATES]);
check('全部模板渲染成功', r6.status === 0 && /失败 0/.test(r6.out),
  (r6.out.split('\n').find((l) => l.includes('[render]')) || '').trim());
console.log(`        耗时 ${r6.ms} ms`);

// ── 10. 构图审计 ──────────────────────────────────────────
// 审计是「一目了然」的可执行版本，必须被保护：健康图不误报 + 坏图必须报。
console.log('\n--- 10. 构图审计 ---');
const { auditFigure, BUDGET } = await import('./render.mjs'); // 同目录，相对路径即可
const goodSvg = readFileSync(join(ASSETS, 'a-flow.svg'), 'utf8');
const good = auditFigure(goodSvg);
check('审计能量出画布', good.w > 0 && good.h > 0);
check('审计能数出节点', good.nodes >= 3, `数到 ${good.nodes}`);
check('审计能认出图型', good.supported === true, `kind=${good.kind}`);
check('健康图不误报', good.violations.length === 0, good.violations.join('; '));

const wide = auditFigure('<svg width="3000" height="200" aria-roledescription="flowchart-v2"></svg>');
check('超宽画布被判违规', wide.violations.some((v) => v.includes('画布宽')), JSON.stringify(wide.violations));
const tallNarrow = auditFigure('<svg width="200" height="3000" aria-roledescription="flowchart-v2"></svg>');
check('畸形宽高比被判违规', tallNarrow.violations.some((v) => v.includes('宽高比')), JSON.stringify(tallNarrow.violations));
const nonFlow = auditFigure('<svg width="600" height="400" aria-roledescription="sequence"></svg>');
check('非 flowchart 不算节点账', nonFlow.supported === false && nonFlow.nodes === 0);
check('非 flowchart 仍量画布', nonFlow.violations.length === 0 && nonFlow.w === 600);
check('预算与文档一致（layout.md 的 1200/12/14）', BUDGET.maxWidth === 1200 && BUDGET.maxNodes === 12 && BUDGET.maxEdges === 14);

// ── 汇总 ─────────────────────────────────────────────────
console.log(`\n[selftest] 通过 ${pass} / 失败 ${failures.length}`);
for (const f of failures) console.log(`  ! ${f}`);
process.exit(failures.length ? 1 : 0);
