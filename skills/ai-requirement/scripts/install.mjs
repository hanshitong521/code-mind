#!/usr/bin/env node
/**
 * Install RequirementMind skill into a consumer project (Cursor / Agent OS).
 *
 *   node scripts/install.mjs [projectRoot]
 *
 * Copies canonical skill tree → `<project>/.cursor/skills/requirement-mind/`
 * Does not touch `.requirementmind/` session state in the consumer.
 */
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const MANIFEST = "requirementmind-manifest.json";
const SKIP = new Set([".git", "node_modules", MANIFEST]);

const COPY_DIRS = ["references", "schemas", "templates", "docs", "scripts"];
const COPY_FILES = ["SKILL.md", "REQUIREMENTS.md"];

function walkCopy(srcDir, destDir, files = []) {
	if (!existsSync(srcDir)) return files;
	for (const name of readdirSync(srcDir)) {
		if (SKIP.has(name)) continue;
		const s = join(srcDir, name);
		const d = join(destDir, name);
		if (statSync(s).isDirectory()) {
			mkdirSync(d, { recursive: true });
			walkCopy(s, d, files);
		} else {
			cpSync(s, d);
			files.push(relative(REPO_ROOT, s));
		}
	}
	return files;
}

function install(projectRoot) {
	const root = resolve(projectRoot || process.cwd());
	const dest = join(root, ".cursor", "skills", "requirement-mind");
	mkdirSync(dest, { recursive: true });

	const installed = [];
	for (const f of COPY_FILES) {
		const src = join(REPO_ROOT, f);
		if (!existsSync(src)) {
			console.error(`missing canonical file: ${f}`);
			process.exit(1);
		}
		cpSync(src, join(dest, f));
		installed.push(f);
	}
	for (const dir of COPY_DIRS) {
		const src = join(REPO_ROOT, dir);
		if (!existsSync(src)) continue;
		const sub = join(dest, dir);
		rmSync(sub, { recursive: true, force: true });
		mkdirSync(sub, { recursive: true });
		installed.push(...walkCopy(src, sub));
	}

	const manifest = {
		manifest_version: 1,
		installed_at: new Date().toISOString(),
		source_repo: REPO_ROOT,
		skill_dir: ".cursor/skills/requirement-mind",
		files: installed.sort(),
	};
	writeFileSync(join(REPO_ROOT, MANIFEST), `${JSON.stringify(manifest, null, 2)}\n`);
	writeFileSync(join(root, ".cursor", MANIFEST), `${JSON.stringify(manifest, null, 2)}\n`);

	console.log(`RequirementMind install OK → ${dest}`);
	console.log(`  files: ${installed.length}`);
	return manifest;
}

const target = process.argv[2] || process.env.REQUIREMENTMIND_CONSUMER;
if (!target) {
	console.error("Usage: node scripts/install.mjs <projectRoot>");
	process.exit(1);
}
install(target);
