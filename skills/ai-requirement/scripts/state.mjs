#!/usr/bin/env node
// RequirementMind 状态辅助脚本（确定性部分，不含任何 LLM 逻辑）
// 用法: node state.mjs <counters|validate|gate|snapshot|migrate> <.requirementmind 目录> [--write]

import { readFileSync, writeFileSync, existsSync, mkdirSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const cmd = process.argv[2];
const dir = process.argv[3];
if (!dir || !['counters', 'frontier', 'freeze', 'risk', 'stop', 'eval', 'validate', 'gate', 'snapshot', 'migrate', 'route', 'budget', 'ledger', 'impact-graph', 'context', 'ir', 'gate-state', 'evidence-pack', 'decision-memory'].includes(cmd)) {
  console.error('用法: node state.mjs <counters|frontier|freeze|risk|stop|eval|validate|gate|snapshot|migrate|route|budget|ledger|impact-graph|context|ir|gate-state|evidence-pack|decision-memory> <.requirementmind 目录> [参数]');
  console.error('  frontier : 输出当前待问批量（OPEN 的 USER_ONLY BLOCKING+IMPORTANT + OPEN 冲突）与计数；TECHNICAL 不问用户');
  console.error('  freeze   : freeze <dir> <Q-xxx|CON-xxx> "<选项字母或决定文本>" [--supersede] [--auto] [--impact "a,b"] — 冻结为 DEC（--auto=AI 自治裁决）');
  console.error('  risk     : 校验 risk.json 八维评分 → 分层 LIGHT/FOCUSED/COUNCIL + 派专家（COUNCIL=五专家强制）');
  console.error('  stop     : 停止条件判定（R9 + 风险维度证据覆盖率）；退出码 0 = 收敛，禁止继续追问/审查');
  console.error('  eval     : 会话指标（用户自治率 / Reviewer 验真率 / 轮次），供 Eval 闭环');
  console.error('  route    : Complexity Router → task_level L0–L3 [--write]');
  console.error('  budget   : Change Budget [--write] [--files N] [--modules N] [--database true|false] [--new-service true|false]');
  console.error('  ledger   : ledger list|validate|append <claim> [--kind KIND] [--refs "a,b"] [--link DEC-001]');
  console.error('  impact-graph : 从 decisions 生成 decision-graph.json [--write]');
  console.error('  context  : 导出 Decision Context Contract JSON（stdout）');
  console.error('  ir            : 从 canonical JSON 单向生成 Requirement IR 7 文件（ir/requirement.yaml 等），供 Coding/Project-Brain/ContextMind/TestMind 消费');
  console.error('  gate-state    : 输出 Gate 状态机当前节点 + 迁移历史；gate-state --record --to FROZEN 记录状态迁移');
  console.error('  evidence-pack : 聚合 facts/decisions/challenges/evidence-ledger → 统一四元组（结论/证据/可信度/验证方式）');
  console.error('  decision-memory: 聚合 decisions + history/ → decision-memory.json（带 rejected_alternatives / failure_history）');
  process.exit(2);
}
const writeFlag = process.argv.includes('--write');
const read = (f) => {
  const p = join(dir, f);
  if (!existsSync(p)) return [];
  const raw = readFileSync(p, 'utf8').trim();
  return raw ? JSON.parse(raw) : [];
};
const isArr = (v) => (Array.isArray(v) ? v : v ? [v] : []);

function countersData() {
  const questions = isArr(read('questions.json'));
  const conflicts = isArr(read('conflicts.json'));
  const assumptions = isArr(read('assumptions.json'));
  const challenges = isArr(read('challenges.json'));
  return {
    blocking_questions: questions.filter((q) => q.priority === 'BLOCKING' && q.status === 'OPEN').length,
    blocking_conflicts: conflicts.filter((x) => x.severity === 'BLOCKING' && x.status === 'OPEN').length,
    critical_assumptions: assumptions.filter((a) => a.risk === 'HIGH' && a.status === 'UNVERIFIED').length,
    unvalidated_high_risks: challenges.filter((x) => x.status === 'PENDING_VALIDATION' && x.severity === 'BLOCKING').length,
  };
}

function counters() {
  const c = countersData();
  for (const [k, v] of Object.entries(c)) console.log(`${k}: ${v}`);
  console.log(c.blocking_questions + c.blocking_conflicts + c.critical_assumptions + c.unvalidated_high_risks === 0
    ? '=> 关键疑问已清零 (R9 出口)' : '=> 仍有 BLOCKING 项，禁止进入下一阶段');
}

function frontier() {
  const questions = isArr(read('questions.json'));
  const conflicts = isArr(read('conflicts.json'));
  const rank = { BLOCKING: 0, IMPORTANT: 1 };
  const open = questions
    .filter((q) => q.status === 'OPEN' && q.priority !== 'OPTIONAL' && q.authority !== 'TECHNICAL')
    .sort((a, b) => (rank[a.priority] ?? 9) - (rank[b.priority] ?? 9));
  const tech = questions.filter((q) => q.status === 'OPEN' && q.priority !== 'OPTIONAL' && q.authority === 'TECHNICAL');
  const openCon = conflicts.filter((x) => x.status === 'OPEN');
  for (const q of open) {
    console.log(`${q.id} [${q.priority}] ${q.topic}`);
    console.log(`  问: ${q.question}`);
    console.log(`  缘由: ${q.reason}`);
    console.log(`  选项: ${(q.options || []).join(' | ')}`);
    console.log(`  推荐: ${q.recommended_option || '?'} — ${q.recommendation_reason || '（先补推荐再展示）'}`);
  }
  for (const c of openCon) {
    console.log(`${c.id} [CONFLICT/${c.severity}]`);
    console.log(`  左: ${c.left}`);
    console.log(`  右: ${c.right}`);
  }
  const c = countersData();
  console.log('---');
  console.log(`frontier = ${open.length} 问 + ${openCon.length} 冲突（OPTIONAL 不问走默认值；TECHNICAL 未决 ${tech.length} 条：AI 采纳推荐 freeze --auto，不问用户）`);
  console.log(`计数: blocking_questions=${c.blocking_questions} blocking_conflicts=${c.blocking_conflicts} critical_assumptions=${c.critical_assumptions} unvalidated_high_risks=${c.unvalidated_high_risks}`);
  if (open.length + openCon.length + tech.length === 0 && c.critical_assumptions === 0 && c.unvalidated_high_risks === 0) {
    console.log('=> frontier 已空且关键疑问清零（R9），可进入 Phase 4');
  } else {
    process.exitCode = 1;
    console.log('=> 仍有待决项，禁止进入 Phase 4');
  }
}

const ENUMS = {
  'facts.json': { category: ['stack', 'structure', 'database', 'api', 'test', 'business_rule', 'history', 'constraint', 'doc'], status: ['VERIFIED'] },
  'questions.json': { priority: ['BLOCKING', 'IMPORTANT', 'OPTIONAL'], status: ['OPEN', 'ANSWERED'], authority: ['USER_ONLY', 'TECHNICAL'], value: ['HIGH', 'MEDIUM', 'LOW'] },
  'decisions.json': { source: ['USER', 'AI_DEFAULT'], status: ['FROZEN', 'SUPERSEDED'] },
  'assumptions.json': { risk: ['HIGH', 'MEDIUM', 'LOW'], source: ['MODEL_INFERENCE'], status: ['UNVERIFIED', 'CONFIRMED_AS_FACT', 'RESOLVED'] },
  'conflicts.json': { severity: ['BLOCKING', 'IMPORTANT'], status: ['OPEN', 'RESOLVED'] },
  'challenges.json': { severity: ['BLOCKING', 'HIGH', 'MEDIUM'], status: ['PENDING_VALIDATION', 'CONFIRMED', 'PLAUSIBLE', 'REFUTED'] },
  'evidence.json': { verdict: ['CONFIRMED', 'PLAUSIBLE', 'REFUTED'] },
};
const REQUIRED = {
  'facts.json': ['id', 'category', 'statement', 'source', 'confidence', 'status'],
  'questions.json': ['id', 'topic', 'question', 'reason', 'priority', 'options', 'recommended_option', 'recommendation_reason', 'authority', 'value', 'status'],
  'decisions.json': ['id', 'question_id', 'decision', 'topic', 'source', 'status', 'created_at'],
  'assumptions.json': ['id', 'statement', 'risk', 'source', 'status'],
  'conflicts.json': ['id', 'left', 'right', 'severity', 'status'],
  'challenges.json': ['id', 'claim', 'evidence', 'validation', 'severity', 'status'],
  'evidence.json': ['id', 'challenge_id', 'verdict', 'reasoning'],
};

function validate() {
  let errors = 0;
  for (const [file, req] of Object.entries(REQUIRED)) {
    let items;
    try { items = isArr(read(file)); } catch (e) { console.log(`${file}: JSON 解析失败 - ${e.message}`); errors++; continue; }
    for (const item of items) {
      for (const k of req) if (item[k] === undefined) { console.log(`${file} ${item.id || '?'}: 缺少字段 ${k}`); errors++; }
      for (const [k, allowed] of Object.entries(ENUMS[file] || {}))
        if (item[k] !== undefined && !allowed.includes(item[k])) { console.log(`${file} ${item.id || '?'}: ${k}=${item[k]} 不在枚举内`); errors++; }
      if (file === 'questions.json' && item.options?.length) {
        const letters = ['A', 'B', 'C', 'D'].slice(0, item.options.length);
        if (item.recommended_option && !letters.includes(item.recommended_option)) {
          console.log(`${file} ${item.id || '?'}: recommended_option=${item.recommended_option} 与 options 条数不匹配`);
          errors++;
        }
        if (item.recommendation_reason !== undefined && !String(item.recommendation_reason).trim()) {
          console.log(`${file} ${item.id || '?'}: recommendation_reason 不能为空`);
          errors++;
        }
        const needsRec = item.status === 'OPEN'
          && item.priority !== 'OPTIONAL'
          && item.authority !== 'TECHNICAL';
        if (needsRec) {
          if (!item.recommended_option) {
            console.log(`${file} ${item.id || '?'}: OPEN USER_ONLY 问题缺少 recommended_option（展示前必填）`);
            errors++;
          }
          if (!String(item.recommendation_reason || '').trim()) {
            console.log(`${file} ${item.id || '?'}: OPEN USER_ONLY 问题缺少 recommendation_reason（展示前必填）`);
            errors++;
          }
        }
      }
    }
    if (items.length) console.log(`${file}: ${items.length} 条 OK`);
  }
  const decs = isArr(read('decisions.json'));
  for (const d of decs.filter((x) => x.status === 'SUPERSEDED'))
    if (!d.replaced_by) { console.log(`decisions.json ${d.id}: SUPERSEDED 缺 replaced_by`); errors++; }
  console.log(errors === 0 ? '=> 校验通过' : `=> ${errors} 个错误`);
  process.exitCode = errors === 0 ? 0 : 1;
}

const CHECKLIST = ['business_goal', 'scope', 'core_flow', 'business_rules', 'data_model', 'api_contract', 'state_machine', 'validation_rules', 'permission', 'concurrency', 'idempotency', 'exception_handling', 'compatibility', 'acceptance_criteria', 'testability', 'spec_consistency'];

function gate() {
  const gPath = join(dir, 'gate.json');
  const g = existsSync(gPath) ? JSON.parse(readFileSync(gPath, 'utf8')) : null;
  const hard = countersData();
  const hardSum = Object.values(hard).reduce((s, v) => s + v, 0);
  if (!g) {
    console.log(JSON.stringify({ status: hardSum === 0 ? 'HARD-GATE-OK(待检查表)' : 'BLOCKED', hard_counters: hard }, null, 2));
    process.exitCode = hardSum === 0 ? 0 : 1;
    return;
  }
  const missing = [];
  for (const k of CHECKLIST) if (g.checklist?.[k] !== 'PASS') missing.push(`checklist.${k} != PASS`);
  for (const [k, v] of Object.entries(hard)) if (v > 0) missing.push(`${k}=${v}`);
  const status = missing.length === 0 ? 'READY_FOR_DEVELOPMENT' : 'BLOCKED';
  console.log(JSON.stringify({ status, hard_counters: hard, missing }, null, 2));
  process.exitCode = status === 'READY_FOR_DEVELOPMENT' ? 0 : 1;
}

function snapshot() {
  const hDir = join(dir, 'history');
  if (!existsSync(hDir)) mkdirSync(hDir, { recursive: true });
  const n = readdirSync(hDir).length + 1;
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const files = ['session.json', 'facts.json', 'questions.json', 'decisions.json', 'assumptions.json', 'conflicts.json', 'challenges.json', 'evidence.json', 'evidence-ledger.json', 'change-budget.json', 'decision-graph.json', 'gate.json'];
  const snap = {};
  for (const f of files) { const p = join(dir, f); if (existsSync(p)) snap[f] = JSON.parse(readFileSync(p, 'utf8')); }
  writeFileSync(join(hDir, `${String(n).padStart(3, '0')}-${stamp}.json`), JSON.stringify(snap, null, 2));
  console.log(`快照已写入 history/${String(n).padStart(3, '0')}-${stamp}.json`);
}

const OPTION_LETTERS = ['A', 'B', 'C', 'D'];

function normalizeQuestionOptions(q) {
  const raw = Array.isArray(q.options) ? q.options.filter(Boolean) : [];
  const letters = OPTION_LETTERS.slice(0, Math.min(raw.length, 4));
  const options = raw.map((opt, i) => {
    const s = String(opt).trim();
    const letter = letters[i];
    const prefixed = new RegExp(`^${letter}[.．、\\s]`, 'i').test(s);
    if (prefixed) return s;
    return `${letter}. ${s}`;
  });
  return { ...q, options };
}

function letterForOptionMatch(decision, options) {
  const d = String(decision).trim();
  if (!d) return null;
  const letterOnly = d.match(/^([A-D])\.?$/i);
  if (letterOnly) return letterOnly[1].toUpperCase();
  for (let i = 0; i < options.length; i++) {
    const letter = OPTION_LETTERS[i];
    const opt = String(options[i]);
    if (d === opt || opt.endsWith(d) || opt.includes(d)) return letter;
    const body = opt.replace(/^[A-D][.．、\s]+/i, '').trim();
    if (d === body || body.includes(d) || d.includes(body)) return letter;
  }
  return null;
}

function frozenDecisionForQuestion(decisions, questionId) {
  const list = decisions
    .filter((x) => x.question_id === questionId && x.status === 'FROZEN')
    .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')));
  return list[0] || null;
}

function migrateQuestions() {
  const qPath = join(dir, 'questions.json');
  if (!existsSync(qPath)) {
    console.log('questions.json 不存在，无需迁移');
    return;
  }
  const questions = isArr(JSON.parse(readFileSync(qPath, 'utf8').trim() || '[]'));
  const decisions = isArr(read('decisions.json'));
  let changed = 0;
  const out = questions.map((q) => {
    let item = normalizeQuestionOptions(q);
    let touched = false;
    if (!item.authority) { item.authority = 'USER_ONLY'; touched = true; }
    if (!item.value) { item.value = 'MEDIUM'; touched = true; }
    const letters = OPTION_LETTERS.slice(0, item.options.length);
    const needsRec =
      !item.recommended_option ||
      !letters.includes(item.recommended_option) ||
      !String(item.recommendation_reason || '').trim();
    if (!needsRec) {
      if (touched) changed++;
      return item;
    }
    touched = true;

    const dec = frozenDecisionForQuestion(decisions, item.id);
    let recommended = item.recommended_option;
    let reason = String(item.recommendation_reason || '').trim();
    if (dec) {
      const letter = letterForOptionMatch(dec.decision, item.options);
      if (letter) {
        recommended = letter;
        reason = `与已冻结决策 ${dec.id} 一致（migrate 推断，请核对 facts 后改写推荐理由）`;
      }
    }
    if (!recommended || !letters.includes(recommended)) recommended = letters[0];
    if (!reason) {
      reason =
        item.status === 'ANSWERED'
          ? '【迁移占位】已回答但无法自动匹配选项，请 Agent 根据 facts 补充推荐理由'
          : '【迁移占位】请 Agent 根据 facts.json 补充推荐理由后再向用户展示';
    }
    changed++;
    console.log(`${item.id}: recommended_option=${recommended} (${writeFlag ? '将写入' : '预览'})`);
    return { ...item, recommended_option: recommended, recommendation_reason: reason };
  });
  if (!changed) {
    console.log('=> 所有问题字段完备，无需迁移');
    return;
  }
  if (writeFlag) {
    writeFileSync(qPath, JSON.stringify(out, null, 2) + '\n');
    console.log(`=> 已更新 questions.json（${changed} 条）`);
  } else {
    console.log(`=> 预览：${changed} 条待更新。确认后加 --write：node state.mjs migrate <dir> --write`);
  }
}

function nextId(items, prefix) {
  const max = items.reduce((m, x) => {
    const match = String(x.id || '').match(new RegExp(`^${prefix}(\\d+)$`));
    return match ? Math.max(m, Number(match[1])) : m;
  }, 0);
  return `${prefix}${String(max + 1).padStart(3, '0')}`;
}

const stripOptionLetter = (s) => String(s).replace(/^[A-D][.．、\s]+/i, '').trim();

const writeJson = (name, data) => writeFileSync(join(dir, name), JSON.stringify(data, null, 2) + '\n');

function freeze() {
  const rest = process.argv.slice(4);
  const [target, answer] = rest;
  const flags = rest.slice(2);
  const supersede = flags.includes('--supersede');
  const auto = flags.includes('--auto');
  const impactIdx = flags.indexOf('--impact');
  const impact = impactIdx >= 0 && flags[impactIdx + 1]
    ? flags[impactIdx + 1].split(',').map((s) => s.trim()).filter(Boolean)
    : undefined;
  const splitFlag = (name) => {
    const i = flags.indexOf(name);
    return i >= 0 && flags[i + 1]
      ? flags[i + 1].split(',').map((s) => s.trim()).filter(Boolean)
      : undefined;
  };
  const impactFiles = splitFlag('--impact-files');
  const impactTests = splitFlag('--impact-tests');
  const impactModules = impact;
  if (!target || !answer || !/^(Q|CON)-\d+$/.test(target)) {
    console.error('用法: node state.mjs freeze <dir> <Q-xxx|CON-xxx> "<选项字母或决定文本>" [--supersede] [--auto] [--impact "a,b"]');
    process.exit(2);
  }
  const decisions = isArr(read('decisions.json'));
  const newId = nextId(decisions, 'DEC-');
  const base = { id: newId, question_id: target, source: auto ? 'AI_DEFAULT' : 'USER', status: 'FROZEN', created_at: new Date().toISOString() };
  if (impact) base.impact = impact;
  if (impactModules || impactFiles || impactTests) {
    base.impact_scope = {
      modules: impactModules || [],
      files: impactFiles || [],
      tests: impactTests || [],
    };
  }

  if (target.startsWith('CON-')) {
    const conflicts = isArr(read('conflicts.json'));
    const c = conflicts.find((x) => x.id === target);
    if (!c) { console.error(`${target}: conflicts.json 中不存在`); process.exit(1); }
    if (c.status === 'RESOLVED' && !supersede) {
      console.error(`${target} 已由 ${c.resolution_decision_id || '未知 DEC'} 裁决（R5 禁止静默覆盖）。确认改判请加 --supersede`);
      process.exit(1);
    }
    if (supersede && c.resolution_decision_id) {
      const old = decisions.find((d) => d.id === c.resolution_decision_id && d.status === 'FROZEN');
      if (old) { old.status = 'SUPERSEDED'; old.replaced_by = newId; }
    }
    decisions.push({ ...base, decision: String(answer).trim(), topic: `conflict:${c.id}` });
    c.status = 'RESOLVED';
    c.resolution_decision_id = newId;
    writeJson('decisions.json', decisions);
    writeJson('conflicts.json', conflicts);
    console.log(`${newId} FROZEN ← ${target} 「${String(answer).trim()}」`);
  } else {
    const questions = isArr(JSON.parse(existsSync(join(dir, 'questions.json')) ? readFileSync(join(dir, 'questions.json'), 'utf8').trim() || '[]' : '[]'));
    const q = questions.find((x) => x.id === target);
    if (!q) { console.error(`${target}: questions.json 中不存在`); process.exit(1); }
    const frozen = decisions.filter((d) => d.question_id === q.id && d.status === 'FROZEN');
    if (frozen.length && !supersede) {
      console.error(`${q.id} 已有冻结决策 ${frozen.map((d) => d.id).join(', ')}（R5 禁止静默覆盖）。确认改判请加 --supersede`);
      process.exit(1);
    }
    const letters = OPTION_LETTERS.slice(0, (q.options || []).length);
    const m = String(answer).trim().match(/^([A-Da-d])[.．、]?$/);
    const letter = m && letters.includes(m[1].toUpperCase()) ? m[1].toUpperCase() : null;
    const decisionText = letter ? stripOptionLetter(q.options[letters.indexOf(letter)]) : String(answer).trim();
    for (const d of frozen) { d.status = 'SUPERSEDED'; d.replaced_by = newId; }
    decisions.push({ ...base, decision: decisionText, topic: q.topic });
    q.status = 'ANSWERED';
    writeJson('decisions.json', decisions);
    writeJson('questions.json', questions);
    console.log(`${newId} FROZEN ← ${q.id} 「${decisionText}」${frozen.length ? `（supersede ${frozen.map((d) => d.id).join(', ')}）` : ''}`);
  }
  snapshot();
  counters();
}

const RISK_DIMS = ['business_criticality', 'data_impact', 'concurrency_risk', 'security_risk', 'compatibility_risk', 'irreversibility', 'blast_radius', 'evidence_gap'];
const SPECIALIST_FOR = {
  security_risk: 'security',
  data_impact: 'data_integrity',
  irreversibility: 'data_integrity',
  concurrency_risk: 'concurrency',
  compatibility_risk: 'compatibility',
  evidence_gap: 'testability',
};

function risk() {
  const p = join(dir, 'risk.json');
  if (!existsSync(p)) {
    console.error('risk.json 不存在 — Phase 2 后必须先完成八维风险评分（见 references/risk-router.md）');
    process.exit(1);
  }
  let r;
  try { r = JSON.parse(readFileSync(p, 'utf8')); } catch (e) { console.error(`risk.json 解析失败: ${e.message}`); process.exit(1); }
  const dims = r.dimensions || {};
  const bad = [];
  for (const k of RISK_DIMS) {
    const d = dims[k];
    if (!d) { bad.push(`缺维度 ${k}`); continue; }
    const s = Number(d.score);
    if (!Number.isInteger(s) || s < 0 || s > 3) bad.push(`${k}.score=${JSON.stringify(d.score)} 应为 0-3 整数`);
    if (s >= 2 && !(Array.isArray(d.refs) && d.refs.length)) bad.push(`${k}.score>=2 必须给 refs（FACT/CON/DEC id）`);
  }
  if (bad.length) { for (const b of bad) console.error(`risk.json: ${b}`); process.exit(1); }
  const total = RISK_DIMS.reduce((sum, k) => sum + Number(dims[k].score), 0);
  const tier = total >= 15 ? 'COUNCIL' : total >= 8 ? 'FOCUSED' : 'LIGHT';
  const ranked = RISK_DIMS.map((k) => [k, Number(dims[k].score)]).sort((a, b) => b[1] - a[1]);
  const specialists = [];
  if (tier !== 'LIGHT') {
    // V5：COUNCIL 必须派满 5 专家委员会（按风险分数从高到低，最多 5 个不同维度映射）
    const cap = tier === 'COUNCIL' ? COUNCIL_FIVE.length : 1;
    for (const [k, s] of ranked) {
      if (specialists.length >= cap) break;
      if (tier === 'FOCUSED' && s < 2) break;
      const sp = SPECIALIST_FOR[k];
      if (sp && !specialists.includes(sp)) specialists.push(sp);
    }
    // V5：COUNCIL 必须补齐所有 5 专家（即使 score<2，按 ZERO_BUT_REQUIRED 标注）
    if (tier === 'COUNCIL') {
      for (const sp of COUNCIL_FIVE) {
        if (!specialists.includes(sp)) specialists.push(sp);
      }
    }
  }
  console.log(JSON.stringify({ total, tier, specialists, top_dims: ranked.filter(([, s]) => s >= 2) }, null, 2));
  console.log(tier === 'LIGHT'
    ? '=> LIGHT：现有轻量流程（主 Agent + Reviewer + Validator），禁止追加角色'
    : tier === 'FOCUSED'
      ? '=> FOCUSED：现有流程 + 1 名专项 Reviewer（references/specialists.md 对应节）'
      : `=> COUNCIL：五专家委员会强制派发（${specialists.join(' / ')}），全部 BLOCKING CLAIM 必须过 Validator`);
  if (writeFlag) {
    r.total = total;
    r.tier = tier;
    r.specialists = specialists;
    r.updated_at = new Date().toISOString();
    writeJson('risk.json', r);
    console.log('=> 已写回 risk.json（tier/specialists）');
  }
}

function stop() {
  const questions = isArr(read('questions.json'));
  const conflicts = isArr(read('conflicts.json'));
  const c = countersData();
  const openQ = questions.filter((q) => q.status === 'OPEN' && q.priority !== 'OPTIONAL');
  const openCon = conflicts.filter((x) => x.status === 'OPEN');
  const checks = {
    open_questions: openQ.length,
    open_conflicts: openCon.length,
    critical_assumptions: c.critical_assumptions,
    unvalidated_high_risks: c.unvalidated_high_risks,
  };
  const known = new Set([
    ...isArr(read('facts.json')).map((x) => x.id),
    ...isArr(read('decisions.json')).map((x) => x.id),
    ...isArr(read('conflicts.json')).map((x) => x.id),
  ]);
  const gaps = [];
  const rp = join(dir, 'risk.json');
  if (!existsSync(rp)) gaps.push('risk.json 缺失（先完成 Phase 2.5 风险评分）');
  else {
    const dims = (JSON.parse(readFileSync(rp, 'utf8')).dimensions) || {};
    for (const k of RISK_DIMS) {
      const d = dims[k];
      if (!d || Number(d.score) < 2) continue;
      if (!Array.isArray(d.refs) || !d.refs.length) { gaps.push(`${k}: score>=2 但无 refs`); continue; }
      for (const ref of d.refs) if (!known.has(ref)) gaps.push(`${k}: ref ${ref} 无法解析为 FACT/DEC/CON`);
    }
  }
  checks.coverage_gaps = gaps.length;
  const blocked = Object.values(checks).reduce((s, v) => s + v, 0);
  for (const [k, v] of Object.entries(checks)) console.log(`${k}: ${v}`);
  for (const g of gaps) console.log(`  覆盖缺口: ${g}`);
  if (blocked === 0) console.log('=> STOP 条件满足（R9 + 覆盖率）：禁止继续追问或“为了严谨”追加审查');
  else console.log('=> 未满足停止条件');
  process.exitCode = blocked === 0 ? 0 : 1;
}

const TASK_LEVEL_DEFAULTS = {
  L0: { files: 3, modules: 1, database: false, new_service: false },
  L1: { files: 10, modules: 2, database: false, new_service: false },
  L2: { files: 25, modules: 5, database: true, new_service: false },
  L3: { files: 15, modules: 3, database: false, new_service: false },
};

const L2_KEYWORDS = /架构|平台|agent\s*os|微服务|新服务|migration|迁移|redesign|从零/i;
const L3_KEYWORDS = /线上故障|生产事故|incident|紧急回滚|hotfix|告警|宕机|线上\s*问题/i;
const L0_KEYWORDS = /加字段|改文案|typo|单文件|rename|常量|日志/i;

function readSession() {
  const p = join(dir, 'session.json');
  if (!existsSync(p)) return { requirement: '' };
  try {
    return JSON.parse(readFileSync(p, 'utf8'));
  } catch {
    return { requirement: '' };
  }
}

function inferTaskLevel() {
  const session = readSession();
  if (session.task_level) {
    return { level: session.task_level, rationale: session.task_level_rationale || 'session.json 已设定', source: 'session' };
  }
  const req = String(session.requirement || '');
  let riskTotal = 0;
  const rp = join(dir, 'risk.json');
  if (existsSync(rp)) {
    try {
      const dims = (JSON.parse(readFileSync(rp, 'utf8')).dimensions) || {};
      riskTotal = RISK_DIMS.reduce((s, k) => s + Number(dims[k]?.score || 0), 0);
    } catch { /* ignore */ }
  }
  if (L3_KEYWORDS.test(req)) return { level: 'L3', rationale: '需求文案命中 incident 信号', source: 'heuristic' };
  if (L2_KEYWORDS.test(req) || riskTotal >= 15) return { level: 'L2', rationale: riskTotal >= 15 ? `risk 总分 ${riskTotal}` : '需求文案命中 architecture 信号', source: 'heuristic' };
  if (L0_KEYWORDS.test(req) && riskTotal <= 7) return { level: 'L0', rationale: '简单变更信号 + risk≤7', source: 'heuristic' };
  return { level: 'L1', rationale: '默认 normal_feature', source: 'heuristic' };
}

function route() {
  const inferred = inferTaskLevel();
  const out = {
    task_level: inferred.level,
    rationale: inferred.rationale,
    source: inferred.source,
    flow: {
      skip_review_validate: inferred.level === 'L0',
      require_change_budget: inferred.level === 'L2' || inferred.level === 'L3',
      require_evidence_ledger_timeline: inferred.level === 'L3',
    },
  };
  console.log(JSON.stringify(out, null, 2));
  if (writeFlag) {
    const session = readSession();
    session.task_level = inferred.level;
    session.task_level_rationale = inferred.rationale;
    session.updated_at = new Date().toISOString();
    writeJson('session.json', session);
    console.log('=> 已写入 session.json task_level');
  }
}

function budget() {
  const { level } = inferTaskLevel();
  const defs = TASK_LEVEL_DEFAULTS[level] || TASK_LEVEL_DEFAULTS.L1;
  const pick = (name, parser) => {
    const i = process.argv.indexOf(name);
    return i >= 0 && process.argv[i + 1] !== undefined ? parser(process.argv[i + 1]) : undefined;
  };
  const body = {
    files: pick('--files', (v) => Number(v)) ?? defs.files,
    modules: pick('--modules', (v) => Number(v)) ?? defs.modules,
    database: pick('--database', (v) => v === 'true') ?? defs.database,
    new_service: pick('--new-service', (v) => v === 'true') ?? defs.new_service,
    task_level: level,
    rationale: pick('--rationale', String) ?? `默认预算（${level}）`,
    updated_at: new Date().toISOString(),
  };
  if (writeFlag) {
    writeJson('change-budget.json', body);
    console.log(JSON.stringify(body, null, 2));
    console.log('=> 已写入 change-budget.json');
  } else {
    console.log(JSON.stringify(body, null, 2));
    console.log('=> 预览；确认后加 --write');
  }
}

function ledgerCmd() {
  const sub = process.argv[4];
  const ledgerPath = join(dir, 'evidence-ledger.json');
  let ledger = [];
  if (existsSync(ledgerPath)) {
    try { ledger = isArr(JSON.parse(readFileSync(ledgerPath, 'utf8'))); } catch { ledger = []; }
  }
  if (sub === 'list') {
    console.log(JSON.stringify(ledger, null, 2));
    return;
  }
  if (sub === 'validate') {
    let errors = 0;
    const kinds = ['FACT', 'DECISION', 'TEST', 'RESULT', 'RISK'];
    for (const e of ledger) {
      if (!/^EL-\d{3}$/.test(e.id || '')) { console.log(`${e.id || '?'}: id 须 EL-xxx`); errors++; }
      if (!kinds.includes(e.kind)) { console.log(`${e.id}: kind 无效`); errors++; }
      if (!String(e.claim || '').trim()) { console.log(`${e.id}: claim 为空`); errors++; }
      if (['RESULT', 'TEST'].includes(e.kind) && !(Array.isArray(e.evidence_refs) && e.evidence_refs.length)) {
        console.log(`${e.id}: ${e.kind} 须有 evidence_refs`);
        errors++;
      }
    }
    console.log(errors === 0 ? '=> ledger 校验通过' : `=> ${errors} 个错误`);
    process.exitCode = errors === 0 ? 0 : 1;
    return;
  }
  if (sub === 'append') {
    const claim = process.argv[5];
    if (!claim) { console.error('用法: ledger append "<claim>" [--kind RESULT] [--refs "a,b"] [--link DEC-001]'); process.exit(2); }
    const kindIdx = process.argv.indexOf('--kind');
    const kind = kindIdx >= 0 ? process.argv[kindIdx + 1] : 'RESULT';
    const refsIdx = process.argv.indexOf('--refs');
    const refs = refsIdx >= 0 && process.argv[refsIdx + 1]
      ? process.argv[refsIdx + 1].split(',').map((s) => s.trim()).filter(Boolean)
      : [];
    const linkIdx = process.argv.indexOf('--link');
    const linked = linkIdx >= 0 && process.argv[linkIdx + 1] ? [process.argv[linkIdx + 1]] : [];
    const id = nextId(ledger, 'EL-');
    ledger.push({ id, kind, claim: String(claim), evidence_refs: refs, linked_ids: linked, created_at: new Date().toISOString() });
    writeJson('evidence-ledger.json', ledger);
    console.log(`${id} appended`);
    return;
  }
  console.error('用法: ledger list|validate|append "<claim>" [...]');
  process.exit(2);
}

function impactGraph() {
  const decisions = isArr(read('decisions.json'));
  const graph = decisions.map((d) => ({
    decision_id: d.id,
    decision: d.decision,
    status: d.status,
    superseded_by: d.status === 'SUPERSEDED' ? d.replaced_by || null : null,
    impact: {
      modules: d.impact_scope?.modules || [],
      files: d.impact_scope?.files || [],
      tests: d.impact_scope?.tests || [],
      legacy: Array.isArray(d.impact) ? d.impact : [],
    },
  }));
  if (writeFlag) {
    writeJson('decision-graph.json', graph);
    console.log(JSON.stringify(graph, null, 2));
    console.log('=> 已写入 decision-graph.json');
  } else {
    console.log(JSON.stringify(graph, null, 2));
    console.log('=> 预览；确认后加 --write');
  }
}

function exportContext() {
  const session = readSession();
  const { level } = inferTaskLevel();
  const facts = isArr(read('facts.json')).map((f) => `${f.id}: ${f.statement} (${f.source?.path || ''}${f.source?.line ? `:${f.source.line}` : ''})`);
  const questions = isArr(read('questions.json'));
  const unknowns = questions.filter((q) => q.status === 'OPEN').map((q) => `${q.id}: ${q.question}`);
  const decisions = isArr(read('decisions.json'))
    .filter((d) => d.status === 'FROZEN')
    .map((d) => ({ id: d.id, decision: d.decision, status: d.status }));
  const assumptions = isArr(read('assumptions.json'));
  const risks = assumptions.filter((a) => a.status === 'UNVERIFIED').map((a) => `${a.id} [${a.risk}]: ${a.statement}`);
  const ledger = existsSync(join(dir, 'evidence-ledger.json')) ? isArr(read('evidence-ledger.json')) : [];
  const evidence = ledger.map((e) => ({ claim: e.claim, refs: e.evidence_refs || [] }));
  const constraints = isArr(read('facts.json'))
    .filter((f) => f.category === 'constraint')
    .map((f) => f.statement);
  let change_budget;
  const bp = join(dir, 'change-budget.json');
  if (existsSync(bp)) {
    try { change_budget = JSON.parse(readFileSync(bp, 'utf8')); } catch { /* */ }
  }
  const gatePath = join(dir, 'gate.json');
  let next_action = '继续 RequirementMind 流程';
  if (existsSync(gatePath)) {
    try {
      const g = JSON.parse(readFileSync(gatePath, 'utf8'));
      if (g.status === 'READY_FOR_DEVELOPMENT') next_action = '导出 agent-prompt，进入 /ai-code';
    } catch { /* */ }
  }
  const doc = {
    contract_version: 1,
    session_id: session.id || undefined,
    task_level: session.task_level || level,
    goal: session.requirement || '',
    facts,
    unknowns,
    decisions,
    constraints,
    risks,
    evidence,
    next_action,
    change_budget: change_budget
      ? { files: change_budget.files, modules: change_budget.modules, database: change_budget.database, new_service: change_budget.new_service }
      : undefined,
  };
  console.log(JSON.stringify(doc, null, 2));
}

function evalMetrics() {
  const questions = isArr(read('questions.json'));
  const decisions = isArr(read('decisions.json'));
  const challenges = isArr(read('challenges.json'));
  const evidence = isArr(read('evidence.json'));
  const answered = questions.filter((q) => q.status === 'ANSWERED');
  const userDec = decisions.filter((d) => d.status === 'FROZEN' && d.source === 'USER');
  const aiDec = decisions.filter((d) => d.status === 'FROZEN' && d.source === 'AI_DEFAULT');
  const verdicts = { CONFIRMED: 0, PLAUSIBLE: 0, REFUTED: 0 };
  for (const e of evidence) if (verdicts[e.verdict] !== undefined) verdicts[e.verdict]++;
  for (const ch of challenges)
    if (verdicts[ch.status] !== undefined && !evidence.some((e) => e.challenge_id === ch.id)) verdicts[ch.status]++;
  const reviewed = verdicts.CONFIRMED + verdicts.PLAUSIBLE + verdicts.REFUTED;
  const m = {
    questions_total: questions.length,
    should_ask_by_policy: questions.filter((q) => q.priority !== 'OPTIONAL' && q.authority !== 'TECHNICAL' && q.value !== 'LOW').length,
    answered_total: answered.length,
    user_decisions: userDec.length,
    ai_decisions: aiDec.length,
    autonomy_rate: answered.length ? `${Math.round(((answered.length - userDec.length) / answered.length) * 100)}%` : 'n/a',
    review: {
      ...verdicts,
      refuted_rate: reviewed ? `${Math.round((verdicts.REFUTED / reviewed) * 100)}%` : 'n/a',
    },
    snapshots: existsSync(join(dir, 'history')) ? readdirSync(join(dir, 'history')).length : 0,
  };
  console.log(JSON.stringify(m, null, 2));
}

// ========================================================================
// Requirement IR（V5 P0）：从 canonical JSON 单向生成 7 个 IR 文件
//   ir/requirement.yaml  业务需求（goal + scope + out_of_scope）
//   ir/business-rule.yaml 业务规则（每条带 DEC id）
//   ir/workflow.yaml      业务流程（state machine + 触发器）
//   ir/risk.yaml          风险评分 + 专家路由
//   ir/acceptance.yaml    验收标准（criteria + required tests）
//   ir/decision.json      决策（含 rejected_alternatives / failure_history）
//   ir/trace.json         追溯链（FACT → DEC → SPEC 章节）
// 原则：JSON → IR 单向，禁止反向。R10：每个 IR 文件对"完全不了解对话历史的 Agent"自足。
// ========================================================================
const COUNCIL_FIVE = ['concurrency', 'data_integrity', 'security', 'compatibility', 'testability'];

function yamlEscape(v) {
  if (v === null || v === undefined) return '""';
  const s = String(v);
  if (/[:#\n"'>&*?|%@`{}[\],\n]/.test(s) || /^\s|\s$/.test(s)) {
    return JSON.stringify(s);
  }
  return s;
}

function yamlList(arr, indent = 0) {
  const pad = ' '.repeat(indent);
  return (arr || []).map((x) => `${pad}- ${yamlEscape(x)}`).join('\n');
}

function toYamlRequirement(session, decisions, scope, oos) {
  const title = session.requirement || '';
  return [
    '# Generated by RequirementMind state.mjs ir — DO NOT EDIT',
    `# source_session: ${session.id || '(unnamed)'}`,
    `# generated_at: ${new Date().toISOString()}`,
    'requirement:',
    `  title: ${yamlEscape(title)}`,
    `  task_level: ${yamlEscape(session.task_level || 'L1')}`,
    `  status: ${yamlEscape(session.phase || 'INPUT')}`,
    'scope:',
    yamlList(scope, 2),
    'out_of_scope:',
    yamlList(oos, 2),
  ].join('\n') + '\n';
}

function toYamlBusinessRules(decisions) {
  const frozen = decisions.filter((d) => d.status === 'FROZEN');
  const lines = [
    '# Generated by RequirementMind state.mjs ir — DO NOT EDIT',
    `# generated_at: ${new Date().toISOString()}`,
    `# total_rules: ${frozen.length}`,
    'rules:',
  ];
  for (const d of frozen) {
    lines.push(`  - id: ${d.id}`);
    lines.push(`    topic: ${yamlEscape(d.topic || '')}`);
    lines.push(`    rule: ${yamlEscape(d.decision)}`);
    lines.push(`    source: ${d.source}`);
    lines.push(`    basis: ${yamlEscape(d.basis || `question ${d.question_id}`)}`);
    if (Array.isArray(d.impact) && d.impact.length) lines.push(`    impact:\n${yamlList(d.impact, 6)}`);
    if (Array.isArray(d.rejected_alternatives) && d.rejected_alternatives.length) {
      lines.push(`    rejected_alternatives:`);
      for (const r of d.rejected_alternatives) {
        lines.push(`      - option: ${yamlEscape(r.option || '')}`);
        lines.push(`        reason: ${yamlEscape(r.reason || '')}`);
      }
    }
  }
  return lines.join('\n') + '\n';
}

function toYamlWorkflow(decisions, assumptions) {
  const stateDecs = decisions.filter((d) => d.status === 'FROZEN' && /state|status|状态|workflow|流程|state_machine/i.test(`${d.topic} ${d.decision}`));
  const lines = [
    '# Generated by RequirementMind state.mjs ir — DO NOT EDIT',
    `# generated_at: ${new Date().toISOString()}`,
    'states:',
  ];
  if (!stateDecs.length) {
    lines.push('  - 未识别到状态机相关冻结决策；状态机由 Coding Agent 按业务规则推导');
  }
  for (const d of stateDecs) {
    lines.push(`  - id: ${d.id}`);
    lines.push(`    name: ${yamlEscape(d.topic)}`);
    lines.push(`    trigger: ${yamlEscape(d.decision)}`);
  }
  lines.push('assumptions_about_flow:');
  for (const a of assumptions.filter((x) => x.risk !== 'LOW').slice(0, 10)) {
    lines.push(`  - id: ${a.id}`);
    lines.push(`    statement: ${yamlEscape(a.statement)}`);
    lines.push(`    risk: ${a.risk}`);
  }
  return lines.join('\n') + '\n';
}

function toYamlRisk(risk) {
  const dims = (risk && risk.dimensions) || {};
  const lines = [
    '# Generated by RequirementMind state.mjs ir — DO NOT EDIT',
    `# generated_at: ${new Date().toISOString()}`,
    `# total: ${risk?.total ?? 0}`,
    `# tier: ${risk?.tier ?? 'LIGHT'}`,
    `# specialists: ${(risk?.specialists || []).join(',') || '(none — LIGHT)'}`,
    'dimensions:',
  ];
  for (const k of RISK_DIMS) {
    const d = dims[k] || { score: 0, refs: [] };
    lines.push(`  - key: ${k}`);
    lines.push(`    score: ${d.score}`);
    lines.push(`    refs:`);
    for (const r of (d.refs || [])) lines.push(`      - ${yamlEscape(r)}`);
  }
  return lines.join('\n') + '\n';
}

function toYamlAcceptance(decisions, questions, gate) {
  const lines = [
    '# Generated by RequirementMind state.mjs ir — DO NOT EDIT',
    `# generated_at: ${new Date().toISOString()}`,
    'criteria:',
  ];
  if (gate && gate.status === 'READY_FOR_DEVELOPMENT') {
    lines.push('  - id: GATE-READY');
    lines.push('    rule: 硬门槛（blocking_questions/blocking_conflicts/critical_assumptions/unvalidated_high_risks）= 0');
    lines.push('    source: gate.json');
  } else {
    lines.push('  - id: GATE-BLOCKED');
    lines.push('    rule: 任一硬门槛 > 0；以下为已知未答问题');
  }
  for (const q of questions.filter((x) => x.priority === 'BLOCKING' && x.status === 'OPEN')) {
    lines.push(`  - id: ${q.id}`);
    lines.push(`    rule: ${yamlEscape(q.question)}`);
    lines.push('    source: questions.json');
    lines.push('    status: BLOCKING');
  }
  lines.push('required_tests:');
  lines.push('  - kind: unit');
  lines.push('    target: 冻结规则对应路径（见 ir/decision.json impact_scope）');
  return lines.join('\n') + '\n';
}

function toDecisionJson(decisions) {
  return JSON.stringify(
    {
      contract_version: 1,
      generated_at: new Date().toISOString(),
      total: decisions.length,
      frozen: decisions.filter((d) => d.status === 'FROZEN').map((d) => ({
        id: d.id,
        topic: d.topic,
        decision: d.decision,
        source: d.source,
        basis: d.basis,
        impact: d.impact || [],
        impact_scope: d.impact_scope || null,
        rejected_alternatives: d.rejected_alternatives || [],
        created_at: d.created_at,
      })),
      superseded: decisions
        .filter((d) => d.status === 'SUPERSEDED')
        .map((d) => ({ id: d.id, replaced_by: d.replaced_by })),
    },
    null,
    2,
  ) + '\n';
}

function toTraceJson(facts, decisions) {
  const knownFacts = new Set(facts.map((f) => f.id));
  const trace = [];
  for (const d of decisions.filter((x) => x.status === 'FROZEN')) {
    const basis = d.basis || d.question_id || '';
    const refs = [];
    for (const token of String(basis).split(/[\s,;]+/)) {
      if (knownFacts.has(token)) refs.push(token);
    }
    trace.push({ decision_id: d.id, topic: d.topic, evidence_refs: refs, basis });
  }
  return JSON.stringify({ contract_version: 1, generated_at: new Date().toISOString(), trace }, null, 2) + '\n';
}

function deriveScopeOOS(decisions, assumptions) {
  const scope = [];
  for (const d of decisions.filter((x) => x.status === 'FROZEN').slice(0, 8)) {
    scope.push(`${d.id}: ${d.topic} — ${d.decision}`);
  }
  if (!scope.length) scope.push('未识别到冻结决策；scope 由 Coding Agent 按业务规则推导');
  const oos = [
    '禁止修改 FROZEN 决策的任何字段（decisions.json / 规格 Frozen Business Rules 章节）',
    '禁止新增业务含义或默认值',
    '禁止修改数据库语义、状态含义、权限规则、验收口径',
    'Coding Agent 自定技术细节/局部重构/补测试允许',
  ];
  return { scope, oos };
}

function exportIR() {
  const session = readSession();
  const facts = isArr(read('facts.json'));
  const questions = isArr(read('questions.json'));
  const decisions = isArr(read('decisions.json'));
  const assumptions = isArr(read('assumptions.json'));
  let risk = null;
  const rp = join(dir, 'risk.json');
  if (existsSync(rp)) {
    try { risk = JSON.parse(readFileSync(rp, 'utf8')); } catch { /* */ }
  }
  let gate = null;
  const gp = join(dir, 'gate.json');
  if (existsSync(gp)) {
    try { gate = JSON.parse(readFileSync(gp, 'utf8')); } catch { /* */ }
  }
  const { scope, oos } = deriveScopeOOS(decisions, assumptions);
  const irDir = join(dir, 'ir');
  if (writeFlag && !existsSync(irDir)) mkdirSync(irDir, { recursive: true });
  const files = {
    'requirement.yaml': toYamlRequirement(session, decisions, scope, oos),
    'business-rule.yaml': toYamlBusinessRules(decisions),
    'workflow.yaml': toYamlWorkflow(decisions, assumptions),
    'risk.yaml': toYamlRisk(risk),
    'acceptance.yaml': toYamlAcceptance(decisions, questions, gate),
    'decision.json': toDecisionJson(decisions),
    'trace.json': toTraceJson(facts, decisions),
  };
  if (!writeFlag) {
    console.log(`# IR 预览（${Object.keys(files).length} 文件，--write 写入 ${irDir}）\n`);
    for (const [name, body] of Object.entries(files)) {
      console.log(`--- ${name} ---`);
      console.log(body);
    }
    return;
  }
  for (const [name, body] of Object.entries(files)) {
    writeFileSync(join(irDir, name), body);
    console.log(`写入 ${join('ir', name)} (${Buffer.byteLength(body, 'utf8')}B)`);
  }
  console.log(`\n=> Requirement IR 已生成（7 文件）。下游消费者：Coding Agent / Project-Brain / ContextMind / TestMind`);
}

// ========================================================================
// Gate 状态机（V5 P0）：INPUT → ANALYZING → BLOCKED → READY_FOR_DEVELOPMENT → FROZEN
// 输出当前节点 + 迁移历史；--record --to <NODE> 记录迁移。
// ========================================================================
const GATE_NODES = ['INPUT', 'ANALYZING', 'BLOCKED', 'READY_FOR_DEVELOPMENT', 'FROZEN'];
const GATE_TRANSITIONS = {
  INPUT: ['ANALYZING'],
  ANALYZING: ['BLOCKED', 'READY_FOR_DEVELOPMENT'],
  BLOCKED: ['ANALYZING'],
  READY_FOR_DEVELOPMENT: ['FROZEN', 'BLOCKED'],
  FROZEN: ['BLOCKED'],
};

function gateStateCmd() {
  const session = readSession();
  const idx = process.argv.indexOf('--to');
  const recordTo = idx >= 0 ? process.argv[idx + 1] : null;
  const history = Array.isArray(session.gate_state_history) ? session.gate_state_history : [];
  const current = (() => {
    if (GATE_NODES.includes(session.phase)) return session.phase;
    if (session.phase === 'READY' || session.phase === 'GATED') return 'READY_FOR_DEVELOPMENT';
    if (session.phase === 'GRILLING' || session.phase === 'SCANNED' || session.phase === 'PARSED') return 'ANALYZING';
    return 'INPUT';
  })();
  if (recordTo) {
    if (!GATE_NODES.includes(recordTo)) {
      console.error(`gate-state: --to 必须是 ${GATE_NODES.join('|')}`);
      process.exit(2);
    }
    const allowed = GATE_TRANSITIONS[current] || [];
    if (!allowed.includes(recordTo)) {
      console.error(`gate-state: 非法迁移 ${current} → ${recordTo}（允许: ${allowed.join(',')}）`);
      process.exit(1);
    }
    history.push({ from: current, to: recordTo, at: new Date().toISOString(), reason: process.argv.includes('--reason') ? process.argv[process.argv.indexOf('--reason') + 1] : '' });
    session.gate_state_history = history;
    session.phase = recordTo;
    session.updated_at = new Date().toISOString();
    writeJson('session.json', session);
    console.log(`gate-state: ${current} → ${recordTo}（已记录）`);
    return;
  }
  const out = {
    current,
    allowed_next: GATE_TRANSITIONS[current] || [],
    history,
    counter_snapshot: countersData(),
  };
  console.log(JSON.stringify(out, null, 2));
}

// ========================================================================
// Evidence Engine（V5 P1）：聚合 facts/decisions/challenges/evidence-ledger
//   → 统一四元组（结论/证据/可信度/验证方式）
//   写到 .requirementmind/evidence-pack.json（--write）或 stdout（预览）
// ========================================================================
function evidencePack() {
  const facts = isArr(read('facts.json'));
  const decisions = isArr(read('decisions.json'));
  const challenges = isArr(read('challenges.json'));
  const evidence = isArr(read('evidence.json'));
  const ledger = existsSync(join(dir, 'evidence-ledger.json')) ? isArr(read('evidence-ledger.json')) : [];
  const verdictMap = new Map(evidence.map((e) => [e.challenge_id, e]));
  const items = [];
  for (const f of facts) {
    items.push({
      kind: 'FACT',
      id: f.id,
      conclusion: f.statement,
      evidence: f.source ? [`${f.source.type}:${f.source.path}${f.source.line ? ':' + f.source.line : ''}`] : [],
      confidence: typeof f.confidence === 'number' ? f.confidence : null,
      verification: f.source ? `grep -n "${(f.statement || '').slice(0, 30)}" ${f.source.path}` : null,
    });
  }
  for (const d of decisions.filter((x) => x.status === 'FROZEN')) {
    items.push({
      kind: 'DECISION',
      id: d.id,
      conclusion: d.decision,
      evidence: d.basis ? [d.basis] : (d.question_id ? [d.question_id] : []),
      confidence: d.source === 'AI_DEFAULT' ? 0.6 : 0.9,
      verification: Array.isArray(d.impact) && d.impact.length ? `trace impact → ${d.impact.join(', ')}` : null,
      source: d.source,
    });
  }
  for (const c of challenges) {
    const ev = verdictMap.get(c.id);
    items.push({
      kind: 'CHALLENGE',
      id: c.id,
      conclusion: c.claim,
      evidence: c.evidence || [],
      confidence: ev && typeof ev.confidence === 'number' ? ev.confidence : null,
      verification: c.validation || null,
      status: ev ? ev.verdict : c.status,
      severity: c.severity,
    });
  }
  for (const e of ledger) {
    items.push({
      kind: 'LEDGER',
      id: e.id,
      conclusion: e.claim,
      evidence: e.evidence_refs || [],
      confidence: null,
      verification: null,
      kind_sub: e.kind,
    });
  }
  const summary = {
    total: items.length,
    by_kind: items.reduce((acc, it) => {
      acc[it.kind] = (acc[it.kind] || 0) + 1;
      return acc;
    }, {}),
    by_status: items.reduce((acc, it) => {
      const k = it.status || (it.kind === 'FACT' ? 'VERIFIED' : it.kind === 'DECISION' ? 'FROZEN' : 'PENDING');
      acc[k] = (acc[k] || 0) + 1;
      return acc;
    }, {}),
  };
  const out = { contract_version: 1, generated_at: new Date().toISOString(), summary, items };
  if (writeFlag) {
    writeJson('evidence-pack.json', out);
    console.log(JSON.stringify({ written: 'evidence-pack.json', ...summary }, null, 2));
  } else {
    console.log(JSON.stringify(out, null, 2));
  }
}

// ========================================================================
// Decision Memory（V5 P1）：聚合 decisions + history/ → decision-memory.json
//   包含 rejected_alternatives（来自当前 decision.rejected_alternatives）
//   + failure_history（来自 history/ 各快照中 status=SUPERSEDED 的决策原因）
// ========================================================================
function decisionMemory() {
  const decisions = isArr(read('decisions.json'));
  const historyDir = join(dir, 'history');
  const failureHistory = [];
  if (existsSync(historyDir)) {
    for (const snapName of readdirSync(historyDir).sort()) {
      try {
        const snap = JSON.parse(readFileSync(join(historyDir, snapName), 'utf8'));
        // snapshot 文件结构：{ "session.json": {...}, "decisions.json": [...], ... }
        const snapDecisions = Array.isArray(snap) ? snap : (snap['decisions.json'] || snap.decisions || []);
        for (const d of snapDecisions) {
          if (d.status === 'SUPERSEDED' && d.replaced_by) {
            failureHistory.push({
              at: snapName,
              decision_id: d.id,
              summary: `${d.topic}: ${d.decision} → 被 ${d.replaced_by} supersede`,
              evidence_refs: d.basis ? [d.basis] : (d.question_id ? [d.question_id] : []),
            });
          }
        }
      } catch { /* skip corrupt snapshot */ }
    }
  }
  const memory = {
    contract_version: 1,
    generated_at: new Date().toISOString(),
    total_decisions: decisions.length,
    frozen: decisions
      .filter((d) => d.status === 'FROZEN')
      .map((d) => ({
        id: d.id,
        topic: d.topic,
        decision: d.decision,
        source: d.source,
        basis: d.basis,
        rejected_alternatives: d.rejected_alternatives || [],
        created_at: d.created_at,
      })),
    failure_history: failureHistory,
    superseded_count: decisions.filter((d) => d.status === 'SUPERSEDED').length,
  };
  if (writeFlag) {
    writeJson('decision-memory.json', memory);
    console.log(JSON.stringify({ written: 'decision-memory.json', total: memory.total_decisions, failure_history: failureHistory.length }, null, 2));
  } else {
    console.log(JSON.stringify(memory, null, 2));
  }
}

({
  counters,
  frontier,
  freeze,
  risk,
  stop,
  eval: evalMetrics,
  validate,
  gate,
  snapshot,
  migrate: migrateQuestions,
  route,
  budget,
  ledger: ledgerCmd,
  'impact-graph': impactGraph,
  context: exportContext,
  ir: exportIR,
  'gate-state': gateStateCmd,
  'evidence-pack': evidencePack,
  'decision-memory': decisionMemory,
})[cmd]();
