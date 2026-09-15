#!/usr/bin/env node
// preview.mjs — 零工具链预览：把 .md/.mmd 变成「打开就出图」的单文件 HTML
//
// 什么时候用它：
//   机器上没装 mermaid-cli / puppeteer（或浏览器起不来），但又想立刻看到图。
//   它在浏览器里从 CDN 拉 mermaid 渲染 —— 出图的是**你的浏览器**，不是本机 Chrome。
//
// ⚠️ 它是预览，不是交付物：
//   正式产物仍须 `render.mjs --strict`（离线、可复现、带构图审计、进 CI）。
//   preview 需要联网，且不做构图审计。
//
// 用法:
//   node scripts/preview.mjs docs/diagram/task-routing.md                 # → 同名 .live.html
//   node scripts/preview.mjs docs/diagram/task-routing.md -o /tmp/p.html
//   node scripts/preview.mjs in.mmd --theme dark
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join, basename, extname, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SKILL_ROOT = resolve(__dirname, '..');

const argv = process.argv.slice(2);
const take = (name, def) => {
  const i = argv.indexOf(name);
  if (i === -1) return def;
  const v = argv[i + 1];
  argv.splice(i, 2);
  return v;
};
const input = argv.filter((a) => !a.startsWith('-'))[0];
const theme = take('--theme', 'light');
const out = take('-o', null);

if (!input || !existsSync(input)) {
  console.error('用法: node scripts/preview.mjs <in.md|in.mmd|目录> [-o out.html] [--theme light|dark]');
  process.exitCode = 1;
} else {
  build(input, out, theme);
}

function extractBlocks(text) {
  const blocks = [];
  const re = /```mermaid[ \t]*\r?\n([\s\S]*?)```/g;
  let m;
  while ((m = re.exec(text))) blocks.push(m[1].replace(/\t/g, '  '));
  return blocks;
}

function firstDiagram(p) {
  const ext = extname(p).toLowerCase();
  const text = readFileSync(p, 'utf8');
  const blocks = ['.mmd', '.mermaid'].includes(ext) ? [text] : extractBlocks(text);
  return blocks[0] || null;
}

function build(input, outPath, theme) {
  const dsl = firstDiagram(input);
  if (!dsl) {
    console.error(`[preview] ${basename(input)} 里没有 mermaid 图块`);
    process.exitCode = 1;
    return;
  }
  const cfg = JSON.parse(readFileSync(join(SKILL_ROOT, 'assets', `mermaid-theme${theme === 'dark' ? '-dark' : ''}.json`), 'utf8'));
  const alt = JSON.parse(readFileSync(join(SKILL_ROOT, 'assets', `mermaid-theme${theme === 'dark' ? '' : '-dark'}.json`), 'utf8'));
  const target = outPath || join(dirname(resolve(input)), `${basename(input, extname(input))}.live.html`);

  const html = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${basename(input)} · 图预览</title>
<style>
  :root{--bg:#ffffff;--fg:#1f2328;--mut:#6b7280;--bd:#e5e7eb}
  *{box-sizing:border-box}
  body{margin:0;padding:24px;background:var(--bg);color:var(--fg);
       font:14px/1.6 'Segoe UI','Microsoft YaHei',system-ui,-apple-system,sans-serif}
  .bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:16px}
  button{border:1px solid var(--bd);background:transparent;color:var(--fg);
         padding:6px 14px;border-radius:6px;cursor:pointer;font:inherit}
  button:hover{border-color:#9aa3af}
  button.on{background:#2563eb;border-color:#2563eb;color:#fff}
  .hint{color:var(--mut);font-size:12px;margin-left:auto}
  #stage{overflow:auto;border:1px solid var(--bd);border-radius:10px;padding:16px;background:var(--bg)}
  #stage svg{max-width:100%;height:auto}
  .err{color:#b71c1c;white-space:pre-wrap;font-family:ui-monospace,Menlo,monospace;font-size:13px}
  body.dark{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;--bd:#30363d}
</style></head><body>
<div class="bar">
  <strong>${basename(input)}</strong>
  <button id="bDir">换个方向</button>
  <button id="bZoom">放大</button>
  <span class="hint">预览（CDN 渲染）· 正式交付请跑 render.mjs --strict</span>
</div>
<div id="stage"><em style="color:var(--mut)">正在加载 mermaid…</em></div>
<script type="module">
const DSL = ${JSON.stringify(dsl)};
const CFG = ${JSON.stringify(cfg)};
const ALT = ${JSON.stringify(alt)};
let dark = ${theme === 'dark'};
let lr = false, zoom = 1;
const stage = document.getElementById('stage');

async function loadMermaid() {
  const urls = [
    'https://unpkg.com/mermaid@11.4.1/dist/mermaid.min.js',
    'https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js',
    'https://registry.npmmirror.com/mermaid/11.4.1/files/dist/mermaid.min.js',
  ];
  for (const u of urls) {
    try { return (await import(u)).default; } catch (e) { /* 换下一个源 */ }
  }
  throw new Error('三个 CDN 都加载失败：本页需要联网');
}
function cfgFor() {
  const c = dark ? ALT : CFG;
  return { ...c, startOnLoad: false, securityLevel: 'loose' };
}
function flipDir(t) {
  const lines = t.split('\\n');
  const i = lines.findIndex((l) => /^\\s*flowchart\\b/.test(l));
  if (i === -1) return t;
  const want = lr ? 'LR' : 'TD';
  lines[i] = /\\b(TB|TD|BT|LR|RL)\\b/.test(lines[i])
    ? lines[i].replace(/\\b(TB|TD|BT|LR|RL)\\b/, want)
    : lines[i].replace(/\\s*$/, '') + ' ' + want;
  return lines.join('\\n');
}
async function draw() {
  try {
    const m = await loadMermaid();
    m.initialize(cfgFor());
    const { svg } = await m.render('g' + Date.now(), flipDir(DSL));
    stage.innerHTML = svg;
    stage.firstChild.style.transformOrigin = 'top left';
    stage.firstChild.style.transform = 'scale(' + zoom + ')';
    document.body.classList.toggle('dark', dark);
  } catch (e) {
    stage.innerHTML = '<div class="err">' + String(e && e.message || e) + '</div>';
  }
}
document.getElementById('bDir').onclick = () => { lr = !lr; draw(); };
document.getElementById('bZoom').onclick = (e) => {
  zoom = zoom >= 1.5 ? 0.75 : zoom + 0.25;
  e.target.textContent = '缩放 ' + Math.round(zoom * 100) + '%';
  draw();
};
draw();
</script></body></html>`;
  writeFileSync(target, html, 'utf8');
  console.log(`[preview] ${target}`);
  console.log('          浏览器打开即出图（需联网加载 mermaid）；正式交付仍用 render.mjs --strict');
}
