#!/usr/bin/env node
/** 实测 Peak v2：Complexity Router / Budget / Ledger / Context 体积与路由 */
import { execFileSync } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const stateMjs = join(here, 'state.mjs');
const fixtureDir = join(here, 'fixtures', 'mock-session');

const run = (args) => {
  try {
    return { code: 0, out: execFileSync(process.execPath, [stateMjs, ...args], { encoding: 'utf8' }) };
  } catch (e) {
    return { code: e.status ?? 1, out: `${e.stdout || ''}${e.stderr || ''}` };
  }
};

const lines = [];
const log = (s) => lines.push(s);

function sessionDir(requirement, extra = {}, zeroRisk = false) {
  const tmp = mkdtempSync(join(tmpdir(), 'rm-demo-'));
  const dir = join(tmp, '.requirementmind');
  mkdirSync(dir, { recursive: true });
  for (const f of readdirSync(fixtureDir)) cpSync(join(fixtureDir, f), join(dir, f));
  const session = JSON.parse(readFileSync(join(dir, 'session.json'), 'utf8'));
  session.requirement = requirement;
  Object.assign(session, extra);
  writeFileSync(join(dir, 'session.json'), JSON.stringify(session, null, 2));
  if (zeroRisk) {
    const dims = {};
    for (const k of ['business_criticality', 'data_impact', 'concurrency_risk', 'security_risk', 'compatibility_risk', 'irreversibility', 'blast_radius', 'evidence_gap']) {
      dims[k] = { score: 0, refs: ['FACT-001'] };
    }
    writeFileSync(join(dir, 'risk.json'), JSON.stringify({ dimensions: dims }, null, 2));
  }
  return { tmp, dir };
}

log('# Peak v2 实测报告\n');
log(`时间: ${new Date().toISOString()}\n`);

log('## 1. Complexity Router（三条需求文案）\n');
for (const [label, req] of [
  ['L0 信号', '给订单表加字段 status，单文件改常量'],
  ['L1 默认', '给红包增加限时领取（expire_at 到达后不可领取）'],
  ['L2 信号', '设计 Agent 平台架构，新服务 + 数据迁移'],
]) {
  const { tmp, dir } = sessionDir(req, {}, label.startsWith('L0'));
  const r = run(['route', dir]);
  const m = r.out.match(/"task_level": "(L\d)"/);
  log(`- **${label}**: \`${req.slice(0, 40)}…\` → **${m?.[1] ?? '?'}**`);
  rmSync(tmp, { recursive: true, force: true });
}

const nexDir = 'e:\\workA\\A-skill\\NexMind\\.requirementmind';
if (existsSync(nexDir)) {
  log('\n## 2. 真实消费者 NexMind\n');
  const rt = run(['route', nexDir]);
  const bg = run(['budget', nexDir, '--write']);
  const ig = run(['impact-graph', nexDir, '--write']);
  const cx = run(['context', nexDir]);
  const ctxBytes = Buffer.byteLength(cx.out, 'utf8');
  const g = run(['gate', nexDir]);
  log(`- route: ${(rt.out.match(/"task_level": "[^"]+"/) || [''])[0]}`);
  log(`- budget --write: exit ${bg.code}`);
  log(`- impact-graph: exit ${ig.code}`);
  log(`- context JSON: **${ctxBytes}** bytes（HANDOFF 输入体量参考）`);
  log(`- gate: ${g.out.includes('READY_FOR_DEVELOPMENT') ? 'READY' : '非 READY 或缺项'}`);
}

log('\n## 3. Evidence Ledger 守门\n');
const { tmp: t2a, dir: d2a } = sessionDir('ledger bad', {}, true);
run(['ledger', d2a, 'append', '性能提升50%', '--kind', 'RESULT']);
const badV = run(['ledger', d2a, 'validate']);
rmSync(t2a, { recursive: true, force: true });
const { tmp: t2b, dir: d2b } = sessionDir('ledger ok', {}, true);
run(['ledger', d2b, 'append', 'P99<200ms', '--kind', 'RESULT', '--refs', 'FACT-001,reports/latency.md']);
const okV = run(['ledger', d2b, 'validate']);
rmSync(t2b, { recursive: true, force: true });
log(`- validate 无 refs 的 RESULT: exit **${badV.code}**（应为 1）`);
log(`- validate 有 refs 的 RESULT: exit **${okV.code}**（应为 0）`);

log('\n## 4. 已安装 skill 自检\n');
const installed = join(here, '..', '..', '.cursor', 'skills', 'requirement-mind', 'scripts', 'state.mjs');
const alt = 'e:\\workA\\A-skill\\.cursor\\skills\\requirement-mind\\scripts\\state.mjs';
const skillState = existsSync(alt) ? alt : installed;
if (existsSync(skillState)) {
  const v = execFileSync(process.execPath, [join(dirname(skillState), 'selftest.mjs')], { encoding: 'utf8', cwd: dirname(skillState) });
  const m = v.match(/(\d+) 通过 \/ (\d+) 失败/);
  log(`- \`.cursor/skills/requirement-mind\` selftest: **${m ? m[0] : '已执行'}**`);
} else {
  log('- 未找到 install 副本，跳过');
}

log('\n---\n');
process.stdout.write(lines.join('\n'));
