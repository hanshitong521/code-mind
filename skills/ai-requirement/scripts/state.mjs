#!/usr/bin/env node
// RequirementMind 状态辅助脚本（确定性部分，不含任何 LLM 逻辑）
// 用法: node state.mjs <counters|validate|gate|snapshot> <.requirementmind 目录>

import { readFileSync, writeFileSync, existsSync, mkdirSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const cmd = process.argv[2];
const dir = process.argv[3];
if (!dir || !['counters', 'validate', 'gate', 'snapshot'].includes(cmd)) {
  console.error('用法: node state.mjs <counters|validate|gate|snapshot> <.requirementmind 目录>');
  process.exit(2);
}
const read = (f) => {
  const p = join(dir, f);
  if (!existsSync(p)) return [];
  const raw = readFileSync(p, 'utf8').trim();
  return raw ? JSON.parse(raw) : [];
};
const isArr = (v) => (Array.isArray(v) ? v : v ? [v] : []);

function counters() {
  const questions = isArr(read('questions.json'));
  const conflicts = isArr(read('conflicts.json'));
  const assumptions = isArr(read('assumptions.json'));
  const challenges = isArr(read('challenges.json'));
  const c = {
    blocking_questions: questions.filter((q) => q.priority === 'BLOCKING' && q.status === 'OPEN').length,
    blocking_conflicts: conflicts.filter((x) => x.severity === 'BLOCKING' && x.status === 'OPEN').length,
    critical_assumptions: assumptions.filter((a) => a.risk === 'HIGH' && a.status === 'UNVERIFIED').length,
    unvalidated_high_risks: challenges.filter((x) => x.status === 'PENDING_VALIDATION' && x.severity === 'BLOCKING').length,
  };
  for (const [k, v] of Object.entries(c)) console.log(`${k}: ${v}`);
  console.log(c.blocking_questions + c.blocking_conflicts + c.critical_assumptions + c.unvalidated_high_risks === 0
    ? '=> 关键疑问已清零 (R9 出口)' : '=> 仍有 BLOCKING 项，禁止进入下一阶段');
}

const ENUMS = {
  'facts.json': { category: ['stack', 'structure', 'database', 'api', 'test', 'business_rule', 'history', 'constraint', 'doc'], status: ['VERIFIED'] },
  'questions.json': { priority: ['BLOCKING', 'IMPORTANT', 'OPTIONAL'], status: ['OPEN', 'ANSWERED'] },
  'decisions.json': { source: ['USER'], status: ['FROZEN', 'SUPERSEDED'] },
  'assumptions.json': { risk: ['HIGH', 'MEDIUM', 'LOW'], source: ['MODEL_INFERENCE'], status: ['UNVERIFIED', 'CONFIRMED_AS_FACT', 'RESOLVED'] },
  'conflicts.json': { severity: ['BLOCKING', 'IMPORTANT'], status: ['OPEN', 'RESOLVED'] },
  'challenges.json': { severity: ['BLOCKING', 'HIGH', 'MEDIUM'], status: ['PENDING_VALIDATION', 'CONFIRMED', 'PLAUSIBLE', 'REFUTED'] },
  'evidence.json': { verdict: ['CONFIRMED', 'PLAUSIBLE', 'REFUTED'] },
};
const REQUIRED = {
  'facts.json': ['id', 'category', 'statement', 'source', 'confidence', 'status'],
  'questions.json': ['id', 'topic', 'question', 'reason', 'priority', 'options', 'status'],
  'decisions.json': ['id', 'question_id', 'decision', 'topic', 'source', 'status', 'created_at'],
  'assumptions.json': ['id', 'statement', 'risk', 'source', 'status'],
  'conflicts.json': ['id', 'left', 'right', 'severity', 'status'],
  'challenges.json': ['id', 'claim', 'challenge', 'evidence', 'counterexample', 'validation', 'severity', 'status'],
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
  const hard = {};
  const q = isArr(read('questions.json')), c = isArr(read('conflicts.json')), a = isArr(read('assumptions.json')), ch = isArr(read('challenges.json'));
  hard.blocking_questions = q.filter((x) => x.priority === 'BLOCKING' && x.status === 'OPEN').length;
  hard.blocking_conflicts = c.filter((x) => x.severity === 'BLOCKING' && x.status === 'OPEN').length;
  hard.critical_assumptions = a.filter((x) => x.risk === 'HIGH' && x.status === 'UNVERIFIED').length;
  hard.unvalidated_high_risks = ch.filter((x) => x.status === 'PENDING_VALIDATION' && x.severity === 'BLOCKING').length;
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
  const files = ['session.json', 'facts.json', 'questions.json', 'decisions.json', 'assumptions.json', 'conflicts.json', 'challenges.json', 'evidence.json', 'gate.json'];
  const snap = {};
  for (const f of files) { const p = join(dir, f); if (existsSync(p)) snap[f] = JSON.parse(readFileSync(p, 'utf8')); }
  writeFileSync(join(hDir, `${String(n).padStart(3, '0')}-${stamp}.json`), JSON.stringify(snap, null, 2));
  console.log(`快照已写入 history/${String(n).padStart(3, '0')}-${stamp}.json`);
}

({ counters, validate, gate, snapshot })[cmd]();
