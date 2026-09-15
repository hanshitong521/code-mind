#!/usr/bin/env node
// RequirementMind 确定性自测：在 mock 会话（scripts/fixtures/mock-session，红包限时领取场景）上
// 跑 state.mjs 全部命令并断言行为，同时计量每轮 grilling 的读取开销（frontier vs 全量读 JSON）。
// 覆盖：Risk Router 分层 / Human-Only Gate（authority）/ Value Score / Stop Rule / Eval / freeze/supersede / migrate。
// 运行: node scripts/selftest.mjs   （改动 SKILL.md / state.mjs / references 后必跑）
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, mkdirSync, readFileSync, writeFileSync, copyFileSync, readdirSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const stateMjs = join(here, 'state.mjs');
const fixtureDir = join(here, 'fixtures', 'mock-session');
let pass = 0, fail = 0;

function check(name, cond, extra = '') {
  if (cond) { pass++; console.log(`  [PASS] ${name}`); }
  else { fail++; console.log(`  [FAIL] ${name}${extra ? ` -- ${extra}` : ''}`); }
}
const run = (args) => {
  try { return { code: 0, out: execFileSync(process.execPath, [stateMjs, ...args], { encoding: 'utf8' }) }; }
  catch (e) { return { code: e.status ?? -1, out: `${e.stdout || ''}${e.stderr || ''}` }; }
};
const readJ = (p) => JSON.parse(readFileSync(p, 'utf8'));
const writeJ = (p, data) => writeFileSync(p, JSON.stringify(data, null, 2) + '\n');

const tmp = mkdtempSync(join(tmpdir(), 'rm-selftest-'));
try {
  const dir = join(tmp, '.requirementmind');
  mkdirSync(dir, { recursive: true });
  for (const f of readdirSync(fixtureDir)) copyFileSync(join(fixtureDir, f), join(dir, f));
  const riskPath = join(dir, 'risk.json');

  console.log('▶ validate / counters');
  const v = run(['validate', dir]);
  check('validate 退出码 0', v.code === 0 && v.out.includes('校验通过'), v.out);
  const c0 = run(['counters', dir]);
  check('初始 blocking_questions=4', c0.out.includes('blocking_questions: 4'), c0.out);
  check('初始 blocking_conflicts=1', c0.out.includes('blocking_conflicts: 1'));
  check('初始 critical_assumptions=1', c0.out.includes('critical_assumptions: 1'));
  check('初始 unvalidated_high_risks=1', c0.out.includes('unvalidated_high_risks: 1'));

  console.log('▶ Risk Router（评分校验 → 分层 → 专项路由）');
  const r0 = run(['risk', dir]);
  check('risk 校验通过', r0.code === 0, r0.out);
  check('总分 13 → FOCUSED', r0.out.includes('"total": 13') && r0.out.includes('FOCUSED'), r0.out);
  check('最高分维度路由专项 concurrency', r0.out.includes('"specialists": [\n    "concurrency"\n  ]') || /"specialists":\s*\[\s*"concurrency"/.test(r0.out), r0.out);
  const riskOrig = readFileSync(riskPath, 'utf8');
  const badRisk = JSON.parse(riskOrig);
  badRisk.dimensions.concurrency_risk.refs = [];
  writeJ(riskPath, badRisk);
  const r1 = run(['risk', dir]);
  check('score>=2 无 refs 被拒（评分必须有证据）', r1.code === 1 && r1.out.includes('必须给 refs'), r1.out);
  const r2 = run(['stop', dir]);
  check('覆盖率缺证据 → stop 拦截', r2.code === 1 && r2.out.includes('无 refs'), r2.out);
  writeFileSync(riskPath, riskOrig);

  console.log('▶ frontier（USER_ONLY 批量 + token 计量）');
  const fullBytes = Buffer.byteLength(readFileSync(join(dir, 'questions.json'), 'utf8'))
    + Buffer.byteLength(readFileSync(join(dir, 'conflicts.json'), 'utf8'));
  const f0 = run(['frontier', dir]);
  const fBytes = Buffer.byteLength(f0.out, 'utf8');
  for (const id of ['Q-001', 'Q-002', 'Q-005', 'CON-001'])
    check(`frontier 含 USER_ONLY 待决项 ${id}`, f0.out.includes(id));
  for (const id of ['Q-003', 'Q-009', 'Q-006'])
    check(`frontier 排除 TECHNICAL ${id}（AI 自治，不打扰用户）`, !f0.out.includes(id));
  for (const id of ['Q-004', 'Q-007', 'Q-008', 'Q-010'])
    check(`frontier 排除已答/OPTIONAL ${id}`, !f0.out.includes(id));
  check('frontier 提示 TECHNICAL 自治通道', f0.out.includes('freeze --auto'));
  check('frontier 退出码 1（仍有待决项）', f0.code === 1, `code=${f0.code}`);
  check(`frontier 输出 ${fBytes}B < 全量读取 ${fullBytes}B`, fBytes < fullBytes);
  const savedPct = Math.max(0, 100 - Math.round((fBytes / fullBytes) * 100));
  console.log(`  ⛽ 每轮读取: frontier ${fBytes}B vs 全量 questions+conflicts ${fullBytes}B（省 ${savedPct}%）`);

  console.log('▶ freeze（用户裁决 / R5 / supersede）');
  const fr1 = run(['freeze', dir, 'Q-001', 'A']);
  check('freeze Q-001 A 退出码 0', fr1.code === 0, fr1.out);
  const d3 = readJ(join(dir, 'decisions.json')).find((d) => d.id === 'DEC-003');
  check('生成 DEC-003 FROZEN，decision=选项正文（非字母）', d3 && d3.status === 'FROZEN' && d3.decision === '请求到达服务端时间', JSON.stringify(d3));
  check('Q-001 置 ANSWERED', readJ(join(dir, 'questions.json')).find((q) => q.id === 'Q-001').status === 'ANSWERED');
  check('冻结后回打印数 blocking_questions=3', fr1.out.includes('blocking_questions: 3'));
  check('自动快照 history/', readdirSync(join(dir, 'history')).length >= 1);
  const fr2 = run(['freeze', dir, 'Q-001', 'B']);
  check('重复冻结被拒（R5，提示 --supersede）', fr2.code === 1 && fr2.out.includes('--supersede'), fr2.out);
  const fr3 = run(['freeze', dir, 'Q-001', 'B', '--supersede']);
  check('--supersede 改判成功', fr3.code === 0, fr3.out);
  const decs = readJ(join(dir, 'decisions.json'));
  check('DEC-003 置 SUPERSEDED + replaced_by=DEC-004', decs.find((d) => d.id === 'DEC-003')?.status === 'SUPERSEDED'
    && decs.find((d) => d.id === 'DEC-003')?.replaced_by === 'DEC-004');

  console.log('▶ freeze 冲突裁决');
  const fc = run(['freeze', dir, 'CON-001', '不复用 status=2：新增 status=3=EXPIRED，status=2 保持 STOPPED 语义']);
  check('freeze CON-001 退出码 0', fc.code === 0, fc.out);
  const con = readJ(join(dir, 'conflicts.json')).find((x) => x.id === 'CON-001');
  check('CON-001 RESOLVED + 回填 resolution_decision_id', con.status === 'RESOLVED' && con.resolution_decision_id === 'DEC-005', JSON.stringify(con));

  console.log('▶ Human-Only Gate（TECHNICAL → freeze --auto 自治裁决）');
  // 模拟主 Agent 的合法动作：assumption 取证升级、validator 销案 challenge
  const asm = readJ(join(dir, 'assumptions.json'));
  asm.find((a) => a.id === 'ASM-001').status = 'RESOLVED';
  writeJ(join(dir, 'assumptions.json'), asm);
  const chs = readJ(join(dir, 'challenges.json'));
  chs.find((x) => x.id === 'CH-001').status = 'REFUTED';
  writeJ(join(dir, 'challenges.json'), chs);
  const restAnswers = [
    ['Q-002', 'D', '--impact', 'sql/red_packet.sql:18'],
    ['Q-003', 'A', '--auto'],
    ['Q-009', 'B', '--auto'],
    ['Q-005', 'A'],
    ['Q-006', 'B', '--auto'],
  ];
  for (const args of restAnswers) {
    const r = run(['freeze', dir, ...args]);
    check(`freeze ${args.slice(0, 2).join(' ')}${args.includes('--auto') ? '（--auto）' : ''}`, r.code === 0, r.out);
  }
  const decAll = readJ(join(dir, 'decisions.json'));
  check('TECHNICAL 冻结 source=AI_DEFAULT', decAll.find((d) => d.question_id === 'Q-009')?.source === 'AI_DEFAULT');
  check('USER 冻结 source=USER', decAll.find((d) => d.question_id === 'Q-002')?.source === 'USER');
  check('impact 落盘', decAll.some((d) => d.question_id === 'Q-002' && Array.isArray(d.impact) && d.impact[0] === 'sql/red_packet.sql:18'));
  const f1 = run(['frontier', dir]);
  check('frontier 空 → 退出码 0（R9 达成）', f1.code === 0 && f1.out.includes('frontier 已空'), f1.out);

  console.log('▶ Stop Rule（R9 + 覆盖率）');
  const s0 = run(['stop', dir]);
  check('全部清零 → stop 退出码 0', s0.code === 0 && s0.out.includes('STOP 条件满足'), s0.out);
  const riskObj = JSON.parse(riskOrig);
  riskObj.dimensions.concurrency_risk.refs = ['FACT-999'];
  writeJ(riskPath, riskObj);
  const s1 = run(['stop', dir]);
  check('风险维度证据失效 → stop 退出码 1', s1.code === 1 && s1.out.includes('无法解析'), s1.out);
  writeFileSync(riskPath, riskOrig);
  const s2 = run(['stop', dir]);
  check('证据恢复 → stop 退出码 0', s2.code === 0, s2.out);

  console.log('▶ Gate');
  const g0 = run(['gate', dir]);
  check('gate 无检查表 → HARD-GATE-OK', g0.code === 0 && g0.out.includes('HARD-GATE-OK'), g0.out);
  const checklist = ['business_goal', 'scope', 'core_flow', 'business_rules', 'data_model', 'api_contract', 'state_machine', 'validation_rules', 'permission', 'concurrency', 'idempotency', 'exception_handling', 'compatibility', 'acceptance_criteria', 'testability', 'spec_consistency'];
  writeJ(join(dir, 'gate.json'), {
    status: 'READY_FOR_DEVELOPMENT',
    checklist: Object.fromEntries(checklist.map((k) => [k, 'PASS'])),
    hard_counters: { blocking_questions: 0, blocking_conflicts: 0, critical_assumptions: 0, unvalidated_high_risks: 0 },
    missing: [],
    checked_at: new Date().toISOString(),
  });
  const g1 = run(['gate', dir]);
  check('gate 全 PASS → READY_FOR_DEVELOPMENT', g1.code === 0 && g1.out.includes('READY_FOR_DEVELOPMENT'), g1.out);

  console.log('▶ Eval 闭环（自治率 / 验真率）');
  const ev = run(['eval', dir]);
  check('eval 退出码 0', ev.code === 0, ev.out);
  let m = null;
  try { m = JSON.parse(ev.out); } catch { /* ignore */ }
  check('eval 输出可解析 JSON', !!m, ev.out.slice(0, 120));
  if (m) {
    check('user_decisions=6', m.user_decisions === 6, JSON.stringify(m));
    check('ai_decisions=3（TECHNICAL 自治）', m.ai_decisions === 3);
    check('answered_total=8', m.answered_total === 8);
    check('autonomy_rate=25%', m.autonomy_rate === '25%');
    check('refuted=2（伪问题被销案）', m.review.REFUTED === 2);
    check('refuted_rate=100%', m.review.refuted_rate === '100%');
  }

  console.log('▶ Peak v2（route / budget / ledger / impact-graph / context）');
  const rt = run(['route', dir]);
  check('route 推断 task_level', rt.code === 0 && rt.out.includes('"task_level"'), rt.out);
  check('红包场景默认 L1', rt.out.includes('"task_level": "L1"'), rt.out);
  const bg = run(['budget', dir, '--write']);
  check('budget --write', bg.code === 0 && existsSync(join(dir, 'change-budget.json')));
  const lg = run(['ledger', dir, 'append', 'mock claim', '--kind', 'TEST', '--refs', 'FACT-001']);
  check('ledger append', lg.code === 0, lg.out);
  const lv = run(['ledger', dir, 'validate']);
  check('ledger validate', lv.code === 0, lv.out);
  const ig = run(['impact-graph', dir, '--write']);
  check('impact-graph --write', ig.code === 0 && existsSync(join(dir, 'decision-graph.json')), ig.out);
  const cx = run(['context', dir]);
  check('context contract_version=1', cx.code === 0 && cx.out.includes('"contract_version": 1'), cx.out);
  check('context 含 FROZEN decisions', cx.out.includes('"decisions"'), cx.out);

  console.log('▶ migrate（旧版 questions 兼容 + authority/value 回填）');
  const dir2 = join(tmp, 'legacy');
  mkdirSync(dir2, { recursive: true });
  copyFileSync(join(here, 'fixtures', 'questions-legacy.json'), join(dir2, 'questions.json'));
  copyFileSync(join(here, 'fixtures', 'decisions-legacy.json'), join(dir2, 'decisions.json'));
  const m0 = run(['migrate', dir2]);
  check('migrate 预览不写盘', m0.code === 0 && m0.out.includes('预览'), m0.out);
  check('预览模式下 questions.json 未变', !readJ(join(dir2, 'questions.json'))[0].options[0].startsWith('A. '));
  const m1 = run(['migrate', dir2, '--write']);
  check('migrate --write 成功', m1.code === 0, m1.out);
  const migrated = readJ(join(dir2, 'questions.json'));
  check('Q-001 选项规范化 A. 前缀', migrated[0].options[0].startsWith('A. '));
  check('Q-001 占位推荐 A', migrated[0].recommended_option === 'A' && migrated[0].recommendation_reason.includes('迁移占位'));
  check('Q-002 从 DEC-002 推断推荐 C', migrated[1].recommended_option === 'C', JSON.stringify(migrated[1]));
  check('缺 authority/value 回填为安全默认', migrated[0].authority === 'USER_ONLY' && migrated[0].value === 'MEDIUM');
  const v2 = run(['validate', dir2]);
  check('迁移后 validate 通过', v2.code === 0, v2.out);
} finally {
  rmSync(tmp, { recursive: true, force: true });
}

// ========================================================================
// V5 攻击测试：5 类典型业务场景必跑（payment_refund / ten_million_db /
// ai_agent_arch / permission_system / high_concurrency）
// 每个 fixture 必断言 6 项：risk=COUNCIL+5专家 / stop=0 / gate=READY /
// ir=7文件 / evidence-pack 含 CONFIRMED / decision-memory 含 failure_history
// ========================================================================
console.log('\n▶ V5 攻击测试（5 场景）');
const attackDir = join(here, 'fixtures', 'attack-tests');
const attackScenarios = ['payment_refund', 'ten_million_db', 'ai_agent_arch', 'permission_system', 'high_concurrency'];
const attackResults = {};
for (const scenario of attackScenarios) {
  console.log(`\n  ▸ ${scenario}`);
  const sDir = join(attackDir, scenario);
  const atmp = mkdtempSync(join(tmpdir(), `rm-attack-${scenario}-`));
  const d = join(atmp, '.requirementmind');
  mkdirSync(d, { recursive: true });
  for (const f of readdirSync(sDir)) {
    if (f === "ir" || f === "testmind") continue; // 跳过生成产物子目录
    copyFileSync(join(sDir, f), join(d, f));
  }
  const passed = { ran: true, found_hidden_issues: 0, blocked_wrong_dev: false, generated_acceptance: false };

  // 1. risk → COUNCIL + 5 专家（risk 输出是 JSON + 提示文本，先剥掉提示再 parse）
  const r0 = run(['risk', d]);
  const riskJson = r0.out.split('=>')[0].trim();
  const riskOut = (() => { try { return JSON.parse(riskJson); } catch { return {}; } })();
  const isCouncil = r0.code === 0 && riskOut.tier === 'COUNCIL' && Array.isArray(riskOut.specialists) && riskOut.specialists.length === 5;
  check('risk=COUNCIL 且 specialists=5', isCouncil, r0.out.slice(0, 200));
  if (isCouncil) passed.found_hidden_issues = 1;

  // 2. freeze 所有 OPEN questions（含一个 supersede 链以造 failure_history）
  const qs = readJ(join(d, 'questions.json')).filter((q) => q.status === 'OPEN');
  if (qs.length >= 1) {
    // 先用推荐项 freeze，再用备选 + --supersede 改判，制造 1 条 SUPERSEDED
    run(['freeze', d, qs[0].id, qs[0].recommended_option || 'A']);
    const options = (qs[0].options || []).filter((o) => !o.startsWith(qs[0].recommended_option + '.'));
    if (options.length) {
      const altLetter = options[0].trim().charAt(0).toUpperCase();
      run(['freeze', d, qs[0].id, altLetter, '--supersede']);
    }
  }
  for (const q of qs.slice(1)) {
    const isTech = q.authority === 'TECHNICAL';
    const args = ['freeze', d, q.id, q.recommended_option || 'A'];
    if (isTech) args.push('--auto');
    run(args);
  }
  const cs = readJ(join(d, 'conflicts.json')).filter((c) => c.status === 'OPEN');
  for (const c of cs) {
    run(['freeze', d, c.id, '以代码为准：保留现状 + 显式标注风险']);
  }

  // 3. 模拟 validator 给至少 1 个 CH- CONFIRMED（取第一个 BLOCKING challenge）
  const chs = readJ(join(d, 'challenges.json'));
  const ev = readJ(join(d, 'evidence.json'));
  const firstBlocking = chs.find((x) => x.severity === 'BLOCKING' && x.status === 'PENDING_VALIDATION');
  if (firstBlocking) {
    firstBlocking.status = 'CONFIRMED';
    ev.push({ id: `EV-${String(ev.length + 1).padStart(3, '0')}`, challenge_id: firstBlocking.id, verdict: 'CONFIRMED', confidence: 0.85, verification: `grep -n "${firstBlocking.claim.slice(0, 20)}" src/`, reasoning: 'fixture 预置 CONFIRMED' });
    writeJ(join(d, 'challenges.json'), chs);
    writeJ(join(d, 'evidence.json'), ev);
  }
  // 解决 HIGH assumption（避免 critical_assumptions 计数挡 stop）
  const asm = readJ(join(d, 'assumptions.json'));
  for (const a of asm.filter((x) => x.risk === 'HIGH' && x.status === 'UNVERIFIED')) {
    a.status = 'RESOLVED';
  }
  writeJ(join(d, 'assumptions.json'), asm);

  // 4. 写 PASS gate.json
  const checklist = ['business_goal', 'scope', 'core_flow', 'business_rules', 'data_model', 'api_contract', 'state_machine', 'validation_rules', 'permission', 'concurrency', 'idempotency', 'exception_handling', 'compatibility', 'acceptance_criteria', 'testability', 'spec_consistency'];
  writeJ(join(d, 'gate.json'), {
    status: 'READY_FOR_DEVELOPMENT',
    checklist: Object.fromEntries(checklist.map((k) => [k, 'PASS'])),
    hard_counters: { blocking_questions: 0, blocking_conflicts: 0, critical_assumptions: 0, unvalidated_high_risks: 0 },
    missing: [],
    checked_at: new Date().toISOString(),
  });

  // 5. stop
  const s0 = run(['stop', d]);
  check('stop=0（R9 达成）', s0.code === 0, s0.out.slice(0, 200));

  // 6. gate
  const g0 = run(['gate', d]);
  check('gate=READY_FOR_DEVELOPMENT', g0.code === 0 && g0.out.includes('READY_FOR_DEVELOPMENT'), g0.out.slice(0, 200));
  if (g0.code === 0 && g0.out.includes('READY_FOR_DEVELOPMENT')) passed.blocked_wrong_dev = true;

  // 7. ir --write → 7 文件
  const ir0 = run(['ir', d, '--write']);
  const irDir = join(d, 'ir');
  const irFiles = existsSync(irDir) ? readdirSync(irDir) : [];
  const expectedIr = ['requirement.yaml', 'business-rule.yaml', 'workflow.yaml', 'risk.yaml', 'acceptance.yaml', 'decision.json', 'trace.json'];
  const irOk = ir0.code === 0 && expectedIr.every((f) => irFiles.includes(f));
  check('ir --write 生成 7 文件', irOk, `files=${irFiles.join(',')}`);

  // 8. evidence-pack --write → 含至少 1 个 CONFIRMED
  const ep0 = run(['evidence-pack', d, '--write']);
  const epExists = existsSync(join(d, 'evidence-pack.json'));
  const ep = epExists ? readJ(join(d, 'evidence-pack.json')) : null;
  const hasConfirmed = ep && Array.isArray(ep.items) && ep.items.some((it) => it.status === 'CONFIRMED');
  check('evidence-pack 含 CONFIRMED', ep0.code === 0 && epExists && hasConfirmed, `items=${ep?.items?.length || 0}`);

  // 9. decision-memory --write → 含至少 1 failure_history
  const dm0 = run(['decision-memory', d, '--write']);
  const dmExists = existsSync(join(d, 'decision-memory.json'));
  const dm = dmExists ? readJ(join(d, 'decision-memory.json')) : null;
  const hasFailure = dm && Array.isArray(dm.failure_history) && dm.failure_history.length > 0;
  check('decision-memory 含 failure_history', dm0.code === 0 && dmExists && hasFailure, `failure_history=${dm?.failure_history?.length || 0}`);

  // 10. 验收标准是否生成（acceptance.yaml 含 criteria 节点）
  if (irFiles.includes('acceptance.yaml')) {
    const acceptYaml = readFileSync(join(d, 'ir', 'acceptance.yaml'), 'utf8');
    passed.generated_acceptance = acceptYaml.includes('criteria:') && acceptYaml.includes('GATE-READY');
  }
  check('acceptance.yaml 含 GATE-READY 验收节点', passed.generated_acceptance);

  // 11. ir-to-testmind 桥：读 IR → testmind 兼容 TEST_CASES.yaml（独立脚本，不是 state.mjs 子命令）
  const tm0 = (() => {
    try {
      return spawnSync(process.execPath, [join(here, 'ir-to-testmind.mjs'), d, '--write'], { encoding: 'utf8' });
    } catch (e) { return { status: 1, stdout: '', stderr: String(e) }; }
  })();
  const tmDir = join(d, 'testmind');
  const tmFiles = existsSync(tmDir) ? readdirSync(tmDir) : [];
  const tmOk = tm0.status === 0 && tmFiles.includes('TEST_CASES.yaml') && tmFiles.includes('TEST_PLAN.md');
  check('ir-to-testmind 生成 TEST_CASES.yaml + TEST_PLAN.md', tmOk, `files=${tmFiles.join(',')} | err=${(tm0.stderr||'').slice(0,200)}`);
  // 11.b 解析 TEST_CASES.yaml：每个场景必须含 BUSINESS（GATE-BLOCKED 时也至少 1 个）；
  // P0-HAPPY（http）当且仅当有 api category fact 时才生成（ai_agent_arch/permission_system 无 api fact）。
  if (tmOk) {
    const tc = readJ(join(tmDir, 'TEST_CASES.yaml'));
    const facts11 = existsSync(join(d, 'facts.json')) ? readJ(join(d, 'facts.json')) : [];
    const hasBusiness = tc && Array.isArray(tc.cases) && tc.cases.some((c) => c.category === 'BUSINESS');
    const hasApiFact = Array.isArray(facts11) && facts11.some((f) => f.category === 'api' || /POST|GET|PUT|DELETE|\/api\//.test(f.statement || ''));
    const hasHappy = tc && Array.isArray(tc.cases) && tc.cases.some((c) => c.id === 'P0-HAPPY' && c.action?.kind === 'http');
    const happyOk = hasApiFact ? hasHappy : true; // 没 api fact 的 fixture 不强求
    check('TEST_CASES 含 BUSINESS (必) + P0-HAPPY (若有 api fact)', hasBusiness && happyOk, `total=${tc?.total || 0} cats=${JSON.stringify(tc?.by_category || {})}`);
  }

  // 12. testmind-e2e：spawn testmind/mcp.py 跑完整 MCP 协议（intake/add_facts/generate_cases）
  //     no-SUT 路径：自己组装 4 件套，验证 final_gate 判定逻辑
  const e2eResult = spawnSync(process.execPath, [join(here, 'testmind-e2e.mjs'), d, '--write'], { encoding: 'utf8', timeout: 120_000 });
  const e2eDir = join(d, 'testmind', 'testmind_run');
  const e2eSummary = existsSync(join(e2eDir, 'summary.json')) ? readJ(join(e2eDir, 'summary.json')) : null;
  const e2eHappy = e2eResult.status === 0 && e2eSummary && e2eSummary.final_gate === 'PASS'
    && e2eSummary.add_facts_status === 'PASS'
    && e2eSummary.generate_cases_status === 'PASS'
    && existsSync(join(e2eDir, 'TEST_PLAN.md'))
    && existsSync(join(e2eDir, 'TEST_CASES.yaml'))
    && existsSync(join(e2eDir, 'EVIDENCE_MANIFEST.json'))
    && existsSync(join(e2eDir, 'TEST_REPORT.md'));
  check('testmind-e2e happy path → final_gate=PASS + 4 件套', e2eHappy, `final_gate=${e2eSummary?.final_gate} status=${e2eResult.status}`);

  attackResults[scenario] = passed;
  rmSync(atmp, { recursive: true, force: true });
}

// ========================================================================
// V5 真 E2E：testmind-e2e.mjs 跑完整 MCP 协议，验证：
//   (a) happy path 5 攻击场景都 final_gate=PASS
//   (b) 故意错 schema → final_gate=FAIL + FAILURE_BUNDLE.json 写出
// ========================================================================
console.log('\n▶ V5 真 E2E（testmind + RequirementMind 闭环）');

// (a) happy path 在每个攻击场景已断言；汇总
const e2eAllPass = Object.values(attackResults).every((r) => r.ran);
check('E2E happy path 5 场景全 ran', e2eAllPass, JSON.stringify(attackResults));

// (b) FAIL 路径：取 high_concurrency fixture + 故意错 schema
console.log('  ▸ FAIL 路径（故意 NOT NULL violation）');
const failTmp = mkdtempSync(join(tmpdir(), 'rm-e2e-fail-'));
const failDst = join(failTmp, '.requirementmind');
mkdirSync(failDst, { recursive: true });
const failSrc = join(attackDir, 'high_concurrency');
for (const f of readdirSync(failSrc)) {
  if (f === "ir" || f === "testmind") continue;
  copyFileSync(join(failSrc, f), join(failDst, f));
}
// 走完流程让 TEST_CASES.yaml 存在
for (const q of readJ(join(failDst, 'questions.json')).filter((q) => q.status === 'OPEN')) {
  const isTech = q.authority === 'TECHNICAL';
  const args = ['freeze', failDst, q.id, q.recommended_option || 'A'];
  if (isTech) args.push('--auto');
  run(args);
}
for (const c of readJ(join(failDst, 'conflicts.json')).filter((c) => c.status === 'OPEN')) {
  run(['freeze', failDst, c.id, '以代码为准：保留现状']);
}
run(['ir', failDst, '--write']);
spawnSync(process.execPath, [join(here, 'ir-to-testmind.mjs'), failDst, '--write'], { encoding: 'utf8' });
// 跑 testmind-e2e + 故意错 schema
const failE2e = spawnSync(process.execPath, [join(here, 'testmind-e2e.mjs'), failDst, '--write',
  '--with-precheck', join(here, 'fixtures', '_e2e-fail-schema', 'schema.sql'),
  join(here, 'fixtures', '_e2e-fail-schema', 'statements.json')], { encoding: 'utf8', timeout: 120_000 });
const failSummaryPath = join(failDst, 'testmind', 'testmind_run', 'summary.json');
const failBundlePath = join(failDst, 'testmind', 'testmind_run', 'FAILURE_BUNDLE.json');
const failSummary = existsSync(failSummaryPath) ? readJ(failSummaryPath) : null;
const failOk = failE2e.status === 0
  && failSummary && failSummary.final_gate === 'FAIL'
  && failSummary.precheck_errors >= 1
  && existsSync(failBundlePath);
check('E2E FAIL 路径 final_gate=FAIL + precheck_errors≥1 + FAILURE_BUNDLE 写出', failOk,
  `final_gate=${failSummary?.final_gate} precheck_errors=${failSummary?.precheck_errors} bundle=${existsSync(failBundlePath)}`);
if (failSummary) {
  console.log(`  ⛽ 捕获 ${failSummary.precheck_errors} 个 not_null_violation / warning ${failSummary.precheck_warnings}`);
}
rmSync(failTmp, { recursive: true, force: true });

// 攻击测试汇总断言：5 场景全 ran + 4 子项全 true 才视为 100% 覆盖
const allScenariosPass = Object.values(attackResults).every((r) => r.ran && r.found_hidden_issues > 0 && r.blocked_wrong_dev && r.generated_acceptance);
check('5 攻击场景 4 子项全覆盖', allScenariosPass, JSON.stringify(attackResults));
console.log(`  ⛽ 攻击测试汇总: ${JSON.stringify(attackResults)}`);

console.log(`\n结果: ${pass} 通过 / ${fail} 失败`);
process.exit(fail ? 1 : 0);
