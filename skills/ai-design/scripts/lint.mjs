#!/usr/bin/env node
// lint.mjs — 渲染前 DSL 预检（零依赖 · 毫秒级 · 不启 Chrome）
//
// 为什么需要它：
//   渲染一张图 = 启 Chrome + 渲 + 审计 + 发现超标 + 改 DSL + 重渲。
//   这个循环里最贵的不是 Chrome，是「改完再渲」那一整轮 LLM turn。
//   本脚本在渲染前用纯字符串把 90% 的超标和 mermaid 静默陷阱一次说清，
//   把「渲染→失败→改→重渲」的多轮压成「预检→改→渲染」两轮。
//
// 用法:
//   node scripts/lint.mjs <in.mmd|in.md>      单文件
//   node scripts/lint.mjs <目录>              批量（跳过 assets/variants/node_modules）
//   node scripts/lint.mjs <路径> --json       机器可读
//   node scripts/lint.mjs <路径> --strict     warn 也算失败（CI 用）
// 退出码: 0 = 无 fail；1 = 有 fail（--strict 下 warn 也 1）
import { readFileSync, readdirSync, statSync, existsSync, realpathSync } from 'node:fs';
import { join, basename, extname, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

// ── 预算（SSOT: references/layout.md，此处为可执行版）──────────────
const BUDGET = {
  maxNodes: 12,
  maxEdges: 14,
  maxLabelChars: 26,
  maxLrLayers: 7,   // LR 每层≈150px，8 层就超 1200px
  minTbLayers: 8,   // TB 长链≥8 层 → 塌成 144px 竖条
};

// 违规码 → 严重度 + 人话说明。severity: fail=必须改；warn=大概率翻车
const RULES = {
  P01: ['fail', '没写方向', '首行补 TD/TB/LR，否则 mermaid 默认竖堆'],
  P02: ['fail', '节点超预算', '砍信息进表（§关键数字/§排查脉络），不是换主题'],
  P03: ['fail', '边超预算', '同上，先砍'],
  P04: ['fail', '标签太长', '一行 ≤26 字；长句拆成两个节点或进表'],
  P05: ['fail', '图块里有尖括号', '开了 htmlLabels，<xxx> 会被当 HTML 标签吃掉；只留 <br/>'],
  P06: ['fail', '名字含括号没加引号', '整个显示名加双引号：A["支付服务(新)"]'],
  P07: ['fail', 'subgraph 跨带连边', '跨带边会让全图 direction 静默失效、塌成竖条；去掉 subgraph，改回竖河主链'],
  P08: ['warn', '有孤立节点', '没有任何边的节点会被竖着堆；用 A ~~~ B 隐形链串起来'],
  P09: ['warn', 'LR 层数过多', 'LR 每层≈150px，层数 ×150 就是画布宽；改 TB 或砍层'],
  P10: ['warn', 'TB 长链', '8 层以上 TB 会塌成一根竖条；改 LR 或按阶段拆'],
  P11: ['fail', '图里写了代码', '图说人话：类名/方法名/path:line 一律进 §0 节点证据表'],
  P12: ['warn', '标签疑似代码', '看着像标识符，确认是业务词就忽略'],
  P13: ['fail', '节点 ID 不合法', 'ID 只用 ASCII 字母数字下划线；中文/空格/括号必炸'],
  P14: ['fail', '用了保留字', 'end/graph/o/x 是保留字，改名或加引号'],
};

const RESERVED = new Set(['end', 'graph', 'o', 'x']);
const SKIP_LINE = /^\s*(classDef|class|style|linkStyle|direction|click|accTitle|accDescr|linkStyle)\b/;
// 长的排前面，避免 `==>` 抢掉 `===>`、`---` 抢掉 `-->`
const ARROW_RE = /^(===>|-\.->|-->|==>|--o|--x|-\.-|---|~~~)/;
// 允许出现在标签里的 HTML 标签（主题靠它们做副标题降级）；其余尖括号一律拦
const SAFE_TAGS = /^<\/?(br|span|b|i|sub|sup|hr)\b[^>]*\/?>$/i;

// ── 代码味检测 ─────────────────────────────────────────────
// P11 硬证据：一眼就是代码的
const HARD_CODE = [
  /\w+\.(java|kt|ts|tsx|js|jsx|mjs|py|go|vue|xml|yml|yaml|sql|md|json)\b/i, // 文件名
  /\w+\.(java|ts|py|go|vue|xml):\d+/,                                        // path:line
  /\w+::\w+/,                                                                 // 静态调用
  /https?:\/\//,                                                              // URL
  /\b[a-z]+\/[A-Za-z0-9_.\-]+\.\w+/,                                          // 相对路径带扩展名
  /\b(SELECT|UPDATE|INSERT|DELETE)\s+[A-Z_]{2,}/,                             // SQL
];
// 白名单：本仓产品名就是 CamelCase，不是代码。项目可在 .diagramlint-allow.txt 追加（一行一个）
const ALLOW = new Set([
  'RequirementMind', 'DiagramMind', 'CodeMind', 'TokenMind',
  'TestMind', 'DesignMind', 'ContextMind', 'BrainMind',
]);
for (const dir of [process.cwd(), resolve(fileURLToPath(import.meta.url), '../..')]) {
  const p = join(dir, '.diagramlint-allow.txt');
  if (!existsSync(p)) continue;
  for (const w of readFileSync(p, 'utf8').split('\n')) {
    if (w.trim() && !w.trim().startsWith('#')) ALLOW.add(w.trim());
  }
}

// P12 软证据：像标识符（camelCase / 下划线常量）
function softCode(s) {
  for (const w of (s.match(/[A-Za-z][A-Za-z0-9_]{4,}/g) || [])) {
    if (w.length < 7) continue;
    if (/^[A-Z]+$/.test(w)) continue;                 // 全大写缩写，不是驼峰
    if (/[a-z][A-Z]/.test(w) && /[A-Z][a-z]/.test(w)) return w;  // camelCase
    if (/^[a-z]+_[A-Z_]{3,}/.test(w)) return w;       // snake 大写常量
  }
  return null;
}

// ── DSL 解析 ───────────────────────────────────────────────
// 引号内文本先掩成占位符，剩下的就是纯粹的 id / 括号 / 箭头
function maskQuotes(line, labels, lineno) {
  return line.replace(/"((?:[^"\\]|\\.)*)"/g, (_m, inner) => {
    labels.push({ text: inner, line: lineno });
    return `\u0000${labels.length - 1}\u0000`;
  });
}

function readBracket(s, i) {
  // s[i] 是 [ ( { 之一；返回括号组结束后的下标
  const close = { '[': ']', '(': ')', '{': '}' }[s[i]];
  let depth = 0;
  for (let j = i; j < s.length; j++) {
    if (s[j] === s[i]) depth++;
    else if (s[j] === close) { depth--; if (depth === 0) return j + 1; }
  }
  return s.length;
}

// 解析一条语句 → { ids:[{id,label}], ops:[箭头], edgeLabels:[] }
function parseStatement(raw, labels) {
  const s = maskQuotes(raw, labels, 0);
  const groups = [[]];
  const ops = [];
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (/\s/.test(c)) { i++; continue; }
    if (c === '|') { const j = s.indexOf('|', i + 1); i = j === -1 ? s.length : j + 1; continue; }
    if (c === '&' || c === ';' || c === ',') { i++; continue; }
    if (c === ':') {  // :::class 速记不是节点，吞掉
      let j = i;
      while (j < s.length && /[A-Za-z0-9_:]/.test(s[j])) j++;
      i = j;
      continue;
    }
    const a = ARROW_RE.exec(s.slice(i));
    if (a && a.index === 0) {
      ops.push(a[1]);
      groups.push([]);
      i += a[1].length;
      continue;
    }
    // `A -- 文本 --> B`：左半 `--` 不是完整箭头，吞掉它和标签，箭头本体留给下一轮
    if ('-=.'.includes(c)) {
      const m = /^[-=.]+\s*[\s\S]*?(?=-->|---|-\.->|==>|===>)/.exec(s.slice(i));
      if (m) { i += m[0].length; continue; }
      i++;
      continue;
    }
    if (/[A-Za-z_]/.test(c)) {
      let j = i;
      while (j < s.length && /[A-Za-z0-9_.]/.test(s[j])) j++;
      const id = s.slice(i, j);
      let label = null;
      let k = j;
      while (k < s.length && /\s/.test(s[k])) k++;
      if (k < s.length && '[{('.includes(s[k])) {
        const end = readBracket(s, k);
        const inner = s.slice(k + 1, end - 1).trim();
        const m = /^\u0000(\d+)\u0000$/.exec(inner);
        label = m ? labels[Number(m[1])]?.text : inner; // 占位符 → 回查被掩的原文
        k = end;
      }
      groups[groups.length - 1].push({ id, label });
      i = k;
      continue;
    }
    i++;
  }
  return { groups, ops };
}

export function parseFlowchart(dsl) {
  const lines = dsl.split('\n');
  const nodes = new Map();
  const edges = [];
  const labels = [];
  const subs = [];
  const stack = [];
  let dir = null;
  let header = null;

  for (let n = 0; n < lines.length; n++) {
    const raw = lines[n];
    const line = raw.replace(/%%.*$/, '').trim();
    if (!line) continue;

    if (n === 0 || header === null) {
      const h = /^(flowchart|graph)\s*(\w+)?/.exec(line);
      if (h) { header = h[1]; dir = (h[2] || '').toUpperCase() || null; continue; }
    }
    if (/^subgraph\b/.test(line)) {
      const m = /^subgraph\s+([^\s[]+)?/.exec(line);
      const name = m && m[1] ? m[1] : `sub_${subs.length}`;
      subs.push(name);
      stack.push(name);
      continue;
    }
    if (/^end\b/.test(line)) { stack.pop(); continue; }
    if (SKIP_LINE.test(line)) continue;

    const { groups, ops } = parseStatement(line, labels);
    const flat = groups.flat();
    for (const g of flat) {
      if (!nodes.has(g.id)) {
        nodes.set(g.id, { id: g.id, label: g.label, sub: stack[stack.length - 1] || null, line: n + 1 });
      } else if (g.label && !nodes.get(g.id).label) {
        nodes.get(g.id).label = g.label;
      }
    }
    for (let k = 0; k < ops.length; k++) {
      const from = groups[k] || [];
      const to = groups[k + 1] || [];
      if (!from.length || !to.length) continue;
      const invisible = ops[k] === '~~~';
      for (const f of from) for (const t of to) {
        edges.push({ from: f.id, to: t.id, invisible });
      }
    }
  }
  return { kind: 'flowchart', dir, nodes, edges, labels, subs };
}

// ── 检查 ───────────────────────────────────────────────────
function labelLines(t) {
  return String(t || '')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<[^>]*>/g, '')
    .replace(/&nbsp;/g, ' ')
    .split('\n');
}

function longestLine(t) {
  return labelLines(t).reduce((a, b) => (b.trim().length > a.length ? b.trim() : a), '');
}

function layerCount(nodes, edges) {
  // 最长路径的节点数 = 层数（沿 LR 方向就是宽度）
  const adj = new Map();
  for (const e of edges) {
    if (!adj.has(e.from)) adj.set(e.from, []);
    adj.get(e.from).push(e.to);
  }
  const indeg = new Map();
  for (const id of nodes.keys()) indeg.set(id, 0);
  for (const e of edges) {
    if (indeg.has(e.to)) indeg.set(e.to, indeg.get(e.to) + 1);
  }
  const depth = new Map();
  const walk = (id, seen) => {
    if (depth.has(id)) return depth.get(id);
    if (seen.has(id)) return 1;          // 有环，兜住不炸
    seen.add(id);
    let d = 1;
    for (const nx of adj.get(id) || []) d = Math.max(d, 1 + walk(nx, seen));
    depth.set(id, d);
    return d;
  };
  let best = 0;
  for (const id of nodes.keys()) best = Math.max(best, walk(id, new Set()));
  return best;
}

export function lintDsl(dsl) {
  const out = [];
  const add = (code, where, detail) => {
    const r = RULES[code];
    out.push({ code, sev: r[0], rule: r[1], where, detail, fix: r[2] });
  };

  const first = (dsl.split('\n').find((l) => l.trim()) || '');
  const isFlow = /^(flowchart|graph)\b/.test(first.trim());

  // 通用检查（所有图型）
  dsl.split('\n').forEach((l, i) => {
    const bad = (l.match(/<[^>\s][^>]*>/g) || []).filter((t) => !SAFE_TAGS.test(t));
    if (bad.length) add('P05', `第${i + 1}行`, `出现 ${bad.join(' ')}`);
  });

  const allLabels = [];
  if (isFlow) {
    const g = parseFlowchart(dsl);
    for (const [, nd] of g.nodes) if (nd.label) allLabels.push({ text: nd.label, line: nd.line });
  } else {
    // 非 flowchart：把引号里的文本当标签粗查一遍
    dsl.split('\n').forEach((l, i) => {
      for (const m of l.matchAll(/"([^"]{2,})"/g)) allLabels.push({ text: m[1], line: i + 1 });
      for (const m of l.matchAll(/\[([^\]"\n]{2,})\]/g)) allLabels.push({ text: m[1], line: i + 1 });
    });
  }

  for (const { text, line } of allLabels) {
    for (const re of HARD_CODE) {
      const m = re.exec(text);
      if (m) { add('P11', `第${line}行`, `「${text.slice(0, 30)}」命中 ${m[0]}`); break; }
    }
    const w = softCode(text);
    if (w && !ALLOW.has(w)) add('P12', `第${line}行`, `疑似标识符：${w}`);
    const long = longestLine(text);
    if (long.length > BUDGET.maxLabelChars) {
      add('P04', `第${line}行`, `${long.length} 字 > ${BUDGET.maxLabelChars}：「${long.slice(0, 16)}…」`);
    }
  }

  if (!isFlow) return out;

  const g = parseFlowchart(dsl);
  if (!g.dir) add('P01', '首行', '未声明 TD/TB/LR');

  // 节点 ID 合法性
  for (const [id, nd] of g.nodes) {
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(id)) add('P13', `第${nd.line}行`, `ID「${id}」`);
    // 只认全小写：mermaid 官方绕过 `end` 的办法就是首字母大写（End / Graph 都是好 ID）
    if (id === 'end' || id === 'graph' || id === 'o' || id === 'x') {
      add('P14', `第${nd.line}行`, `ID「${id}」是保留字`);
    }
  }
  // 未加引号却带括号的显示名（从原始文本里捞）
  dsl.split('\n').forEach((l, i) => {
    // 排除 `[( )]` 圆柱、`[/ /]` 平行四边形 —— 那是有意形状，不是裸名字
    const m = l.match(/[A-Za-z_][A-Za-z0-9_]*\[(?![\/(])([^"\]\n]*[()（）][^"\]\n]*)\]/);
    if (m) add('P06', `第${i + 1}行`, `「${m[1].slice(0, 20)}」`);
  });

  const visEdges = g.edges.filter((e) => !e.invisible);
  if (g.nodes.size > BUDGET.maxNodes) add('P02', '全图', `${g.nodes.size} 个 > ${BUDGET.maxNodes}`);
  if (visEdges.length > BUDGET.maxEdges) add('P03', '全图', `${visEdges.length} 条 > ${BUDGET.maxEdges}`);

  // subgraph 跨带边 —— mermaid 静默陷阱 #1
  if (g.subs.length) {
    for (const e of visEdges) {
      const a = g.nodes.get(e.from)?.sub || null;
      const b = g.nodes.get(e.to)?.sub || null;
      if (a !== b) add('P07', '全图', `${e.from}(${a || '顶层'}) → ${e.to}(${b || '顶层'})`);
    }
  }

  // 孤立节点 —— 静默陷阱 #2
  const linked = new Set();
  for (const e of g.edges) { linked.add(e.from); linked.add(e.to); }
  for (const [id] of g.nodes) {
    if (!linked.has(id)) add('P08', '全图', `节点 ${id} 没有任何边`);
  }

  // 层数 —— 静默陷阱 #3
  // 注意：TB 长链本身不是病（layout.md 旗舰范例就是 TB 9 层 + 分支/锚点撑宽，实测 676×1354 达标）。
  // 病的是「一条到底、毫无分叉」——那才会塌成 144px 竖条。所以只有 branches===0 才报。
  const layers = layerCount(g.nodes, visEdges);
  const outdeg = new Map();
  for (const e of visEdges) outdeg.set(e.from, (outdeg.get(e.from) || 0) + 1);
  const branches = [...outdeg.values()].filter((n) => n >= 2).length;
  if (g.dir === 'LR' && layers > BUDGET.maxLrLayers) {
    add('P09', '全图', `${layers} 层 ≈ ${layers * 150}px 宽 > 1200px`);
  }
  if ((g.dir === 'TB' || g.dir === 'TD' || !g.dir) && layers >= BUDGET.minTbLayers && branches === 0) {
    add('P10', '全图', `${layers} 层且无一处分叉，TB 长链会塌成竖条（加分支或侧挂锚点撑宽）`);
  }

  return out;
}

// ── 输入收集 ───────────────────────────────────────────────
function extractBlocks(text) {
  const blocks = [];
  const re = /```mermaid[ \t]*\r?\n([\s\S]*?)```/g;
  let m;
  while ((m = re.exec(text))) blocks.push(m[1].replace(/\t/g, '  '));
  return blocks;
}

function collect(target) {
  const st = statSync(target);
  if (!st.isDirectory()) {
    const ext = extname(target).toLowerCase();
    const text = readFileSync(target, 'utf8');
    const blocks = ['.mmd', '.mermaid'].includes(ext) ? [text] : extractBlocks(text);
    return blocks.map((b, i) => ({ file: basename(target), dsl: b, idx: i + 1 }));
  }
  const acc = [];
  (function walk(d) {
    for (const e of readdirSync(d, { withFileTypes: true })) {
      const p = join(d, e.name);
      if (e.isDirectory()) {
        if (['assets', 'variants', 'node_modules', '.git'].includes(e.name)) continue;
        walk(p);
      } else if (['.mmd', '.mermaid', '.md'].includes(extname(p).toLowerCase())) {
        acc.push(...collect(p));
      }
    }
  })(target);
  return acc;
}

// ── main ───────────────────────────────────────────────────
const argv = process.argv.slice(2);
const JSON_OUT = argv.includes('--json');
const STRICT = argv.includes('--strict');
const paths = argv.filter((a) => !a.startsWith('--'));

// 被 import 时不自动跑 main（render.mjs / 测试可直接复用 lintDsl）
function runningAsMain() {
  const e = process.argv[1];
  if (!e) return false;
  try { return realpathSync(resolve(e)) === realpathSync(fileURLToPath(import.meta.url)); } catch { return false; }
}

if (!runningAsMain()) { /* noop */ } else if (!paths.length) {
  console.error('用法: node scripts/lint.mjs <in.mmd|in.md|目录> [--json] [--strict]');
  process.exitCode = 1;
} else if (!paths.every(existsSync)) {
  console.error(`[lint] 路径不存在: ${paths.filter((p) => !existsSync(p)).join(', ')}`);
  process.exitCode = 1;
} else {
  const items = paths.flatMap(collect);
  const report = [];
  for (const it of items) {
    const issues = lintDsl(it.dsl);
    report.push({ file: it.file, block: it.idx, issues });
  }

  const fails = report.flatMap((r) => r.issues.filter((i) => i.sev === 'fail'));
  const warns = report.flatMap((r) => r.issues.filter((i) => i.sev === 'warn'));

  if (JSON_OUT) {
    console.log(JSON.stringify({ budget: BUDGET, files: report.length, fail: fails.length, warn: warns.length, report }, null, 2));
  } else {
    const clean = report.filter((r) => !r.issues.length);
    for (const r of report) {
      if (!r.issues.length) continue;
      console.log(`\n${r.file} · 图${r.block}`);
      for (const i of r.issues) {
        const mark = i.sev === 'fail' ? '✗' : '!';
        console.log(`  ${mark} ${i.code} ${i.rule} ${i.where ? `(${i.where})` : ''}${i.detail ? ` — ${i.detail}` : ''}`);
        console.log(`      怎么改: ${i.fix}`);
      }
    }
    if (clean.length) console.log(`\n✓ 无问题: ${clean.map((c) => `${c.file}·图${c.block}`).join(', ')}`);
    const tail = report.length
      ? `\n[lint] ${report.length} 张图：fail ${fails.length} · warn ${warns.length}`
      : '\n[lint] 没找到图块';
    console.log(tail);
    if (fails.length) console.log('  → 先按上面改完再跑 render.mjs，别靠重渲试错');
  }
  process.exitCode = fails.length || (STRICT && warns.length) ? 1 : 0;
}
