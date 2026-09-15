#!/usr/bin/env node
// render.mjs — DiagramMind 渲染器（Mermaid only）
//
// 设计要点（效率优先）:
//   1. 一次 Chrome 启动渲染全部图 —— 不再每图一次冷启动
//   2. 增量跳过 —— 源/主题/方向/布局 hash 未变则直接复用旧 SVG（--force 强制重渲）
//   3. 一个文档只渲一张图 —— 多图块只取第一块，其余警告（--all-blocks 关闭该约束）
//   4. 变体 —— --variants 一次产出 主题(浅/深) × 方向(竖/横) 网格，供 viewer 切换
//   5. ★ 构图审计 —— 渲染后按 画布宽度/宽高比/节点数/边数/填充率/孤岛空档 体检（--strict 阻断）
//   6. ★ 布局 A/B —— --layout auto（默认）时，dagre 不达标才追加一次 elk 复算，取优者
//
// D2 已于 v6.1 下线。v6.5 复核：当时记的「layout:'elk' 挂死」是 **D2(terrastruct)** 的坑；
// Mermaid 侧的 ELK 已随 mermaid-cli 无条件注册，实测可用（同一份 DSL 1952×2319 → 935×2123）。
//
// 用法:
//   node render.mjs <in.mmd|in.md> [out.svg]     单文件
//   node render.mjs <目录>                        批量 → <目录>/assets/
//   node render.mjs <目录> --variants             批量 + 变体 → <目录>/assets/variants/
//   node render.mjs <目录> --strict               构图审计不达标 → 退出码 1
//   node render.mjs --check                       探测工具链
// 选项:
//   --theme <light|dark|none>   主题（默认 light；none = Mermaid 原始默认样式）
//   --bg <color>                背景（默认随主题 #ffffff / #0d1117）
//   --direction <tb|lr>         强制流程图方向（只对 flowchart 生效，其余图型忽略）
//   --layout <auto|dagre|elk>   布局引擎。auto（默认）= dagre 先算，不达标才追加 elk 取优
//   --strict                    任一图构图审计不达标 → 退出码 1
//   --no-audit                  关闭构图审计输出
//   --variants                  产出 主题×方向 网格，供 viewer 切换
//   --force                     忽略增量缓存，强制重渲
//   --all-blocks                允许一个 .md 内渲染多个图块（默认只渲第一个）
//   --json                      输出机器可读 JSON 结果
import { existsSync, mkdirSync, readdirSync, writeFileSync, readFileSync, statSync, realpathSync } from 'node:fs';
import { join, dirname, resolve, basename, extname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import os from 'node:os';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SKILL_ROOT = resolve(__dirname, '..');
const ASSETS = join(SKILL_ROOT, 'assets');
const MANIFEST_NAME = '.diagramrender.json';

export const THEMES = ['light', 'dark'];
export const DIRECTIONS = ['tb', 'lr'];
export const LAYOUTS = ['auto', 'dagre', 'elk'];

// 构图预算（SSOT 是 references/layout.md，这里是它的可执行版本）
export const BUDGET = {
  maxWidth: 1200,      // 画布宽：文档里按 900~1200 显示，宽度直接决定实际字号
  minWidth: 320,       // 画布宽下限：比这更窄 = 一根竖条（连两个框都摆不下）
  maxNodes: 12,        // 节点数：再多没人看
  maxEdges: 14,        // 边数
  minCoverage: 0.12,   // 节点面积 / 内容包围盒 —— 太低 = 图被拉散
  minRatio: 0.32,      // 宽高比下限：只用来兜住「塌成竖条」，纵向长图本身是好的（文档纵向滚动）
  maxRatio: 2.6,       // 宽高比上限（再大就是横幅，文档里字号被压小）
  maxLabelChars: 26,   // 单行标签字数（再长就把画布撑宽）
};
// 预算指纹：预算改了，缓存里的旧判定会过期 —— 审计是 SVG 的纯函数，可就地重算
const BUDGET_FP = createHash('sha1').update(JSON.stringify(BUDGET)).digest('hex').slice(0, 8);

// 只有 flowchart 系列能按节点/边算账；其余图型（state/er/sequence/architecture）只量画布
const FLOWCHART_ROLES = new Set(['flowchart-v2', 'flowchart-elk', 'flowchart']);

// ── 选项 ─────────────────────────────────────────────────
const argv = process.argv.slice(2);
function takeFlag(name, def) {
  const i = argv.indexOf(name);
  if (i === -1) return def;
  const v = argv[i + 1];
  argv.splice(i, 2);
  return v;
}
function takeBool(name) {
  const i = argv.indexOf(name);
  if (i === -1) return false;
  argv.splice(i, 1);
  return true;
}
const DEFAULT_BG = { light: '#ffffff', dark: '#0d1117', none: '#ffffff' };
const OPT = {
  theme: takeFlag('--theme', 'light'),
  bg: null,
  scale: Number(takeFlag('--scale', '2')) || 2,
  direction: takeFlag('--direction', null),
  layout: takeFlag('--layout', 'auto'),
  variants: takeBool('--variants'),
  strict: takeBool('--strict'),
  audit: !takeBool('--no-audit'),
  force: takeBool('--force'),
  allBlocks: takeBool('--all-blocks'),
  json: takeBool('--json'),
};
OPT.bg = takeFlag('--bg', DEFAULT_BG[OPT.theme] || '#ffffff');
if (!LAYOUTS.includes(OPT.layout)) {
  console.error(`[render] --layout 只能是 ${LAYOUTS.join('|')}，收到 "${OPT.layout}"`);
  process.exitCode = 1;
}

const CHROME = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].find((p) => existsSync(p));

// ── 工具链定位 ───────────────────────────────────────────
function nmRoots() {
  const roots = [];
  let d = process.cwd();
  for (let i = 0; i < 6; i++) {
    roots.push(join(d, '.tools', 'diagram', 'node_modules'));
    const p = dirname(d);
    if (p === d) break;
    d = p;
  }
  roots.push(join(SKILL_ROOT, '.tools', 'diagram', 'node_modules'));
  roots.push(join(os.homedir(), '.workbuddy-ai', 'binaries', 'diagram', 'node_modules'));
  return roots.filter((r, i) => roots.indexOf(r) === i && existsSync(r));
}

function resolvePkg(name) {
  for (const r of nmRoots()) {
    try { return createRequire(join(r, '_.js')).resolve(name); } catch { /* next */ }
  }
  return null;
}

// exports 字段会挡住 package.json 子路径解析，直接按目录探
function firstExisting(...segs) {
  for (const r of nmRoots()) {
    const p = join(r, ...segs);
    if (existsSync(p)) return p;
  }
  return null;
}

let _TOOL = null;
export function toolchain() {
  if (_TOOL) return _TOOL;
  _TOOL = {
    mmIndex: firstExisting('@mermaid-js', 'mermaid-cli', 'src', 'index.js'),
    puppeteer: resolvePkg('puppeteer'),
    elk: firstExisting('@mermaid-js', 'layout-elk', 'package.json'),
  };
  return _TOOL;
}

// ── 主题 ─────────────────────────────────────────────────
export function mermaidConfig(theme, layout) {
  const t = theme || OPT.theme;
  if (t === 'none') return {};
  const f = t === 'dark' ? 'mermaid-theme-dark.json' : 'mermaid-theme.json';
  const p = join(ASSETS, f);
  let cfg = {};
  if (existsSync(p)) {
    try { cfg = JSON.parse(readFileSync(p, 'utf8')); } catch { cfg = {}; }
  }
  if (!layout || layout === 'dagre') return cfg;
  // elk：mermaid v11 认顶层 `layout`，flowchart 还认 defaultRenderer —— 两处都写，避版本差异
  return {
    ...cfg,
    layout,
    flowchart: { ...(cfg.flowchart || {}), defaultRenderer: layout },
  };
}
export function bgFor(theme) { return DEFAULT_BG[theme || OPT.theme] || '#ffffff'; }

// ── 源解析 ───────────────────────────────────────────────
function dedent(s) {
  const lines = s.replace(/\t/g, '  ').split('\n');
  let min = Infinity;
  for (const l of lines) {
    if (!l.trim()) continue;
    min = Math.min(min, l.match(/^ */)[0].length);
  }
  if (!isFinite(min) || min === 0) return s;
  return lines.map((l) => l.slice(min)).join('\n');
}

function extractBlocks(text) {
  const blocks = [];
  const re = /```(mermaid|d2)[ \t]*\r?\n([\s\S]*?)```/g;
  let m;
  while ((m = re.exec(text))) {
    if (m[1] === 'd2') continue; // D2 已下线，静默忽略（不阻断整个文档）
    blocks.push({ lang: m[1], code: dedent(m[2]).trim() });
  }
  return blocks;
}

// 只对 flowchart 有意义；其余图型返回 ok:false
export function applyDirection(text, dir) {
  if (!dir) return { ok: true, text, changed: false };
  const want = dir === 'lr' ? 'LR' : 'TD';
  const lines = text.split('\n');
  const i = lines.findIndex((l) => /^\s*flowchart\b/.test(l));
  if (i === -1) return { ok: false, text, changed: false };
  const before = lines[i];
  lines[i] = /\b(TB|TD|BT|LR|RL)\b/.test(before)
    ? before.replace(/\b(TB|TD|BT|LR|RL)\b/, want)
    : `${before.replace(/\s*$/, '')} ${want}`;
  return { ok: true, text: lines.join('\n'), changed: lines[i] !== before };
}

// ── 构图审计 ─────────────────────────────────────────────
// 纯字符串解析，不引 DOM/依赖。目的不是像素级精确，而是把「一目了然」变成可机检指标。
const RE_XLATE = /transform="translate\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)"/;

// mermaid 的节点容器有四种载体，缺一种就会漏数：
//   rect（方/圆角）· polygon（菱形）· circle（圆）· <g class="label-container"><path>（圆角/胶囊/柱形）
function shapeBox(ch) {
  const rect = ch.match(/<rect\b[^>]*?class="[^"]*label-container[^"]*"[^>]*>/);
  if (rect) {
    const n = (k) => { const m = rect[0].match(new RegExp(`\\b${k}="(-?[\\d.]+)"`)); return m ? Number(m[1]) : 0; };
    const w = n('width'); const h = n('height');
    if (w && h) return { x: n('x'), y: n('y'), w, h };
  }
  const circ = ch.match(/<circle\b[^>]*?class="[^"]*label-container[^"]*"[^>]*>/);
  if (circ) {
    const n = (k) => { const m = circ[0].match(new RegExp(`\\b${k}="(-?[\\d.]+)"`)); return m ? Number(m[1]) : null; };
    const r = n('r');
    if (r) return { x: (n('cx') || 0) - r, y: (n('cy') || 0) - r, w: r * 2, h: r * 2 };
  }
  for (const tag of ['polygon', 'path']) {
    const el = ch.match(new RegExp(`<${tag}\\b[^>]*?class="[^"]*label-container[^"]*"[^>]*>`))
      || (tag === 'path' ? ch.match(/class="[^"]*label-container[^"]*"[\s\S]{0,400}?<path\b[^>]*?\sd="[^"]+"/) : null);
    if (!el) continue;
    const src = tag === 'polygon'
      ? (el[0].match(/points="([^"]+)"/) || [])[1]
      : (el[0].match(/\sd="([^"]+)"/) || [])[1];
    if (!src) continue;
    const nums = (src.match(/-?\d+(?:\.\d+)?/g) || []).map(Number);
    if (nums.length < 4) continue;
    const xs = []; const ys = [];
    for (let i = 0; i + 1 < nums.length; i += 2) { xs.push(nums[i]); ys.push(nums[i + 1]); }
    const x0 = Math.min(...xs); const x1 = Math.max(...xs);
    const y0 = Math.min(...ys); const y1 = Math.max(...ys);
    if (!(x1 > x0 && y1 > y0)) continue;
    const t = el[0].match(RE_XLATE); // 菱形等自带一层位移
    return { x: x0 + (t ? Number(t[1]) : 0), y: y0 + (t ? Number(t[2]) : 0), w: x1 - x0, h: y1 - y0 };
  }
  const fo = ch.match(/<foreignObject[^>]*?width="([\d.]+)"[^>]*?height="([\d.]+)"[^>]*?x="(-?[\d.]+)"[^>]*?y="(-?[\d.]+)"/);
  if (fo) return { x: Number(fo[3]), y: Number(fo[4]), w: Number(fo[1]), h: Number(fo[2]) };
  return null;
}

function nodeBoxes(svg) {
  const out = [];
  const chunks = svg.split(/<g class="[^"]*\bnode\b[^"]*"/).slice(1);
  for (const ch of chunks) {
    const t = ch.match(RE_XLATE);
    if (!t) continue;
    const cx = Number(t[1]);
    const cy = Number(t[2]);
    const b = shapeBox(ch);
    if (!b || !b.w || !b.h) continue;
    out.push({ cx, cy, x: cx + b.x, y: cy + b.y, w: b.w, h: b.h });
  }
  return out;
}

export function auditFigure(svg) {
  const m = svg.match(/<svg[^>]*?width="([\d.]+)"[^>]*?height="([\d.]+)"/);
  const W = m ? Number(m[1]) : 0;
  const H = m ? Number(m[2]) : 0;
  const kind = (svg.match(/aria-roledescription="([^"]+)"/) || [])[1] || 'unknown';
  const supported = FLOWCHART_ROLES.has(kind);

  const boxes = supported ? nodeBoxes(svg) : [];
  const edges = supported ? (svg.match(/class="[^"]*flowchart-link[^"]*"/g) || []).length : 0;
  const labels = supported
    ? [...svg.matchAll(/<span class="nodeLabel"[^>]*>([\s\S]*?)<\/span>/g)]
      .map((x) => x[1].replace(/<[^>]*>/g, ' ').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim())
      .filter(Boolean)
    : [];

  const ratio = H ? W / H : 0;
  let coverage = 0;
  let islands = 0;
  if (boxes.length) {
    const x0 = Math.min(...boxes.map((b) => b.x));
    const y0 = Math.min(...boxes.map((b) => b.y));
    const x1 = Math.max(...boxes.map((b) => b.x + b.w));
    const y1 = Math.max(...boxes.map((b) => b.y + b.h));
    const area = Math.max(1, (x1 - x0) * (y1 - y0));
    coverage = boxes.reduce((s, b) => s + b.w * b.h, 0) / area;
    // 孤岛空档：节点按 x 中心排序，找远大于中位间距的空档（典型症状 = 右侧一大片空地）
    const xs = [...new Set(boxes.map((b) => Math.round(b.cx)))].sort((a, b) => a - b);
    if (xs.length > 2) {
      const gaps = [];
      for (let i = 1; i < xs.length; i++) gaps.push(xs[i] - xs[i - 1]);
      const sorted = [...gaps].sort((a, b) => a - b);
      const med = sorted[Math.floor(sorted.length / 2)] || 1;
      islands = gaps.filter((g) => g > med * 2.5).length;
    }
  }

  const violations = [];
  if (W > BUDGET.maxWidth) {
    violations.push(`画布宽 ${Math.round(W)}px > ${BUDGET.maxWidth}（文档里字号会被压到 ~${Math.round(15 * 900 / W)}px）`);
  }
  if (W && W < BUDGET.minWidth) violations.push(`画布宽 ${Math.round(W)}px < ${BUDGET.minWidth}：塌成一根竖条`);
  if (ratio && (ratio < BUDGET.minRatio || ratio > BUDGET.maxRatio)) {
    violations.push(`宽高比 ${ratio.toFixed(2)} 越界 [${BUDGET.minRatio}, ${BUDGET.maxRatio}]`);
  }
  if (supported) {
    if (boxes.length > BUDGET.maxNodes) violations.push(`节点 ${boxes.length} > ${BUDGET.maxNodes}（该砍信息进表）`);
    if (edges > BUDGET.maxEdges) violations.push(`边 ${edges} > ${BUDGET.maxEdges}`);
    if (boxes.length && coverage < BUDGET.minCoverage) {
      violations.push(`图被拉散：节点只占内容区 ${(coverage * 100).toFixed(0)}%`);
    }
    if (islands) violations.push(`存在 ${islands} 处孤岛空档`);
    const longest = labels.reduce((a, b) => (b.length > a.length ? b : a), '');
    if (longest.length > BUDGET.maxLabelChars) {
      violations.push(`最长标签 ${longest.length} 字 > ${BUDGET.maxLabelChars}：「${longest.slice(0, 16)}…」`);
    }
  }

  return {
    kind, supported,
    w: Math.round(W), h: Math.round(H), ratio: Number(ratio.toFixed(2)),
    nodes: boxes.length, edges, coverage: Number(coverage.toFixed(3)), islands,
    longestLabel: labels.reduce((a, b) => (b.length > a.length ? b : a), '').length,
    violations,
  };
}

function scoreAudit(a) {
  // 违规少者优先；同分则更窄者优先（宽度直接决定文档内可读性），再次看填充率
  return -a.violations.length * 1000 - Math.max(0, a.w - BUDGET.maxWidth) / 100 + a.coverage * 10;
}

// 把一个输入文件展开成渲染任务
function planJobs(input, output, warn) {
  const ext = extname(input).toLowerCase();
  const jobs = [];
  if (ext === '.mmd' || ext === '.mermaid') {
    jobs.push({ src: input, out: output, kind: 'mermaid', text: readFileSync(input, 'utf8') });
    return jobs;
  }
  if (ext === '.d2') {
    return { err: 'D2 已在 v6.1 下线，请改用 Mermaid architecture-beta（见 references/decisions.md）' };
  }
  if (ext === '.md' || ext === '.markdown') {
    const blocks = extractBlocks(readFileSync(input, 'utf8'));
    // 纯文字文档没有图块是正常的，静默跳过（不产生噪音）
    if (blocks.length === 0) return jobs;
    const take = OPT.allBlocks ? blocks : blocks.slice(0, 1);
    if (blocks.length > 1 && !OPT.allBlocks) {
      warn?.(`${basename(input)}: 含 ${blocks.length} 个图块，只渲染第 1 个（一文一图；需全渲加 --all-blocks）`);
    }
    const dir = dirname(output);
    const stem = basename(output, extname(output));
    take.forEach((b, i) => {
      const out = i === 0 ? output : join(dir, `${stem}-${i + 1}.svg`);
      jobs.push({ src: input, out, kind: b.lang, text: b.code });
    });
    return jobs;
  }
  return { err: `不支持的输入类型: ${ext}` };
}

// ── 渲染：Mermaid（单浏览器批处理，支持 per-job 主题/布局） ─
async function openToolchain() {
  const { mmIndex, puppeteer } = toolchain();
  if (!mmIndex) throw new Error('mermaid-cli 未安装（见 references/render.md）');
  if (!puppeteer) throw new Error('puppeteer 未安装（见 references/render.md）');
  const mmMod = await import(pathToFileURL(mmIndex).href);
  const renderMermaid = mmMod.renderMermaid || mmMod.default?.renderMermaid;
  if (!renderMermaid) throw new Error('mermaid-cli 未导出 renderMermaid（版本不兼容）');
  const pptrMod = await import(pathToFileURL(puppeteer).href);
  const pptr = pptrMod.default || pptrMod;
  return { renderMermaid, pptr };
}

async function launchBrowser(pptr) {
  const launchOpts = {
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
    headless: true,
  };
  if (CHROME) launchOpts.executablePath = CHROME;
  return pptr.launch(launchOpts);
}

async function renderOnce(browser, renderMermaid, job, theme, layout) {
  const r = await renderMermaid(browser, job.text, 'svg', {
    backgroundColor: job.bg || bgFor(theme),
    mermaidConfig: mermaidConfig(theme, layout),
  });
  return Buffer.from(r.data).toString('utf8');
}

async function renderMermaidJobs(jobs, log, rows, warnings) {
  const { renderMermaid, pptr } = await openToolchain();
  log(`启动 Chrome（1 次，服务 ${jobs.length} 张图）…`);
  const browser = await launchBrowser(pptr);
  try {
    for (const job of jobs) {
      const theme = job.theme || OPT.theme;
      const req = job.noLayoutProbe ? 'dagre' : OPT.layout;
      let used = req === 'auto' ? 'dagre' : req;
      let svg = await renderOnce(browser, renderMermaid, job, theme, used);
      let audit = OPT.audit ? auditFigure(svg) : null;

      // auto：dagre 不达标才追加一次 elk 复算 —— 达标时零额外成本
      if (req === 'auto' && audit && audit.violations.length) {
        try {
          const alt = await renderOnce(browser, renderMermaid, job, theme, 'elk');
          const altAudit = auditFigure(alt);
          if (scoreAudit(altAudit) > scoreAudit(audit)) {
            log(`  ~     ${rel(job.src)} dagre 违规 ${audit.violations.length} → elk 违规 ${altAudit.violations.length}，采用 elk`);
            svg = alt; audit = altAudit; used = 'elk';
          } else {
            log(`  ~     ${rel(job.src)} elk 未改善（违规 ${altAudit.violations.length}），保留 dagre`);
          }
        } catch (e) {
          warnings.push(`${basename(job.src)}: elk 复算失败（${String(e.message).slice(0, 80)}），保留 dagre`);
        }
      }

      job.layout = used;
      job.audit = audit;
      mkdirSync(dirname(job.out), { recursive: true });
      writeFileSync(job.out, Buffer.from(svg, 'utf8'));
      if (audit) rows.push({ file: rel(job.out), layout: used, ...audit });
    }
  } finally {
    await browser.close();
  }
}

// ── 变体展开 ─────────────────────────────────────────────
// 主产物恒为 light + 源方向（保证 md 里 ![](assets/x.svg) 有效）；
// 其余组合进 variants/。非 flowchart 只出主题变体。
export function expandVariants(baseJobs, assetsDir, outDir) {
  const jobs = [];
  const notes = [];
  for (const base of baseJobs) {
    const stem = basename(base.out, '.svg');
    jobs.push({ ...base, theme: 'light', direction: null, out: join(assetsDir, `${stem}.svg`) });
    const probe = applyDirection(base.text, 'lr');
    const dirs = probe.ok ? DIRECTIONS : [null];
    if (!probe.ok) notes.push(`${stem}: 非 flowchart，跳过方向变体（只出主题变体）`);
    for (const theme of THEMES) {
      for (const dir of dirs) {
        if (theme === 'light' && dir === null) continue; // 已由主产物覆盖
        const r = applyDirection(base.text, dir);
        jobs.push({
          ...base,
          text: r.text,
          theme,
          direction: dir,
          noLayoutProbe: true, // 变体不跑 A/B，省一半渲染时间
          out: join(outDir, `${stem}.${dir || 'src'}.${theme}.svg`),
        });
      }
    }
  }
  return { jobs, notes };
}

// ── 增量缓存 ─────────────────────────────────────────────
function hashJob(job) {
  return createHash('sha1')
    .update(`${job.theme || OPT.theme}|${job.bg || OPT.bg}|${job.direction || '-'}|${job.layoutReq || OPT.layout}|${job.kind}|${job.text}`)
    .digest('hex')
    .slice(0, 16);
}
function manifestKey(job) {
  return `${job.src}::${job.theme || OPT.theme}::${job.direction || 'src'}`;
}
function loadManifest(dir) {
  const p = join(dir, MANIFEST_NAME);
  if (!existsSync(p)) return {};
  try { return JSON.parse(readFileSync(p, 'utf8')); } catch { return {}; }
}
function saveManifest(dir, m) {
  try { writeFileSync(join(dir, MANIFEST_NAME), JSON.stringify(m, null, 2)); } catch { /* ignore */ }
}

// ── 构图审计报告 ─────────────────────────────────────────
function auditReport(rows) {
  if (!rows.length) return [];
  const bad = rows.filter((r) => (r.violations || []).length);
  const lines = ['', '构图审计（预算见 references/layout.md）:'];
  for (const r of rows) {
    const flag = (r.violations || []).length ? 'FAIL' : 'ok  ';
    const scope = r.supported === false
      ? `仅画布（${r.kind}，非 flowchart 不算节点账）`
      : `节点${r.nodes} 边${r.edges} 填充${((r.coverage || 0) * 100).toFixed(0)}%`;
    lines.push(`  ${flag} ${r.file}  ${r.w}x${r.h} r=${r.ratio}  ${scope} [${r.layout}]`);
    for (const v of (r.violations || [])) lines.push(`        - ${v}`);
  }
  if (bad.length) {
    lines.push(`  → ${bad.length}/${rows.length} 张超标。先把信息砍进表（§关键数字/§排查脉络/§解决方案），再考虑换方向或 --layout elk。`);
  } else {
    lines.push(`  → ${rows.length} 张全部达标。`);
  }
  return lines;
}

// 跳过的图从 manifest 取回上次审计结果，保证报告始终是「全目录」视角。
// 预算改过（指纹不一致）→ 缓存的判定已过期，直接读 SVG 重算（纯字符串运算，不启 Chrome）。
function auditFromManifest(manifest, jobs, renderedOuts) {
  const rows = [];
  for (const j of jobs) {
    const hit = manifest[manifestKey(j)];
    if (!hit || !hit.audit) continue;
    const file = hit.out || rel(j.out);
    if (renderedOuts.has(file)) continue; // 本次已渲染，避免重复行
    if (hit.budget !== BUDGET_FP && existsSync(j.out)) {
      try {
        const a = auditFigure(readFileSync(j.out, 'utf8'));
        hit.budget = BUDGET_FP;
        hit.audit = { ...a, file: undefined };
        rows.push({ file, layout: hit.layout || 'dagre', ...a });
        continue;
      } catch { /* 读不出来就回落到缓存判定 */ }
    }
    rows.push({ ...hit.audit, file, layout: hit.layout || 'dagre', violations: hit.audit.violations || [] });
  }
  return rows;
}

// ── main ─────────────────────────────────────────────────
const out = [];
function log(s) { if (!OPT.json) out.push(s); }

async function main() {
  const targets = argv.filter((a) => !a.startsWith('--'));

  if (argv.includes('--check') || targets.length === 0) {
    const t = toolchain(); // 只有探测时才付定位成本
    const lines = [
      `Chrome       : ${CHROME || '❌ 未找到（Mermaid 无法渲染）'}`,
      `mermaid-cli  : ${t.mmIndex || '❌ 未安装'}`,
      `puppeteer    : ${t.puppeteer || '❌ 未安装'}`,
      `layout-elk   : ${t.elk || '❌ 未安装（--layout elk/auto 不可用）'}`,
      `主题          : ${OPT.theme}  bg=${OPT.bg}  layout=${OPT.layout}`,
      `主题文件      : ${OPT.theme === 'none' ? '(不用)' : (existsSync(join(ASSETS, OPT.theme === 'dark' ? 'mermaid-theme-dark.json' : 'mermaid-theme.json')) ? '✅' : '⚠️ 缺失')}`,
    ];
    console.log(lines.join('\n'));
    if (targets.length === 0) return;
  }

  const input = targets[0];
  const st = statSync(input);
  const isDir = st.isDirectory();

  // 1) 收集基础任务
  let jobs = [];
  const warnings = [];
  let manifestDir = null;
  let assetsDir = null;
  const warn = (m) => warnings.push(m);

  if (isDir) {
    manifestDir = input;
    assetsDir = join(input, 'assets');
    for (const f of walkDiagrams(input)) {
      const stem = basename(f, extname(f));
      const r = planJobs(f, join(assetsDir, `${stem}.svg`), warn);
      if (r.err) { warnings.push(`${basename(f)}: ${r.err}`); continue; }
      jobs.push(...r);
    }
  } else {
    const o = targets[1] || `${input}.svg`;
    manifestDir = dirname(o);
    assetsDir = dirname(o);
    const r = planJobs(input, o, warn);
    if (r.err) { console.error(`[render] ${r.err}`); process.exitCode = 1; return; }
    jobs.push(...r);
  }

  // 2) 变体展开
  if (OPT.variants) {
    const { jobs: vjobs, notes } = expandVariants(jobs, assetsDir, join(assetsDir, 'variants'));
    jobs = vjobs;
    for (const n of notes) warn(n);
  } else if (OPT.direction) {
    jobs = jobs.map((j) => {
      const r = applyDirection(j.text, OPT.direction);
      if (!r.ok) warn(`${basename(j.src)}: 非 flowchart，--direction 被忽略`);
      return { ...j, text: r.text, direction: OPT.direction };
    });
  }

  // 3) 增量过滤（布局请求也进 hash，改 --layout 会正确失效）
  for (const j of jobs) j.layoutReq = j.noLayoutProbe ? 'dagre' : OPT.layout;
  const manifest = manifestDir ? loadManifest(manifestDir) : {};
  const pending = [];
  let skipped = 0;
  for (const job of jobs) {
    const h = hashJob(job);
    const key = manifestKey(job);
    const hit = manifest[key];
    if (!OPT.force && hit && hit.hash === h && existsSync(job.out)) { skipped++; continue; }
    job.hash = h;
    job.key = key;
    pending.push(job);
  }

  // 4) 渲染 + 审计
  const rows = [];
  let failed = 0;
  if (pending.length) {
    const done = new Set();
    try {
      await renderMermaidJobs(pending, log, rows, warnings);
      for (const j of pending) {
        done.add(j.out);
        log(`  OK    ${rel(j.src)} -> ${rel(j.out)}  [${j.theme || OPT.theme}${j.direction ? '/' + j.direction : ''}${j.layout ? '/' + j.layout : ''}]`);
      }
    } catch (e) {
      // 整体失败（如浏览器起不来）：剩余未完成的全部算失败
      warnings.push(e.message);
    }
    failed = pending.length - done.size;
    if (manifestDir) {
      for (const j of pending) {
        if (!existsSync(j.out)) continue;
        const row = rows.find((r) => r.file === rel(j.out));
        manifest[j.key] = {
          hash: j.hash, out: rel(j.out), layout: j.layout || null, budget: BUDGET_FP,
          audit: row ? { ...row, file: undefined } : null,
        };
      }
      saveManifest(manifestDir, manifest);
    }
  }

  const auditRows = OPT.audit
    ? rows.concat(auditFromManifest(manifest, jobs, new Set(rows.map((r) => r.file))))
    : [];
  const bad = auditRows.filter((r) => (r.violations || []).length);

  const okCount = jobs.length - failed - skipped;
  log(`[render] 成功 ${okCount} / 跳过 ${skipped}（未变） / 失败 ${failed}  [${OPT.theme}${OPT.variants ? ' +变体' : ''} +${OPT.layout}]`);
  if (OPT.audit) for (const l of auditReport(auditRows)) log(l);

  if (OPT.json) {
    console.log(JSON.stringify({
      theme: OPT.theme, variants: OPT.variants, layout: OPT.layout,
      total: jobs.length, rendered: okCount, skipped, failed,
      audit: auditRows, warnings,
    }, null, 2));
  } else {
    if (out.length) console.log(out.join('\n'));
    for (const w of warnings) console.log(`  ! ${w}`);
  }
  if (failed) process.exitCode = 1;
  if (OPT.strict && bad.length) {
    if (!OPT.json) console.error(`[render] --strict：${bad.length} 张构图超标（见上）`);
    process.exitCode = 1;
  }
}

function rel(p) { return p.startsWith(process.cwd()) ? p.slice(process.cwd().length + 1) : p; }

function walkDiagrams(dir, acc = []) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === 'assets' || e.name === 'node_modules' || e.name === 'variants') continue;
      walkDiagrams(p, acc);
    } else if (['.mmd', '.d2', '.mermaid', '.md'].includes(extname(p).toLowerCase())) {
      acc.push(p);
    }
  }
  return acc;
}

// ponytail: Windows junction 下 argv[1] 常为 C:\… 而 import.meta.url 为 E:\…，须 realpath 后再比
function runningAsMain() {
  const entry = process.argv[1];
  if (!entry) return false;
  try {
    const rp = realpathSync.native || realpathSync;
    return rp(resolve(entry)) === rp(fileURLToPath(import.meta.url));
  } catch {
    return false;
  }
}

// 被 viewer.mjs import 时不自动跑 main
if (runningAsMain()) {
  main().catch((e) => {
    console.error(`[render] 致命错误: ${e.message}`);
    process.exitCode = 1;
  });
}
