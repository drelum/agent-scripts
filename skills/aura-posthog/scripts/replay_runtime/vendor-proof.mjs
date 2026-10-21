import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";

export function verifyVendor(root) {
  const manifest = JSON.parse(readFileSync(join(root, "manifest.json"), "utf8"));
  const expectedCommit = "f339527d3ede876431f9da61cbc901a705f8f60a";
  if (manifest.commit !== expectedCommit) throw new Error("Commit PostHog não confere.");
  const actual = readdirSync(root, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => relative(root, join(entry.parentPath, entry.name)))
    .filter((file) => file !== "manifest.json")
    .sort();
  const expected = Object.keys(manifest.files).sort();
  if (JSON.stringify(actual) !== JSON.stringify(expected))
    throw new Error("Inventário PostHog diverge do manifesto.");
  for (const file of actual) {
    const sha = createHash("sha256")
      .update(readFileSync(join(root, file)))
      .digest("hex");
    if (sha !== manifest.files[file]) throw new Error(`Fonte PostHog alterada: ${file}`);
  }
  return manifest;
}
