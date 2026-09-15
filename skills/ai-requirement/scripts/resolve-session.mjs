import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const SESSION_FILES = [
	"session.json",
	"facts.json",
	"questions.json",
	"decisions.json",
	"assumptions.json",
	"conflicts.json",
	"challenges.json",
	"evidence.json",
	"gate.json",
	"risk.json",
];

/**
 * @param {string} consumerRmDir - e.g. <project>/.requirementmind
 * @returns {{ mode: 'legacy'|'session', dir: string, session_id?: string }}
 */
export function resolveActiveSession(consumerRmDir) {
	const activePath = join(consumerRmDir, "active-session.json");
	if (!existsSync(activePath)) {
		return { mode: "legacy", dir: consumerRmDir };
	}
	let active;
	try {
		active = JSON.parse(readFileSync(activePath, "utf8"));
	} catch {
		return { mode: "legacy", dir: consumerRmDir };
	}
	const rel = active.session_path ?? (active.session_id ? `sessions/${active.session_id}` : null);
	if (!rel) return { mode: "legacy", dir: consumerRmDir };
	const sessionDir = join(consumerRmDir, rel);
	if (!existsSync(sessionDir)) {
		return { mode: "legacy", dir: consumerRmDir, session_id: active.session_id, error: "session_dir_missing" };
	}
	return {
		mode: "session",
		dir: sessionDir,
		session_id: active.session_id,
		version: active.version,
	};
}

export { SESSION_FILES };
