#!/usr/bin/env node
/** RM0–RM8 peak gates (consumer integration when SHEJIU_CONSUMER_ROOT set). */
import { existsSync, readdirSync, mkdtempSync, cpSync, rmSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { spawnSync } from "node:child_process";

// V5：peak-gate-lib 可能在多位置（旧仓库期望 shared/ 在 requirement-mind 同级，
// 新仓库 shared/ 在 A-skill 根下），多路径回退，最后给清晰错误。
const here = dirname(fileURLToPath(import.meta.url));
const libCandidates = [
  join(here, "../../shared/scripts/peak-gate-lib.mjs"),
  join(here, "../../../shared/scripts/peak-gate-lib.mjs"),
  join(here, "../../../../shared/scripts/peak-gate-lib.mjs"),
];
const libPath = libCandidates.find((p) => existsSync(p));
if (!libPath) {
  console.error("peak-gate-lib.mjs 未在以下相对路径找到，请检查仓库结构：");
  for (const p of libCandidates) console.error("  - " + p);
  process.exit(1);
}
const { gateEnvelope, printGateReport } = await import(pathToFileURL(libPath).href);

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

function gitCommit() {
	const r = spawnSync("git", ["rev-parse", "--short", "HEAD"], { cwd: ROOT, encoding: "utf8" });
	return r.status === 0 ? (r.stdout || "").trim() : "unknown";
}

const commit = gitCommit();
const gates = [];

gates.push(
	gateEnvelope({
		gate_id: "RM0",
		component: "requirement_mind",
		status: existsSync(join(ROOT, "schemas/active-session.schema.json")) ? "PASS" : "FAIL",
		summary: "active-session schema present",
		commit,
	}),
);

const selftest = (() => {
	const fixtureDir = join(ROOT, "scripts/fixtures/mock-session");
	const stateMjs = join(ROOT, "scripts/state.mjs");
	if (!existsSync(fixtureDir) || !existsSync(stateMjs)) {
		return { status: 1, stdout: "", stderr: "fixture or state.mjs missing" };
	}
	const tmp = mkdtempSync(join(tmpdir(), "rm-peak-gate-"));
	const rmDir = join(tmp, ".requirementmind");
	try {
		mkdirSync(rmDir, { recursive: true });
		for (const f of readdirSync(fixtureDir)) {
			cpSync(join(fixtureDir, f), join(rmDir, f));
		}
		return spawnSync(process.execPath, [stateMjs, "validate", rmDir], { encoding: "utf8", cwd: ROOT });
	} finally {
		try {
			rmSync(tmp, { recursive: true, force: true });
		} catch {
			/* temp */
		}
	}
})();

gates.push(
	gateEnvelope({
		gate_id: "RM1",
		component: "requirement_mind",
		status: selftest.status === 0 ? "PASS" : "FAIL",
		summary: selftest.status === 0 ? "mock-session validate via state.mjs" : "state validate on fixture failed",
		commit,
		findings:
			selftest.status === 0
				? []
				: [{ severity: "error", message: (selftest.stderr || selftest.stdout || "").slice(0, 400) }],
	}),
);

const CONSUMER = process.env.SHEJIU_CONSUMER_ROOT;
if (CONSUMER) {
	const rmRoot = join(CONSUMER, ".requirementmind");
	const active = join(rmRoot, "active-session.json");
	const stateMjs = join(ROOT, "scripts/state.mjs");
	const g = existsSync(stateMjs)
		? spawnSync(process.execPath, [stateMjs, "gate", rmRoot], { encoding: "utf8", cwd: ROOT })
		: { status: 1, stdout: "" };
	const ready = g.status === 0 && /READY_FOR_DEVELOPMENT/.test(g.stdout || "");
	for (const [id, ok, summary] of [
		["RM2", existsSync(join(ROOT, "scripts/migrate-sessions.mjs")), "migrate-sessions.mjs"],
		["RM3", existsSync(active), "consumer active-session.json"],
		["RM4", ready, "consumer gate READY_FOR_DEVELOPMENT"],
		["RM5", existsSync(join(ROOT, "schemas/state.schema.json")), "state.schema.json"],
		["RM6", existsSync(join(ROOT, "SKILL.md")), "SKILL.md canonical"],
		["RM7", existsSync(join(ROOT, "scripts/selftest.mjs")), "selftest.mjs present"],
		["RM8", existsSync(join(ROOT, "templates/DEVELOPMENT_SPEC.md")), "DEVELOPMENT_SPEC template"],
	]) {
		gates.push(
			gateEnvelope({
				gate_id: id,
				component: "requirement_mind",
				status: ok ? "PASS" : "FAIL",
				summary,
				commit,
				blocking: true,
			}),
		);
	}
} else {
	for (let i = 2; i <= 8; i++) {
		gates.push(
			gateEnvelope({
				gate_id: `RM${i}`,
				component: "requirement_mind",
				status: "NOT_REQUIRED",
				summary: `set SHEJIU_CONSUMER_ROOT for RM${i}`,
				commit,
				blocking: false,
			}),
		);
	}
}

const report = printGateReport("requirement_mind", gates);
process.exit(report.rollup === "PASS" ? 0 : 1);
