#!/usr/bin/env node
// drift.mjs — Diagram Drift 检测：代码模块 vs 图节点
// 用法: node drift.mjs <项目根> [图目录] [--json] [--quiet] [--all]
//   --all  关闭"只查架构级组件"过滤，报告全部模块
// 配置: <项目根>/.diagramdrift.json  { "ignore": ["glob"], "include": ["glob"] }
import { readdirSync, readFileSync, statSync, existsSync } from 'node:fs';
import { join, extname, basename, relative } from 'node:path';

const args = process.argv.slice(2);
const jsonOut = args.includes('--json');
const quiet = args.includes('--quiet');
const all = args.includes('--all');
const pos = args.filter((a) => !a.startsWith('--'));
const ROOT = pos[0] || '.';
const DIAG = pos[1] || 'docs/diagram';

const SKIP_DIR = new Set([
  'node_modules', '.git', 'dist', 'build', 'target', 'out', '.next',
  'coverage', 'vendor', '__pycache__', '.venv', 'venv', 'test', 'tests',
  '__tests__', 'e2e', 'fixtures', 'generated', '.tools', 'docs',
  '_pre_p0_backup', 'backup', 'demo', 'demos', 'samples', 'examples',
  '.cache', 'tmp', 'temp', '.idea', '.vscode',
]);

// 架构级组件：架构图只画这些，避免把工具脚本算成漂移
const COMPONENT_RE = /(Service|Controller|Manager|Handler|Repository|Dao|Agent|Mind|Module|Gateway|Client|Provider|Adapter|Store|Engine|Router|Pipeline|Brain|Skill|Task|Runner|Worker|Job|Consumer|Producer|Listener|Mapper|Facade|Orchestrator)$/i;
// 工具目录：默认不算架构组件（--all 才纳入）
const TOOL_DIR_RE = /\/(scripts|tools|bin|migrations|cmd)\//i;

let CFG = { ignore: [], include: [] };
const cfgPath = join(ROOT, '.diagramdrift.json');
if (existsSync(cfgPath)) {
  try { CFG = { ...CFG, ...JSON.parse(readFileSync(cfgPath, 'utf8')) }; } catch { /* ignore */ }
}
const toRe = (g) => new RegExp('^' + g.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*\*/g, '\u0000').replace(/\*/g, '[^/]*').replace(/\u0000/g, '.*') + '$');

function walk(dir, acc = [], depth = 0) {
  if (depth > 10) return acc;
  let entries;
  try { entries = readdirSync(dir, { withFileTypes: true }); } catch { return acc; }
  for (const e of entries) {
    if (e.isDirectory()) {
      if (SKIP_DIR.has(e.name) || e.name.startsWith('.')) continue;
      walk(join(dir, e.name), acc, depth + 1);
    } else {
      acc.push(join(dir, e.name));
    }
  }
  return acc;
}

// 归一：去扩展名/后缀/分隔符，小写
function norm(name) {
  return String(name)
    .replace(/\.[a-z0-9]+$/i, '')
    .replace(/(Impl|Service|Controller|Manager|Handler|Repository|Dao|DTO|VO|Entity|Mapper)$/i, '')
    .replace(/[_\-\s.]/g, '')
    .toLowerCase();
}

// ---- 扫描代码模块 ----
const CODE_EXT = new Set(['.java', '.ts', '.tsx', '.js', '.mjs', '.cjs', '.py', '.go', '.kt', '.cs']);
const codeModules = new Map(); // norm -> 相对路径
for (const f of walk(ROOT)) {
  if (!CODE_EXT.has(extname(f))) continue;
  const raw = basename(f, extname(f));
  if (/^(index|main|app|mod|setup|test|spec|types?|constants?|utils?|helpers?|cli)$/i.test(raw)) continue;
  const rel = relative(ROOT, f).replace(/\\/g, '/');
  if (CFG.ignore.some((g) => toRe(g).test(rel))) continue;
  if (!all) {
    if (TOOL_DIR_RE.test('/' + rel)) continue;
    if (CFG.include.length === 0 && !COMPONENT_RE.test(raw)) continue;
  }
  const n = norm(raw);
  if (n.length < 3) continue;
  if (!codeModules.has(n)) codeModules.set(n, rel);
}

// ---- 扫描图节点 ----
function extractNodes(text) {
  const ids = new Set();
  const labels = new Set();
  for (const raw of text.split('\n')) {
    const t = raw.trim();
    if (!t || t.startsWith('%%') || t.startsWith('//') || t.startsWith('#')) continue;
    // mermaid: ID[名] ID(名) ID{名} ID((名)) ID[[名]]
    for (const m of t.matchAll(/([A-Za-z_][\w-]*)\s*(?:\[\[|\[\(|\(\(|\[|\(|\{)\s*"?([^"\]\)\}]+?)"?\s*(?:\]\]|\)\]|\]|\)|\})/g)) {
      ids.add(m[1]);
      const lbl = m[2].trim();
      if (lbl) labels.add(lbl);
    }
  }
  return { ids, labels };
}

const diagPath = join(ROOT, DIAG);
const diagramFiles = walk(diagPath).filter((f) => ['.md', '.mmd'].includes(extname(f)));
const diagramKeys = new Map(); // norm -> 显示名
const diagramLabels = new Map(); // norm -> 标签（用于 STALE，只认组件式命名）
for (const f of diagramFiles) {
  let text = '';
  try { text = readFileSync(f, 'utf8'); } catch { continue; }
  const { ids, labels } = extractNodes(text);
  for (const n of [...ids, ...labels]) {
    const k = norm(n);
    if (k.length < 3) continue;
    if (!diagramKeys.has(k)) diagramKeys.set(k, n);
  }
  for (const n of labels) {
    // 只有"看起来像代码组件名"的标签才参与 STALE：纯 ASCII + 组件后缀 + 无路径分隔
    if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(n)) continue;
    if (!COMPONENT_RE.test(n)) continue;
    const k = norm(n);
    if (k.length < 3) continue;
    if (!diagramLabels.has(k)) diagramLabels.set(k, n);
  }
}

// ---- 比对 ----
const drifts = [];
const stales = [];
for (const [k, file] of codeModules) {
  if (!diagramKeys.has(k)) drifts.push({ name: basename(file).replace(/\.[^.]+$/, ''), file });
}
for (const [k, name] of diagramLabels) {
  if (!codeModules.has(k)) stales.push({ name });
}

const result = {
  scanned: { code: codeModules.size, diagramFiles: diagramFiles.length, diagramNodes: diagramKeys.size },
  drift: drifts.slice(0, 40),
  stale: stales.slice(0, 40),
  driftTotal: drifts.length,
  staleTotal: stales.length,
};

if (jsonOut) {
  console.log(JSON.stringify(result, null, 2));
} else if (!quiet) {
  console.log(`[drift] 扫描 ${result.scanned.code} 模块 / ${result.scanned.diagramFiles} 图文件 / ${result.scanned.diagramNodes} 图节点`);
  if (!drifts.length && !stales.length) {
    console.log('OK  无漂移');
  } else {
    if (drifts.length) {
      console.log(`FAIL  Diagram Drift（代码有、图缺失）${drifts.length} 项`);
      for (const d of result.drift) console.log(`  DRIFT  ${d.name.padEnd(26)} ${d.file}`);
      if (drifts.length > 40) console.log(`  ... 另有 ${drifts.length - 40} 项`);
    }
    if (stales.length) {
      console.log(`STALE 图有节点、代码已删 ${stales.length} 项`);
      for (const s of result.stale.slice(0, 12)) console.log(`  STALE  ${s.name}`);
      if (stales.length > 12) console.log(`  ... 另有 ${stales.length - 12} 项`);
    }
    console.log(`  -> 建议：更新 ${DIAG}/ 下对应图，或加 .diagramdrift.json ignore`);
  }
}

if (drifts.length > 0) process.exit(1);
if (stales.length > 0) process.exit(2);
process.exit(0);
