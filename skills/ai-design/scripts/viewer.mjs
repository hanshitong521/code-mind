#!/usr/bin/env node
// viewer.mjs — 把一份图文档装配成自包含的查看页（横竖切换 + 主题切换 + 缩放）
//
// 产物是**单个 HTML**：SVG 全部内联，无外部依赖，可直接丢给任何人打开。
//
// 用法:
//   node viewer.mjs <文档.md>             → 同目录 <stem>.viewer.html
//   node viewer.mjs <文档.md> <out.html>
//   node viewer.mjs <目录>                 → 每个含图块的 .md 各出一个
//   node viewer.mjs <文档.md> --force      → 强制重渲变体（默认走增量）
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname, resolve, basename, extname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const RENDER = join(__dirname, 'render.mjs');
const THEMES = ['light', 'dark'];
const DIRECTIONS = ['tb', 'lr'];

const argv = process.argv.slice(2);
const force = argv.includes('--force');
const targets = argv.filter((a) => !a.startsWith('--'));

if (targets.length === 0) {
  console.error('用法: node viewer.mjs <文档.md|目录> [out.html] [--force]');
  process.exit(1);
}

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function docTitle(md, stem) {
  const m = md.match(/^#\s+(.+)$/m);
  return m ? m[1].trim() : stem;
}

function hasFlowchart(md) {
  const m = md.match(/```mermaid[ \t]*\r?\n([\s\S]*?)```/);
  return !!m && /^\s*flowchart\b/m.test(m[1]);
}

function readSvg(p) {
  if (!existsSync(p)) return null;
  return readFileSync(p, 'utf8')
    .replace(/<\?xml[^>]*\?>/g, '')
    .replace(/<!DOCTYPE[^>]*>/gi, '')
    .trim();
}

function svgSize(svg) {
  const m = svg && svg.match(/viewBox="([-\d.]+) ([-\d.]+) ([\d.]+) ([\d.]+)"/);
  if (!m) return null;
  return { w: Math.round(Number(m[3])), h: Math.round(Number(m[4])) };
}

// 给 SVG 补上显式 width/height，否则内联后有些浏览器不显示
function withSize(svg, size) {
  if (!svg || !size) return svg;
  return svg.replace(/<svg\b([^>]*?)\swidth="[^"]*"/, '<svg$1').replace(
    /<svg\b/,
    `<svg width="${size.w}" height="${size.h}"`,
  );
}

const CSS = `
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
  margin: 0; background: #eef1f6; color: #1f2933;
  font-family: 'Segoe UI', 'Microsoft YaHei', system-ui, -apple-system, sans-serif;
}
body[data-theme="dark"] { background: #0b0f14; color: #e6edf3; }
header {
  position: sticky; top: 0; z-index: 10;
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
  padding: 12px 20px; background: #fff; border-bottom: 1px solid #dbe3ec;
  box-shadow: 0 1px 3px rgba(15,23,42,.06);
}
body[data-theme="dark"] header { background: #11171f; border-bottom-color: #262d36; box-shadow: none; }
h1 { font-size: 15px; margin: 0; font-weight: 600; }
.meta { font-size: 12px; color: #64748b; }
body[data-theme="dark"] .meta { color: #8b949e; }
.spacer { flex: 1; }
.group { display: flex; align-items: center; gap: 6px; }
.group > span { font-size: 12px; color: #64748b; }
body[data-theme="dark"] .group > span { color: #8b949e; }
button {
  font: inherit; font-size: 13px; padding: 5px 12px; cursor: pointer;
  border: 1px solid #c9d4e5; background: #f7f9fc; color: #1f2933; border-radius: 7px;
}
button:hover { background: #e8f0fe; border-color: #7ba7e8; }
button[aria-pressed="true"] { background: #e8f0fe; border-color: #5b8fd6; color: #173a6b; font-weight: 600; }
body[data-theme="dark"] button { background: #1b222c; border-color: #303842; color: #e6edf3; }
body[data-theme="dark"] button:hover { background: #24303e; border-color: #4d7cc7; }
body[data-theme="dark"] button[aria-pressed="true"] { background: #1b2b45; border-color: #4d7cc7; color: #cfe1ff; }
main { padding: 20px; }
.stage {
  border: 1px solid #dbe3ec; border-radius: 10px; overflow: auto;
  max-height: calc(100vh - 150px); background: #fff;
  box-shadow: 0 1px 3px rgba(15,23,42,.06);
}
body[data-theme="dark"] .stage { border-color: #262d36; box-shadow: none; }
.stage svg { display: block; }
.stage.fit svg { width: 100%; height: auto; }
.pane[hidden] { display: none; }
.legend { display: flex; gap: 16px; flex-wrap: wrap; margin: 14px 2px 0; font-size: 12px; color: #475569; }
body[data-theme="dark"] .legend { color: #8b949e; }
.legend i { display: inline-block; width: 11px; height: 11px; border-radius: 3px; margin-right: 5px; vertical-align: -1px; }
.legend em { font-style: normal; opacity: .7; }
`;

const JS = `
const panes = [...document.querySelectorAll('.pane')];
const stage = document.getElementById('stage');
const body = document.body;
const sizeEl = document.getElementById('size');
const state = { theme: 'light', dir: null, zoom: 'fit' };

function variants() {
  return panes.map((p) => ({ el: p, theme: p.dataset.theme, dir: p.dataset.dir || null }));
}

function apply() {
  const vs = variants();
  const wantDir = state.dir;
  let pick = vs.find((v) => v.theme === state.theme && (wantDir === null || v.dir === wantDir));
  if (!pick) pick = vs.find((v) => v.theme === state.theme);
  if (!pick) pick = vs[0];
  for (const v of vs) v.el.hidden = v.el !== pick.el;
  body.dataset.theme = state.theme;
  stage.classList.toggle('fit', state.zoom === 'fit');
  const w = pick.el.dataset.w, h = pick.el.dataset.h;
  if (w && h) sizeEl.textContent = w + ' × ' + h + ' px';
  for (const b of document.querySelectorAll('[data-set]')) {
    const [k, v] = b.dataset.set.split(':');
    b.setAttribute('aria-pressed', String(state[k] === (v === 'null' ? null : v)));
  }
}

for (const b of document.querySelectorAll('[data-set]')) {
  b.onclick = () => {
    const [k, v] = b.dataset.set.split(':');
    state[k] = v === 'null' ? null : v;
    apply();
  };
}
apply();
`;

function buildHtml({ title, docName, panes, hasFlow }) {
  const paneHtml = panes.map((p) => {
    const size = svgSize(p.svg);
    return `<div class="pane" data-theme="${p.theme}" data-dir="${p.dir || ''}" data-w="${size ? size.w : ''}" data-h="${size ? size.h : ''}"${p.primary ? '' : ' hidden'}>
${withSize(p.svg, size)}
</div>`;
  }).join('\n');

  const dirGroup = hasFlow ? `
    <div class="group"><span>方向</span>
      <button data-set="dir:tb">竖排</button>
      <button data-set="dir:lr">横排</button>
    </div>` : '';

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>${esc(title)} · 图查看器</title>
<style>${CSS}</style>
</head>
<body data-theme="light">
<header>
  <h1>${esc(title)}</h1>
  <span class="meta" id="size"></span>
  <span class="spacer"></span>${dirGroup}
  <div class="group"><span>主题</span>
    <button data-set="theme:light">浅色</button>
    <button data-set="theme:dark">深色</button>
  </div>
  <div class="group"><span>缩放</span>
    <button data-set="zoom:fit">适应</button>
    <button data-set="zoom:actual">原始</button>
  </div>
</header>
<main>
  <div class="stage fit" id="stage">
${paneHtml}
  </div>
  <div class="legend">
    <span><em>源文件</em> ${esc(docName)}</span>
    <span><em>由</em> scripts/viewer.mjs <em>生成 · SVG 已内联，无外部依赖</em></span>
  </div>
</main>
<script>${JS}</script>
</body>
</html>
`;
}

function buildOne(docPath, outPath) {
  const md = readFileSync(docPath, 'utf8');
  const stem = basename(docPath, extname(docPath));
  const docDir = dirname(docPath);
  const assetsDir = join(docDir, 'assets');
  const variantsDir = join(assetsDir, 'variants');
  const title = docTitle(md, stem);
  const hasFlow = hasFlowchart(md);

  // 1) 渲染变体（走 render.mjs，复用其增量缓存与单 Chrome 批处理）
  const args = [RENDER, docPath, join(assetsDir, `${stem}.svg`), '--variants'];
  if (force) args.push('--force');
  const r = spawnSync(process.execPath, args, { encoding: 'utf8' });
  if (r.status !== 0) {
    console.error(`[viewer] 渲染失败：\n${(r.stderr || r.stdout || '').trim()}`);
    return false;
  }

  // 2) 收集变体
  const panes = [];
  const primary = readSvg(join(assetsDir, `${stem}.svg`));
  if (primary) {
    panes.push({ svg: primary, theme: 'light', dir: hasFlow ? (readSourceDir(md)) : null, primary: true });
  }
  const wanted = hasFlow
    ? THEMES.flatMap((t) => DIRECTIONS.map((d) => ({ t, d })))
    : THEMES.map((t) => ({ t, d: null }));
  for (const { t, d } of wanted) {
    const p = join(variantsDir, `${stem}.${d || 'src'}.${t}.svg`);
    const svg = readSvg(p);
    if (!svg) continue;
    if (t === 'light' && (d === null || d === readSourceDir(md))) continue; // 与主产物重复
    panes.push({ svg, theme: t, dir: d });
  }
  if (panes.length === 0) {
    console.error(`[viewer] 没找到可用 SVG（${docPath}）`);
    return false;
  }

  writeFileSync(outPath, buildHtml({ title, docName: basename(docPath), panes, hasFlow }));
  console.log(`[viewer] ${basename(docPath)} → ${outPath}  (${panes.length} 个变体${hasFlow ? '，支持横竖切换' : '，仅主题切换'})`);
  return true;
}

function readSourceDir(md) {
  const m = md.match(/```mermaid[ \t]*\r?\n([\s\S]*?)```/);
  if (!m) return null;
  const line = (m[1].split('\n').find((l) => /^\s*flowchart\b/.test(l)) || '');
  if (/\b(TB|TD|BT)\b/.test(line)) return 'tb';
  if (/\b(LR|RL)\b/.test(line)) return 'lr';
  return 'tb';
}

// ── main ──
const target = targets[0];
const st = statSync(target);
let ok = 0;
if (st.isDirectory()) {
  for (const f of readdirSync(target)) {
    if (!f.endsWith('.md')) continue;
    const p = join(target, f);
    if (!/```mermaid/.test(readFileSync(p, 'utf8'))) continue;
    if (buildOne(p, join(target, `${basename(f, '.md')}.viewer.html`))) ok++;
  }
} else {
  const outPath = targets[1] || join(dirname(target), `${basename(target, extname(target))}.viewer.html`);
  if (buildOne(target, outPath)) ok++;
}
process.exit(ok ? 0 : 1);
