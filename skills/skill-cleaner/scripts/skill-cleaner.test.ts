import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  canSuggestDeletion,
  compactDescription,
  discoverRoots,
  isRecentHistoryRecord,
  newestFilesFirst,
  parseLiveSkillsPrompt,
  plainLogSkillReads,
  referencedSkillPaths,
  tokenCost,
  usageEvidence,
} from "./skill-cleaner.ts";

test("honors the configured chars-per-token ratio", () => {
  assert.equal(tokenCost("12345678", 4), 2);
  assert.equal(tokenCost("12345678", 8), 1);
});

test("orders log files newest first", (context) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "skill-cleaner-log-order-"));
  context.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const older = path.join(temp, "older.jsonl");
  const newer = path.join(temp, "newer.jsonl");
  fs.writeFileSync(older, "{}\n");
  fs.writeFileSync(newer, "{}\n");
  fs.utimesSync(older, new Date(1_000), new Date(1_000));
  fs.utimesSync(newer, new Date(2_000), new Date(2_000));
  assert.deepEqual(newestFilesFirst([older, newer]), [newer, older]);
});

test("filters history records using second or millisecond timestamps", () => {
  const cutoff = 1_700_000_000_000;
  assert.equal(isRecentHistoryRecord({ ts: 1_699_999_999 }, cutoff), false);
  assert.equal(isRecentHistoryRecord({ ts: 1_700_000_001 }, cutoff), true);
  assert.equal(isRecentHistoryRecord({ ts: 1_699_999_999_999 }, cutoff), false);
  assert.equal(isRecentHistoryRecord({ ts: 1_700_000_000_001 }, cutoff), true);
  assert.equal(isRecentHistoryRecord({ text: "missing timestamp" }, cutoff), false);
});

test("never suggests deleting managed plugin cache skills", () => {
  assert.equal(canSuggestDeletion({ scope: "codex-plugin" }), false);
  assert.equal(canSuggestDeletion({ scope: "agents" }), true);
  assert.equal(canSuggestDeletion({ scope: "agent-scripts" }), true);
});

test("limits root discovery to explicitly supplied roots", (context) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "skill-cleaner-roots-"));
  context.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const defaultRoots = [
    path.join(temp, ".codex/skills"),
    path.join(temp, ".codex/plugins/cache"),
    path.join(temp, ".agents/skills"),
    path.join(temp, "Projects/agent-scripts/skills"),
    path.join(temp, "Projects/demo/.agents/skills"),
  ];
  const isolatedRoot = path.join(temp, "isolated/skills");
  for (const root of [...defaultRoots, isolatedRoot]) fs.mkdirSync(root, { recursive: true });

  assert.deepEqual(discoverRoots(temp, [isolatedRoot], true), [isolatedRoot]);
  assert.deepEqual(
    discoverRoots(temp, [isolatedRoot], false),
    [...defaultRoots, isolatedRoot].sort(),
  );
});

test("parses Codex skill roots and model-visible lines", () => {
  const raw = JSON.stringify([
    {
      role: "developer",
      content: [{
        type: "input_text",
        text: `<skills_instructions>
## Skills
### Skill roots
- \`r0\` = \`/tmp/skills\`
### Available skills
- demo: Demo work. (file: r0/demo/SKILL.md)
### How to use skills
</skills_instructions>`,
      }],
    },
  ]);

  const parsed = parseLiveSkillsPrompt(raw);
  assert.equal(parsed.roots.get("r0"), "/tmp/skills");
  assert.deepEqual(parsed.skillLines, [
    "- demo: Demo work. (file: r0/demo/SKILL.md)",
  ]);
});

test("compacts prose into a readable trigger phrase", () => {
  const compact = compactDescription(
    "Use this skill when the user wants to inspect calendars, compare availability, review conflicts, and schedule a meeting with timezone-aware details.",
    90,
  );
  assert.equal(
    compact,
    "inspect calendars, compare availability, review conflicts, and schedule a meeting with...",
  );
  assert.ok(compact.length <= 90);
  assert.doesNotMatch(compact, /audit, clean, verify/);
});

test("extracts user evidence without counting developer prompt listings", () => {
  assert.deepEqual(
    usageEvidence({ session_id: "abc", text: "use $skill-cleaner", ts: 123 }),
    { userText: "use $skill-cleaner" },
  );
  assert.deepEqual(
    usageEvidence({
      type: "response_item",
      payload: {
        type: "function_call",
        arguments: "{\"cmd\":\"cat /tmp/skills/demo/SKILL.md\"}",
      },
    }),
    { callArgs: "{\"cmd\":\"cat /tmp/skills/demo/SKILL.md\"}" },
  );
  assert.deepEqual(
    usageEvidence({
      type: "response_item",
      payload: {
        type: "custom_tool_call",
        input: "const result = await tools.exec_command({cmd: 'cat /tmp/skills/demo/SKILL.md'});",
      },
    }),
    {
      callArgs:
        "const result = await tools.exec_command({cmd: 'cat /tmp/skills/demo/SKILL.md'});",
    },
  );
  assert.deepEqual(
    usageEvidence({
      type: "response_item",
      payload: { type: "message", role: "developer", content: ["$skill-cleaner"] },
    }),
    {},
  );
});

test("resolves relative skill reads from function-call workdirs", () => {
  assert.deepEqual(
    referencedSkillPaths(JSON.stringify({
      cmd: "cat skills/demo/SKILL.md",
      workdir: "/tmp/repo",
    })),
    ["/tmp/repo/skills/demo/SKILL.md"],
  );
  assert.deepEqual(
    referencedSkillPaths(
      'const result = await tools.exec_command({"cmd":"cat skills/demo/SKILL.md","workdir":"/tmp/repo"});',
    ),
    ["/tmp/repo/skills/demo/SKILL.md"],
  );
});

test("counts command-like plain-log reads but ignores rendered listings", () => {
  assert.deepEqual(
    plainLogSkillReads([
      "cat skills/demo/SKILL.md",
      "- other: description (file: /tmp/skills/other/SKILL.md)",
    ].join("\n")),
    ["demo"],
  );
});

test("runs when invoked through a symbolic link", (context) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "skill-cleaner-symlink-"));
  context.after(() => fs.rmSync(temp, { recursive: true, force: true }));

  const root = path.join(temp, "skills");
  const demo = path.join(root, "demo");
  fs.mkdirSync(demo, { recursive: true });
  fs.writeFileSync(
    path.join(demo, "SKILL.md"),
    "---\nname: demo\ndescription: Demo skill for symlink execution.\n---\n\n# Demo\n",
  );

  const script = fileURLToPath(new URL("./skill-cleaner.ts", import.meta.url));
  const linkedScript = path.join(temp, "skill-cleaner.ts");
  fs.symlinkSync(script, linkedScript);

  const result = spawnSync(
    process.execPath,
    ["--experimental-strip-types", linkedScript, "--root", root, "--root-only", "--no-logs"],
    { encoding: "utf8" },
  );

  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /Skill Cleaner Report/);
  assert.match(result.stdout, /1 skills/);
});
