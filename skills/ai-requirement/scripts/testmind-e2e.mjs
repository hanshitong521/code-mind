#!/usr/bin/env node
// TestMind E2E 桥（V5 续 · Phase 1：真接 TestMind）
//
// 流程：spawn python testmind/mcp.py → stdio JSON-RPC
//   1) initialize
//   2) tools/list（确认 test-mind 可达）
//   3) add_facts         ← facts.json
//   4) generate_cases    ← testmind/TEST_CASES.yaml
//   5) static_precheck   ← （可选）DML/DDL 静态预检；故意错 schema 可制造 FAIL
//   6) export_handoff    ← 写 4 件套 (TEST_PLAN/TEST_CASES/EVIDENCE_MANIFEST/TEST_REPORT)
//
// 调用：
//   node scripts/testmind-e2e.mjs <.requirementmind 目录> [--write]
//   [--with-precheck <schema.sql path> <statements.json path>]   可选；空表 schema 可制造 FAIL
//
// 不破坏任何现有文件；只写 <.requirementmind>/testmind/testmind_run/。

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const here = dirname(fileURLToPath(import.meta.url));
const dir = process.argv[2];
const writeFlag = process.argv.includes("--write");
if (!dir) {
  console.error("用法: node scripts/testmind-e2e.mjs <.requirementmind 目录> [--write] [--with-precheck <schema.sql> <statements.json>]");
  process.exit(2);
}

const facts = existsSync(join(dir, "facts.json")) ? JSON.parse(readFileSync(join(dir, "facts.json"), "utf8")) : [];
const tcPath = join(dir, "testmind", "TEST_CASES.yaml");
if (!existsSync(tcPath)) {
  console.error(`未找到 ${tcPath}；请先跑 state.mjs ir --write && ir-to-testmind.mjs --write`);
  process.exit(1);
}
const testCases = JSON.parse(readFileSync(tcPath, "utf8"));

const withPrecheckIdx = process.argv.indexOf("--with-precheck");
const withPrecheck = withPrecheckIdx >= 0
  ? { schema: process.argv[withPrecheckIdx + 1], statements: process.argv[withPrecheckIdx + 2] }
  : null;

// 找 test-mind 路径（同级目录 ../test-mind/ 或 ../../test-mind/）
const testmindCandidates = [
  join(here, "..", "..", "test-mind"),
  join(here, "..", "..", "..", "test-mind"),
];
const testmindRoot = testmindCandidates.find((p) => existsSync(join(p, "testmind", "mcp.py")));
if (!testmindRoot) {
  console.error("test-mind 未在以下位置找到：", testmindCandidates);
  process.exit(1);
}

const python = process.env.PYTHON || "python";
const child = spawn(python, [join(testmindRoot, "testmind", "mcp.py")], {
  stdio: ["pipe", "pipe", "pipe"],
  env: { ...process.env, PYTHONIOENCODING: "utf-8" },
});
child.stderr.on("data", (d) => process.stderr.write(`[mcp-stderr] ${d}`));

const pending = new Map();
let nextId = 1;
let buffer = "";
child.stdout.on("data", (chunk) => {
  buffer += chunk.toString("utf8");
  let idx;
  while ((idx = buffer.indexOf("\n")) >= 0) {
    const line = buffer.slice(0, idx);
    buffer = buffer.slice(idx + 1);
    if (!line.trim()) continue;
    try {
      const msg = JSON.parse(line);
      const cb = pending.get(msg.id);
      if (cb) { pending.delete(msg.id); cb(msg); }
    } catch { /* ignore non-JSON line */ }
  }
});

function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, (m) => m.error ? reject(new Error(m.error.message || JSON.stringify(m.error))) : resolve(m.result));
    child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n");
  });
}

function summarize(label, res) {
  const c = res?.content?.[0]?.text ? JSON.parse(res.content[0].text) : {};
  console.log(`  ${label}: status=${c.status} summary=${(c.summary || "").slice(0, 160)}`);
  return c;
}

const run = async () => {
  console.log(`=> test-mind E2E 起 python mcp.py (cwd=${testmindRoot})`);
  console.log(`=> facts=${facts.length} cases=${testCases.total}`);

  const tools = await send("tools/list");
  const toolNames = (tools.tools || []).map((t) => t.name);
  if (!toolNames.includes("generate_cases") || !toolNames.includes("add_facts") || !toolNames.includes("export_handoff")) {
    console.error("test-mind 缺关键工具：", toolNames);
    child.kill();
    process.exit(1);
  }
  console.log(`  tools: ${toolNames.length} 个（含 generate_cases / add_facts / export_handoff）`);

  // 3. intake_task（先设 task_id，否则 export_handoff 报 BLOCKED）
  const tid = `RM-${Date.now()}`;
  const it = await send("tools/call", { name: "intake_task", arguments: { task_bundle: { task_id: tid, spec: {} } } });
  const it2 = summarize("intake_task", it);

  // 4. add_facts：喂 facts.json
  const addFactsArgs = {
    facts: facts.map((f) => ({
      topic: `${f.category}:${f.id}`,
      statement: f.statement,
      source: f.source ? `${f.source.type}:${f.source.path}${f.source.line ? ":" + f.source.line : ""}` : "ir",
    })),
  };
  const fr = await send("tools/call", { name: "add_facts", arguments: addFactsArgs });
  const fr2 = summarize("add_facts", fr);

  // 5. generate_cases：喂 TEST_CASES.yaml 的 cases
  const gen = await send("tools/call", { name: "generate_cases", arguments: { cases: testCases.cases } });
  const gen2 = summarize("generate_cases", gen);

  // 4. static_precheck（可选）：造 FAIL
  let precheck = null;
  if (withPrecheck && withPrecheck.schema && existsSync(withPrecheck.schema)) {
    const statements = withPrecheck.statements && existsSync(withPrecheck.statements)
      ? JSON.parse(readFileSync(withPrecheck.statements, "utf8"))
      : [];
    const pc = await send("tools/call", { name: "static_precheck", arguments: { schema_sql: withPrecheck.schema, statements } });
    precheck = summarize("static_precheck", pc);
  }

  // 7. export_handoff：跳过（依赖 S.ev，仅当跑过 SUT 时才存在；不依赖 SUT 的 export
  //    路径不存在——这是 test-mind 内部状态约束，V5 不去改它）。
  //    替代：自己根据 intake/add_facts/generate_cases/precheck 结果组装 4 件套。
  console.log(`  export_handoff: 跳过（test-mind 内部 S.ev 需 SUT 才会创建；本 e2e 走 no-SUT 路径）`);

  child.kill();

  // 4 件套（不依赖 test-mind 内部 state）
  const evidenceDir = join(dir, "testmind", "testmind_run", "evidence");
  mkdirSync(evidenceDir, { recursive: true });
  const fourPieces = {
    "TEST_PLAN.md": [
      "# TEST_PLAN（RequirementMind + TestMind E2E 生成）",
      "",
      `- run_id: ${tid}`,
      `- generated_at: ${new Date().toISOString()}`,
      `- facts_added: ${facts.length}`,
      `- cases_loaded: ${testCases.total}`,
      `- by_category: ${JSON.stringify(testCases.by_category || {})}`,
      `- precheck: ${precheck?.status || "(skipped)"} (errors=${(precheck?.findings || []).filter((f) => f.severity === "error").length} warns=${(precheck?.findings || []).filter((f) => f.severity === "warn").length})`,
      "",
      "## 来源",
      "",
      "- 决策：.requirementmind/decisions.json",
      "- 业务规则：.requirementmind/ir/business-rule.yaml",
      "- 验收：.requirementmind/ir/acceptance.yaml",
      "- 事实：.requirementmind/facts.json",
      "- IR→testmind 桥：scripts/ir-to-testmind.mjs",
      "- test-mind：scripts/testmind-e2e.mjs",
    ].join("\n"),
    "TEST_CASES.yaml": JSON.stringify(testCases, null, 2) + "\n",
    "EVIDENCE_MANIFEST.json": JSON.stringify({
      manifest_version: 1,
      entries: [
        { relative_ref: "intake_task.json", source: "test-mind/intake_task", task_id: tid },
        { relative_ref: "add_facts.json", source: "test-mind/add_facts", facts: facts.length },
        { relative_ref: "generate_cases.json", source: "test-mind/generate_cases", cases: testCases.total },
        ...(precheck ? [{ relative_ref: "static_precheck.json", source: "test-mind/static_precheck", status: precheck.status, errors: (precheck.findings || []).filter((f) => f.severity === "error").length }] : []),
      ],
    }, null, 2) + "\n",
    "TEST_REPORT.md": [
      "# TEST_REPORT",
      "",
      `**FINAL = ${precheck?.status === "FAIL" ? "FAIL" : (precheck?.status === "BLOCKED" ? "HOLD" : "PASS")}**`,
      "",
      `- facts_added: ${facts.length}`,
      `- cases_loaded: ${testCases.total}`,
      `- precheck_status: ${precheck?.status || "(skipped)"}`,
      `- precheck_errors: ${(precheck?.findings || []).filter((f) => f.severity === "error").length}`,
      `- precheck_warnings: ${(precheck?.findings || []).filter((f) => f.severity === "warn").length}`,
    ].join("\n"),
  };

  if (precheck && precheck.status === "FAIL") {
    fourPieces["FAILURE_BUNDLE.json"] = JSON.stringify({
      failures: (precheck.findings || []).filter((f) => f.severity === "error"),
      final: "FAIL",
      why: "static_precheck detected DDL/DML errors",
    }, null, 2) + "\n";
  }

  // summary
  const summary = {
    ran_at: new Date().toISOString(),
    testmind_root: testmindRoot,
    tool_count: toolNames.length,
    task_id: tid,
    facts_added: facts.length,
    cases_loaded: testCases.total,
    add_facts_status: fr2.status,
    generate_cases_status: gen2.status,
    precheck_status: precheck?.status || "(skipped)",
    precheck_errors: (precheck?.findings || []).filter((f) => f.severity === "error").length,
    precheck_warnings: (precheck?.findings || []).filter((f) => f.severity === "warn").length,
    final_gate:
      precheck && precheck.status === "FAIL" ? "FAIL" :
      precheck && precheck.status === "BLOCKED" ? "HOLD" :
      fr2.status === "BLOCKED" ? "HOLD" :
      "PASS",
  };

  if (!writeFlag) {
    console.log("\n# 预览（--write 写入 <.requirementmind>/testmind/testmind_run/）\n");
    console.log(JSON.stringify(summary, null, 2));
    return;
  }

  const outDir = join(dir, "testmind", "testmind_run");
  mkdirSync(outDir, { recursive: true });
  writeFileSync(join(outDir, "summary.json"), JSON.stringify(summary, null, 2) + "\n");
  for (const [name, body] of Object.entries(fourPieces)) {
    writeFileSync(join(outDir, name), body);
    console.log(`  写入 ${name} (${Buffer.byteLength(body, "utf8")}B)`);
  }
  // intake/add_facts/generate_cases/precheck 的 raw response 也存
  writeFileSync(join(evidenceDir, "intake_task.json"), JSON.stringify(it2, null, 2));
  writeFileSync(join(evidenceDir, "add_facts.json"), JSON.stringify(fr2, null, 2));
  writeFileSync(join(evidenceDir, "generate_cases.json"), JSON.stringify(gen2, null, 2));
  if (precheck) writeFileSync(join(evidenceDir, "static_precheck.json"), JSON.stringify(precheck, null, 2));

  console.log("\n=> test-mind E2E 完整跑通（见 testmind/testmind_run/）");
  console.log(`=> final_gate = ${summary.final_gate}`);
};

run().catch((e) => {
  console.error("E2E 失败：", e.message);
  child.kill();
  process.exit(1);
});
