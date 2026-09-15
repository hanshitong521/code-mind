#!/usr/bin/env node
// IR → TestMind 桥（V5 续：让 IR 不再是单向产出）
//
// 读 .requirementmind/ir/* + canonical JSON 状态，生成 test-mind 兼容的：
//   - testmind/TEST_CASES.yaml  （cases 数组，格式与 testmind/core.py::plan_cases 一致）
//   - testmind/TEST_PLAN.md     （人类可读概览 + 数据来源追溯）
//
// 调用：
//   node scripts/ir-to-testmind.mjs <.requirementmind 目录> [--write]
//
// 实现说明：ir/decision.json 已经是 JSON（不依赖 YAML 解析）；
// acceptance.yaml / business-rule.yaml 用最简 line-by-line 解析（生成格式固定）。

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dir = process.argv[2];
const writeFlag = process.argv.includes("--write");
if (!dir) {
  console.error("用法: node scripts/ir-to-testmind.mjs <.requirementmind 目录> [--write]");
  process.exit(2);
}

const readJson = (name) => {
  const p = join(dir, name);
  if (!existsSync(p)) return null;
  try { return JSON.parse(readFileSync(p, "utf8")); } catch { return null; }
};
const readText = (name) => {
  const p = join(dir, name);
  if (!existsSync(p)) return null;
  try { return readFileSync(p, "utf8"); } catch { return null; }
};
const isArr = (x) => Array.isArray(x) ? x : [];

const irReadText = (name) => {
  const p = join(dir, "ir", name);
  if (!existsSync(p)) return null;
  try { return readFileSync(p, "utf8"); } catch { return null; }
};
const irReadJson = (name) => {
  const t = irReadText(name);
  if (!t) return null;
  try { return JSON.parse(t); } catch { return null; }
};

// 极简列表解析：抽 `  - key: value` 行 + 后续 `    key: value` 子字段直到下一个 `- ` 或段尾
function parseBlockList(text, blockName) {
  if (!text) return [];
  const lines = text.split(/\r?\n/);
  const out = [];
  let inBlock = false;
  let current = null;
  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");
    if (!inBlock) {
      if (line === `${blockName}:`) inBlock = true;
      continue;
    }
    // 退出条件：出现顶级 key（缩进 0-2 且不是空行且不是 `  -` 或 `    key:`）
    if (line && !line.startsWith(" ") && line.endsWith(":")) break;
    if (line === "" || line.startsWith("#")) continue;
    const itemMatch = line.match(/^  - (\w[\w_]*):\s*(.*)$/);
    const subMatch = line.match(/^    (\w[\w_]*):\s*(.*)$/);
    if (itemMatch) {
      if (current) out.push(current);
      current = { [itemMatch[1]]: itemMatch[2].replace(/^['"]|['"]$/g, "") };
    } else if (subMatch && current) {
      current[subMatch[1]] = subMatch[2].replace(/^['"]|['"]$/g, "");
    } else if (line === "  -" && current) {
      // 一些 yaml 里空 list item；忽略
    }
  }
  if (current) out.push(current);
  return out;
}

const acceptanceText = irReadText("acceptance.yaml");
const businessText = irReadText("business-rule.yaml");
const decisionObj = irReadJson("decision.json");
const facts = isArr(readJson("facts.json"));
const session = readJson("session.json") || {};

const factMap = new Map(facts.map((f) => [f.id, f]));

function buildCase(id, category, priority, source, action, expected, extra = {}) {
  return { id, category, priority, source, action, expected, ...extra };
}

const cases = [];

// 1. GATE-READY 节点：全局烟测
if (acceptanceText && /GATE-READY/.test(acceptanceText)) {
  cases.push(buildCase(
    "G0-GATE-READY",
    "GATE",
    "P0",
    "ir/acceptance.yaml",
    { kind: "meta", check: "hard_counters_all_zero" },
    { gate_status: "READY_FOR_DEVELOPMENT" },
    { description: "硬门槛（blocking_questions/conflicts/assumptions/high_risks）= 0" },
  ));
}

// 2. business-rule → 每条 FROZEN decision 一条 BUSINESS case（直接读 JSON）
const frozen = (decisionObj && decisionObj.frozen) || [];
for (const d of frozen) {
  cases.push(buildCase(
    `B-${d.id}`,
    "BUSINESS",
    "P0",
    d.id,
    { kind: "rule", check: "decision_frozen", rule: d.decision },
    { rule_id: d.id, topic: d.topic, rule: d.decision, impact: d.impact || [] },
    {
      description: `${d.topic}: ${d.decision}`,
      basis: d.basis || null,
    },
  ));
}

// 3. acceptance.yaml 阻塞问题 → BOUNDARY cases
const criteria = parseBlockList(acceptanceText, "criteria");
for (const c of criteria) {
  if (c.id === "GATE-READY" || c.id === "GATE-BLOCKED") continue;
  const isBlocking = (c.status || "").toUpperCase() === "BLOCKING";
  cases.push(buildCase(
    `A-${c.id}`,
    isBlocking ? "BOUNDARY" : "ACCEPTANCE",
    isBlocking ? "P0" : "P1",
    c.source || "ir/acceptance.yaml",
    { kind: "answer_required", check: "user_decision" },
    { rule: c.rule || null, source: c.source || null },
    { description: c.rule || "" },
  ));
}

// 4. facts 中带 API 端点 → 至少 1 条 P0-HAPPY（让 test-mind 有入口）
const httpFact = facts.find((f) => f.category === "api" || /POST|GET|PUT|DELETE|\/api\//.test(f.statement));
if (httpFact) {
  const m = httpFact.statement.match(/(POST|GET|PUT|DELETE)\s+(\S+)/);
  const method = m ? m[1] : "POST";
  const path = m ? m[2] : "/api/unknown";
  cases.push(buildCase(
    "P0-HAPPY",
    "BUSINESS",
    "P0",
    httpFact.id,
    { kind: "http", method, path, body: {} },
    { http: 200, db_no_write: false },
    { description: `主路径烟测（来自 ${httpFact.id}：${httpFact.statement}）` },
  ));
}

const result = {
  contract_version: 1,
  generated_at: new Date().toISOString(),
  source_ir: existsSync(join(dir, "ir")) ? "ir/" : "(missing — 请先跑 state.mjs ir --write)",
  source_session: { requirement: session.requirement || null, phase: session.phase || null },
  total: cases.length,
  by_category: cases.reduce((acc, c) => { acc[c.category] = (acc[c.category] || 0) + 1; return acc; }, {}),
  cases,
};

const plan = [
  "# TEST_PLAN（由 RequirementMind IR 自动生成）",
  "",
  `- run_id: ${new Date().toISOString()}`,
  `- source_session: ${session.requirement || "(un-named)"}`,
  `- phase: ${session.phase || "(none)"}`,
  `- total_cases: ${cases.length}`,
  `- by_category: ${JSON.stringify(result.by_category)}`,
  "",
  "## 来源",
  "",
  "- ir/acceptance.yaml (硬门槛 + BLOCKING/IMPORTANT 验收)",
  "- ir/business-rule.yaml / ir/decision.json (FROZEN 业务规则)",
  "- facts.json (项目事实，作为 case source 引用)",
  "",
  "## 用途",
  "",
  "test-mind 可直接读 testmind/TEST_CASES.yaml 跑 run_pipeline；",
  "未填 expected.http 的 case (BUSINESS/BOUNDARY/ACCEPTANCE) 由 test-mind 标记为 NOT_TESTED（不阻塞 final_gate）。",
  "",
  "## Case 总览",
  "",
  ...cases.map((c) => `- \`${c.id}\` [${c.category}/${c.priority}] source=${c.source} — ${c.description || c.action?.check || c.action?.method || ""}`),
].join("\n");

if (!writeFlag) {
  console.log("# 预览（--write 写入 .requirementmind/testmind/）\n");
  console.log("===== TEST_PLAN.md =====");
  console.log(plan);
  console.log("\n===== TEST_CASES.yaml =====");
  console.log(JSON.stringify(result, null, 2));
  process.exit(0);
}

const outDir = join(dir, "testmind");
mkdirSync(outDir, { recursive: true });
writeFileSync(join(outDir, "TEST_CASES.yaml"), JSON.stringify(result, null, 2) + "\n");
writeFileSync(join(outDir, "TEST_PLAN.md"), plan + "\n");
console.log(`写入 ${join(".requirementmind/testmind/TEST_CASES.yaml")} (${cases.length} cases)`);
console.log(`写入 ${join(".requirementmind/testmind/TEST_PLAN.md")}`);
console.log(`\n=> 下游：test-mind 可读 testmind/TEST_CASES.yaml 跑 run_pipeline`);
