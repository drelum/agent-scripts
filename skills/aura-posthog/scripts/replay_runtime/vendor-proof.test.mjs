import { test } from "node:test";
import assert from "node:assert/strict";
import { cpSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { verifyVendor } from "./vendor-proof.mjs";

void test("included PostHog sources verify without a clone and reject changes", (t) => {
  const target = mkdtempSync(join(tmpdir(), "posthog-vendor-"));
  // Temporário preservado; nenhuma alteração no snapshot canônico.
  t.diagnostic(`Fixture: ${target}`);
  cpSync(new URL("./vendor/posthog", import.meta.url), target, { recursive: true });
  assert.equal(verifyVendor(target).commit, "f339527d3ede876431f9da61cbc901a705f8f60a");
  writeFileSync(join(target, "replay-headless/src/protocol.ts"), "changed");
  assert.throws(() => verifyVendor(target), /Fonte PostHog alterada/);
});
